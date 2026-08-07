# 📖 Broadcast Playroom — Plugin Developer Guide

คู่มือสำหรับนักพัฒนาที่ต้องการสร้าง plugin สำหรับ Broadcast Playroom

> 📌 **เอกสารที่เกี่ยวข้อง:**
> - [PLATFORM_DEV.md](PLATFORM_DEV.md) — คู่มือเพิ่มแพลตฟอร์มใหม่ (Discord, Facebook, ฯลฯ)
> - [AUDIO_DEV.md](AUDIO_DEV.md) — คู่มือปรับแต่งเสียง (TTS, RVC, Mixed Voice, Translation)
> - [ARCHITECTURE.md](ARCHITECTURE.md) — ภาพรวมสถาปัตยกรรมทั้งระบบ

---

## ภาพรวม

Broadcast Playroom รองรับ plugin 2 ระดับ:

| ระดับ | ความยาก | ต้องเขียนโค้ด? | ความปลอดภัย |
|---|---|---|---|
| **Config-only** (YAML) | ⭐ ง่าย | ❌ ไม่ต้อง | ✅ ปลอดภัย (ไม่รันโค้ด) |
| **Code-based** (Python) | ⭐⭐⭐ ยาก | ✅ ต้องเขียน | ⚠️ รัน Python ได้เต็มที่ |

---

## 1. Config-only Plugin (แนะนำเริ่มต้น)

### 1.1 ประเภท: Command

สร้างไฟล์ `.yml` ใน `plugins/commands/`:

```yaml
# plugins/commands/weather.yml
name: "สภาพอากาศ"           # ชื่อ plugin (แสดงใน Settings)
trigger: "!weather"          # คำสั่งที่ผู้ชมพิมพ์ในแชท
description: "บอกอุณหภูมิ"    # คำอธิบายสั้นๆ
response_type: "text"        # "text" = อ่าน TTS เท่านั้น | "overlay" = แสดงใน overlay ด้วย
response: "สวัสดี {author} อุณหภูมิวันนี้ 35 องศา"  # ข้อความตอบกลับ
cooldown: 30                 # คูลดาวน์วินาที (กัน spam) — 0 = ไม่จำกัด
enabled: true                # เปิด/ปิด plugin
```

### 1.2 ตัวแปรที่ใช้ใน `response`

| ตัวแปร | แทนด้วย | ตัวอย่าง |
|---|---|---|
| `{author}` | ชื่อคนพิมพ์ | `MeN9CH` |
| `{trigger}` | คำสั่งที่ใช้ | `!weather` |
| `{time}` | เวลาปัจจุบัน | `14:30` |

### 1.3 ตัวอย่าง plugin

**ทักทาย:**
```yaml
name: "ทักทาย"
trigger: "!hi"
response: "สวัสดีครับ {author} ยินดีต้อนรับสู่ช่อง!"
cooldown: 10
enabled: true
```

**บอกเวลา:**
```yaml
name: "เวลา"
trigger: "!time"
response: "ตอนนี้เวลา {time} ครับ"
cooldown: 5
enabled: true
```

**คำสั่งพร้อม argument:**
```yaml
# ผู้ชมพิมพ์: !shout สวัสดี
# trigger จะ match ที่ !shout (ส่วน "สวัสดี" ถือเป็น args — ยังไม่รองรับใน config-only)
name: "ตะโกน"
trigger: "!shout"
response: "{author} ตะโกนว่า... ใครบ้างได้ยิน!"
cooldown: 15
enabled: true
```

### 1.4 ข้อจำกัดของ Config-only
- ❌ ไม่สามารถเรียก API ภายนอก (เช่น ดึงสภาพอากาศจริง)
- ❌ ไม่สามารถอ่านไฟล์
- ❌ ไม่สามารถเขียน logic (if/else, loop)
- ✅ เหมาะสำหรับ: ทักทาย, บอกเวลา, แจ้งเตือน, custom announcement

> 💡 ถ้าต้องการ logic ซับซ้อน → ใช้ Code-based Plugin (ด้านล่าง)

---

## 2. Code-based Plugin (ขั้นสูง)

### 2.1 โครงสร้างไฟล์

```
plugins/
└── my_plugin/
    ├── __init__.py
    ├── plugin.json          # metadata
    └── handler.py           # Python code
```

### 2.2 plugin.json (metadata)

```json
{
  "name": "My Plugin",
  "version": "1.0.0",
  "author": "Your Name",
  "description": "คำอธิบาย plugin",
  "type": "command",
  "entry": "handler.MyCommand"
}
```

| field | คำอธิบาย |
|---|---|
| `name` | ชื่อ plugin |
| `version` | เวอร์ชัน (semver) |
| `author` | ชื่อผู้สร้าง |
| `type` | `command` \| `tts` \| `platform` |
| `entry` | `module.ClassName` ที่จะโหลด |

---

## 3. API Reference

### 3.1 CommandHandler (command plugin)

สร้างคำสั่งแชทที่ตอบกลับด้วย logic ของคุณเอง

```python
# plugins/my_plugin/handler.py
from plugin_api import CommandHandler

class WeatherCommand(CommandHandler):
    """คำสั่ง !weather [city] — บอกอุณหภูมิ"""

    @property
    def trigger(self) -> str:
        return "!weather"

    @property
    def cooldown(self) -> int:
        return 60  # คูลดาวน์ 60 วินาที

    def handle(self, args: str, author: str):
        """
        ถูกเรียกเมื่อผู้ชมพิมพ์ !weather

        Args:
            args: ส่วนที่อยู่หลัง trigger (เช่น "!weather bangkok" → args="bangkok")
            author: ชื่อคนพิมพ์ (เช่น "MeN9CH")

        Returns:
            str: ข้อความที่จะให้ TTS อ่าน (หรือ None ถ้าไม่ตอบ)
        """
        city = args.strip() or "bangkok"
        # ตัวอย่าง: เรียก API
        import requests
        try:
            r = requests.get(f"https://api.weather.com/{city}", timeout=5)
            temp = r.json()["temp"]
            return f"อุณหภูมิที่ {city} คือ {temp} องศาครับ {author}"
        except Exception:
            return f"ขออภัย ไม่สามารถดึงข้อมูลอากาศได้"
```

#### API: `CommandHandler`

| Property/Method | ประเภท | คำอธิบาย |
|---|---|---|
| `trigger` | `@property → str` | คำสั่งที่เรียก (ต้องขึ้นต้นด้วย `!` หรือ `#`) |
| `cooldown` | `@property → int` | คูลดาวน์วินาที (default: 0 = ไม่จำกัด) |
| `handle(args, author)` | `method → str\|None` | ประมวลผลคำสั่ง → คืนข้อความตอบกลับ |

#### การ match
- `!weather` → match exact
- `!weather bangkok` → match + `args = "bangkok"`
- `!weatherrr` → ไม่ match

---

### 3.2 TTSEngine (TTS plugin — อนาคต)

สร้าง TTS engine ของคุณเอง (เช่น Google Cloud TTS, Azure, local model)

```python
# plugins/my_tts/engine.py
from plugin_api import TTSEngine

class GoogleCloudTTS(TTSEngine):

    @property
    def name(self) -> str:
        return "google_cloud"

    @property
    def voices(self) -> list[str]:
        return ["th-TH-A", "th-TH-B", "en-US-C"]

    def synth(self, text: str, voice: str = "th-TH-A", rate: int = 0) -> bytes:
        """ลงเสียง → คืน MP3 bytes"""
        from google.cloud import texttospeech
        client = texttospeech.TextToSpeechClient()
        response = client.synthesize_speech(
            input=texttospeech.SynthesisInput(text=text),
            voice=texttospeech.VoiceSelectionParams(
                language_code=voice.split("-")[0],
                name=voice,
            ),
            audio_config=texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
                speaking_rate=1.0 + (rate / 100.0),
            ),
        )
        return response.audio_content

    def cleanup(self):
        """ทำความสะอาดก่อนปิด"""
        pass
```

#### API: `TTSEngine`

| Property/Method | ประเภท | คำอธิบาย |
|---|---|---|
| `name` | `@property → str` | ชื่อ engine |
| `voices` | `@property → list[str]` | รายชื่อ voice (override ได้) |
| `synth(text, voice, rate)` | `method → bytes` | ลงเสียง → คืน **MP3 bytes** |
| `cleanup()` | `method → None` | ทำความสะอาด (override ได้) |

#### ข้อกำหนด `synth()`
- **ต้องคืน MP3 bytes** (ไม่ใช่ WAV, ไม่ใช่ numpy array)
- `voice`: เลือกจาก `voices` property
- `rate`: ความเร็วเป็น % (-50 ถึง +100, 0 = ปกติ)

---

### 3.3 PlatformClient (platform plugin — อนาคต)

สร้างแพลตฟอร์มแชทใหม่ (เช่น Discord, Facebook Live, Trovo)

```python
# plugins/discord/client.py
from plugin_api import PlatformClient

class DiscordClient(PlatformClient):

    @property
    def name(self) -> str:
        return "discord"

    @property
    def label(self) -> str:
        return "Discord"

    def connect(self, target: str) -> bool:
        """เชื่อมต่อ — target คือ channel ID หรือ URL"""
        # เชื่อมต่อ Discord Gateway
        self._connected = True
        return True

    def disconnect(self) -> None:
        """ยกเลิกการเชื่อมต่อ"""
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected
```

#### API: `PlatformClient`

| Property/Method | ประเภท | คำอธิบาย |
|---|---|---|
| `name` | `@property → str` | ชื่อ platform (lowercase, ไม่มีช่องว่าง) |
| `label` | `@property → str` | ชื่อที่แสดงใน UI |
| `connect(target)` | `method → bool` | เชื่อมต่อ → คืน True ถ้าสำเร็จ |
| `disconnect()` | `method → None` | ยกเลิกการเชื่อมต่อ |
| `is_connected` | `@property → bool` | สถานะการเชื่อมต่อ |

#### การส่งข้อความเข้าโปรแกรม
เมื่อได้รับข้อความจาก platform → เรียก callback:

```python
# โปรแกรมจะส่ง callback มาให้:
on_message: Callable[[ChatMessage], None]

# คุณสร้าง ChatMessage:
from chat_queue import ChatMessage
msg = ChatMessage(
    platform="discord",
    author=username,
    text=message_content,
    event="message",
    extra={},
)
on_message(msg)
```

---

## 4. การติดตั้ง Plugin

### Config-only (YAML)
1. สร้างไฟล์ `.yml` ใน `plugins/commands/`
2. รีสตาร์ทโปรแกรม (หรือกด reload ใน Settings > Plugins)

### Code-based (Python)
1. สร้างโฟลเดอร์ใน `plugins/` (เช่น `plugins/my_plugin/`)
2. สร้าง `plugin.json` + Python code
3. รีสตาร์ทโปรแกรม

---

## 5. Settings UI (วางแผนไว้)

Settings > Plugins (tab ใหม่ในอนาคต)
```
┌─────────────────────────────────────────┐
│ 🧩 Plugins                              │
│                                         │
│ ☑ ทักทาย (!hi) — cooldown 10s           │
│ ☑ เวลา (!time) — cooldown 5s            │
│ ☐ สภาพอากาศ (!weather) — cooldown 60s  │
│                                         │
│ [🔄 Reload] [📁 เปิดโฟลเดอร์ plugins]   │
└─────────────────────────────────────────┘
```

---

## 6. ความปลอดภัย

| ประเภท | รันโค้ด? | เสี่ยง? |
|---|---|---|
| Config-only (YAML) | ❌ | ✅ ปลอดภัย |
| Code-based (Python) | ✅ | ⚠️ รันได้ทุกอย่าง (เหมือน Python ปกติ) |

**คำแนะนำ:**
- ใช้ config-only เมื่อทำได้ (ปลอดภัยกว่า)
- ตรวจสอบ code-based plugin จากแหล่งที่เชื่อถือก่อนติดตั้ง
- ไม่ติดตั้ง plugin จากแหล่งที่ไม่น่าเชื่อถือ

---

## 7. Debug

### ตรวจสอบ plugin ที่โหลด
```python
from plugin_loader import get_plugin_loader
loader = get_plugin_loader()
for p in loader.plugins:
    print(f"{p.trigger} → {p.name} (enabled={p.enabled}, cooldown={p.cooldown})")
```

### ทดสอบคำสั่ง
```python
result = loader.check_command("!hi", author="test_user")
if result:
    response, plugin = result
    print(f"Response: {response}")
```

### Log
Plugin error จะถูกบันทึกใน `logs/tts_00.log`

---

## 8. Roadmap

| ฟีเจอร์ | สถานะ |
|---|---|
| Command plugin (config-only) | ✅ พร้อมใช้ |
| Plugin loader + YAML | ✅ พร้อมใช้ |
| Abstract classes (TTSEngine, PlatformClient) | ✅ สร้างแล้ว (ยังไม่ wire) |
| Wire command plugin เข้า TTS pipeline | 🔜 ขั้นถัดไป |
| Settings > Plugins tab | 🔜 |
| TTS engine plugin | 🔜 อนาคต |
| Platform plugin | 🔜 อนาคต |
| Plugin marketplace | 🔜 อนาคตไกล |
