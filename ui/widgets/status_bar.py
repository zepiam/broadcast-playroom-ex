"""status_bar.py — Bottom status bar"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QHBoxLayout


class StatusBar(QFrame):
    """Bottom status bar — shows status text"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("StatusBar")
        self.setFixedHeight(26)
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #9ca3af; font-size: 11px;")
        layout.addWidget(self.status_label)

        layout.addStretch()

        self.version_label = QLabel("v2.0.0-dev")
        self.version_label.setStyleSheet("color: #6b7280; font-size: 11px;")
        layout.addWidget(self.version_label)

    def set_status(self, msg):
        self.status_label.setText(msg)

    def set_version(self, ver):
        self.version_label.setText(ver)
