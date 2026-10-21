# -*- coding: utf-8 -*-
"""ask_panel.py — แผงคุม ASK Widget (โพล/แบบสอบถามบน Composer Overlay)

หน้าต่างลอยด้านขวา (เหมือน Event Sidebar) — เปิด/ปิดจากปุ่ม ASK บน TopBar
- Tab 1: 🗳️ คำถาม & โหวต (ตั้งคำถาม ช้อยส์ โหมดคำตอบ เวลา โหวตสด สรุปผล Preset)
- Tab 2: 🎨 หน้าตา Overlay (รูปแบบ Layout, ธีมสี 23 แบบ, สเกล, พิกัด, ฟอนต์, แอนิเมชัน, ตัวอย่างสดบน OBS)
"""
import time
from typing import Optional
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QFrame, QLabel, QLineEdit, QPushButton, QVBoxLayout, QHBoxLayout,
    QWidget, QSizePolicy, QRadioButton, QButtonGroup, QCheckBox,
    QScrollArea, QComboBox, QMessageBox, QProgressBar, QTabWidget,
    QSlider, QApplication, QStackedWidget
)

LETTERS = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]
MAX_CHOICES = 10

THEME_OPTIONS = [
    ("violet", "🟣 Violet (ม่วงมาตรฐาน)"),
    ("neon", "🔵 Neon (ฟ้านีออนสว่าง)"),
    ("gold", "🟡 Gold (ทองหรูหรา)"),
    ("rose", "🌹 Rose (ชมพูแดงกุหลาบ)"),
    ("emerald", "💚 Emerald (เขียวมรกต)"),
    ("sunset", "🌅 Sunset (ส้มพระอาทิตย์)"),
    ("midnight", "🌌 Midnight (น้ำเงินราตรี)"),
    ("ocean", "🌊 Ocean (ฟ้าทะเลลึก)"),
    ("sakura", "🌸 Sakura (ชมพูซากุระ)"),
    ("forest", "🌲 Forest (เขียวป่าสน)"),
    ("ice", "🧊 Ice (ฟ้าน้ำแข็งใส)"),
    ("candy", "🍬 Candy (ชมพูหวานลูกกวาด)"),
    ("steel", "⚙️ Steel (เทาเหล็กโมเดิร์น)"),
    ("fire", "🔥 Fire (แดงเพลิง)"),
    ("cyberpunk", "🌆 Cyberpunk (เหลืองฟ้านีออน)"),
    ("mint", "🍃 Mint (มินต์สดใส)"),
    ("space", "🪐 Space (น้ำเงินอวกาศ)"),
    ("aurora", "🌟 Aurora (ขอบรุ้งเรืองแสง)"),
    ("crystal", "💎 Crystal (คริสตัลเงาแวว)"),
    ("magma", "🌋 Magma (ลาวาปะทุ)"),
    ("neonframe", "🕶️ Neon Frame (กรอบไฟนีออน)"),
    ("vintage", "🎭 Vintage (ย้อนยุคอบอุ่น)"),
    ("electric", "⚡ Electric (สายฟ้าวิบวับ)"),
]

LAYOUT_OPTIONS = [
    ("vright", "🏛️ เสาแนวตั้ง — ฝั่งขวาของจอ (ขวาสุด)"),
    ("vleft", "🏛️ เสาแนวตั้ง — ฝั่งซ้ายของจอ (ซ้ายสุด)"),
    ("hband", "📏 แถบแนวนอน — เต็มกว้าง (บน/ล่าง)"),
    ("minimal", "📦 Minimal — กล่องอิสระ (กำหนดพิกัด X/Y)"),
    ("lite", "✨ Lite — แถบกระทัดรัดประหยัดพื้นที่ (จิ๋วพิเศษ)"),
]

BAR_STYLES = [
    ("classic", "▬ แถบมน (Classic)"),
    ("striped", "📐 ลายเฉียงวิ่ง (Striped)"),
    ("segmented", "▬▬▬ แบ่งบล็อก (Segmented)"),
    ("glow", "✨ เรืองแสง (Glow)"),
    ("thin", "➖ เส้นบาง (Thin)"),
    ("blocks", "🧱 บล็อกหนา (Blocks)"),
    ("wavy", "〰️ คลื่นไหว (Wavy)"),
    ("dots", "●●● จุดกลม (Dots)"),
    ("neonline", "💡 เส้นนีออน (Neon Line)"),
    ("gradientflow", "🌊 ไล่สีไหล (Gradient Flow)"),
    ("chunky", "🧊 บล็อกหนาเหลี่ยม (Chunky)"),
    ("pulse", "💓 เต้นเป็นจังหวะ (Pulse)"),
]

FRAME_STYLES = [
    ("classic", "📦 มนมีขอบ (Classic)"),
    ("sharp", "📐 มุมแหลม (Sharp)"),
    ("floating", "☁️ ลอยไร้ขอบ (Floating)"),
    ("glow", "💡 ขอบเรืองแสง (Glow)"),
    ("emboss", "🕳️ ฝังลึก (Emboss)"),
    ("double", "⧉ ขอบคู่ (Double)"),
    ("roundedlg", "🫧 มุมโค้งใหญ่ (Rounded LG)"),
    ("ticket", "🎫 ขอบปรุ๊น (Ticket)"),
    ("hologram", "🌈 เรืองรุ้ง (Hologram)"),
    ("carbon", "🏎️ ลายคาร์บอน (Carbon)"),
]

ANIM_IN_OPTIONS = [
    ("fade", "Fade (ค่อยๆ โผล่ขึ้นมา)"),
    ("slide-up", "Slide จากด้านล่างขึ้นบน"),
    ("slide-down", "Slide จากด้านบนลงล่าง"),
    ("slide-left", "Slide จากด้านขวามาซ้าย"),
    ("slide-right", "Slide จากด้านซ้ายมาขวา"),
    ("corner-tl", "พุ่งจากมุมซ้ายบน (ทแยง)"),
    ("corner-tr", "พุ่งจากมุมขวาบน (ทแยง)"),
    ("corner-bl", "พุ่งจากมุมซ้ายล่าง (ทแยง)"),
    ("corner-br", "พุ่งจากมุมขวาล่าง (ทแยง)"),
]

ANIM_OUT_OPTIONS = [
    ("fade", "Fade (ค่อยๆ จางหายไป)"),
    ("slide-up", "Slide กลับขึ้นด้านบน"),
    ("slide-down", "Slide กลับลงด้านล่าง"),
    ("slide-left", "Slide กลับไปด้านซ้าย"),
    ("slide-right", "Slide กลับไปด้านขวา"),
    ("corner-tl", "หดกลับมุมซ้ายบน"),
    ("corner-tr", "หดกลับมุมขวาบน"),
    ("corner-bl", "หดกลับมุมซ้ายล่าง"),
    ("corner-br", "หดกลับมุมขวาล่าง"),
]

STYLE_DEMO_VOTE_NORMAL = """
    QPushButton {
        background: #7c3aed;
        color: #ffffff;
        border: 1px solid #9333ea;
        border-radius: 6px;
        padding: 6px 11px;
        font-weight: 700;
        font-size: 12px;
    }
    QPushButton:hover {
        background: #8b5cf6;
        border-color: #c4b5fd;
    }
    QPushButton:pressed {
        background: #6d28d9;
    }
"""

STYLE_DEMO_RESULT_NORMAL = """
    QPushButton {
        background: #059669;
        color: #ffffff;
        border: 1px solid #10b981;
        border-radius: 6px;
        padding: 6px 11px;
        font-weight: 700;
        font-size: 12px;
    }
    QPushButton:hover {
        background: #10b981;
        border-color: #6ee7b7;
    }
    QPushButton:pressed {
        background: #047857;
    }
"""

STYLE_DEMO_ACTIVE_RED = """
    QPushButton {
        background: #dc2626;
        color: #ffffff;
        border: 1px solid #ef4444;
        border-radius: 6px;
        padding: 6px 11px;
        font-weight: 700;
        font-size: 12px;
    }
    QPushButton:hover {
        background: #ef4444;
        border-color: #f87171;
    }
    QPushButton:pressed {
        background: #b91c1c;
    }
"""

STYLE_TAB2_VOTE_NORMAL = "background: #7c3aed; color: white; border: none; border-radius: 6px; padding: 8px 10px; font-weight: 600;"
STYLE_TAB2_RESULT_NORMAL = "background: #059669; color: white; border: none; border-radius: 6px; padding: 8px 10px; font-weight: 600;"
STYLE_TAB2_ACTIVE_RED = "background: #dc2626; color: white; border: 1px solid #ef4444; border-radius: 6px; padding: 8px 10px; font-weight: 700;"


class AskPanel(QFrame):
    """แผงคุม ASK Widget — หน้าต่างลอยด้านขวาของ main window"""

    # ★ signals การโหวต
    start_requested = Signal(dict)   # poll config (question/choices/mode/...)
    end_requested = Signal()         # จบโหวตทันที
    close_requested = Signal()       # ปิดผลออกจาก Overlay
    # ★ presets — ขอ/บันทึก/ลบ ผ่าน app (เก็บใน settings)
    presets_load_requested = Signal()                    # ขอรายการ preset ล่าสุด
    preset_save_requested = Signal(dict)                 # บันทึก {name, question, choices, answer_mode}
    preset_delete_requested = Signal(str)                # ลบตามชื่อ
    presets_changed = Signal(list)                       # app push รายการใหม่กลับมา
    # ★ signals หน้าตา Overlay & Preview
    closed = Signal()                                    # หน้าต่างถูกปิด
    display_settings_changed = Signal(dict)              # ส่งการตั้งค่าหน้าตาไปบันทึกและ sync ทันที
    preview_requested = Signal(str)                      # "vote" | "result" | "stop"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active_demo = None  # None | "vote" | "result"
        self.setObjectName("AskPanel")
        self.setFrameShape(QFrame.StyledPanel)
        self.setWindowTitle("🗳️ ASK — ระบบโพลและแบบสอบถามบนจอ")
        self.resize(540, 780)
        self.setMinimumSize(360, 500)
        self.setWindowFlags(Qt.Window | Qt.WindowCloseButtonHint | Qt.WindowMinMaxButtonsHint)
        self.setStyleSheet("""
            QFrame#AskPanel { background: #0b1120; border: 1px solid #1e293b; }
            QLabel { color: #e2e8f0; font-size: 13px; background: transparent; border: none; }
            QMessageBox { background-color: #0b1120; }
            QMessageBox QLabel { color: #f8fafc; font-size: 13.5px; min-height: 0px; background: transparent; }
            QMessageBox QPushButton { min-width: 75px; padding: 6px 16px; font-size: 13px; border-radius: 6px; }
            QLabel[hdr="true"] { color: #f59e0b; font-weight: 800; font-size: 14.5px; }
            QLabel[dim="true"] { color: #64748b; font-size: 12px; }
            QLineEdit, QComboBox {
                background: #162032; color: #f8fafc; border: 1px solid #283548;
                border-radius: 6px; padding: 7px 11px; font-size: 13.5px; min-height: 20px;
            }
            QLineEdit:focus, QComboBox:focus { border-color: #a855f7; background: #1e293b; }
            QPushButton {
                background: #7c3aed; color: white; border: none; border-radius: 6px;
                padding: 8px 16px; font-weight: 700; font-size: 13.5px;
            }
            QPushButton:hover { background: #6d28d9; }
            QPushButton:disabled { background: #1e293b; color: #64748b; }
            QPushButton[danger="true"] { background: #dc2626; }
            QPushButton[danger="true"]:hover { background: #b91c1c; }
            QPushButton[ghost="true"] {
                background: #162032; border: 1px solid #283548;
                color: #94a3b8; padding: 6px 12px; font-weight: 600; font-size: 13px;
            }
            QPushButton[ghost="true"]:hover { border-color: #a855f7; color: #e2e8f0; background: #1e293b; }
            QRadioButton { color: #cbd5e1; font-size: 13.5px; background: transparent; spacing: 6px; }
            QCheckBox { color: #cbd5e1; font-size: 13px; background: transparent; spacing: 6px; }
            QTabWidget::pane {
                border: none;
                border-top: 1px solid #1e293b;
                background-color: transparent;
            }
            QTabBar::tab {
                background: transparent;
                color: #94a3b8;
                padding: 10px 20px;
                font-weight: 700;
                font-size: 13.5px;
                border: none;
                border-bottom: 2px solid transparent;
                margin-right: 6px;
            }
            QTabBar::tab:selected {
                color: #c084fc;
                border-bottom: 2px solid #a855f7;
                font-weight: 800;
            }
            QTabBar::tab:hover:!selected {
                color: #f1f5f9;
            }
            QSlider::groove:horizontal {
                height: 5px;
                background: #1e293b;
                border-radius: 2.5px;
            }
            QSlider::sub-page:horizontal {
                background: #7c3aed;
                border-radius: 2.5px;
            }
            QSlider::handle:horizontal {
                background: #a855f7;
                width: 16px;
                margin-top: -6px;
                margin-bottom: -6px;
                border-radius: 8px;
            }
            QSlider::handle:horizontal:hover {
                background: #c084fc;
            }
        """)

        self._loading_settings = False
        self._sync_timer = QTimer(self)
        self._sync_timer.setSingleShot(True)
        self._sync_timer.setInterval(60)
        self._sync_timer.timeout.connect(self._emit_display_settings)

        self.parent_app = parent

        # ── Root Layout with QStackedWidget ──
        self.stack = QStackedWidget(self)

        # ── Page 0: Main tool content ──
        self.main_content = QWidget()
        main_layout = QVBoxLayout(self.main_content)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(8)

        # ── Header Bar ──
        hdr_row = QHBoxLayout()
        hdr_row.setSpacing(6)
        hdr = QLabel("🗳️ ASK โพลบนจอ")
        hdr.setProperty("hdr", True)
        hdr_row.addWidget(hdr)
        hdr_row.addStretch()

        self.btn_top_preview_vote = QPushButton("🗳️ Demo โหวต")
        self.btn_top_preview_vote.setStyleSheet(STYLE_DEMO_VOTE_NORMAL)
        self.btn_top_preview_vote.setToolTip("แสดงตัวอย่างตอนกำลังโหวตจริงบนจอ OBS (กดอีกครั้งเพื่อปิด)")
        self.btn_top_preview_vote.setCursor(Qt.PointingHandCursor)
        self.btn_top_preview_vote.clicked.connect(lambda: self._toggle_demo("vote"))
        hdr_row.addWidget(self.btn_top_preview_vote)

        self.btn_top_preview_result = QPushButton("📊 Demo ผล")
        self.btn_top_preview_result.setStyleSheet(STYLE_DEMO_RESULT_NORMAL)
        self.btn_top_preview_result.setToolTip("แสดงตัวอย่างสรุปผลโหวตบนจอ OBS (กดอีกครั้งเพื่อปิด)")
        self.btn_top_preview_result.setCursor(Qt.PointingHandCursor)
        self.btn_top_preview_result.clicked.connect(lambda: self._toggle_demo("result"))
        hdr_row.addWidget(self.btn_top_preview_result)

        self.btn_copy_obs = QPushButton("📋 คัดลอกลิงก์ OBS")
        self.btn_copy_obs.setStyleSheet("""
            QPushButton {
                background: #162032;
                border: 1px solid #283548;
                border-radius: 6px;
                color: #94a3b8;
                padding: 6px 10px;
                font-weight: 600;
                font-size: 12px;
            }
            QPushButton:hover {
                border-color: #a855f7;
                color: #e2e8f0;
                background: #1e293b;
            }
        """)
        self.btn_copy_obs.setToolTip("คัดลอกลิงก์ Universal Overlay สำหรับใส่ใน Browser Source ของ OBS")
        self.btn_copy_obs.clicked.connect(self._copy_obs_url)
        hdr_row.addWidget(self.btn_copy_obs)
        main_layout.addLayout(hdr_row)

        # ── Tabs ──
        self.tabs = QTabWidget()
        self.tab_vote = QWidget()
        self.tab_design = QWidget()

        self._build_tab_vote()
        self._build_tab_design()

        self.tabs.addTab(self.tab_vote, "🗳️ คำถาม & โหวต")
        self.tabs.addTab(self.tab_design, "🎨 หน้าตา Overlay")
        main_layout.addWidget(self.tabs, 1)

        # ── แถบเครื่องมือ OBS Dock ด้านล่างสุด ──
        dock_bar = QFrame()
        dock_bar.setStyleSheet("""
            QFrame {
                background-color: #080d1a;
                border: 1px solid #1e293b;
                border-radius: 8px;
                padding: 4px 8px;
            }
        """)
        db_layout = QHBoxLayout(dock_bar)
        db_layout.setContentsMargins(8, 4, 8, 4)
        db_layout.setSpacing(8)

        lbl_dock = QLabel("🎛️ OBS Control Dock:")
        lbl_dock.setStyleSheet("color: #38bdf8; font-weight: 700; font-size: 12px; border: none; background: transparent;")
        db_layout.addWidget(lbl_dock)

        btn_install_dock = QPushButton("⚡ ติดตั้งลง OBS")
        btn_install_dock.setCursor(Qt.PointingHandCursor)
        btn_install_dock.setStyleSheet("""
            QPushButton {
                background: #064e3b; color: #a7f3d0; border: 1px solid #059669;
                border-radius: 4px; padding: 4px 9px; font-weight: 600; font-size: 11.5px;
            }
            QPushButton:hover { background: #047857; color: #ffffff; border-color: #10b981; }
            QPushButton:pressed { background: #065f46; }
        """)
        def _install_from_ask():
            import obs_dock_installer as odi
            from PySide6.QtWidgets import QMessageBox
            dock_url = odi.get_dock_url()
            if hasattr(self, 'parent_app') and hasattr(self.parent_app, 'composer_server') and self.parent_app.composer_server:
                dock_url = f"http://localhost:{getattr(self.parent_app.composer_server, 'port', 8801)}/dock"
            ok, msg, _ = odi.install_obs_dock(dock_url=dock_url)
            if ok:
                QMessageBox.information(self, "ติดตั้ง OBS Dock สำเร็จ", msg)
            else:
                QMessageBox.warning(self, "ติดตั้งไม่สำเร็จ", msg)
        btn_install_dock.clicked.connect(_install_from_ask)
        db_layout.addWidget(btn_install_dock)

        btn_copy_dock = QPushButton("📋 คัดลอกลิงก์")
        btn_copy_dock.setCursor(Qt.PointingHandCursor)
        btn_copy_dock.setStyleSheet("""
            QPushButton {
                background: #162032; color: #94a3b8; border: 1px solid #283548;
                border-radius: 4px; padding: 4px 9px; font-weight: 600; font-size: 11.5px;
            }
            QPushButton:hover { background: #1e293b; color: #f1f5f9; border-color: #38bdf8; }
        """)
        def _copy_dock_url_ask():
            import obs_dock_installer as odi
            from PySide6.QtWidgets import QApplication
            dock_url = odi.get_dock_url()
            if hasattr(self, 'parent_app') and hasattr(self.parent_app, 'composer_server') and self.parent_app.composer_server:
                dock_url = f"http://localhost:{getattr(self.parent_app.composer_server, 'port', 8801)}/dock"
            QApplication.clipboard().setText(dock_url)
            btn_copy_dock.setText("✓ คัดลอกแล้ว")
        db_layout.addWidget(btn_copy_dock)

        db_layout.addStretch()

        from PySide6.QtWidgets import QSizeGrip
        self.sizegrip = QSizeGrip(self)
        db_layout.addWidget(self.sizegrip, 0, Qt.AlignVCenter | Qt.AlignRight)

        main_layout.addWidget(dock_bar)

        # ── Page 1: Blocker widget when ASK is missing from overlay ──
        self.blocker_widget = self._build_blocker_widget()

        self.stack.addWidget(self.main_content)
        self.stack.addWidget(self.blocker_widget)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(self.stack)

        # ป้องกันไม่ให้การเลื่อน Scroll เมาส์ไปเผลอปรับค่า Slider / Dropdown
        self._disable_scroll_on_inputs()

        # ตัวตรวจเช็คสถานะ Widget ใน Overlay เป็นระยะ (เช็คทุก 1.5 วินาที)
        self._widget_check_timer = QTimer(self)
        self._widget_check_timer.setInterval(1500)
        self._widget_check_timer.timeout.connect(self._check_widget_status)
        self._widget_check_timer.start()
        self._check_widget_status()

    def _build_blocker_widget(self) -> QWidget:
        """สร้างหน้าต่างแจ้งเตือนเมื่อยังไม่ได้วาง Widget ASK บน Overlay"""
        blocker = QWidget()
        blocker.setStyleSheet("background: transparent;")
        v = QVBoxLayout(blocker)
        v.setContentsMargins(28, 36, 28, 36)
        v.setSpacing(16)
        v.addStretch()

        icon_lbl = QLabel("⚠️")
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet("font-size: 52px; background: transparent; border: none;")
        v.addWidget(icon_lbl)

        title_lbl = QLabel("ยังไม่ได้เพิ่ม Widget ASK (โพล) บนหน้าจอ Overlay")
        title_lbl.setAlignment(Qt.AlignCenter)
        title_lbl.setStyleSheet("font-size: 17px; font-weight: 800; color: #f59e0b; background: transparent; border: none;")
        v.addWidget(title_lbl)

        desc_lbl = QLabel(
            "เพื่อให้ระบบสามารถแสดงโพล คำถาม และผลโหวตบนหน้าจอ OBS ได้อย่างถูกต้อง\n"
            "กรุณาเปิด Overlay Composer แล้วกดปุ่ม \"+ ASK (โพล)\" เพื่อวาง Widget ลงบนหน้าจอก่อนครับ"
        )
        desc_lbl.setAlignment(Qt.AlignCenter)
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet("font-size: 13.5px; color: #94a3b8; line-height: 1.6; background: transparent; border: none;")
        v.addWidget(desc_lbl)

        step_card = QFrame()
        step_card.setStyleSheet("background: #111a2e; border: 1px solid #1e293b; border-radius: 8px; padding: 14px;")
        sv = QVBoxLayout(step_card)
        sv.setSpacing(8)

        s1 = QLabel("1️⃣  กดปุ่ม <b>\"เปิด Overlay Composer\"</b> ด้านล่างเพื่อไปยังหน้าจัดการหน้าจอ")
        s2 = QLabel("2️⃣  กดปุ่ม <b>\"+ ASK (โพล)\"</b> ในแถบเครื่องมือเพื่อวาง Widget บนหน้าจอ")
        s3 = QLabel("3️⃣  เมื่อเพิ่มเรียบร้อยแล้ว หน้านี้จะ<b>ปลดล็อคให้อัตโนมัติทันที</b> เพื่อให้คุณเริ่มตั้งคำถามได้")
        for s in (s1, s2, s3):
            s.setWordWrap(True)
            s.setStyleSheet("color: #cbd5e1; font-size: 13px; line-height: 1.5; background: transparent; border: none;")
            sv.addWidget(s)
        v.addWidget(step_card)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_row.addStretch()

        btn_open = QPushButton("🌐 เปิด Overlay Composer เพื่อเพิ่ม Widget")
        btn_open.setStyleSheet(
            "background-color: #7c3aed; color: #ffffff; border: none; border-radius: 6px; "
            "padding: 11px 22px; font-weight: 800; font-size: 14px;"
        )
        btn_open.setCursor(Qt.PointingHandCursor)
        btn_open.clicked.connect(self._on_open_composer_clicked)
        btn_row.addWidget(btn_open)

        btn_check = QPushButton("🔄 ตรวจสอบอีกครั้ง")
        btn_check.setProperty("variant", "ghost")
        btn_check.setStyleSheet(
            "background-color: #162032; border: 1px solid #283548; color: #cbd5e1; "
            "border-radius: 6px; padding: 11px 18px; font-weight: 600; font-size: 13px;"
        )
        btn_check.setCursor(Qt.PointingHandCursor)
        btn_check.clicked.connect(self._check_widget_status)
        btn_row.addWidget(btn_check)
        btn_row.addStretch()

        v.addLayout(btn_row)
        v.addStretch()
        return blocker

    def _is_widget_installed(self) -> bool:
        """เช็คว่ามี Widget ASK ใน Overlay หรือยัง"""
        try:
            app_inst = self.parent_app or (self.parent() if callable(getattr(self, "parent", None)) else None)
            if app_inst and hasattr(app_inst, "_ask_widget_exists"):
                return bool(app_inst._ask_widget_exists())
            if app_inst and hasattr(app_inst, "settings"):
                widgets = list(getattr(app_inst.settings, "composer_widgets", []) or [])
                return any(isinstance(w, dict) and w.get("type") == "ask" and w.get("enabled", True) for w in widgets)
        except Exception:
            pass
        return False

    def _check_widget_status(self):
        """ตรวจเช็คสถานะการติดตั้ง Widget ASK และสลับหน้าแสดงผลอัตโนมัติ"""
        installed = self._is_widget_installed()
        if installed:
            if self.stack.currentIndex() != 0:
                self.stack.setCurrentIndex(0)
                if hasattr(self, "btn_top_preview_vote"):
                    self.btn_top_preview_vote.setEnabled(True)
                if hasattr(self, "btn_top_preview_result"):
                    self.btn_top_preview_result.setEnabled(True)
        else:
            if self.stack.currentIndex() != 1:
                self.stack.setCurrentIndex(1)
                if hasattr(self, "btn_top_preview_vote"):
                    self.btn_top_preview_vote.setEnabled(False)
                if hasattr(self, "btn_top_preview_result"):
                    self.btn_top_preview_result.setEnabled(False)

    def _on_open_composer_clicked(self):
        """เปิด Overlay Composer บนเบราว์เซอร์เพื่อให้ผู้ใช้เพิ่ม Widget"""
        try:
            app_inst = self.parent_app or (self.parent() if callable(getattr(self, "parent", None)) else None)
            if app_inst and hasattr(app_inst, "_open_composer"):
                app_inst._open_composer()
                return
        except Exception:
            pass
        import webbrowser
        port = 8801
        try:
            app_inst = self.parent_app or (self.parent() if callable(getattr(self, "parent", None)) else None)
            if app_inst and hasattr(app_inst, "composer_server") and app_inst.composer_server:
                port = getattr(app_inst.composer_server, "port", 8801)
            elif app_inst and hasattr(app_inst, "settings"):
                port = getattr(app_inst.settings, "composer_port", 8801)
        except Exception:
            pass
        webbrowser.open(f"http://localhost:{port}/editor")

    def closeEvent(self, event):
        if getattr(self, '_active_demo', None) is not None:
            self._set_demo_state(None)
            self.preview_requested.emit("stop")
        super().closeEvent(event)
        self.closed.emit()

    def hideEvent(self, event):
        if getattr(self, '_active_demo', None) is not None:
            self._set_demo_state(None)
            self.preview_requested.emit("stop")
        super().hideEvent(event)

    def _set_demo_state(self, mode: Optional[str]):
        """อัปเดตหน้าตาปุ่ม Demo (โหวต / ผล) ทั้งแถบหัวและแท็บ 2 ให้แสดงเป็นสีแดง '⏹️ ปิด Demo' เมื่อทำงานอยู่"""
        self._active_demo = mode
        if mode == "vote":
            # ปุ่มโหวตกลายเป็นสีแดง ปิด Demo
            self.btn_top_preview_vote.setText("⏹️ ปิด Demo")
            self.btn_top_preview_vote.setStyleSheet(STYLE_DEMO_ACTIVE_RED)
            self.btn_top_preview_vote.setToolTip("กดเพื่อปิดตัวอย่างแสดงผลบน OBS")
            if hasattr(self, 'btn_preview_vote') and self.btn_preview_vote:
                self.btn_preview_vote.setText("⏹️ ปิด Demo")
                self.btn_preview_vote.setStyleSheet(STYLE_TAB2_ACTIVE_RED)

            # ปุ่มผลคืนค่าเดิม
            self.btn_top_preview_result.setText("📊 Demo ผล")
            self.btn_top_preview_result.setStyleSheet(STYLE_DEMO_RESULT_NORMAL)
            self.btn_top_preview_result.setToolTip("แสดงตัวอย่างสรุปผลโหวตบนจอ OBS (กดอีกครั้งเพื่อปิด)")
            if hasattr(self, 'btn_preview_result') and self.btn_preview_result:
                self.btn_preview_result.setText("📊 ตัวอย่าง (สรุปผล)")
                self.btn_preview_result.setStyleSheet(STYLE_TAB2_RESULT_NORMAL)

        elif mode == "result":
            # ปุ่มผลกลายเป็นสีแดง ปิด Demo
            self.btn_top_preview_result.setText("⏹️ ปิด Demo")
            self.btn_top_preview_result.setStyleSheet(STYLE_DEMO_ACTIVE_RED)
            self.btn_top_preview_result.setToolTip("กดเพื่อปิดตัวอย่างแสดงผลบน OBS")
            if hasattr(self, 'btn_preview_result') and self.btn_preview_result:
                self.btn_preview_result.setText("⏹️ ปิด Demo")
                self.btn_preview_result.setStyleSheet(STYLE_TAB2_ACTIVE_RED)

            # ปุ่มโหวตคืนค่าเดิม
            self.btn_top_preview_vote.setText("🗳️ Demo โหวต")
            self.btn_top_preview_vote.setStyleSheet(STYLE_DEMO_VOTE_NORMAL)
            self.btn_top_preview_vote.setToolTip("แสดงตัวอย่างตอนกำลังโหวตจริงบนจอ OBS (กดอีกครั้งเพื่อปิด)")
            if hasattr(self, 'btn_preview_vote') and self.btn_preview_vote:
                self.btn_preview_vote.setText("🗳️ ตัวอย่าง (กำลังโหวต)")
                self.btn_preview_vote.setStyleSheet(STYLE_TAB2_VOTE_NORMAL)

        else:
            # คืนค่าปกติทั้งสองปุ่ม
            self.btn_top_preview_vote.setText("🗳️ Demo โหวต")
            self.btn_top_preview_vote.setStyleSheet(STYLE_DEMO_VOTE_NORMAL)
            self.btn_top_preview_vote.setToolTip("แสดงตัวอย่างตอนกำลังโหวตจริงบนจอ OBS (กดอีกครั้งเพื่อปิด)")
            if hasattr(self, 'btn_preview_vote') and self.btn_preview_vote:
                self.btn_preview_vote.setText("🗳️ ตัวอย่าง (กำลังโหวต)")
                self.btn_preview_vote.setStyleSheet(STYLE_TAB2_VOTE_NORMAL)

            self.btn_top_preview_result.setText("📊 Demo ผล")
            self.btn_top_preview_result.setStyleSheet(STYLE_DEMO_RESULT_NORMAL)
            self.btn_top_preview_result.setToolTip("แสดงตัวอย่างสรุปผลโหวตบนจอ OBS (กดอีกครั้งเพื่อปิด)")
            if hasattr(self, 'btn_preview_result') and self.btn_preview_result:
                self.btn_preview_result.setText("📊 ตัวอย่าง (สรุปผล)")
                self.btn_preview_result.setStyleSheet(STYLE_TAB2_RESULT_NORMAL)

    def _toggle_demo(self, mode: str):
        if self._active_demo == mode:
            self._set_demo_state(None)
            self.preview_requested.emit("stop")
        else:
            self._set_demo_state(mode)
            self.preview_requested.emit(mode)

    def reset_demo_state(self):
        """รีเซ็ตสถานะปุ่ม Demo กลับเป็นปกติ"""
        self._set_demo_state(None)

    def _disable_scroll_on_inputs(self):
        """ปิดการตอบสนอง Wheel Event ของ Dropdown, Slider, Spinbox ทั้งหมด และป้องกัน ComboBox ดันความกว้างเกินกรอบ"""
        from PySide6.QtWidgets import QComboBox, QSlider, QSpinBox, QSizePolicy
        for cls in (QComboBox, QSlider, QSpinBox):
            for widget in self.findChildren(cls):
                widget.wheelEvent = lambda event: event.ignore()
                if isinstance(widget, QComboBox):
                    widget.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
                    widget.setMinimumContentsLength(8)
                    widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def _create_section_card(self, title: str, icon: str = "", accent_color: str = "#c084fc", extra_widget: Optional[QWidget] = None):
        """สร้างการ์ดกลุ่มการตั้งค่าระดับเดียว (Single-layer Card) พร้อมหัวข้อ เส้นตัดคั่น และสีสันตามมาตรฐาน UI สตูดิโอ"""
        card = QFrame()
        card.setObjectName("SectionCard")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        card.setStyleSheet("""
            QFrame#SectionCard {
                background-color: #0e1726;
                border: 1px solid #1e293b;
                border-radius: 8px;
            }
        """)
        v = QVBoxLayout(card)
        v.setContentsMargins(14, 12, 14, 14)
        v.setSpacing(10)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 2)
        header_row.setSpacing(8)

        title_text = f"{icon}  {title}".strip() if icon else title
        lbl = QLabel(title_text)
        lbl.setStyleSheet(f"font-size: 13px; font-weight: 800; color: {accent_color}; background: transparent; border: none;")
        header_row.addWidget(lbl)
        header_row.addStretch()

        if extra_widget:
            header_row.addWidget(extra_widget)

        v.addLayout(header_row)

        # เส้นแบ่งตัดคั่นใต้หัวข้อ สวยงาม คมชัด ไม่รกตา
        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background-color: #1e293b; border: none;")
        v.addWidget(divider)

        return card, v

    # ───────────────────────────────────────────────────────────────────
    # Slider Row Helper
    # ───────────────────────────────────────────────────────────────────
    def _create_slider_row(self, label_text: str, min_val: int, max_val: int,
                           step: int, default_val: int, unit: str = "", signed: bool = False):
        wrap = QWidget()
        wrap.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        wrap.setStyleSheet("background: transparent;")
        v = QVBoxLayout(wrap)
        v.setContentsMargins(0, 2, 0, 4)
        v.setSpacing(3)

        top_h = QHBoxLayout()
        top_h.setSpacing(6)
        lbl = QLabel(label_text)
        lbl.setStyleSheet("color: #cbd5e1; font-size: 13px; font-weight: 600;")
        init_txt = (f"{default_val:+d}{unit}" if default_val != 0 else f"0{unit}") if signed else f"{default_val}{unit}"
        val_lbl = QLabel(init_txt)
        val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        val_lbl.setMinimumWidth(58)
        val_lbl.setStyleSheet("color: #c084fc; font-weight: 800; font-size: 13.5px;")
        top_h.addWidget(lbl, 1)
        top_h.addWidget(val_lbl, 0)
        v.addLayout(top_h)

        slider = QSlider(Qt.Horizontal)
        slider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        slider.wheelEvent = lambda event: event.ignore()
        slider.setRange(min_val, max_val)
        slider.setSingleStep(step)
        slider.setValue(default_val)
        v.addWidget(slider)

        def _update_label(val):
            txt = (f"{val:+d}{unit}" if val != 0 else f"0{unit}") if signed else f"{val}{unit}"
            val_lbl.setText(txt)
            self._schedule_sync_settings()

        slider.valueChanged.connect(_update_label)
        return wrap, slider, val_lbl

    # ═══════════════════════════════════════════════════════════════════
    # TAB 1: 🗳️ คำถาม & โหวต
    # ═══════════════════════════════════════════════════════════════════
    def _build_tab_vote(self):
        tab_layout = QVBoxLayout(self.tab_vote)
        tab_layout.setContentsMargins(0, 6, 0, 0)
        tab_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        body = QWidget()
        body.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._form = QVBoxLayout(body)
        self._form.setContentsMargins(4, 4, 4, 4)
        self._form.setSpacing(12)
        scroll.setWidget(body)
        tab_layout.addWidget(scroll, 1)

        # ── Card 1: Preset คำถามด่วน ──
        card_pr, layout_pr = self._create_section_card("Preset คำถามด่วน", "📂", accent_color="#38bdf8")
        pr_row = QHBoxLayout()
        pr_row.setSpacing(6)
        self.cmb_preset = QComboBox()
        self.cmb_preset.setMinimumWidth(150)
        self.cmb_preset.currentIndexChanged.connect(self._on_preset_selected)
        pr_row.addWidget(self.cmb_preset, 1)

        btn_save_pr = QPushButton("💾 บันทึก")
        btn_save_pr.setProperty("ghost", True)
        btn_save_pr.setToolTip("บันทึกคำถาม+ช้อยส์ปัจจุบันเป็น Preset")
        btn_save_pr.clicked.connect(self._on_preset_save)
        pr_row.addWidget(btn_save_pr)

        btn_del_pr = QPushButton("🗑 ลบ")
        btn_del_pr.setProperty("ghost", True)
        btn_del_pr.setToolTip("ลบ Preset ที่เลือก")
        btn_del_pr.clicked.connect(self._on_preset_delete)
        pr_row.addWidget(btn_del_pr)
        layout_pr.addLayout(pr_row)
        self._form.addWidget(card_pr)

        # ── Card 2: คำถาม & ตัวเลือก ──
        card_q, layout_q = self._create_section_card("คำถาม & ตัวเลือกคำตอบ", "📝", accent_color="#c084fc")

        lbl_q = QLabel("คำถาม:")
        lbl_q.setStyleSheet("font-weight: 600; color: #cbd5e1;")
        layout_q.addWidget(lbl_q)
        self.inp_question = QLineEdit()
        self.inp_question.setPlaceholderText("เช่น เลือกเกมที่จะเล่นต่อ หรือ มื้อนี้กินอะไรดี?")
        layout_q.addWidget(self.inp_question)

        ch_hdr = QLabel("ช้อยส์คำตอบ:")
        ch_hdr.setProperty("hdr", True)
        ch_hdr.setStyleSheet("font-weight: 600; color: #cbd5e1; margin-top: 4px;")
        layout_q.addWidget(ch_hdr)

        self._choices_host = QVBoxLayout()
        self._choices_host.setSpacing(4)
        layout_q.addLayout(self._choices_host)
        self._choice_rows = []
        self._add_choice_row("")
        self._add_choice_row("")

        self.btn_add_choice = QPushButton("＋ เพิ่มคำตอบ")
        self.btn_add_choice.setProperty("ghost", True)
        self.btn_add_choice.clicked.connect(self._add_default_choice)
        layout_q.addWidget(self.btn_add_choice)

        self.lbl_choice_hint = QLabel("")
        self.lbl_choice_hint.setProperty("dim", True)
        layout_q.addWidget(self.lbl_choice_hint)
        self._form.addWidget(card_q)

        # ── Card 3: กติกา & ระยะเวลา ──
        card_rules, layout_rules = self._create_section_card("กติกา & ระยะเวลา", "⏱️", accent_color="#fbbf24")

        m_hdr = QLabel("วิธีตอบของผู้ชมในแชท:")
        m_hdr.setProperty("hdr", True)
        m_hdr.setStyleSheet("font-weight: 600; color: #cbd5e1;")
        layout_rules.addWidget(m_hdr)

        self.rb_letters = QRadioButton("พิมพ์ตัวอักษร  A B C ...")
        self.rb_numbers = QRadioButton("พิมพ์ตัวเลข  1 2 3 ...")
        self.rb_letters.setChecked(True)
        grp = QButtonGroup(self)
        grp.addButton(self.rb_letters)
        grp.addButton(self.rb_numbers)
        self.rb_letters.toggled.connect(lambda _: self._refresh_choice_labels())
        self.rb_numbers.toggled.connect(lambda _: self._refresh_choice_labels())
        layout_rules.addWidget(self.rb_letters)
        layout_rules.addWidget(self.rb_numbers)

        hint = QLabel("(ระบบจะนับเฉพาะข้อความที่เป็นตัวอักษร/เลขตัวเดียว เพื่อความแม่นยำ)")
        hint.setProperty("dim", True)
        hint.setWordWrap(True)
        layout_rules.addWidget(hint)

        # เวลาโหวต
        t_hdr = QLabel("เวลาโหวต:")
        t_hdr.setProperty("hdr", True)
        t_hdr.setStyleSheet("font-weight: 600; color: #cbd5e1; margin-top: 4px;")
        layout_rules.addWidget(t_hdr)

        t_row = QHBoxLayout()
        self.ed_vote, self.cmb_vote_unit = self._make_duration_inputs(30)
        t_row.addWidget(self.ed_vote)
        t_row.addWidget(self.cmb_vote_unit)
        self.chk_no_limit = QCheckBox("ไม่จำกัดเวลา")
        self.chk_no_limit.toggled.connect(
            lambda on: (self.ed_vote.setEnabled(not on),
                        self.cmb_vote_unit.setEnabled(not on)))
        t_row.addWidget(self.chk_no_limit)
        t_row.addStretch()
        layout_rules.addLayout(t_row)

        # การแสดงผลยอด
        d_hdr = QLabel("การแสดงยอดโหวต:")
        d_hdr.setProperty("hdr", True)
        d_hdr.setStyleSheet("font-weight: 600; color: #cbd5e1; margin-top: 4px;")
        layout_rules.addWidget(d_hdr)

        self.rb_realtime = QRadioButton("เรียลไทม์ (เห็นยอดสดทันทีระหว่างโหวต)")
        self.rb_summary = QRadioButton("รอจบโหวตค่อยแสดงสรุปผล")
        self.rb_realtime.setChecked(True)
        grp2 = QButtonGroup(self)
        grp2.addButton(self.rb_realtime)
        grp2.addButton(self.rb_summary)
        layout_rules.addWidget(self.rb_realtime)
        layout_rules.addWidget(self.rb_summary)

        # เวลาแสดงสรุปผล
        r_hdr = QLabel("แสดงสรุปผล (นับถอยหลังแล้วหายไปเอง):")
        r_hdr.setProperty("hdr", True)
        r_hdr.setStyleSheet("font-weight: 600; color: #cbd5e1; margin-top: 4px;")
        layout_rules.addWidget(r_hdr)

        r_row = QHBoxLayout()
        self.ed_result, self.cmb_result_unit = self._make_duration_inputs(20)
        r_row.addWidget(self.ed_result)
        r_row.addWidget(self.cmb_result_unit)
        self.chk_forever = QCheckBox("แสดงตลอดไป (กดปิดเอง)")
        self.chk_forever.toggled.connect(
            lambda on: (self.ed_result.setEnabled(not on),
                        self.cmb_result_unit.setEnabled(not on)))
        r_row.addWidget(self.chk_forever)
        r_row.addStretch()
        layout_rules.addLayout(r_row)
        self._form.addWidget(card_rules)

        # ── ปุ่มเริ่ม ──
        self.btn_start = QPushButton("▶ เริ่มเปิดโหวตขึ้นจอ")
        self.btn_start.setFixedHeight(48)
        self.btn_start.setCursor(Qt.PointingHandCursor)
        self.btn_start.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #8b5cf6, stop:1 #6d28d9);
                border: 2px solid #a78bfa;
                border-radius: 8px;
                color: #ffffff;
                font-size: 15px;
                font-weight: 800;
            }
            QPushButton:hover {
                background: #8b5cf6;
                border-color: #c4b5fd;
            }
            QPushButton:pressed {
                background: #5b21b6;
            }
        """)
        self.btn_start.clicked.connect(self._on_start)
        self._form.addWidget(self.btn_start)

        # ── โซนสถานะ (แสดงตอนโพล active) ──
        self.status_frame = QFrame()
        self.status_frame.setStyleSheet(
            "QFrame { background: #162032; border: 1px solid #283548; border-radius: 8px; }")
        st = QVBoxLayout(self.status_frame)
        st.setContentsMargins(10, 10, 10, 10)
        st.setSpacing(6)

        self.lbl_state = QLabel("กำลังโหวต")
        self.lbl_state.setProperty("hdr", True)
        st.addWidget(self.lbl_state)

        self.lbl_question_live = QLabel("")
        self.lbl_question_live.setWordWrap(True)
        st.addWidget(self.lbl_question_live)

        self._status_choices_host = QVBoxLayout()
        self._status_choices_host.setSpacing(4)
        st.addLayout(self._status_choices_host)
        self._status_choice_rows = []
        self._status_sorted = False

        self.lbl_totals = QLabel("👥 โหวตแล้ว 0 คน")
        st.addWidget(self.lbl_totals)

        self._platform_host = QHBoxLayout()
        self._platform_host.setSpacing(8)
        st.addLayout(self._platform_host)

        self.btn_end = QPushButton("⏹ จบโหวตทันที")
        self.btn_end.setProperty("danger", True)
        self.btn_end.clicked.connect(self.end_requested.emit)
        st.addWidget(self.btn_end)

        self.btn_close = QPushButton("✕ ปิดผลออกจาก Overlay")
        self.btn_close.setProperty("ghost", True)
        self.btn_close.clicked.connect(self.close_requested.emit)
        st.addWidget(self.btn_close)

        self.status_frame.setVisible(False)
        self._form.addWidget(self.status_frame)

        self._vote_end_ts = None
        self._countdown_timer = QTimer(self)
        self._countdown_timer.setInterval(1000)
        self._countdown_timer.timeout.connect(self._tick_countdown)

        self._form.addStretch()
        self._refresh_choice_labels()

    # ═══════════════════════════════════════════════════════════════════
    # TAB 2: 🎨 หน้าตา Overlay (Single-layer Section Cards)
    # ═══════════════════════════════════════════════════════════════════
    def _build_tab_design(self):
        tab_layout = QVBoxLayout(self.tab_design)
        tab_layout.setContentsMargins(0, 6, 0, 0)
        tab_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        body = QWidget()
        body.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._design_form = QVBoxLayout(body)
        self._design_form.setContentsMargins(4, 6, 12, 12)
        self._design_form.setSpacing(12)
        scroll.setWidget(body)
        tab_layout.addWidget(scroll, 1)

        # ── Card 1: รูปแบบ Layout & ตำแหน่ง ──
        card_layout, layout_layout = self._create_section_card("รูปแบบ Layout & ตำแหน่ง", "🏛️", accent_color="#38bdf8")

        lbl_layout = QLabel("รูปแบบการจัดวาง:")
        lbl_layout.setStyleSheet("font-weight: 600; color: #cbd5e1;")
        layout_layout.addWidget(lbl_layout)
        self.cmb_layout = QComboBox()
        for val, label in LAYOUT_OPTIONS:
            self.cmb_layout.addItem(label, val)
        self.cmb_layout.currentIndexChanged.connect(self._on_layout_changed)
        layout_layout.addWidget(self.cmb_layout)

        # Extend Slider
        self.wrap_extend, self.slider_extend, self.lbl_extend_val = self._create_slider_row(
            "ความยื่นออกมาจากขอบจอ (%):", 20, 30, 1, 20, "%"
        )
        layout_layout.addWidget(self.wrap_extend)

        # Minimal-specific controls
        self.wrap_min_width, self.slider_min_width, self.lbl_min_width_val = self._create_slider_row(
            "ความกว้างกล่องอิสระ (px):", 220, 700, 10, 340, "px"
        )
        layout_layout.addWidget(self.wrap_min_width)

        self.wrap_pos_x, self.slider_pos_x, self.lbl_pos_x_val = self._create_slider_row(
            "ตำแหน่ง X (ซ้าย→ขวา % ของจอ):", 5, 95, 1, 85, "%"
        )
        layout_layout.addWidget(self.wrap_pos_x)

        self.wrap_pos_y, self.slider_pos_y, self.lbl_pos_y_val = self._create_slider_row(
            "ตำแหน่ง Y (บน→ล่าง % ของจอ):", 5, 95, 1, 12, "%"
        )
        layout_layout.addWidget(self.wrap_pos_y)

        # ขยับตำแหน่ง ละเอียด (Offset X / Offset Y) สำหรับทุก Layout (เสาแนวตั้ง/แนวนอน/กล่องอิสระ)
        self.wrap_offset_x, self.slider_offset_x, self.lbl_offset_x_val = self._create_slider_row(
            "ขยับแกน X (ซ้าย ↔ ขวา):", -500, 500, 5, 0, "px", signed=True
        )
        layout_layout.addWidget(self.wrap_offset_x)

        self.wrap_offset_y, self.slider_offset_y, self.lbl_offset_y_val = self._create_slider_row(
            "เลื่อนแกน Y (บน ↕ ล่าง):", -500, 500, 5, 0, "px", signed=True
        )
        layout_layout.addWidget(self.wrap_offset_y)

        # Scale & Opacity
        self.wrap_scale, self.slider_scale, self.lbl_scale_val = self._create_slider_row(
            "สเกลขนาดรวม (สัดส่วนกล่อง):", 50, 200, 5, 100, "%"
        )
        layout_layout.addWidget(self.wrap_scale)

        self.wrap_opacity, self.slider_opacity, self.lbl_opacity_val = self._create_slider_row(
            "ความโปร่งใสของกล่อง:", 10, 100, 5, 100, "%"
        )
        layout_layout.addWidget(self.wrap_opacity)
        self._design_form.addWidget(card_layout)

        # ── Card 2: ธีมสี & สไตล์ ──
        card_theme, layout_theme = self._create_section_card("ธีมสี & สไตล์", "🎨", accent_color="#a855f7")

        lbl_th = QLabel("ธีมสีหลัก (23 รูปแบบ):")
        lbl_th.setStyleSheet("font-weight: 600; color: #cbd5e1;")
        layout_theme.addWidget(lbl_th)
        self.cmb_theme = QComboBox()
        for val, label in THEME_OPTIONS:
            self.cmb_theme.addItem(label, val)
        self.cmb_theme.currentIndexChanged.connect(lambda _: self._schedule_sync_settings())
        layout_theme.addWidget(self.cmb_theme)

        lbl_bar = QLabel("รูปแบบหลอดโหวต:")
        lbl_bar.setStyleSheet("font-weight: 600; color: #cbd5e1; margin-top: 4px;")
        layout_theme.addWidget(lbl_bar)
        self.cmb_bar_style = QComboBox()
        for val, label in BAR_STYLES:
            self.cmb_bar_style.addItem(label, val)
        self.cmb_bar_style.currentIndexChanged.connect(lambda _: self._schedule_sync_settings())
        layout_theme.addWidget(self.cmb_bar_style)

        lbl_frame = QLabel("รูปแบบกรอบ:")
        lbl_frame.setStyleSheet("font-weight: 600; color: #cbd5e1; margin-top: 4px;")
        layout_theme.addWidget(lbl_frame)
        self.cmb_frame_style = QComboBox()
        for val, label in FRAME_STYLES:
            self.cmb_frame_style.addItem(label, val)
        self.cmb_frame_style.currentIndexChanged.connect(lambda _: self._schedule_sync_settings())
        layout_theme.addWidget(self.cmb_frame_style)
        self._design_form.addWidget(card_theme)

        # ── Card 3: ขนาดตัวอักษร & นับถอยหลัง ──
        card_font, layout_font = self._create_section_card("ขนาดตัวอักษร & นับถอยหลัง", "🔤", accent_color="#fbbf24")

        self.wrap_q_fs, self.slider_q_fs, self.lbl_q_fs_val = self._create_slider_row(
            "ขนาดตัวอักษรคำถาม:", 12, 60, 1, 24, "px"
        )
        layout_font.addWidget(self.wrap_q_fs)

        self.wrap_c_fs, self.slider_c_fs, self.lbl_c_fs_val = self._create_slider_row(
            "ขนาดตัวอักษรช้อยส์:", 10, 40, 1, 18, "px"
        )
        layout_font.addWidget(self.wrap_c_fs)

        lbl_cd = QLabel("เวลานับถอยหลังแสดงเป็น:")
        lbl_cd.setStyleSheet("font-weight: 600; color: #cbd5e1; margin-top: 4px;")
        layout_font.addWidget(lbl_cd)
        self.cmb_countdown = QComboBox()
        self.cmb_countdown.addItem("🔢 ตัวเลข (00:15)", "text")
        self.cmb_countdown.addItem("📊 หลอดสีไล่เวลา (เขียว→เหลือง→แดง)", "bar")
        self.cmb_countdown.addItem("🔢+📊 ทั้งเลขและหลอด", "both")
        self.cmb_countdown.currentIndexChanged.connect(lambda _: self._schedule_sync_settings())
        layout_font.addWidget(self.cmb_countdown)
        self._design_form.addWidget(card_font)

        # ── Card 4: แอนิเมชัน & ทดสอบบนจอ ──
        card_anim, layout_anim = self._create_section_card("แอนิเมชัน & ทดสอบบนจอ", "✨", accent_color="#f472b6")

        lbl_ai = QLabel("อนิเมชันตอนเริ่มโหวต (ขาเข้า):")
        lbl_ai.setStyleSheet("font-weight: 600; color: #cbd5e1;")
        layout_anim.addWidget(lbl_ai)
        self.cmb_anim_in = QComboBox()
        for val, label in ANIM_IN_OPTIONS:
            self.cmb_anim_in.addItem(label, val)
        self.cmb_anim_in.currentIndexChanged.connect(lambda _: self._schedule_sync_settings())
        layout_anim.addWidget(self.cmb_anim_in)

        lbl_ao = QLabel("อนิเมชันตอนปิดโหวต (ขาออก):")
        lbl_ao.setStyleSheet("font-weight: 600; color: #cbd5e1; margin-top: 4px;")
        layout_anim.addWidget(lbl_ao)
        self.cmb_anim_out = QComboBox()
        for val, label in ANIM_OUT_OPTIONS:
            self.cmb_anim_out.addItem(label, val)
        self.cmb_anim_out.currentIndexChanged.connect(lambda _: self._schedule_sync_settings())
        layout_anim.addWidget(self.cmb_anim_out)

        # ปุ่มดูตัวอย่างสดบนจอ OBS
        prev_lbl = QLabel("💡 กดเพื่อส่งตัวอย่างจริงไปแสดงผลบนจอ OBS ค้างไว้สำหรับการปรับแต่ง (กดอีกครั้งหรือปิดหน้าต่างเพื่อปิด):")
        prev_lbl.setWordWrap(True)
        prev_lbl.setProperty("dim", True)
        layout_anim.addWidget(prev_lbl)

        prev_row = QHBoxLayout()
        prev_row.setSpacing(8)

        self.btn_preview_vote = QPushButton("🗳️ ตัวอย่าง (กำลังโหวต)")
        self.btn_preview_vote.setStyleSheet(STYLE_TAB2_VOTE_NORMAL)
        self.btn_preview_vote.clicked.connect(lambda: self._toggle_demo("vote"))
        prev_row.addWidget(self.btn_preview_vote)

        self.btn_preview_result = QPushButton("📊 ตัวอย่าง (สรุปผล)")
        self.btn_preview_result.setStyleSheet(STYLE_TAB2_RESULT_NORMAL)
        self.btn_preview_result.clicked.connect(lambda: self._toggle_demo("result"))
        prev_row.addWidget(self.btn_preview_result)

        layout_anim.addLayout(prev_row)
        self._design_form.addWidget(card_anim)

        self._design_form.addStretch()
        self._update_layout_visibility()

    def _on_layout_changed(self):
        self._update_layout_visibility()
        self._schedule_sync_settings()

    def _update_layout_visibility(self):
        layout = self.cmb_layout.currentData() or "vright"
        is_free = layout in ("minimal", "lite")
        self.wrap_extend.setVisible(not is_free)
        self.wrap_min_width.setVisible(is_free)
        self.wrap_pos_x.setVisible(is_free)
        self.wrap_pos_y.setVisible(is_free)

    # ───────────────────────────────────────────────────────────────────
    # Settings Get / Set & Debounced Sync
    # ───────────────────────────────────────────────────────────────────
    def _schedule_sync_settings(self):
        if self._loading_settings:
            return
        self._sync_timer.start()

    def _emit_display_settings(self):
        cfg = self.get_display_settings()
        self.display_settings_changed.emit(cfg)

    def get_display_settings(self) -> dict:
        layout = self.cmb_layout.currentData() or "vright"
        scale = round(self.slider_scale.value() / 100.0, 2)
        return {
            "ask_layout": layout,
            "ask_theme": self.cmb_theme.currentData() or "violet",
            "ask_bar_style": self.cmb_bar_style.currentData() or "classic",
            "ask_frame_style": self.cmb_frame_style.currentData() or "classic",
            "ask_countdown_style": self.cmb_countdown.currentData() or "text",
            "ask_scale": scale,
            "ask_extend_pct": self.slider_extend.value(),
            "ask_min_width": self.slider_min_width.value(),
            "ask_pos_x": self.slider_pos_x.value(),
            "ask_pos_y": self.slider_pos_y.value(),
            "ask_offset_x": self.slider_offset_x.value(),
            "ask_offset_y": self.slider_offset_y.value(),
            "ask_opacity_pct": self.slider_opacity.value(),
            "ask_question_fs": self.slider_q_fs.value(),
            "ask_choice_fs": self.slider_c_fs.value(),
            "ask_anim_in": self.cmb_anim_in.currentData() or "fade",
            "ask_anim_out": self.cmb_anim_out.currentData() or "fade",
        }

    def set_display_settings(self, cfg: dict):
        self._loading_settings = True
        try:
            # Layout
            lay = cfg.get("ask_layout", "vright")
            idx = self.cmb_layout.findData(lay)
            if idx >= 0:
                self.cmb_layout.setCurrentIndex(idx)

            # Theme
            thm = cfg.get("ask_theme", "violet")
            idx = self.cmb_theme.findData(thm)
            if idx >= 0:
                self.cmb_theme.setCurrentIndex(idx)

            # Bar style
            bar = cfg.get("ask_bar_style", "classic")
            idx = self.cmb_bar_style.findData(bar)
            if idx >= 0:
                self.cmb_bar_style.setCurrentIndex(idx)

            # Frame style
            frame = cfg.get("ask_frame_style", "classic")
            idx = self.cmb_frame_style.findData(frame)
            if idx >= 0:
                self.cmb_frame_style.setCurrentIndex(idx)

            # Countdown
            cd = cfg.get("ask_countdown_style", "text")
            idx = self.cmb_countdown.findData(cd)
            if idx >= 0:
                self.cmb_countdown.setCurrentIndex(idx)

            # Sliders
            scale_val = int(round(float(cfg.get("ask_scale", 1.0)) * 100))
            self.slider_scale.setValue(scale_val)
            self.lbl_scale_val.setText(f"{scale_val}%")

            ext_val = int(cfg.get("ask_extend_pct", 20))
            self.slider_extend.setValue(ext_val)
            self.lbl_extend_val.setText(f"{ext_val}%")

            minw_val = int(cfg.get("ask_min_width", 340))
            self.slider_min_width.setValue(minw_val)
            self.lbl_min_width_val.setText(f"{minw_val}px")

            px_val = int(cfg.get("ask_pos_x", 85))
            self.slider_pos_x.setValue(px_val)
            self.lbl_pos_x_val.setText(f"{px_val}%")

            py_val = int(cfg.get("ask_pos_y", 12))
            self.slider_pos_y.setValue(py_val)
            self.lbl_pos_y_val.setText(f"{py_val}%")

            ox_val = int(cfg.get("ask_offset_x", 0))
            self.slider_offset_x.setValue(ox_val)
            self.lbl_offset_x_val.setText(f"{ox_val:+d}px" if ox_val != 0 else "0px")

            oy_val = int(cfg.get("ask_offset_y", 0))
            self.slider_offset_y.setValue(oy_val)
            self.lbl_offset_y_val.setText(f"{oy_val:+d}px" if oy_val != 0 else "0px")

            op_val = int(cfg.get("ask_opacity_pct", 100))
            self.slider_opacity.setValue(op_val)
            self.lbl_opacity_val.setText(f"{op_val}%")

            qfs_val = int(cfg.get("ask_question_fs", 24))
            self.slider_q_fs.setValue(qfs_val)
            self.lbl_q_fs_val.setText(f"{qfs_val}px")

            cfs_val = int(cfg.get("ask_choice_fs", 18))
            self.slider_c_fs.setValue(cfs_val)
            self.lbl_c_fs_val.setText(f"{cfs_val}px")

            # Animations
            ain = cfg.get("ask_anim_in", "fade")
            idx = self.cmb_anim_in.findData(ain)
            if idx >= 0:
                self.cmb_anim_in.setCurrentIndex(idx)

            aout = cfg.get("ask_anim_out", "fade")
            idx = self.cmb_anim_out.findData(aout)
            if idx >= 0:
                self.cmb_anim_out.setCurrentIndex(idx)

            self._update_layout_visibility()
        finally:
            self._loading_settings = False

    # ───────────────────────────────────────────────────────────────────
    # Copy OBS URL
    # ───────────────────────────────────────────────────────────────────
    def _copy_obs_url(self):
        port = 8801
        try:
            parent = self.parent()
            if parent and hasattr(parent, "composer_server") and parent.composer_server:
                port = getattr(parent.composer_server, "port", 8801)
            elif parent and hasattr(parent, "settings"):
                port = getattr(parent.settings, "composer_port", 8801)
        except Exception:
            port = 8801
        url = f"http://localhost:{port}/"
        QApplication.clipboard().setText(url)
        self._show_toast("📋 คัดลอกลิงก์ OBS สำเร็จแล้ว!")

    # ── choices ──────────────────────────────────────────────
    def _add_choice_row(self, text: str = ""):
        if len(self._choice_rows) >= MAX_CHOICES:
            return
        row = QHBoxLayout()
        row.setSpacing(6)
        key_lbl = QLabel()
        key_lbl.setFixedWidth(18)
        inp = QLineEdit()
        inp.setPlaceholderText("คำตอบ...")
        inp.setText(text)
        btn_del = QPushButton("✕")
        btn_del.setProperty("ghost", True)
        btn_del.setFixedSize(30, 26)
        row.addWidget(key_lbl)
        row.addWidget(inp, 1)
        row.addWidget(btn_del)
        self._choices_host.addLayout(row)
        entry = {"layout": row, "key": key_lbl, "inp": inp, "del": btn_del}
        self._choice_rows.append(entry)
        btn_del.clicked.connect(lambda _, e=entry: self._remove_choice(e))
        self._refresh_choice_labels()

    def _add_default_choice(self):
        self._add_choice_row("")

    def _remove_choice(self, entry):
        if len(self._choice_rows) <= 2:
            return
        for w in (entry["key"], entry["inp"], entry["del"]):
            w.deleteLater()
        self._choice_rows.remove(entry)
        self._refresh_choice_labels()

    def _update_add_btn_state(self):
        full = len(self._choice_rows) >= MAX_CHOICES
        if full:
            self.btn_add_choice.setText(f"ไม่สามารถเพิ่มได้เกิน {MAX_CHOICES}")
            self.btn_add_choice.setStyleSheet(
                "background:#dc2626;color:#fff;border:none;border-radius:6px;"
                "padding:7px 14px;font-size:12px;font-weight:600;")
        else:
            self.btn_add_choice.setText("＋ เพิ่มคำตอบ")
            self.btn_add_choice.setStyleSheet("")
            self.btn_add_choice.setProperty("ghost", True)

    def _refresh_choice_labels(self):
        letters = self.rb_letters.isChecked() if hasattr(self, "rb_letters") else True
        for i, entry in enumerate(self._choice_rows):
            entry["key"].setText(LETTERS[i] if letters else str(i + 1))
        left = MAX_CHOICES - len(self._choice_rows)
        if hasattr(self, "lbl_choice_hint"):
            self.lbl_choice_hint.setText(
                f"({len(self._choice_rows)}/{MAX_CHOICES} ช้อยส์"
                + (f" — เพิ่มได้อีก {left}" if left > 0 else " — เต็ม") + ")")
        for entry in self._choice_rows:
            entry["del"].setEnabled(len(self._choice_rows) > 2)
        if hasattr(self, 'btn_add_choice'):
            self._update_add_btn_state()

    # ── Presets ──────────────────────────────────────────────
    def set_presets(self, presets):
        cur = self.cmb_preset.currentText()
        self.cmb_preset.blockSignals(True)
        self.cmb_preset.clear()
        self.cmb_preset.addItem("⚡ เรียกใช้ Preset...", "")
        for pr in (presets or []):
            name = (pr or {}).get("name", "?")
            self.cmb_preset.addItem(name, pr)
        idx = self.cmb_preset.findText(cur) if cur else -1
        if idx > 0:
            self.cmb_preset.setCurrentIndex(idx)
        elif self.cmb_preset.currentIndex() != 0:
            self.cmb_preset.setCurrentIndex(0)
        self.cmb_preset.blockSignals(False)

    def _on_preset_selected(self, idx):
        if idx <= 0:
            return
        pr = self.cmb_preset.itemData(idx)
        if not pr:
            return
        self.inp_question.setText(pr.get("question", ""))
        choices = pr.get("choices", [])
        while self._choice_rows:
            entry = self._choice_rows.pop()
            for w in (entry["key"], entry["inp"], entry["del"]):
                w.deleteLater()
        for c in choices:
            self._add_choice_row(str(c))
        while len(self._choice_rows) < 2:
            self._add_choice_row("")
        if pr.get("answer_mode") == "numbers":
            self.rb_numbers.setChecked(True)
        else:
            self.rb_letters.setChecked(True)
        self._refresh_choice_labels()

        # Restore duration & no_limit
        if pr.get("no_limit") or pr.get("duration_sec") is None:
            self.chk_no_limit.setChecked(True)
        else:
            self.chk_no_limit.setChecked(False)
            try:
                dur = int(pr.get("duration_sec", 30))
                if dur >= 60 and dur % 60 == 0:
                    self.cmb_vote_unit.setCurrentIndex(1)
                    self.ed_vote.setText(str(dur // 60))
                else:
                    self.cmb_vote_unit.setCurrentIndex(0)
                    self.ed_vote.setText(str(dur))
            except Exception:
                pass

        # Restore results duration & forever
        if pr.get("forever") or pr.get("results_duration_sec") is None:
            self.chk_forever.setChecked(True)
        else:
            self.chk_forever.setChecked(False)
            try:
                rdur = int(pr.get("results_duration_sec", 20))
                if rdur >= 60 and rdur % 60 == 0:
                    self.cmb_result_unit.setCurrentIndex(1)
                    self.ed_result.setText(str(rdur // 60))
                else:
                    self.cmb_result_unit.setCurrentIndex(0)
                    self.ed_result.setText(str(rdur))
            except Exception:
                pass

        # Restore realtime mode
        if pr.get("realtime", True):
            self.rb_realtime.setChecked(True)
        else:
            self.rb_summary.setChecked(True)

    def _on_preset_save(self):
        question = self.inp_question.text().strip()
        choices = [e["inp"].text().strip() for e in self._choice_rows if e["inp"].text().strip()]
        if not question or len(choices) < 2:
            self._show_toast("⚠ ต้องมีคำถาม + คำตอบอย่างน้อย 2 ข้อ")
            return
        if not hasattr(self, '_preset_name_inp'):
            self._preset_name_inp = QLineEdit()
            self._preset_name_inp.setPlaceholderText("พิมพ์ชื่อ Preset แล้วกดบันทึกอีกครั้ง...")
            self._preset_name_inp.setStyleSheet(
                "background:#1e293b;color:#e2e8f0;border:1px solid #7c3aed;"
                "border-radius:6px;padding:6px 10px;font-size:12px;")
            self._form.insertWidget(1, self._preset_name_inp)
            self._show_toast("📝 พิมพ์ชื่อ Preset ในช่องด้านบน แล้วกด 💾 บันทึก")
            return
        name = self._preset_name_inp.text().strip() or question[:30]
        self.preset_save_requested.emit({
            "name": name,
            "question": question,
            "choices": choices,
            "answer_mode": "letters" if self.rb_letters.isChecked() else "numbers",
            "duration_sec": None if self.chk_no_limit.isChecked()
                else self._duration_seconds(self.ed_vote, self.cmb_vote_unit),
            "no_limit": self.chk_no_limit.isChecked(),
            "results_duration_sec": None if self.chk_forever.isChecked()
                else self._duration_seconds(self.ed_result, self.cmb_result_unit),
            "forever": self.chk_forever.isChecked(),
            "realtime": self.rb_realtime.isChecked(),
        })
        self._preset_name_inp.setText("")
        self._show_toast(f"💾 บันทึก '{name}' เรียบร้อย")

    def _show_toast(self, text: str):
        if hasattr(self, '_toast_lbl') and self._toast_lbl:
            self._toast_lbl.deleteLater()
        self._toast_lbl = QLabel(text)
        self._toast_lbl.setAlignment(Qt.AlignCenter)
        self._toast_lbl.setStyleSheet(
            "background:#059669;color:#fff;border-radius:6px;padding:6px;"
            "font-size:12px;font-weight:600;")
        self.layout().addWidget(self._toast_lbl)
        QTimer.singleShot(2500, lambda: (
            self._toast_lbl.deleteLater() if hasattr(self, '_toast_lbl') and self._toast_lbl else None,
            setattr(self, '_toast_lbl', None)
        ))

    def _on_preset_delete(self):
        idx = self.cmb_preset.currentIndex()
        if idx <= 0:
            return
        name = self.cmb_preset.itemText(idx)
        if QMessageBox.question(self, "ลบ Preset", f'ลบ "{name}" ?') == QMessageBox.Yes:
            self.preset_delete_requested.emit(name)

    # ── ช่องกรอกเวลา + หน่วย ──
    def _make_duration_inputs(self, default_sec: int):
        from PySide6.QtGui import QIntValidator
        ed = QLineEdit(str(default_sec))
        ed.setValidator(QIntValidator(1, 9999))
        ed.setFixedWidth(70)
        ed.setAlignment(Qt.AlignCenter)
        cmb = QComboBox()
        cmb.addItems(["วินาที", "นาที"])
        cmb.setFixedWidth(80)

        def _on_unit(idx):
            try:
                v = max(1, int(ed.text() or "0"))
                if idx == 1:
                    ed.setText(str(max(1, round(v / 60))))
                else:
                    ed.setText(str(min(3600, v * 60)))
            except Exception:
                pass
        cmb.currentIndexChanged.connect(_on_unit)
        return ed, cmb

    def _duration_seconds(self, ed, cmb) -> int:
        try:
            v = int(ed.text() or "0")
        except ValueError:
            v = 1
        if cmb.currentIndex() == 1:
            v *= 60
        return max(5, min(3600, v))

    def _on_start(self):
        question = self.inp_question.text().strip()
        choices = []
        for entry in self._choice_rows:
            t = entry["inp"].text().strip()
            if t:
                choices.append(t)
        if not question or len(choices) < 2:
            self.status_frame.setVisible(True)
            self.btn_end.setVisible(False)
            self.btn_close.setVisible(False)
            self.lbl_question_live.setText("")
            self.lbl_totals.setText("")
            self._rebuild_status_choices({"choices": []}, False)
            while self._platform_host.count():
                item = self._platform_host.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            self.lbl_state.setText("⚠ ต้องมีคำถาม + คำตอบอย่างน้อย 2 ข้อ")
            QTimer.singleShot(2500, self.show_idle)
            return
        self.start_requested.emit({
            "question": question,
            "choices": choices,
            "answer_mode": "letters" if self.rb_letters.isChecked() else "numbers",
            "duration_sec": None if self.chk_no_limit.isChecked()
                else self._duration_seconds(self.ed_vote, self.cmb_vote_unit),
            "realtime": self.rb_realtime.isChecked(),
            "results_duration_sec": None if self.chk_forever.isChecked()
                else self._duration_seconds(self.ed_result, self.cmb_result_unit),
        })

    # ── live status (เรียกจาก app) ───────────────────────────
    def show_voting(self, payload: dict):
        self.reset_demo_state()
        self.status_frame.setVisible(True)
        self.btn_start.setEnabled(False)
        self.btn_end.setVisible(True)
        self.btn_close.setVisible(False)
        self.lbl_question_live.setText(payload.get("question", ""))
        end_ts = payload.get("end_ts")
        if end_ts:
            self._vote_end_ts = float(end_ts)
            self._countdown_timer.start()
            self._tick_countdown()
        else:
            self._vote_end_ts = None
            self._countdown_timer.stop()
            self.lbl_state.setText("🗳 กำลังโหวต... (ไม่จำกัดเวลา)")
        self.update_live_counts(payload)

    def _tick_countdown(self):
        if not self._vote_end_ts:
            return
        left = self._vote_end_ts - time.time()
        if left <= 0:
            self.lbl_state.setText("🗳 กำลังโหวต... ⏳ กำลังปิดโหวต...")
            self._countdown_timer.stop()
            return
        m, s = divmod(int(left + 0.999), 60)
        txt = f"🗳 กำลังโหวต... ⏳ เหลืออีก {m}:{s:02d}"
        if left <= 10:
            txt += " ⚠"
        self.lbl_state.setText(txt)

    def show_ended(self, payload: dict):
        self.reset_demo_state()
        self._countdown_timer.stop()
        self._vote_end_ts = None
        self.status_frame.setVisible(True)
        self.btn_start.setEnabled(False)
        self.btn_end.setVisible(False)
        self.btn_close.setVisible(True)
        self.lbl_state.setText("📊 จบโหวตแล้ว — แสดงสรุปผล")
        self.lbl_question_live.setText(payload.get("question", ""))
        self.update_live_counts(payload)

    def show_idle(self):
        self._countdown_timer.stop()
        self._vote_end_ts = None
        self.status_frame.setVisible(False)
        self.btn_start.setEnabled(True)

    def _add_status_choice_row(self):
        row = QHBoxLayout()
        row.setSpacing(6)
        key = QLabel()
        key.setFixedWidth(16)
        key.setStyleSheet("color:#f59f0b; font-weight:700; font-size:12px; background:transparent; border:none;")
        text = QLabel()
        text.setFixedWidth(115)
        text.setStyleSheet("color:#cbd5e1; font-size:12px; background:transparent; border:none;")
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setFixedHeight(9)
        bar.setTextVisible(False)
        bar.setStyleSheet(
            "QProgressBar { background:#0f1526; border:none; border-radius:4px; }"
            "QProgressBar::chunk { background:#7c3aed; border-radius:4px; }")
        cnt = QLabel()
        cnt.setFixedWidth(64)
        cnt.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        cnt.setStyleSheet("color:#e2e8f0; font-size:11px; background:transparent; border:none;")
        row.addWidget(key)
        row.addWidget(text)
        row.addWidget(bar, 1)
        row.addWidget(cnt)
        self._status_choices_host.addLayout(row)
        self._status_choice_rows.append(
            {"layout": row, "key": key, "text": text, "bar": bar, "cnt": cnt})

    def _rebuild_status_choices(self, payload: dict, ended: bool):
        for r in self._status_choice_rows:
            try:
                self._status_choices_host.removeItem(r["layout"])
                for w in (r["key"], r["text"], r["bar"], r["cnt"]):
                    w.deleteLater()
            except Exception:
                pass
        self._status_choice_rows = []
        self._status_sorted = ended
        choices = payload.get("choices", [])
        for _ in choices:
            self._add_status_choice_row()

    def update_live_counts(self, payload: dict):
        total = payload.get("total_voters", 0)
        self.lbl_totals.setText(f"👥 โหวตแล้ว {total} คน")
        counts = payload.get("counts", [])
        keys = payload.get("keys", [])
        choices = payload.get("choices", [])
        ended = payload.get("phase") == "ended"
        if len(self._status_choice_rows) != len(choices) or self._status_sorted != ended:
            self._rebuild_status_choices(payload, ended)
        order = list(range(len(choices)))
        if ended:
            order.sort(key=lambda i: -(counts[i] if i < len(counts) else 0))
        maxc = 1
        if counts:
            maxc = max(1, max(counts))
        for r, i in enumerate(order):
            row = self._status_choice_rows[r]
            k = keys[i] if i < len(keys) else "?"
            label = choices[i] if i < len(choices) else ""
            c = counts[i] if i < len(counts) else 0
            pct = round(c * 100 / total) if total else 0
            row["key"].setText(k)
            row["text"].setText(label)
            row["text"].setToolTip(label)
            row["bar"].setValue(int(c * 100 / maxc))
            row["cnt"].setText(f"{c} ({pct}%)")
            color = "#34d399" if (ended and r == 0 and c > 0) else "#f59f0b"
            row["key"].setStyleSheet(
                f"color:{color}; font-weight:700; font-size:12px; background:transparent; border:none;")
            row["cnt"].setStyleSheet(
                ("color:#34d399; font-weight:600;" if (ended and r == 0 and c > 0)
                 else "color:#e2e8f0;") +
                " font-size:11px; background:transparent; border:none;")
        self._update_platform_row(payload.get("per_platform", {}), total)

    def _update_platform_row(self, per_platform: dict, total: int):
        while self._platform_host.count():
            item = self._platform_host.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        if not per_platform or total <= 0:
            lbl = QLabel("ยังไม่มีผู้โหวต")
            lbl.setProperty("dim", True)
            lbl.setStyleSheet("color:#64748b; font-size:11px; background:transparent; border:none;")
            self._platform_host.addWidget(lbl)
            self._platform_host.addStretch()
            return
        from ui.platform_icons import get_platform_pixmap
        order = ["twitch", "youtube", "mylive", "kick", "tiktok"]
        names = {"twitch": "Twitch", "youtube": "YouTube", "mylive": "MyLive",
                 "kick": "KICK", "tiktok": "TikTok"}
        plats = [p for p in order if per_platform.get(p, 0) > 0]
        plats += sorted(set(per_platform) - set(order))
        for p in plats:
            n = per_platform.get(p, 0)
            if n <= 0:
                continue
            icon = QLabel()
            pix = get_platform_pixmap(p, 14)
            if not pix.isNull():
                icon.setPixmap(pix)
            else:
                icon.setText(names.get(p, str(p).capitalize()))
                icon.setStyleSheet("color:#94a3b8; font-size:11px; background:transparent; border:none;")
            cnt = QLabel(f"{n}")
            cnt.setStyleSheet("color:#cbd5e1; font-size:11px; background:transparent; border:none;")
            self._platform_host.addWidget(icon)
            self._platform_host.addWidget(cnt)
        self._platform_host.addStretch()
