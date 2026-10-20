"""ui/dialogs/setup_wizard.py — หน้าต่างเริ่มต้นการตั้งค่าระบบ (First-Run Setup Wizard)

ช่วยแนะนำผู้ใช้งานใหม่ในการตั้งค่าระบบที่สำคัญ 3 ขั้นตอน:
1. การเพิ่มข้อยกเว้นความปลอดภัย Windows Defender เพื่อให้อัปเดตได้ตามปกติ
2. การระบุข้อมูลและเปิดใช้งานแพลตฟอร์มถ่ายทอดสดที่ต้องการดึงข้อความ
3. การเลือกระบบเสียงอ่านข้อความ หรือปิดการอ่านเสียง
"""
from __future__ import annotations

import os
from typing import Optional

from PySide6.QtWidgets import (
    QDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QCheckBox,
    QRadioButton,
    QButtonGroup,
    QStackedWidget,
    QFrame,
    QSizePolicy,
)
from PySide6.QtGui import QColor, QFont
from PySide6.QtCore import Qt, Signal

from defender_helper import DefenderExclusionManager


class FirstRunWizardDialog(QDialog):
    """หน้าต่างตัวช่วยการตั้งค่าระบบสำหรับการเปิดใช้งานครั้งแรก"""

    wizard_completed = Signal()

    def __init__(self, parent_app=None) -> None:
        super().__init__(parent_app if isinstance(parent_app, QWidget) else None)
        self.parent_app = parent_app
        self.settings = getattr(parent_app, "settings", None)

        self.setWindowTitle("เริ่มต้นการตั้งค่าระบบ - Broadcast Playroom")
        self.setFixedSize(720, 620)
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        # รูปแบบดีไซน์หลัก
        self.setStyleSheet("""
            QDialog {
                background-color: #0b0f19;
                color: #f1f5f9;
                font-family: 'Segoe UI', 'Noto Sans Thai', Tahoma, sans-serif;
            }
            QLabel {
                color: #e2e8f0;
                background: transparent;
            }
            QLineEdit {
                background-color: #131d31;
                border: 1px solid #1e293b;
                border-radius: 6px;
                padding: 6px 12px;
                color: #f8fafc;
                font-size: 13px;
            }
            QLineEdit:focus {
                border-color: #38bdf8;
                background-color: #16233d;
            }
            QCheckBox {
                color: #cbd5e1;
                font-size: 12.5px;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 17px;
                height: 17px;
                border-radius: 4px;
                border: 1.5px solid #334155;
                background-color: #0f172a;
            }
            QCheckBox::indicator:hover {
                border-color: #38bdf8;
            }
            QCheckBox::indicator:checked {
                background-color: #0284c7;
                border-color: #38bdf8;
            }
            QRadioButton {
                spacing: 8px;
            }
            QRadioButton::indicator {
                width: 18px;
                height: 18px;
                border-radius: 9px;
                border: 2px solid #334155;
                background-color: #0f172a;
            }
            QRadioButton::indicator:hover {
                border-color: #38bdf8;
            }
            QRadioButton::indicator:checked {
                border-color: #38bdf8;
                background-color: #0284c7;
            }
            QPushButton {
                border-radius: 6px;
                font-weight: 600;
                font-size: 13px;
                padding: 8px 18px;
            }
        """)

        self._build_ui()
        self._update_navigation_state()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(32, 24, 32, 20)
        main_layout.setSpacing(16)

        # ── 1. ส่วนหัวและแถบขั้นตอน ──
        header_box = QVBoxLayout()
        header_box.setSpacing(4)

        title_lbl = QLabel("ยินดีต้อนรับสู่ Broadcast Playroom")
        title_lbl.setStyleSheet("font-size: 19px; font-weight: 700; color: #f8fafc;")
        header_box.addWidget(title_lbl)

        subtitle_lbl = QLabel("กรุณาตั้งค่าการทำงานเบื้องต้นเพื่อให้ระบบสามารถทำงานได้อย่างมีประสิทธิภาพ")
        subtitle_lbl.setStyleSheet("font-size: 12.5px; color: #94a3b8;")
        header_box.addWidget(subtitle_lbl)

        # เส้นขั้นตอน
        steps_row = QHBoxLayout()
        steps_row.setSpacing(12)
        steps_row.setContentsMargins(0, 8, 0, 0)

        self.step_labels = []
        step_titles = [
            "1. ข้อยกเว้นความปลอดภัย",
            "2. เชื่อมต่อแพลตฟอร์ม",
            "3. ระบบเสียงอ่านข้อความ",
        ]

        for i, text in enumerate(step_titles):
            pill = QLabel(text)
            pill.setAlignment(Qt.AlignCenter)
            pill.setFixedHeight(28)
            steps_row.addWidget(pill)
            self.step_labels.append(pill)

        header_box.addLayout(steps_row)
        main_layout.addLayout(header_box)

        # เส้นคั่น
        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setStyleSheet("background-color: #1e293b; max-height: 1px;")
        main_layout.addWidget(divider)

        # ── 2. ส่วนเนื้อหาแต่ละขั้นตอน ──
        self.stack = QStackedWidget()
        self.stack.addWidget(self._create_step1_widget())
        self.stack.addWidget(self._create_step2_widget())
        self.stack.addWidget(self._create_step3_widget())
        main_layout.addWidget(self.stack, 1)

        # เส้นคั่นล่าง
        divider2 = QFrame()
        divider2.setFrameShape(QFrame.HLine)
        divider2.setStyleSheet("background-color: #1e293b; max-height: 1px;")
        main_layout.addWidget(divider2)

        # ── 3. แถบปุ่มนำทาง ──
        footer = QHBoxLayout()
        footer.setSpacing(12)

        self.btn_skip = QPushButton("ข้ามการตั้งค่า")
        self.btn_skip.setCursor(Qt.PointingHandCursor)
        self.btn_skip.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #64748b;
                border: 1px solid #1e293b;
            }
            QPushButton:hover {
                color: #94a3b8;
                border-color: #334155;
                background-color: #0f172a;
            }
        """)
        self.btn_skip.clicked.connect(self._on_skip_clicked)
        footer.addWidget(self.btn_skip)

        footer.addStretch()

        self.btn_back = QPushButton("ย้อนกลับ")
        self.btn_back.setCursor(Qt.PointingHandCursor)
        self.btn_back.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #cbd5e1;
                border: 1px solid #334155;
            }
            QPushButton:hover {
                background-color: #27354f;
                color: #ffffff;
            }
        """)
        self.btn_back.clicked.connect(self._on_back_clicked)
        footer.addWidget(self.btn_back)

        self.btn_next = QPushButton("ถัดไป")
        self.btn_next.setCursor(Qt.PointingHandCursor)
        self.btn_next.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: #ffffff;
                border: 1px solid #38bdf8;
                min-width: 90px;
            }
            QPushButton:hover {
                background-color: #0369a1;
            }
            QPushButton:pressed {
                background-color: #075985;
            }
        """)
        self.btn_next.clicked.connect(self._on_next_clicked)
        footer.addWidget(self.btn_next)

        main_layout.addLayout(footer)

    # ════════════════════════════════════════════════════════════════
    # ขั้นตอนที่ 1: ตั้งค่าให้โปรแกรมสามารถอัพเดทได้ตามปกติ
    # ════════════════════════════════════════════════════════════════
    def _create_step1_widget(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(14)

        header_lbl = QLabel("ขั้นตอนที่ 1 : ตั้งค่าให้โปรแกรมสามารถอัพเดทได้ตามปกติ")
        header_lbl.setStyleSheet("font-size: 15px; font-weight: 700; color: #38bdf8;")
        layout.addWidget(header_lbl)

        desc_lbl = QLabel(
            "จำเป็นต้องเพิ่มข้อยกเว้นให้กันโปรแกรม เพื่อให้ระบบอนุญาตให้โปรแกรมสามารถอัพเดทได้เมื่อมีเวอร์ชั่นใหม่ "
            "หากไม่ทำการเพิ่มข้อยกเว้น Windows Defender แล้วกดอัพเดท โปรแกรมจะถูกลบโดยอัตโนมัติ "
            "กรุณาเพิ่มข้อยกเว้นให้เรียบร้อยก่อนอัพเดท"
        )
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet("font-size: 13px; color: #cbd5e1; line-height: 1.6;")
        layout.addWidget(desc_lbl)

        # การ์ดปุ่มและคำแนะนำ
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #10192b;
                border: 1px solid #1e293b;
                border-radius: 8px;
                padding: 16px;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(12)

        # ปุ่มเพิ่มข้อยกเว้น (เต็มความกว้างจากซ้ายสุดไปขวาสุด)
        self.btn_apply_defender = QPushButton("🛡️ เพิ่มข้อยกเว้น Windows Defender ทันที")
        self.btn_apply_defender.setFixedHeight(44)
        self.btn_apply_defender.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_apply_defender.setCursor(Qt.PointingHandCursor)
        self.btn_apply_defender.setStyleSheet("""
            QPushButton {
                background-color: #059669;
                color: #ffffff;
                font-weight: 700;
                font-size: 14px;
                border: 1px solid #34d399;
                border-radius: 6px;
                width: 100%;
            }
            QPushButton:hover {
                background-color: #047857;
            }
            QPushButton:pressed {
                background-color: #065f46;
            }
            QPushButton:disabled {
                background-color: #1e293b;
                color: #64748b;
                border-color: #334155;
            }
        """)
        self.btn_apply_defender.clicked.connect(self._on_apply_defender)
        card_layout.addWidget(self.btn_apply_defender)

        self.defender_status_lbl = QLabel("สถานะ: ยังไม่ได้ดำเนินการ")
        self.defender_status_lbl.setAlignment(Qt.AlignCenter)
        self.defender_status_lbl.setStyleSheet("font-size: 12.5px; color: #64748b; font-weight: 600;")
        card_layout.addWidget(self.defender_status_lbl)

        uac_notice_lbl = QLabel("เมื่อกดปุ่มจะมีหน้าต่างแจ้งเตือนเต็มจอขึ้นมา ให้กดปุ่ม Yes เพื่อยืนยันการตั้งค่า")
        uac_notice_lbl.setAlignment(Qt.AlignCenter)
        uac_notice_lbl.setStyleSheet("font-size: 12px; color: #94a3b8;")
        card_layout.addWidget(uac_notice_lbl)

        layout.addWidget(card)

        # กล่องแจ้งเตือน [! icon]
        tip_box = QFrame()
        tip_box.setStyleSheet("""
            QFrame {
                background-color: #141f1a;
                border: 1px solid #065f46;
                border-left: 4px solid #10b981;
                border-radius: 6px;
                padding: 10px 14px;
            }
        """)
        tip_layout = QHBoxLayout(tip_box)
        tip_layout.setContentsMargins(0, 0, 0, 0)
        tip_layout.setSpacing(10)

        icon_lbl = QLabel("💡")
        icon_lbl.setStyleSheet("font-size: 16px;")
        tip_layout.addWidget(icon_lbl)

        tip_text_lbl = QLabel(
            "หลังจากทำการเพิ่มข้อยกเว้นไปแล้ว หากทำการย้ายตำแหน่งโปรแกรมไปยังโฟลเดอร์อื่น "
            "กรุณาทำการตั้งค่า เพิ่มข้อยกเว้นใหม่อีกครั้ง ใน Setting ของโปรแกรม"
        )
        tip_text_lbl.setWordWrap(True)
        tip_text_lbl.setStyleSheet("font-size: 12.5px; color: #6ee7b7; line-height: 1.5;")
        tip_layout.addWidget(tip_text_lbl, 1)

        layout.addWidget(tip_box)
        layout.addStretch()
        return widget

    def _on_apply_defender(self) -> None:
        success = DefenderExclusionManager.apply_one_click_exclusion()
        if success:
            self.defender_status_lbl.setText("สถานะ: ส่งคำขอไปยังระบบเรียบร้อยแล้ว กรุณากดยืนยันบนหน้าต่าง Windows")
            self.defender_status_lbl.setStyleSheet("font-size: 12.5px; color: #34d399; font-weight: 700;")
            self.btn_apply_defender.setEnabled(False)
            self.btn_apply_defender.setText("✓ ดำเนินการส่งคำขอแล้ว")
        else:
            self.defender_status_lbl.setText("สถานะ: ไม่สามารถส่งคำขอได้ สามารถข้ามขั้นตอนนี้ได้")
            self.defender_status_lbl.setStyleSheet("font-size: 12.5px; color: #f87171; font-weight: 600;")

    # ════════════════════════════════════════════════════════════════
    # ขั้นตอนที่ 2 : ตั้งค่าแพลตฟอร์มที่ต้องการดึงข้อความมาแสดงในโปรแกรม
    # ════════════════════════════════════════════════════════════════
    def _create_step2_widget(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(10)

        header_lbl = QLabel("ขั้นตอนที่ 2 : ตั้งค่าแพลตฟอร์มที่ต้องการดึงข้อความมาแสดงในโปรแกรม")
        header_lbl.setStyleSheet("font-size: 15px; font-weight: 700; color: #38bdf8;")
        layout.addWidget(header_lbl)

        desc_lbl = QLabel(
            "กรอกชื่อช่องสตรีมของคุณ ตามแพลตฟอร์มที่ต้องการเชื่อมต่อให้ถูกต้อง "
            "แพลตฟอร์มใดที่ไม่ได้กรอก จะถูกซ่อนจากหน้าแรกของโปรแกรมโดยอัตโนมัติ"
        )
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet("font-size: 12.5px; color: #94a3b8; line-height: 1.4;")
        layout.addWidget(desc_lbl)

        # รายการแพลตฟอร์ม เรียงลำดับ: Twitch, Youtube, MyLive, Soop, KICK, Tiktok
        grid = QVBoxLayout()
        grid.setSpacing(6)

        def _make_row(label_text: str, color_hex: str, placeholder: str):
            row = QHBoxLayout()
            row.setSpacing(10)
            lbl = QLabel(label_text)
            lbl.setFixedWidth(75)
            lbl.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {color_hex};")
            input_box = QLineEdit()
            input_box.setFixedHeight(32)
            input_box.setPlaceholderText(placeholder)
            cb = QCheckBox("เชื่อมต่ออัตโนมัติ")
            row.addWidget(lbl)
            row.addWidget(input_box, 1)
            row.addWidget(cb)
            grid.addLayout(row)
            return input_box, cb

        # 1. Twitch
        self.input_twitch, self.cb_auto_twitch = _make_row(
            "Twitch:", "#c084fc", "ชื่อช่อง Twitch เช่น shoptwitch"
        )
        # 2. Youtube
        self.input_youtube, self.cb_auto_youtube = _make_row(
            "Youtube:", "#f87171", "ลิงก์ถ่ายทอดสด หรือ Channel ID เช่น @ChannelName"
        )
        # 3. MyLive
        self.input_mylive, self.cb_auto_mylive = _make_row(
            "MyLive:", "#fbbf24", "ลิงก์ห้องถ่ายทอดสด MyLive"
        )
        # 4. Soop
        self.input_soop, self.cb_auto_soop = _make_row(
            "Soop:", "#38bdf8", "รหัสช่อง BJ ID เช่น mychannel"
        )
        # 5. KICK
        self.input_kick, self.cb_auto_kick = _make_row(
            "KICK:", "#4ade80", "ชื่อช่อง KICK เช่น mykickchannel"
        )
        # 6. Tiktok
        self.input_tiktok, self.cb_auto_tiktok = _make_row(
            "Tiktok:", "#a78bfa", "ชื่อผู้ใช้งาน TikTok เช่น @username"
        )

        layout.addLayout(grid)
        layout.addStretch()
        return widget

    # ════════════════════════════════════════════════════════════════
    # ขั้นตอนที่ 3 : การเลือกรูปแบบเสียงอ่านข้อความ
    # ════════════════════════════════════════════════════════════════
    def _create_step3_widget(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(12)

        header_lbl = QLabel("ขั้นตอนที่ 3 : การเลือกรูปแบบเสียงอ่านข้อความ")
        header_lbl.setStyleSheet("font-size: 15px; font-weight: 700; color: #38bdf8;")
        layout.addWidget(header_lbl)

        desc_lbl = QLabel(
            "กรุณาเลือกลักษณะเสียงที่ต้องการใช้งานสำหรับการอ่านข้อความสนทนา หรือเลือกปิดเสียงอ่านหากต้องการแสดงผลเฉพาะข้อความ"
        )
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet("font-size: 12.5px; color: #94a3b8; line-height: 1.4;")
        layout.addWidget(desc_lbl)

        self.voice_group = QButtonGroup(self)

        # กล่องตัวเลือก 1: เสียงผู้หญิง
        box_female = QFrame()
        box_female.setStyleSheet("""
            QFrame {
                background-color: #10192b;
                border: 1px solid #1e293b;
                border-radius: 8px;
                padding: 10px 14px;
            }
        """)
        bf_layout = QVBoxLayout(box_female)
        bf_layout.setSpacing(3)
        self.rb_female = QRadioButton("เสียงผู้หญิง - เสียงภาษาไทยมาตรฐาน")
        self.rb_female.setChecked(True)
        self.rb_female.setStyleSheet("font-size: 13.5px; font-weight: 700; color: #f8fafc;")
        self.voice_group.addButton(self.rb_female, 1)
        bf_layout.addWidget(self.rb_female)
        desc_f = QLabel("น้ำเสียงนุ่มนวลและเป็นธรรมชาติ เหมาะสำหรับการอ่านข้อความทั่วไป")
        desc_f.setStyleSheet("font-size: 12px; color: #94a3b8; padding-left: 26px;")
        bf_layout.addWidget(desc_f)
        layout.addWidget(box_female)

        # กล่องตัวเลือก 2: เสียงผู้ชาย
        box_male = QFrame()
        box_male.setStyleSheet("""
            QFrame {
                background-color: #10192b;
                border: 1px solid #1e293b;
                border-radius: 8px;
                padding: 10px 14px;
            }
        """)
        bm_layout = QVBoxLayout(box_male)
        bm_layout.setSpacing(3)
        self.rb_male = QRadioButton("เสียงผู้ชาย - เสียงภาษาไทยมาตรฐาน")
        self.rb_male.setStyleSheet("font-size: 13.5px; font-weight: 700; color: #f8fafc;")
        self.voice_group.addButton(self.rb_male, 2)
        bm_layout.addWidget(self.rb_male)
        desc_m = QLabel("น้ำเสียงสุภาพและหนักแน่น เหมาะสำหรับการอ่านข้อความทั่วไป")
        desc_m.setStyleSheet("font-size: 12px; color: #94a3b8; padding-left: 26px;")
        bm_layout.addWidget(desc_m)
        layout.addWidget(box_male)

        # กล่องตัวเลือก 3: ปิดการทำงานของระบบอ่านข้อความเสียง
        box_mute = QFrame()
        box_mute.setStyleSheet("""
            QFrame {
                background-color: #10192b;
                border: 1px solid #1e293b;
                border-radius: 8px;
                padding: 10px 14px;
            }
        """)
        bmu_layout = QVBoxLayout(box_mute)
        bmu_layout.setSpacing(3)
        self.rb_mute = QRadioButton("ปิดการทำงานของระบบอ่านข้อความเสียง")
        self.rb_mute.setStyleSheet("font-size: 13.5px; font-weight: 700; color: #f87171;")
        self.voice_group.addButton(self.rb_mute, 3)
        bmu_layout.addWidget(self.rb_mute)
        desc_mu = QLabel("ปิดระบบอ่านเสียงข้อความทั้งหมด ใช้แต่ระบบดึงแชทเท่านั้น (สามารถกดเปิดอ่านแชทได้ในหน้าแรกของโปรแกรม)")
        desc_mu.setWordWrap(True)
        desc_mu.setStyleSheet("font-size: 12px; color: #94a3b8; padding-left: 26px;")
        bmu_layout.addWidget(desc_mu)
        layout.addWidget(box_mute)

        layout.addStretch()
        return widget

    # ════════════════════════════════════════════════════════════════
    # การควบคุมการเปลี่ยนหน้า
    # ════════════════════════════════════════════════════════════════
    def _update_navigation_state(self) -> None:
        idx = self.stack.currentIndex()

        for i, lbl in enumerate(self.step_labels):
            if i == idx:
                lbl.setStyleSheet("""
                    background-color: #0284c7;
                    color: #ffffff;
                    font-weight: 700;
                    font-size: 12px;
                    border-radius: 14px;
                    padding: 0 12px;
                """)
            elif i < idx:
                lbl.setStyleSheet("""
                    background-color: #1e293b;
                    color: #38bdf8;
                    font-weight: 600;
                    font-size: 12px;
                    border-radius: 14px;
                    padding: 0 12px;
                """)
            else:
                lbl.setStyleSheet("""
                    background-color: #10192b;
                    color: #64748b;
                    font-size: 12px;
                    border-radius: 14px;
                    padding: 0 12px;
                """)

        self.btn_back.setVisible(idx > 0)

        if idx == 2:
            self.btn_next.setText("เสร็จสิ้นการตั้งค่า")
            self.btn_next.setStyleSheet("""
                QPushButton {
                    background-color: #059669;
                    color: #ffffff;
                    border: 1px solid #34d399;
                    min-width: 130px;
                }
                QPushButton:hover {
                    background-color: #047857;
                }
            """)
        else:
            self.btn_next.setText("ถัดไป")
            self.btn_next.setStyleSheet("""
                QPushButton {
                    background-color: #0284c7;
                    color: #ffffff;
                    border: 1px solid #38bdf8;
                    min-width: 90px;
                }
                QPushButton:hover {
                    background-color: #0369a1;
                }
            """)

    def _on_next_clicked(self) -> None:
        idx = self.stack.currentIndex()
        if idx < 2:
            self.stack.setCurrentIndex(idx + 1)
            self._update_navigation_state()
        else:
            self._apply_and_finish()

    def _on_back_clicked(self) -> None:
        idx = self.stack.currentIndex()
        if idx > 0:
            self.stack.setCurrentIndex(idx - 1)
            self._update_navigation_state()

    def _on_skip_clicked(self) -> None:
        self._mark_first_run_done()
        self.reject()

    # ════════════════════════════════════════════════════════════════
    # บันทึกและนำการตั้งค่าไปใช้งานจริง
    # ════════════════════════════════════════════════════════════════
    def _apply_and_finish(self) -> None:
        """บันทึกการตั้งค่าลง settings และแจ้งแอปพลิเคชันหลักให้อัปเดต UI"""
        s = self.settings
        if s is not None:
            # 1. แพลตฟอร์ม เรียงลำดับ: Twitch, Youtube, MyLive, Soop, KICK, Tiktok
            tw = self.input_twitch.text().strip()
            yt = self.input_youtube.text().strip()
            ml = self.input_mylive.text().strip()
            sp = self.input_soop.text().strip()
            kc = self.input_kick.text().strip()
            tt = self.input_tiktok.text().strip()

            s.twitch_channel = tw
            s.youtube_url = yt
            s.mylive_url = ml
            s.soop_bid = sp
            s.kick_channel = kc
            s.tiktok_username = tt

            s.auto_connect_twitch = self.cb_auto_twitch.isChecked()
            s.auto_connect_youtube = self.cb_auto_youtube.isChecked()
            s.auto_connect_mylive = self.cb_auto_mylive.isChecked()
            s.auto_connect_soop = self.cb_auto_soop.isChecked()
            s.auto_connect_kick = self.cb_auto_kick.isChecked()
            s.auto_connect_tiktok = self.cb_auto_tiktok.isChecked()

            # กำหนดการแสดงผลบนแถบด้านซ้าย (แสดงเฉพาะอันที่กรอก)
            has_any = any([tw, yt, ml, sp, kc, tt])
            if has_any:
                s.show_twitch = bool(tw)
                s.show_youtube = bool(yt)
                s.show_mylive = bool(ml)
                s.show_soop = bool(sp)
                s.show_kick = bool(kc)
                s.show_tiktok = bool(tt)
            else:
                s.show_twitch = True
                s.show_youtube = True
                s.show_mylive = False
                s.show_soop = False
                s.show_kick = False
                s.show_tiktok = False

            # 2. ระบบเสียงอ่านข้อความ
            if self.rb_mute.isChecked():
                s.tts_muted = True
            elif self.rb_male.isChecked():
                s.tts_muted = False
                s.edge_voice = "niwat"
            else:
                s.tts_muted = False
                s.edge_voice = "premwadee"

            try:
                from settings import save_settings
                save_settings(s)
            except Exception as e:
                print(f"Failed to save settings from wizard: {e}")

        # อัปเดต UI ของหน้าต่างหลัก
        app = self.parent_app
        if app is not None:
            if hasattr(app, "_rebuild_platform_cards"):
                app._rebuild_platform_cards()
            if hasattr(app, "_refresh_voice_panel"):
                app._refresh_voice_panel()
            if hasattr(app, "sidebar") and app.sidebar:
                master_muted = getattr(s, "tts_muted", False) if s else False
                app.sidebar.set_master_muted(master_muted)

        self._mark_first_run_done()
        self.wizard_completed.emit()
        self.accept()

    def _mark_first_run_done(self) -> None:
        """สร้างไฟล์ marker เพื่อไม่ให้ Wizard แสดงซ้ำอีกในการเปิดครั้งต่อไป"""
        try:
            from data_dir import get_data_dir
            marker_path = os.path.join(get_data_dir(), ".first_run_done")
            with open(marker_path, "w", encoding="utf-8") as f:
                f.write("1")
        except Exception:
            pass
