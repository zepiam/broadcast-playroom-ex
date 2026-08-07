"""playroom_trigger.py — Playroom trigger editor dialog"""
import logging
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QWidget, QFrame, QLabel, QPushButton, QLineEdit, QVBoxLayout,
    QHBoxLayout, QScrollArea, QSpinBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QMessageBox, QFileDialog,
)

logger = logging.getLogger("playroom_trigger")


class PlayroomTriggerDialog(QDialog):
    """Playroom trigger editor — เพิ่ม/ลบ/แก้ไข triggers + clips"""

    def __init__(self, parent_app):
        super().__init__(parent_app if isinstance(parent_app, QWidget) else None)
        self.parent_app = parent_app
        self.settings = getattr(parent_app, 'settings', None)
        self.setWindowTitle("🎮 Playroom Triggers")
        self.setGeometry(180, 120, 720, 560)
        self.setMinimumSize(600, 400)
        self._build_ui()
        self._load_triggers()

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
        title = QLabel("🎮 Playroom Triggers")
        title.setStyleSheet("font-size: 15px; font-weight: 700; color: #f59e0b;")
        hlayout.addWidget(title)
        hlayout.addStretch()
        btn_add = QPushButton("➕ เพิ่ม Trigger")
        btn_add.setObjectName("Primary")
        btn_add.clicked.connect(self._add_trigger)
        hlayout.addWidget(btn_add)
        layout.addWidget(header)

        # ★ Triggers list (scrollable)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(16, 12, 16, 12)
        self.container_layout.setSpacing(8)
        self.container_layout.addStretch()
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll, 1)

        # ★ Bottom bar
        bottom = QFrame()
        bottom.setFixedHeight(50)
        bottom.setStyleSheet("background-color: #131726; border-top: 1px solid #2a2f45;")
        bottom_layout = QHBoxLayout(bottom)
        bottom_layout.setContentsMargins(16, 0, 16, 0)
        bottom_layout.addStretch()
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

    def _load_triggers(self):
        """โหลด triggers จาก settings"""
        triggers = getattr(self.settings, 'playroom_triggers', []) or []
        for trig in triggers:
            self._add_trigger_row(trig)

    def _add_trigger_row(self, trig):
        """เพิ่ม row สำหรับ trigger หนึ่ง"""
        if not isinstance(trig, dict):
            return
        code = trig.get('code', '')
        clips = trig.get('clips', []) or []
        daily_limit = trig.get('daily_limit', 3)

        row = QFrame()
        row.setObjectName("Card")
        row_layout = QVBoxLayout(row)
        row_layout.setContentsMargins(12, 8, 12, 8)
        row_layout.setSpacing(6)

        # ★ Top: code + daily limit + delete
        top = QHBoxLayout()
        code_entry = QLineEdit(code)
        code_entry.setStyleSheet("font-family: monospace; font-weight: 600;")
        top.addWidget(QLabel("Code:"))
        top.addWidget(code_entry, 1)
        limit_label = QLabel("Limit/day:")
        top.addWidget(limit_label)
        limit_spin = QSpinBox()
        limit_spin.setRange(0, 100)
        limit_spin.setValue(daily_limit)
        top.addWidget(limit_spin)
        btn_del = QPushButton("🗑")
        btn_del.setObjectName("IconButton")
        btn_del.setFixedSize(32, 32)
        btn_del.clicked.connect(lambda: row.deleteLater())
        top.addWidget(btn_del)
        row_layout.addLayout(top)

        # ★ Clips section — list + add + browse + weight
        from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
        clips_label = QLabel(f"📦 Clips ({len(clips)}):")
        clips_label.setStyleSheet("color: #9ca3af; font-size: 12px;")
        row_layout.addWidget(clips_label)

        clips_table = QTableWidget(0, 3)
        clips_table.setHorizontalHeaderLabels(["ชื่อ", "ไฟล์", "น้ำหนัก (%)"])
        clips_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        clips_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        clips_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        clips_table.setColumnWidth(2, 80)
        clips_table.setMinimumHeight(80)
        clips_table.setMaximumHeight(140)
        row_layout.addWidget(clips_table)

        # load existing clips
        for clip in clips:
            if isinstance(clip, dict):
                r = clips_table.rowCount()
                clips_table.insertRow(r)
                clips_table.setItem(r, 0, QTableWidgetItem(clip.get('name', '')))
                clips_table.setItem(r, 1, QTableWidgetItem(clip.get('path', '')))
                clips_table.setItem(r, 2, QTableWidgetItem(str(clip.get('weight', 50))))

        # ★ Add clip buttons
        clip_btns = QHBoxLayout()
        btn_add_clip = QPushButton("➕ เพิ่ม Clip")
        btn_add_clip.clicked.connect(lambda: self._add_clip_row(clips_table))
        clip_btns.addWidget(btn_add_clip)
        btn_browse = QPushButton("📁 เลือกไฟล์")
        btn_browse.clicked.connect(lambda: self._browse_clip(clips_table))
        clip_btns.addWidget(btn_browse)
        btn_del_clip = QPushButton("🗑 ลบ Clip ที่เลือก")
        btn_del_clip.clicked.connect(lambda: self._delete_clip(clips_table))
        clip_btns.addWidget(btn_del_clip)
        row_layout.addLayout(clip_btns)

        # ★ Store data for save
        row.code_entry = code_entry
        row.limit_spin = limit_spin
        row.clips_table = clips_table
        row._orig_trigger = trig

        self.container_layout.insertWidget(self.container_layout.count() - 1, row)

    def _add_clip_row(self, table):
        """เพิ่มแถว clip ว่าง"""
        r = table.rowCount()
        table.insertRow(r)
        table.setItem(r, 0, QTableWidgetItem(''))
        table.setItem(r, 1, QTableWidgetItem(''))
        table.setItem(r, 2, QTableWidgetItem('50'))

    def _browse_clip(self, table):
        """เลือกไฟล์ clip (วิดีโอ/รูป)"""
        from PySide6.QtWidgets import QFileDialog
        files, _ = QFileDialog.getOpenFileNames(
            self, "เลือกไฟล์ Clip",
            "", "Media Files (*.mp4 *.webm *.mov *.png *.jpg *.jpeg *.gif *.webp);;All Files (*.*)"
        )
        if not files:
            return
        import os
        for fpath in files:
            name = os.path.splitext(os.path.basename(fpath))[0]
            r = table.rowCount()
            table.insertRow(r)
            table.setItem(r, 0, QTableWidgetItem(name))
            table.setItem(r, 1, QTableWidgetItem(fpath))
            table.setItem(r, 2, QTableWidgetItem('50'))

    def _delete_clip(self, table):
        """ลบ clip ที่เลือก"""
        rows = set()
        for item in table.selectedItems():
            rows.add(item.row())
        for r in sorted(rows, reverse=True):
            table.removeRow(r)

    def _add_trigger(self):
        """เพิ่ม trigger ใหม่ (ว่าง)"""
        self._add_trigger_row({'code': '#new', 'clips': [], 'daily_limit': 3})

    def _save(self):
        """บันทึก triggers"""
        if not self.settings:
            self.accept()
            return
        triggers = []
        for i in range(self.container_layout.count()):
            item = self.container_layout.itemAt(i)
            row = item.widget() if item else None
            if row and hasattr(row, 'code_entry'):
                code = row.code_entry.text().strip()
                if not code:
                    continue
                # ★ read clips from table
                clips = []
                clips_table = row.clips_table
                for cr in range(clips_table.rowCount()):
                    name_item = clips_table.item(cr, 0)
                    path_item = clips_table.item(cr, 1)
                    weight_item = clips_table.item(cr, 2)
                    if name_item and path_item:
                        clips.append({
                            'name': name_item.text().strip(),
                            'path': path_item.text().strip(),
                            'weight': int(weight_item.text()) if weight_item and weight_item.text().isdigit() else 50,
                        })
                orig = getattr(row, '_orig_trigger', {})
                triggers.append({
                    'code': code,
                    'daily_limit': row.limit_spin.value(),
                    'clips': clips,
                    'widget_ids': orig.get('widget_ids', []),
                })
        self.settings.playroom_triggers = triggers
        try:
            from settings import save_settings
            save_settings(self.settings)
            if self.parent_app and hasattr(self.parent_app, 'pipeline') and self.parent_app.pipeline:
                self.parent_app.pipeline.config.playroom_triggers = list(triggers)
        except Exception as e:
            logger.error(f"Failed to save playroom triggers: {e}")
        self.accept()
