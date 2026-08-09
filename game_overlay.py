"""game_overlay.py — Game Overlay manager (spawn Qt subprocess)

Architecture (แก้ปัญหา Tk+Qt conflict):
  Tk main process (this) ─── subprocess ───► game_overlay_qt.py (Qt-only)
                                                  ↓ HTTP/WS
                                            game_overlay_server.py (port 8767)
                                                  ↓
                                            game_overlay.html

คุยกับ subprocess ผ่าน stdin/stdout (JSON lines):
  → parent → child:  {"cmd": "edit_on"} / "edit_off" / "quit" / "reload"
  ← child → parent:  {"cmd": "ready", "hwnd": ...} / {"cmd": "position", ...} /
                     {"cmd": "open_settings"} / {"cmd": "exit_edit"}
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from typing import Optional

from settings import get_base_dir


# ── Windows Job Object — kill child processes อัตโนมัติเมื่อ parent ตาย ──
# แก้ปัญหา: Qt subprocess ค้างเมื่อ parent force-close (kill / crash / Alt+F4)
# Job Object ผูก child เข้ากับ parent → parent ตาย → Windows ฆ่า child ทันที
_job_handle = None

def _ensure_job_object():
    """สร้าง Job Object (ครั้งเดียว) ที่ฆ่า child ทุกตัวเมื่อ parent ตาย"""
    global _job_handle
    if _job_handle is not None:
        return _job_handle
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.windll.kernel32

        # CreateJobObjectW(lpJobAttributes=NULL, lpName=NULL)
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        h = kernel32.CreateJobObjectW(None, None)
        if not h:
            return None

        # JOBOBJECT_EXTENDED_LIMIT_INFORMATION
        # JOBOBJECT_LIMIT_KILL_ON_JOB = 0x2000
        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [("ReadOperationCount", ctypes.c_ulonglong),
                        ("WriteOperationCount", ctypes.c_ulonglong),
                        ("OtherOperationCount", ctypes.c_ulonglong),
                        ("ReadTransferCount", ctypes.c_ulonglong),
                        ("WriteTransferCount", ctypes.c_ulonglong),
                        ("OtherTransferCount", ctypes.c_ulonglong)]
        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                        ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD),
                        ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t),
                        ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t),
                        ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]
        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                        ("IoInfo", IO_COUNTERS),
                        ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]

        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB

        # SetInformationJobObject(hJob, JobObjectExtendedLimitInformation=9, &info, sizeof)
        kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        ok = kernel32.SetInformationJobObject(h, 9, ctypes.byref(info), ctypes.sizeof(info))
        if not ok:
            kernel32.CloseHandle(h)
            return None

        # AssignProcess: ใส่ parent process เองเข้า Job Object ด้วย
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel32.AssignProcessToJobObject(h, kernel32.GetCurrentProcess())
        _job_handle = h
        return h
    except Exception:
        return None


def _assign_to_job(proc):
    """ผูก subprocess เข้า Job Object (ถ้ามี) — กันค้างเมื่อ parent ตาย"""
    if sys.platform != "win32":
        return
    try:
        h = _ensure_job_object()
        if h is None or proc is None or proc.pid is None:
            return
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.windll.kernel32
        # เปิด handle ของ child process (PROCESS_ALL_ACCESS = 0x1F0FFF, PROCESS_SET_QUOTA = 0x0100)
        PROCESS_SET_QUOTA = 0x0100
        PROCESS_TERMINATE = 0x0001
        inherit = False
        child_h = kernel32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, inherit, proc.pid)
        if child_h:
            kernel32.AssignProcessToJobObject(h, child_h)
            kernel32.CloseHandle(child_h)
    except Exception:
        pass


def _is_frozen() -> bool:
    """ตรวจว่ารันใน PyInstaller exe หรือไม่"""
    return getattr(sys, "frozen", False)


def _python_exe() -> str:
    """หา python executable — รองรับทั้ง dev mode และ PyInstaller exe"""
    return sys.executable


def _overlay_script_path() -> str:
    """หา game_overlay_qt.py"""
    # dev mode: อยู่ใน base_dir
    path = os.path.join(get_base_dir(), "game_overlay_qt.py")
    if os.path.exists(path):
        return path
    # PyInstaller bundle: อยู่ใน _MEIPASS
    if hasattr(sys, "_MEIPASS"):
        path2 = os.path.join(sys._MEIPASS, "game_overlay_qt.py")
        if os.path.exists(path2):
            return path2
    return path


class GameOverlay:
    """Game Overlay manager — spawn Qt subprocess + push messages via server"""

    def __init__(self, parent_app) -> None:
        self.parent_app = parent_app
        self.settings = parent_app.settings
        self._server = None
        self._proc: Optional[subprocess.Popen] = None
        self._hwnd: Optional[int] = None
        self._edit_mode = False
        self._demo_running_state = False  # track demo loop state
        self._reader_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    @property
    def is_running(self) -> bool:
        if self._proc is None:
            return False
        return self._proc.poll() is None

    def _find_free_port(self, start: int = 8767, end: int = 8780) -> Optional[int]:
        """หา port ว่างในช่วง start-end — คืน None ถ้าไม่มี"""
        import socket
        for port in range(start, end + 1):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.bind(("127.0.0.1", port))
                    return port
            except OSError:
                continue
        return None

    def _resolve_port(self) -> Optional[int]:
        """หา port ตาม settings:
        - game_overlay_port = 0 → auto (หาอัตโนมัติ 8767-8780)
        - game_overlay_port > 0 → ใช้ port ที่กำหนด (เช็คว่าว่างไหมก่อน)
        """
        import socket
        configured = getattr(self.settings, "game_overlay_port", 0)
        if configured > 0:
            # ผู้ใช้กำหนดเอง → เช็คว่าว่างไหม
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.bind(("127.0.0.1", configured))
                    return configured
            except OSError:
                # ไม่ว่าง → ลองหาอัตโนมัติแทน
                self.parent_app._safe_status(f"⚠️ Port {configured} ไม่ว่าง — หาอัตโนมัติแทน")
                return self._find_free_port()
        else:
            # auto
            return self._find_free_port()

    def start(self) -> bool:
        """start server + spawn Qt subprocess"""
        # 1) start aiohttp server
        from game_overlay_server import GameOverlayServer
        # 1) start aiohttp server — หา port (auto หรือจาก settings)
        port = self._resolve_port()
        if port is None:
            self.parent_app._safe_status("❌ Game Overlay: ไม่พบ port ว่าง (8767-8780)")
            return False
        try:
            self._server = GameOverlayServer(self.settings, port=port)
            if not self._server.start():
                self.parent_app._safe_status(
                    f"❌ Game Overlay server: {self._server._start_error}"
                )
                return False
        except Exception as exc:
            self.parent_app._safe_status(f"❌ Game Overlay server error: {exc}")
            return False

        # 2) spawn Qt subprocess
        s = self.settings
        args = [
            _python_exe(),
        ]
        # ใน exe mode → ส่ง --game-overlay-qt flag (ไม่ใช่ .py file)
        # ใน dev mode → ส่ง game_overlay_qt.py path ตรง ๆ
        if _is_frozen():
            args.append("--game-overlay-qt")
        else:
            args.append(_overlay_script_path())
        args += [
            "--port", str(port),
            "--x", str(s.game_overlay_x),
            "--y", str(s.game_overlay_y),
            "--w", str(s.game_overlay_width),
            "--h", str(s.game_overlay_height),
            "--alpha", str(s.game_overlay_alpha),
        ]

        # เปิด log file เก็บ subprocess output (สำหรับ debug)
        log_path = os.path.join(get_base_dir(), "game_overlay.log")
        try:
            self._log_file = open(log_path, "w", encoding="utf-8", buffering=1)
        except Exception:
            self._log_file = None

        try:
            # ใช้ DETACHED_PROCESS (หรือ 0) — ไม่เปิด console ดำใหม่
            # subprocess จะรันเป็น window app ปกติ (Qt window เท่านั้นที่โผล่)
            creationflags = 0
            if hasattr(subprocess, "DETACHED_PROCESS"):
                # DETACHED_PROCESS = ไม่มี console เลย (แต่ยังเป็น child process ของ parent)
                # หมายเหตุ: ต้องไม่ใช้ DETACHED_PROCESS เพราะจะทำให้ stdin/stdout pipe ติด →
                # ใช้ 0 (default) + ไม่ตั้ง CREATE_NO_WINDOW กันไม่ให้ window หาย
                pass
            self._proc = subprocess.Popen(
                args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=get_base_dir(),
                encoding="utf-8",
            )
            # ★ ผูก subprocess เข้า Job Object — กันค้างเมื่อ parent ตาย/crash
            _assign_to_job(self._proc)
        except Exception as exc:
            self.parent_app._safe_status(f"❌ Game Overlay spawn: {exc}")
            self._server.stop()
            self._server = None
            return False

        # 3) start reader thread (อ่าน stdout จาก subprocess)
        self._stop_event.clear()
        self._reader_thread = threading.Thread(
            target=self._reader_loop, name="GameOverlayReader", daemon=True,
        )
        self._reader_thread.start()

        # รอ subprocess ส่ง "ready" (max 5s)
        import time as _time
        for _ in range(50):
            if self._hwnd is not None or not self.is_running:
                break
            _time.sleep(0.1)

        if self.is_running:
            self.parent_app._safe_status(f"✅ Game Overlay เปิดแล้ว (port {port})")
            return True
        else:
            self.parent_app._safe_status("❌ Game Overlay: subprocess ปิดตัวเอง")
            return False

    def stop(self) -> None:
        """stop subprocess + server"""
        self._stop_event.set()
        # ส่ง quit ไป subprocess
        self._send_cmd("quit")
        # รอ subprocess ปิด (max 3s)
        if self._proc is not None:
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None
        # stop server
        if self._server is not None:
            try:
                self._server.stop()
            except Exception:
                pass
            self._server = None
        # wait reader
        if self._reader_thread is not None and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=2)
        self._reader_thread = None
        # close log file
        if self._log_file is not None:
            try:
                self._log_file.close()
            except Exception:
                pass
            self._log_file = None
        self._hwnd = None
        self._edit_mode = False

    def add_row(self, msg) -> None:
        """push message ผ่าน server WebSocket"""
        if self._server is not None:
            try:
                self._server.push_message(msg)
            except Exception:
                pass

    def clear_rows(self) -> None:
        """clear overlay messages"""
        if self._server is not None:
            try:
                import asyncio
                if self._server._loop and self._server._started:
                    asyncio.run_coroutine_threadsafe(
                        self._server._broadcast({
                            "type": "eval_js",
                            "js": "document.getElementById('chat').innerHTML='';",
                        }),
                        self._server._loop,
                    )
            except Exception:
                pass

    def toggle_edit_mode(self) -> None:
        """toggle Setup ↔ Overlay mode — ส่ง edit_toggle ให้ Qt toggle เอง (กัน state mismatch)"""
        if not self.is_running:
            return
        self._send_cmd("edit_toggle")

    def update_settings(self) -> None:
        """re-apply settings หลังเปลี่ยน — push config (รวม theme_css) ผ่าน server"""
        if not self.is_running:
            return
        self.settings = self.parent_app.settings
        if self._server is not None:
            # config รวม theme_css + custom_css แล้ว → push ครั้งเดียวพอ
            self._server.update_config(self.settings)
        # DEBUG

    def start_demo(self, interval_sec: float) -> None:
        """เริ่ม demo loop (ส่งข้อความตัวอย่างเรื่อย ๆ)"""
        if self._server is not None:
            self._server.start_demo_loop(interval_sec)

    def stop_demo(self) -> None:
        """หยุด demo loop (ไม่ล้างข้อความ — กัน deadlock กับ asyncio task)"""
        if self._server is not None:
            try:
                self._server.stop_demo_loop()
            except Exception:
                pass

    def _sync_demo_state_to_dialog(self, running: bool) -> None:
        """sync สถานะ demo loop กลับไป Game Overlay Settings dialog (ถ้าเปิดอยู่)

        PySide6: dialog ใช้ _refresh_demo_btn_state() ของตัวเอง → no-op here
        (kept for compatibility — game_overlay.py ถูกเรียกจาก toggle_demo)
        """
        try:
            # ★ PySide6 dialog มี _refresh_demo_btn_state → เรียกผ่าน QTimer
            dlg = getattr(self.parent_app, "_go_settings_dlg", None)
            if dlg is not None:
                # อัปเดต state tracking
                dlg._demo_running = running
                # ใช้ QTimer.singleShot เพื่อเรียก refresh ใน main thread
                try:
                    from PySide6.QtCore import QTimer
                    QTimer.singleShot(0, dlg._refresh_demo_btn_state)
                except Exception:
                    pass
        except Exception:
            pass

    def _send_demo_state_to_subprocess(self, running: bool) -> None:
        """ส่ง demo state ไป subprocess เพื่ออัปเดตข้อความปุ่มใน Edit Mode"""
        # DEBUG
        try:
            with open("game_overlay_debug.log", "a", encoding="utf-8") as f:
                from datetime import datetime
                f.write(f"[{datetime.now().strftime('%H:%M:%S')}] _send_demo_state: running={running} proc={self._proc is not None}\n")
        except Exception:
            pass
        self._send_cmd_json({"cmd": "demo_state", "running": running})

    def _send_cmd_json(self, msg: dict) -> None:
        """ส่ง command ไป subprocess ผ่าน file-based queue (atomic write กัน race)"""
        import tempfile
        queue_file = os.path.join(tempfile.gettempdir(), "game_overlay_cmd_queue.json")
        debug_path = os.path.join(get_base_dir(), "go_parent_debug.log")
        try:
            # ★ read existing — tolerant ต่อ empty/corrupt file (race กับ Qt poller)
            existing = []
            if os.path.exists(queue_file):
                try:
                    with open(queue_file, "r", encoding="utf-8") as f:
                        content = f.read().strip()
                    if content:
                        existing = json.loads(content)
                        if not isinstance(existing, list):
                            existing = []
                except (json.JSONDecodeError, ValueError):
                    # corrupt file → เริ่มใหม่
                    existing = []
            existing.append(msg)
            # ★ atomic write: เขียน temp แล้ว rename กัน partial read
            tmp_fd, tmp_path = tempfile.mkstemp(
                dir=tempfile.gettempdir(), suffix=".json", prefix="go_cmd_",
            )
            try:
                with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                    json.dump(existing, f)
                # os.replace = atomic on Windows (Python 3.3+)
                os.replace(tmp_path, queue_file)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
                raise
            with open(debug_path, "a", encoding="utf-8") as f:
                f.write(f"_send_cmd_json OK: {msg.get('cmd')} → queue={len(existing)}\n")
        except Exception as exc:
            try:
                with open(debug_path, "a", encoding="utf-8") as f:
                    f.write(f"_send_cmd_json ERROR: {exc}\n")
            except Exception:
                pass

    @property
    def demo_running(self) -> bool:
        """สถานะ demo loop (track เอง — เชื่อถือได้กว่า server._demo_running)"""
        return getattr(self, "_demo_running_state", False)

    def toggle_demo(self) -> None:
        """toggle demo loop — toggle state เอง + sync ทั้ง 2 ที่ (Setting + Edit Mode)

        ไม่ใช้ background thread (เพราะ sync ต้องการ main thread)
        start_demo/stop_demo ใช้ asyncio อยู่แล้ว → ไม่ block
        """
        # toggle state เอง (อย่าพึ่ง demo_running เพราะ race condition)
        was_running = self._demo_running_state
        if was_running:
            self.stop_demo()
            self._demo_running_state = False
        else:
            interval = float(getattr(self.settings, "game_overlay_demo_interval", 5.0))
            self.start_demo(interval)
            self._demo_running_state = True
        running = self._demo_running_state
        # sync กลับ Setting dialog (เรียกตรง ๆ ใน main thread)
        try:
            self._sync_demo_state_to_dialog(running)
        except Exception:
            pass
        # sync กลับ Edit Mode (subprocess)
        self._send_demo_state_to_subprocess(running)

    # ------------------------------------------------------------------ #
    # Subprocess communication
    # ------------------------------------------------------------------ #
    def _send_cmd(self, cmd: str) -> None:
        """ส่ง command ไป subprocess"""
        try:
            debug_path = os.path.join(get_base_dir(), "go_parent_debug.log")
            with open(debug_path, "a", encoding="utf-8") as f:
                f.write(f"_send_cmd: {cmd}\n")
        except Exception:
            pass
        self._send_cmd_json({"cmd": cmd})

    def _reader_loop(self) -> None:
        """อ่าน response จาก subprocess ผ่าน file-based queue (ทำงานได้ใน exe)

        ตรวจ process exit ด้วย — ถ้า subprocess ปิด (เช่น Alt+F4) → sync button state
        """
        import tempfile, time as _time
        response_file = os.path.join(tempfile.gettempdir(), "game_overlay_response_queue.json")
        exit_handled = False
        while not self._stop_event.is_set():
            try:
                # ตรวจ process exit (เช่น Alt+F4 ปิดหน้าต่าง Qt)
                if not exit_handled and self._proc is not None and self._proc.poll() is not None:
                    # subprocess ปิดแล้ว → sync state
                    exit_handled = True
                    self._hwnd = None
                    try:
                        self.settings.game_overlay_enabled = False
                        from settings import save_settings
                        save_settings(self.settings)
                        # sync button (ใน UI thread)
                        self.parent_app.after(0, self.parent_app._update_game_overlay_btn)
                        self.parent_app._safe_status("⛔ Game Overlay ปิดแล้ว")
                    except Exception:
                        pass
                if os.path.exists(response_file):
                    with open(response_file, "r", encoding="utf-8") as f:
                        responses = json.load(f)
                    if responses:
                        with open(response_file, "w", encoding="utf-8") as f:
                            json.dump([], f)
                    for msg in responses:
                        self._handle_response(msg)
            except Exception:
                pass
            _time.sleep(0.2)

    def _handle_response(self, msg: dict) -> None:
        """จัดการ response จาก subprocess"""
        cmd = msg.get("cmd")
        if not cmd:
            return
        # เขียน log
        if self._log_file is not None:
            try:
                self._log_file.write(json.dumps(msg) + "\n")
            except Exception:
                pass
        if cmd == "ready":
            self._hwnd = msg.get("hwnd")
        elif cmd == "position":
            # บันทึกตำแหน่งที่ผู้ใช้ลาก
            try:
                s = self.settings
                s.game_overlay_x = int(msg.get("x", -1))
                s.game_overlay_y = int(msg.get("y", -1))
                s.game_overlay_width = int(msg.get("w", 360))
                s.game_overlay_height = int(msg.get("h", 500))
                from settings import save_settings
                save_settings(s)
            except Exception:
                pass
        elif cmd == "open_settings":
            try:
                self.parent_app._game_overlay_cmd_sig.emit("open_settings")
            except Exception:
                pass
        elif cmd == "exit_edit":
            self._edit_mode = False
            self._send_cmd("edit_off")
            try:
                self.parent_app._game_overlay_cmd_sig.emit("exit_edit")
            except Exception:
                pass
        elif cmd == "toggle_demo":
            try:
                self.parent_app._game_overlay_cmd_sig.emit("toggle_demo")
            except Exception:
                pass
        elif cmd == "stop_demo":
            try:
                self.parent_app.after(0, self.toggle_demo)
            except Exception:
                pass
        elif cmd == "clear_msgs":
            try:
                self.clear_rows()
            except Exception:
                pass


# ====================================================================== #
# MoreOverlay — Overlay+ (custom URL overlay สูงสุด 3 อัน)
# แบบง่าย: spawn Qt subprocess ที่ load URL ภายนอก (ไม่ต้องมี server)
# แยก queue file ตาม overlay_id (กันชนกับ Game Overlay หลัก)
# ====================================================================== #
class MoreOverlay:
    """Overlay+ — 1 instance = 1 custom URL overlay ลอยเหนือเกม

    ใช้ game_overlay_qt.py subprocess (เหมือน GameOverlay) แต่:
    - โหลด URL ภายนอก (Streamlabs/StreamElements/alert)
    - ไม่ต้องมี server
    - ใช้ queue file แยกตาม overlay_id
    - ส่ง position กลับ parent ตอน drag/resize (เพื่อบันทึก)
    """

    def __init__(self, parent_app, overlay_id: str, url: str,
                 x: int = -1, y: int = -1, w: int = 400, h: int = 300,
                 alpha: float = 0.85) -> None:
        self.parent_app = parent_app
        self.overlay_id = overlay_id
        self.url = url
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.alpha = alpha
        self._proc: Optional[subprocess.Popen] = None
        self._hwnd: Optional[int] = None
        self._edit_mode = False
        self._hidden = False  # ซ่อนอยู่ไหม (hotkey toggle)
        self._reader_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    @property
    def is_running(self) -> bool:
        if self._proc is None:
            return False
        return self._proc.poll() is None

    def start(self) -> bool:
        """spawn Qt subprocess ที่ load URL นี้"""
        # debug log
        try:
            import tempfile as _tf, os as _os
            debug_path = _os.path.join(_tf.gettempdir(), "more_overlay_start.log")
            with open(debug_path, "a", encoding="utf-8") as f:
                f.write(f"MoreOverlay.start() called: id={self.overlay_id} url={self.url[:60]}\n")
        except Exception:
            pass
        # อ่าน hotkey จาก settings เพื่อแสดงใน edit bar
        hk_toggle = getattr(self.parent_app.settings, "more_overlay_hotkey", "ctrl+shift+m")
        hk_edit = getattr(self.parent_app.settings, "more_overlay_hotkey_edit", "ctrl+shift+n")
        # เคลียร์ queue file เก่า (กันคำสั่ง quit ค้างจาก session ก่อน)
        import tempfile
        for qf in [
            os.path.join(tempfile.gettempdir(), f"game_overlay_cmd_queue_{self.overlay_id}.json"),
            os.path.join(tempfile.gettempdir(), f"game_overlay_response_queue_{self.overlay_id}.json"),
        ]:
            try:
                with open(qf, "w", encoding="utf-8") as f:
                    json.dump([], f)
            except Exception:
                pass
        args = [_python_exe()]
        if _is_frozen():
            args.append("--game-overlay-qt")
        else:
            args.append(_overlay_script_path())
        args += [
            "--url", self.url,
            "--id", self.overlay_id,
            "--mode", "overlay+",
            "--hk-toggle", hk_toggle,
            "--hk-edit", hk_edit,
            "--x", str(self.x),
            "--y", str(self.y),
            "--w", str(self.w),
            "--h", str(self.h),
            "--alpha", str(self.alpha),
            "--port", "0",  # ไม่ใช้ server (URL ภายนอก)
        ]
        try:
            self._proc = subprocess.Popen(
                args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=get_base_dir(),
                encoding="utf-8",
            )
        except Exception as exc:
            self.parent_app._safe_status(f"❌ Overlay+ [{self.overlay_id}] spawn: {exc}")
            return False

        # debug spawn
        try:
            import tempfile as _tf, os as _os
            debug_path = _os.path.join(_tf.gettempdir(), "more_overlay_spawn.log")
            with open(debug_path, "a", encoding="utf-8") as f:
                f.write(f"proc spawned, poll={self._proc.poll()}\n")
        except Exception:
            pass

        # start reader thread (อ่าน response queue สำหรับ position/exit_edit)
        self._stop_event.clear()
        self._reader_thread = threading.Thread(
            target=self._reader_loop, name=f"MoreOverlay-{self.overlay_id}", daemon=True,
        )
        self._reader_thread.start()

        # รอ subprocess เริ่มต้น (เหมือน GameOverlay เดิม — reader_loop จะอ่าน hwnd ทีหลัง)
        import time as _time
        for _ in range(30):  # max 3s
            if self._hwnd is not None or not self.is_running:
                break
            _time.sleep(0.1)

        # debug log
        try:
            debug_path = os.path.join(get_base_dir(), "more_overlay_debug.log")
            with open(debug_path, "a", encoding="utf-8") as f:
                f.write(f"MoreOverlay[{self.overlay_id}] start: hwnd={self._hwnd} running={self.is_running}\n")
        except Exception:
            pass

        return self.is_running

    def stop(self) -> None:
        """ปิด subprocess"""
        self._stop_event.set()
        # ไม่ส่ง quit ผ่าน queue (กัน quit ค้างใน queue ไป session ถัดไป)
        # ใช้ terminate อย่างเดียว + เคลียร์ queue ทันที
        if self._proc is not None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=3)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
        self._proc = None
        self._hwnd = None
        self._edit_mode = False
        # เคลียร์ queue file หลัง stop (กันคำสั่งเก่าค้าง)
        import tempfile
        for qf in [
            os.path.join(tempfile.gettempdir(), f"game_overlay_cmd_queue_{self.overlay_id}.json"),
            os.path.join(tempfile.gettempdir(), f"game_overlay_response_queue_{self.overlay_id}.json"),
        ]:
            try:
                with open(qf, "w", encoding="utf-8") as f:
                    json.dump([], f)
            except Exception:
                pass

    def toggle_edit_mode(self) -> None:
        """toggle edit mode (border + drag + resize)"""
        self._edit_mode = not self._edit_mode
        self._send_cmd("edit_on" if self._edit_mode else "edit_off")

    def hide(self) -> None:
        """ซ่อน overlay (click-through อยู่ แต่มองไม่เห็น)"""
        self._hidden = True
        # ใช้ Windows API ซ่อน window ผ่าน hwnd
        if self._hwnd:
            try:
                import ctypes
                ctypes.windll.user32.ShowWindow(self._hwnd, 0)  # SW_HIDE
            except Exception:
                pass

    def show(self) -> None:
        """แสดง overlay กลับมา"""
        self._hidden = False
        if self._hwnd:
            try:
                import ctypes
                ctypes.windll.user32.ShowWindow(self._hwnd, 5)  # SW_SHOW
            except Exception:
                pass

    @property
    def hidden(self) -> bool:
        return self._hidden

    # ------------------------------------------------------------------ #
    # Subprocess communication (file-based queue แยกตาม id)
    # ------------------------------------------------------------------ #
    def _send_cmd(self, cmd: str) -> None:
        self._send_cmd_json({"cmd": cmd})

    def _send_cmd_json(self, msg: dict) -> None:
        """ส่ง command ไป subprocess ผ่าน file-based queue (atomic write กัน race)"""
        import tempfile
        queue_file = os.path.join(
            tempfile.gettempdir(), f"game_overlay_cmd_queue_{self.overlay_id}.json"
        )
        try:
            existing = []
            if os.path.exists(queue_file):
                try:
                    with open(queue_file, "r", encoding="utf-8") as f:
                        content = f.read().strip()
                    if content:
                        existing = json.loads(content)
                        if not isinstance(existing, list):
                            existing = []
                except (json.JSONDecodeError, ValueError):
                    existing = []
            existing.append(msg)
            # ★ atomic write: temp + replace (กัน race กับ Qt poller)
            tmp_fd, tmp_path = tempfile.mkstemp(
                dir=tempfile.gettempdir(), suffix=".json", prefix="mo_cmd_",
            )
            try:
                with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                    json.dump(existing, f)
                os.replace(tmp_path, queue_file)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
                raise
        except Exception:
            pass

    def _read_stdout_line(self, timeout=0.1):
        """อ่าน 1 line จาก subprocess stdout (non-blocking, ใช้ thread)"""
        import threading
        result = [None]
        def _read():
            try:
                if self._proc and self._proc.stdout:
                    result[0] = self._proc.stdout.readline()
            except Exception:
                pass
        t = threading.Thread(target=_read, daemon=True)
        t.start()
        t.join(timeout)
        return result[0]

    def _reader_loop(self) -> None:
        """อ่าน response จาก subprocess (file-based queue แยกตาม id)"""
        import tempfile, time as _time
        response_file = os.path.join(
            tempfile.gettempdir(), f"game_overlay_response_queue_{self.overlay_id}.json"
        )
        exit_handled = False
        while not self._stop_event.is_set():
            try:
                # ตรวจ process exit
                if not exit_handled and self._proc is not None and self._proc.poll() is not None:
                    exit_handled = True
                    self._hwnd = None
                    try:
                        self.parent_app._safe_status(f"⛔ Overlay+ [{self.overlay_id}] ปิดแล้ว")
                    except Exception:
                        pass
                if os.path.exists(response_file):
                    with open(response_file, "r", encoding="utf-8") as f:
                        responses = json.load(f)
                    if responses:
                        with open(response_file, "w", encoding="utf-8") as f:
                            json.dump([], f)
                        for resp in responses:
                            self._handle_response(resp)
            except Exception:
                pass
            _time.sleep(0.2)

    def _handle_response(self, resp: dict) -> None:
        """จัดการ response จาก subprocess"""
        cmd = resp.get("cmd", "")
        if cmd == "ready":
            self._hwnd = resp.get("hwnd")
        elif cmd == "position":
            # บันทึกตำแหน่ง/ขนาดใหม่ (drag/resize สำเร็จ)
            x = resp.get("x", self.x)
            y = resp.get("y", self.y)
            w = resp.get("w", self.w)
            h = resp.get("h", self.h)
            self.x, self.y, self.w, self.h = x, y, w, h
            # ส่ง callback ให้ parent บันทึกลง settings
            try:
                self.parent_app.after(0, lambda: self.parent_app._save_more_overlay_position(
                    self.overlay_id, x, y, w, h
                ))
            except Exception:
                pass
        elif cmd == "exit_edit":
            self._edit_mode = False


# ====================================================================== #
# ViewerOverlay — overlay อิสระสำหรับแสดงยอดคนดู (แยกจาก Game Overlay)
# ====================================================================== #
class ViewerOverlay:
    """Viewer Overlay manager — server + Qt subprocess ของตัวเอง

    แยกอิสระจาก Game Overlay:
    - server ของตัวเอง (port 8790-8800)
    - Qt subprocess ของตัวเอง (--mode viewer --id viewer0)
    - HTML ของตัวเอง (viewer_overlay.html)
    เปิด/ปิดได้เอง ไม่ต้องเปิด Game Overlay ก่อน
    """

    def __init__(self, parent_app) -> None:
        self.parent_app = parent_app
        self.settings = parent_app.settings
        self._server = None
        self._proc: Optional[subprocess.Popen] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    @property
    def is_running(self) -> bool:
        if self._proc is None:
            return False
        return self._proc.poll() is None

    def _find_free_port(self, start: int = 8790, end: int = 8800):
        """หา port ว่าง (ช่วง 8790-8800 — ไม่ทับ Game Overlay 8767-8780)"""
        import socket
        for port in range(start, end + 1):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.bind(("127.0.0.1", port))
                    return port
            except OSError:
                continue
        return None

    def start(self) -> bool:
        """start server + spawn Qt subprocess"""
        from viewer_overlay_server import ViewerOverlayServer
        port = self._find_free_port()
        if port is None:
            self.parent_app._safe_status("❌ Viewer Overlay: ไม่พบ port ว่าง (8790-8800)")
            return False
        try:
            self._server = ViewerOverlayServer(self.settings, port=port)
            if not self._server.start():
                self.parent_app._safe_status(
                    f"❌ Viewer Overlay server: {self._server._start_error}"
                )
                return False
        except Exception as exc:
            self.parent_app._safe_status(f"❌ Viewer Overlay server error: {exc}")
            return False

        # spawn Qt subprocess
        s = self.settings
        args = [_python_exe()]
        if _is_frozen():
            args.append("--game-overlay-qt")
        else:
            args.append(_overlay_script_path())
        args += [
            "--mode", "viewer",
            "--id", "viewer0",
            "--port", str(port),
            "--x", str(getattr(s, "viewer_overlay_x", -1)),
            "--y", str(getattr(s, "viewer_overlay_y", -1)),
            "--w", str(getattr(s, "viewer_overlay_width", 400)),
            "--h", str(getattr(s, "viewer_overlay_height", 80)),
            "--alpha", str(getattr(s, "viewer_overlay_alpha", 1.0)),
        ]
        try:
            self._proc = subprocess.Popen(
                args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=get_base_dir(),
                encoding="utf-8",
            )
            # ★ ผูก subprocess เข้า Job Object — กันค้างเมื่อ parent ตาย/crash
            _assign_to_job(self._proc)
        except Exception as exc:
            self.parent_app._safe_status(f"❌ Viewer Overlay spawn: {exc}")
            self._server.stop()
            self._server = None
            return False

        self._stop_event.clear()
        self._reader_thread = threading.Thread(
            target=self._reader_loop, name="ViewerOverlayReader", daemon=True,
        )
        self._reader_thread.start()

        # รอ subprocess พร้อม (max 5s)
        import time as _time
        for _ in range(50):
            if not self.is_running:
                break
            _time.sleep(0.1)

        if self.is_running:
            self.parent_app._safe_status(f"✅ Viewer Overlay เปิดแล้ว (port {port})")
            return True
        else:
            self.parent_app._safe_status("❌ Viewer Overlay: subprocess ปิดตัวเอง")
            return False

    def stop(self) -> None:
        """stop subprocess + server"""
        self._stop_event.set()
        if self._proc is not None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=3)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None
        if self._server is not None:
            try:
                self._server.stop()
            except Exception:
                pass
            self._server = None
        if self._reader_thread is not None and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=2)
        self._reader_thread = None

    def push_counts(self, total: int, platforms: dict) -> None:
        """push ยอดคนดูไปยัง overlay"""
        if self._server is not None:
            try:
                self._server.push_viewer_counts(total, platforms)
            except Exception:
                pass

    def _send_cmd_json(self, msg: dict) -> None:
        """ส่ง command ไป subprocess ผ่าน file-based queue (atomic write กัน race)"""
        import tempfile
        queue_file = os.path.join(tempfile.gettempdir(), "game_overlay_cmd_queue_viewer0.json")
        try:
            existing = []
            if os.path.exists(queue_file):
                try:
                    with open(queue_file, "r", encoding="utf-8") as f:
                        content = f.read().strip()
                    if content:
                        existing = json.loads(content)
                        if not isinstance(existing, list):
                            existing = []
                except (json.JSONDecodeError, ValueError):
                    existing = []
            existing.append(msg)
            tmp_fd, tmp_path = tempfile.mkstemp(
                dir=tempfile.gettempdir(), suffix=".json", prefix="vo_cmd_",
            )
            try:
                with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                    json.dump(existing, f)
                os.replace(tmp_path, queue_file)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
                raise
        except Exception:
            pass

    def _send_cmd(self, cmd: str) -> None:
        """ส่ง command ไป subprocess"""
        self._send_cmd_json({"cmd": cmd})

    def toggle_edit_mode(self) -> None:
        """toggle Setup ↔ Overlay mode (drag/resize)"""
        if not self.is_running:
            return
        self._send_cmd("edit_toggle")

    def hide(self) -> None:
        """ซ่อนหน้าต่าง overlay (ไม่ปิด process)"""
        if self._proc is None:
            return
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            # หา hwnd จาก subprocess — ใช้ EnumWindows หา window ของ PID
            hwnd_found = []
            def _enum(hwnd, lparam):
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value == self._proc.pid and user32.IsWindowVisible(hwnd):
                    hwnd_found.append(hwnd)
                return True
            user32.EnumWindows(ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(_enum), 0)
            for h in hwnd_found:
                user32.ShowWindow(h, 0)  # SW_HIDE = 0
        except Exception:
            pass

    def show(self) -> None:
        """แสดงหน้าต่าง overlay ที่ซ่อนไว้"""
        if self._proc is None:
            return
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            hwnd_found = []
            def _enum(hwnd, lparam):
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value == self._proc.pid:
                    hwnd_found.append(hwnd)
                return True
            user32.EnumWindows(ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(_enum), 0)
            for h in hwnd_found:
                user32.ShowWindow(h, 5)  # SW_SHOW = 5
        except Exception:
            pass

    def update_settings(self) -> None:
        """re-push config หลัง settings เปลี่ยน (live update)"""
        if not self.is_running:
            return
        self.settings = self.parent_app.settings
        if self._server is not None:
            self._server.update_config(self.settings)

    def _reader_loop(self) -> None:
        """ตรวจ process exit + อ่าน response จาก subprocess (position ฯลฯ)"""
        import time as _time
        import tempfile
        response_file = os.path.join(tempfile.gettempdir(), "game_overlay_response_queue_viewer0.json")
        exit_handled = False
        while not self._stop_event.is_set():
            try:
                # ตรวจ process exit
                if not exit_handled and self._proc is not None and self._proc.poll() is not None:
                    exit_handled = True
                    try:
                        self.settings.viewer_overlay_enabled = False
                        from settings import save_settings
                        save_settings(self.settings)
                        self.parent_app.after(0, self.parent_app._update_viewer_overlay_btn)
                        self.parent_app._safe_status("⛔ Viewer Overlay ปิดแล้ว")
                    except Exception:
                        pass
                # อ่าน response queue (position callback จาก Qt)
                if os.path.exists(response_file):
                    responses = []
                    try:
                        with open(response_file, "r", encoding="utf-8") as f:
                            responses = json.load(f)
                        if responses:
                            with open(response_file, "w", encoding="utf-8") as f:
                                json.dump([], f)
                    except Exception:
                        responses = []
                    for msg in responses:
                        self._handle_response(msg)
            except Exception:
                pass
            _time.sleep(0.2)

    def _handle_response(self, msg: dict) -> None:
        """จัดการ response จาก subprocess"""
        cmd = msg.get("cmd")
        if cmd == "position":
            # user ลาก/ปรับขนาด → บันทึกลง settings
            x = msg.get("x", -1)
            y = msg.get("y", -1)
            w = msg.get("w", 400)
            h = msg.get("h", 80)
            try:
                self.settings.viewer_overlay_x = int(x)
                self.settings.viewer_overlay_y = int(y)
                self.settings.viewer_overlay_width = int(w)
                self.settings.viewer_overlay_height = int(h)
                from settings import save_settings
                save_settings(self.settings)
            except Exception:
                pass
