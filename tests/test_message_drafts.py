from datetime import UTC, date, datetime, time, timedelta

import pytest
from alembic import command
from sqlalchemy import create_engine, text

from lifeos.config.settings import Settings
from lifeos.infrastructure.database.engine import create_database
from lifeos.tasks import TaskService, TaskValidationError
from tests._helpers import alembic_config


@pytest.mark.parametrize(
    ("notice", "title", "due_on"),
    [
        ("- 提交报告 DDL: 2026-12-18", "提交报告", date(2026, 12, 18)),
        ("交报名表，截止：2026-12-20。", "交报名表", date(2026, 12, 20)),
        ("请在 2026-12-18 前提交报告", "请在 2026-12-18 前提交报告", date(2026, 12, 18)),
        ("DDL: 2026-12-18", "DDL: 2026-12-18", None),
        ("提交报告 DDL: 2026-02-30", "提交报告 DDL: 2026-02-30", None),
        ("下周五前提交报告", "下周五前提交报告", None),
        ("说明会 2026-12-18", "说明会 2026-12-18", None),
        ("交表 截止 2026-12-18 18:00", "交表 截止 2026-12-18 18:00", None),
        ("请于2026-12-18前交表 DDL 2026-12-20", "请于2026-12-18前交表 DDL 2026-12-20", None),
        ("不要在2026-12-18前交表", "不要在2026-12-18前交表", None),
        ("交表 DDL 2026-12-18 或 DDL 2026-12-20", "交表 DDL 2026-12-18 或 DDL 2026-12-20", None),
    ],
)
def test_notice_preview_only_extracts_supported_deadlines(notice, title, due_on):
    from lifeos.ai.local_provider import LocalDraftProvider

    drafts = LocalDraftProvider().extract_tasks(f"  \n{notice}\n\n- 其他事项").tasks
    assert [(draft.title, draft.due_on) for draft in drafts] == [
        (title, due_on),
        ("其他事项", None),
    ]
    assert LocalDraftProvider().extract_tasks(" \n ").tasks == []


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


def test_pasted_notice_is_persisted_only_after_desktop_confirmation(qtbot, tmp_path):
    from lifeos.ai.local_provider import LocalDraftProvider
    from lifeos.ui.main_window import MainWindow
    from lifeos.ui.message_import import MessageImportDialog

    settings = Settings(data_dir=tmp_path)
    database = create_database(settings)
    try:
        command.upgrade(alembic_config(database.path), "head")
        service = TaskService(database)
        window = MainWindow("test", True, service, draft_preview=LocalDraftProvider().extract_tasks)
        qtbot.addWidget(window)
        window.show()

        window.message_import_button.click()
        dialog = window.findChild(MessageImportDialog)
        assert dialog is not None
        dialog.message_input.setPlainText("交报名表，截止：2026-12-20。\n不保存这条")
        dialog.generate_button.click()
        assert service.list_tasks() == []
        assert dialog.draft_list.count() == 2
        assert dialog.due_input.text() == "2026-12-20"

        dialog.title_input.setText("提交报名表")
        dialog.due_input.setText("2026-12-21")
        dialog.save_button.click()
        assert dialog.draft_list.count() == 1
        dialog.save_button.click()
        assert len(service.list_tasks()) == 1
        dialog.reject()
        (row,) = window.task_panel.task_titles()
        assert row.endswith("提交报名表  ·  截止 2026-12-21")
        window.close()
    finally:
        database.dispose()

    reopened = create_database(settings)
    try:
        (task,) = TaskService(reopened).list_tasks()
        assert (task.title, task.due_on, task.status) == (
            "提交报名表",
            date(2026, 12, 21),
            "pending",
        )
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
