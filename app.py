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

        # ═══ Start servers (overlay + composer + playroom) ═══
        self.overlay_server = None
        self.composer_server = None
        self.playroom_server = None
        self._np_watcher = None
        self._start_servers()

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
    # Server startup (overlay + composer + playroom + now playing)
    # ════════════════════════════════════════════════════════════
    def _start_servers(self):
        """เริ่ม servers ทั้งหมด (overlay + composer + playroom)"""
        # ★ Composer server (Canvas Overlay Composer)
        self._start_composer_server()
        # ★ Playroom server (ถ้าเปิดไว้)
        if getattr(self.settings, 'playroom_enabled', False):
            self._start_playroom_server()
        # ★ Now Playing watcher (หน่วง 5 วิ)
        QTimer.singleShot(5000, self._start_np_watcher)

    def _start_composer_server(self):
        """เริ่ม composer server"""
        try:
            from composer_server import ComposerServer
            port = int(getattr(self.settings, 'composer_port', 8808))
            self.composer_server = ComposerServer(self.settings, port=port)
            # ★ callbacks
            self.composer_server.on_save_widgets = self._save_composer_widgets
            self.composer_server.on_open_playroom_settings = lambda: None
            self.composer_server.on_save_playroom_triggers = self._save_playroom_triggers
            if self.composer_server.start():
                logger.info(f"Composer server: http://localhost:{port}")
            else:
                logger.error("Composer server failed to start")
                self.composer_server = None
        except Exception as e:
            logger.error(f"Failed to start composer server: {e}")
            self.composer_server = None

    def _start_playroom_server(self):
        """เริ่ม playroom server"""
        try:
            from playroom_server import PlayroomServer
            self.playroom_server = PlayroomServer(self.settings)
            if self.playroom_server.start():
                logger.info("Playroom server started")
            else:
                self.playroom_server = None
        except Exception as e:
            logger.error(f"Failed to start playroom server: {e}")
            self.playroom_server = None

    def _start_np_watcher(self):
        """เริ่ม Now Playing watcher (อ่านเพลงจาก Windows System Media)"""
        try:
            from now_playing import NowPlayingWatcher

            def _on_np_change(title, artist, album, thumb_path, pos, dur, playing):
                thumb_url = ""
                if thumb_path:
                    import urllib.parse
                    thumb_url = "/now-playing-art?path=" + urllib.parse.quote(thumb_path)
                data = {
                    "title": title, "artist": artist, "album": album,
                    "thumbnail_url": thumb_url, "position": pos,
                    "duration": dur, "is_playing": playing,
                }
                self._last_np_data = data
                QTimer.singleShot(0, lambda: self._composer_push_now_playing(data))

            def _on_np_position(pos, dur, playing):
                data = {"position": pos, "duration": dur, "is_playing": playing}
                QTimer.singleShot(0, lambda: self._composer_push_now_playing(data))

            self._np_watcher = NowPlayingWatcher(on_change=_on_np_change, on_position=_on_np_position)
            self._np_watcher.start()
            logger.info("Now Playing watcher started")
        except Exception as e:
            logger.error(f"Failed to start NP watcher: {e}")
            self._np_watcher = None

    def _composer_push_now_playing(self, data):
        """forward now playing data ไป composer widget"""
        if self.composer_server is None:
            return
        try:
            if data.get("title"):
                self.composer_server._last_np_data = data
            self.composer_server.push_now_playing(data)
        except Exception:
            pass

    def _composer_push_message(self, msg):
        """forward chat message ไป composer server"""
        if self.composer_server is None:
            return
        try:
            payload = self._serialize_msg_for_overlay(msg)
            if payload:
                self.composer_server.push_message(payload)
        except Exception:
            pass

    def _composer_push_viewers(self, total, platforms):
        """forward viewer counts ไป composer"""
        if self.composer_server is None:
            return
        try:
            self.composer_server.push_viewer_counts(total, platforms)
        except Exception:
            pass

    def _serialize_msg_for_overlay(self, msg):
        """แปลง ChatMessage → dict สำหรับ composer (แบบย่อ)"""
        try:
            extra = msg.extra or {}
            text = msg.text or ""
            want_animated = bool(getattr(self.settings, "overlay_animated_emotes", True))
            twitch_emotes = []
            for em in (extra.get("emotes") or []):
                eid = em.get("id")
                emote_url = em.get("url", "")
                emote_url_animated = em.get("url_animated", "")
                if emote_url:
                    final_url = emote_url_animated if (want_animated and emote_url_animated) else emote_url
                    twitch_emotes.append({"name": em.get("name", ""), "url": final_url, "start": em.get("start", 0), "end": em.get("end", 0)})
                elif eid is not None:
                    twitch_emotes.append({"name": em.get("name", ""), "url": f"/emote/{eid}", "start": em.get("start", 0), "end": em.get("end", 0)})
            return {
                "author": msg.author or "",
                "text": text,
                "raw_text": extra.get("raw_text", ""),
                "twitch_emotes": twitch_emotes,
                "segments": extra.get("segments", []),
                "sticker_url": extra.get("sticker_url", ""),
                "color": extra.get("color", ""),
                "platform": getattr(msg, "platform", ""),
                "event": getattr(msg, "event", "message"),
                "badge": "",
                "system_text": msg.system_text or "",
                "timestamp": "",
            }
        except Exception:
            return None

    def _save_composer_widgets(self, widgets, canvas_size=None):
        """callback จาก composer editor → persist widgets"""
        try:
            self.settings.composer_widgets = list(widgets)
            if canvas_size in ("720p", "1080p"):
                self.settings.composer_canvas_size = canvas_size
            from settings import save_settings
            save_settings(self.settings)
        except Exception as e:
            logger.error(f"Failed to save composer widgets: {e}")

    def _save_playroom_triggers(self):
        """callback จาก composer → persist playroom triggers"""
        try:
            from settings import save_settings
            save_settings(self.settings)
            if hasattr(self, "pipeline") and self.pipeline is not None:
                self.pipeline.config.playroom_triggers = list(self.settings.playroom_triggers)
        except Exception as e:
            logger.error(f"Failed to save playroom triggers: {e}")

    def _open_composer(self):
        """เปิด composer editor ในเบราว์เซอร์"""
        import webbrowser
        port = int(getattr(self.settings, 'composer_port', 8808))
        url = f"http://localhost:{port}/editor"
        webbrowser.open(url)

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

        # ═══ Connect chat panel signals ═══
        self.chat_panel.popout_requested.connect(self._open_popout)
        self.chat_panel.clear_requested.connect(self._clear_chat)

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
            # ★ forward to composer (overlay)
            self._composer_push_message(msg)

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
            # ★ sync to popout (ถ้าเปิดอยู่)
            if hasattr(self, '_popout_window') and self._popout_window:
                self._popout_window.add_message(msg)
            # ★ system message → status bar
            if getattr(msg, 'event', '') == 'system':
                self.status_bar.set_status(msg.text or msg.system_text or '')

    def _clear_chat(self):
        """ล้าง chat feed"""
        self.chat_panel.clear_messages()
        if hasattr(self, '_popout_window') and self._popout_window:
            self._popout_window.clear_messages()

    def _update_viewer_ui(self):
        """อัปเดตยอดคนดู"""
        total = sum(self._viewer_counts.values())
        self.chat_panel.viewers_label.setText(f"👥 {total:,}")
        if hasattr(self, '_popout_window') and self._popout_window:
            self._popout_window.update_viewers(total)
        # ★ forward to composer
        self._composer_push_viewers(total, dict(self._viewer_counts))

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

    def _open_about(self):
        """เปิด About dialog"""
        from ui.dialogs.about import AboutDialog
        dlg = AboutDialog(self)
        dlg.exec()

    def _open_popout(self):
        """เปิด/ปิด Popout chat window"""
        if hasattr(self, '_popout_window') and self._popout_window:
            self._popout_window.close()
            self._popout_window = None
            return
        from ui.dialogs.popout import PopoutWindow
        self._popout_window = PopoutWindow(self)
        self._popout_window.show()

    def _open_voice_downloader(self):
        """เปิด Voice Downloader dialog"""
        from ui.dialogs.voice_downloader import VoiceDownloaderDialog
        dlg = VoiceDownloaderDialog(self)
        dlg.exec()

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
        # ★ หยุด Now Playing watcher
        if self._np_watcher:
            try:
                self._np_watcher.stop()
            except Exception:
                pass
        # ★ หยุด servers
        for srv_attr in ('composer_server', 'overlay_server', 'playroom_server'):
            srv = getattr(self, srv_attr, None)
            if srv:
                try:
                    srv.stop()
                except Exception:
                    pass
        logger.info("Application closing")
        event.accept()
