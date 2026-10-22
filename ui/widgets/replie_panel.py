# -*- coding: utf-8 -*-

"""replie_panel.py — แผงควบคุมและจัดการคำสั่ง Replie (โต้ตอบภาพและข้อความบน OBS Overlay)



ปรับปรุงสถาปัตยกรรม UI/UX ใหม่ทั้งหมด:

1. หน้าต่างหลัก (RepliePanel):

   - ตารางคำสั่งความสูงเหมาะสม ไม่ตัดขอบปุ่ม

   - ปุ่มลบใช้ไอคอน 🗑 ล้วน ไม่มีตัว X

   - ปุ่ม DEMO / EDIT / 🗑 แสดงผลได้เต็มตัวอักษร ไม่ถูกบีบ

   - แถบโหมดวนลูป (AFK) กะทัดรัด ตัวหนังสือไม่ล้น

   - โหมด Edit / OK ด้านขวาบน สำหรับติ๊กเปิด/ปิดคำสั่ง

2. หน้าต่างสร้างและแก้ไขคำสั่ง (ReplieEditDialog):

   - ดีไซน์ Flat ทันสมัย ไร้กรอบซ้อนกรอบ (No nested bordered boxes)

   - จัดวางช่องกรอกและปุ่มเลือกอย่างสะอาดตาและเป็นสัดส่วน

   - ไม้บรรทัดไทม์ไลน์เลเยอร์ (Video Editor Timeline) สำหรับลากตั้งดีเลย์

   - เมนูตั้งค่าเพิ่มเติม (อนิเมชัน & นับถอยหลัง) พับเก็บ/กางออกได้แบบไร้กรอบหนา

"""

from __future__ import annotations



import os

from typing import Optional, Dict



from PySide6.QtCore import Qt, Signal, QTimer

from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPixmap, QLinearGradient

from PySide6.QtWidgets import (

    QGraphicsDropShadowEffect,

    QFrame, QLabel, QLineEdit, QPushButton, QVBoxLayout, QHBoxLayout,

    QWidget, QSizePolicy, QRadioButton, QButtonGroup, QCheckBox,

    QScrollArea, QComboBox, QMessageBox, QTabWidget, QSlider,

    QDialog, QFileDialog, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView,

    QColorDialog, QStackedWidget

)



ANIM_IN_OPTIONS = [

    ("slide-up", "Slide จากด้านล่างขึ้นบน"),

    ("slide-down", "Slide จากด้านบนลงล่าง"),

    ("slide-left", "Slide จากขวามาซ้าย"),

    ("slide-right", "Slide จากซ้ายมาขวา"),

    ("fade", "Fade ค่อยๆ ปรากฏตัว"),

    ("zoom", "Zoom ขยายตัวขึ้นมา"),

]



ANIM_OUT_OPTIONS = [

    ("slide-down", "Slide กลับลงด้านล่าง"),

    ("slide-up", "Slide กลับขึ้นด้านบน"),

    ("slide-right", "Slide กลับไปด้านขวา"),

    ("slide-left", "Slide กลับไปด้านซ้าย"),

    ("fade", "Fade ค่อยๆ จางหายไป"),

    ("zoom", "Zoom หดตัวหายไป"),

]



PROGRESS_OPTIONS = [

    ("cyan", "⚡ สีนีออนฟ้า"),

    ("gold", "👑 สีทองประกาย"),

    ("violet", "💜 สีม่วงนีออน"),

    ("emerald", "💎 สีเขียวมรกต"),

    ("rainbow", "🌈 สีสายรุ้งเคลื่อนไหว"),

    ("sunset", "🌅 สีส้มซันเซ็ต"),

]



FONT_OPTIONS = [

    "Kanit",

    "Prompt",

    "Segoe UI",

    "Impact",

    "Montserrat",

    "Arial",

    "Sukhumvit Set",

    "Courier New"

]





# ════════════════════════════════════════════════════════════════════════════

# 🎞️ Video Editor Timeline Widget (ไทม์ไลน์เลเยอร์แบบโปรแกรมตัดต่อ)

# ════════════════════════════════════════════════════════════════════════════

class ReplieTimelineWidget(QFrame):

    """วิดเจ็ตไทม์ไลน์แบบตัดต่อวิดีโอ (Video Editor Timeline)"""

    delayChanged = Signal(float)

    subCommandRemoved = Signal()



    def __init__(self, parent=None):

        super().__init__(parent)

        self.setFixedHeight(132)

        self.setMinimumWidth(380)

        self.setStyleSheet("""

            ReplieTimelineWidget {

                background: #070d19;

                border: 1px solid #1e293b;

                border-radius: 8px;

            }

        """)

        self.setMouseTracking(True)



        self.total_duration: float = 15.0

        self.base_name: str = "!command"

        self.base_type: str = "ticker"

        self.sub_name: Optional[str] = None

        self.sub_type: str = "image"

        self.sub_delay: float = 2.5



        self._dragging: bool = False

        self._drag_start_x: int = 0

        self._initial_delay: float = 0.0



    def set_data(self, total_duration: float, base_name: str, base_type: str,

                 sub_name: Optional[str] = None, sub_type: str = "image", sub_delay: float = 0.0):

        self.total_duration = max(2.0, float(total_duration))

        self.base_name = base_name or "!cmd"

        self.base_type = base_type

        self.sub_name = sub_name

        self.sub_type = sub_type

        self.sub_delay = max(0.0, min(float(sub_delay), self.total_duration - 1.0))

        self.update()



    def _get_geometry_info(self):

        w = self.width()

        left_margin = 65

        right_margin = 20

        track_w = max(100, w - left_margin - right_margin)

        return left_margin, track_w



    def paintEvent(self, event):

        super().paintEvent(event)

        painter = QPainter(self)

        painter.setRenderHint(QPainter.Antialiasing)



        w = self.width()

        left_m, track_w = self._get_geometry_info()



        # 1. ไม้บรรทัดเวลาด้านบน (Ruler)

        ruler_h = 32

        painter.fillRect(0, 0, w, ruler_h, QColor("#0d1527"))

        painter.setPen(QColor("#1e293b"))

        painter.drawLine(0, ruler_h, w, ruler_h)



        # Draw time markings (ยกตัวเลขเวลาขึ้นด้านบน เว้นระยะห่างด้านล่าง)

        painter.setFont(QFont("Segoe UI", 9))

        painter.setPen(QColor("#64748b"))

        

        step_sec = 5 if self.total_duration >= 15 else (2 if self.total_duration >= 8 else 1)

        cur_t = 0

        while cur_t <= self.total_duration:

            ratio = cur_t / self.total_duration

            x = int(left_m + ratio * track_w)

            painter.drawLine(x, 22, x, ruler_h)

            time_str = f"00:{int(cur_t):02d}"

            painter.drawText(x - 18, 4, 36, 16, Qt.AlignCenter, time_str)

            cur_t += step_sec



        # 2. Track 1: คำสั่งแทรก (Upper Track - Sub Command) เว้น padding จาก ruler 10px

        t1_y = 42

        t1_h = 36



        painter.setFont(QFont("Kanit", 9, QFont.Bold))

        painter.setPen(QColor("#94a3b8"))

        painter.drawText(8, t1_y + 8, 52, 20, Qt.AlignLeft | Qt.AlignVCenter, "ชั้นที่ 2")



        if self.sub_name:

            x_start = left_m + int((self.sub_delay / self.total_duration) * track_w)

            x_end = left_m + track_w

            bar_w = max(30, x_end - x_start)



            grad = QLinearGradient(x_start, t1_y, x_end, t1_y + t1_h)

            grad.setColorAt(0.0, QColor("#9333ea"))

            grad.setColorAt(1.0, QColor("#7e22ce"))

            painter.setBrush(QBrush(grad))

            painter.setPen(QPen(QColor("#c084fc"), 1.5))

            painter.drawRoundedRect(x_start, t1_y, bar_w, t1_h, 6, 6)



            painter.setPen(QPen(QColor("#f3e8ff"), 1.5))

            painter.drawLine(x_start + 4, t1_y + 8, x_start + 4, t1_y + t1_h - 8)

            painter.drawLine(x_start + 7, t1_y + 8, x_start + 7, t1_y + t1_h - 8)



            sub_icon = "🖼️" if self.sub_type == "image" else "🗨"

            txt = f"{sub_icon} {self.sub_name} (เริ่ม {self.sub_delay:.1f}s — จบ {self.total_duration:.0f}s)"

            painter.setPen(QColor("#ffffff"))

            painter.setFont(QFont("Kanit", 9, QFont.Bold))

            painter.drawText(x_start + 14, t1_y, bar_w - 38, t1_h, Qt.AlignLeft | Qt.AlignVCenter, txt)



            painter.setPen(QColor("#fca5a5"))

            painter.setFont(QFont("Segoe UI", 10, QFont.Bold))

            painter.drawText(x_end - 22, t1_y, 20, t1_h, Qt.AlignCenter, "✕")

        else:

            painter.setPen(QPen(QColor("#334155"), 1, Qt.DashLine))

            painter.setBrush(QBrush(QColor("#0b1222")))

            painter.drawRoundedRect(left_m, t1_y, track_w, t1_h, 6, 6)

            painter.setPen(QColor("#64748b"))

            painter.setFont(QFont("Kanit", 9))

            painter.drawText(left_m, t1_y, track_w, t1_h, Qt.AlignCenter, "+ ยังไม่มีคำสั่งแทรก (กดปุ่มแทรกคำสั่งเพิ่มด้านบน)")



        # 3. Track 2: คำสั่งหลัก (Lower Track - Base Command)

        t2_y = 86

        t2_h = 36



        painter.setFont(QFont("Kanit", 9, QFont.Bold))

        painter.setPen(QColor("#94a3b8"))

        painter.drawText(8, t2_y + 8, 52, 20, Qt.AlignLeft | Qt.AlignVCenter, "หลัก (1)")



        grad2 = QLinearGradient(left_m, t2_y, left_m + track_w, t2_y + t2_h)

        grad2.setColorAt(0.0, QColor("#0284c7"))

        grad2.setColorAt(1.0, QColor("#0369a1"))

        painter.setBrush(QBrush(grad2))

        painter.setPen(QPen(QColor("#38bdf8"), 1.5))

        painter.drawRoundedRect(left_m, t2_y, track_w, t2_h, 6, 6)



        base_icon = "🗨" if self.base_type == "ticker" else "🖼️"

        txt2 = f"{base_icon} {self.base_name} (คำสั่งหลัก: เล่นเต็มเวลา 0s — {self.total_duration:.0f}s)"

        painter.setPen(QColor("#ffffff"))

        painter.setFont(QFont("Kanit", 9, QFont.Bold))

        painter.drawText(left_m + 14, t2_y, track_w - 28, t2_h, Qt.AlignLeft | Qt.AlignVCenter, txt2)



    def mousePressEvent(self, event):

        if event.button() == Qt.LeftButton and self.sub_name:

            left_m, track_w = self._get_geometry_info()

            x_start = left_m + int((self.sub_delay / self.total_duration) * track_w)

            x_end = left_m + track_w

            t1_y = 42

            t1_h = 36



            if x_end - 24 <= event.pos().x() <= x_end and t1_y <= event.pos().y() <= t1_y + t1_h:

                self.subCommandRemoved.emit()

                return



            if x_start <= event.pos().x() <= x_end and t1_y <= event.pos().y() <= t1_y + t1_h:

                self._dragging = True

                self._drag_start_x = event.pos().x()

                self._initial_delay = self.sub_delay

                self.setCursor(Qt.SizeHorCursor)



    def mouseMoveEvent(self, event):

        if self._dragging and self.sub_name:

            left_m, track_w = self._get_geometry_info()

            dx = event.pos().x() - self._drag_start_x

            delta_sec = (dx / float(track_w)) * self.total_duration

            new_delay = max(0.0, min(self.total_duration - 1.0, self._initial_delay + delta_sec))

            new_delay = round(new_delay, 1)

            if new_delay != self.sub_delay:

                self.sub_delay = new_delay

                self.delayChanged.emit(self.sub_delay)

                self.update()

        else:

            if self.sub_name:

                left_m, track_w = self._get_geometry_info()

                x_start = left_m + int((self.sub_delay / self.total_duration) * track_w)

                x_end = left_m + track_w

                t1_y = 42

                t1_h = 36

                if x_start <= event.pos().x() <= x_end and t1_y <= event.pos().y() <= t1_y + t1_h:

                    self.setCursor(Qt.SizeHorCursor)

                else:

                    self.setCursor(Qt.ArrowCursor)



    def mouseReleaseEvent(self, event):

        self._dragging = False

        self.setCursor(Qt.ArrowCursor)





class GlowLineEdit(QLineEdit):

    """ช่องกรอกข้อความพร้อมแสงนีออนเรืองรอบกรอบเมื่อคลิกโฟกัส (Focus Glow Effect)"""

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self._glow = QGraphicsDropShadowEffect(self)

        self._glow.setBlurRadius(16)

        self._glow.setColor(QColor(56, 189, 248, 180))

        self._glow.setOffset(0, 0)

        self._glow.setEnabled(False)

        self.setGraphicsEffect(self._glow)



    def focusInEvent(self, event):

        self._glow.setEnabled(True)

        super().focusInEvent(event)



    def focusOutEvent(self, event):

        self._glow.setEnabled(False)

        super().focusOutEvent(event)





# ════════════════════════════════════════════════════════════════════════════

# 🎯 Fine-Tuning Placement Dialog (ตั้งค่าแต่งตำแหน่งโดยละเอียด)

# ════════════════════════════════════════════════════════════════════════════

class ReplieFineTuneDialog(QDialog):

    """หน้าต่างปรับพิกัด X/Y และ Scale โดยละเอียด"""

    def __init__(self, parent, service, cmd, target="ticker"):

        super().__init__(parent)

        self.service = service

        self.cmd = cmd

        self.target = target



        self.setWindowTitle(f"🎯 ปรับแต่งตำแหน่ง ({'ข้อความ Ticker' if target == 'ticker' else 'รูปภาพ Image'})")

        self.resize(520, 320)

        self.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)

        self.setStyleSheet("""

            QDialog { background: #0f172a; color: #f8fafc; font-family: "Kanit", sans-serif; }

            QLabel { font-weight: 600; color: #cbd5e1; font-size: 13px; }

            QPushButton { background: #1e293b; color: #f8fafc; border: 1px solid #334155; border-radius: 2px; padding: 7px 16px; font-weight: 700; }

            QPushButton:hover { background: #334155; border-color: #38bdf8; }

        """)



        layout = QVBoxLayout(self)

        layout.setSpacing(14)

        layout.setContentsMargins(18, 18, 18, 18)



        lbl_hint = QLabel("💡 ตัวอย่างจะแสดงค้างบนหน้าจอ OBS แบบสดทันทีเพื่อให้คุณเลื่อนจัดตำแหน่งได้อย่างแม่นยำครับ")

        lbl_hint.setWordWrap(True)

        lbl_hint.setStyleSheet("color: #38bdf8; font-size: 12.5px; font-weight: 600; padding: 6px; background: rgba(56, 189, 248, 0.1); border-radius: 6px;")

        layout.addWidget(lbl_hint)



        is_ticker = (target == "ticker")

        init_x = cmd.ticker_pos_x if is_ticker else cmd.image_pos_x

        init_y = cmd.ticker_pos_y if is_ticker else cmd.image_pos_y

        init_scale = int((cmd.ticker_scale if is_ticker else cmd.image_scale) * 100)



        def_x = 50 if is_ticker else 85

        def_y = 88 if is_ticker else 50

        def_scale = 100



        self.slider_x, self.val_x = self._create_slider(layout, "พิกัดแนวนอน (X):", 0, 100, init_x, "%", def_x)

        self.slider_y, self.val_y = self._create_slider(layout, "พิกัดแนวตั้ง (Y):", 0, 100, init_y, "%", def_y)

        self.slider_scale, self.val_scale = self._create_slider(layout, "ขนาดสเกล (Scale):", 50, 150, init_scale, "%", def_scale)



        self.slider_x.valueChanged.connect(self._sync_live_pos)

        self.slider_y.valueChanged.connect(self._sync_live_pos)

        self.slider_scale.valueChanged.connect(self._sync_live_pos)



        layout.addStretch()



        bot_row = QHBoxLayout()

        bot_row.addStretch()

        btn_ok = QPushButton("ตกลง / นำไปใช้")

        btn_ok.setStyleSheet("background: #0284c7; color: #fff; font-weight: 700; border-color: #38bdf8; padding: 8px 24px;")

        btn_ok.clicked.connect(self.accept)

        bot_row.addWidget(btn_ok)

        layout.addLayout(bot_row)



        QTimer.singleShot(100, self._start_persistent_demo)



    def _create_slider(self, parent_layout, label_text, min_v, max_v, cur_v, unit, default_v):

        row = QHBoxLayout()

        row.setSpacing(8)

        lbl = QLabel(label_text)

        lbl.setFixedWidth(140)



        slider = QSlider(Qt.Horizontal)

        slider.setRange(min_v, max_v)

        slider.setValue(cur_v)



        val_lbl = QLabel(f"{cur_v}{unit}")

        val_lbl.setFixedWidth(56)

        val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        val_lbl.setStyleSheet("font-weight: 700; color: #38bdf8;")



        def _on_val(v):

            val_lbl.setText(f"{v}{unit}")



        slider.valueChanged.connect(_on_val)



        btn_reset = QPushButton("↺")

        btn_reset.setToolTip("คืนค่าเริ่มต้น")

        btn_reset.setFixedSize(26, 26)

        btn_reset.setStyleSheet("""

            QPushButton {

                background: transparent;

                color: #64748b;

                border: none;

                font-size: 16px;

                font-weight: bold;

            }

            QPushButton:hover {

                color: #38bdf8;

                background: rgba(56, 189, 248, 0.15);

                border-radius: 4px;

            }

        """)

        btn_reset.clicked.connect(lambda: slider.setValue(default_v))



        row.addWidget(lbl)

        row.addWidget(slider)

        row.addWidget(val_lbl)

        row.addWidget(btn_reset)

        parent_layout.addLayout(row)

        return slider, val_lbl



    def _start_persistent_demo(self):

        if self.service:

            self.service.show_replie(self.cmd, triggered_by="Streamer (Position Edit)", is_loop=True)

            self._sync_live_pos()



    def _sync_live_pos(self):

        if self.service:

            px = self.slider_x.value()

            py = self.slider_y.value()

            sc = self.slider_scale.value() / 100.0

            self.service.update_live_preview(pos_x=px, pos_y=py, scale=sc, target=self.target)



    def closeEvent(self, event):

        if self.service:

            self.service.dismiss_current()

        super().closeEvent(event)



    def get_values(self):

        return self.slider_x.value(), self.slider_y.value(), self.slider_scale.value() / 100.0





# ════════════════════════════════════════════════════════════════════════════

# 📝 Command Creation & Editing Dialog (ReplieEditDialog) — Flat & Clean

# ════════════════════════════════════════════════════════════════════════════

class ReplieEditDialog(QDialog):

    """หน้าต่างสร้างและแก้ไขคำสั่ง ดีไซน์ Flat โปร่งตา ไม่ใช้กรอบซ้อนกรอบ"""



    def __init__(self, parent, cmd, all_commands: Optional[Dict[str, any]] = None):

        super().__init__(parent)

        self.cmd = cmd

        if self.cmd is None:

            from replie_service import ReplieCommand

            self.cmd = ReplieCommand(name="!new")

        cmd = self.cmd

        self.orig_name = getattr(self.cmd, "name", "")

        self.parent_panel = parent

        self.service = getattr(parent, "service", None)

        self.all_commands = all_commands or (self.service.commands if self.service else {})



        # พิกัดและการตั้งค่าตำแหน่งแบบละเอียด (ป้องกันการสูญหายเมื่อกดบันทึก)

        self.saved_ticker_pos_x = getattr(cmd, "ticker_pos_x", 50)

        self.saved_ticker_pos_y = getattr(cmd, "ticker_pos_y", 88)

        self.saved_ticker_scale = getattr(cmd, "ticker_scale", 1.0)

        self.saved_image_pos_x = getattr(cmd, "image_pos_x", 85)

        self.saved_image_pos_y = getattr(cmd, "image_pos_y", 50)

        self.saved_image_scale = getattr(cmd, "image_scale", 1.0)



        self.ticker_color_val = getattr(cmd, "ticker_color", "#f8fafc")

        # Toggle states for demo / test buttons

        self.is_anim_in_active = False

        self.is_live_demo_active = False

        self._demo_timer = QTimer(self)

        self._demo_timer.setSingleShot(True)

        self._demo_timer.timeout.connect(self._reset_live_demo_btn)



        is_new = (cmd.name == "!new" or not cmd.name)

        self.setWindowTitle("เพิ่มคำสั่ง Replie ใหม่" if is_new else f"แก้ไขคำสั่ง: {cmd.name}")

        self.resize(760, 680)

        self.setMinimumSize(700, 600)

        self.setStyleSheet("""

            QDialog {

                background-color: #0b1120;

                color: #f8fafc;

                font-family: -apple-system, BlinkMacSystemFont, "Kanit", "Segoe UI", sans-serif;

                font-size: 13px;

            }

            QTabWidget::pane {

                border: none;

                background: transparent;

                top: 0;

            }

            QTabBar::tab {

                background: transparent;

                color: #94a3b8;

                padding: 10px 24px;

                margin-right: 6px;

                border: none;

                border-bottom: 2px solid transparent;

                font-weight: 700;

                font-size: 13.5px;

            }

            QTabBar::tab:selected {

                color: #38bdf8;

                border-bottom: 2px solid #38bdf8;

            }

            QTabBar::tab:hover {

                color: #e2e8f0;

            }

            QPushButton {

                background: #1e293b;

                color: #f8fafc;

                border: 1px solid #334155;

                border-radius: 2px;

                padding: 7px 16px;

                font-weight: 700;

            }

            QPushButton:hover {

                background: #27364b;

                border-color: #38bdf8;

            }

            QPushButton:pressed {

                background: #0f172a;

            }

            QLineEdit {

                background: #070e1c;

                border: 1.5px solid #1e2a3f;

                border-radius: 5px;

                padding: 8px 12px;

                color: #f8fafc;

                font-size: 13px;

                selection-background-color: #0284c7;

            }

            QLineEdit:focus {

                border: 1.5px solid #38bdf8;

                background: #0b1528;

                color: #ffffff;

            }

            QComboBox {

                background: #070e1c;

                border: 1.5px solid #1e2a3f;

                border-radius: 5px;

                padding: 7px 12px;

                color: #f8fafc;

                font-size: 13px;

            }

            QComboBox:focus, QComboBox:hover {

                border: 1.5px solid #38bdf8;

                background: #0b1528;

            }

            QComboBox::drop-down {

                border: none;

                width: 24px;

            }

            QComboBox QAbstractItemView {

                background: #070e1c;

                border: 1px solid #334155;

                color: #f8fafc;

                selection-background-color: #0284c7;

            }

            QRadioButton {

                color: #f1f5f9;

                font-weight: 600;

                font-size: 13.5px;

                spacing: 8px;

            }

            QCheckBox {

                color: #e2e8f0;

                font-weight: 500;

                spacing: 8px;

            }

            QLabel {

                color: #cbd5e1;

                font-size: 12.5px;

                font-weight: 600;

            }

        """)



        layout = QVBoxLayout(self)

        layout.setContentsMargins(18, 14, 18, 14)

        layout.setSpacing(10)



        # ── 2 Tabs ──

        self.tabs = QTabWidget()

        self.tab_command = QWidget()

        self.tab_appearance = QWidget()



        self.tabs.addTab(self.tab_command, "⚡ คำสั่งและการแสดงผล")

        self.tabs.addTab(self.tab_appearance, "🎨 ปรับแต่งหน้าตาการแสดงผล")

        layout.addWidget(self.tabs)



        self._build_command_tab()

        self._build_appearance_tab()



        # ── Bottom Action Bar ──

        bot_bar = QHBoxLayout()

        bot_bar.setContentsMargins(0, 8, 0, 0)



        self.btn_live_demo = QPushButton("🚀 ทดสอบบน Overlay สด")

        self.btn_live_demo.setStyleSheet("background: #7e22ce; color: #fff; border: 1px solid #a855f7; border-radius: 2px; font-weight: 700; padding: 8px 18px;")

        self.btn_live_demo.setCursor(Qt.PointingHandCursor)

        self.btn_live_demo.setToolTip("กดเพื่อยิงแสดงผลบนจอจริง กดซ้ำอีกครั้งเพื่อซ่อนทันที")

        self.btn_live_demo.clicked.connect(self._on_live_demo_clicked)

        bot_bar.addWidget(self.btn_live_demo)



        bot_bar.addStretch()

        btn_cancel = QPushButton("ยกเลิก")

        btn_cancel.setCursor(Qt.PointingHandCursor)

        btn_cancel.setStyleSheet("background: #1e293b; color: #94a3b8; border: 1px solid #334155; border-radius: 2px; font-weight: 700; padding: 8px 18px;")

        btn_cancel.clicked.connect(self.reject)

        bot_bar.addWidget(btn_cancel)



        btn_save = QPushButton("💾 บันทึกคำสั่ง")

        btn_save.setStyleSheet("background: #0284c7; color: #fff; border: 1px solid #38bdf8; border-radius: 2px; font-weight: 700; padding: 8px 26px;")

        btn_save.setCursor(Qt.PointingHandCursor)

        btn_save.clicked.connect(self._on_save_clicked)

        bot_bar.addWidget(btn_save)



        layout.addLayout(bot_bar)



    # ════════════════════════════════════════════════════════════════════════

    # TAB 1: ⚡ คำสั่งและการแสดงผล — ดีไซน์ Flat สะอาดตา ไร้กรอบซ้อนกรอบ

    # ════════════════════════════════════════════════════════════════════════

    def _build_command_tab(self):

        scroll = QScrollArea(self.tab_command)

        scroll.setWidgetResizable(True)

        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")



        inner = QWidget()

        layout = QVBoxLayout(inner)

        layout.setContentsMargins(4, 10, 4, 10)

        layout.setSpacing(14)



        # 1. แถวชื่อคำสั่ง & คำอธิบาย (สะอาด ไร้กรอบการ์ด)

        row_cmd = QHBoxLayout()

        row_cmd.setSpacing(12)



        v_name = QVBoxLayout()

        v_name.setSpacing(4)

        v_name.addWidget(QLabel("คำสั่งที่จะใช้:"))

        self.inp_name = GlowLineEdit(self.cmd.name if self.cmd.name != "!new" else "!")

        self.inp_name.setPlaceholderText("!donate")

        v_name.addWidget(self.inp_name)

        row_cmd.addLayout(v_name, 2)



        v_desc = QVBoxLayout()

        v_desc.setSpacing(4)

        v_desc.addWidget(QLabel("คำอธิบาย คำสั่งนี้ว่าคืออะไร (แสดงในตาราง):"))

        self.inp_desc = GlowLineEdit(getattr(self.cmd, "desc", ""))

        self.inp_desc.setPlaceholderText("เช่น แสดงข้อมูลงานกิจกรรม และ QR Code")

        v_desc.addWidget(self.inp_desc)

        row_cmd.addLayout(v_desc, 3)

        layout.addLayout(row_cmd)



        # 2. Radio เลือกประเภทคำสั่ง (Flat ไร้กรอบครอบ)

        r_type = QHBoxLayout()

        r_type.setSpacing(24)

        lbl_choose = QLabel("ประเภทคำสั่งหลัก:")

        lbl_choose.setStyleSheet("color: #38bdf8; font-weight: 700; font-size: 13.5px;")

        r_type.addWidget(lbl_choose)



        self.rb_ticker = QRadioButton("🗨 Message Ticker (ข้อความวิ่ง / แถบข้อความ)")

        self.rb_image = QRadioButton("🖼️ Image (รูปภาพ / QR Code)")



        if not self.cmd.ticker_enabled and self.cmd.image_enabled:

            self.rb_image.setChecked(True)

        else:

            self.rb_ticker.setChecked(True)



        self.type_group = QButtonGroup(self)

        self.type_group.addButton(self.rb_ticker, 1)

        self.type_group.addButton(self.rb_image, 2)



        r_type.addWidget(self.rb_ticker)

        r_type.addWidget(self.rb_image)

        r_type.addStretch()

        layout.addLayout(r_type)



        # 3. ส่วนของ Message Ticker (Flat Layout)

        self.box_ticker = QWidget()

        bt_l = QVBoxLayout(self.box_ticker)

        bt_l.setContentsMargins(0, 0, 0, 0)

        bt_l.setSpacing(12)



        row_t1 = QHBoxLayout()

        row_t1.setSpacing(12)



        vt_lay = QVBoxLayout()

        vt_lay.setSpacing(4)

        vt_lay.addWidget(QLabel("รูปแบบการแสดง:"))

        self.combo_ticker_layout = QComboBox()

        self.combo_ticker_layout.addItem("ข้อความวิ่งแบบมีกรอบ", "bottom_ticker")

        self.combo_ticker_layout.addItem("แถบข้อความวิ่งเต็มจอ", "full_ticker")

        if getattr(self.cmd, "layout", "bottom_ticker") == "full_ticker":

            self.combo_ticker_layout.setCurrentIndex(1)

        vt_lay.addWidget(self.combo_ticker_layout)

        row_t1.addLayout(vt_lay, 3)



        vt_pos = QVBoxLayout()

        vt_pos.setSpacing(4)

        vt_pos.addWidget(QLabel("จะขึ้นตรงไหนของจอ:"))

        self.combo_ticker_preset = QComboBox()

        self.combo_ticker_preset.addItem("จากด้านล่างของจอ", "bottom")

        self.combo_ticker_preset.addItem("จากด้านบนของจอ", "top")

        self.combo_ticker_preset.addItem("กำหนดเอง (พิกัดละเอียด)", "custom")

        if getattr(self.cmd, "position_preset", "bottom") == "top" or (self.saved_ticker_pos_y < 30 and self.saved_ticker_pos_x == 50):

            self.combo_ticker_preset.setCurrentIndex(1)

        elif self.saved_ticker_pos_x != 50 or (self.saved_ticker_pos_y != 88 and self.saved_ticker_pos_y != 8) or getattr(self.cmd, "position_preset", "") == "custom":

            self.combo_ticker_preset.setCurrentIndex(2)

        else:

            self.combo_ticker_preset.setCurrentIndex(0)

        self.combo_ticker_preset.currentIndexChanged.connect(self._on_ticker_preset_changed)

        vt_pos.addWidget(self.combo_ticker_preset)

        row_t1.addLayout(vt_pos, 2)



        btn_t_fine = QPushButton("🎯 ปรับตำแหน่งละเอียด")

        btn_t_fine.setCursor(Qt.PointingHandCursor)

        btn_t_fine.setStyleSheet("background: #152238; color: #38bdf8; border: 1px solid #0284c7; border-radius: 2px; padding: 7px 14px; margin-top: 18px; font-weight: 700;")

        btn_t_fine.clicked.connect(lambda: self._open_fine_tune("ticker"))

        row_t1.addWidget(btn_t_fine, 2)

        bt_l.addLayout(row_t1)



        row_t2 = QHBoxLayout()

        row_t2.setSpacing(12)

        vt_title = QVBoxLayout()

        vt_title.setSpacing(4)

        vt_title.addWidget(QLabel("หัวข้อที่แสดง (Title - ถ้าไม่ใส่จะแสดงเฉพาะข้อความ):"))

        self.inp_title = GlowLineEdit(self.cmd.title)

        self.inp_title.setPlaceholderText("เช่น 💖 สนับสนุนช่อง")

        vt_title.addWidget(self.inp_title)

        row_t2.addLayout(vt_title, 2)



        vt_text = QVBoxLayout()

        vt_text.setSpacing(4)

        vt_text.addWidget(QLabel("ข้อความแสดงผล (Text):"))

        self.inp_text = GlowLineEdit(self.cmd.text)

        self.inp_text.setPlaceholderText("เช่น พร้อมเพย์ 08x-xxx-xxxx ขอบคุณครับ!")

        vt_text.addWidget(self.inp_text)

        row_t2.addLayout(vt_text, 3)

        bt_l.addLayout(row_t2)



        # แถบปรับแต่งตัวหนังสือ Ticker (ขนาดฟอนต์, แบบฟอนต์, สี, ตัวหนา)

        row_t_font = QHBoxLayout()

        row_t_font.setSpacing(12)



        v_tsize = QVBoxLayout()

        v_tsize.setSpacing(4)

        v_tsize.addWidget(QLabel("ขนาดตัวหนังสือ:"))

        self.combo_ticker_font_size = QComboBox()

        for sz, label in [

            (14, "14px (เล็ก)"),

            (16, "16px (ปกติ)"),

            (18, "18px (ปานกลาง)"),

            (20, "20px (ใหญ่)"),

            (24, "24px (ใหญ่พิเศษ)"),

            (28, "28px (เด่นชัด)"),

            (32, "32px (ยักษ์)")

        ]:

            self.combo_ticker_font_size.addItem(label, sz)

        cur_sz = getattr(self.cmd, "ticker_font_size", 16)

        idx_sz = self.combo_ticker_font_size.findData(cur_sz)

        if idx_sz >= 0:

            self.combo_ticker_font_size.setCurrentIndex(idx_sz)

        v_tsize.addWidget(self.combo_ticker_font_size)

        row_t_font.addLayout(v_tsize, 2)



        v_tfont = QVBoxLayout()

        v_tfont.setSpacing(4)

        v_tfont.addWidget(QLabel("แบบฟอนต์:"))

        self.combo_ticker_font = QComboBox()

        for f in FONT_OPTIONS:

            self.combo_ticker_font.addItem(f, f)

        cur_tf = getattr(self.cmd, "ticker_font", "Kanit")

        idx_tf = self.combo_ticker_font.findData(cur_tf)

        if idx_tf >= 0:

            self.combo_ticker_font.setCurrentIndex(idx_tf)

        v_tfont.addWidget(self.combo_ticker_font)

        row_t_font.addLayout(v_tfont, 2)



        v_tcol = QVBoxLayout()

        v_tcol.setSpacing(4)

        v_tcol.addWidget(QLabel("สีตัวหนังสือ:"))

        self.btn_ticker_color = QPushButton(f"🎨 {self.ticker_color_val}")

        self.btn_ticker_color.setCursor(Qt.PointingHandCursor)

        self.btn_ticker_color.setStyleSheet(f"background: #1e293b; color: {self.ticker_color_val}; font-weight: 700; border: 1px solid #334155; border-radius: 2px; padding: 7px 12px;")

        self.btn_ticker_color.clicked.connect(self._choose_ticker_color)

        v_tcol.addWidget(self.btn_ticker_color)

        row_t_font.addLayout(v_tcol, 2)



        v_tbold = QVBoxLayout()

        v_tbold.setSpacing(4)

        v_tbold.addWidget(QLabel(""))

        self.cb_ticker_bold = QCheckBox("ตัวหนา (Bold)")

        self.cb_ticker_bold.setChecked(getattr(self.cmd, "ticker_bold", True))

        self.cb_ticker_bold.setStyleSheet("font-weight: 600; color: #cbd5e1; margin-top: 6px;")

        v_tbold.addWidget(self.cb_ticker_bold)

        row_t_font.addLayout(v_tbold, 2)



        bt_l.addLayout(row_t_font)



        layout.addWidget(self.box_ticker)



        # 4. ส่วนของ Image (Flat Layout)

        self.box_image = QWidget()

        bi_l = QVBoxLayout(self.box_image)

        bi_l.setContentsMargins(0, 0, 0, 0)

        bi_l.setSpacing(12)



        row_img = QHBoxLayout()

        row_img.setSpacing(12)

        vi_path = QVBoxLayout()

        vi_path.setSpacing(4)

        vi_path.addWidget(QLabel("เลือกไฟล์รูปภาพที่ต้องการแสดง:"))

        r_browse = QHBoxLayout()

        r_browse.setSpacing(6)

        self.inp_img_url = GlowLineEdit(getattr(self.cmd, "image_url", ""))

        self.inp_img_url.setPlaceholderText("assets/sample_qr.png หรือเลือกไฟล์")

        self.inp_img_url.textChanged.connect(self._update_img_preview)

        btn_browse = QPushButton("📁 เลือกภาพ...")

        btn_browse.setCursor(Qt.PointingHandCursor)

        btn_browse.setStyleSheet("background: #1e293b; color: #f8fafc; border: 1px solid #334155; border-radius: 2px; font-weight: 700;")

        btn_browse.clicked.connect(self._on_browse_image)

        r_browse.addWidget(self.inp_img_url)

        r_browse.addWidget(btn_browse)

        vi_path.addLayout(r_browse)

        row_img.addLayout(vi_path, 4)



        self.lbl_img_thumb = QLabel("🖼️ ภาพ")

        self.lbl_img_thumb.setFixedSize(54, 54)

        self.lbl_img_thumb.setAlignment(Qt.AlignCenter)

        self.lbl_img_thumb.setStyleSheet("background: #151f32; border: 1px dashed #334155; border-radius: 6px;")

        row_img.addWidget(self.lbl_img_thumb, 1)

        bi_l.addLayout(row_img)



        self.cb_image_framed = QCheckBox("มีกรอบหลังรูปภาพไหม (ถ้าติ๊กจะมีข้อความหัว/ท้ายภาพ)")

        self.cb_image_framed.setChecked(not getattr(self.cmd, "image_frameless", True))

        self.cb_image_framed.toggled.connect(self._toggle_image_frame_fields)

        bi_l.addWidget(self.cb_image_framed)



        self.box_frame_texts = QWidget()

        bft_l = QHBoxLayout(self.box_frame_texts)

        bft_l.setContentsMargins(0, 0, 0, 0)

        bft_l.setSpacing(12)

        v_top = QVBoxLayout()

        v_top.setSpacing(4)

        v_top.addWidget(QLabel("ข้อความด้านบนของภาพ:"))

        self.inp_img_top = GlowLineEdit(getattr(self.cmd, "image_top_text", ""))

        self.inp_img_top.setPlaceholderText("เช่น สแกน QR Code")

        v_top.addWidget(self.inp_img_top)

        bft_l.addLayout(v_top)



        v_bot = QVBoxLayout()

        v_bot.setSpacing(4)

        v_bot.addWidget(QLabel("ข้อความด้านใต้ของภาพ:"))

        self.inp_img_bot = GlowLineEdit(getattr(self.cmd, "image_bottom_text", ""))

        self.inp_img_bot.setPlaceholderText("เช่น รองรับทุกธนาคาร")

        v_bot.addWidget(self.inp_img_bot)

        bft_l.addLayout(v_bot)

        bi_l.addWidget(self.box_frame_texts)

        self.box_frame_texts.setVisible(self.cb_image_framed.isChecked())



        row_i_pos = QHBoxLayout()

        row_i_pos.setSpacing(12)

        vi_pos = QVBoxLayout()

        vi_pos.setSpacing(4)

        vi_pos.addWidget(QLabel("จะขึ้นตรงไหนของจอ:"))

        self.combo_img_preset = QComboBox()

        self.combo_img_preset.addItem("จากขวาของจอ", "right")

        self.combo_img_preset.addItem("จากซ้ายของจอ", "left")

        self.combo_img_preset.addItem("จากด้านล่างของจอ", "bottom")

        self.combo_img_preset.addItem("จากด้านบนของจอ", "top")

        self.combo_img_preset.addItem("กำหนดเอง (พิกัดละเอียด)", "custom")

        cur_img_p = getattr(self.cmd, "position_preset", "")

        if cur_img_p == "custom":

            self.combo_img_preset.setCurrentIndex(4)

        else:

            is_std = False

            for idx, (px, py) in enumerate([(85, 50), (15, 50), (50, 85), (50, 15)]):

                if self.saved_image_pos_x == px and self.saved_image_pos_y == py:

                    self.combo_img_preset.setCurrentIndex(idx)

                    is_std = True

                    break

            if not is_std:

                self.combo_img_preset.setCurrentIndex(4)

        self.combo_img_preset.currentIndexChanged.connect(self._on_image_preset_changed)

        vi_pos.addWidget(self.combo_img_preset)

        row_i_pos.addLayout(vi_pos, 2)



        btn_i_fine = QPushButton("🎯 ปรับตำแหน่งละเอียด")

        btn_i_fine.setCursor(Qt.PointingHandCursor)

        btn_i_fine.setStyleSheet("background: #152238; color: #38bdf8; border: 1px solid #0284c7; border-radius: 2px; padding: 7px 14px; margin-top: 18px; font-weight: 700;")

        btn_i_fine.clicked.connect(lambda: self._open_fine_tune("image"))

        row_i_pos.addWidget(btn_i_fine, 2)

        bi_l.addLayout(row_i_pos)



        layout.addWidget(self.box_image)



        self.rb_ticker.toggled.connect(self._on_type_changed)

        self._on_type_changed()

        self._update_img_preview()



        # 5. แถวระยะเวลาแสดงผล & คูลดาวน์ (ใช้ร่วมกันทั้ง Ticker & Image)

        row_common_time = QHBoxLayout()

        row_common_time.setSpacing(12)

        vt_dur = QVBoxLayout()

        vt_dur.setSpacing(4)

        vt_dur.addWidget(QLabel("ระยะเวลาการแสดงผล (วินาที):"))

        self.inp_duration = GlowLineEdit(str(getattr(self.cmd, "duration_sec", 15)))

        self.inp_duration.textChanged.connect(self._sync_timeline_duration)

        vt_dur.addWidget(self.inp_duration)

        row_common_time.addLayout(vt_dur)



        vt_cd = QVBoxLayout()

        vt_cd.setSpacing(4)

        vt_cd.addWidget(QLabel("คูลดาวน์ป้องกันการกดซ้ำ (วินาที):"))

        self.inp_cooldown = GlowLineEdit(str(getattr(self.cmd, "cooldown_sec", 15)))

        vt_cd.addWidget(self.inp_cooldown)

        row_common_time.addLayout(vt_cd)

        layout.addLayout(row_common_time)



        # 6. ปุ่มพับ/กางการตั้งค่าเพิ่มเติม (ไร้กรอบหนา)

        self.btn_adv = QPushButton("▼ ตั้งค่าเพิ่มเติม (อนิเมชัน เข้า/ออก & เวลานับถอยหลัง)")

        self.btn_adv.setCursor(Qt.PointingHandCursor)

        self.btn_adv.setStyleSheet("background: transparent; color: #38bdf8; border: none; text-align: left; padding: 6px 0; font-weight: 700; font-size: 13px;")

        self.btn_adv.clicked.connect(self._toggle_advanced_panel)

        layout.addWidget(self.btn_adv)



        # กล่องตั้งค่าเพิ่มเติม

        self.box_advanced = QWidget()

        adv_l = QVBoxLayout(self.box_advanced)

        adv_l.setContentsMargins(10, 0, 10, 8)

        adv_l.setSpacing(10)



        # อนิเมชัน In / Out

        row_an = QHBoxLayout()

        row_an.setSpacing(10)

        v_ain = QVBoxLayout()

        v_ain.setSpacing(4)

        v_ain.addWidget(QLabel("อนิเมชันนำเข้า:"))

        self.combo_anim_in = QComboBox()

        for k, v in ANIM_IN_OPTIONS:

            self.combo_anim_in.addItem(v, k)

        cur_in = getattr(self.cmd, "ticker_anim_in", "slide-up")

        idx_in = self.combo_anim_in.findData(cur_in)

        if idx_in >= 0:

            self.combo_anim_in.setCurrentIndex(idx_in)

        v_ain.addWidget(self.combo_anim_in)

        row_an.addLayout(v_ain)



        v_aout = QVBoxLayout()

        v_aout.setSpacing(4)

        v_aout.addWidget(QLabel("อนิเมชันนำออก:"))

        self.combo_anim_out = QComboBox()

        for k, v in ANIM_OUT_OPTIONS:

            self.combo_anim_out.addItem(v, k)

        cur_out = getattr(self.cmd, "ticker_anim_out", "slide-down")

        idx_out = self.combo_anim_out.findData(cur_out)

        if idx_out >= 0:

            self.combo_anim_out.setCurrentIndex(idx_out)

        v_aout.addWidget(self.combo_anim_out)

        row_an.addLayout(v_aout)



        # ปุ่มทดสอบอนิเมชันปุ่มเดียว (สลับระหว่าง In -> Out)

        self.btn_test_anim = QPushButton("▶ ทดสอบ In")

        self.btn_test_anim.setStyleSheet("background: #065f46; color: #34d399; font-weight: 700; border-radius: 2px; border: 1px solid #059669; margin-top: 18px; padding: 7px 18px;")

        self.btn_test_anim.setCursor(Qt.PointingHandCursor)

        self.btn_test_anim.setToolTip("กดเพื่อเล่นอนิเมชันตอนเข้า (In) และค้างไว้ จากนั้นกดซ้ำเพื่อเล่นอนิเมชันตอนออก (Out)")

        self.btn_test_anim.clicked.connect(self._on_toggle_test_anim)

        row_an.addWidget(self.btn_test_anim)

        adv_l.addLayout(row_an)



        # เวลานับถอยหลัง

        row_cd_rb = QHBoxLayout()

        row_cd_rb.setSpacing(16)

        self.rb_cd_none = QRadioButton("ไม่แสดงเวลานับถอยหลัง")

        self.rb_cd_number = QRadioButton("แสดงเวลานับถอยหลังเป็นเลข")

        self.rb_cd_bar = QRadioButton("แสดงเวลานับถอยหลังเป็นแถบ")



        self.cd_group = QButtonGroup(self)

        self.cd_group.addButton(self.rb_cd_none, 0)

        self.cd_group.addButton(self.rb_cd_number, 1)

        self.cd_group.addButton(self.rb_cd_bar, 2)



        cur_cd = getattr(self.cmd, "countdown_type", "number")

        if cur_cd == "none":

            self.rb_cd_none.setChecked(True)

        elif cur_cd == "bar":

            self.rb_cd_bar.setChecked(True)

        else:

            self.rb_cd_number.setChecked(True)



        row_cd_rb.addWidget(self.rb_cd_none)

        row_cd_rb.addWidget(self.rb_cd_number)

        row_cd_rb.addWidget(self.rb_cd_bar)

        row_cd_rb.addStretch()

        adv_l.addLayout(row_cd_rb)



        # Number Options

        self.box_cd_num_opts = QWidget()

        bno_l = QHBoxLayout(self.box_cd_num_opts)

        bno_l.setContentsMargins(0, 0, 0, 0)

        bno_l.setSpacing(10)



        v_font = QVBoxLayout()

        v_font.setSpacing(4)

        v_font.addWidget(QLabel("ฟอนต์ตัวเลข:"))

        self.combo_cd_font = QComboBox()

        for f in FONT_OPTIONS:

            self.combo_cd_font.addItem(f)

        cur_font = getattr(self.cmd, "countdown_font", "Kanit")

        idx_f = self.combo_cd_font.findText(cur_font)

        if idx_f >= 0:

            self.combo_cd_font.setCurrentIndex(idx_f)

        v_font.addWidget(self.combo_cd_font)

        bno_l.addLayout(v_font, 2)



        v_color = QVBoxLayout()

        v_color.setSpacing(4)

        v_color.addWidget(QLabel("สีตัวเลข:"))

        self.btn_cd_color = QPushButton("🎨 เลือกสี")

        self.cd_color_val = getattr(self.cmd, "countdown_color", "#ffffff")

        self._update_color_btn_style(self.btn_cd_color, self.cd_color_val)

        self.btn_cd_color.clicked.connect(self._pick_cd_color)

        v_color.addWidget(self.btn_cd_color)

        bno_l.addLayout(v_color, 2)



        self.cb_cd_shadow = QCheckBox("เงาหลังข้อความ")

        self.cb_cd_shadow.setChecked(getattr(self.cmd, "countdown_shadow", True))

        bno_l.addWidget(self.cb_cd_shadow, 2)



        btn_test_cd_num = QPushButton("⏱️ ทดสอบนับถอยหลัง")

        btn_test_cd_num.setStyleSheet("background: #0284c7; color: #fff; font-weight: 700; border-radius: 2px; border: 1px solid #38bdf8;")

        btn_test_cd_num.setCursor(Qt.PointingHandCursor)

        btn_test_cd_num.clicked.connect(lambda: self._test_countdown_live("number"))

        bno_l.addWidget(btn_test_cd_num, 3)

        adv_l.addWidget(self.box_cd_num_opts)



        # Bar Options

        self.box_cd_bar_opts = QWidget()

        bbo_l = QHBoxLayout(self.box_cd_bar_opts)

        bbo_l.setContentsMargins(0, 0, 0, 0)

        bbo_l.setSpacing(10)



        v_bcolor = QVBoxLayout()

        v_bcolor.setSpacing(4)

        v_bcolor.addWidget(QLabel("สีหลอดนับถอยหลัง:"))

        self.combo_progress = QComboBox()

        for k, v in PROGRESS_OPTIONS:

            self.combo_progress.addItem(v, k)

        cur_prog = getattr(self.cmd, "progress_style", "cyan")

        idx_p = self.combo_progress.findData(cur_prog)

        if idx_p >= 0:

            self.combo_progress.setCurrentIndex(idx_p)

        v_bcolor.addWidget(self.combo_progress)

        bbo_l.addLayout(v_bcolor, 3)



        btn_test_cd_bar = QPushButton("⏱️ ทดสอบนับถอยหลัง")

        btn_test_cd_bar.setStyleSheet("background: #0284c7; color: #fff; font-weight: 700; border-radius: 2px; border: 1px solid #38bdf8;")

        btn_test_cd_bar.setCursor(Qt.PointingHandCursor)

        btn_test_cd_bar.clicked.connect(lambda: self._test_countdown_live("bar"))

        bbo_l.addWidget(btn_test_cd_bar, 2)

        adv_l.addWidget(self.box_cd_bar_opts)



        self.rb_cd_none.toggled.connect(self._sync_cd_mode_ui)

        self.rb_cd_number.toggled.connect(self._sync_cd_mode_ui)

        self.rb_cd_bar.toggled.connect(self._sync_cd_mode_ui)

        self._sync_cd_mode_ui()



        self.box_advanced.setVisible(False)

        layout.addWidget(self.box_advanced)



        # 7. แถวไทม์ไลน์เลเยอร์ (Video Editor Timeline)

        tl_head = QHBoxLayout()

        lbl_tl_title = QLabel("🎞️ ไทม์ไลน์คำสั่งซ้อน (Sequence Timeline):")

        lbl_tl_title.setStyleSheet("color: #c084fc; font-weight: 700; font-size: 13px;")

        tl_head.addWidget(lbl_tl_title)

        tl_head.addStretch()



        self.btn_insert_sub = QPushButton("➕ แทรกคำสั่งเพิ่ม")

        self.btn_insert_sub.setStyleSheet("background: #7e22ce; color: #fff; border: 1px solid #a855f7; border-radius: 2px; font-weight: 700; padding: 5px 14px;")

        self.btn_insert_sub.setCursor(Qt.PointingHandCursor)

        self.btn_insert_sub.clicked.connect(self._on_insert_sub_clicked)

        tl_head.addWidget(self.btn_insert_sub)

        layout.addLayout(tl_head)



        self.timeline = ReplieTimelineWidget()

        self.timeline.delayChanged.connect(self._on_timeline_delay_changed)

        self.timeline.subCommandRemoved.connect(self._on_timeline_sub_removed)

        layout.addWidget(self.timeline)



        scroll.setWidget(inner)



        tab_layout = QVBoxLayout(self.tab_command)

        tab_layout.setContentsMargins(0, 0, 0, 0)

        tab_layout.addWidget(scroll)



        self._sync_timeline_data()



    # ════════════════════════════════════════════════════════════════════════

    # TAB 2: 🎨 ปรับแต่งหน้าตาการแสดงผล

    # ════════════════════════════════════════════════════════════════════════

    def _build_appearance_tab(self):

        scroll = QScrollArea(self.tab_appearance)

        scroll.setWidgetResizable(True)

        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")



        inner = QWidget()

        layout = QVBoxLayout(inner)

        layout.setContentsMargins(12, 12, 12, 12)

        layout.setSpacing(14)



        lbl_ct = QLabel("🎨 สไตล์และความโปร่งใสของข้อความ Ticker:")

        lbl_ct.setStyleSheet("color: #38bdf8; font-weight: 700; font-size: 14px;")

        layout.addWidget(lbl_ct)



        self.cb_ticker_frameless = QCheckBox("ไม่มีกรอบหลัง (โปร่งใส / Frameless) — เหมาะสำหรับข้อความ Danmaku ลอยบนจอ")

        self.cb_ticker_frameless.setChecked(getattr(self.cmd, "ticker_frameless", False))

        layout.addWidget(self.cb_ticker_frameless)



        row_tstyle = QHBoxLayout()

        v_ts = QVBoxLayout()

        v_ts.addWidget(QLabel("อนิเมชันตัวหนังสือ Ticker:"))

        self.combo_ticker_anim_style = QComboBox()

        self.combo_ticker_anim_style.addItem("📦 กรอบและข้อความเคลื่อนที่พร้อมกัน", "together")

        self.combo_ticker_anim_style.addItem("🌟 สไลด์กรอบก่อน แล้วข้อความค่อยๆ วิ่งผ่าน", "staged_slide")

        self.combo_ticker_anim_style.addItem("✨ สไลด์กรอบก่อน แล้วข้อความค่อยๆ จางปรากฏ", "staged_fade")

        cur_tas = getattr(self.cmd, "ticker_anim_style", "together")

        idx_tas = self.combo_ticker_anim_style.findData(cur_tas)

        if idx_tas >= 0:

            self.combo_ticker_anim_style.setCurrentIndex(idx_tas)

        v_ts.addWidget(self.combo_ticker_anim_style)

        row_tstyle.addLayout(v_ts)

        layout.addLayout(row_tstyle)



        layout.addStretch()

        scroll.setWidget(inner)



        tab_layout = QVBoxLayout(self.tab_appearance)

        tab_layout.setContentsMargins(0, 0, 0, 0)

        tab_layout.addWidget(scroll)



    # ════════════════════════════════════════════════════════════════════════

    # Event Handlers

    # ════════════════════════════════════════════════════════════════════════

    def _on_type_changed(self):

        is_ticker = self.rb_ticker.isChecked()

        self.box_ticker.setVisible(is_ticker)

        self.box_image.setVisible(not is_ticker)

        self._sync_timeline_data()



    def _toggle_image_frame_fields(self, checked):

        self.box_frame_texts.setVisible(checked)



    def _toggle_advanced_panel(self):

        vis = not self.box_advanced.isVisible()

        self.box_advanced.setVisible(vis)

        self.btn_adv.setText("▲ ซ่อนการตั้งค่าเพิ่มเติม" if vis else "▼ ตั้งค่าเพิ่มเติม (อนิเมชัน เข้า/ออก & เวลานับถอยหลัง)")



    def _sync_cd_mode_ui(self):

        self.box_cd_num_opts.setVisible(self.rb_cd_number.isChecked())

        self.box_cd_bar_opts.setVisible(self.rb_cd_bar.isChecked())



    def _update_color_btn_style(self, btn, hex_color):

        btn.setStyleSheet(f"background: {hex_color}; color: {'#000' if hex_color.lower() in ('#fff', '#ffffff') else '#fff'}; font-weight: 700; border: 1px solid #475569;")



    def _pick_cd_color(self):

        c = QColorDialog.getColor(QColor(self.cd_color_val), self, "เลือกสีตัวเลขนับถอยหลัง")

        if c.isValid():

            self.cd_color_val = c.name()

            self._update_color_btn_style(self.btn_cd_color, self.cd_color_val)



    def _on_browse_image(self):

        f, _ = QFileDialog.getOpenFileName(self, "เลือกรูปภาพ Replie", "", "Image Files (*.png *.jpg *.jpeg *.webp *.gif)")

        if f:

            self.inp_img_url.setText(f)

            self._update_img_preview()



    def _update_img_preview(self):

        path = self.inp_img_url.text().strip()

        if path and os.path.isfile(path):

            pix = QPixmap(path)

            if not pix.isNull():

                self.lbl_img_thumb.setPixmap(pix.scaled(50, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation))

                return

        self.lbl_img_thumb.setText("🖼️ ภาพ")



    def _sync_timeline_duration(self):

        if not hasattr(self, 'timeline'):

            return

        try:

            dur = float(self.inp_duration.text().strip() or "15")

        except ValueError:

            dur = 15.0

        self.timeline.total_duration = max(2.0, dur)

        self.timeline.update()



    def _sync_timeline_data(self):

        if not hasattr(self, 'timeline'):

            return

        try:

            dur = float(self.inp_duration.text().strip() or "15")

        except ValueError:

            dur = 15.0



        is_ticker = self.rb_ticker.isChecked()

        base_name = self.inp_name.text().strip() or "!command"

        base_type = "ticker" if is_ticker else "image"

        sub_name = getattr(self.cmd, "sub_command", None)

        sub_delay = getattr(self.cmd, "sub_command_delay", 2.5)



        sub_type = "image"

        if sub_name and self.all_commands and sub_name in self.all_commands:

            sc = self.all_commands[sub_name]

            sub_type = "image" if sc.image_enabled else "ticker"



        self.timeline.set_data(dur, base_name, base_type, sub_name, sub_type, sub_delay)



    def _on_timeline_delay_changed(self, delay):

        self.cmd.sub_command_delay = delay



    def _on_timeline_sub_removed(self):

        self.cmd.sub_command = None

        self.cmd.sub_command_delay = 0.0

        self._sync_timeline_data()



    def _on_insert_sub_clicked(self):

        available = [name for name in self.all_commands.keys() if name != self.cmd.name]

        if not available:

            QMessageBox.information(self, "แทรกคำสั่ง", "ยังไม่มีคำสั่งอื่นในระบบ กรุณาสร้างคำสั่งอื่นก่อนจึงจะสามารถนำมาแทรกได้ครับ")

            return



        dlg = QDialog(self)

        dlg.setWindowTitle("เลือกคำสั่งที่จะนำมาแทรก")

        dlg.resize(360, 200)

        dlg.setStyleSheet("background: #0f172a; color: #f8fafc;")

        dl = QVBoxLayout(dlg)

        dl.addWidget(QLabel("เลือกคำสั่งที่สร้างไว้แล้ว เพื่อนำมาเล่นควบคู่กัน:"))



        combo = QComboBox()

        for cname in available:

            cmd_obj = self.all_commands[cname]

            c_icon = "🖼️" if cmd_obj.image_enabled else "🗨"

            combo.addItem(f"{c_icon} {cname} — {cmd_obj.desc or cmd_obj.title or ''}", cname)

        dl.addWidget(combo)



        row_b = QHBoxLayout()

        row_b.addStretch()

        btn_c = QPushButton("ยกเลิก")

        btn_c.clicked.connect(dlg.reject)

        btn_ok = QPushButton("ตกลง")

        btn_ok.setStyleSheet("background: #7e22ce; color: #fff;")

        btn_ok.clicked.connect(dlg.accept)

        row_b.addWidget(btn_c)

        row_b.addWidget(btn_ok)

        dl.addLayout(row_b)



        if dlg.exec_():

            picked = combo.currentData()

            self.cmd.sub_command = picked

            self.cmd.sub_command_delay = min(2.5, self.timeline.total_duration - 1.0)

            self._sync_timeline_data()



    def _choose_ticker_color(self):

        col = QColorDialog.getColor(QColor(self.ticker_color_val), self, "เลือกสีตัวหนังสือ Ticker")

        if col.isValid():

            self.ticker_color_val = col.name()

            self.btn_ticker_color.setText(f"🎨 {self.ticker_color_val}")

            self.btn_ticker_color.setStyleSheet(f"background: #1e293b; color: {self.ticker_color_val}; font-weight: 700; border: 1px solid #334155; border-radius: 2px; padding: 7px 12px;")



    def _on_ticker_preset_changed(self):

        preset = self.combo_ticker_preset.currentData()

        if preset == "bottom":

            self.saved_ticker_pos_x = 50

            self.saved_ticker_pos_y = 88

        elif preset == "top":

            self.saved_ticker_pos_x = 50

            self.saved_ticker_pos_y = 8



    def _on_image_preset_changed(self):

        preset = self.combo_img_preset.currentData()

        if preset == "right":

            self.saved_image_pos_x = 85

            self.saved_image_pos_y = 50

        elif preset == "left":

            self.saved_image_pos_x = 15

            self.saved_image_pos_y = 50

        elif preset == "bottom":

            self.saved_image_pos_x = 50

            self.saved_image_pos_y = 85

        elif preset == "top":

            self.saved_image_pos_x = 50

            self.saved_image_pos_y = 15



    def _open_fine_tune(self, target="ticker"):

        temp_cmd = self._build_command_from_ui()

        dlg = ReplieFineTuneDialog(self, self.service, temp_cmd, target=target)

        if dlg.exec_():

            px, py, sc = dlg.get_values()

            if target == "ticker":

                self.saved_ticker_pos_x = px

                self.saved_ticker_pos_y = py

                self.saved_ticker_scale = sc

                self.cmd.ticker_pos_x = px

                self.cmd.ticker_pos_y = py

                self.cmd.ticker_scale = sc

                idx = self.combo_ticker_preset.findData("custom")

                if idx >= 0:

                    self.combo_ticker_preset.blockSignals(True)

                    self.combo_ticker_preset.setCurrentIndex(idx)

                    self.combo_ticker_preset.blockSignals(False)

            else:

                self.saved_image_pos_x = px

                self.saved_image_pos_y = py

                self.saved_image_scale = sc

                self.cmd.image_pos_x = px

                self.cmd.image_pos_y = py

                self.cmd.image_scale = sc

                idx = self.combo_img_preset.findData("custom")

                if idx >= 0:

                    self.combo_img_preset.blockSignals(True)

                    self.combo_img_preset.setCurrentIndex(idx)

                    self.combo_img_preset.blockSignals(False)



    def _build_command_from_ui(self):

        from replie_service import ReplieCommand

        name = self.inp_name.text().strip() or "!preview"

        if not name.startswith("!"):

            name = "!" + name



        try:

            dur = max(2, int(self.inp_duration.text().strip() or "15"))

        except ValueError:

            dur = 15



        try:

            cd = max(5, int(self.inp_cooldown.text().strip() or "15"))

        except ValueError:

            cd = 15



        is_ticker = self.rb_ticker.isChecked()

        

        if self.rb_cd_none.isChecked():

            cd_type = "none"

        elif self.rb_cd_bar.isChecked():

            cd_type = "bar"

        else:

            cd_type = "number"



        return ReplieCommand(

            name=name,

            desc=self.inp_desc.text().strip(),

            duration_sec=dur,

            cooldown_sec=cd,

            progress_style=self.combo_progress.currentData() or "cyan",

            countdown_type=cd_type,

            countdown_font=self.combo_cd_font.currentText(),

            countdown_color=self.cd_color_val,

            countdown_shadow=self.cb_cd_shadow.isChecked(),



            # Ticker

            ticker_enabled=is_ticker,

            title=self.inp_title.text().strip(),

            text=self.inp_text.text().strip(),

            layout=self.combo_ticker_layout.currentData() or "bottom_ticker",

            ticker_font_size=self.combo_ticker_font_size.currentData() or 16,

            ticker_font=self.combo_ticker_font.currentText(),

            ticker_color=self.ticker_color_val,

            ticker_bold=self.cb_ticker_bold.isChecked(),

            ticker_anim_style=self.combo_ticker_anim_style.currentData() or "together",

            ticker_frameless=self.cb_ticker_frameless.isChecked(),

            ticker_pos_x=self.saved_ticker_pos_x,

            ticker_pos_y=self.saved_ticker_pos_y,

            ticker_scale=self.saved_ticker_scale,

            ticker_anim_in=self.combo_anim_in.currentData() or "slide-up",

            ticker_anim_out=self.combo_anim_out.currentData() or "slide-down",

            ticker_delay_sec=0.0,



            # Image

            image_enabled=not is_ticker,

            image_url=self.inp_img_url.text().strip(),

            image_frameless=not self.cb_image_framed.isChecked(),

            image_top_text=self.inp_img_top.text().strip(),

            image_bottom_text=self.inp_img_bot.text().strip(),

            image_pos_x=self.saved_image_pos_x,

            image_pos_y=self.saved_image_pos_y,

            image_scale=self.saved_image_scale,

            image_anim_in=self.combo_anim_in.currentData() or "slide-left",

            image_anim_out=self.combo_anim_out.currentData() or "slide-right",

            image_delay_sec=0.0,



            # Sub-command

            position_preset=self.combo_ticker_preset.currentData() if is_ticker else self.combo_img_preset.currentData(),

            sub_command=getattr(self.cmd, "sub_command", None),

            sub_command_delay=self.timeline.sub_delay,

        )



    def _on_toggle_test_anim(self):

        if not self.is_anim_in_active:

            # 1. กดทดสอบ In -> แสดง In ขึ้นจอ และค้างไว้

            self.is_anim_in_active = True

            self.btn_test_anim.setText("⏹ ทดสอบ Out")

            self.btn_test_anim.setStyleSheet("background: #831843; color: #f472b6; font-weight: 700; border-radius: 2px; border: 1px solid #db2777; margin-top: 18px; padding: 7px 18px;")

            temp_cmd = self._build_command_from_ui()

            temp_cmd.duration_sec = 120

            if self.service:

                self.service.show_replie(temp_cmd, triggered_by="Streamer (Anim In Hold)", test_mode="in_hold")

        else:

            # 2. กดทดสอบ Out -> แสดงอนิเมชัน Out ทันที และเคลียร์จอ

            self.is_anim_in_active = False

            self.btn_test_anim.setText("▶ ทดสอบ In")

            self.btn_test_anim.setStyleSheet("background: #065f46; color: #34d399; font-weight: 700; border-radius: 2px; border: 1px solid #059669; margin-top: 18px; padding: 7px 18px;")

            if self.service:

                self.service.dismiss_current()



    def _test_countdown_live(self, cd_type="number"):

        temp_cmd = self._build_command_from_ui()

        temp_cmd.duration_sec = 10

        temp_cmd.countdown_type = cd_type

        if self.service:

            self.service.show_replie(temp_cmd, triggered_by=f"Streamer (Countdown {cd_type})")



    def _on_live_demo_clicked(self):

        if self.is_live_demo_active:

            # กดซ้ำเพื่อซ่อนทันที

            self._stop_live_demo()

        else:

            # กดเริ่มการทดสอบบน Overlay สด

            self._start_live_demo()



    def _start_live_demo(self):

        temp_cmd = self._build_command_from_ui()

        if not self.service:

            return

        self.is_live_demo_active = True

        self.btn_live_demo.setText("⏹ ซ่อนทันที (กำลังแสดง)")

        self.btn_live_demo.setStyleSheet("background: #991b1b; color: #fca5a5; border: 1px solid #ef4444; border-radius: 2px; font-weight: 700; padding: 8px 18px;")

        self.service.show_replie(temp_cmd, triggered_by="Streamer (Live Demo)")



        dur = max(2, temp_cmd.duration_sec)

        self._demo_timer.stop()

        self._demo_timer.start(dur * 1000)



    def _stop_live_demo(self):

        self._demo_timer.stop()

        if self.service:

            self.service.dismiss_current()

        self._reset_live_demo_btn()



    def _reset_live_demo_btn(self):

        self.is_live_demo_active = False

        self.btn_live_demo.setText("🚀 ทดสอบบน Overlay สด")

        self.btn_live_demo.setStyleSheet("background: #7e22ce; color: #fff; border: 1px solid #a855f7; border-radius: 2px; font-weight: 700; padding: 8px 18px;")



    def _on_save_clicked(self):

        built = self._build_command_from_ui()

        name = built.name

        if not name or name == "!":

            QMessageBox.warning(self, "ข้อผิดพลาด", "กรุณาระบุชื่อคำสั่งให้ถูกต้อง (เช่น !donate)")

            return

        # ── ตรวจสอบคำสั่งซ้ำกับ Playroom Overlay ──
        playroom_triggers = []
        if self.service and getattr(self.service, "settings", None):
            playroom_triggers = getattr(self.service.settings, "playroom_triggers", []) or []
        elif hasattr(self, "parent_app") and getattr(self.parent_app, "settings", None):
            playroom_triggers = getattr(self.parent_app.settings, "playroom_triggers", []) or []

        name_lower = name.lower()
        name_clean = name.lstrip("!#/").lower()

        for trig in playroom_triggers:
            if isinstance(trig, dict):
                t_code = (trig.get("code") or trig.get("trigger") or "").strip()
            else:
                t_code = str(trig).strip()
            if not t_code:
                continue
            t_lower = t_code.lower()
            t_clean = t_code.lstrip("!#/").lower()
            if name_lower == t_lower or (name_clean and name_clean == t_clean):
                QMessageBox.critical(
                    self,
                    "คำสั่งซ้ำกับ Playroom",
                    f"⚠️ คำสั่ง '{name}' ซ้ำกับคำสั่ง '{t_code}' ของระบบ Playroom Overlay ครับ!\n\n"
                    f"กรุณาเปลี่ยนชื่อคำสั่งเพื่อป้องกันความสับสนและไม่ให้คำสั่งทับซ้อนกันครับ"
                )
                if hasattr(self, "inp_name"):
                    self.inp_name.setFocus()
                    self.inp_name.selectAll()
                return

        # ── ตรวจสอบคำสั่งซ้ำกับคำสั่งอื่นใน Replie ──
        if self.service and getattr(self.service, "commands", None):
            orig = getattr(self, "orig_name", "") or ""
            for existing_name in self.service.commands.keys():
                if existing_name.lower() == name_lower and existing_name.lower() != orig.lower():
                    QMessageBox.warning(
                        self,
                        "คำสั่งซ้ำ",
                        f"⚠️ มีคำสั่ง '{name}' ในระบบ Replie อยู่แล้วครับ กรุณาใช้ชื่อคำสั่งอื่น"
                    )
                    if hasattr(self, "inp_name"):
                        self.inp_name.setFocus()
                        self.inp_name.selectAll()
                    return



        for k, v in built.__dict__.items():

            setattr(self.cmd, k, v)



        self._stop_live_demo()

        if self.is_anim_in_active and self.service:

            self.service.dismiss_current()

        if self.service:

            if hasattr(self, "orig_name") and self.orig_name and self.orig_name != "!new":

                if self.orig_name.lower() != self.cmd.name.lower():

                    self.service.commands.pop(self.orig_name.lower(), None)

            self.service.commands[self.cmd.name.lower()] = self.cmd

            self.service.save_settings()

            self.service.show_replie(self.cmd, triggered_by="Streamer (Save)")



        self.accept()



    def reject(self):

        self._stop_live_demo()

        if self.is_anim_in_active and self.service:

            self.service.dismiss_current()

        super().reject()



    def closeEvent(self, event):

        self._stop_live_demo()

        if self.is_anim_in_active and self.service:

            self.service.dismiss_current()

        super().closeEvent(event)



    def get_command(self):

        return self.cmd





# ════════════════════════════════════════════════════════════════════════════

# 🖼️ Main Replie Window Panel (RepliePanel)

# ════════════════════════════════════════════════════════════════════════════

class ReorderableTableWidget(QTableWidget):

    rowMoved = Signal(int, int)



    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.setDragEnabled(True)

        self.setAcceptDrops(True)

        self.viewport().setAcceptDrops(True)

        self.setDragDropOverwriteMode(False)

        self.setDropIndicatorShown(True)

        self.setSelectionMode(QAbstractItemView.SingleSelection)

        self.setSelectionBehavior(QAbstractItemView.SelectRows)

        self.setDragDropMode(QAbstractItemView.DragDrop)

        self.setDefaultDropAction(Qt.CopyAction)

        self._drag_start_row = -1



    def startDrag(self, supportedActions):

        self._drag_start_row = self.currentRow()

        super().startDrag(Qt.CopyAction)



    def dragEnterEvent(self, event):

        if event.source() == self:

            event.acceptProposedAction()

        else:

            event.ignore()



    def dragMoveEvent(self, event):

        if event.source() == self:

            event.acceptProposedAction()

        else:

            event.ignore()



    def dropEvent(self, event):

        if event.source() == self:

            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()

            target_row = self.rowAt(pos.y())

            if target_row < 0:

                target_row = self.rowCount() - 1

            src_row = self._drag_start_row

            event.ignore()

            if src_row >= 0 and src_row != target_row:

                QTimer.singleShot(0, lambda s=src_row, t=target_row: self.rowMoved.emit(s, t))

        else:

            event.ignore()



class RepliePanel(QWidget):

    """หน้าต่างแผงควบคุมหลักของระบบ Replie พร้อมตารางแบบโมเดิร์นตามที่ผู้ใช้ออกแบบ"""



    closed = Signal()



    def __init__(self, service, parent_app=None):

        super().__init__(parent_app if (parent_app is not None and isinstance(parent_app, QWidget)) else None)

        self.service = service

        self.parent_app = parent_app

        self.settings = getattr(service, "settings", None)



        self.is_edit_mode: bool = False

        self._demo_timers: Dict[str, QTimer] = {}

        self._demo_buttons: Dict[str, QPushButton] = {}

        self._toggle_buttons: Dict[str, QPushButton] = {}

        if hasattr(self.service, "status_changed"):

            self.service.status_changed.connect(self._on_service_status_changed)



        self.setWindowTitle("🖼️ Replie — จัดการคำสั่งตอบกลับภาพ/ข้อความบนจอ Overlay")

        self.resize(800, 580)

        self.setMinimumSize(720, 500)

        self.setWindowFlags(Qt.Window | Qt.WindowCloseButtonHint | Qt.WindowMinMaxButtonsHint)



        self.setStyleSheet("""

            QWidget {

                background-color: #0b1120;

                color: #f8fafc;

                font-family: -apple-system, BlinkMacSystemFont, "Kanit", "Segoe UI", sans-serif;

                font-size: 13px;

            }

            QPushButton {

                background: #1e293b;

                color: #f8fafc;

                border: 1px solid #334155;

                border-radius: 2px;

                padding: 6px 14px;

                font-weight: 700;

            }

            QPushButton:hover {

                background: #334155;

                border-color: #38bdf8;

            }

            QTableWidget {

                background-color: #0b1120;

                border: 1px solid #1e293b;

                border-radius: 8px;

                gridline-color: transparent;

                selection-background-color: #182844;

                selection-color: #38bdf8;

                outline: none;

            }

            QTableWidget::item {

                padding: 4px 8px;

                border-bottom: 1px solid #162032;

                color: #f8fafc;

            }

            QTableWidget::item:selected {

                background-color: #182844;

                color: #38bdf8;

                font-weight: 700;

            }

            QTableWidget::item:selected:hover {

                background-color: #203456;

                color: #38bdf8;

            }

            QTableWidget::item:hover {

                background-color: #0f1a2e;

            }

            QHeaderView::section {

                background: #162032;

                color: #94a3b8;

                padding: 8px 10px;

                border: none;

                border-bottom: 1px solid #1e293b;

                font-weight: 700;

            }

        """)



        self.stack = QStackedWidget(self)



        # ── Page 0: Main Replie Dashboard ──

        self.main_content = QWidget()

        self.main_content.setStyleSheet("background: transparent;")

        layout = QVBoxLayout(self.main_content)

        layout.setContentsMargins(16, 14, 16, 14)

        layout.setSpacing(12)



        # ── 1. Top Bar: Title & [Edit]/[OK] & [+ เพิ่มคำสั่งใหม่] ──

        top_bar = QHBoxLayout()

        v_title = QVBoxLayout()

        lbl_title = QLabel("📋 ตารางรายการคำสั่ง Replie")

        lbl_title.setStyleSheet("font-size: 16px; font-weight: 800; color: #38bdf8;")

        v_title.addWidget(lbl_title)

        lbl_subtitle = QLabel("ผู้ชมพิมพ์คำสั่งในแชทเพื่อแสดงภาพหรือข้อความขึ้นจอ OBS Overlay")

        lbl_subtitle.setStyleSheet("color: #64748b; font-size: 11.5px;")

        v_title.addWidget(lbl_subtitle)

        top_bar.addLayout(v_title)



        top_bar.addStretch()



        self.btn_edit_mode = QPushButton("✏️ Edit")

        self.btn_edit_mode.setCursor(Qt.PointingHandCursor)

        self.btn_edit_mode.setStyleSheet("background: #1e293b; color: #f8fafc; border: 1px solid #475569; border-radius: 2px; font-weight: 700; padding: 7px 18px;")

        self.btn_edit_mode.clicked.connect(self._toggle_edit_mode)

        top_bar.addWidget(self.btn_edit_mode)



        self.btn_add = QPushButton("➕ เพิ่มคำสั่งใหม่")

        self.btn_add.setCursor(Qt.PointingHandCursor)

        self.btn_add.setStyleSheet("background: #0284c7; color: #fff; border: 1px solid #38bdf8; border-radius: 2px; font-weight: 700; padding: 7px 18px;")

        self.btn_add.clicked.connect(self._on_add_command)

        top_bar.addWidget(self.btn_add)



        layout.addLayout(top_bar)



        # ── 2. Compact AFK Loop Mode Bar ──

        loop_bar = QHBoxLayout()

        loop_bar.setSpacing(10)



        lbl_loop_icon = QLabel("🔁 วนลูปอัตโนมัติ (AFK):")

        lbl_loop_icon.setStyleSheet("color: #c084fc; font-weight: 700; font-size: 12.5px;")

        loop_bar.addWidget(lbl_loop_icon)



        self.cb_loop_cmd = QComboBox()

        self.cb_loop_cmd.setMinimumWidth(180)

        self.cb_loop_cmd.addItem("🔄 สลับทุกคำสั่งอัตโนมัติ", "__all__")

        for cname in self.service.commands.keys():

            self.cb_loop_cmd.addItem(f"คำสั่ง {cname}", cname)

        loop_bar.addWidget(self.cb_loop_cmd)



        self.cb_loop_interval = QComboBox()

        self.cb_loop_interval.setMinimumWidth(110)

        self.cb_loop_interval.addItem("เว้นช่วง 20 วิ", 20)

        self.cb_loop_interval.addItem("เว้นช่วง 30 วิ", 30)

        self.cb_loop_interval.addItem("เว้นช่วง 45 วิ", 45)

        self.cb_loop_interval.addItem("เว้นช่วง 60 วิ", 60)

        self.cb_loop_interval.addItem("เว้นช่วง 2 นาที", 120)

        self.cb_loop_interval.setCurrentIndex(2)

        loop_bar.addWidget(self.cb_loop_interval)



        self.btn_toggle_loop = QPushButton("▶ เริ่มวนลูป")

        self.btn_toggle_loop.setCursor(Qt.PointingHandCursor)

        self.btn_toggle_loop.setStyleSheet("background: #7e22ce; color: #fff; font-weight: 700; border: 1px solid #a855f7; border-radius: 2px; padding: 6px 16px;")

        self.btn_toggle_loop.clicked.connect(self._on_toggle_loop_clicked)

        loop_bar.addWidget(self.btn_toggle_loop)



        loop_bar.addStretch()

        layout.addLayout(loop_bar)



        # ── 3. Table View (Row Height 46px, Zero Clipping) ──

        self.table = ReorderableTableWidget()

        self.table.rowMoved.connect(self._on_table_row_moved)

        self.table.verticalHeader().setDefaultSectionSize(46)

        self.table.verticalHeader().setVisible(False)

        self.table.setSelectionBehavior(QTableWidget.SelectRows)

        self.table.setShowGrid(False)

        self.table.setAlternatingRowColors(True)

        self.table.setStyleSheet("""

            QTableWidget::item {

                padding: 4px 8px;

                border-bottom: 1px solid #162032;

            }

            QTableWidget::item:alternate {

                background: #0d1527;

            }

        """)

        layout.addWidget(self.table)



        self._refresh_table()



        # Bottom Dock Hint

        lbl_hint = QLabel("💡 จัดการด่วน: สามารถสั่งยิงคำสั่ง, ปิดเสียงชั่วคราว, หรือกด [✕ ซ่อนทันที] ได้ผ่านหน้าต่าง OBS Dock ตลอดเวลาครับ")

        lbl_hint.setStyleSheet("color: #64748b; font-size: 11.5px;")

        layout.addWidget(lbl_hint)



        # ── Page 1: Blocker widget when Replie is missing from overlay ──

        self.blocker_widget = self._build_blocker_widget()



        self.stack.addWidget(self.main_content)

        self.stack.addWidget(self.blocker_widget)



        root_layout = QVBoxLayout(self)

        root_layout.setContentsMargins(0, 0, 0, 0)

        root_layout.addWidget(self.stack)



        self._sync_timer = QTimer(self)

        self._sync_timer.setInterval(1000)

        self._sync_timer.timeout.connect(self._sync_loop_state)

        self._sync_timer.start()



        # ตัวตรวจเช็คสถานะ Widget ใน Overlay เป็นระยะ (เช็คทุก 1.5 วินาที)

        self._widget_check_timer = QTimer(self)

        self._widget_check_timer.setInterval(1500)

        self._widget_check_timer.timeout.connect(self._check_widget_status)

        self._widget_check_timer.start()

        self._check_widget_status()



    def showEvent(self, event):

        super().showEvent(event)

        self._check_widget_status()

        self._refresh_table()



    def _build_blocker_widget(self) -> QWidget:

        """สร้างหน้าต่างแจ้งเตือนเมื่อยังไม่ได้วาง Widget Replie บน Overlay"""

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



        title_lbl = QLabel("ยังไม่ได้เพิ่ม Widget Replie (ตอบกลับภาพ/ข้อความ) บนหน้าจอ Overlay")

        title_lbl.setAlignment(Qt.AlignCenter)

        title_lbl.setStyleSheet("font-size: 17px; font-weight: 800; color: #f59e0b; background: transparent; border: none;")

        v.addWidget(title_lbl)



        desc_lbl = QLabel(

            "เพื่อให้ระบบสามารถแสดงภาพ QR Code, แถบตัวหนังสือวิ่ง และข้อความตอบกลับบนหน้าจอ OBS ได้อย่างถูกต้อง\n"

            "กรุณาเปิด Overlay Composer แล้วกดปุ่ม \"+ Replie\" เพื่อวาง Widget ลงบนหน้าจอก่อนครับ"

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

        s2 = QLabel("2️⃣  กดปุ่ม <b>\"+ Replie\"</b> ในแถบเครื่องมือเพื่อวาง Widget บนหน้าจอ")

        s3 = QLabel("3️⃣  เมื่อเพิ่มเรียบร้อยแล้ว หน้านี้จะ<b>ปลดล็อคให้อัตโนมัติทันที</b> เพื่อให้คุณเริ่มใช้งานและทดสอบคำสั่งได้ครับ")

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

            "background-color: #0284c7; color: #ffffff; border: none; border-radius: 6px; "

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

        """เช็คว่ามี Widget Replie ใน Overlay หรือยัง"""

        try:

            if hasattr(self, "service") and self.service and hasattr(self.service, "is_widget_installed"):

                return bool(self.service.is_widget_installed())

            app_inst = self.parent_app or (self.parent() if callable(getattr(self, "parent", None)) else None)

            if app_inst and hasattr(app_inst, "_replie_widget_exists"):

                return bool(app_inst._replie_widget_exists())

            if app_inst and hasattr(app_inst, "composer_server") and app_inst.composer_server:

                return bool(app_inst.composer_server._is_widget_installed("replie"))

            if self.settings:

                widgets = list(getattr(self.settings, "composer_widgets", []) or [])

                if any(isinstance(w, dict) and w.get("type") == "replie" and w.get("enabled", True) for w in widgets):

                    return True

                pages = getattr(self.settings, "composer_pages", []) or []

                for p in pages:

                    if isinstance(p, dict):

                        pw = p.get("widgets", [])

                        if any(isinstance(w, dict) and w.get("type") == "replie" and w.get("enabled", True) for w in pw):

                            return True

        except Exception:

            pass

        return False



    def _check_widget_status(self):

        """ตรวจเช็คสถานะการติดตั้ง Widget Replie และสลับหน้าแสดงผลอัตโนมัติ"""

        installed = self._is_widget_installed()

        if installed:

            if self.stack.currentIndex() != 0:

                self.stack.setCurrentIndex(0)

                if hasattr(self, "btn_edit_mode"):

                    self.btn_edit_mode.setEnabled(True)

                if hasattr(self, "btn_add"):

                    self.btn_add.setEnabled(True)

                if hasattr(self, "btn_toggle_loop"):

                    self.btn_toggle_loop.setEnabled(True)

        else:

            if self.stack.currentIndex() != 1:

                self.stack.setCurrentIndex(1)

                if hasattr(self, "btn_edit_mode"):

                    self.btn_edit_mode.setEnabled(False)

                if hasattr(self, "btn_add"):

                    self.btn_add.setEnabled(False)

                if hasattr(self, "btn_toggle_loop"):

                    self.btn_toggle_loop.setEnabled(False)



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

            elif self.settings:

                port = getattr(self.settings, "composer_port", 8801)

        except Exception:

            pass

        webbrowser.open(f"http://localhost:{port}/editor")



    def closeEvent(self, event):

        self.closed.emit()

        super().closeEvent(event)



    def _toggle_edit_mode(self):

        if self.is_edit_mode:

            self._save_checkbox_states()

            self.is_edit_mode = False

            self.btn_edit_mode.setText("✏️ Edit")

            self.btn_edit_mode.setStyleSheet("background: #1e293b; color: #f8fafc; border: 1px solid #475569; border-radius: 2px; font-weight: 700; padding: 7px 18px;")

        else:

            self.is_edit_mode = True

            self.btn_edit_mode.setText("✅ OK")

            self.btn_edit_mode.setStyleSheet("background: #059669; color: #fff; border: 1px solid #34d399; border-radius: 2px; font-weight: 800; padding: 7px 22px;")



        self._refresh_table()



    def _on_table_row_moved(self, from_row: int, to_row: int):
        if not self.service or not getattr(self.service, "commands", None):
            return
        items = list(self.service.commands.items())
        if 0 <= from_row < len(items) and 0 <= to_row < len(items):
            moved_item = items.pop(from_row)
            items.insert(to_row, moved_item)
            self.service.commands = dict(items)
            self.service.save_settings()
            self.service._broadcast_dock_status()
            self._refresh_table()
            self.table.selectRow(to_row)

    def _save_checkbox_states(self):

        if not self.service:

            return

        for row in range(self.table.rowCount()):

            w_chk = self.table.cellWidget(row, 1)

            if w_chk:

                btn = w_chk.findChild(QPushButton)

                cname = w_chk.property("cmd_name")

                if btn and cname and cname in self.service.commands:

                    self.service.commands[cname].enabled = btn.isChecked()

        self.service.save_settings()



    def _refresh_table(self):

        self.table.setRowCount(0)

        self._demo_buttons.clear()

        self._toggle_buttons.clear()

        if not self.service:

            return



        if self.is_edit_mode:

            self.table.setColumnCount(7)

            self.table.setHorizontalHeaderLabels(["⠿", "เลือก", "ประเภท", "คำสั่งเรียก", "คำอธิบาย คำสั่งนี้ว่าคืออะไร", "ระยะเวลาแสดงบนจอ", "จัดการ"])

            self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)

            self.table.setColumnWidth(0, 36)

            self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)

            self.table.setColumnWidth(1, 85)

            self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)

            self.table.setColumnWidth(2, 65)

            self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)

            self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)

            self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)

            self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Fixed)

            self.table.setColumnWidth(6, 215)

        else:

            self.table.setColumnCount(6)

            self.table.setHorizontalHeaderLabels(["⠿", "ประเภท", "คำสั่งเรียก", "คำอธิบาย คำสั่งนี้ว่าคืออะไร", "ระยะเวลาแสดงบนจอ", "จัดการ"])

            self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)

            self.table.setColumnWidth(0, 36)

            self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)

            self.table.setColumnWidth(1, 65)

            self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)

            self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)

            self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)

            self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Fixed)

            self.table.setColumnWidth(5, 215)



        col_offset = 2 if self.is_edit_mode else 1



        for name, cmd in self.service.commands.items():

            row = self.table.rowCount()

            self.table.insertRow(row)



            # Drag Handle in Column 0

            item_drag = QTableWidgetItem("⠿")

            item_drag.setTextAlignment(Qt.AlignCenter)

            item_drag.setToolTip("คลิกค้างแล้วลากเพื่อสลับลำดับคำสั่ง (มีผลกับ OBS Dock ทันที)")

            item_drag.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled)

            self.table.setItem(row, 0, item_drag)



            # Checkbox / Toggle in Edit mode (Column 1)

            if self.is_edit_mode:

                w_chk = QWidget()

                w_chk.setProperty("cmd_name", name)

                l_chk = QHBoxLayout(w_chk)

                l_chk.setContentsMargins(4, 2, 4, 2)

                l_chk.setAlignment(Qt.AlignCenter)



                btn_toggle = QPushButton("☑ ใช้" if cmd.enabled else "☐ ปิด")

                btn_toggle.setCheckable(True)

                btn_toggle.setChecked(cmd.enabled)

                btn_toggle.setFixedHeight(26)

                btn_toggle.setFixedWidth(64)

                if cmd.enabled:

                    btn_toggle.setStyleSheet("background: #059669; color: #ffffff; font-weight: 700; font-size: 11.5px; border: none; border-radius: 4px;")

                else:

                    btn_toggle.setStyleSheet("background: #1e293b; color: #94a3b8; font-weight: 600; font-size: 11.5px; border: 1px solid #334155; border-radius: 4px;")



                def _on_toggle(chk, b=btn_toggle, cname=name):

                    if chk:

                        b.setText("☑ ใช้")

                        b.setStyleSheet("background: #059669; color: #ffffff; font-weight: 700; font-size: 11.5px; border: none; border-radius: 4px;")

                    else:

                        b.setText("☐ ปิด")

                        b.setStyleSheet("background: #1e293b; color: #94a3b8; font-weight: 600; font-size: 11.5px; border: 1px solid #334155; border-radius: 4px;")

                    if self.service and cname in self.service.commands:

                        self.service.commands[cname].enabled = chk



                btn_toggle.toggled.connect(_on_toggle)

                self._toggle_buttons[name.lower()] = btn_toggle

                l_chk.addWidget(btn_toggle)

                self.table.setCellWidget(row, 1, w_chk)



            # Icon column (Only icon, hover tooltip)

            has_ticker = cmd.ticker_enabled

            has_image = cmd.image_enabled or bool(getattr(cmd, "sub_command", None))

            if has_ticker and has_image:

                icon_str = "🗨+🖼️"

                tooltip_str = "ข้อความผสมรูปภาพ (Combo / Sequence)"

            elif has_image:

                icon_str = "🖼️"

                tooltip_str = "รูปภาพ / QR Code (Image)"

            else:

                icon_str = "🗨"

                tooltip_str = "ข้อความวิ่ง / แถบข้อความ (Message Ticker)"



            item_icon = QTableWidgetItem(icon_str)

            item_icon.setTextAlignment(Qt.AlignCenter)

            item_icon.setToolTip(tooltip_str)

            item_icon.setFlags((item_icon.flags() & ~Qt.ItemIsEditable) | Qt.ItemIsDragEnabled)

            self.table.setItem(row, col_offset + 0, item_icon)



            # Command name

            item_name = QTableWidgetItem(cmd.name)

            item_name.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)

            item_name.setFlags((item_name.flags() & ~Qt.ItemIsEditable) | Qt.ItemIsDragEnabled)

            item_name.setFont(QFont("Segoe UI", 10, QFont.Bold))

            self.table.setItem(row, col_offset + 1, item_name)



            # Description

            desc_text = getattr(cmd, "desc", "") or cmd.title or cmd.text or "ไม่มีคำอธิบาย"

            item_desc = QTableWidgetItem(desc_text)

            item_desc.setToolTip(desc_text)

            item_desc.setFlags((item_desc.flags() & ~Qt.ItemIsEditable) | Qt.ItemIsDragEnabled)

            self.table.setItem(row, col_offset + 2, item_desc)



            # Duration

            item_dur = QTableWidgetItem(f"{cmd.duration_sec} วินาที")

            item_dur.setTextAlignment(Qt.AlignCenter)

            item_dur.setFlags((item_dur.flags() & ~Qt.ItemIsEditable) | Qt.ItemIsDragEnabled)

            self.table.setItem(row, col_offset + 3, item_dur)



            # Action buttons [DEMO / STOP][EDIT][🗑]

            w_act = QWidget()

            w_act.setMinimumWidth(205)

            l_act = QHBoxLayout(w_act)

            l_act.setContentsMargins(2, 4, 2, 4)

            l_act.setSpacing(6)

            l_act.setAlignment(Qt.AlignCenter)



            btn_demo = QPushButton("▶ DEMO")

            btn_demo.setFixedHeight(28)

            btn_demo.setFixedWidth(82)

            btn_demo.setToolTip("ยิงตัวนี้ขึ้นจอเพื่อทดสอบการแสดงผล")

            btn_demo.setStyleSheet("""

                QPushButton {

                    background: #059669;

                    color: #ffffff;

                    font-weight: 700;

                    font-size: 11px;

                    border: none;

                    border-radius: 4px;

                    padding: 0 4px;

                }

                QPushButton:hover { background: #10b981; }

            """)

            self._demo_buttons[cmd.name.lower()] = btn_demo

            btn_demo.clicked.connect(lambda _, c=cmd, b=btn_demo: self._on_demo_clicked(c, b))



            btn_edit = QPushButton("✏️ EDIT")

            btn_edit.setFixedHeight(28)

            btn_edit.setFixedWidth(70)

            btn_edit.setToolTip("แก้ไขรายละเอียดคำสั่งนี้")

            btn_edit.setStyleSheet("""

                QPushButton {

                    background: #1e293b;

                    color: #f8fafc;

                    font-weight: 700;

                    font-size: 11px;

                    border: 1px solid #334155;

                    border-radius: 4px;

                    padding: 0 4px;

                }

                QPushButton:hover { background: #334155; border-color: #38bdf8; }

            """)

            btn_edit.clicked.connect(lambda _, c=cmd: self._on_edit_command(c))



            # Delete button (🗑 ONLY, no X!)

            btn_del = QPushButton("🗑")

            btn_del.setFixedSize(28, 28)

            btn_del.setToolTip("ลบคำสั่งนี้")

            btn_del.setStyleSheet("""

                QPushButton {

                    background: #7f1d1d;

                    color: #fca5a5;

                    font-size: 13.5px;

                    border: 1px solid #991b1b;

                    border-radius: 4px;

                    padding: 0;

                }

                QPushButton:hover { background: #991b1b; color: #ffffff; }

            """)

            btn_del.clicked.connect(lambda _, cname=name: self._on_delete_command(cname))



            l_act.addWidget(btn_demo)

            l_act.addWidget(btn_edit)

            l_act.addWidget(btn_del)

            self.table.setCellWidget(row, col_offset + 4, w_act)



        self._sync_active_buttons()



    def _sync_active_buttons(self):

        import time

        now = time.time()

        active_cmd = None

        if self.service and getattr(self.service, "current_active", None) and getattr(self.service, "active_until", 0) > now:

            active_cmd = self.service.current_active.get("name")

        self._update_demo_buttons_state(active_cmd)



    def _on_service_status_changed(self, dock_data: dict):

        active_cmd = dock_data.get("active_command") if dock_data.get("is_active") else None

        self._update_demo_buttons_state(active_cmd)

        if self.is_edit_mode and self.service:

            for cname, b_tog in self._toggle_buttons.items():

                c_obj = self.service.commands.get(cname)

                if c_obj:

                    b_tog.blockSignals(True)

                    b_tog.setChecked(c_obj.enabled)

                    if c_obj.enabled:

                        b_tog.setText("☑ ใช้")

                        b_tog.setStyleSheet("background: #059669; color: #ffffff; font-weight: 700; font-size: 11.5px; border: none; border-radius: 4px;")

                    else:

                        b_tog.setText("☐ ปิด")

                        b_tog.setStyleSheet("background: #1e293b; color: #94a3b8; font-weight: 600; font-size: 11.5px; border: 1px solid #334155; border-radius: 4px;")

                    b_tog.blockSignals(False)



    def _update_demo_buttons_state(self, active_cmd: Optional[str]):

        act_lower = active_cmd.lower() if active_cmd else None

        for cname, btn in self._demo_buttons.items():

            if act_lower and cname == act_lower:

                btn.setText("⏹️ STOP")

                btn.setStyleSheet("""

                    QPushButton {

                        background: #dc2626;

                        color: #ffffff;

                        font-weight: 800;

                        font-size: 11px;

                        border: 1px solid #f87171;

                        border-radius: 4px;

                        padding: 0 4px;

                    }

                    QPushButton:hover { background: #ef4444; }

                """)

            else:

                btn.setText("▶ DEMO")

                btn.setStyleSheet("""

                    QPushButton {

                        background: #059669;

                        color: #ffffff;

                        font-weight: 700;

                        font-size: 11px;

                        border: none;

                        border-radius: 4px;

                        padding: 0 4px;

                    }

                    QPushButton:hover { background: #10b981; }

                """)



    def _on_demo_clicked(self, cmd, btn: QPushButton):

        if btn.text() == "⏹️ STOP":

            self.service.dismiss_current()

            return



        self.service.show_replie(cmd, triggered_by="Streamer (Demo)")



    def _on_add_command(self):

        from replie_service import ReplieCommand

        new_cmd = ReplieCommand(name="!new")

        dlg = ReplieEditDialog(self, new_cmd, self.service.commands)

        if dlg.exec_():

            cmd = dlg.get_command()

            self.service.commands[cmd.name.lower()] = cmd

            self.service.save_settings()

            self._refresh_table()



    def _on_edit_command(self, cmd):

        orig_name = cmd.name

        dlg = ReplieEditDialog(self, cmd, self.service.commands)

        if dlg.exec_():

            updated = dlg.get_command()

            if orig_name.lower() != updated.name.lower():

                self.service.commands.pop(orig_name.lower(), None)

            self.service.commands[updated.name.lower()] = updated

            self.service.save_settings()

            self._refresh_table()



    def _on_delete_command(self, cname: str):

        if QMessageBox.question(self, "ยืนยันการลบ", f"ต้องการลบคำสั่ง {cname} หรือไม่?",

                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:

            if self.service and cname in self.service.commands:

                del self.service.commands[cname]

                self.service.save_settings()

                self._refresh_table()



    def _on_toggle_loop_clicked(self):

        if self.service.loop_active:

            self.service.stop_loop()

        else:

            target = self.cb_loop_cmd.currentData() or "__all__"

            interval = self.cb_loop_interval.currentData() or 45

            self.service.start_loop(target, interval)

        self._sync_loop_state()



    def _sync_loop_state(self):

        if hasattr(self, "btn_toggle_loop"):

            if self.service.loop_active:

                target_name = self.service.loop_command

                target_str = "สลับทุกคำสั่ง" if target_name == "__all__" else (target_name or "")

                self.btn_toggle_loop.setText(f"⏹️ หยุดวนลูป ({target_str})")

                self.btn_toggle_loop.setStyleSheet("background: #ef4444; color: #fff; font-weight: 700; border-color: #f87171; padding: 6px 16px;")

            else:

                self.btn_toggle_loop.setText("▶ เริ่มวนลูป")

                self.btn_toggle_loop.setStyleSheet("background: #7e22ce; color: #fff; font-weight: 700; border: 1px solid #a855f7; border-radius: 2px; padding: 6px 16px;")

