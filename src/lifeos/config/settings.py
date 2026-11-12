"""LifeOS 统一配置。

读取配置不产生任何文件或目录副作用；数据目录只在显式启动阶段被创建。
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_APP_VERSION = "0.3.0rc1"


def _default_data_dir() -> Path:
    """返回默认数据目录路径，但不创建它。"""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "LifeOS" / "data"
    return Path.home() / "AppData" / "Local" / "LifeOS" / "data"


class Settings(BaseSettings):
    """进程级配置，支持 ``LIFEOS_`` 前缀的环境变量覆盖。

    例如 ``LIFEOS_DATA_DIR``、``LIFEOS_LOG_MAX_BYTES``。
    """

    model_config = SettingsConfigDict(env_prefix="LIFEOS_", extra="ignore")

    app_version: str = _APP_VERSION
    data_dir: Path = Field(default_factory=_default_data_dir)

    # 轮转日志参数
    log_max_bytes: int = Field(default=1_000_000, gt=0)
    log_backup_count: int = Field(default=3, ge=1)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """返回缓存的进程级配置（无参）。

    测试隔离时可设置环境变量后调用 ``get_settings.cache_clear()``，
    或直接实例化 ``Settings(data_dir=...)``。
    """
    return Settings()
