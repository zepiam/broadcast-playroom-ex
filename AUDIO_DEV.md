# 🔊 Broadcast Playroom — Audio Developer Guide

คู่มือปรับแต่งระบบเสียง: TTS, RVC voice conversion, Mixed Voice, Translation

---

## 🎯 ภาพรวม Pipeline เสียง

```
แชทเข้ามา (ChatMessage)
    │
    ▼
┌─────────────────────────────────────┐
│  ChatPipeline (chat_queue.py)       │
│                                     │
│  1. กรอง (banned/spam/skip-long)   │
│  2. แปลภาษา (ถ้าเปิด)              │
│  3. เลือกเสียง (language detect)    │
│  4. TTS synth (edge-tts → MP3)     │
│  5. RVC convert (ถ้าเลือก)          │
│  6. เล่นเสียง (pygame mixer)       │
└─────────────────────────────────────┘
```

---

## 🗣️ 1. TTS Engine (edge-tts)

### วิธีทำงาน
- ใช้ Microsoft Edge TTS API (ฟรี ไม่ต้อง key)
- ทำงานใน asyncio loop แยก (thread)
- สร้าง MP3 → decode ด้วย ffmpeg → numpy array

### เสียงเริ่มต้น
```
th-TH-PremwadeeNeural  ← เสียงหญิงไทย (default)
```

### ไฟล์หลัก: `tts_engine.py`
```python
@dataclass
class TTSParams:
    text: str
    voice: str = "th-TH-PremwadeeNeural"
    rate: str = "+0%"     # ความเร็ว (-100% ถึง +100%)
    volume: str = "+0%"   # ความดัง (-100% ถึง +100%)
    pitch: str = "+0Hz"   # ระดับเสียง
```

### Prosody Tags (ใส่ในข้อความได้)
| Tag | ผล | ตัวอย่าง |
|---|---|---|
| `<break time="500ms"/>` | หยุด 0.5 วินาที | `สวัสดี<break time="1s"/>ครับ` |
| `<emph>word</emph>` | เน้นคำ | `<emph>สำคัญ</emph>` |
| `__` (2+ underscores) | หยุด (0.05s ต่อ _ ) | `สวัสดี__ครับ` |
| `\|` (1+ pipes) | ยืดเสียง (0.1s ต่อ \|) | `สวัสดี\|\|ครับ` |

### การปรับ rate/volume
```python
# ใน settings.py
rate: int = 0       # -100 ถึง +100 (เปอร์เซ็นต์)
volume: int = 0     # -100 ถึง +100

# Per-platform volume offset
tts_volume_twitch: int = 0
tts_volume_youtube: int = 0
# ... (แต่ละแพลตฟอร์ม)
```

---

## 🎤 2. RVC Voice Conversion

### วิธีทำงาน
- รับ audio จาก TTS → แปลงเสียงเป็น VTuber/อนิเมะ/ผู้ประกาศ
- ใช้ PyTorch + CUDA (GPU) หรือ CPU
- HuBERT cache แชร์ระหว่างโมเดล (โหลดครั้งเดียว)

### ไฟล์หลัก: `rvc_engine.py`
```python
@dataclass
class RVCParams:
    f0up_key: int = 0        # ระดับเสียง (-12 ถึง +12 semitones)
    f0method: str = "rmvpe"  # rmvpe/crepe/harvest/pm (rmvpe ดีสุดสำหรับไทย)
    index_rate: float = 0.75 # ความเข้มของ feature index
    protect: float = 0.33    # ป้องกันเสียงพื้นเสียหาย (สำคัญสำหรับไทย)
    index_path: str = ""     # path ไฟล์ .index
```

### การเพิ่มโมเดล RVC ใหม่
1. หาโมเดล `.pth` (จาก HuggingFace หรือ train เอง)
2. (optional) ไฟล์ `.index` ที่ตรงชื่อ (เช่น `voice.pth` + `voice.index`)
3. วางใน `rvc_models/` หรือ `~/.tts-for-livestream/voices/`
4. โปรแกรมจะ auto-discover → แสดงในเมนูเลือกเสียง

```python
# rvc_engine.py — bundled models registry
# โครงสร้างโฟลเดอร์:
rvc_models/
├── haruka/
│   ├── haruka.pth        ← โมเดล
│   └── haruka.index      ← (optional) feature index
├── calliope/
│   └── calliope.pth
└── ...
```

### ปรับแต่ง RVC
```python
# settings.py
rvc_f0method: str = "rmvpe"   # วิธี pitch detection
rvc_pitch: int = 0            # ยก/ลด pitch (-12 ถึง +12)

# ใน pipeline:
RVCParams(
    f0method=config.rvc_f0method,
    f0up_key=config.rvc_pitch,
    index_rate=0.75,
    protect=0.33,
    index_path=rvc_index_path,
)
```

### วิธีทำงาน (เทคนิค)
1. TTS สร้าง MP3 → decode เป็น float32 44100Hz
2. RVC resample เป็น 16kHz (ทำงานที่ 16kHz)
3. HuBERT สกัด features → model แปลง → output 16kHz
4. Resample กลับ 44100Hz (pygame mixer ต้องการ 44100)
5. Peak-normalize (กัน clipping)

---

## 🌐 3. Mixed Voice (อ่านหลายภาษาในประโยคเดียว)

### วิธีทำงาน
- แยกข้อความตาม Unicode script → TTS แต่ละส่วนด้วยภาษานั้น → ต่อเสียง

```
"สวัสดี hello こんにちは" 
    ↓
[("สวัสดี", th), ("hello", en), ("こんにちは", ja)]
    ↓
TTS(th) + TTS(en) + TTS(ja) → concat (50ms silence between)
```

### ไฟล์หลัก: `language_detect.py`
```python
# แยกภาษาจากตัวอักษร
VOICE_BY_LANG = {
    "th": "th-TH-PremwadeeNeural",
    "en": "en-US-AriaNeural",
    "ja": "ja-JP-NanamiNeural",
    "ko": "ko-KR-SunHiNeural",
    "zh": "zh-CN-XiaoxiaoNeural",
    "zh-TW": "zh-TW-HsiaoChenNeural",
    "fr": "fr-FR-DeniseNeural",
}
```

### เพิ่มภาษาใหม่
```python
# language_detect.py
VOICE_BY_LANG["vi"] = "vi-VN-HoaiMyNeural"  # เวียดนาม
VOICE_BY_LANG["id"] = "id-ID-ArdiNeural"    # อินโดนีเซีย

# settings.py — เพิ่มใน multilang_langs
multilang_langs: list = ["en", "ja", "ko", "zh", "zh-TW", "fr", "vi", "id"]
```

### Settings
```python
# settings.py
multilang_enabled: bool = True       # เปิด/ปิด multi-language
mixed_voice_enabled: bool = True     # เปิด/ปิด Mixed Voice
multilang_langs: list = ["en", "ja", "ko", "zh", "zh-TW", "fr"]
```

---

## 🔄 4. ระบบแปลภาษา (Translation)

### วิธีทำงาน
- ก่อน TTS → แปลเป็นไทยก่อน → TTS อ่านไทย
- รองรับ: Google (ฟรี), DeepL, DeepSeek (LLM)

### Settings
```python
# settings.py
auto_translate_enabled: bool = False
auto_translate_provider: str = "google"  # "google" | "deepl" | "deepseek"
auto_translate_api_key: str = ""         # DeepL/DeepSeek key
auto_translate_target_lang: str = "th"   # แปลเป็นภาษาอะไร
auto_translate_langs: list = ["en", "ja", "ko", "zh", "vi", "id"]  # ภาษาที่จะแปล
force_translate_users: list = []         # บังคับแปลรายบุคคล
```

### Flow
```
message "Hello everyone"
    ↓
detect_language → "en"
    ↓
_is_thai_speaker(author)? → No → translate
    ↓
Translator.translate("Hello everyone", source="en") → "สวัสดีทุกคน"
    ↓
msg.text = "สวัสดีทุกคน"  (TTS อ่านไทย)
msg.extra["translated"] = True
msg.extra["original_text"] = "Hello everyone"
```

---

## ⚡ 5. Auto-Speed (เร่งความเร็วอัตโนมัติ)

ข้อความยาว → เร่ง TTS อัตโนมัติ:

```python
# settings.py
auto_speed: bool = False
auto_speed_length: int = 80        # ถ้าเกิน 80 ตัวอักษร → เร่ง
auto_speed_boost: int = 30         # เร่ง +30%

# ใน pipeline:
if config.auto_speed and len(text) > config.auto_speed_length:
    effective_rate = min(rate + config.auto_speed_boost, 100)
```

---

## 🔇 6. Skip-Long (ข้ามข้อความยาว)

```python
# settings.py
skip_long_enabled: bool = False
skip_long_threshold: int = 200    # ถ้าเกิน 200 ตัวอักษร → ข้าม + เล่นเสียงเตือน
warn_sound_path: str = ""         # path เสียงเตือน
warn_sound_volume: float = 0.6
```

---

## 🔔 7. เสียงแจ้งเตือน + Event Sounds

```python
# settings.py
notifications: dict = {}  # per-event sound config
# format: {"twitch_sub": {"sound": "path.wav", "volume": 0.7}, ...}

# events ที่รองรับ:
# twitch: sub, bits, raid, redeem
# youtube: superchat, membership, gift
# tiktok: gift, follow, share, like, join
# kick: subgift
```

---

## 🎵 8. Secret Codes + Playroom

```python
# settings.py
secret_codes: list = []  # [{code: "#dice", sound_path: "dice.wav", volume: 0.8}]
secret_code_daily_limit: int = 3
code_sound_muted: bool = False

# playroom (มินิเกมวิดีโอ)
playroom_enabled: bool = True
playroom_trigger: str = "#"  # พิมพ์ # นำหน้า
```

---

## 📁 ไฟล์ที่เกี่ยวข้องกับเสียง

| ไฟล์ | หน้าที่ |
|---|---|
| `chat_queue.py` | Pipeline หลัก — กรอง → TTS → RVC → เล่น |
| `tts_engine.py` | edge-tts wrapper (asyncio + MP3) |
| `rvc_engine.py` | RVC voice conversion (PyTorch) |
| `language_detect.py` | ตรวจภาษา + VOICE_BY_LANG mapping |
| `translator.py` | แปลภาษา (Google/DeepL/DeepSeek) |
| `audio_player.py` | pygame mixer wrapper |
| `settings.py` | ทุก audio settings |
| `app_gui.py` | wiring: `_build_pipeline_config`, `_ensure_rvc_loaded` |
| `ffmpeg.exe` | decode MP3 → numpy (จำเป็น!) |

---

## 🛠️ การปรับแต่งทั่วไป

### เปลี่ยนเสียง TTS เริ่มต้น
```python
# settings.py
BASE_VOICE_TTS = "th-TH-PremwadeeNeural"  # เปลี่ยนเป็นเสียงอื่นได้
```

### เพิ่มเสียงใหม่ในเมนู
วาง `.pth` ใน `rvc_models/` → auto-discover → แสดงในเมนู

### ปรับ RVC ละเอียด
```python
# rvc_engine.py — RVCParams
f0method = "rmvpe"   # ดีสุดสำหรับไทย
protect = 0.33       # ป้องกันเสียงพื้นเสียหาย (สูง = ปลอดภัยขึ้น)
index_rate = 0.75    # ความเข้ม feature matching (สูง = เหมือนต้นแบบมากขึ้น)
```

### ทดสอบ TTS เดี่ยว
```bash
python -c "
from tts_engine import TTSEngine, TTSParams
import asyncio
engine = TTSEngine()
async def test():
    mp3 = await engine._synthesize_segment('สวัสดีครับ', 'th-TH-PremwadeeNeural', '+0%', '+0%')
    with open('test.mp3', 'wb') as f: f.write(mp3)
    print('saved test.mp3')
asyncio.run(test())
"
```

### ทดสอบ RVC เดี่ยว
```bash
python rvc_engine.py input.wav diona
```
