"""events_panel.py — Events panel (collapsible, right side)"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QScrollArea,
    QWidget,
)
from ui.theme import COLOR_CARD, COLOR_BORDER, COLOR_ACCENT, COLOR_HEADING


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
        label.setStyleSheet("font-size: 12px;")
        label.setWordWrap(True)
        layout.addWidget(label)


class EventsPanel(QFrame):
    """Events panel — collapsible right sidebar"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("EventsPanel")
        self.setFixedWidth(220)
        self._collapsed = False
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ★ Header (clickable to toggle collapse)
        self.header = QPushButton("📊 Events")
        self.header.setObjectName("IconButton")
        self.header.setFixedHeight(36)
        self.header.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_CARD};
                border: none;
                border-bottom: 1px solid {COLOR_BORDER};
                text-align: left;
                padding: 0 12px;
                font-weight: 600;
                color: {COLOR_HEADING};
            }}
            QPushButton:hover {{ background-color: #1a1f33; }}
        """)
        self.header.clicked.connect(self.toggle_collapse)
        layout.addWidget(self.header)

        # ★ Events list
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(6, 6, 6, 6)
        self.container_layout.setSpacing(4)
        self.container_layout.addStretch()
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll, 1)

    def toggle_collapse(self):
        self._collapsed = not self._collapsed
        if self._collapsed:
            self.setFixedWidth(38)
            self.header.setText("📊")
            self.scroll.setVisible(False)
        else:
            self.setFixedWidth(220)
            self.header.setText("📊 Events")
            self.scroll.setVisible(True)

    def add_event(self, event_type, text):
        """เพิ่ม event ใหม่ (ใหม่สุดอยู่บน)"""
        card = EventCard(event_type, text, self.container)
        self.container_layout.insertWidget(0, card)
        # cap (เก็บล่าสุด 50)
        while self.container_layout.count() > 51:
            item = self.container_layout.takeAt(self.container_layout.count() - 2)
            if item.widget():
                item.widget().deleteLater()
