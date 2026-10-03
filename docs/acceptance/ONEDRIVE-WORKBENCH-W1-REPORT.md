# OneDrive Workbench W1 工作包报告

- 日期：2026-10-03
- 范围：文件夹初始化身份校验、旧工作库显式连接／升级、活动写入与会议 worker 的切库屏障。
- 状态：**源码实现、隔离回归和最终 arm64 打包 smoke 通过；W8 主要 UI 实操记录沿用同版本 build `2026100302`，最终包的切库并发路径由 W1 单测验证。**

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
- W7 最终 arm64 包：[/tmp/swb-phase1-final-release-20261003/0.5.0/arm64/SummitWorkbench-0.5.0-arm64-INTERNAL-DEV.dmg](/tmp/swb-phase1-final-release-20261003/0.5.0/arm64/SummitWorkbench-0.5.0-arm64-INTERNAL-DEV.dmg)，build `2026100305`、源码 `b70669177a33a76c1ffe08539075728329fe62e6`、前端 `v2026.10.03-4084a225`；App SHA-256 `69ca8da98f32dfeac84caeec093fd9c5b40ace67606decffba497068fcc5a6e5`，DMG SHA-256 `b929852a1bfed65a8d2d968576f601af500265da1ce3deeff337c218ae1f5a6d`。
- 包内飞书 App ID / App Secret 结构完整；凭据从现有安装包提取到临时 `0600` env 文件，构建后已删除；没有输出或提交 secret 值。
- 所有工作区变更只在仓库和 pytest 临时目录中进行；没有写入或推送真实旧 `_vault`，没有连接旧 SK、触发全量嵌入或创建真实飞书任务。

## 缺口与下一步

- 最终 build `2026100305` 的打包服务集成 smoke、安装包签名结构和凭据完整性检查通过；该 build 尚未覆盖安装到 `/Applications`，现有 OneDrive 样板工作区和正在运行的 App 均未改变。
- 切换时 mutation／会议 worker 的并发屏障和取消分支由隔离单测验证；最终包上的 UI 切换动作没有单独复做，避免将用户已打开的 OneDrive 样板挂到额外测试进程。
- 样板库六篇正式内容的当前版本均已由用户在 UI 批准，独立只读校验全部通过；这属于内容审批确认，不替代 W1 包级门槛。
