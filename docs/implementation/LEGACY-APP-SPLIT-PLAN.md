> **已归档（2026-09-19）**：`webapp/legacy_app.py` 的拆分计划（Step 0–16 + 收尾）**已全部执行完毕**，
> 原文移到 [`docs/archive/implementation/LEGACY-APP-SPLIT-PLAN.md`](../archive/implementation/LEGACY-APP-SPLIT-PLAN.md)。
> 保留本指路文件是因为 20 处源码 docstring 按此名引用 Step 编号（`routers/sync.py` 的
> 「Step 6 / Q」等）。**判断现状请看代码本身与 `AGENTS.md`，不要照归档里的行号/分工表施工。**

## 收口现状（2026-09-19，提交 `c9b3fc5`）

拆分完成后又做了两次「同一模块内的再拆分」，归档原文的分工表（R2 / R13 行）未反映：

| 原模块 | 再拆出的模块 | 行数 |
| --- | --- | --- |
| `webapp/routers/settings.py` | `webapp/routers/settings_connections.py` | 550 |
| `webapp/routers/sync.py` | `webapp/routers/sync_conflicts.py` | 324 |

再拆后：`settings.py` 600 行、`sync.py` 193 行；飞书授权状态管理另下沉到
`webapp/feishu_authorization.py`。**自动推送出口白名单随之从 `routers/sync.py` 改为
`routers/sync_conflicts.py::api_sync_conflict_recover`**（守卫：`tests/unit/test_auto_push_switch.py`）。
