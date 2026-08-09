"""split_button.py — SplitButton widget (button + dropdown arrow)

Layout:
  [main button (text)] [▼ arrow button]
ใช้ 2 QPushButton ใน QHBoxLayout เพื่อให้ emoji/text แสดงผลถูกต้อง
(QToolButton มีปัญหากับ emoji ใน ToolButtonTextOnly mode)

States:
- default: subtle bg (flat)
- state="on": สี accent (ม่วง)
- state="danger": สีแดง
- state="warning": สี amber
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QPushButton, QHBoxLayout, QMenu, QSizePolicy


class SplitButton(QWidget):
    """ปุ่ม split — ปุ่มหลัก + ลูกศร dropdown (ใช้ 2 QPushButton)

    Usage:
        btn = SplitButton("🎮 Game Overlay", tooltip="...", parent=topbar)
        btn.set_menu_actions([
            ("👁 ซ่อนกรอบ", on_edit),
            ("⚙ ตั้งค่า", on_settings),
        ])
        btn.main_clicked.connect(on_toggle)
        btn.set_state("on")   # accent
        btn.set_state("")     # default
    """

    main_clicked = Signal()

    def __init__(self, text="", tooltip="", parent=None, on_click=None):
        super().__init__(parent)
        self.setObjectName("SplitButtonContainer")
        self._state = ""
        self._text = text
        # ★ layout: [main btn] [arrow btn]
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        # main button
        self._main_btn = QPushButton(text)
        self._main_btn.setObjectName("SplitButtonMain")
        self._main_btn.setCursor(Qt.PointingHandCursor)
        self._main_btn.setToolTip(tooltip)
        self._main_btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self._main_btn.clicked.connect(self.main_clicked.emit)
        if on_click:
            self._main_btn.clicked.connect(on_click)
        layout.addWidget(self._main_btn)
        # arrow button
        self._arrow_btn = QPushButton("▾")
        self._arrow_btn.setObjectName("SplitButtonArrow")
        self._arrow_btn.setCursor(Qt.PointingHandCursor)
        self._arrow_btn.setFixedWidth(18)
        self._arrow_btn.setToolTip("ตัวเลือกเพิ่มเติม")
        self._arrow_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._menu = QMenu(self._arrow_btn)
        self._arrow_btn.clicked.connect(self._show_menu)
        layout.addWidget(self._arrow_btn)
        # apply initial state
        self._apply_state()

    def setText(self, text):
        self._text = text
        self._main_btn.setText(text)

    def text(self):
        return self._text

    def setToolTip(self, tip):
        self._main_btn.setToolTip(tip)

    def set_menu_actions(self, actions):
        """ตั้ง menu actions — list of (label, callback) หรือ (label, callback, enabled)

        ใช้ "-" หรือ "—" (string เดี่ยว) หรือ ("—", None) แทนเส้นคั่น
        """
        self._menu.clear()
        for item in actions:
            # ★ separator: string เดี่ยว หรือ tuple ที่ label เป็น - หรือ —
            if isinstance(item, str) and item in ("-", "—"):
                self._menu.addSeparator()
                continue
            if isinstance(item, (tuple, list)) and len(item) >= 1 and item[0] in ("-", "—"):
                self._menu.addSeparator()
                continue
            label = item[0]
            callback = item[1] if len(item) > 1 else None
            enabled = item[2] if len(item) > 2 else True
            act = self._menu.addAction(label)
            act.setEnabled(enabled)
            if callback:
                act.triggered.connect(callback)

    def set_state(self, state):
        """ตั้งสถานะสี: "", "on", "danger", "warning" """
        self._state = state
        self._apply_state()

    def set_active(self, active, state="on"):
        """shortcut: set_state("on" if active else "")"""
        self.set_state(state if active else "")

    def _apply_state(self):
        """apply dynamic property เพื่อ QSS selector ทำงาน"""
        state_val = self._state or "default"
        self._main_btn.setProperty("state", state_val)
        self._arrow_btn.setProperty("state", state_val)
        self._main_btn.style().unpolish(self._main_btn)
        self._main_btn.style().polish(self._main_btn)
        self._arrow_btn.style().unpolish(self._arrow_btn)
        self._arrow_btn.style().polish(self._arrow_btn)

    def _show_menu(self):
        """แสดง dropdown menu ใต้ปุ่ม arrow"""
        btn = self._arrow_btn
        self._menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))
