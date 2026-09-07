"""announcement_bar.py — แถบประกาศถึงผู้ใช้ (อยู่เหนือ footer/status bar)

แสดงข้อความประกาศจากเจ้าของโปรแกรม (ดึงจาก GitHub repo)
- สีตาม type: update=ส้ม, info=ฟ้า, warning=แดง
- ปุ่ม 🔗 เปิดลิงก์ (แสดงเมื่อ url ปลอดภัย — http/https เท่านั้น)
- ปุ่ม ✕ ปิด — app จะจำ id ที่ปิด (ประกาศใหม่ id ใหม่จะโผล่อีก)

ความปลอดภัย:
- ข้อความแสดงแบบ PlainText (กัน HTML/script injection)
- URL เปิดผ่าน QDesktopServices หลัง validate scheme อีกชั้น
"""
from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFrame, QLabel, QHBoxLayout, QPushButton

# สีตาม type — (พื้นหลัง, ขอบ, ตัวหนังสือ, icon)
_STYLES = {
    "update": ("rgba(245,158,11,0.18)", "rgba(245,158,11,0.55)", "#fbbf24", "📢"),
    "info": ("rgba(59,130,246,0.16)", "rgba(59,130,246,0.5)", "#60a5fa", "ℹ️"),
    "warning": ("rgba(239,68,68,0.18)", "rgba(239,68,68,0.55)", "#f87171", "⚠️"),
}


def _is_safe_url(url: str) -> bool:
    url = (url or "").strip()
    return url.startswith("http://") or url.startswith("https://")


class AnnouncementBar(QFrame):
    """แถบประกาศ — ซ่อน default แสดงเมื่อมีประกาศ"""

    # emit เมื่อ user กด ✕ (พร้อม id ของประกาศที่ปิด) — app เก็บ dismissed id
    dismissed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("AnnouncementBar")
        self.setFixedHeight(36)
        self._current_id = ""
        self._current_url = ""
        self._build_ui()
        self.setVisible(False)

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(8)

        self.icon_label = QLabel("📢")
        self.icon_label.setFixedWidth(22)

        self.text_label = QLabel("")
        self.text_label.setTextFormat(Qt.PlainText)  # ★ กัน rich-text injection
        self.text_label.setWordWrap(False)

        self.link_btn = QPushButton("🔗 เปิดลิงก์")
        self.link_btn.setCursor(Qt.PointingHandCursor)
        self.link_btn.setToolTip("")
        self.link_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.08);
                color: #93c5fd; border: 1px solid rgba(147,197,253,0.35);
                border-radius: 4px; padding: 2px 10px; font-size: 11px; font-weight: 600;
            }
            QPushButton:hover { background: rgba(147,197,253,0.18); }
        """)
        self.link_btn.setVisible(False)
        self.link_btn.clicked.connect(self._open_link)

        self.close_btn = QPushButton("X")
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setFixedSize(22, 22)
        self.close_btn.setToolTip("ปิดประกาศนี้")
        # ★ override global theme ด้วย padding/min-height = 0 — global บังคับ padding 8px 16px
        #   กินพื้นที่ปุ่มเล็กหมดจนตัวอักษร render ไม่ออก (เห็นแต่จุดกดได้เปล่าๆ)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: #ef4444; border: none;
                padding: 0; min-height: 0; min-width: 0; max-height: 22px; max-width: 22px;
                font-size: 16px; font-weight: 800;
            }
            QPushButton:hover { color: #fca5a5; }
        """)
        self.close_btn.clicked.connect(self._on_close)

        layout.addWidget(self.icon_label)
        layout.addWidget(self.text_label, 1)
        layout.addWidget(self.link_btn)
        layout.addWidget(self.close_btn)

        self._apply_type_style("info")

    def _apply_type_style(self, ann_type: str):
        bg, border, fg, _icon = _STYLES.get(ann_type, _STYLES["info"])
        self.setStyleSheet(f"""
            #AnnouncementBar {{
                background: {bg};
                border-top: 1px solid {border};
                border-bottom: 1px solid {border};
            }}
        """)
        self.text_label.setStyleSheet(f"color: {fg}; font-size: 13px; font-weight: 600;")

    def show_announcement(self, ann: dict):
        """แสดงประกาศ — ann = {id, text, type, url} (sanitize แล้วจาก announcement.py)"""
        if not ann or not ann.get("id") or not ann.get("text"):
            self.setVisible(False)
            return
        self._current_id = str(ann.get("id", ""))
        self._current_url = ann.get("url") or ""
        ann_type = ann.get("type") if ann.get("type") in _STYLES else "info"

        icon = _STYLES.get(ann_type, _STYLES["info"])[3]
        self.icon_label.setText(icon)
        self.text_label.setText(str(ann.get("text", "")))  # PlainText อยู่แล้ว
        self._apply_type_style(ann_type)

        # ★ ปุ่มลิงก์ — แสดงเฉพาะ URL ที่ผ่าน validation เท่านั้น
        if _is_safe_url(self._current_url):
            self.link_btn.setVisible(True)
            self.link_btn.setToolTip(self._current_url)
        else:
            self.link_btn.setVisible(False)
            self._current_url = ""

        self.setVisible(True)

    def hide_bar(self):
        """ซ่อนแถบ (เช่น ประกาศถูกลบแล้ว)"""
        self._current_id = ""
        self._current_url = ""
        self.setVisible(False)

    def _open_link(self):
        # ★ validate ซ้ำอีกชั้นก่อนเปิด — defense in depth
        if not _is_safe_url(self._current_url):
            return
        QDesktopServices.openUrl(QUrl(self._current_url))

    def _on_close(self):
        ann_id = self._current_id
        self.hide_bar()
        if ann_id:
            self.dismissed.emit(ann_id)
