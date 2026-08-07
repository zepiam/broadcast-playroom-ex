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
        self.tw_channel = QLineEdit()
        self.tw_channel.setPlaceholderText("เช่น men9ch")
        self._add_row("Twitch Channel:", self.tw_channel)
        # YouTube
        self.yt_id = QLineEdit()
        self.yt_id.setPlaceholderText("Video ID หรือ URL")
        self._add_row("YouTube:", self.yt_id)
        # MyLive
        self.ml_url = QLineEdit()
        self.ml_url.setPlaceholderText("https://mylive.in.th/streams/XXXXX")
        self._add_row("MyLive URL:", self.ml_url)
        # TikTok
        self.tt_user = QLineEdit()
        self.tt_user.setPlaceholderText("username")
        self._add_row("TikTok:", self.tt_user)
        # KICK
        self.kc_channel = QLineEdit()
        self.kc_channel.setPlaceholderText("channel")
        self._add_row("KICK:", self.kc_channel)
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
        self._add_section("translate", "🌐 การแปลภาษา", "แปลข้อความต่างประเทศเป็นไทย")
        self.at_enabled = QCheckBox("เปิดการแปลอัตโนมัติ")
        self._current_section_layout.insertWidget(
            self._current_section_layout.count() - 1, self.at_enabled
        )
        self.at_provider = QComboBox()
        self.at_provider.addItems(["Google (ฟรี)", "DeepL", "DeepSeek"])
        self._add_row("ผู้ให้บริการ:", self.at_provider)

    def _build_playroom_section(self):
        self._add_section("playroom", "🎮 Playroom", "ตั้งค่า Playroom triggers")
        info = QLabel("ตั้งค่า trigger / เพิ่ม clip / ปรับ weight ได้ที่นี่ (เร็วๆ นี้)")
        info.setObjectName("Dim")
        info.setWordWrap(True)
        self._current_section_layout.insertWidget(
            self._current_section_layout.count() - 1, info
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
        self._add_section("ngreplace", "🚫 NG-Replace", "คำต้องห้าม + คำแทนที่")
        info = QLabel("จัดการคำต้องห้ามและคำแทนที่ (เร็วๆ นี้)")
        info.setObjectName("Dim")
        self._current_section_layout.insertWidget(
            self._current_section_layout.count() - 1, info
        )

    def _build_spam_section(self):
        self._add_section("spam", "🛡️ Spam & Block", "บล็อกผู้ใช้ + คำต้องห้าม")
        info = QLabel("บล็อกผู้ใช้ + คำต้องห้าม (เร็วๆ นี้)")
        info.setObjectName("Dim")
        self._current_section_layout.insertWidget(
            self._current_section_layout.count() - 1, info
        )

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
        # TTS
        self.tts_volume.setValue(getattr(s, 'volume', 100))
        self.tts_rate.setValue(getattr(s, 'rate', 0))
        self.read_author.setChecked(getattr(s, 'read_author', True))
        self.read_message.setChecked(getattr(s, 'read_message', True))
        # Translate
        self.at_enabled.setChecked(getattr(s, 'auto_translate_enabled', False))

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
        # TTS
        s.volume = self.tts_volume.value()
        s.rate = self.tts_rate.value()
        s.read_author = self.read_author.isChecked()
        s.read_message = self.read_message.isChecked()
        # Translate
        s.auto_translate_enabled = self.at_enabled.isChecked()
        # Save
        try:
            from settings import save_settings
            save_settings(s)
            self.settings_changed.emit()
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
        self.accept()
