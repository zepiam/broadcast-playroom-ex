"""chat_kick.py — KICK (kick.com) live chat client

เชื่อมต่อ KICK chat ผ่าน Pusher WebSocket (anonymous/read-only — ไม่ต้อง OAuth)

วิธีเชื่อม:
  1. HTTP resolve: GET kick.com/api/v2/channels/{slug}
     (header Accept-Language: en-US สำคัญ กัน Cloudflare 403)
     → ได้ chatroom.id
  2. Pusher WebSocket: wss://ws-us2.pusher.com/app/{APP_KEY}?protocol=7
     → subscribe "chatrooms.{id}.v2" (auth="" = anonymous)
  3. รับ events:
     - AppMessageEvent            → chat ปกติ (event="message")
     - GiftedSubscriptionsEvent   → มอบ sub (event="subgift")
     - LuckyUsersWhoGotGiftSubscriptionsEvent → ผู้รับ sub (event="subgift")
     - pusher:ping                → ตอบ pusher:pong (keepalive)

ข้อจำกัด (anonymous channel):
  - ไม่มี bits/donations (KICK ส่งผ่าน Streamlabs/StreamElements แยก)
  - ไม่มี raids/follows (ต้อง OAuth EventSub)
  - ได้แค่ chat + gifted subscriptions

การใช้งาน:
    client = KickChat(on_message=callback)
    client.connect("trainwreckstv")  # slug (username)
    ...
    client.disconnect()
"""
from __future__ import annotations

import json
import re
import threading
import time
from typing import Callable, Optional

from chat_twitch import ChatMessage  # reuse shared dataclass

# websocket-client (sync) — daemon thread เหมือน Twitch IRC
try:
    import websocket
    _WS_AVAILABLE = True
    _WS_IMPORT_ERROR: Optional[str] = None
except Exception as exc:  # noqa: BLE001
    _WS_AVAILABLE = False
    _WS_IMPORT_ERROR = str(exc)
    websocket = None  # type: ignore[assignment]

# ---------------------------------------------------------------------- #
# KICK API constants
# ---------------------------------------------------------------------- #
KICK_API_BASE = "https://kick.com/api/v2/channels"
# KICK ใช้ Pusher cluster ws-us2 + public app key (ค่า default ของหน้าเว็บ)
KICK_PUSHER_CLUSTER = "ws-us2"
KICK_PUSHER_APP_KEY = "32cbd69e4b950bf97679"
KICK_PUSHER_URL = (
    f"wss://{KICK_PUSHER_CLUSTER}.pusher.com/app/{KICK_PUSHER_APP_KEY}"
    "?protocol=7&client=js&version=8.4.0"
)
# header สำคัญ — Accept-Language: en-US กัน Cloudflare 403
KICK_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}

# regex strip [emote:id:name] tokens ออกจากข้อความ
_EMOTE_TOKEN_RE = re.compile(r"\[\d+:\d+[^\]]*\]")
# กระชับ space หลายช่อง
_MULTI_SPACE_RE = re.compile(r" {2,}")


def _strip_emote_tokens(text: str) -> tuple[str, list]:
    """ตัด [id:id:name] tokens ออกจาก text → (clean_text, segments)

    KICK ส่ง emote เป็น [id:id:name] ฝังในข้อความ
    Returns: (text ที่ตัด emote แล้ว, segments list สำหรับ render ภาพ)
    segments format: [{type:"text", content:"..."}, {type:"emote", url:"...", name:"..."}]
    KICK emote image URL: https://static-cdn.kick.com/images/emote/{id}/fullsize/image
    """
    if not text:
        return "", []
    segments = []
    last_pos = 0
    for m in _EMOTE_TOKEN_RE.finditer(text):
        # text ก่อน emote
        before = text[last_pos:m.start()]
        if before:
            segments.append({"type": "text", "content": before})
        # emote token → [id:id:name]
        token = m.group(0)
        inner = token.strip("[]")
        parts = inner.split(":")
        if len(parts) >= 3:
            emote_id = parts[1]
            emote_name = parts[2]
            url = f"https://static-cdn.kick.com/images/emote/{emote_id}/fullsize/image"
            segments.append({"type": "emote", "url": url, "name": emote_name})
        last_pos = m.end()
    # text หลัง emote สุดท้าย
    after = text[last_pos:]
    if after:
        segments.append({"type": "text", "content": after})
    # clean text = ตัด tokens ออก
    clean = _EMOTE_TOKEN_RE.sub("", text)
    clean = _MULTI_SPACE_RE.sub(" ", clean).strip()
    # ถ้าไม่มี emote เลย → ไม่ส่ง segments (ใช้ text ปกติ)
    has_emote = any(s.get("type") == "emote" for s in segments)
    return clean, segments if has_emote else []


def _resolve_channel(slug: str, timeout: float = 15.0) -> Optional[dict]:
    """HTTP resolve slug → channel info

    Returns: dict {chatroom_id, user_id, username} หรือ None ถ้า fail
    """
    import requests
    url = f"{KICK_API_BASE}/{slug}"
    try:
        r = requests.get(url, headers=KICK_HEADERS, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"เชื่อม KICK API ไม่ได้: {exc}")
    if r.status_code == 404:
        raise RuntimeError(f"ไม่พบ channel KICK: {slug}")
    if r.status_code != 200:
        raise RuntimeError(f"KICK API error {r.status_code}: {r.text[:120]}")
    try:
        d = r.json()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"KICK API: parse JSON ไม่ได้: {exc}")
    chatroom = d.get("chatroom") or {}
    chatroom_id = chatroom.get("id") or d.get("chatroom_id")
    if not chatroom_id:
        raise RuntimeError(f"KICK API: ไม่พบ chatroom_id สำหรับ {slug}")
    user = d.get("user") or {}
    livestream = d.get("livestream") or {}
    viewer_count = livestream.get("viewer_count", 0) if livestream else 0
    return {
        "chatroom_id": int(chatroom_id),
        "user_id": d.get("id") or user.get("id"),
        "username": user.get("username") or d.get("slug") or slug,
        "is_live": bool(d.get("livestream")),
        "viewer_count": int(viewer_count) if viewer_count else 0,
    }


# ---------------------------------------------------------------------- #
# KICK chat client
# ---------------------------------------------------------------------- #
class KickChat:
    """KICK live chat client — Pusher WebSocket (anonymous)

    รัน sync websocket loop ใน background daemon thread
    """

    def __init__(
        self,
        on_message: Callable[[ChatMessage], None],
        on_status: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        on_viewer_count: Optional[Callable[[str, int], None]] = None,
    ) -> None:
        self.on_message = on_message
        self.on_status = on_status or (lambda msg: None)
        self.on_error = on_error or (lambda msg: None)
        self.on_viewer_count = on_viewer_count or (lambda plat, cnt: None)

        self._ws: Optional["websocket.WebSocket"] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._is_connected = False
        self._slug = ""
        self._chatroom_id: Optional[int] = None
        self._last_viewer_poll: float = 0.0

        self.messages_read = 0

    # ------------------------------------------------------------------ #
    # Availability
    # ------------------------------------------------------------------ #
    @staticmethod
    def is_available() -> bool:
        return _WS_AVAILABLE

    @staticmethod
    def import_error() -> Optional[str]:
        return _WS_IMPORT_ERROR

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    # ------------------------------------------------------------------ #
    # Connection
    # ------------------------------------------------------------------ #
    def connect(self, slug: str) -> bool:
        """เชื่อมต่อ KICK — slug = username (เช่น 'trainwreckstv')

        Returns True ถ้า resolve สำเร็จ + เริ่ม WS loop
        """
        if not _WS_AVAILABLE:
            self.on_error(
                f"ไม่ได้ติดตั้ง websocket-client: {_WS_IMPORT_ERROR}\n"
                "ติดตั้งด้วย: pip install websocket-client"
            )
            return False

        # normalize slug — เอา URL ออก, เอา @ ออก
        slug = (slug or "").strip().lstrip("@").strip()
        if "/" in slug:
            slug = slug.rstrip("/").split("/")[-1]
        if not slug:
            self.on_error("กรุณาใส่ชื่อ KICK channel (slug)")
            return False
        if self._is_connected:
            self.on_error("เชื่อมต่อ KICK อยู่แล้ว — กด Disconnect ก่อน")
            return False

        # resolve slug → chatroom_id
        try:
            info = _resolve_channel(slug)
        except RuntimeError as exc:
            self.on_error(str(exc))
            return False
        self._slug = slug
        self._chatroom_id = info["chatroom_id"]
        self._stop_event.clear()
        # emit initial viewer count (จาก resolve response)
        vc = info.get("viewer_count", 0)
        if vc:
            self.on_viewer_count("kick", vc)

        # เริ่ม WS loop ใน background thread
        self._thread = threading.Thread(
            target=self._ws_loop, name="KickWSReader", daemon=True,
        )
        self._thread.start()
        return True

    def disconnect(self) -> None:
        """ยกเลิกการเชื่อมต่อ"""
        self._stop_event.set()
        self._is_connected = False
        if self._ws is not None:
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=4)
        self._thread = None
        self.on_status("⚪ ยกเลิกการเชื่อมต่อ KICK")

    # ------------------------------------------------------------------ #
    # WebSocket loop (background thread)
    # ------------------------------------------------------------------ #
    def _ws_loop(self) -> None:
        """รัน WS connect + read loop จนกว่าจะ disconnect"""
        assert websocket is not None
        chatroom_id = self._chatroom_id
        try:
            ws = websocket.WebSocket()
            ws.settimeout(5.0)  # short timeout → ตอบ _stop_event ได้
            ws.connect(KICK_PUSHER_URL)
            self._ws = ws
        except Exception as exc:  # noqa: BLE001
            if not self._stop_event.is_set():
                self.on_error(f"KICK WS เชื่อมต่อไม่ได้: {exc}")
            self._is_connected = False
            return

        # subscribe to chatroom channel (anonymous — auth ว่าง)
        channel = f"chatrooms.{chatroom_id}.v2"
        try:
            ws.send(json.dumps({
                "event": "pusher:subscribe",
                "data": {"auth": "", "channel": channel},
            }))
        except Exception as exc:  # noqa: BLE001
            if not self._stop_event.is_set():
                self.on_error(f"KICK subscribe ไม่ได้: {exc}")
            self._is_connected = False
            return

        self._is_connected = True
        self.on_status(f"✅ เชื่อมต่อ KICK @{self._slug}")

        # read loop
        while not self._stop_event.is_set():
            try:
                raw = ws.recv()
            except Exception as exc:  # noqa: BLE001
                # timeout → loop ใหม่ (เช็ค _stop_event + poll viewer count)
                if "timed out" in str(exc).lower():
                    self._poll_viewer_count()
                    continue
                if not self._stop_event.is_set():
                    self.on_error(f"KICK WS หลุด: {exc}")
                break
            if not raw:
                continue
            try:
                self._handle_raw(raw)
            except Exception as exc:  # noqa: BLE001
                # ไม่ drop connection เพราะ parse error ตัวเดียว
                if not self._stop_event.is_set():
                    pass  # silent — กัน log spam

        self._is_connected = False
        try:
            ws.close()
        except Exception:
            pass

    def _poll_viewer_count(self) -> None:
        """re-poll KICK resolve endpoint เพื่ออัปเดต viewer count (ทุก ~60s)"""
        if self._stop_event.is_set() or not self._slug:
            return
        import time as _time
        now = _time.time()
        if now - self._last_viewer_poll < 55:
            return
        try:
            info = _resolve_channel(self._slug)
            vc = info.get("viewer_count", 0)
            self.on_viewer_count("kick", vc)
        except Exception:
            pass
        self._last_viewer_poll = now

    # ------------------------------------------------------------------ #
    # Event dispatch
    # ------------------------------------------------------------------ #
    def _handle_raw(self, raw: str) -> None:
        """parse Pusher message → dispatch event"""
        try:
            envelope = json.loads(raw)
        except Exception:
            return
        event = envelope.get("event", "")
        channel = envelope.get("channel", "")
        data_raw = envelope.get("data", "")

        # keepalive
        if event == "pusher:ping":
            try:
                self._ws.send(json.dumps({"event": "pusher:pong", "data": {}}))
            except Exception:
                pass
            return
        if event == "pusher:error":
            err = data_raw if isinstance(data_raw, dict) else {}
            msg = err.get("message", "unknown pusher error")
            if not self._stop_event.is_set():
                self.on_error(f"KICK Pusher error: {msg}")
            return
        # subscription ack — ignore
        if event in (
            "pusher:connection_established",
            "pusher_internal:subscription_succeeded",
        ):
            return

        # parse data (Pusher ส่ง data เป็น JSON string ในหลายกรณี)
        data = data_raw
        if isinstance(data, str) and data:
            try:
                data = json.loads(data)
            except Exception:
                pass
        if not isinstance(data, dict):
            return

        # ── chat message ──
        if event in ("AppMessageEvent", "App\\Events\\ChatMessageEvent", "message"):
            self._handle_chat(data)
        # ── gifted subscription ──
        elif event in (
            "App\\Events\\GiftedSubscriptionsEvent",
            "GiftedSubscriptionsEvent",
        ):
            self._handle_gifted_sub(data, is_gifter=True)
        elif event in (
            "App\\Events\\LuckyUsersWhoGotGiftSubscriptionsEvent",
            "LuckyUsersWhoGotGiftSubscriptionsEvent",
        ):
            self._handle_gifted_sub(data, is_gifter=False)
        # ── stream status (optional — ignore เพื่อลด noise) ──
        elif event in (
            "App\\Events\\StreamerIsLive",
            "StreamerIsLive",
            "App\\Events\\StopStreamBroadcast",
            "StopStreamBroadcast",
        ):
            pass
        # อื่นๆ — ignore (PinMessage, UserBannedFromChannel, etc.)

    def _handle_chat(self, data: dict) -> None:
        """KICK chat message → ChatMessage(event="message")"""
        content = data.get("content", "") or ""
        author_data = data.get("author") or data.get("sender") or {}
        author = (
            author_data.get("username")
            or author_data.get("name")
            or data.get("username")
            or "?"
        )
        clean_text, segments = _strip_emote_tokens(content)
        self.messages_read += 1
        self.on_message(
            ChatMessage(
                platform="kick",
                author=author,
                text=clean_text,
                event="message",
                extra={
                    "kick_user_id": author_data.get("id"),
                    "segments": segments if segments else None,
                },
            )
        )

    def _handle_gifted_sub(self, data: dict, is_gifter: bool) -> None:
        """KICK gifted subscription → ChatMessage(event="subgift")

        is_gifter=True = คนที่มอบ sub (GiftedSubscriptionsEvent)
        is_gifter=False = คนที่รับ sub (LuckyUsersWhoGotGiftSubscriptionsEvent)
        """
        # structure ประมาณ: {gifter_user: {username}, gifted_user: {...}, ...}
        gifter = data.get("gifter") or data.get("gifter_user") or {}
        gifted = data.get("gifted") or data.get("gifted_user") or data.get("user") or {}
        if is_gifter:
            author = gifter.get("username") or gifter.get("name") or "?"
            sys_text = "มอบ KICK Sub"
            # มีจำนวน?
            count = data.get("gifted_amount") or data.get("quantity") or 1
            if count and int(count) > 1:
                sys_text = f"มอบ KICK Sub ×{count}"
        else:
            author = gifted.get("username") or gifted.get("name") or "?"
            sys_text = "ได้รับ KICK Sub"
        display = f"🎁 {sys_text}"
        self.messages_read += 1
        self.on_message(
            ChatMessage(
                platform="kick",
                author=author,
                text=display,
                event="subgift",
                system_text=sys_text,
                extra={
                    "kick_user_id": (gifter if is_gifter else gifted).get("id"),
                    "is_gifter": is_gifter,
                },
            )
        )


# ---------------------------------------------------------------------- #
# Smoke test
# ---------------------------------------------------------------------- #
if __name__ == "__main__":
    import sys

    if not _WS_AVAILABLE:
        print(f"websocket-client ไม่พร้อม: {_WS_IMPORT_ERROR}")
        print("ติดตั้งด้วย: pip install websocket-client")
        sys.exit(1)

    if len(sys.argv) < 2:
        print("Usage: python chat_kick.py <slug> [seconds]")
        print("Example: python chat_kick.py trainwreckstv 20")
        sys.exit(1)

    slug = sys.argv[1]
    duration = int(sys.argv[2]) if len(sys.argv) > 2 else 20

    def cb(msg: ChatMessage) -> None:
        amount_str = f" [{msg.amount}]" if msg.amount else ""
        sys_str = f"  ({msg.system_text})" if msg.system_text else ""
        print(f"[{msg.event}] {msg.author}{amount_str}: {msg.text}{sys_str}")

    def status(msg: str) -> None:
        print(f">> {msg}")

    client = KickChat(on_message=cb, on_status=status, on_error=status)
    if client.connect(slug):
        time.sleep(duration)
        client.disconnect()
        print(f">> read {client.messages_read} messages")
