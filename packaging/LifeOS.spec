# Build with: python -m PyInstaller packaging/LifeOS.spec
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

root = Path(SPECPATH).parent
datas = [(str(root / "migrations"), "migrations")]
datas += collect_data_files("alembic")
for package in ("alembic", "SQLAlchemy", "pydantic", "pydantic-settings"):
    datas += copy_metadata(package)

hiddenimports = ["logging.config"]
hiddenimports += collect_submodules("alembic")
hiddenimports += collect_submodules("sqlalchemy.dialects.sqlite")

a = Analysis(
    [str(root / "packaging" / "launcher.py")],
    pathex=[str(root / "src")],
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
    name="LifeOS",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
