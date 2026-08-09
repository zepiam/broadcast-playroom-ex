# 📝 Developer Notes — Broadcast Playroom v2

> จดบันทึกการพัฒนา ปัญหาที่เจอ และวิธีแก้ เพื่อไม่ให้ลืม

---

## 🐛 ปัญหาที่เจอบ่อย + วิธีแก้ (สำคัญมาก)

### 1. QTimer.singleShot จาก background thread ไม่ทำงาน
**อาการ:** callback ไม่ทำงาน / UI ไม่อัปเดต จาก background thread
**สาเหตุ:** `QTimer.singleShot(0, fn)` ใน PySide6 ไม่ทำงานข้าม thread (ต่างจาก Tk `after()`)
**แก้:** ใช้ **Qt Signals** — class-level `Signal(type)` + `emit()` จาก thread + `connect()` ใน main thread
```python
class TTSForLivestreamApp(QMainWindow):
    _chat_message = Signal(object)
    _platform_error = Signal(str, str)
    _dl_progress = Signal(int)
    _dl_complete = Signal(bool, str)
    _catalog_ready = Signal(object)
```

### 2. QThread + run override ไม่ทำงาน
**อาการ:** emote ไม่โหลด
**สาเหตุ:** `thread.run = _run; thread.start()` รัน QThread default run (event loop) ไม่ใช่ `_run`
**แก้:** ใช้ **QNetworkAccessManager** (Qt built-in async HTTP, main thread event loop)

### 3. Game Overlay Settings — ค่า slider กลับเป็น 0 ทุกครั้ง
**ปัญหาใหญ่มาก** แก้หลายรอบ:
1. **`_build_ui` trigger `_save_mode_config` ก่อน `_load_values`** → save ค่า slider ที่เป็น raw 0 → ทับค่าจริง
   - **แก้:** `self._loading = True` ก่อน `_build_ui()` → `_live_update()` เช็ค `_loading` → skip
   - ตั้ง `self._loading = False` หลัง `_load_values()` เสร็จ
   - ตั้ง `self._loading = True` รอบ `_load_mode_config()` ใน `_on_appearance_change()` ด้วย

2. **slider `.value()` เป็น raw value ไม่ใช่ real value**
   - slider range 10-64 → `.value()` คืน 0-54 (offset by lo)
   - **แก้:** `_get_slider_real(slider)` = `lo + value/scale` (float) หรือ `lo + value` (int)

3. **`isVisible()` ไม่เช็ค parent chain**
   - widget อยู่ใน QFrame card ที่ซ่อน → `widget.isVisible()` คืน True!
   - **แก้:** `_is_really_visible(widget)` — เดิน parent chain ขึ้นไปเช็ค `isHidden()` ทุกตัว

4. **float slider ไม่มี `step` → range ผิด**
   - `is_float=True, step=1` (default) → `scale=1` → `setMaximum(int(0.9*1)) = 0` → slider ลากไม่ได้
   - **แก้:** `step=0.01` → `scale=100` → range ถูกต้อง

5. **3 sliders ใช้ key `"game_overlay_font_size"` ซ้ำกัน**
   - `font_size_sld`, `sp_font_size_sld`, `char_font_size_sld` — `_on_change` เขียน flat settings ทับกัน
   - **แก้:** sp + char ใช้ `key=None` → `_on_change` ไม่เขียน flat (mode-specific เท่านั้น)

6. **mode_configs ไม่ sync กลับไป flat settings**
   - `_save_mode_config` save ลง `cfg[key]` แต่ `_load_values` อ่านจาก flat → ค่าไม่ตรง
   - **แก้:** `_save_slider` sync ไป `settings.game_overlay_{key}` ด้วย

7. **`_build_config` ใน server อ่านจาก flat settings ไม่ใช่ mode_configs**
   - ทุก mode ใช้ค่าเดียวกัน
   - **แก้:** `mc_get(key, flat_key, default)` — อ่านจาก `mode_configs[appearance_mode]` ก่อน → fallback flat

8. **`_load_values._mc()` fallback chain**
   - special/character mode ไม่มี field `emote_size` → fallback flat (อาจเป็น 0)
   - **แก้:** fallback chain: cur_cfg → default_cfg → flat settings

9. **mode_configs เสียจากการ save ผิดซ้ำๆ**
   - **แก้:** clean mode_configs (ลบ fields ที่ไม่ควรอยู่ใน special/character) + fix ค่าใน settings.json

### 4. Theme CSS ค้างเมื่อสลับเป็น default
**อาการ:** สลับจาก Theme → Default แล้วยังเป็นสี Theme เดิม
**สาเหตุ:** CSS variables (`--box-bg`, `--text-shadow`) ที่ Theme CSS ตั้งไว้ไม่ถูก reset
**แก้:** เมื่อ `theme_css` ว่าง → `removeProperty()` ทุก CSS variable ที่ theme ตั้งไว้ (ทั้ง game_overlay.html + overlay.html)

### 5. Balloon (Special Overlay) โปร่งใส ไม่มีพื้นหลัง
**สาเหตุ:** 
1. `_save_mode_config` save `balloon_bg_opacity` โดยหาร 100 (`slider.value() / 100.0`) ทั้งที่ slider เป็น float 0.1-1.0 → ค่ากลายเป็น 0.0095
2. Theme CSS variables (`!important`) ทับ balloon background
**แก้:**
1. ลบ `/ 100.0` — slider value เป็น float อยู่แล้ว
2. `#chat.mode-balloon` reset ทุก theme variable (`--box-bg: transparent !important`, ฯลฯ) + `!important` บนทุก property ของ balloon

### 6. Viewer Overlay กดซ้อนทำหน้าต่างเบิ้ล
**สาเหตุ:** toggle เช็ค `is_running` (`_proc.poll()`) — แต่หลัง `stop()` → `_proc` อาจยังไม่ None ทันที
**แก้:** เช็ค `_viewer_overlay is not None` แทน `is_running` + double-check ใน background thread

### 7. Viewer count แสดง 0 ใน overlay
**สาเหตุ:** `_viewer_counts` ว่างเพราะ chat clients ยังไม่ได้ส่ง viewer count มา (Twitch poll ~30s)
**แก้:** ส่ง `chat_clients.keys()` ทั้งหมดไป composer (แม้ count=0) → overlay แสดง platform icons ทันที

### 8. File-based queue race condition (Game Overlay / Overlay+ commands)
**อาการ:** ปุ่ม edit/toggle ใน overlay ไม่ทำงาน / command หาย
**สาเหตุ:** parent + Qt subprocess อ่าน/เขียน queue file พร้อมกัน → file กลายเป็น empty/corrupt → `json.load` พัง
**แก้:** atomic write (`tempfile.mkstemp` + `os.replace`) + tolerant JSON parse (`try/except json.JSONDecodeError`)

### 9. Block user ไม่ทำงาน (TTS ยังอ่าน)
**สาเหตุ:** `_block_user_from_chat` เพิ่มชื่อลง `settings.blocked_users` แต่ไม่ได้ `pipeline.set_filter()` → pipeline ใช้ filter เดิม
**แก้:** หลังเพิ่ม → `pipeline.set_filter(settings.to_text_filter())` ทันที + เก็บเป็น dict format `{"name": ..., "hide_overlay": bool}`

### 10. Emoji ไม่แสดงในปุ่ม QPushButton
**สาเหตุ:** `setStyleSheet("color: #ef4444; ...")` override สี emoji → emoji ถูกบีบเป็นสีเดียว
**แก้:** ไม่ใส่ `color:` ใน styleSheet ของปุ่มที่มี emoji → ใช้ `background-color` + `padding: 0px` เท่านั้น

### 11. Settings dialog แสดงผลบีบ/crash
**สาเหตุหลายอย่าง:**
- `_collect_values` อ้างถึง widget ที่ไม่มี → AttributeError
  - **แก้:** `hasattr(self, 'xxx')` ทุกที่
- QScrollArea + QStackedWidget + setVisible → layout ไม่คำนวณ
  - **แก้:** `_ConstrainedScrollArea` (override resizeEvent) + `setMaximumWidth(viewport.width)`
- การย้าย layout ภายหลัง (`existing_widget.setLayout(layout)`) → Qt สับสน
  - **แก้:** สร้าง layout structure ตั้งแต่ต้น ไม่ย้าย

---

## 🏗️ สถาปัตยกรรมสำคัญ

### Game Overlay Settings — mode_configs
แต่ละ appearance mode (default/theme/special/character) เก็บ styling ของตัวเองแยกอิสระ:

```python
game_overlay_mode_configs = {
    "default": { font_size, emote_size, text_color, box_*, ... },
    "theme": { theme, custom_css, box_bg_opacity },
    "special": { font_size, font_family, text_color, balloon_*, ... },
    "character": { font_size, font_family, text_color, text_shadow },
}
```

**Flow:**
1. `_build_config()` (server) → `mc_get(key, flat_key, default)` อ่านจาก `mode_configs[appearance_mode]` ก่อน → fallback flat
2. `_load_values()` (dialog) → `_mc(key, flat_key, default)` chain: cur_cfg → default_cfg → flat
3. `_save_mode_config()` → save visible widgets → `cfg[key]` + sync flat
4. `_on_appearance_change(mode)` → `_loading=True` → `_load_mode_config(mode)` → `_loading=False`

### SplitButton widget
`ui/widgets/split_button.py` — 2 QPushButton (main + arrow) ใน QHBoxLayout:
- ไม่ใช้ QToolButton (มีปัญหากับ emoji)
- state: `""` (default), `"on"` (accent), `"danger"` (red), `"warning"` (amber)
- QSS: `QPushButton#SplitButtonMain[state="on"]` + `QPushButton#SplitButtonArrow[state="on"]`

### File structure
```
ui/
├── theme.py                    — QSS + colors + fonts
├── platform_icons.py           — QPixmap cache (assets/*.png)
├── widgets/
│   ├── sidebar.py              — PlatformCard + Sidebar
│   ├── chat_panel.py           — chat feed + header (A-/A+/🔔/🎟/🗑/⚙/↗)
│   ├── chat_row.py             — ChatRow (emote/icon/zebra)
│   ├── events_panel.py         — collapsible events
│   ├── topbar.py               — TopBar (6 SplitButtons + Settings)
│   ├── status_bar.py           — bottom status
│   └── split_button.py         — reusable SplitButton
├── dialogs/
│   ├── settings.py             — SettingsDialog (sidebar layout, auto-save)
│   ├── game_overlay_settings.py — GameOverlaySettingsDialog (tabs: Game + Viewer)
│   ├── live_chat_settings.py   — LiveChatSettingsDialog (split: settings | preview)
│   ├── ngreplace.py            — NG-Replace editor
│   ├── voice_downloader.py     — RVC voice catalog + download
│   ├── hotkey_binder.py        — press-to-capture hotkey button
│   ├── popout.py               — Popout chat window
│   ├── user_manager.py         — User manager
│   └── viewer_profile.py       — Viewer profile
```

---

## 📋 TODO / ยังไม่ได้ทำ

- [ ] PyInstaller spec สำหรับ PySide6
- [ ] Auto-update system
- [ ] OBS WebSocket integration
- [ ] Character Talk — job change system (browse character images)
- [ ] Playroom trigger clips — browse video files
- [ ] Notification sound settings (per-platform per-event)
- [ ] Settings dialog notifications section → wire to NotificationConfig

---

## 🔑 Key Patterns (จำไว้!)

1. **Thread-safety:** ใช้ Qt Signals เสมอ ไม่ใช้ QTimer.singleShot จาก background thread
2. **Slider values:** `.value()` เป็น raw → ต้องแปลงผ่าน `_get_slider_real()`
3. **Mode configs:** แต่ละ appearance mode แยก styling → save/load ต้องใช้ `_is_really_visible()` + `_loading` flag
4. **Emoji buttons:** ไม่ใส่ `color:` ใน styleSheet
5. **File queue:** atomic write (temp + os.replace) + tolerant JSON parse
6. **Settings auto-save:** `_collect_values()` + `hasattr()` guards + `_auto_save()` → `save_settings()` + `settings_changed.emit()`
7. **Composer overlay URL:** `/editor` (editor mode) vs `/` (OBS overlay)

## Plugin System Investigation (2026-08-09)

### Architecture tested:
```
Broadcast Playroom/
├── exe + _internal/    (PyInstaller bundle ~1GB)
└── site-packages/      (torch + omnivoice + rvc ~9GB, external)
```

### What works:
- ✅ torch import from site-packages (with stdlib in hiddenimports + rthook stub removal)
- ✅ numpy import from site-packages
- ✅ App runs without crash
- ✅ Build is fast (~2 min, no torch rebuild)

### What DOESN'T work:
- ❌ `import omnivoice` → PyInstaller's lazy import stubs intercept transformers
  - `AutoFeatureExtractor`, `GenerationMixin`, etc. are stub objects → import fails
  - `importlib.invalidate_caches()` doesn't help
  - Deleting from sys.modules doesn't help (PyInstaller re-creates stubs)
- ❌ PyInstaller's import system overrides Python's import system completely
  - Even with site-packages in sys.path[0], PyInstaller's frozen importer wins
  - `transformers` is too complex (500+ submodules) → stubs everywhere

### Root cause:
PyInstaller creates a **custom import hook** that intercepts ALL imports in frozen exe.
When `transformers` is in `excludes`, PyInstaller creates lazy stub objects for its submodules.
These stubs return fake objects → `hasattr(fake, 'AutoFeatureExtractor')` → fails.
Even after `del sys.modules['transformers']`, PyInstaller's meta_path finder recreates the stub.

### Conclusion:
**PyInstaller + external transformers/omnivoice = NOT POSSIBLE**
The only options are:
1. Bundle everything in PyInstaller (Full build ~7GB) — works but slow to rebuild
2. Use Embedded Python instead of PyInstaller — possible but complex
3. Use a separate Python process for TTS — possible but complex
4. Keep Lite + Full builds as before (current approach)

### Files created during investigation (can be kept or removed):
- `tts_playroom.spec` — plugin system spec (doesn't work with transformers)
- `rthook_site_packages.py` — runtime hook for site-packages path
- `build_playroom.bat` — build script (concept)
- `engine_plugin_loader.py` — plugin detection system (works for simple modules)

---

## 🔧 PyInstaller + OmniVoice: HiggsAudioV2TokenizerModel Fix (2026-08-10)

### ปัญหา
Full build exe: OmniVoice โหลดไม่สำเร็จ ขึ้น "OmniVoice ไม่พร้อมใช้งาน"
Dev mode: ทำงานปกติ

### สาเหตุจริง (3 ชั้น ซ้อนกัน)

#### ชั้นที่ 1: `torchcodec` metadata หาย (ตัวการหลัก)
```
transformers/audio_utils.py บรรทัด 61:
  TORCHCODEC_VERSION = version.parse(importlib.metadata.version("torchcodec"))
                                              ↑
                  PackageNotFoundError: No package metadata was found for torchcodec
                                              ↓
cascade → HiggsAudioV2TokenizerModel import fail → OmniVoice not available
```
PyInstaller bundle โค้ด `.py` แต่ไม่ bundle package metadata ของ `torchcodec`
เพราะไม่ได้ติดตั้งจริง → `importlib.metadata.version("torchcodec")` พ่น error

#### ชั้นที่ 2: transformers `_LazyModule` พัง
`_LazyModule._get_module` ใช้ relative import:
```python
importlib.import_module("." + module_name, self.__name__)
```
ใน PyInstaller relative import บางครั้งพัง เพราะ path resolution เปลี่ยน

#### ชั้นที่ 3: HiggsAudioV2 ไม่ได้ลงทะเบียนใน transformers AutoMap
transformers ใช้ AutoMap registry → PyInstaller ทำให้การลงทะเบียนอัตโนมัติพัง

### วิธีแก้ (ทั้งหมดอยู่ใน `main.py` module-level)

#### 1. Stub `importlib.metadata` สำหรับ torchcodec
```python
import importlib.metadata as _meta
_orig_version = _meta.version
def _safe_version(name):
    try:
        return _orig_version(name)
    except _meta.PackageNotFoundError:
        if name in ("torchcodec",):
            return "0.0.0"  # stub
        raise
_meta.version = _safe_version
```

#### 2. Register HiggsAudioV2 class เข้า transformers AutoMap
```python
from transformers.models.higgs_audio_v2_tokenizer.modeling_higgs_audio_v2_tokenizer import HiggsAudioV2TokenizerModel
from transformers.models.higgs_audio_v2_tokenizer.configuration_higgs_audio_v2_tokenizer import HiggsAudioV2TokenizerConfig
from transformers import AutoConfig, AutoModel
AutoConfig.register("higgs_audio_v2_tokenizer", _HiggsConfig)
AutoModel.register(_HiggsConfig, _HiggsModel)
# inject เข้า sys.modules ด้วยชื่อสั้น
import sys
sys.modules["modeling_higgs_audio_v2_tokenizer"] = _mod_module
```

#### 3. Monkey-patch `_LazyModule._get_module`
```python
from transformers.utils.import_utils import _LazyModule
def _patched_get_module(self, module_name):
    try:
        return importlib.import_module("." + module_name, self.__name__)
    except Exception:
        full_name = f"{self.__name__}.{module_name}"
        return importlib.import_module(full_name)
_LazyModule._get_module = _patched_get_module
```

### ไฟล์ที่เกี่ยวข้อง
| ไฟล์ | การเปลี่ยนแปลง |
|------|----------------|
| `main.py` | 3 patches ที่ module-level (ทำงานก่อน import omnivoice) |
| `omnivoice_engine.py` | `is_omnivoice_available` bypass ใน frozen exe + import HiggsAudioV2 จาก full path |
| `tts_full.spec` | เพิ่ม hiddenimports สำหรับ higgs_audio_v2_tokenizer |

### ถ้าเจอปัญหานี้อีก (debug steps)
1. ดู log: `~/.tts-for-livestream/app_v2.log`
2. ค้นหา `HiggsAudioV2TokenizerModel` หรือ `torchcodec`
3. ถ้าเจอ `PackageNotFoundError: No package metadata was found for torchcodec`:
   - เช็คว่า `main.py` มี stub `importlib.metadata` อยู่
4. ถ้าเจอ `Could not import module 'HiggsAudioV2TokenizerModel'`:
   - เช็คว่า `main.py` มี register AutoMap + patch `_LazyModule`
5. ถ้าเจอ `Could not import module 'modeling_higgs_audio_v2_tokenizer'`:
   - เช็คว่า `tts_full.spec` มี hiddenimports สำหรับ higgs_audio_v2_tokenizer

### สถานะ
- Full exe: OmniVoice + RVC ทำงานครบ ✅
- Dev mode: ทำงานปกติ ✅
- Lite build: ไม่มี OmniVoice (ไม่มีปัญหา) ✅

---

## 🔄 User Manager + Author Modal Redesign (2026-08-10) — IN PROGRESS

### เป้าหมาย
Redesign User Manager เป็น list + Author Modal แบบใหม่ที่รวม:
- สถิติ (ข้อความ + events + donate)
- Donation history (หน้าแยก แยกสกุลเงิน)
- Message history (load more ทีละ 20)
- Export log
- Block/unblock/rename

### ความคืบหน้า (บันทึกตอน context เต็ม)
- ✅ message_history.py — เพิ่ม `get_messages_by_author(author, limit=20, offset=0)` (pagination เรียงใหม่→เก่า)
- ✅ event_log.py — เพิ่ม `get_by_author(author)` (filter events by author)
- ✅ message_history.record() — แก่ bug ส่ง `msg` object → แก่เป็น `(author, platform, text)` (app.py:1148)
- ✅ event_log.record() — แก่สลับ author/event_type (app.py:1349)
- ✅ donate_tracker.record_donation() — แก่สลับ amount/platform/event (app.py:1355)
- ⬜ donate_tracker.py — เพิ่ม currency tracking (THB/USD/JPY/bit/diamond แยกกัน)
- ⬜ ui/dialogs/author_modal.py — สร้าง Author Modal ใหม่
- ⬜ ui/dialogs/user_manager.py — redesign เป็น list
- ⬜ app.py — เชื่อม modal ใหม่ + ส่ง currency

### ไฟล์ที่ต้องทำต่อ
1. donate_tracker.py — record_donation เพิ่ม param `currency` + เก็บยอดแยกสกุล
2. ui/dialogs/author_modal.py — AuthorModal class (รวม donate summary + history + load more + export)
3. ui/dialogs/user_manager.py — UserRow เป็น list แค่ name + stats + ปุ่มคลิก
4. app.py — _open_author_modal เรียก AuthorModal class ใหม่แทน inline code
5. app.py — _record_event ส่ง currency (bits→"bit", superchat→"THB", sub→"")

### Bug ที่แก้แล้ว (สำคัญ!)
- message_history.record() รับ `(author, platform, text)` ไม่ใช่ `msg` object
- event_log.record() ลำดับ `(platform, author, event_type, amount)` ไม่ใช่ `(platform, event_type, author, amount)`
- donate_tracker.record_donation() ลำดับ `(author, platform, event_type, amount)` ไม่ใช่ `(author, amount, platform, event_type)`

### APIs ที่ใช้ได้
- `message_history.get_messages_by_author(author, limit=20, offset=0)` → list[dict] เรียงใหม่→เก่า
- `message_history.count(author)` → int
- `message_history.all_authors()` → {author_lower: [entries]}
- `event_log.get_by_author(author)` → list[EventEntry]
- `event_log.get_all()` → list[EventEntry]
- `donate_tracker.get_user(author)` → {platform: {field: value}, total_donate_count: int}
- `donate_tracker.all_users()` → {author_lower: data}
