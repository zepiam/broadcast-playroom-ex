"""event_detail.py — หน้าต่าง "รายละเอียด event" (กดจากแผง Events หรือจากแถว event ใน Live Chat)

แสดง: ใครให้ / อะไร / มูลค่า / ซับมากี่เดือน / มอบให้ใคร / ข้อความที่แนบมา — ข้อมูลทั้งหมดมาจาก
event_details.build_info() (เก็บใน event_log ด้วย) แถวไหนแพลตฟอร์มไม่ได้ส่งมาจะไม่แสดง (ไม่เดา)
สีทุกจุดตามธีมผ่าน ui/user_kit.py (บทบาทสี)
"""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QApplication, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

import event_details as ed
import user_directory as ud
from ui.user_kit import (
    C, btn_qss, dim_text, faint_text, paint_avatar, platform_chip, rgba, role,
)

logger = logging.getLogger("event_detail")

_CAT_ROLE = {"money": "supporter", "sub": "accent", "gift": "info", "other": "info"}


class _Avatar(QWidget):
    def __init__(self, name: str, size: int = 44, parent=None):
        super().__init__(parent)
        self._name = name
        self.setFixedSize(size, size)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        paint_avatar(p, QRectF(0, 0, self.width(), self.height()), (self._name or "?").lower(), self._name or "?")


def _label(text: str, style: str) -> QLabel:
    lb = QLabel(text)
    lb.setStyleSheet(style + " background: transparent; min-height: 0;")
    return lb


def info_as_text(info: dict) -> str:
    """ข้อความล้วนสำหรับคัดลอก"""
    lines = [f"{info.get('icon', '')} {info.get('headline', '')}".strip(),
             f"ผู้ให้: {info.get('author', '')}  ({ed.PLATFORM_NAMES.get(info.get('platform', ''), info.get('platform', ''))})"]
    if info.get("ts"):
        lines.append(f"เวลา: {ud.fmt_datetime_short(info['ts'])}")
    for name, value in info.get("fields", []):
        lines.append(f"{name}: {value}")
    if info.get("message"):
        lines.append(f"ข้อความที่แนบ: {info['message']}")
    return "\n".join(lines)


class EventDetailDialog(QDialog):
    def __init__(self, info: dict, parent=None, on_open_profile=None):
        super().__init__(parent)
        self.info = dict(info or {})
        self._on_open_profile = on_open_profile
        self.setWindowTitle("รายละเอียด Event")
        self.setModal(True)
        self.setFixedWidth(480)
        self._build()

    def _build(self) -> None:
        info = self.info
        cat = info.get("category", "other")
        R = role(_CAT_ROLE.get(cat, "info"))
        self.setStyleSheet(f"QDialog {{ background-color: {C('BG')}; }}")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 18)
        root.setSpacing(14)

        # ── หัว: ไอคอน + สรุป ──
        head = QFrame()
        head.setObjectName("EDHead")
        head.setStyleSheet(
            f"QFrame#EDHead {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, "
            f"stop:0 {rgba(R['solid'], 0.30)}, stop:1 {rgba(C('BG'), 0)}); "
            f"border-bottom: 1px solid {C('BORDER')}; }}")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(22, 20, 22, 18)
        hl.setSpacing(16)
        badge = QLabel(info.get("icon", "🔔"))
        badge.setAlignment(Qt.AlignCenter)
        badge.setFixedSize(60, 60)
        badge.setStyleSheet(
            f"font-size: 30px; background-color: {rgba(R['solid'], 0.22)}; "
            f"border: 1px solid {rgba(R['solid'], 0.6)}; border-radius: 18px; min-height: 0;")
        hl.addWidget(badge)
        col = QVBoxLayout()
        col.setSpacing(4)
        self.headline = _label(info.get("headline") or info.get("label", ""),
                               f"font-size: 19px; font-weight: 800; color: {C('TEXT')};")
        self.headline.setWordWrap(True)
        self.headline.setTextInteractionFlags(Qt.TextSelectableByMouse)
        col.addWidget(self.headline)
        sub = info.get("label", "")
        if info.get("ts"):
            sub += f"  ·  {ud.fmt_datetime_short(info['ts'])}"
            rel = ud.relative_time(info["ts"])
            if rel:
                sub += f"  ({rel})"
        col.addWidget(_label(sub, f"font-size: 12px; color: {dim_text()};"))
        hl.addLayout(col, 1)
        root.addWidget(head)

        body = QVBoxLayout()
        body.setContentsMargins(22, 0, 22, 0)
        body.setSpacing(12)

        # ── ผู้ให้ ──
        who = QFrame()
        who.setObjectName("EDCard")
        who.setStyleSheet(f"QFrame#EDCard {{ background-color: {C('CARD')}; border: 1px solid {C('BORDER')}; border-radius: 14px; }}")
        wl = QHBoxLayout(who)
        wl.setContentsMargins(14, 12, 14, 12)
        wl.setSpacing(12)
        wl.addWidget(_Avatar(info.get("author", "?")))
        nc = QVBoxLayout()
        nc.setSpacing(3)
        nc.addWidget(_label(info.get("author", "?"), f"font-size: 16px; font-weight: 700; color: {C('TEXT')};"))
        if info.get("platform"):
            nc.addWidget(platform_chip(info["platform"], icon=14))
        wl.addLayout(nc, 1)
        if self._on_open_profile is not None and info.get("author") and info["author"] != "?":
            b = QPushButton("👤 ดูโปรไฟล์")
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(btn_qss("ghost", 11, 34))
            b.clicked.connect(self._open_profile)
            wl.addWidget(b)
        body.addWidget(who)

        # ── รายละเอียด ──
        fields = info.get("fields") or []
        if fields:
            card = QFrame()
            card.setObjectName("EDCard")
            card.setStyleSheet(f"QFrame#EDCard {{ background-color: {C('CARD')}; border: 1px solid {C('BORDER')}; border-radius: 14px; }}")
            g = QGridLayout(card)
            g.setContentsMargins(16, 12, 16, 12)
            g.setHorizontalSpacing(18)
            g.setVerticalSpacing(9)
            g.setColumnStretch(1, 1)
            for i, (name, value) in enumerate(fields):
                g.addWidget(_label(name, f"font-size: 13px; color: {dim_text()};"), i, 0, Qt.AlignTop)
                v = _label(value, f"font-size: 14px; font-weight: 700; color: {R['text_on_card']};")
                v.setWordWrap(True)
                v.setTextInteractionFlags(Qt.TextSelectableByMouse)
                g.addWidget(v, i, 1, Qt.AlignTop)
            body.addWidget(card)

        # ── ข้อความที่แนบมา ──
        msg = (info.get("message") or "").strip()
        self.message_box = None
        if msg:
            box = QFrame()
            box.setObjectName("EDMsg")
            box.setStyleSheet(
                f"QFrame#EDMsg {{ background-color: {rgba(R['solid'], 0.10)}; "
                f"border: 1px solid {rgba(R['solid'], 0.45)}; border-left: 4px solid {R['solid']}; border-radius: 12px; }}")
            bl = QVBoxLayout(box)
            bl.setContentsMargins(14, 10, 14, 12)
            bl.setSpacing(5)
            bl.addWidget(_label("💬  ข้อความที่แนบมา", f"font-size: 12px; font-weight: 700; color: {R['text']};"))
            t = _label(msg, f"font-size: 15px; color: {C('TEXT')};")
            t.setWordWrap(True)
            t.setTextInteractionFlags(Qt.TextSelectableByMouse)
            bl.addWidget(t)
            body.addWidget(box)
            self.message_box = box
        elif cat in ("money", "sub"):
            body.addWidget(_label("ไม่มีข้อความแนบมากับรายการนี้", f"font-size: 12px; color: {faint_text()};"))

        # ── ข้อความดิบจากแพลตฟอร์ม ──
        sys_t = (info.get("system_text") or "").strip()
        if sys_t and sys_t != info.get("headline"):
            st = _label(f"จากแพลตฟอร์ม: {sys_t}", f"font-size: 11px; color: {faint_text()};")
            st.setWordWrap(True)
            st.setTextInteractionFlags(Qt.TextSelectableByMouse)
            body.addWidget(st)
        root.addLayout(body)

        # ── ปุ่ม ──
        foot = QHBoxLayout()
        foot.setContentsMargins(22, 4, 22, 0)
        foot.setSpacing(10)
        copy = QPushButton("📋  คัดลอก")
        copy.setCursor(Qt.PointingHandCursor)
        copy.setStyleSheet(btn_qss("ghost", 12, 38))
        copy.clicked.connect(self._copy)
        foot.addWidget(copy)
        foot.addStretch(1)
        close = QPushButton("ปิด")
        close.setCursor(Qt.PointingHandCursor)
        close.setDefault(True)
        close.setMinimumWidth(110)
        close.setStyleSheet(btn_qss("primary", 12, 38))
        close.clicked.connect(self.accept)
        foot.addWidget(close)
        root.addLayout(foot)

    def _copy(self) -> None:
        QApplication.clipboard().setText(info_as_text(self.info))

    def _open_profile(self) -> None:
        try:
            self._on_open_profile(self.info.get("author", ""))
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"open profile failed: {exc}")
