"""overlay_server.py — local HTTP + WebSocket server สำหรับ OBS overlay

รันเว็บเซิร์ฟเวอร์ในเครื่อง (localhost) ที่ OBS ใช้เป็น Browser Source:
  - GET  /        → overlay HTML (พื้นหลังโปร่งใส + อนิเมชั่น + emote)
  - GET  /config  → JSON config (font_size, emote_size, animation, ...)
  - WS   /ws      → WebSocket รับ message แชทใหม่แบบเรียลไทม์

การใช้งาน:
    server = OverlayServer(settings)
    server.start()                          # เริ่มใน background thread
    server.push_message(chat_message)       # ส่งข้อความไป OBS (เรียกจาก UI thread)
    server.update_config(settings)          # อัปเดต config แล้ว push ใหม่
    server.stop()                           # หยุดเซิร์ฟเวอร์

URL สำหรับ OBS: http://localhost:{port}
"""
from __future__ import annotations

import asyncio
import os
import threading
from typing import Optional

from chat_twitch import ChatMessage
from settings import get_base_dir, resolve_character_default_image

# Twitch emote CDN URL format (overlay โหลดตรงจาก CDN)
TWITCH_EMOTE_CDN = "https://static-cdn.jtvnw.net/emoticons/v2/{id}/default/dark/1.0"


class OverlayServer:
    """local HTTP + WebSocket server สำหรับ OBS browser source overlay"""

    def __init__(self, settings) -> None:
        self.settings = settings
        self.port = getattr(settings, "overlay_port", 8765)
        # WebSocket clients (OBS browser instances)
        self._clients: set = set()
        self._runner = None
        self._site = None
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop_event = threading.Event()
        self._started = False
        self._start_error: Optional[str] = None

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def start(self) -> bool:
        """เริ่ม server ใน daemon thread — คืน True ถ้าเริ่มได้

        ถ้า port ไม่ว่าง → เก็บ error ไว้ใน self._start_error (ตรวจได้ภายหลัง)
        """
        if self._started:
            return True
        self._stop_event.clear()
        self._start_error = None
        self._thread = threading.Thread(
            target=self._run, name="OverlayServer", daemon=True
        )
        self._thread.start()
        # รอสักครู่ให้ thread เริ่ม + ตั้งค่า _started หรือ _start_error
        self._stop_event.wait(1.5)
        if self._start_error:
            return False
        return self._started

    def _run(self) -> None:
        """ทำงานใน daemon thread — asyncio loop + aiohttp server"""
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
        app.router.add_get("/ws", self._handle_ws)
        app.router.add_get("/logo/{platform}", self._handle_logo)
        app.router.add_get("/emote/{emote_id}", self._handle_emote)
        app.router.add_get("/character/{job}", self._handle_character_img)

        try:
            self._runner = web.AppRunner(app)
            self._loop.run_until_complete(self._runner.setup())
            self._site = web.TCPSite(
                self._runner, "127.0.0.1", self.port  # localhost only — ปลอดภัย
            )
            self._loop.run_until_complete(self._site.start())
            self._started = True
            self._stop_event.set()
            # รันจนกว่าจะ stop
            self._loop.run_forever()
        except OSError as exc:  # port ไม่ว่าง
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
        """หยุด server (เรียกจาก UI thread)"""
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
        """serve overlay HTML — cache-bust ทุกครั้ง (กัน OBS browser source cache หน้าเก่า)"""
        html = self._read_overlay_html()
        import aiohttp.web as web
        import time as _time
        # ★ inject meta refresh หาก WS ไม่ติดภายใน 10 วิ → reload อัตโนมัติ
        # (แก้ปัญหา OBS เปิดก่อน server → หน้าค้าง)
        refresh_script = '<script>setTimeout(function(){if(!window.ws||window.ws.readyState!==1){location.reload();}},10000);</script>'
        html = html.replace('</body>', refresh_script + '</body>') if '</body>' in html else html + refresh_script
        return web.Response(text=html, content_type="text/html",
                            headers={
                                "Cache-Control": "no-cache, no-store, must-revalidate",
                                "Pragma": "no-cache",
                                "Expires": "0",
                            })

    async def _handle_config(self, request):
        """serve overlay config as JSON (client โหลดตอนเริ่ม)"""
        import aiohttp.web as web
        return web.json_response(self._build_config())

    async def _handle_logo(self, request):
        """serve platform logo จาก assets/ (เช่น /logo/twitch → assets/twitch.png)"""
        import aiohttp.web as web
        platform = request.match_info.get("platform", "")
        # กัน path traversal — เฉพาะชื่อไฟล์เท่านั้น
        if not platform.replace("-", "").replace("_", "").isalnum():
            return web.Response(status=400, text="bad platform")
        path = os.path.join(get_base_dir(), "assets", f"{platform}.png")
        if os.path.exists(path):
            return web.FileResponse(path, headers={"Cache-Control": "max-age=3600"})
        return web.Response(status=404, text="logo not found")

    async def _handle_character_img(self, request):
        """serve character image สำหรับ Character Talk overlay

        /character/{job} → ค้นหาใน settings.character_jobs + character_default_image
        """
        import aiohttp.web as web
        job = request.match_info.get("job", "").lower().strip()
        if not job.replace("-", "").replace("_", "").isalnum():
            return web.Response(status=400, text="bad job name")
        # ค้นหาใน character_jobs
        img_path = ""
        for cj in getattr(self.settings, "character_jobs", []):
            if cj.get("name", "").lower() == job and cj.get("image"):
                img_path = cj["image"]
                break
        # fallback → default image (ของผู้ใช้ หรือ avatar.png ที่มากับแอป)
        if not img_path:
            img_path = resolve_character_default_image(
                getattr(self.settings, "character_default_image", "")
            )
        if img_path and os.path.exists(img_path):
            return web.FileResponse(img_path, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
        return web.Response(status=404, text="character image not found")

    async def _handle_emote(self, request):
        """proxy Twitch emote ผ่าน local server — รองรับ static + animated (APNG/GIF)

        ดาวน์โหลดจาก Twitch CDN หลาย format → ใช้ไฟล์แรกที่สำเร็จ
        cache แยกตาม format (animated ใช้ .gif/.apng, static ใช้ .png)
        ส่ง content-type ที่ถูกต้อง → browser แสดง animation ได้
        path: /emote/{emote_id}

        emote_id มี 2 format:
          - ตัวเลข (เก่า): เช่น 25, 302222303
          - string (emotesv2): เช่น emotesv2_2d076ec967d946c8853d24dc4c943d82
        """
        import aiohttp.web as web
        import urllib.request
        eid = request.match_info.get("emote_id", "")
        if not eid:
            return web.Response(status=400, text="bad emote id")
        # อ่าน setting — animated หรือ static
        want_animated = bool(getattr(self.settings, "overlay_animated_emotes", True))
        cache_dir = os.path.join(
            os.path.expanduser("~"), ".tts-for-livestream", "emote_cache"
        )

        # cache filename แยกตาม mode
        if want_animated:
            cache_exts = [(".gif", "image/gif"), (".apng", "image/apng"), (".png", "image/png")]
        else:
            cache_exts = [(".png", "image/png")]

        # 1) เช็ค cache ตาม mode (animated หรือ static)
        # NOTE: ใช้ Cache-Control: no-cache เพื่อให้ browser ขอใหม่ทุกครั้ง
        # (toggle animate/static ต้องการ refresh ทันที)
        # ตรวจสุขภาพ cache: ถ้า want_animated แต่ cache gif เป็น static (frames=1)
        # → ลบ cache และโหลดใหม่ (CDN อาจส่ง static fallback ตอนโหลดครั้งแรก)
        for ext, ctype in cache_exts:
            cache_path = os.path.join(cache_dir, f"{eid}_1.0{ext}")
            if os.path.exists(cache_path) and os.path.getsize(cache_path) > 0:
                # ตรวจ cache ถูกต้องไหม (กัน static gif ค้างเมื่อ want animated)
                if want_animated and ext == ".gif":
                    try:
                        from PIL import Image
                        img = Image.open(cache_path)
                        if getattr(img, "n_frames", 1) <= 1:
                            # static gif แต่ต้องการ animated → ลบ cache
                            os.remove(cache_path)
                            continue
                    except Exception:
                        pass
                return web.FileResponse(
                    cache_path,
                    headers={"Content-Type": ctype, "Cache-Control": "no-cache"},
                )

        # 2) ดาวน์โหลด — เลือก URL ตาม mode
        if want_animated:
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
            urls = [
                (f"https://static-cdn.jtvnw.net/emoticons/v2/{eid}/default/dark/1.0", "png"),
                (f"https://static-cdn.jtvnw.net/emoticons/v2/{eid}/default/light/1.0", "png"),
                (f"https://static-cdn.jtvnw.net/emoticons/v2/{eid}/static/dark/1.0", "png"),
                (f"https://static-cdn.jtvnw.net/emoticons/v2/{eid}/default/dark/2.0", "png"),
                (f"https://static-cdn.jtvnw.net/emoticons/v2/{eid}/default/dark/3.0", "png"),
            ]
        # v1 legacy ใช้ได้เฉพาะตัวเลขเท่านั้น
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
                    # want_animated=False แต่ได้ GIF/APNG → แปลงเป็นเฟรมแรก (PNG static)
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
                    # กำหนด extension + content-type ตามที่ Twitch ส่งมาจริง
                    # สำคัญ: APNG (Animated PNG) มี Content-Type เป็น image/png เหมือน PNG ปกติ
                    # → ต้องตรวจ magic bytes 'acTL' (APNG animation control chunk)
                    #    เพื่อแยก APNG ออกจาก PNG ปกติ (browser แสดง APNG ขยับได้)
                    is_apng = b"acTL" in data[:200]
                    if "gif" in resp_ct:
                        ext, ctype = ".gif", "image/gif"
                    elif is_apng:
                        # APNG — ใช้ extension .apng + content-type image/apng
                        # (browser รองรับ image/apng และจะแสดงเป็น animation)
                        ext, ctype = ".apng", "image/apng"
                    elif "png" in resp_ct:
                        ext, ctype = ".png", "image/png"
                    else:
                        ext, ctype = f".{fmt}", f"image/{fmt}"
                    # static mode → บังคับ PNG
                    if not want_animated:
                        ext, ctype = ".png", "image/png"
                    # cache disk
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

    async def _handle_ws(self, request):
        """WebSocket — OBS browser connect รับ message แบบเรียลไทม์"""
        import aiohttp.web as web
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self._clients.add(ws)
        # ส่ง config ปัจจุบันทันทีตอน connect (เผื่อ client พลาด initial fetch)
        try:
            await ws.send_json({"type": "config", "config": self._build_config()})
        except Exception:  # noqa: BLE001
            pass
        try:
            async for _ in ws:
                pass  # รอจน client ปิด
        finally:
            self._clients.discard(ws)
        return ws

    # ------------------------------------------------------------------ #
    # Message push (เรียกจาก UI thread)
    # ------------------------------------------------------------------ #
    def push_message(self, msg: ChatMessage) -> None:
        """ส่ง message ใหม่ไปทุก OBS browser client

        เรียกจาก UI thread → schedule ใน asyncio loop ของ server thread
        ถ้าไม่มี client → เงียบ
        """
        if not self._started or not self._clients or self._loop is None:
            return
        data = self._serialize_message(msg)
        try:
            asyncio.run_coroutine_threadsafe(
                self._broadcast(data), self._loop
            )
        except Exception:  # noqa: BLE001
            pass  # server อาจกำลัง shutdown

    async def _broadcast(self, data: dict) -> None:
        """ส่ง JSON ไปทุก client พร้อมทำความสะอาด client ที่ตาย"""
        dead = set()
        for ws in list(self._clients):
            try:
                await ws.send_json(data)
            except Exception:  # noqa: BLE001
                dead.add(ws)
        self._clients -= dead

    def push_test_message(self) -> None:
        """ส่งข้อความตัวอย่างไป overlay (สำหรับปุ่ม '🎲 ทดสอบ' — เห็น animation ทันที)"""
        from datetime import datetime
        if not self._started or not self._clients or self._loop is None:
            return
        data = {
            "type": "message",
            "platform": "twitch",
            "author": "OverlayTest",
            "text": "สวัสดีครับ! นี่คือข้อความทดสอบ 🎉",
            "system_text": "",
            "event": "message",
            "amount": None,
            "badge": "",
            "color": "#a855f7",
            "timestamp": datetime.now().strftime("%H:%M"),
            "raw_text": "สวัสดีครับ! นี่คือข้อความทดสอบ 🎉",
            "segments": [],
            "twitch_emotes": [],
            "sticker_url": "",
        }
        try:
            asyncio.run_coroutine_threadsafe(self._broadcast(data), self._loop)
        except Exception:  # noqa: BLE001
            pass

    def push_demo_messages(self) -> None:
        """ส่งข้อความตัวอย่างสุ่ม 1 ข้อความเข้า overlay (ปุ่ม Demo — กด 1 ครั้ง = 1 ข้อความ)

        สุ่มจาก pool ทุกประเภท: ข้อความธรรมดา, มี Twitch emote, มี emoji,
        event bits/sub, ข้อความยาว — กดหลายครั้งจะเห็นหลายแบบ
        """
        if not self._started or not self._clients or self._loop is None:
            return
        from datetime import datetime
        import random

        def ts():
            return datetime.now().strftime("%H:%M")

        names = [
            ("สตรีมเมอร์หน้าใหม่", "#a855f7"),
            ("ผู้ชมคนที่1", "#06b6d4"),
            ("เพื่อนบ้านใจดี", "#10b981"),
            ("แขกไม่ได้รับเชิญ", "#f59e0b"),
            ("นักเล่นเกมโปร", "#ef4444"),
        ]
        plain_msgs = [
            "สวัสดีครับ รับชมถ่ายทอดสดครับ",
            "เล่นเกมเก่งจังเลย!",
            "ขอเพลงหน่อยครับ 🎵",
            "เมื่อคืนนอนกี่โมงเหรอครับ",
            "เจ๋งมากครับ กดติดตามแล้วนะ",
            "รักเลย ❤️🔥✨🎉",
        ]
        # pool ของข้อความตัวอย่างทุกประเภท — สุ่มเลือก 1 อันต่อการกด
        long_msg = (
            "อยากให้สตรีมยาวๆ หน่อยครับ วันนี้มาเล่นเกมใหม่ที่เพิ่งออก "
            "ดูน่าสนุกมากเลย กราฟิกสวยและเนื้อเรื่องน่าสนใจ รอติดตามต่อครับ"
        )
        pool = [
            {"kind": "plain", "text": random.choice(plain_msgs)},
            {"kind": "plain", "text": long_msg},
            {"kind": "twitch_emote", "text": "ดีครับ Kappa ทดสอบ emote",
             "raw": "ดีครับ Kappa ทดสอบ emote",
             "emotes": [{"id": 25, "name": "Kappa", "start": 7, "end": 12}]},
            {"kind": "twitch_emote", "text": "PogChamp เจ๋งมาก",
             "raw": "PogChamp เจ๋งมาก",
             "emotes": [{"id": 305954156, "name": "PogChamp", "start": 0, "end": 8}]},
            {"kind": "bits", "text": "สู้ๆ นะครับ", "amount": 100, "badge": "💰"},
            {"kind": "sub", "text": "", "badge": "⭐", "system": "สมัครสมาชิก!"},
        ]
        m = random.choice(pool)
        name, color = random.choice(names)
        data = {
            "type": "message",
            "platform": "twitch",
            "author": name,
            "text": m.get("text", ""),
            "system_text": m.get("system", ""),
            "event": "bits" if m["kind"] == "bits" else ("sub" if m["kind"] == "sub" else "message"),
            "amount": m.get("amount"),
            "badge": m.get("badge", ""),
            "color": color,
            "timestamp": ts(),
            "raw_text": m.get("raw", m.get("text", "")),
            "segments": [],
            "twitch_emotes": m.get("emotes", []),
            "sticker_url": "",
        }
        try:
            asyncio.run_coroutine_threadsafe(self._broadcast(data), self._loop)
        except Exception:  # noqa: BLE001
            pass

    def update_config(self, settings) -> None:
        """อัปเดต config (หลัง settings เปลี่ยน) + push config ใหม่ไป clients

        ใช้สำหรับเปลี่ยน font_size/emote_size/animation แบบสดโดยไม่ restart server
        """
        self.settings = settings
        if not self._started or not self._clients or self._loop is None:
            return
        config = self._build_config()
        try:
            asyncio.run_coroutine_threadsafe(
                self._broadcast({"type": "config", "config": config}), self._loop
            )
        except Exception:  # noqa: BLE001
            pass

    def reload_emotes(self) -> None:
        """push reload_emotes ไป browser — บังคับ reload ทุก emote image

        ใช้ตอน toggle animate/static เปลี่ยน เพื่อให้ emote ที่แสดงอยู่ refresh ทันที
        (เพิ่ม cache-busting query param → browser ขอใหม่จาก proxy)
        """
        if not self._started or not self._clients or self._loop is None:
            return
        try:
            asyncio.run_coroutine_threadsafe(
                self._broadcast({"type": "reload_emotes"}), self._loop
            )
        except Exception:  # noqa: BLE001
            pass

    def reload_page(self) -> None:
        """push eval_js: location.reload() ไป browser ทุกตัวที่เชื่อม WS อยู่

        ใช้ตอน app startup เพื่อบังคับ OBS Browser Source ที่ค้างไว้ reload หน้าใหม่
        กัน cache ค้าง → ข้อความไม่แสดง (client.html มี handler eval_js แล้ว)

        หมายเหตุ: ต้องเรียกหลัง clients reconnect WS แล้ว (delay ~2-3 วิหลัง start)
        """
        if not self._started or not self._clients or self._loop is None:
            return
        try:
            asyncio.run_coroutine_threadsafe(
                self._broadcast({"type": "eval_js", "js": "location.reload()"}), self._loop
            )
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ #
    # Serialization helpers
    # ------------------------------------------------------------------ #
    def _build_config(self) -> dict:
        """config สำหรับ overlay (client ใช้ render + apply CSS variables แบบสด)"""
        s = self.settings
        # theme CSS (mirror game_overlay_themes.py — ใช้ source เดียวกัน)
        try:
            from game_overlay_themes import get_theme_css
            theme = getattr(s, "overlay_theme", "default")
            custom_css = getattr(s, "overlay_custom_css", "")
            theme_css = get_theme_css(theme, custom_css)
        except Exception:
            theme = getattr(s, "overlay_theme", "default")
            theme_css = ""
            custom_css = getattr(s, "overlay_custom_css", "")
        # ★ merge per-mode config — อ่านค่าของ mode ปัจจุบัน (override flat settings)
        active_mode = getattr(s, "overlay_appearance_mode", "default")
        mode_cfgs = getattr(s, "overlay_mode_configs", {})
        mc = mode_cfgs.get(active_mode, {}) if isinstance(mode_cfgs, dict) else {}
        # helper: อ่านจาก mode config ก่อน ไม่มี → fallback flat settings
        def mcv(key, fallback):
            return mc.get(key, getattr(s, f"overlay_{key}", fallback))

        return {
            # พื้นฐาน (ใช้ค่าของ mode ปัจจุบัน)
            "font_size": mcv("font_size", 18),
            "emote_size": mcv("emote_size", 28),
            "animation": getattr(s, "overlay_animation", "fade"),
            "exit_animation": getattr(s, "overlay_exit_animation", "fade_out"),
            "max_messages": getattr(s, "overlay_max_messages", 20),
            "direction": getattr(s, "overlay_direction", "bottom"),
            # เนื้อหา
            "show_logo": getattr(s, "overlay_show_logo", True),
            "show_timestamp": getattr(s, "overlay_show_timestamp", False),
            # auto-hide
            "auto_hide": getattr(s, "overlay_auto_hide", False),
            "hide_after": getattr(s, "overlay_hide_after", 10.0),
            # ฟอนต์ + text styling (ใช้ค่าของ mode ปัจจุบัน)
            "font_family": mcv("font_family", "Kanit"),
            "font_weight": mcv("font_weight", "500"),
            "text_color": mcv("text_color", "#ffffff"),
            "text_stroke": mcv("text_stroke", False),
            "text_stroke_color": mcv("text_stroke_color", "#000000"),
            "text_stroke_width": mcv("text_stroke_width", 2),
            "text_shadow": mcv("text_shadow", True),
            "text_shadow_color": mcv("text_shadow_color", "#000000"),
            "text_shadow_blur": mcv("text_shadow_blur", 3),
            # ★ ส่งค่าทั้ง 4 modes แยกกัน (สำหรับ CSS vars ของแต่ละ mode)
            "mode_configs": {
                "default": mode_cfgs.get("default", {}),
                "theme": mode_cfgs.get("theme", {}),
                "special": mode_cfgs.get("special", {}),
                "character": mode_cfgs.get("character", {}),
            },
            # layout: inline (บรรทัดเดียว) | stacked (สองบรรทัด)
            "layout": getattr(s, "overlay_layout", "inline"),
            # กล่องข้อความ
            "box_enabled": getattr(s, "overlay_box_enabled", True),
            "box_bg_color": getattr(s, "overlay_box_bg_color", "#0a0e1a"),
            "box_bg_opacity": getattr(s, "overlay_box_bg_opacity", 0.55),
            "box_radius": getattr(s, "overlay_box_radius", 8),
            "box_border": getattr(s, "overlay_box_border", False),
            "box_border_color": getattr(s, "overlay_box_border_color", "#7c3aed"),
            "box_border_width": getattr(s, "overlay_box_border_width", 1),
            "box_shadow": getattr(s, "overlay_box_shadow", True),
            "box_blur": float(getattr(s, "overlay_box_blur", 0) or 0),
            # balloon mode → ปิด glow animation เสมอ (กันบัค)
            "box_glow": False if getattr(s, "overlay_balloon_mode", False) else getattr(s, "overlay_box_glow", False),
            "box_glow_color": getattr(s, "overlay_box_glow_color", "#7c3aed"),
            "box_width": getattr(s, "overlay_box_width", "fit"),
            "msg_spacing": getattr(s, "overlay_msg_spacing", 4.0),
            "msg_only": getattr(s, "overlay_msg_only", False),
            "balloon_mode": getattr(s, "overlay_balloon_mode", False),
            "balloon_hide_after": getattr(s, "overlay_balloon_hide_after", 5.0),
            "balloon_bg_opacity": getattr(s, "overlay_balloon_bg_opacity", 0.95),
            # Character Talk
            "character_mode": getattr(s, "overlay_character_mode", False),
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
            # theme + custom CSS (3-mode restructure)
            "theme": theme,
            "theme_css": theme_css,
            "custom_css": custom_css,
            # event colors
            "color_sub": getattr(s, "overlay_color_sub", "#22c55e"),
            "color_bits": getattr(s, "overlay_color_bits", "#f59e0b"),
            "color_donate": getattr(s, "overlay_color_donate", "#22c55e"),
            "color_system": getattr(s, "overlay_color_system", "#9ca3af"),
            # Translator — แสดงต้นฉบับ [xxx] ในวงเล็บ
            "show_original": getattr(s, "overlay_show_original", True),
            # Channel Points redemption — แสดง reward redemption
            "show_redeem": getattr(s, "overlay_show_redeem", True),
        }

    def _serialize_message(self, msg: ChatMessage) -> dict:
        """แปลง ChatMessage → JSON สำหรับ overlay render

        รวมข้อมูลทั้งหมดที่ overlay ต้องการ:
        - platform, author, timestamp, color, badge
        - segments (MyLive: text/emoji/emote-URL)
        - twitch emotes (offset-based → URL list)
        - sticker_url (MyLive sticker)
        """
        from datetime import datetime
        extra = msg.extra or {}
        # badge + color จาก event style (mirror EVENT_STYLE ใน GUI)
        event_badge = {
            "message": "", "bits": "💰", "superchat": "💎", "gift": "🎁",
            "sub": "⭐", "resub": "⭐", "subgift": "🎁", "raid": "🎯",
            "like": "❤️", "follow": "⭐", "share": "📤", "join": "👋",
        }.get(msg.event, "")
        # Twitch emotes → URL list (ใช้ proxy /emote/{id} แทน CDN ตรงๆ
        # เพื่อกัน CORS/block ใน OBS browser + ใช้ disk cache + v1 fallback)
        # TikTok / third-party emotes มี url ตรงๆ → ใช้ url นั้นเลย
        # third-party: เลือก url_animated (GIF) ถ้า overlay_animated_emotes=True
        #              ไม่งั้นใช้ url (static webp/png)
        want_animated = bool(getattr(self.settings, "overlay_animated_emotes", True))
        twitch_emotes = []
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
                # Twitch emote → proxy ผ่าน /emote/{id} (proxy จะเลือก static/animated ตาม setting)
                twitch_emotes.append({
                    "name": em.get("name", ""),
                    "url": f"/emote/{eid}",
                    "start": em.get("start", 0),
                    "end": em.get("end", 0),
                })
        # event color — map event type → user-configured color (ถ้า message ไม่มี color ของตัวเอง)
        msg_color = extra.get("color", "")
        if not msg_color:
            msg_color = self._get_event_color(msg.event, extra)
        return {
            "type": "message",
            "platform": msg.platform,
            "author": msg.author,
            "text": msg.text or "",
            "system_text": msg.system_text or "",
            "event": msg.event,
            "amount": msg.amount,
            "badge": event_badge,
            "color": msg_color,
            "timestamp": datetime.now().strftime("%H:%M"),
            "raw_text": extra.get("raw_text", ""),
            "segments": extra.get("segments", []),
            "twitch_emotes": twitch_emotes,
            "sticker_url": extra.get("sticker_url", ""),
            # Translation info (ส่งให้ browser render [original] ถ้าเปิด show_original)
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

    def _get_event_color(self, event: str, extra: dict) -> str:
        """คืนสี author ตาม event type — ใช้สีที่ผู้ใช้ตั้งใน settings"""
        s = self.settings
        sub_events = {"sub", "resub", "subgift", "membership", "follow"}
        bits_events = {"bits"}
        donate_events = {"superchat", "gift", "raid", "share"}
        system_events = {"system", "join"}
        if event in sub_events:
            return getattr(s, "overlay_color_sub", "#22c55e")
        elif event in bits_events:
            return getattr(s, "overlay_color_bits", "#f59e0b")
        elif event in donate_events:
            return getattr(s, "overlay_color_donate", "#22c55e")
        elif event in system_events:
            return getattr(s, "overlay_color_system", "#9ca3af")
        return ""  # message ทั่วไป → ไม่กำหนดสี (ใช้ default)

    def _read_overlay_html(self) -> str:
        """อ่าน overlay.html จากโฟลเดอร์ app"""
        path = os.path.join(get_base_dir(), "overlay.html")
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:  # noqa: BLE001
            # fallback: หน้าว่างพร้อม error message
            return (
                "<!doctype html><html><body style='background:transparent;"
                "color:#fff;font-family:sans-serif;padding:20px'>"
                "overlay.html not found</body></html>"
            )


# ---------------------------------------------------------------------- #
# Smoke test
# ---------------------------------------------------------------------- #
if __name__ == "__main__":
    import sys
    import time

    # สร้าง fake settings
    class FakeSettings:
        overlay_port = 8765
        overlay_font_size = 18
        overlay_emote_size = 28
        overlay_animation = "fade"
        overlay_max_messages = 20
        overlay_direction = "bottom"
        overlay_show_logo = True

    server = OverlayServer(FakeSettings())
    print(f"Starting overlay server on port {server.port}...")
    if server.start():
        print(f"✅ Server running at http://localhost:{server.port}")
        print("   Open this URL in a browser (or OBS Browser Source) to see overlay")
        print("   Press Ctrl+C to stop")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping...")
            server.stop()
            print("Stopped")
    else:
        print(f"❌ Failed: {server._start_error}")
        sys.exit(1)
