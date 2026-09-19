#!/usr/bin/env python3
"""跨端回归闸门：一句话跑完 SWB → `_vault` → SK 的关键不变量。

存在理由（2026-09-18 三端走通走查实际踩到的四类坑，各自都曾在"测试全绿"的情况下发生）：

1. **审批/导入后工作树残留未提交改动** → SWB 同步被 `dirty-protected` 停摆。
   （`review_apply` 的提交路径集合漏了会议笔记状态与 `_signals` 审计日志。）
2. **`_signals/` 被重新加回 git 跟踪** → 机器本地状态入库、工作树反复变脏。
   （`add()` 曾不读 `.gitignore`。）
3. **原始素材进检索语料** → 逐字稿噪音污染索引；`inbox.md` 却不该进语料。
   （`WORK_EXCLUDED_TYPES` 曾缺 `meeting-transcript`；`_allowed()` 曾只查 status。）
4. **精排静默失效** → 每次提问白跑一次失败请求再降级，界面不报警。
   （存量端点不会随代码默认值迁移。）

2026-09-19 批次 A 追加两条**写入端改造**的不变量（都只在"有真实库"的环境里才有意义）：

5. **原件（`<project>/sources/`）与简报/周复盘类型不进语料** → 契约 §9/§9.1 只把结论页
   留在检索语料里；`source` 与 `daily` / `weekly-review` 只写不检索。
6. **来源白名单覆盖真实库的全部主线项目** → 白名单是 SWB 里的"看得见的常量"，库里加了
   项目目录而白名单没跟上时，`路径#区块` 引用点开会 400（2026-09-19 实测约 612 条引用落空）。
   这条守卫必须放在闸门里：`tests/unit/test_knowledge_sources.py` 在 CI/异机会因拿不到
   真实库而 skip，等于没守住。

**⚠️ 写入与推送的边界（2026-09-19 真实事故，务必先读）**：

闸门的 `[2/6]` 会向 **SWB 端点**发一次真实 capture。SWB 的每一条写路径在 commit 之后都会
经 `sync_coordinator.push_after_commit` **自动推送 vault 远端**——这是 App 的正常行为，
但验证动作不该顺带推送。当时 `--no-push` 只挡住了闸门收尾那一个提交，挡不住端点自己的推送，
结果验证件连同本地未推提交被一起发布到了 `origin/main`。

⇒ **正确姿势**：用**源码**起一个带 `WB_NO_AUTO_PUSH=1` 的服务，再用 `--swb-url/--swb-token`
把闸门指过去：

    WB_NO_AUTO_PUSH=1 WB_SESSION_TOKEN=... \
        ./.venv/bin/python -m summit_workbench.cli.main web --host 127.0.0.1 --port 8791 &
    ./.venv/bin/python scripts/kb_three_end_gate.py \
        --swb-url http://127.0.0.1:8791 --swb-token ... --no-push-cleanup

不要拿正在跑的 App 做验证：App 里没有这个开关（装了新版本才有），capture 必然推送。

用法（**会写 vault、会花钱**：一次极小模型调用 + 检索时的嵌入/精排费用）：

    ./.venv/bin/python scripts/kb_three_end_gate.py            # 跑完整闸门并自动清理验证件
    ./.venv/bin/python scripts/kb_three_end_gate.py --keep     # 保留验证件供人工查看
    ./.venv/bin/python scripts/kb_three_end_gate.py --no-cleanup
    # 收尾提交只留本地、不推 vault：
    ./.venv/bin/python scripts/kb_three_end_gate.py --no-push-cleanup
    # 指向"源码起、带 WB_NO_AUTO_PUSH=1"的服务：
    ./.venv/bin/python scripts/kb_three_end_gate.py --swb-url URL --swb-token TOK

`--no-push` 是 `--no-push-cleanup` 的**弃用别名**（同名参数历史上只关掉收尾那一推，容易
被读成"整个闸门不推送"；实际挡不住端点自动推送）。

默认行为不变（清理提交后推送）；`--no-push-cleanup` 只把**收尾那一次**推送显式关掉，并记为
WARN——推送与否是使用者的决定，不该由一次验证顺带执行。闸门还会记录 vault 的 `origin/main`
前后取值：**未启用收尾推送却发生变化时**会醒目告警（那说明有别的写入者推了 vault）。

退出码：0 = 全部通过（允许 WARN）；1 = 有 FAIL。
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Iterable
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from summit_workbench.config.auto_push import AUTO_PUSH_DISABLE_ENV  # noqa: E402
from summit_workbench.repositories.vault import parse_frontmatter  # noqa: E402
from summit_workbench.webapp.knowledge_sources import (  # noqa: E402
    KNOWLEDGE_SOURCE_ROOTS,
    _is_knowledge_source,
)

MARKER_PREFIX = "【回归闸门验证件】"
DEFAULT_QUESTION = "奖学金折扣要不要收 royalty？"

# 检索返回里**绝不允许出现**的类型：逐字稿、原件、简报/周复盘（契约 §5.2）。
FORBIDDEN_CORPUS_TYPES = frozenset({"meeting-transcript", "source", "daily", "weekly-review"})


# ────────────────────────── 输出 ──────────────────────────
class Report:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.warnings: list[str] = []

    def ok(self, label: str, detail: str = "") -> None:
        print(f"  \033[32m✅\033[0m {label}" + (f" — {detail}" if detail else ""))

    def warn(self, label: str, detail: str = "") -> None:
        self.warnings.append(label)
        print(f"  \033[33m⚠️\033[0m  {label}" + (f" — {detail}" if detail else ""))

    def fail(self, label: str, detail: str = "") -> None:
        self.failures.append(label)
        print(f"  \033[31m❌\033[0m {label}" + (f" — {detail}" if detail else ""))

    def check(self, cond: bool, label: str, detail: str = "") -> bool:
        (self.ok if cond else self.fail)(label, detail)
        return cond


# ────────────────────── 进程与令牌 ──────────────────────
def _env_of(pid: str, name: str) -> str:
    """从进程环境读一个变量；读不到（进程不存在/无权限/命令失败）返回空串。"""
    try:
        out = subprocess.run(["ps", "eww", "-p", pid], capture_output=True, text=True).stdout
    except OSError:
        return ""
    for token in out.split():
        if token.startswith(f"{name}="):
            return token.split("=", 1)[1]
    return ""


def _pid_listening_on(port: int) -> str | None:
    """监听某端口的进程 pid（用来读它的环境变量）；查不到返回 None。"""
    try:
        out = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            capture_output=True,
            text=True,
        ).stdout.split()
    except OSError:
        return None
    return out[0] if out else None


def auto_push_state_of_pid(pid: str | None) -> bool | None:
    """该端点进程是否启用了"不自动推送"。None = 查不到进程/环境。

    闸门必须能说清"这次 capture 会不会被端点自动推送"——否则又一次"验证顺手推了 vault"。
    """
    if not pid:
        return None
    raw = _env_of(str(pid), AUTO_PUSH_DISABLE_ENV)
    if raw == "":
        # 变量缺失与变量为空都视为"未启用"——与 auto_push_disabled() 的判据一致。
        return False
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def swb_endpoint(
    home: Path,
    *,
    url: str | None = None,
    token: str | None = None,
) -> tuple[str, str, str | None]:
    """解析 SWB 端点 → ``(base_url, session_token, pid|None)``。

    - 显式 ``--swb-url``（配合 ``--swb-token`` 或 env ``WB_SESSION_TOKEN``）优先；
      这种形态通常指向"源码起、带 ``WB_NO_AUTO_PUSH=1``"的服务。
    - 否则沿用 ``runtime.json``（即用户正在跑的 App）——注意 App 里**没有**新开关，
      capture 会被自动 commit + push。
    """
    if url:
        base = url.rstrip("/")
        resolved = token or os.environ.get("WB_SESSION_TOKEN", "")
        if not resolved:
            raise SystemExit("✗ 指定 --swb-url 时必须同时提供 --swb-token（或设 WB_SESSION_TOKEN）")
        parsed = urllib.parse.urlsplit(base)
        pid = _pid_listening_on(parsed.port) if parsed.port else None
        return base, resolved, pid
    runtime = home / "Library/Application Support/SummitWorkbench/runtime.json"
    if not runtime.is_file():
        raise SystemExit("✗ 未找到 SWB runtime.json：SummitWorkbench 是否在运行？")
    data = json.loads(runtime.read_text(encoding="utf-8"))
    pid = str(data["pid"])
    tok = _env_of(pid, "WB_SESSION_TOKEN")
    if not tok:
        raise SystemExit("✗ 无法从 SWB 进程环境读取 WB_SESSION_TOKEN")
    return f"http://127.0.0.1:{data['port']}", tok, pid


def sk_endpoint() -> tuple[str, str, str]:
    pid = subprocess.run(
        ["pgrep", "-f", "SummitKnowledgeServer"], capture_output=True, text=True
    ).stdout.split()
    if not pid:
        raise SystemExit("✗ 未找到 SummitKnowledgeServer：SK App 是否在运行？")
    token = _env_of(pid[0], "SUMMIT_API_TOKEN")
    if not token:
        raise SystemExit("✗ 无法从 SK 进程环境读取 SUMMIT_API_TOKEN")
    return "http://127.0.0.1:8580", token, pid[0]


def http_json(
    url: str,
    *,
    token: str,
    payload: dict[str, Any] | None = None,
    header: str,
    origin: str | None = None,
    timeout: int = 180,
) -> dict[str, Any]:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    # SK 用 `Authorization: Bearer <token>`，SWB 用 `X-WB-Session-Token: <token>`
    req.add_header(header, f"Bearer {token}" if header == "Authorization" else token)
    if data:
        req.add_header("Content-Type", "application/json")
    if origin:
        req.add_header("Origin", origin)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # 永远直连
    try:
        with opener.open(req, timeout=timeout) as resp:
            return cast(dict[str, Any], json.loads(resp.read().decode("utf-8")))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise SystemExit(f"✗ HTTP {exc.code} {url}\n{body[:500]}") from None


# ────────────────────────── git ──────────────────────────
def git(vault: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(vault), *args], capture_output=True, text=True).stdout


def worktree_dirty(vault: Path) -> list[str]:
    return [ln for ln in git(vault, "status", "--porcelain").splitlines() if ln.strip()]


def tracked_signals(vault: Path) -> list[str]:
    return [ln for ln in git(vault, "ls-files", "_signals/").splitlines() if ln.strip()]


def origin_main_rev(vault: Path) -> str:
    """vault 的 ``origin/main`` 当前取值（本地跟踪 ref）；没有则返回占位串。"""
    return git(vault, "rev-parse", "--short", "origin/main").strip() or "(无 origin/main)"


def push_vault(vault: Path) -> tuple[bool, str]:
    """推送闸门自己的清理提交。

    本机网络是**波动**的：`github.com` 时而直连可用、时而只通 macOS 系统代理
    （实测同一晚两种都出现过）。所以这里**直连优先、失败回退代理**；
    两者都失败只算 WARN（vault 本地仍自洽，不是闸门失败）。
    用显式 refspec `origin HEAD`：不依赖 branch.<name>.merge 的上游配置是否干净。
    """
    direct = subprocess.run(
        ["git", "-C", str(vault), "push", "origin", "HEAD"], capture_output=True, text=True
    )
    if direct.returncode == 0:
        return True, "直连推送成功"
    proxy = subprocess.run(
        [
            "git",
            "-C",
            str(vault),
            "-c",
            "http.proxy=http://127.0.0.1:7890",
            "-c",
            "https.proxy=http://127.0.0.1:7890",
            "push",
            "origin",
            "HEAD",
        ],
        capture_output=True,
        text=True,
    )
    if proxy.returncode == 0:
        return True, "经系统代理推送成功"
    return False, (direct.stderr or proxy.stderr or "未知错误").strip()[:200]


def active_db(vector_work: Path) -> Path:
    manifest = vector_work / "active_index.json"
    if manifest.is_file():
        loaded = cast(dict[str, Any], json.loads(manifest.read_text(encoding="utf-8")))
        db = vector_work / str(loaded["db_file"])
        if db.is_file():
            return db
    candidates: list[Path] = sorted(vector_work.glob("vectors*.db"))
    return candidates[-1]


def active_profile(health: dict[str, Any]) -> dict[str, Any] | None:
    """返回 health 里当前活动知识库那条 profile（没有就返回 None）。"""
    active = health.get("active_kb_id")
    return next((p for p in health.get("profiles", []) if p["id"] == active), None)


# ──────────────── 语料边界与白名单的纯判定（便于脱机验证/变异） ────────────────
def corpus_boundary_counts(con: sqlite3.Connection) -> dict[str, int]:
    """语料边界的关键计数。纯查询，不依赖端点，可对合成库做脱机验证与变异。"""

    def count(sql: str, params: tuple[object, ...] = ()) -> int:
        return int(con.execute(sql, params).fetchone()[0])

    return {
        "transcripts": count(
            "SELECT COUNT(*) FROM chunks WHERE source_file LIKE 'meetings/transcripts/%'"
        ),
        # 原件层：契约 §1.1 把逐字原件放在 `<project-id>/sources/`（含 sources/attachments/）。
        "sources": count(
            "SELECT COUNT(*) FROM chunks "
            "WHERE source_file LIKE '%/sources/%' OR source_file LIKE 'sources/%'"
        ),
        # 简报/周复盘：按类型与按路径双查（旧 App 回写到 daily/ 或 reviews/weekly/ 也会命中）。
        "daily_weekly": count(
            "SELECT COUNT(*) FROM chunks "
            "WHERE type IN ('daily','weekly-review') "
            "OR source_file LIKE 'daily/%' OR source_file LIKE 'reviews/%'"
        ),
        "inbox": count("SELECT COUNT(*) FROM chunks WHERE source_file = 'inbox.md'"),
    }


def forbidden_types_in(sources: list[dict[str, Any]]) -> list[str]:
    """检索结果里出现的**禁止类型**（空列表 = 通过）。"""
    types = {s.get("type") for s in sources if isinstance(s, dict)}
    return sorted(t for t in FORBIDDEN_CORPUS_TYPES if t in types)


def whitelist_missing(project_ids: Iterable[str]) -> list[str]:
    """这些项目 ID 里，哪些**不能**作为知识来源打开（空列表 = 白名单覆盖全部）。"""
    return sorted(
        pid for pid in project_ids if not _is_knowledge_source(Path(pid) / "notes" / "probe.md")
    )


def project_ids_of(vault: Path) -> list[str]:
    """真实库 `projects/*.md` 的主线项目 ID（frontmatter `project`，回退文件名）。"""
    projects_dir = vault / "projects"
    if not projects_dir.is_dir():
        return []
    ids: list[str] = []
    for path in sorted(projects_dir.glob("*.md")):
        meta, _body, _error = parse_frontmatter(path.read_text(encoding="utf-8"))
        value = meta.get("project")
        ids.append(str(value).strip() if isinstance(value, str) and value.strip() else path.stem)
    return ids


# ────────────────────── 闸门各段 ──────────────────────
def gate_preflight(
    rep: Report, vault: Path, swb_url: str, swb_tok: str, swb_origin: str, sk_url: str, sk_tok: str
) -> int:
    """返回起始 pending_index，供 [4/6] 判断"闸门自己的写入有没有让索引变脏"。"""
    print("\n[1/6] 前置：三端可用 + 起始状态干净")
    rep.check(vault.is_dir(), f"vault 存在（{vault}）")
    rep.check(
        not worktree_dirty(vault),
        "vault 起始工作树干净",
        "" if not worktree_dirty(vault) else str(worktree_dirty(vault)[:3]),
    )
    rep.check(
        not tracked_signals(vault),
        "`_signals/` 未被跟踪",
        f"被跟踪 {len(tracked_signals(vault))} 个",
    )
    sync = http_json(
        f"{swb_url}/api/sync/status", token=swb_tok, header="X-WB-Session-Token", origin=swb_origin
    )
    state = sync.get("state")
    if state == "ready":
        rep.ok("SWB 同步 state=ready")
    elif state == "error":
        rep.warn("SWB 同步 state=error", f"{sync.get('detail')}（网络类，不判失败）")
    else:
        rep.fail("SWB 同步 state 健康", f"state={state} detail={sync.get('detail')}")
    health = http_json(f"{sk_url}/api/health", token=sk_tok, header="Authorization")
    rep.check(
        bool(health.get("ready")), "SK /api/health ready", f"active_kb={health.get('active_kb_id')}"
    )
    prof = active_profile(health)
    pending_before = int((prof or {}).get("pending_index") or 0)
    if pending_before:
        rep.warn(
            "起始 pending_index>0（索引落后于库，非闸门问题）",
            f"pending={pending_before}；可能是新的一天简报/一次 capture/审批写回造成",
        )
    return pending_before


def gate_mutation(
    rep: Report, vault: Path, swb_url: str, swb_tok: str, swb_origin: str, keep: bool
) -> str:
    """S-1(a)/S-1(b)：真实写入之后，工作树必须干净、`_signals` 必须没被回跟踪。"""
    print("\n[2/6] 写入路径：真实 capture 之后工作树是否干净、`_signals` 是否被回跟踪")
    marker = f"{MARKER_PREFIX}{uuid.uuid4().hex[:8]}"
    res = http_json(
        f"{swb_url}/api/capture",
        token=swb_tok,
        header="X-WB-Session-Token",
        origin=swb_origin,
        payload={"text": f"#it-development {marker} 跨端回归闸门"},
    )
    rep.check(
        bool(res.get("ok")), "capture 成功", f"kind={res.get('kind')} project={res.get('project')}"
    )
    commit = (res.get("commit") or {}).get("status")
    rep.check(commit == "committed", "capture 产生了提交", f"commit={commit}")
    dirty = worktree_dirty(vault)
    rep.check(not dirty, "写入后工作树仍然干净（S-1(a)）", "" if not dirty else str(dirty[:5]))
    sig = tracked_signals(vault)
    rep.check(not sig, "写入后 `_signals/` 仍未被跟踪（S-1(b)）", "" if not sig else str(sig[:5]))
    touched = [
        ln
        for ln in git(vault, "show", "--name-only", "--format=", "HEAD").splitlines()
        if ln.strip()
    ]
    bad = [p for p in touched if p.startswith("_signals/")]
    rep.check(not bad, "capture 提交未混入 `_signals/`", f"HEAD 触及：{touched}")
    rep.ok("本轮验证件标记", marker if keep else marker)
    return marker


def gate_source_whitelist(rep: Report, vault: Path) -> None:
    """来源白名单必须覆盖**真实库**的全部主线项目目录（含 `thinking`）。

    这条守卫只在这里成立：单元测试里的同名断言在 CI/异机拿不到真实库只能 skip。
    白名单是 SWB 的"看得见的常量"，故意不做运行时派生——代价就是必须有人（这里）
    在真实库上守它。
    """
    print("\n[3/6] 来源白名单：真实库的全部主线项目都可达")
    project_ids = project_ids_of(vault)
    rep.check(bool(project_ids), "真实库有主线项目页", f"{len(project_ids)} 个")
    missing = whitelist_missing(project_ids)
    rep.check(
        not missing,
        "全部主线项目目录在来源白名单内（点『来源』不报 400）",
        f"缺失 {missing}",
    )
    rep.check(
        "thinking" in KNOWLEDGE_SOURCE_ROOTS,
        "`thinking/` 在来源白名单内",
        f"白名单 {len(KNOWLEDGE_SOURCE_ROOTS)} 项",
    )


def gate_corpus(
    rep: Report,
    vault: Path,
    sk_url: str,
    sk_tok: str,
    vector_work: Path,
    marker: str,
    pending_before: int,
) -> None:
    """P1-4 + 批次 A：语料边界——逐字稿 / inbox / 原件 / 简报周报都不该进语料。"""
    print("\n[4/6] 语料边界：逐字稿、inbox、原件与简报周报都不得进检索语料")
    db = active_db(vector_work)
    # WAL 库用 mode=ro 打开会因缺 -shm 失败（实测），普通连接做 SELECT 是安全的
    con = sqlite3.connect(db, timeout=10)
    try:
        counts = corpus_boundary_counts(con)
        hit = con.execute(
            "SELECT COUNT(*) FROM chunks WHERE content LIKE ?", (f"%{marker}%",)
        ).fetchone()[0]
    finally:
        con.close()
    rep.check(
        counts["transcripts"] == 0,
        "语料中无 `meetings/transcripts/*`（逐字稿已排除）",
        f"命中 {counts['transcripts']}",
    )
    rep.check(counts["inbox"] == 0, "语料中无 `inbox.md`", f"命中 {counts['inbox']}")
    rep.check(
        counts["sources"] == 0,
        "语料中无 `<project>/sources/` 下片段（原件不进语料）",
        f"命中 {counts['sources']}",
    )
    rep.check(
        counts["daily_weekly"] == 0,
        "语料中无 daily / weekly-review 片段（简报周报不在库内）",
        f"命中 {counts['daily_weekly']}",
    )
    rep.check(hit == 0, "本次 capture 未进语料（inbox 类型被排除）", f"命中 {hit}")

    health = http_json(f"{sk_url}/api/health", token=sk_tok, header="Authorization")
    prof = active_profile(health)
    if prof:
        pending_after = int(prof.get("pending_index") or 0)
        # 真正要守的是「闸门自己的写入（inbox capture）不得让索引变脏」；
        # 起始就 >0 只是"索引落后于库"（新的一天简报 / 别人刚 capture / 审批写回），
        # 与闸门要守的不变量无关，所以只告警不判失败。
        rep.check(
            pending_after <= pending_before,
            "闸门写入未让 pending_index 增长（inbox 不进语料）",
            f"{pending_before} → {pending_after}",
        )
        if pending_after:
            rep.warn(
                "活动库 pending_index>0（索引落后于库，非缺陷）",
                f"pending={pending_after}；跑一次 SK 增量索引即可清零",
            )


def gate_retrieval(rep: Report, sk_url: str, sk_tok: str, question: str) -> None:
    """P0-4 + 语料边界：精排必须真的生效，且结果里不得出现非语料类型。"""
    print("\n[5/6] 检索路径：精排是否真的生效、结果是否混入非语料类型")
    payload = {"query": question, "profile_id": "work"}
    req = urllib.request.Request(
        f"{sk_url}/api/chat/stream", data=json.dumps(payload).encode(), method="POST"
    )
    req.add_header("Authorization", f"Bearer {sk_tok}")
    req.add_header("Content-Type", "application/json")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    sources: list[dict[str, Any]] = []
    answer: list[str] = []
    with opener.open(req, timeout=240) as resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data: "):
                continue
            try:
                ev: dict[str, Any] = json.loads(line[6:])
            except Exception:
                continue
            if "token" in ev:
                answer.append(str(ev["token"]))
            elif ev.get("error"):
                rep.fail("检索返回错误", str(ev)[:200])
            elif ev.get("done"):
                sources = cast(list[dict[str, Any]], ev.get("sources") or [])
    rep.check(bool(sources), "检索有证据返回", f"{len(sources)} 条")
    rep.check(bool("".join(answer).strip()), "回答非空")
    applied = {s.get("rerank_applied") for s in sources if isinstance(s, dict)}
    reasons = {s.get("rerank_degraded_reason") for s in sources if isinstance(s, dict)}
    rep.check(
        applied == {True},
        "精排真的生效（rerank_applied 全为 True）",
        f"applied={applied} reasons={reasons}",
    )
    types = {s.get("type") for s in sources if isinstance(s, dict)}
    bad_types = forbidden_types_in(sources)
    rep.check(
        not bad_types,
        "结果中无 source / daily / weekly-review / meeting-transcript",
        f"命中 {bad_types}；types={types}",
    )
    health = http_json(f"{sk_url}/api/health", token=sk_tok, header="Authorization")
    prof = active_profile(health)
    if prof:
        rep.check(
            prof.get("rerank_degraded") is False,
            "health 未报精排降级",
            f"reason={prof.get('rerank_degraded_reason')!r}",
        )


def gate_cleanup(rep: Report, vault: Path, marker: str, do_cleanup: bool, *, push: bool) -> None:
    print("\n[6/6] 收尾：清理验证件并恢复起始状态")
    if not do_cleanup:
        rep.warn("已跳过清理（--keep/--no-cleanup）", f"请人工删除含标记的行：{marker}")
        return
    inbox = vault / "inbox.md"
    lines = inbox.read_text(encoding="utf-8").splitlines(keepends=True)
    kept: list[str] = []
    i = 0
    removed = 0
    while i < len(lines):
        if marker in lines[i]:
            removed += 1
            i += 1
            while i < len(lines) and lines[i].lstrip().startswith("<!-- wb-"):
                i += 1
            continue
        kept.append(lines[i])
        i += 1
    if not removed:
        rep.fail("收尾：未能在 inbox.md 找到验证件行", marker)
        return
    inbox.write_text("".join(kept), encoding="utf-8")
    git(vault, "add", "inbox.md")
    committed = subprocess.run(
        ["git", "-C", str(vault), "commit", "-m", "chore: 清理跨端回归闸门验证件"],
        capture_output=True,
        text=True,
    )
    rep.check(
        committed.returncode == 0,
        "验证件清理已提交",
        (committed.stdout or committed.stderr).strip().splitlines()[-1:]
        and (committed.stdout or committed.stderr).strip().splitlines()[-1]
        or "",
    )
    dirty = worktree_dirty(vault)
    rep.check(not dirty, "收尾后工作树干净", "" if not dirty else str(dirty[:5]))
    if not push:
        rep.warn("清理提交未推送（--no-push-cleanup；vault 本地仍自洽）", "由使用者决定何时 push")
    else:
        pushed, push_detail = push_vault(vault)
        if pushed:
            rep.ok("清理提交已推送", push_detail)
        else:
            rep.warn("清理提交未推送（网络问题；vault 本地仍自洽）", push_detail)
    pending = sum(
        1 for ln in inbox.read_text(encoding="utf-8").splitlines() if ln.startswith("- [ ] ")
    )
    rep.ok("inbox 待处理条目", str(pending))


def gate_origin_guard(rep: Report, vault: Path, origin_before: str, *, push_enabled: bool) -> str:
    """记录 ``origin/main`` 前后取值；**未启用推送模式却变化**时醒目告警。

    这是 2026-09-19 事故的机器守卫：那次闸门"PASS"了，但端点在自己推送 vault。
    这里绝不静默——变化一定进告警清单，而最终 PASS 行会逐条列出告警。
    """
    origin_after = origin_main_rev(vault)
    print("\n[推送守卫] vault origin/main")
    print(f"  跑闸门前 : {origin_before}")
    print(f"  跑闸门后 : {origin_after}")
    if origin_after == origin_before:
        rep.ok("origin/main 未变化（本次验证没有推送到远端）", origin_after)
    elif push_enabled:
        rep.ok("origin/main 的变化可由闸门自己的收尾推送解释", f"{origin_before} → {origin_after}")
    else:
        rep.warn(
            "❗未启用推送模式，但 vault 的 origin/main 变了 —— 有别的写入者推送了 vault",
            f"{origin_before} → {origin_after}（很可能是 SWB 端点的自动推送）",
        )
    return origin_after


def main() -> int:
    ap = argparse.ArgumentParser(description="SWB × _vault × SK 跨端回归闸门")
    ap.add_argument("--vault", default=str(Path.home() / "Documents/Work/_vault"))
    ap.add_argument("--vector-work", default=str(Path.home() / ".summitknowledge/vector_work"))
    ap.add_argument("--question", default=DEFAULT_QUESTION)
    ap.add_argument("--keep", action="store_true", help="保留验证件（不清理）")
    ap.add_argument("--no-cleanup", action="store_true", help="同 --keep")
    ap.add_argument(
        "--no-push-cleanup",
        action="store_true",
        help="收尾提交只留本地，不推送 vault（默认仍推送；它只管收尾那一推，挡不住端点自动推送）",
    )
    ap.add_argument(
        "--no-push",
        action="store_true",
        help="[弃用] 同 --no-push-cleanup；旧名容易被误读为'整个闸门不推送'",
    )
    ap.add_argument(
        "--swb-url",
        default=None,
        help=(
            "SWB 端点（默认用 runtime.json 里正在跑的 App；验证请指向带 "
            "WB_NO_AUTO_PUSH=1 的源码服务）"
        ),
    )
    ap.add_argument(
        "--swb-token",
        default=None,
        help="配合 --swb-url 的会话令牌（或用环境变量 WB_SESSION_TOKEN）",
    )
    args = ap.parse_args()

    no_push_cleanup = bool(args.no_push_cleanup or args.no_push)
    if args.no_push and not args.no_push_cleanup:
        print(
            "ℹ --no-push 已弃用：改名为 --no-push-cleanup"
            "（它只管收尾那一推，挡不住端点自己的自动推送）"
        )

    vault = Path(args.vault).expanduser()
    vector_work = Path(args.vector_work).expanduser()
    home = Path.home()
    rep = Report()

    swb_url, swb_tok, swb_pid = swb_endpoint(home, url=args.swb_url, token=args.swb_token)
    swb_origin = swb_url
    sk_url, sk_tok, _ = sk_endpoint()
    auto_push_off = auto_push_state_of_pid(swb_pid)
    origin_before = origin_main_rev(vault)

    print("=" * 72)
    print("跨端回归闸门：SWB → _vault → SK")
    print(f"  vault      : {vault}")
    print(f"  SWB        : {swb_url}（pid {swb_pid or '未知'}）")
    print(f"  SK         : {sk_url}")
    print(f"  向量库      : {vector_work}")
    print(f"  收尾推送    : {'否（--no-push-cleanup）' if no_push_cleanup else '是（默认）'}")
    print(f"  origin/main : {origin_before}")
    print("-" * 72)
    if auto_push_off is True:
        print(
            f"  ✅ 自动推送  : 端点已启用 {AUTO_PUSH_DISABLE_ENV}=1（capture 只 commit，不推远端）"
        )
    elif auto_push_off is False:
        print(
            f"  ⚠️  自动推送  : 该端点【未】启用 {AUTO_PUSH_DISABLE_ENV}"
            " —— 本次 capture 会被自动 commit 并推送到 vault 远端！"
        )
        rep.warn(
            f"SWB 端点未启用 {AUTO_PUSH_DISABLE_ENV}：本次 capture 可能自动推送到 vault 远端",
            swb_url,
        )
    else:
        print(
            f"  ⚠️  自动推送  : 无法确认该端点是否启用 {AUTO_PUSH_DISABLE_ENV}"
            " —— 保守假设未启用，本次验证可能推送 vault！"
        )
        rep.warn(f"无法确认 SWB 端点是否启用 {AUTO_PUSH_DISABLE_ENV}：验证可能推送 vault", swb_url)
    print("=" * 72)

    try:
        pending_before = gate_preflight(rep, vault, swb_url, swb_tok, swb_origin, sk_url, sk_tok)
        marker = gate_mutation(rep, vault, swb_url, swb_tok, swb_origin, args.keep)
        gate_source_whitelist(rep, vault)
        gate_corpus(rep, vault, sk_url, sk_tok, vector_work, marker, pending_before)
        gate_retrieval(rep, sk_url, sk_tok, args.question)
        gate_cleanup(
            rep, vault, marker, not (args.keep or args.no_cleanup), push=not no_push_cleanup
        )
    finally:
        gate_origin_guard(rep, vault, origin_before, push_enabled=not no_push_cleanup)

    print("\n" + "=" * 72)
    if rep.failures:
        print(
            f"结果：\033[31mFAIL\033[0m —— {len(rep.failures)} 项失败"
            + (f"；另有 {len(rep.warnings)} 项告警" if rep.warnings else "")
        )
        for item in rep.failures:
            print(f"  ❌ {item}")
        for item in rep.warnings:
            print(f"  ⚠️  {item}")
        print("=" * 72)
        return 1
    if rep.warnings:
        # 告警逐条列出：绝不让"验证推了 vault"这类事故藏在裸 PASS 后面。
        print(f"结果：\033[32mPASS\033[0m（{len(rep.warnings)} 项告警，逐条如下）")
        for item in rep.warnings:
            print(f"  ⚠️  {item}")
    else:
        print("结果：\033[32mPASS\033[0m")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
