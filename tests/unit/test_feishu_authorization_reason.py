"""飞书授权失败的原因透出：错误码 → 可执行提示 → 授权状态 → 向导界面。

分发包内置凭据后，同事本机没有任何可改的配置；授权失败时界面必须说清「找谁、做什么」，
否则同事只能在同一个按钮上反复点击。这里锁住整条链路。
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from summit_workbench.config.secrets import CredentialError, CredentialRef, resolve_credential
from summit_workbench.providers.feishu import auth
from summit_workbench.providers.feishu.config import FeishuConfig
from summit_workbench.providers.feishu.errors import FeishuAuthError
from summit_workbench.webapp import feishu_authorization
from summit_workbench.webapp.app import create_app
from summit_workbench.webapp.routers import settings as settings_routes
from summit_workbench.webapp.routers.settings import _AuthorizationStates

CFG = FeishuConfig(app_id="cli_test", redirect_uri="http://localhost:8765/callback")


def _client(payload: object, status: int = 400) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


# ---- 错误码 → 可执行提示 ----


@pytest.mark.parametrize(
    ("error", "code", "expected"),
    [
        (None, 20010, "可用范围"),
        (None, 20002, "内置的应用凭据无效"),
        (None, 20003, "重新点一次"),
        (None, 20065, "已被使用过"),
        ("invalid_grant", None, "重新点一次"),
    ],
)
def test_token_failure_message_is_actionable(error, code, expected) -> None:
    message = auth.token_failure_message(error=error, code=code, status=400)
    assert expected in message
    # 原始错误码必须保留，便于审计与对账
    assert str(code if code is not None else error) in message


def test_token_failure_message_keeps_unknown_codes_verbatim() -> None:
    message = auth.token_failure_message(error=None, code=99999, status=400)
    assert "99999" in message
    assert message.startswith("令牌端点失败（HTTP 400")


def test_exchange_code_surfaces_user_permission_hint() -> None:
    """同事最常见的失败：管理员还没把他加入应用「可用范围」（20010）。"""
    with pytest.raises(FeishuAuthError) as excinfo:
        auth.exchange_code(
            CFG, SecretStr("s"), "code", client=_client({"code": 20010, "msg": "no"})
        )
    assert "可用范围" in str(excinfo.value)


def test_exchange_code_does_not_leak_request_material() -> None:
    secret = "canary-secret-value"
    code = "canary-authorization-code"
    with pytest.raises(FeishuAuthError) as excinfo:
        auth.exchange_code(CFG, SecretStr(secret), code, client=_client({"code": 20002}))
    assert secret not in str(excinfo.value)
    assert code not in str(excinfo.value)


def test_refresh_failure_still_marks_needs_reauthorize() -> None:
    with pytest.raises(FeishuAuthError) as excinfo:
        auth.refresh_token(CFG, SecretStr("s"), SecretStr("rt"), client=_client({"code": 20003}))
    assert excinfo.value.needs_reauthorize is True


def test_keychain_failure_has_stable_reason_without_leaking_stderr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import subprocess

    monkeypatch.setattr(
        "summit_workbench.config.secrets.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args, 44, "", "security: User interaction is not allowed\n"
        ),
    )

    with pytest.raises(CredentialError) as excinfo:
        resolve_credential(type("Ref", (), {"service": "svc", "account": "acct"})())
    assert excinfo.value.reason == "denied"
    assert "User interaction" not in str(excinfo.value)


@pytest.mark.parametrize(
    ("failure", "reason"),
    [
        ("missing", "missing"),
        ("timeout", "timeout"),
        ("unavailable", "unavailable"),
    ],
)
def test_keychain_failure_reasons_are_stable(
    monkeypatch: pytest.MonkeyPatch, failure: str, reason: str
) -> None:
    import subprocess

    if failure == "timeout":

        def run(*args, **kwargs):
            raise subprocess.TimeoutExpired(args[0], 30)
    elif failure == "unavailable":

        def run(*args, **kwargs):
            raise FileNotFoundError("security")
    else:

        def run(*args, **kwargs):
            return subprocess.CompletedProcess(args, 44, "", "security: item not found")

    monkeypatch.setattr("summit_workbench.config.secrets.subprocess.run", run)
    with pytest.raises(CredentialError) as excinfo:
        resolve_credential(CredentialRef(service="svc", account="acct"))
    assert excinfo.value.reason == reason


def test_keychain_timeout_has_distinct_public_error_code() -> None:
    from summit_workbench.webapp.routers.settings import _credential_error_code

    assert _credential_error_code(CredentialError("timeout", reason="timeout")) == (
        "credential_timeout"
    )
    assert _credential_error_code(CredentialError("denied", reason="denied")) == (
        "feishu_credentials_unavailable"
    )


def test_authorize_url_blocks_before_redirect_when_credentials_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from summit_workbench.workflows import settings_connections

    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    config = tmp_path / "config.toml"
    config.write_text(
        '[feishu]\napp_id = "cli_test"\nredirect_uri = "http://localhost:8765/callback"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("WB_CONFIG_FILE", str(config))
    monkeypatch.setenv("WB_FEISHU_DEFAULTS", "")
    monkeypatch.setattr(
        settings_connections.FeishuSession,
        "_app_secret",
        lambda self: (_ for _ in ()).throw(CredentialError("blocked", reason="denied")),
    )

    client = TestClient(create_app(None, static_dir=tmp_path / "missing-static"))
    workspace_id = client.post(
        "/api/onboarding/create", json={"work_root": str(tmp_path / "Work")}
    ).json()["workspace_id"]

    response = client.post(
        "/api/onboarding/feishu/authorize-url", json={"workspace_id": workspace_id}
    )
    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "feishu_credentials_unavailable"
    assert "钥匙串" in body["message"]
    assert "blocked" not in response.text


def test_denied_reason_covers_user_cancel_and_short_circuit() -> None:
    from summit_workbench.webapp.routers.settings import _denied_reason

    assert "取消了授权" in _denied_reason("access_denied")
    assert "access_denied" not in _denied_reason("access_denied")  # 面向用户，不暴露原始串
    assert "没有收到授权码" in _denied_reason(None)
    assert "other_error" in _denied_reason("other_error")


# ---- 授权状态携带原因（含持久化）----


def test_authorization_state_keeps_and_clears_reason(tmp_path: Path) -> None:
    path = tmp_path / "feishu-auth-state.json"
    states = _AuthorizationStates(path)
    state = states.issue("ws-1")

    assert states.finish(state, workspace_id="ws-1", status="failed", reason="请联系管理员")
    assert states.lookup(state) is not None
    assert states.lookup(state).reason == "请联系管理员"  # type: ignore[union-attr]

    # 重新加载（同一状态文件）后原因仍在——App 重启不该丢失解释
    assert _AuthorizationStates(path).lookup(state).reason == "请联系管理员"  # type: ignore[union-attr]

    # 成功路径不保留失败原因
    state2 = states.issue("ws-1")
    assert states.finish(state2, workspace_id="ws-1", status="connected", reason="陈旧原因")
    assert states.lookup(state2).reason is None  # type: ignore[union-attr]


def test_settings_keeps_compatibility_exports_for_authorization_helpers() -> None:
    assert settings_routes._PendingAuthorization is feishu_authorization.PendingAuthorization
    assert settings_routes._AuthorizationStates is feishu_authorization.AuthorizationStates
    old_state_file = settings_routes._authorization_state_file
    new_state_file = feishu_authorization.authorization_state_file
    assert old_state_file is new_state_file
    assert settings_routes._denied_reason is feishu_authorization.denied_reason


def test_authorization_state_file_has_no_unexpected_fields(tmp_path: Path) -> None:
    path = tmp_path / "feishu-auth-state.json"
    states = _AuthorizationStates(path)
    state = states.issue("ws-1")
    states.finish(state, workspace_id="ws-1", status="failed", reason="请联系管理员")
    item = json.loads(path.read_text(encoding="utf-8"))["items"][state]
    assert set(item) == {"workspace_id", "created_at", "status", "reason"}


# ---- 端到端：被拒绝 → 向导显示原因 ----


def test_wizard_shows_reason_when_authorization_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    bundled = tmp_path / "feishu-defaults.json"
    bundled.write_text(
        json.dumps({"app_id": "cli_bundled", "app_secret": "s", "redirect_uri": CFG.redirect_uri}),
        encoding="utf-8",
    )
    monkeypatch.setenv("WB_FEISHU_DEFAULTS", str(bundled))

    client = TestClient(create_app(None, static_dir=tmp_path / "missing-static"))
    # 向导页面本身必须把失败原因显示出来（而不是只说「授权未完成」）
    wizard = client.get("/")
    assert wizard.status_code == 200
    assert "data.reason" in wizard.text
    assert "飞书授权未完成，请重新点击授权" in wizard.text  # 兜底文案仍在

    created = client.post("/api/onboarding/create", json={"work_root": str(tmp_path / "Work")})
    assert created.status_code == 200
    workspace_id = created.json()["workspace_id"]

    started = client.post(
        "/api/onboarding/feishu/authorize-url", json={"workspace_id": workspace_id}
    )
    assert started.status_code == 200
    state = started.json()["state"]

    # 用户在飞书页点了「拒绝」
    callback = client.get("/callback", params={"error": "access_denied", "state": state})
    assert callback.status_code == 200

    status = client.get("/api/onboarding/feishu/status", params={"state": state}).json()
    assert status["status"] == "failed"
    assert "取消了授权" in status["reason"]
    assert "access_denied" not in status["reason"]

    # 查询本身不消费状态，向导轮询可重复读取同一个原因
    again = client.get("/api/onboarding/feishu/status", params={"state": state}).json()
    assert again["reason"] == status["reason"]


def test_static_fallback_page_explains_failure_without_session_cookie(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """拿不到 wb_session 时无法回到面板（例如授权在外部浏览器完成），静态页要自己说明原因。"""
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    bundled = tmp_path / "feishu-defaults.json"
    bundled.write_text(
        json.dumps({"app_id": "cli_bundled", "app_secret": "s", "redirect_uri": CFG.redirect_uri}),
        encoding="utf-8",
    )
    monkeypatch.setenv("WB_FEISHU_DEFAULTS", str(bundled))

    client = TestClient(create_app(None, static_dir=tmp_path / "missing-static"))
    workspace_id = client.post(
        "/api/onboarding/create", json={"work_root": str(tmp_path / "Work")}
    ).json()["workspace_id"]

    def start() -> str:
        payload: dict[str, str] = client.post(
            "/api/onboarding/feishu/authorize-url", json={"workspace_id": workspace_id}
        ).json()
        return payload["state"]

    client.cookies.clear()
    page = client.get(
        "/callback", params={"error": "access_denied", "state": start()}, follow_redirects=False
    )
    assert page.status_code == 200
    assert "授权未完成" in page.text
    assert "取消了授权" in page.text

    # 未信任的 error 参数会被拼进页面：必须转义，不能原样落成标签
    hostile = client.get(
        "/callback",
        params={"error": "<script>alert(1)</script>", "state": start()},
        follow_redirects=False,
    )
    assert "<script>alert(1)</script>" not in hostile.text
    assert "&lt;script&gt;" in hostile.text

    # 状态无效时也不能只说「未完成」
    expired = client.get("/callback", params={"state": "not-a-real-state"}, follow_redirects=False)
    assert "授权链接已失效" in expired.text
