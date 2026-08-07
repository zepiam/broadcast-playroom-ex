"""plugin_api.py — Abstract base classes สำหรับ plugin development

กำหนด interface ที่ plugin ต้อง implement:
- TTSEngine: ลงเสียง TTS แบบกำหนดเอง
- PlatformClient: แพลตฟอร์มแชทใหม่
- CommandHandler: คำสั่งแชทแบบกำหนดเอง (code-based ไม่ใช่ config)

ใช้ในอนาคตเมื่อต้องการสร้าง plugin ที่ซับซ้อนกว่า config-only
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Callable


@dataclass
class PluginInfo:
    """metadata ของ plugin"""
    name: str = ""
    version: str = "1.0.0"
    author: str = ""
    description: str = ""
    plugin_type: str = ""  # "tts" | "platform" | "command"


# ====================================================================== #
# TTSEngine — abstract class สำหรับ TTS engine
# ====================================================================== #
class TTSEngine(ABC):
    """abstract class สำหรับ TTS engine plugin

    การใช้งาน:
        class MyTTSEngine(TTSEngine):
            def synth(self, text, voice):
                # ลงเสียงด้วย API ของคุณ
                return mp3_bytes
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """ชื่อ engine (เช่น 'google_cloud', 'azure')"""
        ...

    @property
    def voices(self) -> list[str]:
        """รายชื่อ voice ที่รองรับ (override ได้)"""
        return ["default"]

    @abstractmethod
    def synth(self, text: str, voice: str = "default", rate: int = 0) -> bytes:
        """ลงเสียง text → คืน MP3 bytes"""
        ...

    def cleanup(self) -> None:
        """ทำความสะอาดก่อนปิด (override ได้)"""
        pass


# ====================================================================== #
# PlatformClient — abstract class สำหรับ platform client
# ====================================================================== #
class PlatformClient(ABC):
    """abstract class สำหรับ platform plugin (เช่น Discord, Facebook Live)

    การใช้งาน:
        class DiscordClient(PlatformClient):
            def connect(self, target):
                # เชื่อมต่อ Discord
                ...
            def disconnect(self):
                ...
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """ชื่อ platform (เช่น 'discord')"""
        ...

    @property
    @abstractmethod
    def label(self) -> str:
        """ชื่อที่แสดงใน UI (เช่น 'Discord')"""
        ...

    @abstractmethod
    def connect(self, target: str) -> bool:
        """เชื่อมต่อ platform → คืน True ถ้าสำเร็จ"""
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """ยกเลิกการเชื่อมต่อ"""
        ...

    @property
    def is_connected(self) -> bool:
        """สถานะการเชื่อมต่อ (override ได้)"""
        return False


# ====================================================================== #
# CommandHandler — abstract class สำหรับ code-based command
# ====================================================================== #
class CommandHandler(ABC):
    """abstract class สำหรับ command plugin แบบ code (ไม่ใช่ config)

    สำหรับ command ที่ต้องการ logic ซับซ้อน (API call, database, etc.)

    การใช้งาน:
        class WeatherCommand(CommandHandler):
            trigger = "!weather"
            def handle(self, args, author):
                city = args or "Bangkok"
                temp = requests.get(f"...{city}").json()["temp"]
                return f"อุณหภูมิที่ {city} คือ {temp}°C"
    """

    @property
    @abstractmethod
    def trigger(self) -> str:
        """คำสั่งที่เรียก (เช่น '!weather')"""
        ...

    @abstractmethod
    def handle(self, args: str, author: str) -> Optional[str]:
        """ประมวลผลคำสั่ง → คืนข้อความตอบกลับ (หรือ None ถ้าไม่ตอบ)

        Args:
            args: ส่วนที่อยู่หลัง trigger (เช่น "!weather bangkok" → args="bangkok")
            author: ชื่อคนพิมพ์
        """
        ...

    @property
    def cooldown(self) -> int:
        """คูลดาวน์เป็นวินาที (override ได้)"""
        return 0
