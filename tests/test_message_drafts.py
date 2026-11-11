from datetime import UTC, date, datetime, time, timedelta

import pytest
from alembic import command
from sqlalchemy import create_engine, text

from lifeos.config.settings import Settings
from lifeos.infrastructure.database.engine import create_database
from lifeos.tasks import TaskService, TaskValidationError
from tests._helpers import alembic_config


def test_migration_keeps_old_task_and_new_deadline_survives_completion_and_reopen(tmp_path):
    settings = Settings(data_dir=tmp_path)
    database = create_database(settings)
    migration = alembic_config(database.path)
    database.dispose()
    command.upgrade(migration, "0002_tasks")

    old_engine = create_engine(migration.attributes["lifeos_url"])
    try:
        with old_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO tasks (id, title, status, created_at, completed_at) "
                    "VALUES ('old', '旧任务', 'pending', '2026-11-07', NULL)"
                )
            )
    finally:
        old_engine.dispose()

    command.upgrade(migration, "head")
    database = create_database(settings)
    try:
        service = TaskService(database)
        (old,) = service.list_tasks()
        assert (old.id, old.title, old.status, old.due_on) == ("old", "旧任务", "pending", None)
        with pytest.raises(TaskValidationError):
            service.create_task("非法截止时间", due_on=datetime(2026, 12, 18, 15, 0))
        assert len(service.list_tasks()) == 1
        created = service.create_task("提交报告", due_on=date(2026, 12, 18))
        assert created.due_on == date(2026, 12, 18)
        completed = service.complete_task(created.id)
        assert completed.due_on == created.due_on
    finally:
        database.dispose()

    reopened = create_database(settings)
    try:
        tasks = {task.id: task for task in TaskService(reopened).list_tasks()}
        assert tasks[created.id] == completed
        assert tasks["old"] == old
    finally:
        reopened.dispose()


def test_both_desktop_entry_points_save_normalized_deadlines(qtbot, tmp_path):
    from lifeos.ai.local_provider import LocalDraftProvider
    from lifeos.ui.main_window import MainWindow
    from lifeos.ui.message_import import MessageImportDialog

    settings = Settings(data_dir=tmp_path)
    database = create_database(settings)
    try:
        command.upgrade(alembic_config(database.path), "head")
        service = TaskService(database)
        provider = LocalDraftProvider(today=date(2026, 11, 11))
        window = MainWindow(
            "test",
            True,
            service,
            draft_preview=provider.extract_tasks,
            quick_parse=provider.parse_quick_task,
        )
        qtbot.addWidget(window)
        window.show()
        window.task_panel.task_input.setText("明天下午5点前提交实验报告")
        window.task_panel.task_input.returnPressed.emit()
        (quick_task,) = service.list_tasks()
        assert (quick_task.title, quick_task.due_on, quick_task.due_time) == (
            "提交实验报告",
            date(2026, 11, 12),
            time(17),
        )

        window.message_import_button.click()
        dialog = window.findChild(MessageImportDialog)
        assert dialog is not None
        dialog.message_input.setPlainText(
            "各位同学好，下面是本周安排。\n"
            "请提交报名表。\n截止时间：2026年12月20日下午6点。\n"
            "请在2026年12月22日前上传附件。\n谢谢配合！"
        )
        dialog.generate_button.click()
        assert service.list_tasks() == [quick_task]
        assert dialog.draft_list.count() == 2
        assert dialog.title_input.text() == "提交报名表"
        assert dialog.due_input.text() == "2026-12-20 18:00"
        assert dialog.draft_list.item(1).text() == "上传附件  ·  截止 2026-12-22"

        dialog.due_input.setText("2026-12-21 17:30")
        dialog.save_button.click()
        assert dialog.draft_list.count() == 1
        dialog.save_button.click()
        assert len(service.list_tasks()) == 2
        dialog.reject()
        rows = window.task_panel.task_titles()
        assert any(row.endswith("提交报名表  ·  截止 2026-12-21 17:30") for row in rows)
        assert any(row.endswith("提交实验报告  ·  截止 2026-11-12 17:00") for row in rows)
        window.close()
    finally:
        database.dispose()

    reopened = create_database(settings)
    try:
        assert {
            (task.title, task.due_on, task.due_time) for task in TaskService(reopened).list_tasks()
        } == {
            ("提交报名表", date(2026, 12, 21), time(17, 30)),
            ("提交实验报告", date(2026, 11, 12), time(17)),
        }
    finally:
        reopened.dispose()


def test_late_completion_stays_distinct_after_reopening(qtbot, tmp_path, monkeypatch):
    from PySide6.QtCore import Qt

    from lifeos.infrastructure.database import task_repository
    from lifeos.ui.task_panel import TaskPanel

    today = date.today()
    yesterday = today - timedelta(days=1)
    completed_at = datetime.combine(today, time(0, 30)).astimezone(UTC)
    settings = Settings(data_dir=tmp_path)
    database = create_database(settings)
    try:
        command.upgrade(alembic_config(database.path), "head")
        service = TaskService(database)
        service.create_task("补交签到表", due_on=yesterday)
        service.create_task("提交实验报告", due_on=today)
        panel = TaskPanel(service)
        qtbot.addWidget(panel)
        monkeypatch.setattr(task_repository, "utcnow", lambda: completed_at.replace(tzinfo=None))

        for index in range(panel.task_list.count()):
            panel.task_list.item(index).setCheckState(Qt.CheckState.Checked)
        assert set(panel.task_titles()) == {
            f"逾期完成  ·  补交签到表  ·  截止 {yesterday}",
            f"提交实验报告  ·  截止 {today}",
        }
        panel.close()
    finally:
        database.dispose()

    reopened = create_database(settings)
    try:
        panel = TaskPanel(TaskService(reopened))
        qtbot.addWidget(panel)
        items = {item.text(): item for item in (panel.task_list.item(i) for i in range(2))}
        late = items[f"逾期完成  ·  补交签到表  ·  截止 {yesterday}"]
        on_time = items[f"提交实验报告  ·  截止 {today}"]
        assert late.checkState() == on_time.checkState() == Qt.CheckState.Checked
        assert late.toolTip() == "逾期完成"
        assert not late.font().strikeOut()
        assert on_time.font().strikeOut()
        panel.close()
    finally:
        reopened.dispose()
