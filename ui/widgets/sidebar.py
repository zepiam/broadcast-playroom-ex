"""sidebar.py — Left sidebar (platforms + voice panel)"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QScrollArea,
    QWidget, QComboBox, QSlider, QSizePolicy,
)
from ui.theme import (
    COLOR_CARD, COLOR_CARD_HI, COLOR_ACCENT, COLOR_HEADING,
    COLOR_TEXT, COLOR_TEXT_DIM, COLOR_BORDER,
)


class PlatformCard(QFrame):
    """Card สำหรับแพลตฟอร์มเดียว (logo + name + connect/disconnect + mute + volume)"""

    connect_requested = Signal(str)  # platform key
    disconnect_requested = Signal(str)
    mute_toggled = Signal(str, bool)  # platform, muted
    volume_changed = Signal(str, int)  # platform, volume

    def __init__(self, platform_key, label, icon="📺", parent=None):
        super().__init__(parent)
        self.platform_key = platform_key
        self.setObjectName("Card")
        self._connected = False
        self._muted = False
        self._build_ui(label, icon)
        # ★ ใช้ minimum height แทน fixed (ให้ขยายได้ตามเนื้อหา)
        self.setMinimumHeight(80)

    def _build_ui(self, label, icon):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(4)

        # ★ Row 1: icon + name + status + connect button
        row1 = QHBoxLayout()
        row1.setSpacing(8)
        icon_label = QLabel(icon)
        icon_label.setStyleSheet("font-size: 18px;")
        icon_label.setFixedWidth(24)
        row1.addWidget(icon_label)

        info = QVBoxLayout()
        info.setSpacing(0)
        self.name_label = QLabel(label)
        self.name_label.setStyleSheet("font-weight: 600; color: #e5e7eb; font-size: 13px;")
        self.status_label = QLabel("ยังไม่เชื่อมต่อ")
        self.status_label.setStyleSheet("font-size: 11px; color: #6b7280;")
        info.addWidget(self.name_label)
        info.addWidget(self.status_label)
        row1.addLayout(info, 1)

        # ★ Connect/disconnect button
        self.btn = QPushButton("เชื่อมต่อ")
        self.btn.setFixedHeight(26)
        self.btn.setFixedWidth(70)
        self.btn.setCursor(Qt.PointingHandCursor)
        self.btn.clicked.connect(self._on_btn)
        row1.addWidget(self.btn)
        layout.addLayout(row1)

        # ★ Row 2: mute + volume (แสดงตอน connected)
        row2 = QHBoxLayout()
        row2.setSpacing(6)
        self.mute_btn = QPushButton("🔊")
        self.mute_btn.setObjectName("IconButton")
        self.mute_btn.setFixedSize(28, 24)
        self.mute_btn.setCursor(Qt.PointingHandCursor)
        self.mute_btn.setToolTip("ปิดเสียง TTS ของแพลตฟอร์มนี้")
        self.mute_btn.clicked.connect(self._on_mute)
        row2.addWidget(self.mute_btn)

        vol_label = QLabel("Vol")
        vol_label.setStyleSheet("font-size: 10px; color: #6b7280;")
        row2.addWidget(vol_label)

        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(100)
        self.vol_slider.setFixedHeight(16)
        self.vol_slider.valueChanged.connect(lambda v: self.volume_changed.emit(self.platform_key, v))
        row2.addWidget(self.vol_slider, 1)
        layout.addLayout(row2)

    def _on_btn(self):
        if self.btn.text() in ("เชื่อมต่อ", "ลองใหม่"):
            self.connect_requested.emit(self.platform_key)
        else:
            self.disconnect_requested.emit(self.platform_key)

    def _on_mute(self):
        self._muted = not getattr(self, '_muted', False)
        self.mute_btn.setText("🔇" if self._muted else "🔊")
        self.mute_toggled.emit(self.platform_key, self._muted)

    def set_connecting(self):
        """แสดงสถานะกำลังเชื่อมต่อ"""
        self.btn.setText("...")
        self.btn.setEnabled(False)
        self.status_label.setText("กำลังเชื่อมต่อ...")
        self.status_label.setStyleSheet("font-size: 11px; color: #f59e0b;")

    def set_connected(self, connected):
        """อัปเดตสถานะ"""
        self._connected = connected
        self.btn.setEnabled(True)
        if connected:
            self.btn.setText("หยุด")
            self.btn.setObjectName("Danger")
            self.status_label.setText("เชื่อมต่อแล้ว")
            self.status_label.setStyleSheet("font-size: 11px; color: #10b981;")
        else:
            self.btn.setText("เชื่อมต่อ")
            self.btn.setObjectName("")
            self.status_label.setText("ยังไม่เชื่อมต่อ")
            self.status_label.setStyleSheet("font-size: 11px; color: #6b7280;")
        # refresh style
        self.btn.style().unpolish(self.btn)
        self.btn.style().polish(self.btn)


class Sidebar(QFrame):
    """Left sidebar — platforms list + voice panel"""

    toggle_requested = Signal()  # ซ่อน/แสดง sidebar

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setMinimumWidth(280)
        self.setMaximumWidth(320)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ★ Scrollable content
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        clayout = QVBoxLayout(container)
        clayout.setContentsMargins(10, 10, 10, 10)
        clayout.setSpacing(8)

        # ★ Platforms header (with toggle button)
        ph = QHBoxLayout()
        ph.setContentsMargins(0, 0, 0, 0)
        header = QLabel("🔌 แพลตฟอร์ม")
        header.setObjectName("Heading")
        header.setStyleSheet("font-size: 14px; font-weight: 700; color: #f59e0b;")
        ph.addWidget(header)
        ph.addStretch()
        # ★ Settings gear for platform selection
        self.gear_btn = QPushButton("⚙")
        self.gear_btn.setObjectName("IconButton")
        self.gear_btn.setFixedSize(24, 24)
        self.gear_btn.setCursor(Qt.PointingHandCursor)
        self.gear_btn.setToolTip("ตั้งค่าแพลตฟอร์ม")
        ph.addWidget(self.gear_btn)
        clayout.addLayout(ph)

        # ★ Platform cards (dynamic)
        self.platforms_container = QVBoxLayout()
        self.platforms_container.setSpacing(6)
        clayout.addLayout(self.platforms_container)

        # ★ Separator
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background-color: {COLOR_BORDER};")
        clayout.addWidget(sep)

        # ★ Voice header
        voice_header = QLabel("🎤 เสียง")
        voice_header.setObjectName("Heading")
        voice_header.setStyleSheet("font-size: 14px; font-weight: 700; color: #f59e0b;")
        clayout.addWidget(voice_header)

        # ★ Voice selector
        voice_row = QHBoxLayout()
        self.voice_combo = QComboBox()
        self.voice_combo.addItem("Premwadee (edge-tts)")
        voice_row.addWidget(self.voice_combo, 1)
        self.voice_test_btn = QPushButton("🔊")
        self.voice_test_btn.setObjectName("IconButton")
        self.voice_test_btn.setFixedSize(32, 32)
        self.voice_test_btn.setCursor(Qt.PointingHandCursor)
        self.voice_test_btn.setToolTip("ทดสอบเสียง")
        voice_row.addWidget(self.voice_test_btn)
        self.voice_download_btn = QPushButton("⬇")
        self.voice_download_btn.setObjectName("IconButton")
        self.voice_download_btn.setFixedSize(32, 32)
        self.voice_download_btn.setCursor(Qt.PointingHandCursor)
        self.voice_download_btn.setToolTip("ดาวน์โหลดเสียง RVC")
        voice_row.addWidget(self.voice_download_btn)
        clayout.addLayout(voice_row)

        # ★ Volume slider
        clayout.addSpacing(4)
        vol_label = QLabel("Volume")
        vol_label.setStyleSheet("color: #9ca3af; font-size: 11px;")
        clayout.addWidget(vol_label)
        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(100)
        clayout.addWidget(self.vol_slider)

        # ★ Rate slider
        rate_label = QLabel("Rate")
        rate_label.setStyleSheet("color: #9ca3af; font-size: 11px;")
        clayout.addWidget(rate_label)
        self.rate_slider = QSlider(Qt.Horizontal)
        self.rate_slider.setRange(-50, 50)
        self.rate_slider.setValue(0)
        clayout.addWidget(self.rate_slider)

        clayout.addStretch()
        self.scroll.setWidget(container)
        layout.addWidget(self.scroll, 1)

    def add_platform(self, key, label, icon="📺"):
        """เพิ่ม platform card เข้า sidebar"""
        card = PlatformCard(key, label, icon, self)
        self.platforms_container.addWidget(card)
        return card
