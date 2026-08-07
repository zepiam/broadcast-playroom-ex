"""chat_panel.py — Chat feed panel (QScrollArea + custom rows)"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QScrollArea,
    QWidget, QSizePolicy,
)
from ui.theme import COLOR_CARD, COLOR_TEXT_DIM, COLOR_BORDER
from ui.widgets.chat_row import ChatRow


from ui.widgets.chat_row import ChatRow


class ChatPanel(QFrame):
    """Chat feed — scrollable list of ChatRow"""

    popout_requested = Signal()  # emit เมื่อกดปุ่ม popout
    clear_requested = Signal()   # emit เมื่อกด clear

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ChatPanel")
        self._build_ui()
        self._rows = []

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ★ Header
        header = QFrame()
        header.setFixedHeight(36)
        header.setStyleSheet(f"background-color: {COLOR_CARD}; border-bottom: 1px solid {COLOR_BORDER};")
        hlayout = QHBoxLayout(header)
        hlayout.setContentsMargins(12, 0, 8, 0)
        hlayout.setSpacing(4)
        title = QLabel("💬 แชทสด")
        title.setStyleSheet("font-weight: 600;")
        hlayout.addWidget(title)
        hlayout.addStretch()
        # ★ viewer count
        self.viewers_label = QLabel("👥 0")
        self.viewers_label.setStyleSheet("color: #9ca3af; font-size: 12px;")
        hlayout.addWidget(self.viewers_label)
        # ★ Popout button
        btn_popout = QPushButton("↗")
        btn_popout.setObjectName("IconButton")
        btn_popout.setFixedSize(28, 28)
        btn_popout.setToolTip("แยกจอ")
        btn_popout.setCursor(Qt.PointingHandCursor)
        btn_popout.clicked.connect(self.popout_requested.emit)
        hlayout.addWidget(btn_popout)
        # ★ Clear button
        btn_clear = QPushButton("🗑")
        btn_clear.setObjectName("IconButton")
        btn_clear.setFixedSize(28, 28)
        btn_clear.setToolTip("ล้างแชท")
        btn_clear.setCursor(Qt.PointingHandCursor)
        btn_clear.clicked.connect(self.clear_requested.emit)
        hlayout.addWidget(btn_clear)
        layout.addWidget(header)

        # ★ Scroll area for chat
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(0, 0, 0, 0)
        self.container_layout.setSpacing(0)
        self.container_layout.addStretch()  # push rows up
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll, 1)

    def add_message(self, msg):
        """เพิ่ม chat message ใหม่"""
        row = ChatRow(msg, self.container)
        # insert ก่อน stretch (index -1 = stretch)
        self.container_layout.insertWidget(self.container_layout.count() - 1, row)
        self._rows.append(row)

        # ★ cap rows (เก็บล่าสุด 60)
        max_rows = 60
        if len(self._rows) > max_rows:
            old = self._rows.pop(0)
            old.deleteLater()

        # ★ auto-scroll to bottom
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(
            self.scroll.verticalScrollBar().maximum()
        ))

    def clear_messages(self):
        """ล้าง chat ทั้งหมด"""
        for row in self._rows:
            row.deleteLater()
        self._rows.clear()
