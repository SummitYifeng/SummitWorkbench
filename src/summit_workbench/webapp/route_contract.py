"""可执行的 Web route contract snapshot 工具（P1-03）。"""

from __future__ import annotations

import inspect
import re
from typing import Any, get_args, get_origin, get_type_hints

from fastapi.routing import APIRoute

_ERROR_CODE_RE = re.compile(r"code\s*=\s*[\"']([^\"']+)[\"']")


def _request_fields(route: APIRoute) -> list[str]:
    dependant = route.dependant
    fields = [field.name for field in dependant.path_params]
    fields.extend(field.name for field in dependant.query_params)
    fields.extend(field.name for field in dependant.header_params)
    fields.extend(field.name for field in dependant.cookie_params)
    fields.extend(field.name for field in dependant.body_params)
    return sorted(set(fields))


def _request_model(route: APIRoute) -> str | None:
    """Return the primary body model name, when FastAPI exposed one."""
    try:
        parameters = inspect.signature(route.endpoint).parameters
    except (TypeError, ValueError):
        return None
    try:
        hints = get_type_hints(route.endpoint, include_extras=True)
    except (NameError, TypeError):
        hints = {}
    models: set[str] = set()
    for field in route.dependant.body_params:
        annotation = parameters.get(field.name)
        if annotation is None:
            continue
        value = hints.get(field.name, annotation.annotation)
        if get_origin(value) is not None:
            args = get_args(value)
            value = args[0] if args else value
        name = getattr(value, "__name__", "")
        if name:
            models.add(name)
    return sorted(models)[0] if models else None


def route_contract(app: Any) -> list[dict[str, object]]:
    """返回稳定、可 JSON 序列化的 route contract（不包含动态 operation id）。"""
    contracts: list[dict[str, object]] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        try:
            source = inspect.getsource(route.endpoint)
        except (OSError, TypeError):
            source = ""
        error_codes = sorted(set(_ERROR_CODE_RE.findall(source)))
        contracts.append(
            {
                "method": sorted(route.methods or []),
                "path": route.path,
                "request_fields": _request_fields(route),
                "request_model": _request_model(route),
                "response_status": route.status_code or 200,
                "error_codes": error_codes,
            }
        )
    return sorted(contracts, key=lambda item: (str(item["path"]), str(item["method"])))
