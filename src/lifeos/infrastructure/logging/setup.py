"""轮转日志初始化。

模块导入不产生副作用；调用 :func:`setup_logging` 才是显式的初始化动作。
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from lifeos.config.settings import Settings

_LOGGER_NAME = "lifeos"
_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def _is_initialized(logger: logging.Logger, log_file: Path) -> bool:
    """仅当已存在指向目标日志文件的轮转处理器时才视为已初始化。"""
    target = os.path.abspath(str(log_file))
    return any(
        isinstance(handler, RotatingFileHandler)
        and getattr(handler, "baseFilename", None) == target
        for handler in logger.handlers
    )


def setup_logging(settings: Settings) -> None:
    """初始化轮转日志，写入 ``settings.data_dir / "logs" / "lifeos.log"``。

    只有本模块自己的轮转处理器已存在时才幂等返回；NullHandler 等其他处理器
    不影响初始化。目录创建失败或无法打开日志文件时抛出异常，由调用方处理。
    """
    logger = logging.getLogger(_LOGGER_NAME)
    log_file = settings.data_dir / "logs" / "lifeos.log"

    if _is_initialized(logger, log_file):
        return

    log_file.parent.mkdir(parents=True, exist_ok=True)

    handler = RotatingFileHandler(
        log_file,
        maxBytes=settings.log_max_bytes,
        backupCount=settings.log_backup_count,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(_FORMAT))
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.propagate = False
