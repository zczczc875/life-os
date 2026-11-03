"""配置模块测试。"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from lifeos.config.settings import Settings, get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_get_settings_returns_typed_settings():
    settings = get_settings()
    assert isinstance(settings.app_version, str) and settings.app_version
    assert isinstance(settings.data_dir, Path)


def test_default_data_dir_uses_local_app_data(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    settings = get_settings()
    assert settings.data_dir == tmp_path / "LifeOS" / "data"


def test_data_dir_can_be_overridden_by_env(monkeypatch, tmp_path):
    override = tmp_path / "custom"
    monkeypatch.setenv("LIFEOS_DATA_DIR", str(override))
    settings = get_settings()
    assert settings.data_dir == override


def test_reading_settings_has_no_side_effect(monkeypatch, tmp_path):
    target = tmp_path / "LifeOS" / "data"
    monkeypatch.setenv("LIFEOS_DATA_DIR", str(target))
    get_settings()
    assert not target.exists()


def test_settings_accept_direct_override(tmp_path):
    settings = Settings(app_version="1.2.3", data_dir=tmp_path / "x")
    assert settings.app_version == "1.2.3"
    assert settings.data_dir == tmp_path / "x"


@pytest.mark.parametrize(
    "overrides",
    [
        {"log_max_bytes": 0},
        {"log_max_bytes": -1},
        {"log_backup_count": 0},
        {"log_backup_count": -1},
    ],
)
def test_invalid_rotation_params_are_rejected(overrides):
    with pytest.raises(ValidationError):
        Settings(**overrides)


def test_invalid_rotation_params_via_env_are_rejected(monkeypatch):
    monkeypatch.setenv("LIFEOS_LOG_MAX_BYTES", "0")
    with pytest.raises(ValidationError):
        Settings()
