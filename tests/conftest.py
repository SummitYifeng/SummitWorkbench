"""所有测试默认使用临时 HOME，避免隐式读取或污染开发者本机状态。"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolate_home(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory) -> None:
    fake_home = tmp_path_factory.mktemp("home")
    monkeypatch.setenv("HOME", str(fake_home))
