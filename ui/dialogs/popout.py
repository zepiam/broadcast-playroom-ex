"""popout.py — Popout chat window (แยกจอ)"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QWidget, QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QScrollArea,
)
from ui.theme import COLOR_CARD, COLOR_BORDER
from ui.widgets.chat_row import ChatRow


class PopoutWindow(QDialog):
    """Popout chat window — แสดง chat แยกจอ (อ่านอย่างเดียว)"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("💬 Popout Chat")
        self.setGeometry(200, 100, 520, 720)
        self.setMinimumSize(400, 500)
        self.setWindowFlag(Qt.Window, True)  # ไม่ modal
        self._rows = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ★ Header
        header = QFrame()
        header.setFixedHeight(40)
        header.setStyleSheet(f"background-color: {COLOR_CARD}; border-bottom: 1px solid {COLOR_BORDER};")
        hlayout = QHBoxLayout(header)
        hlayout.setContentsMargins(12, 0, 12, 0)
        title = QLabel("💬 แชทสด")
        title.setStyleSheet("font-weight: 600;")
        hlayout.addWidget(title)
        hlayout.addStretch()
        self.viewers_label = QLabel("👥 0")
        self.viewers_label.setStyleSheet("color: #9ca3af; font-size: 12px;")
        hlayout.addWidget(self.viewers_label)
        btn_close = QPushButton("✕")
        btn_close.setObjectName("IconButton")
        btn_close.setFixedSize(32, 32)
        btn_close.clicked.connect(self.close)
        hlayout.addWidget(btn_close)
        layout.addWidget(header)

        # ★ Chat scroll
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(0, 0, 0, 0)
        self.container_layout.setSpacing(0)
        self.container_layout.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll, 1)

    def add_message(self, msg):
        """เพิ่มข้อความเข้า popout — ใหม่สุดอยู่บน"""
        row = ChatRow(msg, self.container)
        self.container_layout.insertWidget(0, row)
        self._rows.append(row)
        # cap 60
        if len(self._rows) > 60:
            old = self._rows.pop(0)
            old.deleteLater()

    def clear_messages(self):
        for row in self._rows:
            row.deleteLater()
        self._rows.clear()

    def update_viewers(self, total):
        self.viewers_label.setText(f"👥 {total:,}")
