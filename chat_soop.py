"""chat_soop.py — SOOP Live (เดิมชื่อ AfreecaTV) live chat client

เชื่อมต่อ SOOP chat ผ่าน WebSocket โปรโตคอลเฉพาะที่ reverse-engineer มา (ไม่ใช่ official API
— official Chat SDK ต้องส่ง partnership proposal ผ่าน developers.afreecatv.com แล้วรออนุมัติ
ไม่เกิน 10 วันทำการ ไม่เหมาะกับโปรแกรมแจกฟรีที่อยากให้ต่อได้ทันที)

อ้างอิงโปรโตคอลจาก https://github.com/cha2hyun/afreecatv-chat-crawler (โปรเจกต์ reverse-
engineering ที่เปิดเผย protocol ไว้) — พอร์ตจาก async (websockets lib) มาเป็น sync
(websocket-client) ให้ตรงกับ pattern ที่เหลือของโปรแกรม (background thread เหมือน chat_kick.py)

วิธีเชื่อม:
  1. HTTP resolve: POST live.afreecatv.com/afreeca/player_live_api.php?bjid={bid}
     → ได้ CHDOMAIN (chat server), CHATNO, CHPT (chat port), TITLE
  2. WebSocket: wss://{CHDOMAIN}:{CHPT}/Websocket/{BID}  (subprotocol "chat")
  3. ส่ง CONNECT_PACKET → รอ 2s → ส่ง JOIN_PACKET (มี CHATNO)
  4. รับข้อความเป็น binary frame คั่นด้วย \\x0c (form feed) — field[1]=ข้อความ,
     field[2]=user_id, field[6]=ชื่อเล่น (ถ้า >5 ฟิลด์ และไม่ใช่ system message)
  5. ส่ง PING_PACKET ทุก ~55s กัน timeout (server ตัดถ้าไม่ ping ใน 5 นาที)

★ ข้อจำกัด (v1 — เวอร์ชันง่าย/เร็วที่สุดเท่าที่ยืนยัน protocol ได้ตอนนี้):
  - อ่านได้เฉพาะข้อความแชทปกติ — อีโมติคอน/สติกเกอร์/별풍선(โดเนท)/sub ที่ส่งมาในสตรีม
    ข้อมูลเดียวกัน ยังไม่มี protocol ที่ยืนยันได้ว่า field ไหนคืออะไร → ถูกข้ามไปเงียบๆ
    (ต้อง sniff traffic จริงตอนมี event พวกนี้เกิดขึ้นถึงจะรู้แน่ — ทำเป็นเฟส 2 ได้)
  - ไม่รองรับส่งข้อความ (read-only เหมือน Twitch/Kick anonymous mode)
  - bno (เลขที่ broadcast) ใช้ค่าว่าง "" ให้ API auto-resolve ห้องที่ไลฟ์อยู่ปัจจุบันของ BID
    (mode=landing) — ยังไม่เคยทดสอบกับ live จริง ถ้า resolve ไม่ได้อาจต้องหา bno แยกต่างหาก
  - ยังไม่เคยทดสอบกับ WebSocket จริง (ต้องมี SOOP account/สตรีมจริงถึงจะ verify ได้ครบ) —
    ตาม pattern โค้ดล้วนๆ จาก reference implementation ที่ยืนยันว่าใช้งานได้จริงมาก่อน

การใช้งาน:
    client = SoopChat(on_message=callback)
    client.connect("bjid_ของ_สตรีมเมอร์")
    ...
    client.disconnect()
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from chat_twitch import ChatMessage  # reuse shared dataclass

try:
    import websocket
    _WS_AVAILABLE = True
    _WS_IMPORT_ERROR: Optional[str] = None
except Exception as exc:  # noqa: BLE001
    _WS_AVAILABLE = False
    _WS_IMPORT_ERROR = str(exc)
    websocket = None  # type: ignore[assignment]

# ---------------------------------------------------------------------- #
# SOOP protocol constants (reverse-engineered)
# ---------------------------------------------------------------------- #
_LIVE_API_URL = "https://live.afreecatv.com/afreeca/player_live_api.php"
_ESC = "\x1b\t"
_F = "\x0c"
_PING_INTERVAL = 55.0  # วินาที — server ตัดถ้าไม่ ping ใน 5 นาที ส่งถี่กว่า 60s เผื่อ jitter

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}


def _calc_byte_size(s: str) -> int:
    """ตาม reference implementation — UTF-8 byte length + 6 (protocol overhead)"""
    return len(s.encode("utf-8")) + 6


def _resolve_channel(bid: str, bno: str = "", timeout: float = 15.0) -> dict:
    """HTTP resolve bid → ข้อมูล chat server

    Returns: dict {chdomain, chatno, chpt, title, bjid, ftk}
    Raises: RuntimeError ถ้า resolve ไม่สำเร็จ
    """
    import requests
    data = {
        "bid": bid,
        "bno": bno,
        "type": "live",
        "confirm_adult": "false",
        "player_type": "html5",
        "mode": "landing",
        "from_api": "0",
        "pwd": "",
        "stream_type": "common",
        "quality": "HD",
    }
    try:
        r = requests.post(f"{_LIVE_API_URL}?bjid={bid}", data=data, headers=_HEADERS, timeout=timeout)
        r.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"เชื่อม SOOP API ไม่ได้: {exc}")
    try:
        res = r.json()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"SOOP API: parse JSON ไม่ได้: {exc}")
    channel = res.get("CHANNEL") or {}
    chdomain = channel.get("CHDOMAIN")
    chatno = channel.get("CHATNO")
    chpt = channel.get("CHPT")
    if not chdomain or not chatno or not chpt:
        result = channel.get("RESULT", "?")
        raise RuntimeError(
            f"ไม่พบห้องไลฟ์ของ {bid} (RESULT={result}) — อาจพิมพ์ชื่อ channel ผิด หรือยังไม่ได้เชื่อมต่อ Live"
        )
    return {
        "chdomain": str(chdomain).lower(),
        "chatno": str(chatno),
        "chpt": str(int(chpt) + 1),  # ★ ต้อง +1 ตามที่ reference implementation ทำ
        "title": channel.get("TITLE", ""),
        "bjid": channel.get("BJID", bid),
        "ftk": channel.get("FTK", ""),
    }


class SoopChat:
    """SOOP Live chat client — custom binary WebSocket protocol (anonymous/read-only)

    รัน sync websocket loop ใน background daemon thread (เหมือน KickChat)
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
        self._bid = ""
        self._chatno = ""
        self._chdomain = ""
        self._chpt = ""

        self.messages_read = 0
        self._stream_title = ""

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
    def connect(self, bid: str) -> bool:
        """เชื่อมต่อ SOOP — bid = ไอดีสตรีมเมอร์ (BJID)"""
        if not _WS_AVAILABLE:
            self.on_error(
                f"ไม่ได้ติดตั้ง websocket-client: {_WS_IMPORT_ERROR}\n"
                "ติดตั้งด้วย: pip install websocket-client"
            )
            return False

        bid = (bid or "").strip().lstrip("@").strip()
        if "/" in bid:
            bid = bid.rstrip("/").split("/")[-1]
        if not bid:
            self.on_error("กรุณาใส่ SOOP ID (BJID)")
            return False
        if self._is_connected:
            self.on_error("เชื่อมต่อ SOOP อยู่แล้ว — กด Disconnect ก่อน")
            return False

        try:
            info = _resolve_channel(bid)
        except RuntimeError as exc:
            self.on_error(str(exc))
            return False

        self._bid = bid
        self._chatno = info["chatno"]
        self._chdomain = info["chdomain"]
        self._chpt = info["chpt"]
        self._stream_title = info.get("title", "") or ""
        self._stop_event.clear()

        self._thread = threading.Thread(
            target=self._ws_loop, name="SoopWSReader", daemon=True,
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
        self.on_status("⚪ ยกเลิกการเชื่อมต่อ SOOP")

    # ------------------------------------------------------------------ #
    # WebSocket loop (background thread)
    # ------------------------------------------------------------------ #
    def _ws_loop(self) -> None:
        assert websocket is not None
        url = f"wss://{self._chdomain}:{self._chpt}/Websocket/{self._bid}"
        try:
            ws = websocket.WebSocket()
            ws.settimeout(5.0)  # short timeout → ตอบ _stop_event + ping schedule ได้
            ws.connect(url, subprotocols=["chat"])
            self._ws = ws
        except Exception as exc:  # noqa: BLE001
            if not self._stop_event.is_set():
                self.on_error(f"SOOP WS เชื่อมต่อไม่ได้: {exc}")
            self._is_connected = False
            return

        try:
            connect_packet = f"{_ESC}000100000600{_F * 3}16{_F}"
            ws.send(connect_packet)
            # ★ ต้องรอก่อนส่ง JOIN — ตาม reference implementation (sleep 2s)
            #   ยิง JOIN เร็วเกินไปเสี่ยง server ยังไม่พร้อมรับ
            time.sleep(2.0)
            join_packet = f"{_ESC}0002{_calc_byte_size(self._chatno):06}00{_F}{self._chatno}{_F * 5}"
            ws.send(join_packet)
        except Exception as exc:  # noqa: BLE001
            if not self._stop_event.is_set():
                self.on_error(f"SOOP เข้าห้องแชทไม่ได้: {exc}")
            self._is_connected = False
            return

        self._is_connected = True
        self.on_status(f"✅ เชื่อมต่อ SOOP @{self._bid}")

        last_ping = time.time()
        while not self._stop_event.is_set():
            try:
                raw = ws.recv()
            except Exception as exc:  # noqa: BLE001
                if "timed out" in str(exc).lower():
                    if time.time() - last_ping >= _PING_INTERVAL:
                        try:
                            ws.send(f"{_ESC}000000000100{_F}")
                            last_ping = time.time()
                        except Exception:
                            break
                    continue
                if not self._stop_event.is_set():
                    self.on_error(f"SOOP WS หลุด: {exc}")
                break
            if not raw:
                continue
            try:
                self._handle_raw(raw)
            except Exception:
                pass  # ไม่ drop connection เพราะ parse error ข้อความเดียว

        self._is_connected = False
        try:
            ws.close()
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # Message parsing
    # ------------------------------------------------------------------ #
    def _handle_raw(self, raw) -> None:
        """แยก field จาก \\x0c-delimited frame → ChatMessage (ถ้าเป็นแชทปกติ)

        ★ ข้อความประเภทอื่น (โดเนท/별풍선, อีโมติคอน, sub ฯลฯ) ที่ส่งมาในสตรีมข้อมูล
        เดียวกัน ยังไม่ parse ในเวอร์ชันนี้ — ข้ามเงียบๆ (ดู docstring หัวไฟล์)
        """
        if isinstance(raw, str):
            raw = raw.encode("utf-8", errors="ignore")
        parts = raw.split(b"\x0c")
        try:
            messages = [p.decode("utf-8", errors="replace") for p in parts]
        except Exception:
            return
        if len(messages) <= 5:
            return
        if messages[1] in ("-1", "1") or "|" in messages[1]:
            return  # system/control message ไม่ใช่แชทปกติ
        comment = messages[1]
        if not comment.strip():
            return
        user_id = messages[2] if len(messages) > 2 else ""
        nickname = messages[6] if len(messages) > 6 else user_id
        self.messages_read += 1
        msg = ChatMessage(
            platform="soop",
            author=nickname or user_id or "?",
            text=comment,
            extra={"user_id": user_id},
        )
        self.on_message(msg)
