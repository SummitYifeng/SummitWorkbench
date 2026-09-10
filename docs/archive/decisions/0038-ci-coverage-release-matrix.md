# ADR 0038 · CI、覆盖率门与 M2+ arm64 发布矩阵

- 状态：已实现（P1-06；本地全量质量门、arm64 发布演练和 packaged integration 通过）
- 日期：2026-09-06
- 依据：产品化计划 P1-06、用户平台约束（仅 M2+ Apple Silicon）、ADR 0032 macOS 内部发布、ADR 0037 诊断支持

## 背景与决策

此前 CI 只执行 Python 基础 lint/type/test，前端构建、锁文件、覆盖率、秘密卫生和打包路径没有
统一门禁。P1-06 将这些检查接入 pull request/main CI，并建立 tag 驱动的内部发布 workflow。

Python CI 使用 `uv lock --check`、ruff、format、mypy 和 pytest-cov；覆盖率最低门为 80%，同时
生成 `coverage.xml` 和模块明细。Node 使用 `actions/setup-node` 固定 Node 20、`npm ci` 和
`web/package-lock.json`，然后运行前端 build、browser contract 与 `verify-build.mjs`。
`scripts/secret_scan.py` 扫描 tracked 文本和发布元数据中的高置信度私钥、Bearer、带值凭据和
URL userinfo 特征；测试 fixture 若需模拟 userinfo，采用分段字符串避免把真实凭据形状写进源文件。

## 平台与发布矩阵

产品约束为仅 M2 及以上 Apple Silicon，故不生成 Intel/Windows 包。CI 仍保留独立的 x86_64
负向矩阵项：它必须被构建脚本拒绝，防止误发不支持架构；arm64 项在 macOS runner 上执行完整
App 构建，且构建脚本强制 `ARCH == uname -m`，manifest 的 architecture 与 runner 一致。

release workflow 只响应 `v*` tag，并在任何签名/打包动作前核对 tag 去掉 `v` 后等于
`pyproject.toml` version、runner 为 arm64。内部发布继续使用 ad-hoc 签名，不读取 Apple Developer
ID secret；workflow 使用受保护的 `release` environment，当前没有需要注入的签名 secret。
临时构建目录和目标发布目录不可覆盖既有版本，失败不会更新 partial latest。

`release-macos.sh` 的产物包含 DMG、`SHA256SUMS`、SBOM、notary log 摘要、release metadata 和
test manifest。release workflow 使用产出的 App 设置 `WB_PACKAGED_APP`，强制执行 packaged
integration，而不是让该测试以缺省环境变量静默跳过。

## 验证证据

- `uv run pytest --cov=summit_workbench --cov-report=term-missing --cov-report=xml --cov-fail-under=80 -q`：
  751 passed，1 skipped，覆盖率 83.28%。
- `uv run ruff check .`、`uv run ruff format --check .`、`uv run mypy src tests`、
  `npm ci --prefix web`、`npm --prefix web run test:frontend`、前端 build/verify、secret scan、
  `uv lock --check` 和脚本语法检查通过。
- `BUILD_NUMBER=106 ARCH=arm64 RELEASE_OUTPUT_DIR=dist/p1-06-release scripts/release-macos.sh`：
  内部 arm64 DMG 与 bundle/DMG 离线验证通过；产物包含 checksum、SBOM、notary 摘要和 test manifest。
- `WB_PACKAGED_APP=dist/p1-06-release/0.4.1/arm64/SummitWorkbench.app uv run pytest -m integration -q`：
  1 passed，751 deselected。
- `ARCH=x86_64 scripts/build-macos-app.sh`：按产品策略拒绝，未生成 x86 产物。

## 未验证事项

未调用 GitHub Actions 云端 runner；workflow 本身通过本地契约测试。未使用 Apple Developer ID、
真实账号、真实远端或第二台 Mac；这些不属于当前内部 arm64 产品的本包必需条件。
