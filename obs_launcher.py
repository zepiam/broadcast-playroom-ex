"""obs_launcher.py — เปิด OBS หรือดึงหน้าต่าง OBS ขึ้นมา (Switch To)

การทำงาน:
- ถ้า OBS รันอยู่ → ดึงหน้าต่างขึ้นมาเป็น foreground (เหมือน Task Manager > Switch To)
- ถ้า OBS ยังไม่รัน → เปิดจาก path มาตรฐาน

★ Path สากลของ OBS:
  C:\\Program Files\\obs-studio\\bin\\64bit\\obs64.exe
"""
import os
import ctypes
import logging
import subprocess
from ctypes import wintypes

logger = logging.getLogger("obs_launcher")

# ★ Path สากลของ OBS (installer ทางการ)
OBS_EXE = r"C:\Program Files\obs-studio\bin\64bit\obs64.exe"

# ═══ Win32 API (ctypes) ═══
_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

# setup signatures
_user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
_user32.FindWindowW.restype = wintypes.HWND
_user32.IsWindowVisible.argtypes = [wintypes.HWND]
_user32.IsWindowVisible.restype = wintypes.BOOL
_user32.GetForegroundWindow.argtypes = []
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_user32.GetWindowThreadProcessId.restype = wintypes.DWORD
_user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
_user32.AttachThreadInput.restype = wintypes.BOOL
_user32.SetForegroundWindow.argtypes = [wintypes.HWND]
_user32.SetForegroundWindow.restype = wintypes.BOOL
_user32.SetActiveWindow.argtypes = [wintypes.HWND]
_user32.SetActiveWindow.restype = wintypes.HWND
_user32.BringWindowToTop.argtypes = [wintypes.HWND]
_user32.BringWindowToTop.restype = wintypes.BOOL
_user32.ShowWindow.argtypes = [wintypes.HWND, wintypes.INT]
_user32.ShowWindow.restype = wintypes.BOOL
_user32.IsIconic.argtypes = [wintypes.HWND]
_user32.IsIconic.restype = wintypes.BOOL
_user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
_user32.GetWindowTextLengthW.restype = wintypes.INT
_user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, wintypes.INT]
_user32.GetWindowTextW.restype = wintypes.INT
_kernel32.GetCurrentThreadId.argtypes = []
_kernel32.GetCurrentThreadId.restype = wintypes.DWORD

SW_RESTORE = 9


def _get_obs_pids():
    """หา PID ทั้งหมดของ obs64.exe (จาก tasklist) → set of int"""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq obs64.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=3,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0 or "obs64.exe" not in (result.stdout or "").lower():
            return set()
        import csv, io
        pids = set()
        for row in csv.reader(io.StringIO(result.stdout)):
            if len(row) >= 2 and "obs64" in row[0].lower():
                try:
                    pids.add(int(row[1].strip('"').strip()))
                except ValueError:
                    pass
        return pids
    except Exception as e:
        logger.debug(f"_get_obs_pids error: {e}")
        return set()


def _find_obs_window():
    """หาหน้าต่าง OBS ที่รันอยู่ → คืน hwnd หรือ None

    ★ ค้นหา 2 วิธี (เรียงตามความแม่นยำ):
       1. EnumWindows → เทียบ PID ของ obs64.exe (แม่นยำที่สุด)
       2. FindWindowW ด้วย title/class "OBS" (fallback)
    ★ รวมทั้ง visible + hidden window (OBS อาจ minimize ไป tray)
    """
    obs_pids = _get_obs_pids()
    if not obs_pids:
        return None

    # ★ วิธี 1: EnumWindows + เทียบ PID (หาแม้กระทั่ง hidden window)
    found_hwnds = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _callback(hwnd, lparam):
        # ★ อ่าน PID ของ window นี้
        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in obs_pids:
            # ★ เช็คว่าเป็น top-level window ที่มี title (ไม่ใช่ child/tooltip)
            length = _user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                found_hwnds.append(hwnd)
        return True  # ต่อ enumeration

    try:
        _user32.EnumWindows(_callback, 0)
    except Exception as e:
        logger.debug(f"EnumWindows error: {e}")

    if found_hwnds:
        # ★ เลือก window ที่ใหญ่สุด / visible แรก
        #   OBS มักมีหลาย window (main + projector) → เอาอันแรกที่ visible
        for hwnd in found_hwnds:
            if _user32.IsWindowVisible(hwnd):
                return hwnd
        return found_hwnds[0]  # ไม่มี visible → คืนอันแรก (จะ restore ทีหลัง)

    return None


def _bring_to_front(hwnd):
    """ดึง window ขึ้นมาเป็น foreground (AttachThreadInput trick — กัน SetForegroundWindow fail)"""
    try:
        # ★ restore ถ้า minimize
        if _user32.IsIconic(hwnd):
            _user32.ShowWindow(hwnd, SW_RESTORE)
        # ★ ถ้าไม่ visible → สั่ง show
        if not _user32.IsWindowVisible(hwnd):
            _user32.ShowWindow(hwnd, 5)  # SW_SHOW

        fg = _user32.GetForegroundWindow()
        fg_tid = _user32.GetWindowThreadProcessId(fg, None)
        my_tid = _kernel32.GetCurrentThreadId()
        target_tid = _user32.GetWindowThreadProcessId(hwnd, None)

        attached = False
        if fg_tid != target_tid:
            attached = _user32.AttachThreadInput(fg_tid, target_tid, True)

        _user32.BringWindowToTop(hwnd)
        _user32.SetForegroundWindow(hwnd)
        _user32.SetActiveWindow(hwnd)

        if attached:
            _user32.AttachThreadInput(fg_tid, target_tid, False)
        return True
    except Exception as e:
        logger.debug(f"_bring_to_front error: {e}")
        return False


def launch_obs():
    """เปิด OBS หรือดึงหน้าต่าง OBS ขึ้นมา (Switch To)

    Returns:
        (ok: bool, message: str)
    """
    # ★ ตรวจก่อนว่า OBS รันอยู่ → ดึงหน้าต่างขึ้นมา
    hwnd = _find_obs_window()
    if hwnd:
        logger.info(f"OBS running — bringing window to front (hwnd={hwnd})")
        if _bring_to_front(hwnd):
            return True, "ดึงหน้าต่าง OBS ขึ้นมาแล้ว"
        return True, "OBS รันอยู่แล้ว (ดึงหน้าต่างไม่สำเร็จ)"

    # ★ OBS ยังไม่รัน → เปิดใหม่
    if not os.path.exists(OBS_EXE):
        logger.warning(f"OBS not found at: {OBS_EXE}")
        return False, "ไม่พบ OBS — ติดตั้งจาก https://obsproject.com"

    try:
        logger.info(f"Launching OBS: {OBS_EXE}")
        # ★ ใช้ start "" "path" ผ่าน shell=True → cmd.exe จัดการ elevation อัตโนมัติ
        subprocess.Popen(
            f'start "" "{OBS_EXE}"',
            shell=True,
            cwd=os.path.dirname(OBS_EXE),
        )
        logger.info("OBS launched")
        return True, "กำลังเปิด OBS..."
    except Exception as e:
        logger.error(f"Failed to launch OBS: {e}")
        return False, f"เปิด OBS ไม่ได้: {e}"
