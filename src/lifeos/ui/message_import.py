"""Review task drafts from a pasted notification."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from lifeos.ai.provider import ProviderError
from lifeos.ui.task_panel import EMPTY_TITLE_MESSAGE, STORAGE_MESSAGE

if TYPE_CHECKING:
    from collections.abc import Callable

    from PySide6.QtWidgets import QWidget

    from lifeos.ai.provider import TaskExtractionResponse
    from lifeos.ui.task_panel import TaskService


class MessageImportDialog(QDialog):
    """Keep editable drafts in memory until the user saves a selected row."""

    task_saved = Signal()

    def __init__(
        self,
        draft_preview: Callable[[str], TaskExtractionResponse],
        task_service: TaskService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._draft_preview = draft_preview
        self._task_service = task_service
        self.setObjectName("messageImportDialog")
        self.setWindowTitle("从通知导入")
        self.resize(520, 510)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        instructions = QLabel("粘贴通知文本，在本机生成任务草稿。重新生成会替换尚未保存的草稿。")
        instructions.setWordWrap(True)
        self.message_input = QPlainTextEdit()
        self.message_input.setPlaceholderText("在此粘贴通知文本")
        self.generate_button = QPushButton("生成草稿")
        self.draft_list = QListWidget()
        self.title_input = QLineEdit()
        self.due_input = QLineEdit()
        self.due_input.setPlaceholderText("YYYY-MM-DD（可留空）")
        self.feedback_label = QLabel()
        self.feedback_label.setTextFormat(Qt.TextFormat.PlainText)
        self.feedback_label.setWordWrap(True)
        self.save_button = QPushButton("保存选中任务")
        close_button = QPushButton("关闭")

        editors = QFormLayout()
        editors.addRow("任务标题", self.title_input)
        editors.addRow("截止日期", self.due_input)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self.save_button)
        buttons.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.addWidget(instructions)
        layout.addWidget(self.message_input, 1)
        layout.addWidget(self.generate_button)
        layout.addWidget(QLabel("待确认草稿"))
        layout.addWidget(self.draft_list, 1)
        layout.addLayout(editors)
        layout.addWidget(self.feedback_label)
        layout.addLayout(buttons)

        for button in (self.generate_button, self.save_button, close_button):
            button.setAutoDefault(False)
        self.generate_button.clicked.connect(self._generate)
        self.draft_list.currentItemChanged.connect(self._load_selected)
        self.title_input.textChanged.connect(self._store_edits)
        self.due_input.textChanged.connect(self._store_edits)
        self.save_button.clicked.connect(self._save_selected)
        close_button.clicked.connect(self.reject)
        self._load_selected(None)

    def _generate(self) -> None:
        message = self.message_input.toPlainText()
        if not message.strip():
            self.feedback_label.setText("请先粘贴通知文本。")
            return
        try:
            response = self._draft_preview(message)
        except ProviderError:
            self.feedback_label.setText("草稿生成失败，请稍后重试。")
            return

        self.draft_list.clear()
        for draft in response.tasks:
            title = draft.title.strip()
            if not title:
                continue
            due_text = draft.due_on.isoformat() if draft.due_on else ""
            item = QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole, (title, due_text))
            self.draft_list.addItem(item)
        if self.draft_list.count():
            self.draft_list.setCurrentRow(0)
            self.feedback_label.setText("选中草稿后，可编辑标题和日期，再保存为任务。")
        else:
            self.feedback_label.setText("没有生成可保存的任务草稿。")

    def _load_selected(self, item: QListWidgetItem | None) -> None:
        title, due_text = item.data(Qt.ItemDataRole.UserRole) if item else ("", "")
        with QSignalBlocker(self.title_input), QSignalBlocker(self.due_input):
            self.title_input.setText(title)
            self.due_input.setText(due_text)
        for widget in (self.title_input, self.due_input, self.save_button):
            widget.setEnabled(item is not None)

    def _store_edits(self) -> None:
        item = self.draft_list.currentItem()
        if item is not None:
            title = self.title_input.text()
            item.setData(Qt.ItemDataRole.UserRole, (title, self.due_input.text()))
            item.setText(title.strip() or "（未填写标题）")

    def _save_selected(self) -> None:
        row = self.draft_list.currentRow()
        if row < 0:
            return
        title = self.title_input.text().strip()
        if not title:
            self.feedback_label.setText(EMPTY_TITLE_MESSAGE)
            return

        due_text = self.due_input.text().strip()
        try:
            due_on = date.fromisoformat(due_text) if due_text else None
            if due_on is not None and due_on.isoformat() != due_text:
                raise ValueError
        except ValueError:
            self.feedback_label.setText("截止日期请输入有效的 YYYY-MM-DD，或留空。")
            return

        try:
            self._task_service.create_task(title, due_on=due_on)
        except (ValueError, RuntimeError):
            self.feedback_label.setText(STORAGE_MESSAGE)
            return

        self.draft_list.takeItem(row)
        self.draft_list.setCurrentRow(-1)
        self.feedback_label.setText("任务已保存。")
        self.task_saved.emit()
