"""v3_migration_dialog.py — หน้าต่างและวิดเจ็ตประกาศการย้ายสู่ Broadcast Playroom 3

ใช้สำหรับ:
1. Dialog แจ้งเตือนเมื่อเปิดโปรแกรม v2.9.9 เป็นครั้งแรก (มีตัวเลือก 'ไม่ต้องแสดงอีก' และ 'ใช้เวอร์ชันเก่าต่อ')
2. Section ในหน้าต่าง Setting > Next Version (อยู่บนสุดของเมนู มีเฉพาะปุ่มดาวน์โหลด)
"""
import os
import sys
from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QPixmap, QDesktopServices, QFont, QPainter
from PySide6.QtWidgets import (
    QDialog, QWidget, QFrame, QLabel, QPushButton, 
    QCheckBox, QVBoxLayout, QHBoxLayout
)

SETUP_DOWNLOAD_URL = "https://huggingface.co/men9ch/broadcast-playroom-3/resolve/main/BroadcastPlayroom3-Setup.exe"

def resolve_banner_path():
    """ค้นหาไฟล์ภาพแบนเนอร์ v3_migration_banner.jpg ใน assets/"""
    cur = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(os.path.dirname(cur))
    candidates = [
        os.path.join(root, "assets", "v3_migration_banner.jpg"),
        os.path.join(cur, "..", "..", "assets", "v3_migration_banner.jpg"),
        os.path.join(os.getcwd(), "assets", "v3_migration_banner.jpg"),
    ]
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidates.insert(0, os.path.join(sys._MEIPASS, "assets", "v3_migration_banner.jpg"))
    for c in candidates:
        if os.path.isfile(c):
            return os.path.abspath(c)
    return ""


class BannerWidget(QFrame):
    """วิดเจ็ตแสดงภาพแบนเนอร์แบบเต็มภาพ 100% ไม่ครอบตัดขอบใดๆ (KeepAspectRatio)"""

    def __init__(self, banner_path, parent=None):
        super().__init__(parent)
        self._pixmap = QPixmap(banner_path) if banner_path and os.path.exists(banner_path) else None
        # ความสูง 372px สำหรับสัดส่วน 16:9 บนการ์ดความกว้างประมาณ 660px
        self.setFixedHeight(372)
        self.setStyleSheet("""
            background-color: #0c0d12;
            border-top-left-radius: 13px;
            border-top-right-radius: 13px;
            border-bottom: 1px solid #2e3446;
        """)

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._pixmap or self._pixmap.isNull():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect()
        scaled = self._pixmap.scaled(rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        x = (rect.width() - scaled.width()) // 2
        y = (rect.height() - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)


class V3MigrationCard(QFrame):
    """การ์ดเนื้อหาข่าวสารการย้ายสู่ Broadcast Playroom 3"""
    
    dismiss_requested = Signal()

    def __init__(self, parent=None, show_dismiss_controls=False, settings=None):
        super().__init__(parent)
        self.show_dismiss_controls = show_dismiss_controls
        self.settings = settings
        self.setObjectName("V3MigrationCard")
        self.setStyleSheet("""
            QFrame#V3MigrationCard {
                background-color: #151821;
                border: 1px solid #2e3446;
                border-radius: 14px;
            }
        """)
        self._build_ui()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Top Banner Image (แสดงเต็มภาพ 100% ไม่ตัดขอบ)
        banner_path = resolve_banner_path()
        banner_widget = BannerWidget(banner_path, self)
        main_layout.addWidget(banner_widget)

        # 2. Content Container
        content_box = QWidget()
        c_layout = QVBoxLayout(content_box)
        c_layout.setContentsMargins(22, 12, 22, 12)
        c_layout.setSpacing(8)

        # Title
        title_lbl = QLabel("Broadcast Playroom ขึ้นสู่เวอร์ชั่น 3 !")
        title_font = QFont("Segoe UI", 17, QFont.Bold)
        title_lbl.setFont(title_font)
        title_lbl.setStyleSheet("color: #ffffff; font-family: 'Segoe UI', 'Noto Sans Thai', 'Tahoma', sans-serif; letter-spacing: 0.3px; border: none; background: transparent;")
        c_layout.addWidget(title_lbl)

        # Body Text
        body_text = (
            "สวัสดีผู้ใช้โปรแกรม Broadcast Playroom ทุกท่านครับ<br><br>"
            "ตอนนี้โปรแกรมของเราได้พัฒนาเข้าสู่เวอร์ชั่น 3 แล้ว "
            "โดยมีการเปลี่ยนระบบใหม่ยกเครื่อง เพื่อเพิ่มความรวดเร็วของโปรแกรม "
            "และปรับปรุงหน้าตาการใช้งานให้ดูใหม่ เรียบง่าย และสะอาดตาในขณะใช้งาน "
            "ทำให้ผู้ใช้ใหม่เข้าใจง่าย และวางระบบเพื่อง่ายต่อการพัฒนาระบบในต่อๆ ไปยิ่งขึ้น<br><br>"
            "<span style='color: #38bdf8; font-weight: 600; font-size: 13px;'>"
            "ทางเราจึงขอแนะนำให้ผู้ใช้งานทุกคน ย้ายไปใช้เวอร์ชั่น 3 ได้เลยครับ</span>"
        )
        body_lbl = QLabel(body_text)
        body_lbl.setWordWrap(True)
        body_lbl.setStyleSheet("color: #cbd5e1; font-family: 'Segoe UI', 'Noto Sans Thai', 'Tahoma', sans-serif; font-size: 12.5px; line-height: 1.45; border: none; background: transparent;")
        c_layout.addWidget(body_lbl)

        # Notice Warning Box
        notice_box = QFrame()
        notice_box.setStyleSheet("""
            QFrame {
                background-color: #0f121a;
                border: 1px solid rgba(245, 158, 11, 0.4);
                border-radius: 9px;
            }
        """)
        notice_layout = QVBoxLayout(notice_box)
        notice_layout.setContentsMargins(12, 8, 12, 8)
        notice_layout.setSpacing(4)

        notice_header = QLabel("⚠️ ข้อสำคัญเกี่ยวกับการย้ายระบบ:")
        notice_header.setStyleSheet("color: #fbbf24; font-family: 'Segoe UI', 'Noto Sans Thai', sans-serif; font-weight: bold; font-size: 12.5px; border: none; background: transparent;")
        notice_layout.addWidget(notice_header)

        notice_detail = QLabel(
            "• การย้ายไปนั้นจะไม่สามารถดึงข้อมูลใดๆ ที่เคยตั้งค่าในเวอร์ชั่นเก่าได้ "
            "เนื่องจากใช้ตัว Installer แยกติดตั้งกลายเป็นอีกโปรแกรมเลย<br>"
            "• <b style='color: #38bdf8;'>การย้ายโมเดลเสียง RVC:</b> หากมีโมเดลเสียง AI เดิมอยู่ "
            "<span style='color: #fbbf24; font-weight: 600;'>ก่อนจะลบโปรแกรมตัวเก่า</span> "
            "ให้เข้าไปก๊อปปี้ไฟล์จากโฟลเดอร์ <code>rvc_models</code> ในโปรแกรมเดิม "
            "นำไปวางในโฟลเดอร์ <code>data/rvc_models</code> (หรือ <code>rvc_models</code>) "
            "ในโฟลเดอร์ติดตั้งของ Broadcast Playroom 3 ใหม่ เพื่อใช้งานต่อได้ทันทีครับ<br>"
            "<span style='color: #a5b4fc; font-size: 11px; padding-left: 12px;'>"
            "📍 <i>ที่อยู่โฟลเดอร์เริ่มต้น: %LOCALAPPDATA%\\Programs\\BroadcastPlayroom3\\data\\rvc_models หรือโฟลเดอร์ปลายทางที่ท่านเลือกไว้ตอนติดตั้ง</i></span><br>"
            "• เมื่อย้ายโมเดลและตั้งค่าเวอร์ชัน 3 เรียบร้อยแล้ว สามารถลบโปรแกรมตัวเก่า (v2) ทิ้งได้เลยครับ ไม่จำเป็นต้องเก็บไว้<br>"
            "• แต่หากท่านใดยังชอบเวอร์ชั่นเก่า ก็สามารถเปิดใช้งานต่อได้ตามปกติ เพียงแต่จะไม่มีการอัปเดตระบบเพิ่มหรือแก้บัคแล้วครับ"
        )
        notice_detail.setWordWrap(True)
        notice_detail.setStyleSheet("color: #94a3b8; font-family: 'Segoe UI', 'Noto Sans Thai', 'Tahoma', sans-serif; font-size: 11.5px; line-height: 1.5; border: none; background: transparent;")
        notice_layout.addWidget(notice_detail)

        c_layout.addWidget(notice_box)
        main_layout.addWidget(content_box)

        # 3. Bottom Actions
        bottom_bar = QFrame()
        bottom_bar.setStyleSheet("""
            QFrame {
                background-color: #11141c;
                border-top: 1px solid #252a38;
                border-bottom-left-radius: 13px;
                border-bottom-right-radius: 13px;
            }
        """)
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(18, 8, 18, 8)
        bottom_layout.setSpacing(10)

        if self.show_dismiss_controls:
            # Checkbox: Don't show again
            self.cb_dont_show = QCheckBox("ไม่ต้องแสดงหน้านี้อีกเมื่อเปิดโปรแกรม")
            self.cb_dont_show.setChecked(False)
            self.cb_dont_show.setStyleSheet("""
                QCheckBox {
                    color: #94a3b8;
                    font-family: 'Segoe UI', 'Noto Sans Thai', sans-serif;
                    font-size: 12px;
                    background: transparent;
                    border: none;
                }
                QCheckBox:hover { color: #cbd5e1; }
            """)
            bottom_layout.addWidget(self.cb_dont_show)
            bottom_layout.addStretch()

            # Button: Stay on v2
            btn_stay = QPushButton("ใช้เวอร์ชันเก่าต่อ")
            btn_stay.setCursor(Qt.PointingHandCursor)
            btn_stay.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    color: #94a3b8;
                    font-family: 'Segoe UI', 'Noto Sans Thai', sans-serif;
                    border: 1px solid #334155;
                    border-radius: 8px;
                    padding: 7px 14px;
                    font-size: 12px;
                    font-weight: 500;
                }
                QPushButton:hover {
                    background: #262c3d;
                    color: #ffffff;
                }
            """)
            btn_stay.clicked.connect(self._on_stay_clicked)
            bottom_layout.addWidget(btn_stay)

            dl_btn_text = "🚀 ดาวน์โหลด Broadcast Playroom 3"
        else:
            # In Settings: NO stay button, NO checkbox. Stretch pushes download button to right
            bottom_layout.addStretch()
            dl_btn_text = "🚀 ดาวน์โหลด Broadcast Playroom 3 (Installer)"

        # Primary Download Button
        btn_download = QPushButton(dl_btn_text)
        btn_download.setCursor(Qt.PointingHandCursor)
        btn_download.setFixedHeight(38)
        btn_download.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6366f1, stop:1 #8b5cf6);
                color: #ffffff;
                font-family: 'Segoe UI', 'Noto Sans Thai', sans-serif;
                border: none;
                border-radius: 8px;
                padding: 7px 18px;
                font-size: 12.5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4f46e5, stop:1 #7c3aed);
            }
            QPushButton:pressed {
                background: #4338ca;
            }
        """)
        btn_download.clicked.connect(self._open_download)
        bottom_layout.addWidget(btn_download)

        main_layout.addWidget(bottom_bar)

    def _open_download(self):
        QDesktopServices.openUrl(QUrl(SETUP_DOWNLOAD_URL))

    def _on_stay_clicked(self):
        if hasattr(self, 'cb_dont_show') and self.cb_dont_show.isChecked() and self.settings:
            try:
                self.settings.dismiss_v3_migration_notice = True
                if hasattr(self.settings, 'save'):
                    self.settings.save()
            except Exception:
                pass
        self.dismiss_requested.emit()


class V3MigrationDialog(QDialog):
    """Popup Dialog แจ้งเตือนย้ายสู่เวอร์ชัน 3 ตอนเปิดโปรแกรม v2.9.9"""

    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Broadcast Playroom — ข่าวสารสำคัญสู่เวอร์ชัน 3")
        self.setFixedSize(690, 800)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setStyleSheet("""
            QDialog {
                background-color: #0b1120;
                color: #e2e8f0;
                font-family: 'Segoe UI', 'Noto Sans Thai', sans-serif;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        self.card = V3MigrationCard(self, show_dismiss_controls=True, settings=self.settings)
        self.card.dismiss_requested.connect(self.accept)
        layout.addWidget(self.card)

    def closeEvent(self, event):
        if hasattr(self.card, 'cb_dont_show') and self.card.cb_dont_show.isChecked() and self.settings:
            try:
                self.settings.dismiss_v3_migration_notice = True
                if hasattr(self.settings, 'save'):
                    self.settings.save()
            except Exception:
                pass
        super().closeEvent(event)
