"""Exercise the daily plan from its normal desktop entry point."""

from datetime import UTC, datetime, time, timedelta
from types import SimpleNamespace

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QDialog, QPushButton

from lifeos.config.settings import Settings
from lifeos.infrastructure.database.engine import create_database
from lifeos.tasks import Task, TaskService
from lifeos.ui import daily_plan
from lifeos.ui.main_window import MainWindow


def _open_plan(qtbot, window):
    button = window.findChild(QPushButton, "dailyPlanButton")
    assert button is not None and button.isEnabled()
    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
    dialog = window.findChild(QDialog, "dailyPlanDialog")
    assert dialog is not None and dialog.isVisible()
    return dialog


def _plan_rows(dialog):
    tree = dialog.plan_tree
    return [
        (
            group.text(0),
            [
                tuple(group.child(row).text(column) for column in range(tree.columnCount()))
                for row in range(group.childCount())
            ],
        )
        for group in (tree.topLevelItem(row) for row in range(tree.topLevelItemCount()))
    ]


def test_daily_plan_reads_fresh_tasks_and_highlights_three(qtbot, tmp_path, monkeypatch):
    now = datetime(2026, 11, 12, 15)
    monkeypatch.setattr(daily_plan, "datetime", SimpleNamespace(now=lambda: now))
    database = create_database(Settings(data_dir=tmp_path))
    try:
        database.ensure_schema()
        service = TaskService(database)
        service.create_task("不设截止日期")
        completed = service.create_task("已做完")
        service.complete_task(completed.id)
        window = MainWindow("test", True, task_service=service)
        qtbot.addWidget(window)
        window.show()

        today = now.date()
        earlier = today - timedelta(days=2)
        this_week = today + timedelta(days=1)
        later = today + timedelta(days=8)
        service.create_task("未来任务", due_on=later)
        service.create_task("本周的任务", due_on=this_week)
        service.create_task("今天的任务", due_on=today, due_time=time(23, 59))
        overdue = service.create_task("<b>实验报告</b>", due_on=earlier)
        tasks_before_open = service.list_tasks()

        dialog = _open_plan(qtbot, window)
        assert _plan_rows(dialog) == [
            ("已逾期", [("<b>实验报告</b>", earlier.isoformat(), "高", "建议")]),
            ("今天到期", [("今天的任务", f"{today} 23:59", "高", "建议")]),
            ("本周到期", [("本周的任务", this_week.isoformat(), "中", "建议")]),
            ("之后到期", [("未来任务", later.isoformat(), "中", "")]),
            ("未设截止日期", [("不设截止日期", "—", "低", "")]),
        ]
        assert service.list_tasks() == tasks_before_open

        qtbot.keyClick(dialog, Qt.Key.Key_Escape)
        assert not dialog.isVisible()
        service.complete_task(overdue.id)
        qtbot.waitUntil(lambda: window.findChild(QDialog, "dailyPlanDialog") is None)
        reopened = _open_plan(qtbot, window)
        assert [group for group, _ in _plan_rows(reopened)] == [
            "今天到期",
            "本周到期",
            "之后到期",
            "未设截止日期",
        ]
    finally:
        database.dispose()


def test_open_daily_plan_reclassifies_a_deadline_without_reading_storage(qtbot, monkeypatch):
    now = datetime(2026, 11, 12, 15)
    monkeypatch.setattr(daily_plan, "datetime", SimpleNamespace(now=lambda: now))
    task = Task(
        id="deadline",
        title="实验报告",
        status="pending",
        created_at=now.replace(tzinfo=UTC),
        completed_at=None,
        due_on=now.date(),
        due_time=now.time(),
    )
    reads = []

    def list_tasks():
        reads.append(task.id)
        return [task]

    dialog = daily_plan.DailyPlanDialog(SimpleNamespace(list_tasks=list_tasks))
    qtbot.addWidget(dialog)
    dialog.show()
    assert _plan_rows(dialog)[0][0] == "今天到期"

    timer = dialog.findChild(QTimer)
    assert timer is not None and timer.isActive()
    now += timedelta(minutes=1)
    timer.timeout.emit()

    assert _plan_rows(dialog)[0][0] == "已逾期"
    assert reads == [task.id]


def test_daily_plan_can_retry_after_loading_fails(qtbot):
    class Service:
        failed = True

        def list_tasks(self):
            if self.failed:
                raise RuntimeError("test storage failure")
            return []

    service = Service()
    window = MainWindow("test", True, task_service=service)
    qtbot.addWidget(window)
    window.show()
    dialog = _open_plan(qtbot, window)
    assert "加载失败" in dialog.status_label.text()
    assert dialog.plan_tree.isHidden()

    service.failed = False
    qtbot.mouseClick(dialog.refresh_button, Qt.MouseButton.LeftButton)
    assert dialog.status_label.text() == "暂无待办任务。"
    assert dialog.plan_tree.isHidden()


def test_daily_plan_requires_a_task_service(qtbot):
    window = MainWindow("test", False)
    qtbot.addWidget(window)
    assert window.findChild(QPushButton, "dailyPlanButton") is None
