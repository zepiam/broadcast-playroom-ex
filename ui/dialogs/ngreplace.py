"""ngreplace.py — NG-Replace editor dialog (คำต้องห้าม + คำแทนที่)

รองรับ 3-field: คำเดิม / คำที่แสดง / คำที่อ่าน TTS
+ ปุ่ม "โหลดจากคลัง" (ดาวน์โหลด dictionary จากเว็บชุมชน)
"""
import logging
import threading
import json as _json
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QDialog, QWidget, QFrame, QLabel, QPushButton, QLineEdit, QVBoxLayout,
    QHBoxLayout, QScrollArea, QListWidget, QListWidgetItem, QMessageBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QInputDialog,
)

logger = logging.getLogger("ngreplace")

DICT_URL = "https://men9ch.com/wiki/ng-replace.php?pid=broadcast-playroom&download=1"


class NGReplaceDialog(QDialog):
    """NG-Replace editor — 3-field dictionary (source / display / read)"""

    def __init__(self, parent_app):
        super().__init__(parent_app if isinstance(parent_app, QWidget) else None)
        self.parent_app = parent_app
        self.settings = getattr(parent_app, 'settings', None)
        self.setWindowTitle("🚫 NG-Replace")
        self.setGeometry(180, 120, 720, 560)
        self.setMinimumSize(600, 400)
        self._build_ui()
        self._load_words()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ★ Header
        header = QFrame()
        header.setFixedHeight(50)
        header.setStyleSheet("background-color: #131726; border-bottom: 1px solid #2a2f45;")
        hlayout = QHBoxLayout(header)
        hlayout.setContentsMargins(16, 0, 16, 0)
        title = QLabel("🚫 NG-Replace — คำต้องห้าม + คำแทนที่")
        title.setStyleSheet("font-size: 15px; font-weight: 700; color: #f59e0b;")
        hlayout.addWidget(title)
        hlayout.addStretch()
        # ★ ปุ่มโหลดจากคลัง
        btn_download = QPushButton("⬇️ โหลดจากคลัง")
        btn_download.clicked.connect(self._download_from_wiki)
        hlayout.addWidget(btn_download)
        # ★ ปุ่มเพิ่มคำศัพท์
        btn_add = QPushButton("➕ เพิ่มคำศัพท์")
        btn_add.setObjectName("Primary")
        btn_add.clicked.connect(self._add_word_dialog)
        hlayout.addWidget(btn_add)
        layout.addWidget(header)

        # ★ Table (3 columns: source+🔊 / display / read+🔊)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["คำเดิม", "คำที่แสดง", "คำที่อ่าน TTS"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        # ★ แถวสูงพอให้พิมพ์เห็นชัด
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.verticalHeader().setMinimumSectionSize(36)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: transparent;
                border: none;
                gridline-color: #2a2f45;
            }
            QTableWidget::item {
                padding: 4px;
            }
            QHeaderView::section {
                background-color: #131726;
                color: #9ca3af;
                padding: 8px;
                border: none;
                border-bottom: 1px solid #2a2f45;
                font-weight: 600;
            }
        """)
        layout.addWidget(self.table, 1)

        # ★ Bottom bar
        bottom = QFrame()
        bottom.setFixedHeight(50)
        bottom.setStyleSheet("background-color: #131726; border-top: 1px solid #2a2f45;")
        bottom_layout = QHBoxLayout(bottom)
        bottom_layout.setContentsMargins(16, 0, 16, 0)
        self.count_label = QLabel("0 คำ")
        self.count_label.setStyleSheet("color: #9ca3af;")
        bottom_layout.addWidget(self.count_label)
        bottom_layout.addStretch()
        btn_delete = QPushButton("🗑 ลบที่เลือก")
        btn_delete.setObjectName("Danger")
        btn_delete.clicked.connect(self._delete_selected)
        bottom_layout.addWidget(btn_delete)
        btn_save = QPushButton("💾 บันทึก")
        btn_save.setObjectName("Primary")
        btn_save.setFixedWidth(100)
        btn_save.clicked.connect(self._save)
        btn_close = QPushButton("ปิด")
        btn_close.setFixedWidth(80)
        btn_close.clicked.connect(self.reject)
        bottom_layout.addWidget(btn_save)
        bottom_layout.addWidget(btn_close)
        layout.addWidget(bottom)

    def _load_words(self):
        """โหลดคำจาก settings.replace_words"""
        if not self.settings:
            return
        words = getattr(self.settings, 'replace_words', {}) or {}
        self.table.setRowCount(0)
        for src, fields in sorted(words.items()):
            self._add_row_data(src, fields.get('display', ''), fields.get('read', ''))
        self._update_count()

    def _add_row_data(self, src='', display='', read=''):
        """เพิ่ม row — text editable + 🔊 icon ชิดขวาใน container widget"""
        from PySide6.QtWidgets import QHBoxLayout, QWidget, QLineEdit
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setRowHeight(row, 40)

        # ★ column 0: source text + TTS button (in container)
        w0 = QWidget()
        l0 = QHBoxLayout(w0)
        l0.setContentsMargins(4, 2, 4, 2)
        l0.setSpacing(4)
        edit0 = QLineEdit(src)
        edit0.setStyleSheet("border: none; background: transparent; color: #e5e7eb; padding: 0px;")
        l0.addWidget(edit0)
        if src:
            btn0 = QPushButton("🔊")
            btn0.setFixedSize(28, 28)
            btn0.setToolTip("ฟังคำเดิม")
            btn0.setStyleSheet("border: 1px solid #2a2f45; border-radius: 4px; background: #1a1f33; font-size: 14px; color: #06b6d4;")
            btn0.setCursor(Qt.PointingHandCursor)
            btn0.clicked.connect(lambda _, t=src, b=btn0: self._preview_tts_with_loading(b, t))
            l0.addWidget(btn0)
        self.table.setCellWidget(row, 0, w0)
        w0._edit = edit0

        # ★ column 1: display (editable)
        w1 = QWidget()
        l1 = QHBoxLayout(w1)
        l1.setContentsMargins(4, 2, 4, 2)
        edit1 = QLineEdit(display)
        edit1.setStyleSheet("border: none; background: transparent; color: #e5e7eb; padding: 0px;")
        l1.addWidget(edit1)
        self.table.setCellWidget(row, 1, w1)
        w1._edit = edit1

        # ★ column 2: read text + TTS button
        w2 = QWidget()
        l2 = QHBoxLayout(w2)
        l2.setContentsMargins(4, 2, 4, 2)
        l2.setSpacing(4)
        edit2 = QLineEdit(read)
        edit2.setStyleSheet("border: none; background: transparent; color: #e5e7eb; padding: 0px;")
        l2.addWidget(edit2)
        if read:
            btn2 = QPushButton("🔊")
            btn2.setFixedSize(28, 28)
            btn2.setToolTip("ฟังคำที่อ่าน")
            btn2.setStyleSheet("border: 1px solid #2a2f45; border-radius: 4px; background: #1a1f33; font-size: 14px; color: #06b6d4;")
            btn2.setCursor(Qt.PointingHandCursor)
            btn2.clicked.connect(lambda _, t=read, b=btn2: self._preview_tts_with_loading(b, t))
            l2.addWidget(btn2)
        self.table.setCellWidget(row, 2, w2)
        w2._edit = edit2

    def _preview_tts_with_loading(self, btn, text):
        """preview TTS with loading indicator (กันกดรัว)"""
        if not text.strip():
            return
        if btn.text() == "⏳":
            return  # กำลังโหลดอยู่ → ไม่ทำซ้ำ
        btn.setText("⏳")
        btn.setEnabled(False)
        # ★ enqueue
        self._preview_tts_text(text)
        # ★ reset หลัง 3 วิ (TTS น่าจะเล่นจบแล้ว)
        QTimer.singleShot(3000, lambda: (btn.setText("🔊"), btn.setEnabled(True)))

    def _preview_tts_text(self, text):
        """เล่นเสียง TTS ของ text"""
        if not text.strip():
            return
        if self.parent_app and hasattr(self.parent_app, 'pipeline') and self.parent_app.pipeline:
            try:
                from chat_twitch import ChatMessage
                msg = ChatMessage(platform='test', author='ทดสอบ', text=text)
                self.parent_app.pipeline.enqueue(msg)
            except Exception as e:
                logger.error(f"TTS preview failed: {e}")

    def _add_row(self):
        """เพิ่มแถวว่าง"""
        self._add_row_data('', '', '')
        self._update_count()

    def _add_word_dialog(self):
        """เปิด dialog เพิ่มคำศัพท์ใหม่ (3 ช่อง)"""
        dlg = QDialog(self)
        dlg.setWindowTitle("➕ เพิ่มคำศัพท์")
        dlg.setMinimumWidth(400)
        layout = QVBoxLayout(dlg)
        layout.setSpacing(8)
        # ★ fields
        src_entry = QLineEdit()
        src_entry.setPlaceholderText("คำเดิม (ที่จะค้นหา)")
        layout.addWidget(QLabel("คำเดิม:"))
        layout.addWidget(src_entry)
        display_entry = QLineEdit()
        display_entry.setPlaceholderText("คำที่แสดงในแชท (ว่าง = ซ่อน)")
        layout.addWidget(QLabel("คำที่แสดง:"))
        layout.addWidget(display_entry)
        read_entry = QLineEdit()
        read_entry.setPlaceholderText("คำที่อ่าน TTS (ว่าง = ไม่อ่านส่วนนี้)")
        layout.addWidget(QLabel("คำที่อ่าน TTS:"))
        layout.addWidget(read_entry)
        # ★ buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_ok = QPushButton("เพิ่ม")
        btn_ok.setObjectName("Primary")
        btn_cancel = QPushButton("ยกเลิก")
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)
        btn_ok.clicked.connect(dlg.accept)
        btn_cancel.clicked.connect(dlg.reject)
        if dlg.exec():
            src = src_entry.text().strip()
            if src:
                self._add_row_data(src, display_entry.text().strip(), read_entry.text().strip())
                self._update_count()

    def _download_from_wiki(self):
        """ดาวน์โหลด dictionary จากเว็บชุมชน + import"""
        reply = QMessageBox.question(
            self, "⬇️ โหลดจากคลัง",
            "จะดาวน์โหลด dictionary จากเว็บชุมชนและนำเข้าโปรแกรม\n\n"
            "คำใหม่จะเพิ่มเข้าไป (คำซ้ำจะข้าม)\n\nดำเนินการต่อ?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if reply != QMessageBox.Yes:
            return
        # ★ disable button + show loading
        self._download_btn = self.sender()
        self._download_btn.setText("⏳ กำลังโหลด...")
        self._download_btn.setEnabled(False)
        # ★ process events ทันที (กัน UI ค้างตอน set text)
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()

        # ★ ใช้ QThread (ไม่ใช่ raw threading — กัน signal ไม่ยิง)
        from PySide6.QtCore import QThread
        class DownloadThread(QThread):
            downloaded = Signal(dict)
            failed = Signal(str)
            def __init__(self, url):
                super().__init__()
                self.url = url
            def run(self):
                try:
                    import urllib.request as _urq
                    import ssl
                    ctx = ssl.create_default_context()
                    ctx.load_default_certs()
                    req = _urq.Request(self.url, headers={
                        "User-Agent": "BroadcastPlayroom/2.0",
                        "Accept": "application/json",
                    })
                    with _urq.urlopen(req, timeout=10, context=ctx) as resp:
                        raw = resp.read().decode("utf-8")
                    parsed = _json.loads(raw)
                    if isinstance(parsed, dict) and "replace_words" in parsed:
                        incoming = parsed["replace_words"]
                    elif isinstance(parsed, dict):
                        incoming = parsed
                    else:
                        self.failed.emit("format ไม่ถูกต้อง")
                        return
                    if not isinstance(incoming, dict) or not incoming:
                        self.failed.emit("คลังศัพท์ว่าง")
                        return
                    self.downloaded.emit(incoming)
                except Exception as e:
                    self.failed.emit(str(e))

        self._dl_thread = DownloadThread(DICT_URL)
        self._dl_thread.downloaded.connect(self._on_download_done)
        self._dl_thread.failed.connect(self._on_download_failed)
        self._dl_thread.start()

    def _on_download_failed(self, error):
        self._reset_download_btn()
        QMessageBox.critical(self, "ล้มเหลว", f"ดาวน์โหลดไม่ได้: {error}")

        threading.Thread(target=_worker, daemon=True).start()

    def _reset_download_btn(self):
        if hasattr(self, '_download_btn') and self._download_btn:
            self._download_btn.setText("⬇️ โหลดจากคลัง")
            self._download_btn.setEnabled(True)

    def _on_download_done(self, incoming):
        """import dictionary ที่โหลดมา — merge เข้า table"""
        from text_filter import TextFilter as _TF
        # ★ normalize incoming → {src: {display, read}}
        normalized = {}
        for k, v in incoming.items():
            src = str(k).strip()
            if not src:
                continue
            entry = _TF._normalize_entry(v)
            normalized[src] = entry

        # ★ เก็บค่าปัจจุบันจาก table (อ่านจาก cellWidget._edit)
        existing = set()
        for row in range(self.table.rowCount()):
            w0 = self.table.cellWidget(row, 0)
            if w0 and hasattr(w0, '_edit'):
                src = w0._edit.text().strip()
                if src:
                    existing.add(src)

        # ★ merge: เพิ่มเฉพาะคำใหม่ (คำซ้ำข้าม)
        added = 0
        conflicts = 0
        for src, entry in normalized.items():
            if src in existing:
                conflicts += 1
            else:
                self._add_row_data(src, entry.get('display', ''), entry.get('read', ''))
                existing.add(src)
                added += 1

        self._update_count()
        msg = f"✅ เพิ่ม {added} คำใหม่"
        if conflicts:
            msg += f"\n⚠️ ข้าม {conflicts} คำซ้ำ (เก็บค่าเดิม)"
        QMessageBox.information(self, "⬇️ โหลดเสร็จ", msg)

    def _delete_selected(self):
        """ลบแถวที่เลือก"""
        rows = set()
        for item in self.table.selectedItems():
            rows.add(item.row())
        for r in sorted(rows, reverse=True):
            self.table.removeRow(r)
        self._update_count()

    def _update_count(self):
        self.count_label.setText(f"{self.table.rowCount()} คำ")

    def _save(self):
        """บันทึก"""
        if not self.settings:
            self.accept()
            return
        words = {}
        for row in range(self.table.rowCount()):
            # ★ อ่านจาก QLineEdit ใน cell widget (w._edit)
            src = ''
            display = ''
            read = ''
            w0 = self.table.cellWidget(row, 0)
            w1 = self.table.cellWidget(row, 1)
            w2 = self.table.cellWidget(row, 2)
            if w0 and hasattr(w0, '_edit'):
                src = w0._edit.text().strip()
            if w1 and hasattr(w1, '_edit'):
                display = w1._edit.text().strip()
            if w2 and hasattr(w2, '_edit'):
                read = w2._edit.text().strip()
            if not src:
                continue
            words[src] = {'display': display, 'read': read}
        self.settings.replace_words = words
        try:
            from settings import save_settings
            save_settings(self.settings)
            # ★ update text filter
            if self.parent_app and hasattr(self.parent_app, 'pipeline') and self.parent_app.pipeline:
                self.parent_app.pipeline.set_filter(self.settings.to_text_filter())
        except Exception as e:
            logger.error(f"Failed to save: {e}")
        self.accept()
