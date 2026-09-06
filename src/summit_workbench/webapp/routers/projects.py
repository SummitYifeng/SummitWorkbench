"""Projects 路由边界。

当前 handler 仍由 legacy compatibility bundle 注册；本模块声明领域边界，避免新路由
继续堆回公开 app 入口。既有行为稳定后，按同一 ``RouteDependencies`` 迁移 handler。
"""

ROUTE_PREFIXES = ("/api/projects",)

__all__ = ["ROUTE_PREFIXES"]
