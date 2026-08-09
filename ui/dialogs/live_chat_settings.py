"""live_chat_settings.py — Live Chat Settings dialog

เปิดจากปุ่มเฟือง ⚙ ใน chat panel header
ตั้งค่า:
1. แสดงไอคอนแพลตฟอร์มหน้าชื่อ
2. สีชื่อผู้แชท: ตามแพลตฟอร์ม / สุ่มคงที่
3. แสดง timestamp หลังชื่อ
4. ขนาด emote
5. ฟอนต์ (Google Fonts ภาษาไทย)
"""
import logging
import os
import tempfile
import urllib.request
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QFontDatabase
from PySide6.QtWidgets import (
    QDialog, QWidget, QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QCheckBox, QComboBox, QSlider, QButtonGroup, QRadioButton, QSizePolicy,
    QScrollArea,
)

logger = logging.getLogger("live_chat_settings")

# ── Google Fonts dynamic loader ──
# Qt ไม่สามารถโหลด web fonts → ดาวน์โหลด .ttf จาก Google Fonts API แล้ว register ผ่าน QFontDatabase
_LOADED_FONTS = set()  # family names ที่โหลดแล้ว


def _load_google_font(family: str) -> bool:
    """โหลด Google Font จาก fonts.gstatic.com → register ใน QFontDatabase

    คืน True ถ้าโหลดสำเร็จ (หรือโหลดแล้ว) False ถ้าล้มเหลว
    """
    if family in _LOADED_FONTS:
        return True
    # Google Fonts CSS API → ดึง URL ของ .ttf (latin + thai subset)
    # ใช้ user-agent browser เพื่อให้ได้ woff2/ttf ที่ถูกต้อง
    try:
        css_url = f"https://fonts.googleapis.com/css2?family={family.replace(' ', '+')}:wght@400;500;600;700&display=swap"
        req = urllib.request.Request(css_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=8) as resp:
            css = resp.read().decode('utf-8')
        # extract .ttf URL จาก CSS (ดึงอันแรกที่ unicode-range ครอบ thai/latin)
        import re
        # ดึงทุก @font-face block → เลือกอันที่มี src url
        ttf_urls = re.findall(r'src:\s*url\((https://[^)]+\.ttf)\)', css)
        if not ttf_urls:
            # ลอง woff2 → Qt ไม่ support woff2 ตรงๆ → ข้าม
            return False
        loaded_any = False
        for ttf_url in ttf_urls:
            try:
                req2 = urllib.request.Request(ttf_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req2, timeout=15) as resp2:
                    data = resp2.read()
                # save ลง temp file (QFontDatabase ต้องการ path)
                tmp = os.path.join(tempfile.gettempdir(), f"gfont_{family.replace(' ', '_')}.ttf")
                with open(tmp, 'wb') as f:
                    f.write(data)
                font_id = QFontDatabase.addApplicationFont(tmp)
                if font_id >= 0:
                    loaded_any = True
            except Exception:
                continue
        if loaded_any:
            _LOADED_FONTS.add(family)
            return True
    except Exception as e:
        logger.debug(f"load_google_font({family}) failed: {e}")
    return False

COL_BG = "#0a0e1a"
COL_CARD = "#131726"
COL_BORDER = "#2a2f45"
COL_TEXT = "#e5e7eb"
COL_TEXT_DIM = "#9ca3af"
COL_HEADING = "#f59e0b"
COL_ACCENT = "#7c3aed"


class LiveChatSettingsDialog(QDialog):
    """Live Chat Settings — ปรับแต่งหน้าตาแชทสด"""

    settings_changed = Signal()  # emit เมื่อ settings เปลี่ยน (เพื่อ re-render chat)

    def __init__(self, parent_app):
        super().__init__(parent_app if isinstance(parent_app, QWidget) else None)
        self.parent_app = parent_app
        self.settings = getattr(parent_app, 'settings', None)
        self.setWindowTitle("💬 ตั้งค่าแชทสด")
        self.setGeometry(150, 120, 880, 640)
        self.setMinimumSize(820, 600)
        self._preview_rows = []  # ★ chat row refs ใน preview pane
        self._build_ui()
        self._load_values()

    # ════════════════════════════════════════════════════════════
    # UI helpers
    # ════════════════════════════════════════════════════════════
    def _card(self, parent_layout, title):
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {COL_CARD};
                border: 1px solid {COL_BORDER};
                border-radius: 10px;
            }}
            QLabel#cardtitle {{
                background: transparent; border: none;
                color: {COL_HEADING};
                font-size: 14px; font-weight: 700;
                padding: 8px 12px 4px 12px;
            }}
        """)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(10, 4, 10, 10)
        cl.setSpacing(6)
        title_lbl = QLabel(title)
        title_lbl.setObjectName("cardtitle")
        cl.addWidget(title_lbl)
        parent_layout.addWidget(card)
        return cl

    def _hrow(self, parent_layout, label_text, label_w=200, indent=0):
        row = QHBoxLayout()
        row.setContentsMargins(indent, 0, 0, 0)
        row.setSpacing(8)
        if label_text:
            lbl = QLabel(label_text)
            lbl.setFixedWidth(label_w - indent)
            lbl.setStyleSheet(f"color: {COL_TEXT_DIM}; font-size: 13px;")
            row.addWidget(lbl)
        parent_layout.addLayout(row)
        return row

    def _checkbox_row(self, parent_layout, label, key, indent=0):
        row = QHBoxLayout()
        row.setContentsMargins(indent, 0, 0, 0)
        cb = QCheckBox(label)
        cb.setStyleSheet(f"color: {COL_TEXT}; font-size: 13px; spacing: 8px;")
        def _on(state):
            setattr(self.settings, key, bool(state))
            if key == 'chat_show_platform_icon':
                self._update_icon_preview()
            self._live_update()
        cb.stateChanged.connect(_on)
        cb._key = key
        row.addWidget(cb)
        parent_layout.addLayout(row)
        return cb

    def _combo_row(self, parent_layout, label, items, key=None, indent=0, on_change=None):
        row = self._hrow(parent_layout, label, indent=indent)
        combo = QComboBox()
        combo.setStyleSheet(f"""
            QComboBox {{
                background: {COL_BG}; color: {COL_TEXT};
                border: 1px solid {COL_BORDER}; border-radius: 4px;
                padding: 4px 10px; min-height: 22px; font-size: 13px;
            }}
            QComboBox::drop-down {{ border: none; width: 20px; }}
            QComboBox QAbstractItemView {{
                background: {COL_CARD}; color: {COL_TEXT};
                selection-background-color: {COL_ACCENT};
                border: 1px solid {COL_BORDER};
            }}
        """)
        combo.setMinimumWidth(180)
        for it in items:
            combo.addItem(it[1] if isinstance(it, (tuple, list)) else it)
            combo.setItemData(combo.count() - 1, it[0] if isinstance(it, (tuple, list)) else it)
        combo._key = key
        def _on_idx(idx):
            data = combo.itemData(idx)
            if key:
                setattr(self.settings, key, data)
                self._live_update()
            if on_change:
                on_change(data)
        combo.currentIndexChanged.connect(_on_idx)
        row.addWidget(combo)
        row.addStretch()
        return combo

    # ════════════════════════════════════════════════════════════
    # Build UI
    # ════════════════════════════════════════════════════════════
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ★ Header
        header = QFrame()
        header.setFixedHeight(50)
        header.setStyleSheet(f"background: {COL_CARD}; border-bottom: 1px solid {COL_BORDER};")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 0, 16, 0)
        title = QLabel("💬 ตั้งค่าแชทสด")
        title.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {COL_HEADING};")
        hl.addWidget(title)
        hl.addStretch()
        outer.addWidget(header)

        # ★ Body: split horizontal (settings ซ้าย | preview ขวา)
        body = QWidget()
        body.setStyleSheet(f"background: {COL_BG};")
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # ★ Left: settings content (scrollable)
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        left_content = QWidget()
        left_content.setStyleSheet("background: transparent;")
        cl = QVBoxLayout(left_content)
        cl.setContentsMargins(20, 16, 12, 16)
        cl.setSpacing(10)

        # ── Card 1: ไอคอน + ชื่อ ──
        card_name = self._card(cl, "👤 ชื่อ + ไอคอน")
        self.icon_cb = self._checkbox_row(card_name, "แสดงไอคอนแพลตฟอร์มหน้าชื่อ", "chat_show_platform_icon")
        self.icon_preview = QLabel()
        self.icon_preview.setStyleSheet(f"color: {COL_TEXT_DIM}; font-size: 12px; padding-left: 28px;")
        self._update_icon_preview()
        card_name.addWidget(self.icon_preview)
        color_lbl = QLabel("สีชื่อผู้แชท:")
        color_lbl.setStyleSheet(f"color: {COL_TEXT}; font-size: 13px; padding-top: 6px;")
        card_name.addWidget(color_lbl)
        radio_row = QHBoxLayout()
        radio_row.setContentsMargins(0, 0, 0, 0)
        self.color_group = QButtonGroup(self)
        self.color_radios = {}
        for mode, mode_label, desc in [
            ("platform", "สีตามแพลตฟอร์ม", "ทุกคนในแพลตฟอร์มเดียวกันจะมีสีเดียวกัน"),
            ("random", "สีสุ่ม (คงที่ต่อคน)", "แต่ละคนจะมีสีเฉพาะของตัวเอง ไม่เปลี่ยนไป"),
        ]:
            rb = QRadioButton(mode_label)
            rb.setStyleSheet(f"color: {COL_TEXT}; font-size: 13px; spacing: 6px;")
            rb.toggled.connect(lambda checked, mk=mode: self._on_color_mode(mk) if checked else None)
            self.color_group.addButton(rb)
            self.color_radios[mode] = rb
            radio_row.addWidget(rb)
        radio_row.addStretch()
        card_name.addLayout(radio_row)
        self.color_preview = QLabel()
        self.color_preview.setStyleSheet(f"color: {COL_TEXT_DIM}; font-size: 12px; padding-left: 28px; padding-top: 4px;")
        self._update_color_preview()
        card_name.addWidget(self.color_preview)
        self.ts_cb = self._checkbox_row(card_name, "แสดงเวลาด้านหลังชื่อผู้โพส [HH:MM]", "chat_show_timestamp")
        self.zebra_cb = self._checkbox_row(card_name, "สีพื้นหลังสลับ (Zebra) — แยกข้อความให้อ่านง่าย", "chat_zebra_stripes")

        # ── Card 2: Emote ──
        card_emote = self._card(cl, "😀 Emote")
        emote_row = QHBoxLayout()
        emote_row.setContentsMargins(0, 0, 0, 0)
        emote_lbl = QLabel("ขนาด Emote")
        emote_lbl.setFixedWidth(140)
        emote_lbl.setStyleSheet(f"color: {COL_TEXT_DIM}; font-size: 13px;")
        emote_row.addWidget(emote_lbl)
        self.emote_slider = QSlider(Qt.Horizontal)
        self.emote_slider.setMinimum(16)
        self.emote_slider.setMaximum(56)
        self.emote_slider._key = "chat_emote_size"
        self.emote_val = QLabel()
        self.emote_val.setMinimumWidth(50)
        self.emote_val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.emote_val.setStyleSheet(f"color: {COL_ACCENT}; font-size: 13px; font-weight: 600;")
        def _on_emote(v):
            self.emote_val.setText(f"{v}px")
            self.settings.chat_emote_size = v
            self._live_update()
        self.emote_slider.valueChanged.connect(_on_emote)
        emote_row.addWidget(self.emote_slider, 1)
        emote_row.addWidget(self.emote_val)
        card_emote.addLayout(emote_row)

        # ── Card 3: ฟอนต์ ──
        try:
            from settings import GOOGLE_FONTS
            font_items = list(GOOGLE_FONTS.items())
        except Exception:
            font_items = [("Kanit", "Kanit")]
        card_font = self._card(cl, "🔤 ฟอนต์")
        self.font_combo = self._combo_row(card_font, "ฟอนต์", font_items, key="chat_font_family")

        cl.addStretch()
        left_scroll.setWidget(left_content)
        body_layout.addWidget(left_scroll, 1)

        # ★ Right: chat preview pane (fixed width 340px) — แสดงตัวอย่างแชทจริง
        self._build_preview_pane(body_layout)

        outer.addWidget(body, 1)

        # ★ Bottom buttons
        bottom = QFrame()
        bottom.setFixedHeight(54)
        bottom.setStyleSheet(f"background: {COL_CARD}; border-top: 1px solid {COL_BORDER};")
        bl = QHBoxLayout(bottom)
        bl.setContentsMargins(16, 0, 16, 0)
        bl.addStretch()
        btn_close = QPushButton("ปิด")
        btn_close.setFixedWidth(90)
        btn_close.setFixedHeight(32)
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setStyleSheet(f"""
            QPushButton {{
                background: {COL_CARD}; color: {COL_TEXT};
                border: 1px solid {COL_BORDER}; border-radius: 6px; padding: 0 16px;
            }}
            QPushButton:hover {{ background: #1c2033; border-color: {COL_ACCENT}; }}
        """)
        btn_close.clicked.connect(self.accept)
        bl.addWidget(btn_close)
        outer.addWidget(bottom)

    def _build_preview_pane(self, parent_layout):
        """สร้าง chat preview pane ฝั่งขวา — แสดงตัวอย่างแชท 6 แถว + zebra"""
        from PySide6.QtWidgets import QScrollArea
        pane = QFrame()
        pane.setFixedWidth(340)
        pane.setStyleSheet(f"""
            QFrame {{
                background-color: #0a0e1a;
                border: none;
            }}
        """)
        pane_layout = QVBoxLayout(pane)
        pane_layout.setContentsMargins(12, 12, 12, 12)
        pane_layout.setSpacing(8)
        header = QLabel("👁️ ตัวอย่างแชท")
        header.setStyleSheet(f"color: {COL_HEADING}; font-size: 14px; font-weight: 700;")
        pane_layout.addWidget(header)
        hint = QLabel("แสดงผลตาม settings (zebra + icon + สี + emote + ฟอนต์)")
        hint.setStyleSheet(f"color: #6b7280; font-size: 11px;")
        hint.setWordWrap(True)
        pane_layout.addWidget(hint)
        # ★ chat container (scrollable)
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.preview_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.preview_container = QWidget()
        self.preview_container.setStyleSheet("background: transparent;")
        self.preview_layout = QVBoxLayout(self.preview_container)
        self.preview_layout.setContentsMargins(0, 0, 0, 0)
        self.preview_layout.setSpacing(0)
        self.preview_layout.addStretch()
        self.preview_scroll.setWidget(self.preview_container)
        pane_layout.addWidget(self.preview_scroll, 1)
        parent_layout.addWidget(pane)

    # ════════════════════════════════════════════════════════════
    # Load values
    # ════════════════════════════════════════════════════════════
    def _load_values(self):
        if not self.settings:
            return
        s = self.settings
        self.icon_cb.setChecked(bool(getattr(s, 'chat_show_platform_icon', True)))
        mode = getattr(s, 'chat_author_color_mode', 'platform')
        if mode in self.color_radios:
            self.color_radios[mode].setChecked(True)
        else:
            self.color_radios['platform'].setChecked(True)
        self.ts_cb.setChecked(bool(getattr(s, 'chat_show_timestamp', False)))
        self.zebra_cb.setChecked(bool(getattr(s, 'chat_zebra_stripes', False)))
        self.emote_slider.setValue(int(getattr(s, 'chat_emote_size', 28)))
        self.emote_val.setText(f"{self.emote_slider.value()}px")
        # font
        cur_font = getattr(s, 'chat_font_family', 'Kanit')
        for i in range(self.font_combo.count()):
            if self.font_combo.itemData(i) == cur_font:
                self.font_combo.setCurrentIndex(i)
                break
        self._update_icon_preview()
        self._update_color_preview()
        self._render_preview()  # ★ สร้างตัวอย่าง chat row จริง

    # ════════════════════════════════════════════════════════════
    # Update previews
    # ════════════════════════════════════════════════════════════
    def _update_icon_preview(self):
        on = bool(getattr(self.settings, 'chat_show_platform_icon', True))
        if on:
            self.icon_preview.setText("ตัวอย่าง: 📺 TwitchUser")
        else:
            self.icon_preview.setText("ตัวอย่าง: TwitchUser (ไม่มีไอคอน)")

    def _update_color_preview(self):
        mode = getattr(self.settings, 'chat_author_color_mode', 'platform')
        if mode == 'platform':
            self.color_preview.setText(
                "ตัวอย่าง: "
                "<span style='color:#bf94ff;'>ชื่อ Twitch</span>, "
                "<span style='color:#ff4444;'>ชื่อ YouTube</span>"
            )
        else:
            from ui.widgets.chat_row import _color_for_author
            c1 = _color_for_author("men9ch")
            c2 = _color_for_author("สมชาย")
            c3 = _color_for_author("testuser123")
            self.color_preview.setText(
                "ตัวอย่าง: "
                f"<span style='color:{c1};'>men9ch</span>, "
                f"<span style='color:{c2};'>สมชาย</span>, "
                f"<span style='color:{c3};'>testuser</span>"
            )
        self.color_preview.setTextFormat(Qt.RichText)

    # ════════════════════════════════════════════════════════════
    # Handlers
    # ════════════════════════════════════════════════════════════
    def _on_color_mode(self, mode):
        self.settings.chat_author_color_mode = mode
        self._update_color_preview()
        self._live_update()

    def _live_update(self):
        """save settings + notify app ให้ re-render chat + update previews"""
        try:
            from settings import save_settings
            save_settings(self.settings)
        except Exception as e:
            logger.debug(f"save in live_update failed: {e}")
        self._render_preview()  # ★ re-render live preview
        self.settings_changed.emit()

    def _render_preview(self):
        """สร้าง chat row ตัวอย่าง 6 แถว (ไทย/อังกฤษ/ญี่ปุ่น/emote) ด้วย settings ปัจจุบัน

        แสดงผลเหมือน live chat จริง: zebra + icon + สี + timestamp + emote + ฟอนต์
        """
        try:
            from ui.widgets.chat_row import ChatRow, set_chat_settings, apply_zebra_backgrounds
            from chat_twitch import ChatMessage
        except Exception as e:
            logger.debug(f"preview imports failed: {e}")
            return
        # ★ push settings ปัจจุบันเข้า ChatRow global (preview ใช้ค่าเดียวกับจริง)
        s = self.settings
        font_family = getattr(s, 'chat_font_family', 'Kanit')
        _load_google_font(font_family)
        set_chat_settings(
            show_platform_icon=getattr(s, 'chat_show_platform_icon', True),
            author_color_mode=getattr(s, 'chat_author_color_mode', 'platform'),
            show_timestamp=getattr(s, 'chat_show_timestamp', False),
            emote_size=getattr(s, 'chat_emote_size', 28),
            font_family=font_family,
            zebra_stripes=getattr(s, 'chat_zebra_stripes', False),
        )
        # ★ ล้าง preview rows เก่า
        layout = self.preview_layout
        for row in self._preview_rows:
            layout.removeWidget(row)
            row.setParent(None)
            row.deleteLater()
        self._preview_rows.clear()
        # ★ 6 ตัวอย่างหลากหลาย: ไทย/อังกฤษ/ญี่ปุ่น/emote
        samples = [
            ChatMessage(
                platform='twitch', author='men9ch', event='message',
                text='สวัสดีครับทุกคน ยินดีต้อนรับเข้าสู่ช่อง Kappa',
                extra={
                    'emotes': [{'id': '25', 'name': 'Kappa', 'start': 38, 'end': 42,
                                'url': 'https://static-cdn.jtvnw.net/emoticons/v2/25/default/dark/1.0'}],
                    'raw_text': 'สวัสดีครับทุกคน ยินดีต้อนรับเข้าสู่ช่อง Kappa',
                },
            ),
            ChatMessage(
                platform='youtube', author='GamingFan123', event='message',
                text='Hello! This stream is amazing!',
                extra={},
            ),
            ChatMessage(
                platform='tiktok', author='たろう', event='message',
                text='こんにちは！よろしくお願いします 😊',
                extra={},
            ),
            ChatMessage(
                platform='kick', author='StreamMaster', event='message',
                text='GG WP that was epic LULW',
                extra={
                    'emotes': [{'id': '84635', 'name': 'LULW', 'start': 20, 'end': 23,
                                'url': 'https://static-cdn.jtvnw.net/emoticons/v2/84635/default/dark/1.0'}],
                    'raw_text': 'GG WP that was epic LULW',
                },
            ),
            ChatMessage(
                platform='twitch', author='สมหญิง', event='message',
                text='รักช่องนี้มากค่ะ ดูทุกวันเลย',
                extra={},
            ),
            ChatMessage(
                platform='mylive', author='viewer_pro', event='message',
                text='วันนี้สตรีมอะไรครับ POGGERS',
                extra={
                    'emotes': [{'id': '305954156', 'name': 'POGGERS', 'start': 22, 'end': 29,
                                'url': 'https://static-cdn.jtvnw.net/emoticons/v2/305954156/default/dark/1.0'}],
                    'raw_text': 'วันนี้สตรีมอะไรครับ POGGERS',
                },
            ),
        ]
        font_size = getattr(self.parent_app, 'chat_panel', None)
        fs = getattr(font_size, '_current_font_size', 16) if font_size else 16
        for m in samples:
            row = ChatRow(m, self.preview_container, fs)
            # insert ด้านบน (index 0) → ใหม่สุดอยู่บนเหมือน live chat
            self.preview_layout.insertWidget(0, row)
            self._preview_rows.append(row)
        # ★ apply zebra stripes
        try:
            apply_zebra_backgrounds(self._preview_rows)
        except Exception:
            pass

