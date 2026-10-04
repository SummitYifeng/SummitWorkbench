# 文档导航

此页说明各类文档的用途与优先级。当前项目状态见仓库根目录 [README.md](../README.md)；仓库专有约束见 [AGENTS.md](../AGENTS.md)。

## 当前契约与计划

- [工作库契约 v1](contracts/SWB-WORKSPACE-CONTRACT-v1.md)：0.5.0 工作库身份、内容资格、写入和同步边界。
- [四阶段工作台实施计划](implementation/ONEDRIVE-WORKBENCH-IMPLEMENTATION-PLAN.md)：Phase 1–4 的顺序、范围与阶段门。当前 Phase 1、Phase 2 已完成用户确认；Phase 3 尚未开始。
- [W0 接口与写入盘点](implementation/ONEDRIVE-W0-FROZEN-INTERFACE-AND-WRITE-INVENTORY.md)：实施接口与副作用清单。
- [检索契约](contracts/WORK-KB-RETRIEVAL-CONTRACT.md)：SWB 与 SummitKnowledge 的共享引用、状态和权威顺序约定。
- [Web 工作台使用指南](product/WEB_USAGE_GUIDE.md)：0.5.0 日常界面入口与操作说明；涉及旧工作库行为的段落会标明适用版本。
- [OneDrive 样板库快速说明](product/ONEDRIVE-SAMPLE-QUICKSTART.md)：当前样板库材料和验收使用说明。

## 阶段与环境验收

- [Phase 1 报告](acceptance/SWB-WORKBENCH-PHASE1-REPORT.md)：W0–W8 隔离实施与验收证据。报告中的包身份是当时记录，不代表当前安装包。
- [Phase 2 报告](acceptance/SWB-WORKBENCH-PHASE2-REPORT.md)：OneDrive 样板验收的原始过程，以及 2026-10-04 用户确认完成阶段门的后续记录。
- [0.5.0 Studio → Air → Studio 验收指路](acceptance/STUDIO-AIR-0.5-ACCEPTANCE.md)：Phase 3 启动条件、OneDrive 交接流程与通过证据。
- [旧安装清单](acceptance/FRESH-INSTALL-STUDIO-AIR.md)与[旧双机演练](acceptance/DUAL-DEVICE-REHEARSAL.md)仅供 0.4.x 历史参考，不是 0.5.0 操作指令。
- [未验证清单](acceptance/OPEN-VERIFICATION-ITEMS.md)：0.4.x 历史清单与当前未验证事项的分界说明。旧清单中的历史状态不代表 0.5.0 阶段状态。
- 其它 `acceptance/` 报告按文件名和报告内的日期、版本阅读；报告保留各自当时的事实，不覆盖更新的确认记录。

## 产品说明与交付

- `WEB_USAGE_GUIDE.md` 与 `ONEDRIVE-SAMPLE-QUICKSTART.md` 服务当前 0.5.0 产品；`WEB_WORKBENCH.md` 是 v0.4.9 时代的设计说明，供历史背景参考，不作为当前行为说明。`PRD.md` 记录 0.4.x 产品规格与背景；0.5.0 工作库行为以工作库契约和当前实施计划为准。
- [桌面 App 构建说明](DESKTOP_APP.md) 与 [发布说明](RELEASING.md) 描述源码仓库的构建和发布。
- [变更记录](../CHANGELOG.md) 记录各版本交付；`AGENTS.md` 中 0.4.x 包身份数据是已发布历史。

## 历史资料

- `archive/` 保存已完成阶段的背景、旧计划、旧验收和历史快照。文件内的旧结构、旧路径和旧验收结论不作为当前实现依据；保留原文以维护历史。
- `decisions/` 当前索引与决策用于解释已选实现。涉及 0.5.0 行为时，以工作库契约与当前阶段计划为准。
- `implementation/LEGACY-*-SPLIT-PLAN.md` 是历史模块拆分指路 stub；只有其“收口现状”用于定位当前代码，其余记录按历史材料阅读。

## 冲突时的判定顺序

1. 0.5.0 工作库行为：工作库契约与当前实施计划。
2. 当前阶段是否通过：阶段报告中较新的、带日期和证据来源的确认记录。
3. 界面行为：当前使用指南与实现。
4. 0.4.x 产品行为：PRD、旧验收报告和 `archive/` 历史材料。

对真实工作库的结构或内容判断，以其 `conventions.md` 与实际内容为准；仓库文档不能替代工作库真源。
