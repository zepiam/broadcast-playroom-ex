"""user_profile.py — แผงโปรไฟล์ผู้ชม (ใช้ทั้งใน drawer ของ User Manager และ AuthorModal ที่เปิดจากแชท)

โครง: Hero (avatar + ชื่อ + แพลตฟอร์ม + สถานะ) → 4 tiles สถิติ → แถบ action
      → แท็บ [ข้อความ | การสนับสนุน & กิจกรรม]
ทุกการแก้ไข (เปลี่ยนชื่อ/บล็อก/แปล/ลบ) แจ้งผ่าน signal `changed` เพื่อให้หน้ารายชื่อ refresh
"""
import logging
import re
from collections import Counter
from datetime import datetime

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QFrame, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QGridLayout,
    QMenu, QMessageBox, QFileDialog, QButtonGroup, QSizePolicy,
)

import user_directory as ud
from ui.platform_icons import get_platform_pixmap
from ui.user_kit import (
    C, rgba, pill, role, role_pill, platform_chip, platform_color, platform_label, btn_qss, icon_btn_qss,
    dim_text, faint_text, avatar_pixmap, EscLineEdit, Toast, flow_holder, make_scroll, scrollbar_qss,
)

logger = logging.getLogger("user_profile")

# donate_tracker field → (icon, ชื่อ, หน่วยท้ายค่า)
_DONATE_FIELDS = [
    ("bits", "💎", "Bits", ""),
    ("superchat", "💰", "SuperChat", " THB"),
    ("sub_count", "⭐", "Sub", " ครั้ง"),
    ("subgift_count", "🎁", "Gift Sub", " ครั้ง"),
    ("membership_count", "🎖️", "Membership", " ครั้ง"),
    ("gift_diamonds", "💎", "เพชร", ""),
    ("gift_count", "🎁", "ของขวัญ", " ครั้ง"),
]
_TIMELINE_CAP = 40


def _label(text="", size=13, color=None, weight=None, wrap=False, plain=True) -> QLabel:
    lbl = QLabel(text)
    css = f"background: transparent; border: none; min-height: 0; font-size: {size}px; color: {color or C('TEXT')};"
    if weight:
        css += f" font-weight: {weight};"
    lbl.setStyleSheet(css)
    lbl.setWordWrap(wrap)
    if plain:
        lbl.setTextFormat(Qt.PlainText)   # ข้อความจากผู้ชมเป็น input ภายนอก — ห้ามให้ตีความเป็น HTML
    return lbl


def _card(border_alpha=0.0) -> QFrame:
    fr = QFrame()
    fr.setObjectName("PCard")
    fr.setStyleSheet(
        f"QFrame#PCard {{ background-color: {rgba('#ffffff', 0.035)}; "
        f"border: 1px solid {C('BORDER')}; border-radius: 12px; }}")
    return fr


class UserProfilePanel(QFrame):
    changed = Signal()          # ชื่อ/บล็อก/แปล/ข้อมูลเปลี่ยน
    dataDeleted = Signal()      # ลบข้อมูลผู้ใช้ทั้งหมดแล้ว
    closeRequested = Signal()   # กดปุ่ม ✕

    PAGE = 20

    def __init__(self, app, parent=None, show_close: bool = True):
        super().__init__(parent)
        self.app = app
        self.settings = getattr(app, "settings", None)
        self._show_close = show_close
        self._key = ""
        self._hint = ""
        self._rec = None
        self._tab = "msgs"
        self._msg_limit = self.PAGE
        self._msg_platform = None
        self._editing = False
        self.setObjectName("ProfilePanel")
        self.setStyleSheet(f"QFrame#ProfilePanel {{ background-color: {C('CARD')}; }}")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.scroll = make_scroll()
        self.scroll.setStyleSheet(self.scroll.styleSheet() + scrollbar_qss())
        self.body = QWidget()
        self.body.setStyleSheet("background: transparent;")
        self.lay = QVBoxLayout(self.body)
        self.lay.setContentsMargins(20, 18, 20, 22)
        self.lay.setSpacing(14)
        self.scroll.setWidget(self.body)
        outer.addWidget(self.scroll)
        self.toast = Toast(self)

    # ── สาธารณะ ────────────────────────────────────────────
    def set_user(self, name: str) -> None:
        """แสดงโปรไฟล์ของ name (ชื่ออะไรก็ได้ ตัวพิมพ์ไม่สำคัญ)"""
        self._hint = (name or "").strip()
        self._key = self._hint.lower()
        self._tab = "msgs"
        self._msg_limit = self.PAGE
        self._msg_platform = None
        self._editing = False
        self.reload(keep_scroll=False)

    def current_key(self) -> str:
        return self._key

    def is_editing(self) -> bool:
        return self._editing

    def cancel_edit(self) -> bool:
        """ยกเลิกโหมดแก้ชื่อถ้าเปิดอยู่ — คืน True ถ้าเพิ่งยกเลิก (ให้ caller ไม่ปิดหน้าต่างต่อ)"""
        if self._editing:
            self._editing = False
            self.reload()
            return True
        return False

    def reload(self, keep_scroll: bool = True) -> None:
        if not self._key:
            return
        pos = self.scroll.verticalScrollBar().value() if keep_scroll else 0
        self._rec = ud.build_record(self.app, self.settings, self._key)
        # ไม่เคยมีข้อมูล (เช่นเพิ่งคลิกชื่อใหม่จากแชท) → ใช้ตัวพิมพ์ตามที่คลิกมา
        if self._rec.original == self._key and self._hint and self._hint.lower() == self._key:
            self._rec.original = self._hint
            if not self._rec.renamed:
                self._rec.display = self._hint
        self._rebuild()
        if keep_scroll:
            QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(pos))

    # ── สร้างหน้า ─────────────────────────────────────────
    def _clear(self, layout) -> None:
        while layout.count():
            it = layout.takeAt(0)
            w = it.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
            elif it.layout() is not None:
                self._clear(it.layout())

    def _rebuild(self) -> None:
        self._clear(self.lay)
        self._build_hero()
        self._build_rename_bar()
        self._build_tiles()
        self._build_meta()
        self._build_actions()
        self._build_tabs()
        self.lay.addStretch(1)

    # Hero ───────────────────────────────────────────────
    def _build_hero(self) -> None:
        rec = self._rec
        g0, g1 = ud.avatar_gradient(rec.key)
        hero = QFrame()
        hero.setObjectName("Hero")
        hero.setStyleSheet(
            f"QFrame#Hero {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, "
            f"stop:0 {rgba(g0, 0.30)}, stop:1 {rgba(g1, 0.06)}); "
            f"border: 1px solid {rgba(g0, 0.40)}; border-radius: 16px; }}")
        h = QHBoxLayout(hero)
        h.setContentsMargins(16, 16, 12, 16)
        h.setSpacing(14)

        av = QLabel()
        av.setPixmap(avatar_pixmap(rec.key, rec.display, 72))
        av.setFixedSize(72, 72)
        av.setStyleSheet("background: transparent; border: none;")
        h.addWidget(av, 0, Qt.AlignTop)

        col = QVBoxLayout()
        col.setSpacing(4)
        name_row = QHBoxLayout()
        name_row.setSpacing(6)
        name = _label(rec.display, 22, C("TEXT"), 800, wrap=True)
        name_row.addWidget(name, 1)
        pen = QPushButton("✏️")
        pen.setCursor(Qt.PointingHandCursor)
        pen.setToolTip("เปลี่ยนชื่อที่แสดง")
        pen.setFixedSize(30, 30)
        pen.setStyleSheet(icon_btn_qss("flat", 30, 8))
        pen.clicked.connect(self._start_rename)
        name_row.addWidget(pen, 0, Qt.AlignTop)
        col.addLayout(name_row)

        if rec.renamed:
            col.addWidget(_label(f"ชื่อเดิม: {rec.original}", 12, dim_text()))
        else:
            col.addWidget(_label(f"@{rec.original}", 12, faint_text()))

        chips = [platform_chip(p, text=len(rec.platforms) <= 3) for p in rec.platforms]
        if chips:
            col.addWidget(flow_holder(*chips))
        pills = self._status_pills()
        if pills:
            col.addWidget(flow_holder(*pills, vspacing=4))
        h.addLayout(col, 1)

        if self._show_close:
            x = QPushButton("✕")
            x.setCursor(Qt.PointingHandCursor)
            x.setFixedSize(30, 30)
            x.setStyleSheet(icon_btn_qss("flat", 30, 8))
            x.clicked.connect(self.closeRequested.emit)
            h.addWidget(x, 0, Qt.AlignTop)
        self.lay.addWidget(hero)

    def _status_pills(self) -> list:
        rec = self._rec
        out = []
        if rec.block_status == "block_all":
            out.append(role_pill("🚫 บล็อกทั้งหมด", "blocked", solid=True))
        elif rec.block_status == "block_tts":
            out.append(role_pill("🔇 บล็อก TTS", "blocked"))
        if rec.supporter:
            out.append(role_pill("💎 ผู้สนับสนุน", "supporter"))
        if rec.forced_translate:
            out.append(role_pill("🌐 บังคับแปล", "info"))
        if rec.is_new:
            out.append(role_pill("✨ ใหม่วันนี้", "new"))
        elif rec.is_regular:
            out.append(pill("🔥 แชทประจำ", rgba(role("accent")["solid"], 0.30), C("TEXT")))
        return out

    # แถบเปลี่ยนชื่อ (inline — ไม่เด้ง popup) ─────────────────
    def _build_rename_bar(self) -> None:
        self._rename_bar = QFrame()
        self._rename_bar.setObjectName("RenameBar")
        self._rename_bar.setStyleSheet(
            f"QFrame#RenameBar {{ background-color: {rgba(role('accent')['solid'], 0.10)}; "
            f"border: 1px solid {rgba(role('accent')['solid'], 0.55)}; border-radius: 12px; }}")
        v = QVBoxLayout(self._rename_bar)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(8)
        v.addWidget(_label("ชื่อที่ต้องการแสดง (เว้นว่าง = ใช้ชื่อเดิม)", 12, dim_text()))
        row = QHBoxLayout()
        row.setSpacing(6)
        self._rename_edit = EscLineEdit()
        self._rename_edit.setFixedHeight(34)
        self._rename_edit.setPlaceholderText(self._rec.original)
        self._rename_edit.setText(self._rec.display if self._rec.renamed else "")
        self._rename_edit.setStyleSheet(
            f"QLineEdit {{ background: {C('BG_DARK')}; color: {C('TEXT')}; "
            f"border: 1px solid {C('BORDER_LIGHT')}; border-radius: 8px; padding: 0 10px; "
            f"font-size: 14px; min-height: 34px; max-height: 34px; }}"
            f"QLineEdit:focus {{ border-color: {role('accent')['solid']}; }}")
        self._rename_edit.returnPressed.connect(self._commit_rename)
        self._rename_edit.escapePressed.connect(self.cancel_edit)
        row.addWidget(self._rename_edit, 1)
        ok = QPushButton("บันทึก")
        ok.setFixedHeight(34)
        ok.setCursor(Qt.PointingHandCursor)
        ok.setStyleSheet(btn_qss("primary", 8, 34))
        ok.clicked.connect(self._commit_rename)
        row.addWidget(ok)
        cancel = QPushButton("ยกเลิก")
        cancel.setFixedHeight(34)
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.setStyleSheet(btn_qss("flat", 8, 34))
        cancel.clicked.connect(self.cancel_edit)
        row.addWidget(cancel)
        v.addLayout(row)
        self._rename_bar.setVisible(self._editing)
        self.lay.addWidget(self._rename_bar)
        if self._editing:
            QTimer.singleShot(0, lambda: (self._rename_edit.setFocus(), self._rename_edit.selectAll()))

    def _start_rename(self) -> None:
        self._editing = True
        self._rename_bar.setVisible(True)
        self._rename_edit.setFocus()
        self._rename_edit.selectAll()

    def _commit_rename(self) -> None:
        if not self.settings:
            return
        new = self._rename_edit.text().strip()
        renames = dict(getattr(self.settings, "user_renames", {}) or {})
        if not new or new.lower() == self._rec.original.lower():
            renames.pop(self._key, None)      # เว้นว่าง/เท่าชื่อเดิม = คืนชื่อเดิม
            msg = "↩ คืนชื่อเดิมแล้ว"
        else:
            renames[self._key] = new
            msg = "✅ เปลี่ยนชื่อแล้ว"
        self.settings.user_renames = renames
        self._save_settings()
        self._editing = False
        self.reload()
        self.toast.show_message(msg)
        self.changed.emit()

    # Tiles ──────────────────────────────────────────────
    def _build_tiles(self) -> None:
        rec = self._rec
        grid = QHBoxLayout()
        grid.setSpacing(8)
        tiles = [
            ("💬", ud.fmt_int(rec.msg_count), "ข้อความ", None),
            ("📅", ud.fmt_int(rec.active_days), "วันที่มาแชท", None),
            ("🎉", ud.fmt_int(rec.event_count), "อีเวนต์", None),
            ("💎", ud.fmt_int(rec.donate_total), "สนับสนุน (ครั้ง)", role("supporter")["text_on_card"] if rec.donate_total else None),
        ]
        for icon, value, caption, accent in tiles:
            t = _card()
            v = QVBoxLayout(t)
            v.setContentsMargins(6, 10, 6, 9)
            v.setSpacing(1)
            ic = _label(icon, 15)
            ic.setAlignment(Qt.AlignCenter)
            val = _label(value, 19, accent or C("TEXT"), 800)
            val.setAlignment(Qt.AlignCenter)
            cap = _label(caption, 11, dim_text())
            cap.setAlignment(Qt.AlignCenter)
            v.addWidget(ic)
            v.addWidget(val)
            v.addWidget(cap)
            grid.addWidget(t, 1)
        self.lay.addLayout(grid)

    def _build_meta(self) -> None:
        rec = self._rec
        if not rec.first_seen and not rec.last_seen:
            self.lay.addWidget(_label("ยังไม่มีประวัติการแชทของผู้ใช้นี้", 12, faint_text()))
            return
        text = f"เห็นครั้งแรก {ud.fmt_date(rec.first_seen)}  ·  ล่าสุด {ud.relative_time(rec.last_seen)}"
        if rec.msg_count > rec.retained > 0:
            text += f"\nเก็บข้อความย้อนหลังไว้ {rec.retained:,} จาก {rec.msg_count:,} ข้อความ"
        elif rec.msg_count > 0 and rec.retained == 0:
            text += f"\nตัวข้อความแชทถูกล้างไปแล้ว (ยอดรวม {rec.msg_count:,} ข้อความยังอยู่)"
        self.lay.addWidget(_label(text, 12, dim_text(), wrap=True))

    # Actions ────────────────────────────────────────────
    def _build_actions(self) -> None:
        rec = self._rec
        btns = []

        st = rec.block_status
        if st == "block_all":
            b = QPushButton("🚫 บล็อกอยู่")
            kind = "danger"
        elif st == "block_tts":
            b = QPushButton("🔇 บล็อก TTS")
            kind = "danger_soft"
        else:
            b = QPushButton("🚫 บล็อก")
            kind = "ghost"
        self._style_action(b, kind)
        b.clicked.connect(lambda: self._show_block_menu(b))
        btns.append(b)

        translate_on = bool(getattr(self.settings, "auto_translate_enabled", False))
        if translate_on or rec.forced_translate:
            t = QPushButton("🌐 บังคับแปลอยู่" if rec.forced_translate else "🌐 บังคับแปล")
            self._style_action(t, "info" if rec.forced_translate else "ghost")
            if not translate_on:
                t.setToolTip("ตอนนี้ปิดการแปลอัตโนมัติอยู่ — การตั้งค่านี้จะมีผลเมื่อเปิดการแปล")
            t.clicked.connect(self._toggle_force_translate)
            btns.append(t)

        e = QPushButton("📥 Export")
        self._style_action(e, "ghost")
        e.clicked.connect(self._export)
        btns.append(e)

        more = QPushButton("⋯")
        more.setFixedWidth(38)
        self._style_action(more, "ghost")
        more.setStyleSheet(icon_btn_qss("ghost", 34, 10))
        more.clicked.connect(lambda: self._show_more_menu(more))
        btns.append(more)

        self.lay.addWidget(flow_holder(*btns, hspacing=8, vspacing=8))

    @staticmethod
    def _style_action(btn: QPushButton, kind: str) -> None:
        btn.setFixedHeight(34)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(btn_qss(kind, 10, 34))

    def _show_block_menu(self, anchor: QPushButton) -> None:
        st = self._rec.block_status
        menu = QMenu(self)
        if st is None:
            menu.addAction("🚫 บล็อกทุกอย่าง (ไม่แสดง + ไม่อ่าน)", lambda: self._set_block("block_all"))
            menu.addAction("🔇 บล็อก TTS (แสดงแต่ไม่อ่าน)", lambda: self._set_block("block_tts"))
        else:
            if st == "block_all":
                menu.addAction("🔇 เปลี่ยนเป็น บล็อก TTS", lambda: self._set_block("block_tts"))
            else:
                menu.addAction("🚫 เปลี่ยนเป็น บล็อกทุกอย่าง", lambda: self._set_block("block_all"))
            menu.addSeparator()
            menu.addAction("✅ ปลดบล็อก", lambda: self._set_block(None))
        menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))

    def _set_block(self, mode) -> None:
        """mode: None=ปลด | 'block_all' | 'block_tts'
        ★ app._block_user_from_chat เมินถ้ามีอยู่แล้ว (เช็ค already) → เปลี่ยนโหมดต้องปลดก่อนแล้วบล็อกใหม่"""
        app = self.app
        name = self._rec.original
        try:
            if self._rec.block_status is not None:
                app._unblock_user(name)
            if mode == "block_all":
                app._block_user_from_chat(name, tts_only=False)
            elif mode == "block_tts":
                app._block_user_from_chat(name, tts_only=True)
        except Exception as exc:
            logger.warning(f"set_block failed: {exc}")
            self.toast.show_message("❌ บล็อกไม่สำเร็จ", ok=False)
            return
        self.reload()
        self.toast.show_message({"block_all": "🚫 บล็อกแล้ว", "block_tts": "🔇 บล็อก TTS แล้ว"}.get(mode, "✅ ปลดบล็อกแล้ว"))
        self.changed.emit()

    def _toggle_force_translate(self) -> None:
        s = self.settings
        if not s:
            return
        lst = list(getattr(s, "force_translate_users", []) or [])
        if any(u.lower() == self._key for u in lst):
            lst = [u for u in lst if u.lower() != self._key]
            msg = "ยกเลิกบังคับแปลแล้ว"
        else:
            lst.append(self._key)
            msg = "🌐 บังคับแปลผู้ใช้นี้แล้ว"
        s.force_translate_users = lst
        self._save_settings()
        try:   # sync เข้า pipeline ทันที (ไม่งั้น pipeline ยังใช้ค่าเก่า)
            pipeline = getattr(self.app, "pipeline", None)
            if pipeline is not None and hasattr(pipeline, "config"):
                pipeline.config.force_translate_users = list(lst)
        except Exception:
            pass
        self.reload()
        self.toast.show_message(msg)
        self.changed.emit()

    def _show_more_menu(self, anchor: QPushButton) -> None:
        menu = QMenu(self)
        menu.addAction("🗑 ลบข้อมูลผู้ใช้นี้…", self._delete_data)
        menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))

    def _save_settings(self) -> None:
        try:
            from settings import save_settings
            save_settings(self.settings)
        except Exception as exc:
            logger.warning(f"save_settings failed: {exc}")

    def _delete_data(self) -> None:
        rec = self._rec
        ans = QMessageBox.question(
            self, "ลบข้อมูลผู้ใช้",
            f"ลบประวัติทั้งหมดของ “{rec.display}” ?\n\n"
            f"• ข้อความ {rec.msg_count:,} รายการ\n• ยอดสนับสนุน\n• อีเวนต์ {rec.event_count:,} รายการ\n\n"
            f"(สถานะบล็อกและชื่อที่ตั้งเองไม่ถูกลบ) — ย้อนกลับไม่ได้",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ans != QMessageBox.Yes:
            return
        try:
            for attr, fn in (("message_history", "remove_author"), ("donate_tracker", "clear_user"),
                             ("event_log", "remove_author")):
                obj = getattr(self.app, attr, None)
                if obj is not None:
                    getattr(obj, fn)(self._key)
        except Exception as exc:
            logger.warning(f"delete user data failed: {exc}")
            self.toast.show_message("❌ ลบไม่สำเร็จ", ok=False)
            return
        self.changed.emit()
        self.dataDeleted.emit()
        self.reload(keep_scroll=False)

    def _export(self) -> None:
        rec = self._rec
        mh = getattr(self.app, "message_history", None)
        dt = getattr(self.app, "donate_tracker", None)
        el = getattr(self.app, "event_log", None)
        entries = mh.get(self._key) if mh else []
        events = el.get_by_author(self._key) if el else []
        donate = dt.get_user(self._key) if dt else {}
        if not entries and not events and not donate:
            self.toast.show_message("ยังไม่มีข้อมูลให้ export", ok=False)
            return
        safe = re.sub(r"[^\w\-. ]", "_", rec.original)[:40] or "user"
        default = f"{safe}_{datetime.now():%Y%m%d}.md"
        path, _ = QFileDialog.getSaveFileName(self, "บันทึกไฟล์", default, "Markdown (*.md);;Text (*.txt)")
        if not path:
            return
        md = path.lower().endswith(".md")
        L = []
        L.append(f"# {rec.display}" if md else f"ผู้ใช้: {rec.display}")
        L.append(f"ชื่อเดิม: {rec.original}")
        L.append(f"แพลตฟอร์ม: {', '.join(ud.PLATFORM_LABELS.get(p, p) for p in rec.platforms) or '-'}")
        L.append(f"ข้อความทั้งหมด: {rec.msg_count:,}  ·  วันที่มาแชท: {rec.active_days}  ·  อีเวนต์: {rec.event_count:,}")
        L.append(f"เห็นครั้งแรก: {ud.fmt_date(rec.first_seen)}  ·  ล่าสุด: {ud.fmt_date(rec.last_seen)}")
        L.append(f"ส่งออกเมื่อ: {datetime.now():%Y-%m-%d %H:%M}")
        L.append("")
        if donate:
            L.append("## การสนับสนุน" if md else "== การสนับสนุน ==")
            for plat, fields in sorted(donate.items()):
                if plat == "total_donate_count" or not isinstance(fields, dict):
                    continue
                parts = [f"{fields[k]:,}{u} {n}" for k, _i, n, u in _DONATE_FIELDS if fields.get(k)]
                if parts:
                    L.append(f"- {platform_label(plat)}: " + " · ".join(parts))
            L.append("")
        L.append("## ประวัติข้อความ" if md else "== ประวัติข้อความ ==")
        for m in entries:
            text = m.get("text", "") or (f"(emote) {m.get('emotes', '')}" if m.get("emotes") else "(ว่าง)")
            if m.get("is_banned"):
                text = f"[ถูกกรอง] {m.get('banned_original') or text}"
            L.append(f"[{m.get('timestamp', '')}] [{m.get('platform', '?')}] {text}")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(L) + "\n")
            self.toast.show_message("📥 บันทึกไฟล์แล้ว")
        except Exception as exc:
            QMessageBox.warning(self, "Export", f"บันทึกไม่ได้: {exc}")

    # Tabs ───────────────────────────────────────────────
    def _build_tabs(self) -> None:
        bar = QHBoxLayout()
        bar.setSpacing(18)
        self._tab_group = QButtonGroup(self)
        self._tab_group.setExclusive(True)
        self._tab_btns = {}
        style = (f"QPushButton {{ background: transparent; border: none; border-bottom: 2px solid transparent; "
                 f"border-radius: 0; color: {dim_text()}; padding: 6px 2px; min-height: 0; "
                 f"font-size: 14px; font-weight: 600; }}"
                 f"QPushButton:hover {{ color: {C('TEXT')}; }}"
                 f"QPushButton:checked {{ color: {C('TEXT')}; border-bottom: 2px solid {role('accent')['solid']}; }}")
        for key, text in (("msgs", "💬 ข้อความ"), ("support", "💎 การสนับสนุน & กิจกรรม")):
            b = QPushButton(text)
            b.setCheckable(True)
            b.setChecked(self._tab == key)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(style)
            b.clicked.connect(lambda _=False, k=key: self._switch_tab(k))
            self._tab_group.addButton(b)
            self._tab_btns[key] = b
            bar.addWidget(b)
        bar.addStretch(1)
        wrap = QWidget()
        wl = QVBoxLayout(wrap)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(0)
        wl.addLayout(bar)
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background-color: {C('BORDER')}; border: none;")
        wl.addWidget(line)
        self.lay.addWidget(wrap)

        self._tab_box = QVBoxLayout()
        self._tab_box.setSpacing(8)
        holder = QWidget()
        holder.setLayout(self._tab_box)
        self.lay.addWidget(holder)
        self._fill_tab()

    def _switch_tab(self, key: str) -> None:
        if key == self._tab:
            return
        self._tab = key
        if key in getattr(self, "_tab_btns", {}):
            self._tab_btns[key].setChecked(True)   # สลับด้วยโค้ดก็ให้เส้นใต้แท็บตาม
        self._fill_tab()

    def _fill_tab(self) -> None:
        self._clear(self._tab_box)
        if self._tab == "msgs":
            self._fill_messages()
        else:
            self._fill_support()

    def _empty(self, icon: str, text: str) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 26, 0, 26)
        v.setSpacing(6)
        i = _label(icon, 30)
        i.setAlignment(Qt.AlignCenter)
        t = _label(text, 13, faint_text(), wrap=True)
        t.setAlignment(Qt.AlignCenter)
        v.addWidget(i)
        v.addWidget(t)
        return w

    # แท็บข้อความ ──────────────────────────────────────────
    def _fill_messages(self) -> None:
        mh = getattr(self.app, "message_history", None)
        entries = list(reversed(mh.get(self._key))) if mh else []
        if not entries:
            if self._rec.msg_count > 0:
                self._tab_box.addWidget(self._empty(
                    "🧹", f"ตัวข้อความแชทถูกล้างไปแล้ว — ยอดรวม {self._rec.msg_count:,} ข้อความยังอยู่"))
            else:
                self._tab_box.addWidget(self._empty("💬", "ยังไม่มีข้อความของผู้ใช้นี้"))
            return

        plats = self._rec.platforms
        if len(plats) > 1:
            row = []
            for key, text in [(None, "ทั้งหมด")] + [(p, platform_label(p)) for p in plats]:
                b = QPushButton(text)
                b.setCheckable(True)
                b.setChecked(self._msg_platform == key)
                b.setCursor(Qt.PointingHandCursor)
                col = platform_color(key) if key else role("accent")["solid"]
                b.setFixedHeight(26)
                b.setStyleSheet(
                    f"QPushButton {{ background: transparent; color: {dim_text()}; border: 1px solid {C('BORDER_LIGHT')}; "
                    f"border-radius: 13px; padding: 0 12px; min-height: 26px; max-height: 26px; font-size: 12px; font-weight: 600; }}"
                    f"QPushButton:hover {{ color: {C('TEXT')}; }}"
                    f"QPushButton:checked {{ background: {rgba(col, 0.20)}; color: {C('TEXT')}; border-color: {col}; }}")
                b.clicked.connect(lambda _=False, k=key: self._set_msg_platform(k))
                row.append(b)
            self._tab_box.addWidget(flow_holder(*row))

        if self._msg_platform:
            entries = [e for e in entries if e.get("platform") == self._msg_platform]
        total = len(entries)
        shown = entries[: self._msg_limit]
        self._tab_box.addWidget(_label(f"แสดง {len(shown):,} จาก {total:,} ข้อความ (ใหม่สุดก่อน)", 12, faint_text()))
        for e in shown:
            self._tab_box.addWidget(self._bubble(e))
        if total > len(shown):
            more = QPushButton(f"โหลดเพิ่ม +{min(self.PAGE, total - len(shown))}")
            more.setFixedHeight(34)
            more.setCursor(Qt.PointingHandCursor)
            more.setStyleSheet(btn_qss("info", 10, 34))
            more.clicked.connect(self._more_messages)
            self._tab_box.addWidget(more)

    def _set_msg_platform(self, key) -> None:
        self._msg_platform = key
        self._msg_limit = self.PAGE
        self._fill_tab()

    def _more_messages(self) -> None:
        self._msg_limit += self.PAGE
        self._fill_tab()

    def _bubble(self, e: dict) -> QFrame:
        plat = e.get("platform", "")
        color = platform_color(plat)
        fr = QFrame()
        fr.setObjectName("Bubble")
        fr.setStyleSheet(
            f"QFrame#Bubble {{ background-color: {rgba('#ffffff', 0.04)}; border: none; "
            f"border-left: 3px solid {color}; border-radius: 9px; }}")
        v = QVBoxLayout(fr)
        v.setContentsMargins(12, 8, 12, 9)
        v.setSpacing(3)
        head = QHBoxLayout()
        head.setSpacing(6)
        pm = get_platform_pixmap(plat, 14)
        if not pm.isNull():
            ic = QLabel()
            ic.setPixmap(pm)
            ic.setFixedSize(14, 14)
            ic.setStyleSheet("background: transparent; border: none;")
            head.addWidget(ic)
        head.addWidget(_label(ud.fmt_datetime_short(e.get("timestamp", "")), 11, faint_text()))
        head.addStretch(1)
        if e.get("is_banned"):
            head.addWidget(role_pill("ถูกกรอง", "blocked", size=10))
        v.addLayout(head)
        if e.get("is_banned"):
            text = e.get("banned_original") or e.get("text") or "(ว่าง)"
            body = _label(text, 13, role("blocked")["text_on_card"], wrap=True)
        else:
            text = e.get("text") or (f"🖼️ {e['emotes']}" if e.get("emotes") else "(ว่าง)")
            body = _label(text, 13, C("TEXT"), wrap=True)
        body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        v.addWidget(body)
        return fr

    # แท็บสนับสนุน & กิจกรรม ────────────────────────────────
    def _fill_support(self) -> None:
        dt = getattr(self.app, "donate_tracker", None)
        el = getattr(self.app, "event_log", None)
        donate = dt.get_user(self._key) if dt else {}
        events = list(reversed(el.get_by_author(self._key))) if el else []
        don_events = [e for e in events if e.event in ud.DONATION_EVENTS]
        other = Counter(e.event for e in events if e.event not in ud.DONATION_EVENTS)
        plats = [p for p in donate if p != "total_donate_count" and isinstance(donate[p], dict) and donate[p]]

        if not plats and not don_events and not other:
            self._tab_box.addWidget(self._empty("💎", "ยังไม่มีบันทึกการสนับสนุนหรือกิจกรรม"))
            return

        if plats:
            self._tab_box.addWidget(_label("ยอดสะสมแยกตามแพลตฟอร์ม", 12, faint_text(), 700))
            for p in sorted(plats, key=lambda x: ud.PLATFORM_ORDER.index(x) if x in ud.PLATFORM_ORDER else 99):
                self._tab_box.addWidget(self._wallet(p, donate[p]))

        if don_events:
            self._tab_box.addSpacing(6)
            self._tab_box.addWidget(_label(f"ไทม์ไลน์การสนับสนุน ({len(don_events):,})", 12, faint_text(), 700))
            for e in don_events[:_TIMELINE_CAP]:
                self._tab_box.addWidget(self._timeline_row(e))
            if len(don_events) > _TIMELINE_CAP:
                self._tab_box.addWidget(_label(f"… และอีก {len(don_events) - _TIMELINE_CAP:,} รายการที่เก่ากว่า", 12, faint_text()))

        if other:
            self._tab_box.addSpacing(6)
            self._tab_box.addWidget(_label("กิจกรรมอื่นๆ", 12, faint_text(), 700))
            chips = []
            for ev, n in other.most_common():
                icon, name = ud.EVENT_META.get(ev, ("🎉", ev))
                chips.append(pill(f"{icon} {name}  ×{n:,}", rgba("#ffffff", 0.07), C("TEXT"), 12))
            self._tab_box.addWidget(flow_holder(*chips, hspacing=6, vspacing=6))

    def _wallet(self, plat: str, fields: dict) -> QFrame:
        color = platform_color(plat)
        card = QFrame()
        card.setObjectName("Wallet")
        card.setStyleSheet(
            f"QFrame#Wallet {{ background-color: {rgba(color, 0.08)}; border: 1px solid {rgba(color, 0.35)}; "
            f"border-radius: 12px; }}")
        v = QVBoxLayout(card)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(5)
        head = QHBoxLayout()
        head.setSpacing(6)
        pm = get_platform_pixmap(plat, 18)
        if not pm.isNull():
            ic = QLabel()
            ic.setPixmap(pm)
            ic.setFixedSize(18, 18)
            ic.setStyleSheet("background: transparent; border: none;")
            head.addWidget(ic)
        head.addWidget(_label(platform_label(plat), 13, C("TEXT"), 700))
        head.addStretch(1)
        v.addLayout(head)
        known = {k for k, *_ in _DONATE_FIELDS}
        rows = [(i, n, f"{fields[k]:,}{u}") for k, i, n, u in _DONATE_FIELDS if fields.get(k)]
        rows += [("•", k, f"{val:,}" if isinstance(val, (int, float)) else str(val))
                 for k, val in fields.items() if k not in known and val]
        for icon, name, value in rows:
            r = QHBoxLayout()
            r.setSpacing(6)
            r.addWidget(_label(f"{icon}  {name}", 13, dim_text()))
            r.addStretch(1)
            r.addWidget(_label(value, 14, role("supporter")["text_on_card"], 800))
            v.addLayout(r)
        return card

    def _timeline_row(self, e) -> QFrame:
        fr = QFrame()
        fr.setObjectName("TRow")
        fr.setStyleSheet(
            f"QFrame#TRow {{ background-color: {rgba('#ffffff', 0.035)}; border: none; border-radius: 9px; }}")
        h = QHBoxLayout(fr)
        h.setContentsMargins(10, 7, 12, 7)
        h.setSpacing(8)
        pm = get_platform_pixmap(e.platform, 16)
        if not pm.isNull():
            ic = QLabel()
            ic.setPixmap(pm)
            ic.setFixedSize(16, 16)
            ic.setStyleSheet("background: transparent; border: none;")
            h.addWidget(ic)
        icon, name = ud.EVENT_META.get(e.event, ("🎉", e.event))
        h.addWidget(_label(f"{icon} {name}", 13, C("TEXT"), 600))
        amount = ud.event_amount_text(e.event, e.amount)
        if amount:
            h.addWidget(_label(amount, 13, role("supporter")["text_on_card"], 800))
        h.addStretch(1)
        h.addWidget(_label(ud.fmt_datetime_short(e.timestamp), 11, faint_text()))
        return fr
