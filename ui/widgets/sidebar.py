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
    """Card สำหรับแพลตฟอร์มเดียว (logo + name + connect/disconnect button)"""

    connect_requested = Signal(str)  # platform key
    disconnect_requested = Signal(str)

    def __init__(self, platform_key, label, icon="📺", parent=None):
        super().__init__(parent)
        self.platform_key = platform_key
        self.setObjectName("Card")
        self.setFixedHeight(56)
        self._build_ui(label, icon)

    def _build_ui(self, label, icon):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        # ★ Icon
        icon_label = QLabel(icon)
        icon_label.setStyleSheet("font-size: 20px;")
        icon_label.setFixedWidth(28)
        layout.addWidget(icon_label)

        # ★ Name + status
        info = QVBoxLayout()
        info.setSpacing(0)
        self.name_label = QLabel(label)
        self.name_label.setStyleSheet("font-weight: 600; color: #e5e7eb;")
        self.status_label = QLabel("ยังไม่เชื่อมต่อ")
        self.status_label.setStyleSheet("font-size: 11px; color: #6b7280;")
        info.addWidget(self.name_label)
        info.addWidget(self.status_label)
        layout.addLayout(info, 1)

        # ★ Connect button
        self.btn = QPushButton("เชื่อมต่อ")
        self.btn.setFixedHeight(28)
        self.btn.setCursor(Qt.PointingHandCursor)
        self.btn.clicked.connect(self._on_btn)
        layout.addWidget(self.btn)

    def _on_btn(self):
        if self.btn.text() == "เชื่อมต่อ":
            self.connect_requested.emit(self.platform_key)
        else:
            self.disconnect_requested.emit(self.platform_key)

    def set_connected(self, connected):
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


class Sidebar(QScrollArea):
    """Left sidebar — platforms list + voice panel"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFixedWidth(260)
        self._build_ui()

    def _build_ui(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # ★ Platforms header
        header = QLabel("🔌 แพลตฟอร์ม")
        header.setObjectName("Heading")
        layout.addWidget(header)

        # ★ Platform cards (dynamic)
        self.platforms_container = QVBoxLayout()
        self.platforms_container.setSpacing(6)
        layout.addLayout(self.platforms_container)

        # ★ Separator
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background-color: {COLOR_BORDER};")
        layout.addWidget(sep)

        # ★ Voice header
        voice_header = QLabel("🎤 เสียง")
        voice_header.setObjectName("Heading")
        layout.addWidget(voice_header)

        # ★ Voice selector
        voice_row = QHBoxLayout()
        self.voice_combo = QComboBox()
        self.voice_combo.addItem("Premwadee (edge-tts)")
        voice_row.addWidget(self.voice_combo, 1)
        self.voice_download_btn = QPushButton("⬇")
        self.voice_download_btn.setObjectName("IconButton")
        self.voice_download_btn.setFixedSize(32, 32)
        voice_row.addWidget(self.voice_download_btn)
        layout.addLayout(voice_row)

        # ★ Volume slider
        layout.addSpacing(4)
        vol_label = QLabel("Volume")
        vol_label.setObjectName("Dim")
        layout.addWidget(vol_label)
        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(100)
        layout.addWidget(self.vol_slider)

        # ★ Rate slider
        rate_label = QLabel("Rate")
        rate_label.setObjectName("Dim")
        layout.addWidget(rate_label)
        self.rate_slider = QSlider(Qt.Horizontal)
        self.rate_slider.setRange(-50, 50)
        self.rate_slider.setValue(0)
        layout.addWidget(self.rate_slider)

        layout.addStretch()
        self.setWidget(container)

    def add_platform(self, key, label, icon="📺"):
        """เพิ่ม platform card เข้า sidebar"""
        card = PlatformCard(key, label, icon, self)
        self.platforms_container.addWidget(card)
        return card
