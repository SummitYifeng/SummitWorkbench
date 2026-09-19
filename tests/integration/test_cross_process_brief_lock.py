"""P0-6 跨进程互斥验证（真实子进程 + 同一把 .wb.lock）。

launchd brief（08:00）与面板「生成简报」会走同一 run_brief 写路径：两者都经
daily_note.write_brief / signal_snapshot.write_snapshot 写同一批文件。P0-1 的 repository 级
锁让两个进程在 .wb.lock 上自动互斥——本测试同时起两个进程各循环 write_brief + write_snapshot，
断言最终文件完整、无交错（原子写 + 锁，任一时刻只有一方落盘）。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from summit_workbench.repositories.daily_note import BRIEF_END, BRIEF_START, daily_note_path

_SRC = str(Path(__file__).resolve().parents[2] / "src")

_CHILD = """
import sys
from pathlib import Path
from summit_workbench.repositories.daily_note import write_brief
from summit_workbench.repositories.signal_snapshot import write_snapshot
vault, day, tag = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
for i in range(25):
    write_brief(vault, day, f'payload-{tag}-{i} 完整正文\\n第二行内容完整')
    write_snapshot(vault, day, {'date': day, 'tag': tag, 'i': i})
"""


def test_two_processes_write_brief_and_snapshot_without_interleaving(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    day = "2026-09-03"
    env = dict(os.environ, PYTHONPATH=_SRC)
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", _CHILD, str(vault), day, tag],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for tag in ("P1", "P2")
    ]
    for proc in procs:
        _stdout, stderr = proc.communicate(timeout=90)
        assert proc.returncode == 0, stderr.decode("utf-8", errors="replace")

    # 当日简报：锚点只出现一对（任一写者的完整区块，无交错半截）。
    # 简报写在本机程序目录（不在 vault 内）；两个子进程继承同一 HOME，落点一致。
    note = daily_note_path(vault, day)
    text = note.read_text(encoding="utf-8")
    assert text.count(BRIEF_START) == 1
    assert text.count(BRIEF_END) == 1
    assert "payload-P1-24" in text or "payload-P2-24" in text
    # 快照：完整 JSON、顶层带 schema_version（任一写者的完整落盘）
    snapshot_path = vault / "_signals" / f"{day}.json"
    loaded = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert loaded.get("schema_version") == 1
    assert loaded.get("tag") in ("P1", "P2")
    assert loaded.get("i") == 24
