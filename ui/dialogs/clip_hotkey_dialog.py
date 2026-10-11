"""clip_hotkey_dialog.py — Dialog สำหรับตั้งค่าปุ่มลัด (Hotkey) ของ Clip Marker

ให้ผู้ใช้ bind key ด้วยการกดปุ่มบนคีย์บอร์ดจริง ไม่ต้องพิมพ์ชื่อปุ่มเอง
มีปุ่ม Reset กลับไปเป็น F9
"""
import logging
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QWidget, QFrame, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QMessageBox,
)
from ui.dialogs.hotkey_binder import make_hotkey_binder
from ui.theme import COLOR_BG, COLOR_CARD, COLOR_BORDER, COLOR_TEXT, COLOR_ACCENT

logger = logging.getLogger("clip_hotkey_dialog")


class ClipHotkeyDialog(QDialog):
    """Dialog ตั้งค่าปุ่มลัดมาร์กคลิปไฮไลต์"""

    def __init__(self, parent_app):
        super().__init__(parent_app if isinstance(parent_app, QWidget) else None)
        self.parent_app = parent_app
        self.settings = getattr(parent_app, "settings", None)
        self.setWindowTitle("⭐ ตั้งค่าปุ่มลัดมาร์กคลิป (Clip Hotkey)")
        self.setFixedSize(480, 270)
        self.setStyleSheet(f"QDialog {{ background-color: {COLOR_BG}; }}")
        self._current_hk = getattr(self.settings, "clip_hotkey", "f9") if self.settings else "f9"
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        # Header
        title = QLabel("⭐ ตั้งค่าปุ่มลัดมาร์กคลิปไฮไลต์")
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #facc15;")
        layout.addWidget(title)

        desc = QLabel(
            "กำหนดปุ่มลัดบนคีย์บอร์ดเพื่อบันทึกช่วงเวลาไฮไลต์ (มาร์กช็อตเด็ด)\n"
            "ทำงานแบบ Global Hotkey แม้ขณะเล่นเกมเต็มจอ"
        )
        desc.setStyleSheet("font-size: 12px; color: #9ca3af; line-height: 1.4;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Card: Hotkey binder + Reset button
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background-color: {COLOR_CARD}; border: 1px solid {COLOR_BORDER}; border-radius: 8px; }}"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(10)

        row = QHBoxLayout()
        row.setSpacing(10)
        lbl_key = QLabel("ปุ่มลัด (Hotkey):")
        lbl_key.setStyleSheet("color: #e5e7eb; font-weight: 600; font-size: 13px;")
        row.addWidget(lbl_key)

        # Binder button
        self.binder_btn = make_hotkey_binder(
            self,
            self._current_hk,
            on_captured=self._on_hotkey_captured,
        )
        self.binder_btn.setFixedHeight(32)
        row.addWidget(self.binder_btn, 1)

        # Reset button
        self.btn_reset = QPushButton("🔄 รีเซ็ต (F9)")
        self.btn_reset.setFixedHeight(32)
        self.btn_reset.setCursor(Qt.PointingHandCursor)
        self.btn_reset.setToolTip("รีเซ็ตกลับไปใช้ค่าเริ่มต้น F9")
        self.btn_reset.setStyleSheet(
            "QPushButton { background: #1e293b; color: #cbd5e1; border: 1px solid #334155; "
            "border-radius: 4px; padding: 0 10px; font-size: 12px; font-weight: 600; }"
            "QPushButton:hover { background: #334155; color: #f8fafc; border-color: #64748b; }"
        )
        self.btn_reset.clicked.connect(self._reset_to_default)
        row.addWidget(self.btn_reset)
        card_layout.addLayout(row)

        hint = QLabel("💡 วิธีใช้: คลิกปุ่มสีม่วง แล้วกดปุ่มบนคีย์บอร์ดที่ต้องการ (เช่น F9, F10, Shift+F9, Ctrl+H)")
        hint.setStyleSheet("color: #6b7280; font-size: 11px;")
        card_layout.addWidget(hint)
        layout.addWidget(card)

        layout.addStretch()

        # Bottom buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()

        btn_cancel = QPushButton("ยกเลิก")
        btn_cancel.setFixedHeight(32)
        btn_cancel.setFixedWidth(80)
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.setStyleSheet(
            "QPushButton { background: transparent; color: #9ca3af; border: 1px solid #374151; "
            "border-radius: 6px; font-size: 12px; font-weight: 600; }"
            "QPushButton:hover { background: #1f2937; color: #e5e7eb; }"
        )
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_save = QPushButton("💾 บันทึก")
        btn_save.setFixedHeight(32)
        btn_save.setFixedWidth(90)
        btn_save.setCursor(Qt.PointingHandCursor)
        btn_save.setStyleSheet(
            "QPushButton { background: #7c3aed; color: white; border: none; "
            "border-radius: 6px; font-size: 12px; font-weight: 700; }"
            "QPushButton:hover { background: #6d28d9; }"
        )
        btn_save.clicked.connect(self._save_and_apply)
        btn_row.addWidget(btn_save)

        layout.addLayout(btn_row)

    def _on_hotkey_captured(self, hk: str):
        self._current_hk = (hk or "").strip().lower()

    def _reset_to_default(self):
        self._current_hk = "f9"
        if hasattr(self.binder_btn, "set_hotkey"):
            self.binder_btn.set_hotkey("f9")

    def _save_and_apply(self):
        new_hk = (getattr(self.binder_btn, "_hotkey", "") or self._current_hk or "f9").strip().lower()
        if self.settings:
            self.settings.clip_hotkey = new_hk
            try:
                self.settings.save()
            except Exception as e:
                logger.warning(f"Failed to save settings: {e}")

        # Update in parent_app
        if self.parent_app:
            if hasattr(self.parent_app, "_update_clip_hotkey"):
                self.parent_app._update_clip_hotkey(new_hk)
            elif hasattr(self.parent_app, "_reregister_hotkeys"):
                self.parent_app._reregister_hotkeys()
            if hasattr(self.parent_app, "topbar") and hasattr(self.parent_app.topbar, "update_clip_button_label"):
                self.parent_app.topbar.update_clip_button_label(new_hk)
            if hasattr(self.parent_app, "status_bar"):
                self.parent_app.status_bar.set_status(f"✅ บันทึกปุ่มลัดมาร์กคลิปเป็น: {new_hk.upper()}")

        self.accept()
