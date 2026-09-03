"""P2：线程信号进入晨间简报采集（下一步/阻塞/未闭环跟进 → 需要行动候选）。"""

from __future__ import annotations

from pathlib import Path

from summit_workbench.domain.brief import ActionCategory
from summit_workbench.workflows.brief.collect import collect_signals


def _archive(
    vault: Path,
    project: str,
    *,
    status: str = "active",
    next_step: str = "",
    blocked: str = "无",
    followup: str = "",
) -> None:
    path = vault / "projects" / f"{project}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    step = f"- {next_step}" if next_step else ""
    path.write_text(
        f"---\nproject: {project}\ndate: 2026-09-01\ntype: project-main\nstatus: {status}\n"
        f"---\n\n# {project}\n\n## 当前状态\n\n## 下一步\n{step}\n\n## 阻塞\n{blocked}\n\n"
        f"## 决策记录\n\n## 跟进事项\n{followup}\n",
        encoding="utf-8",
    )


def test_thread_signals_enter_brief_candidates(tmp_path: Path) -> None:
    work = tmp_path / "Work"
    vault = work / "_vault"
    # 知识线程：只有档案，没有文件夹
    _archive(
        vault,
        "FinanceOps",
        next_step="月底前出 Coach V1.1",
        blocked="等金老师回复税务口径",
        followup="- [ ] 木子月底前完成 Coach 梳理\n- [ ] 冯老师确认收费规则",
    )
    # 归档线程：不进候选
    _archive(vault, "DoneOps", status="archived", next_step="历史步骤", followup="- [ ] 旧跟进")
    # 未建档文件夹（新）：不进内容信号
    (work / "BrandNew").mkdir(parents=True)

    collected = collect_signals(work, vault, timezone="Asia/Shanghai", facts_source=None)
    by_id = {sig.signal_id: sig for sig in collected.candidates}

    # 线程「下一步」→ 主线推进（与仓库项目同机制）
    assert by_id["next-FinanceOps"].category is ActionCategory.MAIN_PUSH
    assert by_id["next-FinanceOps"].project == "FinanceOps"
    # 阻塞 → 防止停摆
    assert by_id["block-FinanceOps"].category is ActionCategory.ANTI_STALL
    assert "等金老师回复税务口径" in by_id["block-FinanceOps"].title
    # 未闭环跟进 → 主线推进（聚合为一条，detail 带总数）
    assert by_id["follow-FinanceOps"].category is ActionCategory.MAIN_PUSH
    assert "跟进 FinanceOps" in by_id["follow-FinanceOps"].title
    assert by_id["follow-FinanceOps"].detail == "共 2 条待闭环跟进"
    # 归档线程与新文件夹不产生信号
    assert "next-DoneOps" not in by_id
    assert "block-DoneOps" not in by_id
    assert "next-BrandNew" not in by_id


def test_no_noise_when_blocks_empty(tmp_path: Path) -> None:
    work = tmp_path / "Work"
    vault = work / "_vault"
    _archive(vault, "Quiet", blocked="无")  # 无下一步、无跟进、阻塞=无
    collected = collect_signals(work, vault, timezone="Asia/Shanghai", facts_source=None)
    ids = [sig.signal_id for sig in collected.candidates]
    assert "block-Quiet" not in ids
    assert "follow-Quiet" not in ids
    assert "next-Quiet" not in ids
