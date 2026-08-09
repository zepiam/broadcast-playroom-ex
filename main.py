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

# ═══ PyInstaller fix: stub missing package metadata (torchcodec) ═══
# transformers/audio_utils.py อ่าน importlib.metadata.version("torchcodec")
# แต่ torchcodec ไม่ได้ติดตั้ง → PackageNotFoundError → cascade fail
# แก้: stub metadata ให้คืนค่าเริ่มต้นสำหรับ package ที่ไม่มี
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
    logger.info("warm-up: importlib.metadata stubbed for missing packages")
except Exception as _e:
    logger.debug(f"metadata stub (skipped): {_e}")

# ═══ PyInstaller warm-up: register HiggsAudioV2TokenizerModel into transformers registry ═══
# transformers LazyModule พังใน PyInstaller → register class ตรงๆ แทน
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
    logger.info("warm-up: HiggsAudioV2 registered into transformers registry")
except Exception as _e:
    logger.debug(f"warm-up transformers (skipped): {_e}")

# ═══ PyInstaller patch: monkey-patch _LazyModule._get_module ═══
# ปัญหา: _LazyModule._get_module ใช้ relative import ที่ fail ใน PyInstaller
# แก้: override เป็น absolute import (full path) เป็น fallback
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
    logger.info("warm-up: _LazyModule._get_module patched for PyInstaller")
    # ★ force-clear cache ของ transformers.models.higgs_audio_v2_tokenizer module
    #   เพื่อให้ patch มีผล (instance เดิมอาจ bind method เดิมไว้)
    import sys as _sys
    for _mod_name in list(_sys.modules.keys()):
        if "higgs_audio_v2" in _mod_name:
            del _sys.modules[_mod_name]
            logger.debug(f"cleared cached module: {_mod_name}")
except Exception as _e:
    logger.debug(f"_LazyModule patch (skipped): {_e}")


def main():
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

    # ★ Icon
    base_dir = os.path.dirname(os.path.abspath(__file__))
    icon_path = os.path.join(base_dir, "assets", "icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # ★ Splash screen — random ระหว่าง splash_1.png / splash_2.png (ทั้ง Full + Lite)
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
            splash = QSplashScreen(splash_pix, Qt.WindowStaysOnTopHint)
            splash.show()
            app.processEvents()

    # ★ Import + apply theme
    from ui.theme import apply_theme
    apply_theme(app)

    # ★ Import + create main window
    from app import TTSForLivestreamApp
    window = TTSForLivestreamApp()
    window.show()

    # ★ ซ่อน splash เมื่อ window พร้อม
    if splash:
        splash.finish(window)

    logger.info("Application started")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
