"""打包内置的飞书默认凭据（仅分发给同事的构建使用）。

为什么需要这一层：飞书 ``authen/v2/oauth/token`` 的 ``client_secret`` 是**必填**，
``code_verifier``（PKCE）只是可选的额外保护，不能替代它；而分发包里没有可代持秘密的
后端，所以要让同事「装完点一下就能授权」，唯一办法是构建时把 app_id（非秘密）与
app_secret 作为**默认值**写进包内资源 ``Contents/Resources/feishu-defaults.json``
（由 ``scripts/build-macos-app.sh`` 在签名前写入，见该脚本的 ``REQUIRE_BUNDLED_FEISHU``）。

运行时优先级固定为「显式配置/Keychain > 内置默认」：

- 仓库内**不存在**该资源文件，开发与测试默认拿不到内置凭据；
- 需要时用 ``WB_FEISHU_DEFAULTS`` 显式指向一个文件（一旦设置即以此为唯一来源，
  便于测试确定性地构造「有/无内置凭据」两种情况）；
- 包内运行时按 ``WB_STATIC_DIR``（``Resources/web/static`` 的上一级）与
  ``sys.executable``（``Resources/server/SummitWorkbenchServer`` 的上一级）定位。

秘密只以 :class:`~pydantic.SecretStr` 承载，绝不写入日志或诊断输出。
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

from pydantic import SecretStr

from summit_workbench.providers.feishu.errors import FeishuConfigError

#: 包内资源文件名（位于 ``Contents/Resources/``）。
BUNDLED_FILENAME = "feishu-defaults.json"

#: 显式覆盖内置凭据文件路径的环境变量（设置后不再探测其他位置）。
BUNDLED_PATH_ENV = "WB_FEISHU_DEFAULTS"

#: 与 ``config.example.toml`` 一致的回调默认值。
DEFAULT_REDIRECT_URI = "http://localhost:8765/callback"


@dataclass(frozen=True)
class BundledFeishuDefaults:
    """包内内置的飞书默认值。``app_secret`` 可能缺失（只内置 app_id 的构建）。"""

    app_id: str
    redirect_uri: str
    app_secret: SecretStr | None = None


def _candidate_paths() -> tuple[Path, ...]:
    """按优先级给出候选文件路径；``WB_FEISHU_DEFAULTS`` 一经设置即独占。"""
    import os

    override = os.environ.get(BUNDLED_PATH_ENV)
    if override is not None:
        return (Path(override).expanduser(),) if override.strip() else ()

    candidates: list[Path] = []
    static_dir = os.environ.get("WB_STATIC_DIR")
    if static_dir:
        # Resources/web/static → Resources
        candidates.append(Path(static_dir).expanduser().parent.parent / BUNDLED_FILENAME)
    # Resources/server/SummitWorkbenchServer → Resources
    candidates.append(Path(sys.executable).resolve().parent.parent / BUNDLED_FILENAME)
    return tuple(candidates)


def bundled_defaults_file() -> Path | None:
    """返回实际存在的内置凭据文件；没有则返回 ``None``。"""
    for candidate in _candidate_paths():
        if candidate.is_file():
            return candidate
    return None


def load_bundled_defaults() -> BundledFeishuDefaults | None:
    """读取内置默认凭据。

    :returns: 内置凭据；未随包分发（开发/测试环境）时为 ``None``。
    :raises FeishuConfigError: 文件存在但内容损坏——构建缺陷必须显式暴露，
        不能用占位值蒙混过去。
    """
    path = bundled_defaults_file()
    if path is None:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FeishuConfigError(f"内置飞书默认凭据文件无法解析：{path}") from exc
    if not isinstance(payload, dict):
        raise FeishuConfigError(f"内置飞书默认凭据文件格式不正确（应为 JSON 对象）：{path}")

    app_id = payload.get("app_id")
    if not isinstance(app_id, str) or not app_id.strip():
        # 没有 app_id 就无法授权，等同于未内置。
        return None
    redirect_uri = payload.get("redirect_uri")
    secret = payload.get("app_secret")
    return BundledFeishuDefaults(
        app_id=app_id.strip(),
        redirect_uri=(
            redirect_uri.strip()
            if isinstance(redirect_uri, str) and redirect_uri.strip()
            else DEFAULT_REDIRECT_URI
        ),
        app_secret=(SecretStr(secret) if isinstance(secret, str) and secret.strip() else None),
    )


__all__ = [
    "BUNDLED_FILENAME",
    "BUNDLED_PATH_ENV",
    "DEFAULT_REDIRECT_URI",
    "BundledFeishuDefaults",
    "bundled_defaults_file",
    "load_bundled_defaults",
]
