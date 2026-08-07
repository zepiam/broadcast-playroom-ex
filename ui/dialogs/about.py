"""about.py — About dialog"""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QFrame,
)
from PySide6.QtGui import QPixmap, QIcon
import os


class AboutDialog(QDialog):
    """About dialog — แสดงข้อมูลโปรแกรม + version"""

    def __init__(self, parent_app):
        super().__init__(parent_app if isinstance(parent_app, QWidget) else None)
        self.parent_app = parent_app
        self._click_count = 0
        self.setWindowTitle("ℹ️ เกี่ยวกับ")
        self.setFixedSize(420, 480)
        self.setModal(True)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignCenter)

        # ★ Icon (clickable 20x → Advanced Settings)
        icon_label = QLabel()
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setCursor(Qt.PointingHandCursor)
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        icon_path = os.path.join(base_dir, "assets", "icon.png")
        if os.path.exists(icon_path):
            pix = QPixmap(icon_path)
            if not pix.isNull():
                icon_label.setPixmap(pix.scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        icon_label.mousePressEvent = self._on_icon_click
        layout.addWidget(icon_label)

        # ★ Title
        title = QLabel("Broadcast Playroom")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #f59e0b;")
        layout.addWidget(title)

        # ★ Version
        version = "v2.0.0-dev (PySide6)"
        ver_label = QLabel(version)
        ver_label.setAlignment(Qt.AlignCenter)
        ver_label.setStyleSheet("color: #9ca3af; font-size: 13px;")
        layout.addWidget(ver_label)

        # ★ Separator
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #2a2f45;")
        layout.addWidget(sep)

        # ★ Description
        desc = QLabel(
            "โปรแกรม TTS สำหรับอ่านแชทสดจาก Twitch / YouTube / MyLive / TikTok / KICK\n"
            "ด้วย edge-tts และ RVC voice conversion\n\n"
            "สร้างโดย MeN9CH"
        )
        desc.setAlignment(Qt.AlignCenter)
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #e5e7eb; font-size: 13px;")
        layout.addWidget(desc)

        # ★ Links
        links = QLabel(
            "<a href='https://github.com/zepiam/broadcast-playroom' style='color: #7c3aed;'>GitHub</a>"
        )
        links.setAlignment(Qt.AlignCenter)
        links.setOpenExternalLinks(True)
        layout.addWidget(links)

        layout.addStretch()

        # ★ Close button
        btn_close = QPushButton("ปิด")
        btn_close.setObjectName("Primary")
        btn_close.setFixedWidth(100)
        btn_close.clicked.connect(self.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def _on_icon_click(self, event):
        """Secret: click icon 20x → open Advanced Settings"""
        self._click_count += 1
        if self._click_count >= 20:
            self._click_count = 0
            self._open_advanced_settings()

    def _open_advanced_settings(self):
        """เปิด Advanced Settings (hidden — dev mode)"""
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(self, "🎮 Advanced Settings", "Advanced Settings — เร็วๆ นี้")
