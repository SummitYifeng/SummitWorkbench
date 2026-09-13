"""P0-08 onboarding 服务测试：create / upgrade / connect 三条流程。

覆盖计划矩阵：新建成功、目标非空拒绝、中途失败回滚、重复提交幂等；旧 vault 升级后
内容哈希不变、仅新增 marker/profile/backup；连接 workspace 隔离；CloudStorage 网盘
路径拒绝（普通本地路径通过）；模板含个人化 fixture 时卫生扫描拒绝；全程不运行系统 git。
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest

from summit_workbench.config.app_support import backups_dir, registry_file
from summit_workbench.domain.onboarding import OnboardingFlow
from summit_workbench.domain.workspace import Compatibility, DeviceRole
from summit_workbench.repositories.profile_registry import (
    active_profile_id,
    load_profile,
    load_registry,
    profile_ids,
)
from summit_workbench.repositories.workspace_manifest import load_workspace_manifest
from summit_workbench.workflows import onboarding
from summit_workbench.workflows.onboarding import (
    OnboardingError,
    connect_workspace,
    create_workspace,
    detect_cloud_storage,
    preflight,
    scan_template_hygiene,
    upgrade_workspace,
)

DAY = "2026-09-05"
APP_VERSION = "9.9.9"  # 测试注入：新 marker 的 min 版本


def test_default_templates_resolves_pyinstaller_internal_data(monkeypatch, tmp_path: Path) -> None:
    module_path = (
        tmp_path
        / "SummitWorkbench.app"
        / "Contents"
        / "Resources"
        / "server"
        / "_internal"
        / "summit_workbench"
        / "workflows"
        / "onboarding.py"
    )
    bundled_templates = (
        tmp_path
        / "SummitWorkbench.app"
        / "Contents"
        / "Resources"
        / "server"
        / "_internal"
        / "templates"
        / "vault"
    )
    bundled_templates.mkdir(parents=True)
    monkeypatch.delenv("WB_VAULT_TEMPLATES", raising=False)
    monkeypatch.setattr(onboarding, "__file__", str(module_path))

    assert onboarding.default_vault_templates_dir() == bundled_templates


def _templates(tmp_path: Path) -> Path:
    """干净的最小 vault 种子模板（无个人化内容）。"""
    templates = tmp_path / "templates"
    templates.mkdir(exist_ok=True)
    (templates / "inbox.template.md").write_text(
        "---\ndate: {{date}}\ntype: inbox\n---\n\n# 收件箱\n", encoding="utf-8"
    )
    (templates / "conventions.template.md").write_text(
        "# 约定\n\n通用模板，无个人路径。\n", encoding="utf-8"
    )
    return templates


def _vault_content_hash(vault: Path) -> str:
    """vault 内既有文件内容的稳定摘要（不含 marker/备份等新增物）。"""
    hasher = hashlib.sha256()
    for path in sorted(p for p in vault.rglob("*") if p.is_file()):
        if ".summit-workbench" in path.parts:
            continue
        hasher.update(str(path.relative_to(vault)).encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
    return hasher.hexdigest()


def _seed_legacy_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "legacy-vault"
    vault.mkdir()
    (vault / "inbox.md").write_text("# inbox\n- [ ] 旧条目\n", encoding="utf-8")
    (vault / "daily").mkdir()
    (vault / "daily" / "2026-09-01.md").write_text("---\ndate: 2026-09-01\n---\n", encoding="utf-8")
    return vault


# ---- create-new ----


def test_create_workspace_succeeds_with_seed_and_marker(tmp_path) -> None:
    home = tmp_path / "home"
    work = tmp_path / "new-work"
    result = create_workspace(
        work,
        home=home,
        templates_dir=_templates(tmp_path),
        day=DAY,
        app_version=APP_VERSION,
        device_name="Studio",
    )
    vault = work / "_vault"
    assert result.workspace_id
    assert result.vault_dir == str(vault)
    assert result.device_id
    # 种子文件 + marker 就位；{{date}} 已填充
    assert vault.is_dir()
    assert "date: 2026-09-05" in (vault / "inbox.md").read_text(encoding="utf-8")
    assert (vault / "conventions.md").is_file()
    manifest = load_workspace_manifest(vault)
    assert manifest is not None
    assert manifest.workspace_id == result.workspace_id
    assert manifest.min_reader_version == APP_VERSION
    assert manifest.min_writer_version == APP_VERSION
    # profile 建档并设为 active
    assert active_profile_id(home=home) == result.workspace_id
    profile = load_profile(result.workspace_id, home=home)
    assert profile is not None
    assert str(profile.vault_dir) == result.vault_dir
    # D1（2026-09-13）：新工作台必须纳入版本管理——否则「写回自动留痕」静默失效、
    # 「设置 → Git 同步」预览直接 500。初始化只经 P0-09 backend（不跑系统 git），分支为 main。
    from summit_workbench.repositories.git import GitRepo

    repo = GitRepo(vault, backend_kind="dulwich")
    assert repo.is_git_repo()
    assert repo.current_branch() == "main"
    revision = repo.head_revision()
    assert revision is not None
    assert repo.commit_subject(revision) == "wb: onboarding create"
    committed = set(repo.files_changed_by(revision))
    assert "inbox.md" in committed
    assert ".summit-workbench/workspace.json" in committed


def test_create_refuses_when_vault_target_already_exists(tmp_path) -> None:
    home = tmp_path / "home"
    work = tmp_path / "used-work"
    (work / "_vault").mkdir(parents=True)
    (work / "_vault" / "inbox.md").write_text("既有内容", encoding="utf-8")
    with pytest.raises(OnboardingError) as ei:
        create_workspace(work, home=home, templates_dir=_templates(tmp_path), day=DAY)
    assert any("已存在" in reason or "非空" in reason for reason in ei.value.reasons)
    # 原目录一字未动
    assert (work / "_vault" / "inbox.md").read_text(encoding="utf-8") == "既有内容"
    assert profile_ids(home=home) == []


def test_create_failure_midway_rolls_back_everything(tmp_path, monkeypatch) -> None:
    """registry 激活前失败：本次创建的 vault/marker/profile/registry 全部回滚。"""
    home = tmp_path / "home"
    work = tmp_path / "rollback-work"
    from summit_workbench.workflows import onboarding as onboarding_mod

    def boom(*_args, **_kwargs) -> None:
        raise RuntimeError("模拟激活失败")

    monkeypatch.setattr(onboarding_mod, "set_active_profile", boom)
    with pytest.raises(OnboardingError) as ei:
        create_workspace(
            work,
            home=home,
            templates_dir=_templates(tmp_path),
            day=DAY,
            app_version=APP_VERSION,
        )
    assert "回滚" in str(ei.value)
    assert not (work / "_vault").exists(), "新建的 vault 应被回滚删除"
    assert profile_ids(home=home) == []
    assert not registry_file(home).exists() or load_registry(home).active_workspace_id is None


def test_duplicate_create_is_rejected_idempotently(tmp_path) -> None:
    home = tmp_path / "home"
    work = tmp_path / "work"
    create_workspace(work, home=home, templates_dir=_templates(tmp_path), day=DAY)
    with pytest.raises(OnboardingError):
        create_workspace(work, home=home, templates_dir=_templates(tmp_path), day=DAY)
    # 只存在一份 profile，active 仍是第一个
    assert len(profile_ids(home=home)) == 1
    first_manifest = load_workspace_manifest(work / "_vault")
    assert first_manifest is not None
    assert active_profile_id(home=home) == first_manifest.workspace_id


def test_personalized_template_is_rejected(tmp_path) -> None:
    home = tmp_path / "home"
    templates = _templates(tmp_path)
    (templates / "conventions.template.md").write_text(
        "参考：/Users/alice/Documents/Work\n", encoding="utf-8"
    )
    issues = scan_template_hygiene(templates, home=tmp_path / "home")
    assert issues, "含绝对用户路径的模板必须被卫生扫描命中"
    with pytest.raises(OnboardingError) as ei:
        create_workspace(tmp_path / "work", home=home, templates_dir=templates, day=DAY)
    assert any("模板" in reason for reason in ei.value.reasons)
    assert not (tmp_path / "work" / "_vault").exists()


def test_cloud_storage_work_root_is_rejected(tmp_path) -> None:
    home = tmp_path / "home"
    cloud_root = tmp_path / "Dropbox" / "Work"
    assert detect_cloud_storage(cloud_root) is True
    report = preflight(
        OnboardingFlow.CREATE_NEW, cloud_root, templates_dir=_templates(tmp_path), home=home
    )
    assert report.cloud_storage is True
    assert not report.ok
    with pytest.raises(OnboardingError):
        create_workspace(cloud_root, home=home, templates_dir=_templates(tmp_path), day=DAY)
    assert not (cloud_root / "_vault").exists()


def test_plain_local_path_passes_preflight(tmp_path) -> None:
    work = tmp_path / "local-work"
    report = preflight(
        OnboardingFlow.CREATE_NEW, work, templates_dir=_templates(tmp_path), home=tmp_path
    )
    assert report.ok
    assert report.cloud_storage is False


def test_preflight_detects_existing_git_dir_without_running_git(tmp_path) -> None:
    vault = tmp_path / "repo-vault"
    vault.mkdir()
    (vault / ".git").mkdir()  # 只放目录模拟 git repo，绝不运行 git 命令
    report = preflight(OnboardingFlow.UPGRADE_EXISTING, vault, home=tmp_path)
    assert report.has_git_dir is True


def test_connect_remote_preflight_allows_new_target_and_rejects_nonempty(tmp_path) -> None:
    """P1-07D：Air remote clone 目标目录尚未存在时通过；非空目录被拒绝。"""
    target = tmp_path / "new-vault"
    report = preflight(OnboardingFlow.CONNECT_REMOTE, target, home=tmp_path)
    assert report.ok

    target.mkdir()
    (target / "f.txt").write_text("x", encoding="utf-8")
    report = preflight(OnboardingFlow.CONNECT_REMOTE, target, home=tmp_path)
    assert not report.ok
    assert any("非空" in reason for reason in report.rejections)


# ---- upgrade-existing ----


def test_upgrade_keeps_content_and_only_adds_marker_profile_backup(tmp_path) -> None:
    home = tmp_path / "home"
    vault = _seed_legacy_vault(tmp_path)
    before_hash = _vault_content_hash(vault)
    result = upgrade_workspace(vault, home=home, app_version=APP_VERSION, device_name="Studio")
    # 内容哈希不变：只新增 marker，不改任何业务文件
    assert _vault_content_hash(vault) == before_hash
    manifest = load_workspace_manifest(vault)
    assert manifest is not None
    assert manifest.workspace_id == result.workspace_id
    assert manifest.min_reader_version == APP_VERSION
    assert active_profile_id(home=home) == result.workspace_id
    # 备份存在于 Application Support/backups（timestamped）
    assert result.backup_dir is not None
    backup_path = Path(result.backup_dir)
    assert backup_path.is_dir()
    assert backup_path.is_relative_to(backups_dir(home=home))
    assert list(backup_path.iterdir()), "备份目录不应为空"
    # 没有 .git 被创建
    assert not (vault / ".git").exists()


def test_upgrade_with_existing_marker_is_rejected(tmp_path) -> None:
    home = tmp_path / "home"
    vault = _seed_legacy_vault(tmp_path)
    upgrade_workspace(vault, home=home, app_version=APP_VERSION)
    with pytest.raises(OnboardingError) as ei:
        upgrade_workspace(vault, home=home, app_version=APP_VERSION)
    assert any("已是工作区" in reason or "connect" in reason for reason in ei.value.reasons)
    # 幂等：不会生成第二份 profile / 备份
    assert len(profile_ids(home=home)) == 1


# ---- connect-local ----


def test_connect_local_reads_marker_and_builds_profile(tmp_path) -> None:
    home = tmp_path / "home"
    vault = tmp_path / "shared-vault"
    create_workspace(
        tmp_path / "maker",
        home=tmp_path / "other-home",
        templates_dir=_templates(tmp_path),
        day=DAY,
        app_version=APP_VERSION,
        device_name="Maker",
    )  # 先由另一台机器（另一 home）造出带 marker 的 vault
    other_vault = tmp_path / "maker" / "_vault"
    manifest = load_workspace_manifest(other_vault)
    assert manifest is not None
    # 直接移动 vault 到共享位置模拟 clone/拷贝后的连接（不运行 git）
    shutil.copytree(other_vault, vault)

    result = connect_workspace(vault, home=home, app_version=APP_VERSION, device_name="Air")
    connected_manifest = load_workspace_manifest(vault)
    assert connected_manifest is not None
    assert result.workspace_id == connected_manifest.workspace_id
    assert active_profile_id(home=home) == result.workspace_id
    profile = load_profile(result.workspace_id, home=home)
    assert profile is not None
    assert str(profile.vault_dir) == str(vault)
    assert profile.workspace_id == manifest.workspace_id


def _maker_vault_with_claim(tmp_path: Path) -> tuple[Path, Path, Path]:
    """造一个由"另一台机器"创建、带 automation-primary 声明的 vault，并拷贝到共享位置。

    返回 ``(maker_home, air_home, copied_vault)``。
    """
    maker_home = tmp_path / "maker-home"
    air_home = tmp_path / "air-home"
    create_workspace(
        tmp_path / "maker-work",
        home=maker_home,
        templates_dir=_templates(tmp_path),
        day=DAY,
        app_version=APP_VERSION,
        device_name="Maker",
    )
    vault = tmp_path / "shared-vault"
    shutil.copytree(tmp_path / "maker-work" / "_vault", vault)
    return maker_home, air_home, vault


def test_connect_local_marker_pointing_at_this_device_becomes_primary(tmp_path) -> None:
    """D10：marker 指定的设备连接自己的 vault 时必须是 automation-primary。

    修复前 connect 一律写 secondary ⇒ ``automation_gate`` 在 marker 指定的主设备上也不
    放行定时自动化，而界面没有改角色的入口（真机绕行见 §Q.1）。
    变异验证：把 ``connect_device_role`` 改成恒返回 SECONDARY，本用例失败。
    """
    from summit_workbench.domain.sync import AutomationOutcome
    from summit_workbench.repositories.automation_primary import (
        load_automation_primary,
    )
    from summit_workbench.workflows.sync_coordinator import automation_gate

    maker_home, _, vault = _maker_vault_with_claim(tmp_path)
    # 同一台机器（同一 home ⇒ 同一 device id）重新连接自己创建的工作台
    result = connect_workspace(vault, home=maker_home, app_version=APP_VERSION)
    profile = load_profile(result.workspace_id, home=maker_home)
    assert profile is not None
    assert profile.device_role is DeviceRole.AUTOMATION_PRIMARY
    claim = load_automation_primary(vault)
    assert claim is not None and claim.device_id == result.device_id
    assert (
        automation_gate(profile, claim=claim, device_id=result.device_id, require_claim=True)
        is AutomationOutcome.PRIMARY_OK
    )


def test_connect_local_marker_pointing_at_other_device_stays_secondary(tmp_path) -> None:
    """D10 的另一半：marker 属于别的设备时连接者只能是 secondary，且**不得抢占**。

    变异验证：把 ``connect_device_role`` 改成恒返回 AUTOMATION_PRIMARY，本用例的
    角色断言与"claim 不失败"断言都会失败（等于 connect 偷偷接管了主设备）。
    """
    from summit_workbench.domain.sync import AutomationOutcome
    from summit_workbench.repositories.automation_primary import (
        AutomationPrimaryError,
        claim_automation_primary,
        load_automation_primary,
    )
    from summit_workbench.workflows.sync_coordinator import automation_gate

    _, air_home, vault = _maker_vault_with_claim(tmp_path)
    before = load_automation_primary(vault)
    assert before is not None

    result = connect_workspace(vault, home=air_home, app_version=APP_VERSION)
    profile = load_profile(result.workspace_id, home=air_home)
    assert profile is not None
    assert profile.device_role is DeviceRole.SECONDARY
    assert result.device_id != before.device_id

    after = load_automation_primary(vault)
    assert after is not None
    # 声明没被连接流程改写：仍是原设备、原 generation
    assert (after.device_id, after.generation) == (before.device_id, before.generation)
    with pytest.raises(AutomationPrimaryError) as ei:
        claim_automation_primary(
            vault, result.workspace_id, result.device_id, expected_generation=after.generation
        )
    assert ei.value.code == "primary_already_claimed"
    assert (
        automation_gate(profile, claim=after, device_id=result.device_id, require_claim=True)
        is AutomationOutcome.NOT_PRIMARY
    )


def test_connect_local_without_primary_marker_keeps_secondary_default(tmp_path) -> None:
    """D10：没有主设备声明时沿用连接流程既有语义（secondary），不新造声明。"""
    from summit_workbench.repositories.automation_primary import (
        automation_primary_path,
        load_automation_primary,
    )

    _, air_home, vault = _maker_vault_with_claim(tmp_path)
    automation_primary_path(vault).unlink()

    result = connect_workspace(vault, home=air_home, app_version=APP_VERSION)
    profile = load_profile(result.workspace_id, home=air_home)
    assert profile is not None
    assert profile.device_role is DeviceRole.SECONDARY
    assert load_automation_primary(vault) is None


def test_connect_requires_marker_and_rejects_cannot_open(tmp_path) -> None:
    home = tmp_path / "home"
    # 无 marker 的 vault → 拒绝，提示走 upgrade
    plain = tmp_path / "plain-vault"
    plain.mkdir()
    (plain / "inbox.md").write_text("x", encoding="utf-8")
    with pytest.raises(OnboardingError) as ei:
        connect_workspace(plain, home=home, app_version=APP_VERSION)
    assert any("marker" in reason.lower() for reason in ei.value.reasons)

    # min_reader 高于当前 app → cannot-open → 拒绝连接
    future = tmp_path / "future-vault"
    create_workspace(
        tmp_path / "future-work",
        home=tmp_path / "future-home",
        templates_dir=_templates(tmp_path),
        day=DAY,
        app_version="10.0.0",
    )
    shutil.copytree(tmp_path / "future-work" / "_vault", future)
    report = preflight(OnboardingFlow.CONNECT_LOCAL, future, home=home, app_version=APP_VERSION)
    assert report.compatibility is Compatibility.CANNOT_OPEN
    with pytest.raises(OnboardingError) as ei:
        connect_workspace(future, home=home, app_version=APP_VERSION)
    assert any("升级" in reason for reason in ei.value.reasons)
    assert profile_ids(home=home) == []


def test_two_workspaces_profiles_do_not_cross_read(tmp_path) -> None:
    home = tmp_path / "home"
    create_workspace(tmp_path / "work-a", home=home, templates_dir=_templates(tmp_path), day=DAY)
    create_workspace(tmp_path / "work-b", home=home, templates_dir=_templates(tmp_path), day=DAY)
    ids = profile_ids(home=home)
    assert len(ids) == 2
    active = active_profile_id(home=home)
    assert active == ids[1]  # 最近创建的是 active
    profile_a = load_profile(ids[0], home=home)
    profile_b = load_profile(ids[1], home=home)
    assert profile_a is not None and profile_b is not None
    # B 的 profile 绝不会带出 A 的 vault 路径
    assert "work-a" not in str(profile_b.vault_dir)
    assert "work-b" not in str(profile_a.vault_dir)
