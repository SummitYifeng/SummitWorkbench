"""追加型 JSONL 日志的容错读（韧性加固 LHF #2 / P0-06 隔离去重）。

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
- **隔离去重（P0-06）**：坏行带**稳定 id**（``sha256(source + 行号 + 完整 raw)``）
  抄进旁挂的 ``<log>.quarantine``，原日志不改动（非破坏性——不重写、不删除历史）；
  同一坏行被反复读取（如每次 ``wb status`` 刷新）只写入**一条**隔离记录，隔离文件
  不会无限膨胀；记录含截断后的 raw、原因、首次发现时间与稳定 id。
- 模型用 ``extra="ignore"`` 容忍 schema 漂移：日后新增字段的旧读者不会因未知键报错。

设计成上游无关：调用方给「日志路径 + 行模型」，拿回一列已校验的模型实例。
"""

from __future__ import annotations

import hashlib
import json
import warnings
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ValidationError

_QUARANTINE_SUFFIX = ".quarantine"
_RAW_CAP = 2_000  # 隔离记录 raw 上限：防止坏行把诊断文件撑爆
_REASON_CAP = 500  # 隔离记录 reason 上限
_TRUNCATION_MARKER = "…[截断]"


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


def quarantine_id(source: str, lineno: int, raw: str) -> str:
    """坏行隔离记录的稳定 id：``sha256(source + line-number + raw-line)``（P0-06）。

    :param source: 源日志的稳定相对标识（默认是日志文件名；多机同步下保持稳定）。
    :param lineno: 坏行在源日志中的 1-based 行号。
    :param raw: 坏行**完整**原文（未截断），保证同一坏行反复读取得到同一 id。
    :returns: 64 位小写十六进制 sha256 摘要。

    同一次序（source、行号、原文）在任意机器/任意时间都产出同一 id，使同一坏行
    无论被读多少次、在哪台设备读，都只产生一条隔离记录。
    """
    return hashlib.sha256(f"{source}{lineno}{raw}".encode()).hexdigest()


@dataclass(frozen=True)
class _BadLine:
    source: str
    lineno: int
    raw: str
    reason: str

    @property
    def id(self) -> str:
        return quarantine_id(self.source, self.lineno, self.raw)


def _truncate(text: str, cap: int) -> str:
    """超过 ``cap`` 时截断并加可见标记；截断不改变用于 id 的完整原文。"""
    if len(text) <= cap:
        return text
    keep = cap - len(_TRUNCATION_MARKER)
    if keep <= 0:
        return text[:cap]
    return text[:keep] + _TRUNCATION_MARKER


def _existing_quarantine_ids(sidecar: Path) -> set[str]:
    """读回旁挂文件里已有的稳定 id（容忍旧版注释行与损坏行，尽力而为）。

    隔离文件是诊断数据：读取失败绝不让业务读日志崩溃，按「没有已有记录」处理即可。
    """
    if not sidecar.is_file():
        return set()
    try:
        lines = sidecar.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return set()
    ids: set[str] = set()
    for line in lines:
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue  # 旧版注释格式 / 损坏行：跳过
        if isinstance(record, dict) and isinstance(record.get("id"), str):
            ids.add(record["id"])
    return ids


def _quarantine(log: Path, bad_lines: list[_BadLine]) -> None:
    """把尚未隔离过的坏行追加到旁挂的 ``<log>.quarantine``，原日志不动（非破坏性）。

    以稳定 id 去重：同一坏行重复读取只写一条；记录保存截断后的 raw、原因、
    首次发现时间（本条真正落盘的时刻）与稳定 id，供事后排查与跨设备去重。
    """
    if not bad_lines:
        return
    sidecar = log.with_name(log.name + _QUARANTINE_SUFFIX)
    existing = _existing_quarantine_ids(sidecar)
    fresh = [bad for bad in bad_lines if bad.id not in existing]
    if not fresh:
        return
    first_seen = datetime.now(UTC).isoformat()
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    with sidecar.open("a", encoding="utf-8") as fh:
        for bad in fresh:
            record = {
                "id": bad.id,
                "source": bad.source,
                "line": bad.lineno,
                "reason": _truncate(bad.reason, _REASON_CAP),
                "first_seen": first_seen,
                "raw": _truncate(bad.raw, _RAW_CAP),
            }
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _reason_of(exc: ValidationError) -> str:
    """坏行原因：错误类型 + 首个校验错误类型/信息，供事后定位。"""
    detail = ""
    try:
        errors = exc.errors()
        if errors:
            first = errors[0]
            err_type = first.get("type")
            loc = ".".join(str(part) for part in first.get("loc", ()))
            detail = f" type={err_type}" + (f" loc={loc}" if loc else "")
    except Exception:  # noqa: BLE001 - 原因只用于诊断，绝不因格式化异常影响读日志
        detail = ""
    return f"{type(exc).__name__}{detail}"


def read_models[ModelT: BaseModel](
    log: Path,
    model: type[ModelT],
    *,
    quarantine: bool = True,
    source: str | None = None,
) -> list[ModelT]:
    """容错读整本 JSONL：逐行校验成 ``model``，坏行跳过 + 告警 +（可选）隔离。

    :param log: 日志文件路径；不存在时返回空列表（尚未写过是正常态）。
    :param model: 每行对应的 Pydantic 模型（建议 ``extra="ignore"``）。
    :param quarantine: 是否把坏行抄进 ``<log>.quarantine``；关掉则只告警不落盘。
    :param source: 坏行隔离记录的源标识（默认取 ``log.name``）；需要 vault 相对路径等
        更可读/更稳定的标识时由调用方显式传入，同一逻辑日志需保持稳定。
    :returns: 顺序保留的、已校验的模型实例；坏行被剔除。

    只读——绝不改写原日志（NFR-3 非破坏性）。空行忽略。同一坏行重复读取只隔离一次。
    """
    if not log.is_file():
        return []
    source_id = source if source is not None else log.name
    rows: list[ModelT] = []
    bad_lines: list[_BadLine] = []
    for lineno, line in enumerate(log.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(model.model_validate_json(line))
        except ValidationError as exc:
            bad_lines.append(
                _BadLine(
                    source=source_id,
                    lineno=lineno,
                    raw=line,
                    reason=_reason_of(exc),
                )
            )
            warnings.warn(
                f"{log.name}:{lineno} 跳过损坏日志行（已隔离）",
                CorruptLogLine,
                stacklevel=2,
            )
    if bad_lines and quarantine:
        _quarantine(log, bad_lines)
    return rows
