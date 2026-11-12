# Build with: python -m PyInstaller packaging/LifeOS.spec
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

packaging_dir = Path(SPECPATH)
root = packaging_dir.parent
icon = packaging_dir / "LifeOS.ico"
preview = os.environ.get("LIFEOS_BUILD_PREVIEW") == "1"
datas = [(str(root / "migrations"), "migrations"), (str(icon), ".")]
datas += collect_data_files("alembic")
for package in ("alembic", "SQLAlchemy", "pydantic", "pydantic-settings"):
    datas += copy_metadata(package)

hiddenimports = ["logging.config"]
hiddenimports += collect_submodules("alembic")
hiddenimports += collect_submodules("sqlalchemy.dialects.sqlite")

a = Analysis(
    [str(packaging_dir / "launcher.py")],
    pathex=[str(root / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(packaging_dir / "preview_profile.py")] if preview else [],
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
    name="LifeOS-Preview" if preview else "LifeOS",
    icon=str(icon),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
