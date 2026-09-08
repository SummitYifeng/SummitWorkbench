"""P0-11A：可恢复首次使用向导与安装级非秘密草稿。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from summit_workbench.config.app_support import app_support_dir
from summit_workbench.repositories.onboarding_draft import (
    OnboardingDraft,
    clear_onboarding_draft,
    load_onboarding_draft,
    save_onboarding_draft,
)
from summit_workbench.webapp.app import create_app


def test_onboarding_draft_is_atomic_private_and_contains_no_secret(tmp_path: Path) -> None:
    home = tmp_path / "home"
    draft = OnboardingDraft(
        flow="create-new",
        step="location",
        work_root=str(tmp_path / "Work"),
        display_name="My Workbench",
        model_id="model-name",
        feishu_app_id="cli_demo",
        provider_status="skipped",
    )

    path = save_onboarding_draft(draft, home=home)
    assert path.stat().st_mode & 0o777 == 0o600
    loaded = load_onboarding_draft(home=home)
    assert loaded is not None
    assert loaded.model_copy(update={"updated_at": None}) == draft
    assert "canary-secret" not in path.read_text(encoding="utf-8")
    clear_onboarding_draft(home=home)
    assert load_onboarding_draft(home=home) is None


def test_onboarding_draft_rejects_secret_fields_and_never_creates_workspace_id(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    with pytest.raises(ValidationError):
        OnboardingDraft.model_validate(
            {"flow": "model", "step": "provider", "api_key": "canary-secret"}
        )
    draft = OnboardingDraft(flow="model", step="provider")
    save_onboarding_draft(draft, home=home)
    raw = json.loads((app_support_dir(home) / "onboarding-draft.json").read_text(encoding="utf-8"))
    assert "api_key" not in raw
    assert raw.get("workspace_id") is None


def test_empty_install_renders_recoverable_wizard_and_api(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    app = create_app(None, static_dir=tmp_path / "missing-static")
    client = TestClient(app)
    page = client.get("/")
    assert page.status_code == 200
    assert "新建我的工作台" in page.text
    assert "连接已有工作台" in page.text
    assert "升级这台 Mac 上的旧工作台" in page.text
    assert "api_key" not in page.text
    assert "/feishu/status?state=" in page.text
    assert "restartService" in page.text
    assert client.get("/api/onboarding/draft").json()["draft"] is None
    saved = client.put(
        "/api/onboarding/draft",
        json={"flow": "create-new", "step": "location", "work_root": str(tmp_path / "Work")},
    )
    assert saved.status_code == 200
    draft = client.get("/api/onboarding/draft").json()["draft"]
    assert draft["work_root"] == str(tmp_path / "Work")
    rejected = client.put(
        "/api/onboarding/draft",
        json={"flow": "model", "step": "provider", "api_key": "canary-secret"},
    )
    assert rejected.status_code == 422
    assert "canary-secret" not in rejected.text
    assert client.delete("/api/onboarding/draft").json()["ok"] is True
