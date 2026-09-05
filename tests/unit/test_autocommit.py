"""P0' 自动提交 / 撤销 helper 单测（U1-U3）：非 git 降级、只 add 显式路径、
端到端还原、脏文件拒绝。"""

from __future__ import annotations

import subprocess
from pathlib import Path

from summit_workbench.repositories.autocommit import (
    CommitStatus,
    commit_diff_text,
    commit_paths,
    list_wb_commits,
    revert_commit,
)


def _git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(path), *args], check=True, capture_output=True, text=True
    ).stdout


def _git_bytes(path: Path, *args: str) -> bytes:
    return subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True).stdout


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "t@t.test")
    _git(path, "config", "user.name", "Tester")
    (path / "seed.txt").write_text("seed", encoding="utf-8")
    _git(path, "add", "seed.txt")
    _git(path, "commit", "-q", "-m", "chore: seed")


def _vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    _init_repo(vault)
    return vault


# ---- U1：非 git 降级 + 只 add 显式路径 ----


def test_u1_not_git_returns_status_without_raising(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    note = vault / "inbox.md"
    note.write_text("# inbox", encoding="utf-8")
    result = commit_paths(vault, [note], "wb: capture")
    assert result.status is CommitStatus.NOT_GIT


def test_u1_only_stages_listed_paths(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    target = vault / "inbox.md"
    target.write_text("# inbox\n- [ ] x", encoding="utf-8")
    user_file = vault / "user-notes.md"
    user_file.write_text("私人笔记", encoding="utf-8")
    result = commit_paths(vault, [target], "wb: capture")
    assert result.status is CommitStatus.COMMITTED
    status = _git(vault, "status", "--porcelain")
    assert "user-notes.md" in status  # 用户文件仍是未跟踪状态
    assert "inbox.md" not in status  # 目标已提交
    log = _git(vault, "log", "--pretty=%s", "-1")
    assert log.strip() == "wb: capture"


def test_u1_refuses_preexisting_index_and_preserves_it_byte_for_byte(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    manual = vault / "manual.md"
    manual.write_bytes(b"user staged content\x00")
    _git(vault, "add", "--", "manual.md")
    before = _git_bytes(vault, "diff", "--cached", "--binary")
    target = vault / "inbox.md"
    target.write_text("system content", encoding="utf-8")

    result = commit_paths(vault, [target], "wb: capture")

    assert result.status is CommitStatus.INDEX_NOT_CLEAN
    assert _git_bytes(vault, "diff", "--cached", "--binary") == before
    assert "manual.md" in _git(vault, "diff", "--cached", "--name-only")
    assert "inbox.md" not in _git(vault, "diff", "--cached", "--name-only")
    assert _git(vault, "log", "--pretty=%s", "-1").strip() == "chore: seed"


def test_u1_refuses_intent_to_add_as_preexisting_staged_path(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    manual = vault / "manual.md"
    manual.write_text("user content", encoding="utf-8")
    _git(vault, "add", "-N", "--", "manual.md")
    target = vault / "inbox.md"
    target.write_text("system content", encoding="utf-8")

    result = commit_paths(vault, [target], "wb: capture")

    assert result.status is CommitStatus.INDEX_NOT_CLEAN
    assert "manual.md" in _git(vault, "status", "--porcelain")


def test_u1_invalid_message_does_not_touch_index_or_create_commit(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    target = vault / "inbox.md"
    target.write_text("system content", encoding="utf-8")

    result = commit_paths(vault, [target], "capture\nmanual")

    assert result.status is CommitStatus.FAILED
    assert result.error_code == "invalid-message"
    assert "inbox.md" not in _git(vault, "diff", "--cached", "--name-only")
    assert _git(vault, "log", "--pretty=%s", "-1").strip() == "chore: seed"


def test_u1_message_is_normalized_to_one_line(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    target = vault / "inbox.md"
    target.write_text("system content", encoding="utf-8")

    result = commit_paths(vault, [target], "  wb: capture\nwith\tline  ")

    assert result.status is CommitStatus.COMMITTED
    assert _git(vault, "log", "--pretty=%s", "-1").strip() == "wb: capture with line"


def test_u1_unchanged_content_skips_commit(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    target = vault / "inbox.md"
    target.write_text("# inbox\n- [ ] x", encoding="utf-8")
    first = commit_paths(vault, [target], "wb: capture")
    assert first.status is CommitStatus.COMMITTED
    second = commit_paths(vault, [target], "wb: capture")
    assert second.status is CommitStatus.NOTHING_TO_COMMIT


# ---- U2：list_wb_commits / revert_commit 端到端 ----


def test_u2_list_and_revert_roundtrip(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    target = vault / "projects" / "P1.md"
    target.parent.mkdir(exist_ok=True)
    target.write_text("v1", encoding="utf-8")
    _git(vault, "add", "projects/P1.md")
    _git(vault, "commit", "-q", "-m", "chore: v1")
    # 人工提交不带 wb: 前缀 → 不进撤销列表
    target.write_text("v2", encoding="utf-8")
    result = commit_paths(vault, [target], "wb: threads/state P1")
    assert result.status is CommitStatus.COMMITTED

    commits, error = list_wb_commits(vault, limit=10)
    assert error is None
    assert len(commits) == 1
    assert commits[0].message == "wb: threads/state P1"
    assert "projects/P1.md" in commits[0].files
    # 差异预览可用
    diff, diff_error = commit_diff_text(vault, commits[0].sha)
    assert diff_error is None
    assert "v2" in diff and "v1" in diff
    # 还原 → 文件回到 v1
    reverted = revert_commit(vault, commits[0].sha)
    assert reverted.status is CommitStatus.REVERTED
    assert target.read_text(encoding="utf-8") == "v1"
    # 还原本身也留痕（撤销后仍可查历史，日志主题是 Revert）
    log = _git(vault, "log", "--pretty=%s", "-1")
    assert log.startswith("Revert")


def test_u2_list_excludes_non_wb_commits(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    other = vault / "meeting.md"
    other.write_text("人工提交", encoding="utf-8")
    _git(vault, "add", "meeting.md")
    _git(vault, "commit", "-q", "-m", "docs: 人工记录")
    commits, error = list_wb_commits(vault)
    assert error is None
    assert commits == []


def test_u2_diff_and_revert_reject_non_wb_short_unknown_and_option_sha(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    target = vault / "manual.md"
    target.write_text("manual", encoding="utf-8")
    _git(vault, "add", "--", "manual.md")
    _git(vault, "commit", "-q", "-m", "docs: manual")
    manual_sha = _git(vault, "rev-parse", "HEAD").strip()

    invalid_shas = [
        manual_sha,
        manual_sha[:8],
        "--output=/tmp/should-not-be-created",
        "f" * 40,
    ]
    for sha in invalid_shas:
        diff, diff_error = commit_diff_text(vault, sha)
        reverted = revert_commit(vault, sha)
        assert diff == ""
        assert diff_error is not None
        assert reverted.status is CommitStatus.FAILED
        assert reverted.error_code == "invalid-wb-commit"


def test_u2_merge_wb_commit_is_not_listed_or_reversible(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    _git(vault, "checkout", "-qb", "feature")
    (vault / "feature.md").write_text("feature", encoding="utf-8")
    _git(vault, "add", "--", "feature.md")
    _git(vault, "commit", "-q", "-m", "feature")
    _git(vault, "checkout", "-q", "-")
    (vault / "main.md").write_text("main", encoding="utf-8")
    _git(vault, "add", "--", "main.md")
    _git(vault, "commit", "-q", "-m", "main")
    _git(vault, "merge", "--no-ff", "-q", "feature", "-m", "wb: merge")
    merge_sha = _git(vault, "rev-parse", "HEAD").strip()

    commits, error = list_wb_commits(vault)
    diff, diff_error = commit_diff_text(vault, merge_sha)
    reverted = revert_commit(vault, merge_sha)

    assert error is None
    assert commits == []
    assert diff == ""
    assert diff_error is not None
    assert reverted.status is CommitStatus.FAILED
    assert reverted.error_code == "invalid-wb-commit"


# ---- U3：还原前目标文件有未提交改动 → 拒绝 ----


def test_u3_revert_refused_when_file_dirty(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    target = vault / "inbox.md"
    target.write_text("wb 写入", encoding="utf-8")
    commit_paths(vault, [target], "wb: capture")
    commits, _error = list_wb_commits(vault)
    sha = commits[0].sha
    # 用户随后手动改了该文件（未提交）
    target.write_text("wb 写入 + 用户手改", encoding="utf-8")
    result = revert_commit(vault, sha)
    assert result.status is CommitStatus.FAILED
    assert "未提交改动" in result.detail
    # 文件保持用户手改内容，未被覆盖
    assert target.read_text(encoding="utf-8") == "wb 写入 + 用户手改"


def test_u3_revert_unknown_sha_returns_visible_error(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    result = revert_commit(vault, "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef")
    assert result.status is CommitStatus.FAILED
