"""PyInstaller hook to keep preview databases separate from stable releases."""

import os
from pathlib import Path

local_app_data = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
os.environ.setdefault("LIFEOS_DATA_DIR", str(Path(local_app_data) / "LifeOS Preview" / "data"))
