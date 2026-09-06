"""PyInstaller onedir specification for the production automation worker."""

from pathlib import Path

import certifi
from PyInstaller.utils.hooks import collect_submodules


REPO_ROOT = Path(SPECPATH).resolve().parent
datas = [
    (str(REPO_ROOT / "prompts"), "prompts"),
    (str(REPO_ROOT / "templates"), "templates"),
    (certifi.where(), "certifi"),
]
hiddenimports = (
    collect_submodules("summit_workbench")
    + collect_submodules("dulwich")
    + [
        "certifi",
        "dulwich.client",
        "urllib3",
        "multipart",
    ]
)

a = Analysis(
    [str(REPO_ROOT / "src" / "summit_workbench" / "worker_entry.py")],
    pathex=[str(REPO_ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    exclude_binaries=False,
    name="SummitWorkbenchWorker",
    console=True,
)
