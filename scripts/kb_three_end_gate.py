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

用法（**会写 vault、会花钱**：一次极小模型调用 + 检索时的嵌入/精排费用）：

    ./.venv/bin/python scripts/kb_three_end_gate.py            # 跑完整闸门并自动清理验证件
    ./.venv/bin/python scripts/kb_three_end_gate.py --keep     # 保留验证件供人工查看
    ./.venv/bin/python scripts/kb_three_end_gate.py --no-cleanup

退出码：0 = 全部通过（允许 WARN）；1 = 有 FAIL。
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, cast

MARKER_PREFIX = "【回归闸门验证件】"
DEFAULT_QUESTION = "奖学金折扣要不要收 royalty？"


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
    out = subprocess.run(["ps", "eww", "-p", pid], capture_output=True, text=True).stdout
    for token in out.split():
        if token.startswith(f"{name}="):
            return token.split("=", 1)[1]
    return ""


def swb_endpoint(home: Path) -> tuple[str, str]:
    runtime = home / "Library/Application Support/SummitWorkbench/runtime.json"
    if not runtime.is_file():
        raise SystemExit("✗ 未找到 SWB runtime.json：SummitWorkbench 是否在运行？")
    data = json.loads(runtime.read_text(encoding="utf-8"))
    token = _env_of(str(data["pid"]), "WB_SESSION_TOKEN")
    if not token:
        raise SystemExit("✗ 无法从 SWB 进程环境读取 WB_SESSION_TOKEN")
    return f"http://127.0.0.1:{data['port']}", token


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


# ────────────────────── 闸门各段 ──────────────────────
def gate_preflight(
    rep: Report, vault: Path, swb_url: str, swb_tok: str, swb_origin: str, sk_url: str, sk_tok: str
) -> int:
    """返回起始 pending_index，供 [3/5] 判断"闸门自己的写入有没有让索引变脏"。"""
    print("\n[1/5] 前置：三端可用 + 起始状态干净")
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
    print("\n[2/5] 写入路径：真实 capture 之后工作树是否干净、`_signals` 是否被回跟踪")
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


def gate_corpus(
    rep: Report,
    vault: Path,
    sk_url: str,
    sk_tok: str,
    vector_work: Path,
    marker: str,
    pending_before: int,
) -> None:
    """P1-4：原始逐字稿与 inbox 都不该进语料。"""
    print("\n[3/5] 语料边界：逐字稿与 inbox 都不得进检索语料")
    db = active_db(vector_work)
    # WAL 库用 mode=ro 打开会因缺 -shm 失败（实测），普通连接做 SELECT 是安全的
    con = sqlite3.connect(db, timeout=10)
    try:
        tr = con.execute(
            "SELECT COUNT(*) FROM chunks WHERE source_file LIKE 'meetings/transcripts/%'"
        ).fetchone()[0]
        inbox = con.execute(
            "SELECT COUNT(*) FROM chunks WHERE source_file = 'inbox.md'"
        ).fetchone()[0]
        hit = con.execute(
            "SELECT COUNT(*) FROM chunks WHERE content LIKE ?", (f"%{marker}%",)
        ).fetchone()[0]
    finally:
        con.close()
    rep.check(tr == 0, "语料中无 `meetings/transcripts/*`（逐字稿已排除）", f"命中 {tr}")
    rep.check(inbox == 0, "语料中无 `inbox.md`", f"命中 {inbox}")
    rep.check(hit == 0, "本次 capture 未进语料（inbox 类型被排除）", f"命中 {hit}")

    health = http_json(f"{sk_url}/api/health", token=sk_tok, header="Authorization")
    prof = active_profile(health)
    if prof:
        pending_after = int(prof.get("pending_index") or 0)
        # 真正要守的是「闸门自己的写入（inbox capture）不得让索引变脏」；
        # 起始就 >0 只是"索引落后于库"（新的一天简报 / 别人刚 capture / 审批写回），
        # 与闸门要守的四类不变量无关，所以只告警不判失败。
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
    """P0-4 + 语料边界：精排必须真的生效，且结果里不得出现逐字稿。"""
    print("\n[4/5] 检索路径：精排是否真的生效、结果是否混入逐字稿")
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
    rep.check("meeting-transcript" not in types, "结果中无 meeting-transcript", f"types={types}")
    health = http_json(f"{sk_url}/api/health", token=sk_tok, header="Authorization")
    prof = active_profile(health)
    if prof:
        rep.check(
            prof.get("rerank_degraded") is False,
            "health 未报精排降级",
            f"reason={prof.get('rerank_degraded_reason')!r}",
        )


def gate_cleanup(rep: Report, vault: Path, marker: str, do_cleanup: bool) -> None:
    print("\n[5/5] 收尾：清理验证件并恢复起始状态")
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
    pushed, push_detail = push_vault(vault)
    if pushed:
        rep.ok("清理提交已推送", push_detail)
    else:
        rep.warn("清理提交未推送（网络问题；vault 本地仍自洽）", push_detail)
    pending = sum(
        1 for ln in inbox.read_text(encoding="utf-8").splitlines() if ln.startswith("- [ ] ")
    )
    rep.ok("inbox 待处理条目", str(pending))


def main() -> int:
    ap = argparse.ArgumentParser(description="SWB × _vault × SK 跨端回归闸门")
    ap.add_argument("--vault", default=str(Path.home() / "Documents/Work/_vault"))
    ap.add_argument("--vector-work", default=str(Path.home() / ".summitknowledge/vector_work"))
    ap.add_argument("--question", default=DEFAULT_QUESTION)
    ap.add_argument("--keep", action="store_true", help="保留验证件（不清理）")
    ap.add_argument("--no-cleanup", action="store_true", help="同 --keep")
    args = ap.parse_args()

    vault = Path(args.vault).expanduser()
    vector_work = Path(args.vector_work).expanduser()
    home = Path.home()
    rep = Report()

    swb_url, swb_tok = swb_endpoint(home)
    swb_origin = swb_url
    sk_url, sk_tok, _ = sk_endpoint()

    print("=" * 72)
    print("跨端回归闸门：SWB → _vault → SK")
    print(f"  vault      : {vault}")
    print(f"  SWB        : {swb_url}")
    print(f"  SK         : {sk_url}")
    print(f"  向量库      : {vector_work}")
    print("=" * 72)

    pending_before = gate_preflight(rep, vault, swb_url, swb_tok, swb_origin, sk_url, sk_tok)
    marker = gate_mutation(rep, vault, swb_url, swb_tok, swb_origin, args.keep)
    gate_corpus(rep, vault, sk_url, sk_tok, vector_work, marker, pending_before)
    gate_retrieval(rep, sk_url, sk_tok, args.question)
    gate_cleanup(rep, vault, marker, not (args.keep or args.no_cleanup))

    print("\n" + "=" * 72)
    if rep.failures:
        print(
            f"结果：\033[31mFAIL\033[0m —— {len(rep.failures)} 项失败"
            + (f"；另有 {len(rep.warnings)} 项告警" if rep.warnings else "")
        )
        for item in rep.failures:
            print(f"  ❌ {item}")
        print("=" * 72)
        return 1
    print(
        "结果：\033[32mPASS\033[0m"
        + (f"（{len(rep.warnings)} 项告警，见上）" if rep.warnings else "")
    )
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
