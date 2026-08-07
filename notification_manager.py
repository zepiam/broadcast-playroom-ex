"""notification_manager.py — donate/sub/raid → เล่นเสียง + TTS (per-platform)

เมื่อ chat client ส่ง event พิเศษ (bits/sub/raid/SuperChat/gift/membership):
  1. เล่นไฟล์เสียง notification (เช่น sounds/donate.mp3) — แยกตาม platform
  2. enqueue ข้อความ TTS (เช่น "ขอบคุณ X ที่โดเนท 100 บิท")
     กลับเข้า ChatPipeline เพื่อให้อยู่ในลำดับที่ถูกต้อง

การออกแบบ per-platform:
  - แต่ละ platform มีชุดเสียงของตัวเอง (Twitch sub ≠ YouTube membership ≠ KICK subgift)
  - settings.notifications = {platform: {notif_key: {sound_path, volume}}}
  - EVENT_MAP[(platform, event)] → notif_key (lookup ที่ handle time)

การใช้งาน:
    mgr = NotificationManager(pipeline)
    mgr.update_platform_config("twitch", {"donate": {"sound_path": "...", "volume": 0.8}, ...})
    # ใน callback ของ chat client:
    mgr.handle(msg)  # เลือก action ตาม (platform, event)
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from chat_twitch import ChatMessage


# ---------------------------------------------------------------------- #
# Per-platform notification config
# ---------------------------------------------------------------------- #
@dataclass
class NotificationSound:
    """ไฟล์เสียงสำหรับ 1 event type"""

    sound_path: str = ""
    volume: float = 0.8  # 0..1


# event types ที่แต่ละ platform ส่งได้ (notif_key → ใช้ใน settings + UI)
# เป็น source of truth สำหรับ UI — แต่ละ platform แสดงเฉพาะที่ส่งได้จริง
PLATFORM_NOTIF_EVENTS = {
    "twitch": ["donate", "sub", "subgift", "raid"],
    "youtube": ["superchat", "membership"],
    "mylive": [],
    "tiktok": ["gift", "follow", "share", "like", "join"],
    "kick": ["subgift"],
}

# label แสดงผลสำหรับแต่ละ notif_key (ใช้ใน UI)
NOTIF_LABELS = {
    "donate": "💰 Donate",
    "sub": "⭐ Sub",
    "subgift": "🎁 Subgift",
    "raid": "🎯 Raid",
    "superchat": "💎 SuperChat",
    "membership": "🎖️ Membership",
    "gift": "🎁 Gift",
}

# EVENT_MAP — (platform, event) → notif_key
# ใช้ค้นตอน handle(msg) ว่า event นี้ของ platform นี้แมปไป notif_key อะไร
# ถ้า event ไม่อยู่ใน map → จะไป pipeline.enqueue ตรงๆ (ข้าม read_event_text check!)
EVENT_MAP = {
    # Twitch
    ("twitch", "bits"):      "donate",
    ("twitch", "sub"):       "sub",
    ("twitch", "resub"):     "sub",
    ("twitch", "subgift"):   "subgift",
    ("twitch", "raid"):      "raid",
    # YouTube
    ("youtube", "superchat"): "superchat",
    ("youtube", "sub"):       "membership",
    ("youtube", "membership"):"membership",
    # TikTok
    ("tiktok", "gift"):      "gift",
    ("tiktok", "follow"):    "follow",
    ("tiktok", "share"):     "share",
    ("tiktok", "like"):      "like",
    ("tiktok", "join"):      "join",
    # KICK
    ("kick", "subgift"):     "subgift",
    # Generic fallback — ทุก platform + event พิเศษ → เข้า notification (เคารพ read_event_text)
    ("twitch", "redeem"):    "redeem",
}

# TTS announcement toggles (read_* ใช้ร่วมกันข้าม platform ตาม category)
# category = กลุ่มของ notif_key (donate-like / sub-like / raid)
NOTIF_CATEGORY = {
    "donate": "donate", "superchat": "donate", "gift": "donate",
    "sub": "sub", "membership": "sub", "subgift": "sub",
    "raid": "raid",
    "follow": "other", "share": "other", "like": "other", "join": "other", "redeem": "other",
}


@dataclass
class NotificationConfig:
    """ตั้งค่า notification ทั้งหมด — per-platform + global toggles

    platform_sounds: {platform: {notif_key: NotificationSound}}
    read_donate/read_sub/read_raid: TTS announcement toggles (global)
    min_interval: rate limit ระหว่างเสียงเดียวกัน
    """

    # เสียงแยกตาม platform + notif_key
    platform_sounds: dict = field(default_factory=dict)
    # เปิด/ปิด TTS announcement (global ข้าม platform — ตาม category)
    read_donate: bool = True
    read_sub: bool = True
    read_raid: bool = True
    read_event_text: bool = True  # อ่านข้อความ event (ปิด = เล่นแค่เสียง notification)
    # ระยะห่างขั้นต่ำระหว่างเสียงเดียวกัน (วินาที) กัน spam
    min_interval: float = 5.0

    def get_sound(self, platform: str, notif_key: str) -> NotificationSound:
        """ดึง NotificationSound ของ platform + notif_key (default = empty)"""
        plat = self.platform_sounds.get(platform, {})
        data = plat.get(notif_key, {})
        if isinstance(data, NotificationSound):
            return data
        if isinstance(data, dict):
            return NotificationSound(
                sound_path=data.get("sound_path", ""),
                volume=float(data.get("volume", 0.8)),
            )
        return NotificationSound()

    def set_sound(self, platform: str, notif_key: str,
                  sound_path: str = "", volume: float = 0.8) -> None:
        """ตั้งเสียงของ platform + notif_key"""
        plat = self.platform_sounds.setdefault(platform, {})
        plat[notif_key] = NotificationSound(
            sound_path=sound_path, volume=float(volume),
        )

    def to_dict(self) -> dict:
        """serialize → {platform: {notif_key: {sound_path, volume}}} + global toggles"""
        out = {}
        for platform, sounds in self.platform_sounds.items():
            plat_out = {}
            for key, snd in sounds.items():
                if isinstance(snd, NotificationSound):
                    plat_out[key] = {"sound_path": snd.sound_path, "volume": snd.volume}
                elif isinstance(snd, dict):
                    plat_out[key] = {
                        "sound_path": snd.get("sound_path", ""),
                        "volume": float(snd.get("volume", 0.8)),
                    }
            if plat_out:
                out[platform] = plat_out
        # global toggles (ต้องเก็บด้วย ไม่งั้นหายตอน save/load)
        out["read_donate"] = self.read_donate
        out["read_sub"] = self.read_sub
        out["read_raid"] = self.read_raid
        out["read_event_text"] = self.read_event_text
        out["min_interval"] = self.min_interval
        return out

    @classmethod
    def from_dict(cls, data: dict) -> "NotificationConfig":
        """deserialize — ยอมรับ format ใหม่ {platform: {key: {sound_path, volume}}}
        และ format เก่า (flat: {donate: {...}, sub: {...}, read_donate, min_interval})"""
        cfg = cls()
        if not isinstance(data, dict):
            return cfg
        # format เก่า — flat {donate, sub, subgift, raid, read_*, min_interval}
        # ย้ายไป twitch (เพราะ format เก่ามาจาก Twitch-only era)
        legacy_keys = {"donate", "sub", "subgift", "raid"}
        if any(k in data for k in legacy_keys):
            twitch_sounds = {}
            for k in legacy_keys:
                if k in data and isinstance(data[k], dict):
                    twitch_sounds[k] = {
                        "sound_path": data[k].get("sound_path", ""),
                        "volume": float(data[k].get("volume", 0.8)),
                    }
            if twitch_sounds:
                cfg.platform_sounds["twitch"] = twitch_sounds
        # format ใหม่ — per-platform
        for platform, sounds in data.items():
            if platform in legacy_keys or platform in ("read_donate", "read_sub", "read_raid", "read_event_text", "min_interval"):
                continue  # skip non-platform keys
            if not isinstance(sounds, dict):
                continue
            plat_out = {}
            for key, snd in sounds.items():
                if isinstance(snd, dict):
                    plat_out[key] = {
                        "sound_path": snd.get("sound_path", ""),
                        "volume": float(snd.get("volume", 0.8)),
                    }
                elif isinstance(snd, NotificationSound):
                    plat_out[key] = {"sound_path": snd.sound_path, "volume": snd.volume}
            if plat_out:
                # merge (ถ้ามี twitch จาก legacy แล้ว → เก็บทั้งคู่)
                existing = cfg.platform_sounds.get(platform, {})
                existing.update(plat_out)
                cfg.platform_sounds[platform] = existing
        # global toggles
        cfg.read_donate = bool(data.get("read_donate", True))
        cfg.read_sub = bool(data.get("read_sub", True))
        cfg.read_raid = bool(data.get("read_raid", True))
        cfg.read_event_text = bool(data.get("read_event_text", True))
        cfg.min_interval = float(data.get("min_interval", 5.0))
        return cfg


# ---------------------------------------------------------------------- #
# Notification manager
# ---------------------------------------------------------------------- #
class NotificationManager:
    """จัดการ donate/sub/raid → sound + TTS (per-platform)"""

    def __init__(self, pipeline, config: Optional[NotificationConfig] = None) -> None:
        # pipeline = ChatPipeline (มี method _play_sound_blocking + enqueue)
        self.pipeline = pipeline
        self.config = config or NotificationConfig()
        # rate limit per (platform, notif_key)
        self._last_play_time: dict[str, float] = {}

    def update_config(self, config: NotificationConfig) -> None:
        self.config = config

    def update_platform_config(self, platform: str, sounds: dict) -> None:
        """อัปเดตเสียงของ platform หนึ่ง (sounds = {notif_key: {sound_path, volume}})"""
        # merge เข้า platform_sounds ที่มีอยู่
        existing = self.config.platform_sounds.get(platform, {})
        for key, snd in sounds.items():
            if isinstance(snd, dict):
                existing[key] = {
                    "sound_path": snd.get("sound_path", ""),
                    "volume": float(snd.get("volume", 0.8)),
                }
            elif isinstance(snd, NotificationSound):
                existing[key] = {"sound_path": snd.sound_path, "volume": snd.volume}
        self.config.platform_sounds[platform] = existing

    # ------------------------------------------------------------------ #
    # Handle message from chat client
    # ------------------------------------------------------------------ #
    def handle(self, msg: ChatMessage) -> bool:
        """เรียกจาก poll loop — ทุก event พิเศษเข้าที่นี่

        Returns True เสมอ (จัดการแล้ว — เล่นเสียง/ไม่เล่น + TTS/ไม่อ่าน)
        """
        notif_key = EVENT_MAP.get((msg.platform, msg.event), msg.event)

        # เล่นไฟล์เสียงของ platform + notif_key นี้
        self._play_sound(msg.platform, notif_key)

        # enqueue TTS announcement (กลับเข้า pipeline)
        category = NOTIF_CATEGORY.get(notif_key, "")
        read_attr = {
            "donate": "read_donate",
            "sub": "read_sub",
            "raid": "read_raid",
        }.get(category)
        should_read = getattr(self.config, read_attr, True) if read_attr else True
        if should_read and getattr(self.config, "read_event_text", True):
            # ใช้ msg.text ที่ normalize แล้ว (จาก _normalize_event_text) ถ้ามี
            # ไม่ต้องสร้างใหม่ — กันอ่านเบิ้บ
            text = msg.text.strip() if msg.text else ""
            if not text:
                text = self._build_tts_text(msg)
            if text:
                announcement = ChatMessage(
                    platform=msg.platform,
                    author=msg.author,
                    text=text,
                    event="message",
                )
                self.pipeline._q.put(announcement)

        return True

    # ------------------------------------------------------------------ #
    # Sound playback
    # ------------------------------------------------------------------ #
    def _play_sound(self, platform: str, notif_key: str) -> None:
        """เล่นไฟล์เสียง notification ของ platform + notif_key (ถ้ามี path)"""
        sound = self.config.get_sound(platform, notif_key)
        if not sound.sound_path:
            return
        if not os.path.exists(sound.sound_path):
            return

        # rate limit — แยกตาม (platform, notif_key) กัน spam
        rl_key = f"{platform}.{notif_key}"
        now = time.time()
        last = self._last_play_time.get(rl_key, 0)
        if now - last < self.config.min_interval:
            return
        self._last_play_time[rl_key] = now

        # เล่นใน thread แยก (ไม่บล็อก callback)
        t = threading.Thread(
            target=self.pipeline._play_sound_blocking,
            args=(sound.sound_path, sound.volume),
            daemon=True,
        )
        t.start()

    # ------------------------------------------------------------------ #
    # TTS text builder
    # ------------------------------------------------------------------ #
    def _build_tts_text(self, msg: ChatMessage) -> str:
        """สร้างข้อความสำหรับ TTS announce — แยกตาม (platform, event)"""
        key = (msg.platform, msg.event)
        author = msg.author
        # Twitch
        if key == ("twitch", "bits"):
            amount = msg.amount or "?"
            base = f"{author} ให้ {amount} บิท"
            if msg.text.strip():
                base += " " + msg.text
            return base
        if key == ("twitch", "sub"):
            base = f"{author} ให้ซับช่อง"
            if msg.text.strip():
                base += " " + msg.text
            return base
        if key == ("twitch", "resub"):
            base = f"{author} ให้ซับต่อเนื่อง"
            if msg.system_text:
                # ดึงเลขเดือนจาก system_text (เช่น "ต่อสับ 12 เดือน")
                import re
                m = re.search(r"(\d+)", msg.system_text)
                if m:
                    base += f" เป็นเดือนที่ {m.group(1)}"
            if msg.text.strip():
                base += " " + msg.text
            return base
        if key == ("twitch", "subgift"):
            # ดึงชื่อผู้รับจาก system_text (เช่น "มอบสับให้ Viewer99")
            import re
            recipient = ""
            if msg.system_text:
                # ลองหาชื่อหลัง "ให้"
                m = re.search(r"ให้\s*(.+)", msg.system_text)
                if m:
                    recipient = m.group(1).strip()
            if recipient:
                return f"{author} แจกซับให้ {recipient}"
            return f"{author} แจกซับ"
        if key == ("twitch", "raid"):
            viewers = msg.amount or "?"
            return f"{author} พาคนบุกช่อง {viewers} คน"
        # YouTube
        if key == ("youtube", "superchat"):
            amt = msg.system_text or (f"{msg.amount}" if msg.amount else "")
            if amt:
                base = f"{author} ให้ซุปเปอร์แชท {amt}"
            else:
                base = f"{author} ให้ซุปเปอร์แชท"
            if msg.text.strip():
                base += " " + msg.text
            return base
        if key in (("youtube", "membership"), ("youtube", "sub")):
            base = f"{author} เข้าร่วมเป็นสมาชิก"
            if msg.text.strip():
                base += " " + msg.text
            return base
        # TikTok
        if key == ("tiktok", "gift"):
            amount = msg.amount or 0
            sys_text = msg.system_text or ""
            if amount > 0:
                return f"{author} แจกซับให้ {amount} คน"
            base = f"{author} {sys_text}" if sys_text else f"{author} ส่งของขวัญ"
            if msg.text.strip():
                base += " " + msg.text
            return base
        if key == ("tiktok", "follow"):
            return f"{author} กดติดตามช่อง"
        if key == ("tiktok", "share"):
            return f"{author} ช่วยโปรโมทช่อง"
        if key == ("tiktok", "like"):
            amount = msg.amount or 1
            return f"{author} ให้ไลค์ ×{amount}"
        if key == ("tiktok", "join"):
            return f"{author} เข้าร่วมเป็นสมาชิก"
        # KICK
        if key == ("kick", "subgift"):
            return f"{author} แจกซับ"

        # fallback generic
        return f"{author} {msg.system_text or msg.event}"


# ---------------------------------------------------------------------- #
# Smoke test
# ---------------------------------------------------------------------- #
if __name__ == "__main__":
    cfg = NotificationConfig()
    cfg.set_sound("twitch", "donate", "sounds/donate.mp3", 0.8)
    cfg.set_sound("youtube", "membership", "sounds/membership.mp3", 0.5)
    cfg.set_sound("kick", "subgift", "sounds/subgift.mp3", 0.7)

    print("get twitch.donate:", cfg.get_sound("twitch", "donate"))
    print("get youtube.membership:", cfg.get_sound("youtube", "membership"))
    print("get kick.subgift:", cfg.get_sound("kick", "subgift"))
    print("get unknown:", cfg.get_sound("tiktok", "nonexistent"))

    # roundtrip
    d = cfg.to_dict()
    print("\nto_dict:", d)
    cfg2 = NotificationConfig.from_dict(d)
    print("roundtrip twitch.donate:", cfg2.get_sound("twitch", "donate"))

    # legacy format migration
    legacy = {
        "donate": {"sound_path": "old_donate.mp3", "volume": 0.9},
        "sub": {"sound_path": "old_sub.mp3"},
        "read_donate": False,
        "min_interval": 3.0,
    }
    cfg3 = NotificationConfig.from_dict(legacy)
    print("\nlegacy migration:")
    print("  twitch.donate:", cfg3.get_sound("twitch", "donate"))
    print("  read_donate:", cfg3.read_donate)
    print("  min_interval:", cfg3.min_interval)

    # EVENT_MAP lookup
    print("\nEVENT_MAP tests:")
    print("  twitch bits →", EVENT_MAP.get(("twitch", "bits")))
    print("  youtube sub →", EVENT_MAP.get(("youtube", "sub")))
    print("  kick subgift →", EVENT_MAP.get(("kick", "subgift")))
    print("  unknown →", EVENT_MAP.get(("foo", "bar")))
    print("OK")
