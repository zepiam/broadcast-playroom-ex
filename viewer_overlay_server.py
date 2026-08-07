"""viewer_overlay_server.py — local HTTP + WebSocket server สำหรับ Viewer Overlay

Server เล็กๆ (แยกจาก Game Overlay) — แสดงยอดคนดูบนจอ

Routes:
  GET /             → viewer_overlay.html
  GET /config       → JSON config (viewer_overlay_* settings)
  GET /logo/{plat}  → platform logo (assets/{plat}.png)
  WS  /ws           → WebSocket (push viewer counts + config updates)
"""
from __future__ import annotations

import asyncio
import os
import threading
from typing import Optional

from aiohttp import web, WSMsgType

from settings import get_base_dir


class ViewerOverlayServer:
    """aiohttp server สำหรับ Viewer Overlay — ทำงานใน daemon thread ของตัวเอง"""

    def __init__(self, settings, port: int = 8790) -> None:
        self.settings = settings
        self.port = port
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self._clients: set = set()
        self._started = False
        self._start_error: Optional[str] = None

    # ── lifecycle ──
    def start(self) -> bool:
        self._thread = threading.Thread(target=self._run, daemon=True, name="viewer-overlay-server")
        self._thread.start()
        # รอ start (max 3 วิ)
        for _ in range(30):
            if self._started or self._start_error:
                break
            threading.Event().wait(0.1)
        return self._started

    def stop(self) -> None:
        if self._loop and self._loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop).result(timeout=2)
            except Exception:
                pass
        self._started = False

    async def _shutdown(self) -> None:
        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()
        self._loop.stop()

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._setup())
            self._loop.run_forever()
        except Exception as e:
            self._start_error = str(e)
        finally:
            try:
                self._loop.close()
            except Exception:
                pass

    async def _setup(self) -> None:
        app = web.Application()
        app.router.add_get("/", self._handle_index)
        app.router.add_get("/config", self._handle_config)
        app.router.add_get("/logo/{platform}", self._handle_logo)
        app.router.add_get("/ws", self._handle_ws)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, "127.0.0.1", self.port)
        try:
            await self._site.start()
            self._started = True
        except OSError as e:
            self._start_error = f"port {self.port} ไม่ว่าง: {e}"

    # ── routes ──
    async def _handle_index(self, request):
        path = os.path.join(get_base_dir(), "viewer_overlay.html")
        if os.path.exists(path):
            return web.FileResponse(path)
        return web.Response(status=404, text="viewer_overlay.html not found")

    async def _handle_config(self, request):
        return web.json_response(self._build_config())

    async def _handle_logo(self, request):
        platform = request.match_info.get("platform", "")
        if not platform.replace("-", "").replace("_", "").isalnum():
            return web.Response(status=400, text="bad platform")
        path = os.path.join(get_base_dir(), "assets", f"{platform}.png")
        if os.path.exists(path):
            return web.FileResponse(path, headers={"Cache-Control": "max-age=3600"})
        return web.Response(status=404, text="logo not found")

    async def _handle_ws(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self._clients.add(ws)
        # ส่ง config ทันทีตอน connect
        try:
            await ws.send_json({"type": "config", "config": self._build_config()})
        except Exception:
            pass
        try:
            async for msg in ws:
                if msg.type == WSMsgType.ERROR:
                    break
        except Exception:
            pass
        finally:
            self._clients.discard(ws)
        return ws

    # ── push (เรียกจาก Tk thread) ──
    async def _broadcast(self, data: dict) -> None:
        dead = set()
        for ws in list(self._clients):
            try:
                await ws.send_json(data)
            except Exception:
                dead.add(ws)
        self._clients -= dead

    def push_viewer_counts(self, total: int, platforms: dict) -> None:
        if not self._started or not self._clients or self._loop is None:
            return
        data = {"type": "viewers", "total": int(total or 0), "platforms": platforms or {}}
        try:
            asyncio.run_coroutine_threadsafe(self._broadcast(data), self._loop)
        except Exception:
            pass

    def update_config(self, settings) -> None:
        self.settings = settings
        if not self._started or not self._clients or self._loop is None:
            return
        config = self._build_config()
        try:
            asyncio.run_coroutine_threadsafe(
                self._broadcast({"type": "config", "config": config}), self._loop,
            )
        except Exception:
            pass

    def _build_config(self) -> dict:
        s = self.settings
        return {
            "mode": getattr(s, "viewer_overlay_mode", "off"),
            "align": getattr(s, "viewer_overlay_align", "center"),
            "icon_size": getattr(s, "viewer_overlay_icon_size", 24),
            "font_size": getattr(s, "viewer_overlay_font_size", 18),
            "font_color": getattr(s, "viewer_overlay_font_color", "#ffffff"),
            "font_family": getattr(s, "game_overlay_font_family", "Kanit"),
            "font_weight": getattr(s, "game_overlay_font_weight", "700"),
            "text_stroke": getattr(s, "viewer_overlay_text_stroke", True),
            "text_stroke_color": getattr(s, "viewer_overlay_text_stroke_color", "#000000"),
            "text_stroke_width": getattr(s, "viewer_overlay_text_stroke_width", 2),
            "text_shadow": getattr(s, "viewer_overlay_text_shadow", True),
            "text_shadow_color": getattr(s, "viewer_overlay_text_shadow_color", "#000000"),
            "text_shadow_blur": getattr(s, "viewer_overlay_text_shadow_blur", 3),
        }
