from fastapi import FastAPI
from fastapi.testclient import TestClient

from summit_workbench.config.locking import LockBusy
from summit_workbench.webapp.request_boundary import install_exception_handlers
from summit_workbench.workflows.local_mutation import MutationInvariantError


def test_lock_busy_has_stable_workspace_busy_error(tmp_path) -> None:
    app = FastAPI()
    install_exception_handlers(app, operation_id=lambda _request: "op-1")

    @app.get("/busy")
    def busy() -> None:
        raise LockBusy("内部锁等待细节")

    response = TestClient(app).get("/busy")
    assert response.status_code == 409
    assert response.json() == {
        "ok": False,
        "code": "workspace_busy",
        "message": "工作区正被另一个操作使用，请稍后重试",
        "operation_id": "op-1",
    }


def test_committed_mutation_invariant_exposes_safe_retry_state() -> None:
    app = FastAPI()
    install_exception_handlers(app, operation_id=lambda _request: "op-2")

    @app.get("/invariant")
    def invariant() -> None:
        raise MutationInvariantError(
            "本地 mutation 未提交全部写入：capture；新增未提交路径：extra.md",
            committed=True,
            commit_sha="a" * 40,
            paths=["extra.md"],
        )

    response = TestClient(app).get("/invariant")
    assert response.status_code == 500
    assert response.json() == {
        "ok": False,
        "code": "mutation_invariant",
        "message": (
            "本地 mutation 未提交全部写入：capture；新增未提交路径：extra.md"
            "（写入已提交，请勿重复执行）"
        ),
        "operation_id": "op-2",
        "details": {"committed": True, "commit_sha": "a" * 40, "paths": ["extra.md"]},
    }
