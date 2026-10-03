# OneDrive Workbench 第一阶段单机验收记录

- 验收日期：2026-10-03
- 应用：SummitWorkbench 0.5.0 INTERNAL-DEV，arm64，build `2026100304`
- 源码提交：`cffd8f9a79aa2aeb1fcc86694aa67ef7d201d471`
- 前端身份：`v2026.10.03-4084a225`
- 临时安装包：`/tmp/swb-review-release-20261003-switchfix/0.5.0/arm64/SummitWorkbench-0.5.0-arm64-INTERNAL-DEV.dmg`
- DMG SHA-256：`3abd3ad240c06dbb93fc916a8c1f2ebeffb24749c3642dbef1b874c698b7fc4c`
- 发布元数据：同目录 `release-metadata.json`、`SBOM.json`、`test-manifest.json`

## 已实现与验收

- 审批队列只读列出工作库内 `pending-review` 的正式内容版本，并按当前内容摘要锁定版本；不把来源副本、内部目录或未知类型放入队列。
- 审批页提供路径、类型、摘要和可展开正文；批准需要用户在界面逐篇确认，成功后以原子写入添加批准证明并转为正式状态。此流程不创建飞书任务。
- 修复工作台切换接口：prepare 与 commit 两次 JSON POST 均显式发送 `Content-Type: application/json`，并增加浏览器契约守卫。
- 已从旧工作库切换到 OneDrive 样板工作库，设置页显示路径 `/Users/yifengair/Library/CloudStorage/OneDrive-个人/_vault`。
- 实机打开“审批”页，确认列出 6 篇待确认正式内容：项目主页、两家酒店页、场地成本模型、成本决定、9 月成本核对草稿。
- 当前版本未执行批准；OneDrive 页面保持待确认，供用户逐篇审阅。未创建飞书任务。

## 检查结果

- `pytest tests/unit`：1273 passed，5 warnings。
- Web 路由契约：2 passed。
- 前端契约、渲染与浏览器交互检查：全通过（70 个源码文件）。
- Ruff 格式与 lint：通过；mypy：229 个源码文件通过。
- 发布检查：68 passed；发布清单 13 项状态为 passed；打包服务集成 smoke：1 passed。
- DMG 校验和已生成并与发布元数据一致。
- 飞书完整默认凭据已从现有安装包按 `docs/RELEASING.md` 安全提取并构建期内置；本次未执行飞书联网检查。

## 边界与未完成项

- `2026 年 9 月宿心集场地成本核对草稿`金额仍为空并标注待活动结束后核对；用户应先审阅正文，再决定是否批准当前版本。后续核算金额时，内容版本变化会要求重新批准。
- 连接状态显示 DeepSeek 与飞书凭据已配置，但未现场联网验证。
- 本次仅在 OneDrive 新样板库执行只读审批列表检查；未修改真实旧 `_vault`，未连接旧 SK，未触发全量嵌入，未创建自动测试用飞书任务。
- `INTERNAL-DEV` 包没有更新 feed；未安装覆盖 `/Applications/SummitWorkbench.app`。当前正在运行的临时 0.5.0 实例连接 OneDrive 样板库并停留在审批页。
- 下一步由用户逐篇审阅并亲自点击“批准当前版本”；批准后再做后续阶段验收。
