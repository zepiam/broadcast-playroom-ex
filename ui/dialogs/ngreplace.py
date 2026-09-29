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
CONTRIBUTE_URL = "https://www.men9ch.com/wiki/ng-replace.php?pid=broadcast-playroom"


class NGReplaceDialog(QDialog):
    """NG-Replace editor — 3-field dictionary (source / display / read)"""

    def __init__(self, parent_app):
        super().__init__(parent_app if isinstance(parent_app, QWidget) else None)
        self.parent_app = parent_app
        self.settings = getattr(parent_app, 'settings', None)
        self.setWindowTitle("🚫 NG-Replace")
        self.setGeometry(180, 120, 780, 580)
        self.setMinimumSize(660, 440)
        self._build_ui()
        self._load_words()
        # ★ snapshot ข้อมูลตอนเปิด (เพื่อเทียบตอนปิด — เตือนถ้ามีการแก้ไข)
        self._original_data = self._collect_current_data()
        from PySide6.QtCore import QTimer
        QTimer.singleShot(400, self._auto_sync_on_open)

    def _auto_sync_on_open(self):
        """ซิงค์คำศัพท์ใหม่อัตโนมัติเมื่อเปิดหน้าต่าง (ถ้าเปิด replace_auto_sync)"""
        if not getattr(self.settings, 'replace_auto_sync', True):
            return
        if getattr(self, '_auto_syncing', False):
            return

        import time
        now = time.time()
        if now - getattr(self, '_last_auto_sync_time', 0) < 10:
            return
        self._last_auto_sync_time = now
        self._auto_syncing = True

        from PySide6.QtCore import QThread
        DICT_URL = "https://men9ch.com/wiki/ng-replace.php?pid=broadcast-playroom&download=1"

        class _AutoSyncWorker(QThread):
            success_sig = Signal(dict)
            done_sig = Signal()

            def run(self):
                try:
                    import urllib.request as _urq, ssl, json as _json
                    ctx = ssl.create_default_context()
                    ctx.load_default_certs()
                    req = _urq.Request(DICT_URL, headers={
                        "User-Agent": "BroadcastPlayroom/2.0",
                        "Accept": "application/json"
                    })
                    with _urq.urlopen(req, timeout=8, context=ctx) as resp:
                        raw = resp.read().decode("utf-8")
                    parsed = _json.loads(raw)
                    incoming = parsed.get("replace_words", parsed) if isinstance(parsed, dict) else {}
                    if isinstance(incoming, dict) and incoming:
                        self.success_sig.emit(incoming)
                except Exception as e:
                    logger.debug(f"_auto_sync_on_open failed/skipped: {e}")
                finally:
                    self.done_sig.emit()

        worker = _AutoSyncWorker(self)

        def _on_success(incoming):
            from text_filter import TextFilter as _TF
            deleted_set = set(getattr(self.settings, 'replace_deleted_words', []) or [])
            existing = set()
            for r in range(self.table.rowCount()):
                w0 = self.table.cellWidget(r, 0)
                if w0 and hasattr(w0, '_edit'):
                    txt = w0._edit.text().strip()
                    if txt:
                        existing.add(txt)

            added_count = 0
            for k, v in incoming.items():
                src = str(k).strip()
                if not src or src in existing or src in deleted_set:
                    continue
                norm = _TF._normalize_entry(v)
                self._add_row_data(src, norm.get('display', ''), norm.get('read', ''))
                existing.add(src)
                added_count += 1

            if added_count > 0:
                self._update_count()
                self._save_silent()
                self._original_data = self._collect_current_data()
                logger.info(f"Auto-synced {added_count} new words in ngreplace dialog")

        def _on_done():
            self._auto_syncing = False

        worker.success_sig.connect(_on_success)
        worker.done_sig.connect(_on_done)
        self._auto_sync_worker = worker
        worker.start()

    def _collect_current_data(self):
        """อ่านข้อมูลทั้งหมดจาก table → dict {src: {display, read}}"""
        words = {}
        for row in range(self.table.rowCount()):
            src = display = read = ''
            w0 = self.table.cellWidget(row, 0)
            w1 = self.table.cellWidget(row, 1)
            w2 = self.table.cellWidget(row, 2)
            if w0 and hasattr(w0, '_edit'):
                src = w0._edit.text().strip()
            if w1 and hasattr(w1, '_edit'):
                display = w1._edit.text().strip()
            if w2 and hasattr(w2, '_edit'):
                read = w2._edit.text().strip()
            if src:
                words[src] = {'display': display, 'read': read}
        return words

    def closeEvent(self, event):
        """★ ตอนปิด — เตือนถ้ามีการเพิ่ม/แก้ไขคำศัพท์"""
        current = self._collect_current_data()
        if current != self._original_data:
            from PySide6.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                self, "บันทึกการเปลี่ยนแปลง",
                "คุณได้เพิ่มหรือแก้ไขคำศัพท์\nต้องการบันทึกหรือไม่?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.Yes,
            )
            if reply == QMessageBox.Yes:
                self._save()  # save + accept (ปิด)
                event.accept()
            elif reply == QMessageBox.No:
                event.accept()  # ปิดโดยไม่บันทึก
            else:
                event.ignore()  # ยกเลิกการปิด
        else:
            event.accept()  # ไม่มีการเปลี่ยนแปลง → ปิดได้เลย

    def _open_contribute_url(self):
        """เปิดหน้าเว็บช่วยเพิ่มคำศัพท์เข้าคลังกลาง"""
        try:
            from ui.dialogs.replace_contribute import open_replace_contribute_dialog
            open_replace_contribute_dialog(self)
        except Exception as e:
            logger.error(f"Cannot open contribute dialog: {e}")
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl(CONTRIBUTE_URL))

    def _on_auto_sync_toggled(self, checked: bool):
        """บันทึกสถานะเปิด/ปิด Auto-Sync"""
        if self.settings:
            self.settings.replace_auto_sync = bool(checked)
            try:
                from settings import save_settings
                save_settings(self.settings)
            except Exception as e:
                logger.error(f"_on_auto_sync_toggled save failed: {e}")

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
        title.setStyleSheet("font-size: 17px; font-weight: 700; color: #f59e0b;")
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

        # ★ Banner ช่วยเพิ่มคำศัพท์ (สีเขียวเด่น)
        banner = QFrame()
        banner.setStyleSheet("background-color: #0d121f; border-bottom: 1px solid #1e2436;")
        banner_layout = QHBoxLayout(banner)
        banner_layout.setContentsMargins(16, 7, 16, 7)
        banner_layout.setSpacing(10)
        btn_contribute = QPushButton("🌐 ช่วยเราเพิ่มคำศัพท์ (แชร์กับทุกคนที่ใช้โปรแกรม)")
        btn_contribute.setCursor(Qt.PointingHandCursor)
        btn_contribute.setStyleSheet("""
            QPushButton {
                background-color: #059669;
                color: #ffffff;
                font-size: 13px;
                font-weight: 600;
                border: 1px solid #10b981;
                border-radius: 6px;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background-color: #10b981;
                border-color: #34d399;
            }
            QPushButton:pressed {
                background-color: #047857;
            }
        """)
        btn_contribute.clicked.connect(self._open_contribute_url)
        banner_layout.addWidget(btn_contribute)
        banner_layout.addStretch()
        layout.addWidget(banner)

        # ★ Search box + Auto-sync CheckBox
        search_row = QHBoxLayout()
        search_row.setContentsMargins(16, 8, 16, 6)
        search_row.setSpacing(12)
        search_lbl = QLabel("🔍")
        search_lbl.setStyleSheet("color: #9ca3af; font-size: 16px;")
        search_row.addWidget(search_lbl)
        self.search_entry = QLineEdit()
        self.search_entry.setPlaceholderText("ค้นหาคำศัพท์ (คำเดิม / คำที่แสดง / คำที่อ่าน)...")
        self.search_entry.setStyleSheet("QLineEdit { background: #0a0e1a; border: 1px solid #2a2f45; border-radius: 4px; padding: 6px 10px; color: #e5e7eb; }")
        self.search_entry.textChanged.connect(self._filter_rows)
        search_row.addWidget(self.search_entry, 1)

        from PySide6.QtWidgets import QCheckBox
        self.chk_auto_sync = QCheckBox("ซิงค์คลังศัพท์อัตโนมัติเมื่อเปิดโปรแกรม")
        self.chk_auto_sync.setToolTip("ดาวน์โหลดคำศัพท์ที่ผ่านการ Approve จากคลังชุมชนอัตโนมัติทุกครั้งที่เปิดโปรแกรม")
        self.chk_auto_sync.setCursor(Qt.PointingHandCursor)
        self.chk_auto_sync.setStyleSheet("""
            QCheckBox {
                color: #d1d5db;
                font-size: 13px;
                spacing: 6px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid #4b5563;
                border-radius: 3px;
                background: #111827;
            }
            QCheckBox::indicator:hover {
                border-color: #7c3aed;
            }
            QCheckBox::indicator:checked {
                background-color: #7c3aed;
                border-color: #a78bfa;
            }
        """)
        auto_sync_val = getattr(self.settings, 'replace_auto_sync', True) if self.settings else True
        self.chk_auto_sync.setChecked(bool(auto_sync_val))
        self.chk_auto_sync.toggled.connect(self._on_auto_sync_toggled)
        search_row.addWidget(self.chk_auto_sync)

        layout.addLayout(search_row)

        # ★ Table (4 columns: source+🔊 / display / read+🔊 / ❌ delete)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["คำเดิม", "คำที่แสดง", "คำที่อ่าน TTS", ""])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.horizontalHeader().resizeSection(3, 40)  # ★ คอลัมน์ลบ 40px
        self.table.horizontalHeader().setStretchLastSection(False)
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
        btn_save = QPushButton("💾 บันทึก")
        btn_save.setObjectName("Primary")
        btn_save.setFixedWidth(100)
        btn_save.clicked.connect(self._save)
        btn_close = QPushButton("ปิด")
        btn_close.setFixedWidth(80)
        btn_close.clicked.connect(self.close)  # ★ ใช้ close() เพื่อ trigger closeEvent (เตือนถ้ามีแก้ไข)
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
        btn2 = QPushButton("🔊")
        btn2.setFixedSize(32, 28)
        btn2.setToolTip("ฟังคำที่อ่าน")
        btn2.setStyleSheet("border: 1px solid #2a2f45; border-radius: 4px; background: #1a1f33; padding: 0px; font-size: 15px;")
        btn2.setCursor(Qt.PointingHandCursor)
        # ★ อ่าน text จาก QLineEdit ตอนกด (แก้ไขได้ทันที ไม่ต้อง save + reopen)
        btn2.clicked.connect(lambda _, e=edit2, b=btn2: self._preview_tts_with_loading(b, e.text()))
        l2.addWidget(btn2)
        self.table.setCellWidget(row, 2, w2)
        w2._edit = edit2

        # ★ column 3: ❌ delete button
        w3 = QWidget()
        l3 = QHBoxLayout(w3)
        l3.setContentsMargins(2, 2, 2, 2)
        btn_del = QPushButton("❌")
        btn_del.setFixedSize(30, 28)
        btn_del.setToolTip("ลบแถวนี้")
        btn_del.setCursor(Qt.PointingHandCursor)
        btn_del.setStyleSheet("border: none; background: transparent; font-size: 14px; padding: 0px;")
        btn_del.clicked.connect(lambda _, r=row: self._delete_row_with_confirm(r))
        l3.addWidget(btn_del)
        self.table.setCellWidget(row, 3, w3)

    def _delete_row_with_confirm(self, row):
        """ลบแถวพร้อมถามยืนยัน + save ทันที"""
        # ★ อ่านคำเดิมเพื่อแสดงใน confirmation
        w0 = self.table.cellWidget(row, 0)
        word = w0._edit.text().strip() if w0 and hasattr(w0, '_edit') else f"แถว {row+1}"
        reply = QMessageBox.question(
            self, "ยืนยันการลบ",
            f'ต้องการลบ "{word}" ใช่ไหม?',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
        )
        if reply == QMessageBox.Yes:
            # ★ บันทึกคำที่ลบลง replace_deleted_words ป้องกัน auto-sync ดึงกลับมา
            if self.settings and word and not word.startswith("แถว "):
                del_list = list(getattr(self.settings, 'replace_deleted_words', []) or [])
                if word not in del_list:
                    del_list.append(word)
                    self.settings.replace_deleted_words = del_list
            # ★ clear cell widgets ก่อน removeRow (กัน crash)
            for col in range(4):
                w = self.table.cellWidget(row, col)
                if w:
                    self.table.removeCellWidget(row, col)
            self.table.removeRow(row)
            self._update_count()
            # ★ save ทันที + sync count + update snapshot
            self._save_silent()
            self._update_count()

    def _save_silent(self):
        """save โดยไม่ปิด dialog (เรียกหลังลบ/แก้ไข)"""
        if not self.settings:
            return
        words = {}
        for row in range(self.table.rowCount()):
            src = display = read = ''
            w0 = self.table.cellWidget(row, 0)
            w1 = self.table.cellWidget(row, 1)
            w2 = self.table.cellWidget(row, 2)
            if w0 and hasattr(w0, '_edit'):
                src = w0._edit.text().strip()
            if w1 and hasattr(w1, '_edit'):
                display = w1._edit.text().strip()
            if w2 and hasattr(w2, '_edit'):
                read = w2._edit.text().strip()
            if src:
                words[src] = {'display': display, 'read': read}
        self.settings.replace_words = words
        try:
            from settings import save_settings
            save_settings(self.settings)
            # ★ sync pipeline filter
            if self.parent_app and hasattr(self.parent_app, 'pipeline') and self.parent_app.pipeline:
                self.parent_app.pipeline.set_filter(self.settings.to_text_filter())
        except Exception as e:
            logger.error(f"_save_silent failed: {e}")
        # ★ update snapshot (กัน closeEvent เตือนซ้ำ)
        self._original_data = dict(words)

    def _delete_selected(self):
        """ลบแถวที่เลือก (legacy — ใช้ _delete_row_with_confirm แทน)"""
        pass

    def _preview_tts_with_loading(self, btn, text, is_original=False):
        """preview TTS with loading indicator (กันกดรัว)"""
        if not text.strip():
            return
        if btn.text() == "⏳":
            return  # กำลังโหลดอยู่ → ไม่ทำซ้ำ
        btn.setText("⏳")
        # ★ เล่น TTS ตรงๆ (ไม่ผ่าน pipeline)
        self._preview_tts_text(text, is_original=is_original)
        # ★ reset หลัง 3 วิ
        QTimer.singleShot(3000, lambda: btn.setText("🔊"))

    def _preview_tts_text(self, text, is_original=False):
        """เล่นเสียง TTS ของ text — ★ เรียก edge-tts ตรงๆ (ไม่ผ่าน pipeline)

        ★ ทั้งคำเดิมและคำอ่านใช้ Premwadee เหมือนกัน (เหมือน v1)
        ★ ไม่ผ่าน pipeline เด็ดขาด → ไม่แปลภาษา ไม่ multilang ไม่ RVC
        ★ is_original มีไว้แค่บอกว่าเป็นคำเดิมหรือคำอ่าน (ไม่เปลี่ยน voice)
        """
        if not text.strip():
            return
        import threading
        # ★ หยุด preview เก่าก่อน (กันซ้อน)
        if hasattr(self, '_preview_stop'):
            self._preview_stop.set()
        self._preview_stop = threading.Event()

        # ★ ใช้ Premwadee เสมอ (เหมือน v1)
        voice = "th-TH-PremwadeeNeural"

        def _play():
            try:
                import edge_tts, asyncio, tempfile, os
                async def _tts():
                    communicate = edge_tts.Communicate(text, voice)
                    audio = b""
                    async for chunk in communicate.stream():
                        if self._preview_stop.is_set():
                            return None
                        if chunk["type"] == "audio":
                            audio += chunk["data"]
                    return audio
                mp3_bytes = asyncio.run(_tts())
                if not mp3_bytes or self._preview_stop.is_set():
                    return
                # save mp3 + play with pygame
                tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
                tmp.write(mp3_bytes)
                tmp.close()
                import pygame
                try:
                    pygame.mixer.init()
                except Exception:
                    pass
                if pygame.mixer.get_init():
                    if pygame.mixer.music.get_busy():
                        pygame.mixer.music.stop()
                    pygame.mixer.music.load(tmp.name)
                    pygame.mixer.music.play()
                    import time
                    for _ in range(100):
                        if not pygame.mixer.music.get_busy() or self._preview_stop.is_set():
                            break
                        time.sleep(0.1)
                    pygame.mixer.music.unload()
                try:
                    os.remove(tmp.name)
                except Exception:
                    pass
            except Exception as e:
                logger.warning(f"TTS preview error: {e}")

        self._preview_thread = threading.Thread(target=_play, daemon=True)
        self._preview_thread.start()

    def _add_row(self):
        """เพิ่มแถวว่าง"""
        self._add_row_data('', '', '')
        self._update_count()

    def _add_word_dialog(self):
        """เปิด dialog เพิ่มคำศัพท์ใหม่ (3 ช่อง + ปุ่ม preview)"""
        dlg = QDialog(self)
        dlg.setWindowTitle("➕ เพิ่มคำศัพท์")
        dlg.setMinimumWidth(440)
        layout = QVBoxLayout(dlg)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 16, 20, 16)

        # ★ ปุ่มสีเขียว ช่วยเพิ่มคำศัพท์ (แชร์กับทุกคนที่ใช้โปรแกรม)
        btn_contribute = QPushButton("🌐 ช่วยเราเพิ่มคำศัพท์ (แชร์กับทุกคนที่ใช้โปรแกรม)")
        btn_contribute.setCursor(Qt.PointingHandCursor)
        btn_contribute.setStyleSheet("""
            QPushButton {
                background-color: #059669;
                color: #ffffff;
                font-size: 13px;
                font-weight: 600;
                border: 1px solid #10b981;
                border-radius: 6px;
                padding: 8px 12px;
            }
            QPushButton:hover {
                background-color: #10b981;
                border-color: #34d399;
            }
            QPushButton:pressed {
                background-color: #047857;
            }
        """)
        btn_contribute.clicked.connect(self._open_contribute_url)
        layout.addWidget(btn_contribute)

        # เส้นคั่นบางๆ
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #2a2f45; margin-top: 2px; margin-bottom: 2px;")
        layout.addWidget(sep)

        # ★ คำเดิม + 🔊 preview
        layout.addWidget(QLabel("คำเดิม:"))
        src_row = QHBoxLayout()
        src_row.setSpacing(4)
        src_entry = QLineEdit()
        src_entry.setPlaceholderText("คำเดิม (ที่จะค้นหา)")
        src_row.addWidget(src_entry, 1)
        layout.addLayout(src_row)
        # ★ คำที่แสดง
        layout.addWidget(QLabel("คำที่แสดง:"))
        display_entry = QLineEdit()
        display_entry.setPlaceholderText("คำที่แสดงในแชท (ว่าง = ซ่อน)")
        layout.addWidget(display_entry)
        # ★ คำที่อ่าน + 🔊 preview
        layout.addWidget(QLabel("คำที่อ่าน TTS:"))
        read_row = QHBoxLayout()
        read_row.setSpacing(4)
        read_entry = QLineEdit()
        read_entry.setPlaceholderText("คำที่อ่าน TTS (ว่าง = ไม่อ่านส่วนนี้)")
        read_row.addWidget(read_entry, 1)
        btn_read_preview = QPushButton("🔊")
        btn_read_preview.setFixedSize(34, 30)
        btn_read_preview.setToolTip("ทดสอบอ่านคำที่จะอ่าน")
        btn_read_preview.setStyleSheet("border: 1px solid #2a2f45; border-radius: 4px; background: #1a1f33; padding: 0px; font-size: 15px;")
        btn_read_preview.setCursor(Qt.PointingHandCursor)
        btn_read_preview.clicked.connect(lambda: self._preview_tts_with_loading(btn_read_preview, read_entry.text()))
        read_row.addWidget(btn_read_preview)
        layout.addLayout(read_row)
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
                # ★ ปลดบล็อกหากคำนี้เคยอยู่ใน replace_deleted_words
                if self.settings:
                    del_list = list(getattr(self.settings, 'replace_deleted_words', []) or [])
                    if src in del_list:
                        del_list.remove(src)
                        self.settings.replace_deleted_words = del_list
                self._add_row_data(src, display_entry.text().strip(), read_entry.text().strip())
                self._update_count()
                self._save_silent()

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

    def _reset_download_btn(self):
        if hasattr(self, '_download_btn') and self._download_btn:
            self._download_btn.setText("⬇️ โหลดจากคลัง")
            self._download_btn.setEnabled(True)

    def _on_download_done(self, incoming):
        """import dictionary ที่โหลดมา — merge เข้า table"""
        self._reset_download_btn()
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

        deleted_words = list(getattr(self.settings, 'replace_deleted_words', []) or [])
        deleted_set = set(deleted_words)

        # หาว่ามีคำที่เคยลบใน incoming ที่ยังไม่มีใน existing หรือไม่
        found_deleted_in_incoming = [src for src in normalized if src in deleted_set and src not in existing]

        restore_deleted = False
        if found_deleted_in_incoming:
            sample_words = ", ".join(f'"{w}"' for w in found_deleted_in_incoming[:5])
            if len(found_deleted_in_incoming) > 5:
                sample_words += f" และอีก {len(found_deleted_in_incoming) - 5} คำ"

            box = QMessageBox(self)
            box.setWindowTitle("พบคำศัพท์ที่เคยลบในคลังออนไลน์")
            box.setIcon(QMessageBox.Question)
            box.setText(f"<b>พบคำศัพท์ {len(found_deleted_in_incoming)} คำ ที่คุณเคยลบออกจากเครื่องไปแล้ว:</b>")
            box.setInformativeText(
                f"<p style='color: #fbbf24; font-size: 13px; font-weight: bold;'>👉 {sample_words}</p>"
                "<p>คุณต้องการ<b>กู้คืนคำเหล่านี้กลับมาใช้งานใหม่</b> หรือ<b>ข้ามไป</b> (ไม่ดาวน์โหลดคำที่เคยลบ)?</p>"
            )
            btn_restore = box.addButton("🔄 กู้คืนกลับมาใช้", QMessageBox.YesRole)
            btn_skip = box.addButton("🚫 ข้าม (ไม่โหลดคำนี้)", QMessageBox.NoRole)
            box.setDefaultButton(btn_skip)
            box.exec()

            if box.clickedButton() == btn_restore:
                restore_deleted = True
                # ลบออกจาก replace_deleted_words
                for w in found_deleted_in_incoming:
                    if w in deleted_words:
                        deleted_words.remove(w)
                self.settings.replace_deleted_words = deleted_words

        # ★ merge: เพิ่มเฉพาะคำใหม่ (คำซ้ำข้าม)
        added = 0
        conflicts = 0
        skipped_deleted = 0
        restored = 0

        for src, entry in normalized.items():
            if src in existing:
                conflicts += 1
            elif src in deleted_set and not restore_deleted:
                skipped_deleted += 1
            else:
                self._add_row_data(src, entry.get('display', ''), entry.get('read', ''))
                existing.add(src)
                if src in found_deleted_in_incoming and restore_deleted:
                    restored += 1
                else:
                    added += 1

        self._update_count()
        self._save_silent()

        msg = f"✅ เพิ่ม {added} คำใหม่"
        if restored:
            msg += f"\n🔄 กู้คืน {restored} คำที่เคยลบกลับมาใช้งาน"
        if conflicts:
            msg += f"\n⚠️ ข้าม {conflicts} คำเดิมในเครื่อง (ไม่เขียนทับ)"
        if skipped_deleted:
            msg += f"\n🚫 ข้าม {skipped_deleted} คำที่คุณเคยลบไว้"
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
        """นับเฉพาะแถวที่มีข้อมูล + ไม่ถูกซ่อนโดย search filter"""
        visible_with_data = 0
        total_with_data = 0
        for row in range(self.table.rowCount()):
            w0 = self.table.cellWidget(row, 0)
            src = w0._edit.text().strip() if w0 and hasattr(w0, '_edit') else ''
            if not src:
                continue
            total_with_data += 1
            if not self.table.isRowHidden(row):
                visible_with_data += 1
        search = self.search_entry.text().strip().lower() if hasattr(self, 'search_entry') else ''
        if search:
            self.count_label.setText(f"{visible_with_data} / {total_with_data} คำ")
        else:
            self.count_label.setText(f"{total_with_data} คำ")

    def _filter_rows(self):
        """กรองแถวตามคำค้นหา (คำเดิม / คำที่แสดง / คำที่อ่าน)"""
        search = self.search_entry.text().strip().lower()
        for row in range(self.table.rowCount()):
            # อ่าน text จาก QLineEdit ในทุกคอลัมน์
            texts = []
            for col in range(3):  # col 0,1,2 (skip 3 = delete button)
                w = self.table.cellWidget(row, col)
                if w and hasattr(w, '_edit'):
                    texts.append(w._edit.text().lower())
            combined = ' '.join(texts)
            should_show = (not search) or (search in combined)
            self.table.setRowHidden(row, not should_show)
        self._update_count()

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
        # ★ update snapshot หลัง save (กัน closeEvent เตือนซ้ำ)
        self._original_data = self._collect_current_data()
        self.accept()
