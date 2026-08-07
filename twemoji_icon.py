"""twemoji_icon.py — render emoji เป็น CTkImage สีสัน (Twemoji ของ Twitter)

แก้ปัญหา: Tk 8.6 บน Windows แสดง emoji เป็นเส้น monochrome (ไม่มีสี)
→ ใช้ Twemoji PNG (สีสันสวย) แทน

Flow:
  1. emoji_to_ctkimage("🎮", size=24) → โหลด PNG จาก CDN → CTkImage
  2. cache ใน memory (emoji + size → CTkImage)
  3. cache ใน disk (~/.tts-for-livestream/twemoji_cache/) กันโหลดซ้ำ

CDN: jdecked/twemoji (fork ที่ active ต่อจาก Twitter อย่างเป็นทางการ)
  PNG: https://cdn.jsdelivr.net/gh/jdecked/twemoji@latest/assets/72x72/{codepoint}.png

Usage:
  from twemoji_icon import emoji_to_ctkimage
  img = emoji_to_ctkimage("🎮", size=20)  # CTkImage หรือ None ถ้าโหลด fail
"""
from __future__ import annotations

import os
import threading
import urllib.request
from io import BytesIO
from typing import Optional

CACHE_DIR = os.path.join(
    os.path.expanduser("~"), ".tts-for-livestream", "twemoji_cache"
)
CDN_BASE = "https://cdn.jsdelivr.net/gh/jdecked/twemoji@latest/assets/72x72"

# memory cache: (emoji, size_px) → CTkImage
_mem_cache: dict[tuple, object] = {}
_mem_lock = threading.Lock()
# ระบุว่ากำลังโหลดอยู่ (กันโหลดซ้ำ)
_loading: set[tuple] = set()
_disk_cache_ready = False


def _ensure_disk_cache() -> None:
    """สร้างโฟลเดอร์ cache (ครั้งแรกเท่านั้น)"""
    global _disk_cache_ready
    if not _disk_cache_ready:
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            _disk_cache_ready = True
        except Exception:
            pass


def _emoji_to_codepoint(emoji: str) -> str:
    """แปลง emoji → codepoint string สำหรับ URL (เช่น 🎮 → 1f3ae)

    รองรับ emoji ที่เป็นหลาย codepoint (เช่น 👨‍👩‍👧 = man+zwj+woman+zwj+girl)
    → คั่นด้วย - (เช่น 1f468-200d-1f469-200d-1f467)
    """
    # แยก codepoint แต่ละตัว (skip variation selectors ที่ไม่จำเป็น)
    cps = []
    for ch in emoji:
        cp = ord(ch)
        # ข้าม variation selectors (fe0f, fe0e) — Twemoji URL ใช้แบบไม่มี
        if cp in (0xFE0F, 0xFE0E):
            continue
        cps.append(f"{cp:x}")
    return "-".join(cps)


def _load_png(codepoint: str) -> Optional[bytes]:
    """โหลด PNG จาก disk cache หรือ CDN — คืน bytes หรือ None"""
    _ensure_disk_cache()
    disk_path = os.path.join(CACHE_DIR, f"{codepoint}.png")
    # 1. disk cache
    try:
        if os.path.exists(disk_path) and os.path.getsize(disk_path) > 0:
            with open(disk_path, "rb") as f:
                return f.read()
    except Exception:
        pass
    # 2. CDN
    url = f"{CDN_BASE}/{codepoint}.png"
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "TTS-for-Livestream/1.0"}
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            data = r.read()
        if not data or len(data) < 50:
            return None
        # save disk cache
        try:
            with open(disk_path, "wb") as f:
                f.write(data)
        except Exception:
            pass
        return data
    except Exception:
        return None


def _bytes_to_ctkimage(data: bytes, size_px: int):
    """แปลง PNG bytes → CTkImage ขนาด size_px"""
    try:
        from PIL import Image
        import customtkinter as ctk

        img = Image.open(BytesIO(data))
        img = img.convert("RGBA").resize(
            (size_px, size_px),
            Image.LANCZOS if hasattr(Image, "LANCZOS") else Image.Resampling.LANCZOS,
        )
        return ctk.CTkImage(light_image=img, dark_image=img, size=(size_px, size_px))
    except Exception:
        return None


def emoji_to_ctkimage(emoji: str, size: int = 20, sync: bool = True):
    """แปลง emoji → CTkImage สี (Twemoji)

    Args:
        emoji: ตัวอักษร emoji (เช่น "🎮", "⚙", "💬")
        size: ขนาด px (square)
        sync: True = โหลดพร้อมกัน (blocking), False = คืน None ทันทีถ้ายังไม่มี cache
              (สำหรับ UI thread — sync=True ปลอดภัยเพราะ cache hit เร็ว)

    Returns: CTkImage หรือ None (ถ้าโหลด fail หรือ async ยังไม่พร้อม)
    """
    if not emoji:
        return None
    key = (emoji, size)
    # 1. memory cache
    with _mem_lock:
        cached = _mem_cache.get(key)
        if cached is not None:
            return cached
        if not sync:
            # async mode — ถ้ายังไม่มี cache ให้ trigger โหลด background + คืน None
            if key not in _loading:
                _loading.add(key)
                t = threading.Thread(
                    target=_async_load, args=(emoji, size), daemon=True
                )
                t.start()
            return None
    # 2. sync โหลด (blocking)
    codepoint = _emoji_to_codepoint(emoji)
    data = _load_png(codepoint)
    if data is None:
        return None
    img = _bytes_to_ctkimage(data, size)
    if img is not None:
        with _mem_lock:
            _mem_cache[key] = img
    return img


def _async_load(emoji: str, size: int) -> None:
    """โหลด emoji ใน background thread — เก็บใน memory cache"""
    try:
        codepoint = _emoji_to_codepoint(emoji)
        data = _load_png(codepoint)
        if data is not None:
            img = _bytes_to_ctkimage(data, size)
            if img is not None:
                with _mem_lock:
                    _mem_cache[(emoji, size)] = img
    except Exception:
        pass
    finally:
        with _mem_lock:
            _loading.discard((emoji, size))


def has_cached(emoji: str, size: int) -> bool:
    """เช็คว่า emoji มีใน memory cache แล้วหรือยัง"""
    with _mem_lock:
        return (emoji, size) in _mem_cache


if __name__ == "__main__":
    # smoke test — โหลด 5 emoji และบันทึกไฟล์ตรวจสอบ
    import sys
    test_emojis = ["⚙", "💬", "🎮", "🎨", "👤"]
    print("Loading Twemoji icons...")
    for e in test_emojis:
        img = emoji_to_ctkimage(e, size=48)
        cp = _emoji_to_codepoint(e)
        status = "OK" if img is not None else "FAIL"
        print(f"  {e} (cp={cp}): {status}")
    print(f"\nCache dir: {CACHE_DIR}")
    print(f"Files: {os.listdir(CACHE_DIR) if os.path.exists(CACHE_DIR) else 'none'}")
