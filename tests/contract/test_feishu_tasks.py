"""飞书 Task v2 契约：创建/完成（写回）与列举（只读）的 endpoint/请求形状。"""

from __future__ import annotations

import json

import httpx
from pydantic import SecretStr

from summit_workbench.providers.feishu import FeishuClient, complete_task, create_task
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


def test_complete_task_patches_official_v2_shape():
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"code": 0, "data": {}})

    client = FeishuClient(
        CFG,
        SecretStr("token"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    complete_task(client, "task-guid-123")
    assert seen["method"] == "PATCH"
    assert seen["path"] == "/open-apis/task/v2/tasks/task-guid-123"
    body = seen["body"]
    assert isinstance(body, dict)
    task = body.get("task")
    assert isinstance(task, dict)
    assert task["completed"] is True
