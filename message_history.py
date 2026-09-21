"""message_history.py — เก็บประวัติข้อความแยกตามผู้ชม

เก็บข้อความทั้งหมด (รวมที่ถูกแบน) เพื่อแสดงใน Viewer Profile Modal:
  - สถิติ: จำนวนข้อความต่อคน
  - ประวัติ: log ข้อความ + timestamp
  - ข้อความแบน: เก็บต้นฉบับไว้ reveal ได้

retention modes:
  - "all":   เก็บทั้งหมด (ไม่มีวันหมดอายุ)
  - "today": เก็บเฉพาะวันนี้ (prune ตอนโหลด — ลบของเก่าออก)

persist: ~/.tts-for-livestream/message_history.json

★ สถิติรายคน (_stats) แยกจากตัวข้อความ: แพลตฟอร์มที่เคยแชท + จำนวนข้อความต่อแพลตฟอร์ม + เห็นครั้งแรก/ล่าสุด + วันที่เคยมา
  อัปเดตทุกข้อความ และ "ไม่หายตอนล้างประวัติข้อความ" (clear_chat_text) — ล้างแล้วยังรู้ว่าใครมาจากไหน คุยกี่ครั้ง
  (ยอดโดเนท/ซับเก็บที่ donate_tracker / event_log แยกอยู่แล้ว)
"""
from __future__ import annotations

import gzip
import json
import os
import threading
from datetime import datetime, date, timedelta

from data_dir import get_data_dir
CACHE_DIR = get_data_dir()
HISTORY_FILE = os.path.join(CACHE_DIR, "message_history.json")

# ไฟล์ประวัติใหญ่เกินนี้ → โปรแกรมเตือนตอนเปิด (ให้สำรอง/ล้างข้อความ) — 1 GB
WARN_BYTES = 1024 ** 3


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
        # author_lower → ชื่อจริงตัวพิมพ์เดิมล่าสุด (key เก็บแค่ตัวเล็ก → หน้า User Manager ต้องใช้โชว์ชื่อสวย)
        self._names: dict[str, str] = {}
        # author_lower → {"p": {platform: n}, "first": ts, "last": ts, "d": [วันที่ที่เคยมา]} — ไม่หายตอนล้างข้อความ
        self._stats: dict[str, dict] = {}
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
            # ★ จำชื่อตัวพิมพ์เดิมไว้ (เก็บต่อคนแค่ 1 ค่า ไม่ซ้ำทุกข้อความ)
            if author != key or key in self._names:
                self._names[key] = author
            # ★ สถิติรายคน — คงอยู่แม้ล้างตัวข้อความ
            st = self._stats.setdefault(key, {"p": {}, "first": entry["timestamp"], "last": entry["timestamp"], "d": []})
            if platform:
                st["p"][platform] = st["p"].get(platform, 0) + 1
            st["last"] = entry["timestamp"]
            day = entry["timestamp"][:10]
            if not st["d"] or st["d"][-1] != day:
                if day not in st["d"]:
                    st["d"].append(day)
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
            dates = set((self._stats.get(author.lower()) or {}).get("d", []))
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
            key = author.lower()
            plats = {e.get("platform", "") for e in self._data.get(key, [])}
            plats |= {p for p in (self._stats.get(key) or {}).get("p", {}) if p}
            return plats

    def display_name(self, author: str) -> str:
        """ชื่อตัวพิมพ์เดิมล่าสุดของ author (ไม่เคยเก็บไว้ → คืน '' ให้ caller ใช้ key เอง)"""
        with self._lock:
            return self._names.get(author.lower(), "")

    def remove_author(self, author: str) -> None:
        """ลบประวัติทั้งหมดของ author (ข้อความ + ยอดนับ + ชื่อ)"""
        key = author.lower()
        with self._lock:
            self._data.pop(key, None)
            self._total_counts.pop(key, None)
            self._names.pop(key, None)
            self._stats.pop(key, None)
        self._save_async()

    # ------------------------------------------------------------------ #
    # สรุปรายคน (User Manager) + ดูแลขนาดไฟล์
    # ------------------------------------------------------------------ #
    def roster_stats(self, only: str | None = None) -> dict:
        """สรุปรายคนสำหรับหน้า User Manager — ไม่ต้อง copy ข้อความทั้งหมด (เบา แม้ประวัติใหญ่)
        {key: {"n": ยอดข้อความตลอดกาล, "plats": {แพลตฟอร์ม: จำนวน}, "first", "last", "days": [วันที่], "retained": ข้อความที่ยังเก็บอยู่}}
        """
        with self._lock:
            if only:
                keys = [only.lower()] if (only.lower() in self._data or only.lower() in self._total_counts
                                          or only.lower() in self._stats) else []
            else:
                keys = set(self._data) | set(self._total_counts) | set(self._stats)
            out = {}
            for k in keys:
                st = self._stats.get(k) or {}
                entries = self._data.get(k, [])
                plats = dict(st.get("p", {}))
                if not plats and entries:                     # ไม่มีสถิติ (ไม่ควรเกิด) → นับจากข้อความที่มี
                    for e in entries:
                        p = e.get("platform", "")
                        if p:
                            plats[p] = plats.get(p, 0) + 1
                out[k] = {
                    "n": self._total_counts.get(k, len(entries)),
                    "plats": plats,
                    "first": st.get("first") or (entries[0].get("timestamp", "") if entries else ""),
                    "last": st.get("last") or (entries[-1].get("timestamp", "") if entries else ""),
                    "days": list(st.get("d", [])),
                    "retained": len(entries),
                }
            return out

    @staticmethod
    def file_size() -> int:
        """ขนาดไฟล์ประวัติบนดิสก์ (ไบต์) — 0 ถ้ายังไม่มี"""
        try:
            return os.path.getsize(HISTORY_FILE)
        except OSError:
            return 0

    def chat_text_summary(self) -> tuple[int, int]:
        """(จำนวนข้อความที่เก็บตัวข้อความไว้, จำนวนคนที่มีข้อความเก็บอยู่)"""
        with self._lock:
            return sum(len(v) for v in self._data.values()), sum(1 for v in self._data.values() if v)

    def archive_chat_text(self, path: str) -> int:
        """สำรองตัวข้อความแชททั้งหมดเป็นไฟล์บีบอัด (.json.gz) — เขียนแบบสตรีม ไม่สร้างสตริงก้อนใหญ่ในหน่วยความจำ
        คืนขนาดไฟล์ที่ได้ (ไบต์); พลาดตรงไหน → โยน exception (ผู้เรียกต้องไม่ล้างข้อความ) และลบไฟล์ที่เขียนค้าง"""
        with self._lock:
            snap = {k: list(v) for k, v in self._data.items()}          # ตื้นๆ: list ใหม่ แต่ entry เดิม
            counts = dict(self._total_counts)
            names = dict(self._names)
        payload = {"format": "broadcast-playroom-chat-archive", "version": 1,
                   "created": datetime.now().isoformat(timespec="seconds"),
                   "data": snap, "_total_counts": counts, "_names": names}
        tmp = path + ".part"
        try:
            with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=6) as f:
                json.dump(payload, f, ensure_ascii=False)
            # ตรวจว่าอ่านกลับได้จริง (แค่หัวไฟล์ + ท้ายไฟล์ผ่าน gzip CRC เมื่ออ่านจนจบ)
            with gzip.open(tmp, "rt", encoding="utf-8") as f:
                while f.read(1 << 20):
                    pass
            os.replace(tmp, path)
        except Exception:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise
        return os.path.getsize(path)

    def purge_older_than(self, days: int) -> int:
        """ลบ "ตัวข้อความแชท" ที่เก่ากว่า `days` วัน (นับย้อนจากตอนนี้) — คืนจำนวนที่ลบ; days <= 0 = ไม่ทำอะไร

        ไม่ลบ: ยอดข้อความรวม/ชื่อ/สถิติรายคน (แพลตฟอร์ม, วันที่มา, เห็นครั้งแรก-ล่าสุด) — สร้างสถิติให้ครบก่อนลบเสมอ
        """
        if not days or days <= 0:
            return 0
        cutoff = (datetime.now() - timedelta(days=int(days))).isoformat(timespec="seconds")
        removed = 0
        with self._lock:
            self._ensure_stats_locked()
            for author in list(self._data.keys()):
                entries = self._data[author]
                # ข้อความที่ไม่มี timestamp (ไม่ควรมี) ตัดสินอายุไม่ได้ → เก็บไว้
                keep = [e for e in entries if not e.get("timestamp") or e["timestamp"] >= cutoff]
                if len(keep) != len(entries):
                    removed += len(entries) - len(keep)
                    if keep:
                        self._data[author] = keep
                    else:
                        del self._data[author]
        if removed:
            self._dirty = False
            self._save()
        return removed

    def clear_chat_text(self) -> int:
        """ล้าง "ตัวข้อความแชท" ของทุกคน — คืนจำนวนข้อความที่ล้าง

        เก็บไว้ครบ: ยอดข้อความรวมต่อคน (_total_counts), ชื่อ (_names), สถิติรายคน (_stats: แพลตฟอร์ม/วันที่มา/เห็นครั้งแรก-ล่าสุด)
        ไม่แตะ donate_tracker / event_log / settings (ชื่อที่ตั้งเอง, บล็อก) เลย
        """
        with self._lock:
            removed = sum(len(v) for v in self._data.values())
            # ก่อนล้าง: ให้แน่ใจว่าทุกคนมีสถิติ (กรณีข้อมูลเก่าที่ยังไม่เคยสร้าง) — จะได้ไม่เสียแพลตฟอร์ม/วันที่
            self._ensure_stats_locked()
            self._data = {}
        self._dirty = False
        self._save()                       # เขียนทันที → ไฟล์หดลงเลย (ไม่รอ writer)
        return removed

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
                names = raw.get("_names", {})
                self._names = dict(names) if isinstance(names, dict) else {}
                stats = raw.get("_stats", {})
                self._stats = dict(stats) if isinstance(stats, dict) else {}
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
            # ★ ไฟล์จากรุ่นก่อน (ยังไม่มีสถิติรายคน) → สร้างจากข้อความที่เก็บอยู่ตอนนี้ (ครั้งเดียว)
            self._ensure_stats_locked()

        if self.retention == "today":
            self._prune_today()

    def _ensure_stats_locked(self) -> None:
        """สร้างสถิติให้คนที่ยังไม่มี จากข้อความที่เก็บอยู่ (เรียกภายใต้ self._lock)"""
        for author, entries in self._data.items():
            if author in self._stats or not entries:
                continue
            plats: dict[str, int] = {}
            days: list[str] = []
            for e in entries:
                p = e.get("platform", "")
                if p:
                    plats[p] = plats.get(p, 0) + 1
                d = (e.get("timestamp", "") or "")[:10]
                if d and d not in days:
                    days.append(d)
            self._stats[author] = {"p": plats, "first": entries[0].get("timestamp", ""),
                                   "last": entries[-1].get("timestamp", ""), "d": days}

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
        # ★ reset total_counts ในโหมด today (นับใหม่เฉพาะวันนี้) — สถิติรายคนก็เริ่มใหม่ให้สอดคล้องกัน
        with self._lock:
            self._total_counts = {k: len(v) for k, v in self._data.items()}
            self._stats = {}
            self._ensure_stats_locked()
        self._save()

    def _save(self) -> None:
        """บันทึกลง JSON (sync) — เก็บ data + total_counts"""
        try:
            with self._lock:
                save_obj = {
                    "data": {k: list(v) for k, v in self._data.items()},
                    "_total_counts": dict(self._total_counts),
                    "_names": dict(self._names),
                    "_stats": {k: {"p": dict(v.get("p", {})), "first": v.get("first", ""),
                                   "last": v.get("last", ""), "d": list(v.get("d", []))}
                               for k, v in self._stats.items()},
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
