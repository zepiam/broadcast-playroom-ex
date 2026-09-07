"""announce_sender.py — โปรแกรมเล็กสำหรับเจ้าของ: เผยแพร่/ลบประกาศ + ดูสถิติการอ่าน

- เผยแพร่/ลบประกาศ → push announce.json ขึ้น GitHub (fine-grained PAT — ใส่ครั้งเดียว)
- สถิติ → ดึงจาก men9ch.com (seen = แถบโผล่, dismiss = กด X ปิด — uniq คือเครื่องไม่ซ้ำ)

รัน dev:  python announce_sender.py
Build:     python -m PyInstaller announce_sender.spec --noconfirm
"""
from __future__ import annotations

import json
import os
import sys

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QTextEdit, QComboBox,
    QPushButton, QVBoxLayout, QHBoxLayout, QGroupBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox,
)

import announcement
from announcement import (
    fetch_announcement, publish_announcement, delete_announcement,
    VALID_TYPES, MAX_TEXT_LEN,
)

SETTINGS_FILE = os.path.join(
    os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
    else os.path.dirname(os.path.abspath(__file__)),
    "data", "announce_sender.json",
)

QSS = """
QWidget { background: #0f1420; color: #e5e7eb; font-family: 'Segoe UI', 'Kanit', sans-serif; font-size: 13px; }
QLabel#Heading { font-size: 18px; font-weight: 700; color: #f59e0b; }
QLabel#Dim { color: #9ca3af; font-size: 11px; }
QLineEdit, QTextEdit, QComboBox {
    background: #1a2133; color: #fff; border: 1px solid #334155;
    border-radius: 6px; padding: 8px;
}
QPushButton {
    background: #1a2133; color: #e5e7eb; border: 1px solid #334155;
    border-radius: 6px; padding: 9px 18px; font-weight: 600;
}
QPushButton:hover { border-color: #4a9eff; color: #93c5fd; }
QPushButton#Publish { background: #10b981; color: #fff; border: none; }
QPushButton#Publish:hover { background: #059669; }
QPushButton#Delete { background: rgba(239,68,68,0.15); color: #f87171; border: 1px solid rgba(239,68,68,0.4); }
QGroupBox {
    border: 1px solid #334155; border-radius: 8px; margin-top: 14px;
    padding: 14px; padding-top: 26px; font-weight: 700; color: #93c5fd;
}
QTableWidget { background: #1a2133; gridline-color: #334155; }
QHeaderView::section { background: #0f1420; color: #9ca3af; border: none; padding: 6px; }
"""


def _load_settings() -> dict:
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_settings(data: dict):
    try:
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


class _Job(QThread):
    """background job สำหรับ network — กัน UI ค้าง"""
    done = Signal(str, object)  # job_name, result

    def __init__(self, job: str, fn, *args):
        super().__init__()
        self._job = job
        self._fn = fn
        self._args = args

    def run(self):
        try:
            self.done.emit(self._job, self._fn(*self._args))
        except Exception as e:
            self.done.emit(self._job, {"error": str(e)})


class AnnounceSender(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("📢 Announce Sender — Broadcast Playroom")
        self.setMinimumSize(980, 560)
        self._thread = None
        self._build_ui()
        self._load()

    # ── UI ── (2 คอลัมน์: ซ้าย = จัดการประกาศ / ขวา = สถิติ)
    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # ═══ คอลัมน์ซ้าย: จัดการประกาศ ═══
        left = QVBoxLayout()
        left.setSpacing(10)

        title = QLabel("📢 ประกาศถึงผู้ใช้")
        title.setObjectName("Heading")
        left.addWidget(title)

        # ── Token ──
        token_box = QGroupBox("GitHub Token (ใส่ครั้งเดียว)")
        tv = QVBoxLayout(token_box)
        self.token_edit = QLineEdit()
        self.token_edit.setEchoMode(QLineEdit.Password)
        self.token_edit.setPlaceholderText("github_pat_...")
        tv.addWidget(self.token_edit)
        hint = QLabel("Fine-grained PAT — เลือก repo broadcast-playroom-ex + Contents: Read and write")
        hint.setObjectName("Dim")
        tv.addWidget(hint)
        left.addWidget(token_box)

        # ── ประกาศปัจจุบัน ──
        cur_box = QGroupBox("ประกาศปัจจุบัน (บน GitHub)")
        cv = QVBoxLayout(cur_box)
        self.current_label = QLabel("⏳ กำลังโหลด...")
        self.current_label.setWordWrap(True)
        self.current_label.setObjectName("Dim")
        cv.addWidget(self.current_label)
        self.refresh_btn = QPushButton("🔄 รีเฟรช")
        self.refresh_btn.clicked.connect(self.refresh_current)
        cv.addWidget(self.refresh_btn, 0, Qt.AlignLeft)
        left.addWidget(cur_box)

        # ── เผยแพร่ ──
        pub_box = QGroupBox("เผยแพร่ประกาศใหม่")
        pv = QVBoxLayout(pub_box)
        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText(
            f"พิมพ์ข้อความประกาศ (สูงสุด {MAX_TEXT_LEN} ตัวอักษร)\nเช่น: มีเวอร์ชั่นใหม่ — รีบอัพเดทนะครับ"
        )
        self.text_edit.setFixedHeight(90)
        pv.addWidget(self.text_edit)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("ระดับ"))
        self.type_combo = QComboBox()
        self.type_combo.addItem("📢 อัพเดท (ส้ม)", "update")
        self.type_combo.addItem("ℹ️ ข้อมูล (ฟ้า)", "info")
        self.type_combo.addItem("⚠️ เตือน (แดง)", "warning")
        row1.addWidget(self.type_combo, 1)
        row1.addStretch()
        pv.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("ลิงก์"))
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://... (ไม่บังคับ)")
        row2.addWidget(self.url_edit, 1)
        pv.addLayout(row2)

        btn_row = QHBoxLayout()
        self.publish_btn = QPushButton("🚀 เผยแพร่ประกาศ")
        self.publish_btn.setObjectName("Publish")
        self.publish_btn.clicked.connect(self.publish)
        self.delete_btn = QPushButton("🗑 ลบประกาศปัจจุบัน")
        self.delete_btn.setObjectName("Delete")
        self.delete_btn.clicked.connect(self.delete)
        btn_row.addWidget(self.publish_btn)
        btn_row.addWidget(self.delete_btn)
        btn_row.addStretch()
        pv.addLayout(btn_row)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setObjectName("Dim")
        pv.addWidget(self.status_label)
        left.addWidget(pub_box)

        left.addStretch()

        # ═══ คอลัมน์ขวา: สถิติ ═══
        right = QVBoxLayout()
        stat_box = QGroupBox("📊 สถิติการอ่าน (จากทุกเครื่อง)")
        sv = QVBoxLayout(stat_box)
        self.stats_table = QTableWidget(0, 5)
        self.stats_table.setHorizontalHeaderLabels(
            ["ID ประกาศ", "เห็น (เครื่อง)", "เห็น (ครั้ง)", "กดปิด (เครื่อง)", "กดปิด (ครั้ง)"]
        )
        self.stats_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.stats_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.stats_table.verticalHeader().setVisible(False)
        sv.addWidget(self.stats_table)
        stat_note = QLabel("เห็น = แถบประกาศโผล่บนเครื่องนั้น • กดปิด = ผู้ใช้กด X\nเครื่อง = IP ไม่ซ้ำ (เปิดซ้ำ 100 รอบก็นับเครื่องเดียว)")
        stat_note.setObjectName("Dim")
        sv.addWidget(stat_note)
        self.stats_btn = QPushButton("🔄 ดึงสถิติล่าสุด")
        self.stats_btn.clicked.connect(self.refresh_stats)
        sv.addWidget(self.stats_btn, 0, Qt.AlignLeft)
        right.addWidget(stat_box)

        # ★ ประกอบ 2 คอลัมน์ — ซ้าย fix กว้าง 400 / ขวา stretch เต็มที่เหลือ
        layout.addLayout(left, 0)
        layout.addLayout(right, 1)

    # ── actions ──
    def _run_job(self, job: str, fn, *args):
        if self._thread is not None and self._thread.isRunning():
            return
        self._thread = _Job(job, fn, *args)
        self._thread.done.connect(self._on_job_done)
        self._thread.start()

    def _on_job_done(self, job: str, result):
        # ★ ปลดล็อคปุ่มทุก job เสมอ — กันค้างหลัง publish/delete (เดิมลืม unlock)
        if job in ("publish", "delete"):
            self._set_busy(False)
        if job == "current":
            if result and result.get("id"):
                t = VALID_TYPES[0] if result.get("type") not in VALID_TYPES else result["type"]
                self.current_label.setText(
                    f"🟢 มีประกาศ [{result['id']}] ({t})\n\"{result.get('text', '')}\""
                    + (f"\n🔗 {result.get('url')}" if result.get("url") else "")
                )
            else:
                self.current_label.setText("⚪ ไม่มีประกาศ (ว่างอยู่)")
        elif job == "publish":
            ok, msg = result if isinstance(result, tuple) else (False, str(result))
            self.status_label.setText(msg)
            self.status_label.setStyleSheet(f"color: {'#10b981' if ok else '#ef4444'};")
            if ok:
                self.text_edit.clear()
                self.refresh_current()
        elif job == "delete":
            ok, msg = result if isinstance(result, tuple) else (False, str(result))
            self.status_label.setText(msg)
            self.status_label.setStyleSheet(f"color: {'#10b981' if ok else '#ef4444'};")
            if ok:
                self.refresh_current()
        elif job == "stats":
            self._render_stats(result)

    def _set_busy(self, busy: bool):
        for b in (self.publish_btn, self.delete_btn, self.refresh_btn, self.stats_btn):
            b.setEnabled(not busy)

    def refresh_current(self):
        self.current_label.setText("⏳ กำลังโหลด...")
        self._run_job("current", fetch_announcement)

    def publish(self):
        token = self.token_edit.text().strip()
        text = self.text_edit.toPlainText().strip()
        url = self.url_edit.text().strip()
        ann_type = self.type_combo.currentData()
        if not text:
            self.status_label.setText("❌ กรุณาพิมพ์ข้อความประกาศก่อน")
            self.status_label.setStyleSheet("color: #ef4444;")
            return
        if QMessageBox.question(
            self, "ยืนยัน",
            f"เผยแพร่ประกาศนี้ขึ้นทุกเครื่อง?\n\n\"{text[:120]}{'...' if len(text) > 120 else ''}\""
        ) != QMessageBox.Yes:
            return
        self._save_token()
        self._set_busy(True)
        self.status_label.setText("⏳ กำลังส่ง...")
        self.status_label.setStyleSheet("color: #f59e0b;")
        self._run_job("publish", publish_announcement, token, text, ann_type, url)

    def delete(self):
        token = self.token_edit.text().strip()
        if QMessageBox.question(
            self, "ยืนยัน", "ลบประกาศปัจจุบันออกจากทุกเครื่อง?"
        ) != QMessageBox.Yes:
            return
        self._save_token()
        self._set_busy(True)
        self.status_label.setText("⏳ กำลังลบ...")
        self.status_label.setStyleSheet("color: #f59e0b;")
        self._run_job("delete", delete_announcement, token)

    def refresh_stats(self):
        self.stats_btn.setEnabled(False)
        self._run_job("stats", self._fetch_stats)

    @staticmethod
    def _fetch_stats():
        import urllib.request, ssl
        req = urllib.request.Request(
            f"{announcement.HIT_URL}?action=stats",
            headers={"User-Agent": "AnnounceSender/1.0"},
        )
        with urllib.request.urlopen(req, timeout=10, context=ssl.create_default_context()) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _render_stats(self, data):
        self.stats_btn.setEnabled(True)
        if not isinstance(data, dict) or not data.get("ok"):
            self.stats_table.setRowCount(0)
            return
        stats = data.get("stats", {})
        rows = sorted(stats.items(), key=lambda kv: kv[1].get("last", 0), reverse=True)
        self.stats_table.setRowCount(len(rows))
        for i, (sid, s) in enumerate(rows[:50]):
            for col, key in enumerate(("seen_uniq", "seen_hits", "dismiss_uniq", "dismiss_hits")):
                item = QTableWidgetItem(str(s.get(key, 0)))
                item.setTextAlignment(Qt.AlignCenter)
                self.stats_table.setItem(i, col + 1, item)
            id_item = QTableWidgetItem(sid)
            self.stats_table.setItem(i, 0, id_item)

    # ── settings ──
    def _save_token(self, *args):
        data = _load_settings()
        data["token"] = self.token_edit.text().strip()
        _save_settings(data)

    def _load(self):
        self.token_edit.setText(_load_settings().get("token", ""))
        # ★ save ทันทีที่พิมพ์เสร็จ (คลิกที่อื่น/Enter) + ตอนปิดโปรแกรม — กัน token หาย
        self.token_edit.editingFinished.connect(self._save_token)
        self.refresh_current()

    def closeEvent(self, event):
        self._save_token()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS)
    win = AnnounceSender()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
