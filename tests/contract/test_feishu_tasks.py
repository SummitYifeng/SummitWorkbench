"""飞书 Task v2 契约：创建/完成（写回）与列举（只读）的 endpoint/请求形状。"""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import SecretStr

from summit_workbench.providers.feishu import (
    FeishuAPIError,
    FeishuClient,
    complete_task,
    create_task,
    delete_task,
    update_task,
)
from summit_workbench.providers.feishu.config import FeishuConfig

CFG = FeishuConfig(app_id="cli_test", redirect_uri="http://localhost/callback")


def _capture_create() -> tuple[FeishuClient, list[dict[str, object]]]:
    bodies: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={"code": 0, "data": {"task": {"guid": "g", "url": "https://t"}}},
        )

    return (
        FeishuClient(
            CFG, SecretStr("token"), client=httpx.Client(transport=httpx.MockTransport(handler))
        ),
        bodies,
    )


def test_create_task_assigns_the_current_user_so_it_lands_in_their_list():
    """必须带 members[role=assignee]。

    飞书只把 creator 记为创建者，不会据此指派给本人；而今日简报用 list_tasks 只列
    「当前用户的任务」——不带 assignee 的任务只会在「全部任务」里可见，永远进不了
    用户自己的清单，审批→建任务的闭环会在最后一步断掉。
    """
    client, bodies = _capture_create()

    create_task(
        client,
        "写出排期表",
        "2026-09-19",
        "m:n#action-item-0",
        timezone="Asia/Shanghai",
        assignee_open_id="ou_3e9a8be618f19172c65b81d1c8be61f9",
    )

    members = bodies[0].get("members")
    assert members == [
        {"id": "ou_3e9a8be618f19172c65b81d1c8be61f9", "type": "user", "role": "assignee"}
    ]


def test_create_task_omits_members_without_an_assignee():
    """没拿到身份时退化为不带 members，而不是伪造一个负责人。"""
    client, bodies = _capture_create()

    create_task(client, "内部推进", None, "stable", timezone="Asia/Shanghai")

    assert "members" not in bodies[0]


def test_create_task_uses_official_v2_shape_and_stable_token():
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"code": 0, "data": {"task": {"guid": "task-guid", "url": "https://t"}}},
        )

    client = FeishuClient(
        CFG,
        SecretStr("token"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    first = create_task(
        client,
        "提交样章",
        "2026-09-04",
        "m:n#action-item-0",
        timezone="Asia/Shanghai",
        start_date="2026-09-01",
    )
    assert first.guid == "task-guid"
    assert seen["path"] == "/open-apis/task/v2/tasks"
    body = seen["body"]
    assert isinstance(body, dict)
    assert body["summary"] == "提交样章"
    assert body["due"]["is_all_day"] is True
    assert isinstance(body["due"]["timestamp"], int)
    assert body["start"]["is_all_day"] is True
    assert isinstance(body["start"]["timestamp"], int)
    assert body["start"]["timestamp"] == 1788192000000
    assert body["due"]["timestamp"] == 1788451200000
    assert body["client_token"].startswith("swb-")


def test_without_due_omits_due_field():
    bodies: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"code": 0, "data": {"task": {"task_id": "id"}}})

    client = FeishuClient(
        CFG,
        SecretStr("token"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = create_task(client, "内部推进", None, "stable", timezone="Asia/Shanghai")
    assert result.guid == "id"
    assert "due" not in bodies[0]


def test_create_task_retries_with_stable_client_token():
    calls = {"n": 0}
    bodies: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        bodies.append(json.loads(request.content))
        if calls["n"] == 1:
            return httpx.Response(503, text="temporary")
        return httpx.Response(200, json={"code": 0, "data": {"task": {"guid": "id"}}})

    client = FeishuClient(
        CFG,
        SecretStr("token"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _: None,
    )
    create_task(client, "可重试任务", None, "candidate-1", timezone="Asia/Shanghai")

    assert calls["n"] == 2
    assert bodies[0]["client_token"] == bodies[1]["client_token"]


def test_create_task_adds_operation_marker_when_outbox_managed():
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"code": 0, "data": {"task": {"guid": "id"}}})

    client = FeishuClient(
        CFG,
        SecretStr("token"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    create_task(
        client,
        "带标识任务",
        None,
        "candidate-1",
        timezone="Asia/Shanghai",
        operation_id="op-1",
    )
    body = seen["body"]
    assert isinstance(body, dict)
    assert "WB operation_id=op-1" in body["description"]


def test_complete_task_patches_completed_at_official_shape():
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "task": {
                        "agent_task_status": 4,
                        "completed_at": str(int(1789000000 * 1000)),
                    }
                },
            },
        )

    client = FeishuClient(
        CFG,
        SecretStr("token"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    # 真机核实（2026-09-03）：update_fields 白名单不含 completed、POST .../complete 返回 404；
    # 完成正解 = PATCH 设置 completed_at（毫秒字符串）+ update_fields。
    complete_task(client, "task-guid-123")
    assert seen["method"] == "PATCH"
    assert seen["path"] == "/open-apis/task/v2/tasks/task-guid-123"
    body = seen["body"]
    assert isinstance(body, dict)
    task = body.get("task")
    assert isinstance(task, dict)
    completed_at = str(task.get("completed_at") or "")
    assert completed_at.isdigit() and len(completed_at) == 13
    assert body["update_fields"] == ["completed_at"]


_ALREADY_COMPLETED_MSG = (
    "Invalid Param 'task.completed_at', cannot set non-zero completed_at for a completed task. "
    "To change task's completed_at, you can update task's 'completed_at' to 0, then update its "
    "'completed'_at to new value."
)


def _complete_handlers(
    patch_response: httpx.Response, get_response: httpx.Response
) -> tuple[FeishuClient, list[tuple[str, str]]]:
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        return patch_response if request.method == "PATCH" else get_response

    client = FeishuClient(
        CFG, SecretStr("token"), client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    return client, seen


@pytest.mark.parametrize(
    "task_payload",
    [
        {"guid": "task-1", "completed_at": "1756700000000"},
        {"guid": "task-1", "completed_at": "0", "status": "done"},
    ],
)
def test_complete_task_is_idempotent_when_feishu_says_already_completed(
    task_payload: dict[str, object],
) -> None:
    """飞书拒绝对已完成任务再次完成（2026-09-19 真机）。

    本地待办列表只是**简报生成时**的快照，任务可能已在飞书 App / 别处完成 ⇒ 再点「✓」
    会 `PATCH` 一个非零 `completed_at`，飞书报
    "cannot set non-zero completed_at for a completed task"（官方 PATCH 文档：
    「不能对已经完成的任务再次完成」）。此时「完成」的目标本已达成 ⇒ 只读复核一次后
    按成功返回，而不是把红色警告丢给用户。`completed_at` 与 `status` 任一表明完成即可。
    """
    client, seen = _complete_handlers(
        httpx.Response(400, json={"code": 1470400, "msg": _ALREADY_COMPLETED_MSG}),
        httpx.Response(200, json={"code": 0, "data": {"task": task_payload}}),
    )

    complete_task(client, "task-1")  # 不抛错 = 幂等成功

    assert seen == [
        ("PATCH", "/open-apis/task/v2/tasks/task-1"),
        ("GET", "/open-apis/task/v2/tasks/task-1"),
    ]


def test_complete_task_reraises_when_recovery_read_says_still_pending() -> None:
    """复核发现任务**确实未完成**时，原始 PATCH 失败必须原样上抛（不吞错，NFR-6）。"""
    client, _seen = _complete_handlers(
        httpx.Response(400, json={"code": 1470400, "msg": "PATCH 真因"}),
        httpx.Response(
            200,
            json={"code": 0, "data": {"task": {"guid": "task-1", "completed_at": "0"}}},
        ),
    )

    with pytest.raises(FeishuAPIError) as excinfo:
        complete_task(client, "task-1")

    assert "PATCH 真因" in str(excinfo.value)
    assert excinfo.value.code == 1470400


def test_complete_task_reraises_original_error_when_recovery_read_fails() -> None:
    """复核本身失败（任务已删/网络）时不能让 GET 的错误顶替 PATCH 的错误，否则真因被掩盖。"""
    client, _seen = _complete_handlers(
        httpx.Response(400, json={"code": 1470400, "msg": "PATCH 真因"}),
        httpx.Response(404, json={"code": 1470404, "msg": "任务不存在或已删除"}),
    )

    with pytest.raises(FeishuAPIError) as excinfo:
        complete_task(client, "task-1")

    assert "PATCH 真因" in str(excinfo.value)
    assert "已删除" not in str(excinfo.value)


def test_update_task_patches_only_given_fields():
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(
            {
                "method": request.method,
                "path": request.url.path,
                "body": json.loads(request.content),
            }
        )
        return httpx.Response(200, json={"code": 0, "data": {}})

    client = FeishuClient(
        CFG,
        SecretStr("token"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    update_task(client, "task-1", summary="改标题", timezone="Asia/Shanghai")
    body = seen[-1]["body"]
    assert isinstance(body, dict)
    task = body.get("task")
    assert isinstance(task, dict)
    assert task == {"summary": "改标题"}
    assert body["update_fields"] == ["summary"]

    update_task(client, "task-1", due_date="2026-09-10", timezone="Asia/Shanghai")
    body = seen[-1]["body"]
    assert isinstance(body, dict)
    task = body.get("task")
    assert isinstance(task, dict)
    assert set(task) == {"due"}
    assert body["update_fields"] == ["due"]
    due = task["due"]
    assert isinstance(due, dict)
    assert due["is_all_day"] is True
    assert isinstance(due["timestamp"], int)

    update_task(client, "task-1", clear_due=True, timezone="Asia/Shanghai")
    body = seen[-1]["body"]
    assert isinstance(body, dict)
    task = body.get("task")
    assert isinstance(task, dict)
    assert task["due"] is None
    assert body["update_fields"] == ["due"]


def test_delete_task_deletes_official_endpoint():
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        return httpx.Response(200, json={"code": 0, "data": {}})

    client = FeishuClient(
        CFG,
        SecretStr("token"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    delete_task(client, "task-guid-9")
    assert seen["method"] == "DELETE"
    assert seen["path"] == "/open-apis/task/v2/tasks/task-guid-9"
