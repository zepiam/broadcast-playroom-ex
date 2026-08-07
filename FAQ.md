# ❓ FAQ — ปัญหาที่อาจพบ + วิธีแก้

## 🚨 โปรแกรมเปิดไม่ติด / โดน Antivirus

### Windows Defender SmartScreen: "Windows protected your PC"
เพราะโปรแกรมไม่มี code signing (เป็นงานทำเอง)
**แก้:** คลิก **"More info"** → คลิก **"Run anyway"**

### Antivirus แจ้งเตือน / ลบไฟล์
PyInstaller exe ถูก AV แจ้งเตือนบ่อย (เป็นปัญหาทั่วไปของโปรแกรมที่ build ด้วย PyInstaller)
**แก้:**
1. เปิด Windows Security → Virus & threat protection → Manage settings
2. Add exclusion → เลือกโฟลเดอร์ Broadcast Playroom
3. หรือ Add exclusion ไฟล์ `.exe` โดยตรง

---

## 🔊 เสียงไม่ออก / TTS error

### "No audio was received. please verify that your parameters are correct"
**สาเหตุ:** edge-tts ปฏิเสธการอ่าน (มักเป็นภาษาที่ไม่รองรับ)
**แก้:**
- ตรวจ Settings > TTS ว่าภาษาที่ต้องการอยู่ใน list
- ถ้าพิมพ์ภาษาที่ไม่รองรับ (ฮินดี/อาหรับ) → โปรแกรมจะเงียบ (ไม่ error)
- ลองเช็ค internet — edge-tts ต้องเน็ต

### RVC: "Numpy is not available"
**สาเหตุ:** numpy เวอร์ชันใหม่เกิน (2.x) ไม่รองรับ torch 2.2.2
**แก้:** ลง numpy เวอร์ชันเก่า: `pip install "numpy<2"`

### RVC: ช้ามาก / กระตุก
**สาเหตุ:** GPU ไม่รองรับ CUDA → fallback CPU
**แก้:**
- ใช้เวอร์ชั่น **Lite** (ไม่ต้อง GPU)
- หรืออัพเดท NVIDIA driver เป็นเวอร์ชั่นล่าสุด

---

## 🌐 ระบบแปลภาษา

### แปลไม่ทำงาน (ข้อความต่างภาษาไม่แปล)
**ตรวจ:**
1. Settings > TTS > เลือก **"แปลเป็นภาษาไทย"**
2. เลือกภาษาที่ต้องการแปล (ถ้าใช้ Google ไม่ต้อง API key)
3. ถ้าใช้ DeepL/DeepSeek → ต้องใส่ API key

### แปลแล้ว overlay ไม่แสดง
**สาเหตุ:** overlay push คำแปลหลังแปลเสร็จ (ใช้เวลา ~0.4 วิ)
**แก้:** รอสักครู่ — ถ้าเกิน 5 วิ แล้วไม่ขึ้น → เช็ค internet

### Rate limit: แปลไม่ทัน (60 ครั้ง/5 นาที)
**สาเหตุ:** livestream มี chat เยอะเกิน
**แก้:** ใช้ DeepL/DeepSeek (ไม่มี rate limit ฝั่งเรา) แทน Google

---

## 🖼️ Overlay (OBS / Game Overlay)

### Overlay เปิดไม่ติด (port 8765/8766)
**สาเหตุ:** port ถูกใช้ / firewall block
**แก้:**
1. ปิดโปรแกรมอื่นที่ใช้ port 8765/8766
2. ตรวจ firewall อนุญาต Broadcast Playroom
3. เปลี่ยน port ใน Settings > Overlay

### OBS Browser Source ดำ / ไม่แสดง
**แก้:**
1. ตรวจ URL: `http://localhost:8765` (Overlay) / `http://localhost:8766` (Game Overlay)
2. ตั้งความสูง ≥ 600px
3. ปิด-เปิด Browser Source ใหม่

---

## 🎮 Game Overlay (chat ลอยเหนือเกม)

### Game Overlay ไม่ขึ้น
**สาเหตุ:** ต้องใช้ Chromium/CEF
**แก้:**
- โหลด Chromium ถ้าโปรแกรมถามตอนเปิดครั้งแรก
- ลอง toggle Game Overlay ใน topbar

### Game Overlay กระพริบ / หาย
**แก้:**
- ปิดโหมด exclusive fullscreen ในเกม (ใช้ borderless windowed)
- ปิด overlay programs อื่น (GeForce Overlay, Discord Overlay)

---

## 📺 การอัพเดท

### อัพเดทไม่สำเร็จ
**แก้:**
1. ปิดโปรแกรมก่อนอัพเดท
2. ตรวจ internet
3. ลองดาวน์โหลดใหม่จาก GitHub: https://github.com/zepiam/broadcast-playroom/releases

### อัพเดทแล้วข้อมูลหาย
**สาเหตุ:** update แทนที่ไฟล์โปรแกรม ไม่แตะ user data
**ตรวจ:** user data อยู่ที่ `%USERPROFILE%\.tts-for-livestream\`

---

## 🐛 แจ้งปัญหา / ส่ง log

ถ้าเจอปัญหาที่ไม่อยู่ในนี้:
1. เปิดไฟล์ `tts.log` ข้างไฟล์ `.exe` (มี error log)
2. ส่ง screenshot + `tts.log` มาให้ dev

---

## 🎮 Viewer Interaction Commands (คำสั่งสำหรับผู้ชม)

> 📖 **คู่มือฉบับเต็ม:** https://men9ch.com/wiki/p/index.php?pid=broadcast-playroom&slug=viewer-commands
>
> ให้ผู้ชมควบคุม TTS ผ่านคำสั่งข้างหน้าข้อความ — **ปิดไว้เป็น default**
> เปิดได้ที่ **Settings → TTS → คำสั่งสำหรับผู้ชม**

### รูปแบบคำสั่ง (3 ประเภท)

| คำสั่ง | ควบคุม | ช่วงที่พิมพ์ได้ | ช่วงผลจริง (หลัง clamp) | baseline |
|---|---|---|---|---|
| `[x..]` | ความเร็ว | 0.1 – 3.0 | -90% ถึง +100% | `x1` = 0% |
| `[p..]` | เสียงสูง/ต่ำ | -10 ถึง +10 | -50Hz ถึง +50Hz (1 unit = 5Hz) | `p0` = 0Hz |
| `[v..]` | ความดัง | 0 – 200 | -50% ถึง +50% | `v100` = 0% |

### ตัวอย่าง
| ผู้ชมพิมพ์ | ผล |
|---|---|
| `[x2]สวัสดี` | เร็ว 2 เท่า |
| `[x0.5]hello` | ช้าลงครึ่ง |
| `[p1]hi` | เสียงสูง 5Hz |
| `[p-2]hi` | เสียงต่ำ 10Hz |
| `[v50]hi` | เบาครึ่ง |
| `[v150]hi` | ดัง 1.5x |
| `[x2][p1]สวัสดี` | รวมได้ (เร็ว 2x + สูง 5Hz) |

### เงื่อนไข / ข้อจำกัด
- ✅ **ทุก platform ใช้ได้** (Twitch, YouTube, MyLive, TikTok, Kick)
- ✅ **ทุกคนใช้ได้** — ไม่จำกัดเฉพาะ mod/VIP
- 🔒 **มี cooldown ต่อ user** (ปรับได้ 0-60 วินาที, default 5)
  - ถ้าใช้คำสั่งซ้ำในช่วง cooldown → อ่านข้อความปกติ (ไม่ block แชท)
  - ตั้ง 0 = ปิด cooldown (ทุกข้อความมีเอฟเฟกต์)
- 🔒 **คำสั่งต้องอยู่ต้นข้อความเท่านั้น** — กัน false positive
  - `[valorant]`, `[gg]`, `[ดี]` ไม่ match (ไม่ใช่คำสั่ง)
  - รูปแบบที่ถูก: `[x`+ตัวเลข+`]`, `[p`+ตัวเลข+`]`, `[v`+ตัวเลข+`]`
- 🔒 **คำสั่งถูกตัดออกจากข้อความ** — ผู้ชม/สตรีมเมอร์ไม่เห็น `[x2]` ในแชท/overlay
- ⚠️ **เอฟเฟกต์ทับค่าเริ่มต้น** — rate/volume override แทนที่ค่าตั้งใน Setting; pitch เริ่มจาก 0

### ทำงานร่วมกับระบบเดิม
- ✅ **auto-speed** — override ทับ rate ถ้าผู้ชมระบุ `[x..]`
- ✅ **per-platform volume offset** — ใช้ร่วมกับ `[v..]` ได้
- ✅ **RVC voice conversion** — override rate/volume/pitch ส่งผลก่อน RVC
- ✅ **Auto Translate** — แปลก่อน TTS, override ใช้ได้ปกติ

### ทิปส์สำหรับสตรีมเมอร์
แปะตารางคำสั่งไว้ในกฎแชท หรือคอมเมนต์ปัก (pinned comment) เพื่อให้ผู้ชมรู้ว่าใช้ยังไง

---

## 💻 ความต้องการของระบบ

| ข้อกำหนด | Lite | Full |
|---|---|---|
| OS | Windows 10/11 x64 | Windows 10/11 x64 |
| RAM | 4 GB | 8 GB |
| GPU | ไม่จำเป็น | NVIDIA + CUDA (หรือ CPU ช้า) |
| Internet | ต้อง (edge-tts + แปล) | ต้อง (edge-tts + แปล) |
| พื้นที่ | ~900 MB | ~6 GB |
