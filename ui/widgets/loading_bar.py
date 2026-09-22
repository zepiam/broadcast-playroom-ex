"""loading_bar.py — smooth indeterminate loading bar (custom-painted, time-based)

เดิมใช้ QProgressBar(range 0,0) ("busy" mode ของ Qt) — สไตล์เนทีฟของแต่ละ OS วิ่งเป็นก้อนเดียว
กระตุกไม่สม่ำเสมอ (ขึ้นกับ style ของเครื่อง ไม่ควบคุมได้) → วาดเองแทนด้วย QPainter

รูปแบบ: 2 แถบนุ่มๆ กว้างคงที่ (ไล่สีจาง-เข้ม-จาง) กวาดหัวจาก -15% ไป 115% ของความกว้าง ห่างเฟสกันครึ่งรอบ
พิสูจน์ด้วยเลขแล้วว่า "ไม่มีช่วงว่างเปล่า" ตลอดรอบ (แถบหนึ่งเข้าเฟรมก่อนอีกแถบออกเฟรมเสมอ — ดู
dev_tests/app/loading_bar_test.py) ขับด้วยเวลาจริง (time.perf_counter ไม่ใช่นับสเต็ป) เฟรมสม่ำเสมอไม่ว่า
เครื่องจะช้าหรือมีเฟรมหลุดบ้างก็ตาม

★ ความเร็วคงที่ (linear) ไม่ใช้ ease-in-out — ลองแบบ ease-in-out มาก่อนแล้วเจอปัญหา: จังหวะที่หัวแถบเข้าใกล้ขอบขวา
  (ปลายโค้ง ease ที่ชะลอความเร็ว) ทำให้แถบดู "ค้างแป๊บนึงแล้วหายวับ" ก่อนออกจากจอ ไม่สวย — พฤติกรรมทั่วไปของ
  ease-in-out ที่เหมาะกับแอนิเมชันจบรอบเดียว (เข้า-หยุดนิ่ง) แต่ไม่เหมาะกับแอนิเมชันวนซ้ำไม่รู้จบแบบนี้ ที่ต้องการ
  ความเร็วสม่ำเสมอตลอดจนถึงขอบ (เหมือน marquee/shimmer ของโหลดหน้าเว็บทั่วไป) — เปลี่ยนเป็นเชิงเส้นแล้วปัญหาหาย
"""
import time

from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QColor, QLinearGradient, QPainter
from PySide6.QtWidgets import QWidget

import ui.theme as theme  # ★ theme.T(): สีตามธีม + รีเฟรชสดเมื่อสลับธีม (เหมือน theme.styled())


# หัวแถบกวาดจาก HEAD_START ไป HEAD_END ด้วยความเร็วคงที่ (สัดส่วนความกว้าง — ติดลบ/เกิน 1 = อยู่นอกกรอบ)
# ท้ายแถบตามหลังหัวแถบคงที่ WIDTH เสมอ
# ★ ค่าทั้งสามนี้ + เฟส 0.5 รอบ ผ่านการคำนวณแล้วว่าช่วง "หัวแถบยังไม่โผล่พ้นขอบซ้าย" ของแต่ละแถบ (สั้นกว่าเฟส
#   ออฟเซ็ตมาก เพราะไม่มี ease-in ชะลอตอนเริ่ม) → อีกแถบยังมองเห็นอยู่พอดีตอนแถบแรกยังไม่โผล่ ไม่มีจังหวะว่างเปล่า
#   (พิสูจน์แล้วว่ามีความกว้างที่มองเห็นอยู่เสมอ ≥ 30% ของหลอด ตลอดทุกจุดในรอบ)
HEAD_START, HEAD_END, WIDTH = -0.15, 1.15, 0.30
_DELAYS = (0.0, 0.5)


class LoadingBar(QWidget):
    """หลอดโหลดแบบ indeterminate ที่วาดเอง — เรียก start()/stop() แทน setVisible() ตรงๆ
    (start/stop จัดการทั้งความเห็น + timer ให้ในตัว — compat กับโค้ดเดิมที่เคยเรียก setVisible)"""

    def __init__(self, parent=None, track: str = "#1a1f33", accent: str = "#f59e0b",
                 cycle_ms: int = 2100, fps: int = 30):
        super().__init__(parent)
        self._track_hex = track
        self._accent_hex = accent
        self._track = QColor(theme.T(track))
        self._accent = QColor(theme.T(accent))
        self._cycle_ms = cycle_ms
        self._t0 = None
        self.setFixedHeight(4)
        self.setVisible(False)
        self._timer = QTimer(self)
        self._timer.setInterval(max(1, round(1000 / fps)))
        self._timer.timeout.connect(self.update)
        theme.register_theme_listener(self._on_theme_changed)

    def _on_theme_changed(self):
        self._track = QColor(theme.T(self._track_hex))
        self._accent = QColor(theme.T(self._accent_hex))
        self.update()

    def start(self):
        """เริ่มวิ่ง (setVisible(True) + เริ่มจับเวลา) — เรียกซ้ำได้ (รีสตาร์ทรอบใหม่)"""
        self._t0 = time.perf_counter()
        self.setVisible(True)
        self._timer.start()

    def stop(self):
        """หยุดวิ่ง + ซ่อน (setVisible(False))"""
        self._timer.stop()
        self.setVisible(False)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect()
        radius = r.height() / 2.0
        p.setPen(Qt.NoPen)
        p.setBrush(self._track)
        p.drawRoundedRect(r, radius, radius)
        if self._t0 is None or r.width() <= 0:
            return
        elapsed_ms = (time.perf_counter() - self._t0) * 1000.0
        cycle_pos = (elapsed_ms / self._cycle_ms) % 1.0
        for delay in _DELAYS:
            phase = (cycle_pos - delay) % 1.0
            head = HEAD_START + (HEAD_END - HEAD_START) * phase   # ความเร็วคงที่ตลอดรอบ — ไม่ชะลอตอนใกล้ขอบขวา
            x0, x1 = head - WIDTH, head
            left_px, right_px = x0 * r.width(), x1 * r.width()
            if right_px <= 0 or left_px >= r.width() or right_px <= left_px:
                continue
            grad = QLinearGradient(left_px, 0, right_px, 0)
            transparent = QColor(self._accent); transparent.setAlpha(0)
            grad.setColorAt(0.0, transparent)
            grad.setColorAt(0.5, self._accent)
            grad.setColorAt(1.0, transparent)
            p.setBrush(grad)
            band_rect = QRectF(left_px, 0.0, right_px - left_px, r.height())  # QPainter clips to the widget automatically
            p.drawRoundedRect(band_rect, radius, radius)
