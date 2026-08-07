# Broadcast Playroom — Project Notes

คู่มือการพัฒนา ปัญหาที่เจอ + วิธีแก้ สำหรับ session ถัดไป

---

## สถานะปัจจุบัน (v1.8.17)

### ฟีเจอร์หลัก
- TTS: edge-tts (Premwadee) + RVC voice conversion (Full only)
- Mixed Voice TTS: หลายเสียงอ่านต่อกันในประโยคเดียว
- Auto Translate: Google / DeepL / DeepSeek v4-flash
- 5 แพลตฟอร์ม (default 3: Twitch/YouTube/MyLive)
- Chat Overlay (OBS) + Game Overlay + Playroom + Overlay+
- Event system + Notification
- NG-Replace 2 คอลัมน์ + User Manager + Channel Points
- Auto-update (4 layer fallback + retry)
- Settings auto-save (debounce 500ms)
- Splash screen (ขั้นต่ำ 2.5s)
- prefix อัตโนมัติ (! โค้ดลับ, # Playroom)
- Plugin System (command config-only + abstract classes)
- Log rotation (10 ครั้ง + crash.log)
- **Viewer Interaction Commands** ([x2]/[p1]/[v50] — ควบคุม speed/pitch/volume จาก chat, default OFF)
- **Voice Downloader** — 85 curated models (Genshin/VTuber/อื่นๆ) พร้อม cache
- **Overlay Themes** — 46+ themes (Pip-Boy, Sakura, Retro RPG, ฯลฯ)

---

## Plugin System

### ไฟล์หลัก
| ไฟล์ | หน้าที่ |
|---|---|
| `plugin_loader.py` | PluginLoader — โหลด plugins/commands/*.yml |
| `plugin_api.py` | Abstract classes: TTSEngine, PlatformClient, CommandHandler |
| `PLUGIN_DEV.md` | คู่มือนักพัฒนา plugin (API reference ครบ) |
| `plugins/README.md` | คู่มือผู้ใช้ (วิธีสร้าง command plugin) |
| `plugins/commands/*.yml` | ตัวอย่าง plugin (!hi, !time) |

### สถานะ
- ✅ Command plugin (config-only) — โหลด YAML, ตรวจ trigger, ตอบกลับ
- ✅ Abstract classes — TTSEngine, PlatformClient, CommandHandler
- 🔜 Wire เข้า TTS pipeline (ยังไม่ได้เชื่อม on_message)
- 🔜 Settings > Plugins tab
- 🔜 TTS engine plugin support
- 🔜 Platform plugin support

---

## สถาปัตยกรรมสำคัญ

### Message Flow
```
chat_client → on_message callback → _msg_buffer (thread-safe)
→ _poll_ui_updates (200ms, main thread)
→ _normalize_event_text(msg) [events → msg.text = "MeN9CH ให้ซับช่อง"]
→ _add_chat_row(msg) [Live Chat]
→ overlay push [OBS + Game] (หน่วงถ้า _will_be_translated)
→ notification.handle(msg) [events → เสียง + TTS]
   หรือ pipeline.enqueue(msg) [message → TTS]
```

### Translation Flow (โหมดแปล)
```
pipeline.enqueue(msg)
→ text_filter.filter_text (replace ก่อนแปล)
→ _maybe_translate (Google/DeepL/DeepSeek)
→ msg.text = translated + msg.extra["translated"] = True
→ on_translated callback
  → _rerender_all_chat_rows() [Live Chat]
  → overlay push (คำแปล) [OBS + Game]
→ _build_speak_text → edge-tts → play
```

### Overlay Push Flow (โหมดแปล)
```
poll loop → _will_be_translated(msg)?
├── ใช่ → ข้าม push (รอ on_translated)
│        → on_translated → push คำแปล
└── ไม่ → push ทันที (ไทย/emote-only/unknown)
```

### Mixed Voice Flow
```
_compute_one → _use_mixed (multilang + not translate)
→ _synth_mixed_voice(text)
  → แยก segment ตาม Unicode script (language_detect._char_lang)
  → TTS แต่ละ segment ด้วย voice ของภาษานั้น
  → trim trailing silence
  → concat ด้วย gap 50ms
  → (1 segment ที่ไม่ใช่ไทย → synth ด้วย voice นั้น)
→ RVC convert ถ้ามี
→ play
```

### Update System
```
updater.py → check_for_update() → fetch_remote_version()
  → 4 layer fallback: requests → urllib(win cert) → urllib(default) → urllib(unverified)
  → retry 2 ครั้ง + timeout 20s
→ compare versions → download_file (3 layer fallback เหมือนกัน)
→ apply_patch (bat script): stage in install_dir → wait exe close → xcopy → restart
→ GitHub: zepiam/broadcast-playroom/releases/tag/latest
```

### Settings Auto-Save Flow
```
widget toggle → command=self._auto_save
→ debounce 500ms → _commit_settings() [commit + apply, ไม่ destroy]
→ save_settings(self.settings)
(ผู้ใช้ยังอยู่ใน dialog ได้)

ปิด dialog → _on_dialog_close → _on_save
→ _commit_settings() + save_settings + self.destroy()
```

### Overlay+ Architecture
```
app_gui.py (TTSForLivestreamApp)
├── self.more_overlays: list[MoreOverlay]  (0-3 instances)
├── _toggle_more_overlays() — เปิด/ปิด ทั้งหมด (kill process)
├── _open_all_more_overlays() — spawn จาก settings (เฉพาะ enabled=True)
├── _toggle_mo_edit_from_menu() — ส่ง edit_toggle ให้ Qt toggle เอง
├── _save_more_overlay_position() — บันทึกตำแหน่งลง settings
└── _show_more_overlay_menu() — dropdown ▾ (Edit Mode + Settings)

game_overlay.py
├── class MoreOverlay — คัดลอกจาก GameOverlay แต่:
│   ├── รับ url + overlay_id + geometry
│   ├── queue file แยก: game_overlay_cmd_queue_{id}.json
│   ├── ไม่มี server (URL ภายนอก)
│   └── เคลียร์ queue ทุกครั้ง (start + stop)
└── class GameOverlay — เดิม (unchanged)

game_overlay_qt.py
├── --url + --id + --mode overlay+ + --hk-toggle + --hk-edit
├── _OVERLAY_ID global → queue file suffix
├── _send_to_parent() → file queue (ไม่ใช้ stdout)
├── edit_toggle command → Qt toggle เอง
└── Overlay+ mode: hint text แทนปุ่ม
```

---

## ปัญหาที่เจอ + วิธีแก้

### Session 1 (v1.0.0 → v1.5.0)

#### 1. Live Chat ข้อความไม่เต็มความกว้าง (wraplength)
**สาเหตุ:** `_rewrap_chat` + binding `<Configure>` ทุก row → overwrite wraplength
**แก้:** ลบ `_rewrap_chat` ใช้ inline `max(200, width - 40)`

#### 2. Translation ไม่แสดง realtime
**สาเหตุ:** `_swap_main_text_to_translation` หา label ไม่เจอ
**แก้:** `_rerender_all_chat_rows()` — ล้าง + re-render ทั้งหมด

#### 3. Settings dialog ปิดตัวเอง (FocusOut)
**แก้:** ลบ `<FocusOut>` binding

#### 4. Notification toggles ไม่เซฟ
**แก้:** เพิ่ม read_* ใน to_dict + from_dict + _commit_notif_config

#### 5. Event อ่านเบิ้บ (SuperChat อ่าน 2 รอบ)
**แก้:** ใช้ msg.text ที่ normalize แล้ว

#### 6. Events ไม่เคารพ read_event_text
**แก้:** เปลี่ยนเงื่อนไขจาก `in _NOTIF_EVENT_MAP` → `event not in ("message", "system")`

#### 7. Event list ลำดับผิด + กระพริบ
**แก้:** re-render ทั้งหมด + `reversed(entries)`

#### 8. RVC "Numpy is not available"
**แก้:** `pip install "numpy<2"`

#### 9. voice referenced before assignment
**แก้:** เพิ่ม `voice = "th-TH-PremwadeeNeural"` ใน fallback

#### 10-16. บัคเล็กๆ (splash, docstring, ffmpeg, force_translate, Channel Points)
**ดูรายละเอียดใน git log**

---

### Session 2 (v1.5.0 → v1.7.0)

#### 17. User Manager ประวัติข้อความเรียงผิดลำดับ
**แก้:** `entries[-take:]` = ใหม่สุด N → reverse → ใหม่สุดบนสุด

#### 18. User Manager ไม่อัพเดท history
**แก้:** 🔄 Refresh button + auto-refresh ตอน focus (throttle 3 วิ)

#### 19. Overlay ▾ ไม่มี dropdown
**แก้:** `_show_overlay_menu` (tk.Menu popup)

#### 20. Overlay ▾ OFF แล้ว 3 ข้อบนคลิกได้
**แก้:** state="disabled" + "(ปิดอยู่)" + สีจาง

#### 21-22. กระดิ่ง (ซ่อน/แสดง)
**แก้:** ไม่ pack ตอน init + `winfo_manager()` ตรวจสถานะ

#### 23. Tooltip ไม่ครบ
**แก้:** `_make_split_button` คืน 3-tuple + bind tooltip แยก

#### 24. NG-Replace เรียงบนลงล่าง
**แก้:** grid 2 คอลัมน์ (weight 2:3)

#### 25. Tab Setting รก
**แก้:** รวม Blocklist เข้า Spam → "🛡️ Spam & Block" + เพิ่ม tab TTS

#### 26. prefix ไม่ default
**แก้:** `!` สำหรับ secret_code, `#` สำหรับ playroom + migrate

#### 27. ญี่ปุ่นล้วน → error "No audio"
**แก้:** 1 segment ที่ไม่ใช่ไทย → synth ด้วย voice ของภาษานั้น

#### 28. ภาษาที่ไม่รู้จัก → error
**แก้:** `_char_lang` ตรวจ ASCII เท่านั้น + `detect_language` คืน "unknown" + guard ทุกโหมด

#### 29. TTS error ตอนแปล fail/same
**แก้:** translated == msg.text และไม่ใช่ไทย → skip TTS

#### 30. CJK wrap ตัดกลางคำ
**ลอง:** ZWSP → ทำให้ตัดเร็ว → **ถอน** ปล่อย Tk ตัดกลางคำ

#### 31. emote + translate → emote ทับ
**แก้:** `emotes=None` ตอน is_translated

#### 32. overlay ต้นฉบับซ้อน 2
**แก้:** ข้าม branch twitch_emotes ตอน is_translated

#### 33. ไทย/emote-only ไม่แสดงใน overlay (โหมดแปล)
**แก้:** `_will_be_translated()` ทำนาย → push ทันทีถ้าไม่แปล

#### 34. abc icon ซ่อนเมื่อ multilang
**แก้:** ลบ `pack_forget` → แสดงตลอด + dynamic tooltip

#### 35-37. บัคเล็ก (NameError, auto-save, widget order)
**แก้:** ดูในรายละเอียด git log

---

### Session 3 (v1.7.0 → v1.8.7)

#### 38. แพลตฟอร์ม default รก
**แก้:** show_tiktok/show_kick = False → เหลือ 3

#### 39. auto-save dead code
**แก้:** wire `_auto_save` เข้าทุก checkbox/menu/slider

#### 40. ระบบอัพเดท fail บนเครื่องอื่น
**สาเหตุ:** requests ไม่ bundle + SSL cert + urllib redirect
**แก้:** bundle requests + 4 layer fallback + Windows cert + retry

#### 41. download_file ใช้แค่ urllib
**แก้:** 3 layer fallback เหมือน fetch_remote_version

#### 42. Windows Defender ลบ exe
**แก้:** ย้าย staging จาก %TEMP% → install_dir + บอก Add Exception

#### 43. auto-save ปิด dialog ทันที
**แก้:** แยก `_commit_settings` (ไม่ destroy) จาก `_on_save` (destroy)

#### 44. Settings เปิดช้า
**แก้:** deferred tab build (after 50ms)

#### 45. โหลด RVC ช้าตอนเปิด
**แก้:** lazy import + find_spec("torch")

#### 46. เปลี่ยนโมเดลเสียงนาน
**แก้:** HuBERT cache + warm-up ครั้งเดียว

#### 47. splash กะพริบ 0.5 วิ
**แก้:** ขั้นต่ำ 2.5 วิ

#### 48. segments แสดงต้นฉบับตอนแปล
**แก้:** `if segments and not is_translated`

#### 49. MyLive Chromium download เงียบ
**แก้:** stream output + on_status callback + progress

#### 50. edit toggle ต้องกด 2 ครั้ง
**แก้:** `edit_toggle` command → Qt toggle เอง

#### 51. Theme selector หายตอน switch mode
**แก้:** `pack(before=self._ov_content_card_parent)`

#### 52. Balloon มีเงาจาก Default
**แก้:** `!important` ใน text-stroke + text-shadow

#### 53. User Manager rename ไม่มี TTS checkbox
**แก้:** เพิ่ม checkbox + ปุ่มลบการเปลี่ยนชื่อ

#### 54. preview TTS crash
**แก้:** หยุด preview เก่าก่อนเริ่มใหม่ + _preview_stop flag

#### 55. log เขียนทับ
**แก้:** rotation 10 ครั้งใน logs/ + crash.log

#### 56. Platform Modal หน้าเปล่า
**แก้:** ใช้ `font()` + `COLOR_BG` ที่ถูกต้อง

---

## ข้อจำกัดที่รู้ (ไม่ได้แก้)

1. **Channel Points** — Anonymous IRC เห็นเฉพาะ text-prompt reward
2. **CJK wrap** — ตัดกลางคำ (Tk limitation)
3. **Antivirus false positive** — PyInstaller exe + Add Exception
4. **emote + translate** — emote หายจากข้อความที่แปล
5. **Code signing** — ไม่มี certificate → SmartScreen warning
6. **Overlay+ Edit Mode ปุ่ม** — click-through กัน → ใช้ hint text + hotkey แทน

---

## Build & Release

### Build
```bash
python -m PyInstaller tts_lite.spec --noconfirm
python -m PyInstaller tts_full.spec --noconfirm
```

### Pack + Upload
```bash
cp version.json "dist/Broadcast Playroom Lite/_internal/version.json"
cp version.json "dist/BroadcastPlayroom_Full/_internal/version.json"
python build_patch.py patch lite
python build_patch.py patch full
python build_patch.py version
cp release/remote_version.json release/version.json

gh release edit latest --repo zepiam/broadcast-playroom --title "vX.Y.Z" --notes "..."
gh release upload latest release/version.json release/patch_lite.zip release/patch_full.zip --repo zepiam/broadcast-playroom --clobber
```

### สำคัญ
- numpy < 2 (torch compatibility)
- `collect_submodules('requests')` + `('urllib3')` ใน spec
- ต้อง copy version.json ไป dist ก่อน pack

---

## Token / Credentials

- GitHub PAT: เก็บใน Windows credential store (gh auth login --with-token)
- DeepSeek API: ผู้ใช้ใส่เองใน Settings
- Google Translate: ฟรี ไม่ต้อง key

---

## ไฟล์หลัก

| ไฟล์ | ที่หน้าที่ |
|------|---------|
| `app_gui.py` | Main GUI (~11000+ lines) |
| `chat_queue.py` | TTS pipeline + Mixed Voice + translation |
| `settings.py` | AppSettings dataclass |
| `notification_manager.py` | Event notification + sounds |
| `translator.py` | Google/DeepL/DeepSeek |
| `language_detect.py` | Unicode script detection + VOICE_BY_LANG |
| `event_log.py` | Event history + filter |
| `user_manager.py` | User management dialog |
| `text_filter.py` | NG words + Replace patterns |
| `chat_twitch.py` | Twitch IRC client |
| `overlay_server.py` + `overlay.html` | OBS overlay |
| `game_overlay.py` + `game_overlay_qt.py` | Game Overlay + Overlay+ |
| `game_overlay.html` | Game overlay web page |
| `splash.py` | Splash screen |
| `updater.py` | Auto-update (4 layer fallback) |
| `build_patch.py` | Release packer |
| `plugin_loader.py` | Plugin loader (command config-only) |
| `plugin_api.py` | Abstract classes (TTSEngine, PlatformClient, CommandHandler) |
| `FAQ.md` | คู่มือแก้ปัญหาผู้ใช้ |
| `PLUGIN_DEV.md` | คู่มือนักพัฒนา plugin |
| `PROJECT_NOTES.md` | ไฟล์นี้ (dev notes) |

---

## Version History

| Version | Highlights |
|---------|-----------|
| v1.0.0 | เริ่มต้น — TTS + 5 แพลตฟอร์ม + overlay |
| v1.5.0 | Mixed Voice + Event system + Translation + Auto-update |
| v1.6.0 | ระบบภาษาใหม่ (overlay แปล + unknown skip + abc icon) |
| v1.6.5 | ระบบอัพเดท 4 layer fallback + Windows cert |
| v1.7.0 | auto-save + Settings refactor + แก้ bug กระดิ่ง/CJK/overlay |
| v1.8.0 | Overlay+ (custom URL overlay) + edit toggle fix + segments fix |
| v1.8.3 | Platform Modal + Settings 865px + deferred build |
| v1.8.7 | Theme selector fix + Balloon shadow fix + Plugin System foundation |
