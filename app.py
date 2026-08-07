"""app.py — Main application window (QMainWindow)

ประกอบ UI ทั้งหมดเข้าด้วยกัน + เชื่อม logic (chat clients, TTS, pipeline)
"""
import logging
import os
import threading
import time
from PySide6.QtCore import Qt, QTimer, Signal, QObject, QThread
from PySide6.QtGui import QAction, QIcon, QFont, QColor, QPixmap
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QFrame, QLabel, QPushButton, QLineEdit,
    QVBoxLayout, QHBoxLayout, QGridLayout, QSplitter, QScrollArea,
    QSizePolicy, QSpacerItem, QApplication, QMessageBox,
)

from ui.theme import (
    COLOR_BG, COLOR_BG_DARK, COLOR_CARD, COLOR_CARD_HI, COLOR_ACCENT,
    COLOR_ACCENT_HOVER, COLOR_ACCENT_2, COLOR_HEADING, COLOR_DANGER,
    COLOR_SUCCESS, COLOR_TEXT, COLOR_TEXT_DIM, COLOR_TEXT_FAINT,
    COLOR_BORDER, COLOR_BORDER_LIGHT,
)
from ui.widgets.topbar import TopBar
from ui.widgets.sidebar import Sidebar, PlatformCard
from ui.widgets.chat_panel import ChatPanel
from ui.widgets.events_panel import EventsPanel
from ui.widgets.status_bar import StatusBar

logger = logging.getLogger("app")

# ═══ Platform Registry (คัดลอกจาก v1 — แบบย่อ) ═══
PLATFORM_ORDER = ["twitch", "youtube", "mylive", "tiktok", "kick"]
PLATFORM_LABELS = {
    "twitch": "Twitch",
    "youtube": "YouTube",
    "mylive": "MyLive",
    "tiktok": "TikTok",
    "kick": "KICK",
}
PLATFORM_ICONS = {
    "twitch": "🟣",
    "youtube": "🔴",
    "mylive": "🟠",
    "tiktok": "⚫",
    "kick": "🟢",
}


class TTSForLivestreamApp(QMainWindow):
    """Main application window — Broadcast Playroom v2 (PySide6)"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Broadcast Playroom by MeN9CH")
        self.setGeometry(100, 100, 1080, 720)
        self.setMinimumSize(960, 640)

        # ═══ State ═══
        self._closing = False
        self.settings = None
        self.pipeline = None
        self.tts_engine = None
        self.audio_player = None
        self.chat_clients = {}
        self._viewer_counts = {}
        self._platform_widgets = {}
        self._msg_buffer = []
        self._msg_buffer_lock = threading.Lock()

        # ═══ Load settings + engines ═══
        self._init_engines()

        # ═══ Build UI ═══
        self._build_ui()

        # ═══ Start poll timer (flush message buffer → chat feed) ═══
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_messages)
        self._poll_timer.start(100)

        # ═══ Auto-connect + timers ═══
        QTimer.singleShot(500, self._maybe_auto_connect)

        logger.info("Main window initialized")

    # ════════════════════════════════════════════════════════════
    # Engine init (logic — คัดลอกจาก v1)
    # ════════════════════════════════════════════════════════════
    def _init_engines(self):
        """โหลด settings + TTS engine + pipeline (เหมือน v1)"""
        try:
            from settings import load_settings
            self.settings = load_settings()
        except Exception as e:
            logger.error(f"Failed to load settings: {e}")
            self.settings = None

        try:
            from tts_engine import TTSEngine
            self.tts_engine = TTSEngine()
        except Exception as e:
            logger.error(f"Failed to init TTS engine: {e}")
            self.tts_engine = None

        try:
            from audio_player import AudioPlayer
            self.audio_player = AudioPlayer()
        except Exception:
            try:
                # fallback: อาจอยู่ใน chat_queue หรือที่อื่น
                from chat_queue import AudioPlayer
                self.audio_player = AudioPlayer()
            except Exception as e:
                logger.error(f"Failed to init audio player: {e}")
                self.audio_player = None

        # ★ pipeline (TTS queue manager)
        try:
            from chat_queue import ChatPipeline
            config = self._build_pipeline_config()
            self.pipeline = ChatPipeline(self.tts_engine, self.audio_player, config)
            if self.settings:
                self.pipeline.set_filter(self.settings.to_text_filter())
            self.pipeline.on_status = lambda msg: self._safe_status(msg)
        except Exception as e:
            logger.error(f"Failed to init pipeline: {e}")
            self.pipeline = None

    def _build_pipeline_config(self):
        """สร้าง PipelineConfig จาก settings (เหมือน v1)"""
        try:
            from chat_queue import PipelineConfig
            s = self.settings
            if not s:
                return PipelineConfig()
            return PipelineConfig(
                voice=getattr(s, 'voice_id', ''),
                read_author=getattr(s, 'read_author', True),
                read_message=getattr(s, 'read_message', True),
                rate=getattr(s, 'rate', 0),
                volume=getattr(s, 'volume', 100),
            )
        except Exception as e:
            logger.error(f"Failed to build pipeline config: {e}")
            from chat_queue import PipelineConfig
            return PipelineConfig()

    # ════════════════════════════════════════════════════════════
    # UI Build
    # ════════════════════════════════════════════════════════════
    def _build_ui(self):
        """ประกอบ UI หลัก: TopBar + (Sidebar | Chat | Events) + StatusBar"""
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ★ TopBar
        self.topbar = TopBar(self)
        layout.addWidget(self.topbar)

        # ★ Body (3-column splitter)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setChildrenCollapsible(False)

        self.sidebar = Sidebar(self)
        self.chat_panel = ChatPanel(self)
        self.events_panel = EventsPanel(self)

        splitter.addWidget(self.sidebar)
        splitter.addWidget(self.chat_panel)
        splitter.addWidget(self.events_panel)
        splitter.setStretchFactor(0, 0)  # sidebar fixed
        splitter.setStretchFactor(1, 1)  # chat expands
        splitter.setStretchFactor(2, 0)  # events fixed
        splitter.setSizes([260, 600, 240])

        layout.addWidget(splitter, 1)

        # ★ StatusBar
        self.status_bar = StatusBar(self)
        layout.addWidget(self.status_bar)

        # ═══ Connect signals ═══
        self.topbar.settings_clicked.connect(self._open_settings)
        self.topbar.user_manager_clicked.connect(self._open_user_manager)
        self.topbar.overlay_toggle_clicked.connect(self._toggle_overlay)
        self.topbar.mute_toggle_clicked.connect(self._toggle_mute)

        # ═══ Build platform cards ═══
        self._platform_cards = {}
        self._build_platform_cards()

        # ═══ Connect sidebar voice controls ═══
        self.sidebar.voice_combo.currentIndexChanged.connect(self._on_voice_change)
        self.sidebar.vol_slider.valueChanged.connect(self._on_volume_change)
        self.sidebar.rate_slider.valueChanged.connect(self._on_rate_change)
        self.sidebar.voice_download_btn.clicked.connect(self._open_voice_downloader)

    def _build_platform_cards(self):
        """สร้าง card สำหรับแต่ละแพลตฟอร์ม + เชื่อม connect signal"""
        # ★ อ่านว่าแสดงแพลตฟอร์มไหนบ้าง (default = ทั้งหมด)
        show_platforms = getattr(self.settings, 'show_platforms', None) if self.settings else None
        if not show_platforms:
            show_platforms = PLATFORM_ORDER[:]

        for plat in PLATFORM_ORDER:
            if plat not in show_platforms:
                continue
            label = PLATFORM_LABELS.get(plat, plat)
            icon = PLATFORM_ICONS.get(plat, "📺")
            card = self.sidebar.add_platform(plat, label, icon)
            card.connect_requested.connect(self._connect_platform)
            card.disconnect_requested.connect(self._disconnect_platform)
            self._platform_cards[plat] = card
            # ★ เพิ่ม status dot ใน topbar
            card._topbar_widget = self.topbar.add_platform_status(label)

    # ════════════════════════════════════════════════════════════
    # Platform connect/disconnect
    # ════════════════════════════════════════════════════════════
    def _get_platform_target(self, platform):
        """ดึง target (channel/URL) จาก settings"""
        if not self.settings:
            return ""
        target_map = {
            "twitch": getattr(self.settings, 'twitch_channel', ''),
            "youtube": getattr(self.settings, 'youtube_video_id', ''),
            "mylive": getattr(self.settings, 'mylive_url', ''),
            "tiktok": getattr(self.settings, 'tiktok_user', ''),
            "kick": getattr(self.settings, 'kick_channel', ''),
        }
        return target_map.get(platform, '')

    def _connect_platform(self, platform):
        """เชื่อมต่อแพลตฟอร์ม"""
        target = self._get_platform_target(platform)
        if not target:
            label = PLATFORM_LABELS.get(platform, platform)
            QMessageBox.warning(self, "ยังไม่ได้ตั้งค่า", f"กรุณาตั้งค่า {label} ใน Settings ก่อน")
            return

        # ★ set UI to "connecting"
        card = self._platform_cards.get(platform)
        if card:
            card.btn.setText("...")
            card.btn.setEnabled(False)

        # ★ connect in background thread
        def _bg_connect():
            try:
                client = self._create_client(platform)
                if client:
                    ok = client.connect(target)
                    if ok:
                        self.chat_clients[platform] = client
                        QTimer.singleShot(0, lambda: self._on_platform_connected(platform))
                    else:
                        QTimer.singleShot(0, lambda: self._on_platform_connect_failed(platform, "connect returned False"))
                else:
                    QTimer.singleShot(0, lambda: self._on_platform_connect_failed(platform, "unsupported platform"))
            except Exception as e:
                logger.error(f"Connect {platform} failed: {e}")
                QTimer.singleShot(0, lambda e=e: self._on_platform_connect_failed(platform, str(e)))

        threading.Thread(target=_bg_connect, name=f"Connect-{platform}", daemon=True).start()

    def _create_client(self, platform):
        """สร้าง chat client สำหรับแพลตฟอร์ม"""
        on_message, on_status, on_error = self._make_callbacks(platform)
        def on_viewer_count(plat, count):
            self._viewer_counts[plat] = count
            QTimer.singleShot(0, self._update_viewer_ui)

        # ★ text_filter (สำหรับ Twitch)
        text_filter = None
        if self.settings:
            try:
                text_filter = self.settings.to_text_filter()
            except Exception:
                pass

        try:
            if platform == "twitch":
                from chat_twitch import TwitchChat
                return TwitchChat(on_message=on_message, on_status=on_status, on_error=on_error, on_viewer_count=on_viewer_count, text_filter=text_filter)
            elif platform == "youtube":
                from chat_youtube import YouTubeChat
                return YouTubeChat(on_message=on_message, on_status=on_status, on_error=on_error, on_viewer_count=on_viewer_count)
            elif platform == "mylive":
                from chat_mylive import MyLiveChat
                return MyLiveChat(on_message=on_message, on_status=on_status, on_error=on_error, on_viewer_count=on_viewer_count)
            elif platform == "tiktok":
                from chat_tiktok import TikTokChat
                return TikTokChat(on_message=on_message, on_status=on_status, on_error=on_error, on_viewer_count=on_viewer_count)
            elif platform == "kick":
                from chat_kick import KickChat
                return KickChat(on_message=on_message, on_status=on_status, on_error=on_error, on_viewer_count=on_viewer_count)
        except Exception as e:
            logger.error(f"Failed to create {platform} client: {e}")
        return None

    def _make_callbacks(self, platform):
        """สร้าง callbacks สำหรับ chat client"""
        def on_message(msg):
            with self._msg_buffer_lock:
                self._msg_buffer.append(msg)
            # ★ ส่งเข้า pipeline (TTS queue)
            if self.pipeline and getattr(msg, 'event', 'message') == 'message':
                try:
                    self.pipeline.enqueue(msg)
                except Exception:
                    pass

        def on_status(msg_text):
            QTimer.singleShot(0, lambda: self.status_bar.set_status(f"[{platform}] {msg_text}"))

        def on_error(msg_text):
            QTimer.singleShot(0, lambda: self._on_platform_error(platform, msg_text))

        return on_message, on_status, on_error

    def _on_platform_connected(self, platform):
        """เรียกเมื่อเชื่อมต่อสำเร็จ"""
        card = self._platform_cards.get(platform)
        if card:
            card.set_connected(True)
            card.btn.setEnabled(True)
        label = PLATFORM_LABELS.get(platform, platform)
        self.status_bar.set_status(f"✅ {label} เชื่อมต่อแล้ว")

    def _on_platform_connect_failed(self, platform, error):
        """เรียกเมื่อเชื่อมต่อล้มเหลว"""
        card = self._platform_cards.get(platform)
        if card:
            card.set_connected(False)
            card.btn.setEnabled(True)
        label = PLATFORM_LABELS.get(platform, platform)
        self.status_bar.set_status(f"❌ {label} เชื่อมต่อไม่ได้: {error}")

    def _on_platform_error(self, platform, error_msg):
        """เรียกเมื่อ chat client ส่ง error (หลุด/ปิด)"""
        card = self._platform_cards.get(platform)
        if card:
            card.set_connected(False)
        label = PLATFORM_LABELS.get(platform, platform)
        self.status_bar.set_status(f"⚠️ {label}: {error_msg}")

    def _disconnect_platform(self, platform):
        """ยุติการเชื่อมต่อ"""
        client = self.chat_clients.pop(platform, None)
        if client:
            try:
                client.disconnect()
            except Exception:
                pass
        card = self._platform_cards.get(platform)
        if card:
            card.set_connected(False)
        label = PLATFORM_LABELS.get(platform, platform)
        self.status_bar.set_status(f"🛑 {label} ยุติการเชื่อมต่อแล้ว")

    # ════════════════════════════════════════════════════════════
    # Chat feed (poll message buffer)
    # ════════════════════════════════════════════════════════════
    def _poll_messages(self):
        """flush message buffer → chat feed (เรียกทุก 100ms ผ่าน QTimer)"""
        if self._closing:
            return
        with self._msg_buffer_lock:
            msgs = self._msg_buffer[:]
            self._msg_buffer.clear()
        for msg in msgs:
            self.chat_panel.add_message(msg)
            # ★ system message → status bar
            if getattr(msg, 'event', '') == 'system':
                self.status_bar.set_status(msg.text or msg.system_text or '')

    def _update_viewer_ui(self):
        """อัปเดตยอดคนดู"""
        total = sum(self._viewer_counts.values())
        self.chat_panel.viewers_label.setText(f"👥 {total:,}")

    # ════════════════════════════════════════════════════════════
    # Voice / TTS controls
    # ════════════════════════════════════════════════════════════
    def _on_voice_change(self, index):
        """เปลี่ยนเสียง TTS"""
        # TODO: implement voice selection

    def _on_volume_change(self, value):
        """ปรับ volume"""
        if self.settings:
            self.settings.volume = value
        if self.pipeline:
            self.pipeline.config.volume = value

    def _on_rate_change(self, value):
        """ปรับ rate"""
        if self.settings:
            self.settings.rate = value
        if self.pipeline:
            self.pipeline.config.rate = value

    def _open_voice_downloader(self):
        """เปิด Voice Downloader dialog"""
        # TODO: implement voice downloader dialog
        self.status_bar.set_status("Voice Downloader — เร็วๆ นี้")

    # ════════════════════════════════════════════════════════════
    # TopBar actions
    # ════════════════════════════════════════════════════════════
    def _open_settings(self):
        """เปิด Settings dialog"""
        from ui.dialogs.settings import SettingsDialog
        dlg = SettingsDialog(self)
        dlg.settings_changed.connect(self._on_settings_changed)
        dlg.exec()

    def _on_settings_changed(self):
        """เรียกเมื่อ settings เปลี่ยน"""
        # ★ reload pipeline config
        if self.pipeline and self.settings:
            self.pipeline.set_filter(self.settings.to_text_filter())
        self.status_bar.set_status("✅ บันทึกการตั้งค่าแล้ว")

    def _open_user_manager(self):
        """เปิด User Manager"""
        self.status_bar.set_status("User Manager — เร็วๆ นี้")

    def _toggle_overlay(self):
        """เปิด/ปิด overlay"""
        self.status_bar.set_status("Overlay — เร็วๆ นี้")

    def _toggle_mute(self):
        """เปิด/ปิด TTS"""
        if self.pipeline:
            self.pipeline.toggle_mute()
        muted = getattr(self.pipeline, '_muted', False) if self.pipeline else False
        self.status_bar.set_status("🔇 TTS ปิดเสียงแล้ว" if muted else "🔊 TTS เปิดเสียงแล้ว")

    # ════════════════════════════════════════════════════════════
    # Logic bridges (เรียกจาก widgets)
    # ════════════════════════════════════════════════════════════
    def _safe_status(self, msg):
        """thread-safe status update"""
        QTimer.singleShot(0, lambda: self.status_bar.set_status(msg))

    def _maybe_auto_connect(self):
        """auto-connect แพลตฟอร์มที่เปิดไว้ (ถ้ามี channel)"""
        if not self.settings:
            return
        if not getattr(self.settings, 'auto_connect_on_start', False):
            return
        for plat in PLATFORM_ORDER:
            target = self._get_platform_target(plat)
            if target and plat in self._platform_cards:
                self._connect_platform(plat)

    def closeEvent(self, event):
        """cleanup on close"""
        self._closing = True
        # ★ หยุด chat clients
        for plat, client in list(self.chat_clients.items()):
            try:
                client.disconnect()
            except Exception:
                pass
        # ★ หยุด TTS engine
        if self.tts_engine:
            try:
                self.tts_engine.stop()
            except Exception:
                pass
        logger.info("Application closing")
        event.accept()
