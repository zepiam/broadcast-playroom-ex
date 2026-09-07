"""updater.py — Auto-update (เหมือน v1 — ดาวน์โหลด version.json จาก release)

Flow:
1. ดาวน์โหลด version.json จาก release URL
2. เทียบเวอร์ชั่น
3. ถ้ามีใหม่ → แจ้ง user → เปิด browser ดาวน์โหลด

★ version.json ใน release มีโครง:
  { "version": "2.1.0", "changelog": "...",
    "lite": {"type": "major", "url": "..."},
    "full": {"type": "major", "url": "..."} }
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import ssl
import threading
import time
import urllib.request
import webbrowser
from typing import Callable, Optional

# requests (optional — ใช้สำหรับ download layer 1)
try:
    import requests
except ImportError:
    requests = None

logger = logging.getLogger("updater")

# ★ URL สำหรับเช็คเวอร์ชั่นล่าสุด (GitHub API releases/latest)
VERSION_API_URL = "https://api.github.com/repos/zepiam/broadcast-playroom-ex/releases/latest"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"


def get_current_version() -> str:
    """อ่านเวอร์ชั่นปัจจุบันจาก version.json (bundled กับ exe)"""
    install_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(install_dir, "_internal", "version.json"),
        os.path.join(install_dir, "version.json"),
    ]
    for path in candidates:
        try:
            if os.path.exists(path):
                with open(path, encoding='utf-8') as f:
                    data = json.load(f)
                ver = data.get("version", "0.0.0")
                if ver and ver != "0.0.0":
                    return ver
        except Exception:
            pass
    return "0.0.0"


def get_build_type() -> str:
    """ตรวจ Lite/Full จากชื่อ exe"""
    try:
        exe_name = os.path.basename(sys.executable).lower()
        if "full" in exe_name:
            return "full"
        if "lite" in exe_name:
            return "lite"
    except Exception:
        pass
    try:
        import torch  # noqa: F401
        return "full"
    except ImportError:
        return "lite"


def _parse_version(v: str) -> list[int]:
    """แยก "2.1.0" → [2, 1, 0]"""
    cleaned = (v or "").strip().lower().lstrip("v")
    parts = []
    for p in cleaned.split("."):
        num = ""
        for ch in p:
            if ch.isdigit():
                num += ch
            else:
                break
        if num:
            parts.append(int(num))
    return parts or [0]


def is_version_newer(remote: str, local: str) -> bool:
    """เทียบเวอร์ชั่น — True ถ้า remote > local"""
    return _parse_version(remote) > _parse_version(local)


def fetch_remote_version(retries: int = 2, timeout: int = 10) -> Optional[dict]:
    """ดาวน์โหลด version.json จาก GitHub Releases (ผ่าน API latest → assets)

    ★ 3-layer SSL fallback (ทุกชั้น verify cert — ไม่มี CERT_NONE แล้ว):
      1. requests (รองรับ redirect + certifi)
      2. urllib + Windows cert store
      3. urllib + default SSL
    ★ ถ้าทุกชั้น fail (เช่น AV ตัด SSL) → คืน None = เงียบๆ ไม่มีปุ่ม update
      ดีกว่าเสี่ยงโหลดของปลอมแบบเดิม (MITM → RCE ผ่านช่องอัพเดท)
    """
    last_error = None
    for attempt in range(retries + 1):
        # ★ Stage 1: หา version.json URL จาก GitHub API
        release_data = None
        # Layer 1: requests
        if requests is not None:
            try:
                r = requests.get(VERSION_API_URL, headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/vnd.github+json",
                }, timeout=timeout, allow_redirects=True)
                if r.status_code == 200:
                    release_data = r.json()
            except Exception as e:
                last_error = e
                logger.debug(f"fetch_remote_version requests: {e}")

        # Layer 2-3: urllib (verify เท่านั้น — ไม่มี unverified)
        if release_data is None:
            for ctx_mode in ("win_cert", "default"):
                try:
                    if ctx_mode == "win_cert":
                        ctx = ssl.create_default_context()
                        ctx.load_default_certs()
                    else:
                        ctx = None  # default
                    req = urllib.request.Request(VERSION_API_URL, headers={
                        "User-Agent": USER_AGENT,
                        "Accept": "application/vnd.github+json",
                    })
                    kw = {"timeout": timeout}
                    if ctx:
                        kw["context"] = ctx
                    with urllib.request.urlopen(req, **kw) as r:
                        release_data = json.loads(r.read().decode("utf-8"))
                        break
                except Exception as e:
                    last_error = e
                    logger.debug(f"fetch_remote_version urllib ({ctx_mode}): {e}")

        if not release_data:
            if attempt < retries:
                time.sleep(1)
            continue

        # ★ Stage 2: หา version.json URL ใน assets
        version_url = None
        for asset in release_data.get("assets", []):
            if asset.get("name") == "version.json":
                version_url = asset.get("browser_download_url")
                break
        if not version_url:
            tag = release_data.get("tag_name", "latest")
            version_url = f"https://github.com/zepiam/broadcast-playroom-ex/releases/download/{tag}/version.json"

        # ★ security: URL ต้องเป็น https + github.com ของเราเท่านั้น
        #   (กัน version.json ปลอม/API ปลอมชี้ไปโดเมนอื่น)
        if not version_url.startswith("https://github.com/zepiam/broadcast-playroom-ex/"):
            logger.error(f"blocked non-github version url: {version_url}")
            return None

        # ★ Stage 3: ดาวน์โหลด version.json (verify เท่านั้น)
        # Layer 1: requests
        if requests is not None:
            try:
                r2 = requests.get(version_url, headers={"User-Agent": USER_AGENT},
                                  timeout=timeout, allow_redirects=True)
                if r2.status_code == 200 and r2.text:
                    return r2.json()
            except Exception as e:
                last_error = e
                logger.debug(f"fetch version.json requests: {e}")

        # Layer 2-3: urllib
        for ctx_mode in ("win_cert", "default"):
            try:
                if ctx_mode == "win_cert":
                    ctx = ssl.create_default_context()
                    ctx.load_default_certs()
                else:
                    ctx = None
                req2 = urllib.request.Request(version_url, headers={"User-Agent": USER_AGENT})
                kw = {"timeout": timeout}
                if ctx:
                    kw["context"] = ctx
                with urllib.request.urlopen(req2, **kw) as r2:
                    data = r2.read()
                    if data:
                        return json.loads(data.decode("utf-8"))
            except Exception as e:
                last_error = e
                logger.debug(f"fetch version.json urllib ({ctx_mode}): {e}")

        if attempt < retries:
            time.sleep(1)

    logger.warning(f"fetch_remote_version failed after {retries+1} attempts: {last_error}")
    return None


def check_for_update(build_type: Optional[str] = None) -> Optional[dict]:
    """ตรวจอัพเดท — คืน dict ข้อมูลอัพเดท หรือ None ถ้าไม่มีอัพเดท

    ★ แยก "ไม่มีอัพเดท" กับ "network error":
      - ไม่มีอัพเดท → คืน None
      - network error → raise Exception (caller จับได้)
      - มีอัพเดท → คืน dict

    Returns: {
        "current": "2.0.0",
        "latest": "2.1.0",
        "changelog": "...",
        "type": "patch" | "major",
        "url": "https://...",
        "build_type": "lite" | "full",
    }
    """
    bt = build_type or get_build_type()
    local_ver = get_current_version()
    remote = fetch_remote_version()
    if not remote:
        # ★ network error — raise ให้ caller แยกจาก "ไม่มีอัพเดท"
        raise RuntimeError("ไม่สามารถเชื่อมต่อ server ได้ (network/SSL error)")
    latest_ver = remote.get("version", "")
    if not latest_ver or not is_version_newer(latest_ver, local_ver):
        return None  # ไม่มีอัพเดท (version เท่ากันหรือเก่ากว่า)
    bt_info = remote.get(bt, {})
    if not bt_info:
        bt_info = {"type": "major", "url": ""}
    return {
        "current": local_ver,
        "latest": latest_ver,
        "changelog": remote.get("changelog", ""),
        "type": bt_info.get("type", "major"),
        "url": bt_info.get("url", ""),
        "sha256": bt_info.get("sha256", ""),  # ★ hash ของ patch zip (มีใน manifest ใหม่)
        "build_type": bt,
    }


def check_update_async(callback, build_type: Optional[str] = None):
    """เช็คอัพเดทใน background thread

    callback(info) — info = dict (มีอัพเดท), None (ไม่มีอัพเดท), หรือ {"error": "msg"} (network error)
    """
    import threading
    def _bg():
        try:
            info = check_for_update(build_type)
        except Exception as e:
            logger.debug(f"check_update_async: {e}")
            info = {"error": str(e)}  # ★ ส่ง error แยกจาก None (ไม่มีอัพเดท)
        callback(info)
    threading.Thread(target=_bg, name="UpdateChecker", daemon=True).start()


def open_url(url: str):
    """เปิด URL ใน browser"""
    try:
        webbrowser.open(url)
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════
# ★ Auto-update: download + apply_patch + restart (port จาก v1)
# ════════════════════════════════════════════════════════════════

def get_exe_name() -> str:
    """คืนชื่อ exe ปัจจุบัน (เช่น Broadcast Playroom Lite.exe)"""
    return os.path.basename(sys.executable)


def download_file(url: str, dest: str,
                  progress_cb: Optional[Callable[[int, int], None]] = None,
                  timeout: float = 300.0,
                  expected_sha256: Optional[str] = None) -> bool:
    """ดาวน์โหลดไฟล์ patch พร้อม progress callback

    progress_cb(downloaded_bytes, total_bytes) — เรียกทุก chunk
    Returns True ถ้าสำเร็จ

    ★ security:
      - URL ต้องเป็น https://github.com/zepiam/broadcast-playroom-ex/ เท่านั้น (ล็อค domain)
      - ทุก layer verify cert — ไม่มี unverified fallback (เดิม CERT_NONE = MITM โหลด patch ปลอมได้)
      - ถ้ามี expected_sha256 → ตรวจหลังโหลด ไม่ตรง = ลบไฟล์ + คืน False
    """
    # ★ security: ล็อค domain — patch ต้องมาจาก GitHub ของเราเท่านั้น
    if not url.startswith("https://github.com/zepiam/broadcast-playroom-ex/"):
        logger.error(f"download blocked — non-github url: {url}")
        return False

    def _write_stream(response, total_getter, read_fn) -> bool:
        """helper — เขียน stream ลงไฟล์ พร้อม progress callback"""
        total = total_getter()
        downloaded = 0
        chunk_size = 65536  # 64KB
        with open(dest, "wb") as f:
            while True:
                chunk = read_fn(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if progress_cb:
                    try:
                        progress_cb(downloaded, total)
                    except Exception:
                        pass
        return True

    def _verify_sha256() -> bool:
        """★ ตรวจ SHA-256 ของไฟล์ที่โหลดมา — ไม่ตรง = ลบทิ้ง + คืน False"""
        if not expected_sha256:
            return True  # manifest เก่าไม่มี hash → ข้าม (user เวอร์ชันเก่ายังอัพเดทได้)
        import hashlib
        h = hashlib.sha256()
        try:
            with open(dest, "rb") as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    h.update(chunk)
        except Exception as e:
            logger.error(f"sha256 read failed: {e}")
            return False
        actual = h.hexdigest().lower()
        if actual != expected_sha256.strip().lower():
            logger.error(f"sha256 MISMATCH — expected {expected_sha256}, got {actual}")
            try:
                os.remove(dest)  # ★ ลบไฟล์ปลอมทิ้ง
            except Exception:
                pass
            return False
        logger.info("sha256 verified ✓")
        return True

    # ── วิธี 1: requests (ดีสุด — จัดการ cert + redirect อัตโนมัติ) ──
    _dl_headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Origin": "https://github.com",
        "Referer": "https://github.com/",
    }
    if requests is not None:
        try:
            r = requests.get(url, headers=_dl_headers,
                             timeout=timeout, allow_redirects=True, stream=True)
            if r.status_code == 200:
                total = int(r.headers.get("Content-Length", 0))
                ok = _write_stream(
                    r, lambda: total,
                    lambda sz: next(r.iter_content(chunk_size=sz), b"")
                )
                return ok and _verify_sha256()
            logger.debug(f"download requests status={r.status_code}")
        except Exception as exc:
            logger.debug(f"download requests failed: {type(exc).__name__}: {exc}")

    # ── วิธี 2: urllib + Windows cert store (verify เท่านั้น) ──
    try:
        ctx = ssl.create_default_context()
        ctx.load_default_certs()  # โหลดจาก Windows cert store
        req = urllib.request.Request(url, headers=_dl_headers)
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            ok = _write_stream(
                r, lambda: int(r.headers.get("Content-Length", 0)),
                lambda sz: r.read(sz)
            )
            return ok and _verify_sha256()
    except Exception as exc:
        logger.debug(f"download urllib (win cert) failed: {type(exc).__name__}: {exc}")

    # ★ ไม่มี unverified fallback อีกต่อไป — โหลดไม่ได้ = False (ปลอดภัยกว่าโหลดของปลอม)
    return False


def apply_patch(zip_path: str) -> bool:
    """แตก patch zip ทับไฟล์ปัจจุบัน + รีสตาร์ท

    ใช้ batch script (stage-then-copy pattern):
      1. แตก zip ไป staging folder (ใน install_dir — ไม่ใช่ %TEMP% เพื่อลด AV suspicion)
      2. รอจนกว่า exe ปัจจุบันจะปิด
      3. copy ทับ
      4. รีสตาร์ท exe + self-delete batch

    ★ security: ตรวจ zip entries ก่อนแตก (กัน zip-slip — path ที่มี ../ หรือ absolute
      path จะเขียนทับไฟล์นอก install_dir ได้)

    Returns True ถ้าสร้าง bat สำเร็จ (โปรแกรมจะปิดตัวเองหลังจากนี้)
    """
    if not getattr(sys, 'frozen', False):
        logger.warning("apply_patch: not a frozen exe — skip (dev mode)")
        return False

    # ★ ตรวจ zip-slip ก่อนเขียน bat — ทุก entry ต้อง resolve อยู่ใน install_dir เท่านั้น
    try:
        import zipfile
        install_dir_real = os.path.realpath(os.path.dirname(sys.executable))
        with zipfile.ZipFile(zip_path, "r") as zf:
            for name in zf.namelist():
                target = os.path.realpath(os.path.join(install_dir_real, name))
                if not (target == install_dir_real or target.startswith(install_dir_real + os.sep)):
                    logger.error(f"apply_patch blocked — zip-slip entry: {name}")
                    try:
                        os.remove(zip_path)
                    except Exception:
                        pass
                    return False
    except zipfile.BadZipFile:
        logger.error("apply_patch: corrupt zip")
        return False

    exe_name = get_exe_name()
    install_dir = os.path.dirname(sys.executable)
    exe_path = os.path.join(install_dir, exe_name)
    staging = os.path.join(install_dir, ".update_staging")
    bat_path = os.path.join(install_dir, ".update.bat")
    log_path = os.path.join(install_dir, ".update.log")

    # ★ migration — หา exe ใหม่จาก patch (ชื่ออาจเปลี่ยน เช่น Full เดิม BroadcastPlayroom_Full → Broadcast Playroom Full)
    #   + เก็บรายการ exe เก่าที่ต้องลบหลังอัพเดท
    import zipfile as _zf
    new_exe_name = exe_name  # default = ชื่อเดิม
    old_exes_to_delete = []
    try:
        with _zf.ZipFile(zip_path, "r") as zf:
            for name in zf.namelist():
                if name.lower().endswith(".exe") and "/" not in name and "\\" not in name:
                    candidate = os.path.basename(name)
                    if candidate != exe_name:
                        new_exe_name = candidate
                        logger.info(f"apply_patch: exe name change detected: {exe_name} → {new_exe_name}")
    except Exception as e:
        logger.debug(f"exe name scan failed: {e}")
    # ★ exe เก่าที่ต้องลบ (ทุก .exe ใน install_dir ที่ไม่ใช่ตัวใหม่)
    try:
        for f in os.listdir(install_dir):
            if f.lower().endswith(".exe") and f != new_exe_name and f != exe_name:
                if "broadcast" in f.lower() or "playroom" in f.lower():
                    old_exes_to_delete.append(f)
                    logger.info(f"apply_patch: will delete old exe: {f}")
    except Exception:
        pass
    # ★ ใช้ exe ใหม่สำหรับ restart
    if new_exe_name != exe_name:
        exe_path = os.path.join(install_dir, new_exe_name)

    # ★ บรรทัด batch สำหรับลบ exe เก่า (migration ชื่อเปลี่ยน)
    #   ★ แก้บั๊ก NameError: เดิม f-string ใช้ {delete_old_exes} ซึ่งไม่มีตัวแปรนี้
    #     (ตัวแปรจริงชื่อ old_exes_to_delete) → กดอัพเดทแล้ว error ทันที
    delete_old_exes_lines = "".join(
        f'del "{os.path.join(install_dir, f)}" >nul 2>&1\n' for f in old_exes_to_delete)

    # batch script — stage-then-copy pattern
    bat = f"""@echo off
chcp 65001 >nul 2>&1
>"{log_path}" echo === Broadcast Playroom v2 updater ===
>>"{log_path}" echo staging: {staging}
>>"{log_path}" echo install: {install_dir}
>>"{log_path}" echo exe: {exe_name}

:: Stage 1: extract zip to staging (PowerShell Expand-Archive)
if exist "{staging}" rd /s /q "{staging}"
mkdir "{staging}"
powershell -NoProfile -Command "try {{ Expand-Archive -LiteralPath '{zip_path}' -DestinationPath '{staging}' -Force }} catch {{ exit 1 }}"
if errorlevel 1 (
  >>"{log_path}" echo FAIL: cannot extract zip
  exit /b 1
)

:: Stage 2: wait until exe is gone from tasklist
:waitloop
tasklist /fi "imagename eq {exe_name}" 2>nul | find /i "{exe_name}" >nul
if not errorlevel 1 (
  ping 127.0.0.1 -n 2 >nul
  goto waitloop
)

:: Stage 2b: 3s buffer for OS to release mutex/file handle
>>"{log_path}" echo waiting for OS cleanup (3s)...
ping 127.0.0.1 -n 4 >nul

:: Stage 3: recursive overwrite copy
>>"{log_path}" echo copying files...
xcopy /y /e /i "{staging}\\*" "{install_dir}\\" >nul 2>&1

:: Stage 4: cleanup old exe files (migration — ชื่อเปลี่ยน)
{delete_old_exes_lines}
:: Stage 5: cleanup + restart + self-delete
rd /s /q "{staging}" 2>nul
del "{zip_path}" 2>nul
>>"{log_path}" echo done — restarting
start "" "{exe_path}"
(goto) 2>nul & del "%~f0"
"""
    try:
        with open(bat_path, "w", encoding="utf-8") as f:
            f.write(bat)
        # spawn batch (hidden) → ปิดโปรแกรม
        subprocess.Popen(
            ["cmd", "/c", bat_path],
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        logger.info(f"Update batch spawned: {bat_path}")
        return True
    except Exception as e:
        logger.error(f"apply_patch failed: {e}")
        return False


def start_patch_update(url: str,
                       progress_cb: Optional[Callable[[int, int], None]] = None,
                       done_cb: Optional[Callable[[bool, str], None]] = None,
                       expected_sha256: Optional[str] = None) -> None:
    """เริ่มอัพเดทแบบ patch (background thread)

    progress_cb(downloaded, total) — progress ดาวน์โหลด
    done_cb(success, message) — เรียกเมื่อเสร็จ (success=True → โปรแกรมจะปิดตัวเอง)
    expected_sha256 — hash จาก version.json (ถ้ามี) → ตรวจหลังโหลด
    """
    def _worker():
        # ดาวน์โหลด zip ไว้ใน install_dir (ไม่ใช่ %TEMP% — ลด AV suspicion)
        install_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
        temp_zip = os.path.join(install_dir, ".update_patch.zip")
        ok = download_file(url, temp_zip, progress_cb=progress_cb,
                           expected_sha256=expected_sha256)
        if not ok:
            if done_cb:
                done_cb(False, "ดาวน์โหลดไม่สำเร็จ — ตรวจสอบอินเทอร์เน็ต\n(หรือไฟล์ไม่ผ่านการตรวจสอบความถูกต้อง)")
            return
        # แตก + รีสตาร์ท
        ok = apply_patch(temp_zip)
        if done_cb:
            if ok:
                done_cb(True, "กำลังติดตั้งและรีสตาร์ท...")
            else:
                done_cb(False, "ไม่สามารถติดตั้งอัพเดทได้ (dev mode หรือไม่ใช่ frozen exe)")

    threading.Thread(target=_worker, name="BP-Updater", daemon=True).start()
