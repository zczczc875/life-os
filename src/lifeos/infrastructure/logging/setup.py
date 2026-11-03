"""轮转日志初始化。

模块导入不产生副作用；调用 :func:`setup_logging` 才是显式的初始化动作。
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from lifeos.config.settings import Settings

_LOGGER_NAME = "lifeos"
_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def setup_logging(settings: Settings) -> None:
    """初始化轮转日志，写入 ``settings.data_dir / "logs" / "lifeos.log"``。

    重复调用幂等；目录创建失败或无法打开日志文件时抛出异常，由调用方处理。
    """
    logger = logging.getLogger(_LOGGER_NAME)
    if logger.handlers:
        return

    log_dir = settings.data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    handler = RotatingFileHandler(
        log_dir / "lifeos.log",
        maxBytes=settings.log_max_bytes,
        backupCount=settings.log_backup_count,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(_FORMAT))
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.propagate = False
