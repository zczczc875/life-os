import sys
from types import SimpleNamespace

import pytest

from lifeos.config import windows_startup
from lifeos.config.windows_startup import START_IN_TRAY_ARG, WindowsStartup, WindowsStartupError


@pytest.fixture
def registry(monkeypatch):
    """Use an in-memory registry so tests never change the real Run key."""
    values = {}
    key_exists = False
    run_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
    current_user, read, write, reg_sz = object(), object(), object(), object()

    class Handle:
        def __init__(self, access):
            self.access = access

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def open_key(root, key, reserved, access):
        assert root is current_user and key == run_key and reserved == 0
        if not key_exists:
            raise FileNotFoundError
        return Handle(access)

    def create_key(root, key, reserved, access):
        nonlocal key_exists
        key_exists = True
        return open_key(root, key, reserved, access)

    def query_value(key, name):
        assert key.access is read
        if name not in values:
            raise FileNotFoundError
        return values[name]

    def set_value(key, name, reserved, kind, value):
        assert key.access is write and reserved == 0 and kind is reg_sz
        values[name] = (value, kind)

    def delete_value(key, name):
        assert key.access is write
        if name not in values:
            raise FileNotFoundError
        del values[name]

    api = SimpleNamespace(
        HKEY_CURRENT_USER=current_user,
        KEY_QUERY_VALUE=read,
        KEY_SET_VALUE=write,
        REG_SZ=reg_sz,
        OpenKey=open_key,
        CreateKeyEx=create_key,
        QueryValueEx=query_value,
        SetValueEx=set_value,
        DeleteValue=delete_value,
    )
    monkeypatch.setattr(windows_startup, "winreg", api)
    return values, api


@pytest.fixture
def packaged(monkeypatch, tmp_path):
    executable = tmp_path / "测试 folder" / "LifeOS.exe"
    executable.parent.mkdir()
    executable.touch()
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("LIFEOS_PREVIEW_PROFILE", raising=False)
    return executable


def test_startup_registration_is_opt_in_and_can_be_removed(registry, packaged, tmp_path):
    values, api = registry
    startup = WindowsStartup.for_current_executable(tmp_path / "LifeOS" / "data")
    assert startup is not None
    assert not startup.enabled()
    startup.set_enabled(False)
    assert not values

    startup.set_enabled(True)
    assert values == {"LifeOS": (f'"{packaged}" {START_IN_TRAY_ARG}', api.REG_SZ)}
    assert startup.enabled()

    startup.set_enabled(False)
    startup.set_enabled(False)
    assert not startup.enabled()
    assert not values


def test_preview_uses_a_separate_registration_name(registry, packaged, monkeypatch, tmp_path):
    values, _ = registry
    stable = WindowsStartup.for_current_executable(tmp_path / "LifeOS" / "data")
    stable.set_enabled(True)
    monkeypatch.setenv("LIFEOS_PREVIEW_PROFILE", "1")

    assert WindowsStartup.for_current_executable(tmp_path / "LifeOS" / "data") is None
    preview = WindowsStartup.for_current_executable(tmp_path / "LifeOS Preview" / "data")
    assert preview is not None and not preview.enabled()
    preview.set_enabled(True)
    assert set(values) == {"LifeOS", "LifeOS Preview"}
    preview.set_enabled(False)
    assert stable.enabled()


def test_launchers_without_the_default_profile_cannot_register(
    registry, packaged, monkeypatch, tmp_path
):
    default = tmp_path / "LifeOS" / "data"
    assert WindowsStartup.for_current_executable(tmp_path / "isolated") is None
    monkeypatch.delattr(sys, "frozen")
    assert WindowsStartup.for_current_executable(default) is None
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    assert WindowsStartup.for_current_executable(default) is None


def test_enabling_replaces_the_existing_version_path(registry, packaged, monkeypatch, tmp_path):
    values, api = registry
    profile = tmp_path / "LifeOS" / "data"
    WindowsStartup.for_current_executable(profile).set_enabled(True)
    new_executable = tmp_path / "LifeOS-next.exe"
    new_executable.touch()
    monkeypatch.setattr(sys, "executable", str(new_executable))

    startup = WindowsStartup.for_current_executable(profile)
    assert startup.enabled()
    startup.set_enabled(True)
    assert values == {"LifeOS": (f'"{new_executable}" {START_IN_TRAY_ARG}', api.REG_SZ)}


def test_long_unicode_command_is_rejected_without_changing_registry(
    registry, packaged, monkeypatch, tmp_path
):
    values, _ = registry
    # Characters outside the BMP occupy two UTF-16 code units in the registry.
    length = 260 - len(f'"{packaged.with_name(".exe")}" {START_IN_TRAY_ARG}')
    executable = packaged.with_name(f"{'𠮷' * length}.exe")
    assert len(f'"{executable}" {START_IN_TRAY_ARG}') == 260
    monkeypatch.setattr(sys, "executable", str(executable))
    startup = WindowsStartup.for_current_executable(tmp_path / "LifeOS" / "data")

    with pytest.raises(WindowsStartupError, match="260"):
        startup.set_enabled(True)
    assert not values


def test_registry_access_error_is_not_reported_as_disabled(
    registry, packaged, monkeypatch, tmp_path
):
    _, api = registry
    startup = WindowsStartup.for_current_executable(tmp_path / "LifeOS" / "data")

    def deny(*args):
        raise PermissionError("access denied")

    monkeypatch.setattr(api, "OpenKey", deny)
    monkeypatch.setattr(api, "CreateKeyEx", deny)
    with pytest.raises(WindowsStartupError, match="读取"):
        startup.enabled()
    with pytest.raises(WindowsStartupError, match="修改"):
        startup.set_enabled(True)
