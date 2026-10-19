# -*- coding: utf-8 -*-
"""giveaway_panel.py — แผงควบคุมระบบเช็คชื่อ & สุ่มแจกรางวัล (Loyalty Giveaway)

ดีไซน์ใหม่: Seamless Flat (ไร้กรอบซ้อน ไร้กล่องครอบ)
- ตัด container QFrame ที่เป็นกล่องสี่เหลี่ยมครอบเนื้อหาออกทั้งหมด (No nested card boxes)
- ไหลลื่นแบบผืนผ้าเดียว (Unified Canvas) ใช้การจัดวรรคและเส้นแบ่งบางๆ สไตล์ซอฟต์แวร์ระดับมืออาชีพ
- รองรับทั้งรอบเดียว และหลายด่าน (2-5 ด่าน) แก้ไขคำสั่งได้อิสระ
- ตัวเลือกเวลาทั้งแบบนับถอยหลังและเปิดค้างจนกว่าจะปิดเอง
- ระบบ Export Excel CSV และล้างข้อมูลที่ปลอดภัย
"""
from __future__ import annotations

import os
import time
import random
from typing import Optional, List

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QFrame, QLabel, QLineEdit, QPushButton, QVBoxLayout, QHBoxLayout,
    QWidget, QSpinBox, QCheckBox, QScrollArea, QComboBox, QMessageBox,
    QProgressBar, QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QApplication, QFileDialog, QDialog, QButtonGroup, QRadioButton, QSlider,
)

from giveaway_service import GiveawayService, Participant, WinnerRecord

STYLE_PREVIEW_NORMAL = """
    QPushButton {
        background-color: #0c2135;
        border: 1px solid #0284c7;
        border-radius: 6px;
        color: #38bdf8;
        font-weight: 700;
        font-size: 11.5px;
        padding: 4px 11px;
    }
    QPushButton:hover {
        background-color: #0e3052;
        border-color: #38bdf8;
        color: #e0f2fe;
    }
    QPushButton:pressed {
        background-color: #0369a1;
    }
"""

STYLE_DEMO_RED = """
    QPushButton {
        background-color: #dc2626;
        border: 1px solid #ef4444;
        border-radius: 6px;
        color: #ffffff;
        font-weight: 700;
        font-size: 11.5px;
        padding: 4px 11px;
    }
    QPushButton:hover {
        background-color: #ef4444;
        border-color: #f87171;
    }
    QPushButton:pressed {
        background-color: #b91c1c;
    }
"""

STYLE_DRAW_DEMO_NORMAL = """
    QPushButton {
        background: #7c3aed;
        border: 1px solid #9333ea;
        border-radius: 6px;
        color: #ffffff;
        font-weight: 700;
        font-size: 11.5px;
        padding: 4px 11px;
    }
    QPushButton:hover {
        background: #8b5cf6;
        border-color: #c4b5fd;
    }
    QPushButton:pressed {
        background: #6d28d9;
    }
"""


class DurationStepper(QWidget):
    """ตัวปรับเวลาแบบ Stepper [-] [เวลา] [+] สไตล์โมเดิร์น ไร้ปัญหารูปลูกศรเพี้ยนหรือทับตัวหนังสือ"""
    valueChanged = Signal(int)  # ส่งค่าหน่วยเป็นวินาที (seconds)

    def __init__(self, parent=None, default_secs: int = 60):
        super().__init__(parent)
        self._secs = default_secs
        self.setObjectName("DurationStepper")
        self.setFixedSize(126, 34)
        self.setStyleSheet("""
            QWidget#DurationStepper {
                background-color: #131d31;
                border: 1.5px solid #334155;
                border-radius: 6px;
            }
            QWidget#DurationStepper:hover {
                border-color: #475569;
            }
        """)

        h = QHBoxLayout(self)
        h.setContentsMargins(4, 3, 4, 3)
        h.setSpacing(4)

        self.btn_minus = QPushButton("-")
        self.btn_minus.setFixedSize(26, 26)
        self.btn_minus.setCursor(Qt.PointingHandCursor)
        self.btn_minus.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #ffffff;
                font-size: 16px;
                font-weight: 900;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 0px;
                margin: 0px;
            }
            QPushButton:hover {
                background-color: #334155;
                color: #fbbf24;
                border-color: #fbbf24;
            }
            QPushButton:pressed {
                background-color: #0f172a;
            }
        """)
        self.btn_minus.clicked.connect(self._step_down)
        h.addWidget(self.btn_minus)

        self.lbl_val = QLabel(self._format_secs(self._secs))
        self.lbl_val.setAlignment(Qt.AlignCenter)
        self.lbl_val.setStyleSheet("color: #fbbf24; font-size: 13.5px; font-weight: 800; background: transparent; border: none;")
        h.addWidget(self.lbl_val, 1)

        self.btn_plus = QPushButton("+")
        self.btn_plus.setFixedSize(26, 26)
        self.btn_plus.setCursor(Qt.PointingHandCursor)
        self.btn_plus.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #ffffff;
                font-size: 16px;
                font-weight: 900;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 0px;
                margin: 0px;
            }
            QPushButton:hover {
                background-color: #334155;
                color: #fbbf24;
                border-color: #fbbf24;
            }
            QPushButton:pressed {
                background-color: #0f172a;
            }
        """)
        self.btn_plus.clicked.connect(self._step_up)
        h.addWidget(self.btn_plus)

    def _format_secs(self, s: int) -> str:
        if s < 60:
            return f"{s} วิ"
        mins = s // 60
        return f"{mins} นาที"

    def _step_down(self):
        if self._secs <= 30:
            return
        elif self._secs <= 60:
            self.set_seconds(30)
        else:
            self.set_seconds(self._secs - 60)

    def _step_up(self):
        if self._secs < 30:
            self.set_seconds(30)
        elif self._secs < 60:
            self.set_seconds(60)
        elif self._secs < 1200:
            self.set_seconds(self._secs + 60)

    def seconds(self) -> int:
        return self._secs

    def set_seconds(self, s: int):
        s = max(30, min(1200, s))
        if s != self._secs:
            self._secs = s
            self.lbl_val.setText(self._format_secs(self._secs))
            self.valueChanged.emit(self._secs)

    def value(self) -> int:
        return max(1, self._secs // 60)

    def setValue(self, mins: int):
        self.set_seconds(mins * 60)

    def setRange(self, min_val: int, max_val: int):
        pass


class RoundNameDialog(QDialog):
    """ไดอะล็อกตั้งชื่อรอบกิจกรรม สไตล์ Studio Dark เรียบหรู"""

    def __init__(self, title: str, default_name: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedWidth(380)
        self.setStyleSheet("""
            QDialog {
                background-color: #0b1120;
                border: 1px solid #1e293b;
                border-radius: 10px;
            }
            QLabel {
                color: #e2e8f0;
                font-size: 13px;
                font-weight: 600;
            }
            QLineEdit {
                background-color: #131d31;
                border: 1.5px solid #3b82f6;
                border-radius: 6px;
                color: #ffffff;
                font-size: 13.5px;
                padding: 8px 12px;
            }
            QLineEdit:focus {
                border-color: #60a5fa;
                background-color: #17243c;
            }
        """)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 18)
        layout.setSpacing(14)

        lbl = QLabel("ระบุชื่อรอบกิจกรรม:")
        layout.addWidget(lbl)

        self.inp_name = QLineEdit(default_name)
        self.inp_name.setPlaceholderText("เช่น รอบที่ 1, รอบตอบคำถาม, รอบแจกไอดี...")
        self.inp_name.selectAll()
        layout.addWidget(self.inp_name)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()

        self.btn_cancel = QPushButton("ยกเลิก")
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #94a3b8;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 7px 16px;
                font-weight: 600;
                font-size: 12.5px;
            }
            QPushButton:hover {
                background-color: #334155;
                color: #f1f5f9;
            }
        """)
        self.btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_cancel)

        self.btn_ok = QPushButton("ตกลง")
        self.btn_ok.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0284c7, stop:1 #0369a1);
                color: #ffffff;
                border: 1.5px solid #38bdf8;
                border-radius: 6px;
                padding: 7px 20px;
                font-weight: 700;
                font-size: 12.5px;
            }
            QPushButton:hover {
                background: #0284c7;
                border-color: #7dd3fc;
            }
            QPushButton:pressed {
                background: #0369a1;
            }
        """)
        self.btn_ok.clicked.connect(self.accept)
        self.inp_name.returnPressed.connect(self.accept)
        btn_row.addWidget(self.btn_ok)

        layout.addLayout(btn_row)

    def get_name(self) -> str:
        return self.inp_name.text().strip()


class GiveawayPanel(QFrame):
    """หน้าต่างแผงควบคุมระบบ Giveaway สไตล์ Seamless Flat ปราศจากกรอบซ้อนกรอบ"""

    closed = Signal()

    def __init__(self, service: GiveawayService, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.service = service
        self.setObjectName("GiveawayPanel")
        self.setWindowTitle("🎁 ระบบเช็คชื่อ & สุ่มแจกรางวัล — Giveaway")
        self.resize(540, 780)
        self.setMinimumSize(380, 500)
        self.setWindowFlags(Qt.Window | Qt.WindowCloseButtonHint | Qt.WindowMinMaxButtonsHint)

        # ตัวจับเวลานับถอยหลัง
        self._timer = QTimer(self)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._on_timer_tick)

        # ตัวจับเวลาอนิเมชั่นสล็อตหมุนสุ่ม
        self._slot_timer = QTimer(self)
        self._slot_timer.setInterval(45)
        self._slot_timer.timeout.connect(self._on_slot_tick)
        self._slot_ticks_left: int = 0
        self._slot_pool: List[Participant] = []
        self._pending_winner: Optional[Participant] = None

        self._init_qss()
        self._build_ui()
        self._connect_service_signals()
        self._sync_mode_ui()

        # ตัวตรวจเช็คสถานะ Widget ใน Overlay เป็นระยะ (เช็คทุก 1.5 วินาที)
        self._widget_check_timer = QTimer(self)
        self._widget_check_timer.setInterval(1500)
        self._widget_check_timer.timeout.connect(self._check_widget_status)
        self._widget_check_timer.start()
        self._check_widget_status()

    def _init_qss(self):
        """ธีม Seamless Flat — ตัดกรอบซ้อนกรอบออกทั้งหมด เรียบหรู สะอาดตา"""
        self.setStyleSheet("""
            QFrame#GiveawayPanel {
                background-color: #0b1120;
                border: 1px solid #1e293b;
            }
            QLabel {
                color: #e2e8f0;
                font-size: 13px;
                background: transparent;
                border: none;
            }
            QLabel[role="section"] {
                color: #38bdf8;
                font-size: 12px;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            QLabel[role="hint"] {
                color: #64748b;
                font-size: 11.5px;
            }
            QTabWidget::pane {
                border: none;
                border-top: 1px solid #1e293b;
                background-color: #0b1120;
                top: 0px;
            }
            QTabBar::tab {
                background: transparent;
                color: #94a3b8;
                padding: 8px 12px;
                font-weight: 700;
                font-size: 12.5px;
                border: none;
                border-bottom: 2px solid transparent;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                color: #38bdf8;
                border-bottom: 2px solid #38bdf8;
                font-weight: 700;
            }
            QTabBar::tab:hover:!selected {
                color: #f1f5f9;
            }
            QLineEdit, QSpinBox, QComboBox {
                background-color: #162032;
                color: #f8fafc;
                border: 1px solid #283548;
                border-radius: 4px;
                padding: 7px 10px;
                font-size: 13px;
            }
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
                border-color: #38bdf8;
                background-color: #1a273e;
            }
            QPushButton {
                background-color: #2563eb;
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
            QPushButton:pressed {
                background-color: #1e40af;
            }
            QPushButton[variant="success"] {
                background-color: #059669;
            }
            QPushButton[variant="success"]:hover {
                background-color: #047857;
            }
            QPushButton[variant="danger"] {
                background-color: #dc2626;
            }
            QPushButton[variant="danger"]:hover {
                background-color: #b91c1c;
            }
            QPushButton[variant="amber"] {
                background-color: #f59e0b;
                color: #0f172a;
            }
            QPushButton[variant="amber"]:hover {
                background-color: #d97706;
            }
            QPushButton[variant="ghost"] {
                background-color: #162032;
                border: 1px solid #283548;
                color: #cbd5e1;
            }
            QPushButton[variant="ghost"]:hover {
                background-color: #202d44;
                border-color: #3b4d6b;
                color: #ffffff;
            }
            QPushButton[variant="mode_toggle"] {
                background-color: #111a2e;
                border: 2px solid #22324d;
                border-radius: 8px;
                padding: 10px 16px;
                font-size: 13.5px;
                color: #94a3b8;
                font-weight: 700;
                min-height: 24px;
            }
            QPushButton[variant="mode_toggle"]:hover {
                background-color: #16243d;
                border-color: #0ea5e9;
                color: #f8fafc;
            }
            QPushButton[variant="mode_toggle"]:checked {
                background-color: #0284c7;
                border: 2px solid #38bdf8;
                color: #ffffff;
                font-weight: 800;
            }
            QPushButton[variant="display_toggle"] {
                background-color: #111a2e;
                border: 2px solid #22324d;
                border-radius: 8px;
                padding: 10px 16px;
                font-size: 13px;
                color: #94a3b8;
                font-weight: 700;
                min-height: 24px;
            }
            QPushButton[variant="display_toggle"]:hover {
                background-color: #16243d;
                border-color: #0ea5e9;
                color: #f8fafc;
            }
            QPushButton[variant="display_toggle"]:checked {
                background-color: #0284c7;
                border: 2px solid #38bdf8;
                color: #ffffff;
                font-weight: 800;
            }
            QPushButton#btn_toggle_checkpoint[variant="success"] {
                background-color: #059669;
                border: 2px solid #10b981;
                border-radius: 8px;
                color: #ffffff;
                font-size: 15.5px;
                font-weight: 800;
                padding: 11px 20px;
            }
            QPushButton#btn_toggle_checkpoint[variant="success"]:hover {
                background-color: #047857;
                border-color: #34d399;
            }
            QPushButton#btn_toggle_checkpoint[variant="danger"] {
                background-color: #dc2626;
                border: 2px solid #f87171;
                border-radius: 8px;
                color: #ffffff;
                font-size: 15.5px;
                font-weight: 800;
                padding: 11px 20px;
            }
            QPushButton#btn_toggle_checkpoint[variant="danger"]:hover {
                background-color: #b91c1c;
                border-color: #ef4444;
            }
            QProgressBar {
                border: none;
                border-radius: 3px;
                background-color: #162032;
                text-align: center;
                color: #ffffff;
                font-weight: bold;
                height: 18px;
            }
            QProgressBar::chunk {
                background-color: #0284c7;
                border-radius: 3px;
            }
            QTableWidget {
                background-color: #0d1527;
                border: 1px solid #1e293b;
                border-radius: 4px;
                gridline-color: #162032;
                color: #f8fafc;
                font-size: 12.5px;
            }
            QHeaderView::section {
                background-color: #111a2e;
                color: #94a3b8;
                padding: 7px;
                border: none;
                border-bottom: 1px solid #1e293b;
                border-right: 1px solid #162032;
                font-weight: bold;
            }
            QRadioButton {
                color: #cbd5e1;
                font-size: 13px;
                background: transparent;
                spacing: 6px;
            }
            QCheckBox {
                color: #cbd5e1;
                font-size: 12.5px;
                background: transparent;
                spacing: 6px;
            }
            QSlider::groove:horizontal {
                height: 4px;
                background: #1e293b;
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #0284c7;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #38bdf8;
                width: 14px;
                margin-top: -5px;
                margin-bottom: -5px;
                border-radius: 7px;
            }
            QSlider::handle:horizontal:hover {
                background: #7dd3fc;
            }
        """)

    def _build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(14, 12, 14, 12)
        root_layout.setSpacing(8)

        # ── Header Bar ──
        hdr_layout = QHBoxLayout()
        hdr_layout.setSpacing(8)
        hdr_title = QLabel("🎁 Giveaway")
        hdr_title.setStyleSheet("font-size: 15px; font-weight: 800; color: #f59e0b;")
        hdr_layout.addWidget(hdr_title)

        self.lbl_status_badge = QLabel("พร้อมเริ่ม")
        self.lbl_status_badge.setStyleSheet(
            "background: #162032; color: #94a3b8; border-radius: 4px; "
            "padding: 3px 8px; font-size: 11px; font-weight: bold;"
        )
        hdr_layout.addWidget(self.lbl_status_badge)
        hdr_layout.addStretch()

        self.btn_copy_obs = QPushButton("📋 คัดลอกลิงก์ OBS")
        self.btn_copy_obs.setProperty("variant", "ghost")
        self.btn_copy_obs.setStyleSheet("font-size: 11.5px; padding: 4px 10px; color: #38bdf8; border-color: #0284c7; font-weight: bold;")
        self.btn_copy_obs.setToolTip("คัดลอก URL สำหรับนำไปใส่เป็น Browser Source ใน OBS Studio")
        self.btn_copy_obs.clicked.connect(self._copy_obs_url)
        hdr_layout.addWidget(self.btn_copy_obs)
        root_layout.addLayout(hdr_layout)

        # ── Stacked Container (Tabs vs Blocker) ──
        from PySide6.QtWidgets import QStackedWidget
        self.stack = QStackedWidget()

        # Page 0: หน้าแท็บจัดการ Giveaway ปกติ
        self.tabs = QTabWidget()
        self.tab_checkpoint = QWidget()
        self.tab_participants = QWidget()
        self.tab_draw = QWidget()

        self._build_tab_checkpoint()
        self._build_tab_participants()
        self._build_tab_draw()

        self.tabs.addTab(self.tab_checkpoint, "📍 เช็คชื่อ & ตั้งค่า")
        self.tabs.addTab(self.tab_participants, "👥 รายชื่อผู้เข้าร่วม")
        self.tabs.addTab(self.tab_draw, "🎰 สุ่มรางวัล")
        self.stack.addWidget(self.tabs)

        # Page 1: หน้าจอแจ้งเตือนบล็อคเมื่อยังไม่ได้ใส่ Widget Giveaway บน Overlay
        self.blocker_widget = self._build_blocker_widget()
        self.stack.addWidget(self.blocker_widget)

        root_layout.addWidget(self.stack, 1)

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
        def _install_from_giveaway():
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
        btn_install_dock.clicked.connect(_install_from_giveaway)
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
        def _copy_dock_url_giveaway():
            import obs_dock_installer as odi
            from PySide6.QtWidgets import QApplication
            dock_url = odi.get_dock_url()
            if hasattr(self, 'parent_app') and hasattr(self.parent_app, 'composer_server') and self.parent_app.composer_server:
                dock_url = f"http://localhost:{getattr(self.parent_app.composer_server, 'port', 8801)}/dock"
            QApplication.clipboard().setText(dock_url)
            btn_copy_dock.setText("✓ คัดลอกแล้ว")
            QTimer.singleShot(1500, lambda: btn_copy_dock.setText("📋 คัดลอกลิงก์"))
        db_layout.addWidget(btn_copy_dock)

        db_layout.addStretch()

        from PySide6.QtWidgets import QSizeGrip
        self.sizegrip = QSizeGrip(self)
        db_layout.addWidget(self.sizegrip, 0, Qt.AlignVCenter | Qt.AlignRight)

        root_layout.addWidget(dock_bar)

        # ป้องกันไม่ให้การเลื่อน Scroll เมาส์ไปเผลอปรับค่า Slider / Dropdown
        self._disable_scroll_on_inputs()

    def _disable_scroll_on_inputs(self):
        """ปิดการตอบสนอง Wheel Event ของ Dropdown, Slider, Spinbox ทั้งหมดเพื่อให้ Scroll หน้าได้อย่างราบรื่น"""
        for cls in (QComboBox, QSlider, QSpinBox):
            for widget in self.findChildren(cls):
                widget.wheelEvent = lambda event: event.ignore()

    def _build_blocker_widget(self) -> QWidget:
        """สร้างหน้าต่างบล็อคเมื่อยังไม่มี Widget Giveaway บน Overlay"""
        blocker = QWidget()
        blocker.setStyleSheet("background: transparent;")
        v = QVBoxLayout(blocker)
        v.setContentsMargins(24, 30, 24, 30)
        v.setSpacing(16)
        v.addStretch()

        icon_lbl = QLabel("⚠️")
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet("font-size: 52px; background: transparent; border: none;")
        v.addWidget(icon_lbl)

        title_lbl = QLabel("ยังไม่ได้เพิ่ม Widget Giveaway บนหน้าจอ Overlay")
        title_lbl.setAlignment(Qt.AlignCenter)
        title_lbl.setStyleSheet("font-size: 17px; font-weight: 800; color: #f59e0b; background: transparent; border: none;")
        v.addWidget(title_lbl)

        desc_lbl = QLabel(
            "เพื่อให้ระบบสามารถแสดงผลแบนเนอร์และโค้ดกิจกรรมบนหน้าจอ OBS ได้อย่างถูกต้อง\n"
            "กรุณาเปิด Overlay Composer แล้วกดปุ่ม \"+ Giveaway\" เพื่อวาง Widget ลงบนหน้าจอก่อนครับ"
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
        s2 = QLabel("2️⃣  กดปุ่ม <b>\"+ Giveaway\"</b> เพื่อวาง Widget บนหน้าจอ (ไม่ต้องจัดขนาด เพราะระบบจะฟิกเต็มจอให้อัตโนมัติ)")
        s3 = QLabel("3️⃣  เมื่อเพิ่มเรียบร้อยแล้ว หน้านี้จะ<b>ปลดล็อคให้อัตโนมัติทันที</b> เพื่อให้คุณเริ่มตั้งค่ากิจกรรมได้")
        for s in (s1, s2, s3):
            s.setWordWrap(True)
            s.setStyleSheet("color: #cbd5e1; font-size: 13px; line-height: 1.5; background: transparent; border: none;")
            sv.addWidget(s)
        v.addWidget(step_card)

        btn_vbox = QVBoxLayout()
        btn_vbox.setSpacing(8)
        btn_vbox.setAlignment(Qt.AlignCenter)

        btn_open = QPushButton("🌐 เปิด Overlay Composer เพื่อเพิ่ม Widget")
        btn_open.setStyleSheet(
            "background-color: #2563eb; color: #ffffff; border: none; border-radius: 6px; "
            "padding: 10px 20px; font-weight: 800; font-size: 13.5px;"
        )
        btn_open.setCursor(Qt.PointingHandCursor)
        btn_open.clicked.connect(self._on_open_composer_clicked)
        btn_vbox.addWidget(btn_open)

        btn_check = QPushButton("🔄 ตรวจสอบอีกครั้ง")
        btn_check.setProperty("variant", "ghost")
        btn_check.setStyleSheet(
            "background-color: #162032; border: 1px solid #283548; color: #cbd5e1; "
            "border-radius: 6px; padding: 8px 16px; font-weight: 600; font-size: 12.5px;"
        )
        btn_check.setCursor(Qt.PointingHandCursor)
        btn_check.clicked.connect(self._check_widget_status)
        btn_vbox.addWidget(btn_check)

        v.addLayout(btn_vbox)
        v.addStretch()
        return blocker

    def _is_widget_installed(self) -> bool:
        """เช็คว่ามี Widget Giveaway ใน Overlay หรือยัง"""
        try:
            app_inst = None
            if hasattr(self, "service") and self.service:
                if callable(getattr(self.service, "parent", None)):
                    app_inst = self.service.parent()
                elif hasattr(self.service, "parent"):
                    app_inst = self.service.parent
            if not app_inst and hasattr(self, "parent_app"):
                app_inst = self.parent_app
            if not app_inst and callable(getattr(self, "parent", None)):
                app_inst = self.parent()

            if app_inst and hasattr(app_inst, "_giveaway_widget_exists"):
                return bool(app_inst._giveaway_widget_exists())
            if app_inst and hasattr(app_inst, "settings"):
                widgets = list(getattr(app_inst.settings, "composer_widgets", []) or [])
                return any(isinstance(w, dict) and w.get("type") == "giveaway" and w.get("enabled", True) for w in widgets)
        except Exception:
            pass
        return False

    def _check_widget_status(self):
        """ตรวจเช็คสถานะการติดตั้ง Widget และสลับหน้าแสดงผลอัตโนมัติ"""
        installed = self._is_widget_installed()
        if installed:
            if self.stack.currentIndex() != 0:
                self.stack.setCurrentIndex(0)
                self.lbl_status_badge.setText("พร้อมเริ่มกิจกรรม")
                self.lbl_status_badge.setStyleSheet(
                    "background: #162032; color: #94a3b8; border-radius: 4px; "
                    "padding: 4px 10px; font-size: 11px; font-weight: bold;"
                )
        else:
            if self.stack.currentIndex() != 1:
                self.stack.setCurrentIndex(1)
                self.lbl_status_badge.setText("⚠️ ยังไม่มี Widget บนจอ")
                self.lbl_status_badge.setStyleSheet(
                    "background: #451a03; color: #fbbf24; border-radius: 4px; "
                    "padding: 4px 10px; font-size: 11px; font-weight: bold;"
                )

    def _on_open_composer_clicked(self):
        """เปิด Overlay Composer บนเบราว์เซอร์เพื่อให้ผู้ใช้เพิ่ม Widget"""
        try:
            app_inst = None
            if hasattr(self, "service") and self.service:
                if callable(getattr(self.service, "parent", None)):
                    app_inst = self.service.parent()
                elif hasattr(self.service, "parent"):
                    app_inst = self.service.parent
            if not app_inst and hasattr(self, "parent_app"):
                app_inst = self.parent_app
            if not app_inst and callable(getattr(self, "parent", None)):
                app_inst = self.parent()

            if app_inst and hasattr(app_inst, "_open_composer"):
                app_inst._open_composer()
                return
        except Exception:
            pass
        import webbrowser
        port = 8801
        try:
            if app_inst and hasattr(app_inst, "composer_server") and app_inst.composer_server:
                port = getattr(app_inst.composer_server, "port", 8801)
            elif app_inst and hasattr(app_inst, "settings"):
                port = getattr(app_inst.settings, "composer_port", 8801)
        except Exception:
            pass
        webbrowser.open(f"http://localhost:{port}/editor")

    # ───────────────────────────────────────────────────────────────────
    # UI Section Separators (เส้นแบ่งและหัวข้อหมวดหมู่สไตล์สตูดิโอมืออาชีพ)
    # ───────────────────────────────────────────────────────────────────
    def _create_section_card(self, title: str, icon: str = "", accent_color: str = "#38bdf8", extra_widget: Optional[QWidget] = None):
        """สร้างการ์ดกลุ่มการตั้งค่าระดับเดียว (Single-layer Card) พร้อมหัวข้อ เส้นตัดคั่น และสีสันตามมาตรฐาน UI สตูดิโอ"""
        card = QFrame()
        card.setObjectName("SectionCard")
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

        # Header Row
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

        # เส้นแบ่งตัดคั่นใต้หัวข้อ สวยงาม ไม่รกตา
        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background-color: #1e293b; border: none;")
        v.addWidget(divider)

        return card, v

    # ═══════════════════════════════════════════════════════════════════
    # TAB 1: 📍 เช็คชื่อ & ตั้งค่า (Seamless Flow with Divided Sections)
    # ═══════════════════════════════════════════════════════════════════
    def _build_tab_checkpoint(self):
        tab_layout = QVBoxLayout(self.tab_checkpoint)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.setSpacing(0)

        # Scroll Area สำหรับให้เลื่อนดูการตั้งค่าได้อย่างสบายตา ไม่มีกรอบสี่เหลี่ยมซ้อน
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(6, 10, 14, 12)
        layout.setSpacing(12)
        scroll.setWidget(content_widget)
        tab_layout.addWidget(scroll, 1)

        # ── Card 1: รูปแบบกิจกรรม ──
        card_mode, layout_mode = self._create_section_card("รูปแบบกิจกรรม", "🎯", accent_color="#38bdf8")

        mode_row = QHBoxLayout()
        mode_row.setSpacing(10)
        self.btn_mode_single = QPushButton("🔘 🎯 ด่านเดียว (รอบเดียว)")
        self.btn_mode_single.setCheckable(True)
        self.btn_mode_single.setProperty("variant", "mode_toggle")
        self.btn_mode_single.setCursor(Qt.PointingHandCursor)
        self.btn_mode_single.clicked.connect(lambda: self._set_mode("single"))

        self.btn_mode_multi = QPushButton("⚪ 📍 หลายด่านสะสมแต้ม")
        self.btn_mode_multi.setCheckable(True)
        self.btn_mode_multi.setChecked(True)
        self.btn_mode_multi.setProperty("variant", "mode_toggle")
        self.btn_mode_multi.setCursor(Qt.PointingHandCursor)
        self.btn_mode_multi.clicked.connect(lambda: self._set_mode("multi"))

        mode_row.addWidget(self.btn_mode_single, 1)
        mode_row.addWidget(self.btn_mode_multi, 1)
        layout_mode.addLayout(mode_row)
        layout.addWidget(card_mode)

        # ── Card 2: จัดการด่านและคำสั่งที่ต้องพิมพ์ ──
        self.lbl_cp_summary = QLabel("รอบเดียว (1 ด่าน)")
        self.lbl_cp_summary.setStyleSheet("color: #94a3b8; font-size: 11.5px; font-weight: 600; background: transparent;")
        card_cp, layout_cp = self._create_section_card("ด่านและคำสั่งที่เปิดใช้งาน", "📍", accent_color="#818cf8", extra_widget=self.lbl_cp_summary)

        cp_sel_row = QHBoxLayout()
        cp_sel_row.setSpacing(8)
        self.lbl_sel_cp = QLabel("รอบที่เปิด:")
        self.lbl_sel_cp.setStyleSheet("color: #cbd5e1; font-weight: 600; min-width: 70px;")
        cp_sel_row.addWidget(self.lbl_sel_cp)

        self.cmb_active_cp = QComboBox()
        self.cmb_active_cp.setStyleSheet("""
            QComboBox {
                background-color: #131d31;
                border: 1px solid #334155;
                border-radius: 6px;
                color: #f8fafc;
                padding: 6px 10px;
                font-size: 13px;
                font-weight: 600;
            }
            QComboBox:hover {
                border-color: #475569;
            }
            QComboBox:focus {
                border-color: #38bdf8;
            }
        """)
        self.cmb_active_cp.currentIndexChanged.connect(self._on_active_cp_changed)
        cp_sel_row.addWidget(self.cmb_active_cp, 1)
        layout_cp.addLayout(cp_sel_row)

        cp_btn_row = QHBoxLayout()
        cp_btn_row.setSpacing(8)

        self.btn_rename_cp = QPushButton("✏️ แก้ชื่อรอบ")
        self.btn_rename_cp.setStyleSheet("""
            QPushButton {
                background-color: #17243c;
                border: 1px solid #3b82f6;
                border-radius: 6px;
                color: #60a5fa;
                font-weight: 700;
                font-size: 11.5px;
                padding: 5px 10px;
            }
            QPushButton:hover {
                background-color: #1e3a5f;
                border-color: #60a5fa;
                color: #93c5fd;
            }
            QPushButton:pressed {
                background-color: #1d4ed8;
            }
        """)
        self.btn_rename_cp.setToolTip("เปลี่ยนชื่อรอบกิจกรรมที่เลือกอยู่ (สามารถแก้ไขได้ทุกรอบรวมถึงรอบแรก)")
        self.btn_rename_cp.clicked.connect(self._on_rename_checkpoint_clicked)
        cp_btn_row.addWidget(self.btn_rename_cp)

        self.btn_add_cp = QPushButton("➕ เพิ่มรอบ")
        self.btn_add_cp.setStyleSheet("""
            QPushButton {
                background-color: #0c2135;
                border: 1px solid #0284c7;
                border-radius: 6px;
                color: #38bdf8;
                font-weight: 700;
                font-size: 11.5px;
                padding: 5px 10px;
            }
            QPushButton:hover {
                background-color: #0e3052;
                border-color: #38bdf8;
                color: #e0f2fe;
            }
            QPushButton:pressed {
                background-color: #0369a1;
            }
        """)
        self.btn_add_cp.setToolTip("กดเพื่อเพิ่มรอบใหม่และกำหนดชื่อรอบ")
        self.btn_add_cp.clicked.connect(self._on_add_checkpoint_clicked)
        cp_btn_row.addWidget(self.btn_add_cp)

        self.btn_remove_cp = QPushButton("🗑️ ลบรอบ")
        self.btn_remove_cp.setStyleSheet("""
            QPushButton {
                background-color: #271216;
                border: 1px solid #7f1d1d;
                border-radius: 6px;
                color: #f87171;
                font-weight: 700;
                font-size: 11.5px;
                padding: 5px 10px;
            }
            QPushButton:hover {
                background-color: #3b181e;
                border-color: #ef4444;
                color: #fecaca;
            }
            QPushButton:pressed {
                background-color: #991b1b;
            }
        """)
        self.btn_remove_cp.setToolTip("ลบรอบล่าสุด")
        self.btn_remove_cp.clicked.connect(self._on_remove_checkpoint_clicked)
        cp_btn_row.addWidget(self.btn_remove_cp)
        cp_btn_row.addStretch()

        layout_cp.addLayout(cp_btn_row)

        code_input_row = QHBoxLayout()
        code_input_row.setSpacing(8)
        lbl_code = QLabel("โค้ดที่ให้พิมพ์:")
        lbl_code.setStyleSheet("color: #cbd5e1; font-weight: 600; min-width: 80px;")
        code_input_row.addWidget(lbl_code)

        self.inp_code = QLineEdit("!join")
        self.inp_code.setPlaceholderText("ระบุคำสั่ง เช่น !join, 789, LUCKY")
        self.inp_code.setStyleSheet("""
            QLineEdit {
                background-color: #131d31;
                border: 1.5px solid #3b82f6;
                border-radius: 6px;
                color: #ffffff;
                font-size: 14.5px;
                font-weight: 700;
                padding: 7px 12px;
                selection-background-color: #0284c7;
            }
            QLineEdit:hover {
                border-color: #60a5fa;
                background-color: #162238;
            }
            QLineEdit:focus {
                border: 2px solid #38bdf8;
                background-color: #1a2744;
                color: #ffffff;
            }
        """)
        self.inp_code.textChanged.connect(self._on_code_text_edited)
        code_input_row.addWidget(self.inp_code, 1)

        btn_rand = QPushButton("🎲 สุ่มคำสั่ง")
        btn_rand.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 6px;
                color: #cbd5e1;
                font-weight: 600;
                font-size: 12.5px;
                padding: 7px 13px;
            }
            QPushButton:hover {
                background-color: #283548;
                border-color: #38bdf8;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #0f172a;
            }
        """)
        btn_rand.clicked.connect(self._generate_random_code)
        code_input_row.addWidget(btn_rand)
        layout_cp.addLayout(code_input_row)
        layout.addWidget(card_cp)

        # ── Card 3: ระยะเวลาเปิดรับ ──
        card_time, layout_time = self._create_section_card("ระยะเวลาเปิดรับข้อความ", "⏱️", accent_color="#fbbf24")

        radio_row = QHBoxLayout()
        self.rad_duration_timer = QRadioButton("จับเวลาถอยหลัง")
        self.rad_duration_timer.setChecked(True)
        self.rad_duration_manual = QRadioButton("ไม่มีกำหนด (เปิดค้างจนกว่าจะกดปิดเอง)")
        self.rad_duration_timer.toggled.connect(self._on_duration_mode_toggled)

        radio_row.addWidget(self.rad_duration_timer)
        radio_row.addWidget(self.rad_duration_manual)
        radio_row.addStretch()
        layout_time.addLayout(radio_row)

        # แถบควบคุมตัวเลขเวลา
        self.timer_controls_widget = QWidget()
        t_ctrl_layout = QHBoxLayout(self.timer_controls_widget)
        t_ctrl_layout.setContentsMargins(0, 0, 0, 0)
        t_ctrl_layout.setSpacing(6)

        self.spin_minutes = DurationStepper(default_secs=60)
        self.spin_minutes.valueChanged.connect(self._on_stepper_duration_changed)

        self.btn_preset_30s = QPushButton("30 วิ")
        self.btn_preset_1m = QPushButton("1 นาที")
        self.btn_preset_2m = QPushButton("2 นาที")
        self.btn_preset_5m = QPushButton("5 นาที")
        self.btn_preset_10m = QPushButton("10 นาที")

        self._preset_time_buttons = [
            (30, self.btn_preset_30s),
            (60, self.btn_preset_1m),
            (120, self.btn_preset_2m),
            (300, self.btn_preset_5m),
            (600, self.btn_preset_10m),
        ]

        self.btn_preset_30s.clicked.connect(lambda: self._set_quick_seconds(30))
        self.btn_preset_1m.clicked.connect(lambda: self._set_quick_preset(60))
        self.btn_preset_2m.clicked.connect(lambda: self._set_quick_preset(120))
        self.btn_preset_5m.clicked.connect(lambda: self._set_quick_preset(300))
        self.btn_preset_10m.clicked.connect(lambda: self._set_quick_preset(600))

        t_ctrl_layout.addWidget(self.spin_minutes)
        for _, btn in self._preset_time_buttons:
            btn.setCursor(Qt.PointingHandCursor)
            t_ctrl_layout.addWidget(btn)
        t_ctrl_layout.addStretch()
        layout_time.addWidget(self.timer_controls_widget)
        self._update_preset_time_buttons(60)
        layout.addWidget(card_time)

        # ── Card 4: รูปแบบการแสดงผลบนจอ OBS (Overlay) ──
        self._demo_cp_active = False
        self.btn_preview_obs = QPushButton("👁️ Demo เปิดรับโค้ด")
        self.btn_preview_obs.setStyleSheet(STYLE_PREVIEW_NORMAL)
        self.btn_preview_obs.setToolTip("คลิกเพื่อเปิด/ปิดแสดงตัวอย่างการ์ดเปิดรับโค้ดบน OBS Overlay ค้างไว้สำหรับปรับตำแหน่งและขนาด")
        self.btn_preview_obs.clicked.connect(self._toggle_checkpoint_demo)

        card_overlay, layout_overlay = self._create_section_card("การแสดงผลบนจอ OBS (OVERLAY)", "📺", accent_color="#f472b6", extra_widget=self.btn_preview_obs)

        disp_mode_row = QHBoxLayout()
        disp_mode_row.setSpacing(8)
        self.btn_display_banner = QPushButton("🔘 📝 การ์ดข้อความ")
        self.btn_display_banner.setCheckable(True)
        self.btn_display_banner.setChecked(True)
        self.btn_display_banner.setProperty("variant", "display_toggle")
        self.btn_display_banner.setCursor(Qt.PointingHandCursor)
        self.btn_display_banner.setToolTip("แสดงการ์ดข้อความโค้ดและเวลานับถอยหลังที่มุมบนของจอ")
        self.btn_display_banner.clicked.connect(lambda: self._set_display_mode("banner"))

        self.btn_display_image = QPushButton("⚪ 🖼️ ภาพแบนเนอร์")
        self.btn_display_image.setCheckable(True)
        self.btn_display_image.setProperty("variant", "display_toggle")
        self.btn_display_image.setCursor(Qt.PointingHandCursor)
        self.btn_display_image.setToolTip("แสดงรูปภาพแบนเนอร์ที่คุณเลือกเอง พร้อมกรอบนับเวลา")
        self.btn_display_image.clicked.connect(lambda: self._set_display_mode("image"))

        self.btn_display_none = QPushButton("⚪ 🔇 ซ่อนบนจอ")
        self.btn_display_none.setCheckable(True)
        self.btn_display_none.setProperty("variant", "display_toggle")
        self.btn_display_none.setCursor(Qt.PointingHandCursor)
        self.btn_display_none.setToolTip("ไม่แสดงกล่องข้อความใดๆ บนจอ OBS ขณะเปิดรับโค้ด (รับข้อมูลเงียบๆ ไม่รกจอเกม) และจะแสดง Overlay เฉพาะตอนหมุนสุ่มรางวัลเท่านั้น")
        self.btn_display_none.clicked.connect(lambda: self._set_display_mode("none"))

        disp_mode_row.addWidget(self.btn_display_banner, 1)
        disp_mode_row.addWidget(self.btn_display_image, 1)
        disp_mode_row.addWidget(self.btn_display_none, 1)
        layout_overlay.addLayout(disp_mode_row)

        # คอนเทนเนอร์การตั้งค่ารูปภาพแบนเนอร์ (เฉพาะตอนเลือกโหมดภาพแบนเนอร์)
        self.image_settings_widget = QWidget()
        self.image_settings_widget.setVisible(False)
        self.image_settings_widget.setStyleSheet("background: #080d19; border: 1px solid #1a273b; border-radius: 6px;")
        img_vlayout = QVBoxLayout(self.image_settings_widget)
        img_vlayout.setContentsMargins(12, 10, 12, 10)
        img_vlayout.setSpacing(8)

        # 1. แถบเลือกไฟล์รูปภาพ
        img_file_row = QHBoxLayout()
        img_file_row.setSpacing(8)
        btn_browse_img = QPushButton("📁 เลือกรูปภาพ...")
        btn_browse_img.setProperty("variant", "ghost")
        btn_browse_img.setStyleSheet("font-size: 12px; padding: 5px 12px; color: #f8fafc;")
        btn_browse_img.clicked.connect(self._on_browse_image)
        img_file_row.addWidget(btn_browse_img)

        self.lbl_image_path = QLabel("ยังไม่ได้เลือกรูปภาพ (รองรับ PNG, JPG, WebP, GIF)")
        self.lbl_image_path.setStyleSheet("color: #94a3b8; font-size: 12px;")
        img_file_row.addWidget(self.lbl_image_path, 1)

        self.btn_clear_img = QPushButton("✕")
        self.btn_clear_img.setProperty("variant", "ghost")
        self.btn_clear_img.setFixedSize(28, 28)
        self.btn_clear_img.setStyleSheet("font-size: 13px; font-weight: bold; color: #94a3b8; padding: 0;")
        self.btn_clear_img.setToolTip("ยกเลิกภาพ")
        self.btn_clear_img.clicked.connect(self._on_clear_image)
        img_file_row.addWidget(self.btn_clear_img)
        img_vlayout.addLayout(img_file_row)

        img_opts_row = QHBoxLayout()
        self.chk_show_stats = QCheckBox("แสดงแถบสถิติด้านล่างภาพ (เวลา / ยอดคน)")
        self.chk_show_stats.setChecked(True)
        self.chk_show_stats.toggled.connect(self._on_overlay_settings_changed)
        img_opts_row.addWidget(self.chk_show_stats)
        img_opts_row.addStretch()
        img_vlayout.addLayout(img_opts_row)

        layout_overlay.addWidget(self.image_settings_widget)

        # คอนเทนเนอร์การจัดวางตำแหน่ง ขนาด และอนิเมชั่น (ใช้ร่วมกันทั้งการ์ดข้อความและภาพแบนเนอร์)
        overlay_ctrl_widget = QWidget()
        overlay_ctrl_widget.setStyleSheet("background: #080d19; border: 1px solid #1a273b; border-radius: 6px;")
        ctrl_vlayout = QVBoxLayout(overlay_ctrl_widget)
        ctrl_vlayout.setContentsMargins(12, 10, 12, 10)
        ctrl_vlayout.setSpacing(8)

        # ตำแหน่งบนจอ
        pos_row = QHBoxLayout()
        pos_row.setSpacing(8)
        lbl_pos = QLabel("ตำแหน่งจอ:")
        lbl_pos.setStyleSheet("color: #cbd5e1; font-weight: 600; min-width: 70px;")
        pos_row.addWidget(lbl_pos)

        self.cmb_position = QComboBox()
        self.cmb_position.addItem("ขวาบน (Top-Right)", "top-right")
        self.cmb_position.addItem("ขวา (Right)", "right")
        self.cmb_position.addItem("ขวาล่าง (Bottom-Right)", "bottom-right")
        self.cmb_position.addItem("ซ้ายบน (Top-Left)", "top-left")
        self.cmb_position.addItem("ซ้าย (Left)", "left")
        self.cmb_position.addItem("ซ้ายล่าง (Bottom-Left)", "bottom-left")
        self.cmb_position.addItem("กึ่งกลางบน (Top)", "top")
        self.cmb_position.addItem("กึ่งกลางล่าง (Bottom)", "bottom")
        self.cmb_position.addItem("กึ่งกลางจอ (Center)", "center")
        self.cmb_position.currentIndexChanged.connect(self._on_overlay_settings_changed)
        pos_row.addWidget(self.cmb_position, 1)
        ctrl_vlayout.addLayout(pos_row)

        # สเกลขนาด
        scale_row = QHBoxLayout()
        scale_row.setSpacing(8)
        lbl_scale = QLabel("ขนาด:")
        lbl_scale.setStyleSheet("color: #cbd5e1; font-weight: 600; min-width: 70px;")
        scale_row.addWidget(lbl_scale)

        self.slider_scale = QSlider(Qt.Horizontal)
        self.slider_scale.setRange(50, 180)
        self.slider_scale.setValue(100)
        self.slider_scale.valueChanged.connect(self._on_scale_slider_changed)
        scale_row.addWidget(self.slider_scale, 1)

        self.lbl_scale_val = QLabel("100%")
        self.lbl_scale_val.setStyleSheet("color: #38bdf8; font-weight: bold; min-width: 42px;")
        scale_row.addWidget(self.lbl_scale_val)
        ctrl_vlayout.addLayout(scale_row)

        # Fine-tune เลื่อนตำแหน่งแกน X และ Y
        offset_row = QHBoxLayout()
        offset_row.setSpacing(8)

        lbl_ox = QLabel("เลื่อน X:")
        lbl_ox.setStyleSheet("color: #94a3b8; font-size: 12px; min-width: 45px;")
        offset_row.addWidget(lbl_ox)

        self.slider_offset_x = QSlider(Qt.Horizontal)
        self.slider_offset_x.setRange(-400, 400)
        self.slider_offset_x.setValue(0)
        self.slider_offset_x.valueChanged.connect(self._on_offset_x_changed)
        offset_row.addWidget(self.slider_offset_x, 1)

        self.lbl_offset_x_val = QLabel("0px")
        self.lbl_offset_x_val.setStyleSheet("color: #cbd5e1; font-size: 11.5px; min-width: 38px;")
        offset_row.addWidget(self.lbl_offset_x_val)

        lbl_oy = QLabel("Y:")
        lbl_oy.setStyleSheet("color: #94a3b8; font-size: 12px; margin-left: 4px;")
        offset_row.addWidget(lbl_oy)

        self.slider_offset_y = QSlider(Qt.Horizontal)
        self.slider_offset_y.setRange(-400, 400)
        self.slider_offset_y.setValue(0)
        self.slider_offset_y.valueChanged.connect(self._on_offset_y_changed)
        offset_row.addWidget(self.slider_offset_y, 1)

        self.lbl_offset_y_val = QLabel("0px")
        self.lbl_offset_y_val.setStyleSheet("color: #cbd5e1; font-size: 11.5px; min-width: 38px;")
        offset_row.addWidget(self.lbl_offset_y_val)
        ctrl_vlayout.addLayout(offset_row)

        # อนิเมชั่น เข้า
        anim_in_row = QHBoxLayout()
        anim_in_row.setSpacing(8)
        lbl_ai = QLabel("อนิเมชั่นเข้า:")
        lbl_ai.setStyleSheet("color: #cbd5e1; font-weight: 600; min-width: 70px;")
        anim_in_row.addWidget(lbl_ai)

        self.cmb_anim_in = QComboBox()
        self.cmb_anim_in.addItem("อัตโนมัติตามตำแหน่ง (Auto / Slide)", "slide")
        self.cmb_anim_in.addItem("บินมาจากด้านบน (From Top)", "from-top")
        self.cmb_anim_in.addItem("บินมาจากด้านล่าง (From Bottom)", "from-bottom")
        self.cmb_anim_in.addItem("บินมาจากทางซ้าย (From Left)", "from-left")
        self.cmb_anim_in.addItem("บินมาจากทางขวา (From Right)", "from-right")
        self.cmb_anim_in.addItem("บินมาจากมุมซ้ายบน (From Top-Left)", "from-top-left")
        self.cmb_anim_in.addItem("บินมาจากมุมขวาบน (From Top-Right)", "from-top-right")
        self.cmb_anim_in.addItem("บินมาจากมุมซ้ายล่าง (From Bottom-Left)", "from-bottom-left")
        self.cmb_anim_in.addItem("บินมาจากมุมขวาล่าง (From Bottom-Right)", "from-bottom-right")
        self.cmb_anim_in.addItem("ค่อยๆ ปรากฏ (Fade In)", "fade")
        self.cmb_anim_in.addItem("ซูมขยายเข้า (Zoom In)", "zoom")
        self.cmb_anim_in.addItem("เด้งดึ๋งเข้า (Bounce In)", "bounce")
        self.cmb_anim_in.currentIndexChanged.connect(self._on_overlay_settings_changed)
        anim_in_row.addWidget(self.cmb_anim_in, 1)
        ctrl_vlayout.addLayout(anim_in_row)

        # อนิเมชั่น ออก
        anim_out_row = QHBoxLayout()
        anim_out_row.setSpacing(8)
        lbl_ao = QLabel("อนิเมชั่นออก:")
        lbl_ao.setStyleSheet("color: #cbd5e1; font-weight: 600; min-width: 70px;")
        anim_out_row.addWidget(lbl_ao)

        self.cmb_anim_out = QComboBox()
        self.cmb_anim_out.addItem("อัตโนมัติตามตำแหน่ง (Auto / Slide)", "slide")
        self.cmb_anim_out.addItem("ลอยออกไปด้านบน (To Top)", "from-top")
        self.cmb_anim_out.addItem("ลอยออกไปด้านล่าง (To Bottom)", "from-bottom")
        self.cmb_anim_out.addItem("ลอยออกไปทางซ้าย (To Left)", "from-left")
        self.cmb_anim_out.addItem("ลอยออกไปทางขวา (To Right)", "from-right")
        self.cmb_anim_out.addItem("ลอยออกไปมุมซ้ายบน (To Top-Left)", "from-top-left")
        self.cmb_anim_out.addItem("ลอยออกไปมุมขวาบน (To Top-Right)", "from-top-right")
        self.cmb_anim_out.addItem("ลอยออกไปมุมซ้ายล่าง (To Bottom-Left)", "from-bottom-left")
        self.cmb_anim_out.addItem("ลอยออกไปมุมขวาล่าง (To Bottom-Right)", "from-bottom-right")
        self.cmb_anim_out.addItem("ค่อยๆ จางหาย (Fade Out)", "fade")
        self.cmb_anim_out.addItem("ซูมเล็กลง (Zoom Out)", "zoom")
        self.cmb_anim_out.currentIndexChanged.connect(self._on_overlay_settings_changed)
        anim_out_row.addWidget(self.cmb_anim_out, 1)
        ctrl_vlayout.addLayout(anim_out_row)

        layout_overlay.addWidget(overlay_ctrl_widget)

        # ตัวเลือกทั่วไปของ Overlay (หลอดนับถอยหลัง, เส้นขอบ, ธีมสี, ป็อปอัป)
        common_opts_layout = QVBoxLayout()
        common_opts_layout.setContentsMargins(0, 4, 0, 0)
        common_opts_layout.setSpacing(6)

        self.chk_show_progress_bar = QCheckBox("แสดงหลอดนับถอยหลัง (Progress Bar)")
        self.chk_show_progress_bar.setChecked(True)
        self.chk_show_progress_bar.toggled.connect(self._on_overlay_settings_changed)
        common_opts_layout.addWidget(self.chk_show_progress_bar)

        self.chk_border_countdown = QCheckBox("แสดงเส้นขอบนับถอยหลังรอบการ์ด/ภาพ")
        self.chk_border_countdown.setChecked(True)
        self.chk_border_countdown.toggled.connect(self._on_overlay_settings_changed)
        common_opts_layout.addWidget(self.chk_border_countdown)

        theme_row = QHBoxLayout()
        theme_row.setSpacing(8)
        lbl_theme = QLabel("ธีมสีเส้นขอบ & หลอดเวลา:")
        lbl_theme.setStyleSheet("color: #cbd5e1; font-weight: 600; font-size: 12px;")
        theme_row.addWidget(lbl_theme)

        self.cmb_border_theme = QComboBox()
        self.cmb_border_theme.addItem("สายรุ้งนีออน (Rainbow)", "rainbow")
        self.cmb_border_theme.addItem("ไซเบอร์พังก์ (Cyberpunk)", "cyberpunk")
        self.cmb_border_theme.addItem("เปลวทองอร่าม (Flame Gold)", "gold")
        self.cmb_border_theme.addItem("พายุน้ำแข็ง (Ice Blizzard)", "ice")
        self.cmb_border_theme.addItem("ซากุระนีออน (Sakura Neon)", "sakura")
        self.cmb_border_theme.addItem("มรกตสว่าง (Emerald)", "emerald")
        self.cmb_border_theme.addItem("ทับทิมเรืองรอง (Ruby Glow)", "ruby")
        self.cmb_border_theme.addItem("นีออนไวโอเล็ต (Neon Violet)", "violet")
        self.cmb_border_theme.addItem("อิเล็กทริกบลู (Electric Blue)", "blue")
        self.cmb_border_theme.currentIndexChanged.connect(self._on_overlay_settings_changed)
        theme_row.addWidget(self.cmb_border_theme, 1)
        common_opts_layout.addLayout(theme_row)

        self.chk_show_toast = QCheckBox("แสดงป็อปอัปแจ้งเตือนบนจอเมื่อมีคนพิมพ์เข้าร่วม")
        self.chk_show_toast.setChecked(True)
        self.chk_show_toast.toggled.connect(self._on_overlay_settings_changed)
        common_opts_layout.addWidget(self.chk_show_toast)

        lbl_toast_hint = QLabel("💡 ติ๊กออกสำหรับงานทางการ/อีสปอร์ต เพื่อเก็บข้อมูลเงียบๆ ไม่ให้เด้งรกจอพรีเซนต์")
        lbl_toast_hint.setProperty("role", "hint")
        lbl_toast_hint.setStyleSheet("color: #64748b; font-size: 11px; margin-left: 20px;")
        common_opts_layout.addWidget(lbl_toast_hint)
        layout_overlay.addLayout(common_opts_layout)
        layout.addWidget(card_overlay)

        # ── Card 5: แถบสถานะนับเวลา & ปุ่มเริ่ม ──
        card_status, layout_status = self._create_section_card("สถานะกิจกรรม & เปิดรับโค้ด", "🚀", accent_color="#34d399")

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.progress_bar.setFormat("เหลือเวลา: 00:00")
        layout_status.addWidget(self.progress_bar)

        self.lbl_round_stats = QLabel("ผู้เข้ารอบนี้: 0 คน (รวมสะสม: 0 คน)")
        self.lbl_round_stats.setAlignment(Qt.AlignCenter)
        self.lbl_round_stats.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 13px;")
        layout_status.addWidget(self.lbl_round_stats)

        self.btn_toggle_checkpoint = QPushButton("🚀 เริ่มเปิดรับโค้ดขึ้นจอ")
        self.btn_toggle_checkpoint.setObjectName("btn_toggle_checkpoint")
        self.btn_toggle_checkpoint.setFixedHeight(50)
        self.btn_toggle_checkpoint.setCursor(Qt.PointingHandCursor)
        self.btn_toggle_checkpoint.clicked.connect(self._on_toggle_checkpoint)
        self._update_checkpoint_button_style(False)
        layout_status.addWidget(self.btn_toggle_checkpoint)

        layout.addWidget(card_status)

        self._set_display_mode("banner")

        layout.addStretch()

    # ═══════════════════════════════════════════════════════════════════
    # TAB 2: 👥 รายชื่อผู้เข้าร่วม (Single-layer Cards with Clean Divided Sections)
    # ═══════════════════════════════════════════════════════════════════
    def _build_tab_participants(self):
        layout = QVBoxLayout(self.tab_participants)
        layout.setContentsMargins(6, 10, 8, 12)
        layout.setSpacing(12)

        # ── Card 1: สรุปสถิติ ──
        card_stats, layout_stats = self._create_section_card("สรุปยอดผู้เข้าร่วมกิจกรรม", "📊", accent_color="#38bdf8")

        self.stat_bar_widget = QWidget()
        from PySide6.QtWidgets import QGridLayout
        self.stat_bar_layout = QGridLayout(self.stat_bar_widget)
        self.stat_bar_layout.setContentsMargins(0, 0, 0, 0)
        self.stat_bar_layout.setHorizontalSpacing(14)
        self.stat_bar_layout.setVerticalSpacing(6)
        layout_stats.addWidget(self.stat_bar_widget)
        layout.addWidget(card_stats)

        # ── Card 2: ค้นหา & ตารางรายชื่อ ──
        card_list, layout_list = self._create_section_card("รายชื่อและระดับสิทธิ์", "👥", accent_color="#818cf8")

        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)
        self.inp_search = QLineEdit()
        self.inp_search.setPlaceholderText("🔍 ค้นหาชื่อคนดู...")
        self.inp_search.setStyleSheet("""
            QLineEdit {
                background-color: #131d31;
                border: 1.5px solid #283548;
                border-radius: 6px;
                color: #f8fafc;
                font-size: 13px;
                padding: 7px 11px;
            }
            QLineEdit:hover {
                border-color: #3b4d6b;
            }
            QLineEdit:focus {
                border-color: #38bdf8;
                background-color: #162238;
            }
        """)
        self.inp_search.textChanged.connect(self._refresh_participants_table)
        filter_row.addWidget(self.inp_search, 1)

        self.cmb_filter_tier = QComboBox()
        self.cmb_filter_tier.addItem("ทั้งหมด", "all")
        self.cmb_filter_tier.setStyleSheet("""
            QComboBox {
                background-color: #131d31;
                border: 1.5px solid #283548;
                border-radius: 6px;
                color: #f8fafc;
                font-size: 13px;
                padding: 7px 11px;
            }
            QComboBox:hover {
                border-color: #38bdf8;
            }
        """)
        self.cmb_filter_tier.currentIndexChanged.connect(self._refresh_participants_table)
        filter_row.addWidget(self.cmb_filter_tier)

        btn_refresh = QPushButton("🔄")
        btn_refresh.setFixedWidth(38)
        btn_refresh.setStyleSheet("""
            QPushButton {
                background-color: #162032;
                border: 1px solid #283548;
                border-radius: 6px;
                color: #cbd5e1;
                font-size: 13px;
                padding: 6px 10px;
            }
            QPushButton:hover {
                background-color: #1e293b;
                border-color: #38bdf8;
                color: #ffffff;
            }
        """)
        btn_refresh.clicked.connect(self._refresh_participants_table)
        filter_row.addWidget(btn_refresh)
        layout_list.addLayout(filter_row)

        # ตารางรายชื่อ
        self.tbl_participants = QTableWidget(0, 5)
        self.tbl_participants.setHorizontalHeaderLabels(["ชื่อผู้ชม", "แพลตฟอร์ม", "รอบที่ผ่าน", "สิทธิ์", "สถานะ"])
        self.tbl_participants.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tbl_participants.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tbl_participants.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.tbl_participants.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.tbl_participants.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.tbl_participants.verticalHeader().setVisible(False)
        self.tbl_participants.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl_participants.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl_participants.setShowGrid(False)
        self.tbl_participants.setAlternatingRowColors(True)
        layout_list.addWidget(self.tbl_participants, 1)

        # ปุ่มจัดการข้อมูลกิจกรรม (Export ด้านซ้ายล่าง / ล้างข้อมูลด้านขวาล่าง)
        btm_row = QHBoxLayout()

        btn_export = QPushButton("📥 Export CSV")
        btn_export.setProperty("variant", "ghost")
        btn_export.setStyleSheet("color: #38bdf8; border-color: #0369a1; font-weight: 700; padding: 6px 14px;")
        btn_export.clicked.connect(self._export_csv_directly)
        btm_row.addWidget(btn_export)

        btm_row.addStretch()

        btn_manage = QPushButton("🗑️ ล้างข้อมูล...")
        btn_manage.setProperty("variant", "ghost")
        btn_manage.setStyleSheet("color: #ef4444; border-color: #7f1d1d;")
        btn_manage.clicked.connect(self._open_clear_dialog)
        btm_row.addWidget(btn_manage)
        layout_list.addLayout(btm_row)

        layout.addWidget(card_list, 1)

    # ═══════════════════════════════════════════════════════════════════
    # ═══════════════════════════════════════════════════════════════════
    # TAB 3: 🎰 สุ่มรางวัล (Single-layer Cards with Clean Divided Sections)
    # ═══════════════════════════════════════════════════════════════════
    def _build_tab_draw(self):
        tab_layout = QVBoxLayout(self.tab_draw)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(6, 10, 14, 12)
        layout.setSpacing(12)
        scroll.setWidget(content_widget)
        tab_layout.addWidget(scroll, 1)

        # ── Card 1: ตั้งค่าของรางวัล & กลุ่มเป้าหมาย ──
        card_cfg, layout_cfg = self._create_section_card("ตั้งค่าของรางวัล & กลุ่มเป้าหมาย", "🎁", accent_color="#fbbf24")

        row1 = QHBoxLayout()
        lbl_grp = QLabel("กลุ่มผู้ลุ้นรางวัล:")
        lbl_grp.setStyleSheet("font-weight: 600; color: #cbd5e1; width: 100px;")
        self.cmb_draw_group = QComboBox()
        self.cmb_draw_group.setStyleSheet("""
            QComboBox {
                background-color: #131d31;
                border: 1.5px solid #283548;
                border-radius: 6px;
                color: #f8fafc;
                font-size: 13px;
                padding: 7px 11px;
            }
            QComboBox:hover {
                border-color: #fbbf24;
            }
        """)
        self.cmb_draw_group.currentIndexChanged.connect(self._update_draw_pool_info)
        row1.addWidget(lbl_grp)
        row1.addWidget(self.cmb_draw_group, 1)
        layout_cfg.addLayout(row1)

        row2 = QHBoxLayout()
        lbl_prz = QLabel("ชื่อของรางวัล:")
        lbl_prz.setStyleSheet("font-weight: 600; color: #cbd5e1; width: 100px;")
        self.inp_prize = QLineEdit("รางวัลใหญ่: บัตรกำนัล 500 บาท")
        self.inp_prize.setStyleSheet("""
            QLineEdit {
                background-color: #131d31;
                border: 1.5px solid #283548;
                border-radius: 6px;
                color: #f8fafc;
                font-size: 13px;
                padding: 7px 11px;
            }
            QLineEdit:hover {
                border-color: #3b4d6b;
            }
            QLineEdit:focus {
                border-color: #fbbf24;
                background-color: #162238;
            }
        """)
        row2.addWidget(lbl_prz)
        row2.addWidget(self.inp_prize, 1)
        layout_cfg.addLayout(row2)

        self.chk_exclude_previous = QCheckBox("☑ ไม่สุ่มผู้ที่เคยได้รับรางวัลไปแล้วซ้ำ")
        self.chk_exclude_previous.setChecked(True)
        self.chk_exclude_previous.stateChanged.connect(self._update_draw_pool_info)
        layout_cfg.addWidget(self.chk_exclude_previous)

        row_style = QHBoxLayout()
        lbl_style = QLabel("รูปแบบอนิเมชั่น:")
        lbl_style.setStyleSheet("font-weight: 600; color: #cbd5e1; width: 100px;")
        self.cmb_draw_style = QComboBox()
        self.cmb_draw_style.setStyleSheet("""
            QComboBox {
                background-color: #131d31;
                border: 1.5px solid #283548;
                border-radius: 6px;
                color: #f8fafc;
                font-size: 13px;
                padding: 7px 11px;
            }
            QComboBox:hover {
                border-color: #fbbf24;
            }
        """)
        self.cmb_draw_style.addItem("Shuffle", "slot")
        self.cmb_draw_style.addItem("Slot Machine", "slot_reel")
        self.cmb_draw_style.addItem("Gacha", "gachapon")
        cur_style_idx = self.cmb_draw_style.findData(getattr(self.service, "draw_animation_style", "gachapon"))
        if cur_style_idx >= 0:
            self.cmb_draw_style.setCurrentIndex(cur_style_idx)
        self.cmb_draw_style.currentIndexChanged.connect(self._on_draw_style_changed)
        row_style.addWidget(lbl_style)
        row_style.addWidget(self.cmb_draw_style, 1)
        layout_cfg.addLayout(row_style)

        row_theme = QHBoxLayout()
        lbl_theme = QLabel("Theme สีสัน:")
        lbl_theme.setStyleSheet("font-weight: 600; color: #cbd5e1; width: 100px;")
        self.cmb_draw_theme = QComboBox()
        self.cmb_draw_theme.setStyleSheet("""
            QComboBox {
                background-color: #131d31;
                border: 1.5px solid #283548;
                border-radius: 6px;
                color: #f8fafc;
                font-size: 13px;
                padding: 7px 11px;
            }
            QComboBox:hover {
                border-color: #38bdf8;
            }
        """)
        self.cmb_draw_theme.addItem("Flame Gold", "gold")
        self.cmb_draw_theme.addItem("Cyberpunk", "cyberpunk")
        self.cmb_draw_theme.addItem("Galactic Violet", "violet")
        self.cmb_draw_theme.addItem("Emerald Green", "emerald")
        self.cmb_draw_theme.addItem("Sakura Pink", "sakura")
        self.cmb_draw_theme.addItem("Ice Blizzard", "ice")
        self.cmb_draw_theme.addItem("Ruby Red", "ruby")
        cur_theme_idx = self.cmb_draw_theme.findData(getattr(self.service, "draw_theme", "gold"))
        if cur_theme_idx >= 0:
            self.cmb_draw_theme.setCurrentIndex(cur_theme_idx)
        self.cmb_draw_theme.currentIndexChanged.connect(self._on_draw_theme_changed)
        row_theme.addWidget(lbl_theme)
        row_theme.addWidget(self.cmb_draw_theme, 1)
        layout_cfg.addLayout(row_theme)

        row_autohide = QHBoxLayout()
        lbl_autohide = QLabel("ซ่อนผลรางวัลบนจอ:")
        lbl_autohide.setStyleSheet("font-weight: 600; color: #cbd5e1; width: 100px;")
        self.cmb_draw_autohide = QComboBox()
        self.cmb_draw_autohide.setStyleSheet("""
            QComboBox {
                background-color: #131d31;
                border: 1.5px solid #283548;
                border-radius: 6px;
                color: #f8fafc;
                font-size: 13px;
                padding: 7px 11px;
            }
            QComboBox:hover {
                border-color: #38bdf8;
            }
        """)
        self.cmb_draw_autohide.addItem("10 วินาที", 10)
        self.cmb_draw_autohide.addItem("15 วินาที (แนะนำ)", 15)
        self.cmb_draw_autohide.addItem("20 วินาที", 20)
        self.cmb_draw_autohide.addItem("30 วินาที", 30)
        self.cmb_draw_autohide.addItem("ไม่ซ่อนอัตโนมัติ (ค้างจนกว่าจะกดใหม่)", 0)
        cur_ah = getattr(self.service, "draw_autohide_sec", 15)
        ah_idx = self.cmb_draw_autohide.findData(cur_ah)
        if ah_idx >= 0:
            self.cmb_draw_autohide.setCurrentIndex(ah_idx)
        self.cmb_draw_autohide.currentIndexChanged.connect(self._on_draw_autohide_changed)
        self.cmb_draw_autohide.setToolTip("ตั้งเวลาให้ Overlay รางวัลบนจอ OBS ค่อยๆ จางหายไปอัตโนมัติ\n(ข้อมูลและทำเนียบผู้ชนะในโปรแกรมจะยังคงอยู่ครบถ้วนตลอดเวลา)")
        row_autohide.addWidget(lbl_autohide)
        row_autohide.addWidget(self.cmb_draw_autohide, 1)
        layout_cfg.addLayout(row_autohide)

        self.chk_draw_sound = QCheckBox("🔊 เปิดเสียงเอฟเฟกต์ตอนสุ่ม (Sound Effects)")
        self.chk_draw_sound.setChecked(getattr(self.service, "sound_enabled", False))
        self.chk_draw_sound.stateChanged.connect(self._on_draw_sound_changed)
        layout_cfg.addWidget(self.chk_draw_sound)

        layout.addWidget(card_cfg)

        # ── Card 2: เวทีแสดงผลสุ่มรางวัล ──
        self._demo_draw_active = False
        self.btn_draw_demo = QPushButton("🎮 Demo สุ่มรางวัล")
        self.btn_draw_demo.setStyleSheet(STYLE_DRAW_DEMO_NORMAL)
        self.btn_draw_demo.setToolTip("แสดงตัวอย่างเวทีสุ่มรางวัลบน OBS Overlay เพื่อปรับแต่งขนาดและตำแหน่ง")
        self.btn_draw_demo.clicked.connect(self._toggle_draw_demo)

        card_stage, layout_stage = self._create_section_card("เวทีสุ่มผู้โชคดี (LUCKY DRAW)", "🎁", accent_color="#a855f7", extra_widget=self.btn_draw_demo)

        self.slot_stage = QWidget()
        self.slot_stage.setFixedHeight(115)
        stage_layout = QVBoxLayout(self.slot_stage)
        stage_layout.setContentsMargins(0, 4, 0, 4)
        stage_layout.setSpacing(4)

        self.lbl_slot_status = QLabel("พร้อมหมุนสุ่มรางวัล")
        self.lbl_slot_status.setAlignment(Qt.AlignCenter)
        self.lbl_slot_status.setStyleSheet("color: #a78bfa; font-size: 12.5px; font-weight: 700; background: transparent; border: none;")
        stage_layout.addWidget(self.lbl_slot_status)

        self.lbl_slot_name = QLabel("ยังไม่เริ่มสุ่ม")
        self.lbl_slot_name.setAlignment(Qt.AlignCenter)
        self.lbl_slot_name.setStyleSheet("color: #94a3b8; font-size: 26px; font-weight: 700; background: transparent; border: none;")
        stage_layout.addWidget(self.lbl_slot_name, 1)

        self.lbl_slot_sub = QLabel("ผู้มีสิทธิ์ในกลุ่มนี้: 0 คน")
        self.lbl_slot_sub.setAlignment(Qt.AlignCenter)
        self.lbl_slot_sub.setStyleSheet("color: #64748b; font-size: 12px; background: transparent; border: none;")
        stage_layout.addWidget(self.lbl_slot_sub)
        layout_stage.addWidget(self.slot_stage)

        self.btn_spin = QPushButton("🎁 เริ่มสุ่มเปิดกาชาปอง (GACHA PULL)")
        self.btn_spin.setProperty("variant", "amber")
        self.btn_spin.setFixedHeight(44)
        self.btn_spin.setStyleSheet("font-size: 15px; font-weight: 900;")
        self.btn_spin.clicked.connect(self._start_slot_spin)
        layout_stage.addWidget(self.btn_spin)
        self._on_draw_style_changed()

        self.winner_actions_box = QWidget()
        self.winner_actions_box.setVisible(False)
        w_layout = QHBoxLayout(self.winner_actions_box)
        w_layout.setContentsMargins(0, 4, 0, 4)
        w_layout.setSpacing(8)

        self.btn_confirm_winner = QPushButton("✅ ยืนยันผู้ชนะ (มอบรางวัล)")
        self.btn_confirm_winner.setProperty("variant", "success")
        self.btn_confirm_winner.clicked.connect(self._on_confirm_winner)
        w_layout.addWidget(self.btn_confirm_winner, 1)

        self.btn_reroll = QPushButton("🔄 สุ่มใหม่ (ไม่อยู่รับรางวัล)")
        self.btn_reroll.setStyleSheet("""
            QPushButton {
                background-color: #162032;
                border: 1px solid #283548;
                border-radius: 6px;
                color: #cbd5e1;
                font-size: 13px;
                font-weight: 600;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #1e293b;
                border-color: #fbbf24;
                color: #fbbf24;
            }
        """)
        self.btn_reroll.clicked.connect(self._start_slot_spin)
        w_layout.addWidget(self.btn_reroll, 1)
        layout_stage.addWidget(self.winner_actions_box)
        layout.addWidget(card_stage)

        # ── Card 3: ปรับแต่งหน้าตาสุ่มรางวัล (OBS Overlay) ──
        card_style, layout_style = self._create_section_card("ปรับแต่งหน้าตาสุ่มรางวัล (OBS OVERLAY)", "🎨", accent_color="#38bdf8")

        # 1. ขนาดโดยรวม (Overall Scale)
        row_scale = QHBoxLayout()
        row_scale.setSpacing(10)
        lbl_scale = QLabel("ขนาดโดยรวม:")
        lbl_scale.setStyleSheet("color: #cbd5e1; font-weight: 600; width: 95px;")
        self.slider_draw_scale = QSlider(Qt.Horizontal)
        self.slider_draw_scale.setRange(50, 180)
        self.slider_draw_scale.setValue(self.service.draw_scale)
        self.lbl_draw_scale_val = QLabel(f"{self.service.draw_scale}%")
        self.lbl_draw_scale_val.setStyleSheet("color: #38bdf8; font-weight: bold; width: 44px;")
        self.slider_draw_scale.valueChanged.connect(self._on_draw_scale_changed)
        row_scale.addWidget(lbl_scale)
        row_scale.addWidget(self.slider_draw_scale, 1)
        row_scale.addWidget(self.lbl_draw_scale_val)
        layout_style.addLayout(row_scale)

        # 2. ขนาดชื่อผู้ชนะ (Winner Font Size)
        row_name = QHBoxLayout()
        row_name.setSpacing(10)
        lbl_name = QLabel("ขนาดชื่อคน:")
        lbl_name.setStyleSheet("color: #cbd5e1; font-weight: 600; width: 95px;")
        self.slider_draw_name = QSlider(Qt.Horizontal)
        cur_style = getattr(self.service, "draw_animation_style", "gachapon")
        max_name_size = 50 if cur_style in ("slot", "slot_reel") else 90
        self.slider_draw_name.setRange(28, max_name_size)
        cur_val = min(self.service.draw_name_size, max_name_size)
        self.slider_draw_name.setValue(cur_val)
        self.lbl_draw_name_val = QLabel(f"{cur_val}px")
        self.lbl_draw_name_val.setStyleSheet("color: #fbbf24; font-weight: bold; width: 44px;")
        self.slider_draw_name.valueChanged.connect(self._on_draw_name_size_changed)
        row_name.addWidget(lbl_name)
        row_name.addWidget(self.slider_draw_name, 1)
        row_name.addWidget(self.lbl_draw_name_val)
        layout_style.addLayout(row_name)

        # 3. ขนาดป้ายของรางวัล (Prize Banner / Font Size)
        row_prize = QHBoxLayout()
        row_prize.setSpacing(10)
        lbl_prize = QLabel("ขนาดป้ายรางวัล:")
        lbl_prize.setStyleSheet("color: #cbd5e1; font-weight: 600; width: 95px;")
        self.slider_draw_prize = QSlider(Qt.Horizontal)
        self.slider_draw_prize.setRange(14, 38)
        self.slider_draw_prize.setValue(self.service.draw_prize_size)
        self.lbl_draw_prize_val = QLabel(f"{self.service.draw_prize_size}px")
        self.lbl_draw_prize_val.setStyleSheet("color: #f97316; font-weight: bold; width: 44px;")
        self.slider_draw_prize.valueChanged.connect(self._on_draw_prize_size_changed)
        row_prize.addWidget(lbl_prize)
        row_prize.addWidget(self.slider_draw_prize, 1)
        row_prize.addWidget(self.lbl_draw_prize_val)
        layout_style.addLayout(row_prize)

        # 4. ตำแหน่งแกน X / Y (Offset X / Y)
        row_ox = QHBoxLayout()
        row_ox.setSpacing(8)
        lbl_ox_title = QLabel("ตำแหน่ง X:")
        lbl_ox_title.setStyleSheet("color: #cbd5e1; font-weight: 600; width: 95px;")
        self.slider_draw_ox = QSlider(Qt.Horizontal)
        self.slider_draw_ox.setRange(-400, 400)
        self.slider_draw_ox.setValue(self.service.draw_offset_x)
        self.lbl_draw_ox_val = QLabel(f"{self.service.draw_offset_x:+d}px" if self.service.draw_offset_x != 0 else "0px")
        self.lbl_draw_ox_val.setStyleSheet("color: #a78bfa; font-size: 11.5px; width: 44px;")
        self.slider_draw_ox.valueChanged.connect(self._on_draw_ox_changed)
        row_ox.addWidget(lbl_ox_title)
        row_ox.addWidget(self.slider_draw_ox, 1)
        row_ox.addWidget(self.lbl_draw_ox_val)
        layout_style.addLayout(row_ox)

        row_oy = QHBoxLayout()
        row_oy.setSpacing(8)
        lbl_oy_title = QLabel("ตำแหน่ง Y:")
        lbl_oy_title.setStyleSheet("color: #cbd5e1; font-weight: 600; width: 95px;")
        self.slider_draw_oy = QSlider(Qt.Horizontal)
        self.slider_draw_oy.setRange(-400, 400)
        self.slider_draw_oy.setValue(self.service.draw_offset_y)
        self.lbl_draw_oy_val = QLabel(f"{self.service.draw_offset_y:+d}px" if self.service.draw_offset_y != 0 else "0px")
        self.lbl_draw_oy_val.setStyleSheet("color: #a78bfa; font-size: 11.5px; width: 44px;")
        self.slider_draw_oy.valueChanged.connect(self._on_draw_oy_changed)
        row_oy.addWidget(lbl_oy_title)
        row_oy.addWidget(self.slider_draw_oy, 1)
        row_oy.addWidget(self.lbl_draw_oy_val)
        layout_style.addLayout(row_oy)

        layout.addWidget(card_style)

        # ── Card 4: ทำเนียบผู้โชคดี ──
        card_win, layout_win = self._create_section_card("ทำเนียบผู้โชคดีที่ได้รับรางวัล", "🏆", accent_color="#34d399")

        self.tbl_winners = QTableWidget(0, 4)
        self.tbl_winners.setHorizontalHeaderLabels(["ผู้โชคดี", "แพลตฟอร์ม", "ของรางวัล", "สิทธิ์"])
        self.tbl_winners.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tbl_winners.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tbl_winners.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.tbl_winners.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.tbl_winners.verticalHeader().setVisible(False)
        self.tbl_winners.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl_winners.setShowGrid(False)
        self.tbl_winners.setAlternatingRowColors(True)
        self.tbl_winners.setFixedHeight(110)
        layout_win.addWidget(self.tbl_winners)

        win_actions_row = QHBoxLayout()
        win_actions_row.setContentsMargins(0, 4, 0, 0)
        self.btn_export_winners = QPushButton("📥 Export CSV")
        self.btn_export_winners.setProperty("variant", "ghost")
        self.btn_export_winners.setStyleSheet("color: #34d399; border-color: #059669; font-weight: 700; font-size: 11.5px; padding: 5px 12px;")
        self.btn_export_winners.clicked.connect(self._export_winners_csv_directly)
        win_actions_row.addWidget(self.btn_export_winners)

        win_actions_row.addStretch()

        self.btn_clear_winners = QPushButton("🗑️ ล้างประวัติ...")
        self.btn_clear_winners.setProperty("variant", "ghost")
        self.btn_clear_winners.setStyleSheet("color: #94a3b8; border-color: #334155; font-size: 11px; padding: 5px 10px;")
        self.btn_clear_winners.clicked.connect(self._clear_winners_history)
        win_actions_row.addWidget(self.btn_clear_winners)
        layout_win.addLayout(win_actions_row)

        layout.addWidget(card_win)

    # ═══════════════════════════════════════════════════════════════════
    # LOGIC & INTERACTION
    # ═══════════════════════════════════════════════════════════════════
    # ═══════════════════════════════════════════════════════════════════
    # LOGIC & INTERACTION
    # ═══════════════════════════════════════════════════════════════════
    def _connect_service_signals(self):
        self.service.config_changed.connect(self._on_service_config_changed)
        self.service.checkpoint_started.connect(self._on_service_cp_started)
        self.service.checkpoint_tick.connect(self._on_service_cp_tick)
        self.service.checkpoint_ended.connect(self._on_service_cp_ended)
        self.service.participant_added.connect(self._on_service_participant_added)
        self.service.data_cleared.connect(self._on_service_data_cleared)

    def _set_mode(self, mode: str):
        if mode == "single":
            self.service.set_mode("single")
        else:
            self.service.set_mode("multi")
        self._sync_mode_ui()

    def _on_add_checkpoint_clicked(self):
        if self.service.is_checkpoint_active():
            QMessageBox.warning(self, "แจ้งเตือน", "กรุณาปิดรับโค้ดในรอบปัจจุบันก่อนเพิ่มรอบใหม่ครับ")
            return
        next_idx = self.service.total_checkpoints + 1
        dlg = RoundNameDialog("➕ เพิ่มรอบกิจกรรมใหม่", f"รอบที่ {next_idx}", self)
        if dlg.exec() == QDialog.Accepted:
            custom_name = dlg.get_name()
            if not custom_name:
                custom_name = f"รอบที่ {next_idx}"
            new_cp = self.service.add_checkpoint(name=custom_name)
            self._sync_mode_ui()
            idx = self.cmb_active_cp.findData(new_cp)
            if idx >= 0:
                self.cmb_active_cp.setCurrentIndex(idx)

    def _on_rename_checkpoint_clicked(self):
        if self.service.is_checkpoint_active():
            QMessageBox.warning(self, "แจ้งเตือน", "กรุณาปิดรับโค้ดในรอบปัจจุบันก่อนแก้ไขชื่อรอบครับ")
            return
        target_cp = self.cmb_active_cp.currentData() or 1
        current_name = self.service.get_checkpoint_name(target_cp)
        dlg = RoundNameDialog(f"✏️ แก้ไขชื่อรอบ ({current_name})", current_name, self)
        if dlg.exec() == QDialog.Accepted:
            new_name = dlg.get_name()
            if new_name:
                self.service.set_checkpoint_name(target_cp, new_name)
                self._sync_mode_ui()

    def _on_remove_checkpoint_clicked(self):
        if self.service.is_checkpoint_active():
            QMessageBox.warning(self, "แจ้งเตือน", "กรุณาปิดรับโค้ดในรอบปัจจุบันก่อนลบรอบครับ")
            return
        if self.service.total_checkpoints <= 1:
            return

        target_cp = self.service.total_checkpoints
        cp_name = self.service.get_checkpoint_name(target_cp)
        cnt = sum(1 for p in self.service.participants.values() if target_cp in p.checkins)
        msg = f"คุณต้องการลบ '{cp_name}' ใช่หรือไม่?"
        if cnt > 0:
            msg += f"\n(มีผู้เข้าร่วมรอบนี้ {cnt} คน สิทธิ์ของรอบนี้จะถูกตัดออก)"

        reply = QMessageBox.question(
            self,
            "ยืนยันการลบรอบ",
            msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.service.remove_checkpoint()
            self._sync_mode_ui()

    def _sync_mode_ui(self):
        is_multi = (self.service.mode == "multi")
        self.btn_mode_single.setChecked(not is_multi)
        self.btn_mode_multi.setChecked(is_multi)

        active_mode_qss = (
            "QPushButton {"
            "  background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0284c7, stop:1 #0369a1);"
            "  color: #ffffff;"
            "  border: 2px solid #38bdf8;"
            "  border-radius: 8px;"
            "  padding: 10px 14px;"
            "  font-size: 13.5px;"
            "  font-weight: 800;"
            "}"
            "QPushButton:hover {"
            "  background: #0284c7;"
            "  border-color: #7dd3fc;"
            "}"
        )
        inactive_mode_qss = (
            "QPushButton {"
            "  background-color: #111a2e;"
            "  color: #94a3b8;"
            "  border: 2px solid #24344d;"
            "  border-radius: 8px;"
            "  padding: 10px 14px;"
            "  font-size: 13.5px;"
            "  font-weight: 600;"
            "}"
            "QPushButton:hover {"
            "  background-color: #17243c;"
            "  border-color: #38bdf8;"
            "  color: #f1f5f9;"
            "}"
        )

        if not is_multi:
            self.btn_mode_single.setText("🔘 🎯 ด่านเดียว (รอบเดียว)")
            self.btn_mode_single.setStyleSheet(active_mode_qss)
            self.btn_mode_multi.setText("⚪ 📍 หลายด่านสะสมแต้ม")
            self.btn_mode_multi.setStyleSheet(inactive_mode_qss)
        else:
            self.btn_mode_single.setText("⚪ 🎯 ด่านเดียว (รอบเดียว)")
            self.btn_mode_single.setStyleSheet(inactive_mode_qss)
            self.btn_mode_multi.setText("🔘 📍 หลายด่านสะสมแต้ม")
            self.btn_mode_multi.setStyleSheet(active_mode_qss)

        self.btn_rename_cp.setEnabled(not self.service.is_active)
        self.btn_add_cp.setEnabled(not self.service.is_active)
        self.btn_remove_cp.setEnabled(is_multi and self.service.total_checkpoints > 1 and not self.service.is_active)

        if not is_multi:
            self.lbl_cp_summary.setText(f"รอบเดียว ({self.service.get_checkpoint_name(1)})")
        else:
            self.lbl_cp_summary.setText(f"สะสมแต้ม (ทั้งหมด {self.service.total_checkpoints} รอบ)")

        self.cmb_active_cp.blockSignals(True)
        self.cmb_active_cp.clear()

        if not is_multi:
            cnt = sum(1 for p in self.service.participants.values() if 1 in p.checkins)
            code_str = self.service.get_checkpoint_code(1)
            name_str = self.service.get_checkpoint_name(1)
            if self.service.is_active:
                self.cmb_active_cp.addItem(f"🟢 {name_str} — กำลังเปิด: {code_str}", 1)
            elif cnt > 0:
                self.cmb_active_cp.addItem(f"✅ {name_str}: {code_str} ({cnt} คน)", 1)
            else:
                self.cmb_active_cp.addItem(f"🎯 {name_str} ({code_str})", 1)
            self.lbl_sel_cp.setText("รอบกิจกรรม:")
        else:
            self.lbl_sel_cp.setText("รอบที่จะเปิด:")
            for i in range(1, self.service.total_checkpoints + 1):
                name_str = self.service.get_checkpoint_name(i)
                cnt = sum(1 for p in self.service.participants.values() if i in p.checkins)
                code_str = self.service.get_checkpoint_code(i)
                if self.service.is_active and self.service.active_checkpoint == i:
                    status_desc = f"🟢 {name_str} — กำลังเปิด: {code_str}"
                elif cnt > 0:
                    status_desc = f"✅ {name_str} — {code_str} ({cnt} คน)"
                else:
                    status_desc = f"📍 {name_str} — {code_str}"
                self.cmb_active_cp.addItem(status_desc, i)

        cur_cp = min(self.service.active_checkpoint, self.service.total_checkpoints)
        idx = self.cmb_active_cp.findData(cur_cp)
        if idx >= 0:
            self.cmb_active_cp.setCurrentIndex(idx)
        self.cmb_active_cp.blockSignals(False)

        self.inp_code.setText(self.service.get_checkpoint_code(cur_cp))

        cur_name = self.service.get_checkpoint_name(cur_cp)
        cur_cnt = sum(1 for p in self.service.participants.values() if cur_cp in p.checkins)

        disp_mode = getattr(self.service, 'overlay_display_mode', 'banner')
        if disp_mode not in ("banner", "image", "none"):
            disp_mode = "banner"

        if not self.service.is_checkpoint_active():
            if cur_cnt > 0:
                self.btn_toggle_checkpoint.setText(f"🚀 เปิดรับเพิ่ม ({cur_name})")
            elif is_multi:
                self.btn_toggle_checkpoint.setText(f"🚀 เริ่มเปิดรับโค้ด ({cur_name})")
            elif disp_mode == "none":
                self.btn_toggle_checkpoint.setText("🚀 เริ่มเปิดรับโค้ด (โหมดเบื้องหลัง)")
            else:
                self.btn_toggle_checkpoint.setText("🚀 เริ่มเปิดรับโค้ดขึ้นจอ")

        # ซิงค์การแสดงผล Overlay
        is_image_mode = (disp_mode == 'image')
        self.btn_display_banner.setChecked(disp_mode == 'banner')
        self.btn_display_image.setChecked(disp_mode == 'image')
        self.btn_display_none.setChecked(disp_mode == 'none')
        self.image_settings_widget.setVisible(is_image_mode)

        self._overlay_image_path = getattr(self.service, 'overlay_image_path', '')
        if self._overlay_image_path and os.path.exists(self._overlay_image_path):
            self.lbl_image_path.setText(f"🖼️ {os.path.basename(self._overlay_image_path)}")
            self.lbl_image_path.setStyleSheet("color: #38bdf8; font-weight: 600; font-size: 12px;")
            self.lbl_image_path.setToolTip(self._overlay_image_path)
        else:
            self.lbl_image_path.setText("ยังไม่ได้เลือกรูปภาพ (รองรับ PNG, JPG, WebP, GIF)")
            self.lbl_image_path.setStyleSheet("color: #94a3b8; font-size: 12px;")
            self.lbl_image_path.setToolTip("")

        pos = getattr(self.service, 'overlay_position', 'right')
        pos_idx = self.cmb_position.findData(pos)
        if pos_idx >= 0:
            self.cmb_position.blockSignals(True)
            self.cmb_position.setCurrentIndex(pos_idx)
            self.cmb_position.blockSignals(False)

        self.slider_scale.blockSignals(True)
        self.slider_scale.setValue(getattr(self.service, 'overlay_scale', 100))
        self.lbl_scale_val.setText(f"{self.slider_scale.value()}%")
        self.slider_scale.blockSignals(False)

        self.slider_offset_x.blockSignals(True)
        self.slider_offset_x.setValue(getattr(self.service, 'overlay_offset_x', 0))
        self.lbl_offset_x_val.setText(f"{self.slider_offset_x.value():+d}px" if self.slider_offset_x.value() != 0 else "0px")
        self.slider_offset_x.blockSignals(False)

        self.slider_offset_y.blockSignals(True)
        self.slider_offset_y.setValue(getattr(self.service, 'overlay_offset_y', 0))
        self.lbl_offset_y_val.setText(f"{self.slider_offset_y.value():+d}px" if self.slider_offset_y.value() != 0 else "0px")
        self.slider_offset_y.blockSignals(False)

        anim_in = getattr(self.service, 'overlay_anim_in', 'slide')
        ai_idx = self.cmb_anim_in.findData(anim_in)
        if ai_idx >= 0:
            self.cmb_anim_in.blockSignals(True)
            self.cmb_anim_in.setCurrentIndex(ai_idx)
            self.cmb_anim_in.blockSignals(False)

        anim_out = getattr(self.service, 'overlay_anim_out', 'slide')
        ao_idx = self.cmb_anim_out.findData(anim_out)
        if ao_idx >= 0:
            self.cmb_anim_out.blockSignals(True)
            self.cmb_anim_out.setCurrentIndex(ao_idx)
            self.cmb_anim_out.blockSignals(False)

        self.chk_show_progress_bar.blockSignals(True)
        self.chk_show_progress_bar.setChecked(getattr(self.service, 'overlay_show_progress_bar', True))
        self.chk_show_progress_bar.blockSignals(False)

        self.chk_border_countdown.blockSignals(True)
        self.chk_border_countdown.setChecked(getattr(self.service, 'overlay_show_countdown_border', True))
        self.chk_border_countdown.blockSignals(False)

        b_theme = getattr(self.service, 'overlay_border_theme', 'rainbow')
        bt_idx = self.cmb_border_theme.findData(b_theme)
        if bt_idx >= 0:
            self.cmb_border_theme.blockSignals(True)
            self.cmb_border_theme.setCurrentIndex(bt_idx)
            self.cmb_border_theme.blockSignals(False)

        self.chk_show_stats.blockSignals(True)
        self.chk_show_stats.setChecked(getattr(self.service, 'overlay_show_stats', True))
        self.chk_show_stats.blockSignals(False)

        self.chk_show_toast.blockSignals(True)
        self.chk_show_toast.setChecked(getattr(self.service, 'overlay_show_toast', True))
        self.chk_show_toast.blockSignals(False)

        self._update_stat_strip_ui()
        self._update_draw_groups_dropdown()
        self._refresh_participants_table()

    def _set_display_mode(self, mode: str):
        is_img = (mode == "image")
        self.btn_display_banner.setChecked(not is_img)
        self.btn_display_image.setChecked(is_img)
        self.image_settings_widget.setVisible(is_img)

        active_disp_qss = (
            "QPushButton {"
            "  background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0284c7, stop:1 #0369a1);"
            "  color: #ffffff;"
            "  border: 2px solid #38bdf8;"
            "  border-radius: 8px;"
            "  padding: 8px 6px;"
            "  font-size: 11.5px;"
            "  font-weight: 800;"
            "}"
            "QPushButton:hover {"
            "  background: #0284c7;"
            "  border-color: #7dd3fc;"
            "}"
        )
        inactive_disp_qss = (
            "QPushButton {"
            "  background-color: #111a2e;"
            "  color: #94a3b8;"
            "  border: 2px solid #24344d;"
            "  border-radius: 8px;"
            "  padding: 8px 6px;"
            "  font-size: 11.5px;"
            "  font-weight: 600;"
            "}"
            "QPushButton:hover {"
            "  background-color: #17243c;"
            "  border-color: #38bdf8;"
            "  color: #f1f5f9;"
            "}"
        )

        self.btn_display_banner.setChecked(mode == "banner")
        self.btn_display_image.setChecked(mode == "image")
        self.btn_display_none.setChecked(mode == "none")

        self.btn_display_banner.setText("🔘 📝 การ์ดข้อความ" if mode == "banner" else "⚪ 📝 การ์ดข้อความ")
        self.btn_display_banner.setStyleSheet(active_disp_qss if mode == "banner" else inactive_disp_qss)

        self.btn_display_image.setText("🔘 🖼️ ภาพแบนเนอร์" if mode == "image" else "⚪ 🖼️ ภาพแบนเนอร์")
        self.btn_display_image.setStyleSheet(active_disp_qss if mode == "image" else inactive_disp_qss)

        self.btn_display_none.setText("🔘 🔇 ซ่อนบนจอ" if mode == "none" else "⚪ 🔇 ซ่อนบนจอ")
        self.btn_display_none.setStyleSheet(active_disp_qss if mode == "none" else inactive_disp_qss)

        self.image_settings_widget.setVisible(mode == "image")
        self._on_overlay_settings_changed()

    def _on_browse_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "เลือกรูปภาพแบนเนอร์สำหรับ Overlay",
            "",
            "รูปภาพ (*.png *.jpg *.jpeg *.webp *.gif);;All Files (*.*)"
        )
        if file_path:
            self._overlay_image_path = file_path
            self.lbl_image_path.setText(f"🖼️ {os.path.basename(file_path)}")
            self.lbl_image_path.setStyleSheet("color: #38bdf8; font-weight: 600; font-size: 12px;")
            self.lbl_image_path.setToolTip(file_path)
            self._on_overlay_settings_changed()

    def _on_clear_image(self):
        self._overlay_image_path = ""
        self.lbl_image_path.setText("ยังไม่ได้เลือกรูปภาพ (รองรับ PNG, JPG, WebP, GIF)")
        self.lbl_image_path.setStyleSheet("color: #94a3b8; font-size: 12px;")
        self.lbl_image_path.setToolTip("")
        self._on_overlay_settings_changed()

    def _on_scale_slider_changed(self, val: int):
        self.lbl_scale_val.setText(f"{val}%")
        self._on_overlay_settings_changed()

    def _on_offset_x_changed(self, val: int):
        self.lbl_offset_x_val.setText(f"{val:+d}px" if val != 0 else "0px")
        self._on_overlay_settings_changed()

    def _on_offset_y_changed(self, val: int):
        self.lbl_offset_y_val.setText(f"{val:+d}px" if val != 0 else "0px")
        self._on_overlay_settings_changed()

    def _on_overlay_settings_changed(self):
        if self.btn_display_none.isChecked():
            mode = "none"
        elif self.btn_display_image.isChecked():
            mode = "image"
        else:
            mode = "banner"
        pos = self.cmb_position.currentData() or "right"
        scale = self.slider_scale.value()
        ox = self.slider_offset_x.value()
        oy = self.slider_offset_y.value()
        anim_in = self.cmb_anim_in.currentData() or "slide"
        anim_out = self.cmb_anim_out.currentData() or "slide"
        border = self.chk_border_countdown.isChecked()
        border_theme = self.cmb_border_theme.currentData() or "rainbow"
        stats = self.chk_show_stats.isChecked()
        toast = self.chk_show_toast.isChecked()
        img_path = getattr(self, '_overlay_image_path', '')

        self.service.update_overlay_settings(
            overlay_display_mode=mode,
            overlay_image_path=img_path,
            overlay_position=pos,
            overlay_offset_x=ox,
            overlay_offset_y=oy,
            overlay_scale=scale,
            overlay_anim_in=anim_in,
            overlay_anim_out=anim_out,
            overlay_show_progress_bar=self.chk_show_progress_bar.isChecked(),
            overlay_show_countdown_border=border,
            overlay_border_theme=border_theme,
            overlay_show_stats=stats,
            overlay_show_toast=toast,
        )

    def _on_preview_obs_clicked(self):
        self._toggle_checkpoint_demo()

    def _toggle_checkpoint_demo(self):
        self._on_overlay_settings_changed()
        if getattr(self, "_demo_cp_active", False):
            self._demo_cp_active = False
            self.btn_preview_obs.setText("👁️ Demo เปิดรับโค้ด")
            self.btn_preview_obs.setStyleSheet(STYLE_PREVIEW_NORMAL)
            self.btn_preview_obs.setToolTip("คลิกเพื่อเปิด/ปิดแสดงตัวอย่างการ์ดเปิดรับโค้ดบน OBS Overlay ค้างไว้สำหรับปรับตำแหน่งและขนาด")
            self.service.trigger_preview({"action": "stop", "show": False})
        else:
            self._demo_cp_active = True
            self.btn_preview_obs.setText("⏹️ ปิด Demo")
            self.btn_preview_obs.setStyleSheet(STYLE_DEMO_RED)
            self.btn_preview_obs.setToolTip("คลิกเพื่อปิดการแสดงตัวอย่างเปิดรับโค้ดบน OBS")
            cp_idx = self.cmb_active_cp.currentData() or 1
            code = self.inp_code.text().strip() or "!join"
            dur = self.spin_minutes.seconds() if self.rad_duration_timer.isChecked() else 0
            self.service.trigger_preview({
                "stay": True,
                "show": True,
                "cp_index": cp_idx,
                "code": code,
                "duration": dur or 60,
                "mode": self.service.mode,
                "total_checkpoints": self.service.total_checkpoints
            })

    def _on_active_cp_changed(self, idx: int):
        cp_num = self.cmb_active_cp.currentData() or 1
        self.inp_code.setText(self.service.get_checkpoint_code(cp_num))
        cur_name = self.service.get_checkpoint_name(cp_num)
        cur_cnt = sum(1 for p in self.service.participants.values() if cp_num in p.checkins)
        if not self.service.is_checkpoint_active():
            if cur_cnt > 0:
                self.btn_toggle_checkpoint.setText(f"🚀 เปิดรับเพิ่ม ({cur_name})")
            elif self.service.mode == "multi":
                self.btn_toggle_checkpoint.setText(f"🚀 เริ่มเปิดรับโค้ด ({cur_name})")
            else:
                self.btn_toggle_checkpoint.setText("🚀 เริ่มเปิดรับโค้ดขึ้นจอ")
            self._update_checkpoint_button_style(False)

    def _on_code_text_edited(self, text: str):
        cp_num = self.cmb_active_cp.currentData() or 1
        if not self.service.is_active:
            self.service.set_checkpoint_code(cp_num, text)

    def _generate_random_code(self):
        prefixes = ["WIN", "LUCKY", "DROP", "GIFT", "PLAY", "CODE"]
        num = random.randint(100, 999)
        self.inp_code.setText(f"{random.choice(prefixes)}{num}")

    def _on_duration_mode_toggled(self):
        is_timer = self.rad_duration_timer.isChecked()
        self.timer_controls_widget.setVisible(is_timer)
        if not is_timer:
            self.progress_bar.setFormat("เปิดรับต่อเนื่อง (ไม่มีกำหนดเวลา)")
            self.progress_bar.setValue(100)

    def _update_preset_time_buttons(self, active_secs: int):
        qss_active = """
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #d97706, stop:1 #b45309);
                border: 1.5px solid #fbbf24;
                border-radius: 6px;
                color: #ffffff;
                font-weight: 800;
                font-size: 12.5px;
                padding: 6px 13px;
                min-height: 20px;
            }
            QPushButton:hover {
                background: #d97706;
                border-color: #fde68a;
            }
        """
        qss_inactive = """
            QPushButton {
                background-color: #162032;
                border: 1px solid #283548;
                border-radius: 6px;
                color: #94a3b8;
                font-weight: 600;
                font-size: 12.5px;
                padding: 6px 13px;
                min-height: 20px;
            }
            QPushButton:hover {
                background-color: #1e293b;
                border-color: #fbbf24;
                color: #fbbf24;
            }
            QPushButton:pressed {
                background-color: #0f172a;
            }
        """
        for secs, btn in getattr(self, '_preset_time_buttons', []):
            if secs == active_secs:
                btn.setStyleSheet(qss_active)
            else:
                btn.setStyleSheet(qss_inactive)

    def _set_quick_seconds(self, secs: int):
        self.rad_duration_timer.setChecked(True)
        self.spin_minutes.blockSignals(True)
        self.spin_minutes.set_seconds(secs)
        self.spin_minutes.blockSignals(False)
        self._quick_secs = secs
        self._update_preset_time_buttons(secs)

    def _set_quick_preset(self, secs: int):
        self.rad_duration_timer.setChecked(True)
        self.spin_minutes.blockSignals(True)
        self.spin_minutes.set_seconds(secs)
        self.spin_minutes.blockSignals(False)
        self._quick_secs = secs
        self._update_preset_time_buttons(secs)

    def _on_stepper_duration_changed(self, secs: int):
        self._quick_secs = secs
        self._update_preset_time_buttons(secs)

    def _on_toggle_checkpoint(self):
        if getattr(self, "_demo_cp_active", False):
            self._demo_cp_active = False
            self.btn_preview_obs.setText("👁️ Demo เปิดรับโค้ด")
            self.btn_preview_obs.setStyleSheet(STYLE_PREVIEW_NORMAL)

        if self.service.is_checkpoint_active():
            self.service.stop_checkpoint()
        else:
            cp_idx = self.cmb_active_cp.currentData() or 1
            code = self.inp_code.text().strip()
            if not code:
                QMessageBox.warning(self, "แจ้งเตือน", "กรุณาระบุโค้ดที่ต้องการให้ผู้ชมพิมพ์ครับ")
                return

            if self.rad_duration_timer.isChecked():
                dur = self.spin_minutes.seconds()
            else:
                dur = 0

            self.service.start_checkpoint(cp_idx, code, dur)

    def _update_checkpoint_button_style(self, is_active: bool):
        """อัปเดตสไตล์ของปุ่มเริ่ม/ปิดรับโค้ด ให้โดดเด่น ชัดเจน มีมิติ"""
        if is_active:
            self.btn_toggle_checkpoint.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ef4444, stop:1 #dc2626);
                    border: 2px solid #f87171;
                    border-radius: 8px;
                    color: #ffffff;
                    font-size: 15.5px;
                    font-weight: 800;
                    padding: 11px 20px;
                }
                QPushButton:hover {
                    background: #ef4444;
                    border-color: #fca5a5;
                }
                QPushButton:pressed {
                    background: #b91c1c;
                }
            """)
        else:
            self.btn_toggle_checkpoint.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #10b981, stop:1 #059669);
                    border: 2px solid #34d399;
                    border-radius: 8px;
                    color: #ffffff;
                    font-size: 15.5px;
                    font-weight: 800;
                    padding: 11px 20px;
                }
                QPushButton:hover {
                    background: #10b981;
                    border-color: #6ee7b7;
                }
                QPushButton:pressed {
                    background: #047857;
                }
            """)

    def _on_service_cp_started(self, cp_index: int, code: str, duration: int):
        cur_name = self.service.get_checkpoint_name(cp_index)
        self.btn_toggle_checkpoint.setText(f"⏹️ ปิดรับโค้ดทันที (ปิด{cur_name})")
        self._update_checkpoint_button_style(True)

        self.btn_rename_cp.setEnabled(False)
        self.btn_add_cp.setEnabled(False)
        self.btn_remove_cp.setEnabled(False)

        self.lbl_status_badge.setText(f"🟢 กำลังเปิดรับ: {code}")
        self.lbl_status_badge.setStyleSheet(
            "background: #064e3b; color: #34d399; border-radius: 4px; "
            "padding: 4px 10px; font-size: 11px; font-weight: bold;"
        )

        if duration > 0:
            self.progress_bar.setRange(0, duration * 10)
            self.progress_bar.setValue(duration * 10)
            mins = duration // 60
            secs = duration % 60
            self.progress_bar.setFormat(f"เหลือเวลา: {mins:02d}:{secs:02d}")
            self._timer.start()
        else:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(100)
            self.progress_bar.setFormat("เปิดรับต่อเนื่อง (คลิกปิดรับโค้ดเมื่อต้องการ)")
            self._timer.start()

        self._update_stats_display()

    def _on_service_cp_ended(self, cp_index: int, total: int):
        self._timer.stop()
        self._update_checkpoint_button_style(False)

        cur_name = self.service.get_checkpoint_name(cp_index)
        self.lbl_status_badge.setText("พร้อมเริ่มกิจกรรม")
        self.lbl_status_badge.setStyleSheet(
            "background: #162032; color: #94a3b8; border-radius: 4px; "
            "padding: 4px 10px; font-size: 11px; font-weight: bold;"
        )

        self.progress_bar.setValue(0)
        self.progress_bar.setFormat(f"ปิดรับ{cur_name}แล้ว ({total} คน)")
        self._sync_mode_ui()
        self._update_stats_display()
        self._refresh_participants_table()
        self._update_draw_pool_info()

    def _on_service_cp_tick(self, remaining_sec: float, round_participants: int):
        """รับ tick ตรงจาก GiveawayService ซิงค์ตัวเลขเวลาให้ตรงกับ OBS Overlay 100%"""
        if not self.service.is_checkpoint_active():
            return
        if self.service.duration_sec > 0:
            mins = int(remaining_sec // 60)
            secs = int(remaining_sec % 60)
            self.progress_bar.setValue(int(remaining_sec * 10))
            self.progress_bar.setFormat(f"เหลือเวลา: {mins:02d}:{secs:02d}")
        else:
            elapsed = int(time.time() - self.service.start_time)
            em = elapsed // 60
            es = elapsed % 60
            self.progress_bar.setFormat(f"เปิดรับอยู่: {em:02d}:{es:02d} (ปิดด้วยตนเอง)")
        self._update_stats_display()

    def _on_timer_tick(self):
        if not self.service.is_checkpoint_active():
            return
        if self.service.duration_sec > 0:
            rem = self.service.get_remaining_sec()
            mins = int(rem // 60)
            secs = int(rem % 60)
            self.progress_bar.setValue(int(rem * 10))
            self.progress_bar.setFormat(f"เหลือเวลา: {mins:02d}:{secs:02d}")
        else:
            elapsed = int(time.time() - self.service.start_time)
            em = elapsed // 60
            es = elapsed % 60
            self.progress_bar.setFormat(f"เปิดรับอยู่: {em:02d}:{es:02d} (ปิดด้วยตนเอง)")
        self._update_stats_display()

    def _on_service_participant_added(self, participant: Participant, cp_index: int):
        self._update_stats_display()
        self._refresh_participants_table()
        self._update_draw_pool_info()

    def _on_service_config_changed(self):
        self._sync_mode_ui()

    # ── Flat Stat Summary (เรียบหรู ปราศจากกล่องครอบ) ──
    def _update_stat_strip_ui(self):
        while self.stat_bar_layout.count():
            item = self.stat_bar_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        counts = self.service.get_participant_counts()

        if self.service.mode == "single":
            lbl_all = QLabel(f"👥 ผู้เข้าร่วมกิจกรรมทั้งหมด: <b style='color:#38bdf8;'>{counts['all']}</b> คน")
            lbl_all.setStyleSheet("font-size: 13px;")
            self.stat_bar_layout.addWidget(lbl_all, 0, 0, 1, 2)
        else:
            tot = self.service.total_checkpoints
            colors = ["#34d399", "#fbbf24", "#94a3b8", "#c084fc", "#f472b6"]
            row, col = 0, 0
            for i in range(1, tot + 1):
                col_c = colors[(i - 1) % len(colors)]
                cnt = counts.get(f"tier_{i}", 0)
                tier_title = "ผ่านครบทุกรอบ" if i == 1 else f"ผ่าน {tot - i + 1} รอบ"
                lbl = QLabel(f"<span style='color:{col_c}; font-size:14px;'>●</span> <b>{tier_title}:</b> {cnt} คน")
                lbl.setStyleSheet("font-size: 12.5px; color: #cbd5e1;")
                self.stat_bar_layout.addWidget(lbl, row, col)
                col += 1
                if col >= 2:
                    col = 0
                    row += 1

            lbl_tot = QLabel(f"<span style='color:#38bdf8;'>👥</span> <b>รวมทั้งหมด:</b> {counts['all']} คน")
            lbl_tot.setStyleSheet("font-size: 12.5px; color: #f8fafc;")
            self.stat_bar_layout.addWidget(lbl_tot, row, col)

    def _update_stats_display(self):
        counts = self.service.get_participant_counts()
        cur_cp = self.cmb_active_cp.currentData() or 1
        round_count = counts.get(f"cp{cur_cp}", 0)
        total_count = counts["all"]

        self.lbl_round_stats.setText(f"ผู้เข้ารอบนี้: {round_count} คน (รวมสะสม: {total_count} คน)")
        self._update_stat_strip_ui()

    def _refresh_participants_table(self):
        tier_filter = self.cmb_filter_tier.currentData()
        groups = self.service.get_tier_groups()
        items = groups.get(tier_filter, groups.get("all", []))

        search = self.inp_search.text().strip().lower()
        if search:
            items = [p for p in items if search in p.author.lower()]

        tot = self.service.total_checkpoints
        self.tbl_participants.setRowCount(len(items))

        for row, p in enumerate(items):
            self.tbl_participants.setItem(row, 0, QTableWidgetItem(p.author))
            self.tbl_participants.setItem(row, 1, QTableWidgetItem(p.platform.capitalize()))

            if tot > 1:
                badges = [f"✓ {i}" for i in range(1, tot + 1) if i in p.checkins]
                it_cps = QTableWidgetItem(" ".join(badges) or "-")
                it_cps.setTextAlignment(Qt.AlignCenter)
                self.tbl_participants.setItem(row, 2, it_cps)

                it_cnt = QTableWidgetItem(f"{len(p.checkins)}/{tot}")
                it_cnt.setTextAlignment(Qt.AlignCenter)
                self.tbl_participants.setItem(row, 3, it_cnt)

                tier_num = p.calculate_tier(tot)
                status_text = "🏆 ผ่านครบทุกรอบ" if tier_num == 1 else f"ผ่าน {tot - tier_num + 1} รอบ"
                it_tier = QTableWidgetItem(status_text)
                it_tier.setTextAlignment(Qt.AlignCenter)
                it_tier.setForeground(QColor("#10b981" if tier_num == 1 else "#f59e0b"))
                self.tbl_participants.setItem(row, 4, it_tier)
            else:
                it_cps = QTableWidgetItem("ผ่าน ✓" if 1 in p.checkins else "-")
                it_cps.setTextAlignment(Qt.AlignCenter)
                self.tbl_participants.setItem(row, 2, it_cps)

                it_cnt = QTableWidgetItem("1 สิทธิ์")
                it_cnt.setTextAlignment(Qt.AlignCenter)
                self.tbl_participants.setItem(row, 3, it_cnt)

                it_tier = QTableWidgetItem("ผู้เข้าร่วม")
                it_tier.setTextAlignment(Qt.AlignCenter)
                it_tier.setForeground(QColor("#38bdf8"))
                self.tbl_participants.setItem(row, 4, it_tier)

    def _update_draw_groups_dropdown(self):
        self.cmb_draw_group.blockSignals(True)
        self.cmb_draw_group.clear()

        self.cmb_filter_tier.blockSignals(True)
        self.cmb_filter_tier.clear()
        self.cmb_filter_tier.addItem("ทั้งหมด (ทุกคน)", "all")

        groups = self.service.get_tier_groups()
        tot = self.service.total_checkpoints

        if self.service.mode == "single":
            cnt = len(groups.get("all", []))
            self.cmb_draw_group.addItem(f"🌐 ผู้เข้าร่วมทั้งหมด ({cnt} คน)", "all")
        else:
            # 1. สุ่มเฉพาะตามรอบกิจกรรม (กรณีที่ 2: ของรางวัลคนละแบบ แยกตามรอบ)
            for i in range(1, tot + 1):
                cp_name = self.service.get_checkpoint_name(i)
                code_str = self.service.get_checkpoint_code(i)
                cnt = len(groups.get(f"cp_{i}", []))
                self.cmb_draw_group.addItem(f"📍 สุ่มเฉพาะ: {cp_name} [{code_str}] ({cnt} คน)", f"cp_{i}")
                self.cmb_filter_tier.addItem(f"📍 {cp_name} ({cnt} คน)", f"cp_{i}")

            # 2. สุ่มตามระดับสะสมแต้ม (กรณีที่ 1: เก็บคะแนนสะสมแต้ม)
            cnt_t1 = len(groups.get("tier_1", []))
            self.cmb_draw_group.addItem(f"🏆 สิทธิ์สูงสุด (สะสมครบ {tot} รอบ) ({cnt_t1} คน)", "tier_1")
            self.cmb_filter_tier.addItem(f"🏆 ผ่านครบทุกรอบ ({tot} รอบ)", "tier_1")

            for i in range(2, tot + 1):
                cnt_ti = len(groups.get(f"tier_{i}", []))
                self.cmb_draw_group.addItem(f"🥈 สะสม {tot - i + 1} รอบ ({cnt_ti} คน)", f"tier_{i}")
                self.cmb_filter_tier.addItem(f"🥈 ผ่าน {tot - i + 1} รอบ", f"tier_{i}")

            # 3. สุ่มรวมทุกคน
            cnt_all = len(groups.get("all", []))
            self.cmb_draw_group.addItem(f"🌐 รวมผู้เข้าร่วมทั้งหมดทุกรอบ ({cnt_all} คน)", "all")

        self.cmb_draw_group.blockSignals(False)
        self.cmb_filter_tier.blockSignals(False)
        self._update_draw_pool_info()

    def _update_draw_pool_info(self):
        grp_key = self.cmb_draw_group.currentData() or "all"
        groups = self.service.get_tier_groups()
        pool = groups.get(grp_key, groups.get("all", []))

        if self.chk_exclude_previous.isChecked():
            prev = {w.author.lower() for w in self.service.winners_history}
            pool = [p for p in pool if p.author.lower() not in prev]

        self.lbl_slot_sub.setText(f"ผู้มีสิทธิ์ในกลุ่มนี้: {len(pool)} คน")

    def _on_draw_style_changed(self):
        style = self.cmb_draw_style.currentData() or "gachapon"
        self.service.update_overlay_settings(draw_animation_style=style)
        if hasattr(self, 'slider_draw_name'):
            max_name = 50 if style in ("slot", "slot_reel") else 90
            self.slider_draw_name.blockSignals(True)
            self.slider_draw_name.setRange(28, max_name)
            if self.slider_draw_name.value() > max_name:
                self.slider_draw_name.setValue(max_name)
                self.lbl_draw_name_val.setText(f"{max_name}px")
                self.service.update_overlay_settings(draw_name_size=max_name)
            self.slider_draw_name.blockSignals(False)
        if not self._pending_winner:
            self.lbl_slot_name.setText("ยังไม่เริ่มสุ่ม")
            self.lbl_slot_name.setStyleSheet("color: #94a3b8; font-size: 26px; font-weight: 700; background: transparent; border: none;")

        if style == "gachapon":
            self.btn_spin.setText("🎁 เริ่มสุ่มเปิดกาชาปอง (GACHA PULL)")
        elif style == "slot_reel":
            self.btn_spin.setText("🎰 เริ่มหมุนวงล้อสล็อต (SPIN REEL)")
        else:
            self.btn_spin.setText("🔀 เริ่มสุ่มสลับชื่อ (SHUFFLE)")

    def _on_draw_theme_changed(self):
        theme = self.cmb_draw_theme.currentData() or "gold"
        self.service.update_overlay_settings(draw_theme=theme)

    def _on_draw_sound_changed(self, state: int):
        enabled = bool(state == Qt.Checked or state == 2 or state is True)
        self.service.update_overlay_settings(sound_enabled=enabled)

    def _on_draw_autohide_changed(self):
        sec = self.cmb_draw_autohide.currentData()
        if sec is None:
            sec = 15
        self.service.update_overlay_settings(draw_autohide_sec=int(sec))

    def _on_draw_scale_changed(self, val: int):
        self.lbl_draw_scale_val.setText(f"{val}%")
        self.service.update_overlay_settings(draw_scale=val)

    def _on_draw_name_size_changed(self, val: int):
        self.lbl_draw_name_val.setText(f"{val}px")
        self.service.update_overlay_settings(draw_name_size=val)

    def _on_draw_prize_size_changed(self, val: int):
        self.lbl_draw_prize_val.setText(f"{val}px")
        self.service.update_overlay_settings(draw_prize_size=val)

    def _on_draw_ox_changed(self, val: int):
        self.lbl_draw_ox_val.setText(f"{val:+d}px" if val != 0 else "0px")
        self.service.update_overlay_settings(draw_offset_x=val)

    def _on_draw_oy_changed(self, val: int):
        self.lbl_draw_oy_val.setText(f"{val:+d}px" if val != 0 else "0px")
        self.service.update_overlay_settings(draw_offset_y=val)

    def _toggle_draw_demo(self):
        if getattr(self, "_demo_draw_active", False):
            self._demo_draw_active = False
            self.btn_draw_demo.setText("🎮 Demo สุ่มรางวัล")
            self.btn_draw_demo.setStyleSheet(STYLE_DRAW_DEMO_NORMAL)
            self.btn_draw_demo.setToolTip("แสดงตัวอย่างเวทีสุ่มรางวัลบน OBS Overlay เพื่อปรับแต่งขนาดและตำแหน่ง")
            if hasattr(self, "_demo_draw_timer") and self._demo_draw_timer.isActive():
                self._demo_draw_timer.stop()
            self.service.broadcast_draw_reset()
        else:
            self._demo_draw_active = True
            self.btn_draw_demo.setText("⏹️ ปิด Demo")
            self.btn_draw_demo.setStyleSheet(STYLE_DEMO_RED)
            self.btn_draw_demo.setToolTip("คลิกเพื่อปิดการแสดงตัวอย่างสุ่มรางวัลบนหน้าต่าง OBS")

            prize = self.inp_prize.text().strip() or "บัตรกำนัล 500 บาท"
            tier_lbl = self.cmb_draw_group.currentText() or "🏆 สิทธิ์สูงสุด (ผู้มีสิทธิ์ลุ้นรางวัล)"
            candidates = ["LuckyGamer99", "ProViewer", "SakuraGirl", "MegaWin88", "GachaMaster"]
            demo_winner = "StreamerLoyalty99"
            self.service.broadcast_draw_start(prize, tier_lbl, candidates, demo_winner)

            if not hasattr(self, "_demo_draw_timer"):
                self._demo_draw_timer = QTimer(self)
                self._demo_draw_timer.setSingleShot(True)
                self._demo_draw_timer.timeout.connect(self._on_demo_draw_winner_show)
            style = self.cmb_draw_style.currentData() or "gachapon"
            demo_duration = 5700 if style == "slot" else 3400
            self._demo_draw_timer.start(demo_duration)

    def _on_demo_draw_winner_show(self):
        if not getattr(self, "_demo_draw_active", False):
            return
        prize = self.inp_prize.text().strip() or "บัตรกำนัล 500 บาท"
        tier_lbl = self.cmb_draw_group.currentText() or "🏆 ผู้โชคดีได้รับรางวัลใหญ่"
        demo_participant = Participant(
            author="StreamerLoyalty99",
            platform="youtube",
            avatar="",
            checkins={1, 2, 3},
            first_seen=time.time(),
            last_seen=time.time()
        )
        self.service.broadcast_draw_winner(demo_participant, prize, tier_lbl)

    # ── Slot Machine / Lucky Draw Spin ──
    def _start_slot_spin(self):
        if getattr(self, "_demo_draw_active", False):
            self._demo_draw_active = False
            self.btn_draw_demo.setText("🎮 Demo สุ่มรางวัล")
            self.btn_draw_demo.setStyleSheet(STYLE_DRAW_DEMO_NORMAL)
            if hasattr(self, "_demo_draw_timer") and self._demo_draw_timer.isActive():
                self._demo_draw_timer.stop()

        grp_key = self.cmb_draw_group.currentData() or "all"
        groups = self.service.get_tier_groups()
        pool = groups.get(grp_key, groups.get("all", []))

        if self.chk_exclude_previous.isChecked():
            prev = {w.author.lower() for w in self.service.winners_history}
            pool = [p for p in pool if p.author.lower() not in prev]

        if not pool:
            QMessageBox.information(self, "แจ้งเตือน", "ไม่มีรายชื่อผู้มีสิทธิ์ในกลุ่มที่เลือกครับ (หรือได้รับรางวัลไปหมดแล้ว)")
            return

        self._slot_pool = pool
        self._pending_winner = random.choice(pool)
        self.btn_spin.setEnabled(False)
        self.winner_actions_box.setVisible(False)
        self.lbl_slot_status.setText("⚡ กำลังหมุนสุ่มรายชื่อ...")
        self.lbl_slot_status.setStyleSheet("color: #f59e0b; font-size: 13px; font-weight: bold; background: transparent; border: none;")

        # ส่งสัญญาณเริ่มสุ่มไปยัง OBS Overlay พร้อมรายชื่อ candidates และ winner เพื่อให้ Overlay สุ่มเลื่อนอย่างสมูท
        prize = self.inp_prize.text().strip() or "ของรางวัล"
        tier_lbl = self.cmb_draw_group.currentText()
        candidate_names = [p.author for p in pool]
        self.service.broadcast_draw_start(prize, tier_lbl, candidate_names, self._pending_winner.author)

        style = self.cmb_draw_style.currentData() or "gachapon"
        if style == "slot":
            self._slot_ticks_left = 60
            self._slot_timer.setInterval(35)
        else:
            self._slot_ticks_left = 28
            self._slot_timer.setInterval(45)
        self._slot_timer.start()

    def _on_slot_tick(self):
        self._slot_ticks_left -= 1
        style = self.cmb_draw_style.currentData() or "gachapon"
        if self._slot_ticks_left > 0:
            # สุ่มชื่อผู้เข้าร่วมคนอื่นเพื่อสร้างความตื่นเต้นระหว่างสุ่ม
            others = [p for p in self._slot_pool if p.author != self._pending_winner.author]
            candidates = others if others else self._slot_pool
            dummy = random.choice(candidates)
            self.lbl_slot_name.setText(dummy.author)
            self.lbl_slot_name.setStyleSheet("color: #cbd5e1; font-size: 30px; font-weight: 800; background: transparent; border: none;")

            if style == "slot":
                # ชะลอความเร็วแบบตื่นเต้นสำหรับ Shuffle ให้ซิงค์กับ OBS Overlay (+2 วินาที)
                if self._slot_ticks_left <= 1:
                    self._slot_timer.setInterval(750)
                elif self._slot_ticks_left <= 2:
                    self._slot_timer.setInterval(650)
                elif self._slot_ticks_left <= 4:
                    self._slot_timer.setInterval(450)
                elif self._slot_ticks_left <= 7:
                    self._slot_timer.setInterval(280)
                elif self._slot_ticks_left <= 10:
                    self._slot_timer.setInterval(160)
                elif self._slot_ticks_left <= 14:
                    self._slot_timer.setInterval(100)
                elif self._slot_ticks_left <= 18:
                    self._slot_timer.setInterval(60)
            else:
                # ชะลอความเร็วแบบ Dynamic Deceleration สำหรับ Slot Machine / Gacha (~3.4s)
                if self._slot_ticks_left <= 2:
                    self._slot_timer.setInterval(480)
                elif self._slot_ticks_left <= 4:
                    self._slot_timer.setInterval(300)
                elif self._slot_ticks_left <= 7:
                    self._slot_timer.setInterval(190)
                elif self._slot_ticks_left <= 11:
                    self._slot_timer.setInterval(120)
                elif self._slot_ticks_left <= 16:
                    self._slot_timer.setInterval(75)
        else:
            self._slot_timer.stop()
            self._slot_timer.setInterval(45)
            self.btn_spin.setEnabled(True)
            if self._pending_winner:
                self.lbl_slot_status.setText("🎉 ผู้โชคดีได้รับรางวัล! 🎉")
                self.lbl_slot_status.setStyleSheet("color: #10b981; font-size: 13px; font-weight: bold; background: transparent; border: none;")
                self.lbl_slot_name.setText(self._pending_winner.author)
                self.lbl_slot_name.setStyleSheet("color: #38bdf8; font-size: 34px; font-weight: 900; background: transparent; border: none;")
                self.winner_actions_box.setVisible(True)

                # ส่งสัญญาณผู้ชนะขึ้น OBS Overlay เพื่อยืนยันสถานะ
                prize = self.inp_prize.text().strip() or "ของรางวัล"
                tier_lbl = self.cmb_draw_group.currentText()
                self.service.broadcast_draw_winner(self._pending_winner, prize, tier_lbl)

    def _on_confirm_winner(self):
        if not self._pending_winner:
            return
        prize = self.inp_prize.text().strip() or "ของรางวัล"
        tier_lbl = self.cmb_draw_group.currentText()
        self.service.record_winner(self._pending_winner, prize, tier_lbl)

        self.winner_actions_box.setVisible(False)
        self._pending_winner = None
        self.lbl_slot_status.setText("พร้อมหมุนสุ่มรางวัล")
        self.lbl_slot_status.setStyleSheet("color: #a78bfa; font-size: 12.5px; font-weight: 700; background: transparent; border: none;")
        self.lbl_slot_name.setText("ยังไม่เริ่มสุ่ม")
        self.lbl_slot_name.setStyleSheet("color: #94a3b8; font-size: 26px; font-weight: 700; background: transparent; border: none;")
        self._refresh_winners_table()
        self._update_draw_pool_info()

        # ซ่อนเวทีสุ่มบน OBS Overlay
        self.service.broadcast_draw_reset()

    def _copy_obs_url(self):
        port = 8801
        if hasattr(self.service, "parent") and self.service.parent:
            app_inst = self.service.parent
            if hasattr(app_inst, "composer_server") and app_inst.composer_server:
                port = getattr(app_inst.composer_server, "port", 8801)
            elif hasattr(app_inst, "settings"):
                port = getattr(app_inst.settings, "composer_port", 8801)
        url = f"http://localhost:{port}/"
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(url)
        self.btn_copy_obs.setText("✅ คัดลอกสำเร็จ!")
        QTimer.singleShot(2200, lambda: self.btn_copy_obs.setText("📋 คัดลอกลิงก์ OBS"))

    def _refresh_winners_table(self):
        hist = self.service.winners_history
        self.tbl_winners.setRowCount(len(hist))
        for row, w in enumerate(reversed(hist)):
            self.tbl_winners.setItem(row, 0, QTableWidgetItem(w.author))
            self.tbl_winners.setItem(row, 1, QTableWidgetItem(w.platform.capitalize()))
            self.tbl_winners.setItem(row, 2, QTableWidgetItem(w.prize))
            it_t = QTableWidgetItem(w.tier_label)
            it_t.setTextAlignment(Qt.AlignCenter)
            self.tbl_winners.setItem(row, 3, it_t)

    # ═══════════════════════════════════════════════════════════════════
    # EXPORT & CLEAR FLOW: [Export File] [ลบทันที] [ไม่ลบ]
    # ═══════════════════════════════════════════════════════════════════
    def _export_csv_directly(self):
        """ส่งออกไฟล์ Excel CSV โดยตรงจากปุ่มซ้ายล่าง"""
        total = len(self.service.participants)
        if total == 0:
            QMessageBox.information(self, "แจ้งเตือน", "ยังไม่มีข้อมูลผู้เข้าร่วมสำหรับส่งออกครับ")
            return

        def_name = f"giveaway_participants_{time.strftime('%Y%m%d_%H%M')}.csv"
        file_path, _ = QFileDialog.getSaveFileName(
            self, "บันทึกไฟล์รายชื่อผู้เข้าร่วม (Excel CSV)",
            def_name, "CSV Files (*.csv)"
        )
        if not file_path:
            return

        ok = self.service.export_csv(file_path)
        if ok:
            QMessageBox.information(self, "สำเร็จ", f"✅ ส่งออกไฟล์เรียบร้อยแล้วที่:\n{file_path}")
        else:
            QMessageBox.critical(self, "เกิดข้อผิดพลาด", "ไม่สามารถส่งออกไฟล์ได้ กรุณาลองใหม่อีกครั้งครับ")

    def _export_winners_csv_directly(self):
        """ส่งออกไฟล์ Excel CSV เฉพาะทำเนียบผู้ได้รับรางวัล"""
        if not self.service.winners_history:
            QMessageBox.information(self, "แจ้งเตือน", "ยังไม่มีรายชื่อผู้ได้รับรางวัลในทำเนียบครับ")
            return

        def_name = f"giveaway_winners_{time.strftime('%Y%m%d_%H%M')}.csv"
        file_path, _ = QFileDialog.getSaveFileName(
            self, "บันทึกไฟล์ทำเนียบผู้ได้รับรางวัล (Excel CSV)",
            def_name, "CSV Files (*.csv)"
        )
        if not file_path:
            return

        ok = self.service.export_winners_csv(file_path)
        if ok:
            QMessageBox.information(self, "สำเร็จ", f"✅ ส่งออกรายชื่อผู้ได้รับรางวัลเรียบร้อยแล้วที่:\n{file_path}")
        else:
            QMessageBox.critical(self, "เกิดข้อผิดพลาด", "ไม่สามารถส่งออกไฟล์ได้ กรุณาลองใหม่อีกครั้งครับ")

    def _clear_winners_history(self):
        """ล้างเฉพาะทำเนียบผู้ได้รับรางวัล"""
        if not self.service.winners_history:
            return
        reply = QMessageBox.question(
            self,
            "ยืนยันการล้างข้อมูล",
            "คุณต้องการล้างทำเนียบผู้ได้รับรางวัลทั้งหมดใช่หรือไม่?\n(รายชื่อผู้เข้าร่วมสะสมแต้มจะยังคงอยู่ครบถ้วนเหมือนเดิม)",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.service.winners_history.clear()
            self._refresh_winners_table()
            self._update_draw_pool_info()

    def _open_clear_dialog(self):
        total = len(self.service.participants)
        if total == 0:
            QMessageBox.information(self, "แจ้งเตือน", "ยังไม่มีข้อมูลผู้เข้าร่วมกิจกรรมครับ")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("จัดการข้อมูลกิจกรรม")
        dlg.setFixedWidth(440)
        dlg.setStyleSheet("""
            QDialog { background-color: #0b1120; border: 1px solid #1e293b; }
            QLabel { color: #f8fafc; font-size: 13px; }
            QPushButton { border-radius: 4px; padding: 9px 16px; font-weight: bold; font-size: 13px; }
        """)

        d_layout = QVBoxLayout(dlg)
        d_layout.setContentsMargins(20, 20, 20, 20)
        d_layout.setSpacing(14)

        icon_title = QLabel("⚠️ จัดการข้อมูลผู้เข้าร่วมกิจกรรม")
        icon_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #f59e0b;")
        d_layout.addWidget(icon_title)

        desc = QLabel(f"ปัจจุบันมีข้อมูลผู้เข้าร่วมกิจกรรมทั้งหมด <b>{total} คน</b><br>คุณต้องการส่งออกข้อมูลหรือล้างข้อมูลเพื่อเริ่มใหม่?")
        desc.setWordWrap(True)
        d_layout.addWidget(desc)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        btn_export = QPushButton("💾 Export ไฟล์ Excel")
        btn_export.setStyleSheet("background-color: #0284c7; color: white; border: none;")
        btn_export.clicked.connect(lambda: self._handle_export_and_prompt(dlg))

        btn_delete = QPushButton("🗑️ ลบทันที")
        btn_delete.setStyleSheet("background-color: #dc2626; color: white; border: none;")
        btn_delete.clicked.connect(lambda: self._execute_delete(dlg))

        btn_cancel = QPushButton("ยกเลิก")
        btn_cancel.setStyleSheet("background-color: #162032; border: 1px solid #283548; color: #cbd5e1;")
        btn_cancel.clicked.connect(dlg.reject)

        btn_row.addWidget(btn_export)
        btn_row.addWidget(btn_delete)
        btn_row.addWidget(btn_cancel)
        d_layout.addLayout(btn_row)

        dlg.exec()

    def _handle_export_and_prompt(self, parent_dlg: QDialog):
        def_name = f"giveaway_participants_{time.strftime('%Y%m%d_%H%M')}.csv"
        file_path, _ = QFileDialog.getSaveFileName(
            self, "บันทึกไฟล์รายชื่อผู้เข้าร่วม (Excel CSV)",
            def_name, "CSV Files (*.csv)"
        )
        if not file_path:
            return

        ok = self.service.export_csv(file_path)
        if ok:
            parent_dlg.accept()
            ret = QMessageBox.question(
                self, "Export สำเร็จแล้ว",
                f"✅ ส่งออกไฟล์เรียบร้อยแล้วที่:\n{file_path}\n\nคุณต้องการลบข้อมูลกิจกรรมในโปรแกรมเพื่อเริ่มใหม่เลยหรือไม่?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if ret == QMessageBox.Yes:
                self.service.clear_all_data()
        else:
            QMessageBox.critical(self, "เกิดข้อผิดพลาด", "ไม่สามารถส่งออกไฟล์ได้ กรุณาลองใหม่อีกครั้งครับ")

    def _execute_delete(self, parent_dlg: QDialog):
        self.service.clear_all_data()
        parent_dlg.accept()
        QMessageBox.information(self, "สำเร็จ", "ล้างข้อมูลกิจกรรมทั้งหมดเรียบร้อยแล้วครับ")

    def _on_service_data_cleared(self):
        self._update_stats_display()
        self._refresh_participants_table()
        self._refresh_winners_table()
        self._update_draw_pool_info()
        self.lbl_slot_name.setText("ยังไม่เริ่มสุ่ม")
        self.lbl_slot_name.setStyleSheet("color: #94a3b8; font-size: 26px; font-weight: 700; background: transparent; border: none;")
        self.winner_actions_box.setVisible(False)
        self._pending_winner = None

    def closeEvent(self, event):
        if getattr(self, "_demo_draw_active", False):
            self._demo_draw_active = False
            self.btn_draw_demo.setText("🎮 Demo สุ่มรางวัล")
            self.btn_draw_demo.setStyleSheet(STYLE_DRAW_DEMO_NORMAL)
            if hasattr(self, "_demo_draw_timer") and self._demo_draw_timer.isActive():
                self._demo_draw_timer.stop()
            self.service.broadcast_draw_reset()
        if getattr(self, "_demo_active", False):
            self._demo_active = False
            self.btn_demo.setText("🎮 Demo")
            self.btn_demo.setStyleSheet(STYLE_DEMO_NORMAL)
            self.service.trigger_preview({"action": "stop", "show": False})
        self.closed.emit()
        super().closeEvent(event)
