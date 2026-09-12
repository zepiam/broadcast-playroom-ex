# ระบบผู้สนับสนุน (Supporters System) — เอกสารสำหรับพอร์ตไปใช้ที่อื่น

สกัดจาก Broadcast Playroom 2 (`tts-for-livestream-ver2`) เพื่อเอาไปใช้กับเว็บไซต์ + โปรแกรมอื่นๆ ในอนาคต โดยให้ **ทุกโปรแกรม/เว็บเห็นรายชื่อผู้สนับสนุนชุดเดียวกัน** (ระบบรวมศูนย์อยู่แล้วโดยดีไซน์ — ดูหัวข้อ "ทำไมรายชื่อรวมกันได้อัตโนมัติ" ด้านล่าง — **ไม่มีการจัดอันดับ/tier ใดๆ โดยตั้งใจ** ดูหัวข้อ "ไม่มีระบบ tier/ranking โดยตั้งใจ")

## ⚠️ สิ่งที่ไม่ได้อยู่ใน repo นี้

โค้ดฝั่ง server (PHP) และ URL ของ Discord webhook จริง **ไม่ได้อยู่ใน repo นี้เลย** — อยู่บน hosting ของ `men9ch.com` คนละที่กับโค้ด Python เอกสารนี้สกัดมาจากสิ่งที่มีอยู่จริงในฝั่ง client (Python) เท่านั้น คือ **API contract** (ที่ต้อง reverse-engineer จาก client code เพราะไม่มี PHP ให้อ่าน) และ **โค้ดฝั่ง client ที่พอร์ตไปภาษาอื่นได้**

## Architecture ปัจจุบัน

```
ผู้สนับสนุน: โปรแกรม/เว็บ → กรอกฟอร์ม + แนบสลิป → POST submit.php
  → server เก็บ pending.json + ส่ง Discord webhook (@mention แอดมิน)
  → แอดมินคลิกลิงก์จาก Discord → GET approve.php → กด Approve
  → server ย้าย entry จาก pending.json → approved.json
  → ทุกโปรแกรม/เว็บดึง GET api.php → แสดง ranking/รายชื่อ
```

## ทำไมรายชื่อรวมกันได้อัตโนมัติ

ระบบนี้ **centralized อยู่แล้ว** — ข้อมูลทั้งหมด (`pending.json`, `approved.json`) เก็บอยู่บน server กลางเดียว (`men9ch.com`) ไม่ใช่เก็บแยกในแต่ละโปรแกรม ดังนั้น **แค่ทำให้ client ใหม่ (เว็บไซต์ หรือโปรแกรมอนาคต) เรียก endpoint เดียวกันกับที่อธิบายด้านล่าง ก็จะเห็นข้อมูลเดียวกันกับ Broadcast Playroom ทันทีโดยไม่ต้องทำอะไรเพิ่มฝั่ง server** — ไม่ต้องสร้างระบบซิงค์เอง

## Base URL

```
https://men9ch.com/api
```
ต่อท้ายด้วย `api.php`, `submit.php`, `approve.php`, หรือ `admin.php`

---

## Endpoints

### 1. `GET api.php` — ดึงรายชื่อผู้สนับสนุนที่ approve แล้ว

ใช้แสดงหน้า ranking/leaderboard — endpoint นี้แหละที่ทุกโปรแกรม/เว็บควรเรียกร่วมกัน

**Response (สำเร็จ):**
```json
{
  "ok": true,
  "supporters": [
    {
      "name": "คุณAAA",
      "amount": 500,
      "currency": "THB",
      "date": "2026-09-08",
      "message": "สู้ๆครับ"
    }
  ]
}
```

**Response (error):**
```json
{"ok": false, "error": "เหตุผล"}
```

Client ควร:
- ตรวจ `Content-Type: application/json` ตอนขอ, `Cache-Control: no-cache`
- ปลอม User-Agent เป็น browser จริง (ดูหัวข้อ Headers ด้านล่าง — security plugin ฝั่ง host บล็อก bot UA)
- ทำ retry 2-3 ครั้งถ้า fail (network เว็บ host ทั่วไปหลุดบ่อย)

---

### 2. `POST submit.php` — ส่งหลักฐานการสนับสนุน (multipart/form-data)

**Fields ที่ส่งทุกครั้ง:**

| field | ตัวอย่างค่า | บังคับ | หมายเหตุ |
|---|---|---|---|
| `name` | `"คุณAAA"` | ✅ | ชื่อที่จะแสดงบน ranking, จำกัด 50 ตัวอักษรฝั่ง client |
| `amount` | `"500"` | ✅ | จำนวนเงิน (string ของตัวเลข) |
| `currency` | `"THB"` | ✅ | `THB` / `USD` / `JPY` / `EUR` (ขยายเพิ่มได้) |
| `message` | `"สู้ๆครับ"` | ไม่บังคับ | จำกัด 200 ตัวอักษรฝั่ง client |
| `machine_id` | sha256 hex 64 ตัว | ไม่บังคับ | ดูหัวข้อ Anti-fraud ด้านล่าง — **เว็บไซต์ทำแบบเดียวกันไม่ได้** |
| `platform` | `"twitch"`/`"youtube"`/`"kick"`/`"tiktok"`/`"mylive"` | ไม่บังคับ | แพลตฟอร์มที่ผู้บริจาคสตรีมอยู่ (โปรโมทช่อง) |
| `channel_url` | ลิงก์ช่อง | ไม่บังคับ | |
| `channel` | `"bank"` หรือ `"truemoney"` | ✅ | ช่องทางโอนเงิน |

**ถ้า `channel = "bank"`:**

| field | บังคับ | หมายเหตุ |
|---|---|---|
| `method` | ✅ | `"slip"` (แนบไฟล์) หรือ `"manual"` (กรอกเอง) |
| `bank` | เฉพาะ `method=manual` | รหัสธนาคาร: `SCB` `KBANK` `BBL` `KTB` `BAY` `TTB` `GHB` `CIMB` `UOB` `LH` `OTHER` |
| `transfer_date` | เฉพาะ `method=manual` | `YYYY-MM-DD` |
| `transfer_time` | เฉพาะ `method=manual` | `HH:MM` |
| `slip` (ไฟล์) | เฉพาะ `method=slip` | multipart file field, PNG/JPG/WebP/GIF, 1KB–5MB |

**ถ้า `channel = "truemoney"`:** ไม่มี slip เลย ต้องมี `transfer_date` + `transfer_time` เสมอ (กรอกมือทั้งคู่)

**Response (สำเร็จ):**
```json
{"ok": true, "id": "xxxxx", "message": "ส่งสำเร็จ"}
```
**Response (fail):**
```json
{"ok": false, "error": "เหตุผล"}
```

---

### 3. `POST api.php?action=delete&id={id}&token={admin_secret}` — ลบผู้สนับสนุน (admin)

### 4. `POST api.php?action=fetch_pending&token={admin_secret}` — ดูรายการรอ approve (admin)
```json
{"ok": true, "pending": [...], "count": 3}
```

### 5. `GET approve.php?id={id}&token={admin_secret}` — อนุมัติ (ลิงก์ที่ webhook โพสต์เข้า Discord ให้แอดมินกด)

### 6. `GET admin.php?token={admin_secret}` — หน้า admin panel เต็มรูปแบบ

---

## Headers ที่ต้องใส่ทุก request

Host มี security plugin บล็อก bot User-Agent — ทุก client (รวมเว็บไซต์/โปรแกรมใหม่) ต้องปลอม header ให้เหมือน browser จริง:

```
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36
Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8   (หรือ application/json สำหรับ api.php)
Accept-Language: en-US,en;q=0.5
Origin: https://men9ch.com
Referer: https://men9ch.com/api/upload.html
```
(สำหรับเว็บไซต์ที่ยิงจาก browser ของ user เอง — เบราว์เซอร์ตั้ง header พวกนี้ให้อัตโนมัติอยู่แล้ว ไม่ต้องปลอมเอง แต่ต้องระวังเรื่อง CORS — ถ้า server ยังไม่เปิด CORS ให้ origin ของเว็บไซต์ใหม่ การเรียกตรงจาก browser JS จะโดนบล็อก ต้องขอให้ฝั่ง server เพิ่ม CORS header หรือ proxy ผ่าน backend ของเว็บไซต์เอง)

---

## ไม่มีระบบ tier/ranking โดยตั้งใจ

เดิมมีระบบ tier (👑 Diamond / 💎 Platinum / 🥇 Gold / 🥈 Silver / 🥉 Bronze คำนวณจากยอดเงิน) แต่ถูก
เอาออกแล้ว — ตัดสินใจว่าการจัดลำดับชั้นผู้สนับสนุนตามยอดเงินดูไม่ให้เกียรติผู้สนับสนุนที่ให้น้อยกว่า
ตอนนี้แสดงแค่ **ชื่อ + ยอด (โปร่งใส แต่ไม่จัดอันดับ) + ข้อความ** เรียงตามเวลาที่อนุมัติล่าสุดก่อน
เท่านั้น (`api.php`'s `usort` by `approved_at`) — ไม่มี badge/ไอคอนแสดงลำดับชั้นใดๆ

ถ้าจะพอร์ตไปเว็บไซต์หรือโปรแกรมอื่น **อย่าเพิ่มระบบ tier/ranking กลับเข้ามา** — คงดีไซน์ "รายชื่อเรียง
ตามเวลา ไม่จัดอันดับ" นี้ไว้ให้สอดคล้องกันทุก client

---

## Anti-fraud: machine_id (ใช้ได้เฉพาะโปรแกรม desktop เท่านั้น!)

จาก [machine_id.py](machine_id.py) — สร้าง fingerprint จาก MAC address + OS info + machine name + Windows volume serial number → SHA256 hash 64 ตัวอักษร เก็บ cache ไว้ใน `data/machine_id.json` เพื่อให้ค่าคงที่ข้าม session ใช้เพื่อให้ฝั่ง server แบนเครื่องที่ส่งข้อมูลเท็จ

**⚠️ พอร์ตไปเว็บไซต์แบบเดียวกันตรงๆ ไม่ได้** — browser JavaScript เข้าไม่ถึง MAC address / hardware info / volume serial ของเครื่อง user เว็บไซต์ต้องใช้กลไกอื่นแทน เช่น browser fingerprint library (FingerprintJS ฯลฯ), cookie/localStorage-based ID, หรือ IP-based rate limiting — แล้วแต่ระดับความเข้มงวดที่ต้องการ ถ้าจะให้ระบบแบนทำงานสอดคล้องกันข้ามทุกช่องทาง ควรคุยกับฝั่ง server ว่าจะออกแบบ identity/ban system ยังไงให้ครอบคลุมทั้ง desktop app และเว็บ (อาจต้องแยก field เช่น `client_fingerprint` ที่มีความหมายต่างกันตาม `source` แทนที่จะ assume ว่าเป็น machine hardware id เสมอ)

---

## จุดที่ควรแก้ก่อนขยายเป็นหลายโปรแกรม/เว็บ

ระบบตอนนี้ออกแบบมาให้มี client เดียว (Broadcast Playroom) เรียก — ถ้าจะขยายให้มีหลาย client (เว็บ + โปรแกรมอื่นๆ ในอนาคต) ควรพิจารณา:

1. **เพิ่ม field `source`/`client_id` ใน submit.php** (ปัจจุบันไม่มีเลย) — ระบุว่าใครส่งมา (`"desktop_app"` / `"website"` / โปรแกรมอื่นในอนาคต) จะได้แยกดู stats/debug ได้ แม้รายชื่อรวมกันเป็นก้อนเดียวอยู่ดี ไม่ต้องกระทบ endpoint ปัจจุบัน — เพิ่มเป็น optional field ได้เลย ฝั่ง server เก็บไว้เฉยๆ ก็พอ
2. **แก้ currency conversion จริง** ถ้าจะรับบริจาคหลายสกุลเงินแล้วอยากให้ยอดที่แสดงเทียบกันได้ตรงจริง (ตอนนี้แสดงยอด+สกุลเงินดิบตามที่ผู้สนับสนุนกรอก ไม่แปลงอัตราแลกเปลี่ยน)
3. **เปิด CORS บน server** ถ้าเว็บไซต์จะเรียก API ตรงจาก browser JS (ไม่ผ่าน backend ของเว็บเอง)
4. **ออกแบบ anti-fraud ให้เหมาะกับแต่ละ client type** ตามหัวข้อด้านบน — อย่าพึ่ง `machine_id` แบบเดียวกับ desktop app กับทุกช่องทาง

---

## Client-side Python (โค้ดต้นฉบับ พอร์ตไปภาษาอื่นได้)

- **[supporters_api.py](supporters_api.py)** — ทุกฟังก์ชันเรียก API: `fetch_supporters()`, `submit_supporter()`, `delete_supporter()`, `fetch_pending()`, `open_approve_url()`, `open_admin_url()` ใช้ `urllib` ล้วน ไม่พึ่ง `requests` — เห็น logic ทั้ง multipart body construction manual (ไม่ใช้ lib), SSL context, retry, error handling ครบ
- **[ui/dialogs/supporter_upload.py](ui/dialogs/supporter_upload.py)** — หน้าฟอร์ม PySide6 (reference สำหรับ UX flow ถ้าจะออกแบบฟอร์มเว็บให้ประสบการณ์คล้ายกัน — reactive ตามช่องทางที่เลือก, preview รูปสลิปก่อนส่ง, confirm dialog ก่อน submit)
- **[machine_id.py](machine_id.py)** — fingerprint generator (desktop only ตามที่อธิบายด้านบน)

## Settings ที่เกี่ยวข้อง ([settings.py:369-371](settings.py:369))
```python
supporters_api_url: str = "https://men9ch.com/api"
supporters_admin_secret: str = ""  # ดูจาก config.php บน server
```

---

## FAQ

**ถ้าเปลี่ยน/หมุน Discord webhook URL ใหม่ ต้องแก้โปรแกรม/client ไหม?**

ไม่ต้อง — client (โปรแกรม Python นี้, เว็บไซต์, หรือโปรแกรมอื่นในอนาคต) **ไม่เคยรู้จักหรือเก็บ webhook URL เลยแม้แต่นิดเดียว** สิ่งที่ client รู้มีแค่ `supporters_api_url` (base URL ของ `api.php`/`submit.php`) กับ `supporters_admin_secret` (token คนละตัวกับ webhook ใช้แค่ยืนยันแอดมินตอนเรียก API ลบ/ดู pending) การยิง Discord webhook เกิดขึ้นทั้งหมดฝั่ง `submit.php` บนโฮส — client แค่ POST ฟอร์มไปเหมือนเดิม ไม่รู้ตัวด้วยซ้ำว่ามีการเปลี่ยน webhook

เปลี่ยน webhook = ไปแก้ค่าใน `config.php` บนโฮสอย่างเดียวพอ ทุก client ที่มีอยู่และที่จะเพิ่มในอนาคตไม่ต้องแตะเลย
