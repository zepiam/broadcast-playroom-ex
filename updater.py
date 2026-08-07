"""updater.py — ระบบอัพเดทอัตโนมัติสำหรับ Broadcast Playroom

รองรับ 2 โหมด:
  - patch: ดาวน์โหลด zip เล็ก (exe + .py + .html) → แตกทับ → รีสตาร์ท
  - major: แจ้งผู้ใช้ไปดาวน์โหลดใหม่ทั้งโปรแกรมจาก URL

การตรวจ Lite/Full: อ่านจากชื่อ exe
  - Broadcast Playroom Lite.exe → "lite"
  - BroadcastPlayroom_Full.exe → "full"

version.json (บน GitHub) โครงสร้าง:
{
  "version": "1.1.0",
  "changelog": "แก้บั๊ก emote...",
  "lite": {
    "type": "patch",          ← "patch" หรือ "major"
    "url": "https://github.com/.../patch_lite.zip",
    "size": 20000000
  },
  "full": {
    "type": "major",
    "url": "https://drive.google.com/...",
    "size": 5700000000
  }
}
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
import threading
import urllib.request
from typing import Optional, Callable

# top-level import (ไม่ใช่ lazy) เพื่อให้ PyInstaller bundle ถูกต้อง
try:
    import requests  # noqa: F401
except ImportError:
    requests = None  # fallback ใช้ urllib ถ้าไม่มี

_log = logging.getLogger(__name__)


# ── Constants — ⚠️ เปลี่ยน URL นี้เมื่อสร้าง GitHub repo จริง! ──
VERSION_CHECK_URL = "https://github.com/zepiam/broadcast-playroom/releases/download/latest/version.json"
USER_AGENT = "BroadcastPlayroom-Updater/1.0"


def get_current_version() -> str:
    """อ่านเวอร์ชันปัจจุบันจาก version.json (bundled กับ exe)

    ★ ตรวจหลายที่เพราะ PyInstaller onedir เก็บไฟล์ใน _internal/ แต่บางครั้ง root ด้วย
    """
    from settings import get_base_dir
    # ★ ลำดับการค้นหา: _internal/version.json → root/version.json → base_dir/version.json
    install_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(install_dir, "_internal", "version.json"),   # PyInstaller onedir
        os.path.join(install_dir, "version.json"),                # root (บางครั้ง)
        os.path.join(get_base_dir(), "version.json"),             # base_dir (dev mode)
    ]
    for path in candidates:
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                ver = data.get("version", "0.0.0")
                if ver and ver != "0.0.0":
                    return ver
        except Exception:
            pass
    return "0.0.0"


def get_build_type() -> str:
    """ตรวจ Lite/Full จากชื่อ exe — คืน 'lite' / 'full'

    ★ เดิมมี 'full_ex' แต่ตั้งแต่ v1.9.8 เลิกแยก Full Ex → เหลือแค่ Lite + Full
      (ถ้าเจอชื่อ exe เก่าที่มี full_ex/fullex → ถือว่าเป็น 'full' เพราะใช้ torch 2.7.0 เหมือนกัน)
    """
    try:
        exe_name = os.path.basename(sys.executable).lower()
        # ★ full/full_ex/full-ex/fullex ถือว่าเป็น "full" ทั้งหมด (Full Ex เดิม = Full ใหม่)
        if "full" in exe_name:
            return "full"
        if "lite" in exe_name:
            return "lite"
    except Exception:
        pass
    # fallback: ตรวจจากการมี torch
    try:
        import torch  # noqa: F401
        return "full"
    except ImportError:
        return "lite"


def get_exe_name() -> str:
    """คืนชื่อ exe ปัจจุบัน (เช่น Broadcast Playroom Lite.exe)"""
    return os.path.basename(sys.executable)


def _parse_version(v: str) -> list[int]:
    """แยก "1.2.3" → [1, 2, 3] (รองรับ "v1.2.3", "1.2.3-beta")"""
    cleaned = (v or "").strip().lower().lstrip("v")
    parts = []
    for p in cleaned.split("."):
        # เอาเฉพาะตัวเลขนำหน้า (เช่น "3-beta" → 3)
        num = ""
        for ch in p:
            if ch.isdigit():
                num += ch
            else:
                break
        if num:
            parts.append(int(num))
        else:
            parts.append(0)
    return parts if parts else [0]


def is_version_newer(remote: str, local: str) -> bool:
    """คืน True ถ้า remote เป็นรุ่นใหม่กว่า local"""
    try:
        r = _parse_version(remote)
        l = _parse_version(local)
        length = max(len(r), len(l))
        for i in range(length):
            rv = r[i] if i < len(r) else 0
            lv = l[i] if i < len(l) else 0
            if rv > lv:
                return True
            if rv < lv:
                return False
        return False  # เท่ากัน
    except Exception:
        return False


def fetch_remote_version(timeout: float = 20.0, retries: int = 2) -> Optional[dict]:
    """ดาวน์โหลด version.json จาก GitHub — คืน dict หรือ None ถ้า fail

    4 layer fallback + retry 2 ครั้ง (robust — รองรับเครื่องที่ firewall/proxy/SSL แปลกๆ):
    1. requests (รองรับ redirect + SSL ดีกว่า — ใช้ certifi)
    2. urllib + Windows cert store (load_default_certs — ไม่ต้อง certifi)
    3. urllib + default (certifi ถ้ามี)
    4. urllib + unverified SSL (fallback สุดท้าย — ปิด cert verification)
    """
    import time

    for attempt in range(retries + 1):
        # ── วิธี 1: requests (ดีสุด — จัดการ cert + redirect อัตโนมัติ) ──
        if requests is not None:
            try:
                r = requests.get(VERSION_CHECK_URL, headers={"User-Agent": USER_AGENT},
                                 timeout=timeout, allow_redirects=True)
                if r.status_code == 200 and r.text:
                    return r.json()
                print(f"[updater] requests attempt {attempt+1}: status {r.status_code}", flush=True)
            except Exception as exc:
                print(f"[updater] requests attempt {attempt+1} failed: {type(exc).__name__}: {exc}", flush=True)

        # ── วิธี 2: urllib + Windows cert store (load_default_certs — ไม่ต้อง certifi) ──
        try:
            import ssl
            ctx = ssl.create_default_context()
            ctx.load_default_certs()  # โหลดจาก Windows cert store แทน certifi
            req = urllib.request.Request(
                VERSION_CHECK_URL,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                data = r.read()
                if data:
                    return json.loads(data.decode("utf-8"))
        except Exception as exc:
            print(f"[updater] urllib (win cert) attempt {attempt+1} failed: {type(exc).__name__}: {exc}", flush=True)

        # ── วิธี 3: urllib + default SSL (certifi ถ้ามี) ──
        try:
            req = urllib.request.Request(
                VERSION_CHECK_URL,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
                if data:
                    return json.loads(data.decode("utf-8"))
        except Exception as exc:
            print(f"[updater] urllib (default) attempt {attempt+1} failed: {type(exc).__name__}: {exc}", flush=True)

        # ── วิธี 4: urllib + unverified SSL (fallback สุดท้าย — ปิด cert verification) ──
        try:
            import ssl
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request(
                VERSION_CHECK_URL,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                data = r.read()
                if data:
                    print(f"[updater] fallback to unverified SSL (attempt {attempt+1})", flush=True)
                    return json.loads(data.decode("utf-8"))
        except Exception as exc:
            print(f"[updater] urllib (unverified) attempt {attempt+1} failed: {type(exc).__name__}: {exc}", flush=True)

        if attempt < retries:
            time.sleep(1)  # รอ 1 วินาทีก่อน retry

    _log.warning("fetch_remote_version: all methods failed after %d attempts", retries + 1)
    return None


def check_for_update(build_type: Optional[str] = None) -> Optional[dict]:
    """ตรวจอัพเดท — คืน dict ข้อมูลอัพเดท หรือ None ถ้าไม่มี/ไม่สำเร็จ

    Returns (ถ้ามีอัพเดท):
        {
            "current": "1.0.0",
            "latest": "1.1.0",
            "changelog": "...",
            "type": "patch" | "major",
            "url": "https://...",
            "size": 20000000,
            "build_type": "lite" | "full",
        }
    """
    bt = build_type or get_build_type()
    local_ver = get_current_version()
    remote = fetch_remote_version()
    if not remote:
        return None
    latest_ver = remote.get("version", "")
    if not latest_ver or not is_version_newer(latest_ver, local_ver):
        return None
    # อ่านข้อมูลอัพเดทสำหรับ build type นี้
    bt_info = remote.get(bt, {})
    if not bt_info:
        # ★ fallback: ไม่มี block สำหรับ build type นี้ → major update (ให้ user โหลดใหม่)
        bt_info = {"type": "major", "url": "", "size": 0}
    return {
        "current": local_ver,
        "latest": latest_ver,
        "changelog": remote.get("changelog", ""),
        "type": bt_info.get("type", "major"),
        "url": bt_info.get("url", ""),
        "size": bt_info.get("size", 0),
        "build_type": bt,
    }


def download_file(url: str, dest: str, progress_cb: Optional[Callable[[int, int], None]] = None,
                  timeout: float = 300.0) -> bool:
    """ดาวน์โหลดไฟล์พร้อม progress callback

    progress_cb(downloaded_bytes, total_bytes) — เรียกทุก chunk
    Returns True ถ้าสำเร็จ

    ใช้ 3 layer fallback เหมือน fetch_remote_version:
    1. requests (รองรับ redirect + SSL ดีกว่า)
    2. urllib + Windows cert store
    3. urllib + unverified SSL (fallback สุดท้าย)
    """

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

    # ── วิธี 1: requests (ดีสุด — จัดการ cert + redirect อัตโนมัติ) ──
    if requests is not None:
        try:
            r = requests.get(url, headers={"User-Agent": USER_AGENT},
                             timeout=timeout, allow_redirects=True, stream=True)
            if r.status_code == 200:
                total = int(r.headers.get("Content-Length", 0))
                return _write_stream(
                    r, lambda: total,
                    lambda sz: next(r.iter_content(chunk_size=sz), b"")
                )
            print(f"[updater] download requests status={r.status_code}", flush=True)
        except Exception as exc:
            print(f"[updater] download requests failed: {type(exc).__name__}: {exc}", flush=True)

    # ── วิธี 2: urllib + Windows cert store ──
    try:
        import ssl
        ctx = ssl.create_default_context()
        ctx.load_default_certs()  # โหลดจาก Windows cert store
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return _write_stream(
                r, lambda: int(r.headers.get("Content-Length", 0)),
                lambda sz: r.read(sz)
            )
    except Exception as exc:
        print(f"[updater] download urllib (win cert) failed: {type(exc).__name__}: {exc}", flush=True)

    # ── วิธี 3: urllib + unverified SSL (fallback สุดท้าย) ──
    try:
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            print("[updater] download fallback to unverified SSL", flush=True)
            return _write_stream(
                r, lambda: int(r.headers.get("Content-Length", 0)),
                lambda sz: r.read(sz)
            )
    except Exception as exc:
        print(f"[updater] download urllib (unverified) failed: {type(exc).__name__}: {exc}", flush=True)

    return False


def apply_patch(zip_path: str) -> bool:
    """แตก patch zip ทับไฟล์ปัจจุบัน + รีสตาร์ท

    ใช้ batch script (stage-then-copy pattern):
      1. แตก zip ไป staging folder (ใน install_dir — ไม่ใช่ %TEMP% เพื่อลด AV suspicion)
      2. รอจนกว่า exe ปัจจุบันจะปิด
      3. copy ทับ
      4. รีสตาร์ท exe

    Returns True ถ้าสร้าง bat สำเร็จ (โปรแกรมจะปิดตัวเองหลังจากนี้)
    """
    exe_name = get_exe_name()
    install_dir = os.path.dirname(sys.executable)
    exe_path = os.path.join(install_dir, exe_name)
    # staging + bat อยู่ใน install_dir (AV มอง %TEMP% เป็นพื้นที่อันตราย)
    staging = os.path.join(install_dir, ".update_staging")
    bat_path = os.path.join(install_dir, ".update.bat")
    log_path = os.path.join(install_dir, ".update.log")

    # batch script — stage-then-copy pattern
    # รอ mutex release อย่างแท้จริง (กัน "โปรแกรมเปิดอยู่แล้ว" ตอนรีสตาร์ท)
    bat = f"""@echo off
chcp 65001 >nul 2>&1
>"{log_path}" echo === Broadcast Playroom updater ===
>>"{log_path}" echo staging: {staging}
>>"{log_path}" echo install: {install_dir}
>>"{log_path}" echo exe: {exe_name}

:: Stage 1: แตก zip ไป staging (ใช้ PowerShell Expand-Archive)
if exist "{staging}" rd /s /q "{staging}"
mkdir "{staging}"
powershell -NoProfile -Command "try {{ Expand-Archive -LiteralPath '{zip_path}' -DestinationPath '{staging}' -Force }} catch {{ exit 1 }}"
if errorlevel 1 (
  >>"{log_path}" echo FAIL: cannot extract zip
  exit /b 1
)

:: Stage 2: รอจนกว่า exe จะปิดจาก tasklist
:waitloop
tasklist /fi "imagename eq {exe_name}" 2>nul | find /i "{exe_name}" >nul
if not errorlevel 1 (
  ping 127.0.0.1 -n 2 >nul
  goto waitloop
)

:: Stage 2b: buffer เพิ่ม 3 วินาที เพื่อให้ OS ปล่อย mutex/file handle สมบูรณ์
>>"{log_path}" echo waiting for OS cleanup (3s)...
ping 127.0.0.1 -n 4 >nul

:: Stage 3: copy ทับ (xcopy /y /e = recursive + overwrite)
>>"{log_path}" echo copying files...
xcopy /y /e /i "{staging}\\*" "{install_dir}\\" >nul 2>&1

:: Stage 4: เก็บกวาด + รีสตาร์ท
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
        return True
    except Exception:
        return False


def start_patch_update(url: str, progress_cb: Optional[Callable[[int, int], None]] = None,
                       done_cb: Optional[Callable[[bool, str], None]] = None) -> None:
    """เริ่มอัพเดทแบบ patch (background thread)

    progress_cb(downloaded, total) — progress ดาวน์โหลด
    done_cb(success, message) — เรียกเมื่อเสร็จ (success=True → โปรแกรมจะปิดตัวเอง)
    """
    def _worker():
        # ดาวน์โหลด zip ไว้ใน install_dir (ไม่ใช่ %TEMP% — ลด AV suspicion)
        install_dir = os.path.dirname(sys.executable)
        temp_zip = os.path.join(install_dir, ".update_patch.zip")
        ok = download_file(url, temp_zip, progress_cb=progress_cb)
        if not ok:
            if done_cb:
                done_cb(False, "ดาวน์โหลดไม่สำเร็จ — ตรวจสอบอินเทอร์เน็ต")
            return
        # แตก + รีสตาร์ท
        ok = apply_patch(temp_zip)
        if done_cb:
            if ok:
                done_cb(True, "กำลังติดตั้งและรีสตาร์ท...")
            else:
                done_cb(False, "ไม่สามารถติดตั้งอัพเดทได้")

    threading.Thread(target=_worker, name="BP-Updater", daemon=True).start()


if __name__ == "__main__":
    # smoke test
    print(f"build type: {get_build_type()}")
    print(f"exe: {get_exe_name()}")
    print(f"current version: {get_current_version()}")
    print(f"checking for update...")
    info = check_for_update()
    if info:
        print(f"  update available: {info['current']} → {info['latest']}")
        print(f"  type: {info['type']}")
        print(f"  changelog: {info['changelog']}")
    else:
        print("  no update or check failed")
