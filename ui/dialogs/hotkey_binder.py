"""hotkey_binder.py — reusable hotkey-capture button for PySide6 dialogs

Instead of typing a hotkey string into a QLineEdit, the user clicks a button,
presses the desired key combination, and it is captured + stored in the
`keyboard` library's format (e.g. ``ctrl+shift+m``).

Public API:
    HotkeyCaptureFilter  — QObject event filter that captures one key combo
    make_hotkey_binder   — convenience factory that wires a QPushButton
"""
from PySide6.QtCore import Qt, QObject, QEvent, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QPushButton

# ── style sync กับ game_overlay_settings.py ──
COL_BG = "#0a0e1a"
COL_CARD = "#131726"
COL_BORDER = "#2a2f45"
COL_TEXT = "#e5e7eb"
COL_ACCENT = "#7c3aed"


# Mapping จาก Qt modifier flag → string token ของ keyboard lib
# (เรียงตามลำดับที่ keyboard lib คาดไว้ — ctrl, alt, shift, windows)
_QT2TOKEN = [
    (Qt.ControlModifier, "ctrl"),
    (Qt.AltModifier, "alt"),
    (Qt.ShiftModifier, "shift"),
    (Qt.MetaModifier, "windows"),
]


def _key_token(qt_key):
    """แปลง Qt.Key → token เดี่ยวของ keyboard lib (lowercase)

    รองรับ: ตัวอักษร, ตัวเลข, F1-F35, ปุ่มพิเศษบางตัว
    คืน None ถ้าเป็น modifier ล้วน (ไม่ใช่ key)
    """
    # F-keys
    if Qt.Key_F1 <= qt_key <= Qt.Key_F35:
        return f"f{qt_key - Qt.Key_F1 + 1}"
    # ตัวอักษร A-Z
    if Qt.Key_A <= qt_key <= Qt.Key_Z:
        return chr(ord('a') + (qt_key - Qt.Key_A))
    # ตัวเลข 0-9 (บนแถวบน)
    if Qt.Key_0 <= qt_key <= Qt.Key_9:
        return chr(ord('0') + (qt_key - Qt.Key_0))
    # numpad 0-9
    if Qt.Key_Keypad0 <= qt_key <= Qt.Key_Keypad9:
        return chr(ord('0') + (qt_key - Qt.Key_Keypad0))
    # พิเศษที่ keyboard lib รู้จัก
    special = {
        Qt.Key_Space: "space",
        Qt.Key_Tab: "tab",
        Qt.Key_Return: "enter",
        Qt.Key_Enter: "enter",
        Qt.Key_Backspace: "backspace",
        Qt.Key_Insert: "insert",
        Qt.Key_Delete: "delete",
        Qt.Key_Home: "home",
        Qt.Key_End: "end",
        Qt.Key_PageUp: "page up",
        Qt.Key_PageDown: "page down",
        Qt.Key_CapsLock: "caps lock",
        Qt.Key_NumLock: "num lock",
        Qt.Key_ScrollLock: "scroll lock",
        Qt.Key_Print: "print screen",
        Qt.Key_Pause: "pause",
        Qt.Key_Left: "left",
        Qt.Key_Right: "right",
        Qt.Key_Up: "up",
        Qt.Key_Down: "down",
        Qt.Key_Minus: "-",
        Qt.Key_Equal: "=",
        Qt.Key_BracketLeft: "[",
        Qt.Key_BracketRight: "]",
        Qt.Key_Backslash: "\\",
        Qt.Key_Semicolon: ";",
        Qt.Key_Apostrophe: "'",
        Qt.Key_Comma: ",",
        Qt.Key_Period: ".",
        Qt.Key_Slash: "/",
        Qt.Key_QuoteLeft: "`",
    }
    return special.get(qt_key)


def format_hotkey(qt_modifiers, qt_key):
    """รวม modifier + key → string รูปแบบ keyboard lib (lowercase)

    คืน None ถ้าไม่มี key หลัก (modifier ล้วน) หรือจับไม่ได้
    """
    token = _key_token(qt_key)
    if token is None:
        return None
    parts = []
    for flag, name in _QT2TOKEN:
        if qt_modifiers & flag:
            parts.append(name)
    parts.append(token)
    return "+".join(parts)


class HotkeyCaptureFilter(QObject):
    """Event filter จับ key press ครั้งถัดไป → emit captured(string) | cancelled()

    ติดตั้งบน widget ที่ต้องการให้รับ focus (ปกติคือปุ่มที่ถูกคลิก)
    Escape = ยกเลิก (emit cancelled)
    Modifier ล้วน = รอ key ถัดไป (ยังไม่ emit)
    """

    captured = Signal(str)
    cancelled = Signal()

    def eventFilter(self, obj, event):
        if event.type() != QEvent.KeyPress:
            return super().eventFilter(obj, event)
        key = event.key()
        # Escape → cancel
        if key == Qt.Key_Escape:
            self.cancelled.emit()
            return True
        # Modifier ล้วน → รอต่อ (ไม่ capture)
        if key in (Qt.Key_Control, Qt.Key_Alt, Qt.Key_Shift, Qt.Key_Meta,
                   Qt.Key_AltGr, Qt.Key_Super_L, Qt.Key_Super_R,
                   Qt.Key_Hyper_L, Qt.Key_Hyper_R):
            return True
        mods = event.modifiers()
        hk = format_hotkey(mods, key)
        if hk:
            self.captured.emit(hk)
        else:
            # จับ key เดี่ยวไม่ได้ (modifier ไม่พอ) → ยังถือว่าจับไม่ได้ รอต่อ
            return True
        return True


def _btn_style():
    return f"""
        QPushButton {{
            background: {COL_BG}; color: {COL_TEXT};
            border: 1px solid {COL_BORDER}; border-radius: 4px;
            padding: 6px 12px; min-height: 22px; font-size: 13px;
            text-align: left;
        }}
        QPushButton:hover {{ border-color: {COL_ACCENT}; }}
        QPushButton[capturing="true"] {{
            background: {COL_ACCENT}; color: #fff; font-weight: 600;
        }}
    """


def make_hotkey_binder(parent_dialog, initial_hotkey, on_captured=None):
    """สร้าง QPushButton binder + คืน button

    - แสดง hotkey ปัจจุบัน (เก็บใน ``btn._hotkey``)
    - คลิก → เข้าสถานะ capture (ข้อความเป็น "กดคีย์ที่ต้องการ...")
    - กดปุ่มผสม → อัปเดต ``btn._hotkey`` + เรียก ``on_captured(str)``
    - Escape → ยกเลิก

    parent_dialog — QDialog ที่เป็นเจ้าของ event filter
    initial_hotkey — string hotkey เริ่มต้น
    on_captured — callable(str) ถ้าต้องการ callback หลังจับได้
    """
    btn = QPushButton(initial_hotkey or "(none)")
    btn._hotkey = (initial_hotkey or "").strip().lower()
    btn.setStyleSheet(_btn_style())
    btn.setMinimumWidth(160)
    btn.setCursor(Qt.PointingHandCursor)
    # ★ เก็บ ref ของ filter ไว้กับ parent (กัน GC)
    if not hasattr(parent_dialog, '_hotkey_filters'):
        parent_dialog._hotkey_filters = []
    parent_dialog._hotkey_filters.append(None)  # placeholder slot

    filter_instance = HotkeyCaptureFilter(btn)
    parent_dialog._hotkey_filters[-1] = filter_instance  # อ้างอิงถึงกัน GC

    def _set_capturing(capturing):
        btn.setProperty("capturing", "true" if capturing else "false")
        if capturing:
            btn.setText("กดคีย์ที่ต้องการ... (Esc = ยกเลิก)")
        else:
            btn.setText(btn._hotkey or "(none)")
        # ★ บังคับ style refresh
        btn.setStyle(btn.style())

    def _on_click():
        _set_capturing(True)
        btn.setFocus()
        btn.installEventFilter(filter_instance)

    def _on_captured(hk):
        btn._hotkey = hk
        _set_capturing(False)
        btn.removeEventFilter(filter_instance)
        if on_captured:
            try:
                on_captured(hk)
            except Exception:
                pass

    def _on_cancelled():
        _set_capturing(False)
        btn.removeEventFilter(filter_instance)

    filter_instance.captured.connect(_on_captured)
    filter_instance.cancelled.connect(_on_cancelled)
    btn.clicked.connect(_on_click)
    btn._set_capturing = _set_capturing
    return btn
