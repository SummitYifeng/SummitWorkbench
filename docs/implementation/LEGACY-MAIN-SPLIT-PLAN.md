> **已归档（2026-09-19）**：`web/src/legacy-main.ts` 的拆分目标（原 3346 行 → 步骤 9 的 964 行）
> **已达成**，原文移到 [`docs/archive/implementation/LEGACY-MAIN-SPLIT-PLAN.md`](../archive/implementation/LEGACY-MAIN-SPLIT-PLAN.md)。
> 保留本指路文件是因为 3 个测试的注释按此路径引用（前端源码聚合读取的由来）。
> **判断现状请看代码本身与 `AGENTS.md`，不要照归档里的行号施工。**

## 收口现状（2026-09-19，提交 `c9b3fc5`）

归档原文 §C.7 记的收口状态是 **964 行**；此后又下沉三处动作，现为 **922 行**：

| 下沉内容 | 新模块 | 行数 |
| --- | --- | --- |
| 诊断动作 | `web/src/features/diagnostics.ts` | 84 |
| 项目与审批表单动作 | `web/src/features/projects/actions.ts` | 68 |
| 审批表单动作 | `web/src/features/review/actions.ts` | 286 |

`legacy-main.ts` 现在只剩类型契约、跨域状态、`render()`、全局 click/submit 派发与
`mountLegacyWorkbench`；本批同时更新了 `web/scripts/test-browser-contract.mjs` 的位置守卫。
