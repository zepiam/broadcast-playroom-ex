# -*- coding: utf-8 -*-
"""replie_service.py — บริการจัดการระบบ Replie (ตอบกลับอัตโนมัติบนจอ OBS Overlay)

คุณสมบัติหลัก:
- แปลงคำสั่งแชท (เช่น !donate, !qrcode) เป็นภาพ/แถบข้อความบนจอ Overlay
- Cooldown รวมคำขอ (Coalescing): ในช่วงเวลาเดียวกัน คำขอซ้ำจากผู้ชมหลายคนจะถูกรวบเป็นการแสดงผล 1 ครั้ง
- Emergency Control: ปุ่มปิด/ซ่อนทันทีจาก OBS Dock
- Per-command Mute: ปิดชั่วคราว (5m, 15m, 30m) หรือปิดถาวร
- ปรับแต่งพิกัด, สเกล, ทิศทางอนิเมชัน (Slide เข้า/ออก), และมี Demo ให้ทดสอบทุกรูปแบบ
"""
from __future__ import annotations
import collections
from PySide6.QtCore import QObject, Signal

import time
import logging
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger("replie_service")


@dataclass
class ReplieCommand:
    """ข้อมูลคำสั่ง Replie แต่ละคำสั่ง พร้อมการแยกตั้งค่า Ticker และ Image อิสระ"""
    name: str                       # e.g. "!donate"
    desc: str = ""                  # คำอธิบายคำสั่ง เช่น "ข้อมูลการโดเนท"
    enabled: bool = True            # เปิด/ปิดถาวร
    muted_until: float = 0.0        # timestamp พักคำสั่งชั่วคราว (0 = ไม่ได้พัก)
    duration_sec: int = 15          # ระยะเวลาค้างบนจอรวม (วินาที)
    cooldown_sec: int = 15          # Cooldown ป้องกันสแปม (วินาที)
    progress_style: str = "cyan"    # "cyan" | "gold" | "violet" | "emerald" | "rainbow" | "sunset"
    
    # Countdown Settings
    countdown_type: str = "number"  # "none" | "number" | "bar"
    countdown_font: str = "Kanit"   # font family for digital number
    countdown_color: str = "#ffffff"# hex color for digital number
    countdown_shadow: bool = True   # text shadow for number
    
    # ── 1. Ticker Element (แถบข้อความ / ข้อความวิ่ง / กล่องข้อความ) ──
    ticker_enabled: bool = True
    title: str = ""                 # หัวข้อ (เช่น "💖 สนับสนุนช่อง")
    text: str = ""                  # ข้อความแสดงผล (เช่น "PromptPay 08x-xxx-xxxx")
    layout: str = "bottom_ticker"   # "bottom_ticker" | "full_ticker" | "card"
    ticker_font_size: int = 16      # ขนาดตัวหนังสือ (px)
    ticker_font: str = "Kanit"      # ชื่อฟอนต์ตัวหนังสือ
    ticker_color: str = "#f8fafc"   # สีตัวหนังสือ
    ticker_bold: bool = True        # ตัวหนา
    ticker_anim_style: str = "together" # "together" | "staged_slide" | "staged_fade"
    ticker_frameless: bool = False  # ไม่มีกรอบหลัง (โปร่งใส)
    ticker_pos_x: int = 50          # 0 - 100 %
    ticker_pos_y: int = 88          # 0 - 100 %
    ticker_scale: float = 1.0       # 0.5 - 1.5
    ticker_opacity: int = 95        # 20 - 100 %
    ticker_anim_in: str = "slide-up"
    ticker_anim_out: str = "slide-down"
    ticker_delay_sec: float = 0.0   # ดีเลย์ก่อนเริ่มแสดง (วินาที)

    # ── 2. Image Element (ป้ายรูปภาพ / QR Code / โลโก้) ──
    image_enabled: bool = False
    image_url: str = ""             # ลิงก์หรือ path รูปภาพ
    image_frameless: bool = True    # ไม่มีกรอบหลัง (โปร่งใส)
    image_top_text: str = ""        # ข้อความด้านบนภาพ (เมื่อมีกรอบ)
    image_bottom_text: str = ""     # ข้อความด้านล่างภาพ (เมื่อมีกรอบ)
    image_pos_x: int = 85           # 0 - 100 %
    image_pos_y: int = 50           # 0 - 100 %
    image_scale: float = 1.0        # 0.5 - 1.5
    image_opacity: int = 95         # 20 - 100 %
    image_anim_in: str = "slide-left"
    image_anim_out: str = "slide-right"
    image_delay_sec: float = 0.0    # ดีเลย์ก่อนเริ่มแสดง (เช่น 2.5 วินาที ตามหลัง Ticker แต่จบพร้อมกัน)

    # Preset & Sub-command Sequence
    position_preset: str = "bottom" # "bottom" | "top" | "left" | "right"
    sub_command: Optional[str] = None       # ชื่อคำสั่งย่อยที่นำมาต่อคิว/แทรก (e.g. "!qrcode")
    sub_command_delay: float = 0.0          # เวลาเริ่มคำสั่งย่อย (วินาที)

    # Legacy fields
    type: str = "combo"
    frameless: bool = False
    pos_x: Optional[int] = None
    pos_y: Optional[int] = None
    scale: Optional[float] = None
    anim_in: Optional[str] = None
    anim_out: Optional[str] = None

    def is_active(self) -> bool:
        if not self.enabled:
            return False
        if self.muted_until > time.time():
            return False
        return True

    def get_remaining_mute_sec(self) -> int:
        now = time.time()
        if self.muted_until > now:
            return int(self.muted_until - now)
        return 0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "desc": self.desc,
            "enabled": self.enabled,
            "muted_until": self.muted_until,
            "duration_sec": self.duration_sec,
            "cooldown_sec": self.cooldown_sec,
            "progress_style": self.progress_style,
            "countdown_type": self.countdown_type,
            "countdown_font": self.countdown_font,
            "countdown_color": self.countdown_color,
            "countdown_shadow": self.countdown_shadow,

            # Ticker element
            "ticker_enabled": self.ticker_enabled,
            "title": self.title,
            "text": self.text,
            "layout": self.layout,
            "ticker_font_size": self.ticker_font_size,
            "ticker_font": self.ticker_font,
            "ticker_color": self.ticker_color,
            "ticker_bold": self.ticker_bold,
            "ticker_anim_style": self.ticker_anim_style,
            "ticker_frameless": self.ticker_frameless,
            "ticker_pos_x": self.ticker_pos_x,
            "ticker_pos_y": self.ticker_pos_y,
            "ticker_scale": self.ticker_scale,
            "ticker_opacity": self.ticker_opacity,
            "ticker_anim_in": self.ticker_anim_in,
            "ticker_anim_out": self.ticker_anim_out,
            "ticker_delay_sec": self.ticker_delay_sec,

            # Image element
            "image_enabled": self.image_enabled,
            "image_url": self.image_url,
            "image_frameless": self.image_frameless,
            "image_top_text": self.image_top_text,
            "image_bottom_text": self.image_bottom_text,
            "image_pos_x": self.image_pos_x,
            "image_pos_y": self.image_pos_y,
            "image_scale": self.image_scale,
            "image_opacity": self.image_opacity,
            "image_anim_in": self.image_anim_in,
            "image_anim_out": self.image_anim_out,
            "image_delay_sec": self.image_delay_sec,

            # Preset & Sub-command Sequence
            "position_preset": self.position_preset,
            "sub_command": self.sub_command,
            "sub_command_delay": self.sub_command_delay,

            # Legacy compatibility
            "type": "combo" if (self.ticker_enabled and self.image_enabled) else ("image" if self.image_enabled else "text"),
            "frameless": self.ticker_frameless or self.image_frameless,
            "pos_x": self.ticker_pos_x,
            "pos_y": self.ticker_pos_y,
            "scale": self.ticker_scale,
            "anim_in": self.ticker_anim_in,
            "anim_out": self.ticker_anim_out,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ReplieCommand:
        has_new = ("ticker_enabled" in data) or ("image_enabled" in data)
        if has_new:
            t_en = bool(data.get("ticker_enabled", True))
            i_en = bool(data.get("image_enabled", False))
        else:
            old_type = data.get("type", "text")
            if old_type == "image":
                t_en = bool(data.get("text"))
                i_en = True
            elif old_type == "combo":
                t_en = True
                i_en = True
            else:
                t_en = True
                i_en = bool(data.get("image_url"))

        t_pos_x = data.get("ticker_pos_x")
        if t_pos_x is None:
            t_pos_x = data.get("pos_x", 50 if data.get("layout") in ("bottom_ticker", "full_ticker") else 85)
            
        t_pos_y = data.get("ticker_pos_y")
        if t_pos_y is None:
            t_pos_y = data.get("pos_y", 88 if data.get("layout") in ("bottom_ticker", "full_ticker") else 50)

        i_pos_x = data.get("image_pos_x")
        if i_pos_x is None:
            i_pos_x = data.get("pos_x", 85)

        i_pos_y = data.get("image_pos_y")
        if i_pos_y is None:
            i_pos_y = data.get("pos_y", 50)

        return cls(
            name=data.get("name", "!cmd"),
            desc=data.get("desc", ""),
            enabled=data.get("enabled", True),
            muted_until=float(data.get("muted_until", 0.0)),
            duration_sec=int(data.get("duration_sec", 15)),
            cooldown_sec=int(data.get("cooldown_sec", 15)),
            progress_style=data.get("progress_style", "cyan"),
            countdown_type=data.get("countdown_type", "number"),
            countdown_font=data.get("countdown_font", "Kanit"),
            countdown_color=data.get("countdown_color", "#ffffff"),
            countdown_shadow=bool(data.get("countdown_shadow", True)),

            # Ticker
            ticker_enabled=t_en,
            title=data.get("title", ""),
            text=data.get("text", "") or data.get("ticker_text", ""),
            layout=data.get("layout", "bottom_ticker") or data.get("ticker_layout", "bottom_ticker"),
            ticker_font_size=int(data.get("ticker_font_size", 16)),
            ticker_font=str(data.get("ticker_font", "Kanit")),
            ticker_color=str(data.get("ticker_color", "#f8fafc")),
            ticker_bold=bool(data.get("ticker_bold", True)),
            ticker_anim_style=data.get("ticker_anim_style", "together"),
            ticker_frameless=bool(data.get("ticker_frameless", data.get("frameless", False))),
            ticker_pos_x=int(t_pos_x if t_pos_x is not None else 50),
            ticker_pos_y=int(t_pos_y if t_pos_y is not None else 88),
            ticker_scale=float(data.get("ticker_scale", data.get("scale", 1.0))),
            ticker_opacity=int(data.get("ticker_opacity", 95)),
            ticker_anim_in=data.get("ticker_anim_in", data.get("anim_in", "slide-up")),
            ticker_anim_out=data.get("ticker_anim_out", data.get("anim_out", "slide-down")),
            ticker_delay_sec=float(data.get("ticker_delay_sec", 0.0)),

            # Image
            image_enabled=i_en,
            image_url=data.get("image_url", ""),
            image_frameless=bool(data.get("image_frameless", True)),
            image_top_text=data.get("image_top_text", ""),
            image_bottom_text=data.get("image_bottom_text", ""),
            image_pos_x=int(i_pos_x if i_pos_x is not None else 85),
            image_pos_y=int(i_pos_y if i_pos_y is not None else 50),
            image_scale=float(data.get("image_scale", data.get("scale", 1.0))),
            image_opacity=int(data.get("image_opacity", 95)),
            image_anim_in=data.get("image_anim_in", "slide-left"),
            image_anim_out=data.get("image_anim_out", "slide-right"),
            image_delay_sec=float(data.get("image_delay_sec", 0.0)),

            # Preset & Sub-command
            position_preset=data.get("position_preset", "bottom"),
            sub_command=data.get("sub_command", None),
            sub_command_delay=float(data.get("sub_command_delay", 0.0)),

            # Legacy compatibility
            type="combo" if (t_en and i_en) else ("image" if i_en else "text"),
            frameless=bool(data.get("frameless", False)),
            pos_x=data.get("pos_x"),
            pos_y=data.get("pos_y"),
            scale=data.get("scale"),
            anim_in=data.get("anim_in"),
            anim_out=data.get("anim_out"),
        )


class ReplieService(QObject):
    """ระบบจัดการ Replie ในโปรแกรม"""

    status_changed = Signal(dict)

    def __init__(self, parent_app=None):
        super().__init__(parent_app if (parent_app is not None and isinstance(parent_app, QObject)) else None)
        self.parent_app = parent_app
        self.settings = getattr(parent_app, "settings", None)
        
        # State การแสดงผลปัจจุบัน
        self.current_active: Optional[dict] = None
        self.active_until: float = 0.0
        self._auto_expire_timer: Optional[threading.Timer] = None
        self.scheduled_commands: Dict[str, dict] = {}
        self._playback_queue: collections.deque = collections.deque()
        
        # Cooldown tracker: {cmd_name: next_allowed_ts}
        self._command_cooldowns: Dict[str, float] = {}
        # Per-user per-command cooldown: {(author_lower, cmd_name): next_allowed_ts}
        self._user_command_cooldowns: Dict[Tuple[str, str], float] = {}

        # Default commands หากยังไม่เคยตั้งค่า
        self.commands: Dict[str, ReplieCommand] = {}
        self._init_defaults()

        # Loop Mode attributes (สตรีมเมอร์เปิดรันวนลูปทิ้งไว้)
        self.loop_active: bool = False
        self.loop_command: Optional[str] = None  # cmd name or '__all__'
        self.loop_interval_sec: int = 45         # เว้นช่วงระหว่างการแสดงผล (วินาที)
        self._loop_thread: Optional[threading.Thread] = None
        self._loop_stop_event = threading.Event()
        self._loop_index: int = 0

    def _init_defaults(self):
        """โหลดคำสั่งเริ่มต้นหรือดึงจากการตั้งค่า"""
        saved = getattr(self.settings, "replie_commands", None)
        if saved and isinstance(saved, dict):
            for k, v in saved.items():
                if isinstance(v, dict):
                    cmd_obj = ReplieCommand.from_dict(v)
                    proper_key = (cmd_obj.name or k).strip().lower()
                    self.commands[proper_key] = cmd_obj
            return

        # ตัวอย่างคำสั่งเริ่มต้น
        # ตัวอย่างคำสั่ง Dual Element (!donate): Ticker ขึ้นก่อน แล้ว QR Code ตามมา 2.5 วิ จบพร้อมกัน!
        # 3 คำสั่งเริ่มต้นทางการของโปรแกรม Replie
        # 1. !donatecombo: แสดงข้อความพร้อมภาพ QR Code (Combo Sequence)
        default_combo = ReplieCommand(
            name="!donatecombo",
            desc="แสดงข้อความพร้อมภาพ QR Code",
            title="💖 สนับสนุนช่อง",
            text="สามารถร่วมสนับสนุนและเป็นกำลังใจให้สตรีมเมอร์ได้โดยการโดเนทผ่าน QR Code นี้ได้เลยครับ",
            duration_sec=18,
            cooldown_sec=15,
            progress_style="gold",
            countdown_type="number",
            countdown_font="Kanit",
            countdown_color="#ffffff",
            countdown_shadow=True,
            ticker_enabled=True,
            layout="full_ticker",
            ticker_font_size=24,
            ticker_font="Kanit",
            ticker_color="#f8fafc",
            ticker_bold=True,
            ticker_anim_style="staged_slide",
            ticker_frameless=False,
            ticker_pos_x=50,
            ticker_pos_y=95,
            ticker_scale=1.41,
            ticker_opacity=95,
            ticker_anim_in="slide-up",
            ticker_anim_out="slide-down",
            ticker_delay_sec=0.0,
            image_enabled=False,
            image_url="assets/men9ch-qr-500x500.png",
            image_frameless=True,
            image_pos_x=50,
            image_pos_y=85,
            image_scale=0.9,
            image_opacity=95,
            image_anim_in="slide-up",
            image_anim_out="slide-down",
            image_delay_sec=0.0,
            position_preset="custom",
            sub_command="!qrcode",
            sub_command_delay=7.4,
            type="combo",
            frameless=True,
            pos_x=50,
            pos_y=95,
            scale=1.41,
            anim_in="slide-up",
            anim_out="slide-down"
        )

        # 2. !donate: อธิบายรายละเอียดโดเนท (Ticker ข้อความ)
        default_donate = ReplieCommand(
            name="!donate",
            desc="อธิบายรายละเอียดโดเนท",
            title="💖 สนับสนุนช่อง (ข้อความ)",
            text="สามารถโอนเข้า Truemoney & Promptpay ได้ที่เบอร์ 08x-xxx-xxxx ได้โดยตรงเลยครับ",
            duration_sec=15,
            cooldown_sec=15,
            progress_style="rainbow",
            countdown_type="bar",
            countdown_font="Kanit",
            countdown_color="#ffffff",
            countdown_shadow=True,
            ticker_enabled=True,
            layout="bottom_ticker",
            ticker_font_size=20,
            ticker_font="Kanit",
            ticker_color="#f8fafc",
            ticker_bold=True,
            ticker_anim_style="staged_fade",
            ticker_frameless=False,
            ticker_pos_x=50,
            ticker_pos_y=2,
            ticker_scale=1.33,
            ticker_opacity=95,
            ticker_anim_in="slide-down",
            ticker_anim_out="slide-up",
            position_preset="top",
            sub_command=None,
            sub_command_delay=0.0,
            type="text",
            frameless=True,
            pos_x=50,
            pos_y=2,
            scale=1.33,
            anim_in="slide-down",
            anim_out="slide-up"
        )

        # 3. !qrcode: แสดงภาพ QR Code
        default_qr = ReplieCommand(
            name="!qrcode",
            desc="แสดงภาพ QR Code",
            title="📱 Scan QR Code",
            text="สแกน QR Code เพื่อทำรายการ",
            image_url="assets/men9ch-qr-500x500.png",
            duration_sec=12,
            cooldown_sec=20,
            progress_style="cyan",
            countdown_type="number",
            countdown_font="Kanit",
            countdown_color="#ffffff",
            countdown_shadow=True,
            ticker_enabled=False,
            image_enabled=True,
            image_frameless=True,
            image_pos_x=98,
            image_pos_y=98,
            image_scale=0.9,
            image_opacity=95,
            image_anim_in="slide-up",
            image_anim_out="slide-down",
            image_delay_sec=0.0,
            position_preset="custom",
            sub_command=None,
            sub_command_delay=0.0,
            type="image",
            frameless=True,
            pos_x=50,
            pos_y=88,
            scale=1.0,
            anim_in="slide-up",
            anim_out="slide-down"
        )

        self.commands["!donatecombo"] = default_combo
        self.commands["!donate"] = default_donate
        self.commands["!qrcode"] = default_qr
        self.save_settings()

    def save_settings(self):
        """บันทึกลง AppSettings"""
        if self.settings:
            cleaned_commands = {}
            for k, cmd in self.commands.items():
                proper_key = (cmd.name or k).strip().lower()
                cleaned_commands[proper_key] = cmd
            self.commands = cleaned_commands
            self.settings.replie_commands = {k: cmd.to_dict() for k, cmd in self.commands.items()}
            try:
                from settings import save_settings
                save_settings(self.settings)
            except Exception as e:
                logger.warning(f"Failed to save replie settings: {e}")

    def is_widget_installed(self) -> bool:
        """ตรวจสอบว่ามี Widget Replie ติดตั้งและเปิดใช้งานอยู่บน Overlay หรือไม่"""
        try:
            if self.parent_app and hasattr(self.parent_app, "composer_server") and self.parent_app.composer_server:
                return bool(self.parent_app.composer_server._is_widget_installed("replie"))
            if self.parent_app and hasattr(self.parent_app, "_replie_widget_exists"):
                return bool(self.parent_app._replie_widget_exists())
            if self.settings:
                widgets = list(getattr(self.settings, "composer_widgets", []) or [])
                if any(isinstance(w, dict) and w.get("type") == "replie" and w.get("enabled", True) for w in widgets):
                    return True
                pages = getattr(self.settings, "composer_pages", []) or []
                for p in pages:
                    if isinstance(p, dict):
                        pw = p.get("widgets", [])
                        if any(isinstance(w, dict) and w.get("type") == "replie" and w.get("enabled", True) for w in pw):
                            return True
        except Exception:
            pass
        return False

    def handle_chat_message(self, platform: str, author: str, text: str) -> bool:
        """ตรวจจับข้อความแชท หากตรงกับคำสั่ง Replie จะประมวลผลทันที

        Returns:
            bool: True ถ้าตรงกับคำสั่ง Replie (เพื่อนำไป skip_tts หรือแสดงผล)
        """
        if not text:
            return False
        
        # เช็คว่าเปิดใช้งานระบบ Replie โดยรวมหรือไม่ และมี Widget วางอยู่บนจอหรือไม่
        if not getattr(self.settings, "replie_enabled", True):
            return False
        if not self.is_widget_installed():
            return False

        first_token = text.strip().split()[0].lower()
        if first_token not in self.commands:
            return False

        cmd = self.commands[first_token]
        if not cmd.is_active():
            return True  # คำสั่งปิดอยู่หรือโดน mute -> ดักไว้ ไม่ให้อ่านเป็นแชทปกติ

        author_key = (author or "").strip().lower()

        # 1. เช็คว่าผู้ใช้นี้ถูกบล็อกไม่ให้ใช้คำสั่ง Replie หรือไม่
        blocked_users = [str(u).strip().lower() for u in (getattr(self.settings, "replie_blocked_users", []) or [])]
        if author_key in blocked_users:
            logger.info(f"Replie: '{first_token}' ignored because user '{author}' is blocked from using Replie.")
            return True  # ดูดคำสั่งไว้ ไม่ให้ออกเสียง TTS และไม่ให้แสดงขึ้นจอ

        now = time.time()

        # 2. เช็ค Cooldown เฉพาะบุคคล (User Cooldown - ป้องกัน troll ป่วนซ้ำ)
        # ผู้ใช้เดิมจะใช้คำสั่งเดิมซ้ำได้หลังจากผ่านไป 5 นาที (300 วินาที)
        # แต่ละคำสั่งนับแยกกัน เช่น !donate กับ !qrcode ไม่ชนกัน
        user_cd_key = (author_key, first_token)
        next_user_allowed = self._user_command_cooldowns.get(user_cd_key, 0.0)
        if now < next_user_allowed:
            rem_sec = int(next_user_allowed - now)
            logger.info(f"Replie: '{first_token}' from user '{author}' blocked by user cooldown ({rem_sec}s remaining).")
            return True  # ดูดคำสั่งไว้ ไม่ให้ขึ้นจอซ้ำและไม่อ่าน TTS

        # 3. เช็ค Cooldown รวมของคำสั่ง (Global Command Cooldown)
        # ป้องกันกรณีคนพิมพ์ซ้ำพร้อมๆ กันหลายคนในช่วงเวลาสั้นๆ (cmd.cooldown_sec เช่น 15-20 วิ)
        next_allowed = self._command_cooldowns.get(first_token, 0.0)
        if now < next_allowed:
            logger.info(f"Replie: '{first_token}' from {author} absorbed by active global cooldown.")
            return True

        # อัปเดต Cooldown ของคำสั่ง (ส่วนกลาง)
        self._command_cooldowns[first_token] = now + cmd.cooldown_sec

        # อัปเดต Cooldown เฉพาะบุคคล (ค่าเริ่มต้น 5 นาที = 300 วิ)
        user_cd_duration = float(getattr(self.settings, "replie_user_cooldown_sec", 300))
        self._user_command_cooldowns[user_cd_key] = now + user_cd_duration

        # ทำความสะอาด dict เมื่อมีขนาดใหญ่เกินไป
        if len(self._user_command_cooldowns) > 2000:
            self._user_command_cooldowns = {k: v for k, v in self._user_command_cooldowns.items() if v > now}

        # สั่งแสดงผลขึ้นจอ Overlay
        self.show_replie(cmd, triggered_by=author)
        return True

    def _resolve_image_data_url(self, image_path: str) -> str:
        """แปลง image_path (ไฟล์บนเครื่องหรือ relative path) เป็น Base64 Data URL ให้ OBS Browser นำไปแสดงผลได้แน่นอน 100%"""
        if not image_path:
            return ""
        if str(image_path).startswith("data:") or str(image_path).startswith("http://") or str(image_path).startswith("https://"):
            return image_path

        import base64
        import mimetypes
        import os
        try:
            from settings import get_base_dir
            base_dir = get_base_dir()
        except Exception:
            base_dir = os.path.dirname(os.path.abspath(__file__))

        candidates = [
            str(image_path),
            os.path.join(base_dir, str(image_path)),
            os.path.join(base_dir, "assets", os.path.basename(str(image_path))),
            os.path.join(base_dir, "assets", str(image_path)),
        ]
        for p in candidates:
            if os.path.isfile(p):
                try:
                    mime, _ = mimetypes.guess_type(p)
                    if not mime:
                        mime = "image/png"
                    with open(p, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode("ascii")
                    return f"data:{mime};base64,{b64}"
                except Exception as e:
                    logger.warning(f"Replie: failed to encode image {p} to data url: {e}")
                    break
        return image_path

    def show_replie(self, cmd: ReplieCommand, triggered_by: str = "", is_loop: bool = False, test_mode: Optional[str] = None) -> bool:
        """ส่งคำสั่งขึ้นแสดงผลบนหน้าจอ OBS Overlay พร้อมระบบคิว (Queue) และป้องกันการแสดงซ้ำซ้อน (Deduplication)"""
        if not self.is_widget_installed():
            logger.info(f"Replie: show_replie '{cmd.name}' skipped because Replie widget is not installed on overlay.")
            return False
        now = time.time()
        is_currently_active = self.current_active is not None and self.active_until > now

        # ดักที่ 1: หากคำสั่งนี้กำลังแสดงอยู่บนจออยู่แล้ว ห้ามขึ้นซ้ำหรือเบิ้ลเด็ดขาด
        if is_currently_active and self.current_active.get("name", "").lower() == cmd.name.lower():
            logger.info(f"Replie: '{cmd.name}' is already currently playing on screen. Ignored duplicate trigger from {triggered_by}.")
            return False

        # ดักที่ 2: หากคำสั่งนี้อยู่ในคิวรอเล่นอยู่แล้ว ห้ามใส่คิวซ้ำ
        if any(item["cmd"].name.lower() == cmd.name.lower() for item in self._playback_queue):
            logger.info(f"Replie: '{cmd.name}' is already in playback queue. Ignored duplicate queue request.")
            return False

        # ดักที่ 3: หากมีคำสั่งอื่นกำลังแสดงอยู่บนจอ ให้ต่อคิว FIFO ทันที
        if is_currently_active:
            self._playback_queue.append({
                "cmd": cmd,
                "triggered_by": triggered_by,
                "is_loop": is_loop,
                "test_mode": test_mode
            })
            logger.info(f"Replie: '{cmd.name}' queued behind active command (queue position #{len(self._playback_queue)}).")
            self._broadcast_dock_status()
            return True

        # ถ้าจอว่างอยู่ ให้แสดงผลทันที
        self._play_now(cmd, triggered_by, is_loop, test_mode)
        return True

    def _play_now(self, cmd: ReplieCommand, triggered_by: str = "", is_loop: bool = False, test_mode: Optional[str] = None):
        """เริ่มแสดงผลคำสั่งบนจอ Overlay ทันที"""
        now = time.time()
        duration = 3 if test_mode else max(2, cmd.duration_sec)
        self.active_until = now + duration

        # Resolve sub-command if inserted
        eff_ticker_enabled = cmd.ticker_enabled
        eff_image_enabled = cmd.image_enabled
        
        # Base Ticker config
        ticker_cfg = {
            "enabled": cmd.ticker_enabled,
            "title": cmd.title,
            "text": cmd.text,
            "layout": cmd.layout,
            "ticker_font_size": getattr(cmd, "ticker_font_size", 16),
            "ticker_font": getattr(cmd, "ticker_font", "Kanit"),
            "ticker_color": getattr(cmd, "ticker_color", "#f8fafc"),
            "ticker_bold": getattr(cmd, "ticker_bold", True),
            "anim_style": getattr(cmd, "ticker_anim_style", "together"),
            "frameless": getattr(cmd, "ticker_frameless", False),
            "pos_x": cmd.ticker_pos_x,
            "pos_y": cmd.ticker_pos_y,
            "scale": cmd.ticker_scale,
            "opacity": getattr(cmd, "ticker_opacity", 95) / 100.0,
            "anim_in": getattr(cmd, "ticker_anim_in", "slide-up"),
            "anim_out": getattr(cmd, "ticker_anim_out", "slide-down"),
            "delay_sec": getattr(cmd, "ticker_delay_sec", 0.0),
            "countdown_type": getattr(cmd, "countdown_type", "number"),
            "countdown_font": getattr(cmd, "countdown_font", "Kanit"),
            "countdown_color": getattr(cmd, "countdown_color", "#ffffff"),
            "countdown_shadow": getattr(cmd, "countdown_shadow", True),
        }

        # Base Image config
        resolved_img = self._resolve_image_data_url(cmd.image_url) if cmd.image_enabled else cmd.image_url
        image_cfg = {
            "enabled": cmd.image_enabled,
            "image_url": resolved_img,
            "frameless": getattr(cmd, "image_frameless", True),
            "top_text": getattr(cmd, "image_top_text", ""),
            "bottom_text": getattr(cmd, "image_bottom_text", ""),
            "pos_x": cmd.image_pos_x,
            "pos_y": cmd.image_pos_y,
            "scale": cmd.image_scale,
            "opacity": getattr(cmd, "image_opacity", 95) / 100.0,
            "anim_in": getattr(cmd, "image_anim_in", "slide-left"),
            "anim_out": getattr(cmd, "image_anim_out", "slide-right"),
            "delay_sec": getattr(cmd, "image_delay_sec", 0.0),
            "countdown_type": getattr(cmd, "countdown_type", "number"),
            "countdown_font": getattr(cmd, "countdown_font", "Kanit"),
            "countdown_color": getattr(cmd, "countdown_color", "#ffffff"),
            "countdown_shadow": getattr(cmd, "countdown_shadow", True),
        }

        # If has sub_command, overlay sub_command element with delay
        sub_cname = getattr(cmd, "sub_command", None)
        if sub_cname and sub_cname in self.commands:
            sub_cmd = self.commands[sub_cname]
            sub_delay = max(0.0, float(getattr(cmd, "sub_command_delay", 0.0)))
            if sub_cmd.image_enabled and not cmd.image_enabled:
                resolved_sub_img = self._resolve_image_data_url(sub_cmd.image_url)
                image_cfg = {
                    "enabled": True,
                    "image_url": resolved_sub_img,
                    "frameless": getattr(sub_cmd, "image_frameless", True),
                    "top_text": getattr(sub_cmd, "image_top_text", ""),
                    "bottom_text": getattr(sub_cmd, "image_bottom_text", ""),
                    "pos_x": sub_cmd.image_pos_x,
                    "pos_y": sub_cmd.image_pos_y,
                    "scale": sub_cmd.image_scale,
                    "opacity": getattr(sub_cmd, "image_opacity", 95) / 100.0,
                    "anim_in": getattr(sub_cmd, "image_anim_in", "slide-left"),
                    "anim_out": getattr(sub_cmd, "image_anim_out", "slide-right"),
                    "delay_sec": sub_delay,
                    "countdown_type": getattr(sub_cmd, "countdown_type", "number"),
                    "countdown_font": getattr(sub_cmd, "countdown_font", "Kanit"),
                    "countdown_color": getattr(sub_cmd, "countdown_color", "#ffffff"),
                    "countdown_shadow": getattr(sub_cmd, "countdown_shadow", True),
                }
                eff_image_enabled = True
            elif sub_cmd.ticker_enabled and not cmd.ticker_enabled:
                ticker_cfg = {
                    "enabled": True,
                    "title": sub_cmd.title,
                    "text": sub_cmd.text,
                    "layout": sub_cmd.layout,
                    "ticker_font_size": getattr(sub_cmd, "ticker_font_size", 16),
                    "ticker_font": getattr(sub_cmd, "ticker_font", "Kanit"),
                    "ticker_color": getattr(sub_cmd, "ticker_color", "#f8fafc"),
                    "ticker_bold": getattr(sub_cmd, "ticker_bold", True),
                    "anim_style": getattr(sub_cmd, "ticker_anim_style", "together"),
                    "frameless": getattr(sub_cmd, "ticker_frameless", False),
                    "pos_x": sub_cmd.ticker_pos_x,
                    "pos_y": sub_cmd.ticker_pos_y,
                    "scale": sub_cmd.ticker_scale,
                    "opacity": getattr(sub_cmd, "ticker_opacity", 95) / 100.0,
                    "anim_in": getattr(sub_cmd, "ticker_anim_in", "slide-up"),
                    "anim_out": getattr(sub_cmd, "ticker_anim_out", "slide-down"),
                    "delay_sec": sub_delay,
                    "countdown_type": getattr(sub_cmd, "countdown_type", "number"),
                    "countdown_font": getattr(sub_cmd, "countdown_font", "Kanit"),
                    "countdown_color": getattr(sub_cmd, "countdown_color", "#ffffff"),
                    "countdown_shadow": getattr(sub_cmd, "countdown_shadow", True),
                }
                eff_ticker_enabled = True

        payload = {
            "name": cmd.name,
            "title": cmd.title or cmd.name,
            "duration_sec": duration,
            "progress_style": getattr(cmd, "progress_style", "cyan"),
            "countdown_type": getattr(cmd, "countdown_type", "number"),
            "countdown_font": getattr(cmd, "countdown_font", "Kanit"),
            "countdown_color": getattr(cmd, "countdown_color", "#ffffff"),
            "countdown_shadow": getattr(cmd, "countdown_shadow", True),
            "is_loop": is_loop,
            "triggered_by": triggered_by,
            "timestamp": now,
            "test_mode": test_mode,

            # Ticker & Image Configuration
            "ticker": ticker_cfg,
            "image": image_cfg,

            # Top-level legacy fallbacks
            "type": "combo" if (cmd.ticker_enabled and cmd.image_enabled) else ("image" if cmd.image_enabled else "text"),
            "text": cmd.text,
            "image_url": resolved_img if cmd.image_enabled else cmd.image_url,
            "layout": cmd.layout,
            "pos_x": cmd.ticker_pos_x if cmd.ticker_enabled else cmd.image_pos_x,
            "pos_y": cmd.ticker_pos_y if cmd.ticker_enabled else cmd.image_pos_y,
            "scale": cmd.ticker_scale if cmd.ticker_enabled else cmd.image_scale,
            "opacity": (cmd.ticker_opacity if cmd.ticker_enabled else cmd.image_opacity) / 100.0,
            "anim_in": cmd.ticker_anim_in if cmd.ticker_enabled else cmd.image_anim_in,
            "anim_out": cmd.ticker_anim_out if cmd.ticker_enabled else cmd.image_anim_out,
            "frameless": cmd.ticker_frameless if cmd.ticker_enabled else cmd.image_frameless,
        }

        self.current_active = payload

        # Cancel previous expire timer if running
        if self._auto_expire_timer:
            try:
                self._auto_expire_timer.cancel()
            except Exception:
                pass
            self._auto_expire_timer = None

        # Schedule automatic expiration to sync dock & tool and play next queue
        def _on_expire():
            if self.current_active is not None and time.time() >= (self.active_until - 0.2):
                self._on_display_finished()

        self._auto_expire_timer = threading.Timer(duration, _on_expire)
        self._auto_expire_timer.daemon = True
        self._auto_expire_timer.start()

        # Broadcast ไปยัง OBS Overlay และ Dock
        self._broadcast({
            "type": "replie_show",
            "data": payload
        })
        dock_data = self.get_dock_data()
        self._broadcast_dock_status()
        try:
            self.status_changed.emit(dock_data)
        except Exception:
            pass

    def _on_display_finished(self):
        """เมื่อคำสั่งปัจจุบันจบลง ให้เคลียร์จอและนำคำสั่งถัดไปในคิวขึ้นมาเล่นต่ออัตโนมัติ"""
        self.current_active = None
        self.active_until = 0.0
        self._broadcast({"type": "replie_dismiss"})
        dock_data = self.get_dock_data()
        self._broadcast_dock_status()
        try:
            self.status_changed.emit(dock_data)
        except Exception:
            pass

        # ตรวจสอบคิว: ถ้ามีคำสั่งรออยู่ ให้เล่นคำสั่งถัดไปหลังจากเว้นจังหวะอนิเมชันออก 0.4 วินาที
        if self._playback_queue:
            next_item = self._playback_queue.popleft()
            logger.info(f"Replie: Auto-playing next queued command '{next_item['cmd'].name}'...")
            def _play_next():
                self._play_now(
                    next_item["cmd"],
                    next_item["triggered_by"],
                    next_item["is_loop"],
                    next_item["test_mode"]
                )
            t = threading.Timer(0.4, _play_next)
            t.daemon = True
            t.start()

    def dismiss_current(self, clear_queue: bool = False):
        """[✕ ซ่อนทันที / Panic Dismiss] สั่งปิดสิ่งที่กำลังแสดงผลอยู่บนจอทันที"""
        if self._auto_expire_timer:
            try:
                self._auto_expire_timer.cancel()
            except Exception:
                pass
            self._auto_expire_timer = None

        if clear_queue:
            self._playback_queue.clear()

        self._on_display_finished()
        logger.info("Replie: current display dismissed.")

    def mute_command(self, cmd_name: str, minutes: int):
        """พักการใช้งานคำสั่งนี้ชั่วคราว (เช่น 5, 15, 30 นาที)"""
        cmd = self.commands.get(cmd_name.lower())
        if cmd:
            cmd.muted_until = time.time() + (minutes * 60)
            self.save_settings()
            self._broadcast_dock_status()
            logger.info(f"Replie: {cmd_name} muted for {minutes} minutes.")

    def unmute_command(self, cmd_name: str):
        """ยกเลิกการพักคำสั่ง"""
        cmd = self.commands.get(cmd_name.lower())
        if cmd:
            cmd.muted_until = 0.0
            self.save_settings()
            self._broadcast_dock_status()

    def toggle_command(self, cmd_name: str, enabled: Optional[bool] = None) -> bool:
        """เปิด/ปิด การใช้งานคำสั่งนี้ถาวร"""
        cmd = self.commands.get(cmd_name.lower())
        if cmd:
            if enabled is None:
                cmd.enabled = not cmd.enabled
            else:
                cmd.enabled = enabled
            if cmd.enabled:
                cmd.muted_until = 0.0
            self.save_settings()
            dock_data = self.get_dock_data()
            self._broadcast_dock_status()
            try:
                self.status_changed.emit(dock_data)
            except Exception:
                pass
            return cmd.enabled
        return False

    def start_schedule(self, cmd_name: str, interval_min: int):
        """เริ่มรันคำสั่งอัตโนมัติทุกๆ interval_min นาที"""
        cmd_key = cmd_name.strip().lower()
        cmd = self.commands.get(cmd_key)
        if not cmd:
            return
        self.stop_schedule(cmd_key)

        interval_min = max(1, int(interval_min))
        interval_sec = interval_min * 60
        next_ts = time.time() + interval_sec

        def _schedule_tick():
            if cmd_key not in self.scheduled_commands:
                return
            cmd_obj = self.commands.get(cmd_key)
            if cmd_obj:
                self.show_replie(cmd_obj, triggered_by=f"Auto-Schedule ({interval_min}m)")

            # Schedule next execution
            if cmd_key in self.scheduled_commands:
                t = threading.Timer(interval_sec, _schedule_tick)
                t.daemon = True
                self.scheduled_commands[cmd_key]["timer"] = t
                self.scheduled_commands[cmd_key]["next_ts"] = time.time() + interval_sec
                t.start()
                self._broadcast_dock_status()

        t = threading.Timer(interval_sec, _schedule_tick)
        t.daemon = True
        self.scheduled_commands[cmd_key] = {
            "interval_min": interval_min,
            "next_ts": next_ts,
            "timer": t
        }
        t.start()
        self._broadcast_dock_status()
        try:
            self.status_changed.emit(self.get_dock_data())
        except Exception:
            pass
        logger.info(f"Replie: Scheduled '{cmd_key}' every {interval_min} minutes.")

    def stop_schedule(self, cmd_name: str):
        """หยุดการรันคำสั่งอัตโนมัติตามเวลา"""
        cmd_key = cmd_name.strip().lower()
        entry = self.scheduled_commands.pop(cmd_key, None)
        if entry and entry.get("timer"):
            try:
                entry["timer"].cancel()
            except Exception:
                pass
        self._broadcast_dock_status()
        try:
            self.status_changed.emit(self.get_dock_data())
        except Exception:
            pass
        logger.info(f"Replie: Stopped schedule for '{cmd_key}'.")

    def start_loop(self, cmd_name: str = "__all__", interval_sec: Optional[int] = None):
        """เริ่มรันคำสั่ง Replie แบบวนลูปอัตโนมัติ (เช่น สตรีมเมอร์ไม่อยู่ที่โต๊ะ)"""
        if interval_sec is not None and interval_sec > 0:
            self.loop_interval_sec = interval_sec
        self.loop_command = cmd_name
        self.loop_active = True
        self._loop_index = 0

        # หยุด thread เดิมถ้ากำลังทำงานอยู่
        self._loop_stop_event.set()
        if self._loop_thread and self._loop_thread.is_alive():
            self._loop_thread.join(timeout=1.0)

        self._loop_stop_event.clear()
        self._loop_thread = threading.Thread(target=self._loop_worker, daemon=True, name="ReplieLoopThread")
        self._loop_thread.start()

        self._broadcast_dock_status()
        logger.info(f"Replie: Started loop for '{cmd_name}' every {self.loop_interval_sec}s.")

    def stop_loop(self):
        """หยุดการวนลูป Replie ทันที"""
        if not self.loop_active and not self._loop_thread:
            return
        self.loop_active = False
        self.loop_command = None
        self._loop_stop_event.set()
        self._broadcast_dock_status()
        logger.info("Replie: Stopped loop.")

    def toggle_loop(self, cmd_name: str, interval_sec: Optional[int] = None):
        """สลับเปิด/ปิด การวนลูปคำสั่ง"""
        if self.loop_active and self.loop_command == cmd_name:
            self.stop_loop()
        else:
            self.start_loop(cmd_name, interval_sec)

    def _loop_worker(self):
        """Worker thread สำหรับยิงคำสั่งวนลูปตามช่วงเวลาที่กำหนด"""
        while not self._loop_stop_event.is_set():
            target_cmd: Optional[ReplieCommand] = None

            if self.loop_command == "__all__":
                active_cmds = [c for c in self.commands.values() if c.is_active()]
                if active_cmds:
                    target_cmd = active_cmds[self._loop_index % len(active_cmds)]
                    self._loop_index += 1
            elif self.loop_command:
                c = self.commands.get(self.loop_command.lower())
                if c and c.is_active():
                    target_cmd = c

            if target_cmd:
                try:
                    self.show_replie(target_cmd, triggered_by="Streamer (Loop)", is_loop=True)
                except Exception as e:
                    logger.warning(f"Replie loop show error: {e}")

            duration = target_cmd.duration_sec if target_cmd else 8
            wait_time = max(5, duration + self.loop_interval_sec)

            if self._loop_stop_event.wait(timeout=wait_time):
                break

    def update_live_preview(self, pos_x: Optional[int] = None, pos_y: Optional[int] = None,
                            offset_x: int = 0, offset_y: int = 0,
                            scale: Optional[float] = None, opacity: Optional[float] = None,
                            target: str = "all"):
        """ส่งอัปเดตพิกัดสดไปยัง OBS Overlay ทันทีขณะเลื่อน slider พร้อมรองรับ target (ticker / image)"""
        now = time.time()
        if not self.current_active or (self.active_until <= now):
            self.trigger_demo("ticker" if target == "ticker" else "image")

        # ขยายเวลาค้างจอไประหว่างกำลังเลื่อน slider
        self.active_until = now + 12.0

        payload = {
            "target": target,
            "pos_x": pos_x if pos_x is not None else 50,
            "pos_y": pos_y if pos_y is not None else 88,
            "offset_x": offset_x,
            "offset_y": offset_y,
            "scale": scale if scale is not None else 1.0,
            "opacity": opacity if opacity is not None else 0.95,
            "show_guides": True,
        }
        self._broadcast({
            "type": "replie_update_pos",
            "data": payload
        })

    def trigger_demo(self, mode: str = "ticker"):
        """ส่งคำสั่ง Demo จำลองขึ้นจอ Overlay ทันทีสำหรับทดสอบ"""
        s = self.settings
        pos_x = getattr(s, "replie_pos_x", 85)
        pos_y = getattr(s, "replie_pos_y", 50)
        offset_x = getattr(s, "replie_offset_x", 0)
        offset_y = getattr(s, "replie_offset_y", 0)
        scale = getattr(s, "replie_scale", 1.0)
        opacity = getattr(s, "replie_opacity_pct", 95)
        anim_in = getattr(s, "replie_anim_in", "slide-left")
        anim_out = getattr(s, "replie_anim_out", "slide-right")

        if mode == "ticker":
            demo_cmd = ReplieCommand(
                name="!donate (Demo)",
                type="text",
                title="💖 สนับสนุนสตรีมเมอร์ (Demo Ticker)",
                text="PromptPay: 08x-xxx-xxxx หรือโดเนทผ่าน TrueMoney ขอบคุณทุกการสนับสนุนครับ!",
                duration_sec=7,
                layout="bottom_ticker",
                anim_in="slide-up",
                anim_out="slide-down",
            )
        elif mode == "image":
            demo_cmd = ReplieCommand(
                name="!qrcode (Demo)",
                type="image",
                title="📱 QR Code (Demo)",
                text="สแกนเพื่อเปิดลิงก์หรือสนับสนุนช่อง",
                image_url="assets/sample_qr.png",
                duration_sec=8,
                layout="side_card",
                pos_x=pos_x,
                pos_y=pos_y,
                scale=scale,
                anim_in=anim_in,
                anim_out=anim_out,
            )
        else:  # combo (both image and text)
            demo_cmd = ReplieCommand(
                name="!specs (Demo)",
                type="combo",
                title="💻 Gaming Rig (Demo Combo)",
                text="CPU: Ryzen 7 7800X3D | GPU: RTX 4080 Super | RAM: 32GB DDR5",
                image_url="assets/sample_qr.png",
                duration_sec=9,
                layout="floating_card",
                pos_x=pos_x,
                pos_y=pos_y,
                scale=scale,
                anim_in=anim_in,
                anim_out=anim_out,
            )

        self.show_replie(demo_cmd, triggered_by="Streamer (Demo)")

    def get_dock_data(self) -> dict:
        """ข้อมูลสำหรับส่งให้ OBS Dock นำไปเรนเดอร์ UI"""
        now = time.time()
        is_active = self.current_active is not None and (self.active_until > now)
        
        cmd_list = []
        for name, cmd in self.commands.items():
            rem_mute = cmd.get_remaining_mute_sec()
            if not cmd.enabled:
                status_text = "⇄ ปิดรับคำสั่งนี้"
                status_type = "disabled"
            elif rem_mute > 0:
                mins = (rem_mute // 60) + 1
                status_text = f"⏸️ พักชั่วคราว ({mins} น.)"
                status_type = "muted"
            else:
                status_text = "⇄ พร้อมรับคำสั่งนี้"
                status_type = "ready"

            is_sched = cmd.name.lower() in self.scheduled_commands
            sched_info = self.scheduled_commands.get(cmd.name.lower(), {})
            sched_next_ts = sched_info.get("next_ts", 0.0)
            cmd_list.append({
                "name": cmd.name,
                "title": cmd.title or cmd.name,
                "type": cmd.type,
                "layout": cmd.layout,
                "enabled": cmd.enabled,
                "is_scheduled": is_sched,
                "sched_interval_min": sched_info.get("interval_min", 0),
                "sched_next_ts": sched_next_ts,
                "sched_rem_sec": max(0, int(sched_next_ts - now)) if is_sched else 0,
                "muted": rem_mute > 0,
                "rem_mute_sec": rem_mute,
                "status_text": status_text,
                "status_type": status_type,
            })

        return {
            "is_active": is_active,
            "active_command": self.current_active.get("name") if is_active else None,
            "active_title": self.current_active.get("title") if is_active else None,
            "duration_sec": self.current_active.get("duration_sec", 8) if is_active else 8,
            "rem_active_sec": max(0, int(self.active_until - now)) if is_active else 0,
            "queue_count": len(self._playback_queue),
            "queued_commands": [q["cmd"].name for q in self._playback_queue],
            "loop_active": self.loop_active,
            "loop_command": self.loop_command,
            "loop_interval_sec": self.loop_interval_sec,
            "commands": cmd_list,
        }

    def _broadcast(self, data: dict):
        """ส่ง event ผ่าน composer_server WebSocket ไปยัง Overlay และ Dock"""
        if self.parent_app and hasattr(self.parent_app, "composer_server") and self.parent_app.composer_server:
            try:
                self.parent_app.composer_server._broadcast_threadsafe(data)
            except Exception as e:
                logger.debug(f"Replie broadcast error: {e}")

    def _broadcast_dock_status(self):
        """อัปเดตสถานะ Replie ไปยัง OBS Dock ทันที"""
        self._broadcast({
            "type": "replie_status",
            "data": self.get_dock_data()
        })
