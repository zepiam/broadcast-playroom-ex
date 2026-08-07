# 🤝 Broadcast Playroom — Contributing Guide

คู่มือสำหรับนักพัฒนาที่ต้องการมีส่วนร่วมพัฒนา Broadcast Playroom

---

## เริ่มต้น

### สิ่งที่ต้องมี
- Python 3.10+ (แนะนำ 3.10 เพราะรองรับ torch 2.2.2)
- pip
- Git
- NVIDIA GPU + CUDA (ถ้าทำ Full version RVC)
- Windows 10/11 (โปรแกรมรองรับแค่ Windows ตอนนี้)

### Setup
```bash
# clone
git clone https://github.com/zepiam/broadcast-playroom.git
cd broadcast-playroom

# ลง dependencies หลัก
pip install customtkinter edge-tts pygame aiohttp Pillow

# ลง dependencies เพิ่ม (ถ้าทำ Full)
pip install "numpy<2" torch torchaudio  # RVC
pip install PySide6 PySide6-Addons      # Game Overlay
pip install playwright                  # MyLive
playwright install chromium             # MyLive browser

# รันโหมด dev (ไม่ต้อง build exe)
python main.py
```

### รันแบบ dev (ไม่ build)
```bash
python main.py
```
- ไม่ต้อง PyInstaller
- แก้โค้ด → รันใหม่ได้ทันที
- log แสดงใน terminal (ไม่เข้าไฟล์)

---

## Code Style

### หลักการ
- เขียนภาษาไทยสำหรับ comment + status message (ผู้ใช้เป็นคนไทย)
- เขียนภาษาอังกฤษสำหรับ docstring API (เผื่อนักพัฒนาต่างชาติ)
- function/method name เป็น `snake_case`
- class name เป็น `PascalCase`
- constant เป็น `UPPER_SNAKE_CASE`

### ตัวอย่าง
```python
def _toggle_overlay_from_topbar(self) -> None:
    """Toggle overlay server on/off from topbar button"""
    self.settings.overlay_enabled = not self.settings.overlay_enabled
    save_settings(self.settings)
    self._apply_overlay_settings()
    self._update_overlay_toggle_btn()
    # แจ้งผู้ใช้
    self._safe_status("✅ Overlay เปิดแล้ว")
```

### เรื่องสำคัญ
- **อย่ากลืน error** — ถ้าจะ `except Exception` ต้องมี log หรือ status message
- **thread-safety** — Tk widget ต้อง access จาก main thread เท่านั้น → ใช้ `self.after(0, callback)`
- **lazy import** — import หนัก (torch, PySide6) แบบ lazy ใน function ไม่ใช่ top-level

---

## โครงสร้างโค้ด

### การแยก module
```
main.py              → entry point (splash + log + crash handler)
app_gui.py           → Main GUI + SettingsDialog + GameOverlaySettingsDialog
                        (ใหญ่สุด ~11000+ บรรทัด — แยกได้ในอนาคต)

chat_queue.py        → TTS pipeline + Mixed Voice + translation
                        (core logic ของการอ่านเสียง)

settings.py          → AppSettings dataclass + load/save
                        (single source of truth ของทุก config)

chat_*.py            → Platform clients (twitch, youtube, mylive, tiktok, kick)
                        (แต่ละตัวอิสระ ไม่พึ่งกัน)

overlay_*.py         → OBS overlay (HTTP server + WebSocket)
game_overlay*.py     → Game Overlay + Overlay+ (Qt subprocess)
```

### การเพิ่มฟีเจอร์ใหม่

#### 1. เพิ่ม platform client
```python
# chat_newplatform.py
from chat_queue import ChatMessage

class NewPlatformClient:
    def __init__(self, on_message, on_status, on_error, **kwargs):
        self.on_message = on_message
        self.on_status = on_status
        # ...

    def connect(self, target: str) -> bool:
        # เชื่อมต่อ platform
        pass

    def disconnect(self):
        pass

    def _on_chat(self, data):
        # แปลง data → ChatMessage
        msg = ChatMessage(
            platform="newplatform",
            author=data["user"],
            text=data["message"],
            event="message",
            extra={},
        )
        self.on_message(msg)
```

จากนั้น register ใน `app_gui.py`:
```python
PLATFORM_REGISTRY["newplatform"] = {
    "label": "NewPlatform",
    "emoji": "🆕",
    "color": "#ff6b6b",
    "logo": "assets/logo_newplatform.png",
    "placeholder": "ใส่ channel ID",
    "saved_attr": "newplatform_target",
    "client_cls": NewPlatformClient,
    "client_kwargs": lambda app: {},
    "supports_autoconnect": False,
}
```

#### 2. เพิ่ม event type
```python
# ใน notification_manager.py EVENT_MAP
EVENT_MAP["myevent"] = {
    "label": "อีเวนต์ใหม่",
    "icon": "🎯",
    "sound": "assets/sound/myevent.mp3",
    "tts_template": "{author} ทำอีเวนต์ใหม่",
}

# ใน event_log.py ALL_EVENT_TYPES
ALL_EVENT_TYPES.append("myevent")
```

#### 3. เพิ่ม setting field
```python
# ใน settings.py AppSettings
my_new_setting: bool = False

# ใน to_dict()
"my_new_setting": self.my_new_setting,

# ใน from_dict()
if "my_new_setting" in data:
    s.my_new_setting = bool(data["my_new_setting"])
```

---

## Git Workflow

### Branch
```
main              → stable (release-ready)
feature/xxx       → ฟีเจอร์ใหม่
fix/xxx           → แก้บัค
```

### Commit message
```
feat: เพิ่ม Overlay+ custom URL overlay
fix: แก้ Theme selector หายตอน switch mode
docs: เพิ่ม plugin developer guide
refactor: แยก _commit_settings จาก _on_save
```

### ก่อน commit
```bash
# syntax check ทุกไฟล์ที่แก้
python -m py_compile app_gui.py

# รันโปรแกรมทดสอบ
python main.py

# ทดสอบ build (อย่างน้อย Lite)
python -m PyInstaller tts_lite.spec --noconfirm
```

---

## Build & Release

### Build exe
```bash
# สำคัญ: ปิดโปรแกรมก่อน build เสมอ (กัน file lock)

# Lite (~900 MB)
python -m PyInstaller tts_lite.spec --noconfirm

# Full (~5.7 GB)
python -m PyInstaller tts_full.spec --noconfirm
```

### สร้าง patch + version
```bash
# copy version.json ไป dist (สำคัญ — กัน version mismatch)
cp version.json "dist/Broadcast Playroom Lite/_internal/version.json"
cp version.json "dist/BroadcastPlayroom_Full/_internal/version.json"

# สร้าง patch zip
python build_patch.py patch lite
python build_patch.py patch full

# สร้าง version.json สำหรับ GitHub
python build_patch.py version
cp release/remote_version.json release/version.json
```

### Upload GitHub
```bash
gh release edit latest --repo zepiam/broadcast-playroom \
  --title "Broadcast Playroom vX.Y.Z" --notes "..."

gh release upload latest \
  release/version.json release/patch_lite.zip release/patch_full.zip \
  --repo zepiam/broadcast-playroom --clobber
```

### ข้อควรระวังตอน build
1. **ปิดโปรแกรมก่อน** — exe และ `logs/tts_00.log` ถูก Windows ล็อก → build fail
2. **copy version.json** — ถ้าลืม → version.json ใน zip เป็นของเก่า
3. **numpy < 2** — torch 2.2.2 ไม่รองรับ numpy 2.x
4. **collect_submodules('requests')** — ต้องมีใน spec ไม่งั้น updater ไม่ทำงานบนเครื่องอื่น
5. **`--noconfirm`** — ให้ PyInstaller ลบ dist เอง (ดีกว่า `rm -rf`)

---

## Debug

### ดู log
```
logs/
├── tts_00.log    ← ล่าสุด
├── tts_01.log    ← ครั้งก่อน
├── ...
├── tts_09.log    ← เก่าสุด
└── crash.log     ← crash ล่าสุด (traceback เต็ม)
```

### Debug print (ในโค้ด)
```python
print(f"[debug] overlay state: {self.overlay_enabled}", flush=True)
```
- ใน dev mode → แสดงใน terminal
- ใน exe (windowed) → เข้า `logs/tts_00.log`

### Debug Game Overlay / Overlay+
```
# Qt subprocess log
%TEMP%\qt_startup_mo0.log     ← Overlay+ startup
%TEMP%\game_overlay_qt.log    ← Game Overlay dispatch

# Queue files
%TEMP%\game_overlay_cmd_queue.json         ← Game Overlay commands
%TEMP%\game_overlay_cmd_queue_mo0.json     ← Overlay+ 0 commands
%TEMP%\game_overlay_response_queue_mo0.json ← Overlay+ 0 responses
```

---

## การทดสอบ

### ทดสอบ TTS
```python
python -c "
import asyncio, edge_tts
async def test():
    c = edge_tts.Communicate('สวัสดีครับ', 'th-TH-PremwadeeNeural')
    audio = b''
    async for chunk in c.stream():
        if chunk['type'] == 'audio':
            audio += chunk['data']
    print(f'OK: {len(audio)} bytes')
asyncio.run(test())
"
```

### ทดสอบ Translation
```python
python -c "
from translator import Translator
t = Translator(provider='google', api_key='', host='', target_lang='th', supported_langs=['en','ja'])
print(t.translate('Hello', source_lang='en'))
print(t.translate('こんにちは', source_lang='ja'))
"
```

### ทดสอบ Plugin
```python
python -c "
from plugin_loader import get_plugin_loader
loader = get_plugin_loader()
for p in loader.plugins:
    print(f'{p.trigger} → {p.name}')
r = loader.check_command('!hi', author='test')
print(r[0] if r else 'no match')
"
```

### ทดสอบ Auto-update
```python
python -c "
from updater import check_for_update, get_current_version
print('current:', get_current_version())
info = check_for_update()
print('update:', info)
"
```

---

## สิ่งที่ต้องรู้ (Gotchas)

### 1. PyInstaller + Tk + Qt ในเครื่องเดียวกัน
- Qt (Game Overlay) รันเป็น **subprocess** ไม่ใช่ import ใน main process
- ถ้า import Qt ใน main → crash (Tk + Qt conflict)
- แก้: spawn subprocess `["python", "game_overlay_qt.py", ...]`

### 2. windowed mode + stdout
- PyInstaller windowed mode → stdout เป็น pipe (ไม่ใช่ terminal)
- ถ้า subprocess พิมพ์ stdout เยอะ → pipe เต็ม → deadlock
- แก้: ใช้ file-based queue แทน stdout (ดู game_overlay_qt.py)

### 3. edge-tts เป็น async
- edge-tts ใช้ asyncio → ต้อง `asyncio.run()` ใน sync context
- หรือใช้ `edge_tts.Communicate` ใน background thread

### 4. numpy version
- torch 2.2.2 ต้องการ numpy < 2
- ถ้า numpy อัปเกรดเป็น 2.x → RVC crash ("Numpy is not available")
- แก้: `pip install "numpy<2"`

### 5. customtkinter + Tk 8.6
- CTkToplevel ต้องการ Tk 8.6+
- ถ้าสร้าง Toplevel หลายอัน → บางครั้ง modal grab พัง
- แก้: singleton pattern (กันเปิดซ้อน)

### 6. Windows Defender
- PyInstaller exe โดน AV แจ้งเตือนบ่อย (false positive)
- staging/download ใน %TEMP% ทำให้น่าสงสัยมากขึ้น
- แก้: staging ใน install_dir + บอกผู้ใช้ Add Exception

### 7. Settings persistence
- settings.json อยู่ที่ `~/.tts-for-livestream/settings.json`
- ถ้า field ใหม่ไม่อยู่ใน JSON → ใช้ default จาก dataclass
- แก้: `from_dict` อ่านแบบ optional (`if "field" in data:`)

### 8. Thread-safety
- Tk widget ต้อง access จาก **main thread** เท่านั้น
- Background thread (chat client, TTS) → ใช้ `self.after(0, callback)`
- ถ้าแก้ widget จาก background thread → crash ได้

---

## คำถามที่พบบ่อย (Developer)

### Q: ทำไม Settings เปิดช้า?
A: `_build_*_tab` สร้าง widget ร้อยกว่าตัวใน `__init__` → แก้ด้วย deferred build (`after(50, _build_tabs)`)

### Q: ทำไม overlay ข้อความไม่ขึ้น?
A: เช็ค 3 อย่าง:
1. overlay server เปิดอยู่ไหม (`overlay_enabled = True`)
2. port ว่างไหม (8765/8766/8767)
3. ในโหมดแปล → `_will_be_translated` หน่วง push หรือเปล่า

### Q: ทำไม build fail?
A: ส่วนใหญ่เพราะโปรแกรมเปิดค้าง → ปิดก่อน build

### Q: ทำไม auto-update ไม่ทำงานบนเครื่องอื่น?
A: เช็ค 4 layer fallback ใน `updater.py` — ถ้า fail ทุก layer → ดู `logs/tts_00.log` บนเครื่องนั้น

### Q: Emote ไม่แสดงใน Overlay (สำคัญ — เคยเจอหลายรอบ)
A: Emote rendering มี **4 จุดที่ต้องครบ** ถ้าขาดจุดใดจุดหนึ่ง → emote ไม่แสดง:

1. **`chat_twitch.py`** — parse emote จาก Twitch tag → เก็บใน `extra["emotes"]` (offset-based)
   - ต้องเก็บ `raw_text` (text ก่อน strip emote) ด้วย เพราะ emote offset อ้างอิงจาก text เดิม
   - `msg.text` หลัง strip จะว่างถ้าเป็น emote ล้วน → **ต้องใช้ raw_text แทน**

2. **Serialize (ส่งไป overlay)** — ต้องส่ง `raw_text` + `twitch_emotes` + `segments` + `sticker_url`
   - Overlay server (`overlay_server.py:_serialize_message`) — มีครบแล้ว
   - **Composer server (`app_gui.py:_serialize_msg_for_overlay`)** — เคยลืมส่ง emote data ทั้งหมด!
   - ถ้าเพิ่ม overlay type ใหม่ → ต้อง serialize ครบทุก field

3. **Emote proxy (ดาวน์โหลดรูป)** — `/emote/{emote_id}` endpoint
   - Overlay server (`overlay_server.py:_handle_emote`) — มีครบ (static + animated + cache)
   - **Composer server (`composer_server.py:_handle_emote_simple`)** — เคยเป็น placeholder คืน 404!
   - ถ้าสร้าง server ใหม่ → ต้อง copy emote proxy logic มาด้วย

4. **Client rendering (HTML/JS)** — ต้อง render emote เป็น `<img>` ไม่ใช่ `textContent`
   - `overlay.html:renderContent()` — ใช้ `raw_text` + slice offset + `makeImg()` (ถูกแล้ว)
   - **แต่แต่ละ appearance mode มี render path แยก**:
     - **Default** → `addMessage()` → `renderContent()` ✅
     - **Balloon** → `addMessage()` + balloon mode ใช้ `raw_text` แทน `text` ✅
     - **Character Talk** → `addCharacterMessage()` → `updateCharBubble()` — **เคยใช้ textContent ล้วน (ไม่ render emote)** ต้องแก้ให้เรียก emote rendering เหมือน renderContent
   - **ถ้าเพิ่ม appearance ใหม่** → ต้องเช็คว่า render path ของ mode นั้นรองรับ emote หรือไม่

**สรุปเมื่อเพิ่ม appearance ใหม่ / overlay server ใหม่:**
> 1. Serialize ต้องส่ง `raw_text` + `twitch_emotes` + `segments` + `sticker_url`
> 2. Server ต้องมี `/emote/{id}` proxy (copy จาก overlay_server)
> 3. Render path ของ mode นั้นต้องเรียก emote rendering (อย่าใช้แค่ `textContent`)
> 4. เช็คกรณี emote ล้วน (`msg.text` ว่าง) — ต้องใช้ `raw_text` แทน

### Q: จะเพิ่ม voice ใหม่ใน Mixed Voice?
A: เพิ่มใน `language_detect.py` → `VOICE_BY_LANG` + `_char_lang()` (Unicode range)

### Q: Composer Chat Widget ไม่รับข้อความจริง (แต่ Demo Test ได้)
A: เช็คว่า `_composer_push_message(msg)` ถูกเรียกแยกจาก `overlay_server.push_message` หรือไม่

**ปัญหาที่เคยเจอ:** ใน poll loop (`_poll_ui_updates`) `_composer_push_message` ถูกฝังอยู่ใน block เดียวกับ `overlay_server.push_message`:
```python
# ❌ ผิด — ถ้า overlay_server = None (ปิด overlay เก่า) → ข้ามทั้ง block → composer ไม่ได้รับ
elif (self.overlay_server is not None and ...):
    self.overlay_server.push_message(msg)
    self._composer_push_message(msg)  # ← ไม่ถูกเรียก!
```

**แก้:** แยก composer push ออกมาอิสระ:
```python
# ✅ ถูก — composer push ไม่ขึ้นกับ overlay_server
elif (...):
    if self.overlay_server is not None:
        self.overlay_server.push_message(msg)
    self._composer_push_message(msg)  # ← เรียกเสมอ
```

**กฎ:** Composer overlay (8801) และ OBS overlay (8765) เป็นคนละ server — push message ต้องแยกอิสระ ไม่ขึ้นต่อกัน

---

### Q: TTS ไม่ต่อเนื่อง / เสียงขาดช่วง / อ่านช้า
A: ปรับ 3 จุดใน `chat_queue.py` + `app_gui.py` (บันทึกการปรับ v1.11.0):

| จุด | ไฟล์ | เดิม | ใหม่ | เหตุผล |
|---|---|---|---|---|
| **ready queue buffer** | `chat_queue.py:216` | `maxsize=2` | `maxsize=5` | เพิ่ม buffer เสียงพร้อมเล่น → ลดโอกาสขาดช่วง |
| **poll cadence** | `app_gui.py:6183` | `after(200)` | `after(100)` | ข้อความเข้าคิว TTS เร็วขึ้น (200ms → 100ms) |
| **play busy-wait** | `chat_queue.py:855` | `sleep(0.05)` | `sleep(0.01)` | ลด gap ระหว่างจบเสียงเก่า + เริ่มใหม่ (50ms → 10ms) |

**ถ้าย้อนกลับ:** เปลี่ยนค่ากลับตามตาราง (เดิม) — ทุกจุดมี comment บอกค่าเดิมไว้แล้ว

**อื่น ๆ ที่มีผลต่อความต่อเนื่อง:**
- `author_cooldown = 0.0` (ปิดแล้ว — เดิม 3.0s) คนเดียวพิมพ์รัว ๆ จะเข้าคิวหมด
- `auto_speed = True` — ข้อความยาวอ่านเร็วขึ้น (ลดเวลาเล่น → buffer ทันข้อความถัดไป)
- TTS synth ฝั่ง Microsoft Edge server — ความเร็วขึ้นกับเน็ตของ user

## 🚀 Release Process (อัปเดตเวอร์ชัน)

### ขั้นตอนปล่อยเวอร์ชันใหม่

1. **แก้ `version.json`** — เปลี่ยน `version` + `changelog`
2. **Build exe** — `py -3.10 -m PyInstaller tts_lite.spec` + `tts_full.spec`
3. **Build patch** — `py -3.10 build_patch.py patch lite` + `patch full`
   - ⚠️ **ต้อง build patch หลังแก้ version.json เสมอ** (patch บรรจุ `_internal/version.json`)
4. **อัป GitHub** — `gh release upload latest patch_lite.zip patch_full.zip version.json --clobber`
5. **อัปเดตชื่อ release** — `gh release edit latest --title "Broadcast Playroom vX.Y.Z"`

### ⚠️ ปัญหา Update Loop (สำคัญมาก!)

**อาการ:** User กดอัปเดต → อัปเดตเสร็จ → โปรแกรมยังเห็นเวอร์ชันเดิม → แจ้งอัปเดตอีก → วนลูปไม่จบ

**สาเหตุหลัก (เจอบ่อยสุด):**
1. **เปลี่ยน `version.json` แต่ลืม build patch ใหม่** → patch ยังบรรจุ version.json เก่า → อัปเดตแล้วเห็นเวอร์ชันเก่า
   - แก้: build_patch.py ต้องรันหลังแก้ version.json เสมอ
2. **GitHub CDN cache propagation delay** (~2-5 นาที) — edge ในไทยยังส่ง patch เก่า
   - อาการ: บางเครื่องเห็นเวอร์ชันใหม่ บางเครื่องยังเห็นเก่า
   - แก้: รอ 5 นาที → หายเอง (ไม่ใช่บั๊ก)
3. **อัปแค่ version.json แต่ไม่อัป patch zip** → version.json บน GitHub เป็นใหม่ แต่ patch ยังเก่า
   - แก้: อัปทั้งคู่พร้อมกันเสมอ

**กฎทอง:**
> ทุกครั้งที่แก้ `version.json` → **ต้อง build patch ใหม่ + อัพโหลด patch ด้วย** (ไม่ใช่แค่ version.json)

### Checklist ก่อนปล่อยเวอร์ชัน

- [ ] แก้ `version.json` (version + changelog)
- [ ] ปิดโปรแกรมที่รันอยู่ (กัน build fail — PermissionError)
- [ ] ล้าง `__pycache__` (กันใช้ .pyc เก่า)
- [ ] Build Lite exe (`tts_lite.spec`)
- [ ] Build Full exe (`tts_full.spec`)
- [ ] Build patch_lite + patch_full (`build_patch.py`)
- [ ] **เช็ค version ใน patch** — `py -c "import zipfile,json; ..."` ต้องเป็นเวอร์ชันใหม่
- [ ] อัป patch_lite + patch_full + version.json ขึ้น GitHub พร้อมกัน
- [ ] อัปเดตชื่อ release title
- [ ] ทดสอบ: โหลด version.json จาก GitHub ตรวจเป็นเวอร์ชันใหม่
- [ ] แจ้ง user รอ 5 นาที (CDN propagation) ก่อนทดสอบอัปเดต
