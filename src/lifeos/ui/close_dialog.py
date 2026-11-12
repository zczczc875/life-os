"""Ask how LifeOS should handle closing its main window."""

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from lifeos.config.close_preferences import CloseAction


class CloseDialog(QDialog):
    def __init__(self, tray_available: bool, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("关闭 LifeOS")
        self.action: CloseAction | None = None

        explanation = (
            "最小化到托盘后，LifeOS 会在后台继续运行。" if tray_available else "系统托盘暂不可用。"
        )
        label = QLabel(explanation, self)
        label.setWordWrap(True)
        self.remember = QCheckBox("以后不再提醒", self)
        self.remember.setObjectName("rememberCloseAction")

        tray_button = QPushButton("最小化到托盘", self)
        tray_button.setObjectName("minimizeToTrayButton")
        tray_button.setEnabled(tray_available)
        tray_button.setDefault(tray_available)
        tray_button.clicked.connect(lambda: self._choose("tray"))
        exit_button = QPushButton("直接关闭", self)
        exit_button.setObjectName("exitLifeOSButton")
        exit_button.setAutoDefault(False)
        exit_button.clicked.connect(lambda: self._choose("exit"))

        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(tray_button)
        buttons.addWidget(exit_button)
        layout = QVBoxLayout(self)
        layout.addWidget(label)
        layout.addWidget(self.remember)
        layout.addLayout(buttons)
        self.setMinimumWidth(320)

    def _choose(self, action: CloseAction) -> None:
        self.action = action
        self.accept()
