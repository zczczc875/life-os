"""Opt in to starting a packaged LifeOS profile at Windows sign-in."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from lifeos.config.settings import _default_data_dir

try:
    import winreg
except ImportError:
    winreg = None

START_IN_TRAY_ARG = "--start-in-tray"
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_COMMAND_LIMIT = 260


class WindowsStartupError(RuntimeError):
    """The Windows startup registration could not be read or changed."""


class WindowsStartup:
    def __init__(self, executable: Path, name: str) -> None:
        if winreg is None:
            raise WindowsStartupError("当前系统不支持 Windows 登录启动设置。")
        self._registry = winreg
        self._executable = executable
        self._name = name

    @classmethod
    def for_current_executable(cls, data_dir: Path) -> WindowsStartup | None:
        """Keep custom profiles and source launches out of Windows startup."""
        if sys.platform != "win32" or winreg is None or not getattr(sys, "frozen", False):
            return None

        name = "LifeOS Preview" if os.environ.get("LIFEOS_PREVIEW_PROFILE") == "1" else "LifeOS"
        stable_data = _default_data_dir()
        default_data = stable_data.parent.with_name(name) / stable_data.name
        try:
            if data_dir.resolve() != default_data.resolve():
                return None
        except (OSError, RuntimeError) as error:
            raise WindowsStartupError("无法核对 Windows 登录启动的数据目录。") from error
        return cls(Path(sys.executable), name)

    def enabled(self) -> bool:
        """Read the profile's startup entry, including one for an older build."""
        registry = self._registry
        try:
            with registry.OpenKey(
                registry.HKEY_CURRENT_USER, _RUN_KEY, 0, registry.KEY_QUERY_VALUE
            ) as key:
                value, value_type = registry.QueryValueEx(key, self._name)
        except FileNotFoundError:
            return False
        except OSError as error:
            raise WindowsStartupError("无法读取 Windows 登录启动设置。") from error
        return value_type == registry.REG_SZ and bool(value)

    def set_enabled(self, enabled: bool) -> None:
        """Register the current EXE or remove this profile's entry."""
        registry = self._registry
        try:
            if enabled:
                command = self._command()
                with registry.CreateKeyEx(
                    registry.HKEY_CURRENT_USER, _RUN_KEY, 0, registry.KEY_SET_VALUE
                ) as key:
                    registry.SetValueEx(key, self._name, 0, registry.REG_SZ, command)
            else:
                try:
                    with registry.OpenKey(
                        registry.HKEY_CURRENT_USER, _RUN_KEY, 0, registry.KEY_SET_VALUE
                    ) as key:
                        registry.DeleteValue(key, self._name)
                except FileNotFoundError:
                    pass
        except OSError as error:
            raise WindowsStartupError("无法修改 Windows 登录启动设置。") from error

    def _command(self) -> str:
        command = f'"{self._executable}" {START_IN_TRAY_ARG}'
        if len(command.encode("utf-16-le")) // 2 > _RUN_COMMAND_LIMIT:
            raise WindowsStartupError("启动命令超过 260 个字符，请将 LifeOS 移到路径更短的目录。")
        if not self._executable.is_absolute() or not self._executable.is_file():
            raise WindowsStartupError("找不到当前 LifeOS 程序，无法设置登录启动。")
        return command
