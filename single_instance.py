"""single_instance.py — ป้องกันการเปิดโปรแกรมซ้อน (single-instance lock)

ใช้ Windows named mutex (Global\\BroadcastPlayroom_SingleInstance) เพื่อตรวจว่า
มี instance รันอยู่แล้วหรือไม่

★ ถ้ามี instance รันอยู่ → คืน False → main.py จะแสดง modal ถาม user
★ ถ้าไม่มี → คืน True + จับ mutex ไว้ตลอดการทำงาน

★ Windows-only (ใช้ ctypes CreateMutexW) — ไม่ต้องลง dependency
"""
import ctypes
from ctypes import wintypes
import logging

logger = logging.getLogger("single_instance")

# ★ Mutex name — Global prefix = ทุก session ของ user เห็น (กันข้าม session)
MUTEX_NAME = "Global\\BroadcastPlayroom_SingleInstance_v2"

# ★ เก็บ handle ของ mutex ไว้ตลอดการทำงาน (ถ้า release → instance อื่นเข้ามาได้)
_mutex_handle = None


def acquire_lock() -> bool:
    """พยายามจับ mutex → คืน True ถ้าไม่มี instance อื่นรันอยู่

    Returns:
        True = ไม่มี instance อื่น → ทำงานต่อได้
        False = มี instance รันอยู่แล้ว → หยุด (หรือถาม user)
    """
    global _mutex_handle
    try:
        # ★ CreateMutexW — สร้าง mutex (หรือเปิดที่มีอยู่)
        #   bInitialOwner=True → ขอเป็นเจ้าของทันที
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.argtypes = [wintypes.LPCVOID, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.CreateMutexW.restype = wintypes.HANDLE

        _mutex_handle = kernel32.CreateMutexW(None, True, MUTEX_NAME)

        # ★ GetLastError — ถ้าคืน ERROR_ALREADY_EXISTS (183) = มี instance อื่น
        last_error = kernel32.GetLastError()
        ERROR_ALREADY_EXISTS = 183

        if last_error == ERROR_ALREADY_EXISTS:
            logger.info("Another instance is already running (mutex exists)")
            # ★ ปิด handle ของเรา (เพราะไม่ได้เป็นเจ้าของจริง)
            kernel32.CloseHandle(_mutex_handle)
            _mutex_handle = None
            return False

        logger.info("Single-instance lock acquired")
        return True
    except Exception as e:
        # ★ ถ้า ctypes fail (เช่น ไม่ใช่ Windows) → ไม่ล็อค (ยอมให้เปิดซ้อน)
        logger.warning(f"single_instance lock failed: {e} — allowing multiple instances")
        return True


def release_lock():
    """ปล่อย mutex (เรียกตอนปิดโปรแกรม)"""
    global _mutex_handle
    if _mutex_handle:
        try:
            kernel32 = ctypes.windll.kernel32
            kernel32.CloseHandle(_mutex_handle)
        except Exception:
            pass
        _mutex_handle = None


def find_playroom_windows():
    """หา window ของ Broadcast Playroom ที่รันอยู่ (EnumWindows)

    Returns:
        list of hwnd ที่ title ขึ้นต้นด้วย "Broadcast Playroom"
    """
    found = []
    try:
        user32 = ctypes.windll.user32
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.restype = wintypes.INT
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, wintypes.INT]
        user32.GetWindowTextW.restype = wintypes.INT
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def _callback(hwnd, lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value
                # ★ title = "Broadcast Playroom by MeN9CH"
                if "Broadcast Playroom" in title:
                    found.append(hwnd)
            return True

        user32.EnumWindows(_callback, 0)
    except Exception as e:
        logger.debug(f"find_playroom_windows error: {e}")
    return found


def bring_to_front(hwnd):
    """ดึง window ขึ้นมาเป็น foreground"""
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        # setup signatures
        user32.GetForegroundWindow.argtypes = []
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
        user32.AttachThreadInput.restype = wintypes.BOOL
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.SetForegroundWindow.restype = wintypes.BOOL
        user32.ShowWindow.argtypes = [wintypes.HWND, wintypes.INT]
        user32.ShowWindow.restype = wintypes.BOOL
        user32.IsIconic.argtypes = [wintypes.HWND]
        user32.IsIconic.restype = wintypes.BOOL
        kernel32.GetCurrentThreadId.argtypes = []
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD
        user32.BringWindowToTop.argtypes = [wintypes.HWND]
        user32.BringWindowToTop.restype = wintypes.BOOL

        SW_RESTORE = 9
        # ★ restore ถ้า minimize
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)

        fg = user32.GetForegroundWindow()
        fg_tid = user32.GetWindowThreadProcessId(fg, None)
        my_tid = kernel32.GetCurrentThreadId()
        target_tid = user32.GetWindowThreadProcessId(hwnd, None)

        attached = False
        if fg_tid != target_tid:
            attached = user32.AttachThreadInput(fg_tid, target_tid, True)

        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)

        if attached:
            user32.AttachThreadInput(fg_tid, target_tid, False)
        return True
    except Exception as e:
        logger.debug(f"bring_to_front error: {e}")
        return False


def kill_playroom_process(exclude_self: bool = True):
    """Kill โปรเซส Broadcast Playroom ทั้งหมด (ยกเว้นตัวเอง)

    Args:
        exclude_self: True = ไม่ kill ตัวเอง (default)

    Returns:
        (ok: bool, message: str)
    """
    import subprocess, os
    try:
        # ★ หา PID ของตัวเอง (เพื่อ exclude)
        self_pid = os.getpid() if exclude_self else -1

        # ★ tasklist หา Broadcast Playroom Full.exe / BroadcastPlayroom_Lite.exe
        #   หรือ python.exe ที่รัน main.py (dev mode)
        result = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0:
            return False, "ไม่สามารถอ่านรายการ process ได้"

        # ★ parse CSV → หา process ที่เกี่ยวข้อง
        import csv, io
        reader = csv.reader(io.StringIO(result.stdout))
        targets = []  # list of (pid, name)
        for row in reader:
            if len(row) >= 2:
                name = row[0].strip('"').lower()
                pid_str = row[1].strip('"').strip()
                try:
                    pid = int(pid_str)
                except ValueError:
                    continue
                # ★ match process name
                # ★ รองับทั้งชื่อติดกัน (Full) และมีช่องว่าง (Lite)
                if "broadcastplayroom" in name or "broadcast playroom" in name:
                    if pid != self_pid:
                        targets.append((pid, row[0].strip('"')))
                # ★ dev mode: python.exe ที่รัน main.py — เดี๋ยวว่ากัน (ยากเกินไปที่จะแยก)

        # ★ dev mode — หา python.exe ที่รัน main.py ด้วย wmic
        if not targets:
            try:
                wmic = subprocess.run(
                    ["wmic", "process", "where", "name='python.exe'",
                     "get", "processid,commandline", "/FORMAT:CSV"],
                    capture_output=True, text=True, timeout=5,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                if wmic.returncode == 0 and wmic.stdout:
                    import csv as _csv
                    reader2 = _csv.reader(io.StringIO(wmic.stdout))
                    for row2 in reader2:
                        if len(row2) >= 3:
                            cmdline = row2[1].strip()
                            pid2_str = row2[2].strip()
                            try:
                                pid2 = int(pid2_str)
                            except ValueError:
                                continue
                            if "main.py" in cmdline.lower() and pid2 != self_pid:
                                targets.append((pid2, "python.exe (main.py)"))
                                logger.info(f"Found dev process: PID {pid2}")
            except Exception as e:
                logger.debug(f"wmic scan failed: {e}")

        if not targets:
            return False, "ไม่พบโปรเซส Broadcast Playroom"

        # ★ kill ทีละตัว
        killed = 0
        for pid, name in targets:
            try:
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(pid)],
                    capture_output=True, timeout=5,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                killed += 1
                logger.info(f"Killed {name} (PID {pid})")
            except Exception as e:
                logger.warning(f"Failed to kill {name} (PID {pid}): {e}")

        import time
        time.sleep(1)  # รอให้ปิดสนิท

        if killed > 0:
            return True, f"ปิด Broadcast Playroom ที่ค้างไว้แล้ว ({killed} ตัว)"
        return False, "ปิดไม่สำเร็จ (อาจไม่มีสิทธิ์)"
    except Exception as e:
        logger.error(f"kill_playroom_process error: {e}")
        return False, f"ปิดไม่ได้: {e}"
