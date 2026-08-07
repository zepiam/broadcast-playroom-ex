"""chat_row.py — Chat message row with full emote/segment/sticker rendering

รองรับ:
- Twitch emotes (sub + BTTV/FFZ/7TV) via extra["emotes"] → twitch_emotes
- MyLive/YouTube/TikTok segments via extra["segments"]
- Stickers via extra["sticker_url"]
- System messages (sub/bits/raid) styling
- Platform color coding
- Click author → open viewer profile (signal)
"""
import logging
import os
import urllib.request
from PySide6.QtCore import Qt, Signal, QSize, QTimer, QThread, QObject
from PySide6.QtGui import QPixmap, QImage, QFont, QColor
from PySide6.QtWidgets import (
    QWidget, QLabel, QHBoxLayout, QVBoxLayout, QFrame, QSizePolicy,
)

logger = logging.getLogger("chat_row")

# ═══ Emote cache (in-memory — กันโหลดซ้ำ) ═══
_EMOTE_CACHE = {}  # url → QPixmap (or None if failed)
_EMOTE_CACHE_LOCK = None

def _get_cache_lock():
    global _EMOTE_CACHE_LOCK
    if _EMOTE_CACHE_LOCK is None:
        import threading
        _EMOTE_CACHE_LOCK = threading.Lock()
    return _EMOTE_CACHE_LOCK


class EmoteLoader(QObject):
    """Background thread loader for emote images"""
    loaded = Signal(str, QPixmap)  # url, pixmap

    def __init__(self):
        super().__init__()
        self._thread = None

    def load(self, url, size=28):
        """Load emote async — emit loaded signal when done"""
        # check cache first
        with _get_cache_lock():
            if url in _EMOTE_CACHE:
                pix = _EMOTE_CACHE[url]
                if pix is not None:
                    self.loaded.emit(url, pix.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                return

        # load in background
        def _bg_load():
            try:
                # resolve relative URLs (composer proxy)
                src_url = url
                if url.startswith('/emote/'):
                    src_url = f"http://localhost:8808{url}"
                elif url.startswith('/'):
                    src_url = f"http://localhost:8808{url}"

                req = urllib.request.Request(src_url, headers={'User-Agent': 'BroadcastPlayroom/2.0'})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = resp.read()
                img = QImage()
                img.loadFromData(data)
                if img.isNull():
                    with _get_cache_lock():
                        _EMOTE_CACHE[url] = None
                    return
                pix = QPixmap.fromImage(img)
                with _get_cache_lock():
                    _EMOTE_CACHE[url] = pix
                # emit on main thread
                self.loaded.emit(url, pix.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            except Exception as e:
                logger.debug(f"Emote load failed {url}: {e}")
                with _get_cache_lock():
                    _EMOTE_CACHE[url] = None

        import threading
        t = threading.Thread(target=_bg_load, daemon=True)
        t.start()

    def load_sticker(self, url, size=64):
        """Load sticker (larger)"""
        self.load(url, size)


# ★ Singleton loader
_emote_loader = None
def get_emote_loader():
    global _emote_loader
    if _emote_loader is None:
        _emote_loader = EmoteLoader()
    return _emote_loader


class ChatRow(QWidget):
    """Single chat message row — full rendering with emotes/segments/stickers"""

    author_clicked = Signal(str)  # emit author name on click

    def __init__(self, msg, parent=None, font_size=13):
        super().__init__(parent)
        self.msg = msg
        self._font_size = font_size
        self._emote_labels = {}  # url → QLabel (for updating when loaded)
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignTop)
        # ★ ใช้ SizePolicy เพื่อให้ row ขยายตามเนื้อหา (ไม่ตัดความสูง)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)

        event = getattr(self.msg, 'event', 'message')

        # ═══ System/event messages (sub/bits/raid) ═══
        if event != 'message':
            self._build_event_row(layout, event)
            return

        # ═══ Normal chat message ═══
        extra = getattr(self.msg, 'extra', {}) or {}
        platform = getattr(self.msg, 'platform', '')
        author = getattr(self.msg, 'author', '?') or '?'

        # ★ Author label (clickable)
        self.author_label = QLabel()
        self.author_label.setCursor(Qt.PointingHandCursor)
        self.author_label.setTextFormat(Qt.RichText)
        author_color = self._get_platform_color(platform)
        # ★ apply rename if available
        display_name = author
        self.author_label.setText(f'<span style="color:{author_color}; font-weight:600;">{display_name}</span>:')
        font = QFont("Kanit", self._font_size)
        font.setWeight(QFont.DemiBold)
        self.author_label.setFont(font)
        # ★ ไม่ fixed height — ให้ขยายตาม font
        self.author_label.setMinimumHeight(self._font_size + 8)
        # click handler
        self.author_label.mousePressEvent = lambda e: self.author_clicked.emit(author)
        layout.addWidget(self.author_label)

        # ★ Message content (text + emotes + segments)
        self.content_widget = QWidget()
        self.content_layout = QHBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(2)
        self.content_layout.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        # render content
        self._render_content(extra, platform)
        layout.addWidget(self.content_widget, 1)

    def _build_event_row(self, layout, event):
        """render event message (sub/bits/raid/etc)"""
        author = getattr(self.msg, 'author', '') or ''
        system_text = getattr(self.msg, 'system_text', '') or ''
        amount = getattr(self.msg, 'amount', None)
        tier = getattr(self.msg, 'tier', None)

        icon_map = {
            'sub': '⭐', 'resub': '⭐', 'subgift': '🎁',
            'bits': '💎', 'raid': '🚀', 'follow': '❤️',
            'share': '📢', 'join': '👋',
        }
        icon = icon_map.get(event, '🔔')
        text = f"{icon} "
        if author:
            text += f"<b style='color:#f47fff'>{author}</b> "
        if system_text:
            text += system_text
        elif event == 'bits' and amount:
            text += f"cheered {amount} bits!"
        elif event == 'raid' and tier:
            text += f"raiding with {tier} viewers!"
        elif event == 'sub':
            text += "subscribed!"
        elif event == 'resub':
            text += "resubscribed!"
        else:
            text += event

        label = QLabel(text)
        label.setTextFormat(Qt.RichText)
        label.setWordWrap(True)
        label.setStyleSheet(f"color: #fbbf24; font-size: {self._font_size}px;")
        layout.addWidget(label, 1)

    def _render_content(self, extra, platform):
        """Render message content — text + emotes + segments"""
        segments = extra.get('segments', [])
        twitch_emotes = extra.get('twitch_emotes', []) or []
        # Also check "emotes" (raw from chat client)
        raw_emotes = extra.get('emotes', []) or []
        sticker_url = extra.get('sticker_url', '')
        raw_text = extra.get('raw_text', '') or getattr(self.msg, 'text', '')

        # ★ Sticker (MyLive) — show image only
        if sticker_url and not segments and not twitch_emotes:
            self._add_sticker(sticker_url)
            return

        # ★ Segments (MyLive/YouTube/TikTok) — render inline
        if segments and not getattr(self.msg, 'is_translated', False):
            self._render_segments(segments)
            # ★ append translated text if available
            translated = getattr(self.msg, 'text', '')
            if translated and translated != raw_text:
                lbl = QLabel(f"  ⟶ {translated}")
                lbl.setStyleSheet(f"color: #10b981; font-size: {self._font_size}px;")
                lbl.setWordWrap(True)
                self.content_layout.addWidget(lbl)
            return

        # ★ Twitch emotes — render with text interpolation
        if twitch_emotes and raw_text and not getattr(self.msg, 'is_translated', False):
            self._render_twitch_emotes(raw_text, twitch_emotes)
            return

        # ★ Fallback: plain text
        text = getattr(self.msg, 'text', '') or raw_text
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lbl.setStyleSheet(f"color: #e5e7eb; font-size: {self._font_size}px;")
        self.content_layout.addWidget(lbl, 1)

    def _render_segments(self, segments):
        """Render segments (MyLive/YouTube/TikTok format)"""
        for seg in segments:
            stype = seg.get('type', '')
            if stype == 'text':
                content = seg.get('content', '')
                if content:
                    lbl = QLabel(content)
                    lbl.setWordWrap(True)
                    lbl.setStyleSheet(f"color: #e5e7eb; font-size: {self._font_size}px;")
                    self.content_layout.addWidget(lbl)
            elif stype == 'emoji':
                char = seg.get('char', '')
                if char:
                    lbl = QLabel(char)
                    lbl.setStyleSheet(f"font-size: {self._font_size + 2}px;")
                    self.content_layout.addWidget(lbl)
            elif stype == 'emote':
                url = seg.get('url', '')
                if url:
                    self._add_emote(url)

    def _render_twitch_emotes(self, text, emotes):
        """Render Twitch emotes inline with text"""
        sorted_emotes = sorted(emotes, key=lambda e: e.get('start', 0))
        cur = 0
        for em in sorted_emotes:
            start = em.get('start', 0)
            end = em.get('end', 0)
            url = em.get('url', '')
            # text before emote
            if start > cur:
                txt = text[cur:start]
                if txt:
                    lbl = QLabel(txt)
                    lbl.setWordWrap(True)
                    lbl.setStyleSheet(f"color: #e5e7eb; font-size: {self._font_size}px;")
                    self.content_layout.addWidget(lbl)
            # emote image
            if url:
                self._add_emote(url)
            cur = end + 1
        # remaining text
        if cur < len(text):
            txt = text[cur:]
            if txt:
                lbl = QLabel(txt)
                lbl.setWordWrap(True)
                lbl.setStyleSheet(f"color: #e5e7eb; font-size: {self._font_size}px;")
                self.content_layout.addWidget(lbl)

    def _add_emote(self, url, size=28):
        """Add emote image to row (async load)"""
        lbl = QLabel()
        lbl.setFixedSize(size, size)
        lbl.setAlignment(Qt.AlignCenter)
        self.content_layout.addWidget(lbl)
        self._emote_labels[url] = lbl
        # async load
        loader = get_emote_loader()
        loader.loaded.connect(lambda u, p, l=lbl: self._on_emote_loaded(u, p, l))
        loader.load(url, size)

    def _add_sticker(self, url, size=64):
        """Add sticker image (larger)"""
        lbl = QLabel()
        lbl.setFixedSize(size, size)
        lbl.setAlignment(Qt.AlignCenter)
        self.content_layout.addWidget(lbl)
        self._emote_labels[url] = lbl
        loader = get_emote_loader()
        loader.loaded.connect(lambda u, p, l=lbl: self._on_emote_loaded(u, p, l))
        loader.load_sticker(url, size)

    def _on_emote_loaded(self, url, pixmap, label):
        """Called when emote image loads"""
        if not pixmap.isNull():
            label.setPixmap(pixmap)

    def _get_platform_color(self, platform):
        """สี author ตามแพลตฟอร์ม"""
        colors = {
            'twitch': '#bf94ff',
            'youtube': '#ff4444',
            'mylive': '#ff8800',
            'tiktok': '#00f2ea',
            'kick': '#53fc18',
        }
        return colors.get(platform, '#06b6d4')
