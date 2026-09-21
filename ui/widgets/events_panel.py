"""events_panel.py — Events panel (collapsible, right side)

★ collapse behavior: กด › (ขวาบน) → ซ่อน panel ทั้งหมด เหลือแค่แถบบางๆ ทางขวา
  มีปุ่مة ‹ (ลูกศรซ้าย) ให้กดกลับมาโชว์ panel ได้
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QScrollArea,
    QWidget, QSizePolicy,
)
import ui.theme as theme  # ★ theme.styled(): สีตามธีม + รีเฟรชสดเมื่อสลับธีม


class EventCard(QFrame):
    """แถว event 1 รายการ — กดเพื่อดูรายละเอียด (ใครให้ / เท่าไหร่ / ซับกี่เดือน / มอบให้ใคร / ข้อความแนบ)

    ข้อมูลมาจาก event_details.build_info() (dict `info`) — ไม่มี info ก็แสดงแบบย่อจาก text เหมือนเดิม
    สีตามธีม (import ui.theme / ui.user_kit ตอนสร้าง ไม่ freeze ค่า)
    """
    clicked = Signal(dict)

    _ICONS = {"sub": "⭐", "bits": "💎", "raid": "🚀", "donate": "💰", "follow": "❤️"}
    _CAT_ROLE = {"money": "supporter", "sub": "accent", "gift": "info", "other": "info"}

    def __init__(self, event_type, text, parent=None, info=None):
        super().__init__(parent)
        from ui.user_kit import C, role, dim_text, faint_text, rgba
        from ui.platform_icons import get_platform_pixmap
        self.setObjectName("EventCard")
        self.info = dict(info) if info else {
            "event": event_type, "headline": text, "author": "", "fields": [], "message": "",
            "icon": self._ICONS.get(event_type, "🔔"), "category": "other", "label": event_type,
        }
        info = self.info
        self._cat_key = self._CAT_ROLE.get(info.get("category", "other"), "info")
        self._w_name = self._w_time = self._w_head = self._w_prev = None
        self.setCursor(Qt.PointingHandCursor if info.get("author") else Qt.ArrowCursor)
        self.setToolTip("คลิกเพื่อดูรายละเอียด" if info.get("author") else "")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 7, 8, 7)
        lay.setSpacing(2)

        top = QHBoxLayout()
        top.setSpacing(5)
        icon = QLabel(info.get("icon", "🔔"))
        icon.setStyleSheet("font-size: 14px; background: transparent; border: none; min-height: 0;")
        top.addWidget(icon)
        name = QLabel(info.get("author") or text)
        self._w_name = name
        name.setMinimumWidth(10)
        top.addWidget(name, 1)
        plat = info.get("platform")
        if plat:
            pm = get_platform_pixmap(plat, 14)
            if not pm.isNull():
                pl = QLabel()
                pl.setPixmap(pm)
                pl.setStyleSheet("background: transparent; border: none;")
                top.addWidget(pl)
        ts = info.get("ts") or ""
        if len(ts) >= 16:
            tl = QLabel(ts[11:16])
            self._w_time = tl
            top.addWidget(tl)
        lay.addLayout(top)

        head = QLabel(info.get("headline") or text)
        head.setWordWrap(True)
        self._w_head = head
        lay.addWidget(head)

        msg = (info.get("message") or "").strip()
        if msg:
            prev = QLabel("“" + (msg if len(msg) <= 70 else msg[:68] + "…") + "”")
            prev.setWordWrap(True)
            self._w_prev = prev
            lay.addWidget(prev)
        self.restyle()
        theme.register_theme_listener(self.restyle)     # ★ การ์ดที่มีอยู่แล้วเปลี่ยนสีตามธีมใหม่สดๆ

    def restyle(self):
        """ตั้ง/รีเฟรชสีของการ์ดตามธีมปัจจุบัน (เรียกตอนสร้าง + ทุกครั้งที่สลับธีม)"""
        from ui.user_kit import C, role, dim_text, faint_text
        R = role(self._cat_key)
        self.setStyleSheet(
            f"QFrame#EventCard {{ background-color: {C('CARD')}; border: 1px solid {C('BORDER')}; "
            f"border-left: 4px solid {R['solid']}; border-radius: 8px; }}"
            f"QFrame#EventCard:hover {{ background-color: {C('CARD_HOVER')}; border-color: {R['solid']}; }}")
        if self._w_name is not None:
            self._w_name.setStyleSheet(f"font-size: 13px; font-weight: 700; color: {C('TEXT')}; background: transparent; border: none; min-height: 0;")
        if self._w_time is not None:
            self._w_time.setStyleSheet(f"font-size: 11px; color: {faint_text()}; background: transparent; border: none; min-height: 0;")
        if self._w_head is not None:
            self._w_head.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {R['text_on_card']}; background: transparent; border: none; min-height: 0;")
        if self._w_prev is not None:
            self._w_prev.setStyleSheet(f"font-size: 12px; color: {dim_text()}; background: transparent; border: none; min-height: 0;")

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.info.get("author") and self.rect().contains(e.position().toPoint()):
            self.clicked.emit(self.info)
        super().mouseReleaseEvent(e)


class EventsPanel(QFrame):
    """Events panel — collapsible right sidebar

    ★ 2 states:
      - expanded: panel เต็ม + header (title + ‹ ซ่อน)
      - collapsed: แถบบางๆ ขวาสุด มีแค่ › (กดกลับมาโชว์)
    """

    collapsed_toggled = Signal(bool)  # ★ emit เมื่อ collapse state เปลี่ยน (เพื่อ save)
    event_clicked = Signal(dict)      # ★ กดการ์ด event → info dict (app เปิดหน้ารายละเอียด)

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
        theme.styled(header_row, "background-color: #131726; border-bottom: 1px solid #2a2f45;")
        h_layout = QHBoxLayout(header_row)
        h_layout.setContentsMargins(12, 0, 4, 0)
        h_layout.setSpacing(4)
        self.title_label = QLabel("📊 Events (0)")
        theme.styled(self.title_label, "font-weight: 600; color: #f59e0b; font-size: 14px; border: none; background: transparent;")
        h_layout.addWidget(self.title_label)
        h_layout.addStretch()
        # ★ ปุ่ม ‹ (ซ่อน panel)
        self.btn_collapse = QPushButton("›")
        self.btn_collapse.setObjectName("IconButton")
        self.btn_collapse.setFixedSize(28, 28)
        self.btn_collapse.setCursor(Qt.PointingHandCursor)
        self.btn_collapse.setToolTip("ซ่อนแผง Events")
        theme.styled(self.btn_collapse, """
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
        theme.styled(self.btn_expand, """
            QPushButton {
                border: none;
                background-color: #131726;
                border-left: 1px solid #2a2f45;
                font-size: 20px;
                font-weight: 700;
                color: #9ca3af;
                padding: 0;
            }
            QPushButton:hover { color: #f59e0b; background-color: #1a1f33; }
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

    def add_event(self, event_type, text, info=None):
        """เพิ่ม event ใหม่ (ใหม่สุดอยู่บน) — info = event_details.build_info() (ไม่ใส่ = แสดงแบบย่อ)"""
        card = EventCard(event_type, text, self.container, info=info)
        card.clicked.connect(self.event_clicked.emit)
        self.container_layout.insertWidget(0, card)
        # cap (เก็บล่าสุด 50)
        while self.container_layout.count() > 51:
            item = self.container_layout.takeAt(self.container_layout.count() - 2)
            if item.widget():
                item.widget().deleteLater()
        # ★ update title count
        count = self.container_layout.count() - 1  # -1 for stretch
        self.title_label.setText(f"📊 Events ({count})")
