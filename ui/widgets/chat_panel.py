"""chat_panel.py — Chat feed panel (QScrollArea + custom rows)"""
from PySide6.QtCore import Qt, Signal, QSize, QTimer
from PySide6.QtWidgets import (
    QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QScrollArea,
    QWidget, QSizePolicy, QMenu, QWidgetAction, QSlider, QLineEdit, QCheckBox,
)
import ui.theme as theme  # ★ อ้าง theme.COLOR_X สดตอนสร้าง widget (ตามธีมที่เลือกไว้จริง)
from ui.widgets.chat_row import ChatRow


from ui.widgets.chat_row import ChatRow


class ChatPanel(QFrame):
    """Chat feed — scrollable list of ChatRow"""

    popout_requested = Signal()  # emit เมื่อกดปุ่ม popout
    clear_requested = Signal()   # emit เมื่อกด clear
    block_user_requested = Signal(str)  # emit author for blocking
    author_clicked = Signal(str)  # emit author name for profile/modal
    settings_clicked = Signal()  # emit เมื่อกด gear → Live Chat Settings
    code_mute_toggled = Signal(bool)  # emit True = muted (ปิดเสียงโค้ดลับ)
    send_requested = Signal(str, str, bool)  # ★ emit (text, platforms_json, read_tts) — JSON string กัน Qt signal issue
    ask_toggled = Signal()                    # ★ ปุ่ม ASK — toggle แผงโพล
    connect_bot_requested = Signal()  # ★ emit เมื่อกดปุ่ม "เชื่อมต่อแชทบอท"
    bot_toggle_requested = Signal(bool)  # ★ emit เมื่อ toggle Enable/Disable Chat Bot
    bot_platforms_changed = Signal(dict)  # ★ emit {platform: bool} เมื่อติ๊กเมนูเร็ว
    bot_settings_requested = Signal()  # ★ emit เมื่อกดเฟือง → ไปหน้า Chat Bot settings

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ChatPanel")
        self._build_ui()
        self._rows = []

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ★ Header
        header = QFrame()
        header.setFixedHeight(36)
        header.setStyleSheet(f"background-color: {theme.COLOR_CARD}; border-bottom: 1px solid {theme.COLOR_BORDER};")
        hlayout = QHBoxLayout(header)
        hlayout.setContentsMargins(12, 0, 8, 0)
        hlayout.setSpacing(6)

        # ═══ LEFT: title + viewer count (clickable to hide) ═══
        title = QLabel("💬 แชทสด")
        title.setStyleSheet("font-weight: 600;")
        hlayout.addWidget(title)
        # ★ viewer count (click → toggle hide/show)
        self.viewers_label = QLabel("👥 0")
        self.viewers_label.setStyleSheet("color: #9ca3af; font-size: 14px;")
        self.viewers_label.setCursor(Qt.PointingHandCursor)
        self.viewers_label.setToolTip("คลิกเพื่อซ่อน/แสดงยอดคนดู")
        self._viewers_hidden = False
        self.viewers_label.mousePressEvent = lambda e: self._toggle_viewers()
        hlayout.addWidget(self.viewers_label)

        hlayout.addStretch()  # ★ push ปุ่มขวาไปทางขวา

        # ═══ RIGHT: A-/A+, system msg, code mute, clear, settings, popout ═══
        # ★ Font controls
        btn_font_dec = QPushButton("A-")
        btn_font_dec.setObjectName("IconButton")
        btn_font_dec.setFixedSize(34, 30)
        btn_font_dec.setCursor(Qt.PointingHandCursor)
        btn_font_dec.setToolTip("ลดขนาดฟอนต์")
        btn_font_dec.setStyleSheet("font-size: 13px; font-weight: bold; padding: 0px;")
        hlayout.addWidget(btn_font_dec)
        btn_font_inc = QPushButton("A+")
        btn_font_inc.setObjectName("IconButton")
        btn_font_inc.setFixedSize(34, 30)
        btn_font_inc.setCursor(Qt.PointingHandCursor)
        btn_font_inc.setToolTip("เพิ่มขนาดฟอนต์")
        btn_font_inc.setStyleSheet("font-size: 13px; font-weight: bold; padding: 0px;")
        hlayout.addWidget(btn_font_inc)
        # ★ ASK — เปิด/ปิดแผงโพล (เทาจาง = ยังไม่ใช้ / เขียว = กำลังใช้)
        self.btn_ask = QPushButton("ASK")
        self.btn_ask.setObjectName("IconButton")
        self.btn_ask.setFixedSize(46, 30)
        self.btn_ask.setCursor(Qt.PointingHandCursor)
        self.btn_ask.setToolTip("สร้างโพล/แบบสอบถาม (ASK)")
        self.btn_ask.setStyleSheet(self._ask_btn_qss(False))
        self._ask_active = False
        self.btn_ask.clicked.connect(self._on_ask_btn)
        hlayout.addWidget(self.btn_ask)
        # ★ System message toggle
        self.btn_system = QPushButton("🔔")
        self.btn_system.setObjectName("IconButton")
        self.btn_system.setCheckable(True)
        self.btn_system.setChecked(True)
        self.btn_system.setFixedSize(34, 30)
        self.btn_system.setCursor(Qt.PointingHandCursor)
        self.btn_system.setToolTip("แสดงสถานะเชื่อมต่อ (✅/⚪/⚠️) ในแชท")
        self.btn_system.setStyleSheet("font-size: 15px; padding: 0px;")
        hlayout.addWidget(self.btn_system)
        # ★ Code Mute toggle (ปิดเสียงโค้ดลับ)
        self.btn_code_mute = QPushButton("🎟")
        self.btn_code_mute.setObjectName("IconButton")
        self.btn_code_mute.setCheckable(True)
        self.btn_code_mute.setFixedSize(34, 30)
        self.btn_code_mute.setCursor(Qt.PointingHandCursor)
        self.btn_code_mute.setToolTip("ปิดเสียงโค้ดลับ (Secret Code)")
        self.btn_code_mute.setStyleSheet("font-size: 15px; padding: 0px;")
        self.btn_code_mute.clicked.connect(lambda: self.code_mute_toggled.emit(self.btn_code_mute.isChecked()))
        hlayout.addWidget(self.btn_code_mute)
        # ★ Clear button
        btn_clear = QPushButton("🗑")
        btn_clear.setObjectName("IconButton")
        btn_clear.setFixedSize(34, 30)
        btn_clear.setToolTip("ล้างแชท")
        btn_clear.setCursor(Qt.PointingHandCursor)
        btn_clear.setStyleSheet("font-size: 15px; padding: 0px;")
        btn_clear.clicked.connect(self.clear_requested.emit)
        hlayout.addWidget(btn_clear)
        # ★ Settings gear
        self.btn_settings = QPushButton("⚙")
        self.btn_settings.setObjectName("IconButton")
        self.btn_settings.setFixedSize(34, 30)
        self.btn_settings.setToolTip("ตั้งค่าแชทสด")
        self.btn_settings.setCursor(Qt.PointingHandCursor)
        self.btn_settings.setStyleSheet("font-size: 17px; padding: 0px;")
        self.btn_settings.clicked.connect(self.settings_clicked.emit)
        hlayout.addWidget(self.btn_settings)
        # ★ Popout button (ขวาสุด)
        btn_popout = QPushButton("↗")
        btn_popout.setObjectName("IconButton")
        btn_popout.setFixedSize(34, 30)
        btn_popout.setToolTip("แยกจอ")
        btn_popout.setCursor(Qt.PointingHandCursor)
        btn_popout.setStyleSheet("font-size: 17px; padding: 0px;")
        btn_popout.clicked.connect(self.popout_requested.emit)
        hlayout.addWidget(btn_popout)
        layout.addWidget(header)

        # ★ expose font buttons for external connections
        self.font_dec_btn = btn_font_dec
        self.font_inc_btn = btn_font_inc

        # ★ Scroll area for chat
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(0, 0, 0, 0)
        self.container_layout.setSpacing(0)
        self.container_layout.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll, 1)

        # ═══ ★ Chat input bar (ด้านล่าง — พิมพ์ส่งแชท + เลือกแพลตฟอร์ม) ═══
        #   ★ แสดงเฉพาะเมื่อล็อกอินแพลตฟอร์มที่รองรับการส่ง
        #   ★ มี platform chips ให้ติ๊กเลือกแพลตฟอร์มที่จะส่ง
        self._input_bar = QFrame()
        self._input_bar.setObjectName("ChatInputBar")
        self._input_bar.setStyleSheet(
            f"QFrame#ChatInputBar {{ background: {theme.COLOR_BG_DARK}; "
            f"border-top: 1px solid {theme.COLOR_BORDER}; }}"
        )
        input_outer = QVBoxLayout(self._input_bar)
        input_outer.setContentsMargins(8, 4, 8, 6)
        input_outer.setSpacing(4)

        # ★ Row 1: platform label (ซ้าย) + stretch + Bot toggle + เฟือง (ขวา)
        chips_and_controls = QHBoxLayout()
        chips_and_controls.setSpacing(8)

        # ★ platform chips container (ซ้าย) — จะถูกเติมโดย update_platform_chips
        self._chips_container = QWidget()
        self._chips_container.setStyleSheet("background: transparent; border: none;")
        self._platform_chips_layout = QHBoxLayout(self._chips_container)
        self._platform_chips_layout.setContentsMargins(0, 0, 0, 0)
        self._platform_chips_layout.setSpacing(4)
        self._platform_chips = {}
        self._platform_chips_state = {}
        chips_and_controls.addWidget(self._chips_container)
        chips_and_controls.addStretch()

        # ★ Bot toggle (ขวา — text ไม่มีขอบ, เปลี่ยนสีแค่ ON/OFF)
        self.btn_bot_toggle = QPushButton()
        self.btn_bot_toggle.setObjectName("BotToggle")
        self.btn_bot_toggle.setCheckable(True)
        self.btn_bot_toggle.setChecked(True)
        self.btn_bot_toggle.setCursor(Qt.PointingHandCursor)
        self.btn_bot_toggle.toggled.connect(self._on_bot_toggle)
        self._update_bot_toggle_text(True)
        # ★ กดค้าง / คลิกขวา ที่ปุ่ม Bot → เมนูเร็วเลือกแพลตฟอร์มที่ให้ Bot ทำงาน
        # ★ timer อัปเดตตัวนับวินาทีรอคิว TTS ริมข้อความ (ทุก 1 วิ)
        self._tts_wait_timer = QTimer(self)
        self._tts_wait_timer.timeout.connect(self._refresh_tts_waits)
        self._tts_wait_timer.start(1000)

        self._bot_btn_hold_timer = QTimer(self)
        self._bot_btn_hold_timer.setSingleShot(True)
        self._bot_btn_hold_timer.setInterval(450)  # hold 450ms = เปิดเมนู
        self._bot_btn_hold_timer.timeout.connect(self._show_bot_platform_menu)
        self._bot_btn_hold_pressed = False
        self.btn_bot_toggle.installEventFilter(self)
        chips_and_controls.addWidget(self.btn_bot_toggle)

        # ★ เส้นคั่น | ระหว่าง toggle กับ setting
        separator = QLabel("|")
        separator.setStyleSheet("color: #475569; font-size: 12px; border: none; background: transparent;")
        chips_and_controls.addWidget(separator)

        # ★ Setting text (ขวาสุด)
        self.btn_bot_settings = QPushButton("Setting")
        self.btn_bot_settings.setObjectName("BotSetting")
        self.btn_bot_settings.setCursor(Qt.PointingHandCursor)
        self.btn_bot_settings.setStyleSheet(
            "QPushButton#BotSetting { background: transparent; border: none; "
            "color: #94a3b8; font-size: 12px; font-weight: 600; }"
            "QPushButton#BotSetting:hover { color: #e2e8f0; }"
        )
        self.btn_bot_settings.clicked.connect(self.bot_settings_requested.emit)
        chips_and_controls.addWidget(self.btn_bot_settings)

        input_outer.addLayout(chips_and_controls)

        # ★ Row 2: text input + send button
        input_row = QHBoxLayout()
        input_row.setSpacing(6)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("พิมพ์ข้อความ... (Enter = ส่ง)")
        self.input_field.setStyleSheet(
            f"QLineEdit {{ background: {theme.COLOR_CARD_HI}; color: {theme.COLOR_TEXT}; "
            f"border: 1px solid {theme.COLOR_BORDER_LIGHT}; "
            "border-radius: 6px; padding: 6px 10px; font-size: 13px; }"
            f"QLineEdit:focus {{ border-color: {theme.COLOR_ACCENT}; }}"
        )
        self.input_field.returnPressed.connect(self._on_send_clicked)

        self.btn_send = QPushButton("ส่ง")
        self.btn_send.setFixedHeight(32)
        self.btn_send.setCursor(Qt.PointingHandCursor)
        self.btn_send.setStyleSheet(
            f"QPushButton {{ background: {theme.COLOR_ACCENT}; color: white; border: none; "
            "border-radius: 6px; padding: 0 16px; font-weight: 600; }"
            f"QPushButton:hover {{ background: {theme.COLOR_ACCENT_HOVER}; }}"
            f"QPushButton:pressed {{ background: {theme.COLOR_ACCENT_HOVER}; }}"
        )
        self.btn_send.clicked.connect(self._on_send_clicked)

        # ★ checkbox TTS ข้างปุ่มส่ง — ติ๊ก = ข้อความที่พิมพ์ผ่านช่องนี้จะถูกอ่านออกเสียง
        #   (คุมเฉพาะช่องพิมพ์นี้ — ข้อความบนหน้าเว็บคุมที่ ตั้งค่า > TTS)
        self.tts_check = QCheckBox("TTS")
        self.tts_check.setToolTip(
            "☑ = ให้ TTS อ่านข้อความที่ส่งผ่านช่องพิมพ์นี้ | "
            "☐ = ส่งโดยไม่อ่านออกเสียง | "
            "(จำค่าที่ติ๊กไว้ — เปิดโปรแกรมใหม่ใช้ค่าเดิม)"
        )
        self.tts_check.setStyleSheet(
            "QCheckBox { color: #94a3b8; font-size: 12px; font-weight: 600; "
            "background: transparent; border: none; spacing: 4px; }"
            "QCheckBox::indicator { width: 14px; height: 14px; }"
            "QCheckBox:hover { color: #e2e8f0; }"
        )

        input_row.addWidget(self.input_field, 1)
        input_row.addWidget(self.tts_check)
        input_row.addWidget(self.btn_send)
        input_outer.addLayout(input_row)

        # ★ ซ่อนเป็น default (จะแสดงเมื่อ app.py เรียก set_send_enabled)
        self._input_bar.setVisible(False)
        layout.addWidget(self._input_bar)

        # ═══ ★ Bot connect overlay (เบลอ + ปุ่มเชื่อมต่อแชทบอท) ═══
        #   ★ แสดงเมื่อ: เชื่อมต่อ Twitch แล้ว แต่ยังไม่ได้ OAuth login
        #   ★ ซ่อนเมื่อ: ไม่ได้เชื่อมต่อ Twitch หรือ OAuth login แล้ว
        self._bot_overlay = QFrame()
        self._bot_overlay.setObjectName("BotOverlay")
        self._bot_overlay.setStyleSheet(
            "QFrame#BotOverlay { background: rgba(15, 23, 42, 0.85); border-top: 1px solid #334155; }"
        )
        overlay_layout = QHBoxLayout(self._bot_overlay)
        overlay_layout.setContentsMargins(12, 8, 12, 8)
        overlay_layout.setSpacing(8)

        overlay_text = QLabel("🔒 ล็อกอิน Twitch / KICK เพื่อส่งแชท + ใช้ Chat Bot")
        overlay_text.setStyleSheet("color: #94a3b8; font-size: 13px; border: none; background: transparent;")
        overlay_layout.addWidget(overlay_text)
        overlay_layout.addStretch()

        self.btn_connect_bot = QPushButton("🤖 เชื่อมต่อแชทบอท")
        self.btn_connect_bot.setCursor(Qt.PointingHandCursor)
        self.btn_connect_bot.setStyleSheet(
            "QPushButton { background: #7c3aed; color: white; border: none; "
            "border-radius: 6px; padding: 6px 16px; font-weight: 600; }"
            "QPushButton:hover { background: #6d28d9; }"
        )
        self.btn_connect_bot.clicked.connect(self.connect_bot_requested.emit)
        overlay_layout.addWidget(self.btn_connect_bot)

        self._bot_overlay.setVisible(False)
        layout.addWidget(self._bot_overlay)

    def _update_bot_toggle_text(self, checked):
        """★ อัปเดตข้อความ toggle — 'Chat Bot : ON' (สีส้ม) / 'OFF' (สีเทา)"""
        state = "ON" if checked else "OFF"
        # ★ QPushButton ไม่รองรับ HTML → ใช้ stylesheet คุมสีทั้งปุ่ม
        color = "#f59e0b" if checked else "#64748b"
        weight = "700" if checked else "600"
        self.btn_bot_toggle.setText(f"🤖 Chat Bot :  {state}")
        self.btn_bot_toggle.setStyleSheet(
            f"QPushButton#BotToggle {{ background: transparent; border: none; font-size: 12px; "
            f"color: {color}; font-weight: {weight}; }}"
        )

    def _on_bot_toggle(self, checked):
        """★ toggle Bot ON/OFF → emit signal + เปลี่ยนข้อความ"""
        self._update_bot_toggle_text(checked)
        self.bot_toggle_requested.emit(checked)

    def set_bot_enabled(self, enabled):
        """★ sync toggle กับ settings (เรียกจาก app.py)"""
        self.btn_bot_toggle.blockSignals(True)
        self.btn_bot_toggle.setChecked(enabled)
        self._update_bot_toggle_text(enabled)
        self.btn_bot_toggle.blockSignals(False)

    # ------------------------------------------------------------------ #
    # ★ เมนูเร็ว — กดค้าง/คลิกขวาที่ปุ่ม Chat Bot → เลือกแพลตฟอร์ม
    # ------------------------------------------------------------------ #
    def eventFilter(self, obj, event):
        if obj is self.btn_bot_toggle:
            from PySide6.QtCore import QEvent
            if event.type() == QEvent.MouseButtonPress:
                if event.button() == Qt.RightButton:
                    self._show_bot_platform_menu()
                    return True
                # ★ ซ้ายกดค้าง → จับเวลา (ครบ 450ms = เมนู, ปล่อยก่อน = toggle ปกติ)
                self._bot_btn_hold_pressed = True
                self._bot_btn_hold_timer.start()
            elif event.type() == QEvent.MouseButtonRelease:
                self._bot_btn_hold_timer.stop()
                if getattr(self, '_bot_menu_shown', False):
                    # ★ เมนูเพิ่งเปิดจากการ hold → กลืน click กัน toggle โดยพลาด
                    self._bot_menu_shown = False
                    self._bot_btn_hold_pressed = False
                    return True
                self._bot_btn_hold_pressed = False
        return super().eventFilter(obj, event)

    def _show_bot_platform_menu(self):
        """เมนูเล็ก popup ใต้ปุ่ม — ติ๊กแพลตฟอร์มที่ให้ Bot ทำงาน"""
        from PySide6.QtWidgets import QMenu
        self._bot_btn_hold_timer.stop()
        self._bot_menu_shown = True
        state = getattr(self, '_bot_platforms_state', None) or {
            "twitch": True, "youtube": True, "kick": True}
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: #1e293b; color: #e2e8f0; border: 1px solid #475569; "
            "padding: 4px; } QMenu::item { padding: 4px 24px 4px 12px; } "
            "QMenu::item:selected { background: #7c3aed; }"
        )
        # ★ แสดงเฉพาะแพลตฟอร์มที่มี Bot ใช้งานจริง (YouTube ยังไม่มี — พร้อมเมื่อไหร่ค่อยเพิ่ม)
        labels = {"twitch": "Twitch", "kick": "KICK"}
        for key in labels:
            act = menu.addAction(f"{labels[key]}{' ✓' if state.get(key, True) else ''}")
            act.setCheckable(True)
            act.setChecked(bool(state.get(key, True)))
            def _toggle(checked, k=key):
                state[k] = checked
                self._bot_platforms_state = dict(state)
                self.bot_platforms_changed.emit(dict(state))
            act.toggled.connect(_toggle)
        menu.setAttribute(Qt.WA_DeleteOnClose, True)
        # ★ popup ใต้ปุ่ม
        btn = self.btn_bot_toggle
        pos = btn.mapToGlobal(btn.rect().bottomLeft())
        menu.popup(pos)

    def set_bot_platforms(self, platforms: dict):
        """★ sync สถานะ per-platform จาก settings (เรียกจาก app.py)"""
        self._bot_platforms_state = dict(platforms or {})

    @staticmethod
    def _ask_btn_qss(active: bool) -> str:
        """QSS ของปุ่ม ASK — ★ฝัง rule QToolTip ชุดเดียวกับ stylesheet กลาง
        (ปุ่มที่มี setStyleSheet เป็นของตัวเอง tooltip จะไม่รับ style กลาง
         ทำให้หน้าตา tooltip ต่างจากปุ่มข้าง ๆ — ต้องใส่ให้เอง)"""
        body = (
            "font-size: 11px; font-weight: 800; letter-spacing: 0.5px; padding: 0px; "
            + ("color: #ffffff; background: #059669;" if active
               else "color: #6b7280; background: rgba(255,255,255,0.05);")
        )
        tip = ("QToolTip { background-color: #1a1f33; color: #e5e7eb; "
               "border: 1px solid #2a2f45; border-radius: 4px; "
               "padding: 4px 8px; font-size: 14px; }")
        return body + " " + tip

    def _on_ask_btn(self):
        """กดปุ่ม ASK → toggle แผง (app เชื่อม signal) + สลับสีเทา/เขียว"""
        self.ask_toggled.emit()

    def set_ask_active(self, active: bool):
        """sync สีปุ่ม — เทาจาง = ยังไม่ใช้ / เขียว = กำลังใช้งาน"""
        self._ask_active = bool(active)
        self.btn_ask.setStyleSheet(self._ask_btn_qss(active))

    def _on_send_clicked(self):
        """★ กดส่ง / Enter → ส่งข้อความผ่าน signal send_requested"""
        text = self.input_field.text().strip()
        if not text:
            return
        # ★ รวบรวมแพลตฟอร์มที่ติ๊กไว้ (เข้ม = ส่ง)
        selected = [plat for plat, active in self._platform_chips_state.items() if active]
        if not selected:
            self.input_field.setPlaceholderText("⚠️ เลือกแพลตฟอร์มอย่างน้อย 1 ตัว")
            return
        # ★ emit เป็น JSON string (กัน Qt signal issue กับ Python list) + สถานะ checkbox TTS
        import json
        self.send_requested.emit(text, json.dumps(selected), self.tts_check.isChecked())
        self.input_field.clear()
        self.input_field.setFocus()

    def update_platform_chips(self, platforms, twitch_connected_no_oauth=False):
        """★ อัปเดต platform chips + bot overlay

        Args:
            platforms: list of แพลตฟอร์มที่ส่งได้ (OAuth login แล้ว)
            twitch_connected_no_oauth: True = Twitch เชื่อมต่อแล้วแต่ยังไม่ OAuth → แสดง overlay
        """
        # ★ จัดการ overlay + input bar
        if hasattr(self, '_bot_overlay'):
            if twitch_connected_no_oauth:
                # ★ Twitch เชื่อมต่อ + ยังไม่ OAuth → แสดง overlay
                self._bot_overlay.setVisible(True)
                self._input_bar.setVisible(False)
            elif platforms:
                # ★ OAuth login แล้ว → แสดงช่องพิมพ์ + ซ่อน overlay
                self._bot_overlay.setVisible(False)
                self._input_bar.setVisible(True)
            else:
                # ★ ไม่เชื่อมต่อ / disconnect → ซ่อนทั้งคู่
                self._bot_overlay.setVisible(False)
                self._input_bar.setVisible(False)
        # ★ clear chips เดิม (ทั้งหมด — กันซ้อน)
        while self._platform_chips_layout.count():
            item = self._platform_chips_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._platform_chips = {}
        self._platform_chips_state = {}

        # ★ ซ่อน input bar ถ้าไม่มีแพลตฟอร์ม
        if not platforms:
            self._input_bar.setVisible(False)
            return
        self._input_bar.setVisible(True)

        # ★ ถ้ามีแค่ 1 แพลตฟอร์ม → แสดงเป็น label คลิกไม่ได้
        if len(platforms) == 1:
            plat = platforms[0]
            key = plat.get("key", "")
            label = plat.get("label", key)
            icon = plat.get("icon")
            lbl = QLabel()
            lbl.setFixedHeight(28)
            lbl.setAlignment(Qt.AlignCenter)
            if icon and not icon.isNull():
                lbl.setPixmap(icon)
                lbl.setFixedSize(20, 20)
            # ★ แสดงชื่อแพลตฟอร์มข้างหน้าช่องพิมพ์ (label ธรรมดา)
            text_lbl = QLabel(label)
            text_lbl.setStyleSheet(
                "color: #a78bfa; font-size: 12px; font-weight: 600; "
                "background: rgba(124,58,237,0.15); border-radius: 14px; "
                "padding: 2px 12px; border: none;"
            )
            text_lbl.setFixedHeight(24)
            self._platform_chips_layout.insertWidget(
                self._platform_chips_layout.count() - 1, text_lbl)
            self._platform_chips_state[key] = True  # active เสมอ
            self._platform_chips[key] = text_lbl
            return

        # ★ ถ้ามีหลายแพลตฟอร์ม → แสดงเป็น toggle chips (เหมือนเดิม)
        for plat in platforms:
            key = plat.get("key", "")
            label = plat.get("label", key)
            icon = plat.get("icon")
            active = plat.get("active", True)
            if not key:
                continue

            chip = QPushButton()
            chip.setCursor(Qt.PointingHandCursor)
            chip.setFixedHeight(28)
            chip.setCheckable(True)
            chip.setChecked(active)
            if icon and not icon.isNull():
                chip.setIcon(icon)
                chip.setIconSize(QSize(16, 16))
                chip.setText(f"  {label}")
            else:
                chip.setText(label)
            chip.clicked.connect(lambda checked, k=key: self._on_chip_toggled(k, checked))
            self._platform_chips_layout.insertWidget(self._platform_chips_layout.count() - 1, chip)
            self._platform_chips[key] = chip
            self._platform_chips_state[key] = active
            self._apply_chip_style(key, active)

    def _on_chip_toggled(self, key, checked):
        """★ toggle chip → เปลี่ยนสถานะ + style"""
        self._platform_chips_state[key] = checked
        self._apply_chip_style(key, checked)

    def _apply_chip_style(self, key, active):
        """★ apply style ให้ chip — active = เข้ม, inactive = จาง"""
        chip = self._platform_chips.get(key)
        if not chip:
            return
        if active:
            chip.setStyleSheet(
                "QPushButton { background: #7c3aed; color: white; border: 1px solid #6d28d9; "
                "border-radius: 14px; padding: 2px 12px; font-size: 12px; font-weight: 600; }"
                "QPushButton:hover { background: #6d28d9; }"
            )
        else:
            chip.setStyleSheet(
                "QPushButton { background: #1e293b; color: #64748b; border: 1px solid #334155; "
                "border-radius: 14px; padding: 2px 12px; font-size: 12px; }"
                "QPushButton:hover { background: #334155; color: #94a3b8; }"
            )

    def set_send_enabled(self, enabled: bool, placeholder: str = ""):
        """★ legacy method — คงไว้เพื่อ compat (ไม่ทำอะไร ใช้ update_platform_chips แทน)"""
        # ★ ถ้า enabled=False → ซ่อนทั้ง input bar
        if not enabled:
            self._input_bar.setVisible(False)
        if placeholder:
            self.input_field.setPlaceholderText(placeholder)

    def _toggle_viewers(self):
        """ซ่อน/แสดงยอดคนดู (คลิกที่ label)

        ★ เมื่อซ่อน → ยอดรวมเป็น "👥 --" + ยอดแต่ละการ์ดแพลตฟอร์มก็เป็น "👥 --" ด้วย
        ★ app._update_viewer_ui จะ detect _viewers_hidden แล้วซ่อนยอดการ์ดให้อัตโนมัติ
        """
        self._viewers_hidden = not self._viewers_hidden
        if self._viewers_hidden:
            self.viewers_label.setText("👥 --")
        else:
            count = getattr(self, '_last_viewer_count', 0)
            self.viewers_label.setText(f"👥 {count:,}")
        # ★ trigger update ทันที → ยอดในการ์ดแพลตฟอร์มตามสถานะใหม่
        #    (app เก็บ ref ไว้ใน self.viewer_toggle_callback — set ตอน _build_ui)
        cb = getattr(self, 'viewer_toggle_callback', None)
        if cb:
            try: cb()
            except Exception: pass

    def add_message(self, msg, font_size=None):
        """เพิ่ม chat message ใหม่ — ใหม่สุดอยู่บน (insert at index 0)
        font_size: ถ้าระบุ → ใช้ขนาดนี้ (สำหรับ font scale)
        """
        fs = font_size or getattr(self, '_current_font_size', 16)
        row = ChatRow(msg, self.container, fs)
        # ★ connect row signals
        row.delete_requested.connect(self._delete_row)
        row.block_user_requested.connect(self.block_user_requested.emit)
        row.author_clicked.connect(self.author_clicked.emit)
        self.container_layout.insertWidget(0, row)
        self._rows.append(row)

        # ★ cap rows (เก็บล่าสุด 60)
        max_rows = 60
        if len(self._rows) > max_rows:
            old = self._rows.pop(0)
            old.deleteLater()

        # ★ re-apply zebra backgrounds (index เปลี่ยนเพราะมี row ใหม่ด้านบน)
        self._apply_zebra()

    def _apply_zebra(self):
        """re-apply zebra stripes ตาม settings (เรียกหลัง add/delete)"""
        try:
            from ui.widgets.chat_row import apply_zebra_backgrounds
            apply_zebra_backgrounds(self._rows)
        except Exception:
            pass

    def clear_messages(self):
        """ล้าง chat ทั้งหมด"""
        for row in self._rows:
            row.deleteLater()
        self._rows.clear()

    # ════════════════════════════════════════════════════════════
    # ★ TTS status — ไอคอนริมข้อความ (รอคิว/กำลังอ่าน/อ่านแล้วกี่วิ)
    # ════════════════════════════════════════════════════════════
    def update_tts_status(self, tts_id: str, status: str, info: dict | None = None):
        """อัปเดตไอคอนสถานะ TTS ของข้อความ (หา row จาก _tts_id ใน extra)"""
        if not tts_id:
            return
        for row in self._rows:
            try:
                extra = getattr(getattr(row, 'msg', None), 'extra', None) or {}
                if extra.get("_tts_id") == tts_id:
                    row.set_tts_status(status, info)
                    return
            except Exception:
                continue

    def _refresh_tts_waits(self):
        """timer ทุก 1 วิ — อัปเดตตัวนับวินาทีที่รอคิว (เห็นชัดว่าค้างไหม)"""
        for row in self._rows:
            try:
                row.refresh_tts_wait()
            except Exception:
                pass

    def _delete_row(self, row):
        """ลบ row เดียว"""
        if row in self._rows:
            self._rows.remove(row)
            row.deleteLater()
