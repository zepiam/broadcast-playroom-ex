"""replace_contribute.py — Dialog ช่วยเพิ่มคำศัพท์ผ่านเว็บชุมชนในโปรแกรม (In-App Web View)

คุณสมบัติ:
- ใช้ QWebEngineView โหลดหน้าเพิ่มคำศัพท์จากเว็บชุมชน
- ซ่อน Sidebar และตารางคำศัพท์เดิมออก เพื่อให้เห็นเฉพาะแบบฟอร์ม "✏️ เพิ่มคำใหม่" และ "📁 อัปโหลดไฟล์" ชัดเจน สวยงาม
- คุมโทนสี Dark Theme ให้กลมกลืนกับโปรแกรม
- รองรับการกดฟังเสียง TTS 🔊, เพิ่มบรรทัด, ส่งข้อมูล และอัปโหลดไฟล์ในตัว
- ลิงก์ภายนอกจะเปิดผ่าน Default Web Browser ของเครื่องแทน
"""

import logging
from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QWidget, QFrame, QMessageBox
)
from PySide6.QtGui import QDesktopServices

logger = logging.getLogger("replace_contribute")

CONTRIBUTE_URL = "https://www.men9ch.com/wiki/ng-replace.php?pid=broadcast-playroom"

# CSS สำหรับตกแต่งและซ่อน Sidebar + ส่วนที่ไม่จำเป็น
CLEANUP_CSS = """
/* ซ่อน Sidebar, ปุ่ม Mobile, ตารางคำเดิม และ Actions ด้านบน */
.sidebar, .mobile-toggle { display: none !important; }
.dict-actions, .table-controls, #approved-table, #approved-pagination { display: none !important; }
h2:has(#approved-count) { display: none !important; }

/* จัดระยะ Main Content ให้เต็มหน้าจอ สวยงาม ไม่ติดขอบ */
.main {
    margin-left: 0 !important;
    max-width: 100% !important;
    padding: 24px 36px 40px !important;
}

/* ปรับฟอร์มเพิ่มคำให้ชิดหัวข้อขึ้น */
#add-form {
    margin-top: 12px !important;
}

/* สไตล์ Scrollbar ให้กลืนกับธีมโปรแกรม */
::-webkit-scrollbar {
    width: 8px;
    height: 8px;
}
::-webkit-scrollbar-track {
    background: #0d1220;
}
::-webkit-scrollbar-thumb {
    background: #2a2f45;
    border-radius: 4px;
}
::-webkit-scrollbar-thumb:hover {
    background: #4b5563;
}
"""

CLEANUP_JS = f"""
(function() {{
    // 1. เพิ่ม Style Sheet สำหรับซ่อนส่วนประกอบที่ไม่จำเป็น
    let style = document.getElementById('bp-custom-style');
    if (!style) {{
        style = document.createElement('style');
        style.id = 'bp-custom-style';
        style.textContent = `{CLEANUP_CSS}`;
        document.head.appendChild(style);
    }}

    // 2. ซ่อนองค์ประกอบเพิ่มเติมเพื่อความแน่นอน (Fallback สำหรับ Browser เวอร์ชั่นเก่า)
    const approvedCount = document.getElementById('approved-count');
    if (approvedCount) {{
        const h2 = approvedCount.closest('h2');
        if (h2) h2.style.display = 'none';
    }}
    document.querySelectorAll('.dict-actions, .table-controls, #approved-table, #approved-pagination, .sidebar, .mobile-toggle').forEach(el => {{
        el.style.display = 'none';
    }});

    const main = document.querySelector('.main');
    if (main) {{
        main.style.marginLeft = '0';
        main.style.maxWidth = '100%';
        main.style.padding = '24px 36px 40px';
    }}
}})();
"""


class ReplaceContributeDialog(QDialog):
    """หน้าต่าง Pop-up แสดงแบบฟอร์มเพิ่มคำศัพท์ในโปรแกรม"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🌐 ช่วยเราเพิ่มคำศัพท์ — Broadcast Playroom")
        self.resize(960, 720)
        self.setMinimumSize(800, 560)

        # ตั้งสไตล์หน้าต่าง
        self.setStyleSheet("""
            QDialog {
                background-color: #0a0e1a;
                color: #e5e7eb;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ═══ Top Header Bar ═══
        header = QFrame()
        header.setFixedHeight(50)
        header.setStyleSheet("""
            QFrame {
                background-color: #131726;
                border-bottom: 1px solid #2a2f45;
            }
        """)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(16, 0, 16, 0)
        h_layout.setSpacing(10)

        title_lbl = QLabel("🌐 เพิ่มคำศัพท์เข้าคลังชุมชน (แชร์กับทุกคนที่ใช้โปรแกรม)")
        title_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #10b981;")
        h_layout.addWidget(title_lbl)

        h_layout.addStretch()

        # ปุ่มรีเฟรชหน้า
        self.btn_reload = QPushButton("🔄 รีเฟรช")
        self.btn_reload.setCursor(Qt.PointingHandCursor)
        self.btn_reload.setStyleSheet("""
            QPushButton {
                background: #1a1f33;
                color: #d1d5db;
                border: 1px solid #2a2f45;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #2a2f45;
                color: #ffffff;
            }
        """)
        self.btn_reload.clicked.connect(self._reload_page)
        h_layout.addWidget(self.btn_reload)

        # ปุ่มเปิดบน Web Browser
        self.btn_external = QPushButton("🔗 เปิดในเบราว์เซอร์")
        self.btn_external.setCursor(Qt.PointingHandCursor)
        self.btn_external.setStyleSheet("""
            QPushButton {
                background: #1a1f33;
                color: #38bdf8;
                border: 1px solid #2a2f45;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #2a2f45;
                color: #7dd3fc;
            }
        """)
        self.btn_external.clicked.connect(self._open_external)
        h_layout.addWidget(self.btn_external)

        layout.addWidget(header)

        # ═══ Progress Bar (แถบบอกสถานะการโหลดแบบเส้นบาง) ═══
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(2)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: transparent;
                border: none;
            }
            QProgressBar::chunk {
                background-color: #10b981;
            }
        """)
        layout.addWidget(self.progress_bar)

        # ═══ QWebEngineView ═══
        try:
            from PySide6.QtWebEngineWidgets import QWebEngineView
            from PySide6.QtWebEngineCore import QWebEnginePage

            class CustomWebPage(QWebEnginePage):
                def acceptNavigationRequest(self, url, nav_type, is_main_frame):
                    # ถ้าเป็นการกดลิงก์ออกไปหน้าอื่นที่ไม่ใช่ ng-replace → เปิดใน External Browser
                    url_str = url.toString()
                    if "ng-replace.php" not in url_str and nav_type == QWebEnginePage.NavigationTypeLinkClicked:
                        QDesktopServices.openUrl(url)
                        return False
                    return super().acceptNavigationRequest(url, nav_type, is_main_frame)

            self.web_view = QWebEngineView()
            self.custom_page = CustomWebPage(self.web_view)
            self.web_view.setPage(self.custom_page)

            self.web_view.loadProgress.connect(self._on_load_progress)
            self.web_view.loadFinished.connect(self._on_load_finished)

            layout.addWidget(self.web_view, 1)

            # เริ่มโหลดหน้าเว็บ
            self.web_view.load(QUrl(CONTRIBUTE_URL))

        except Exception as e:
            logger.error(f"Cannot initialize QWebEngineView: {e}")
            fallback_label = QLabel(
                f"ไม่สามารถเปิดหน้าเว็บในโปรแกรมได้ ({e})\n\n"
                "กรุณาคลิกปุ่มด้านล่างเพื่อเปิดผ่านเว็บเบราว์เซอร์"
            )
            fallback_label.setAlignment(Qt.AlignCenter)
            fallback_label.setStyleSheet("color: #ef4444; font-size: 14px; padding: 40px;")
            layout.addWidget(fallback_label, 1)

            btn_open = QPushButton("🌐 เปิดผ่านเว็บเบราว์เซอร์")
            btn_open.setFixedHeight(40)
            btn_open.setStyleSheet("""
                background-color: #059669; color: white; font-size: 14px; font-weight: bold;
                border-radius: 6px; margin: 0 40px 40px;
            """)
            btn_open.clicked.connect(self._open_external)
            layout.addWidget(btn_open)

    def _on_load_progress(self, progress: int):
        self.progress_bar.setValue(progress)
        if progress < 100:
            self.progress_bar.show()

    def _on_load_finished(self, ok: bool):
        self.progress_bar.hide()
        if ok and hasattr(self, 'web_view'):
            # ฉีด CSS & JS ซ่อน sidebar และตาราง
            self.web_view.page().runJavaScript(CLEANUP_JS)

    def _reload_page(self):
        if hasattr(self, 'web_view'):
            self.web_view.reload()

    def _open_external(self):
        QDesktopServices.openUrl(QUrl(CONTRIBUTE_URL))


def open_replace_contribute_dialog(parent=None):
    """ฟังก์ชันกลางสำหรับเปิดหน้าต่างช่วยเพิ่มคำศัพท์"""
    dlg = ReplaceContributeDialog(parent)
    dlg.exec()
