"""plugin_loader.py — โหลด command plugins จาก plugins/commands/*.yml

Plugin system แบบ config-only (ไม่รัน Python code เพื่อความปลอดภัย)
โหลด YAML → ตรวจ trigger → ตอบกลับด้วย TTS/ข้อความ

การใช้งาน:
    loader = PluginLoader()
    loader.load_all()  # โหลด plugins/commands/*.yml
    response = loader.check_command("!hi", author="MeN9CH")
    if response:
        # ส่งเข้า TTS pipeline
        print(response)
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CommandPlugin:
    """command plugin config (จาก YAML)"""
    name: str = ""
    trigger: str = ""
    description: str = ""
    response_type: str = "text"  # "text" | "overlay"
    response: str = ""
    cooldown: int = 0  # วินาที
    enabled: bool = True
    # runtime
    _last_triggered: dict[str, float] = field(default_factory=dict)  # {author: timestamp}

    def can_trigger(self, author: str) -> bool:
        """เช็ค cooldown — คืน True ถ้ายิงได้"""
        if self.cooldown <= 0:
            return True
        last = self._last_triggered.get(author.lower(), 0)
        return (time.time() - last) >= self.cooldown

    def get_response(self, author: str) -> str:
        """สร้างข้อความตอบกลับ (แทนตัวแปร)"""
        self._last_triggered[author.lower()] = time.time()
        now = time.strftime("%H:%M")
        return (self.response
                .replace("{author}", author)
                .replace("{trigger}", self.trigger)
                .replace("{time}", now))


class PluginLoader:
    """โหลด + จัดการ command plugins"""

    def __init__(self, plugins_dir: str = "") -> None:
        if not plugins_dir:
            # หา plugins/ ข้าง exe หรือข้าง script
            if getattr(__import__('sys'), 'frozen', False):
                base = os.path.dirname(__import__('sys').executable)
            else:
                base = os.path.dirname(os.path.abspath(__file__))
            self._plugins_dir = os.path.join(base, "plugins", "commands")
        else:
            self._plugins_dir = plugins_dir
        self._plugins: dict[str, CommandPlugin] = {}  # {trigger_lower: plugin}
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def plugins(self) -> list[CommandPlugin]:
        return list(self._plugins.values())

    def load_all(self) -> int:
        """โหลด plugins/commands/*.yml ทั้งหมด → คืนจำนวนที่โหลดสำเร็จ"""
        self._plugins.clear()
        if not os.path.isdir(self._plugins_dir):
            self._loaded = True
            return 0
        count = 0
        try:
            import yaml
        except ImportError:
            try:
                import json
                # fallback: ลอง json แทน yaml
                for fname in os.listdir(self._plugins_dir):
                    if fname.endswith(".json"):
                        path = os.path.join(self._plugins_dir, fname)
                        if self._load_json(path):
                            count += 1
                self._loaded = True
                return count
            except Exception:
                self._loaded = True
                return 0
        for fname in os.listdir(self._plugins_dir):
            if not fname.endswith((".yml", ".yaml")):
                continue
            path = os.path.join(self._plugins_dir, fname)
            if self._load_yaml(path, yaml):
                count += 1
        self._loaded = True
        return count

    def _load_yaml(self, path: str, yaml_module) -> bool:
        """โหลด YAML → CommandPlugin"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml_module.safe_load(f) or {}
            return self._register(data)
        except Exception:
            return False

    def _load_json(self, path: str) -> bool:
        """โหลด JSON → CommandPlugin (fallback ถ้าไม่มี yaml)"""
        try:
            import json
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return self._register(data)
        except Exception:
            return False

    def _register(self, data: dict) -> bool:
        """สร้าง CommandPlugin + register"""
        trigger = str(data.get("trigger", "")).strip()
        if not trigger:
            return False
        plugin = CommandPlugin(
            name=str(data.get("name", trigger)),
            trigger=trigger,
            description=str(data.get("description", "")),
            response_type=str(data.get("response_type", "text")),
            response=str(data.get("response", "")),
            cooldown=int(data.get("cooldown", 0)),
            enabled=bool(data.get("enabled", True)),
        )
        if plugin.enabled:
            self._plugins[trigger.lower()] = plugin
        return True

    def check_command(self, text: str, author: str = "ผู้ชม") -> Optional[tuple[str, CommandPlugin]]:
        """ตรวจว่าข้อความเป็นคำสั่ง plugin ไหม

        คืน (response_text, plugin) ถ้า match + ผ่าน cooldown
        คืน None ถ้าไม่ match หรือ cooldown ยังไม่หมด
        """
        if not self._loaded:
            self.load_all()
        text_stripped = text.strip()
        for trigger_lower, plugin in self._plugins.items():
            # match: exact หรือ trigger + space + args
            if text_stripped.lower() == trigger_lower or text_stripped.lower().startswith(trigger_lower + " "):
                if plugin.can_trigger(author):
                    response = plugin.get_response(author)
                    return (response, plugin)
                else:
                    return None  # cooldown ยังไม่หมด
        return None

    def reload(self) -> int:
        """โหลดใหม่ทั้งหมด (หลังแก้ไข YAML)"""
        self._loaded = False
        return self.load_all()


# ====================================================================== #
# Singleton — ใช้ร่วมกันทั้งโปรแกรม
# ====================================================================== #
_loader: Optional[PluginLoader] = None


def get_plugin_loader() -> PluginLoader:
    """คืน singleton PluginLoader"""
    global _loader
    if _loader is None:
        _loader = PluginLoader()
        _loader.load_all()
    return _loader
