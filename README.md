# 🎙️ Broadcast Playroom 2

โปรแกรมรวบรวมแชทสดและอ่านแชทด้วย AI จาก 5 แพลตฟอร์ม — Twitch / YouTube / MyLive / TikTok / KICK

> **เวอร์ชั่นปัจจุบัน**: v2.4.2 (PySide6)
> **เวอร์ชั่นก่อนหน้า**: v1.x (CustomTkinter / Tkinter — Python)
> **เว็บไซต์**: https://men9ch.com/broadcast-playroom/

---

## 📊 สรุปการเปลี่ยนแปลงจาก v1 → v2

### ภาษา / Framework
| | v1 (เก่า) | v2 (ปัจจุบัน) |
|---|---|---|
| **UI Framework** | CustomTkinter (Tkinter) | **PySide6 (Qt for Python)** |
| **ภาษา** | Python 3.10 | Python 3.10 (เหมือนเดิม) |
| **Rendering** | Tk canvas (CPU) | Qt native (GPU accelerated) |
| **Thread-safety** | `self.after(0, fn)` | **Qt Signals** + QThread |
| **Layout** | pack/grid (Tk) | QHBoxLayout/QVBoxLayout/QSplitter |
| **Settings UI** | Tabs (CTkTabview) | **Sidebar layout** (QListWidget — 13 sections) |

### ฟีเจอร์ใหม่ใน v2 (ที่ v1 ไม่มี)
- ✅ **ระบบ Supporters** — ผู้สนับสนุนส่งหลักฐานผ่านเว็บ → admin approve ผ่าน Discord → แสดงในโปรแกรม
- ✅ **Auto-Update** — อัพเดทอัตโนมัติ (patch download + restart) ไม่ต้องโหลดใหม่
- ✅ **โค้ดลับ** — viewer พิมพ์ !code → เล่นเสียง (มีหน้าตั้งค่า + Preview/Stop)
- ✅ **OmniVoice** — TTS offline (Zero-shot, 600+ ภาษา) นอกจาก Azure
- ✅ **Lite / Full** — แยกเวอร์ชั่น Lite (Edge-TTS only, ~1GB) และ Full (OmniVoice + RVC, ~7GB)
- ✅ **Portable Data** — ข้อมูลเก็บใน `data/` ข้าง exe (ไม่ depend home dir)
- ✅ **Portable exe** — PyInstaller รองรับทั้ง Lite และ Full build

### สิ่งที่ใช้ต่อเนื่องจาก v1
- Logic ทั้งหมด (TTS / RVC / chat / translation / overlay / composer / playroom)
- chat_twitch.py, chat_youtube.py, chat_mylive.py, chat_tiktok.py, chat_kick.py
- chat_queue.py, settings.py, rvc_engine.py, translator.py
- text_filter.py, message_history.py, event_log.py, donate_tracker.py

---

## 🎮 ฟีเจอร์ทั้งหมด (v2.2.0)

### แพลตฟอร์ม
- รองรับ 5 แพลตฟอร์ม: Twitch, YouTube, MyLive, TikTok, KICK
- เชื่อม/ตัดการเชื่อมต่อแยกต่อแพลตฟอร์ม
- ปรับระดับเสียง TTS แยกต่อแพลตฟอร์ม (volume slider)
- เปิด/ปิดการแสดงแพลตฟอร์มในหน้าหลัก (sidebar + topbar sync ทันที)
- Auto-reconnect

### TTS (Text to Speech)
- **Azure (Edge-TTS)** — ออนไลน์ เสียงชัดแม่นยำ (Neural Voice)
- **OmniVoice** — ออฟไลน์ Zero-shot TTS (Full version เท่านั้น)
- **RVC Voice Conversion** — แปลงเสียงด้วย AI (Full version เท่านั้น)
- ปรับ pitch / speed / volume
- รองรับ viewer commands ([x2] / [p1] / [v50])

### โค้ดลับ (Secret Code)
- viewer พิมพ์ !code ในแชท → ตัดโค้ดออก → TTS อ่านส่วนที่เหลือ → เล่นเสียง
- หน้าตั้งค่าใน Settings: เพิ่ม/แก้/ลบ โค้ด + เลือกไฟล์เสียง
- Preview/Stop toggle — ทดลองฟังตาม volume ที่ตั้ง
- จำกัดการเล่นต่อ user/วัน

### ระบบ Supporters (ผู้สนับสนุน)
- ผู้สนับสนุนส่งหลักฐานผ่านเว็บ (ธนาคาร / True Money)
- Admin รับแจ้งเตือน Discord → approve/reject/ban
- แสดงรายชื่อในโปรแกรน (ตาราง + โลโก้แพลตฟอร์ม clickable + pagination)
- ระบบแบนเครื่อง (machine ID) กันส่งข้อมูลเท็จ

### Auto-Update
- เช็คอัพเดทอัตโนมัติ 5 วินาทีหลังเปิดโปรแกรม
- ปุ่ม "New Update" แดงกระพริบขวาสุด topbar (pulse animation)
- กดปุ่ม → ดาวน์โหลด patch (11-63 MB) → restart อัตโนมัติ
- 4-layer SSL fallback (รองรับเครื่องที่มี SSL/antivirus ปัญหา)
- กัน loop: เช็ค version หลังอัพเดท

### Overlay & Composer
- Composer (Canvas Overlay) — แก้ไข overlay แบบ drag-drop (port 8808)
- Overlay+ — custom URL overlays (Streamlabs / StreamElements)
- Game Overlay — overlay ลอยเหนือเกม
- OBS WebSocket auto-refresh — รีเฟรช browser source อัตโนมัติ

### การแปลภาษา
- โหมด: ปิด / อ่านทุกภาษา (multilang) / แปลอัตโนมัติ (translate)
- รองรับ Google Translate + หลายภาษา

### Playroom
- ตัวแสดงความคิดเห็นแบบ widget (ลากวางบนหน้าเว็บ)
- Trigger system (#code → เล่น clip)

### อื่นๆ
- NG Words — กรองคำต้องห้าม
- Replace — แทนที่คำก่อน TTS อ่าน
- Blocklist & Spam — บล็อกผู้ใช้ + ป้องกันสแปม
- User Manager — ดูสถิติ + ประวัติ + แบน/เปลี่ยนชื่อ
- Now Playing — แสดงเพลงที่กำลังเล่น
- Portable data — ข้อมูลเก็บใน `data/` ข้าง exe

---

## 📦 เวอร์ชั่น Lite vs Full

| | Lite | Full |
|---|---|---|
| **ขนาด** | ~1 GB | ~7 GB |
| **TTS** | Edge-TTS (Azure) | Edge-TTS + OmniVoice |
| **RVC** | ❌ | ✅ |
| **GPU** | ไม่ต้องการ | แนะนำ RTX (CUDA) |
| **เหมาะกับ** | ทุกคน | มีการ์ดจอ RTX/GTX |

---

## 📁 โครงสร้างโปรเจค

```
tts-for-livestream-ver2/
├── main.py                    # Entry point + warm-up patches (PyInstaller)
├── app.py                     # TTSForLivestreamApp — main controller
├── version.json               # เลขเวอร์ชั่น + changelog + download URLs
├── updater.py                 # Auto-update (check + download + apply_patch + restart)
├── machine_id.py              # Machine fingerprint (สำหรับระบบแบน)
├── supporters_api.py          # API client สำหรับระบบ Supporters
├── data_dir.py                # Portable data directory + migration
│
├── ui/
│   ├── theme.py               # QSS stylesheet + colors + fonts
│   ├── widgets/
│   │   ├── topbar.py          # แถบบน (buttons + platform status + update button)
│   │   ├── sidebar.py         # แถบซ้าย (platforms + voice + sliders)
│   │   ├── chat_panel.py      # แชทสด
│   │   ├── chat_row.py        # แต่ละข้อความ (emote rendering)
│   │   └── status_bar.py      # แถบล่าง
│   └── dialogs/
│       ├── settings.py        # หน้าตั้งค่า (13 sections)
│       ├── supporter_upload.py # Dialog ส่งหลักฐานสนับสนุน
│       ├── author_modal.py    # ข้อมูลผู้ใช้ (สถิติ + ประวัติ)
│       ├── user_manager.py    # จัดการผู้ชม
│       └── ...
│
├── (logic — shared with v1)
│   chat_queue.py              # TTS pipeline (enqueue → synth → play)
│   chat_twitch.py             # Twitch chat client
│   chat_youtube.py            # YouTube chat client
│   chat_mylive.py             # MyLive chat client
│   chat_tiktok.py             # TikTok chat client
│   chat_kick.py               # KICK chat client
│   settings.py                # AppSettings dataclass + save/load
│   text_filter.py             # Text filtering (NG/replace/secret codes)
│   tts_engine.py              # Edge-TTS engine
│   omnivoice_engine.py        # OmniVoice engine (Full only)
│   rvc_engine.py              # RVC voice conversion (Full only)
│   translator.py              # Translation (Google)
│   composer_server.py         # Canvas overlay server (aiohttp)
│   overlay_server.py          # OBS overlay server
│   playroom_server.py         # Playroom server
│   game_overlay.py            # Game overlay launcher
│   game_overlay_qt.py         # Game overlay Qt window
│   obs_refresh.py             # OBS WebSocket auto-refresh
│   audio_player.py            # pygame.mixer audio playback
│   message_history.py         # Message history (portable)
│   event_log.py               # Event log (portable)
│   donate_tracker.py          # Donate tracker (portable)
│   emote_cache.py             # Emote cache (Twitch/7TV/BTTV/FFZ)
│   voice_downloader.py        # RVC voice downloader
│
├── assets/                    # icon + fonts (NotoSansThai) + logos
├── server/                    # PHP backend (Supporters system)
├── *.spec                     # PyInstaller specs (lite/full)
└── build_patch.py             # Build patch/full zip + version.json
```

---

## 🛠️ สำหรับนักพัฒนา

### รันในโหมด dev
```bash
cd tts-for-livestream-ver2
python main.py
# หรือ
run.bat
```

### Build exe
```bash
# Lite (Edge-TTS only, ~1GB)
python -m PyInstaller tts_lite.spec --noconfirm

# Full (OmniVoice + RVC, ~7GB)
python -m PyInstaller tts_full.spec --noconfirm
```

### Build patch + release
```bash
python build_patch.py patch lite   # สร้าง patch_lite.zip (~11MB)
python build_patch.py patch full   # สร้าง patch_full.zip (~63MB)
python build_patch.py full lite    # สร้าง full_lite.zip (~1GB)
python build_patch.py version      # สร้าง version.json + remote_version.json
```

### Qt Signal Pattern (สำคัญ — กัน UI ค้าง)
```python
# ❌ ผิด — QTimer.singleShot จาก background thread ไม่ทำงาน
threading.Thread(target=lambda: QTimer.singleShot(0, callback)).start()

# ✅ ถูก — ใช้ QThread + Signal
class _Worker(QThread):
    done = Signal(object)
    def run(self):
        result = do_work()
        self.done.emit(result)  # → main thread

worker.done.connect(callback)
worker.start()
```

---

## 📝 Changelog

### v2.4.x (current)
- 🆕 Widget: Avatar (PNGTuber 4-image + animations + flip + preset man/girl)
- 🆕 Widget: Donate Goal (EasyDonate API + 5 bar styles + 19 color themes + custom colors)
- 🆕 Composer: Auto port fallback (8801-8810)
- 🆕 Composer: Donate Goal ปุ่มเชื่อมต่อ EasyDonate + sync color theme
- 🔧 แก้บั๊ก แพลตฟอร์มหลุดตอนปิด Settings (restore connected state)
- 🔧 แก้บั๊ก ยอดคนดูไม่แสดงในการ์ด (show 👥 0 ตอนเชื่อมต่อ)
- 🔧 แก้บั๊ก เวอร์ชั่นค้าง v2.0.0 มุมขวาล่าง (อ่านจาก version.json)
- 🔧 แก้บั๊ก port 8808 → 8801 (migrate + unify)
- 🔧 แก้บั๊ก Now Playing โปร่งใสตลอด (np_bg_opacity default 1.0)
- 🔧 แก้บั๊ก emote ในแชทไม่แสดงเป็นรูป (port ผิด 8808 → 8801)
- 🔧 แก้บั๊ก default ค้างทุกครั้ง (migration flag save ทันที)
- 🔧 แก้บั๊ก Composer widget ไม่ย้ายตำแหน่งใน OBS (overlay config ตรงๆ)
- 🔧 แก้บั๊ก Composer color pickers ไม่อัปเดจ (WS push ทับค่าใหม่ → merge fields)
- 🔧 Chat widget: เพิ่มการจัดตำแหน่ง ซ้าย/กลาง/ขวา
- 🔧 Settings: สลับลำดับเมนูการแปล (อ่านหลายภาษาบน, แปลไทยกลาง, ปิดล่าง)
- 🔧 Top menu: ปุ่ม toggle เปลี่ยนเป็นสถานะ (คลิก → เปิด Settings > การแปล)
- 🔧 Default: Azure ผู้หญิง + อ่านทุกภาษา (ครั้งแรกเท่านั้น + flag กันทำซ้ำ)

### v2.3.x
- 🆕 Replace Export/Import (JSON format)
- 🆕 Replace Preview ใช้ Premwadee edge-tts ตรงๆ (ไม่ผ่าน pipeline)
- 🆕 Replace Preview ลบปุ่มคำเดิม (เหลือแค่คำอ่าน TTS เหมือน v1)
- 🔧 Top menu sync กับ settings ตอนเปิดโปรแกรม (multilang priority)
- 🔧 Zebra stripes default เปิด
- 🔧 Default mode = อ่านทุกภาษา (ไม่ใช่ แปลภาษา)
- 🔧 โค้ดลับ: จำกัดไฟล์เฉพาะ MP3/WAV
- 🔧 โค้ดลับ: ขยายช่องจำกัด/user/วัน + Preview/Stop toggle + volume slider
- 🔧 Auto-update: QThread + browser UA + glow animation + ปุ่ม UPDATE แดง
- 🔧 Volume slider จดจำค่า + default 100% (master + per-platform)
- 🔧 Auto-connect ทุกแพลตฟอร์ม + Block button ใน Author Modal กดได้
- 🔧 TTS on/off → หยุดเสียงทันที + ล้างคิว
- 🔧 Game Overlay / Overlay+ dispatch ใน main.py (กันเปิดโปรแกรมใหม่)
- 🔧 Composer Editor port fix (_port → composer_port)
- 🔧 Auto-update download: QThread + Signal (แก้ progress ค้าง 0%)
- 🔧 Auto-update check: QThread + Signal (แก้ auto-check ไม่ทำงานใน exe)
- 🔧 Replace หลังแปลภาษา: apply pronunciation หลัง translate
- 🔧 Replace ไม่ผ่าน pipeline เด็ดขาด (edge-tts ตรงๆ)
- 🌐 แก้เว็บคลังศัพท์ ng-replace.php: JS syntax fix + admin bypass + DOMContentLoaded
- 📦 Build system: patch_lite + patch_full + version.json + GitHub release

### 🤖 Chat Bot + ส่งแชท (Twitch) — ทำเสร็จแล้ว ✅
สถานะ: **Twitch เสร็จแล้ว** — YouTube ยังไม่ได้ทำ (รอต่อ)

| แพลตฟอร์ม | พิมพ์แชท | Chat Bot | Event Response | สถานะ |
|-----------|---------|----------|---------------|-------|
| **Twitch** | ✅ เสร็จ | ✅ เสร็จ | ✅ Sub/Bits/Raid | ใช้งานได้ |
| **YouTube** | ❌ ยัง | ❌ ยัง | ❌ ยัง | รอทำ (quota จำกัด) |
| **Kick** | ❌ | ❌ | ❌ | ไม่ทำ (unofficial) |
| **TikTok** | ❌ | ❌ | ❌ | ไม่ทำ (ไม่มี API) |
| **MyLive** | ❌ | ❌ | ❌ | ไม่ทำ (ไม่มี API) |

#### สิ่งที่ทำเสร็จ (Twitch):
- **OAuth flow** (`twitch_oauth.py`) — กดปุ่ม → เบราว์เซอร์ → token กลับมาอัตโนมัติ (Client ID ฝังในโปรแกรม)
- **พิมพ์แชท** (`chat_twitch.py`) — ช่องพิมพ์ด้านล่าง Live Chat + platform chips เลือกแพลตฟอร์ม
- **Chat Bot** (`twitch_bot.py`) — ตอบคำสั่ง !xxx + Timer + Event Responses (Sub/Bits/Raid/Follow)
- **Bot filter** — ไม่อ่าน TTS สำหรับ: บอทตัวเอง + Nightbot/StreamElements/blacklist + คำสั่ง !xxx
- **Overlay filter** — ซ่อนบอทจาก Overlay (toggle ได้)
- **Bot display** — 🤖 ไอคอนหุ่นยนต์ + ชื่อสีเหลือง + ชื่อ "Baitoei-Bot" (custom ได้)

#### ไฟล์หลัก:
- `twitch_oauth.py` — OAuth flow (localhost server + code exchange + token refresh)
- `twitch_bot.py` — Bot engine (commands + timer + event responses + cooldown + rate limit)
- `chat_twitch.py` — รองรับ OAuth login + `send_message()` + `send_command()` + thread lock
- `settings.py` — `twitch_oauth_token`, `twitch_bot_*` fields
- `app.py` — `_on_chat_send`, `_on_bot_response`, `_is_bot_author`, `_chat_bots` dict (แยกตามแพลตฟอร์ม)
- `ui/widgets/chat_panel.py` — ช่องพิมพ์ + platform chips + `update_platform_chips()`
- `ui/widgets/chat_row.py` — bot response display (🤖 + สีเหลือง)
- `ui/dialogs/settings.py` — section 🤖 Chat Bot (commands + timers + events + overlay toggle)

#### สิ่งที่ต้องทำต่อ (YouTube):
- สมัคร Google Cloud Project + OAuth Client ID
- ใช้ `liveChatMessages.insert` API (quota 10,000 units/วัน)
- ทำ OAuth flow สำหรับ YouTube (บัญชี Google)
- เพิ่ม YouTube chip ใน platform chips
- ทำ bot response สำหรับ YouTube events (Super Chat, Membership, etc.)

#### ⚠️ ปัญหาที่เจอ + วิธีแก้สุดท้าย:

**ปัญหา Splash screen ขึ้นช้า (5-6 วิ):**
- สาเหตุ: `main.py` import `transformers` + `torch` (4.3GB) ที่ module-level ก่อน `splash.show()`
- แก้: ย้าย warmup ออกจาก module-level → เรียกหลัง `splash.show()` + `app.processEvents()`
- ผล: splash ขึ้นใน ~1.4 วิ (จาก 5-6 วิ)

**ปัญหา OBS launch fail (`WinError 740`):**
- สาเหตุ: `subprocess.Popen([obs_path])` ตรงๆ → OBS ใน `Program Files` ต้องการ elevation
- แก้: ใช้ `subprocess.Popen(shell=True)` + `start "" "{path}"` → cmd.exe จัดการ elevation
- ผล: เปิด OBS ได้โดยไม่ต้อง admin

**ปัญหา OBS zombie process (เปิดไม่ได้ แต่ tasklist เจอ):**
- สาเหตุ: OBS crash ค้าง → process รันอยู่แต่ไม่มี window → โปรแกรมเข้าใจว่า "เปิดอยู่"
- แก้: ใช้ `_find_obs_window()` (EnumWindows + PID) แทน tasklist → ถ้าไม่มี window = ไม่ได้เปิดจริง
- ผล: zombie → ถือว่าไม่ได้เปิด → เปิดใหม่ได้

**ปัญหา ChatMessage TypeError (echo ไม่ขึ้น Live Chat):**
- สาเหตุ: `ChatMessage` dataclass ไม่มี fields `color/badges/emotes/timestamp/raw` → ส่งผิด → `TypeError` → catch เงียบๆ
- แก้: ย้าย `color/badges/timestamp` เข้า `extra` dict แทน
- ผล: echo ขึ้นใน Live Chat ปกติ

**ปัญหา Bot response ไม่ขึ้น Live Chat (cross-thread):**
- สาเหตุ: bot response ถูกเรียกจาก IRC reader thread (background) → `add_message` แก้ UI จาก background → Qt ห้าม
- แก้: เพิ่ม Qt Signal `_bot_response_sig = Signal(str, str)` → marshal ข้าม thread → main thread เรียก `add_message`
- ผล: bot ตอบ → echo ขึ้น Live Chat ปกติ

**ปัญหา `Signal(str, object)` ไม่ trigger:**
- สาเหตุ: Qt signal มีปัญหากับ Python list/object → emit แล้ว slot ไม่ถูกเรียก
- แก้: เปลี่ยนเป็น `Signal(str, str)` + JSON encode/decode
- ผล: signal ทำงานปกติ

**ปัญหา Settings checkbox reset ทุกครั้ง:**
- สาเหตุ: `_load_values` เรียก `setChecked()` → trigger `stateChanged` → `_auto_save()` → เขียนทับค่าจริงด้วย default
- แก้: เพิ่ม flag `_loading = True/False` → `_auto_save` ข้ามถ้ากำลัง load
- ผล: checkbox คงค่าเดิมหลังปิด-เปิด settings

**ปัญหา Bot widgets ไม่ save:**
- สาเหตุ: `bot_enabled_cb` และ bot widgets ไม่ได้เชื่อมกับ `_auto_save`
- แก้: เพิ่ม `stateChanged`/`textChanged` + QTimer debounce 500ms ให้ทุก bot widget
- ผล: ทุกการเปลี่ยนแปลงในหน้า Chat Bot ถูกบันทึกอัตโนมัติ

**ปัญหา `_add_bot_cmd_row` หายไป (settings เปิดไม่ได้):**
- สาเหตุ: ตอนแก้ UI section ใหม่ → ลืมใส่ `def _add_bot_cmd_row(self, command, response):` กลับ → Python มองเป็นส่วนต่อของ method เดิม
- แก้: เพิ่ม `def` กลับเข้าไป
- ผล: settings เปิดได้ปกติ

**ปัญหา Chat Bot section ไม่อยู่ใน sidebar:**
- สาเหตุ: `categories` list เป็น hardcoded → ไม่มี "🤖 Chat Bot"
- แก้: เพิ่ม `("🤖 Chat Bot", "twitch_bot")` ใน categories list
- ผล: section โผล่ใน sidebar ตำแหน่ง 12

**ปัญหา data/settings.json vs ~/.tts-for-livestream/settings.json:**
- สาเหตุ: dev mode อ่าน `data/settings.json` แต่ OAuth token ถูกบันทึกใน `~/.tts-for-livestream/settings.json` (path คนละที่)
- แก้: คัดลอก OAuth fields จากไฟล์เก่ามาใส่ `data/settings.json`
- ผล: token ถูกอ่านถูกที่ → chip แสดง → ส่งแชทได้

**ปัญหา `QSize` ไม่ defined (chip ไม่แสดง):**
- สาเหตุ: `chat_panel.py` ใช้ `QSize` แต่ไม่ได้ import → `update_platform_chips` fail เงียบๆ
- แก้: เพิ่ม `from PySide6.QtCore import Qt, Signal, QSize`
- ผล: chip แสดงปกติ

### v2.2.0
- 🆕 ระบบ Supporters (ส่งหลักฐาน + Discord approve + แสดงในโปรแกรม)
- 🆕 Auto-Update (ปุ่ม New Update + patch download + restart)
- 🆕 โค้ดลับ (viewer พิมพ์ !code → เล่นเสียง)
- 🔧 Volume slider แพลตฟอร์มใช้งานได้จริง
- 🔧 ปิด/เปิด แสดงแพลตฟอร์ม → sidebar + topbar อัพเดตทันที
- 🔧 ปุ่ม TTS on/off → หยุดเสียงทันที + ล้างคิว
- 🔧 Game Overlay / Overlay+ / Composer แก้บั๊ก

### v2.1.0
- 🆕 Auto-Update system (4-layer SSL fallback)
- 🆕 ระบบ Supporters (upload + approve + display)
- 🔧 ขยาย Settings sidebar + OBS WebSocket toggle

### v2.0.0
- 🔄 Migration: CustomTkinter → PySide6
- 🔄 Thread-safety: `self.after()` → Qt Signals
- 🔄 Layout: Tk pack/grid → Qt HBox/VBox/Splitter

### v1.x (CustomTkinter)
- โปรแกรมดั้งเดิม พัฒนาด้วย CustomTkinter (Tkinter)
- รองรับ Twitch / YouTube / MyLive / TikTok / KICK
- TTS (Edge-TTS + RVC) + translation + overlay + playroom
