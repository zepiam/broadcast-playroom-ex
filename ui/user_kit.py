"""user_kit.py — ชิ้นส่วน UI ที่ใช้ร่วมกันของหน้า User Manager + แผงโปรไฟล์ผู้ชม

สีทุกตัวอ่านสดจาก ui.theme ตอนสร้าง widget (ไม่ from-import ค่าตายตัว) → ตามธีมที่ผู้ใช้เลือก

ระบบสี (สำคัญ — ทุกธีมต้องใช้ได้):
  ไม่ใช้สีของธีมตรงๆ ตามชื่อ (เช่น HEADING = "ทอง") เพราะบางธีม HEADING == ACCENT (nightwave) หรือ
  ACCENT_2 ≈ ACCENT (ember) ทำให้ความหมายต่างกันแต่สีเหมือนกัน → ใช้ "บทบาทสี" (roles()) แทน:
    accent     = ปุ่มหลัก/แท็บที่เลือก/แชทประจำ          → ACCENT ของธีม
    select     = วงแหวนการ์ดที่เลือก                       → ACCENT (แต่ถ้าใกล้สีแดง "บล็อก" เกินไป เช่น ember → ผสมขาวให้ต่างที่ความสว่าง)
    supporter  = ผู้สนับสนุน/เงิน                          → ทอง (ถ้าใกล้ ACCENT เกินไป เช่น ember → ชมพู)
    blocked    = บล็อก/ลบ                                  → DANGER ของธีม
    new        = ใหม่วันนี้                                 → SUCCESS ของธีม
    info       = บังคับแปล/ข้อมูล                          → ACCENT_2 (ถ้าเหมือน ACCENT เกินไป → ฟ้า/ม่วงอ่อน)
  สีตัวอักษรบนพื้นสีทุกจุดผ่าน readable() ให้ contrast ≥ 4.5:1 เสมอ
"""
from functools import lru_cache

from PySide6.QtCore import Qt, QRectF, QRect, QPoint, QSize, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QLinearGradient, QPixmap, QFont, QBrush, QPen
from PySide6.QtWidgets import QLabel, QFrame, QHBoxLayout, QLineEdit, QLayout, QScrollArea, QWidget

import ui.theme as theme
import user_directory as ud
from ui.platform_icons import get_platform_pixmap


def C(name: str) -> str:
    """สีตามธีมปัจจุบัน เช่น C('CARD'), C('ACCENT')"""
    return getattr(theme, "COLOR_" + name)


# ── คณิตศาสตร์สี ───────────────────────────────────────────
def _rgb(h: str):
    c = QColor(h)
    return c.red(), c.green(), c.blue()


def _hex(r, g, b) -> str:
    return "#%02x%02x%02x" % tuple(int(max(0, min(255, round(v)))) for v in (r, g, b))


def mix(a: str, b: str, t: float) -> str:
    """ผสมสี a→b ที่สัดส่วน t (0=a, 1=b)"""
    ra, ga, ba = _rgb(a)
    rb, gb, bb = _rgb(b)
    return _hex(ra + (rb - ra) * t, ga + (gb - ga) * t, ba + (bb - ba) * t)


def luminance(h: str) -> float:
    """WCAG relative luminance"""
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = _rgb(h)
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def hue_gap(a: str, b: str) -> float:
    """ห่างกันกี่องศาบนวงล้อสี (สีเทา/ขาว/ดำ ไม่มี hue → ถือว่าห่างมาก)"""
    ha, hb = QColor(a).hsvHueF(), QColor(b).hsvHueF()
    if ha < 0 or hb < 0:
        return 180.0
    d = abs(ha - hb) * 360
    return min(d, 360 - d)


def readable(fg: str, bg: str, ratio: float = 4.5) -> str:
    """ปรับ fg ให้อ่านออกบน bg (contrast ≥ ratio) — พื้นมืดดันไปทางขาว พื้นสว่างดันไปทางดำ"""
    target = "#ffffff" if luminance(bg) < 0.5 else "#000000"
    out = fg
    for _ in range(14):
        if contrast(out, bg) >= ratio:
            return out
        out = mix(out, target, 0.14)
    return out


def rgba(hex_color: str, alpha: float) -> str:
    r, g, b = _rgb(hex_color)
    return f"rgba({r},{g},{b},{alpha})"


def on_solid(hex_color: str) -> str:
    """สีตัวอักษรบนพื้นทึบสีนี้ — เลือกขาว/เกือบดำตามที่ contrast สูงกว่าจริง
    (เดิมเทียบแค่ความสว่างหยาบๆ ทำให้ตัวขาวบนแดง #ef4444 ได้แค่ 3.76:1 ต่ำกว่าเกณฑ์ 4.5)"""
    dark = "#0b0e14"
    return dark if contrast(dark, hex_color) >= contrast("#ffffff", hex_color) else "#ffffff"


@lru_cache(maxsize=32)
def _roles(sig: tuple) -> dict:
    bg, card, accent, accent2, danger, success, text = sig

    def pick(cands, avoid, min_gap):
        for c in cands:
            if all(hue_gap(c, a) >= min_gap for a in avoid):
                return c
        return cands[-1]

    supporter = pick(["#fbbf24", "#f472b6", "#34d399"], [accent], 30)
    info = pick([accent2, "#60a5fa", "#a78bfa", "#f472b6"], [accent], 40)
    select = accent if hue_gap(accent, danger) >= 30 else mix(accent, text, 0.55)
    out = {}
    for name, solid in (("accent", accent), ("select", select), ("supporter", supporter),
                        ("blocked", danger), ("new", success), ("info", info)):
        tint_bg = mix(card, solid, 0.22)          # พื้นป้ายโปร่ง (ผสมบนสีการ์ด)
        out[name] = {
            "solid": solid,
            "on_solid": on_solid(solid),
            "text": readable(solid, tint_bg),      # ตัวอักษรสีนี้บนพื้นโปร่ง
            "text_on_card": readable(solid, card),
            "tint_bg": tint_bg,
        }
    return out


def roles() -> dict:
    return _roles((C("BG"), C("CARD"), C("ACCENT"), C("ACCENT_2"), C("DANGER"), C("SUCCESS"), C("TEXT")))


def role(name: str) -> dict:
    return roles()[name]


def platform_color(platform: str) -> str:
    return ud.PLATFORM_COLORS.get(platform, ud.DEFAULT_PLATFORM_COLOR)


def platform_label(platform: str) -> str:
    return ud.PLATFORM_LABELS.get(platform, platform.upper() if platform else "?")


def dim_text() -> str:
    """ข้อความรอง — รับประกันอ่านออกบนการ์ด (ธีมที่ TEXT_DIM จางเกินจะถูกดันให้สว่างขึ้น)"""
    return readable(C("TEXT_DIM"), C("CARD"), 4.5)


def faint_text() -> str:
    """ข้อความจาง (hint/รายละเอียดรอง) — ต่ำสุด 3:1 ตามเกณฑ์ UI ที่ไม่ใช่เนื้อหาหลัก"""
    return readable(C("TEXT_FAINT"), C("CARD"), 3.2)


# ── avatar ─────────────────────────────────────────────────
def paint_avatar(p: QPainter, rect: QRectF, key: str, name: str) -> None:
    g0, g1 = ud.avatar_gradient(key)
    grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
    grad.setColorAt(0.0, QColor(g0))
    grad.setColorAt(1.0, QColor(g1))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(grad))
    p.drawEllipse(rect)
    f = QFont(p.font())
    f.setPixelSize(max(10, int(rect.height() * 0.44)))
    f.setWeight(QFont.Weight.Bold)
    p.setFont(f)
    p.setPen(QColor("#ffffff"))
    p.drawText(rect, Qt.AlignCenter, ud.avatar_initial(name))


def avatar_pixmap(key: str, name: str, size: int) -> QPixmap:
    dpr = 2
    pm = QPixmap(size * dpr, size * dpr)
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
    paint_avatar(p, QRectF(0, 0, size, size), key, name)
    p.end()
    return pm


def avatar_stack_pixmap(size: int = 52) -> QPixmap:
    """ไอคอนหัวหน้า: อวาตาร์ 3 วงซ้อนกัน (วาดเอง ไม่พึ่งอีโมจิที่สีขึ้นกับฟอนต์)"""
    dpr = 2
    pm = QPixmap(size * dpr, size * dpr)
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
    d = size * 0.50
    xs = (size * 0.05, size * 0.25, size * 0.45)
    ys = (size * 0.30, size * 0.18, size * 0.30)
    for i, gi in enumerate((0, 1, 3)):
        r = QRectF(xs[i], ys[i], d, d)
        g0, g1 = ud.AVATAR_GRADIENTS[gi]
        grad = QLinearGradient(r.topLeft(), r.bottomRight())
        grad.setColorAt(0.0, QColor(g0))
        grad.setColorAt(1.0, QColor(g1))
        p.setPen(QPen(QColor(C("BG")), 2))   # วงขอบสีพื้นหลัง ให้วงซ้อนกันแล้วแยกออก
        p.setBrush(QBrush(grad))
        p.drawEllipse(r)
    p.end()
    return pm


# ── ชิ้นส่วนเล็ก ───────────────────────────────────────────
def pill(text: str, bg: str, fg: str = "#ffffff", size: int = 11) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"background-color: {bg}; color: {fg}; font-size: {size}px; font-weight: 700; "
        f"border-radius: 9px; padding: 1px 9px; min-height: 0; border: none;")
    lbl.setAlignment(Qt.AlignCenter)
    return lbl


def role_pill(text: str, role_name: str, solid: bool = False, size: int = 11) -> QLabel:
    """ป้ายสีตามบทบาท — solid=พื้นทึบ, ไม่งั้นพื้นโปร่ง+ตัวอักษรที่ contrast ผ่านแล้ว"""
    r = role(role_name)
    if solid:
        return pill(text, r["solid"], r["on_solid"], size)
    return pill(text, rgba(r["solid"], 0.22), r["text"], size)


def platform_chip(platform: str, *, icon: int = 16, text: bool = True) -> QFrame:
    """ป้ายแพลตฟอร์ม: โลโก้จริงจาก assets + ชื่อ"""
    color = platform_color(platform)
    fr = QFrame()
    fr.setStyleSheet(
        f"QFrame {{ background-color: {rgba(color, 0.14)}; border: 1px solid {rgba(color, 0.45)}; "
        f"border-radius: 11px; }}")
    lay = QHBoxLayout(fr)
    lay.setContentsMargins(6, 2, 9 if text else 6, 2)
    lay.setSpacing(5)
    pm = get_platform_pixmap(platform, icon)
    ic = QLabel()
    ic.setStyleSheet("border: none; background: transparent; min-height: 0;")
    if not pm.isNull():
        ic.setPixmap(pm)
    else:
        ic.setText("●")
        ic.setStyleSheet(f"border: none; background: transparent; color: {color}; min-height: 0; font-size: {icon - 4}px;")
    ic.setFixedSize(icon, icon)
    ic.setAlignment(Qt.AlignCenter)
    lay.addWidget(ic)
    if text:
        t = QLabel(platform_label(platform))
        t.setStyleSheet(f"border: none; background: transparent; color: {C('TEXT')}; "
                        f"font-size: 12px; font-weight: 600; min-height: 0;")
        lay.addWidget(t)
    return fr


def btn_qss(kind: str = "ghost", radius: int = 10, height: int = 0) -> str:
    """QSS ปุ่มเล็กแบบ flat-outline

    ★ ต้องระบุ border/padding/min-height/font-size เอง เพราะ QSS ส่วนกลางของแอปตั้งปุ่มไว้ใหญ่ (padding 8x16, min-height 22)
    ★ QSS `min-height` ไปเขียนทับ QWidget.minimumHeight → `setFixedHeight()` ใช้ไม่ได้ผลถ้า QSS ตั้ง min-height: 0
      ต้องส่ง height มาให้ใส่ min/max-height ใน QSS เอง (บั๊กที่เคยทำให้ปุ่มเตี้ยกว่าที่ตั้ง)
    """
    h = f"min-height: {height}px; max-height: {height}px;" if height else "min-height: 0;"
    base = f"padding: 0 14px; {h} font-size: 13px; font-weight: 600; border-radius: {radius}px;"
    if kind in ("danger", "danger_soft"):
        r = role("blocked")
        if kind == "danger":
            return (f"QPushButton {{ {base} color: {r['on_solid']}; background: {r['solid']}; border: 1px solid {r['solid']}; }}"
                    f"QPushButton:hover {{ background: {mix(r['solid'], '#000000', 0.15)}; }}")
        return (f"QPushButton {{ {base} color: {r['text']}; background: {rgba(r['solid'], 0.14)}; "
                f"border: 1px solid {rgba(r['solid'], 0.65)}; }}"
                f"QPushButton:hover {{ background: {rgba(r['solid'], 0.26)}; }}")
    if kind in ("gold", "info"):
        r = role("supporter" if kind == "gold" else "info")
        return (f"QPushButton {{ {base} color: {r['text']}; background: {rgba(r['solid'], 0.14)}; "
                f"border: 1px solid {rgba(r['solid'], 0.55)}; }}"
                f"QPushButton:hover {{ background: {rgba(r['solid'], 0.26)}; }}")
    if kind == "primary":
        r = role("accent")
        return (f"QPushButton {{ {base} color: {r['on_solid']}; background: {r['solid']}; border: 1px solid {r['solid']}; }}"
                f"QPushButton:hover {{ background: {C('ACCENT_HOVER')}; }}")
    if kind == "flat":
        return (f"QPushButton {{ {base} color: {dim_text()}; background: transparent; border: none; }}"
                f"QPushButton:hover {{ color: {C('TEXT')}; background: {rgba('#ffffff', 0.07)}; }}")
    return (f"QPushButton {{ {base} color: {C('TEXT')}; background: {rgba('#ffffff', 0.05)}; "
            f"border: 1px solid {C('BORDER_LIGHT')}; }}"
            f"QPushButton:hover {{ background: {rgba('#ffffff', 0.10)}; border-color: {role('accent')['solid']}; }}"
            f"QPushButton:disabled {{ color: {faint_text()}; border-color: {C('BORDER')}; }}")


def icon_btn_qss(kind: str, size: int, radius: int) -> str:
    """ปุ่มไอคอนสี่เหลี่ยมจัตุรัสขนาด size (padding 0)"""
    return btn_qss(kind, radius, size).replace("padding: 0 14px", "padding: 0")


class FlowLayout(QLayout):
    """เรียง widget ซ้าย→ขวา แล้วขึ้นบรรทัดใหม่เองเมื่อเต็มความกว้าง (ป้ายแพลตฟอร์ม/ปุ่มไม่ล้นกรอบ)
    ใช้งาน: สร้าง holder = QWidget(); holder.setLayout(FlowLayout(...)) แล้ว add holder เข้า layout แม่"""

    def __init__(self, parent=None, hspacing: int = 6, vspacing: int = 6):
        super().__init__(parent)
        self._items = []
        self._h = hspacing
        self._v = vspacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return self._layout(QRect(0, 0, w, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        s = QSize()
        for it in self._items:
            s = s.expandedTo(it.minimumSize())
        m = self.contentsMargins()
        return s + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _layout(self, rect, test_only):
        m = self.contentsMargins()
        r = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y, line_h = r.x(), r.y(), 0
        for it in self._items:
            sz = it.sizeHint()
            nx = x + sz.width()
            if nx > r.right() + 1 and line_h > 0:
                x = r.x()
                y += line_h + self._v
                nx = x + sz.width()
                line_h = 0
            if not test_only:
                it.setGeometry(QRect(QPoint(x, y), sz))
            x = nx + self._h
            line_h = max(line_h, sz.height())
        return y + line_h - rect.y() + m.bottom()


def flow_holder(*widgets, hspacing: int = 6, vspacing: int = 6) -> QWidget:
    """QWidget ที่เรียงลูกแบบ flow — คืนออกไปวางใน layout แม่ได้เลย"""
    holder = QWidget()
    holder.setStyleSheet("background: transparent;")
    lay = FlowLayout(holder, hspacing, vspacing)
    for w in widgets:
        lay.addWidget(w)
    return holder


def make_scroll() -> QScrollArea:
    """QScrollArea พื้นโปร่ง (QSS ส่วนกลางทาสี viewport ด้วยสีพื้นแอป ต้องล้างเอง)"""
    sc = QScrollArea()
    sc.setWidgetResizable(True)
    sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    sc.setFrameShape(QFrame.NoFrame)
    sc.setStyleSheet(
        "QScrollArea, QScrollArea > QWidget, QScrollArea > QWidget > QWidget "
        "{ background: transparent; border: none; }")
    return sc


def scrollbar_qss() -> str:
    """แถบเลื่อนบางแนวตั้งที่ตามธีม (ใช้กับ QListView — กันลายตาหมากรุกของ style เดิมตอนพื้นโปร่ง)"""
    return (f"QScrollBar:vertical {{ background: {rgba('#ffffff', 0.03)}; width: 10px; margin: 2px; border-radius: 5px; }}"
            f"QScrollBar::handle:vertical {{ background: {C('BORDER_LIGHT')}; min-height: 36px; border-radius: 5px; }}"
            f"QScrollBar::handle:vertical:hover {{ background: {C('TEXT_FAINT')}; }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}"
            f"QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}")


class EscLineEdit(QLineEdit):
    """ช่องพิมพ์ที่กด Esc แล้วยกเลิก (ไม่ให้ Esc ทะลุไปปิดหน้าต่างทั้งหมด)"""
    escapePressed = Signal()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.escapePressed.emit()
            e.accept()
            return
        super().keyPressEvent(e)


class Toast(QLabel):
    """แถบแจ้งผลเล็กๆ ลอยที่ล่างของ parent — หายเองใน ~2 วินาที (แทน QMessageBox ที่ต้องกดปิด)"""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(False)
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_message(self, text: str, ok: bool = True, ms: int = 2200) -> None:
        color = C("SUCCESS") if ok else C("DANGER")
        self.setStyleSheet(
            f"background-color: {C('CARD_HI')}; color: {C('TEXT')}; border: 1px solid {color}; "
            f"border-radius: 12px; padding: 8px 16px; font-size: 13px; font-weight: 600; min-height: 0;")
        self.setText(text)
        self.adjustSize()
        p = self.parentWidget()
        if p is not None:
            self.move(max(8, (p.width() - self.width()) // 2), max(8, p.height() - self.height() - 18))
        self.show()
        self.raise_()
        self._timer.start(ms)
