# -*- coding: utf-8 -*-

"""

giveaway_panel.py

หน้าต่างแผงควบคุมระบบ Giveaway (Loyalty Giveaway)

ดีไซน์ Flat UI สะอาดตา ไม่ใช้กรอบซ้อนกรอบ รองรับขนาดหน้าจอทุกระดับ ไม่ล้น ไม่ตกขอบ

แบ่ง 3 แท็บหลัก:

1. ควบคุมสด (Live Wizard): Step 1 เลือกกติกา -> Step 2 เปิดรับโค้ดสด -> Step 3 สุ่มรางวัล

2. กติกาคนเข้าร่วม (Participant Presets): ตั้งค่าด่าน โค้ด เวลา และการแสดงผลบน OBS

3. ข้อมูลของรางวัล (Prize Sets): กำหนดชุดของรางวัลและผูกกับกติกา

"""



import os

import sys

import time

import random

import logging

from typing import Optional, List, Dict, Any



from PySide6.QtCore import Qt, QTimer, Signal

from PySide6.QtGui import QFont, QCursor, QColor

from PySide6.QtWidgets import (

    QApplication, QWidget, QFrame, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,

    QPushButton, QLineEdit, QComboBox, QListView, QSpinBox, QSlider, QProgressBar,

    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QFileDialog,

    QStackedWidget, QScrollArea, QDialog, QRadioButton, QButtonGroup

)



from giveaway_service import GiveawayService, Participant

from giveaway_preset_manager import GiveawayPresetManager



logger = logging.getLogger(__name__)



# --- STYLES ---

STYLE_BTN_PRIMARY = """

QPushButton {

    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2563eb, stop:1 #1d4ed8);

    border: 1px solid #3b82f6;

    border-radius: 7px;

    color: #ffffff;

    font-size: 13px;

    font-weight: 700;

    padding: 8px 16px;

}

QPushButton:hover { background: #3b82f6; }

QPushButton:pressed { background: #1e40af; }

"""



STYLE_BTN_SUCCESS = """

QPushButton {

    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #059669, stop:1 #047857);

    border: 1px solid #10b981;

    border-radius: 8px;

    color: #ffffff;

    font-size: 14px;

    font-weight: 800;

    padding: 11px 18px;

}

QPushButton:hover { background: #10b981; }

QPushButton:pressed { background: #065f46; }

"""



STYLE_BTN_DANGER = """

QPushButton {

    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #dc2626, stop:1 #b91c1c);

    border: 1px solid #ef4444;

    border-radius: 8px;

    color: #ffffff;

    font-size: 13.5px;

    font-weight: 800;

    padding: 10px 18px;

}

QPushButton:hover { background: #ef4444; }

QPushButton:pressed { background: #991b1b; }

"""



STYLE_BTN_SECONDARY = """

QPushButton {

    background-color: #1e293b;

    border: 1px solid #334155;

    border-radius: 6px;

    color: #cbd5e1;

    font-size: 12px;

    font-weight: 600;

    padding: 6px 12px;

}

QPushButton:hover {

    background-color: #334155;

    border-color: #475569;

    color: #ffffff;

}

QPushButton:pressed { background-color: #0f172a; }

"""



STYLE_SPIN_BTN = """

QPushButton {

    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f59e0b, stop:1 #d97706);

    border: 2px solid #fbbf24;

    border-radius: 8px;

    color: #0b1120;

    font-size: 15px;

    font-weight: 900;

    padding: 12px 18px;

}

QPushButton:hover { background: #fbbf24; border-color: #fef08a; }

QPushButton:pressed { background: #b45309; }

"""





class RoundNameDialog(QDialog):

    """ไดอะล็อกเปลี่ยนชื่อรอบกิจกรรม"""

    def __init__(self, title: str, default_name: str, parent: Optional[QWidget] = None):

        super().__init__(parent)

        self.setWindowTitle(title)

        self.setFixedSize(360, 150)

        self.setStyleSheet("background-color: #0b1120; color: #f8fafc;")



        layout = QVBoxLayout(self)

        layout.setContentsMargins(18, 16, 18, 16)

        layout.setSpacing(12)



        lbl = QLabel("ระบุชื่อรอบกิจกรรม:", self)

        lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #cbd5e1;")

        layout.addWidget(lbl)



        self.inp_name = QLineEdit(self)

        self.inp_name.setText(default_name)

        self.inp_name.setStyleSheet("""

            QLineEdit {

                background-color: #162032;

                border: 1.5px solid #283548;

                border-radius: 6px;

                color: #ffffff;

                font-size: 13.5px;

                padding: 6px 10px;

            }

            QLineEdit:focus { border-color: #3b82f6; }

        """)

        layout.addWidget(self.inp_name)



        btn_box = QHBoxLayout()

        btn_box.setSpacing(8)

        self.btn_ok = QPushButton("ตกลง", self)

        self.btn_ok.setStyleSheet(STYLE_BTN_PRIMARY)

        self.btn_ok.clicked.connect(self.accept)

        self.btn_cancel = QPushButton("ยกเลิก", self)

        self.btn_cancel.setStyleSheet(STYLE_BTN_SECONDARY)

        self.btn_cancel.clicked.connect(self.reject)

        btn_box.addStretch()

        btn_box.addWidget(self.btn_cancel)

        btn_box.addWidget(self.btn_ok)

        layout.addLayout(btn_box)



    def get_name(self) -> str:

        return self.inp_name.text().strip()





def _get_asset_path(filename: str) -> str:
    import os, sys
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        p = os.path.join(exe_dir, "_internal", "assets", filename)
        if not os.path.exists(p):
            p = os.path.join(exe_dir, "assets", filename)
    else:
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        p = os.path.join(root, "assets", filename)
    return p.replace(chr(92), "/")

class GiveawayPanel(QFrame):

    """หน้าต่างแผงควบคุมระบบ Giveaway สไตล์ Flat สะอาดตา ไร้กรอบซ้อนกรอบ"""

    closed = Signal()



    def __init__(self, service: GiveawayService, parent: Optional[QWidget] = None):

        super().__init__(parent)

        self.service = service

        self.preset_mgr = GiveawayPresetManager()

        self.setObjectName("GiveawayPanel")

        self.setWindowTitle("🎁 Giveaway Tool — ระบบสุ่มแจกรางวัล")

        self.resize(680, 840)

        self.setMinimumSize(540, 560)

        self.setWindowFlags(Qt.Window | Qt.WindowCloseButtonHint | Qt.WindowMinMaxButtonsHint)



        # Timers

        self._timer = QTimer(self)

        self._timer.setInterval(250)

        self._timer.timeout.connect(self._on_timer_tick)



        # Slot animation timer

        self._slot_timer = QTimer(self)

        self._slot_timer.setInterval(50)

        self._slot_timer.timeout.connect(self._on_slot_tick)

        self._slot_ticks_left = 0

        self._slot_candidates: List[str] = []

        self._pending_winner_name = ""

        # Test Draw state & timer
        self._is_obs_demo_active: bool = False
        self._is_draw_demo_active: bool = False
        self._draw_demo_timer = QTimer(self)
        self._draw_demo_timer.setSingleShot(True)
        self._draw_demo_timer.timeout.connect(self._on_draw_demo_timeout)



        # Runtime states

        self.current_live_step = 1

        self.active_participant_preset: Dict[str, Any] = {}

        self.active_prize_set: Optional[Dict[str, Any]] = None

        self.live_duration_sec: int = 300

        self.current_checkpoint_idx: int = 1

        self.realtime_participants_count: int = 0

        self.draw_history: List[Dict[str, Any]] = []



        self._init_qss()

        self._build_ui()

        self._connect_service_signals()



        # Load initial preset into live mode

        self._load_initial_live_presets()



        # Periodic check for OBS Overlay installation

        self._widget_check_timer = QTimer(self)

        self._widget_check_timer.setInterval(1500)

        self._widget_check_timer.timeout.connect(self._check_widget_status)

        self._widget_check_timer.start()

        self._check_widget_status()



    def _setup_combobox(self, combo: QComboBox):

        """ตั้งค่า QListView และ StrongFocus เพื่อให้คลิกครั้งเดียวเลือกได้ทันที ไม่หน่วง"""

        combo.setView(QListView())

        combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)

        combo.setMinimumContentsLength(6)



    def _init_qss(self):

        
        arrow_img = _get_asset_path("arrow_down.png")
        arrow_disabled_img = _get_asset_path("arrow_down_disabled.png")
        self.setStyleSheet("""

            QFrame#GiveawayPanel {

                background-color: #0b1120;

                border: 1px solid #1e293b;

            }

            QLabel {

                color: #e2e8f0;

                font-size: 13px;

                background: transparent;

            }

            QMessageBox {

                background-color: #0b1120;

            }

            QMessageBox QLabel {

                color: #f8fafc;

                font-size: 13px;

            }

            QMessageBox QPushButton {

                background-color: #2563eb;

                color: #ffffff;

                border-radius: 6px;

                padding: 6px 14px;

                font-weight: bold;

            }

            QComboBox {

                background-color: #162032;

                border: 1px solid #283548;

                border-radius: 6px;

                color: #f8fafc;

                font-size: 13px;

                padding: 6px 10px;

                min-height: 24px;

            }

            QComboBox:focus, QComboBox:hover {

                border-color: #3b82f6;

            }

            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 28px;
                border: none;
                background: transparent;
            }

            QComboBox::down-arrow {
                image: url("__ARROW_DOWN_IMG__");
                width: 12px;
                height: 8px;
                margin-right: 8px;
                border: none;
                background: transparent;
            }

            QComboBox::down-arrow:disabled {
                image: url("__ARROW_DOWN_DISABLED_IMG__");
                border: none;
                background: transparent;
            }

            QComboBox QAbstractItemView {

                background-color: #111827;

                border: 1px solid #334155;

                border-radius: 6px;

                color: #f8fafc;

                selection-background-color: #2563eb;

                selection-color: #ffffff;

                outline: none;

            }

            QComboBox QAbstractItemView::item {

                min-height: 30px;

                padding: 4px 10px;

                color: #f8fafc;

            }

            QComboBox QAbstractItemView::item:selected {

                background-color: #2563eb;

                color: #ffffff;

            }

            QLineEdit {

                background-color: #162032;

                border: 1px solid #283548;

                border-radius: 6px;

                color: #f8fafc;

                font-size: 13px;

                padding: 6px 10px;

            }

            QLineEdit:focus {

                border-color: #3b82f6;

            }

            QSpinBox {

                background-color: #162032;

                border: 1.5px solid #283548;

                border-radius: 6px;

                color: #38bdf8;

                font-size: 14px;

                font-weight: 700;

                min-height: 28px;

            }

            QSpinBox:focus {

                border-color: #38bdf8;

                background-color: #1e293b;

            }

            QSlider::groove:horizontal {

                height: 6px;

                background: #1e293b;

                border-radius: 3px;

            }

            QSlider::sub-page:horizontal {

                background: #38bdf8;

                border-radius: 3px;

            }

            QSlider::handle:horizontal {

                background: #ffffff;

                border: 2px solid #0284c7;

                width: 14px;

                margin-top: -5px;

                margin-bottom: -5px;

                border-radius: 7px;

            }

            QTableWidget {

                background-color: #0f172a;

                border: 1px solid #1e293b;

                border-radius: 6px;

                gridline-color: #1e293b;

                color: #e2e8f0;

                font-size: 12px;

            }

            QHeaderView::section {

                background-color: #162032;

                color: #94a3b8;

                border: none;

                border-bottom: 1px solid #1e293b;

                padding: 6px 8px;

                font-weight: bold;

            }

            QRadioButton {

                color: #cbd5e1;

                font-size: 13px;

                spacing: 8px;

            }

            QRadioButton:hover {

                color: #f8fafc;

            }

            QRadioButton::indicator {

                width: 16px;

                height: 16px;

            }

        """.replace("__ARROW_DOWN_IMG__", arrow_img).replace("__ARROW_DOWN_DISABLED_IMG__", arrow_disabled_img))



    # ─────────────────────────────────────────────────────────────

    # BUILD UI

    # ─────────────────────────────────────────────────────────────

    def _build_ui(self):

        root_layout = QVBoxLayout(self)

        root_layout.setContentsMargins(0, 0, 0, 0)

        root_layout.setSpacing(0)



        # Stack for installed vs not-installed

        self.stack = QStackedWidget(self)

        root_layout.addWidget(self.stack)



        # Index 0: Main Application Container

        self.main_container = QWidget()

        self._build_main_container_ui(self.main_container)

        self.stack.addWidget(self.main_container)



        # Index 1: Not installed blocker

        self.blocker_widget = self._build_not_installed_view()

        self.stack.addWidget(self.blocker_widget)



    def _build_main_container_ui(self, container: QWidget):

        layout = QVBoxLayout(container)

        layout.setContentsMargins(14, 12, 14, 12)

        layout.setSpacing(10)



        # ── Header Bar ──

        header = QHBoxLayout()

        header.setSpacing(10)



        lbl_icon = QLabel("🎁")

        lbl_icon.setStyleSheet("font-size: 24px;")

        header.addWidget(lbl_icon)



        v_titles = QVBoxLayout()

        v_titles.setSpacing(2)

        lbl_title = QLabel("Giveaway Tool")

        lbl_title.setStyleSheet("font-size: 16px; font-weight: 800; color: #ffffff;")

        self.lbl_sub = QLabel("ระบบสุ่มรายชื่อผู้โชคดี & สุ่มกิจกรรมคนดู")

        self.lbl_sub.setStyleSheet("font-size: 11.5px; color: #94a3b8;")

        v_titles.addWidget(lbl_title)

        v_titles.addWidget(self.lbl_sub)

        header.addLayout(v_titles)



        header.addStretch()



        self.btn_copy_link = QPushButton("📋 ลิงก์ OBS")

        self.btn_copy_link.setStyleSheet(STYLE_BTN_SECONDARY)

        self.btn_copy_link.setToolTip("คัดลอกลิงก์สำหรับใส่ใน OBS Browser Source")

        self.btn_copy_link.setCursor(Qt.PointingHandCursor)

        self.btn_copy_link.clicked.connect(self._on_copy_obs_link)

        header.addWidget(self.btn_copy_link)



        layout.addLayout(header)



        # ── Mode Navigation Tabs (Flat Pill Bar) ──

        nav_box = QHBoxLayout()

        nav_box.setSpacing(6)



        self.btn_nav_live = QPushButton("📺 ควบคุมสด")

        self.btn_nav_live.setCursor(Qt.PointingHandCursor)

        self.btn_nav_live.setStyleSheet(STYLE_BTN_PRIMARY)

        self.btn_nav_live.clicked.connect(lambda: self._switch_main_mode(0))



        self.btn_nav_participant = QPushButton("🎨 ตกแต่ง Overlay")

        self.btn_nav_participant.setCursor(Qt.PointingHandCursor)

        self.btn_nav_participant.setStyleSheet(STYLE_BTN_SECONDARY)

        self.btn_nav_participant.clicked.connect(lambda: self._switch_main_mode(1))

        nav_box.addWidget(self.btn_nav_live, 1)

        nav_box.addWidget(self.btn_nav_participant, 1)

        layout.addLayout(nav_box)



        # ── Main Stack for 3 Modes ──

        self.main_stack = QStackedWidget()

        layout.addWidget(self.main_stack, 1)



        # Page 0: Live Wizard

        self.page_live = QWidget()

        self._build_live_wizard_ui(self.page_live)

        self.main_stack.addWidget(self.page_live)



        # Page 1: Participant Preset Setup

        self.page_participant = QWidget()

        self._build_participant_preset_ui(self.page_participant)

        self.main_stack.addWidget(self.page_participant)



    def _on_copy_obs_link(self):
        url = "http://localhost:8080/giveaway_overlay.html"
        QApplication.clipboard().setText(url)
        QMessageBox.information(self, "คัดลอกสำเร็จ", f"คัดลอกลิงก์สำหรับใส่ OBS Browser Source เรียบร้อยแล้วครับ:\n\n{url}")

    def _switch_main_mode(self, idx: int):
        self.main_stack.setCurrentIndex(idx)
        btns = [self.btn_nav_live, self.btn_nav_participant]
        for i, b in enumerate(btns):
            if i == idx:
                b.setStyleSheet(STYLE_BTN_PRIMARY)
            else:
                b.setStyleSheet(STYLE_BTN_SECONDARY)

        if idx == 0:
            self._load_initial_live_presets()
        elif idx == 1:
            self._reload_participant_preset_dropdown()



    # ─────────────────────────────────────────────────────────────

    # PAGE 0: LIVE WIZARD (ควบคุมสด)

    # ─────────────────────────────────────────────────────────────

    def _build_live_wizard_ui(self, parent: QWidget):

        vbox = QVBoxLayout(parent)

        vbox.setContentsMargins(0, 4, 0, 0)

        vbox.setSpacing(8)



        # Stepper bar

        self.stepper_box = QHBoxLayout()

        self.stepper_box.setSpacing(6)

        self.step_btn_1 = QLabel("1. เลือกกติกา")

        self.step_btn_2 = QLabel("2. เปิดรับโค้ดสด")

        self.step_btn_3 = QLabel("3. สุ่มผู้โชคดี")

        for s in (self.step_btn_1, self.step_btn_2, self.step_btn_3):

            s.setAlignment(Qt.AlignCenter)

            s.setFixedHeight(28)

        self._update_live_stepper_style(1)

        self.stepper_box.addWidget(self.step_btn_1, 1)

        self.stepper_box.addWidget(QLabel("➔"))

        self.stepper_box.addWidget(self.step_btn_2, 1)

        self.stepper_box.addWidget(QLabel("➔"))

        self.stepper_box.addWidget(self.step_btn_3, 1)

        vbox.addLayout(self.stepper_box)



        # Scrollable container for live steps (ensures zero overflow / clipping)

        scroll = QScrollArea()

        scroll.setWidgetResizable(True)

        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")



        self.live_step_stack = QStackedWidget()

        scroll.setWidget(self.live_step_stack)

        vbox.addWidget(scroll, 1)



        # Step 1: Select Preset

        self.step1_widget = QWidget()

        self._build_live_step1_ui(self.step1_widget)

        self.live_step_stack.addWidget(self.step1_widget)



        # Step 2: Code Reception (Live)

        self.step2_widget = QWidget()

        self._build_live_step2_ui(self.step2_widget)

        self.live_step_stack.addWidget(self.step2_widget)



        # Step 3: Draw Stage

        self.step3_widget = QWidget()

        self._build_live_step3_ui(self.step3_widget)

        self.live_step_stack.addWidget(self.step3_widget)



    def _update_live_stepper_style(self, active_step: int):

        qss_active = "background: #2563eb; color: #ffffff; font-weight: bold; border-radius: 6px; font-size: 12px;"

        qss_done = "background: #064e3b; color: #34d399; font-weight: bold; border-radius: 6px; font-size: 12px;"

        qss_inactive = "background: #162032; color: #64748b; border-radius: 6px; font-size: 12px;"



        self.step_btn_1.setStyleSheet(qss_active if active_step == 1 else (qss_done if active_step > 1 else qss_inactive))

        self.step_btn_2.setStyleSheet(qss_active if active_step == 2 else (qss_done if active_step > 2 else qss_inactive))

        self.step_btn_3.setStyleSheet(qss_active if active_step == 3 else qss_inactive)



    # ── Live Step 1 UI ──

    def _build_live_step1_ui(self, widget: QWidget):

        cv = QVBoxLayout(widget)

        cv.setContentsMargins(4, 8, 4, 8)

        cv.setSpacing(12)



        lbl_s1 = QLabel("🎯 ขั้นตอนที่ 1: เลือกกติกาสำหรับกิจกรรมรอบนี้")

        lbl_s1.setStyleSheet("font-size: 14.5px; font-weight: 800; color: #ffffff;")

        cv.addWidget(lbl_s1)



        lbl_desc = QLabel("เลือกรูปแบบคำสั่งและระยะเวลาที่ใช้เปิดรับรายชื่อผู้เข้าร่วมกิจกรรม")

        lbl_desc.setStyleSheet("font-size: 12px; color: #94a3b8;")

        cv.addWidget(lbl_desc)



        cv.addWidget(QLabel("เลือกรูปแบบคำสั่ง / Preset ที่ใช้ร่วมสนุก:"))

        self.cmb_live_participant_preset = QComboBox()

        self._setup_combobox(self.cmb_live_participant_preset)

        self.cmb_live_participant_preset.currentIndexChanged.connect(self._on_live_preset_selected)

        self.cmb_live_participant_preset.activated.connect(self._on_live_preset_selected)

        cv.addWidget(self.cmb_live_participant_preset)



        



        cv.addStretch()



        btn_start_live = QPushButton("🚀 เริ่มเปิดกิจกรรมถ่ายทอดสด (เข้าสู่ห้องรับโค้ด)")

        btn_start_live.setStyleSheet(STYLE_BTN_SUCCESS)

        btn_start_live.setCursor(Qt.PointingHandCursor)

        btn_start_live.clicked.connect(self._start_live_from_step1)

        cv.addWidget(btn_start_live)



    def _load_initial_live_presets(self):

        self.cmb_live_participant_preset.blockSignals(True)

        self.cmb_live_participant_preset.clear()

        presets = self.preset_mgr.get_participant_presets()

        for p in presets:

            self.cmb_live_participant_preset.addItem(p.get("name", "Preset"), p.get("id"))

        self.cmb_live_participant_preset.blockSignals(False)



        if presets:

            self._on_live_preset_selected(0)



    def _on_live_preset_selected(self, idx: int):

        p_id = self.cmb_live_participant_preset.currentData()

        p = self.preset_mgr.get_participant_preset(p_id)

        if not p:

            return



        self.active_participant_preset = p

        p_name = p.get("name", "")

        pass

    def _start_live_from_step1(self):

        preset = self.active_participant_preset

        if not preset:

            QMessageBox.warning(self, "แจ้งเตือน", "กรุณาเลือกกติกาคนเข้าร่วมก่อนครับ")

            return



        # Setup service mode

        mode = preset.get("mode", "single")

        self.service.mode = mode

        if mode == "single":

            self.service.total_checkpoints = 1

            self.service.checkpoint_names = {1: preset.get("name", "สุ่มแจกรางวัล")}

            self.service.checkpoint_codes = {1: preset.get("code", "#join")}

        else:

            cps = preset.get("checkpoints", [])

            self.service.total_checkpoints = len(cps)

            self.service.checkpoint_names = {cp.get("index", i+1): cp.get("name", f"รอบที่ {i+1}") for i, cp in enumerate(cps)}

            self.service.checkpoint_codes = {cp.get("index", i+1): cp.get("code", f"#join{i+1}") for i, cp in enumerate(cps)}



        # Sync overlay display settings to service

        self.service.update_overlay_settings(
            overlay_display_mode=preset.get("overlay_display_mode", "banner"),
            overlay_scale=preset.get("overlay_scale", 100),
            overlay_font_size=preset.get("overlay_font_size", 100),
            overlay_offset_x=preset.get("overlay_offset_x", 0),
            overlay_offset_y=preset.get("overlay_offset_y", 0),
            custom_image_path=preset.get("custom_image_path", ""),
            draw_animation_style=preset.get("draw_animation_style", "gachapon"),
            draw_theme=preset.get("draw_theme", "gold"),
            draw_scale=preset.get("draw_scale", 100),
            draw_name_size=preset.get("draw_name_size", 52),
            draw_offset_x=preset.get("draw_offset_x", 0),
            draw_offset_y=preset.get("draw_offset_y", 0),
            draw_autohide_sec=preset.get("draw_autohide_sec", 15)
        )



        # Clear previous live round data safely

        self.service.clear_all_data()

        self.current_checkpoint_idx = 1

        self.draw_history = []

        self.realtime_participants_count = 0

        self.tbl_draw_history.setRowCount(0)



        # Move to Step 2

        self._setup_live_step2_display()

        self.current_live_step = 2

        self.live_step_stack.setCurrentIndex(1)

        self._update_live_stepper_style(2)



    # ── Live Step 2 UI (เปิดรับโค้ดสด) ──

    def _build_live_step2_ui(self, widget: QWidget):

        cv = QVBoxLayout(widget)

        cv.setContentsMargins(4, 6, 4, 6)

        cv.setSpacing(10)



        # Round Header

        hdr = QHBoxLayout()

        hdr.setSpacing(8)

        self.lbl_live_round_badge = QLabel("ด่านที่ 1")

        self.lbl_live_round_badge.setStyleSheet("background: #1e3a8a; color: #60a5fa; font-weight: bold; border-radius: 4px; padding: 3px 8px; font-size: 11px;")

        hdr.addWidget(self.lbl_live_round_badge)

        self.lbl_live_round_title = QLabel("📍 เปิดรับโค้ดรอบที่ 1")

        self.lbl_live_round_title.setStyleSheet("font-size: 15px; font-weight: 800; color: #ffffff;")

        hdr.addWidget(self.lbl_live_round_title)

        hdr.addStretch()



        hdr_code = QHBoxLayout()

        hdr_code.setSpacing(6)

        lbl_c_hint = QLabel("โค้ด:")

        lbl_c_hint.setStyleSheet("font-size: 12px; color: #94a3b8;")

        self.lbl_live_code = QLabel("#join")

        self.lbl_live_code.setStyleSheet("font-size: 16px; font-weight: 900; color: #f59e0b; background: #162032; padding: 2px 10px; border-radius: 6px; font-family: monospace;")

        hdr_code.addWidget(lbl_c_hint)

        hdr_code.addWidget(self.lbl_live_code)

        hdr.addLayout(hdr_code)

        cv.addLayout(hdr)



        # Duration Quick Buttons (Clean 2-row layout -> ZERO horizontal overflow!)

        dhdr = QHBoxLayout()

        dhdr.addWidget(QLabel("⏱️ กำหนดเวลาเปิดรับรอบนี้:"))

        self.lbl_live_time_preview = QLabel("5 นาที 00 วินาที")

        self.lbl_live_time_preview.setStyleSheet("color: #38bdf8; font-weight: bold;")

        dhdr.addStretch()

        dhdr.addWidget(self.lbl_live_time_preview)

        cv.addLayout(dhdr)



        d_grid = QGridLayout()

        d_grid.setSpacing(6)

        self.btn_dur_preset = QPushButton("ใช้ตาม Preset")

        self.btn_dur_1m = QPushButton("1 นาที")

        self.btn_dur_5m = QPushButton("5 นาที")

        self.btn_dur_10m = QPushButton("10 นาที")

        self.btn_dur_custom = QPushButton("⚙️ กำหนดเวลาเอง...")



        for b in (self.btn_dur_preset, self.btn_dur_1m, self.btn_dur_5m, self.btn_dur_10m, self.btn_dur_custom):

            b.setCursor(Qt.PointingHandCursor)

            b.setStyleSheet(STYLE_BTN_SECONDARY)



        self.btn_dur_preset.clicked.connect(lambda: self._set_live_quick_time(self.active_participant_preset.get("duration_sec", 300), "ใช้ตาม Preset"))

        self.btn_dur_1m.clicked.connect(lambda: self._set_live_quick_time(60, "1 นาที"))

        self.btn_dur_5m.clicked.connect(lambda: self._set_live_quick_time(300, "5 นาที"))

        self.btn_dur_10m.clicked.connect(lambda: self._set_live_quick_time(600, "10 นาที"))

        self.btn_dur_custom.clicked.connect(self._toggle_custom_time_drawer)



        d_grid.addWidget(self.btn_dur_preset, 0, 0)

        d_grid.addWidget(self.btn_dur_1m, 0, 1)

        d_grid.addWidget(self.btn_dur_5m, 0, 2)

        d_grid.addWidget(self.btn_dur_10m, 1, 0)

        d_grid.addWidget(self.btn_dur_custom, 1, 1, 1, 2)

        cv.addLayout(d_grid)



        # Custom Drawer (Digital Clock Pill)

        self.drawer_custom_time = QFrame()

        self.drawer_custom_time.setObjectName("CustTimeCard")

        self.drawer_custom_time.setVisible(False)

        self.drawer_custom_time.setStyleSheet("""

            QFrame#CustTimeCard {

                background-color: #131d31;

                border: 1px solid #1e293b;

                border-radius: 8px;

            }

            QSpinBox {

                background-color: #0b1120;

                border: 1px solid #283548;

                border-radius: 6px;

                color: #38bdf8;

                font-size: 14px;

                font-weight: 800;

                min-height: 28px;

                max-height: 28px;

            }

            QSpinBox:focus {

                border-color: #38bdf8;

                background-color: #0e1726;

            }

            QLabel {

                border: none;

                background: transparent;

            }

        """)

        cust_layout = QHBoxLayout(self.drawer_custom_time)

        cust_layout.setContentsMargins(10, 6, 10, 6)

        cust_layout.setSpacing(6)



        self.spin_cust_hr = QSpinBox()

        self.spin_cust_hr.setButtonSymbols(QSpinBox.NoButtons)

        self.spin_cust_hr.setRange(0, 24)

        self.spin_cust_hr.setFixedWidth(44)

        self.spin_cust_hr.setAlignment(Qt.AlignCenter)

        cust_layout.addWidget(self.spin_cust_hr)

        lbl_c_hr = QLabel("ชม.")

        lbl_c_hr.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: bold;")

        cust_layout.addWidget(lbl_c_hr)

        sep_c1 = QLabel(":")

        sep_c1.setStyleSheet("color: #475569; font-weight: bold;")

        cust_layout.addWidget(sep_c1)



        self.spin_cust_min = QSpinBox()

        self.spin_cust_min.setButtonSymbols(QSpinBox.NoButtons)

        self.spin_cust_min.setRange(0, 59)

        self.spin_cust_min.setValue(5)

        self.spin_cust_min.setFixedWidth(44)

        self.spin_cust_min.setAlignment(Qt.AlignCenter)

        cust_layout.addWidget(self.spin_cust_min)

        lbl_c_min = QLabel("นาที")

        lbl_c_min.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: bold;")

        cust_layout.addWidget(lbl_c_min)

        sep_c2 = QLabel(":")

        sep_c2.setStyleSheet("color: #475569; font-weight: bold;")

        cust_layout.addWidget(sep_c2)



        self.spin_cust_sec = QSpinBox()

        self.spin_cust_sec.setButtonSymbols(QSpinBox.NoButtons)

        self.spin_cust_sec.setRange(0, 59)

        self.spin_cust_sec.setFixedWidth(44)

        self.spin_cust_sec.setAlignment(Qt.AlignCenter)

        cust_layout.addWidget(self.spin_cust_sec)

        lbl_c_sec = QLabel("วิ")

        lbl_c_sec.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: bold;")

        cust_layout.addWidget(lbl_c_sec)



        btn_apply_cust = QPushButton("นำไปใช้")

        btn_apply_cust.setStyleSheet(STYLE_BTN_PRIMARY)

        btn_apply_cust.clicked.connect(self._apply_custom_duration)

        cust_layout.addWidget(btn_apply_cust)

        cust_layout.addStretch()

        cv.addWidget(self.drawer_custom_time)



        # Action Button (Start / Stop)

        self.btn_toggle_checkpoint = QPushButton("🚀 ปล่อยโค้ดขึ้นจอ OBS ทันที!")

        self.btn_toggle_checkpoint.setStyleSheet(STYLE_BTN_SUCCESS)

        self.btn_toggle_checkpoint.setCursor(Qt.PointingHandCursor)

        self.btn_toggle_checkpoint.clicked.connect(self._on_toggle_checkpoint)

        cv.addWidget(self.btn_toggle_checkpoint)



        # Countdown Progress display

        self.box_countdown = QWidget()

        self.box_countdown.setVisible(False)

        bcv = QVBoxLayout(self.box_countdown)

        bcv.setContentsMargins(0, 4, 0, 4)

        bcv.setSpacing(4)

        self.lbl_countdown_time = QLabel("05:00")

        self.lbl_countdown_time.setAlignment(Qt.AlignCenter)

        self.lbl_countdown_time.setStyleSheet("font-size: 30px; font-weight: 900; color: #10b981; font-family: monospace;")

        self.progress_bar = QProgressBar()

        self.progress_bar.setStyleSheet("""

            QProgressBar {

                border: 1px solid #1e293b;

                border-radius: 4px;

                background-color: #0b1120;

                height: 8px;

                text-align: center;

            }

            QProgressBar::chunk {

                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10b981, stop:1 #38bdf8);

                border-radius: 3px;

            }

        """)

        self.progress_bar.setValue(100)

        bcv.addWidget(self.lbl_countdown_time)

        bcv.addWidget(self.progress_bar)

        cv.addWidget(self.box_countdown)



        # Realtime Participant Stream

        self.box_realtime_feed = QWidget()

        self.box_realtime_feed.setVisible(False)

        rf_v = QVBoxLayout(self.box_realtime_feed)

        rf_v.setContentsMargins(0, 4, 0, 0)

        rf_v.setSpacing(6)



        rf_hdr = QHBoxLayout()

        rf_hdr.addWidget(QLabel("🟢 ผู้เข้าร่วมสดขณะนี้:"))

        self.lbl_realtime_count = QLabel("0 คน")

        self.lbl_realtime_count.setStyleSheet("color: #10b981; font-weight: 800; font-size: 13px;")

        rf_hdr.addStretch()

        rf_hdr.addWidget(self.lbl_realtime_count)

        rf_v.addLayout(rf_hdr)



        self.table_realtime = QTableWidget(0, 3)

        self.table_realtime.setHorizontalHeaderLabels(["แพลตฟอร์ม", "ชื่อผู้ชม", "เวลา"])

        self.table_realtime.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

        self.table_realtime.setFixedHeight(120)

        rf_v.addWidget(self.table_realtime)

        cv.addWidget(self.box_realtime_feed)



        # Summary box after checkpoint ends

        self.box_round_summary = QFrame()

        self.box_round_summary.setObjectName("RoundSummaryBox")

        self.box_round_summary.setVisible(False)

        self.box_round_summary.setStyleSheet("""

            QFrame#RoundSummaryBox {

                background-color: #064e3b;

                border: 1px solid #059669;

                border-radius: 8px;

            }

            QLabel {

                border: none;

                background: transparent;

            }

        """)

        sb_v = QVBoxLayout(self.box_round_summary)

        sb_v.setContentsMargins(12, 10, 12, 10)

        sb_v.setSpacing(6)

        self.lbl_summary_text = QLabel("✅ จบด่านแล้ว: มีผู้เข้าร่วมสำเร็จ 0 คน")

        self.lbl_summary_text.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 13px;")

        sb_v.addWidget(self.lbl_summary_text)



        self.btn_next_action = QPushButton("➡️ ดำเนินการต่อไป")

        self.btn_next_action.setStyleSheet(STYLE_BTN_PRIMARY)

        self.btn_next_action.clicked.connect(self._on_next_action_clicked)

        sb_v.addWidget(self.btn_next_action)

        cv.addWidget(self.box_round_summary)



        cv.addStretch()



    def _setup_live_step2_display(self):

        cp_idx = self.current_checkpoint_idx

        mode = self.service.mode

        tot = self.service.total_checkpoints

        code = self.service.get_checkpoint_code(cp_idx)

        name = self.service.get_checkpoint_name(cp_idx)



        self.lbl_live_round_badge.setText(f"ด่าน {cp_idx}/{tot}" if mode == "multi" else "ด่านเดียว")

        self.lbl_live_round_title.setText(f"📍 {name}")

        self.lbl_live_code.setText(code)



        # Default time from preset

        dur = self.active_participant_preset.get("duration_sec", 300)

        self._set_live_quick_time(dur, "ใช้ตาม Preset")



        # Reset button & box states

        self.btn_toggle_checkpoint.setText(f"🚀 ปล่อยโค้ด {code} ขึ้นจอ OBS")

        self.btn_toggle_checkpoint.setStyleSheet(STYLE_BTN_SUCCESS)

        self.btn_toggle_checkpoint.setVisible(True)

        self.box_countdown.setVisible(False)

        self.box_realtime_feed.setVisible(False)

        self.box_round_summary.setVisible(False)

        self.table_realtime.setRowCount(0)

        self.realtime_participants_count = 0



    def _set_live_quick_time(self, seconds: int, label: str):

        self.live_duration_sec = seconds

        m = seconds // 60

        s = seconds % 60

        self.lbl_live_time_preview.setText(f"{m:02d} นาที {s:02d} วินาที ({label})" if seconds > 0 else "เปิดต่อเนื่อง")

        self.drawer_custom_time.setVisible(False)



    def _toggle_custom_time_drawer(self):

        self.drawer_custom_time.setVisible(not self.drawer_custom_time.isVisible())



    def _apply_custom_duration(self):

        hr = self.spin_cust_hr.value()

        mn = self.spin_cust_min.value()

        sc = self.spin_cust_sec.value()

        tot = (hr * 3600) + (mn * 60) + sc

        if tot <= 0:

            QMessageBox.warning(self, "แจ้งเตือน", "กรุณาระบุเวลามากกว่า 0 วินาทีครับ")

            return

        self.live_duration_sec = tot

        self.lbl_live_time_preview.setText(f"{hr} ชม. {mn} นาที {sc} วิ (กำหนดเอง)" if hr > 0 else f"{mn} นาที {sc} วิ (กำหนดเอง)")

        self.drawer_custom_time.setVisible(False)



    def _on_toggle_checkpoint(self):

        if self.service.is_checkpoint_active():

            # Stop immediately

            self.service.stop_checkpoint()

        else:

            # Confirm start

            code = self.service.get_checkpoint_code(self.current_checkpoint_idx)

            name = self.service.get_checkpoint_name(self.current_checkpoint_idx)

            ans = QMessageBox.question(

                self,

                "ยืนยันเริ่มเปิดรับโค้ด",

                f"คุณกำลังจะเริ่มเปิด {name} (โค้ด: {code})\n\nต้องการปล่อยโค้ดขึ้นจอ OBS ตอนนี้เลยใช่หรือไม่?",

                QMessageBox.Yes | QMessageBox.No

            )

            if ans != QMessageBox.Yes:

                return



            self.service.start_checkpoint(self.current_checkpoint_idx, code, self.live_duration_sec)

            self._timer.start()



            self.btn_toggle_checkpoint.setText("⏹️ ปิดรับโค้ดทันที (ซ่อนออกจากจอ OBS)")

            self.btn_toggle_checkpoint.setStyleSheet(STYLE_BTN_DANGER)

            self.box_countdown.setVisible(True)

            self.box_realtime_feed.setVisible(True)

            self.box_round_summary.setVisible(False)



    def _on_timer_tick(self):

        if not self.service.is_checkpoint_active():

            self._timer.stop()

            self._on_live_checkpoint_stopped()

            return



        rem = self.service.get_remaining_sec()

        dur = self.service.duration_sec

        if dur > 0:

            m = int(rem // 60)

            s = int(rem % 60)

            self.lbl_countdown_time.setText(f"{m:02d}:{s:02d}")

            self.progress_bar.setValue(int((rem / dur) * 100))

        else:

            self.lbl_countdown_time.setText("เปิดรับต่อเนื่อง")

            self.progress_bar.setValue(100)



    def _on_live_checkpoint_stopped(self):

        self._timer.stop()

        cp_idx = self.current_checkpoint_idx

        name = self.service.get_checkpoint_name(cp_idx)

        cnt = sum(1 for p in self.service.participants.values() if cp_idx in p.checkins)



        self.btn_toggle_checkpoint.setVisible(False)

        self.box_countdown.setVisible(False)

        self.box_round_summary.setVisible(True)

        self.lbl_summary_text.setText(f"✅ จบ {name} แล้ว: มีผู้เข้าร่วมสำเร็จ {cnt} คน")



        # Determine next action

        if self.service.mode == "multi" and self.current_checkpoint_idx < self.service.total_checkpoints:

            next_name = self.service.get_checkpoint_name(self.current_checkpoint_idx + 1)

            self.btn_next_action.setText(f"➡️ ดำเนินการต่อไปยัง {next_name}")

        else:

            self.btn_next_action.setText("🎁 ไปสู่ห้องสุ่มรางวัล (Draw Screen)")



    def _on_next_action_clicked(self):

        if self.service.mode == "multi" and self.current_checkpoint_idx < self.service.total_checkpoints:

            self.current_checkpoint_idx += 1

            self._setup_live_step2_display()

        else:

            # Go to Step 3: Draw Stage

            self._setup_live_step3_display()

            self.current_live_step = 3

            self.live_step_stack.setCurrentIndex(2)

            self._update_live_stepper_style(3)



    # ── Live Step 3 UI (ห้องสุ่มรางวัลปลายทาง) ──

    def _build_live_step3_ui(self, widget: QWidget):

        cv = QVBoxLayout(widget)

        cv.setContentsMargins(4, 6, 4, 6)

        cv.setSpacing(10)



        hdr = QHBoxLayout()

        hdr.addWidget(QLabel("🎲 สุ่มรายชื่อผู้โชคดี"))

        hdr.addStretch()

        btn_exp_csv = QPushButton("📥 ส่งออก CSV")

        btn_exp_csv.setStyleSheet(STYLE_BTN_SECONDARY)

        btn_exp_csv.setToolTip("Export รายชื่อผู้เข้าร่วมและผู้ได้รับรางวัลเป็นไฟล์ CSV")

        btn_exp_csv.clicked.connect(self._export_full_csv)

        hdr.addWidget(btn_exp_csv)

        cv.addLayout(hdr)



        



        self.lbl_pool_info = QLabel("ผู้มีสิทธิ์ในกลุ่มนี้: 0 คน")
        self.lbl_pool_info.setStyleSheet("color: #38bdf8; font-weight: bold;")
        cv.addWidget(self.lbl_pool_info)

        # Quick Draw Style Selector in Step 3
        row_s3_style = QHBoxLayout()
        row_s3_style.setSpacing(8)
        lbl_s3_st = QLabel("🎰 รูปแบบการสุ่ม:")
        lbl_s3_st.setStyleSheet("font-weight: bold; color: #f59e0b;")
        row_s3_style.addWidget(lbl_s3_st)

        self.cmb_step3_draw_style = QComboBox()
        self._setup_combobox(self.cmb_step3_draw_style)
        self.cmb_step3_draw_style.addItem("⭐ Gachapon (กาชาปองระเบิดดาว)", "gachapon")
        self.cmb_step3_draw_style.addItem("🎰 Slot Machine (ตู้สล็อตหมุนรายชื่อ)", "slot")
        self.cmb_step3_draw_style.addItem("🎲 Smooth Shuffle (สลับการ์ดรายชื่อ)", "shuffle")
        self.cmb_step3_draw_style.currentIndexChanged.connect(self._on_step3_style_changed)
        row_s3_style.addWidget(self.cmb_step3_draw_style, 1)
        cv.addLayout(row_s3_style)

        # Draw Launch Button

        self.btn_spin_draw = QPushButton("🎰 สุ่มผู้โชคดีขึ้นจอ OBS ทันที!")

        self.btn_spin_draw.setStyleSheet(STYLE_SPIN_BTN)

        self.btn_spin_draw.setCursor(Qt.PointingHandCursor)

        self.btn_spin_draw.clicked.connect(self._on_spin_draw_clicked)

        cv.addWidget(self.btn_spin_draw)



        # Winner Announcement Card

        self.box_winner_announce = QFrame()

        self.box_winner_announce.setVisible(False)

        self.box_winner_announce.setStyleSheet("background: #020617; border: 2px solid #f59e0b; border-radius: 8px; padding: 12px;")

        wv = QVBoxLayout(self.box_winner_announce)

        wv.setSpacing(4)

        lbl_w_top = QLabel("🎉 ยินดีด้วยกับผู้โชคดี! 🎉")

        lbl_w_top.setAlignment(Qt.AlignCenter)

        lbl_w_top.setStyleSheet("color: #fbbf24; font-size: 11px; font-weight: bold; letter-spacing: 1px;")

        self.lbl_winner_name = QLabel("@WinnerName")

        self.lbl_winner_name.setAlignment(Qt.AlignCenter)

        self.lbl_winner_name.setStyleSheet("color: #ffffff; font-size: 22px; font-weight: 900;")

        self.lbl_winner_details = QLabel("ได้รับรางวัล: ...")

        self.lbl_winner_details.setAlignment(Qt.AlignCenter)

        self.lbl_winner_details.setStyleSheet("color: #cbd5e1; font-size: 12px;")

        wv.addWidget(lbl_w_top)

        wv.addWidget(self.lbl_winner_name)

        wv.addWidget(self.lbl_winner_details)

        cv.addWidget(self.box_winner_announce)



        # Winners History Table

        cv.addWidget(QLabel("ประวัติผู้โชคดีที่ได้รับการสุ่ม:"))

        self.tbl_draw_history = QTableWidget(0, 4)
        self.tbl_draw_history.setHorizontalHeaderLabels(["ลำดับ", "ชื่อผู้โชคดี", "แพลตฟอร์ม", "เวลา"])
        self.tbl_draw_history.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

        self.tbl_draw_history.setFixedHeight(140)

        cv.addWidget(self.tbl_draw_history)



        # Finish Activity Button

        self.btn_finish_live = QPushButton("🏁 จบกิจกรรมทั้งหมด (รีเซ็ตและกลับสู่หน้าแรก)")

        self.btn_finish_live.setStyleSheet(STYLE_BTN_SECONDARY)

        self.btn_finish_live.setCursor(Qt.PointingHandCursor)

        self.btn_finish_live.clicked.connect(self._finish_and_reset_activity)

        cv.addWidget(self.btn_finish_live)



        cv.addStretch()



    def _update_step3_pool_info(self):
        all_p = list(self.service.participants.values())
        drawn_names = {h.get("name") for h in self.draw_history}
        available = [p for p in all_p if p.author not in drawn_names]
        self.lbl_pool_info.setText(f"ผู้มีสิทธิ์ลุ้นทั้งหมด: {len(available)} คน (จากทั้งหมด {len(all_p)} คน)")

    def _on_step3_style_changed(self, idx: int):
        style = self.cmb_step3_draw_style.currentData() if hasattr(self, "cmb_step3_draw_style") else "gachapon"
        if hasattr(self, "cmb_draw_style"):
            idx_ds = self.cmb_draw_style.findData(style)
            if idx_ds >= 0 and self.cmb_draw_style.currentIndex() != idx_ds:
                self.cmb_draw_style.blockSignals(True)
                self.cmb_draw_style.setCurrentIndex(idx_ds)
                self.cmb_draw_style.blockSignals(False)
        self.service.update_overlay_settings(draw_animation_style=style)

    def _setup_live_step3_display(self):
        self._update_step3_pool_info()
        self.box_winner_announce.setVisible(False)
        if hasattr(self, "cmb_step3_draw_style"):
            idx = self.cmb_step3_draw_style.findData(self.service.draw_animation_style)
            if idx >= 0:
                self.cmb_step3_draw_style.blockSignals(True)
                self.cmb_step3_draw_style.setCurrentIndex(idx)
                self.cmb_step3_draw_style.blockSignals(False)

    



    def _on_spin_draw_clicked(self):
        all_p = list(self.service.participants.values())
        drawn_names = {h.get("name") for h in self.draw_history}
        available = [p for p in all_p if p.author not in drawn_names]

        if not available:
            QMessageBox.warning(self, "ไม่มีผู้มีสิทธิ์", "ไม่มีผู้เข้าร่วมเหลือให้สุ่มแล้ว หรือถูกสุ่มไปครบทุกคนแล้วครับ")
            return

        winner = random.choice(available)
        self._pending_winner = winner

        self._slot_candidates = [p.author for p in available]
        self._pending_winner_name = winner.author

        # ปรับเวลาแสดงใน GUI ให้สอดคล้องกับอนิเมชั่นบน OBS (Gachapon: ~3.4s, Slot: ~3.5s, Shuffle: ~5.5s)
        draw_style = getattr(self.service, "draw_animation_style", "gachapon")
        if draw_style == "shuffle":
            self._slot_ticks_left = 110
        elif draw_style in ("slot", "slotmachine", "slot_reel"):
            self._slot_ticks_left = 70
        else:
            self._slot_ticks_left = 68

        self.btn_spin_draw.setEnabled(False)
        self._slot_timer.start()

        # Broadcast to OBS Overlay WebSocket
        self.service.broadcast_draw_start("", "", self._slot_candidates[:20], winner.author)

    def _on_slot_tick(self):
        if self._slot_ticks_left > 0:
            self._slot_ticks_left -= 1
            cand = random.choice(self._slot_candidates)
            self.lbl_winner_name.setText(f"🎲 {cand}")
            self.box_winner_announce.setVisible(True)
        else:
            self._slot_timer.stop()
            self.btn_spin_draw.setEnabled(True)
            self._show_draw_winner_result()

    def _show_draw_winner_result(self):
        w = getattr(self, "_pending_winner", None)
        if not w:
            return

        now_str = time.strftime("%H:%M:%S")

        self.lbl_winner_name.setText(f"🎉 @{w.author}")
        self.lbl_winner_details.setText(f"แพลตฟอร์ม: {w.platform.capitalize()} | เวลา: {now_str}")
        self.box_winner_announce.setVisible(True)

        # Broadcast winner to OBS Overlay
        self.service.broadcast_draw_winner(w, "", "")

        # Record to history table
        self.draw_history.append({
            "name": w.author,
            "platform": w.platform,
            "time": now_str
        })

        row = self.tbl_draw_history.rowCount()
        self.tbl_draw_history.insertRow(row)
        self.tbl_draw_history.setItem(row, 0, QTableWidgetItem(str(row + 1)))
        self.tbl_draw_history.setItem(row, 1, QTableWidgetItem(w.author))
        self.tbl_draw_history.setItem(row, 2, QTableWidgetItem(w.platform.capitalize()))
        self.tbl_draw_history.setItem(row, 3, QTableWidgetItem(now_str))

        self._update_step3_pool_info()

    



    def _finish_and_reset_activity(self):

        ans = QMessageBox.question(

            self,

            "ยืนยันจบกิจกรรม",

            "คุณต้องการจบกิจกรรมการสุ่มรางวัลในครั้งนี้ และรีเซ็ตข้อมูลเพื่อกลับสู่หน้าแรกใช่หรือไม่?",

            QMessageBox.Yes | QMessageBox.No

        )

        if ans == QMessageBox.Yes:

            self.service.clear_all_data()

            self.service.broadcast_draw_reset()

            self.current_live_step = 1

            self.live_step_stack.setCurrentIndex(0)

            self._update_live_stepper_style(1)

            self._load_initial_live_presets()



    # ─────────────────────────────────────────────────────────────

    # PAGE 1: PARTICIPANT PRESET SETUP (กติกาคนเข้าร่วม)

    # ─────────────────────────────────────────────────────────────

    def _build_participant_preset_ui(self, widget: QWidget):

        scroll = QScrollArea(widget)

        scroll.setWidgetResizable(True)

        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")



        content = QWidget()

        cv = QVBoxLayout(content)

        cv.setContentsMargins(10, 8, 16, 12)

        cv.setSpacing(10)



        # Header with actions

        hdr = QHBoxLayout()

        hdr.addWidget(QLabel("👥 กติกาคนเข้าร่วม"))

        hdr.addStretch()



        self.btn_demo_obs = QPushButton("👁️ ทดสอบ OBS")

        self.btn_demo_obs.setStyleSheet(STYLE_BTN_SECONDARY)

        self.btn_demo_obs.setCursor(Qt.PointingHandCursor)

        self.btn_demo_obs.clicked.connect(self._toggle_obs_demo)

        hdr.addWidget(self.btn_demo_obs)



        btn_save_p = QPushButton("💾 บันทึก")

        btn_save_p.setStyleSheet(STYLE_BTN_PRIMARY)

        btn_save_p.clicked.connect(self._save_current_participant_preset)

        hdr.addWidget(btn_save_p)

        cv.addLayout(hdr)



        # Preset Selector / Manager

        mgr_row = QHBoxLayout()

        mgr_row.addWidget(QLabel("เลือก Preset:"))

        self.cmb_p_editor_select = QComboBox()

        self._setup_combobox(self.cmb_p_editor_select)

        self.cmb_p_editor_select.currentIndexChanged.connect(self._on_p_editor_selected)

        self.cmb_p_editor_select.activated.connect(self._on_p_editor_selected)

        mgr_row.addWidget(self.cmb_p_editor_select, 1)



        btn_new_p = QPushButton("+ สร้างใหม่")

        btn_new_p.setStyleSheet(STYLE_BTN_SECONDARY)

        btn_new_p.clicked.connect(self._create_new_participant_preset)

        mgr_row.addWidget(btn_new_p)



        btn_del_p = QPushButton("🗑️")

        btn_del_p.setStyleSheet(STYLE_BTN_SECONDARY)

        btn_del_p.clicked.connect(self._delete_current_participant_preset)

        mgr_row.addWidget(btn_del_p)

        cv.addLayout(mgr_row)



        # Preset Name & Mode

        row_nm = QHBoxLayout()

        row_nm.addWidget(QLabel("ชื่อ Preset:"))

        self.inp_p_name = QLineEdit()

        row_nm.addWidget(self.inp_p_name, 1)

        cv.addLayout(row_nm)



        row_mode = QHBoxLayout()

        row_mode.addWidget(QLabel("รูปแบบ:"))

        self.cmb_p_mode = QComboBox()

        self._setup_combobox(self.cmb_p_mode)

        self.cmb_p_mode.addItem("🎯 ด่านเดียว (Single Checkpoint)", "single")

        self.cmb_p_mode.addItem("🏆 หลายด่านสะสมแต้ม (Multi-Checkpoint)", "multi")

        self.cmb_p_mode.currentIndexChanged.connect(self._on_p_mode_changed)

        self.cmb_p_mode.activated.connect(self._on_p_mode_changed)

        row_mode.addWidget(self.cmb_p_mode, 1)

        cv.addLayout(row_mode)



        # Single Mode Section

        self.box_p_single = QWidget()

        sv = QVBoxLayout(self.box_p_single)

        sv.setContentsMargins(0, 4, 0, 4)

        sv.setSpacing(6)



        s_code_row = QHBoxLayout()

        s_code_row.addWidget(QLabel("โค้ดที่ให้พิมพ์:"))

        self.inp_p_single_code = QLineEdit("#join")

        self.inp_p_single_code.setStyleSheet("font-weight: bold; color: #f59e0b;")

        s_code_row.addWidget(self.inp_p_single_code, 1)



        btn_dice = QPushButton("🎲 สุ่มคำสั่ง")

        btn_dice.setStyleSheet(STYLE_BTN_SECONDARY)

        btn_dice.clicked.connect(lambda: self._randomize_code(self.inp_p_single_code))

        s_code_row.addWidget(btn_dice)

        sv.addLayout(s_code_row)



        # Clean Studio Time Row

        s_time_box = QFrame()

        s_time_box.setObjectName("TimeCard")

        s_time_box.setStyleSheet("""

            QFrame#TimeCard {

                background-color: #131d31;

                border: 1px solid #1e293b;

                border-radius: 8px;

            }

            QSpinBox {

                background-color: #0b1120;

                border: 1px solid #283548;

                border-radius: 6px;

                color: #38bdf8;

                font-size: 14px;

                font-weight: 800;

                min-height: 28px;

                max-height: 28px;

            }

            QSpinBox:focus {

                border-color: #38bdf8;

                background-color: #0e1726;

            }

            QLabel {

                border: none;

                background: transparent;

            }

        """)

        s_time_row = QHBoxLayout(s_time_box)

        s_time_row.setContentsMargins(12, 6, 12, 6)

        s_time_row.setSpacing(8)



        lbl_t_title = QLabel("⏱️ เวลาตั้งต้น:")

        lbl_t_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #cbd5e1;")

        s_time_row.addWidget(lbl_t_title)



        self.spin_p_single_hr = QSpinBox()

        self.spin_p_single_hr.setButtonSymbols(QSpinBox.NoButtons)

        self.spin_p_single_hr.setRange(0, 24)

        self.spin_p_single_hr.setFixedWidth(46)

        self.spin_p_single_hr.setAlignment(Qt.AlignCenter)

        s_time_row.addWidget(self.spin_p_single_hr)



        lbl_hr = QLabel("ชม.")

        lbl_hr.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: bold;")

        s_time_row.addWidget(lbl_hr)



        sep1 = QLabel(":")

        sep1.setStyleSheet("color: #475569; font-weight: bold;")

        s_time_row.addWidget(sep1)



        self.spin_p_single_min = QSpinBox()

        self.spin_p_single_min.setButtonSymbols(QSpinBox.NoButtons)

        self.spin_p_single_min.setRange(0, 59)

        self.spin_p_single_min.setValue(5)

        self.spin_p_single_min.setFixedWidth(46)

        self.spin_p_single_min.setAlignment(Qt.AlignCenter)

        s_time_row.addWidget(self.spin_p_single_min)



        lbl_min = QLabel("นาที")

        lbl_min.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: bold;")

        s_time_row.addWidget(lbl_min)



        sep2 = QLabel(":")

        sep2.setStyleSheet("color: #475569; font-weight: bold;")

        s_time_row.addWidget(sep2)



        self.spin_p_single_sec = QSpinBox()

        self.spin_p_single_sec.setButtonSymbols(QSpinBox.NoButtons)

        self.spin_p_single_sec.setRange(0, 59)

        self.spin_p_single_sec.setFixedWidth(46)

        self.spin_p_single_sec.setAlignment(Qt.AlignCenter)

        s_time_row.addWidget(self.spin_p_single_sec)



        lbl_sec = QLabel("วิ")

        lbl_sec.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: bold;")

        s_time_row.addWidget(lbl_sec)



        s_time_row.addStretch()

        sv.addWidget(s_time_box)

        cv.addWidget(self.box_p_single)



        # Multi Mode Section

        self.box_p_multi = QWidget()

        self.box_p_multi.setVisible(False)

        mv = QVBoxLayout(self.box_p_multi)

        mv.setContentsMargins(0, 4, 0, 4)

        mv.setSpacing(6)



        m_hdr = QHBoxLayout()

        m_hdr.addWidget(QLabel("รายการด่านและโค้ด:"))

        m_hdr.addStretch()

        btn_add_cp = QPushButton("+ เพิ่มด่าน")

        btn_add_cp.setStyleSheet(STYLE_BTN_SECONDARY)

        btn_add_cp.clicked.connect(self._add_multi_cp_row)

        btn_del_cp = QPushButton("- ลบด่าน")

        btn_del_cp.setStyleSheet(STYLE_BTN_SECONDARY)

        btn_del_cp.clicked.connect(self._remove_multi_cp_row)

        m_hdr.addWidget(btn_add_cp)

        m_hdr.addWidget(btn_del_cp)

        mv.addLayout(m_hdr)



        self.tbl_multi_cps = QTableWidget(3, 4)

        self.tbl_multi_cps.setHorizontalHeaderLabels(["ด่านที่", "ชื่อรอบ", "โค้ด", "เวลา (วิ)"])

        self.tbl_multi_cps.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

        self.tbl_multi_cps.setFixedHeight(120)

        mv.addWidget(self.tbl_multi_cps)

        cv.addWidget(self.box_p_multi)



        # OBS Display Settings

        cv.addWidget(QLabel("การแสดงผลการเปิดรับเข้าร่วม บน OBS Studio:"))

        self.rad_disp_banner = QRadioButton("กล่อง Overlay ข้อความ/รหัส (มาตรฐาน)")

        self.rad_disp_image = QRadioButton("ภาพแบนเนอร์กิจกรรมบน Overlay")

        self.rad_disp_none = QRadioButton("ไม่แสดงบนจอ Overlay (รับเข้าร่วมเบื้องหลัง)")

        self.rad_disp_banner.setChecked(True)



        self.btn_grp_disp = QButtonGroup(self)

        self.btn_grp_disp.addButton(self.rad_disp_banner)

        self.btn_grp_disp.addButton(self.rad_disp_image)

        self.btn_grp_disp.addButton(self.rad_disp_none)

        self.rad_disp_image.toggled.connect(self._on_display_mode_toggled)
        self.rad_disp_banner.toggled.connect(lambda c: c and self._sync_overlay_live_settings())
        self.rad_disp_none.toggled.connect(lambda c: c and self._sync_overlay_live_settings())



        cv.addWidget(self.rad_disp_banner)

        cv.addWidget(self.rad_disp_image)



        # Image browse box

        self.box_img_browse = QWidget()

        self.box_img_browse.setVisible(False)

        ib_layout = QHBoxLayout(self.box_img_browse)

        ib_layout.setContentsMargins(18, 0, 0, 0)

        self.inp_img_path = QLineEdit()

        self.inp_img_path.setPlaceholderText("เลือกรูปภาพ...")

        self.inp_img_path.textChanged.connect(self._sync_overlay_live_settings)

        btn_browse_img = QPushButton("📁 เลือกภาพ...")

        btn_browse_img.setStyleSheet(STYLE_BTN_SECONDARY)

        btn_browse_img.clicked.connect(self._browse_custom_image)

        ib_layout.addWidget(self.inp_img_path, 1)

        ib_layout.addWidget(btn_browse_img)

        cv.addWidget(self.box_img_browse)



        cv.addWidget(self.rad_disp_none)



        # Sliders for Scale & Position X / Y

        cv.addWidget(QLabel("🎛️ ตัวปรับสเกลขนาด & พิกัด X/Y (บนหน้าจอ OBS):"))

        sl_v = QVBoxLayout()

        sl_v.setSpacing(6)



        # Box scale slider

        row_sc = QHBoxLayout()

        row_sc.addWidget(QLabel("ขนาดกล่อง Overlay:"))

        self.lbl_val_scale = QLabel("100%")

        self.lbl_val_scale.setFixedWidth(46)

        self.lbl_val_scale.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.lbl_val_scale.setStyleSheet("color: #38bdf8; font-weight: bold;")

        self.slider_scale = QSlider(Qt.Horizontal)

        self.slider_scale.setRange(50, 180)

        self.slider_scale.setValue(100)

        self.slider_scale.valueChanged.connect(lambda v: self.lbl_val_scale.setText(f"{v}%"))

        self.slider_scale.valueChanged.connect(self._sync_overlay_live_settings)

        row_sc.addWidget(self.slider_scale, 1)

        row_sc.addWidget(self.lbl_val_scale)

        sl_v.addLayout(row_sc)



        # Font scale slider

        row_font = QHBoxLayout()

        row_font.addWidget(QLabel("ขนาดตัวหนังสือ:"))

        self.lbl_val_font = QLabel("100%")

        self.lbl_val_font.setFixedWidth(46)

        self.lbl_val_font.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.lbl_val_font.setStyleSheet("color: #38bdf8; font-weight: bold;")

        self.slider_font = QSlider(Qt.Horizontal)

        self.slider_font.setRange(70, 160)

        self.slider_font.setValue(100)

        self.slider_font.valueChanged.connect(lambda v: self.lbl_val_font.setText(f"{v}%"))

        self.slider_font.valueChanged.connect(self._sync_overlay_live_settings)

        row_font.addWidget(self.slider_font, 1)

        row_font.addWidget(self.lbl_val_font)

        sl_v.addLayout(row_font)



        # Offset X

        row_ox = QHBoxLayout()

        row_ox.addWidget(QLabel("เลื่อนตำแหน่ง X:"))

        self.lbl_val_ox = QLabel("0px")

        self.lbl_val_ox.setFixedWidth(52)

        self.lbl_val_ox.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.lbl_val_ox.setStyleSheet("color: #f59e0b; font-weight: bold;")

        self.slider_ox = QSlider(Qt.Horizontal)

        self.slider_ox.setRange(-400, 400)

        self.slider_ox.setValue(0)

        self.slider_ox.valueChanged.connect(lambda v: self.lbl_val_ox.setText(f"{v:+d}px" if v != 0 else "0px"))

        self.slider_ox.valueChanged.connect(self._sync_overlay_live_settings)

        row_ox.addWidget(self.slider_ox, 1)

        row_ox.addWidget(self.lbl_val_ox)

        sl_v.addLayout(row_ox)



        # Offset Y

        row_oy = QHBoxLayout()

        row_oy.addWidget(QLabel("เลื่อนตำแหน่ง Y:"))

        self.lbl_val_oy = QLabel("0px")

        self.lbl_val_oy.setFixedWidth(52)

        self.lbl_val_oy.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.lbl_val_oy.setStyleSheet("color: #f59e0b; font-weight: bold;")

        self.slider_oy = QSlider(Qt.Horizontal)

        self.slider_oy.setRange(-400, 400)

        self.slider_oy.setValue(0)

        self.slider_oy.valueChanged.connect(lambda v: self.lbl_val_oy.setText(f"{v:+d}px" if v != 0 else "0px"))

        self.slider_oy.valueChanged.connect(self._sync_overlay_live_settings)

        row_oy.addWidget(self.slider_oy, 1)

        row_oy.addWidget(self.lbl_val_oy)

        sl_v.addLayout(row_oy)



        cv.addLayout(sl_v)

        # Dropdowns สำหรับเลือกทิศทาง / สไตล์อนิเมชั่น เข้า-ออก
        row_anim = QHBoxLayout()
        row_anim.setSpacing(10)

        col_ai = QVBoxLayout()
        col_ai.setSpacing(4)
        col_ai.addWidget(QLabel("🎬 อนิเมชั่นเข้า (In):"))
        self.cmb_anim_in = QComboBox()
        self._setup_combobox(self.cmb_anim_in)
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
        self.cmb_anim_in.currentIndexChanged.connect(self._sync_overlay_live_settings)
        col_ai.addWidget(self.cmb_anim_in)
        row_anim.addLayout(col_ai, 1)

        col_ao = QVBoxLayout()
        col_ao.setSpacing(4)
        col_ao.addWidget(QLabel("🎬 อนิเมชั่นออก (Out):"))
        self.cmb_anim_out = QComboBox()
        self._setup_combobox(self.cmb_anim_out)
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
        self.cmb_anim_out.currentIndexChanged.connect(self._sync_overlay_live_settings)
        col_ao.addWidget(self.cmb_anim_out)
        row_anim.addLayout(col_ao, 1)

        cv.addSpacing(6)
        cv.addLayout(row_anim)

        # ─────────────────────────────────────────────────────────────
        # Lucky Draw Stage Styling (เวทีสุ่มผู้โชคดีบน OBS)
        # ─────────────────────────────────────────────────────────────
        cv.addSpacing(14)
        lbl_draw_sec = QLabel("🎲 หน้าสุ่มผู้โชคดี (Lucky Draw Stage Overlay):")
        lbl_draw_sec.setStyleSheet("font-size: 13px; font-weight: bold; color: #fbbf24;")
        cv.addWidget(lbl_draw_sec)

        # Style & Theme Row
        row_draw_style = QHBoxLayout()
        row_draw_style.setSpacing(10)

        col_ds = QVBoxLayout()
        col_ds.setSpacing(4)
        col_ds.addWidget(QLabel("🎰 รูปแบบการสุ่ม:"))
        self.cmb_draw_style = QComboBox()
        self._setup_combobox(self.cmb_draw_style)
        self.cmb_draw_style.addItem("⭐ Gachapon (กาชาปองระเบิดดาว)", "gachapon")
        self.cmb_draw_style.addItem("🎰 Slot Machine (ตู้สล็อตหมุนรายชื่อ)", "slot")
        self.cmb_draw_style.addItem("🎲 Smooth Shuffle (สลับการ์ดรายชื่อ)", "shuffle")
        self.cmb_draw_style.currentIndexChanged.connect(self._sync_draw_live_settings)
        col_ds.addWidget(self.cmb_draw_style)
        row_draw_style.addLayout(col_ds, 1)

        col_dt = QVBoxLayout()
        col_dt.setSpacing(4)
        col_dt.addWidget(QLabel("🎨 ธีมสีเวทีสุ่ม:"))
        self.cmb_draw_theme = QComboBox()
        self._setup_combobox(self.cmb_draw_theme)
        self.cmb_draw_theme.addItem("✨ สีทองหรูหรา (Gold)", "gold")
        self.cmb_draw_theme.addItem("⚡ นีออนไซเบอร์พังก์ (Cyberpunk)", "cyberpunk")
        self.cmb_draw_theme.addItem("🔮 ม่วงเวทมนตร์ (Violet)", "violet")
        self.cmb_draw_theme.addItem("🌿 มรกตสดใส (Emerald)", "emerald")
        self.cmb_draw_theme.addItem("🌸 ซากุระชมพู (Sakura)", "sakura")
        self.cmb_draw_theme.addItem("❄️ น้ำแข็งสีฟ้า (Ice)", "ice")
        self.cmb_draw_theme.addItem("💎 ทับทิมแดง (Ruby)", "ruby")
        self.cmb_draw_theme.currentIndexChanged.connect(self._sync_draw_live_settings)
        col_dt.addWidget(self.cmb_draw_theme)
        row_draw_style.addLayout(col_dt, 1)

        cv.addLayout(row_draw_style)

        # Draw Sliders (Scale, Name Font Size, Offset X, Offset Y)
        sl_draw = QVBoxLayout()
        sl_draw.setSpacing(6)

        # Draw Scale slider
        row_d_sc = QHBoxLayout()
        row_d_sc.addWidget(QLabel("ขนาดเวทีสุ่ม (Scale):"))
        self.lbl_val_draw_scale = QLabel("100%")
        self.lbl_val_draw_scale.setFixedWidth(46)
        self.lbl_val_draw_scale.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.lbl_val_draw_scale.setStyleSheet("color: #38bdf8; font-weight: bold;")
        self.slider_draw_scale = QSlider(Qt.Horizontal)
        self.slider_draw_scale.setRange(50, 180)
        self.slider_draw_scale.setValue(100)
        self.slider_draw_scale.valueChanged.connect(lambda v: self.lbl_val_draw_scale.setText(f"{v}%"))
        self.slider_draw_scale.valueChanged.connect(self._sync_draw_live_settings)
        row_d_sc.addWidget(self.slider_draw_scale, 1)
        row_d_sc.addWidget(self.lbl_val_draw_scale)
        sl_draw.addLayout(row_d_sc)

        # Draw Winner Name Font Size slider
        row_d_fn = QHBoxLayout()
        row_d_fn.addWidget(QLabel("ขนาดชื่อผู้โชคดี:"))
        self.lbl_val_draw_name_size = QLabel("52px")
        self.lbl_val_draw_name_size.setFixedWidth(46)
        self.lbl_val_draw_name_size.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.lbl_val_draw_name_size.setStyleSheet("color: #38bdf8; font-weight: bold;")
        self.slider_draw_name_size = QSlider(Qt.Horizontal)
        self.slider_draw_name_size.setRange(28, 84)
        self.slider_draw_name_size.setValue(52)
        self.slider_draw_name_size.valueChanged.connect(lambda v: self.lbl_val_draw_name_size.setText(f"{v}px"))
        self.slider_draw_name_size.valueChanged.connect(self._sync_draw_live_settings)
        row_d_fn.addWidget(self.slider_draw_name_size, 1)
        row_d_fn.addWidget(self.lbl_val_draw_name_size)
        sl_draw.addLayout(row_d_fn)

        # Draw Offset X
        row_d_ox = QHBoxLayout()
        row_d_ox.addWidget(QLabel("เลื่อนตำแหน่ง X:"))
        self.lbl_val_draw_ox = QLabel("0px")
        self.lbl_val_draw_ox.setFixedWidth(52)
        self.lbl_val_draw_ox.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.lbl_val_draw_ox.setStyleSheet("color: #f59e0b; font-weight: bold;")
        self.slider_draw_ox = QSlider(Qt.Horizontal)
        self.slider_draw_ox.setRange(-400, 400)
        self.slider_draw_ox.setValue(0)
        self.slider_draw_ox.valueChanged.connect(lambda v: self.lbl_val_draw_ox.setText(f"{v:+d}px" if v != 0 else "0px"))
        self.slider_draw_ox.valueChanged.connect(self._sync_draw_live_settings)
        row_d_ox.addWidget(self.slider_draw_ox, 1)
        row_d_ox.addWidget(self.lbl_val_draw_ox)
        sl_draw.addLayout(row_d_ox)

        # Draw Offset Y
        row_d_oy = QHBoxLayout()
        row_d_oy.addWidget(QLabel("เลื่อนตำแหน่ง Y:"))
        self.lbl_val_draw_oy = QLabel("0px")
        self.lbl_val_draw_oy.setFixedWidth(52)
        self.lbl_val_draw_oy.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.lbl_val_draw_oy.setStyleSheet("color: #f59e0b; font-weight: bold;")
        self.slider_draw_oy = QSlider(Qt.Horizontal)
        self.slider_draw_oy.setRange(-400, 400)
        self.slider_draw_oy.setValue(0)
        self.slider_draw_oy.valueChanged.connect(lambda v: self.lbl_val_draw_oy.setText(f"{v:+d}px" if v != 0 else "0px"))
        self.slider_draw_oy.valueChanged.connect(self._sync_draw_live_settings)
        row_d_oy.addWidget(self.slider_draw_oy, 1)
        row_d_oy.addWidget(self.lbl_val_draw_oy)
        sl_draw.addLayout(row_d_oy)

        cv.addLayout(sl_draw)

        # Draw Autohide & Test Button
        row_d_bot = QHBoxLayout()
        row_d_bot.addWidget(QLabel("ซ่อนผลสุ่มอัตโนมัติ:"))
        self.spin_draw_autohide = QSpinBox()
        self.spin_draw_autohide.setRange(0, 60)
        self.spin_draw_autohide.setValue(15)
        self.spin_draw_autohide.setSuffix(" วินาที (0 = ไม่ซ่อน)")
        self.spin_draw_autohide.valueChanged.connect(self._sync_draw_live_settings)
        row_d_bot.addWidget(self.spin_draw_autohide, 1)

        self.btn_test_draw_obs = QPushButton("👁️ ทดสอบหน้าสุ่มบน OBS")
        self.btn_test_draw_obs.setStyleSheet(STYLE_BTN_SECONDARY)
        self.btn_test_draw_obs.setCursor(Qt.PointingHandCursor)
        self.btn_test_draw_obs.clicked.connect(self._test_draw_on_obs)
        row_d_bot.addWidget(self.btn_test_draw_obs)

        cv.addLayout(row_d_bot)

        cv.addStretch()

        scroll.setWidget(content)



        root_v = QVBoxLayout(widget)

        root_v.setContentsMargins(0, 0, 0, 0)

        root_v.addWidget(scroll)



    def _reload_participant_preset_dropdown(self):

        self.cmb_p_editor_select.blockSignals(True)

        self.cmb_p_editor_select.clear()

        presets = self.preset_mgr.get_participant_presets()

        for p in presets:

            self.cmb_p_editor_select.addItem(p.get("name", "Preset"), p.get("id"))

        self.cmb_p_editor_select.blockSignals(False)

        if presets:

            self._on_p_editor_selected(0)



    def _on_p_editor_selected(self, idx: int):

        p_id = self.cmb_p_editor_select.currentData()

        p = self.preset_mgr.get_participant_preset(p_id)

        if not p:

            return



        self.inp_p_name.setText(p.get("name", ""))

        mode = p.get("mode", "single")

        self.cmb_p_mode.setCurrentIndex(0 if mode == "single" else 1)



        # Single

        self.inp_p_single_code.setText(p.get("code", "#join"))

        sec = p.get("duration_sec", 300)

        self.spin_p_single_hr.setValue(sec // 3600)

        self.spin_p_single_min.setValue((sec % 3600) // 60)

        self.spin_p_single_sec.setValue(sec % 60)



        # Multi

        cps = p.get("checkpoints", [])

        self.tbl_multi_cps.setRowCount(len(cps))

        for r, cp in enumerate(cps):

            self.tbl_multi_cps.setItem(r, 0, QTableWidgetItem(str(cp.get("index", r+1))))

            self.tbl_multi_cps.setItem(r, 1, QTableWidgetItem(cp.get("name", f"รอบที่ {r+1}")))

            self.tbl_multi_cps.setItem(r, 2, QTableWidgetItem(cp.get("code", f"#join{r+1}")))

            self.tbl_multi_cps.setItem(r, 3, QTableWidgetItem(str(cp.get("duration_sec", 300))))



        # Display mode

        disp = p.get("overlay_display_mode", "banner")

        if disp == "image":

            self.rad_disp_image.setChecked(True)

        elif disp == "none":

            self.rad_disp_none.setChecked(True)

        else:

            self.rad_disp_banner.setChecked(True)



        self.inp_img_path.setText(p.get("custom_image_path", ""))

        self.box_img_browse.setVisible(disp == "image")



        # Sliders (บล็อคสัญญาณขณะโหลดค่า แล้วซิงก์อัปเดต OBS ครั้งเดียว)
        for s in (self.slider_scale, self.slider_font, self.slider_ox, self.slider_oy):
            s.blockSignals(True)

        self.slider_scale.setValue(p.get("overlay_scale", 100))
        self.lbl_val_scale.setText(f"{self.slider_scale.value()}%")

        self.slider_font.setValue(p.get("overlay_font_size", 100))
        self.lbl_val_font.setText(f"{self.slider_font.value()}%")

        self.slider_ox.setValue(p.get("overlay_offset_x", 0))
        self.lbl_val_ox.setText(f"{self.slider_ox.value():+d}px" if self.slider_ox.value() != 0 else "0px")

        self.slider_oy.setValue(p.get("overlay_offset_y", 0))
        self.lbl_val_oy.setText(f"{self.slider_oy.value():+d}px" if self.slider_oy.value() != 0 else "0px")

        for s in (self.slider_scale, self.slider_font, self.slider_ox, self.slider_oy):
            s.blockSignals(False)

        if hasattr(self, "cmb_anim_in"):
            ain = p.get("overlay_anim_in", "slide")
            idx_ai = self.cmb_anim_in.findData(ain)
            if idx_ai >= 0:
                self.cmb_anim_in.blockSignals(True)
                self.cmb_anim_in.setCurrentIndex(idx_ai)
                self.cmb_anim_in.blockSignals(False)

        if hasattr(self, "cmb_anim_out"):
            aout = p.get("overlay_anim_out", "slide")
            idx_ao = self.cmb_anim_out.findData(aout)
            if idx_ao >= 0:
                self.cmb_anim_out.blockSignals(True)
                self.cmb_anim_out.setCurrentIndex(idx_ao)
                self.cmb_anim_out.blockSignals(False)

        # Load Draw Stage Settings
        if hasattr(self, "cmb_draw_style"):
            d_st = p.get("draw_animation_style", "gachapon")
            idx_ds = self.cmb_draw_style.findData(d_st)
            if idx_ds >= 0:
                self.cmb_draw_style.blockSignals(True)
                self.cmb_draw_style.setCurrentIndex(idx_ds)
                self.cmb_draw_style.blockSignals(False)

        if hasattr(self, "cmb_draw_theme"):
            d_th = p.get("draw_theme", "gold")
            idx_dt = self.cmb_draw_theme.findData(d_th)
            if idx_dt >= 0:
                self.cmb_draw_theme.blockSignals(True)
                self.cmb_draw_theme.setCurrentIndex(idx_dt)
                self.cmb_draw_theme.blockSignals(False)

        if hasattr(self, "slider_draw_scale"):
            self.slider_draw_scale.blockSignals(True)
            self.slider_draw_scale.setValue(p.get("draw_scale", 100))
            self.lbl_val_draw_scale.setText(f"{self.slider_draw_scale.value()}%")
            self.slider_draw_scale.blockSignals(False)

        if hasattr(self, "slider_draw_name_size"):
            self.slider_draw_name_size.blockSignals(True)
            self.slider_draw_name_size.setValue(p.get("draw_name_size", 52))
            self.lbl_val_draw_name_size.setText(f"{self.slider_draw_name_size.value()}px")
            self.slider_draw_name_size.blockSignals(False)

        if hasattr(self, "slider_draw_ox"):
            self.slider_draw_ox.blockSignals(True)
            self.slider_draw_ox.setValue(p.get("draw_offset_x", 0))
            self.lbl_val_draw_ox.setText(f"{self.slider_draw_ox.value():+d}px" if self.slider_draw_ox.value() != 0 else "0px")
            self.slider_draw_ox.blockSignals(False)

        if hasattr(self, "slider_draw_oy"):
            self.slider_draw_oy.blockSignals(True)
            self.slider_draw_oy.setValue(p.get("draw_offset_y", 0))
            self.lbl_val_draw_oy.setText(f"{self.slider_draw_oy.value():+d}px" if self.slider_draw_oy.value() != 0 else "0px")
            self.slider_draw_oy.blockSignals(False)

        if hasattr(self, "spin_draw_autohide"):
            self.spin_draw_autohide.blockSignals(True)
            self.spin_draw_autohide.setValue(p.get("draw_autohide_sec", 15))
            self.spin_draw_autohide.blockSignals(False)

        self._sync_overlay_live_settings()
        self._sync_draw_live_settings()



    def _on_p_mode_changed(self, idx: int):

        is_multi = (idx == 1)

        self.box_p_single.setVisible(not is_multi)

        self.box_p_multi.setVisible(is_multi)



    def _on_display_mode_toggled(self, checked: bool):

        self.box_img_browse.setVisible(checked)

        self._sync_overlay_live_settings()



    def _sync_draw_live_settings(self):
        style = self.cmb_draw_style.currentData() if hasattr(self, "cmb_draw_style") else "gachapon"
        theme = self.cmb_draw_theme.currentData() if hasattr(self, "cmb_draw_theme") else "gold"
        scale = self.slider_draw_scale.value() if hasattr(self, "slider_draw_scale") else 100
        name_size = self.slider_draw_name_size.value() if hasattr(self, "slider_draw_name_size") else 52
        ox = self.slider_draw_ox.value() if hasattr(self, "slider_draw_ox") else 0
        oy = self.slider_draw_oy.value() if hasattr(self, "slider_draw_oy") else 0
        autohide = self.spin_draw_autohide.value() if hasattr(self, "spin_draw_autohide") else 15

        if hasattr(self, "cmb_step3_draw_style"):
            idx = self.cmb_step3_draw_style.findData(style)
            if idx >= 0 and self.cmb_step3_draw_style.currentIndex() != idx:
                self.cmb_step3_draw_style.blockSignals(True)
                self.cmb_step3_draw_style.setCurrentIndex(idx)
                self.cmb_step3_draw_style.blockSignals(False)

        self.service.update_overlay_settings(
            draw_animation_style=style,
            draw_theme=theme,
            draw_scale=scale,
            draw_name_size=name_size,
            draw_offset_x=ox,
            draw_offset_y=oy,
            draw_autohide_sec=autohide
        )

    def _toggle_draw_demo_obs(self):
        """เปิด / ปิด ทดสอบหน้าสุ่มผู้โชคดีบนจอ OBS Studio ทันทีแบบ Toggle"""
        if getattr(self, "_is_draw_demo_active", False):
            # ปิดการทดสอบทันที
            self._stop_draw_demo_obs()
        else:
            # เริ่มการทดสอบ
            self._is_draw_demo_active = True
            self.btn_test_draw_obs.setText("⏹️ ปิดทดสอบหน้าสุ่ม")
            self.btn_test_draw_obs.setStyleSheet("""
                QPushButton {
                    background-color: #dc2626;
                    color: #ffffff;
                    border: 1px solid #ef4444;
                    border-radius: 6px;
                    padding: 6px 14px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #b91c1c;
                }
            """)
            self._sync_draw_live_settings()
            self.service.trigger_draw_preview()

            # ตั้งเวลารีเซ็ตสถานะปุ่มตาม autohide (ถ้าตั้งไว้ > 0)
            autohide = self.spin_draw_autohide.value() if hasattr(self, "spin_draw_autohide") else 15
            if autohide > 0:
                total_ms = (autohide + 4) * 1000
                self._draw_demo_timer.start(total_ms)

    def _stop_draw_demo_obs(self):
        """หยุดการทดสอบหน้าสุ่ม และส่งคำสั่งรีเซ็ตไปยัง OBS ทันที"""
        self._is_draw_demo_active = False
        if hasattr(self, "_draw_demo_timer"):
            self._draw_demo_timer.stop()
        if hasattr(self, "btn_test_draw_obs"):
            self.btn_test_draw_obs.setText("👁️ ทดสอบหน้าสุ่มบน OBS")
            self.btn_test_draw_obs.setStyleSheet(STYLE_BTN_SECONDARY)
        self.service.broadcast_draw_reset()

    def _on_draw_demo_timeout(self):
        """เมื่อหน้าสุ่มหมดเวลาแสดงผลอัตโนมัติ ให้คืนสถานะปุ่มกลับมาเป็นปกติ"""
        self._is_draw_demo_active = False
        if hasattr(self, "btn_test_draw_obs"):
            self.btn_test_draw_obs.setText("👁️ ทดสอบหน้าสุ่มบน OBS")
            self.btn_test_draw_obs.setStyleSheet(STYLE_BTN_SECONDARY)

    _test_draw_on_obs = _toggle_draw_demo_obs

    def _sync_overlay_live_settings(self):
        """ส่งการตั้งค่า Overlay (Scale, Font, X/Y Offset, Mode, Image) ไปยัง Service และจอ OBS ทันทีแบบ Realtime"""
        if not hasattr(self, "service") or not self.service:
            return

        disp_mode = "banner"
        if hasattr(self, "rad_disp_image") and self.rad_disp_image.isChecked():
            disp_mode = "image"
        elif hasattr(self, "rad_disp_none") and self.rad_disp_none.isChecked():
            disp_mode = "none"

        scale = self.slider_scale.value() if hasattr(self, "slider_scale") else 100
        font_size = self.slider_font.value() if hasattr(self, "slider_font") else 100
        ox = self.slider_ox.value() if hasattr(self, "slider_ox") else 0
        oy = self.slider_oy.value() if hasattr(self, "slider_oy") else 0
        img_path = self.inp_img_path.text().strip() if hasattr(self, "inp_img_path") else ""

        anim_in = self.cmb_anim_in.currentData() if hasattr(self, "cmb_anim_in") else "slide"
        anim_out = self.cmb_anim_out.currentData() if hasattr(self, "cmb_anim_out") else "slide"

        self.service.update_overlay_settings(
            overlay_display_mode=disp_mode,
            overlay_scale=scale,
            overlay_font_size=font_size,
            overlay_offset_x=ox,
            overlay_offset_y=oy,
            overlay_anim_in=anim_in,
            overlay_anim_out=anim_out,
            overlay_image_path=img_path,
            custom_image_path=img_path
        )

    def _browse_custom_image(self):

        path, _ = QFileDialog.getOpenFileName(self, "เลือกรูปภาพสำหรับ Overlay", "", "Images (*.png *.jpg *.jpeg *.webp)")

        if path:

            self.inp_img_path.setText(path)



    def _randomize_code(self, line_edit: QLineEdit):

        prefixes = ["WIN", "LUCKY", "DROP", "GIFT", "PLAY", "STAR"]

        num = random.randint(100, 999)

        line_edit.setText(f"#{random.choice(prefixes)}{num}")



    def _add_multi_cp_row(self):

        r = self.tbl_multi_cps.rowCount()

        self.tbl_multi_cps.insertRow(r)

        self.tbl_multi_cps.setItem(r, 0, QTableWidgetItem(str(r + 1)))

        self.tbl_multi_cps.setItem(r, 1, QTableWidgetItem(f"รอบที่ {r + 1}"))

        self.tbl_multi_cps.setItem(r, 2, QTableWidgetItem(f"#join{r + 1}"))

        self.tbl_multi_cps.setItem(r, 3, QTableWidgetItem("300"))



    def _remove_multi_cp_row(self):

        r = self.tbl_multi_cps.rowCount()

        if r > 1:

            self.tbl_multi_cps.removeRow(r - 1)



    def _create_new_participant_preset(self):

        dlg = RoundNameDialog("➕ สร้างกติกาคนเข้าร่วมใหม่", "กิจกรรมใหม่", self)

        if dlg.exec() == QDialog.Accepted and dlg.get_name():

            new_p = {

                "id": f"preset_{int(time.time())}",

                "name": dlg.get_name(),

                "mode": "single",

                "code": "#join",

                "duration_sec": 300,

                "overlay_display_mode": "banner",

                "overlay_scale": 100,

                "overlay_font_size": 100,

                "overlay_offset_x": 0,

                "overlay_offset_y": 0,

                "custom_image_path": ""

            }

            self.preset_mgr.save_participant_preset(new_p)

            self._reload_participant_preset_dropdown()

            idx = self.cmb_p_editor_select.findData(new_p["id"])

            if idx >= 0:

                self.cmb_p_editor_select.setCurrentIndex(idx)



    def _delete_current_participant_preset(self):

        p_id = self.cmb_p_editor_select.currentData()

        if not p_id:

            return

        ans = QMessageBox.question(self, "ยืนยันการลบ", "คุณแน่ใจหรือไม่ว่าต้องการลบกติกานี้?", QMessageBox.Yes | QMessageBox.No)

        if ans == QMessageBox.Yes:

            self.preset_mgr.delete_participant_preset(p_id)

            self._reload_participant_preset_dropdown()



    def _save_current_participant_preset(self):

        p_id = self.cmb_p_editor_select.currentData()

        if not p_id:

            return



        mode = "multi" if self.cmb_p_mode.currentIndex() == 1 else "single"

        sec = (self.spin_p_single_hr.value() * 3600) + (self.spin_p_single_min.value() * 60) + self.spin_p_single_sec.value()



        cps = []

        if mode == "multi":

            for r in range(self.tbl_multi_cps.rowCount()):

                cps.append({

                    "index": r + 1,

                    "name": self.tbl_multi_cps.item(r, 1).text() if self.tbl_multi_cps.item(r, 1) else f"รอบที่ {r+1}",

                    "code": self.tbl_multi_cps.item(r, 2).text() if self.tbl_multi_cps.item(r, 2) else f"#join{r+1}",

                    "duration_sec": int(self.tbl_multi_cps.item(r, 3).text()) if self.tbl_multi_cps.item(r, 3) else 300

                })



        disp_mode = "banner"

        if self.rad_disp_image.isChecked():

            disp_mode = "image"

        elif self.rad_disp_none.isChecked():

            disp_mode = "none"



        p_data = {

            "id": p_id,

            "name": self.inp_p_name.text().strip() or "Preset คนเข้าร่วม",

            "mode": mode,

            "code": self.inp_p_single_code.text().strip() or "#join",

            "duration_sec": sec or 300,

            "total_checkpoints": len(cps) if mode == "multi" else 1,

            "checkpoints": cps,

            "overlay_display_mode": disp_mode,

            "custom_image_path": self.inp_img_path.text().strip(),

            "overlay_scale": self.slider_scale.value(),

            "overlay_font_size": self.slider_font.value(),

            "overlay_offset_x": self.slider_ox.value(),

            "overlay_offset_y": self.slider_oy.value(),
            "overlay_anim_in": self.cmb_anim_in.currentData() if hasattr(self, "cmb_anim_in") else "slide",
            "overlay_anim_out": self.cmb_anim_out.currentData() if hasattr(self, "cmb_anim_out") else "slide",
            "draw_animation_style": self.cmb_draw_style.currentData() if hasattr(self, "cmb_draw_style") else "gachapon",
            "draw_theme": self.cmb_draw_theme.currentData() if hasattr(self, "cmb_draw_theme") else "gold",
            "draw_scale": self.slider_draw_scale.value() if hasattr(self, "slider_draw_scale") else 100,
            "draw_name_size": self.slider_draw_name_size.value() if hasattr(self, "slider_draw_name_size") else 52,
            "draw_offset_x": self.slider_draw_ox.value() if hasattr(self, "slider_draw_ox") else 0,
            "draw_offset_y": self.slider_draw_oy.value() if hasattr(self, "slider_draw_oy") else 0,
            "draw_autohide_sec": self.spin_draw_autohide.value() if hasattr(self, "spin_draw_autohide") else 15
        }

        self.preset_mgr.save_participant_preset(p_data)

        QMessageBox.information(self, "สำเร็จ", "บันทึกกติกาคนเข้าร่วมเรียบร้อยแล้วครับ!")

        self._reload_participant_preset_dropdown()



    def _toggle_obs_demo(self):
        """เปิด / ปิด ตัวอย่างบนจอ OBS Studio ทันทีแบบ Toggle โดยไม่เด้ง Popup แจ้งเตือน"""
        if getattr(self, "_is_obs_demo_active", False):
            # ปิดทดสอบทันที
            self._is_obs_demo_active = False
            self.btn_demo_obs.setText("👁️ ทดสอบ OBS")
            self.btn_demo_obs.setStyleSheet(STYLE_BTN_SECONDARY)
            self.service.trigger_preview({
                "action": "stop",
                "show": False
            })
        else:
            # เปิดทดสอบ
            self._is_obs_demo_active = True
            self.btn_demo_obs.setText("⏹️ ปิดทดสอบ OBS")
            self.btn_demo_obs.setStyleSheet("""
                QPushButton {
                    background-color: #dc2626;
                    color: #ffffff;
                    border: 1px solid #ef4444;
                    border-radius: 6px;
                    padding: 6px 14px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #b91c1c;
                }
            """)

            disp_mode = "banner"
            if self.rad_disp_image.isChecked():
                disp_mode = "image"
            elif self.rad_disp_none.isChecked():
                disp_mode = "none"

            cp_code = self.inp_p_single_code.text().strip() or "#join"
            sec = (self.spin_p_single_hr.value() * 3600) + (self.spin_p_single_min.value() * 60) + self.spin_p_single_sec.value()
            if sec <= 0:
                sec = 60

            self.service.update_overlay_settings(
                overlay_display_mode=disp_mode,
                overlay_scale=self.slider_scale.value(),
                overlay_font_size=self.slider_font.value(),
                overlay_offset_x=self.slider_ox.value(),
                overlay_offset_y=self.slider_oy.value(),
                overlay_anim_in=self.cmb_anim_in.currentData() if hasattr(self, "cmb_anim_in") else "slide",
                overlay_anim_out=self.cmb_anim_out.currentData() if hasattr(self, "cmb_anim_out") else "slide",
                overlay_image_path=self.inp_img_path.text().strip(),
                custom_image_path=self.inp_img_path.text().strip()
            )
            self.service.trigger_preview({
                "action": "start",
                "show": True,
                "stay": True,
                "cp_index": 1,
                "code": cp_code,
                "duration": sec,
                "mode": "single" if self.cmb_p_mode.currentIndex() == 0 else "multi",
                "total_checkpoints": 1
            })



    # ─────────────────────────────────────────────────────────────

    def _export_full_csv(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export รายชื่อผู้เข้าร่วมและผู้โชคดี",
            "giveaway_results.csv",
            "CSV Files (*.csv)"
        )
        if path:
            self.service.export_csv(path)
            QMessageBox.information(self, "สำเร็จ", f"Export ผลกิจกรรมเรียบร้อยแล้ว:\n{path}")

    def _finish_and_reset_activity(self):
        ans = QMessageBox.question(
            self,
            "จบกิจกรรม",
            "ต้องการจบกิจกรรมรอบนี้ และล้างข้อมูลเพื่อเริ่มรอบใหม่หรือไม่?",
            QMessageBox.Yes | QMessageBox.No
        )
        if ans == QMessageBox.Yes:
            self.service.clear_all_data()
            self.service.broadcast_draw_reset()
            self.current_live_step = 1
            self.live_step_stack.setCurrentIndex(0)
            self._update_live_stepper_style(1)
            self._load_initial_live_presets()

    # Page 2 removed (no prizes)
    def _build_prize_set_ui(self, widget: QWidget):
        pass

    def _reload_prize_set_ui(self):
        pass

    def _connect_service_signals(self):
        self.service.participant_added.connect(self._on_participant_added)
        self.service.checkpoint_ended.connect(lambda idx, tot: self._on_live_checkpoint_stopped())

    def _on_participant_added(self, p, cp_index: int):
        self.realtime_participants_count += 1
        if hasattr(self, "lbl_realtime_count"):
            self.lbl_realtime_count.setText(f"{self.realtime_participants_count} คน")

        if hasattr(self, "table_realtime"):
            self.table_realtime.insertRow(0)
            self.table_realtime.setItem(0, 0, QTableWidgetItem(getattr(p, "platform", "").upper()))
            self.table_realtime.setItem(0, 1, QTableWidgetItem(getattr(p, "author", "")))
            self.table_realtime.setItem(0, 2, QTableWidgetItem(time.strftime("%H:%M:%S")))

    def _is_widget_installed(self) -> bool:
        try:
            app_inst = None
            if hasattr(self, "service") and self.service:
                if hasattr(self.service, "app"):
                    app_inst = self.service.app
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
        return True

    def _check_widget_status(self):
        installed = self._is_widget_installed()
        if installed:
            if self.stack.currentIndex() != 0:
                self.stack.setCurrentIndex(0)
        else:
            if self.stack.currentIndex() != 1:
                self.stack.setCurrentIndex(1)

    def _build_not_installed_view(self) -> QWidget:
        blocker = QWidget()
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
        title_lbl.setStyleSheet("font-size: 16px; font-weight: 800; color: #f59e0b;")
        v.addWidget(title_lbl)

        desc_lbl = QLabel('กรุณาเปิด Overlay Composer แล้วกดปุ่ม "+ Giveaway" เพื่อวาง Widget ลงบนหน้าจอก่อนครับ')
        desc_lbl.setAlignment(Qt.AlignCenter)
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet("font-size: 13px; color: #94a3b8;")
        v.addWidget(desc_lbl)

        btn_open = QPushButton("🌐 เปิด Overlay Composer เพื่อเพิ่ม Widget")
        btn_open.setStyleSheet(STYLE_BTN_PRIMARY)
        btn_open.clicked.connect(self._on_open_composer_clicked)
        v.addWidget(btn_open)

        btn_check = QPushButton("🔄 ตรวจสอบอีกครั้ง")
        btn_check.setStyleSheet(STYLE_BTN_SECONDARY)
        btn_check.clicked.connect(self._check_widget_status)
        v.addWidget(btn_check)

        v.addStretch()
        return blocker

    def _on_open_composer_clicked(self):
        try:
            import webbrowser
            webbrowser.open("http://localhost:8080/composer")
        except Exception:
            pass
