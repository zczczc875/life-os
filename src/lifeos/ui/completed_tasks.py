"""Browse completed tasks by their deadline or local completion month."""

from __future__ import annotations

from collections import defaultdict
from html import escape
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from lifeos.ui.task_dates import format_deadline
from lifeos.ui.task_panel import (
    COMPLETED_TOOLTIP,
    LATE_COMPLETION_TEXT,
    STATUS_COMPLETED,
    TaskEditDialog,
    completed_after_deadline,
)

if TYPE_CHECKING:
    from datetime import datetime

    from PySide6.QtWidgets import QWidget

    from lifeos.ui.task_panel import TaskRecord, TaskService


class CompletedTasksDialog(QDialog):
    """Show archived task records without changing their stored status."""

    def __init__(self, task_service: TaskService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._task_service = task_service
        self._can_edit = callable(getattr(task_service, "update_task", None))
        self.setObjectName("completedTasksDialog")
        self.setWindowTitle("已完成任务")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(680, 460)

        self.status_label = QLabel(self)
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setWordWrap(True)

        self.task_tree = QTreeWidget(self)
        self.task_tree.setObjectName("completedTasksTree")
        self.task_tree.setAccessibleName("按年月分组的已完成任务")
        self.task_tree.setHeaderLabels(["任务", "截止时间", "完成时间", "状态"])
        self.task_tree.setAlternatingRowColors(True)
        header = self.task_tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.task_tree.itemSelectionChanged.connect(self._update_edit_button)

        self.edit_button = QPushButton("编辑任务", self)
        self.edit_button.setObjectName("editCompletedTaskButton")
        self.edit_button.setVisible(self._can_edit)
        self.edit_button.setAutoDefault(False)
        self.edit_button.clicked.connect(self._open_editor)
        refresh_button = QPushButton("刷新", self)
        refresh_button.setObjectName("refreshCompletedTasksButton")
        refresh_button.setAutoDefault(False)
        refresh_button.clicked.connect(self.refresh)
        close_button = QPushButton("关闭", self)
        close_button.setAutoDefault(False)
        close_button.clicked.connect(self.reject)

        buttons = QHBoxLayout()
        buttons.addWidget(self.edit_button)
        buttons.addStretch()
        buttons.addWidget(refresh_button)
        buttons.addWidget(close_button)
        layout = QVBoxLayout(self)
        layout.addWidget(self.status_label)
        layout.addWidget(self.task_tree, 1)
        layout.addLayout(buttons)
        self.refresh()

    def refresh(self) -> None:
        groups: dict[tuple[int, int], list[tuple[TaskRecord, datetime | None]]] = defaultdict(list)
        try:
            tasks = self._task_service.list_tasks()
        except RuntimeError:
            self._show_empty("已完成任务加载失败，请点击「刷新」重试。")
            return

        for task in tasks:
            if task.status != STATUS_COMPLETED:
                continue
            completed = task.completed_at.astimezone() if task.completed_at is not None else None
            day = task.due_on or (completed.date() if completed is not None else None)
            month = (day.year, day.month) if day is not None else (0, 0)
            groups[month].append((task, completed))
        if not groups:
            self._show_empty("暂无已完成任务。")
            return

        tree = self.task_tree
        old_groups = [tree.topLevelItem(index) for index in range(tree.topLevelItemCount())]
        expanded = {group.text(0) for group in old_groups if group.isExpanded()}
        selected = tree.currentItem()
        selected_id = selected.data(0, Qt.ItemDataRole.UserRole) if selected else None
        tree.clear()
        self.status_label.hide()
        tree.show()
        group_font = tree.font()
        group_font.setBold(True)
        for index, (year, month) in enumerate(sorted(groups, reverse=True)):
            label = f"{year} 年 {month} 月" if year else "日期未知"
            group = QTreeWidgetItem(tree, [label])
            group.setFirstColumnSpanned(True)
            group.setFont(0, group_font)
            group.setExpanded(label in expanded or (not old_groups and index == 0))
            for task, completed in groups[year, month]:
                deadline = format_deadline(task.due_on, task.due_time)
                completed_text = (
                    format_deadline(completed.date(), completed.time()) if completed else ""
                )
                state = (
                    LATE_COMPLETION_TEXT if completed_after_deadline(task) else COMPLETED_TOOLTIP
                )
                row = QTreeWidgetItem(
                    group, [task.title, deadline or "—", completed_text or "—", state]
                )
                row.setToolTip(0, f"<qt>{escape(task.title)}</qt>")
                row.setData(0, Qt.ItemDataRole.UserRole, task.id)
                if task.id == selected_id:
                    group.setExpanded(True)
                    tree.setCurrentItem(row)
        self._update_edit_button()

    def _show_empty(self, message: str) -> None:
        self.task_tree.clear()
        self.task_tree.hide()
        self.status_label.setText(message)
        self.status_label.show()
        self._update_edit_button()

    def _update_edit_button(self) -> None:
        rows = self.task_tree.selectedItems()
        task_id = rows[0].data(0, Qt.ItemDataRole.UserRole) if rows else None
        self.edit_button.setEnabled(self._can_edit and bool(task_id))

    def _open_editor(self) -> None:
        rows = self.task_tree.selectedItems()
        if not self._can_edit or not rows:
            return
        row = rows[0]
        task_id = row.data(0, Qt.ItemDataRole.UserRole)
        if not task_id:
            return
        deadline = row.text(1) if row.text(1) != "—" else ""
        editor = TaskEditDialog(self._task_service, task_id, row.text(0), deadline, self)
        editor.accepted.connect(self.refresh)
        editor.open()
