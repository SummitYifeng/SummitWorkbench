# ADR 0034 · 工作区 schema 迁移、备份与回滚

- 状态：✅ P1-02 完成（离线实现与验收完成；真实远端/跨设备真机门未执行）
- 日期：2026-09-06
- 里程碑：v0.4.1 → P1-02
- 依据：计划 P1-02、ADR 0029 workspace marker、ADR 0031 多设备同步

## 背景与决策

workspace marker 会随 vault 进入 Git，同一份 vault 可能被 v0.4.1 旧 App 与新 App
交替打开。旧版本不能在未知字段上猜测并写回，否则一次升级就可能破坏另一台设备的
读取能力。因此当前 marker schema 提升到 v2，并登记唯一的相邻迁移边
`v1 -> v2`；迁移历史写在 marker 的 `migration_history` 中，未知字段继续保留。

schema 低于当前支持版本但存在迁移路径时，旧 workspace 对业务保持
`read-only-upgrade-required`；schema 高于当前支持版本仍只读保护，schema 0 或损坏
marker 直接拒绝。迁移完成后保留旧 `min_reader_version`，并把
`min_writer_version` 提升到执行迁移的 App 版本，使旧 reader 可读、新 writer 才能写。

## 安全事务

`workflows/workspace_migration.py` 在单一 workspace lock 内执行：

1. 校验当前设备 id 与用户明确确认的设备 id 相同；
2. 要求 Git 仓库有 remote/upstream、工作树干净，并 `fetch` 后确认 ahead/behind 均为 0；
3. 在本机 `Application Support/SummitWorkbench/backups/` 生成带权限保护的目录，保存
   manifest、被修改 marker 的快照、SHA-256、App version、workspace id 与 Git HEAD；
4. 每个相邻迁移边校验输入/输出版本，并以原子写落盘；
5. 迁移成功后只对 marker 生成独立的
   `wb: migrate workspace vN -> vN+1` 提交并 push；
6. 中途失败恢复 marker 快照并写脱敏失败报告。若 push 在提交后失败，使用安全的 Git
   revert 清掉本次本地迁移提交，不使用 reset、force、stash 或覆盖远端。

迁移通过 `/api/workspace/migration` 暴露给旧 schema 的设置页。设置中心只在当前设备
处于旧 schema 只读保护时显示“升级工作区 schema”，并要求用户确认设备；成功后请求
原生壳重新打开服务，使新的 compatibility context 生效。

## 验证证据

- `tests/unit/test_workspace_migration.py` 覆盖相邻 registry、重复迁移、设备确认、
  dirty tree、远端不可达、ahead/behind 分叉、未来 schema、备份 checksum、成功 commit
  + push、中途异常回滚和 push 失败后的安全 revert。
- 同一测试还覆盖旧 schema 只读状态下迁移 API 不被全局写保护误拦截。
- `uv run pytest -q`：742 passed，1 skipped（既有需要 `WB_PACKAGED_APP` 的打包 smoke）。
- `uv run ruff check .`、`uv run ruff format --check .`、`uv run mypy src tests` 通过。
- `npm --prefix web run build` 与
  `node web/scripts/verify-build.mjs src/summit_workbench/webapp/static` 通过。

## 尚未执行

未访问真实私有 Git remote、真实凭据、第二台 Mac 或真实升级中的双设备共享 vault；这些
属于后续人工真机矩阵。所有本包实现和安全拒绝路径均使用临时目录、fake backend 和
离线测试完成。
