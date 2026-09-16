# 「今日」页精简与全局 Markdown 展示验收记录

状态：✅ 已合并到 `main`，源码自动化验收通过（2026-09-16）

本记录对应 `main` 当前提交 `61260b0`，基线提交为 `25d6094`。实现先在
`codex/reliability-luna` 上完成，再以 fast-forward 方式合并并推送；没有修改 API
返回字段、飞书数据或 vault 原文。

## 提交顺序

1. ea2ff7f — test: add dirty markdown display cases
2. b008c9b — fix: normalize user markdown at display boundary
3. 768e586 — test: pin the five-section today layout
4. 6abd287 — refactor: simplify today into five clear sections
5. 77ee5cc — build: refresh frontend bundle
6. 8fe8341 — docs: record today-page and markdown acceptance

## 自动化验收

- cd web && npm run test:frontend：通过；包含 Markdown、项目、审批、来源阅读器、
  今日页结构、导入、设置、同步、撤销、线程和浏览器交互契约测试。
- cd web && npm run build：通过；候选前端身份为
  v2026.09.16-6abd287-5236bd8a，静态产物提交为 77ee5cc。
- uv run ruff check .：通过。
- uv run ruff format --check .：通过，已跟踪 Python 文件均已格式化。
- uv run mypy：通过，372 source files。
- uv run pytest：1300 passed，1 skipped，5 warnings。唯一跳过项为未设置
  WB_PACKAGED_APP 的打包 smoke test。
- `WB_PACKAGED_APP=/Applications/SummitWorkbench.app .venv/bin/python -m pytest
  tests/integration/test_packaged_app.py -q`：通过，1 passed；验证包版本为 `0.4.9`、
  build `2026091603`，前端身份为 `v2026.09.16-479f967-5236bd8a`。

## 功能验收

- 今日页只输出“记点什么”“导入会议纪要”“待办任务”“会议”“需要行动”五个内容模块；
  日期、健康状态、读取状态和重新生成属于页面状态，继续保留。
- 项目推进、待确认审批、AI 提议、最近完成不再出现在今日页；/api/state 的项目、
  审批、proposal、completion 字段未删除，项目和审批页继续使用。
- 结构化 brief 缺失时仍输出三个固定内容区和空状态，不整份展示历史 brief_md。
- normalizeDisplayMarkdown() 只在前端展示边界生效：NBSP 变体、历史转义粗体和
  三星脏粗体得到兼容；单独 \* 与 fenced code 内容保持不变；通用 HTML entity
  不解码，原始 HTML 不解析。
- 今日、项目、审批、来源阅读器中的用户正文分别通过 inlineMd() 或 mdToHtml()
  展示；textarea、input、aria/data 属性和诊断/代码/日志仍保留 esc() 原值路径。

## 人工只读检查

- 本地候选工作台真实界面：双列工具区、三个全宽独立内容区、明显边界和区块顺序均可见。
- 展开“导入会议纪要”后，抽屉、dropzone、关闭按钮和选择文件入口均可见；未导入文件、
  未生成简报、未执行审批或写回。
- 当前 CUA 窗口未提供精确 viewport 覆盖，因此未对 390×844 做独立截图；源码已包含
  max-width: 760px 单列规则，且今日页结构测试覆盖固定模块和关键事件标识。
- vault /Users/yifengstudio/Documents/Work/_vault 在检查后工作树为 clean；本轮没有
  vault 文件变更。

历史 build 的验收记录和结论未改写；本文件记录当前 `main` 实现与本机 App 更新后的验收状态。
