"""composer_server.py — Canvas Overlay Composer server

Server สำหรับ Composer overlay — 1 URL รวมทุก widget (chat/alert/viewer/clock)
ผู้ใช้ลาก widget จัดวางในหน้า editor (?edit=1) แล้วเอา URL เดียวใส่ OBS Browser Source

สถาปัตยกรรม: 1 aiohttp server + 1 HTML page + WS push (เหมือน viewer_overlay_server)
แยกอิสระจาก OBS overlay เดิม — ไม่ทำลายของเดิม ค่อยแทนที่ทีหลัง

Routes:
  GET /             → composer.html (overlay ปกติ ใส่ใน OBS)
  GET /editor       → composer.html?edit=1 (โหมด editor ลาก widget)
  GET /config       → JSON config (widget list + canvas size)
  POST /save        → รับ widget layout ใหม่จาก editor → เซฟลง settings
  GET /logo/{plat}  → platform logo
  WS  /ws           → WebSocket (push config, message, viewers, eval_js)
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
from typing import Optional

from aiohttp import web, WSMsgType

from settings import get_base_dir, resolve_character_default_image

logger = logging.getLogger("composer")
from game_overlay_themes import get_theme_css, get_theme_list


class ComposerServer:
    """aiohttp server สำหรับ Canvas Overlay Composer — ทำงานใน daemon thread"""

    def __init__(self, settings, port: int = 8801) -> None:
        self.settings = settings
        self.port = port
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self._clients: set = set()
        self._last_ask_state = None  # ★ ASK state ล่าสุด (ส่งให้ client ใหม่ที่เชื่อมมา)
        self._ask_demo_handles = []  # ★ ตัวจับเวลา demo auto-flow (vote→result→stop)
        # ★ chat widget clients แยกตาม widget_id (สำหรับ push config/message เฉพาะ widget)
        self._chat_widget_clients: dict[str, set] = {}
        # ★ playroom clients — รับเฉพาะ type:"clip" (ไม่ปนกับ composer/chat clients)
        # ★ เก็บแยกตาม widget_id เพื่อ push clip เฉพาะ widget ที่กำหนด
        #    key = widget_id ของ playroom widget, value = set ของ websocket
        #    key = "_all" สำหรับ client ที่ไม่ส่ง widget_id มา (backward compat)
        self._playroom_clients: dict = {}  # widget_id → set of ws
        self._started = False
        self._start_error: Optional[str] = None
        # ★ callback สำหรับ save widgets → parent_app จะ set เพื่อ persist ลง settings
        self.on_save_widgets = None
        # ★ callback สำหรับเปิด settings tab ของแอป (เช่น Playroom settings)
        self.on_open_playroom_settings = None
        # ★ callback สำหรับบันทึก playroom widget_ids (จาก composer settings modal checkbox)
        #    signature: on_save_playroom_triggers(trigger_codes_by_widget: dict[str, list[str]])
        #    key = widget_id, value = list ของ trigger code ที่ติ๊กไว้
        self.on_save_playroom_triggers = None

    # ── lifecycle ──
    def start(self) -> bool:
        self._thread = threading.Thread(target=self._run, daemon=True, name="composer-server")
        self._thread.start()
        # รอ start (max 3 วิ)
        for _ in range(30):
            if self._started or self._start_error:
                break
            threading.Event().wait(0.1)
        return self._started

    @property
    def is_running(self) -> bool:
        """★ composer server กำลังทำงานอยู่ไหม (ใช้ใน app_gui เพื่อเช็คก่อน push)"""
        return self._started and self._loop is not None and self._loop.is_running()

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
        from server_guard import make_origin_guard_middleware
        app = web.Application(middlewares=[make_origin_guard_middleware("composer")])
        app.router.add_get("/", self._handle_index)
        app.router.add_get("/editor", self._handle_editor)
        app.router.add_get("/config", self._handle_config)
        app.router.add_post("/save", self._handle_save)
        app.router.add_get("/export-profile", self._handle_export_profile)
        app.router.add_post("/import-profile", self._handle_import_profile)
        app.router.add_post("/upload-character-image", self._handle_upload_char_image)
        app.router.add_get("/demo", self._handle_demo)
        app.router.add_post("/demo-one", self._handle_demo_one)
        app.router.add_post("/ask-demo", self._handle_ask_demo)
        app.router.add_get("/chat-widget", self._handle_chat_widget)
        app.router.add_get("/chat-config", self._handle_chat_config)
        app.router.add_get("/character/{job}", self._handle_character_img)
        app.router.add_get("/emote/{emote_id}", self._handle_emote_simple)
        app.router.add_get("/logo/{platform}", self._handle_logo)
        app.router.add_post("/upload-widget-image", self._handle_upload_widget_image)
        app.router.add_post("/delete-widget-image", self._handle_delete_widget_image)
        app.router.add_get("/widget-image/{widget_id}/{image_id}", self._handle_widget_image)
        # ★ video widget — upload/serve (เหมือน image แต่เป็นวิดีโอ)
        app.router.add_post("/upload-widget-video", self._handle_upload_widget_video)
        app.router.add_get("/widget-video/{widget_id}/{video_id}", self._handle_widget_video)
        # ★ playroom widget — serve playroom.html + clips ผ่าน composer (ไม่ต้องเปิด port แยก)
        app.router.add_get("/playroom-widget", self._handle_playroom_widget)
        app.router.add_get("/clip/{name}", self._handle_clip)
        app.router.add_get("/playroom-test", self._handle_playroom_test)
        # ★ POST — กัน GET-through-<img> CSRF (origin guard คุม POST แล้ว)
        app.router.add_post("/open-playroom-settings", self._handle_open_playroom_settings)
        # ★ save playroom widget trigger selection (checkbox ใน composer settings modal)
        app.router.add_post("/save-playroom-triggers", self._handle_save_playroom_triggers)
        # ★ now_playing widget — serve album cover จาก np_cache
        app.router.add_get("/now-playing-art", self._handle_now_playing_art)
        app.router.add_get("/now-playing-state", self._handle_now_playing_state)
        # ★ avatar widget — TTS speaking state (สำหรับ client reconnect)
        app.router.add_get("/avatar-state", self._handle_avatar_state)
        # ★ avatar preset — serve bundled avatar images (man/girl default)
        app.router.add_get("/avatar-preset/{name}/{role}", self._handle_avatar_preset)
        # ★ donate goal state (reconnect recovery)
        app.router.add_get("/donate-goal-state", self._handle_donate_goal_state)
        # ★ easydonate API key test
        app.router.add_post("/easydonate-test", self._handle_easydonate_test)
        # ★ mic devices list (Python sounddevice — แก้ OBS Browser Source ไม่เข้าถึงไมค์)
        app.router.add_get("/mic-devices", self._handle_mic_devices)
        # ★ mic level polling (สำหรับ settings meter — กัน WS หลุด)
        app.router.add_get("/mic-level", self._handle_mic_level)
        app.router.add_get("/ws", self._handle_ws)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        # ★ ลอง port ที่ตั้งค่าไว้ก่อน → ถ้าไม่ว่าง ลอง port ถัดไปสูงสุด 10 port
        #   กันปัญหา port ชนกับโปรแกรมอื่น (เช่น Discord, streaming apps)
        start_port = self.port
        for attempt in range(10):
            port_try = start_port + attempt
            self._site = web.TCPSite(self._runner, "127.0.0.1", port_try)
            try:
                await self._site.start()
                self.port = port_try  # ★ อัปเดต port จริงที่ใช้
                self._started = True
                if attempt > 0:
                    logger.info(f"Composer server: port {start_port} ไม่ว่าง → ใช้ port {port_try} แทน")
                return
            except OSError:
                continue
        self._start_error = f"ไม่สามารถเปิด composer server ได้ (port {start_port}-{start_port+9} ไม่ว่างทั้งหมด)"

    # ── routes ──
    async def _handle_index(self, request):
        """serve composer.html (overlay ปกติ ใส่ใน OBS)
        ★ gzip ถ้า client รองรับ — ลด 467KB → ~100KB (OBS โหลดเร็วขึ้นมาก)
        """
        html = self._read_composer_html()
        body = html.encode('utf-8')
        ae = request.headers.get('Accept-Encoding', '')
        if 'gzip' in ae and len(body) > 1024:
            import gzip as _gz
            compressed = _gz.compress(body, 6)
            if len(compressed) < len(body) * 0.9:
                return web.Response(
                    body=compressed,
                    headers={
                        "Content-Type": "text/html; charset=utf-8",
                        "Content-Encoding": "gzip",
                        "Vary": "Accept-Encoding",
                        "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
                        "Pragma": "no-cache",
                        "Expires": "0",
                    },
                )
        return web.Response(
            body=body,
            headers={
                "Content-Type": "text/html; charset=utf-8",
                "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

    async def _handle_editor(self, request):
        """redirect ไป composer.html?edit=1 (โหมด editor ลาก widget)"""
        # ★ cache-bust: เพิ่ม timestamp ใน URL → browser โหลดใหม่เสมอ (กัน cache ค้าง)
        raise web.HTTPFound(f"/?edit=1&_t={int(__import__('time').time())}")

    @staticmethod
    def _no_cache_headers() -> dict:
        """headers สำหรับกัน cache ทุกประเภท (กว่า no-cache เดี่ยว)"""
        return {
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        }

    async def _handle_config(self, request):
        return web.json_response(self._build_config())

    async def _handle_save(self, request):
        """รับ widget layout ใหม่จาก editor → เซฟผ่าน callback → push config ใหม่"""
        try:
            data = await request.json()
            widgets = data.get("widgets", [])
            canvas_size = data.get("canvas_size")
        except Exception:
            return web.json_response({"ok": False, "error": "bad json"}, status=400)

        # ป้องกันข้อมุลผิดรูปแบบ — validate พื้นฐาน
        clean_widgets = []
        valid_types = {"chat", "alert", "viewer", "clock", "image", "playroom", "webcam", "text", "video", "now_playing", "emote_party", "avatar", "donate_goal", "ask"}
        for i, w in enumerate(widgets if isinstance(widgets, list) else []):
            if not isinstance(w, dict):
                continue
            wt = str(w.get("type", ""))
            if wt not in valid_types:
                continue

            # ★ dg_api_key — config ที่ broadcast เป็น "__MASKED__" (กันรั่วผ่าน /config + WS)
            #   ถ้า client ส่งกลับมาเป็น masked หรือว่าง → คงค่าเดิมจาก settings (แก้ไขค่าอื่นได้โดยไม่ทำ key หาย)
            _dg_key_final = ""
            if wt == "donate_goal":
                _dg_key_raw = str(w.get("dg_api_key", "") or "").strip()
                if _dg_key_raw and _dg_key_raw != "__MASKED__":
                    _dg_key_final = _dg_key_raw
                else:
                    _wid = str(w.get("id", ""))
                    for _ow in (getattr(self.settings, "composer_widgets", None) or []):
                        if isinstance(_ow, dict) and _ow.get("id") == _wid:
                            _dg_key_final = str(_ow.get("dg_api_key", "") or "")
                            break

            clean_widgets.append({
                "id": str(w.get("id", f"w{i}")),
                "type": wt,
                "name": str(w.get("name", "")),
                "x": int(w.get("x", 0)),
                "y": int(w.get("y", 0)),
                "w": max(50, int(w.get("w", 300))),
                "h": max(30, int(w.get("h", 200))),
                "z": int(w.get("z", 1)),
                "url": str(w.get("url", "")) if wt == "alert" else "",
                "alpha": max(0.0, min(1.0, float(w.get("alpha", 1.0)))),
                "content_opacity": max(0.0, min(1.0, float(w.get("content_opacity", 1.0)))),
                "enabled": bool(w.get("enabled", True)),
                # ── per-widget style (optional — ใช้ตาม type) ──
                # chat/viewer/clock: font_size, font_color, font_weight,
                #                   text_stroke (bool), text_stroke_color, text_stroke_width
                # chat: bg_color, bg_opacity, max_messages
                # clock: format ("HH:MM" | "HH:MM:SS")
                "font_size": int(w.get("font_size", 16)) if wt != "alert" else 16,
                "font_family": str(w.get("font_family", "Kanit")) if wt == "chat" else "Kanit",
                "font_color": str(w.get("font_color", "#ffffff")),
                "font_weight": str(w.get("font_weight", "600")),
                "text_stroke": bool(w.get("text_stroke", True)),
                "text_stroke_type": str(w.get("text_stroke_type", "inner")),
                "text_stroke_color": str(w.get("text_stroke_color", "#000000")),
                "text_stroke_width": int(w.get("text_stroke_width", 2)),
                "text_shadow": bool(w.get("text_shadow", True)) if wt == "chat" else True,
                "text_shadow_color": str(w.get("text_shadow_color", "#000000")),
                "text_shadow_blur": int(w.get("text_shadow_blur", 3)),
                "bg_color": str(w.get("bg_color", "#0a0e1a")) if wt == "chat" else "#0a0e1a",
                "bg_opacity": max(0.0, min(1.0, float(w.get("bg_opacity", 0.0)))) if wt == "chat" else 0.0,
                "max_messages": int(w.get("max_messages", 30)) if wt == "chat" else 30,
                "clock_format": str(w.get("clock_format", "HH:MM")) if wt == "clock" else "HH:MM",
                # ── chat-specific (ย้ายจาก overlay_* settings เดิม) ──
                "layout": str(w.get("layout", "inline")) if wt == "chat" else "inline",
                "direction": str(w.get("direction", "bottom")) if wt == "chat" else "bottom",
                "show_logo": bool(w.get("show_logo", True)) if wt == "chat" else True,
                "show_timestamp": bool(w.get("show_timestamp", False)) if wt == "chat" else False,
                "animation": str(w.get("animation", "fade")) if wt == "chat" else "fade",
                "exit_animation": str(w.get("exit_animation", "fade_out")) if wt == "chat" else "fade_out",
                "auto_hide": bool(w.get("auto_hide", False)) if wt == "chat" else False,
                "hide_after": int(w.get("hide_after", 8)) if wt == "chat" else 8,
                "chat_align": str(w.get("chat_align", "left")) if wt == "chat" else "left",
                # ── chat appearance mode + theme (iframe overlay.html reuse) ──
                "appearance_mode": str(w.get("appearance_mode", "default")) if wt == "chat" else "default",
                "theme": str(w.get("theme", "default")) if wt == "chat" else "default",
                "custom_css": str(w.get("custom_css", "")) if wt == "chat" else "",
                "custom_css_enabled": bool(w.get("custom_css_enabled", False)) if wt == "chat" else False,
                "emote_size": int(w.get("emote_size", 28)) if wt == "chat" else 28,
                # ── box settings (default + theme modes) ──
                "box_enabled": bool(w.get("box_enabled", True)) if wt == "chat" else True,
                "box_width": str(w.get("box_width", "fit")) if wt == "chat" else "fit",
                "box_radius": int(w.get("box_radius", 8)) if wt == "chat" else 8,
                "box_padding": max(0, min(40, int(w.get("box_padding", 8)))) if wt == "chat" else 8,
                "chat_padding": max(0, min(60, int(w.get("chat_padding", 12)))) if wt == "chat" else 12,
                "msg_spacing": max(0, min(30, int(w.get("msg_spacing", 4)))) if wt == "chat" else 4,
                "box_border": bool(w.get("box_border", False)) if wt == "chat" else False,
                "box_border_color": str(w.get("box_border_color", "#ffffff")),
                "box_border_width": int(w.get("box_border_width", 1)) if wt == "chat" else 1,
                "box_shadow": bool(w.get("box_shadow", True)) if wt == "chat" else True,
                "box_glow": bool(w.get("box_glow", False)) if wt == "chat" else False,
                "box_glow_color": str(w.get("box_glow_color", "#a855f7")),
                # ── balloon settings (mode=balloon) ──
                "balloon_hide_after": int(w.get("balloon_hide_after", 5)) if wt == "chat" else 5,
                # ── danmaku slider settings (mode=slider) ──
                "slider_font_family": str(w.get("slider_font_family", "Kanit")) if wt == "chat" else "Kanit",
                "slider_font_weight": str(w.get("slider_font_weight", "700")) if wt == "chat" else "700",
                "slider_font_size": int(w.get("slider_font_size", 24)) if wt == "chat" else 24,
                "slider_text_color": str(w.get("slider_text_color", "#ffffff")) if wt == "chat" else "#ffffff",
                "slider_text_stroke": bool(w.get("slider_text_stroke", False)) if wt == "chat" else False,
                "slider_text_stroke_color": str(w.get("slider_text_stroke_color", "#000000")) if wt == "chat" else "#000000",
                "slider_text_stroke_width": int(w.get("slider_text_stroke_width", 2)) if wt == "chat" else 2,
                "slider_text_shadow": bool(w.get("slider_text_shadow", True)) if wt == "chat" else True,
                "slider_text_shadow_color": str(w.get("slider_text_shadow_color", "#000000")) if wt == "chat" else "#000000",
                "slider_text_shadow_blur": int(w.get("slider_text_shadow_blur", 3)) if wt == "chat" else 3,
                "slider_emote_size": int(w.get("slider_emote_size", 28)) if wt == "chat" else 28,
                "slider_duration": float(w.get("slider_duration", 5)) if wt == "chat" else 5,
                "slider_show_logo": bool(w.get("slider_show_logo", True)) if wt == "chat" else True,
                "slider_lane_height": int(w.get("slider_lane_height", 40)) if wt == "chat" else 40,
                "slider_zone": str(w.get("slider_zone", "middle")) if wt == "chat" else "middle",
                "balloon_bg_opacity": max(0.1, min(1.0, float(w.get("balloon_bg_opacity", 0.95)))) if wt == "chat" else 0.95,
                "balloon_font_size": int(w.get("balloon_font_size", 18)) if wt == "chat" else 18,
                "balloon_text_color": str(w.get("balloon_text_color", "#1a1a2e")) if wt == "chat" else "#1a1a2e",
                "balloon_font_family": str(w.get("balloon_font_family", "Kanit")) if wt == "chat" else "Kanit",
                "balloon_font_weight": str(w.get("balloon_font_weight", "600")) if wt == "chat" else "600",
                "balloon_emote_size": int(w.get("balloon_emote_size", 28)) if wt == "chat" else 28,
                # ── character talk settings (mode=character) ──
                "character_bubble_width": int(w.get("character_bubble_width", 500)) if wt == "chat" else 500,
                "character_size": int(w.get("character_size", 120)) if wt == "chat" else 120,
                "character_hide_after": float(w.get("character_hide_after", 6)) if wt == "chat" else 6,
                "character_max_on_screen": int(w.get("character_max_on_screen", 8)) if wt == "chat" else 8,
                "character_font_family": str(w.get("character_font_family", "Kanit")) if wt == "chat" else "Kanit",
                "character_font_weight": str(w.get("character_font_weight", "600")) if wt == "chat" else "600",
                "character_font_color": str(w.get("character_font_color", "#1a1a2e")) if wt == "chat" else "#1a1a2e",
                "character_stroke": bool(w.get("character_stroke", False)) if wt == "chat" else False,
                "character_stroke_width": int(w.get("character_stroke_width", 2)) if wt == "chat" else 2,
                "character_stroke_color": str(w.get("character_stroke_color", "#000000")) if wt == "chat" else "#000000",
                "character_shadow": bool(w.get("character_shadow", False)) if wt == "chat" else False,
                "character_shadow_blur": int(w.get("character_shadow_blur", 3)) if wt == "chat" else 3,
                "character_shadow_color": str(w.get("character_shadow_color", "#000000")) if wt == "chat" else "#000000",
                "character_emote_size": int(w.get("character_emote_size", 28)) if wt == "chat" else 28,
                "character_name_font_family": str(w.get("character_name_font_family", "Kanit")) if wt == "chat" else "Kanit",
                "character_name_font_weight": str(w.get("character_name_font_weight", "600")) if wt == "chat" else "600",
                "character_name_color": str(w.get("character_name_color", "#ffffff")) if wt == "chat" else "#ffffff",
                "character_random_pos": bool(w.get("character_random_pos", True)) if wt == "chat" else True,
                "character_name_size": int(w.get("character_name_size", 11)) if wt == "chat" else 11,
                "character_name_stroke": bool(w.get("character_name_stroke", True)) if wt == "chat" else True,
                "character_name_stroke_color": str(w.get("character_name_stroke_color", "#000000")),
                "character_name_stroke_width": int(w.get("character_name_stroke_width", 1)) if wt == "chat" else 1,
                "character_name_shadow": bool(w.get("character_name_shadow", True)) if wt == "chat" else True,
                "character_name_shadow_color": str(w.get("character_name_shadow_color", "#000000")),
                "character_name_shadow_blur": int(w.get("character_name_shadow_blur", 2)) if wt == "chat" else 2,
                "character_show_name": bool(w.get("character_show_name", True)) if wt == "chat" else True,
                "character_show_logo": bool(w.get("character_show_logo", True)) if wt == "chat" else True,
                # ── webcam frame widget ──
                "webcam_ratio": str(w.get("webcam_ratio", "16:9")) if wt == "webcam" else "16:9",
                "webcam_theme": str(w.get("webcam_theme", "simple-white")) if wt == "webcam" else "simple-white",
                "webcam_border_width": max(0, int(w.get("webcam_border_width", 4))) if wt == "webcam" else 4,
                # ── text widget ──
                "text_content": str(w.get("text_content", "")) if wt == "text" else "",
                "text_mode": str(w.get("text_mode", "static")) if wt == "text" else "static",
                "text_interval": max(1, int(w.get("text_interval", 10))) if wt == "text" else 10,
                "text_interval_unit": str(w.get("text_interval_unit", "seconds")) if wt == "text" else "seconds",
                "text_align": str(w.get("text_align", "center")) if wt == "text" else "center",
                "text_scroll_speed": max(1, min(20, int(w.get("text_scroll_speed", 10)))) if wt == "text" else 10,
                "text_scroll_delay": max(1, min(30, float(w.get("text_scroll_delay", 2)))) if wt == "text" else 2,
                "text_theme": str(w.get("text_theme", "default")) if wt == "text" else "default",
                # ── text widget background ──
                "text_bg_enabled": bool(w.get("text_bg_enabled", False)) if wt == "text" else False,
                "text_bg_color": str(w.get("text_bg_color", "#1a1a2e")) if wt == "text" else "#1a1a2e",
                "text_bg_opacity": max(0.0, min(1.0, float(w.get("text_bg_opacity", 1.0)))) if wt == "text" else 1.0,
                "text_bg_radius": max(0, min(30, int(w.get("text_bg_radius", 8)))) if wt == "text" else 8,
                # ── video widget (เหมือน image widget แต่เป็นวิดีโอ loop) ──
                "video_url": str(w.get("video_url", "")) if wt == "video" else "",
                # ── color key (playroom + video) — chroma key ตัดสีพื้นหลัง ──
                "ck_enabled": bool(w.get("ck_enabled", False)) if wt in ("playroom", "video") else False,
                "ck_color": str(w.get("ck_color", "#00ff00")) if wt in ("playroom", "video") else "#00ff00",
                "ck_similarity": max(0, min(100, int(w.get("ck_similarity", 50)))) if wt in ("playroom", "video") else 50,
                "ck_smoothness": max(0, min(100, int(w.get("ck_smoothness", 30)))) if wt in ("playroom", "video") else 30,
                # ── clock themes + date settings ──
                "clock_theme": str(w.get("clock_theme", "default")) if wt == "clock" else "default",
                "clock_style": str(w.get("clock_style", "none")) if wt == "clock" else "none",
                # ── clock opacity แยกตามโหมด (Style vs Theme) ──
                "style_opacity": float(w.get("style_opacity", 1.0)) if wt == "clock" else 1.0,
                "theme_opacity": float(w.get("theme_opacity", 1.0)) if wt == "clock" else 1.0,
                "show_date": bool(w.get("show_date", False)) if wt == "clock" else False,
                "date_format": str(w.get("date_format", "short")) if wt == "clock" else "short",
                "date_lang": str(w.get("date_lang", "th")) if wt == "clock" else "th",
                "date_font_size": int(w.get("date_font_size", 14)) if wt == "clock" else 14,
                "date_color": str(w.get("date_color", "#cccccc")),
                "time_color": str(w.get("time_color", "#ffffff")),
                # ── balloon emote size ──
                "balloon_emote_size": int(w.get("balloon_emote_size", 28)) if wt == "chat" else 28,
                # ── viewer widget settings ──
                "ask_bar_style": str(w.get("ask_bar_style", "classic")) if wt == "ask" else "classic",
                "ask_frame_style": str(w.get("ask_frame_style", "classic")) if wt == "ask" else "classic",
                "ask_countdown_style": str(w.get("ask_countdown_style", "text")) if wt == "ask" else "text",
                "ask_layout": str(w.get("ask_layout", "vright")
                                  if w.get("ask_layout") in ("vleft", "vright", "hband", "minimal", "card", "bar", "tower")
                                  else "vright") if wt == "ask" else "vright",
                "ask_extend_pct": max(20, min(30, int(w.get("ask_extend_pct", 20) or 20))) if wt == "ask" else 20,
                "ask_min_width": max(220, min(700, int(w.get("ask_min_width", 340) or 340))) if wt == "ask" else 340,
                "ask_pos_x": max(5, min(95, int(w.get("ask_pos_x", 85) or 85))) if wt == "ask" else 85,
                "ask_pos_y": max(5, min(95, int(w.get("ask_pos_y", 12) or 12))) if wt == "ask" else 12,
                "ask_opacity_pct": max(10, min(100, int(w.get("ask_opacity_pct", 100) or 100))) if wt == "ask" else 100,
                "ask_question_fs": max(12, min(60, int(w.get("ask_question_fs", 24) or 24))) if wt == "ask" else 24,
                "ask_choice_fs": max(10, min(40, int(w.get("ask_choice_fs", 18) or 18))) if wt == "ask" else 18,
                "ask_anchor": ("bottom" if str(w.get("ask_anchor", "top")) in ("bottom", "bl", "br", "center") else "top") if wt == "ask" else "top",
                "ask_theme": str(w.get("ask_theme", "violet")) if wt == "ask" else "violet",
                "ask_scale": max(0.5, min(2.0, float(w.get("ask_scale", 1.0) or 1.0))) if wt == "ask" else 1.0,
                "ask_anim_in": str(w.get("ask_anim_in", "fade")) if wt == "ask" else "fade",
                "ask_anim_out": str(w.get("ask_anim_out", "fade")) if wt == "ask" else "fade",
                "ask_anim_in_ms": max(200, min(5000, int(w.get("ask_anim_in_ms", w.get("ask_anim_ms", 1200)) or 1200))) if wt == "ask" else 1200,
                "ask_anim_out_ms": max(200, min(5000, int(w.get("ask_anim_out_ms", w.get("ask_anim_ms", 1200)) or 1200))) if wt == "ask" else 1200,
                "viewer_mode": str(w.get("viewer_mode", "both")) if wt == "viewer" else "both",
                "viewer_show_icon": bool(w.get("viewer_show_icon", True)) if wt == "viewer" else True,
                "viewer_theme": str(w.get("viewer_theme", "default")) if wt == "viewer" else "default",
                "viewer_icon_size": int(w.get("viewer_icon_size", 20)) if wt == "viewer" else 20,
                "viewer_align": str(w.get("viewer_align", "left")) if wt == "viewer" else "left",
                "viewer_direction": str(w.get("viewer_direction", "horizontal")) if wt == "viewer" else "horizontal",
                # ── image & slideshow widget settings ──
                "images": [dict(img) for img in w.get("images", [])] if (wt == "image" and isinstance(w.get("images", []), list)) else [],
                "slide_interval": max(1, int(w.get("slide_interval", 10))) if wt == "image" else 10,
                "slide_interval_unit": str(w.get("slide_interval_unit", "seconds")) if wt == "image" else "seconds",
                "fit_mode": str(w.get("fit_mode", "cover")) if wt == "image" else "cover",
                "transition": str(w.get("transition", "fade")) if wt == "image" else "fade",
                "shuffle": bool(w.get("shuffle", False)) if wt == "image" else False,
                "image_mode": str(w.get("image_mode", "slideshow")) if wt == "image" else "slideshow",
                "timer_interval_sec": int(w.get("timer_interval_sec", 600)) if wt == "image" else 600,
                "timer_interval_unit": str(w.get("timer_interval_unit", "minutes")) if wt == "image" else "minutes",
                "timer_slide_duration": int(w.get("timer_slide_duration", 10)) if wt == "image" else 10,
                "timer_anim_in": str(w.get("timer_anim_in", "fade")) if wt == "image" else "fade",
                "timer_anim_out": str(w.get("timer_anim_out", "fade")) if wt == "image" else "fade",
                "timer_anim_in_ms": int(w.get("timer_anim_in_ms", 2000)) if wt == "image" else 2000,
                "timer_anim_out_ms": int(w.get("timer_anim_out_ms", 2000)) if wt == "image" else 2000,
                # ── now_playing widget settings ──
                "np_show_art": bool(w.get("np_show_art", True)) if wt == "now_playing" else True,
                "np_show_progress": bool(w.get("np_show_progress", True)) if wt == "now_playing" else True,
                "np_scroll_title": bool(w.get("np_scroll_title", True)) if wt == "now_playing" else True,
                "np_font_size": int(w.get("np_font_size", 14)) if wt == "now_playing" else 14,
                "np_artist_font_size": int(w.get("np_artist_font_size", 12)) if wt == "now_playing" else 12,
                "np_time_font_size": int(w.get("np_time_font_size", 10)) if wt == "now_playing" else 10,
                "np_text_color": str(w.get("np_text_color", "#ffffff")) if wt == "now_playing" else "#ffffff",
                "np_accent_color": str(w.get("np_accent_color", "#1db954")) if wt == "now_playing" else "#1db954",
                "np_bg_color": str(w.get("np_bg_color", "#1a1a2e")) if wt == "now_playing" else "#1a1a2e",
                "np_bg_opacity": max(0.0, min(1.0, float(w.get("np_bg_opacity", 1.0)))) if wt == "now_playing" else 1.0,
                "np_radius": int(w.get("np_radius", 8)) if wt == "now_playing" else 8,
                "np_art_radius": int(w.get("np_art_radius", 6)) if wt == "now_playing" else 6,
                "np_art_size": int(w.get("np_art_size", 48)) if wt == "now_playing" else 48,
                "np_sync_mode": str(w.get("np_sync_mode", "browser")) if wt == "now_playing" else "browser",
                "np_source": str(w.get("np_source", "auto")) if wt == "now_playing" else "auto",
                "np_theme": str(w.get("np_theme", "custom")) if wt == "now_playing" else "custom",
                "np_style": str(w.get("np_style", "flat")) if wt == "now_playing" else "flat",
                # ── emote_party widget settings ──
                "ep_animation": str(w.get("ep_animation", "float")) if wt == "emote_party" else "float",
                "ep_duration": max(1.0, min(30.0, float(w.get("ep_duration", 5.0)))) if wt == "emote_party" else 5.0,
                "ep_max_emotes": max(1, min(50, int(w.get("ep_max_emotes", 15)))) if wt == "emote_party" else 15,
                "ep_emote_size": max(20, min(200, int(w.get("ep_emote_size", 64)))) if wt == "emote_party" else 64,
                "ep_bg_color": str(w.get("ep_bg_color", "#0a0e1a")) if wt == "emote_party" else "#0a0e1a",
                "ep_bg_opacity": max(0.0, min(1.0, float(w.get("ep_bg_opacity", 0.0)))) if wt == "emote_party" else 0.0,
                "ep_emoji_enabled": bool(w.get("ep_emoji_enabled", True)) if wt == "emote_party" else True,
                # ── avatar widget settings (PNGTuber-style 4-image) ──
                # ★ 4 ภาพ: idle / talk / blink-idle / blink-talk
                #   blink กับ talk ทำงานอิสระ → กระพริบได้ขณะพูด (ตามมาตรฐาน PNGTuber)
                "avatar_mode": str(w.get("avatar_mode", "tts")) if wt == "avatar" else "tts",  # "tts" | "mic"
                # ★ avatar_preset: "man" | "girl" | "" (custom = อัพเอง)
                #   เมื่อเลือก preset → URL ทั้ง 4 จะถูก fill จาก /avatar-preset/{name}/{role}
                "avatar_preset": str(w.get("avatar_preset", "")) if wt == "avatar" else "",
                "avatar_idle_url": str(w.get("avatar_idle_url", "")) if wt == "avatar" else "",
                "avatar_talk_url": str(w.get("avatar_talk_url", "")) if wt == "avatar" else "",
                "avatar_blink_idle_url": str(w.get("avatar_blink_idle_url", "")) if wt == "avatar" else "",
                "avatar_blink_talk_url": str(w.get("avatar_blink_talk_url", "")) if wt == "avatar" else "",
                "avatar_fit_mode": str(w.get("avatar_fit_mode", "contain")) if wt == "avatar" else "contain",
                "avatar_blink_rate": max(1, min(10, int(w.get("avatar_blink_rate", 4)))) if wt == "avatar" else 4,
                # ★ mic threshold เป็น dB (-60 = เงียบมาก, 0 = เต็ม) — default -35 dB
                "avatar_mic_threshold": max(-60, min(0, int(w.get("avatar_mic_threshold", -35)))) if wt == "avatar" else -35,
                # ★ mic device — เก็บเป็น index (str สำหรับ serialize) จาก Python sounddevice
                #   ค่าว่าง = system default
                "avatar_mic_device": str(w.get("avatar_mic_device", "")) if wt == "avatar" else "",
                # ★ software gain — ขยายสัญญาณ dynamic mic (1-1000, default 100 = +40dB)
                "avatar_mic_gain": max(1, min(1000, int(w.get("avatar_mic_gain", 100)))) if wt == "avatar" else 100,
                "avatar_bounce": bool(w.get("avatar_bounce", True)) if wt == "avatar" else True,
                "avatar_breathing": bool(w.get("avatar_breathing", True)) if wt == "avatar" else True,
                "avatar_sway": bool(w.get("avatar_sway", True)) if wt == "avatar" else True,
                # ★ flip (mirror) — สะท้อนภาพแนวนอน/แนวตั้ง
                "avatar_flip_h": bool(w.get("avatar_flip_h", False)) if wt == "avatar" else False,
                "avatar_flip_v": bool(w.get("avatar_flip_v", False)) if wt == "avatar" else False,
                # ── donate_goal widget settings (EasyDonate API) ──
                "dg_api_key": _dg_key_final if wt == "donate_goal" else "",
                "dg_goal_amount": max(1, int(w.get("dg_goal_amount", 1000))) if wt == "donate_goal" else 1000,
                "dg_goal_title": str(w.get("dg_goal_title", "")) if wt == "donate_goal" else "",
                "dg_start_amount": max(0, int(w.get("dg_start_amount", 0))) if wt == "donate_goal" else 0,
                "dg_currency": str(w.get("dg_currency", "฿")) if wt == "donate_goal" else "฿",
                "dg_theme": str(w.get("dg_theme", "neon")) if wt == "donate_goal" else "neon",
                "dg_color_theme": str(w.get("dg_color_theme", "default")) if wt == "donate_goal" else "default",
                "dg_color_theme": str(w.get("dg_color_theme", "default")) if wt == "donate_goal" else "default",
                "dg_bar_color": str(w.get("dg_bar_color", "#10b981")) if wt == "donate_goal" else "#10b981",
                "dg_bg_color": str(w.get("dg_bg_color", "#1a1a2e")) if wt == "donate_goal" else "#1a1a2e",
                "dg_font_color": str(w.get("dg_font_color", "#e5e7eb")) if wt == "donate_goal" else "#e5e7eb",
                "dg_current_color": str(w.get("dg_current_color", "#10b981")) if wt == "donate_goal" else "#10b981",
                "dg_goal_color": str(w.get("dg_goal_color", "#9ca3af")) if wt == "donate_goal" else "#9ca3af",
                "dg_show_donor": bool(w.get("dg_show_donor", True)) if wt == "donate_goal" else True,
                "dg_amount_align": str(w.get("dg_amount_align", "left")) if wt == "donate_goal" else "left",
                "dg_title_align": str(w.get("dg_title_align", "left")) if wt == "donate_goal" else "left",
                "dg_font_size": int(w.get("dg_font_size", 16)) if wt == "donate_goal" else 16,
                "dg_opacity": max(0, min(100, int(w.get("dg_opacity", 100)))) if wt == "donate_goal" else 100,
                # ── common: ratio lock + widget scale (ทุก widget) ──
                "lock_ratio": bool(w.get("lock_ratio", False)),
                "widget_scale": max(0.2, min(3.0, float(w.get("widget_scale", 1.0)))),
            })

        # เรียง z-index ใหม่ตามลำดับที่ได้รับ (ตัวแรก = หลังสุด)
        for idx, w in enumerate(clean_widgets):
            w["z"] = idx + 1

        # เซฟผ่าน callback (parent_app จะ persist ลง settings)
        if self.on_save_widgets is not None:
            try:
                self.on_save_widgets(clean_widgets, canvas_size)
            except Exception:
                pass

        # push config ใหม่ให้ client ที่เชื่อม WS อยู่
        self.settings.composer_widgets = clean_widgets
        if canvas_size in ("720p", "1080p"):
            self.settings.composer_canvas_size = canvas_size
        # ★ sync character_jobs จาก client (ถ้าส่งมา)
        char_jobs = data.get("character_jobs")
        if isinstance(char_jobs, list):
            # validate basic shape + keep only name/image
            clean_jobs = []
            for cj in char_jobs:
                if isinstance(cj, dict) and cj.get("name"):
                    clean_jobs.append({
                        "name": str(cj["name"]),
                        "image": str(cj.get("image", "")),
                    })
            self.settings.character_jobs = clean_jobs
        # ★ sync character_default_image จาก client (ถ้าส่งมา)
        if "character_default_image" in data:
            self.settings.character_default_image = str(data.get("character_default_image") or "")
        # ★ persist settings ผ่าน callback
        if self.on_save_widgets is not None:
            try:
                self.on_save_widgets(clean_widgets, canvas_size)
            except Exception:
                pass
        await self._broadcast_safe({"type": "config", "config": self._build_config()})
        # ★ push config update เฉพาะ chat widget ที่เปลี่ยน (overlay.html iframe จะได้ refresh theme/mode)
        #    ★ เดย์ 100ms กัน race condition (broadcast config ทับ push widget config)
        import asyncio as _aio2
        await _aio2.sleep(0.1)
        for w in clean_widgets:
            if w.get("type") == "chat":
                await self._push_widget_config(w["id"])
        return web.json_response({"ok": True, "widgets": clean_widgets})

    async def _handle_export_profile(self, request):
        """GET /export-profile → ดาวน์โหลด layout เป็นไฟล์ JSON"""
        import datetime as _dt
        cfg = self._build_config()
        data = {
            "version": "1.0",
            "exported_at": _dt.datetime.now().isoformat(),
            "canvas_size": cfg.get("canvas_size", "1080p"),
            "canvas_w": cfg.get("canvas_w", 1920),
            "canvas_h": cfg.get("canvas_h", 1080),
            "widgets": cfg.get("widgets", []),
        }
        return web.json_response(data, headers={
            "Content-Disposition": 'attachment; filename="composer-profile.json"'
        })

    async def _handle_import_profile(self, request):
        """POST /import-profile → โหลด layout จาก JSON → apply + save"""
        try:
            data = await request.json()
            widgets = data.get("widgets", [])
            canvas_size = data.get("canvas_size", "1080p")
            # ★ apply widgets
            self._widgets = widgets
            self._canvas_size = canvas_size
            if canvas_size == "720p":
                self._canvas_w, self._canvas_h = 1280, 720
            else:
                self._canvas_w, self._canvas_h = 1920, 1080
            # ★ save
            if self.on_save_widgets is not None:
                try:
                    self.on_save_widgets(widgets, canvas_size)
                except Exception:
                    pass
            # ★ broadcast config ใหม่
            await self._broadcast_safe({"type": "config", "config": self._build_config()})
            for w in widgets:
                if w.get("type") == "chat":
                    await self._push_widget_config(w["id"])
            return web.json_response({"ok": True, "widgets": widgets})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=400)

    async def _handle_upload_char_image(self, request):
        """POST /upload-character-image — รับรูป (multipart form) เซฟลง cache dir

        รับ: job_name (form field) + image file
        คืน: {ok, path} — path สัมบูรณ์ของรูปที่เซฟแล้ว
        """
        import os as _os
        try:
            reader = await request.multipart()
            job_name = None
            image_data = None
            ext = ".png"
            while True:
                part = await reader.next()
                if part is None:
                    break
                if part.name == "job_name":
                    job_name = (await part.read()).decode("utf-8", errors="ignore").strip().lower()
                elif part.name == "image":
                    # ตรวจ extension จาก filename
                    fn = part.filename or ""
                    if fn.lower().endswith((".jpg", ".jpeg")):
                        ext = ".jpg"
                    elif fn.lower().endswith(".webp"):
                        ext = ".webp"
                    elif fn.lower().endswith(".gif"):
                        ext = ".gif"
                    image_data = await part.read()
            if not image_data or not job_name:
                return web.json_response({"ok": False, "error": "missing image or job_name"}, status=400)
            # กัน path traversal
            if not job_name.replace("-", "").replace("_", "").isalnum():
                return web.json_response({"ok": False, "error": "bad job name"}, status=400)
            # เซฟลง ~/.tts-for-livestream/character_images/{job}{ext}
            save_dir = _os.path.join(_os.path.expanduser("~"), ".tts-for-livestream", "character_images")
            _os.makedirs(save_dir, exist_ok=True)
            save_path = _os.path.join(save_dir, f"{job_name}{ext}")
            with open(save_path, "wb") as f:
                f.write(image_data)
            return web.json_response({"ok": True, "path": save_path})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def _handle_demo(self, request):
        """GET /demo → push ข้อความตัววตัวอย่างไป client ทั้งหมด (เรียกจาก editor)"""
        # ★ ใช้ async version (await ตรงๆ ไม่ใช่ run_coroutine_threadsafe จากใน loop)
        await self.push_demo_messages_async()
        return web.json_response({"ok": True})

    async def _handle_demo_one(self, request):
        """POST /demo-one → push ข้อความตัวอย่าง 1 ข้อความ (สำหรับ Demo toggle ส่งทีละข้อความ)

        body: {index: 0-3} → เลือกข้อความที่จะส่ง (วนลูป)
        """
        try:
            data = await request.json()
            idx = int(data.get("index", 0)) % 4
        except Exception:
            idx = 0
        demos = self._build_demo_messages()
        if demos and idx < len(demos):
            await self._broadcast_safe(demos[idx])
        return web.json_response({"ok": True})

    async def _handle_chat_widget(self, request):
        """GET /chat-widget?id={widget_id} → serve overlay.html (chat widget = iframe reuse)

        overlay.html เดิมจะ fetch /chat-config?id=... เองเพื่ออ่าน config เฉพาะ widget
        """
        html = self._read_overlay_html()
        return web.Response(
            text=html, content_type="text/html",
            headers=self._no_cache_headers(),
        )

    async def _handle_chat_config(self, request):
        """GET /chat-config?id={widget_id} → JSON config เฉพาะ widget นั้น

        overlay.html จะเรียก endpoint นี้แทน /config ปกติ (ปรับใน overlay.html เล็กน้อย)
        """
        widget_id = request.query.get("id", "")
        return web.json_response(self._build_chat_widget_config(widget_id))

    async def _handle_character_img(self, request):
        """GET /character/{job} → character image (สำหรับ Character Talk) — คลอนจาก overlay_server"""
        job = request.match_info.get("job", "").lower().strip()
        if not job.replace("-", "").replace("_", "").isalnum():
            return web.Response(status=400, text="bad job name")
        img_path = ""
        for cj in getattr(self.settings, "character_jobs", []):
            if cj.get("name", "").lower() == job and cj.get("image"):
                img_path = cj["image"]
                break
        if not img_path:
            img_path = resolve_character_default_image(
                getattr(self.settings, "character_default_image", "")
            )
        if img_path and os.path.exists(img_path):
            return web.FileResponse(img_path, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
        return web.Response(status=404, text="character image not found")

    async def _handle_emote_simple(self, request):
        """GET /emote/{emote_id} — proxy Twitch emote (copy จาก overlay_server)

        ดาวน์โหลดจาก Twitch CDN หลาย format → ใช้ไฟล์แรกที่สำเร็จ
        cache แยกตาม format (animated ใช้ .gif/.apng, static ใช้ .png)
        """
        import urllib.request
        eid = request.match_info.get("emote_id", "")
        # ★ validate — กัน path traversal ผ่าน ../ หรือ %2F (อ่าน/ลบไฟล์นอก cache dir)
        if not eid or not eid.replace("-", "").replace("_", "").isalnum():
            return web.Response(status=400, text="bad emote id")
        want_animated = bool(getattr(self.settings, "overlay_animated_emotes", True))
        cache_dir = os.path.join(os.path.expanduser("~"), ".tts-for-livestream", "emote_cache")

        if want_animated:
            cache_exts = [(".gif", "image/gif"), (".apng", "image/apng"), (".png", "image/png")]
        else:
            cache_exts = [(".png", "image/png")]

        # 1) cache hit
        for ext, ctype in cache_exts:
            cache_path = os.path.join(cache_dir, f"{eid}_1.0{ext}")
            if os.path.exists(cache_path) and os.path.getsize(cache_path) > 0:
                if want_animated and ext == ".gif":
                    try:
                        from PIL import Image
                        img = Image.open(cache_path)
                        if getattr(img, "n_frames", 1) <= 1:
                            os.remove(cache_path)
                            continue
                    except Exception:
                        pass
                return web.FileResponse(
                    cache_path,
                    headers={"Content-Type": ctype, "Cache-Control": "no-cache"},
                )

        # 2) download
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
                    n_frames = 1
                    if is_gif or is_apng:
                        try:
                            from PIL import Image
                            from io import BytesIO
                            _img = Image.open(BytesIO(data))
                            n_frames = getattr(_img, "n_frames", 1)
                        except Exception:
                            n_frames = 1
                    if want_animated and (is_gif or is_apng) and n_frames <= 1:
                        continue
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
                        except Exception:
                            pass
                    is_apng = b"acTL" in data[:200]
                    if "gif" in resp_ct:
                        ext, ctype = ".gif", "image/gif"
                    elif is_apng:
                        ext, ctype = ".apng", "image/apng"
                    elif "png" in resp_ct:
                        ext, ctype = ".png", "image/png"
                    else:
                        ext, ctype = f".{fmt}", f"image/{fmt}"
                    if not want_animated:
                        ext, ctype = ".png", "image/png"
                    cache_path = os.path.join(cache_dir, f"{eid}_1.0{ext}")
                    try:
                        os.makedirs(cache_dir, exist_ok=True)
                        with open(cache_path, "wb") as f:
                            f.write(data)
                    except Exception:
                        pass
                    return web.Response(
                        body=data, content_type=ctype,
                        headers={"Cache-Control": "no-cache"},
                    )
            except Exception:
                continue
        return web.Response(status=404, text="emote not found")

    async def _handle_logo(self, request):
        platform = request.match_info.get("platform", "")
        if not platform.replace("-", "").replace("_", "").isalnum():
            return web.Response(status=400, text="bad platform")
        path = os.path.join(get_base_dir(), "assets", f"{platform}.png")
        if os.path.exists(path):
            return web.FileResponse(path, headers={"Cache-Control": "max-age=3600"})
        return web.Response(status=404, text="logo not found")

    # ═══ Image & Slideshow widget — upload / serve / delete ═══

    def _widget_image_dir(self, widget_id: str) -> str:
        """โฟลเดอร์เก็บรูปของ widget ใน home cache dir (~/.tts-for-livestream/widget_images/{id})"""
        safe_id = "".join(c for c in str(widget_id) if c.isalnum() or c in "-_") or "unknown"
        return os.path.join(os.path.expanduser("~"), ".tts-for-livestream", "widget_images", safe_id)

    async def _handle_upload_widget_image(self, request):
        """POST /upload-widget-image — รับ multipart (widget_id + image file)

        เก็บรูปที่ ~/.tts-for-livestream/widget_images/{widget_id}/{image_id}{ext}
        คืน {ok, image_id, ext, url}
        """
        import time
        try:
            reader = await request.multipart()
            widget_id = None
            image_data = None
            ext = ".png"
            while True:
                part = await reader.next()
                if part is None:
                    break
                if part.name == "widget_id":
                    widget_id = (await part.read()).decode("utf-8", errors="ignore").strip()
                elif part.name == "image":
                    fname = part.filename or ""
                    low = fname.lower()
                    if low.endswith((".jpg", ".jpeg")):
                        ext = ".jpg"
                    elif low.endswith(".webp"):
                        ext = ".webp"
                    elif low.endswith(".gif"):
                        ext = ".gif"
                    elif low.endswith(".png"):
                        ext = ".png"
                    image_data = await part.read()
            if not widget_id or not image_data:
                return web.json_response({"ok": False, "error": "missing widget_id or image"}, status=400)
            # ★ จำกัดขนาดไฟล์ 3MB (local อยู่แล้ว — ไม่ต้องห่วง bandwidth)
            MAX_IMAGE_SIZE = 3 * 1024 * 1024  # 3 MB
            if len(image_data) > MAX_IMAGE_SIZE:
                size_mb = len(image_data) / 1024 / 1024
                return web.json_response({
                    "ok": False,
                    "error": f"ไฟล์ใหญ่เกินไป ({size_mb:.1f} MB) — จำกัดสูงสุด 3 MB",
                }, status=400)
            save_dir = self._widget_image_dir(widget_id)
            os.makedirs(save_dir, exist_ok=True)
            image_id = f"img{int(time.time() * 1000)}"
            save_path = os.path.join(save_dir, f"{image_id}{ext}")
            with open(save_path, "wb") as f:
                f.write(image_data)
            return web.json_response({
                "ok": True,
                "image_id": image_id,
                "ext": ext,
                "url": f"/widget-image/{widget_id}/{image_id}",
            })
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def _handle_delete_widget_image(self, request):
        """POST /delete-widget-image — ลบรูปออกจาก disk

        รับ JSON {widget_id, image_id, ext}
        """
        try:
            data = await request.json()
            widget_id = data.get("widget_id", "")
            image_id = data.get("image_id", "")
            ext = str(data.get("ext", ".png")).lower()
            # validate (กัน path traversal)
            if not image_id.replace("-", "").replace("_", "").isalnum():
                return web.json_response({"ok": False, "error": "bad image_id"}, status=400)
            # ★ whitelist ext — กัน os.remove หลุดออกนอก save_dir ผ่าน "../" ใน ext
            if ext not in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
                return web.json_response({"ok": False, "error": "bad ext"}, status=400)
            save_dir = self._widget_image_dir(widget_id)
            path = os.path.join(save_dir, f"{image_id}{ext}")
            if os.path.exists(path):
                os.remove(path)
            return web.json_response({"ok": True})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def _handle_widget_image(self, request):
        """GET /widget-image/{widget_id}/{image_id} — serve รูปจาก cache dir"""
        widget_id = request.match_info.get("widget_id", "")
        image_id = request.match_info.get("image_id", "")
        # validate
        if not widget_id.replace("-", "").replace("_", "").isalnum():
            return web.Response(status=400, text="bad widget_id")
        if not image_id.replace("-", "").replace("_", "").isalnum():
            return web.Response(status=400, text="bad image_id")
        save_dir = self._widget_image_dir(widget_id)
        # หาไฟล์ที่ match image_id (ไม่รู้ ext → ลองทุก ext)
        for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
            path = os.path.join(save_dir, f"{image_id}{ext}")
            if os.path.exists(path):
                return web.FileResponse(path, headers=self._no_cache_headers())
        return web.Response(status=404, text="image not found")

    # ═══ Video widget — upload / serve ═══

    async def _handle_upload_widget_video(self, request):
        """POST /upload-widget-video — รับ multipart (widget_id + video file)

        เก็บวิดีโอที่ ~/.tts-for-livestream/widget_videos/{widget_id}/{video_id}{ext}
        คืน {ok, video_id, ext, url}
        """
        import time
        try:
            reader = await request.multipart()
            widget_id = None
            video_data = None
            ext = ".mp4"
            while True:
                part = await reader.next()
                if part is None:
                    break
                if part.name == "widget_id":
                    widget_id = (await part.read()).decode("utf-8", errors="ignore").strip()
                elif part.name == "video":
                    fname = part.filename or ""
                    low = fname.lower()
                    if low.endswith(".webm"):
                        ext = ".webm"
                    elif low.endswith(".mov"):
                        ext = ".mov"
                    elif low.endswith(".ogv"):
                        ext = ".ogv"
                    elif low.endswith(".mp4"):
                        ext = ".mp4"
                    video_data = await part.read()
            if not widget_id or not video_data:
                return web.json_response({"ok": False, "error": "missing widget_id or video"}, status=400)
            safe_id = "".join(c for c in str(widget_id) if c.isalnum() or c in "-_") or "unknown"
            save_dir = os.path.join(os.path.expanduser("~"), ".tts-for-livestream", "widget_videos", safe_id)
            os.makedirs(save_dir, exist_ok=True)
            video_id = f"vid{int(time.time() * 1000)}"
            save_path = os.path.join(save_dir, f"{video_id}{ext}")
            with open(save_path, "wb") as f:
                f.write(video_data)
            return web.json_response({
                "ok": True,
                "video_id": video_id,
                "ext": ext,
                "url": f"/widget-video/{widget_id}/{video_id}",
            })
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def _handle_widget_video(self, request):
        """GET /widget-video/{widget_id}/{video_id} → serve video file"""
        widget_id = request.match_info.get("widget_id", "")
        video_id = request.match_info.get("video_id", "")
        if not widget_id.replace("-", "").replace("_", "").isalnum():
            return web.Response(status=400, text="bad widget_id")
        if not video_id.replace("-", "").replace("_", "").isalnum():
            return web.Response(status=400, text="bad video_id")
        safe_id = "".join(c for c in str(widget_id) if c.isalnum() or c in "-_") or "unknown"
        save_dir = os.path.join(os.path.expanduser("~"), ".tts-for-livestream", "widget_videos", safe_id)
        for ext in (".mp4", ".webm", ".mov", ".ogv"):
            path = os.path.join(save_dir, f"{video_id}{ext}")
            if os.path.exists(path):
                return web.FileResponse(path, headers=self._no_cache_headers())
        return web.Response(status=404, text="video not found")

    # ═══ Now Playing widget — serve album cover ═══

    async def _handle_now_playing_art(self, request):
        """GET /now-playing-art?path=<absolute_path> — serve album cover image จาก np_cache

        security: อนุญาตเฉพาะไฟล์ที่อยู่ใน ~/.tts-for-livestream/np_cache เท่านั้น
        """
        path = request.query.get("path", "")
        if not path:
            return web.Response(status=404, text="not found")
        # security: only allow files inside np_cache
        # ★ ใช้ realpath + commonpath (path-aware) แทน startswith ธรรมดา
        #   — กัน sibling dir อย่าง np_cache_backup/ หรือ np_cache_evil/ ที่ขึ้นต้นชื่อเดียวกัน
        np_cache = os.path.join(os.path.expanduser("~"), ".tts-for-livestream", "np_cache")
        real_path = os.path.realpath(path)
        real_cache = os.path.realpath(np_cache)
        try:
            inside = os.path.commonpath([real_path, real_cache]) == real_cache
        except ValueError:  # different drive letters on Windows
            inside = False
        if not inside or not os.path.isfile(real_path):
            return web.Response(status=403, text="forbidden")
        return web.FileResponse(real_path, headers={"Content-Type": "image/jpeg", "Cache-Control": "no-cache"})

    async def _handle_now_playing_state(self, request):
        """GET /now-playing-state → คืน now playing data ล่าสุด (สำหรับ client ที่ refresh หน้า)

        ถ้ายังไม่มีข้อมูล → คืน {empty: true}
        """
        data = getattr(self, "_last_np_data", None)
        if data and data.get("title"):
            return web.json_response(data)
        return web.json_response({"empty": True})

    # ═══ Playroom widget — serve playroom.html + clips (single composer port) ═══

    async def _handle_playroom_widget(self, request):
        """GET /playroom-widget → serve playroom.html (playroom iframe ใน composer canvas)

        ใช้ composer port เดียวกัน → ไม่ต้องเปิด playroom_server port แยก (8766)
        """
        html = self._read_playroom_html()
        return web.Response(text=html, content_type="text/html", headers=self._no_cache_headers())

    def _read_playroom_html(self) -> str:
        """read playroom.html (fallback stub ถ้าไม่พบ)"""
        path = os.path.join(get_base_dir(), "playroom.html")
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return "<!DOCTYPE html><html><body><h1>playroom.html not found</h1></body></html>"

    async def _handle_clip(self, request):
        """GET /clip/{name} → serve video/image clip (port จาก playroom_server)

        ค้นหา clip name ใน settings.playroom_triggers → serve file
        ★ name อาจมีนามสกุลติดมา (เช่น good.png) → strip ออกก่อนค้นหา
        """
        raw_name = request.match_info.get("name", "")
        # ★ path traversal guard (ใช้ raw_name ทุกตัว — กัน path traversal)
        if ".." in raw_name or "/" in raw_name or "\\" in raw_name:
            return web.Response(status=403, text="forbidden")
        # ★ strip ext ออก (name ใน config ไม่มี ext — เช่น "good" ไม่ใช่ "good.png")
        import os as _os
        name = _os.path.splitext(raw_name)[0]
        # หา clip ใน triggers
        triggers = getattr(self.settings, "playroom_triggers", []) or []
        clip_path = None
        for trig in triggers:
            if not isinstance(trig, dict):
                continue
            for clip in trig.get("clips", []):
                if not isinstance(clip, dict):
                    continue
                if clip.get("name") == name:
                    clip_path = clip.get("path", "")
                    break
            if clip_path:
                break
        if not clip_path:
            return web.Response(status=404, text="clip not found")
        # resolve path (relative → base dir; dev fallback playroom/media/ → media/)
        if os.path.isabs(clip_path):
            abs_path = clip_path
        else:
            abs_path = os.path.join(get_base_dir(), clip_path)
            # dev fallback: ถ้าไม่พบ ลอง playroom/media/ → media/
            if not os.path.exists(abs_path) and clip_path.startswith("playroom/media/"):
                abs_path = os.path.join(get_base_dir(), clip_path.replace("playroom/media/", "media/", 1))
        if not os.path.exists(abs_path):
            return web.Response(status=404, text="clip file not found")
        # infer content-type
        low = abs_path.lower()
        ct = "application/octet-stream"
        for ext, mime in [
            (".mp4", "video/mp4"), (".webm", "video/webm"), (".mov", "video/quicktime"),
            (".ogv", "video/ogg"), (".avi", "video/x-msvideo"), (".mkv", "video/x-matroska"),
            (".png", "image/png"), (".jpg", "image/jpeg"), (".jpeg", "image/jpeg"),
            (".gif", "image/gif"), (".webp", "image/webp"), (".bmp", "image/bmp"),
            (".svg", "image/svg+xml"),
        ]:
            if low.endswith(ext):
                ct = mime
                break
        return web.FileResponse(abs_path, headers={"Cache-Control": "no-cache"})

    async def _handle_playroom_test(self, request):
        """GET /playroom-test?widget_id=... → push clip สุ่ม (สำหรับทดสอบใน editor)

        เลือก clip แรกที่พบใน triggers → push ไปยัง playroom widget ที่กำหนด (หรือทุก widget ถ้าไม่ระบุ)
        ★ widget_id = เล่นเฉพาะ widget ที่กดปุ่มทดสอบ (ไม่กระจายไป widget อื่น)
        """
        widget_id = request.query.get("widget_id", "")
        # ★ ถ้าระบุ widget_id → กรอง triggers เฉพาะที่ widget นี้เปิดอยู่
        triggers = getattr(self.settings, "playroom_triggers", []) or []

        def _iter_matching(trigs):
            """ผ่านเฉพาะ trigger ที่ widget นี้ใช้ (ถ้าระบุ widget_id)

            ★ priority: trigger ที่ระบุ widget_ids ตรงเป็นชุดแรก (specific) —
              ชุด widget_ids ว่าง (=ทุก widget, backward compat) เป็นชุดหลัง
              กันบั๊กเดิม: ยิงทดสอบ widget ของ #random แต่ได้ clip ของ #fortune
              (ที่ widget_ids ว่าง) มาก่อนเสมอ
            """
            if not widget_id:
                yield from trigs
                return
            specific = [t for t in trigs
                        if isinstance(t, dict) and widget_id in (t.get("widget_ids") or [])]
            wildcard = [t for t in trigs
                        if isinstance(t, dict) and not (t.get("widget_ids") or [])]
            yield from specific
            yield from wildcard

        for trig in _iter_matching(triggers):
            if not isinstance(trig, dict):
                continue
            clips = trig.get("clips", [])
            if clips and isinstance(clips[0], dict):
                name = clips[0].get("name", "")
                if name:
                    target_ids = [widget_id] if widget_id else None
                    self.push_clip(name, widget_ids=target_ids)
                    return web.json_response({"ok": True, "clip": name})
        return web.json_response({"ok": False, "error": "no clips found"})

    async def _handle_open_playroom_settings(self, request):
        """GET /open-playroom-settings → เรียก callback ให้แอปเปิดแท็บ Playroom settings"""
        if self.on_open_playroom_settings is not None:
            try:
                self.on_open_playroom_settings()
            except Exception:
                pass
        return web.json_response({"ok": True})

    async def _handle_save_playroom_triggers(self, request):
        """POST /save-playroom-triggers — บันทึกการติ๊ก checkbox ของ Playroom widget

        Body: {"widget_id": "w3", "trigger_codes": ["#fortune", "#random"]}
        → อัปเดต settings.playroom_triggers[*].widget_ids (เพิ่ม/ลบ widget_id)
        """
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "bad json"}, status=400)
        widget_id = str(data.get("widget_id", ""))
        codes = data.get("trigger_codes", [])
        if not isinstance(codes, list):
            codes = []
        codes = [str(c) for c in codes if c]
        if not widget_id:
            return web.json_response({"ok": False, "error": "missing widget_id"}, status=400)

        # ★ อัปเดต settings.playroom_triggers ฝั่ง server (เพื่อให้ push_clip routing ถูกต้องทันที)
        triggers = getattr(self.settings, "playroom_triggers", []) or []
        for t in triggers:
            if not isinstance(t, dict):
                continue
            wids = list(t.get("widget_ids", []) or [])
            code = t.get("code", "")
            if code in codes:
                if widget_id not in wids:
                    wids.append(widget_id)
            else:
                if widget_id in wids:
                    wids.remove(widget_id)
            t["widget_ids"] = wids
        self.settings.playroom_triggers = triggers

        # ★ เรียก callback ให้ parent_app persist ลง settings.json
        if self.on_save_playroom_triggers is not None:
            try:
                self.on_save_playroom_triggers()
            except Exception:
                pass

        # ★ broadcast config ใหม่ (playroom_triggers เปลี่ยน → checkbox state refresh)
        await self._broadcast_safe({"type": "config", "config": self._build_config()})
        return web.json_response({"ok": True})

    def push_clip(self, clip_name: str, widget_ids=None) -> None:
        """push clip ไปยัง playroom clients (เรียกจาก app_gui เมื่อ chat trigger match)

        ส่งเฉพาะ _playroom_clients — ไม่ปนกับ composer/chat clients
        ★ URL มีนามสกุลจริง (เช่น /clip/good.png) เพื่อให้ playroom.html แยก image/video ได้
        ★ widget_ids: list ของ widget id ที่จะส่ง (None/[] = ทุก widget, backward compat)
        """
        if not self._playroom_clients or self._loop is None:
            return
        import asyncio
        # ★ หา clip path เพื่อสกัดนามสกุลจริง (กัน isImage() ใน playroom.html ตรวจผิด)
        ext = self._clip_extension(clip_name)
        url = f"/clip/{clip_name}{ext}" if ext else f"/clip/{clip_name}"
        data = {"type": "clip", "url": url, "name": clip_name}
        # ★ รวบรวม target websockets ตาม widget_ids
        targets = self._collect_playroom_targets(widget_ids)
        # ★ DEBUG — เห็น buckets/targets จริงตอน push
        logger.info(f"[CLIP-DEBUG] push '{clip_name}' → widget_ids={widget_ids} | buckets={ {k: len(v) for k, v in self._playroom_clients.items()} } | targets={len(targets)}")
        if not targets:
            return
        try:
            asyncio.run_coroutine_threadsafe(self._send_to_set(data, targets), self._loop)
        except Exception:
            pass

    def _collect_playroom_targets(self, widget_ids=None) -> set:
        """รวบรวม set ของ ws ที่จะส่ง clip ให้
        - widget_ids ว่าง → ส่งทุก widget (backward compat)
        - widget_ids ระบุ → ส่งเฉพาะ widget เหล่านั้น (รวม "_all" bucket เสมอ เพื่อ backward compat กับ client เก่า)
        """
        targets = set()
        if widget_ids:
            # ส่งเฉพาะ widget ที่กำหนด + "_all" bucket (client เก่าที่ไม่ส่ง widget_id)
            ids = set(widget_ids)
            ids.add("_all")
            for wid, clients in self._playroom_clients.items():
                if wid in ids:
                    targets.update(clients)
        else:
            # ไม่ระบุ → ส่งทุก widget
            for clients in self._playroom_clients.values():
                targets.update(clients)
        return targets

    def _clip_extension(self, clip_name: str) -> str:
        """หานามสกุลไฟล์จริงของ clip (เพื่อส่งใน URL ให้ playroom.html แยก image/video)"""
        triggers = getattr(self.settings, "playroom_triggers", []) or []
        for trig in triggers:
            if not isinstance(trig, dict):
                continue
            for clip in trig.get("clips", []):
                if not isinstance(clip, dict):
                    continue
                if clip.get("name") == clip_name:
                    path = clip.get("path", "")
                    import os as _os
                    _, ext = _os.path.splitext(path)
                    return ext.lower()  # เช่น ".png", ".mp4"
        return ""

    def push_emote_party(self, emotes: list) -> None:
        """push emote list ไปยัง composer clients (Emote Party widget)

        ถูกเรียกจาก app_gui เมื่อแชทมี emote (Twitch sub/BTTV/FFZ/7TV/YouTube/TikTok/Unicode emoji)
        - emotes: list ของ {url, text, source} (url สำหรับ image emote, text สำหรับ Unicode emoji)
        - ส่งไป _clients (composer.html ทั้ง editor + OBS browser source)
        """
        if not emotes or self._loop is None:
            return
        import asyncio
        data = {"type": "emote_party", "emotes": emotes}
        try:
            asyncio.run_coroutine_threadsafe(self._broadcast(data), self._loop)
        except Exception:
            pass

    async def _send_to_set(self, data: dict, ws_set: set) -> None:
        """ส่ง data ไปยัง set ของ ws ที่กำหนด + ทำความสะอาด dead ws ออกจาก _playroom_clients"""
        dead = set()
        for ws in list(ws_set):
            try:
                await ws.send_json(data)
            except Exception:
                dead.add(ws)
        if dead:
            for clients in self._playroom_clients.values():
                clients -= dead

    async def _broadcast_playroom(self, data: dict) -> None:
        """broadcast ไปยัง playroom clients ทุกตัว (backward compat — ใช้ _send_to_set)"""
        targets = set()
        for clients in self._playroom_clients.values():
            targets.update(clients)
        await self._send_to_set(data, targets)

    async def _handle_ws(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        # ★ ยังไม่ add เข้า _clients ทันที — รอเช็ค hello ก่อน (กัน chat widget iframe อยู่ซ้อน 2 ที่)
        pending_widget_id = None
        pending_client_kind = ""
        hello_received = False
        # composer config (เริ่มต้น — ถ้าไม่มี hello ภายใน 200ms ให้ push composer config ปกติ)
        import asyncio as _aio
        try:
            # รอ hello แบบ timeout 200ms (chat widget จะส่ง hello ทันที)
            try:
                first_msg = await _aio.wait_for(ws.receive(), timeout=0.2)
                if first_msg.type == WSMsgType.TEXT:
                    try:
                        data = first_msg.json()
                        if data.get("type") == "hello":
                            hello_received = True
                            pending_widget_id = data.get("widget_id", "")
                            pending_client_kind = data.get("client", "")  # "playroom" หรือ ว่าง
                    except Exception:
                        pass
            except _aio.TimeoutError:
                pass  # ไม่มี hello → push composer config ปกติ
        except Exception:
            pass

        # ★ แยก client ออกเป็น 3 กลุ่มชัดเจน (กัน broadcast ซ้อน)
        if pending_client_kind == "playroom":
            # playroom iframe → เก็บใน _playroom_clients เท่านั้น (รับแค่ type:"clip")
            # ★ group by widget_id (empty widget_id → "_all" bucket สำหรับ backward compat)
            _pr_wid = pending_widget_id or "_all"
            self._playroom_clients.setdefault(_pr_wid, set()).add(ws)
        elif pending_widget_id:
            # chat widget iframe → เก็บใน _chat_widget_clients เท่านั้น (ไม่ใส่ _clients)
            self._chat_widget_clients.setdefault(pending_widget_id, set()).add(ws)
            try:
                await ws.send_json({"type": "config", "config": self._build_chat_widget_config(pending_widget_id)})
            except Exception:
                pass
        else:
            # composer editor/overlay ปกติ → add เข้า _clients (รับ message/config ทั่วไป)
            self._clients.add(ws)
            try:
                await ws.send_json({"type": "config", "config": self._build_config()})
                # ★ ASK state ล่าสุด — client ใหม่ (เช่น OBS refresh) ได้โพลปัจจุบันทันที
                if self._last_ask_state:
                    await ws.send_json(self._last_ask_state)
            except Exception:
                pass

        # รอ message ถัดไป
        # ★ track ว่า ws นี้อยู่ใน _playroom_clients bucket ไหน (เพื่อ cleanup ที่ถูกต้อง)
        playroom_bucket = "_all" if pending_client_kind == "playroom" else None
        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        data = msg.json()
                        # ★ editor ส่ง config ใหม่ → push ไป chat widget iframe ทันที
                        if data.get("type") == "config" and data.get("config"):
                            cfg = data["config"]
                            widgets = cfg.get("widgets", [])
                            for w in widgets:
                                if w.get("type") == "chat":
                                    await self._push_widget_config(w["id"])
                        if data.get("type") == "hello":
                            late_client_kind = data.get("client", "")
                            late_wid = data.get("widget_id", "")
                            if late_client_kind == "playroom":
                                # late hello จาก playroom → re-register bucket
                                if playroom_bucket and playroom_bucket in self._playroom_clients:
                                    self._playroom_clients[playroom_bucket].discard(ws)
                                playroom_bucket = late_wid or "_all"
                                self._playroom_clients.setdefault(playroom_bucket, set()).add(ws)
                                pending_client_kind = "playroom"
                            elif late_wid:
                                # late hello จาก chat widget → re-register
                                wid = late_wid
                                if pending_widget_id and pending_widget_id in self._chat_widget_clients:
                                    self._chat_widget_clients[pending_widget_id].discard(ws)
                                pending_widget_id = wid
                                self._chat_widget_clients.setdefault(wid, set()).add(ws)
                                await ws.send_json({"type": "config", "config": self._build_chat_widget_config(wid)})
                    except Exception:
                        pass
                elif msg.type == WSMsgType.ERROR:
                    break
        except Exception:
            pass
        finally:
            self._clients.discard(ws)
            # ★ cleanup playroom ws ออกจาก bucket ที่ถูกต้อง
            if playroom_bucket and playroom_bucket in self._playroom_clients:
                self._playroom_clients[playroom_bucket].discard(ws)
                if not self._playroom_clients[playroom_bucket]:
                    del self._playroom_clients[playroom_bucket]
            if pending_widget_id and pending_widget_id in self._chat_widget_clients:
                self._chat_widget_clients[pending_widget_id].discard(ws)
                if not self._chat_widget_clients[pending_widget_id]:
                    del self._chat_widget_clients[pending_widget_id]
        return ws

    # ── push (เรียกจาก Tk thread) ──
    async def _broadcast(self, data: dict) -> None:
        """broadcast ไป composer clients + chat widget clients (ทุก widget)

        ★ แยก 2 กลุ่มชัดเจน — ไม่มี client ไหนอยู่ 2 กลุ่มพร้อมกัน (กันเบิ้ล)
        """
        dead = set()
        # composer clients (editor/overlay ปกติ) — รับเฉพาะ config/message/viewers
        for ws in list(self._clients):
            try:
                await ws.send_json(data)
            except Exception:
                dead.add(ws)
        self._clients -= dead
        # ★ chat widget clients (แต่ละ iframe) — รับเฉพาะ message/viewers (ไม่รับ config ทั่วไป)
        if data.get("type") in ("message", "viewers", "eval_js", "reload_emotes"):
            chat_dead = set()
            for wid, wset in list(self._chat_widget_clients.items()):
                for ws in list(wset):
                    try:
                        await ws.send_json(data)
                    except Exception:
                        chat_dead.add((wid, ws))
            for wid, ws in chat_dead:
                self._chat_widget_clients.get(wid, set()).discard(ws)
            # ★ ล้าง widget_id ที่ไม่มี client แล้ว (กัน ghost connections)
            empty_wids = [wid for wid, wset in self._chat_widget_clients.items() if not wset]
            for wid in empty_wids:
                del self._chat_widget_clients[wid]

    async def _push_widget_config(self, widget_id: str) -> None:
        """push config update เฉพาะ widget (เรียกหลัง save settings)"""
        wset = self._chat_widget_clients.get(widget_id, set())
        if not wset:
            return
        config = self._build_chat_widget_config(widget_id)
        dead = set()
        for ws in list(wset):
            try:
                await ws.send_json({"type": "config", "config": config})
            except Exception:
                dead.add(ws)
        for ws in dead:
            wset.discard(ws)

    async def _broadcast_safe(self, data: dict) -> None:
        """broadcast จากภายใน async context (เรียกใน handler ได้โดยตรง)

        ★ ห้ามการ์ดแค่ _clients — ต้องเช็คทุกกลุ่ม (chat widget iframe / playroom)
          เคยบั๊ก: ปิดหน้า editor แล้ว demo/ข้อความหายทั้งหมดทั้งที่ widget ยังเปิดอยู่
        """
        if not self._clients and not self._chat_widget_clients and not self._playroom_clients:
            return
        await self._broadcast(data)

    def _broadcast_threadsafe(self, data: dict) -> None:
        """broadcast จาก pipeline thread → ส่งเข้า event loop ของ server

        ★ เช็คทุกกลุ่ม client (แก้เหมือน _broadcast_safe — เคยบั๊ก: ไม่มี editor
          เปิดอยู่ → แชทจริงไม่เข้า widget iframe เลย)
        """
        if (not self._started or self._loop is None
                or (not self._clients and not self._chat_widget_clients
                    and not self._playroom_clients)):
            return
        try:
            asyncio.run_coroutine_threadsafe(self._broadcast(data), self._loop)
        except Exception:
            pass

    def update_config(self, settings) -> None:
        """push config ใหม่ (เรียกเมื่อ settings เปลี่ยน)"""
        self.settings = settings
        self._broadcast_threadsafe({"type": "config", "config": self._build_config()})

    def push_message(self, msg_payload: dict) -> None:
        """push chat message ไป composer (msg_payload = dict ที่ serialize แล้ว)

        parent_app (app_gui) จะเรียก method นี้พร้อมกับ overlay_server.push_message

        ★ msg_payload ต้องเป็น flat dict (มี type/author/text/ฯลฯ ใน root)
          เหมือน overlay_server._serialize_message — overlay.html อ่าน field จาก root
          ไม่ใช่จาก data.message
        """
        # ถ้า payload ยังไม่มี type → เติม type=message
        if "type" not in msg_payload:
            msg_payload = dict(msg_payload)
            msg_payload["type"] = "message"
        self._broadcast_threadsafe(msg_payload)

    def push_viewer_counts(self, total: int, platforms: dict) -> None:
        """push ยอดคนดูไป composer widget"""
        data = {"type": "viewers", "total": int(total or 0), "platforms": platforms or {}}
        self._broadcast_threadsafe(data)

    def _ask_demo_cancel(self) -> None:
        """ยกเลิกตัวจับเวลา demo ทั้งหมด (เรียกบน event loop ของ server เท่านั้น)"""
        for h in getattr(self, "_ask_demo_handles", []) or []:
            try:
                h.cancel()
            except Exception:
                pass
        self._ask_demo_handles = []

    def _ask_demo_later(self, delay: float, payload: dict) -> None:
        """จับเวลา broadcast demo ถัดไป (บน event loop)"""
        import asyncio

        async def _fire():
            try:
                msg = {"type": "ask"}
                msg.update(payload)
                await self._broadcast_safe(msg)
            except Exception:
                pass
        try:
            loop = asyncio.get_event_loop()
            if not hasattr(self, "_ask_demo_handles"):
                self._ask_demo_handles = []
            self._ask_demo_handles.append(
                loop.call_later(delay, lambda: asyncio.ensure_future(_fire())))
        except Exception:
            pass

    async def _handle_ask_demo(self, request):
        """POST /ask-demo {mode: 'vote'|'result'|'stop'} — ฉายโพลตัวอย่าง ASK ทุก client

        ★ broadcast อย่างเดียว ไม่แคช _last_ask_state (โพลจริง push มาจะทับทันที
          และหน้าที่ refresh กลาง demo ไม่โดนดึง demo ค้างกลับมา)
        ★ auto-flow: vote ครบเวลา (45s) → สลับเป็นหน้าสรุปผล → 10 วิ → หายไปเอง
          (หน้าสรุปหายด้วย active=false → client เล่น anim-out ตามที่ตั้งไว้)
          โพลจริงเริ่ม / กดหยุดมือ → ยกเลิก flow ทันที
        """
        try:
            data = await request.json()
        except Exception:
            data = {}
        mode = str(data.get("mode", "vote"))
        import time as _t
        self._ask_demo_cancel()
        if mode == "vote":
            duration = 30  # ★ เดิม 45 วิ — ลด 30% ตาม user (นานเกิน)
            import random as _rnd
            # ★ ยอดเริ่มต้น + สุ่มเพิ่มเรื่อย ๆ ทุก 2.5 วิ (18 รอบพอดี 45 วิ)
            #   → แถบขยับ + ยอดรวมขึ้นสด ๆ ให้เห็นว่าโหวตจริงหน้าตาเป็นยังไง
            counts = [3, 1, 2, 1]
            end_ts = _t.time() + duration
            base = {
                "active": True, "phase": "voting",
                "question": "ตัวอย่าง: ชอบช่วงเวลาไหนในการดูไลฟ์?",
                "choices": ["เช้า", "บ่าย", "เย็น", "ดึก"],
                "keys": ["A", "B", "C", "D"],
                "realtime": True,
                "end_ts": end_ts,
                "duration_sec": duration,
            }
            payload = dict(base, counts=list(counts), total_voters=sum(counts))
            # ★ รอบสุดท้าย = 27.5 วิ (k=11) — เว้นช่วงก่อน result ที่ 30 วิ
            #   (กัน race: update ชนกับ result push → หน้าสรุปผลโดนดันกลับ)
            for k in range(1, 12):
                for j in range(len(counts)):
                    counts[j] += _rnd.randint(0, 2)
                upd = dict(base, counts=list(counts), total_voters=sum(counts))
                self._ask_demo_later(k * 2.5, upd)
            # ★ สรุปผลใช้ยอดสุดท้ายที่สุ่มได้จริง (ต่อเนื่องจากช่วงโหวต)
            result_payload = {
                "active": True, "phase": "ended",
                "question": base["question"],
                "choices": base["choices"],
                "keys": base["keys"],
                "counts": list(counts),
                "total_voters": sum(counts),
                "realtime": False,
                "end_ts": None,
                "duration_sec": None,
            }
            # ★ ครบเวลา → สรุปผล → +10 วิ → ปิด
            self._ask_demo_later(duration, result_payload)
            self._ask_demo_later(duration + 10, {"active": False})
        elif mode == "result":
            payload = {
                "active": True, "phase": "ended",
                "question": "ตัวอย่าง: ชอบช่วงเวลาไหนในการดูไลฟ์?",
                "choices": ["เช้า", "บ่าย", "เย็น", "ดึก"],
                "keys": ["A", "B", "C", "D"],
                "counts": [12, 7, 3, 9],
                "total_voters": 31,
                "realtime": False,
                "end_ts": None,
                "duration_sec": None,
            }
            # ★ สรุปผลเดี่ยว → 10 วิ → ปิด
            self._ask_demo_later(10, {"active": False})
        else:  # stop
            payload = {"active": False}
        msg = {"type": "ask"}
        msg.update(payload)
        await self._broadcast_safe(msg)
        return web.json_response({"ok": True})

    def push_ask_state(self, payload: dict) -> None:
        """★ push สถานะ ASK (โพล) ไป composer widget — แคชไว้ส่ง client ที่มาใหม่ด้วย"""
        data = {"type": "ask"}
        data.update(payload or {})
        self._last_ask_state = data
        # ★ โพลจริงมาแล้ว → ยกเลิก demo auto-flow ค้าง (ถ้ามี) บน event loop
        if self._loop is not None and getattr(self, "_started", False):
            try:
                self._loop.call_soon_threadsafe(self._ask_demo_cancel)
            except Exception:
                pass
        self._broadcast_threadsafe(data)

    def push_now_playing(self, data: dict) -> None:
        """push now playing data ไป composer widget"""
        payload = {"type": "now_playing"}
        payload.update(data)
        self._broadcast_threadsafe(payload)

    # ═══ Avatar widget — TTS speaking state push ═══

    def push_avatar_state(self, widget_id: str, talking: bool) -> None:
        """push avatar speaking state ไป composer widget (TTS mode only)

        Args:
            widget_id: id ของ avatar widget ที่จะอัปเดต (TTS mode)
            talking: True = กำลังพูด, False = idle

        ★ Mic mode ไม่ใช้ push นี้ — วัด RMS ใน JS เอง (ลด latency)
        ★ เก็บ last state สำหรับ client ที่ reconnect
        """
        payload = {"type": "avatar_state", "widget_id": widget_id, "talking": bool(talking)}
        # ★ cache last state per widget (สำหรับ /avatar-state endpoint)
        if not hasattr(self, "_last_avatar_state"):
            self._last_avatar_state = {}
        self._last_avatar_state[widget_id] = bool(talking)
        self._broadcast_threadsafe(payload)

    async def _handle_avatar_state(self, request):
        """GET /avatar-state → คืน avatar speaking state ล่าสุด (สำหรับ client ที่ refresh/reconnect)

        คืน {widget_id: talking_bool, ...} สำหรับทุก avatar widget ที่เคย push
        """
        state = getattr(self, "_last_avatar_state", {})
        return web.json_response(state or {})

    # ═══ Mic level watcher (Python — แก้ปัญหา OBS Browser Source ไม่เข้าถึงไมค์ได้) ═══

    async def _handle_mic_devices(self, request):
        """GET /mic-devices → คืนรายการ audio input devices ทั้งหมดจากระบบ

        คืน {devices: [{index, name, channels}, ...], default: int}
        """
        try:
            from mic_level_watcher import list_input_devices, get_default_input_index
            devices = list_input_devices()
            default_idx = get_default_input_index()
            return web.json_response({"devices": devices, "default": default_idx})
        except Exception as e:
            return web.json_response({"devices": [], "default": -1, "error": str(e)})

    async def _handle_mic_level(self, request):
        """GET /mic-level → คืนค่า mic level ล่าสุด (สำหรับ settings meter polling)

        คืน {level: float, age: float} — age = วินาทีที่ผ่านไปหลังอัปเดตล่าสุด
        ถ้าไม่มี watcher รัน → คืน {level: null}
        """
        level = getattr(self, "_last_mic_level", None)
        last_time = getattr(self, "_last_mic_level_time", None)
        import time as _t
        now = _t.time()
        age = (now - last_time) if last_time else 999
        return web.json_response({
            "level": level,
            "age": round(age, 2),
            "running": self._mic_watcher is not None and self._mic_watcher.is_running if hasattr(self, '_mic_watcher') else False,
        })

    def start_mic_watcher(self, device_index, threshold_db, widget_id, gain=100):
        """เริ่มวัดเสียงไมโครโฟน → push avatar_state + mic_level ไป overlay

        Args:
            device_index: index ของไมโครโฟน (None = default)
            threshold_db: dB threshold (-60..0) — เสียงดังกว่านี้ = talking
            widget_id: id ของ avatar widget ที่จะ push
        """
        try:
            from mic_level_watcher import MicLevelWatcher
            logger.info(f"start_mic_watcher: device={device_index} threshold={threshold_db}dB widget={widget_id}")
            # ★ stop existing watcher (ถ้ามี)
            self.stop_mic_watcher()
            # ★ talking state tracking — กัน flicker
            state = {"talking": False, "talking_frames": 0, "silent_frames": 0}
            # ★ clamp threshold (กันค่าผิดปกติ) — default -35
            thr = max(-60, min(0, float(threshold_db if threshold_db is not None else -35)))
            logger.info(f"start_mic_watcher: clamped threshold = {thr}dB")
            # ★ เก็บ threshold + widget_id สำหรับ browser mic relay fallback
            self._mic_threshold = thr
            self._mic_widget_id = widget_id
            # ★ auto noise floor calibration — วัด noise floor ใน 2 วินาทีแรก
            calib = {"samples": [], "done": False, "start_time": None}
            import time as _time
            # ★ เก็บ device + widget id เพื่อเช็คตอน restart
            self._mic_watcher_dev = device_index
            self._mic_watcher_wid = widget_id

            def on_level(db):
                # ★ calibration phase (2 วินาทีแรก)
                if not calib["done"]:
                    if calib["start_time"] is None:
                        calib["start_time"] = _time.time()
                    calib["samples"].append(db)
                    elapsed = _time.time() - calib["start_time"]
                    if elapsed >= 2.0 and len(calib["samples"]) >= 10:
                        calib["done"] = True
                        # หา noise floor = ค่ามัธยฐานของ samples (เสียงเงียบส่วนใหญ่)
                        import statistics
                        try:
                            noise_floor = statistics.median(calib["samples"])
                        except Exception:
                            noise_floor = -50
                        # ★ ถ้า threshold ที่ตั้งต่ำกว่า noise floor → ปรับให้สูงกว่า 5 dB
                        if thr < noise_floor:
                            new_thr = noise_floor + 5
                            if new_thr > 0: new_thr = -5
                            logger.info(f"auto-calib: noise floor={noise_floor:.1f}dB, threshold {thr:.1f} → {new_thr:.1f}dB")
                            thr = new_thr
                            # ★ broadcast ค่า threshold ใหม่
                            self._broadcast_threadsafe({
                                "type": "mic_calibrated",
                                "widget_id": widget_id,
                                "threshold": round(thr, 1),
                                "noise_floor": round(noise_floor, 1),
                            })
                        else:
                            logger.info(f"auto-calib: noise floor={noise_floor:.1f}dB, threshold {thr:.1f}dB OK (no change)")
                # ★ detect talking — ต้องดังกว่า threshold 2 frame ติด / เงียบ 5 frame
                if db > thr:
                    state["talking_frames"] += 1
                    state["silent_frames"] = 0
                    if state["talking_frames"] >= 2 and not state["talking"]:
                        state["talking"] = True
                        self.push_avatar_state(widget_id, True)
                else:
                    state["silent_frames"] += 1
                    state["talking_frames"] = 0
                    if state["silent_frames"] >= 5 and state["talking"]:
                        state["talking"] = False
                        self.push_avatar_state(widget_id, False)
                # ★ push level ไป meter ด้วย
                if not hasattr(self, "_mic_level_counter"):
                    self._mic_level_counter = 0
                self._mic_level_counter += 1
                # ★ เก็บค่าล่าสุดไว้ใน server (สำหรับ HTTP polling — กัน WS หลุด)
                self._last_mic_level = round(db, 1)
                self._last_mic_level_time = _time.time()
                if self._mic_level_counter % 3 == 0:
                    self._broadcast_threadsafe({
                        "type": "mic_level",
                        "widget_id": widget_id,
                        "level": round(db, 1),
                    })

            self._mic_watcher = MicLevelWatcher(on_level=on_level, device_index=device_index, gain=gain)
            ok = self._mic_watcher.start()
            if not ok:
                logger.warning("MicLevelWatcher failed to start")
            return ok
        except Exception as e:
            logger.error(f"start_mic_watcher failed: {e}")
            return False

    def stop_mic_watcher(self):
        """หยุดวัดเสียงไมโครโฟน"""
        w = getattr(self, "_mic_watcher", None)
        if w:
            try:
                w.stop()
            except Exception:
                pass
            self._mic_watcher = None

    # ═══ Avatar preset — serve bundled avatar images (man/girl default) ═══
    # ★ mapping: preset name + role → file ใน assets/avatar/
    #   man1=man idle, man2=man talk, man3=man blink-idle, man4=man blink-talk
    #   (เหมือนกันสำหรับ girl)
    AVATAR_PRESETS = {
        "man": {"idle": "man1", "talk": "man2", "blink_idle": "man3", "blink_talk": "man4"},
        "girl": {"idle": "girl1", "talk": "girl2", "blink_idle": "girl3", "blink_talk": "girl4"},
    }

    async def _handle_avatar_preset(self, request):
        """GET /avatar-preset/{name}/{role} → serve bundled avatar preset image

        name: "man" | "girl"
        role: "idle" | "talk" | "blink_idle" | "blink_talk"
        """
        name = request.match_info.get("name", "").lower()
        role = request.match_info.get("role", "").lower()
        preset = self.AVATAR_PRESETS.get(name)
        if not preset or role not in preset:
            return web.Response(status=404, text="invalid preset/role")
        file_base = preset[role]
        path = os.path.join(get_base_dir(), "assets", "avatar", f"{file_base}.png")
        if not os.path.exists(path):
            return web.Response(status=404, text="preset image not found")
        return web.FileResponse(path, headers={"Cache-Control": "max-age=3600", "Content-Type": "image/png"})

    # ═══ Donate Goal widget — push from EasyDonate watcher ═══

    def push_donate_goal(self, widget_id: str, current: float, goal: float,
                         last_donor: str = "", last_amount: float = 0, donor_count: int = 0) -> None:
        """push donate goal update ไป composer widget

        Args:
            widget_id: id ของ donate_goal widget
            current: ยอดปัจจุบัน (บาท)
            goal: เป้าหมาย (บาท)
            last_donor: ชื่อผู้โดเนทล่าสุด
            last_amount: ยอดโดเนทล่าสุด
            donor_count: จำนวนครั้งโดเนท
        """
        payload = {
            "type": "donate_goal",
            "widget_id": widget_id,
            "current": float(current),
            "goal": float(goal),
            "last_donor": last_donor,
            "last_amount": float(last_amount),
            "donor_count": int(donor_count),
            "percent": min(100, (float(current) / max(1, float(goal))) * 100),
        }
        # ★ cache last state (สำหรับ reconnect)
        if not hasattr(self, "_last_donate_goal"):
            self._last_donate_goal = {}
        self._last_donate_goal[widget_id] = payload
        self._broadcast_threadsafe(payload)

    async def _handle_donate_goal_state(self, request):
        """GET /donate-goal-state → คืน donate goal state ล่าสุด (สำหรับ reconnect)"""
        state = getattr(self, "_last_donate_goal", {})
        return web.json_response(state or {})

    async def _handle_easydonate_test(self, request):
        """POST /easydonate-test — ทดสอบ EasyDonate API key

        รับ JSON: {api_key: "ezdn_v1_xxx"} หรือ {widget_id: "w123"} (ใช้ key เดิมจาก settings —
        config ที่ broadcast เป็น masked จึงต้องให้ server ดึงเอง)
        คืน: {ok: true, username: "xxx"} หรือ {ok: false, error: "..."}
        """
        try:
            data = await request.json()
            api_key = data.get("api_key", "").strip()
            # ★ ไม่ได้ส่ง key มาแต่ส่ง widget_id → ใช้ key เดิมจาก settings
            if not api_key and data.get("widget_id"):
                _wid = str(data.get("widget_id"))
                for _w in (getattr(self.settings, "composer_widgets", None) or []):
                    if isinstance(_w, dict) and _w.get("id") == _wid:
                        api_key = str(_w.get("dg_api_key", "") or "").strip()
                        break
            if not api_key:
                return web.json_response({"ok": False, "error": "กรุณาใส่ API Key"})

            from easydonate_api import EasyDonateClient
            client = EasyDonateClient(api_key)
            me = client.get_me()
            if me and "id" in me:
                return web.json_response({
                    "ok": True,
                    "username": me.get("username", ""),
                    "display_name": me.get("displayName", ""),
                })
            else:
                return web.json_response({"ok": False, "error": "API Key ไม่ถูกต้องหรือเชื่อมต่อไม่ได้"})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)})

    def reload_page(self) -> None:
        """push eval_js: location.reload() — บังคับ reload client ทุกตัว (กัน cache ค้าง)"""
        self._broadcast_threadsafe({"type": "eval_js", "js": "location.reload()"})

    def _build_demo_messages(self) -> list:
        """สร้าง demo messages — ถ้ามี character_jobs → เพิ่ม job field เพื่อทดสอบ Character Talk

        ส่ง messages หมุนเวียน job ระหว่าง jobs ที่มี + default → ทดสอบทุกตัวละคร
        """
        demos = [
            {"type": "message", "author": "Meng", "text": "สวัสดีครับ ยินดีต้อนรับ!", "color": "#06b6d4", "platform": "twitch", "event": "message"},
            {"type": "message", "author": "PlayerOne", "text": "Hello world! ส่งจาก YouTube", "color": "#ff0000", "platform": "youtube", "event": "message"},
            {"type": "message", "author": "ไทยแลนด์", "text": "ทดสอบภาษาไทย อักขระพิเศษ สระบนล่าง ใจ", "color": "#fbbf24", "platform": "mylive", "event": "message"},
            {"type": "message", "author": "TestBot", "text": "🎮 ทดสอบ emoji + ข้อความยาวๆ หน่อยเพื่อดูว่า wrap ได้ดีไหมนะครับ", "color": "#a78bfa", "platform": "tiktok", "event": "message"},
        ]
        # ★ ถ้ามี character_jobs → ใส่ job field หมุนเวียน (ทดสอบ Character Talk)
        char_jobs = getattr(self.settings, "character_jobs", [])
        if char_jobs:
            # รวม job names + "default" (ทดสอบ default image ด้วย)
            job_names = [cj.get("name", "") for cj in char_jobs if cj.get("name")]
            job_names.append("default")   # สุดท้าย = default
            # กระจาย job ให้แต่ละ author (หมุนเวียน)
            for i, msg in enumerate(demos):
                msg["job"] = job_names[i % len(job_names)]
        return demos

    async def push_demo_messages_async(self) -> None:
        """push ข้อความตัวอย่างจาก async context (เรียกใน handler)"""
        demos = self._build_demo_messages()
        for msg in demos:
            await self._broadcast_safe(msg)
        # ทดสอบ viewer count ด้วย
        await self._broadcast_safe({
            "type": "viewers", "total": 1234,
            "platforms": {"twitch": 500, "youtube": 300, "mylive": 200, "tiktok": 234},
        })

    def push_demo_messages(self) -> None:
        """push ข้อความตัวอย่างหลายแบบเข้า composer (เรียกจาก Tk thread)

        ส่งจาก platform ต่างๆ + สีต่างกัน → ทดสอบ chat widget + viewer widget
        ถ้ามี character_jobs → เพิ่ม job field เพื่อทดสอบ Character Talk
        """
        demos = self._build_demo_messages()
        for msg in demos:
            self._broadcast_threadsafe(msg)
        # ทดสอบ viewer count ด้วย
        self.push_viewer_counts(1234, {"twitch": 500, "youtube": 300, "mylive": 200, "tiktok": 234})

    # ── config builder ──
    def _build_config(self) -> dict:
        s = self.settings
        canvas = getattr(s, "composer_canvas_size", "1080p")
        # ★ mask dg_api_key ก่อน broadcast — /config ถูก push ไปทุก WS client
        #   (รวมเว็บที่เปิดใน browser สามารถเชื่อม WS แบบ cross-origin ได้) → ห้ามส่ง API key จริง
        widgets_out = []
        for _w in list(getattr(s, "composer_widgets", []) or []):
            if isinstance(_w, dict) and _w.get("type") == "donate_goal" and _w.get("dg_api_key"):
                _w = dict(_w)  # copy — ไม่แต้ข้อมูลต้นทาง
                _w["dg_api_key"] = "__MASKED__"
            widgets_out.append(_w)
        return {
            "canvas_size": canvas,
            "canvas_w": 1280 if canvas == "720p" else 1920,
            "canvas_h": 720 if canvas == "720p" else 1080,
            "widgets": widgets_out,
            "font_family": getattr(s, "game_overlay_font_family", "Kanit"),
            # ★ character jobs + default image (ใช้ใน Character Talk mode)
            "character_jobs": list(getattr(s, "character_jobs", [])),
            "character_default_image": getattr(s, "character_default_image", ""),
            # ★ playroom triggers — ส่ง code + widget_ids ไปให้ composer.html แสดง checkbox ใน settings
            #    (ส่งเฉพาะ field ที่ UI ใช้ — ไม่ส่ง path ทั้งหมด)
            "playroom_triggers": [
                {
                    "code": str(t.get("code", "")),
                    "widget_ids": list(t.get("widget_ids", []) or []),
                    "clip_count": len(t.get("clips", []) or []),
                }
                for t in (getattr(s, "playroom_triggers", []) or [])
                if isinstance(t, dict) and t.get("code")
            ],
            # ★ overlay_version = mtime ของ overlay.html → เมื่อแก้ไฟล์, version เปลี่ยน
            #    composer.html จะ reload chat-widget iframe อัตโนมัติ (กัน cache ค้าง)
            "overlay_version": self._overlay_version(),
        }

    # ── helpers ──
    def _read_composer_html(self) -> str:
        path = os.path.join(get_base_dir(), "composer.html")
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return "<!DOCTYPE html><html><body><h1>composer.html not found</h1></body></html>"

    def _read_overlay_html(self) -> str:
        """read overlay.html (สำหรับ chat widget iframe — reuse rendering เดิม)"""
        path = os.path.join(get_base_dir(), "overlay.html")
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return "<!DOCTYPE html><html><body><h1>overlay.html not found</h1></body></html>"

    def _overlay_version(self) -> int:
        """mtime ของ overlay.html → ใช้เป็น cache-bust version
        เมื่อ overlay.html ถูกแก้ → version เปลี่ยน → iframe reload อัตโนมัติ
        (ป้องกันปัญหา iframe ค้างอยู่ที่เวอร์ชันเก่าหลังจากแก้ CSS/JS)
        """
        try:
            path = os.path.join(get_base_dir(), "overlay.html")
            return int(os.path.getmtime(path))
        except Exception:
            return 0

    def _find_widget(self, widget_id: str) -> dict:
        """หา widget ใน settings.composer_widgets ตาม id"""
        for w in getattr(self.settings, "composer_widgets", []):
            if w.get("id") == widget_id:
                return w
        return {}

    def _build_chat_widget_config(self, widget_id: str) -> dict:
        """build config สำหรับ overlay.html ที่อยู่ใน chat widget iframe

        แปลง widget settings → config format ที่ overlay.html เข้าใจ (overlay_* fields)
        + inject theme_css (จาก game_overlay_themes)
        """
        w = self._find_widget(widget_id)
        s = self.settings
        appearance = w.get("appearance_mode", "default")
        theme = w.get("theme", "default")
        custom_css = w.get("custom_css", "")
        # compute theme_css (raw CSS string)
        # ★ theme ใช้ได้ในทุก mode (ไม่ใช่แค่ mode=theme)
        try:
            theme_css = ""
            if appearance == "theme" and theme and theme != "default":
                theme_css = get_theme_css(theme, "")
            elif appearance == "default" and w.get("custom_css_enabled") and custom_css:
                # ★ Custom CSS ย้ายมาโหมด Default (เปิดผ่าน checkbox)
                theme_css = custom_css
        except Exception:
            theme_css = ""

        # mode flags ตาม appearance
        balloon_mode = (appearance == "balloon")
        character_mode = (appearance == "character")
        slider_mode = (appearance == "slider")

        config = {
            # mode
            "appearance_mode": appearance,
            "theme": theme if appearance == "theme" else "default",
            "theme_css": theme_css,
            "custom_css": custom_css if theme == "custom" else "",
            "balloon_mode": balloon_mode,
            "character_mode": character_mode,
            "slider_mode": slider_mode,
            # chat layout/animation (จาก widget)
            "layout": w.get("layout", "inline"),
            "direction": w.get("direction", "bottom"),
            "animation": w.get("animation", "fade"),
            "exit_animation": w.get("exit_animation", "fade_out"),
            "chat_align": w.get("chat_align", "left"),
            "show_logo": w.get("show_logo", True),
            "show_timestamp": w.get("show_timestamp", False),
            "max_messages": w.get("max_messages", 30),
            # auto-hide
            "auto_hide": w.get("auto_hide", False),
            "hide_after": w.get("hide_after", 8),
            # font (อ่านจาก widget ก่อน ไม่ใช้ shared overlay settings)
            "font_size": w.get("font_size", 18),
            "font_family": w.get("font_family", getattr(s, "overlay_font_family", "Kanit")),
            "font_weight": w.get("font_weight", "600"),
            "text_color": w.get("font_color", "#ffffff"),
            # stroke/shadow (จาก widget — แยก stroke/shadow ชัดเจน)
            "text_stroke": w.get("text_stroke", True),
            "text_stroke_color": w.get("text_stroke_color", "#000000"),
            "text_stroke_width": w.get("text_stroke_width", 2),
            "text_shadow": w.get("text_shadow", True),
            "text_shadow_color": w.get("text_shadow_color", "#000000"),
            "text_shadow_blur": w.get("text_shadow_blur", 3),
            # box (จาก widget — ครบทุก field)
            "box_enabled": w.get("box_enabled", True),
            "box_bg_color": w.get("bg_color", "#0a0e1a"),
            "box_bg_opacity": w.get("bg_opacity", 0.0),
            "box_radius": w.get("box_radius", 8),
            "box_padding": w.get("box_padding", 8),
            "chat_padding": w.get("chat_padding", 12),
            "box_border": w.get("box_border", False),
            "box_border_width": w.get("box_border_width", 1),
            "box_border_color": w.get("box_border_color", "#ffffff"),
            "box_shadow": w.get("box_shadow", True),
            "box_blur": 0,
            "box_glow": w.get("box_glow", False),
            "box_glow_color": w.get("box_glow_color", "#a855f7"),
            "box_width": w.get("box_width", "fit"),
            "msg_spacing": w.get("msg_spacing", 4),
            # balloon (per-widget — แยกจาก default/theme สนิท)
            "balloon_hide_after": w.get("balloon_hide_after", 5),
            "balloon_bg_opacity": w.get("balloon_bg_opacity", 0.95),
            "balloon_font_family": w.get("balloon_font_family", "Kanit"),
            "balloon_font_weight": w.get("balloon_font_weight", 600),
            "balloon_font_size": w.get("balloon_font_size", 18),
            "balloon_text_color": w.get("balloon_text_color", "#1a1a2e"),
            "balloon_emote_size": w.get("balloon_emote_size", 28),
            # ★ text slider (Niconico style — ข้อความเลื่อนขวา→ซ้าย แล้วหายไปเอง)
            "slider_font_size": w.get("slider_font_size", 24),
            "slider_font_family": w.get("slider_font_family", "Kanit"),
            "slider_font_weight": w.get("slider_font_weight", 700),
            "slider_text_color": w.get("slider_text_color", "#ffffff"),
            "slider_text_stroke": w.get("slider_text_stroke", False),
            "slider_text_stroke_color": w.get("slider_text_stroke_color", "#000000"),
            "slider_text_stroke_width": w.get("slider_text_stroke_width", 2),
            "slider_text_shadow": w.get("slider_text_shadow", True),
            "slider_text_shadow_color": w.get("slider_text_shadow_color", "#000000"),
            "slider_text_shadow_blur": w.get("slider_text_shadow_blur", 3),
            "slider_duration": w.get("slider_duration", 5.0),
            "slider_emote_size": w.get("slider_emote_size", 28),
            "slider_show_logo": w.get("slider_show_logo", True),
            "slider_lane_height": w.get("slider_lane_height", 40),
            "slider_zone": w.get("slider_zone", "middle"),
            # event colors (จาก settings ทั่วไป)
            "color_sub": getattr(s, "overlay_color_sub", "#f47fff"),
            "color_bits": getattr(s, "overlay_color_bits", "#ffaa00"),
            "color_donate": getattr(s, "overlay_color_donate", "#00ff7f"),
            "color_system": getattr(s, "overlay_color_system", "#aaaaaa"),
            # translator/channel points
            "show_original": getattr(s, "overlay_show_original", True),
            "show_redeem": getattr(s, "overlay_show_redeem", True),
            # emote/animate
            "emote_size": w.get("emote_size", getattr(s, "overlay_emote_size", 28)),
            "animated_emotes": getattr(s, "overlay_animated_emotes", True),
            # ★ per-mode configs (สำหรับ overlay.html per-mode CSS vars)
            "mode_configs": getattr(s, "overlay_mode_configs", {}),
        }
        # ★ character mode → เพิ่ม character settings
        if character_mode:
            config.update({
                "character_mode": True,
                "character_font_family": w.get("character_font_family", "Kanit"),
                "character_font_weight": w.get("character_font_weight", 600),
                "character_font_color": w.get("character_font_color", "#1a1a2e"),
                "character_stroke": w.get("character_stroke", False),
                "character_stroke_width": w.get("character_stroke_width", 2),
                "character_stroke_color": w.get("character_stroke_color", "#000000"),
                "character_shadow": w.get("character_shadow", False),
                "character_shadow_blur": w.get("character_shadow_blur", 3),
                "character_shadow_color": w.get("character_shadow_color", "#000000"),
                "character_emote_size": w.get("character_emote_size", 28),
                "character_name_font_family": w.get("character_name_font_family", "Kanit"),
                "character_name_font_weight": w.get("character_name_font_weight", 600),
                "character_name_color": w.get("character_name_color", "#ffffff"),
                "character_size": w.get("character_size", 120),
                "character_hide_after": w.get("character_hide_after", 6),
                "character_max_on_screen": w.get("character_max_on_screen", 8),
                "character_random_pos": w.get("character_random_pos", True),
                "character_name_size": w.get("character_name_size", 11),
                "character_name_stroke": w.get("character_name_stroke", True),
                "character_name_stroke_color": w.get("character_name_stroke_color", "#000000"),
                "character_name_stroke_width": w.get("character_name_stroke_width", 1),
                "character_name_shadow": w.get("character_name_shadow", True),
                "character_name_shadow_color": w.get("character_name_shadow_color", "#000000"),
                "character_name_shadow_blur": w.get("character_name_shadow_blur", 2),
                "character_show_name": w.get("character_show_name", True),
                "character_show_logo": w.get("character_show_logo", True),
                "character_bubble_width": w.get("character_bubble_width", 500),
            })
        return config

