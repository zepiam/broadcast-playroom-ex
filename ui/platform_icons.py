"""platform_icons.py — โหลดและแคชไอคอนแพลตฟอร์มจาก assets/*.png

ใช้ทั่วทั้งแอป: chat_row, sidebar, topbar, settings dialog
preload ครั้งเดียว + cache QPixmap ตามขนาด → ไม่ต้องอ่านไฟล์ซ้ำ
"""
import logging
import os
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QIcon

logger = logging.getLogger("platform_icons")

# ── registry (sync กับ PLATFORM_LABELS ใน app.py + v1 PLATFORM_REGISTRY) ──
PLATFORM_FILES = {
    "twitch": "twitch.png",
    "youtube": "youtube.png",
    "mylive": "mylive.png",
    "tiktok": "tiktok.png",
    "kick": "kick.png",
}

# ── cache: {(platform, size): QPixmap} ──
_cache = {}
_assets_dir = None


def _get_assets_dir():
    """หา assets/ folder — 2 ระดับจาก ui/ (ui/platform_icons.py → base)"""
    global _assets_dir
    if _assets_dir is not None:
        return _assets_dir
    # ui/platform_icons.py → ui/ → base
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # ลองหลายตำแหน่ง (dev mode + PyInstaller _MEIPASS)
    candidates = [
        os.path.join(base, "assets"),
        os.path.join(getattr(__import__('sys'), '_MEIPASS', base), "assets"),
    ]
    for cand in candidates:
        if os.path.isdir(cand):
            _assets_dir = cand
            return _assets_dir
    _assets_dir = os.path.join(base, "assets")
    return _assets_dir


def get_platform_pixmap(platform: str, size: int = 22) -> QPixmap:
    """คืน QPixmap ของไอคอนแพลตฟอร์ม (scaled) — cache ตาม (platform, size)

    ถ้าไม่พบไฟล์ → คืน QPixmap ว่าง (caller ตรวจ .isNull())
    """
    key = (platform, size)
    if key in _cache:
        return _cache[key]
    fname = PLATFORM_FILES.get(platform)
    if not fname:
        return QPixmap()
    path = os.path.join(_get_assets_dir(), fname)
    if not os.path.exists(path):
        logger.debug(f"platform icon not found: {path}")
        return QPixmap()
    pix = QPixmap(path)
    if pix.isNull():
        return QPixmap()
    # scale (KeepAspectRatio + SmoothTransformation เพื่อคุณภาพดี)
    scaled = pix.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    _cache[key] = scaled
    return scaled


def get_platform_icon(platform: str, size: int = 22) -> QIcon:
    """คืน QIcon ของแพลตฟอร์ม (สำหรับ setIcon บน QAbstractButton)"""
    pix = get_platform_pixmap(platform, size)
    return QIcon(pix) if not pix.isNull() else QIcon()


def make_icon_label(platform: str, size: int = 16):
    """สร้าง QLabel ที่แสดงไอคอนแพลตฟอร์ม — สะดวกใช้ใน layout

    คืน (QLabel, bool found) — found=False ถ้าไม่มีไฟล์ (caller อาจแสดง emoji fallback)
    """
    from PySide6.QtWidgets import QLabel
    pix = get_platform_pixmap(platform, size)
    lbl = QLabel()
    if not pix.isNull():
        lbl.setPixmap(pix)
        lbl.setFixedSize(size, size)
        return lbl, True
    # fallback: emoji
    emoji_fallback = {
        "twitch": "🟣", "youtube": "🔴", "mylive": "🔵",
        "tiktok": "⚫", "kick": "🟢",
    }
    lbl.setText(emoji_fallback.get(platform, "📺"))
    lbl.setStyleSheet(f"font-size: {size}px;")
    lbl.setFixedSize(size, size)
    return lbl, False
