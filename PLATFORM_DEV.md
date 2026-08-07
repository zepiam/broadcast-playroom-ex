# 📡 Broadcast Playroom — Platform Developer Guide

คู่มือสำหรับนักพัฒนาที่ต้องการ **เพิ่มแพลตฟอร์มใหม่** (Discord, Facebook Live, etc.)

---

## 🎯 ภาพรวม

Broadcast Playroom ใช้ระบบ **duck-typed** — แพลตฟอร์มทุกตัวแค่ต้องมี:
1. Class ที่รับ callback 4 ตัวใน constructor
2. Method `connect(target) -> bool` และ `disconnect()`
3. ส่ง `ChatMessage` dataclass กลับผ่าน callback

```
แพลตฟอร์มใหม่ (chat_xxx.py)
    │
    ├── connect(target) ──── เชื่อม server/API/WebSocket
    │
    ├── รับข้อความ/emote/event
    │       │
    │       └── on_message(ChatMessage(...)) ──► app_gui.py
    │                                               │
    │                                               ├── Live Chat display
    │                                               ├── Event log
    │                                               ├── TTS pipeline
    │                                               └── Overlay
    │
    └── disconnect() ──── ตัดการเชื่อมต่อ
```

---

## 📦 ขั้นตอนการเพิ่มแพลตฟอร์มใหม่ (5 ขั้น)

### ขั้นที่ 1: สร้างไฟล์ `chat_xxx.py`

สร้างไฟล์ใหม่ในโฟลเดอร์โปรเจค ตั้งชื่อตามแพลตฟอร์ม เช่น `chat_discord.py`

### ขั้นที่ 2: เขียน Client Class

```python
# chat_discord.py
import threading
from chat_twitch import ChatMessage  # ใช้ ChatMessage ร่วมกับทุกแพลตฟอร์ม


class DiscordChat:
    """Discord chat client — ตัวอย่างโครงสร้าง"""

    def __init__(self, on_message, on_status=None, on_error=None,
                 on_viewer_count=None, poll_interval=2.0):
        """
        Constructor ต้องรับ callback 4 ตัว:
          on_message(ChatMessage)     — ข้อความ/event ใหม่ (บังคับ)
          on_status(str)              — สถานะการเชื่อมต่อ ("เชื่อมต่อแล้ว", ฯลฯ)
          on_error(str)               — error message
          on_viewer_count(str, int)   — platform name, จำนวนผู้ชม
        """
        self.on_message = on_message
        self.on_status = on_status
        self.on_error = on_error
        self.on_viewer_count = on_viewer_count
        self._stop = threading.Event()
        self._thread = None
        self._connected = False

    def connect(self, target: str) -> bool:
        """
        เชื่อมต่อแพลตฟอร์ม
          target = ชื่อ channel/URL/ID ที่ผู้ใช้กรอก
          return True ถ้าสำเร็จ, False ถ้าล้มเหลว
        """
        try:
            # TODO: เชื่อมต่อ server/API/WebSocket ของแพลตฟอร์ม
            self._connected = True
            self._stop.clear()
            self._thread = threading.Thread(target=self._poll_loop, daemon=True)
            self._thread.start()
            if self.on_status:
                self.on_status("เชื่อมต่อแล้ว")
            return True
        except Exception as e:
            if self.on_error:
                self.on_error(str(e))
            return False

    def disconnect(self) -> None:
        """ตัดการเชื่อมต่อ + หยุด thread"""
        self._stop.set()
        self._connected = False
        if self._thread:
            self._thread.join(timeout=5)
        if self.on_status:
            self.on_status("ตัดการเชื่อมต่อแล้ว")

    @property
    def is_connected(self) -> bool:
        return self._connected

    def _poll_loop(self):
        """Loop หลัก — รับข้อความจากแพลตฟอร์ม ส่งผ่าน on_message"""
        while not self._stop.is_set():
            try:
                # TODO: รับข้อมูลจากแพลตฟอร์ม (poll/API/WebSocket)
                # ตัวอย่าง: ได้ข้อความใหม่
                raw_messages = self._fetch_messages()  # ฟังก์ชั่นของคุณ

                for raw in raw_messages:
                    msg = self._parse_message(raw)
                    if msg:
                        self.on_message(msg)  # ส่งกลับไป app

            except Exception as e:
                if self.on_error:
                    self.on_error(str(e))
                self._stop.wait(5)  # รอ 5 วิbefore retry

    def _parse_message(self, raw) -> ChatMessage:
        """
        แปลง raw data จากแพลตฟอร์ม เป็น ChatMessage
        สำคัญมาก — ต้องกรอกให้ถูกต้อง
        """
        return ChatMessage(
            platform="discord",              # ชื่อแพลตฟอร์ม (ตัวเล็ก)
            author=raw.get("username", ""),  # ชื่อคนส่ง
            text=raw.get("content", ""),     # ข้อความ (emote ถูก strip ออกแล้วสำหรับ TTS)
            event="message",                 # ประเภท (ดูตารางด้านล่าง)
            extra={                          # ข้อมูลเสริม
                "raw_text": raw.get("content", ""),  # ข้อความเดิม (ก่อน strip emote)
                "segments": [...],                    # สำหรับ render ใน Live Chat
                "color": raw.get("color", ""),        # สีชื่อผู้ใช้
            },
        )
```

### ขั้นที่ 3: ลงทะเบียนใน `app_gui.py`

```python
# app_gui.py — ส่วน import (บนสุด)
from chat_discord import DiscordChat

# app_gui.py — ส่วน PLATFORM_REGISTRY (ประมาณบรรทัด 528)
PLATFORM_REGISTRY = {
    # ... existing platforms ...

    "discord": {
        "label": "Discord",
        "emoji": "💬",
        "color": "#5865F2",
        "logo": "assets/discord.png",  # โลโก้ (optional)
        "placeholder": "Server ID หรือ invite link",
        "saved_attr": "discord_target",     # ชื่อ field ใน AppSettings
        "client_cls": DiscordChat,          # class ของคุณ
        "client_kwargs": lambda app: {},    # extra constructor args (ถ้ามี)
        "supports_autoconnect": False,       # auto-reconnect (ส่วนใหญ่ False)
    },
}

# app_gui.py — ส่วน PLATFORM_ORDER (ประมาณบรรทัด 588)
PLATFORM_ORDER = ["twitch", "youtube", "mylive", "tiktok", "kick", "discord"]
```

### ขั้นที่ 4: เพิ่ม Settings Field

```python
# settings.py — เพิ่มใน class AppSettings
discord_target: str = ""  # เก็บชื่อ channel ล่าสุด

# ถ้ามี per-platform volume/toggle:
tts_volume_discord: int = 0      # volume offset (-50 to +50)
read_tts_discord: bool = True     # อ่าน TTS หรือไม่
```

### ขั้นที่ 5: เพิ่ม "Open URL" (optional)

```python
# app_gui.py — ฟังก์ชั่น _platform_open_url (ประมาณบรรทัด 591)
def _platform_open_url(self, platform):
    urls = {
        # ...
        "discord": f"https://discord.com/channels/{target}",
    }
    # ...
```

---

## 📋 ChatMessage Dataclass — ฟิลด์ที่ต้องกรอก

```python
@dataclass
class ChatMessage:
    platform: str                # "twitch" | "youtube" | "discord" | ...
    author: str                  # ชื่อคนส่ง (แสดงใน Live Chat)
    text: str                    # ข้อความ (emote strip ออกแล้วสำหรับ TTS)
    event: str = "message"       # ประเภท (ดูตารางด้านล่าง)
    amount: Optional[int] = None # จำนวน (bits, เงิน, จำนวนผู้ชม raid)
    tier: Optional[int] = None   # sub tier (1/2/3, Prime=0)
    system_text: Optional[str] = None  # ข้อความระบบ (TTS อ่านได้)
    extra: dict = field(default_factory=dict)  # ข้อมูลเสริม
```

### Event Types (ฟิลด์ `event`)

| event | ความหมาย | amount | ตัวอย่าง |
|---|---|---|---|
| `"message"` | ข้อความทั่วไป | — | แชทปกติ |
| `"bits"` | บริจาค (bits/donate) | จำนวนเงิน/bits | Twitch bits, YouTube superchat |
| `"sub"` | สมัครสมาชิก | — | Twitch sub, YouTube membership |
| `"resub"` | ต่อสมาชิก | เดือนที่ | "Subbed for 12 months" |
| `"subgift"` | ส่งของขวัญสมาชิก | จำนวน | sub gift, gifted sub |
| `"raid"` | เรด | จำนวนผู้ชม | Twitch raid |
| `"redeem"` | Channel Points | — | Twitch reward |
| `"gift"` | ของขวัญ | จำนวน | TikTok gift |
| `"like"` | ไลค์ | จำนวน | TikTok like |
| `"follow"` | ติดตาม | — | — |
| `"share"` | แชร์ | — | — |
| `"join"` | เข้าร่วม | — | — |
| `"superchat"` | YouTube Super Chat | เงิน | — |
| `"membership"` | YouTube Membership | — | — |

### `extra` dict — ฟิลด์ที่ใช้บ่อย

| Key | ค่า | ใช้ทำอะไร |
|---|---|---|
| `raw_text` | str | ข้อความเดิมก่อน strip emote (แสดงใน Live Chat) |
| `segments` | list | `[{type:"text"\|"emote"\|"emoji", ...}]` สำหรับ render |
| `color` | str | สีชื่อผู้ใช้ (hex) |
| `emotes` | list | `[{id, name, start, end}]` Twitch emotes |
| `sticker_url` | str | URL รูป sticker (MyLive) |
| `badges` | str | Twitch badges |

---

## 🎭 การจัดการ Emote

Emote ต้องแยกออกจาก `text` (สำหรับ TTS) แต่เก็บไว้ใน `extra` (สำหรับแสดงผล):

```python
def _parse_message(self, raw):
    full_text = raw["content"]
    emotes = raw.get("emotes", [])

    # strip emote ออกจาก text (สำหรับ TTS)
    tts_text = full_text
    for emote in sorted(emotes, key=lambda e: e["start"], reverse=True):
        tts_text = tts_text[:emote["start"]] + tts_text[emote["end"]:]

    # สร้าง segments สำหรับ render
    segments = self._build_segments(full_text, emotes)

    return ChatMessage(
        platform="discord",
        author=raw["username"],
        text=tts_text.strip(),           # TTS text (ไม่มี emote)
        extra={
            "raw_text": full_text,        # เดิม (มี emote)
            "segments": segments,         # render-ready
        },
    )
```

### Segments format

```python
segments = [
    {"type": "text", "text": "สวัสดี"},
    {"type": "emote", "name": "Kappa", "url": "https://..."},
    {"type": "text", "text": "ทุกคน"},
]
```

---

## 🔌 วิธีเชื่อมต่อ — 4 รูปแบบที่ใช้ในปัจจุบัน

### 1. IRC (Twitch)
- เปิด SSL socket → JOIN channel → อ่านบรรทัด IRC
- ใช้ `CAP REQ twitch.tv/tags` เพื่อรับ metadata
- **ไฟล์อ้างอิง:** `chat_twitch.py`

### 2. HTTP API Polling (YouTube)
- ยิง POST ไป InnerTube API (`live_chat/get_live_chat`)
- Poll ทุก 2-10 วินาที (adaptive backoff)
- Dedup ด้วย message ID
- **ไฟล์อ้างอิง:** `chat_youtube.py`

### 3. WebSocket (Kick, TikTok)
- เชื่อม WebSocket → subscribe channel → รับ push
- Kick: Pusher WebSocket (anonymous)
- TikTok: `TikTokLive` library (protobuf)
- **ไฟล์อ้างอิง:** `chat_kick.py`, `chat_tiktok.py`

### 4. Browser Automation (MyLive)
- เปิด headless Chromium (Playwright)
- Navigate ไปหน้าสตรีม → poll DOM selector
- จำเป็นเมื่อแพลตฟอร์มเป็น SPA (Vue/React)
- **ไฟล์อ้างอิง:** `chat_mylive.py`

---

## 🧪 การทดสอบ

### ทดสอบแยกส่วน
```python
# test_discord.py
from chat_discord import DiscordChat

def on_message(msg):
    print(f"[{msg.platform}] {msg.author}: {msg.text} (event={msg.event})")

client = DiscordChat(on_message=on_message)
client.connect("your-channel-id")
input("กด Enter เพื่อ disconnect...")
client.disconnect()
```

### ทดสอบในโปรแกรมจริง
1. เพิ่มแพลตฟอร์มตามขั้นตอนข้างบน
2. รัน `python main.py`
3. กรอก channel → กด connect
4. ดู Live Chat ว่าข้อความแสดงไหม
5. ดู TTS ว่าอ่านไหม

---

## 📁 ไฟล์ที่เกี่ยวข้อง

| ไฟล์ | หน้าที่ |
|---|---|
| `chat_twitch.py` | Twitch IRC + `ChatMessage` dataclass (canonical) |
| `chat_youtube.py` | YouTube InnerTube API |
| `chat_mylive.py` | MyLive Playwright browser |
| `chat_tiktok.py` | TikTok WebSocket (TikTokLive) |
| `chat_kick.py` | Kick Pusher WebSocket |
| `plugin_api.py` | `PlatformClient` ABC (reference) |
| `app_gui.py` | `PLATFORM_REGISTRY` + callback wiring |
| `settings.py` | `AppSettings` (per-platform fields) |
