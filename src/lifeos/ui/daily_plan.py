"""Show a read-only plan based on the user's current pending tasks."""

from __future__ import annotations

from datetime import datetime
from html import escape
from itertools import groupby
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

from lifeos.tasks.daily_plan import build_daily_plan
from lifeos.ui.task_dates import format_deadline

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget

    from lifeos.ui.task_panel import TaskService

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
        self.refresh()

    def refresh(self) -> None:
        self.plan_tree.clear()
        try:
            tasks = self._task_service.list_tasks()
        except RuntimeError:
            self.plan_tree.hide()
            self.status_label.setText("今日计划加载失败，请点击「刷新」重试。")
            return

        plan = build_daily_plan(tasks, now=datetime.now())
        self.plan_tree.setVisible(bool(plan))
        if not plan:
            self.status_label.setText("暂无待办任务。")
            return

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
