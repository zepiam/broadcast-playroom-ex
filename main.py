"""main.py — Entry point สำหรับ Broadcast Playroom v2 (PySide6)

ทำงาน:
1. สร้าง QApplication
2. แสดง splash screen
3. โหลด app (settings, fonts, theme)
4. แสดง main window
"""
import sys
import os
import logging

# ═══ Logging setup (before anything else) ═══
def setup_logging():
    log_dir = os.path.join(os.path.expanduser("~"), ".tts-for-livestream")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "app_v2.log")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )

setup_logging()
logger = logging.getLogger("main")

import time as _time
_BOOT_T0 = _time.perf_counter()
def _boot_log(msg):
    """log เวลาตั้งแต่กดเปิดโปรแกรม (ms) — debug startup performance"""
    logger.info(f"boot[{(_time.perf_counter() - _BOOT_T0) * 1000:.0f}ms] {msg}")


# ═══ PyInstaller fix: stub missing package metadata (torchcodec) ═══
# transformers/audio_utils.py อ่าน importlib.metadata.version("torchcodec")
# แต่ torchcodec ไม่ได้ติดตั้ง → PackageNotFoundError → cascade fail
# แก้: stub metadata ให้คืนค่าเริ่มต้นสำหรับ package ที่ไม่มี
# ★ ต้องทำก่อน transformers import → เก็บไว้ก่อน splash (เบา ทำงานทันที)
def _stub_importlib_metadata():
    try:
        import importlib.metadata as _meta
        _orig_version = _meta.version
        _orig_distribution = _meta.distribution
        def _safe_version(name):
            try:
                return _orig_version(name)
            except _meta.PackageNotFoundError:
                # stub เฉพาะ package ที่รู้ว่าไม่จำเป็น (torchcodec) — อย่างอื่นคืน error จริง
                if name in ("torchcodec",):
                    return "0.0.0"
                raise
        def _safe_distribution(name):
            try:
                return _orig_distribution(name)
            except _meta.PackageNotFoundError:
                if name in ("torchcodec",):
                    class _StubDist:
                        def __init__(self, n):
                            self.version = "0.0.0"
                            self.metadata = type("M", (), {"Name": n, "Version": "0.0.0"})()
                    return _StubDist(name)
                raise
        _meta.version = _safe_version
        _meta.distribution = _safe_distribution
        _boot_log("importlib.metadata stubbed for missing packages")
    except Exception as _e:
        logger.debug(f"metadata stub (skipped): {_e}")


# ═══ PyInstaller warm-up: register HiggsAudioV2TokenizerModel into transformers registry ═══
# transformers LazyModule พังใน PyInstaller → register class ตรงๆ แทน
# ★ ย้ายออกจาก module-level → เรียกหลัง splash.show() (ประหยัดเวลา startup 5-6 วิ)
def _warmup_transformers():
    """register HiggsAudioV2 + patch _LazyModule — จำเป็นเฉพาะตอน OmniVoice โหลด

    ★ ย้ายมาเรียกหลัง splash.show() เพื่อให้ splash ขึ้นเร็ว (ไม่รอ import transformers/torch)
    ★ OmniVoice จะถูกโหลดที่ app.py QTimer.singleShot(2000, ...) — warmup นี้ต้องเสร็จก่อน
    """
    # ═══ PyInstaller patch: monkey-patch _LazyModule._get_module ═══
    # ปัญหา: _LazyModule._get_module ใช้ relative import ที่ fail ใน PyInstaller
    # แก้: override เป็น absolute import (full path) เป็น fallback
    # ★ ต้อง patch ก่อน import HiggsAudioV2 (เพื่อให้ patch มีผลกับ instance ใหม่)
    try:
        import importlib
        from transformers.utils.import_utils import _LazyModule
        def _patched_get_module(self, module_name):
            try:
                return importlib.import_module("." + module_name, self.__name__)
            except Exception:
                full_name = f"{self.__name__}.{module_name}"
                return importlib.import_module(full_name)
        _LazyModule._get_module = _patched_get_module
        _boot_log("_LazyModule._get_module patched for PyInstaller")
    except Exception as _e:
        logger.debug(f"_LazyModule patch (skipped): {_e}")

    # ═══ register HiggsAudioV2TokenizerModel into transformers registry ═══
    try:
        # ★ import module แบบ full path (ทำงานใน PyInstaller)
        from transformers.models.higgs_audio_v2_tokenizer.modeling_higgs_audio_v2_tokenizer import (
            HiggsAudioV2TokenizerModel as _HiggsModel,
        )
        from transformers.models.higgs_audio_v2_tokenizer.configuration_higgs_audio_v2_tokenizer import (
            HiggsAudioV2TokenizerConfig as _HiggsConfig,
        )
        # ★ register เข้า transformers AUTO mapping (กัน "Could not import module" error)
        from transformers import AutoConfig, AutoModel
        try:
            AutoConfig.register("higgs_audio_v2_tokenizer", _HiggsConfig)
        except Exception:
            pass  # อาจ register ซ้ำ
        try:
            AutoModel.register(_HiggsConfig, _HiggsModel)
        except Exception:
            pass
        # ★ inject เข้า sys.modules ด้วยชื่อสั้น (transformers AutoMap ใช้ชื่อสั้น)
        import sys as _sys
        import transformers.models.higgs_audio_v2_tokenizer.modeling_higgs_audio_v2_tokenizer as _mod_module
        _sys.modules["modeling_higgs_audio_v2_tokenizer"] = _mod_module
        import transformers.models.higgs_audio_v2_tokenizer.configuration_higgs_audio_v2_tokenizer as _cfg_module
        _sys.modules["configuration_higgs_audio_v2_tokenizer"] = _cfg_module
        _boot_log("HiggsAudioV2 registered into transformers registry")
    except Exception as _e:
        logger.debug(f"warm-up transformers (skipped): {_e}")


def main():
    # ★ dispatch to Game Overlay Qt subprocess ถ้าถูกเรียกด้วย flag นี้
    #   (fix: exe mode เปิด Game Overlay แล้วเปิดตัวเองซ้ำ)
    if "--game-overlay-qt" in sys.argv:
        from game_overlay_qt import main as qt_main
        return qt_main()

    # ★ stub metadata ก่อน splash (เบา + จำเป็น ต้องอยู่ก่อน transformers import)
    _stub_importlib_metadata()

    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QPixmap, QIcon
    from PySide6.QtCore import Qt

    # ★ Init pygame mixer ก่อน Qt (สำคัญ — กัน WASAPI conflict)
    #    ต้อง init ก่อนสร้าง QApplication เพราะ Qt อาจจะ lock audio device
    try:
        import pygame
        pygame.mixer.pre_init(frequency=44100, size=-16, channels=1, buffer=512)
        pygame.mixer.init()
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setApplicationName("Broadcast Playroom")
    app.setOrganizationName("MeN9CH")
    _boot_log("QApplication ready")

    # ═══ Single-instance check (กันเปิดโปรแกรมซ้อน) ═══
    #   ★ ถ้ามี instance รันอยู่แล้ว → แสดง modal ถาม user (kill หรือยกเลิก)
    #   ★ ใช้ Windows named mutex (Global\BroadcastPlayroom_SingleInstance)
    try:
        from single_instance import acquire_lock, find_playroom_windows, bring_to_front
        is_first_instance = acquire_lock()
        if not is_first_instance:
            _boot_log("another instance running — showing modal")
            # ★ ลอง bring-to-front instance เดิมก่อน
            windows = find_playroom_windows()
            # ★ แสดง modal ถาม user
            from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
            dlg = QDialog()
            dlg.setWindowTitle("⚠️ โปรแกรมเปิดอยู่แล้ว")
            dlg.setModal(True)
            dlg.setMinimumWidth(420)
            layout = QVBoxLayout(dlg)
            layout.setSpacing(12)
            layout.setContentsMargins(20, 20, 20, 20)

            title_lbl = QLabel("⚠️ Broadcast Playroom กำลังรันอยู่แล้ว")
            title_lbl.setStyleSheet("font-size: 15px; font-weight: 700; color: #f59e0b;")
            title_lbl.setWordWrap(True)
            layout.addWidget(title_lbl)

            desc_text = (
                "พบว่าโปรแกรม Broadcast Playroom กำลังรันอยู่เบื้องหลัง\n\n"
                + ("✅ พบหน้าต่างโปรแกรม — กด \"ดึงหน้าต่างขึ้นมา\" เพื่อใช้งาน\n" if windows else "")
                + "หากคิดว่าโปรแกรมค้าง (ไม่ตอบสนอง) สามารถกด \"สั่งปิดและเปิดใหม่ทันที\" "
                "เพื่อ Kill Process เดิมแล้วเปิดโปรแกรมใหม่ทันที"
            )
            desc_lbl = QLabel(desc_text)
            desc_lbl.setWordWrap(True)
            desc_lbl.setStyleSheet("color: #cbd5e1; font-size: 13px; line-height: 1.5;")
            layout.addWidget(desc_lbl)

            btn_layout = QHBoxLayout()
            btn_layout.setSpacing(8)

            if windows:
                btn_focus = QPushButton("🪟 ดึงหน้าต่างขึ้นมา")
                btn_focus.setCursor(Qt.PointingHandCursor)
                btn_focus.setStyleSheet(
                    "QPushButton { background: #7c3aed; color: white; border: none; "
                    "border-radius: 6px; padding: 8px 16px; font-weight: 600; }"
                    "QPushButton:hover { background: #6d28d9; }"
                )
                def _on_focus():
                    for hwnd in windows:
                        bring_to_front(hwnd)
                    dlg.accept()
                btn_focus.clicked.connect(_on_focus)
                btn_layout.addWidget(btn_focus)

            btn_kill = QPushButton("🔄 สั่งปิดและเปิดใหม่ทันที")
            btn_kill.setCursor(Qt.PointingHandCursor)
            btn_kill.setStyleSheet(
                "QPushButton { background: #dc2626; color: white; border: none; "
                "border-radius: 6px; padding: 8px 16px; font-weight: 600; }"
                "QPushButton:hover { background: #b91c1c; }"
            )
            from single_instance import kill_playroom_process, release_lock
            def _on_kill():
                dlg.accept()
                kill_playroom_process(exclude_self=True)
                # ★ Kill เดิมแล้ว restart ตัวเองใหม่ทันที
                import subprocess, sys, os
                try:
                    if getattr(sys, 'frozen', False):
                        # exe mode — re-launch ตัวเอง
                        subprocess.Popen([sys.executable], cwd=os.path.dirname(sys.executable))
                    else:
                        # dev mode — re-launch ผ่าน python
                        subprocess.Popen([sys.executable, os.path.abspath(__file__)],
                                         cwd=os.path.dirname(os.path.abspath(__file__)))
                except Exception as e:
                    print(f"Restart failed: {e}")
                import sys as _sys
                _sys.exit(0)  # ปิดตัวเอง (instance ใหม่จะเปิดขึ้นมาแทน
            btn_kill.clicked.connect(_on_kill)
            btn_layout.addWidget(btn_kill)

            btn_cancel = QPushButton("ยกเลิก")
            btn_cancel.setCursor(Qt.PointingHandCursor)
            btn_cancel.setStyleSheet(
                "QPushButton { background: #334155; color: #e2e8f0; border: 1px solid #475569; "
                "border-radius: 6px; padding: 8px 16px; }"
                "QPushButton:hover { background: #475569; }"
            )
            btn_cancel.clicked.connect(dlg.reject)
            btn_layout.addWidget(btn_cancel)

            layout.addLayout(btn_layout)

            result = dlg.exec()
            if result == QDialog.Accepted and windows:
                # ★ user เลือกดึงหน้าต่าง → ปิด instance ใหม่นี้
                release_lock()
                sys.exit(0)
            elif result == QDialog.Rejected:
                # ★ user ยกเลิก → ปิด instance ใหม่นี้
                release_lock()
                sys.exit(0)
            # ★ user เลือก kill → ทำต่อ (รัน instance ใหม่นี้)
            #   แต่ต้อง acquire_lock ใหม่หลัง kill
            import time as _t
            _t.sleep(1)
            acquire_lock()  # พยายามจับ lock อีกครั้ง (ควรสำเร็จเพราะเก่าถูก kill)
            _boot_log("took over after kill")
    except SystemExit:
        raise
    except Exception as _e:
        logger.debug(f"single-instance check failed: {_e} — allowing run")

    # ★ Startup migration — ลบ exe เก่าที่ค้างจากการเปลี่ยนชื่อ (เช่น BroadcastPlayroom_Full → Broadcast Playroom Full)
    #   กรณี: อัพเดทจากเวอร์ชั่นเก่า (updater เก่าไม่มี migration) → เหลือ 2 exe ซ้อนกัน
    if getattr(sys, 'frozen', False):
        try:
            _exe_dir = os.path.dirname(sys.executable)
            _exe_name = os.path.basename(sys.executable)
            for _f in os.listdir(_exe_dir):
                if _f.lower().endswith('.exe') and _f != _exe_name:
                    _f_lower = _f.lower()
                    # ★ เฉพาะ exe ของเราเท่านั้น (กันลบ exe อื่นในโฟลเดอร์)
                    if ('broadcast' in _f_lower and 'playroom' in _f_lower):
                        _old = os.path.join(_exe_dir, _f)
                        # ★ ถ้าชื่อปัจจุบันคือชื่อใหม่ (มีช่องว่าง) → ลบชื่อเก่า (ไม่มีช่องว่าง)
                        #   ถ้าชื่อปัจจุบันคือชื่อเก่า → ลบชื่อใหม่ แล้วรีสตาร์ทด้วยชื่อใหม่
                        if ' ' in _exe_name and ' ' not in _f:
                            # ปัจจุบัน = ชื่อใหม่, เจอชื่อเก่า → ลบได้เลย
                            os.remove(_old)
                            logger.info(f"Startup migration: deleted old exe {_f}")
                        elif ' ' not in _exe_name and ' ' in _f:
                            # ปัจจุบัน = ชื่อเก่า, เจอชื่อใหม่ → รันชื่อใหม่ + ลบตัวเอง
                            logger.info(f"Startup migration: switching to new exe {_f}")
                            import subprocess
                            subprocess.Popen([_old], cwd=_exe_dir)
                            _boot_log(f"migrated to {_f}, exiting old exe")
                            sys.exit(0)
        except SystemExit:
            raise
        except Exception as _e:
            logger.debug(f"startup exe cleanup: {_e}")

    # ★ Icon
    base_dir = os.path.dirname(os.path.abspath(__file__))
    icon_path = os.path.join(base_dir, "assets", "icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # ★ Splash screen — random ระหว่าง splash_1.png / splash_2.png (ทั้ง Full + Lite)
    #   ★ แสดง splash ทันที (ก่อน warmup_transformers + สร้าง window) → user เห็นทันที
    splash_pix = None
    splash = None
    import random
    splash_candidates = [
        os.path.join(base_dir, "assets", "splash_1.png"),
        os.path.join(base_dir, "assets", "splash_2.png"),
    ]
    # ★ PyInstaller bundled: assets/ อยู่ใน _internal/assets/ (sys._MEIPASS หรือ exe dir)
    try:
        if getattr(sys, 'frozen', False):
            _internal = os.path.join(os.path.dirname(sys.executable), "_internal")
            if os.path.isdir(_internal):
                splash_candidates = [
                    os.path.join(_internal, "assets", "splash_1.png"),
                    os.path.join(_internal, "assets", "splash_2.png"),
                ]
    except Exception:
        pass
    # ★ random เฉพาะภาพที่มีอยู่จริง
    available = [p for p in splash_candidates if os.path.exists(p)]
    if available:
        splash_path = random.choice(available)
        from PySide6.QtWidgets import QSplashScreen
        splash_pix = QPixmap(splash_path)
        if not splash_pix.isNull():
            splash = QSplashScreen(splash_pix)
            splash.show()
            # ★ บังคับ Qt วาด splash ทันที (ไม่รอ event loop) → user เห็นเลย
            app.processEvents()
            _boot_log("splash visible ✓")

    # ★ warmup transformers หลัง splash ขึ้นแล้ว (หนัก — import torch/transformers)
    #   ★ ย้ายมาจาก module-level → user เห็น splash ระหว่างรอ (ไม่ใช่จอดำ 5-6 วิ)
    #   ★ OmniVoice จะถูกโหลดที่ app.py QTimer.singleShot(2000, ...) — warmup นี้ต้องเสร็จก่อน
    _warmup_transformers()

    # ★ Import + apply theme (อ่านค่าธีมจาก settings ก่อนสร้าง widget ใดๆ)
    from ui.theme import apply_theme
    try:
        from settings import load_settings
        _theme_name = getattr(load_settings(), "ui_theme", "default")
    except Exception:
        _theme_name = "default"
    apply_theme(app, _theme_name)

    # ★ Import + create main window
    from app import TTSForLivestreamApp
    window = TTSForLivestreamApp()
    _boot_log("main window constructed")

    window.show()
    # ★ บังคับ Qt วาด window ทันที → splash จะได้หายไปเมื่อ window พร้อมจริง (render แล้ว)
    app.processEvents()

    # ★ ซ่อน splash เมื่อ window พร้อม (render เสร็จแล้ว)
    if splash:
        splash.finish(window)
        _boot_log("splash finished — window visible")

    logger.info("Application started")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
