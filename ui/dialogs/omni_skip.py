"""omni_skip.py — OmniVoice short-word behavior editor

คำเดี่ยวที่ OmniVoice อ่านพัง (เช่น "อ๋อ", "อะ") → ไม่อ่านด้วย OmniVoice เสมอ ไม่มีข้อยกเว้น
(สลับไป Azure หรือลอง OmniVoice พูดซ้ำ+ตัด ตามที่เลือก) — ทดสอบแล้วพบว่าไม่มีคำไหน
"ปลอดภัย 100%" จริง เพราะโมเดลสุ่ม noise เริ่มต้นทุกครั้งที่ generate จึงตัด whitelist ออก
★ ถ้าคำนั้นอยู่ในประโยคยาว → อ่านปกติ (เพราะเงื่อนไข "ไม่มี space")
"""
import logging
import os
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QWidget, QFrame, QLabel, QLineEdit, QVBoxLayout,
    QHBoxLayout, QSpinBox, QCheckBox, QRadioButton, QButtonGroup,
    QPushButton, QSlider, QFileDialog, QMessageBox,
)
from ui.theme import COLOR_CARD, COLOR_BORDER

logger = logging.getLogger("omni_skip")


class OmniSkipDialog(QDialog):
    """OmniVoice Word Skip editor — list คำเดี่ยวที่จะข้าม"""

    settings_changed = Signal()

    def __init__(self, parent_app):
        super().__init__(parent_app if isinstance(parent_app, QWidget) else None)
        self.parent_app = parent_app
        self.settings = getattr(parent_app, 'settings', None)
        self.setWindowTitle("🔊 คำสั้น OmniVoice")
        self.setGeometry(200, 140, 480, 480)
        self.setMinimumSize(380, 360)
        self._build_ui()
        self._load_words()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ★ Header
        header = QFrame()
        header.setFixedHeight(50)
        header.setStyleSheet(f"background-color: {COLOR_CARD}; border-bottom: 1px solid {COLOR_BORDER};")
        hlayout = QHBoxLayout(header)
        hlayout.setContentsMargins(16, 0, 16, 0)
        title = QLabel("✅ คำสั้น OmniVoice")
        title.setStyleSheet("font-size: 17px; font-weight: 700; color: #f59e0b;")
        hlayout.addWidget(title)
        hlayout.addStretch()
        layout.addWidget(header)

        # ★ Toggle on/off — default ON
        #   ★ ก่อนหน้านี้ label บอกว่า "คำสั้นให้ Azure อ่านแทน" ตรงๆ — ทำให้ตัวเลือก
        #   "ให้ OmniVoice อ่านเอง" ที่ซ้อนอยู่ข้างในดูเหมือนเป็น sub-setting ของ Azure
        #   ทั้งที่จริงมันเป็นอีกทางเลือกที่เท่ากัน (peer) → เปลี่ยน label ให้กลาง ไม่เอียงไปทาง
        #   ใดทางหนึ่ง เพราะ toggle นี้คุมแค่ "ตรวจจับคำสั้นไหม" ไม่ได้คุมว่าจะจัดการยังไง
        toggle_row = QHBoxLayout()
        toggle_row.setContentsMargins(16, 12, 16, 4)
        toggle_row.setSpacing(8)
        self.enabled_cb = QCheckBox("เปิดใช้งานระบบจัดการคำสั้น")
        self.enabled_cb.setChecked(True)
        self.enabled_cb.setStyleSheet("color: #d1d5db; font-size: 13px; font-weight: 600;")
        self.enabled_cb.toggled.connect(self._on_enabled_toggled)
        toggle_row.addWidget(self.enabled_cb)
        toggle_row.addStretch()
        layout.addLayout(toggle_row)

        # ★ Min length input — คำเดียวสั้นกว่า X ตัวอักษร → ถือว่าเป็น "คำสั้น"
        self.min_row_widget = QWidget()
        min_row = QHBoxLayout(self.min_row_widget)
        min_row.setContentsMargins(32, 4, 16, 4)
        min_row.setSpacing(8)
        min_label = QLabel("คำสั้นกว่า:")
        min_label.setStyleSheet("color: #d1d5db; font-size: 13px;")
        min_row.addWidget(min_label)
        self.min_length_input = QSpinBox()
        self.min_length_input.setRange(0, 20)
        self.min_length_input.setFixedWidth(100)
        self.min_length_input.setStyleSheet("font-size: 14px;")
        self.min_length_input.setToolTip(
            "ถ้าข้อความเป็นคำเดี่ยว (ไม่มี space) และสั้นกว่าจำนวนนี้ → ถือว่าเป็น \"คำสั้น\"\n"
            "(เลือกวิธีจัดการคำสั้นได้ด้านล่าง) — 0 = ปิด (OmniVoice อ่านทุกคำตรงๆ เสมอ)"
        )
        self.min_length_input.valueChanged.connect(self._on_min_length_changed)
        min_row.addWidget(self.min_length_input)
        min_label2 = QLabel("ตัวอักษร ให้:")
        min_label2.setStyleSheet("color: #9ca3af; font-size: 12px;")
        min_row.addWidget(min_label2)
        min_row.addStretch()
        layout.addWidget(self.min_row_widget)

        # ★ เมื่อเจอคำสั้น จะจัดการยังไง — 2 ตัวเลือกที่เท่ากัน (radio,
        #   ไม่ใช่ checkbox ซ้อน) กันสับสนว่าอันไหนเป็น "หลัก" อันไหนเป็น "sub-setting"
        self.strategy_group = QButtonGroup(self)
        self.retry_row_widget = QWidget()
        retry_row = QVBoxLayout(self.retry_row_widget)
        retry_row.setContentsMargins(32, 0, 16, 4)
        retry_row.setSpacing(4)

        self.strategy_azure_rb = QRadioButton("สลับไปใช้ Azure อ่านแทน (ปลอดภัย — เสียงจะสลับชั่วคราว)")
        self.strategy_azure_rb.setStyleSheet("color: #d1d5db; font-size: 12px;")
        self.strategy_group.addButton(self.strategy_azure_rb)
        retry_row.addWidget(self.strategy_azure_rb)

        self.strategy_retry_rb = QRadioButton("🧪 ทดลอง: ให้ OmniVoice อ่านคำสั้นเอง (พูดซ้ำ + ตัด)")
        self.strategy_retry_rb.setStyleSheet("color: #9ca3af; font-size: 12px;")
        self.strategy_retry_rb.setToolTip(
            "แทนที่จะสลับไป Azure ทันที — ลองให้ OmniVoice พูดคำเดิมซ้ำหลายครั้ง\n"
            "(\"ครับ ครับ ครับ\") แล้วตัดเอาแค่ท่อนสุดท้ายมาเล่น ถ้าตัดพัง (สั้นผิดปกติ)\n"
            "จะ fallback ไป Azure เหมือนเดิมอัตโนมัติ"
        )
        self.strategy_group.addButton(self.strategy_retry_rb)
        retry_row.addWidget(self.strategy_retry_rb)

        self.strategy_azure_rb.toggled.connect(self._on_strategy_changed)
        self.strategy_retry_rb.toggled.connect(self._on_strategy_changed)
        layout.addWidget(self.retry_row_widget)

        # ★ จำนวนครั้งที่พูดซ้ำ (2-5) — ปรับสดได้เลยไม่ต้อง build ใหม่ ช่วยทดลองหาค่าที่พอดี
        #   enable เฉพาะตอนเลือก strategy_retry_rb
        self.repeat_row_widget = QWidget()
        repeat_row = QHBoxLayout(self.repeat_row_widget)
        repeat_row.setContentsMargins(52, 0, 16, 4)
        repeat_row.setSpacing(8)
        repeat_label = QLabel("พูดซ้ำ:")
        repeat_label.setStyleSheet("color: #9ca3af; font-size: 12px;")
        repeat_row.addWidget(repeat_label)
        self.repeat_count_input = QSpinBox()
        self.repeat_count_input.setRange(2, 5)
        self.repeat_count_input.setFixedWidth(70)
        self.repeat_count_input.setStyleSheet("font-size: 13px;")
        self.repeat_count_input.setToolTip(
            "จำนวนครั้งที่พูดคำเดิมซ้ำก่อนตัด — ยิ่งเยอะยิ่งให้โมเดล \"warm up\" นานขึ้น\n"
            "ก่อนพูดคำสุดท้าย (ที่เอามาเล่นจริง) แต่ก็ยิ่งใช้เวลา synth นานขึ้นด้วย"
        )
        self.repeat_count_input.valueChanged.connect(self._on_repeat_count_changed)
        repeat_row.addWidget(self.repeat_count_input)
        repeat_label2 = QLabel("ครั้ง")
        repeat_label2.setStyleSheet("color: #9ca3af; font-size: 12px;")
        repeat_row.addWidget(repeat_label2)
        repeat_row.addStretch()
        layout.addWidget(self.repeat_row_widget)

        # ★ ช่องทดลองพิมพ์ — นับตัวอักษรจริง + บอกว่าจะใช้ engine ไหน
        test_row = QHBoxLayout()
        test_row.setContentsMargins(32, 4, 16, 4)
        test_row.setSpacing(8)
        test_label = QLabel("🔍 ทดลอง:")
        test_label.setStyleSheet("color: #9ca3af; font-size: 12px;")
        test_row.addWidget(test_label)
        self.test_input = QLineEdit()
        self.test_input.setPlaceholderText("พิมพ์คำเพื่อนับตัวอักษร...")
        self.test_input.setStyleSheet("font-size: 13px;")
        self.test_input.textChanged.connect(self._on_test_input_changed)
        test_row.addWidget(self.test_input)
        self.test_result = QLabel("")
        self.test_result.setStyleSheet("font-size: 12px; font-weight: 600;")
        test_row.addWidget(self.test_result)
        layout.addLayout(test_row)

        # ★ Note — อธิบายพฤติกรรมตอนนี้ (ไม่มี whitelist แล้ว คำสั้นทุกคำโดนกฎเดียวกันหมด)
        note = QLabel(
            "คำเดี่ยวที่สั้นกว่าเกณฑ์ด้านบน จะใช้วิธีที่เลือกไว้เสมอ ไม่มีข้อยกเว้นรายคำ\n"
            "ถ้าคำอยู่ในประโยคยาว เช่น \"อ๋อ แบบนี้\" จะใช้ OmniVoice อ่านเสมอ"
        )
        note.setStyleSheet("color: #9ca3af; font-size: 12px; padding: 8px 32px 12px;")
        note.setWordWrap(True)
        layout.addWidget(note)

        # ★ Separator
        sep2 = QFrame()
        sep2.setFixedHeight(1)
        sep2.setStyleSheet(f"background-color: {COLOR_BORDER}; margin: 4px 16px;")
        layout.addWidget(sep2)

        # ★ เสียงแจ้งเตือนตอนข้ามข้อความ (เช่น OmniVoice generate เสียงเงียบผิดปกติ)
        notif_title = QLabel("🔔 เสียงแจ้งเตือนเมื่อข้ามข้อความ")
        notif_title.setStyleSheet("color: #d1d5db; font-size: 13px; font-weight: 600; padding: 8px 16px 2px;")
        layout.addWidget(notif_title)

        notif_desc = QLabel(
            "เล่นเสียงสั้นๆ แทนตอนที่ OmniVoice สร้างเสียงผิดปกติ (เงียบ) — ใช้เสียง\n"
            "ค่าเริ่มต้น (ติ๊งสั้นๆ เบาๆ) หรือเปลี่ยนเป็นไฟล์ของตัวเองก็ได้"
        )
        notif_desc.setStyleSheet("color: #9ca3af; font-size: 12px; padding: 0 16px 8px;")
        notif_desc.setWordWrap(True)
        layout.addWidget(notif_desc)

        path_row = QHBoxLayout()
        path_row.setContentsMargins(16, 0, 16, 4)
        path_row.setSpacing(8)
        self.sound_path_label = QLabel("ค่าเริ่มต้น")
        self.sound_path_label.setStyleSheet("color: #d1d5db; font-size: 12px;")
        self.sound_path_label.setWordWrap(True)
        path_row.addWidget(self.sound_path_label, 1)
        self.btn_browse_sound = QPushButton("📁 เลือกไฟล์")
        self.btn_browse_sound.clicked.connect(self._browse_notify_sound)
        path_row.addWidget(self.btn_browse_sound)
        self.btn_reset_sound = QPushButton("↺ ค่าเริ่มต้น")
        self.btn_reset_sound.clicked.connect(self._reset_notify_sound)
        path_row.addWidget(self.btn_reset_sound)
        self.btn_test_sound = QPushButton("🔊 ทดสอบ")
        self.btn_test_sound.clicked.connect(self._test_notify_sound)
        path_row.addWidget(self.btn_test_sound)
        layout.addLayout(path_row)

        vol_row = QHBoxLayout()
        vol_row.setContentsMargins(16, 0, 16, 12)
        vol_row.setSpacing(8)
        vol_label = QLabel("ระดับเสียง:")
        vol_label.setStyleSheet("color: #d1d5db; font-size: 12px;")
        vol_row.addWidget(vol_label)
        self.sound_volume_slider = QSlider(Qt.Horizontal)
        self.sound_volume_slider.setRange(0, 100)
        self.sound_volume_slider.valueChanged.connect(self._on_sound_volume_changed)
        vol_row.addWidget(self.sound_volume_slider, 1)
        self.sound_volume_label = QLabel("60%")
        self.sound_volume_label.setStyleSheet("color: #9ca3af; font-size: 12px;")
        self.sound_volume_label.setFixedWidth(40)
        vol_row.addWidget(self.sound_volume_label)
        layout.addLayout(vol_row)

        layout.addStretch(1)

    def _load_words(self):
        """โหลด min_length + enabled + strategy จาก settings"""
        if not self.settings:
            return
        # ★ load enabled toggle
        enabled = getattr(self.settings, 'omnivoice_skip_enabled', True)
        self.enabled_cb.blockSignals(True)
        self.enabled_cb.setChecked(bool(enabled))
        self.enabled_cb.blockSignals(False)
        # ★ load min_length
        min_len = getattr(self.settings, 'omnivoice_skip_min_length', 6)
        self.min_length_input.blockSignals(True)
        self.min_length_input.setValue(int(min_len))
        self.min_length_input.blockSignals(False)
        # ★ load strategy radio (experimental) — retry_on=True → retry rb, else → azure rb
        retry_on = getattr(self.settings, 'omnivoice_short_word_retry', False)
        self.strategy_azure_rb.blockSignals(True)
        self.strategy_retry_rb.blockSignals(True)
        self.strategy_retry_rb.setChecked(bool(retry_on))
        self.strategy_azure_rb.setChecked(not retry_on)
        self.strategy_azure_rb.blockSignals(False)
        self.strategy_retry_rb.blockSignals(False)
        # ★ load repeat count (experimental)
        repeat_n = getattr(self.settings, 'omnivoice_short_word_repeat', 3)
        self.repeat_count_input.blockSignals(True)
        self.repeat_count_input.setValue(int(repeat_n))
        self.repeat_count_input.blockSignals(False)
        self.repeat_row_widget.setEnabled(bool(retry_on))
        # ★ load notification sound path + volume
        sound_path = getattr(self.settings, 'warn_sound_path', '') or ''
        self.sound_path_label.setText(os.path.basename(sound_path) if sound_path else "ค่าเริ่มต้น")
        self.sound_path_label.setToolTip(sound_path or "")
        volume = getattr(self.settings, 'warn_sound_volume', 0.6)
        vol_pct = int(round(float(volume) * 100))
        self.sound_volume_slider.blockSignals(True)
        self.sound_volume_slider.setValue(vol_pct)
        self.sound_volume_slider.blockSignals(False)
        self.sound_volume_label.setText(f"{vol_pct}%")

    def _on_enabled_toggled(self, checked):
        """toggle on/off → save + ซ่อน/แสดง content"""
        if self.settings:
            self.settings.omnivoice_skip_enabled = bool(checked)
            try:
                from settings import save_settings
                save_settings(self.settings)
            except Exception:
                pass
            if hasattr(self.parent_app, 'pipeline') and self.parent_app.pipeline:
                self.parent_app.pipeline.config.omnivoice_skip_enabled = bool(checked)
        self._update_content_visibility(bool(checked))
        self.settings_changed.emit()

    def _update_content_visibility(self, visible):
        """ซ่อน/แสดง min_length + strategy section ตาม toggle"""
        self.min_row_widget.setVisible(visible)
        self.retry_row_widget.setVisible(visible)
        self.repeat_row_widget.setVisible(visible)

    def _on_strategy_changed(self, _checked):
        """เลือกวิธีจัดการคำสั้น (Azure / OmniVoice พูดซ้ำ+ตัด) → save + sync pipeline สด

        ★ ต่อกับ toggled ของ radio ทั้งคู่ — ไฟร์ 2 ครั้งต่อคลิก (ตัวที่ถูกยกเลิก + ตัวที่ถูก
        เลือก) จึงอ่านสถานะสุดท้ายจาก strategy_retry_rb.isChecked() ตรงๆ แทนใช้ค่า param
        (idempotent — ไฟร์ซ้ำด้วยผลลัพธ์เดิมไม่มีผลเสีย)
        """
        retry_on = self.strategy_retry_rb.isChecked()
        # ★ อัปเดต test result ด้วย (ผลลัพธ์ที่โชว์อาจเปลี่ยน)
        self._on_test_input_changed(self.test_input.text())
        self.repeat_row_widget.setEnabled(retry_on)
        if not self.settings:
            return
        self.settings.omnivoice_short_word_retry = retry_on
        try:
            from settings import save_settings
            save_settings(self.settings)
        except Exception:
            pass
        if hasattr(self.parent_app, 'pipeline') and self.parent_app.pipeline:
            self.parent_app.pipeline.config.omnivoice_short_word_retry = retry_on
        self.settings_changed.emit()

    def _on_repeat_count_changed(self, value):
        """จำนวนครั้งพูดซ้ำเปลี่ยน → save + sync pipeline สด (ไม่ต้อง build ใหม่)"""
        if not self.settings:
            return
        self.settings.omnivoice_short_word_repeat = int(value)
        try:
            from settings import save_settings
            save_settings(self.settings)
        except Exception:
            pass
        if hasattr(self.parent_app, 'pipeline') and self.parent_app.pipeline:
            self.parent_app.pipeline.config.omnivoice_short_word_repeat = int(value)
        self.settings_changed.emit()

    def _on_min_length_changed(self, value):
        """min_length เปลี่ยน → save + อัปเดต test result"""
        # ★ อัปเดต test result ด้วย (เพราะ min_length เปลี่ยน ผลอาจเปลี่ยน)
        self._on_test_input_changed(self.test_input.text())
        if not self.settings:
            return
        self.settings.omnivoice_skip_min_length = int(value)
        try:
            from settings import save_settings
            save_settings(self.settings)
        except Exception:
            pass
        if hasattr(self.parent_app, 'pipeline') and self.parent_app.pipeline:
            self.parent_app.pipeline.config.omnivoice_skip_min_length = int(value)
        self.settings_changed.emit()

    def _on_test_input_changed(self, text):
        """อัปเดตผลลัพธ์นับตัวอักษร + บอกว่าจะใช้ engine ไหน"""
        text = (text or "").strip()
        if not text:
            self.test_result.setText("")
            self.test_result.setStyleSheet("font-size: 12px; font-weight: 600; color: #9ca3af;")
            return
        length = len(text)
        min_len = self.min_length_input.value()
        has_space = " " in text
        if has_space:
            # ประโยคยาว → OmniVoice
            self.test_result.setText(f"{length} ตัว → 🎤 OmniVoice (ประโยคยาว)")
            self.test_result.setStyleSheet("font-size: 12px; font-weight: 600; color: #10b981;")
        elif length < min_len and min_len > 0:
            if self.strategy_retry_rb.isChecked():
                self.test_result.setText(f"{length} ตัว → 🧪 OmniVoice พูดซ้ำ+ตัด (สั้นกว่า {min_len})")
                self.test_result.setStyleSheet("font-size: 12px; font-weight: 600; color: #a78bfa;")
            else:
                self.test_result.setText(f"{length} ตัว → 🔵 Azure (สั้นกว่า {min_len})")
                self.test_result.setStyleSheet("font-size: 12px; font-weight: 600; color: #f59e0b;")
        else:
            self.test_result.setText(f"{length} ตัว → 🎤 OmniVoice (≥ {min_len})")
            self.test_result.setStyleSheet("font-size: 12px; font-weight: 600; color: #10b981;")

    def _browse_notify_sound(self):
        """เลือกไฟล์เสียงแจ้งเตือนเอง — รองรับทุกฟอร์แมตที่ ffmpeg อ่านได้ (wav/mp3/m4a/ogg/...)

        ★ soundfile (ตัวเล่นเสียงจริง) ไม่รองรับ m4a/AAC โดยตรง → แปลงเป็น .wav
        ด้วย ffmpeg ที่ bundle มากับโปรแกรมก่อนเสมอ กันปัญหาเล่นไม่ได้แบบเงียบๆ
        """
        path, _ = QFileDialog.getOpenFileName(
            self, "เลือกไฟล์เสียงแจ้งเตือน", "",
            "Audio Files (*.wav *.mp3 *.m4a *.ogg *.flac *.aac);;All Files (*)"
        )
        if not path:
            return
        try:
            import subprocess
            from chat_queue import ChatPipeline
            from data_dir import get_data_dir

            out_path = os.path.join(get_data_dir(), "_custom_skip_notify.wav")
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            ffmpeg = ChatPipeline._ffmpeg_path()
            no_window = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
            subprocess.run(
                [ffmpeg, "-y", "-i", path, "-ar", "44100", "-ac", "1", "-t", "5", out_path],
                check=True, capture_output=True, timeout=15, creationflags=no_window,
            )
            self._save_notify_sound_path(out_path)
        except Exception as e:
            logger.error(f"convert notify sound failed: {e}")
            QMessageBox.warning(self, "แปลงไฟล์เสียงไม่สำเร็จ", f"เลือกไฟล์นี้ไม่ได้: {e}")

    def _reset_notify_sound(self):
        """กลับไปใช้เสียง default"""
        self._save_notify_sound_path("")

    def _save_notify_sound_path(self, path):
        self.sound_path_label.setText(os.path.basename(path) if path else "ค่าเริ่มต้น")
        self.sound_path_label.setToolTip(path or "")
        if not self.settings:
            return
        self.settings.warn_sound_path = path
        try:
            from settings import save_settings
            save_settings(self.settings)
        except Exception:
            pass
        if hasattr(self.parent_app, 'pipeline') and self.parent_app.pipeline:
            self.parent_app.pipeline.config.warn_sound_path = path
        self.settings_changed.emit()

    def _on_sound_volume_changed(self, value):
        """ระดับเสียงแจ้งเตือนเปลี่ยน → save + sync pipeline สด"""
        self.sound_volume_label.setText(f"{value}%")
        if not self.settings:
            return
        volume = value / 100.0
        self.settings.warn_sound_volume = volume
        try:
            from settings import save_settings
            save_settings(self.settings)
        except Exception:
            pass
        if hasattr(self.parent_app, 'pipeline') and self.parent_app.pipeline:
            self.parent_app.pipeline.config.warn_sound_volume = volume
        self.settings_changed.emit()

    def _test_notify_sound(self):
        """เล่นเสียงแจ้งเตือนปัจจุบัน (default หรือไฟล์ที่เลือกไว้) ให้ฟัง"""
        try:
            path = getattr(self.settings, 'warn_sound_path', '') or ''
            if not path:
                from chat_queue import get_default_notify_sound_path
                path = get_default_notify_sound_path()
            volume = getattr(self.settings, 'warn_sound_volume', 0.6)
            if hasattr(self.parent_app, 'pipeline') and self.parent_app.pipeline:
                self.parent_app.pipeline._play_notification_sound(path, float(volume))
        except Exception as e:
            logger.error(f"test notify sound failed: {e}")
