"""voice_downloader.py — Voice Downloader dialog (RVC models)"""
import logging
import threading
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QDialog, QWidget, QFrame, QLabel, QPushButton, QLineEdit, QVBoxLayout,
    QHBoxLayout, QScrollArea, QProgressBar, QComboBox,
)
from ui.theme import COLOR_CARD, COLOR_BORDER, COLOR_ACCENT

logger = logging.getLogger("voice_downloader")


class VoiceRow(QFrame):
    """แถวเสียงเดียว (ชื่อ + ปุ่มดาวน์โหลด/ลบ)"""

    def __init__(self, voice, on_download, on_delete, parent=None):
        super().__init__(parent)
        self.voice = voice
        self.setObjectName("Card")
        self.setFixedHeight(52)
        self._build_ui(voice, on_download, on_delete)

    def _build_ui(self, voice, on_download, on_delete):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(10)

        # ★ Name + category
        name = getattr(voice, 'name', '?')
        category = getattr(voice, 'category', '')
        size_mb = getattr(voice, 'size', 0) // (1024 * 1024) if getattr(voice, 'size', 0) else 0
        info = QVBoxLayout()
        info.setSpacing(0)
        name_label = QLabel(name)
        name_label.setStyleSheet("font-weight: 600; color: #e5e7eb;")
        meta = f"{category}"
        if size_mb:
            meta += f" • {size_mb} MB"
        cat_label = QLabel(meta)
        cat_label.setStyleSheet("font-size: 11px; color: #6b7280;")
        info.addWidget(name_label)
        info.addWidget(cat_label)
        layout.addLayout(info, 1)

        # ★ Downloaded state
        from voice_downloader import is_voice_downloaded
        self.downloaded = False
        try:
            self.downloaded = is_voice_downloaded(voice)
        except Exception:
            pass

        self.btn = QPushButton()
        self.btn.setFixedHeight(30)
        self.btn.setFixedWidth(80)
        self.btn.setCursor(Qt.PointingHandCursor)
        if self.downloaded:
            self.btn.setText("🗑 ลบ")
            self.btn.setObjectName("Danger")
            self.btn.clicked.connect(lambda: on_delete(voice, self))
        else:
            self.btn.setText("⬇ ดาวน์โหลด")
            self.btn.setObjectName("Primary")
            self.btn.clicked.connect(lambda: on_download(voice, self))
        layout.addWidget(self.btn)


class VoiceDownloaderDialog(QDialog):
    """Voice Downloader — เลือก + ดาวน์โหลด RVC models"""

    def __init__(self, parent_app):
        super().__init__(parent_app if isinstance(parent_app, QWidget) else None)
        self.parent_app = parent_app
        self.setWindowTitle("⬇️ ดาวน์โหลดเสียง RVC")
        self.setGeometry(200, 100, 640, 640)
        self.setMinimumSize(480, 480)
        self._voices = []
        self._build_ui()
        # ★ fetch catalog async
        QTimer.singleShot(100, self._fetch_catalog)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ★ Header
        header = QFrame()
        header.setFixedHeight(80)
        header.setStyleSheet(f"background-color: {COLOR_CARD}; border-bottom: 1px solid {COLOR_BORDER};")
        hlayout = QHBoxLayout(header)
        hlayout.setContentsMargins(16, 12, 16, 12)
        title = QLabel("⬇️ ดาวน์โหลดเสียง RVC")
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #f59e0b;")
        hlayout.addWidget(title)
        hlayout.addStretch()
        # ★ Search
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍 ค้นหา...")
        self.search.setFixedWidth(200)
        self.search.textChanged.connect(self._filter)
        hlayout.addWidget(self.search)
        # ★ Refresh
        btn_refresh = QPushButton("🔄")
        btn_refresh.setObjectName("IconButton")
        btn_refresh.setFixedSize(36, 36)
        btn_refresh.clicked.connect(lambda: QTimer.singleShot(100, self._fetch_catalog))
        hlayout.addWidget(btn_refresh)
        layout.addWidget(header)

        # ★ Category tabs
        tab_row = QHBoxLayout()
        tab_row.setContentsMargins(16, 8, 16, 8)
        self.category_combo = QComboBox()
        self.category_combo.addItems(["ทั้งหมด", "vtuber", "anime", "genshin"])
        self.category_combo.currentIndexChanged.connect(self._filter)
        tab_row.addWidget(QLabel("หมวด:"))
        tab_row.addWidget(self.category_combo)
        tab_row.addStretch()
        self.count_label = QLabel("0 เสียง")
        self.count_label.setStyleSheet("color: #9ca3af; font-size: 12px;")
        tab_row.addWidget(self.count_label)
        layout.addLayout(tab_row)

        # ★ Scroll area for voice list
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(16, 0, 16, 16)
        self.container_layout.setSpacing(4)
        self.container_layout.addStretch()
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll, 1)

    def _fetch_catalog(self):
        """ดึง catalog จาก HuggingFace (async)"""
        def _bg_fetch():
            try:
                from voice_downloader import get_catalog_voices
                voices = get_catalog_voices()
                QTimer.singleShot(0, lambda: self._on_catalog_ready(voices))
            except Exception as e:
                logger.error(f"Failed to fetch catalog: {e}")
                QTimer.singleShot(0, lambda: self.count_label.setText(f"❌ โหลดไม่ได้: {e}"))

        threading.Thread(target=_bg_fetch, daemon=True).start()

    def _on_catalog_ready(self, voices):
        self._voices = voices
        self._render_voices()

    def _render_voices(self):
        """render voice rows ตาม filter"""
        # clear existing
        while self.container_layout.count() > 1:
            item = self.container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        search = self.search.text().lower().strip()
        cat = self.category_combo.currentText()
        filtered = []
        for v in self._voices:
            name = getattr(v, 'name', '').lower()
            vcat = getattr(v, 'category', '')
            if search and search not in name:
                continue
            if cat != "ทั้งหมด" and vcat != cat:
                continue
            filtered.append(v)

        for v in filtered:
            row = VoiceRow(v, self._on_download, self._on_delete, self.container)
            self.container_layout.insertWidget(self.container_layout.count() - 1, row)

        self.count_label.setText(f"{len(filtered)} เสียง")

    def _filter(self):
        if self._voices:
            self._render_voices()

    def _on_download(self, voice, row):
        """ดาวน์โหลดเสียง"""
        row.btn.setText("... กำลังโหลด")
        row.btn.setEnabled(False)

        def _bg_download():
            try:
                from voice_downloader import download_voice
                download_voice(voice)
                QTimer.singleShot(0, lambda: self._on_download_done(voice, row, True))
            except Exception as e:
                logger.error(f"Download failed: {e}")
                QTimer.singleShot(0, lambda: self._on_download_done(voice, row, False, str(e)))

        threading.Thread(target=_bg_download, daemon=True).start()

    def _on_download_done(self, voice, row, success, error=""):
        if success:
            row.btn.setText("🗑 ลบ")
            row.btn.setObjectName("Danger")
            row.btn.setEnabled(True)
            row.downloaded = True
        else:
            row.btn.setText("❌ ล้มเหลว")
            QTimer.singleShot(2000, lambda: row.btn.setText("⬇ ดาวน์โหลด"))
            row.btn.setEnabled(True)
        # refresh style
        row.btn.style().unpolish(row.btn)
        row.btn.style().polish(row.btn)

    def _on_delete(self, voice, row):
        """ลบเสียง"""
        try:
            from voice_downloader import delete_voice
            delete_voice(voice)
            row.btn.setText("⬇ ดาวน์โหลด")
            row.btn.setObjectName("Primary")
            row.btn.setEnabled(True)
            row.downloaded = False
            row.btn.style().unpolish(row.btn)
            row.btn.style().polish(row.btn)
        except Exception as e:
            logger.error(f"Delete failed: {e}")
