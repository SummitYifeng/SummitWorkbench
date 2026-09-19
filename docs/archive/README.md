# 历史文档归档

> **归档标注（适用于本目录下每一篇文档）**
> 这里是**历史记录，其中的结论可能已经过期**。归档只代表"当时这么想过/这么做过"，
> 不代表它现在仍然成立，也不代表它已经被删除。
> **当前状态请以 [`docs/acceptance/OPEN-VERIFICATION-ITEMS.md`](../acceptance/OPEN-VERIFICATION-ITEMS.md)
> 为准**——那是"还没验证什么"的唯一权威；产品边界以 `docs/product/`、当前 ADR 和最新验收记录为准。
> 本目录内容**只读**：新结论请写进 `docs/product/`、`docs/decisions/` 或 `docs/implementation/`，
> 不要就地改写历史记录。

这里保存已经完成、被新规格取代或只用于复盘的历史材料。归档不表示内容被删除，也不表示其中的结论仍然有效；当前实现与产品边界以仓库根目录说明、`docs/product/`、`docs/decisions/`、最新验收记录和当前实施记录为准。

## 目录

- `background/`：早期思考与需求再发现记录。
- `architecture/`：v0.1 架构示意图。
- `plans/`：已完成的开发、生命周期、多设备产品化计划，以及已执行完毕的下一轮交付/清理交接说明。
- `acceptance/`：已完成的 P2-02 build 25–29 现场 runbook。
- `implementation/`：已完结的增量实施、交接与会话快照（2026-09-19 从 `docs/implementation/` 整体归位，共 16 篇；其中 `LEGACY-APP-SPLIT-PLAN.md` / `LEGACY-MAIN-SPLIT-PLAN.md` 在 `docs/implementation/` 留有指路 stub，因为源码 docstring 与测试注释按那两个路径引用）。
- `design/`：简报 v2 的历史静态预览。
- `audits/`：冗余审计与执行方案。
- `decisions/`：ADR 0001–0042 的历史决策记录；当前保留的 ADR 文件在 `docs/decisions/`。

> 归位说明（2026-09-19）：`implementation/` 下的文档在移动时只做了**相对链接重写**（例如
> `../acceptance/…` → `../../acceptance/…`），正文一字未改；其中引用的行号、行数与模块分工
> 都是**当时**的快照，现已过期，**不要照它们施工**。当前结构见 `AGENTS.md` 与代码本身。

需要引用历史事实时，请直接链接到这里的归档路径，并在正文中标注“历史”或“非权威”；不要从归档文档恢复已经被 PRD、ADR 或当前代码推翻的设计。
