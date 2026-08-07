"""chat_mylive.py — MyLive.in.th live chat reader (Playwright headless browser)

mylive.in.th เป็น Vue 3 (Quasar) SPA แท้ — HTML ดิบที่ได้จาก `/streams/<id>` เป็น
แค่ shell เปล่า `<div id="q-app">` ไม่มีแชท แชทถูก render โดย Vue หลังโหลด JS
และดันเข้า DOM ผ่าน WebSocket (SocketCluster) → ต้องใช้ headless browser รอ render
ก่อนแล้วค่อย poll DOM (เป็นวิธีหลักที่เชื่อถือได้ที่สุด ตามเอกสาร mylive.md)

การใช้งาน:
    client = MyLiveChat(on_message=cb)
    client.connect("162006")               # เลข stream
    client.connect("https://mylive.in.th/streams/162006")  # หรือ URL เต็ม
    ...
    client.disconnect()

วิธีนี้แยกข้อความใหม่ด้วย index สะสม (เลื่อนไปอ่านท้าย list) แล้วแปลงแต่ละ entry
เป็น ChatMessage ร่วมกับ Twitch/YouTube

ข้อจำกัด:
  - ต้องลง playwright + chromium: `pip install playwright && playwright install chromium`
  - กิน RAM ~1-2GB ขณะทำงาน (browser จริง)
  - มี latency เล็กน้อยเพราะ poll DOM (default 1.5s)

อ้างอิง selectors / message types จาก mylive.md (วิเคราะห์ frontend bundle 2026-07-22)
"""
from __future__ import annotations

import re
import threading
import time
from typing import Any, Callable, List, Optional

from chat_twitch import ChatMessage  # reuse shared dataclass

# Playwright เป็น optional dependency — import แบบ lazy/graceful ใน _ensure_playwright()
try:
    from playwright.sync_api import sync_playwright, Error as PlaywrightError
    _PLAYWRIGHT_AVAILABLE = True
except Exception:  # noqa: BLE001 — ไม่สนใจสาเหตุ ถ้า import ไม่ได้ก็แจ้ง user
    _PLAYWRIGHT_AVAILABLE = False
    PlaywrightError = Exception  # type: ignore[assignment,misc]


def _ensure_playwright_browser_path(on_status=None) -> str:
    """ตั้ง PLAYWRIGHT_BROWSERS_PATH ให้หา Chromium ได้ + ดาวน์โหลดให้ถ้าไม่มี

    ลำดับค้นหา:
      1. โฟลเดอร์ 'browsers' ข้าง exe (สำหรับ portable distribution)
      2. default Playwright location (%LOCALAPPDATA%\\ms-playwright บน Windows)
    ถ้าไม่เจอ → ดาวน์โหลด Chromium ให้อัตโนมัติ (ครั้งแรก ~150MB)

    on_status: callback สำหรับแจ้งสถานะการดาวน์โหลด (เช่น "กำลังดาวน์โหลด Chromium 45%")

    คืน path ที่ใช้ (ตั้ง env var ด้วย)
    """
    import os
    import sys

    # ถ้า user ตั้งเองแล้ว → ไม่แก้
    if os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        return os.environ["PLAYWRIGHT_BROWSERS_PATH"]

    candidates = []

    # 1. โฟลเดอร์ 'browsers' ข้าง exe (PyInstaller frozen)
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        candidates.append(os.path.join(exe_dir, "browsers"))
        candidates.append(os.path.join(exe_dir, "ms-playwright"))

    # 2. ข้าง script (dev mode)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.join(script_dir, "browsers"))
    candidates.append(os.path.join(script_dir, "ms-playwright"))

    # 3. default Playwright location
    local_app = os.environ.get("LOCALAPPDATA", "")
    default_path = ""
    if local_app:
        default_path = os.path.join(local_app, "ms-playwright")
        candidates.append(default_path)

    # ใช้ path แรกที่มี chromium อยู่
    for path in candidates:
        if os.path.isdir(path):
            has_chromium = any(
                name.startswith("chromium") for name in os.listdir(path)
            )
            if has_chromium:
                os.environ["PLAYWRIGHT_BROWSERS_PATH"] = path
                return path

    # ไม่เจอ → ดาวน์โหลด Chromium ให้อัตโนมัติ
    browser_path = candidates[-1] if candidates else default_path  # ใช้ default location
    if on_status:
        try:
            on_status("⏳ กำลังดาวน์โหลด Chromium (ครั้งแรก ~150MB) กรุณารอซักครู่...")
        except Exception:
            pass
    _download_chromium(browser_path, on_status=on_status)
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = browser_path
    return browser_path


def _download_chromium(browser_path: str, on_status=None) -> bool:
    """ดาวน์โหลด Chromium สำหรับ Playwright (ครั้งแรก ~150MB)

    ใช้ playwright driver ที่ bundle มาแล้ว (node.exe + cli.js)
    ส่ง progress ผ่าน on_status callback (เพราะ node.exe พิมพ์ progress ออกมา)
    คืน True ถ้าสำเร็จ
    """
    import os
    import subprocess
    import sys

    try:
        # หา playwright driver path (bundle มาใน PyInstaller หรือ site-packages)
        import playwright
        pw_dir = os.path.dirname(os.path.abspath(playwright.__file__))
        driver_dir = os.path.join(pw_dir, "driver")
        node_exe = os.path.join(driver_dir, "node.exe")
        cli_js = os.path.join(driver_dir, "package", "cli.js")

        if not os.path.exists(node_exe) or not os.path.exists(cli_js):
            return False  # ไม่มี driver — ไม่สามารถดาวน์โหลดได้

        os.makedirs(browser_path, exist_ok=True)

        # รัน: node.exe cli.js install chromium — stream output แทน capture
        # (node.exe พิมพ์ progress เช่น "Downloading Chromium 113.0.5672/154.2 MB")
        proc = subprocess.Popen(
            [node_exe, cli_js, "install", "chromium"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
            env={**os.environ, "PLAYWRIGHT_BROWSERS_PATH": browser_path},
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        last_line = ""
        import re as _re
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            last_line = line
            # สกัด progress จากบรรทัดเช่น "Downloading Chromium 113.0.5672/154.2 MB"
            m = _re.search(r"(\d+\.?\d*)\s*/\s*(\d+\.?\d*)\s*MB", line)
            if m and on_status:
                done_mb = float(m.group(1))
                total_mb = float(m.group(2))
                pct = int(done_mb * 100 / total_mb) if total_mb > 0 else 0
                try:
                    on_status(f"⏳ กำลังดาวน์โหลด Chromium... {pct}% ({done_mb:.0f}/{total_mb:.0f} MB)")
                except Exception:
                    pass
            elif "Downloading" in line and on_status:
                try:
                    on_status(f"⏳ {line}")
                except Exception:
                    pass
        proc.wait(timeout=300)  # 5 นาที timeout
        if on_status and proc.returncode == 0:
            try:
                on_status("✅ ดาวน์โหลด Chromium เสร็จแล้ว")
            except Exception:
                pass
        return proc.returncode == 0
    except Exception:
        return False


# ---------------------------------------------------------------------- #
# Constants — จาก mylive.md
# ---------------------------------------------------------------------- #
MYLIVE_STREAM_URL = "https://mylive.in.th/streams/{stream_id}"

# message `type` → event ของเรา (ดู mylive.md หัวข้อ 3)
# 0=None(ลบ/ซ่อน), 1=Normal, 2=Sticker, 4=Gift, 5=Tip, 6=Subscribe, 8=Poll, 28=System, 29=Announce
TYPE_NORMAL = 1
TYPE_STICKER = 2
TYPE_GIFT = 4
TYPE_TIP = 5
TYPE_SUBSCRIBE = 6
TYPE_POLL = 8
TYPE_SYSTEM = 28
TYPE_ANNOUNCE = 29

# JS ที่ inject เข้า page เพื่ออ่านแชททั้งหมดที่ render แล้ว
# อิงจาก readChat()/extractBgUrl() ใน mylive.md หัวข้อ 6
# คืน array ของ {idx, kind, name, time, segments, stickerUrl}
# segments = ลำดับเนื้อหาของ .m-msg ตาม DOM → render inline ได้ถูกต้อง
#   {type:'text', content:'...'}
#   {type:'emote', subtype:'custom', url:'https://...'}
#   {type:'emote', subtype:'sprite', unicode:'1f600'}
_READ_CHAT_JS = r"""
() => {
    function extractBgUrl(el) {
        if (!el) return null;
        const m = (el.style.backgroundImage || '').match(/url\(["']?(.*?)["']?\)/);
        return m ? m[1] : null;
    }
    function normalizeUrl(u) {
        if (!u) return null;
        // URL สัมพัทธ์ → prepend CDN host ของ mylive
        if (u.startsWith('//')) return 'https:' + u;
        if (u.startsWith('/')) return 'https://s.mylive.in.th' + u;
        return u;
    }
    function extractSegments(msgEl) {
        // วน child nodes ของ .m-msg ตามลำดับ DOM เพื่อรักษาตำแหน่ง emote ในข้อความ
        if (!msgEl) return [];
        const out = [];
        const walk = (node) => {
            node.childNodes.forEach(child => {
                if (child.nodeType === Node.TEXT_NODE) {
                    const t = (child.textContent || '').trim();
                    if (t) out.push({ type: 'text', content: t });
                    return;
                }
                if (child.nodeType !== Node.ELEMENT_NODE) return;
                // emoticon span
                if (child.classList && child.classList.contains('m-emoticon')) {
                    const custom = child.querySelector('.cs');
                    if (custom) {
                        const u = normalizeUrl(extractBgUrl(custom));
                        if (u) out.push({ type: 'emote', subtype: 'custom', url: u });
                        return;
                    }
                    const sprite = child.querySelector('.ss');
                    if (sprite) {
                        const classes = [...sprite.classList];
                        const posCls = classes.find(c => /^s[1-6]-[a-f0-9]+$/.test(c));
                        if (posCls) {
                            const unicode = posCls.split('-')[1];
                            out.push({ type: 'emote', subtype: 'sprite', unicode });
                            return;
                        }
                    }
                    return;
                }
                // โหนดอื่นที่อาจมี text/emote ซ้อน (เช่น .m-ts) → recurse
                if (child.childNodes.length > 0) walk(child);
                else {
                    const t = (child.textContent || '').trim();
                    if (t) out.push({ type: 'text', content: t });
                }
            });
        };
        walk(msgEl);
        return out;
    }
    const items = [...document.querySelectorAll('.m-chat-item')];
    return items.map((item, idx) => {
        const name = (item.querySelector('.m-name')?.textContent || '').trim();
        const time = (item.querySelector('.m-time')?.textContent || '').trim();
        const msg = item.querySelector('.m-msg');
        let kind = 'normal';
        let stickerUrl = null;
        if (item.querySelector('.m-sticker')) {
            kind = 'sticker';
            stickerUrl = normalizeUrl(extractBgUrl(item.querySelector('.m-sticker .m-item')));
        } else if (item.querySelector('.m-gift')) kind = 'gift';
        else if (item.querySelector('.m-tip')) kind = 'tip';
        else if (item.querySelector('.m-subscribe')) kind = 'subscribe';
        else if (item.querySelector('.m-poll')) kind = 'poll';
        else if (item.querySelector('.m-system')) kind = 'system';
        else if (item.querySelector('.m-announce')) kind = 'announce';
        // ★ ใช้ลำดับใน DOM เป็น idx (พอใช้ได้เพราะ Vue append ข้อความใหม่ต่อท้ายเสมอ)
        return {
            idx,
            kind,
            name,
            time,
            segments: extractSegments(msg),
            stickerUrl,
        };
    });
}
"""


class MyLiveChat:
    """MyLive.in.th live chat reader — Playwright headless browser DOM polling"""

    def __init__(
        self,
        on_message: Callable[[ChatMessage], None],
        on_status: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        on_viewer_count: Optional[Callable[[str, int], None]] = None,
        poll_interval: float = 1.5,
    ) -> None:
        self.on_message = on_message
        self.on_status = on_status or (lambda msg: None)
        self.on_error = on_error or (lambda msg: None)
        self.on_viewer_count = on_viewer_count or (lambda plat, cnt: None)
        self.poll_interval = poll_interval

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._is_connected = False

        # browser/page handle อยู่ใน worker thread เท่านั้น (sync API ไม่ thread-safe ข้าม thread)
        self._stream_id: str = ""

        # จำ index ล่าสุดที่ emit แล้ว เพื่อ diff (DOM สะสมตลอด → อ่านเฉพาะที่เพิ่ม)
        self._last_seen_idx: int = -1

        self.messages_read = 0

    # ------------------------------------------------------------------ #
    # Connection
    # ------------------------------------------------------------------ #
    @property
    def is_connected(self) -> bool:
        return self._is_connected

    def connect(self, target: str) -> bool:
        """เชื่อมต่อ MyLive chat

        Args:
            target: เลข stream เช่น "162006" หรือ URL เต็ม https://mylive.in.th/streams/162006
        """
        if not _PLAYWRIGHT_AVAILABLE:
            self.on_error(
                "ยังไม่ได้ติดตั้ง Playwright — เรียก: pip install playwright "
                "&& python -m playwright install chromium"
            )
            return False

        stream_id = self._extract_stream_id(target)
        if not stream_id:
            self.on_error("ระบุเลขห้อง MyLive เช่น 162006 หรือลิงก์ /streams/162006")
            return False

        if self._is_connected:
            self.on_error("เชื่อมต่ออยู่แล้ว — กด Disconnect ก่อน")
            return False

        self._stream_id = stream_id
        self._last_seen_idx = -1
        self._stop_event.clear()

        # sync_playwright + browser ต้องสร้างใน thread เดียวกับที่ใช้ page ตลอดอายุการทำงาน
        # ดังนั้น start worker thread ก่อน แล้วค่อยทำทุกอย่างในนั้น
        self._is_connected = True
        self._thread = threading.Thread(
            target=self._worker_loop, name="MyLiveChatPlaywright", daemon=True
        )
        self._thread.start()
        return True

    def disconnect(self) -> None:
        if not self._is_connected and self._thread is None:
            return
        self._stop_event.set()
        self._is_connected = False
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=6)
        self._thread = None
        self.on_status("⚪ ยกเลิกการเชื่อมต่อ MyLive")

    # ------------------------------------------------------------------ #
    # Target parsing
    # ------------------------------------------------------------------ #
    @staticmethod
    def _extract_stream_id(text: str) -> Optional[str]:
        """แยกเลข stream จาก URL หรือ input ตรงๆ

        รองรับทุกรูปแบบ:
          - "162006"                                  (เลขห้องล้วน)
          - "https://mylive.in.th/streams/162006"     (URL ตรงๆ)
          - "https://mylive.in.th/Men9CH/streams/162006"  (URL ที่มี user คั่น)
        """
        text = text.strip()
        if not text:
            return None
        # URL รูปแบบ /streams/<id> หรือ /<user>/streams/<id>
        # จับเลขตัวเลขที่อยู่หลัง /streams/ ตัวสุดท้าย
        m = re.search(r"/streams/(\d+)", text)
        if m:
            return m.group(1)
        # เลข stream ล้วน
        if re.fullmatch(r"\d+", text):
            return text
        return None

    # ------------------------------------------------------------------ #
    # Worker loop — เปิด browser + poll DOM จนกว่าจะ disconnect
    # ------------------------------------------------------------------ #
    def _worker_loop(self) -> None:
        """ทำงานใน daemon thread: sync_playwright → goto → wait_for_selector → poll"""
        pw = None
        browser = None
        page = None
        try:
            _ensure_playwright_browser_path(on_status=self.on_status)
            pw = sync_playwright().start()
            # headless Chromium; ปิดฟีเจอร์ที่ไม่จำเป็นเพื่อประหยัดทรัพยากร
            browser = pw.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--mute-audio",
                ],
            )
            page = browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 800},
            )
            url = MYLIVE_STREAM_URL.format(stream_id=self._stream_id)
            # ★ โหลดหน้า 1 ครั้ง แล้วรอ Vue render .m-chat-log (รอนานขึ้น = 45 วิ)
            #    ไม่ retry โหลดใหม่ เพราะ Vue อาจต้องการเวลามากกว่า 15 วิในการ render
            #    โหลดใหม่ทำให้เริ่มนับเวลาใหม่ตั้งแต่ต้น → ใช้เวลารวมนานกว่า + trigger reconnect loop
            chat_ready = False
            try:
                if self._stop_event.is_set():
                    return
                self.on_status("⏳ กำลังโหลดหน้า MyLive...")
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                # ★ รอ Vue render แพนเนลแชท (เพิ่ม timeout เป็น 45 วิ — Vue อาจช้าในบางครั้ง)
                self.on_status("⏳ กำลังรอ MyLive โหลดแชท...")
                page.wait_for_selector(".m-chat-log, .side-chat, .m-ext-chat", timeout=45000)
                chat_ready = True
            except PlaywrightError as exc:
                pass
            # ★ ถ้า user กดหยุดเอง → ออกเงียบๆ (ไม่ส่ง error)
            if self._stop_event.is_set():
                return
            if not chat_ready:
                self.on_error(
                    "ไม่พบกล่องแชท — อาจไม่ใช่ห้อง live, ยังไม่เริ่ม, หรือหน้าโหลดช้า"
                )
                self._signal_disconnected()
                return

            self.on_status(f"✅ เชื่อมต่อ MyLive แล้ว (ห้อง {self._stream_id})")

            # prime: ข้ามข้อความเก่าทั้งหมดที่ค้างอยู่ในหน้า → emit เฉพาะของใหม่หลังกดเชื่อมต่อ
            # ★ Vue อาจโหลด chat history ทีละส่วน (lazy/async) → prime หลายรอบเพื่อจับให้หมด
            #    แต่ละรอบหน่วง 1 วิ ถ้า idx สูงสุดไม่เพิ่มแล้ว = โหลดครบแล้ว
            last_prime_idx = -1
            for _prime_round in range(5):
                if self._stop_event.is_set():
                    break
                try:
                    primed = page.evaluate(_READ_CHAT_JS)
                    if primed:
                        current_max = max(e.get("idx", -1) for e in primed)
                        self._last_seen_idx = current_max
                        # ถ้า idx สูงสุดไม่เพิ่มจากรอบก่อน → Vue โหลดครบแล้ว → หยุด prime
                        if current_max == last_prime_idx:
                            break
                        last_prime_idx = current_max
                except PlaywrightError:
                    pass
                # หน่วง 1 วิก่อน prime รอบถัดไป (ให้ Vue เวลาโหลด history เพิ่ม)
                self._stop_event.wait(1.0)

            # poll จนกว่าจะหยุด
            consecutive_errors = 0
            last_viewer_poll = 0.0
            while not self._stop_event.is_set():
                try:
                    entries = page.evaluate(_READ_CHAT_JS)
                    self._dispatch_new(entries)
                    consecutive_errors = 0
                    # poll viewer count ทุก ~30s (อยู่ใน div.col.m-count)
                    now = time.time()
                    if now - last_viewer_poll >= 30:
                        try:
                            vc_text = page.evaluate(
                                "() => { const el = document.querySelector('div.col.m-count');"
                                " return el ? el.textContent.trim() : ''; }"
                            )
                            if vc_text:
                                import re as _re
                                m = _re.search(r'([\d,]+)', vc_text)
                                if m:
                                    count = int(m.group(1).replace(',', ''))
                                    # ★ หัก 1 ออก เพราะเครื่องเราที่เข้าไปดึงแชทนับเป็นคนดูด้วย
                                    count = max(0, count - 1)
                                    self.on_viewer_count("mylive", count)
                        except Exception:
                            pass
                        last_viewer_poll = now
                except PlaywrightError as exc:
                    consecutive_errors += 1
                    # ★ ถ้า error ติดต่อกันเกิน 5 ครั้ง = browser ตายแน่ → ส่ง on_error เพื่อ trigger reconnect
                    if consecutive_errors >= 5:
                        self.on_error(f"หลุด: {exc}")
                        break
                except Exception as exc:  # noqa: BLE001
                    consecutive_errors += 1
                    if consecutive_errors >= 5:
                        self.on_error(f"หลุด: {exc}")
                        break
                # interruptible sleep
                self._stop_event.wait(self.poll_interval)

        except PlaywrightError as exc:
            # ★ ถ้า user กดหยุดเอง → ไม่ส่ง error (เป็นการ disconnect ปกติ)
            if not self._stop_event.is_set():
                self.on_error(f"เปิดเบราว์เซอร์ไม่ได้: {exc}")
        except Exception as exc:  # noqa: BLE001
            if not self._stop_event.is_set():
                self.on_error(f"ข้อผิดพลาด: {exc}")
        finally:
            # cleanup browser (สำคัญ — กัน leak process)
            for closer in (page, browser):
                if closer is not None:
                    try:
                        closer.close()
                    except Exception:  # noqa: BLE001
                        pass
            if pw is not None:
                try:
                    pw.stop()
                except Exception:  # noqa: BLE001
                    pass
            self._signal_disconnected()

    def _signal_disconnected(self) -> None:
        """บอกว่าหลุดแล้ว (ใช้กับ on_error watcher ใน GUI ที่ดูคำว่า ปิด/หลุด)

        ★ ถ้า user กดหยุดเอง (_stop_event set) → ไม่ส่ง on_error (กัน trigger auto-reconnect)
        """
        if self._is_connected:
            self._is_connected = False
            if not self._stop_event.is_set():
                self.on_error("การเชื่อมต่อ MyLive ปิดลง/หลุด")

    # ------------------------------------------------------------------ #
    # Dispatch — diff ตาม index แล้วแปลงเป็น ChatMessage
    # ------------------------------------------------------------------ #
    def _dispatch_new(self, entries: List[dict]) -> None:
        """emit เฉพาะ entry ที่ idx > _last_seen_idx"""
        if not entries:
            return
        # entries มาเรียงตาม DOM (เก่า→ใหม่) — idx คือลำดับใน DOM ปัจจุบัน
        # DOM สะสม chat log ตลอด → idx มักเพิ่มขึ้นเรื่อยๆ (อาจมี scroll prune ทำให้ลด)
        # กรณี prune: ถ้า idx สูงสุดลดลง → reset ให้เริ่มนับใหม่จาก entry สุดท้าย
        max_idx = max(e.get("idx", -1) for e in entries)
        if max_idx < self._last_seen_idx:
            # DOM ถูก prune แล้ว → ถือว่าทุกอย่างที่เห็นเป็นของใหม่เทียบกับเก่า
            self._last_seen_idx = max_idx - 1

        new_entries = [
            e for e in entries if e.get("idx", -1) > self._last_seen_idx
        ]
        # เรียงตาม idx เผื่อกรณี DOM ส่งกลับไม่เรียง
        new_entries.sort(key=lambda e: e.get("idx", -1))
        if not new_entries:
            return

        for entry in new_entries:
            self._last_seen_idx = max(self._last_seen_idx, entry.get("idx", -1))
            msg = self._entry_to_message(entry)
            if msg is not None:
                self.messages_read += 1
                self.on_message(msg)

    def _entry_to_message(self, entry: dict) -> Optional[ChatMessage]:
        """แปลง entry จาก DOM เป็น ChatMessage (หรือ None ถ้าไม่ควร emit)

        segments → render-ready:
          - sprite emote → เปลี่ยนเป็น {type:'emoji', char:'😀'} (render ผ่านฟอนต์ระบบ)
          - custom emote → คง {type:'emote', url} (GUI โหลดรูป async)
          - text → รวมเป็น raw_text สำหรับ TTS + คง segment สำหรับ render
        """
        kind = entry.get("kind", "normal")
        author = entry.get("name", "") or "ผู้ชม"
        raw_segments = entry.get("segments", []) or []
        sticker_url = entry.get("stickerUrl")

        # แปลง segment ดิบ → render-ready + สะสม raw_text (สำหรับ TTS)
        render_segments: list = []
        text_parts: list = []
        for seg in raw_segments:
            stype = seg.get("type")
            if stype == "text":
                content = seg.get("content", "")
                if content:
                    render_segments.append({"type": "text", "content": content})
                    text_parts.append(content)
            elif stype == "emote":
                subtype = seg.get("subtype")
                if subtype == "sprite":
                    # twemoji → ตัวอักขระ emoji จริง (render ผ่านฟอนต์ระบบ)
                    unicode_hex = seg.get("unicode", "")
                    char = self._unicode_to_emoji(unicode_hex)
                    if char:
                        render_segments.append({"type": "emoji", "char": char})
                elif subtype == "custom":
                    url = seg.get("url")
                    if url:
                        render_segments.append({"type": "emote", "url": url})

        raw_text = " ".join(text_parts).strip()
        # text สำหรับ TTS = เฉพาะข้อความ (emoji/emote ไม่เข้า TTS อยู่แล้ว)
        text_for_tts = raw_text

        extra: dict = {
            "raw_text": raw_text,
            "segments": render_segments,  # สำหรับ GUI render
            "color": "",  # mylive ไม่ได้ฝังสีชื่อแบบ Twitch
        }

        if kind == "normal":
            # ถ้ามีแต่ emote/emoji ไม่มีข้อความเลย → ยัง emit (เพื่อแสดงในแชท) แต่ TTS จะเงียบ
            if not render_segments:
                return None  # ไม่มีอะไรเลย → ข้าม
            return ChatMessage(
                platform="mylive", author=author, text=text_for_tts,
                event="message", extra=extra,
            )

        if kind == "sticker":
            # sticker = รูปอย่างเดียว ไม่มีข้อความ → ข้าม TTS แต่แสดงรูปในแชท
            extra["sticker_url"] = sticker_url
            return ChatMessage(
                platform="mylive", author=author, text="", event="message", extra=extra,
            )

        if kind == "gift":
            return ChatMessage(
                platform="mylive", author=author, text=text_for_tts, event="bits",
                system_text="ส่งของขวัญ", extra=extra,
            )
        if kind == "tip":
            return ChatMessage(
                platform="mylive", author=author, text=text_for_tts, event="bits",
                system_text="บริจาค", extra=extra,
            )
        if kind == "subscribe":
            return ChatMessage(
                platform="mylive", author=author, text=text_for_tts, event="sub",
                system_text="สมัครสมาชิก", extra=extra,
            )

        # poll / system / announce — ข้าม (ไม่ใช่ chat ที่ต้องอ่าน)
        return None

    @staticmethod
    def _unicode_to_emoji(hex_str: str) -> str:
        """แปลง unicode hex codepoint → ตัวอักขระ emoji

        รองรับ codepoint เดี่ยว ('1f600' → 😀) และหลาย codepoint คั่นด้วย '-'
        ('1f468-200d-1f469-200d-1f467' → 👨‍👩‍👧) ตามรูปแบบ twemoji/zwj
        """
        if not hex_str:
            return ""
        parts = [p for p in hex_str.split("-") if p]
        try:
            codes = [int(p, 16) for p in parts]
            return "".join(chr(c) for c in codes)
        except (ValueError, OverflowError):
            return ""


# ---------------------------------------------------------------------- #
# Smoke test
# ---------------------------------------------------------------------- #
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python chat_mylive.py <stream_id_or_url> [seconds]")
        sys.exit(1)

    target = sys.argv[1]
    duration = int(sys.argv[2]) if len(sys.argv) > 2 else 30

    def cb(msg: ChatMessage) -> None:
        prefix = msg.event.upper()
        sysstr = f"  ({msg.system_text})" if msg.system_text else ""
        seg_n = len(msg.extra.get("segments", []))
        sticker = msg.extra.get("sticker_url")
        seg_tag = f" [{seg_n} seg]" if seg_n else ""
        sticker_tag = " [sticker]" if sticker else ""
        print(f"[{prefix}] {msg.author}: {msg.text!r}{sysstr}{seg_tag}{sticker_tag}")
        if msg.extra.get("segments"):
            for s in msg.extra["segments"]:
                if s["type"] == "text":
                    print(f"      text: {s['content']!r}")
                elif s["type"] == "emoji":
                    print(f"      emoji: {s['char']!r}")
                elif s["type"] == "emote":
                    print(f"      emote: {s['url']}")

    def status(msg: str) -> None:
        print(f">> {msg}")

    client = MyLiveChat(on_message=cb, on_status=status, on_error=status)
    if client.connect(target):
        time.sleep(duration)
        client.disconnect()
        print(f">> read {client.messages_read} messages")
