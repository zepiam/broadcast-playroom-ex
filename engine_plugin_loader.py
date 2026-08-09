"""engine_plugin_loader.py — TTS/RVC engine plugin system

★ Plugin = โฟลเดอร์ใน engines/ ที่มี plugin.json
★ โหลดทันทีตอนเปิดโปรแกรม (auto-enable)
★ ไม่มี plugin → ใช้ Edge-TTS (base engine)

Plugin structure:
  engines/
  ├── omnivoice/
  │   ├── plugin.json          ← metadata
  │   ├── site-packages/       ← Python packages (torch, omnivoice, ...)
  │   └── files/               ← engine code (omnivoice_engine.py)
  │       └── omnivoice_engine.py
  └── rvc/
      ├── plugin.json
      ├── site-packages/
      └── files/
          └── rvc_engine.py

plugin.json format:
  {
    "id": "omnivoice",
    "name": "OmniVoice TTS",
    "description": "เสียง TTS ออฟไลน์",
    "version": "1.0.0",
    "type": "tts_engine",
    "engine_module": "omnivoice_engine",
    "engine_class": "OmniVoiceEngine",
    "requires_gpu": true,
    "min_disk_gb": 10
  }
"""
from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("engine_plugin_loader")


@dataclass
class EnginePlugin:
    """Plugin metadata + loaded state"""
    id: str
    name: str
    description: str
    version: str
    type: str                    # "tts_engine" | "voice_filter" | "shared"
    engine_module: str = ""
    engine_class: str = ""
    requires_gpu: bool = False
    min_disk_gb: int = 0
    plugin_dir: str = ""         # absolute path
    loaded: bool = False         # import สำเร็จไหม
    error: str = ""              # error message (ถ้า load fail)
    requires: list = None        # list of plugin IDs ที่ต้องโหลดก่อน (เช่น ["_shared"])


def get_engines_dir() -> str:
    """คืน path ของ engines/ folder

    ★ PyInstaller: อยู่ข้าง exe (dist/BroadcastPlayroom_Lite/engines/)
    ★ Dev: อยู่ใน project root
    """
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "engines")


def scan_plugins() -> list[EnginePlugin]:
    """สแกน engines/ folder → คืน list ของ EnginePlugin ที่พบ

    ★ อ่าน plugin.json จากทุก subfolder ใน engines/
    ★ ถ้าโฟลเดอร์ไม่มี plugin.json → ข้าม
    """
    plugins = []
    engines_dir = get_engines_dir()

    if not os.path.isdir(engines_dir):
        logger.info(f"engines/ not found: {engines_dir}")
        return plugins

    try:
        for name in sorted(os.listdir(engines_dir)):
            plugin_path = os.path.join(engines_dir, name)
            if not os.path.isdir(plugin_path):
                continue

            json_path = os.path.join(plugin_path, "plugin.json")
            if not os.path.exists(json_path):
                continue

            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                plugin = EnginePlugin(
                    id=data.get("id", name),
                    name=data.get("name", name),
                    description=data.get("description", ""),
                    version=data.get("version", "0.0.0"),
                    type=data.get("type", "tts_engine"),
                    engine_module=data.get("engine_module", ""),
                    engine_class=data.get("engine_class", ""),
                    requires_gpu=data.get("requires_gpu", False),
                    min_disk_gb=data.get("min_disk_gb", 0),
                    plugin_dir=plugin_path,
                    requires=data.get("requires", []),
                )
                plugins.append(plugin)
                logger.info(f"Plugin found: {plugin.id} ({plugin.name})")
            except Exception as e:
                logger.warning(f"Failed to read {json_path}: {e}")
    except Exception as e:
        logger.error(f"scan_plugins error: {e}")

    return plugins


def load_plugin(plugin: EnginePlugin) -> bool:
    """โหลด plugin → เพิ่ม sys.path + import engine module

    ★ เพิ่ม engines/<id>/site-packages และ engines/<id>/files เข้า sys.path
    ★ import engine module → ถ้าสำเร็จ → plugin.loaded = True

    Returns: True ถ้าโหลดสำเร็จ
    """
    if plugin.loaded:
        return True

    try:
        # ★ เพิ่ม site-packages และ files เข้า sys.path
        site_packages = os.path.join(plugin.plugin_dir, "site-packages")
        files_dir = os.path.join(plugin.plugin_dir, "files")

        if os.path.isdir(site_packages):
            if site_packages not in sys.path:
                sys.path.insert(0, site_packages)
            logger.info(f"Added to sys.path: {site_packages}")

        if os.path.isdir(files_dir):
            if files_dir not in sys.path:
                sys.path.insert(0, files_dir)
            logger.info(f"Added to sys.path: {files_dir}")

        # ★ import engine module (ถ้ามี) — โหลดจาก file path โดยตรง (ไม่ผ่าน PyInstaller)
        if plugin.engine_module:
            try:
                engine_file = os.path.join(files_dir, plugin.engine_module + ".py")
                if os.path.exists(engine_file):
                    # ★ ใช้ spec_from_file_location — โหลดจากไฟล์จริง ไม่ผ่าน frozen module
                    import importlib.util
                    spec = importlib.util.spec_from_file_location(plugin.engine_module, engine_file)
                    mod = importlib.util.module_from_spec(spec)
                    sys.modules[plugin.engine_module] = mod  # ★ cache ไว้ใน sys.modules
                    spec.loader.exec_module(mod)
                    plugin.loaded = True
                    logger.info(f"Plugin loaded: {plugin.id} ({plugin.engine_module}) from {engine_file}")
                else:
                    # ★ fallback: __import__ (สำหรับ Full build ที่ bundle แล้ว)
                    __import__(plugin.engine_module)
                    plugin.loaded = True
                    logger.info(f"Plugin loaded: {plugin.id} ({plugin.engine_module}) via __import__")
            except ImportError as e:
                plugin.error = str(e)
                plugin.loaded = False
                logger.warning(f"Plugin {plugin.id} import failed: {e}")
            except Exception as e:
                plugin.error = str(e)
                plugin.loaded = False
                logger.warning(f"Plugin {plugin.id} load failed: {e}")
        else:
            # ★ plugin ไม่มี engine_module → แค่เพิ่ม sys.path (เช่น rvc มีแค่ packages)
            plugin.loaded = True
            logger.info(f"Plugin loaded (path only): {plugin.id}")

        return plugin.loaded

    except Exception as e:
        plugin.error = str(e)
        plugin.loaded = False
        logger.error(f"load_plugin {plugin.id} error: {e}")
        return False


def get_loaded_plugins() -> list[EnginePlugin]:
    """สแกน + โหลด plugins ทั้งหมด → คืน list ของ EnginePlugin ที่โหลดสำเร็จ

    ★ cache ผลลัพธ์ (เรียกครั้งเดียวตอนเปิดโปรแกรม)
    ★ โหลดลำดับ: lib/ ก่อน (base layer — torch/scipy/soundfile) → แล้วถึง engine plugins
      (เพราะ omnivoice + rvc ใช้ torch ร่วมกันจาก lib/)
    """
    global _cache
    if _cache is not None:
        return _cache

    # ★ 1. โหลด lib/ ก่อนเสมอ (base layer — shared torch/CUDA packages)
    lib_dir = os.path.join(get_engines_dir(), "lib", "site-packages")
    if os.path.isdir(lib_dir):
        if lib_dir not in sys.path:
            sys.path.insert(0, lib_dir)
        logger.info(f"Loaded lib/ (base layer): {lib_dir}")

    # ★ 2. โหลด engine plugins
    plugins = scan_plugins()
    for plugin in plugins:
        load_plugin(plugin)
    _cache = [p for p in plugins if p.loaded]
    return _cache


_cache: Optional[list[EnginePlugin]] = None


def is_plugin_available(plugin_id: str) -> bool:
    """เช็คว่า plugin ติดตั้งและโหลดแล้วไหม

    ★ ใช้สำหรับเช็คก่อนแสดงตัวเลือกใน UI
      เช่น is_plugin_available("omnivoice") → True/False
    """
    plugins = get_loaded_plugins()
    return any(p.id == plugin_id and p.loaded for p in plugins)


def get_plugin_info(plugin_id: str) -> Optional[EnginePlugin]:
    """คืน EnginePlugin info ของ plugin_id (ถ้ามี)"""
    plugins = get_loaded_plugins()
    for p in plugins:
        if p.id == plugin_id:
            return p
    return None


def ensure_engines_dir():
    """สร้าง engines/ folder ถ้ายังไม่มี"""
    engines_dir = get_engines_dir()
    if not os.path.isdir(engines_dir):
        try:
            os.makedirs(engines_dir, exist_ok=True)
            # ★ สร้าง README อธิบายวิธีใช้
            readme_path = os.path.join(engines_dir, "README.txt")
            with open(readme_path, "w", encoding="utf-8") as f:
                f.write(
                    "Engines Folder\n"
                    "=============\n\n"
                    "วาง plugin engine ที่นี่ (เช่น omnivoice/, rvc/)\n\n"
                    "วิธีติดตั้ง plugin:\n"
                    "1. ดาวน์โหลด plugin (เช่น omnivoice.zip)\n"
                    "2. แตกไฟล์ → วางในโฟลเดอร์นี้\n"
                    "3. เปิดโปรแกรมใหม่ → ใช้งานได้ทันที\n"
                )
            logger.info(f"Created engines/ folder: {engines_dir}")
        except Exception as e:
            logger.error(f"Failed to create engines/ folder: {e}")


def reset_cache():
    """reset cache (ใช้ตอนต้องการสแกนใหม่)"""
    global _cache
    _cache = None
