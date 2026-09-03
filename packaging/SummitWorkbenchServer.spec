"""PyInstaller onedir specification for the production local server."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


REPO_ROOT = Path(SPECPATH).resolve().parent
datas = [
    (str(REPO_ROOT / "prompts"), "prompts"),
    (str(REPO_ROOT / "templates"), "templates"),
]
hiddenimports = (
    collect_submodules("summit_workbench")
    + [
        "multipart",
        "uvicorn.logging",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
    ]
)

a = Analysis(
    [str(REPO_ROOT / "src" / "summit_workbench" / "webapp" / "server_entry.py")],
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
    [],
    exclude_binaries=True,
    name="SummitWorkbenchServer",
    console=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="SummitWorkbenchServer",
)
