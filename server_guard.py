"""server_guard.py — Origin guard middleware (กัน CSRF + cross-origin WebSocket)

★ หลักการ (แบบเบา — ไม่กระทบผู้ใช้ปัจจุบัน):
  บล็อคเฉพาะ method ที่เปลี่ยน state (POST/PUT/DELETE) + WS handshake
  ยอมรับ Origin:
    - ไม่ส่ง header (client ที่ไม่ใช่ browser: OBS CEF บางกรณี, Python requests, curl)
    - "null" (OBS Browser Source โหลด URL ตรงๆ ส่ง Origin: null)
    - http://localhost:* / http://127.0.0.1:* (โปรแกรมตัวเอง + iframe ภายใน)
  บล็อค: Origin ที่เป็นโดเมนภายนอก (เว็บที่ user เปิดใน browser ยิงเข้ามา)

★ GET ธรรมดาไม่ถูกเช็ค — เพราะ OBS/overlay ต้องโหลด asset (html/js/logo) ได้อิสระ
"""
from __future__ import annotations

import re

import aiohttp.web as web

_LOCAL_ORIGIN_RE = re.compile(r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$", re.IGNORECASE)


def make_origin_guard_middleware(server_name: str = "server"):
    """สร้าง aiohttp middleware สำหรับกัน cross-origin request จากเว็บภายนอก"""

    @web.middleware
    async def origin_guard(request, handler):
        is_ws = request.headers.get("Upgrade", "").lower() == "websocket"
        if request.method in ("POST", "PUT", "DELETE") or (request.method == "GET" and is_ws):
            origin = request.headers.get("Origin")
            if origin and origin != "null" and not _LOCAL_ORIGIN_RE.match(origin):
                # ★ เว็บภายนอกพยายามยิงเข้ามา (CSRF / cross-origin WS) — ปฏิเสธ
                import logging
                logging.getLogger(server_name).warning(
                    f"blocked cross-origin {request.method} {request.path} from {origin}"
                )
                if is_ws:
                    return web.Response(status=403, text="forbidden origin")
                return web.json_response({"error": "forbidden origin"}, status=403)
        return await handler(request)

    return origin_guard
