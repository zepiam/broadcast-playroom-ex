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
import sys
import ssl
import time
import urllib.request
import webbrowser
from typing import Optional

logger = logging.getLogger("updater")

# ★ URL สำหรับดาวน์โหลด version.json (จาก GitHub Releases)
VERSION_CHECK_URL = "https://github.com/zepiam/broadcast-playroom-ex/releases/download/latest/version.json"
USER_AGENT = "BroadcastPlayroom-v2-Updater/2.0"


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
    """ดาวน์โหลด version.json จาก release URL — ลองหลายวิธี (เหมือน v1)"""
    for attempt in range(retries + 1):
        # วิธี 1: urllib + Windows cert
        try:
            ctx = ssl.create_default_context()
            ctx.load_default_certs()
            req = urllib.request.Request(VERSION_CHECK_URL, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                data = r.read()
                if data:
                    return json.loads(data.decode("utf-8"))
        except Exception:
            pass

        # วิธี 2: urllib default
        try:
            req = urllib.request.Request(VERSION_CHECK_URL, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
                if data:
                    return json.loads(data.decode("utf-8"))
        except Exception:
            pass

        # วิธี 3: urllib unverified SSL (fallback)
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request(VERSION_CHECK_URL, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                data = r.read()
                if data:
                    return json.loads(data.decode("utf-8"))
        except Exception:
            pass

        if attempt < retries:
            time.sleep(1)

    return None


def check_for_update(build_type: Optional[str] = None) -> Optional[dict]:
    """ตรวจอัพเดท — คืน dict ข้อมูลอัพเดท หรือ None ถ้าไม่มี/ไม่สำเร็จ

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
        return None
    latest_ver = remote.get("version", "")
    if not latest_ver or not is_version_newer(latest_ver, local_ver):
        return None
    bt_info = remote.get(bt, {})
    if not bt_info:
        bt_info = {"type": "major", "url": ""}
    return {
        "current": local_ver,
        "latest": latest_ver,
        "changelog": remote.get("changelog", ""),
        "type": bt_info.get("type", "major"),
        "url": bt_info.get("url", ""),
        "build_type": bt,
    }


def check_update_async(callback, build_type: Optional[str] = None):
    """เช็คอัพเดทใน background thread"""
    import threading
    def _bg():
        try:
            info = check_for_update(build_type)
        except Exception as e:
            logger.debug(f"check_update_async: {e}")
            info = None
        callback(info)
    threading.Thread(target=_bg, name="UpdateChecker", daemon=True).start()


def open_url(url: str):
    """เปิด URL ใน browser"""
    try:
        webbrowser.open(url)
    except Exception:
        pass
