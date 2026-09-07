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
import logging
import urllib.request as urllib_request
import urllib.error as urllib_error
from typing import Callable, Optional

import requests

from chat_twitch import ChatMessage  # reuse shared dataclass

# ★ aliases สำหรับ json functions (ใช้ใน send_message)
json_dumps = json.dumps
json_loads = json.loads
logger = logging.getLogger("chat_youtube")

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
    """YouTube live chat reader — direct InnerTube API polling
    ★ รองรับการส่งแชทผ่าน YouTube Data API v3 (ถ้ามี OAuth token)
    """

    def __init__(
        self,
        on_message: Callable[[ChatMessage], None],
        on_status: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        on_viewer_count: Optional[Callable[[str, int], None]] = None,
        poll_interval: float = 2.0,
        oauth_token: str = "",
        bot_username: str = "",
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
        # ★ โหมด profile — ลิงก์ช่องแทนลิงก์ห้อง (รอ/สลับไลฟ์ใหม่อัตโนมัติ)
        self._profile_ref: str = ""
        self._ended_vids: set = set()
        self._video_url: str = ""
        self._last_viewer_poll: float = 0.0

        self.messages_read = 0
        self._seen_ids: set[str] = set()

        # ★ OAuth (ส่งแชท) — ถ้ามี → ส่งได้ ถ้าไม่มี → อ่านอย่างเดียว
        self._oauth_token = (oauth_token or "").strip()
        self._bot_username = (bot_username or "").strip()
        self._can_send = bool(self._oauth_token)
        # ★ refresh token + auto-refresh callback (เหมือน Twitch)
        self._refresh_token = ""
        self._on_token_refreshed = None  # callback(new_token) → app.py เก็บลง settings
        # ★ live chat ID — จะได้จาก videos API ตอน connect (จำเป็นสำหรับ insert)
        self._live_chat_id: str = ""
        self._send_lock = threading.Lock()
        # ★ quota callback — เรียกเมื่อเจอ error 403 quotaExceeded
        self.on_quota_exceeded = None  # callable() หรือ None
        # ★ เจ้าของห้อง — ดักกัน bot โพสในห้องคนอื่น
        self._own_channel_id: str = ""  # channel ID ของเรา (set จาก app.py)
        self._is_own_channel: bool = True  # default True (จะถูกแก้ตอน fetch_live_chat_id)

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    @property
    def can_send(self) -> bool:
        """True ถ้าล็อกอิน OAuth + เป็นห้องเรา → ส่งแชทได้"""
        return (self._can_send and self._is_connected
                and bool(self._live_chat_id) and self._is_own_channel)

    def _try_refresh_token(self) -> bool:
        """★ Auto-refresh token เมื่อหมดอายุ (เรียกเมื่อเจอ 401)

        Returns True ถ้า refresh สำเร็จ, False ถ้า fail
        """
        if not self._refresh_token:
            return False
        try:
            from youtube_oauth import refresh_access_token
            result = refresh_access_token(self._refresh_token)
            if result and result.get("access_token"):
                self._oauth_token = result["access_token"]
                logger.info("YouTube token refreshed automatically")
                if self._on_token_refreshed:
                    try:
                        self._on_token_refreshed(self._oauth_token)
                    except Exception:
                        pass
                self.on_status("🔄 YouTube token ต่ออายุอัตโนมัติ")
                return True
        except Exception as e:
            logger.error(f"YouTube token refresh failed: {e}")
        return False

    # ------------------------------------------------------------------ #
    # ★ Send chat (YouTube Data API v3 — liveChatMessages.insert)
    # ------------------------------------------------------------------ #
    def _fetch_live_chat_id(self, video_id: str) -> str:
        """ดึง liveChatId จาก video ID + เช็คว่าเป็นห้องเราไหม

        ★ ถ้าเป็นห้องคนอื่น → คืน liveChatId แต่ตั้ง _is_own_channel=False → ปิด bot
        """
        try:
            # ★ ดึงทั้ง liveStreamingDetails + snippet (เพื่อเช็คเจ้าของ)
            url = (f"https://www.googleapis.com/youtube/v3/videos"
                   f"?part=liveStreamingDetails,snippet&id={video_id}")
            req = urllib_request.Request(url)
            req.add_header("Authorization", f"Bearer {self._oauth_token}")
            with urllib_request.urlopen(req, timeout=10) as resp:
                result = json_loads(resp.read().decode("utf-8"))
            items = result.get("items", [])
            if not items:
                logger.warning("No video found")
                return ""
            item = items[0]
            chat_id = item.get("liveStreamingDetails", {}).get("activeLiveChatId", "")
            if not chat_id:
                logger.warning("No activeLiveChatId — video may not be live")
                return ""

            # ★ เช็คเจ้าของ video — ถ้าเป็นห้องคนอื่น → ปิด bot (กันโพสพลาด)
            video_channel_id = item.get("snippet", {}).get("channelId", "")
            self._is_own_channel = (video_channel_id == self._own_channel_id)
            if self._is_own_channel:
                logger.info(f"YouTube liveChatId: {chat_id} (ห้องเรา — bot ทำงาน)")
            else:
                logger.info(f"YouTube liveChatId: {chat_id} (ห้องคนอื่น — bot ปิด)")
                self.on_status("⚠️ YouTube: นี่ไม่ใช่ห้องของคุณ — Bot ปิดทำงาน (อ่านแชทได้ปกติ)")
            return chat_id
        except Exception as e:
            logger.error(f"_fetch_live_chat_id failed: {e}")
            return ""

    def send_message(self, text: str) -> bool:
        """ส่งข้อความไปยัง YouTube Live Chat (ผ่าน Data API v3)"""
        if not self._can_send:
            self.on_error("ไม่สามารถส่งแชทได้ — ยังไม่ได้ล็อกอิน YouTube OAuth")
            return False
        if not self._is_own_channel:
            self.on_error("ไม่สามารถส่งแชทได้ — นี่ไม่ใช่ห้องของคุณ (กันโพสในห้องคนอื่น)")
            return False
        if not self._live_chat_id:
            self.on_error("ไม่พบ liveChatId — วิดีโออาจไม่ได้ live อยู่")
            return False
        text = (text or "").strip()
        if not text:
            return False
        text = text[:500]  # YouTube จำกัด ~200 ตัวอักษร แต่เผื่อไว้

        with self._send_lock:
            try:
                url = "https://www.googleapis.com/youtube/v3/liveChatMessages"
                data = json_dumps({
                    "snippet": {
                        "liveChatId": self._live_chat_id,
                        "type": "textMessageEvent",
                        "textMessageDetails": {
                            "messageText": text
                        }
                    }
                }).encode("utf-8")
                req = urllib_request.Request(url, data=data, method="POST")
                req.add_header("Authorization", f"Bearer {self._oauth_token}")
                req.add_header("Content-Type", "application/json")
                with urllib_request.urlopen(req, timeout=15) as resp:
                    if resp.status in (200, 201):
                        logger.info(f"YouTube message sent: {text[:50]}")
                        return True
                    return False
            except urllib_error.HTTPError as e:
                body = e.read().decode("utf-8", errors="replace")
                logger.error(f"YouTube send failed: HTTP {e.code} - {body[:200]}")
                # ★ ตรวจ quota exceeded
                if e.code == 403 and "quotaExceeded" in body:
                    logger.warning("YouTube quota exceeded!")
                    if self.on_quota_exceeded:
                        try:
                            self.on_quota_exceeded()
                        except Exception:
                            pass
                # ★ token หมดอายุ → auto-refresh + retry
                elif e.code == 401:
                    if self._try_refresh_token():
                        return self.send_message(text)
                    self.on_error("YouTube token หมดอายุ — ล็อกอินใหม่")
                # ★ 404 = liveChatId ไม่พร้อม/ไม่ถูกต้อง → ไม่หลุดการเชื่อมต่อ (แค่แจ้งเตือน)
                elif e.code == 404:
                    logger.warning(f"YouTube chat ยังไม่พร้อม (404) — ไม่ตัดการเชื่อมต่อ")
                    # ★ ไม่เรียก on_error (กัน app.py ตีความเป็นหลุด) — แค่ log
                    pass
                else:
                    logger.warning(f"YouTube send error (ไม่ตัดการเชื่อมต่อ): HTTP {e.code}")
                    # ★ ไม่เรียก on_error สำหรับ error อื่นๆ ด้วย (กันหลุด)
                return False
            except Exception as e:
                logger.error(f"YouTube send failed: {e}")
                # ★ ไม่เรียก on_error (กันหลุดการเชื่อมต่อ)
                return False

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
    # ★ Profile mode — ใส่ลิงก์ช่อง (@handle) แทนลิงก์ห้อง (แบบ OneComme)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _extract_profile_url(text: str) -> Optional[str]:
        """แปลง input เป็น URL หน้า /live ของช่อง — คืน None ถ้าไม่ใช่ profile

        รองรับ: @MeN9CH | youtube.com/@MeN9CH | /channel/UCxxx | /c/name | /user/name
        """
        text = (text or "").strip()
        if not text:
            return None
        # ถ้าเป็นลิงก์วิดีโอ → ไม่ใช่ profile
        if YouTubeChat._extract_video_id(text):
            return None
        # @handle ตรงๆ
        m = re.fullmatch(r"@([A-Za-z0-9._-]{3,30})", text)
        if m:
            return f"https://www.youtube.com/@{m.group(1)}/live"
        # URL ของช่อง (ถ้ามี watch?v= / live/ID จะโดนตัดออกก่อนหน้านี้แล้ว)
        m = re.search(
            r"youtube\.com/(@[A-Za-z0-9._-]+|channel/UC[A-Za-z0-9_-]+|c/[A-Za-z0-9._-]+|user/[A-Za-z0-9._-]+)",
            text,
        )
        if m:
            return f"https://www.youtube.com/{m.group(1)}/live"
        return None

    def _resolve_profile_video(self, profile_url: str) -> Optional[str]:
        """ดึง video ของ live ปัจจุบันจากหน้า /live ของช่อง

        เทคนิค: หน้า /live ของช่องที่กำลัง live จะมี <link rel="canonical">
        ชี้ไป watch?v=ID ของไลฟ์นั้นเสมอ
        """
        try:
            r = self._session.get(profile_url, timeout=15)
            if r.status_code != 200:
                return None
            m = re.search(r'<link rel="canonical" href="[^"]*watch\?v=([A-Za-z0-9_-]{11})"', r.text)
            return m.group(1) if m else None
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"resolve profile failed: {exc}")
            return None

    def _is_video_live(self, video_id: str) -> bool:
        """เช็คว่า video กำลัง live จริงไหม (InnerTube player API — ไม่ต้องล็อกอิน)"""
        try:
            resp = self._session.post(
                "https://www.youtube.com/youtubei/v1/player",
                json={
                    "context": {"client": {"clientName": "WEB", "clientVersion": "2.20240101.00.00"}},
                    "videoId": video_id,
                },
                timeout=10,
            )
            data = resp.json()
            details = data.get("videoDetails", {})
            return bool(details.get("isLive")) or bool(details.get("isLiveContent") and data.get("streamingData"))
        except Exception:
            return False

    # ------------------------------------------------------------------ #
    # Connection
    # ------------------------------------------------------------------ #
    def connect(self, url_or_id: str) -> bool:
        """เชื่อมต่อ YouTube live chat

        Args:
            url_or_id: video URL / video ID / ★ ลิงก์โปรไฟล์ช่อง (@MeN9CH หรือ
                       youtube.com/@MeN9CH) — โปรแกรมหาห้อง live ปัจจุบันให้เอง
                       และสลับห้องให้อัตโนมัติเมื่อเริ่มสตรีมใหม่
        Returns True ถ้าเริ่ม polling สำเร็จ
        """
        self._profile_ref = None        # ★ URL หน้า /live ของช่อง (โหมด profile)
        self._ended_vids = set()        # ★ วิดีโอไลฟ์ที่จบแล้ว (ไม่กลับไปเกาะซ้ำ)

        video_id = self._extract_video_id(url_or_id)
        if not video_id:
            # ★ ไม่ใช่ลิงก์วิดีโอ → ลองเป็นลิงก์โปรไฟล์ช่อง
            profile_url = self._extract_profile_url(url_or_id)
            if profile_url:
                self._profile_ref = profile_url
                video_id = self._resolve_profile_video(profile_url)
                # ★ canonical ชี้ห้องเก่า (VOD) — เช็คว่า live จริงไหม ไม่งั้นเข้าโหมดรอ
                if video_id and not self._is_video_live(video_id):
                    self._ended_vids.add(video_id)
                    video_id = ""
                if video_id:
                    self.on_status(f"📺 YouTube: ใช้ช่อง {url_or_id.strip()} — เจอห้อง live กำลังเชื่อมต่อ")
                else:
                    self.on_status(f"📺 YouTube: ช่องนี้ยังไม่ได้ Live — "
                                   f"แชทจะเชื่อมต่อให้อัตโนมัติเมื่อเริ่มสตรีม (ตรวจทุก 1 นาที)")
            else:
                self.on_error("YouTube: ไม่พบ Video ID — ใส่ URL, Video ID หรือ @ชื่อช่อง")
                return False

        # ★ ถ้าเชื่อมต่ออยู่แล้ว → หยุดก่อน (กัน duplicate thread)
        if self._is_connected or (self._thread and self._thread.is_alive()):
            self._stop_event.set()
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=5)
            self._is_connected = False

        # ★ clear seen IDs (กัน duplicate หลัง reconnect)
        self._seen_ids.clear()
        self._stop_event.clear()

        self._video_id = video_id
        self._video_url = f"https://www.youtube.com/watch?v={video_id}" if video_id else ""
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
        """driver — รัน session ไลฟ์ละรอบ

        ★ โหมด profile (ลิงก์ช่อง): เมื่อไลฟ์จบหรือยังไม่เริ่ม → รอและเกาะไลฟ์ใหม่เอง
        ★ โหมดลิงก์วิดีโอ: จบแล้วจบเลย (พฤติกรรมเดิม)
        """
        while not self._stop_event.is_set():
            result = self._run_session()
            if result == "ended" and self._profile_ref and not self._stop_event.is_set():
                self._ended_vids.add(self._video_id)
                self._is_connected = False
                self.on_status("⏳ YouTube: กำลังรอสตรีมถัดไป — แชทจะเชื่อมต่ออัตโนมัติเมื่อ Live")
                if self._wait_next_stream():
                    self._seen_ids.clear()
                    continue  # ★ ไลฟ์ใหม่มาแล้ว → รัน session ใหม่
            break  # ★ "stopped" หรือรอไม่สำเร็จ → จบ loop
        self._is_connected = False

    def _wait_next_stream(self) -> bool:
        """โหมด profile: วนตรวจช่องทุก 60 วิ จนกว่าจะมีไลฟ์ใหม่ (คืน True = เจอ)

        ★ ข้ามวิดีโอที่จบไปแล้ว (_ended_vids) — กันเกาะ VOD เก่าซ้ำ
        """
        while not self._stop_event.is_set():
            vid = self._resolve_profile_video(self._profile_ref)
            if vid and vid not in self._ended_vids and vid != self._video_id:
                if self._is_video_live(vid):
                    self._video_id = vid
                    self._video_url = f"https://www.youtube.com/watch?v={vid}"
                    self.on_status("📺 YouTube: เจอสตรีมใหม่ของช่อง — กำลังเข้าร่วม...")
                    return True
            # sleep 60 วิ (เช็ค stop ทุก 0.5 วิ)
            slept = 0.0
            while slept < 60 and not self._stop_event.is_set():
                time.sleep(0.5)
                slept += 0.5
        return False

    def _run_session(self) -> str:
        """resolve continuation → poll get_live_chat → dispatch messages

        ★ ถ้ามี OAuth + InnerTube อ่านไม่ได้ (เช่น Private live) → ใช้ API อ่านแชทแทน
        Returns: "ended" (ไลฟ์จบ/ไม่มี live chat) | "stopped" (user disconnect)
        """
        # ★ โหมด profile ที่ยังไม่เจอห้อง live → คืน "ended" ให้ driver เข้า wait loop
        if not self._video_id:
            return "ended"
        # ★ ลิงก์วิดีโอตรงๆ: ถ้าไลฟ์จบแล้ว → ปฏิเสธ (กัน auto-connect เข้าห้องเก่า
        #   เพราะ VOD ที่จบแล้วยังมี chat continuation ให้เกาะได้)
        if not self._profile_ref and not self._is_video_live(self._video_id):
            self.on_error("YouTube: ไลฟ์นี้จบไปแล้ว — ไม่เชื่อมต่อห้องเก่า "
                          "(ใช้ @ชื่อช่อง เพื่อรอสตรีมถัดไปอัตโนมัติ)")
            return "stopped"
        # 1) ลอง resolve continuation token แบบ anonymous (InnerTube)
        try:
            self._continuation = self._resolve_continuation(self._video_id)
        except Exception as exc:  # noqa: BLE001
            self.on_error(f"YouTube resolve error: {str(exc)[:120]}")
            self._continuation = None

        # ★ ถ้า InnerTube ไม่ได้ + มี OAuth → ใช้ API mode (อ่านผ่าน liveChatMessages.list)
        if not self._continuation and self._can_send:
            try:
                self._live_chat_id = self._fetch_live_chat_id(self._video_id)
                if self._live_chat_id:
                    self._is_connected = True
                    if self._is_own_channel:
                        self.on_status("✅ เชื่อมต่อ YouTube ผ่าน API (ส่งแชท + bot ได้)")
                        # ★ ส่ง test message
                        import time as _time
                        _time.sleep(2)
                        test_ok = self.send_message("🤖 บอทเชื่อมต่อสำเร็จแล้ว!")
                        if test_ok:
                            self.on_status("✅ YouTube Bot พร้อมใช้งาน!")
                        else:
                            self.on_status("⚠️ YouTube Bot: ส่ง test message ไม่สำเร็จ")
                    else:
                        self.on_status("📖 YouTube: อ่านแชทได้ (ห้องคนอื่น — bot ปิด)")
                    # ★ poll ด้วย API mode
                    self._poll_loop_api()
                    return "ended"
            except Exception as exc:
                logger.error(f"API mode connect failed: {exc}")
            return "ended"

        if not self._continuation:
            self.on_error("YouTube: ไม่พบ live chat — ตรวจสอบว่าเป็น live stream จริง")
            return "ended"

        self._is_connected = True
        self.on_status(f"✅ เชื่อมต่อ YouTube live chat แล้ว")

        # ★ ถ้ามี OAuth → ดึง liveChatId (จำเป็นสำหรับส่งแชท) + ส่ง test message
        if self._can_send:
            try:
                self._live_chat_id = self._fetch_live_chat_id(self._video_id)
                if self._live_chat_id:
                    if self._is_own_channel:
                        self.on_status(f"🔐 YouTube ล็อกอินแล้ว (ส่งแชท + bot ได้)")
                        # ★ ส่ง test message เพื่อยืนยันว่า bot พร้อมใช้งาน
                        import time as _time
                        _time.sleep(2)  # รอ 2 วิ ให้ chat พร้อม
                        test_ok = self.send_message("🤖 บอทเชื่อมต่อสำเร็จแล้ว!")
                        if test_ok:
                            self.on_status("✅ YouTube Bot พร้อมใช้งาน!")
                        else:
                            self.on_status("⚠️ YouTube Bot: ส่ง test message ไม่สำเร็จ — แชทยังไม่พร้อม")
                    else:
                        self.on_status("📖 YouTube: อ่านแชทได้ (ห้องคนอื่น — bot ปิด)")
            except Exception as e:
                logger.debug(f"fetch liveChatId failed: {e}")

        # 2) รอบแรก: จด ID ของข้อความ history (ไม่ dispatch ของเก่า)
        #    ★ เก็บ token หน้าต่างล่าสุด (reload) ไว้ใช้ re-poll ทุกรอบ
        self._reload_token = self._continuation
        self._reload_token_ts = time.time()
        self._empty_streak = 0   # ★ นับรอบเงียบติดกัน (trigger รีเฟรช token)
        self._had_any = False    # ★ เคยเห็นข้อความไหลใน session นี้
        try:
            self._fetch_chat(skip_dispatch=True)  # skip ไม่ dispatch + จด seen IDs
        except Exception:  # noqa: BLE001
            pass

        # 3) poll loop — ★ กลยุทธ์ reload re-poll:
        #    invalidation continuation ของ YouTube ไม่ส่ง action กลับมาให้ client
        #    ภายนอกเบราว์เซอร์อีกแล้ว (ทดสอบครบทุก variant) → ยิง token หน้าต่าง
        #    ล่าสุดซ้ำทุกรอบแล้วตัดซ้ำด้วย message ID (เห็นข้อความใหม่ที่หน้าต่าง
        #    จริงเสมอ — พิสูจน์แล้ว) poll เร็วตลอด (cap 4 วิ) กันพลาด burst แชทเร็ว
        backoff = max(1.2, self.poll_interval)
        self._session_ended = False
        drain_streak = 0  # ★ นับรอบติดที่เจอข้อความ — เจอแล้วดึงต่อทันที (drain burst)
        while not self._stop_event.is_set():
            try:
                # ★ token ที่ถืออยู่ cursor เดินช้า → หลุดข้อความช่วงยาว
                #   รีเฟรช 2 กรณี: (1) ทุก 45 วิ (2) เคยมีแชทไหลแล้วเงียบผิดปกติ 3 รอบ
                #   (GT พิสูจน์: token สดเห็นข้อความล่าสุดเสมอ)
                now_ts = time.time()
                need_refresh = (
                    now_ts - getattr(self, "_reload_token_ts", 0) > 45
                    or (self._empty_streak >= 3
                        and now_ts - getattr(self, "_reload_token_ts", 0) >= 12)
                )
                if need_refresh:
                    fresh = self._resolve_continuation(self._video_id)
                    if fresh:
                        self._reload_token = fresh
                        self._reload_token_ts = now_ts
                    self._empty_streak = 0
                self._continuation = self._reload_token  # ★ re-poll หน้าต่างล่าสุด
                had_messages = self._fetch_chat()
                if had_messages:
                    self._had_any = True
                    self._empty_streak = 0
                    backoff = max(1.2, self.poll_interval)  # reset backoff
                    drain_streak += 1
                    if drain_streak <= 5:
                        # ★ แชทกำลังไหล — วนดึงต่อเลยไม่หลับ (กันพลาด burst ของห้องยุ่ง)
                        self._poll_viewer_count()
                        continue
                else:
                    self._empty_streak += 1
                    backoff = min(backoff + 0.4, 4.0)  # cap ต่ำ — กันพลาดข้อความ
                drain_streak = 0
            except requests.exceptions.ConnectionError:
                backoff = min(backoff + 2, 8.0)
                drain_streak = 0
            except Exception as exc:  # noqa: BLE001
                drain_streak = 0
                if self._stop_event.is_set():
                    break
                err = str(exc)
                if "ended" in err.lower() or "not live" in err.lower():
                    self.on_error("YouTube: ไลฟ์สดจบลงแล้ว")
                    self._session_ended = True
                    break
                backoff = min(backoff + 1, 8.0)
            # poll viewer count (ทุก ~60s)
            self._poll_viewer_count()
            # sleep (เช็ค stop_event ทุก 0.5s เพื่อให้ disconnect ตอบสนองเร็ว)
            slept = 0.0
            while slept < backoff and not self._stop_event.is_set():
                time.sleep(0.5)
                slept += 0.5

        self._is_connected = False
        if self._stop_event.is_set():
            return "stopped"
        return "ended" if getattr(self, '_session_ended', True) else "stopped"

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
        # ★ เก็บ API key + clientVersion สดจากหน้าเว็บ (ค่าคงที่เก่าจะได้หน้าต่าง
        #   แชทค้างไม่เดินหน้า — YouTube ผูก freshness กับ client version)
        try:
            mk = re.search(r'"INNERTUBE_API_KEY":"([^"]+)"', html)
            mv = re.search(r'"INNERTUBE_CLIENT_VERSION":"([^"]+)"', html)
            if mk:
                self._yt_api_key = mk.group(1)
            if mv:
                self._yt_client_version = mv.group(1)
        except Exception:  # noqa: BLE001
            pass
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
        """สกัด viewer count จาก watch page / InnerTube response

        ★ 2026 format: "metadataParts":[{"text":{"content":"70 watching"}}
                       (lockupViewModel — พบในทั้ง watch page และ next API)
        ★ runs format: "runs":[{"text":"70"},{"text":" watching"}]
        ★ Pattern เก่า: "concurrentViewers" / "... watching now"
        """
        # ★ Pattern หลัก (แม่นยำ — ของวิดีโอตัวเองเท่านั้น):
        #   videoViewCountRenderer → viewCount.runs[0].text (มีทั้งใน watch page + next API)
        #   ★ ห้ามใช้ "N watching" ลอยๆ — มันโดนวิดีโอแนะนำของห้องอื่น!
        m = re.search(
            r'"videoViewCountRenderer":\s*\{\s*"viewCount":\s*\{\s*"runs":\s*\[\s*\{\s*"text":\s*"(\d[\d,]*)"',
            html)
        if not m:
            # ★ fallback: originalViewCount คู่กับ isLive
            m = re.search(r'"originalViewCount":\s*"(\d[\d,]*)"', html)
        if m:
            try:
                count = int(m.group(1).replace(",", ""))
                self.on_viewer_count("youtube", count)
                return
            except Exception:
                pass
        # ★ Pattern เก่า: concurrentViewers (ของวิดีโอตัวเอง — จาก playerResponse)
        m2 = re.search(r'"concurrentViewers":"(\d+)"', html)
        if m2:
            try:
                self.on_viewer_count("youtube", int(m2.group(1)))
                return
            except Exception:
                pass

    def _poll_loop_api(self):
        """★ API mode — อ่านแชทผ่าน liveChatMessages.list (สำหรับ Private/Unlisted)

        ★ ใช้เมื่อ InnerTube อ่านไม่ได้ (เช่น Private live)
        ★ กิน quota: 5 units/request → poll ทุก 10 วิ = 30 req/นาที = 150 units/นาที
        """
        next_page_token = ""
        first_poll = True
        poll_interval = 10  # default 10s
        while not self._stop_event.is_set():
            try:
                url = (f"https://www.googleapis.com/youtube/v3/liveChatMessages"
                       f"?liveChatId={self._live_chat_id}&part=snippet,authorDetails"
                       f"&maxResults=200")
                if next_page_token:
                    url += f"&pageToken={next_page_token}"
                req = urllib_request.Request(url)
                req.add_header("Authorization", f"Bearer {self._oauth_token}")
                with urllib_request.urlopen(req, timeout=15) as resp:
                    result = json_loads(resp.read().decode("utf-8"))

                # ★ อัปเดต polling interval (YouTube แนะนำ)
                poll_interval_ms = result.get("pollingIntervalMillis", 10000)
                poll_interval = max(3, min(30, poll_interval_ms / 1000))

                next_page_token = result.get("nextPageToken", "")

                # ★ dispatch messages (skip รอบแรก — ไม่อ่าน history)
                if not first_poll:
                    for item in result.get("items", []):
                        try:
                            self._handle_api_message(item)
                        except Exception as e:
                            logger.debug(f"API message parse error: {e}")
                first_poll = False

                # ★ consume quota
                if self.on_quota_exceeded:
                    pass  # quota tracking ทำใน send_message เท่านั้น (list = น้อย)

            except urllib_error.HTTPError as e:
                body = e.read().decode("utf-8", errors="replace")
                logger.error(f"API poll failed: HTTP {e.code} - {body[:200]}")
                if e.code == 403 and "quotaExceeded" in body:
                    if self.on_quota_exceeded:
                        try: self.on_quota_exceeded()
                        except: pass
                    self.on_error("YouTube quota หมด — หยุดอ่านแชท")
                    return
                elif e.code == 401:
                    # ★ auto-refresh + continue (ไม่ return — รอบหน้าจะใช้ token ใหม่)
                    if not self._try_refresh_token():
                        self.on_error("YouTube token หมดอายุ — ล็อกอินใหม่")
                        return
            except Exception as e:
                logger.error(f"API poll error: {e}")

            self._stop_event.wait(poll_interval)

    def _handle_api_message(self, item: dict):
        """★ parse message จาก liveChatMessages.list API → dispatch"""
        snippet = item.get("snippet", {})
        author = item.get("authorDetails", {})
        msg_type = snippet.get("type", "textMessageEvent")
        author_name = author.get("displayName", "?")
        # ★ text message
        if msg_type == "textMessageEvent":
            text = snippet.get("textMessageDetails", {}).get("messageText", "")
        elif msg_type == "superChatEvent":
            amount = snippet.get("superChatDetails", {}).get("amountDisplayString", "")
            text = snippet.get("superChatDetails", {}).get("userComment", "")
            msg = ChatMessage(
                platform="youtube", author=author_name, text=text,
                event="superchat", extra={"amount": amount},
            )
            self.messages_read += 1
            self.on_message(msg)
            return
        elif msg_type == "newSponsorEvent":
            msg = ChatMessage(
                platform="youtube", author=author_name, text="",
                event="member", system_text="New member",
            )
            self.messages_read += 1
            self.on_message(msg)
            return
        else:
            text = snippet.get("textMessageDetails", {}).get("messageText", str(snippet)[:100])

        if text:
            msg = ChatMessage(
                platform="youtube", author=author_name, text=text, event="message",
            )
            self.messages_read += 1
            self.on_message(msg)

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
            api_key = getattr(self, "_yt_api_key", "") or INNERTUBE_API_KEY
            api_url = f"https://www.youtube.com/youtubei/v1/next?key={api_key}"
            payload = {
                "context": {
                    "client": {
                        "clientName": "WEB",
                        "clientVersion": getattr(self, "_yt_client_version", "") or INNERTUBE_CLIENT_VERSION,
                    }
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
                    "clientVersion": getattr(self, "_yt_client_version", "") or INNERTUBE_CLIENT_VERSION,
                }
            },
            "continuation": self._continuation,
        }
        api_key = getattr(self, "_yt_api_key", "") or INNERTUBE_API_KEY
        api_url = f"{INNERTUBE_API_URL}?key={api_key}"
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
        # ★ actions ของรอบนี้ (ใช้ทั้งกรณี skip และ dispatch)
        actions = lc.get("actions", []) or []
        # skip dispatch (รอบแรก — จด ID ของ history ไว้กัน re-poll ซ้ำ แต่ไม่ dispatch)
        if skip_dispatch:
            for action in actions:
                try:
                    item = (action.get("addChatItemAction") or {}).get("item", {})
                    for rn in item:
                        mid = (item.get(rn) or {}).get("id")
                        if mid:
                            self._seen_ids.add(mid)
                            break
                except Exception:  # noqa: BLE001
                    pass
            return False
        # dispatch actions
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
