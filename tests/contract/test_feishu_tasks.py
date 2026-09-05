"""飞书 Task v2 契约：创建/完成（写回）与列举（只读）的 endpoint/请求形状。"""

from __future__ import annotations

import json

import httpx
from pydantic import SecretStr

from summit_workbench.providers.feishu import (
    FeishuClient,
    complete_task,
    create_task,
    delete_task,
    update_task,
)
from summit_workbench.providers.feishu.config import FeishuConfig

CFG = FeishuConfig(app_id="cli_test", redirect_uri="http://localhost/callback")


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
    )
    assert first.guid == "task-guid"
    assert seen["path"] == "/open-apis/task/v2/tasks"
    body = seen["body"]
    assert isinstance(body, dict)
    assert body["summary"] == "提交样章"
    assert body["due"]["is_all_day"] is True
    assert isinstance(body["due"]["timestamp"], int)
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
