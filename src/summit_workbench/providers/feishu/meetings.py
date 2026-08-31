"""会议逐字稿来源：飞书 Note 主链路 + 本地文件兜底（PRD L14）。

M0-4 交付：
- ``verify_identity`` 用稳定的 user_info 接口证明 user_access_token 与最小 scope 生效
  （可重复、可审计的鉴权冒烟）。
- ``import_local_transcript`` 是本地投递兜底，完全可用，不依赖任何飞书接口。
- ``FeishuNoteSource`` 是主链路骨架：端点与响应结构因租户/纪要类型而异，
  按 PRD L14 需在 M0-10 用真实历史会议实测后固定（见 ADR 0004）。此处不臆造端点，
  未固定前调用会抛出显式错误并指向本地兜底，绝不返回伪造结果。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from summit_workbench.providers.feishu.client import FeishuClient
from summit_workbench.providers.feishu.errors import FeishuAPIError, FeishuError

# 稳定：证明 user_access_token 可用。
USER_INFO_PATH = "/open-apis/authen/v1/user_info"


@dataclass(frozen=True)
class TranscriptResult:
    """一份取得的逐字稿。``source`` 标明来源，便于审计与降级判断。"""

    source: str  # "feishu-note" | "local-file"
    meeting_id: str
    text: str
    note_id: str | None = None
    origin_path: str | None = None


def verify_identity(client: FeishuClient) -> dict[str, Any]:
    """调用 user_info 证明当前 access_token 有效。返回用户档案（name/open_id 等）。

    这是 M0-4 的鉴权冒烟：成功即证明授权链路与 token 刷新可用；失败抛显式错误。
    """
    return client.get(USER_INFO_PATH)


def import_local_transcript(source_path: Path, meeting_id: str) -> TranscriptResult:
    """本地兜底：从本地文件读入一份逐字稿（Note API 不可用时使用）。

    只读入文本，不做结构化；结构化交给 M1 的模型链路。文件不存在即显式报错。
    """
    if not source_path.is_file():
        raise FeishuError(f"本地逐字稿文件不存在：{source_path}")
    text = source_path.read_text(encoding="utf-8")
    if not text.strip():
        raise FeishuError(f"本地逐字稿文件为空：{source_path}")
    return TranscriptResult(
        source="local-file",
        meeting_id=meeting_id,
        text=text,
        origin_path=str(source_path),
    )


class FeishuNoteSource:
    """飞书会议纪要主链路（骨架）。

    定位已结束会议 → 取 note_id → 读智能纪要 / 逐字稿。普通纪要经 verbatim_doc_token
    对应文档读取，统一纪要经 Note transcript 接口读取（PRD L14）。这些端点与响应结构
    需在 M0-10 用本人租户真实会议实测后固定。
    """

    def __init__(self, client: FeishuClient) -> None:
        self.client = client

    def fetch_transcript(self, meeting_id: str) -> TranscriptResult:
        raise FeishuAPIError(
            "飞书会议纪要读取端点尚未固定：需 M0-10 用真实历史会议实测确认后实现；"
            "在此之前请用 wb feishu import-local 走本地兜底"
        )
