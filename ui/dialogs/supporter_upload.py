"""supporter_upload.py — Dialog ส่งหลักฐานการสนับสนุน (ในโปรแกรม)

Multi-channel form:
  - 🏦 ธนาคาร → เลือก "แนบสลิป" หรือ "กรอกข้อมูล"
    - แนบสลิป → เลือกไฟล์รูป
    - กรอกข้อมูล → เลือกธนาคาร + วันที่ + เวลา
  - 💵 True Money → วันที่ + เวลา (กรอกข้อมูลอย่างเดียว)

จำนวนเงิน + ชื่อที่แสดง + ข้อความ — ทุกกรณี

★ Reactive: fields ซ่อน/แสดงตามตัวเลือก (setVisible)
★ Background thread → ไม่ค้าง UI
"""
import logging
import os
from datetime import date as _date, datetime as _dt

from PySide6.QtCore import Qt, QThread, Signal, QDate, QTime
from PySide6.QtWidgets import (
    QDialog, QWidget, QFrame, QLabel, QPushButton, QLineEdit, QVBoxLayout,
    QHBoxLayout, QFileDialog, QMessageBox, QComboBox, QDoubleSpinBox,
    QProgressBar, QTextEdit, QDateEdit, QTimeEdit, QButtonGroup, QRadioButton,
    QSizePolicy,
)
from PySide6.QtGui import QPixmap

logger = logging.getLogger("supporter_upload")

# ★ รายชื่อธนาคาร (code, ชื่อเต็ม)
BANKS = [
    ("SCB",   "ธนาคารไทยพาณิชย์"),
    ("KBANK", "ธนาคารกสิกรไทย"),
    ("BBL",   "ธนาคารกรุงเทพ"),
    ("KTB",   "ธนาคารกรุงไทย"),
    ("BAY",   "ธนาคารกรุงศรีอยุธยา"),
    ("TTB",   "ธนาคารทหารไทยธนชาต"),
    ("GHB",   "ธนาคารอาคารสงเคราะห์"),
    ("CIMB",  "ธนาคารซีไอเอ็มบีไทย"),
    ("UOB",   "ธนาคารยูโอบี"),
    ("LH",    "ธนาคารแลนด์ แอนด์ ฮาวส์"),
    ("OTHER", "อื่นๆ"),
]


class _SubmitThread(QThread):
    """Background thread สำหรับ submit (กัน UI ค้าง)"""
    finished_sig = Signal(dict)
    progress_sig = Signal(int)

    def __init__(self, payload, api_url):
        """
        payload = {
            'name', 'amount', 'currency', 'message',
            'channel', 'method', 'bank', 'transfer_date', 'transfer_time',
            'slip_path' (optional)
        }
        """
        super().__init__()
        self.payload = payload
        self.api_url = api_url

    def run(self):
        try:
            from supporters_api import submit_supporter
            self.progress_sig.emit(20)
            result = submit_supporter(
                api_url=self.api_url,
                **self.payload,
            )
            self.progress_sig.emit(100)
            self.finished_sig.emit(result)
        except Exception as e:
            self.finished_sig.emit({"ok": False, "error": f"เกิดข้อผิดพลาด: {e}"})


class SupporterUploadDialog(QDialog):
    """Dialog ส่งหลักฐานการสนับสนุน — multi-channel reactive form"""

    def __init__(self, parent=None, api_url="https://men9ch.com/api"):
        super().__init__(parent)
        self._api_url = api_url
        self._slip_path = None
        self._thread = None

        self.setWindowTitle("💚 ส่งหลักฐานการสนับสนุน")
        self.setModal(True)
        self.setMinimumWidth(480)
        self.setStyleSheet(self._stylesheet())

        self._build_ui()
        self._on_channel_change()   # init visibility
        self._on_method_change()

    def _stylesheet(self):
        return """
            QDialog { background-color: #0f172a; color: #e2e8f0; }
            QLabel { color: #e2e8f0; }
            QLabel[role="title"] { font-size: 18px; font-weight: 700; color: #10b981; }
            QLabel[role="subtitle"] { color: #94a3b8; font-size: 12px; }
            QLabel[role="section-label"] { color: #f59e0b; font-size: 13px; font-weight: 700; margin-top: 8px; }
            QLabel[role="field-label"] { color: #94a3b8; font-size: 12px; font-weight: 600; }
            QLabel[role="hint"] { color: #64748b; font-size: 11px; }
            QLabel[role="filename"] { color: #10b981; font-size: 12px; font-weight: 600; }
            QLineEdit, QTextEdit, QDoubleSpinBox, QComboBox, QDateEdit, QTimeEdit {
                background-color: #1e293b; border: 1px solid #334155; border-radius: 6px;
                padding: 8px; color: #e2e8f0; font-size: 13px;
            }
            QLineEdit:focus, QTextEdit:focus, QDoubleSpinBox:focus, QComboBox:focus,
            QDateEdit:focus, QTimeEdit:focus { border-color: #7c3aed; }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView { background-color: #1e293b; color: #e2e8f0; selection-background-color: #7c3aed; }
            QPushButton#Primary {
                background-color: #10b981; color: white; font-weight: 700;
                border: none; border-radius: 6px; padding: 12px;
            }
            QPushButton#Primary:hover { background-color: #059669; }
            QPushButton#Primary:disabled { background-color: #334155; color: #64748b; }
            QPushButton#Secondary {
                background-color: #334155; color: #e2e8f0; font-weight: 600;
                border: none; border-radius: 6px; padding: 12px;
            }
            QPushButton#Secondary:hover { background-color: #475569; }
            QPushButton#FileDrop {
                background-color: #1e293b; border: 2px dashed #334155; border-radius: 8px;
                color: #94a3b8; padding: 20px; font-size: 13px; text-align: center;
            }
            QPushButton#FileDrop:hover { border-color: #7c3aed; background-color: #1e1b4b; }
            QRadioButton { color: #e2e8f0; font-size: 13px; padding: 8px; }
            QRadioButton::indicator { width: 16px; height: 16px; }
            QRadioButton::indicator:unchecked { border: 2px solid #475569; border-radius: 9px; background: #1e293b; }
            QRadioButton::indicator:checked { border: 2px solid #7c3aed; border-radius: 9px; background: #7c3aed; }
            QProgressBar {
                background-color: #1e293b; border: 1px solid #334155; border-radius: 4px;
                text-align: center; color: #e2e8f0; height: 6px;
            }
            QProgressBar::chunk { background-color: #10b981; border-radius: 3px; }
        """

    def _make_channel_btn(self, text, obj_name):
        """สร้างปุ่มเลือกช่องทาง (card style)"""
        btn = QRadioButton(text)
        btn.setStyleSheet(f"""
            QRadioButton {{
                background-color: #1e293b; border: 2px solid #334155; border-radius: 8px;
                padding: 14px; font-size: 14px; font-weight: 600;
            }}
            QRadioButton:checked {{ border-color: #7c3aed; background-color: #1e1b4b; }}
            QRadioButton:hover {{ border-color: #6d28d9; }}
        """)
        return btn

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)

        # ── Title ──
        title = QLabel("💚 ส่งหลักฐานการสนับสนุน")
        title.setProperty("role", "title")
        layout.addWidget(title)

        subtitle = QLabel("ขอบคุณที่สนับสนุน Broadcast Playroom — เลือกช่องทางแล้วกรอกข้อมูลด้านล่าง")
        subtitle.setProperty("role", "subtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        # ═══ Section: ช่องทาง ═══
        channel_label = QLabel("สนับสนุนด้วยช่องทางใด?")
        channel_label.setProperty("role", "section-label")
        layout.addWidget(channel_label)

        channel_row = QHBoxLayout()
        channel_row.setSpacing(8)
        self.channel_group = QButtonGroup(self)
        self.rb_bank = self._make_channel_btn("🏦 ธนาคาร", "bank")
        self.rb_tm = self._make_channel_btn("💵 True Money", "truemoney")
        self.channel_group.addButton(self.rb_bank)
        self.channel_group.addButton(self.rb_tm)
        self.rb_bank.setChecked(True)
        self.rb_bank.toggled.connect(self._on_channel_change)
        channel_row.addWidget(self.rb_bank)
        channel_row.addWidget(self.rb_tm)
        layout.addLayout(channel_row)

        # ═══ Section: วิธีแจ้งยอด (เฉพาะธนาคาร) ═══
        self.method_label = QLabel("วิธีแจ้งยอด:")
        self.method_label.setProperty("role", "section-label")
        layout.addWidget(self.method_label)

        method_row = QHBoxLayout()
        method_row.setSpacing(8)
        self.method_group = QButtonGroup(self)
        self.rb_slip = self._make_channel_btn("📷 แนบสลิป", "slip")
        self.rb_manual = self._make_channel_btn("✍️ กรอกข้อมูล", "manual")
        self.method_group.addButton(self.rb_slip)
        self.method_group.addButton(self.rb_manual)
        self.rb_slip.setChecked(True)
        self.rb_slip.toggled.connect(self._on_method_change)
        method_row.addWidget(self.rb_slip)
        method_row.addWidget(self.rb_manual)
        layout.addLayout(method_row)

        # ═══ Slip upload (เฉพาะ bank + slip) ═══
        self.slip_label = QLabel("📷 หลักฐานสลิป")
        self.slip_label.setProperty("role", "field-label")
        layout.addWidget(self.slip_label)

        self.btn_file = QPushButton("📎 คลิกเพื่อเลือกไฟล์รูป...")
        self.btn_file.setObjectName("FileDrop")
        self.btn_file.setCursor(Qt.PointingHandCursor)
        self.btn_file.clicked.connect(self._pick_file)
        layout.addWidget(self.btn_file)

        self.filename_label = QLabel("")
        self.filename_label.setProperty("role", "filename")
        layout.addWidget(self.filename_label)

        self.slip_preview = QLabel()
        self.slip_preview.setAlignment(Qt.AlignCenter)
        self.slip_preview.setMaximumHeight(180)
        layout.addWidget(self.slip_preview)

        self.slip_hint = QLabel("รองรับ PNG/JPG/WebP/GIF · สูงสุด 5MB")
        self.slip_hint.setProperty("role", "hint")
        layout.addWidget(self.slip_hint)

        # ═══ Bank manual (เฉพาะ bank + manual) ═══
        self.bank_label = QLabel("🏦 ธนาคารที่โอน")
        self.bank_label.setProperty("role", "field-label")
        layout.addWidget(self.bank_label)

        self.bank_combo = QComboBox()
        for code, name in BANKS:
            self.bank_combo.addItem(f"{code} — {name}", code)
        layout.addWidget(self.bank_combo)

        # ═══ Date + Time (bank manual + truemoney) ═══
        self.datetime_label = QLabel("🕐 วันที่และเวลาที่โอน")
        self.datetime_label.setProperty("role", "field-label")
        layout.addWidget(self.datetime_label)

        datetime_row = QHBoxLayout()
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        datetime_row.addWidget(self.date_edit, 1)

        self.time_edit = QTimeEdit()
        self.time_edit.setTime(QTime.currentTime())
        self.time_edit.setDisplayFormat("HH:mm")
        datetime_row.addWidget(self.time_edit, 1)
        layout.addLayout(datetime_row)

        # ═══ Amount + Currency (ทุกกรณี) ═══
        amount_label = QLabel("💰 จำนวนเงิน")
        amount_label.setProperty("role", "field-label")
        layout.addWidget(amount_label)

        amount_row = QHBoxLayout()
        self.amount_input = QDoubleSpinBox()
        self.amount_input.setMinimum(1)
        self.amount_input.setMaximum(9999999)
        self.amount_input.setDecimals(2)
        self.amount_input.setValue(100)
        amount_row.addWidget(self.amount_input, 1)

        self.currency_combo = QComboBox()
        for cur in ["THB", "USD", "JPY", "EUR"]:
            self.currency_combo.addItem(cur)
        self.currency_combo.setFixedWidth(80)
        amount_row.addWidget(self.currency_combo)
        layout.addLayout(amount_row)

        # ═══ Name (ทุกกรณี) ═══
        name_label = QLabel("👤 ชื่อที่ต้องการแสดง")
        name_label.setProperty("role", "field-label")
        layout.addWidget(name_label)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("เช่น คุณAAA")
        self.name_input.setMaxLength(50)
        layout.addWidget(self.name_input)

        # ═══ Platform + Channel URL (optional — โปรโมทช่อง) ═══
        platform_label = QLabel("📺 แพลตฟอร์มสตรีม (ไม่บังคับ — ช่วยโปรโมทช่อง)")
        platform_label.setProperty("role", "field-label")
        layout.addWidget(platform_label)

        platform_row = QHBoxLayout()
        self.platform_combo = QComboBox()
        self.platform_combo.addItem("— ไม่ระบุ —", "")
        self.platform_combo.addItem("🟣 Twitch", "twitch")
        self.platform_combo.addItem("🔴 YouTube", "youtube")
        self.platform_combo.addItem("🟢 Kick", "kick")
        self.platform_combo.addItem("🎵 TikTok", "tiktok")
        self.platform_combo.addItem("🔴 MyLive", "mylive")
        platform_row.addWidget(self.platform_combo, 1)

        self.channel_url_input = QLineEdit()
        self.channel_url_input.setPlaceholderText("ลิงก์ช่อง (เช่น https://twitch.tv/yourname)")
        platform_row.addWidget(self.channel_url_input, 2)
        layout.addLayout(platform_row)

        # ═══ Message (ทุกกรณี — optional) ═══
        msg_label = QLabel("💬 ข้อความ (ไม่บังคับ)")
        msg_label.setProperty("role", "field-label")
        layout.addWidget(msg_label)

        self.message_input = QTextEdit()
        self.message_input.setPlaceholderText('สู้ๆครับ / ขอบคุณสำหรับโปรแกรมดีๆ')
        self.message_input.setMaximumHeight(60)
        layout.addWidget(self.message_input)

        # ── Progress ──
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)

        # ── Buttons ──
        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("ยกเลิก")
        btn_cancel.setObjectName("Secondary")
        btn_cancel.clicked.connect(self.reject)
        self.btn_submit = QPushButton("ส่ง ✉️")
        self.btn_submit.setObjectName("Primary")
        self.btn_submit.clicked.connect(self._on_submit)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(self.btn_submit, 1)
        layout.addLayout(btn_row)

        # ── ข้อความเตือน (กันส่งข้อมูลเท็จ) ──
        warning = QLabel(
            "⚠️ หากทำการส่งข้อมูลเท็จเข้ามา ระบบจะทำการแบน "
            "ให้โปรแกรมไม่สามารถใช้งานได้"
        )
        warning.setWordWrap(True)
        warning.setAlignment(Qt.AlignCenter)
        warning.setStyleSheet(
            "font-size: 11px; color: #ef4444; "
            "background: rgba(239, 68, 68, 0.08); "
            "border: 1px solid rgba(239, 68, 68, 0.3); "
            "border-radius: 6px; padding: 8px; margin-top: 8px;"
        )
        layout.addWidget(warning)

    # ═══ Reactive visibility ═══

    def _on_channel_change(self):
        """เมื่อเปลี่ยนช่องทาง → แสดง/ซ่อน fields"""
        is_bank = self.rb_bank.isChecked()

        # ★ method section — เฉพาะธนาคาร
        self.method_label.setVisible(is_bank)
        self.rb_slip.setVisible(is_bank)
        self.rb_manual.setVisible(is_bank)

        if not is_bank:
            # True Money → กรอกข้อมูลอย่างเดียว (ไม่มี slip)
            self._show_slip_fields(False)
            self._show_bank_fields(False)
            self._show_datetime_fields(True)
        else:
            # ธนาคาร → ดู method
            self._on_method_change()

    def _on_method_change(self):
        """เมื่อเปลี่ยนวิธีแจ้งยอด (เฉพาะธนาคาร)"""
        if not self.rb_bank.isChecked():
            return  # True Money ไม่ใช้ method

        is_slip = self.rb_slip.isChecked()
        self._show_slip_fields(is_slip)
        self._show_bank_fields(not is_slip)
        self._show_datetime_fields(not is_slip)  # กรอกข้อมูล → มี date/time

    def _show_slip_fields(self, show):
        for w in [self.slip_label, self.btn_file, self.filename_label, self.slip_preview, self.slip_hint]:
            w.setVisible(show)
        if not show:
            self._slip_path = None
            self.filename_label.setText("")

    def _show_bank_fields(self, show):
        for w in [self.bank_label, self.bank_combo]:
            w.setVisible(show)

    def _show_datetime_fields(self, show):
        for w in [self.datetime_label, self.date_edit, self.time_edit]:
            w.setVisible(show)

    # ═══ File picker ═══

    def _pick_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "เลือกรูปสลิป", "",
            "Images (*.png *.jpg *.jpeg *.webp *.gif);;All Files (*.*)"
        )
        if path:
            self._slip_path = path
            filename = os.path.basename(path)
            size_kb = os.path.getsize(path) / 1024
            self.filename_label.setText(f"✅ {filename} ({size_kb:.0f} KB)")
            self.btn_file.setText("📎 เลือกใหม่...")

            # preview
            pix = QPixmap(path)
            if not pix.isNull():
                self.slip_preview.setPixmap(pix.scaledToHeight(180, Qt.SmoothTransformation))

    # ═══ Submit ═══

    def _build_payload(self):
        """รวบรวมข้อมูลจาก form → payload dict (หรือ None ถ้า invalid)"""
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "ข้อมูลไม่ครบ", "กรุณากรอกชื่อที่ต้องการแสดง")
            return None

        amount = self.amount_input.value()
        currency = self.currency_combo.currentText()
        message = self.message_input.toPlainText().strip()[:200]

        # ★ machine ID (สำหรับระบบแบน)
        try:
            from machine_id import get_machine_id
            machine_id = get_machine_id()
        except Exception:
            machine_id = ""

        payload = {
            'name': name,
            'amount': amount,
            'currency': currency,
            'message': message,
            'machine_id': machine_id,
            'platform': self.platform_combo.currentData() or '',
            'channel_url': self.channel_url_input.text().strip(),
        }

        is_bank = self.rb_bank.isChecked()
        if is_bank:
            payload['channel'] = 'bank'
            is_slip = self.rb_slip.isChecked()
            if is_slip:
                payload['method'] = 'slip'
                if not self._slip_path or not os.path.exists(self._slip_path):
                    QMessageBox.warning(self, "ข้อมูลไม่ครบ", "กรุณาเลือกไฟล์รูปสลิป")
                    return None
                payload['slip_path'] = self._slip_path
            else:
                payload['method'] = 'manual'
                payload['bank'] = self.bank_combo.currentData()
                payload['transfer_date'] = self.date_edit.date().toString("yyyy-MM-dd")
                payload['transfer_time'] = self.time_edit.time().toString("HH:mm")
        else:
            payload['channel'] = 'truemoney'
            payload['transfer_date'] = self.date_edit.date().toString("yyyy-MM-dd")
            payload['transfer_time'] = self.time_edit.time().toString("HH:mm")

        return payload

    def _on_submit(self):
        payload = self._build_payload()
        if payload is None:
            return

        # confirm
        channel_text = "ธนาคาร" if payload['channel'] == 'bank' else "True Money"
        if payload['channel'] == 'bank' and payload.get('method') == 'slip':
            channel_text += " (แนบสลิป)"
        elif payload['channel'] == 'bank':
            channel_text += f" ({payload.get('bank', '?')})"

        reply = QMessageBox.question(
            self, "ยืนยันการส่ง",
            f"ยืนยันส่งข้อมูลการสนับสนุน?\n\n"
            f"ช่องทาง: {channel_text}\n"
            f"จำนวน: {payload['amount']} {payload['currency']}\n"
            f"ชื่อ: {payload['name']}",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if reply != QMessageBox.Yes:
            return

        # disable + show progress
        self.btn_submit.setEnabled(False)
        self.btn_submit.setText("กำลังส่ง...")
        self.progress.setVisible(True)
        self.progress.setValue(0)

        # run in background
        self._thread = _SubmitThread(payload, self._api_url)
        self._thread.progress_sig.connect(self._on_progress)
        self._thread.finished_sig.connect(self._on_finished)
        self._thread.start()

    def _on_progress(self, pct):
        self.progress.setValue(pct)

    def _on_finished(self, result):
        self.btn_submit.setEnabled(True)
        self.btn_submit.setText("ส่ง ✉️")
        self.progress.setVisible(False)

        if result.get("ok"):
            QMessageBox.information(
                self, "✅ ส่งสำเร็จ",
                "ขอบคุณสำหรับการสนับสนุนเรา\n\n"
                "หลังจากตรวจสอบข้อมูลถูกต้องแล้ว\n"
                "ข้อมูลการสนับสนุนของคุณจะขึ้นบนหน้านี้"
            )
            self.accept()
        else:
            QMessageBox.critical(
                self, "❌ ส่งไม่สำเร็จ",
                result.get("error", "เกิดข้อผิดพลาดไม่ทราบสาเหตุ")
            )

    def closeEvent(self, event):
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(3000)
        super().closeEvent(event)
