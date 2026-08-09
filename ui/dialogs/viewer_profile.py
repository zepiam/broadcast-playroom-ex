"""viewer_profile.py — Viewer profile dialog (ประวัติข้อความผู้ชม)"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QWidget, QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QScrollArea, QListWidget, QListWidgetItem,
)
from ui.theme import COLOR_CARD, COLOR_BORDER


class ViewerProfileDialog(QDialog):
    """Viewer profile — ดูประวัติข้อความของผู้ชมรายบุคคล"""

    def __init__(self, author, messages, parent=None):
        super().__init__(parent)
        self.author = author
        self.messages = messages or []
        self.setWindowTitle(f"👤 {author}")
        self.setGeometry(200, 120, 600, 500)
        self.setMinimumSize(480, 360)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ★ Header
        header = QFrame()
        header.setFixedHeight(50)
        header.setStyleSheet(f"background-color: {COLOR_CARD}; border-bottom: 1px solid {COLOR_BORDER};")
        hlayout = QHBoxLayout(header)
        hlayout.setContentsMargins(16, 0, 16, 0)
        title = QLabel(f"👤 {self.author}")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #f59e0b;")
        hlayout.addWidget(title)
        hlayout.addStretch()
        count = QLabel(f"{len(self.messages)} ข้อความ")
        count.setStyleSheet("color: #9ca3af;")
        hlayout.addWidget(count)
        layout.addWidget(header)

        # ★ Message list
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(12, 12, 12, 12)
        self.container_layout.setSpacing(4)

        if not self.messages:
            empty = QLabel("ยังไม่มีประวัติข้อความ")
            empty.setStyleSheet("color: #6b7280; padding: 20px;")
            empty.setAlignment(Qt.AlignCenter)
            self.container_layout.addWidget(empty)
        else:
            for msg in self.messages[-100:]:  # ล่าสุด 100
                text = getattr(msg, 'text', '') or ''
                platform = getattr(msg, 'platform', '')
                row = QLabel(f"[{platform}] {text}")
                row.setStyleSheet("color: #e5e7eb; padding: 4px; border-bottom: 1px solid rgba(42,47,69,0.3);")
                row.setWordWrap(True)
                self.container_layout.addWidget(row)

        self.container_layout.addStretch()
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll, 1)

        # ★ Close
        bottom = QFrame()
        bottom.setFixedHeight(44)
        bottom.setStyleSheet(f"background-color: {COLOR_CARD}; border-top: 1px solid {COLOR_BORDER};")
        blayout = QHBoxLayout(bottom)
        blayout.setContentsMargins(16, 0, 16, 0)
        blayout.addStretch()
        btn = QPushButton("ปิด")
        btn.setFixedWidth(80)
        btn.clicked.connect(self.accept)
        blayout.addWidget(btn)
        layout.addWidget(bottom)
