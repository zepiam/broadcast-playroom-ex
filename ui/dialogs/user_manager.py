"""user_manager.py — User Manager (ดีไซน์ใหม่: "Viewer Directory")

แนวคิด: ไม่ใช่ลิสต์แถว + popup — เป็นกำแพงการ์ดผู้ชม (grid) + ลิ้นชักโปรไฟล์สไลด์ออกมาข้างๆ
  • แท็บอัจฉริยะแยกตาม "ความหมาย" (ผู้สนับสนุน / แชทประจำ / ใหม่วันนี้ / ถูกบล็อก) พร้อมจำนวน
  • ชิปแพลตฟอร์มด้วยโลโก้จริง + จำนวน  • ค้นหา + เรียงลำดับ
  • แบ่งหน้า (ครั้งละ 24/48/96/200 คน) — วาดเฉพาะหน้าที่เปิด รายชื่อหลักหมื่นก็ไม่หน่วง
  • บัญชีที่ถูกบล็อก/บอท ซ่อนไว้เป็นค่าเริ่มต้น — ติ๊ก "แสดงบล็อก/บอท" เพื่อดู (แท็บ "ถูกบล็อก" เห็นเสมอ)
  • คลิกการ์ด → ลิ้นชักโปรไฟล์เต็ม (สถิติ/ข้อความ/สนับสนุน/แอ็กชัน) โดยไม่ปิดรายชื่อ
ข้อมูลรวมโดย user_directory.py • สีทุกตัวตามธีมที่เลือก ผ่านระบบ "บทบาทสี" ใน ui/user_kit.py
"""
import logging

from PySide6.QtCore import (
    Qt, QAbstractListModel, QModelIndex, QRectF, QSize, QTimer, QPropertyAnimation,
    QEasingCurve, QEvent,
)
from PySide6.QtGui import (
    QColor, QPainter, QPainterPath, QPen, QFont, QFontMetricsF, QKeySequence, QShortcut, QIcon,
)
from PySide6.QtWidgets import (
    QDialog, QWidget, QFrame, QLabel, QPushButton, QLineEdit, QVBoxLayout, QHBoxLayout,
    QListView, QStyledItemDelegate, QStyle, QMenu, QButtonGroup, QStackedLayout, QAbstractItemView,
    QLayout, QSizePolicy,
)

import user_directory as ud
from ui.platform_icons import get_platform_pixmap
from ui.user_kit import (
    C, rgba, mix, role, paint_avatar, platform_label, platform_color, btn_qss, icon_btn_qss,
    dim_text, faint_text, avatar_stack_pixmap, scrollbar_qss,
)
from ui.widgets.user_profile import UserProfilePanel

logger = logging.getLogger("user_manager")

DRAWER_W = 440
CARD_H = 156
CARD_MIN_W = 268

TAB_DEFS = [
    ("all", "ทั้งหมด", "ผู้ชมทุกคนที่โปรแกรมเคยเจอ"),
    ("supporter", "💎 ผู้สนับสนุน", "เคยโดเนท / ซับ / ส่งของขวัญ"),
    ("regular", "🔥 แชทประจำ", f"มาแชทตั้งแต่ {ud.REGULAR_MIN_DAYS} วันขึ้นไป"),
    ("new", "✨ ใหม่วันนี้", "เห็นครั้งแรกวันนี้"),
    ("blocked", "🚫 ถูกบล็อก", "ถูกบล็อกทั้งหมด หรือบล็อกเฉพาะ TTS"),
]
SORT_DEFS = [
    ("recent", "เห็นล่าสุด"),
    ("messages", "ข้อความมากสุด"),
    ("days", "มาบ่อยสุด"),
    ("name", "ชื่อ ก–ฮ"),
    ("support", "ผู้สนับสนุนก่อน"),
]


def _argb(hex_color: str, alpha: int) -> QColor:
    """'#rrggbb' + alpha 0-255 → QColor"""
    c = QColor(hex_color)
    c.setAlpha(alpha)
    return c


# ═══════════════════════════════════════════════════════════
# Model + การ์ด (วาดเองด้วย QPainter → รองรับผู้ชมเป็นพันคนโดยไม่หน่วง)
# ═══════════════════════════════════════════════════════════
class RosterModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._recs: list = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._recs)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._recs)):
            return None
        rec = self._recs[index.row()]
        if role == Qt.UserRole:
            return rec
        if role == Qt.DisplayRole:
            return rec.display
        return None

    def set_records(self, recs: list) -> None:
        self.beginResetModel()
        self._recs = list(recs)
        self.endResetModel()

    def index_of(self, key: str) -> QModelIndex:
        for i, r in enumerate(self._recs):
            if r.key == key:
                return self.index(i, 0)
        return QModelIndex()

    def record_at(self, index: QModelIndex):
        return self._recs[index.row()] if index.isValid() else None


class CardDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cell_w = 280

    def sizeHint(self, option, index):
        return QSize(self.cell_w, CARD_H)

    @staticmethod
    def _font(base: QFont, px: int, bold=False) -> QFont:
        f = QFont(base)
        f.setPixelSize(px)
        f.setWeight(QFont.Weight.Bold if bold else QFont.Weight.Normal)
        return f

    def _pill(self, p: QPainter, base: QFont, right: float, cy: float, text: str, bg: QColor, fg: QColor) -> float:
        """วาดป้ายเล็กชิดขวา คืนตำแหน่ง x ซ้ายสุดของป้าย (ไว้วางป้ายถัดไป)"""
        f = self._font(base, 11, True)
        fm = QFontMetricsF(f)
        w = fm.horizontalAdvance(text) + 16
        rect = QRectF(right - w, cy - 9, w, 18)
        path = QPainterPath()
        path.addRoundedRect(rect, 9, 9)
        p.fillPath(path, bg)
        p.setFont(f)
        p.setPen(fg)
        p.drawText(rect, Qt.AlignCenter, text)
        return rect.left() - 5

    def paint(self, p: QPainter, opt, index):
        rec = index.data(Qt.UserRole)
        if rec is None:
            return
        p.save()
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
        base = opt.font
        R = {k: role(k) for k in ("select", "supporter", "blocked", "new", "info", "accent")}
        dim = QColor(dim_text())
        r = QRectF(opt.rect).adjusted(7, 7, -7, -7)
        sel = bool(opt.state & QStyle.State_Selected)
        hov = bool(opt.state & QStyle.State_MouseOver)
        pad = 14.0

        # พื้นการ์ด: ปกติ / เมาส์ชี้ / เลือกอยู่ (เลือก = ผสมสี select เข้าไปนิดๆ + ขอบหนา)
        if sel:
            bg = QColor(mix(C("CARD_HI"), R["select"]["solid"], 0.18))
            border = QColor(R["select"]["solid"])
        elif hov:
            bg = QColor(C("CARD_HOVER"))
            border = QColor(mix(C("BORDER_LIGHT"), R["accent"]["solid"], 0.55))
        else:
            bg = QColor(C("CARD"))
            border = QColor(C("BORDER"))
        path = QPainterPath()
        path.addRoundedRect(r, 16, 16)
        p.fillPath(path, bg)

        # แถบซ้าย: แดงทึบ = บล็อกทั้งหมด / แดงจาง = บล็อกเฉพาะ TTS (clip ตามมุมโค้งของการ์ด)
        if rec.block_status:
            stripe = QColor(R["blocked"]["solid"])
            if rec.block_status == "block_tts":
                stripe = QColor(mix(R["blocked"]["solid"], C("CARD"), 0.45))
            p.save()
            p.setClipPath(path)
            p.fillRect(QRectF(r.left(), r.top(), 4, r.height()), stripe)
            p.restore()

        p.setPen(QPen(border, 2 if sel else 1))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

        # คนที่บล็อกอยู่ทำให้จางลงนิดนึง (ยังอ่านออก)
        if rec.blocked and not sel:
            p.setOpacity(0.78)

        # ── แถวบน: avatar + ชื่อ + บรรทัดรอง ──
        av = QRectF(r.left() + pad, r.top() + pad, 46, 46)
        paint_avatar(p, av, rec.key, rec.display)
        if rec.platforms:
            pm = get_platform_pixmap(rec.platforms[0], 18)
            if not pm.isNull():
                ring = QRectF(av.right() - 14, av.bottom() - 14, 22, 22)
                p.setPen(Qt.NoPen)
                p.setBrush(bg)
                p.drawEllipse(ring)
                p.drawPixmap(int(ring.left() + 2), int(ring.top() + 2), pm)

        text_x = av.right() + 14
        right_edge = r.right() - pad
        gem_w = 22 if rec.supporter else 0
        name_w = right_edge - text_x - gem_w

        f_name = self._font(base, 15, True)
        p.setFont(f_name)
        p.setPen(QColor(C("TEXT")))
        name = QFontMetricsF(f_name).elidedText(rec.display, Qt.ElideRight, name_w)
        p.drawText(QRectF(text_x, r.top() + pad - 2, name_w, 24), Qt.AlignLeft | Qt.AlignVCenter, name)

        f_sub = self._font(base, 12)
        p.setFont(f_sub)
        p.setPen(dim)
        sub = ud.relative_time(rec.last_seen) if rec.last_seen else "ยังไม่มีประวัติแชท"
        if rec.renamed:
            sub = f"@{rec.original} · {sub}"
        sub = QFontMetricsF(f_sub).elidedText(sub, Qt.ElideRight, right_edge - text_x)
        p.drawText(QRectF(text_x, r.top() + pad + 22, right_edge - text_x, 20), Qt.AlignLeft | Qt.AlignVCenter, sub)

        if rec.supporter:
            p.setFont(self._font(base, 15))
            p.setPen(QColor(R["supporter"]["solid"]))
            p.drawText(QRectF(right_edge - 20, r.top() + pad - 2, 22, 24), Qt.AlignCenter, "💎")

        # ── แถวกลาง: โลโก้แพลตฟอร์ม (ซ้าย) + ป้ายสถานะ (ขวา) ──
        mid_y = r.top() + pad + 62
        x = r.left() + pad
        for plat in rec.platforms[:6]:
            pm = get_platform_pixmap(plat, 18)
            if pm.isNull():
                p.setBrush(QColor(platform_color(plat)))
                p.setPen(Qt.NoPen)
                p.drawEllipse(QRectF(x + 3, mid_y - 5, 10, 10))
            else:
                p.drawPixmap(int(x), int(mid_y - 9), pm)
            x += 24
        pills_right = right_edge
        if rec.block_status == "block_all":
            pills_right = self._pill(p, base, pills_right, mid_y, "บล็อก",
                                     QColor(R["blocked"]["solid"]), QColor(R["blocked"]["on_solid"]))
        elif rec.block_status == "block_tts":
            pills_right = self._pill(p, base, pills_right, mid_y, "TTS ปิด",
                                     _argb(R["blocked"]["solid"], 70), QColor(R["blocked"]["text"]))
        if rec.forced_translate and pills_right - x > 60:
            pills_right = self._pill(p, base, pills_right, mid_y, "🌐 แปล",
                                     _argb(R["info"]["solid"], 60), QColor(R["info"]["text"]))
        if rec.is_new and pills_right - x > 60:
            self._pill(p, base, pills_right, mid_y, "ใหม่",
                       _argb(R["new"]["solid"], 60), QColor(R["new"]["text"]))
        elif rec.is_regular and not rec.blocked and pills_right - x > 70:
            self._pill(p, base, pills_right, mid_y, "🔥 ประจำ",
                       _argb(R["accent"]["solid"], 70), QColor(C("TEXT")))

        # ── แถวล่าง: 3 สถิติ ──
        div_y = r.bottom() - 50
        p.setPen(QPen(QColor(C("BORDER")), 1))
        p.drawLine(int(r.left() + pad), int(div_y), int(r.right() - pad), int(div_y))
        cell_w = (r.width() - 2 * pad) / 3
        stats = [
            (ud.fmt_compact(rec.msg_count), "ข้อความ", C("TEXT")),
            (str(rec.active_days), "วันที่มา", C("TEXT")),
            (f"{rec.donate_total:,} ครั้ง" if rec.donate_total else "—", "สนับสนุน",
             R["supporter"]["text_on_card"] if rec.donate_total else faint_text()),
        ]
        for i, (val, cap, col) in enumerate(stats):
            cx = r.left() + pad + cell_w * i
            p.setFont(self._font(base, 15, True))
            p.setPen(QColor(col))
            p.drawText(QRectF(cx, div_y + 5, cell_w, 22), Qt.AlignLeft | Qt.AlignVCenter, val)
            p.setFont(self._font(base, 11))
            p.setPen(dim)
            p.drawText(QRectF(cx, div_y + 26, cell_w, 16), Qt.AlignLeft | Qt.AlignVCenter, cap)
        p.restore()


# ═══════════════════════════════════════════════════════════
# หน้าต่างหลัก
# ═══════════════════════════════════════════════════════════
class UserManagerDialog(QDialog):
    def __init__(self, parent_app):
        super().__init__(parent_app if isinstance(parent_app, QWidget) else None)
        self.parent_app = parent_app
        self.settings = getattr(parent_app, "settings", None)
        self.setWindowTitle("👤 User Manager")
        self.resize(1240, 800)
        self.setMinimumSize(1040, 620)

        self._all: list = []
        self._tab = "all"
        self._platform = "all"
        self._query = ""
        self._sort = "recent"
        self._show_hidden = False           # ค่าเริ่มต้น: ซ่อนบล็อก/บอท
        self._page = 0
        self._per_page = ud.DEFAULT_PAGE_SIZE
        self._pages = 1
        self._selected_key = None
        self._drawer_open = False
        self._signature = None
        self._anim = None

        self._build_ui()
        QShortcut(QKeySequence("Ctrl+F"), self, activated=lambda: (self.search.setFocus(), self.search.selectAll()))
        QShortcut(QKeySequence("Alt+Right"), self, activated=lambda: self._goto_page(self._page + 1))
        QShortcut(QKeySequence("Alt+Left"), self, activated=lambda: self._goto_page(self._page - 1))
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(120)
        self._search_timer.timeout.connect(self._on_search_commit)
        # ต่อข้อมูลสดตอนเปิดค้างไว้ (แชทเข้าเรื่อยๆ) — รีเฟรชเงียบๆ ทุก 15 วิ ถ้าข้อมูลเปลี่ยนจริง
        self._auto = QTimer(self)
        self._auto.setInterval(15000)
        self._auto.timeout.connect(lambda: self.refresh(force=False))
        self._auto.start()
        self.refresh(force=True)

    # ── สร้างหน้าตา ───────────────────────────────────────
    def _build_ui(self) -> None:
        accent = role("accent")["solid"]
        self.setStyleSheet(f"QDialog {{ background-color: {C('BG')}; }}")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header ─ ไล่เฉดสี accent จางๆ + ชื่อหน้า + ค้นหา
        header = QFrame()
        header.setObjectName("UMHeader")
        header.setStyleSheet(
            f"QFrame#UMHeader {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            f"stop:0 {rgba(accent, 0.22)}, stop:0.6 {rgba(accent, 0.06)}, stop:1 {rgba(C('BG'), 0)}); "
            f"border-bottom: 1px solid {C('BORDER')}; }}")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(26, 18, 26, 16)
        hl.setSpacing(16)
        badge = QLabel()
        badge.setPixmap(avatar_stack_pixmap(46))
        badge.setFixedSize(58, 58)
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(
            f"background-color: {rgba(accent, 0.20)}; border: 1px solid {rgba(accent, 0.55)}; "
            f"border-radius: 18px; min-height: 0;")
        hl.addWidget(badge)
        tcol = QVBoxLayout()
        tcol.setSpacing(2)
        title = QLabel("รายชื่อผู้ชม")
        title.setStyleSheet(f"font-size: 26px; font-weight: 800; color: {C('TEXT')}; background: transparent; min-height: 0;")
        self.subtitle = QLabel("")
        self.subtitle.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)   # จอแคบ → ตัดท้ายข้อความ ไม่ดันช่องอื่นซ้อนกัน
        self.subtitle.setStyleSheet(f"font-size: 13px; color: {dim_text()}; background: transparent; min-height: 0;")
        tcol.addWidget(title)
        tcol.addWidget(self.subtitle)
        hl.addLayout(tcol, 1)

        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍  ค้นหาชื่อ (ชื่อเดิมหรือชื่อที่ตั้งเอง)…   Ctrl+F")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(200)
        self.search.setMaximumWidth(360)
        self.search.setFixedHeight(42)
        self.search.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.search.setStyleSheet(
            f"QLineEdit {{ background-color: {rgba(C('BG_DARK'), 0.85)}; color: {C('TEXT')}; "
            f"border: 1px solid {C('BORDER_LIGHT')}; border-radius: 21px; padding: 0 18px; "
            f"font-size: 14px; min-height: 42px; max-height: 42px; }}"
            f"QLineEdit:focus {{ border-color: {accent}; }}")
        self.search.textChanged.connect(lambda _t: self._search_timer.start())
        hl.addWidget(self.search)
        refresh = QPushButton("⟳")
        refresh.setToolTip("โหลดข้อมูลใหม่")
        refresh.setCursor(Qt.PointingHandCursor)
        refresh.setFixedSize(42, 42)
        refresh.setStyleSheet(icon_btn_qss("ghost", 42, 21).replace("font-size: 13px", "font-size: 20px"))
        refresh.clicked.connect(lambda: self.refresh(force=True))
        hl.addWidget(refresh)
        # ★ ตั้งค่า "เก็บข้อความแชทไว้กี่วัน" (เกินแล้วลบเองตอนเปิดโปรแกรม) — ย้ายมาไว้ที่นี่จากหน้า Settings
        self.keep_btn = QPushButton()
        self.keep_btn.setCursor(Qt.PointingHandCursor)
        self.keep_btn.setStyleSheet(btn_qss("ghost", 21, 42))
        self.keep_btn.setEnabled(getattr(self.parent_app, "message_history", None) is not None)
        self.keep_btn.clicked.connect(self._show_keep_menu)
        self._update_keep_text()
        hl.addWidget(self.keep_btn)
        # ★ ล้างตัวข้อความแชททันที (ยอดรายคน/แพลตฟอร์ม/ยอดสนับสนุนยังอยู่ — เลือกสำรองก่อนได้)
        self.clear_hist_btn = QPushButton("🧹 ล้างแชท")
        self.clear_hist_btn.setToolTip(
            "ลบตัวข้อความแชทของทุกคนทันที\n"
            "ยอดข้อความ/แพลตฟอร์ม/วันที่มา และยอดโดเนท-ซับ ของแต่ละคนยังอยู่ครบ — เลือกสำรองไว้ก่อนได้")
        self.clear_hist_btn.setCursor(Qt.PointingHandCursor)
        self.clear_hist_btn.setStyleSheet(btn_qss("ghost", 21, 42))
        self.clear_hist_btn.setEnabled(getattr(self.parent_app, "message_history", None) is not None)
        self.clear_hist_btn.clicked.connect(self._open_clear_history)
        hl.addWidget(self.clear_hist_btn)
        root.addWidget(header)

        # แถบตัวกรอง ─ แท็บอัจฉริยะ + เรียง / ชิปแพลตฟอร์ม
        filters = QWidget()
        filters.setStyleSheet("background: transparent;")
        fl = QVBoxLayout(filters)
        fl.setContentsMargins(26, 14, 26, 6)
        fl.setSpacing(10)

        row1 = QHBoxLayout()
        row1.setSpacing(12)
        seg = QFrame()
        seg.setObjectName("Seg")
        seg.setStyleSheet(
            f"QFrame#Seg {{ background-color: {C('CARD')}; border: 1px solid {C('BORDER')}; border-radius: 19px; }}")
        sl = QHBoxLayout(seg)
        sl.setContentsMargins(4, 4, 4, 4)
        sl.setSpacing(2)
        self._tab_group = QButtonGroup(self)
        self._tab_group.setExclusive(True)
        self._tab_btns = {}
        seg_style = (
            f"QPushButton {{ background: transparent; color: {dim_text()}; border: none; border-radius: 15px; "
            f"padding: 0 16px; min-height: 32px; max-height: 32px; font-size: 14px; font-weight: 600; }}"
            f"QPushButton:hover {{ color: {C('TEXT')}; background: {rgba('#ffffff', 0.06)}; }}"
            f"QPushButton:checked {{ background-color: {accent}; color: {role('accent')['on_solid']}; }}")
        for key, label, tip in TAB_DEFS:
            b = QPushButton(label)
            b.setCheckable(True)
            b.setChecked(key == self._tab)
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip(tip)
            b.setStyleSheet(seg_style)
            b.clicked.connect(lambda _=False, k=key: self._set_tab(k))
            self._tab_group.addButton(b)
            self._tab_btns[key] = b
            sl.addWidget(b)
        row1.addWidget(seg)
        row1.addStretch(1)
        self.hidden_btn = QPushButton()
        self.hidden_btn.setCheckable(True)
        self.hidden_btn.setChecked(self._show_hidden)
        self.hidden_btn.setCursor(Qt.PointingHandCursor)
        self.hidden_btn.setToolTip(
            "บัญชีที่ถูกบล็อก (ทั้งหมด/เฉพาะ TTS) และบอทใน Blacklist ถูกซ่อนไว้จากรายชื่อ\n"
            "ติ๊กเพื่อแสดงรวมด้วย — หรือเปิดแท็บ \"ถูกบล็อก\" เพื่อดูเฉพาะกลุ่มนี้")
        self.hidden_btn.setStyleSheet(
            f"QPushButton {{ background-color: {C('CARD')}; color: {dim_text()}; border: 1px solid {C('BORDER')}; "
            f"border-radius: 13px; padding: 0 14px; min-height: 38px; max-height: 38px; font-size: 13px; "
            f"font-weight: 600; }}"
            f"QPushButton:hover {{ border-color: {accent}; color: {C('TEXT')}; }}"
            f"QPushButton:checked {{ background-color: {rgba(accent, 0.20)}; color: {C('TEXT')}; border-color: {accent}; }}")
        self.hidden_btn.toggled.connect(self._set_show_hidden)
        row1.addWidget(self.hidden_btn)
        self.sort_btn = QPushButton()
        self.sort_btn.setMinimumWidth(180)
        self.sort_btn.setCursor(Qt.PointingHandCursor)
        self.sort_btn.setStyleSheet(
            f"QPushButton {{ background-color: {C('CARD')}; color: {C('TEXT')}; border: 1px solid {C('BORDER')}; "
            f"border-radius: 13px; padding: 0 16px; min-height: 38px; max-height: 38px; font-size: 14px; "
            f"font-weight: 600; text-align: left; }}"
            f"QPushButton:hover {{ border-color: {accent}; }}")
        self.sort_btn.clicked.connect(self._show_sort_menu)
        self._update_sort_text()
        row1.addWidget(self.sort_btn)
        fl.addLayout(row1)

        self._plat_row = QHBoxLayout()
        self._plat_row.setSpacing(8)
        self._plat_holder = QWidget()
        self._plat_holder.setLayout(self._plat_row)
        self._plat_group = QButtonGroup(self)
        self._plat_group.setExclusive(True)
        self._plat_btns = {}
        fl.addWidget(self._plat_holder)
        root.addWidget(filters)

        # เนื้อหา: กำแพงการ์ด (ซ้าย) + ลิ้นชักโปรไฟล์ (ขวา)
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        left = QWidget()
        left.setStyleSheet("background: transparent;")
        left_col = QVBoxLayout(left)
        left_col.setContentsMargins(0, 0, 0, 0)
        left_col.setSpacing(0)
        stack_host = QWidget()
        stack_host.setStyleSheet("background: transparent;")
        self._stack = QStackedLayout(stack_host)
        self._stack.setContentsMargins(0, 0, 0, 0)

        self.model = RosterModel(self)
        self.delegate = CardDelegate(self)
        self.view = QListView()
        self.view.setModel(self.model)
        self.view.setItemDelegate(self.delegate)
        self.view.setViewMode(QListView.IconMode)
        self.view.setResizeMode(QListView.Adjust)
        self.view.setMovement(QListView.Static)
        self.view.setWrapping(True)
        self.view.setFlow(QListView.LeftToRight)
        self.view.setUniformItemSizes(True)
        self.view.setSpacing(0)
        self.view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setFrameShape(QFrame.NoFrame)
        self.view.setMouseTracking(True)
        self.view.viewport().setCursor(Qt.PointingHandCursor)
        self.view.setStyleSheet(
            "QListView { background: transparent; border: none; outline: 0; padding: 4px 19px 16px 19px; }"
            + scrollbar_qss())
        self.view.viewport().installEventFilter(self)
        self.view.selectionModel().currentChanged.connect(self._on_current_changed)
        self._stack.addWidget(self.view)

        self._empty = QWidget()
        ev = QVBoxLayout(self._empty)
        ev.setAlignment(Qt.AlignCenter)
        ev.setSpacing(10)
        self._empty_icon = QLabel("🗂️")
        self._empty_icon.setAlignment(Qt.AlignCenter)
        self._empty_icon.setStyleSheet("font-size: 54px; background: transparent; min-height: 0;")
        self._empty_title = QLabel("")
        self._empty_title.setAlignment(Qt.AlignCenter)
        self._empty_title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {C('TEXT')}; background: transparent; min-height: 0;")
        self._empty_hint = QLabel("")
        self._empty_hint.setAlignment(Qt.AlignCenter)
        self._empty_hint.setWordWrap(True)
        self._empty_hint.setStyleSheet(f"font-size: 13px; color: {dim_text()}; background: transparent; min-height: 0;")
        self._empty_btn = QPushButton("ล้างตัวกรอง")
        self._empty_btn.setFixedSize(150, 38)
        self._empty_btn.setCursor(Qt.PointingHandCursor)
        self._empty_btn.setStyleSheet(btn_qss("primary", 13, 38))
        self._empty_btn.clicked.connect(self._clear_filters)
        ev.addWidget(self._empty_icon)
        ev.addWidget(self._empty_title)
        ev.addWidget(self._empty_hint)
        ev.addWidget(self._empty_btn, 0, Qt.AlignCenter)
        self._stack.addWidget(self._empty)
        left_col.addWidget(stack_host, 1)
        left_col.addWidget(self._build_pager())
        body.addWidget(left, 1)

        self.drawer = QFrame()
        self.drawer.setObjectName("Drawer")
        self.drawer.setStyleSheet(
            f"QFrame#Drawer {{ background-color: {C('CARD')}; border-left: 1px solid {C('BORDER')}; }}")
        self.drawer.setMinimumWidth(0)
        self.drawer.setMaximumWidth(0)
        dl = QHBoxLayout(self.drawer)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.setSizeConstraint(QLayout.SetNoConstraint)
        self.panel = UserProfilePanel(self.parent_app, show_close=True)
        self.panel.setFixedWidth(DRAWER_W)
        self.panel.changed.connect(self._on_panel_changed)
        self.panel.dataDeleted.connect(self._on_panel_deleted)
        self.panel.closeRequested.connect(self.close_profile)
        dl.addWidget(self.panel, 0, Qt.AlignLeft)
        body.addWidget(self.drawer)

        wrap = QWidget()
        wrap.setLayout(body)
        wrap.setStyleSheet("background: transparent;")
        root.addWidget(wrap, 1)

    # ── แถบเปลี่ยนหน้า ────────────────────────────────────
    def _build_pager(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("UMPager")
        bar.setStyleSheet(f"QFrame#UMPager {{ background: transparent; border-top: 1px solid {C('BORDER')}; }}")
        bar.setFixedHeight(58)
        hl = QHBoxLayout(bar)
        hl.setContentsMargins(26, 8, 26, 8)
        hl.setSpacing(12)
        self.range_lbl = QLabel("")
        self.range_lbl.setStyleSheet(
            f"color: {dim_text()}; font-size: 13px; background: transparent; min-height: 0;")
        self.range_lbl.setMinimumWidth(190)
        hl.addWidget(self.range_lbl)
        hl.addStretch(1)
        self._pages_box = QHBoxLayout()
        self._pages_box.setContentsMargins(0, 0, 0, 0)
        self._pages_box.setSpacing(6)
        self._pages_holder = QWidget()
        self._pages_holder.setStyleSheet("background: transparent;")
        self._pages_holder.setLayout(self._pages_box)
        hl.addWidget(self._pages_holder)
        hl.addStretch(1)
        per_lbl = QLabel("ต่อหน้า")
        per_lbl.setStyleSheet(f"color: {dim_text()}; font-size: 13px; background: transparent; min-height: 0;")
        hl.addWidget(per_lbl)
        self.per_btn = QPushButton()
        self.per_btn.setCursor(Qt.PointingHandCursor)
        self.per_btn.setMinimumWidth(96)
        self.per_btn.setStyleSheet(
            f"QPushButton {{ background-color: {C('CARD')}; color: {C('TEXT')}; border: 1px solid {C('BORDER')}; "
            f"border-radius: 12px; padding: 0 12px; min-height: 34px; max-height: 34px; font-size: 13px; "
            f"font-weight: 600; text-align: left; }}"
            f"QPushButton:hover {{ border-color: {role('accent')['solid']}; }}")
        self.per_btn.clicked.connect(self._show_per_page_menu)
        self._update_per_text()
        hl.addWidget(self.per_btn)
        return bar

    def _page_btn(self, text: str, page, *, current=False, enabled=True, tip="") -> QPushButton:
        accent = role("accent")
        b = QPushButton(text)
        b.setCursor(Qt.PointingHandCursor if enabled and not current else Qt.ArrowCursor)
        b.setEnabled(enabled)
        if tip:
            b.setToolTip(tip)
        w = max(36, 12 * len(text) + 20)
        b.setStyleSheet(
            f"QPushButton {{ background-color: {accent['solid'] if current else 'transparent'}; "
            f"color: {accent['on_solid'] if current else C('TEXT')}; "
            f"border: 1px solid {accent['solid'] if current else C('BORDER')}; border-radius: 12px; padding: 0; "
            f"min-width: {w}px; max-width: {w}px; min-height: 34px; max-height: 34px; font-size: 13px; font-weight: 700; }}"
            f"QPushButton:hover {{ border-color: {accent['solid']}; }}"
            f"QPushButton:disabled {{ color: {faint_text()}; border-color: {rgba(C('BORDER'), 0.6)}; }}")
        if page is not None and enabled and not current:
            b.clicked.connect(lambda _=False, p=page: self._goto_page(p))
        return b

    def _update_pager(self, total: int, start: int, end: int) -> None:
        while self._pages_box.count():
            w = self._pages_box.takeAt(0).widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        if total <= 0:
            self.range_lbl.setText("")
            self._pages_holder.setVisible(False)
            return
        self.range_lbl.setText(f"แสดง {start + 1:,}–{end:,} จาก {total:,} คน")
        self._pages_holder.setVisible(self._pages > 1)
        if self._pages <= 1:
            return
        cur, last = self._page, self._pages - 1
        self._pages_box.addWidget(self._page_btn("«", 0, enabled=cur > 0, tip="หน้าแรก"))
        self._pages_box.addWidget(self._page_btn("‹", cur - 1, enabled=cur > 0, tip="ก่อนหน้า  (Alt+←)"))
        for n in ud.page_buttons(cur, self._pages):
            if n is None:
                dots = QLabel("…")
                dots.setAlignment(Qt.AlignCenter)
                dots.setFixedWidth(22)
                dots.setStyleSheet(f"color: {faint_text()}; font-size: 15px; background: transparent; min-height: 0;")
                self._pages_box.addWidget(dots)
            else:
                self._pages_box.addWidget(self._page_btn(f"{n + 1:,}", n, current=(n == cur)))
        self._pages_box.addWidget(self._page_btn("›", cur + 1, enabled=cur < last, tip="ถัดไป  (Alt+→)"))
        self._pages_box.addWidget(self._page_btn("»", last, enabled=cur < last, tip="หน้าสุดท้าย"))

    def _goto_page(self, page: int) -> None:
        page = min(max(0, page), self._pages - 1)
        if page == self._page:
            return
        self._page = page
        self._apply(keep_key=self._selected_key)
        self.view.verticalScrollBar().setValue(0)

    def _update_per_text(self) -> None:
        self.per_btn.setText(f"{self._per_page}     ▾")

    def _show_per_page_menu(self) -> None:
        menu = QMenu(self)
        for n in ud.PAGE_SIZES:
            act = menu.addAction(("✓   " if n == self._per_page else "      ") + f"{n} คน")
            act.triggered.connect(lambda _=False, v=n: self._set_per_page(v))
        menu.exec(self.per_btn.mapToGlobal(self.per_btn.rect().topLeft()))

    def _set_per_page(self, n: int) -> None:
        if n == self._per_page:
            return
        first_shown = self._page * self._per_page
        self._per_page = n
        self._page = first_shown // n          # คงรายการแรกของหน้าเดิมไว้ในหน้าใหม่
        self._update_per_text()
        self._apply(keep_key=self._selected_key)
        self.view.verticalScrollBar().setValue(0)

    def _set_show_hidden(self, on: bool) -> None:
        self._show_hidden = bool(on)
        self._page = 0
        self._apply(keep_key=self._selected_key)

    # ── ข้อมูล / ตัวกรอง ──────────────────────────────────
    def refresh(self, force: bool = True) -> None:
        """โหลดข้อมูลใหม่ — force=False จะข้ามถ้าข้อมูลไม่เปลี่ยน (กันกระพริบตอน auto-refresh)"""
        if self.panel.is_editing():
            return
        try:
            recs = ud.build_roster(self.parent_app, self.settings)
        except Exception as exc:
            logger.warning(f"build_roster failed: {exc}")
            recs = []
        sig = (len(recs), sum(r.msg_count for r in recs), sum(r.event_count for r in recs),
               sum(r.donate_total for r in recs), sum(1 for r in recs if r.blocked), sum(1 for r in recs if r.is_bot),
               sum(1 for r in recs if r.renamed), sum(1 for r in recs if r.forced_translate),
               max((r.last_seen for r in recs), default=""))
        if not force and sig == self._signature:
            return
        self._signature = sig
        self._all = recs
        self._rebuild_platform_chips()
        self._apply(keep_key=self._selected_key)

    # ── เก็บข้อความแชทไว้กี่วัน ────────────────────────────
    KEEP_CHOICES = [0, 1, 3, 5, 7, 14, 30, 90]      # 0 = ไม่จำกัด

    def _keep_days(self) -> int:
        return int(getattr(self.settings, "message_history_keep_days", 0) or 0)

    def _update_keep_text(self) -> None:
        d = self._keep_days()
        self.keep_btn.setText(f"🗂 เก็บ {'ไม่จำกัด' if d == 0 else f'{d} วัน'}  ▾")
        self.keep_btn.setToolTip(
            "เก็บตัวข้อความแชทไว้กี่วัน (คลิกเพื่อเปลี่ยน) — ข้อความที่เก่ากว่านั้นจะถูกลบอัตโนมัติทุกครั้งที่เปิดโปรแกรม (ไม่ถามซ้ำ)\n"
            "ยอดข้อความ / แพลตฟอร์ม / วันที่มา ของแต่ละคน และยอดโดเนท-ซับ ไม่ถูกลบ")

    def _show_keep_menu(self) -> None:
        cur = self._keep_days()
        # ค่าที่เคยตั้งไว้แบบกำหนดเอง (ไม่อยู่ในรายการ) ก็แสดงและติ๊กให้เห็น — "ไม่จำกัด" อยู่บนสุด ที่เหลือเรียงน้อย→มาก
        choices = sorted(set(self.KEEP_CHOICES) | {cur}, key=lambda d: (d != 0, d))
        menu = QMenu(self)
        head = menu.addAction("เก็บตัวข้อความแชทไว้นานเท่าไหร่")
        head.setEnabled(False)
        menu.addSeparator()
        for d in choices:
            label = "ไม่จำกัด  (ไม่ลบอัตโนมัติ)" if d == 0 else f"{d} วัน" + ("  (แนะนำ)" if d == 5 else "")
            act = menu.addAction(("✓   " if d == cur else "      ") + label)
            act.triggered.connect(lambda _=False, v=d: self._set_keep_days(v))
        menu.addSeparator()
        note = menu.addAction("เกินกำหนด = ลบเองตอนเปิดโปรแกรม (หรือทุก 6 ชม.) · ยอดรายคนไม่ถูกลบ")
        note.setEnabled(False)
        menu.exec(self.keep_btn.mapToGlobal(self.keep_btn.rect().bottomLeft()))

    def _set_keep_days(self, days: int) -> None:
        if self.settings is None or days == self._keep_days():
            return
        self.settings.message_history_keep_days = int(days)
        save = getattr(self.parent_app, "_save_settings", None)
        try:
            if callable(save):
                save()
            else:
                from settings import save_settings
                save_settings(self.settings)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"save keep-days failed: {exc}")
        self._update_keep_text()

    def _open_clear_history(self) -> None:
        mh = getattr(self.parent_app, "message_history", None)
        if mh is None:
            return
        from ui.dialogs.history_size_dialog import HistorySizeDialog
        days = int(getattr(self.settings, "message_history_keep_days", 0) or 0)
        dlg = HistorySizeDialog(mh, self, manual=True, keep_days=days)
        dlg.exec()
        if dlg.cleared:
            self.close_profile()
            self.refresh(force=True)

    def _rebuild_platform_chips(self) -> None:
        present = {p for r in self._all for p in r.platforms}
        order = [p for p in ud.PLATFORM_ORDER if p in present] + sorted(present - set(ud.PLATFORM_ORDER))
        for b in list(self._plat_btns.values()):
            self._plat_group.removeButton(b)
        while self._plat_row.count():
            w = self._plat_row.takeAt(0).widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._plat_btns = {}
        accent = role("accent")["solid"]
        chip = (f"QPushButton {{ background: transparent; color: {dim_text()}; border: 1px solid {C('BORDER_LIGHT')}; "
                f"border-radius: 17px; padding: 0 14px 0 8px; min-height: 32px; max-height: 32px; "
                f"font-size: 13px; font-weight: 600; }}"
                f"QPushButton:hover {{ color: {C('TEXT')}; border-color: {accent}; }}")
        for key in ["all"] + order:
            b = QPushButton()
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            col = platform_color(key) if key != "all" else accent
            b.setStyleSheet(chip + f"QPushButton:checked {{ background-color: {rgba(col, 0.20)}; "
                                   f"color: {C('TEXT')}; border-color: {col}; }}")
            if key != "all":
                pm = get_platform_pixmap(key, 18)
                if not pm.isNull():
                    b.setIcon(QIcon(pm))
                    b.setIconSize(QSize(18, 18))
            b.setChecked(key == self._platform)
            b.clicked.connect(lambda _=False, k=key: self._set_platform(k))
            self._plat_group.addButton(b)
            self._plat_btns[key] = b
            self._plat_row.addWidget(b)
        self._plat_row.addStretch(1)
        if self._platform != "all" and self._platform not in present:
            self._platform = "all"
            self._plat_btns["all"].setChecked(True)

    def _apply(self, keep_key=None, reset_page: bool = False) -> None:
        q, sh = self._query, self._show_hidden
        if reset_page:
            self._page = 0
        vis = [r for r in self._all if ud.matches(r, self._tab, self._platform, q, sh)]
        vis = ud.sort_records(vis, self._sort)

        # แบ่งหน้า — โมเดลได้เฉพาะรายการของหน้านี้ (วาด/จัดเลย์เอาต์แค่หลักสิบ ไม่ว่าทั้งระบบจะกี่คน)
        self._page, self._pages, start, end = ud.paginate(len(vis), self._page, self._per_page)
        page_recs = vis[start:end]

        # จำนวนบนแท็บ/ชิป (facet: แท็บนับตาม แพลตฟอร์ม+คำค้น, ชิปนับตาม แท็บ+คำค้น)
        for key, b in self._tab_btns.items():
            n = sum(1 for r in self._all if ud.matches(r, key, self._platform, q, sh))
            label = next(l for k, l, _ in TAB_DEFS if k == key)
            b.setText(f"{label}  {n:,}")
        for key, b in self._plat_btns.items():
            n = sum(1 for r in self._all if ud.matches(r, self._tab, key, q, sh))
            b.setText(("🌐 ทุกแพลตฟอร์ม" if key == "all" else platform_label(key)) + f"  {n:,}")

        hidden_n = sum(1 for r in self._all if r.hidden_by_default)
        shown = self._all if sh else [r for r in self._all if not r.hidden_by_default]
        self.hidden_btn.blockSignals(True)
        self.hidden_btn.setChecked(sh)
        self.hidden_btn.blockSignals(False)
        self.hidden_btn.setText(f"{'☑' if sh else '☐'}  แสดงบล็อก/บอท  {hidden_n:,}")
        self.hidden_btn.setVisible(hidden_n > 0)
        sub = (f"ผู้ชม {len(shown):,} คน  ·  ข้อความรวม {sum(r.msg_count for r in shown):,}  ·  "
               f"ผู้สนับสนุน {sum(1 for r in shown if r.supporter):,}")
        if hidden_n and not sh:
            sub += f"  ·  ซ่อน บล็อก/บอท {hidden_n:,}"
        self.subtitle.setText(sub)

        self.model.set_records(page_recs)
        self._update_pager(len(vis), start, end)
        if not vis:
            if not self._all:
                self._empty_icon.setText("🗂️")
                self._empty_title.setText("ยังไม่มีผู้ชมในระบบ")
                self._empty_hint.setText("เมื่อมีคนแชทหรือส่งของขวัญ รายชื่อจะปรากฏที่นี่โดยอัตโนมัติ")
                self._empty_btn.setVisible(False)
            else:
                self._empty_icon.setText("🔎")
                self._empty_title.setText("ไม่พบผู้ใช้ที่ตรงกับตัวกรอง")
                behind = 0 if sh else sum(1 for r in self._all
                                          if ud.matches(r, self._tab, self._platform, q, True))
                self._empty_hint.setText(
                    f"มี {behind:,} รายการที่เป็นบัญชีบล็อก/บอทซึ่งถูกซ่อนอยู่ — ติ๊ก \"แสดงบล็อก/บอท\" เพื่อดู"
                    if behind else "ลองเปลี่ยนแท็บ แพลตฟอร์ม หรือคำค้นหา")
                self._empty_btn.setVisible(True)
            self._stack.setCurrentWidget(self._empty)
        else:
            self._stack.setCurrentWidget(self.view)
            self._relayout_grid()

        # คงการเลือกเดิมไว้ (ไม่ให้ลิ้นชักเด้งปิดเวลาแค่เปลี่ยนตัวกรอง)
        if keep_key:
            idx = self.model.index_of(keep_key)
            if idx.isValid():
                self.view.selectionModel().blockSignals(True)
                self.view.setCurrentIndex(idx)
                self.view.selectionModel().blockSignals(False)
                self.view.scrollTo(idx)
            elif not any(r.key == keep_key for r in self._all):
                self.close_profile()   # คนนี้หายไปจากระบบแล้ว (เช่นลบข้อมูล)

    def _set_tab(self, key: str) -> None:
        self._tab = key
        self._apply(keep_key=self._selected_key, reset_page=True)

    def _set_platform(self, key: str) -> None:
        self._platform = key
        self._apply(keep_key=self._selected_key, reset_page=True)

    def _update_sort_text(self) -> None:
        label = next(l for k, l in SORT_DEFS if k == self._sort)
        self.sort_btn.setText(f"เรียง: {label}   ▾")

    def _show_sort_menu(self) -> None:
        menu = QMenu(self)
        for key, label in SORT_DEFS:
            act = menu.addAction(("✓   " if key == self._sort else "      ") + label)
            act.triggered.connect(lambda _=False, k=key: self._set_sort(k))
        menu.exec(self.sort_btn.mapToGlobal(self.sort_btn.rect().bottomLeft()))

    def _set_sort(self, key: str) -> None:
        self._sort = key
        self._update_sort_text()
        self._apply(keep_key=self._selected_key, reset_page=True)

    def _on_search_commit(self) -> None:
        self._query = self.search.text().strip().lower()
        self._apply(keep_key=self._selected_key, reset_page=True)

    def _clear_filters(self) -> None:
        self._tab = "all"
        self._platform = "all"
        self._query = ""
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self._tab_btns["all"].setChecked(True)
        if "all" in self._plat_btns:
            self._plat_btns["all"].setChecked(True)
        self._apply(keep_key=self._selected_key, reset_page=True)

    # ── grid ─────────────────────────────────────────────
    def eventFilter(self, obj, event):
        if obj is self.view.viewport() and event.type() == QEvent.Resize:
            self._relayout_grid()
        return super().eventFilter(obj, event)

    def _relayout_grid(self) -> None:
        avail = self.view.viewport().width() - 38   # ลบ padding ซ้าย/ขวาของ list
        if avail <= 0:
            return
        cols = max(1, avail // CARD_MIN_W)
        cell_w = avail // cols
        if cell_w != self.delegate.cell_w or self.view.gridSize().width() != cell_w:
            self.delegate.cell_w = cell_w
            self.view.setGridSize(QSize(cell_w, CARD_H))
            self.view.doItemsLayout()

    # ── ลิ้นชักโปรไฟล์ ────────────────────────────────────
    def _on_current_changed(self, cur: QModelIndex, _prev: QModelIndex) -> None:
        rec = self.model.record_at(cur)
        if rec is None:
            return
        self._selected_key = rec.key
        self.panel.set_user(rec.original)
        self._animate_drawer(True)

    def _animate_drawer(self, open_: bool) -> None:
        if open_ == self._drawer_open:
            return
        self._drawer_open = open_
        anim = QPropertyAnimation(self.drawer, b"maximumWidth", self)
        anim.setDuration(220)
        anim.setStartValue(self.drawer.maximumWidth())
        anim.setEndValue(DRAWER_W if open_ else 0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.finished.connect(self._relayout_grid)
        anim.valueChanged.connect(lambda _v: self._relayout_grid())
        self._anim = anim
        anim.start()

    def close_profile(self) -> None:
        self._selected_key = None
        self.view.selectionModel().blockSignals(True)
        self.view.clearSelection()
        self.view.setCurrentIndex(QModelIndex())
        self.view.selectionModel().blockSignals(False)
        self.view.viewport().update()
        self._animate_drawer(False)

    def _on_panel_changed(self) -> None:
        self.refresh(force=True)

    def _on_panel_deleted(self) -> None:
        self.refresh(force=True)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            if self.panel.cancel_edit():
                e.accept()
                return
            if self._drawer_open:
                self.close_profile()
                e.accept()
                return
        super().keyPressEvent(e)
