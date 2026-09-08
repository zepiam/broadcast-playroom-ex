"""theme.py — QSS stylesheet + color constants + font setup (PySide6)

Modern flat design — Discord/Spotify style dark theme
เก็บ color palette เดิมจาก v1 (เพราะคุ้นเคย + สวยอยู่แล้ว)
"""
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

# ═══════════════════════════════════════════════════════════════
# Themes — palette ต่อธีม (ui_theme ใน settings เก็บ key ในนี้)
# ★ "default" = ค่าเดิมจาก v1 เป๊ะๆ ทุกตัว (ห้ามแก้ค่าพวกนี้ — ผู้ใช้เดิมต้องไม่เห็นอะไรเปลี่ยน
#   ถ้าไม่ได้เข้าไปเลือกธีมใหม่เองใน Settings)
# ═══════════════════════════════════════════════════════════════
THEMES = {
    "default": {
        "BG": "#0a0e1a", "BG_DARK": "#060912", "CARD": "#131726",
        "CARD_HI": "#1a1f33", "CARD_HOVER": "#1e2438",
        "ACCENT": "#7c3aed", "ACCENT_HOVER": "#6d28d9", "ACCENT_2": "#06b6d4",
        "HEADING": "#f59e0b",
        "DANGER": "#ef4444", "DANGER_HOVER": "#dc2626",
        "SUCCESS": "#10b981", "SUCCESS_HOVER": "#059669",
        "TEXT": "#e5e7eb", "TEXT_DIM": "#9ca3af", "TEXT_FAINT": "#6b7280",
        "BORDER": "#2a2f45", "BORDER_LIGHT": "#374151",
    },
    "aurora_violet": {
        "BG": "#0d0b1a", "BG_DARK": "#08060f", "CARD": "#181430",
        "CARD_HI": "#211c3d", "CARD_HOVER": "#251f45",
        "ACCENT": "#8b5cf6", "ACCENT_HOVER": "#7c3aed", "ACCENT_2": "#22d3ee",
        "HEADING": "#c4b5fd",
        "DANGER": "#f87171", "DANGER_HOVER": "#ef4444",
        "SUCCESS": "#34d399", "SUCCESS_HOVER": "#10b981",
        "TEXT": "#ece9f7", "TEXT_DIM": "#b4aecb", "TEXT_FAINT": "#8b87a3",
        "BORDER": "#332b52", "BORDER_LIGHT": "#453a6e",
    },
    "ember_dusk": {
        "BG": "#17110d", "BG_DARK": "#100c09", "CARD": "#201611",
        "CARD_HI": "#2a1d15", "CARD_HOVER": "#33241a",
        "ACCENT": "#ea580c", "ACCENT_HOVER": "#c2410c", "ACCENT_2": "#fb923c",
        "HEADING": "#fbbf24",
        "DANGER": "#dc2626", "DANGER_HOVER": "#991b1b",
        "SUCCESS": "#16a34a", "SUCCESS_HOVER": "#15803d",
        "TEXT": "#f5ece2", "TEXT_DIM": "#c9b5a1", "TEXT_FAINT": "#8a7562",
        "BORDER": "#3d2a1c", "BORDER_LIGHT": "#4d3624",
    },
    "nightwave_cyan": {
        "BG": "#070c0f", "BG_DARK": "#04080a", "CARD": "#0a1417",
        "CARD_HI": "#0d1a1e", "CARD_HOVER": "#112128",
        "ACCENT": "#22d3ee", "ACCENT_HOVER": "#0e7490", "ACCENT_2": "#67e8f9",
        "HEADING": "#22d3ee",
        "DANGER": "#f87171", "DANGER_HOVER": "#dc2626",
        "SUCCESS": "#4ade80", "SUCCESS_HOVER": "#22c55e",
        "TEXT": "#dbe7ea", "TEXT_DIM": "#8fb0b6", "TEXT_FAINT": "#4d6469",
        "BORDER": "#16292e", "BORDER_LIGHT": "#1c383f",
    },
}

THEME_ORDER = ["default", "aurora_violet", "ember_dusk", "nightwave_cyan"]
THEME_LABELS = {
    "default": "ค่าเริ่มต้น (ม่วง-กรมท่า)",
    "aurora_violet": "Aurora Violet",
    "ember_dusk": "Ember Dusk",
    "nightwave_cyan": "Nightwave Cyan",
}
# ★ swatch สีเด่นของแต่ละธีม (ใช้โชว์ preview ใน Settings)
THEME_SWATCH = {k: v["ACCENT"] for k, v in THEMES.items()}


def _luma(hex_color: str) -> float:
    """ความสว่างคร่าวๆ ของสี hex (0=ดำ, 255=ขาว) — ใช้เลือกสีตัวอักษรที่อ่านออก"""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (r * 299 + g * 587 + b * 114) / 1000


def _readable_on(hex_color: str, dark: str = "#0b0e14", light: str = "#ffffff") -> str:
    """เลือกสีตัวอักษรที่อ่านง่ายบนพื้น hex_color — พื้นสว่างเกิน threshold ใช้ตัวหนังสือเข้มแทนขาว

    ★ Qt Style Sheets ไม่รองรับ text-shadow/box-shadow (ไม่อยู่ใน property ที่ QSS รองรับเลย)
      วิธีแก้ contrast ที่ถูกต้องคือสลับสีตัวอักษรตามความสว่างพื้นหลัง แทนการใส่เงา
    """
    return dark if _luma(hex_color) > 150 else light


# ★ เติมสีตัวอักษรที่อ่านออกให้ทุกธีม (คำนวณจาก ACCENT/DANGER/SUCCESS/HEADING ของธีมนั้นๆ)
#   ใช้กับปุ่ม state="on"/"danger"/"warning" (topbar split-button) + ปุ่ม TTS เขียว/แดง
for _key, _pal in THEMES.items():
    _pal["ON_ACCENT_TEXT"] = _readable_on(_pal["ACCENT"])
    _pal["ON_DANGER_TEXT"] = _readable_on(_pal["DANGER"])
    _pal["ON_SUCCESS_TEXT"] = _readable_on(_pal["SUCCESS"])
    _pal["ON_WARNING_TEXT"] = _readable_on(_pal["HEADING"])

# ═══════════════════════════════════════════════════════════════
# Color constants (module-level) — apply_theme() จะเขียนทับตัวแปรพวกนี้
# ตาม theme ที่เลือกไว้ใน settings ตอนเปิดโปรแกรม (ก่อนสร้าง widget ใดๆ)
# ★ ไฟล์ widget อื่นที่ต้องการสีให้ตรงธีมสด ต้อง `import ui.theme as theme` แล้วอ้าง
#   `theme.COLOR_X` ตอนสร้าง widget (ไม่ใช่ `from ui.theme import COLOR_X` ที่ตายตัว
#   ตั้งแต่ตอน import module — ค่าจะไม่ขยับตามถ้า apply_theme() มาทีหลัง)
# ═══════════════════════════════════════════════════════════════
COLOR_BG = THEMES["default"]["BG"]
COLOR_BG_DARK = THEMES["default"]["BG_DARK"]
COLOR_CARD = THEMES["default"]["CARD"]
COLOR_CARD_HI = THEMES["default"]["CARD_HI"]
COLOR_CARD_HOVER = THEMES["default"]["CARD_HOVER"]
COLOR_ACCENT = THEMES["default"]["ACCENT"]
COLOR_ACCENT_HOVER = THEMES["default"]["ACCENT_HOVER"]
COLOR_ACCENT_2 = THEMES["default"]["ACCENT_2"]
COLOR_HEADING = THEMES["default"]["HEADING"]
COLOR_DANGER = THEMES["default"]["DANGER"]
COLOR_DANGER_HOVER = THEMES["default"]["DANGER_HOVER"]
COLOR_SUCCESS = THEMES["default"]["SUCCESS"]
COLOR_SUCCESS_HOVER = THEMES["default"]["SUCCESS_HOVER"]
COLOR_TEXT = THEMES["default"]["TEXT"]
COLOR_TEXT_DIM = THEMES["default"]["TEXT_DIM"]
COLOR_TEXT_FAINT = THEMES["default"]["TEXT_FAINT"]
COLOR_BORDER = THEMES["default"]["BORDER"]
COLOR_BORDER_LIGHT = THEMES["default"]["BORDER_LIGHT"]
COLOR_ON_ACCENT_TEXT = THEMES["default"]["ON_ACCENT_TEXT"]
COLOR_ON_DANGER_TEXT = THEMES["default"]["ON_DANGER_TEXT"]
COLOR_ON_SUCCESS_TEXT = THEMES["default"]["ON_SUCCESS_TEXT"]
COLOR_ON_WARNING_TEXT = THEMES["default"]["ON_WARNING_TEXT"]

# ═══════════════════════════════════════════════════════════════
# Fonts
# ═══════════════════════════════════════════════════════════════
def setup_fonts(app: QApplication) -> None:
    """ตั้ง font default + โหลด Kanit + NotoSansThai (fallback ภาษาไทย)"""
    import os, sys
    # ★ หา assets/fonts path — รองรับทั้ง dev + PyInstaller frozen
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        fonts_dir = os.path.join(exe_dir, "_internal", "assets", "fonts")
        if not os.path.isdir(fonts_dir):
            fonts_dir = os.path.join(exe_dir, "assets", "fonts")
    else:
        fonts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "fonts")

    # ★ โหลด Kanit (ถ้ามี) + NotoSansThai (fallback ภาษาไทย — ติดมากับโปรแกรมเสมอ)
    font_files = [
        "Kanit-Regular.ttf", "Kanit-Medium.ttf", "Kanit-SemiBold.ttf", "Kanit-Bold.ttf",
        "NotoSansThai-Regular.ttf", "NotoSansThai-Medium.ttf", "NotoSansThai-Bold.ttf",
    ]
    for fname in font_files:
        p = os.path.join(fonts_dir, fname)
        if os.path.exists(p):
            QFontDatabase.addApplicationFont(p)

    # ★ default font — Kanit ถ้ามี, ถ้าไม่มี Qt จะ fallback เป็น NotoSansThai อัตโนมัติ
    font = QFont("Kanit", 11)
    font.setStyleHint(QFont.SansSerif)
    app.setFont(font)


# ═══════════════════════════════════════════════════════════════
# QSS Stylesheet — Modern Flat Design
# ═══════════════════════════════════════════════════════════════
QSS = """
/* ═══ Global ═══ */
* {
    font-family: 'Kanit', 'Noto Sans Thai', 'Segoe UI', sans-serif;
    color: __TEXT__;
    outline: none;
}

QWidget {
    background-color: __BG__;
    font-size: 16px;
}

/* ★ label — ไม่ตัดความสูง */
QLabel {
    background-color: transparent;
    color: __TEXT__;
    min-height: 20px;
    font-size: 16px;
}

/* ═══ Windows ═══ */
QMainWindow, QDialog {
    background-color: __BG__;
}

/* ═══ Frames / Panels ═══ */
QFrame#Sidebar {
    background-color: __BG_DARK__;
    border-right: 1px solid __BORDER__;
}
QFrame#TopBar {
    background-color: __CARD__;
    border-bottom: 1px solid __BORDER__;
}
QFrame#StatusBar {
    background-color: __CARD__;
    border-top: 1px solid __BORDER__;
}
QFrame#ChatPanel {
    background-color: __BG__;
}
QFrame#EventsPanel {
    background-color: __CARD__;
    border-left: 1px solid __BORDER__;
}

/* ═══ Cards ═══ */
QFrame#Card {
    background-color: __CARD__;
    border-radius: 8px;
    border: 1px solid __BORDER__;
}

/* ═══ Buttons ═══ */
QPushButton {
    background-color: __CARD_HI__;
    border: 2px solid __BORDER_LIGHT__;
    border-radius: 6px;
    padding: 8px 16px;
    color: __TEXT__;
    font-weight: 600;
    font-size: 16px;
    min-height: 22px;
}
QPushButton:hover {
    background-color: __CARD_HOVER__;
    border-color: __ACCENT__;
}
QPushButton:pressed {
    background-color: __CARD__;
}
QPushButton:disabled {
    color: __TEXT_FAINT__;
    background-color: __CARD__;
    border-color: __BORDER__;
}

/* Primary button (accent) */
QPushButton#Primary {
    background-color: __ACCENT__;
    border: 2px solid __ACCENT_HOVER__;
    color: white;
    font-weight: 600;
}
QPushButton#Primary:hover {
    background-color: __ACCENT_HOVER__;
}

/* Danger button */
QPushButton#Danger {
    background-color: __DANGER__;
    border: 2px solid __DANGER_HOVER__;
    color: white;
    font-weight: 600;
}
QPushButton#Danger:hover {
    background-color: __DANGER_HOVER__;
    border-color: #fca5a5;
}

/* Success button */
QPushButton#Success {
    background-color: __SUCCESS__;
    border: none;
    color: white;
}
QPushButton#Success:hover {
    background-color: __SUCCESS_HOVER__;
}

/* Icon button (topbar/chat panel — flat, no border) */
QPushButton#IconButton {
    background-color: transparent;
    border: none;
    padding: 2px 4px;
    font-size: 16px;
    border-radius: 6px;
}
QPushButton#IconButton:hover {
    background-color: __CARD_HI__;
}

/* ═══ SplitButton (QPushButton — topbar split button with dropdown) ═══ */
/* flat pill design — main button + arrow button คู่กัน */
QPushButton#SplitButtonMain {
    background-color: rgba(255, 255, 255, 0.04);
    border: none;
    border-radius: 14px 0 0 14px;
    padding: 4px 6px 4px 14px;
    font-size: 12px;
    font-weight: 600;
    color: __TEXT_DIM__;
    min-height: 18px;
}
QPushButton#SplitButtonMain:hover {
    background-color: rgba(255, 255, 255, 0.10);
    color: __TEXT__;
}
QPushButton#SplitButtonMain:pressed {
    background-color: rgba(255, 255, 255, 0.06);
}
/* arrow button (dropdown) */
QPushButton#SplitButtonArrow {
    background-color: rgba(255, 255, 255, 0.04);
    border: none;
    border-radius: 0 14px 14px 0;
    padding: 4px 2px;
    font-size: 11px;
    color: __TEXT_DIM__;
    min-height: 18px;
}
QPushButton#SplitButtonArrow:hover {
    background-color: rgba(255, 255, 255, 0.10);
    color: __TEXT__;
}
/* ★ state="on" — accent (ม่วง) ตอนเปิดใช้งาน */
QPushButton#SplitButtonMain[state="on"],
QPushButton#SplitButtonArrow[state="on"] {
    background-color: __ACCENT__;
    color: __ON_ACCENT_TEXT__;
}
QPushButton#SplitButtonMain[state="on"]:hover,
QPushButton#SplitButtonArrow[state="on"]:hover {
    background-color: __ACCENT_HOVER__;
}
/* ★ state="danger" — แดง */
QPushButton#SplitButtonMain[state="danger"],
QPushButton#SplitButtonArrow[state="danger"] {
    background-color: __DANGER__;
    color: __ON_DANGER_TEXT__;
}
QPushButton#SplitButtonMain[state="danger"]:hover,
QPushButton#SplitButtonArrow[state="danger"]:hover {
    background-color: __DANGER_HOVER__;
}
/* ★ state="warning" — amber */
QPushButton#SplitButtonMain[state="warning"],
QPushButton#SplitButtonArrow[state="warning"] {
    background-color: __HEADING__;
    color: __ON_WARNING_TEXT__;
}
QPushButton#SplitButtonMain[state="warning"]:hover,
QPushButton#SplitButtonArrow[state="warning"]:hover {
    background-color: #d97706;
}

/* ═══ Input ═══ */
QLineEdit {
    background-color: __CARD__;
    border: 1px solid __BORDER__;
    border-radius: 6px;
    padding: 8px 12px;
    color: __TEXT__;
    selection-background-color: __ACCENT__;
}
QLineEdit:focus {
    border-color: __ACCENT__;
}
QLineEdit::placeholder {
    color: __TEXT_FAINT__;
}

QTextEdit, QPlainTextEdit {
    background-color: __CARD__;
    border: 1px solid __BORDER__;
    border-radius: 6px;
    padding: 8px;
    color: __TEXT__;
}

/* ═══ ComboBox ═══ */
QComboBox {
    background-color: __CARD__;
    border: 1px solid __BORDER__;
    border-radius: 6px;
    padding: 6px 12px;
    color: __TEXT__;
    min-height: 20px;
}
QComboBox:hover {
    border-color: __ACCENT__;
}
QComboBox::drop-down {
    border: none;
    width: 26px;
}
QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid __TEXT_DIM__;
    margin-right: 10px;
}
QComboBox QAbstractItemView {
    background-color: __CARD__;
    border: 1px solid __BORDER__;
    border-radius: 6px;
    padding: 4px;
    selection-background-color: __ACCENT__;
    outline: none;
}

/* ═══ CheckBox ═══ */
QCheckBox {
    spacing: 8px;
    color: __TEXT__;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 2px solid __BORDER_LIGHT__;
    background-color: __CARD__;
}
QCheckBox::indicator:checked {
    background-color: __ACCENT__;
    border-color: __ACCENT__;
    image: none;
}
QCheckBox::indicator:hover {
    border-color: __ACCENT__;
}

/* ═══ RadioButton ═══ */
QRadioButton {
    spacing: 8px;
    color: __TEXT__;
    font-size: 16px;
    padding: 4px;
}
QRadioButton::indicator {
    width: 18px;
    height: 18px;
    border-radius: 9px;
    border: 2px solid __BORDER_LIGHT__;
    background-color: __CARD__;
}
QRadioButton::indicator:checked {
    background-color: __ACCENT__;
    border-color: __ACCENT__;
}
QRadioButton::indicator:hover {
    border-color: __ACCENT__;
}

/* ═══ Slider ═══ */
QSlider::groove:horizontal {
    height: 6px;
    background: __CARD_HI__;
    border-radius: 3px;
}
QSlider::sub-page:horizontal {
    background: __ACCENT__;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    width: 16px;
    height: 16px;
    margin: -6px 0;
    background: white;
    border-radius: 8px;
    border: 2px solid __ACCENT__;
}
QSlider::handle:horizontal:hover {
    background: __ACCENT__;
}

/* ═══ ScrollArea ═══ */
QScrollArea {
    background-color: transparent;
    border: none;
}
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: __BORDER_LIGHT__;
    min-height: 30px;
    border-radius: 5px;
}
QScrollBar::handle:vertical:hover {
    background: __TEXT_FAINT__;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: __BORDER_LIGHT__;
    min-width: 30px;
    border-radius: 5px;
}
QScrollBar::handle:horizontal:hover {
    background: __TEXT_FAINT__;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}

/* ═══ Label ═══ */
QLabel {
    background-color: transparent;
    color: __TEXT__;
}
QLabel#Heading {
    color: __HEADING__;
    font-size: 16px;
    font-weight: 600;
}
QLabel#Dim {
    color: __TEXT_DIM__;
}
QLabel#Faint {
    color: __TEXT_FAINT__;
    font-size: 13px;
}
QLabel#Section {
    color: __ACCENT_2__;
    font-size: 14px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
}

/* ═══ ProgressBar ═══ */
QProgressBar {
    background-color: __CARD_HI__;
    border: none;
    border-radius: 4px;
    height: 8px;
    text-align: center;
    font-size: 12px;
    color: __TEXT_DIM__;
}
QProgressBar::chunk {
    background-color: __ACCENT__;
    border-radius: 4px;
}

/* ═══ Splitter ═══ */
QSplitter::handle {
    background-color: __BORDER__;
}
QSplitter::handle:horizontal {
    width: 1px;
}
QSplitter::handle:vertical {
    height: 1px;
}

/* ═══ ToolTip ═══ */
QToolTip {
    background-color: __CARD_HI__;
    color: __TEXT__;
    border: 1px solid __BORDER__;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 14px;
}

/* ═══ Menu (context menu / dropdown) ═══ */
QMenu {
    background-color: __CARD__;
    border: 1px solid __BORDER__;
    border-radius: 8px;
    padding: 4px;
}
QMenu::item {
    padding: 8px 24px;
    border-radius: 4px;
}
QMenu::item:selected {
    background-color: __ACCENT__;
}
QMenu::separator {
    height: 1px;
    background-color: __BORDER__;
    margin: 4px 8px;
}

/* ═══ List (chat feed, events) ═══ */
QListWidget, QListView {
    background-color: transparent;
    border: none;
    outline: none;
}
QListWidget::item {
    border-bottom: 1px solid rgba(42, 47, 69, 0.3);
    padding: 4px;
}
"""


def apply_theme(app: QApplication, theme_name: str = "default") -> None:
    """ตั้ง font + apply QSS stylesheet ตามธีมที่เลือก (settings.ui_theme)

    ★ เขียนทับตัวแปร COLOR_* ระดับโมดูลด้วย — ต้องเรียกฟังก์ชันนี้ "ก่อน" สร้าง
    QMainWindow/widget ใดๆ เสมอ (main.py เรียกก่อน TTSForLivestreamApp() อยู่แล้ว)
    เพื่อให้ widget ที่อ้าง `theme.COLOR_X` ตอนสร้างตัวเอง (ไม่ใช่ from-import ตายตัว)
    ได้ค่าตามธีมที่เลือกจริง — ถ้า theme_name ไม่รู้จัก fallback เป็น "default" เงียบๆ
    (กันไฟล์ settings.json เก่า/พัง ทำให้เปิดโปรแกรมไม่ได้)
    """
    global COLOR_BG, COLOR_BG_DARK, COLOR_CARD, COLOR_CARD_HI, COLOR_CARD_HOVER
    global COLOR_ACCENT, COLOR_ACCENT_HOVER, COLOR_ACCENT_2, COLOR_HEADING
    global COLOR_DANGER, COLOR_DANGER_HOVER, COLOR_SUCCESS, COLOR_SUCCESS_HOVER
    global COLOR_TEXT, COLOR_TEXT_DIM, COLOR_TEXT_FAINT, COLOR_BORDER, COLOR_BORDER_LIGHT
    global COLOR_ON_ACCENT_TEXT, COLOR_ON_DANGER_TEXT, COLOR_ON_SUCCESS_TEXT, COLOR_ON_WARNING_TEXT

    setup_fonts(app)
    palette = THEMES.get(theme_name) or THEMES["default"]

    COLOR_BG = palette["BG"]
    COLOR_BG_DARK = palette["BG_DARK"]
    COLOR_CARD = palette["CARD"]
    COLOR_CARD_HI = palette["CARD_HI"]
    COLOR_CARD_HOVER = palette["CARD_HOVER"]
    COLOR_ACCENT = palette["ACCENT"]
    COLOR_ACCENT_HOVER = palette["ACCENT_HOVER"]
    COLOR_ACCENT_2 = palette["ACCENT_2"]
    COLOR_HEADING = palette["HEADING"]
    COLOR_DANGER = palette["DANGER"]
    COLOR_DANGER_HOVER = palette["DANGER_HOVER"]
    COLOR_SUCCESS = palette["SUCCESS"]
    COLOR_SUCCESS_HOVER = palette["SUCCESS_HOVER"]
    COLOR_TEXT = palette["TEXT"]
    COLOR_TEXT_DIM = palette["TEXT_DIM"]
    COLOR_TEXT_FAINT = palette["TEXT_FAINT"]
    COLOR_BORDER = palette["BORDER"]
    COLOR_BORDER_LIGHT = palette["BORDER_LIGHT"]
    COLOR_ON_ACCENT_TEXT = palette["ON_ACCENT_TEXT"]
    COLOR_ON_DANGER_TEXT = palette["ON_DANGER_TEXT"]
    COLOR_ON_SUCCESS_TEXT = palette["ON_SUCCESS_TEXT"]
    COLOR_ON_WARNING_TEXT = palette["ON_WARNING_TEXT"]

    # ★ replace placeholders with actual colors
    qss = QSS
    replacements = {
        '__BG__': COLOR_BG,
        '__BG_DARK__': COLOR_BG_DARK,
        '__CARD__': COLOR_CARD,
        '__CARD_HI__': COLOR_CARD_HI,
        '__CARD_HOVER__': COLOR_CARD_HOVER,
        '__ACCENT__': COLOR_ACCENT,
        '__ACCENT_HOVER__': COLOR_ACCENT_HOVER,
        '__ACCENT_2__': COLOR_ACCENT_2,
        '__HEADING__': COLOR_HEADING,
        '__DANGER__': COLOR_DANGER,
        '__DANGER_HOVER__': COLOR_DANGER_HOVER,
        '__SUCCESS__': COLOR_SUCCESS,
        '__SUCCESS_HOVER__': COLOR_SUCCESS_HOVER,
        '__TEXT__': COLOR_TEXT,
        '__TEXT_DIM__': COLOR_TEXT_DIM,
        '__TEXT_FAINT__': COLOR_TEXT_FAINT,
        '__BORDER__': COLOR_BORDER,
        '__BORDER_LIGHT__': COLOR_BORDER_LIGHT,
        '__ON_ACCENT_TEXT__': COLOR_ON_ACCENT_TEXT,
        '__ON_DANGER_TEXT__': COLOR_ON_DANGER_TEXT,
        '__ON_WARNING_TEXT__': COLOR_ON_WARNING_TEXT,
    }
    for placeholder, color in replacements.items():
        qss = qss.replace(placeholder, color)
    app.setStyleSheet(qss)
