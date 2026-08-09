"""author_modal.py — Author Modal dialog (คลิกชื่อ user → ดูข้อมูล)

รวม: สถิติ + donation summary + message history (load more) + export log + block/rename
★ Fixed layout — แต่ละ section มีที่คงที่ ไม่ขยายเละเมื่อข้อมูลไม่ครบ
"""
import logging
from datetime import datetime
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QWidget, QFrame, QLabel, QPushButton, QLineEdit, QVBoxLayout,
    QHBoxLayout, QScrollArea, QMessageBox, QFileDialog, QMenu, QSizePolicy,
)
from ui.theme import COLOR_CARD, COLOR_BORDER

logger = logging.getLogger("author_modal")

EVENT_ICONS = {
    'sub': '⭐', 'resub': '🔁', 'bits': '💎', 'raid': '🚀',
    'follow': '❤️', 'superchat': '💎', 'gift': '🎁', 'membership': '🎖️',
    'sponsor': '🤝', 'donate': '💰', 'tip': '💰', 'like': '👍',
    'share': '📢', 'subgift': '🎁',
}

# ★ Section styles — consistent
SECTION_STYLE = f"""
    QFrame#Section {{
        background-color: {COLOR_CARD};
        border: 1px solid {COLOR_BORDER};
        border-radius: 8px;
    }}
"""
SECTION_TITLE_STYLE = "color: #f59e0b; font-size: 13px; font-weight: 700;"
SECTION_BODY_STYLE = "color: #d1d5db; font-size: 12px;"


def _make_section(title_text):
    """สร้าง section frame + layout — fixed structure"""
    frame = QFrame()
    frame.setObjectName("Section")
    frame.setStyleSheet(SECTION_STYLE)
    frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(14, 10, 14, 10)
    layout.setSpacing(4)
    title = QLabel(title_text)
    title.setStyleSheet(SECTION_TITLE_STYLE)
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
        self._build_ui()
        self._load_data()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header (fixed) ──
        header = QFrame()
        header.setFixedHeight(44)
        header.setStyleSheet(f"background-color: {COLOR_CARD}; border-bottom: 1px solid {COLOR_BORDER};")
        h = QHBoxLayout(header)
        h.setContentsMargins(16, 0, 12, 0)
        title = QLabel(f"👤 {self.author}")
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #f59e0b;")
        h.addWidget(title)
        h.addStretch()
        btn_close = QPushButton("✕")
        btn_close.setObjectName("IconButton")
        btn_close.setFixedSize(32, 32)
        btn_close.setStyleSheet("font-size: 16px; padding: 0px;")
        btn_close.clicked.connect(self.reject)
        h.addWidget(btn_close)
        layout.addWidget(header)

        # ── Scrollable content ──
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: #0a0e1a; }")
        self.container = QWidget()
        self.container.setStyleSheet("background: #0a0e1a;")
        self.cl = QVBoxLayout(self.container)
        self.cl.setContentsMargins(16, 12, 16, 12)
        self.cl.setSpacing(8)
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll, 1)

        # ── Bottom action bar (fixed) ──
        bottom = QFrame()
        bottom.setFixedHeight(52)
        bottom.setStyleSheet(f"background-color: {COLOR_CARD}; border-top: 1px solid {COLOR_BORDER};")
        bl = QHBoxLayout(bottom)
        bl.setContentsMargins(16, 0, 16, 0)
        bl.setSpacing(6)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("เปลี่ยนชื่อ...")
        self.name_input.setFixedHeight(30)
        self.name_input.setMinimumWidth(80)
        renames = getattr(self.settings, 'user_renames', {}) or {}
        self.name_input.setText(renames.get(self.author.lower(), ''))
        bl.addWidget(self.name_input, 1)

        self.btn_rename = QPushButton("💾 เปลี่ยนชื่อ")
        self.btn_rename.setFixedHeight(30)
        self.btn_rename.clicked.connect(self._do_rename)
        bl.addWidget(self.btn_rename)

        self.btn_block = QPushButton("🚫 บล็อก")
        self.btn_block.setFixedHeight(30)
        self.btn_block.clicked.connect(self._show_block_menu)
        bl.addWidget(self.btn_block)

        self.btn_export = QPushButton("📥 Export")
        self.btn_export.setFixedHeight(30)
        self.btn_export.clicked.connect(self._export_log)
        bl.addWidget(self.btn_export)
        layout.addWidget(bottom)

        self._update_block_button()

    def _load_data(self):
        """โหลดข้อมูลทั้งหมด — แต่ละ section สร้างเสมอ (ถ้าไม่มีข้อมูลแสดงว่าง)"""
        app = self.parent_app
        author = self.author

        # ── ดึงข้อมูล ──
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

        # ═══ SECTION 1: สถิติ (เสมอ) ═══
        s1, l1 = _make_section("📊 สถิติ")
        plat_str = f" · 📺 {' · '.join(sorted(platforms))}" if platforms else ""
        l1.addWidget(self._body_label(f"💬 {msg_count} ข้อความ{plat_str}"))
        if events:
            event_counts = {}
            for e in events:
                event_counts[e.event] = event_counts.get(e.event, 0) + 1
            parts = []
            for ev, cnt in sorted(event_counts.items(), key=lambda x: -x[1]):
                icon = EVENT_ICONS.get(ev, '🎉')
                parts.append(f"{icon} {ev} ×{cnt}")
            l1.addWidget(self._body_label("🎉 " + " · ".join(parts)))
        else:
            l1.addWidget(self._body_label("🎉 ยังไม่มี event"))
        self.cl.addWidget(s1)

        # ═══ SECTION 2: Donation (เสมอ) ═══
        s2, l2 = _make_section("💎 Donation")
        has_donate = False
        for plat, fields in sorted(donate.items()):
            if plat == 'total_donate_count':
                continue
            parts = []
            for field, value in sorted(fields.items()):
                if not value:
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
                elif field == 'gift_count':
                    continue
                else:
                    parts.append(f"{value} {field}")
            if parts:
                l2.addWidget(self._body_label(f"  {plat}: {' · '.join(parts)}"))
                has_donate = True
        total = donate.get('total_donate_count', 0)
        if total:
            l2.addWidget(self._body_label(f"  📊 รวม {total} ครั้ง", bold=True))
            has_donate = True
        if events:
            btn_dh = QPushButton("📋 ดูประวัติ Donation ทั้งหมด")
            btn_dh.setStyleSheet("color: #06b6d4; font-size: 12px; border: none; text-align: left; padding: 2px 0;")
            btn_dh.setCursor(Qt.PointingHandCursor)
            btn_dh.clicked.connect(self._show_donate_history)
            l2.addWidget(btn_dh)
        if not has_donate:
            l2.addWidget(self._body_label("  ยังไม่มี donation"))
        self.cl.addWidget(s2)

        # ═══ SECTION 3: ข้อความล่าสุด (เสมอ) ═══
        s3, l3 = _make_section(f"📝 ข้อความล่าสุด ({min(self._msg_limit, self._msg_total)} of {self._msg_total})")
        self._msg_container = QVBoxLayout()
        self._msg_container.setSpacing(2)
        l3.addLayout(self._msg_container)
        self.btn_load_more = QPushButton("📥 load more +20")
        self.btn_load_more.setStyleSheet("color: #06b6d4; font-size: 12px; border: none; padding: 2px;")
        self.btn_load_more.setCursor(Qt.PointingHandCursor)
        self.btn_load_more.clicked.connect(self._load_more_messages)
        l3.addWidget(self.btn_load_more)
        self.cl.addWidget(s3)

        # โหลดข้อความ
        self._load_messages()

        # ★ spacer ด้านล่างสุด
        self.cl.addStretch()

    def _body_label(self, text, bold=False):
        """สร้าง label สำหรับ body text — word wrap + fixed width"""
        lbl = QLabel(text)
        style = SECTION_BODY_STYLE
        if bold:
            style += " font-weight: 600; color: #f59e0b;"
        lbl.setStyleSheet(style)
        lbl.setWordWrap(True)
        lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        return lbl

    def _load_messages(self):
        """โหลดข้อความลงใน history section"""
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
            empty = QLabel("  ยังไม่มีข้อความ")
            empty.setStyleSheet(SECTION_BODY_STYLE + " color: #6b7280;")
            self._msg_container.addWidget(empty)
            self.btn_load_more.setVisible(False)
            return

        for msg in messages:
            plat = msg.get('platform', '?')
            text = msg.get('text', '')
            emotes = msg.get('emotes', '')
            # ★ ถ้า text ว่าง แต่มี emotes → แสดงชื่อ emote
            if not text and emotes:
                text = f"🖼️ {emotes}"
            elif not text:
                text = "(ว่าง)"
            row = QLabel(f"  [{plat}] {text}")
            row.setStyleSheet("color: #d1d5db; font-size: 12px;")
            row.setWordWrap(True)
            self._msg_container.addWidget(row)

        self.btn_load_more.setVisible(self._msg_offset + self._msg_limit < self._msg_total)

    def _load_more_messages(self):
        self._msg_offset += self._msg_limit
        self._load_messages()

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
            self.btn_block.setStyleSheet("background-color: #ef4444; color: white; font-weight: 600; border: none; border-radius: 4px;")
        elif status == "block_tts":
            self.btn_block.setText("🔇 บล็อก TTS")
            self.btn_block.setStyleSheet("background-color: #f59e0b; color: white; font-weight: 600; border: none; border-radius: 4px;")
        else:
            self.btn_block.setText("🚫 บล็อก")
            self.btn_block.setStyleSheet("")

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
