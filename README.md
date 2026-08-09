# 🎙️ Broadcast Playroom v2 (PySide6)

โปรแกรม TTS สำหรับอ่านแชทสดจาก Twitch / YouTube / MyLive / TikTok / KICK ด้วย edge-tts และ RVC voice conversion

> ⚠️ **v2.0.0** — เวอร์ชันพัฒนา (PySide6 migration)
> UI framework เปลี่ยนจาก customtkinter → PySide6 (Qt for Python)
> Logic เดิมทั้งหมด (TTS/RVC/chat/translation/overlay) ใช้ได้เหมือนเดิม

> **สำหรับผู้ใช้ทั่วไป** — ดาวน์โหลดเวอร์ชันเสถียรได้ที่ https://men9ch.com/broadcast-playroom/
> **v1 (เสถียร)** — https://github.com/zepiam/broadcast-playroom (main branch)

---

## 🔄 ความแตกต่างจาก v1

| ส่วน | v1 (customtkinter) | v2 (PySide6) |
|---|---|---|
| **UI Framework** | customtkinter (Tk) | PySide6 (Qt) |
| **Rendering** | Tk canvas (CPU) | Qt native (GPU accelerated) |
| **Minimize/Restore** | กระพริบดำ | ลื่นไม่กระพริบ |
| **Font** | มักเบลอ | คมชัด |
| **Thread-safety** | `self.after(0, fn)` | Qt Signals |
| **Threading** | raw threading + QTimer | QThread + Signals |
| **Layout** | pack/grid (Tk) | QHBoxLayout/QVBoxLayout/QSplitter |
| **Settings Dialog** | tabs (CTkTabview) | sidebar layout (QListWidget) |
| **File structure** | app_gui.py (~15000 lines) | แยก ui/widgets/ + ui/dialogs/ |

> ⚠️ v2 ใช้ logic (TTS/RVC/chat/translation/overlay/composer/playroom) ร่วมกับ v1 ทั้งหมด
> แก้เฉพาะส่วน UI เท่านั้น

---

## 📁 โครงสร้างโปรเจค

```
tts-for-livestream-ver2/
├── main.py                    # Entry point (QApplication + pygame.mixer.init)
├── app.py                     # TTSForLivestreamApp(QMainWindow) — main controller
├── ui/
│   ├── theme.py               # QSS stylesheet + color constants + fonts
│   ├── widgets/
│   │   ├── topbar.py          # Top bar (platform status + buttons + menu)
│   │   ├── sidebar.py         # Sidebar (platforms + voice + pitch + volume)
│   │   ├── platform_card.py   # (in sidebar.py — PlatformCard class)
│   │   ├── chat_panel.py      # Chat feed (QScrollArea + ChatRow)
│   │   ├── chat_row.py        # Chat message row (emote/segment/sticker rendering)
│   │   ├── events_panel.py    # Events panel (collapsible)
│   │   └── status_bar.py      # Bottom status bar
│   └── dialogs/
│       ├── settings.py        # Settings dialog (9 sections, sidebar layout)
│       ├── popout.py          # Popout chat window
│       ├── voice_downloader.py # RVC voice downloader
│       ├── user_manager.py    # User manager (rename/block/TTS mute)
│       ├── ngreplace.py       # NG-Replace editor (3-field table + wiki download)
│       ├── viewer_profile.py  # Viewer profile (history + block)
│       ├── playroom_trigger.py # Playroom trigger editor (clips + weight)
│       ├── game_overlay_settings.py # Game Overlay appearance settings
│       └── about.py           # About dialog (+ hidden Advanced Settings)
├── (logic files — shared with v1)
│   chat_twitch.py, chat_youtube.py, chat_mylive.py, chat_tiktok.py, chat_kick.py
│   chat_queue.py, settings.py, tts_engine.py, rvc_engine.py, translator.py
│   overlay_server.py, overlay.html, composer_server.py, composer.html
│   playroom.html, game_overlay.py, game_overlay_qt.py, game_overlay_server.py
│   game_overlay.html, viewer_overlay.html, now_playing.py, obs_refresh.py
│   text_filter.py, voice_downloader.py, emote_cache.py, message_history.py
│   event_log.py, donate_tracker.py, notification_manager.py, plugin_loader.py
│   ├── assets/                # icon + fonts + logo
│   ├── plugins/               # Plugin directory
│   └── version.json
```

---

## ⚡ สถาปัตยกรรมใหม่ (PySide6)

### Threading Model
| สถานการณ์ | v1 | v2 |
|---|---|---|
| Chat message → UI | `self.after(0, fn)` | `_chat_message.emit(msg)` (Signal) |
| Connect result | `self.after(0, fn)` | `_connect_result.emit(...)` (Signal) |
| RVC load done | `self.after(0, fn)` | `_rvc_loaded_sig.emit(...)` (Signal) |
| Translation done | `self.after(0, fn)` | `_msg_translated.emit(msg)` (Signal) |
| Viewer count | `self.after(0, fn)` | `_viewer_update.emit()` (Signal) |
| Game overlay cmd | file queue + `after()` | `_game_overlay_cmd_sig.emit(cmd)` (Signal) |
| Demo timer | `self.after(N, fn)` | `QTimer.singleShot(N, fn)` |
| Poll loop | `self.after(100, fn)` | `QTimer.start(100)` |

> ⚠️ **สำคัญ**: `QTimer.singleShot(0, fn)` จาก background thread **ไม่ทำงาน** ใน Qt
> ต้องใช้ Signal เสมอ (queued connection — thread-safe อัตโนมัติ)

### Layout System
- **QSplitter** — 3 columns (Sidebar | Chat | Events) + resize + persist
- **QVBoxLayout/QHBoxLayout** — แทน pack/grid
- **QScrollArea** — แทน CTkScrollableFrame
- **QTableWidget** — แทน Tk Treeview (NG-Replace + block list)

---

## ✨ ฟีเจอร์ที่ทำงานแล้ว

### Main Window
- ✅ TopBar (platform status dots + buttons + menu)
- ✅ Sidebar (platform cards + voice + pitch + volume + speed)
- ✅ ChatPanel (real-time + font A-/A+ + popout + clear + context menu)
- ✅ EventsPanel (collapsible + count)
- ✅ StatusBar

### Platform
- ✅ Connect/disconnect (Twitch/YouTube/MyLive/TikTok/KICK)
- ✅ Per-platform mute + volume
- ✅ Per-platform auto-connect + show/hide
- ✅ Auto-reconnect (backoff + manual flag)
- ✅ System messages (connect/disconnect/error)

### Chat
- ✅ ChatRow (emote/segment/sticker rendering — QNetworkAccessManager)
- ✅ Translation (original text below, green + flag)
- ✅ Context menu (delete / block all / block TTS)
- ✅ Author modal (rename / block / unblock / message history)
- ✅ Popout chat (copies messages + syncs)
- ✅ Font scale (A-/A+ — re-renders all rows)
- ✅ New messages at top

### TTS
- ✅ Pipeline (edge-tts + RVC + translation + multilang)
- ✅ RVC voice switching + auto-load (background thread)
- ✅ RVC pitch slider
- ✅ Voice test button
- ✅ Volume + speed sliders
- ✅ pygame.mixer.init() before QApplication (critical)

### Settings
- ✅ Sidebar layout (9 sections)
- ✅ Platforms (channel + auto-connect + show/hide per platform)
- ✅ TTS (volume/speed/read author/read message)
- ✅ Translate (radio: off/translate/multilang + language grid)
- ✅ Playroom (trigger editor + clips + weight)
- ✅ Canvas (port + open composer)
- ✅ Notifications (event checkboxes)
- ✅ NG-Replace (type + Enter → table + wiki download)
- ✅ Spam (type + Enter → block table + type dropdown)
- ✅ About

### Dialogs
- ✅ NG-Replace editor (3-field table + TTS preview + wiki download)
- ✅ Voice Downloader (search + category + download/delete)
- ✅ User Manager (rename + TTS name + block)
- ✅ Viewer Profile (history + block)
- ✅ Playroom Trigger (code + clips + browse + weight)
- ✅ Game Overlay Settings (appearance + demo + position)

### Servers (shared with v1)
- ✅ Composer server (Canvas Overlay — 8808)
- ✅ Overlay server (OBS Browser Source — 8765)
- ✅ Playroom server (8765)
- ✅ Now Playing watcher (Windows System Media)
- ✅ Game Overlay (subprocess — game_overlay_qt.py)

### Cross-thread Communication
- ✅ Chat messages → Signal → main thread
- ✅ Connect result → Signal → main thread
- ✅ RVC load → Signal → main thread
- ✅ Translation → Signal → main thread
- ✅ Game overlay commands → Signal → main thread
- ✅ Viewer counts → Signal → main thread

---

## ⚠️ ฟีเจอร์ที่ยังไม่สมบูรณ์ / ต้องแก้

### Emote Rendering (IN PROGRESS)
- 🔄 Chat emote loading — เปลี่ยนจาก QThread → QNetworkAccessManager
- 🔄 Game overlay emotes — ต้อง forward ผ่าน add_row
- 🔄 Emote Party widget — ทำงานผ่าน composer push_emote_party

### Game Overlay
- 🔄 Loop Demo toggle (เขียว→แดง)
- 🔄 Appearance settings (54 themes + mode + animation — copy from v1)
- 🔄 Edit mode (drag bar)

### Other
- 🔄 OBS WebSocket auto-refresh
- 🔄 Overlay+ (custom URL)
- 🔄 Advanced Settings (hidden)
- 🔄 PyInstaller spec (PySide6 build)
- 🔄 Auto-update system

---

## 🛠️ สำหรับนักพัฒนา

### วิธีรัน
```bash
cd tts-for-livestream-ver2
python main.py
# หรือ
run.bat
```

### Dependencies
```
PySide6
PySide6-WebEngine
pygame
edge-tts
aiohttp
requests
Pillow
numpy
torch (Full only — for RVC)
```

### Qt Signal Pattern (สำคัญ)
```python
# ❌ ผิด — QTimer.singleShot จาก background thread ไม่ทำงาน
def _bg():
    result = do_work()
    QTimer.singleShot(0, lambda: callback(result))  # DEAD

# ✅ ถูก — ใช้ Signal (thread-safe)
class App(QMainWindow):
    _result_sig = Signal(object)  # class-level signal
    def __init__(self):
        self._result_sig.connect(self._on_result)
    def _bg(self):
        result = do_work()
        self._result_sig.emit(result)  # queued connection → main thread
```

### QSS Theming
- Colors defined in `ui/theme.py` (color constants + QSS stylesheet)
- Placeholder pattern: `__BG__` → replaced with actual hex at runtime
- Apply: `apply_theme(app)` in `main.py`

### Layout Persistence
- Splitter sizes + events collapsed → `~/.tts-for-livestream/layout.json`

---

## 📝 TODO

- [ ] Emote rendering: QNetworkAccessManager (replace QThread)
- [ ] Game Overlay: full appearance settings (copy from v1)
- [ ] Game Overlay: Loop Demo toggle button
- [ ] Game Overlay: Edit mode
- [ ] OBS WebSocket integration
- [ ] Overlay+ (custom URL overlays)
- [ ] PyInstaller spec (PySide6)
- [ ] Auto-update system
- [ ] Build + release v2.0.0
