"""topbar.py — Top bar widget (platform status + action buttons)"""
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QHBoxLayout, QSizePolicy, QWidget, QMenu


class TopBar(QFrame):
    """Top bar — platform status dots + action buttons"""

    settings_clicked = Signal()
    user_manager_clicked = Signal()
    overlay_toggle_clicked = Signal()
    mute_toggle_clicked = Signal()
    translate_clicked = Signal()
    code_mute_clicked = Signal()
    about_clicked = Signal()
    ngreplace_clicked = Signal()
    font_increase_clicked = Signal()
    font_decrease_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TopBar")
        self.setMinimumHeight(44)
        self.setMaximumHeight(48)
        self._muted = False
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(6)

        # ★ Left: platform status
        self._platforms_layout = QHBoxLayout()
        self._platforms_layout.setSpacing(10)
        layout.addLayout(self._platforms_layout)

        layout.addStretch()

        # ★ Font controls
        self.btn_font_dec = self._icon_btn("A-", "ลดขนาดฟอนต์", self.font_decrease_clicked.emit)
        self.btn_font_inc = self._icon_btn("A+", "เพิ่มขนาดฟอนต์", self.font_increase_clicked.emit)
        layout.addWidget(self.btn_font_dec)
        layout.addWidget(self.btn_font_inc)

        # ★ Translate
        self.btn_translate = self._icon_btn("🌐", "การแปลอัตโนมัติ", self.translate_clicked.emit)
        layout.addWidget(self.btn_translate)

        # ★ Code mute
        self.btn_code = self._icon_btn("🔔", "เสียงโค้ดลับ", self.code_mute_clicked.emit)
        layout.addWidget(self.btn_code)

        # ★ Overlay
        self.btn_overlay = self._icon_btn("🔲", "Overlay", self.overlay_toggle_clicked.emit)
        layout.addWidget(self.btn_overlay)

        # ★ User manager
        self.btn_user = self._icon_btn("👤", "User Manager", self.user_manager_clicked.emit)
        layout.addWidget(self.btn_user)

        # ★ Mute
        self.btn_mute = self._icon_btn("🔊", "Mute TTS", self._toggle_mute)
        layout.addWidget(self.btn_mute)

        # ★ Settings + menu
        self.btn_settings = self._icon_btn("⚙️", "Settings", self.settings_clicked.emit)
        layout.addWidget(self.btn_settings)

        # ★ More menu (...)
        self.btn_more = QPushButton("⋯")
        self.btn_more.setObjectName("IconButton")
        self.btn_more.setFixedSize(36, 32)
        self.btn_more.setCursor(Qt.PointingHandCursor)
        self.btn_more.setToolTip("เพิ่มเติม")
        self.btn_more.clicked.connect(self._show_menu)
        layout.addWidget(self.btn_more)

    def _icon_btn(self, icon, tooltip, callback):
        btn = QPushButton(icon)
        btn.setObjectName("IconButton")
        btn.setToolTip(tooltip)
        btn.setFixedSize(36, 32)
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(callback)
        return btn

    def _toggle_mute(self):
        self._muted = not self._muted
        self.btn_mute.setText("🔇" if self._muted else "🔊")
        self.btn_mute.setToolTip("Unmute TTS" if self._muted else "Mute TTS")
        self.mute_toggle_clicked.emit()

    def _show_menu(self):
        """เมนูเพิ่มเติม (About + NG-Replace + Playroom)"""
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: #131726; border: 1px solid #2a2f45; border-radius: 8px; padding: 4px; } QMenu::item { padding: 8px 24px; border-radius: 4px; color: #e5e7eb; } QMenu::item:selected { background-color: #7c3aed; }")
        act_about = menu.addAction("ℹ️ เกี่ยวกับ")
        act_ng = menu.addAction("🚫 NG-Replace")
        act_playroom = menu.addAction("🎮 Playroom")
        menu.addSeparator()
        act_copy_url = menu.addAction("📋 คัดลอก Overlay URL")
        action = menu.exec(self.btn_more.mapToGlobal(self.btn_more.rect().bottomLeft()))
        if action == act_about:
            self.about_clicked.emit()
        elif action == act_ng:
            self.ngreplace_clicked.emit()
        elif action == act_playroom:
            # emit via settings_clicked as workaround (or add signal)
            pass

    def add_platform_status(self, platform, color="#6b7280"):
        """เพิ่ม status indicator สำหรับแพลตฟอร์ม"""
        widget = QWidget()
        widget.setStyleSheet("background: transparent;")
        wlayout = QHBoxLayout(widget)
        wlayout.setContentsMargins(0, 0, 0, 0)
        wlayout.setSpacing(4)
        dot = QLabel()
        dot.setFixedSize(10, 10)
        dot.setStyleSheet(f"background-color: {color}; border-radius: 5px; border: none;")
        name = QLabel(platform)
        name.setStyleSheet("color: #9ca3af; font-size: 12px; background: transparent; border: none;")
        wlayout.addWidget(dot)
        wlayout.addWidget(name)
        widget.dot = dot
        self._platforms_layout.addWidget(widget)
        return widget

    def update_platform_status(self, platform_widget, connected):
        """อัปเดตสี dot"""
        color = "#10b981" if connected else "#6b7280"
        platform_widget.dot.setStyleSheet(f"background-color: {color}; border-radius: 5px; border: none;")
