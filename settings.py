"""settings.py — persistence สำหรับ TTS for Livestream

เก็บ:
  - chat source (twitch channel / youtube url)
  - voice + reading options
  - filter (blocked_users, banned_words, replace_words, secret_codes)
  - notification (donate/sub/raid sounds + read toggles)
  - queue throttle
  - UI appearance
"""
from __future__ import annotations

import glob
import json
import os
from dataclasses import dataclass, field

from notification_manager import NotificationConfig, NotificationSound
from text_filter import SecretCode, TextFilter

from data_dir import get_data_dir
CACHE_DIR = get_data_dir()
SETTINGS_FILE = os.path.join(CACHE_DIR, "settings.json")

# base edge-tts voice (no RVC) — เสียงเดียวที่มีตั้งแต่ต้น ไม่ต้องลงเพิ่ม
BASE_VOICE_ID = "premwadee"
BASE_VOICE_LABEL = "🎙️ Premwadee (เสียงไทยหลัก)"
BASE_VOICE_TTS = "th-TH-PremwadeeNeural"


def get_base_dir() -> str:
    """หา base directory — รองรับ PyInstaller bundle"""
    if getattr(os.sys, "frozen", False):
        if hasattr(os.sys, "_MEIPASS"):
            return os.sys._MEIPASS
        return os.path.dirname(os.sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resolve_voice_path(rel: str) -> str:
    """แปลง relative path (เทียบกับ app) → absolute path"""
    if not rel:
        return ""
    if os.path.isabs(rel):
        return rel
    return os.path.join(get_base_dir(), rel)


def resolve_character_default_image(user_image: str) -> str:
    """คืน path ภาพตัวละคร default ที่จะใช้จริง

    ถ้าผู้ใช้ตั้ง character_default_image เอง → ใช้ของผู้ใช้
    ไม่งั้น → fallback ไป avatar.png ที่ bundle มากับแอป
    คืน absolute path (อาจไม่มีอยู่จริง ถ้าไม่มีไฟล์ — caller ต้องเช็คอีกที)
    """
    if user_image and os.path.exists(user_image):
        return user_image
    return os.path.join(get_base_dir(), "avatar.png")


# ---------------------------------------------------------------------- #
# Overlay animations — ตัวเลือกอนิเมชั่นสำหรับ OBS browser source overlay
# key = ชื่อใน settings.overlay_animation, value = คำอธิบายสำหรับแสดงใน UI
# ---------------------------------------------------------------------- #
OVERLAY_ANIMATIONS = {
    # พื้นฐาน
    "minimal": "Minimal (ไม่มีอนิเมชั่น)",
    "fade": "Fade (ค่อยๆ โผล่)",
    "slide_left": "Slide Left (เลื่อนจากขวา)",
    "slide_up": "Slide Up (เลื่อนจากล่าง)",
    "zoom": "Zoom (ซูมเข้าจากไกล)",
    # สนุก
    "bounce": "Bounce (เด้งเข้า)",
    "pop": "Pop (ขยายจากเล็ก)",
    "flip": "Flip (หมุนเข้า)",
    "glow": "Glow (โผล่พร้อมแสง)",
    "typewriter": "Typewriter (พิมพ์ทีละตัว)",
    # ทันสมัย (ใหม่)
    "slide_pop": "Slide + Pop (เลื่อน+เด้ง) ✨",
    "card_flip": "Card Flip (ไพ่พลิก 3D) ✨",
    "liquid": "Liquid (คลื่นน้ำไหล) ✨",
    "neon_pulse": "Neon Pulse (นีออนเต้น) ✨",
    "glassy": "Glassy (กระจกเคลื่อน) ✨",
    "elastic": "Elastic (ยืดหยุ่น) ✨",
}

# อนิเมชั่นตอนข้อความหาย (auto-hide / cap)
OVERLAY_EXIT_ANIMATIONS = {
    "fade_out": "Fade Out (ค่อยๆ จาง)",
    "slide_right": "Slide Right (เลื่อนออก)",
    "slide_down": "Slide Down (ตกลง)",
    "shrink": "Shrink (หดหาย)",
    "blur_out": "Blur Out (เบลอหาย)",
    "dissolve": "Dissolve (สลาย)",
}

# Google Fonts ภาษาไทยที่คัดสรร (โหลด dynamic ใน overlay HTML)
GOOGLE_FONTS = {
    "Kanit": "Kanit",
    "Prompt": "Prompt",
    "Sarabun": "Sarabun",
    "Mitr": "Mitr",
    "Bai Jamjuree": "Bai Jamjuree",
    "Noto Sans Thai": "Noto Sans Thai",
    "IBM Plex Sans Thai": "IBM Plex Sans Thai",
    "Plus Jakarta Sans": "Plus Jakarta Sans",
}


# ---------------------------------------------------------------------- #
# RVC voice discovery — scan โฟลเดอร์เสียงแทน bundle แบบตายตัว
# ผู้ใช้ยัดไฟล์ .pth ในโฟลเดอร์ → auto-detect → แสดงใน dropdown
# ---------------------------------------------------------------------- #
def get_voices_dirs() -> list[str]:
    """โฟลเดอร์ที่จะ scan หาไฟล์เสียง RVC (.pth)

    - rvc_models/ ข้างโปรแกรม (รวมใน bundle หรือยัดเอง)
    - ~/.tts-for-livestream/voices/ (user folder — แยกจากโปรแกรม)
    ลำดับสำคัญ: โฟลเดอร์แรกที่เจอชื่อไฟล์ซ้ำจะชนะ
    """
    return [
        os.path.join(get_base_dir(), "rvc_models"),
        os.path.join(CACHE_DIR, "voices"),
    ]


def discover_voices() -> list[tuple]:
    """สแกนโฟลเดอร์เสียง → คืน list of (id, label, pth_path, index_path)

    - id = ชื่อไฟล์ไม่มีนามสกุล (เช่น 'haruka')
    - label = ชื่อไฟล์ Title Case (เช่น 'Haruka'); ถ้าซ้ำ → append id
    - pth_path = absolute path ของ .pth
    - index_path = .index ชื่อเดียวกันถ้ามี ไม่มี = ""

    ข้าม .pth ที่ชื่อซ้ำ (โฟลเดอร์แรกที่เจอชนะ)
    """
    voices = []
    seen_ids = set()
    seen_labels = set()
    for vdir in get_voices_dirs():
        if not os.path.isdir(vdir):
            continue
        for pth in sorted(glob.glob(os.path.join(vdir, "*.pth"))):
            stem = os.path.splitext(os.path.basename(pth))[0]
            voice_id = stem.lower()  # normalize id เป็น lowercase (กัน Haruka/haruka ชน)
            if voice_id in seen_ids:
                continue  # โฟลเดอร์แรกชนะ
            seen_ids.add(voice_id)
            label = stem.replace("_", " ").replace("-", " ").title()
            # ถ้า label ซ้ำ → append id ในวงเล็บเพื่อไม่ให้สับสน
            if label in seen_labels:
                label = f"{label} ({voice_id})"
            seen_labels.add(label)
            index = os.path.join(vdir, stem + ".index")
            index_path = index if os.path.exists(index) else ""
            voices.append((voice_id, label, pth, index_path))
    return voices


# ---------------------------------------------------------------------- #
# Settings dataclass
# ---------------------------------------------------------------------- #
@dataclass
class AppSettings:
    """settings ทั้งหมด"""

    # ---- chat source ----
    platform: str = "twitch"  # "twitch" | "youtube" | "mylive" | "tiktok"
    twitch_channel: str = ""
    youtube_url: str = ""
    mylive_url: str = ""  # เลข stream MyLive เช่น "162006" หรือ URL /streams/...
    tiktok_username: str = ""  # @username TikTok LIVE (ไม่ต้องมี @)
    kick_channel: str = ""  # KICK slug (username) เช่น "trainwreckstv"
    auto_connect: bool = False  # เชื่อมต่ออัตโนมัติตอนเปิดโปรแกรม
    # ★ auto-connect per platform
    auto_connect_twitch: bool = False
    auto_connect_youtube: bool = False
    auto_connect_mylive: bool = False
    auto_connect_tiktok: bool = False
    auto_connect_kick: bool = False
    # แพลตฟอร์มที่จะแสดงใน sidebar (เปิด/ปิดได้ — ซ่อนเว็บที่ไม่ใช้ออกไป)
    show_twitch: bool = True
    show_youtube: bool = True
    show_mylive: bool = True
    show_tiktok: bool = False
    show_kick: bool = False
    # TTS toggle per platform (อ่าน TTS เฉพาะแพลตฟอร์มที่เปิด)
    read_tts_twitch: bool = True
    read_tts_youtube: bool = True
    read_tts_mylive: bool = True
    read_tts_tiktok: bool = True
    read_tts_kick: bool = True
    # สถานะหุบ/ขยายของส่วน platform cards ใน sidebar (default ขยาย)
    platforms_collapsed: bool = False
    # วอลุ่ม TTS แยกต่อแพลตฟอร์ม (override ค่า volume หลัก — None = ใช้ค่า volume หลัก)
    tts_volume_twitch: int = 0    # % offset (-50 ถึง +50)
    tts_volume_youtube: int = 0
    tts_volume_mylive: int = 0
    tts_volume_tiktok: int = 0
    tts_volume_kick: int = 0

    # ---- reading ----
    voice_id: str = BASE_VOICE_ID  # "premwadee" หรือ rvc model id
    # ★ TTS engine choice — "edge" (edge-tts, online) | "omnivoice" (offline, zero-shot, RTX only)
    #   default = "omnivoice" สำหรับ Full build (มี torch); Lite build จะ fallback เป็น "edge" อัตโนมัติ
    tts_engine: str = "omnivoice"
    # ★ OmniVoice voice design — "male" | "female" | "child" | "auto"
    omnivoice_voice: str = "female"
    # ★ edge-tts voice — "premwadee" (หญิง) | "niwat" (ชาย)
    edge_voice: str = "premwadee"
    # ★ OmniVoice short word policy — คำเดี่ยวสั้นกว่า min_length → ไม่อ่าน (default)
    #   แต่ถ้าอยู่ใน whitelist → อ่าน (ยกเว้น)
    #   0 = ปิด (อ่านทุกคำ)
    omnivoice_skip_enabled: bool = True  # ★ default ON — คนไม่ชอบไปกดปิดเอง
    omnivoice_skip_min_length: int = 3
    # ★ whitelist คำเดียวที่สั้นแต่อ่านได้ (เช่น "ได้" "มี" "ไป" "กิน")
    omnivoice_short_whitelist: list[str] = field(default_factory=lambda: ["ได้", "มี", "ไป", "กิน", "ดี", "ใช่"])
    read_author: bool = True
    read_message: bool = True
    rate: int = 0  # %
    volume: int = 100  # master volume 0-100 (ใช้ player.set_volume — รองรับทุก engine)
    rvc_f0method: str = "rmvpe"  # "rmvpe" | "crepe" | "harvest" | "pm"
    rvc_pitch: int = 0  # semitones (-12 ถึง +12) — เลื่อนระดับเสียง RVC

    # ---- ปิด/เปิด TTS (mute) ----
    tts_muted: bool = False  # ปิดการอ่านออกเสียงชั่วคราว (แชทยังแสดง)

    # ---- ข้ามข้อความยาวเกินไป + เสียงเตือน ----
    skip_long_enabled: bool = False       # ★ ปิด (เดิม True)
    skip_long_threshold: int = 9999       # ★ ไม่จำกัด (เดิม 200)
    warn_sound_path: str = ""             # ไฟล์เสียงเตือน (user upload, .mp3/.wav)
    warn_sound_volume: float = 0.6        # 0-1

    # ---- หลายภาษา (ตรวจจับภาษา → เลือก edge-tts voice) ----
    # เมื่อเปิด → ข้อความอังกฤษ/ญี่ปุ่น/เกาหลีใช้ edge-tts voice ของภาษานั้น
    # (RVC ยังทับทับเสมอถ้าเปิดอยู่)
    multilang_enabled: bool = True  # default on — อ่านข้อความหลากภาษาด้วยเสียงภาษานั้น
    mixed_voice_enabled: bool = True  # Mixed Voice เป็น default ของ multilang
    # ภาษาที่รองรับในโหมดอ่านหลายภาษา (ถ้าข้อความมีภาษาอื่นนอกเหนือจากนี้ → เงียบ)
    multilang_langs: list = field(default_factory=lambda: ["en", "ja", "ko", "zh", "zh-TW", "fr"])

    # ---- auto-reconnect (เชื่อมต่อใหม่อัตโนมัติเมื่อหลุด) ----
    auto_reconnect_enabled: bool = True
    auto_reconnect_interval: float = 10.0  # วินาทีระหว่างการพยายามใหม่

    # ---- auto-speed (เร่งข้อความยาวอัตโนมัติ) ----
    auto_speed: bool = True        # เปิด/ปิด
    auto_speed_length: int = 80    # ถ้า len(text) > นี้ → เร่ง
    auto_speed_boost: int = 30     # เพิ่ม rate +% ตอนเร่ง

    # ---- viewer interaction commands (chat prefix [x2]/[p1]/[v50]) ----
    viewer_cmd_enabled: bool = False  # ปิดไว้ก่อน — streamer เปิดเอง
    viewer_cmd_cooldown: float = 5.0  # cooldown ต่อ user (วินาที)

    # ---- queue throttle ----
    max_queue: int = 20
    dedupe_window: float = 0.0  # ★ ปิด (เดิม 8.0)
    author_cooldown: float = 0.0

    # ---- spam protection ----
    # 4a — rate limit ต่อ user (sliding window + temp-ban)
    user_rate_limit: int = 999       # ★ ปิด (เดิม 5)
    user_rate_window: float = 10.0   # วินาที
    user_ban_duration: float = 0.0   # ★ ปิด (เดิม 30s)
    # 4b — ข้ามข้อความซ้ำจากคนต่างคน (raid/copy-paste)
    cross_dedupe_threshold: int = 999    # ★ ปิด (เดิม 3)
    cross_dedupe_window: float = 0.0     # ★ ปิด (เดิม 15.0)
    # 4c — กรองลิงก์/โค้ด/ยาวผิดปกติ
    filter_urls: bool = True
    filter_code_blocks: bool = True
    max_msg_length: int = 500  # ★ default จำกัด 500 ตัวอักษร (0 = ไม่จำกัด)
    # 4d — auto-throttle ตอน chat ระเบิด
    global_rate_threshold: int = 99999  # ★ ปิด (เดิม 100)
    throttle_keep_percent: int = 100    # ★ เก็บ 100% (เดิม 50)

    # ---- appearance ----
    appearance: str = "dark"  # "dark" | "light" | "system"
    show_timestamp: bool = False  # แสดงเวลา [HH:MM:SS] ในแชท
    chat_font_scale: int = 1  # ขนาดฟอนต์ Live Chat/Popout: step 1-5 (เพิ่มทีละ 8pt ต่อ step)
    chat_animated_emotes: bool = False  # แสดง emote ขยับ (animated) ใน Live Chat/Popout
    show_system_messages: bool = True  # แสดงสถานะเชื่อมต่อ (✅/⚪/⚠️) ใน Live Chat
    # ---- Live Chat appearance (เฟืองใน chat panel header) ----
    chat_show_platform_icon: bool = True       # แสดงไอคอนแพลตฟอร์มหน้าชื่อ
    chat_author_color_mode: str = "platform"   # "platform" (สีตามแพลตฟอร์ม) | "random" (สีสุ่มคงที่ต่อคน)
    chat_show_timestamp: bool = False          # แสดง timestamp ด้านหลังชื่อผู้โพส
    chat_emote_size: int = 28                  # ขนาด emote ใน Live Chat (px)
    chat_font_family: str = "Kanit"            # Google Font สำหรับ Live Chat/Popout
    chat_zebra_stripes: bool = False           # สีพื้นหลังสลับ (zebra) สำหรับแยกข้อความ

    # ---- overlay (OBS browser source — เว็บที่ OBS render ทับบนสตรีม) ----
    overlay_enabled: bool = False
    overlay_port: int = 8765  # localhost HTTP/WS port
    # ── OBS WebSocket (auto-refresh browser source ตอนเปิดโปรแกรม) ──
    obs_ws_enabled: bool = False
    obs_ws_host: str = "localhost"
    obs_ws_port: int = 4455
    obs_ws_password: str = ""
    overlay_animation: str = "fade"  # หนึ่งใน OVERLAY_ANIMATIONS (เข้า)
    overlay_exit_animation: str = "fade_out"  # หนึ่งใน OVERLAY_EXIT_ANIMATIONS (ออก)
    overlay_font_size: int = 18   # px (12-48)
    overlay_emote_size: int = 28  # px (16-64)
    overlay_max_messages: int = 20  # เก็ง่าสุดกี่ข้อความ
    overlay_direction: str = "bottom"  # "bottom" (ใหม่ล่าง) | "top" (ใหม่บน)
    # ข้อ 1,3 — เนื้อหา
    overlay_show_logo: bool = True   # แสดงโลโก้แพลตฟอร์มหน้า author
    overlay_show_timestamp: bool = False  # แสดงเวลา HH:MM
    # ข้อ 4 — auto-hide
    overlay_auto_hide: bool = False  # ซ่อนข้อความอัตโนมัติหลังเวลาที่กำหนด
    overlay_hide_after: float = 10.0  # วินาที ก่อนซ่อน
    # ข้อ 5,6 — ฟอนต์ + effects
    overlay_font_family: str = "Kanit"   # Google Font (หนึ่งใน GOOGLE_FONTS)
    overlay_font_weight: str = "500"     # น้ำหนักฟอนต์
    overlay_text_color: str = "#ffffff"
    overlay_text_stroke: bool = False    # stroke รอบตัวอักษร
    overlay_text_stroke_color: str = "#000000"
    overlay_text_stroke_width: int = 2
    overlay_text_shadow: bool = True     # เงาตัวอักษร (ช่วยให้อ่านได้บนวิดีโอ)
    overlay_text_shadow_color: str = "#000000"
    overlay_text_shadow_blur: int = 3
    # layout: "inline" (ชื่อ: ข้อความ บรรทัดเดียว) | "stacked" (ชื่อบน / ข้อความล่าง)
    overlay_layout: str = "inline"
    # ข้อ 7 — กล่องข้อความ
    overlay_box_enabled: bool = False        # default = ไม่มีกล่อง (แค่ตัวอักษร + เงา)
    overlay_box_bg_color: str = "#0a0e1a"
    overlay_box_bg_opacity: float = 0.55   # 0-1 (0 = โปร่งใส)
    overlay_box_radius: int = 8            # ขอบมน px
    overlay_box_border: bool = False       # เส้นขอบ
    overlay_box_border_color: str = "#7c3aed"
    overlay_box_border_width: int = 1
    overlay_box_shadow: bool = True        # drop-shadow ของกล่อง
    overlay_box_blur: float = 0            # backdrop-filter blur เป็น px (0 = ปิด, 1-20 = เบลอ)
    overlay_box_glow: bool = False         # อนิเมชั่นกรอบเรืองรอบ
    overlay_box_glow_color: str = "#7c3aed"
    overlay_box_width: str = "fit"         # "fit" (ชิดข้อความ) | "wide" (กว้างหน่อย)
    overlay_msg_spacing: float = 4.0       # ช่องว่างระหว่างข้อความ (px)
    # โหมดพิเศษ
    overlay_msg_only: bool = False         # แสดงแค่ข้อความ (ซ่อนชื่อ+โลโก้)
    overlay_balloon_mode: bool = False     # โหมดบอลลูน (chat balloon สุ่มตำแหน่ง)
    overlay_balloon_hide_after: float = 5.0  # วินาทีที่บอลลูนโผล่แล้วหาย (แยกจาก auto_hide ทั่วไป)
    overlay_balloon_bg_opacity: float = 0.95  # opacity บอลลูน (แยกจาก Default mode)
    overlay_animated_emotes: bool = True  # แสดง emote ขยับ (animated) ใน OBS overlay
    # ── OBS Overlay 3-mode restructure (เหมือน Game Overlay) ──
    # appearance mode: "default" | "theme" | "special"
    overlay_appearance_mode: str = "default"
    # theme: neon | glass | cute | minimal | custom (ใช้ game_overlay_themes.py)
    overlay_theme: str = "default"
    overlay_custom_css: str = ""  # CSS ของผู้ใช้ (เมื่อ theme == "custom")
    # mode configs — เก็บค่าแยกของแต่ละ appearance mode (persist ถาวร)
    # ★ 4 modes: default, theme, special (balloon), character (Character Talk)
    # แต่ละ mode มี text styling ของตัวเอง (font/stroke/shadow/color) ไม่แชร์กัน
    overlay_mode_configs: dict = field(default_factory=lambda: {
        "default": {
            "font_family": "Kanit", "font_weight": "500", "font_size": 18,
            "emote_size": 28, "text_color": "#ffffff",
            "text_stroke": False, "text_stroke_color": "#000000", "text_stroke_width": 2,
            "text_shadow": True, "text_shadow_color": "#000000", "text_shadow_blur": 3,
        },
        "theme": {
            "font_family": "Kanit", "font_weight": "500", "font_size": 18,
            "emote_size": 28, "text_color": "#ffffff",
            "text_stroke": False, "text_stroke_color": "#000000", "text_stroke_width": 2,
            "text_shadow": True, "text_shadow_color": "#000000", "text_shadow_blur": 3,
        },
        "special": {  # Balloon
            "font_family": "Kanit", "font_weight": "600", "font_size": 18,
            "emote_size": 28, "text_color": "#1a1a2e",
            "text_stroke": False, "text_stroke_color": "#000000", "text_stroke_width": 0,
            "text_shadow": False, "text_shadow_color": "#000000", "text_shadow_blur": 0,
        },
        "character": {  # Character Talk bubble text
            "font_family": "Kanit", "font_weight": "600", "font_size": 18,
            "emote_size": 28, "text_color": "#1a1a2e",
            "text_stroke": False, "text_stroke_color": "#000000", "text_stroke_width": 0,
            "text_shadow": False, "text_shadow_color": "#000000", "text_shadow_blur": 0,
        },
    })
    # event colors — สี author สำหรับ event พิเศษ (sub/bits/donate/system)
    overlay_color_sub: str = "#22c55e"
    overlay_color_bits: str = "#f59e0b"
    overlay_color_donate: str = "#22c55e"
    overlay_color_system: str = "#9ca3af"
    # Translator (overlay) — แสดงต้นฉบับ [xxx] ในวงเล็บ ถ้าเปิด auto-translate
    overlay_show_original: bool = True
    # Channel Points redemption (overlay) — แสดง reward redemption ใน OBS overlay
    overlay_show_redeem: bool = True

    # ---- Game Overlay (Qt+QtWebEngine transparent overlay — เหมือน OBS) ----
    game_overlay_enabled: bool = False
    # "เลือกใช้" Game Overlay (ติ๊กใน Setting) — กดปุ่มหลักจะเปิดตัวที่เลือกไว้
    game_overlay_enabled_setting: bool = True
    # Game Overlay port: 0 = auto (หาอัตโนมัติ), >0 = กำหนดเอง
    game_overlay_port: int = 0
    # ── Viewer Overlay (overlay อิสระ — แสดงยอดคนดูบนจอ) ──
    viewer_overlay_enabled: bool = False
    # "เลือกใช้" Viewer Overlay (ติ๊กใน Setting)
    viewer_overlay_enabled_setting: bool = True
    # mode: "off" = ปิด | "total" = ยอดรวม | "per_platform" = แยกตาม platform
    viewer_overlay_mode: str = "off"
    # alignment: left | center | right
    viewer_overlay_align: str = "center"
    # position: top-left | top-right | bottom-left | bottom-right
    viewer_overlay_position: str = "top-right"
    viewer_overlay_port: int = 0       # 0 = auto (8790-8800)
    viewer_overlay_x: int = -1          # geometry (saved ตอน drag)
    viewer_overlay_y: int = -1
    viewer_overlay_width: int = 400
    viewer_overlay_height: int = 80
    viewer_overlay_alpha: float = 1.0   # content opacity (1.0 = solid)
    # ปรับขนาด/สี (ข้อ 4)
    viewer_overlay_icon_size: int = 24     # ขนาด platform icon (px)
    viewer_overlay_font_size: int = 18     # ขนาดตัวเลข
    viewer_overlay_font_color: str = "#ffffff"
    viewer_overlay_text_stroke: bool = True
    viewer_overlay_text_stroke_color: str = "#000000"
    viewer_overlay_text_stroke_width: int = 2
    viewer_overlay_text_shadow: bool = True
    viewer_overlay_text_shadow_color: str = "#000000"
    viewer_overlay_text_shadow_blur: int = 3
    # appearance mode: "default" | "theme" | "special"
    game_overlay_appearance_mode: str = "default"
    # theme: neon | glass | cute | minimal | custom
    game_overlay_theme: str = "neon"
    game_overlay_custom_css: str = ""  # CSS ของผู้ใช้ (เมื่อ theme == "custom")
    game_overlay_demo_interval: float = 5.0  # วินาที (3-10) สำหรับ Loop Demo
    # mode configs — เก็บค่าแยกของแต่ละ appearance mode (persist ถาวร)
    game_overlay_mode_configs: dict = field(default_factory=lambda: {
        "default": {
            "font_family": "Kanit", "font_weight": "500", "font_size": 32,
            "emote_size": 24, "text_color": "#ffffff",
            "text_stroke": False, "text_stroke_color": "#000000", "text_stroke_width": 2,
            "text_shadow": True, "text_shadow_color": "#000000", "text_shadow_blur": 3,
            "layout": "stacked", "anim_in": "fade", "anim_out": "fade_out",
            "auto_hide": True, "hide_after": 8.0,
            "box_enabled": True, "box_bg_color": "#0a0e1a", "box_bg_opacity": 0.55,
            "box_radius": 8, "box_border": False, "box_border_color": "#7c3aed",
            "box_border_width": 1, "box_shadow": True, "box_blur": False,
            "box_glow": False, "box_glow_color": "#7c3aed",
            "show_logo": True, "show_timestamp": False,
            "max_rows": 15, "max_msg_length": 0, "msg_spacing": 4.0, "alpha": 0.85,
        },
        "theme": {
            "theme": "neon", "custom_css": "",
            "box_bg_opacity": 0.55,
        },
        "special": {
            "balloon_mode": True, "balloon_hide_after": 5.0,
            "font_family": "Kanit", "font_weight": "500", "font_size": 32,
            "emote_size": 24, "text_color": "#ffffff",
            "text_stroke": False, "text_stroke_width": 0,
            "text_shadow": False, "text_shadow_blur": 0,
            "balloon_bg_opacity": 0.95,
            "layout": "stacked", "anim_in": "bounce", "anim_out": "fade_out",
            "auto_hide": True, "hide_after": 5.0,
            "show_logo": False, "show_timestamp": False,
        },
        "character": {
            "font_family": "Kanit", "font_weight": "500", "font_size": 32,
            "emote_size": 24, "text_color": "#ffffff",
            "text_stroke": False, "text_stroke_width": 0,
            "text_shadow": True, "text_shadow_color": "#000000", "text_shadow_blur": 3,
        },
    })
    # position + size
    game_overlay_x: int = -1
    game_overlay_y: int = -1
    game_overlay_width: int = 360
    game_overlay_height: int = 500
    game_overlay_alpha: float = 0.85
    # content
    game_overlay_max_rows: int = 15
    game_overlay_show_logo: bool = True
    game_overlay_show_timestamp: bool = False
    game_overlay_direction: str = "bottom"
    game_overlay_layout: str = "stacked"  # stacked (2 บรรทัด) | inline (1 บรรทัด) | message_only ...
    game_overlay_max_msg_length: int = 0  # 0 = ไม่จำกัด
    game_overlay_scrollbar: str = "none"  # "left" | "right" | "none"
    game_overlay_msg_spacing: float = 4.0
    # font
    game_overlay_font_family: str = "Kanit"
    game_overlay_font_weight: str = "500"
    game_overlay_font_size: int = 32
    game_overlay_emote_size: int = 24  # px — ขนาด emote ใน overlay
    game_overlay_text_color: str = "#ffffff"
    # สี author สำหรับ event พิเศษ (แยกจากข้อความปกติ)
    game_overlay_color_sub: str = "#22c55e"        # Subscription / Resub
    game_overlay_color_bits: str = "#f59e0b"       # Bits (Twitch)
    game_overlay_color_donate: str = "#22c55e"     # Donate / Super Chat / Gift
    game_overlay_color_system: str = "#9ca3af"     # สถานะเชื่อมต่อ (ติด/หลุด)
    # Translator (game overlay) — แสดงต้นฉบับ [xxx] ในวงเล็บ ถ้าเปิด auto-translate
    game_overlay_show_original: bool = True
    # Channel Points redemption (game overlay) — แสดง reward redemption
    game_overlay_show_redeem: bool = True
    game_overlay_text_stroke: bool = False
    game_overlay_text_stroke_color: str = "#000000"
    game_overlay_text_stroke_width: int = 2
    game_overlay_text_shadow: bool = True
    game_overlay_text_shadow_color: str = "#000000"
    game_overlay_text_shadow_blur: int = 3
    # animation (CSS — 16 entry + 6 exit แบบ)
    game_overlay_anim_in: str = "fade"
    game_overlay_anim_out: str = "fade_out"
    game_overlay_auto_hide: bool = True
    game_overlay_hide_after: float = 8.0
    # box (กล่องข้อความ — CSS รองรับครบ)
    game_overlay_box_enabled: bool = True
    game_overlay_box_bg_color: str = "#0a0e1a"
    game_overlay_box_bg_opacity: float = 0.55
    game_overlay_box_radius: int = 8
    game_overlay_box_border: bool = False
    game_overlay_box_border_color: str = "#7c3aed"
    game_overlay_box_border_width: int = 1
    game_overlay_box_shadow: bool = True
    game_overlay_box_blur: float = 0       # backdrop-filter blur เป็น px (0 = ปิด, 1-20 = เบลอ)
    game_overlay_box_glow: bool = False
    game_overlay_box_glow_color: str = "#7c3aed"
    game_overlay_box_width: str = "fit"
    # balloon mode (chat ลอยกระจายสุ่ม)
    game_overlay_balloon_mode: bool = False
    game_overlay_balloon_hide_after: float = 5.0
    game_overlay_balloon_bg_opacity: float = 0.95  # opacity บอลลูน (แยกจาก Default mode)
    # ── Character Talk overlay ──
    overlay_character_mode: bool = False       # OBS overlay
    game_overlay_character_mode: bool = False   # Game overlay
    character_hide_after: float = 6.0           # วินาทีที่บอลลูน+ตัวละครโผล่แล้วหาย
    character_size: int = 120                    # ขนาดตัวละคร (px)
    character_max_on_screen: int = 8             # จำนวนตัวละครสูงสุดที่แสดงพร้อมกัน
    character_name_size: int = 11                # ขนาดชื่อตัวละคร (px)
    character_name_stroke: bool = True
    character_name_stroke_color: str = "#000000"
    character_name_stroke_width: int = 1
    character_name_shadow: bool = True
    character_name_shadow_color: str = "#000000"
    character_name_shadow_blur: int = 2
    character_random_pos: bool = True            # สุ่มตำแหน่งแนวนอน (ไม่เรียงตรงกลาง)
    character_bubble_width: int = 500            # ความกว้าง balloon (400/500/600/700/800)
    game_overlay_animated_emotes: bool = False  # แสดง emote ขยับ (animated) ใน Game Overlay
    game_overlay_show_system: bool = False  # แสดงสถานะเชื่อมต่อ (✅/⚪/⚠️) ใน Game Overlay
    # hotkeys
    game_overlay_hotkey: str = "ctrl+shift+g"  # เปิด/ปิด overlay
    game_overlay_hotkey_edit: str = "ctrl+shift+h"  # edit mode (ย้าย/resize)

    # ---- Overlay+ (custom URL overlays — สูงสุด 3 อัน ลอยเหนือเกม) ----
    # แต่ละ item: {url, x, y, w, h, alpha, enabled}
    more_overlays: list = field(default_factory=list)
    more_overlay_hotkey: str = "ctrl+shift+m"        # toggle show/hide ทุกอัน
    more_overlay_hotkey_edit: str = "ctrl+shift+n"   # edit mode (drag/resize) ทุกอัน

    # ---- Canvas Overlay Composer (1 URL รวมทุก widget ใส่ OBS) ----
    # widget ใน list: {id, type, x, y, w, h, z, url?, alpha, enabled}
    #   type: "chat" | "alert" | "viewer" | "clock"
    #   x/y/w/h: ตำแหน่ง + ขนาด (px ใน canvas)
    #   z: layer order (สูง = ด้านหน้า)
    #   url: URL ภายนอก (สำหรับ alert)
    #   alpha: ความโปร่งใส (0.0-1.0)
    composer_enabled: bool = False
    composer_port: int = 8801              # port ใหม่ (หลีกเลี่ยงช่วง 8765-8800)
    composer_canvas_size: str = "1080p"    # "720p" | "1080p"
    composer_widgets: list = field(default_factory=list)

    # ---- Playroom overlay (มินิเกมวิดีโอ — multi-trigger) ----
    playroom_enabled: bool = False
    playroom_port: int = 8766              # port แยกจาก chat overlay (8765)
    # triggers: list of {code, daily_limit, widget_ids, clips: [{name, path, weight}]}
    # แต่ละ trigger = collection ของวิดีโอเป็นของตัวเอง + daily limit แยก
    # widget_ids: [] = ทุก widget (backward compat), ถ้าระบุ = เฉพาะ widget เหล่านั้น
    playroom_triggers: list = field(default_factory=lambda: [
        {
            "code": "#fortune",
            "daily_limit": 3,
            "widget_ids": [],
            "clips": [
                {"name": "good", "path": "playroom/media/good.mp4", "weight": 30},
                {"name": "normal", "path": "playroom/media/normal.mp4", "weight": 50},
                {"name": "bad", "path": "playroom/media/bad.mp4", "weight": 20},
            ],
        },
    ])

    # ---- filter (เก็บฝั่งเอง ไม่ใช่ TextFilter object เพื่อ JSON-friendly) ----
    blocked_users: list[str] = field(default_factory=list)
    banned_words: list[str] = field(default_factory=lambda: ["ควย"])
    # per-word mode: {word_lower: "hide" | "show_no_tts"}
    # hide = ไม่แสดงทั้งข้อความ + ไม่อ่าน + ไม่ขึ้น overlay
    # show_no_tts = แสดงในแชท + ไม่อ่าน TTS + ไม่ขึ้น overlay
    banned_word_modes: dict = field(default_factory=dict)
    replace_words: dict[str, dict] = field(default_factory=lambda: {"55@": {"display": "", "read": "ฮ่าๆ"}})
    secret_codes: list[dict] = field(default_factory=list)  # [{code, sound_path, volume}]
    secret_code_daily_limit: int = 0  # จำกัดการเล่นเสียงโค้ดลับต่อ user/วัน (0 = ไม่จำกัด)
    code_sound_muted: bool = False  # ปิดเสียงโค้ดลับทั้งหมดชั่วคราว (ไม่เล่น + ไม่ติดคิว)
    # ── OBS WebSocket auto-refresh ──
    # ★ refresh browser source อัตโนมัติตอนเปิดโปรแกรม
    #   แก้ปัญหา: เปิด OBS ก่อน Broadcast Playroom → browser source cache หน้าเก่า → overlay ไม่แสดง
    obs_ws_enabled: bool = False
    obs_ws_host: str = "localhost"
    obs_ws_port: int = 4455              # OBS WebSocket v5 default port
    obs_ws_password: str = ""
    # ── Auto Translate ──
    auto_translate_enabled: bool = False
    auto_translate_provider: str = "google"  # "google" | "deepl" | "deepseek"
    auto_translate_api_key: str = ""
    auto_translate_host: str = ""  # DeepL/DeepSeek host (ว่าง = default)
    auto_translate_target_lang: str = "th"
    auto_translate_langs: list = field(default_factory=lambda: ["en", "ja", "ko", "zh", "vi", "id"])
    # rename: original_lower → new_name (TTS+GUI ใช้ใหม่, overlay ใช้เดิม)
    user_renames: dict[str, str] = field(default_factory=dict)
    tts_renames: dict[str, str] = field(default_factory=dict)  # author_lower → ชื่อที่ TTS อ่าน
    # Character Talk — author_lower → job name (เก็บถาวร)
    user_jobs: dict[str, str] = field(default_factory=dict)
    # Character Talk — job config: [{name, image}]
    # name = job identifier (match กับ {jobchange:name}), image = absolute path
    # NOTE: "default" job ไม่จำเป็นต้องมี — ผู้ชมที่ยังไม่ได้ set job จะใช้ character_default_image อัตโนมัติ
    character_jobs: list = field(default_factory=list)
    character_default_image: str = ""  # ภาพตัวละคร default (ผู้ชมที่ยังไม่ได้ set job)
    # force_translate_users: list of usernames that should ALWAYS be translated (skip history check)
    # ใช้สำหรับต่างชาติที่ก๊อปข้อความไทยมาโพส → บังคับแปลทุกข้อความ
    force_translate_users: list = field(default_factory=list)
    # message history (viewer profile modal)
    message_history_enabled: bool = True
    message_history_retention: str = "all"  # "all" | "today"

    # ---- events panel (ฝั่งขวาของแชท) ----
    # จำสถานะหุบ/ขยายของแผง Events ใน main window (default ขยาย)
    events_panel_collapsed: bool = False
    # event types ที่แสดงในแผง (เก็บทุก event เสมอ แต่กรองตอนแสดง)
    events_shown: list = field(default_factory=lambda: [
        "bits", "superchat", "gift", "sub", "resub", "subgift", "raid",
    ])
    # จำสถานะหุบ/ขยายของ Events section ใน popout window (default หุบ)
    events_popout_collapsed: bool = True
    # จำนวน event สูงสุดที่เก็บ (cap กันพองไฟล์)
    events_log_max: int = 2000

    # ---- notification (per-platform: {platform: {notif_key: {sound_path, volume}}}) ----
    # notif_key ของแต่ละ platform ดู PLATFORM_NOTIF_EVENTS ใน notification_manager.py
    # เก็บ legacy "notification" (flat) ไว้ด้วย เพื่อ migrate จากเวอร์ชันเก่า
    notifications: dict = field(default_factory=dict)
    notification: dict = field(default_factory=dict)  # legacy flat (สำหรับ backward compat)

    def to_dict(self) -> dict:
        return {
            "platform": self.platform,
            "twitch_channel": self.twitch_channel,
            "youtube_url": self.youtube_url,
            "mylive_url": self.mylive_url,
            "tiktok_username": self.tiktok_username,
            "kick_channel": self.kick_channel,
            "auto_connect": self.auto_connect,
            "auto_connect_twitch": self.auto_connect_twitch,
            "auto_connect_youtube": self.auto_connect_youtube,
            "auto_connect_mylive": self.auto_connect_mylive,
            "auto_connect_tiktok": self.auto_connect_tiktok,
            "auto_connect_kick": self.auto_connect_kick,
            "show_twitch": self.show_twitch,
            "show_youtube": self.show_youtube,
            "show_mylive": self.show_mylive,
            "show_tiktok": self.show_tiktok,
            "show_kick": self.show_kick,
            "read_tts_twitch": self.read_tts_twitch,
            "read_tts_youtube": self.read_tts_youtube,
            "read_tts_mylive": self.read_tts_mylive,
            "read_tts_tiktok": self.read_tts_tiktok,
            "read_tts_kick": self.read_tts_kick,
            "platforms_collapsed": self.platforms_collapsed,
            "tts_volume_twitch": self.tts_volume_twitch,
            "tts_volume_youtube": self.tts_volume_youtube,
            "tts_volume_mylive": self.tts_volume_mylive,
            "tts_volume_tiktok": self.tts_volume_tiktok,
            "tts_volume_kick": self.tts_volume_kick,
            "voice_id": self.voice_id,
            "tts_engine": self.tts_engine,
            "omnivoice_voice": self.omnivoice_voice,
            "edge_voice": self.edge_voice,
            "omnivoice_skip_enabled": bool(self.omnivoice_skip_enabled),
            "omnivoice_skip_min_length": int(self.omnivoice_skip_min_length),
            "omnivoice_short_whitelist": list(self.omnivoice_short_whitelist),
            "read_author": self.read_author,
            "read_message": self.read_message,
            "rate": self.rate,
            "volume": self.volume,
            "rvc_f0method": self.rvc_f0method,
            "rvc_pitch": self.rvc_pitch,
            "tts_muted": self.tts_muted,
            "skip_long_enabled": self.skip_long_enabled,
            "skip_long_threshold": self.skip_long_threshold,
            "warn_sound_path": self.warn_sound_path,
            "warn_sound_volume": self.warn_sound_volume,
            "multilang_enabled": self.multilang_enabled,
            "mixed_voice_enabled": self.mixed_voice_enabled,
            "multilang_langs": list(self.multilang_langs),
            "auto_reconnect_enabled": self.auto_reconnect_enabled,
            "auto_reconnect_interval": self.auto_reconnect_interval,
            "auto_speed": self.auto_speed,
            "auto_speed_length": self.auto_speed_length,
            "auto_speed_boost": self.auto_speed_boost,
            "viewer_cmd_enabled": self.viewer_cmd_enabled,
            "viewer_cmd_cooldown": self.viewer_cmd_cooldown,
            "max_queue": self.max_queue,
            "dedupe_window": self.dedupe_window,
            "author_cooldown": self.author_cooldown,
            "user_rate_limit": self.user_rate_limit,
            "user_rate_window": self.user_rate_window,
            "user_ban_duration": self.user_ban_duration,
            "cross_dedupe_threshold": self.cross_dedupe_threshold,
            "cross_dedupe_window": self.cross_dedupe_window,
            "filter_urls": self.filter_urls,
            "filter_code_blocks": self.filter_code_blocks,
            "max_msg_length": self.max_msg_length,
            "global_rate_threshold": self.global_rate_threshold,
            "throttle_keep_percent": self.throttle_keep_percent,
            "appearance": self.appearance,
            "show_timestamp": self.show_timestamp,
            "chat_font_scale": self.chat_font_scale,
            "chat_animated_emotes": self.chat_animated_emotes,
            "show_system_messages": self.show_system_messages,
            "chat_show_platform_icon": self.chat_show_platform_icon,
            "chat_author_color_mode": self.chat_author_color_mode,
            "chat_show_timestamp": self.chat_show_timestamp,
            "chat_emote_size": self.chat_emote_size,
            "chat_font_family": self.chat_font_family,
            "chat_zebra_stripes": self.chat_zebra_stripes,
            "overlay_enabled": self.overlay_enabled,
            "overlay_port": self.overlay_port,
            "obs_ws_enabled": self.obs_ws_enabled,
            "obs_ws_host": self.obs_ws_host,
            "obs_ws_port": self.obs_ws_port,
            "obs_ws_password": self.obs_ws_password,
            "overlay_animation": self.overlay_animation,
            "overlay_exit_animation": self.overlay_exit_animation,
            "overlay_font_size": self.overlay_font_size,
            "overlay_emote_size": self.overlay_emote_size,
            "overlay_max_messages": self.overlay_max_messages,
            "overlay_direction": self.overlay_direction,
            "overlay_show_logo": self.overlay_show_logo,
            "overlay_show_timestamp": self.overlay_show_timestamp,
            "overlay_auto_hide": self.overlay_auto_hide,
            "overlay_hide_after": self.overlay_hide_after,
            "overlay_font_family": self.overlay_font_family,
            "overlay_font_weight": self.overlay_font_weight,
            "overlay_text_color": self.overlay_text_color,
            "overlay_text_stroke": self.overlay_text_stroke,
            "overlay_text_stroke_color": self.overlay_text_stroke_color,
            "overlay_text_stroke_width": self.overlay_text_stroke_width,
            "overlay_text_shadow": self.overlay_text_shadow,
            "overlay_text_shadow_color": self.overlay_text_shadow_color,
            "overlay_text_shadow_blur": self.overlay_text_shadow_blur,
            "overlay_layout": self.overlay_layout,
            "overlay_box_enabled": self.overlay_box_enabled,
            "overlay_box_bg_color": self.overlay_box_bg_color,
            "overlay_box_bg_opacity": self.overlay_box_bg_opacity,
            "overlay_box_radius": self.overlay_box_radius,
            "overlay_box_border": self.overlay_box_border,
            "overlay_box_border_color": self.overlay_box_border_color,
            "overlay_box_border_width": self.overlay_box_border_width,
            "overlay_box_shadow": self.overlay_box_shadow,
            "overlay_box_blur": self.overlay_box_blur,
            "overlay_box_glow": self.overlay_box_glow,
            "overlay_box_glow_color": self.overlay_box_glow_color,
            "overlay_box_width": self.overlay_box_width,
            "overlay_msg_spacing": self.overlay_msg_spacing,
            "overlay_msg_only": self.overlay_msg_only,
            "overlay_balloon_mode": self.overlay_balloon_mode,
            "overlay_balloon_hide_after": self.overlay_balloon_hide_after,
            "overlay_balloon_bg_opacity": self.overlay_balloon_bg_opacity,
            "overlay_animated_emotes": self.overlay_animated_emotes,
            "overlay_appearance_mode": self.overlay_appearance_mode,
            "overlay_theme": self.overlay_theme,
            "overlay_custom_css": self.overlay_custom_css,
            "overlay_mode_configs": dict(self.overlay_mode_configs),
            "overlay_color_sub": self.overlay_color_sub,
            "overlay_color_bits": self.overlay_color_bits,
            "overlay_color_donate": self.overlay_color_donate,
            "overlay_color_system": self.overlay_color_system,
            "overlay_show_original": self.overlay_show_original,
            "overlay_show_redeem": self.overlay_show_redeem,
            "game_overlay_enabled": self.game_overlay_enabled,
            "game_overlay_enabled_setting": self.game_overlay_enabled_setting,
            "viewer_overlay_enabled": self.viewer_overlay_enabled,
            "viewer_overlay_enabled_setting": self.viewer_overlay_enabled_setting,
            "viewer_overlay_mode": self.viewer_overlay_mode,
            "viewer_overlay_align": self.viewer_overlay_align,
            "viewer_overlay_position": self.viewer_overlay_position,
            "viewer_overlay_port": self.viewer_overlay_port,
            "viewer_overlay_x": self.viewer_overlay_x,
            "viewer_overlay_y": self.viewer_overlay_y,
            "viewer_overlay_width": self.viewer_overlay_width,
            "viewer_overlay_height": self.viewer_overlay_height,
            "viewer_overlay_alpha": self.viewer_overlay_alpha,
            "viewer_overlay_icon_size": self.viewer_overlay_icon_size,
            "viewer_overlay_font_size": self.viewer_overlay_font_size,
            "viewer_overlay_font_color": self.viewer_overlay_font_color,
            "viewer_overlay_text_stroke": self.viewer_overlay_text_stroke,
            "viewer_overlay_text_stroke_color": self.viewer_overlay_text_stroke_color,
            "viewer_overlay_text_stroke_width": self.viewer_overlay_text_stroke_width,
            "viewer_overlay_text_shadow": self.viewer_overlay_text_shadow,
            "viewer_overlay_text_shadow_color": self.viewer_overlay_text_shadow_color,
            "viewer_overlay_text_shadow_blur": self.viewer_overlay_text_shadow_blur,
            "game_overlay_port": self.game_overlay_port,
            "game_overlay_theme": self.game_overlay_theme,
            "game_overlay_custom_css": self.game_overlay_custom_css,
            "game_overlay_demo_interval": self.game_overlay_demo_interval,
            "game_overlay_appearance_mode": self.game_overlay_appearance_mode,
            "game_overlay_mode_configs": dict(self.game_overlay_mode_configs),
            "game_overlay_x": self.game_overlay_x,
            "game_overlay_y": self.game_overlay_y,
            "game_overlay_width": self.game_overlay_width,
            "game_overlay_height": self.game_overlay_height,
            "game_overlay_alpha": self.game_overlay_alpha,
            "game_overlay_max_rows": self.game_overlay_max_rows,
            "game_overlay_show_logo": self.game_overlay_show_logo,
            "game_overlay_show_timestamp": self.game_overlay_show_timestamp,
            "game_overlay_direction": self.game_overlay_direction,
            "game_overlay_layout": self.game_overlay_layout,
            "game_overlay_max_msg_length": self.game_overlay_max_msg_length,
            "game_overlay_scrollbar": self.game_overlay_scrollbar,
            "game_overlay_msg_spacing": self.game_overlay_msg_spacing,
            "game_overlay_font_family": self.game_overlay_font_family,
            "game_overlay_font_weight": self.game_overlay_font_weight,
            "game_overlay_font_size": self.game_overlay_font_size,
            "game_overlay_emote_size": self.game_overlay_emote_size,
            "game_overlay_text_color": self.game_overlay_text_color,
            "game_overlay_color_sub": self.game_overlay_color_sub,
            "game_overlay_color_bits": self.game_overlay_color_bits,
            "game_overlay_color_donate": self.game_overlay_color_donate,
            "game_overlay_color_system": self.game_overlay_color_system,
            "game_overlay_show_original": self.game_overlay_show_original,
            "game_overlay_show_redeem": self.game_overlay_show_redeem,
            "game_overlay_text_stroke": self.game_overlay_text_stroke,
            "game_overlay_text_stroke_color": self.game_overlay_text_stroke_color,
            "game_overlay_text_stroke_width": self.game_overlay_text_stroke_width,
            "game_overlay_text_shadow": self.game_overlay_text_shadow,
            "game_overlay_text_shadow_color": self.game_overlay_text_shadow_color,
            "game_overlay_text_shadow_blur": self.game_overlay_text_shadow_blur,
            "game_overlay_anim_in": self.game_overlay_anim_in,
            "game_overlay_anim_out": self.game_overlay_anim_out,
            "game_overlay_auto_hide": self.game_overlay_auto_hide,
            "game_overlay_hide_after": self.game_overlay_hide_after,
            "game_overlay_box_enabled": self.game_overlay_box_enabled,
            "game_overlay_box_bg_color": self.game_overlay_box_bg_color,
            "game_overlay_box_bg_opacity": self.game_overlay_box_bg_opacity,
            "game_overlay_box_radius": self.game_overlay_box_radius,
            "game_overlay_box_border": self.game_overlay_box_border,
            "game_overlay_box_border_color": self.game_overlay_box_border_color,
            "game_overlay_box_border_width": self.game_overlay_box_border_width,
            "game_overlay_box_shadow": self.game_overlay_box_shadow,
            "game_overlay_box_blur": self.game_overlay_box_blur,
            "game_overlay_box_glow": self.game_overlay_box_glow,
            "game_overlay_box_glow_color": self.game_overlay_box_glow_color,
            "game_overlay_box_width": self.game_overlay_box_width,
            "game_overlay_balloon_mode": self.game_overlay_balloon_mode,
            "game_overlay_balloon_hide_after": self.game_overlay_balloon_hide_after,
            "game_overlay_balloon_bg_opacity": self.game_overlay_balloon_bg_opacity,
            "game_overlay_animated_emotes": self.game_overlay_animated_emotes,
            "game_overlay_show_system": self.game_overlay_show_system,
            "game_overlay_hotkey": self.game_overlay_hotkey,
            "game_overlay_hotkey_edit": self.game_overlay_hotkey_edit,
            "more_overlays": list(self.more_overlays),
            "more_overlay_hotkey": self.more_overlay_hotkey,
            "more_overlay_hotkey_edit": self.more_overlay_hotkey_edit,
            "composer_enabled": self.composer_enabled,
            "composer_port": self.composer_port,
            "composer_canvas_size": self.composer_canvas_size,
            "composer_widgets": list(self.composer_widgets),
            "playroom_enabled": self.playroom_enabled,
            "playroom_port": self.playroom_port,
            "playroom_triggers": list(self.playroom_triggers),
            # ── OBS WebSocket auto-refresh ──
            "obs_ws_enabled": self.obs_ws_enabled,
            "obs_ws_host": self.obs_ws_host,
            "obs_ws_port": self.obs_ws_port,
            "obs_ws_password": self.obs_ws_password,
            "blocked_users": list(self.blocked_users),
            "banned_words": list(self.banned_words),
            "banned_word_modes": dict(self.banned_word_modes),
            "replace_words": dict(self.replace_words),
            "secret_codes": list(self.secret_codes),
            "secret_code_daily_limit": self.secret_code_daily_limit,
            "code_sound_muted": self.code_sound_muted,
            "auto_translate_enabled": self.auto_translate_enabled,
            "auto_translate_provider": self.auto_translate_provider,
            "auto_translate_api_key": self.auto_translate_api_key,
            "auto_translate_host": self.auto_translate_host,
            "auto_translate_target_lang": self.auto_translate_target_lang,
            "auto_translate_langs": list(self.auto_translate_langs),
            "user_renames": dict(self.user_renames),
            "tts_renames": dict(self.tts_renames),
            "user_jobs": dict(self.user_jobs),
            "character_jobs": list(self.character_jobs),
            "character_default_image": self.character_default_image,
            "overlay_character_mode": self.overlay_character_mode,
            "game_overlay_character_mode": self.game_overlay_character_mode,
            "character_hide_after": self.character_hide_after,
            "character_size": self.character_size,
            "character_max_on_screen": self.character_max_on_screen,
            "character_name_size": self.character_name_size,
            "character_name_stroke": self.character_name_stroke,
            "character_name_stroke_color": self.character_name_stroke_color,
            "character_name_stroke_width": self.character_name_stroke_width,
            "character_name_shadow": self.character_name_shadow,
            "character_name_shadow_color": self.character_name_shadow_color,
            "character_name_shadow_blur": self.character_name_shadow_blur,
            "character_random_pos": self.character_random_pos,
            "character_bubble_width": self.character_bubble_width,
            "force_translate_users": list(self.force_translate_users),
            "message_history_enabled": self.message_history_enabled,
            "message_history_retention": self.message_history_retention,
            "events_panel_collapsed": self.events_panel_collapsed,
            "events_shown": list(self.events_shown),
            "events_popout_collapsed": self.events_popout_collapsed,
            "events_log_max": self.events_log_max,
            "notifications": dict(self.notifications),
            "notification": dict(self.notification),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AppSettings":
        """สร้างจาก dict — ยืดหยุ่นกับ missing keys (เก่า→ใหม่)"""
        s = cls()
        if not isinstance(data, dict):
            return s
        if "platform" in data:
            s.platform = data["platform"]
        if "twitch_channel" in data:
            s.twitch_channel = data["twitch_channel"]
        if "youtube_url" in data:
            s.youtube_url = data["youtube_url"]
        if "mylive_url" in data:
            s.mylive_url = data["mylive_url"]
        if "tiktok_username" in data:
            s.tiktok_username = str(data["tiktok_username"])
        if "kick_channel" in data:
            s.kick_channel = str(data["kick_channel"])
        if "auto_connect" in data:
            s.auto_connect = bool(data["auto_connect"])
        for plat in ("twitch", "youtube", "mylive", "tiktok", "kick"):
            key = f"auto_connect_{plat}"
            if key in data:
                setattr(s, key, bool(data[key]))
        if "show_twitch" in data:
            s.show_twitch = bool(data["show_twitch"])
        if "show_youtube" in data:
            s.show_youtube = bool(data["show_youtube"])
        if "show_mylive" in data:
            s.show_mylive = bool(data["show_mylive"])
        if "show_tiktok" in data:
            s.show_tiktok = bool(data["show_tiktok"])
        if "show_kick" in data:
            s.show_kick = bool(data["show_kick"])
        if "read_tts_twitch" in data:
            s.read_tts_twitch = bool(data["read_tts_twitch"])
        if "read_tts_youtube" in data:
            s.read_tts_youtube = bool(data["read_tts_youtube"])
        if "read_tts_mylive" in data:
            s.read_tts_mylive = bool(data["read_tts_mylive"])
        if "read_tts_tiktok" in data:
            s.read_tts_tiktok = bool(data["read_tts_tiktok"])
        if "read_tts_kick" in data:
            s.read_tts_kick = bool(data["read_tts_kick"])
        if "platforms_collapsed" in data:
            s.platforms_collapsed = bool(data["platforms_collapsed"])
        for vol_field in ("tts_volume_twitch", "tts_volume_youtube",
                           "tts_volume_mylive", "tts_volume_tiktok", "tts_volume_kick"):
            if vol_field in data:
                setattr(s, vol_field, int(data[vol_field]))
        if "voice_id" in data:
            s.voice_id = data["voice_id"]
        if "tts_engine" in data:
            s.tts_engine = str(data["tts_engine"])
        # ★ Lite build fallback ถูกจัดการที่ runtime (ไม่ใช่ settings load time)
        #   เพราะ PyInstaller frozen exe อาจยังไม่พร้อม import torch ตอน load_settings
        if "omnivoice_voice" in data:
            # ★ migration: "auto" ถูกลบออกแล้ว → default เป็น "female"
            ov = str(data["omnivoice_voice"])
            s.omnivoice_voice = ov if ov in ("female", "male", "child") else "female"
        if "edge_voice" in data:
            s.edge_voice = str(data["edge_voice"])
        if "omnivoice_skip_enabled" in data:
            try:
                s.omnivoice_skip_enabled = bool(data["omnivoice_skip_enabled"])
            except Exception:
                s.omnivoice_skip_enabled = True
        if "omnivoice_skip_min_length" in data:
            try:
                s.omnivoice_skip_min_length = int(data["omnivoice_skip_min_length"])
            except Exception:
                s.omnivoice_skip_min_length = 3
        if "omnivoice_short_whitelist" in data:
            try:
                s.omnivoice_short_whitelist = [str(w).strip() for w in list(data["omnivoice_short_whitelist"]) if str(w).strip()]
            except Exception:
                s.omnivoice_short_whitelist = ["ได้", "มี", "ไป", "กิน", "ดี", "ใช่"]
        elif "omnivoice_skip_words" in data:
            # ★ migration: เดิมเป็น skip_words (blacklist) → ตอนนี้เป็น whitelist
            #   ใช้ default whitelist แทน เพราะ blacklist เดิมไม่แปลงได้ตรงๆ
            pass
        if "read_author" in data:
            s.read_author = bool(data["read_author"])
        if "read_message" in data:
            s.read_message = bool(data["read_message"])
        if "rate" in data:
            s.rate = int(data["rate"])
        if "volume" in data:
            v = int(data["volume"])
            # ★ migration: volume เดิมเป็น -50..+50 offset (default 0)
            #   ตอนนี้เป็น master volume 0-100 (default 100) — ค่าเก่า 0 = เบาสุด
            #   แปลง: ถ้า <= 0 ให้ใช้ default 100
            s.volume = v if 0 < v <= 100 else 100
        if "rvc_f0method" in data:
            s.rvc_f0method = data["rvc_f0method"]
        if "rvc_pitch" in data:
            s.rvc_pitch = int(data["rvc_pitch"])
        if "tts_muted" in data:
            s.tts_muted = bool(data["tts_muted"])
        if "skip_long_enabled" in data:
            # ★ migrate: เดิม True → ปิด
            s.skip_long_enabled = False if bool(data["skip_long_enabled"]) else bool(data["skip_long_enabled"])
        if "skip_long_threshold" in data:
            s.skip_long_threshold = 9999 if int(data["skip_long_threshold"]) == 200 else int(data["skip_long_threshold"])
        if "warn_sound_path" in data:
            s.warn_sound_path = str(data["warn_sound_path"])
        if "warn_sound_volume" in data:
            s.warn_sound_volume = float(data["warn_sound_volume"])
        if "multilang_enabled" in data:
            s.multilang_enabled = bool(data["multilang_enabled"])
        if "mixed_voice_enabled" in data:
            s.mixed_voice_enabled = bool(data["mixed_voice_enabled"])
        if "multilang_langs" in data:
            s.multilang_langs = list(data["multilang_langs"])
        if "auto_reconnect_enabled" in data:
            s.auto_reconnect_enabled = bool(data["auto_reconnect_enabled"])
        if "auto_reconnect_interval" in data:
            s.auto_reconnect_interval = float(data["auto_reconnect_interval"])
        if "auto_speed" in data:
            s.auto_speed = bool(data["auto_speed"])
        if "auto_speed_length" in data:
            s.auto_speed_length = int(data["auto_speed_length"])
        if "auto_speed_boost" in data:
            s.auto_speed_boost = int(data["auto_speed_boost"])
        if "viewer_cmd_enabled" in data:
            s.viewer_cmd_enabled = bool(data["viewer_cmd_enabled"])
        if "viewer_cmd_cooldown" in data:
            try:
                s.viewer_cmd_cooldown = float(data["viewer_cmd_cooldown"])
            except (TypeError, ValueError):
                s.viewer_cmd_cooldown = 5.0
        if "max_queue" in data:
            s.max_queue = int(data["max_queue"])
        if "dedupe_window" in data:
            s.dedupe_window = 0.0 if float(data["dedupe_window"]) == 8.0 else float(data["dedupe_window"])
        if "author_cooldown" in data:
            # ★ migrate: เดิม default 3.0 → ถ้า user ยังเป็น 3.0 ให้เปลี่ยนเป็น 0 (ปิด cooldown)
            old_val = float(data["author_cooldown"])
            s.author_cooldown = 0.0 if old_val == 3.0 else old_val
        if "user_rate_limit" in data:
            # ★ migrate: เดิม default 5 → ถ้า user ยังเป็น 5 ให้เปลี่ยนเป็น 999 (ปิด)
            old_val = int(data["user_rate_limit"])
            s.user_rate_limit = 999 if old_val == 5 else old_val
        if "user_rate_window" in data:
            s.user_rate_window = float(data["user_rate_window"])
        if "user_ban_duration" in data:
            # ★ migrate: เดิม default 30 → ถ้า user ยังเป็น 30 ให้เปลี่ยนเป็น 0 (ปิด)
            old_val = float(data["user_ban_duration"])
            s.user_ban_duration = 0.0 if old_val == 30.0 else old_val
        if "cross_dedupe_threshold" in data:
            s.cross_dedupe_threshold = 999 if int(data["cross_dedupe_threshold"]) == 3 else int(data["cross_dedupe_threshold"])
        if "cross_dedupe_window" in data:
            s.cross_dedupe_window = 0.0 if float(data["cross_dedupe_window"]) == 15.0 else float(data["cross_dedupe_window"])
        if "filter_urls" in data:
            s.filter_urls = bool(data["filter_urls"])
        if "filter_code_blocks" in data:
            s.filter_code_blocks = bool(data["filter_code_blocks"])
        if "max_msg_length" in data:
            s.max_msg_length = int(data["max_msg_length"])
        if "global_rate_threshold" in data:
            s.global_rate_threshold = 99999 if int(data["global_rate_threshold"]) == 100 else int(data["global_rate_threshold"])
        if "throttle_keep_percent" in data:
            s.throttle_keep_percent = 100 if int(data["throttle_keep_percent"]) == 50 else int(data["throttle_keep_percent"])
        if "appearance" in data:
            s.appearance = data["appearance"]
        if "show_timestamp" in data:
            s.show_timestamp = bool(data["show_timestamp"])
        if "chat_font_scale" in data:
            try:
                s.chat_font_scale = max(1, min(5, int(data["chat_font_scale"])))
            except (ValueError, TypeError):
                s.chat_font_scale = 1
        if "chat_animated_emotes" in data:
            s.chat_animated_emotes = bool(data["chat_animated_emotes"])
        if "show_system_messages" in data:
            s.show_system_messages = bool(data["show_system_messages"])
        if "chat_show_platform_icon" in data:
            s.chat_show_platform_icon = bool(data["chat_show_platform_icon"])
        if "chat_author_color_mode" in data:
            s.chat_author_color_mode = str(data["chat_author_color_mode"])
        if "chat_show_timestamp" in data:
            s.chat_show_timestamp = bool(data["chat_show_timestamp"])
        if "chat_emote_size" in data:
            try:
                s.chat_emote_size = int(data["chat_emote_size"])
            except (ValueError, TypeError):
                s.chat_emote_size = 28
        if "chat_font_family" in data:
            s.chat_font_family = str(data["chat_font_family"])
        if "chat_zebra_stripes" in data:
            s.chat_zebra_stripes = bool(data["chat_zebra_stripes"])
        # overlay
        if "overlay_enabled" in data:
            s.overlay_enabled = bool(data["overlay_enabled"])
        if "overlay_port" in data:
            s.overlay_port = int(data["overlay_port"])
        if "obs_ws_enabled" in data:
            s.obs_ws_enabled = bool(data["obs_ws_enabled"])
        if "obs_ws_host" in data:
            s.obs_ws_host = str(data["obs_ws_host"])
        if "obs_ws_port" in data:
            s.obs_ws_port = int(data["obs_ws_port"])
        if "obs_ws_password" in data:
            s.obs_ws_password = str(data["obs_ws_password"])
        if "overlay_animation" in data:
            s.overlay_animation = str(data["overlay_animation"])
        if "overlay_font_size" in data:
            s.overlay_font_size = int(data["overlay_font_size"])
        if "overlay_emote_size" in data:
            s.overlay_emote_size = int(data["overlay_emote_size"])
        if "overlay_max_messages" in data:
            s.overlay_max_messages = int(data["overlay_max_messages"])
        if "overlay_direction" in data:
            s.overlay_direction = str(data["overlay_direction"])
        if "overlay_show_logo" in data:
            s.overlay_show_logo = bool(data["overlay_show_logo"])
        if "overlay_show_timestamp" in data:
            s.overlay_show_timestamp = bool(data["overlay_show_timestamp"])
        if "overlay_auto_hide" in data:
            s.overlay_auto_hide = bool(data["overlay_auto_hide"])
        if "overlay_hide_after" in data:
            s.overlay_hide_after = float(data["overlay_hide_after"])
        if "overlay_exit_animation" in data:
            s.overlay_exit_animation = str(data["overlay_exit_animation"])
        if "overlay_font_family" in data:
            s.overlay_font_family = str(data["overlay_font_family"])
        if "overlay_font_weight" in data:
            s.overlay_font_weight = str(data["overlay_font_weight"])
        if "overlay_text_color" in data:
            s.overlay_text_color = str(data["overlay_text_color"])
        if "overlay_text_stroke" in data:
            s.overlay_text_stroke = bool(data["overlay_text_stroke"])
        if "overlay_text_stroke_color" in data:
            s.overlay_text_stroke_color = str(data["overlay_text_stroke_color"])
        if "overlay_text_stroke_width" in data:
            s.overlay_text_stroke_width = int(data["overlay_text_stroke_width"])
        if "overlay_text_shadow" in data:
            s.overlay_text_shadow = bool(data["overlay_text_shadow"])
        if "overlay_text_shadow_color" in data:
            s.overlay_text_shadow_color = str(data["overlay_text_shadow_color"])
        if "overlay_text_shadow_blur" in data:
            s.overlay_text_shadow_blur = int(data["overlay_text_shadow_blur"])
        if "overlay_layout" in data:
            s.overlay_layout = str(data["overlay_layout"])
        if "overlay_box_enabled" in data:
            s.overlay_box_enabled = bool(data["overlay_box_enabled"])
        if "overlay_box_bg_color" in data:
            s.overlay_box_bg_color = str(data["overlay_box_bg_color"])
        if "overlay_box_bg_opacity" in data:
            s.overlay_box_bg_opacity = float(data["overlay_box_bg_opacity"])
        if "overlay_box_radius" in data:
            s.overlay_box_radius = int(data["overlay_box_radius"])
        if "overlay_box_border" in data:
            s.overlay_box_border = bool(data["overlay_box_border"])
        if "overlay_box_border_color" in data:
            s.overlay_box_border_color = str(data["overlay_box_border_color"])
        if "overlay_box_border_width" in data:
            s.overlay_box_border_width = int(data["overlay_box_border_width"])
        if "overlay_box_shadow" in data:
            s.overlay_box_shadow = bool(data["overlay_box_shadow"])
        if "overlay_box_blur" in data:
            # migrate: เดิมเป็น bool (True=6px) → เปลี่ยนเป็น float
            v = data["overlay_box_blur"]
            s.overlay_box_blur = 6.0 if v is True else (0.0 if v is False else float(v))
        if "overlay_box_glow" in data:
            s.overlay_box_glow = bool(data["overlay_box_glow"])
        if "overlay_box_glow_color" in data:
            s.overlay_box_glow_color = str(data["overlay_box_glow_color"])
        if "overlay_box_width" in data:
            s.overlay_box_width = str(data["overlay_box_width"])
        if "overlay_msg_spacing" in data:
            s.overlay_msg_spacing = float(data["overlay_msg_spacing"])
        if "overlay_msg_only" in data:
            s.overlay_msg_only = bool(data["overlay_msg_only"])
        if "overlay_balloon_mode" in data:
            s.overlay_balloon_mode = bool(data["overlay_balloon_mode"])
        if "overlay_balloon_hide_after" in data:
            s.overlay_balloon_hide_after = float(data["overlay_balloon_hide_after"])
        if "overlay_balloon_bg_opacity" in data:
            s.overlay_balloon_bg_opacity = float(data["overlay_balloon_bg_opacity"])
        if "overlay_animated_emotes" in data:
            s.overlay_animated_emotes = bool(data["overlay_animated_emotes"])
        if "overlay_appearance_mode" in data:
            s.overlay_appearance_mode = str(data["overlay_appearance_mode"])
        if "overlay_theme" in data:
            s.overlay_theme = str(data["overlay_theme"])
        if "overlay_custom_css" in data:
            s.overlay_custom_css = str(data["overlay_custom_css"])
        if "overlay_mode_configs" in data and isinstance(data["overlay_mode_configs"], dict):
            s.overlay_mode_configs = data["overlay_mode_configs"]
        if "overlay_color_sub" in data:
            s.overlay_color_sub = str(data["overlay_color_sub"])
        if "overlay_color_bits" in data:
            s.overlay_color_bits = str(data["overlay_color_bits"])
        if "overlay_color_donate" in data:
            s.overlay_color_donate = str(data["overlay_color_donate"])
        if "overlay_color_system" in data:
            s.overlay_color_system = str(data["overlay_color_system"])
        if "overlay_show_original" in data:
            s.overlay_show_original = bool(data["overlay_show_original"])
        if "overlay_show_redeem" in data:
            s.overlay_show_redeem = bool(data["overlay_show_redeem"])
        if "game_overlay_enabled" in data:
            s.game_overlay_enabled = bool(data["game_overlay_enabled"])
        if "game_overlay_enabled_setting" in data:
            s.game_overlay_enabled_setting = bool(data["game_overlay_enabled_setting"])
        if "viewer_overlay_enabled" in data:
            s.viewer_overlay_enabled = bool(data["viewer_overlay_enabled"])
        if "viewer_overlay_enabled_setting" in data:
            s.viewer_overlay_enabled_setting = bool(data["viewer_overlay_enabled_setting"])
        if "viewer_overlay_mode" in data:
            s.viewer_overlay_mode = str(data["viewer_overlay_mode"])
        if "viewer_overlay_align" in data:
            s.viewer_overlay_align = str(data["viewer_overlay_align"])
        if "viewer_overlay_position" in data:
            s.viewer_overlay_position = str(data["viewer_overlay_position"])
        if "viewer_overlay_port" in data:
            s.viewer_overlay_port = int(data["viewer_overlay_port"])
        if "viewer_overlay_x" in data:
            s.viewer_overlay_x = int(data["viewer_overlay_x"])
        if "viewer_overlay_y" in data:
            s.viewer_overlay_y = int(data["viewer_overlay_y"])
        if "viewer_overlay_width" in data:
            s.viewer_overlay_width = int(data["viewer_overlay_width"])
        if "viewer_overlay_height" in data:
            s.viewer_overlay_height = int(data["viewer_overlay_height"])
        if "viewer_overlay_alpha" in data:
            try:
                s.viewer_overlay_alpha = float(data["viewer_overlay_alpha"])
            except (TypeError, ValueError):
                s.viewer_overlay_alpha = 1.0
        if "viewer_overlay_icon_size" in data:
            s.viewer_overlay_icon_size = int(data["viewer_overlay_icon_size"])
        if "viewer_overlay_font_size" in data:
            s.viewer_overlay_font_size = int(data["viewer_overlay_font_size"])
        if "viewer_overlay_font_color" in data:
            s.viewer_overlay_font_color = str(data["viewer_overlay_font_color"])
        if "viewer_overlay_text_stroke" in data:
            s.viewer_overlay_text_stroke = bool(data["viewer_overlay_text_stroke"])
        if "viewer_overlay_text_stroke_color" in data:
            s.viewer_overlay_text_stroke_color = str(data["viewer_overlay_text_stroke_color"])
        if "viewer_overlay_text_stroke_width" in data:
            s.viewer_overlay_text_stroke_width = int(data["viewer_overlay_text_stroke_width"])
        if "viewer_overlay_text_shadow" in data:
            s.viewer_overlay_text_shadow = bool(data["viewer_overlay_text_shadow"])
        if "viewer_overlay_text_shadow_color" in data:
            s.viewer_overlay_text_shadow_color = str(data["viewer_overlay_text_shadow_color"])
        if "viewer_overlay_text_shadow_blur" in data:
            s.viewer_overlay_text_shadow_blur = int(data["viewer_overlay_text_shadow_blur"])
        if "game_overlay_port" in data:
            s.game_overlay_port = int(data["game_overlay_port"])
        if "game_overlay_x" in data:
            s.game_overlay_x = int(data["game_overlay_x"])
        if "game_overlay_y" in data:
            s.game_overlay_y = int(data["game_overlay_y"])
        if "game_overlay_width" in data:
            s.game_overlay_width = int(data["game_overlay_width"])
        if "game_overlay_height" in data:
            s.game_overlay_height = int(data["game_overlay_height"])
        if "game_overlay_max_rows" in data:
            s.game_overlay_max_rows = int(data["game_overlay_max_rows"])
        if "game_overlay_font_size" in data:
            s.game_overlay_font_size = int(data["game_overlay_font_size"])
        if "game_overlay_emote_size" in data:
            s.game_overlay_emote_size = int(data["game_overlay_emote_size"])
        if "game_overlay_box_radius" in data:
            s.game_overlay_box_radius = int(data["game_overlay_box_radius"])
        if "game_overlay_box_border_width" in data:
            s.game_overlay_box_border_width = int(data["game_overlay_box_border_width"])
        if "game_overlay_text_stroke_width" in data:
            s.game_overlay_text_stroke_width = int(data["game_overlay_text_stroke_width"])
        if "game_overlay_text_shadow_blur" in data:
            s.game_overlay_text_shadow_blur = int(data["game_overlay_text_shadow_blur"])
        if "game_overlay_alpha" in data:
            s.game_overlay_alpha = float(data["game_overlay_alpha"])
        if "game_overlay_msg_spacing" in data:
            s.game_overlay_msg_spacing = float(data["game_overlay_msg_spacing"])
        if "game_overlay_box_bg_opacity" in data:
            s.game_overlay_box_bg_opacity = float(data["game_overlay_box_bg_opacity"])
        if "game_overlay_hide_after" in data:
            s.game_overlay_hide_after = float(data["game_overlay_hide_after"])
        if "game_overlay_balloon_hide_after" in data:
            s.game_overlay_balloon_hide_after = float(data["game_overlay_balloon_hide_after"])
        if "game_overlay_balloon_bg_opacity" in data:
            s.game_overlay_balloon_bg_opacity = float(data["game_overlay_balloon_bg_opacity"])
        if "game_overlay_animated_emotes" in data:
            s.game_overlay_animated_emotes = bool(data["game_overlay_animated_emotes"])
        if "game_overlay_show_system" in data:
            s.game_overlay_show_system = bool(data["game_overlay_show_system"])
        if "game_overlay_direction" in data:
            s.game_overlay_direction = str(data["game_overlay_direction"])
        if "game_overlay_layout" in data:
            s.game_overlay_layout = str(data["game_overlay_layout"])
        if "game_overlay_max_msg_length" in data:
            s.game_overlay_max_msg_length = str(data["game_overlay_max_msg_length"])
        if "game_overlay_scrollbar" in data:
            s.game_overlay_scrollbar = str(data["game_overlay_scrollbar"])
        if "game_overlay_font_family" in data:
            s.game_overlay_font_family = str(data["game_overlay_font_family"])
        if "game_overlay_font_weight" in data:
            s.game_overlay_font_weight = str(data["game_overlay_font_weight"])
        if "game_overlay_text_color" in data:
            s.game_overlay_text_color = str(data["game_overlay_text_color"])
        if "game_overlay_color_sub" in data:
            s.game_overlay_color_sub = str(data["game_overlay_color_sub"])
        if "game_overlay_color_bits" in data:
            s.game_overlay_color_bits = str(data["game_overlay_color_bits"])
        if "game_overlay_color_donate" in data:
            s.game_overlay_color_donate = str(data["game_overlay_color_donate"])
        if "game_overlay_color_system" in data:
            s.game_overlay_color_system = str(data["game_overlay_color_system"])
        if "game_overlay_show_original" in data:
            s.game_overlay_show_original = bool(data["game_overlay_show_original"])
        if "game_overlay_show_redeem" in data:
            s.game_overlay_show_redeem = bool(data["game_overlay_show_redeem"])
        if "game_overlay_text_stroke_color" in data:
            s.game_overlay_text_stroke_color = str(data["game_overlay_text_stroke_color"])
        if "game_overlay_text_shadow_color" in data:
            s.game_overlay_text_shadow_color = str(data["game_overlay_text_shadow_color"])
        if "game_overlay_anim_in" in data:
            s.game_overlay_anim_in = str(data["game_overlay_anim_in"])
        if "game_overlay_anim_out" in data:
            s.game_overlay_anim_out = str(data["game_overlay_anim_out"])
        if "game_overlay_box_bg_color" in data:
            s.game_overlay_box_bg_color = str(data["game_overlay_box_bg_color"])
        if "game_overlay_box_border_color" in data:
            s.game_overlay_box_border_color = str(data["game_overlay_box_border_color"])
        if "game_overlay_box_glow_color" in data:
            s.game_overlay_box_glow_color = str(data["game_overlay_box_glow_color"])
        if "game_overlay_box_width" in data:
            s.game_overlay_box_width = str(data["game_overlay_box_width"])
        if "game_overlay_theme" in data:
            s.game_overlay_theme = str(data["game_overlay_theme"])
        if "game_overlay_custom_css" in data:
            s.game_overlay_custom_css = str(data["game_overlay_custom_css"])
        if "game_overlay_demo_interval" in data:
            s.game_overlay_demo_interval = float(data["game_overlay_demo_interval"])
        if "game_overlay_appearance_mode" in data:
            s.game_overlay_appearance_mode = str(data["game_overlay_appearance_mode"])
        if "game_overlay_mode_configs" in data:
            # merge — ถ้า key ใหม่ไม่มี → ใช้ default
            saved = data["game_overlay_mode_configs"]
            for mode_key in s.game_overlay_mode_configs:
                if mode_key in saved:
                    s.game_overlay_mode_configs[mode_key].update(saved[mode_key])
        if "game_overlay_hotkey" in data:
            s.game_overlay_hotkey = str(data["game_overlay_hotkey"])
        if "game_overlay_hotkey_edit" in data:
            s.game_overlay_hotkey_edit = str(data["game_overlay_hotkey_edit"])
        if "more_overlays" in data:
            s.more_overlays = list(data["more_overlays"])
        if "more_overlay_hotkey" in data:
            s.more_overlay_hotkey = str(data["more_overlay_hotkey"])
        if "more_overlay_hotkey_edit" in data:
            s.more_overlay_hotkey_edit = str(data["more_overlay_hotkey_edit"])
        # ── Canvas Overlay Composer ──
        if "composer_enabled" in data:
            s.composer_enabled = bool(data["composer_enabled"])
        if "composer_port" in data:
            try: s.composer_port = int(data["composer_port"])
            except Exception: s.composer_port = 8801
        if "composer_canvas_size" in data:
            v = str(data["composer_canvas_size"])
            s.composer_canvas_size = v if v in ("720p", "1080p") else "1080p"
        if "composer_widgets" in data:
            s.composer_widgets = list(data["composer_widgets"])
        if "game_overlay_show_logo" in data:
            s.game_overlay_show_logo = bool(data["game_overlay_show_logo"])
        if "game_overlay_show_timestamp" in data:
            s.game_overlay_show_timestamp = bool(data["game_overlay_show_timestamp"])
        if "game_overlay_text_stroke" in data:
            s.game_overlay_text_stroke = bool(data["game_overlay_text_stroke"])
        if "game_overlay_text_shadow" in data:
            s.game_overlay_text_shadow = bool(data["game_overlay_text_shadow"])
        if "game_overlay_auto_hide" in data:
            s.game_overlay_auto_hide = bool(data["game_overlay_auto_hide"])
        if "game_overlay_box_enabled" in data:
            s.game_overlay_box_enabled = bool(data["game_overlay_box_enabled"])
        if "game_overlay_box_border" in data:
            s.game_overlay_box_border = bool(data["game_overlay_box_border"])
        if "game_overlay_box_shadow" in data:
            s.game_overlay_box_shadow = bool(data["game_overlay_box_shadow"])
        if "game_overlay_box_blur" in data:
            # migrate: เดิมเป็น bool (True=6px) → เปลี่ยนเป็น float
            v = data["game_overlay_box_blur"]
            s.game_overlay_box_blur = 6.0 if v is True else (0.0 if v is False else float(v))
        if "game_overlay_box_glow" in data:
            s.game_overlay_box_glow = bool(data["game_overlay_box_glow"])
        if "game_overlay_balloon_mode" in data:
            s.game_overlay_balloon_mode = bool(data["game_overlay_balloon_mode"])

        if "playroom_enabled" in data:
            s.playroom_enabled = bool(data["playroom_enabled"])
        if "playroom_port" in data:
            s.playroom_port = int(data["playroom_port"])
        # backward compat: format เก่า (playroom_trigger + playroom_clips + playroom_daily_limit)
        # → แปลงเป็น playroom_triggers ใหม่
        if "playroom_triggers" in data:
            s.playroom_triggers = list(data["playroom_triggers"])
        elif "playroom_trigger" in data:
            # migrate format เก่า → ใหม่
            s.playroom_triggers = [{
                "code": str(data["playroom_trigger"]),
                "daily_limit": int(data.get("playroom_daily_limit", 3)),
                "clips": list(data.get("playroom_clips", [])),
            }]
        # ── migrate: playroom prefix เปลี่ยนจาก "!" → "#" ──
        # trigger ทุกตัวที่ขึ้นต้นด้วย "!" → แปลงเป็น "#" (เช่น !fortune → #fortune)
        for t in s.playroom_triggers:
            code = t.get("code", "")
            if code.startswith("!"):
                t["code"] = "#" + code[1:]
            # ★ migrate: เพิ่ม widget_ids ให้ entry เก่าที่ไม่มี (default = [] = ทุก widget)
            if "widget_ids" not in t:
                t["widget_ids"] = []
        # ── OBS WebSocket auto-refresh ──
        if "obs_ws_enabled" in data:
            s.obs_ws_enabled = bool(data["obs_ws_enabled"])
        if "obs_ws_host" in data:
            s.obs_ws_host = str(data["obs_ws_host"])
        if "obs_ws_port" in data:
            s.obs_ws_port = int(data["obs_ws_port"])
        if "obs_ws_password" in data:
            s.obs_ws_password = str(data["obs_ws_password"])
        if "blocked_users" in data:
            s.blocked_users = list(data["blocked_users"])
        if "banned_words" in data:
            s.banned_words = list(data["banned_words"])
        if "banned_word_modes" in data:
            s.banned_word_modes = dict(data["banned_word_modes"])
        if "replace_words" in data:
            # ★ migrate: legacy string/object → format ใหม่ {display, read}
            from text_filter import TextFilter as _TF
            s.replace_words = {
                k: _TF._normalize_entry(v) for k, v in dict(data["replace_words"]).items()
            }
        if "secret_codes" in data:
            s.secret_codes = list(data["secret_codes"])
            # ── migrate: secret_code prefix บังคับ "!" ──
            # code ที่ยังไม่มี prefix → เติม "!" (เช่น alert → !alert)
            for c in s.secret_codes:
                if isinstance(c, dict):
                    code = c.get("code", "")
                    if code and not code.startswith("!"):
                        c["code"] = "!" + code
        if "secret_code_daily_limit" in data:
            s.secret_code_daily_limit = int(data["secret_code_daily_limit"])
        if "code_sound_muted" in data:
            s.code_sound_muted = bool(data["code_sound_muted"])
        if "auto_translate_enabled" in data:
            s.auto_translate_enabled = bool(data["auto_translate_enabled"])
        if "auto_translate_provider" in data:
            s.auto_translate_provider = str(data["auto_translate_provider"])
        if "auto_translate_api_key" in data:
            s.auto_translate_api_key = str(data["auto_translate_api_key"])
        if "auto_translate_host" in data:
            s.auto_translate_host = str(data["auto_translate_host"])
        if "auto_translate_target_lang" in data:
            s.auto_translate_target_lang = str(data["auto_translate_target_lang"])
        if "auto_translate_langs" in data:
            s.auto_translate_langs = list(data["auto_translate_langs"])
        if "user_renames" in data:
            s.user_renames = dict(data["user_renames"])
        if "tts_renames" in data:
            s.tts_renames = dict(data["tts_renames"])
        if "user_jobs" in data:
            s.user_jobs = dict(data["user_jobs"])
        if "character_jobs" in data:
            # migrate: ลบ "default" job ออก — default image จัดการที่ character_default_image แล้ว
            loaded = list(data["character_jobs"])
            s.character_jobs = [
                cj for cj in loaded
                if isinstance(cj, dict) and cj.get("name", "").lower() != "default"
            ]
        if "character_default_image" in data:
            s.character_default_image = str(data["character_default_image"])
        if "overlay_character_mode" in data:
            s.overlay_character_mode = bool(data["overlay_character_mode"])
        if "game_overlay_character_mode" in data:
            s.game_overlay_character_mode = bool(data["game_overlay_character_mode"])
        if "character_hide_after" in data:
            try:
                s.character_hide_after = float(data["character_hide_after"])
            except (TypeError, ValueError):
                s.character_hide_after = 6.0
        if "character_size" in data:
            s.character_size = int(data["character_size"])
        if "character_max_on_screen" in data:
            s.character_max_on_screen = int(data["character_max_on_screen"])
        if "character_name_size" in data:
            s.character_name_size = int(data["character_name_size"])
        if "character_name_stroke" in data:
            s.character_name_stroke = bool(data["character_name_stroke"])
        if "character_name_stroke_color" in data:
            s.character_name_stroke_color = str(data["character_name_stroke_color"])
        if "character_name_stroke_width" in data:
            s.character_name_stroke_width = int(data["character_name_stroke_width"])
        if "character_name_shadow" in data:
            s.character_name_shadow = bool(data["character_name_shadow"])
        if "character_name_shadow_color" in data:
            s.character_name_shadow_color = str(data["character_name_shadow_color"])
        if "character_name_shadow_blur" in data:
            s.character_name_shadow_blur = int(data["character_name_shadow_blur"])
        if "character_random_pos" in data:
            s.character_random_pos = bool(data["character_random_pos"])
        if "character_bubble_width" in data:
            s.character_bubble_width = int(data["character_bubble_width"])
        if "force_translate_users" in data:
            s.force_translate_users = list(data["force_translate_users"])
        if "message_history_enabled" in data:
            s.message_history_enabled = bool(data["message_history_enabled"])
        if "message_history_retention" in data:
            s.message_history_retention = str(data["message_history_retention"])
        if "events_panel_collapsed" in data:
            s.events_panel_collapsed = bool(data["events_panel_collapsed"])
        if "events_shown" in data:
            shown = data["events_shown"]
            if isinstance(shown, list):
                s.events_shown = [str(x) for x in shown]
                # migration: เพิ่ม events ใหม่ที่อาจไม่มีใน settings เดิม
                _required = ["like", "follow", "share", "join", "redeem"]
                for ev in _required:
                    if ev not in s.events_shown:
                        s.events_shown.append(ev)
        if "events_popout_collapsed" in data:
            s.events_popout_collapsed = bool(data["events_popout_collapsed"])
        if "events_log_max" in data:
            s.events_log_max = int(data["events_log_max"])
        if "notifications" in data and isinstance(data["notifications"], dict):
            s.notifications = dict(data["notifications"])
        if "notification" in data:
            s.notification = dict(data["notification"])
        return s

    # ------------------------------------------------------------------ #
    # Bridge to TextFilter / NotificationConfig
    # ------------------------------------------------------------------ #
    def to_text_filter(self) -> TextFilter:
        codes = [
            SecretCode(
                code=c["code"],
                sound_path=c["sound_path"],
                volume=float(c.get("volume", 0.8)),
            )
            for c in self.secret_codes
            if c.get("code") and c.get("sound_path")
        ]
        return TextFilter(
            blocked_users=list(self.blocked_users),
            banned_words=list(self.banned_words),
            replace_words=dict(self.replace_words),
            secret_codes=codes,
        )

    def apply_text_filter(self, f: TextFilter) -> None:
        """copy state จาก TextFilter object → settings"""
        self.blocked_users = list(f.blocked_users)
        self.banned_words = list(f.banned_words)
        self.replace_words = dict(f.replace_words)
        self.secret_codes = [
            {"code": c.code, "sound_path": c.sound_path, "volume": c.volume}
            for c in f.secret_codes
        ]

    def to_notification_config(self) -> NotificationConfig:
        """สร้าง NotificationConfig จาก settings — รวม format ใหม่ (per-platform) + legacy"""
        # merge: notifications (per-platform) + legacy flat (backward compat)
        merged = {}
        # legacy flat → ย้ายไป twitch (format เก่าใช้ shared donate/sub/raid)
        legacy = self.notification or {}
        if legacy:
            for k in ("donate", "sub", "subgift", "raid"):
                if k in legacy:
                    merged.setdefault("twitch", {})[k] = legacy[k]
            for k in ("read_donate", "read_sub", "read_raid", "read_event_text", "min_interval"):
                if k in legacy:
                    merged[k] = legacy[k]
        # format ใหม่ — per-platform (override legacy ถ้าซ้ำ)
        for platform, sounds in (self.notifications or {}).items():
            merged[platform] = sounds
        return NotificationConfig.from_dict(merged)

    def apply_notification_config(self, c: NotificationConfig) -> None:
        """บันทึก NotificationConfig → settings.notifications (per-platform)"""
        self.notifications = c.to_dict()
        # sync legacy ด้วย (เพื่อ backward compat ถ้ามี code เก่าอ้าง self.notification)
        # แยก global toggles ออก
        legacy = {}
        for k in ("read_donate", "read_sub", "read_raid", "read_event_text", "min_interval"):
            legacy[k] = getattr(c, k, True) if k != "min_interval" else getattr(c, k, 5.0)
        # เสียง twitch → flat (legacy)
        twitch = c.platform_sounds.get("twitch", {})
        for key, snd in twitch.items():
            if isinstance(snd, NotificationSound):
                legacy[key] = {"sound_path": snd.sound_path, "volume": snd.volume}
            elif isinstance(snd, dict):
                legacy[key] = snd
        self.notification = legacy


# ---------------------------------------------------------------------- #
# Persistence
# ---------------------------------------------------------------------- #
def ensure_cache_dir() -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)


# default RVC voice — ถ้ามีใน rvc_models/ จะใช้เป็น default แทน Premwadee
# (Premwadee ยังเป็น fallback เสมอ ถ้าไม่มีไฟล์นี้ หรือไม่มี RVC)
DEFAULT_RVC_VOICE = "diona"


def _has_rvc_voice(voice_id: str) -> bool:
    """เช็คว่ามี .pth ของ voice นี้ใน rvc_models/ หรือ user voices หรือไม่"""
    for vdir in get_voices_dirs():
        pth = os.path.join(vdir, voice_id + ".pth")
        if os.path.exists(pth):
            return True
    return False


def load_settings() -> AppSettings:
    """อ่าน settings จาก disk — คืน default ถ้าไม่มี

    ถ้าเปิดครั้งแรก (ไม่มี settings.json) → ใช้ Diona เป็น default ถ้ามีไฟล์
    ถ้าไม่มี Diona → ใช้ Premwadee (base voice)
    """
    if not os.path.exists(SETTINGS_FILE):
        s = AppSettings()
        # default RVC voice — ถ้ามี diona ใน rvc_models/
        if _has_rvc_voice(DEFAULT_RVC_VOICE):
            s.voice_id = DEFAULT_RVC_VOICE
        return s
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        s = AppSettings.from_dict(data)
        # migrate: ถ้า voice_id เป็น premwadee (default เก่า) และมี diona → เปลี่ยนเป็น diona
        # (ทำครั้งเดียว — ครั้งต่อไป user จะเป็นคนเลือกเอง)
        if s.voice_id == BASE_VOICE_ID and _has_rvc_voice(DEFAULT_RVC_VOICE):
            if not data.get("_rvc_default_migrated"):
                s.voice_id = DEFAULT_RVC_VOICE
        # migrate: reset game_overlay_alpha เป็น 1.0 (กรอบ edit frame ต้องชัด 100% เสมอ)
        # ★ user เดิมที่ตั้ง window alpha ต่ำกว่า 1.0 → reset อัตโนมัติหลังอัพเดท
        #   (window alpha ถูกลบออกจาก UI แล้ว ใช้ alpha=1.0 คงที่ กรอบ edit ชัด)
        if not data.get("_game_overlay_alpha_reset"):
            try:
                if float(getattr(s, "game_overlay_alpha", 1.0)) < 1.0:
                    s.game_overlay_alpha = 1.0
            except Exception:
                s.game_overlay_alpha = 1.0
        # migrate v2: reset ทุก opacity เป็น 1.0 (100%) บังคับหลังอัพเดท
        # ★ user เดิมที่ปรับ opacity ไว้ → reset กลับ 100% แล้วค่อยปรับเองใหม่
        #   ครอบ: overlay_box_bg_opacity (Default), overlay_balloon_bg_opacity (Balloon),
        #          game_overlay_box_bg_opacity (Default), game_overlay_balloon_bg_opacity (Balloon)
        if not data.get("_opacity_reset_v2"):
            for _field in ("overlay_box_bg_opacity", "overlay_balloon_bg_opacity",
                           "game_overlay_box_bg_opacity", "game_overlay_balloon_bg_opacity"):
                try:
                    setattr(s, _field, 1.0)
                except Exception:
                    pass
        return s
    except (json.JSONDecodeError, OSError, TypeError):
        s = AppSettings()
        if _has_rvc_voice(DEFAULT_RVC_VOICE):
            s.voice_id = DEFAULT_RVC_VOICE
        return s


def save_settings(settings: AppSettings) -> None:
    ensure_cache_dir()
    data = settings.to_dict()
    data["_rvc_default_migrated"] = True  # กัน migrate ซ้ำ
    data["_game_overlay_alpha_reset"] = True  # กัน reset alpha ซ้ำ (migration ครั้งเดียว)
    data["_opacity_reset_v2"] = True  # กัน reset opacity ซ้ำ (migration ครั้งเดียว)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
