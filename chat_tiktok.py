"""chat_tiktok.py — TikTok LIVE chat client (isaackogan/TikTokLive)

เชื่อมต่อ TikTok LIVE ผ่านไลบรารี TikTokLive (WebSocket protobuf)
ไม่ต้องใช้ OAuth/login — อ่าน events ได้เลย (comment / gift / like / follow / join)

รับ events:
  - CommentEvent  → chat ปกติ (event="message")
  - GiftEvent     → ของขวัญ (event="gift", amount=diamond_count × repeat_count)
  - LikeEvent     → กดหัวใจ (event="like", amount=like_count)
  - SocialEvent   → ฟอลโล (event="follow")
  - JoinEvent     → เข้าห้อง (event="join")

การใช้งาน:
    client = TikTokChat(on_message=callback)
    client.connect("username")
    ...
    client.disconnect()

Callback ได้รับ ChatMessage dataclass (ร่วมกับ Twitch/YouTube client)
"""
from __future__ import annotations

import asyncio
import threading
import time
from typing import Callable, Optional

from chat_twitch import ChatMessage  # reuse shared dataclass

# TikTokLive imports — ทำ lazy/try-except ไว้ข้างนอกเพื่อ error message ชัดเจน
try:
    from TikTokLive.events import (
        CommentEvent,
        ConnectEvent,
        DisconnectEvent,
        FollowEvent,
        GiftEvent,
        JoinEvent,
        LikeEvent,
        RoomUpdateEvent,
        SocialEvent,
    )
    from TikTokLive.client.client import TikTokLiveClient

    _TIKTOK_AVAILABLE = True
    _IMPORT_ERROR: Optional[str] = None
except Exception as exc:  # noqa: BLE001
    _TIKTOK_AVAILABLE = False
    _IMPORT_ERROR = str(exc)
    CommentEvent = ConnectEvent = DisconnectEvent = None  # type: ignore[assignment]
    FollowEvent = GiftEvent = JoinEvent = LikeEvent = SocialEvent = None  # type: ignore[assignment]
    TikTokLiveClient = None  # type: ignore[assignment]


# ---------------------------------------------------------------------- #
# Helpers — แปลง TikTokLive event → ChatMessage
# ---------------------------------------------------------------------- #


def _user_display_name(user) -> str:
    """ดึง display name จาก ExtendedUser (nickname หรือ unique_id หรือ id)"""
    if user is None:
        return "?"
    # nickname = display name ที่ user ตั้ง (มีภาษาไทย/unicode ได้)
    nick = getattr(user, "nickname", None)
    if nick:
        return nick
    uid = getattr(user, "unique_id", None)
    if uid:
        return uid
    return str(getattr(user, "id", "?"))


def _build_gift_text(event) -> tuple[str, int, Optional[str]]:
    """สร้างข้อความบรรยายของขวัญ → (display_text, diamond_amount, system_text)

    gift แบบ streak/combo: TikTokLive ส่ง event หลายครั้ง (repeat_count เพิ่มทีละ 1)
    repeat_end=1 หมายถึง "จบ streak แล้ว" → เราใช้ค่าสะสมตอนนี้เป็นยอดสุดท้าย
    """
    gift = getattr(event, "gift", None)
    repeat_count = getattr(event, "repeat_count", 1) or 1
    combo_count = getattr(event, "combo_count", 0) or 0

    # ชื่อของขวัญ
    gift_name = ""
    diamond_count = 0
    if gift is not None:
        gift_name = getattr(gift, "name", "") or getattr(gift, "describe", "") or "ของขวัญ"
        diamond_count = getattr(gift, "diamond_count", 0) or 0

    # ยอดรวม (diamond × repeat) — repeat_count คือจำนวนที่ส่งในครั้งนี้
    total_diamonds = diamond_count * max(repeat_count, 1)

    # ข้อความสำหรับแสดงในแชท
    if gift_name and diamond_count > 0:
        display = f"🎁 ส่ง {gift_name} ×{repeat_count}"
        system = f"ส่ง {gift_name} {total_diamonds} เพชร"
    elif gift_name:
        display = f"🎁 ส่ง {gift_name} ×{repeat_count}"
        system = f"ส่ง {gift_name}"
    else:
        display = "🎁 ส่งของขวัญ"
        system = "ส่งของขวัญ"

    return display, total_diamonds, system


# ---------------------------------------------------------------------- #
# TikTok LIVE client
# ---------------------------------------------------------------------- #


class TikTokChat:
    """TikTok LIVE chat client — ใช้ TikTokLive library (WebSocket)

    รัน asyncio event loop ใน background thread (daemon)
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

        self._client: Optional["TikTokLiveClient"] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._is_connected = False
        self._is_connecting = False
        self._should_stop = False
        self._unique_id = ""

        # สถิติ
        self.messages_read = 0

    # ------------------------------------------------------------------ #
    # Availability
    # ------------------------------------------------------------------ #
    @staticmethod
    def is_available() -> bool:
        """เช็คว่าติดตั้ง TikTokLive library แล้วหรือไม่"""
        return _TIKTOK_AVAILABLE

    @staticmethod
    def import_error() -> Optional[str]:
        """ข้อความ error ถ้า import ล้มเหลว"""
        return _IMPORT_ERROR

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    # ------------------------------------------------------------------ #
    # Connection
    # ------------------------------------------------------------------ #
    def connect(self, unique_id: str) -> bool:
        """เชื่อมต่อ TikTok LIVE — unique_id คือ @username (ไม่ต้องมี @)

        Returns True ถ้าเริ่มเชื่อมต่อสำเร็จ (connection เกิดขึ้น async)
        """
        if not _TIKTOK_AVAILABLE:
            self.on_error(
                f"ไม่ได้ติดตั้ง TikTokLive library: {_IMPORT_ERROR}\n"
                "ติดตั้งด้วย: pip install TikTokLive"
            )
            return False

        unique_id = unique_id.strip().lstrip("@").strip()
        # ถ้าใส่ URL เต็ม → เอาเฉพาะ username
        if "/" in unique_id:
            unique_id = unique_id.rstrip("/").split("/")[-1]
        if not unique_id:
            self.on_error("กรุณาใส่ชื่อ TikTok (@username)")
            return False

        if self._is_connected or self._is_connecting:
            self.on_error("เชื่อมต่ออยู่แล้ว — กด Disconnect ก่อน")
            return False

        self._unique_id = unique_id
        self._should_stop = False
        self._is_connecting = True

        # เริ่ม asyncio loop ใน background thread
        self._thread = threading.Thread(
            target=self._run_loop, name="TikTokLiveThread", daemon=True
        )
        self._thread.start()
        return True

    def disconnect(self) -> None:
        """ยกเลิกการเชื่อมต่อ"""
        self._should_stop = True
        self._is_connecting = False

        # สั่ง stop ใน asyncio loop
        if self._loop is not None and self._loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(self._stop_async(), self._loop)
            except Exception:  # noqa: BLE001
                pass

        self._is_connected = False
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._thread = None
        self._loop = None
        self._client = None
        self.on_status("⚪ ยกเลิกการเชื่อมต่อ TikTok")

    async def _stop_async(self) -> None:
        """หยุด client ใน asyncio context"""
        if self._client is not None:
            try:
                await self._client.stop()
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------ #
    # Asyncio background loop
    # ------------------------------------------------------------------ #
    def _run_loop(self) -> None:
        """รัน asyncio event loop ใน background thread"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            loop.run_until_complete(self._connect_and_listen())
        except Exception as exc:  # noqa: BLE001
            if not self._should_stop:
                self.on_error(f"TikTok connection error: {exc}")
        finally:
            self._is_connected = False
            self._is_connecting = False
            try:
                loop.close()
            except Exception:  # noqa: BLE001
                pass

    async def _connect_and_listen(self) -> None:
        """สร้าง client + connect + register listeners + รัน forever"""
        assert TikTokLiveClient is not None

        try:
            self._client = TikTokLiveClient(unique_id=self._unique_id)
        except Exception as exc:  # noqa: BLE001
            self.on_error(f"สร้าง TikTok client ไม่ได้: {exc}")
            self._is_connecting = False
            return

        # register listeners
        @self._client.on(ConnectEvent)  # type: ignore[union-attr]
        async def on_connect(event):  # noqa: ANN001
            self._is_connected = True
            self._is_connecting = False
            self.on_status(f"✅ เชื่อมต่อ TikTok @{self._unique_id}")

        @self._client.on(DisconnectEvent)  # type: ignore[union-attr]
        async def on_disconnect(event):  # noqa: ANN001
            self._is_connected = False
            if not self._should_stop:
                self.on_status("⚠️ TikTok ถูกตัดการเชื่อมต่อ")

        @self._client.on(CommentEvent)  # type: ignore[union-attr]
        async def on_comment(event):  # noqa: ANN001
            self.messages_read += 1
            author = _user_display_name(event.user)
            text = getattr(event, "content", "") or ""
            # emotes ใน comment → แปลงเป็น segments (URL-based, เหมือน MyLive/YouTube)
            segments = [{"type": "text", "content": text}] if text else []
            for em in getattr(event, "emotes", []) or []:
                emote_model = getattr(em, "emote", None) or em
                url = ""
                for attr in ("image", "icon"):
                    img = getattr(emote_model, attr, None)
                    if img is not None:
                        url = getattr(img, "url", "") or ""
                        if url:
                            break
                if url:
                    segments.append({"type": "emote", "url": url, "name": ""})
            extra = {
                "tiktok_user_id": getattr(event.user, "id", None) if event.user else None,
                "segments": segments if len(segments) > 1 else None,
            }
            self.on_message(
                ChatMessage(
                    platform="tiktok",
                    author=author,
                    text=text,
                    event="message",
                    extra=extra,
                )
            )

        @self._client.on(GiftEvent)  # type: ignore[union-attr]
        async def on_gift(event):  # noqa: ANN001
            # streak/combo handling — เก็บเฉพาะตอน repeat_end หรือ event แรก
            # (TikTokLive ส่งซ้ำเพื่ออัปเดต combo; เราแจ้งทุกครั้งแต่ amount = diamond × repeat)
            author = _user_display_name(event.user)
            display, total_diamonds, system = _build_gift_text(event)
            gift = getattr(event, "gift", None)
            gift_name = ""
            gift_icon = ""
            if gift is not None:
                gift_name = getattr(gift, "name", "") or ""
                icon_img = getattr(gift, "image", None) or getattr(gift, "icon", None)
                if icon_img is not None:
                    gift_icon = getattr(icon_img, "url", "") or ""
            self.messages_read += 1
            extra = {
                "tiktok_user_id": getattr(event.user, "id", None) if event.user else None,
                "gift_name": gift_name,
                "gift_icon": gift_icon,
                "gift_id": getattr(event, "gift_id", None),
                "repeat_count": getattr(event, "repeat_count", 1) or 1,
                "diamond_count": getattr(gift, "diamond_count", 0) if gift else 0,
                "repeat_end": getattr(event, "repeat_end", 0),
            }
            self.on_message(
                ChatMessage(
                    platform="tiktok",
                    author=author,
                    text=display,
                    event="gift",
                    amount=total_diamonds,
                    system_text=system,
                    extra=extra,
                )
            )

        @self._client.on(LikeEvent)  # type: ignore[union-attr]
        async def on_like(event):  # noqa: ANN001
            author = _user_display_name(event.user)
            like_count = getattr(event, "total_count", 1) or getattr(event, "count", 1) or 1
            self.messages_read += 1
            self.on_message(
                ChatMessage(
                    platform="tiktok",
                    author=author,
                    text=f"❤️ กดหัวใจ ×{like_count}",
                    event="like",
                    amount=like_count,
                    extra={
                        "tiktok_user_id": getattr(event.user, "id", None)
                        if event.user
                        else None,
                    },
                )
            )

        @self._client.on(FollowEvent)  # type: ignore[union-attr]
        async def on_follow(event):  # noqa: ANN001
            author = _user_display_name(getattr(event, "user", None))
            self.messages_read += 1
            self.on_message(
                ChatMessage(
                    platform="tiktok",
                    author=author,
                    text="⭐ ฟอลโล",
                    event="follow",
                    extra={
                        "tiktok_user_id": getattr(event.user, "id", None)
                        if event.user
                        else None,
                    },
                )
            )

        @self._client.on(SocialEvent)  # type: ignore[union-attr]
        async def on_social(event):  # noqa: ANN001
            # SocialEvent = share/follow ทั่วไป — เช็ค display_type
            author = _user_display_name(getattr(event, "user", None))
            display_type = ""
            common = getattr(event, "common", None)
            if common is not None:
                display_type = getattr(common, "display_type", "") or ""
            # share = แชร์, follow = ฟอลโล (ถ้าไม่ซ้ำกับ FollowEvent)
            if "share" in display_type.lower():
                self.messages_read += 1
                self.on_message(
                    ChatMessage(
                        platform="tiktok",
                        author=author,
                        text="📤 แชร์ไลฟ์",
                        event="share",
                        extra={
                            "tiktok_user_id": getattr(event.user, "id", None)
                            if event.user
                            else None,
                        },
                    )
                )
            # อื่นๆ ข้าม (FollowEvent จัดการ follow อยู่แล้ว)

        @self._client.on(JoinEvent)  # type: ignore[union-attr]
        async def on_join(event):  # noqa: ANN001
            author = _user_display_name(getattr(event, "user", None))
            self.messages_read += 1
            self.on_message(
                ChatMessage(
                    platform="tiktok",
                    author=author,
                    text="👋 เข้าร่วมไลฟ์",
                    event="join",
                    extra={
                        "tiktok_user_id": getattr(event.user, "id", None)
                        if event.user
                        else None,
                    },
                )
            )

        # viewer count — TikTok push event ~ทุก 5-10s
        @self._client.on(RoomUpdateEvent)  # type: ignore[union-attr]
        async def on_room_update(event):  # noqa: ANN001
            try:
                count = getattr(event, "viewer_count", None)
                if count is not None:
                    self.on_viewer_count("tiktok", int(count))
            except Exception:
                pass

        # connect + รัน forever (จนกว่าจะ disconnect)
        try:
            await self._client.start(
                process_connect_events=True,
                fetch_room_info=True,  # เพื่อ initial viewer count
                fetch_gift_info=False,
                fetch_live_check=True,
            )
        except Exception as exc:  # noqa: BLE001
            err_msg = str(exc)
            if not self._should_stop:
                # แยก error ที่พบบ่อย
                if "live" in err_msg.lower() and (
                    "not" in err_msg.lower() or "offline" in err_msg.lower()
                ):
                    self.on_error(
                        f"TikTok: @{self._unique_id} ไม่ได้ไลฟ์อยู่ (offline)"
                    )
                elif "user" in err_msg.lower() and "not found" in err_msg.lower():
                    self.on_error(f"TikTok: ไม่พบ user @{self._unique_id}")
                else:
                    self.on_error(f"TikTok connect error: {err_msg}")
            self._is_connecting = False


# ---------------------------------------------------------------------- #
# Smoke test
# ---------------------------------------------------------------------- #
if __name__ == "__main__":
    import sys

    if not _TIKTOK_AVAILABLE:
        print(f"TikTokLive ไม่พร้อมใช้งาน: {_IMPORT_ERROR}")
        print("ติดตั้งด้วย: pip install TikTokLive")
        sys.exit(1)

    if len(sys.argv) < 2:
        print("Usage: python chat_tiktok.py <username> [seconds]")
        print("Example: python chat_tiktok.py someuser 30")
        sys.exit(1)

    username = sys.argv[1]
    duration = int(sys.argv[2]) if len(sys.argv) > 2 else 30

    def cb(msg: ChatMessage) -> None:
        prefix = msg.event.upper()
        amount_str = f" [{msg.amount}]" if msg.amount else ""
        sys_str = f"  ({msg.system_text})" if msg.system_text else ""
        print(f"[{prefix}] {msg.author}{amount_str}: {msg.text}{sys_str}")

    def status(msg: str) -> None:
        print(f">> {msg}")

    client = TikTokChat(on_message=cb, on_status=status, on_error=status)
    if client.connect(username):
        time.sleep(duration)
        client.disconnect()
        print(f">> read {client.messages_read} events")
