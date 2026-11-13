from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta, timezone

from PySide6.QtWidgets import QLineEdit, QPushButton

from lifeos.tasks.service import Task
from lifeos.ui.completed_tasks import CompletedTasksDialog
from lifeos.ui.task_panel import TaskEditDialog


class ArchiveService:
    def __init__(self, *tasks):
        self.tasks = list(tasks)
        self.fail = False
        self.edits = []

    def list_tasks(self):
        if self.fail:
            raise RuntimeError("database unavailable")
        return self.tasks

    def update_task(self, task_id, title, *, due_on=None, due_time=None):
        self.edits.append(task_id)
        for index, task in enumerate(self.tasks):
            if task.id == task_id:
                updated = replace(task, title=title, due_on=due_on, due_time=due_time)
                self.tasks[index] = updated
                return updated
        raise LookupError(task_id)


def _task(title, *, due_on=None, due_time=None, completed_at=None, status="completed"):
    return Task(
        title,
        title,
        status,
        datetime(2026, 10, 12, tzinfo=UTC),
        completed_at,
        due_on,
        due_time,
    )


def test_groups_completed_tasks_by_deadline_or_local_completion_month(qtbot):
    class BeijingCompletion(datetime):
        def astimezone(self, tz=None):
            return super().astimezone(tz or timezone(timedelta(hours=8)))

    completion = BeijingCompletion(2026, 10, 31, 17, 15, tzinfo=UTC)
    service = ArchiveService(
        _task("只写截止日期", due_on=date(2026, 9, 30), completed_at=completion),
        _task("未填截止日期", completed_at=completion),
        _task(
            "指定到期时刻", due_on=date(2026, 11, 1), due_time=time(1, 15), completed_at=completion
        ),
        _task("无历史时间"),
        _task("仍在待办", due_on=date(2026, 12, 1), status="pending"),
    )
    dialog = CompletedTasksDialog(service)
    qtbot.addWidget(dialog)
    dialog.show()
    tree = dialog.task_tree
    assert [tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())] == [
        "2026 年 11 月",
        "2026 年 9 月",
        "日期未知",
    ]
    assert tree.topLevelItem(0).isExpanded()
    assert not tree.topLevelItem(1).isExpanded()
    rows = {}
    for group_index in range(tree.topLevelItemCount()):
        group = tree.topLevelItem(group_index)
        for row_index in range(group.childCount()):
            row = group.child(row_index)
            rows[row.text(0)] = (row.text(1), row.text(2), row.text(3))
    assert rows == {
        "指定到期时刻": ("2026-11-01 01:15", "2026-11-01 01:15", "已完成"),
        "未填截止日期": ("—", "2026-11-01 01:15", "已完成"),
        "只写截止日期": ("2026-09-30", "2026-11-01 01:15", "逾期完成"),
        "无历史时间": ("—", "—", "已完成"),
    }
    assert service.edits == []


def test_editing_an_archived_task_regroups_it(qtbot):
    completion = datetime(2026, 10, 31, 17, 15, tzinfo=UTC)
    service = ArchiveService(_task("报告", due_on=date(2026, 10, 23), completed_at=completion))
    dialog = CompletedTasksDialog(service)
    qtbot.addWidget(dialog)
    dialog.show()
    group = dialog.task_tree.topLevelItem(0)
    assert not dialog.edit_button.isEnabled()
    dialog.task_tree.setCurrentItem(group.child(0))
    assert dialog.edit_button.isEnabled()
    dialog.edit_button.click()
    editor = dialog.findChild(TaskEditDialog)
    assert editor is not None
    editor.findChild(QLineEdit, "editTaskTitleInput").setText("修改后的报告")
    editor.findChild(QLineEdit, "editTaskDueInput").setText("2026-12-03 19:00")
    editor.save_button.click()
    assert service.edits == ["报告"]
    assert service.tasks[0].completed_at == completion
    new_group = dialog.task_tree.topLevelItem(0)
    assert new_group.text(0) == "2026 年 12 月"
    assert new_group.isExpanded()
    assert new_group.child(0).text(0) == "修改后的报告"
    assert dialog.task_tree.currentItem() == new_group.child(0)


def test_empty_and_load_failure_can_be_retried(qtbot):
    service = ArchiveService()
    service.fail = True
    dialog = CompletedTasksDialog(service)
    qtbot.addWidget(dialog)
    dialog.show()
    assert dialog.task_tree.isHidden()
    assert "加载失败" in dialog.status_label.text()
    assert not dialog.edit_button.isEnabled()

    service.fail = False
    dialog.findChild(QPushButton, "refreshCompletedTasksButton").click()
    assert dialog.status_label.text() == "暂无已完成任务。"
    assert dialog.task_tree.isHidden()
