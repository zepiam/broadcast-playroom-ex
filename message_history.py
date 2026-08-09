"""message_history.py — เก็บประวัติข้อความแยกตามผู้ชม

เก็บข้อความทั้งหมด (รวมที่ถูกแบน) เพื่อแสดงใน Viewer Profile Modal:
  - สถิติ: จำนวนข้อความต่อคน
  - ประวัติ: log ข้อความ + timestamp
  - ข้อความแบน: เก็บต้นฉบับไว้ reveal ได้

retention modes:
  - "all":   เก็บทั้งหมด (ไม่มีวันหมดอายุ)
  - "today": เก็บเฉพาะวันนี้ (prune ตอนโหลด — ลบของเก่าออก)

persist: ~/.tts-for-livestream/message_history.json
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, date

from data_dir import get_data_dir
CACHE_DIR = get_data_dir()
HISTORY_FILE = os.path.join(CACHE_DIR, "message_history.json")


class MessageHistory:
    """เก็บประวัติข้อความแยกตาม author — thread-safe + JSON persist"""

    # debounce: รวมหลาย record เป็น 1 ครั้งเขียน (กัน thread storm ตอน chat เยอะ)
    _SAVE_DEBOUNCE = 3.0  # วินาที — รอ 3 วิแล้วค่อยเขียน (รวมทุก record ในช่วงนั้น)

    def __init__(self, retention: str = "all", enabled: bool = True) -> None:
        self.retention = retention  # "all" | "today"
        self.enabled = enabled
        # author_lower → [{timestamp, platform, text, is_banned, banned_original}]
        self._data: dict[str, list[dict]] = {}
        # author_lower → total message count (ตลอดกาล — ไม่หายตอน cap)
        self._total_counts: dict[str, int] = {}
        self._lock = threading.Lock()
        os.makedirs(CACHE_DIR, exist_ok=True)
        self._load()
        # debounced save state (single writer thread + dirty flag)
        self._dirty = False
        self._writer_stop = threading.Event()
        self._writer_wake = threading.Event()
        self._writer_thread: threading.Thread | None = None

    # ------------------------------------------------------------------ #
    # Record
    # ------------------------------------------------------------------ #
    def record(
        self,
        author: str,
        platform: str,
        text: str,
        is_banned: bool = False,
        banned_original: str = "",
        emotes: str = "",
        emote_urls: str = "",
    ) -> None:
        """บันทึกข้อความ 1 รายการ (เรียกจาก on_message ทุกครั้ง แม้แบน)

        Args:
            emotes: emote names (คั่นด้วย space) สำหรับแสดงใน log เมื่อ text ว่าง
            emote_urls: emote image URLs (คั่นด้วย |) สำหรับแสดงภาพใน Modal
        thread-safe (เรียกจาก chat thread ได้)
        """
        if not self.enabled or not author:
            return
        entry = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "platform": platform,
            "text": text or "",
            "is_banned": is_banned,
            "banned_original": banned_original or "",
            "emotes": emotes or "",
            "emote_urls": emote_urls or "",
        }
        key = author.lower()
        with self._lock:
            user_list = self._data.setdefault(key, [])
            user_list.append(entry)
            # cap per author (กัน memory bloat — เก็บสูงสุด 500/คน)
            if len(user_list) > 500:
                user_list[:] = user_list[-500:]
            # ★ total_count — นับรวมตลอดกาล (ไม่หายตอน cap)
            self._total_counts[key] = self._total_counts.get(key, 0) + 1
        self._save_async()

    # ------------------------------------------------------------------ #
    # Query
    # ------------------------------------------------------------------ #
    def get(self, author: str) -> list[dict]:
        """คืนประวัติของ author (เรียงเก่า→ใหม่)"""
        with self._lock:
            return list(self._data.get(author.lower(), []))

    def get_messages_by_author(self, author: str, limit: int = 20, offset: int = 0) -> list[dict]:
        """คืนข้อความของ author พร้อม pagination (เรียงใหม่→เก่า)

        Args:
            author: ชื่อ user
            limit: จำนวนสูงสุดที่จะคืน (default 20)
            offset: ข้ามรายการแรก N รายการ (สำหรับ load more)
        Returns: list[dict] เรียงใหม่→เก่า
        """
        with self._lock:
            entries = list(self._data.get(author.lower(), []))
        # เรียงใหม่→เก่า
        entries.reverse()
        # pagination
        return entries[offset:offset + limit]

    def count(self, author: str) -> int:
        """จำนวนข้อความทั้งหมดของ author (ตลอดกาล — ไม่จำกัดที่ 500)"""
        with self._lock:
            return self._total_counts.get(author.lower(), len(self._data.get(author.lower(), [])))

    def all_authors(self) -> dict:
        """คืนทุก author + entries (for User Manager)
        Returns: {author_lower: [entry, ...]}
        """
        with self._lock:
            return {k: list(v) for k, v in self._data.items()}

    def visit_count(self, author: str) -> int:
        """นับจำนวนวันที่แตกต่างกันที่ author มาแชท (unique dates)
        ถ้าแชทวันเดียว = 1 ครั้ง, คนละวัน = +1 ต่อวัน
        """
        with self._lock:
            entries = self._data.get(author.lower(), [])
            dates = set()
            for e in entries:
                ts = e.get("timestamp", "")
                # timestamp format: "2026-07-24T12:30:00" → date = "2026-07-24"
                date_str = ts[:10] if len(ts) >= 10 else ts
                if date_str:
                    dates.add(date_str)
            return len(dates)

    def platforms(self, author: str) -> set[str]:
        """แพลตฟอร์มที่ author คุยด้วย"""
        with self._lock:
            return {e.get("platform", "") for e in self._data.get(author.lower(), [])}

    # ------------------------------------------------------------------ #
    # Persist
    # ------------------------------------------------------------------ #
    def _load(self) -> None:
        """โหลดจาก JSON — prune ถ้า retention='today'"""
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:  # noqa: BLE001
            return  # ไม่มีไฟล์/เสีย → เริ่มใหม่

        with self._lock:
            # ★ backward compat: เดิมเก็บแค่ data dict → ถ้ามี _total_counts ให้แยก
            if isinstance(raw, dict) and "_total_counts" in raw:
                self._data = raw.get("data", {})
                self._total_counts = raw.get("_total_counts", {})
            elif isinstance(raw, dict):
                # เดิม — สร้าง total_counts จากจำนวน entries ปัจจุบัน
                self._data = raw
                self._total_counts = {k: len(v) for k, v in raw.items()}
            else:
                return

        # ★ migration: ถ้า total_counts น้อยกว่า entries (ข้อมูลเก่า) → sync
        with self._lock:
            for author, entries in self._data.items():
                if self._total_counts.get(author, 0) < len(entries):
                    self._total_counts[author] = len(entries)

        if self.retention == "today":
            self._prune_today()

    def _prune_today(self) -> None:
        """ลบ entries ที่ไม่ใช่วันนี้ (เรียกตอนโหลด)"""
        today_str = date.today().isoformat()
        with self._lock:
            for author in list(self._data.keys()):
                self._data[author] = [
                    e for e in self._data[author]
                    if e.get("timestamp", "").startswith(today_str)
                ]
                if not self._data[author]:
                    del self._data[author]
        # ★ reset total_counts ในโหมด today (นับใหม่เฉพาะวันนี้)
        with self._lock:
            self._total_counts = {k: len(v) for k, v in self._data.items()}
        self._save()

    def _save(self) -> None:
        """บันทึกลง JSON (sync) — เก็บ data + total_counts"""
        try:
            with self._lock:
                save_obj = {
                    "data": {k: list(v) for k, v in self._data.items()},
                    "_total_counts": dict(self._total_counts),
                }
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(save_obj, f, ensure_ascii=False)
        except Exception:  # noqa: BLE001
            pass

    def _save_async(self) -> None:
        """แจ้ง writer thread ว่ามีข้อมูลเปลี่ยน (debounced)

        แทนการ spawn thread ใหม่ทุก record (เคยทำให้ RAM พุ่ง 1.9GB ตอน chat เยอะ)
        ใช้ dirty flag + single writer thread ที่ wait debounce แล้วเขียนรวมครั้งเดียว
        """
        self._dirty = True
        # start writer thread ถ้ายังไม่มี (lazy — เริ่มตอนมี record แรกเท่านั้น)
        if self._writer_thread is None or not self._writer_thread.is_alive():
            self._writer_thread = threading.Thread(
                target=self._writer_loop, name="history-writer", daemon=True,
            )
            self._writer_thread.start()
        self._writer_wake.set()

    def _writer_loop(self) -> None:
        """writer thread เดียว — loop จนกว่าจะปิดโปรแกรม

        wake → รอ debounce → เขียน → กลับไปรอ (กันเขียนถี่เกินไป)
        """
        while not self._writer_stop.is_set():
            # รอจนกว่าจะมี dirty (แต่ไม่ block ถ้าโปรแกรมกำลังปิด)
            self._writer_wake.wait(timeout=self._SAVE_DEBOUNCE)
            self._writer_wake.clear()
            if not self._dirty:
                continue
            # debounce: รอเพิ่มอีกเพื่อรวบ record ที่มาในช่วงสั้นๆ
            self._writer_stop.wait(timeout=self._SAVE_DEBOUNCE)
            if self._dirty:
                self._dirty = False
                self._save()

    def flush(self) -> None:
        """บังคับเขียนทันที (เรียกตอนปิดโปรแกรม เพื่อกันเสียข้อมูล)"""
        if self._writer_thread is not None and self._writer_thread.is_alive():
            self._writer_stop.set()
            self._writer_wake.set()
            self._writer_thread.join(timeout=2.0)
        # เขียนครั้งสุดท้าย sync
        if self._dirty:
            self._dirty = False
            self._save()

    def set_retention(self, retention: str) -> None:
        """เปลี่ยน retention mode — prune ทันทีถ้าเป็น 'today'"""
        self.retention = retention
        if retention == "today":
            self._prune_today()


# ---------------------------------------------------------------------- #
# Smoke test
# ---------------------------------------------------------------------- #
if __name__ == "__main__":
    h = MessageHistory(retention="all")
    h.record("TestUser", "twitch", "hello")
    h.record("TestUser", "twitch", "world")
    h.record("TestUser", "twitch", "banned msg", is_banned=True, banned_original="bad word")
    print(f"count: {h.count('TestUser')}")  # 3
    print(f"platforms: {h.platforms('TestUser')}")  # {'twitch'}
    for e in h.get("TestUser"):
        print(f"  [{e['timestamp']}] banned={e['is_banned']} text={e['text']!r}"
              + (f" orig={e['banned_original']!r}" if e['is_banned'] else ""))
