"""game_overlay_server.py — local HTTP + WebSocket server สำหรับ Game Overlay

Mirror ของ overlay_server.py แต่:
  - อ่าน game_overlay_* settings (ไม่ใช่ overlay_*)
  - เพิ่ม endpoint /theme → return CSS ของ theme ที่เลือก
  - เพิ่ม endpoint /custom_css → return user custom CSS

Routes:
  GET /             → game_overlay.html
  GET /config       → JSON config (game_overlay_* settings)
  GET /theme        → JSON { css: ... } (theme CSS)
  GET /custom_css   → JSON { css: ... } (user custom CSS)
  GET /logo/{plat}  → platform logo (assets/{plat}.png)
  GET /emote/{id}   → Twitch emote proxy (cached)
  WS  /ws           → WebSocket (push messages + config updates)
"""
from __future__ import annotations

import asyncio
import os
import sys
import threading
from typing import Optional

from chat_twitch import ChatMessage
from settings import get_base_dir, resolve_character_default_image
from game_overlay_themes import get_theme_css


# ────────────────────────────────────────────────────────────────────
# DEMO_POOL — 50 ข้อความตัวอย่างครอบคลุมทุก event type
# ใช้สำหรับ "Loop Demo" ใน Game Overlay Settings (preview แบบเรียลไทม์)
# ────────────────────────────────────────────────────────────────────
def _mkmsg(author, color, platform, event, text, system_text="",
           amount=None, badge="", emotes=None, segments=None):
    """helper สร้าง demo message dict"""
    return {
        "type": "message",
        "platform": platform,
        "author": author,
        "text": text,
        "system_text": system_text,
        "event": event,
        "amount": amount,
        "badge": badge,
        "color": color,
        "timestamp": "00:00",  # จะถูก override เป็นเวลาปัจจุบันตอน push
        "raw_text": text,
        "segments": segments or [],
        "twitch_emotes": emotes or [],
        "sticker_url": "",
    }


# author + color pool (ขยายจาก 20 → 40)
_AUTHORS = [
    ("สตรีมเมอร์หน้าใหม่", "#a855f7", "twitch"),
    ("ผู้ชมคนที่1", "#06b6d4", "twitch"),
    ("เพื่อนบ้านใจดี", "#10b981", "twitch"),
    ("แขกไม่ได้รับเชิญ", "#f59e0b", "twitch"),
    ("นักเล่นเกมโปร", "#ef4444", "twitch"),
    ("GamerPro_YT", "#ef4444", "youtube"),
    ("ไอ้น้อย", "#22c55e", "youtube"),
    ("ญาติมิตร", "#60a5fa", "mylive"),
    ("tokyofan", "#fe2c55", "tiktok"),
    ("คนดูที่10", "#06b6d4", "kick"),
    ("หมีน้อย", "#fbbf24", "twitch"),
    ("senpai_404", "#a855f7", "youtube"),
    ("โคตรเทพ", "#10b981", "twitch"),
    ("คุณครู", "#60a5fa", "mylive"),
    ("ป้ามาเยือน", "#f59e0b", "tiktok"),
    ("CatLover", "#ec4899", "twitch"),
    ("โอตาคุจงเจริญ", "#8b5cf6", "youtube"),
    ("newbie_player", "#06b6d4", "kick"),
    ("night_owl", "#10b981", "twitch"),
    ("kaigo_desu", "#ef4444", "youtube"),
    # เพิ่ม 20 คนใหม่
    ("มะม่วงหวาน", "#fbbf24", "twitch"),
    ("DragonSlayer", "#dc2626", "youtube"),
    ("น้องเนย", "#f472b6", "tiktok"),
    ("ProSniper99", "#0ea5e9", "kick"),
    ("สายมู", "#84cc16", "twitch"),
    ("PokémonMaster", "#f59e0b", "youtube"),
    ("แมวเหมียว", "#c084fc", "mylive"),
    ("Vtuber_Fan", "#ec4899", "youtube"),
    ("กาแฟดำ", "#78716c", "twitch"),
    ("Speedrunner", "#06b6d4", "twitch"),
    ("ขนมจาก", "#fb7185", "tiktok"),
    ("LootGoblin", "#65a30d", "kick"),
    ("นักเล่าเรื่อง", "#a855f7", "mylive"),
    ("NoobMaster69", "#ef4444", "youtube"),
    ("เทพคีย์บอร์ด", "#0284c7", "twitch"),
    ("AnimeGirl_00", "#f472b6", "youtube"),
    ("ไอติมเจ๊", "#06b6d4", "tiktok"),
    ("ClutchKing", "#facc15", "kick"),
    ("น้องใหม่ไลฟ์สด", "#34d399", "mylive"),
    ("ZombieKiller", "#dc2626", "twitch"),
]

# ── ข้อความธรรมดาภาษาไทย (ขยาย 12 → 25) ──
_THAI_PLAIN = [
    "สวัสดีครับ รับชมถ่ายทอดสดครับ",
    "เล่นเกมเก่งจังเลยครับ",
    "ขอเพลงหน่อยครับ 🎵",
    "เมื่อคืนนอนกี่โมงเหรอครับ",
    "เจ๋งมากครับ กดติดตามแล้วนะ",
    "วันนี้เล่นเกมอะไรครับ",
    "โชคดีครับ สู้ๆ",
    "เพิ่งมาดู น่าสนุกดี",
    "พี่หล่อมากครับ 😍",
    "เล่นเกมสิครับ อย่าหยุด",
    "ขอบคุณที่สตรีมครับ",
    "หิวข้าวจัง ไปกินข้าวก่อนนะ",
    # เพิ่ม 13 ข้อความใหม่
    "สายมูจริงๆ ครับพี่",
    "ขอเปิดไมค์คุยหน่อยครับ",
    "พี่ใช้เมาส์รุ่นไหนครับ",
    "เพิ่งตื่นมาดูทันเลย",
    "วันนี้ออกไปไหนไหมครับ",
    "เล่นเกมจบหรือยังครับ",
    "พี่อายุเท่าไหร่ครับ",
    "กราฟิกสวยมากครับ",
    "เสียงไมค์ชัดดีครับ",
    "ขอเพลงหวานๆ หน่อยค่ะ",
    "เกมนี้เล่นยากไหมคะ",
    "พี่เล่นเกมนี้กี่ปีแล้วครับ",
    "ดูสบายตาดีครับ อิ่มใจ",
]

# ── ข้อความภาษาอังกฤษ (ขยาย 5 → 12) ──
_EN_PLAIN = [
    "Hello! Nice stream",
    "GG WP! amazing play",
    "Pog content right here",
    "first time watching, loving it",
    "where are you from?",
    # เพิ่ม 7 ข้อความใหม่
    "That clutch was insane!",
    "Haha nice fail 😄",
    "Stream is so relaxing",
    "What game is this?",
    "Your setup looks clean",
    "KEKW that was funny",
    "Let's gooo! 🔥",
]

# ── ข้อความภาษาญี่ปุ่น (ขยาย 3 → 6) ──
_JP_PLAIN = [
    "こんにちは！楽しい配信ですね",
    "おつかれさまです！応援しています",
    "すごいプレイですね！",
    # เพิ่ม 3 ข้อความใหม่
    "また来ますね！",
    "めっちゃ上手いですね！",
    "頑張ってください！",
]

# ── ข้อความภาษาเกาหลี่ / จีน (ใหม่ — 5) ──
_KR_CN_PLAIN = [
    "안녕하세요! 재미있네요",
    "잘하고 계시네요! 응원합니다",
    "대박! 진짜 잘하신다",
    "你好！直播很精彩",
    "加油！我会一直看的",
]

# ── ข้อความยาว (ขยาย 3 → 6) ──
_LONG_MSGS = [
    "อยากให้สตรีมยาวๆ หน่อยครับ วันนี้มาเล่นเกมใหม่ที่เพิ่งออก ดูน่าสนุกมากเลย กราฟิกสวยและเนื้อเรื่องน่าสนใจ รอติดตามต่อครับ",
    "ขอบคุณที่สตรีมมาตลอดครับ ดูทุกคลิปเลย วันนี้เกมน่าตื่นเต้นมาก เล่นได้เก่งขึ้นเยอะเลย ฝากเนื้อฝากตัวด้วยนะครับ",
    "Long time viewer here! Been watching since the beginning, your content keeps getting better. Keep up the great work and don't forget to take breaks! 💪",
    # เพิ่ม 3 ข้อความใหม่
    "พี่ครับ อยากแนะนำเกมใหม่ที่น่าสนใจมาก มีเนื้อเรื่องที่ลึกซึ้ง ระบบเล่นหลากหลาย และกราฟิกที่สวยงาม น่าจะลองเล่นดูนะครับรับรองว่าสนุกแน่ๆ",
    "เพิ่งจบเกมมาเหนื่อยมากเลย แวะมาดูสตรีมพักผ่อนสายตา ดื่มกาแฟ แล้วก็หายเหนื่อยเลยครับ ขอบคุณที่ทำคอนเทนต์ดีๆ มาให้ดูเสมอ",
    "Just wanted to say your streams have been a highlight of my week! The way you interact with chat and handle tough situations in-game is so entertaining. Sending positive vibes from across the world! 🌍",
]

# ── ข้อความมี emoji (ขยาย 5 → 10) ──
_EMOJI_MSGS = [
    "รักเลย ❤️🔥✨🎉",
    "ขำๆ 😂😂😂 ตลกจัง",
    "เจ๋งไปเลย 👍😎👌",
    "น่ารักจัง 🥰🥰",
    "GG 🎮🎯🏆",
    # เพิ่ม 5 ข้อความใหม่
    "ปากกาไซส์ 🖊️✏️📝",
    "ฟ้าผ่า ⚡⚡⚡ สุดยอด!",
    "อากาศดี 🌈🌤️ สดชื่น",
    "กาแฟคัพ ☕🥐 พร้อมเริ่มวัน",
    "ไนท์โอวล 🌙⭐ นอนดึกจัง",
]

# ── ข้อความมี Twitch emote (ขยาย 3 → 5) ──
_TWITCH_EMOTE_MSGS = [
    {"text": "ดีครับ Kappa ทดสอบ emote",
     "raw": "ดีครับ Kappa ทดสอบ emote",
     "emotes": [{"id": 25, "name": "Kappa", "start": 7, "end": 12}]},
    {"text": "PogChamp เจ๋งมาก",
     "raw": "PogChamp เจ๋งมาก",
     "emotes": [{"id": 305954156, "name": "PogChamp", "start": 0, "end": 8}]},
    {"text": "LUL ขำมาก Kappa",
     "raw": "LUL ขำมาก Kappa",
     "emotes": [{"id": 425618, "name": "LUL", "start": 0, "end": 3},
                {"id": 25, "name": "Kappa", "start": 10, "end": 15}]},
    # เพิ่ม 2 ข้อความใหม่
    {"text": "KEKW ตลกจัง PogChamp",
     "raw": "KEKW ตลกจัง PogChamp",
     "emotes": [{"id": 187004427, "name": "KEKW", "start": 0, "end": 4},
                {"id": 305954156, "name": "PogChamp", "start": 12, "end": 20}]},
    {"text": "peepoHappy ดีใจจัง",
     "raw": "peepoHappy ดีใจจัง",
     "emotes": [{"id": 304489322, "name": "peepoHappy", "start": 0, "end": 11}]},
]

# ── คำถามจากผู้ชม (ใหม่ — 8) ──
_QUESTIONS = [
    "พี่เล่นเกมนี้เป็นกี่ปีแล้วครับ?",
    "ใช้คีย์บอร์ดยี่ห้ออะไรครับ?",
    "ตั้งค่าเมาส์ sens เท่าไหร่ครับ?",
    "เล่น ranked หรือ casual ครับ?",
    "มีคลิปน่าสนใจไหมครับ?",
    "พี่เริ่มสตรีมตอนไหนครับ?",
    "ใช้โปรแกรมตัดคลิปอะไรครับ?",
    "เคยแข่ง esport ไหมครับ?",
]

# ── ปฏิกิริยาสั้นๆ (ใหม่ — 10) ──
_REACTIONS = [
    "โอ้!",
    "ว้าว!",
    "เหี้ย!",
    "แน่่!",
    "อุ๊ย!",
    "เร็วจัง!",
    "ช็ค!",
    "จริงๆ?",
    "โคตร!",
    "สุดยอด!",
]


def _build_demo_pool():
    """สร้าง ~150 demo messages จาก pools (หลากหลาย ไม่ซ้ำ)"""
    pool = []
    offset = 0
    def _next_author(i):
        # วน author แบบกระจาย (offset เพิ่มตามหมวด เพื่อกันซ้ำผู้พูดติดกัน)
        nonlocal offset
        a, c, p = _AUTHORS[(i + offset) % len(_AUTHORS)]
        offset += 1
        return a, c, p

    # ข้อความธรรมดา: ไทย 25 + EN 12 + JP 6 + KR/CN 5 + long 6 = 54
    for i, txt in enumerate(_THAI_PLAIN):
        a, c, p = _next_author(i)
        pool.append(_mkmsg(a, c, p, "message", txt))
    for i, txt in enumerate(_EN_PLAIN):
        a, c, p = _next_author(i)
        pool.append(_mkmsg(a, c, p, "message", txt))
    for i, txt in enumerate(_JP_PLAIN):
        a, c, p = _next_author(i)
        pool.append(_mkmsg(a, c, p, "message", txt))
    for i, txt in enumerate(_KR_CN_PLAIN):
        a, c, p = _next_author(i)
        pool.append(_mkmsg(a, c, p, "message", txt))
    for i, txt in enumerate(_LONG_MSGS):
        a, c, p = _next_author(i)
        pool.append(_mkmsg(a, c, p, "message", txt))
    # ข้อความมี emoji (10)
    for i, txt in enumerate(_EMOJI_MSGS):
        a, c, p = _next_author(i)
        pool.append(_mkmsg(a, c, p, "message", txt))
    # ข้อความมี Twitch emote (5)
    for i, m in enumerate(_TWITCH_EMOTE_MSGS):
        a, c, p = _next_author(i)
        pool.append(_mkmsg(a, c, p, "message", m["text"], emotes=m["emotes"]))
    # คำถามจากผู้ชม (8)
    for i, txt in enumerate(_QUESTIONS):
        a, c, p = _next_author(i)
        pool.append(_mkmsg(a, c, p, "message", txt))
    # ปฏิกิริยาสั้นๆ (10)
    for i, txt in enumerate(_REACTIONS):
        a, c, p = _next_author(i)
        pool.append(_mkmsg(a, c, p, "message", txt))
    # Bits (Twitch) — 3
    pool.append(_mkmsg("ผู้ชมใจดี", "#f59e0b", "twitch", "bits", "สู้ๆ นะครับ", amount=100, badge="💰"))
    pool.append(_mkmsg("GoldDonator", "#fbbf24", "twitch", "bits", "เจ๋งมาก!", amount=500, badge="💰"))
    pool.append(_mkmsg("WhaleX", "#f59e0b", "twitch", "bits", "GG!", amount=1000, badge="💰"))
    # Sub / Resub (Twitch) — 3
    pool.append(_mkmsg("นักสมัครใหม่", "#10b981", "twitch", "sub", "", system_text="สมัครสมาชิก!", badge="⭐"))
    pool.append(_mkmsg("ขาประจำ", "#22c55e", "twitch", "resub", "", system_text="ต่อสมาชิกเดือนที่ 3!", badge="⭐"))
    pool.append(_mkmsg("SubTier2", "#10b981", "twitch", "sub", "", system_text="Tier 2 Subscriber!", badge="⭐"))
    # Subgift (Twitch) — 2
    pool.append(_mkmsg("ใจดีการิล", "#a855f7", "twitch", "subgift", "", system_text="แจก 5 ซับให้ช่องนี้!", badge="🎁"))
    pool.append(_mkmsg("GiftMaster", "#a855f7", "twitch", "subgift", "", system_text="แจก 10 ซับให้คอมมูนิตี้!", badge="🎁"))
    # Superchat (YouTube) — 3
    pool.append(_mkmsg("FanClub", "#22c55e", "youtube", "superchat", "สู้ๆ ค่ะ!", amount="฿50", badge="💎"))
    pool.append(_mkmsg("BigFan", "#22c55e", "youtube", "superchat", "รักน้าา", amount="฿100", badge="💎"))
    pool.append(_mkmsg("VIP_Viewer", "#16a34a", "youtube", "superchat", "ขอบคุณครับ!", amount="฿500", badge="💎"))
    # Membership (YouTube) — 2
    pool.append(_mkmsg("MemberNew", "#22c55e", "youtube", "membership", "", system_text="สมัคร Member แล้ว!", badge="🎖️"))
    pool.append(_mkmsg("MemberPro", "#16a34a", "youtube", "membership", "", system_text="Member ระดับ 2!", badge="🎖️"))
    # Gift (TikTok) — 2
    pool.append(_mkmsg("TikTokFan", "#fe2c55", "tiktok", "gift", "", system_text="ส่ง Rose ให้!", amount="Rose", badge="🎁"))
    pool.append(_mkmsg("TikToker", "#fe2c55", "tiktok", "gift", "", system_text="ส่ง Lion!", amount="Lion", badge="🎁"))
    # Raid (Twitch) — 2
    pool.append(_mkmsg("RaidLeader", "#06b6d4", "twitch", "raid", "", system_text="Raid 50 คน จาก channel_x", amount="50", badge="🎯"))
    pool.append(_mkmsg("BigRaid", "#06b6d4", "twitch", "raid", "", system_text="Raid 200 คน จาก streamer_pro", amount="200", badge="🎯"))
    # Follow / Like / Share (TikTok) — 3
    pool.append(_mkmsg("NewFollower", "#fe2c55", "tiktok", "follow", "", system_text="กดติดตามแล้ว!", badge="⭐"))
    pool.append(_mkmsg("LikeSpammer", "#fe2c55", "tiktok", "like", "", system_text="กดไลค์ 100 ครั้ง!", amount="100", badge="❤️"))
    pool.append(_mkmsg("ShareFriend", "#fe2c55", "tiktok", "share", "", system_text="แชร์ให้เพื่อน ๆ!", badge="📤"))
    return pool


DEMO_POOL = _build_demo_pool()


class GameOverlayServer:
    """HTTP + WebSocket server สำหรับ Game Overlay"""

    def __init__(self, settings, port: int = 8767) -> None:
        self.settings = settings
        self.port = port
        self._clients: set = set()
        self._runner = None
        self._site = None
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop_event = threading.Event()
        self._started = False
        self._start_error: Optional[str] = None
        # demo loop state
        self._demo_running = False
        self._demo_task = None
        self._demo_interval = 5.0
        self._demo_stop_event = None  # asyncio.Event (สร้างใน _run)
        # command queue — parent push → subprocess poll (แทน stdin ที่ไม่ทำงานใน exe)
        self._cmd_queue: list[dict] = []

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def start(self) -> bool:
        if self._started:
            return True
        self._stop_event.clear()
        self._start_error = None
        self._thread = threading.Thread(
            target=self._run, name="GameOverlayServer", daemon=True,
        )
        self._thread.start()
        self._stop_event.wait(1.5)
        if self._start_error:
            return False
        return self._started

    def _run(self) -> None:
        try:
            import aiohttp.web as web
        except Exception as exc:  # noqa: BLE001
            self._start_error = f"aiohttp ไม่พร้อมใช้: {exc}"
            self._stop_event.set()
            return

        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        app = web.Application()
        app.router.add_get("/", self._handle_index)
        app.router.add_get("/config", self._handle_config)
        app.router.add_get("/theme", self._handle_theme)
        app.router.add_get("/custom_css", self._handle_custom_css)
        app.router.add_get("/ws", self._handle_ws)
        app.router.add_get("/logo/{platform}", self._handle_logo)
        app.router.add_get("/emote/{emote_id}", self._handle_emote)
        app.router.add_get("/character/{job}", self._handle_character_img)
        # command queue (parent → subprocess ผ่าน HTTP แทน stdin)
        app.router.add_post("/cmd", self._handle_cmd)
        app.router.add_get("/poll_cmd", self._handle_poll_cmd)

        # สร้าง asyncio.Event สำหรับ demo loop (ต้องอยู่ใน event loop)
        self._demo_stop_event = asyncio.Event()

        try:
            self._runner = web.AppRunner(app)
            self._loop.run_until_complete(self._runner.setup())
            self._site = web.TCPSite(self._runner, "127.0.0.1", self.port)
            self._loop.run_until_complete(self._site.start())
            self._started = True
            self._stop_event.set()
            self._loop.run_forever()
        except OSError as exc:
            self._start_error = f"port {self.port} ไม่ว่าง: {exc}"
            self._stop_event.set()
        except Exception as exc:  # noqa: BLE001
            self._start_error = f"เริ่ม server ไม่ได้: {exc}"
            self._stop_event.set()
        finally:
            try:
                if self._runner is not None:
                    self._loop.run_until_complete(self._runner.cleanup())
            except Exception:  # noqa: BLE001
                pass
            try:
                self._loop.close()
            except Exception:  # noqa: BLE001
                pass

    def stop(self) -> None:
        if not self._started:
            return
        self._started = False
        if self._loop is not None and self._loop.is_running():
            try:
                self._loop.call_soon_threadsafe(self._loop.stop)
            except Exception:  # noqa: BLE001
                pass
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=3)
        self._thread = None
        self._loop = None
        self._clients.clear()

    @property
    def is_running(self) -> bool:
        return self._started

    # ------------------------------------------------------------------ #
    # HTTP handlers
    # ------------------------------------------------------------------ #
    async def _handle_index(self, request):
        import aiohttp.web as web
        html = self._read_overlay_html()
        return web.Response(text=html, content_type="text/html",
                            headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

    async def _handle_config(self, request):
        import aiohttp.web as web
        return web.json_response(self._build_config())

    async def _handle_theme(self, request):
        """return CSS ของ theme ที่เลือก"""
        import aiohttp.web as web
        s = self.settings
        theme = getattr(s, "game_overlay_theme", "neon")
        css = get_theme_css(theme, getattr(s, "game_overlay_custom_css", ""))
        return web.json_response({"theme": theme, "css": css})

    async def _handle_custom_css(self, request):
        """return user custom CSS"""
        import aiohttp.web as web
        s = self.settings
        css = getattr(s, "game_overlay_custom_css", "")
        return web.json_response({"css": css})

    async def _handle_logo(self, request):
        import aiohttp.web as web
        platform = request.match_info.get("platform", "")
        if not platform.replace("-", "").replace("_", "").isalnum():
            return web.Response(status=400, text="bad platform")
        path = os.path.join(get_base_dir(), "assets", f"{platform}.png")
        if os.path.exists(path):
            return web.FileResponse(path, headers={"Cache-Control": "max-age=3600"})
        return web.Response(status=404, text="logo not found")

    async def _handle_character_img(self, request):
        """serve character image สำหรับ Character Talk overlay"""
        import aiohttp.web as web
        job = request.match_info.get("job", "").lower().strip()
        if not job.replace("-", "").replace("_", "").isalnum():
            return web.Response(status=400, text="bad job name")
        img_path = ""
        for cj in getattr(self.settings, "character_jobs", []):
            if cj.get("name", "").lower() == job and cj.get("image"):
                img_path = cj["image"]
                break
        if not img_path:
            # fallback → default image (ของผู้ใช้ หรือ avatar.png ที่มากับแอป)
            img_path = resolve_character_default_image(
                getattr(self.settings, "character_default_image", "")
            )
        if img_path and os.path.exists(img_path):
            return web.FileResponse(img_path, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
        return web.Response(status=404, text="character image not found")

    async def _handle_emote(self, request):
        """proxy Twitch emote — รองรับ static + animated ตาม setting

        อ่าน game_overlay_animated_emotes จาก settings:
          - True → ส่ง animated (GIF/APNG) — ขยับได้
          - False → ส่ง static (PNG เฟรมแรก) — ภาพนิ่ง (default)

        รองรับ emote_id ทั้งตัวเลขและ string (emotesv2_XXX)
        """
        import aiohttp.web as web
        import urllib.request
        eid = request.match_info.get("emote_id", "")
        if not eid:
            return web.Response(status=400, text="bad emote id")
        # อ่าน setting — animated หรือ static
        want_animated = bool(getattr(self.settings, "game_overlay_animated_emotes", False))
        cache_dir = os.path.join(
            os.path.expanduser("~"), ".tts-for-livestream", "emote_cache"
        )
        # cache filename แยกตาม mode (static = .png, animated = .gif/.apng)
        if want_animated:
            cache_exts = [(".gif", "image/gif"), (".apng", "image/apng"), (".png", "image/png")]
        else:
            cache_exts = [(".png", "image/png")]
        # check cache — ตรวจสุขภาพ cache ด้วย (กัน static gif ค้าง)
        for ext, ctype in cache_exts:
            cache_path = os.path.join(cache_dir, f"{eid}_1.0{ext}")
            if os.path.exists(cache_path) and os.path.getsize(cache_path) > 0:
                # ถ้า want_animated แต่ cache gif เป็น static (frames=1) → ลบ cache
                if want_animated and ext == ".gif":
                    try:
                        from PIL import Image
                        _check = Image.open(cache_path)
                        if getattr(_check, "n_frames", 1) <= 1:
                            os.remove(cache_path)
                            continue
                    except Exception:
                        pass
                return web.FileResponse(
                    cache_path,
                    headers={"Content-Type": ctype, "Cache-Control": "no-cache"},
                )
        # download — เลือก URL ตาม mode
        if want_animated:
            # animated ก่อน (GIF/APNG) แล้วค่อย static fallback
            urls = [
                (f"https://static-cdn.jtvnw.net/emoticons/v2/{eid}/animated/dark/1.0", "gif"),
                (f"https://static-cdn.jtvnw.net/emoticons/v2/{eid}/animated/light/1.0", "gif"),
                (f"https://static-cdn.jtvnw.net/emoticons/v2/{eid}/default/dark/1.0", "png"),
                (f"https://static-cdn.jtvnw.net/emoticons/v2/{eid}/default/light/1.0", "png"),
                (f"https://static-cdn.jtvnw.net/emoticons/v2/{eid}/static/dark/1.0", "png"),
                (f"https://static-cdn.jtvnw.net/emoticons/v2/{eid}/default/dark/2.0", "png"),
                (f"https://static-cdn.jtvnw.net/emoticons/v2/{eid}/default/dark/3.0", "png"),
            ]
        else:
            # static เท่านั้น
            urls = [
                (f"https://static-cdn.jtvnw.net/emoticons/v2/{eid}/default/dark/1.0", "png"),
                (f"https://static-cdn.jtvnw.net/emoticons/v2/{eid}/default/light/1.0", "png"),
                (f"https://static-cdn.jtvnw.net/emoticons/v2/{eid}/static/dark/1.0", "png"),
                (f"https://static-cdn.jtvnw.net/emoticons/v2/{eid}/default/dark/2.0", "png"),
                (f"https://static-cdn.jtvnw.net/emoticons/v2/{eid}/default/dark/3.0", "png"),
            ]
        # v1 legacy ใช้ได้เฉพาะตัวเลข
        if eid.isdigit():
            urls.append((f"https://static-cdn.jtvnw.net/emoticons/v1/{eid}/1.0", "png"))
        for url, fmt in urls:
            try:
                req = urllib.request.Request(
                    url, headers={"User-Agent": "TTS-for-Livestream/1.0"}
                )
                with urllib.request.urlopen(req, timeout=10) as r:
                    data = r.read()
                    resp_ct = r.headers.get("Content-Type", "")
                if data and len(data) > 0:
                    is_gif = data[:3] == b"GIF"
                    is_apng = b"acTL" in data[:200]
                    # ตรวจ frames (CDN อาจส่ง static GIF แทน animated)
                    n_frames = 1
                    if is_gif or is_apng:
                        try:
                            from PIL import Image
                            from io import BytesIO
                            _img = Image.open(BytesIO(data))
                            n_frames = getattr(_img, "n_frames", 1)
                        except Exception:
                            n_frames = 1
                    # want_animated=True แต่ได้ static (frames=1) → ลอง URL ถัดไป
                    if want_animated and (is_gif or is_apng) and n_frames <= 1:
                        continue
                    # Game Overlay ถ้า want_animated=False → แปลง GIF/APNG → เฟรมแรก PNG
                    if (is_gif or is_apng) and not want_animated:
                        try:
                            from PIL import Image
                            from io import BytesIO
                            img = Image.open(BytesIO(data))
                            if getattr(img, "is_animated", False):
                                img.seek(0)
                            img = img.convert("RGBA")
                            buf = BytesIO()
                            img.save(buf, format="PNG")
                            data = buf.getvalue()
                        except Exception:  # noqa: BLE001
                            pass
                    # กำหนด ext + content-type
                    if "gif" in resp_ct:
                        ext, ctype = ".gif", "image/gif"
                    elif is_apng:
                        ext, ctype = ".apng", "image/apng"
                    elif "png" in resp_ct:
                        ext, ctype = ".png", "image/png"
                    else:
                        ext, ctype = f".{fmt}", f"image/{fmt}"
                    # cache + ส่ง (static mode บังคับ PNG)
                    if not want_animated:
                        ext, ctype = ".png", "image/png"
                    cache_path = os.path.join(cache_dir, f"{eid}_1.0{ext}")
                    try:
                        os.makedirs(cache_dir, exist_ok=True)
                        with open(cache_path, "wb") as f:
                            f.write(data)
                    except Exception:  # noqa: BLE001
                        pass
                    return web.Response(
                        body=data, content_type=ctype,
                        headers={"Cache-Control": "no-cache"},
                    )
            except Exception:  # noqa: BLE001
                continue
        return web.Response(status=404, text="emote not found")

    async def _handle_cmd(self, request):
        """POST /cmd — parent push command → queue (รับ JSON body)"""
        import aiohttp.web as web
        try:
            data = await request.json()
            self._cmd_queue.append(data)
            return web.json_response({"ok": True})
        except Exception as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=400)

    async def _handle_poll_cmd(self, request):
        """GET /poll_cmd — subprocess poll command queue → return all + clear"""
        import aiohttp.web as web
        cmds = self._cmd_queue[:]
        self._cmd_queue.clear()
        return web.json_response({"cmds": cmds})

    async def _handle_ws(self, request):
        import aiohttp.web as web
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self._clients.add(ws)
        try:
            await ws.send_json({"type": "config", "config": self._build_config()})
        except Exception:  # noqa: BLE001
            pass
        try:
            async for _ in ws:
                pass
        finally:
            self._clients.discard(ws)
        return ws

    # ------------------------------------------------------------------ #
    # Push (เรียกจาก UI thread)
    # ------------------------------------------------------------------ #
    def push_message(self, msg: ChatMessage) -> None:
        if not self._started or not self._clients or self._loop is None:
            return
        data = self._serialize_message(msg)
        try:
            asyncio.run_coroutine_threadsafe(self._broadcast(data), self._loop)
        except Exception:  # noqa: BLE001
            pass

    async def _broadcast(self, data: dict) -> None:
        dead = set()
        for ws in list(self._clients):
            try:
                await ws.send_json(data)
            except Exception:  # noqa: BLE001
                dead.add(ws)
        self._clients -= dead

    def update_config(self, settings) -> None:
        """re-push config หลัง settings เปลี่ยน"""
        self.settings = settings
        if not self._started or not self._clients or self._loop is None:
            # DEBUG
            return
        config = self._build_config()
        # DEBUG — log theme push
        try:
            asyncio.run_coroutine_threadsafe(
                self._broadcast({"type": "config", "config": config}), self._loop,
            )
        except Exception:  # noqa: BLE001
            pass

    def update_theme(self, settings) -> None:
        """push theme + custom CSS update ผ่าน WebSocket (live update)"""
        self.settings = settings
        if not self._started or not self._clients or self._loop is None:
            return
        s = settings
        theme = getattr(s, "game_overlay_theme", "neon")
        theme_css = get_theme_css(theme, getattr(s, "game_overlay_custom_css", ""))
        custom_css = getattr(s, "game_overlay_custom_css", "")
        js = (
            f"window.applyTheme && window.applyTheme({json_string(theme_css)}, "
            f"{json_string(custom_css)});"
        )
        try:
            asyncio.run_coroutine_threadsafe(
                self._broadcast({"type": "eval_js", "js": js}), self._loop,
            )
        except Exception:  # noqa: BLE001
            pass

    def reload_emotes(self) -> None:
        """push reload_emotes ไป browser — บังคับ reload ทุก emote image

        ใช้ตอน toggle animate/static เปลี่ยน (Game Overlay)
        """
        if not self._started or not self._clients or self._loop is None:
            return
        try:
            asyncio.run_coroutine_threadsafe(
                self._broadcast({"type": "reload_emotes"}), self._loop,
            )
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ #
    # Demo loop — ส่งข้อความตัวอย่างสุ่มเพื่อ preview settings
    # ------------------------------------------------------------------ #
    def push_demo_message(self) -> None:
        """ส่งข้อความ demo สุ่ม 1 ข้อความจาก DEMO_POOL"""
        if not self._started or not self._clients or self._loop is None:
            return
        try:
            import random
            data = random.choice(DEMO_POOL)
            # อัปเดต timestamp ให้เป็นเวลาปัจจุบัน
            from datetime import datetime
            data = dict(data)
            data["timestamp"] = datetime.now().strftime("%H:%M")
            asyncio.run_coroutine_threadsafe(self._broadcast(data), self._loop)
        except Exception:  # noqa: BLE001
            pass

    def start_demo_loop(self, interval_sec: float) -> None:
        """เริ่ม loop ส่ง demo message ทุก interval_sec วินาที (3-10s)"""
        if not self._started or self._loop is None or self._demo_stop_event is None:
            return
        # หยุด loop เดิมก่อน (clear stop event + ตั้ง running=True)
        def _start_in_loop():
            self._demo_stop_event.clear()
            self._demo_running = True
            self._demo_interval = max(3.0, min(10.0, float(interval_sec)))
            # cancel task เดิมถ้ามี
            if self._demo_task is not None and not self._demo_task.done():
                self._demo_task.cancel()
            self._demo_task = asyncio.ensure_future(self._schedule_demo_loop(self._demo_interval))
        try:
            self._loop.call_soon_threadsafe(_start_in_loop)
        except Exception:  # noqa: BLE001
            pass

    async def _schedule_demo_loop(self, interval_sec: float) -> None:
        """asyncio task ส่ง demo ทุก interval_sec — อ่าน interval ใหม่ทุกรอบ"""
        while self._started and self._demo_running:
            self.push_demo_message()
            try:
                # ใช้ self._demo_interval (อัปเดตได้ real-time)
                cur_interval = self._demo_interval
                await asyncio.wait_for(self._demo_stop_event.wait(), timeout=cur_interval)
                break  # stop_event set → ออก
            except asyncio.TimeoutError:
                continue  # timeout ปกติ → ส่งข้อความถัดไป
            except asyncio.CancelledError:
                break

    def stop_demo_loop(self) -> None:
        """หยุด demo loop"""
        self._demo_running = False
        if self._loop is not None and not self._loop.is_closed() and self._demo_stop_event is not None:
            try:
                self._loop.call_soon_threadsafe(self._demo_stop_event.set)
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------ #
    # Serialization
    # ------------------------------------------------------------------ #
    def _build_config(self) -> dict:
        s = self.settings
        # ★ อ่าน appearance mode + mode-specific config (เหมือน v1)
        #    mode_configs[mode] มีค่า styling เฉพาะของ mode นั้น → override flat settings
        appearance_mode = getattr(s, "game_overlay_appearance_mode", "default")
        mode_configs = getattr(s, "game_overlay_mode_configs", {}) or {}
        mc = dict(mode_configs.get(appearance_mode, {}))  # mode-specific overrides

        # helper: อ่านจาก mode config ก่อน → fallback flat settings
        def mc_get(key, flat_key, default):
            if key in mc:
                return mc[key]
            return getattr(s, flat_key, default)

        # theme + CSS — อ่านจาก mode config ของ theme mode (ถ้าเป็น theme mode)
        if appearance_mode == "theme":
            theme = mc.get("theme", getattr(s, "game_overlay_theme", "default"))
        else:
            theme = "default"  # default/special/character → ไม่มี theme CSS
        theme_css = get_theme_css(theme, getattr(s, "game_overlay_custom_css", "")) if theme != "default" else ""
        custom_css = getattr(s, "game_overlay_custom_css", "")

        # balloon/character mode flags (จาก appearance mode)
        balloon_mode = (appearance_mode == "special")
        character_mode = (appearance_mode == "character")

        return {
            "theme": theme,
            "theme_css": theme_css,
            "custom_css": custom_css,
            # ★ styling อ่านจาก mode config ก่อน → fallback flat
            "font_size": mc_get("font_size", "game_overlay_font_size", 14),
            "emote_size": mc_get("emote_size", "game_overlay_emote_size", 24),
            "animation": mc_get("anim_in", "game_overlay_anim_in", "fade"),
            "exit_animation": mc_get("anim_out", "game_overlay_anim_out", "fade_out"),
            "max_messages": mc_get("max_rows", "game_overlay_max_rows", 15),
            "direction": getattr(s, "game_overlay_direction", "bottom"),
            "show_logo": mc_get("show_logo", "game_overlay_show_logo", True),
            "show_timestamp": mc_get("show_timestamp", "game_overlay_show_timestamp", False),
            "auto_hide": mc_get("auto_hide", "game_overlay_auto_hide", True),
            "hide_after": mc_get("hide_after", "game_overlay_hide_after", 8.0),
            "font_family": mc_get("font_family", "game_overlay_font_family", "Kanit"),
            "font_weight": mc_get("font_weight", "game_overlay_font_weight", "500"),
            "text_color": mc_get("text_color", "game_overlay_text_color", "#ffffff"),
            "color_sub": getattr(s, "game_overlay_color_sub", "#22c55e"),
            "color_bits": getattr(s, "game_overlay_color_bits", "#f59e0b"),
            "color_donate": getattr(s, "game_overlay_color_donate", "#22c55e"),
            "color_system": getattr(s, "game_overlay_color_system", "#9ca3af"),
            "show_original": getattr(s, "game_overlay_show_original", True),
            "show_redeem": getattr(s, "game_overlay_show_redeem", True),
            "text_stroke": mc_get("text_stroke", "game_overlay_text_stroke", False),
            "text_stroke_color": mc_get("text_stroke_color", "game_overlay_text_stroke_color", "#000000"),
            "text_stroke_width": mc_get("text_stroke_width", "game_overlay_text_stroke_width", 2),
            "text_shadow": mc_get("text_shadow", "game_overlay_text_shadow", True),
            "text_shadow_color": mc_get("text_shadow_color", "game_overlay_text_shadow_color", "#000000"),
            "text_shadow_blur": mc_get("text_shadow_blur", "game_overlay_text_shadow_blur", 3),
            "layout": mc_get("layout", "game_overlay_layout", "inline"),
            # box settings — อ่านจาก mode config ก่อน
            "box_enabled": mc_get("box_enabled", "game_overlay_box_enabled", False),
            "box_bg_color": mc_get("box_bg_color", "game_overlay_box_bg_color", "#0a0e1a"),
            "box_bg_opacity": mc_get("box_bg_opacity", "game_overlay_box_bg_opacity", 0.55),
            "box_radius": mc_get("box_radius", "game_overlay_box_radius", 8),
            "box_border": mc_get("box_border", "game_overlay_box_border", False),
            "box_border_color": mc_get("box_border_color", "game_overlay_box_border_color", "#7c3aed"),
            "box_border_width": mc_get("box_border_width", "game_overlay_box_border_width", 1),
            "box_shadow": mc_get("box_shadow", "game_overlay_box_shadow", False),
            "box_blur": float(mc_get("box_blur", "game_overlay_box_blur", 0) or 0),
            "box_glow": (
                False if balloon_mode
                else mc_get("box_glow", "game_overlay_box_glow", False)
            ),
            "box_glow_color": mc_get("box_glow_color", "game_overlay_box_glow_color", "#7c3aed"),
            "box_width": getattr(s, "game_overlay_box_width", "fit"),
            "msg_spacing": mc_get("msg_spacing", "game_overlay_msg_spacing", 4.0),
            "msg_only": mc_get("layout", "game_overlay_layout", "inline") == "message_only",
            "balloon_mode": balloon_mode,
            "balloon_hide_after": mc_get("balloon_hide_after", "game_overlay_balloon_hide_after", 5.0),
            "balloon_bg_opacity": mc_get("balloon_bg_opacity", "game_overlay_balloon_bg_opacity", 0.95),
            # Character Talk
            "character_mode": character_mode,
            "character_hide_after": getattr(s, "character_hide_after", 6.0),
            "character_size": getattr(s, "character_size", 120),
            "character_max_on_screen": getattr(s, "character_max_on_screen", 8),
            "character_name_size": getattr(s, "character_name_size", 11),
            "character_name_stroke": getattr(s, "character_name_stroke", True),
            "character_name_stroke_color": getattr(s, "character_name_stroke_color", "#000000"),
            "character_name_stroke_width": getattr(s, "character_name_stroke_width", 1),
            "character_name_shadow": getattr(s, "character_name_shadow", True),
            "character_name_shadow_color": getattr(s, "character_name_shadow_color", "#000000"),
            "character_name_shadow_blur": getattr(s, "character_name_shadow_blur", 2),
            "character_random_pos": getattr(s, "character_random_pos", True),
            "character_bubble_width": getattr(s, "character_bubble_width", 500),
            "character_jobs": [cj.get("name", "") for cj in getattr(s, "character_jobs", [])],
            "scrollbar": getattr(s, "game_overlay_scrollbar", "none"),
            "max_msg_length": getattr(s, "game_overlay_max_msg_length", 0),
        }

    def _get_event_color(self, event: str, extra: dict) -> str:
        """คืนสี author ตาม event type — ใช้สีที่ผู้ใช้ตั้งใน settings"""
        s = self.settings
        # map event → color field
        sub_events = {"sub", "resub", "subgift", "membership", "follow"}
        bits_events = {"bits"}
        donate_events = {"superchat", "gift", "raid", "share"}
        system_events = {"system", "join"}
        if event in sub_events:
            return getattr(s, "game_overlay_color_sub", "#22c55e")
        elif event in bits_events:
            return getattr(s, "game_overlay_color_bits", "#f59e0b")
        elif event in donate_events:
            return getattr(s, "game_overlay_color_donate", "#22c55e")
        elif event in system_events:
            return getattr(s, "game_overlay_color_system", "#9ca3af")
        # message ปกติ → ใช้สีของ platform/author ถ้ามี ไม่งั้นใช้ text_color
        user_color = extra.get("color", "") if extra else ""
        return user_color if user_color else getattr(s, "game_overlay_text_color", "#ffffff")

    def _serialize_message(self, msg: ChatMessage) -> dict:
        from datetime import datetime
        extra = msg.extra or {}
        event_badge = {
            "message": "", "bits": "💰", "superchat": "💎", "gift": "🎁",
            "sub": "⭐", "resub": "⭐", "subgift": "🎁", "raid": "🎯",
            "like": "❤️", "follow": "⭐", "share": "📤", "join": "👋",
            "membership": "🎖️",
        }.get(msg.event, "")
        twitch_emotes = []
        want_animated = bool(getattr(self.settings, "game_overlay_animated_emotes", False))
        for em in (extra.get("emotes") or []):
            eid = em.get("id")
            emote_url = em.get("url", "")
            emote_url_animated = em.get("url_animated", "")
            if emote_url:
                # เลือก URL ตาม setting (animated หรือ static)
                if want_animated and emote_url_animated:
                    final_url = emote_url_animated
                else:
                    final_url = emote_url
                twitch_emotes.append({
                    "name": em.get("name", ""),
                    "url": final_url,
                    "start": em.get("start", 0),
                    "end": em.get("end", 0),
                })
            elif eid is not None:
                # Twitch emote → proxy /emote/{id} (proxy เลือก static/animated ตาม setting)
                twitch_emotes.append({
                    "name": em.get("name", ""),
                    "url": f"/emote/{eid}",
                    "start": em.get("start", 0),
                    "end": em.get("end", 0),
                })
        return {
            "type": "message",
            "platform": msg.platform,
            "author": msg.author,
            "text": msg.text or "",
            "system_text": msg.system_text or "",
            "event": msg.event,
            "amount": msg.amount,
            "badge": event_badge,
            "color": self._get_event_color(msg.event, extra),
            "timestamp": datetime.now().strftime("%H:%M"),
            "raw_text": extra.get("raw_text", ""),
            "segments": extra.get("segments", []),
            "twitch_emotes": twitch_emotes,
            "sticker_url": extra.get("sticker_url", ""),
            # Translation info
            "is_translated": bool(extra.get("translated")),
            "translated_text": extra.get("translated_text", ""),
            "original_text": extra.get("original_text", ""),
            "source_lang": extra.get("source_lang", ""),
            # Channel Points redemption info
            "reward_title": extra.get("reward_title", ""),
            "reward_cost": extra.get("reward_cost", 0),
            "reward_icon": extra.get("reward_icon", ""),
            "job": extra.get("_job", ""),
        }

    def _read_overlay_html(self) -> str:
        path = os.path.join(get_base_dir(), "game_overlay.html")
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:  # noqa: BLE001
            return (
                "<!doctype html><html><body style='background:transparent;"
                "color:#fff;font-family:sans-serif;padding:20px'>"
                "game_overlay.html not found</body></html>"
            )


def json_string(s: str) -> str:
    """แปลง Python string → JavaScript string literal (JSON-encoded)"""
    import json
    return json.dumps(s, ensure_ascii=False)


if __name__ == "__main__":
    import sys
    import time

    class FakeSettings:
        game_overlay_port = 8767
        game_overlay_theme = "neon"
        game_overlay_custom_css = ""
        game_overlay_font_size = 14
        game_overlay_anim_in = "fade"
        game_overlay_anim_out = "fade_out"
        game_overlay_max_rows = 15
        game_overlay_direction = "bottom"
        game_overlay_show_logo = True
        game_overlay_show_timestamp = False
        game_overlay_auto_hide = True
        game_overlay_hide_after = 8.0
        game_overlay_font_family = "Kanit"
        game_overlay_font_weight = "500"
        game_overlay_text_color = "#ffffff"
        game_overlay_text_stroke = False
        game_overlay_text_stroke_color = "#000000"
        game_overlay_text_stroke_width = 2
        game_overlay_text_shadow = True
        game_overlay_text_shadow_color = "#000000"
        game_overlay_text_shadow_blur = 3
        game_overlay_layout = "inline"
        game_overlay_box_enabled = True
        game_overlay_box_bg_color = "#0a0e1a"
        game_overlay_box_bg_opacity = 0.55
        game_overlay_box_radius = 8
        game_overlay_box_border = False
        game_overlay_box_border_color = "#7c3aed"
        game_overlay_box_border_width = 1
        game_overlay_box_shadow = True
        game_overlay_box_blur = False
        game_overlay_box_glow = False
        game_overlay_box_glow_color = "#7c3aed"
        game_overlay_box_width = "fit"
        game_overlay_msg_spacing = 4.0
        game_overlay_balloon_mode = False
        game_overlay_balloon_hide_after = 5.0
        game_overlay_scrollbar = "none"
        game_overlay_max_msg_length = 0

    server = GameOverlayServer(FakeSettings(), port=8767)
    print(f"Starting game overlay server on port {server.port}...")
    if server.start():
        print(f"✅ Server running at http://localhost:{server.port}")
        print("   Press Ctrl+C to stop")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping...")
            server.stop()
    else:
        print(f"❌ Failed: {server._start_error}")
        sys.exit(1)
