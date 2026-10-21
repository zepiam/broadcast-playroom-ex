"""obs_refresh.py — สั่ง OBS refresh browser source ผ่าน OBS WebSocket v5

แก้ปัญหา: เปิด OBS ก่อน Broadcast Playroom → browser source cache หน้าเก่า → overlay ไม่แสดง
วิธี: เชื่อม OBS WS → หา browser source ที่ URL ชี้ไป overlay ของเรา → cache-bust URL (?v=timestamp)
"""
from __future__ import annotations

import logging
import os
import threading
import time
import urllib.parse

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


def get_obs_auto_password() -> str:
    """อ่าน password จาก obs-websocket/config.json อัตโนมัติ (หากผู้ใช้ไม่ได้ตั้งรหัสผ่านเองในโปรแกรม)"""
    try:
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            cfg = os.path.join(appdata, "obs-studio", "plugin_config", "obs-websocket", "config.json")
            if os.path.exists(cfg):
                import json
                with open(cfg, "r", encoding="utf-8") as f:
                    return json.load(f).get("server_password", "") or ""
    except Exception:
        pass
    return ""


def inspect_scene_overlay(cl, scene_name: str = None, match_ports=(8801,)) -> dict:
    """ตรวจสอบ scene ว่ามี browser source ของ Broadcast Playroom หรือไม่
    และเช็คว่าเป็นแบบ Pinned (?p=...) หรือ Dynamic (ไม่มี ?p=)

    คืนค่า:
      {
        "connected": True,
        "scene_name": str,
        "has_overlay": bool,
        "source_name": str,
        "is_pinned": bool,
        "pinned_page": str or None,
        "url": str,
      }
    """
    if not scene_name:
        try:
            cur = cl.get_current_program_scene()
            scene_name = getattr(cur, "current_program_scene_name", getattr(cur, "scene_name", ""))
        except Exception:
            return {
                "connected": True,
                "scene_name": "",
                "has_overlay": False,
                "source_name": "",
                "is_pinned": False,
                "pinned_page": None,
                "url": "",
            }

    try:
        items_resp = cl.get_scene_item_list(scene_name)
        items = getattr(items_resp, "scene_items", []) or []
    except Exception:
        items = []

    overlay_sources = []
    for it in items:
        kind = it.get("inputKind") if isinstance(it, dict) else getattr(it, "input_kind", "")
        if kind != "browser_source":
            continue
        s_name = it.get("sourceName") if isinstance(it, dict) else getattr(it, "source_name", "")
        s_enabled = it.get("sceneItemEnabled") if isinstance(it, dict) else getattr(it, "scene_item_enabled", True)
        try:
            st = cl.get_input_settings(s_name)
            url = (st.input_settings if hasattr(st, "input_settings") else {}).get("url", "")
            if any(f":{p}" in url or f"localhost:{p}" in url or f"127.0.0.1:{p}" in url for p in match_ports):
                overlay_sources.append({"name": s_name, "enabled": bool(s_enabled), "url": url})
        except Exception:
            pass

    # ดึงเฉพาะ source ที่เปิดใช้งาน (enabled=True) ถ้ามี; ถ้าไม่มีตัวเปิดเลย ให้ใช้ทั้งหมดเป็น fallback
    active_sources = [s for s in overlay_sources if s.get("enabled")]
    if not active_sources:
        active_sources = overlay_sources

    if not active_sources:
        return {
            "connected": True,
            "scene_name": scene_name,
            "has_overlay": False,
            "source_name": "",
            "is_pinned": False,
            "pinned_page": None,
            "url": "",
            "multiple_sources": False,
            "sources": [],
        }

    parsed_sources = []
    for s in active_sources:
        u = urllib.parse.urlparse(s["url"])
        qs = urllib.parse.parse_qs(u.query)
        p_val = qs.get("p", [None])[0] or qs.get("page", [None])[0]
        parsed_sources.append({
            "source_name": s["name"],
            "enabled": s.get("enabled", True),
            "is_pinned": bool(p_val),
            "pinned_page": p_val if p_val else None,
            "url": s["url"],
        })

    top = parsed_sources[0]
    return {
        "connected": True,
        "scene_name": scene_name,
        "has_overlay": True,
        "source_name": top["source_name"],
        "is_pinned": top["is_pinned"],
        "pinned_page": top["pinned_page"],
        "url": top["url"],
        "multiple_sources": len(parsed_sources) > 1,
        "sources": parsed_sources,
    }


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

        effective_pw = password or get_obs_auto_password()
        cl = obs.ReqClient(host=host, port=port, password=effective_pw, timeout=5)

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

                # cache-bust: เพิ่ม/แทน ?v=timestamp (ระวังอย่าให้ทับพารามิเตอร์ ?p=)
                u = urllib.parse.urlparse(url)
                qs = urllib.parse.parse_qs(u.query)
                qs["v"] = [str(ts)]
                # rebuild query string
                new_query = urllib.parse.urlencode(qs, doseq=True)
                new_url = urllib.parse.urlunparse((u.scheme, u.netloc, u.path, u.params, new_query, u.fragment))

                # สั่ง SetInputSettings เพื่อเปลี่ยน URL → OBS reload หน้านั้น
                cl.set_input_settings(name, {"url": new_url}, overlay=True)
                refreshed += 1
                _log.info("OBS refresh: %s → %s", name, new_url)

            except Exception as e:
                _log.debug("OBS refresh error for %s: %s", name, e)

        try:
            cl.base_client.ws.close()
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
# ★ Persistent watcher — เชื่อม OBS WS ค้างไว้ + auto-retry + live stream monitor + scene watcher
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
    """ดึงสถานะสตรีม/บันทึกจาก OBS WebSocket"""
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
        effective_pw = password or get_obs_auto_password()
        cl = obs.ReqClient(host=host, port=port, password=effective_pw, timeout=1.5)
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
            cl.base_client.ws.close()
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
    """เชื่อม OBS WebSocket ค้างไว้ → auto-retry + refresh เมื่อพร้อม + monitor stream live status + scene awareness

    Callbacks:
      on_connected() — เรียกเมื่อเชื่อมต่อสำเร็จ
      on_refreshed(n) — เรียกเมื่อ refresh browser sources แล้ว
      on_status(msg) — เรียกเมื่อมีสถานะเปลี่ยน
      on_stream_started(timecode, duration_sec) — เรียกเมื่อเริ่ม Live / Record
      on_stream_stopped() — เรียกเมื่อจบ Live / Record
      on_stream_tick(status_dict) — เรียกทุกรอบที่กำลัง Live อยู่ (บอกเวลาปัจจุบัน)
      on_scene_changed(info_dict) — เรียกเมื่อ OBS เปลี่ยน scene หรือข้อมูล overlay ใน scene เปลี่ยน
    """

    RETRY_INTERVAL = 5.0

    def __init__(self, host="localhost", port=4455, password="",
                 match_urls=("localhost:8765", "localhost:8801", "localhost:8808"),
                 match_ports=(8801,),
                 on_connected=None, on_refreshed=None, on_status=None,
                 on_stream_started=None, on_stream_stopped=None, on_stream_tick=None,
                 on_scene_changed=None):
        self.host = host
        self.port = port
        self.password = password
        self.match_urls = match_urls
        self.match_ports = tuple(match_ports or (8801,))
        self.on_connected = on_connected
        self.on_refreshed = on_refreshed
        self.on_status = on_status
        self.on_stream_started = on_stream_started
        self.on_stream_stopped = on_stream_stopped
        self.on_stream_tick = on_stream_tick
        self.on_scene_changed = on_scene_changed
        self._stop = threading.Event()
        self._thread = None
        self._connected = False
        self._was_streaming = False
        self._event_client = None
        self._last_scene_overlay = None
        self._current_scene_name = ""

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
        self._last_scene_overlay = None
        self._current_scene_name = ""
        self._stop_event_client()

    @property
    def is_connected(self):
        return self._connected

    def _stop_event_client(self):
        if self._event_client:
            try:
                self._event_client.unsubscribe()
            except Exception:
                pass
            self._event_client = None

    def _start_event_client(self, effective_pw: str):
        self._stop_event_client()
        try:
            import obsws_python as obs
            self._event_client = obs.EventClient(host=self.host, port=self.port, password=effective_pw)

            def on_current_program_scene_changed(data):
                sc_name = getattr(data, "scene_name", "") or getattr(data, "current_program_scene_name", "")
                self._inspect_and_notify_scene(sc_name)

            def on_scene_item_enable_state_changed(data):
                self._inspect_and_notify_scene()

            def on_scene_item_created(data):
                self._inspect_and_notify_scene()

            def on_scene_item_removed(data):
                self._inspect_and_notify_scene()

            def on_scene_item_list_reindexed(data):
                self._inspect_and_notify_scene()

            def on_input_settings_changed(data):
                self._inspect_and_notify_scene()

            def on_input_created(data):
                self._inspect_and_notify_scene()

            def on_input_name_changed(data):
                self._inspect_and_notify_scene()

            self._event_client.callback.register((
                on_current_program_scene_changed,
                on_scene_item_enable_state_changed,
                on_scene_item_created,
                on_scene_item_removed,
                on_scene_item_list_reindexed,
                on_input_settings_changed,
                on_input_created,
                on_input_name_changed,
            ))
            _log.info("OBS EventClient subscribed for real-time scene events & item changes")
        except Exception as e:
            _log.debug(f"EventClient start failed (will use polling): {e}")
            self._event_client = None

    def _inspect_and_notify_scene(self, scene_name: str = None):
        """ตรวจสอบ scene และแจ้ง on_scene_changed callback"""
        try:
            import obsws_python as obs
            effective_pw = self.password or get_obs_auto_password()
            cl = obs.ReqClient(host=self.host, port=self.port, password=effective_pw, timeout=2)
            info = inspect_scene_overlay(cl, scene_name, match_ports=self.match_ports)
            try:
                cl.base_client.ws.close()
            except Exception:
                pass

            if info != self._last_scene_overlay:
                self._last_scene_overlay = info
                self._current_scene_name = info.get("scene_name", "")
                if self.on_scene_changed:
                    self.on_scene_changed(info)
        except Exception as e:
            _log.debug(f"_inspect_and_notify_scene error: {e}")

    def _watch_loop(self):
        """ลูปหลัก: เชื่อมต่อ OBS WS → refresh browser sources → monitor stream status + scenes อย่างต่อเนื่อง"""
        attempt = 0
        while not self._stop.is_set():
            effective_pw = self.password or get_obs_auto_password()
            if not self._connected:
                if not is_port_open(self.host, self.port, timeout=0.3):
                    if attempt == 0 and self.on_status:
                        self.on_status("🔌 OBS: กำลังรอ OBS เปิด...")
                    attempt += 1
                    self._stop.wait(self.RETRY_INTERVAL)
                    continue

                ok, msg = test_connection(self.host, self.port, effective_pw)
                if ok:
                    self._connected = True
                    attempt = 0
                    _log.info("OBS WS connected")
                    if self.on_connected:
                        self.on_connected()

                    # เริ่ม EventClient สำหรับ real-time scene change
                    self._start_event_client(effective_pw)

                    # ตรวจสอบ scene ปัจจุบันทันที
                    self._inspect_and_notify_scene()

                    # refresh ทันที
                    n = refresh_obs_sources(self.host, self.port, effective_pw, self.match_urls)
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

            # เมื่อเชื่อมต่อแล้ว → ตรวจสอบสถานะการ Live + Scene ต่อเนื่องทุกๆ 1.5 วินาที
            self._stop.wait(1.5)
            if self._stop.is_set():
                break

            status = get_obs_stream_status(self.host, self.port, effective_pw)
            if not status["connected"]:
                _log.info("OBS WS disconnected")
                self._connected = False
                self._stop_event_client()
                if self._was_streaming:
                    self._was_streaming = False
                    if self.on_stream_stopped:
                        self.on_stream_stopped()
                if self._last_scene_overlay is not None:
                    self._last_scene_overlay = None
                    self._current_scene_name = ""
                    if self.on_scene_changed:
                        self.on_scene_changed({
                            "connected": False,
                            "scene_name": "",
                            "has_overlay": False,
                            "source_name": "",
                            "is_pinned": False,
                            "pinned_page": None,
                            "url": "",
                        })
                continue

            # ตรวจสอบ scene ปัจจุบัน (polling check เป็นตัวสำรองของ EventClient)
            try:
                import obsws_python as obs
                cl = obs.ReqClient(host=self.host, port=self.port, password=effective_pw, timeout=1.5)
                cur_sc = cl.get_current_program_scene()
                cur_name = getattr(cur_sc, "current_program_scene_name", getattr(cur_sc, "scene_name", ""))
                try:
                    cl.base_client.ws.close()
                except Exception:
                    pass
                self._inspect_and_notify_scene(cur_name)
            except Exception:
                pass

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

        effective_pw = password or get_obs_auto_password()
        cl = obs.ReqClient(host=host, port=port, password=effective_pw, timeout=3)
        version = cl.get_version()
        ver_str = getattr(version, 'obs_version', getattr(version, 'obsVersion', ''))
        try:
            cl.base_client.ws.close()
        except Exception:
            pass
        return (True, f"เชื่อมต่อสำเร็จ (OBS v{ver_str})")
    except ImportError:
        return (False, "ไม่ได้ติดตั้ง obsws_python (pip install obsws-python)")
    except Exception as e:
        err = str(e)
        if "Authentication failed" in err or "authentication enabled but no password" in err:
            return (False, "รหัสผ่าน OBS WebSocket ไม่ถูกต้อง — ตรวจสอบรหัสผ่านใน OBS (Tools > WebSocket Server Settings)")
        return (False, f"เชื่อมต่อไม่สำเร็จ: {err}")
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
