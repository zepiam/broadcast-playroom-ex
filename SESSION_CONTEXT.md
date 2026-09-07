# 🧠 SESSION CONTEXT — v2.7.1 dev (Save before compact)

> **อัปเดต**: 2026-08-18
> **สถานะ**: ✅ v2.7.1 RELEASED (2026-08-18 ~20:55) — https://github.com/zepiam/broadcast-playroom-ex/releases/tag/v2.7.1
> **งานใหม่หลัง 2.7.1**: ★ System message สรุปผลโหวต ASK หลายบรรทัด + โลโก้แพลตฟอร์มบรรทัดเดียว (แก้แล้ว — Lite rebuilt 22:36 พร้อมทดสอบ)
> **Build**: ✅ patch_lite 15.6MB + patch_full 67.3MB อัปโหลดแล้ว + version.json (rule 13: copy จาก remote_version.json) — checksum ตรง / data leak ไม่มี / composer.html ใน patch = ตัวล่าสุด

---

## 📦 เวอร์ชั่นปัจจุบัน

| | |
|---|---|
| **version.json** | 2.7.1 ✅ released |
| **GitHub** | v2.7.1 released |
| **Full exe** | `Broadcast Playroom Full.exe` |
| **Lite exe** | `Broadcast Playroom Lite.exe` |

### Release history (รอบนี้)
| เวอร์ชั่น | อะไร |
|---|---|
| 2.6.7 | Danmaku Chat + settings rework |
| 2.6.8 | Timer mode + layers + viewer + bug fixes (whitelist/font_family/theme) |
| 2.6.9 | Danmaku tools + UPDATE button + Full exe rename + migration |
| 2.7.0 | แก้บั๊ค Composer แสดงผล (beforeunload + text scroll + viewer theme) |
| 2.7.1 | ASK Widget + 21 bug fixes — ✅ released 18 ส.ค. |
| 2.7.2 | +สรุปผลโหวตใน Live Chat (โลโก้/หลายบรรทัด) + panel ASK ใหม่ (หลอด realtime/นับถอยหลัง/กรอกเวลา+หน่วย/400px) — ✅ released 18 ส.ค. (23:30) |

---

## ✅ งานที่เสร็จในรอบนี้ (หลัง 2.6.8)

### Danmaku Chat
- **}color{ command** — ผู้ชมพิมพ์ `}red{ข้อความ` / `}rainbow{hello` เปลี่ยนสี
  - 11 สี + rainbow (gradient วิ่ง)
  - ใช้ `}xxx{` แทน `[xxx]` (กันดักเจอข้อความธรรมดา)
  - TTS ไม่อ่าน (strip ผ่าน copy ไม่แตะ msg ต้นฉบับ)
  - **ใช้ได้เฉพาะ Danmaku เท่านั้น** (กฎข้อ 9)
- **ตำแหน่งแสดงแชท** — 6 โซน: บน 30% / ครึ่งบน 50% / กลาง 40% (default) / ครึ่งล่าง 50% / ล่าง 30% / สุ่มทั้งจอ
  - Padding กันติดขอบ (PAD = 60% ของ lane height)
- NOTE แนะนำเต็มจอตอนเลือก Danmaku

### Image & Slideshow — Timer Mode
- โหมด Timer: ภาพขึ้นมา-หายไปตามเวลา
- Animation เข้า/ออก 9 แบบ (fade + slide 4 ทิศ + มุมทแยง 4 มุม)
- Exit = กลับทางเดิมอัตโนมัติ (default) หรือเลือกเอง
- ปรับความเร็ว animation in/out แยก (ms)
- Progress bar นับเวลาใต้ภาพ
- ตั้งเวลารอบ (นาที หรือ วินาทีสำหรับเทส)
- ตั้งเวลาแสดงแต่ละภาพ (วินาที)
- ภาพสุดท้ายไม่วนกลับภาพ 1 ก่อนออก
- จำกัดอัปโหลด 3MB (เดิม 2MB)
- setTimeout chain (ไม่ใช้ setInterval — กัน drift)

### UPDATE Button
- ทรงแคปซูล + ไล่เฉดแนวตั้ง + ขอบโปร่งใส + shimmer (แสงขาววิ่งผ่าน) + เงาขาวกระพริบ
- ข้อความ: "NEW UPDATE v2.6.9"
- Mockup ลบแล้ว (dev mode return)

### Full exe rename + migration
- `BroadcastPlayroom_Full` → `Broadcast Playroom Full` (มีช่องว่าง)
- **Updater migration**: ตรวจ zip → เทียบชื่อ exe → ลบเก่า + รันใหม่
- **Startup migration (main.py)**: สแกน exe ใน install dir → สลับไปรันใหม่ + ลบเก่า
- `kill_playroom_process` รองรับ: exe (มี/ไม่มีช่องว่าง) + dev (wmic หา python.exe main.py)
- **Kill + Restart**: ปุ่ม "🔄 สั่งปิดและเปิดใหม่ทันที" ใน single-instance dialog

### Overlay layout หายหลังอัพเดท (บั๊กเมื่อกี้)
- **สาเหตุ**: auto-save debounce 200ms + ไม่มี save ตอนปิด browser
- **แก่**: `beforeunload` handler → `navigator.sendBeacon()` บังคับเซฟก่อนปิดหน้า
- (ยังไม่ได้ release — รอ 2.7.0)

### Text Widget — Scroll Loop fix (รอ 2.7.0)
- **แก้ flash ตอน reset**: CSS `left: 0` → `left: 100%` + `visibility:hidden` ระหว่างรอ + `rAF` ค่อยโชว์
- **เพิ่ม "Timing ในการเริ่ม Loop ข้อความ"**: slider 1-30 วิ (default 2) — หน่วงหลังข้อความออกจากจอก่อนเริ่มใหม่
- Server whitelist: `text_scroll_delay` (float 1-30)
- **แก้ "โผล่กลางจอตอนเริ่ม loop ใหม่"**: `.text-scroll .text-content` มี `width:100%` + inherit
  `justify-content:center` จาก base → ข้อความยาวกว่ากล่องถูกเซ็นเตอร์แล้วล้นสองข้าง → ตอน reset
  (`left=containerW`) ครึ่งส่วนล้นโผล่กลางจอทันที + `scrollWidth` วัดไม่ครบ (ส่วนล้นซ้ายไม่นับ)
  → แก้ด้วย `text-align:left; justify-content:flex-start` เฉพาะ scroll mode → เริ่มนอกจอขวาพอดี
  ไหลเข้ามาทีละน้อย และเงื่อนไขจบ loop (`scrollPos+textW<=0`) แม่นตรงเป๊ะ

### Viewer Widget หายตอนเปลี่ยน Theme (รวมใน 2.7.0 แล้ว)
- **อาการ**: เปลี่ยน Theme ยอดคนดู → widget หายจาก Composer + OBS ต้องรีเฟรช/ล้าง cache
- **สาเหตุ**: `updateWidgetElement` ล้าง children เมื่อ viewerSig เปลี่ยน แต่ `dataset.viewerHtml`
  (signature กัน flicker) ยังค้างค่าเดิม → `handleViewers` คำนวณ html ได้เท่าเดิม (เลขไม่เปลี่ยน)
  → เทียบ "เหมือนเดิม" → ข้ามเขียน → widget ว่างเปล่า ไม่กลับมาจนตัวเลขเปลี่ยนจริง
- **แก้ 2 จุดใน composer.html**:
  1. หลังล้าง children → `delete inner.dataset.viewerHtml` ก่อน re-render
  2. `handleViewers` guard เพิ่ม `|| !inner.firstElementChild` (DOM ว่าง → เขียนเสมอ)
- **ผล**: theme เปลี่ยนสดทันทีทั้ง Composer และ OBS (รับ config push ผ่าน WS อยู่แล้ว —
  OBS overlay = composer.html ตัวเดียวกันผ่าน `/`) ไม่ต้องรีเฟรชหรือล้าง cache
- (ทดสอบด้วย node simulation: ก่อน fix = ว่างเปล่า, หลัง fix = เนื้อหากลับมา)

### Bug fixes
- **Now Playing หดแคบตอนเพลงชื่อสั้น**: `.np-container` เป็น flex child โดยไม่มี
  width → ขนาดตามเนื้อหาเสมอ (ชื่อสั้น = การ์ดหด) → แก้: `width:100%` ใน inline
  style ของ np-container (การ์ดเต็ม widget เสมอ)
- `_broadcast_threadsafe` guard (chat widget starve เมื่อ editor ปิด)
- Layer: คลิกไม่เด้งบนสุด (5px threshold) + drop ล่างสุดได้ + ปุ่ม ▲▼ + ปุ่มขาว
- Viewer: theme sync + vertical direction + push ทันทีตอน connect + total mode
- Clock: LIVE TEXT 5 bolt fix (SVG height 100%)
- `widgetEl` undefined (crash renderAll)
- Font whitelist + 30+ fields whitelist

### Twitch: ส่งเบิ้ล 4 ครั้ง + echo ชื่อผิด + TTS อ่านของตัวเอง (แก้แล้ว รอ 2.7.1)
- **อาการ**: หลุด → reconnect fail 4 ครั้ง → กดมือ → พิมพ์ครั้งเดียว เบิ้ล 4 รอบ
  + echo ขึ้นชื่อ account เรา (ควรเป็น Baitoei-Bot) + TTS อ่านข้อความตัวเอง
- **สาเหตุ 3 จุด**:
  1. `_connect_platform` (กดมือ) ไม่ disconnect client เดิม → ทับใน dict แล้วตัวเก่า
     กลายเป็น orphan ที่ยัง JOIN ห้อง (รับ echo ของตัวเองทุก connection)
  2. (ไม่ใช่บั๊ก — echo ชื่อ twitch_bot_username ถูกตามกฎแล้ว)
  3. `_is_bot_author` ไม่ดัก `twitch_bot_username` (comment บอกตั้งใจ — แต่พังงาน
     ห้ามอ่าน TTS) + IRC echo ของข้อความตัวเองไหลเข้า pipeline เต็ม ๆ
- **แก้ (app.py)**:
  1. **บังคับ connection เดียว**: `_client_registry` จดทุก client ที่สร้าง +
     `_retire_other_clients(platform, keep)` กวาดล้างทุกตัวที่ไม่ใช่ตัวใช้งาน
     (เรียกตอน connect/reconnect สำเร็จ) + `_connecting_platforms` guard กัน
     connect ซ้อน (dict จับเวลา — ค้างเกิน 60 วิ ปลดล็อกเอง) + กดมือ disconnect
     ตัวเก่าก่อนเสมอ + fail ก็ disconnect ตัวที่สร้างค้าง
  2. Echo Twitch → `twitch_bot_name` (Baitoei-Bot)
     ★แก้ไขภายหลังตามกฎที่ถูก: **โพสในโปรแกรม = ชื่อเรา** (twitch_bot_username)
     ส่วน Baitoei-Bot สงวนสำหรับข้อความที่บอทตอบเท่านั้น (_on_bot_response ถูกอยู่แล้ว)
  3. `_on_chat_message` ดัก IRC echo ตัวเอง (author == twitch_bot_username →
     ไม่โชว์ panel/ไม่อ่าน TTS แต่ยังให้ bot ตอบ !xxx ผ่าน `_bot_handle_own_echo`)
     + `_is_bot_author` ดัก twitch_bot_username เพิ่ม
     ★แก้ไขรอบ 2 (หลัง user ทดสอบ): ดักหมดทุกข้อความของบัญชีตัวเอง = แรงเกิน —
     พิมพ์ตรง ๆ บนหน้า Twitch ก็หายไปจากโปรแกรม → แยก 2 กรณีด้วย `_recent_own_sends`
     (จำข้อความที่เพิ่งส่งผ่านโปรแกรม 15 วิ):
     a. ตรงกับที่เพิ่งส่งผ่านโปรแกรม = IRC echo → ซ่อน (โปรแกรม echo แล้ว) + bot ตอบได้
     b. ไม่ตรง = พิมพ์บนหน้า Twitch เอง → **แสดงใน Live Chat** + mark _own_message
        (ไม่อ่าน TTS)
     ★รอบ 3: KICK ทำเหมือนกัน — ถอดตัวดัก own ทิ้งหมดใน chat_kick._handle_chat ออก
     แล้วให้ app แยกกรณี (ใช้ kick_bot_username) + echo โปรแกรมส่ง KICK ขึ้นชื่อ
     kick_bot_username + _is_bot_author ดักทั้ง twitch/kick username
- (ทดสอบ: method จริง `_retire_other_clients` กับซอมบี้ 4 ตัว → เหลือ winner ตัวเดียว ✓)
- **★ root cause ยืนยันตามสมมติฐาน user ข้อ 2**: `connect()` โหลด emote แบบ blocking
  (comment อ้างว่า background แต่โค้ดรันตรง — HTTP หลายตัว × 10s = ค้างถึง 30s)
  + โค้ดเก่าไม่มี in-flight guard → รอบ reconnect ซ้อนทับกันระหว่างที่ค้าง →
  client หลายตัวเชื่อมสำเร็จช้ากว่าโดยไม่มีใครตาม → "ติดจริงแต่แยกเป็น 4 session"
- **สมมติฐานข้อ 1 (reconnect ไม่ติด แต่กดมือติดเลย)**: by design — auto-reconnect
  มี cap 5 ครั้ง + backoff สูงสุด 60s เมื่อเน็ตล่มนานเกินงบ ระบบจะหยุดถาวร
  (manual_disconnect=True) จนกว่าจะกดมือ — ไม่ใช่ reconnect พัง
- **แก้เพิ่มใน chat_twitch.py**: emote load → background thread จริง (หน้าต่างค้าง
  connect() 30s → ~1s)

### Reconnect system review — แก้เพิ่ม (รอ 2.7.1)
- **★★ logger ไม่ถูกประกาศใน chat_twitch.py** (ใช้ 8 จุด ไม่มี import logging!)
  → token หมดอายุ (LOGIN_UNSUCCESSFUL) พัง NameError ตั้งแต่บรรทัดแรก
  → reader thread ตายกลางคัน + `_is_connected` ค้าง True → ระบบคิดว่ายังเชื่อม
  อยู่ → auto-reconnect ไม่ทำงานตลอดกาล = อาการ "หลุดแล้วต่อไม่ติด" อีกทาง
  → แก้: `import logging` + `logger = logging.getLogger('chat_twitch')`
- **Twitch token refresh sync** (เดิมไม่มี — KICK/YouTube มี):
  1. `_build_client`: `client._refresh_token = ...` เดิมอยู่**หลัง return = dead code**
     → client ไม่เคยได้ refresh_token → token หมดอายุ = ตก anonymous ทันที
  2. refresh ใน client ไม่เก็บ refresh_token ใหม่ (Twitch หมุนเวียน ตัวเก่าตาย)
  3. ไม่มี callback ยิงกลับ app → settings ค้าง token เก่า
  → แก้ครบ: set ก่อน return + `_on_token_refreshed` callback →
  `_on_twitch_token_refreshed` save ทั้ง token + refresh + expiry ลง settings
  + startup path "ใกล้หมดอายุ" เก็บ refresh_token ใหม่ด้วย (เดิมไม่เก็บ)
- **กด disconnect กลางทางโดนทับ**: connect ที่บินอยู่เสร็จทีหลังแล้วเก็บเข้าระบบสวน
  คำสั่ง → แก้: `_on_connect_result`/`_on_reconnect_done` เช็ค `manual_disconnect`
  ก่อนเก็บ → ถ้า user สั่งตัดแล้ว = ตัด client ทิ้ง + แจ้ง "ยกเลิกตามคำสั่ง"
- **attempts นับเบิ้ล**: `_check_reconnect` นับ attempts ทุกรอบแม้รอบเดิมยังบินอยู่
  (guard อยู่ใน `_do_reconnect` ซึ่งถูกเรียกหลังนับแล้ว) → 5 รอบที่ไม่ได้ทำจริง
  = หยุดกลางคันทั้งที่กำลังจะสำเร็จ → แก้: เช็ค in-flight ใน `_check_reconnect`
  ก่อนนับ (skip ไม่นับ)
- **ทดสอบ**: token-expiry path + refresh-fail path ผ่านหมด (mock refresh)

### ★ ASK Minimal: slider ตำแหน่ง X/Y ไม่ขยับสด (แก่แล้ว รอ 2.7.1)
- **อาการ**: ลาก slider ตำแหน่ง X/Y (และความกว้าง) ใน ⚙ ระหว่างเดโม/โพล active
  → แผงไม่ขยับ ต้องหยุดเดโมแล้วเปิดใหม่ถึงเห็นตำแหน่งใหม่
- **สาเหตุ 2 ชั้น**:
  1. Minimal ถูก pin ตำแหน่งด้วย px ตอนสร้างแผง (renderAskInto วัดขนาดแล้ว set
     `--ask-min-x/y` + class `ask-min-fixed` ซึ่ง override CSS var) → เปลี่ยน
     `--ask-px/py` ทีหลังไม่มีผล
  2. signature เปรียบเทียบ rebuild (`[question, choices, phase, mode]`) ไม่รวมค่า
     ตำแหน่ง → save แล้วก็ไม่ rebuild / slider ไม่เคยแตะ widget เลย (แค่เปลี่ยน label)
- **แก้ (composer.html)**:
  1. แยก clamp เป็น `askClampMinimal(wEl, ovX, ovY)` — เรียกได้ทั้งตอนสร้างแผงและ
    ตอนลาก slider (ovX/ovY = ค่า slider ตอนนี้ override ค่า config ที่ยังไม่ได้บันทึก)
  2. เพิ่ม `askLivePos()` — อ่าน slider กว้าง/X/Y → set `--ask-minw/--ask-px/--ask-py`
     + re-clamp ทุก widget ask ทันที
  3. oninput ของ slider ทั้ง 3 ตัว (กว้าง/X/Y) เรียก `askLivePos()` ต่อท้าย
- **ทดสอบ (Node + DOM stub)**: clamp จาก config ✓ / ลาก (60,70) ขยับทันที ✓ /
  vars set สด ✓ / ชิดขอบ 95% clamp กลับ 1750px ✓ / โหมด vright ไม่ถูกแตะ ✓
  + node --check ผ่าน
- Rebuild Lite ให้ user ทดสอบ (Full อัปเดต composer.html แบบ loose file แล้ว)

**★ รอบ 2 — Overlay OBS ก็ไม่ขยับ (แก่แล้ว)**: ทั้งที่ editor ขยับสดแล้ว ฝั่ง OBS
ยังค้างจนเรียก Demo ใหม่ — เพราะ path config-update (updateWidgetElement) กับ
handleAskState แค่ set CSS vars แต่แผง Minimal ถูก pin ด้วย px (ask-min-fixed)
→ เติม `askClampMinimal(el)` 2 จุด: ท้าย branch ask ของ updateWidgetElement
(หลัง renderAskInto) และใน handleAskState หลัง set vars (ก่อน logic render —
ถ้า rebuild มัน clamp ซ้ำเอง ถูกอยู่ดี) / ทดสอบ Node stub: แผง pin เก่า (85,12)
+ config ใหม่ (40,60) → ย้ายเป็น 768,648 ทันที ✓ / copy composer.html เข้า dist
ทั้งสองแบบ loose file (19:51 — ไม่ต้อง rebuild)

**★ รอบ 4 — เพิ่ม ASK แล้วกด Demo เลย ไม่ขึ้นบน OBS (แก่แล้ว)**: ต้องแก้ค่าใน ⚙
+ บันทึกก่อนถึงขึ้น — เพราะปุ่มเพิ่ม widget เดิม**ไม่ได้ save เลย** (มีแค่
_markLocalEdit) → widget ใหม่อยู่แค่ใน editor local → Overlay ไม่มี widget นั้น
ตอน Demo broadcast → หา `.widget.type-ask` ไม่เจอ → ไม่มีอะไรขึ้น
- **แก้**: แยก `saveLayoutNow()` (ยิง POST /save ทันที — ดึงจากโค้ด delete เดิมมา
  เป็น helper ร่วม) → เรียกทั้งใน add handler และ deleteWidget
- **ทดสอบ end-to-end จริง**: server config ว่าง → เปิดหน้า overlay (จำลอง OBS)
  → POST save widget ask เปล่า ๆ (เหมือนที่ add สร้าง — ไม่มี field ask เลย)
  → overlay ได้ widget + default vright/violet → POST /ask-demo ทันที →
  **แผงขึ้นบน overlay เลย** ✓ + node --check ผ่าน
- composer.html sync เข้า dist ทั้งสอง (20:08 — loose ไม่ต้อง rebuild)

**★ รอบ 6 — ปุ่ม "📖 วิธีเชื่อม WebSocket" กดไม่ได้ (แก่แล้ว)**: lambda เรียก
`webbrowser.open()` แต่**ลืม import webbrowser** ใน scope นั้น (จุดอื่นในไฟล์
import แบบ local ในฟังก์ชัน — จุดนี้ลืม) → กดแล้ว NameError โดน Qt กลืนเงียบ ๆ
= ปุ่มเหมือนเปล่า ไม่เปิดเว็บ → เติม `import webbrowser` ใน
_build_obs_ws_section / syntax + module load ผ่าน / **ต้อง rebuild** (.py)

**★ รอบ 5 — สับสนสถานะ OBS WebSocket / ช่องรหัสว่าง (แก่แล้ว)**:
- **คำถาม user**: ติ๊กเปิด WebSocket แล้วรู้สึกต่อได้เลยทั้งที่ช่องรหัสว่าง —
  งงว่าตอนนี้เชื่อมอยู่รึเปล่า?
- **ความจริง**: (1) OBS ที่ปิด Enable Authentication ต่อได้เลยไม่ต้องมีรหัส —
  ช่องว่างใช้ได้จริง (2) ภาพขึ้น OBS ไม่ใช่หลักฐานว่า WS ต่ออยู่ — overlay
  วิ่งผ่าน HTTP ธรรมดา WS มีหน้าที่แค่ auto-refresh ตอนเปิดโปรแกรม
- **แก้ (ui/dialogs/settings.py)**:
  1. เพิ่ม `_poll_obs_ws_live_status()` + QTimer 2 วิ — ดึงสถานะจริงจาก
    `parent_app._obs_watcher.is_connected`: ⏸️ ปิดใช้งาน / 🔌 ยังไม่บันทึก /
    🟢 เชื่อมสำเร็จ+refresh แล้ว (+ ถ้ารหัสว่างบรรทัดอธิบาย "OBS คุณไม่ได้เปิดล็อครหัส") /
    🟡 ยังไม่ติด+ชี้ว่า 'รหัสผ่านผิด' = ต้องคัดลอกรหัสจาก OBS มาใส่
  2. hint เพิ่มบรรทัดรหัส: OBS ใหม่สุ่มรหัสให้เสมอ → คัดลอกจาก Connect
    Information / ว่างได้เฉพาะเมื่อปิด Enable Authentication เอง
- ทดสอบ: logic 6 เคส (ปิด/ยังไม่บันทึก/ต่อแล้ว+รหัสว่าง/ต่อแล้ว+มีรหัส/ลองอยู่/
  ยังไม่มี watcher) ผ่านหมด + ast.parse ผ่าน / **ต้อง rebuild exe** (.py)

**★ รอบ 3 — composer เห็น ASK สองโหมดซ้อน (เสา+mini) / OBS ถูก (แก่แล้ว)**:
- **root cause = merge bug ใน WS config handler (editor mode)**: path ปกติ (ไม่อยู่
  local-edit window) เดิม merge ค่า local แบบ non-empty ทับค่า server **ทุก field**
  ตลอดกาล → ค่า local เก่า (stale) ชนะตลอด เช่น server ส่ง ask_layout=minimal
  แต่ local มี vright ค้าง → editor เรนเดอร์โหมดเก่าค้างถาวร (ผสมกับ widget อื่น
  = เห็นซ้อน 2 แบบ) ขณะที่ OBS รับ config ตรง ๆ เลยถูก — reproduce จริงผ่าน
  test server: save minimal แล้ว className ยัง ask-mode-vright + cfgLayout ค้าง vright
- **แก้ 3 จุด (composer.html)**:
  1. merge ใน path ปกติ → เหลือเก็บแค่ x/y/w/h จาก editor (กันกระตุก) ค่าอื่นรับ
    จาก server ตรง ๆ (ค่าที่ user เพิ่งเปลี่ยนคุมด้วย local-edit 1.5s + modal-open
    guard อยู่แล้ว — จึงไม่หาย)
  2. แยก `askWidgetClasses(w)` (theme/bar/frame/mode/anchor) ใช้ร่วมทั้ง
    updateWidgetElement + createWidgetElement (เดิมซ้ำกัน 2 ที่)
  3. handleAskState เพิ่ม **self-heal className** — ทุก push สถานะโพล rebuild
    class ของ widget จาก config ปัจจุบัน (กัน className ค้างรุ่นเก่าตอน renderAll
    ถูกข้ามช่วง local-edit window)
- **ทดสอบใน browser จริง** (server 8899 + editor page): เดโม vright → save
  minimal ระหว่าง active → className เปลี่ยนเป็น ask-mode-minimal + panel เดียว
  + pin (60,50) ทันที ✓ / ย้อนกลับ minimal→vright → เสาขวาเต็มสูง ✓
  + node --check ผ่าน / Rebuild Lite + copy loose เข้า Full

### ★ Avatar Widget กลับหัว + ปุ่ม flip หาย (แก่แล้ว รอ 2.7.1)
- **อาการ**: เลือกตัวละคร preset (เม้ง/ใบเตย) หรือ custom → avatar กลับหัว
  (หัวลงล่าง) + checkbox "สะท้อนภาพ ↔/↕" ใน ⚙ หายไป (ทั้งที่ออกแบบไว้)
- **root cause 2 จุดร่วมกัน** (ห่วงโซ่บั๊ก):
  1. **modal avatar flush ไม่ครบ**: หลัง refactor string buffer (กัน innerHTML +=
     re-parse) — branch avatar เรียก `_showSettingsModal()` ที่บรรทัด 7919 ครั้งเดียว
     แล้วเพิ่มฟิลด์ "ตัวเลือก/flip/Animation/ไมค์" ต่อใน buffer แต่ **return โดยไม่ flush
     ซ้ำ** → ฟิลด์เหล่านั้นไม่เคยไปถึง DOM (ปุ่ม flip หาย)
  2. **getChecked คืน true เมื่อ element ไม่มี** (line ~8989: `return el ? el.checked
     : true`) → ตอนกดบันทึก readModalFields อ่าน `f-avatar_flip_v` ไม่เจอ → ได้ true
     → **บันทึก avatar_flip_v=true เงียบ ๆ** → กลับหัวทั้ง preset และ custom
- **แก้ (composer.html)**:
  1. ย้ายบล็อกฟิลด์ทั้งหมด (display options + flip + animations + mic section)
     มาไว้ก่อน flush เดียว — wiring ทั้งหมด (preset toggle/upload/mic) ทำงานหลัง
     flush = element มีจริงทั้งหมด (bonus: โค้ด mic threshold/meter ที่เคย null-guard
     ไม่ทำงาน กลับมาใช้ได้)
  2. readModalFields เพิ่ม guard: `if (get('f-avatar_flip_h') !== null)` — ถ้า
     checkbox ไม่อยู่ใน DOM ให้คงค่าเดิม (ห้ามเขียน true ทับ)
  - สแกนทุก branch แล้ว: avatar เป็น branch เดียวที่พัง (ที่อื่น flush ครอบ return หมด)
- **ทดสอบ**:
  - Node + DOM stub รัน `_openSettingsModalInner` จริงจากไฟล์ → flip_h/flip_v/
    fit/bounce/mic อยู่ใน HTML ที่ flush ครบ + overlay active ✓
  - readModalFields guard 3 เคส (หาย+false เดิม / หาย+true เดิม / มีจริงอ่านถูก) ✓
  - node --check script ทั้งไฟล์ผ่าน
  - ★ IAB (in-app browser) กด click ไม่ได้บนหน้า editor เลย (แม้เวอร์ชั่นเก่าก่อนแก้
    ก็ตายเหมือนกัน — mousedown ยิงแต่ click ไม่ยิง) = artifact ของ IAB ไม่ใช่บั๊ก
    ของโค้ด — ผู้ใช้เปิดใน Chrome จริงได้ปกติ (เคยเห็น modal มาก่อน)
- **หมายเหตุ**: composer.html เป็น loose file — copy ไป dist ทั้งสองชุดแล้ว
  (ไม่ต้อง rebuild exe) / build 19:03+19:12 ที่ทำไว้มี composer.html ตัวเก่าอยู่ข้างใน
  แต่ patch จะเอาจากต้นทางล่าสุดอยู่แล้ว

### ปุ่มการ์ดแพลตฟอร์มค้างขอบแดงหลังกดตัดการเชื่อมต่อ (แก่แล้ว รอ 2.7.1)
- **อาการ**: กด "หยุดเชื่อมต่อ" แล้วบางทีปุ่มไม่กลับเป็น "เชื่อมต่อ" ค้างสถานะแดง
- **สาเหตุ 3 ทาง** (ปุ่มแดง = state เชื่อมต่ออยู่):
  1. ผล connect/reconnect ที่บินอยู่มาถึงหลังกดตัด → เปิดการ์ดกลับแดง
     (แก้แล้วใน section ก่อน — reject path เช็ค manual_disconnect)
  2. `_reconnect_twitch_oauth` (auto หลัง OAuth) เรียก `_connect_platform`
     ซึ่งล้างธง manual_disconnect → สวนคำสั่งตัดของ user แล้วเชื่อมกลับ
     → แก้: เช็ค manual_disconnect ก่อนเรียก
  3. auto-reconnect ยอมแพ้ (5 ครั้ง) หรือ fail แต่ละรอบ → ไม่อัปเดตการ์ด
     เลย ค้าง state เดิม → แก้: set_connected(False) ทั้งตอน give-up และตอน fail

### ★ ฟีเจอร์ใหม่: ASK Widget — โพล/แบบสอบถามบน Composer Overlay (รอ 2.7.1)
- **ปุ่ม "ASK" (text เทาจาง→เขียว) ใน Live Chat header หลัง A+** (chat_panel.btn_ask
  — signal ask_toggled → _toggle_ask_panel / sync สีผ่าน set_ask_active)
- **แผงคุมลอยด้านขวา** (`ui/widgets/ask_panel.py`) — ชิดขวาตามขอบโปรแกรมเสมอ
  (resizeEvent ตาม) / ช้อยส์เริ่มว่างเป็น placeholder / default โหวต 30 วิ /
  สรุป 20 วิ + แสดงตลอดไปเป็น optional (default = นับถอยหลังแล้วหาย)
- **Preset คำถามด่วน** (`ask_presets` ใน settings): dropdown + 💾 บันทึก + 🗑 ลบ
  — เลือกแล้วเติมคำถาม+ช้อยส์+โหมดทันที / CSS vars ถูก set ตั้งแต่สร้าง widget ครั้งแรก
  (renderWidgetContent) กันกล่องโผล่ผิดตำแหน่ง/ขนาดบน OBS ก่อน push รอบสอง
  - คำถาม + ช้อยส์ 2-9 ข้อ (A-I / เพิ่มกด "+" ลบกด ✕ — ขั้นต่ำ 2)
  - วิธีตอบ: ตัวอักษร A B C หรือ ตัวเลข 1 2 3
  - เวลาโหวต: 30-3600 วิ หรือไม่จำกัด
  - แสดงผล: เรียลไทม์ (เห็น bar+ตัวเลขระหว่างโหวต) หรือรอจบค่อยสรุป
  - แสดงสรุปผล: N วิ หรือตลอดไปจนกดปิด
  - ระหว่างโหวต: สถิติสด + ปุ่ม "จบโหวตทันที" / จบแล้ว: ปุ่ม "ปิดผลออกจากจอ"
- **Overlay** (`composer.html` widget type `ask`): หัวคำถาม / grid 2 คอลัมน์
  (key+คำตอบ+จำนวน+progress bar) / footer "โหวตแล้ว N คน" + countdown นับถอยหลัง
  สด / จบแล้ว: badge "จบโหวต" + winner เขียวเรืองแสง / XSS-escaped (esc())
- **กติกาโหวต** (`_ask_try_vote` ใน app.py):
  - ข้อความต้องเป็น token เดียวเป๊ะ (A/a/1) — "ขอเลือก A" ไม่นับ / "AB" ไม่นับ
  - 1 คน 1 โหวต ครั้งแรกเท่านั้น (key = platform+author — ชื่อเดียวคนละแพลตฟอร์ม = คนละคน)
  - โหวตถูก → ข้าม TTS (แต่ยังแสดงในแชท) / โหวตเมื่อจบแล้ว → ไม่นับ
- **State machine**: voting → ended (หมดเวลา timer / กดมือ) → close (ครบเวลาแสดงผล /
  กดมือ) — ใช้ generation counter กัน timer โพลเก่าปิดโพลใหม่
- **ตกแต่ง (รอบ 2)**:
  - พื้นหลัง**โปร่งใส** (rgba + backdrop-blur เบา ๆ) เป็น widget วางทับ overlay
  - **gzip compression** ที่ `_handle_index` (composer_server.py): 526KB → 119KB (ลด 78%)
  ★ เดิมมี gzip_middleware ที่พัง (500 error) — ลบออก ทำที่ handler ตรง ๆ แทน
- **Modal แนะนำเชื่อม OBS WebSocket** (ไม่บังคับ — QDialog custom 360px dark theme):
  กดปุ่ม Overlay ถ้า `obs_ws_enabled=False` → เด้ง modal 3 ปุ่ม (จัดกลาง)
  - [เชื่อม WebSocket] (เขียว) → `_open_settings_to("obs_ws")` เปิด Settings หน้า WS
    ★ `_show_section()` sync sidebar highlight ด้วย (setUserRole + setCurrentRow)
    ★ `_open_settings_to` ต้องสร้าง dialog เอง ห้ามเรียก _open_settings เพราะ exec() blocking
  - [วิธีเชื่อม] (ขอบ) → เว็บสอน https://men9ch.com/broadcastplayroom-websocket-setting/
  - [ไม่สนใจ] (แดง #dc2626) → เปิด Composer ปกติ
  - ★ ปิดด้วย X/Escape → `QDialog.Rejected` → return "close" → ไม่เปิด composer
  - ถ้า WS enabled แล้ว → ไม่เด้ง modal
  - ปุ่ม "📖 วิธีเชื่อม WebSocket" ในหน้า Settings > WS ใช้ลิงก์เดียวกัน
- **zoom/mode toolbar ย้ายเข้า sidebar** (เหนือ tab Widgets — เดิมลอยขวาบน canvas
  บังปุ่ม ✕ ของ ASK เต็มจอ ปิดไม่ได้)
- **ปุ่มเพิ่ม Widget → grid 2 คอลัมน์ แนวตั้ง** (icon บน / label ล่าง ลดความยาว)
  ★ tab switcher ต้อง set 'grid' ให้ tab-widgets (ห้าม 'block' — จะฆ่า grid)
- **ASK เต็มจอตั้งแต่กดเพิ่ม** — บังคับ x/y/w/h = full canvas ครบ 3 ประตู:
  ปุ่มเพิ่ม widget / createWidgetElement / updateWidgetElement (เดิมมีแค่ประตู
  หลัง → กดเพิ่มแล้วเป็นกล่องเล็ก ต้องเข้า settings บันทึกก่อนถึงเต็มจอ)
- **★ รอบ 4 — โครงใหม่: widget = เฟรมเต็ม canvas ล็อค** (ลาก/ย่อไม่ได้ แก้ที่ ⚙ เท่านั้น
    x/y/w/h บังคับ 0,0,canvas — updateWidgetElement + createWidgetElement ข้าม drag/resize)
    ตัวโพล = `.ask-panel` วางตามโหมด:
    - `vright`/`vleft` = เสาแนวตั้งเต็มสูง ยื่นจากขวา/ซ้าย กว้าง `ask_extend_pct` %
      (★UI: select รวมเป็น "เสาแนวตั้ง" ตัวเดียว + dropdown "ยื่นจาก" ขวา/ซ้ายแยก
      — โชว์เฉพาะโหมดเสา / config ยังเก็บ vleft/vright เหมือนเดิม)
    - `hband` = แถบเต็มกว้าง สูงตาม % + `ask_anchor` top/middle/bottom
    - `minimal` = กล่องเล็กตามเนื้อหา **ย้ายอิสระด้วย slider X/Y** (`ask_pos_x/ask_pos_y`
      5-95% ของ canvas — จุดกึ่งกลางกล่อง translate(-50%,-50%))
      ★clamp ตอน render: วัดขนาดกล่องจริงแล้วดึงกึ่งกลางกลับเข้าขอบ canvas เสมอ
      (เคยล้นครึ่งตัวออกนอกจอตอน slider ชิดสุด — ขนาดกล่องแปรผันตามช้อยส์ ล็อคช่วง
      slider ตายตัวไม่ได้)
      ★ความกว้าง FIX ตามที่ user ตั้ง (slider 220-700px default 340 → --ask-minw)
      — เดิม max-content ตามเนื้อหา = คำถามสั้นกล่องหด ตำแหน่ง composer ไม่ตรงของจริง / hband บน-ล่าง
      ★UI: dropdown "ตำแหน่ง" ช่องเดียวกัน label เดียวกันใต้ select รูปแบบ
      (เสา→ขวา/ซ้าย, แนวนอน→บน/ล่าง — รวม sec-anchor เก่าเข้า sec-side)
    - extend **จำกัด 20-30%** (default 20) — slider + whitelist clamp
    - settings แสดง slider/select ตามโหมด (updateAskModeSections — อ่านค่า live
      จาก DOM ก่อน rebuild กันรีเซ็ต) / legacy: card→minimal, bar→hband, tower→vright
    - **Demo auto-flow**: vote (★30 วิ — เดิม 45 ลด 30%) → **ยอดสดไต่ขึ้นทุก 2.5 วิ
      11 รอบ** (สุ่มเพิ่ม/แถบขยับ) → ครบ 30 วิสลับหน้าสรุปผล (ยอดต่อเนื่อง)
      → 10 วิ → หาย (anim-out) รวมจบใน 40 วิ
      — จับเวลาฝั่ง server (_ask_demo_handles + call_later) ทุกหน้าพร้อมกัน /
      ★บั๊ก race ที่แก้แล้ว: รอบ update ที่ 18 จับ 45 วิพอดีชนกับ result push →
      แพ้ race ดันกลับเป็นหน้าโหวต = "หมดเวลาไม่เปลี่ยน" → ตัดรอบสุดท้ายเหลือ 17
      (สุดท้าย 42.5 วิ) เว้นช่วงให้ result เด่น
      / กดหยุดมือ หรือโพลจริง push มา → cancel ทันที / ปุ่ม editor sync ตาม
    - **หน้าสรุปผลเรียงมาก→น้อย** (ไม่เรียง A B C — winner อยู่อันดับ 1 เสมอ)
      ระหว่างโหวตคงลำดับเดิม
  - **★ โพสผลสรุปลงแชทเมื่อจบโหวต** (`_ask_post_result_to_chat` — เรียกจาก
    `_ask_end_vote`): `[ผลสรุปการโหวต] หัวข้อ : ... | จาก N คนโหวต | ผลออกมาดังนี้
    [C- เย็น 20 โหวต] ...` (บรรทัดเดียว เรียงมาก→น้อย — ★0 โหวต = ไม่ส่ง) — ส่งทุกแพลตฟอร์มที่เชื่อม+
    can_send (ข้ามตัวที่ส่งไม่ได้เช่น YouTube) + echo เป็นชื่อบอทผ่าน _on_bot_response
    (จำ _recent_own_sends กันซ้ำ/ไม่อ่าน TTS) / คุมด้วย checkbox ใน Chat Bot Setting
    (`ask_post_result` default เปิด)
    - เสาแนวตั้ง **สูงตามเนื้อหา ชิดบน** (top:0; bottom:auto — เดิมยืดเต็มสูงเสมอ
      ทำให้ช้อยส์น้อยแล้วกล่องโหว่) / hband+minimal คงเดิม
    - **แยกขนาดฟอนต์**: `ask_question_fs` (12-60px default 24) + `ask_choice_fs`
      (10-40px default 18) — ใช้ CSS var --ask-qfs / --ask-cfs (ไม่ผูก ask_scale
      ซึ่งเหลือใช้กับป้าย A-B / แถบ % / ระยะห่าง)
    - ป้ายช้อยส์ = **[พิมพ์ "A"] / [พิมพ์ "1"]** แยกบรรทัด:
      บรรทัด 1 = ป้ายพิมพ์ (ซ้าย) + ยอดโหวต (ขวา) / บรรทัด 2 = เนื้อหาช้อยส์ /
      บรรทัด 3 = แถบ % (ตอนแสดงยอด)
    - **หัวข้อยาว → marquee**: `.ask-question` nowrap + overflow hidden +
      `setupAskTitleScroll()` (rAF แบบ np-title: หยุด 1.5 วิสองปลาย 30px/วิ วนซ้ำ
      — สั้นพอจัดกึ่งกลางปกติ / DOM ถูกถอด → isConnected guard หยุดเอง)
    - พื้นแผง **ทึบ 100% default** (ธีมทุกตัว alpha=1) + slider "ความโปร่งใส"
      (`ask_opacity_pct` 10-100 default 100 → --ask-opacity บน .ask-panel)
    - ★**เขียน CSS ทั้งชุดใหม่รอบสุดท้าย**: พบว่าไฟล์จริงค้าง CSS รุ่นเก่า (patch ก่อนหน้า
      ไม่ติดจริงทั้งก้อน) + regex solidify เคยสร้าง rgba(..., ,1) จุลภาคซ้อน = invalid
      → เขียนทับ section ทั้งหมดระหว่าง marker ASK↔Video ให้ครบทุกฟีเจอร์ปัจจุบัน
    - ช้อยส์ **responsive** — wrap ครบทุกตัวอักษร ไม่มี ... แม้ % ยื่นน้อย + เลื่อนได้ถ้าแน่น
    - whitelist: ask_layout validate + ask_extend_pct (5-90) + ask_anchor + 2 ฟอนต์
  - **Theme 17 แบบ** (`ask_theme`): violet/neon/gold/rose/emerald/sunset/midnight/
    ocean/sakura/forest/ice/candy/steel/fire/cyberpunk/mint/space — ทำผ่าน CSS vars
    (--ask-accent/--ask-bg/--ask-border/--ask-win ฯลฯ) ★glass+mono ถูกถอด — legacy
    map glass→ice, mono→steel ทั้งใน class builder และ select
    ★บั๊กใหญ่ที่เพิ่งเจอ: default ของทุกสีเคยประกาศใน `.widget-inner` (ลูก) → ชนะ
    cascade เสมอ ธีม (class บน .widget พ่อ) ไม่เคยมีผลเลย — แก้: ย้าย defaults
    มาที่ `.widget.type-ask` (ก่อนธีมในไฟล์) → inner เหลือแค่ var() ล้วน
  - **ขยายขนาด** (`ask_scale` 0.5-2.0) — ทุกอย่างคูณ scale (ฟอนต์/padding/มุม)
  - **Animation IN/OUT** เหมือน Image Timer (`ask_anim_in`/`ask_anim_out` 9 ทิศ +
    `ask_anim_ms` 200-5000) — ใช้ keyframes t-* ชุดเดียวกับ Image Timer เป๊ะ
    เล่นตอน: โพลเริ่ม (anim-in) / ปิดโพล (anim-out) — โหวตต่อเนื่อง/จบโหวตไม่แทรก
    ★anim-out เก็บ content ระหว่างเล่น (เดิม idle → innerHTML='' ทันทีทับ animation
    → กดปิดเองไม่เห็น anim ออก) → setTimeout(ms+50) ค่อยเคลียร์ idle ถ้าไม่มีโพลใหม่
  - ตั้งค่าทั้งหมดใน ⚙ ของ widget / whitelist ใน composer_server แล้ว
  - **Idle (ไม่มีโพล) → หายไปทั้งก้อน**: class `ask-idle` บน inner — ไม่มีพื้นหลัง/
    ขอบ/เบลอ/เงา + DOM ว่างเปล่า / editor mode = `ask-idle-editor` **โปร่งใสสนิท**
    เหลือแค่เส้นประบาง + placeholder (ลาก/ปรับขนาดได้ ไม่มีสีทับ widget อื่น)
  - **ตัด backdrop-filter ออกจาก ASK ทั้งหมด** (เดิม blur(3px) ฐาน → เบลอทับ widget
    อื่น — user ขอโปร่งใสเหมือน widget อื่น) — โพล active ใช้แค่พื้นธีมโปร่ง (ไม่มี blur)
  - **หลอดเวลานับถอยหลัง** (`ask_countdown_style`): text (เลข — default) / bar (หลอด
    สี) / both — ไล่สี: เขียว >50% / เหลือง ≤50% / แดง ≤10% (payload มี duration_sec)
    ★สมูทรอบล่าสุด: หลอดเวลาขับด้วย rAF ทุกเฟรม (askTimebarFrame — ตัด width
    transition ออก, เลขข้อความยัง tick 1 วิพอ) + หลอดโหวต transition 1.6s
    easeOutCubic (เดิม 0.4s ease → สั้นกระตุก)
    ★บั๊กกระตุกที่แก้แล้ว: ทุกโหวต = rebuild ทั้งแผง → หลอดใหม่เคยเกิดที่ 100%
    เขียวแล้วดีดไปค่าจริงผ่าน transition (ค้าง/กระตุกทุกโหวต) → แก้: คำนวณ
    %+สี ตอนสร้าง HTML เลย หลอดเกิดที่ค่าถูกต้อง เนียนต่อเนื่อง
  - **ปุ่มดูตัวอย่างสดใน ⚙ (รอบ 2)**: 2 ปุ่ม (🗳️ โหวต / 📊 สรุปผล) — กดแล้วปุ่มนั้น
    **กลายเป็น "⏹ หยุดตัวอย่าง"** (สีแดง) กดซ้ำ = หยุด + ปิด modal = หยุดอัตโนมัติ
    - ส่งผ่าน **POST /ask-demo → server broadcast ทุก client** = ขึ้นบน Overlay OBS
      จริง (เล่น anim in/out ตามที่ตั้ง) — **ไม่แคช** _last_ask_state (โพลจริง/refresh
      ไม่โดน demo เกาะ) — ทดสอบ WS จริงผ่านครบ
  - **★ บั๊ก settings ไม่เซฟ (แก่แล้ว)**: readModalFields ของ ask เคยถูกแทรกพลาด
    อยู่ใน branch `w.type === 'viewer'` → ค่า ask ไม่เคยถูกอ่าน/เซฟ → ย้ายมาเป็น
    branch `w.type === 'ask'` ของตัวเองแล้ว (server roundtrip ทดสอบผ่านอยู่แล้ว)
  - **ขยายช้อยส์**: slider 0.5–3.0 + ฐานใหญ่ขึ้น (คำถาม 24px, ช้อยส์ 18px,
    key 17px, bar 11px)
- **Gate (เช็คก่อนใช้)**: ต้องมี ASK widget (enabled) ใน Composer layout ก่อน —
  ไม่มี = กดปุ่ม ASK ไม่ผ่าน + System Message "โหมด ASK จำเป็นต้องใส่ Overlay ASK
  ก่อนถึงจะใช้ได้ (เพิ่มได้ที่ Composer → เพิ่ม Widget → 🗳️ ASK)"
  ★ยกเลิกระบบสร้าง widget อัตโนมัติ (ขัดกับ gate) — ผู้ใช้เพิ่มเอง
- **Port fallback (8801 ไม่ว่าง → 8802)**: gate อ่าน layout จาก settings ของแอปตัวที่
  กดปุ่ม (ผูก server ตัวเอง) — editor/copy URL ใช้ port จริงเสมอ → เช็คตรงกับ server
  ที่คุมจริงเสมอ + ตอน port เปลี่ยน: จำ port ใหม่ลง settings ถาวร + System Message
  เตือนให้เปลี่ยน OBS Browser Source URL (defer 3 วิ รอ UI พร้อม)
- **Push**: `composer_server.push_ask_state()` broadcast WS type='ask' + แคช
  `_last_ask_state` ส่งให้ client ใหม่ทันที (OBS refresh กลางโพลไม่หาย)
- ทดสอบ: state machine 6 เคส + กติกาโหวตครบ + panel 4 เคส + server cache +
  overlay render 4 เคส (realtime/summary/winner/idle + XSS) ผ่านหมด

### ★★ E2E TEST: updater 2.7.2 → 2.7.3 → ลบ (ผ่านแล้ว)
- ขึ้น release ทดสอบ v2.7.3 (patch_lite + version.json) โดยไม่แตะ 2.7.2 → เครื่อง
  local รัน dist Lite 2.7.2 กด UPDATE → **อัปได้ปกติเต็มทาง** (โหลด→bat→แทนที่→restart→2.7.3)
- ★ ระวัง: build_patch.py ตอนสร้าง patch จะ copy version.json ทับลง dist/_internal
  ด้วย (sync เข้าตัวที่จะแจก) — ตอนทดสอบเลยทำให้ dist กลายเป็น 2.7.3 ก่อน ต้องคืน
- เก็บกวาด: ลบ release v2.7.3 (latest กลับเป็น v2.7.2 อัตโนมัติ) + rebuild Lite
  กลับเป็น 2.7.2 ใน dist

### ★★ HOTFIX: updater NameError 'delete_old_exes' (แก่แล้ว — v2.7.2 assets แทนที่แล้ว)
- **อาการ**: กดอัพเดท → "เกิดข้อผิดพลาด : name 'delete_old_exes' is not defined"
- **สาเหตุ**: updater.py apply_patch — f-string ของ batch script ใช้
  `{delete_old_exes}` แต่ตัวแปรจริงชื่อ `old_exes_to_delete` (rename ไม่ครบ)
  → NameError ตอนสร้าง bat → อัปเดตตายทันที
- **แก้**: สร้าง `delete_old_exes_lines` (join บรรทัด del จาก old_exes_to_delete)
  → ใช้ใน Stage 4 ของ bat + สแกน AST ทุก placeholder ใน apply_patch แล้ว
  (ที่เหลือเป็น param/loop var — ปลอดภัย)
- **ทดสอบจริง**: จำลอง frozen + temp install dir + zip มี exe เก่า/ใหม่ + stub
  Popen → apply_patch คืน True / bat เขียนได้ / มีบรรทัด del exe เก่า / ไม่มี NameError
- **Rebuild ทั้งคู่ + patch ใหม่ + gh release upload --clobber แทน assets v2.7.2 เดิม**
  (tag เดิม เพราะยังไม่มีใครอัพ)
- ★ ข้อจำกัด: เครื่องที่ติดตั้งรุ่นที่ updater พังอยู่แล้ว กดอัพเดทก็ยัง error —
  ต้องอัปเดตมือครั้งเดียว (แตก zip ทับ หรือโหลด full) รุ่นที่แจกก่อนหน้านี้
  ถ้า updater ยังปกติจะอัพมาได้เอง

### ★ งานใหม่หลัง 2.7.1 (4): ASK panel — โซนกำลังโหวตแบบมีหลอดเหมือน overlay (แก่แล้ว รอทดสอบ dev)
- **user ขอ**: กล่องกำลังโหวตแสดงเป็นข้อ ๆ มีหลอดเหมือน overlay + จำนวนในกล่อง
  ต่อช้อยส์ + ล่างสุดสรุปยอดรวม + แยกแพลตฟอร์ม realtime
- **แก้**:
  - app.py `_ask_payload()` เพิ่ม **per_platform** {platform: count} จาก voters
    (push ไป overlay ด้วยแต่ overlay ไม่ใช้ — ใช้ใน panel)
  - ask_panel.py: ลบ lbl_counts บรรทัดเดียว → โซนใหม่:
    - แถวต่อช้อยส์ [key ส้ม][ช้อยส์ 105px][QProgressBar หลอดม่วง 9px สูง
      สัดส่วนตาม max][จำนวน + %] — สร้างครั้งเดียวต่อเฟส อัปเดตค่า in-place
      (กัน flicker) — `_add_status_choice_row` / `_rebuild_status_choices` /
      `update_live_counts` เขียนใหม่
    - จบโหวต → เรียงมาก→น้อย + อันดับ 1 สีเขียว (เหมือน overlay) —
      เช็ค `_status_sorted != ended` ครั้งแรกของเฟสค่อย rebuild
    - แถวแพลตฟอร์ม `_update_platform_row` — โลโก้ (get_platform_pixmap 14px,
      fallback ชื่อ) + จำนวน / ไม่มีโหวต = "ยังไม่มีผู้โหวต" / เรียง twitch→youtube→
      mylive→kick→tiktok / rebuild ทุกโหวต (แถวสั้น)
    - path เตือน validation ใน _on_start แทน lbl_counts ด้วย clear แถว
  - import QProgressBar + QTimer ระดับโมดูล
- **ทดสอบ offscreen**: เริ่มโหวต 3 แถว+นับถอยหลัง ✓ / โหวตไหลเข้า 8 คน
  (bar 20/100/40 ตาม max, % ถูก, platform row มี twitch+youtube) ✓ / จบเรียง
  B,C,A + winner เขียว ✓ / validation fail เคลียร์แถว ✓

### ★ งานใหม่หลัง 2.7.1 (3): ASK panel — นับถอยหลังในกล่องสถานะ + กว้าง 400px (แก่แล้ว รอทดสอบ dev)
- กล่องสถานะตอนโหวตเพิ่มเวลาถอยหลัง: "🗳 กำลังโหวต... ⏳ เหลืออีก 0:30"
  (QTimer 1 วิ / ≤10 วิ เติม ⚠ / หมดเวลา = "กำลังปิดโหวต..." + หยุด timer /
  ไม่จำกัดเวลา = ข้อความนิ่ง "(ไม่จำกัดเวลา)" / show_ended + show_idle หยุด timer
  ★ ลำดับ start ก่อน tick — เคสเปิดตอนหมดเวลาแล้ว tick จะ stop ทันที)
- panel กว้าง 320 → 400px + form padding 5px ทุกด้าน (ตาม user ขอ)
- QTimer เพิ่มใน import ระดับโมดูล (เดิม import local ใน _on_start)
- ทดสอบ offscreen ครบ: T0 นับทันที / วิแรกขยับ 0:29 / 8 วิ มี ⚠ / expired หยุด /
  no-limit นิ่ง / ended+idle หยุด

### ★ งานใหม่หลัง 2.7.1 (2): ASK panel — ช่องเวลาเป็นกรอกตรง + หน่วย วินาที/นาที (แก่แล้ว รอทดสอบ dev)
- **ปัญหา**: QSpinBox ลูกศร +/- เล็กกดยาก — กดกลางปุ่มกลายเป็น cursor text
- **แก้ (ui/widgets/ask_panel.py)**: เวลาโหวต + เวลาสรุปผล → QLineEdit กรอกตรง (70px,
  QIntValidator 1-9999, จัดกลาง) + QComboBox หน่วย "วินาที/นาที" (default วินาที)
  - `_make_duration_inputs(default_sec)` — สลับหน่วยแปลงค่าอัตโนมัติ (30วิ→1นาที /
    2นาที→120วิ — กันเผลอสลับแล้วกลายเป็น 30 นาที)
  - `_duration_seconds(ed, cmb)` — อ่านค่า → วินาที + clamp 5-3600 / ผิดรูป=5
  - toggle ไม่จำกัดเวลา/แสดงตลอดไป → disable ทั้งช่องกรอก+dropdown
  - _on_start ใช้ helper แทน sp_vote_sec/sp_result_sec (ลบ QSpinBox ออกหมด)
- **ทดสอบ (offscreen widget จริง)**: default 30วิ/20วิ ✓ / สลับหน่วยแปลงถูก ✓ /
  2นาที=120วิ ✓ / 90นาที clamp 3600 ✓ / 1วิ clamp 5 ✓ / ช่องว่าง=5 ✓
- **เทสใน dev mode ได้เลย** (python main.py) — ไม่ต้อง rebuild จนกว่าจะเอา exe

### ★ งานใหม่หลัง 2.7.1: System message สรุปผลโหวต ASK หลายบรรทัด (แก้แล้ว รอทดสอบ)
- **user ขอ**: หลัง ASK จบ → สรุปผลลง Live Chat หลายบรรทัด: หัวข้อ / จำนวนผู้โหวต /
  ผลแต่ละข้อเรียงมาก→น้อย + % / แยกยอดตามแพลตฟอร์ม (เฉพาะที่มีคนโหวตจริง — ไม่เชื่อมหรือ
  ไม่มีคนโหวต = ไม่ขึ้น) / 0 โหวต = แค่ "ไม่มีผู้โหวตในครั้งนี้"
- **แก้ (app.py)**: เพิ่ม `_ask_summary_system_message()` — เรียกจาก `_ask_end_vote`
  (แทนข้อความเดิม "จบโหวตแล้ว — แสดงสรุปผลบน Overlay") / ใช้ voters dict
  ((platform, author) → idx) นับยอดต่อแพลตฟอร์ม / chat row เป็น RichText →
  ใช้ <br> ขึ้นบรรทัด + <b> + winner แถวแรกสีเขียว #34d399 / escape HTML ด้วย
  html.escape กันโดนข้อความมี < > & ทำ RichText พัง / เคารพ toggle 🔔
  (show_system_messages) ตาม system message อื่น / popout ได้ด้วย (ผ่าน
  _post_system_message) / โพสลงแพลตฟอร์มแบบบรรทัดเดียว (_ask_post_result_to_chat)
  ยังอยู่เหมือนเดิมแยกกัน
- ลำดับแพลตฟอร์ม: Twitch → YouTube → MyLive → KICK → TikTok (ตามที่ user เรียง)
  + fallback แพลตฟอร์มนอกลิสต์ capitalize
- **รอบ 2 แก้ตาม user**: ส่วน "โหวตจาก" → ใช้**โลโก้แพลตฟอร์มแทนชื่อ** + รวม
  **บรรทัดเดียว** ("โหวตจาก : [logo] 8 คน&nbsp;&nbsp;[logo] 3 คน") — เพิ่ม helper
  `_ask_platform_icon_html()` (ui.platform_icons._get_assets_dir + Path.as_uri →
  <img 16px> / ไม่มีไฟล์ = fallback ชื่อ) / ทดสอบ offscreen render จริง — QLabel
  RichText วาด <img> ได้ (เจอพิกเซลสีม่วง twitch 31 จุด)
- **ทดสอบ logic (exec ฟังก์ชันจริง)**: 12 คน 3 แพลตฟอร์ม เรียงถูก winner เขียว /
  0 โหวตขึ้นบรรทัดเดียว / เสมอ+escape HTML ผ่านหมด + ast.parse ผ่าน
- **ต้อง rebuild exe** (.py) — Lite รอ auto-rebuild (โปรแกรม user เปิดค้าง PID 33468)

### ★ ฟีเจอร์ใหม่: ไอคอนสถานะ TTS ริมข้อความ (รอ 2.7.1)
- **ทุกข้อความใน Live Chat มีไอคอนเล็กขวาสุดแถว author** บอกสถานะ TTS:
  - `⏳ Ns` รอคิว/กำลังสร้างเสียง/รอเล่น (นับวินาทีสด — **เกิน 30 วิเปลี่ยนเป็นสีส้มเตือน**)
  - `🔊` กำลังอ่านอยู่
  - `✓ X.Xs` อ่านแล้ว + เวลารวมตั้งแต่รับข้อความถึงอ่านจบ (tooltip บอกด้วย)
  - `⊘` ไม่อ่าน (tooltip บอกเหตุผล — ด้านล่างครบทุกข้อ)
  - `⚠` ผิดพลาด (สีแดง + tooltip error ดิบ)
- **เหตุผล ⊘ ทั้งหมด** (tooltip): คำสั่ง !xxx / บอทของเรา / TTS ไม่พร้อม /
  pipeline หยุด / ปิดเสียง TTS / **ไม่ใช่ภาษาที่ตั้งค่าให้อ่านหรือแปล (xx)** —
  4 จุด: translate mode ไม่อยู่ในลิสต์แปล + RVC ไม่ใช่ th/en + multilang ไม่มี
  voice + mixed voice โดนกรอง / แปลไม่สำเร็จ (ไม่ใช่ไทย) / มีลิงก์ / code block /
  ยาวเกิน N / skip-long / ข้อความซ้ำ / ซ้ำหลายคน / throttle / rate limit ชั่วคราว /
  cooldown / คิวเต็ม / ข้อความว่าง / ดูเหมือน emote / TTS engine fail /
  decode เสียง fail / edge-tts timeout
- **⚠ error 2 ชั้น**: สร้างเสียง (exception จาก edge-tts/OmniVoice/RVC — ตอนแรก
  ลืมชั้นนี้ ⏳ ค้างตลอด) + เล่นเสียง (audio device)
- **โครงสร้าง**:
  - `app._on_chat_message` ติด `extra._tts_id` (uuid8) + `_tts_recv_ts` ทุกข้อความ
  - `chat_queue.on_tts_status(tts_id, status, info)` callback — ยิงทุกจุด
  - `_maybe_translate` เปลี่ยนเป็น 3-tuple `(translated, src_lang, skip_reason)` —
    "lang_not_configured" → enqueue ดัก → ⊘ "ไม่ใช่ภาษาที่ตั้งค่าให้อ่านหรือแปล (xx)"
    (เดิมหลุดไปให้ Premwadee อ่านต่างภาษา = เสียงแปลก) — detect ไม่ออก (None) ไม่โดนดัก
  - `_compute_one` จุดเงียบทั้ง 10 จุด → ติด `extra._tts_skip_reason` ก่อน return None
    → compute loop ใช้เป็นเหตุผล tooltip
  - ready_q tuple ขยาย: (audio, sr, vol, author, **tts_id, recv_ts**)
  - `_tts_status_sig` signal marshal จาก pipeline thread → main thread
  - ChatRow: `tts_status_label` + `set_tts_status()` + `refresh_tts_wait()`
  - ChatPanel/Popout: `update_tts_status()` + QTimer 1 วิ refresh ตัวนับ
- ทดสอบ: pipeline emit + ChatRow ทุกสถานะ + panel + popout + ทางภาษา 3 เคส
  (ไม่ใช่ภาษาที่ตั้งค่า / ไทยผ่านปกติ / อังกฤษแปลสำเร็จเข้าคิว) ผ่านหมด

---

## 🔧 โครงสร้างสำคัญ

### ไฟล์สำคัญที่เปลี่ยนในรอบนี้
```
overlay.html          — Danmaku + color commands + zone + timer animations
composer.html         — Settings UI rework + timer mode + layer tools + beforeunload
composer_server.py    — Whitelist + broadcast guard + zone/color passthrough
app.py                — TTS color strip (copy-based) + startup migration + viewer push
updater.py            — Exe migration + old exe cleanup + restart with new name
main.py               — Startup exe migration + kill/restart dialog
single_instance.py    — Dev mode kill (wmic) + Lite exe name (มีช่องว่าง)
tts_full.spec         — exe name = "Broadcast Playroom Full"
ui/widgets/topbar.py  — UPDATE button (capsule + shimmer)
```

### Danmaku Chat — โครงสร้าง
```
overlay.html:
  spawnSliderMessage() — สร้าง .slider-msg + lane + zone + color
  COLOR_MAP = { red, blue, green, yellow, purple, pink, orange, cyan, white, black, gray }
  rainbow-text class — gradient animation
  slider_zone: top / top50 / middle / bottom50 / bottom / full
  }color{ regex: /^\}([a-zA-Z]+)\{\s*/
app.py:
  TTS strip: copy-based (ไม่แตะ msg ต้นฉบับ)
  _re_color.match(r'^\}([a-zA-Z]+)\{\s*', msg.text or '')
```

### Image Timer Mode — โครงสร้าง
```
overlay.html:
  setupImageTimer() — setTimeout chain (wait → anim in → slides → anim out → hide)
  progress bar: .t-progress-wrap / .t-progress-bar
  ANIM_IN_MS / ANIM_OUT_MS — จาก settings (default 2000ms)
  CSS: --t-anim-in-dur / --t-anim-out-dur (var)
composer.html:
  Timer settings: interval (min/sec) + slide duration + anim in/out + anim speed
  Auto exit: default = mirror entrance direction
```

### Updater migration
```
updater.py apply_patch():
  1. Scan zip หา exe name ใหม่
  2. Scan install dir หา exe เก่า (broadcast/playroom)
  3. Batch: copy → delete old → start new
main.py startup:
  1. ถ้ารันชื่อเก่า + เจอชื่อใหม่ → start ใหม่ + exit
  2. ถ้ารันชื่อใหม่ + เจอชื่อเก่า → delete เก่า
```

---

## 📌 กฎการทำงาน

1. **Build = ต้องถามก่อนทุกครั้ง** (ห้ามทำเอง)
2. **Build = background** เสมอ (user คุยต่อได้)
3. **Patch = แค่ไฟล์ที่เปลี่ยน** (build_patch.py) — ห้ามบีบ dist ทั้งโฟลเดอร์
4. **Dev settings หลุดเข้า exe = อันตราย** — build_patch.py ลบ data/ อัตโนมัติแล้ว
5. **Changelog = user เขียนเอง** ห้ามเขียนแทน
6. **ประกาศใช้เฉพาะเรื่องสำคัญ** — ไม่ใช่ช่องทางประกาศอัพเดท
7. **User ข้ามเวอร์ชั่นได้** (patch มีไฟล์ครบ)
8. **★★ กฎเหล็กปุ่มไอคอนเล็ก**: `padding: 0; min-height: 0;` เสมอ
9. **}color{ ใช้เฉพาะ Danmaku Chat** — TTS ไม่อ่าน (strip ผ่าน copy)
10. **หลังอัพเดท: refresh OBS browser source** เสมอ (กัน cache)
11. **ไฟล์หลวม vs Python**: HTML/assets = ไม่ต้อง rebuild / .py = rebuild เต็ม
12. **beforeunload save** — เพิ่มแล้วใน composer.html (รวมใน 2.7.0 แล้ว)
13. **★ อัปโหลด version.json**: ห้ามอัป `release/version.json` (ไฟล์เก่าค้างจากรอบก่อน!)
    ต้อง copy `release/remote_version.json` → ชื่อ `version.json` แล้วอัป (gh ไม่รองรับ `#` rename)
14. **★★ กฎเหล็ก "ฟีเจอร์เยอะแล้ว"**: โปรแกรมมีฟีเจอร์จำนวนมาก — ทุกการแก้/เพิ่ม
    ต้อง (a) ทดสอบแบบ integration จริง ไม่ใช่แค่ syntax check (b) ยืนยันว่าไม่พัง
    ของเดิม (c) แจ้ง user ชัดว่าต้อง refresh OBS หรือ restart โปรแกรมหรือไม่
    (d) ถ้าเป็น .py ต้อง rebuild exe — จดไว้ทุกครั้ง
15. **★ กฎชื่อ echo + TTS ของข้อความตัวเอง (Twitch + KICK เหมือนกัน)** — ฉบับ 5 (ล่าสุด):
    - **เว็บ (Twitch/KICK)** = **อ่านเสมอ (default)** — ปิดได้ที่ **ตั้งค่า > TTS**
      "อ่านข้อความที่เราพิมพ์บนหน้าเว็บเอง" (`read_own_web_messages` default True)
      ผู้ใช้เก่าอัพเดท → ได้ default นี้อัตโนมัติ
    - **โปรแกรม** = checkbox "TTS" ข้างปุ่มส่ง (จำค่าใน `chat_input_read_tts`)
      ★บั๊กที่เจอจริง (จาก log): เคยพิมพ์ `_copy_send(my_msg)` เรียก module แทน
      `copy.copy()` → exception เงียบ ๆ → ไม่อ่าน + ไอคอน ⏳ ค้างตลอดกาล → แก้แล้ว
      + เติม emission จุดเงียบ 2 จุดสุดท้าย (block user / NG word) ครบ 15/15
      default ไม่ติ๊ก = ไม่อ่าน / ติ๊ก = อ่าน (enqueue copy ถอดธง own แชร์ _tts_id)
    - **คำตอบ Chat Bot = ไม่อ่านเด็ดขาด** (ไม่มีสวิตช์ — echo มีธง _own_message +
      ถูกจำใน _recent_own_sends → echo จากเว็บโดนซ่อน ไม่มีทางเข้า pipeline)
    - **การอ่าน: "อ่านแต่ข้อความเท่านั้น" เป็น default** (`read_author` default False —
      เดิม True) / "อ่านชื่อและข้อความ" เป็นตัวเลือก (radio เดิมใน ตั้งค่า > TTS)
      ค่าที่ผู้ใช้เคยบันทึกไว้ไม่ถูกแตะ
    - echo ของโปรแกรม/บอท → ซ่อนเสมอ + bot ตอบ !xxx ที่เราพิมพ์เองได้
    - `_is_bot_author` ไม่ดักชื่อ account ตัวเอง (ใช้ธง _own_message แทน)

---

## 📋 สรุปงานทั้งหมดหลัง 2.7.0 → 2.7.1 (สำหรับเขียน changelog)

### Bug Fixes (21 รายการหลัก)
1. Twitch ส่งเบิ้ล 4 ครั้ง (orphan client + emote blocking)
2. Twitch reconnect ไม่ติด (logger ไม่ถูกประกาศ → thread ตาย)
3. Twitch token หมดอายุ = ตก anonymous (refresh chain พัง 3 จุด)
4. กด disconnect ปุ่มค้างแดง (ผล connect สวนคำสั่ง + ไม่อัปเดตการ์ด)
5. ติ๊ก TTS แล้วส่งไม่อ่าน + ไอคอนค้าง (copy.copy() ผิด)
6. Overlay layout หายหลังอัพเดท (beforeunload + sendBeacon)
7. Text Scroll Loop flash + โผล่กลางจอ (CSS left:0 → left:100%)
8. Viewer Widget หายตอนเปลี่ยน Theme (viewerHtml signature ค้าง)
9. ASK เกิดกล่องเล็กบน OBS (CSS vars ไม่ set ตอนสร้างครั้งแรก)
10. Now Playing หดแคบตอนเพลงสั้น (np-container ไม่มี width)
11. ASK Theme เปลี่ยนไม่ได้ (CSS cascade ผิด — defaults อยู่ในลูก)
12. ASK settings ไม่เซฟ (readModalFields อยู่ใน branch viewer)
13. ASK anim-out ไม่เล่นตอนกดปิด (innerHTML='' ทับ animation)
14. ASK Minimal กล่องหดตามเนื้อหา (width:max-content → slider fix)
15. Preset กดเซฟไม่ได้ (QMessageBox บน QFrame โผล่หลัง main window)
16. ASK panel ค้างกลางจอตอน maximize (resizeEvent ซ้ำ 2 ตัว)
17. เวลาโหวตปรับไม่ได้ (setRange min=30)
18. Avatar กลับหัว + ปุ่ม flip หาย (modal flush ไม่ครบ + getChecked คืน true กับ element ที่หาย)
19. Composer เห็น ASK สองโหมดซ้อน/OBS ถูก (WS config merge ฝั่ง editor ทับค่า server ด้วยค่า stale)
20. เพิ่ม ASK แล้วกด Demo เลยไม่ขึ้นบน OBS (ปุ่มเพิ่ม widget ไม่ save/broadcast ทันที)
21. ปุ่ม "วิธีเชื่อม WebSocket" กดไม่ได้ (ลืม import webbrowser → NameError เงียบ)

### ฟีเจอร์ใหม่หลัก
- **ASK Widget** (โพล/แบบสอบถาม) — เฟรมเต็ม canvas / ผู้ชมโหวต A-J หรือ 1-10
  / 1 คน 1 โหวต / 0 โหวตไม่สรุปแชท / สรุปผลลงแชทอัตโนมัติ
- 4 โหมดแสดงผล (เสาแนวตั้งซ้าย/ขวา, แถบแนวนอนบน/ล่าง, Minimal ย้ายอิสระ)
- 23 ธีม (รวม 6 พรีเมียมมีเอฟเฟค: Aurora, Crystal, Magma, NeonFrame, Vintage, Electric)
- 12 รูปแบบหลอดโหวต + 10 รูปแบบกรอบ (แยกจากธีม ผสมกันได้อิสระ)
- Animation in/out 9 ทิศ (แยกความเร็วเข้า/ออก)
- หลอดเวลา (เลข/หลอดสี/ทั้งคู่) — rAF สมูท 60fps
- หลอดโหวตสมูท (easeOutCubic 1.6s ไหลต่อเนื่อง)
- หน้าสรุปผลเรียงมาก→น้อย + winner ไฮไลต์ + "ผลสรุป :" นำหน้าหัวข้อ
- ป้าย [พิมพ์ "A"] + เงาฟุ้ง + กล่อง "จบโหวต" มี shadow
- Demo สด 3 ปุ่ม (ยอดสด 11 รอบ → สรุปผล → หาย) — ขึ้น OBS จริง
- Preset คำถามด่วน + toast 2 วิ + dropdown อัปเดตทันที
- หัวข้อยาว marquee (ไม่ reset ตอนโหวต)
- Modal แนะนำเชื่อม OBS WebSocket (3 ปุ่ม: เชื่อม/วิธีเชื่อม/ไม่สนใจ)
- ไอคอนสถานะ TTS ใน Live Chat (⏳/🔊/✓/⊘/⚠)
- Checkbox TTS ข้างปุ่มส่ง + จำค่าถาวร
- ตั้งค่า > TTS: "อ่านข้อความที่เราพิมพ์บนหน้าเว็บ" + default อ่านแต่ข้อความ
- KICK เหมือน Twitch ครบทุกอย่าง
- ปุ่ม ASK ใน Live Chat header หลัง A+ (เทา→เขียว + tooltip sync)
- แผง ASK ชิดขวาตาม resize + placeholder + default 30/20 วิ + เวลา 5-3600
- Sidebar 2 คอลัมน์ + zoom toolbar ย้ายเข้า sidebar
- gzip compression (526KB → 119KB ลด 78%)

## 🔍 สิ่งที่ยังเหลือ / รอรอบหน้า

- **B4 (token plaintext)** — ยอมรับชั่วคราว
- **B3 เต็มรูปแบบ** (URL token WS) — v3.0
- **KICK bot mode ทางการ** — รอ KICK approve (ตอนนี้ 500)
- **dev_audit_chat.py** — สคริปต์ตรวจ 3 ชั้น (runtime + key + var) — รันซ้ำได้

---

## 💡 Git status
```
Untracked: kick_oauth.py, twitch_bot.py, youtube_oauth.py,
           easydonate_api.py, supporters_api.py, announcement.py,
           announce_sender.py, server_guard.py, ui/widgets/announcement_bar.py,
           dev_audit_chat.py
Modified: app.py, settings.py, chat_queue.py, chat_twitch.py, chat_youtube.py,
          chat_kick.py, composer.html, composer_server.py, overlay.html,
          playroom.html, ui/dialogs/settings.py, updater.py, main.py,
          single_instance.py, ui/widgets/topbar.py, ui/widgets/sidebar.py,
          ui/widgets/chat_panel.py, ui/dialogs/author_modal.py
```

⚠️ Secrets ไม่เคย commit เข้า git (untracked ทั้งหมด)
