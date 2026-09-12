# 收尾提示词：**已无待跑项**（UI 层开放项已清零）

> **状态：本文件不再有需要执行的提示词。**
>
> - **C4「新建会议（个人日程）」落点已于 2026-09-12 关闭** —— 见
>   `OPEN-VERIFICATION-ITEMS.md` §M 第八轮。
> - B/C/D/E 各组开放项已全部关闭。
>
> 仍在清单上的只剩 **A6**（需第二台机器现场复跑；代码路径已有端到端自动化 + 变异测试覆盖）
> 与 **F1**（**非缺陷**，明确超出 `INTERNAL-DEV` 交付范围）。两者都不需要 computer use 提示词。

---

## 如果要重跑真实外部服务的写回类验收，先读这三条

第八轮在真实飞书上跑通 C4 时，查明了几条**对所有"真实写回"验收都适用**的机制。
它们不是产品缺陷，但会决定验收环境怎么搭——踩错会把测试数据永久留在真实远端。

### 1. Web 写操作会自动 commit **并 push**

`legacy_app.py` 的 `_run_web_mutation` 是**所有** web 写操作的公共入口，它**总是**传
`push_after_commit`。所以在**带远端的真实 vault** 上做写回，提交会被推送到真实远端；而
**远端历史无法用本地 `reset` 收回**（产品设计上绝不 force-push）。

⇒ **任何会产生真实写回的验收，都必须在"无远端的隔离 vault"上做。**

### 2. `HOME` 隔离会**同时切断 Keychain 访问**

`security` CLI 按 `$HOME` 解析钥匙串。临时 `HOME` 下没有 `login.keychain-db`，于是 workspace
凭据一律"找不到"（`未在 Keychain 找到 refresh_token`）。**这与 runtime 记录路径问题（第六轮）
同源**——都是"以为 `HOME` 能隔离一切"。

⇒ 要在隔离环境里用**真实凭据**，必须**保留真实 `HOME`**，只把 `vault_dir` 指到临时 vault。

### 3. 于是，正确的形态是「真实 `HOME` + 隔离 vault + 无远端 + 真实凭据」

本轮 C4 的可复现做法（**已验证**，全程不改真实 vault、不推送、事后逐字节复原）：

1. 记下真实 vault 的 `HEAD` 与相关文件哈希；备份要改的 profile `config.toml`。
2. 造一个临时 vault，其 `.summit-workbench/workspace.json` **沿用真实 `workspace_id`**
   （凭据按这个 id 解析，因此复用真实 Keychain 项、**无需复制秘密**，也不会有
   refresh_token 轮换导致真实 App 失效的风险）。
3. `git init` + 一次初始提交（工作树干净 ⇒ 不触发 `dirty-protected` 写保护），**不设 remote**
   （同步状态为 `unconfigured` ⇒ `push_after_commit` 是空操作）。
4. 用项目自己的 API 把真实 profile **临时**指向该临时 vault（`load_profile` → `model_copy` →
   `save_profile`），`HOME` 保持真实；结束后按备份复原。
5. 起服务，用 `frontend_build`、`workspace_id`、`sync state` 三项自证环境对。
6. 跑 UI 流程；**预演必须先确认零写入**（另查一次日历确认为空），再确认写回。
7. 回读事件字段并核对 `start`/`end` 与候选一致；**按 `event_id` 精确删除**
   ——不要遍历列表删除：列表里可能有别人的事件（飞书会以 `no permission` 拒绝）；
   删除成功的判定是 **`status == cancelled`**，而**不是**它从原始列表消失。
8. 逐字节复原 profile 与 vault，删除临时目录，确认无残留进程。

> 另注：`wb feishu calendar --date` 按日期过滤，是核对"当天有没有事件"的**权威**入口；
> 直接 `GET .../events` **不传时间参数时不会过滤**，会返回大量历史/已取消事件，容易被误读。
