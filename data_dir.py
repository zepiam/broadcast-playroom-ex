"""data_dir.py — หา data directory (portable mode)

★ กฎ:
  - PyInstaller exe → โฟลเดอร์ข้าง exe (portable — copy โฟลเดอร์ไปเครื่องใหม่ ข้อมูลตามไปด้วย)
  - Dev mode → ./data/ (ข้าง source code)
  - Fallback → ~/.tts-for-livestream/ (ถ้าหา path ไม่ได้)

★ Migration: ถ้าพบข้อมูลเก่าใน ~/.tts-for-livestream/ จะย้ายมาอัตโนมัติ
"""
import os
import sys
import shutil
import logging

logger = logging.getLogger("data_dir")

_OLD_DIR = os.path.join(os.path.expanduser("~"), ".tts-for-livestream")


def get_data_dir() -> str:
    """คืน path ของ data directory (portable)

    ★ Priority:
      1. exe dir / "data" (PyInstaller frozen)
      2. source dir / "data" (dev)
      3. ~/.tts-for-livestream/ (fallback)
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller exe → โฟลเดอร์ข้าง exe
        base = os.path.dirname(sys.executable)
    else:
        # Dev → โฟลเดอร์ข้าง source
        base = os.path.dirname(os.path.abspath(__file__))

    data_dir = os.path.join(base, "data")

    try:
        os.makedirs(data_dir, exist_ok=True)
    except Exception:
        # ถ้าสร้างไม่ได้ → fallback ใช้ home dir
        return _OLD_DIR

    # ★ Migration: ย้ายข้อมูลเก่าจาก ~/.tts-for-livestream/ → data/ (ครั้งเดียว)
    _migrate_old_data(data_dir)

    return data_dir


def _migrate_old_data(new_dir: str):
    """ย้ายข้อมูลเก่าจาก ~/.tts-for-livestream/ → new_dir (ถ้ายังไม่ได้ย้าย)"""
    if not os.path.isdir(_OLD_DIR):
        return

    # ★ ไฟล์ที่ต้องย้าย
    migrate_files = [
        "settings.json",
        "message_history.json",
        "event_log.json",
        "donate_tracker.json",
        "layout.json",
        "donate_tracker.json",
    ]
    # ★ โฟลเดอร์ที่ต้องย้าย
    migrate_dirs = ["character_images", "emote_cache", "voices"]

    moved = False
    for fname in migrate_files:
        old_path = os.path.join(_OLD_DIR, fname)
        new_path = os.path.join(new_dir, fname)
        if os.path.exists(old_path) and not os.path.exists(new_path):
            try:
                shutil.copy2(old_path, new_path)
                moved = True
                logger.info(f"Migrated {fname} → {new_path}")
            except Exception as e:
                logger.debug(f"Migration {fname}: {e}")

    for dname in migrate_dirs:
        old_path = os.path.join(_OLD_DIR, dname)
        new_path = os.path.join(new_dir, dname)
        if os.path.isdir(old_path) and not os.path.isdir(new_path):
            try:
                shutil.copytree(old_path, new_path)
                moved = True
                logger.info(f"Migrated {dname}/ → {new_path}")
            except Exception as e:
                logger.debug(f"Migration {dname}/: {e}")

    # ★ สร้าง marker ว่าย้ายแล้ว (กันย้ายซ้ำ)
    marker = os.path.join(new_dir, ".migrated")
    if moved and not os.path.exists(marker):
        try:
            with open(marker, 'w') as f:
                f.write("1")
        except Exception:
            pass
