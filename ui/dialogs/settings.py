"""settings.py — Settings dialog (sidebar layout, modern style)

เปลี่ยนจาก tab แบบเดิม → sidebar layout (ซ้ายเลือกหมวด → ขวาแสดง content)
"""
import logging
from PySide6.QtCore import Qt, Signal, QTimer, QEvent
from PySide6.QtWidgets import (
    QDialog, QWidget, QFrame, QLabel, QPushButton, QLineEdit, QCheckBox,
    QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea,
    QComboBox, QSlider, QSpinBox, QListWidget, QListWidgetItem,
    QMessageBox, QStackedWidget, QSizePolicy,
    QButtonGroup, QRadioButton,
    QTableWidget, QTableWidgetItem,
)
import ui.theme as theme  # ★ อ้าง theme.COLOR_X สดตอน build/re-theme (ไม่ใช่ from-import ตายตัว)


class _ContentStack(QStackedWidget):
    """QStackedWidget ที่ sizeHint ตาม "หน้าปัจจุบัน" เท่านั้น

    ★ ค่า default ของ Qt คือ sizeHint/minimumSizeHint ของ QStackedWidget = ค่ามากสุด
    ของทุกหน้าที่เคยเพิ่มเข้ากอง (กันหน้าต่างสั่นตอนสลับหน้า) — ผลข้างเคียงคือหน้าที่
    เนื้อหาน้อยนิดเดียว (เช่น Theme, Canvas) ก็โดน QScrollArea ที่ห่ออยู่คำนวณพื้นที่
    ตามหน้าที่ยาวที่สุดในกอง (เช่น Chat Bot) เลยมี scrollbar ค้างทั้งที่เนื้อหาไม่พอเลื่อน
    """

    def sizeHint(self):
        w = self.currentWidget()
        return w.sizeHint() if w is not None else super().sizeHint()

    def minimumSizeHint(self):
        w = self.currentWidget()
        return w.minimumSizeHint() if w is not None else super().minimumSizeHint()


class _ClickableLabel(QLabel):
    """QLabel ที่คลิกได้ — emit clicked signal (ลองรับทั้ง click และ release)"""
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_MouseTracking, False)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

logger = logging.getLogger("settings")


class SettingsDialog(QDialog):
    """Settings dialog — sidebar layout (modern flat design)"""

    settings_changed = Signal()  # emit เมื่อ settings เปลี่ยน (บันทึกแล้ว)
    _obs_test_sig = Signal(str, object)  # OBS test result from background thread
    _update_result_sig = Signal(object)  # update check result from background thread

    def __init__(self, parent_app):
        super().__init__(parent_app if isinstance(parent_app, QWidget) else None)
        self.parent_app = parent_app
        self.settings = getattr(parent_app, 'settings', None)
        self.setWindowTitle("⚙ ตั้งค่า")
        self.setGeometry(150, 110, 980, 720)
        self.setMinimumSize(880, 640)
        self.setModal(True)
        # ★ Twitch OAuth handlers (จะถูก setup จาก app.py หลังสร้าง dialog)
        self._twitch_oauth_connect_handler = None
        self._twitch_oauth_disconnect_handler = None
        self._twitch_oauth_refresh = None
        self._kick_oauth_connect_handler = None
        self._kick_oauth_disconnect_handler = None
        self._youtube_oauth_connect_handler = None
        self._youtube_oauth_disconnect_handler = None
        self._youtube_oauth_refresh = None
        self._build_ui()
        self._load_values()

    def showEvent(self, event):
        """★ บังคับ layout ใหม่หลัง show — แก้ Windows/Qt ที่ content บีบจนกว่าจะ drag"""
        super().showEvent(event)
        from PySide6.QtCore import QTimer
        def _force_refresh():
            self.resize(980, 720)
            pos = self.pos()
            self.move(pos.x() + 1, pos.y() + 1)
            self.move(pos.x(), pos.y())
            for child in self.findChildren(QWidget):
                child.updateGeometry()
            self.update()
            self._resize_stack_to_current()
        QTimer.singleShot(0, _force_refresh)

    def resizeEvent(self, event):
        """★ ลาก resize หน้าต่าง Settings → คำนวณความสูงหน้าปัจจุบันใหม่ตาม viewport ใหม่"""
        super().resizeEvent(event)
        self._resize_stack_to_current()

    def _resize_stack_to_current(self):
        """บังคับความสูง content_stack ให้พอดีกับ "หน้าปัจจุบัน" เท่านั้น

        ★ เจอจริงว่า QScrollArea (widgetResizable=True) ไม่ query sizeHint()/
        minimumSizeHint() ของ QStackedWidget ใหม่เองตอนสลับหน้า (แม้ override
        ทั้งสองเมธอดแล้ว + ลอง updateGeometry()/LayoutRequest event/nudge resize
        ก็ไม่ช่วย) → มันค้างใช้ความสูงของหน้าที่ยาวที่สุดที่เคยโชว์ตลอดไป
        ทำให้ทุกหน้ามี scrollbar เท่าหน้าที่ยาวสุด (เช่น 🤖 Chat Bot) แม้เนื้อหาน้อยนิดเดียว
        วิธีแก้ที่ยืนยันแล้วว่าได้ผลจริง (ทดสอบ headless): บังคับ setFixedHeight()
        ตรงๆ ตาม sizeHint ของหน้าปัจจุบัน (หรือเท่า viewport ถ้าเนื้อหาน้อยกว่า viewport)
        """
        widget = self.content_stack.currentWidget()
        if widget is None:
            return
        vp_h = self.content_scroll.viewport().height()
        if vp_h <= 0:
            vp_h = self.content_scroll.height()  # ★ fallback ตอนยังไม่ show จริง (viewport = 0)
        target_h = max(widget.sizeHint().height(), vp_h)
        self.content_stack.setFixedHeight(target_h)

    def _build_ui(self):
        # ★ Layout structure (สะอาด — ไม่ย้าย layout ภายหลัง):
        #   dialog (QVBoxLayout)
        #     ├─ body (QHBoxLayout): category sidebar | settings content | preview pane
        #     └─ bottom bar (buttons)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ★ Body container (sidebar + content + preview)
        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # ★ Left sidebar (category list) — ขยายจาก 200 → 220 กัน sidescroll
        self.sidebar = QListWidget()
        self.sidebar.setFixedWidth(220)
        self.sidebar.setObjectName("SettingsSidebar")
        self._apply_sidebar_theme_qss()
        categories = [
            ("🔌 แพลตฟอร์ม", "platforms"),
            ("🔊 TTS", "tts"),
            ("🎨 Theme", "app_theme"),
            ("🌐 การแปล", "translate"),
            ("🎮 Playroom", "playroom"),
            ("🎨 Canvas", "canvas"),
            ("🔌 OBS WebSocket", "obs_ws"),
            ("🔔 แจ้งเตือน", "notifications"),
            ("🚫 NG Words", "ng"),
            ("🔄 Replace", "replace"),
            ("🚫 Blocklist & Spam", "block"),
            ("🎟 โค้ดลับ", "secret_code"),
            ("🪟 Overlay+", "overlay_plus"),
            ("🤖 Chat Bot", "twitch_bot"),
            ("💚 สนับสนุน", "supporters"),
            ("ℹ️ เกี่ยวกับ", "about"),
        ]
        for label, key in categories:
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, key)
            # ★ เพิ่ม Twitch icon สำหรับ Chat Bot section
            if key == "twitch_bot":
                try:
                    from ui.platform_icons import get_platform_pixmap
                    pix = get_platform_pixmap("twitch", 16)
                    if not pix.isNull():
                        from PySide6.QtGui import QIcon
                        item.setIcon(QIcon(pix))
                except Exception:
                    pass
            self.sidebar.addItem(item)
        self.sidebar.setCurrentRow(0)
        self.sidebar.currentRowChanged.connect(self._on_category_change)
        body_layout.addWidget(self.sidebar)

        # ★ Middle: settings content area (scrollable) — เต็มพื้นที่
        self.content_scroll = QScrollArea()
        self.content_scroll.setWidgetResizable(True)
        self.content_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.content_stack = _ContentStack()
        self.content_stack.setMinimumWidth(640)
        self.content_stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.content_scroll.setWidget(self.content_stack)
        body_layout.addWidget(self.content_scroll, 1)

        outer.addWidget(body, 1)

        # ★ Build all sections (แต่ละ section = page ใน stack)
        self._sections = {}
        self._build_platforms_section()
        self._build_tts_section()
        self._build_theme_section()
        self._build_translate_section()
        self._build_playroom_section()
        self._build_canvas_section()
        self._build_obs_ws_section()
        self._build_notifications_section()
        self._build_ng_section()
        self._build_replace_section()
        self._build_block_section()
        self._build_secret_code_section()
        self._build_overlay_plus_section()
        self._build_twitch_bot_section()
        # ★ _build_announce_section() ถอดออกจาก UI แล้ว — เครื่องมือ dev เท่านั้น
        #   (ยังใช้งานได้ผ่าน announce_sender.py แยกต่างหาก ไม่ควรให้ end user เห็นในนี้)
        self._build_supporters_section()
        self._build_about_section()

        # ★ Show first section
        self._show_section("platforms")

        # ★ Bottom bar (ปุ่มปิดอย่างเดียว — auto-save ทำงาน live)
        bottom = QFrame()
        self._bottom_bar = bottom
        bottom.setFixedHeight(50)
        bottom.setStyleSheet(
            f"background-color: {theme.COLOR_CARD}; border-top: 1px solid {theme.COLOR_BORDER};"
        )
        bottom_layout = QHBoxLayout(bottom)
        bottom_layout.setContentsMargins(20, 0, 20, 0)
        # ★ auto-save hint
        hint = QLabel("✓ บันทึกอัตโนมัติทุกครั้งที่เปลี่ยนแปลง")
        hint.setStyleSheet("color: #10b981; font-size: 12px;")
        bottom_layout.addWidget(hint)
        bottom_layout.addStretch()
        btn_close = QPushButton("ปิด")
        btn_close.setFixedWidth(90)
        btn_close.clicked.connect(self._save)  # save ครั้งสุดท้าย + accept
        bottom_layout.addWidget(btn_close)
        outer.addWidget(bottom)

        # ★ wire auto-save: เชื่อมทุก widget ที่เปลี่ยนค่าได้ → _auto_save
        QTimer.singleShot(100, self._wire_auto_save)

    def _wire_auto_save(self):
        """เชื่อมทุก widget กับ _auto_save (หลัง build UI เสร็จ) — ใช้ getattr กัน crash"""
        # QLineEdit → editingFinished
        for attr in ['tw_channel', 'yt_id', 'ml_url', 'tt_user', 'kc_channel',
                      'at_apikey', 'at_host',
                      'obs_ws_host', 'obs_ws_password', 'ann_token', 'ann_url']:
            w = getattr(self, attr, None)
            if w and hasattr(w, 'editingFinished'):
                w.editingFinished.connect(self._auto_save)
        # QCheckBox → stateChanged
        for attr in ['auto_reconnect', 'tw_auto', 'yt_auto', 'ml_auto', 'tt_auto', 'kc_auto',
                      'tw_show', 'yt_show', 'ml_show', 'tt_show', 'kc_show',
                      'playroom_enabled', 'mode_translate', 'mode_multilang',
                      'at_enabled', 'ml_enabled', 'mv_enabled',
                      'read_author', 'read_message', 'read_own_web',
                      'obs_ws_enabled']:
            w = getattr(self, attr, None)
            if w and hasattr(w, 'stateChanged'):
                w.stateChanged.connect(lambda _: self._auto_save())
        # QSlider / QSpinBox → valueChanged
        for attr in ['tts_volume', 'tts_rate', 'max_msg_length', 'obs_ws_port']:
            w = getattr(self, attr, None)
            if w and hasattr(w, 'valueChanged'):
                w.valueChanged.connect(lambda _: self._auto_save())
        # QComboBox → currentIndexChanged
        for attr in ['at_provider', 'edge_voice_combo', 'omnivoice_voice_combo']:
            w = getattr(self, attr, None)
            if w and hasattr(w, 'currentIndexChanged'):
                w.currentIndexChanged.connect(lambda _: self._auto_save())
        # QRadioButton → toggled (language checkboxes + translate modes + TTS read)
        for checks in [getattr(self, '_lang_checks', {}), getattr(self, '_ml_lang_checks', {})]:
            if isinstance(checks, dict):
                for cb in checks.values():
                    if hasattr(cb, 'stateChanged'):
                        cb.stateChanged.connect(lambda _: self._auto_save())
        # TTS read radio buttons + engine radios
        for attr in ['tts_read_both', 'tts_read_message_only', 'tts_engine_edge', 'tts_engine_omni']:
            rb = getattr(self, attr, None)
            if rb and hasattr(rb, 'toggled'):
                rb.toggled.connect(lambda _: self._auto_save())

    def _on_category_change(self, row):
        if row < 0:
            return
        item = self.sidebar.item(row)
        key = item.data(Qt.UserRole)
        self._show_section(key)

    def _show_section(self, key):
        """แสดง section ที่เลือก (QStackedWidget — แสดงทีละอัน)
        ★ sync sidebar highlight ด้วย (กัน sidebar ค้างที่หน้าเดิม)
        """
        widget = self._sections.get(key)
        if widget:
            self.content_stack.setCurrentWidget(widget)
            # ★ บังคับความสูง content_stack ให้พอดีกับหน้าที่เพิ่งสลับไป (ไม่งั้น
            #   ค้างความสูงของหน้าที่ยาวที่สุดที่เคยโชว์ — ดู _resize_stack_to_current ทำไม)
            self._resize_stack_to_current()
            # ★ sync sidebar — หา row ที่ตรงกับ key แล้วไฮไลท์
            for i in range(self.sidebar.count()):
                item = self.sidebar.item(i)
                if item and item.data(Qt.UserRole) == key:
                    self.sidebar.setCurrentRow(i)
                    break

    def _apply_sidebar_theme_qss(self):
        """สไตล์ sidebar หมวดหมู่ (ซ้ายสุดของ Settings) ตามธีมปัจจุบัน — เรียกซ้ำได้เวลาเปลี่ยนธีมสด"""
        self.sidebar.setStyleSheet(f"""
            QListWidget {{
                background-color: {theme.COLOR_BG_DARK};
                border: none;
                border-right: 1px solid {theme.COLOR_BORDER};
                outline: none;
                padding: 8px 0;
            }}
            QListWidget::item {{
                padding: 12px 16px;
                color: {theme.COLOR_TEXT_DIM};
                border: none;
            }}
            QListWidget::item:selected {{
                background-color: {theme.COLOR_CARD};
                color: {theme.COLOR_ACCENT};
                border-left: 3px solid {theme.COLOR_ACCENT};
            }}
            QListWidget::item:hover {{
                background-color: {theme.COLOR_CARD};
            }}
        """)

    def _apply_dialog_chrome_theme(self):
        """re-apply สีของ chrome ทั้งหมดของ Settings dialog เอง (sidebar + หัวข้อทุก section +
        bottom bar) — เรียกตอนเปิด dialog และตอนคลิกเปลี่ยนธีมสด (ไม่งั้นค้างสีเดิมเพราะ
        setStyleSheet() ระดับ widget ไม่ได้ผูกกับ global QSS ของ apply_theme())
        """
        self._apply_sidebar_theme_qss()
        for lbl in getattr(self, '_section_heading_labels', []):
            lbl.setStyleSheet(f"font-size: 20px; font-weight: 700; color: {theme.COLOR_HEADING};")
        if hasattr(self, '_bottom_bar'):
            self._bottom_bar.setStyleSheet(
                f"background-color: {theme.COLOR_CARD}; border-top: 1px solid {theme.COLOR_BORDER};"
            )

    def _add_section(self, key, title, description=""):
        """สร้าง section ใหม่ + เพิ่มเข้า QStackedWidget

        ★ มี addStretch() ท้าย layout → content อยู่ด้านบนเสมอ (ดันลงด้วย stretch)
        ★ content builders ใช้ insertWidget/insertLayout(count-1) เพื่อแทรกก่อน stretch
        ★ padding 24px รอบด้าน → content ไม่ชิดกรอบ
        """
        widget = QWidget()
        wlayout = QVBoxLayout(widget)
        wlayout.setContentsMargins(24, 20, 24, 20)
        wlayout.setSpacing(10)
        if title:
            lbl = QLabel(title)
            lbl.setObjectName("Heading")
            lbl.setStyleSheet(f"font-size: 20px; font-weight: 700; color: {theme.COLOR_HEADING};")
            if not hasattr(self, '_section_heading_labels'):
                self._section_heading_labels = []
            self._section_heading_labels.append(lbl)
            wlayout.addWidget(lbl)
        if description:
            desc = QLabel(description)
            desc.setObjectName("Dim")
            desc.setWordWrap(True)
            wlayout.addWidget(desc)
        wlayout.addStretch()  # ★ stretch ท้าย → ดัน content ขึ้นบน
        self.content_stack.addWidget(widget)
        self._sections[key] = widget
        self._current_section_layout = wlayout
        return widget

    def _add_row(self, label, widget):
        """เพิ่ม row (label + widget) เข้า section ปัจจุบัน (แทรกก่อน stretch)"""
        row = QHBoxLayout()
        lbl = QLabel(label)
        lbl.setMinimumWidth(140)
        lbl.setStyleSheet("color: #e5e7eb;")
        row.addWidget(lbl)
        row.addWidget(widget, 1)
        self._current_section_layout.insertLayout(
            self._current_section_layout.count() - 1, row
        )

    # ════════════════════════════════════════════════════════════
    # Section builders
    # ════════════════════════════════════════════════════════════
    def _build_platforms_section(self):
        w = self._add_section("platforms", "🔌 แพลตฟอร์ม", "ตั้งค่า channel/URL สำหรับแต่ละแพลตฟอร์ม")
        # ★ helper: สร้าง row แพลตฟอร์ม (label ด้านบน / บรรทัดล่าง = channel + auto + show)
        def _platform_row(label, channel_widget, auto_cb_name, show_cb_name):
            # ★ vertical layout: label ด้านบน, row ของ input/checkbox ด้านล่าง
            card = QVBoxLayout()
            card.setSpacing(4)
            name_lbl = QLabel(label)
            name_lbl.setStyleSheet("color: #e5e7eb; font-weight: 600;")
            card.addWidget(name_lbl)
            row = QHBoxLayout()
            row.setSpacing(4)
            row.addWidget(channel_widget, 1)
            auto_cb = QCheckBox("เชื่อมอัตโนมัติ")
            auto_cb.setToolTip(f"เชื่อมต่อ {label} อัตโนมัติตอนเปิดโปรแกรม")
            row.addWidget(auto_cb)
            setattr(self, auto_cb_name, auto_cb)
            show_cb = QCheckBox("แสดง")
            show_cb.setToolTip(f"แสดง {label} ในหน้าหลัก (เลิกติ๊กเพื่อซ่อน)")
            row.addWidget(show_cb)
            setattr(self, show_cb_name, show_cb)
            card.addLayout(row)
            self._current_section_layout.insertLayout(self._current_section_layout.count() - 1, card)

        # Twitch
        self.tw_channel = QLineEdit()
        self.tw_channel.setPlaceholderText("เช่น men9ch")
        _platform_row("Twitch:", self.tw_channel, 'tw_auto', 'tw_show')

        # ★ Twitch OAuth (ส่งแชท + Bot) — ปุ่มเชื่อมต่อ + สถานะ
        tw_oauth_card = QFrame()
        tw_oauth_card.setStyleSheet(
            "QFrame { background: #1e293b; border: 1px solid #334155; border-radius: 8px; }"
        )
        tw_oauth_layout = QVBoxLayout(tw_oauth_card)
        tw_oauth_layout.setContentsMargins(12, 10, 12, 10)
        tw_oauth_layout.setSpacing(6)

        tw_oauth_title = QLabel("🔐 ล็อกอิน Twitch (ส่งแชท + Bot)")
        tw_oauth_title.setStyleSheet("font-weight: 600; color: #f59e0b; border: none;")
        tw_oauth_layout.addWidget(tw_oauth_title)

        self.tw_oauth_status = QLabel("⏳ กำลังตรวจสอบ...")
        self.tw_oauth_status.setWordWrap(True)
        self.tw_oauth_status.setStyleSheet("color: #94a3b8; font-size: 12px; border: none;")
        tw_oauth_layout.addWidget(self.tw_oauth_status)

        tw_oauth_btn_row = QHBoxLayout()
        self.btn_tw_connect = QPushButton("🔗 เชื่อมต่อ Twitch")
        self.btn_tw_connect.setCursor(Qt.PointingHandCursor)
        self.btn_tw_connect.setStyleSheet(
            "QPushButton { background: #334155; color: #e2e8f0; border: 1px solid #475569; "
            "border-radius: 6px; padding: 6px 14px; font-weight: 600; }"
            "QPushButton:hover { background: #475569; }"
        )
        self.btn_tw_disconnect = QPushButton("⚪ ยกเลิกการเชื่อมต่อ")
        self.btn_tw_disconnect.setCursor(Qt.PointingHandCursor)
        self.btn_tw_disconnect.setStyleSheet(
            "QPushButton { background: #dc2626; color: white; border: none; "
            "border-radius: 6px; padding: 6px 14px; font-weight: 600; }"
            "QPushButton:hover { background: #b91c1c; }"
        )
        # ★ ปุ่ม "ตั้งค่า Chat Bot" — แสดงหลังเชื่อมต่อสำเร็จ → เด้งไป section Chat Bot
        self.btn_tw_bot_settings = QPushButton("🤖 ตั้งค่า Chat Bot")
        self.btn_tw_bot_settings.setCursor(Qt.PointingHandCursor)
        self.btn_tw_bot_settings.setStyleSheet(
            "QPushButton { background: #7c3aed; color: white; border: none; "
            "border-radius: 6px; padding: 6px 14px; font-weight: 600; }"
            "QPushButton:hover { background: #6d28d9; }"
        )
        self.btn_tw_bot_settings.setVisible(False)  # ★ ซ่อนจนกว่าจะเชื่อมต่อสำเร็จ
        self.btn_tw_bot_settings.clicked.connect(self._goto_chat_bot_section)

        tw_oauth_btn_row.addWidget(self.btn_tw_connect)
        tw_oauth_btn_row.addWidget(self.btn_tw_disconnect)
        tw_oauth_btn_row.addWidget(self.btn_tw_bot_settings)
        tw_oauth_btn_row.addStretch()
        tw_oauth_layout.addLayout(tw_oauth_btn_row)
        # ★ เชื่อมปุ่ม
        self.btn_tw_connect.clicked.connect(self._on_tw_connect_clicked)
        self.btn_tw_disconnect.clicked.connect(self._on_tw_disconnect_clicked)

        self._current_section_layout.insertWidget(
            self._current_section_layout.count() - 1, tw_oauth_card
        )

        # YouTube
        self.yt_id = QLineEdit()
        self.yt_id.setPlaceholderText("@ชื่อช่อง เช่น @MeN9CH (แนะนำ — หาห้อง live เอง) หรือ URL ห้อง")
        _platform_row("YouTube:", self.yt_id, 'yt_auto', 'yt_show')

        # MyLive
        self.ml_url = QLineEdit()
        self.ml_url.setPlaceholderText("https://mylive.in.th/streams/XXXXX")
        _platform_row("MyLive:", self.ml_url, 'ml_auto', 'ml_show')
        # KICK (★ ไว้ก่อน TikTok — รองรับส่งแชท + bot)
        self.kc_channel = QLineEdit()
        self.kc_channel.setPlaceholderText("channel")
        _platform_row("KICK:", self.kc_channel, 'kc_auto', 'kc_show')

        # ★ KICK OAuth (ส่งแชท + Bot + แก้ชื่อห้อง) — ปุ่มเชื่อมต่อ + สถานะ
        kc_oauth_card = QFrame()
        kc_oauth_card.setStyleSheet(
            "QFrame { background: #1e293b; border: 1px solid #334155; border-radius: 8px; }"
        )
        kc_oauth_layout = QVBoxLayout(kc_oauth_card)
        kc_oauth_layout.setContentsMargins(12, 10, 12, 10)
        kc_oauth_layout.setSpacing(6)

        kc_oauth_title = QLabel("🔐 ล็อกอิน KICK (ส่งแชท + Bot + แก้ชื่อห้อง)")
        kc_oauth_title.setStyleSheet("font-weight: 600; color: #53fc18; border: none;")
        kc_oauth_layout.addWidget(kc_oauth_title)

        self.kc_oauth_status = QLabel("⏳ กำลังตรวจสอบ...")
        self.kc_oauth_status.setWordWrap(True)
        self.kc_oauth_status.setStyleSheet("color: #94a3b8; font-size: 12px; border: none;")
        kc_oauth_layout.addWidget(self.kc_oauth_status)

        kc_oauth_btn_row = QHBoxLayout()
        self.btn_kc_connect = QPushButton("🔗 เชื่อมต่อ KICK")
        self.btn_kc_connect.setCursor(Qt.PointingHandCursor)
        self.btn_kc_connect.setStyleSheet(
            "QPushButton { background: #334155; color: #e2e8f0; border: 1px solid #475569; "
            "border-radius: 6px; padding: 6px 14px; font-weight: 600; }"
            "QPushButton:hover { background: #475569; }"
        )
        self.btn_kc_disconnect = QPushButton("⚪ ยกเลิกการเชื่อมต่อ")
        self.btn_kc_disconnect.setCursor(Qt.PointingHandCursor)
        self.btn_kc_disconnect.setStyleSheet(
            "QPushButton { background: #dc2626; color: white; border: none; "
            "border-radius: 6px; padding: 6px 14px; font-weight: 600; }"
            "QPushButton:hover { background: #b91c1c; }"
        )
        self.btn_kc_bot_settings = QPushButton("🤖 ตั้งค่า Chat Bot")
        self.btn_kc_bot_settings.setCursor(Qt.PointingHandCursor)
        self.btn_kc_bot_settings.setStyleSheet(
            "QPushButton { background: #7c3aed; color: white; border: none; "
            "border-radius: 6px; padding: 6px 14px; font-weight: 600; }"
            "QPushButton:hover { background: #6d28d9; }"
        )
        self.btn_kc_bot_settings.setVisible(False)
        self.btn_kc_bot_settings.clicked.connect(self._goto_chat_bot_section)

        kc_oauth_btn_row.addWidget(self.btn_kc_connect)
        kc_oauth_btn_row.addWidget(self.btn_kc_disconnect)
        kc_oauth_btn_row.addWidget(self.btn_kc_bot_settings)
        kc_oauth_btn_row.addStretch()
        kc_oauth_layout.addLayout(kc_oauth_btn_row)
        # ★ เชื่อมปุ่ม
        self.btn_kc_connect.clicked.connect(self._on_kc_connect_clicked)
        self.btn_kc_disconnect.clicked.connect(self._on_kc_disconnect_clicked)

        self._current_section_layout.insertWidget(
            self._current_section_layout.count() - 1, kc_oauth_card
        )

        # TikTok (★ ไว้ล่างสุด — อ่านอย่างเดียว)
        self.tt_user = QLineEdit()
        self.tt_user.setPlaceholderText("username")
        _platform_row("TikTok:", self.tt_user, 'tt_auto', 'tt_show')
        # Auto-reconnect
        self.auto_reconnect = QCheckBox("เชื่อมต่อใหม่อัตโนมัติเมื่อหลุด")
        self._current_section_layout.insertWidget(self._current_section_layout.count() - 1,  self.auto_reconnect
        )

    def _build_tts_section(self):
        self._add_section("tts", "🔊 Text to Speech", "เลือกเสียงหลัก — เลือกเสร็จเปลี่ยนที่ sidebar ได้")
        layout = self._current_section_layout
        ci = lambda: layout.count() - 1

        # ═══ Engine selector ═══
        engine_label = QLabel("เสียงหลัก (Base Engine):")
        engine_label.setStyleSheet("font-weight: 600; color: #f59e0b;")
        layout.insertWidget(ci(), engine_label)

        # ★ radio: edge-tts (online) | OmniVoice (offline RTX)
        self.tts_engine_edge = QRadioButton("🌐 edge-tts (ออนไลน์ — เสียง Azure คมชัด)")
        self.tts_engine_omni = QRadioButton("🎤 OmniVoice (ออฟไลน์ — ไม่ต้องเน็ต, ต้องมี RTX)")
        # ★ check OmniVoice available (ผ่าน plugin loader → fallback import ตรง)
        omni_available = False
        try:
            from engine_plugin_loader import is_plugin_available
            omni_available = is_plugin_available("omnivoice")
        except Exception:
            pass
        if not omni_available:
            try:
                from omnivoice_engine import is_omnivoice_available
                omni_available = is_omnivoice_available()
            except Exception:
                pass
        if not omni_available:
            # ★ Lite build ไม่มี OmniVoice → ซ่อนปุ่มเลย (ไม่แสดง disabled)
            self.tts_engine_omni.setVisible(False)
        engine_group = QButtonGroup(self)
        engine_group.addButton(self.tts_engine_edge)
        engine_group.addButton(self.tts_engine_omni)
        layout.insertWidget(ci(), self.tts_engine_edge)
        layout.insertWidget(ci(), self.tts_engine_omni)

        # ═══ edge-tts voice selector ═══
        self._edge_voice_widget = QWidget()
        ev_layout = QVBoxLayout(self._edge_voice_widget)
        ev_layout.setContentsMargins(20, 4, 0, 4)
        ev_layout.setSpacing(4)
        ev_layout.addWidget(QLabel("เสียง edge-tts:"))
        self.edge_voice_combo = QComboBox()
        self.edge_voice_combo.addItem("Premwadee หญิง (th-TH-PremwadeeNeural)", "premwadee")
        self.edge_voice_combo.addItem("Niwat ชาย (th-TH-NiwatNeural)", "niwat")
        ev_layout.addWidget(self.edge_voice_combo)
        layout.insertWidget(ci(), self._edge_voice_widget)

        # ═══ OmniVoice voice selector ═══
        self._omni_voice_widget = QWidget()
        ov_layout = QVBoxLayout(self._omni_voice_widget)
        ov_layout.setContentsMargins(20, 4, 0, 4)
        ov_layout.setSpacing(4)
        ov_layout.addWidget(QLabel("เสียง OmniVoice (design — ไม่ต้องมี ref audio):"))
        self.omnivoice_voice_combo = QComboBox()
        self.omnivoice_voice_combo.addItem("หญิง (female)", "female")
        self.omnivoice_voice_combo.addItem("ชาย (male)", "male")
        ov_layout.addWidget(self.omnivoice_voice_combo)
        layout.insertWidget(ci(), self._omni_voice_widget)

        # ★ engine radio → show/hide voice selectors
        self.tts_engine_edge.toggled.connect(self._on_tts_engine_change)
        self.tts_engine_omni.toggled.connect(self._on_tts_engine_change)

        # Volume
        self.tts_volume = QSlider(Qt.Horizontal)
        self.tts_volume.setRange(0, 100)
        self._add_row("Volume:", self.tts_volume)
        # Rate (★ ซ่อน — ไม่ได้ใช้ แต่เก็บไว้กัน _collect_values crash)
        self.tts_rate = QSlider(Qt.Horizontal)
        self.tts_rate.setRange(-50, 50)
        self.tts_rate.setVisible(False)
        # ★ Read group (radio buttons) — "การอ่าน"
        read_label = QLabel("การอ่าน:")
        read_label.setStyleSheet("font-weight: 600; color: #f59e0b;")
        layout.insertWidget(ci(), read_label)
        self.tts_read_both = QRadioButton("อ่านชื่อและข้อความ")
        layout.insertWidget(ci(), self.tts_read_both)
        self.tts_read_message_only = QRadioButton("อ่านแต่ข้อความเท่านั้น")
        # ★ default = อ่านแต่ข้อความเท่านั้น (อ่านชื่อเป็นตัวเลือก — ตามที่ user สั่ง)
        self.tts_read_message_only.setChecked(True)
        layout.insertWidget(ci(), self.tts_read_message_only)
        self.tts_read_group = QButtonGroup(self)
        self.tts_read_group.addButton(self.tts_read_both)
        self.tts_read_group.addButton(self.tts_read_message_only)
        # ★ อ่านข้อความที่เราพิมพ์บนหน้าเว็บ — default เปิด (ปิดได้จากตรงนี้)
        from PySide6.QtWidgets import QCheckBox as _QCB2
        self.read_own_web = _QCB2("อ่านข้อความที่เราพิมพ์บนหน้าเว็บเอง (Twitch / KICK)")
        self.read_own_web.setToolTip(
            "☑ = ข้อความที่เราพิมพ์บนหน้าเว็บ Twitch/KICK จะถูกอ่านออกเสียงเหมือนข้อความปกติ | "
            "☐ = แสดงใน Live Chat แต่ไม่อ่าน | "
            "(ไม่เกี่ยวกับคำตอบของ Chat Bot — อันนั้นไม่อ่านเสมอ)"
        )
        layout.insertWidget(ci(), self.read_own_web)
        # ★ backing variables (driven from radio buttons in _collect_values)
        self.read_author = QCheckBox()
        self.read_message = QCheckBox()
        self.read_author.setVisible(False)
        self.read_message.setVisible(False)

        # ═══ Viewer interaction commands ([x2]/[p1]/[v50] chat prefix) ═══
        from PySide6.QtWidgets import QCheckBox as _QCB, QDoubleSpinBox as _QDSB
        vc_label = QLabel("คำสั่งผู้ชม (Viewer Commands):")
        vc_label.setStyleSheet("font-weight: 600; color: #f59e0b;")
        layout.insertWidget(ci(), vc_label)
        self.viewer_cmd_enabled = _QCB("เปิดใช้คำสั่ง [x2]/[p1]/[v50] หน้าข้อความ (เร่งเสียง/เปลี่ยน pitch/เปลี่ยน volume)")
        layout.insertWidget(ci(), self.viewer_cmd_enabled)
        # ★ cooldown spinner
        cd_row = QHBoxLayout()
        cd_row.setContentsMargins(20, 0, 0, 0)
        cd_label = QLabel("Cooldown ต่อ user (วินาที):")
        cd_label.setStyleSheet("color: #9ca3af; font-size: 12px;")
        cd_row.addWidget(cd_label)
        self.viewer_cmd_cooldown = _QDSB()
        self.viewer_cmd_cooldown.setRange(0.0, 60.0)
        self.viewer_cmd_cooldown.setSingleStep(0.5)
        self.viewer_cmd_cooldown.setDecimals(1)
        self.viewer_cmd_cooldown.setValue(5.0)
        self.viewer_cmd_cooldown.setFixedWidth(110)
        self.viewer_cmd_cooldown.setStyleSheet("font-size: 14px;")
        cd_row.addWidget(self.viewer_cmd_cooldown)
        cd_row.addStretch()
        layout.insertLayout(ci(), cd_row)
        # ★ help text
        vc_help = QLabel(
            "รูปแบบ: [x2] = เร็ว 2x, [x0.5] = ช้าลงครึ่ง, [p1] = สูง +5Hz, [v50] = เบาลงครึ่ง\n"
            "ตัวอย่าง: [x2][p1]สวัสดี = เร็ว 2x + สูงขึ้น"
        )
        vc_help.setStyleSheet("color: #6b7280; font-size: 11px; padding: 4px 20px;")
        vc_help.setWordWrap(True)
        layout.insertWidget(ci(), vc_help)

        # ═══ OmniVoice short word policy ═══
        # ★ ซ่อนทั้งหมดใน Lite build (ไม่มี OmniVoice)
        self._omni_skip_widgets = []
        omni_skip_label = QLabel("คำสั้น OmniVoice:")
        omni_skip_label.setStyleSheet("font-weight: 600; color: #f59e0b;")
        layout.insertWidget(ci(), omni_skip_label)
        self._omni_skip_widgets.append(omni_skip_label)
        omni_skip_btn = QPushButton("✅ จัดการคำสั้น OmniVoice (min length + whitelist)")
        omni_skip_btn.setToolTip("คำเดียวสั้นกว่า X ตัว → ไม่อ่าน (ยกเว้นคำใน whitelist)")
        omni_skip_btn.clicked.connect(self._open_omni_skip)
        layout.insertWidget(ci(), omni_skip_btn)
        self._omni_skip_widgets.append(omni_skip_btn)
        # ★ Lite build: ซ่อนถ้าไม่มี OmniVoice
        try:
            from omnivoice_engine import is_omnivoice_available
            if not is_omnivoice_available():
                for w in self._omni_skip_widgets:
                    w.setVisible(False)
        except Exception:
            for w in self._omni_skip_widgets:
                w.setVisible(False)

    def _open_omni_skip(self):
        """เปิด OmniVoice Word Skip editor"""
        from ui.dialogs.omni_skip import OmniSkipDialog
        dlg = OmniSkipDialog(self.parent_app)
        dlg.settings_changed.connect(self._auto_save)
        dlg.exec()

    def _on_tts_engine_change(self):
        """engine radio เปลี่ยน → show/hide voice selectors"""
        is_edge = self.tts_engine_edge.isChecked()
        self._edge_voice_widget.setVisible(is_edge)
        self._omni_voice_widget.setVisible(not is_edge)

    def _build_theme_section(self):
        """เลือกธีมสีของโปรแกรม (ui/theme.py THEMES) — คลิก thumbnail เปลี่ยนทันที

        ★ ไม่ผ่าน auto-save ปกติ — คลิกแล้ว save + apply_theme() สดเลย (ไม่ต้องรอ
          ปิด dialog หรือรีสตาร์ทถึงจะเห็นผล — ส่วนที่เหลือ ~ hardcode ไม่กี่จุด
          ค่อยรีสตาร์ทเอาให้ครบ)
        """
        self._add_section(
            "app_theme", "🎨 Theme",
            "คลิกเลือกธีมที่ต้องการ — เปลี่ยนทันที (บางจุดเล็กๆ ต้องรีสตาร์ทโปรแกรมเพื่อผลเต็มรูปแบบ)",
        )
        from ui.theme import THEME_ORDER, THEME_LABELS, THEMES

        self._theme_thumbs = {}
        grid = QHBoxLayout()
        grid.setSpacing(14)
        for key in THEME_ORDER:
            pal = THEMES[key]
            thumb = QFrame()
            thumb.setFixedSize(150, 108)
            thumb.setCursor(Qt.PointingHandCursor)

            tlayout = QVBoxLayout(thumb)
            tlayout.setContentsMargins(8, 8, 8, 8)
            tlayout.setSpacing(6)

            # ★ mini "หน้าต่างจำลอง" — sidebar mini + card mini + accent dot
            preview = QFrame()
            preview.setFixedHeight(52)
            preview.setStyleSheet("background: transparent; border: none;")
            players = QHBoxLayout(preview)
            players.setContentsMargins(0, 0, 0, 0)
            players.setSpacing(4)
            sidebar_mini = QFrame()
            sidebar_mini.setFixedWidth(14)
            sidebar_mini.setStyleSheet(
                f"background-color: {pal['BG_DARK']}; border-radius: 3px; border: none;"
            )
            players.addWidget(sidebar_mini)
            card_mini = QFrame()
            card_mini.setStyleSheet(
                f"background-color: {pal['CARD']}; border-radius: 3px; border: none;"
            )
            card_layout = QVBoxLayout(card_mini)
            card_layout.setContentsMargins(6, 6, 6, 6)
            accent_dot = QLabel()
            accent_dot.setFixedSize(14, 14)
            accent_dot.setStyleSheet(
                f"background-color: {pal['ACCENT']}; border-radius: 7px; border: none;"
            )
            card_layout.addWidget(accent_dot)
            card_layout.addStretch()
            players.addWidget(card_mini, 1)
            tlayout.addWidget(preview)

            name_lbl = QLabel(THEME_LABELS.get(key, key))
            name_lbl.setAlignment(Qt.AlignCenter)
            name_lbl.setWordWrap(True)
            name_lbl.setStyleSheet(
                f"color: {pal['TEXT']}; font-size: 11px; font-weight: 600; "
                "border: none; background: transparent;"
            )
            tlayout.addWidget(name_lbl)

            thumb.mousePressEvent = lambda e, k=key: self._on_theme_thumb_clicked(k)
            self._theme_thumbs[key] = thumb
            grid.addWidget(thumb)
        grid.addStretch()
        self._current_section_layout.insertLayout(
            self._current_section_layout.count() - 1, grid
        )
        self._refresh_theme_thumb_selection()

    def _refresh_theme_thumb_selection(self):
        """ไฮไลต์ thumbnail ของธีมที่ใช้อยู่ตอนนี้ด้วยขอบสี accent หนาขึ้น"""
        from ui.theme import THEMES
        current = getattr(self.settings, 'ui_theme', 'default') if self.settings else 'default'
        for key, thumb in getattr(self, '_theme_thumbs', {}).items():
            pal = THEMES[key]
            border = (
                f"3px solid {pal['ACCENT']}" if key == current
                else f"2px solid {pal['BORDER']}"
            )
            thumb.setStyleSheet(
                f"QFrame {{ background-color: {pal['BG']}; border-radius: 10px; border: {border}; }}"
            )

    def _on_theme_thumb_clicked(self, key):
        """คลิก thumbnail ธีม → save + apply สดทันที (ไม่ต้องปิด Settings/รีสตาร์ท)"""
        if self.settings:
            self.settings.ui_theme = key
            try:
                from settings import save_settings
                save_settings(self.settings)
            except Exception:
                pass
        try:
            from PySide6.QtWidgets import QApplication
            from ui.theme import apply_theme
            app = QApplication.instance()
            if app is not None:
                apply_theme(app, key)
        except Exception:
            pass
        # ★ apply_theme() ข้างบนแก้แค่ global QSS ของแอป — chrome ของ Settings dialog เอง
        #   (sidebar/หัวข้อ/bottom bar) ตั้งด้วย setStyleSheet() ตรงๆ ต้อง re-apply เองด้วย
        #   ไม่งั้นค้างสีเดิมทั้งที่กำลังมองอยู่ตรงนี้เป๊ะๆ
        self._apply_dialog_chrome_theme()
        self._refresh_theme_thumb_selection()
        # ★ topbar TTS toggle ก็ตั้งสีตรงๆ ผ่าน setStyleSheet() เหมือนกัน (ไม่ผ่าน global QSS)
        #   ต้อง refresh สดด้วย ไม่งั้นค้างสีจนกว่าจะกด toggle TTS เอง
        try:
            if self.parent_app is not None and hasattr(self.parent_app, 'topbar'):
                self.parent_app.topbar._update_tts_button()
        except Exception:
            pass
        self.settings_changed.emit()

    def _build_translate_section(self):
        self._add_section("translate", "🌐 การแปลภาษา + หลายภาษา", "เลือกโหมด: แปลเป็นไทย หรือ อ่านหลายภาษา")
        from PySide6.QtWidgets import QRadioButton, QButtonGroup, QGridLayout

        # ★ โหมดเลือก (radio buttons)
        mode_label = QLabel("เลือกโหมด:")
        mode_label.setStyleSheet("font-weight: 600; color: #f59e0b;")
        self._current_section_layout.insertWidget(self._current_section_layout.count() - 1,  mode_label
        )
        self.mode_multilang = QRadioButton("🎤 อ่านหลายภาษา (ตรวจจับภาษา → เลือกเสียงที่เหมาะสม)")
        self.mode_translate = QRadioButton("🌐 แปลเป็นไทย (แปลข้อความต่างประเทศ → TTS อ่านไทย)")
        self.mode_off = QRadioButton("❌ ปิด (อ่านไทยอย่างเดียว)")
        self.mode_off.setChecked(True)

        mode_group = QButtonGroup(self)
        mode_group.addButton(self.mode_multilang)
        mode_group.addButton(self.mode_translate)
        mode_group.addButton(self.mode_off)

        self.mode_multilang.toggled.connect(self._on_translate_mode_change)
        self.mode_translate.toggled.connect(self._on_translate_mode_change)

        self._current_section_layout.insertWidget(self._current_section_layout.count() - 1,  self.mode_multilang
        )
        self._current_section_layout.insertWidget(self._current_section_layout.count() - 1,  self.mode_translate
        )
        self._current_section_layout.insertWidget(self._current_section_layout.count() - 1,  self.mode_off
        )

        # ★ Translate settings (ซ่อนจนกว่าจะเลือกโหมดแปล)
        self._translate_settings = QWidget()
        ts_layout = QVBoxLayout(self._translate_settings)
        ts_layout.setContentsMargins(20, 0, 0, 0)
        ts_layout.setSpacing(6)

        # provider
        provider_row = QHBoxLayout()
        provider_row.addWidget(QLabel("ผู้ให้บริการ:"))
        self.at_provider = QComboBox()
        self.at_provider.addItems(["google", "deepl", "deepseek"])
        self.at_provider.currentTextChanged.connect(self._on_translate_provider_change)
        provider_row.addWidget(self.at_provider, 1)
        ts_layout.addLayout(provider_row)
        # ★ API key + Host — เก็บเป็น row container เพื่อซ่อนได้ตอน provider=google
        self._at_apikey_row = QWidget()
        ak_layout = QVBoxLayout(self._at_apikey_row)
        ak_layout.setContentsMargins(0, 0, 0, 0)
        ak_layout.setSpacing(2)
        ak_layout.addWidget(QLabel("API Key:"))
        self.at_apikey = QLineEdit()
        self.at_apikey.setPlaceholderText("API Key (DeepL/DeepSeek)")
        self.at_apikey.setEchoMode(QLineEdit.Password)
        ak_layout.addWidget(self.at_apikey)
        ts_layout.addWidget(self._at_apikey_row)
        # host
        self._at_host_row = QWidget()
        host_layout = QVBoxLayout(self._at_host_row)
        host_layout.setContentsMargins(0, 0, 0, 0)
        host_layout.setSpacing(2)
        host_layout.addWidget(QLabel("Host:"))
        self.at_host = QLineEdit()
        self.at_host.setPlaceholderText("Host (ว่าง = default)")
        host_layout.addWidget(self.at_host)
        ts_layout.addWidget(self._at_host_row)
        # language grid (2 columns)
        ts_layout.addWidget(QLabel("ภาษาที่จะแปล:"))
        self._lang_checks = {}
        all_langs = [
            ("en", "🇬🇧 อังกฤษ"), ("ja", "🇯🇵 ญี่ปุ่น"), ("ko", "🇰🇷 เกาหลี"),
            ("zh", "🇨🇳 จีน"), ("zh-TW", "🇹🇼 ไต้หวัน"), ("fr", "🇫🇷 ฝรั่งเศส"),
            ("vi", "🇻🇳 เวียดนาม"), ("id", "🇮🇩 อินโด"), ("es", "🇪🇸 สเปน"),
            ("de", "🇩🇪 เยอรมัน"), ("ru", "🇷🇺 รัสเซีย"),
        ]
        lang_grid = QGridLayout()
        lang_grid.setSpacing(4)
        for i, (code, name) in enumerate(all_langs):
            cb = QCheckBox(name)
            self._lang_checks[code] = cb
            lang_grid.addWidget(cb, i // 2, i % 2)
        ts_layout.addLayout(lang_grid)
        self._current_section_layout.insertWidget(self._current_section_layout.count() - 1,  self._translate_settings
        )

        # ★ Multilang settings (ซ่อนจนกว่าจะเลือกโหมด multilang)
        self._multilang_settings = QWidget()
        ml_layout = QVBoxLayout(self._multilang_settings)
        ml_layout.setContentsMargins(20, 0, 0, 0)
        ml_label = QLabel("ภาษาที่จะอ่าน (เลือกเสียงตามภาษา):")
        ml_layout.addWidget(ml_label)
        self._ml_lang_checks = {}
        ml_grid = QGridLayout()
        ml_grid.setSpacing(4)
        ml_langs = [
            ("en", "🇬🇧 อังกฤษ"), ("ja", "🇯🇵 ญี่ปุ่น"), ("ko", "🇰🇷 เกาหลี"),
            ("zh", "🇨🇳 จีน"), ("zh-TW", "🇹🇼 ไต้หวัน"), ("fr", "🇫🇷 ฝรั่งเศส"),
            ("vi", "🇻🇳 เวียดนาม"), ("id", "🇮🇩 อินโด"),
        ]
        for i, (code, name) in enumerate(ml_langs):
            cb = QCheckBox(name)
            self._ml_lang_checks[code] = cb
            ml_grid.addWidget(cb, i // 2, i % 2)
        ml_layout.addLayout(ml_grid)
        self._current_section_layout.insertWidget(self._current_section_layout.count() - 1,  self._multilang_settings
        )

        # ★ Mixed Voice — ลบแล้ว (อ่านหลายภาษาครอบคลุมอยู่แล้ว)
        # initial state
        self._translate_settings.setVisible(False)
        self._multilang_settings.setVisible(False)
        self._on_translate_provider_change("google")

    def _on_translate_mode_change(self):
        """แสดง/ซ่อน settings ตามโหมดที่เลือก"""
        is_translate = self.mode_translate.isChecked()
        is_multilang = self.mode_multilang.isChecked()
        self._translate_settings.setVisible(is_translate)
        self._multilang_settings.setVisible(is_multilang)

    def _on_translate_provider_change(self, provider):
        """ซ่อน/แสดง API Key + Host ตาม provider"""
        show = provider != "google"
        if hasattr(self, '_at_apikey_row'):
            self._at_apikey_row.setVisible(show)
        if hasattr(self, '_at_host_row'):
            self._at_host_row.setVisible(show)

    def _add_row_widget(self, label, widget):
        """เพิ่ม row (label + widget) และคืน container widget (สำหรับ show/hide)"""
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(label)
        lbl.setMinimumWidth(140)
        row.addWidget(lbl)
        row.addWidget(widget, 1)
        self._current_section_layout.insertWidget(self._current_section_layout.count() - 1,  container
        )
        return container

    def _build_playroom_section(self):
        self._add_section("playroom", "🎮 Playroom", "ตั้งค่า Playroom triggers + clips")
        # ★ enable/disable playroom (อยู่บนสุด)
        self.playroom_enabled = QCheckBox("เปิดใช้งาน Playroom")
        self._current_section_layout.insertWidget(self._current_section_layout.count() - 1,  self.playroom_enabled
        )

        # ★ triggers list container (เก็บ trigger rows ทั้งหมด)
        self._playroom_triggers_container = QWidget()
        pt_layout = QVBoxLayout(self._playroom_triggers_container)
        pt_layout.setContentsMargins(0, 8, 0, 0)
        pt_layout.setSpacing(6)
        self._playroom_triggers_layout = pt_layout
        self._current_section_layout.insertWidget(
            self._current_section_layout.count() - 1, self._playroom_triggers_container
        )

        # ★ populate trigger rows จาก settings.playroom_triggers
        self._playroom_trigger_rows = []
        triggers = getattr(self.settings, 'playroom_triggers', []) or []
        for trig in triggers:
            self._add_playroom_trigger_row(trig)

        # ★ "เพิ่ม Trigger" button
        btn_add = QPushButton("➕ เพิ่ม Trigger")
        btn_add.setObjectName("Primary")
        btn_add.setMinimumHeight(32)
        btn_add.clicked.connect(lambda: self._add_playroom_trigger_row(
            {'code': '#new', 'clips': [], 'daily_limit': 3}))
        self._current_section_layout.insertWidget(
            self._current_section_layout.count() - 1, btn_add
        )

    def _add_playroom_trigger_row(self, trig):
        """เพิ่ม collapsible row สำหรับ trigger หนึ่ง (inline ใน settings)"""
        if not isinstance(trig, dict):
            trig = {}
        code = trig.get('code', '')
        clips = trig.get('clips', []) or []
        daily_limit = trig.get('daily_limit', 3)

        # ★ container card
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background: #131726; border: 1px solid #2a2f45; border-radius: 6px; }"
        )
        cl = QVBoxLayout(card)
        cl.setContentsMargins(10, 6, 10, 6)
        cl.setSpacing(4)

        # ★ header row: [^/V toggle] Code: [entry] Limit/day: [spin] [❌]
        #   ทั้ง header คลิกได้ (ไม่ใช่แค่ปุ่ม toggle) → คลิกพื้นที่ว่างก็หุบ/ขยายได้
        header = QHBoxLayout()
        header.setSpacing(6)
        toggle_btn = QPushButton("⌃")  # ★ ⌃ = ชี้ขึ้น (ซ่อน) ตอนขยายอยู่
        toggle_btn.setFixedSize(24, 24)
        toggle_btn.setCursor(Qt.PointingHandCursor)
        toggle_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; color: #9ca3af; font-size: 16px; font-weight: 700; padding: 0; }"
            "QPushButton:hover { color: #f59e0b; }"
        )
        header.addWidget(toggle_btn)

        code_entry = QLineEdit(code)
        code_entry.setStyleSheet("font-family: monospace; font-weight: 600;")
        code_entry.setPlaceholderText("#code")
        header.addWidget(QLabel("Code:"))
        header.addWidget(code_entry, 1)

        header.addWidget(QLabel("Limit/day:"))
        limit_spin = QSpinBox()
        limit_spin.setRange(0, 100)
        limit_spin.setValue(daily_limit)
        limit_spin.valueChanged.connect(lambda _: self._auto_save())
        header.addWidget(limit_spin)

        btn_del = QPushButton("❌")
        btn_del.setFixedSize(30, 26)
        btn_del.setToolTip("ลบ trigger นี้")
        btn_del.setStyleSheet(
            "QPushButton { background: transparent; border: none; font-size: 14px; padding: 0px; }"
            "QPushButton:hover { background: #ef4444; border-radius: 4px; color: white; }"
        )
        btn_del.setCursor(Qt.PointingHandCursor)
        def _del_trigger(_, c=card, le=code_entry):
            from PySide6.QtWidgets import QMessageBox
            code = le.text().strip() or "trigger นี้"
            reply = QMessageBox.question(
                c, "ยืนยันการลบ",
                f'ต้องการลบ trigger "{code}" ใช่ไหม?\n'
                f"clips ทั้งหมดใน trigger นี้จะถูกลบด้วย",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
            )
            if reply == QMessageBox.Yes:
                c.deleteLater()
        btn_del.clicked.connect(_del_trigger)
        header.addWidget(btn_del)
        cl.addLayout(header)

        # ★ details container (clips list) — toggle โดยปุ่ม ▼/▶
        details = QWidget()
        dl = QVBoxLayout(details)
        dl.setContentsMargins(28, 4, 4, 4)
        dl.setSpacing(4)

        from PySide6.QtWidgets import QHeaderView
        clips_label = QLabel(f"📦 Clips ({len(clips)}):")
        clips_label.setStyleSheet("color: #9ca3af; font-size: 12px;")
        dl.addWidget(clips_label)

        clips_table = QTableWidget(0, 3)
        clips_table.setHorizontalHeaderLabels(["ชื่อ", "ไฟล์", "น้ำหนัก (%)"])
        clips_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        clips_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        clips_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        clips_table.setColumnWidth(2, 80)
        clips_table.verticalHeader().setVisible(False)
        clips_table.verticalHeader().setDefaultSectionSize(24)   # ★ แถวเตี้ยกระชับ
        clips_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        dl.addWidget(clips_table)

        def _fit_clips_table(tbl):
            """★ สูงพอดีตามแถว: แถวน้อย = กระชับ, แถวเยอะ = แสดงสูงสุด 4 แถวแล้ว scroll
            + grip มุมขวาล่างสำหรับลากยืดเพิ่มเองได้"""
            from PySide6.QtWidgets import QSizePolicy, QSizeGrip
            rows = tbl.rowCount()
            visible = min(rows, 4) if rows else 0
            h = 30 + (24 * visible) + 4   # header 30 + แถวละ 24 + margin
            tbl.setMinimumHeight(h if rows else 34)
            tbl.setMaximumHeight(16777215)   # ไม่จำกัดบน — ลาก grip ยืดได้อิสระ
            tbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        # ★ grip ลากยืดมุมขวาล่างของตาราง
        from PySide6.QtWidgets import QSizeGrip
        _clip_grip = QSizeGrip(clips_table)
        clips_table.setCornerWidget(_clip_grip)

        for clip in clips:
            if isinstance(clip, dict):
                r = clips_table.rowCount()
                clips_table.insertRow(r)
                clips_table.setItem(r, 0, QTableWidgetItem(clip.get('name', '')))
                clips_table.setItem(r, 1, QTableWidgetItem(clip.get('path', '')))
                clips_table.setItem(r, 2, QTableWidgetItem(str(clip.get('weight', 50))))
        _fit_clips_table(clips_table)
        # เก็บ ref ให้ add/browse/delete เรียก fit หลังแถวเปลี่ยน
        clips_table._fit = _fit_clips_table

        clip_btns = QHBoxLayout()
        btn_add_clip = QPushButton("➕ เพิ่ม Clip")
        btn_add_clip.clicked.connect(lambda _, t=clips_table: self._add_playroom_clip_row(t))
        clip_btns.addWidget(btn_add_clip)
        btn_browse = QPushButton("📁 เลือกไฟล์")
        btn_browse.clicked.connect(lambda _, t=clips_table: self._browse_playroom_clip(t))
        clip_btns.addWidget(btn_browse)
        btn_del_clip = QPushButton("🗑 ลบ Clip ที่เลือก")
        btn_del_clip.clicked.connect(lambda _, t=clips_table: self._delete_playroom_clip(t))
        clip_btns.addWidget(btn_del_clip)
        dl.addLayout(clip_btns)

        cl.addWidget(details)

        # ★ toggle visibility — ⌃ (ชี้ขึ้น=ซ่อน) ตอนขยาย / ⌄ (ชี้ลง=ขยาย) ตอนซ่อน
        def _toggle():
            visible = not details.isVisible()
            details.setVisible(visible)
            details.setMaximumHeight(16777215 if visible else 0)
            toggle_btn.setText("⌃" if visible else "⌄")
        toggle_btn.clicked.connect(_toggle)
        # ★ คลิกพื้นที่ว่างใน card (พื้นที่ที่ไม่ใช่ child widget) → toggle ด้วย
        #   ใช้ QObject event filter แยก (เพราะ QFrame.eventFilter เป็น method ไม่ใช่ attribute)
        from PySide6.QtCore import QObject, QEvent
        class _CardClickFilter(QObject):
            def eventFilter(self, obj, event):
                if event.type() == QEvent.MouseButtonPress and obj is card:
                    _toggle()
                    return True
                return False
        _filter = _CardClickFilter(card)
        card.installEventFilter(_filter)
        details.setVisible(False)  # ★ collapsed by default (หุบไว้)
        details.setMaximumHeight(0)  # ★ บังคับ height=0 กัน layout ค้าง
        toggle_btn.setText("⌄")  # ลูกศรชี้ลง = หุบ

        # ★ store refs for save
        card.code_entry = code_entry
        card.limit_spin = limit_spin
        card.clips_table = clips_table
        card._orig_trigger = trig

        self._playroom_trigger_rows.append(card)
        self._playroom_triggers_layout.addWidget(card)

    def _add_playroom_clip_row(self, table):
        """เพิ่มแถว clip ว่าง"""
        r = table.rowCount()
        table.insertRow(r)
        table.setItem(r, 0, QTableWidgetItem(''))
        table.setItem(r, 1, QTableWidgetItem(''))
        table.setItem(r, 2, QTableWidgetItem('50'))
        if getattr(table, '_fit', None): table._fit(table)

    def _browse_playroom_clip(self, table):
        """เลือกไฟล์ clip (วิดีโอ/รูป)"""
        from PySide6.QtWidgets import QFileDialog, QTableWidgetItem
        files, _ = QFileDialog.getOpenFileNames(
            self, "เลือกไฟล์ Clip",
            "", "Media Files (*.mp4 *.webm *.mov *.png *.jpg *.jpeg *.gif *.webp);;All Files (*.*)"
        )
        if not files:
            return
        import os
        for fpath in files:
            name = os.path.splitext(os.path.basename(fpath))[0]
            r = table.rowCount()
            table.insertRow(r)
            table.setItem(r, 0, QTableWidgetItem(name))
            table.setItem(r, 1, QTableWidgetItem(fpath))
            table.setItem(r, 2, QTableWidgetItem('50'))
        if getattr(table, '_fit', None): table._fit(table)

    def _delete_playroom_clip(self, table):
        """ลบ clip ที่เลือก"""
        rows = set()
        for item in table.selectedItems():
            rows.add(item.row())
        for r in sorted(rows, reverse=True):
            table.removeRow(r)
        if getattr(table, '_fit', None): table._fit(table)

    def _build_canvas_section(self):
        self._add_section("canvas", "🎨 Canvas Composer", "ตั้งค่า Overlay Composer")
        self.composer_port = QSpinBox()
        self.composer_port.setRange(8000, 9999)
        self.composer_port.setValue(8801)
        self._add_row("Port:", self.composer_port)
        btn_open = QPushButton("🌐 เปิด Composer")
        btn_open.setObjectName("Primary")
        btn_open.clicked.connect(lambda: self.parent_app._open_composer() if hasattr(self.parent_app, '_open_composer') else None)
        self._current_section_layout.insertWidget(self._current_section_layout.count() - 1,  btn_open
        )

    def _build_obs_ws_section(self):
        """🔌 OBS WebSocket — auto-refresh browser sources ตอนเปิดโปรแกรม

        แก้ปัญหา: เปิด OBS ก่อน Broadcast Playroom → browser source cache หน้าเก่า → overlay ไม่แสดง
        เมื่อเปิดใช้งาน → เชื่อม OBS WS แล้ว refresh browser sources ที่ URL ชี้ overlay ของเรา
        ★ ปิดใช้งาน → ไม่เริ่ม watcher, ไม่ขึ้นสถานะ "รอ OBS" ใน status bar
        """
        self._add_section(
            "obs_ws", "🔌 OBS WebSocket",
            "Refresh browser source อัตโนมัติตอนเปิดโปรแกรม "
            "(แก้ปัญหา OBS เปิดก่อน → overlay ค้างหน้าเก่า)"
        )
        # ★ เปิด/ปิดใช้งาน — ถ้าปิด จะไม่เชื่อมต่อ OBS เลย (ไม่ขึ้นสถานะค้าง)
        self.obs_ws_enabled = QCheckBox("เปิดใช้งาน OBS WebSocket")
        self.obs_ws_enabled.setStyleSheet("font-size: 14px; font-weight: 600;")
        self._current_section_layout.insertWidget(
            self._current_section_layout.count() - 1, self.obs_ws_enabled
        )
        self._obs_status_label = QLabel("⏸️ ปิดใช้งาน")
        self._obs_status_label.setStyleSheet("font-size: 12px; color: #6b7280; margin-bottom: 8px;")
        self._current_section_layout.insertWidget(
            self._current_section_layout.count() - 1, self._obs_status_label
        )
        # ★ toggle: อัพเดท label ทันที
        self.obs_ws_enabled.toggled.connect(self._on_obs_ws_toggled)
        # ★ สถานะสด — โพลจาก OBSWatcher จริงทุก 2 วิ (กัน "งงว่าเชื่อมอยู่รึเปล่า"
        #   เพราะช่องรหัสว่างก็ต่อได้เมื่อ OBS ไม่ได้เปิดล็อครหัส)
        self._obs_live_timer = QTimer(self)
        self._obs_live_timer.timeout.connect(self._poll_obs_ws_live_status)
        self._obs_live_timer.start(2000)
        # ★ Host
        self.obs_ws_host = QLineEdit()
        self.obs_ws_host.setPlaceholderText("localhost")
        self._add_row("Host:", self.obs_ws_host)
        # ★ Port
        self.obs_ws_port = QSpinBox()
        self.obs_ws_port.setRange(1, 65535)
        self.obs_ws_port.setValue(4455)
        self._add_row("Port:", self.obs_ws_port)
        # ★ Password
        self.obs_ws_password = QLineEdit()
        self.obs_ws_password.setEchoMode(QLineEdit.Password)
        self.obs_ws_password.setPlaceholderText("(ว่างถ้า OBS ไม่ได้ตั้งรหัส)")
        self._add_row("Password:", self.obs_ws_password)
        # ★ ปุ่มทดสอบการเชื่อมต่อ
        btn_test = QPushButton("🔌 ทดสอบการเชื่อมต่อ")
        btn_test.setObjectName("Primary")
        btn_test.clicked.connect(self._test_obs_ws)
        self._current_section_layout.insertWidget(
            self._current_section_layout.count() - 1, btn_test
        )
        # ★ hint
        hint = QLabel(
            "💡 เปิด OBS → Tools → WebSocket Server Settings → Enable "
            "(default port 4455)\n"
            "🔑 รหัสผ่าน: OBS ใหม่ ๆ สุ่มรหัสให้เสมอ → คัดลอกจากหน้าต่างนั้น (Connect Information) มาใส่\n"
            "    ปล่อยว่างได้ เฉพาะเมื่อคุณปิด 'Enable Authentication' ใน OBS เอง\n"
            "★ ใช้ร่วมกับ OBS Browser Source ที่ URL ชี้ overlay/composer ของเรา\n"
            "★ ปิดใช้งานถ้าไม่ได้ใช้ OBS — จะได้ไม่ขึ้นสถานะรอเชื่อมต่อ"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #9ca3af; font-size: 12px; margin-top: 8px;")
        self._current_section_layout.insertWidget(
            self._current_section_layout.count() - 1, hint
        )
        # ★ ปุ่มวิธีเชื่อม — เปิดหน้าเว็บสอน
        # ★ import webbrowser แบบ local (จุดอื่นในไฟล์ก็ใช้แบบนี้) — เดิมลืม import
        #   ทำให้กดแล้ว NameError โดน Qt กลืนเงียบ ๆ = ปุ่มกดไม่ได้
        import webbrowser
        btn_guide = QPushButton("📖 วิธีเชื่อม WebSocket")
        btn_guide.setObjectName("Primary")
        btn_guide.clicked.connect(lambda: webbrowser.open(
            "https://men9ch.com/broadcastplayroom-websocket-setting/"))
        self._current_section_layout.insertWidget(
            self._current_section_layout.count() - 1, btn_guide
        )

    def _on_obs_ws_toggled(self, checked):
        """★ อัพเดท status label ทันทีเมื่อ toggle (โพลสดจะตามมาเช็คอีกทีทุก 2 วิ)"""
        if hasattr(self, '_obs_status_label') and self._obs_status_label:
            if checked:
                self._obs_status_label.setText("🔌 จะเริ่มเชื่อมต่อ OBS เมื่อบันทึกการตั้งค่า")
                self._obs_status_label.setStyleSheet(
                    "font-size: 12px; color: #06b6d4; margin-bottom: 8px;")
            else:
                self._obs_status_label.setText("⏸️ ปิดใช้งาน")
                self._obs_status_label.setStyleSheet(
                    "font-size: 12px; color: #6b7280; margin-bottom: 8px;")

    def _poll_obs_ws_live_status(self):
        """★ สถานะเชื่อมต่อ OBS WebSocket จริงจาก watcher (ไม่ใช่แค่ checkbox)

        ลำดับ: ปิดอยู่ → ติ๊กแล้วยังไม่บันทึก → เชื่อมสำเร็จแล้ว → กำลังลอง/ยังไม่ติด
        ★ อธิบายรหัสว่างให้ชัด: OBS ที่ปิด 'Enable Authentication' ต่อได้เลยไม่ต้องมีรหัส
        """
        lbl = getattr(self, '_obs_status_label', None)
        if lbl is None:
            return
        try:
            chk = self.obs_ws_enabled.isChecked() if hasattr(self, 'obs_ws_enabled') else False
            saved = bool(getattr(self.settings, 'obs_ws_enabled', False))
            watcher = getattr(self.parent_app, '_obs_watcher', None) if self.parent_app else None
            pw_empty = True
            if hasattr(self, 'obs_ws_password'):
                pw_empty = not self.obs_ws_password.text().strip()

            if not chk:
                text, color = "⏸️ ปิดใช้งาน", "#6b7280"
            elif not saved:
                text, color = "🔌 จะเริ่มเชื่อมต่อ OBS เมื่อบันทึกการตั้งค่า", "#06b6d4"
            elif watcher is not None and watcher.is_connected:
                text = "🟢 เชื่อมต่อ OBS สำเร็จ — auto-refresh browser sources ทำงานแล้ว"
                if pw_empty:
                    text += "\n• ช่องรหัสว่างได้: OBS ของคุณไม่ได้เปิดล็อครหัส (Enable Authentication ปิดอยู่)"
                color = "#10b981"
            else:
                text = "🟡 ยังเชื่อมไม่ติด — กำลังลองทุก 5 วิ (เปิด OBS และ WebSocket Server ไว้)"
                text += "\n• ดูสาเหตุล่าสุดที่แถบสถานะล่างของโปรแกรม เช่น 'รหัสผ่านผิด' = OBS ตั้งรหัสไว้ ต้องคัดลอกมาใส่"
                color = "#f59e0b"
            lbl.setText(text)
            lbl.setStyleSheet(f"font-size: 12px; color: {color}; margin-bottom: 8px;")
        except Exception:
            pass

    def _test_obs_ws(self):
        """ทดสอบการเชื่อมต่อ OBS WebSocket (รันใน background กัน UI ค้าง)"""
        # ★ อ่านค่าล่าสุดจาก form ก่อน (กัน user พิมพ์ยังไม่ save)
        host = self.obs_ws_host.text().strip() or 'localhost'
        port = int(self.obs_ws_port.value())
        pw = self.obs_ws_password.text()

        btn = self.sender()
        if btn:
            btn.setEnabled(False)
            btn.setText("⏳ กำลังทดสอบ...")

        # ★ ใช้ class-level Signal แทน QTimer.singleShot (กัน cross-thread issue)
        try:
            self._obs_test_sig.disconnect()
        except Exception:
            pass
        self._obs_test_sig.connect(self._obs_test_done_slot)

        def _bg():
            try:
                from obs_refresh import test_connection
                ok, msg = test_connection(host=host, port=port, password=pw)
            except Exception as e:
                ok, msg = False, f"เกิดข้อผิดพลาด: {e}"
            icon = "✅" if ok else "❌"
            self._obs_test_sig.emit(f"{icon} {msg}", btn)

        import threading
        threading.Thread(target=_bg, name="ObsWsTest", daemon=True).start()

    def _obs_test_done_slot(self, message, btn):
        """slot ที่ทำงานใน main thread (รับจาก signal)"""
        from PySide6.QtWidgets import QMessageBox
        if btn:
            btn.setEnabled(True)
            btn.setText("🔌 ทดสอบเชื่อมต่อ")
        QMessageBox.information(self, "OBS WebSocket", message)

    def _build_notifications_section(self):
        self._add_section("notifications", "🔔 แจ้งเตือน", "เสียง + TTS สำหรับ events แยกตามแพลตฟอร์ม")
        # ★ platform groups — key prefix = attribute name (self.notif_<platform>_<event>)
        # (3 per row ในแต่ละ group, aligned to right via QGridLayout column stretch)
        platform_groups = [
            ("Twitch",  "twitch",  [("sub", "⭐ Sub"), ("resub", "🔁 Resub"), ("bits", "💎 Bits"),
                                    ("raid", "🚀 Raid"), ("follow", "❤️ Follow")]),
            ("YouTube", "youtube", [("superchat", "💎 SuperChat"), ("gift", "🎁 Gift"),
                                    ("membership", "🎖️ Membership"), ("sponsor", "🤝 Sponsor")]),
            ("TikTok",  "tiktok",  [("like", "👍 Like"), ("follow", "❤️ Follow"),
                                    ("share", "📢 Share"), ("gift", "🎁 Gift")]),
            ("MyLive",  "mylive",  [("gift", "🎁 Gift"), ("donate", "💰 Donate"),
                                    ("membership", "🎖️ Membership")]),
            ("KICK",    "kick",    [("subgift", "🎁 Subgift"), ("raid", "🚀 Raid"),
                                    ("donate", "💰 Donate")]),
        ]
        self.notif_checks = {}  # (platform, event) → QCheckBox
        for pname, plat_key, events in platform_groups:
            # ★ platform header
            header = QLabel(pname)
            header.setStyleSheet("color: #f59e0b; font-weight: 700; font-size: 14px; margin-top: 8px;")
            self._current_section_layout.insertWidget(
                self._current_section_layout.count() - 1, header
            )
            # ★ 3-column grid
            grid_container = QWidget()
            grid = QGridLayout(grid_container)
            grid.setContentsMargins(20, 0, 0, 4)
            grid.setHorizontalSpacing(12)
            grid.setVerticalSpacing(4)
            for i, (ev_key, ev_label) in enumerate(events):
                cb = QCheckBox(ev_label)
                # ★ attribute: self.notif_<platform>_<event>
                attr_name = f"notif_{plat_key}_{ev_key}"
                setattr(self, attr_name, cb)
                self.notif_checks[(plat_key, ev_key)] = cb
                # wire auto-save
                cb.stateChanged.connect(lambda _: self._auto_save())
                r, c = i // 3, i % 3
                grid.addWidget(cb, r, c)
            # ★ align grid ให้ checkboxes ชิดซ้าย (column สุดท้าย stretch)
            grid.setColumnStretch(2, 1)
            self._current_section_layout.insertWidget(
                self._current_section_layout.count() - 1, grid_container
            )

        # ★ Debug Mode — ทดสอบแจ้งเตือนทุกประเภท (dev mode เท่านั้น)
        import sys as _sys
        if not getattr(_sys, 'frozen', False):
            from PySide6.QtWidgets import QPushButton as _QPB
            debug_row = QHBoxLayout()
            debug_row.setContentsMargins(0, 12, 0, 0)
            debug_label = QLabel("🧪 Debug Mode:")
            debug_label.setStyleSheet("font-weight: 600; color: #f59e0b;")
            debug_row.addWidget(debug_label)
            debug_row.addStretch()
            btn_debug = _QPB("🔔 ทดสอบแจ้งเตือนทั้งหมด")
            btn_debug.setToolTip("ส่ง event ทุกประเภท เพื่อทดสอบว่าแจ้งเตือนขึ้นถูกต้องไหม")
            btn_debug.clicked.connect(self._test_all_notifications)
            debug_row.addWidget(btn_debug)
            self._current_section_layout.insertLayout(
                self._current_section_layout.count() - 1, debug_row
            )

    def _test_all_notifications(self):
        """ทดสอบแจ้งเตือนทุกประเภท — ส่ง fake events เข้าระบบ"""
        if not self.parent_app:
            return
        app = self.parent_app
        from chat_twitch import ChatMessage
        test_events = [
            ("sub", "TestUser", "sub"),
            ("resub", "TestUser", "resub"),
            ("bits", "TestUser", "bits"),
            ("raid", "TestUser", "raid"),
            ("follow", "TestUser", "follow"),
            ("superchat", "TestUser", "superchat"),
            ("gift", "TestUser", "gift"),
            ("membership", "TestUser", "membership"),
            ("donate", "TestUser", "donate"),
            ("like", "TestUser", "like"),
            ("share", "TestUser", "share"),
        ]
        import time
        for event_type, author, event in test_events:
            msg = ChatMessage(
                platform='test',
                author=author,
                text=f"[{event}] ทดสอบแจ้งเตือน",
                event=event_type,
            )
            msg.amount = 100 if event_type in ('bits', 'superchat', 'donate') else 0
            try:
                app._record_event(msg, 'test')
            except Exception as e:
                pass
            time.sleep(0.1)  # เว้นช่วงกัน event ชนกัน

    def _build_ng_section(self):
        self._add_section("ng", "🚫 NG Words", "คำต้องห้าม — ข้อความที่มีคำเหล่านี้จะไม่แสดงใน Live Chat และไม่ถูกอ่านด้วย TTS (พิมพ์แล้วกด Enter เพื่อเพิ่ม)")
        # ★ NG words (พิมพ์ + enter → ลงตาราง)
        ng_label = QLabel("🚫 คำต้องห้าม (พิมพ์แล้วกด Enter):")
        ng_label.setObjectName("Section")
        self._current_section_layout.insertWidget(self._current_section_layout.count() - 1,  ng_label
        )
        self.ng_input = QLineEdit()
        self.ng_input.setPlaceholderText("พิมพ์คำที่ต้องการห้าม แล้วกด Enter...")
        self.ng_input.returnPressed.connect(self._add_ng_word)
        self._current_section_layout.insertWidget(self._current_section_layout.count() - 1,  self.ng_input
        )
        # ★ NG word table (สวย + มีปุ่มลบ)
        from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
        self.ng_table = QTableWidget(0, 2)
        self.ng_table.setHorizontalHeaderLabels(["คำต้องห้าม", ""])
        self.ng_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.ng_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.ng_table.setColumnWidth(1, 40)
        self.ng_table.verticalHeader().setDefaultSectionSize(32)
        self.ng_table.verticalHeader().hide()
        self.ng_table.horizontalHeader().setFixedHeight(28)
        self.ng_table.setMinimumHeight(80)
        self.ng_table.setMaximumHeight(200)
        self.ng_table.setStyleSheet("""
            QTableWidget { background: transparent; border: 1px solid #2a2f45; border-radius: 4px; }
            QTableWidget::item { padding: 4px; }
            QHeaderView::section { background: #131726; color: #9ca3af; border: none; padding: 4px; font-size: 14px; }
        """)
        self._current_section_layout.insertWidget(self._current_section_layout.count() - 1,  self.ng_table
        )
        # load existing
        banned = getattr(self.settings, 'banned_words', []) or []
        for w in banned:
            self._add_ng_row(w)

    def _build_replace_section(self):
        """🔄 Replace — editor inline (table + 🔊 + โหลดจากคลัง + pagination + search)"""
        self._add_section("replace", "🔄 Replace", "คำแทนที่ — แก้ไข / ทดสอบเสียง / โหลดจากคลัง")
        layout = self._current_section_layout
        ci = lambda: layout.count() - 1
        from PySide6.QtWidgets import QTableWidget, QHeaderView

        # ═══ State ═══
        # ★ เก็บข้อมูลทั้งหมดใน list of dict (truth source) — table แสดงเฉพาะหน้าที่กรองแล้ว
        self._replace_data = []        # [{src, display, read}]
        self._replace_page = 0          # current page index (0-based)
        self._replace_page_size = 50    # 50 คำต่อหน้า
        self._replace_search = ""       # quick search text

        # ═══ Top bar: [📥 Import] [📤 Export] [⬇️ โหลดจากคลัง] [🔍 search] ... [count] ═══
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)
        btn_import = QPushButton("📥 Import")
        btn_import.setMinimumHeight(32)
        btn_import.setCursor(Qt.PointingHandCursor)
        btn_import.setStyleSheet(
            "QPushButton { background: #334155; color: #06b6d4; border: none; "
            "border-radius: 6px; padding: 4px 12px; font-size: 12px; font-weight: 600; }"
            "QPushButton:hover { background: #475569; }"
        )
        btn_import.clicked.connect(self._replace_import)
        top_bar.addWidget(btn_import)

        btn_export = QPushButton("📤 Export")
        btn_export.setMinimumHeight(32)
        btn_export.setCursor(Qt.PointingHandCursor)
        btn_export.setStyleSheet(
            "QPushButton { background: #334155; color: #10b981; border: none; "
            "border-radius: 6px; padding: 4px 12px; font-size: 12px; font-weight: 600; }"
            "QPushButton:hover { background: #475569; }"
        )
        btn_export.clicked.connect(self._replace_export)
        top_bar.addWidget(btn_export)

        btn_download = QPushButton("⬇️ โหลดจากคลัง")
        btn_download.clicked.connect(self._replace_download_from_wiki)
        top_bar.addWidget(btn_download)
        # ★ quick search
        self.replace_search = QLineEdit()
        self.replace_search.setPlaceholderText("🔍 ค้นหาคำศัพท์...")
        self.replace_search.setClearButtonEnabled(True)
        self.replace_search.textChanged.connect(self._replace_on_search)
        top_bar.addWidget(self.replace_search, 1)
        self.replace_count = QLabel("📋 0 คำ")
        self.replace_count.setStyleSheet("color: #9ca3af; font-size: 12px;")
        top_bar.addWidget(self.replace_count)
        top_container = QWidget()
        top_container.setLayout(top_bar)
        layout.insertWidget(ci(), top_container)

        # ═══ "➕ เพิ่มคำศัพท์" bar (กด → เปิด modal) ═══
        btn_add = QPushButton("➕ เพิ่มคำศัพท์ใหม่")
        btn_add.setObjectName("Primary")
        btn_add.setMinimumHeight(32)
        btn_add.setCursor(Qt.PointingHandCursor)
        btn_add.clicked.connect(self._replace_open_add_modal)
        layout.insertWidget(ci(), btn_add)

        # ═══ Table ═══
        self.replace_table = QTableWidget(0, 4)
        self.replace_table.setHorizontalHeaderLabels(["คำเดิม", "คำที่แสดง", "คำที่อ่าน TTS", ""])
        self.replace_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.replace_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.replace_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.replace_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.replace_table.horizontalHeader().resizeSection(3, 40)
        self.replace_table.verticalHeader().setDefaultSectionSize(38)
        self.replace_table.verticalHeader().setMinimumSectionSize(38)
        self.replace_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.replace_table.setStyleSheet("""
            QTableWidget { background-color: transparent; border: 1px solid #2a2f45; border-radius: 6px; gridline-color: #2a2f45; }
            QTableWidget::item { padding: 4px; }
            QHeaderView::section { background-color: #131726; color: #9ca3af; padding: 6px; border: none; border-bottom: 1px solid #2a2f45; font-weight: 600; }
        """)
        layout.insertWidget(ci(), self.replace_table, 1)

        # ═══ Pagination bar ═══
        pag_bar = QHBoxLayout()
        pag_bar.setSpacing(6)
        self.replace_btn_prev = QPushButton("‹ ก่อนหน้า")
        self.replace_btn_prev.clicked.connect(lambda: self._replace_goto_page(self._replace_page - 1))
        pag_bar.addWidget(self.replace_btn_prev)
        self.replace_page_label = QLabel("1 / 1")
        self.replace_page_label.setAlignment(Qt.AlignCenter)
        self.replace_page_label.setStyleSheet("color: #9ca3af; font-size: 12px;")
        pag_bar.addWidget(self.replace_page_label)
        self.replace_btn_next = QPushButton("ถัดไป ›")
        self.replace_btn_next.clicked.connect(lambda: self._replace_goto_page(self._replace_page + 1))
        pag_bar.addWidget(self.replace_btn_next)
        pag_container = QWidget()
        pag_container.setLayout(pag_bar)
        layout.insertWidget(ci(), pag_container)

        # ═══ Load data → render ═══
        words = getattr(self.settings, 'replace_words', {}) or {}
        for src, info in words.items():
            if isinstance(info, dict):
                self._replace_data.append({
                    'src': src, 'display': info.get('display', ''), 'read': info.get('read', '')})
            else:
                self._replace_data.append({'src': src, 'display': '', 'read': str(info)})
        self._replace_render()

    # ════════════════════════════════════════════════════════════
    # Replace — filtering + pagination
    # ════════════════════════════════════════════════════════════
    def _replace_filtered(self):
        """คืน list ของ entries ที่ผ่าน search filter (truth-source = _replace_data)"""
        q = self._replace_search.strip().lower()
        if not q:
            return list(self._replace_data)
        out = []
        for e in self._replace_data:
            if (q in e['src'].lower() or q in e.get('display', '').lower()
                    or q in e.get('read', '').lower()):
                out.append(e)
        return out

    def _replace_render(self):
        """render table ใหม่จาก _replace_data (filtered + paginated) + update count/page"""
        filtered = self._replace_filtered()
        total = len(filtered)
        # ★ clamp page
        max_page = max(0, (total - 1) // self._replace_page_size)
        if self._replace_page > max_page:
            self._replace_page = max_page
        if self._replace_page < 0:
            self._replace_page = 0
        start = self._replace_page * self._replace_page_size
        end = start + self._replace_page_size
        page_items = filtered[start:end]

        # ★ clear table (ลบ rows + cell widgets กัน leak)
        self.replace_table.setRowCount(0)
        for entry in page_items:
            self._replace_insert_table_row(entry['src'], entry.get('display', ''), entry.get('read', ''))

        # ★ update count + page label
        total_data = len(self._replace_data)
        if self._replace_search.strip():
            self.replace_count.setText(f"📋 {total}/{total_data} คำ (ค้นหา)")
        else:
            self.replace_count.setText(f"📋 {total_data} คำ")
        page_num = self._replace_page + 1
        total_pages = max_page + 1
        self.replace_page_label.setText(f"{page_num} / {total_pages}")
        self.replace_btn_prev.setEnabled(self._replace_page > 0)
        self.replace_btn_next.setEnabled(self._replace_page < max_page)

    def _replace_on_search(self, text):
        """search text เปลี่ยน → reset page 0 + render"""
        self._replace_search = text
        self._replace_page = 0
        self._replace_render()

    def _replace_goto_page(self, page):
        """เปลี่ยนหน้า"""
        self._replace_page = max(0, page)
        self._replace_render()

    def _replace_insert_table_row(self, src='', display='', read=''):
        """เพิ่ม row ใน table — QLineEdit editable + 🔊 + ❌ (visual เท่านั้น data อยู่ใน _replace_data)"""
        edit_style = "border: none; background: transparent; color: #e5e7eb; padding: 0px;"
        btn_style = "border: 1px solid #2a2f45; border-radius: 4px; background: #1a1f33; padding: 0px; font-size: 14px;"
        r = self.replace_table.rowCount()
        self.replace_table.insertRow(r)

        # ★ col 0: source + 🔊 — edit แล้ว sync กลับ _replace_data
        w0 = QWidget()
        l0 = QHBoxLayout(w0); l0.setContentsMargins(4, 2, 4, 2); l0.setSpacing(4)
        edit0 = QLineEdit(src); edit0.setStyleSheet(edit_style)
        edit0.editingFinished.connect(lambda e=edit0, s=src: self._replace_sync_edit(s, 'src', e.text()))
        l0.addWidget(edit0)
        btn0 = QPushButton("🔊"); btn0.setFixedSize(30, 26); btn0.setToolTip("ฟังคำเดิม")
        btn0.setStyleSheet(btn_style); btn0.setCursor(Qt.PointingHandCursor)
        btn0.clicked.connect(lambda _, e=edit0, b=btn0: self._replace_preview_tts(b, e.text()))
        l0.addWidget(btn0)
        self.replace_table.setCellWidget(r, 0, w0)
        w0._edit = edit0

        # ★ col 1: display
        w1 = QWidget()
        l1 = QHBoxLayout(w1); l1.setContentsMargins(4, 2, 4, 2)
        edit1 = QLineEdit(display); edit1.setStyleSheet(edit_style)
        edit1.editingFinished.connect(lambda e=edit1, s=src: self._replace_sync_edit(s, 'display', e.text()))
        l1.addWidget(edit1)
        self.replace_table.setCellWidget(r, 1, w1)
        w1._edit = edit1

        # ★ col 2: read + 🔊
        w2 = QWidget()
        l2 = QHBoxLayout(w2); l2.setContentsMargins(4, 2, 4, 2); l2.setSpacing(4)
        edit2 = QLineEdit(read); edit2.setStyleSheet(edit_style)
        edit2.editingFinished.connect(lambda e=edit2, s=src: self._replace_sync_edit(s, 'read', e.text()))
        l2.addWidget(edit2)
        btn2 = QPushButton("🔊"); btn2.setFixedSize(30, 26); btn2.setToolTip("ฟังคำที่อ่าน")
        btn2.setStyleSheet(btn_style); btn2.setCursor(Qt.PointingHandCursor)
        btn2.clicked.connect(lambda _, e=edit2, b=btn2: self._replace_preview_tts(b, e.text()))
        l2.addWidget(btn2)
        self.replace_table.setCellWidget(r, 2, w2)
        w2._edit = edit2

        # ★ col 3: ❌ delete
        w3 = QWidget()
        l3 = QHBoxLayout(w3); l3.setContentsMargins(2, 2, 2, 2)
        btn_del = QPushButton("❌"); btn_del.setFixedSize(30, 26); btn_del.setToolTip("ลบแถวนี้")
        btn_del.setCursor(Qt.PointingHandCursor)
        btn_del.setStyleSheet("border: none; background: transparent; font-size: 14px; padding: 0px;")
        def _del(s=src):
            reply = QMessageBox.question(
                self.replace_table, "ยืนยันการลบ",
                f'ต้องการลบ "{s}" ใช่ไหม?',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
            )
            if reply == QMessageBox.Yes:
                self._replace_data = [e for e in self._replace_data if e['src'] != s]
                self._replace_render()
                self._auto_save()
        btn_del.clicked.connect(_del)
        l3.addWidget(btn_del)
        self.replace_table.setCellWidget(r, 3, w3)

    def _replace_sync_edit(self, old_src, field, new_value):
        """sync การแก้ QLineEdit กลับไป _replace_data (edit in-place)"""
        new_value = new_value.strip()
        for e in self._replace_data:
            if e['src'] == old_src:
                if field == 'src' and new_value and new_value != old_src:
                    # ★ src เปลี่ยน → เช็ค duplicate
                    if any(x['src'] == new_value for x in self._replace_data if x is not e):
                        return
                    e['src'] = new_value
                else:
                    e[field] = new_value
                break
        self._auto_save()

    def _replace_preview_tts(self, btn, text):
        """เล่นเสียง TTS ของ text (กับ loading indicator กันกดรัว)"""
        if not text.strip():
            return
        if btn.text() == "⏳":
            return
        btn.setText("⏳"); btn.setEnabled(False)
        if self.parent_app and hasattr(self.parent_app, 'pipeline') and self.parent_app.pipeline:
            try:
                from chat_twitch import ChatMessage
                msg = ChatMessage(platform='test', author='ทดสอบ', text=text)
                self.parent_app.pipeline.enqueue(msg)
            except Exception as e:
                logger.error(f"TTS preview failed: {e}")
        QTimer.singleShot(3000, lambda: (btn.setText("🔊"), btn.setEnabled(True)))

    # ═══ Add modal ═══
    def _replace_open_add_modal(self):
        """เปิด modal เพิ่มคำศัพท์ใหม่ — 3 ช่อง + 🔊 + ยกเลิก/เพิ่ม"""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle("➕ เพิ่มคำศัพท์ใหม่")
        dlg.setMinimumWidth(440)
        vlay = QVBoxLayout(dlg)
        vlay.setSpacing(10)
        vlay.setContentsMargins(20, 18, 20, 16)
        edit_style = "QLineEdit { background: #0a0e1a; border: 1px solid #2a2f45; border-radius: 6px; padding: 8px 10px; color: #e5e7eb; }"
        btn_style = "border: 1px solid #2a2f45; border-radius: 4px; background: #1a1f33; padding: 0px; font-size: 16px;"

        # ★ คำเดิม + 🔊
        vlay.addWidget(QLabel("คำเดิม:"))
        src_row = QHBoxLayout(); src_row.setSpacing(6)
        src_entry = QLineEdit(); src_entry.setPlaceholderText("คำเดิม (ที่จะค้นหา)")
        src_entry.setStyleSheet(edit_style)
        src_row.addWidget(src_entry, 1)
        btn_src = QPushButton("🔊"); btn_src.setFixedSize(36, 32); btn_src.setToolTip("ฟังคำเดิม")
        btn_src.setStyleSheet(btn_style); btn_src.setCursor(Qt.PointingHandCursor)
        btn_src.clicked.connect(lambda _, e=src_entry, b=btn_src: self._replace_preview_tts(b, e.text()))
        src_row.addWidget(btn_src)
        vlay.addLayout(src_row)

        # ★ คำที่แสดง
        vlay.addWidget(QLabel("คำที่แสดง:"))
        disp_entry = QLineEdit(); disp_entry.setPlaceholderText("คำที่แสดง (ว่าง = ใช้คำเดิม)")
        disp_entry.setStyleSheet(edit_style)
        vlay.addWidget(disp_entry)

        # ★ คำที่อ่าน + 🔊
        vlay.addWidget(QLabel("คำที่อ่าน TTS:"))
        read_row = QHBoxLayout(); read_row.setSpacing(6)
        read_entry = QLineEdit(); read_entry.setPlaceholderText("คำที่อ่าน TTS (ว่าง = ใช้คำเดิม)")
        read_entry.setStyleSheet(edit_style)
        read_row.addWidget(read_entry, 1)
        btn_read = QPushButton("🔊"); btn_read.setFixedSize(36, 32); btn_read.setToolTip("ฟังคำที่อ่าน")
        btn_read.setStyleSheet(btn_style); btn_read.setCursor(Qt.PointingHandCursor)
        btn_read.clicked.connect(lambda _, e=read_entry, b=btn_read: self._replace_preview_tts(b, e.text()))
        read_row.addWidget(btn_read)
        vlay.addLayout(read_row)

        # ★ Enter ในช่องใด → เพิ่มเลย
        def _on_add():
            src = src_entry.text().strip()
            if not src:
                src_entry.setFocus(); return
            if any(e['src'] == src for e in self._replace_data):
                QMessageBox.warning(dlg, "ซ้ำ", f'มี "{src}" อยู่แล้ว')
                return
            self._replace_data.insert(0, {  # ★ ใหม่สุดอยู่บน
                'src': src,
                'display': disp_entry.text().strip(),
                'read': read_entry.text().strip(),
            })
            self._replace_page = 0  # ★ กลับหน้า 1 เพื่อให้เห็นคำใหม่
            self._replace_search = ""  # ★ clear search (กัน user ค้นหาอยู่ ไม่เห็นคำใหม่)
            if hasattr(self, 'replace_search'):
                self.replace_search.clear()
            self._replace_render()
            self._auto_save()
            dlg.accept()
        src_entry.returnPressed.connect(_on_add)
        disp_entry.returnPressed.connect(_on_add)
        read_entry.returnPressed.connect(_on_add)

        # ★ ปุ่มยกเลิก / เพิ่ม
        btn_box = QDialogButtonBox()
        btn_cancel = btn_box.addButton("ยกเลิก", QDialogButtonBox.RejectRole)
        btn_add = btn_box.addButton("เพิ่ม", QDialogButtonBox.AcceptRole)
        btn_add.setObjectName("Primary")
        btn_add.clicked.connect(_on_add)
        vlay.addWidget(btn_box)
        src_entry.setFocus()
        dlg.exec()

    def _replace_update_count(self):
        """backward-compat — render จัดการ count อยู่แล้ว"""
        self._replace_render()

    def _replace_export(self):
        """📤 Export คำแทนที่เป็น JSON"""
        import json, time
        from PySide6.QtWidgets import QFileDialog
        # ★ อ่านจาก settings (truth source)
        replace_words = {}
        if self.settings and hasattr(self.settings, 'replace_words'):
            replace_words = dict(self.settings.replace_words)
        if not replace_words:
            QMessageBox.information(self, "Export", "ยังไม่มีคำแทนที่จะส่งออก")
            return
        data = {
            "type": "replace",
            "version": 2,
            "replace_words": replace_words,
        }
        default_name = f"tts_replace_{time.strftime('%Y%m%d')}.json"
        path, _ = QFileDialog.getSaveFileName(
            self, "ส่งออกคำแทนที่", default_name, "JSON (*.json)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "✅ ส่งออกสำเร็จ",
                f"ส่งออก {len(replace_words)} คำ ไปยัง:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "❌ ส่งออกไม่ได้", str(e))

    def _replace_import(self):
        """📥 Import คำแทนที่จาก JSON — merge (ข้ามซ้ำ + เขียนทับ conflict)"""
        import json
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "นำเข้าคำแทนที่", "", "JSON (*.json)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "❌ อ่านไฟล์ไม่ได้", str(e))
            return

        incoming = data.get("replace_words", {})
        if not isinstance(incoming, dict) or not incoming:
            QMessageBox.warning(self, "ไฟล์ไม่ถูกต้อง", "ไม่พบ replace_words ในไฟล์")
            return

        # ★ merge เข้า settings
        if not self.settings:
            return
        existing = dict(self.settings.replace_words)
        n_new = 0
        n_overwrite = 0
        for src, entry in incoming.items():
            src = str(src).strip()
            if not src:
                continue
            if src in existing:
                n_overwrite += 1
            else:
                n_new += 1
            # ★ migrate format เก่า (string) → {display, read}
            if isinstance(entry, str):
                entry = {"display": entry, "read": entry}
            elif not isinstance(entry, dict):
                entry = {"display": str(entry), "read": str(entry)}
            existing[src] = entry

        self.settings.replace_words = existing
        self._auto_save()
        self._replace_refresh()

        QMessageBox.information(self, "✅ นำเข้าสำเร็จ",
            f"นำเข้า {n_new} คำใหม่\nเขียนทับ {n_overwrite} คำ\nรวม {len(incoming)} คำจากไฟล์")

    def _replace_download_from_wiki(self):
        """ดาวน์โหลด dictionary จากเว็บชุมชน + merge เข้า _replace_data"""
        reply = QMessageBox.question(
            self, "⬇️ โหลดจากคลัง",
            "จะดาวน์โหลด dictionary จากเว็บชุมชนและนำเข้าโปรแกรม\n\n"
            "คำใหม่จะเพิ่มเข้าไป (คำซ้ำจะข้าม)\n\nดำเนินการต่อ?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if reply != QMessageBox.Yes:
            return
        btn = self.sender()
        if btn:
            btn.setText("⏳ กำลังโหลด..."); btn.setEnabled(False)
        self._replace_dl_btn = btn
        from PySide6.QtCore import QThread, Signal as _Sig
        DICT_URL = "https://men9ch.com/wiki/ng-replace.php?pid=broadcast-playroom&download=1"
        class _DL(QThread):
            downloaded = _Sig(dict)
            failed = _Sig(str)
            def run(self):
                try:
                    import urllib.request as _urq, ssl, json as _json
                    ctx = ssl.create_default_context(); ctx.load_default_certs()
                    req = _urq.Request(DICT_URL, headers={
                        "User-Agent": "BroadcastPlayroom/2.0", "Accept": "application/json"})
                    with _urq.urlopen(req, timeout=10, context=ctx) as resp:
                        raw = resp.read().decode("utf-8")
                    parsed = _json.loads(raw)
                    incoming = parsed.get("replace_words", parsed) if isinstance(parsed, dict) else {}
                    if not isinstance(incoming, dict) or not incoming:
                        self.failed.emit("คลังศัพท์ว่าง"); return
                    self.downloaded.emit(incoming)
                except Exception as e:
                    self.failed.emit(str(e))
        self._replace_dl_thread = _DL(self)
        self._replace_dl_thread.downloaded.connect(self._replace_on_download_done)
        self._replace_dl_thread.failed.connect(self._replace_on_download_failed)
        self._replace_dl_thread.start()

    def _replace_on_download_failed(self, error):
        if getattr(self, '_replace_dl_btn', None):
            self._replace_dl_btn.setText("⬇️ โหลดจากคลัง"); self._replace_dl_btn.setEnabled(True)
        QMessageBox.critical(self, "ล้มเหลว", f"ดาวน์โหลดไม่ได้: {error}")

    def _replace_on_download_done(self, incoming):
        """merge dictionary ที่โหลดมาเข้า _replace_data"""
        from text_filter import TextFilter as _TF
        if getattr(self, '_replace_dl_btn', None):
            self._replace_dl_btn.setText("⬇️ โหลดจากคลัง"); self._replace_dl_btn.setEnabled(True)
        # ★ normalize → {src: {display, read}}
        normalized = {}
        for k, v in incoming.items():
            src = str(k).strip()
            if src:
                normalized[src] = _TF._normalize_entry(v)
        # ★ existing sources
        existing = set(e['src'] for e in self._replace_data)
        # ★ merge
        added = 0; conflicts = 0
        for src, entry in normalized.items():
            if src in existing:
                conflicts += 1
            else:
                self._replace_data.insert(0, {
                    'src': src,
                    'display': entry.get('display', ''),
                    'read': entry.get('read', ''),
                })
                existing.add(src); added += 1
        self._replace_page = 0
        self._replace_render()
        self._auto_save()
        msg = f"✅ เพิ่ม {added} คำใหม่"
        if conflicts:
            msg += f"\n⚠️ ข้าม {conflicts} คำซ้ำ (เก็บค่าเดิม)"
        QMessageBox.information(self, "⬇️ โหลดเสร็จ", msg)

    def _add_ng_word(self):
        """เพิ่มคำต้องห้ามจาก input → ตาราง + save + sync filter"""
        word = self.ng_input.text().strip()
        if not word:
            return
        self.ng_input.clear()
        # check duplicate
        for r in range(self.ng_table.rowCount()):
            item = self.ng_table.item(r, 0)
            if item and item.text().lower() == word.lower():
                return
        self._add_ng_row(word)
        # ★ save + sync filter ทันที (กัน NG word ไม่ทำงาน)
        self._auto_save()

    def _add_ng_row(self, word):
        """เพิ่ม row ใน NG table + ปุ่มลบ (icon แดง)"""
        from PySide6.QtWidgets import QPushButton
        r = self.ng_table.rowCount()
        self.ng_table.insertRow(r)
        self.ng_table.setItem(r, 0, QTableWidgetItem(word))
        # ★ ปุ่มลบ (❌ แดง + confirmation)
        btn_del = QPushButton("❌")
        btn_del.setFixedSize(30, 26)
        btn_del.setToolTip("ลบคำนี้")
        btn_del.setStyleSheet(
            "QPushButton { background: transparent; border: none; font-size: 14px; padding: 0px; }"
            "QPushButton:hover { background: #ef4444; border-radius: 4px; }"
        )
        btn_del.setCursor(Qt.PointingHandCursor)
        def _del_ng_row(_, r=r, tbl=self.ng_table):
            from PySide6.QtWidgets import QMessageBox
            item = tbl.item(r, 0)
            word = item.text().strip() if item else f"แถว {r+1}"
            reply = QMessageBox.question(
                tbl, "ยืนยันการลบ",
                f'ต้องการลบ "{word}" ใช่ไหม?',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
            )
            if reply == QMessageBox.Yes:
                tbl.removeRow(r)
                self._auto_save()  # ★ sync filter ทันที
        btn_del.clicked.connect(_del_ng_row)
        self.ng_table.setCellWidget(r, 1, btn_del)

    def _build_block_section(self):
        self._add_section("block", "🚫 Blocklist & Spam", "บล็อกผู้ใช้ + จัดการผู้ใช้ + จำกัดความยาวข้อความ")
        # ★ open user manager
        btn_users = QPushButton("👤 จัดการผู้ใช้ (User Manager)")
        btn_users.setObjectName("Primary")
        btn_users.setMinimumHeight(36)
        def _open_um():
            from ui.dialogs.user_manager import UserManagerDialog
            dlg = UserManagerDialog(self.parent_app)
            dlg.exec()
        btn_users.clicked.connect(_open_um)
        self._current_section_layout.insertWidget(self._current_section_layout.count() - 1,  btn_users
        )
        # ★ block user input (พิมพ์ชื่อ + Enter)
        block_label = QLabel("🚫 บล็อกผู้ใช้ (พิมพ์ชื่อแล้วกด Enter):")
        block_label.setObjectName("Section")
        self._current_section_layout.insertWidget(self._current_section_layout.count() - 1,  block_label
        )
        self.block_input = QLineEdit()
        self.block_input.setPlaceholderText("พิมพ์ชื่อผู้ใช้ที่ต้องการบล็อก แล้วกด Enter...")
        self.block_input.returnPressed.connect(self._add_blocked_user)
        self._current_section_layout.insertWidget(self._current_section_layout.count() - 1,  self.block_input
        )
        # ★ blocked users table (+ คอลัมน์ X ลบแถว)
        from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView, QComboBox
        self.block_table = QTableWidget(0, 3)
        self.block_table.setHorizontalHeaderLabels(["ชื่อผู้ใช้", "ประเภทการบล็อก", "ลบ"])
        self.block_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.block_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.block_table.setColumnWidth(1, 180)
        self.block_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.block_table.setColumnWidth(2, 46)
        self.block_table.setMinimumHeight(120)
        self.block_table.setStyleSheet("""
            QTableWidget { background: transparent; border: 1px solid #2a2f45; border-radius: 4px; }
            QTableWidget::item { padding: 4px; }
            QHeaderView::section { background: #131726; color: #9ca3af; border: none; padding: 6px; }
        """)
        self._current_section_layout.insertWidget(self._current_section_layout.count() - 1,  self.block_table
        )
        # ★ delete blocked user button
        btn_unblock = QPushButton("🗑 ลบที่เลือก")
        btn_unblock.clicked.connect(self._remove_blocked_user)
        self._current_section_layout.insertWidget(self._current_section_layout.count() - 1,  btn_unblock
        )
        # ★ load existing blocked users (รองรับทั้ง format เก่า str + ใหม่ dict)
        blocked = getattr(self.settings, 'blocked_users', []) or []
        for u in blocked:
            if isinstance(u, dict):
                name = u.get('name', '') or ''
                # hide_overlay=True → block_all, False → block_tts
                block_type = "block_all" if u.get('hide_overlay', True) else "block_tts"
            elif isinstance(u, str):
                name = u
                block_type = "block_all"
            else:
                continue
            if name:
                self._add_blocked_row(name, block_type)
        # ★ Spam settings (ย้ายมารวมกับ block) — ไว้ด้านล่าง
        spam_header = QLabel("🛡️ Spam — จำกัดความยาวข้อความ")
        spam_header.setStyleSheet("color: #f59e0b; font-weight: 700; font-size: 14px; margin-top: 16px; border-top: 1px solid #2a2f45; padding-top: 12px;")
        self._current_section_layout.insertWidget(self._current_section_layout.count() - 1,  spam_header
        )
        self.max_msg_length = QSpinBox()
        self.max_msg_length.setRange(0, 10000)
        self.max_msg_length.setValue(getattr(self.settings, 'max_msg_length', 500))
        self.max_msg_length.setSpecialValueText("ไม่จำกัด")
        self._add_row("ความยาวสูงสุด:", self.max_msg_length)

    def _add_blocked_user(self):
        """เพิ่มผู้ใช้เข้า block table"""
        name = self.block_input.text().strip()
        if not name:
            return
        self.block_input.clear()
        # check duplicate
        for r in range(self.block_table.rowCount()):
            item = self.block_table.item(r, 0)
            if item and item.text().lower() == name.lower():
                return
        self._add_blocked_row(name, "block_all")

    def _add_blocked_row(self, name, block_type):
        """เพิ่ม row ใน block table (+ ปุ่ม X แดงลบรายชื่อ — sync กับ modal ของ user)"""
        from PySide6.QtWidgets import QComboBox, QPushButton
        row = self.block_table.rowCount()
        self.block_table.insertRow(row)
        self.block_table.setItem(row, 0, QTableWidgetItem(name))
        combo = QComboBox()
        combo.addItem("🚫 บล็อกทุกอย่าง", "block_all")
        combo.addItem("🔇 บล็อก TTS เท่านั้น", "block_tts")
        combo.setCurrentIndex(0 if block_type == "block_all" else 1)
        # ★ จำกัดขนาดให้พอดีช่อง (กันตัวหนังสือใหญ่ทะลุกล่อง)
        combo.setFixedHeight(26)
        combo.setStyleSheet(
            "QComboBox { background: #1e293b; color: #e2e8f0; border: 1px solid #334155; "
            "border-radius: 4px; font-size: 12px; padding: 0 6px; min-height: 0; }"
            "QComboBox::drop-down { border: none; width: 18px; }"
            "QComboBox QAbstractItemView { background: #1e293b; color: #e2e8f0; "
            "selection-background-color: #7c3aed; font-size: 12px; }"
        )
        self.block_table.setCellWidget(row, 1, combo)
        # ★ ปุ่ม X สีแดง — ลบออกจาก blocklist + ปลดบล็อก user คนนั้นทันที
        #   ★★ กฎเหล็ก: ปุ่มไอคอนเล็กต้อง override padding/min-height เสมอ
        #       (ธีมกลาง padding 8px + min-height จะบีบจนไอคอน/ตัวอักษรมองไม่เห็น)
        btn_x = QPushButton("✕")
        btn_x.setFixedSize(32, 24)
        btn_x.setCursor(Qt.PointingHandCursor)
        btn_x.setToolTip(f"ลบ {name} ออกจาก Blocklist (ปลดบล็อกทันที)")
        btn_x.setStyleSheet(
            "QPushButton { background: transparent; color: #ef4444; border: none; "
            "font-size: 14px; font-weight: 700; padding: 0; min-height: 0; }"
            "QPushButton:hover { background: #ef4444; color: white; "
            "border-radius: 4px; padding: 0; min-height: 0; }"
        )
        btn_x.clicked.connect(lambda _, r=row, n=name: self._remove_blocked_row(r, n))
        self.block_table.setCellWidget(row, 2, btn_x)

    def _remove_blocked_row(self, row, name):
        """★ ลบ row ออกจากตาราง + ปลดบล็อกจริง (sync กับ modal ของ user คนนั้น)"""
        # ★ guard — row อาจถูกลบไปแล้ว (double click)
        if row >= self.block_table.rowCount():
            return
        item = self.block_table.item(row, 0)
        if not item or item.text().lower() != (name or "").lower():
            return
        self.block_table.removeRow(row)
        # ★ ปลดบล็อกจริงผ่าน app (อัปเดต settings + filter ทันที → modal ของ user
        #   ที่เปิดภายหลังจะเห็นสถานะกลับเป็นปกติ)
        app = getattr(self, 'parent_app', None)
        if app and hasattr(app, '_unblock_user'):
            try:
                app._unblock_user(name)
            except Exception:
                pass
        self._auto_save()

    def _remove_blocked_user(self):
        """ลบผู้ใช้ที่เลือกจาก block table"""
        rows = set()
        for item in self.block_table.selectedItems():
            rows.add(item.row())
        for r in sorted(rows, reverse=True):
            self.block_table.removeRow(r)

    # ════════════════════════════════════════════════════════════
    # ★ Secret Code section (โค้ดลับ → เล่นเสียง)
    # ════════════════════════════════════════════════════════════
    def _build_secret_code_section(self):
        """🎟 โค้ดลับ — viewer พิมพ์ !code ในแชท → เล่นเสียงหลัง TTS"""
        self._add_section("secret_code", "", "")
        layout = self._current_section_layout
        ci = lambda: layout.count() - 1

        # ── header row: [title] ...stretch... [limit spinbox] ──
        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        title_lbl = QLabel("🎟 โค้ดลับ")
        title_lbl.setStyleSheet("font-size: 20px; font-weight: 700; color: #f59e0b;")
        header_row.addWidget(title_lbl)
        header_row.addStretch()

        limit_lbl = QLabel("จำกัด/user/วัน:")
        limit_lbl.setStyleSheet("font-size: 12px; color: #94a3b8;")
        header_row.addWidget(limit_lbl)
        self.code_limit_spin = QSpinBox()
        self.code_limit_spin.setRange(0, 100)
        self.code_limit_spin.setValue(0)
        self.code_limit_spin.setFixedWidth(90)
        self.code_limit_spin.setToolTip("0 = ไม่จำกัด")
        self.code_limit_spin.valueChanged.connect(self._on_code_limit_change)
        header_row.addWidget(self.code_limit_spin)
        layout.insertLayout(ci(), header_row)

        # ── hint ──
        hint = QLabel(
            "💡 viewer พิมพ์โค้ด (เช่น !wow) → TTS อ่านส่วนที่เหลือ → เล่นเสียง\n"
            "★ พิมพ์ wow จะกลายเป็น !wow อัตโนมัติ"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size: 12px; color: #9ca3af; margin-bottom: 4px;")
        layout.insertWidget(ci(), hint)

        # ── เพิ่มโค้ดใหม่ ──
        add_row = QHBoxLayout()
        add_row.setSpacing(8)
        self.code_entry = QLineEdit()
        self.code_entry.setPlaceholderText("โค้ด เช่น wow")
        add_row.addWidget(self.code_entry, 1)

        btn_browse = QPushButton("➕ เพิ่ม")
        btn_browse.setObjectName("Primary")
        btn_browse.setMinimumHeight(32)
        btn_browse.clicked.connect(self._add_secret_code)
        add_row.addWidget(btn_browse)
        layout.insertLayout(ci(), add_row)

        # ── รายการโค้ดปัจจุบัน ──
        self._code_list_container = QWidget()
        self._code_list_layout = QVBoxLayout(self._code_list_container)
        self._code_list_layout.setContentsMargins(0, 0, 0, 0)
        self._code_list_layout.setSpacing(4)
        self._code_list_layout.addStretch()

        code_scroll = QScrollArea()
        code_scroll.setWidgetResizable(True)
        code_scroll.setWidget(self._code_list_container)
        code_scroll.setFrameShape(QScrollArea.NoFrame)
        code_scroll.setMinimumHeight(120)
        code_scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: 1px solid #1f2937; border-radius: 6px; }"
            "QScrollBar:vertical { background: #1f2937; width: 6px; border-radius: 3px; }"
            "QScrollBar::handle:vertical { background: #4b5563; border-radius: 3px; min-height: 20px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )
        layout.insertWidget(ci(), code_scroll)

        # ── โหลดค่า ──
        self._refresh_secret_code_list()

    def _refresh_secret_code_list(self):
        """rebuild รายการโค้ดลับใน settings"""
        cl = self._code_list_layout
        # เคลียร์เก่า (เก็บ stretch)
        while cl.count() > 1:
            item = cl.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        codes = getattr(self.settings, 'secret_codes', []) if self.settings else []
        if not codes:
            placeholder = QLabel("ยังไม่มีโค้ดลับ — เพิ่มได้ด้านบน")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet("font-size: 13px; color: #4b5563; padding: 16px;")
            cl.insertWidget(cl.count() - 1, placeholder)
            return

        for c in codes:
            if not isinstance(c, dict):
                continue
            code = c.get("code", "")
            sound_path = c.get("sound_path", "")
            volume = float(c.get("volume", 0.8))
            if not code:
                continue

            import os
            filename = os.path.basename(sound_path) if sound_path else "(ไม่มีไฟล์)"

            row = QFrame()
            row.setStyleSheet(
                "QFrame { background: #1f2937; border-radius: 6px; }"
                "QFrame:hover { background: #263244; }"
            )
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(10, 6, 10, 6)
            row_layout.setSpacing(8)

            # code
            code_lbl = QLabel(code)
            code_lbl.setStyleSheet("font-size: 14px; font-weight: 700; color: #10b981; min-width: 80px;")
            row_layout.addWidget(code_lbl)

            # filename
            file_lbl = QLabel(f"🔊 {filename}")
            file_lbl.setStyleSheet("font-size: 12px; color: #9ca3af;")
            row_layout.addWidget(file_lbl, 1)

            # volume slider
            vol_slider = QSlider(Qt.Horizontal)
            vol_slider.setRange(0, 100)
            vol_slider.setValue(int(volume * 100))
            vol_slider.setFixedWidth(80)
            vol_slider.setStyleSheet("QSlider { min-height: 20px; }")
            _code = code
            # ★ save เฉพาะตอนปล่อย slider (กัน save หนักจาก valueChanged)
            vol_slider.sliderReleased.connect(lambda c=_code: self._on_code_volume(c, vol_slider.value()))
            row_layout.addWidget(vol_slider)

            # ★ ปุ่ม Edit (แก้ code + เปลี่ยนไฟล์)
            btn_edit = QPushButton("✏️ Edit")
            btn_edit.setFixedHeight(30)
            btn_edit.setCursor(Qt.PointingHandCursor)
            btn_edit.setStyleSheet(
                "QPushButton { background: #334155; color: #06b6d4; border: none; border-radius: 4px; padding: 4px 10px; font-size: 12px; font-weight: 600; }"
                "QPushButton:hover { background: #475569; }"
            )
            btn_edit.clicked.connect(lambda checked=False, c=code: self._edit_secret_code(c))
            row_layout.addWidget(btn_edit)

            # ★ ปุ่ม Preview/Stop (ทดลองฟัง — กดซ้ำเพื่อหยุด)
            btn_preview = QPushButton("🔊 Preview")
            btn_preview.setFixedHeight(30)
            btn_preview.setCursor(Qt.PointingHandCursor)
            btn_preview.setStyleSheet(
                "QPushButton { background: #334155; color: #10b981; border: none; border-radius: 4px; padding: 4px 10px; font-size: 12px; font-weight: 600; }"
                "QPushButton:hover { background: #475569; }"
            )
            _path = sound_path
            _slider = vol_slider
            btn_preview.clicked.connect(lambda checked=False, p=_path, b=btn_preview, s=_slider: self._toggle_preview_sound(p, b, s))
            row_layout.addWidget(btn_preview)

            # ★ ปุ่ม Delete
            btn_del = QPushButton("🗑️ Delete")
            btn_del.setFixedHeight(30)
            btn_del.setCursor(Qt.PointingHandCursor)
            btn_del.setStyleSheet(
                "QPushButton { background: #ef4444; color: white; border: none; border-radius: 4px; padding: 4px 10px; font-size: 12px; font-weight: 600; }"
                "QPushButton:hover { background: #dc2626; }"
            )
            btn_del.clicked.connect(lambda checked=False, c=code: self._remove_secret_code(c))
            row_layout.addWidget(btn_del)

            cl.insertWidget(cl.count() - 1, row)

    def _add_secret_code(self):
        """เพิ่มโค้ดลับใหม่ — กรอกโค้ด + เลือกไฟล์เสียง"""
        from PySide6.QtWidgets import QFileDialog
        raw = self.code_entry.text().strip()
        if not raw:
            QMessageBox.warning(self, "ข้อมูลไม่ครบ", "กรุณากรอกโค้ดลับ")
            return
        # ★ บังคับ ! prefix
        code = raw if raw.startswith("!") else "!" + raw
        # เลือกไฟล์เสียง
        path, _ = QFileDialog.getOpenFileName(
            self, "เลือกไฟล์เสียง", "",
            "Audio (*.mp3 *.wav)"
        )
        if not path:
            return
        # เพิ่มใน settings
        if not self.settings:
            return
        codes = self.settings.secret_codes
        # ลบอันเดิมถ้ามี code ซ้ำ
        codes = [c for c in codes if c.get("code") != code]
        codes.append({"code": code, "sound_path": path, "volume": 0.8})
        self.settings.secret_codes = codes
        # sync text_filter
        try:
            from text_filter import SecretCode
            f = self.settings.to_text_filter() if hasattr(self.settings, 'to_text_filter') else None
        except Exception:
            pass
        # save
        self._auto_save()
        # refresh UI
        self._refresh_secret_code_list()
        self.code_entry.clear()
        QMessageBox.information(self, "✅ เพิ่มสำเร็จ", f"เพิ่มโค้ดลับ {code} แล้ว")

    def _remove_secret_code(self, code: str):
        """ลบโค้ดลับ"""
        if not self.settings:
            return
        reply = QMessageBox.question(
            self, "ยืนยันลบ", f"ลบโค้ดลับ {code}?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if reply != QMessageBox.Yes:
            return
        self.settings.secret_codes = [
            c for c in self.settings.secret_codes if c.get("code") != code
        ]
        self._auto_save()
        self._refresh_secret_code_list()

    def _edit_secret_code(self, code: str):
        """★ แก้โค้ดลับ — เปลี่ยน code และ/หรือไฟล์เสียง"""
        import os
        if not self.settings:
            return
        # หา entry เดิม
        entry = None
        for c in self.settings.secret_codes:
            if c.get("code") == code:
                entry = c
                break
        if not entry:
            return

        # ★ dialog แก้ไข
        from PySide6.QtWidgets import QDialog as _Dlg, QVBoxLayout as _VBL, QHBoxLayout as _HBL
        dlg = _Dlg(self)
        dlg.setWindowTitle(f"✏️ แก้ไขโค้ดลับ {code}")
        dlg.setMinimumWidth(400)
        dlg.setStyleSheet("QDialog { background: #0f172a; color: #e2e8f0; }"
                          "QLabel { color: #94a3b8; font-size: 12px; }"
                          "QLineEdit { background: #1e293b; border: 1px solid #334155; border-radius: 6px; padding: 8px; color: #e2e8f0; }"
                          "QPushButton { padding: 8px 16px; border: none; border-radius: 6px; font-weight: 600; }")

        dl = _VBL(dlg)
        dl.setSpacing(8)
        dl.setContentsMargins(20, 16, 20, 16)

        lbl_code = QLabel("โค้ด:")
        dl.addWidget(lbl_code)
        inp_code = QLineEdit(code)
        dl.addWidget(inp_code)

        lbl_file = QLabel(f"ไฟล์เสียง: {os.path.basename(entry.get('sound_path', '')) if entry.get('sound_path') else '(ไม่มี)'}")
        dl.addWidget(lbl_file)

        btn_file = QPushButton("📁 เปลี่ยนไฟล์เสียง")
        btn_file.setStyleSheet("background: #334155; color: #e2e8f0;")
        new_path = [entry.get("sound_path", "")]

        def _pick_file():
            from PySide6.QtWidgets import QFileDialog
            path, _ = QFileDialog.getOpenFileName(
                dlg, "เลือกไฟล์เสียง", "",
                "Audio (*.mp3 *.wav)")
            if path:
                new_path[0] = path
                lbl_file.setText(f"ไฟล์เสียง: {os.path.basename(path)}")
        btn_file.clicked.connect(_pick_file)
        dl.addWidget(btn_file)

        btn_row = _HBL()
        btn_row.addStretch()
        btn_cancel = QPushButton("ยกเลิก")
        btn_cancel.setStyleSheet("background: #334155; color: #e2e8f0;")
        btn_cancel.clicked.connect(dlg.reject)
        btn_row.addWidget(btn_cancel)
        btn_save = QPushButton("บันทึก")
        btn_save.setStyleSheet("background: #10b981; color: white;")
        btn_save.clicked.connect(dlg.accept)
        btn_row.addWidget(btn_save)
        dl.addLayout(btn_row)

        if dlg.exec():
            new_code = inp_code.text().strip()
            if not new_code:
                QMessageBox.warning(self, "ข้อมูลไม่ครบ", "กรุณากรอกโค้ด")
                return
            # บังคับ ! prefix
            if not new_code.startswith("!"):
                new_code = "!" + new_code
            # update entry
            entry["code"] = new_code
            entry["sound_path"] = new_path[0]
            self._auto_save()
            self._refresh_secret_code_list()

    def _on_code_volume(self, code: str, vol_int: int):
        """เปลี่ยนระดับเสียงของโค้ด"""
        if not self.settings:
            return
        vol = vol_int / 100.0
        for c in self.settings.secret_codes:
            if c.get("code") == code:
                c["volume"] = vol
                break
        self._auto_save()

    def _preview_code_sound(self, path: str):
        """ทดลองฟังเสียง (legacy — ใช้ _toggle_preview_sound แทน)"""
        self._toggle_preview_sound(path, None)

    def _toggle_preview_sound(self, path: str, btn=None, slider=None):
        """★ toggle preview — ถ้ากำลังเล่นอยู่ → หยุด; ถ้าไม่ได้เล่น → เริ่มเล่น

        เมื่อเล่น → ปุ่มเปลี่ยนเป็น "⏹ Stop"
        เมื่อจบ/หยุด → ปุ่มกลับเป็น "🔊 Preview"
        ★ volume อ่านจาก slider (ถ้ามี) — เล่นเสียงตามระดับที่ตั้ง
        """
        import os

        # ★ ถ้ามี channel เก่ากำลังเล่นอยู่ → หยุด
        if hasattr(self, '_preview_channel') and self._preview_channel is not None:
            try:
                if self._preview_channel.get_busy():
                    self._preview_channel.stop()
            except Exception:
                pass
            self._preview_channel = None
            # กลับเป็น Preview
            if btn:
                btn.setText("🔊 Preview")
                btn.setStyleSheet(
                    "QPushButton { background: #334155; color: #10b981; border: none; border-radius: 4px; padding: 4px 10px; font-size: 12px; font-weight: 600; }"
                    "QPushButton:hover { background: #475569; }"
                )
            return

        # ★ เริ่มเล่นใหม่
        if not path or not os.path.exists(path):
            if btn:
                QMessageBox.warning(self, "ไม่พบไฟล์", f"ไม่พบไฟล์: {path}")
            return

        try:
            import pygame
            snd = pygame.mixer.Sound(path)
            # ★ อ่าน volume จาก slider (0.0-1.0)
            vol = 0.8
            if slider:
                vol = slider.value() / 100.0
            snd.set_volume(max(0.0, min(1.0, vol)))
            self._preview_channel = pygame.mixer.find_channel(True)
            if self._preview_channel:
                self._preview_channel.play(snd)
                # เปลี่ยนปุ่มเป็น Stop
                if btn:
                    btn.setText("⏹ Stop")
                    btn.setStyleSheet(
                        "QPushButton { background: #ef4444; color: white; border: none; border-radius: 4px; padding: 4px 10px; font-size: 12px; font-weight: 600; }"
                        "QPushButton:hover { background: #dc2626; }"
                    )
                # ★ ตรวจสอบว่าเล่นจบหรือยัง → กลับเป็น Preview
                if btn:
                    _btn = btn
                    def _check_done():
                        if self._preview_channel and not self._preview_channel.get_busy():
                            _btn.setText("🔊 Preview")
                            _btn.setStyleSheet(
                                "QPushButton { background: #334155; color: #10b981; border: none; border-radius: 4px; padding: 4px 10px; font-size: 12px; font-weight: 600; }"
                                "QPushButton:hover { background: #475569; }"
                            )
                            self._preview_channel = None
                        else:
                            QTimer.singleShot(200, _check_done)
                    QTimer.singleShot(200, _check_done)
        except Exception as e:
            if btn:
                QMessageBox.warning(self, "เล่นไม่ได้", f"ไม่สามารถเล่นเสียง: {e}")

    def _on_code_limit_change(self, val: int):
        """เปลี่ยน daily limit (SpinBox)"""
        if not self.settings:
            return
        self.settings.secret_code_daily_limit = val
        self._auto_save()

    # ════════════════════════════════════════════════════════════
    # Overlay+ section (custom URL overlays — max 3)
    # ════════════════════════════════════════════════════════════
    def _build_overlay_plus_section(self):
        self._add_section("overlay_plus", "🪟 Overlay+",
                          "Custom URL overlays ลอยเหนือเกม (สูงสุด 3 อัน) — เช่น Streamlabs/StreamElements alerts")
        warn = QLabel("⚠️ 1 overlay กิน RAM ~100-200 MB\nเปิดเมื่อจำเป็นเท่านั้น")
        warn.setStyleSheet("color: #f59e0b; font-size: 12px; padding: 4px 0;")
        warn.setWordWrap(True)
        self._current_section_layout.insertWidget(self._current_section_layout.count() - 1, warn)
        # ★ ensure list has 3 entries
        overlays = list(getattr(self.settings, 'more_overlays', []))
        while len(overlays) < 3:
            overlays.append({"url": "", "x": -1, "y": -1, "w": 400, "h": 300, "alpha": 0.85, "enabled": False})
        self._mo_url_entries = []
        self._mo_enabled_cbs = []
        self._mo_alpha_sliders = []
        for i in range(3):
            cfg = overlays[i]
            # card title
            card = QFrame()
            card.setStyleSheet("QFrame { background: #131726; border: 1px solid #2a2f45; border-radius: 8px; }")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(10, 6, 10, 6)
            cl.setSpacing(4)
            # enabled checkbox + label
            top_row = QHBoxLayout()
            cb = QCheckBox(f"🔗 Overlay {i+1}")
            cb.setChecked(cfg.get("enabled", False))
            cb.setStyleSheet("color: #e5e7eb; font-size: 13px; font-weight: 600; spacing: 8px;")
            top_row.addWidget(cb)
            top_row.addStretch()
            alpha_lbl = QLabel(f"ความโปร่งใส: {int(cfg.get('alpha', 0.85)*100)}%")
            alpha_lbl.setStyleSheet("color: #9ca3af; font-size: 11px;")
            top_row.addWidget(alpha_lbl)
            cl.addLayout(top_row)
            # URL entry
            url_entry = QLineEdit(cfg.get("url", ""))
            url_entry.setPlaceholderText("https://streamlabs.com/alert-box/...")
            url_entry.setStyleSheet("QLineEdit { background: #0a0e1a; border: 1px solid #2a2f45; border-radius: 4px; padding: 6px 10px; color: #e5e7eb; }")
            cl.addWidget(url_entry)
            # alpha slider
            alpha_sld = QSlider(Qt.Horizontal)
            alpha_sld.setRange(10, 100)
            alpha_sld.setValue(int(cfg.get("alpha", 0.85) * 100))
            def _on_alpha(v, lbl=alpha_lbl, idx=i):
                lbl.setText(f"ความโปร่งใส: {v}%")
                self._save_overlay_plus(idx, alpha=v / 100.0)
            alpha_sld.valueChanged.connect(_on_alpha)
            cl.addWidget(alpha_sld)
            # position label (read-only)
            pos = cfg.get("x", -1), cfg.get("y", -1), cfg.get("w", 400), cfg.get("h", 300)
            pos_lbl = QLabel(f"ตำแหน่ง: {pos[0]}, {pos[1]} | ขนาด: {pos[2]}×{pos[3]}")
            pos_lbl.setStyleSheet("color: #6b7280; font-size: 11px;")
            cl.addWidget(pos_lbl)
            self._current_section_layout.insertWidget(self._current_section_layout.count() - 1, card)
            self._mo_url_entries.append(url_entry)
            self._mo_enabled_cbs.append(cb)
            self._mo_alpha_sliders.append(alpha_sld)
            # save on URL edit + enabled toggle
            url_entry.editingFinished.connect(lambda idx=i, e=url_entry: self._save_overlay_plus(idx, url=e.text()))
            cb.toggled.connect(lambda checked, idx=i: self._save_overlay_plus(idx, enabled=checked))
        # ★ hotkey card
        hk_card = QFrame()
        hk_card.setStyleSheet("QFrame { background: #131726; border: 1px solid #2a2f45; border-radius: 8px; }")
        hkl = QVBoxLayout(hk_card)
        hkl.setContentsMargins(10, 6, 10, 6)
        hkl.setSpacing(4)
        hk_title = QLabel("🔑 Hotkeys")
        hk_title.setStyleSheet("color: #f59e0b; font-size: 13px; font-weight: 700;")
        hkl.addWidget(hk_title)
        hk_toggle = getattr(self.settings, 'more_overlay_hotkey', 'ctrl+shift+m')
        hk_edit = getattr(self.settings, 'more_overlay_hotkey_edit', 'ctrl+shift+n')
        from ui.dialogs.hotkey_binder import make_hotkey_binder
        toggle_row = QHBoxLayout()
        toggle_row.addWidget(QLabel("เปิด/ปิด:"))
        self.mo_hk_toggle_entry = make_hotkey_binder(
            self, hk_toggle, on_captured=lambda hk: self._save_hotkey_overlay_plus('toggle', hk)
        )
        toggle_row.addWidget(self.mo_hk_toggle_entry, 1)
        toggle_row.addStretch()
        hkl.addLayout(toggle_row)
        edit_row = QHBoxLayout()
        edit_row.addWidget(QLabel("Edit Mode:"))
        self.mo_hk_edit_entry = make_hotkey_binder(
            self, hk_edit, on_captured=lambda hk: self._save_hotkey_overlay_plus('edit', hk)
        )
        edit_row.addWidget(self.mo_hk_edit_entry, 1)
        edit_row.addStretch()
        hkl.addLayout(edit_row)
        hk_hint = QLabel("💡 คลิกปุ่มแล้วกดคีย์ผสมที่ต้องการ\nรองรับ F1-F35, ตัวอักษร, ตัวเลข — เช่น f13, ctrl+f24, shift+f1, ctrl+shift+m\nกด Esc เพื่อยกเลิกการจับคีย์")
        hk_hint.setStyleSheet("color: #6b7280; font-size: 11px; padding-top: 4px;")
        hk_hint.setWordWrap(True)
        hkl.addWidget(hk_hint)
        self._current_section_layout.insertWidget(self._current_section_layout.count() - 1, hk_card)

    def _save_overlay_plus(self, idx, url=None, enabled=None, alpha=None):
        """save single overlay+ entry"""
        overlays = list(getattr(self.settings, 'more_overlays', []))
        while len(overlays) <= idx:
            overlays.append({"url": "", "x": -1, "y": -1, "w": 400, "h": 300, "alpha": 0.85, "enabled": False})
        if url is not None:
            overlays[idx]["url"] = url
        if enabled is not None:
            overlays[idx]["enabled"] = enabled
        if alpha is not None:
            overlays[idx]["alpha"] = alpha
        self.settings.more_overlays = overlays[:3]
        try:
            from settings import save_settings
            save_settings(self.settings)
        except Exception:
            pass

    def _save_hotkey_overlay_plus(self, which, hotkey):
        """save hotkey ที่จับได้จาก binder button (which = 'toggle' | 'edit')"""
        if not self.settings:
            return
        if which == 'toggle':
            self.settings.more_overlay_hotkey = (hotkey or "ctrl+shift+m").strip().lower()
        else:
            self.settings.more_overlay_hotkey_edit = (hotkey or "ctrl+shift+n").strip().lower()
        try:
            from settings import save_settings
            save_settings(self.settings)
        except Exception:
            pass

    def _build_twitch_bot_section(self):
        """🤖 Chat Bot (Twitch) — คำสั่งอัตโนมัติ + Timer"""
        self._add_section("twitch_bot", "🤖 Chat Bot (Twitch)",
                          "ตอบคำสั่งอัตโนมัติ + ส่งข้อความซ้ำตามช่วงเวลา (เหมือน Nightbot)")
        layout = self._current_section_layout
        ci = lambda: layout.count() - 1

        # ★ Toggle เปิด/ปิด bot
        self.bot_enabled_cb = QCheckBox("เปิดใช้งาน Chat Bot (ตอบคำสั่ง !xxx อัตโนมัติ)")
        self.bot_enabled_cb.stateChanged.connect(lambda _: self._auto_save())
        layout.insertWidget(ci(), self.bot_enabled_cb)

        # ★ ASK — โพสผลสรุปโหวตลงแชททุกแพลตฟอร์มที่เชื่อมไว้ (เมื่อโพลจบ)
        self.ask_post_result_cb = QCheckBox("โพสผลสรุปโหวต ASK ลงแชทเมื่อจบโหวต (แพลตฟอร์มที่เชื่อมอยู่)")
        self.ask_post_result_cb.stateChanged.connect(lambda _: self._auto_save())
        layout.insertWidget(ci(), self.ask_post_result_cb)

        # ★ เลือกว่าให้ Bot ทำงานที่แพลตฟอร์มไหนบ้าง (ปิดเฉพาะแพลตฟอร์มได้)
        plat_row = QHBoxLayout()
        plat_lbl = QLabel("ให้ Bot ทำงานที่:")
        plat_lbl.setStyleSheet("color: #e5e7eb; font-size: 12px;")
        plat_row.addWidget(plat_lbl)
        self.bot_plat_cbs = {}
        # ★ แสดงเฉพาะแพลตฟอร์มที่มี Bot จริง (YouTube ยังไม่มี)
        for key, label in (("twitch", "Twitch"), ("kick", "KICK")):
            cb = QCheckBox(label)
            cb.setToolTip(f"เปิด/ปิด Bot เฉพาะ {label} (ปิดแล้ว Bot เงียบเฉพาะที่นี่)")
            cb.stateChanged.connect(lambda _: self._auto_save())
            plat_row.addWidget(cb)
            self.bot_plat_cbs[key] = cb
        plat_row.addStretch()
        from PySide6.QtWidgets import QWidget as _W
        _plat_holder = _W()
        _plat_holder.setLayout(plat_row)
        layout.insertWidget(ci(), _plat_holder)

        # ★ Note
        note = QLabel("ℹ️ ต้องล็อกอิน Twitch ก่อน (ไปที่ section 🔌 แพลตฟอร์ม → เชื่อมต่อ Twitch)")
        note.setWordWrap(True)
        note.setStyleSheet("color: #94a3b8; font-size: 12px;")
        layout.insertWidget(ci(), note)

        # ═══ Commands section ═══
        cmd_title = QLabel("📝 คำสั่ง Bot")
        cmd_title.setStyleSheet("font-weight: 600; color: #f59e0b; margin-top: 12px;")
        layout.insertWidget(ci(), cmd_title)

        cmd_desc = QLabel("เมื่อมีคนพิมพ์ !command ในแชท → Bot จะตอบด้วยข้อความที่ตั้งไว้")
        cmd_desc.setWordWrap(True)
        cmd_desc.setStyleSheet("color: #64748b; font-size: 12px;")
        layout.insertWidget(ci(), cmd_desc)

        # ★ Container สำหรับ rows คำสั่ง (dynamic add/remove)
        self._bot_cmd_rows = []  # list of (command_input, response_input, remove_btn)
        self._bot_cmd_container = QWidget()
        self._bot_cmd_layout = QVBoxLayout(self._bot_cmd_container)
        self._bot_cmd_layout.setContentsMargins(0, 0, 0, 0)
        self._bot_cmd_layout.setSpacing(4)
        layout.insertWidget(ci(), self._bot_cmd_container)

        # ★ ปุ่มเพิ่มคำสั่ง
        btn_add_cmd = QPushButton("+ เพิ่มคำสั่ง")
        btn_add_cmd.setCursor(Qt.PointingHandCursor)
        btn_add_cmd.setStyleSheet(
            "QPushButton { background: #1e293b; color: #a78bfa; border: 1px dashed #475569; "
            "border-radius: 6px; padding: 6px; }"
            "QPushButton:hover { background: #334155; }"
        )
        btn_add_cmd.clicked.connect(lambda: self._add_bot_cmd_row("", ""))
        layout.insertWidget(ci(), btn_add_cmd)

        # ═══ Timers section ═══
        timer_title = QLabel("⏰ Timer (ส่งข้อความซ้ำ)")
        timer_title.setStyleSheet("font-weight: 600; color: #f59e0b; margin-top: 16px;")
        layout.insertWidget(ci(), timer_title)

        timer_desc = QLabel("ส่งข้อความซ้ำทุก N นาที (เช่น ทุก 10 นาที ส่ง 'Follow me!')")
        timer_desc.setWordWrap(True)
        timer_desc.setStyleSheet("color: #64748b; font-size: 12px;")
        layout.insertWidget(ci(), timer_desc)

        # ★ Container สำหรับ rows timer
        self._bot_timer_rows = []
        self._bot_timer_container = QWidget()
        self._bot_timer_layout = QVBoxLayout(self._bot_timer_container)
        self._bot_timer_layout.setContentsMargins(0, 0, 0, 0)
        self._bot_timer_layout.setSpacing(4)
        layout.insertWidget(ci(), self._bot_timer_container)

        # ★ ปุ่มเพิ่ม timer
        btn_add_timer = QPushButton("+ เพิ่ม Timer")
        btn_add_timer.setCursor(Qt.PointingHandCursor)
        btn_add_timer.setStyleSheet(
            "QPushButton { background: #1e293b; color: #a78bfa; border: 1px dashed #475569; "
            "border-radius: 6px; padding: 6px; }"
            "QPushButton:hover { background: #334155; }"
        )
        btn_add_timer.clicked.connect(lambda: self._add_bot_timer_row("", 10))
        layout.insertWidget(ci(), btn_add_timer)

        # ═══ Bot name ═══
        name_title = QLabel("🏷️ ชื่อบอท")
        name_title.setStyleSheet("font-weight: 600; color: #f59e0b; margin-top: 16px;")
        layout.insertWidget(ci(), name_title)

        name_desc = QLabel("ชื่อบอทในโปรแกรม — TTS จะไม่อ่านข้อความที่ตรงกับชื่อนี้ "
                           "(แม้จะใช้บัญชีของคุณโพสก็ตาม)")
        name_desc.setWordWrap(True)
        name_desc.setStyleSheet("color: #64748b; font-size: 12px;")
        layout.insertWidget(ci(), name_desc)

        self.bot_name_input = QLineEdit()
        self.bot_name_input.setPlaceholderText("Baitoei-Bot")
        self.bot_name_input.setStyleSheet(
            "QLineEdit { background: #0f172a; color: #e2e8f0; border: 1px solid #334155; "
            "border-radius: 4px; padding: 6px 10px; }"
        )
        # ★ auto-save (textChanged + debounce)
        from PySide6.QtCore import QTimer
        _bot_name_timer = QTimer(self)
        _bot_name_timer.setSingleShot(True)
        _bot_name_timer.setInterval(500)
        _bot_name_timer.timeout.connect(self._auto_save)
        self.bot_name_input.textChanged.connect(lambda _: _bot_name_timer.start())
        layout.insertWidget(ci(), self.bot_name_input)

        # ═══ Event responses ═══
        ev_title = QLabel("🎉 Event Responses (ตอบอัตโนมัติ)")
        ev_title.setStyleSheet("font-weight: 600; color: #f59e0b; margin-top: 16px;")
        layout.insertWidget(ci(), ev_title)

        self.bot_events_cb = QCheckBox("เปิดใช้งาน Event Responses (Sub/Bits/Raid อัตโนมัติ)")
        self.bot_events_cb.stateChanged.connect(lambda _: self._auto_save())
        layout.insertWidget(ci(), self.bot_events_cb)

        ev_desc = QLabel("ใช้ placeholders: {user} = ชื่อคน, {amount} = จำนวน bits, "
                         "{months} = เดือน sub, {raid_count} = ยอดคนดูที่มา")
        ev_desc.setWordWrap(True)
        ev_desc.setStyleSheet("color: #64748b; font-size: 12px;")
        layout.insertWidget(ci(), ev_desc)

        # ★ Event input rows (label + lineedit)
        _input_style = (
            "QLineEdit { background: #0f172a; color: #e2e8f0; border: 1px solid #334155; "
            "border-radius: 4px; padding: 6px 10px; }"
        )
        _label_style = "color: #cbd5e1; font-size: 13px;"

        # ★ auto-save debounce timer (ใช้ร่วมกับทุก event input)
        from PySide6.QtCore import QTimer
        _ev_save_timer = QTimer(self)
        _ev_save_timer.setSingleShot(True)
        _ev_save_timer.setInterval(500)
        _ev_save_timer.timeout.connect(self._auto_save)

        self.bot_ev_sub = QLineEdit()
        self.bot_ev_sub.setPlaceholderText("ขอบคุณ {user} สำหรับการ Sub! 💜")
        self.bot_ev_sub.setStyleSheet(_input_style)
        self.bot_ev_sub.textChanged.connect(lambda _: _ev_save_timer.start())
        ev_sub_lbl = QLabel("Sub / Re-sub:")
        ev_sub_lbl.setStyleSheet(_label_style)
        layout.insertWidget(ci(), ev_sub_lbl)
        layout.insertWidget(ci(), self.bot_ev_sub)

        self.bot_ev_bits = QLineEdit()
        self.bot_ev_bits.setPlaceholderText("ขอบคุณ {user} สำหรับ {amount} bits! 💎")
        self.bot_ev_bits.setStyleSheet(_input_style)
        self.bot_ev_bits.textChanged.connect(lambda _: _ev_save_timer.start())
        ev_bits_lbl = QLabel("Bits:")
        ev_bits_lbl.setStyleSheet(_label_style)
        layout.insertWidget(ci(), ev_bits_lbl)
        layout.insertWidget(ci(), self.bot_ev_bits)

        self.bot_ev_raid = QLineEdit()
        self.bot_ev_raid.setPlaceholderText("ขอบคุณ {user} สำหรับการ Raid พา {raid_count} คนมา! 🎉")
        self.bot_ev_raid.setStyleSheet(_input_style)
        self.bot_ev_raid.textChanged.connect(lambda _: _ev_save_timer.start())
        ev_raid_lbl = QLabel("Raid:")
        ev_raid_lbl.setStyleSheet(_label_style)
        layout.insertWidget(ci(), ev_raid_lbl)
        layout.insertWidget(ci(), self.bot_ev_raid)

        self.bot_ev_follow = QLineEdit()
        self.bot_ev_follow.setPlaceholderText("ขอบคุณ {user} ที่ติดตาม! ❤️")
        self.bot_ev_follow.setStyleSheet(_input_style)
        self.bot_ev_follow.textChanged.connect(lambda _: _ev_save_timer.start())
        ev_follow_lbl = QLabel("Follow:")
        ev_follow_lbl.setStyleSheet(_label_style)
        layout.insertWidget(ci(), ev_follow_lbl)
        layout.insertWidget(ci(), self.bot_ev_follow)

        # ═══ Overlay filter ═══
        overlay_title = QLabel("🖥️ การแสดงใน Overlay")
        overlay_title.setStyleSheet("font-weight: 600; color: #f59e0b; margin-top: 16px;")
        layout.insertWidget(ci(), overlay_title)

        self.overlay_hide_bots_cb = QCheckBox("ซ่อนข้อความบอทจาก Overlay "
                                              "(Nightbot, StreamElements, บอทของเรา ฯลฯ)")
        self.overlay_hide_bots_cb.stateChanged.connect(lambda _: self._auto_save())
        layout.insertWidget(ci(), self.overlay_hide_bots_cb)

        overlay_desc = QLabel("ถ้าเปิด → ข้อความของบอทจะไม่แสดงใน Overlay (แต่ยังแสดงใน Live Chat)")
        overlay_desc.setWordWrap(True)
        overlay_desc.setStyleSheet("color: #64748b; font-size: 12px;")
        layout.insertWidget(ci(), overlay_desc)

    def _add_bot_cmd_row(self, command: str, response: str):
        """เพิ่ม row คำสั่ง bot"""
        row = QFrame()
        row.setStyleSheet("QFrame { background: #1e293b; border-radius: 6px; }")
        rlayout = QHBoxLayout(row)
        rlayout.setContentsMargins(8, 6, 8, 6)
        rlayout.setSpacing(6)

        cmd_input = QLineEdit(command)
        cmd_input.setPlaceholderText("!command")
        cmd_input.setFixedWidth(120)
        cmd_input.setStyleSheet(
            "QLineEdit { background: #0f172a; color: #e2e8f0; border: 1px solid #334155; "
            "border-radius: 4px; padding: 4px 8px; }"
        )

        arrow = QLabel("→")
        arrow.setStyleSheet("color: #64748b;")

        resp_input = QLineEdit(response)
        resp_input.setPlaceholderText("ข้อความตอบกลับ")
        resp_input.setStyleSheet(
            "QLineEdit { background: #0f172a; color: #e2e8f0; border: 1px solid #334155; "
            "border-radius: 4px; padding: 4px 8px; }"
        )

        btn_del = QPushButton("✕")
        btn_del.setFixedSize(20, 20)
        btn_del.setCursor(Qt.PointingHandCursor)
        btn_del.setStyleSheet(
            "QPushButton { background: transparent; color: #ef4444; border: none; font-size: 16px; font-weight: bold; }"
            "QPushButton:hover { color: #dc2626; }"
        )

        rlayout.addWidget(cmd_input)
        rlayout.addWidget(arrow)
        rlayout.addWidget(resp_input, 1)
        rlayout.addWidget(btn_del)

        # ★ auto-save เมื่อแก้ไข (textChanged + debounce 500ms — กัน save รัวๆ)
        from PySide6.QtCore import QTimer
        save_timer = QTimer(self)
        save_timer.setSingleShot(True)
        save_timer.setInterval(500)
        save_timer.timeout.connect(self._auto_save)
        cmd_input.textChanged.connect(lambda _: save_timer.start())
        resp_input.textChanged.connect(lambda _: save_timer.start())

        # ★ remove button handler
        def _remove():
            row.setParent(None)
            row.deleteLater()
            if row in self._bot_cmd_rows:
                self._bot_cmd_rows.remove(row)
            self._auto_save()
        btn_del.clicked.connect(_remove)

        self._bot_cmd_layout.addWidget(row)
        self._bot_cmd_rows.append(row)

    def _add_bot_timer_row(self, text: str, interval_min: int = 10, min_chat_count: int = 0):
        """เพิ่ม row timer — เลือกโหมดได้: ทุก N นาที หรือ ทุก N ข้อความ"""
        row = QFrame()
        row.setStyleSheet("QFrame { background: #1e293b; border-radius: 6px; }")
        rlayout = QHBoxLayout(row)
        rlayout.setContentsMargins(8, 6, 8, 6)
        rlayout.setSpacing(6)

        _input_style = (
            "QLineEdit { background: #0f172a; color: #e2e8f0; border: 1px solid #334155; "
            "border-radius: 4px; padding: 4px 8px; }"
        )
        _label_style = "color: #64748b;"

        text_input = QLineEdit(text)
        text_input.setPlaceholderText("ข้อความที่จะส่งซ้ำ")
        text_input.setStyleSheet(_input_style)

        # ★ mode dropdown: "ทุก N นาที" หรือ "ทุก N ข้อความ"
        mode_combo = QComboBox()
        mode_combo.addItem("⏰ ทุกๆ", "interval")
        mode_combo.addItem("💬 ทุกๆ", "chat_count")
        if min_chat_count > 0:
            mode_combo.setCurrentIndex(1)
        mode_combo.setMinimumWidth(100)
        mode_combo.setStyleSheet(
            "QComboBox { background: #0f172a; color: #e2e8f0; border: 1px solid #334155; "
            "border-radius: 4px; padding: 4px 8px; }"
        )

        value_input = QLineEdit()
        value_input.setFixedWidth(50)
        value_input.setStyleSheet(_input_style)
        if min_chat_count > 0:
            value_input.setText(str(min_chat_count))
        elif interval_min > 0:
            value_input.setText(str(interval_min))

        unit_lbl = QLabel("นาที")
        unit_lbl.setStyleSheet(_label_style)

        def _on_mode_change():
            if mode_combo.currentData() == "interval":
                unit_lbl.setText("นาที")
            else:
                unit_lbl.setText("ข้อความ")
            save_timer.start()
        mode_combo.currentIndexChanged.connect(_on_mode_change)

        btn_del = QPushButton("✕")
        btn_del.setFixedSize(20, 20)
        btn_del.setCursor(Qt.PointingHandCursor)
        btn_del.setStyleSheet(
            "QPushButton { background: transparent; color: #ef4444; border: none; font-size: 16px; font-weight: bold; }"
            "QPushButton:hover { color: #dc2626; }"
        )

        rlayout.addWidget(text_input, 1)
        rlayout.addWidget(mode_combo)
        rlayout.addWidget(value_input)
        rlayout.addWidget(unit_lbl)
        rlayout.addWidget(btn_del)

        # ★ auto-save (debounce 500ms)
        from PySide6.QtCore import QTimer
        save_timer = QTimer(self)
        save_timer.setSingleShot(True)
        save_timer.setInterval(500)
        save_timer.timeout.connect(self._auto_save)
        text_input.textChanged.connect(lambda _: save_timer.start())
        value_input.textChanged.connect(lambda _: save_timer.start())

        # ★ เก็บ widgets สำหรับ collect
        row._text_input = text_input
        row._mode_combo = mode_combo
        row._value_input = value_input

        def _remove():
            row.setParent(None)
            row.deleteLater()
            if row in self._bot_timer_rows:
                self._bot_timer_rows.remove(row)
            self._auto_save()
        btn_del.clicked.connect(_remove)

        self._bot_timer_layout.addWidget(row)
        self._bot_timer_rows.append(row)

    def _build_about_section(self):
        """ℹ️ เกี่ยวกับ — เนื้อหาจาก v1 AboutDialog (port มา PySide6)"""
        self._add_section("about", "", "")
        layout = self._current_section_layout
        ci = lambda: layout.count() - 1  # insert index (ก่อน stretch)

        # ── version (อ่านครั้งเดียว → ใช้ทั้งใน header ขวา + ปุ่มเช็คอัพเดท) ──
        try:
            from updater import get_current_version, get_build_type
            _ver = get_current_version()
            _bt = get_build_type()
            ver_text = f"v{_ver} ({'Lite' if _bt == 'lite' else 'Full'})"
        except Exception:
            ver_text = "v?"

        # ── header: [🎮 title] ...stretch... [version] [เช็คอัพเดท] ──
        header = QHBoxLayout()
        header.setSpacing(8)
        icon_lbl = QLabel("🎮")
        icon_lbl.setStyleSheet("font-size: 26px; font-weight: 700;")
        title_lbl = QLabel("Broadcast Playroom 2")
        title_lbl.setStyleSheet("font-size: 22px; font-weight: 700; color: #f59e0b;")
        header.addWidget(icon_lbl)
        header.addWidget(title_lbl)
        header.addStretch()
        # version (ขวา)
        ver_lbl = QLabel(ver_text)
        ver_lbl.setStyleSheet("font-size: 12px; color: #6b7280;")
        header.addWidget(ver_lbl)
        # ปุ่มเช็คอัพเดท (ขวาสุด)
        btn_update = QPushButton("🔄 เช็คอัพเดท")
        btn_update.setStyleSheet(
            "QPushButton { color: #06b6d4; font-size: 12px; font-weight: 600; "
            "border: none; background: transparent; padding: 4px 8px; }"
            "QPushButton:hover { color: #0891b2; text-decoration: underline; }"
        )
        btn_update.setCursor(Qt.PointingHandCursor)
        btn_update.clicked.connect(self._check_update)
        header.addWidget(btn_update)
        layout.insertLayout(ci(), header)

        # subtitle
        sub = QLabel("รวบข้อมูลแชท และ อ่านแชทจากเว็บไลฟ์สตรีม ด้วยเสียงสังเคราะห์")
        sub.setStyleSheet("font-size: 15px; color: #9ca3af; margin-bottom: 4px;")
        layout.insertWidget(ci(), sub)

        # ── ข้อความอธิบาย (แบ่งเป็น paragraphs) ──
        paragraphs = [
            ("โปรแกรมนี้ถูกออกแบบเพื่อให้ใช้แสดงข้อมูลแชทจากเว็บไซต์สตรีมมิ่งทั้ง 5 แพลตฟอร์ม "
             "(Twitch, MyLive, Youtube, Kick, Tiktok) โดยสามารถบริหารจัดการและเก็บข้อมูลผู้แชทได้ทั้งหมด "
             "รวมถึงข้อมูลการโดเนทหรือการกดซับในทุกๆรูปแบบ", None),

            ("นอกจากนั้นโปรแกรมนี้ยังสามารถให้ระบบ TTS-Text to Speech ช่วยอ่านข้อความแชทให้อัตโนมัติ "
             "โดยไม่ต้องเหลือบมามองโปรแกรมเลย เหมาะสำหรับผู้ที่ชอบโฟกัสกับจอเกมขณะถ่ายทอดสด "
             "และเหมาะกับผู้ที่มีจอคอมเพียงจอเดียว", None),

            ("ตั้งแต่เวอร์ชั่น 2.0 เป็นต้นไป โปรแกรมถูกออกแบบมาให้เลือกใช้ TTS ได้ 2 โมเดล "
             "คือ Azure และ Omnivoice โดยทั้งสองแบบจะมีจุดเด่นที่ต่างกันไปคือ", None),

            ("Azure จะสามารถอ่านข้อความได้ชัดและแม่นยำกว่า Omnivoice มาก "
             "แต่จำเป็นจะต้องใช้อินเตอร์เน็ตในการส่งข้อมูลไปอ่าน (ONLINE MODE) "
             "บางครั้งถ้าเซิฟเวอร์ปลายทางไม่ดี อาจจะพบปัญหาเสียงอ่านมาช้า", None),

            ("Omnivoice เป็นอีกโมเดล TTS อีกตัวนึง ซึ่งมีความสามารถในการอ่านเสียงภาษาไทยที่ดีมากอีกตัว "
             "ข้อดีคือประมวลทุกอย่างในคอมได้เลย (OFFLINE MODE) "
             "แต่จะมีจุดอ่อนตรงที่ไม่สามารถอ่านคำที่ถูกโพสมาสั้นๆได้ เช่น \"อ่อ , ครับ , เค\" เป็นต้น", None),

            ("ฉะนั้นผู้ใช้งานจะต้องเลือกใช้ตามความเหมาะสม หากชอบแบบไหนก็ลองเลือกใช้กันดูครับ", None),

            ("หลังจากตั้งเสียงเสร็จแล้วยังมีการ Filter เสียง ด้วยระบบ RVC "
             "เพื่อให้โทนเสียงต่างออกไปอีก สามารถเลือกโหลดโมเดลเสียงต่างๆได้ที่ปุ่มดาวโหลดโมเดล "
             "ใกล้ๆจุดเปลี่ยนโมเดล RVC ครับ", None),

            ("นอกเหนือจาก TTS แล้วยังมีระบบจัดการอีกมากมาย "
             "แนะนำให้ลองเล่นโปรแกรมเพื่อทำความเข้าใจดูครับ "
             "หรือถ้าไม่รู้สามารถอ่านได้ที่เว็บไซต์ของผมได้ครับ", None),

            ("⚠️ สิ่งที่ควรทราบไว้ก่อนใช้โปรแกรมนี้", "#f59e0b"),

            ("การใช้ Omnivoice และ RVC นั้นจำเป็นจะต้องใช้การ์ดจอที่รองรับ CUDA "
             "ซึ่งมีแค่บนการ์ดจอซีรี่ย์ RTX ทุกรุ่น "
             "ขนาดของโปรแกรมที่รองรับ RVC นั้นจะมีขนาดใหญ่มาก "
             "และยังไม่รวมโมเดลเสียง RVC ที่โหลดมาใช้เพิ่มเติม "
             "สาเหตุที่โปรแกรมใหญ่นั้น เกิดจากไฟล์ของ CUDA ล้วนๆ "
             "ไม่ใช่ตัวหลักของโปรแกรมนี้เลย "
             "และเราไม่สามารถลดขนาดไฟล์ให้ต่ำกว่านี้ได้แล้ว "
             "เป็นขีดจำกัดของระบบ TTS ล้วนๆ", None),

            ("หากผู้ใดคิดว่าโปรแกรมเวอร์ชั่น FULL ที่ใช้พื้นที่เยอะเกินไป "
             "สามารถเลือกใช้เวอร์ชั่น LITE ได้เช่นกัน "
             "เพียงแต่จะไม่มี Omnivoice และ RVC "
             "แต่ยังมี Azure ให้ใช้ตามเดิมครับ", None),
        ]
        for text, color in paragraphs:
            lbl = QLabel(text)
            lbl.setWordWrap(True)
            lbl.setAlignment(Qt.AlignLeft)
            if color:
                lbl.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {color}; margin-top: 8px;")
            else:
                lbl.setStyleSheet("font-size: 15px; color: #e5e7eb;")
            layout.insertWidget(ci(), lbl)

        # ── credit ──
        credit = QLabel("By MeN9CH")
        credit.setStyleSheet("font-size: 14px; font-weight: 700; color: #06b6d4; margin-top: 12px;")
        layout.insertWidget(ci(), credit)
        credit_desc = QLabel(
            "นอกเหนือจากโปรแกรมนี้แล้ว เรายังมีพัฒนาโปรแกรมอื่น และเขียนลง Blog เช่นกัน "
            "สามารถเข้าไปรับชม สอบถามการใช้งานได้ หากพบเห็นจะทำการตอบกลับทันทีครับ"
        )
        credit_desc.setWordWrap(True)
        credit_desc.setStyleSheet("font-size: 13px; color: #9ca3af;")
        layout.insertWidget(ci(), credit_desc)

        # ── ปุ่มเว็บ ──
        btn_web = QPushButton("🌐 www.men9ch.com")
        btn_web.setObjectName("Primary")
        btn_web.setMinimumHeight(32)
        btn_web.clicked.connect(lambda: self._open_url("https://www.men9ch.com"))
        layout.insertWidget(ci(), btn_web)

    def _build_announce_section(self):
        """📢 ประกาศถึงผู้ใช้ — หน้าสำหรับเจ้าของโปรแกรมเท่านั้น

        พิมพ์ข้อความ → push ขึ้น GitHub (announce.json) → แถบประกาศโผล่ในโปรแกรมทุกเครื่อง
        จนกว่าจะกดลบ (สำหรับ user ทั่วไปหน้านี้ไม่มีผลอะไร — แค่ดูประกาศในแถบ)
        """
        from PySide6.QtWidgets import QTextEdit, QComboBox
        w = self._add_section(
            "announce", "📢 ประกาศถึงผู้ใช้",
            "ส่งข้อความถึงทุกคนที่ใช้โปรแกรม — ข้อความจะขึ้นเป็นแถบเหนือ footer ของทุกเครื่อง "
            "จนกว่าจะลบ (เหมาะกับประกาศให้รีบอัพเดท หรือข่าวสาร)"
        )

        # ── Token ──
        self.ann_token = QLineEdit()
        self.ann_token.setEchoMode(QLineEdit.Password)
        self.ann_token.setPlaceholderText("github_pat_... (ใส่ครั้งเดียว — เจ้าของเท่านั้น)")
        self._add_row("GitHub Token", self.ann_token)
        hint = QLabel(
            "สร้างครั้งเดียว: GitHub → Settings → Developer settings → Fine-grained tokens → "
            "เลือกเฉพาะ repo broadcast-playroom-ex + Permission: Contents = Read and write"
        )
        hint.setStyleSheet("color: #6b7280; font-size: 11px;")
        hint.setWordWrap(True)
        self._current_section_layout.insertWidget(self._current_section_layout.count() - 1, hint)

        # ── ข้อความ ──
        self.ann_text = QTextEdit()
        self.ann_text.setPlaceholderText("พิมพ์ข้อความประกาศ เช่น: มีเวอร์ชั่นใหม่ 2.6.3 แก้บัคสำคัญ — รีบอัพเดทนะครับ")
        self.ann_text.setFixedHeight(90)
        self._add_row("ข้อความ", self.ann_text)

        # ── type + URL ──
        self.ann_type = QComboBox()
        self.ann_type.addItem("📢 อัพเดท (ส้ม)", "update")
        self.ann_type.addItem("ℹ️ ข้อมูล (ฟ้า)", "info")
        self.ann_type.addItem("⚠️ เตือน (แดง)", "warning")
        self._add_row("ระดับ", self.ann_type)

        self.ann_url = QLineEdit()
        self.ann_url.setPlaceholderText("https://... (ไม่บังคับ — ถ้าใส่จะมีปุ่ม 'เปิดลิงก์' ในแถบ)")
        self._add_row("ลิงก์ (ไม่บังคับ)", self.ann_url)

        # ── ปุ่มเผยแพร่/ลบ + สถานะ ──
        btn_row = QHBoxLayout()
        self.ann_publish_btn = QPushButton("🚀 เผยแพร่ประกาศ")
        self.ann_publish_btn.setStyleSheet(
            "background:#10b981;color:#fff;border:none;border-radius:6px;padding:9px 18px;font-weight:700;"
        )
        self.ann_publish_btn.setCursor(Qt.PointingHandCursor)
        self.ann_delete_btn = QPushButton("🗑 ลบประกาศปัจจุบัน")
        self.ann_delete_btn.setStyleSheet(
            "background:rgba(239,68,68,0.15);color:#f87171;border:1px solid rgba(239,68,68,0.4);"
            "border-radius:6px;padding:9px 18px;font-weight:600;"
        )
        self.ann_delete_btn.setCursor(Qt.PointingHandCursor)
        btn_row.addWidget(self.ann_publish_btn)
        btn_row.addWidget(self.ann_delete_btn)
        btn_row.addStretch()
        self._current_section_layout.insertLayout(self._current_section_layout.count() - 1, btn_row)

        self.ann_status = QLabel("")
        self.ann_status.setWordWrap(True)
        self.ann_status.setStyleSheet("color: #9ca3af; font-size: 12px;")
        self._current_section_layout.insertWidget(self._current_section_layout.count() - 1, self.ann_status)

        # ── actions (ทำงานใน QThread กัน UI ค้าง) ──
        self._ann_thread = None

        def _run_announce_job(job):
            from PySide6.QtCore import QThread, Signal as QSignal
            token = self.ann_token.text().strip()
            text = self.ann_text.toPlainText().strip()
            url = self.ann_url.text().strip()
            ann_type = self.ann_type.currentData()

            if job == "publish" and not text:
                self.ann_status.setText("❌ กรุณาพิมพ์ข้อความประกาศก่อน")
                self.ann_status.setStyleSheet("color:#ef4444;font-size:12px;")
                return

            class _AnnJob(QThread):
                done = QSignal(bool, str)
                def run(self):
                    from announcement import publish_announcement, delete_announcement
                    if job == "publish":
                        ok, msg = publish_announcement(token, text, ann_type, url)
                    else:
                        ok, msg = delete_announcement(token)
                    self.done.emit(ok, msg)

            self.ann_publish_btn.setEnabled(False)
            self.ann_delete_btn.setEnabled(False)
            self.ann_status.setText("⏳ กำลังส่ง...")
            self.ann_status.setStyleSheet("color:#f59e0b;font-size:12px;")

            def _on_done(ok, msg):
                self.ann_publish_btn.setEnabled(True)
                self.ann_delete_btn.setEnabled(True)
                self.ann_status.setText(msg)
                self.ann_status.setStyleSheet(f"color:{'#10b981' if ok else '#ef4444'};font-size:12px;")

            self._ann_thread = _AnnJob()
            self._ann_thread.done.connect(_on_done)
            self._ann_thread.start()

        self.ann_publish_btn.clicked.connect(lambda: _run_announce_job("publish"))
        self.ann_delete_btn.clicked.connect(lambda: _run_announce_job("delete"))

    def _build_supporters_section(self):
        """💚 สนับสนุน — บริจาค + รายชื่อผู้สนับสนุน"""
        # ★ สร้าง section แบบไม่มี header default (จะสร้าง header เอง)
        self._add_section("supporters", "", "")
        layout = self._current_section_layout
        ci = lambda: layout.count() - 1

        # ── Header row: [title] ...stretch... [PromptPay] [TrueMoney] [ส่งหลักฐาน] ──
        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        title_lbl = QLabel("💚 สนับสนุน")
        title_lbl.setStyleSheet("font-size: 20px; font-weight: 700; color: #f59e0b;")
        header_row.addWidget(title_lbl)
        header_row.addStretch()

        # ★ ปุ่มบริจาค + ส่งหลักฐาน อยู่ขวาบนบรรทัดเดียวกับหัวข้อ
        btn_pp = QPushButton("💳 PromptPay")
        btn_pp.setMinimumHeight(32)
        btn_pp.setStyleSheet(
            "QPushButton { background-color: #10b981; color: white; font-weight: 600; "
            "border: none; border-radius: 6px; padding: 6px 16px; }"
            "QPushButton:hover { background-color: #059669; }"
        )
        btn_pp.clicked.connect(lambda: self._show_qr("promptpay_qr.png", "PromptPay"))
        header_row.addWidget(btn_pp)

        btn_tm = QPushButton("💳 True Money")
        btn_tm.setMinimumHeight(32)
        btn_tm.setStyleSheet(
            "QPushButton { background-color: #06b6d4; color: white; font-weight: 600; "
            "border: none; border-radius: 6px; padding: 6px 16px; }"
            "QPushButton:hover { background-color: #0891b2; }"
        )
        btn_tm.clicked.connect(lambda: self._show_qr("truemoney_qr.png", "True Money"))
        header_row.addWidget(btn_tm)

        btn_upload = QPushButton("📤 แนบหลักฐานสนับสนุน")
        btn_upload.setMinimumHeight(32)
        btn_upload.setStyleSheet(
            "QPushButton { background-color: #7c3aed; color: white; font-weight: 600; "
            "border: none; border-radius: 6px; padding: 6px 16px; }"
            "QPushButton:hover { background-color: #6d28d9; }"
        )
        btn_upload.clicked.connect(self._open_supporter_upload)
        header_row.addWidget(btn_upload)
        layout.insertLayout(ci(), header_row)

        # ── รายชื่อผู้สนับสนุน (ดึงจาก API) ──
        # ★ header row: title + reload button
        supporters_header_row = QHBoxLayout()
        supporters_header_row.setSpacing(8)
        supporters_hdr = QLabel("⭐ รายชื่อผู้สนับสนุน")
        supporters_hdr.setStyleSheet("font-size: 15px; font-weight: 700; color: #f59e0b;")
        supporters_header_row.addWidget(supporters_hdr)
        supporters_header_row.addStretch()
        # ★ ปุ่มรีโหลด
        self._supporters_reload_btn = QPushButton("🔄 รีโหลด")
        self._supporters_reload_btn.setCursor(Qt.PointingHandCursor)
        self._supporters_reload_btn.setStyleSheet(
            "QPushButton { color: #06b6d4; font-size: 12px; font-weight: 600; "
            "border: none; background: transparent; padding: 4px 8px; }"
            "QPushButton:hover { color: #0891b2; text-decoration: underline; }"
            "QPushButton:disabled { color: #4b5563; }"
        )
        self._supporters_reload_btn.clicked.connect(self._on_supporters_reload)
        supporters_header_row.addWidget(self._supporters_reload_btn)
        layout.insertLayout(ci(), supporters_header_row)

        # ★ status label ("⏳ กำลังโหลด..." / "✅ N ผู้สนับสนุน" / "❌ error")
        self._supporters_status_label = QLabel("⏳ กำลังรอโหลดข้อมูล...")
        self._supporters_status_label.setStyleSheet("font-size: 13px; color: #9ca3af; margin-bottom: 4px;")
        layout.insertWidget(ci(), self._supporters_status_label)

        # ★ scrollable container สำหรับ list ผู้สนับสนุน
        from PySide6.QtWidgets import QScrollArea
        self._supporters_container = QWidget()
        self._supporters_container_layout = QVBoxLayout(self._supporters_container)
        self._supporters_container_layout.setContentsMargins(0, 0, 0, 0)
        self._supporters_container_layout.setSpacing(0)
        self._supporters_container_layout.addStretch()

        supporters_scroll = QScrollArea()
        supporters_scroll.setWidgetResizable(True)
        supporters_scroll.setWidget(self._supporters_container)
        supporters_scroll.setFrameShape(QScrollArea.NoFrame)
        supporters_scroll.setMinimumHeight(200)
        supporters_scroll.setStyleSheet(
            "QScrollArea { background: transparent; }"
            "QScrollBar:vertical { background: #1f2937; width: 8px; border-radius: 4px; }"
            "QScrollBar::handle:vertical { background: #4b5563; border-radius: 4px; min-height: 30px; }"
            "QScrollBar::handle:vertical:hover { background: #6b7280; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )
        layout.insertWidget(ci(), supporters_scroll)

        # ★ cache + state
        self._supporters_cache = None     # {"ok": ..., "supporters": [...]} ล่าสุด
        self._supporters_loading = False  # flag กัน double-load
        self._supporters_current_page = 0  # pagination (0-indexed)
        self._supporters_per_page = 15     # แสดง 15 รายชื่อต่อหน้า

        # ★ เชื่อมกับ app.py (parent_app = MainWindow ที่ส่งเข้ามาใน __init__):
        #   - รับ cache ล่าสุดจาก parent_app._supporters_cache
        #   - ตั้ง reload callback → parent_app._load_supporters()
        parent_app = getattr(self, 'parent_app', None)
        if parent_app is not None:
            # ★ ส่ง callback ให้ปุ่มรีโหลดเรียก app.py
            if hasattr(parent_app, '_load_supporters'):
                self._supporters_reload_callback = parent_app._load_supporters
            # ★ แสดง cache ถ้ามี (ดึงตอน startup แล้ว)
            parent_cache = getattr(parent_app, '_supporters_cache', None)
            if parent_cache is not None:
                self._populate_supporters_list(parent_cache)
            else:
                # ★ ยังไม่มี cache → trigger fetch ถ้ายังไม่ได้ fetch
                self._supporters_status_label.setText("⏳ กำลังโหลดข้อมูลผู้สนับสนุน...")
                self._supporters_status_label.setStyleSheet("font-size: 13px; color: #06b6d4; margin-bottom: 4px;")
                # ★ trigger fetch ด้วย QThread + Signal (ไม่บล็อก UI + thread-safe)
                self._start_fetch_thread()

    def _on_supporters_reload(self):
        """★ ปุ่มรีโหลด → บอก app.py ให้ดึงใหม่ (emit signal)"""
        # ★ ถ้ามี callback ที่ app.py ตั้งไว้ → เรียก
        if hasattr(self, '_supporters_reload_callback') and self._supporters_reload_callback:
            self._supporters_status_label.setText("⏳ กำลังโหลด...")
            self._supporters_status_label.setStyleSheet("font-size: 13px; color: #06b6d4; margin-bottom: 4px;")
            self._supporters_reload_btn.setEnabled(False)
            self._supporters_reload_callback()
        else:
            # fallback: ดึงด้วย QThread เอง (ถ้าไม่ได้เชื่อมกับ app.py)
            if self._supporters_loading:
                return
            self._supporters_loading = True
            self._supporters_reload_btn.setEnabled(False)
            self._supporters_status_label.setText("⏳ กำลังโหลด...")
            self._supporters_status_label.setStyleSheet("font-size: 13px; color: #06b6d4; margin-bottom: 4px;")
            self._start_fetch_thread()

    def _start_fetch_thread(self):
        """★ ดึง supporters ด้วย QThread + Signal (thread-safe)"""
        from PySide6.QtCore import QThread, Signal

        class _Fetch(QThread):
            done = Signal(dict)
            def run(self):
                try:
                    from supporters_api import fetch_supporters
                    result = fetch_supporters()
                except Exception as e:
                    result = {"ok": False, "error": str(e)}
                self.done.emit(result)

        self._supporters_qthread = _Fetch()
        self._supporters_qthread.done.connect(self._on_supporters_fetched)
        self._supporters_qthread.start()

    def _on_supporters_fetched(self, result: dict):
        """★ slot ที่ทำงานใน main thread หลัง fetch เสร็จ"""
        self._supporters_loading = False
        self._supporters_reload_btn.setEnabled(True)
        self._populate_supporters_list(result)

    def _populate_supporters_list(self, result: dict):
        """★ cache ผลลัพธ์ + render หน้าปัจจุบัน (reset to page 0)

        result: {"ok": True, "supporters": [...]} หรือ {"ok": False, "error": "..."}
        """
        # ★ cache ล่าสุดเสมอ
        self._supporters_cache = result
        self._supporters_current_page = 0  # reset to first page
        self._render_supporters_page()

    def _render_supporters_page(self):
        """★ render หน้าปัจจุบันของตาราง (ใช้ cache ที่มี)"""
        from PySide6.QtWidgets import QFrame
        result = self._supporters_cache
        if result is None:
            return

        # ★ เคลียร์ container เดิม (เก็บ stretch ไว้)
        cl = self._supporters_container_layout
        while cl.count() > 1:  # เก็บ stretch (index สุดท้าย)
            item = cl.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        # ★ error case
        if not result.get("ok"):
            err = result.get("error", "ไม่ทราบสาเหตุ")
            self._supporters_status_label.setText(f"❌ ไม่สามารถดึงข้อมูลได้: {err}")
            self._supporters_status_label.setStyleSheet("font-size: 13px; color: #ef4444; margin-bottom: 4px;")
            # ★ placeholder row
            placeholder = QLabel("ยังไม่มีข้อมูลผู้สนับสนุน\nกด 🔄 รีโหลด เพื่อลองใหม่")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet("font-size: 13px; color: #6b7280; padding: 32px;")
            cl.insertWidget(cl.count() - 1, placeholder)
            return

        supporters = result.get("supporters", [])
        count = len(supporters)

        # ★ empty case
        if count == 0:
            self._supporters_status_label.setText("📋 ยังไม่มีผู้สนับสนุน — คุณสามารถเป็นคนแรกได้!")
            self._supporters_status_label.setStyleSheet("font-size: 13px; color: #9ca3af; margin-bottom: 4px;")
            placeholder = QLabel("💚\nยังไม่มีผู้สนับสนุนในตอนนี้")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet("font-size: 14px; color: #6b7280; padding: 32px;")
            cl.insertWidget(cl.count() - 1, placeholder)
            return

        # ★ success case — ตารางรายชื่อผู้สนับสนุน
        from supporters_api import get_tier, format_amount
        self._supporters_status_label.setText(f"✅ {count} ผู้สนับสนุน")
        self._supporters_status_label.setStyleSheet("font-size: 13px; color: #10b981; margin-bottom: 4px;")

        # ★ โหลดโลโก้แพลตฟอร์มจริงจาก assets/ (cache ใน memory)
        import os
        from PySide6.QtGui import QPixmap
        assets_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "assets")
        PLATFORM_LOGOS = {
            'twitch':  os.path.join(assets_dir, "twitch.png"),
            'youtube': os.path.join(assets_dir, "youtube.png"),
            'kick':    os.path.join(assets_dir, "kick.png"),
            'tiktok':  os.path.join(assets_dir, "tiktok.png"),
            'mylive':  os.path.join(assets_dir, "mylive.png"),
        }

        # ★ table header — ใช้ stretch factor 4:2:3 (name:amount:message)
        #   amount ใช้ ratio 2 + fixed min width 80px → ไม่ชิดขวาเกิน + รองรับยอดยาว
        COL_NAME_STRETCH = 4
        COL_AMOUNT_STRETCH = 2
        COL_MSG_STRETCH = 3

        header = QFrame()
        header.setStyleSheet("QFrame { background: #111827; border: none; border-bottom: 1px solid #334155; }")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 6, 12, 6)
        header_layout.setSpacing(12)
        h_name = QLabel("👤 ชื่อ")
        h_name.setStyleSheet("font-size: 11px; font-weight: 700; color: #6b7280; background: transparent; border: none;")
        header_layout.addWidget(h_name, COL_NAME_STRETCH)
        h_amount = QLabel("💰 จำนวน")
        h_amount.setStyleSheet("font-size: 11px; font-weight: 700; color: #6b7280; background: transparent; border: none;")
        h_amount.setMinimumWidth(80)
        header_layout.addWidget(h_amount, COL_AMOUNT_STRETCH)
        h_msg = QLabel("💬 ข้อความ")
        h_msg.setStyleSheet("font-size: 11px; font-weight: 700; color: #6b7280; background: transparent; border: none;")
        header_layout.addWidget(h_msg, COL_MSG_STRETCH)
        cl.insertWidget(cl.count() - 1, header)

        # ★ pagination — slice เฉพาะหน้าปัจจุบัน
        per_page = self._supporters_per_page
        page = self._supporters_current_page
        start = page * per_page
        end = start + per_page
        page_supporters = supporters[start:end]

        for idx, sup in enumerate(page_supporters):
            if not isinstance(sup, dict):
                continue
            name = str(sup.get("name", "ผู้สนับสนุน")).strip() or "ผู้สนับสนุน"
            amount = sup.get("amount", 0)
            currency = str(sup.get("currency", "THB")).upper()
            date = str(sup.get("date", "")).strip()
            message = str(sup.get("message", "")).strip()
            platform = str(sup.get("platform", "")).strip()
            channel_url = str(sup.get("channel_url", "")).strip()

            tier = get_tier(amount, currency)
            amount_str = format_amount(amount, currency)

            # ★ zebra stripes (สลับสีพื้นหลัง)
            # ★ zebra stripes — ใช้ absolute index (start + idx) เพื่อความต่อเนื่องข้ามหน้า
            abs_idx = start + idx
            bg_color = "#1a1f2e" if abs_idx % 2 == 0 else "#1f2937"

            # ★ table row — ใช้ stretch factor เดียวกับ header (ตำแหน่งตรงกันทุก row)
            row = QFrame()
            row.setStyleSheet(
                f"QFrame {{ background: {bg_color}; border: none; }}"
                f"QFrame:hover {{ background: #2a3447; }}"
            )
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(12, 8, 12, 8)
            row_layout.setSpacing(12)

            # ═══ NAME COLUMN (stretch 3) — container รวม tier + name + platform logo ═══
            name_container = QWidget()
            name_container.setStyleSheet("background: transparent;")
            name_col = QHBoxLayout(name_container)
            name_col.setContentsMargins(0, 0, 0, 0)
            name_col.setSpacing(6)

            tier_lbl = QLabel(tier["icon"])
            tier_lbl.setStyleSheet("font-size: 16px; background: transparent; border: none;")
            tier_lbl.setFixedSize(20, 20)
            tier_lbl.setToolTip(f"{tier['name']} tier")
            name_col.addWidget(tier_lbl)

            name_lbl = QLabel(name)
            name_lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #f3f4f6; background: transparent; border: none;")
            name_col.addWidget(name_lbl)

            # platform logo (clickable → เปิด channel URL) — ใช้ QPushButton เพื่อความน่าเชื่อถือ
            if platform and channel_url and platform in PLATFORM_LOGOS:
                logo_path = PLATFORM_LOGOS[platform]
                if os.path.exists(logo_path):
                    from PySide6.QtGui import QIcon
                    plat_btn = QPushButton()
                    pix = QPixmap(logo_path)
                    if not pix.isNull():
                        plat_btn.setIcon(QIcon(pix.scaled(18, 18, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
                        plat_btn.setIconSize(pix.size().scaled(18, 18, Qt.KeepAspectRatio))
                    plat_btn.setFixedSize(22, 22)
                    plat_btn.setCursor(Qt.PointingHandCursor)
                    plat_btn.setToolTip(f"เปิดช่อง {platform}: {channel_url}")
                    plat_btn.setStyleSheet(
                        "QPushButton { background: transparent; border: none; padding: 0; margin: 0; }"
                        "QPushButton:hover { background: rgba(124, 58, 237, 0.2); border-radius: 4px; }"
                    )
                    _url = channel_url
                    plat_btn.clicked.connect(lambda checked=False, u=_url: self._open_url(u))
                    name_col.addWidget(plat_btn)

            name_col.addStretch()
            row_layout.addWidget(name_container, COL_NAME_STRETCH)

            # ═══ AMOUNT COLUMN (stretch 2) — ชิดซ้ายติด name (ไม่ขวาเกิน) ═══
            amount_lbl = QLabel(amount_str)
            amount_lbl.setStyleSheet("font-size: 13px; font-weight: 700; color: #f59e0b; background: transparent; border: none;")
            amount_lbl.setMinimumWidth(80)
            amount_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            row_layout.addWidget(amount_lbl, COL_AMOUNT_STRETCH)

            # ═══ MESSAGE COLUMN (stretch 2) ═══
            if message:
                msg_lbl = QLabel(f'"{message}"')
                msg_lbl.setStyleSheet("font-size: 12px; color: #9ca3af; font-style: italic; background: transparent; border: none;")
                msg_lbl.setWordWrap(True)
                msg_lbl.setAlignment(Qt.AlignVCenter)
                row_layout.addWidget(msg_lbl, COL_MSG_STRETCH)
            else:
                spacer = QLabel("—")
                spacer.setStyleSheet("font-size: 12px; color: #4b5563; background: transparent; border: none;")
                row_layout.addWidget(spacer, COL_MSG_STRETCH)

            cl.insertWidget(cl.count() - 1, row)

        # ★ pagination controls (ถ้ามีมากกว่า 1 หน้า)
        total_pages = (count + per_page - 1) // per_page  # ceil division
        if total_pages > 1:
            pager = QWidget()
            pager.setStyleSheet("background: transparent;")
            pager_layout = QHBoxLayout(pager)
            pager_layout.setContentsMargins(12, 8, 12, 8)
            pager_layout.setSpacing(6)

            # ★ prev button
            btn_prev = QPushButton("‹ ก่อนหน้า")
            btn_prev.setEnabled(page > 0)
            btn_prev.setCursor(Qt.PointingHandCursor)
            btn_prev.setStyleSheet(
                "QPushButton { background: #334155; color: #e2e8f0; border: none; "
                "border-radius: 6px; padding: 6px 14px; font-size: 12px; font-weight: 600; }"
                "QPushButton:hover { background: #475569; }"
                "QPushButton:disabled { background: #1f2937; color: #4b5563; }"
            )
            _p = page
            btn_prev.clicked.connect(lambda checked=False, p=page: self._supporters_goto_page(p - 1))
            pager_layout.addWidget(btn_prev)

            # ★ page info
            page_lbl = QLabel(f"หน้า {page + 1} / {total_pages}")
            page_lbl.setStyleSheet("color: #9ca3af; font-size: 12px; padding: 0 12px;")
            page_lbl.setAlignment(Qt.AlignCenter)
            pager_layout.addWidget(page_lbl)

            # ★ next button
            btn_next = QPushButton("ถัดไป ›")
            btn_next.setEnabled(page < total_pages - 1)
            btn_next.setCursor(Qt.PointingHandCursor)
            btn_next.setStyleSheet(
                "QPushButton { background: #334155; color: #e2e8f0; border: none; "
                "border-radius: 6px; padding: 6px 14px; font-size: 12px; font-weight: 600; }"
                "QPushButton:hover { background: #475569; }"
                "QPushButton:disabled { background: #1f2937; color: #4b5563; }"
            )
            btn_next.clicked.connect(lambda checked=False, p=page: self._supporters_goto_page(p + 1))
            pager_layout.addWidget(btn_next)

            pager_layout.addStretch()
            cl.insertWidget(cl.count() - 1, pager)

    def _supporters_goto_page(self, page_num):
        """★ เปลี่ยนหน้า — ไม่ต้อง fetch ใหม่ (ใช้ cache)"""
        if page_num < 0:
            return
        self._supporters_current_page = page_num
        self._render_supporters_page()

    def _open_url(self, url):
        """เปิด URL ในเบราว์เซอร์"""
        import webbrowser
        try:
            webbrowser.open(url)
        except Exception as e:
            logger.warning(f"Cannot open URL {url}: {e}")

    def _open_supporter_upload(self):
        """★ เปิด dialog ส่งหลักฐานการสนับสนุน"""
        from ui.dialogs.supporter_upload import SupporterUploadDialog
        api_url = getattr(self.settings, 'supporters_api_url', 'https://men9ch.com/api') if self.settings else "https://men9ch.com/api"
        dlg = SupporterUploadDialog(self, api_url=api_url)
        dlg.exec()

    def _open_supporter_admin(self):
        """★ เปิดหน้า admin ในเบราว์เซอร์ — สำหรับ streamer เข้าไป approve/reject/ban"""
        api_url = getattr(self.settings, 'supporters_api_url', 'https://men9ch.com/api') if self.settings else "https://men9ch.com/api"
        # ★ เปิดหน้า admin.php ในเบราว์เซอร์ (admin จะใส่ token เองบนหน้าเว็บ)
        from supporters_api import open_admin_url
        # ★ ใช้ secret จาก settings (ถ้ามี) หรือเปิดหน้า login ให้ใส่เอง
        admin_secret = getattr(self.settings, 'supporters_admin_secret', '') if self.settings else ""
        open_admin_url(admin_secret, api_url)

    def _show_qr(self, filename, title):
        """แสดง QR popup — ขนาดคำนวณจากเนื้อหาจริง (กัน QR ถูกบีบ)"""
        import os
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QSizePolicy
        from PySide6.QtGui import QPixmap
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        qr_path = os.path.join(base, "assets", filename)
        if not os.path.exists(qr_path):
            QMessageBox.information(
                self, title,
                f"ยังไม่มีไฟล์ QR {filename}\nวางไฟล์ในโฟลเดอร์ assets/ เพื่อแสดง QR"
            )
            return
        popup = QDialog(self)
        popup.setWindowTitle(f"QR {title}")
        popup.setModal(True)
        pop_layout = QVBoxLayout(popup)
        pop_layout.setContentsMargins(24, 24, 24, 16)
        pop_layout.setSpacing(12)
        pix = QPixmap(qr_path)
        if not pix.isNull():
            img_lbl = QLabel()
            img_lbl.setPixmap(pix)
            img_lbl.setAlignment(Qt.AlignCenter)
            # ★ SizePolicy = Fixed → ไม่ถูกบีบ แสดง 100% เสมอ
            img_lbl.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            img_lbl.setFixedSize(pix.size())
            pop_layout.addWidget(img_lbl)
            # ★ title label บน QR
            title_lbl = QLabel(f"💳 {title}")
            title_lbl.setAlignment(Qt.AlignCenter)
            title_lbl.setStyleSheet("font-size: 14px; font-weight: 700; color: #f59e0b; margin-bottom: 4px;")
            pop_layout.insertWidget(0, title_lbl)
            # ★ setFixedSize ตามเนื้อหาจริง (QR + title + button + margins)
            #   เพิ่ม padding generous เพื่อกันบีบ
            total_w = pix.width() + 48
            total_h = pix.height() + 110  # title + button + margins
            popup.setFixedSize(total_w, total_h)
        else:
            pop_layout.addWidget(QLabel(f"(โหลด {filename} ไม่ได้)"))
            popup.resize(300, 150)
        btn_close = QPushButton("ปิด")
        btn_close.setMinimumHeight(36)
        btn_close.clicked.connect(popup.accept)
        pop_layout.addWidget(btn_close)
        popup.exec()

    def _check_update(self):
        """เช็คอัพเดท — รันใน background thread (กัน UI ค้าง) → แสดงผลใน main thread"""
        btn = self.sender()
        if btn:
            btn.setEnabled(False)
            btn.setText("⏳ กำลังเช็ค...")

        # ★ class-level signal สำหรับ cross-thread
        try:
            self._update_result_sig.disconnect()
        except Exception:
            pass
        self._update_result_sig.connect(lambda info: self._check_update_done(info, btn))

        from updater import check_update_async
        check_update_async(lambda info: self._update_result_sig.emit(info))

    def _check_update_done(self, info, btn):
        """slot: เช็คอัพเดทเสร็จ (main thread) → แสดงผล + คืนปุ่ม"""
        if btn:
            btn.setEnabled(True)
            btn.setText("🔄 เช็คอัพเดท")
        # ★ แยก 3 กรณี: error / ไม่มีอัพเดท / มีอัพเดท
        if isinstance(info, dict) and info.get("error"):
            QMessageBox.warning(self, "เช็คอัพเดท", f"⚠️ เช็คอัพเดทไม่สำเร็จ\n\n{info['error']}")
            return
        if not info:
            QMessageBox.information(self, "เช็คอัพเดท", "✅ คุณใช้เวอร์ชั่นล่าสุดอยู่แล้ว")
            return
        # ★ มีอัพเดท → เรียก _show_update_dialog ของ parent_app (เหมือน auto-check)
        #   → ใช้ auto-download (patch) แทนการเปิด browser
        parent_app = getattr(self, 'parent_app', None)
        if parent_app and hasattr(parent_app, '_show_update_dialog'):
            parent_app._show_update_dialog(info)
        else:
            # fallback — dialog แบบเดิม (เปิด browser)
            latest = info.get("latest", "?")
            current = info.get("current", "?")
            changelog = info.get("changelog", "")
            url = info.get("url", "")
            msg = f"🆕 เวอร์ชั่นใหม่พร้อมใช้งาน!\n\nเวอร์ชั่นปัจจุบัน: v{current}\nเวอร์ชั่นล่าสุด: v{latest}\n\n"
            if changelog:
                msg += f"มีอะไรใหม่:\n{changelog}\n\n"
            msg += "ต้องการดาวน์โหลดตอนนี้ไหม?"
            reply = QMessageBox.question(self, "เช็คอัพเดท", msg,
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if reply == QMessageBox.Yes:
                import webbrowser
                webbrowser.open(url or "https://github.com/zepiam/broadcast-playroom-ex/releases/latest")

    # ════════════════════════════════════════════════════════════
    # Load / Save
    # ════════════════════════════════════════════════════════════
    def _on_tw_connect_clicked(self):
        """★ กดปุ่มเชื่อมต่อ Twitch OAuth → เรียก app._on_twitch_oauth_connect"""
        if self._twitch_oauth_connect_handler:
            self.tw_oauth_status.setText("⏳ กำลังเปิดเบราว์เซอร์...")
            self.tw_oauth_status.setStyleSheet("color: #f59e0b; font-size: 12px; border: none;")
            self._twitch_oauth_connect_handler()

    def _on_tw_disconnect_clicked(self):
        """★ กดปุ่มยกเลิกการเชื่อมต่อ → เรียก app._on_twitch_oauth_disconnect"""
        if self._twitch_oauth_disconnect_handler:
            self._twitch_oauth_disconnect_handler()
            # ★ refresh UI ทันที
            self._refresh_twitch_oauth_status()

    # ═══ KICK OAuth (ส่งแชท + Bot + แก้ชื่อห้อง) ═══

    def _on_kc_connect_clicked(self):
        """★ กดปุ่มเชื่อมต่อ KICK OAuth → เรียก app._on_kick_oauth_connect"""
        if self._kick_oauth_connect_handler:
            self.kc_oauth_status.setText("⏳ กำลังเปิดเบราว์เซอร์...")
            self.kc_oauth_status.setStyleSheet("color: #f59e0b; font-size: 12px; border: none;")
            self._kick_oauth_connect_handler()

    def _on_kc_disconnect_clicked(self):
        """★ กดปุ่มยกเลิกการเชื่อมต่อ KICK → เรียก app._on_kick_oauth_disconnect"""
        if self._kick_oauth_disconnect_handler:
            self._kick_oauth_disconnect_handler()
            self._refresh_kick_oauth_status()

    def setup_kick_oauth_handlers(self, connect_handler, disconnect_handler, refresh_callback=None):
        """★ ตั้งค่า handlers สำหรับ KICK OAuth (เรียกจาก app.py)"""
        self._kick_oauth_connect_handler = connect_handler
        self._kick_oauth_disconnect_handler = disconnect_handler
        if refresh_callback:
            self._kick_oauth_refresh = refresh_callback

    def _refresh_kick_oauth_status(self):
        """★ อัปเดตสถานะ KICK OAuth ใน settings dialog"""
        if not self.settings:
            return
        token = getattr(self.settings, 'kick_oauth_token', '') or ''
        username = getattr(self.settings, 'kick_bot_username', '') or ''
        if token and username:
            self.kc_oauth_status.setText(f"✅ เชื่อมต่อแล้ว — ล็อกอิน: <b>{username}</b><br>"
                                         f"<span style='color:#64748b;'>ส่งแชท + Bot + แก้ชื่อห้องได้</span>"
                                         "<br><span style='color:#f59e0b;'>⚠ ล็อกอินนี้ต่ออายุให้เองอัตโนมัติ "
                                         "(หลุดเมื่อถอนสิทธิ์บน KICK เท่านั้น)</span>")
            self.kc_oauth_status.setStyleSheet("color: #10b981; font-size: 12px; border: none;")
            self.btn_kc_connect.setVisible(False)
            self.btn_kc_disconnect.setVisible(True)
            self.btn_kc_bot_settings.setVisible(True)
        else:
            self.kc_oauth_status.setText("❌ ยังไม่ได้เชื่อมต่อ (อ่านแชทได้อย่างเดียว)<br>"
                                         f"<span style='color:#64748b;'>กดเชื่อมต่อเพื่อส่งแชท + ใช้ Bot + แก้ชื่อห้อง</span>")
            self.kc_oauth_status.setStyleSheet("color: #94a3b8; font-size: 12px; border: none;")
            self.btn_kc_connect.setVisible(True)
            self.btn_kc_disconnect.setVisible(False)
            self.btn_kc_bot_settings.setVisible(False)

    def setup_twitch_oauth_handlers(self, connect_handler, disconnect_handler, refresh_callback=None):
        """★ ตั้งค่า handlers สำหรับ Twitch OAuth (เรียกจาก app.py)

        Args:
            connect_handler: callable — เริ่ม OAuth flow
            disconnect_handler: callable — ลบ token
            refresh_callback: callable (optional) — เรียกเมื่อ OAuth เสร็จ (refresh UI)
        """
        self._twitch_oauth_connect_handler = connect_handler
        self._twitch_oauth_disconnect_handler = disconnect_handler
        if refresh_callback:
            self._twitch_oauth_refresh = refresh_callback

    def _goto_chat_bot_section(self):
        """★ เด้งไป section Chat Bot"""
        if "twitch_bot" in self._sections:
            for i in range(self.sidebar.count()):
                item = self.sidebar.item(i)
                if item and item.data(Qt.UserRole) == "twitch_bot":
                    self.sidebar.setCurrentRow(i)
                    break

    def _twitch_expiry_line(self) -> str:
        """★ บรรทัดสีเหลืองนับวันหมดอายุล็อกอิน Twitch"""
        import time, math
        ts = float(getattr(self.settings, 'twitch_token_expiry_ts', 0) or 0)
        if not ts:
            return ""
        days = math.ceil((ts - time.time()) / 86400)
        if days >= 2:
            return (f"<br><span style='color:#f59e0b;'>⚠ การเชื่อมต่อนี้จะหลุดในอีก {days} วัน "
                    f"เมื่อหลุดให้ทำการเชื่อมต่ออีกครั้ง</span>")
        if days >= 1:
            return ("<br><span style='color:#f59e0b;'>⚠ การเชื่อมต่อนี้จะหลุดในอีก 1 วัน "
                    "เมื่อหลุดให้ทำการเชื่อมต่ออีกครั้ง</span>")
        return ("<br><span style='color:#f59e0b;'>⚠ การเชื่อมต่อหมดอายุแล้ว — "
                "กดเชื่อมต่ออีกครั้ง</span>")

    def _refresh_twitch_oauth_status(self):
        """★ อัปเดตสถานะ Twitch OAuth ใน settings dialog"""
        if not self.settings:
            return
        token = getattr(self.settings, 'twitch_oauth_token', '') or ''
        username = getattr(self.settings, 'twitch_bot_username', '') or ''
        if token and username:
            self.tw_oauth_status.setText(f"✅ เชื่อมต่อแล้ว — ล็อกอิน: <b>{username}</b><br>"
                                         f"<span style='color:#64748b;'>ส่งแชท + Bot ได้ — ปิด-เปิด Twitch ใหม่เพื่อใช้งาน</span>"
                                         + self._twitch_expiry_line())
            self.tw_oauth_status.setStyleSheet("color: #10b981; font-size: 12px; border: none;")
            self.btn_tw_connect.setVisible(False)
            self.btn_tw_disconnect.setVisible(True)
            self.btn_tw_bot_settings.setVisible(True)
        else:
            self.tw_oauth_status.setText("❌ ยังไม่ได้เชื่อมต่อ (อ่านแชทได้อย่างเดียว)<br>"
                                         f"<span style='color:#64748b;'>กดเชื่อมต่อเพื่อส่งแชท + ใช้ Bot</span>")
            self.tw_oauth_status.setStyleSheet("color: #94a3b8; font-size: 12px; border: none;")
            self.btn_tw_connect.setVisible(True)
            self.btn_tw_disconnect.setVisible(False)
            self.btn_tw_bot_settings.setVisible(False)

    def _load_values(self):
        """โหลดค่าจาก settings ใส่ใน form"""
        if not self.settings:
            return
        # ★ กัน auto-save ระหว่าง load (setChecked/setText trigger stateChanged/editingFinished)
        self._loading = True
        s = self.settings
        # Platforms
        self.tw_channel.setText(getattr(s, 'twitch_channel', '') or '')
        # ★ Twitch OAuth status
        self._refresh_twitch_oauth_status()
        # ★ Twitch Bot — load enabled + commands + timers
        if hasattr(self, 'bot_enabled_cb'):
            self.bot_enabled_cb.setChecked(getattr(s, 'twitch_bot_enabled', False))
            self.ask_post_result_cb.setChecked(getattr(s, 'ask_post_result', True))
            # ★ per-platform bot toggles
            _bp = getattr(s, 'bot_platforms', {}) or {}
            for key, cb in getattr(self, 'bot_plat_cbs', {}).items():
                cb.setChecked(bool(_bp.get(key, True)))
            # ★ clear old rows ก่อน
            for row in list(getattr(self, '_bot_cmd_rows', [])):
                row.setParent(None)
                row.deleteLater()
            self._bot_cmd_rows = []
            for row in list(getattr(self, '_bot_timer_rows', [])):
                row.setParent(None)
                row.deleteLater()
            self._bot_timer_rows = []
            # ★ add rows จาก settings
            commands = getattr(s, 'twitch_bot_commands', {}) or {}
            for cmd, resp in commands.items():
                self._add_bot_cmd_row(cmd, resp)
            timers = getattr(s, 'twitch_bot_timers', []) or []
            for timer in timers:
                self._add_bot_timer_row(
                    timer.get('text', ''),
                    int(timer.get('interval_min', 10)),
                    int(timer.get('min_chat_count', 0)),
                )
            # ★ bot name
            if hasattr(self, 'bot_name_input'):
                self.bot_name_input.setText(getattr(s, 'twitch_bot_name', 'Baitoei-Bot') or 'Baitoei-Bot')
            # ★ event responses
            if hasattr(self, 'bot_events_cb'):
                self.bot_events_cb.setChecked(getattr(s, 'twitch_bot_events_enabled', True))
                self.bot_ev_sub.setText(getattr(s, 'twitch_bot_event_sub', '') or '')
                self.bot_ev_bits.setText(getattr(s, 'twitch_bot_event_bits', '') or '')
                self.bot_ev_raid.setText(getattr(s, 'twitch_bot_event_raid', '') or '')
                self.bot_ev_follow.setText(getattr(s, 'twitch_bot_event_follow', '') or '')
            # ★ overlay hide bots
            if hasattr(self, 'overlay_hide_bots_cb'):
                self.overlay_hide_bots_cb.setChecked(getattr(s, 'overlay_hide_bots', True))
        self.yt_id.setText(getattr(s, 'youtube_url', '') or '')
        self.ml_url.setText(getattr(s, 'mylive_url', '') or '')
        self.tt_user.setText(getattr(s, 'tiktok_username', '') or getattr(s, 'tiktok_user', '') or '')
        if hasattr(self, 'ann_token'):
            self.ann_token.setText(getattr(s, 'announce_gh_token', '') or '')
        self.kc_channel.setText(getattr(s, 'kick_channel', '') or '')
        # ★ KICK OAuth status
        self._refresh_kick_oauth_status()
        self.auto_reconnect.setChecked(getattr(s, 'auto_reconnect_enabled', True))
        # auto-connect per platform
        self.tw_auto.setChecked(getattr(s, 'auto_connect_twitch', False))
        self.yt_auto.setChecked(getattr(s, 'auto_connect_youtube', False))
        self.ml_auto.setChecked(getattr(s, 'auto_connect_mylive', False))
        self.tt_auto.setChecked(getattr(s, 'auto_connect_tiktok', False))
        self.kc_auto.setChecked(getattr(s, 'auto_connect_kick', False))
        # show per platform
        self.tw_show.setChecked(getattr(s, 'show_twitch', True))
        self.yt_show.setChecked(getattr(s, 'show_youtube', True))
        self.ml_show.setChecked(getattr(s, 'show_mylive', True))
        self.tt_show.setChecked(getattr(s, 'show_tiktok', False))
        self.kc_show.setChecked(getattr(s, 'show_kick', False))
        # playroom
        self.playroom_enabled.setChecked(getattr(s, 'playroom_enabled', False))
        # translate mode
        at_on = getattr(s, 'auto_translate_enabled', False)
        ml_on = getattr(s, 'multilang_enabled', False)
        if at_on:
            self.mode_translate.setChecked(True)
        elif ml_on:
            self.mode_multilang.setChecked(True)
        else:
            self.mode_off.setChecked(True)
        # API key/host — ★ provider=google → clear (ไม่จำเป็น + กัน key ค้างใน form)
        provider = getattr(s, 'auto_translate_provider', 'google')
        if provider == "google":
            self.at_apikey.setText("")
            self.at_host.setText("")
        else:
            self.at_apikey.setText(getattr(s, 'auto_translate_api_key', '') or '')
            self.at_host.setText(getattr(s, 'auto_translate_host', '') or '')
        idx = self.at_provider.findText(provider)
        if idx >= 0: self.at_provider.setCurrentIndex(idx)
        # ★ sync show/hide API row ตาม provider
        self._on_translate_provider_change(provider)
        # translate language list
        enabled_langs = getattr(s, 'auto_translate_langs', ['en', 'ja', 'ko', 'zh', 'vi', 'id'])
        for code, cb in self._lang_checks.items():
            cb.setChecked(code in enabled_langs)
        # multilang language list
        ml_langs = getattr(s, 'multilang_langs', ['en', 'ja', 'ko', 'zh', 'zh-TW', 'fr'])
        for code, cb in self._ml_lang_checks.items():
            cb.setChecked(code in ml_langs)
        # TTS
        self.tts_volume.setValue(getattr(s, 'volume', 100))
        self.tts_rate.setValue(getattr(s, 'rate', 0))
        # ★ TTS engine + voice selectors
        if hasattr(self, 'tts_engine_edge'):
            engine = getattr(s, 'tts_engine', 'edge')
            if engine == 'omnivoice':
                self.tts_engine_omni.setChecked(True)
            else:
                self.tts_engine_edge.setChecked(True)
            self._on_tts_engine_change()
        if hasattr(self, '_theme_thumbs'):
            self._refresh_theme_thumb_selection()
        if hasattr(self, 'edge_voice_combo'):
            ev = getattr(s, 'edge_voice', 'premwadee')
            idx = self.edge_voice_combo.findData(ev)
            if idx >= 0:
                self.edge_voice_combo.setCurrentIndex(idx)
        if hasattr(self, 'omnivoice_voice_combo'):
            ov = getattr(s, 'omnivoice_voice', 'female')
            idx = self.omnivoice_voice_combo.findData(ov)
            if idx >= 0:
                self.omnivoice_voice_combo.setCurrentIndex(idx)
        # ★ Viewer command toggle + cooldown
        if hasattr(self, 'viewer_cmd_enabled'):
            self.viewer_cmd_enabled.setChecked(getattr(s, 'viewer_cmd_enabled', False))
        if hasattr(self, 'viewer_cmd_cooldown'):
            self.viewer_cmd_cooldown.setValue(getattr(s, 'viewer_cmd_cooldown', 5.0))
        # ★ sync backing checkboxes + radio buttons from stored settings
        ra = getattr(s, 'read_author', False)   # ★ default ใหม่ = อ่านแต่ข้อความ
        rm = getattr(s, 'read_message', True)
        self.read_author.setChecked(ra)
        self.read_message.setChecked(rm)
        if hasattr(self, 'read_own_web'):
            self.read_own_web.setChecked(getattr(s, 'read_own_web_messages', True))
        if hasattr(self, 'tts_read_both') and hasattr(self, 'tts_read_message_only'):
            if ra and rm:
                self.tts_read_both.setChecked(True)
            else:
                self.tts_read_message_only.setChecked(True)
        # ★ OBS WebSocket
        if hasattr(self, 'obs_ws_enabled'):
            self.obs_ws_enabled.setChecked(getattr(s, 'obs_ws_enabled', False))
            self.obs_ws_host.setText(getattr(s, 'obs_ws_host', 'localhost'))
            self.obs_ws_port.setValue(int(getattr(s, 'obs_ws_port', 4455)))
            self.obs_ws_password.setText(getattr(s, 'obs_ws_password', ''))
        # ★ secret code daily limit
        if hasattr(self, 'code_limit_spin'):
            self.code_limit_spin.setValue(int(getattr(s, 'secret_code_daily_limit', 0)))
        # ★ ปลด flag — auto-save ทำงานปกติหลัง load เสร็จ
        self._loading = False

    def _collect_values(self):
        """อ่านค่าจากทุก widget → เขียนลง settings (ใช้ getattr กัน crash ถ้า widget ไม่มี)"""
        if not self.settings:
            return
        s = self.settings
        # Platforms
        if hasattr(self, 'tw_channel'):
            s.twitch_channel = self.tw_channel.text().strip()
            s.youtube_url = self.yt_id.text().strip()
            s.mylive_url = self.ml_url.text().strip()
            s.tiktok_username = self.tt_user.text().strip()  # ★ ต้องเป็นชื่อเดียวกับ settings.py field (persist จริง)
            if hasattr(self, 'ann_token'):
                s.announce_gh_token = self.ann_token.text().strip()
            s.kick_channel = self.kc_channel.text().strip()
            s.auto_reconnect_enabled = self.auto_reconnect.isChecked()
            s.auto_connect_twitch = self.tw_auto.isChecked()
            s.auto_connect_youtube = self.yt_auto.isChecked()
            s.auto_connect_mylive = self.ml_auto.isChecked()
            s.auto_connect_tiktok = self.tt_auto.isChecked()
            s.auto_connect_kick = self.kc_auto.isChecked()
            s.show_twitch = self.tw_show.isChecked()
            s.show_youtube = self.yt_show.isChecked()
            s.show_mylive = self.ml_show.isChecked()
            s.show_tiktok = self.tt_show.isChecked()
            s.show_kick = self.kc_show.isChecked()
        # playroom
        if hasattr(self, 'playroom_enabled'):
            s.playroom_enabled = self.playroom_enabled.isChecked()
        # ★ playroom triggers (อ่านจาก inline editor — ข้าม container layout ที่ลบไปแล้ว)
        if hasattr(self, '_playroom_triggers_container'):
            from PySide6.QtWidgets import QTableWidgetItem
            triggers = []
            for i in range(self._playroom_triggers_layout.count()):
                item = self._playroom_triggers_layout.itemAt(i)
                row = item.widget() if item else None
                if row and hasattr(row, 'code_entry'):
                    code = row.code_entry.text().strip()
                    if not code:
                        continue
                    clips = []
                    clips_table = row.clips_table
                    for cr in range(clips_table.rowCount()):
                        name_item = clips_table.item(cr, 0)
                        path_item = clips_table.item(cr, 1)
                        weight_item = clips_table.item(cr, 2)
                        if name_item and path_item:
                            clips.append({
                                'name': name_item.text().strip(),
                                'path': path_item.text().strip(),
                                'weight': int(weight_item.text()) if weight_item and weight_item.text().isdigit() else 50,
                            })
                    orig = getattr(row, '_orig_trigger', {})
                    triggers.append({
                        'code': code,
                        'daily_limit': row.limit_spin.value(),
                        'clips': clips,
                        'widget_ids': orig.get('widget_ids', []),
                    })
            s.playroom_triggers = triggers
            # sync pipeline config live
            if self.parent_app and hasattr(self.parent_app, 'pipeline') and self.parent_app.pipeline:
                try:
                    self.parent_app.pipeline.config.playroom_triggers = list(triggers)
                except Exception:
                    pass
        # translate mode
        if hasattr(self, 'mode_translate'):
            s.auto_translate_enabled = self.mode_translate.isChecked()
            s.multilang_enabled = self.mode_multilang.isChecked()
        if hasattr(self, 'at_provider'):
            s.auto_translate_provider = self.at_provider.currentText()
        # ★ provider=google → clear API key + host (ไม่จำเป็นต้องใช้ + กัน key ค้าง)
        if s.auto_translate_provider == "google":
            s.auto_translate_api_key = ""
            s.auto_translate_host = ""
        else:
            if hasattr(self, 'at_apikey'):
                s.auto_translate_api_key = self.at_apikey.text().strip()
            if hasattr(self, 'at_host'):
                s.auto_translate_host = self.at_host.text().strip()
        if hasattr(self, '_lang_checks'):
            s.auto_translate_langs = [c for c, cb in self._lang_checks.items() if cb.isChecked()]
        if hasattr(self, '_ml_lang_checks'):
            s.multilang_langs = [c for c, cb in self._ml_lang_checks.items() if cb.isChecked()]
        # banned words
        s.banned_words = []
        if hasattr(self, 'ng_table'):
            for r in range(self.ng_table.rowCount()):
                item = self.ng_table.item(r, 0)
                if item and item.text().strip():
                    s.banned_words.append(item.text().strip())
        # ★ replace words — อ่านจาก _replace_data (truth source — ทุก page ไม่ใช่แค่หน้าที่แสดง)
        if hasattr(self, '_replace_data'):
            words = {}
            for e in self._replace_data:
                src = e.get('src', '').strip()
                if not src:
                    continue
                words[src] = {'display': e.get('display', ''), 'read': e.get('read', '')}
            s.replace_words = words
            # ★ sync ไป pipeline ทันที (กัน TTS ยังอ่านคำเก่า)
            if self.parent_app and hasattr(self.parent_app, 'pipeline') and self.parent_app.pipeline:
                try:
                    self.parent_app.pipeline.set_filter(s.to_text_filter())
                except Exception:
                    pass
        # blocked users
        if hasattr(self, 'block_table'):
            # ★ save เป็น list[dict] format (ตรงกับ app.py + text_filter)
            #   {name: str, hide_overlay: bool} — hide_overlay=True → block_all
            blocked = []
            for r in range(self.block_table.rowCount()):
                item = self.block_table.item(r, 0)
                if not item:
                    continue
                name = item.text().strip()
                if not name:
                    continue
                # อ่าน combo (block_all / block_tts)
                combo = self.block_table.cellWidget(r, 1)
                block_type = combo.currentData() if combo else "block_all"
                hide_overlay = (block_type != "block_tts")  # block_tts = ยังแสดงใน overlay
                blocked.append({"name": name, "hide_overlay": hide_overlay})
            s.blocked_users = blocked
            # ★ sync ไป pipeline ทันที (กัน TTS ยังอ่าน user ที่เพิ่ง block)
            if self.parent_app and hasattr(self.parent_app, 'pipeline') and self.parent_app.pipeline:
                try:
                    self.parent_app.pipeline.set_filter(s.to_text_filter())
                except Exception:
                    pass
        if hasattr(self, 'max_msg_length'):
            s.max_msg_length = self.max_msg_length.value()
        # TTS
        if hasattr(self, 'tts_volume'):
            s.volume = self.tts_volume.value()
            s.rate = self.tts_rate.value()
            # ★ drive read_author / read_message from radio buttons
            if hasattr(self, 'tts_read_both') and hasattr(self, 'tts_read_message_only'):
                if self.tts_read_both.isChecked():
                    s.read_author = True
                    s.read_message = True
                elif self.tts_read_message_only.isChecked():
                    s.read_author = False
                    s.read_message = True
            if hasattr(self, 'read_own_web'):
                s.read_own_web_messages = self.read_own_web.isChecked()
            else:
                s.read_author = self.read_author.isChecked()
                s.read_message = self.read_message.isChecked()
        # ★ TTS engine + voice (edge-tts / OmniVoice)
        if hasattr(self, 'tts_engine_edge'):
            if self.tts_engine_omni.isChecked():
                s.tts_engine = "omnivoice"
            else:
                s.tts_engine = "edge"
        # ★ ui_theme ไม่ผ่านตรงนี้แล้ว — เขียน+apply ทันทีตอนคลิก thumbnail (_on_theme_thumb_clicked)
        if hasattr(self, 'edge_voice_combo'):
            s.edge_voice = self.edge_voice_combo.currentData() or "premwadee"
        if hasattr(self, 'omnivoice_voice_combo'):
            s.omnivoice_voice = self.omnivoice_voice_combo.currentData() or "female"
        # ★ Viewer command toggle + cooldown
        if hasattr(self, 'viewer_cmd_enabled'):
            s.viewer_cmd_enabled = self.viewer_cmd_enabled.isChecked()
        if hasattr(self, 'viewer_cmd_cooldown'):
            s.viewer_cmd_cooldown = float(self.viewer_cmd_cooldown.value())
        # Translate detailed (ถ้ามี)
        if hasattr(self, 'at_enabled'):
            s.auto_translate_enabled = self.at_enabled.isChecked()
        if hasattr(self, 'ml_enabled'):
            s.multilang_enabled = self.ml_enabled.isChecked()
        if hasattr(self, 'mv_enabled'):
            s.mixed_voice_enabled = self.mv_enabled.isChecked()
        # Overlay+ hotkeys (อ่านจาก binder button — เก็บใน _hotkey)
        if hasattr(self, 'mo_hk_toggle_entry'):
            s.more_overlay_hotkey = (getattr(self.mo_hk_toggle_entry, '_hotkey', '') or 'ctrl+shift+m').strip().lower()
            s.more_overlay_hotkey_edit = (getattr(self.mo_hk_edit_entry, '_hotkey', '') or 'ctrl+shift+n').strip().lower()
        # ★ OBS WebSocket auto-refresh
        if hasattr(self, 'obs_ws_enabled'):
            s.obs_ws_enabled = self.obs_ws_enabled.isChecked()
            s.obs_ws_host = self.obs_ws_host.text().strip() or 'localhost'
            s.obs_ws_port = int(self.obs_ws_port.value())
            s.obs_ws_password = self.obs_ws_password.text()
        # ★ secret code daily limit
        if hasattr(self, 'code_limit_spin'):
            s.secret_code_daily_limit = int(self.code_limit_spin.value())
        # ★ Twitch Bot config (commands + timers + enabled)
        if hasattr(self, 'bot_enabled_cb'):
            s.twitch_bot_enabled = self.bot_enabled_cb.isChecked()
            s.ask_post_result = self.ask_post_result_cb.isChecked()
            # ★ per-platform bot toggles
            if hasattr(self, 'bot_plat_cbs'):
                s.bot_platforms = {k: cb.isChecked() for k, cb in self.bot_plat_cbs.items()}
            # ★ collect commands
            commands = {}
            for row in getattr(self, '_bot_cmd_rows', []):
                rlayout = row.layout()
                if rlayout and rlayout.count() >= 3:
                    cmd_w = rlayout.itemAt(0).widget()
                    resp_w = rlayout.itemAt(2).widget()
                    cmd_text = cmd_w.text().strip()
                    resp_text = resp_w.text().strip()
                    if cmd_text and resp_text:
                        # ★ ปรับให้ขึ้นต้นด้วย ! (ถ้า user ไม่ใส่)
                        if not cmd_text.startswith('!'):
                            cmd_text = '!' + cmd_text
                        commands[cmd_text.lower()] = resp_text
            s.twitch_bot_commands = commands
            # ★ collect timers
            timers = []
            for row in getattr(self, '_bot_timer_rows', []):
                text_w = getattr(row, '_text_input', None)
                mode_w = getattr(row, '_mode_combo', None)
                value_w = getattr(row, '_value_input', None)
                if text_w and mode_w and value_w:
                    text_val = text_w.text().strip()
                    mode = mode_w.currentData() or "interval"
                    try:
                        val = max(1, int(value_w.text().strip() or '10'))
                    except ValueError:
                        val = 10
                    if mode == "chat_count":
                        # ★ chat count mode → min_chat_count = val, interval = 0 (ไม่จำกัดเวลา)
                        interval_val = 0
                        chat_val = val
                    else:
                        # ★ interval mode → interval = val, chat = 0 (ไม่จำกัด chat)
                        interval_val = val
                        chat_val = 0
                    if text_val:
                        timers.append({"text": text_val, "interval_min": interval_val, "min_chat_count": chat_val})
            s.twitch_bot_timers = timers
            # ★ bot name
            if hasattr(self, 'bot_name_input'):
                s.twitch_bot_name = self.bot_name_input.text().strip() or 'Baitoei-Bot'
            # ★ event responses
            if hasattr(self, 'bot_events_cb'):
                s.twitch_bot_events_enabled = self.bot_events_cb.isChecked()
                s.twitch_bot_event_sub = self.bot_ev_sub.text().strip()
                s.twitch_bot_event_bits = self.bot_ev_bits.text().strip()
                s.twitch_bot_event_raid = self.bot_ev_raid.text().strip()
                s.twitch_bot_event_follow = self.bot_ev_follow.text().strip()
            # ★ overlay hide bots
            if hasattr(self, 'overlay_hide_bots_cb'):
                s.overlay_hide_bots = self.overlay_hide_bots_cb.isChecked()

    def _auto_save(self):
        """auto-save: collect + save + emit signal (ไม่ปิด dialog)"""
        if not self.settings:
            return
        # ★ กัน auto-save ระหว่าง _load_values (กัน setChecked trigger stateChanged → เขียนทับค่าจริง)
        if getattr(self, '_loading', False):
            return
        self._collect_values()
        try:
            from settings import save_settings
            save_settings(self.settings)
            self.settings_changed.emit()
        except Exception as e:
            logger.error(f"auto_save failed: {e}")

    def _save(self):
        """บันทึกครั้งสุดท้าย + ปิด"""
        self._auto_save()
        self.accept()
