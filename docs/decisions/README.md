# 架构决策记录（ADR）索引

按工作包记录关键决策与真机验证结论。文件名带里程碑标识；编号顺序按落地时间，
不严格等于里程碑顺序（M0-6 先于 M0-5 落地）。

| ADR | 里程碑 | 主题 |
|---|---|---|
| [0001](0001-m0-1-tech-stack.md) | M0-1 | 工程与质量技术栈（uv / Typer / Pydantic / httpx / pytest / ruff / mypy）|
| [0002](0002-m0-2-project-migration.md) | M0-2 | 工作目录与 4 项目迁移（iCloud 边界、状态校验）|
| [0003](0003-m0-3-vault.md) | M0-3 | 工作 vault 结构、frontmatter schema、私有远端 |
| [0004](0004-m0-4-feishu-identity.md) | M0-4 | 飞书身份授权、最小权限、refresh token 轮换 |
| [0005](0005-m0-6-cloud-model.md) | M0-6 | 供应商无关云端模型、结构化输出、用量费用账本 |
| [0006](0006-m0-5-work-sync.md) | M0-5 | work-sync 非破坏性批量同步 |
| [0007](0007-m0-10-meeting-note.md) | M0-10 | 会议纪要拉取（会议号 → note_id → 逐字稿），tenant token |

M0 地基全部完成并真机验证；下一步 M1（会议进入第二大脑）。
