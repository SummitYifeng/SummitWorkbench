# ADR 0041 · P1-07D 远端规范化与一次性双设备验收

- 状态：进行中；最近已发布 `v0.4.3-rc.5`，其后的 packaged TLS 修复待进入新 RC，再做 Studio + Air 真机闭环
- 日期：2026-09-06（2026-09-07 更新 TLS 阻塞处理）
- 范围：P1-07D；不进入 P2-01B，不迁移 inbox、会议决策或项目正文

## 背景

v0.4.2 的 packaged App 暴露了 Dulwich clean-worktree 判定错误。随后确认现有工作台的
origin 仍是 GitHub SSH remote。生产同步必须有一个可验证、可诊断且与开发环境一致的远端
契约，不能把 SSH/scp-style URL 混同为离线或远端不可达。

## 决策

1. 生产 backend 固定为 Dulwich，生产 remote 只接受 HTTPS。其它 scheme 返回稳定错误
   `remote_scheme_unsupported`，同步状态与迁移门均保留该语义。
2. 设置中心提供 preview/apply/rollback 事务。preview 在临时 clone 中验证 PAT 认证、仓库
   身份、workspace marker、branch/upstream、fetch 与 ahead/behind；apply 重新验证后才更新
   origin、本机 profile 和 workspace-scoped Keychain。事务不提交、不推送、不改 vault，失败
   恢复旧 URL/profile，事务记录绝不含 PAT。旧 schema 的只读保护对这三个受控端点例外，
   以打破“迁移要求 HTTPS、转换又被只读拦截”的循环；其它 vault/profile 写入仍被只读保护。
3. acceptance preflight 是只读门：检查 App/build、生产 backend、remote scheme、凭据、
   system Git 与 Dulwich dirty 结果、fetch、ahead/behind、schema 路径、备份可写性和
   automation role，并返回可复制脱敏报告。
4. 双设备自动验收使用两个临时 HOME、两个 clone 和临时 bare remote，覆盖 v1→v2、提交推送、
   fast-forward、双端离线追加、恢复联网、non-fast-forward/diverged-protected、数据保留与
   迁移失败回滚；dirty 回归覆盖 ignored directory、真正未跟踪文件和已跟踪删除。
5. `v0.4.3-rc.N` 只进入 draft/prerelease 渠道，feed 使用 tag-specific URL，不更新 `latest`。
   候选包完成 packaged integration 与双设备自动验收后，再由用户做唯一一次 Studio/Air 真机
   验收。稳定 `v0.4.3` 必须从同一 RC DMG 原资产晋升，哈希不变，禁止重新构建。
6. 若 App 被强制退出而遗留自有 server，下一次启动只在 runtime record 与当前 bundle
   server 可执行文件精确匹配时终止该孤儿进程并重新启动；未知进程仍绝不接管或终止。

## 安全边界

PAT 只在请求生命周期内以 `SecretStr` 传递，绝不进入 URL、profile、事务记录、日志、报告或
仓库。公开更新仓库只提供 DMG/feed 的完整性（Ed25519、大小和 SHA-256），不提供保密性；
任何私有 workspace 内容都不得放入公开更新仓库。

## 未决外部验收

`v0.4.3-rc.5` 的 tag `a6e1e12` 早于 TLS 修复提交，因此当前已安装的 rc.5 不能作为最终
验收候选。需先从包含 `ba946b9..ee30db4` 的当前源码生成新 RC；用户再在 Studio 输入 GitHub
username 与 workspace-scoped PAT，点击 preview/apply（如需可 rollback），随后在 Air 完成
一次引导式往返同步。只有该验收成功后，才允许将完全相同的 RC DMG 晋升为稳定 `v0.4.3`。

## 2026-09-07 · packaged TLS 阻塞处理

- 根因：PyInstaller server 使用的 Python/OpenSSL 编译期 `OPENSSLDIR` 指向未随 bundle 分发
  且本机不存在的 python.org framework 证书目录；Dulwich/urllib3 默认加载不到可信根，因此
  GitHub 证书校验失败。系统 Git 使用 macOS SecureTransport/Keychain，不受同一缺口影响。
- 源码修复：`config/tls_trust.py` 统一选择 certifi → frozen `_MEIPASS` → OpenSSL 默认 CA；
  server/worker 入口设置 `SSL_CERT_FILE`，Dulwich HTTPS transport 同时显式传入 CA bundle，
  TLS 校验始终保持开启。错误分类仍严格区分 TLS、认证与网络不可达。
- 离线/源码证据：TLS/凭据/打包契约相关 32 项测试通过；全库 778 passed、1 skipped，ruff、
  format、mypy 通过；同一 HTTPS pool manager 对 GitHub 的真实 TLS 握手返回 200。
- 尚未验证：修复尚未进入任何已发布 tag/DMG，故不能据此宣称 packaged App 真机问题已闭环。
  下一证据必须来自新 RC 的 Studio 真实 preview/apply；其后才执行 Air 往返同步。

## 操作顺序

旧 schema 工作区应先在设置中心完成 HTTPS remote 预览与转换，再点击“升级工作区 schema”。
转换成功后重新加载设置页，确认工作区状态为 ready，再执行 schema 迁移；迁移前仍不得有
未提交改动、ahead/behind 或不可达远端。
