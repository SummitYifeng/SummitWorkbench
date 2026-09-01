# ADR 0016 · 工作区级跨进程锁（韧性加固 LHF #1）

- 状态：✅ 已实现并合并（离线全绿：ruff + mypy --strict + pytest 301 项）
- 日期：2026-09-01
- 里程碑：韧性加固（低垂果实 LHF #1；非新功能，兜底既有并发写路径）
- 依据：底层韧性评审「文件并发读写与 git 同步竞态」「macOS Keychain 容错」两维度；
  NFR-3（git remote 唯一真源、非破坏性）、NFR-4（凭据只在运行时按需从 Keychain 取）、
  NFR-6（失败必须可见，不静默吞错）

## 背景与问题（要根治的故障类）

系统有多个 **互不知情** 的写入触发源会同时改动共享持久状态：

- `launchd` 定时任务 `com.summitworkbench.brief`（每日 08:00）、`com.summitworkbench.weekly`（周一 07:30）；
- 手动 CLI（`wb brief` / `wb weekly` / `wb sync` / `wb ask` / `wb meeting …`）；
- 本地 Web 面板「一键触发」（`/run/brief`、`/run/weekly`、`/ask`）。

它们在无任何互斥的情况下并发地做两类操作，构成两条真实竞态：

1. **飞书 `refresh_token` 轮换自毁**。`FeishuSession.access_token()` 是一段
   `读 Keychain 里的 RT → POST 刷新 → 写回新 RT` 的 read-modify-write；飞书
   refresh_token **单次轮换**，刷新成功后旧 RT 立即作废。两个进程同时进入这段会
   拿到同一个 RT，其中一个刷新后令另一个手里的 RT 失效，随后互相覆盖写回 Keychain，
   最终 **Keychain 里存成一个已作废的死 token** → 下一趟所有飞书任务失败，必须人肉
   `wb feishu login` 重新授权。后台定时任务能就此悄悄弄砖前台授权，属最难排查的一类。

2. **git 写序列交错**。`workflows/brief/publish.py::publish_brief` 的
   `add → commit →（push）` 与 `workflows/sync.py::sync_work_root` 的
   `fetch → ff-merge → push` 都跨多条 git 命令。git 自身的 `index.lock` 只能保护单条
   命令，保护不了「读 ahead/behind → 决策 → 写」这个跨命令窗口；两个触发源并发操作
   同一个 `_vault` 仓库时存在交错风险。

（`config/secrets.py` 已把秘密值以 `SecretStr` 承载、异常不含秘密值；单文件写回
`writeback.py` / `daily_note.py` 已用 tmp + `os.replace` 原子落盘——这些不在本 ADR 的
改动面内，但正是它们让「跨进程序列」成为剩下的主要缺口。）

## 决策

给「所有会改动共享持久状态的临界区」加一道 **工作区级** 总闸，而不是逐函数打补丁——
一处基础设施，根治一整类并发故障。

- **单锁、单文件**：锁文件固定在 `<work_root>/.wb.lock`，用 `fcntl.flock` 做独占咨询锁。
  默认 `work_root` 取 `config.paths.resolve_work_root()`（`WORK_ROOT` 环境变量或
  `$HOME/Documents/Work`）。序列化的是「整个 wb 进程的写动作」——单用户本地工具下这是
  正确粒度。锁文件位于 work_root（各仓库之上），不落在任何被 git 跟踪的仓库内。
- **零新增依赖**：`fcntl` 为标准库，macOS 原生支持。满足「新增外部依赖不超过 1 个」的上限
  （本 ADR 用 0 个）。
- **带超时，绝不无限挂起**：`launchd` 任务必须能终止。默认阻塞等待有限时长
  （`_DEFAULT_TIMEOUT = 60s`，非阻塞轮询实现），超时抛 `LockBusy`，由调用方转成
  **可见状态** 而非静默卡死（NFR-6）。`timeout=None` 表示无限等待，`timeout=0` 表示只试一次。
- **按线程重入，避免自锁死**：`flock` 的锁与「打开文件描述」绑定，同一进程用不同 fd 再次
  `LOCK_EX` 会自锁死。真实调用链存在 **同线程嵌套**（Web endpoint → `run_brief` →
  `FeishuSession.access_token`）。故用 **线程内** 重入计数：同线程已持有则直接放行、不再
  真正 flock；而 uvicorn 里 **不同线程** 的并发请求各自 `open` 独立 fd，仍在内核层互斥、
  被正确串行化。

## 实现

- 新增 `src/summit_workbench/config/locking.py`：
  - `workspace_lock(work_root=None, *, timeout=60.0, sleep=time.sleep)` 上下文管理器；
  - `LockBusy` 异常（超时未获取）；
  - 按 `(thread_id, 锁文件规范路径)` 记账的进程内重入表。
- 接入 3 处临界区（改动最小、语义不变）：
  - `providers/feishu/session.py`：`access_token()` 的整段 read-modify-write、以及
    `complete_authorization()` 的 `store_credential` 都圈入 `workspace_lock()`。
  - `workflows/brief/publish.py`：`publish_brief` 的 `add→commit→push` 圈入
    `workspace_lock(vault_dir.parent)`；锁忙时返回新增的 `PublishStatus.BUSY`。
  - `workflows/sync.py`：`sync_work_root` 整批圈入 `workspace_lock(work_root)`；锁忙时
    返回单条 `SyncStatus.BUSY`（`is_problem=True`，可见、可等下次触发，幂等无副作用）。
  - 正常布局下三者（`resolve_work_root()`、`vault_dir.parent`、`work_root`）解析到同一把
    `<work_root>/.wb.lock`，从而 git-vs-git、token-vs-token 均互斥。

## 验收

- Ruff + mypy --strict（100 源文件）+ pytest **301 项全绿**。
- 新增 `tests/unit/test_locking.py`：正常获取/释放、跨「打开文件描述」真实互斥、
  同线程重入不自锁死、内层退出不提前释放、跨线程互斥、超时三态（立即失败 / 等待后获得 /
  超时抛 `LockBusy`）、`WORK_ROOT` 缺省解析。
- 现有 `tests/unit/test_feishu_session.py` 补 `WORK_ROOT` tmp 隔离，防止锁落到真实 home。

## 稳定性收益

- 飞书 refresh_token 并发自毁：从「触发窗口重叠即可能发生、每次代价是人肉重新授权 +
  期间所有飞书任务失败」→ **0**。
- `_vault` 仓库跨命令写序列交错 / index.lock 撞车：多触发源下的仓库损坏窗口 → 消除。
- 附带：`LockBusy` / `BUSY` 状态把「为什么两个任务一起跑就出问题」的幽灵故障变成一行
  可见结果。

## 遗留（同批评审识别出的其余低垂果实，未在本 ADR 内实现）

- **LHF #2**：追加型 JSONL 日志（`repositories/meeting_state.py`、`usage_ledger.py`）的
  容错读 + Pydantic 逐行兜底。当前 `json.loads(line)` 裸调用，一条半截行（进程被 kill /
  磁盘满 / 断电导致最后一行未闭合）会让 **整本** 读取 `JSONDecodeError` 崩溃；且 `_task_from_row`
  用 `row["…"]` 硬索引，缺键即 `KeyError`。对策：逐行 `model_validate_json`，坏行跳过 +
  隔离 + 告警。
- **LHF #3**：飞书 HTTP 客户端复用 LLM 客户端已有的重试/退避策略并尊重 `Retry-After`。
  `providers/llm/client.py` 已有指数退避重试（超时/429/5xx），而 `providers/feishu/client.py`
  与 `auth.py` 仍是 **单发**——一次瞬时抖动即让整趟拉取报废。对策：抽公共 `send_with_retry`
  两处共用，并给长驻客户端设 `keepalive_expiry` 防复用半开连接。
