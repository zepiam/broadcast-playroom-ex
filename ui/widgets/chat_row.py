"""chat_row.py — Chat message row with full emote/segment/sticker rendering

ใช้ QNetworkAccessManager สำหรับโหลด emote (Qt built-in async — thread-safe)
"""
import hashlib
import logging
import os
import urllib.request
from PySide6.QtCore import Qt, Signal, QSize, QTimer, QThread, QObject, QUrl, QByteArray
from PySide6.QtGui import QPixmap, QImage, QFont, QColor
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PySide6.QtWidgets import (
    QWidget, QLabel, QHBoxLayout, QVBoxLayout, QFrame, QSizePolicy,
)

logger = logging.getLogger("chat_row")


# ★ chat appearance settings (set จาก app.py ตอนเริ่ม + ตอน settings เปลี่ยน)
# ChatRow อ่านค่าจาก global นี้ → re-render ทุก row เมื่อค่าเปลี่ยน
_chat_settings = {
    'show_platform_icon': True,
    'author_color_mode': 'platform',   # "platform" | "random"
    'show_timestamp': False,
    'emote_size': 28,
    'font_family': 'Kanit',
    'zebra_stripes': False,            # สีพื้นหลังสลับ (zebra) แยกข้อความ
}


def set_chat_settings(show_platform_icon=None, author_color_mode=None,
                      show_timestamp=None, emote_size=None, font_family=None,
                      zebra_stripes=None):
    """อัปเดต chat appearance settings (เรียกจาก app.py)"""
    if show_platform_icon is not None:
        _chat_settings['show_platform_icon'] = show_platform_icon
    if author_color_mode is not None:
        _chat_settings['author_color_mode'] = author_color_mode
    if show_timestamp is not None:
        _chat_settings['show_timestamp'] = show_timestamp
    if emote_size is not None:
        _chat_settings['emote_size'] = emote_size
    if font_family is not None:
        _chat_settings['font_family'] = font_family
    if zebra_stripes is not None:
        _chat_settings['zebra_stripes'] = zebra_stripes


# ★ zebra colors (เข้มกว่า bg นิดหน่อย — subtle separation)
ZEBRA_COLOR = "#101524"  # odd rows


def apply_zebra_backgrounds(rows):
    """อัปเดตสีพื้นหลังของ chat rows ตาม zebra setting (เรียกจาก chat_panel)

    rows = list ของ ChatRow (index 0 = บนสุด = ใหม่สุด)
    ★ ถ้า zebra off → ล้างสีพื้นหลังทั้งหมด
    ★ ถ้า zebra on  → row ที่ index คี่ จะมีสีเข้มกว่าเล็กน้อย

    ใช้ flag `_zebra_on` + paintEvent ของ ChatRow เอง — กัน QSS หลัก override
    (app-level QWidget { background-color } ชนะ setStyleSheet บน widget instance)
    """
    zebra_on = _chat_settings.get('zebra_stripes', False)
    for i, row in enumerate(rows):
        try:
            is_odd = (i % 2 == 1)
            row._zebra_on = bool(zebra_on and is_odd)
            row.update()  # ★ trigger repaint
        except Exception:
            pass


# ★ palette สำหรับ "random" color mode — สีสดใส อ่านง่ายบนพื้นดำ
_RANDOM_PALETTE = [
    "#f87171", "#fb923c", "#fbbf24", "#facc15", "#a3e635", "#4ade80",
    "#34d399", "#22d3ee", "#38bdf8", "#60a5fa", "#818cf8", "#a78bfa",
    "#c084fc", "#e879f9", "#f472b6", "#fb7185", "#fda4af", "#fdba74",
    "#bef264", "#67e8f9", "#a5b4fc", "#d8b4fe", "#f0abfc", "#fbcfe8",
]


def _color_for_author(author: str) -> str:
    """คืนสีคงที่สำหรับ author (hash ชื่อ → index ใน palette)

    ผู้ใช้คนเดียวกันจะได้สีเดิมเสมอ ไม่ว่าจะโพสกี่ครั้ง
    """
    if not author:
        return "#06b6d4"
    h = int(hashlib.md5(author.encode("utf-8")).hexdigest(), 16)
    return _RANDOM_PALETTE[h % len(_RANDOM_PALETTE)]


# ★ QNetworkAccessManager singleton — 1 instance ใช้ทั้ง app (thread-safe)
_NAM = None
def _get_nam():
    global _NAM
    if _NAM is None:
        _NAM = QNetworkAccessManager()
    return _NAM

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

    def __init__(self, msg, parent=None, font_size=16):
        super().__init__(parent)
        self.setObjectName("ChatRow")
        # ★ ปิด QSS background painting เพื่อให้ paintEvent ของเรา (zebra) แสดงผลได้
        #    (QSS หลักมี QWidget { background-color } จะ override paintEvent)
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setAutoFillBackground(False)
        self.msg = msg
        self._font_size = font_size
        self._emote_labels = {}
        self._emote_replies = []  # ★ keep refs to QNetworkReply กัน GC ก่อน finished
        self._zebra_on = False  # ★ flag สำหรับ zebra background (set โดย apply_zebra_backgrounds)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self._build_ui()

    def paintEvent(self, event):
        """★ paint zebra background เอง — กัน QSS หลัก override

        ถ้า _zebra_on = True → paint ZEBRA_COLOR เต็ม widget ก่อน children
        """
        if self._zebra_on:
            from PySide6.QtGui import QPainter, QColor
            painter = QPainter(self)
            painter.fillRect(self.rect(), QColor(ZEBRA_COLOR))
            painter.end()
        super().paintEvent(event)

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

        # ★ Author row (icon + name + timestamp) — horizontal
        author_row = QHBoxLayout()
        author_row.setContentsMargins(0, 0, 0, 0)
        author_row.setSpacing(4)

        # ★ platform icon (ถ้าเปิด) — ใช้ ui.platform_icons (cached QPixmap)
        if _chat_settings.get('show_platform_icon', True):
            try:
                from ui.platform_icons import get_platform_pixmap
                pix = get_platform_pixmap(platform, 16)
                if not pix.isNull():
                    icon_lbl = QLabel()
                    icon_lbl.setPixmap(pix)
                    icon_lbl.setFixedSize(16, 16)
                    author_row.addWidget(icon_lbl)
            except Exception:
                pass

        # ★ Author label
        self.author_label = QLabel()
        self.author_label.setCursor(Qt.PointingHandCursor)
        self.author_label.setTextFormat(Qt.RichText)
        # ★ color: platform color หรือ random (คงที่ต่อคน)
        if _chat_settings.get('author_color_mode', 'platform') == 'random':
            author_color = _color_for_author(author)
        else:
            author_color = self._get_platform_color(platform)
        display_name = author
        # ★ timestamp (ถ้าเปิด)
        ts_html = ''
        if _chat_settings.get('show_timestamp', False):
            ts = self._get_timestamp()
            if ts:
                ts_html = f' <span style="color:#6b7280; font-size:{max(10, self._font_size-2)}px;">{ts}</span>'
        self.author_label.setText(
            f'<span style="color:{author_color}; font-weight:600;">{display_name}</span>:{ts_html}'
        )
        font_family = _chat_settings.get('font_family', 'Kanit')
        font = QFont(font_family, self._font_size)
        font.setWeight(QFont.DemiBold)
        self.author_label.setFont(font)
        self.author_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self.author_label.mousePressEvent = lambda e: self.author_clicked.emit(author)
        author_row.addWidget(self.author_label)
        author_row.addStretch()
        layout.addLayout(author_row)

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
        # ★ อ่าน emotes จากทั้ง 2 formats: raw 'emotes' (from chat client) + 'twitch_emotes' (serialized)
        raw_emotes = extra.get('emotes', []) or []
        twitch_emotes = extra.get('twitch_emotes', []) or []
        # ★ normalize raw emotes → twitch_emotes format (มี url)
        if raw_emotes and not twitch_emotes:
            for em in raw_emotes:
                eid = em.get('id')
                url = em.get('url', '')
                if url:
                    twitch_emotes.append({'name': em.get('name', ''), 'url': url,
                                          'start': em.get('start', 0), 'end': em.get('end', 0)})
                elif eid is not None:
                    twitch_emotes.append({'name': em.get('name', ''), 'url': f'/emote/{eid}',
                                          'start': em.get('start', 0), 'end': em.get('end', 0)})
        sticker_url = extra.get('sticker_url', '')
        raw_text = extra.get('raw_text', '') or getattr(self.msg, 'text', '')
        is_translated = bool(extra.get('translated'))
        original_text = extra.get('original_text', '')
        source_lang = extra.get('source_lang', '')

        # ★ Sticker
        if sticker_url and not segments and not twitch_emotes:
            self._add_sticker(sticker_url)
            return

        # ★ inline layout สำหรับ text + emotes (HBox — text กับ emote อยู่บรรทัดเดียวกัน)
        from PySide6.QtWidgets import QHBoxLayout as _HBox
        inline = _HBox()
        inline.setContentsMargins(0, 0, 0, 0)
        inline.setSpacing(2)

        rendered_anything = False
        if segments and not is_translated:
            self._render_segments_inline(inline, segments)
            rendered_anything = True
        elif twitch_emotes and raw_text and not is_translated:
            self._render_twitch_emotes_inline(inline, raw_text, twitch_emotes)
            rendered_anything = True

        if not rendered_anything:
            # plain text — แสดงเสมอ (กัน message หายเงียบ)
            text = getattr(self.msg, 'text', '') or raw_text or ''
            lbl = self._make_wrap_label(text if text else '(ไม่มีข้อความ)')
            inline.addWidget(lbl, 1)
        else:
            # ★ มี emote/segment → เพิ่ม stretch ท้าย inline เพื่อให้ text+emote ชิดซ้าย
            #   (ไม่งั้น text label ที่เป็น MinimumExpanding จะขยายเต็ม → emote ถูกไล่ไปขวาสุด)
            inline.addStretch(1)

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
        font_family = _chat_settings.get('font_family', 'Kanit')
        lbl.setFont(QFont(font_family, fs))
        lbl.setStyleSheet(f"color: {color}; font-size: {fs}px; font-family: '{font_family}';")
        lbl.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Preferred)
        lbl.setMinimumWidth(0)
        return lbl

    def _render_segments_inline(self, layout, segments):
        """Render segments — text wrap + emotes inline

        ★ inline = text + emote อยู่บรรทัดเดียวกัน → text label ใช้ Preferred (ย่อตามเนื้อหา)
          ไม่ใช่ MinimumExpanding (ขยายเต็ม → emote ถูกไล่ไปขวาสุด)
        """
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
            # ★ inline: ย่อตามเนื้อหา (Preferred) ไม่ขยายเต็ม — กัน emote ถูกไล่ไปขวาสุด
            lbl.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
            layout.addWidget(lbl, 0, Qt.AlignBottom)
        if emoji_chars:
            for char in emoji_chars:
                lbl = QLabel(char)
                lbl.setFont(QFont("Kanit", self._font_size + 2))
                lbl.setStyleSheet(f"font-size: {self._font_size + 2}px;")
                layout.addWidget(lbl, 0, Qt.AlignBottom)
        if emote_urls:
            for url in emote_urls:
                self._add_emote_to_layout(layout, url)

    def _render_twitch_emotes_inline(self, layout, text, emotes):
        """Render Twitch emotes — text + emotes inline"""
        sorted_emotes = sorted(emotes, key=lambda e: e.get('start', 0))
        text_parts = []
        emote_urls = []
        cur = 0
        for em in sorted_emotes:
            start = em.get('start', 0)
            end = em.get('end', 0)
            url = em.get('url', '')
            name = em.get('name', '')
            if start > cur:
                text_parts.append(text[cur:start])
            if url:
                emote_urls.append((url, name))
            cur = end + 1
        if cur < len(text):
            text_parts.append(text[cur:])
        # ★ render text (ถ้ามี — ถ้าไม่มี text เลย เช่น "Kappa" = emote ล้วน → ข้าม)
        if text_parts:
            full_text = ''.join(text_parts).strip()
            if full_text:
                lbl = self._make_wrap_label(full_text)
                # ★ inline: ย่อตามเนื้อหา (Preferred) + AlignBottom → emote ต่อท้าย text ตรง baseline
                lbl.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
                layout.addWidget(lbl, 0, Qt.AlignBottom)
        # ★ render emotes inline
        for url, name in emote_urls:
            self._add_emote_to_layout(layout, url, name)
        # ★ ถ้าไม่มีทั้ง text และ emote → แสดง text เดิม (กันหาย)
        if not text_parts and not emote_urls:
            lbl = self._make_wrap_label(text)
            layout.addWidget(lbl)

    def _add_emote_to_layout(self, layout, url, name=''):
        """Add emote — download via QNetworkAccessManager (Qt built-in async, thread-safe)

        QNetworkAccessManager ทำงานใน main thread event loop → ไม่มีปัญหา thread-safety
        ต่างจาก QThread + QTimer.singleShot ที่ไม่ทำงานข้าม thread
        """
        # ★ ใช้ emote size จาก settings (default 28px) — ความสูงเป็นหลัก
        sz = int(_chat_settings.get('emote_size', 28))

        # placeholder label (จะถูกแทนด้วย pixmap ถ้าโหลดสำเร็จ)
        lbl = QLabel(name or '⬚')
        lbl.setFixedHeight(sz)  # ★ กำหนดแค่ความสูง — ความกว้างขยายตามอัตราส่วน emote
        lbl.setMinimumWidth(sz // 2)
        # ★ content alignment ในกรอบ label เอง (pixmap ชิดขวาล่าง เพื่อต่อจาก text ด้านซ้าย)
        lbl.setAlignment(Qt.AlignRight | Qt.AlignBottom)
        lbl.setStyleSheet(f"color: #9ca3af; font-size: 12px;")
        # ★ AlignBottom ใน parent QHBoxLayout → emote ตรง baseline ของ text (ไม่ลอยกลาง)
        #   AlignLeft → ไม่กลางจอ (กัน "center เฉย" เมื่อมีแค่ emote อย่างเดียว)
        layout.addWidget(lbl, 0, Qt.AlignBottom | Qt.AlignLeft)

        # resolve URL — relative → composer server (port 8808)
        src_url = url
        if url.startswith('/emote/') or url.startswith('/'):
            src_url = f"http://localhost:8808{url}"

        # ★ download via QNetworkAccessManager (main thread event loop)
        try:
            nam = _get_nam()
            req = QNetworkRequest(QUrl(src_url))
            req.setRawHeader(b'User-Agent', b'BroadcastPlayroom/2.0')
            reply = nam.get(req)
            # ★ keep ref กัน GC (QNetworkReply ต้องมี parent หรือ ref)
            reply._lbl = lbl
            reply._sz = sz
            reply._url = src_url
            reply.finished.connect(lambda: self._on_emote_loaded(reply))
            self._emote_replies.append(reply)  # keep ref กัน GC
        except Exception as e:
            logger.debug(f"Emote NAM request failed {src_url}: {e}")

    def _on_emote_loaded(self, reply):
        """callback เมื่อ QNetworkReply finished — set pixmap บน label

        ★ scale ตามความสูง (height=sz) — ความกว้างขยายตาม aspect ratio
          กัน emote ถูกบีบ (เดิมใช้ sz×sz + KeepAspectRatio → emote แนวนอนถูกบีบ)
        """
        try:
            lbl = getattr(reply, '_lbl', None)
            sz = getattr(reply, '_sz', 28)
            if lbl is None:
                return
            if reply.error() != QNetworkReply.NoError:
                logger.debug(f"Emote load error: {reply.errorString()}")
                return
            data = reply.readAll()
            img = QImage()
            img.loadFromData(QByteArray(data))
            if not img.isNull():
                # ★ scale ตามความสูง (height=sz) ความกว้างตามอัตราส่วนเดิม
                orig_w = img.width()
                orig_h = img.height()
                if orig_h > 0:
                    new_w = max(1, int(orig_w * sz / orig_h))
                    new_h = sz
                else:
                    new_w, new_h = sz, sz
                pix = QPixmap.fromImage(img).scaled(
                    new_w, new_h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation,
                )
                lbl.setPixmap(pix)
                lbl.setFixedWidth(new_w)  # ★ ปรับความกว้างตาม pixmap จริง
                lbl.setText("")
                lbl.setStyleSheet("")
        except Exception as e:
            logger.debug(f"_on_emote_loaded error: {e}")
        finally:
            reply.deleteLater()

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

    def _get_platform_icon_path(self, platform):
        """คืน path ของไอคอนแพลตฟอร์ม (assets/*.png) หรือ None ถ้าไม่มี"""
        try:
            import os
            # base_dir = โฟลเดอร์ที่ assets/ อยู่ (2 ระดับจาก ui/widgets/)
            base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            icon_map = {
                'twitch': 'twitch.png', 'youtube': 'youtube.png',
                'mylive': 'mylive.png', 'tiktok': 'tiktok.png', 'kick': 'kick.png',
            }
            fname = icon_map.get(platform)
            if fname:
                path = os.path.join(base, 'assets', fname)
                if os.path.exists(path):
                    return path
        except Exception:
            pass
        return None

    def _get_timestamp(self):
        """คืน timestamp [HH:MM] จาก msg.timestamp หรือเวลาตอนสร้าง row"""
        try:
            from datetime import datetime
            # ★ ถ้า msg มี timestamp → ใช้อันนั้น
            ts = getattr(self.msg, 'timestamp', None)
            if ts is not None:
                if isinstance(ts, str):
                    try:
                        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                        return dt.strftime('%H:%M')
                    except Exception:
                        pass
                elif isinstance(ts, datetime):
                    return ts.strftime('%H:%M')
            # ★ fallback: ใช้เวลาตอนสร้าง ChatRow (ใกล้เคียงเวลาส่งจริง)
            return datetime.now().strftime('%H:%M')
        except Exception:
            return None


# ★ helper: convert CTkImage / PIL → QPixmap
def _set_pixmap(label, pixmap):
    """set pixmap on label (เก็บไว้เผื่อใช้ — _add_emote_to_layout_qlabel ยังใช้ QTimer path)"""
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
