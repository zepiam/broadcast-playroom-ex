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
        self.btn.setFixedHeight(30)
        self.btn.setMinimumWidth(90)
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
            self.btn.setText("หยุดเชื่อมต่อ")
            self.btn.setObjectName("Danger")
            self.status_label.setText("✅ เชื่อมต่อแล้ว")
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
        self.setMinimumWidth(290)
        self.setMaximumWidth(380)
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

        # ★ Platforms header (collapsible)
        ph = QHBoxLayout()
        ph.setContentsMargins(0, 0, 0, 0)
        ph.setSpacing(4)
        # ★ collapse toggle button
        self.platform_toggle = QPushButton("▼")
        self.platform_toggle.setObjectName("IconButton")
        self.platform_toggle.setFixedSize(20, 20)
        self.platform_toggle.setCursor(Qt.PointingHandCursor)
        self.platform_toggle.setStyleSheet("font-size: 11px; padding: 0px; margin: 0px;")
        self.platform_toggle.setToolTip("หด/ขยาย")
        ph.addWidget(self.platform_toggle)
        header = QLabel("🔌 แพลตฟอร์ม")
        header.setObjectName("Heading")
        header.setStyleSheet("font-size: 14px; font-weight: 700; color: #f59e0b;")
        ph.addWidget(header)
        ph.addStretch()
        # ★ connected count
        self.platform_count = QLabel("0/0")
        self.platform_count.setStyleSheet("color: #10b981; font-size: 11px; font-weight: 600;")
        ph.addWidget(self.platform_count)
        # ★ Settings gear
        self.gear_btn = QPushButton("⚙")
        self.gear_btn.setObjectName("IconButton")
        self.gear_btn.setFixedSize(28, 28)
        self.gear_btn.setCursor(Qt.PointingHandCursor)
        self.gear_btn.setToolTip("ตั้งค่าแพลตฟอร์ม")
        self.gear_btn.setStyleSheet("font-size: 16px; padding: 0px; margin: 0px;")
        ph.addWidget(self.gear_btn)
        clayout.addLayout(ph)

        # ★ Platform container (collapsible)
        self.platforms_container = QVBoxLayout()
        self.platforms_container.setSpacing(6)
        clayout.addLayout(self.platforms_container)

        # ★ Separator
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background-color: {COLOR_BORDER};")
        clayout.addWidget(sep)

        # ★ Voice header — สถานะ RVC อยู่ชิดขวา
        voice_header_row = QHBoxLayout()
        voice_header_row.setContentsMargins(0, 0, 0, 0)
        voice_header_row.setSpacing(4)
        voice_header = QLabel("🎤 เสียง")
        voice_header.setObjectName("Heading")
        voice_header.setStyleSheet("font-size: 14px; font-weight: 700; color: #f59e0b;")
        voice_header_row.addWidget(voice_header)
        voice_header_row.addStretch()
        # ★ RVC status label (ชิดขวา — เหมือน v1)
        self.rvc_status = QLabel("✅ Premwadee (edge-tts)")
        self.rvc_status.setStyleSheet("color: #10b981; font-size: 11px;")
        voice_header_row.addWidget(self.rvc_status)
        clayout.addLayout(voice_header_row)

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

        # ★ Rate slider (ความเร็วอ่าน)
        rate_label = QLabel("Speed (ความเร็ว)")
        rate_label.setStyleSheet("color: #9ca3af; font-size: 11px;")
        clayout.addWidget(rate_label)
        self.rate_slider = QSlider(Qt.Horizontal)
        self.rate_slider.setRange(-50, 50)
        self.rate_slider.setValue(0)
        clayout.addWidget(self.rate_slider)

        # ★ RVC controls (Pitch เท่านั้น — f0method ใช้ rmvpe default)
        self.rvc_controls = QWidget()
        rvc_layout = QVBoxLayout(self.rvc_controls)
        rvc_layout.setContentsMargins(0, 0, 0, 0)
        rvc_layout.setSpacing(2)
        # pitch slider
        pitch_label_row = QHBoxLayout()
        pitch_label = QLabel("Pitch (ระดับเสียง)")
        pitch_label.setStyleSheet("color: #9ca3af; font-size: 11px;")
        self.pitch_val_label = QLabel("+0")
        self.pitch_val_label.setStyleSheet("color: #06b6d4; font-size: 11px;")
        pitch_label_row.addWidget(pitch_label)
        pitch_label_row.addStretch()
        pitch_label_row.addWidget(self.pitch_val_label)
        rvc_layout.addLayout(pitch_label_row)
        self.pitch_slider = QSlider(Qt.Horizontal)
        self.pitch_slider.setRange(-24, 24)
        self.pitch_slider.setValue(0)
        self.pitch_slider.valueChanged.connect(lambda v: self.pitch_val_label.setText(f"{v:+d}"))
        rvc_layout.addWidget(self.pitch_slider)
        clayout.addWidget(self.rvc_controls)
        # ★ ซ่อน RVC controls ถ้าเป็น Lite (ไม่มี RVC)
        try:
            import rvc_engine
            self.rvc_controls.setVisible(True)
        except ImportError:
            self.rvc_controls.setVisible(False)

        clayout.addStretch()
        self.scroll.setWidget(container)
        layout.addWidget(self.scroll, 1)

    def add_platform(self, key, label, icon="📺"):
        """เพิ่ม platform card เข้า sidebar"""
        card = PlatformCard(key, label, icon, self)
        self.platforms_container.addWidget(card)
        return card

    def toggle_platforms(self):
        """หด/ขยาย section แพลตฟอร์ม"""
        self._platforms_collapsed = not getattr(self, '_platforms_collapsed', False)
        collapsed = self._platforms_collapsed
        self.platform_toggle.setText("▶" if collapsed else "▼")
        # ★ toggle visibility ของทุก card
        for i in range(self.platforms_container.count()):
            item = self.platforms_container.itemAt(i)
            if item.widget():
                item.widget().setVisible(not collapsed)

    def update_platform_count(self, connected, total):
        """อัปเดตตัวเลขจำนวนแพลตฟอร์มที่เชื่อมต่ออยู่"""
        color = "#10b981" if connected > 0 else "#6b7280"
        self.platform_count.setText(f"{connected}/{total}")
        self.platform_count.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: 600;")
