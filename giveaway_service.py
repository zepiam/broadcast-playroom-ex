# -*- coding: utf-8 -*-
"""giveaway_service.py — บริการจัดการระบบเช็คชื่อ & สุ่มแจกรางวัล (Loyalty Giveaway)

รองรับ:
- โหมดรอบเดียว (Single Check-in: พิมพ์ครั้งเดียวจบ)
- โหมดหลายรอบ (Multi-Checkpoint: 2-5 ด่านสะสมแต้ม)
- โค้ดอิสระในแต่ละด่าน สามารถแก้ไขเปลี่ยนคำสั่งได้ตลอดจนกว่าจะเริ่มใช้งาน
- กำหนดเวลาแบบนับถอยหลัง (1-20 นาที) หรือแบบไม่มีกำหนด (Manual Close)
- Export ข้อมูลเป็น Excel CSV (UTF-8 BOM ภาษาไทยไม่เพี้ยน)
"""
from __future__ import annotations

import csv
import io
import time
import random
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Tuple

from PySide6.QtCore import QObject, Signal, QTimer


@dataclass
class Participant:
    """ข้อมูลผู้เข้าร่วมกิจกรรม"""
    author: str
    platform: str
    avatar: str = ""
    checkins: Set[int] = field(default_factory=set)  # {1, 2, ...}
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)

    @property
    def key(self) -> str:
        return f"{self.platform}:{self.author.lower()}"

    def calculate_tier(self, total_checkpoints: int) -> int:
        """คำนวณ Tier (1 = ครบทุกด่าน, 2 = ขาด 1 ด่าน, ...)"""
        if total_checkpoints <= 1:
            return 1
        count = len(self.checkins)
        if count >= total_checkpoints:
            return 1
        diff = total_checkpoints - count
        return min(total_checkpoints, 1 + diff)


@dataclass
class WinnerRecord:
    """บันทึกประวัติผู้ที่ได้รับรางวัล"""
    author: str
    platform: str
    prize: str
    tier_label: str
    timestamp: float = field(default_factory=time.time)


class GiveawayService(QObject):
    """บริการหลักของระบบ Giveaway เชื่อมต่อระหว่าง Chat Stream, App GUI และ OBS Overlay"""

    # Signals
    config_changed = Signal()
    checkpoint_started = Signal(int, str, int)   # (cp_index, code, duration_sec) — duration_sec = 0 หมายถึงไม่มีกำหนด
    checkpoint_tick = Signal(float, int)         # (remaining_sec, total_participants)
    checkpoint_ended = Signal(int, int)          # (cp_index, total_checked_in)
    participant_added = Signal(object, int)      # (Participant, cp_index)
    winner_picked = Signal(object, str, str)     # (Participant, prize, tier_label)
    draw_started = Signal(str, str, list, str)   # (prize, tier_label, candidate_names, winner_name)
    draw_winner_shown = Signal(object, str, str) # (Participant, prize, tier_label)
    draw_reset = Signal()
    data_cleared = Signal()
    preview_requested = Signal(object)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._lock = threading.RLock()

        # โหมดการเล่น: "single" (รอบเดียว) หรือ "multi" (หลายรอบ)
        self.mode: str = "single"
        self.total_checkpoints: int = 1  # จำนวนด่านทั้งหมด (1 - 5)

        # รูปแบบอนิเมชั่นการสุ่มรางวัล: "gachapon" (กาชาปองระเบิดดาว) หรือ "slot" (ตู้สล็อตคลาสสิก)
        self.draw_animation_style: str = "gachapon"

        # โค้ดของแต่ละด่าน {1: "#join", 2: "#join2", ...} (แก้ได้ตลอดก่อนเริ่มด่าน)
        self.checkpoint_codes: Dict[int, str] = {
            1: "#join",
            2: "#join2",
            3: "#lucky3",
            4: "#code4",
            5: "#code5",
        }

        # ชื่อที่กำหนดเองของแต่ละรอบ {1: "รอบที่ 1", ...}
        self.checkpoint_names: Dict[int, str] = {
            1: "รอบที่ 1",
            2: "รอบที่ 2",
            3: "รอบที่ 3",
            4: "รอบที่ 4",
            5: "รอบที่ 5",
        }

        # ตัวจับเวลานับถอยหลังภายใน Service ส่ง tick ให้ Overlay และ GUI
        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._on_service_timer_tick)

        # สถานะการเปิดรับปัจจุบัน
        self.active_checkpoint: int = 1         # กำลังรันด่านไหนอยู่ (1..total)
        self.current_code: str = "#join"
        self.duration_sec: int = 60             # 0 = ไม่มีกำหนด (Manual Close), >0 = นับถอยหลัง
        self.is_active: bool = False
        self.start_time: float = 0.0
        self.end_time: float = 0.0

        # ข้อมูลผู้เข้าร่วม key: "platform:author_lowercase" -> Participant
        self.participants: Dict[str, Participant] = {}

        # บันทึกผู้ชนะรางวัล
        self.winners_history: List[WinnerRecord] = []

        # การแสดงผลบน OBS Overlay (Banner หรือ Custom Image)
        self.overlay_display_mode: str = "banner"   # "banner" (การ์ดข้อความ) หรือ "image" (รูปภาพแบนเนอร์)
        self.overlay_image_path: str = ""          # path ไฟล์รูปภาพ (png, jpg, webp, gif)
        self.overlay_position: str = "right"       # "right", "left", "center", "top", "bottom"
        self.overlay_offset_x: int = 0             # px (-300 ถึง 300)
        self.overlay_offset_y: int = 0             # px (-300 ถึง 300)
        self.overlay_scale: int = 100              # % (50 ถึง 150)
        self.overlay_font_size: int = 100          # % (70 ถึง 160)
        self.overlay_anim_in: str = "slide"        # "slide", "fade", "zoom", "bounce"
        self.overlay_anim_out: str = "slide"       # "slide", "fade", "zoom"
        self.overlay_show_progress_bar: bool = True     # หลอดนับถอยหลัง (Progress bar)
        self.overlay_show_countdown_border: bool = True  # เส้นขอบนับถอยหลังรอบการ์ด/ภาพ
        self.overlay_border_theme: str = "rainbow" # "rainbow", "cyberpunk", "gold", "ice", "sakura", "emerald", "ruby", "violet", "blue"
        self.overlay_show_toast: bool = True       # แสดงป็อปอัปผู้เข้าร่วม (ถ้า False = โหมดเงียบสำหรับรายการใหญ่)
        self.overlay_show_stats: bool = True       # แสดงตัวเลขเวลา/คน

        # การปรับแต่งหน้าตาสุ่มรางวัล (Draw Overlay Styling)
        self.draw_scale: int = 100         # % (50 ถึง 180)
        self.draw_name_size: int = 52      # px (28 ถึง 84)
        self.draw_prize_size: int = 20     # px (14 ถึง 36)
        self.draw_offset_x: int = 0        # px (-400 ถึง 400)
        self.draw_offset_y: int = 0        # px (-400 ถึง 400)
        self.draw_theme: str = "gold"      # "gold", "cyberpunk", "violet", "emerald", "sakura", "ice", "ruby"
        self.sound_enabled: bool = False   # เปิด/ปิด เสียงเอฟเฟกต์ (ค่าเริ่มต้นปิดเป็นโหมดเงียบตามความต้องการ)
        self.draw_autohide_sec: int = 15   # ซ่อนผลการสุ่มบนจอ OBS อัตโนมัติ (วินาที) ค่าเริ่มต้น 15 วิ (0 = ไม่ซ่อน)
        self._last_draw_candidates: List[str] = []
        self._last_draw_winner_name: str = ""
        self._last_draw_prize: str = ""
        self._last_draw_tier: str = ""

    def _on_service_timer_tick(self):
        """ตัวนับถอยหลังระดับ Service ทำงานทุก 250ms เพื่อส่ง tick ไปยัง OBS Overlay และ GUI"""
        should_end = False
        cp_idx = 1
        round_p = 0
        rem = 0.0

        with self._lock:
            if not self.is_active:
                self._timer.stop()
                return

            now = time.time()
            cp_idx = self.active_checkpoint
            round_p = len([p for p in self.participants.values() if cp_idx in p.checkins])

            if self.duration_sec > 0:
                rem = max(0.0, self.end_time - now)
                if rem <= 0.0:
                    should_end = True
                    self.is_active = False
                    self._timer.stop()
            else:
                rem = 0.0

        # ส่ง tick สัญญาณออกนอก lock
        self.checkpoint_tick.emit(rem, round_p)

        if should_end:
            self.checkpoint_ended.emit(cp_idx, round_p)

    def set_mode(self, mode: str, total_checkpoints: Optional[int] = None):
        """ตั้งค่าโหมดกิจกรรม (single / multi) และจำนวนด่าน"""
        with self._lock:
            self.mode = "single" if mode == "single" else "multi"
            if self.mode == "single":
                self.total_checkpoints = 1
                self.active_checkpoint = 1
            else:
                if total_checkpoints is not None:
                    self.total_checkpoints = max(2, int(total_checkpoints))
                elif self.total_checkpoints < 2:
                    self.total_checkpoints = 2
                self.active_checkpoint = min(self.active_checkpoint, self.total_checkpoints)
        self.config_changed.emit()

    def get_checkpoint_name(self, cp_index: int) -> str:
        """ดึงชื่อรอบกิจกรรม (กำหนดเองได้)"""
        with self._lock:
            if self.mode == "single":
                name = self.checkpoint_names.get(cp_index, "")
                return name if (name and name != "รอบที่ 1") else "เปิดรับโค้ดสุ่มรางวัล"
            return self.checkpoint_names.get(cp_index, f"รอบที่ {cp_index}")

    def set_checkpoint_name(self, cp_index: int, name: str):
        """แก้ไขชื่อรอบกิจกรรม"""
        clean = name.strip()
        if not clean:
            return
        with self._lock:
            self.checkpoint_names[cp_index] = clean
        self.config_changed.emit()

    def add_checkpoint(self, code: Optional[str] = None, name: Optional[str] = None) -> int:
        """เพิ่มรอบใหม่แบบยืดหยุ่นระหว่างไลฟ์ พร้อมตั้งชื่อรอบได้เอง"""
        with self._lock:
            self.total_checkpoints += 1
            new_idx = self.total_checkpoints
            if self.total_checkpoints > 1:
                self.mode = "multi"

            clean_name = (name or "").strip()
            self.checkpoint_names[new_idx] = clean_name if clean_name else f"รอบที่ {new_idx}"

            clean_code = (code or "").strip()
            if clean_code:
                self.checkpoint_codes[new_idx] = clean_code
            elif new_idx not in self.checkpoint_codes:
                self.checkpoint_codes[new_idx] = f"#join{new_idx}"
            self.active_checkpoint = new_idx
            self.current_code = self.checkpoint_codes[new_idx]
        self.config_changed.emit()
        return new_idx

    def remove_checkpoint(self, cp_index: Optional[int] = None) -> bool:
        """ลบรอบล่าสุด (ต้องมีอย่างน้อย 1 รอบเสมอ)"""
        with self._lock:
            if self.total_checkpoints <= 1:
                return False
            target = cp_index if (cp_index is not None and cp_index > 0) else self.total_checkpoints
            # ลบสิทธิ์ของรอบนี้ออกจากผู้เข้าร่วม
            for p in self.participants.values():
                p.checkins.discard(target)
            self.checkpoint_codes.pop(target, None)
            self.checkpoint_names.pop(target, None)
            self.total_checkpoints -= 1
            if self.total_checkpoints <= 1:
                self.total_checkpoints = 1
                self.mode = "single"
            self.active_checkpoint = min(self.active_checkpoint, self.total_checkpoints)
            self.current_code = self.get_checkpoint_code(self.active_checkpoint)
        self.config_changed.emit()
        return True

    def set_checkpoint_code(self, cp_index: int, code: str):
        """เปลี่ยนโค้ดสำหรับด่านที่ระบุ (เปลี่ยนได้อิสระตราบใดที่ด่านนั้นยังไม่เปิดรันอยู่)"""
        with self._lock:
            clean = code.strip()
            if clean:
                self.checkpoint_codes[cp_index] = clean
                if cp_index == self.active_checkpoint and not self.is_active:
                    self.current_code = clean
        self.config_changed.emit()

    def get_checkpoint_code(self, cp_index: int) -> str:
        """ดึงโค้ดของด่านที่ระบุ"""
        with self._lock:
            return self.checkpoint_codes.get(cp_index, f"#join{cp_index}" if cp_index > 1 else "#join")

    def start_checkpoint(self, cp_index: int, code: str, duration_sec: int) -> bool:
        """เปิดรับโค้ดและเริ่มรอบ

        Args:
            cp_index: ด่าน/รอบที่ต้องการเปิด
            code: โค้ดที่ต้องพิมพ์
            duration_sec: ระยะเวลา (วินาที) โดย 0 = ไม่มีกำหนด (ปิดเอง)
        """
        with self._lock:
            self._timer.stop()
            self.active_checkpoint = cp_index
            self.current_code = code.strip()
            self.checkpoint_codes[cp_index] = self.current_code
            self.duration_sec = max(0, int(duration_sec))

            if not self.current_code:
                return False

            self.is_active = True
            self.start_time = time.time()
            if self.duration_sec > 0:
                self.end_time = self.start_time + self.duration_sec
            else:
                self.end_time = 0.0  # ไม่มีกำหนด

            round_p = len([p for p in self.participants.values() if cp_index in p.checkins])

        self.checkpoint_started.emit(self.active_checkpoint, self.current_code, self.duration_sec)

        # ส่ง tick เริ่มต้นทันทีเพื่อให้ Overlay ได้รับข้อมูลทันทีโดยไม่ต้องรอรอบ 250ms
        if self.duration_sec > 0:
            self.checkpoint_tick.emit(float(self.duration_sec), round_p)
        else:
            self.checkpoint_tick.emit(0.0, round_p)

        self._timer.start()
        return True

    def stop_checkpoint(self):
        """ปิดรับโค้ดทันที"""
        with self._lock:
            self._timer.stop()
            if not self.is_active:
                return
            self.is_active = False
            cp_idx = self.active_checkpoint
            total = len([p for p in self.participants.values() if cp_idx in p.checkins])

        self.checkpoint_ended.emit(cp_idx, total)

    def is_checkpoint_active(self) -> bool:
        """ตรวจสอบว่าขณะนี้กำลังเปิดรับโค้ดอยู่หรือไม่"""
        with self._lock:
            if not self.is_active:
                return False
            # ถ้ามีกำหนดเวลา แล้วเกินเวลา
            if self.duration_sec > 0:
                now = time.time()
                if now > self.end_time:
                    self.is_active = False
                    self._timer.stop()
                    cp_idx = self.active_checkpoint
                    total = len([p for p in self.participants.values() if cp_idx in p.checkins])
                    self.checkpoint_ended.emit(cp_idx, total)
                    return False
            return True

    def get_remaining_sec(self) -> float:
        """เวลาที่เหลืออยู่ในรอบปัจจุบัน (วินาที) หรือ 0 ถ้าไม่มีกำหนด"""
        with self._lock:
            if not self.is_active or self.duration_sec == 0:
                return 0.0
            return max(0.0, self.end_time - time.time())

    def try_checkin(self, platform: str, author: str, text: str, avatar: str = "") -> bool:
        """ตรวจสอบข้อความแชท หากตรงกับโค้ดจะบันทึกสิทธิ์และคืนค่า True (เพื่อสั่ง Mute TTS)"""
        if not text or not author:
            return False

        if not self.is_checkpoint_active():
            return False

        clean_text = text.strip()
        clean_code = self.current_code.strip()

        # ตรวจสอบการพิมพ์โค้ดอย่างยืดหยุ่น:
        # 1. ตรงกันเป๊ะทุกตัวอักษร (case-insensitive) เช่น !join, #join, join
        # 2. ปลดเครื่องหมาย # หรือ ! ออกจากหัวข้อความ แล้วตรวจเทียบเนื้อหาคำ (core word)
        #    ทำให้ผู้ชมพิมพ์ "#join", "!join", หรือ "join" ก็สามารถเข้าร่วมกิจกรรมได้สำเร็จทันที
        core_text = clean_text.lstrip("#!").strip().lower()
        core_code = clean_code.lstrip("#!").strip().lower()
        is_matched = (clean_text.lower() == clean_code.lower()) or (bool(core_code) and core_text == core_code)

        if not is_matched:
            return False

        with self._lock:
            key = f"{platform.lower()}:{author.lower()}"
            participant = self.participants.get(key)
            if participant is None:
                participant = Participant(
                    author=author,
                    platform=platform,
                    avatar=avatar,
                    checkins={self.active_checkpoint},
                    first_seen=time.time(),
                    last_seen=time.time(),
                )
                self.participants[key] = participant
            else:
                participant.checkins.add(self.active_checkpoint)
                participant.last_seen = time.time()
                if avatar and not participant.avatar:
                    participant.avatar = avatar

        self.participant_added.emit(participant, self.active_checkpoint)
        return True

    def get_tier_groups(self) -> Dict[str, List[Participant]]:
        """จัดกลุ่มผู้เข้าร่วมตามระดับ Tier ที่คำนวณแบบยืดหยุ่นตาม total_checkpoints
        รวมถึงจัดกลุ่มตามรายรอบ (cp_{i}) เพื่อให้สุ่มรางวัลแยกตามรอบกิจกรรมได้
        """
        with self._lock:
            all_list = list(self.participants.values())
            tot = self.total_checkpoints

        groups: Dict[str, List[Participant]] = {
            "all": all_list,
        }

        # กลุ่มแยกตามรายรอบกิจกรรม (กรณีของรางวัลคนละแบบ สุ่มแยกตามรอบ)
        for i in range(1, tot + 1):
            groups[f"cp_{i}"] = [p for p in all_list if i in p.checkins]

        if tot <= 1:
            groups["tier_1"] = all_list
            return groups

        for i in range(1, tot + 1):
            groups[f"tier_{i}"] = []

        for p in all_list:
            t = p.calculate_tier(tot)
            grp_key = f"tier_{t}"
            if grp_key in groups:
                groups[grp_key].append(p)
            else:
                groups["tier_1"].append(p)

        return groups

    def get_participant_counts(self) -> Dict[str, int]:
        """ดึงสถิติจำนวนคนในแต่ละด่านและแต่ละกลุ่ม"""
        groups = self.get_tier_groups()
        counts: Dict[str, int] = {
            "all": len(groups.get("all", [])),
        }
        for k, v in groups.items():
            counts[k] = len(v)

        with self._lock:
            for i in range(1, self.total_checkpoints + 1):
                counts[f"cp{i}"] = len([p for p in self.participants.values() if i in p.checkins])

        return counts

    def pick_random_winner(self, group_key: str = "all", exclude_previous: bool = True) -> Optional[Participant]:
        """สุ่มเลือกผู้โชคดี 1 คนจากกลุ่มที่กำหนด"""
        groups = self.get_tier_groups()
        pool = groups.get(group_key, groups.get("all", []))

        with self._lock:
            if exclude_previous:
                previous_authors = {w.author.lower() for w in self.winners_history}
                pool = [p for p in pool if p.author.lower() not in previous_authors]

            if not pool:
                return None

            return random.choice(pool)

    def record_winner(self, participant: Participant, prize: str, tier_label: str):
        """บันทึกผู้ชนะลงประวัติรางวัล"""
        record = WinnerRecord(
            author=participant.author,
            platform=participant.platform,
            prize=prize,
            tier_label=tier_label,
            timestamp=time.time(),
        )
        with self._lock:
            self.winners_history.append(record)

        self.winner_picked.emit(participant, prize, tier_label)

    def export_csv(self, file_path: str) -> bool:
        """ส่งออกรายชื่อผู้เข้าร่วมทั้งหมดเป็นไฟล์ CSV (UTF-8 BOM สำหรับเปิดใน Excel สบายๆ)"""
        with self._lock:
            all_list = list(self.participants.values())
            tot = self.total_checkpoints

        try:
            # ใช้ utf-8-sig เพื่อให้ Excel เปิดภาษาไทยได้คมชัดไม่เพี้ยน
            with open(file_path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)

                # Header columns
                headers = ["ลำดับ", "ชื่อผู้ชม (Username)", "แพลตฟอร์ม"]
                if tot > 1:
                    for i in range(1, tot + 1):
                        cp_label = self.get_checkpoint_name(i)
                        headers.append(f"{cp_label} ({self.checkpoint_codes.get(i, '')})")
                    headers.extend(["จำนวนรอบที่ผ่าน", "สถานะสิทธิ์", "เวลาเข้าร่วมครั้งแรก"])
                else:
                    cp_label = self.get_checkpoint_name(1)
                    headers.extend([f"สถานะเข้าร่วม ({cp_label})", "เวลาเข้าร่วม"])

                writer.writerow(headers)

                for idx, p in enumerate(all_list, start=1):
                    first_seen_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(p.first_seen))
                    row = [idx, p.author, p.platform.capitalize()]

                    if tot > 1:
                        for i in range(1, tot + 1):
                            row.append("ผ่าน ✓" if i in p.checkins else "-")
                        status_label = "ผ่านครบทุกรอบ" if len(p.checkins) >= tot else f"ผ่าน {len(p.checkins)}/{tot} รอบ"
                        row.extend([f"{len(p.checkins)}/{tot}", status_label, first_seen_str])
                    else:
                        row.extend(["ผ่าน ✓" if 1 in p.checkins else "-", first_seen_str])

                    writer.writerow(row)

                # สรุปผู้ได้รับรางวัลท้ายตาราง
                if self.winners_history:
                    writer.writerow([])
                    writer.writerow(["=== สรุปทำเนียบผู้ได้รับรางวัล ==="])
                    writer.writerow(["ลำดับ", "ผู้โชคดี", "แพลตฟอร์ม", "ของรางวัล", "เงื่อนไข / สิทธิ์", "เวลาที่ได้รับ"])
                    for widx, w in enumerate(self.winners_history, start=1):
                        w_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(w.timestamp))
                        writer.writerow([widx, w.author, w.platform.capitalize(), w_time])

            return True
        except Exception as e:
            print(f"Export CSV error: {e}")
            return False

    def export_winners_csv(self, file_path: str) -> bool:
        """Export เฉพาะทำเนียบผู้ได้รับรางวัลทั้งหมด (Excel CSV UTF-8 BOM)"""
        try:
            with self._lock:
                winners = list(self.winners_history)

            with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["ลำดับ", "ชื่อผู้โชคดี", "แพลตฟอร์ม", "ของรางวัลที่ได้รับ", "เงื่อนไข / ระดับสิทธิ์", "วัน-เวลาที่ได้รับรางวัล"])
                for widx, w in enumerate(winners, start=1):
                    w_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(w.timestamp))
                    writer.writerow([widx, w.author, w.platform.capitalize(), w_time])

            return True
        except Exception as e:
            print(f"Export winners CSV error: {e}")
            return False

    def clear_all_data(self):
        """ล้างข้อมูลกิจกรรมทั้งหมดสำหรับเริ่มใหม่"""
        with self._lock:
            self.is_active = False
            self.participants.clear()
            self.winners_history.clear()
        self.data_cleared.emit()

    def broadcast_draw_start(self, prize: str, tier_label: str, candidates: List[str], winner_name: str = ""):
        """ส่งสัญญาณเริ่มสุ่ม Slot Machine ไปยัง OBS Overlay พร้อม candidates และ winner_name"""
        self._last_draw_candidates = list(candidates or [])
        self._last_draw_winner_name = str(winner_name or "")
        self._last_draw_prize = str(prize or "")
        self._last_draw_tier = str(tier_label or "")
        self.draw_started.emit(prize, tier_label, candidates, self._last_draw_winner_name)

    def broadcast_draw_winner(self, participant: Participant, prize: str, tier_label: str):
        """ส่งสัญญาณผู้ชนะไปยัง OBS Overlay"""
        if participant:
            self._last_draw_winner_name = getattr(participant, "author", "")
        self.draw_winner_shown.emit(participant, prize, tier_label)

    def broadcast_draw_reset(self):
        """ส่งสัญญาณปิด/ซ่อนหน้าต่างสุ่มบน OBS Overlay"""
        self.draw_reset.emit()

    def trigger_preview(self, payload: Optional[dict] = None):
        """ส่งสัญญาณทดสอบแสดงผลบน OBS Overlay"""
        self.preview_requested.emit(payload or {})

    def trigger_draw_preview(self, style: Optional[str] = None):
        """ส่งสัญญาณทดสอบแสดงผลเวทีสุ่มขึ้น OBS Overlay ทันที"""
        st = style or self.draw_animation_style
        candidates = ["LuckyViewer_01", "CatFan_99", "StreamerTH", "SuperChatPro", "GachaLover"]
        self.preview_requested.emit({
            "action": "draw_preview",
            "style": st,
            "winner": "🎉 @LuckyViewer_01 🎉",
            "candidates": candidates,
        })

    def update_overlay_settings(self, **kwargs):
        """อัปเดตการตั้งค่าการแสดงผลบน OBS Overlay"""
        with self._lock:
            if "custom_image_path" in kwargs:
                kwargs["overlay_image_path"] = kwargs.pop("custom_image_path")
            for k, v in kwargs.items():
                if hasattr(self, k):
                    setattr(self, k, v)
        self.config_changed.emit()

    def get_current_state(self) -> dict:
        """ดึงสถานะปัจจุบันของ Giveaway สำหรับให้ OBS Browser Source ดึงค่าตอนเชื่อมต่อครั้งแรก"""
        import os
        with self._lock:
            active = self.is_active
            rem = self.get_remaining_sec()
            counts = self.get_participant_counts()
            cur_cp = self.active_checkpoint
            cp_name = self.get_checkpoint_name(cur_cp)
            has_img = bool(self.overlay_image_path and os.path.exists(self.overlay_image_path))
            return {
                "active": active,
                "cp_index": cur_cp,
                "cp_name": cp_name,
                "checkpoint_names": dict(self.checkpoint_names),
                "code": self.current_code,
                "duration_sec": self.duration_sec,
                "remaining_sec": rem,
                "total_checkpoints": self.total_checkpoints,
                "mode": self.mode,
                "round_participants": counts.get(f"cp{cur_cp}", 0),
                "total_participants": counts.get("all", 0),
                "draw_animation_style": self.draw_animation_style,
                "draw_scale": self.draw_scale,
                "draw_name_size": self.draw_name_size,
                "draw_prize_size": self.draw_prize_size,
                "draw_offset_x": self.draw_offset_x,
                "draw_offset_y": self.draw_offset_y,
                "draw_theme": self.draw_theme,
                "sound_enabled": self.sound_enabled,
                "draw_autohide_sec": self.draw_autohide_sec,
                "overlay_display_mode": self.overlay_display_mode,
                "overlay_has_image": has_img,
                "overlay_position": self.overlay_position,
                "overlay_offset_x": self.overlay_offset_x,
                "overlay_offset_y": self.overlay_offset_y,
                "overlay_scale": self.overlay_scale,
                "overlay_font_size": getattr(self, "overlay_font_size", 100),
                "overlay_image_path": self.overlay_image_path,
                "overlay_anim_in": self.overlay_anim_in,
                "overlay_anim_out": self.overlay_anim_out,
                "overlay_show_progress_bar": self.overlay_show_progress_bar,
                "overlay_show_countdown_border": self.overlay_show_countdown_border,
                "overlay_border_theme": self.overlay_border_theme,
                "overlay_show_toast": self.overlay_show_toast,
                "overlay_show_stats": self.overlay_show_stats,
            }
