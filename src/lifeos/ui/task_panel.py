"""Task list UI: input, list and completion.

The panel is presentation-only and talks to an injected task service, so it can
be exercised with a service double. It never imports the database layer or
executes SQL. Errors are reported next to the input; the service stays the
source of truth, so every successful mutation re-reads the list.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Sequence
    from datetime import date

__all__ = [
    "COMPLETED_TOOLTIP",
    "EMPTY_HINT_TEXT",
    "EMPTY_TITLE_MESSAGE",
    "INPUT_PLACEHOLDER",
    "LOAD_FAILED_MESSAGE",
    "NOT_FOUND_MESSAGE",
    "SERVICE_MISSING_TEXT",
    "STATUS_COMPLETED",
    "STATUS_PENDING",
    "STORAGE_MESSAGE",
    "TaskPanel",
]

STATUS_PENDING = "pending"
STATUS_COMPLETED = "completed"

INPUT_PLACEHOLDER = "输入任务标题，回车即可添加"
EMPTY_HINT_TEXT = "还没有任务，先添加一个吧。"
EMPTY_TITLE_MESSAGE = "任务标题不能为空"
NOT_FOUND_MESSAGE = "任务不存在，可能已被删除"
STORAGE_MESSAGE = "任务保存失败，请稍后重试"
LOAD_FAILED_MESSAGE = "任务加载失败，请稍后重试"
SERVICE_MISSING_TEXT = "任务服务尚未接入，暂不可用。"

COMPLETED_TOOLTIP = "已完成"


class TaskRecord(Protocol):
    """The parts of a task the UI reads; no ORM types leak in here."""

    id: str
    title: str
    status: str
    due_on: date | None


class TaskService(Protocol):
    """The service surface ``docs/PHASE2_TASKS.md`` defines for A."""

    def create_task(self, title: str, *, due_on: date | None = None) -> TaskRecord: ...

    def list_tasks(self) -> Sequence[TaskRecord]: ...

    def complete_task(self, task_id: str) -> TaskRecord: ...


class TaskPanel(QWidget):
    """Render the task list and forward user actions to the service."""

    def __init__(self, task_service: TaskService | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self._service = task_service
        self._loading = False

        self.task_input = QLineEdit(self)
        self.task_input.setObjectName("taskInput")
        self.task_input.setPlaceholderText(INPUT_PLACEHOLDER)
        self.task_input.setClearButtonEnabled(True)

        self.add_button = QPushButton("添加", self)
        self.add_button.setObjectName("addTaskButton")
        self.add_button.setDefault(True)

        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        input_row.addWidget(self.task_input, 1)
        input_row.addWidget(self.add_button)

        self.error_label = QLabel("", self)
        self.error_label.setObjectName("taskErrorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #b42318;")
        self.error_label.setVisible(False)

        self.empty_label = QLabel(EMPTY_HINT_TEXT, self)
        self.empty_label.setObjectName("taskEmptyLabel")
        self.empty_label.setWordWrap(True)
        self.empty_label.setStyleSheet("color: #6b7280;")

        self.task_list = QListWidget(self)
        self.task_list.setObjectName("taskList")
        self.task_list.setAlternatingRowColors(True)
        self.task_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addLayout(input_row)
        layout.addWidget(self.error_label)
        layout.addWidget(self.empty_label)
        layout.addWidget(self.task_list, 1)

        self.task_input.returnPressed.connect(self.submit_input)
        self.add_button.clicked.connect(self.submit_input)
        self.task_list.itemChanged.connect(self._on_item_changed)

        if self._service is None:
            self.set_service_available(False)
        else:
            self.refresh()

    # -- public API -----------------------------------------------------

    def set_service_available(self, available: bool) -> None:
        """Enable or disable the controls when no service is injected yet."""
        self.task_input.setEnabled(bool(available))
        self.add_button.setEnabled(bool(available))
        if not available:
            self.task_list.clear()
            self.task_list.setVisible(False)
            self._set_error("")
            self.empty_label.setText(SERVICE_MISSING_TEXT)
            self.empty_label.setVisible(True)
        else:
            self.task_list.setVisible(True)
            self.empty_label.setText(EMPTY_HINT_TEXT)
            self._set_error("")

    def refresh(self) -> None:
        """Re-read the list from the service and render it."""
        if self._service is None:
            return
        try:
            tasks = list(self._service.list_tasks())
        except Exception:  # noqa: BLE001 - the UI must not crash on storage errors
            self._render([])
            self._set_error(LOAD_FAILED_MESSAGE)
            return
        self._set_error("")
        self._render(tasks)

    def submit_input(self) -> None:
        """Handle Enter or a click on the add button."""
        self.submit(self.task_input.text())

    def submit(self, text: str) -> None:
        """Create a task from ``text``; blank titles never reach the service."""
        title = (text or "").strip()
        if not title:
            self._set_error(EMPTY_TITLE_MESSAGE)
            self.task_input.setFocus()
            return
        if self._service is None:
            self._set_error(SERVICE_MISSING_TEXT)
            return
        try:
            self._service.create_task(title)
        except LookupError:
            self._set_error(NOT_FOUND_MESSAGE)
            return
        except ValueError as error:
            self._set_error(str(error).strip() or EMPTY_TITLE_MESSAGE)
            return
        except RuntimeError:
            self._set_error(STORAGE_MESSAGE)
            return
        self.task_input.clear()
        self.refresh()

    def complete(self, task_id: str) -> bool:
        """Mark ``task_id`` complete; return whether the call succeeded."""
        if self._service is None:
            self._set_error(SERVICE_MISSING_TEXT)
            return False
        try:
            self._service.complete_task(task_id)
        except LookupError:
            self.refresh()
            self._set_error(NOT_FOUND_MESSAGE)
            return False
        except ValueError as error:
            self._set_error(str(error).strip() or EMPTY_TITLE_MESSAGE)
            return False
        except RuntimeError:
            self.refresh()
            self._set_error(STORAGE_MESSAGE)
            return False
        self._set_error("")
        self.refresh()
        return True

    # -- rendering ------------------------------------------------------

    def _render(self, tasks: Sequence[TaskRecord]) -> None:
        self._loading = True
        try:
            self.task_list.clear()
            for task in tasks:
                self.task_list.addItem(self._build_item(task))
        finally:
            self._loading = False
        has_tasks = bool(tasks)
        self.task_list.setVisible(has_tasks)
        self.empty_label.setText(EMPTY_HINT_TEXT)
        self.empty_label.setVisible(not has_tasks)

    def _build_item(self, task: TaskRecord) -> QListWidgetItem:
        completed = task.status == STATUS_COMPLETED
        text = task.title
        due_on = getattr(task, "due_on", None)
        if due_on is not None:
            text = f"{text}  ·  截止 {due_on.isoformat()}"
        item = QListWidgetItem(text)
        item.setData(Qt.ItemDataRole.UserRole, task.id)
        flags = Qt.ItemFlag.ItemIsEnabled
        if not completed:
            flags |= Qt.ItemFlag.ItemIsUserCheckable
        item.setFlags(flags)
        item.setCheckState(Qt.CheckState.Checked if completed else Qt.CheckState.Unchecked)
        if completed:
            font = QFont()
            font.setStrikeOut(True)
            item.setFont(font)
            item.setForeground(Qt.GlobalColor.gray)
            item.setToolTip(COMPLETED_TOOLTIP)
        return item

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        if self._loading:
            return
        if item.checkState() != Qt.CheckState.Checked:
            return
        task_id = item.data(Qt.ItemDataRole.UserRole)
        if task_id:
            self.complete(str(task_id))

    # -- helpers --------------------------------------------------------

    def _set_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.setVisible(bool(message))

    def error_message(self) -> str:
        """Return the message currently shown to the user (empty when none)."""
        return "" if self.error_label.isHidden() else self.error_label.text()

    def task_titles(self) -> list[str]:
        """Return the rendered titles, in display order."""
        return [self.task_list.item(row).text() for row in range(self.task_list.count())]
