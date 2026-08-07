# 🧩 Plugins — Broadcast Playroom

โฟลเดอร์นี้สำหรับเก็บ plugin ที่ขยายความสามารถของ Broadcast Playroom

## ประเภท plugin ที่รองรับ (วางแผนไว้)

| ประเภท | สถานะ | คำอธิบาย |
|---|---|---|
| `command` | ✅ พร้อมใช้ | คำสั่งแชทที่ตอบกลับด้วย TTS/ข้อความ (config-only ไม่ต้องเขียนโค้ด) |
| `tts_engine` | 🔜 วางแผน | ลงเสียง TTS แบบกำหนดเอง |
| `platform` | 🔜 วางแผน | แพลตฟอร์มแชทใหม่ (เช่น Discord) |
| `overlay_widget` | 🔜 วางแผน | widget ใหม่ใน overlay |

## วิธีสร้าง Command Plugin

สร้างไฟล์ `.yml` ใน `plugins/commands/`:

```yaml
# plugins/commands/weather.yml
name: "สภาพอากาศ"
trigger: "!weather"
description: "บอกอุณหภูมิปัจจุบัน"

# ประเภทการตอบสนอง: "text" = อ่าน TTS เท่านั้น, "overlay" = แสดงใน overlay ด้วย
response_type: "text"

# ข้อความตอบกลับ (รองรับตัวแปร: {author}, {trigger}, {time})
response: "สวัสดี {author} ครับ คำสั่ง {trigger} ยังไม่ได้เชื่อม API"

# คูลดาวน์ (วินาที) — กัน spam
cooldown: 30

# เปิด/ปิด
enabled: true
```

## ตัวอย่าง plugin

ดูไฟล์ใน `plugins/commands/` เพื่อดูตัวอย่าง

## ⚠️ ข้อจำกัด
- Command plugin เป็นแบบ **config-only** (ไม่รัน Python code)
- สำหรับ plugin ที่ซับซ้อน (API call, custom logic) ต้องรอ TTS/Platform API ในอนาคต
