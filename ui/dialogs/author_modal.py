"""author_modal.py — Author Modal dialog (คลิกชื่อ user → ดูข้อมูล)

รวม: สถานิติ + donation summary + message history (load more) + export log + block/rename
★ Redesigned UI: hero profile (avatar สี + ชื่อใหญ่ + pills) + stat tiles + chat bubbles
★ Fixed layout — แต่ละ section มีที่คงที่ ไม่ขยายเละเมื่อข้อมูลไม่ครบ
"""
import logging
from datetime import datetime
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QWidget, QFrame, QLabel, QPushButton, QLineEdit, QVBoxLayout,
    QHBoxLayout, QScrollArea, QMessageBox, QFileDialog, QMenu, QSizePolicy,
    QGridLayout,
)
from ui.theme import COLOR_CARD, COLOR_BORDER

logger = logging.getLogger("author_modal")

EVENT_ICONS = {
    'sub': '⭐', 'resub': '🔁', 'bits': '💎', 'raid': '🚀',
    'follow': '❤️', 'superchat': '💎', 'gift': '🎁', 'membership': '🎖️',
    'sponsor': '🤝', 'donate': '💰', 'tip': '💰', 'like': '👍',
    'share': '📢', 'subgift': '🎁',
}

# ★ สีประจำแพลตฟอร์ม (pills)
PLATFORM_COLORS = {
    'twitch': ('#9146FF', '#FFFFFF'),
    'youtube': ('#FF0000', '#FFFFFF'),
    'mylive': ('#0EA5E9', '#FFFFFF'),
    'tiktok': ('#EC4899', '#FFFFFF'),
    'kick': ('#53FC18', '#0B0C0E'),
}

# ★ ชุดสี avatar (ไล่ตาม hash ขนาดชื่อ — คนละชื่อได้คนละสี คนเดิมได้สีเดิม)
AVATAR_GRADIENTS = [
    ("#7C3AED", "#C084FC"),  # ม่วง
    ("#0EA5E9", "#67E8F9"),  # ฟ้า
    ("#F43F5E", "#FDA4AF"),  # ชมพูแดง
    ("#10B981", "#6EE7B7"),  # เขียว
    ("#F59E0B", "#FDE68A"),  # ทอง
    ("#EC4899", "#F9A8D4"),  # ชมพู
    ("#6366F1", "#A5B4FC"),  # คราม
    ("#14B8A6", "#5EEAD4"),  # เขียวหัวเป็ด
]

BG_DARK = "#0A0E1A"
CARD = "#111827"
CARD_BORDER = "#1F2937"


def _avatar_style(name: str) -> str:
    """สี gradient ของ avatar ตาม hash ชื่อ"""
    grad = AVATAR_GRADIENTS[hash(name.lower()) % len(AVATAR_GRADIENTS)]
    return f"qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {grad[0]}, stop:1 {grad[1]})"


def _make_section(title_text):
    """สร้าง section card + layout — fixed structure"""
    frame = QFrame()
    frame.setObjectName("Section")
    frame.setStyleSheet(
        f"QFrame#Section {{ background-color: {CARD}; border: 1px solid {CARD_BORDER}; "
        f"border-radius: 10px; }}"
    )
    frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(12, 10, 12, 10)
    layout.setSpacing(6)
    title = QLabel(title_text)
    title.setStyleSheet("color: #9CA3AF; font-size: 11px; font-weight: 700; "
                        "letter-spacing: 1px; text-transform: uppercase;")
    layout.addWidget(title)
    return frame, layout


class AuthorModal(QDialog):
    """Author Modal — แสดงข้อมูล user + stats + donate + history + actions"""

    def __init__(self, parent_app, author: str):
        super().__init__(parent_app if isinstance(parent_app, QWidget) else None)
        self.parent_app = parent_app
        self.settings = getattr(parent_app, 'settings', None)
        self.author = author
        self._msg_limit = 20
        self._msg_offset = 0
        self._msg_total = 0
        self.setWindowTitle(f"👤 {author}")
        self.setFixedWidth(520)
        self.setMinimumHeight(500)
        self.setStyleSheet(f"QDialog {{ background: {BG_DARK}; }}")
        self._build_ui()
        self._load_data()

    # ------------------------------------------------------------------ #
    # UI
    # ------------------------------------------------------------------ #
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Hero header: avatar + ชื่อ + pills + ปุ่มปิด (fixed) ──
        header = QFrame()
        header.setStyleSheet(
            f"background-color: {CARD}; border-bottom: 1px solid {CARD_BORDER};"
        )
        h = QHBoxLayout(header)
        h.setContentsMargins(14, 12, 10, 12)
        h.setSpacing(12)

        # ★ avatar วงกลมตัวอักษรแรก
        avatar = QLabel(self.author[:1].upper() if self.author else "?")
        avatar.setFixedSize(52, 52)
        avatar.setAlignment(Qt.AlignCenter)
        avatar.setStyleSheet(
            f"background-color: {_avatar_style(self.author)}; color: white; "
            f"font-size: 24px; font-weight: 800; border-radius: 26px; border: none;"
        )
        h.addWidget(avatar)

        name_col = QVBoxLayout()
        name_col.setSpacing(3)
        renames = getattr(self.settings, 'user_renames', {}) or {}
        display = renames.get(self.author.lower(), '') or self.author
        self.title_label = QLabel(display)
        self.title_label.setStyleSheet(
            "font-size: 17px; font-weight: 800; color: #F9FAFB; border: none; background: transparent;")
        self.title_label.setWordWrap(True)
        name_col.addWidget(self.title_label)
        if renames.get(self.author.lower()):
            sub = QLabel(f"@{self.author}")
            sub.setStyleSheet("font-size: 11px; color: #6B7280; border: none; background: transparent;")
            name_col.addWidget(sub)
        # ★ แถว pills: สถานะบล็อก + แพลตฟอร์ม (เติมทีหลังตอนโหลดข้อมูล)
        self.pill_row = QHBoxLayout()
        self.pill_row.setSpacing(5)
        self.status_pill = QLabel("")
        self.status_pill.setStyleSheet("border: none; background: transparent;")
        self.status_pill.setVisible(False)
        self.pill_row.addWidget(self.status_pill)
        self.plat_pills_label = QLabel("")
        self.plat_pills_label.setStyleSheet("border: none; background: transparent;")
        self.pill_row.addWidget(self.plat_pills_label)
        self.pill_row.addStretch()
        name_col.addLayout(self.pill_row)
        h.addLayout(name_col, 1)

        btn_close = QPushButton("✕")
        btn_close.setObjectName("IconButton")
        btn_close.setFixedSize(30, 30)
        # ★ กฎเหล็กปุ่มไอคอนเล็ก: padding:0 + min-height:0
        btn_close.setStyleSheet(
            "font-size: 14px; padding: 0; min-height: 0; color: #9CA3AF; "
            "background: transparent; border: none; border-radius: 5px;")
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.clicked.connect(self.reject)
        h.addWidget(btn_close, 0, Qt.AlignTop)
        layout.addWidget(header)

        # ── Scrollable content ──
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet(f"QScrollArea {{ border: none; background: {BG_DARK}; }}")
        self.container = QWidget()
        self.container.setStyleSheet(f"background: {BG_DARK};")
        self.cl = QVBoxLayout(self.container)
        self.cl.setContentsMargins(14, 12, 14, 12)
        self.cl.setSpacing(10)
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll, 1)

        # ── Bottom action bar (fixed) ──
        bottom = QFrame()
        bottom.setStyleSheet(
            f"background-color: {CARD}; border-top: 1px solid {CARD_BORDER};")
        bl = QHBoxLayout(bottom)
        bl.setContentsMargins(14, 8, 14, 8)
        bl.setSpacing(6)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("เปลี่ยนชื่อ...")
        self.name_input.setFixedHeight(32)
        self.name_input.setMinimumWidth(70)
        self.name_input.setStyleSheet(
            f"QLineEdit {{ background: {BG_DARK}; color: #E5E7EB; border: 1px solid {CARD_BORDER}; "
            f"border-radius: 6px; padding: 0 8px; font-size: 12px; }}"
            f"QLineEdit:focus {{ border-color: #7C3AED; }}"
        )
        renames = getattr(self.settings, 'user_renames', {}) or {}
        self.name_input.setText(renames.get(self.author.lower(), ''))
        bl.addWidget(self.name_input, 1)

        self.btn_rename = QPushButton("💾 เปลี่ยนชื่อ")
        self.btn_rename.setFixedHeight(32)
        self.btn_rename.setCursor(Qt.PointingHandCursor)
        self.btn_rename.setStyleSheet(
            "QPushButton { background: #1E293B; color: #E2E8F0; border: 1px solid #334155; "
            "border-radius: 6px; padding: 0 10px; font-size: 12px; font-weight: 600; }"
            "QPushButton:hover { background: #334155; }")
        self.btn_rename.clicked.connect(self._do_rename)
        bl.addWidget(self.btn_rename)

        self.btn_block = QPushButton("🚫 บล็อก")
        self.btn_block.setFixedHeight(32)
        self.btn_block.setCursor(Qt.PointingHandCursor)
        self.btn_block.clicked.connect(self._show_block_menu)
        bl.addWidget(self.btn_block)

        self.btn_export = QPushButton("📥 Export")
        self.btn_export.setFixedHeight(32)
        self.btn_export.setCursor(Qt.PointingHandCursor)
        self.btn_export.setStyleSheet(
            "QPushButton { background: #1E293B; color: #E2E8F0; border: 1px solid #334155; "
            "border-radius: 6px; padding: 0 10px; font-size: 12px; font-weight: 600; }"
            "QPushButton:hover { background: #334155; }")
        self.btn_export.clicked.connect(self._export_log)
        bl.addWidget(self.btn_export)
        layout.addWidget(bottom)

        self._update_block_button()

    # ------------------------------------------------------------------ #
    # Helpers (visual)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _pill(text, bg, fg="#FFFFFF"):
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"background-color: {bg}; color: {fg}; font-size: 10px; font-weight: 700; "
            f"border-radius: 8px; padding: 1px 8px; border: none;")
        return lbl

    def _stat_tile(self, icon, value, label):
        """การ์ดสถิติเล็ก (icon + เลข + คำอธิบาย)"""
        tile = QFrame()
        tile.setStyleSheet(
            f"QFrame {{ background: {CARD}; border: 1px solid {CARD_BORDER}; "
            f"border-radius: 10px; }}")
        v = QVBoxLayout(tile)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(2)
        icon_lbl = QLabel(icon)
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet("font-size: 16px; border: none; background: transparent;")
        val_lbl = QLabel(str(value))
        val_lbl.setAlignment(Qt.AlignCenter)
        val_lbl.setStyleSheet(
            "font-size: 16px; font-weight: 800; color: #F9FAFB; "
            "border: none; background: transparent;")
        cap_lbl = QLabel(label)
        cap_lbl.setAlignment(Qt.AlignCenter)
        cap_lbl.setStyleSheet(
            "font-size: 10px; color: #6B7280; border: none; background: transparent;")
        v.addWidget(icon_lbl)
        v.addWidget(val_lbl)
        v.addWidget(cap_lbl)
        return tile

    def _body_label(self, text, bold=False):
        lbl = QLabel(text)
        style = "color: #D1D5DB; font-size: 12px; border: none; background: transparent;"
        if bold:
            style += " font-weight: 700; color: #F59E0B;"
        lbl.setStyleSheet(style)
        lbl.setWordWrap(True)
        lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        return lbl

    # ------------------------------------------------------------------ #
    # Data loading
    # ------------------------------------------------------------------ #
    def _load_data(self):
        app = self.parent_app
        author = self.author

        msg_count = 0
        platforms = set()
        if app and hasattr(app, 'message_history') and app.message_history:
            try:
                msg_count = app.message_history.count(author)
                platforms = app.message_history.platforms(author)
                self._msg_total = msg_count
            except Exception:
                pass

        events = []
        if app and hasattr(app, 'event_log') and app.event_log:
            try:
                events = app.event_log.get_by_author(author)
            except Exception:
                pass

        donate = {}
        if app and hasattr(app, 'donate_tracker') and app.donate_tracker:
            try:
                donate = app.donate_tracker.get_user(author.lower())
            except Exception:
                pass

        # ═══ Hero: platform pills ═══
        if platforms:
            self.plat_pills_label.setText("  ".join(
                f"● {p.upper()}" for p in sorted(platforms)))
            # ★ ใส่สีด้วย rich text (QLabel เดียวหลายสี)
            parts = []
            for p in sorted(platforms):
                color = PLATFORM_COLORS.get(p, ('#6B7280',))[0]
                parts.append(
                    f"<span style='background-color:{color}; color:#FFFFFF; "
                    f"font-size:10px; font-weight:700; border-radius:8px; "
                    f"padding:1px 8px;'>&nbsp;{p.upper()}&nbsp;</span>")
            self.plat_pills_label.setTextFormat(Qt.RichText)
            self.plat_pills_label.setText("&nbsp;".join(parts))

        # ═══ Stat tiles: ข้อความ / events / donation รวม ═══
        total_donate = donate.get('total_donate_count', 0) if donate else 0
        tiles = QGridLayout()
        tiles.setSpacing(8)
        tiles.addWidget(self._stat_tile("💬", msg_count, "ข้อความ"), 0, 0)
        tiles.addWidget(self._stat_tile("🎉", len(events), "อีเวนต์"), 0, 1)
        tiles.addWidget(self._stat_tile("💰", total_donate, "สนับสนุน (ครั้ง)"), 0, 2)
        self.cl.addLayout(tiles)

        # ═══ SECTION: Donation ═══
        s2, l2 = _make_section("💎 การสนับสนุน")
        has_donate = False
        for plat, fields in sorted((donate or {}).items()):
            if plat == 'total_donate_count':
                continue
            parts = []
            for field, value in sorted(fields.items()):
                if not value or field == 'gift_count':
                    continue
                if field == 'bits':
                    parts.append(f"{value} bits")
                elif field == 'superchat':
                    parts.append(f"{value} THB")
                elif field == 'sub_count':
                    parts.append(f"{value} sub")
                elif field == 'subgift_count':
                    parts.append(f"{value} gift")
                elif field == 'membership_count':
                    parts.append(f"{value} membership")
                elif field == 'gift_diamonds':
                    parts.append(f"{value} diamonds")
                else:
                    parts.append(f"{value} {field}")
            if parts:
                plat_color = PLATFORM_COLORS.get(plat, ('#374151', '#FFFFFF'))[0]
                row = QHBoxLayout()
                row.setSpacing(6)
                row.addWidget(self._pill(plat.upper(), plat_color))
                row.addWidget(self._body_label(" · ".join(parts)), 1)
                l2.addLayout(row)
                has_donate = True
        if total_donate:
            l2.addWidget(self._body_label(f"รวมทั้งหมด {total_donate} ครั้ง", bold=True))
            has_donate = True
        if events:
            btn_dh = QPushButton("📋 ดูประวัติทั้งหมด")
            btn_dh.setStyleSheet(
                "color: #06B6D4; font-size: 12px; border: none; padding: 0; "
                "min-height: 0; text-align: left;")
            btn_dh.setCursor(Qt.PointingHandCursor)
            btn_dh.clicked.connect(self._show_donate_history)
            l2.addWidget(btn_dh)
        if not has_donate:
            l2.addWidget(self._body_label("ยังไม่มีบันทึกการสนับสนุน"))
        self.cl.addWidget(s2)

        # ═══ SECTION: Events (แยกจาก stat — แสดงเฉพาะมีข้อมูล) ═══
        if events:
            event_counts = {}
            for e in events:
                event_counts[e.event] = event_counts.get(e.event, 0) + 1
            s4, l4 = _make_section("🏆 กิจกรรม")
            row = QHBoxLayout()
            row.setSpacing(6)
            for ev, cnt in sorted(event_counts.items(), key=lambda x: -x[1])[:6]:
                icon = EVENT_ICONS.get(ev, '🎉')
                w = QLabel(f"{icon} {cnt}")
                w.setAlignment(Qt.AlignCenter)
                w.setStyleSheet(
                    f"background-color: {BG_DARK}; color: #D1D5DB; font-size: 12px; "
                    f"font-weight: 700; border-radius: 8px; padding: 3px 8px; border: none;")
                row.addWidget(w)
            row.addStretch()
            l4.addLayout(row)
            self.cl.addWidget(s4)

        # ═══ SECTION: ข้อความล่าสุด ═══
        s3, l3 = _make_section(f"📝 ข้อความล่าสุด ({min(self._msg_limit, self._msg_total)} / {self._msg_total})")
        self._msg_container = QVBoxLayout()
        self._msg_container.setSpacing(4)
        l3.addLayout(self._msg_container)
        self.btn_load_more = QPushButton("📥 โหลดเพิ่ม +20")
        self.btn_load_more.setStyleSheet(
            "color: #06B6D4; font-size: 12px; border: none; padding: 0; min-height: 0;")
        self.btn_load_more.setCursor(Qt.PointingHandCursor)
        self.btn_load_more.clicked.connect(self._load_more_messages)
        l3.addWidget(self.btn_load_more)
        self.cl.addWidget(s3)

        self._load_messages()
        self.cl.addStretch()

    def _load_messages(self):
        """โหลดข้อความลงใน history section — สไตล์ chat bubble"""
        app = self.parent_app
        messages = []
        if app and hasattr(app, 'message_history') and app.message_history:
            try:
                messages = app.message_history.get_messages_by_author(
                    self.author, limit=self._msg_limit, offset=self._msg_offset
                )
            except Exception:
                pass

        if not messages and self._msg_offset == 0:
            empty = QLabel("ยังไม่มีข้อความ")
            empty.setStyleSheet(
                "color: #4B5563; font-size: 12px; border: none; "
                "background: transparent; padding: 4px;")
            self._msg_container.addWidget(empty)
            self.btn_load_more.setVisible(False)
            return

        for msg in messages:
            plat = msg.get('platform', '?')
            text = msg.get('text', '')
            emotes = msg.get('emotes', '')
            if not text and emotes:
                text = f"🖼️ {emotes}"
            elif not text:
                text = "(ว่าง)"
            bubble = QFrame()
            bubble.setStyleSheet(
                f"QFrame {{ background: {BG_DARK}; border: 1px solid {CARD_BORDER}; "
                f"border-left: 3px solid {PLATFORM_COLORS.get(plat, ('#6B7280',))[0]}; "
                f"border-radius: 6px; }}")
            bl = QHBoxLayout(bubble)
            bl.setContentsMargins(8, 5, 8, 5)
            bl.setSpacing(6)
            tag = QLabel(plat.upper())
            tag.setStyleSheet(
                f"color: {PLATFORM_COLORS.get(plat, ('#6B7280',))[0]}; font-size: 9px; "
                f"font-weight: 800; border: none; background: transparent;")
            tag.setFixedWidth(44)
            bl.addWidget(tag, 0, Qt.AlignTop)
            body = QLabel(text)
            body.setStyleSheet(
                "color: #E5E7EB; font-size: 12px; border: none; background: transparent;")
            body.setWordWrap(True)
            bl.addWidget(body, 1)
            self._msg_container.addWidget(bubble)

        self.btn_load_more.setVisible(self._msg_offset + self._msg_limit < self._msg_total)

    def _load_more_messages(self):
        self._msg_offset += self._msg_limit
        self._load_messages()

    # ------------------------------------------------------------------ #
    # Actions (logic เดิม — ไม่แตะ)
    # ------------------------------------------------------------------ #
    def _show_donate_history(self):
        """แสดงหน้าประวัติ donation"""
        app = self.parent_app
        events = []
        if app and hasattr(app, 'event_log') and app.event_log:
            try:
                all_events = app.event_log.get_by_author(self.author)
                events = [e for e in all_events if e.event in
                          ('bits', 'superchat', 'donate', 'tip', 'gift', 'sub', 'resub', 'membership', 'subgift')]
            except Exception:
                pass

        if not events:
            QMessageBox.information(self, "Donation", "ยังไม่มีประวัติ donation")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(f"💎 ประวัติ Donation: {self.author}")
        dlg.setFixedWidth(480)
        dlg.setMinimumHeight(350)
        dlg.setStyleSheet(f"QDialog {{ background: {BG_DARK}; }}")
        dl = QVBoxLayout(dlg)
        dl.setContentsMargins(16, 16, 16, 16)
        dl.setSpacing(4)

        header = QLabel(f"{'วันที่':12s} | {'Platform':8s} | {'Type':12s} | ยอด")
        header.setStyleSheet("color: #f59e0b; font-size: 12px; font-weight: 700;")
        dl.addWidget(header)

        currency_totals = {}
        for e in reversed(events):
            ts = e.timestamp[:10]
            icon = EVENT_ICONS.get(e.event, '🎉')
            amount_str = str(e.amount) if e.amount else "—"
            row = QLabel(f"{ts:12s} | {e.platform:8s} | {icon} {e.event:10s} | {amount_str}")
            row.setStyleSheet("color: #d1d5db; font-size: 12px;")
            dl.addWidget(row)
            if e.amount and e.event in ('bits',):
                currency_totals['bits'] = currency_totals.get('bits', 0) + e.amount
            elif e.amount and e.event in ('superchat', 'donate', 'tip'):
                currency_totals['THB'] = currency_totals.get('THB', 0) + e.amount
            elif e.event in ('sub', 'resub'):
                currency_totals['sub'] = currency_totals.get('sub', 0) + 1
            elif e.event in ('membership',):
                currency_totals['membership'] = currency_totals.get('membership', 0) + 1
            elif e.event in ('gift', 'subgift'):
                currency_totals['gift'] = currency_totals.get('gift', 0) + 1

        dl.addSpacing(8)
        summary = QLabel("📊 สรุปยอดรวม (แยกสกุล):")
        summary.setStyleSheet("color: #f59e0b; font-size: 13px; font-weight: 700;")
        dl.addWidget(summary)

        for cur, total in sorted(currency_totals.items()):
            if cur in ('sub', 'membership', 'gift'):
                lbl = QLabel(f"  ⭐ {cur}: {total} ครั้ง")
            else:
                lbl = QLabel(f"  💰 {cur}: {total}")
            lbl.setStyleSheet("color: #10b981; font-size: 13px; font-weight: 600;")
            dl.addWidget(lbl)

        dl.addStretch()
        btn = QPushButton("ปิด")
        btn.clicked.connect(dlg.accept)
        dl.addWidget(btn)
        dlg.exec()

    def _do_rename(self):
        new_name = self.name_input.text().strip()
        if not new_name or not self.settings:
            return
        renames = getattr(self.settings, 'user_renames', {}) or {}
        renames[self.author.lower()] = new_name
        self.settings.user_renames = renames
        try:
            from settings import save_settings
            save_settings(self.settings)
        except Exception:
            pass
        QMessageBox.information(self, "เปลี่ยนชื่อ", f"เปลี่ยนชื่อ {self.author} → {new_name}")
        # ★ sync ชื่อที่แสดงใน header ทันที
        self.title_label.setText(new_name)

    def _show_block_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: #131726; color: #e5e7eb; border: 1px solid #2a2f45; padding: 4px; } QMenu::item { padding: 6px 20px; } QMenu::item:selected { background-color: #1a1f33; }")
        status = self._get_block_status()
        if status == "block_all":
            menu.addAction("✅ ปลดบล็อก")
            menu.addAction("🔇 เปลี่ยนเป็น บล็อก TTS")
        elif status == "block_tts":
            menu.addAction("✅ ปลดบล็อก")
            menu.addAction("🚫 เปลี่ยนเป็น บล็อกทุกอย่าง")
        else:
            menu.addAction("🚫 บล็อกทุกอย่าง (ไม่แสดง + ไม่อ่าน)")
            menu.addAction("🔇 บล็อก TTS (แสดงแต่ไม่อ่าน)")
        action = menu.exec(self.btn_block.mapToGlobal(self.btn_block.rect().bottomLeft()))
        if not action:
            return
        txt = action.text()
        if "ปลด" in txt:
            self._do_unblock()
        elif "TTS" in txt:
            self._do_block(tts_only=True)
        else:
            self._do_block(tts_only=False)

    def _get_block_status(self):
        app = self.parent_app
        if app and hasattr(app, '_get_block_status'):
            try:
                return app._get_block_status(self.author)
            except Exception:
                pass
        return None

    def _do_block(self, tts_only=False):
        app = self.parent_app
        if app and hasattr(app, '_block_user_from_chat'):
            try:
                app._block_user_from_chat(self.author, tts_only=tts_only)
            except Exception:
                pass
        self._update_block_button()

    def _do_unblock(self):
        app = self.parent_app
        if app and hasattr(app, '_unblock_user'):
            try:
                app._unblock_user(self.author)
            except Exception:
                pass
        self._update_block_button()

    def _update_block_button(self):
        status = self._get_block_status()
        if status == "block_all":
            self.btn_block.setText("🚫 บล็อกอยู่")
            self.btn_block.setStyleSheet(
                "background-color: #ef4444; color: white; font-weight: 700; border: none; "
                "border-radius: 6px; padding: 0 10px; font-size: 12px;")
            pill_text, pill_bg = "บล็อกทั้งหมด", "#ef4444"
        elif status == "block_tts":
            self.btn_block.setText("🔇 บล็อก TTS")
            self.btn_block.setStyleSheet(
                "background-color: #f59e0b; color: white; font-weight: 700; border: none; "
                "border-radius: 6px; padding: 0 10px; font-size: 12px;")
            pill_text, pill_bg = "บล็อก TTS", "#f59e0b"
        else:
            self.btn_block.setText("🚫 บล็อก")
            self.btn_block.setStyleSheet(
                "QPushButton { background: #1E293B; color: #E2E8F0; border: 1px solid #334155; "
                "border-radius: 6px; padding: 0 10px; font-size: 12px; font-weight: 600; }"
                "QPushButton:hover { background: #334155; }")
            pill_text, pill_bg = "", ""
        # ★ sync pill สถานะใน header
        if pill_text:
            self.status_pill.setText(pill_text)
            self.status_pill.setStyleSheet(
                f"background-color: {pill_bg}; color: white; font-size: 10px; font-weight: 700; "
                f"border-radius: 8px; padding: 1px 8px; border: none;")
            self.status_pill.setVisible(True)
        else:
            self.status_pill.setVisible(False)

    def _export_log(self):
        app = self.parent_app
        messages = []
        if app and hasattr(app, 'message_history') and app.message_history:
            try:
                messages = app.message_history.get(self.author)
            except Exception:
                pass
        if not messages:
            QMessageBox.information(self, "Export", "ยังไม่มีข้อความให้ export")
            return
        default_name = f"chat_log_{self.author}_{datetime.now().strftime('%Y%m%d')}.txt"
        path, _ = QFileDialog.getSaveFileName(self, "บันทึกไฟล์", default_name, "Text files (*.txt)")
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(f"Chat Log: {self.author}\n")
                f.write(f"Exported: {datetime.now().isoformat()}\n")
                f.write(f"Total messages: {len(messages)}\n")
                f.write("=" * 60 + "\n\n")
                for msg in messages:
                    ts = msg.get('timestamp', '')
                    plat = msg.get('platform', '?')
                    text = msg.get('text', '')
                    emotes = msg.get('emotes', '')
                    if not text and emotes:
                        text = "(emote)"
                    elif not text:
                        text = "(ว่าง)"
                    f.write(f"[{ts}] [{plat}] {text}\n")
            QMessageBox.information(self, "Export", f"บันทึกแล้ว:\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "Export", f"บันทึกไม่ได้: {e}")
