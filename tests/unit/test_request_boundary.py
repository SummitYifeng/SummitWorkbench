from fastapi import FastAPI
from fastapi.testclient import TestClient

from summit_workbench.config.locking import LockBusy
from summit_workbench.webapp.request_boundary import install_exception_handlers


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
