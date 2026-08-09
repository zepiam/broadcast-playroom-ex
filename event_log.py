"""event_log.py — เก็บ log ของทุก event (bits/sub/superchat/gift/raid/like/follow/share/join)

แยกจาก message_history (เก็บเฉพาะ chat) — อันนี้เก็บ event พิเศษเท่านั้น
เก็บ **ทุก event** เสมอ (ไม่ filter ตอนบันทึก) — การกรองทำตอนแสดงผล
เพื่อให้ผู้ใช้เปิด/ปิด event type ทีหลังได้ และยังเห็นข้อมูลเก่า

persist: ~/.tts-for-livestream/event_log.json (cap ตาม events_log_max)
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, asdict
from datetime import datetime

from data_dir import get_data_dir
CACHE_DIR = get_data_dir()
EVENT_LOG_FILE = os.path.join(CACHE_DIR, "event_log.json")

# event types ที่เป็นไปได้ (ใช้ใน settings filter)
ALL_EVENT_TYPES = [
    "bits", "superchat", "gift", "sub", "resub", "subgift",
    "raid", "like", "follow", "share", "join", "redeem",
]

# default event types ที่แสดง (ทั้งหมด)
DEFAULT_SHOWN_EVENTS = [
    "bits", "superchat", "gift", "sub", "resub", "subgift",
    "raid", "like", "follow", "share", "join", "redeem",
]

DEFAULT_MAX = 2000


@dataclass
class EventEntry:
    """1 event record — สำหรับแสดงใน Events panel"""
    timestamp: str          # ISO (สำหรับ sort/เรียงลำดับ)
    platform: str           # twitch/youtube/mylive/tiktok
    author: str             # ชื่อ display ตอนนั้น
    event: str              # bits/sub/superchat/gift/raid/like/follow/share/join
    amount: int             # bits/diamonds/baht/viewers/0
    display_text: str       # "ส่ง 100 บิท" (ข้อความสั้นสำหรับแสดง)
    system_text: str        # "500 THB" / "subbed 12 months" (รายละเอียดเพิ่ม)

    def to_dict(self) -> dict:
        return asdict(self)


class EventLog:
    """เก็บ event log — thread-safe + JSON persist

    เก็บทุก event (ไม่ filter ตอน record) — filter ตอน query เท่านั้น
    """

    def __init__(self, max_entries: int = DEFAULT_MAX) -> None:
        self.max_entries = max_entries
        # list of EventEntry (เรียงเก่า→ใหม่)
        self._entries: list[EventEntry] = []
        self._lock = threading.Lock()
        os.makedirs(CACHE_DIR, exist_ok=True)
        self._load()
        # debounced save (single writer thread + dirty flag — กัน thread storm)
        self._dirty = False
        self._writer_stop = threading.Event()
        self._writer_wake = threading.Event()
        self._writer_thread: threading.Thread | None = None

    # ------------------------------------------------------------------ #
    # Record
    # ------------------------------------------------------------------ #
    def record(
        self,
        platform: str,
        author: str,
        event: str,
        amount: int = 0,
        display_text: str = "",
        system_text: str = "",
    ) -> EventEntry:
        """บันทึก event 1 รายการ — เก็บทุก event เสมอ

        Returns: EventEntry ที่บันทึก
        """
        entry = EventEntry(
            timestamp=datetime.now().isoformat(timespec="seconds"),
            platform=platform,
            author=author or "?",
            event=event,
            amount=int(amount or 0),
            display_text=display_text or "",
            system_text=system_text or "",
        )
        with self._lock:
            self._entries.append(entry)
            # cap — เก็บแค่ล่าสุด max_entries
            if len(self._entries) > self.max_entries:
                self._entries = self._entries[-self.max_entries:]
        self._save_async()
        return entry

    # ------------------------------------------------------------------ #
    # Query
    # ------------------------------------------------------------------ #
    def get_all(self) -> list[EventEntry]:
        """คืนทุก event (เรียงเก่า→ใหม่)"""
        with self._lock:
            return list(self._entries)

    def get_by_author(self, author: str) -> list[EventEntry]:
        """คืน events ของ author เท่านั้น (เรียงเก่า→ใหม่)"""
        author_lower = (author or "").lower()
        with self._lock:
            return [e for e in self._entries if e.author.lower() == author_lower]

    def get_filtered(self, shown_events) -> list[EventEntry]:
        """คืนเฉพาะ event type ที่อยู่ใน shown_events (เรียงเก่า→ใหม่)

        Args:
            shown_events: set/list ของ event type ที่จะแสดง
        """
        if not shown_events:
            return []
        shown = set(shown_events)
        with self._lock:
            return [e for e in self._entries if e.event in shown]

    def count(self) -> int:
        """จำนวน event ทั้งหมด"""
        with self._lock:
            return len(self._entries)

    def count_filtered(self, shown_events) -> int:
        """จำนวน event ที่กรองแล้ว"""
        return len(self.get_filtered(shown_events))

    # ------------------------------------------------------------------ #
    # Modify
    # ------------------------------------------------------------------ #
    def clear(self) -> None:
        """ล้าง event log ทั้งหมด"""
        with self._lock:
            self._entries = []
        self._save_async()

    def set_max(self, max_entries: int) -> None:
        """เปลี่ยนขนาด cap — prune ทันทีถ้าเกิน"""
        self.max_entries = max(100, int(max_entries or DEFAULT_MAX))
        with self._lock:
            if len(self._entries) > self.max_entries:
                self._entries = self._entries[-self.max_entries:]
        self._save_async()

    # ------------------------------------------------------------------ #
    # Persist
    # ------------------------------------------------------------------ #
    def _load(self) -> None:
        try:
            with open(EVENT_LOG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:  # noqa: BLE001
            return
        if not isinstance(data, list):
            return
        entries = []
        for d in data:
            if not isinstance(d, dict):
                continue
            try:
                entries.append(EventEntry(
                    timestamp=d.get("timestamp", ""),
                    platform=d.get("platform", ""),
                    author=d.get("author", "?"),
                    event=d.get("event", ""),
                    amount=int(d.get("amount", 0) or 0),
                    display_text=d.get("display_text", ""),
                    system_text=d.get("system_text", ""),
                ))
            except Exception:  # noqa: BLE001
                continue
        with self._lock:
            self._entries = entries[-self.max_entries:]

    def _save(self) -> None:
        try:
            with self._lock:
                data = [e.to_dict() for e in self._entries]
            with open(EVENT_LOG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception:  # noqa: BLE001
            pass

    def _save_async(self) -> None:
        """debounced — แจ้ง writer thread ว่ามีข้อมูลเปลี่ยน (กัน spawn thread/record)"""
        self._dirty = True
        if self._writer_thread is None or not self._writer_thread.is_alive():
            self._writer_thread = threading.Thread(
                target=self._writer_loop, name="event-log-writer", daemon=True,
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
    import tempfile
    import event_log as _self

    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    tmp.close()
    _self.EVENT_LOG_FILE = tmp.name

    el = EventLog(max_entries=100)
    el.record("twitch", "Alice", "bits", 100, "ส่ง 100 บิท")
    el.record("youtube", "Bob", "superchat", 500, "SuperChat 500 THB", "500 THB")
    el.record("tiktok", "Carol", "gift", 30, "ส่ง Rose 30 เพชร")
    el.record("tiktok", "Dave", "like", 5, "กดหัวใจ 5")
    el.record("twitch", "Eve", "sub", 0, "สับ")

    print("Total:", el.count())  # 5
    print("Filtered (default):", el.count_filtered(DEFAULT_SHOWN_EVENTS))  # 4 (like excluded)
    print("Filtered (like only):", el.count_filtered(["like"]))  # 1

    # reload — บันทึกถาวร
    el2 = EventLog(max_entries=100)
    print("After reload:", el2.count())  # 5

    el.clear()
    print("After clear:", el.count())  # 0

    os.unlink(tmp.name)
    print("OK")
