"""omni_skip.py — OmniVoice Word Skip editor

คำเดี่ยวที่ OmniVoice อ่านพัง (เช่น "อ๋อ", "อะ") → ไม่อ่าน
★ ถ้าคำนั้นอยู่ในประโยคยาว → อ่านปกติ (เพราะเงื่อนไข "ไม่มี space")
"""
import logging
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QWidget, QFrame, QLabel, QPushButton, QLineEdit, QVBoxLayout,
    QHBoxLayout, QScrollArea, QListWidget, QListWidgetItem, QMessageBox,
    QInputDialog, QSpinBox, QCheckBox,
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
        toggle_row = QHBoxLayout()
        toggle_row.setContentsMargins(16, 12, 16, 4)
        toggle_row.setSpacing(8)
        self.enabled_cb = QCheckBox("เปิดใช้งาน — คำสั้นให้ Azure อ่านแทน")
        self.enabled_cb.setChecked(True)
        self.enabled_cb.setStyleSheet("color: #d1d5db; font-size: 13px; font-weight: 600;")
        self.enabled_cb.toggled.connect(self._on_enabled_toggled)
        toggle_row.addWidget(self.enabled_cb)
        toggle_row.addStretch()
        layout.addLayout(toggle_row)

        # ★ Min length input — คำเดียวสั้นกว่า X ตัวอักษร → Azure อ่านแทน
        self.min_row_widget = QWidget()
        min_row = QHBoxLayout(self.min_row_widget)
        min_row.setContentsMargins(32, 4, 16, 4)
        min_row.setSpacing(8)
        min_label = QLabel("ต่ำกว่า:")
        min_label.setStyleSheet("color: #d1d5db; font-size: 13px;")
        min_row.addWidget(min_label)
        self.min_length_input = QSpinBox()
        self.min_length_input.setRange(0, 20)
        self.min_length_input.setFixedWidth(100)
        self.min_length_input.setStyleSheet("font-size: 14px;")
        self.min_length_input.setToolTip(
            "ถ้าข้อความเป็นคำเดี่ยว (ไม่มี space) และสั้นกว่าจำนวนนี้\n"
            "→ สลับไปใช้ Azure อ่านแทน OmniVoice (เพราะ OmniVoice อ่านคำสั้นไม่ค่อยดี)\n"
            "เช่น ตั้ง 4 → \"อะ\" (2 ตัว) Azure อ่าน, \"โอเค\" (4 ตัว) OmniVoice อ่าน\n"
            "0 = ปิด (OmniVoice อ่านทุกคำ)"
        )
        self.min_length_input.valueChanged.connect(self._on_min_length_changed)
        min_row.addWidget(self.min_length_input)
        min_label2 = QLabel("ตัวอักษร")
        min_label2.setStyleSheet("color: #9ca3af; font-size: 12px;")
        min_row.addWidget(min_label2)
        min_row.addStretch()
        layout.addWidget(self.min_row_widget)

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

        # ★ Container ที่จะซ่อนเมื่อ toggle off (sep + desc + list + buttons)
        self.content_container = QWidget()
        content_layout = QVBoxLayout(self.content_container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # ★ Separator
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background-color: {COLOR_BORDER}; margin: 4px 16px;")
        content_layout.addWidget(sep)

        # ★ Description for whitelist
        desc = QLabel(
            "✅ whitelist — คำสั้นที่ OmniVoice อ่านได้ (ไม่ต้องส่งให้ Azure)\n"
            "เช่น \"ได้\" \"มี\" \"ไป\" — สั้นแต่ OmniVoice อ่านเป็น\n"
            "ถ้าคำอยู่ในประโยคยาว เช่น \"อ๋อ แบบนี้\" จะใช้ OmniVoice อ่านเสมอ"
        )
        desc.setStyleSheet("color: #9ca3af; font-size: 12px; padding: 8px 16px 4px;")
        desc.setWordWrap(True)
        content_layout.addWidget(desc)

        # ★ Word list (scrollable)
        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(f"""
            QListWidget {{
                background-color: {COLOR_CARD};
                border: 1px solid {COLOR_BORDER};
                border-radius: 6px;
                padding: 4px;
            }}
            QListWidget::item {{
                padding: 8px 12px;
                border-bottom: 1px solid {COLOR_BORDER};
            }}
            QListWidget::item:selected {{
                background-color: rgba(245, 158, 11, 0.15);
            }}
        """)
        content_layout.addWidget(self.list_widget, 1)

        # ★ Action buttons
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(16, 12, 16, 16)
        btn_row.setSpacing(8)
        self.btn_add = QPushButton("➕ เพิ่มคำ")
        self.btn_add.setObjectName("Primary")
        self.btn_add.clicked.connect(self._add_word)
        btn_row.addWidget(self.btn_add)
        self.btn_remove = QPushButton("🗑 ลบที่เลือก")
        self.btn_remove.clicked.connect(self._remove_selected)
        btn_row.addWidget(self.btn_remove)
        btn_row.addStretch()
        self.btn_clear = QPushButton("ล้างทั้งหมด")
        self.btn_clear.clicked.connect(self._clear_all)
        btn_row.addWidget(self.btn_clear)
        content_layout.addLayout(btn_row)

        layout.addWidget(self.content_container, 1)
        # ★ spacer ด้านล่าง — กัน content กระโดดตอน toggle (รักษา layout คงที่)
        layout.addStretch(0)

    def _load_words(self):
        """โหลด whitelist + min_length + enabled จาก settings"""
        self.list_widget.clear()
        if not self.settings:
            return
        # ★ load enabled toggle
        enabled = getattr(self.settings, 'omnivoice_skip_enabled', True)
        self.enabled_cb.blockSignals(True)
        self.enabled_cb.setChecked(bool(enabled))
        self.enabled_cb.blockSignals(False)
        # ★ load min_length
        min_len = getattr(self.settings, 'omnivoice_skip_min_length', 3)
        self.min_length_input.blockSignals(True)
        self.min_length_input.setValue(int(min_len))
        self.min_length_input.blockSignals(False)
        # ★ load whitelist
        words = getattr(self.settings, 'omnivoice_short_whitelist', [])
        for word in words:
            item = QListWidgetItem(word)
            self.list_widget.addItem(item)

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
        """ซ่อน/แสดง min_length + whitelist section ตาม toggle"""
        self.min_row_widget.setVisible(visible)
        self.content_container.setVisible(visible)

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
        whitelist = [w.lower() for w in self._get_whitelist()]
        has_space = " " in text
        if has_space:
            # ประโยคยาว → OmniVoice
            self.test_result.setText(f"{length} ตัว → 🎤 OmniVoice (ประโยคยาว)")
            self.test_result.setStyleSheet("font-size: 12px; font-weight: 600; color: #10b981;")
        elif length < min_len and min_len > 0:
            if text.lower() in whitelist:
                self.test_result.setText(f"{length} ตัว → 🎤 OmniVoice (whitelist)")
                self.test_result.setStyleSheet("font-size: 12px; font-weight: 600; color: #10b981;")
            else:
                self.test_result.setText(f"{length} ตัว → 🔵 Azure (สั้นกว่า {min_len})")
                self.test_result.setStyleSheet("font-size: 12px; font-weight: 600; color: #f59e0b;")
        else:
            self.test_result.setText(f"{length} ตัว → 🎤 OmniVoice (≥ {min_len})")
            self.test_result.setStyleSheet("font-size: 12px; font-weight: 600; color: #10b981;")

    def _get_whitelist(self):
        """อ่าน whitelist จาก list widget"""
        return [self.list_widget.item(i).text().strip()
                for i in range(self.list_widget.count())
                if self.list_widget.item(i).text().strip()]

    def _add_word(self):
        """เพิ่มคำใหม่ (input dialog)"""
        text, ok = QInputDialog.getText(
            self, "เพิ่มคำ", "คำที่จะข้าม:",
            QLineEdit.Normal, ""
        )
        if ok and text.strip():
            word = text.strip()
            # ★ เช็คว่ามีอยู่แล้วไหม (case-insensitive)
            existing = [self.list_widget.item(i).text().lower() for i in range(self.list_widget.count())]
            if word.lower() in existing:
                QMessageBox.information(self, "ซ้ำ", f"มีคำ \"{word}\" อยู่แล้ว")
                return
            # ★ เตือนถ้ามี space (จะไม่ทำงาน)
            if " " in word:
                reply = QMessageBox.question(
                    self, "คำนี้มีช่องว่าง",
                    f"\"{word}\" มี space → จะไม่ถูกข้ามเพราะเงื่อนไขต้องเป็นคำเดี่ยว\nต้องการเพิ่มอยู่ไหม?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                )
                if reply != QMessageBox.Yes:
                    return
            self.list_widget.addItem(QListWidgetItem(word))
            self._save()

    def _remove_selected(self):
        """ลบคำที่เลือก"""
        items = self.list_widget.selectedItems()
        if not items:
            return
        for item in items:
            self.list_widget.takeItem(self.list_widget.row(item))
        self._save()

    def _clear_all(self):
        """ล้างทั้งหมด"""
        if self.list_widget.count() == 0:
            return
        reply = QMessageBox.question(
            self, "ล้างทั้งหมด",
            f"ต้องการลบคำทั้งหมด {self.list_widget.count()} คำใช่ไหม?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.list_widget.clear()
            self._save()

    def _save(self):
        """บันทึก whitelist กลับ settings"""
        if not self.settings:
            return
        words = [self.list_widget.item(i).text().strip()
                 for i in range(self.list_widget.count())
                 if self.list_widget.item(i).text().strip()]
        self.settings.omnivoice_short_whitelist = words
        try:
            from settings import save_settings
            save_settings(self.settings)
        except Exception as e:
            logger.error(f"save omni_skip failed: {e}")
        # ★ sync pipeline config
        if hasattr(self.parent_app, 'pipeline') and self.parent_app.pipeline:
            self.parent_app.pipeline.config.omnivoice_short_whitelist = words
        self.settings_changed.emit()
