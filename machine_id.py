"""machine_id.py — สร้าง machine fingerprint สำหรับระบบแบนผู้สนับสนุนเท็จ

★ ใช้ข้อมูลฮาร์ดแวร์ผสมกัน → hash SHA256 → เก็บใน data/machine_id.json
★ ครั้งแรก generate + cache, ครั้งต่อไปอ่านจาก cache (เร็ว + stable)
★ ฝั่ง server เก็บ machine_id นี้ → admin กดแบน → submit.php แบนเครื่องนั้น

หมายเหตุ: fingerprint ไม่สมบูรณ์ 100% (ผู้ใช้ที่มีความรู้สามารถปลอมได้)
แต่เพียงพอสำหรับกันผู้ใช้ทั่วไปที่ส่งข้อมูลเท็จเล่น
"""
from __future__ import annotations

import hashlib
import logging
import os
import platform
import uuid

logger = logging.getLogger(__name__)

_cache: str | None = None


def _collect_hardware_info() -> str:
    """รวบรวมข้อมูลฮาร์ดแวร์ + OS → string สำหรับ hash

    ★ ใช้ข้อมูลที่ stable (ไม่เปลี่ยนง่าย) แต่ไม่ระบุตัวตนเกินไป
    """
    parts = []

    # MAC address (จาก uuid.getnode — คืน MAC หรือ random ถ้าไม่พบ)
    try:
        mac = uuid.getnode()
        parts.append(f"mac:{mac:012x}")
    except Exception:
        parts.append("mac:0")

    # OS info
    try:
        parts.append(f"os:{platform.system()}")
        parts.append(f"os_ver:{platform.version()}")
        parts.append(f"os_rel:{platform.release()}")
    except Exception:
        pass

    # Machine name
    try:
        parts.append(f"node:{platform.node()}")
    except Exception:
        pass

    # Machine type
    try:
        parts.append(f"mach:{platform.machine()}")
    except Exception:
        pass

    # Processor
    try:
        parts.append(f"proc:{platform.processor()}")
    except Exception:
        pass

    # Volume serial (Windows) — stable identifier
    if platform.system() == "Windows":
        try:
            import subprocess
            result = subprocess.run(
                ["vol", "C:"], capture_output=True, text=True, timeout=3,
                shell=True,
            )
            # output: " Volume in drive C is XXX\n Volume Serial Number is XXXX-XXXX"
            output = (result.stdout or "") + (result.stderr or "")
            # ดึง serial number
            import re
            match = re.search(r"([0-9A-Fa-f]{4}-[0-9A-Fa-f]{4})", output)
            if match:
                parts.append(f"vol:{match.group(1)}")
        except Exception:
            pass

    return "|".join(parts)


def generate_machine_id() -> str:
    """สร้าง machine ID (SHA256 hash ของข้อมูลฮาร์ดแวร์)

    Returns: 64-char hex string
    """
    raw = _collect_hardware_info()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_machine_id() -> str:
    """คืน machine ID (cache ใน memory + file)

    ★ ครั้งแรก → generate + เก็บใน data/machine_id.json
    ★ ครั้งต่อไป → อ่านจาก cache (stable ข้าม restart)
    """
    global _cache
    if _cache:
        return _cache

    # ★ หา data dir (เหมือน data_dir.py)
    try:
        from data_dir import get_data_dir
        data_dir = get_data_dir()
    except Exception:
        data_dir = os.path.join(os.path.expanduser("~"), ".tts-for-livestream")

    cache_file = os.path.join(data_dir, "machine_id.json")

    # ★ อ่านจาก cache ก่อน
    try:
        if os.path.exists(cache_file):
            import json
            with open(cache_file, encoding="utf-8") as f:
                data = json.load(f)
            cached = data.get("machine_id", "")
            if cached and len(cached) == 64:
                _cache = cached
                logger.debug("Machine ID loaded from cache")
                return _cache
    except Exception as e:
        logger.debug(f"Cannot read machine_id cache: {e}")

    # ★ generate ใหม่
    _cache = generate_machine_id()
    logger.info(f"Generated new machine ID: {_cache[:16]}...")

    # ★ เก็บ cache
    try:
        os.makedirs(data_dir, exist_ok=True)
        import json
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump({"machine_id": _cache}, f)
    except Exception as e:
        logger.debug(f"Cannot save machine_id cache: {e}")

    return _cache


if __name__ == "__main__":
    # test
    mid = get_machine_id()
    print(f"Machine ID: {mid}")
    print(f"Length: {len(mid)}")
    print(f"First 16: {mid[:16]}")
