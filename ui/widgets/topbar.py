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
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QLabel, QPushButton, QHBoxLayout, QWidget,
    QSlider, QWidgetAction,
)
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

        # ★ Left: platform status dots
        self._platforms_layout = QHBoxLayout()
        self._platforms_layout.setSpacing(10)
        layout.addLayout(self._platforms_layout)

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
            # ★ override to green specifically
            self.btn_tts._main_btn.setStyleSheet(
                "QPushButton { background-color: #10b981; color: white; border: none; "
                "border-radius: 14px 0 0 14px; padding: 4px 6px 4px 14px; "
                "font-weight: 600; font-size: 12px; }"
                "QPushButton:hover { background-color: #059669; }"
            )
            self.btn_tts._arrow_btn.setStyleSheet(
                "QPushButton { background-color: #10b981; color: white; border: none; "
                "border-radius: 0 14px 14px 0; padding: 4px 2px; font-size: 11px; }"
                "QPushButton:hover { background-color: #059669; }"
            )
        else:
            self.btn_tts.setText("🔇 ปิดอ่าน")
            self.btn_tts._main_btn.setStyleSheet(
                "QPushButton { background-color: #ef4444; color: white; border: none; "
                "border-radius: 14px 0 0 14px; padding: 4px 6px 4px 14px; "
                "font-weight: 600; font-size: 12px; }"
                "QPushButton:hover { background-color: #dc2626; }"
            )
            self.btn_tts._arrow_btn.setStyleSheet(
                "QPushButton { background-color: #ef4444; color: white; border: none; "
                "border-radius: 0 14px 14px 0; padding: 4px 2px; font-size: 11px; }"
                "QPushButton:hover { background-color: #dc2626; }"
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
    # Translate mode (2-state toggle: translate ↔ multilang)
    # ════════════════════════════════════════════════════════════
    def _toggle_translate(self):
        """toggle 2-state: translate ↔ multilang"""
        if self._translate_mode == "translate":
            self.set_translate_mode("multilang")
        else:
            self.set_translate_mode("translate")
        self.translate_mode_changed.emit(self._translate_mode)

    def set_translate_mode(self, mode):
        """set translate mode จากภายนอก + update button

        ★ mode="off" → ซ่อนปุ่มทั้งหมด (กัน user สับสน — ปิดแล้วไม่ควรเห็นปุ่ม)
        """
        self._translate_mode = mode
        # ★ off → ซ่อนปุ่ม translate ทั้งหมด
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
    # Platform status (เดิม)
    # ════════════════════════════════════════════════════════════
    def add_platform_status(self, platform, color="#6b7280"):
        """เพิ่ม status indicator สำหรับแพลตฟอร์ม"""
        widget = QWidget()
        widget.setStyleSheet("background: transparent;")
        wlayout = QHBoxLayout(widget)
        wlayout.setContentsMargins(0, 0, 0, 0)
        wlayout.setSpacing(4)
        name_to_key = {
            "Twitch": "twitch", "YouTube": "youtube", "MyLive": "mylive",
            "TikTok": "tiktok", "KICK": "kick",
        }
        plat_key = name_to_key.get(platform, "")
        try:
            from ui.platform_icons import get_platform_pixmap
            from PySide6.QtGui import QPixmap
            pix = get_platform_pixmap(plat_key, 16) if plat_key else QPixmap()
        except Exception:
            pix = QPixmap()
        dot = QLabel()
        dot.setFixedSize(16, 16)
        if not pix.isNull():
            dot.setPixmap(pix)
        else:
            dot.setFixedSize(10, 10)
            dot.setStyleSheet(f"background-color: {color}; border-radius: 5px; border: none;")
        name_lbl = QLabel(platform)
        name_lbl.setStyleSheet("color: #4b5563; font-size: 14px; background: transparent; border: none;")
        wlayout.addWidget(dot)
        wlayout.addWidget(name_lbl)
        widget.dot = dot
        widget.name_label = name_lbl
        widget._platform_key = plat_key
        self._platforms_layout.addWidget(widget)
        self.update_platform_status(widget, False)
        return widget

    def update_platform_status(self, platform_widget, connected):
        """อัปเดตสถานะ — icon + text"""
        from PySide6.QtWidgets import QGraphicsOpacityEffect
        dot = platform_widget.dot
        name_lbl = getattr(platform_widget, 'name_label', None)
        if connected:
            if dot.pixmap() is not None and not dot.pixmap().isNull():
                effect = dot.graphicsEffect()
                if not isinstance(effect, QGraphicsOpacityEffect):
                    effect = QGraphicsOpacityEffect(dot)
                    dot.setGraphicsEffect(effect)
                effect.setOpacity(1.0)
            else:
                dot.setStyleSheet("background-color: #10b981; border-radius: 5px; border: none;")
            if name_lbl is not None:
                name_lbl.setStyleSheet("color: #ffffff; font-size: 14px; background: transparent; border: none; font-weight: 600;")
        else:
            if dot.pixmap() is not None and not dot.pixmap().isNull():
                effect = dot.graphicsEffect()
                if not isinstance(effect, QGraphicsOpacityEffect):
                    effect = QGraphicsOpacityEffect(dot)
                    dot.setGraphicsEffect(effect)
                effect.setOpacity(0.3)
            else:
                dot.setStyleSheet("background-color: #4b5563; border-radius: 5px; border: none;")
            if name_lbl is not None:
                name_lbl.setStyleSheet("color: #4b5563; font-size: 14px; background: transparent; border: none;")
