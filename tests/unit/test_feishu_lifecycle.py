"""P0-03 飞书客户端的 App 生命周期测试。"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from summit_workbench.webapp.app import WebContext, create_app


def test_app_lifespan_closes_cached_feishu_clients(tmp_path: Path, monkeypatch) -> None:
    closed = {"n": 0}

    class FakeSession:
        def __init__(self, _cfg: object, lock_root: Path | None = None) -> None:
            # P0-06：池会传入 ctx.lock_root（此处为 None → 兼容旧语义）
            assert lock_root is None

        def access_token(self):
            return "token"

    class FakeClient:
        def __init__(self, _cfg: object, _token: object) -> None:
            pass

        def close(self) -> None:
            closed["n"] += 1

    monkeypatch.setattr("summit_workbench.providers.feishu.FeishuSession", FakeSession)
    monkeypatch.setattr("summit_workbench.providers.feishu.FeishuClient", FakeClient)
    monkeypatch.setattr("summit_workbench.providers.feishu.load_feishu_config", lambda: object())

    app = create_app(
        WebContext(tmp_path / "vault", tmp_path, "Asia/Shanghai"),
        static_dir=tmp_path / "no-static",
    )
    with TestClient(app):
        first = app.state.feishu_clients.user_client()
        second = app.state.feishu_clients.user_client()
        assert first is second
        assert closed["n"] == 0
    assert closed["n"] == 1
