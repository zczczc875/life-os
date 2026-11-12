"""Show a read-only plan based on the user's current pending tasks."""

from __future__ import annotations

from datetime import datetime
from html import escape
from itertools import groupby
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer
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

from lifeos.tasks.daily_plan import build_daily_plan
from lifeos.ui.task_dates import format_deadline

if TYPE_CHECKING:
    from collections.abc import Sequence

    from PySide6.QtWidgets import QWidget

    from lifeos.tasks.daily_plan import PlannedTask
    from lifeos.ui.task_panel import TaskRecord, TaskService

_BUCKET_LABELS = {
    "overdue": "已逾期",
    "today": "今天到期",
    "this_week": "本周到期",
    "later": "之后到期",
    "unscheduled": "未设截止日期",
}
_PRIORITY_LABELS = {"high": "高", "medium": "中", "low": "低"}
_SUGGESTION_LIMIT = 3


class DailyPlanDialog(QDialog):
    """List pending tasks once, with the first few marked as today's suggestions."""

    def __init__(self, task_service: TaskService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._task_service = task_service
        self._tasks: Sequence[TaskRecord] | None = None
        self._plan: list[PlannedTask] | None = None
        self.setObjectName("dailyPlanDialog")
        self.setWindowTitle("今日计划")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(600, 420)

        self.status_label = QLabel(self)
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setWordWrap(True)
        self.plan_tree = QTreeWidget(self)
        self.plan_tree.setObjectName("dailyPlanTree")
        self.plan_tree.setAccessibleName("按截止时间分组的待办任务")
        self.plan_tree.setHeaderLabels(["任务", "截止时间", "优先级", "今日建议"])
        self.plan_tree.setAlternatingRowColors(True)
        header = self.plan_tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        self.refresh_button = QPushButton("刷新", self)
        close_button = QPushButton("关闭", self)
        self.refresh_button.setAutoDefault(False)
        close_button.setAutoDefault(False)
        self.refresh_button.clicked.connect(self.refresh)
        close_button.clicked.connect(self.reject)

        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self.refresh_button)
        buttons.addWidget(close_button)
        layout = QVBoxLayout(self)
        layout.addWidget(self.status_label)
        layout.addWidget(self.plan_tree, 1)
        layout.addLayout(buttons)

        self._deadline_timer = QTimer(self)
        self._deadline_timer.setInterval(60_000)
        self._deadline_timer.timeout.connect(self._render_plan)
        self.refresh()

    def refresh(self) -> None:
        try:
            self._tasks = self._task_service.list_tasks()
        except RuntimeError:
            self._tasks = None
            self._plan = None
            self._deadline_timer.stop()
            self.plan_tree.clear()
            self.plan_tree.hide()
            self.status_label.setText("今日计划加载失败，请点击「刷新」重试。")
            return

        self._render_plan()

    def _render_plan(self) -> None:
        if self._tasks is None:
            return
        plan = build_daily_plan(self._tasks, now=datetime.now())
        if plan == self._plan:
            return
        self._plan = plan
        self.plan_tree.clear()
        self.plan_tree.setVisible(bool(plan))
        if not plan:
            self._deadline_timer.stop()
            self.status_label.setText("暂无待办任务。")
            return

        if not self._deadline_timer.isActive():
            self._deadline_timer.start()
        suggestion_count = min(_SUGGESTION_LIMIT, len(plan))
        self.status_label.setText(f"从 {len(plan)} 项待办中选出 {suggestion_count} 项今日建议。")
        for bucket, entries in groupby(enumerate(plan), key=lambda entry: entry[1].bucket):
            group = QTreeWidgetItem(self.plan_tree, [_BUCKET_LABELS[bucket]])
            group.setFirstColumnSpanned(True)
            font = self.plan_tree.font()
            font.setBold(True)
            group.setFont(0, font)
            for index, task in entries:
                item = QTreeWidgetItem(
                    group,
                    [
                        task.title,
                        format_deadline(task.due_on, task.due_time) or "—",
                        _PRIORITY_LABELS[task.priority],
                        "建议" if index < suggestion_count else "",
                    ],
                )
                item.setToolTip(0, f"<qt>{escape(task.title)}</qt>")
            group.setExpanded(True)
