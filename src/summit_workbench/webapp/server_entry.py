"""Self-contained entry point used by the packaged macOS server bundle."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import uvicorn

from summit_workbench.config.profiles import resolve_active_workspace
from summit_workbench.webapp.app import WebContext, create_app
from summit_workbench.webapp.build_info import mode_from_environment
from summit_workbench.webapp.security import validate_bind_host


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SummitWorkbench bundled web server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--work-root", default=os.environ.get("WORK_ROOT"))
    parser.add_argument("--static-dir", default=os.environ.get("WB_STATIC_DIR"))
    return parser


def main(argv: list[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    validate_bind_host(args.host, mode_from_environment(os.environ.get("WB_PANEL_MODE")))
    static_dir = Path(args.static_dir).expanduser() if args.static_dir else None
    if static_dir is None or not static_dir.is_dir():
        raise SystemExit("WB_STATIC_DIR/--static-dir 必须指向 bundle 内的 web/static")
    # Bundled/production server never consumes WORK_ROOT or --work-root.  An empty
    # installation receives a restricted onboarding control plane instead of creating
    # the legacy default vault.
    active_workspace = resolve_active_workspace(allow_env_fallback=False)
    ctx = WebContext.from_active_workspace(active_workspace)
    if ctx is None:
        application = create_app(
            None,
            static_dir=static_dir,
            bind_host=args.host,
            port=args.port,
        )
    else:
        # Keep the explicit call shape visible to packaging contract checks.
        application = create_app(ctx, static_dir=static_dir, bind_host=args.host, port=args.port)
    uvicorn.run(
        application,
        host=args.host,
        port=args.port,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
