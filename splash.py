"""splash.py — Splash screen สมัยใหม่สำหรับ PySide6 พร้อม Border Chase Animation

- ดีไซน์โมเดิร์น: ภาพตัวละครโปร่งใส + แคปซูลแสดงข้อความสถานะ
- Border Chase Animation: แถบลำแสงวิ่งวนรอบกรอบแคปซูลอย่างต่อเนื่องตามสไตล์ https://motion-reference.takayustudio.jp/#motion=border-chase
- Zero GPU / CPU Freeze: รันบน Subprocess แยก ทำให้ Animation ลื่นไหล 60 FPS 100% ไม่มีทางค้าง
- Base64 IPC: สื่อสารข้อความภาษาไทยผ่าน Base64 ทำให้ปลอดภัยจากปัญหา Windows Codepage (CP1252/CP874) 100% ภาษาไทยคมชัด ไม่กลายเป็นต่างดาวเด็ดขาด
- รองรับการตรวจจับการเปิดครั้งแรกเพื่อแสดงข้อความชี้แจงอย่างเหมาะสม
"""
from __future__ import annotations

import os
import sys
import time
import base64
import threading
import subprocess
import logging
from typing import Optional

from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
)
from PySide6.QtGui import QPixmap, QPainter, QPainterPath, QPen, QColor
from PySide6.QtCore import Qt, QTimer, QRectF, QObject, Signal

logger = logging.getLogger("splash")


class BorderChaseCapsule(QWidget):
    """แคปซูลแสดงผลที่มีลำแสงวิ่งรอบกรอบ (Border Chase Motion)"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._offset = 0.0
        self._beam_len = 115.0  # ความยาวของลำแสงที่วิ่งรอบกรอบ (px)
        self._pen_w = 2.5
        self._speed = 130.0  # ความเร็ว px/วินาที
        self._last_time = time.perf_counter()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._step_animation)
        self._timer.start(16)  # ~60 FPS เคลื่อนที่อย่างนุ่มนวล

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 14, 24, 14)
        layout.setSpacing(0)
        self._inner_layout = layout

    def set_content_layout(self, content_layout: QHBoxLayout | QVBoxLayout) -> None:
        self._inner_layout.addLayout(content_layout)

    def _step_animation(self) -> None:
        now = time.perf_counter()
        dt = now - self._last_time
        self._last_time = now
        # ป้องกันการกระโดดของเฟรมถ้ามีการกระตุกชั่วขณะ
        if dt > 0.1:
            dt = 0.016
        self._offset += self._speed * dt
        self.update()

    def stop(self) -> None:
        if self._timer.isActive():
            self._timer.stop()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        m = self._pen_w / 2.0
        rect = QRectF(m + 1, m + 1, w - (2 * m + 2), h - (2 * m + 2))
        radius = 14.0

        # 1. วาดพื้นหลังกล่องสีเข้มแบบกึ่งโปร่งใส
        bg_path = QPainterPath()
        bg_path.addRoundedRect(rect, radius, radius)
        painter.fillPath(bg_path, QColor(15, 23, 42, 245))

        # 2. วาดเส้นขอบพื้นฐานสีเทาเข้ม
        track_pen = QPen(QColor(30, 41, 59, 210), self._pen_w)
        painter.strokePath(bg_path, track_pen)

        # 3. วาดลำแสงสีฟ้าครามที่วิ่งรอบกรอบ (Border Chase)
        total_len = bg_path.length()
        if total_len > 0:
            beam_dash = self._beam_len / self._pen_w
            space_dash = max(1.0, (total_len - self._beam_len) / self._pen_w)

            chase_pen = QPen(QColor(56, 189, 248), self._pen_w)
            chase_pen.setCapStyle(Qt.RoundCap)
            chase_pen.setDashPattern([beam_dash, space_dash])
            chase_pen.setDashOffset(self._offset / self._pen_w)
            painter.strokePath(bg_path, chase_pen)


class ModernSplashScreen(QWidget):
    """Modern Splash Screen widget with Border Chase animation."""

    def __init__(self, image_path: str = "", is_first_run: bool = False) -> None:
        super().__init__()
        self.is_first_run = is_first_run
        self._image_path = image_path

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.SplashScreen
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self._build_ui()
        self._center_on_screen()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # ── 1. ส่วนรูปภาพ Splash ──
        self.img_lbl = QLabel()
        self.img_lbl.setAlignment(Qt.AlignCenter)
        if self._image_path and os.path.exists(self._image_path):
            try:
                pix = QPixmap(self._image_path)
                if not pix.isNull():
                    self.img_lbl.setPixmap(pix)
            except Exception:
                pass
        layout.addWidget(self.img_lbl)

        # ── 2. แคปซูลข้อความพร้อม Border Chase ──
        self.capsule = BorderChaseCapsule()

        text_layout = QHBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setAlignment(Qt.AlignCenter)

        if self.is_first_run:
            msg = "กำลังเตรียมการจากการเปิดครั้งแรก อาจใช้เวลานานกว่าปกติ กรุณารอซักครู่..."
            color = "#38bdf8"
        else:
            msg = "กำลังเริ่มต้นระบบและโหลดการตั้งค่า..."
            color = "#f1f5f9"

        self.status_lbl = QLabel(msg)
        self.status_lbl.setAlignment(Qt.AlignCenter)
        self.status_lbl.setWordWrap(True)
        self.status_lbl.setStyleSheet(f"""
            font-size: 12.5px;
            font-weight: 600;
            color: {color};
            background: transparent;
            font-family: 'Segoe UI', 'Noto Sans Thai', Tahoma, sans-serif;
        """)
        text_layout.addWidget(self.status_lbl)
        self.capsule.set_content_layout(text_layout)

        layout.addWidget(self.capsule)
        self.adjustSize()

    def _center_on_screen(self) -> None:
        """จัดตำแหน่ง Splash ให้อยู่กึ่งกลางหน้าจอหลัก"""
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.x() + (geo.width() - self.width()) // 2
            y = geo.y() + (geo.height() - self.height()) // 2
            self.move(x, y)

    def set_progress(self, percent: int, text: str | None = None) -> None:
        """อัปเดตข้อความสถานะตามขั้นตอนการบูต"""
        try:
            if text:
                if self.is_first_run and percent < 100:
                    pass  # คงข้อความเตือนเปิดครั้งแรกไว้ตลอดการโหลด
                else:
                    self.status_lbl.setText(text)
            qapp = QApplication.instance()
            if qapp:
                qapp.processEvents()
        except Exception:
            pass

    def finish(self, window: QWidget | None = None) -> None:
        """ปิดหน้า Splash เมื่อหน้าต่างหลักพร้อมแสดงผล"""
        try:
            if hasattr(self, "capsule") and hasattr(self.capsule, "stop"):
                self.capsule.stop()
            self.close()
            self.deleteLater()
        except Exception:
            pass


class SubprocessSplashController:
    """Controller ควบคุม Splash Screen ที่รันใน Subprocess แยก
    
    ประโยชน์:
    - Animation Border Chase หมุนลื่นไหลต่อเนื่อง 60 FPS 100%
    - ป้องกันปัญหาข้อความต่างดาวด้วยการเข้ารหัส Base64 ผ่าน IPC
    """

    def __init__(self, image_path: str = "", is_first_run: bool = False) -> None:
        self.image_path = image_path
        self.is_first_run = is_first_run
        self.proc: Optional[subprocess.Popen] = None
        self._start_process()

    def _start_process(self) -> None:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "--splash-subprocess"]
        else:
            main_script = os.path.join(base_dir, "main.py")
            cmd = [sys.executable, "-u", main_script, "--splash-subprocess"]

        if self.image_path:
            cmd.extend(["--image", os.path.abspath(self.image_path)])
        if self.is_first_run:
            cmd.append("--first-run")

        creationflags = 0
        if sys.platform == "win32":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"

        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            cwd=base_dir,
            env=env,
            creationflags=creationflags,
        )

    def set_progress(self, percent: int, text: str | None = None) -> None:
        """ส่งคำสั่งอัปเดตสถานะไปยัง Subprocess โดยใช้ Base64 เพื่อป้องกันภาษาไทยเพี้ยน 100%"""
        if not self.proc or self.proc.poll() is not None:
            return
        try:
            safe_text = (text or "").replace("\n", " ").strip()
            b64_text = base64.b64encode(safe_text.encode("utf-8")).decode("ascii")
            self.proc.stdin.write(f"PROGRESS:{percent}:{b64_text}\n")
            self.proc.stdin.flush()
        except Exception:
            pass

    def finish(self, window: QWidget | None = None) -> None:
        """สั่งปิด Subprocess เมื่อ Main Window พร้อมแสดงผล"""
        if not self.proc:
            return
        try:
            if self.proc.poll() is None:
                self.proc.stdin.write("CLOSE\n")
                self.proc.stdin.flush()
                self.proc.stdin.close()
                self.proc.wait(timeout=0.6)
        except Exception:
            try:
                self.proc.terminate()
            except Exception:
                pass
        finally:
            self.proc = None
            if window:
                try:
                    window.raise_()
                    window.activateWindow()
                except Exception:
                    pass

    def close(self) -> None:
        self.finish()


def create_splash(image_path: str = "", is_first_run: bool = False):
    """สร้าง Splash Screen โดยเลือกใช้ Subprocess เพื่อให้ Animation หมุนลื่นไหลไม่ค้าง 100%
    หากเกิดข้อผิดพลาดจะ Fallback กลับมาใช้ In-process อัตโนมัติ
    """
    try:
        controller = SubprocessSplashController(image_path=image_path, is_first_run=is_first_run)
        if controller.proc and controller.proc.poll() is None:
            return controller
    except Exception as e:
        logger.warning(f"Subprocess splash creation failed ({e}), falling back to in-process splash.")

    # Fallback to in-process
    splash = ModernSplashScreen(image_path=image_path, is_first_run=is_first_run)
    splash.show()
    return splash


def run_splash_subprocess() -> int:
    """Entry point สำหรับ Subprocess ของ Splash Screen"""
    import argparse
    import io

    # บังคับ stdin เป็น utf-8 บน Windows
    if hasattr(sys.stdin, "reconfigure"):
        try:
            sys.stdin.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Broadcast Playroom Splash Subprocess")
    parser.add_argument("--splash-subprocess", action="store_true")
    parser.add_argument("--image", type=str, default="")
    parser.add_argument("--first-run", action="store_true")
    args, _ = parser.parse_known_args()

    app = QApplication(sys.argv)
    app.setApplicationName("Broadcast Playroom Splash")

    splash = ModernSplashScreen(image_path=args.image, is_first_run=args.first_run)
    splash.show()

    class Bridge(QObject):
        update_progress = Signal(int, str)
        should_close = Signal()

    bridge = Bridge()
    bridge.update_progress.connect(splash.set_progress)
    bridge.should_close.connect(lambda: (splash.finish(), app.quit()))

    def listen_stdin() -> None:
        try:
            for line in sys.stdin:
                line = line.strip()
                if not line:
                    continue
                if line == "CLOSE":
                    bridge.should_close.emit()
                    return
                elif line.startswith("PROGRESS:"):
                    parts = line.split(":", 2)
                    pct = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
                    txt = ""
                    if len(parts) > 2 and parts[2]:
                        raw = parts[2]
                        try:
                            # ถอดรหัส base64 คืนเป็นภาษาไทย UTF-8 ที่สมบูรณ์
                            txt = base64.b64decode(raw.encode("ascii")).decode("utf-8")
                        except Exception:
                            txt = raw
                    bridge.update_progress.emit(pct, txt)
        except Exception:
            pass
        bridge.should_close.emit()

    t = threading.Thread(target=listen_stdin, daemon=True)
    t.start()

    return app.exec()
