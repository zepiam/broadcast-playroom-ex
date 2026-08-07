# 🏗️ Broadcast Playroom — Architecture

ภาพรวมสถาปัตยกรรมโปรแกรม สำหรับการทำเว็บไซต์หรือเอกสารประกอบ

---

## ภาพรวมระบบ

```
┌─────────────────────────────────────────────────────────────────┐
│                    Broadcast Playroom                            │
│                                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐         │
│  │  Twitch  │  │ YouTube  │  │  MyLive  │  │  TikTok  │  KICK   │
│  │  Client  │  │  Client  │  │  Client  │  │  Client  │         │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘         │
│       │              │              │              │              │
│       └──────────────┴──────────────┴──────────────┘              │
│                          │                                       │
│                    on_message()                                  │
│                          │                                       │
│                    ┌─────▼─────┐                                 │
│                    │  Message  │                                 │
│                    │  Buffer   │                                 │
│                    └─────┬─────┘                                 │
│                          │                                       │
│              ┌───────────┼───────────┐                           │
│              │           │           │                            │
│        ┌─────▼─────┐ ┌───▼───┐ ┌────▼─────┐                     │
│        │ Live Chat │ │ Event │ │   TTS    │                      │
│        │   + Popout│ │  Log  │ │ Pipeline │                      │
│        └───────────┘ └───────┘ └────┬─────┘                      │
│                                    │                             │
│              ┌─────────────────────┼─────────────────┐           │
│              │                     │                 │            │
│        ┌─────▼─────┐        ┌──────▼──────┐  ┌──────▼──────┐    │
│        │   edge    │        │    RVC      │  │  Mixed Voice│    │
│        │   TTS     │        │  (PyTorch)  │  │  (multi)    │    │
│        └───────────┘        └─────────────┘  └─────────────┘    │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │                    Overlays                               │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │    │
│  │  │   OBS    │  │   Game   │  │ Overlay+ │  │ Playroom │  │    │
│  │  │ Overlay  │  │ Overlay  │  │ (custom) │  │ (games)  │  │    │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘  │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │                    Translation                            │    │
│  │     Google (free)  │  DeepL  │  DeepSeek (LLM)           │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │                    Auto-Update                            │    │
│  │     GitHub Release → check → download → patch → restart  │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │                    Plugin System                          │    │
│  │     plugins/commands/*.yml → trigger → response           │    │
│  └──────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

---

## เทคโนโลยีที่ใช้

| ส่วน | เทคโนโลยี | เหตุผล |
|---|---|---|
| **ภาษา** | Python 3.10 | รองรับ TTS/AI libraries |
| **GUI** | customtkinter (Tkinter) | ข้ามแพลตฟอร์ม + เบา |
| **TTS** | edge-tts | ฟรี + เสียงดี + หลายภาษา |
| **RVC** | PyTorch + CUDA | Voice conversion (GPU) |
| **Game Overlay** | PySide6 + QtWebEngine | Transparent window |
| **OBS Overlay** | aiohttp + WebSocket | Real-time chat |
| **Translation** | deep-translator + DeepSeek API | Google/DeepL/LLM |
| **Build** | PyInstaller (onedir) | แจกเป็น exe ไม่ต้องลง Python |
| **Auto-update** | GitHub Releases + requests/urllib | 4 layer fallback |
| **Plugin** | YAML config + Python ABC | ปลอดภัย + ยืดหยุ่น |

---

## เวอร์ชั่น

| | Lite | Full |
|---|---|---|
| **ขนาด** | ~900 MB | ~5.7 GB |
| **RVC** | ❌ | ✅ (PyTorch + CUDA) |
| **TTS** | edge-tts (Premwadee) | edge-tts + RVC voices |
| **GPU** | ไม่จำเป็น | NVIDIA + CUDA (หรือ CPU ช้า) |
| **Mixed Voice** | ✅ | ✅ + RVC convert |
| **RAM** | ~4 GB | ~8 GB |

---

## Flow หลัก

### 1. รับแชท → แสดง → อ่าน
```
แพลตฟอร์ม → on_message → buffer → poll (200ms)
  → Live Chat (แสดงข้อความ)
  → Overlay (OBS + Game)
  → TTS Pipeline (อ่านออกเสียง)
  → Event Log (บันทึก)
```

### 2. TTS Pipeline
```
text → filter (NG/Replace) → translate (ถ้าเปิด) → detect language
  → เลือก voice → edge-tts synth → decode MP3
  → RVC convert (ถ้ามี) → play (pygame)
```

### 3. Auto-Update
```
เปิดโปรแกรม → 5 วิ → เช็ค version.json จาก GitHub
  → เทียบเวอร์ชั่น → มีใหม่ → popup
  → กดอัพเดท → ดาวน์โหลด patch zip (9-33 MB)
  → แตกไฟล์ทับ → รีสตาร์ท
```

---

## โครงสร้างไฟล์

```
tts-for-livestream/
├── main.py                    # Entry point + splash + log rotation
├── app_gui.py                 # Main GUI (~11000+ lines)
├── chat_queue.py              # TTS pipeline + Mixed Voice
├── settings.py                # AppSettings dataclass
├── text_filter.py             # NG words + Replace
├── notification_manager.py    # Event notification
├── translator.py              # Google/DeepL/DeepSeek
├── language_detect.py         # Unicode script detection
├── event_log.py               # Event history
├── user_manager.py            # User management dialog
├── updater.py                 # Auto-update (4 layer fallback)
├── splash.py                  # Splash screen
├── build_patch.py             # Release packer
├── plugin_loader.py           # Plugin loader
├── plugin_api.py              # Abstract classes
│
├── chat_twitch.py             # Twitch IRC client
├── chat_youtube.py            # YouTube chat client
├── chat_mylive.py             # MyLive Playwright client
├── chat_tiktok.py             # TikTok client
├── chat_kick.py               # KICK client
│
├── rvc_engine.py              # RVC voice conversion
│
├── overlay_server.py          # OBS overlay HTTP server
├── overlay.html               # OBS overlay web page
├── game_overlay.py            # Game Overlay + Overlay+ manager
├── game_overlay_qt.py         # Qt transparent window
├── game_overlay_server.py     # Game overlay HTTP server
├── game_overlay.html          # Game overlay web page
│
├── tts_lite.spec              # PyInstaller spec (Lite)
├── tts_full.spec              # PyInstaller spec (Full)
│
├── plugins/                   # Plugin directory
│   ├── README.md
│   └── commands/              # Command plugins (YAML)
├── assets/                    # Logo + fonts + icons
├── version.json               # Local version
│
├── FAQ.md                     # คู่มือผู้ใช้
├── PLUGIN_DEV.md              # คู่มือนักพัฒนา plugin
├── ARCHITECTURE.md            # ไฟล์นี้
└── PROJECT_NOTES.md           # Dev notes (ปัญหา + วิธีแก้)
```

---

## ความต้องการของระบบ

| ข้อกำหนด | Lite | Full |
|---|---|---|
| OS | Windows 10/11 x64 | Windows 10/11 x64 |
| RAM | 4 GB | 8 GB |
| GPU | ไม่จำเป็น | NVIDIA + CUDA (หรือ CPU ช้า) |
| Internet | ต้อง (edge-tts + แปล) | ต้อง (edge-tts + แปล) |
| พื้นที่ | ~900 MB | ~6 GB |
