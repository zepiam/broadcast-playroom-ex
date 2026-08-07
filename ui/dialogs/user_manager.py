"""user_manager.py — User Manager dialog

จัดการผู้ใช้: เปลี่ยนชื่อ / Block / Force translate / TTS rename + ดูประวัติ
"""
import logging
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QDialog, QWidget, QFrame, QLabel, QPushButton, QLineEdit, QVBoxLayout,
    QHBoxLayout, QScrollArea, QListWidget, QListWidgetItem, QComboBox,
    QCheckBox, QMessageBox, QSplitter, QGroupBox,
)

logger = logging.getLogger("user_manager")


class UserRow(QFrame):
    """แถวผู้ใช้เดียว"""

    def __init__(self, username, data, parent_dialog, parent=None):
        super().__init__(parent)
        self.username = username
        self.data = data or {}
        self.parent_dialog = parent_dialog
        self.setObjectName("Card")
        self.setFixedHeight(48)
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(8)

        # ★ Username
        name = QLabel(self.username)
        name.setStyleSheet("font-weight: 600; color: #e5e7eb;")
        name.setMinimumWidth(120)
        layout.addWidget(name)

        # ★ Display name (rename)
        display = self.data.get('display', '') or self.username
        self.display_entry = QLineEdit(display)
        self.display_entry.setPlaceholderText("ชื่อที่แสดง")
        self.display_entry.setFixedHeight(28)
        layout.addWidget(self.display_entry, 1)

        # ★ TTS name
        tts_name = self.data.get('read', '') or ''
        self.tts_entry = QLineEdit(tts_name)
        self.tts_entry.setPlaceholderText("ชื่อที่อ่าน TTS")
        self.tts_entry.setFixedHeight(28)
        self.tts_entry.setMaximumWidth(120)
        layout.addWidget(self.tts_entry)

        # ★ Block checkbox
        self.block_cb = QCheckBox("บล็อก")
        self.block_cb.setChecked(self.username in getattr(self.parent_dialog, '_blocked', set()))
        layout.addWidget(self.block_cb)


class UserManagerDialog(QDialog):
    """User Manager — จัดการผู้ใช้ทั้งหมด"""

    def __init__(self, parent_app):
        super().__init__(parent_app if isinstance(parent_app, QWidget) else None)
        self.parent_app = parent_app
        self.settings = getattr(parent_app, 'settings', None)
        self.setWindowTitle("👤 User Manager")
        self.setGeometry(180, 120, 800, 600)
        self.setMinimumSize(600, 400)
        self._blocked = set()
        self._rows = []
        self._build_ui()
        self._load_users()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ★ Header
        header = QFrame()
        header.setFixedHeight(50)
        header.setStyleSheet("background-color: #131726; border-bottom: 1px solid #2a2f45;")
        hlayout = QHBoxLayout(header)
        hlayout.setContentsMargins(16, 0, 16, 0)
        title = QLabel("👤 User Manager")
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #f59e0b;")
        hlayout.addWidget(title)
        hlayout.addStretch()
        # ★ Search
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍 ค้นหาผู้ใช้...")
        self.search.setFixedWidth(200)
        self.search.textChanged.connect(self._filter)
        hlayout.addWidget(self.search)
        layout.addWidget(header)

        # ★ Users list
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(16, 12, 16, 12)
        self.container_layout.setSpacing(4)
        self.container_layout.addStretch()
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll, 1)

        # ★ Bottom bar
        bottom = QFrame()
        bottom.setFixedHeight(50)
        bottom.setStyleSheet("background-color: #131726; border-top: 1px solid #2a2f45;")
        bottom_layout = QHBoxLayout(bottom)
        bottom_layout.setContentsMargins(16, 0, 16, 0)
        self.count_label = QLabel("0 ผู้ใช้")
        self.count_label.setStyleSheet("color: #9ca3af;")
        bottom_layout.addWidget(self.count_label)
        bottom_layout.addStretch()
        btn_save = QPushButton("💾 บันทึก")
        btn_save.setObjectName("Primary")
        btn_save.setFixedWidth(100)
        btn_save.clicked.connect(self._save)
        btn_close = QPushButton("ปิด")
        btn_close.setFixedWidth(80)
        btn_close.clicked.connect(self.reject)
        bottom_layout.addWidget(btn_save)
        bottom_layout.addWidget(btn_close)
        layout.addWidget(bottom)

    def _load_users(self):
        """โหลดผู้ใช้จาก settings"""
        if not self.settings:
            return
        # ★ renames + tts_renames + blocked_users
        renames = getattr(self.settings, 'user_renames', {}) or {}
        tts_renames = getattr(self.settings, 'tts_renames', {}) or {}
        self._blocked = set(getattr(self.settings, 'blocked_users', []) or [])

        # ★ รวมผู้ใช้ทั้งหมด
        all_users = set(renames.keys()) | set(tts_renames.keys()) | self._blocked
        self._users = {}
        for u in all_users:
            self._users[u] = {
                'display': renames.get(u, ''),
                'read': tts_renames.get(u, ''),
            }
        self._render_users()

    def _render_users(self):
        """render user rows"""
        # clear
        for row in self._rows:
            row.deleteLater()
        self._rows.clear()

        search = self.search.text().lower().strip()
        for username, data in sorted(self._users.items()):
            if search and search not in username.lower():
                continue
            row = UserRow(username, data, self, self.container)
            self.container_layout.insertWidget(self.container_layout.count() - 1, row)
            self._rows.append(row)

        self.count_label.setText(f"{len(self._rows)} ผู้ใช้")

    def _filter(self):
        self._render_users()

    def _save(self):
        """บันทึกการเปลี่ยนแปลง"""
        if not self.settings:
            self.accept()
            return
        renames = {}
        tts_renames = {}
        blocked = []
        for row in self._rows:
            u = row.username
            display = row.display_entry.text().strip()
            tts = row.tts_entry.text().strip()
            if display and display != u:
                renames[u] = display
            if tts:
                tts_renames[u] = tts
            if row.block_cb.isChecked():
                blocked.append(u)
        self.settings.user_renames = renames
        self.settings.tts_renames = tts_renames
        self.settings.blocked_users = blocked
        try:
            from settings import save_settings
            save_settings(self.settings)
        except Exception as e:
            logger.error(f"Failed to save: {e}")
        self.accept()
