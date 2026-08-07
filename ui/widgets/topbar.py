"""topbar.py — Top bar widget (platform status + action buttons)"""
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QHBoxLayout, QSizePolicy, QWidget


class TopBar(QFrame):
    """Top bar — platform status dots + action buttons"""

    # signals (เรียกจาก parent app)
    settings_clicked = Signal()
    user_manager_clicked = Signal()
    overlay_toggle_clicked = Signal()
    mute_toggle_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TopBar")
        self.setFixedHeight(44)
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(8)

        # ★ Left: platform status (dynamic — เพิ่มตอน connect)
        self._platforms_layout = QHBoxLayout()
        self._platforms_layout.setSpacing(10)
        layout.addLayout(self._platforms_layout)

        # ★ Stretch (ดันปุ่มไปขวา)
        layout.addStretch()

        # ★ Right: action buttons (icon buttons)
        self.btn_overlay = self._icon_btn("🔲", "Overlay", self.overlay_toggle_clicked.emit)
        self.btn_user = self._icon_btn("👤", "User Manager", self.user_manager_clicked.emit)
        self.btn_settings = self._icon_btn("⚙️", "Settings", self.settings_clicked.emit)
        self.btn_mute = self._icon_btn("🔊", "Mute TTS", self._toggle_mute)

        layout.addWidget(self.btn_overlay)
        layout.addWidget(self.btn_user)
        layout.addWidget(self.btn_mute)
        layout.addWidget(self.btn_settings)

    def _icon_btn(self, icon, tooltip, callback):
        btn = QPushButton(icon)
        btn.setObjectName("IconButton")
        btn.setToolTip(tooltip)
        btn.setFixedSize(36, 32)
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(callback)
        return btn

    def _toggle_mute(self):
        self._muted = not getattr(self, '_muted', False)
        self.btn_mute.setText("🔇" if self._muted else "🔊")
        self.btn_mute.setToolTip("Unmute TTS" if self._muted else "Mute TTS")
        self.mute_toggle_clicked.emit()

    def add_platform_status(self, platform, color="#6b7280"):
        """เพิ่ม status indicator สำหรับแพลตฟอร์ม (dot + name)"""
        widget = QWidget()
        wlayout = QHBoxLayout(widget)
        wlayout.setContentsMargins(0, 0, 0, 0)
        wlayout.setSpacing(4)
        dot = QFrame()
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(f"background-color: {color}; border-radius: 4px;")
        name = QLabel(platform)
        name.setStyleSheet("color: #9ca3af; font-size: 12px;")
        wlayout.addWidget(dot)
        wlayout.addWidget(name)
        widget.dot = dot  # เก็บ ref เพื่ออัปเดตสีทีหลัง
        self._platforms_layout.addWidget(widget)
        return widget

    def update_platform_status(self, platform_widget, connected):
        """อัปเดตสี dot (เขียว=connected, เทา=disconnected)"""
        color = "#10b981" if connected else "#6b7280"
        platform_widget.dot.setStyleSheet(f"background-color: {color}; border-radius: 4px;")
