"""Self-contained entry point used by the packaged macOS server bundle."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import socket
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import uvicorn

from summit_workbench.config.profiles import resolve_active_workspace
from summit_workbench.config.settings import default_config_file
from summit_workbench.config.tls_trust import configure_default_tls_trust, tls_runtime_diagnostic
from summit_workbench.webapp.app import WebContext, create_app
from summit_workbench.webapp.build_info import (
    WebBuildInfo,
    mode_from_environment,
    new_server_instance,
)
from summit_workbench.webapp.runtime import (
    RuntimeRecord,
    cleanup_stale_runtime_record,
    load_runtime_record,
    write_runtime_record,
)
from summit_workbench.webapp.security import validate_bind_host


def _feishu_callback_target(context: WebContext | None) -> tuple[int, str] | None:
    """Return a configured local OAuth callback target, if one is usable by the App."""
    try:
        if context is not None and context.workspace_id is not None:
            from summit_workbench.workflows.settings_connections import feishu_config

            cfg = feishu_config(
                config_file=context.provider_config_file(), workspace_id=context.workspace_id
            )
        else:
            from summit_workbench.providers.feishu.config import load_feishu_config

            # Restricted onboarding has no workspace context yet, but it still
            # needs the configured redirect target to receive the first callback.
            cfg = load_feishu_config(default_config_file())
    except Exception:
        return None
    parsed = urlsplit(cfg.redirect_uri)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"localhost", "127.0.0.1"}
        or parsed.port is None
        or parsed.path not in {"/callback", "/callback/feishu"}
    ):
        return None
    return parsed.port, parsed.path


def _bind_feishu_callback_socket(
    target: tuple[int, str] | None, *, bound_port: int
) -> socket.socket | None:
    """Bind the legacy fixed localhost callback while the panel keeps a random port."""
    if target is None or target[0] == bound_port:
        return None
    callback = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    callback.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        callback.bind(("127.0.0.1", target[0]))
        callback.listen(128)
    except OSError as exc:
        callback.close()
        raise SystemExit(
            f"飞书 OAuth 回调端口 {target[0]} 无法监听；请关闭占用该端口的程序后重试"
        ) from exc
    return callback


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SummitWorkbench bundled web server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--work-root", default=os.environ.get("WORK_ROOT"))
    parser.add_argument("--static-dir", default=os.environ.get("WB_STATIC_DIR"))
    parser.add_argument("--runtime-record", default=os.environ.get("WB_RUNTIME_RECORD"))
    parser.add_argument(
        "--tls-diagnostic",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    # 打包运行时 OpenSSL 默认 CA 路径不可用；先统一指向随 bundle 分发的 certifi
    # CA bundle，避免 dulwich/httpx 对 GitHub 报 TLS 校验失败（P1-07D）。
    configure_default_tls_trust()
    args = _parser().parse_args(argv)
    if args.tls_diagnostic:
        print(json.dumps(tls_runtime_diagnostic(), ensure_ascii=False, sort_keys=True))
        return
    validate_bind_host(args.host, mode_from_environment(os.environ.get("WB_PANEL_MODE")))
    static_dir = Path(args.static_dir).expanduser() if args.static_dir else None
    if static_dir is None or not static_dir.is_dir():
        raise SystemExit("WB_STATIC_DIR/--static-dir 必须指向 bundle 内的 web/static")
    # Bundled/production server never consumes WORK_ROOT or --work-root.  An empty
    # installation receives a restricted onboarding control plane instead of creating
    # the legacy default vault.
    active_workspace = resolve_active_workspace(allow_env_fallback=False)
    ctx = WebContext.from_active_workspace(active_workspace)
    server_instance = new_server_instance()
    session_token = os.environ.setdefault("WB_SESSION_TOKEN", secrets.token_urlsafe(32))
    started_at = datetime.now(UTC)
    if ctx is None:
        application = create_app(
            None,
            static_dir=static_dir,
            bind_host=args.host,
            port=args.port,
            session_token=session_token,
            workspace_id=active_workspace.workspace_id,
            device_id=active_workspace.device_id,
            server_instance=server_instance,
        )
    else:
        # Keep the explicit call shape visible to packaging contract checks.
        application = create_app(
            ctx,
            static_dir=static_dir,
            bind_host=args.host,
            port=args.port,
            session_token=session_token,
            workspace_id=active_workspace.workspace_id,
            device_id=active_workspace.device_id,
            server_instance=server_instance,
        )

    family = socket.AF_INET6 if ":" in args.host else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((args.host, args.port))
    sock.listen(2048)
    bound_port = int(sock.getsockname()[1])
    callback_target = _feishu_callback_target(ctx)
    callback_sock = _bind_feishu_callback_socket(callback_target, bound_port=bound_port)
    if args.runtime_record:
        record_path = Path(args.runtime_record).expanduser()
    else:
        record_dir = active_workspace.runtime_dir or active_workspace.application_support
        record_path = record_dir / "runtime.json"
    cleanup_stale_runtime_record(record_path)
    existing = load_runtime_record(record_path)
    if existing is not None and existing.pid != os.getpid():
        raise SystemExit("已有 SummitWorkbench 服务实例正在运行；未终止未知进程")
    try:
        info = WebBuildInfo.from_static_dir(static_dir)
        frontend_build = info.frontend_build
    except Exception as exc:
        sock.close()
        raise SystemExit(f"静态构建元数据无效：{exc}") from exc
    write_runtime_record(
        RuntimeRecord(
            product_id="com.summitworkbench.panel",
            api_protocol=2,
            frontend_build=frontend_build,
            server_instance=server_instance,
            workspace_id=active_workspace.workspace_id,
            device_id=active_workspace.device_id,
            pid=os.getpid(),
            port=bound_port,
            started_at=started_at,
        ),
        path=record_path,
    )
    application.state.bound_port = bound_port
    application.state.feishu_callback_required = callback_target is not None
    application.state.feishu_callback_ready = (
        callback_target is None
        or callback_sock is not None
        or (callback_target[0] == bound_port if callback_target else False)
    )
    config = uvicorn.Config(application, host=args.host, port=bound_port, log_level="warning")
    server = uvicorn.Server(config)
    try:
        sockets = [sock, callback_sock] if callback_sock is not None else [sock]
        server.run(sockets=sockets)
    finally:
        sock.close()
        if callback_sock is not None:
            callback_sock.close()
        record_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
