"""chat_youtube.py — YouTube live chat reader (direct InnerTube API)

วิธีการที่ทำงาน (ค.ศ. 2026):
  1. GET watch page (ด้วย bpctr=9999999999 ข้าม consent check)
     → หา continuation token จาก reloadContinuationData
  2. POST live_chat/get_live_chat ด้วย token
     → ได้ actions (chat messages) + next continuation token
  3. loop เรียก get_live_chat ซ้ำด้วย next token

ไม่ต้องใช้ library เสริม (chat-downloader/yt-dlp) — ใช้ requests อย่างเดียว
ไม่ต้อง OAuth — anonymous read-only

การใช้งาน:
    client = YouTubeChat(on_message=cb)
    client.connect("https://www.youtube.com/watch?v=XXXX")
    # หรือ: video ID 11 หลัก, /live URL, youtu.be short URL
    ...
    client.disconnect()

Events ที่ detect:
  - liveChatTextMessageRenderer       → chat ปกติ
  - liveChatPaidMessageRenderer       → SuperChat
  - liveChatMembershipItemRenderer    → membership
  - liveChatSponsorshipsGiftRedemptionNotification → gift
"""
from __future__ import annotations

import json
import re
import threading
import time
from typing import Callable, Optional

import requests

from chat_twitch import ChatMessage  # reuse shared dataclass

# ---------------------------------------------------------------------- #
# Constants
# ---------------------------------------------------------------------- #
INNERTUBE_API_URL = "https://www.youtube.com/youtubei/v1/live_chat/get_live_chat"
INNERTUBE_CLIENT_VERSION = "2.20250723.00.00"
# public API key (hardcoded ในหน้า YouTube — ใช้ได้ anonymous)
INNERTUBE_API_KEY = "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)


class YouTubeChat:
    """YouTube live chat reader — direct InnerTube API polling"""

    def __init__(
        self,
        on_message: Callable[[ChatMessage], None],
        on_status: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        on_viewer_count: Optional[Callable[[str, int], None]] = None,
        poll_interval: float = 2.0,
    ) -> None:
        self.on_message = on_message
        self.on_status = on_status or (lambda msg: None)
        self.on_error = on_error or (lambda msg: None)
        self.on_viewer_count = on_viewer_count or (lambda plat, cnt: None)
        self.poll_interval = poll_interval

        self._session = requests.Session()
        self._session.headers["User-Agent"] = USER_AGENT
        self._session.headers["Accept-Language"] = "en-US,en;q=0.9"

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._is_connected = False
        self._continuation: Optional[str] = None
        self._video_id: str = ""
        self._video_url: str = ""
        self._last_viewer_poll: float = 0.0  # timestamp ของ viewer count poll ล่าสุด

        self.messages_read = 0
        # dedupe message IDs (กัน duplicate ตอน re-fetch)
        self._seen_ids: set[str] = set()

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    # ------------------------------------------------------------------ #
    # URL → video ID
    # ------------------------------------------------------------------ #
    @staticmethod
    def _extract_video_id(text: str) -> Optional[str]:
        """แยก video ID จาก URL หรือ input ตรงๆ"""
        text = (text or "").strip()
        if not text:
            return None
        if re.fullmatch(r"[A-Za-z0-9_-]{11}", text):
            return text
        patterns = [
            r"youtube\.com/watch\?v=([A-Za-z0-9_-]{11})",
            r"youtu\.be/([A-Za-z0-9_-]{11})",
            r"youtube\.com/live/([A-Za-z0-9_-]{11})",
            r"youtube\.com/embed/([A-Za-z0-9_-]{11})",
            r"[?&]v=([A-Za-z0-9_-]{11})",
        ]
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                return m.group(1)
        return None

    # ------------------------------------------------------------------ #
    # Connection
    # ------------------------------------------------------------------ #
    def connect(self, url_or_id: str) -> bool:
        """เชื่อมต่อ YouTube live chat

        Args:
            url_or_id: video URL / video ID / live URL
        Returns True ถ้าเริ่ม polling สำเร็จ
        """
        video_id = self._extract_video_id(url_or_id)
        if not video_id:
            self.on_error("YouTube: ไม่พบ Video ID — ใส่ URL หรือ Video ID 11 หลัก")
            return False
        if self._is_connected:
            self.on_error("เชื่อมต่อ YouTube อยู่แล้ว — กด Disconnect ก่อน")
            return False

        self._video_id = video_id
        self._video_url = f"https://www.youtube.com/watch?v={video_id}"
        self._stop_event.clear()

        # เริ่ม polling loop ใน background thread
        self._thread = threading.Thread(
            target=self._poll_loop, name="YouTubeChatReader", daemon=True,
        )
        self._thread.start()
        return True

    def disconnect(self) -> None:
        """ยกเลิกการเชื่อมต่อ"""
        self._stop_event.set()
        self._is_connected = False
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._thread = None
        self.on_status("⚪ ยกเลิกการเชื่อมต่อ YouTube")

    # ------------------------------------------------------------------ #
    # Polling loop (background thread)
    # ------------------------------------------------------------------ #
    def _poll_loop(self) -> None:
        """resolve continuation → poll get_live_chat → dispatch messages"""
        # 1) resolve initial continuation token
        try:
            self._continuation = self._resolve_continuation(self._video_id)
        except Exception as exc:  # noqa: BLE001
            self.on_error(f"YouTube resolve error: {str(exc)[:120]}")
            self._continuation = None
            return

        if not self._continuation:
            self.on_error("YouTube: ไม่พบ live chat — ตรวจสอบว่าเป็น live stream จริง")
            return

        self._is_connected = True
        self.on_status(f"✅ เชื่อมต่อ YouTube live chat แล้ว")

        # 2) รอบแรก: skip history — ดึงเพื่อเอา next continuation token ล่าสุด
        #    (token ตั้งต้น reloadContinuationData = ดึงตั้งแต่เริ่ม live → เยอะมาก)
        #    หลัง fetch รอบแรก → continuation ใหม่ = live tail (เฉพาะข้อความใหม่)
        try:
            self._fetch_chat(skip_dispatch=True)  # skip ไม่ dispatch messages เก่า
        except Exception:  # noqa: BLE001
            pass

        # 3) poll loop — ต่อจากนี้จะได้เฉพาะข้อความใหม่
        backoff = self.poll_interval
        while not self._stop_event.is_set():
            try:
                had_messages = self._fetch_chat()
                if had_messages:
                    backoff = self.poll_interval  # reset backoff
                else:
                    backoff = min(backoff + 0.5, 10.0)  # เพิ่มช้าลงถ้าไม่มี msg
            except requests.exceptions.ConnectionError:
                backoff = min(backoff + 2, 15.0)
            except Exception as exc:  # noqa: BLE001
                if self._stop_event.is_set():
                    break
                err = str(exc)
                if "ended" in err.lower() or "not live" in err.lower():
                    self.on_error("YouTube: ไลฟ์สดจบลงแล้ว")
                    break
                backoff = min(backoff + 1, 15.0)
            # poll viewer count (ทุก ~60s)
            self._poll_viewer_count()
            # sleep (เช็ค stop_event ทุก 0.5s เพื่อให้ disconnect ตอบสนองเร็ว)
            slept = 0.0
            while slept < backoff and not self._stop_event.is_set():
                time.sleep(0.5)
                slept += 0.5

        self._is_connected = False

    # ------------------------------------------------------------------ #
    # Resolve continuation token (จาก watch page)
    # ------------------------------------------------------------------ #
    def _resolve_continuation(self, video_id: str) -> Optional[str]:
        """ดึง live chat continuation token จาก watch page

        ใช้ bpctr=9999999999 + has_verified=1 ข้าม consent check
        หา reloadContinuationData → continuation token
        + extract concurrentViewers (viewer count) จาก HTML
        """
        # URL ที่ข้าม consent (yt-dlp ใช้ trick นี้)
        url = f"https://www.youtube.com/watch?v={video_id}&bpctr=9999999999&has_verified=1"
        resp = self._session.get(url, timeout=20)
        if resp.status_code != 200:
            return None
        html = resp.text
        # extract viewer count (ลองหลาย pattern — YouTube เปลี่ยนบ่อย)
        self._extract_viewer_from_html(html)
        self._last_viewer_poll = time.time()
        # หา continuation token จาก reloadContinuationData
        m = re.search(r'"reloadContinuationData":\{"continuation":"([^"]+)"', html)
        if m:
            return m.group(1)
        m2 = re.search(r'"continuationCommand":\{"token":"([^"]+)"', html)
        if m2:
            return m2.group(1)
        return None

    def _extract_viewer_from_html(self, html: str) -> None:
        """สกัด viewer count จาก HTML/API response — ลองหลาย pattern

        YouTube เปลี่ยน format บ่อย:
        - เก่า: "concurrentViewers":"1234"
        - ใหม่: [{"text":"1,552"},{"text":" watching now"}]
        """
        # Pattern 1: concurrentViewers (format เก่า)
        m = re.search(r'"concurrentViewers":"(\d+)"', html)
        if m:
            try:
                self.on_viewer_count("youtube", int(m.group(1)))
                return
            except Exception:
                pass
        # Pattern 2: "N watching now" (format ใหม่ — มาจาก InnerTube/watch page)
        m2 = re.search(r'"text":\s*"([\d,]+)"\s*\},\s*\{\s*"text":\s*"\s*watching\s+now"', html)
        if m2:
            try:
                count = int(m2.group(1).replace(",", ""))
                self.on_viewer_count("youtube", count)
                return
            except Exception:
                pass
        # Pattern 3: fallback "N watching"
        m3 = re.search(r'"([\d,]+)\s*watching"', html, re.IGNORECASE)
        if m3:
            try:
                count = int(m3.group(1).replace(",", ""))
                self.on_viewer_count("youtube", count)
                return
            except Exception:
                pass

    def _poll_viewer_count(self) -> None:
        """re-fetch viewer count ผ่าน InnerTube next API (เรียกทุก 60s)

        ใช้ next API เพราะเร็วกว่า watch page + มี 'N watching now' pattern
        """
        if self._stop_event.is_set() or not self._video_id:
            return
        now = time.time()
        if now - self._last_viewer_poll < 55:
            return
        try:
            api_url = f"https://www.youtube.com/youtubei/v1/next?key={INNERTUBE_API_KEY}"
            payload = {
                "context": {
                    "client": {"clientName": "WEB", "clientVersion": INNERTUBE_CLIENT_VERSION}
                },
                "videoId": self._video_id,
            }
            resp = self._session.post(api_url, json=payload, timeout=15)
            if resp.status_code == 200:
                import json as _json
                txt = _json.dumps(resp.json())
                self._extract_viewer_from_html(txt)
        except Exception:
            pass
        self._last_viewer_poll = now

    # ------------------------------------------------------------------ #
    # Fetch chat (1 API call)
    # ------------------------------------------------------------------ #
    def _fetch_chat(self, skip_dispatch: bool = False) -> bool:
        """เรียก get_live_chat 1 ครั้ง → dispatch messages → return had_messages

        Args:
            skip_dispatch: ถ้า True → อัปเดต continuation token แต่ไม่ dispatch messages
                           (ใช้รอบแรกเพื่อ skip history → เอาเฉพาะ live tail token)
        """
        if not self._continuation:
            return False
        payload = {
            "context": {
                "client": {
                    "clientName": "WEB",
                    "clientVersion": INNERTUBE_CLIENT_VERSION,
                }
            },
            "continuation": self._continuation,
        }
        api_url = f"{INNERTUBE_API_URL}?key={INNERTUBE_API_KEY}"
        resp = self._session.post(api_url, json=payload, timeout=15)
        if resp.status_code != 200:
            return False
        data = resp.json()
        # extract continuation contents
        cont = data.get("continuationContents", {})
        lc = cont.get("liveChatContinuation", {})
        if not lc:
            # อาจจะจบแล้ว (no more chat)
            if data.get("contents") is None and not lc:
                raise RuntimeError("live ended")
            return False
        # update continuation token สำหรับรอบถัดไป (สำคัญที่สุด — เลื่อน cursor ไปยัง live tail)
        continuations = lc.get("continuations", [])
        if continuations:
            next_data = continuations[0]
            # อาจอยู่ใน liveChatActionPollAction, reloadContinuationData, invalidationContinuationData, timedContinuationData
            for key in ("invalidationContinuationData", "timedContinuationData",
                        "reloadContinuationData", "liveChatActionPollAction"):
                if key in next_data:
                    tok = next_data[key].get("continuation")
                    if tok:
                        self._continuation = tok
                        break
        # skip dispatch (รอบแรก — skip history, เอาแค่ token)
        if skip_dispatch:
            return False
        # dispatch actions
        actions = lc.get("actions", [])
        had = False
        for action in actions:
            if self._stop_event.is_set():
                break
            try:
                if self._handle_action(action):
                    had = True
            except Exception:  # noqa: BLE001
                pass
        return had

    # ------------------------------------------------------------------ #
    # Action dispatch — YouTube action → ChatMessage
    # ------------------------------------------------------------------ #
    def _handle_action(self, action: dict) -> bool:
        """parse 1 action → emit ChatMessage → return True ถ้ามี message"""
        # action structure: {"addChatItemAction": {"item": {"rendererName": {...}}}}
        # หรือ {"replayChatItemAction": {"actions": [{"addChatItemAction": {...}}]}}
        add = action.get("addChatItemAction")
        if add is None:
            # replay action (chat replay) — unwrap
            replay = action.get("replayChatItemAction", {})
            inner = replay.get("actions", [])
            if inner and isinstance(inner[0], dict):
                add = inner[0].get("addChatItemAction")
            if add is None:
                return False

        item = add.get("item", {})
        if not item:
            return False
        # dispatch by renderer type
        for renderer_name, handler in [
            ("liveChatTextMessageRenderer", self._handle_text_message),
            ("liveChatPaidMessageRenderer", self._handle_paid_message),
            ("liveChatMembershipItemRenderer", self._handle_membership),
            ("liveChatSponsorshipsGiftRedemptionNotification",
             self._handle_gift),
            ("liveChatSponsorshipsGiftReceivedNotification",
             self._handle_gift),
        ]:
            renderer = item.get(renderer_name)
            if renderer is not None:
                # dedupe by message ID (ถ้ามี)
                msg_id = renderer.get("id") or renderer.get("externalChannelId", "")
                if msg_id and msg_id in self._seen_ids:
                    return False
                if msg_id:
                    self._seen_ids.add(msg_id)
                    # cap dedupe set (กัน memory bloat)
                    if len(self._seen_ids) > 2000:
                        self._seen_ids = set(list(self._seen_ids)[-1000:])
                handler(renderer)
                return True
        return False

    # ------------------------------------------------------------------ #
    # Renderer handlers
    # ------------------------------------------------------------------ #
    def _handle_text_message(self, r: dict) -> None:
        """liveChatTextMessageRenderer → chat ปกติ"""
        author = (r.get("authorName") or {}).get("simpleText", "?")
        text, segments = self._extract_runs_with_segments(r.get("message", {}))
        self.messages_read += 1
        self.on_message(
            ChatMessage(
                platform="youtube",
                author=author,
                text=text,
                event="message",
                extra={
                    "author_id": r.get("authorExternalChannelId"),
                    "segments": segments if segments else None,
                },
            )
        )

    def _handle_paid_message(self, r: dict) -> None:
        """liveChatPaidMessageRenderer → SuperChat"""
        author = (r.get("authorName") or {}).get("simpleText", "?")
        text = self._extract_runs(r.get("message", {}))
        amount, currency = self._parse_purchase_amount(r.get("purchaseAmount", ""))
        self.messages_read += 1
        self.on_message(
            ChatMessage(
                platform="youtube",
                author=author,
                text=text,
                event="superchat",
                amount=amount,
                system_text=f"{amount} {currency}" if amount else None,
                extra={
                    "currency": currency,
                    "purchase_amount": r.get("purchaseAmount"),
                    "author_id": r.get("authorExternalChannelId"),
                },
            )
        )

    def _handle_membership(self, r: dict) -> None:
        """liveChatMembershipItemRenderer → membership (แยกจาก Twitch sub)"""
        author = (r.get("authorName") or {}).get("simpleText", "?")
        text = self._extract_runs(r.get("message", {}))
        # header subtext (เช่น "Welcome to members!")
        header = self._extract_runs(r.get("headerSubtext", {}))
        self.messages_read += 1
        self.on_message(
            ChatMessage(
                platform="youtube",
                author=author,
                text=text,
                event="membership",
                system_text=header or "สมัครสมาชิก",
                extra={
                    "author_id": r.get("authorExternalChannelId"),
                },
            )
        )

    def _handle_gift(self, r: dict) -> None:
        """liveChatSponsorshipsGift*Notification → subgift"""
        author = (r.get("authorName") or {}).get("simpleText", "?")
        text = self._extract_runs(r.get("message", {}))
        self.messages_read += 1
        self.on_message(
            ChatMessage(
                platform="youtube",
                author=author,
                text="",
                event="subgift",
                system_text=text or "มอบสมาชิกให้",
                extra={
                    "author_id": r.get("authorExternalChannelId"),
                },
            )
        )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _extract_runs(msg_obj) -> str:
        """ดึง text จาก message object {runs: [{text}, {emoji}, ...]}

        emoji → ใช้ shortcut (เช่น ":blowfish:") — สำหรับ TTS text
        """
        if isinstance(msg_obj, str):
            return msg_obj
        runs = msg_obj.get("runs", []) if isinstance(msg_obj, dict) else []
        parts = []
        for run in runs:
            if isinstance(run, str):
                parts.append(run)
            elif isinstance(run, dict):
                if "text" in run:
                    parts.append(run["text"])
                elif "emoji" in run:
                    emoji = run["emoji"]
                    shortcuts = emoji.get("shortcuts", [])
                    if shortcuts:
                        parts.append(shortcuts[0])
        return "".join(parts).strip()

    @staticmethod
    def _extract_runs_with_segments(msg_obj) -> tuple[str, list]:
        """ดึง text + segments (พร้อม emote URLs) จาก message object

        Returns: (plain_text, segments)
        segments format เหมือน MyLive: [{type:"text", content:"..."}, {type:"emote", url:"..."}]
        emoji runs → สกัด thumbnail URL สำหรับแสดงเป็นภาพ

        **สำคัญ:** emote ไม่ถูกฝังใน text (TTS) — เก็บเฉพาะใน segments (display)
        text สำหรับ TTS = เฉพาะ text runs เท่านั้น (ไม่มี emoji/shortcut)
        """
        if isinstance(msg_obj, str):
            return msg_obj, [{"type": "text", "content": msg_obj}]
        runs = msg_obj.get("runs", []) if isinstance(msg_obj, dict) else []
        text_parts = []  # text สำหรับ TTS (ไม่มี emote)
        segments = []     # สำหรับ display (มี emote)
        for run in runs:
            if isinstance(run, str):
                text_parts.append(run)
                segments.append({"type": "text", "content": run})
            elif isinstance(run, dict):
                if "text" in run:
                    text_parts.append(run["text"])
                    segments.append({"type": "text", "content": run["text"]})
                elif "emoji" in run:
                    emoji = run["emoji"]
                    shortcuts = emoji.get("shortcuts", [])
                    name = shortcuts[0] if shortcuts else ""
                    # สกัด thumbnail URL
                    url = ""
                    thumbnails = emoji.get("image") or {}
                    if isinstance(thumbnails, dict):
                        for thumb_key in ("thumbnails",):
                            thumbs = thumbnails.get(thumb_key, [])
                            if thumbs and isinstance(thumbs, list):
                                url = thumbs[0].get("url", "")
                                if url:
                                    break
                        if not url:
                            url = thumbnails.get("url", "")
                    elif isinstance(thumbnails, list) and thumbnails:
                        url = thumbnails[0].get("url", "")
                    # emote → เก็บใน segments เท่านั้น (ไม่ฝังใน text_parts → TTS ไม่อ่าน)
                    segments.append({"type": "emote", "url": url or "", "name": name})
        return "".join(text_parts).strip(), segments

    @staticmethod
    def _parse_purchase_amount(pa: str) -> tuple[Optional[int], str]:
        """แยก (amount_int, currency) จาก purchaseAmount string

        เช่น "฿50.00" → (50, "THB"), "$5.00" → (5, "USD"), "¥1000" → (1000, "JPY")
        """
        if not pa:
            return None, ""
        # หาตัวเลข
        m = re.search(r"([\d,]+(?:\.\d+)?)", pa)
        if not m:
            return None, ""
        try:
            amount = int(float(m.group(1).replace(",", "")))
        except ValueError:
            amount = None
        # ทาย currency จาก symbol
        symbol_map = {
            "฿": "THB", "$": "USD", "€": "EUR", "£": "GBP",
            "¥": "JPY", "₩": "KRW", "₹": "INR", "₽": "RUB",
        }
        currency = ""
        for sym, code in symbol_map.items():
            if sym in pa:
                currency = code
                break
        return amount, currency


# ---------------------------------------------------------------------- #
# Smoke test
# ---------------------------------------------------------------------- #
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python chat_youtube.py <URL or Video ID> [seconds]")
        print("Example: python chat_youtube.py WhbrWrM7mzo 30")
        sys.exit(1)

    target = sys.argv[1]
    duration = int(sys.argv[2]) if len(sys.argv) > 2 else 30

    def cb(msg: ChatMessage) -> None:
        prefix = msg.event.upper()
        amt = f" [{msg.amount}]" if msg.amount else ""
        sys_text = f"  ({msg.system_text})" if msg.system_text else ""
        print(f"[{prefix}] {msg.author}{amt}: {msg.text}{sys_text}")

    client = YouTubeChat(on_message=cb, on_status=lambda m: print(f">> {m}"),
                         on_error=lambda m: print(f">> {m}"))
    if client.connect(target):
        time.sleep(duration)
        client.disconnect()
        print(f">> read {client.messages_read} messages")
