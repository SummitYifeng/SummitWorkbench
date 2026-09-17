"""``wb doctor``：正式使用前的端到端预检（正式使用前加固 #3）。

``wb diagnose`` 只查底座（运行时/路径/系统工具）；各 provider 的连通性此前散在
``feishu smoke`` / ``model smoke``。启用那一刻最怕「配了但某一环没通」。``doctor`` 把
「明天的定时简报能不能跑」收敛成一条命令：底座 → 配置 → vault schema → 凭据可解析 →
（可选）飞书 token 真的有效 → launchd 已装。

**默认完全离线、无副作用**：只读配置与 Keychain（`security find-generic-password`，
只验证「能否解析」，绝不打印秘密值），不联网、不轮换任何 token、不花模型钱。
``--online`` 才追加一次真实的飞书 token 刷新（会正常轮换 refresh_token）——这是对「每日
简报的飞书事实源」最直接的预检。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import typer

from summit_workbench.cli import diagnostics
from summit_workbench.config.profiles import ActiveWorkspaceContext, resolve_active_workspace
from summit_workbench.config.secrets import CredentialError, CredentialRef, resolve_credential
from summit_workbench.config.settings import Settings, default_config_file, load_settings
from summit_workbench.providers.feishu.config import FeishuConfig, load_feishu_config
from summit_workbench.providers.feishu.errors import FeishuAuthError, FeishuError
from summit_workbench.providers.feishu.session import FeishuSession
from summit_workbench.providers.llm import LLMError, load_model_config
from summit_workbench.repositories.vault import check_vault
from summit_workbench.webapp.build_info import mode_from_environment

# launchd 定时任务的标签与安装路径（见 scripts/install-launchd.sh）。
_LAUNCHD_LABELS = ("com.summitworkbench.brief", "com.summitworkbench.weekly")


class CheckStatus(StrEnum):
    OK = "ok"
    WARN = "warn"  # 未就绪但不阻断（未配置、可按需创建、可选组件缺失）
    FAIL = "fail"  # 已配置却坏了 / 硬性不达标


@dataclass(frozen=True)
class Check:
    name: str
    status: CheckStatus
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {"name": self.name, "status": self.status.value, "detail": self.detail}


def _base_checks(settings: Settings) -> list[Check]:
    report = diagnostics.collect(settings)
    checks = [
        Check(
            "Python",
            CheckStatus.OK if report.python_ok else CheckStatus.FAIL,
            f"{report.python_version}（需 ≥ 3.12）",
        )
    ]
    for tool, present in report.tools.items():
        # git/security 是核心；launchctl 仅定时任务需要，缺失降级为 WARN。
        hard = tool != "launchctl"
        status = CheckStatus.OK if present else (CheckStatus.FAIL if hard else CheckStatus.WARN)
        checks.append(Check(f"系统工具 {tool}", status, "可用" if present else "未找到"))
    checks.append(
        Check(
            "工作根目录",
            CheckStatus.OK if report.work_root_exists else CheckStatus.WARN,
            f"{report.work_root}（{'存在' if report.work_root_exists else '待创建'}）",
        )
    )
    checks.append(
        Check(
            "vault 目录",
            CheckStatus.OK if report.vault_dir_exists else CheckStatus.WARN,
            f"{report.vault_dir}（{'存在' if report.vault_dir_exists else '待创建'}）",
        )
    )
    cfg_state = "已找到" if report.config_file_found else "未创建，用内置默认值"
    checks.append(
        Check(
            "配置文件",
            CheckStatus.OK if report.config_file_found else CheckStatus.WARN,
            f"{report.config_file}（{cfg_state}）",
        )
    )
    return checks


def _vault_schema_check(vault_dir: Path) -> Check:
    if not vault_dir.is_dir():
        return Check("vault schema", CheckStatus.WARN, "vault 目录尚不存在，跳过")
    issues = check_vault(vault_dir, work_vault=True)
    if not issues:
        return Check("vault schema", CheckStatus.OK, "全部 Markdown 通过 schema 校验")
    return Check(
        "vault schema",
        CheckStatus.WARN,
        f"{len(issues)} 篇存在问题（用 wb vault check 查看详情）",
    )


def _credential_check(name: str, ref: CredentialRef) -> Check:
    """尝试解析一条凭据；只报告能否解析，绝不打印值。"""
    try:
        resolve_credential(ref)
    except CredentialError as exc:
        return Check(name, CheckStatus.FAIL, f"Keychain 无法解析（{ref}）：{exc}")
    return Check(name, CheckStatus.OK, f"Keychain 可解析（{ref}）")


def _feishu_app_secret_check(cfg: FeishuConfig) -> Check:
    """验证飞书 app_secret 的实际解析路径（Keychain 或安装包内置凭据）。"""
    try:
        FeishuSession(cfg)._app_secret()
    except (CredentialError, FeishuError) as exc:
        return Check("飞书 app_secret", CheckStatus.FAIL, f"凭据无法解析：{exc}")
    return Check("飞书 app_secret", CheckStatus.OK, "Keychain 或安装包内置凭据可解析")


def _feishu_checks(
    config_file: Path, *, online: bool, workspace_id: str | None = None
) -> list[Check]:
    try:
        cfg = load_feishu_config(config_file, workspace_id=workspace_id)
    except FeishuError as exc:
        return [Check("飞书配置", CheckStatus.WARN, f"未配置或不完整：{exc}")]

    checks = [
        Check("飞书配置", CheckStatus.OK, f"app_id={cfg.app_id}"),
        _feishu_app_secret_check(cfg),
        _credential_check("飞书 refresh_token", cfg.refresh_token_ref),
    ]
    if online:
        checks.append(_feishu_online_check(cfg))
    return checks


def _feishu_online_check(cfg: FeishuConfig) -> Check:
    """真实刷新一次飞书 token（会正常轮换 refresh_token）。仅 --online 调用。"""
    try:
        FeishuSession(cfg).access_token()
    except FeishuAuthError as exc:
        if getattr(exc, "needs_reauthorize", False):
            return Check(
                "飞书 token（在线）",
                CheckStatus.FAIL,
                f"需重新授权，请运行 wb feishu login：{exc}",
            )
        return Check("飞书 token（在线）", CheckStatus.FAIL, f"刷新失败：{exc}")
    except FeishuError as exc:
        return Check("飞书 token（在线）", CheckStatus.FAIL, f"刷新失败：{exc}")
    return Check("飞书 token（在线）", CheckStatus.OK, "刷新成功（已轮换 refresh_token）")


def _model_checks(config_file: Path, *, workspace_id: str | None = None) -> list[Check]:
    try:
        cfg = load_model_config("ranking", config_file, workspace_id=workspace_id)
    except LLMError as exc:
        return [Check("模型配置", CheckStatus.WARN, f"未配置或不完整：{exc}")]
    return [
        Check("模型配置", CheckStatus.OK, f"{cfg.model_id} @ {cfg.base_url}"),
        _credential_check("模型 api key", cfg.api_key_ref),
    ]


def _launchd_check() -> Check:
    la_dir = Path.home() / "Library" / "LaunchAgents"
    installed = [label for label in _LAUNCHD_LABELS if (la_dir / f"{label}.plist").is_file()]
    if len(installed) == len(_LAUNCHD_LABELS):
        return Check("launchd 定时任务", CheckStatus.OK, "brief + weekly 均已安装")
    if not installed:
        return Check(
            "launchd 定时任务",
            CheckStatus.WARN,
            "未安装（用 scripts/install-launchd.sh 安装，或手动运行 wb brief/weekly）",
        )
    return Check("launchd 定时任务", CheckStatus.WARN, f"仅安装了 {', '.join(installed)}")


def run_checks(
    settings: Settings,
    *,
    config_file: Path,
    online: bool,
    context: ActiveWorkspaceContext | None = None,
) -> list[Check]:
    """跑全部预检，返回结构化结果（离线安全；online 才碰网络）。"""
    if context is not None and context.is_onboarding_required:
        return [
            Check(
                "工作区",
                CheckStatus.WARN,
                "尚未选择工作区：请在 SummitWorkbench onboarding 中新建、连接或升级",
            )
        ]
    checks = _base_checks(settings)
    vault_dir = (
        context.paths.vault_dir if context and context.paths else settings.work_paths().vault_dir
    )
    workspace_id = context.workspace_id if context else None
    checks.append(_vault_schema_check(vault_dir))
    checks.extend(_feishu_checks(config_file, online=online, workspace_id=workspace_id))
    checks.extend(_model_checks(config_file, workspace_id=workspace_id))
    checks.append(_launchd_check())
    return checks


_ICON = {CheckStatus.OK: "✓", CheckStatus.WARN: "⚠", CheckStatus.FAIL: "✗"}


def doctor_command(
    online: bool = typer.Option(
        False,
        "--online",
        help="追加真实飞书 token 刷新检查（联网，会正常轮换 refresh_token）。",
    ),
    as_json: bool = typer.Option(False, "--json", help="以 JSON 输出，便于脚本/CI 判定。"),
) -> None:
    """端到端预检：底座/配置/vault/凭据/(可选)飞书 token/launchd。

    退出码：无 FAIL 返回 0，存在 FAIL 返回 1（WARN 不影响退出码）。
    """
    panel_mode = mode_from_environment(os.environ.get("WB_PANEL_MODE"))
    context = resolve_active_workspace(allow_env_fallback=panel_mode != "production")
    settings = load_settings(
        work_root=context.paths.work_root if context.paths else None,
        vault_dir=context.paths.vault_dir if context.paths else None,
        timezone=context.timezone,
    )
    config_file = context.config_file or default_config_file()
    checks = run_checks(settings, config_file=config_file, online=online, context=context)

    if as_json:
        import json

        failed = any(c.status is CheckStatus.FAIL for c in checks)
        typer.echo(
            json.dumps(
                {"ok": not failed, "checks": [c.as_dict() for c in checks]},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        for check in checks:
            typer.echo(f"{_ICON[check.status]} {check.name}：{check.detail}")
        fails = [c for c in checks if c.status is CheckStatus.FAIL]
        warns = [c for c in checks if c.status is CheckStatus.WARN]
        typer.echo("")
        if fails:
            typer.echo(f"预检未通过：{len(fails)} 项 FAIL、{len(warns)} 项 WARN。")
        else:
            typer.echo(f"预检通过：0 项 FAIL、{len(warns)} 项 WARN（WARN 不阻断）。")

    raise typer.Exit(code=1 if any(c.status is CheckStatus.FAIL for c in checks) else 0)
