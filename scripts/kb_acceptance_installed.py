#!/usr/bin/env python3
"""对**已安装的 App** 做端到端验收（真机口径）。

与 `kb_acceptance.py` 的分工：

- `kb_acceptance.py` 用仓库源码直接跑检索与问答（开发/CI 口径）；
- 本脚本通过**已安装 App 自己的本地服务**发问——也就是「第二大脑」面板调用的同一个路由
  `POST /api/ask`——因此验的是「装到 /Applications 之后到底还能不能用」。

为什么不做 GUI 自动化：面板是受管 WKWebView，脚本无法可靠地驱动它；但面板本身不实现问答逻辑，
它只是把 `/api/ask` 的返回渲染成 HTML。所以打通这条路由，并核对返回的 `路径#区块` 引用
**能解析、能追到证据层**，就等价于「面板里问得出、点得开」。脚本同时把面板会渲染的那段 HTML
（含「检索轨迹」折叠块）原样落盘，便于人工比对。

会话令牌由 App 自己持有（原生启动器把 `WB_SESSION_TOKEN` 注入 bundle server），本脚本从
server 进程环境里读取，**绝不打印、绝不写进任何输出文件**。

用法：

    scripts/kb_acceptance_installed.py                     # 两题对外验收口径（真调模型）
    scripts/kb_acceptance_installed.py --all               # 清单全部题目
    scripts/kb_acceptance_installed.py --out FILE          # 落盘报告
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import kb_acceptance as acceptance  # noqa: E402  (同一目录的验收清单与判据)

from summit_workbench.repositories.kb_index import KnowledgeIndex  # noqa: E402

SERVER_PROCESS = "SummitWorkbench.app/Contents/Resources/server/SummitWorkbenchServer"
ROUTE_RE = re.compile(r"路由：<code>([a-z]+)</code>")


@dataclass(frozen=True)
class Endpoint:
    port: int
    token: str
    frontend_build: str
    record: Path


def runtime_records(app_support: Path) -> list[Path]:
    """runtime record 的合法落点（与 native/.../RuntimeRecord.swift 的 candidateURLs 同口径）。"""
    root = app_support / "runtime.json"
    found = [root] if root.is_file() else []
    profiles = app_support / "profiles"
    if profiles.is_dir():
        found.extend(sorted(profiles.rglob("runtime.json")))
    return found


def _live_server_pid() -> str | None:
    result = subprocess.run(["pgrep", "-f", SERVER_PROCESS], capture_output=True, text=True)
    pids = result.stdout.split()
    return pids[0] if pids else None


def _session_token() -> str | None:
    """从 server 进程环境里取 App 注入的会话令牌（只读，不打印）。"""
    import os

    injected = os.environ.get("WB_SESSION_TOKEN")
    if injected:
        return injected
    pid = _live_server_pid()
    if pid is None:
        return None
    # macOS 上 `ps eww` 会打印目标进程的环境（仅限同用户进程）。
    environment = subprocess.run(["ps", "eww", "-p", pid], capture_output=True, text=True).stdout
    match = re.search(r"WB_SESSION_TOKEN=(\S+)", environment)
    return match.group(1) if match else None


def discover(app_support: Path) -> Endpoint:
    """找到正在运行的已安装 App 的本地服务端点。"""
    records = runtime_records(app_support)
    if not records:
        raise SystemExit(f"✗ 没找到 runtime record（App 没在运行？）：{app_support}")
    record = json.loads(records[0].read_text(encoding="utf-8"))
    token = _session_token()
    if not token:
        raise SystemExit("✗ 读不到会话令牌：请确认 SummitWorkbench 正在运行")
    return Endpoint(
        port=int(record["port"]),
        token=token,
        frontend_build=str(record.get("frontend_build", "")),
        record=records[0],
    )


def _post(endpoint: Endpoint, path: str, payload: dict[str, object]) -> dict[str, object]:
    request = urllib.request.Request(
        f"http://127.0.0.1:{endpoint.port}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "X-WB-Session-Token": endpoint.token,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:  # 503 ask_unavailable 等
        return {"ok": False, "http_status": exc.code, "body": exc.read().decode("utf-8", "replace")}


def _get(endpoint: Endpoint, path: str) -> dict[str, object]:
    request = urllib.request.Request(
        f"http://127.0.0.1:{endpoint.port}{path}",
        headers={"X-WB-Session-Token": endpoint.token},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def _route_of(html: str) -> str:
    match = ROUTE_RE.search(html)
    return match.group(1) if match else ""


def _facts(answer: dict[str, object] | None) -> list[dict[str, object]]:
    if not isinstance(answer, dict):
        return []
    facts = answer.get("facts")
    return [fact for fact in facts if isinstance(fact, dict)] if isinstance(facts, list) else []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="已安装 App 的第二大脑端到端验收")
    parser.add_argument(
        "--all", action="store_true", help="跑清单全部题目（默认只跑两题模型口径）。"
    )
    parser.add_argument(
        "--app-support",
        type=Path,
        default=Path.home() / "Library/Application Support/SummitWorkbench",
    )
    parser.add_argument(
        "--out", type=Path, default=None, help="报告落盘路径（默认打印到 stdout）。"
    )
    args = parser.parse_args(argv)

    endpoint = discover(args.app_support)
    version = _get(endpoint, "/api/version")
    cases = list(acceptance.CASES) if args.all else [c for c in acceptance.CASES if c.use_model]

    lines: list[str] = []
    failures: list[str] = []

    def emit(text: str = "") -> None:
        lines.append(text)
        print(text)

    emit("SummitWorkbench · 已安装 App 的第二大脑验收")
    emit(f"runtime record：{endpoint.record}")
    emit(f"frontend_build：{endpoint.frontend_build}")
    emit(f"/api/version：{json.dumps(version, ensure_ascii=False, sort_keys=True)}")
    emit(f"题目数：{len(cases)}（{'全部' if args.all else '两题模型口径'}）")
    emit("")

    vault_dir = Path(str(version.get("vault_dir") or "")) if version.get("vault_dir") else None
    if vault_dir is None or not vault_dir.is_dir():
        # /api/version 未必暴露 vault；退回本机 active workspace
        try:
            from summit_workbench.config.profiles import resolve_active_workspace

            active = resolve_active_workspace()
            vault_dir = active.paths.vault_dir if active.paths else None
        except Exception:  # noqa: BLE001
            vault_dir = None
    if vault_dir is None or not vault_dir.is_dir():
        raise SystemExit("✗ 无法确定 vault 目录，无法核对引用锚点")

    index_db = args.app_support / "kb-index.sqlite"
    with KnowledgeIndex(vault_dir, index_db) as index:
        index.build()
        for case in cases:
            emit("=" * 78)
            emit(f"【{case.name}】")
            emit(f"问：{case.question}")
            emit("-" * 78)
            payload = _post(endpoint, "/api/ask", {"question": case.question})
            if not payload.get("ok"):
                failures.append(f"{case.name}：/api/ask 未成功返回（{payload}）")
                emit(f"✗ /api/ask 失败：{payload}")
                emit("")
                continue

            html = str(payload.get("answer_html", ""))
            answer = payload.get("answer")
            answer_dict = answer if isinstance(answer, dict) else None
            facts = _facts(answer_dict)
            cited = [str(item) for item in (payload.get("cited_source_ids") or [])]
            source_ids = [str(item) for item in (payload.get("source_ids") or [])]
            cited = cited or [str(fact.get("source_id", "")) for fact in facts]

            if answer_dict is not None:
                emit(f"回答：{answer_dict.get('summary', '')}")
                for fact in facts:
                    emit(f"  • {fact.get('text', '')}")
                    emit(f"      ← {fact.get('source_id', '')}")
                for conflict in answer_dict.get("conflicts") or []:
                    emit(f"  ▸ 冲突：{conflict.get('topic', '')}")

            observation = acceptance.Observation(
                route=_route_of(html),
                anchors=tuple(cited),
                fused=tuple(source_ids),
            )
            case_failures = acceptance.audit_case(case, observation, index)
            chains, transcripts = acceptance.evidence_chains(index, tuple(cited))
            emit("")
            emit(f"检索轨迹里的路由：{observation.route or '（未渲染）'}")
            emit(f"进入上下文的来源：{len(source_ids)} 条")
            emit(f"事实引用：{len(cited)} 条，其中块级 {sum('#' in a for a in cited)} 条")
            emit(f"追溯到证据层：{chains[0] if chains else '（未走出）'}（共 {len(chains)} 条）")
            emit(f"其中走到逐字稿：{transcripts[0] if transcripts else '（无）'}")
            if case.expect_transcript:
                emit("本题要求走到逐字稿：是")
            if case_failures:
                emit("✗ 判定失败：")
                for item in case_failures:
                    emit(f"    - {item}")
                failures.extend(case_failures)
            else:
                emit("✓ 通过：关键证据已召回、引用为块级且可解析、能追到证据层")
            emit("")
            emit("—— 面板会渲染的 HTML（含检索轨迹折叠块）——")
            emit(html)
            emit("")

    emit("=" * 78)
    if failures:
        emit(f"✗ 已安装 App 验收未通过，{len(failures)} 项：")
        for item in failures:
            emit(f"  - {item}")
    else:
        emit(f"✓ 已安装 App 验收通过：{len(cases)} 题全部合格。")

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"\n报告已写入：{args.out}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
