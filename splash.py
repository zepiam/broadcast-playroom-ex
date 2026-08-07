"""splash.py — Splash screen พร้อม progress bar สำหรับตอนเปิดโปรแกรม

⚠️ สำคัญ: CTk (customtkinter) extends tk.Tk → มันสร้าง root เป็นตัวที่ 2
ถ้า splash สร้าง tk.Tk() แล้วไม่ destroy ทิ้ง → image registry พัง

วิธีแก้: splash ใช้ tk.Tk() ของตัวเอง → เมื่อ destroy ทำลาย root ทิ้งทั้งหมด
หลังจากนั้น CTk จะสร้าง root ใหม่ (สะอาด — image registry เริ่มนับใหม่)
"""
from __future__ import annotations

import os
import tkinter as tk
from PIL import Image, ImageTk


class SplashScreen:
    """Splash window — root + ภาพ + progress bar"""

    def __init__(self, image_path: str = "") -> None:
        # สร้าง root ของ splash (จะถูก destroy ทิ้งตอนปิด)
        self.root = tk.Tk()
        self.root.overrideredirect(True)  # ไม่มี title bar
        # ★ ใช้สี "magic pink" เป็น bg → แล้วตั้ง -transparentcolor ให้โปร่งใสจริง
        # (ทำให้เห็นแค่ภาพ splash ไม่มีกล่องสี่เหลี่ยมพื้นหลัง)
        self._bg_color = "#ff00ff"  # magic pink — สีที่ไม่ควรมีในภาพ splash
        self.root.configure(bg=self._bg_color)
        # ทำให้สีนี้โปร่งใส (Windows only — กลืนเข้ากับ desktop)
        try:
            self.root.attributes("-transparentcolor", self._bg_color)
        except Exception:
            pass  # OS อื่นไม่รองรับ → ใช้ bg ปกติ

        # โหลดภาพ
        self._img = None
        self._photo = None
        img_w, img_h = 500, 500
        if image_path and os.path.exists(image_path):
            try:
                self._img = Image.open(image_path)
                self._img.thumbnail((500, 500), Image.LANCZOS)
                img_w, img_h = self._img.size
            except Exception:
                self._img = None

        win_w = img_w
        win_h = img_h + 50
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - win_w) // 2
        y = (sh - win_h) // 2
        self.root.geometry(f"{win_w}x{win_h}+{x}+{y}")

        # ภาพ
        if self._img is not None:
            try:
                self._photo = ImageTk.PhotoImage(self._img)
                img_label = tk.Label(self.root, image=self._photo, bg=self._bg_color)
                img_label.pack(side="top", fill="x")
                img_label.image = self._photo  # กัน GC
            except Exception:
                self._photo = None
                tk.Label(
                    self.root, text="Broadcast Playroom",
                    font=("Segoe UI", 24, "bold"), fg="#e5e7eb", bg=self._bg_color,
                ).pack(expand=True)
        else:
            tk.Label(
                self.root, text="Broadcast Playroom",
                font=("Segoe UI", 24, "bold"), fg="#e5e7eb", bg=self._bg_color,
            ).pack(expand=True)

        # ★ Pixel Block Loading Bar — สไตล์ Famicom/NES
        self._pixel_total = 20       # จำนวนช่องทั้งหมด
        self._pixel_filled = 0       # ช่องที่เติมแล้ว
        self._pixel_bar_h = 22       # ความสูงแถบ
        self._pixel_gap = 3          # gap ระหว่างช่อง
        self._pixel_color_on = "#22c55e"   # สีช่องที่เติม (เขียวสด)
        self._pixel_color_off = "#1a1f33"  # สีช่องว่าง (เข้ม)
        self._pixel_border = "#2a2f45"     # สีขอบ
        self._pixel_canvas = tk.Canvas(
            self.root, bg=self._bg_color,
            highlightthickness=0,
            height=self._pixel_bar_h + 6,
        )
        self._pixel_canvas.pack(side="bottom", fill="x", padx=24, pady=(8, 16))
        self._render_pixel_bar()
        # animate: เติมทีละช่องทุก 120ms
        self._pixel_anim_id = None
        self._start_pixel_anim()

        # force update
        self.root.update_idletasks()
        self.root.update()

    def _render_pixel_bar(self):
        """render pixel block loading bar — วาดช่องเล็กๆ ทีละช่อง"""
        c = self._pixel_canvas
        c.delete("pixel")
        w = c.winfo_width()
        if w <= 1:
            w = self.root.winfo_width() - 48
        h = self._pixel_bar_h
        gap = self._pixel_gap
        total = self._pixel_total
        block_w = (w - gap * (total - 1)) // total
        block_h = h
        y0 = 3
        for i in range(total):
            x0 = i * (block_w + gap)
            color = self._pixel_color_on if i < self._pixel_filled else self._pixel_color_off
            # ช่อง (สี่เหลี่ยมเติมสี)
            c.create_rectangle(
                x0, y0, x0 + block_w, y0 + block_h,
                fill=color, outline=self._pixel_border, width=1,
                tags="pixel",
            )

    def _start_pixel_anim(self):
        """animate: เติมทีละช่องทุก 120ms"""
        def _tick():
            if self._pixel_filled < self._pixel_total:
                self._pixel_filled += 1
            else:
                # ครบแล้ว → รีเซ็ต (วนลูป)
                self._pixel_filled = 0
            try:
                self._render_pixel_bar()
                self.root.update_idletasks()
            except Exception:
                pass
            self._pixel_anim_id = self.root.after(120, _tick)
        _tick()

    def set_status(self, text: str) -> None:
        """(deprecated — ไม่แสดงข้อความแล้ว) เก็บไว้เผื่อมี caller เดิม"""
        pass

    def destroy(self) -> None:
        """ปิด splash และ destroy root ทิ้ง (CTk จะสร้าง root ใหม่ที่สะอาด)"""
        # หยุด pixel animation
        if self._pixel_anim_id is not None:
            try:
                self.root.after_cancel(self._pixel_anim_id)
            except Exception:
                pass
            self._pixel_anim_id = None
        try:
            self.root.destroy()
        except Exception:
            pass
        # reset default root ให้ CTk สร้างใหม่ได้
        try:
            tk._default_root = None  # type: ignore[attr-defined]
        except Exception:
            pass


def show_splash(image_path: str = "") -> "SplashScreen | None":
    """แสดง splash แล้วคืน instance (เรียก destroy() เมื่อ main window พร้อม)

    คืน None ถ้าสร้างไม่สำเร็จ (ไม่ block startup)
    """
    try:
        return SplashScreen(image_path)
    except Exception:
        return None
