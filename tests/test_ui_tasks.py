"""UI tests for the task panel, using a service double.

``docs/PHASE2_TASKS.md`` assigns the UI to B and allows a service stand-in for
tests: the panel only depends on the documented ``TaskService`` surface, so the
double below mirrors its behaviour instead of touching a database.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QDialog, QLineEdit

from lifeos.ai.provider import ExtractedTask, ProviderError, TaskExtractionResponse
from lifeos.ui import task_panel
from lifeos.ui.main_window import TASKS_HEADING, MainWindow
from lifeos.ui.task_panel import (
    EMPTY_HINT_TEXT,
    EMPTY_TITLE_MESSAGE,
    LOAD_FAILED_MESSAGE,
    NOT_FOUND_MESSAGE,
    SERVICE_MISSING_TEXT,
    STATUS_COMPLETED,
    STATUS_PENDING,
    STORAGE_MESSAGE,
    TaskPanel,
)


class TaskValidationError(ValueError):
    """Mirror of the planned ``lifeos.tasks.TaskValidationError``."""


class TaskNotFoundError(LookupError):
    """Mirror of the planned ``lifeos.tasks.TaskNotFoundError``."""


class TaskStorageError(RuntimeError):
    """Mirror of the planned ``lifeos.tasks.TaskStorageError``."""


@dataclass
class TaskDouble:
    id: str
    title: str
    status: str = STATUS_PENDING
    due_on: date | None = None
    completed_at: datetime | None = None
    due_time: time | None = None


@dataclass
class FakeTaskService:
    """In-memory stand-in for ``lifeos.tasks.TaskService``."""

    tasks: list[TaskDouble] = field(default_factory=list)
    fail_list: bool = False
    fail_create: bool = False
    fail_complete: bool = False
    created_titles: list[str] = field(default_factory=list)
    completed_ids: list[str] = field(default_factory=list)
    _next_id: int = 0

    def create_task(
        self, title: str, *, due_on: date | None = None, due_time: time | None = None
    ) -> TaskDouble:
        stripped = title.strip()
        if not stripped:
            raise TaskValidationError(EMPTY_TITLE_MESSAGE)
        if self.fail_create:
            raise TaskStorageError("write failed")
        self.created_titles.append(stripped)
        self._next_id += 1
        task = TaskDouble(
            id=f"task-{self._next_id}", title=stripped, due_on=due_on, due_time=due_time
        )
        self.tasks.append(task)
        return task

    def list_tasks(self) -> list[TaskDouble]:
        if self.fail_list:
            raise TaskStorageError("read failed")
        return list(self.tasks)

    def complete_task(self, task_id: str) -> TaskDouble:
        self.completed_ids.append(task_id)
        if self.fail_complete:
            raise TaskStorageError("write failed")
        for task in self.tasks:
            if task.id == task_id:
                # Completing twice keeps the first completion.
                if task.status != STATUS_COMPLETED:
                    task.status = STATUS_COMPLETED
                return task
        raise TaskNotFoundError(task_id)


@pytest.fixture
def panel(qtbot):
    service = FakeTaskService()
    widget = TaskPanel(service)
    qtbot.addWidget(widget)
    return widget


def test_deadline_hints_follow_the_local_day_and_task_status(qtbot, monkeypatch):
    now = datetime(2026, 12, 9, 23, 59)
    monkeypatch.setattr(task_panel, "_local_minute", lambda: now)
    service = FakeTaskService(
        tasks=[
            TaskDouble("past", "交报告", due_on=date(2026, 12, 8)),
            TaskDouble("today", "交表", due_on=date(2026, 12, 9)),
            TaskDouble("later", "报名", due_on=date(2026, 12, 10)),
            TaskDouble("done", "付款", status=STATUS_COMPLETED, due_on=date(2026, 12, 8)),
            TaskDouble("undated", "买菜"),
        ]
    )
    widget = TaskPanel(service)
    qtbot.addWidget(widget)
    assert widget.task_titles() == [
        "已逾期  ·  交报告  ·  截止 2026-12-08",
        "今天到期  ·  交表  ·  截止 2026-12-09",
        "报名  ·  截止 2026-12-10",
        "付款  ·  截止 2026-12-08",
        "买菜",
    ]

    now = datetime(2026, 12, 10)
    timer = widget.findChild(QTimer)
    assert timer is not None and timer.isActive()
    service.fail_list = True
    timer.timeout.emit()
    assert widget.error_message() == LOAD_FAILED_MESSAGE
    service.fail_list = False
    timer.timeout.emit()
    assert widget.error_message() == ""
    assert widget.task_titles()[1:3] == [
        "已逾期  ·  交表  ·  截止 2026-12-09",
        "今天到期  ·  报名  ·  截止 2026-12-10",
    ]
    assert service.completed_ids == []

    widget.task_list.item(2).setCheckState(Qt.CheckState.Checked)
    assert widget.task_titles()[2] == "报名  ·  截止 2026-12-10"
    assert service.completed_ids == ["later"]


def test_exact_deadlines_change_at_the_next_minute_and_use_local_completion(qtbot, monkeypatch):
    now = datetime(2026, 12, 9, 14, 29)
    monkeypatch.setattr(task_panel, "_local_minute", lambda: now)
    due_on = now.date()
    due_time = time(14, 30)
    completed_on_time = datetime(2026, 12, 9, 14, 30, 59).astimezone(UTC)
    completed_late = datetime(2026, 12, 9, 14, 31).astimezone(UTC)
    service = FakeTaskService(
        tasks=[
            TaskDouble("pending", "交报告", due_on=due_on, due_time=due_time),
            TaskDouble(
                "done",
                "交表",
                STATUS_COMPLETED,
                due_on,
                completed_on_time,
                due_time,
            ),
            TaskDouble("late", "报名", STATUS_COMPLETED, due_on, completed_late, due_time),
        ]
    )
    widget = TaskPanel(service)
    qtbot.addWidget(widget)
    assert widget.task_titles() == [
        "今天到期  ·  交报告  ·  截止 2026-12-09 14:30",
        "交表  ·  截止 2026-12-09 14:30",
        "逾期完成  ·  报名  ·  截止 2026-12-09 14:30",
    ]

    timer = widget.findChild(QTimer)
    now = datetime(2026, 12, 9, 14, 30)
    timer.timeout.emit()
    assert widget.task_titles()[0].startswith("今天到期")
    now = datetime(2026, 12, 9, 14, 31)
    timer.timeout.emit()
    assert widget.task_titles()[0] == "已逾期  ·  交报告  ·  截止 2026-12-09 14:30"
    assert widget.task_list.item(1).font().strikeOut()
    assert not widget.task_list.item(2).font().strikeOut()


def test_empty_state_shows_hint_and_hides_list(qtbot):
    widget = TaskPanel(FakeTaskService())
    qtbot.addWidget(widget)

    assert widget.task_titles() == []
    assert widget.empty_label.isVisible() is False  # not shown before show()
    assert widget.empty_label.text() == EMPTY_HINT_TEXT
    assert widget.error_message() == ""


def test_empty_state_hint_is_visible_after_show(qtbot):
    widget = TaskPanel(FakeTaskService())
    qtbot.addWidget(widget)
    widget.show()

    assert widget.empty_label.isVisible() is True
    assert widget.task_list.isVisible() is False


def test_adding_a_task_renders_it_and_clears_the_input(panel):
    panel.task_input.setText("  买牛奶  ")
    panel.add_button.click()

    assert panel._service.created_titles == ["买牛奶"]
    assert panel.task_titles() == ["买牛奶"]
    assert panel.task_input.text() == ""
    assert panel.error_message() == ""


def test_enter_key_adds_a_task(panel):
    panel.task_input.setText("写周报")
    panel.task_input.returnPressed.emit()

    assert panel.task_titles() == ["写周报"]


def test_quick_entry_keeps_input_on_errors_and_persists_one_parsed_task(qtbot):
    def quick_parse(text):
        if text == "2026-02-29 前写实验报告":
            raise ValueError("截止日期无效")
        assert text == "2000-02-29 下午三点半前写实验报告"
        return ExtractedTask("写实验报告", date(2000, 2, 29), time(15, 30))

    service = FakeTaskService()
    window = MainWindow("test", True, task_service=service, quick_parse=quick_parse)
    qtbot.addWidget(window)
    panel = window.task_panel
    panel.task_input.setText("2026-02-29 前写实验报告")
    panel.add_button.click()

    assert service.tasks == []
    assert panel.error_message() == "截止日期无效"
    assert panel.task_input.text() == "2026-02-29 前写实验报告"

    panel.task_input.setText("2000-02-29 下午三点半前写实验报告")
    service.fail_create = True
    qtbot.keyClick(panel.task_input, Qt.Key.Key_Return)

    assert panel.error_message() == STORAGE_MESSAGE
    assert panel.task_input.text() == "2000-02-29 下午三点半前写实验报告"

    service.fail_create = False
    qtbot.keyClick(panel.task_input, Qt.Key.Key_Return)

    assert [(task.title, task.due_on, task.due_time) for task in service.tasks] == [
        ("写实验报告", date(2000, 2, 29), time(15, 30)),
    ]
    assert panel.task_titles() == ["已逾期  ·  写实验报告  ·  截止 2000-02-29 15:30"]
    assert panel.task_input.text() == ""
    assert panel.error_message() == ""


@pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
def test_blank_title_is_rejected_without_touching_the_service(panel, blank):
    panel.task_input.setText(blank)
    panel.add_button.click()

    assert panel._service.created_titles == []
    assert panel.task_titles() == []
    assert panel.error_message() == EMPTY_TITLE_MESSAGE


def test_service_validation_error_is_shown(panel):
    panel._service.create_task = lambda title: (_ for _ in ()).throw(
        TaskValidationError("标题太长了")
    )

    panel.submit("正常标题")

    assert panel.error_message() == "标题太长了"


def test_create_storage_error_shows_message_and_keeps_input(panel):
    panel._service.fail_create = True
    panel.task_input.setText("买咖啡")

    panel.add_button.click()

    assert panel.error_message() == STORAGE_MESSAGE
    assert panel.task_input.text() == "买咖啡"
    assert panel.task_titles() == []


def test_marks_task_complete_when_checked(qtbot):
    service = FakeTaskService()
    widget = TaskPanel(service)
    qtbot.addWidget(widget)
    widget.submit("交水电费")

    item = widget.task_list.item(0)
    item.setCheckState(Qt.CheckState.Checked)

    assert service.completed_ids == ["task-1"]
    assert widget.task_titles() == ["交水电费"]
    completed_item = widget.task_list.item(0)
    assert completed_item.checkState() == Qt.CheckState.Checked
    assert completed_item.font().strikeOut() is True
    assert widget.error_message() == ""


def test_completed_task_can_not_be_reopened(qtbot):
    service = FakeTaskService(tasks=[TaskDouble("task-1", "旧任务", STATUS_COMPLETED)])
    widget = TaskPanel(service)
    qtbot.addWidget(widget)

    item = widget.task_list.item(0)

    assert item.checkState() == Qt.CheckState.Checked
    assert not item.flags() & Qt.ItemFlag.ItemIsUserCheckable
    assert item.font().strikeOut() is True
    assert widget.task_titles() == ["旧任务"]


def test_complete_unknown_task_reports_not_found(panel):
    ok = panel.complete("missing")

    assert ok is False
    assert panel.error_message() == NOT_FOUND_MESSAGE
    assert panel.task_titles() == []


def test_complete_storage_error_shows_message_and_reverts(panel):
    panel.submit("打包行李")
    panel._service.fail_complete = True

    panel.task_list.item(0).setCheckState(Qt.CheckState.Checked)

    assert panel.error_message() == STORAGE_MESSAGE
    # The service is the source of truth, so the list is re-read (still pending).
    assert panel.task_titles() == ["打包行李"]


def test_list_failure_is_reported_without_a_crash(qtbot):
    widget = TaskPanel(FakeTaskService(fail_list=True))
    qtbot.addWidget(widget)

    assert widget.error_message() == LOAD_FAILED_MESSAGE
    assert widget.task_titles() == []


def test_panel_without_service_is_disabled(qtbot):
    widget = TaskPanel(None)
    qtbot.addWidget(widget)

    assert widget.task_input.isEnabled() is False
    assert widget.add_button.isEnabled() is False
    assert widget.empty_label.text() == SERVICE_MISSING_TEXT


def test_main_window_hosts_the_task_panel(qtbot):
    service = FakeTaskService()
    window = MainWindow("0.1.0", True, task_service=service)
    qtbot.addWidget(window)

    assert window.findChild(QLineEdit, "taskInput") is window.task_panel.task_input
    assert window.tasks_heading_label.text() == TASKS_HEADING

    assert window.findChild(QLineEdit, "taskDueInput") is None
    window.task_panel.submit("明天整理桌面")
    assert service.created_titles == ["明天整理桌面"]
    assert window.task_panel.task_titles() == ["明天整理桌面"]


def test_main_window_without_service_still_builds(qtbot):
    window = MainWindow("0.1.0", False)
    qtbot.addWidget(window)

    assert window.task_panel.task_input.isEnabled() is False
    assert "未连接" in window.status_label.text()


def _open_message_import(qtbot, service, preview):
    window = MainWindow("0.1.0", True, task_service=service, draft_preview=preview)
    qtbot.addWidget(window)
    window.show()
    window.message_import_button.click()
    dialog = window.findChild(QDialog, "messageImportDialog")
    assert dialog is not None and dialog.isVisible() and dialog.isModal()
    return window, dialog


def test_message_preview_saves_only_the_confirmed_draft_and_refreshes_tasks(qtbot):
    service = FakeTaskService()
    received = []

    def preview(message):
        received.append(message)
        return TaskExtractionResponse(
            [ExtractedTask("提交初稿", date(2026, 12, 8), time(14, 30)), ExtractedTask("带电脑")]
        )

    window, dialog = _open_message_import(qtbot, service, preview)
    dialog.message_input.setPlainText("通知 <b>原文</b>")
    dialog.generate_button.click()

    assert received == ["通知 <b>原文</b>"]
    assert service.tasks == []
    assert dialog.draft_list.count() == 2
    assert dialog.due_input.text() == "2026-12-08 14:30"
    assert dialog.draft_list.item(0).text() == "提交初稿  ·  截止 2026-12-08 14:30"
    assert dialog.draft_list.item(1).text() == "带电脑  ·  未设截止时间"

    dialog.title_input.setText("提交期末报告")
    dialog.due_input.setText("2026-12-09 15:00")
    dialog.draft_list.setCurrentRow(1)
    dialog.draft_list.setCurrentRow(0)
    assert dialog.title_input.text() == "提交期末报告"
    assert dialog.due_input.text() == "2026-12-09 15:00"
    assert dialog.draft_list.item(0).text() == "提交期末报告  ·  截止 2026-12-09 15:00"
    dialog.save_button.click()

    assert [(task.title, task.due_on, task.due_time) for task in service.tasks] == [
        ("提交期末报告", date(2026, 12, 9), time(15)),
    ]
    assert window.task_panel.task_titles()[0].endswith("提交期末报告  ·  截止 2026-12-09 15:00")
    assert dialog.draft_list.count() == 1
    assert not dialog.save_button.isEnabled()
    dialog.draft_list.setCurrentRow(0)
    assert dialog.title_input.text() == "带电脑"

    dialog.reject()
    qtbot.waitUntil(lambda: window.findChild(QDialog, "messageImportDialog") is None)
    window.message_import_button.click()
    new_dialog = window.findChild(QDialog, "messageImportDialog")
    assert new_dialog.message_input.toPlainText() == ""
    assert new_dialog.draft_list.count() == 0
    assert service.created_titles == ["提交期末报告"]


def test_message_import_keeps_draft_after_invalid_date_and_save_failure(qtbot):
    service = FakeTaskService(fail_create=True)
    _, dialog = _open_message_import(
        qtbot, service, lambda message: TaskExtractionResponse([ExtractedTask(message)])
    )
    dialog.message_input.setPlainText("写实验报告")
    dialog.generate_button.click()
    for invalid in (
        "2026-02-29",
        "2028-02-29 24:00",
        "2028-02-29 9:30",
        "2028-02-29 09:30:00",
        "2028-02-29 09:30+08:00",
        "2028-02-29T09:30",
    ):
        dialog.due_input.setText(invalid)
        dialog.save_button.click()
        assert service.tasks == []
        assert "YYYY-MM-DD" in dialog.feedback_label.text()
        assert dialog.due_input.text() == invalid
        assert dialog.draft_list.item(0).text() == "写实验报告  ·  截止时间格式有误"

    dialog.due_input.setText("2028-02-29 09:30")
    dialog.save_button.click()
    assert service.tasks == []
    assert "保存失败" in dialog.feedback_label.text()
    assert dialog.draft_list.count() == 1
    assert dialog.due_input.text() == "2028-02-29 09:30"

    service.fail_create = False
    dialog.save_button.click()
    assert service.created_titles == ["写实验报告"]
    assert service.tasks[0].due_time == time(9, 30)
    assert dialog.draft_list.count() == 0
    assert not dialog.save_button.isEnabled()


def test_message_preview_hides_provider_error_details(qtbot):
    def preview(_message):
        raise ProviderError("通知隐私正文")

    service = FakeTaskService()
    _, dialog = _open_message_import(qtbot, service, preview)
    dialog.message_input.setPlainText("通知隐私正文")
    dialog.generate_button.click()

    assert "生成失败" in dialog.feedback_label.text()
    assert "通知隐私正文" not in dialog.feedback_label.text()
    assert not dialog.save_button.isEnabled()
    assert service.tasks == []
