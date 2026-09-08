"""topbar.py — Top bar widget (new design with split buttons + TTS toggle)

Layout (ซ้าย → ขวา):
  [platform status dots] [stretch]
  [เปิด/ปิด อ่านแชท + volume slider]
  [Overlay ▼]
  [อ่านทุกภาษา/แปล ▼⚙]
  [Game Overlay ▼]
  [Overlay+ ▼]
  [⚙ Settings]
"""
from PySide6.QtCore import Qt, Signal, QVariantAnimation, QSize
from PySide6.QtWidgets import (
    QFrame, QLabel, QPushButton, QHBoxLayout, QWidget,
    QSlider, QWidgetAction,
)
import ui.theme as theme  # ★ อ้าง theme.COLOR_X สดตอนสร้าง widget (ตามธีมที่เลือกไว้จริง)
from ui.widgets.split_button import SplitButton


class TopBar(QFrame):
    """Top bar — platform status + action buttons (new design)"""

    # ═══ Signals ═══
    settings_clicked = Signal()                         # ⚙ Settings
    # TTS toggle
    tts_toggled = Signal(bool)                          # True = เปิดอ่าน, False = ปิด
    volume_changed = Signal(int)                        # 0-100
    # Composer (Canvas Overlay)
    composer_toggled = Signal()                         # เปิด/ปิด Composer
    copy_overlay_url = Signal()                         # คัดลอก Overlay URL
    # Translate
    translate_mode_changed = Signal(str)                # "off" | "multilang" | "translate"
    translate_settings = Signal()                       # ⚙ ตั้งค่าการแปล
    # Game Overlay
    game_overlay_toggled = Signal()                     # เปิด/ปิด Game Overlay
    game_overlay_edit = Signal()                        # ซ่อน/แสดงกรอบ
    game_overlay_settings = Signal()                    # ⚙ Game Overlay Settings
    # Overlay+
    overlay_plus_toggled = Signal()                     # เปิด/ปิด Overlay+ ทั้งหมด
    overlay_plus_edit = Signal()                        # Edit Mode
    overlay_plus_settings = Signal()                    # ⚙ ตั้งค่า Overlay+
    # Viewer Overlay (ใน Game Overlay dropdown)
    viewer_overlay_toggled = Signal()                   # เปิด/ปิด Viewer Overlay
    # User manager (เก็บไว้ — เปิดจาก menu อื่นหรือ settings)
    user_manager_clicked = Signal()
    # ★ Update notification
    update_clicked = Signal()
    # ★ Launch OBS (เปิดโปรแกรม OBS หรือ bring-to-front ถ้ารันอยู่แล้ว)
    obs_launch_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TopBar")
        self.setMinimumHeight(48)
        self.setMaximumHeight(52)
        self._translate_mode = "off"  # "off" | "multilang" | "translate"
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(6)

        # ═══ Left: เปิด OBS (icon จาก obs64.exe) ═══
        #   ★ กด 1 ครั้ง → เปิด OBS (ถ้ายังไม่รัน) หรือ bring-to-front (ถ้ารันอยู่)
        self.btn_obs = QPushButton("  OBS")
        self.btn_obs.setObjectName("OBSButton")
        self.btn_obs.setFixedHeight(32)
        self.btn_obs.setCursor(Qt.PointingHandCursor)
        self.btn_obs.setToolTip("เปิดโปรแกรม OBS (หรือดึงหน้าต่าง OBS ที่ซ่อนไว้ขึ้นมาแสดง)")
        self.btn_obs.setStyleSheet(
            "QPushButton { background-color: #1e293b; color: #e2e8f0; border: 1px solid #334155; "
            "border-radius: 6px; padding: 4px 12px; font-size: 13px; font-weight: 600; }"
            "QPushButton:hover { background-color: #334155; border-color: #475569; }"
            "QPushButton:pressed { background-color: #0f172a; }"
        )
        # ★ โหลด OBS icon จาก assets/obs_icon.png (extract จาก obs64.exe)
        import os as _os
        from PySide6.QtGui import QPixmap, QIcon
        _icon_path = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))), "assets", "obs_icon.png")
        # ★ PyInstaller bundled: assets/ อยู่ใน _internal/assets/
        try:
            import sys as _sys
            if getattr(_sys, 'frozen', False):
                _internal = _os.path.join(_os.path.dirname(_sys.executable), "_internal")
                if _os.path.isdir(_internal):
                    _icon_path = _os.path.join(_internal, "assets", "obs_icon.png")
        except Exception:
            pass
        if _os.path.exists(_icon_path):
            _obs_pix = QPixmap(_icon_path)
            if not _obs_pix.isNull():
                self.btn_obs.setIcon(QIcon(_obs_pix))
                self.btn_obs.setIconSize(QSize(20, 20))
        self.btn_obs.clicked.connect(self.obs_launch_clicked.emit)
        layout.addWidget(self.btn_obs)
        # ★ default state = ยังไม่เปิด
        self._obs_running = False

        layout.addStretch()

        # ═══ 1. เปิด/ปิด อ่านแชท (SplitButton — toggle + volume slider ใน dropdown) ═══
        self.btn_tts = SplitButton(
            "🔊 อ่านแชท", tooltip="เปิด/ปิดการอ่านแชทด้วย TTS",
            parent=self, on_click=self._on_tts_click,
        )
        # ★ volume slider widget สำหรับใส่ใน dropdown menu
        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(100)
        self.vol_slider.setFixedHeight(20)
        self.vol_slider.setMinimumWidth(140)
        self.vol_slider.setToolTip("ระดับเสียง TTS")
        self.vol_slider.valueChanged.connect(self.volume_changed.emit)
        # ★ สร้าง custom menu ที่มี slider widget action
        vol_action = QWidgetAction(self.btn_tts)
        vol_widget = QWidget()
        vol_layout = QHBoxLayout(vol_widget)
        vol_layout.setContentsMargins(12, 8, 12, 8)
        vol_layout.setSpacing(8)
        vol_lbl = QLabel("🔊")
        vol_layout.addWidget(vol_lbl)
        vol_layout.addWidget(self.vol_slider, 1)
        self.vol_value_lbl = QLabel("100%")
        self.vol_value_lbl.setStyleSheet("color: #7c3aed; font-weight: 600; min-width: 36px;")
        self.vol_slider.valueChanged.connect(lambda v: self.vol_value_lbl.setText(f"{v}%"))
        vol_layout.addWidget(self.vol_value_lbl)
        vol_action.setDefaultWidget(vol_widget)
        # ★ เพิ่ม slider เป็น menu action แรก
        self.btn_tts._menu.addAction(vol_action)
        layout.addWidget(self.btn_tts)
        # initial state: TTS เปิดอยู่ (default)
        self._tts_on = True
        self._update_tts_button()

        # ═══ 2. Overlay ▼ (Composer toggle + copy URL) ═══
        self.btn_composer = SplitButton(
            "🖥️ Overlay", tooltip="เปิด/ปิด Composer (Canvas Overlay)",
            parent=self,
        )
        self.btn_composer.set_menu_actions([
            ("📋 คัดลอก Overlay URL", self.copy_overlay_url.emit),
        ])
        self.btn_composer.main_clicked.connect(self.composer_toggled.emit)
        self.btn_composer.set_active(True)  # ★ สี accent ตลอดเวลา (composer เปิดอยู่เสมอ)
        layout.addWidget(self.btn_composer)

        # ═══ 3. แปลภาษา/อ่านทุกภาษา ▼ (toggle 2-state + settings) ═══
        self.btn_translate = SplitButton(
            "🌐 แปลภาษา", tooltip="คลิกเพื่อสลับโหมด — แปลภาษา ↔ อ่านทุกภาษา",
            parent=self,
        )
        self.btn_translate.set_menu_actions([
            ("⚙ ตั้งค่าภาษาที่รองรับ", self.translate_settings.emit),
        ])
        self.btn_translate.main_clicked.connect(self._toggle_translate)
        layout.addWidget(self.btn_translate)

        # ═══ 4. Game Overlay ▼ (toggle + edit/settings) ═══
        self.btn_game = SplitButton(
            "🎮 Game Overlay", tooltip="เปิด/ปิด Game Overlay",
            parent=self,
        )
        self.btn_game.set_menu_actions([
            ("👥 Viewer Overlay", self.viewer_overlay_toggled.emit),
            ("👁 ซ่อน/แสดงกรอบ", self.game_overlay_edit.emit),
            ("—", None),
            ("⚙ ตั้งค่า Game Overlay", self.game_overlay_settings.emit),
        ])
        self.btn_game.main_clicked.connect(self.game_overlay_toggled.emit)
        layout.addWidget(self.btn_game)

        # ═══ 5. Overlay+ ▼ (toggle + edit/settings) ═══
        self.btn_overlay_plus = SplitButton(
            "🪟 Overlay+", tooltip="เปิด/ปิด Overlay+ (custom URL overlays)",
            parent=self,
        )
        self.btn_overlay_plus.set_menu_actions([
            ("👁 ซ่อน/แสดงกรอบ", self.overlay_plus_edit.emit),
            ("⚙ ตั้งค่า Overlay+", self.overlay_plus_settings.emit),
        ])
        self.btn_overlay_plus.main_clicked.connect(self.overlay_plus_toggled.emit)
        layout.addWidget(self.btn_overlay_plus)

        # ═══ 6. 👤 User Manager ═══
        self.btn_user_manager = QPushButton("👤")
        self.btn_user_manager.setObjectName("IconButton")
        self.btn_user_manager.setFixedSize(36, 32)
        self.btn_user_manager.setToolTip("จัดการผู้ชม — ดูรายชื่อ + สถิติ + แบน/เปลี่ยนชื่อ")
        self.btn_user_manager.setCursor(Qt.PointingHandCursor)
        self.btn_user_manager.setStyleSheet("font-size: 16px; padding: 0px;")
        self.btn_user_manager.clicked.connect(self.user_manager_clicked.emit)
        layout.addWidget(self.btn_user_manager)

        # ═══ 7. ⚙ Settings ═══
        self.btn_settings = QPushButton("⚙")
        self.btn_settings.setObjectName("IconButton")
        self.btn_settings.setFixedSize(36, 32)
        self.btn_settings.setToolTip("ตั้งค่า")
        self.btn_settings.setCursor(Qt.PointingHandCursor)
        self.btn_settings.setStyleSheet("font-size: 18px; padding: 0px;")
        self.btn_settings.clicked.connect(self.settings_clicked.emit)
        layout.addWidget(self.btn_settings)

        # ═══ 9. 🆕 New Update (ขวาสุด — ซ่อนไว้ แสดงเมื่อมีอัพเดท) ═══
        self.btn_update = QPushButton("UPDATE")
        self.btn_update.setFixedHeight(32)
        self.btn_update.setCursor(Qt.PointingHandCursor)
        self.btn_update.setToolTip("มีเวอร์ชั่นใหม่ — คลิกเพื่ออัพเดท")
        self._update_btn_base_style = (
            # ★ ทรงแคปซูล (border-radius = ครึ่งความสูง) + ไล่เฉดแนวตั้ง + ขอบบาง + เงาใต้
            "QPushButton { "
            "background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            " stop:0 #ff4757, stop:1 #ff3344);"
            " color: white; border: 1px solid rgba(255,255,255,0.25); "
            "border-radius: 16px; padding: 4px 18px; font-size: 12px; font-weight: 700; "
            "letter-spacing: 1px; "
            "} "
            "QPushButton:hover { "
            "background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            " stop:0 #ff5b6a, stop:1 #ff4455);"
            "border: 1px solid rgba(255,255,255,0.4);"
            "} "
            "QPushButton:pressed { "
            "background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            " stop:0 #e03444, stop:1 #cc2a38);"
            "padding-top: 5px; padding-bottom: 3px;"
            "}"
        )
        self.btn_update.setStyleSheet(self._update_btn_base_style)

        # ★ glow effect (เงาแดงรอบปุ่ม)
        from PySide6.QtWidgets import QGraphicsDropShadowEffect
        # ★ Shimmer — แสงขาววิ่งผ่านปุ่ม (เหมือนปุ่ม "Download" ใน App Store)
        from PySide6.QtWidgets import QGraphicsDropShadowEffect, QGraphicsOpacityEffect
        from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPixmap, QBrush, QPen
        from PySide6.QtCore import QRectF, QPointF

        self._update_glow = QGraphicsDropShadowEffect()
        self._update_glow.setBlurRadius(20)
        self._update_glow.setColor(QColor(255, 255, 255, 180))  # ขาวนวล
        self._update_glow.setOffset(0, 0)
        self._update_glow.setEnabled(False)
        self.btn_update.setGraphicsEffect(self._update_glow)

        # ★ Shimmer overlay — QLabel โปร่งใสทับบนปุ่ม ให้แสงขาววิ่งผ่าน
        self._shimmer_label = QLabel(self.btn_update)
        self._shimmer_label.setGeometry(0, 0, 40, 32)  # แถบแสงกว้าง 40px
        self._shimmer_label.setStyleSheet(
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            " stop:0, rgba(255,255,255,0),"
            " stop:0.5, rgba(255,255,255,120),"
            " stop:1, rgba(255,255,255,0));"
            "border-radius: 6px;"
        )
        self._shimmer_label.setAttribute(Qt.WA_TransparentForMouseEvents)  # ไม่กิน click
        self._shimmer_label.setVisible(False)
        self.btn_update.clicked.connect(self.update_clicked.emit)
        self.btn_update.setVisible(False)
        layout.addWidget(self.btn_update)

        # ★ glow pulse animation (เงาขาวนวล)
        self._update_pulse = QVariantAnimation(self)
        self._update_pulse.setDuration(700)
        self._update_pulse.setStartValue(0.0)
        self._update_pulse.setEndValue(1.0)
        self._update_pulse.setLoopCount(-1)
        self._update_pulse.valueChanged.connect(self._on_pulse_update)

    # ════════════════════════════════════════════════════════════
    # TTS toggle
    # ════════════════════════════════════════════════════════════
    def _on_tts_click(self):
        self._tts_on = not self._tts_on
        self._update_tts_button()
        self.tts_toggled.emit(self._tts_on)

    def _update_tts_button(self):
        """อัปเดตปุ่ม TTS — SplitButton ใช้ set_state + setText"""
        if self._tts_on:
            self.btn_tts.setText("🔊 อ่านแชท")
            self.btn_tts.set_state("on")  # green via custom — but we use "on" (accent)
            # ★ override to success color ตามธีมที่เลือกไว้ — สีตัวอักษรสลับเข้ม/อ่อนตามความสว่าง
            #   ของพื้นหลัง (QSS ไม่รองรับ text-shadow ให้ใส่เงาใต้ตัวอักษร — สลับสีให้ contrast
            #   พอแทน) ★ ธีมที่พื้นสว่างมาก (เช่น Nightwave Cyan) จะได้ตัวอักษรเข้มแทนขาวอ่านไม่ออก
            _on_success = theme.COLOR_ON_SUCCESS_TEXT
            _on_danger = theme.COLOR_ON_DANGER_TEXT
            self.btn_tts._main_btn.setStyleSheet(
                f"QPushButton {{ background-color: {theme.COLOR_SUCCESS}; color: {_on_success}; border: none; "
                "border-radius: 14px 0 0 14px; padding: 4px 6px 4px 14px; "
                "font-weight: 600; font-size: 12px; }"
                f"QPushButton:hover {{ background-color: {theme.COLOR_SUCCESS_HOVER}; }}"
            )
            self.btn_tts._arrow_btn.setStyleSheet(
                f"QPushButton {{ background-color: {theme.COLOR_SUCCESS}; color: {_on_success}; border: none; "
                "border-radius: 0 14px 14px 0; padding: 4px 2px; font-size: 11px; }"
                f"QPushButton:hover {{ background-color: {theme.COLOR_SUCCESS_HOVER}; }}"
            )
        else:
            self.btn_tts.setText("🔇 ปิดอ่าน")
            _on_danger = theme.COLOR_ON_DANGER_TEXT
            self.btn_tts._main_btn.setStyleSheet(
                f"QPushButton {{ background-color: {theme.COLOR_DANGER}; color: {_on_danger}; border: none; "
                "border-radius: 14px 0 0 14px; padding: 4px 6px 4px 14px; "
                "font-weight: 600; font-size: 12px; }"
                f"QPushButton:hover {{ background-color: {theme.COLOR_DANGER_HOVER}; }}"
            )
            self.btn_tts._arrow_btn.setStyleSheet(
                f"QPushButton {{ background-color: {theme.COLOR_DANGER}; color: {_on_danger}; border: none; "
                "border-radius: 0 14px 14px 0; padding: 4px 2px; font-size: 11px; }"
                f"QPushButton:hover {{ background-color: {theme.COLOR_DANGER_HOVER}; }}"
            )

    def set_tts_state(self, on):
        """set TTS state จากภายนอก (เช่น restore จาก settings)"""
        self._tts_on = bool(on)
        self._update_tts_button()

    def set_volume(self, vol):
        """set volume จากภายนอก (ไม่ trigger signal)"""
        self.vol_slider.blockSignals(True)
        self.vol_slider.setValue(int(vol))
        self.vol_slider.blockSignals(False)
        if hasattr(self, 'vol_value_lbl'):
            self.vol_value_lbl.setText(f"{int(vol)}%")

    # ════════════════════════════════════════════════════════════
    # Translate mode (แสดงสถานะ — คลิกเพื่อเปิด Settings > การแปล)
    # ════════════════════════════════════════════════════════════
    def _toggle_translate(self):
        """คลิกปุ่ม → เปิด Settings > การแปล (ไม่ toggle โหมดแล้ว)"""
        self.translate_settings.emit()

    def set_translate_mode(self, mode):
        """set translate mode จากภายนอก + update button (แสดงสถานะเท่านั้น)

        ★ mode="off" → ซ่อนปุ่ม (ปิดแล้วไม่ควรเห็น)
        """
        self._translate_mode = mode
        if mode == "off":
            self.btn_translate.setVisible(False)
            return
        self.btn_translate.setVisible(True)
        labels = {
            "multilang": ("🌐 อ่านทุกภาษา", "on"),
            "translate": ("🔄 แปลภาษา", "warning"),
        }
        text, state = labels.get(mode, ("🔄 แปลภาษา", "warning"))
        self.btn_translate.setText(text)
        self.btn_translate.set_state(state)

    # ════════════════════════════════════════════════════════════
    # Game Overlay + Overlay+ state updates (เรียกจาก app.py)
    # ════════════════════════════════════════════════════════════
    def set_composer_active(self, active):
        self.btn_composer.set_active(active)

    def set_game_overlay_active(self, active):
        self.btn_game.set_active(active)

    def set_overlay_plus_active(self, active):
        self.btn_overlay_plus.set_active(active, state="warning" if active else "")

    # ════════════════════════════════════════════════════════════
    # ★ Update notification button (pulse animation)
    # ════════════════════════════════════════════════════════════
    def show_update_button(self, version=""):
        """แสดงปุ่ม UPDATE + เริ่ม shimmer + glow"""
        vers = f" v{version}" if version else ""
        self.btn_update.setText(f"NEW UPDATE{vers}")
        self.btn_update.setVisible(True)
        self.btn_update.raise_()
        self._update_glow.setEnabled(True)
        if self._shimmer_label:
            self._shimmer_label.setVisible(True)
        if self._update_pulse.state() != QVariantAnimation.Running:
            self._update_pulse.start()

    def hide_update_button(self):
        """ซ่อนปุ่ม UPDATE + หยุด animation"""
        self.btn_update.setVisible(False)
        self._update_pulse.stop()
        self._update_glow.setEnabled(False)
        if self._shimmer_label:
            self._shimmer_label.setVisible(False)
        self.btn_update.setStyleSheet(self._update_btn_base_style)

    def _on_pulse_update(self, val):
        """shimmer + glow — แสงขาววิ่งผ่านปุ่ม + เงาขาวนวลกระพริบ"""
        import math
        # sine wave: 0→1→0 → 0=เข้มสุด, 1=หาย
        alpha = (math.sin(val * math.pi * 2) + 1) / 2
        glow_alpha = 1.0 - alpha
        # ★ glow ขาว: นุ่มๆ ไม่แรงเกิน
        blur = int(8 + glow_alpha * 20)
        self._update_glow.setBlurRadius(blur)
        self._update_glow.setColor(QColor(255, 255, 255, int(80 + glow_alpha * 100)))

        # ★ shimmer — ขยับแถบแสงจากซ้ายไปขวาตลอดความกว้างปุ่ม
        btn_w = self.btn_update.width()
        if btn_w > 0 and self._shimmer_label:
            # val 0→1 = รอบ 1 รอบ → แสงวิ่งซ้าย→ขวา→ซ้าย (ping-pong)
            travel = btn_w + 40  # กว้างพอให้ออกนอกปุ่ม
            x = int(val * travel) - 20  # offset ให้เริ่มก่อนปุ่ม
            self._shimmer_label.move(x, 0)
            self._shimmer_label.setFixedHeight(self.btn_update.height())
            self._shimmer_label.setVisible(True)
        # เงาสีแดง: โปร่งใสตาม alpha
        from PySide6.QtGui import QColor
        color = QColor(239, 68, 68, int(150 + glow_alpha * 105))
        self._update_glow.setColor(color)

    # ════════════════════════════════════════════════════════════
    # OBS button state (poll จาก app.py ทุก 3 วิ)
    # ════════════════════════════════════════════════════════════
    def set_obs_running(self, running: bool):
        """★ เปลี่ยนสถานะปุ่ม OBS — เรียกจาก app.py (poll ทุก 3 วิ)

        running=True  → "กำลังใช้งาน OBS" (สีเขียว)
        running=False → "เปิด OBS" (สีเทา)
        """
        if self._obs_running == running:
            return  # ไม่เปลี่ยน → ไม่ต้อง update
        self._obs_running = running
        if running:
            self.btn_obs.setText("  กำลังใช้งาน OBS")
            self.btn_obs.setStyleSheet(
                "QPushButton { background-color: #064e3b; color: #6ee7b7; border: 1px solid #10b981; "
                "border-radius: 6px; padding: 4px 12px; font-size: 13px; font-weight: 600; }"
                "QPushButton:hover { background-color: #065f46; border-color: #34d399; }"
                "QPushButton:pressed { background-color: #064e3b; }"
            )
            self.btn_obs.setToolTip("OBS กำลังรันอยู่ — กดเพื่อเปิดหน้าต่าง")
        else:
            self.btn_obs.setText("  เปิด OBS")
            self.btn_obs.setStyleSheet(
                "QPushButton { background-color: #1e293b; color: #e2e8f0; border: 1px solid #334155; "
                "border-radius: 6px; padding: 4px 12px; font-size: 13px; font-weight: 600; }"
                "QPushButton:hover { background-color: #334155; border-color: #475569; }"
                "QPushButton:pressed { background-color: #0f172a; }"
            )
            self.btn_obs.setToolTip("เปิดโปรแกรม OBS")
