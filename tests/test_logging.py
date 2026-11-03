"""日志初始化与轮转测试。"""

from __future__ import annotations

import logging

import pytest

from lifeos.config.settings import Settings
from lifeos.infrastructure.logging.setup import setup_logging


@pytest.fixture(autouse=True)
def _reset_logger():
    logger = logging.getLogger("lifeos")
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)
    logger.propagate = True
    yield
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)
    logger.propagate = True


def test_setup_logging_creates_log_file(tmp_path):
    setup_logging(Settings(data_dir=tmp_path))
    assert (tmp_path / "logs" / "lifeos.log").exists()


def test_setup_logging_writes_records(tmp_path):
    setup_logging(Settings(data_dir=tmp_path))
    logging.getLogger("lifeos").info("hello-from-test")
    content = (tmp_path / "logs" / "lifeos.log").read_text(encoding="utf-8")
    assert "hello-from-test" in content


def test_setup_logging_is_idempotent(tmp_path):
    settings = Settings(data_dir=tmp_path)
    setup_logging(settings)
    logger = logging.getLogger("lifeos")
    handler_count = len(logger.handlers)
    setup_logging(settings)
    assert len(logger.handlers) == handler_count == 1


def test_setup_logging_ignores_foreign_handlers(tmp_path):
    logging.getLogger("lifeos").addHandler(logging.NullHandler())
    setup_logging(Settings(data_dir=tmp_path))
    assert (tmp_path / "logs" / "lifeos.log").exists()


def test_logging_rotates(tmp_path):
    settings = Settings(data_dir=tmp_path, log_max_bytes=200, log_backup_count=2)
    setup_logging(settings)
    logger = logging.getLogger("lifeos")
    for _ in range(30):
        logger.info("x" * 80)
    backups = sorted((tmp_path / "logs").glob("lifeos.log.*"))
    assert backups, "should have produced rotated backup files"
