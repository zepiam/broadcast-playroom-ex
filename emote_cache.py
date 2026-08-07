"""emote_cache.py — ดาวน์โหลด + cache Twitch emote image

โหลด emote จาก Twitch CDN (ไม่ต้อง OAuth) + cache ลง memory + disk
เพื่อ render เป็นภาพ inline ใน chat row

URL format:
  https://static-cdn.jtvnw.net/emoticons/v2/{emote_id}/default/{theme}/{scale}
  - theme: "dark" (default) หรือ "light"
  - scale: 1.0 (28px), 2.0 (56px), 3.0 (112px) — เราใช้ 1.0

การใช้งาน:
    cache = EmoteCache()
    # ใน UI thread — เช็ค memory ก่อน (non-blocking)
    img = cache.get_sync(emote_id)
    if img is not None:
        label.configure(image=img, text="")
    else:
        # โหลดใน background → ส่ง CTkImage กลับผ่าน callback
        cache.fetch_async(emote_id, on_ready)
"""
from __future__ import annotations

import os
import threading
import time
import urllib.request
from io import BytesIO
from typing import Callable, Optional

# CTkImage import lazy เพื่อกัน circular import ถ้า module นี้ถูก import ก่อน customtkinter init
_CTK = None


def _get_ctk():
    global _CTK
    if _CTK is None:
        import customtkinter as ctk
        _CTK = ctk
    return _CTK


CACHE_DIR = os.path.join(
    os.path.expanduser("~"), ".tts-for-livestream", "emote_cache"
)
EMOTE_CDN = "https://static-cdn.jtvnw.net/emoticons/v2/{id}/default/{theme}/1.0"


class EmoteCache:
    """cache emote image — memory + disk + async download"""

    def __init__(self, theme: str = "dark", size_px: int = 22) -> None:
        self.theme = theme
        self.size_px = size_px
        self._mem: dict[int, object] = {}  # emote_id → CTkImage (Twitch)
        # emote ที่โหลด fail: id → timestamp (TTL 60s — หมดแล้ว retry ได้)
        # เดิมเป็น set ถาวร → 1 timeout พังทั้ง session; เปลี่ยนเป็น TTL แก้ปัญหาช่องเปล่า
        self._failed: dict[int, float] = {}
        self._failed_ttl: float = 60.0
        self._lock = threading.Lock()
        # URL-based cache (MyLive emote/sticker) — key = (url, size_px)
        self._mem_url: dict[tuple, object] = {}
        self._failed_url: dict[tuple, float] = {}
        os.makedirs(CACHE_DIR, exist_ok=True)

    def _path(self, emote_id: int) -> str:
        """default cache path (static png)"""
        return os.path.join(CACHE_DIR, f"{emote_id}_1.0.png")

    def _path_ext(self, emote_id: int, ext: str) -> str:
        """cache path ตาม extension"""
        return os.path.join(CACHE_DIR, f"{emote_id}_1.0{ext}")

    def _find_cached_path(self, emote_id: int) -> Optional[str]:
        """หาไฟล์ cache ที่มีอยู่ (ลองหลาย extension)"""
        for ext in [".gif", ".png"]:
            p = self._path_ext(emote_id, ext)
            if os.path.exists(p) and os.path.getsize(p) > 0:
                return p
        return None

    # ------------------------------------------------------------------ #
    # Sync API (UI thread)
    # ------------------------------------------------------------------ #
    def get_sync(self, emote_id: int, size_px: Optional[int] = None) -> Optional[object]:
        """เรียกใน UI thread — คืน CTkImage ถ้ามีใน memory cache, None ถ้ายังไม่มี

        size_px=None → ใช้ขนาด default ของ cache (self.size_px)
        key รวม size → emote เดียวที่โหลดหลายขนาด (ตาม font scale) จะแยกกัน
        """
        size = size_px if size_px is not None else self.size_px
        with self._lock:
            return self._mem.get((emote_id, size))

    def is_failed(self, emote_id: int, size_px: Optional[int] = None) -> bool:
        """emote นี้โหลด fail และยังอยู่ใน TTL → ไม่ต้องลองในรอบนี้ (หมด TTL แล้ว retry ได้)

        NOTE: failed ใช้ key เป็น emote_id เดียว (ไม่รวม size) — เพราะถ้า download fail
        ที่ขนาดหนึ่ง ก็ fail ทุกขนาด (URL เดียวกัน)
        """
        with self._lock:
            ts = self._failed.get(emote_id)
            if ts is None:
                return False
            if time.time() - ts > self._failed_ttl:
                # หมด TTL → ลบออก ให้ retry ได้
                del self._failed[emote_id]
                return False
            return True

    # ------------------------------------------------------------------ #
    # URL-based API (MyLive emote/sticker — key เป็น URL รูปตรงๆ)
    # ------------------------------------------------------------------ #
    def get_url_sync(self, url: str, size_px: Optional[int] = None) -> Optional[object]:
        """เรียกใน UI thread — คืน CTkImage ถ้ามีใน memory cache, None ถ้ายังไม่มี

        size_px=None → ใช้ขนาด default ของ cache (self.size_px)
        key รวม size → URL เดียวที่โหลด 2 ขนาด (emote 26px + sticker 64px) จะแชร์กันได้
        """
        size = size_px if size_px is not None else self.size_px
        with self._lock:
            return self._mem_url.get((url, size))

    def is_failed_url(self, url: str, size_px: Optional[int] = None) -> bool:
        size = size_px if size_px is not None else self.size_px
        with self._lock:
            ts = self._failed_url.get((url, size))
            if ts is None:
                return False
            if time.time() - ts > self._failed_ttl:
                del self._failed_url[(url, size)]
                return False
            return True

    def fetch_url_async(
        self,
        url: str,
        on_ready: Callable[[str, object], None],
        size_px: Optional[int] = None,
    ) -> None:
        """โหลดรูปจาก URL ใน background thread

        on_ready(url, ctk_image) จะถูกเรียกเมื่อโหลดเสร็จ
        *** on_ready ทำงานใน background thread → caller ต้อง wrap ด้วย
            widget.after(0, ...) เองเพื่อ thread-safety ***
        รองรับ .gif → โหลดเฟรมแรก (static) — standard สำหรับ chat emote
        """
        size = size_px if size_px is not None else self.size_px
        if self.is_failed_url(url, size):
            return
        t = threading.Thread(
            target=self._fetch_url_worker,
            args=(url, size, on_ready),
            name=f"emote-url-{hash(url) & 0xffff:x}",
            daemon=True,
        )
        t.start()

    def _fetch_url_worker(
        self,
        url: str,
        size_px: int,
        on_ready: Callable[[str, object], None],
    ) -> None:
        """ทำงานใน background thread — ดาวน์โหลด/อ่าน disk + wrap CTkImage"""
        key = (url, size_px)
        try:
            pil = self._load_url_image(url, size_px)
        except Exception:
            with self._lock:
                self._failed_url[key] = time.time()
            return

        if pil is None:
            with self._lock:
                self._failed_url[key] = time.time()
            return

        try:
            pil = pil.convert("RGBA").resize(
                (size_px, size_px), _get_lanczos(),
            )
        except Exception:
            with self._lock:
                self._failed_url[key] = time.time()
            return

        try:
            ctk = _get_ctk()
            ctk_img = ctk.CTkImage(
                light_image=pil, dark_image=pil, size=(size_px, size_px),
            )
        except Exception:
            with self._lock:
                self._failed_url[key] = time.time()
            return

        with self._lock:
            self._mem_url[key] = ctk_img
        try:
            on_ready(url, ctk_img)
        except Exception:
            pass  # callback fail ไม่ fatal

    def _url_disk_path(self, url: str, size_px: int) -> str:
        """disk path สำหรับ URL-based cache — key ด้วย md5(url) เพราะ URL ยาว/มีอักขระพิเศษ"""
        import hashlib
        h = hashlib.md5(url.encode("utf-8")).hexdigest()[:16]
        return os.path.join(CACHE_DIR, f"url_{h}_{size_px}.png")

    def _load_url_image(self, url: str, size_px: int):
        """คืน PIL.Image — อ่านจาก disk cache ก่อน, ไม่มีค่อยดาวน์โหลด"""
        from PIL import Image

        path = self._url_disk_path(url, size_px)
        # 1) disk cache
        if os.path.exists(path):
            try:
                return Image.open(path)
            except Exception:
                pass  # ไฟล์เสีย → ดาวน์โหลดใหม่

        # 2) download จาก URL
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "TTS-for-Livestream/1.0"},
            )
            with urllib.request.urlopen(req, timeout=8) as r:
                data = r.read()
        except Exception:
            return None

        # โหลดเป็น PIL (รองรับ .gif → โหลดเฟรมแรก)
        try:
            img = Image.open(BytesIO(data))
            if getattr(img, "is_animated", False):
                img.seek(0)  # เฟรมแรก
            img.load()  # force load ก่อนปิด BytesIO
        except Exception:
            return None

        # save disk cache (convert เป็น PNG static — ทิ้ง animation เพื่อประหยัด)
        try:
            img.convert("RGBA").save(path)
        except Exception:
            pass
        return img

    # ------------------------------------------------------------------ #
    # Async download (Twitch ID-based — original path, ไม่แตะ)
    # ------------------------------------------------------------------ #
    def fetch_async(
        self,
        emote_id: int,
        on_ready: Callable[[int, object], None],
        size_px: Optional[int] = None,
    ) -> None:
        """โหลด emote ใน background thread

        on_ready(emote_id, ctk_image) จะถูกเรียกเมื่อโหลดเสร็จ
        *** on_ready ทำงานใน background thread → caller ต้อง wrap ด้วย
            widget.after(0, ...) เองเพื่อ thread-safety ***

        size_px=None → ใช้ขนาด default ของ cache (self.size_px)
        แต่ละขนาดจะ cache แยกกัน (key = (emote_id, size))
        """
        # ถ้าเคย fail → ไม่ลองอีก (failed ใช้ key emote_id เดียว — fail ทุกขนาด)
        if self.is_failed(emote_id):
            return

        size = size_px if size_px is not None else self.size_px
        t = threading.Thread(
            target=self._fetch_worker,
            args=(emote_id, on_ready, size),
            name=f"emote-{emote_id}-{size}",
            daemon=True,
        )
        t.start()

    def _fetch_worker(
        self,
        emote_id: int,
        on_ready: Callable[[int, object], None],
        size_px: int,
    ) -> None:
        """ทำงานใน background thread — ดาวน์โหลด/อ่าน disk + wrap CTkImage

        size_px: ขนาดที่จะ resize (cache key รวม size)
        """
        try:
            pil = self._load_image(emote_id)
        except Exception:
            # mark as failed กัน retry loop
            with self._lock:
                self._failed[emote_id] = time.time()
            return

        if pil is None:
            with self._lock:
                self._failed[emote_id] = time.time()
            return

        try:
            # resize + convert RGBA (ตาม size_px ที่ส่งมา)
            pil = pil.convert("RGBA").resize(
                (size_px, size_px),
                # Image.Resampling.LANCZOS (Pillow 9.1+) หรือ Image.LANCZOS (เก่า)
                _get_lanczos(),
            )
        except Exception:
            with self._lock:
                self._failed[emote_id] = time.time()
            return

        try:
            ctk = _get_ctk()
            ctk_img = ctk.CTkImage(
                light_image=pil,
                dark_image=pil,
                size=(size_px, size_px),
            )
        except Exception:
            with self._lock:
                self._failed[emote_id] = time.time()
            return

        # เก็บ memory cache + เรียก callback (key รวม size)
        with self._lock:
            self._mem[(emote_id, size_px)] = ctk_img
        try:
            on_ready(emote_id, ctk_img)
        except Exception:
            pass  # callback fail ไม่ fatal

    def _load_image(self, emote_id: int):
        """คืน PIL.Image — อ่านจาก disk cache ก่อน, ไม่มีค่อยดาวน์โหลด

        ลองหลาย URL formats (animated ก่อน เพื่อรักษา animation):
          - v2 animated (emote ขยับได้ — APNG/GIF)
          - v2 default (static emotes ทั่วไป + sub emotes)
          - v2 static
          - v1 legacy (emote เก่าบางตัว)
        """
        from PIL import Image

        # 1) disk cache — หาไฟล์ที่มีอยู่ (gif หรือ png)
        cached = self._find_cached_path(emote_id)
        if cached:
            try:
                return Image.open(cached)
            except Exception:
                pass

        # 2) download — ลองหลาย URL และ theme (animated + default + static + v1 + light theme)
        other_theme = "light" if self.theme == "dark" else "dark"
        urls = [
            f"https://static-cdn.jtvnw.net/emoticons/v2/{emote_id}/animated/{self.theme}/1.0",
            f"https://static-cdn.jtvnw.net/emoticons/v2/{emote_id}/animated/{other_theme}/1.0",
            f"https://static-cdn.jtvnw.net/emoticons/v2/{emote_id}/default/{self.theme}/1.0",
            f"https://static-cdn.jtvnw.net/emoticons/v2/{emote_id}/default/{other_theme}/1.0",
            f"https://static-cdn.jtvnw.net/emoticons/v2/{emote_id}/static/{self.theme}/1.0",
            f"https://static-cdn.jtvnw.net/emoticons/v1/{emote_id}/1.0",
            # ลอง scale ใหญ่ขึ้น (2.0) บาง emote มีแค่ขนาด 2.0 หรือ 3.0
            f"https://static-cdn.jtvnw.net/emoticons/v2/{emote_id}/default/{self.theme}/2.0",
            f"https://static-cdn.jtvnw.net/emoticons/v2/{emote_id}/default/{self.theme}/3.0",
        ]
        data = None
        resp_ct = ""
        for url in urls:
            try:
                req = urllib.request.Request(
                    url, headers={"User-Agent": "TTS-for-Livestream/1.0"}
                )
                with urllib.request.urlopen(req, timeout=10) as r:
                    data = r.read()
                    resp_ct = r.headers.get("Content-Type", "")
                if data:
                    break
            except Exception:
                continue

        if not data:
            return None

        # กำหนด extension ตาม content-type (รองรับ webp สำหรับ 7TV)
        if "gif" in resp_ct:
            ext = ".gif"
        elif "webp" in resp_ct:
            ext = ".webp"
        else:
            ext = ".png"

        # save disk cache + handle animated
        cache_path = self._path_ext(emote_id, ext)
        try:
            from PIL import Image as _Image

            img = _Image.open(BytesIO(data))
            # ถ้าเป็น animated → เก็บเฟรมแรก (CTkImage เป็น static เท่านั้น)
            if getattr(img, "is_animated", False):
                img.seek(0)
                img = img.convert("RGBA")
            img.save(cache_path)  # cache disk
            return img
        except Exception:
            try:
                from PIL import Image as _Image

                return _Image.open(BytesIO(data))
            except Exception:
                return None


def _get_lanczos():
    """คืน resampling filter ที่รองรับทั้ง Pillow เก่าและใหม่"""
    from PIL import Image

    # Pillow 9.1+ → Image.Resampling.LANCZOS
    # Pillow เก่า → Image.LANCZOS
    try:
        return Image.Resampling.LANCZOS
    except AttributeError:
        return Image.LANCZOS


# ---------------------------------------------------------------------- #
# Smoke test — ดาวน์โหลด Kappa (emote id 25) จริง
# ---------------------------------------------------------------------- #
if __name__ == "__main__":
    import time

    cache = EmoteCache(theme="dark", size_px=22)

    # ทดสอบ get_sync — ยังไม่มี → None
    assert cache.get_sync(25) is None
    print("✅ get_sync(25) → None (ยังไม่มีใน cache)")

    # fetch_async Kappa (id=25)
    result: dict = {}
    done = threading.Event()

    def on_ready(eid, img):
        result["id"] = eid
        result["img"] = img
        done.set()

    print("⏳ ดาวน์โหลด Kappa (id=25)...")
    cache.fetch_async(25, on_ready)

    if done.wait(timeout=10):
        print(f"✅ โหลดเสร็จ — emote_id={result['id']}, img={result['img']}")
        # โหลดซ้ำ → ใช้ memory cache (เร็ว)
        assert cache.get_sync(25) is result["img"]
        print("✅ get_sync(25) → ใช้ memory cache (ไม่ดาวน์โหลดซ้ำ)")
        # disk cache ต้องมีไฟล์
        assert os.path.exists(cache._path(25))
        print(f"✅ disk cache: {cache._path(25)}")
    else:
        print("❌ timeout — อาจไม่มีอินเทอร์เน็ต หรือ CDN ล่ม")
