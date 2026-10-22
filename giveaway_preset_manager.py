# -*- coding: utf-8 -*-
"""
giveaway_preset_manager.py
ระบบจัดการ Preset คนเข้าร่วม และ ข้อมูลของรางวัล สำหรับ Giveaway Tool 2.0
"""
import os
import json
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

DEFAULT_PARTICIPANT_PRESETS: List[Dict[str, Any]] = [
    {
        "id": "preset_single",
        "name": "🎯 กิจกรรมสุ่มรางวัลรอบเดียว (ค่าเริ่มต้น)",
        "mode": "single",
        "code": "#join",
        "duration_sec": 300,
        "overlay_display_mode": "banner",
        "overlay_scale": 100,
        "overlay_font_size": 100,
        "overlay_offset_x": 0,
        "overlay_offset_y": 0,
        "overlay_anchor": "bottom-center",
        "anim_in": "Slide From Bottom",
        "anim_out": "Slide To Bottom",
        "custom_image_path": ""
    },
    {
        "id": "preset_multi3",
        "name": "🏆 กิจกรรมแจกใหญ่ 3 ด่านสะสมแต้ม",
        "mode": "multi",
        "total_checkpoints": 3,
        "checkpoints": [
            {"index": 1, "name": "รอบที่ 1", "code": "#join1", "duration_sec": 300},
            {"index": 2, "name": "รอบที่ 2", "code": "#join2", "duration_sec": 300},
            {"index": 3, "name": "รอบที่ 3", "code": "#join3", "duration_sec": 300}
        ],
        "overlay_display_mode": "banner",
        "overlay_scale": 100,
        "overlay_font_size": 100,
        "overlay_offset_x": 0,
        "overlay_offset_y": 0,
        "overlay_anchor": "bottom-center",
        "anim_in": "Slide From Bottom",
        "anim_out": "Slide To Bottom",
        "custom_image_path": ""
    }
]

DEFAULT_PRIZE_SETS: List[Dict[str, Any]] = [
    {
        "id": "prize_set_multi3",
        "name": "ชุดของรางวัลแจกใหญ่ 3 ด่าน (9 รางวัล)",
        "linked_participant_preset_id": "preset_multi3",
        "tiers": [
            {
                "tier_name": "🏆 รางวัลใหญ่",
                "prize_name": "บัตรของขวัญ 1,000 บาท",
                "target_group": "3_points",
                "target_group_label": "ผู้มี 3 คะแนน (ครบทุกรอบ)",
                "quantity": 1
            },
            {
                "tier_name": "🥈 รางวัลรอง",
                "prize_name": "เสื้อยืด Limited Edition",
                "target_group": "2_points",
                "target_group_label": "ผู้มี 2 คะแนน (เข้าร่วมไม่ครบ)",
                "quantity": 3
            },
            {
                "tier_name": "🥉 รางวัลเล็ก",
                "prize_name": "โค้ดไอเทมเกม 100 บาท",
                "target_group": "1_point",
                "target_group_label": "ผู้มี 1 คะแนน (เข้าร่วมครั้งเดียว)",
                "quantity": 5
            }
        ],
        "last_drawn_at": ""
    },
    {
        "id": "prize_set_single",
        "name": "ชุดของรางวัลสุ่มรอบเดียว",
        "linked_participant_preset_id": "preset_single",
        "tiers": [
            {
                "tier_name": "🎁 รางวัลใหญ่",
                "prize_name": "ไอดีเกม VIP",
                "target_group": "all",
                "target_group_label": "ผู้เข้าร่วมทุกคน",
                "quantity": 1
            }
        ],
        "last_drawn_at": ""
    }
]

class GiveawayPresetManager:
    """จัดการการบันทึกและโหลด Preset คนเข้าร่วม และ ชุดของรางวัล"""
    def __init__(self, data_dir: Optional[str] = None):
        if not data_dir:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            data_dir = os.path.join(base_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        self.filepath = os.path.join(data_dir, "giveaway_presets.json")
        self.participant_presets: List[Dict[str, Any]] = []
        self.prize_sets: List[Dict[str, Any]] = []
        self.load()

    def load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.participant_presets = data.get("participant_presets", [])
                    self.prize_sets = data.get("prize_sets", [])
            except Exception as e:
                logger.error(f"Failed to load giveaway presets: {e}")
                self.participant_presets = list(DEFAULT_PARTICIPANT_PRESETS)
                self.prize_sets = list(DEFAULT_PRIZE_SETS)
        else:
            self.participant_presets = list(DEFAULT_PARTICIPANT_PRESETS)
            self.prize_sets = list(DEFAULT_PRIZE_SETS)
            self.save()

        # Fallback if empty
        if not self.participant_presets:
            self.participant_presets = list(DEFAULT_PARTICIPANT_PRESETS)
        if not self.prize_sets:
            self.prize_sets = list(DEFAULT_PRIZE_SETS)

    def save(self):
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump({
                    "participant_presets": self.participant_presets,
                    "prize_sets": self.prize_sets
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save giveaway presets: {e}")

    # --- Participant Presets ---
    def get_participant_presets(self) -> List[Dict[str, Any]]:
        return self.participant_presets

    def get_participant_preset(self, preset_id: str) -> Optional[Dict[str, Any]]:
        for p in self.participant_presets:
            if p.get("id") == preset_id:
                return p
        return None

    def save_participant_preset(self, preset_data: Dict[str, Any]):
        p_id = preset_data.get("id")
        if not p_id:
            import time
            preset_data["id"] = f"preset_{int(time.time())}"
        
        updated = False
        for i, p in enumerate(self.participant_presets):
            if p.get("id") == preset_data["id"]:
                self.participant_presets[i] = preset_data
                updated = True
                break
        if not updated:
            self.participant_presets.append(preset_data)
        self.save()

    def delete_participant_preset(self, preset_id: str) -> bool:
        initial_len = len(self.participant_presets)
        self.participant_presets = [p for p in self.participant_presets if p.get("id") != preset_id]
        if len(self.participant_presets) < initial_len:
            self.save()
            return True
        return False

    # --- Prize Sets ---
    def get_prize_sets(self) -> List[Dict[str, Any]]:
        return self.prize_sets

    def get_prize_set(self, prize_id: str) -> Optional[Dict[str, Any]]:
        for p in self.prize_sets:
            if p.get("id") == prize_id:
                return p
        return None

    def get_prize_sets_for_participant_preset(self, participant_preset_id: str) -> List[Dict[str, Any]]:
        return [p for p in self.prize_sets if p.get("linked_participant_preset_id") == participant_preset_id]

    def save_prize_set(self, prize_data: Dict[str, Any]):
        p_id = prize_data.get("id")
        if not p_id:
            import time
            prize_data["id"] = f"prize_{int(time.time())}"

        updated = False
        for i, p in enumerate(self.prize_sets):
            if p.get("id") == prize_data["id"]:
                self.prize_sets[i] = prize_data
                updated = True
                break
        if not updated:
            self.prize_sets.append(prize_data)
        self.save()

    def delete_prize_set(self, prize_id: str) -> bool:
        initial_len = len(self.prize_sets)
        self.prize_sets = [p for p in self.prize_sets if p.get("id") != prize_id]
        if len(self.prize_sets) < initial_len:
            self.save()
            return True
        return False
