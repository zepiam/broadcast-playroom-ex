"""donate_tracker.py — เก็บยอดโดเนท/สับ/ของขวัญ แยกตาม user + แพลตฟอร์ม

เก็บสถิติสะสมรายคน:
  - Twitch: bits (จำนวนบิทรวม), sub_count (จำนวนครั้ง sub/resub)
  - YouTube: superchat_amount (ยอดเงินรวม)
  - TikTok: gift_diamonds (เพชรรวม), gift_count (จำนวนครั้งส่งของขวัญ)

โครงสร้างข้อมูล:
    {
        "user_lower": {
            "twitch": {"bits": 500, "sub_count": 2},
            "youtube": {"superchat": 1000},
            "tiktok": {"gift_diamonds": 50, "gift_count": 3},
            "total_donate_count": 1,  # นับจากครั้งแรกที่โดเนทผ่านโปรแกรมนี้
        },
    }

persist: ~/.tts-for-livestream/donate_tracker.json
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime

from data_dir import get_data_dir
CACHE_DIR = get_data_dir()
DONATE_FILE = os.path.join(CACHE_DIR, "donate_tracker.json")

# ประเภท donation แยกตามแพลตฟอร์ม
# platform → field name ใน user dict
PLATFORM_FIELDS = {
    "twitch": {
        "bits": int,        # จำนวน bits รวม
        "sub_count": int,   # จำนวนครั้ง sub/resub
    },
    "youtube": {
        "superchat": int,       # ยอดเงิน SuperChat รวม (micros → แปลงแล้ว)
        "membership_count": int,  # จำนวนครั้ง Membership (แยกจาก Twitch sub)
    },
    "tiktok": {
        "gift_diamonds": int,  # จำนวนเพชรรวม
        "gift_count": int,     # จำนวนครั้งส่งของขวัญ
    },
    "kick": {
        "subgift_count": int,  # จำนวนครั้ง gifted sub ของ KICK
    },
}


class DonateTracker:
    """เก็บยอด donation แยกตาม user — thread-safe + JSON persist

    เริ่มนับจาก 1 ตั้งแต่ครั้งแรกที่ user โดเนทผ่านโปรแกรมนี้
    """

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        # user_lower → {platform → {field → value}, "total_donate_count": int}
        self._data: dict[str, dict] = {}
        self._lock = threading.Lock()
        os.makedirs(CACHE_DIR, exist_ok=True)
        self._load()
        # debounced save (single writer thread + dirty flag — กัน thread storm)
        self._dirty = False
        self._writer_stop = threading.Event()
        self._writer_wake = threading.Event()
        self._writer_thread: threading.Thread | None = None

    # ------------------------------------------------------------------ #
    # Record — เพิ่มยอด donation
    # ------------------------------------------------------------------ #
    def record_donation(
        self,
        author: str,
        platform: str,
        event: str,
        amount: int = 0,
    ) -> None:
        """บันทึก donation 1 ครั้ง

        Args:
            author: ชื่อผู้ส่ง
            platform: "twitch" | "youtube" | "tiktok"
            event: ประเภท ("bits" | "sub" | "resub" | "gift" | "superchat" | ...)
            amount: จำนวน (bits/diamonds/baht)
        """
        if not self.enabled or not author:
            return

        user_key = author.lower()
        amount = int(amount or 0)

        with self._lock:
            user_data = self._data.setdefault(user_key, {})
            plat_data = user_data.setdefault(platform, {})

            # แมป event → field
            if platform == "twitch":
                if event in ("bits",):
                    plat_data["bits"] = plat_data.get("bits", 0) + amount
                    self._bump_donate_count(user_data)
                elif event in ("sub", "resub"):
                    plat_data["sub_count"] = plat_data.get("sub_count", 0) + 1
                    self._bump_donate_count(user_data)
                elif event in ("subgift",):
                    plat_data["subgift_count"] = plat_data.get("subgift_count", 0) + 1
                    self._bump_donate_count(user_data)
            elif platform == "youtube":
                if event in ("superchat",):
                    plat_data["superchat"] = plat_data.get("superchat", 0) + amount
                    self._bump_donate_count(user_data)
                elif event in ("sub", "membership"):
                    # YouTube membership (แยกจาก Twitch sub)
                    plat_data["membership_count"] = plat_data.get("membership_count", 0) + 1
                    self._bump_donate_count(user_data)
            elif platform == "tiktok":
                if event in ("gift",):
                    plat_data["gift_diamonds"] = plat_data.get("gift_diamonds", 0) + amount
                    plat_data["gift_count"] = plat_data.get("gift_count", 0) + 1
                    self._bump_donate_count(user_data)
            elif platform == "kick":
                if event in ("subgift",):
                    plat_data["subgift_count"] = plat_data.get("subgift_count", 0) + 1
                    self._bump_donate_count(user_data)

        self._save_async()

    def _bump_donate_count(self, user_data: dict) -> None:
        """เพิ่ม total_donate_count — เริ่มจาก 1 ในครั้งแรก"""
        current = user_data.get("total_donate_count", 0)
        user_data["total_donate_count"] = current + 1

    # ------------------------------------------------------------------ #
    # Query
    # ------------------------------------------------------------------ #
    def get_user(self, author: str) -> dict:
        """คืน dict ของ user (platform stats + total_donate_count)

        Returns {} ถ้าไม่มีข้อมูล
        """
    def all_users(self) -> dict:
        """คืนทุก user + stats (for User Manager)
        Returns: {author_lower: {platform: {...}, ...}}
        """
        import json as _json
        with self._lock:
            return _json.loads(_json.dumps(self._data))

    def get_user(self, author: str) -> dict:
        """คืน dict ของ user (platform stats + total_donate_count)

        Returns {} ถ้าไม่มีข้อมูล
        """
        with self._lock:
            data = self._data.get(author.lower(), {})
            # deep copy เพื่อกัน mutation
            return json.loads(json.dumps(data))

    def get_platform_stat(self, author: str, platform: str) -> dict:
        """คืน stat ของ user ในแพลตฟอร์มนั้น เช่น {"bits": 500, "sub_count": 2}"""
        with self._lock:
            user = self._data.get(author.lower(), {})
            return dict(user.get(platform, {}))

    def get_total_donate_count(self, author: str) -> int:
        """จำนวนครั้งรวมที่ user โดเนทผ่านโปรแกรมนี้"""
        with self._lock:
            user = self._data.get(author.lower(), {})
            return int(user.get("total_donate_count", 0))

    def has_donated(self, author: str) -> bool:
        """user เคยโดเนทผ่านโปรแกรมนี้หรือไม่"""
        return self.get_total_donate_count(author) > 0

    # ------------------------------------------------------------------ #
    # Edit — streamer แก้ไขยอดได้
    # ------------------------------------------------------------------ #
    def set_platform_stat(
        self,
        author: str,
        platform: str,
        field: str,
        value: int,
    ) -> None:
        """ตั้งค่า stat ของ user ในแพลตฟอร์มนั้น (streamer แก้ไขยอด)

        ถ้า user ยังไม่มี record → สร้างใหม่
        ถ้า value <= 0 → ลบ field นั้นออก (กลับเป็น 0)
        """
        try:
            value = int(value)
        except (ValueError, TypeError):
            value = 0

        user_key = author.lower()
        with self._lock:
            user_data = self._data.setdefault(user_key, {})
            plat_data = user_data.setdefault(platform, {})
            if value <= 0:
                plat_data.pop(field, None)
                # ถ้า platform ว่างแล้ว → ลบทิ้ง
                if not plat_data:
                    user_data.pop(platform, None)
            else:
                plat_data[field] = value
            # อัปเดต total_donate_count — นับ platform ที่มีข้อมูลอยู่
            self._recount_donate_total(user_data)
        self._save_async()

    def _recount_donate_total(self, user_data: dict) -> None:
        """คำนวณ total_donate_count ใหม่จากจำนวน platform ที่มีข้อมูล

        (ใช้เมื่อ streamer แก้ไขยอด — นับเป็น platform ที่เคยโดเนท)
        """
        count = sum(1 for k, v in user_data.items() if k != "total_donate_count" and v)
        user_data["total_donate_count"] = count

    def clear_user(self, author: str) -> None:
        """ล้างข้อมูล donation ทั้งหมดของ user"""
        with self._lock:
            self._data.pop(author.lower(), None)
        self._save_async()

    # ------------------------------------------------------------------ #
    # Persist
    # ------------------------------------------------------------------ #
    def _load(self) -> None:
        try:
            with open(DONATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:  # noqa: BLE001
            return
        if not isinstance(data, dict):
            return
        with self._lock:
            self._data = data

    def _save(self) -> None:
        try:
            with self._lock:
                data_copy = json.loads(json.dumps(self._data))
            with open(DONATE_FILE, "w", encoding="utf-8") as f:
                json.dump(data_copy, f, ensure_ascii=False)
        except Exception:  # noqa: BLE001
            pass

    def _save_async(self) -> None:
        """debounced — แจ้ง writer thread ว่ามีข้อมูลเปลี่ยน (กัน spawn thread/record)"""
        self._dirty = True
        if self._writer_thread is None or not self._writer_thread.is_alive():
            self._writer_thread = threading.Thread(
                target=self._writer_loop, name="donate-writer", daemon=True,
            )
            self._writer_thread.start()
        self._writer_wake.set()

    def _writer_loop(self) -> None:
        while not self._writer_stop.is_set():
            self._writer_wake.wait(timeout=3.0)
            self._writer_wake.clear()
            if not self._dirty:
                continue
            self._writer_stop.wait(timeout=3.0)  # debounce
            if self._dirty:
                self._dirty = False
                self._save()

    def flush(self) -> None:
        """บังคับเขียนทันที (เรียกตอนปิดโปรแกรม)"""
        if self._writer_thread is not None and self._writer_thread.is_alive():
            self._writer_stop.set()
            self._writer_wake.set()
            self._writer_thread.join(timeout=2.0)
        if self._dirty:
            self._dirty = False
            self._save()


# ---------------------------------------------------------------------- #
# Smoke test
# ---------------------------------------------------------------------- #
if __name__ == "__main__":
    # ใช้ temp file เพื่อทดสอบ
    import tempfile
    import donate_tracker as _self
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    tmp.close()
    _self.DONATE_FILE = tmp.name

    dt = DonateTracker()
    dt.record_donation("Alice", "twitch", "bits", 100)
    dt.record_donation("Alice", "twitch", "bits", 50)
    dt.record_donation("Alice", "twitch", "sub")
    dt.record_donation("Bob", "tiktok", "gift", 10)
    dt.record_donation("Bob", "tiktok", "gift", 5)

    print("Alice:", dt.get_user("Alice"))
    # → {'twitch': {'bits': 150, 'sub_count': 1}, 'total_donate_count': 3}
    print("Bob:", dt.get_user("Bob"))
    # → {'tiktok': {'gift_diamonds': 15, 'gift_count': 2}, 'total_donate_count': 2}
    print("Alice donate count:", dt.get_total_donate_count("Alice"))  # 3

    # edit
    dt.set_platform_stat("Alice", "twitch", "bits", 999)
    print("After edit Alice:", dt.get_user("Alice"))

    os.unlink(tmp.name)
    print("OK")
