# -*- coding: utf-8 -*-
"""ask_panel.py — แผงคุม ASK Widget (โพล/แบบสอบถามบน Composer Overlay)

หน้าต่างลอยด้านขวา (เหมือน Event Sidebar) — เปิด/ปิดจากปุ่ม ASK บน TopBar

ส่วนประกอบ:
- คำถาม + ช้อยส์คำตอบ A B C ... (เพิ่มได้ถึง I — กด "+ เพิ่มคำตอบ")
- โหมดคำตอบ: ตัวอักษร A B C หรือ ตัวเลข 1 2 3
- เวลาโหวต: 30 วิ - 1 ชม. หรือไม่จำกัด
- การแสดงผล: เรียลไทม์ หรือ รอจบค่อยสรุป
- เวลาแสดงสรุปผล: N วิ หรือตลอดไปจนกดปิด
- ระหว่างโหวต: สถิติสด + ปุ่ม "จบโหวตทันที" / หลังจบ: ปุ่ม "ปิดผลออกจากจอ"
"""
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QFrame, QLabel, QLineEdit, QPushButton, QVBoxLayout, QHBoxLayout,
    QWidget, QSizePolicy, QRadioButton, QButtonGroup, QSpinBox, QCheckBox,
    QScrollArea, QComboBox, QMessageBox, QProgressBar,
)

LETTERS = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]
MAX_CHOICES = 10


class AskPanel(QFrame):
    """แผงคุม ASK Widget — หน้าต่างลอยด้านขวาของ main window"""

    # ★ signals
    start_requested = Signal(dict)   # poll config (question/choices/mode/...)
    end_requested = Signal()         # จบโหวตทันที
    close_requested = Signal()       # ปิดผลออกจาก Overlay
    # ★ presets — ขอ/บันทึก/ลบ ผ่าน app (เก็บใน settings)
    presets_load_requested = Signal()                    # ขอรายการ preset ล่าสุด
    preset_save_requested = Signal(dict)                 # บันทึก {name, question, choices, answer_mode}
    preset_delete_requested = Signal(str)                # ลบตามชื่อ
    presets_changed = Signal(list)                       # app push รายการใหม่กลับมา

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("AskPanel")
        self.setFrameShape(QFrame.StyledPanel)
        self.setWindowTitle("ASK — โพล/แบบสอบถาม")
        self.setFixedWidth(400)   # ★ 320 → 400 — กันเนื้อหาภายในแสดงไม่ครบ
        self.setStyleSheet("""
            QFrame#AskPanel { background: #131726; border: 1px solid #2a3049; }
            QLabel { color: #e2e8f0; font-size: 12px; background: transparent; border: none; }
            QLabel[hdr="true"] { color: #f59e0b; font-weight: 700; font-size: 13px; }
            QLabel[dim="true"] { color: #64748b; font-size: 11px; }
            QLineEdit { background: #1e293b; color: #e2e8f0; border: 1px solid #334155;
                        border-radius: 6px; padding: 5px 8px; font-size: 12px; }
            QLineEdit:focus { border-color: #7c3aed; }
            QPushButton { background: #7c3aed; color: white; border: none; border-radius: 6px;
                          padding: 7px 14px; font-weight: 600; font-size: 12px; }
            QPushButton:hover { background: #6d28d9; }
            QPushButton:disabled { background: #334155; color: #64748b; }
            QPushButton[danger="true"] { background: #dc2626; }
            QPushButton[danger="true"]:hover { background: #b91c1c; }
            QPushButton[ghost="true"] { background: transparent; border: 1px solid #334155;
                                       color: #94a3b8; padding: 5px 10px; font-weight: 400; }
            QPushButton[ghost="true"]:hover { border-color: #7c3aed; color: #e2e8f0; }
            QRadioButton { color: #cbd5e1; font-size: 12px; background: transparent; }
            QSpinBox { background: #1e293b; color: #e2e8f0; border: 1px solid #334155;
                       border-radius: 6px; padding: 4px 6px; font-size: 12px; }
            QCheckBox { color: #94a3b8; font-size: 12px; background: transparent; }
        """)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(8)

        # ── header ──
        hdr = QLabel("ASK — โพลบน Overlay")
        hdr.setProperty("hdr", True)
        outer.addWidget(hdr)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        body = QWidget()
        self._form = QVBoxLayout(body)
        self._form.setContentsMargins(5, 5, 5, 5)   # ★ padding รอบเนื้อหา กันชิดขอบ
        self._form.setSpacing(8)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        # ── ★ Preset คำถามด่วน (บันทึกชุดคำถามที่ใช้บ่อย เรียกใช้ทันทีไม่ต้องพิมพ์ใหม่) ──
        pr_row = QHBoxLayout()
        pr_row.setSpacing(6)
        self.cmb_preset = QComboBox()
        self.cmb_preset.setMinimumWidth(150)
        self.cmb_preset.setStyleSheet(
            "QComboBox { background:#1e293b;color:#e2e8f0;border:1px solid #334155;"
            "border-radius:6px;padding:5px 8px;font-size:12px; }")
        self.cmb_preset.currentIndexChanged.connect(self._on_preset_selected)
        pr_row.addWidget(self.cmb_preset, 1)
        btn_save_pr = QPushButton("💾")
        btn_save_pr.setProperty("ghost", True)
        btn_save_pr.setFixedSize(34, 30)
        btn_save_pr.setToolTip("บันทึกคำถาม+ช้อยส์ปัจจุบันเป็น Preset")
        btn_save_pr.clicked.connect(self._on_preset_save)
        pr_row.addWidget(btn_save_pr)
        btn_del_pr = QPushButton("🗑")
        btn_del_pr.setProperty("ghost", True)
        btn_del_pr.setFixedSize(34, 30)
        btn_del_pr.setToolTip("ลบ Preset ที่เลือก")
        btn_del_pr.clicked.connect(self._on_preset_delete)
        pr_row.addWidget(btn_del_pr)
        self._form.addLayout(pr_row)

        # ── คำถาม ──
        self._form.addWidget(QLabel("คำถาม:"))
        self.inp_question = QLineEdit()
        self.inp_question.setPlaceholderText("เช่น เลือกเกมที่จะเล่นต่อ")
        self._form.addWidget(self.inp_question)

        # ── ช้อยส์ ──
        ch_hdr = QLabel("ช้อยส์คำตอบ:")
        ch_hdr.setProperty("hdr", True)
        self._form.addWidget(ch_hdr)
        self._choices_host = QVBoxLayout()
        self._choices_host.setSpacing(4)
        self._form.addLayout(self._choices_host)
        self._choice_rows = []
        # ★ placeholder — เริ่มว่าง พิมพ์แทนได้เลย (ข้อ 2)
        self._add_choice_row("")
        self._add_choice_row("")
        self.btn_add_choice = QPushButton("＋ เพิ่มคำตอบ")
        self.btn_add_choice.setProperty("ghost", True)
        self.btn_add_choice.clicked.connect(self._add_default_choice)
        self._form.addWidget(self.btn_add_choice)
        self.lbl_choice_hint = QLabel("")
        self.lbl_choice_hint.setProperty("dim", True)
        self._form.addWidget(self.lbl_choice_hint)

        # ── โหมดคำตอบ ──
        m_hdr = QLabel("วิธีตอบของผู้ชม:")
        m_hdr.setProperty("hdr", True)
        self._form.addWidget(m_hdr)
        self.rb_letters = QRadioButton("พิมพ์ตัวอักษร  A B C")
        self.rb_numbers = QRadioButton("พิมพ์ตัวเลข  1 2 3")
        self.rb_letters.setChecked(True)
        grp = QButtonGroup(self)
        grp.addButton(self.rb_letters)
        grp.addButton(self.rb_numbers)
        self.rb_letters.toggled.connect(lambda _: self._refresh_choice_labels())
        self.rb_numbers.toggled.connect(lambda _: self._refresh_choice_labels())
        self._form.addWidget(self.rb_letters)
        self._form.addWidget(self.rb_numbers)
        hint = QLabel("(นับเฉพาะข้อความที่เป็นตัวอักษร/เลขตัวเดียว — มีคำอื่นปน = ไม่นับ)")
        hint.setProperty("dim", True)
        hint.setWordWrap(True)
        self._form.addWidget(hint)

        # ── เวลาโหวต ──
        # ★ ช่องกรอกตรง ๆ + dropdown หน่วย (วินาที/นาที) แทน QSpinBox
        #   (ลูกศร +/- ของ spinbox เล็กกดยาก กดกลางปุ่มกลายเป็นช่องพิมพ์)
        t_hdr = QLabel("เวลาโหวต:")
        t_hdr.setProperty("hdr", True)
        self._form.addWidget(t_hdr)
        t_row = QHBoxLayout()
        self.ed_vote, self.cmb_vote_unit = self._make_duration_inputs(30)
        t_row.addWidget(self.ed_vote)
        t_row.addWidget(self.cmb_vote_unit)
        self.chk_no_limit = QCheckBox("ไม่จำกัดเวลา")
        self.chk_no_limit.toggled.connect(
            lambda on: (self.ed_vote.setEnabled(not on),
                        self.cmb_vote_unit.setEnabled(not on)))
        t_row.addWidget(self.chk_no_limit)
        t_row.addStretch()
        self._form.addLayout(t_row)

        # ── การแสดงผล ──
        d_hdr = QLabel("การแสดงยอดโหวต:")
        d_hdr.setProperty("hdr", True)
        self._form.addWidget(d_hdr)
        self.rb_realtime = QRadioButton("เรียลไทม์ (เห็นยอดทันทีระหว่างโหวต)")
        self.rb_summary = QRadioButton("รอจบโหวตค่อยแสดงสรุปผล")
        self.rb_realtime.setChecked(True)
        grp2 = QButtonGroup(self)
        grp2.addButton(self.rb_realtime)
        grp2.addButton(self.rb_summary)
        self._form.addWidget(self.rb_realtime)
        self._form.addWidget(self.rb_summary)

        # ── เวลาแสดงสรุปผล ──
        r_hdr = QLabel("แสดงสรุปผล (นับถอยหลังแล้วหายไปเอง):")
        r_hdr.setProperty("hdr", True)
        self._form.addWidget(r_hdr)
        r_row = QHBoxLayout()
        self.ed_result, self.cmb_result_unit = self._make_duration_inputs(20)
        r_row.addWidget(self.ed_result)
        r_row.addWidget(self.cmb_result_unit)
        # ★ default ไม่ติ๊ก = นับถอยหลังแล้วหายเอง / ตลอดไปเป็น optional
        self.chk_forever = QCheckBox("แสดงตลอดไป (กดปิดเอง)")
        self.chk_forever.toggled.connect(
            lambda on: (self.ed_result.setEnabled(not on),
                        self.cmb_result_unit.setEnabled(not on)))
        r_row.addWidget(self.chk_forever)
        r_row.addStretch()
        self._form.addLayout(r_row)

        # ── ปุ่มเริ่ม ──
        self.btn_start = QPushButton("▶ เริ่มโหวต")
        self.btn_start.clicked.connect(self._on_start)
        self._form.addWidget(self.btn_start)

        # ── โซนสถานะ (แสดงตอนโพล active) ──
        self.status_frame = QFrame()
        self.status_frame.setStyleSheet(
            "QFrame { background: #1a1f33; border-radius: 8px; }")
        st = QVBoxLayout(self.status_frame)
        st.setContentsMargins(10, 10, 10, 10)
        st.setSpacing(6)
        self.lbl_state = QLabel("กำลังโหวต")
        self.lbl_state.setProperty("hdr", True)
        st.addWidget(self.lbl_state)
        self.lbl_question_live = QLabel("")
        self.lbl_question_live.setWordWrap(True)
        st.addWidget(self.lbl_question_live)
        # ★ แถวโหวตต่อช้อยส์ — หลอด + จำนวน + % เหมือน overlay (realtime ทุกโหวต)
        self._status_choices_host = QVBoxLayout()
        self._status_choices_host.setSpacing(4)
        st.addLayout(self._status_choices_host)
        self._status_choice_rows = []
        self._status_sorted = False   # ★ จบโหวต → เรียงมาก→น้อย + winner เขียว
        # ★ สรุปยอดรวม + แยกแพลตฟอร์ม (โลโก้ + จำนวน)
        self.lbl_totals = QLabel("👥 โหวตแล้ว 0 คน")
        st.addWidget(self.lbl_totals)
        self._platform_host = QHBoxLayout()
        self._platform_host.setSpacing(8)
        st.addLayout(self._platform_host)
        self.btn_end = QPushButton("⏹ จบโหวตทันที")
        self.btn_end.setProperty("danger", True)
        self.btn_end.clicked.connect(self.end_requested.emit)
        st.addWidget(self.btn_end)
        self.btn_close = QPushButton("✕ ปิดผลออกจาก Overlay")
        self.btn_close.setProperty("ghost", True)
        self.btn_close.clicked.connect(self.close_requested.emit)
        st.addWidget(self.btn_close)
        self.status_frame.setVisible(False)
        self._form.addWidget(self.status_frame)

        # ★ ตัวนับถอยหลังตอนโหวต — ให้เห็นเวลาที่เหลือในกล่องสถานะ
        self._vote_end_ts = None
        self._countdown_timer = QTimer(self)
        self._countdown_timer.setInterval(1000)
        self._countdown_timer.timeout.connect(self._tick_countdown)

        self._form.addStretch()
        self._refresh_choice_labels()

    # ── choices ──────────────────────────────────────────────
    def _add_choice_row(self, text: str = ""):
        if len(self._choice_rows) >= MAX_CHOICES:
            return
        row = QHBoxLayout()
        row.setSpacing(6)
        key_lbl = QLabel()
        key_lbl.setFixedWidth(18)
        inp = QLineEdit()
        inp.setPlaceholderText("คำตอบ...")
        inp.setText(text)
        btn_del = QPushButton("✕")
        btn_del.setProperty("ghost", True)
        btn_del.setFixedSize(30, 26)
        row.addWidget(key_lbl)
        row.addWidget(inp, 1)
        row.addWidget(btn_del)
        self._choices_host.addLayout(row)
        entry = {"layout": row, "key": key_lbl, "inp": inp, "del": btn_del}
        self._choice_rows.append(entry)
        btn_del.clicked.connect(lambda _, e=entry: self._remove_choice(e))
        self._refresh_choice_labels()

    def _add_default_choice(self):
        self._add_choice_row("")

    def _remove_choice(self, entry):
        if len(self._choice_rows) <= 2:
            return  # เหลือขั้นต่ำ 2 ช้อยส์
        entry["layout"].deleteLater()  # layout ไม่มี deleteLater โดยตรง → ลูกๆ ทีละตัว
        for w in (entry["key"], entry["inp"], entry["del"]):
            w.deleteLater()
        self._choice_rows.remove(entry)
        self._refresh_choice_labels()

    def _update_add_btn_state(self):
        """ครบ 10 ช้อยส์ → ปุ่มเพิ่มกลายเป็นแดง ข้อความเตือน / ยังไม่เต็ม → ปกติ"""
        full = len(self._choice_rows) >= MAX_CHOICES
        if full:
            self.btn_add_choice.setText(f"ไม่สามารถเพิ่มได้เกิน {MAX_CHOICES}")
            self.btn_add_choice.setStyleSheet(
                "background:#dc2626;color:#fff;border:none;border-radius:6px;"
                "padding:7px 14px;font-size:12px;font-weight:600;")
        else:
            self.btn_add_choice.setText("＋ เพิ่มคำตอบ")
            self.btn_add_choice.setStyleSheet("")  # กลับไปใช้ ghost style จาก stylesheet หลัก
            self.btn_add_choice.setProperty("ghost", True)

    def _refresh_choice_labels(self):
        # ★ guard — ช่วง __init__ ยังสร้าง choice ก่อน radio โหมดตัวอักษร (default A B C)
        letters = self.rb_letters.isChecked() if hasattr(self, "rb_letters") else True
        for i, entry in enumerate(self._choice_rows):
            entry["key"].setText(LETTERS[i] if letters else str(i + 1))
        left = MAX_CHOICES - len(self._choice_rows)
        if hasattr(self, "lbl_choice_hint"):
            self.lbl_choice_hint.setText(
                f"({len(self._choice_rows)}/{MAX_CHOICES} ช้อยส์"
                + (f" — เพิ่มได้อีก {left}" if left > 0 else " — เต็ม") + ")")
        # ปุ่มลบใช้ไม่ได้เมื่อเหลือ 2
        for entry in self._choice_rows:
            entry["del"].setEnabled(len(self._choice_rows) > 2)
        if hasattr(self, 'btn_add_choice'):
            self._update_add_btn_state()

    # ── actions ──────────────────────────────────────────────
    # ── ★ Preset คำถามด่วน ──
    def set_presets(self, presets):
        """รับรายการ preset จาก app → เติม dropdown (ไม่แตะการเลือกปัจจุบันถ้าเป็นไปได้)"""
        cur = self.cmb_preset.currentText()
        self.cmb_preset.blockSignals(True)
        self.cmb_preset.clear()
        self.cmb_preset.addItem("⚡ เรียกใช้ Preset...", "")
        for pr in (presets or []):
            name = (pr or {}).get("name", "?")
            self.cmb_preset.addItem(name, pr)
        # คงเลือกเดิมถ้ายังมี
        idx = self.cmb_preset.findText(cur) if cur else -1
        if idx > 0:
            self.cmb_preset.setCurrentIndex(idx)
        elif self.cmb_preset.currentIndex() != 0:
            self.cmb_preset.setCurrentIndex(0)
        self.cmb_preset.blockSignals(False)

    def _on_preset_selected(self, idx):
        """เลือก preset → เติมคำถาม+ช้อยส์+โหมดเข้าฟอร์มทันที"""
        if idx <= 0:
            return
        pr = self.cmb_preset.itemData(idx)
        if not pr:
            return
        self.inp_question.setText(pr.get("question", ""))
        choices = pr.get("choices", [])
        # เคลียร์ rows เดิม → เติมตาม preset
        while self._choice_rows:
            entry = self._choice_rows.pop()
            for w in (entry["key"], entry["inp"], entry["del"]):
                w.deleteLater()
            entry["layout"].deleteLater() if hasattr(entry["layout"], "deleteLater") else None
        for c in choices:
            self._add_choice_row(str(c))
        while len(self._choice_rows) < 2:
            self._add_choice_row("")
        if pr.get("answer_mode") == "numbers":
            self.rb_numbers.setChecked(True)
        else:
            self.rb_letters.setChecked(True)
        self._refresh_choice_labels()

    def _on_preset_save(self):
        """บันทึกปัจจุบันเป็น preset — ★ใช้ inline name field (ไม่ใช้ QMessageBox ที่อาจ
        โผล่หลัง main window บน QFrame ลูก) + toast แจ้ง 2 วิ"""
        question = self.inp_question.text().strip()
        choices = [e["inp"].text().strip() for e in self._choice_rows if e["inp"].text().strip()]
        if not question or len(choices) < 2:
            self._show_toast("⚠ ต้องมีคำถาม + คำตอบอย่างน้อย 2 ข้อ")
            return
        # ★ inline name — ใช้ชื่อ preset จากช่องถัดจาก dropdown (สร้างครั้งเดียว)
        if not hasattr(self, '_preset_name_inp'):
            from PySide6.QtCore import QTimer as _QT
            self._preset_name_inp = QLineEdit()
            self._preset_name_inp.setPlaceholderText("ชื่อ preset...")
            self._preset_name_inp.setStyleSheet(
                "background:#1e293b;color:#e2e8f0;border:1px solid #334155;"
                "border-radius:6px;padding:4px 8px;font-size:12px;")
            # แทรกใต้แถว preset dropdown
            self._form.insertWidget(self._form.indexOf(self.cmb_preset.parent()) + 1
                                    if self.cmb_preset.parent() else 3, self._preset_name_inp)
        name = self._preset_name_inp.text().strip() or question[:30]
        self.preset_save_requested.emit({
            "name": name,
            "question": question,
            "choices": choices,
            "answer_mode": "letters" if self.rb_letters.isChecked() else "numbers",
        })
        self._show_toast(f"💾 บันทึก '{name}' เรียบร้อย")

    def _show_toast(self, text: str):
        """toast แจ้งผล 2 วิ ด้านล่างสุดของแผง"""
        from PySide6.QtCore import Qt as _Qt, QTimer as _QT
        if hasattr(self, '_toast_lbl'):
            self._toast_lbl.deleteLater()
        self._toast_lbl = QLabel(text)
        self._toast_lbl.setAlignment(_Qt.AlignCenter)
        self._toast_lbl.setStyleSheet(
            "background:#059669;color:#fff;border-radius:6px;padding:6px;"
            "font-size:12px;font-weight:600;")
        self.layout().addWidget(self._toast_lbl)
        _QT.singleShot(2000, lambda: (
            self._toast_lbl.deleteLater(),
            setattr(self, '_toast_lbl', None),
        ) if hasattr(self, '_toast_lbl') else None)

    def _on_preset_delete(self):
        """ลบ preset ที่เลือก"""
        idx = self.cmb_preset.currentIndex()
        if idx <= 0:
            return
        name = self.cmb_preset.itemText(idx)
        if QMessageBox.question(self, "ลบ Preset", f'ลบ "{name}" ?') == QMessageBox.Yes:
            self.preset_delete_requested.emit(name)

    # ── ★ ช่องกรอกเวลา + หน่วย (วินาที/นาที) — แทน QSpinBox ที่ลูกศร +/- กดยาก ──
    def _make_duration_inputs(self, default_sec: int):
        """สร้าง (QLineEdit ตัวเลข, QComboBox หน่วย) — default เป็นวินาที"""
        from PySide6.QtGui import QIntValidator
        from PySide6.QtCore import Qt
        ed = QLineEdit(str(default_sec))
        ed.setValidator(QIntValidator(1, 9999))
        ed.setFixedWidth(70)
        ed.setAlignment(Qt.AlignCenter)
        ed.setStyleSheet(
            "QLineEdit { background: #1e293b; color: #e2e8f0; border: 1px solid #334155;"
            "border-radius: 6px; padding: 4px 6px; font-size: 12px; }")
        cmb = QComboBox()
        cmb.addItems(["วินาที", "นาที"])
        cmb.setFixedWidth(80)
        cmb.setStyleSheet(
            "QComboBox { background:#1e293b;color:#e2e8f0;border:1px solid #334155;"
            "border-radius:6px;padding:4px 8px;font-size:12px; }")
        # ★ สลับหน่วย → แปลงค่าให้อัตโนมัติ (30 วิ → 1 นาที / 2 นาที → 120 วิ)
        #   กันเผลอ: ตั้ง 30 ไว้แล้วสลับเป็นนาทีโดยไม่ดู = กลายเป็น 30 นาที
        def _on_unit(idx):
            try:
                v = max(1, int(ed.text() or "0"))
                if idx == 1:   # → นาที
                    ed.setText(str(max(1, round(v / 60))))
                else:          # → วินาที
                    ed.setText(str(min(3600, v * 60)))
            except Exception:
                pass
        cmb.currentIndexChanged.connect(_on_unit)
        return ed, cmb

    def _duration_seconds(self, ed, cmb) -> int:
        """อ่านค่าจากช่องกรอก + หน่วย → วินาที (clamp 5-3600 / ผิดรูป = ต่ำสุด)"""
        try:
            v = int(ed.text() or "0")
        except ValueError:
            v = 1
        if cmb.currentIndex() == 1:
            v *= 60
        return max(5, min(3600, v))

    def _on_start(self):
        from PySide6.QtCore import QTimer
        question = self.inp_question.text().strip()
        choices = []
        for entry in self._choice_rows:
            t = entry["inp"].text().strip()
            if t:
                choices.append(t)
        if not question or len(choices) < 2:
            # เตือนสั้น ๆ แล้วซ่อนเอง (กัน status_frame ค้างเป็นข้อความเตือน)
            self.status_frame.setVisible(True)
            self.btn_end.setVisible(False)
            self.btn_close.setVisible(False)
            self.lbl_question_live.setText("")
            self.lbl_totals.setText("")
            self._rebuild_status_choices({"choices": []}, False)
            while self._platform_host.count():
                item = self._platform_host.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            self.lbl_state.setText("⚠ ต้องมีคำถาม + คำตอบอย่างน้อย 2 ข้อ")
            QTimer.singleShot(2500, self.show_idle)
            return
        self.start_requested.emit({
            "question": question,
            "choices": choices,
            "answer_mode": "letters" if self.rb_letters.isChecked() else "numbers",
            "duration_sec": None if self.chk_no_limit.isChecked()
                else self._duration_seconds(self.ed_vote, self.cmb_vote_unit),
            "realtime": self.rb_realtime.isChecked(),
            "results_duration_sec": None if self.chk_forever.isChecked()
                else self._duration_seconds(self.ed_result, self.cmb_result_unit),
        })

    # ── live status (เรียกจาก app) ───────────────────────────
    def show_voting(self, payload: dict):
        """แสดงโซนสถานะ — กำลังโหวต (มีเวลานับถอยหลัง)"""
        self.status_frame.setVisible(True)
        self.btn_start.setEnabled(False)
        self.btn_end.setVisible(True)
        self.btn_close.setVisible(False)
        self.lbl_question_live.setText(payload.get("question", ""))
        # ★ นับถอยหลัง — มี end_ts (จำกัดเวลา) → ติ๊กทุกวิ / ไม่จำกัด → ข้อความนิ่ง
        end_ts = payload.get("end_ts")
        if end_ts:
            self._vote_end_ts = float(end_ts)
            # ★ start ก่อนแล้วค่อย tick — เคสหมดเวลาแล้ว tick จะ stop ให้ทันที
            self._countdown_timer.start()
            self._tick_countdown()
        else:
            self._vote_end_ts = None
            self._countdown_timer.stop()
            self.lbl_state.setText("🗳 กำลังโหวต... (ไม่จำกัดเวลา)")
        self.update_live_counts(payload)

    def _tick_countdown(self):
        """อัปเดตเวลาที่เหลือใน lbl_state ทุก 1 วิ"""
        import time as _t
        if not self._vote_end_ts:
            return
        left = self._vote_end_ts - _t.time()
        if left <= 0:
            self.lbl_state.setText("🗳 กำลังโหวต... ⏳ กำลังปิดโหวต...")
            self._countdown_timer.stop()
            return
        m, s = divmod(int(left + 0.999), 60)
        txt = f"🗳 กำลังโหวต... ⏳ เหลืออีก {m}:{s:02d}"
        if left <= 10:
            txt += " ⚠"   # ใกล้หมดเวลา
        self.lbl_state.setText(txt)

    def show_ended(self, payload: dict):
        """แสดงโซนสถานะ — จบแล้ว (แสดงผล)"""
        self._countdown_timer.stop()
        self._vote_end_ts = None
        self.status_frame.setVisible(True)
        self.btn_start.setEnabled(False)
        self.btn_end.setVisible(False)
        self.btn_close.setVisible(True)
        self.lbl_state.setText("📊 จบโหวตแล้ว — แสดงสรุปผล")
        self.lbl_question_live.setText(payload.get("question", ""))
        self.update_live_counts(payload)

    def show_idle(self):
        """กลับสู่สถานะพร้อมเริ่มโพลใหม่"""
        self._countdown_timer.stop()
        self._vote_end_ts = None
        self.status_frame.setVisible(False)
        self.btn_start.setEnabled(True)

    # ── ★ โซนสถานะโหวต — แถวช้อยส์ + หลอด + แพลตฟอร์ม ──
    def _add_status_choice_row(self):
        """สร้างแถว [key] [ช้อยส์] [หลอด] [จำนวน + %] หนึ่งแถว"""
        row = QHBoxLayout()
        row.setSpacing(6)
        key = QLabel()
        key.setFixedWidth(16)
        key.setStyleSheet("color:#f59f0b; font-weight:700; font-size:12px; background:transparent; border:none;")
        text = QLabel()
        text.setFixedWidth(105)
        text.setStyleSheet("color:#cbd5e1; font-size:12px; background:transparent; border:none;")
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setFixedHeight(9)
        bar.setTextVisible(False)
        bar.setStyleSheet(
            "QProgressBar { background:#0f1526; border:none; border-radius:4px; }"
            "QProgressBar::chunk { background:#7c3aed; border-radius:4px; }")
        cnt = QLabel()
        cnt.setFixedWidth(64)
        cnt.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        cnt.setStyleSheet("color:#e2e8f0; font-size:11px; background:transparent; border:none;")
        row.addWidget(key)
        row.addWidget(text)
        row.addWidget(bar, 1)
        row.addWidget(cnt)
        self._status_choices_host.addLayout(row)
        self._status_choice_rows.append(
            {"layout": row, "key": key, "text": text, "bar": bar, "cnt": cnt})

    def _rebuild_status_choices(self, payload: dict, ended: bool):
        """สร้างแถวช้อยส์ใหม่ทั้งชุด (ตอนเริ่มโพล / เปลี่ยนเฟสจบ → เรียงมาก→น้อย)"""
        # ล้างแถวเดิม
        for r in self._status_choice_rows:
            try:
                self._status_choices_host.removeItem(r["layout"])
                for w in (r["key"], r["text"], r["bar"], r["cnt"]):
                    w.deleteLater()
            except Exception:
                pass
        self._status_choice_rows = []
        self._status_sorted = ended
        choices = payload.get("choices", [])
        for _ in choices:
            self._add_status_choice_row()

    def update_live_counts(self, payload: dict):
        """อัปเดตผลโหวตสด — หลอดต่อช้อยส์ + ยอดรวม + แยกแพลตฟอร์ม (realtime ทุกโหวต)"""
        total = payload.get("total_voters", 0)
        self.lbl_totals.setText(f"👥 โหวตแล้ว {total} คน")
        counts = payload.get("counts", [])
        keys = payload.get("keys", [])
        choices = payload.get("choices", [])
        ended = payload.get("phase") == "ended"
        # ★ จบโหวต → เรียงมาก→น้อย (winner อันดับ 1) / กำลังโหวต → ลำดับเดิม
        if len(self._status_choice_rows) != len(choices) or self._status_sorted != ended:
            self._rebuild_status_choices(payload, ended)
        order = list(range(len(choices)))
        if ended:
            order.sort(key=lambda i: -(counts[i] if i < len(counts) else 0))
        maxc = 1
        if counts:
            maxc = max(1, max(counts))
        for r, i in enumerate(order):
            row = self._status_choice_rows[r]
            k = keys[i] if i < len(keys) else "?"
            label = choices[i] if i < len(choices) else ""
            c = counts[i] if i < len(counts) else 0
            pct = round(c * 100 / total) if total else 0
            row["key"].setText(k)
            row["text"].setText(label)
            row["text"].setToolTip(label)
            row["bar"].setValue(int(c * 100 / maxc))
            row["cnt"].setText(f"{c} ({pct}%)")
            # ★ จบแล้ว — อันดับ 1 สีเขียว (เหมือน overlay)
            color = "#34d399" if (ended and r == 0 and c > 0) else "#f59f0b"
            row["key"].setStyleSheet(
                f"color:{color}; font-weight:700; font-size:12px; background:transparent; border:none;")
            row["cnt"].setStyleSheet(
                ("color:#34d399; font-weight:600;" if (ended and r == 0 and c > 0)
                 else "color:#e2e8f0;") +
                " font-size:11px; background:transparent; border:none;")
        # ★ แถวแพลตฟอร์ม — โลโก้ + จำนวน (rebuild ทุกครั้ง — แถวสั้น ไม่หนัก)
        self._update_platform_row(payload.get("per_platform", {}), total)

    def _update_platform_row(self, per_platform: dict, total: int):
        """แสดงยอดต่อแพลตฟอร์มเป็นโลโก้ + จำนวน (เฉพาะที่มีคนโหวต)"""
        while self._platform_host.count():
            item = self._platform_host.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        if not per_platform or total <= 0:
            lbl = QLabel("ยังไม่มีผู้โหวต")
            lbl.setProperty("dim", True)
            lbl.setStyleSheet("color:#64748b; font-size:11px; background:transparent; border:none;")
            self._platform_host.addWidget(lbl)
            self._platform_host.addStretch()
            return
        from ui.platform_icons import get_platform_pixmap
        order = ["twitch", "youtube", "mylive", "kick", "tiktok"]
        names = {"twitch": "Twitch", "youtube": "YouTube", "mylive": "MyLive",
                 "kick": "KICK", "tiktok": "TikTok"}
        plats = [p for p in order if per_platform.get(p, 0) > 0]
        plats += sorted(set(per_platform) - set(order))
        for p in plats:
            n = per_platform.get(p, 0)
            if n <= 0:
                continue
            icon = QLabel()
            pix = get_platform_pixmap(p, 14)
            if not pix.isNull():
                icon.setPixmap(pix)
            else:
                icon.setText(names.get(p, str(p).capitalize()))
                icon.setStyleSheet("color:#94a3b8; font-size:11px; background:transparent; border:none;")
            cnt = QLabel(f"{n}")
            cnt.setStyleSheet("color:#cbd5e1; font-size:11px; background:transparent; border:none;")
            self._platform_host.addWidget(icon)
            self._platform_host.addWidget(cnt)
        self._platform_host.addStretch()
