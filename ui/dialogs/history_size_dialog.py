"""history_size_dialog.py — แจ้งเตือนตอนเปิดโปรแกรม: "ประวัติแชทใหญ่เกิน 1 GB" → สำรองแล้วล้าง / ล้างเลย / ไว้ก่อน

"ประวัติแชท" ในที่นี้ = ตัวข้อความแชทของผู้ชมทุกคน (message_history.json) — ไฟล์นี้ถูกเขียนใหม่ทั้งไฟล์ทุกไม่กี่วินาที
และโหลดทั้งไฟล์ตอนเปิดโปรแกรม ถ้าใหญ่เป็นระดับ GB โปรแกรมจะช้า/กินแรมมาก

ล้างแล้ว "หาย": ตัวข้อความแชท (ที่ดูได้ในโปรไฟล์ผู้ชม)
ล้างแล้ว "ยังอยู่": ยอดข้อความรวมต่อคน, แพลตฟอร์มที่เคยแชท, เห็นครั้งแรก/ล่าสุด + จำนวนวันที่มา, ยอดโดเนท/ซับ,
                   ประวัติ event, ชื่อที่ตั้งเอง, การบล็อก — (ทั้งหมดนี้เก็บแยกจากตัวข้อความ)
ถ้าเลือกสำรอง: บันทึกข้อความทั้งหมดเป็นไฟล์บีบอัด .json.gz ในโฟลเดอร์ที่เลือก และตรวจว่าอ่านกลับได้ก่อนจึงล้าง
(สำรองไม่สำเร็จ = ไม่ล้าง)
"""
from __future__ import annotations

import logging
import os
from datetime import datetime

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton, QVBoxLayout,
)

from ui.user_kit import C, btn_qss, dim_text, faint_text, rgba, role

logger = logging.getLogger("history_size")


def fmt_size(n: int) -> str:
    n = float(max(0, n))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:,.0f} {unit}" if unit in ("B", "KB") else f"{n:,.2f} {unit}"
        n /= 1024
    return f"{n:,.2f} TB"


def _pick_dir(parent, start: str) -> str:
    """เลือกโฟลเดอร์เก็บไฟล์สำรอง (แยกเป็นฟังก์ชันเพื่อให้ทดสอบแทนที่ได้)"""
    return QFileDialog.getExistingDirectory(parent, "เลือกโฟลเดอร์สำหรับเก็บไฟล์สำรองประวัติแชท", start)


def _confirm_clear(parent) -> bool:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Warning)
    box.setWindowTitle("ยืนยันล้างประวัติข้อความ")
    box.setText("ล้างตัวข้อความแชทของทุกคนโดยไม่สำรอง ?")
    box.setInformativeText("ข้อความแชทจะหายถาวร กู้คืนไม่ได้\n"
                           "(ยอดข้อความ/แพลตฟอร์ม/ยอดโดเนท-ซับ ของแต่ละคนยังอยู่ครบ)")
    yes = box.addButton("ล้างเลย", QMessageBox.DestructiveRole)
    no = box.addButton("ยกเลิก", QMessageBox.RejectRole)
    box.setDefaultButton(no)
    box.exec()
    return box.clickedButton() is yes


class _ArchiveThread(QThread):
    done = Signal(bool, str, int)      # ok, error_text, size_bytes

    def __init__(self, mh, path, parent=None):
        super().__init__(parent)
        self._mh, self._path = mh, path

    def run(self) -> None:
        try:
            size = self._mh.archive_chat_text(self._path)
            self.done.emit(True, "", int(size))
        except Exception as exc:  # noqa: BLE001
            self.done.emit(False, str(exc), 0)


class HistorySizeDialog(QDialog):
    def __init__(self, mh, parent=None, size_bytes: int | None = None, manual: bool = False, keep_days: int = 0):
        """manual=True: เปิดจากปุ่ม "ล้างข้อความแชท" ใน User Manager (ไม่ใช่การเตือนไฟล์ใหญ่เกิน 1 GB)"""
        super().__init__(parent)
        self.manual = manual
        self.keep_days = int(keep_days or 0)
        self.mh = mh
        self.size_bytes = size_bytes if size_bytes is not None else mh.file_size()
        self.result_kind = "later"       # "later" | "backup_clear" | "clear"
        self.archive_path = ""
        self.cleared = False
        self._thread = None
        self.setWindowTitle("ล้างข้อความแชท" if manual else "ประวัติแชทมีขนาดใหญ่มาก")
        self.setModal(True)
        self.setFixedWidth(560)
        self._build()

    # ── หน้าตา ────────────────────────────────────────────
    def _build(self) -> None:
        R = role("supporter")            # โทนเตือน (เหลือง/ทอง ตามธีม)
        self.setStyleSheet(f"QDialog {{ background-color: {C('BG')}; }}")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 20)
        root.setSpacing(14)

        head = QFrame()
        head.setObjectName("HSHead")
        head.setStyleSheet(
            f"QFrame#HSHead {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, "
            f"stop:0 {rgba(R['solid'], 0.28)}, stop:1 {rgba(C('BG'), 0)}); border-bottom: 1px solid {C('BORDER')}; }}")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(24, 20, 24, 18)
        hl.setSpacing(16)
        badge = QLabel("🗄️")
        badge.setAlignment(Qt.AlignCenter)
        badge.setFixedSize(60, 60)
        badge.setStyleSheet(f"font-size: 30px; background-color: {rgba(R['solid'], 0.22)}; "
                            f"border: 1px solid {rgba(R['solid'], 0.6)}; border-radius: 18px; min-height: 0;")
        hl.addWidget(badge)
        col = QVBoxLayout()
        col.setSpacing(3)
        col.addWidget(self._lbl("ล้างข้อความแชทของทุกคน" if self.manual else "ประวัติแชทมีขนาดใหญ่มากแล้ว", 19, C("TEXT"), bold=True))
        size_txt = (f"ไฟล์ประวัติตอนนี้ {fmt_size(self.size_bytes)}" if self.manual
                    else f"ไฟล์ประวัติ {fmt_size(self.size_bytes)}  (เกิน {fmt_size(self._warn())})")
        self.size_label = self._lbl(size_txt, 13, R["text"], bold=True)
        col.addWidget(self.size_label)
        hl.addLayout(col, 1)
        root.addWidget(head)

        body = QVBoxLayout()
        body.setContentsMargins(24, 0, 24, 0)
        body.setSpacing(12)
        n_msgs, n_people = self.mh.chat_text_summary()
        intro_txt = f"ตอนนี้เก็บตัวข้อความแชทไว้ {n_msgs:,} ข้อความ จาก {n_people:,} คน"
        if self.manual:
            auto = (f"ตั้งไว้ให้เก็บ {self.keep_days} วัน — เกินนั้นจะถูกลบเองตอนเปิดโปรแกรม" if self.keep_days
                    else "ตอนนี้ตั้งเก็บไม่จำกัด — ตั้งให้ลบอัตโนมัติได้ที่ปุ่ม \"เก็บข้อความ\" ด้านบนของหน้า User Manager")
            intro_txt += f"\n{auto}"
        else:
            intro_txt += " — ไฟล์ใหญ่ขนาดนี้ทำให้โปรแกรมเปิดช้า กินหน่วยความจำมาก และเขียนไฟล์ช้าลงเรื่อยๆ"
        intro = self._lbl(intro_txt, 13, dim_text())
        intro.setWordWrap(True)
        body.addWidget(intro)

        body.addWidget(self._info_card("✅  ล้างแล้วยังอยู่ครบ", role("new"),
                                       "ยอดข้อความรวมของแต่ละคน · แพลตฟอร์มที่เคยแชท · เห็นครั้งแรก/ล่าสุด และจำนวนวันที่มา · "
                                       "ยอดโดเนท/ซับ · ประวัติ event · ชื่อที่ตั้งเอง · การบล็อก"))
        body.addWidget(self._info_card("🧹  ที่จะหายไป", role("blocked"),
                                       "เฉพาะตัวข้อความแชทของทุกคน (ที่ดูได้ในโปรไฟล์ผู้ชม → แท็บข้อความ)"))
        self.status = self._lbl("", 13, C("TEXT"))
        self.status.setWordWrap(True)
        self.status.setVisible(False)
        body.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        self.progress.setVisible(False)
        body.addWidget(self.progress)
        root.addLayout(body)

        self.btn_backup = QPushButton("💾  สำรองไว้ก่อน แล้วล้าง  (แนะนำ)")
        self.btn_backup.setStyleSheet(btn_qss("primary", 12, 44))
        self.btn_backup.setToolTip("บันทึกข้อความทั้งหมดเป็นไฟล์บีบอัดในโฟลเดอร์ที่เลือก ตรวจว่าอ่านกลับได้ แล้วจึงล้าง")
        self.btn_clear = QPushButton("🗑  ล้างเลย ไม่สำรอง")
        self.btn_clear.setStyleSheet(btn_qss("danger", 12, 40))
        self.btn_later = QPushButton("ยกเลิก" if self.manual else "ไว้ก่อน  (เตือนอีกตอนเปิดโปรแกรมครั้งหน้า)")
        self.btn_later.setStyleSheet(btn_qss("ghost", 12, 38))
        for b in (self.btn_backup, self.btn_clear, self.btn_later):
            b.setCursor(Qt.PointingHandCursor)
        self.btn_backup.clicked.connect(self._do_backup_and_clear)
        self.btn_clear.clicked.connect(self._do_clear_only)
        self.btn_later.clicked.connect(self.reject)
        foot = QVBoxLayout()
        foot.setContentsMargins(24, 4, 24, 0)
        foot.setSpacing(8)
        for b in (self.btn_backup, self.btn_clear, self.btn_later):
            foot.addWidget(b)
        self._foot = foot
        root.addLayout(foot)

    @staticmethod
    def _warn() -> int:
        from message_history import WARN_BYTES
        return WARN_BYTES

    @staticmethod
    def _lbl(text: str, px: int, color: str, bold: bool = False) -> QLabel:
        lb = QLabel(text)
        lb.setStyleSheet(f"font-size: {px}px; color: {color}; {'font-weight: 800;' if bold else ''} "
                         f"background: transparent; min-height: 0;")
        return lb

    def _info_card(self, title: str, R: dict, text: str) -> QFrame:
        card = QFrame()
        card.setObjectName("HSCard")
        card.setStyleSheet(
            f"QFrame#HSCard {{ background-color: {rgba(R['solid'], 0.10)}; border: 1px solid {rgba(R['solid'], 0.45)}; "
            f"border-left: 4px solid {R['solid']}; border-radius: 12px; }}")
        v = QVBoxLayout(card)
        v.setContentsMargins(14, 10, 14, 12)
        v.setSpacing(4)
        v.addWidget(self._lbl(title, 13, R["text"], bold=True))
        t = self._lbl(text, 13, C("TEXT"))
        t.setWordWrap(True)
        v.addWidget(t)
        return card

    # ── การทำงาน ──────────────────────────────────────────
    def _busy(self, on: bool, text: str = "") -> None:
        for b in (self.btn_backup, self.btn_clear, self.btn_later):
            b.setEnabled(not on)
        self.progress.setVisible(on)
        self.status.setVisible(bool(text))
        self.status.setText(text)

    def _default_backup_dir(self) -> str:
        docs = os.path.join(os.path.expanduser("~"), "Documents")
        return docs if os.path.isdir(docs) else os.path.expanduser("~")

    def _do_backup_and_clear(self) -> None:
        folder = _pick_dir(self, self._default_backup_dir())
        if not folder:
            return                                                   # ผู้ใช้ยกเลิกการเลือกโฟลเดอร์ → ไม่ทำอะไร
        name = f"chat_history_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json.gz"
        self.archive_path = os.path.join(folder, name)
        self._busy(True, "กำลังสำรองข้อความ… (อย่าปิดโปรแกรม — ไฟล์ใหญ่อาจใช้เวลาสักครู่)")
        self._thread = _ArchiveThread(self.mh, self.archive_path, self)
        self._thread.done.connect(self._on_archived)
        self._thread.start()

    def _on_archived(self, ok: bool, err: str, size: int) -> None:
        if not ok:
            logger.error(f"archive failed: {err}")
            self._busy(False, f"❌ สำรองไม่สำเร็จ: {err}\nยังไม่ได้ล้างอะไรเลย — ข้อความทั้งหมดยังอยู่ครบ")
            return
        removed = self.mh.clear_chat_text()
        self.result_kind = "backup_clear"
        self._finish(f"✅ สำรองแล้วที่\n{self.archive_path}\n({fmt_size(size)})  และล้างข้อความ {removed:,} รายการเรียบร้อย")

    def _do_clear_only(self) -> None:
        if not _confirm_clear(self):
            return
        removed = self.mh.clear_chat_text()
        self.result_kind = "clear"
        self._finish(f"✅ ล้างข้อความแชท {removed:,} รายการเรียบร้อย")

    def _finish(self, text: str) -> None:
        self.cleared = True
        new_size = self.mh.file_size()
        self._busy(False, f"{text}\nไฟล์ประวัติเหลือ {fmt_size(new_size)}  (จาก {fmt_size(self.size_bytes)})")
        self.status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.btn_backup.setVisible(False)
        self.btn_clear.setVisible(False)
        self.btn_later.setText("ปิด")
        self.btn_later.setStyleSheet(btn_qss("primary", 12, 40))
        self.btn_later.setEnabled(True)
        self.btn_later.clicked.disconnect()
        self.btn_later.clicked.connect(self.accept)
