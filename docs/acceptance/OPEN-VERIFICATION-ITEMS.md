# 未验证清单（单一真源）

> **这是唯一权威的「还没验证什么」清单。** 其他文档（README、验收记录、交接档案、ADR）只描述
> 各自范围内的结论并链接到这里，不再各自维护一份可能漂移的副本。
>
> 维护约定：本文件只记录**尚未取得证据**或**证据不足**的项；取得证据后把该项移入下方
> 「已关闭」并注明证据位置（提交、CI run、测试文件名）。不要在这里写计划或需求。

- 最近更新：2026-09-11
- 当前基线：`v0.4.4` build 9（前端 `v2026.09.10-df4ba1f-1cb9c2eb`），远端 CI 全绿（844→878 passed）
- 判定口径：**「历史某个 build 上验证过」不等于「当前代码已验证」**，见 A 组。

## A. 真实外部服务回归（历史验证过，当前 build 未回归）

这些链路在更早的里程碑真机通过，但 v0.4.4 代码上未重新执行。需要真实凭据，且必须在隔离环境做。

| # | 项 | 历史证据 |
|---|---|---|
| A1 | 真实云端模型调用：会议结构化、快速捕捉分类、简报排序、`wb ask` 回答 | M1/M2 验收 |
| A2 | 飞书 OAuth 全链路（authorize-url → login → token 刷新 → smoke） | M0/M1 |
| A3 | 飞书任务写回（`wb task`、面板一键完成、行内编辑） | 2026-09-03 真机核实 |
| A4 | 飞书日历写回（会议行内编辑、新建日程） | 2026-09-03 真机核实 |
| A5 | 真实远端 Git 凭据与双向同步（HTTPS remote + PAT） | P1-07D 双机验收（v0.4.3） |
| A6 | 真实双设备上的冲突恢复提交 | P2-02 build 29 双机验收 |

> A6 的**代码路径**已于 2026-09-11 由
> `tests/integration/test_acceptance_dual_device.py::test_dual_device_divergence_recovery_converges_with_two_parent_merge`
> 端到端自动化覆盖（双父提交、审计、推送、对端快进），并做过变异测试验证。仍缺的只是真实双设备现场复跑。

## B. 原生与无障碍矩阵

| # | 项 | 说明 |
|---|---|---|
| B1 | Chrome 原生 200% 缩放 | 现有证据只到 viewport override，不等同原生缩放 |
| B2 | 浅色主题 | CUA 实际只跑过深色主题 |
| B3 | 系统 `prefers-reduced-motion` | 未验证 |
| B4 | packaged App / WKWebView 黑盒 | CI 的 packaged smoke 只覆盖打包后的 server 与构建身份，**不覆盖原生 UI** |

## C. 审批边界

| # | 项 | 说明 |
|---|---|---|
| C1 | `0/1/100/101` 条完整矩阵 | 100 条上限目前只有源码级断言 |
| C2 | 「一次点击一次请求」的网络计数证据 | UI 点击观察不能替代网络层计数 |
| C3 | 部分失败 / unknown 的真实 UI 流程 | 与 C1 是两件事 |
| C4 | global inbox / 个人日程落点的完整浏览器证据 | 资格与禁用逻辑有纯渲染测试 |

## D. 导入与来源

| # | 项 | 说明 |
|---|---|---|
| D1 | 导入成功 / 部分失败 / 软预算 / 成功幂等重复 | 当前只验到「模型未配置」失败回执 |
| D2 | 来源面板异常矩阵（浏览器层） | 404 / 非 Markdown / 超长 / 路径穿越 / 符号链接越界 / workspace 隔离 |
| D3 | 正文截断提示的真实显示 | `truncated` 在 100,000–256 KiB 时的页面表现 |

## E. 交互细节

| # | 项 | 说明 |
|---|---|---|
| E1 | 冲突包导出下载的确定性证据 | In-app Browser 未观测到 download 事件 |
| E2 | 原生确认框关闭后的稳定返回焦点 | CUA 通道超时，未取得 |
| E3 | 项目可移动滚动位置恢复 | 既有 fixture 高度等于视口，无位移 |
| E4 | 动态 loopback 端口变化后的同源边界 | 跨端口草稿迁移是明确不做的独立事项 |
| E5 | R01–R14 交互断言在真实页面复验 | 源码级契约测试不算真实浏览器证据 |

## F. 发布链路

| # | 项 | 说明 |
|---|---|---|
| F1 | Developer ID / 公证 / Intel / Windows | **明确超出 `INTERNAL-DEV` 交付范围**，非缺陷 |

> tag 触发的 `release.yml` 实跑已于 2026-09-11 关闭，见下方「已关闭」。

## G. 测试覆盖洼地（代码有、测试未走到）

总体覆盖率 82.36%。以下是仍然偏低的模块；多为薄封装或需要真实外部服务，风险等级不同。

| 模块 | 覆盖率 | 备注 |
|---|---|---|
| `cli/ask.py` | 21% | 主要是真实模型链路 |
| `cli/web.py` | 24% | 拉起服务，需进程级测试 |
| `cli/model.py` | 30% | 需真实模型 |
| `cli/vault.py` | 33% | |
| `config/tls_trust.py` | 33% | TLS/CA 分支 |
| `webapp/routers/settings.py` | 42% | 设置页大量 API 分支 |
| `workflows/threadnotes.py` | 44% | |
| `cli/meeting.py` | 46% | 已由 16% 提升；余下需飞书/模型 |
| `cli/feishu.py` | 48% | 已由 20% 提升；余下需真实 API |
| `webapp/server_entry.py` / `worker_entry.py` | 0% | 由 CI packaged smoke 覆盖，非单测 |

## H. 明确不做（非缺陷，不要计入缺口）

- M3（带上下文启动与会话收尾）、P2-03（组织级云服务）——按 ADR 0044 与产品边界不实施
- 向量数据库 / Embedding / RAG
- 跨动态端口的历史与草稿迁移（需独立持久化设计）
- Intel / Windows / 公网 notarized 发行

## I. 依赖安全评估（dulwich 0.22.8）

2026-09-11 审计结论：**当前锁定版本没有任何可达的已知漏洞**，因此**不构成升级驱动**。
交叉验证：GitHub 依赖图已建立（122 个包，含 `dulwich 0.22.8`），Dependabot 告警数为 **0**，
与手工结论一致（不是"尚未扫描"）。

| CVE | 受影响范围 | 攻击面 | 本项目可达 |
|---|---|---|---|
| CVE-2026-52726 | 0.23.2 – 1.2.4 | submodule 路径穿越 → RCE | 否：0.22.8 不在范围，且不使用 submodule |
| CVE-2026-42563 | 0.24.0 – 1.2.4 | merge driver `shell=True` 注入 → RCE | 否：0.22.8 不在范围，且无 merge driver |
| CVE-2026-47712 | 0.24.0 – 1.2.4 | `format_patch` 路径穿越 | 否：0.22.8 不在范围，且不使用 |
| CVE-2026-47734 | 0.1.0 – 1.2.4 | thin pack 内存放大 DoS | 否：需 dulwich **服务端**接收 push，本项目纯客户端 |
| CVE-2026-38974 | ≤ 1.1.0 | 缺 SSH host key 验证 | 否：dulwich 侧不走 SSH，生产同步限 HTTPS |

代码面核验（全 `src/` grep）：无 `ReceivePackHandler` / `dulwich.server`、无 submodule、
无 `format_patch`、无 merge driver 与 `shell=True`、`dulwich_git.py` 无 SSH。

**技术债（非安全驱动，可延后）**：`pyproject.toml` 钉 `dulwich>=0.22,<0.23`，上界使安全补丁
永远无法流入。将来升级到 1.2.5+ 时需：修 `dulwich_git.py:831` 的 `type: ignore[attr-defined]`
（补 `union-attr`），并跑全量 + 冲突恢复端到端 + packaged smoke。1.0 起官方承诺 2.0 前不破坏兼容。

## 已关闭（保留证据指针）

| 项 | 关闭日期 | 证据 |
|---|---|---|
| 远端 CI 从未真正运行 | 2026-09-11 | 仓库迁移到 `SummitYifeng/SummitWorkbench`；quality-gate + arm64/x86_64 矩阵 + workflow lint 全绿 |
| `packaged App smoke` 从未纳入 CI | 2026-09-11 | `ci.yml` arm64 构建矩阵 `WB_PACKAGED_APP` 步骤 |
| macOS framework Python 下 runtime record 身份误判 | 2026-09-11 | `src/summit_workbench/webapp/runtime.py` + `tests/unit/test_runtime_record.py` 回归测试 |
| 冲突恢复提交无自动化端到端覆盖（A6 的代码路径部分） | 2026-09-11 | `tests/integration/test_acceptance_dual_device.py`（变异测试验证有效） |
| Node 20 弃用告警 | 2026-09-11 | action 升级到 node24 大版本，告警清零 |
| 「本地绿、CI 红」反复发生 | 2026-09-11 | `scripts/pre-push-gate.sh` + `scripts/check-action-refs.sh` + pre-push hook |
| `release.yml`（tag 触发）从未在组织下实跑 | 2026-09-11 | `v0.4.4-rc.1` 运行成功：签名 DMG + `update-feed.json` + SBOM + SHA256SUMS 全部产出，作为 **prerelease** 发布到公开 Updates 仓库；`latest` 仍为 `v0.4.2`，rc 未污染 stable 通道；证明最小权限 `contents: read` 与升级后的 action 在发布路径同样可用 |
| 冲突恢复无法在 CI 中验证 | 2026-09-11 | `test_dual_device_divergence_recovery_converges_with_two_parent_merge` 随全量测试在 CI 运行 |
| 依赖漏洞无人监控（CVE 可能静默存在） | 2026-09-11 | 开启 Dependabot **alerts** + **security updates**（`automated-security-fixes.enabled = true`）；依赖图 122 个包，当前告警 0 |
| `v0.4.4-rc.1` 测试产物遗留在公开渠道 | 2026-09-11 | 已删除 prerelease 与本地/远程 tag；`latest` 保持 `v0.4.2` |
