"""settings.py — Settings dialog (sidebar layout, modern style)

เปลี่ยนจาก tab แบบเดิม → sidebar layout (ซ้ายเลือกหมวด → ขวาแสดง content)
"""
import logging
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QWidget, QFrame, QLabel, QPushButton, QLineEdit, QCheckBox,
    QVBoxLayout, QHBoxLayout, QGridLayout, QSplitter, QScrollArea,
    QComboBox, QSlider, QSpinBox, QGroupBox, QListWidget, QListWidgetItem,
    QTextEdit, QTabWidget, QMessageBox,
)

logger = logging.getLogger("settings")


class SettingsDialog(QDialog):
    """Settings dialog — sidebar layout (modern flat design)"""

    settings_changed = Signal()  # emit เมื่อ settings เปลี่ยน (บันทึกแล้ว)

    def __init__(self, parent_app):
        super().__init__(parent_app if isinstance(parent_app, QWidget) else None)
        self.parent_app = parent_app
        self.settings = getattr(parent_app, 'settings', None)
        self.setWindowTitle("⚙ ตั้งค่า")
        self.setGeometry(150, 150, 900, 680)
        self.setMinimumSize(800, 600)
        self.setModal(True)
        self._build_ui()
        self._load_values()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ★ Left sidebar (category list)
        self.sidebar = QListWidget()
        self.sidebar.setFixedWidth(200)
        self.sidebar.setObjectName("SettingsSidebar")
        self.sidebar.setStyleSheet("""
            QListWidget {
                background-color: #060912;
                border: none;
                border-right: 1px solid #2a2f45;
                outline: none;
                padding: 8px 0;
            }
            QListWidget::item {
                padding: 12px 16px;
                color: #9ca3af;
                border: none;
            }
            QListWidget::item:selected {
                background-color: #131726;
                color: #7c3aed;
                border-left: 3px solid #7c3aed;
            }
            QListWidget::item:hover {
                background-color: #131726;
            }
        """)
        categories = [
            ("🔌 แพลตฟอร์ม", "platforms"),
            ("🔊 TTS", "tts"),
            ("🌐 การแปล", "translate"),
            ("🎮 Playroom", "playroom"),
            ("🎨 Canvas", "canvas"),
            ("🔔 แจ้งเตือน", "notifications"),
            ("🚫 NG-Replace", "ngreplace"),
            ("🛡️ Spam & Block", "spam"),
            ("ℹ️ เกี่ยวกับ", "about"),
        ]
        for label, key in categories:
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, key)
            self.sidebar.addItem(item)
        self.sidebar.setCurrentRow(0)
        self.sidebar.currentRowChanged.connect(self._on_category_change)
        layout.addWidget(self.sidebar)

        # ★ Right content area (scrollable)
        self.content_scroll = QScrollArea()
        self.content_scroll.setWidgetResizable(True)
        self.content_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.content_container = QWidget()
        self.content_layout = QVBoxLayout(self.content_container)
        self.content_layout.setContentsMargins(20, 20, 20, 20)
        self.content_layout.setSpacing(12)
        self.content_scroll.setWidget(self.content_container)
        layout.addWidget(self.content_scroll, 1)

        # ★ Build all sections (hidden by default)
        self._sections = {}
        self._build_platforms_section()
        self._build_tts_section()
        self._build_translate_section()
        self._build_playroom_section()
        self._build_canvas_section()
        self._build_notifications_section()
        self._build_ngreplace_section()
        self._build_spam_section()
        self._build_about_section()

        # ★ Show first section
        self._show_section("platforms")

        # ★ Bottom bar (Save + Cancel)
        bottom = QFrame()
        bottom.setFixedHeight(50)
        bottom.setStyleSheet("background-color: #131726; border-top: 1px solid #2a2f45;")
        bottom_layout = QHBoxLayout(bottom)
        bottom_layout.setContentsMargins(20, 0, 20, 0)
        bottom_layout.addStretch()
        btn_save = QPushButton("💾 บันทึก")
        btn_save.setObjectName("Primary")
        btn_save.setFixedWidth(100)
        btn_save.clicked.connect(self._save)
        btn_cancel = QPushButton("ยกเลิก")
        btn_cancel.setFixedWidth(80)
        btn_cancel.clicked.connect(self.reject)
        bottom_layout.addWidget(btn_cancel)
        bottom_layout.addWidget(btn_save)

        # Wrap layout to add bottom bar
        wrapper = QVBoxLayout()
        wrapper.setContentsMargins(0, 0, 0, 0)
        wrapper.setSpacing(0)
        # move existing layout into wrapper
        existing_widget = QWidget()
        existing_widget.setLayout(layout)
        wrapper.addWidget(existing_widget, 1)
        wrapper.addWidget(bottom)
        self.setLayout(wrapper)

    def _on_category_change(self, row):
        if row < 0:
            return
        item = self.sidebar.item(row)
        key = item.data(Qt.UserRole)
        self._show_section(key)

    def _show_section(self, key):
        """แสดง section ที่เลือก (ซ่อนอันอื่น)"""
        for k, widget in self._sections.items():
            widget.setVisible(k == key)

    def _add_section(self, key, title, description=""):
        """สร้าง section ใหม่ + เพิ่มเข้า layout"""
        widget = QWidget()
        wlayout = QVBoxLayout(widget)
        wlayout.setContentsMargins(0, 0, 0, 0)
        wlayout.setSpacing(8)
        if title:
            lbl = QLabel(title)
            lbl.setObjectName("Heading")
            lbl.setStyleSheet("font-size: 18px; font-weight: 700; color: #f59e0b;")
            wlayout.addWidget(lbl)
        if description:
            desc = QLabel(description)
            desc.setObjectName("Dim")
            desc.setWordWrap(True)
            wlayout.addWidget(desc)
        wlayout.addStretch()
        self.content_layout.addWidget(widget)
        self._sections[key] = widget
        self._current_section_layout = wlayout
        return widget

    def _add_row(self, label, widget):
        """เพิ่ม row (label + widget) เข้า section ปัจจุบัน"""
        row = QHBoxLayout()
        lbl = QLabel(label)
        lbl.setMinimumWidth(140)
        lbl.setStyleSheet("color: #e5e7eb;")
        row.addWidget(lbl)
        row.addWidget(widget, 1)
        # insert ก่อน stretch
        self._current_section_layout.insertLayout(
            self._current_section_layout.count() - 1, row
        )

    # ════════════════════════════════════════════════════════════
    # Section builders
    # ════════════════════════════════════════════════════════════
    def _build_platforms_section(self):
        w = self._add_section("platforms", "🔌 แพลตฟอร์ม", "ตั้งค่า channel/URL สำหรับแต่ละแพลตฟอร์ม")
        # Twitch
        tw_row = QHBoxLayout()
        self.tw_channel = QLineEdit()
        self.tw_channel.setPlaceholderText("เช่น men9ch")
        tw_row.addWidget(QLabel("Twitch:"), 0)
        tw_row.addWidget(self.tw_channel, 1)
        self.tw_auto = QCheckBox("เชื่อมอัตโนมัติ")
        tw_row.addWidget(self.tw_auto)
        self._current_section_layout.insertLayout(self._current_section_layout.count() - 1, tw_row)
        # YouTube
        yt_row = QHBoxLayout()
        self.yt_id = QLineEdit()
        self.yt_id.setPlaceholderText("Video ID หรือ URL")
        yt_row.addWidget(QLabel("YouTube:"), 0)
        yt_row.addWidget(self.yt_id, 1)
        self.yt_auto = QCheckBox("เชื่อมอัตโนมัติ")
        yt_row.addWidget(self.yt_auto)
        self._current_section_layout.insertLayout(self._current_section_layout.count() - 1, yt_row)
        # MyLive
        ml_row = QHBoxLayout()
        self.ml_url = QLineEdit()
        self.ml_url.setPlaceholderText("https://mylive.in.th/streams/XXXXX")
        ml_row.addWidget(QLabel("MyLive:"), 0)
        ml_row.addWidget(self.ml_url, 1)
        self.ml_auto = QCheckBox("เชื่อมอัตโนมัติ")
        ml_row.addWidget(self.ml_auto)
        self._current_section_layout.insertLayout(self._current_section_layout.count() - 1, ml_row)
        # TikTok
        tt_row = QHBoxLayout()
        self.tt_user = QLineEdit()
        self.tt_user.setPlaceholderText("username")
        tt_row.addWidget(QLabel("TikTok:"), 0)
        tt_row.addWidget(self.tt_user, 1)
        self.tt_auto = QCheckBox("เชื่อมอัตโนมัติ")
        tt_row.addWidget(self.tt_auto)
        self._current_section_layout.insertLayout(self._current_section_layout.count() - 1, tt_row)
        # KICK
        kc_row = QHBoxLayout()
        self.kc_channel = QLineEdit()
        self.kc_channel.setPlaceholderText("channel")
        kc_row.addWidget(QLabel("KICK:"), 0)
        kc_row.addWidget(self.kc_channel, 1)
        self.kc_auto = QCheckBox("เชื่อมอัตโนมัติ")
        kc_row.addWidget(self.kc_auto)
        self._current_section_layout.insertLayout(self._current_section_layout.count() - 1, kc_row)
        # Auto-reconnect
        self.auto_reconnect = QCheckBox("เชื่อมต่อใหม่อัตโนมัติเมื่อหลุด")
        self._current_section_layout.insertWidget(
            self._current_section_layout.count() - 1, self.auto_reconnect
        )

    def _build_tts_section(self):
        self._add_section("tts", "🔊 Text to Speech", "ปรับเสียง TTS")
        # Volume
        self.tts_volume = QSlider(Qt.Horizontal)
        self.tts_volume.setRange(0, 100)
        self._add_row("Volume:", self.tts_volume)
        # Rate
        self.tts_rate = QSlider(Qt.Horizontal)
        self.tts_rate.setRange(-50, 50)
        self._add_row("Rate:", self.tts_rate)
        # Read author
        self.read_author = QCheckBox("อ่านชื่อผู้ส่ง")
        self._current_section_layout.insertWidget(
            self._current_section_layout.count() - 1, self.read_author
        )
        self.read_message = QCheckBox("อ่านข้อความ")
        self._current_section_layout.insertWidget(
            self._current_section_layout.count() - 1, self.read_message
        )

    def _build_translate_section(self):
        self._add_section("translate", "🌐 การแปลภาษา + หลายภาษา", "เลือกโหมด: แปลเป็นไทย หรือ อ่านหลายภาษา")
        from PySide6.QtWidgets import QRadioButton, QButtonGroup, QGridLayout

        # ★ โหมดเลือก (radio buttons)
        mode_label = QLabel("เลือกโหมด:")
        mode_label.setStyleSheet("font-weight: 600; color: #f59e0b;")
        self._current_section_layout.insertWidget(
            self._current_section_layout.count() - 1, mode_label
        )
        self.mode_translate = QRadioButton("🌐 แปลเป็นไทย (แปลข้อความต่างประเทศ → TTS อ่านไทย)")
        self.mode_multilang = QRadioButton("🎤 อ่านหลายภาษา (ตรวจจับภาษา → เลือกเสียงที่เหมาะสม)")
        self.mode_off = QRadioButton("❌ ปิด (อ่านไทยอย่างเดียว)")
        self.mode_off.setChecked(True)

        mode_group = QButtonGroup(self)
        mode_group.addButton(self.mode_translate)
        mode_group.addButton(self.mode_multilang)
        mode_group.addButton(self.mode_off)
        # ★ เก็กว่าเป็น exclusive → ไม่ต้อง setExclusive (default = True)

        self.mode_translate.toggled.connect(self._on_translate_mode_change)
        self.mode_multilang.toggled.connect(self._on_translate_mode_change)

        self._current_section_layout.insertWidget(
            self._current_section_layout.count() - 1, self.mode_translate
        )
        self._current_section_layout.insertWidget(
            self._current_section_layout.count() - 1, self.mode_multilang
        )
        self._current_section_layout.insertWidget(
            self._current_section_layout.count() - 1, self.mode_off
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
        # API key
        self.at_apikey = QLineEdit()
        self.at_apikey.setPlaceholderText("API Key (DeepL/DeepSeek)")
        self.at_apikey.setEchoMode(QLineEdit.Password)
        ts_layout.addWidget(QLabel("API Key:"))
        ts_layout.addWidget(self.at_apikey)
        # host
        self.at_host = QLineEdit()
        self.at_host.setPlaceholderText("Host (ว่าง = default)")
        ts_layout.addWidget(QLabel("Host:"))
        ts_layout.addWidget(self.at_host)
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
        self._current_section_layout.insertWidget(
            self._current_section_layout.count() - 1, self._translate_settings
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
        self._current_section_layout.insertWidget(
            self._current_section_layout.count() - 1, self._multilang_settings
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
        self._current_section_layout.insertWidget(
            self._current_section_layout.count() - 1, container
        )
        return container

    def _build_playroom_section(self):
        self._add_section("playroom", "🎮 Playroom", "ตั้งค่า Playroom triggers + clips")
        # ★ open trigger editor button
        btn_edit = QPushButton("🎮 จัดการ Triggers")
        btn_edit.setObjectName("Primary")
        btn_edit.setMinimumHeight(36)
        def _open_triggers():
            from ui.dialogs.playroom_trigger import PlayroomTriggerDialog
            dlg = PlayroomTriggerDialog(self.parent_app)
            dlg.exec()
        btn_edit.clicked.connect(_open_triggers)
        self._current_section_layout.insertWidget(
            self._current_section_layout.count() - 1, btn_edit
        )
        # ★ show current triggers count
        triggers = getattr(self.settings, 'playroom_triggers', []) or []
        info = QLabel(f"📋 มี {len(triggers)} triggers ตั้งไว้")
        info.setObjectName("Dim")
        self._current_section_layout.insertWidget(
            self._current_section_layout.count() - 1, info
        )
        # ★ enable/disable playroom
        self.playroom_enabled = QCheckBox("เปิดใช้งาน Playroom")
        self._current_section_layout.insertWidget(
            self._current_section_layout.count() - 1, self.playroom_enabled
        )

    def _build_canvas_section(self):
        self._add_section("canvas", "🎨 Canvas Composer", "ตั้งค่า Overlay Composer")
        self.composer_port = QSpinBox()
        self.composer_port.setRange(8000, 9999)
        self.composer_port.setValue(8808)
        self._add_row("Port:", self.composer_port)
        btn_open = QPushButton("🌐 เปิด Composer")
        btn_open.setObjectName("Primary")
        btn_open.clicked.connect(lambda: self.parent_app._open_composer() if hasattr(self.parent_app, '_open_composer') else None)
        self._current_section_layout.insertWidget(
            self._current_section_layout.count() - 1, btn_open
        )

    def _build_notifications_section(self):
        self._add_section("notifications", "🔔 แจ้งเตือน", "เสียง + TTS สำหรับ events")
        events = [
            ("sub", "⭐ Sub"), ("bits", "💎 Bits"), ("raid", "🚀 Raid"),
            ("donate", "💰 Donate"), ("follow", "❤️ Follow"), ("share", "📢 Share"),
        ]
        self.notif_checks = {}
        for key, label in events:
            cb = QCheckBox(label)
            self.notif_checks[key] = cb
            self._current_section_layout.insertWidget(
                self._current_section_layout.count() - 1, cb
            )

    def _build_ngreplace_section(self):
        self._add_section("ngreplace", "🚫 NG-Replace", "คำต้องห้าม + คำแทนที่ (3 ฟิลด์)")
        # ★ open editor button
        btn_edit = QPushButton("🚫 จัดการคำต้องห้าม (Replace)")
        btn_edit.setObjectName("Primary")
        btn_edit.setMinimumHeight(36)
        def _open_ng():
            from ui.dialogs.ngreplace import NGReplaceDialog
            dlg = NGReplaceDialog(self.parent_app)
            dlg.exec()
        btn_edit.clicked.connect(_open_ng)
        self._current_section_layout.insertWidget(
            self._current_section_layout.count() - 1, btn_edit
        )
        # ★ show count
        words = getattr(self.settings, 'replace_words', {}) or {}
        info = QLabel(f"📋 มี {len(words)} คำแทนที่")
        info.setObjectName("Dim")
        self._current_section_layout.insertWidget(
            self._current_section_layout.count() - 1, info
        )
        # ★ NG words (พิมพ์ + enter → ลงรายการ)
        ng_label = QLabel("🚫 คำต้องห้าม (พิมพ์แล้วกด Enter):")
        ng_label.setObjectName("Section")
        self._current_section_layout.insertWidget(
            self._current_section_layout.count() - 1, ng_label
        )
        self.ng_input = QLineEdit()
        self.ng_input.setPlaceholderText("พิมพ์คำที่ต้องการห้าม แล้วกด Enter...")
        self.ng_input.returnPressed.connect(self._add_ng_word)
        self._current_section_layout.insertWidget(
            self._current_section_layout.count() - 1, self.ng_input
        )
        # ★ NG word list (tag-style)
        from PySide6.QtWidgets import QGridLayout
        self._ng_words_widget = QWidget()
        self._ng_words_layout = QGridLayout(self._ng_words_widget)
        self._ng_words_layout.setContentsMargins(0, 0, 0, 0)
        self._ng_words_layout.setSpacing(4)
        self._ng_chips = []
        self._current_section_layout.insertWidget(
            self._current_section_layout.count() - 1, self._ng_words_widget
        )
        # load existing
        banned = getattr(self.settings, 'banned_words', []) or []
        for w in banned:
            self._add_ng_chip(w)

    def _add_ng_word(self):
        """เพิ่มคำต้องห้ามจาก input"""
        word = self.ng_input.text().strip()
        if not word:
            return
        self.ng_input.clear()
        # check duplicate
        existing = [c.text() for c in self._ng_chips]
        if word in existing:
            return
        self._add_ng_chip(word)

    def _add_ng_chip(self, word):
        """เพิ่ม tag chip สำหรับคำต้องห้าม"""
        from PySide6.QtWidgets import QFrame
        chip = QPushButton(f"{word} ✕")
        chip.setStyleSheet("""
            QPushButton {
                background-color: #ef4444;
                color: white;
                border: none;
                border-radius: 10px;
                padding: 4px 10px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover { background-color: #dc2626; }
        """)
        chip.setCursor(Qt.PointingHandCursor)
        chip.clicked.connect(lambda _, c=chip, w=word: self._remove_ng_chip(c, w))
        chip.text_val = word
        count = len(self._ng_chips)
        self._ng_words_layout.addWidget(chip, count // 3, count % 3)
        self._ng_chips.append(chip)

    def _remove_ng_chip(self, chip, word):
        """ลบ tag chip"""
        chip.deleteLater()
        self._ng_chips.remove(chip)
        # re-layout remaining
        for i, c in enumerate(self._ng_chips):
            self._ng_words_layout.removeWidget(c)
            self._ng_words_layout.addWidget(c, i // 3, i % 3)

    def _build_spam_section(self):
        self._add_section("spam", "🛡️ Spam & Block", "บล็อกผู้ใช้ + จำกัด rate + ตั้งค่า anti-spam")
        # ★ open user manager
        btn_users = QPushButton("👤 จัดการผู้ใช้ (User Manager)")
        btn_users.setObjectName("Primary")
        btn_users.setMinimumHeight(36)
        def _open_um():
            from ui.dialogs.user_manager import UserManagerDialog
            dlg = UserManagerDialog(self.parent_app)
            dlg.exec()
        btn_users.clicked.connect(_open_um)
        self._current_section_layout.insertWidget(
            self._current_section_layout.count() - 1, btn_users
        )
        # ★ block user input (พิมพ์ชื่อ + Enter)
        block_label = QLabel("🚫 บล็อกผู้ใช้ (พิมพ์ชื่อแล้วกด Enter):")
        block_label.setObjectName("Section")
        self._current_section_layout.insertWidget(
            self._current_section_layout.count() - 1, block_label
        )
        self.block_input = QLineEdit()
        self.block_input.setPlaceholderText("พิมพ์ชื่อผู้ใช้ที่ต้องการบล็อก แล้วกด Enter...")
        self.block_input.returnPressed.connect(self._add_blocked_user)
        self._current_section_layout.insertWidget(
            self._current_section_layout.count() - 1, self.block_input
        )
        # ★ blocked users table
        from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView, QComboBox
        self.block_table = QTableWidget(0, 2)
        self.block_table.setHorizontalHeaderLabels(["ชื่อผู้ใช้", "ประเภทการบล็อก"])
        self.block_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.block_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.block_table.setColumnWidth(1, 180)
        self.block_table.setMinimumHeight(120)
        self.block_table.setStyleSheet("""
            QTableWidget { background: transparent; border: 1px solid #2a2f45; border-radius: 4px; }
            QTableWidget::item { padding: 4px; }
            QHeaderView::section { background: #131726; color: #9ca3af; border: none; padding: 6px; }
        """)
        self._current_section_layout.insertWidget(
            self._current_section_layout.count() - 1, self.block_table
        )
        # ★ delete blocked user button
        btn_unblock = QPushButton("🗑 ลบที่เลือก")
        btn_unblock.clicked.connect(self._remove_blocked_user)
        self._current_section_layout.insertWidget(
            self._current_section_layout.count() - 1, btn_unblock
        )
        # ★ max message length
        max_len_label = QLabel("ความยาวข้อความสูงสุด:")
        max_len_label.setObjectName("Dim")
        self._current_section_layout.insertWidget(
            self._current_section_layout.count() - 1, max_len_label
        )
        self.max_msg_length = QSpinBox()
        self.max_msg_length.setRange(0, 10000)
        self.max_msg_length.setValue(getattr(self.settings, 'max_msg_length', 500))
        self.max_msg_length.setSpecialValueText("ไม่จำกัด")
        self._current_section_layout.insertWidget(
            self._current_section_layout.count() - 1, self.max_msg_length
        )
        # ★ load existing blocked users
        blocked = getattr(self.settings, 'blocked_users', []) or []
        for u in blocked:
            self._add_blocked_row(u, "block_all")

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
        """เพิ่ม row ใน block table"""
        from PySide6.QtWidgets import QComboBox
        row = self.block_table.rowCount()
        self.block_table.insertRow(row)
        self.block_table.setItem(row, 0, QTableWidgetItem(name))
        combo = QComboBox()
        combo.addItem("🚫 บล็อกทุกอย่าง", "block_all")
        combo.addItem("🔇 บล็อก TTS เท่านั้น", "block_tts")
        combo.setCurrentIndex(0 if block_type == "block_all" else 1)
        self.block_table.setCellWidget(row, 1, combo)

    def _remove_blocked_user(self):
        """ลบผู้ใช้ที่เลือกจาก block table"""
        rows = set()
        for item in self.block_table.selectedItems():
            rows.add(item.row())
        for r in sorted(rows, reverse=True):
            self.block_table.removeRow(r)

    def _build_about_section(self):
        self._add_section("about", "ℹ️ เกี่ยวกับ", "")
        info = QLabel(
            "<b>Broadcast Playroom</b> v2.0.0-dev<br><br>"
            "TTS livestreaming program (edge-tts + RVC)<br><br>"
            "สร้างโดย MeN9CH<br>"
            "GitHub: <a href='https://github.com/zepiam/broadcast-playroom'>zepiam/broadcast-playroom</a>"
        )
        info.setOpenExternalLinks(True)
        info.setWordWrap(True)
        info.setStyleSheet("font-size: 14px; color: #e5e7eb;")
        self._current_section_layout.insertWidget(
            self._current_section_layout.count() - 1, info
        )

    # ════════════════════════════════════════════════════════════
    # Load / Save
    # ════════════════════════════════════════════════════════════
    def _load_values(self):
        """โหลดค่าจาก settings ใส่ใน form"""
        if not self.settings:
            return
        s = self.settings
        # Platforms
        self.tw_channel.setText(getattr(s, 'twitch_channel', '') or '')
        self.yt_id.setText(getattr(s, 'youtube_video_id', '') or '')
        self.ml_url.setText(getattr(s, 'mylive_url', '') or '')
        self.tt_user.setText(getattr(s, 'tiktok_user', '') or '')
        self.kc_channel.setText(getattr(s, 'kick_channel', '') or '')
        self.auto_reconnect.setChecked(getattr(s, 'auto_reconnect_enabled', True))
        # auto-connect per platform
        self.tw_auto.setChecked(getattr(s, 'auto_connect_twitch', False))
        self.yt_auto.setChecked(getattr(s, 'auto_connect_youtube', False))
        self.ml_auto.setChecked(getattr(s, 'auto_connect_mylive', False))
        self.tt_auto.setChecked(getattr(s, 'auto_connect_tiktok', False))
        self.kc_auto.setChecked(getattr(s, 'auto_connect_kick', False))
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
        # API key/host
        self.at_apikey.setText(getattr(s, 'auto_translate_api_key', '') or '')
        self.at_host.setText(getattr(s, 'auto_translate_host', '') or '')
        provider = getattr(s, 'auto_translate_provider', 'google')
        idx = self.at_provider.findText(provider)
        if idx >= 0: self.at_provider.setCurrentIndex(idx)
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
        self.read_author.setChecked(getattr(s, 'read_author', True))
        self.read_message.setChecked(getattr(s, 'read_message', True))

    def _save(self):
        """บันทึกค่าจาก form ลง settings"""
        if not self.settings:
            self.accept()
            return
        s = self.settings
        # Platforms
        s.twitch_channel = self.tw_channel.text().strip()
        s.youtube_video_id = self.yt_id.text().strip()
        s.mylive_url = self.ml_url.text().strip()
        s.tiktok_user = self.tt_user.text().strip()
        s.kick_channel = self.kc_channel.text().strip()
        s.auto_reconnect_enabled = self.auto_reconnect.isChecked()
        # auto-connect per platform
        s.auto_connect_twitch = self.tw_auto.isChecked()
        s.auto_connect_youtube = self.yt_auto.isChecked()
        s.auto_connect_mylive = self.ml_auto.isChecked()
        s.auto_connect_tiktok = self.tt_auto.isChecked()
        s.auto_connect_kick = self.kc_auto.isChecked()
        # playroom
        s.playroom_enabled = self.playroom_enabled.isChecked()
        # translate mode
        s.auto_translate_enabled = self.mode_translate.isChecked()
        s.multilang_enabled = self.mode_multilang.isChecked()
        s.auto_translate_provider = self.at_provider.currentText()
        s.auto_translate_api_key = self.at_apikey.text().strip()
        s.auto_translate_host = self.at_host.text().strip()
        s.auto_translate_langs = [c for c, cb in self._lang_checks.items() if cb.isChecked()]
        s.multilang_langs = [c for c, cb in self._ml_lang_checks.items() if cb.isChecked()]
        # banned words + blocked users
        s.banned_words = [c.text_val for c in self._ng_chips] if hasattr(self, '_ng_chips') else []
        blocked_text = self.blocked_users.text().strip() if hasattr(self, 'blocked_users') else ''
        # ★ อ่านจาก block_table
        blocked = []
        for r in range(self.block_table.rowCount()):
            item = self.block_table.item(r, 0)
            if item:
                blocked.append(item.text().strip())
        s.blocked_users = blocked
        s.max_msg_length = self.max_msg_length.value()
        # TTS
        s.volume = self.tts_volume.value()
        s.rate = self.tts_rate.value()
        s.read_author = self.read_author.isChecked()
        s.read_message = self.read_message.isChecked()
        # Translate
        s.auto_translate_enabled = self.at_enabled.isChecked()
        s.auto_translate_provider = self.at_provider.currentText()
        s.auto_translate_api_key = self.at_apikey.text().strip()
        s.auto_translate_host = self.at_host.text().strip()
        s.multilang_enabled = self.ml_enabled.isChecked()
        s.mixed_voice_enabled = self.mv_enabled.isChecked()
        # language list
        s.auto_translate_langs = [code for code, cb in self._lang_checks.items() if cb.isChecked()]
        # Save
        try:
            from settings import save_settings
            save_settings(s)
            self.settings_changed.emit()
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
        self.accept()
