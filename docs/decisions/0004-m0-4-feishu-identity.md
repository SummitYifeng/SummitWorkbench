# ADR 0004 · M0-4 飞书身份与权限

- 状态：已执行（骨架与鉴权链路），会议纪要读取端点待 M0-10 实测固定
- 日期：2026-08-31
- 里程碑：M0-4（飞书身份与权限）
- 依据：`docs/plans/DEVELOPMENT_PLAN.md` §5 M0-4；PRD NFR-4 / L14；PRD §6 M0-8、M0-10

## 已核实的端点（官方文档，2026-08）

| 用途 | 方法 / URL |
|---|---|
| 用户授权取 code | GET `https://accounts.feishu.cn/open-apis/authen/v1/authorize` |
| 授权码换令牌 | POST `https://open.feishu.cn/open-apis/authen/v2/oauth/token`（`grant_type=authorization_code`）|
| 刷新令牌 | POST 同上（`grant_type=refresh_token`）|
| 鉴权冒烟（稳定） | GET `https://open.feishu.cn/open-apis/authen/v1/user_info` |

关键约束：
- 只有 scope 含 **`offline_access`** 才返回 refresh_token。
- **refresh_token 单次有效并轮换**：每次刷新返回新值、旧值立即失效，因此刷新后必须回写 Keychain。
- 令牌以 `Bearer` 放入 Authorization 头；业务响应信封 `{code,msg,data}`，`code!=0` 即失败。

## 最小权限（NFR-4，`[feishu].scopes` 可覆盖）

`calendar:calendar:readonly`（日历只读）、`task:task`（任务读写）、`vc:meeting:readonly`（会议只读）、
`minutes:minutes:readonly`（纪要只读）、`docx:document:readonly`（纪要正文文档只读）、`offline_access`。
不申请消息、多维表格、通用文档写。`vc`/`minutes` 的精确标识须与开放平台「应用权限」列表核对。

## 凭据模型（NFR-4）

- 非敏感项（app_id、redirect_uri、scopes）进本机 `config.toml` 的 `[feishu]` 表。
- 敏感项只以 Keychain 引用出现：`app_secret`（service `summit-workbench-feishu-app-secret`）、
  `refresh_token`（service `summit-workbench-feishu-refresh-token`），account 均为 app_id。
- 代码只存引用、运行时解析为 `SecretStr`，绝不入 git / 日志 / 模型上下文。
- `wb feishu login` 授权后写入 refresh_token；`access_token()` 每次刷新回写轮换后的新 refresh_token。

## 交付（SummitWorkbench 仓库）

- `providers/feishu/`：`config`（配置+凭据引用）、`errors`（显式错误，NFR-6）、`auth`（授权 URL /
  换取 / 刷新）、`session`（凭据编排 + refresh_token 轮换回写）、`client`（信封解析）、
  `meetings`（`verify_identity` 鉴权冒烟 + `import_local_transcript` 本地兜底 + `FeishuNoteSource` 骨架）。
- CLI `wb feishu`：`authorize-url` / `login --code` / `smoke` / `import-local`。
- 契约测试用 `httpx.MockTransport`，覆盖授权 URL、换取/刷新（含轮换与失效重授权）、信封错误、
  会话回写、本地兜底；**无任何真实调用、无凭据**。
- `config.example.toml` 示例与 Keychain 命令模板。

## 刻意推迟（不臆造）

**飞书会议纪要读取端点未在本批固定**。普通纪要经 `verbatim_doc_token` 文档读取、统一纪要经 Note
transcript 接口、妙记经 `minute_token`——端点与响应因租户与纪要类型而异（PRD L14）。按 M0-10
「用一场真实历史会议验证 `meeting_id → note_id → 完整文本`」的要求，这些端点在真实租户实测后再固定，
届时实现 `FeishuNoteSource.fetch_transcript`。在此之前该方法**显式报错并指向本地兜底**，绝不返回伪造结果。

## 验收对照（M0-4 / M0-8 / M0-10）

- ✅ 用户身份授权 + 最小权限 + refresh_token 刷新链路：已实现并契约测试覆盖。
- ✅ 凭据仅存 Keychain / 运行环境：代码只存引用，密钥保护测试通过。
- ✅ 权限清单与 PRD 一致。
- ✅ 鉴权冒烟可重复、可审计：`wb feishu smoke`（user_info）。
- ⏳ `meeting_id → note_id → 完整文本` 冒烟：待用户完成授权（`login` 取得 offline_access token）
  并提供一场真实历史会议后，于 M0-10 实测；Note API 不可用则记录原因并走已就绪的本地导入兜底。

## 尚待用户完成

1. `[feishu]` 填 app_id / redirect_uri（redirect_uri 需在开放平台登记）。
2. `security add-generic-password ... -s summit-workbench-feishu-app-secret -w -U` 存 App Secret。
3. `wb feishu authorize-url` → 浏览器授权（含 offline_access）→ `wb feishu login --code <code>` → `wb feishu smoke`。
