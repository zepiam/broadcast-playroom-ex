"""author_modal.py — Author Modal (คลิกชื่อผู้ชมในแชท → ดูโปรไฟล์)

ตัวห่อบางๆ รอบ UserProfilePanel — ใช้แผงเดียวกับลิ้นชักใน User Manager
(หน้าตาและฟีเจอร์ตรงกันทุกที่: สถิติ / ข้อความ / สนับสนุน / เปลี่ยนชื่อ / บล็อก / บังคับแปล / export / ลบ)
"""
import logging

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QDialog, QVBoxLayout, QWidget

import ui.theme as theme
from ui.widgets.user_profile import UserProfilePanel

logger = logging.getLogger("author_modal")


class AuthorModal(QDialog):
    def __init__(self, parent_app, author: str):
        super().__init__(parent_app if isinstance(parent_app, QWidget) else None)
        self.parent_app = parent_app
        self.author = author
        self.setWindowTitle(f"👤 {author}")
        self.setFixedWidth(480)
        # ไม่ให้สูงเกินหน้าจอ (โน้ตบุ๊ก 1366x768 / จอที่มี taskbar) — โปรไฟล์ยาวเลื่อนดูได้อยู่แล้ว
        scr = parent_app.screen() if isinstance(parent_app, QWidget) else QGuiApplication.primaryScreen()
        avail = scr.availableGeometry().height() if scr is not None else 800
        self.setMinimumHeight(min(640, max(420, avail - 110)))
        self.resize(480, min(740, max(480, avail - 90)))
        self.setStyleSheet(f"QDialog {{ background-color: {theme.COLOR_CARD}; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.panel = UserProfilePanel(parent_app, show_close=True)
        self.panel.closeRequested.connect(self.reject)
        self.panel.dataDeleted.connect(self.reject)
        lay.addWidget(self.panel)
        self.panel.set_user(author)

    def keyPressEvent(self, e):
        from PySide6.QtCore import Qt
        if e.key() == Qt.Key_Escape and self.panel.cancel_edit():
            e.accept()
            return
        super().keyPressEvent(e)
