"""status_bar.py — Bottom status bar with progress bar"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QHBoxLayout, QProgressBar


class StatusBar(QFrame):
    """Bottom status bar — shows status text + progress bar (for OmniVoice loading)

    ★ Progress bar:
      - hidden by default (setVisible(False))
      - show_progress() → แสดง + เริ่มที่ 0%
      - set_progress(percent, text) → อัปเดต % + status text
      - hide_progress() → ซ่อน
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("StatusBar")
        self.setFixedHeight(26)
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(8)

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #9ca3af; font-size: 13px;")
        layout.addWidget(self.status_label)

        layout.addStretch()

        # ★ Progress bar (ฝั่งขวา — ก่อน version)
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(200)
        self.progress_bar.setFixedHeight(16)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setVisible(False)  # ★ hidden by default
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #1a1f33;
                border: 1px solid #2a2f45;
                border-radius: 8px;
                text-align: center;
                color: #e5e7eb;
                font-size: 11px;
                font-weight: 600;
            }
            QProgressBar::chunk {
                background-color: #10b981;
                border-radius: 7px;
            }
        """)
        layout.addWidget(self.progress_bar)

        self.version_label = QLabel("v2.0.0")
        self.version_label.setStyleSheet("color: #6b7280; font-size: 13px;")
        layout.addWidget(self.version_label)

    def set_status(self, msg):
        self.status_label.setText(msg)

    def set_version(self, ver):
        self.version_label.setText(ver)

    # ═══ Progress bar methods ═══
    def show_progress(self):
        """แสดง progress bar (เริ่มที่ 0%)"""
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)

    def hide_progress(self):
        """ซ่อน progress bar"""
        self.progress_bar.setVisible(False)

    def set_progress(self, percent: int, text: str = ""):
        """อัปเดต progress bar %

        Args:
            percent: 0-100
            text: stage text (แสดงใน status label ฝั่งซ้าย)
        """
        self.progress_bar.setValue(int(percent))
        self.progress_bar.setFormat(f"{percent}%")
        if text:
            self.status_label.setText(text)
