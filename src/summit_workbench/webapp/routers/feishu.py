"""Feishu/外部动作路由边界；既有 handler 暂由兼容 bundle 承载。"""

ROUTE_PREFIXES = ("/api/external-actions", "/api/meetings", "/api/tasks")

__all__ = ["ROUTE_PREFIXES"]
