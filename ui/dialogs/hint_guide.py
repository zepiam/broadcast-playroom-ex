"""hint_guide.py — คลังคำสั่งสำหรับคนดู (Viewer Commands & Hint Guide)

รวบรวมคำสั่งทั้งหมดที่คนดูสามารถพิมพ์ในแชทได้ พร้อมคำอธิบาย ตัวอย่าง และปุ่มคัดลอก
เพื่อให้สตรีมเมอร์นำไปบอกต่อคนดูในแชทบอท / Discord / คำอธิบายใต้คลิป
★ รองรับ dynamic commands: มินิเกม Playroom และ โค้ดลับเสียง จะดึงจากค่าที่ตั้งไว้จริงในโปรแกรม
  (ถ้าไม่มีการตั้งค่าไว้ จะไม่แสดงในตารางเลย)
"""
import os
import logging
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QPushButton, QLineEdit, QVBoxLayout,
    QHBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QApplication,
)
from ui.theme import COLOR_BG, COLOR_CARD, COLOR_BORDER, COLOR_TEXT, COLOR_ACCENT

logger = logging.getLogger("hint_guide")

# ══════════════════════════════════════════════════════════════════════
# คำสั่งพื้นฐานของระบบ (Base System Commands)
# ══════════════════════════════════════════════════════════════════════
BASE_HINT_COMMANDS = [
    # ── 1. Danmaku Colors ──
    {
        "category": "danmaku",
        "category_label": "🎨 สี Danmaku",
        "command": "}red{, }blue{, }green{",
        "example": "}red{สวัสดีครับ",
        "description": "เปลี่ยนสีข้อความตัววิ่งบนหน้าจอสตรีม (Danmaku Text)\nสีที่รองรับ: red, blue, green, yellow, purple, pink, orange, cyan, white, black, gray",
    },
    {
        "category": "danmaku",
        "category_label": "🎨 สี Danmaku",
        "command": "}rainbow{",
        "example": "}rainbow{ยินดีด้วยครับ!",
        "description": "ข้อความตัววิ่งสีรุ้งแอนิเมชั่น (Rainbow Gradient Animated)\nตัวอักษรจะไล่เฉดสีรุ้งขยับตลอดเวลา",
    },
    # ── 2. TTS Controls ──
    {
        "category": "tts",
        "category_label": "⚡ Speed & Pitch",
        "command": "[x1.5], [x2], [x0.8]",
        "example": "[x2] พูดเร็วติดสปีด",
        "description": "เร่ง/ลดความเร็วการอ่าน TTS ชั่วคราว (0.1x ถึง 2.0x)\nใส่ที่ต้นข้อความ ระบบจะตัดแท็กออกก่อนอ่าน",
    },
    {
        "category": "tts",
        "category_label": "⚡ Speed & Pitch",
        "command": "[p1] ถึง [p10], [p-1] ถึง [p-10]",
        "example": "[p2] เสียงสูงจัง / [p-2] เสียงทุ้ม",
        "description": "ปรับคีย์เสียง TTS: [p1] ถึง [p10] = เสียงแหลมสูงขึ้น\n[p-1] ถึง [p-10] = เสียงทุ้มต่ำลง",
    },
    {
        "category": "tts",
        "category_label": "⚡ Speed & Pitch",
        "command": "[v50], [v80], [v120]",
        "example": "[v50] ข้อความนี้ขอเบาๆ",
        "description": "ปรับระดับความดังของเสียง TTS ในข้อความนั้นๆ\n([v100] = ดังปกติ, [v50] = เบาลงครึ่งหนึ่ง)",
    },
    {
        "category": "tts",
        "category_label": "⚡ Speed & Pitch",
        "command": "[x2][p2] (รวมคำสั่ง)",
        "example": "[x2][p2] พูดเร็วและเสียงแหลม",
        "description": "ผสมคำสั่งความเร็วและโทนเสียงเข้าด้วยกันที่ต้นประโยคได้",
    },
    # ── 3. Voice Selection ──
    {
        "category": "voice",
        "category_label": "🎙️ เสียงประจำตัว",
        "command": "-voiceman, !voiceman",
        "example": "-voiceman สวัสดีครับ",
        "description": "เลือกใช้เสียงชาย (นิวัฒน์ - Niwat) เป็นเสียงประจำตัวถาวร\nระบบจะจำชื่อไว้ ข้อความถัดไปทั้งหมดจะใช้เสียงนี้ทันทีโดยไม่ต้องพิมพ์ซ้ำ\n(รองรับ: -voiceman, !voiceman, -voiceboy, -man)",
    },
    {
        "category": "voice",
        "category_label": "🎙️ เสียงประจำตัว",
        "command": "-voicegirl, !voicegirl",
        "example": "-voicegirl สวัสดีค่ะ",
        "description": "เลือกใช้เสียงหญิง (เปรมวดี - Premwadee) เป็นเสียงประจำตัวถาวร\nระบบจะจำชื่อไว้ ข้อความถัดไปทั้งหมดจะใช้เสียงนี้ทันทีโดยไม่ต้องพิมพ์ซ้ำ\n(รองรับ: -voicegirl, !voicegirl, -voicewoman, -girl)",
    },
    {
        "category": "voice",
        "category_label": "🎙️ เสียงประจำตัว",
        "command": "-voicereset, !voicereset",
        "example": "-voicereset",
        "description": "รีเซ็ตเสียงประจำตัว กลับไปใช้เสียงตามระบบของสตรีมเมอร์\n(รองรับ: -voicereset, !voicereset, -reset)",
    },
    # ── 4. Clip Marker ──
    {
        "category": "clip",
        "category_label": "⭐ มาร์กคลิป",
        "command": "!clip, !mark, -clip, -mark",
        "example": "!clip จังหวะยิงสวยมาก",
        "description": "บันทึกเวลาสตรีม (HH:MM:SS) ลงไฟล์ data/clip_markers.txt\nช่วยให้สตรีมเมอร์รู้เวลาที่เกิดช็อตเด็ดเพื่อนำไปตัดต่อไฮไลต์ได้แม่นยำ",
    },
    # ── 5. Poll & Vote ──
    {
        "category": "vote",
        "category_label": "🗳️ โหวต (ASK)",
        "command": "A, B, C, D หรือ 1, 2, 3, 4",
        "example": "A หรือ 1",
        "description": "โหวตคำตอบเมื่อสตรีมเมอร์เปิดโพลบนหน้าจอ (ระบบจะนับคะแนนอัตโนมัติและไม่อ่าน TTS)",
    },
]


def get_hint_commands(settings=None) -> list[dict]:
    """สร้างรายการคำสั่งทั้งหมดตามการตั้งค่าจริง (live settings)

    ★ กฎสำคัญ:
    - คำสั่งเสียง (Secret Codes): แสดงเฉพาะโค้ดที่สตรีมเมอร์ตั้งไว้ในโปรแกรมจริงๆ เท่านั้น (ถ้าไม่มี ไม่แสดงเลย)
    - Playroom Triggers: แสดงเฉพาะโค้ดที่ตั้งไว้จริงและเปิดใช้งานเท่านั้น (ถ้าไม่มี ไม่แสดงเลย)
    - Character Jobs: แสดงเฉพาะชื่อ Job ที่ตั้งไว้ในโปรแกรมจริงเท่านั้น
    """
    commands = list(BASE_HINT_COMMANDS)

    if not settings:
        return commands

    # ── 6. โค้ดเสียงลับ (Secret Sound Codes) ──
    # แสดงเฉพาะที่มีการตั้งค่าไว้จริงในโปรแกรม
    secret_codes = getattr(settings, "secret_codes", [])
    if isinstance(secret_codes, list):
        limit = getattr(settings, "secret_code_daily_limit", 0)
        limit_desc = f" (จำกัด {limit} ครั้ง/คน/วัน)" if limit > 0 else " (ไม่จำกัดครั้ง)"
        muted_desc = " [⚠️ ปิดเสียงชั่วคราว]" if getattr(settings, "code_sound_muted", False) else ""

        for sc in secret_codes:
            if not isinstance(sc, dict):
                continue
            code_str = sc.get("code", "").strip()
            sound_path = sc.get("sound_path", "").strip()
            if not code_str:
                continue
            sound_name = os.path.basename(sound_path) if sound_path else "ไฟล์เสียง"
            vol = int(sc.get("volume", 1.0) * 100)
            commands.append({
                "category": "sound",
                "category_label": "🎵 โค้ดเสียง",
                "command": code_str,
                "example": code_str,
                "description": f"เล่นเสียงเอฟเฟกต์ '{sound_name}' (ระดับเสียง {vol}%){limit_desc}{muted_desc}",
            })

    # ── 7. Playroom Video Triggers ──
    # แสดงเฉพาะเมื่อเปิดใช้งาน Playroom และมีการตั้งค่า Trigger ไว้จริง
    playroom_enabled = getattr(settings, "playroom_enabled", False)
    playroom_triggers = getattr(settings, "playroom_triggers", [])
    if playroom_enabled and isinstance(playroom_triggers, list):
        for trig in playroom_triggers:
            if not isinstance(trig, dict):
                continue
            code_str = trig.get("code", "").strip()
            if not code_str:
                continue
            daily_limit = int(trig.get("daily_limit", 0))
            limit_desc = f"จำกัด {daily_limit} ครั้ง/คน/วัน" if daily_limit > 0 else "ไม่จำกัดครั้ง"
            clips = trig.get("clips", [])
            clip_count = len(clips) if isinstance(clips, list) else 0
            clip_desc = f"สุ่ม {clip_count} วิดีโอ" if clip_count > 0 else "วิดีโออนิเมชั่น"
            commands.append({
                "category": "playroom",
                "category_label": "🎮 มินิเกม (Playroom)",
                "command": code_str,
                "example": code_str,
                "description": f"สุ่มเปิดคลิปวิดีโออนิเมชั่นบนหน้าจอ ({clip_desc}, {limit_desc})",
            })

    # ── 8. Character Talk (Job Change) ──
    # แสดงเฉพาะเมื่อมีการตั้งค่า Job ในโปรแกรม
    char_jobs = getattr(settings, "character_jobs", [])
    if isinstance(char_jobs, list):
        valid_jobs = []
        for cj in char_jobs:
            if isinstance(cj, dict):
                jname = cj.get("name", "").strip()
                if jname and jname.lower() != "default":
                    valid_jobs.append(jname)
        if valid_jobs:
            for jname in valid_jobs:
                commands.append({
                    "category": "character",
                    "category_label": "🎭 ตัวละคร",
                    "command": f"{{jobchange:{jname}}}",
                    "example": f"{{jobchange:{jname}}}",
                    "description": f"สลับอวาตาร์ตัวละครบนหน้าจอสตรีมเป็น '{jname}'",
                })
            commands.append({
                "category": "character",
                "category_label": "🎭 ตัวละคร",
                "command": "{jobchange:reset}",
                "example": "{jobchange:reset}",
                "description": "รีเซ็ตอวาตาร์ตัวละครกลับเป็นภาพเริ่มต้น",
            })

    return commands


def generate_copy_all_text(commands: list[dict]) -> str:
    """สร้างข้อความสรุปคำสั่งทั้งหมดตามรายการที่มีอยู่จริง เพื่อนำไปแจกคนดู"""
    lines = [
        "📢 รวมคำสั่งสำหรับคนดู (Viewer Commands Guide)",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    grouped = {}
    for item in commands:
        grouped.setdefault(item["category"], []).append(item)

    order = [
        ("danmaku", "🎨 เปลี่ยนสีข้อความตัววิ่ง (Danmaku)"),
        ("tts", "⚡ ปรับสปีด & โทนเสียง TTS"),
        ("voice", "🎙️ เลือกเสียงประจำตัวคนดู (ระบบจำถาวร)"),
        ("clip", "⭐ มาร์กช็อตเด็ด (Clip Marker)"),
        ("sound", "🎵 โค้ดเสียงเอฟเฟกต์ (Secret Sounds)"),
        ("playroom", "🎮 มินิเกมบนจอ (Playroom Triggers)"),
        ("character", "🎭 สลับตัวละครบนหน้าจอ (Character)"),
        ("vote", "🗳️ คำสั่งโหวต (Poll / Vote)"),
    ]

    for cat_key, cat_title in order:
        if cat_key in grouped:
            lines.append(f"{cat_title}:")
            for item in grouped[cat_key]:
                lines.append(f"• {item['command']} -> ตัวอย่าง: {item['example']}")
            lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines).strip()


class HintSectionWidget(QWidget):
    """Widget สำหรับหน้า Hint — ตารางคำสั่งคนดู + ค้นหา + ปุ่มคัดลอก

    รองรับการอัพเดทข้อมูลตาม settings จริงแบบ Dynamic (refresh ได้เมื่อมีการแก้ไข)
    """

    def __init__(self, parent_dialog=None, settings=None):
        super().__init__(parent_dialog)
        self.parent_dialog = parent_dialog
        self.settings = settings
        self._current_filter_cat = "all"
        self._commands = get_hint_commands(self.settings)
        self.btn_cats = {}

        self._build_ui()
        self._rebuild_category_buttons()
        self._render_table()

    def refresh(self, settings=None):
        """รีเฟรชคำสั่งในตารางใหม่ตามการตั้งค่าล่าสุด"""
        if settings is not None:
            self.settings = settings
        self._commands = get_hint_commands(self.settings)
        self._rebuild_category_buttons()
        self._render_table()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # ── Card ด้านบน: ข้อมูล + ปุ่ม Copy สรุปทั้งหมด ──
        top_card = QFrame()
        top_card.setStyleSheet(
            "QFrame { background-color: #0e1726; border: 1px solid #1e293b; border-radius: 8px; }"
        )
        tcl = QVBoxLayout(top_card)
        tcl.setContentsMargins(14, 12, 14, 12)
        tcl.setSpacing(8)

        th = QHBoxLayout()
        th.setSpacing(10)
        desc_lbl = QLabel(
            "💡 ตารางสรุปคำสั่งที่คนดูสามารถพิมพ์ในแชทได้ (Danmaku สี, สปีดอ่าน, เลือกเสียง, มาร์กคลิป, มินิเกม)\n"
            "สตรีมเมอร์สามารถคลิกปุ่มด้านขวาเพื่อคัดลอกสรุปคำสั่งไปโพสต์ใน Discord, แชทบอท หรือใต้คลิปได้ทันที"
        )
        desc_lbl.setStyleSheet("color: #94a3b8; font-size: 12px; line-height: 1.4;")
        desc_lbl.setWordWrap(True)
        th.addWidget(desc_lbl, 1)

        self.btn_copy_all = QPushButton("📋 คัดลอกสรุปคำสั่งทั้งหมด")
        self.btn_copy_all.setFixedHeight(34)
        self.btn_copy_all.setCursor(Qt.PointingHandCursor)
        self.btn_copy_all.setToolTip("คัดลอกสรุปคำสั่งทั้งหมดลงคลิปบอร์ด เพื่อนำไปใส่ในแชทบอทหรือหน้าสตรีม")
        self.btn_copy_all.setStyleSheet(
            "QPushButton { background: #0c2135; color: #38bdf8; border: 1px solid #0284c7; "
            "border-radius: 6px; padding: 0 16px; font-size: 13px; font-weight: 700; }"
            "QPushButton:hover { background: #0e3052; border-color: #38bdf8; color: #e0f2fe; }"
            "QPushButton:pressed { background: #075985; }"
        )
        self.btn_copy_all.clicked.connect(self._copy_all_commands)
        th.addWidget(self.btn_copy_all)
        tcl.addLayout(th)

        self.status_feedback = QLabel("")
        self.status_feedback.setStyleSheet("color: #10b981; font-size: 12px; font-weight: 600;")
        self.status_feedback.setVisible(False)
        tcl.addWidget(self.status_feedback)
        layout.addWidget(top_card)

        # ── Toolbar: หมวดหมู่ + ช่องค้นหา ──
        tb_row = QHBoxLayout()
        tb_row.setSpacing(8)

        # Layout ย่อยสำหรับปุ่มหมวดหมู่ (จะถูกสร้างใหม่ตาม category ที่มีจริง)
        self.cat_btn_layout = QHBoxLayout()
        self.cat_btn_layout.setSpacing(6)
        tb_row.addLayout(self.cat_btn_layout)

        tb_row.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 ค้นหาคำสั่ง / ฟังก์ชั่น...")
        self.search_input.setFixedHeight(30)
        self.search_input.setFixedWidth(220)
        self.search_input.setStyleSheet(
            "QLineEdit { background: #131d31; color: #f8fafc; border: 1.5px solid #283548; "
            "border-radius: 6px; padding: 0 10px; font-size: 12.5px; }"
            "QLineEdit:focus { border-color: #38bdf8; background: #16243d; }"
        )
        self.search_input.textChanged.connect(self._on_search_changed)
        tb_row.addWidget(self.search_input)
        layout.addLayout(tb_row)

        # ── ตารางแสดงคำสั่ง ──
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([
            "หมวดหมู่", "คำสั่ง (Command)", "ตัวอย่างพิมพ์", "คำอธิบายและรายละเอียด", "คัดลอก"
        ])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.Stretch)
        hh.setSectionResizeMode(4, QHeaderView.Fixed)
        self.table.setColumnWidth(4, 70)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setWordWrap(True)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #0e1726;
                border: 1px solid #1e293b;
                border-radius: 6px;
                gridline-color: #1e293b;
                color: #e2e8f0;
            }
            QTableWidget::item {
                padding: 8px 10px;
                border-bottom: 1px solid #1e293b;
            }
            QHeaderView::section {
                background-color: #131d31;
                color: #38bdf8;
                padding: 8px;
                border: none;
                border-bottom: 1px solid #1e293b;
                font-weight: 700;
                font-size: 12.5px;
            }
        """)
        layout.addWidget(self.table, 1)

    def _rebuild_category_buttons(self):
        """สร้างปุ่มหมวดหมู่ใหม่ โดยแสดงเฉพาะหมวดที่มีคำสั่งอยู่จริงเท่านั้น"""
        while self.cat_btn_layout.count():
            item = self.cat_btn_layout.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        self.btn_cats.clear()

        present_cats = {item["category"] for item in self._commands}
        cat_defs = [("all", "🌐 ทั้งหมด")]
        all_possible = [
            ("danmaku", "🎨 สี Danmaku"),
            ("tts", "⚡ Speed & Pitch"),
            ("voice", "🎙️ เสียงประจำตัว"),
            ("clip", "⭐ มาร์กคลิป"),
            ("sound", "🎵 โค้ดเสียง"),
            ("playroom", "🎮 มินิเกม"),
            ("character", "🎭 ตัวละคร"),
            ("vote", "🗳️ โหวต"),
        ]
        for c_key, c_label in all_possible:
            if c_key in present_cats:
                cat_defs.append((c_key, c_label))

        available_keys = {c[0] for c in cat_defs}
        if self._current_filter_cat not in available_keys:
            self._current_filter_cat = "all"

        for c_key, c_name in cat_defs:
            b = QPushButton(c_name)
            b.setFixedHeight(28)
            b.setCursor(Qt.PointingHandCursor)
            is_sel = (c_key == self._current_filter_cat)
            self._update_cat_btn_style(b, is_sel)
            b.clicked.connect(lambda _, k=c_key: self._set_category_filter(k))
            self.btn_cats[c_key] = b
            self.cat_btn_layout.addWidget(b)

    def _update_cat_btn_style(self, btn, is_selected):
        if is_selected:
            btn.setStyleSheet(
                "QPushButton { background: #0284c7; color: #ffffff; border: 1px solid #38bdf8; "
                "border-radius: 6px; padding: 0 12px; font-size: 11.5px; font-weight: 700; }"
            )
        else:
            btn.setStyleSheet(
                "QPushButton { background: #162032; color: #94a3b8; border: 1px solid #283548; "
                "border-radius: 6px; padding: 0 12px; font-size: 11.5px; font-weight: 600; }"
                "QPushButton:hover { background: #1e293b; color: #f1f5f9; border-color: #38bdf8; }"
            )

    def _set_category_filter(self, cat_key):
        self._current_filter_cat = cat_key
        for k, b in self.btn_cats.items():
            self._update_cat_btn_style(b, k == cat_key)
        self._render_table()

    def _on_search_changed(self):
        self._render_table()

    def _render_table(self):
        self.table.setRowCount(0)
        query = self.search_input.text().strip().lower()
        selected_cat = self._current_filter_cat

        filtered = []
        for item in self._commands:
            if selected_cat != "all" and item["category"] != selected_cat:
                continue
            if query:
                text_to_search = f"{item['category_label']} {item['command']} {item['example']} {item['description']}".lower()
                if query not in text_to_search:
                    continue
            filtered.append(item)

        self.table.setRowCount(len(filtered))
        for row_idx, item in enumerate(filtered):
            # 0. หมวดหมู่
            cat_item = QTableWidgetItem(item["category_label"])
            cat_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            cat_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.table.setItem(row_idx, 0, cat_item)

            # 1. คำสั่ง
            cmd_item = QTableWidgetItem(item["command"])
            cmd_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            cmd_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            cmd_item.setForeground(Qt.yellow)
            self.table.setItem(row_idx, 1, cmd_item)

            # 2. ตัวอย่างพิมพ์
            ex_item = QTableWidgetItem(item["example"])
            ex_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            ex_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            ex_item.setForeground(Qt.cyan)
            self.table.setItem(row_idx, 2, ex_item)

            # 3. คำอธิบาย
            desc_item = QTableWidgetItem(item["description"])
            desc_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            desc_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.table.setItem(row_idx, 3, desc_item)

            # 4. ปุ่มคัดลอกตัวอย่าง
            btn_copy = QPushButton("คัดลอก")
            btn_copy.setFixedHeight(24)
            btn_copy.setCursor(Qt.PointingHandCursor)
            btn_copy.setToolTip(f"คัดลอกตัวอย่าง: {item['example']}")
            btn_copy.setStyleSheet(
                "QPushButton { background: #1e293b; color: #cbd5e1; border: 1px solid #334155; "
                "border-radius: 4px; font-size: 11px; padding: 0 4px; font-weight: 600; }"
                "QPushButton:hover { background: #334155; color: #38bdf8; border-color: #0284c7; }"
            )
            btn_copy.clicked.connect(lambda _, ex=item["example"]: self._copy_single(ex))
            self.table.setCellWidget(row_idx, 4, btn_copy)

            self.table.setRowHeight(row_idx, 48)

    def _copy_single(self, text: str):
        cb = QApplication.clipboard()
        cb.setText(text)
        self.status_feedback.setText(f"✅ คัดลอก '{text}' แล้ว")
        self.status_feedback.setVisible(True)

    def _copy_all_commands(self):
        cb = QApplication.clipboard()
        text = generate_copy_all_text(self._commands)
        cb.setText(text)
        self.status_feedback.setText("✅ คัดลอกสรุปคำสั่งทั้งหมดแล้ว! นำไปแปะในแชทบอทหรือคำอธิบายสตรีมได้เลย")
        self.status_feedback.setVisible(True)
