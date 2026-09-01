"""追加型 JSONL 日志的容错读（韧性加固 LHF #2）。

**根治的故障类**：``meeting_state`` / ``usage_ledger`` 是 append-only JSONL——每次
状态变迁或用量调用追加一行。追加写本身不是原子的：进程被 kill、磁盘写满、断电，都
可能留下一条 **半截行**（末行未闭合的 JSON）。此前两个仓库都用裸 ``json.loads(line)``
逐行读，任何一条坏行都会抛 ``JSONDecodeError`` 让 **整本** 日志读取崩溃——一条截断的
末行足以让 ``wb status`` / 防重查询 / 月度费用汇总全部失效，且越老的历史越无辜受累。
``meeting_state._task_from_row`` 还用 ``row["…"]`` 硬索引，缺键即 ``KeyError``。

对策：一处通用容错读，两个仓库共用。逐行 :meth:`~pydantic.BaseModel.model_validate_json`
成显式 schema 的 Pydantic 模型——

- **坏行跳过**，不再让整本崩溃（把「全损」降为「丢那一行」）；
- **告警可见**（``warnings.warn``，NFR-6：失败必须可见，不静默吞错）；
- **隔离**：把坏行原样抄进旁挂的 ``<log>.quarantine`` 供事后排查，原日志不改动
  （非破坏性——不重写、不删除历史）；
- 模型用 ``extra="ignore"`` 容忍 schema 漂移：日后新增字段的旧读者不会因未知键报错。

设计成上游无关：调用方给「日志路径 + 行模型」，拿回一列已校验的模型实例。
"""

from __future__ import annotations

import json
import warnings
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ValidationError

_QUARANTINE_SUFFIX = ".quarantine"


def append_row(log: Path, row: Mapping[str, object]) -> Path:
    """把一行记录追加到 JSONL 日志（父目录按需创建），返回日志路径。

    两个 append-only 仓库（``meeting_state`` / ``usage_ledger``）共用同一写法：
    ``ensure_ascii=False`` 保留中文可读，一行一条便于逐行容错读（见 :func:`read_models`）。
    """
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(dict(row), ensure_ascii=False) + "\n")
    return log


class CorruptLogLine(UserWarning):
    """JSONL 日志中一条无法解析/校验的行（已跳过并隔离）。"""


def _quarantine(log: Path, bad_lines: list[tuple[int, str]]) -> None:
    """把坏行原样追加到旁挂的 ``<log>.quarantine``，原日志不动（非破坏性）。"""
    sidecar = log.with_name(log.name + _QUARANTINE_SUFFIX)
    stamp = datetime.now(UTC).isoformat()
    with sidecar.open("a", encoding="utf-8") as fh:
        for lineno, raw in bad_lines:
            fh.write(f"# {stamp} {log.name}:{lineno}\n{raw}\n")


def read_models[ModelT: BaseModel](
    log: Path,
    model: type[ModelT],
    *,
    quarantine: bool = True,
) -> list[ModelT]:
    """容错读整本 JSONL：逐行校验成 ``model``，坏行跳过 + 告警 +（可选）隔离。

    :param log: 日志文件路径；不存在时返回空列表（尚未写过是正常态）。
    :param model: 每行对应的 Pydantic 模型（建议 ``extra="ignore"``）。
    :param quarantine: 是否把坏行抄进 ``<log>.quarantine``；关掉则只告警不落盘。
    :returns: 顺序保留的、已校验的模型实例；坏行被剔除。

    只读——绝不改写原日志（NFR-3 非破坏性）。空行忽略。
    """
    if not log.is_file():
        return []
    rows: list[ModelT] = []
    bad_lines: list[tuple[int, str]] = []
    for lineno, line in enumerate(log.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(model.model_validate_json(line))
        except ValidationError:
            bad_lines.append((lineno, line))
            warnings.warn(
                f"{log.name}:{lineno} 跳过损坏日志行（已隔离）",
                CorruptLogLine,
                stacklevel=2,
            )
    if bad_lines and quarantine:
        _quarantine(log, bad_lines)
    return rows
