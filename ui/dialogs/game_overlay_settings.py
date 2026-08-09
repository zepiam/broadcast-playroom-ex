"""game_overlay_settings.py — Game Overlay settings dialog (PySide6)

Port จาก v1 GameOverlaySettingsDialog — รวม appearance settings ครบทุกอย่าง:
- Appearance mode (default / theme / special / character)
- Theme selector (54 themes)
- Content (logo, timestamp, layout, font size, emote size, msg length, stroke, shadow)
- Font family + weight + text color
- Animation (in/out + auto-hide)
- Box (bg, opacity, radius, border, shadow, glow)
- Loop Demo toggle (green เริ่ม ↔ red หยุด)
- Custom CSS (theme=custom only)
"""
import logging
import os
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QColor, QPixmap, QImage
from PySide6.QtWidgets import (
    QDialog, QWidget, QFrame, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QFormLayout, QScrollArea, QComboBox, QSlider, QCheckBox,
    QSpinBox, QDoubleSpinBox, QButtonGroup, QRadioButton, QColorDialog,
    QGroupBox, QTextEdit, QSizePolicy, QTabWidget, QGridLayout, QMessageBox,
    QLineEdit,
)

logger = logging.getLogger("game_overlay_settings")

# ── colors (sync กับ ui/theme.py) ──
COL_BG = "#0a0e1a"
COL_CARD = "#131726"
COL_BORDER = "#2a2f45"
COL_TEXT = "#e5e7eb"
COL_TEXT_DIM = "#9ca3af"
COL_HEADING = "#f59e0b"
COL_ACCENT = "#7c3aed"
COL_SUCCESS = "#22c55e"
COL_DANGER = "#ef4444"


class GameOverlaySettingsDialog(QDialog):
    """Game Overlay settings — appearance + demo + box + animation + custom CSS

    อัปเดต live ไปยัง overlay (ถ้าเปิดอยู่) ทุกครั้งที่ผู้ใช้เปลี่ยนค่า
    """

    def __init__(self, parent_app):
        super().__init__(parent_app if isinstance(parent_app, QWidget) else None)
        self.parent_app = parent_app
        self.settings = getattr(parent_app, 'settings', None)
        self.setWindowTitle("🎮 Game Overlay Settings")
        self.setGeometry(180, 120, 720, 720)
        self.setMinimumSize(620, 560)
        self._css_timer = None  # debounce custom CSS
        self._loading = True  # ★ กัน _save_mode_config รันตอน build/load
        self._build_ui()
        self._load_values()
        self._loading = False  # ★ เปิดใช้งาน live_update หลัง load เสร็จ
        self._refresh_demo_btn_state()
        # ★ refresh ปุ่ม demo อีกครั้งหลัง overlay start (ถ้าจะเปิดตอนนี้)
        QTimer.singleShot(800, self._refresh_demo_btn_state)

    # ════════════════════════════════════════════════════════════
    # UI helpers
    # ════════════════════════════════════════════════════════════
    def _card(self, parent_layout, title):
        """สร้าง card (QFrame) พร้อม title bar + returns content layout"""
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {COL_CARD};
                border: 1px solid {COL_BORDER};
                border-radius: 10px;
            }}
            QLabel#cardtitle {{
                background: transparent;
                border: none;
                color: {COL_HEADING};
                font-size: 15px;
                font-weight: 700;
                padding: 8px 12px 4px 12px;
            }}
        """)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(8, 4, 8, 8)
        cl.setSpacing(4)
        title_lbl = QLabel(title)
        title_lbl.setObjectName("cardtitle")
        cl.addWidget(title_lbl)
        parent_layout.addWidget(card)
        return cl

    def _hrow(self, parent_layout, label_text, label_w=180, indent=0):
        """สร้าง row: [label (fixed width)] [stretch] + returns the row layout"""
        row = QHBoxLayout()
        row.setContentsMargins(indent, 0, 0, 0)
        row.setSpacing(8)
        if label_text:
            lbl = QLabel(label_text)
            lbl.setFixedWidth(label_w - indent)
            lbl.setStyleSheet(f"color: {COL_TEXT_DIM}; font-size: 14px;")
            row.addWidget(lbl)
        parent_layout.addLayout(row)
        return row

    def _slider_row(self, parent_layout, key, label, lo, hi, fmt_fn=None,
                    is_float=False, indent=0, step=1):
        """สร้าง slider row + returns slider widget
        key = settings attribute name (str)
        """
        row = self._hrow(parent_layout, label, indent=indent)
        slider = QSlider(Qt.Horizontal)
        slider.setMinimum(0)
        if is_float:
            # map float → int (*100 หรือ ตาม step)
            scale = max(1, int(1 / step)) if step < 1 else 1
            slider.setMaximum(int((hi - lo) * scale))
            slider.setSingleStep(1)
            slider._lo = lo
            slider._scale = scale
            slider._is_float = True
        else:
            slider.setMaximum(hi - lo)
            slider.setSingleStep(step)
            slider._lo = lo
            slider._scale = 1
            slider._is_float = False
        slider._key = key
        slider._fmt_fn = fmt_fn
        slider._is_float = is_float
        val_lbl = QLabel()
        val_lbl.setMinimumWidth(50)
        val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        val_lbl.setStyleSheet(f"color: {COL_ACCENT}; font-size: 14px; font-weight: 600;")
        def _on_change(v):
            if is_float:
                real = lo + v / scale
            else:
                real = lo + v
            val_lbl.setText(fmt_fn(real) if fmt_fn else str(int(real)))
            if key:  # ★ key=None = mode-specific slider (ไม่เขียน flat settings)
                setattr(self.settings, key, real)
            self._live_update()
        slider.valueChanged.connect(_on_change)
        slider._val_lbl = val_lbl
        slider._set_real = lambda v: slider.setValue(int((v - lo) * scale) if is_float else (v - lo))
        row.addWidget(slider, 1)
        row.addWidget(val_lbl)
        return slider

    def _checkbox_row(self, parent_layout, label, key, indent=0, on_change=None):
        """สร้าง checkbox row bound to settings[key]"""
        row = QHBoxLayout()
        row.setContentsMargins(indent, 0, 0, 0)
        cb = QCheckBox(label)
        cb.setStyleSheet(f"color: {COL_TEXT}; font-size: 14px; spacing: 8px;")
        def _on_state(state):
            val = bool(state)
            setattr(self.settings, key, val)
            self._live_update()
            if on_change:
                on_change(val)
        cb.stateChanged.connect(_on_state)
        cb._key = key
        row.addWidget(cb)
        parent_layout.addLayout(row)
        return cb

    def _color_row(self, parent_layout, label, key, indent=0):
        """สร้าง color picker row bound to settings[key] (hex string)"""
        row = self._hrow(parent_layout, label, indent=indent)
        btn = QPushButton()
        btn.setFixedHeight(28)
        btn.setMinimumWidth(80)
        btn._key = key
        def _pick():
            initial = getattr(self.settings, key, "#ffffff") or "#ffffff"
            color = QColorDialog.getColor(QColor(initial), self, "เลือกสี")
            if color.isValid():
                hex_val = color.name()
                setattr(self.settings, key, hex_val)
                btn._update_swatch()
                self._live_update()
        btn.clicked.connect(_pick)
        def _update_swatch():
            hex_val = getattr(self.settings, key, "#ffffff") or "#ffffff"
            btn.setText(hex_val.upper())
            btn.setStyleSheet(
                f"background: {hex_val}; color: {'#000' if _is_light(hex_val) else '#fff'};"
                f"border: 1px solid {COL_BORDER}; border-radius: 4px; padding: 2px 8px; font-size: 13px;"
            )
        btn._update_swatch = _update_swatch
        _update_swatch()  # ★ แสดงสีเริ่มต้นทันที
        row.addWidget(btn)
        row.addStretch()
        return btn

    def _combo_row(self, parent_layout, label, items, key=None, indent=0, on_change=None):
        """สร้าง combobox row"""
        row = self._hrow(parent_layout, label, indent=indent)
        combo = QComboBox()
        combo.setStyleSheet(f"""
            QComboBox {{
                background: {COL_BG}; color: {COL_TEXT};
                border: 1px solid {COL_BORDER}; border-radius: 4px;
                padding: 4px 10px; min-height: 22px; font-size: 14px;
            }}
            QComboBox::drop-down {{ border: none; width: 20px; }}
            QComboBox QAbstractItemView {{
                background: {COL_CARD}; color: {COL_TEXT};
                selection-background-color: {COL_ACCENT};
                border: 1px solid {COL_BORDER};
            }}
        """)
        combo.setMinimumWidth(180)
        for it in items:
            combo.addItem(it[1] if isinstance(it, (tuple, list)) else it)
            combo.setItemData(combo.count() - 1, it[0] if isinstance(it, (tuple, list)) else it)
        combo._key = key
        def _on_idx(idx):
            data = combo.itemData(idx)
            if key:
                setattr(self.settings, key, data)
                self._live_update()
            if on_change:
                on_change(data)
        combo.currentIndexChanged.connect(_on_idx)
        row.addWidget(combo)
        row.addStretch()
        return combo

    # ════════════════════════════════════════════════════════════
    # Build UI
    # ════════════════════════════════════════════════════════════
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ★ Header
        header = QFrame()
        header.setFixedHeight(50)
        header.setStyleSheet(f"background: {COL_CARD}; border-bottom: 1px solid {COL_BORDER};")
        hlayout = QHBoxLayout(header)
        hlayout.setContentsMargins(16, 0, 16, 0)
        title = QLabel("🎮 Game Overlay Settings")
        title.setStyleSheet(f"font-size: 17px; font-weight: 700; color: {COL_HEADING};")
        hlayout.addWidget(title)
        hlayout.addStretch()
        hint = QLabel("💡 เปลี่ยนค่าได้ทันที — Overlay อัปเดต live")
        hint.setStyleSheet(f"color: {COL_TEXT_DIM}; font-size: 13px;")
        hlayout.addWidget(hint)
        layout.addWidget(header)

        # ★ Tab widget (Game Overlay + Viewer Overlay)
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: none; background: {COL_BG}; }}
            QTabBar::tab {{
                background: {COL_CARD}; color: {COL_TEXT_DIM};
                padding: 8px 18px; margin-right: 2px;
                border: 1px solid {COL_BORDER}; border-bottom: none;
                border-top-left-radius: 6px; border-top-right-radius: 6px;
                font-size: 14px;
            }}
            QTabBar::tab:selected {{
                background: {COL_BG}; color: {COL_HEADING};
                font-weight: 600;
            }}
            QTabBar::tab:hover {{ color: {COL_TEXT}; }}
        """)

        # ── Tab 1: Game Overlay (existing content wrapped) ──
        game_tab = QWidget()
        game_tab_layout = QVBoxLayout(game_tab)
        game_tab_layout.setContentsMargins(0, 0, 0, 0)
        game_tab_layout.setSpacing(0)
        self._build_game_overlay_tab(game_tab_layout)
        self.tabs.addTab(game_tab, "🎮 Game Overlay")

        # ── Tab 2: Viewer Overlay (new) ──
        viewer_tab = QWidget()
        viewer_tab_layout = QVBoxLayout(viewer_tab)
        viewer_tab_layout.setContentsMargins(0, 0, 0, 0)
        viewer_tab_layout.setSpacing(0)
        self._build_viewer_overlay_tab(viewer_tab_layout)
        self.tabs.addTab(viewer_tab, "👥 Viewer Overlay")

        layout.addWidget(self.tabs, 1)

        # ★ Bottom buttons
        bottom = QFrame()
        bottom.setFixedHeight(54)
        bottom.setStyleSheet(f"background: {COL_CARD}; border-top: 1px solid {COL_BORDER};")
        blayout = QHBoxLayout(bottom)
        blayout.setContentsMargins(16, 0, 16, 0)
        blayout.addStretch()
        btn_close = QPushButton("ปิด")
        btn_close.setFixedWidth(90)
        btn_close.setFixedHeight(32)
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setStyleSheet(self._btn_secondary_style())
        btn_close.clicked.connect(self.reject)
        btn_save = QPushButton("💾 บันทึก")
        btn_save.setFixedWidth(110)
        btn_save.setFixedHeight(32)
        btn_save.setCursor(Qt.PointingHandCursor)
        btn_save.setStyleSheet(self._btn_primary_style())
        btn_save.clicked.connect(self._save)
        blayout.addWidget(btn_close)
        blayout.addWidget(btn_save)
        layout.addWidget(bottom)

    def _build_game_overlay_tab(self, parent_layout):
        """สร้างเนื้อหา Game Overlay tab (scrollable) — ย้ายมาจาก _build_ui"""
        # ★ Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ border: none; background: {COL_BG}; }}")
        container = QWidget()
        container.setStyleSheet(f"background: {COL_BG};")
        cl = QVBoxLayout(container)
        cl.setContentsMargins(20, 16, 20, 16)
        cl.setSpacing(10)

        s = self.settings

        # ────────────────────────────────────────────────────────
        # การเชื่อมต่อ + Loop Demo
        # ────────────────────────────────────────────────────────
        card_conn = self._card(cl, "🔌 การเชื่อมต่อ + Loop Demo")
        self.enabled_cb = self._checkbox_row(
            card_conn, "เลือกใช้ Game Overlay (เปิด/ปิดผ่านปุ่มหลัก)",
            "game_overlay_enabled_setting",
        )
        # Loop Demo button + interval slider
        demo_row = QHBoxLayout()
        demo_row.setContentsMargins(0, 4, 0, 0)
        demo_row.setSpacing(8)
        self.demo_btn = QPushButton("▶ เปิด Loop Demo")
        self.demo_btn.setFixedHeight(32)
        self.demo_btn.setMinimumWidth(150)
        self.demo_btn.setCursor(Qt.PointingHandCursor)
        self.demo_btn.setStyleSheet(self._demo_btn_style(False))
        self.demo_btn.clicked.connect(self._toggle_demo)
        demo_row.addWidget(self.demo_btn)
        interval_lbl = QLabel("ทุกๆ")
        interval_lbl.setStyleSheet(f"color: {COL_TEXT_DIM}; font-size: 14px;")
        demo_row.addWidget(interval_lbl)
        self.demo_interval_lbl = QLabel("5.0s")
        self.demo_interval_lbl.setStyleSheet(f"color: {COL_ACCENT}; font-size: 14px; font-weight: 600;")
        self.demo_interval_lbl.setMinimumWidth(40)
        demo_row.addWidget(self.demo_interval_lbl)
        demo_sld = QSlider(Qt.Horizontal)
        demo_sld.setMinimum(30)
        demo_sld.setMaximum(100)
        demo_sld.setValue(int(getattr(s, 'game_overlay_demo_interval', 5.0) * 10))
        demo_sld.valueChanged.connect(self._on_demo_interval_change)
        demo_row.addWidget(demo_sld, 1)
        card_conn.addLayout(demo_row)

        # ────────────────────────────────────────────────────────
        # Hotkeys (toggle overlay + edit mode)
        # ────────────────────────────────────────────────────────
        card_hk = self._card(cl, "🔑 Hotkeys")
        from ui.dialogs.hotkey_binder import make_hotkey_binder
        hk_toggle_row = self._hrow(card_hk, "เปิด/ปิด Overlay", label_w=180)
        self.go_hk_toggle = make_hotkey_binder(
            self, getattr(s, 'game_overlay_hotkey', 'ctrl+shift+g'),
            on_captured=lambda hk: self._save_go_hotkey('toggle', hk),
        )
        hk_toggle_row.addWidget(self.go_hk_toggle)
        hk_toggle_row.addStretch()
        hk_edit_row = self._hrow(card_hk, "Edit Mode (ลาก/resize)", label_w=180)
        self.go_hk_edit = make_hotkey_binder(
            self, getattr(s, 'game_overlay_hotkey_edit', 'ctrl+shift+h'),
            on_captured=lambda hk: self._save_go_hotkey('edit', hk),
        )
        hk_edit_row.addWidget(self.go_hk_edit)
        hk_edit_row.addStretch()
        hk_hint = QLabel("💡 คลิกปุ่มแล้วกดคีย์ผสมที่ต้องการ\nรองรับ F1-F35, ตัวอักษร, ตัวเลข — เช่น f13, ctrl+f24, shift+f1, ctrl+shift+g\nกด Esc เพื่อยกเลิกการจับคีย์")
        hk_hint.setStyleSheet(f"color: {COL_TEXT_DIM}; font-size: 11px; padding-top: 4px;")
        hk_hint.setWordWrap(True)
        card_hk.addWidget(hk_hint)

        # ────────────────────────────────────────────────────────
        # Appearance mode (default / theme / special / character)
        # ────────────────────────────────────────────────────────
        card_app = self._card(cl, "🎨 Appearance")
        mode_lbl = QLabel("ต้องการใช้ Chat Overlay แบบไหน?")
        mode_lbl.setStyleSheet(f"color: {COL_TEXT}; font-size: 14px; font-weight: 600;")
        card_app.addWidget(mode_lbl)
        mode_row = QHBoxLayout()
        mode_row.setContentsMargins(0, 4, 0, 4)
        self.mode_group = QButtonGroup(self)
        self.mode_radios = {}
        for mode_key, mode_label in [
            ("default", "Default"),
            ("theme", "Theme"),
            ("special", "Special Overlay"),
            ("character", "🎭 Character Talk"),
        ]:
            rb = QRadioButton(mode_label)
            rb.setStyleSheet(f"color: {COL_TEXT}; font-size: 14px; spacing: 6px;")
            rb._mode = mode_key
            rb.toggled.connect(lambda checked, mk=mode_key: self._on_appearance_change(mk) if checked else None)
            self.mode_group.addButton(rb)
            self.mode_radios[mode_key] = rb
            mode_row.addWidget(rb)
        mode_row.addStretch()
        card_app.addLayout(mode_row)

        # ── Theme selector (visible เฉพาะ mode=theme) ──
        self.theme_holder = QFrame()
        self.theme_holder.setStyleSheet("background: transparent; border: none;")
        th_layout = QVBoxLayout(self.theme_holder)
        th_layout.setContentsMargins(0, 4, 0, 4)
        th_layout.setSpacing(4)
        try:
            from game_overlay_themes import get_theme_list
            theme_items = get_theme_list()  # [(key, label), ...]
        except Exception:
            theme_items = [("default", "Default"), ("neon", "Neon")]
        theme_combo_items = [(k, lbl) for k, lbl in theme_items]
        self.theme_combo = self._combo_row(
            th_layout, "🎨 Theme", theme_combo_items, key="game_overlay_theme",
        )
        card_app.addWidget(self.theme_holder)

        # ── Custom CSS (visible เฉพาะ theme=custom) ──
        self.css_holder = QFrame()
        self.css_holder.setStyleSheet("background: transparent; border: none;")
        ch_layout = QVBoxLayout(self.css_holder)
        ch_layout.setContentsMargins(0, 4, 0, 4)
        ch_layout.setSpacing(4)
        css_guide_row = QHBoxLayout()
        btn_guide = QPushButton("📖 CSS Guide")
        btn_guide.setFixedHeight(26)
        btn_guide.setCursor(Qt.PointingHandCursor)
        btn_guide.clicked.connect(self._show_css_guide)
        css_guide_row.addWidget(btn_guide)
        css_guide_row.addStretch()
        ch_layout.addLayout(css_guide_row)
        css_lbl = QLabel("✏️ Custom CSS")
        css_lbl.setStyleSheet(f"color: {COL_HEADING}; font-size: 14px; font-weight: 700;")
        ch_layout.addWidget(css_lbl)
        self.css_edit = QTextEdit()
        self.css_edit.setMinimumHeight(120)
        self.css_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {COL_BG}; color: {COL_TEXT};
                border: 1px solid {COL_BORDER}; border-radius: 6px;
                padding: 6px; font-family: Consolas, monospace; font-size: 13px;
            }}
        """)
        self.css_edit.textChanged.connect(self._on_css_change)
        ch_layout.addWidget(self.css_edit)
        card_app.addWidget(self.css_holder)

        # ────────────────────────────────────────────────────────
        # เนื้อหาและขนาด
        # ────────────────────────────────────────────────────────
        card_content = self._card(cl, "📝 เนื้อหาและขนาด")
        self.logo_cb = self._checkbox_row(card_content, "แสดงโลโก้แพลตฟอร์ม", "game_overlay_show_logo")
        self.ts_cb = self._checkbox_row(card_content, "แสดงเวลาที่โพสข้อความ", "game_overlay_show_timestamp")
        # layout dropdown
        from collections import OrderedDict
        layout_opts = OrderedDict([
            ("stacked", "2 บรรทัด (ชื่อบน / ข้อความล่าง)"),
            ("inline", "1 บรรทัด (ชื่อ: ข้อความ)"),
            ("message_only", "เฉพาะข้อความ (ซ่อนชื่อ/โลโก้)"),
            ("stacked_no_logo", "2 บรรทัด (ไม่มีโลโก้)"),
            ("inline_no_logo", "1 บรรทัด (ไม่มีโลโก้)"),
        ])
        self.layout_combo = self._combo_row(
            card_content, "เลย์เอาต์ข้อความ",
            list(layout_opts.items()), key="game_overlay_layout",
        )
        self.font_size_sld = self._slider_row(card_content, "game_overlay_font_size", "ขนาดฟอนต์", 10, 64, lambda v: f"{int(v)}px")
        self.emote_size_sld = self._slider_row(card_content, "game_overlay_emote_size", "ขนาด Emote", 12, 64, lambda v: f"{int(v)}px")
        self.animated_emotes_cb = self._checkbox_row(card_content, "🎞️ แสดง emote ขยับ (animated)", "game_overlay_animated_emotes")
        self.msg_len_sld = self._slider_row(card_content, "game_overlay_max_msg_length", "ความยาวข้อความสูงสุด (0=ไม่จำกัด)", 0, 500, lambda v: f"{int(v)}")
        self.msg_spacing_sld = self._slider_row(card_content, "game_overlay_msg_spacing", "ช่องว่างข้อความ", 0, 30, lambda v: f"{int(v)}px", is_float=True, step=0.5)
        # stroke
        self.stroke_cb = self._checkbox_row(card_content, "Stroke (ขอบตัวอักษร)", "game_overlay_text_stroke")
        self.stroke_color_btn = self._color_row(card_content, "สี Stroke", "game_overlay_text_stroke_color", indent=24)
        self.stroke_w_sld = self._slider_row(card_content, "game_overlay_text_stroke_width", "ความหนา Stroke", 0, 6, lambda v: f"{int(v)}px", indent=24)
        # shadow
        self.shadow_cb = self._checkbox_row(card_content, "เงาตัวอักษร", "game_overlay_text_shadow")
        self.shadow_color_btn = self._color_row(card_content, "สีเงา", "game_overlay_text_shadow_color", indent=24)
        self.shadow_blur_sld = self._slider_row(card_content, "game_overlay_text_shadow_blur", "ความเบลอเงา", 0, 10, lambda v: f"{int(v)}px", indent=24)

        # ────────────────────────────────────────────────────────
        # ฟอนต์
        # ────────────────────────────────────────────────────────
        try:
            from settings import GOOGLE_FONTS
            font_items = list(GOOGLE_FONTS.items())
        except Exception:
            font_items = [("Kanit", "Kanit")]
        card_font = self._card(cl, "🔤 ฟอนต์")
        self.font_combo = self._combo_row(card_font, "ฟอนต์", font_items, key="game_overlay_font_family")
        weight_items = [("300", "300"), ("400", "400"), ("500", "500"), ("600", "600"), ("700", "700")]
        self.weight_combo = self._combo_row(card_font, "น้ำหนักฟอนต์", weight_items, key="game_overlay_font_weight")
        self.text_color_btn = self._color_row(card_font, "สีข้อความ", "game_overlay_text_color")

        # ────────────────────────────────────────────────────────
        # อนิเมชั่น
        # ────────────────────────────────────────────────────────
        try:
            from settings import OVERLAY_ANIMATIONS, OVERLAY_EXIT_ANIMATIONS
            anim_in_items = list(OVERLAY_ANIMATIONS.items())
            anim_out_items = list(OVERLAY_EXIT_ANIMATIONS.items())
        except Exception:
            anim_in_items = [("fade", "Fade")]
            anim_out_items = [("fade_out", "Fade Out")]
        card_anim = self._card(cl, "🎬 อนิเมชั่น")
        self.anim_in_combo = self._combo_row(card_anim, "ตอนเข้า", anim_in_items, key="game_overlay_anim_in")
        self.anim_out_combo = self._combo_row(card_anim, "ตอนออก", anim_out_items, key="game_overlay_anim_out")
        self.autohide_cb = self._checkbox_row(card_anim, "ซ่อนเมื่อหมดเวลา", "game_overlay_auto_hide")
        self.hide_after_sld = self._slider_row(card_anim, "game_overlay_hide_after", "ซ่อนหลัง (วินาที)", 3, 60, lambda v: f"{int(v)}s", indent=24)

        # ────────────────────────────────────────────────────────
        # กล่องข้อความ
        # ────────────────────────────────────────────────────────
        card_box = self._card(cl, "📦 กล่องข้อความ")
        self.box_cb = self._checkbox_row(card_box, "แสดงกล่องข้อความ", "game_overlay_box_enabled")
        self.box_bg_btn = self._color_row(card_box, "สีพื้นหลังกล่อง", "game_overlay_box_bg_color", indent=24)
        self.opacity_sld = self._slider_row(card_box, "game_overlay_box_bg_opacity", "ความโปร่งใส", 0, 1, lambda v: f"{int(v*100)}%", is_float=True, indent=24, step=0.01)
        self.box_radius_sld = self._slider_row(card_box, "game_overlay_box_radius", "ความโค้งมุม", 0, 30, lambda v: f"{int(v)}px", indent=24)
        self.box_border_cb = self._checkbox_row(card_box, "ขอบ", "game_overlay_box_border", indent=24)
        self.border_color_btn = self._color_row(card_box, "สีขอบ", "game_overlay_box_border_color", indent=48)
        self.box_border_w_sld = self._slider_row(card_box, "game_overlay_box_border_width", "ความหนาขอบ", 0, 6, lambda v: f"{int(v)}px", indent=48)
        self.box_shadow_cb = self._checkbox_row(card_box, "เงากล่อง", "game_overlay_box_shadow", indent=24)
        self.box_glow_cb = self._checkbox_row(card_box, "✨ Glow", "game_overlay_box_glow", indent=24)
        self.glow_color_btn = self._color_row(card_box, "สี Glow", "game_overlay_box_glow_color", indent=48)

        # ────────────────────────────────────────────────────────
        # Special Overlay (visible เฉพาะ mode=special)
        # ────────────────────────────────────────────────────────
        self.special_holder = QFrame()
        self.special_holder.setStyleSheet("background: transparent; border: none;")
        sh_layout = QVBoxLayout(self.special_holder)
        sh_layout.setContentsMargins(0, 4, 0, 4)
        sh_layout.setSpacing(4)
        sp_title = QLabel("🎈 Special Overlay")
        sp_title.setStyleSheet(f"color: {COL_HEADING}; font-size: 15px; font-weight: 700;")
        sh_layout.addWidget(sp_title)
        sp_desc = QLabel("ข้อความลอยกระจายสุ่ม (Balloon Mode)")
        sp_desc.setStyleSheet(f"color: {COL_TEXT_DIM}; font-size: 13px;")
        sh_layout.addWidget(sp_desc)
        self.balloon_cb = self._checkbox_row(sh_layout, "🎈 Balloon Mode (ข้อความลอยกระจายสุ่ม)", "game_overlay_balloon_mode")
        self.balloon_hide_sld = self._slider_row(sh_layout, "game_overlay_balloon_hide_after", "Duration (ข้อความหาย)", 2, 30, lambda v: f"{int(v)}s", is_float=True)
        self.balloon_opacity_sld = self._slider_row(sh_layout, "game_overlay_balloon_bg_opacity", "ความโปร่งใส", 0.1, 1.0, lambda v: f"{int(v*100)}%", is_float=True, step=0.01)
        # ★ balloon-specific font + color (แยกจาก default/theme)
        try:
            from settings import GOOGLE_FONTS
            sp_font_items = list(GOOGLE_FONTS.items())
        except Exception:
            sp_font_items = [("Kanit", "Kanit")]
        self.sp_font_combo = self._combo_row(sh_layout, "ฟอนต์ Balloon", sp_font_items, key=None,
                                             on_change=lambda v: self._set_mode_cfg('special', 'font_family', v))
        self.sp_font_size_sld = self._slider_row(sh_layout, None, "ขนาดฟอนต์ Balloon", 10, 64, lambda v: f"{int(v)}px")
        self.sp_text_color_btn = self._color_row(sh_layout, "สีข้อความ Balloon", "game_overlay_text_color")
        cl.addWidget(self.special_holder)

        # ── Character Talk holder (เฉพาะ Character mode) ──
        self.character_holder = QFrame()
        self.character_holder.setStyleSheet("background: transparent; border: none;")
        ch_layout = QVBoxLayout(self.character_holder)
        char_card = self._card(ch_layout, "🎭 Character Talk")
        char_desc = QLabel(
            "💡 ตัวละครยืนเรียงด้านล่างจอ — ผู้ชมพิมพ์แชท → บอลลูนโผล่เหนือตัวละคร\n"
            "ผู้ชมพิมพ์ {jobchange:knight} เพื่อเลือกตัวละคร"
        )
        char_desc.setStyleSheet(f"color: {COL_TEXT_DIM}; font-size: 12px;")
        char_desc.setWordWrap(True)
        char_card.addWidget(char_desc)
        # character sliders
        self._slider_row(char_card, "character_size", "ขนาดตัวละคร (px)", 60, 250, lambda v: f"{int(v)}px")
        self._slider_row(char_card, "character_hide_after", "ระยะเวลาแสดง (วินาที)", 2, 20, lambda v: f"{int(v)}s", is_float=True)
        self._slider_row(char_card, "character_max_on_screen", "จำนวนตัวละครสูงสุด", 3, 15, lambda v: f"{int(v)}")
        self._checkbox_row(char_card, "สุ่มตำแหน่งตัวละคร (ไม่เรียงตรงกลาง)", "character_random_pos")
        # bubble width
        bw_items = [("400", "400px"), ("500", "500px"), ("600", "600px"), ("700", "700px"), ("800", "800px")]
        self._combo_row(char_card, "ความกว้างกล่องข้อความ", bw_items, key=None,
                        on_change=lambda v: setattr(self.settings, 'character_bubble_width', int(v)))
        # ── ชื่อตัวละคร ──
        name_title = QLabel("📝 ชื่อตัวละคร")
        name_title.setStyleSheet(f"color: {COL_HEADING}; font-size: 14px; font-weight: 700; padding-top: 8px;")
        char_card.addWidget(name_title)
        self._slider_row(char_card, "character_name_size", "ขนาดชื่อ (px)", 8, 24, lambda v: f"{int(v)}px")
        self._checkbox_row(char_card, "เส้นขอบชื่อ (Stroke)", "character_name_stroke")
        self._color_row(char_card, "สีเส้นขอบชื่อ", "character_name_stroke_color")
        self._slider_row(char_card, "character_name_stroke_width", "ความหนาเส้นขอบชื่อ", 1, 4, lambda v: f"{int(v)}px")
        self._checkbox_row(char_card, "เงาชื่อ (Shadow)", "character_name_shadow")
        self._color_row(char_card, "สีเงาชื่อ", "character_name_shadow_color")
        self._slider_row(char_card, "character_name_shadow_blur", "ความฟุ้งเงาชื่อ", 0, 8, lambda v: f"{int(v)}px")
        # ── ภาพตัวละคร Default ──
        img_title = QLabel("🖼️ ภาพตัวละคร Default")
        img_title.setStyleSheet(f"color: {COL_HEADING}; font-size: 14px; font-weight: 700; padding-top: 8px;")
        char_card.addWidget(img_title)
        char_img_row = QHBoxLayout()
        char_img_row.addWidget(QLabel("ไฟล์ภาพ:"))
        self.char_default_path = QLineEdit(getattr(s, 'character_default_image', ''))
        self.char_default_path.setStyleSheet(f"background: {COL_BG}; color: {COL_TEXT}; border: 1px solid {COL_BORDER}; border-radius: 4px; padding: 4px 10px;")
        char_img_row.addWidget(self.char_default_path, 1)
        btn_browse_char = QPushButton("📁")
        btn_browse_char.setFixedSize(34, 30)
        btn_browse_char.setCursor(Qt.PointingHandCursor)
        btn_browse_char.setToolTip("เลือกไฟล์ภาพ")
        btn_browse_char.setStyleSheet(f"border: 1px solid {COL_BORDER}; border-radius: 4px; background: {COL_CARD}; padding: 0px; font-size: 15px;")
        def _browse_char():
            from PySide6.QtWidgets import QFileDialog
            path, _ = QFileDialog.getOpenFileName(self, "เลือกภาพตัวละคร", "", "Images (*.png *.jpg *.jpeg *.webp)")
            if path:
                self.char_default_path.setText(path)
                self.settings.character_default_image = path
                self._live_update()
        btn_browse_char.clicked.connect(_browse_char)
        char_img_row.addWidget(btn_browse_char)
        char_card.addLayout(char_img_row)
        # character font + text color
        try:
            from settings import GOOGLE_FONTS
            char_font_items = list(GOOGLE_FONTS.items())
        except Exception:
            char_font_items = [("Kanit", "Kanit")]
        self._combo_row(char_card, "ฟอนต์", char_font_items, key=None,
                        on_change=lambda v: self._set_mode_cfg('character', 'font_family', v))
        self._color_row(char_card, "สีข้อความ", "game_overlay_text_color")
        # ★ character font size — เก็บใน mode_configs["character"]["font_size"]
        self.char_font_size_sld = self._slider_row(char_card, None, "ขนาดฟอนต์", 10, 64, lambda v: f"{int(v)}px")

        cl.addWidget(self.character_holder)
        self.character_holder.setVisible(False)  # ซ่อนตอนเริ่ม (default mode)

        cl.addStretch()
        scroll.setWidget(container)
        parent_layout.addWidget(scroll, 1)

    def _build_viewer_overlay_tab(self, parent_layout):
        """สร้างเนื้อหา Viewer Overlay tab (ย้ายมาจาก settings.py)"""
        from PySide6.QtGui import QColor
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ border: none; background: {COL_BG}; }}")
        container = QWidget()
        container.setStyleSheet(f"background: {COL_BG};")
        cl = QVBoxLayout(container)
        cl.setContentsMargins(20, 16, 20, 16)
        cl.setSpacing(10)

        s = self.settings

        # ★ heading
        heading = QLabel("👥 Viewer Overlay")
        heading.setStyleSheet(f"font-size: 20px; font-weight: 700; color: {COL_HEADING};")
        cl.addWidget(heading)
        desc = QLabel("Overlay แสดงยอดคนดูแบบลอยเหนือเกม")
        desc.setStyleSheet(f"color: {COL_TEXT_DIM}; font-size: 13px;")
        desc.setWordWrap(True)
        cl.addWidget(desc)

        # enabled
        self.vo_enabled_cb = QCheckBox("เลือกใช้ Viewer Overlay")
        self.vo_enabled_cb.setChecked(bool(getattr(s, 'viewer_overlay_enabled_setting', True)))
        self.vo_enabled_cb.setStyleSheet(f"color: {COL_TEXT}; font-size: 14px; spacing: 8px; font-weight: 600;")
        def _on_vo_enabled(state):
            self.settings.viewer_overlay_enabled_setting = bool(state)
            self._vo_live_update()
        self.vo_enabled_cb.stateChanged.connect(_on_vo_enabled)
        cl.addWidget(self.vo_enabled_cb)

        # mode (segmented)
        mode_lbl = QLabel("โหมด:")
        mode_lbl.setStyleSheet(f"color: {COL_TEXT}; font-size: 14px; padding-top: 6px;")
        cl.addWidget(mode_lbl)
        mode_row = QHBoxLayout()
        self.vo_mode_group = QButtonGroup(self)
        self.vo_mode_radios = {}
        for mkey, mlabel in [
            ("off", "ปิด"),
            ("total", "รวมยอด"),
            ("per_platform", "แยกตามแพลตฟอร์ม"),
        ]:
            rb = QRadioButton(mlabel)
            rb.setStyleSheet(f"color: {COL_TEXT}; font-size: 14px; spacing: 6px;")
            self.vo_mode_group.addButton(rb)
            self.vo_mode_radios[mkey] = rb
            rb.toggled.connect(lambda checked, mk=mkey: self._on_vo_mode(mk) if checked else None)
            mode_row.addWidget(rb)
        mode_row.addStretch()
        cl.addLayout(mode_row)
        cur_mode = getattr(s, 'viewer_overlay_mode', 'off')
        if cur_mode in self.vo_mode_radios:
            self.vo_mode_radios[cur_mode].setChecked(True)

        # alignment
        align_lbl = QLabel("การจัดวาง:")
        align_lbl.setStyleSheet(f"color: {COL_TEXT}; font-size: 14px; padding-top: 6px;")
        cl.addWidget(align_lbl)
        align_row = QHBoxLayout()
        self.vo_align_group = QButtonGroup(self)
        self.vo_align_radios = {}
        for akey, alabel in [("left", "ชิดซ้าย"), ("center", "กลาง"), ("right", "ชิดขวา")]:
            rb = QRadioButton(alabel)
            rb.setStyleSheet(f"color: {COL_TEXT}; font-size: 14px; spacing: 6px;")
            self.vo_align_group.addButton(rb)
            self.vo_align_radios[akey] = rb
            rb.toggled.connect(lambda checked, ak=akey: self._on_vo_align(ak) if checked else None)
            align_row.addWidget(rb)
        align_row.addStretch()
        cl.addLayout(align_row)
        cur_align = getattr(s, 'viewer_overlay_align', 'center')
        if cur_align in self.vo_align_radios:
            self.vo_align_radios[cur_align].setChecked(True)

        # sliders: icon size, font size
        self.vo_icon_sld = self._vo_slider(cl, "ขนาดไอคอน", "viewer_overlay_icon_size", 12, 48)
        self.vo_font_sld = self._vo_slider(cl, "ขนาดฟอนต์", "viewer_overlay_font_size", 10, 40)
        # font color
        self.vo_font_color_btn = self._vo_color(cl, "สีตัวเลข", "viewer_overlay_font_color")
        # stroke
        self.vo_stroke_cb = QCheckBox("เส้นขอบ (Stroke)")
        self.vo_stroke_cb.setChecked(bool(getattr(s, 'viewer_overlay_text_stroke', True)))
        self.vo_stroke_cb.setStyleSheet(f"color: {COL_TEXT}; font-size: 14px; padding-top: 6px;")
        def _on_vo_stroke(state):
            self.settings.viewer_overlay_text_stroke = bool(state)
            self._vo_live_update()
        self.vo_stroke_cb.stateChanged.connect(_on_vo_stroke)
        cl.addWidget(self.vo_stroke_cb)
        self.vo_stroke_color_btn = self._vo_color(cl, "สีเส้นขอบ", "viewer_overlay_text_stroke_color")
        self.vo_stroke_w_sld = self._vo_slider(cl, "ความหนาเส้นขอบ", "viewer_overlay_text_stroke_width", 1, 6)
        # shadow
        self.vo_shadow_cb = QCheckBox("เงา (Shadow)")
        self.vo_shadow_cb.setChecked(bool(getattr(s, 'viewer_overlay_text_shadow', True)))
        self.vo_shadow_cb.setStyleSheet(f"color: {COL_TEXT}; font-size: 14px; padding-top: 6px;")
        def _on_vo_shadow(state):
            self.settings.viewer_overlay_text_shadow = bool(state)
            self._vo_live_update()
        self.vo_shadow_cb.stateChanged.connect(_on_vo_shadow)
        cl.addWidget(self.vo_shadow_cb)
        self.vo_shadow_color_btn = self._vo_color(cl, "สีเงา", "viewer_overlay_text_shadow_color")
        self.vo_shadow_blur_sld = self._vo_slider(cl, "ความเบลอเงา", "viewer_overlay_text_shadow_blur", 0, 10)
        # opacity
        self.vo_opacity_sld = self._vo_slider(cl, "ความโปร่งใส", "viewer_overlay_alpha", 20, 100,
                                               fmt=lambda v: f"{int(v)}%", scale=0.01)

        cl.addStretch()
        scroll.setWidget(container)
        parent_layout.addWidget(scroll, 1)

    # ── Viewer Overlay helpers ──
    def _on_vo_mode(self, mkey):
        """mode radio toggled — save + live update"""
        self.settings.viewer_overlay_mode = mkey
        self._vo_live_update()

    def _on_vo_align(self, akey):
        """align radio toggled — save + live update"""
        self.settings.viewer_overlay_align = akey
        self._vo_live_update()

    def _vo_live_update(self):
        """save settings + push update ไป viewer overlay (live)"""
        if not self.settings:
            return
        try:
            from settings import save_settings
            save_settings(self.settings)
        except Exception as e:
            logger.debug(f"vo save failed: {e}")
        vo = getattr(self.parent_app, '_viewer_overlay', None)
        if vo and getattr(vo, 'is_running', False):
            try:
                vo.update_settings()
            except Exception as e:
                logger.debug(f"viewer overlay update_settings failed: {e}")

    def _vo_slider(self, parent_layout, label, key, lo, hi, fmt=None, scale=1):
        """slider row สำหรับ viewer overlay setting (live update)"""
        row = QHBoxLayout()
        lbl = QLabel(label)
        lbl.setFixedWidth(180)
        lbl.setStyleSheet(f"color: {COL_TEXT_DIM}; font-size: 14px;")
        row.addWidget(lbl)
        sld = QSlider(Qt.Horizontal)
        sld.setRange(lo, hi)
        cur = getattr(self.settings, key, (lo + hi) // 2)
        if scale != 1:
            sld.setValue(int(cur / scale))
        else:
            sld.setValue(int(cur))
        val_lbl = QLabel()
        val_lbl.setMinimumWidth(50)
        val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        val_lbl.setStyleSheet(f"color: {COL_ACCENT}; font-size: 14px; font-weight: 600;")
        def _on(v):
            real = v * scale if scale != 1 else v
            val_lbl.setText(fmt(real) if fmt else str(int(real)))
            setattr(self.settings, key, real)
            self._vo_live_update()
        sld.valueChanged.connect(_on)
        _on(sld.value())
        row.addWidget(sld, 1)
        row.addWidget(val_lbl)
        parent_layout.addLayout(row)
        return sld

    def _vo_color(self, parent_layout, label, key):
        """color picker row สำหรับ viewer overlay setting (live update)"""
        from PySide6.QtGui import QColor
        row = QHBoxLayout()
        lbl = QLabel(label)
        lbl.setFixedWidth(180)
        lbl.setStyleSheet(f"color: {COL_TEXT_DIM}; font-size: 14px;")
        row.addWidget(lbl)
        btn = QPushButton()
        btn.setFixedHeight(28)
        btn.setMinimumWidth(80)
        btn.setCursor(Qt.PointingHandCursor)
        def _update():
            hex_val = getattr(self.settings, key, "#ffffff") or "#ffffff"
            btn.setText(hex_val.upper())
            c = QColor(hex_val)
            txt_color = "#000" if (c.red()*299 + c.green()*587 + c.blue()*114) / 1000 > 128 else "#fff"
            btn.setStyleSheet(
                f"background: {hex_val}; color: {txt_color}; "
                f"border: 1px solid {COL_BORDER}; border-radius: 4px; "
                f"padding: 2px 8px; font-size: 13px;"
            )
        def _pick():
            initial = getattr(self.settings, key, "#ffffff") or "#ffffff"
            color = QColorDialog.getColor(QColor(initial), self, "เลือกสี")
            if color.isValid():
                setattr(self.settings, key, color.name())
                _update()
                self._vo_live_update()
        btn.clicked.connect(_pick)
        _update()
        row.addWidget(btn)
        row.addStretch()
        parent_layout.addLayout(row)
        return btn

    def _btn_primary_style(self):
        return f"""
            QPushButton {{
                background: {COL_ACCENT}; color: #fff; border: none;
                border-radius: 6px; font-weight: 600; padding: 0 16px;
            }}
            QPushButton:hover {{ background: #6d28d9; }}
            QPushButton:disabled {{ background: #4a5568; color: #a0aec0; }}
        """

    def _btn_secondary_style(self):
        return f"""
            QPushButton {{
                background: {COL_CARD}; color: {COL_TEXT};
                border: 1px solid {COL_BORDER}; border-radius: 6px;
                padding: 0 16px;
            }}
            QPushButton:hover {{ background: #1c2033; border-color: {COL_ACCENT}; }}
        """

    def _demo_btn_style(self, is_running):
        if is_running:
            return f"""
                QPushButton {{
                    background: {COL_DANGER}; color: #fff; border: none;
                    border-radius: 6px; font-weight: 700; padding: 0 16px;
                }}
                QPushButton:hover {{ background: #dc2626; }}
                QPushButton:disabled {{ background: #4a5568; color: #a0aec0; }}
            """
        return f"""
            QPushButton {{
                background: {COL_SUCCESS}; color: #fff; border: none;
                border-radius: 6px; font-weight: 700; padding: 0 16px;
            }}
            QPushButton:hover {{ background: #16a34a; }}
            QPushButton:disabled {{ background: #4a5568; color: #a0aec0; }}
        """

    # ════════════════════════════════════════════════════════════
    # Load / save values
    # ════════════════════════════════════════════════════════════
    def _load_values(self):
        if not self.settings:
            return
        s = self.settings
        # enabled
        self.enabled_cb.setChecked(bool(getattr(s, 'game_overlay_enabled_setting', True)))
        # demo interval slider (find it — created inline in _build_ui)
        interval = float(getattr(s, 'game_overlay_demo_interval', 5.0))
        for sld in self.findChildren(QSlider):
            # demo interval slider is the only one not created via _slider_row (no _key)
            if not hasattr(sld, '_key') and sld.minimum() == 30 and sld.maximum() == 100:
                sld.setValue(int(interval * 10))
                break
        self.demo_interval_lbl.setText(f"{interval:.1f}s")
        # appearance mode
        mode = getattr(s, 'game_overlay_appearance_mode', 'default')
        if mode in self.mode_radios:
            self.mode_radios[mode].setChecked(True)
        else:
            self.mode_radios['default'].setChecked(True)
        # theme
        cur_theme = getattr(s, 'game_overlay_theme', 'default')
        for i in range(self.theme_combo.count()):
            if self.theme_combo.itemData(i) == cur_theme:
                self.theme_combo.setCurrentIndex(i)
                break
        # custom CSS
        self.css_edit.setPlainText(getattr(s, 'game_overlay_custom_css', '') or '')
        # ★ load values from mode_configs[current_mode] first → fallback flat settings
        # ★ สำหรับ special/character → บาง fields โหลดจาก default config หรือ flat (ไม่ใช่ mode ปัจจุบัน)
        cur_mode = getattr(s, 'game_overlay_appearance_mode', 'default')
        mc = getattr(s, 'game_overlay_mode_configs', {}) or {}
        cur_cfg = dict(mc.get(cur_mode, {}))
        # default config = แหล่งข้อมูลสำรองสำหรับ fields ที่ mode ปัจจุบันไม่มี
        default_cfg = dict(mc.get('default', {}))

        def _mc(key, flat_key, default):
            # 1. current mode config → 2. default mode config → 3. flat settings
            if key in cur_cfg:
                return cur_cfg[key]
            if key in default_cfg:
                return default_cfg[key]
            return getattr(s, flat_key, default)

        # sliders — อ่านจาก mode_configs ก่อน → fallback flat
        self._set_slider(self.font_size_sld, _mc('font_size', 'game_overlay_font_size', 32))
        self._set_slider(self.emote_size_sld, _mc('emote_size', 'game_overlay_emote_size', 24))
        self._set_slider(self.msg_len_sld, getattr(s, 'game_overlay_max_msg_length', 0))
        self._set_slider(self.msg_spacing_sld, getattr(s, 'game_overlay_msg_spacing', 4.0))
        self._set_slider(self.stroke_w_sld, _mc('text_stroke_width', 'game_overlay_text_stroke_width', 2))
        self._set_slider(self.shadow_blur_sld, _mc('text_shadow_blur', 'game_overlay_text_shadow_blur', 3))
        self._set_slider(self.hide_after_sld, _mc('hide_after', 'game_overlay_hide_after', 8.0))
        self._set_slider(self.opacity_sld, getattr(s, 'game_overlay_box_bg_opacity', 0.55))
        self._set_slider(self.box_radius_sld, getattr(s, 'game_overlay_box_radius', 8))
        self._set_slider(self.box_border_w_sld, getattr(s, 'game_overlay_box_border_width', 1))
        self._set_slider(self.balloon_hide_sld, _mc('balloon_hide_after', 'game_overlay_balloon_hide_after', 5.0))
        self._set_slider(self.balloon_opacity_sld, _mc('balloon_bg_opacity', 'game_overlay_balloon_bg_opacity', 0.95))
        # ★ load special-specific font size + font family from mode_configs
        sp_cfg = mc.get('special', {})
        if hasattr(self, 'sp_font_size_sld'):
            self._set_slider(self.sp_font_size_sld, sp_cfg.get('font_size', 32))
        if hasattr(self, 'sp_font_combo') and sp_cfg.get('font_family'):
            for i in range(self.sp_font_combo.count()):
                if self.sp_font_combo.itemData(i) == sp_cfg['font_family']:
                    self.sp_font_combo.setCurrentIndex(i)
                    break
        # ★ load character holder slider values from flat settings
        # (sliders ใน character_holder ไม่ได้ถูกโหลดโดย _load_values ปกติ)
        from PySide6.QtWidgets import QSlider as _QS
        if hasattr(self, 'character_holder'):
            for sld in self.character_holder.findChildren(_QS):
                key = getattr(sld, '_key', None)
                if not key:
                    continue  # skip key=None sliders (char_font_size_sld)
                default_val = 120 if key == 'character_size' else 6.0 if key == 'character_hide_after' else 8
                val = getattr(s, key, default_val)
                self._set_slider(sld, val)

        # ★ load character-specific font size from mode_configs
        ch_cfg = mc.get('character', {})
        if hasattr(self, 'char_font_size_sld'):
            ch_fs = ch_cfg.get('font_size', 32)
            if ch_fs < 10:  # ★ guard กันค่าพัง
                ch_fs = 32
            self._set_slider(self.char_font_size_sld, ch_fs)
        # ★ text_color — apply from mode_configs + update swatch
        text_color = _mc('text_color', 'game_overlay_text_color', '#ffffff')
        s.game_overlay_text_color = text_color
        if hasattr(self, 'text_color_btn'):
            self.text_color_btn._update_swatch()
        if hasattr(self, 'sp_text_color_btn'):
            self.sp_text_color_btn._update_swatch()
        # checkboxes
        self.logo_cb.setChecked(bool(getattr(s, 'game_overlay_show_logo', True)))
        self.ts_cb.setChecked(bool(getattr(s, 'game_overlay_show_timestamp', False)))
        self.animated_emotes_cb.setChecked(bool(getattr(s, 'game_overlay_animated_emotes', False)))
        self.stroke_cb.setChecked(bool(getattr(s, 'game_overlay_text_stroke', False)))
        self.shadow_cb.setChecked(bool(getattr(s, 'game_overlay_text_shadow', True)))
        self.autohide_cb.setChecked(bool(getattr(s, 'game_overlay_auto_hide', True)))
        self.box_cb.setChecked(bool(getattr(s, 'game_overlay_box_enabled', True)))
        self.box_border_cb.setChecked(bool(getattr(s, 'game_overlay_box_border', False)))
        self.box_shadow_cb.setChecked(bool(getattr(s, 'game_overlay_box_shadow', True)))
        self.box_glow_cb.setChecked(bool(getattr(s, 'game_overlay_box_glow', False)))
        self.balloon_cb.setChecked(bool(getattr(s, 'game_overlay_balloon_mode', False)))
        # combos
        self._set_combo(self.layout_combo, getattr(s, 'game_overlay_layout', 'stacked'))
        self._set_combo(self.font_combo, getattr(s, 'game_overlay_font_family', 'Kanit'))
        self._set_combo(self.weight_combo, getattr(s, 'game_overlay_font_weight', '500'))
        self._set_combo(self.anim_in_combo, getattr(s, 'game_overlay_anim_in', 'fade'))
        self._set_combo(self.anim_out_combo, getattr(s, 'game_overlay_anim_out', 'fade_out'))
        # color swatches
        self.stroke_color_btn._update_swatch()
        self.shadow_color_btn._update_swatch()
        self.text_color_btn._update_swatch()
        self.box_bg_btn._update_swatch()
        self.border_color_btn._update_swatch()
        self.glow_color_btn._update_swatch()
        # appearance visibility
        self._update_appearance_visibility(mode)

    def _set_slider(self, slider, real_value):
        if slider is None:
            return
        # coerce type (settings อาจเก็บเป็น str จาก JSON)
        if getattr(slider, '_is_float', False):
            try:
                real_value = float(real_value)
            except (TypeError, ValueError):
                real_value = 0.0
            scale = getattr(slider, '_scale', 1) or 1
            lo = getattr(slider, '_lo', 0)
            slider.setValue(int((real_value - lo) * scale))
        else:
            try:
                real_value = int(real_value)
            except (TypeError, ValueError):
                real_value = 0
            lo = getattr(slider, '_lo', 0)
            slider.setValue(int(real_value - lo))

    def _set_combo(self, combo, value):
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return

    def _update_appearance_visibility(self, mode):
        """ซ่อน/แสดง sections ตาม appearance mode"""
        is_default_or_theme = mode in ('default', 'theme')
        is_theme = mode == 'theme'
        is_special = mode == 'special'
        # theme selector — visible ถ้า mode == theme
        self.theme_holder.setVisible(is_theme)
        # custom CSS — visible ถ้า theme == 'custom' AND mode == theme
        try:
            cur_theme = self.theme_combo.currentData() if is_theme else None
        except Exception:
            cur_theme = None
        self.css_holder.setVisible(is_theme and cur_theme == 'custom')
        # content/font/animation/box — visible ใน default + theme
        # (หา card widgets ผ่าน parent)
        for card in self.findChildren(QFrame):
            title_lbl = card.findChild(QLabel, "cardtitle")
            if title_lbl is None:
                continue
            txt = title_lbl.text()
            if txt in ("📝 เนื้อหาและขนาด", "🔤 ฟอนต์", "🎬 อนิเมชั่น", "📦 กล่องข้อความ"):
                card.setVisible(is_default_or_theme)
        # special overlay — visible ถ้า mode == special
        self.special_holder.setVisible(is_special)
        # character talk — visible ถ้า mode == character
        if hasattr(self, 'character_holder'):
            self.character_holder.setVisible(mode == 'character')

    # ════════════════════════════════════════════════════════════
    # Live update
    # ════════════════════════════════════════════════════════════
    def _live_update(self):
        """push update ไป overlay (live) — save mode config + save settings + update overlay"""
        if not self.settings:
            return
        # ★ กัน _save_mode_config รันตอนกำลัง build/load (กัน slider valueChanged trigger ระหว่าง init)
        if getattr(self, '_loading', False):
            return
        # ★ save current widget values to mode_configs[current_mode] before pushing
        self._save_mode_config()
        try:
            from settings import save_settings
            save_settings(self.settings)
        except Exception as e:
            logger.debug(f"save in live_update failed: {e}")
        go = getattr(self.parent_app, '_game_overlay', None)
        if go and go.is_running:
            try:
                go.update_settings()
            except Exception as e:
                logger.debug(f"overlay update_settings failed: {e}")

    def _set_mode_cfg(self, mode, key, value):
        """set single value in mode_configs[mode]"""
        configs = getattr(self.settings, 'game_overlay_mode_configs', None)
        if configs is None:
            configs = {}
            self.settings.game_overlay_mode_configs = configs
        cfg = configs.setdefault(mode, {})
        cfg[key] = value
        self._live_update()

    def _get_slider_real(self, slider):
        """แปลง raw slider value → real value (lo + value/scale หรือ lo + value)"""
        if slider is None:
            return 0
        v = slider.value()
        lo = getattr(slider, '_lo', 0)
        scale = getattr(slider, '_scale', 1) or 1
        is_float = getattr(slider, '_is_float', False)
        if is_float:
            return lo + v / scale
        return lo + v

    def _is_really_visible(self, widget):
        """เช็ค widget visible จริง — เช็ค parent chain ด้วย (กัน slider ใน card ที่ซ่อน)"""
        if widget is None:
            return False
        w = widget
        while w is not None and w is not self:
            if w.isHidden():
                return False
            w = w.parentWidget()
        return True

    def _save_mode_config(self):
        """save current widget values to mode_configs[current_appearance_mode]

        ★ แต่ละ appearance mode เก็บ styling ของตัวเอง — ไม่ sync กัน
        ★ ใช้ _is_really_visible() เช็คว่า widget และ parent ทั้งหมด visible ไหม
        """
        mode = getattr(self.settings, 'game_overlay_appearance_mode', 'default')
        configs = getattr(self.settings, 'game_overlay_mode_configs', None)
        if configs is None:
            configs = {}
            self.settings.game_overlay_mode_configs = configs
        cfg = configs.setdefault(mode, {})

        def _save_slider(attr_name, key):
            w = getattr(self, attr_name, None)
            if self._is_really_visible(w):
                real = self._get_slider_real(w)
                if real > 0:
                    cfg[key] = real
                    # ★ sync ไป flat settings ด้วย (server อ่านจาก mode_configs ก่อน → fallback flat)
                    flat_key = f'game_overlay_{key}'
                    if hasattr(self.settings, flat_key):
                        setattr(self.settings, flat_key, real)

        def _save_combo(attr_name, key):
            w = getattr(self, attr_name, None)
            if self._is_really_visible(w):
                data = w.currentData()
                if data:
                    cfg[key] = data

        def _save_checkbox(attr_name, key):
            w = getattr(self, attr_name, None)
            if self._is_really_visible(w):
                cfg[key] = w.isChecked()

        _save_combo('font_combo', 'font_family')
        _save_combo('weight_combo', 'font_weight')
        _save_slider('font_size_sld', 'font_size')
        _save_slider('emote_size_sld', 'emote_size')
        if hasattr(self, 'text_color_btn') and self._is_really_visible(self.text_color_btn):
            cfg['text_color'] = getattr(self.settings, 'game_overlay_text_color', '#ffffff')
        _save_checkbox('stroke_cb', 'text_stroke')
        _save_slider('stroke_w_sld', 'text_stroke_width')
        _save_checkbox('shadow_cb', 'text_shadow')
        _save_slider('shadow_blur_sld', 'text_shadow_blur')
        _save_combo('layout_combo', 'layout')
        _save_combo('anim_in_combo', 'anim_in')
        _save_combo('anim_out_combo', 'anim_out')
        _save_checkbox('autohide_cb', 'auto_hide')
        _save_slider('hide_after_sld', 'hide_after')
        _save_checkbox('logo_cb', 'show_logo')
        _save_checkbox('ts_cb', 'show_timestamp')
        # box settings (default/theme only) — save + sync ไป flat settings
        if mode in ('default', 'theme'):
            if hasattr(self, 'box_cb') and self._is_really_visible(self.box_cb):
                cfg['box_enabled'] = self.box_cb.isChecked()
                self.settings.game_overlay_box_enabled = cfg['box_enabled']
            if hasattr(self, 'box_radius_sld') and self._is_really_visible(self.box_radius_sld):
                val = self._get_slider_real(self.box_radius_sld)
                cfg['box_radius'] = val
                self.settings.game_overlay_box_radius = int(val)
            if hasattr(self, 'box_border_cb') and self._is_really_visible(self.box_border_cb):
                cfg['box_border'] = self.box_border_cb.isChecked()
                self.settings.game_overlay_box_border = cfg['box_border']
            if hasattr(self, 'box_border_w_sld') and self._is_really_visible(self.box_border_w_sld):
                val = self._get_slider_real(self.box_border_w_sld)
                cfg['box_border_width'] = val
                self.settings.game_overlay_box_border_width = int(val)
            if hasattr(self, 'box_shadow_cb') and self._is_really_visible(self.box_shadow_cb):
                cfg['box_shadow'] = self.box_shadow_cb.isChecked()
                self.settings.game_overlay_box_shadow = cfg['box_shadow']
            if hasattr(self, 'box_glow_cb') and self._is_really_visible(self.box_glow_cb):
                cfg['box_glow'] = self.box_glow_cb.isChecked()
                self.settings.game_overlay_box_glow = cfg['box_glow']
        # special: balloon-specific (ไม่เช็ค isVisible)
        if mode == 'special':
            if hasattr(self, 'sp_font_size_sld'):
                cfg['font_size'] = self._get_slider_real(self.sp_font_size_sld)
            if hasattr(self, 'sp_font_combo'):
                data = self.sp_font_combo.currentData()
                if data:
                    cfg['font_family'] = data
            if hasattr(self, 'sp_text_color_btn'):
                cfg['text_color'] = getattr(self.settings, 'game_overlay_text_color', '#ffffff')
            if hasattr(self, 'balloon_hide_sld'):
                cfg['balloon_hide_after'] = self._get_slider_real(self.balloon_hide_sld)
            if hasattr(self, 'balloon_opacity_sld'):
                cfg['balloon_bg_opacity'] = self._get_slider_real(self.balloon_opacity_sld)
        # theme: save theme key
        if mode == 'theme' and hasattr(self, 'theme_combo'):
            cfg['theme'] = self.theme_combo.currentData() or 'default'
        # character: save character-specific (ไม่เช็ค isVisible)
        if mode == 'character':
            if hasattr(self, 'char_font_size_sld'):
                cfg['font_size'] = self._get_slider_real(self.char_font_size_sld)

    def _load_mode_config(self, mode):
        """load values from mode_configs[mode] → apply to flat settings + ALL widgets

        ★ server อ่านจาก mode_configs ก่อน → fallback flat
        ★ widgets ต้อง sync ด้วย — แยกตาม mode (default/theme vs special vs character)
        """
        configs = getattr(self.settings, 'game_overlay_mode_configs', {}) or {}
        cfg = dict(configs.get(mode, {}))
        # apply to flat settings (server จะได้อ่านถูก)
        for key, val in cfg.items():
            flat_key = f'game_overlay_{key}'
            if hasattr(self.settings, flat_key):
                setattr(self.settings, flat_key, val)

        # ★ default/theme widgets
        if mode in ('default', 'theme'):
            if 'font_family' in cfg and hasattr(self, 'font_combo'):
                for i in range(self.font_combo.count()):
                    if self.font_combo.itemData(i) == cfg['font_family']:
                        self.font_combo.setCurrentIndex(i)
                        break
            if 'font_size' in cfg and hasattr(self, 'font_size_sld'):
                self._set_slider(self.font_size_sld, cfg['font_size'])
            if 'emote_size' in cfg and hasattr(self, 'emote_size_sld'):
                self._set_slider(self.emote_size_sld, cfg['emote_size'])
            if 'text_color' in cfg and hasattr(self, 'text_color_btn'):
                self.settings.game_overlay_text_color = cfg['text_color']
                self.text_color_btn._update_swatch()
            if 'box_enabled' in cfg and hasattr(self, 'box_cb'):
                self.box_cb.setChecked(bool(cfg['box_enabled']))
            if 'text_stroke' in cfg and hasattr(self, 'stroke_cb'):
                self.stroke_cb.setChecked(bool(cfg['text_stroke']))
            if 'text_shadow' in cfg and hasattr(self, 'shadow_cb'):
                self.shadow_cb.setChecked(bool(cfg['text_shadow']))

        # ★ special widgets (balloon-specific)
        elif mode == 'special':
            if 'font_size' in cfg and hasattr(self, 'sp_font_size_sld'):
                self._set_slider(self.sp_font_size_sld, cfg['font_size'])
            if 'font_family' in cfg and hasattr(self, 'sp_font_combo'):
                for i in range(self.sp_font_combo.count()):
                    if self.sp_font_combo.itemData(i) == cfg['font_family']:
                        self.sp_font_combo.setCurrentIndex(i)
                        break
            if 'text_color' in cfg and hasattr(self, 'sp_text_color_btn'):
                self.settings.game_overlay_text_color = cfg['text_color']
                self.sp_text_color_btn._update_swatch()
            if 'balloon_hide_after' in cfg and hasattr(self, 'balloon_hide_sld'):
                self._set_slider(self.balloon_hide_sld, cfg['balloon_hide_after'])
            if 'balloon_bg_opacity' in cfg and hasattr(self, 'balloon_opacity_sld'):
                self._set_slider(self.balloon_opacity_sld, cfg['balloon_bg_opacity'])

        # ★ character widgets
        elif mode == 'character':
            if 'font_size' in cfg and hasattr(self, 'char_font_size_sld'):
                self._set_slider(self.char_font_size_sld, cfg['font_size'])
            if 'text_color' in cfg:
                self.settings.game_overlay_text_color = cfg['text_color']
                if hasattr(self, 'text_color_btn'):
                    self.text_color_btn._update_swatch()

    def _on_appearance_change(self, mode):
        """radio ถูก toggle — save old mode config → load new mode config → update overlay

        ★ แต่ละ mode มี styling ของตัวเอง — save ค่าปัจจุบันก่อนสลับ
        """
        # ★ save current mode config (ก่อนสลับ)
        old_mode = getattr(self.settings, 'game_overlay_appearance_mode', 'default')
        if old_mode != mode:
            self._save_mode_config()
        # ★ set new mode
        self.settings.game_overlay_appearance_mode = mode
        if mode == "special":
            self.settings.game_overlay_balloon_mode = True
            self.settings.game_overlay_character_mode = False
        elif mode == "character":
            self.settings.game_overlay_balloon_mode = False
            self.settings.game_overlay_character_mode = True
        else:
            self.settings.game_overlay_balloon_mode = False
            self.settings.game_overlay_character_mode = False
        # ★ load new mode config → apply to widgets (block _save_mode_config during load)
        self._loading = True
        self._load_mode_config(mode)
        self._loading = False
        # sync balloon checkbox
        if hasattr(self, 'balloon_cb'):
            self.balloon_cb.blockSignals(True)
            self.balloon_cb.setChecked(bool(self.settings.game_overlay_balloon_mode))
            self.balloon_cb.blockSignals(False)
        self._update_appearance_visibility(mode)
        self._live_update()

    def _on_css_change(self):
        """debounce custom CSS change (500ms)"""
        if self._css_timer:
            self._css_timer.stop()
        self._css_timer = QTimer(self)
        self._css_timer.setSingleShot(True)
        self._css_timer.timeout.connect(self._commit_css)
        self._css_timer.start(500)

    def _commit_css(self):
        css = self.css_edit.toPlainText()
        self.settings.game_overlay_custom_css = css
        self._live_update()

    # ════════════════════════════════════════════════════════════
    # Loop Demo
    # ════════════════════════════════════════════════════════════
    def _toggle_demo(self):
        """toggle Loop Demo — start/stop"""
        go = getattr(self.parent_app, '_game_overlay', None)
        if not go or not go.is_running:
            self.demo_btn.setText("🔒 ต้องเปิด Overlay ก่อน")
            self.demo_btn.setEnabled(False)
            self.demo_btn.setStyleSheet(self._demo_btn_style(False))
            return
        try:
            go.toggle_demo()
        except Exception as e:
            logger.error(f"toggle_demo failed: {e}")
        # sync UI ตามสถานะจริง
        QTimer.singleShot(100, self._refresh_demo_btn_state)

    def _refresh_demo_btn_state(self):
        """sync ปุ่ม Loop Demo ตามสถานะ Game Overlay จริง"""
        try:
            go = getattr(self.parent_app, '_game_overlay', None)
            running = go is not None and getattr(go, 'is_running', False)
            if not running:
                self.demo_btn.setText("🔒 ต้องเปิด Overlay ก่อน")
                self.demo_btn.setEnabled(False)
                self.demo_btn.setStyleSheet(self._demo_btn_style(False))
                return
            self.demo_btn.setEnabled(True)
            is_demo = bool(getattr(go, '_demo_running_state', False))
            if is_demo:
                self.demo_btn.setText("⏸ หยุด Loop Demo")
                self.demo_btn.setStyleSheet(self._demo_btn_style(True))
            else:
                self.demo_btn.setText("▶ เริ่ม Loop Demo")
                self.demo_btn.setStyleSheet(self._demo_btn_style(False))
        except Exception as e:
            logger.debug(f"_refresh_demo_btn_state error: {e}")

    def _on_demo_interval_change(self, value):
        """slider interval change — update label + save"""
        interval = value / 10.0
        self.demo_interval_lbl.setText(f"{interval:.1f}s")
        self.settings.game_overlay_demo_interval = interval
        try:
            from settings import save_settings
            save_settings(self.settings)
        except Exception:
            pass
        # ถ้า demo กำลังรันอยู่ → restart ด้วย interval ใหม่
        go = getattr(self.parent_app, '_game_overlay', None)
        if go and go.is_running and getattr(go, '_demo_running_state', False):
            try:
                go.start_demo(interval)
            except Exception:
                pass

    # ════════════════════════════════════════════════════════════
    # CSS Guide
    # ════════════════════════════════════════════════════════════
    def _show_css_guide(self):
        """แสดง CSS Guide (popup)"""
        try:
            from settings import get_base_dir
            guide_path = os.path.join(get_base_dir(), "game_overlay_css_guide.md")
            with open(guide_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            content = "ไม่พบไฟล์ game_overlay_css_guide.md"
        dlg = QDialog(self)
        dlg.setWindowTitle("📖 Game Overlay — CSS Guide")
        dlg.setGeometry(300, 150, 720, 600)
        dlg.setStyleSheet(f"background: {COL_BG};")
        dl = QVBoxLayout(dlg)
        dl.setContentsMargins(16, 16, 16, 16)
        edit = QTextEdit()
        edit.setReadOnly(True)
        edit.setPlainText(content)
        edit.setStyleSheet(f"""
            QTextEdit {{
                background: {COL_CARD}; color: {COL_TEXT};
                border: 1px solid {COL_BORDER}; border-radius: 6px;
                padding: 10px; font-family: Consolas, monospace; font-size: 13px;
            }}
        """)
        dl.addWidget(edit)
        btn = QPushButton("ปิด")
        btn.clicked.connect(dlg.accept)
        dl.addWidget(btn)
        dlg.exec()

    # ════════════════════════════════════════════════════════════
    # Save
    # ════════════════════════════════════════════════════════════
    def _save_go_hotkey(self, which, hotkey):
        """save hotkey ที่จับได้จาก binder (which = 'toggle' | 'edit') + re-register"""
        if not self.settings:
            return
        hk = (hotkey or "").strip().lower()
        # validate
        try:
            import keyboard
            keyboard.parse_hotkey(hk)
        except Exception:
            QMessageBox.warning(self, "Hotkey ไม่ถูกต้อง",
                f"รูปแบบ hotkey ไม่ถูกต้อง: {hk}\n\n"
                "ตัวอย่างที่ถูก: f13, ctrl+f24, shift+f1, ctrl+shift+g")
            return
        if which == 'toggle':
            self.settings.game_overlay_hotkey = hk
        else:
            self.settings.game_overlay_hotkey_edit = hk
        try:
            from settings import save_settings
            save_settings(self.settings)
        except Exception as e:
            logger.debug(f"go hotkey save failed: {e}")
        # re-register hotkeys ทันที
        if hasattr(self.parent_app, '_reregister_hotkeys'):
            self.parent_app._reregister_hotkeys()

    def _save(self):
        """save settings + update overlay + re-register hotkeys + close"""
        if self.settings:
            # ★ save hotkey fields (อ่านจาก binder button._hotkey)
            if hasattr(self, 'go_hk_toggle'):
                hk_t = (getattr(self.go_hk_toggle, '_hotkey', '') or 'ctrl+shift+g').strip().lower()
                hk_e = (getattr(self.go_hk_edit, '_hotkey', '') or 'ctrl+shift+h').strip().lower()
                # ★ validate hotkey format (รองรับ F1-F35)
                try:
                    import keyboard
                    keyboard.parse_hotkey(hk_t)
                    keyboard.parse_hotkey(hk_e)
                except Exception:
                    QMessageBox.warning(self, "Hotkey ไม่ถูกต้อง",
                        f"รูปแบบ hotkey ไม่ถูกต้อง:\nToggle: {hk_t}\nEdit: {hk_e}\n\n"
                        "ตัวอย่างที่ถูก: f13, ctrl+f24, shift+f1, ctrl+shift+g")
                    return
                self.settings.game_overlay_hotkey = hk_t
                self.settings.game_overlay_hotkey_edit = hk_e
            try:
                from settings import save_settings
                save_settings(self.settings)
            except Exception as e:
                logger.error(f"Save failed: {e}")
        go = getattr(self.parent_app, '_game_overlay', None)
        if go and go.is_running:
            try:
                go.update_settings()
            except Exception:
                pass
        # ★ re-register hotkeys (เผื่อ user เปลี่ยน)
        if hasattr(self.parent_app, '_reregister_hotkeys'):
            self.parent_app._reregister_hotkeys()
        self.accept()

    def closeEvent(self, event):
        """save on close"""
        if self.settings:
            # ★ save hotkey fields (อ่านจาก binder button._hotkey)
            if hasattr(self, 'go_hk_toggle'):
                self.settings.game_overlay_hotkey = (getattr(self.go_hk_toggle, '_hotkey', '') or 'ctrl+shift+g').strip().lower()
                self.settings.game_overlay_hotkey_edit = (getattr(self.go_hk_edit, '_hotkey', '') or 'ctrl+shift+h').strip().lower()
            try:
                from settings import save_settings
                save_settings(self.settings)
            except Exception:
                pass
        # ★ re-register hotkeys
        if hasattr(self.parent_app, '_reregister_hotkeys'):
            self.parent_app._reregister_hotkeys()
        super().closeEvent(event)


# ── helpers ──
def _is_light(hex_color):
    """เช็คว่าสีสว่างหรือไม่ (สำหรับเลือก text color บน color swatch)"""
    try:
        c = QColor(hex_color)
        # perceived brightness
        return (c.red() * 299 + c.green() * 587 + c.blue() * 114) / 1000 > 128
    except Exception:
        return False
