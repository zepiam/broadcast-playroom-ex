"""chat_row.py — Chat message row with full emote/segment/sticker rendering

ใช้ EmoteCache (จาก v1) สำหรับโหลด emote — sync + async + cache + resize
"""
import logging
import os
from PySide6.QtCore import Qt, Signal, QSize, QTimer, QObject
from PySide6.QtGui import QPixmap, QImage, QFont, QColor
from PySide6.QtWidgets import (
    QWidget, QLabel, QHBoxLayout, QVBoxLayout, QFrame, QSizePolicy,
)

logger = logging.getLogger("chat_row")

# ★ EmoteCache singleton (จาก v1)
_emote_cache = None
def _get_emote_cache():
    global _emote_cache
    if _emote_cache is None:
        try:
            from emote_cache import EmoteCache
            _emote_cache = EmoteCache(theme="dark", size_px=28)
        except Exception as e:
            logger.warning(f"EmoteCache not available: {e}")
    return _emote_cache


class ChatRow(QWidget):
    """Single chat message row — full rendering with emotes/segments/stickers"""

    author_clicked = Signal(str)
    delete_requested = Signal(object)
    block_user_requested = Signal(str)

    def __init__(self, msg, parent=None, font_size=14):
        super().__init__(parent)
        self.msg = msg
        self._font_size = font_size
        self._emote_labels = {}
        self._emote_threads = []  # ★ keep refs to prevent GC
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self._build_ui()

    def _show_context_menu(self, pos):
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
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)

        event = getattr(self.msg, 'event', 'message')

        if event != 'message':
            self._build_event_row(layout, event)
            return

        extra = getattr(self.msg, 'extra', {}) or {}
        platform = getattr(self.msg, 'platform', '')
        author = getattr(self.msg, 'author', '?') or '?'

        # ★ Author label
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

        # ★ Content area
        self.content_layout = QVBoxLayout()
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(2)
        self._render_content(extra, platform)
        layout.addLayout(self.content_layout)

    def _build_event_row(self, layout, event):
        author = getattr(self.msg, 'author', '') or ''
        system_text = getattr(self.msg, 'system_text', '') or ''
        amount = getattr(self.msg, 'amount', None)
        tier = getattr(self.msg, 'tier', None)

        icon_map = {
            'sub': '⭐', 'resub': '⭐', 'subgift': '🎁',
            'bits': '💎', 'raid': '🚀', 'follow': '❤️',
            'share': '📢', 'join': '👋', 'system': '🔔',
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
        elif event == 'system':
            text += getattr(self.msg, 'text', '') or getattr(self.msg, 'system_text', '') or ''
        else:
            text += event

        label = QLabel(text)
        label.setTextFormat(Qt.RichText)
        label.setWordWrap(True)
        label.setStyleSheet(f"color: #fbbf24; font-size: {self._font_size}px;")
        layout.addWidget(label, 1)

    def _render_content(self, extra, platform):
        """Render message content"""
        segments = extra.get('segments', [])
        twitch_emotes = extra.get('twitch_emotes', []) or []
        sticker_url = extra.get('sticker_url', '')
        raw_text = extra.get('raw_text', '') or getattr(self.msg, 'text', '')
        is_translated = bool(extra.get('translated'))
        original_text = extra.get('original_text', '')
        source_lang = extra.get('source_lang', '')

        # ★ Sticker
        if sticker_url and not segments and not twitch_emotes:
            self._add_sticker(sticker_url)
            return

        # ★ inline layout สำหรับ text + emotes
        from PySide6.QtWidgets import QHBoxLayout as _HBox
        inline = _HBox()
        inline.setContentsMargins(0, 0, 0, 0)
        inline.setSpacing(2)

        if segments and not is_translated:
            self._render_segments_inline(inline, segments)
        elif twitch_emotes and raw_text and not is_translated:
            self._render_twitch_emotes_inline(inline, raw_text, twitch_emotes)
        else:
            text = getattr(self.msg, 'text', '') or raw_text
            lbl = self._make_wrap_label(text)
            inline.addWidget(lbl, 1)

        self.content_layout.addLayout(inline)

        # ★ ต้นฉบับ
        if is_translated and original_text:
            try:
                from flag_utils import flag_for
                flag = flag_for(source_lang)
            except Exception:
                flag = "🌐"
            orig_label = self._make_wrap_label(f"{flag} {original_text}", color="#10b981", size_offset=-1)
            self.content_layout.addWidget(orig_label)

    def _make_wrap_label(self, text, color="#e5e7eb", size_offset=0):
        fs = self._font_size + size_offset
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lbl.setFont(QFont("Kanit", fs))
        lbl.setStyleSheet(f"color: {color}; font-size: {fs}px;")
        lbl.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Preferred)
        lbl.setMinimumWidth(0)
        return lbl

    def _render_segments_inline(self, layout, segments):
        """Render segments — text wrap + emotes inline"""
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
        if text_parts:
            lbl = self._make_wrap_label(' '.join(text_parts))
            layout.addWidget(lbl)
        if emoji_chars:
            for char in emoji_chars:
                lbl = QLabel(char)
                lbl.setFont(QFont("Kanit", self._font_size + 2))
                lbl.setStyleSheet(f"font-size: {self._font_size + 2}px;")
                layout.addWidget(lbl)
        if emote_urls:
            for url in emote_urls:
                self._add_emote_to_layout(layout, url)

    def _render_twitch_emotes_inline(self, layout, text, emotes):
        """Render Twitch emotes — text wrap + emotes inline"""
        sorted_emotes = sorted(emotes, key=lambda e: e.get('start', 0))
        text_parts = []
        emote_data = []
        cur = 0
        for em in sorted_emotes:
            start = em.get('start', 0)
            end = em.get('end', 0)
            url = em.get('url', '')
            name = em.get('name', '')
            if start > cur:
                text_parts.append(text[cur:start])
            if url:
                emote_data.append(('url', url, name))
            cur = end + 1
        if cur < len(text):
            text_parts.append(text[cur:])
        if text_parts:
            lbl = self._make_wrap_label(''.join(text_parts))
            layout.addWidget(lbl)
        for kind, val, name in emote_data:
            self._add_emote_to_layout(layout, val, name)

    def _add_emote_to_layout(self, layout, url, name=''):
        """Add emote — download directly via urllib (EmoteCache returns CTkImage which can't convert to QPixmap)"""
        sz = self._font_size + 14

        # placeholder label
        lbl = QLabel(name or '⬚')
        lbl.setFixedSize(sz, sz)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet(f"color: #9ca3af; font-size: 10px;")
        layout.addWidget(lbl)

        # resolve URL
        src_url = url
        if url.startswith('/emote/') or url.startswith('/'):
            src_url = f"http://localhost:8808{url}"

        # ★ download via QThread (thread-safe) — keep ref to prevent GC
        thread = QThread()
        thread._url = src_url
        thread._sz = sz
        thread._lbl = lbl
        def _run():
            try:
                import urllib.request
                req = urllib.request.Request(thread._url, headers={'User-Agent': 'BroadcastPlayroom/2.0'})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = resp.read()
                img = QImage()
                img.loadFromData(data)
                if not img.isNull():
                    pix = QPixmap.fromImage(img).scaled(thread._sz, thread._sz, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    QTimer.singleShot(0, lambda: _set_pixmap(thread._lbl, pix))
            except Exception as e:
                logger.debug(f"Emote load failed {thread._url}: {e}")

        thread.run = _run
        thread.start()
        self._emote_threads.append(thread)

    def _add_sticker(self, url, size=64):
        lbl = QLabel()
        lbl.setFixedSize(size, size)
        lbl.setAlignment(Qt.AlignCenter)
        self.content_layout.addWidget(lbl)
        self._add_emote_to_layout_qlabel(lbl, url, size)

    def _add_emote_to_layout_qlabel(self, lbl, url, size):
        cache = _get_emote_cache()
        if cache is None:
            return
        src_url = url
        if url.startswith('/'):
            src_url = f"http://localhost:8808{url}"
        try:
            cached = cache.get_url_sync(src_url, size_px=size)
            if cached is not None:
                pix = _ctk_to_qpixmap(cached, size)
                if pix:
                    lbl.setPixmap(pix)
                return
            def _on_ready(_url, img, l=lbl, s=size):
                QTimer.singleShot(0, lambda: _apply_emote(l, img, s))
            cache.fetch_url_async(src_url, _on_ready, size_px=size)
        except Exception:
            pass

    def update_translation(self, msg):
        self.msg = msg
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_sublayout(item.layout())
        extra = getattr(msg, 'extra', {}) or {}
        self._render_content(extra, getattr(msg, 'platform', ''))

    def _clear_sublayout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        layout.deleteLater()

    def _get_platform_color(self, platform):
        colors = {
            'twitch': '#bf94ff', 'youtube': '#ff4444',
            'mylive': '#ff8800', 'tiktok': '#00f2ea', 'kick': '#53fc18',
        }
        return colors.get(platform, '#06b6d4')


# ★ helper: convert CTkImage / PIL → QPixmap
def _set_pixmap(label, pixmap):
    """set pixmap on label (called from QTimer.singleShot — main thread)"""
    if pixmap and not pixmap.isNull():
        label.setPixmap(pixmap)
        label.setText("")
        label.setStyleSheet("")


def _ctk_to_qpixmap(ctk_img, size):
    """แปลง CTkImage → QPixmap (สำหรับ Qt)"""
    try:
        # CTkImage has _photoImage (PIL ImageTk.PhotoImage)
        if hasattr(ctk_img, '_photoImage'):
            pil_img = ctk_img._photoImage
            # access PIL Image from PhotoImage
            if hasattr(pil_img, '_PhotoImage__photo'):
                # can't easily extract — try different approach
                pass
        # fallback: use the PIL image directly
        if hasattr(ctk_img, '_pil_image'):
            from PIL import Image
            pil = ctk_img._pil_image
            if hasattr(pil, 'size'):
                # convert PIL → QImage → QPixmap
                import io
                buf = io.BytesIO()
                pil.save(buf, format='PNG')
                buf.seek(0)
                img = QImage()
                img.loadFromData(buf.read())
                return QPixmap.fromImage(img).scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    except Exception as e:
        logger.debug(f"ctk_to_qpixmap failed: {e}")
    return None


def _apply_emote(label, ctk_img, size):
    """apply emote image to QLabel"""
    try:
        pix = _ctk_to_qpixmap(ctk_img, size)
        if pix:
            label.setPixmap(pix)
            label.setText("")
            label.setStyleSheet("")
    except Exception:
        pass
