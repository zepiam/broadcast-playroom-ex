"""user_manager.py — User Manager dialog (list view)

List รายชื่อ + stats summary + คลิก → เปิด Author Modal
"""
import logging
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QWidget, QFrame, QLabel, QPushButton, QLineEdit, QVBoxLayout,
    QHBoxLayout, QScrollArea, QCheckBox, QMessageBox,
)
from ui.theme import COLOR_CARD, COLOR_BORDER

logger = logging.getLogger("user_manager")


class UserListRow(QFrame):
    """แถว user ใน list — name + stats summary + ปุ่มดู"""

    def __init__(self, username, stats, parent_dialog, parent=None):
        super().__init__(parent)
        self.username = username
        self.stats = stats or {}
        self.parent_dialog = parent_dialog
        self.setObjectName("Card")
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        # Name
        name = QLabel(self.username)
        name.setStyleSheet("font-weight: 600; color: #e5e7eb; font-size: 14px;")
        name.setMinimumWidth(100)
        layout.addWidget(name)

        # Stats summary
        parts = []
        msg_count = self.stats.get('msg_count', 0)
        if msg_count:
            parts.append(f"💬 {msg_count}")
        evt_count = self.stats.get('event_count', 0)
        if evt_count:
            parts.append(f"🎉 {evt_count}")
        donate_str = self.stats.get('donate_str', '')
        if donate_str:
            parts.append(f"💎 {donate_str}")
        if parts:
            stats_label = QLabel(" · ".join(parts))
            stats_label.setStyleSheet("color: #9ca3af; font-size: 12px;")
            layout.addWidget(stats_label, 1)

        layout.addStretch()

        # Block indicator
        if self.username.lower() in getattr(self.parent_dialog, '_blocked', set()):
            block_label = QLabel("🚫")
            block_label.setStyleSheet("color: #ef4444; font-size: 14px;")
            layout.addWidget(block_label)

        # View button
        btn_view = QPushButton("👤")
        btn_view.setObjectName("IconButton")
        btn_view.setFixedSize(32, 28)
        btn_view.setCursor(Qt.PointingHandCursor)
        btn_view.setStyleSheet("font-size: 16px; padding: 0px;")
        btn_view.setToolTip("ดูข้อมูล")
        btn_view.clicked.connect(lambda: self.parent_dialog._open_user(self.username))
        layout.addWidget(btn_view)


class UserManagerDialog(QDialog):
    """User Manager — list รายชื่อ + คลิกเปิด Author Modal"""

    def __init__(self, parent_app):
        super().__init__(parent_app if isinstance(parent_app, QWidget) else None)
        self.parent_app = parent_app
        self.settings = getattr(parent_app, 'settings', None)
        self.setWindowTitle("👤 User Manager")
        self.setGeometry(180, 120, 600, 600)
        self.setMinimumSize(450, 350)
        self._blocked = set()
        self._rows = []
        self._build_ui()
        self._load_users()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QFrame()
        header.setFixedHeight(50)
        header.setStyleSheet(f"background-color: {COLOR_CARD}; border-bottom: 1px solid {COLOR_BORDER};")
        h = QHBoxLayout(header)
        h.setContentsMargins(16, 0, 16, 0)
        title = QLabel("👤 User Manager")
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #f59e0b;")
        h.addWidget(title)
        h.addStretch()
        # Search
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍 ค้นหา...")
        self.search.setFixedWidth(180)
        self.search.setFixedHeight(28)
        self.search.textChanged.connect(self._filter)
        h.addWidget(self.search)
        # Refresh
        self.btn_refresh = QPushButton("🔄")
        self.btn_refresh.setObjectName("IconButton")
        self.btn_refresh.setFixedSize(32, 32)
        self.btn_refresh.setStyleSheet("font-size: 14px; padding: 0px;")
        self.btn_refresh.clicked.connect(self._load_users)
        h.addWidget(self.btn_refresh)
        layout.addWidget(header)

        # List
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.container = QWidget()
        self.container.setStyleSheet("background: transparent;")
        self.cl = QVBoxLayout(self.container)
        self.cl.setContentsMargins(12, 8, 12, 8)
        self.cl.setSpacing(4)
        self.cl.addStretch()
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll, 1)

        # Bottom
        bottom = QFrame()
        bottom.setFixedHeight(40)
        bottom.setStyleSheet(f"background-color: {COLOR_CARD}; border-top: 1px solid {COLOR_BORDER};")
        bl = QHBoxLayout(bottom)
        bl.setContentsMargins(16, 0, 16, 0)
        self.count_label = QLabel("0 ผู้ใช้")
        self.count_label.setStyleSheet("color: #9ca3af;")
        bl.addWidget(self.count_label)
        bl.addStretch()
        btn_close = QPushButton("ปิด")
        btn_close.setFixedWidth(70)
        btn_close.clicked.connect(self.reject)
        bl.addWidget(btn_close)
        layout.addWidget(bottom)

    def _load_users(self):
        """โหลด users จาก message_history + donate + events + settings"""
        app = self.parent_app
        all_users = set()

        # renames + blocked
        renames = getattr(self.settings, 'user_renames', {}) or {}
        all_users.update(renames.keys())
        self._blocked = set()
        for b in (getattr(self.settings, 'blocked_users', []) or []):
            if isinstance(b, dict):
                self._blocked.add(b.get('name', '').lower())
            elif isinstance(b, str):
                self._blocked.add(b.lower())
        all_users.update(self._blocked)

        # message history
        if app and hasattr(app, 'message_history') and app.message_history:
            try:
                all_users.update(app.message_history.all_authors().keys())
            except Exception:
                pass

        # donate tracker
        if app and hasattr(app, 'donate_tracker') and app.donate_tracker:
            try:
                all_users.update(app.donate_tracker.all_users().keys())
            except Exception:
                pass

        # event log
        if app and hasattr(app, 'event_log') and app.event_log:
            try:
                for e in app.event_log.get_all():
                    if hasattr(e, 'author') and e.author:
                        all_users.add(e.author.lower())
            except Exception:
                pass

        # กรอง event types
        _fake = {'bits', 'donate', 'follow', 'gift', 'like', 'share', 'sub',
                 'resub', 'subgift', 'raid', 'superchat', 'membership', 'sponsor',
                 'tip', 'message', 'system', ''}
        all_users = {u for u in all_users if u and u not in _fake}

        # สร้าง stats สำหรับแต่ละ user
        self._users = {}
        for u in sorted(all_users):
            self._users[u] = self._get_stats(u)

        self._render()

    def _get_stats(self, username):
        """ดึง stats สั้นๆ สำหรับแสดงใน list"""
        app = self.parent_app
        stats = {'msg_count': 0, 'event_count': 0, 'donate_str': ''}

        if app and hasattr(app, 'message_history') and app.message_history:
            try:
                stats['msg_count'] = app.message_history.count(username)
            except Exception:
                pass

        if app and hasattr(app, 'event_log') and app.event_log:
            try:
                events = app.event_log.get_by_author(username)
                stats['event_count'] = len(events)
            except Exception:
                pass

        if app and hasattr(app, 'donate_tracker') and app.donate_tracker:
            try:
                donate = app.donate_tracker.get_user(username)
                total = donate.get('total_donate_count', 0)
                if total:
                    stats['donate_str'] = f"×{total}"
            except Exception:
                pass

        return stats

    def _render(self):
        """render list"""
        for row in self._rows:
            row.deleteLater()
        self._rows.clear()

        search = self.search.text().lower().strip()
        for username, stats in self._users.items():
            if search and search not in username.lower():
                # เช็คใน rename ด้วย
                renames = getattr(self.settings, 'user_renames', {}) or {}
                display = renames.get(username, '')
                if not display or search not in display.lower():
                    continue
            row = UserListRow(username, stats, self, self.container)
            self.cl.insertWidget(self.cl.count() - 1, row)
            self._rows.append(row)

        self.count_label.setText(f"{len(self._rows)} ผู้ใช้")

    def _filter(self):
        self._render()

    def _open_user(self, username):
        """เปิด Author Modal ของ user นี้"""
        from ui.dialogs.author_modal import AuthorModal
        dlg = AuthorModal(self.parent_app, username)
        dlg.exec()
        # refresh list หลังปิด (status อาจเปลี่ยน)
        self._load_users()
