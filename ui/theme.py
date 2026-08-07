"""theme.py — QSS stylesheet + color constants + font setup (PySide6)

Modern flat design — Discord/Spotify style dark theme
เก็บ color palette เดิมจาก v1 (เพราะคุ้นเคย + สวยอยู่แล้ว)
"""
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

# ═══════════════════════════════════════════════════════════════
# Color Palette (เดิมจาก v1 — สวย + คุ้นเคย)
# ═══════════════════════════════════════════════════════════════
COLOR_BG = "#0a0e1a"           # main background (dark navy)
COLOR_BG_DARK = "#060912"      # darker variant (sidebar)
COLOR_CARD = "#131726"         # panel background
COLOR_CARD_HI = "#1a1f33"      # hover/elevated card
COLOR_CARD_HOVER = "#1e2438"   # hover state
COLOR_ACCENT = "#7c3aed"       # primary accent (purple)
COLOR_ACCENT_HOVER = "#6d28d9"
COLOR_ACCENT_2 = "#06b6d4"     # secondary accent (cyan)
COLOR_HEADING = "#f59e0b"      # amber — section headings
COLOR_DANGER = "#ef4444"       # red — disconnect/danger
COLOR_DANGER_HOVER = "#dc2626"
COLOR_SUCCESS = "#10b981"      # green — connected
COLOR_SUCCESS_HOVER = "#059669"
COLOR_TEXT = "#e5e7eb"         # primary text
COLOR_TEXT_DIM = "#9ca3af"     # secondary text
COLOR_TEXT_FAINT = "#6b7280"   # tertiary text
COLOR_BORDER = "#2a2f45"
COLOR_BORDER_LIGHT = "#374151"

# ═══════════════════════════════════════════════════════════════
# Fonts
# ═══════════════════════════════════════════════════════════════
def setup_fonts(app: QApplication) -> None:
    """ตั้ง font default + โหลด Kanit (ถ้ามี)"""
    # หา Kanit ใน assets/fonts
    import os
    font_paths = [
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "fonts", "Kanit-Regular.ttf"),
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "fonts", "Kanit-Medium.ttf"),
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "fonts", "Kanit-SemiBold.ttf"),
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "fonts", "Kanit-Bold.ttf"),
    ]
    for p in font_paths:
        if os.path.exists(p):
            QFontDatabase.addApplicationFont(p)
    # default font
    font = QFont("Kanit", 10)
    font.setStyleHint(QFont.SansSerif)
    app.setFont(font)


# ═══════════════════════════════════════════════════════════════
# QSS Stylesheet — Modern Flat Design
# ═══════════════════════════════════════════════════════════════
QSS = """
/* ═══ Global ═══ */
* {
    font-family: 'Kanit', 'Segoe UI', sans-serif;
    color: __TEXT__;
    outline: none;
}

QWidget {
    background-color: __BG__;
    font-size: 14px;
}

/* ★ label — ไม่ตัดความสูง */
QLabel {
    background-color: transparent;
    color: __TEXT__;
    min-height: 18px;
    font-size: 14px;
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
    font-size: 14px;
    min-height: 20px;
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

/* Icon button (topbar — flat, no border) */
QPushButton#IconButton {
    background-color: transparent;
    border: none;
    padding: 6px 10px;
    font-size: 16px;
    border-radius: 6px;
}
QPushButton#IconButton:hover {
    background-color: __CARD_HI__;
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
    font-size: 14px;
    font-weight: 600;
}
QLabel#Dim {
    color: __TEXT_DIM__;
}
QLabel#Faint {
    color: __TEXT_FAINT__;
    font-size: 11px;
}
QLabel#Section {
    color: __ACCENT_2__;
    font-size: 12px;
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
    font-size: 10px;
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
    font-size: 12px;
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


def apply_theme(app: QApplication) -> None:
    """ตั้ง font + apply QSS stylesheet"""
    setup_fonts(app)
    # ★ replace placeholders with actual colors
    qss = QSS
    replacements = {
        '__BG__': COLOR_BG,
        '__BG_DARK__': COLOR_BG_DARK,
        '__CARD__': COLOR_CARD,
        '__CARD_HI__': COLOR_CARD_HI,
        '__CARD_HOVER__': '#1e2438',
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
    }
    for placeholder, color in replacements.items():
        qss = qss.replace(placeholder, color)
    app.setStyleSheet(qss)
