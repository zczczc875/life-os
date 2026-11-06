"""Windows packaged entry point with an explicit database upgrade prompt."""

from __future__ import annotations

import sqlite3
import sys
import uuid
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox


def _existing_revision(path: Path, latest_revision: str) -> str | None:
    """Read the database version without creating or modifying the database."""
    if not path.exists():
        return None
    if not path.is_file():
        raise RuntimeError("数据库路径不是文件。")

    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            if not row[0].startswith("sqlite_")
        }
        if "alembic_version" not in tables:
            if tables:
                raise RuntimeError("已有数据库没有迁移版本，无法安全升级。请先备份并联系开发者。")
            return None
        revisions = connection.execute("SELECT version_num FROM alembic_version").fetchall()
        if not revisions:
            if tables - {"alembic_version"}:
                raise RuntimeError("已有数据库版本为空，无法安全升级。请先备份并联系开发者。")
            return None
        if len(revisions) != 1:
            raise RuntimeError("数据库存在多个迁移版本，无法安全升级。请联系开发者。")
        revision = str(revisions[0][0])
        if revision == latest_revision and not {"tasks", "app_settings"}.issubset(tables):
            raise RuntimeError("数据库版本已是最新，但缺少数据表。请备份数据库并联系开发者。")
        return revision
    finally:
        connection.close()


def _backup(path: Path) -> Path:
    """Create and verify a consistent, uniquely named backup before migration."""
    backup = path.with_name(f"{path.name}.before-upgrade-{uuid.uuid4().hex}.bak")
    with backup.open("xb"):
        pass
    source = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    destination = sqlite3.connect(backup)
    try:
        source.backup(destination)
        if destination.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("数据库备份校验失败，已停止升级。")
    finally:
        destination.close()
        source.close()
    return backup


def _known_revisions() -> tuple[str, set[str]]:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    from lifeos.infrastructure.database.migrate import find_migrations_dir

    config = Config()
    config.set_main_option("script_location", str(find_migrations_dir()))
    scripts = ScriptDirectory.from_config(config)
    head = scripts.get_current_head()
    if head is None:
        raise RuntimeError("未找到数据库迁移版本。")
    return head, {revision.revision for revision in scripts.walk_revisions()}


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("LifeOS")
    try:
        from lifeos.config.settings import get_settings
        from lifeos.infrastructure.database.url import resolve_target

        settings = get_settings()
        target = resolve_target(settings)
        head, known = _known_revisions()
        current = _existing_revision(target.path, head)
        if current is not None and current not in known:
            raise RuntimeError("数据库版本不在当前程序支持范围内，已停止启动以保护数据。")
        if current != head:
            result = QMessageBox.question(
                None,
                "初始化或升级数据库",
                "LifeOS 需要初始化或升级本地数据库才能使用任务功能。\n\n"
                f"数据库位置：{target.path}\n\n"
                "如果数据库已存在，程序会先在同一目录创建备份。是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if result != QMessageBox.StandardButton.Yes:
                return 0
            if target.path.exists():
                _backup(target.path)
            from lifeos.infrastructure.database.engine import create_database

            database = create_database(settings)
            try:
                database.ensure_schema()
            finally:
                database.dispose()

        from lifeos.app import main as run_application

        return run_application()
    except Exception as error:  # noqa: BLE001 - errors must be visible in a windowed build
        QMessageBox.critical(None, "LifeOS 无法启动", f"启动或数据库升级失败：\n{error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
