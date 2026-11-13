"""Exercise saved task editing through the desktop and a reopened SQLite database."""

from dataclasses import replace
from datetime import date, time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from lifeos.config.settings import Settings
from lifeos.infrastructure.database.engine import create_database
from lifeos.tasks import TaskService
from lifeos.ui.main_window import MainWindow


def test_editing_a_completed_task_persists_details_and_keeps_completion(qtbot, tmp_path):
    from lifeos.ui.completed_tasks import CompletedTasksDialog

    settings = Settings(data_dir=tmp_path)
    database = create_database(settings)
    try:
        database.ensure_schema()
        service = TaskService(database)
        task = service.create_task("实验报告", due_on=date(2000, 2, 29))
        completed = service.complete_task(task.id)

        window = MainWindow("test", True, task_service=service)
        qtbot.addWidget(window)
        window.show()
        panel = window.task_panel
        assert panel.task_titles() == []
        window.completed_tasks_button.click()
        archive = window.findChild(CompletedTasksDialog)
        assert archive is not None and archive.isVisible()
        old_month = archive.task_tree.topLevelItem(0)
        assert old_month.text(0) == "2000 年 2 月"
        archive.task_tree.setCurrentItem(old_month.child(0))
        qtbot.mouseClick(archive.edit_button, Qt.MouseButton.LeftButton)
        editor = window.findChild(QDialog, "taskEditDialog")
        assert editor is not None and editor.isVisible()
        assert editor.title_input.text() == "实验报告"
        assert editor.due_input.text() == "2000-02-29"

        editor.title_input.setText("提交实验报告")
        editor.due_input.setText("2099-12-18 17:30")
        qtbot.mouseClick(editor.save_button, Qt.MouseButton.LeftButton)
        assert panel.task_titles() == []
        assert archive.task_tree.topLevelItemCount() == 1
        new_month = archive.task_tree.topLevelItem(0)
        assert new_month.text(0) == "2099 年 12 月"
        assert new_month.child(0).text(0) == "提交实验报告"
        assert new_month.child(0).text(1) == "2099-12-18 17:30"
        archive.reject()
        window.close()
    finally:
        database.dispose()

    reopened = create_database(settings)
    try:
        assert TaskService(reopened).list_tasks() == [
            replace(
                completed, title="提交实验报告", due_on=date(2099, 12, 18), due_time=time(17, 30)
            )
        ]
    finally:
        reopened.dispose()
