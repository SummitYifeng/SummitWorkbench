"""会议逐字稿来源：飞书 Note 主链路 + 本地文件兜底（PRD L14）。

- ``verify_identity``：稳定的 user_info 鉴权冒烟（M0-4）。
- ``import_local_transcript``：本地投递兜底，不依赖任何飞书接口。
- 会议发现（``list_meetings_by_no`` + ``get_meeting_detail``）：会议号 → 会议 → note_id。
- ``FeishuNoteSource``：note_id → ``vc/v1/notes/{note_id}`` 取产物 → 选逐字稿文档
  （artifact_type=2）的 doc_token → ``docx/v1/documents/{doc_token}/raw_content`` 读正文。

会议纪要/文档读取用 tenant_access_token（应用身份），所需 scope 在开放平台按应用授予：
``vc:note:read`` + ``docx:document:readonly`` + vc 会议只读。端点均对官方文档核实并真机验证。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from summit_workbench.providers.feishu.client import FeishuClient
from summit_workbench.providers.feishu.errors import FeishuError

# 稳定：证明 user_access_token 可用。
USER_INFO_PATH = "/open-apis/authen/v1/user_info"

# 会议纪要产物类型（官方文档）。
ARTIFACT_MINUTES = 1  # 智能纪要文档
ARTIFACT_TRANSCRIPT = 2  # 逐字稿文档

# 按会议号 + 时间范围列会议（返回 meeting_briefs：id/topic/meeting_no，不含 note_id）。
LIST_BY_NO_PATH = "/open-apis/vc/v1/meetings/list_by_no"
# 会议详情（返回体含 note_id / start_time / status 等）。
MEETING_GET_PATH = "/open-apis/vc/v1/meetings/{meeting_id}"


@dataclass(frozen=True)
class MeetingSummary:
    """一场会议的摘要（list_by_no + 会议详情）。``note_id`` 为空表示该会议没有纪要。"""

    meeting_id: str
    meeting_no: str
    topic: str
    note_id: str | None
    start_time: str | None


@dataclass(frozen=True)
class TranscriptResult:
    """一份取得的逐字稿。``source`` 标明来源，便于审计与降级判断。"""

    source: str  # "feishu-note" | "local-file"
    text: str
    meeting_id: str | None = None
    note_id: str | None = None
    doc_token: str | None = None
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


def list_meeting_briefs(
    client: FeishuClient,
    meeting_no: str,
    start_time: int,
    end_time: int,
    *,
    max_items: int = 100,
) -> list[dict[str, Any]]:
    """按会议号在 [start_time, end_time]（unix 秒）内列出会议摘要，逐页翻取。

    返回原始 ``meeting_briefs``（含 id/meeting_no/topic，不含 note_id）。
    """
    briefs: list[dict[str, Any]] = []
    page_token: str | None = None
    while len(briefs) < max_items:
        params: dict[str, Any] = {
            "meeting_no": meeting_no,
            "start_time": str(start_time),
            "end_time": str(end_time),
            "page_size": 50,
        }
        if page_token:
            params["page_token"] = page_token
        data = client.get(LIST_BY_NO_PATH, params)
        items = data.get("meeting_briefs") or data.get("meeting_list") or []
        briefs.extend(m for m in items if isinstance(m, dict))
        if not data.get("has_more") or not data.get("page_token"):
            break
        page_token = str(data["page_token"])
    return briefs[:max_items]


def get_meeting_detail(client: FeishuClient, meeting_id: str) -> dict[str, Any]:
    """GET /open-apis/vc/v1/meetings/{meeting_id}，返回 meeting 实体（含 note_id）。"""
    data = client.get(
        MEETING_GET_PATH.format(meeting_id=meeting_id), {"with_participants": "false"}
    )
    meeting = data.get("meeting")
    if not isinstance(meeting, dict):
        raise FeishuError(f"会议 {meeting_id} 响应缺少 meeting 实体")
    return meeting


def list_meetings_by_no(
    client: FeishuClient,
    meeting_no: str,
    start_time: int,
    end_time: int,
    *,
    max_items: int = 100,
) -> list[MeetingSummary]:
    """列出会议并逐个取详情补全 note_id（list_by_no 只给摘要，note_id 在会议详情里）。"""
    results: list[MeetingSummary] = []
    for brief in list_meeting_briefs(client, meeting_no, start_time, end_time, max_items=max_items):
        meeting_id = str(brief.get("id", ""))
        detail = get_meeting_detail(client, meeting_id) if meeting_id else {}
        results.append(
            MeetingSummary(
                meeting_id=meeting_id,
                meeting_no=str(brief.get("meeting_no", meeting_no)),
                topic=str(brief.get("topic", "")),
                note_id=(str(detail["note_id"]) if detail.get("note_id") else None),
                start_time=(str(detail["start_time"]) if detail.get("start_time") else None),
            )
        )
    return results


class FeishuNoteSource:
    """飞书会议纪要主链路：note_id → 逐字稿文档 → 正文（端点已核实，2026-08）。"""

    def __init__(self, client: FeishuClient) -> None:
        self.client = client

    def get_note(self, note_id: str) -> dict[str, Any]:
        """GET /open-apis/vc/v1/notes/{note_id}，返回 note 实体（含 artifacts）。"""
        data = self.client.get(f"/open-apis/vc/v1/notes/{note_id}")
        note = data.get("note")
        if not isinstance(note, dict):
            raise FeishuError(f"纪要 {note_id} 响应缺少 note 实体")
        return note

    def read_doc_text(self, doc_token: str) -> str:
        """GET /open-apis/docx/v1/documents/{doc_token}/raw_content，返回纯文本正文。"""
        data = self.client.get(f"/open-apis/docx/v1/documents/{doc_token}/raw_content")
        content = data.get("content")
        if not isinstance(content, str):
            raise FeishuError(f"文档 {doc_token} 未返回 content 正文")
        return content

    def fetch_transcript(self, note_id: str) -> TranscriptResult:
        """按 note_id 取回完整逐字稿正文（artifact_type=2）。

        无逐字稿产物时显式报错（不拿智能纪要冒充逐字稿），并可降级到本地兜底。
        """
        note = self.get_note(note_id)
        artifacts = note.get("artifacts") or []
        doc_token = next(
            (
                a.get("doc_token")
                for a in artifacts
                if isinstance(a, dict) and a.get("artifact_type") == ARTIFACT_TRANSCRIPT
            ),
            None,
        )
        if not doc_token:
            raise FeishuError(
                f"纪要 {note_id} 没有逐字稿产物（artifact_type=2）；"
                "可能该会议未生成逐字稿，请改用本地导入兜底"
            )
        text = self.read_doc_text(doc_token)
        return TranscriptResult(
            source="feishu-note",
            text=text,
            note_id=note_id,
            doc_token=doc_token,
        )
