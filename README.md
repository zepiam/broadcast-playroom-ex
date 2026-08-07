# 🎙️ Broadcast Playroom

โปรแกรม TTS สำหรับอ่านแชทสดจาก Twitch / YouTube / MyLive / TikTok / KICK ด้วย edge-tts และ RVC voice conversion

> **สำหรับผู้ใช้ทั่วไป** — ดาวน์โหลดเวอร์ชันล่าสุดได้ที่ https://men9ch.com/broadcast-playroom/

---

## 📦 เวอร์ชัน

| เวอร์ชัน | ขนาด | PyTorch/CUDA | การ์ดจอรองรับ |
|----------|------|-------------|-------------|
| **Lite** | ~900 MB | ไม่มี (ไม่ใช้ RVC) | ทุกเครื่อง |
| **Full** | ~5.7 GB | 2.7.0+cu128 | RTX 20xx ถึง RTX 50xx+ |

> ⚠️ **เลิกรองรับ GTX 10xx (Pascal)** ตั้งแต่ v1.9.8 — เนื่องจากคนสตรีมในยุคนี้ใช้ RTX กันหมดแล้ว ถ้ายังใช้ GTX 10xx ให้ใช้เวอร์ชันเก่า (v1.9.7) หรือเปลี่ยนไปใช้ Lite
> Auto-update ใช้ patch ร่วมกันได้ทั้ง 2 เวอร์ชั่น (โค้ด Python/HTML เหมือนกัน)

---

## ✨ ฟีเจอร์หลัก

### TTS & เสียง
- **edge-tts (Premwadee)** — เสียงหญิงไทย ฟรี ไม่ต้อง GPU
- **RVC voice conversion** — แปลงเสียงเป็น VTuber/อนิเมะ/ผู้ประกาศ (Full only)
- **Mixed Voice** — อ่านหลายภาษาในประโยคเดียว (ไทย+ญี่ปุ่น+ไทย)
- **อ่านชื่อ + ข้อความ** — ปรับ volume/rate ได้
- **ข้ามข้อความยาว** — ตั้ง threshold + เสียงเตือน

### การแปลภาษา
- **Google** (ฟรี) / **DeepL** / **DeepSeek v4-flash** (LLM)
- แปลเป็นไทย → TTS อ่านไทย
- แสดงคำแปลใน Live Chat + Overlay + Game Overlay (realtime)
- บังคับแปลรายบุคคล (Force translate)
- ภาษาที่ไม่รู้จัก (ฮินดี/อาหรับ) → เงียบ ไม่ error

### แพลตฟอร์ม
- **5 แพลตฟอร์ม**: Twitch / YouTube / MyLive / TikTok / KICK
- Default 3 (Twitch/YouTube/MyLive) — เปิดเพิ่มได้ใน Platform Modal (เฟือง sidebar)
- ผู้ชมนับ live / auto-reconnect

### Overlays
- **🎨 Canvas Overlay Composer** — จัดวาง widget บน canvas ขนาด 720p/1080p (drag + resize + z-index)
  - Widget หลายประเภท: Chat / Viewer Count / Clock / Image / Playroom / Webcam / Text / Video
  - ล็อค Ratio ของ widget ได้ (กันบิดเบี้ยวเวลาขยาย)
  - ตั้งค่า widget แยกแต่ละตัว (font / theme / size / position / opacity)
- **Chat Overlay (OBS)** — แสดงแชทใน OBS/Streamlabs (Browser Source)
  - 4 โหมด: Default / Theme / Special (Balloon) / **🎭 Character Talk**
- **Game Overlay** — แชทลอยเหนือเกม (transparent + click-through, Qt)
  - เปิด/ปิดได้จากใน Setting เลย (ไม่ต้องกลับหน้าหลัก)
  - รองรับ Character Talk เช่นกัน
- **🎭 Character Talk** — ตัวละครยืนเรียงด้านล่างจอ + บอลลูนข้อความเหนือหัว
  - ผู้ชมพิมพ์ `{jobchange:ชื่อjob}` เพื่อเลือกตัวละคร (เก็บถาวร)
  - `{jobchange:reset}` เพื่อล้าง job กลับเป็น default
  - ภาพตัวละคร default (`avatar.png`) + เพิ่ม/ลบ job แต่ละตัวได้
  - ตัวละครสุ่มตำแหน่ง (grid-slot) — ไม่ซ้อนกัน กระจายทั่วจอ
  - บอลลูนขยายตามเนื้อหา (shrink-to-fit) + scroll ข้อความยาว + กันล้นขอบจอ
  - ปรับ: ขนาดตัวละคร / ระยะเวลา / จำนวน / ความกว้างกล่อง / สไตล์ชื่อ (stroke/shadow)
  - ใช้ได้ทั้ง OBS Overlay + Game Overlay (ตั้งค่าร่วมกัน)
- **🎵 Now Playing Widget** — แสดงเพลงที่กำลังฟัง (Windows System Media)
  - รองรับ Spotify / YouTube Music (Desktop App) / เบราว์เซอร์ (Chrome/Edge/Firefox)
  - 20+ Theme + 20 ลวดลาย Style (Flat / Metal / Neon / Glass / CRT / Pixel ฯลฯ)
  - แสดง album art + progress bar + scroll ชื่อเพลง + client-side timer (sync แม่นยำ)
- **🎉 Emote Party Widget** — ดัก emote จากทุกแพลตฟอร์ม + animation สนุก ๆ
  - รองรับ Twitch (sub + BTTV + FFZ + 7TV) / YouTube / TikTok / Unicode emoji
  - 4 animation: Float / DVD Bounce / Pop & Drop / Shake-Spin
  - ปรับ: รูปแบบ animation / ระยะเวลา / จำนวนสูงสุด / ขนาด emote
- **👥 Viewer Count Widget** — แสดงยอดคนดูแยกตามแพลตฟอร์ม
  - โหมด: รวม / รายแพลตฟอร์ม / ทั้งสอง
  - เรียงแนวนอนหรือแนวตั้งได้ + 18 Theme
- **🎮 Playroom Widget** — เล่น clip เมื่อผู้ชมพิมพ์ trigger
  - คัดแยก trigger ได้ต่อ widget (กล่องนี้รับ #fortune, อีกกล่องรับ #random)
  - เครื่องมือ **Color Key** ตัดสีฉากหลัง (chroma key) + Eyedropper + Similarity + Smoothness
- **🎬 Video Widget** — วิดีโอ loop + รองรับ Color Key ตัดสีฉากหลัง
- **🔌 OBS WebSocket** — เชื่อมต่อ OBS อัตโนมัติ → refresh browser source ทันทีหากเปิด OBS ก่อนโปรแกรม
- **Viewer Overlay** — แสดงยอดคนดูบนจอ (overlay อิสระ — ไม่ต้องเปิด Game Overlay)
  - โหมดรวม: `👥 1,234` (ยอดรวมทุก platform)
  - โหมดแยก: `[Twitch icon] 500 [YT icon] 300` (ใช้ platform icon จริง)
  - ปรับขนาด icon + font + stroke + shadow + color
  - เลือกจัดวาง: ชิดซ้าย/กลาง/ชิดขวา + ตำแหน่ง 4 มุม
- **Overlay+** — custom URL overlay สูงสุด 3 อัน (Streamlabs/StreamElements/alert)
  - ปรับความโปร่งใสแยกแต่ละอัน
- **ปุ่ม Overlay รวม** — กดปุ่ม 🔲 เดียว → เปิด/ปิดทั้ง Game + Viewer Overlay
  - ▼ Dropdown: ซ่อนกรอบ / Game Overlay Setting / Viewer Overlay Setting
  - Hotkey ซ่อนกรอบร่วม (Ctrl+Shift+H)
- **Theme 54 แบบ** — Neon/Glass/Cyberpunk ฯลฯ + Pip-Boy (Fallout) + สไตล์ผู้หญิง (Sakura/Princess/Galaxy Girl ฯลฯ)
- **Playroom** — มินิเกมวิดีโอ (trigger ด้วย #)

### Event System
- รองรับ: sub/bits/raid/superchat/gift/follow/share/like/join/redeem
- เสียงแจ้งเตือน + TTS announcement (toggle ได้)
- Event List (ใหม่→เก่า)

### การจัดการ
- **NG-Replace** — คำต้องห้าม + คำแทนที่ (2 คอลัมน์ + Edit + TTS preview)
- **User Manager** — เปลี่ยนชื่อ / Block / Force translate / TTS rename + Refresh
- **Channel Points** (Twitch text-prompt rewards)
- **NG words** — 2 โหมด: hide / show_no_tts

### อำนวยความสะดวก
- **Auto-update** — ตรวจ + ดาวน์โหลด + ติดตั้งอัตโนมัติ (4 layer fallback)
- **Settings auto-save** — เปลี่ยนค่าแล้วเซฟทันที (debounce 500ms)
- **Splash screen** — แยกภาพ LITE/FULL + Pixel Block loading bar + พื้นหลังโปร่งใส
- **prefix อัตโนมัติ** — `!` สำหรับโค้ดลับ, `#` สำหรับ Playroom
- **Log rotation** — เก็บ 10 ครั้งล่าสุด + crash.log
- **Plugin System** — command plugin (config-only YAML)
- **Viewer Commands** — ผู้ชมคุม TTS ผ่านแชท (`[x2]` `[p1]` `[v50]`)

---

## 🔄 Auto-Update

โปรแกรมจะตรวจอัพเดทอัตโนมัติเมื่อเปิดใช้งาน (5 วินาทีหลังเปิด)

- **Patch update** — ดาวน์โหลดและติดตั้งอัตโนมัติ (~9-33 MB)
- **Major update** — แจ้งให้ดาวน์โหลดเวอร์ชันใหม่ทั้งหมด

### ⚠️ Windows Defender / Antivirus
PyInstaller exe อาจถูก AV แจ้งเตือน (false positive) — เพิ่ม Exception:
1. Windows Security → Virus & threat protection → Manage settings
2. Add or remove exclusions → Add an exclusion → Folder
3. เลือกโฟลเดอร์ Broadcast Playroom

ดูเพิ่มเติม: [FAQ.md](FAQ.md)

---

## 📋 Release Assets

ไฟล์ที่อัพโหลดไว้ใน [Releases](https://github.com/zepiam/broadcast-playroom/releases) tag `latest`:

| ไฟล์ | หน้าที่ |
|------|---------|
| `version.json` | ⚠️ **ต้องมี lite/full block** (ไม่ใช่แค่ version+changelog) — updater อ่านไฟล์นี้ |
| `remote_version.json` | เหมือน version.json (สำรอง) |
| `patch_lite.zip` | Patch สำหรับ Lite (delta update) |
| `patch_full.zip` | Patch สำหรับ Full (delta update) |

> ⚠️ **สำคัญ**: `version.json` บน GitHub ต้องมีโครงสร้าง `{version, changelog, lite: {type, url, size}, full: {type, url, size}}` — ถ้าขาด lite/full block updater จะ fallback เป็น major (ดาวน์โหลดใหม่ทั้งโปรแกรม) ทั้งที่ควรเป็น patch

---

## 📝 Changelog ล่าสุด

### v1.12.0
- **🎵 Now Playing Widget** — แสดงเพลงที่กำลังฟัง (Spotify / YouTube Music / เบราว์เซอร์)
  - 20+ Theme + 20 ลวดลาย Style + album art + progress bar + client-side timer
- **🎉 Emote Party Widget** — ดัก emote จากทุกแพลตฟอร์ม (Twitch/YouTube/TikTok/emoji)
  - 4 animation: Float / DVD Bounce / Pop & Drop / Shake-Spin
- **🎨 Color Key (Chroma Key)** — ตัดสีฉากหลังบน Playroom + Video widget
  - Eyedropper คลิกเก็บสีจากวิดีโอ + Similarity + Smoothness
- **👥 Viewer Count Widget** — แยกยอดคนดูตามแพลตฟอร์ม + เรียงแนวตั้งได้
- **🎮 Playroom Widget** — คัดแยก trigger ได้ต่อ widget
- **🔌 OBS WebSocket** — refresh overlay อัตโนมัติเมื่อเปิด OBS ก่อนโปรแกรม
- **🔲 Ratio Lock** — ล็อคอัตราส่วน widget ไม่ให้ขยับผิดไซส์
- **🔧 แก้บั๊ก MyLive** — เชื่อมต่อได้แม้ในห้อง Live ยังไม่มีแชท
- **🔧 แก้ reconnect** — ไม่ค้าง UI + ไม่ loop + ไม่ error ตอนกดหยุดเอง
- **⌨️ Ctrl+C/V/A/X** — ใช้ได้ทุกภาษา (ไทย/อังกฤษ)
- **🔧 ปรับ Chat Widget / System Message / TTS queue**
- **🗑️ ลบ RVC Model ที่ลิ้งค์ใช้ไม่ได้**

### v1.8.20
- **🎭 Character Talk** — ตัวละครยืนเรียงด้านล่างจอ + บอลลูนข้อความเหนือหัว (overlay mode ใหม่)
  - ผู้ชมพิมพ์ `{jobchange:ชื่อjob}` เพื่อเลือกตัวละคร (เก็บถาวรต่อผู้ชม)
  - ภาพ default (`avatar.png` ที่มากับแอป) + browse ภาพเองได้ + เพิ่ม/ลบ job
  - ตัวละครสุ่มตำแหน่งแบบ grid-slot — ไม่ซ้อนกัน กระจายทั่วจอ
  - บอลลูน shrink-to-fit + scroll ข้อความยาว + กันล้นขอบจอ (หางชี้ตัวละคร)
  - ปรับความกว้างกล่อง (400-800px) + สไตล์ชื่อ (size/stroke/shadow)
  - ใช้ได้ทั้ง OBS Overlay + Game Overlay
- **🔧 แก้ Qt WebEngine cache** — incognito profile + cache-bust (กัน HTML เวอร์ชันเก่า)

### v1.8.19
- **👥 Viewer Overlay** — overlay อิสระแสดงยอดคนดู (แยก server ของตัวเอง)
  - โหมดรวม / แยก platform (ใช้ platform icon จริง)
  - ปรับขนาด icon + font + stroke + shadow + color
  - จัดวาง: ชิดซ้าย/กลาง/ชิดขวา + 4 มุม + จดจำตำแหน่ง
- **🎨 Splash ใหม่** — แยกภาพ LITE/FULL + Pixel Block loading bar + โปร่งใส
- **🔲 ปุ่ม Overlay รวม** — กดปุ่มเดียวเปิด/ปิดทั้ง Game + Viewer + dropdown menu
- **⌨️ Hotkey ร่วม** — Ctrl+Shift+H ซ่อนกรอบทั้งคู่
- **🔧 Job Object** — subprocess ตายอัตโนมัติเมื่อ parent ปิด/crash

### v1.8.17
- **🎮 Viewer Commands** — ผู้ชมคุม TTS ผ่านแชท (`[x2]` `[p1]` `[v50]`)
- **Voice Downloader** — 85 curated models + popup picker + status indicator

### v1.8.9
- **Setting เปิดเร็วขึ้น** — lazy build + preload
- **Theme ใหม่ 30+ แบบ** — Pip-Boy + สไตล์ผู้หญิง + กรอบลูกเล่น
- **Game Overlay toggle ใน Setting**

---

## 🛠️ สำหรับนักพัฒนา (Development)

### โครงสร้างโปรเจค

```
tts-for-livestream/
├── main.py                 # Entry point + splash + log rotation
├── app_gui.py              # GUI (~11000+ lines) — Main app + SettingsDialog
├── chat_queue.py           # TTS pipeline + Mixed Voice + translation
├── settings.py             # AppSettings dataclass + load/save
├── updater.py              # Auto-update (4 layer fallback)
├── build_patch.py          # สร้าง patch/full zip สำหรับ release
├── tts_lite.spec           # PyInstaller spec (Lite)
├── tts_full.spec           # PyInstaller spec (Full — torch 2.7.0+cu128, RTX 20xx → 50xx+)
├── plugin_loader.py        # Plugin loader (command config-only)
├── plugin_api.py           # Abstract classes (TTSEngine, PlatformClient, CommandHandler)
├── rvc_engine.py           # RVC voice conversion + HuBERT cache
├── chat_twitch.py          # Twitch IRC client
├── chat_youtube.py         # YouTube chat client
├── chat_mylive.py          # MyLive Playwright client
├── chat_tiktok.py          # TikTok client
├── chat_kick.py            # KICK client
├── overlay_server.py       # OBS overlay HTTP server
├── overlay.html            # OBS overlay web page
├── game_overlay.py         # Game Overlay + Overlay+ + Viewer Overlay manager
├── game_overlay_qt.py      # Qt transparent window subprocess (game/overlay+/viewer)
├── game_overlay.html       # Game overlay web page
├── viewer_overlay.html     # Viewer overlay web page (ยอดคนดู)
├── viewer_overlay_server.py # Viewer overlay HTTP server (port 8790-8800)
├── splash.py               # Splash screen (Pixel Block loading bar)
├── assets/                 # icon + fonts + logo
├── plugins/                # Plugin directory (commands/*.yml)
├── version.json            # เลขเวอร์ชัน local
├── web/                    # Documentation website (Node.js + Express)
└── release/                # output ของ build_patch.py (ไม่ commit)
```

### เอกสารสำหรับนักพัฒนา

| ไฟล์ | เนื้อหา |
|------|--------|
| [PLATFORM_DEV.md](PLATFORM_DEV.md) | **คู่มือเพิ่มแพลตฟอร์มใหม่** (chat/emote/event) |
| [AUDIO_DEV.md](AUDIO_DEV.md) | **คู่มือปรับแต่งเสียง** (TTS/RVC/Mixed Voice/Translation) |
| [PROJECT_NOTES.md](PROJECT_NOTES.md) | 56 บัค + วิธีแก้ + สถาปัตยกรรมลึก |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Setup + code style + build + debug + gotchas |
| [PLUGIN_DEV.md](PLUGIN_DEV.md) | API reference สำหรับ plugin (Command/TTSEngine/Platform) |
| [ARCHITECTURE.md](ARCHITECTURE.md) | ภาพรวมระบบ + flow + โครงสร้างไฟล์ |
| [CHANGELOG.md](CHANGELOG.md) | ประวัติเวอร์ชั่นทั้งหมด |
| [FAQ.md](FAQ.md) | ปัญหาที่พบ + วิธีแก้ (ผู้ใช้) |

---

## 🗺️ Roadmap — สิ่งที่วางไว้ (ทำเมื่อสั่ง)

> 💡 เก็บไว้เป็นแผน ไม่ได้ทำทันที — เมื่อถึงเวลาที่มี requirement ใหม่ค่อยทำ

### 🔄 PySide6 Migration (v2.0.0 — เปลี่ยน UI Framework)

> 🎯 **เป้าหมาย**: แก้ปัญหากระพริบ/กระตุก ของ customtkinter โดยย้ายไปใช้ PySide6 (Qt for Python)

#### ทำไมต้องเปลี่ยน?

| ปัญหา | customtkinter (ปัจจุบัน) | PySide6/Qt |
|---|---|---|
| Restore จาก minimize | กระพริบดำทั้งจอ | ลื่น ไม่กระพริบ |
| สลับ tab / เปิด Settings | มี flash ขาว/ดำ | สลับลื่น |
| Resize window | กระตุก ภาพฉีก | ลื่น 60fps |
| Scroll chat เยอะๆ | กระตุกบ้าง | ลื่น |
| Font rendering | มักเบลอ | คมชัด |
| Animation | จำกัด (Tk canvas) | transition/fade/slide ครบ |

#### สิ่งที่เปลี่ยนไป

**ใช้ได้เลย (logic เดิม ไม่ต้องแก้):**
- ✅ edge-tts (Python library)
- ✅ RVC voice conversion (Python + PyTorch)
- ✅ Chat connectors ทั้ง 5 แพลตฟอร์ม (Twitch/YouTube/MyLive/TikTok/KICK)
- ✅ Translation (Google/DeepL/DeepSeek)
- ✅ NG-Replace / User Manager / Settings logic
- ✅ OBS WebSocket auto-refresh
- ✅ Composer overlay server (aiohttp — แยกจาก UI)
- ✅ Playwright (MyLive)
- ✅ Plugin system
- ✅ Auto-update system

**ต้องเขียนใหม่ (UI เท่านั้น):**
- 🔄 หน้าหลัก (chat feed, toolbar, status bar)
- 🔄 Settings window
- 🔄 Popout chat window
- 🔄 Voice Downloader UI
- 🔄 Splash screen
- 🔄 Advanced Settings (hidden tab)

**ได้ประโยชน์เพิ่ม:**
- ⬆️ Game Overlay รวมเข้าโปรแกรมหลักได้ (ตอนนี้เป็น subprocess แยก เพราะใช้ PySide6 WebEngine)
- ⬆️ Native Windows rendering (คมชัด สวย ลื่น)
- ⬆️ รองรับ high-DPI ได้ดีกว่า
- ⬆️ Animation/transition ลื่น

#### ผลกระทบต่อผู้ใช้

| เหตุการณ์ | ผู้ใช้ต้องทำอะไร | ขนาด |
|---|---|---|
| อัปเดตเป็น v2.0.0 ครั้งแรก | **โหลดใหม่ทั้งโปรแกรม** (เพราะเปลี่ยน dependency) | ~1GB (Lite) / ~6GB (Full) |
| หลัง v2.0.0 แล้ว อัปเดต logic | patch อัตโนมัติเหมือนเดิม | 10-35MB |

> ⚠️ **v2.0.0 = breaking change** — ผู้ใช้ต้องโหลดใหม่ทั้งโปรแกรมครั้งเดียว หลังจากนั้นใช้ patch update ได้ปกติ

#### ขั้นตอนการทำ (สัปดาห์ละขั้นตอน)

1. **สัปดาห์ที่ 1-2**: เขียน UI หลัก (chat feed + toolbar + status bar) บน PySide6
2. **สัปดาห์ที่ 2-3**: Settings window + Popout + Voice Downloader + Splash
3. **สัปดาห์ที่ 3**: รวม Game Overlay เข้าโปรแกรมหลัก + ทดสอบ
4. **สัปดาห์ที่ 4**: Build + debug + release v2.0.0

#### ไฟล์ที่จะเพิ่ม/เปลี่ยน

```
tts-for-livestream/
├── main.py                 # เปลี่ยน: ใช้ QApplication แทน CTk
├── app_gui.py              # เขียนใหม่: QMainWindow + QWidget (PySide6)
├── ui/                     # ✨ ใหม่: UI components แยกไฟล์
│   ├── main_window.py      # หน้าหลัก
│   ├── chat_panel.py       # chat feed
│   ├── settings_dialog.py  # Settings
│   ├── popout_window.py    # Popout chat
│   ├── voice_downloader.py # Voice Downloader
│   └── splash.py           # Splash screen
├── game_overlay_qt.py      # ลบ: รวมเข้า app_gui.py แล้ว
├── tts_lite.spec           # เปลี่ยน: PySide6 แทน customtkinter
├── tts_full.spec           # เปลี่ยน: PySide6 แทน customtkinter
└── (ไฟล์อื่นๆ เดิมหมด — logic ไม่เปลี่ยน)
```

### 🔌 Plugin System (เชื่อม ABC ที่ยังเป็น stub)

| ลำดับ | ฟีเจอร์ | สถานะปัจจุบัน | สิ่งที่ต้องทำ |
|---|---|---|---|
| 1 | **Command Plugin (Python)** | `plugin_loader.py` สร้างแล้ว แต่ไม่ได้ import ใน `app_gui.py`/`chat_queue.py` | เชื่อม `get_plugin_loader().check_command(msg)` เข้า on_message pipeline |
| 2 | **TTSEngine Plugin** | ABC มีใน `plugin_api.py` แต่ `tts_engine.py` ไม่ได้ subclass | ทำให้ edge-tts เป็น subclass + รองรับ TTS อื่น (Google Cloud, Azure, Coqui) |
| 3 | **PlatformClient Plugin** | ABC มี แต่ client จริงไม่ได้ subclass (duck-typed) | ทำให้ client จริง inherit + รองรับ plugin loading |
| 4 | **Event Hooks** | ไม่มี | เพิ่มระบบให้ plugin รับ event (sub/bits/raid) ผ่าน callback |

### 🎨 ฟีเจอร์ที่ขยายได้ (คนอื่นต่อยอด)

| ฟีเจอร์ | วิธีเพิ่ม | อ้างอิง |
|---|---|---|
| **Command Plugin (YAML)** | สร้าง `.yml` ใน `plugins/commands/` | [PLUGIN_DEV.md](PLUGIN_DEV.md) |
| **RVC Voice Model** | วาง `.pth` ใน `rvc_models/` | [AUDIO_DEV.md](AUDIO_DEV.md) |
| **แพลตฟอร์มใหม่** | สร้าง `chat_xxx.py` + register | [PLATFORM_DEV.md](PLATFORM_DEV.md) |
| **Translation Provider** | เพิ่มใน `translator.py` | [AUDIO_DEV.md](AUDIO_DEV.md) |
| **Overlay Theme** | แก้ CSS ใน `overlay.html` | — |
| **ภาษาใหม่ (Mixed Voice)** | เพิ่มใน `VOICE_BY_LANG` | [AUDIO_DEV.md](AUDIO_DEV.md) |

### 📝 TODO อื่นๆ

- [ ] Settings > Plugins tab (ดู + เปิด/ปิด plugin)
- [ ] PyYAML ใน PyInstaller spec (สำหรับ command plugin)
- [ ] Web Wiki: User Guide (สำหรับผู้ใช้ทั่วไป ไม่ใช่ dev)
- [ ] Web Wiki: Settings Reference (อธิบายทุก setting)
- [ ] Web Wiki: Overlay/RVC/Translation Setup Guide

---

### Build

```bash
# สำคัญ: ปิดโปรแกรมก่อน build เสมอ (กัน file lock)
# สำคัญ: numpy < 2 (เพื่อ torch compatibility)

# ── Lite (ไม่ต้องใช้ torch) ──
pip install "numpy<2"
python -m PyInstaller tts_lite.spec --noconfirm   # Lite

# ── Full (RTX 20xx → 50xx+ — ใช้ torch 2.7.0+cu128) ──
pip install torch==2.7.0 torchaudio==2.7.0 --index-url https://download.pytorch.org/whl/cu128
python -m PyInstaller tts_full.spec --noconfirm   # Full
# (dev) คืน torch 2.2.2 เพื่อเทสโค้ดเก่าที่ยังอ้างอยู่ (ถ้าจำเป็น):
pip install torch==2.2.2 torchaudio==2.2.2 --index-url https://download.pytorch.org/whl/cu121
```

#### 🚨 จดบทเรียนราคาแพง — ต้อง rebuild exe ก่อน build patch เสมอ!

**บั๊คที่เกิดซ้ำ 2 ครั้งแล้ว (v1.8.x + v1.9.x):**
1. แก้โค้ดใน source (เช่น `composer.html`)
2. รัน `build_patch.py` โดย **ไม่ rebuild exe ก่อน**
3. `build_patch.py` อ่านจาก `dist/_internal/` ที่ยังเป็นของเก่า → patch ส่งไฟล์เก่าไป
4. User อัปเดตแล้วไม่เห็นฟีเจอร์ใหม่

**อาการอีกแบบ:** version.json ใน patch ไม่ตรง → updater detect อัปเดตซ้ำๆ ไม่รู้จบ (loop)

**วิธีป้องกัน (ทำทุกครั้งก่อน release):**
```bash
# 1. REBUILD EXE ทั้ง 2 ก่อนเสมอ (แม้แก้แค่ HTML)
python -m PyInstaller tts_lite.spec --noconfirm
# Full (ต้องลง torch 2.7.0+cu128 ก่อน):
pip install torch==2.7.0 torchaudio==2.7.0 --index-url https://download.pytorch.org/whl/cu128
python -m PyInstaller tts_full.spec --noconfirm
pip install torch==2.2.2 torchaudio==2.2.2 --index-url https://download.pytorch.org/whl/cu121

# 2. sync version.json ลง dist/_internal/ (build_patch.py version ทำให้)
python build_patch.py patch lite
python build_patch.py patch full
python build_patch.py version

# 3. ตรวจสอบว่า patch มีไฟล์ใหม่จริง
python -c "
import zipfile
z = zipfile.ZipFile('release/patch_lite.zip')
data = z.read('_internal/composer.html').decode()
print('has new feature:', 'NEW_FEATURE_KEYWORD' in data)
"
```

> ⚠️ **ถ้าไม่ rebuild exe → patch จะส่งไฟล์เก่า → user ไม่ได้ฟีเจอร์ใหม่ + อาจทำให้ version ไม่ตรง → loop update**

### สร้างไฟล์ Release + อัพโหลด

```bash
# ⚠️ สำคัญมาก: ทำตามลำดับนี้เท่านั้น — ผิดลำดับ = updater พัง

# 1. แก้ไขโค้ด + syntax check
python -m py_compile *.py

# 2. Bump version.json ก่อน (version + changelog + lite/full blocks)
#    ⚠️ version.json ต้องมี lite/full blocks ครบ (ไม่ใช่แค่ version+changelog)
#    build_patch.py version จะสร้างให้อัตโนมัติจาก patch sizes

# 3. Build exe (PyInstaller) — ต้องปิดโปรแกรมก่อน!
python -m PyInstaller tts_lite.spec --noconfirm
python -m PyInstaller tts_full.spec --noconfirm

# 4. สร้าง patch + version files
#    ⚠️ ต้องรันหลัง build exe เสมอ (build_patch.py sync version.json → dist/_internal/)
python build_patch.py patch lite
python build_patch.py patch full
python build_patch.py version    # สร้าง remote_version.json + version.json (เหมือนกัน)

# 5. ตรวจสอบ patch zip มี version ที่ถูกต้อง
python -c "
import zipfile, json
for f in ['release/patch_lite.zip', 'release/patch_full.zip']:
    z = zipfile.ZipFile(f)
    data = json.loads(z.read('_internal/version.json'))
    print(f'{f}: version={data.get(\"version\")}, has blocks={\"lite\" in data}')
"
# ต้องเห็น version ใหม่ + has blocks=True ทั้งคู่

# 6. อัพโหลดขึ้น GitHub
gh release upload latest release/patch_lite.zip release/patch_full.zip \
  release/remote_version.json version.json --clobber
gh release edit latest --title "Broadcast Playroom vX.Y.Z"

# 7. ⚠️ ตรวจสอบ version.json บน GitHub มี lite/full blocks จริง
gh release download latest --pattern "version.json" --dir /tmp/check --clobber
python -c "import json; d=json.load(open('/tmp/check/version.json')); print('lite:', d.get('lite',{}).get('type')); print('full:', d.get('full',{}).get('type'))"
# ต้องเห็น lite: patch / full: patch (ไม่ใช่ major)
```

### Dependencies สำคัญ
- `numpy < 2` (torch compatibility — ใช้ได้กับทั้ง torch 2.2.2 และ 2.7.0)
- `collect_submodules('requests')` + `('urllib3')` ใน spec (ต้องมี! — updater ใช้)
- `certifi` (SSL certificates สำหรับ HTTPS)

### Documentation Website
```bash
cd web
npm install
node server.js  # http://localhost:3000
```
หลังบ้าน: `/admin/login` (เปลี่ยน password ใน server.js)

---

## 📋 Character Talk — บันทึกสถานการณ์ปัจจุบัน (สำหรับ AI รุ่นต่อไป)

> ส่วนนี้เขียนขึ้นเพื่อส่งต่อบริบทให้ AI รุ่นต่อไปเข้าใจสถานการณ์ปัจจุบันของ feature Character Talk
> วันที่อัปเดต: 2026-08-03

### Feature ที่ทำเสร็จแล้ว
- **🎭 Character Talk** — overlay mode ใหม่ (ตัวที่ 4 ใน OBS Overlay + Game Overlay)
  - ตัวละครยืนเรียงด้านล่างจอ + บอลลูนข้อความเหนือหัว
  - ผู้ชมพิมพ์ `{jobchange:ชื่อjob}` เพื่อเลือกตัวละคร (เก็บถาวรใน `settings.user_jobs`)
  - `{jobchange:reset}` ล้าง job กลับเป็น default
  - ภาพ default = `avatar.png` ที่ bundle มากับแอป (browse เปลี่ยนเองได้)
  - ตัวละครสุ่มตำแหน่ง (grid-slot algorithm) — ไม่ซ้อนกัน
  - บอลลูน shrink-to-fit + scroll ข้อความยาว (เกิน 3 บรรทัด) + กันล้นขอบจอ
  - ปรับความกว้างกล่อง (400-800px) + สไตล์ชื่อ (size/stroke/shadow)

### ปัญหาที่เจอ + วิธีแก้

#### 1. ตัวละครซ้อนกัน (หลายรอบ)
- **สาเหตุที่ 1:** `randomizeCharPosition` ใช้ `el.offsetWidth` วัดความกว้าง แต่ offsetWidth รวม bubble (500px+) → charW ใหญ่เกิน → มีแค่ 1 ช่อง → ทุกตัวอยู่ที่เดียวกัน
  - **แก้:** ใช้ค่าจาก config ล้วน — `charW = Math.max(60, Math.round(charH * 0.7))`
- **สาเหตุที่ 2:** สูตรคำนวณ `occupied` ใน grid-slot ผิด — `Math.abs(ul - slotCenter + charW / 2)` มี `+ charW/2` ที่ทำให้คำนวณระยะผิด → หาว่า slot ว่างทั้งที่ไม่ว่าง
  - **แก้:** `Math.abs(ul + charW / 2 - slotCenter) < slotW / 2`
- **สาเหตุที่ 3 (กลับมาซ้ำ):** Browser cache HTML เก่า → ใช้ logic เก่าที่มี bug
  - **แก้:** เพิ่ม `?v={timestamp}` ที่ URL ที่โปรแกรมสร้างให้ (open + copy) → URL ต่างกันทุกครั้ง → browser โหลดใหม่

#### 2. Game Overlay เปิดไม่ได้ (crash)
- **สาเหตุ:** สร้าง `QWebEngineProfile` **ก่อน QApplication** → Qt crash (ต้องการ QApplication ก่อนเสมอ)
  - **แก้:** ย้าย incognito profile ไปหลัง QApplication
- **สาเหตุที่ 2:** ส่ง profile เป็น kwarg → PySide6 6.11 ต้องการ positional arg
  - **แก้:** ส่งเป็น positional arg ตัวที่ 2

#### 3. OBS Overlay Character Talk setting แสดง Theme content ตอนเปิดครั้งแรก
- **สาเหตุ:** `_render_ov_character_jobs` method ถูกวางผิดคลาส — อยู่ใน `GameOverlaySettingsDialog` แทน `SettingsDialog` → AttributeError → build หยุด → holder ไม่ถูก grid
  - **แก้:** ย้าย method ไป SettingsDialog

#### 4. ภาพตัวละครไม่ replace เวลาอัพโหลดใหม่
- **สาเหตุ:** Browser cache ภาพ (`Cache-Control: max-age=60`) + URL `/character/{job}` เดิม
  - **แก้:** `Cache-Control: no-cache` + เพิ่ม `?t={timestamp}` ที่ img.src

#### 5. ข้อความพอดี 3 บรรทัดก็ scroll
- **สาเหตุ:** Logic เช็ค `fullH > visibleH + 2` (เผื่อแค่ 2px) → sub-pixel rounding trigger scroll
  - **แก้:** เพิ่ม threshold เป็น `fullH > visibleH + lineHeight` (เผื่อ 1 บรรทัด)

### สถานะปัจจุบัน (ที่ AI ใหม่ต้องรู้)
- **โค้ดเสร็จหมดแล้ว** — Character Talk ทำงานครบทุกส่วน
- **ยังไม่ได้ build/release** — Meng ทดสอบจาก `run.bat` (source) ตลอด
- **ปัญหาสุดท้ายที่อาจเจอ:** Browser cache HTML เก่า (OBS Browser Source โดยเฉพาะ) — แก้ด้วย `?v={timestamp}` ใน URL แล้ว แต่ถ้ายังเจอ ให้ลบ Browser Source เดิมใน OBS แล้วเพิ่มใหม่ด้วย URL ใหม่
- **เมื่อพร้อม build:** bump version → 1.8.20, sync version.json ลง `_internal/`, build LITE + FULL, push GitHub

### ไฟล์ที่แก้ (สำหรับ AI ใหม่ reference)
- `settings.py` — fields: `user_jobs`, `character_jobs`, `character_default_image`, `character_*` settings + `resolve_character_default_image()` helper
- `app_gui.py` — parse `{jobchange:xxx}` in `on_message`, Character Talk holder UI (OBS + Game), `_render_character_jobs` + `_render_ov_character_jobs`
- `overlay_server.py` + `game_overlay_server.py` — `/character/{job}` endpoint + character config in `_build_config`
- `overlay.html` + `game_overlay.html` — character mode CSS + JS (`addCharacterMessage`, `randomizeCharPosition`, `positionCharBubble`, `updateCharBubble`)
- `game_overlay_qt.py` — incognito profile + cache-bust URL + javaScriptConsoleMessage
- `tts_lite.spec` + `tts_full.spec` — bundle `avatar.png`
- `build_patch.py` — เพิ่ม `avatar.png` ใน PATCH_PATTERNS

---

## 📝 License

Private project — สงวนลิขสิทธิ์
