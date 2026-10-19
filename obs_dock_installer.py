"""obs_dock_installer.py — จัดการติดตั้ง Custom Browser Dock สำหรับ Broadcast Playroom ลงใน OBS Studio

ระบบนี้จะตรวจหาไฟล์ user.ini ของ OBS Studio ในเครื่อง:
  %APPDATA%\\obs-studio\\user.ini
และเพิ่มรายการ Custom Browser Dock ให้อัตโนมัติในคลิกเดียว (1-Click Install)
"""
import os
import re
import json
import uuid
import shutil
import logging
from typing import Optional, Tuple

logger = logging.getLogger("obs_dock_installer")

DOCK_TITLE_DEFAULT = "Broadcast Playroom"
DOCK_UUID_DEFAULT = "broadcast-playroom-quick-dock"
DOCK_DEFAULT_PORT = 8801


def get_dock_port() -> int:
    """ดึงพอร์ตของ Composer Server ที่แท้จริงจาก settings"""
    try:
        from settings import load_settings
        st = load_settings()
        return int(getattr(st, "composer_port", 8801))
    except Exception:
        return 8801


def get_dock_url() -> str:
    """ดึง URL สำหรับ OBS Dock ที่ถูกต้อง"""
    port = get_dock_port()
    return f"http://localhost:{port}/dock"


def get_obs_user_ini_path() -> Optional[str]:
    """หาที่อยู่ของไฟล์ user.ini ของ OBS Studio"""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    ini_path = os.path.join(appdata, "obs-studio", "user.ini")
    return ini_path


def is_obs_installed() -> bool:
    """ตรวจสอบว่ามีการติดตั้งหรือเคยเปิดใช้งาน OBS Studio ในเครื่องหรือไม่"""
    ini_path = get_obs_user_ini_path()
    if ini_path and os.path.exists(ini_path):
        return True
    # เช็คโฟลเดอร์หลัก obs-studio ใน AppData
    appdata = os.environ.get("APPDATA")
    if appdata and os.path.isdir(os.path.join(appdata, "obs-studio")):
        return True
    return False


def is_dock_installed(dock_url: str = f"http://localhost:{DOCK_DEFAULT_PORT}/dock") -> bool:
    """ตรวจสอบว่า Dock ของ Broadcast Playroom ถูกติดตั้งใน user.ini หรือยัง"""
    ini_path = get_obs_user_ini_path()
    if not ini_path or not os.path.exists(ini_path):
        return False

    try:
        with open(ini_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        m = re.search(r"^ExtraBrowserDocks=(.*)$", content, re.MULTILINE)
        if not m:
            return False

        docks_json = m.group(1).strip()
        docks = json.loads(docks_json)
        norm_target = dock_url.rstrip("/").lower()
        for d in docks:
            u = str(d.get("url", "")).rstrip("/").lower()
            if u == norm_target or d.get("uuid") == DOCK_UUID_DEFAULT or "broadcast playroom" in str(d.get("title", "")).lower():
                return True
        return False
    except Exception as e:
        logger.debug(f"is_dock_installed error: {e}")
        return False


def install_obs_dock(title: str = DOCK_TITLE_DEFAULT,
                     dock_url: str = f"http://localhost:{DOCK_DEFAULT_PORT}/dock") -> Tuple[bool, str, bool]:
    """ติดตั้ง Broadcast Playroom Quick Control Dock ลงใน OBS Studio

    Returns:
        (success: bool, message: str, obs_was_running: bool)
    """
    ini_path = get_obs_user_ini_path()
    if not ini_path:
        return False, "ไม่พบโฟลเดอร์ AppData ของระบบ", False

    obs_dir = os.path.dirname(ini_path)
    if not os.path.exists(obs_dir):
        try:
            os.makedirs(obs_dir, exist_ok=True)
        except Exception as e:
            return False, f"สร้างโฟลเดอร์ OBS Studio ไม่สำเร็จ: {e}", False

    # ตรวจสอบว่า OBS รันอยู่หรือไม่
    obs_was_running = False
    try:
        from obs_launcher import _get_obs_pids
        pids = _get_obs_pids()
        if pids:
            obs_was_running = True
    except Exception:
        pass

    try:
        content = ""
        if os.path.exists(ini_path):
            with open(ini_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            # ทำ Backup สำรองไฟล์ไว้เสมอ
            try:
                shutil.copy2(ini_path, ini_path + ".bak")
            except Exception:
                pass

        # เตรียม Entry สำหรับ Dock
        dock_entry = {
            "title": title,
            "url": dock_url,
            "uuid": DOCK_UUID_DEFAULT
        }

        m = re.search(r"^ExtraBrowserDocks=(.*)$", content, re.MULTILINE)
        if m:
            raw_docks = m.group(1).strip()
            try:
                docks = json.loads(raw_docks)
                if not isinstance(docks, list):
                    docks = []
            except Exception:
                docks = []

            # อัปเดตรายการเดิมถ้ามี หรือเพิ่มใหม่ถ้ายังไม่มี
            found = False
            norm_target = dock_url.rstrip("/").lower()
            for d in docks:
                u = str(d.get("url", "")).rstrip("/").lower()
                if u == norm_target or d.get("uuid") == DOCK_UUID_DEFAULT or "broadcast playroom" in str(d.get("title", "")).lower():
                    d["title"] = title
                    d["url"] = dock_url
                    d["uuid"] = DOCK_UUID_DEFAULT
                    found = True
                    break

            if not found:
                docks.append(dock_entry)

            new_docks_json = json.dumps(docks, ensure_ascii=False)
            new_content = content[:m.start(1)] + new_docks_json + content[m.end(1):]
        else:
            # ยังไม่มีคีย์ ExtraBrowserDocks
            new_docks_json = json.dumps([dock_entry], ensure_ascii=False)
            if "[BasicWindow]" in content:
                # แทรกใต้ [BasicWindow]
                new_content = content.replace("[BasicWindow]\n", f"[BasicWindow]\nExtraBrowserDocks={new_docks_json}\n", 1)
                if new_content == content:  # กรณี CRLF \r\n
                    new_content = content.replace("[BasicWindow]\r\n", f"[BasicWindow]\r\nExtraBrowserDocks={new_docks_json}\r\n", 1)
            else:
                # สร้าง section [BasicWindow]
                if content and not content.endswith("\n"):
                    content += "\n"
                new_content = content + f"\n[BasicWindow]\nExtraBrowserDocks={new_docks_json}\n"

        # บันทึกไฟล์ user.ini
        with open(ini_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        if obs_was_running:
            msg = (
                "ติดตั้ง Dock ลงใน OBS สำเร็จแล้วครับ!\n\n"
                "⚠️ ตรวจพบว่า OBS กำลังเปิดทำงานอยู่:\n"
                "กรุณา 'ปิดแล้วเปิด OBS ใหม่อีก 1 ครั้ง' เพื่อให้ OBS โหลดแถบ 'Broadcast Playroom' ขึ้นมาในเมนู Docks ครับ"
            )
        else:
            msg = (
                "ติดตั้ง Dock ลงใน OBS สำเร็จเรียบร้อยแล้วครับ!\n\n"
                "เมื่อเปิด OBS Studio ขึ้นมา จะพบแถบ 'Broadcast Playroom' ในเมนู Docks ที่แถบด้านบนของ OBS ทันทีครับ"
            )

        return True, msg, obs_was_running

    except Exception as e:
        logger.error(f"install_obs_dock error: {e}", exc_info=True)
        return False, f"เกิดข้อผิดพลาดในการเขียนไฟล์ OBS config: {e}", obs_was_running
