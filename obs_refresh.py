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
# ★ Persistent watcher — เชื่อม OBS WS ค้างไว้ + auto-retry + live stream monitor
# ═══════════════════════════════════════════════════════════════
import socket

def is_port_open(host: str, port: int, timeout: float = 0.2) -> bool:
    """ตรวจสอบ socket port แบบเร็ว (ไม่ค้าง ไม่โยน traceback)"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def get_obs_stream_status(host: str = "localhost", port: int = 4455, password: str = "") -> dict:
    """ดึงสถานะสตรีม/บันทึกจาก OBS WebSocket
    Returns:
      {
        "connected": bool,
        "is_streaming": bool,
        "is_recording": bool,
        "output_active": bool,
        "timecode": str,      # เช่น "00:15:32"
        "duration_sec": int,  # วินาที
      }
    """
    if not is_port_open(host, port, timeout=0.2):
        return {
            "connected": False,
            "is_streaming": False,
            "is_recording": False,
            "output_active": False,
            "timecode": "",
            "duration_sec": 0,
        }
    try:
        import obsws_python as obs
        cl = obs.ReqClient(host=host, port=port, password=password, timeout=1.5)
        is_streaming = False
        is_recording = False
        timecode = ""
        duration_sec = 0
        try:
            st = cl.get_stream_status()
            if getattr(st, 'output_active', False):
                is_streaming = True
                tc = getattr(st, 'output_timecode', '') or ''
                timecode = tc.split('.')[0] if '.' in tc else tc
                duration_sec = int(getattr(st, 'output_duration', 0) / 1000)
        except Exception:
            pass
        if not is_streaming:
            try:
                rec = cl.get_record_status()
                if getattr(rec, 'output_active', False):
                    is_recording = True
                    tc = getattr(rec, 'output_timecode', '') or ''
                    timecode = tc.split('.')[0] if '.' in tc else tc
                    duration_sec = int(getattr(rec, 'output_duration', 0) / 1000)
            except Exception:
                pass
        try:
            cl.base_close()
        except Exception:
            pass
        return {
            "connected": True,
            "is_streaming": is_streaming,
            "is_recording": is_recording,
            "output_active": is_streaming or is_recording,
            "timecode": timecode,
            "duration_sec": duration_sec,
        }
    except Exception:
        return {
            "connected": False,
            "is_streaming": False,
            "is_recording": False,
            "output_active": False,
            "timecode": "",
            "duration_sec": 0,
        }


class OBSWatcher:
    """เชื่อม OBS WebSocket ค้างไว้ → auto-retry + refresh เมื่อพร้อม + monitor stream live status

    Callbacks:
      on_connected() — เรียกเมื่อเชื่อมต่อสำเร็จ
      on_refreshed(n) — เรียกเมื่อ refresh browser sources แล้ว
      on_status(msg) — เรียกเมื่อมีสถานะเปลี่ยน
      on_stream_started(timecode, duration_sec) — เรียกเมื่อเริ่ม Live / Record
      on_stream_stopped() — เรียกเมื่อจบ Live / Record
      on_stream_tick(status_dict) — เรียกทุกรอบที่กำลัง Live อยู่ (บอกเวลาปัจจุบัน)
    """

    RETRY_INTERVAL = 5.0

    def __init__(self, host="localhost", port=4455, password="",
                 match_urls=("localhost:8765", "localhost:8801", "localhost:8808"),
                 on_connected=None, on_refreshed=None, on_status=None,
                 on_stream_started=None, on_stream_stopped=None, on_stream_tick=None):
        self.host = host
        self.port = port
        self.password = password
        self.match_urls = match_urls
        self.on_connected = on_connected
        self.on_refreshed = on_refreshed
        self.on_status = on_status
        self.on_stream_started = on_stream_started
        self.on_stream_stopped = on_stream_stopped
        self.on_stream_tick = on_stream_tick
        self._stop = threading.Event()
        self._thread = None
        self._connected = False
        self._was_streaming = False

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._watch_loop, name="OBSWatcher", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._connected = False
        self._was_streaming = False

    @property
    def is_connected(self):
        return self._connected

    def _watch_loop(self):
        """ลูปหลัก: เชื่อมต่อ OBS WS → refresh browser sources → monitor stream status อย่างต่อเนื่อง"""
        attempt = 0
        while not self._stop.is_set():
            if not self._connected:
                if not is_port_open(self.host, self.port, timeout=0.3):
                    if attempt == 0 and self.on_status:
                        self.on_status("🔌 OBS: กำลังรอ OBS เปิด...")
                    attempt += 1
                    self._stop.wait(self.RETRY_INTERVAL)
                    continue

                ok, msg = test_connection(self.host, self.port, self.password)
                if ok:
                    self._connected = True
                    attempt = 0
                    _log.info("OBS WS connected")
                    if self.on_connected:
                        self.on_connected()
                    # refresh ทันที
                    n = refresh_obs_sources(self.host, self.port, self.password, self.match_urls)
                    if self.on_refreshed:
                        self.on_refreshed(n)
                    if self.on_status:
                        if n > 0:
                            self.on_status(f"🔄 OBS: refresh {n} browser source(s) สำเร็จ")
                        else:
                            self.on_status("🔌 OBS: เชื่อมต่อแล้ว")
                else:
                    attempt += 1
                    self._stop.wait(self.RETRY_INTERVAL)
                    continue

            # เมื่อเชื่อมต่อแล้ว → ตรวจสอบสถานะการ Live ต่อเนื่องทุกๆ 2 วินาที
            self._stop.wait(2.0)
            if self._stop.is_set():
                break

            status = get_obs_stream_status(self.host, self.port, self.password)
            if not status["connected"]:
                _log.info("OBS WS disconnected")
                self._connected = False
                if self._was_streaming:
                    self._was_streaming = False
                    if self.on_stream_stopped:
                        self.on_stream_stopped()
                continue

            is_active = status["output_active"]
            if is_active and not self._was_streaming:
                self._was_streaming = True
                _log.info(f"OBS stream started: {status['timecode']}")
                if self.on_stream_started:
                    self.on_stream_started(status['timecode'], status['duration_sec'])
            elif not is_active and self._was_streaming:
                self._was_streaming = False
                _log.info("OBS stream stopped")
                if self.on_stream_stopped:
                    self.on_stream_stopped()

            if is_active and self.on_stream_tick:
                self.on_stream_tick(status)


def test_connection(
    host: str = "localhost",
    port: int = 4455,
    password: str = "",
) -> tuple[bool, str]:
    """ทดสอบการเชื่อมต่อ OBS WS → คืน (success, message)"""
    if not is_port_open(host, port, timeout=0.3):
        return (False, "เชื่อมต่อไม่ได้ — ตรวจสอบว่า OBS เปิดอยู่และเปิด WebSocket Server แล้ว")
    try:
        import obsws_python as obs

        cl = obs.ReqClient(host=host, port=port, password=password, timeout=3)
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
