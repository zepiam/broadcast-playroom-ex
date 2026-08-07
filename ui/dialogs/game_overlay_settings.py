"""game_overlay_settings.py — Game Overlay settings dialog

ตั้งค่า Game Overlay: appearance (theme), demo loop, position
"""
import logging
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QWidget, QFrame, QLabel, QPushButton, QLineEdit, QVBoxLayout,
    QHBoxLayout, QScrollArea, QComboBox, QSlider, QCheckBox, QSpinBox,
    QDoubleSpinBox, QGroupBox,
)

logger = logging.getLogger("game_overlay_settings")


class GameOverlaySettingsDialog(QDialog):
    """Game Overlay settings — appearance + demo + position"""

    def __init__(self, parent_app):
        super().__init__(parent_app if isinstance(parent_app, QWidget) else None)
        self.parent_app = parent_app
        self.settings = getattr(parent_app, 'settings', None)
        self.setWindowTitle("🎮 Game Overlay Settings")
        self.setGeometry(180, 120, 560, 600)
        self.setMinimumSize(460, 480)
        self._build_ui()
        self._load_values()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ★ Header
        header = QFrame()
        header.setFixedHeight(50)
        header.setStyleSheet("background: #131726; border-bottom: 1px solid #2a2f45;")
        hlayout = QHBoxLayout(header)
        hlayout.setContentsMargins(16, 0, 16, 0)
        title = QLabel("🎮 Game Overlay Settings")
        title.setStyleSheet("font-size: 15px; font-weight: 700; color: #f59e0b;")
        hlayout.addWidget(title)
        hlayout.addStretch()
        layout.addWidget(header)

        # ★ Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        clayout = QVBoxLayout(container)
        clayout.setContentsMargins(20, 16, 20, 16)
        clayout.setSpacing(10)

        # ── Appearance ──
        clayout.addWidget(self._section_label("🎨 Appearance"))
        # Theme
        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("Theme:"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["default", "neon", "glass", "pill", "dark", "cyberpunk"])
        theme_row.addWidget(self.theme_combo, 1)
        clayout.addLayout(theme_row)
        # Font size
        font_row = QHBoxLayout()
        font_row.addWidget(QLabel("ขนาด Font:"))
        self.font_size = QSpinBox()
        self.font_size.setRange(8, 40)
        self.font_size.setValue(16)
        font_row.addWidget(self.font_size)
        font_row.addWidget(QLabel("px"))
        font_row.addStretch()
        clayout.addLayout(font_row)
        # Max messages
        max_row = QHBoxLayout()
        max_row.addWidget(QLabel("ข้อความสูงสุด:"))
        self.max_messages = QSpinBox()
        self.max_messages.setRange(3, 50)
        self.max_messages.setValue(10)
        max_row.addWidget(self.max_messages)
        max_row.addStretch()
        clayout.addLayout(max_row)
        # Opacity
        opa_row = QHBoxLayout()
        opa_row.addWidget(QLabel("ความโปร่งใส:"))
        self.opacity = QSlider(Qt.Horizontal)
        self.opacity.setRange(20, 100)
        self.opacity.setValue(85)
        self.opacity_val = QLabel("85%")
        self.opacity.valueChanged.connect(lambda v: self.opacity_val.setText(f"{v}%"))
        opa_row.addWidget(self.opacity, 1)
        opa_row.addWidget(self.opacity_val)
        clayout.addLayout(opa_row)

        # ── Demo Loop ──
        clayout.addSpacing(8)
        clayout.addWidget(self._section_label("🎬 Demo Loop"))
        demo_row = QHBoxLayout()
        demo_row.addWidget(QLabel("ช่วงเวลา (วินาที):"))
        self.demo_interval = QDoubleSpinBox()
        self.demo_interval.setRange(0.5, 60.0)
        self.demo_interval.setValue(5.0)
        self.demo_interval.setSingleStep(0.5)
        demo_row.addWidget(self.demo_interval)
        demo_row.addStretch()
        clayout.addLayout(demo_row)
        # Start/stop demo button
        self.demo_btn = QPushButton("🎬 เริ่ม Loop Demo")
        self.demo_btn.setMinimumHeight(36)
        self.demo_btn.clicked.connect(self._toggle_demo)
        clayout.addWidget(self.demo_btn)

        # ── Position ──
        clayout.addSpacing(8)
        clayout.addWidget(self._section_label("📍 ตำแหน่ง"))
        pos_row = QHBoxLayout()
        pos_row.addWidget(QLabel("X:"))
        self.pos_x = QSpinBox()
        self.pos_x.setRange(-1, 9999)
        self.pos_x.setValue(-1)
        pos_row.addWidget(self.pos_x)
        pos_row.addWidget(QLabel("Y:"))
        self.pos_y = QSpinBox()
        self.pos_y.setRange(-1, 9999)
        self.pos_y.setValue(-1)
        pos_row.addWidget(self.pos_y)
        pos_row.addWidget(QLabel("W:"))
        self.pos_w = QSpinBox()
        self.pos_w.setRange(100, 9999)
        self.pos_w.setValue(360)
        pos_row.addWidget(self.pos_w)
        pos_row.addWidget(QLabel("H:"))
        self.pos_h = QSpinBox()
        self.pos_h.setRange(100, 9999)
        self.pos_h.setValue(500)
        pos_row.addWidget(self.pos_h)
        clayout.addLayout(pos_row)

        clayout.addStretch()

        # ★ Bottom buttons
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        bottom = QFrame()
        bottom.setFixedHeight(50)
        bottom.setStyleSheet("background: #131726; border-top: 1px solid #2a2f45;")
        blayout = QHBoxLayout(bottom)
        blayout.setContentsMargins(16, 0, 16, 0)
        blayout.addStretch()
        btn_save = QPushButton("💾 บันทึก")
        btn_save.setObjectName("Primary")
        btn_save.setFixedWidth(100)
        btn_save.clicked.connect(self._save)
        btn_close = QPushButton("ปิด")
        btn_close.setFixedWidth(80)
        btn_close.clicked.connect(self.reject)
        blayout.addWidget(btn_close)
        blayout.addWidget(btn_save)
        layout.addWidget(bottom)

    def _section_label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet("font-size: 14px; font-weight: 700; color: #f59e0b;")
        return lbl

    def _load_values(self):
        if not self.settings:
            return
        s = self.settings
        # theme
        theme = getattr(s, 'game_overlay_theme', 'default')
        idx = self.theme_combo.findText(theme)
        if idx >= 0: self.theme_combo.setCurrentIndex(idx)
        self.font_size.setValue(getattr(s, 'game_overlay_font_size', 16))
        self.max_messages.setValue(getattr(s, 'game_overlay_max_messages', 10))
        self.opacity.setValue(int(getattr(s, 'game_overlay_alpha', 0.85) * 100))
        self.demo_interval.setValue(getattr(s, 'game_overlay_demo_interval', 5.0))
        self.pos_x.setValue(getattr(s, 'game_overlay_x', -1))
        self.pos_y.setValue(getattr(s, 'game_overlay_y', -1))
        self.pos_w.setValue(getattr(s, 'game_overlay_width', 360))
        self.pos_h.setValue(getattr(s, 'game_overlay_height', 500))

    def _toggle_demo(self):
        """toggle demo loop"""
        if not self.parent_app:
            return
        go = getattr(self.parent_app, '_game_overlay', None)
        if go and go.is_running:
            if getattr(go, '_demo_running_state', False):
                go.stop_demo()
                go._demo_running_state = False
                self.demo_btn.setText("🎬 เริ่ม Loop Demo")
            else:
                interval = self.demo_interval.value()
                go.start_demo(interval)
                go._demo_running_state = True
                self.demo_btn.setText("⏹ หยุด Loop Demo")

    def _save(self):
        if not self.settings:
            self.accept()
            return
        s = self.settings
        s.game_overlay_theme = self.theme_combo.currentText()
        s.game_overlay_font_size = self.font_size.value()
        s.game_overlay_max_messages = self.max_messages.value()
        s.game_overlay_alpha = self.opacity.value() / 100.0
        s.game_overlay_demo_interval = self.demo_interval.value()
        s.game_overlay_x = self.pos_x.value()
        s.game_overlay_y = self.pos_y.value()
        s.game_overlay_width = self.pos_w.value()
        s.game_overlay_height = self.pos_h.value()
        try:
            from settings import save_settings
            save_settings(s)
        except Exception as e:
            logger.error(f"Save failed: {e}")
        # ★ update overlay if running
        go = getattr(self.parent_app, '_game_overlay', None)
        if go and go.is_running:
            go.update_settings()
        self.accept()
