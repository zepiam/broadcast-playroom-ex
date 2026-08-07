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
    block_user_requested = Signal(str)  # emit author for blocking
    author_clicked = Signal(str)  # emit author name for profile/modal

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
        # ★ Font controls (A-/A+ อยู่ใน header เดียวกับ "แชทสด")
        btn_font_dec = QPushButton("A-")
        btn_font_dec.setObjectName("IconButton")
        btn_font_dec.setFixedSize(28, 28)
        btn_font_dec.setCursor(Qt.PointingHandCursor)
        btn_font_dec.setToolTip("ลดขนาดฟอนต์")
        btn_font_dec.setStyleSheet("font-size: 11px; font-weight: bold; padding: 0px;")
        hlayout.addWidget(btn_font_dec)
        btn_font_inc = QPushButton("A+")
        btn_font_inc.setObjectName("IconButton")
        btn_font_inc.setFixedSize(28, 28)
        btn_font_inc.setCursor(Qt.PointingHandCursor)
        btn_font_inc.setToolTip("เพิ่มขนาดฟอนต์")
        btn_font_inc.setStyleSheet("font-size: 11px; font-weight: bold; padding: 0px;")
        hlayout.addWidget(btn_font_inc)
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

        # ★ expose font buttons for external connections
        self.font_dec_btn = btn_font_dec
        self.font_inc_btn = btn_font_inc

        # ★ Scroll area for chat
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

    def add_message(self, msg, font_size=None):
        """เพิ่ม chat message ใหม่ — ใหม่สุดอยู่บน (insert at index 0)
        font_size: ถ้าระบุ → ใช้ขนาดนี้ (สำหรับ font scale)
        """
        fs = font_size or getattr(self, '_current_font_size', 14)
        row = ChatRow(msg, self.container, fs)
        # ★ connect row signals
        row.delete_requested.connect(self._delete_row)
        row.block_user_requested.connect(self.block_user_requested.emit)
        row.author_clicked.connect(self.author_clicked.emit)
        self.container_layout.insertWidget(0, row)
        self._rows.append(row)

        # ★ cap rows (เก็บล่าสุด 60)
        max_rows = 60
        if len(self._rows) > max_rows:
            old = self._rows.pop(0)
            old.deleteLater()

    def clear_messages(self):
        """ล้าง chat ทั้งหมด"""
        for row in self._rows:
            row.deleteLater()
        self._rows.clear()

    def _delete_row(self, row):
        """ลบ row เดียว"""
        if row in self._rows:
            self._rows.remove(row)
            row.deleteLater()
