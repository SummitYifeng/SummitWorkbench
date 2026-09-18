"""``build-meta.json`` 读取契约（2026-09-18：脏树构建必须仍可加载）。

背景：为了让前端 build 身份不再依赖 git 提交，构建器在工作树脏时把
``git_revision`` 写成空串。旧读取实现用 ``_required_str`` 读该字段、拒绝空串，
于是「脏树构建出的包」启动即 503（`/api/version` 报 BuildInfoError）。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from summit_workbench.webapp.build_info import BuildInfoError, WebBuildInfo

STATIC_DIR = Path(__file__).resolve().parents[2] / "src/summit_workbench/webapp/static"


def _static_with_meta(tmp_path: Path, mutate) -> Path:
    """复制真实静态产物到 tmp_path 并改写 build-meta（保证资产哈希仍自洽）。"""
    target = tmp_path / "static"
    shutil.copytree(STATIC_DIR, target)
    meta_path = target / "build-meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    mutate(meta)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def test_build_meta_accepts_empty_git_revision_from_dirty_tree(tmp_path: Path) -> None:
    """脏树构建（git_revision 为空串）必须加载成功，并归一为 None。"""
    static = _static_with_meta(tmp_path, lambda meta: meta.update({"git_revision": ""}))

    info = WebBuildInfo.from_static_dir(static)

    assert info.git_revision is None
    assert info.frontend_build  # 身份本身不受影响


def test_build_meta_accepts_missing_git_revision(tmp_path: Path) -> None:
    """字段整个缺失同样按可选处理（老/未来产物兼容）。"""
    static = _static_with_meta(tmp_path, lambda meta: meta.pop("git_revision", None))

    assert WebBuildInfo.from_static_dir(static).git_revision is None


def test_build_meta_still_rejects_invalid_git_revision_type(tmp_path: Path) -> None:
    """可选 ≠ 不校验：类型不对仍然报错，避免静默吞掉损坏的元数据。"""
    static = _static_with_meta(tmp_path, lambda meta: meta.update({"git_revision": 123}))

    with pytest.raises(BuildInfoError):
        WebBuildInfo.from_static_dir(static)


def test_build_meta_keeps_requiring_core_identity_fields(tmp_path: Path) -> None:
    """核心身份字段（frontend_build）不允许为空——可选化只针对溯源字段。"""
    static = _static_with_meta(tmp_path, lambda meta: meta.update({"frontend_build": ""}))

    with pytest.raises(BuildInfoError):
        WebBuildInfo.from_static_dir(static)
