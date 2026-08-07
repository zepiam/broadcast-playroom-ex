"""obs_refresh.py — สั่ง OBS refresh browser source ผ่าน OBS WebSocket v5

แก้ปัญหา: เปิด OBS ก่อน Broadcast Playroom → browser source cache หน้าเก่า → overlay ไม่แสดง
วิธี: เชื่อม OBS WS → หา browser source ที่ URL ชี้ไป overlay ของเรา → cache-bust URL (?v=timestamp)
"""
from __future__ import annotations

import logging
import threading
import time

_log = logging.getLogger(__name__)

# ★ suppress asyncio connection reset warnings (Windows บ่นตอน OBS ปิดก่อน)
import asyncio as _asyncio
_orig_call_connection_lost = _asyncio.proactor_events._ProactorBasePipeTransport._call_connection_lost
def _silent_connection_lost(self, exc):
    try:
        _orig_call_connection_lost(self, exc)
    except (ConnectionResetError, ConnectionAbortedError, OSError):
        pass
_asyncio.proactor_events._ProactorBasePipeTransport._call_connection_lost = _silent_connection_lost


def refresh_obs_sources(
    host: str = "localhost",
    port: int = 4455,
    password: str = "",
    match_urls: tuple = ("localhost:8765", "localhost:8801", "localhost:8808"),
) -> int:
    """เชื่อม OBS WS → refresh browser sources ที่ URL ตรง overlay ของเรา

    Returns: จำนวน source ที่ refresh สำเร็จ (0 = ไม่เจอ / OBS ไม่เปิด / error)
    """
    try:
        import obsws_python as obs

        cl = obs.ReqClient(host=host, port=port, password=password, timeout=5)

        # ดึงรายการ browser sources
        resp = cl.get_input_list()
        input_list = resp.inputs if hasattr(resp, "inputs") else []

        refreshed = 0
        ts = int(time.time())

        for inp in input_list:
            # ★ API v5 ส่งคืน dict ไม่ใช่ object — ใช้ key แบบ dict
            kind = inp.get("inputKind", "") if isinstance(inp, dict) else getattr(inp, "input_kind", "")
            if kind != "browser_source":
                continue
            name = inp.get("inputName", "") if isinstance(inp, dict) else getattr(inp, "input_name", "")
            try:
                settings = cl.get_input_settings(name)
                input_settings = settings.input_settings if hasattr(settings, "input_settings") else {}
                url = input_settings.get("url", "")

                # เช็คว่า URL ตรง overlay ของเราไหม
                if not any(m in url for m in match_urls):
                    continue

                # cache-bust: เพิ่ม/แทน ?v=timestamp
                if "?" in url:
                    new_url = url.split("?")[0] + f"?v={ts}"
                else:
                    new_url = f"{url}?v={ts}"

                # สั่ง SetInputSettings เพื่อเปลี่ยน URL → OBS reload หน้านั้น
                cl.set_input_settings(name, {"url": new_url}, overlay=True)
                refreshed += 1
                _log.info("OBS refresh: %s → %s", name, new_url)

            except Exception as e:
                _log.debug("OBS refresh error for %s: %s", name, e)

        try:
            cl.base_close()
        except Exception:
            pass

        return refreshed

    except ImportError:
        _log.debug("obsws_python not installed — skip OBS refresh")
        return 0
    except Exception as e:
        _log.debug("OBS refresh failed (OBS not running?): %s", e)
        return 0


# ═══════════════════════════════════════════════════════════════
# ★ Persistent watcher — เชื่อม OBS WS ค้างไว้ + auto-retry
# ═══════════════════════════════════════════════════════════════
class OBSWatcher:
    """เชื่อม OBS WebSocket ค้างไว้ → retry จนกว่าจะติด → refresh เมื่อพร้อม

    Callbacks:
      on_connected() — เรียกเมื่อเชื่อมต่อสำเร็จ (ครั้งแรกหรือ reconnect)
      on_refreshed(n) — เรียกเมื่อ refresh browser sources แล้ว
      on_status(msg) — เรียกเมื่อมีสถานะเปลี่ยน (สำหรับ status bar)
    """

    RETRY_INTERVAL = 5.0   # วินาทีระหว่าง retry
    MAX_RETRIES = 60       # สูงสุด 60 ครั้ง (5 นาที)

    def __init__(self, host="localhost", port=4455, password="",
                 match_urls=("localhost:8765", "localhost:8801", "localhost:8808"),
                 on_connected=None, on_refreshed=None, on_status=None):
        self.host = host
        self.port = port
        self.password = password
        self.match_urls = match_urls
        self.on_connected = on_connected
        self.on_refreshed = on_refreshed
        self.on_status = on_status
        self._stop = threading.Event()
        self._thread = None
        self._connected = False

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._watch_loop, name="OBSWatcher", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._connected = False

    @property
    def is_connected(self):
        return self._connected

    def _watch_loop(self):
        """ลู principal: retry เชื่อม OBS จนกว่าจะติด → refresh → จบ"""
        for attempt in range(self.MAX_RETRIES):
            if self._stop.is_set():
                return

            ok, msg = test_connection(self.host, self.port, self.password)
            if ok:
                self._connected = True
                _log.info("OBS WS connected (attempt %d)", attempt + 1)
                if self.on_connected:
                    self.on_connected()
                if self.on_status:
                    self.on_status("🔌 OBS: เชื่อมต่อแล้ว — กำลัง refresh browser sources")
                # refresh ทันที
                n = refresh_obs_sources(self.host, self.port, self.password, self.match_urls)
                if self.on_refreshed:
                    self.on_refreshed(n)
                if self.on_status:
                    if n > 0:
                        self.on_status(f"🔄 OBS: refresh {n} browser source(s) สำเร็จ")
                    else:
                        self.on_status("🔌 OBS: เชื่อมต่อแล้ว (ไม่พบ browser source ของเรา)")
                return  # ทำงานเสร็จ → จบ

            # ยังไม่ติด → รอแล้วลองใหม่
            if attempt == 0:
                _log.info("OBS WS not ready — retrying every %.0fs...", self.RETRY_INTERVAL)
                if self.on_status:
                    self.on_status("🔌 OBS: กำลังรอ OBS เปิด...")
            self._stop.wait(self.RETRY_INTERVAL)

        _log.info("OBS WS gave up after %d attempts", self.MAX_RETRIES)
        if self.on_status:
            self.on_status("⚠️ OBS: ไม่สามารถเชื่อมต่อได้ (รอเกิน 5 นาที)")



def test_connection(
    host: str = "localhost",
    port: int = 4455,
    password: str = "",
) -> tuple[bool, str]:
    """ทดสอบการเชื่อมต่อ OBS WS → คืน (success, message)"""
    try:
        import obsws_python as obs

        cl = obs.ReqClient(host=host, port=port, password=password, timeout=5)
        version = cl.get_version()
        v = version.obs_version if hasattr(version, "obs_version") else "?"
        try:
            cl.base_close()
        except Exception:
            pass
        return (True, f"เชื่อมต่อสำเร็จ — OBS {v}")
    except ImportError:
        return (False, "obsws_python ไม่ได้ติดตั้ง")
    except Exception as e:
        msg = str(e)
        if "Connection" in msg or "refused" in msg or "timeout" in msg:
            return (False, "เชื่อมต่อไม่ได้ — ตรวจสอบว่า OBS เปิดอยู่และเปิด WebSocket Server แล้ว")
        if "auth" in msg.lower() or "password" in msg.lower():
            return (False, "รหัสผ่านผิด")
        return (False, f"เชื่อมต่อล้มเหลว: {msg}")
