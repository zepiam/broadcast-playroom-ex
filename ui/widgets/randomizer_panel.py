# -*- coding: utf-8 -*-

"""

randomizer_panel.py

หน้าต่างแผงควบคุมระบบสุ่มอเนกประสงค์ (Quick Randomizer)

สำหรับสุ่มบทลงโทษ, สุ่มคนดูร่วมเล่นเกม, สุ่มกิจกรรม โดยไม่ต้องเพิ่ม Widget ใน Composer

"""



import os

import json

import time

import random

import logging

from typing import Optional, List, Dict, Any



from PySide6.QtCore import Qt, QTimer, Signal

from PySide6.QtGui import QFont, QCursor

from PySide6.QtWidgets import (

    QApplication, QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel,

    QPushButton, QLineEdit, QComboBox, QListView, QSlider, QScrollArea, QMessageBox,

    QStackedWidget, QCheckBox, QDialog

)



logger = logging.getLogger(__name__)



STYLE_BTN_PRIMARY = """

QPushButton {

    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2563eb, stop:1 #1d4ed8);

    border: 1px solid #3b82f6;

    border-radius: 8px;

    color: #ffffff;

    font-size: 13.5px;

    font-weight: 700;

    padding: 8px 16px;

}

QPushButton:hover { background: #3b82f6; }

QPushButton:pressed { background: #1e40af; }

"""



STYLE_BTN_SPIN = """

QPushButton {

    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f59e0b, stop:1 #d97706);

    border: 2px solid #fbbf24;

    border-radius: 10px;

    color: #0f172a;

    font-size: 16px;

    font-weight: 900;

    padding: 12px 20px;

}

QPushButton:hover {

    background: #fbbf24;

    border-color: #fef08a;

}

QPushButton:pressed {

    background: #b45309;

}

"""



STYLE_BTN_SECONDARY = """

QPushButton {

    background-color: #162032;

    border: 1px solid #283548;

    border-radius: 7px;

    color: #cbd5e1;

    font-size: 12.5px;

    font-weight: 600;

    padding: 6px 12px;

}

QPushButton:hover {

    background-color: #1e293b;

    border-color: #475569;

    color: #ffffff;

}

QPushButton:pressed {

    background-color: #0f172a;

}

"""



DEFAULT_RANDOMIZER_PRESETS = [

    {

        "id": "preset_penalty",

        "title": "สุ่มบทลงโทษสตรีมเมอร์สุดฮา",

        "items": [

            "วิดพื้น 10 ครั้ง",

            "ดื่มน้ำ 1 แก้วเต็ม",

            "ร้องเพลง 1 ท่อน",

            "เต้นไก่ย่าง 10 วินาที",

            "พูดเสียงเป็ด 1 นาที"

        ]

    },

    {

        "id": "preset_viewers",

        "title": "สุ่มคนดูร่วมเล่นเกม",

        "items": [

            "ผู้โชคดีคนที่ 1",

            "ผู้โชคดีคนที่ 2",

            "ผู้โชคดีคนที่ 3",

            "ผู้โชคดีคนที่ 4"

        ]

    },

    {

        "id": "preset_food",

        "title": "สุ่มเมนูอาหารวันนี้",

        "items": [

            "กะเพราไข่ดาว",

            "ชาบูปิ้งย่าง",

            "ก๋วยเตี๋ยวต้มยำ",

            "ส้มตำไก่ย่าง",

            "ข้าวมันไก่"

        ]

    }

]





def _get_asset_path(filename: str) -> str:
    import os, sys
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        p = os.path.join(exe_dir, "_internal", "assets", filename)
        if not os.path.exists(p):
            p = os.path.join(exe_dir, "assets", filename)
    else:
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        p = os.path.join(root, "assets", filename)
    return p.replace(chr(92), "/")

class RandomizerPanel(QFrame):

    """หน้าต่างแผงควบคุมระบบสุ่มอเนกประสงค์ (Quick Randomizer)"""

    closed = Signal()



    def __init__(self, parent_app=None):

        super().__init__()

        self.parent_app = parent_app

        self.setObjectName("RandomizerPanel")

        self.setWindowTitle("🎯 ระบบสุ่มอเนกประสงค์ — Quick Randomizer")

        self.resize(520, 720)

        self.setMinimumSize(400, 550)

        self.setWindowFlags(Qt.Window | Qt.WindowCloseButtonHint | Qt.WindowMinMaxButtonsHint)



        self.presets_file = os.path.join(

            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),

            "data", "randomizer_presets.json"

        )

        self.presets: List[Dict[str, Any]] = []

        self._load_presets()



        # Slot animation timer for local preview

        self._anim_timer = QTimer(self)

        self._anim_timer.setInterval(45)

        self._anim_timer.timeout.connect(self._on_anim_tick)

        self._anim_ticks_left = 0

        self._pending_winner = ""

        self._spin_candidates: List[str] = []



        # Overlay settings state

        self.overlay_scale = 100

        self.overlay_font = 100

        self.overlay_ox = 0

        self.overlay_oy = 0

        self.overlay_anchor = "center"

        self.overlay_duration = 5



        self._item_rows: List[QLineEdit] = []



        self._init_qss()

        self._build_ui()

        self._apply_preset(self.presets[0] if self.presets else None)



    def _setup_combobox(self, combo: QComboBox):

        """ตั้งค่า QListView และ StrongFocus เพื่อให้คลิกครั้งเดียวเลือกได้ทันที"""

        combo.setView(QListView())

        combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)



    def _init_qss(self):

        
        arrow_img = _get_asset_path("arrow_down.png")
        arrow_disabled_img = _get_asset_path("arrow_down_disabled.png")
        self.setStyleSheet("""

            QFrame#RandomizerPanel {

                background-color: #0b1120;

                border: 1px solid #1e293b;

            }

            QLabel {

                color: #e2e8f0;

                font-size: 13px;

                background: transparent;

            }

            QLineEdit {

                background-color: #162032;

                border: 1px solid #283548;

                border-radius: 6px;

                color: #f8fafc;

                font-size: 13px;

                padding: 6px 10px;

            }

            QLineEdit:focus {

                border-color: #3b82f6;

            }

            QComboBox {

                background-color: #162032;

                border: 1px solid #283548;

                border-radius: 6px;

                color: #f8fafc;

                font-size: 13px;

                padding: 6px 10px;

                min-height: 24px;

            }

            QComboBox:focus, QComboBox:hover {

                border-color: #3b82f6;

            }

            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 28px;
                border: none;
                background: transparent;
            }

            QComboBox::down-arrow {
                image: url("__ARROW_DOWN_IMG__");
                width: 12px;
                height: 8px;
                margin-right: 8px;
                border: none;
                background: transparent;
            }

            QComboBox::down-arrow:disabled {
                image: url("__ARROW_DOWN_DISABLED_IMG__");
                border: none;
                background: transparent;
            }

            QComboBox QAbstractItemView {

                background-color: #111827;

                border: 1px solid #334155;

                border-radius: 6px;

                color: #f8fafc;

                selection-background-color: #2563eb;

                selection-color: #ffffff;

                outline: none;

            }

            QComboBox QAbstractItemView::item {

                min-height: 30px;

                padding: 4px 10px;

                color: #f8fafc;

            }

            QComboBox QAbstractItemView::item:selected {

                background-color: #2563eb;

                color: #ffffff;

            }

            QSlider::groove:horizontal {

                height: 6px;

                background: #1e293b;

                border-radius: 3px;

            }

            QSlider::sub-page:horizontal {

                background: #38bdf8;

                border-radius: 3px;

            }

            QSlider::handle:horizontal {

                background: #ffffff;

                border: 2px solid #0284c7;

                width: 14px;

                margin-top: -5px;

                margin-bottom: -5px;

                border-radius: 7px;

            }

        """)



    def _load_presets(self):

        if os.path.exists(self.presets_file):

            try:

                with open(self.presets_file, "r", encoding="utf-8") as f:

                    self.presets = json.load(f)

            except Exception as e:

                logger.error(f"Failed to load randomizer presets: {e}")

                self.presets = list(DEFAULT_RANDOMIZER_PRESETS)

        else:

            self.presets = list(DEFAULT_RANDOMIZER_PRESETS)

            self._save_presets()



        if not self.presets:

            self.presets = list(DEFAULT_RANDOMIZER_PRESETS)



    def _save_presets(self):

        try:

            os.makedirs(os.path.dirname(self.presets_file), exist_ok=True)

            with open(self.presets_file, "w", encoding="utf-8") as f:

                json.dump(self.presets, f, ensure_ascii=False, indent=2)

        except Exception as e:

            logger.error(f"Failed to save randomizer presets: {e}")



    def _build_ui(self):

        root = QVBoxLayout(self)

        root.setContentsMargins(14, 14, 14, 14)

        root.setSpacing(10)



        # Header Bar

        hdr = QHBoxLayout()

        hdr.addWidget(QLabel("🎰"))

        v_title = QVBoxLayout()

        v_title.setSpacing(1)

        lbl_t = QLabel("ระบบสุ่มอเนกประสงค์ (Quick Randomizer)")

        lbl_t.setStyleSheet("font-size: 15px; font-weight: 800; color: #ffffff;")

        lbl_s = QLabel("สุ่มบทลงโทษ / สุ่มคนดู / สุ่มกิจกรรม ➔ เสกลอยขึ้น OBS อัตโนมัติ")

        lbl_s.setStyleSheet("font-size: 11px; color: #94a3b8;")

        v_title.addWidget(lbl_t)

        v_title.addWidget(lbl_s)

        hdr.addLayout(v_title)

        hdr.addStretch()



        # Tabs Switcher: [ 🎯 สุ่มกิจกรรม ] vs [ ⚙️ ตั้งค่าจอ OBS ]

        self.btn_tab_spin = QPushButton("🎯 สุ่มกิจกรรม")

        self.btn_tab_spin.setStyleSheet(STYLE_BTN_PRIMARY)

        self.btn_tab_spin.clicked.connect(lambda: self._switch_tab(0))



        self.btn_tab_settings = QPushButton("⚙️ ตั้งค่าจอ OBS")

        self.btn_tab_settings.setStyleSheet(STYLE_BTN_SECONDARY)

        self.btn_tab_settings.clicked.connect(lambda: self._switch_tab(1))



        hdr.addWidget(self.btn_tab_spin)

        hdr.addWidget(self.btn_tab_settings)

        root.addLayout(hdr)



        self.main_stack = QStackedWidget()

        root.addWidget(self.main_stack, 1)



        # Tab 0: Spin Page

        self.page_spin = QWidget()

        self._build_spin_page_ui(self.page_spin)

        self.main_stack.addWidget(self.page_spin)



        # Tab 1: Settings Page

        self.page_settings = QWidget()

        self._build_settings_page_ui(self.page_settings)

        self.main_stack.addWidget(self.page_settings)



    def _switch_tab(self, idx: int):

        self.main_stack.setCurrentIndex(idx)

        self.btn_tab_spin.setStyleSheet(STYLE_BTN_PRIMARY if idx == 0 else STYLE_BTN_SECONDARY)

        self.btn_tab_settings.setStyleSheet(STYLE_BTN_PRIMARY if idx == 1 else STYLE_BTN_SECONDARY)



    # ── Tab 0: Spin Page UI ──

    def _build_spin_page_ui(self, widget: QWidget):

        v = QVBoxLayout(widget)

        v.setContentsMargins(0, 6, 0, 0)

        v.setSpacing(10)



        # Preset Selector Row

        p_row = QHBoxLayout()

        p_row.addWidget(QLabel("เลือก Preset:"))

        self.cmb_preset = QComboBox()

        self._setup_combobox(self.cmb_preset)

        self._refresh_preset_dropdown()

        self.cmb_preset.currentIndexChanged.connect(self._on_preset_dropdown_changed)

        self.cmb_preset.activated.connect(self._on_preset_dropdown_changed)

        p_row.addWidget(self.cmb_preset, 1)



        btn_save_p = QPushButton("💾 บันทึก")

        btn_save_p.setStyleSheet(STYLE_BTN_SECONDARY)

        btn_save_p.clicked.connect(self._save_current_as_preset)

        p_row.addWidget(btn_save_p)



        btn_del_p = QPushButton("🗑️")

        btn_del_p.setStyleSheet(STYLE_BTN_SECONDARY)

        btn_del_p.clicked.connect(self._delete_current_preset)

        p_row.addWidget(btn_del_p)

        v.addLayout(p_row)



        # Title input

        t_row = QHBoxLayout()

        t_row.addWidget(QLabel("หัวข้อกิจกรรม:"))

        self.inp_title = QLineEdit("สุ่มบทลงโทษประจำวัน")

        self.inp_title.setStyleSheet("font-weight: bold; color: #f59e0b;")

        t_row.addWidget(self.inp_title, 1)

        v.addLayout(t_row)



        # Items List Header

        i_hdr = QHBoxLayout()

        self.lbl_items_count = QLabel("รายการที่จะสุ่ม (อย่างต่ำ 2 รายการ / สูงสุด 50):")

        self.lbl_items_count.setStyleSheet("font-size: 12px; color: #94a3b8;")

        i_hdr.addWidget(self.lbl_items_count)

        i_hdr.addStretch()



        btn_add = QPushButton("➕ เพิ่มรายการ")

        btn_add.setStyleSheet(STYLE_BTN_SECONDARY)

        btn_add.clicked.connect(lambda: self._add_item_row(""))

        btn_shuffle = QPushButton("🎲 สลับลำดับ")

        btn_shuffle.setStyleSheet(STYLE_BTN_SECONDARY)

        btn_shuffle.clicked.connect(self._shuffle_items)

        btn_clear = QPushButton("🗑️ ล้าง")

        btn_clear.setStyleSheet(STYLE_BTN_SECONDARY)

        btn_clear.clicked.connect(self._clear_all_items)



        i_hdr.addWidget(btn_add)

        i_hdr.addWidget(btn_shuffle)

        i_hdr.addWidget(btn_clear)

        v.addLayout(i_hdr)



        # Scrollable items area

        scroll = QScrollArea()

        scroll.setWidgetResizable(True)

        scroll.setStyleSheet("background: #0f172a; border: 1px solid #1e293b; border-radius: 8px;")

        self.items_container = QWidget()

        self.items_layout = QVBoxLayout(self.items_container)

        self.items_layout.setContentsMargins(8, 8, 8, 8)

        self.items_layout.setSpacing(6)

        self.items_layout.addStretch()

        scroll.setWidget(self.items_container)

        v.addWidget(scroll, 1)



        # Local Winner Result Card

        self.box_winner = QFrame()

        self.box_winner.setVisible(False)

        self.box_winner.setStyleSheet("background: #020617; border: 2px solid #f59e0b; border-radius: 8px; padding: 10px;")

        wv = QVBoxLayout(self.box_winner)

        wv.setSpacing(3)

        lbl_w_tag = QLabel("🎉 ผลลัพธ์ที่สุ่มได้ 🎉")

        lbl_w_tag.setAlignment(Qt.AlignCenter)

        lbl_w_tag.setStyleSheet("color: #fbbf24; font-size: 11px; font-weight: bold;")

        self.lbl_winner_text = QLabel("ผลลัพธ์")

        self.lbl_winner_text.setAlignment(Qt.AlignCenter)

        self.lbl_winner_text.setStyleSheet("color: #ffffff; font-size: 20px; font-weight: 900;")

        wv.addWidget(lbl_w_tag)

        wv.addWidget(self.lbl_winner_text)

        v.addWidget(self.box_winner)



        # Big Spin Launch Button

        self.btn_spin = QPushButton("🎰 เริ่มหมุนสุ่มขึ้นจอ OBS ทันที!")

        self.btn_spin.setStyleSheet(STYLE_BTN_SPIN)

        self.btn_spin.setCursor(Qt.PointingHandCursor)

        self.btn_spin.clicked.connect(self._start_spin)

        v.addWidget(self.btn_spin)



    def _refresh_preset_dropdown(self):

        self.cmb_preset.blockSignals(True)

        self.cmb_preset.clear()

        for p in self.presets:

            self.cmb_preset.addItem(p.get("title", "Preset"), p.get("id"))

        self.cmb_preset.blockSignals(False)



    def _on_preset_dropdown_changed(self, idx: int):

        p_id = self.cmb_preset.currentData()

        for p in self.presets:

            if p.get("id") == p_id:

                self._apply_preset(p)

                break



    def _apply_preset(self, preset: Optional[Dict[str, Any]]):

        if not preset:

            return

        self.inp_title.setText(preset.get("title", ""))

        items = preset.get("items", [])

        self._clear_all_items()

        for it in items:

            self._add_item_row(it)

        while len(self._item_rows) < 2:

            self._add_item_row("")



    def _add_item_row(self, text: str = ""):

        if len(self._item_rows) >= 50:

            QMessageBox.warning(self, "แจ้งเตือน", "ใส่รายการได้สูงสุด 50 รายการครับ")

            return



        row_widget = QWidget()

        rl = QHBoxLayout(row_widget)

        rl.setContentsMargins(0, 0, 0, 0)

        rl.setSpacing(6)



        idx = len(self._item_rows) + 1

        lbl_num = QLabel(f"{idx}.")

        lbl_num.setStyleSheet("color: #94a3b8; font-weight: bold; min-width: 24px;")

        rl.addWidget(lbl_num)



        inp = QLineEdit(text)

        inp.setPlaceholderText(f"รายการที่ {idx}...")

        rl.addWidget(inp, 1)



        btn_del = QPushButton("✕")

        btn_del.setStyleSheet("background: transparent; color: #ef4444; font-weight: bold; border: none; padding: 4px 8px;")

        btn_del.setCursor(Qt.PointingHandCursor)

        btn_del.clicked.connect(lambda: self._remove_item_row(row_widget, inp))

        rl.addWidget(btn_del)



        self._item_rows.append(inp)

        self.items_layout.insertWidget(self.items_layout.count() - 1, row_widget)

        self.lbl_items_count.setText(f"รายการที่จะสุ่ม ({len(self._item_rows)}/50 รายการ):")



    def _remove_item_row(self, row_widget: QWidget, inp: QLineEdit):

        if len(self._item_rows) <= 2:

            QMessageBox.warning(self, "แจ้งเตือน", "ต้องมีรายการอย่างน้อย 2 รายการขึ้นไปครับ")

            return

        if inp in self._item_rows:

            self._item_rows.remove(inp)

        row_widget.deleteLater()

        QTimer.singleShot(50, self._reindex_rows)



    def _reindex_rows(self):

        for i, inp in enumerate(self._item_rows):

            parent = inp.parentWidget()

            if parent:

                lbl = parent.findChild(QLabel)

                if lbl:

                    lbl.setText(f"{i + 1}.")

        self.lbl_items_count.setText(f"รายการที่จะสุ่ม ({len(self._item_rows)}/50 รายการ):")



    def _shuffle_items(self):

        texts = [inp.text().strip() for inp in self._item_rows if inp.text().strip()]

        if len(texts) < 2:

            return

        random.shuffle(texts)

        for i, inp in enumerate(self._item_rows):

            if i < len(texts):

                inp.setText(texts[i])

            else:

                inp.clear()



    def _clear_all_items(self):

        while self.items_layout.count() > 1:

            item = self.items_layout.takeAt(0)

            if item.widget():

                item.widget().deleteLater()

        self._item_rows.clear()

        self.lbl_items_count.setText("รายการที่จะสุ่ม (0/50 รายการ):")



    def _save_current_as_preset(self):

        items = [inp.text().strip() for inp in self._item_rows if inp.text().strip()]

        if len(items) < 2:

            QMessageBox.warning(self, "แจ้งเตือน", "กรุณากรอกรายการอย่างน้อย 2 รายการก่อนบันทึกครับ")

            return



        title = self.inp_title.text().strip() or "Preset สุ่ม"

        p_id = self.cmb_preset.currentData() or f"preset_{int(time.time())}"



        # Update or append

        found = False

        for p in self.presets:

            if p.get("id") == p_id:

                p["title"] = title

                p["items"] = items

                found = True

                break

        if not found:

            self.presets.append({"id": p_id, "title": title, "items": items})



        self._save_presets()

        self._refresh_preset_dropdown()

        QMessageBox.information(self, "สำเร็จ", f"บันทึก Preset '{title}' เรียบร้อยแล้วครับ!")



    def _delete_current_preset(self):

        p_id = self.cmb_preset.currentData()

        if not p_id:

            return

        ans = QMessageBox.question(self, "ยืนยันการลบ", "ต้องการลบ Preset นี้ใช่หรือไม่?", QMessageBox.Yes | QMessageBox.No)

        if ans == QMessageBox.Yes:

            self.presets = [p for p in self.presets if p.get("id") != p_id]

            self._save_presets()

            self._refresh_preset_dropdown()

            if self.presets:

                self._apply_preset(self.presets[0])



    # ── Tab 1: Settings Page UI ──

    def _build_settings_page_ui(self, widget: QWidget):

        v = QVBoxLayout(widget)

        v.setContentsMargins(0, 6, 0, 0)

        v.setSpacing(12)



        card = QFrame()

        card.setStyleSheet("background: #111827; border: 1px solid #1f293d; border-radius: 8px; padding: 14px;")

        cv = QVBoxLayout(card)

        cv.setSpacing(10)



        cv.addWidget(QLabel("⚙️ ตั้งค่าตำแหน่ง & ขนาดบนหน้าจอ OBS:"))



        # Scale slider

        s_row = QHBoxLayout()

        s_row.addWidget(QLabel("ขนาดกล่องสุ่ม (Scale):"))

        self.lbl_set_scale = QLabel(f"{self.overlay_scale}%")

        self.lbl_set_scale.setStyleSheet("color: #38bdf8; font-weight: bold;")

        self.slider_scale = QSlider(Qt.Horizontal)

        self.slider_scale.setRange(50, 200)

        self.slider_scale.setValue(self.overlay_scale)

        self.slider_scale.valueChanged.connect(self._on_scale_changed)

        s_row.addWidget(self.slider_scale, 1)

        s_row.addWidget(self.lbl_set_scale)

        cv.addLayout(s_row)



        # Offset X slider

        ox_row = QHBoxLayout()

        ox_row.addWidget(QLabel("เลื่อนตำแหน่ง แกน X:"))

        self.lbl_set_ox = QLabel(f"{self.overlay_ox}px")

        self.lbl_set_ox.setStyleSheet("color: #f59e0b; font-weight: bold;")

        self.slider_ox = QSlider(Qt.Horizontal)

        self.slider_ox.setRange(-500, 500)

        self.slider_ox.setValue(self.overlay_ox)

        self.slider_ox.valueChanged.connect(self._on_ox_changed)

        ox_row.addWidget(self.slider_ox, 1)

        ox_row.addWidget(self.lbl_set_ox)

        cv.addLayout(ox_row)



        # Offset Y slider

        oy_row = QHBoxLayout()

        oy_row.addWidget(QLabel("เลื่อนตำแหน่ง แกน Y:"))

        self.lbl_set_oy = QLabel(f"{self.overlay_oy}px")

        self.lbl_set_oy.setStyleSheet("color: #f59e0b; font-weight: bold;")

        self.slider_oy = QSlider(Qt.Horizontal)

        self.slider_oy.setRange(-500, 500)

        self.slider_oy.setValue(self.overlay_oy)

        self.slider_oy.valueChanged.connect(self._on_oy_changed)

        oy_row.addWidget(self.slider_oy, 1)

        oy_row.addWidget(self.lbl_set_oy)

        cv.addLayout(oy_row)



        # Anchor selection

        a_row = QHBoxLayout()

        a_row.addWidget(QLabel("จุดยึดตำแหน่งหน้าจอ:"))

        self.cmb_anchor = QComboBox()

        self._setup_combobox(self.cmb_anchor)

        self.cmb_anchor.addItem("กลางจอ (Center) [ค่าเริ่มต้น]", "center")

        self.cmb_anchor.addItem("บนซ้าย (Top-Left)", "top-left")

        self.cmb_anchor.addItem("บนกลาง (Top-Center)", "top-center")

        self.cmb_anchor.addItem("บนขวา (Top-Right)", "top-right")

        self.cmb_anchor.addItem("กลางซ้าย (Mid-Left)", "mid-left")

        self.cmb_anchor.addItem("กลางขวา (Mid-Right / ข้างจอ)", "mid-right")

        self.cmb_anchor.addItem("ล่างซ้าย (Bottom-Left)", "bottom-left")

        self.cmb_anchor.addItem("ล่างกลาง (Bottom-Center)", "bottom-center")

        self.cmb_anchor.addItem("ล่างขวา (Bottom-Right)", "bottom-right")

        self.cmb_anchor.currentIndexChanged.connect(self._on_anchor_changed)

        a_row.addWidget(self.cmb_anchor, 1)

        cv.addLayout(a_row)



        # Hold duration

        d_row = QHBoxLayout()

        d_row.addWidget(QLabel("แสดงผลค้างไว้ก่อนหาย:"))

        self.cmb_duration = QComboBox()

        self._setup_combobox(self.cmb_duration)

        self.cmb_duration.addItem("3 วินาที", 3)

        self.cmb_duration.addItem("5 วินาที [แนะนำ]", 5)

        self.cmb_duration.addItem("8 วินาที", 8)

        self.cmb_duration.addItem("10 วินาที", 10)

        self.cmb_duration.setCurrentIndex(1)

        self.cmb_duration.currentIndexChanged.connect(self._on_duration_changed)

        self.cmb_duration.activated.connect(self._on_duration_changed)

        d_row.addWidget(self.cmb_duration, 1)

        cv.addLayout(d_row)



        cv.addStretch()



        # Demo button

        btn_demo = QPushButton("👁️ ทดสอบแสดงผลบนจอ OBS (Demo)")

        btn_demo.setStyleSheet(STYLE_BTN_SECONDARY)

        btn_demo.clicked.connect(self._trigger_obs_demo)

        cv.addWidget(btn_demo)



        v.addWidget(card)



    def _on_scale_changed(self, v: int):

        self.overlay_scale = v

        self.lbl_set_scale.setText(f"{v}%")



    def _on_ox_changed(self, v: int):

        self.overlay_ox = v

        self.lbl_set_ox.setText(f"{v:+d}px" if v != 0 else "0px")



    def _on_oy_changed(self, v: int):

        self.overlay_oy = v

        self.lbl_set_oy.setText(f"{v:+d}px" if v != 0 else "0px")



    def _on_anchor_changed(self, idx: int):

        self.overlay_anchor = self.cmb_anchor.currentData()



    def _on_duration_changed(self, idx: int):

        self.overlay_duration = self.cmb_duration.currentData()



    # ── Spin Logic & WebSocket Broadcast ──

    def _start_spin(self):

        items = [inp.text().strip() for inp in self._item_rows if inp.text().strip()]

        if len(items) < 2:

            QMessageBox.warning(self, "แจ้งเตือน", "กรุณากรอกรายการที่จะสุ่มอย่างน้อย 2 รายการครับ")

            return



        winner = random.choice(items)

        self._pending_winner = winner

        self._spin_candidates = list(items)

        title = self.inp_title.text().strip() or "สุ่มกิจกรรม"



        # Start local animation

        self._anim_ticks_left = 25

        self.btn_spin.setEnabled(False)

        self._anim_timer.start()



        # Broadcast On-Demand Dynamic Modal Event to OBS Overlay

        payload = {

            "type": "randomizer_spin",

            "title": title,

            "items": items,

            "winner": winner,

            "settings": {

                "scale": self.overlay_scale,

                "offset_x": self.overlay_ox,

                "offset_y": self.overlay_oy,

                "anchor": self.overlay_anchor,

                "duration": self.overlay_duration

            }

        }

        self._broadcast_to_obs(payload)



    def _on_anim_tick(self):

        if self._anim_ticks_left > 0:

            self._anim_ticks_left -= 1

            cand = random.choice(self._spin_candidates)

            self.lbl_winner_text.setText(f"🎰 {cand}")

            self.box_winner.setVisible(True)

        else:

            self._anim_timer.stop()

            self.btn_spin.setEnabled(True)

            self.lbl_winner_text.setText(f"🏆 {self._pending_winner}")

            self.box_winner.setVisible(True)



    def _trigger_obs_demo(self):

        payload = {

            "type": "randomizer_spin",

            "title": "ตัวอย่างการสุ่ม (Demo)",

            "items": ["ตัวเลือกที่ 1", "ตัวเลือกที่ 2", "ตัวเลือกที่ 3"],

            "winner": "ตัวเลือกที่ 2",

            "settings": {

                "scale": self.overlay_scale,

                "offset_x": self.overlay_ox,

                "offset_y": self.overlay_oy,

                "anchor": self.overlay_anchor,

                "duration": self.overlay_duration

            }

        }

        self._broadcast_to_obs(payload)

        QMessageBox.information(self, "ส่ง Demo แล้ว", "ส่งตัวอย่างการสุ่มลอยขึ้นจอ OBS เรียบร้อยแล้วครับ!")



    def _broadcast_to_obs(self, payload: dict):

        try:

            # Broadcast via composer_server

            if self.parent_app and hasattr(self.parent_app, "composer_server") and self.parent_app.composer_server:

                self.parent_app.composer_server._broadcast_threadsafe(payload)

        except Exception as e:

            logger.error(f"Failed to broadcast randomizer event: {e}")



    def closeEvent(self, event):

        self.closed.emit()

        super().closeEvent(event)

