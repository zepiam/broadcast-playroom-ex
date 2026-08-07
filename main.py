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


def main():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QPixmap, QIcon
    from PySide6.QtCore import Qt

    app = QApplication(sys.argv)
    app.setApplicationName("Broadcast Playroom")
    app.setOrganizationName("MeN9CH")

    # ★ Icon
    base_dir = os.path.dirname(os.path.abspath(__file__))
    icon_path = os.path.join(base_dir, "assets", "icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # ★ Splash screen (ถ้ามีภาพ)
    splash_pix = None
    splash = None
    splash_path = os.path.join(base_dir, "splash-full.png")
    if not os.path.exists(splash_path):
        splash_path = os.path.join(base_dir, "splash-lite.png")
    if os.path.exists(splash_path):
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
