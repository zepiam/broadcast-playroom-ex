"""settings.py — Settings dialog (sidebar layout, modern style)

เปลี่ยนจาก tab แบบเดิม → sidebar layout (ซ้ายเลือกหมวด → ขวาแสดง content)
"""
import logging
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QDialog, QWidget, QFrame, QLabel, QPushButton, QLineEdit, QCheckBox,
    QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea,
    QComboBox, QSlider, QSpinBox, QListWidget, QListWidgetItem,
    QMessageBox, QStackedWidget, QSizePolicy,
    QButtonGroup, QRadioButton,
    QTableWidget, QTableWidgetItem,
)

logger = logging.getLogger("settings")


class SettingsDialog(QDialog):
    """Settings dialog — sidebar layout (modern flat design)"""

    settings_changed = Signal()  # emit เมื่อ settings เปลี่ยน (บันทึกแล้ว)
    _obs_test_sig = Signal(str, object)  # OBS test result from background thread

    def __init__(self, parent_app):
        super().__init__(parent_app if isinstance(parent_app, QWidget) else None)
        self.parent_app = parent_app
        self.settings = getattr(parent_app, 'settings', None)
        self.setWindowTitle("⚙ ตั้งค่า")
        self.setGeometry(150, 110, 980, 720)
        self.setMinimumSize(880, 640)
        self.setModal(True)
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
        QTimer.singleShot(0, _force_refresh)

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
            ("🔌 OBS WebSocket", "obs_ws"),
            ("🔔 แจ้งเตือน", "notifications"),
            ("🚫 NG Words", "ng"),
            ("🔄 Replace", "replace"),
            ("🚫 Blocklist & Spam", "block"),
            ("🪟 Overlay+", "overlay_plus"),
            ("ℹ️ เกี่ยวกับ", "about"),
        ]
        for label, key in categories:
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, key)
            self.sidebar.addItem(item)
        self.sidebar.setCurrentRow(0)
        self.sidebar.currentRowChanged.connect(self._on_category_change)
        body_layout.addWidget(self.sidebar)

        # ★ Middle: settings content area (scrollable) — เต็มพื้นที่
        self.content_scroll = QScrollArea()
        self.content_scroll.setWidgetResizable(True)
        self.content_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.content_stack = QStackedWidget()
        self.content_stack.setMinimumWidth(640)
        self.content_stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.content_scroll.setWidget(self.content_stack)
        body_layout.addWidget(self.content_scroll, 1)

        outer.addWidget(body, 1)

        # ★ Build all sections (แต่ละ section = page ใน stack)
        self._sections = {}
        self._build_platforms_section()
        self._build_tts_section()
        self._build_translate_section()
        self._build_playroom_section()
        self._build_canvas_section()
        self._build_obs_ws_section()
        self._build_notifications_section()
        self._build_ng_section()
        self._build_replace_section()
        self._build_block_section()
        self._build_overlay_plus_section()
        self._build_about_section()

        # ★ Show first section
        self._show_section("platforms")

        # ★ Bottom bar (ปุ่มปิดอย่างเดียว — auto-save ทำงาน live)
        bottom = QFrame()
        bottom.setFixedHeight(50)
        bottom.setStyleSheet("background-color: #131726; border-top: 1px solid #2a2f45;")
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
                      'obs_ws_host', 'obs_ws_password']:
            w = getattr(self, attr, None)
            if w and hasattr(w, 'editingFinished'):
                w.editingFinished.connect(self._auto_save)
        # QCheckBox → stateChanged
        for attr in ['auto_reconnect', 'tw_auto', 'yt_auto', 'ml_auto', 'tt_auto', 'kc_auto',
                      'tw_show', 'yt_show', 'ml_show', 'tt_show', 'kc_show',
                      'playroom_enabled', 'mode_translate', 'mode_multilang',
                      'at_enabled', 'ml_enabled', 'mv_enabled',
                      'read_author', 'read_message',
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
        """แสดง section ที่เลือก (QStackedWidget — แสดงทีละอัน)"""
        widget = self._sections.get(key)
        if widget:
            self.content_stack.setCurrentWidget(widget)

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
            lbl.setStyleSheet("font-size: 20px; font-weight: 700; color: #f59e0b;")
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
        # YouTube
        self.yt_id = QLineEdit()
        self.yt_id.setPlaceholderText("Video ID หรือ URL")
        _platform_row("YouTube:", self.yt_id, 'yt_auto', 'yt_show')
        # MyLive
        self.ml_url = QLineEdit()
        self.ml_url.setPlaceholderText("https://mylive.in.th/streams/XXXXX")
        _platform_row("MyLive:", self.ml_url, 'ml_auto', 'ml_show')
        # TikTok
        self.tt_user = QLineEdit()
        self.tt_user.setPlaceholderText("username")
        _platform_row("TikTok:", self.tt_user, 'tt_auto', 'tt_show')
        # KICK
        self.kc_channel = QLineEdit()
        self.kc_channel.setPlaceholderText("channel")
        _platform_row("KICK:", self.kc_channel, 'kc_auto', 'kc_show')
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
        self.tts_read_both.setChecked(True)
        layout.insertWidget(ci(), self.tts_read_both)
        self.tts_read_message_only = QRadioButton("อ่านแต่ข้อความเท่านั้น")
        layout.insertWidget(ci(), self.tts_read_message_only)
        self.tts_read_group = QButtonGroup(self)
        self.tts_read_group.addButton(self.tts_read_both)
        self.tts_read_group.addButton(self.tts_read_message_only)
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

    def _build_translate_section(self):
        self._add_section("translate", "🌐 การแปลภาษา + หลายภาษา", "เลือกโหมด: แปลเป็นไทย หรือ อ่านหลายภาษา")
        from PySide6.QtWidgets import QRadioButton, QButtonGroup, QGridLayout

        # ★ โหมดเลือก (radio buttons)
        mode_label = QLabel("เลือกโหมด:")
        mode_label.setStyleSheet("font-weight: 600; color: #f59e0b;")
        self._current_section_layout.insertWidget(self._current_section_layout.count() - 1,  mode_label
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

        self._current_section_layout.insertWidget(self._current_section_layout.count() - 1,  self.mode_translate
        )
        self._current_section_layout.insertWidget(self._current_section_layout.count() - 1,  self.mode_multilang
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
        clips_table.setMinimumHeight(70)
        clips_table.setMaximumHeight(140)
        dl.addWidget(clips_table)

        for clip in clips:
            if isinstance(clip, dict):
                r = clips_table.rowCount()
                clips_table.insertRow(r)
                clips_table.setItem(r, 0, QTableWidgetItem(clip.get('name', '')))
                clips_table.setItem(r, 1, QTableWidgetItem(clip.get('path', '')))
                clips_table.setItem(r, 2, QTableWidgetItem(str(clip.get('weight', 50))))

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

    def _delete_playroom_clip(self, table):
        """ลบ clip ที่เลือก"""
        rows = set()
        for item in table.selectedItems():
            rows.add(item.row())
        for r in sorted(rows, reverse=True):
            table.removeRow(r)

    def _build_canvas_section(self):
        self._add_section("canvas", "🎨 Canvas Composer", "ตั้งค่า Overlay Composer")
        self.composer_port = QSpinBox()
        self.composer_port.setRange(8000, 9999)
        self.composer_port.setValue(8808)
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
        """
        self._add_section(
            "obs_ws", "🔌 OBS WebSocket",
            "Refresh browser source อัตโนมัติตอนเปิดโปรแกรม "
            "(แก้ปัญหา OBS เปิดก่อน → overlay ค้างหน้าเก่า)"
        )
        # ★ เปิด/ปิด
        self.obs_ws_enabled = QCheckBox("เปิดใช้งาน auto-refresh")
        self.obs_ws_enabled.setStyleSheet("font-size: 14px; font-weight: 600;")
        self._current_section_layout.insertWidget(
            self._current_section_layout.count() - 1, self.obs_ws_enabled
        )
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
            "★ ใช้ร่วมกับ OBS Browser Source ที่ URL ชี้ overlay/composer ของเรา"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #9ca3af; font-size: 12px; margin-top: 8px;")
        self._current_section_layout.insertWidget(
            self._current_section_layout.count() - 1, hint
        )

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

        # ═══ Top bar: [⬇️ โหลดจากคลัง] [🔍 search] ... [count] ═══
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)
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
            ver_text = "v2.0.0"

        # ── header: [🎮 title] ...stretch... [version] [เช็คอัพเดท] ──
        header = QHBoxLayout()
        header.setSpacing(8)
        icon_lbl = QLabel("🎮")
        icon_lbl.setStyleSheet("font-size: 26px; font-weight: 700;")
        title_lbl = QLabel("Broadcast Playroom")
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
        sub = QLabel("อ่านแชทสดทุกแพลตฟอร์มด้วยเสียง AI")
        sub.setStyleSheet("font-size: 13px; color: #9ca3af; margin-bottom: 4px;")
        layout.insertWidget(ci(), sub)

        # ── ข้อความอธิบาย (แบ่งเป็น paragraphs) ──
        paragraphs = [
            ("โปรแกรมนี้ถูกออกแบบมาให้แสดงข้อมูลแชทการถ่ายทอดสดจากหลายแพลตฟอร์ม "
             "นำมารวมอยู่ในหน้าเดียวได้ และมีระบบอ่านออกเสียงแชท Text to Speech "
             "เพื่อให้ผู้สตรีมสามารถทำการสตรีมได้อย่างลื่นไหล โดยไม่จำเป็นต้องมองอีกจอเลย "
             "แค่ฟังก็สามารถตอบกลับผู้ชมได้ทันที เหมาะกับผู้ที่ไม่ชอบมองจอที่สอง หรือมีเพียงจอเดียว", None),

            ("จุดเด่นหลักของโปรแกรมคือมี Text to Speech ที่ใช้ Neural Voice "
             "ของ Microsoft Azure ซึ่งเป็นระบบอ่านออกเสียงที่อ่านภาษาไทยชัดและแม่นยำที่สุดในตอนนี้ "
             "เราได้นำมาใช้พัฒนาโปรแกรมนี้ รวมถึงใช้ระบบ RVC ในการแปลงเสียงให้น่าฟังยิ่งขึ้น", None),

            ("ระบบเสียง RVC ที่ถูกนำมาใช้นั้น เป็นการนำเสียงที่ Neural Voice มาแปลงเสียงซ้ำอีกครั้ง "
             "โดยพื้นฐานเสียงที่ใช้แปลงเป็น RVC นั้นเป็นเสียงที่ใช้ AI Learning เสียงจากตัวละครยอดนิยมต่างๆมาอีกที", None),

            ("⚠️ สิ่งที่ควรทราบไว้ก่อนใช้โปรแกรมนี้", "#f59e0b"),

            ("การใช้ RVC นั้นจำเป็นจะต้องใช้การ์ดจอที่รองรับ CUDA ซึ่งมีแค่บนการ์ดจอซีรี่ย์ RTX ทุกรุ่น "
             "และ GTX มีเพียงบางรุ่น ขนาดของโปรแกรมที่รองรับ RVC นั้นจะมีขนาดใหญ่มาก 4GB+ เป็นอย่างต่ำ "
             "และยังไม่รวมเสียง RVC ที่โหลดมาใช้เพิ่มเติม สาเหตุที่โปรแกรมใหญ่นั้น "
             "เกิดจากไฟล์ของ CUDA ล้วนๆ ไม่ใช่ตัวหลักของโปรแกรมนี้เลย "
             "และเราไม่สามารถลดขนาดไฟล์ให้ต่ำกว่านี้ได้แล้ว", None),

            ("ผู้ที่ไม่ได้ใช้การ์ดจอ RTX/GTX จะไม่แนะนำให้ใช้ RVC เพราะว่าจะทำการประมวลเสียง TTS นานมากๆ "
             "แต่หากก็ยังใช้เสียง Neural Voice ของ Microsoft Azure ก็จะยังใช้งานได้ตามเดิม "
             "ผู้ใดที่ไม่ได้ใช้การ์ดจอของ RTX/GTX เราแนะนำให้โหลดเวอร์ชั่น Lite มาใช้จะดีกว่า "
             "ขนาดจะเล็กกว่ามากๆ (300MB) โดยระบบภายในเหมือนกันหมด "
             "มีเพียงแค่ไม่รองรับ RVC เท่านั้นเอง", None),
        ]
        for text, color in paragraphs:
            lbl = QLabel(text)
            lbl.setWordWrap(True)
            lbl.setAlignment(Qt.AlignLeft)
            if color:
                lbl.setStyleSheet(f"font-size: 13px; font-weight: 700; color: {color}; margin-top: 8px;")
            else:
                lbl.setStyleSheet("font-size: 13px; color: #e5e7eb;")
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

        # ── บริจาค ──
        donate_hdr = QLabel("💚 บริจาคช่วยเหลือ สนับสนุน")
        donate_hdr.setStyleSheet("font-size: 14px; font-weight: 700; color: #f59e0b; margin-top: 8px;")
        layout.insertWidget(ci(), donate_hdr)
        donate_desc = QLabel("ขอบคุณสำหรับผู้สนับสนุนมากๆครับ")
        donate_desc.setStyleSheet("font-size: 13px; color: #9ca3af;")
        layout.insertWidget(ci(), donate_desc)

        donate_row = QHBoxLayout()
        donate_row.setSpacing(8)
        btn_pp = QPushButton("💳 PromptPay")
        btn_pp.setMinimumHeight(32)
        btn_pp.setStyleSheet(
            "QPushButton { background-color: #10b981; color: white; font-weight: 600; "
            "border: none; border-radius: 6px; padding: 6px 16px; }"
            "QPushButton:hover { background-color: #059669; }"
        )
        btn_pp.clicked.connect(lambda: self._show_qr("promptpay_qr.png", "PromptPay"))
        btn_tm = QPushButton("💳 True Money")
        btn_tm.setMinimumHeight(32)
        btn_tm.setStyleSheet(
            "QPushButton { background-color: #06b6d4; color: white; font-weight: 600; "
            "border: none; border-radius: 6px; padding: 6px 16px; }"
            "QPushButton:hover { background-color: #0891b2; }"
        )
        btn_tm.clicked.connect(lambda: self._show_qr("truemoney_qr.png", "True Money"))
        donate_row.addWidget(btn_pp)
        donate_row.addWidget(btn_tm)
        donate_row.addStretch()
        layout.insertLayout(ci(), donate_row)

    def _open_url(self, url):
        """เปิด URL ในเบราว์เซอร์"""
        import webbrowser
        try:
            webbrowser.open(url)
        except Exception:
            pass

    def _show_qr(self, filename, title):
        """แสดง QR popup (ถ้ามีไฟล์ภาพใน assets/)"""
        import os
        from PySide6.QtWidgets import QDialog, QVBoxLayout
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
        pop_layout.setContentsMargins(20, 20, 20, 12)
        pix = QPixmap(qr_path)
        if not pix.isNull():
            img_lbl = QLabel()
            img_lbl.setPixmap(pix)
            img_lbl.setAlignment(Qt.AlignCenter)
            pop_layout.addWidget(img_lbl)
            popup.resize(pix.width() + 40, pix.height() + 60)
        else:
            pop_layout.addWidget(QLabel(f"(โหลด {filename} ไม่ได้)"))
        btn_close = QPushButton("ปิด")
        btn_close.clicked.connect(popup.accept)
        pop_layout.addWidget(btn_close)
        popup.exec()

    def _check_update(self):
        """เช็คอัพเดท — รันใน background thread (กัน UI ค้าง) → แสดงผลใน main thread"""
        btn = self.sender()
        if btn:
            btn.setEnabled(False)
            btn.setText("⏳ กำลังเช็ค...")

        def _bg():
            try:
                from updater import check_for_update
                info = check_for_update()
            except Exception as e:
                info = {"error": str(e)}
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self._check_update_done(info, btn))

        import threading
        threading.Thread(target=_bg, name="CheckUpdate", daemon=True).start()

    def _check_update_done(self, info, btn):
        """slot: เช็คอัพเดทเสร็จ (main thread) → แสดงผล + คืนปุ่ม"""
        if btn:
            btn.setEnabled(True)
            btn.setText("🔄 เช็คอัพเดท")
        if not info:
            QMessageBox.information(self, "เช็คอัพเดท", "✅ คุณใช้เวอร์ชั่นล่าสุดอยู่แล้ว")
            return
        if info.get("error"):
            QMessageBox.warning(self, "เช็คอัพเดท", f"❌ เช็คไม่สำเร็จ\n\n{info['error']}")
            return
        latest = info.get("latest", "?")
        current = info.get("current", "?")
        changelog = info.get("changelog", "")
        bt = info.get("build_type", "")
        bt_label = "Lite" if bt == "lite" else "Full"
        msg = f"🆕 เวอร์ชั่นใหม่พร้อมใช้งาน!\n\n"
        msg += f"เวอร์ชั่นปัจจุบัน: v{current} ({bt_label})\n"
        msg += f"เวอร์ชั่นล่าสุด: v{latest}\n\n"
        if changelog:
            msg += f"มีอะไรใหม่:\n{changelog}"
        QMessageBox.information(self, "เช็คอัพเดท", msg)

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
        ra = getattr(s, 'read_author', True)
        rm = getattr(s, 'read_message', True)
        self.read_author.setChecked(ra)
        self.read_message.setChecked(rm)
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

    def _collect_values(self):
        """อ่านค่าจากทุก widget → เขียนลง settings (ใช้ getattr กัน crash ถ้า widget ไม่มี)"""
        if not self.settings:
            return
        s = self.settings
        # Platforms
        if hasattr(self, 'tw_channel'):
            s.twitch_channel = self.tw_channel.text().strip()
            s.youtube_video_id = self.yt_id.text().strip()
            s.mylive_url = self.ml_url.text().strip()
            s.tiktok_user = self.tt_user.text().strip()
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
            else:
                s.read_author = self.read_author.isChecked()
                s.read_message = self.read_message.isChecked()
        # ★ TTS engine + voice (edge-tts / OmniVoice)
        if hasattr(self, 'tts_engine_edge'):
            if self.tts_engine_omni.isChecked():
                s.tts_engine = "omnivoice"
            else:
                s.tts_engine = "edge"
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

    def _auto_save(self):
        """auto-save: collect + save + emit signal (ไม่ปิด dialog)"""
        if not self.settings:
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
