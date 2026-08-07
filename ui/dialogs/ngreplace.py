"""ngreplace.py — NG-Replace editor dialog (คำต้องห้าม + คำแทนที่)

รองรับ 3-field: คำเดิม / คำที่แสดง / คำที่อ่าน TTS
"""
import logging
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QWidget, QFrame, QLabel, QPushButton, QLineEdit, QVBoxLayout,
    QHBoxLayout, QScrollArea, QListWidget, QListWidgetItem, QMessageBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)

logger = logging.getLogger("ngreplace")


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
        btn_add = QPushButton("➕ เพิ่ม")
        btn_add.setObjectName("Primary")
        btn_add.clicked.connect(self._add_row)
        hlayout.addWidget(btn_add)
        layout.addWidget(header)

        # ★ Table (3 columns: source / display / read)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["คำเดิม", "คำที่แสดง", "คำที่อ่าน TTS"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
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
        """เพิ่ม row ลง table"""
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(src))
        self.table.setItem(row, 1, QTableWidgetItem(display))
        self.table.setItem(row, 2, QTableWidgetItem(read))

    def _add_row(self):
        """เพิ่มแถวว่าง"""
        self._add_row_data('', '', '')
        self._update_count()

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
            src_item = self.table.item(row, 0)
            display_item = self.table.item(row, 1)
            read_item = self.table.item(row, 2)
            if not src_item:
                continue
            src = src_item.text().strip()
            if not src:
                continue
            display = display_item.text().strip() if display_item else ''
            read = read_item.text().strip() if read_item else ''
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
