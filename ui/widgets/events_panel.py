"""events_panel.py — Events panel (collapsible, right side)

★ collapse behavior: กด › (ขวาบน) → ซ่อน panel ทั้งหมด เหลือแค่แถบบางๆ ทางขวา
  มีปุ่مة ‹ (ลูกศรซ้าย) ให้กดกลับมาโชว์ panel ได้
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QScrollArea,
    QWidget, QSizePolicy,
)
from ui.theme import COLOR_CARD, COLOR_BORDER, COLOR_HEADING


class EventCard(QFrame):
    """Single event row (sub/bits/raid/etc)"""

    def __init__(self, event_type, text, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)

        icon_map = {"sub": "⭐", "bits": "💎", "raid": "🚀", "donate": "💰", "follow": "❤️"}
        icon = icon_map.get(event_type, "🔔")
        label = QLabel(f"{icon} {text}")
        label.setStyleSheet("font-size: 14px;")
        label.setWordWrap(True)
        layout.addWidget(label)


class EventsPanel(QFrame):
    """Events panel — collapsible right sidebar

    ★ 2 states:
      - expanded: panel เต็ม + header (title + ‹ ซ่อน)
      - collapsed: แถบบางๆ ขวาสุด มีแค่ › (กดกลับมาโชว์)
    """

    collapsed_toggled = Signal(bool)  # ★ emit เมื่อ collapse state เปลี่ยน (เพื่อ save)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("EventsPanel")
        self._collapsed = False
        self._build_ui()
        self._apply_state()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ═══ Expanded content (header + scroll) ═══
        self.expanded_widget = QWidget(self)
        exp_layout = QVBoxLayout(self.expanded_widget)
        exp_layout.setContentsMargins(0, 0, 0, 0)
        exp_layout.setSpacing(0)

        # ★ Header: [📊 Events (N)] ........ [‹ ซ่อน]
        header_row = QFrame()
        header_row.setFixedHeight(36)
        header_row.setStyleSheet(f"background-color: {COLOR_CARD}; border-bottom: 1px solid {COLOR_BORDER};")
        h_layout = QHBoxLayout(header_row)
        h_layout.setContentsMargins(12, 0, 4, 0)
        h_layout.setSpacing(4)
        self.title_label = QLabel("📊 Events (0)")
        self.title_label.setStyleSheet(f"font-weight: 600; color: {COLOR_HEADING}; font-size: 14px; border: none; background: transparent;")
        h_layout.addWidget(self.title_label)
        h_layout.addStretch()
        # ★ ปุ่ม ‹ (ซ่อน panel)
        self.btn_collapse = QPushButton("›")
        self.btn_collapse.setObjectName("IconButton")
        self.btn_collapse.setFixedSize(28, 28)
        self.btn_collapse.setCursor(Qt.PointingHandCursor)
        self.btn_collapse.setToolTip("ซ่อนแผง Events")
        self.btn_collapse.setStyleSheet("""
            QPushButton { border: none; background: transparent; font-size: 18px; font-weight: 700; color: #9ca3af; padding: 0; }
            QPushButton:hover { color: #f59e0b; }
        """)
        self.btn_collapse.clicked.connect(self.collapse)
        h_layout.addWidget(self.btn_collapse)
        exp_layout.addWidget(header_row)

        # ★ Events list
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QFrame.NoFrame)

        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(6, 6, 6, 6)
        self.container_layout.setSpacing(4)
        self.container_layout.addStretch()
        self.scroll.setWidget(self.container)
        exp_layout.addWidget(self.scroll, 1)
        layout.addWidget(self.expanded_widget, 1)

        # ═══ Collapsed bar (แค่ปุ่ม ‹ กลับมาโชว์) ═══
        self.collapsed_widget = QWidget(self)
        col_layout = QVBoxLayout(self.collapsed_widget)
        col_layout.setContentsMargins(0, 0, 0, 0)
        col_layout.setSpacing(0)
        self.btn_expand = QPushButton("‹")
        self.btn_expand.setObjectName("IconButton")
        self.btn_expand.setCursor(Qt.PointingHandCursor)
        self.btn_expand.setToolTip("แสดงแผง Events")
        self.btn_expand.setStyleSheet(f"""
            QPushButton {{
                border: none;
                background-color: {COLOR_CARD};
                border-left: 1px solid {COLOR_BORDER};
                font-size: 20px;
                font-weight: 700;
                color: #9ca3af;
                padding: 0;
            }}
            QPushButton:hover {{ color: #f59e0b; background-color: #1a1f33; }}
        """)
        self.btn_expand.clicked.connect(self.expand)
        col_layout.addWidget(self.btn_expand)
        layout.addWidget(self.collapsed_widget)

    # ═══ State management ═══
    def _apply_state(self):
        """apply collapse state → show/hide widgets + adjust size

        ★ collapsed → setVisible(False) ทั้ง panel → QSplitter จะไม่เสนอพื้นที่/handle
          (chat_panel จะขยายเต็มที่) — ปุ่ม ‹ ลอยอยู่ที่ main window (จัดการใน app.py)
        """
        if self._collapsed:
            self.setVisible(False)
        else:
            self.collapsed_widget.setVisible(False)
            self.expanded_widget.setVisible(True)
            self.setVisible(True)
            self.setMinimumWidth(180)
            self.setMaximumWidth(300)
            self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

    def collapse(self):
        """ซ่อน panel ทั้งหมด (chat_panel ขยายเต็มที่) — ปุ่ม ‹ ลอยที่ main window"""
        if self._collapsed:
            return
        self._collapsed = True
        self._apply_state()
        self.collapsed_toggled.emit(True)

    def expand(self):
        """โชว์ panel กลับมา"""
        if not self._collapsed:
            return
        self._collapsed = False
        self._apply_state()
        self.collapsed_toggled.emit(False)

    def toggle_collapse(self):
        """toggle (backward-compat — เรียกจาก app.py)"""
        if self._collapsed:
            self.expand()
        else:
            self.collapse()

    @property
    def is_collapsed(self):
        return self._collapsed

    def add_event(self, event_type, text):
        """เพิ่ม event ใหม่ (ใหม่สุดอยู่บน)"""
        card = EventCard(event_type, text, self.container)
        self.container_layout.insertWidget(0, card)
        # cap (เก็บล่าสุด 50)
        while self.container_layout.count() > 51:
            item = self.container_layout.takeAt(self.container_layout.count() - 2)
            if item.widget():
                item.widget().deleteLater()
        # ★ update title count
        count = self.container_layout.count() - 1  # -1 for stretch
        self.title_label.setText(f"📊 Events ({count})")
