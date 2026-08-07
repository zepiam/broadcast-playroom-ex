# MyLive.in.th — ข้อมูลและวิธีดึงแชท

เอกสารอ้างอิงสำหรับดึงแชทจากเว็บไซต์ [mylive.in.th](https://mylive.in.th) เพื่อนำไปใช้ในโปรแกรม TTS-for-Livestream

วิเคราะห์จากโค้ดฝั่งเว็บ (Frontend bundle) เมื่อวันที่ 2026-07-22

---

## 📋 สารบัญ

1. [ภาพรวมสถาปัตยกรรมเว็บ](#1-ภาพรวมสถาปัตยกรรมเว็บ)
2. [ตำแหน่งแชทใน DOM](#2-ตำแหน่งแชทใน-dom)
3. [ประเภทข้อความแชท (9 ประเภท)](#3-ประเภทข้อความแชท-9-ประเภท)
4. [Emote — ดึงภาพตรง ๆ ได้](#4-emote--ดึงภาพตรง-ๆ-ได้)
5. [Sticker — ดึงภาพตรง ๆ](#5-sticker--ดึงภาพตรง-ๆ)
6. [ตัวอย่างโค้ดดึงแชท](#6-ตัวอย่างโค้ดดึงแชท)
7. [ทางเลือก: WebSocket (เรียลไทม์)](#7-ทางเลือก-websocket-เรียลไทม์)
8. [ข้อควรระวัง](#8-ข้อควรระวัง)

---

## 1. ภาพรวมสถาปัตยกรรมเว็บ

| รายการ | ค่า |
|---|---|
| Framework | **Quasar / Vue 3 (SPA)** |
| State | **Pinia** (store ชื่อ `chat`, `stream`, `info`) |
| Server-rendered HTML | ❌ ไม่มี — ตอนโหลดได้แค่ `<div id="q-app"></div>` เปล่า ๆ |
| แชทเข้ามาทาง | **WebSocket** (SocketCluster) แล้ว Vue ถึง render ลง DOM |
| WebSocket host | `wss://chat7.mylive.in.th/socketcluster/` |
| Asset CDN (รูป) | `https://s.mylive.in.th/` |

### 🔑 ข้อสำคัญที่สุด

> **HTML ดิบที่ได้จาก `/streams/162006` ไม่มีแชท** เพราะเป็น SPA โปรแกรมที่อ่าน DOM
> **ต้องรอให้ Vue render เสร็จก่อน** (รอ selector `.m-chat-log` ปรากฏ) ไม่งั้นจะเจอจอว่าง

โปรแกรมที่เหมาะ: **Selenium / Playwright / Puppeteer** (headless browser ที่รอ JS render ได้)
ไม่เหมาะ: `requests` + `BeautifulSoup` ธรรมดา (จะไม่เจอแชท)

---

## 2. ตำแหน่งแชทใน DOM

```
<div id="q-app">                                ← root ของเว็บทั้งหมด
  ...
  <div class="c-area c-chatlog fit">            ← กรอบ scroll ของพาเนลแชท
    <div class="m-chat-log q-px-sm ...">        ← ★ คอนเทนเนอร์รายการแชททั้งหมด
      <div class="m-chat-item">                 ← ★ 1 ข้อความ = 1 item (key = item.i)
        ... (โครงสร้างข้างในต่างกันตามประเภท — ดูหัวข้อ 3) ...
      </div>
      <div class="m-chat-item"> ... </div>
      ...
    </div>
  </div>
</div>
```

### Selector หลัก

| ต้องการ | Selector | หมายเหตุ |
|---|---|---|
| กล่องแชททั้งก้อน | `.m-chat-log` | iterate รายการจากตรงนี้ |
| แต่ละข้อความ | `.m-chat-item` | 1 element = 1 ข้อความ |
| ชื่อผู้ส่ง | `.m-chat-item .m-name` | เช่น `Men9ch` |
| เวลา | `.m-chat-item .m-time` | format `HH:mm` |
| avatar | `.m-chat-item .m-avatar` | เป็น `background-image` ไม่ใช่ `<img>` |

---

## 3. ประเภทข้อความแชท (9 ประเภท)

แต่ละ `.m-chat-item` มี field `type` ที่กำหนด component render (เก็บใน Pinia store ไม่ได้ expose ลง DOM)
**วิธีจำแนกใน DOM: ดู class ของ row ด้านใน**

Dispatcher จากโค้ด:
```javascript
const r = {0:None, 1:Normal, 2:Sticker, 4:Gift, 5:Tip, 6:Subscribe, 8:Poll, 28:System, 29:Announce}
const component = r[item.type] || r[0]
```

| `type` | Component | คืออะไร | จำแนกใน DOM ด้วย |
|---|---|---|---|
| 0 | CChatLogNone | ข้อความที่ถูกลบ/ซ่อน | item ว่าง/ไม่แสดง |
| **1** | **CChatLogNormal** | **แชทปกติ** ★ | `.m-normal` |
| **2** | **CChatLogSticker** | **สติ๊กเกอร์** ★ | `.m-sticker` |
| 4 | CChatLogGift | ของขวัญ | `.m-gift` |
| 5 | CChatLogTip | ทิป (บริจาค) | `.m-tip` |
| 6 | CChatLogSubscribe | สมัครสมาชิก | `.m-subscribe` |
| 8 | CChatLogPoll | โหวต | `.m-poll` |
| 28 | CChatLogSystem | ข้อความระบบ | `.m-system` |
| 29 | CChatLogAnnounce | ประกาศ | `.m-announce` |

### โครงสร้างของแชทปกติ (type 1)

```
<div class="m-chat-item">
  <div class="row items-start m-normal">
    <div class="m-time col-shrink">10:42</div>
    <span class="m-avatar m-mini" style="background-image:url(...)"></span>
    <div class="m-message col m-rank-X">
      <span class="m-name">Men9ch</span>            ← ชื่อผู้ส่ง
      <span class="m-bdg m-sub" style="..."></span> ← badge สมาชิก (ถ้ามี)
      <span class="m-msg">                          ← ★ เนื้อข้อความ + emote แทรก
        <span class="m-ts">สวัสดี</span>             ← token ข้อความธรรมดา
        <span class="m-emoticon">...</span>         ← emote (ดูหัวข้อ 4)
      </span>
    </div>
  </div>
</div>
```

### โครงสร้างของสติ๊กเกอร์ (type 2)

```
<div class="m-chat-item">
  <div class="row items-start m-normal">
    <div class="m-time col-shrink">10:45</div>
    <span class="m-avatar m-mini" style="background-image:url(...)"></span>
    <div class="m-message col m-rank-X">
      <span class="m-name">Men9ch</span>
    </div>
  </div>
  <div class="m-sticker">
    <div class="m-item" style="background-image:url(STICKER_URL)"></div>  ← ★ รูปสติ๊กเกอร์
  </div>
</div>
```

---

## 4. Emote — ดึงภาพตรง ๆ ได้

Emote คือรูปเล็ก ๆ ที่แทรกในข้อความแชทปกติ (`.m-msg`) render โดย component `CChatLogMixed`
มัน split ข้อความตามช่องว่าง แล้ว render แต่ละ token:

- ข้อความธรรมดา → `<span class="m-ts">`
- รูป emote → `<span class="m-emoticon">` ซึ่งมี 2 แบบ (ดูใต้)

### 🅰️ Emote พื้นฐาน (twemoji / sprite sheet)

รูปแบบที่ผู้ใช้พิมพ์: `:ชื่อemote:` เช่น `:smile:`, `:kekw:`, `:LUL:`
regex จากโค้ด: `/^:(([a-z0-9_]+)([A-Z][a-z0-9]+)?)(\+[a-z]+)?:$/`

```
<span class="m-emoticon">
  <span class="ss s5 s5-1f600"></span>   ← class "ss" + "s{set}" + "s{set}-{unicode}"
</span>
```

**วิธีดึงภาพ:**

| ข้อมูล | ที่มา |
|---|---|
| URL sprite sheet | `https://s.mylive.in.th/emo/twemoji{set}.png` (set = 1–6) |
| ตำแหน่งในรูป | CSS rule `.s{set}-{unicode}{background-position:Xpx Ypx}` |
| ขนาด cell | **82px × 82px** (72px รูป + 10px padding) |
| ขนาดรูปจริง | 72px × 72px |

**ตาราง emote ทั้งหมด**: อยู่ใน frontend bundle (`Index.vue_vue_type_script_setup_true_lang-DYI-D20w.js`)
เป็น array `ce` ที่มี 1330 ตัว — แต่ละตัวมี field:
```javascript
{ code:"smile", unicode:"1f600", cate:"Smiley", set:5, name:"Grinning Face" }
```

> 💡 **ทางลัด**: อย่างน้อยที่สุด โปรแกรมของเราสามารถ crop รูปได้โดยใช้ set + unicode จาก class ของ `.ss`
> เช่น class `s5 s5-1f600` → ดาวน์โหลด `twemoji5.png` → crop ที่ตำแหน่งจาก CSS rule `.s5-1f600`

**วิธี parse class `.ss` ใน DOM:**
```javascript
const el = spanElement; // <span class="ss s5 s5-1f600">
const classes = [...el.classList];
const setMatch = classes.find(c => /^s[1-6]$/.test(c));      // "s5"
const posMatch = classes.find(c => /^s[1-6]-[a-f0-9]+$/.test(c)); // "s5-1f600"
const set = setMatch.replace('s','');                         // "5"
const unicode = posMatch.split('-')[1];                       // "1f600"
// → sheet URL: https://s.mylive.in.th/emo/twemoji5.png
// → position: อ่านจาก CSS rule .s5-1f600 (ต้อง parse stylesheet)
```

### 🅱️ Emote แบบกำหนดเองของ streamer (custom)

รูปแบบที่ผู้ใช้พิมพ์: `:ชื่อ+variant:` เช่น `:wave+animated:`, `:custom123:`
รูปเป็น URL ของตัวเอง (ไม่ใช่ sprite)

```
<span class="m-emoticon">
  <span class="cs" style="background-image:url(https://.../wave.gif)"></span>
</span>
```

**วิธีดึงภาพ:** ดึง `background-image` จาก inline style ของ `.cs` ได้ URL เป็นภาพเดี่ยวเลย (ง่ายสุด)

> ข้อมูล custom emote ทั้งหมดของ streamer เก็บใน Pinia store `info.emoticons` (key = `i.full`)
> โครงสร้าง: `addEmoticon(i.full, i)` ที่ `i` มี field `.url`, `.full`
> streamer แต่ละคนมี custom emote ไม่เหมือนกัน → ต้องดึงใหม่ต่อห้อง

### สรุป selector สำหรับ emote

| ต้องการ | Selector |
|---|---|
| emote ทั้งหมดในข้อความ | `.m-msg .m-emoticon` |
| emote sprite (พื้นฐาน) | `.m-emoticon .ss` (อ่าน class) |
| emote custom (URL) | `.m-emoticon .cs` (อ่าน style `background-image`) |

---

## 5. Sticker — ดึงภาพตรง ๆ

Sticker เป็นข้อความแยกประเภท (type 2) URL รูปเก็บใน field `item.img` แล้ว render เป็น `background-image`

```
<div class="m-sticker">
  <div class="m-item" style="background-image:url(STICKER_URL)"></div>
</div>
```

**วิธีดึงภาพ:**
```javascript
const stickerEl = item.querySelector('.m-sticker .m-item');
const url = stickerEl.style.backgroundImage.match(/url\(["']?(.*?)["']?\)/)[1];
// url = URL รูปเดี่ยว (ดาวน์โหลดได้เลย)
```

---

## 6. ตัวอย่างโค้ดดึงแชท

### JavaScript (ทำงานใน Console หรือ Puppeteer)

```javascript
// ดึง URL จาก inline style "background-image:url(...)"
function extractBgUrl(el) {
  if (!el) return null;
  const m = el.style.backgroundImage.match(/url\(["']?(.*?)["']?\)/);
  return m ? m[1] : null;
}

// อ่าน emote ทั้งหมดใน .m-msg
function extractEmotes(msgEl) {
  if (!msgEl) return [];
  return [...msgEl.querySelectorAll('.m-emoticon')].map(e => {
    // 🅱️ custom emote (URL ตรง)
    const custom = e.querySelector('.cs');
    if (custom) return { type: 'custom', url: extractBgUrl(custom) };
    // 🅰️ sprite emote (ต้อง crop จาก sheet)
    const sprite = e.querySelector('.ss');
    if (sprite) {
      const classes = [...sprite.classList];
      const setCls = classes.find(c => /^s[1-6]$/.test(c));
      const posCls = classes.find(c => /^s[1-6]-[a-f0-9]+$/.test(c));
      if (setCls && posCls) {
        const set = parseInt(setCls.slice(1));
        const unicode = posCls.split('-')[1];
        return {
          type: 'sprite',
          set,
          unicode,
          sheetUrl: `https://s.mylive.in.th/emo/twemoji${set}.png`,
          // ตำแหน่ง crop ต้องอ่านจาก CSS rule .s{set}-{unicode}
        };
      }
    }
    return null;
  }).filter(Boolean);
}

// อ่านทุกข้อความแบบมีประเภท
function readChat() {
  return [...document.querySelectorAll('.m-chat-item')].map(item => {
    const name = item.querySelector('.m-name')?.textContent.trim() ?? '';
    const time = item.querySelector('.m-time')?.textContent.trim() ?? '';
    const msg  = item.querySelector('.m-msg');

    // จำแนกประเภทจาก class ด้านใน
    let kind = 'normal';
    let stickerUrl = null;
    if (item.querySelector('.m-sticker')) {
      kind = 'sticker';
      stickerUrl = extractBgUrl(item.querySelector('.m-sticker .m-item'));
    } else if (item.querySelector('.m-gift')) kind = 'gift';
    else if (item.querySelector('.m-tip')) kind = 'tip';
    else if (item.querySelector('.m-subscribe')) kind = 'subscribe';
    else if (item.querySelector('.m-poll')) kind = 'poll';
    else if (item.querySelector('.m-system')) kind = 'system';
    else if (item.querySelector('.m-announce')) kind = 'announce';

    return {
      kind,
      name, time,
      text: msg?.textContent.trim() ?? '',          // ข้อความเต็ม (รวม alt ของ emote)
      emotes: extractEmotes(msg),                   // emote แยกออกมาเป็น list
      stickerUrl,                                    // URL สติ๊กเกอร์ (ถ้าเป็น sticker)
    };
  });
}

// ตัวอย่างผลลัพธ์:
// [
//   { kind:"normal",  name:"Men9ch", time:"10:42", text:"test", emotes:[] },
//   { kind:"normal",  name:"Men9ch", time:"10:43",
//     text:"สวัสดี", emotes:[{type:"sprite",set:5,unicode:"1f600",sheetUrl:"...twemoji5.png"}] },
//   { kind:"sticker", name:"Men9ch", time:"10:45",
//     text:"", emotes:[], stickerUrl:"https://.../sticker.png" }
// ]
```

### รอให้ Vue render เสร็จก่อน (สำคัญ!)

```javascript
async function waitForChat(timeoutMs = 15000) {
  const start = Date.now();
  while (!document.querySelector('.m-chat-log')) {
    if (Date.now() - start > timeoutMs) throw new Error('chat ไม่ปรากฏในเวลาที่กำหนด');
    await new Promise(r => setTimeout(r, 300));
  }
}
// ใช้งาน: await waitForChat(); const messages = readChat();
```

---

## 7. ทางเลือก: WebSocket (เรียลไทม์)

ถ้าอยากได้ข้อความแบบเรียลไทม์โดยไม่ต้อง poll DOM ใช้ WebSocket ได้ (เว็บทำแบบนี้เอง)

| รายการ | ค่า |
|---|---|
| WebSocket URL | `wss://chat7.mylive.in.th/socketcluster/` |
| Event name | `"chat"` (ส่ง/รับใช้ชื่อเดียวกัน) |
| เลขห้อง (channel) | = เลข stream ใน URL (`162006` สำหรับ `/streams/162006`) |
| token | ได้จาก REST `GET /streams/{channel}` → field `token` |

**วิธี subscribe ห้อง:**
```javascript
socket.transmit("chat", {
  cmd: "update",
  channel: 162006,
  token: "<token จาก REST>"
});
// หลังจากนี้ข้อความใหม่จะถูกส่งกลับมาทาง event "chat"
```

**Pinia store structure (เพื่อเข้าใจ field ของข้อความที่ socket ส่งมา):**
```
chat.logs["162006"] = [ <entry>, <entry>, ... ]   // key = เลขห้องเป็น string
```
แต่ละ entry (chat log) มี field:
- `i` — id ข้อความ (ใช้เป็น key)
- `type` — ประเภท (0,1,2,4,5,6,8,28,29 — ดูหัวข้อ 3)
- `name` — ชื่อผู้ส่ง
- `msg` — เนื้อข้อความ (อาจมี `:emote:` แทรก)
- `time` — timestamp (Unix ms; แสดงเป็น `HH:mm`)
- `avatar` — URL avatar
- `img` — URL รูป (สำหรับ sticker)
- `rank` — rank ผู้ใช้ (มีผลต่อ class `m-rank-X`)
- `id` — user id (สำหรับ report/block)

> ⚠️ WebSocket route นี้เป็น SocketCluster (ไม่ใช่ raw WebSocket ธรรมดา) ต้องใช้ client library
> ที่รองรับ SocketCluster หรือ implement handshake เอง — ซับซ้อนกว่าทาง DOM

---

## 8. ข้อควรระวัง

1. **ต้องรอ render เสร็จ** — `requests`+`BeautifulSoup` จะไม่เจอแชท ต้องใช้ headless browser
   (Selenium/Playwright/Puppeteer) แล้วรอ selector `.m-chat-log` ปรากฏก่อน

2. **avatar / sticker / custom emote เป็น `background-image`** — ไม่ใช่แท็ก `<img>`
   ต้อง parse inline `style` เพื่อเอา URL ออกมา

3. **emote sprite (`.ss`) ดึงได้แค่ตำแหน่ง** — รูปจริงเป็น sprite sheet ใหญ่ (twemoji)
   ต้อง crop ตาม `background-position` ใน CSS rule `.s{set}-{unicode}`
   ถ้าอยากได้รูปเดี่ยวสมบูรณ์ ต้อง parse stylesheet ของเว็บ

4. **`.textContent` ของ `.m-msg`** — ถ้ามี emote แทรก ผลลัพธ์จะเป็นข้อความเรียบ (emote span ไม่มี text)
   ถ้าอยากเก็บเป็น `:kekw:` ให้ใช้ข้อมูลจาก `extractEmotes()` มาประกอบเอง

5. **custom emote ต่างกันทุกห้อง** — store `info.emoticons` โหลดใหม่ตาม streamer
   เก็บใน Pinia (เข้าถึงผ่าน Vue Devtools) ไม่ได้ฝังใน DOM

6. **เลขห้อง = เลข stream** — key ของ `chat.logs` และ `channel` ใน socket คือเลข stream จาก URL

---

## ภาคผนวก: แหล่งข้อมูลใน Frontend Bundle

| ข้อมูล | ไฟล์ asset |
|---|---|
| Chat Pinia store (state, actions) | `assets/chat-C5hr8rdh.js` |
| Stream/Info store (emoticons, rooms) | `assets/stream-DHKj2-x1.js` |
| Stream page logic (subscribe socket) | `assets/Stream-D_NdMrZL.js` |
| SocketCluster client | `assets/socketcluster-CfNBv0rQ.js` |
| ★ Chat renderer + emote map (1330 emotes) | `assets/Index.vue_vue_type_script_setup_true_lang-DYI-D20w.js` |
| Main bundle | `assets/index-BUhqP9fb.js` |
| CSS (sprite position, sizing) | `assets/index-zwFewLdI.css` |

> ⚠️ hash ในชื่อไฟล์ (เช่น `C5hr8rdh`) จะเปลี่ยนทุกครั้งที่เว็บ deploy ใหม่
> ดึงชื่อไฟล์ล่าสุดได้จาก `<script src>` ใน HTML ของหน้าหลัก
