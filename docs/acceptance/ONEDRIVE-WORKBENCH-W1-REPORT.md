# OneDrive Workbench W1 工作包报告

- 日期：2026-10-03
- 范围：文件夹初始化身份校验、旧工作库显式连接／升级、活动写入与会议 worker 的切库屏障。
- 状态：**源码实现与隔离回归通过；最终 arm64 包级和 W8 实机复验留到 W7/W8。**

## 实现

- 活动工作区必须同时具有匹配 profile 的旧版 workspace marker、新版便携契约 marker 和非空、可读的 `conventions.md`。缺失、损坏或身份不匹配时不按路径生成身份，不进入业务上下文，应用只提供受限 onboarding 控制面。
- 旧工作库升级／显式连接会写入便携契约；保留已有 `conventions.md` 原文。升级回滚会移除本次新建的 marker，并保留原有文件。
- 切换准备先停止接受新 mutation，再等待已开始的 mutation 完成。会议导入 manager 同样暂停接收和重试，等待正在处理的任务；超时会取消切换并恢复旧工作区服务。
- 更新旧 Git 测试夹具，使隔离库显式包含便携契约；旧 schema 现在验证为拒绝业务打开并提供 onboarding 控制面，不再以只读业务上下文暴露已退役的迁移入口。

## 检查

- 针对性回归：`pytest -q tests/unit/test_sync_coordinator.py tests/unit/test_workspace_migration.py tests/unit/test_active_profile_runtime.py tests/unit/test_meeting_import_jobs.py tests/unit/test_profile_settings.py tests/unit/test_onboarding.py`：**67 passed**。
- 全量 Python 回归：`pytest -q`：**1373 passed, 1 skipped**；跳过项为需设置 `WB_PACKAGED_APP` 的打包 App smoke。
- `ruff check`、`ruff format --check`、`mypy src`（229 个源文件）和 `git diff --check` 通过。
- `npm --prefix web run test:frontend` 通过（浏览器契约扫描 70 个源码文件）。
- 所有工作区变更只在仓库和 pytest 临时目录中进行；没有写入或推送真实旧 `_vault`，没有连接旧 SK、触发全量嵌入或创建真实飞书任务。

## 缺口与下一步

- 当前临时 0.5.0 包早于本 W1 修改，不能作为 W1 交付包；W7 将从最终源码重建 arm64 包、检查内置飞书凭据和包级隔离 smoke，W8 将验证最终包行为。
- 本次验证了切换时 mutation／会议 worker 的并发屏障和取消分支；最终 UI 切换仍由 W8 在隔离工作区复核。
- 样板库六篇正式内容的当前版本均已由用户在 UI 批准，独立只读校验全部通过；这属于内容审批确认，不替代 W1 包级门槛。
