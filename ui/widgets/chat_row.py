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
    """QThread-based loader for emote images — thread-safe signal emission"""
    loaded = Signal(str, QPixmap)  # url, pixmap

    def load(self, url, size=28):
        """Load emote async — emit loaded signal when done"""
        # check cache first
        with _get_cache_lock():
            if url in _EMOTE_CACHE:
                pix = _EMOTE_CACHE[url]
                if pix is not None:
                    self.loaded.emit(url, pix.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                return

        # ★ use QThread (not raw thread) — signal emission must be from Qt thread
        class _LoadThread(QThread):
            def __init__(self, url, callback):
                super().__init__()
                self.url = url
                self.callback = callback
            def run(self):
                try:
                    src_url = self.url
                    if self.url.startswith('/emote/') or self.url.startswith('/'):
                        src_url = f"http://localhost:8808{self.url}"
                    req = urllib.request.Request(src_url, headers={'User-Agent': 'BroadcastPlayroom/2.0'})
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        data = resp.read()
                    img = QImage()
                    img.loadFromData(data)
                    if img.isNull():
                        with _get_cache_lock():
                            _EMOTE_CACHE[self.url] = None
                        return
                    pix = QPixmap.fromImage(img)
                    with _get_cache_lock():
                        _EMOTE_CACHE[self.url] = pix
                    # ★ emit on main thread (QThread.finished or direct signal)
                    self.callback(self.url, pix, size)
                except Exception as e:
                    logger.debug(f"Emote load failed {self.url}: {e}")
                    with _get_cache_lock():
                        _EMOTE_CACHE[self.url] = None

        def _on_loaded(url, pix, sz):
            """called from QThread.run → schedule on main thread"""
            QTimer.singleShot(0, lambda: self.loaded.emit(
                url, pix.scaled(sz, sz, Qt.KeepAspectRatio, Qt.SmoothTransformation)))

        t = _LoadThread(url, _on_loaded)
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
    delete_requested = Signal(object)  # emit self (row) for deletion
    block_user_requested = Signal(str)  # emit author for blocking

    def __init__(self, msg, parent=None, font_size=14):
        super().__init__(parent)
        self.msg = msg
        self._font_size = font_size
        self._emote_labels = {}
        # ★ context menu (right-click)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self._build_ui()

    def _show_context_menu(self, pos):
        """context menu — ลบข้อความ / บล็อกผู้ใช้"""
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background: #131726; border: 1px solid #2a2f45; border-radius: 8px; padding: 4px; } QMenu::item { padding: 8px 24px; border-radius: 4px; color: #e5e7eb; } QMenu::item:selected { background: #7c3aed; }")
        author = getattr(self.msg, 'author', '') or ''
        act_delete = menu.addAction("🗑 ลบข้อความนี้")
        if author:
            menu.addSeparator()
            act_block_all = menu.addAction("🚫 บล็อกผู้ใช้ (ทุกอย่าง)")
            act_block_tts = menu.addAction("🔇 บล็อก TTS (ไม่อ่าน)")
        action = menu.exec(self.mapToGlobal(pos))
        if action == act_delete:
            self.delete_requested.emit(self)
        elif author and action == act_block_all:
            self.block_user_requested.emit(author)
        elif author and action == act_block_tts:
            self.block_user_requested.emit(author + "||tts_only")

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(2)
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

        # ★ Author label (clickable) — อยู่บนสุดของ row
        self.author_label = QLabel()
        self.author_label.setCursor(Qt.PointingHandCursor)
        self.author_label.setTextFormat(Qt.RichText)
        author_color = self._get_platform_color(platform)
        display_name = author
        self.author_label.setText(f'<span style="color:{author_color}; font-weight:600;">{display_name}</span>:')
        font = QFont("Kanit", self._font_size)
        font.setWeight(QFont.DemiBold)
        self.author_label.setFont(font)
        self.author_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self.author_label.mousePressEvent = lambda e: self.author_clicked.emit(author)
        layout.addWidget(self.author_label)

        # ★ Content area — vertical layout (ข้อความแปล บน / ต้นฉบับ ล่าง)
        self.content_layout = QVBoxLayout()
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(2)

        # render content
        self._render_content(extra, platform)
        layout.addLayout(self.content_layout)

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
        """Render message content — text + emotes + segments + translated original"""
        segments = extra.get('segments', [])
        twitch_emotes = extra.get('twitch_emotes', []) or []
        sticker_url = extra.get('sticker_url', '')
        raw_text = extra.get('raw_text', '') or getattr(self.msg, 'text', '')
        is_translated = bool(extra.get('translated'))
        original_text = extra.get('original_text', '')
        source_lang = extra.get('source_lang', '')

        # ★ Sticker (MyLive) — show image only
        if sticker_url and not segments and not twitch_emotes:
            self._add_sticker(sticker_url)
            return

        # ★ text/emote content — ใช้ QLabel เดียวที่ word-wrap ตามความกว้าง
        #    (ไม่ใช้ QHBoxLayout เพราะ text จะไม่ wrap)
        if segments and not is_translated:
            self._render_segments_wrap(segments)
        elif twitch_emotes and raw_text and not is_translated:
            self._render_twitch_emotes_wrap(raw_text, twitch_emotes)
        else:
            # plain text
            text = getattr(self.msg, 'text', '') or raw_text
            lbl = self._make_wrap_label(text)
            self.content_layout.addWidget(lbl)

        # ★ ต้นฉบับ (บรรทัดใหม่ — ใต้คำแปล)
        if is_translated and original_text:
            try:
                from flag_utils import flag_for
                flag = flag_for(source_lang)
            except Exception:
                flag = "🌐"
            orig_label = self._make_wrap_label(f"{flag} {original_text}", color="#10b981", size_offset=-1)
            self.content_layout.addWidget(orig_label)

    def _make_wrap_label(self, text, color="#e5e7eb", size_offset=0):
        """สร้าง QLabel ที่ word-wrap ตามความกว้างของ container (สำคัญสำหรับข้อความยาว)"""
        fs = self._font_size + size_offset
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lbl.setFont(QFont("Kanit", fs))
        lbl.setStyleSheet(f"color: {color}; font-size: {fs}px;")
        # ★ บังคับให้ label ขยายตามความกว้างของ parent (wrap ไม่ล้นออกขวา)
        lbl.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Preferred)
        lbl.setMinimumWidth(0)
        return lbl

    def _render_segments_wrap(self, segments):
        """Render segments — text ใช้ wrap label, emote inline"""
        from PySide6.QtWidgets import QHBoxLayout as _HBox
        # ★ แยก text segments กับ emote segments
        #    text → wrap label เดียว (concat ทั้งหมด)
        #    emote → แสดงหลัง text
        text_parts = []
        emote_urls = []
        emoji_chars = []
        for seg in segments:
            stype = seg.get('type', '')
            if stype == 'text':
                content = seg.get('content', '')
                if content:
                    text_parts.append(content)
            elif stype == 'emoji':
                char = seg.get('char', '')
                if char:
                    emoji_chars.append(char)
            elif stype == 'emote':
                url = seg.get('url', '')
                if url:
                    emote_urls.append(url)
        # ★ render text (wrap)
        if text_parts:
            full_text = ' '.join(text_parts)
            lbl = self._make_wrap_label(full_text)
            self.content_layout.addWidget(lbl)
        # ★ render emoji + emotes inline (หลัง text)
        if emoji_chars or emote_urls:
            inline = _HBox()
            inline.setContentsMargins(0, 0, 0, 0)
            inline.setSpacing(2)
            for char in emoji_chars:
                lbl = QLabel(char)
                lbl.setFont(QFont("Kanit", self._font_size + 2))
                lbl.setStyleSheet(f"font-size: {self._font_size + 2}px;")
                inline.addWidget(lbl)
            for url in emote_urls:
                self._add_emote_to_layout(inline, url)
            self.content_layout.addLayout(inline)

    def _render_twitch_emotes_wrap(self, text, emotes):
        """Render Twitch emotes — text wrap + emotes inline"""
        from PySide6.QtWidgets import QHBoxLayout as _HBox
        sorted_emotes = sorted(emotes, key=lambda e: e.get('start', 0))
        # ★ ถ้ามีแค่ text ล้วน (ไม่มี emote กลาง) → wrap label เดียว
        if not sorted_emotes:
            lbl = self._make_wrap_label(text)
            self.content_layout.addWidget(lbl)
            return
        # ★ มี emote → แยกเป็น text segments + emote
        text_parts = []
        emote_urls = []
        cur = 0
        for em in sorted_emotes:
            start = em.get('start', 0)
            end = em.get('end', 0)
            url = em.get('url', '')
            if start > cur:
                text_parts.append(text[cur:start])
            if url:
                emote_urls.append(url)
            cur = end + 1
        if cur < len(text):
            text_parts.append(text[cur:])
        # ★ render text (wrap)
        if text_parts:
            full_text = ''.join(text_parts)
            lbl = self._make_wrap_label(full_text)
            self.content_layout.addWidget(lbl)
        # ★ render emotes inline
        if emote_urls:
            inline = _HBox()
            inline.setContentsMargins(0, 0, 0, 0)
            inline.setSpacing(2)
            for url in emote_urls:
                self._add_emote_to_layout(inline, url)
            self.content_layout.addLayout(inline)

    def _add_emote_to_layout(self, layout, url, size=28):
        """Add emote image to a horizontal layout (async load)"""
        lbl = QLabel()
        lbl.setFixedSize(size, size)
        lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl)
        self._emote_labels[url] = lbl
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

    def update_translation(self, msg):
        """อัปเดต row เมื่อข้อความถูกแปลแล้ว (re-render content)"""
        self.msg = msg
        # ★ clear old content layout
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_sublayout(item.layout())
        # ★ re-render with translated content
        extra = getattr(msg, 'extra', {}) or {}
        self._render_content(extra, getattr(msg, 'platform', ''))

    def _clear_sublayout(self, layout):
        """clear sub-layout (inline layout)"""
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        layout.deleteLater()

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
