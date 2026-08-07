"""playroom_server.py — local HTTP + WebSocket server สำหรับ Playroom overlay

รับ trigger จาก chat (เช่น !fortune) → broadcast clip URL ไปยัง OBS browser source
เล่นวิดีโอสุ่มตาม weight ที่ user ตั้งไว้

Routes:
  GET /            → playroom.html (หน้าเว็บเล่นวิดีโอ)
  GET /ws          → WebSocket (รับ clip push)
  GET /clip/{name} → serve video file (mp4/webm/mov)
"""
from __future__ import annotations

import asyncio
import os
import threading
from typing import Optional


def _get_base_dir() -> str:
    """หา base directory — รองรับ PyInstaller bundle"""
    if getattr(os.sys, "frozen", False):
        if hasattr(os.sys, "_MEIPASS"):
            return os.sys._MEIPASS
        return os.path.dirname(os.sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


class PlayroomServer:
    """local HTTP + WebSocket server สำหรับ Playroom overlay (มินิเกมวิดีโอ)"""

    def __init__(self, settings) -> None:
        self.settings = settings
        self.port = getattr(settings, "playroom_port", 8766)
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
        if self._started:
            return True
        self._stop_event.clear()
        self._start_error = None
        self._thread = threading.Thread(
            target=self._run, name="PlayroomServer", daemon=True
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
        app.router.add_get("/ws", self._handle_ws)
        app.router.add_get("/clip/{name}", self._handle_clip)

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
        if self._thread is not None:
            self._thread.join(timeout=3)
        self._clients.clear()

    @property
    def is_running(self) -> bool:
        return self._started

    # ------------------------------------------------------------------ #
    # HTTP handlers
    # ------------------------------------------------------------------ #
    async def _handle_index(self, request):
        import aiohttp.web as web
        html = self._read_playroom_html()
        return web.Response(text=html, content_type="text/html")

    async def _handle_ws(self, request):
        import aiohttp.web as web
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self._clients.add(ws)
        try:
            async for _ in ws:
                pass
        finally:
            self._clients.discard(ws)
        return ws

    async def _handle_clip(self, request):
        """serve media file (video/image) — path-traversal guarded

        ค้น clip name ในทุก trigger ของ playroom_triggers
        รองรับทั้งวิดีโอ (.mp4/.webm/.mov/.ogv) และภาพ (.png/.jpg/.gif/.webp/.bmp/.svg)
        """
        import aiohttp.web as web
        name = request.match_info.get("name", "")
        if not name:
            return web.Response(status=404, text="not found")
        # หา clip path จาก settings.playroom_triggers (ค้นในทุก trigger)
        triggers = getattr(self.settings, "playroom_triggers", [])
        clip_path = ""
        for trig in triggers:
            if not isinstance(trig, dict):
                continue
            for clip in trig.get("clips", []):
                if isinstance(clip, dict) and clip.get("name") == name:
                    clip_path = clip.get("path", "")
                    break
            if clip_path:
                break
        if not clip_path:
            return web.Response(status=404, text="clip not found")
        # resolve relative path (เช่น "media/good.mp4") → absolute (ข้าง base dir)
        if not os.path.isabs(clip_path):
            base = _get_base_dir()
            clip_path = os.path.join(base, clip_path)
            # fallback: ถ้าไม่เจอ → ลอง media/ เดิม (dev mode)
            if not os.path.isfile(clip_path):
                clip_path = os.path.join(base, clip_path.replace("playroom/media/", "media/", 1))
        if not os.path.isfile(clip_path):
            return web.Response(status=404, text="clip file not found")
        # กัน path traversal
        abs_path = os.path.abspath(clip_path)
        if ".." in name:
            return web.Response(status=403, text="forbidden")
        # content type ตามนามสกุล — รองรับทั้งวิดีโอและภาพ
        ext = os.path.splitext(clip_path)[1].lower()
        ctype = {
            # video
            ".mp4": "video/mp4",
            ".webm": "video/webm",
            ".mov": "video/quicktime",
            ".ogv": "video/ogg",
            ".avi": "video/x-msvideo",
            ".mkv": "video/x-matroska",
            # image
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
            ".svg": "image/svg+xml",
        }.get(ext, "application/octet-stream")
        return web.FileResponse(abs_path, headers={"Content-Type": ctype})

    def _read_playroom_html(self) -> str:
        """อ่าน playroom.html — fallback ถ้าไม่มีไฟล์"""
        path = os.path.join(_get_base_dir(), "playroom.html")
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:  # noqa: BLE001
            return (
                "<!doctype html><html><body style='background:transparent'>"
                "<p style='color:white'>playroom.html not found</p>"
                "</body></html>"
            )

    # ------------------------------------------------------------------ #
    # Push clip (เรียกจาก UI thread)
    # ------------------------------------------------------------------ #
    def push_clip(self, clip_name: str) -> None:
        """broadcast clip URL ไปยัง OBS browser → เล่นวิดีโอ"""
        if not self._started or not self._clients or self._loop is None:
            return
        url = f"/clip/{clip_name}"
        data = {"type": "clip", "url": url, "name": clip_name}
        try:
            asyncio.run_coroutine_threadsafe(self._broadcast(data), self._loop)
        except Exception:  # noqa: BLE001
            pass

    async def _broadcast(self, data: dict) -> None:
        dead = set()
        for ws in self._clients:
            try:
                await ws.send_json(data)
            except Exception:  # noqa: BLE001
                dead.add(ws)
        self._clients -= dead
