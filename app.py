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
from ui.widgets.chat_row import ChatRow
from ui.widgets.events_panel import EventsPanel
from ui.widgets.status_bar import StatusBar

logger = logging.getLogger("app")


# ★ Helper class for system status messages (routed through _chat_message signal)
class _SystemMsg:
    def __init__(self, text):
        self.text = text


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

    # ★ Signals for cross-thread communication
    _connect_result = Signal(str, object, bool)  # platform, client, ok
    _chat_message = Signal(object)  # ChatMessage
    _platform_error = Signal(str, str)  # platform, error_msg
    _viewer_update = Signal()
    _msg_translated = Signal(object)  # ChatMessage (translated)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Broadcast Playroom by MeN9CH")
        self.setGeometry(100, 100, 1080, 720)
        self.setMinimumSize(960, 640)

        # ═══ Connect cross-thread signals ═══
        self._connect_result.connect(self._on_connect_result)
        self._chat_message.connect(self._on_chat_message)
        self._platform_error.connect(self._on_platform_error_signal)
        self._viewer_update.connect(self._update_viewer_ui)
        self._msg_translated.connect(self._on_msg_translated)

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

        # ═══ State — reconnect + events + history ═══
        self._reconnect_state = {}  # platform → {attempts, last_attempt, manual_disconnect, target}
        self._init_reconnect_state()
        self.event_log = None
        self.donate_tracker = None
        self.notification_manager = None
        self.message_history = None
        self._init_subsystems()

        # ═══ Start servers (overlay + composer + playroom) ═══
        self.overlay_server = None
        self.composer_server = None
        self.playroom_server = None
        self._np_watcher = None
        self._start_servers()

        # ═══ Build UI ═══
        self._build_ui()

        # ═══ Start reconnect watcher (every 1s) ═══
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.timeout.connect(self._check_reconnect)
        self._reconnect_timer.start(1000)

        # ═══ Auto-connect + timers ═══
        QTimer.singleShot(500, self._maybe_auto_connect)

        logger.info("Main window initialized")

    # ════════════════════════════════════════════════════════════
    # Subsystem init (events + donate + notification + history)
    # ════════════════════════════════════════════════════════════
    def _init_subsystems(self):
        """เริ่ม subsystems (event_log + donate + notification + history)"""
        try:
            from event_log import EventLog
            self.event_log = EventLog()
        except Exception as e:
            logger.warning(f"EventLog not available: {e}")
        try:
            from donate_tracker import DonateTracker
            self.donate_tracker = DonateTracker()
        except Exception as e:
            logger.warning(f"DonateTracker not available: {e}")
        try:
            from notification_manager import NotificationManager
            self.notification_manager = NotificationManager(self.settings)
        except Exception as e:
            logger.warning(f"NotificationManager not available: {e}")
        try:
            from message_history import MessageHistory
            self.message_history = MessageHistory(enabled=getattr(self.settings, 'message_history_enabled', True))
        except Exception as e:
            logger.warning(f"MessageHistory not available: {e}")

    def _init_reconnect_state(self):
        """เตรียม reconnect state สำหรับทุกแพลตฟอร์ม"""
        for plat in PLATFORM_ORDER:
            self._reconnect_state[plat] = {
                'attempts': 0,
                'last_attempt': None,
                'manual_disconnect': False,
                'target': '',
            }

    # ════════════════════════════════════════════════════════════
    # Auto-reconnect system (#2)
    # ════════════════════════════════════════════════════════════
    def _check_reconnect(self):
        """ตรวจทุก platform ที่หลุด → reconnect ถ้าถึงเวลา"""
        if self._closing:
            return
        if not getattr(self.settings, 'auto_reconnect_enabled', True):
            return
        now = time.time()
        interval = getattr(self.settings, 'auto_reconnect_interval', 10.0)
        for platform, st in list(self._reconnect_state.items()):
            if st.get('manual_disconnect'):
                continue
            target = st.get('target')
            if not target:
                continue
            # ตรวจว่าหลุดหรือไม่
            disconnected = st.get('last_attempt') is not None
            if not disconnected:
                client = self.chat_clients.get(platform)
                if client is not None and hasattr(client, 'is_connected'):
                    try:
                        if not client.is_connected():
                            st['last_attempt'] = now
                            disconnected = True
                    except Exception:
                        pass
            if not disconnected:
                continue
            # รอครบ interval
            last = st.get('last_attempt') or 0
            if now - last < interval:
                continue
            # จำกัดจำนวน
            attempts = st.get('attempts', 0)
            if attempts >= 5:
                label = PLATFORM_LABELS.get(platform, platform)
                self._post_system_message(f"❌ หยุดพยายามเชื่อมต่อ {label} — เชื่อมไม่ได้ 5 ครั้งแล้ว")
                st['manual_disconnect'] = True
                st['attempts'] = 0
                continue
            st['attempts'] = attempts + 1
            st['last_attempt'] = now
            self._do_reconnect(platform, target)

    def _do_reconnect(self, platform, target):
        """พยายาม reconnect platform (background thread)"""
        st = self._reconnect_state.get(platform, {})
        label = PLATFORM_LABELS.get(platform, platform)
        self._post_system_message(f"🔄 กำลังเชื่อมต่อ {label} ใหม่... (ครั้งที่ {st.get('attempts', 1)})")
        old_client = self.chat_clients.pop(platform, None)

        def _bg_reconnect():
            if old_client:
                try:
                    old_client.disconnect()
                except Exception:
                    pass
            try:
                client = self._create_client(platform)
                if client:
                    ok = client.connect(target)
                else:
                    ok = False
                    client = None
            except Exception as e:
                ok = False
                client = None
                logger.error(f"Reconnect {platform} failed: {e}")
            QTimer.singleShot(0, lambda: self._on_reconnect_done(platform, client, ok, label))

        threading.Thread(target=_bg_reconnect, name=f"Reconnect-{platform}", daemon=True).start()

    def _on_reconnect_done(self, platform, client, ok, label):
        """หลัง reconnect เสร็จ"""
        st = self._reconnect_state.get(platform, {})
        now = time.time()
        interval = getattr(self.settings, 'auto_reconnect_interval', 10.0)
        if ok and client:
            self.chat_clients[platform] = client
            card = self._platform_cards.get(platform)
            if card:
                card.set_connected(True)
            st['attempts'] = 0
            st['last_attempt'] = None
            self._post_system_message(f"✅ เชื่อมต่อ {label} ใหม่สำเร็จ")
        else:
            backoff = min(st.get('attempts', 1) * interval, 60)
            st['last_attempt'] = now + backoff - interval
            self._post_system_message(f"❌ ยังเชื่อมต่อ {label} ไม่ได้ จะลองใหม่ใน {int(backoff)} วิ")

    def _post_system_message(self, text):
        """แทรกข้อความระบบเข้า chat feed (main thread only)"""
        try:
            from chat_twitch import ChatMessage
            msg = ChatMessage(platform='system', author='', text=text, event='system')
            self.chat_panel.add_message(msg)
            if hasattr(self, '_popout_window') and self._popout_window:
                self._popout_window.add_message(msg)
        except Exception:
            pass

    # ════════════════════════════════════════════════════════════
    # Server startup (overlay + composer + playroom + now playing)
    # ════════════════════════════════════════════════════════════
    def _start_servers(self):
        """เริ่ม servers ทั้งหมด (overlay + composer + playroom)"""
        # ★ Composer server (Canvas Overlay Composer)
        self._start_composer_server()
        # ★ Overlay server (OBS Browser Source)
        self._start_overlay_server()
        # ★ Playroom server (ถ้าเปิดไว้)
        if getattr(self.settings, 'playroom_enabled', False):
            self._start_playroom_server()
        # ★ Now Playing watcher (หน่วง 5 วิ)
        QTimer.singleShot(5000, self._start_np_watcher)

    def _start_overlay_server(self):
        """เริ่ม overlay server (OBS Browser Source)"""
        try:
            from overlay_server import OverlayServer
            self.overlay_server = OverlayServer(self.settings)
            if self.overlay_server.start():
                logger.info("Overlay server started")
            else:
                self.overlay_server = None
        except Exception as e:
            logger.error(f"Failed to start overlay server: {e}")
            self.overlay_server = None

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
            # ★ translation callback → re-render chat row (thread-safe via signal)
            self.pipeline.on_translated = lambda msg: self._msg_translated.emit(msg)
            # ★ start the pipeline worker thread (สำคัญ — ถ้าไม่ start TTS จะไม่อ่าน!)
            self.pipeline.start()
        except Exception as e:
            logger.error(f"Failed to init pipeline: {e}")
            self.pipeline = None

    def _build_pipeline_config(self):
        """สร้าง PipelineConfig จาก settings (full config — translation + mixed voice + events)"""
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
                # ★ translation
                auto_translate_enabled=getattr(s, 'auto_translate_enabled', False),
                auto_translate_provider=getattr(s, 'auto_translate_provider', 'google'),
                auto_translate_api_key=getattr(s, 'auto_translate_api_key', ''),
                auto_translate_host=getattr(s, 'auto_translate_host', ''),
                auto_translate_target_lang=getattr(s, 'auto_translate_target_lang', 'th'),
                auto_translate_langs=getattr(s, 'auto_translate_langs', ['en', 'ja', 'ko', 'zh', 'vi', 'id']),
                # ★ mixed voice
                mixed_voice_enabled=getattr(s, 'mixed_voice_enabled', False),
                multilang_enabled=getattr(s, 'multilang_enabled', False),
                multilang_langs=getattr(s, 'multilang_langs', ['en', 'ja', 'ko', 'zh', 'zh-TW', 'fr']),
                # ★ events
                playroom_enabled=getattr(s, 'playroom_enabled', False),
                playroom_triggers=list(getattr(s, 'playroom_triggers', [])),
                # ★ secret code
                secret_code_daily_limit=getattr(s, 'secret_code_daily_limit', 0),
                code_sound_muted=getattr(s, 'code_sound_muted', False),
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
        # ★ เริ่มต้นด้วยความกว้างที่พอดีเห็นครบ (sidebar 300, chat พอประมาณ, events 200)
        splitter.setSizes([300, 580, 200])

        layout.addWidget(splitter, 1)

        # ★ StatusBar
        self.status_bar = StatusBar(self)
        layout.addWidget(self.status_bar)

        # ═══ Connect signals ═══
        self.topbar.settings_clicked.connect(self._open_settings)
        self.topbar.user_manager_clicked.connect(self._open_user_manager)
        self.topbar.overlay_toggle_clicked.connect(self._toggle_overlay)
        self.topbar.mute_toggle_clicked.connect(self._toggle_mute)
        self.topbar.translate_clicked.connect(self._toggle_translate)
        self.topbar.code_mute_clicked.connect(self._toggle_code_mute)
        self.topbar.about_clicked.connect(self._open_about)
        self.topbar.ngreplace_clicked.connect(self._open_ngreplace)
        self.topbar.font_increase_clicked.connect(self._increase_chat_font)
        self.topbar.font_decrease_clicked.connect(self._decrease_chat_font)

        # ═══ Build platform cards ═══
        self._platform_cards = {}
        self._build_platform_cards()

        # ★ gear button → open settings at platforms tab
        self.sidebar.gear_btn.clicked.connect(self._open_platform_settings)
        # ★ toggle platforms section
        self.sidebar.platform_toggle.clicked.connect(self.sidebar.toggle_platforms)

        # ═══ Connect sidebar voice controls ═══
        self.sidebar.voice_combo.currentIndexChanged.connect(self._on_voice_change)
        self.sidebar.vol_slider.valueChanged.connect(self._on_volume_change)
        self.sidebar.rate_slider.valueChanged.connect(self._on_rate_change)
        self.sidebar.voice_download_btn.clicked.connect(self._open_voice_downloader)
        self.sidebar.voice_test_btn.clicked.connect(self._test_voice)
        # ★ refresh voice combo
        self._refresh_voice_combo()

        # ═══ Connect chat panel signals ═══
        self.chat_panel.popout_requested.connect(self._open_popout)
        self.chat_panel.clear_requested.connect(self._clear_chat)
        self.chat_panel.block_user_requested.connect(self._block_user_from_chat)
        self.chat_panel.author_clicked.connect(self._open_author_modal)

        # ═══ Events panel toggle ═══
        self.events_panel.header.clicked.connect(self.events_panel.toggle_collapse)

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
            card.mute_toggled.connect(self._on_platform_mute)
            card.volume_changed.connect(self._on_platform_volume)
            self._platform_cards[plat] = card
            # ★ เพิ่ม status dot ใน topbar
            card._topbar_widget = self.topbar.add_platform_status(label)

    def _on_platform_mute(self, platform, muted):
        """ปิด/เปิดเสียง TTS ของแพลตฟอร์ม"""
        if self.settings:
            muted_key = f'tts_muted_{platform}'
            setattr(self.settings, muted_key, muted)
        label = PLATFORM_LABELS.get(platform, platform)
        state = "ปิด" if muted else "เปิด"
        self.status_bar.set_status(f"🔊 {label}: {state}")

    def _update_platform_count(self):
        """อัปเดตตัวเลขจำนวนแพลตฟอร์มที่เชื่อมต่อใน sidebar"""
        connected = len(self.chat_clients)
        total = len(self._platform_cards)
        self.sidebar.update_platform_count(connected, total)

    def _on_platform_volume(self, platform, volume):
        """ปรับ volume ของแพลตฟอร์ม"""
        if self.settings:
            vol_key = f'tts_volume_{platform}'
            setattr(self.settings, vol_key, volume)

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
            card.set_connecting()

        label = PLATFORM_LABELS.get(platform, platform)
        self._post_system_message(f"🔌 กำลังเชื่อมต่อ {label}...")
        self.status_bar.set_status(f"🔌 กำลังเชื่อมต่อ {label}...")

        # ★ save target + clear manual disconnect
        st = self._reconnect_state.get(platform)
        if st:
            st['target'] = target
            st['manual_disconnect'] = False
            st['attempts'] = 0
            st['last_attempt'] = None

        # ★ connect in background thread (result → QMetaObject.invokeMethod via signal)
        def _bg_connect():
            try:
                client = self._create_client(platform)
                if client:
                    ok = client.connect(target)
                else:
                    ok = False
                    client = None
            except Exception as e:
                logger.error(f"Connect {platform} failed: {e}")
                ok = False
                client = None
            # ★ use signal to marshal back to main thread
            self._connect_result.emit(platform, client, ok)

        threading.Thread(target=_bg_connect, name=f"Connect-{platform}", daemon=True).start()

    def _create_client(self, platform):
        """สร้าง chat client สำหรับแพลตฟอร์ม"""
        on_message, on_status, on_error = self._make_callbacks(platform)
        def on_viewer_count(plat, count):
            self._viewer_counts[plat] = count
            self._viewer_update.emit()  # thread-safe signal

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
            # ★ emit signal (thread-safe)
            self._chat_message.emit(msg)

        def on_status(msg_text):
            self._chat_message.emit(_SystemMsg(f"[{platform}] {msg_text}"))

        def on_error(msg_text):
            self._platform_error.emit(platform, msg_text)

        return on_message, on_status, on_error

    def _on_chat_message(self, msg):
        """รับ message จาก signal (main thread) — render + pipeline + forward"""
        # ★ system status message
        if isinstance(msg, _SystemMsg):
            self.status_bar.set_status(msg.text)
            return
        # ★ record message history
        if self.message_history:
            try:
                self.message_history.record(msg)
            except Exception:
                pass
        # ★ record events
        if getattr(msg, 'event', 'message') != 'message':
            self._record_event(msg, getattr(msg, 'platform', ''))
        # ★ push to chat feed
        self.chat_panel.add_message(msg)
        if hasattr(self, '_popout_window') and self._popout_window:
            self._popout_window.add_message(msg)
        # ★ system message → status bar
        if getattr(msg, 'event', '') == 'system':
            self.status_bar.set_status(msg.text or msg.system_text or '')
        # ★ pipeline (TTS queue)
        if self.pipeline and getattr(msg, 'event', 'message') == 'message':
            try:
                self.pipeline.enqueue(msg)
            except Exception:
                pass
        # ★ forward to composer (overlay)
        self._composer_push_message(msg)

    def _on_connect_result(self, platform, client, ok):
        """รับผล connect จาก signal (main thread)"""
        label = PLATFORM_LABELS.get(platform, platform)
        card = self._platform_cards.get(platform)
        if ok and client:
            self.chat_clients[platform] = client
            if card:
                card.set_connected(True)
            # ★ update topbar dot
            if card and hasattr(card, '_topbar_widget'):
                self.topbar.update_platform_status(card._topbar_widget, True)
            self._post_system_message(f"✅ {label} เชื่อมต่อแล้ว")
            self.status_bar.set_status(f"✅ {label} เชื่อมต่อแล้ว")
        else:
            if card:
                card.set_connected(False)
            self._post_system_message(f"❌ {label} เชื่อมต่อไม่ได้")
            self.status_bar.set_status(f"❌ {label} เชื่อมต่อไม่ได้")
        self._update_platform_count()

    def _on_platform_error_signal(self, platform, error_msg):
        """รับ error จาก signal (main thread)"""
        card = self._platform_cards.get(platform)
        if card:
            card.set_connected(False)
            if hasattr(card, '_topbar_widget'):
                self.topbar.update_platform_status(card._topbar_widget, False)
        label = PLATFORM_LABELS.get(platform, platform)
        self._post_system_message(f"⚠️ {label}: {error_msg}")
        self.status_bar.set_status(f"⚠️ {label}: {error_msg}")
        # ★ mark for reconnect
        st = self._reconnect_state.get(platform)
        if st and not st.get('manual_disconnect'):
            if 'ปิด' in error_msg or 'หลุด' in error_msg:
                st['last_attempt'] = time.time()
        self._update_platform_count()

    def _record_event(self, msg, platform):
        """บันทึก event (sub/bits/raid) → event_log + events panel + donate"""
        event_type = getattr(msg, 'event', 'message')
        author = getattr(msg, 'author', '') or ''
        amount = getattr(msg, 'amount', None)
        # ★ event_log
        if self.event_log:
            try:
                self.event_log.record(platform, event_type, author, amount)
            except Exception:
                pass
        # ★ donate tracker
        if self.donate_tracker and event_type in ('bits', 'donate', 'tip', 'superchat'):
            try:
                self.donate_tracker.record_donation(author, amount or 0, platform, event_type)
            except Exception:
                pass
        # ★ notification (sound)
        if self.notification_manager:
            try:
                self.notification_manager.notify(event_type, author, amount)
            except Exception:
                pass
        # ★ push to events panel
        text = author
        if amount:
            text += f" ({amount})"
        QTimer.singleShot(0, lambda t=event_type, a=text: self.events_panel.add_event(t, a))

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
        # ★ mark manual disconnect (หยุด auto-reconnect)
        st = self._reconnect_state.get(platform)
        if st:
            st['manual_disconnect'] = True
            st['last_attempt'] = None
            st['attempts'] = 0
        self._update_platform_count()

    # ════════════════════════════════════════════════════════════
    # Chat feed (event-driven via signals — ไม่ต้อง poll)
    # ════════════════════════════════════════════════════════════
    def _clear_chat(self):
        """ล้าง chat feed"""
        self.chat_panel.clear_messages()
        if hasattr(self, '_popout_window') and self._popout_window:
            self._popout_window.clear_messages()

    def _block_user_from_chat(self, author_info):
        """บล็อกผู้ใช้จาก context menu — author_info อาจมี ||tts_only suffix"""
        if '||tts_only' in author_info:
            author = author_info.replace('||tts_only', '').strip()
            block_type = "tts_only"
            msg = f"🔇 บล็อก TTS: {author}"
        else:
            author = author_info.strip()
            block_type = "block_all"
            msg = f"🚫 บล็อกผู้ใช้: {author}"
        if self.settings:
            blocked = list(getattr(self.settings, 'blocked_users', []) or [])
            if author not in blocked:
                blocked.append(author)
                self.settings.blocked_users = blocked
                try:
                    from settings import save_settings
                    save_settings(self.settings)
                except Exception:
                    pass
        self._post_system_message(msg)

    def _update_viewer_ui(self):
        """อัปเดตยอดคนดู"""
        total = sum(self._viewer_counts.values())
        self.chat_panel.viewers_label.setText(f"👥 {total:,}")
        if hasattr(self, '_popout_window') and self._popout_window:
            self._popout_window.update_viewers(total)
        # ★ forward to composer
        self._composer_push_viewers(total, dict(self._viewer_counts))

    def _on_msg_translated(self, msg):
        """re-render chat row เมื่อข้อความถูกแปลแล้ว (แสดงคำแปล + ต้นฉบับ)"""
        # ★ main chat
        for row in self.chat_panel._rows:
            if getattr(row, 'msg', None) is msg:
                row.update_translation(msg)
                break
        else:
            # fallback: หาด้วย author + original_text
            extra = getattr(msg, 'extra', {}) or {}
            original = extra.get('original_text', '')
            for row in self.chat_panel._rows:
                row_msg = getattr(row, 'msg', None)
                if row_msg and getattr(row_msg, 'author', '') == getattr(msg, 'author', ''):
                    row_extra = getattr(row_msg, 'extra', {}) or {}
                    if not row_extra.get('translated') and original:
                        row.update_translation(msg)
                        break
        # ★ popout (ถ้าเปิดอยู่)
        if hasattr(self, '_popout_window') and self._popout_window:
            for row in self._popout_window._rows:
                if getattr(row, 'msg', None) is msg:
                    row.update_translation(msg)
                    break

    # ════════════════════════════════════════════════════════════
    # Voice / TTS controls (#3 RVC + #7 Voice test)
    # ════════════════════════════════════════════════════════════
    def _discover_voices(self):
        """ค้นหา RVC voices ที่ติดตั้งแล้ว + edge-tts default"""
        voices = ["Premwadee (edge-tts)"]
        import os
        # ★ หาในหลายที่ (v1 folder + user home + current dir)
        search_dirs = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "rvc_models"),
            os.path.join(os.path.expanduser("~"), ".tts-for-livestream", "rvc_models"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "rvc_models"),  # current dir
        ]
        # ★ หาจาก parent dir ด้วย (กรณี ver2 อยู่ข้าง v1)
        parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        search_dirs.append(os.path.join(parent, "tts-for-livestream", "rvc_models"))

        seen = set()
        for models_dir in search_dirs:
            if not os.path.isdir(models_dir):
                continue
            try:
                for f in sorted(os.listdir(models_dir)):
                    if f.endswith('.pth') and f not in seen:
                        name = os.path.splitext(f)[0]
                        voices.append(f"{name} (RVC)")
                        seen.add(f)
            except Exception:
                pass
        return voices

    def _refresh_voice_combo(self):
        """refresh voice combo ด้วย voices ที่ค้นพบ"""
        self.sidebar.voice_combo.blockSignals(True)
        self.sidebar.voice_combo.clear()
        for v in self._discover_voices():
            self.sidebar.voice_combo.addItem(v)
        current = getattr(self.settings, 'voice_id', '') if self.settings else ''
        if current:
            for i in range(self.sidebar.voice_combo.count()):
                if current in self.sidebar.voice_combo.itemText(i):
                    self.sidebar.voice_combo.setCurrentIndex(i)
                    break
        self.sidebar.voice_combo.blockSignals(False)

    def _on_voice_change(self, index):
        """เปลี่ยนเสียง TTS"""
        if index < 0 or not self.settings:
            return
        text = self.sidebar.voice_combo.itemText(index)
        if '(RVC)' in text:
            voice_id = text.replace(' (RVC)', '').strip()
            self.settings.voice_id = voice_id
            if self.pipeline:
                self.pipeline.config.voice = voice_id
            # ★ หา model path จากหลายที่
            import os
            search_dirs = [
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "rvc_models"),
                os.path.join(os.path.expanduser("~"), ".tts-for-livestream", "rvc_models"),
                os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tts-for-livestream", "rvc_models"),
            ]
            pth_path = None
            for d in search_dirs:
                p = os.path.join(d, f"{voice_id}.pth")
                if os.path.exists(p):
                    pth_path = p
                    break
            if not pth_path:
                self.status_bar.set_status(f"❌ ไม่พบ {voice_id}.pth")
                return
            # index path (optional)
            index_path = pth_path.replace('.pth', '.index')
            if not os.path.exists(index_path):
                index_path = ''
            try:
                from rvc_engine import RVCEngine, RVCParams
                engine = RVCEngine()
                engine.load(pth_path)
                if self.pipeline:
                    pitch = getattr(self.settings, 'rvc_pitch', 0)
                    f0method = getattr(self.settings, 'rvc_f0method', 'rmvpe')
                    params = RVCParams(f0up_key=pitch, f0method=f0method, index_path=index_path)
                    self.pipeline.set_rvc(engine, voice_id, index_path)
                self.status_bar.set_status(f"🎤 เสียง: {voice_id} (RVC)")
            except Exception as e:
                logger.error(f"Failed to load RVC voice: {e}")
                self.status_bar.set_status(f"❌ โหลด RVC ไม่ได้: {e}")
        else:
            self.settings.voice_id = ''
            if self.pipeline:
                self.pipeline.config.voice = ''
                self.pipeline.set_rvc(None, '', '')
            self.status_bar.set_status("🎤 เสียง: Premwadee (edge-tts)")
        try:
            from settings import save_settings
            save_settings(self.settings)
        except Exception:
            pass

    def _on_volume_change(self, value):
        if self.settings:
            self.settings.volume = value
        if self.pipeline:
            self.pipeline.config.volume = value

    def _on_rate_change(self, value):
        if self.settings:
            self.settings.rate = value
        if self.pipeline:
            self.pipeline.config.rate = value

    def _test_voice(self):
        """ทดสอบเสียง TTS"""
        if not self.pipeline:
            return
        import random
        phrases = [
            "สวัสดีครับ ยินดีต้อนรับสู่ห้องสด",
            "ขอบคุณที่เข้ามารับชมนะครับ",
            "วันนี้อากาศดีนะ มีความสุขมาก",
        ]
        phrase = random.choice(phrases)
        try:
            from chat_twitch import ChatMessage
            msg = ChatMessage(platform='test', author='ทดสอบ', text=phrase)
            self.pipeline.enqueue(msg)
            self.status_bar.set_status(f"🔊 ทดสอบ: {phrase}")
        except Exception as e:
            logger.error(f"Voice test failed: {e}")

    def _open_voice_downloader(self):
        """เปิด Voice Downloader dialog"""
        from ui.dialogs.voice_downloader import VoiceDownloaderDialog
        dlg = VoiceDownloaderDialog(self)
        dlg.exec()
        self._refresh_voice_combo()

    def _safe_status(self, msg):
        """thread-safe status update (เรียกจาก game_overlay.py + pipeline)"""
        QTimer.singleShot(0, lambda: self.status_bar.set_status(msg))

    def after(self, ms, callback):
        """Tk compatibility shim — game_overlay.py อ้าง parent_app.after"""
        QTimer.singleShot(ms, callback)

    def _open_game_overlay_settings(self):
        """game_overlay.py อ้าง — เปิด settings"""
        self._open_settings()

    def _update_game_overlay_btn(self):
        """game_overlay.py อ้าง — update button state (no-op ใน v2)"""
        pass

    # ════════════════════════════════════════════════════════════
    # TopBar actions (#6 Translate + #10 OBS + #11 Secret code + #12 Viewer profile + #13 Playroom + #14 Overlay+ + #15 Menu)
    # ════════════════════════════════════════════════════════════
    def _open_settings(self):
        """เปิด Settings dialog"""
        from ui.dialogs.settings import SettingsDialog
        dlg = SettingsDialog(self)
        dlg.settings_changed.connect(self._on_settings_changed)
        dlg.exec()

    def _open_platform_settings(self):
        """เปิด Settings ไปที่แท็บแพลตฟอร์ม"""
        from ui.dialogs.settings import SettingsDialog
        dlg = SettingsDialog(self)
        dlg.settings_changed.connect(self._on_settings_changed)
        # ★ สลับไป section แพลตฟอร์ม (index 0)
        dlg.sidebar.setCurrentRow(0)
        dlg.exec()

    def _on_settings_changed(self):
        """เรียกเมื่อ settings เปลี่ยน"""
        if self.pipeline and self.settings:
            self.pipeline.set_filter(self.settings.to_text_filter())
            # ★ rebuild pipeline config (translation + mixed voice)
            new_config = self._build_pipeline_config()
            self.pipeline.config = new_config
        self.status_bar.set_status("✅ บันทึกการตั้งค่าแล้ว")

    def _open_user_manager(self):
        from ui.dialogs.user_manager import UserManagerDialog
        dlg = UserManagerDialog(self)
        dlg.exec()

    def _open_ngreplace(self):
        from ui.dialogs.ngreplace import NGReplaceDialog
        dlg = NGReplaceDialog(self)
        dlg.exec()

    def _open_about(self):
        from ui.dialogs.about import AboutDialog
        dlg = AboutDialog(self)
        dlg.exec()

    def _open_popout(self):
        if hasattr(self, '_popout_window') and self._popout_window:
            self._close_popout()
            return
        from ui.dialogs.popout import PopoutWindow
        self._popout_window = PopoutWindow(self)
        # ★ copy existing messages to popout
        for row in self.chat_panel._rows:
            if hasattr(row, 'msg'):
                fs = getattr(self, '_chat_font_scale', 0) + 14
                self._popout_window.add_message(row.msg, fs)
        # ★ finished signal → restore chat panel
        self._popout_window.finished.connect(self._close_popout)
        self._popout_window.show()
        # ★ แสดง overlay ทับ chat panel (แทนที่จะซ่อน)
        if not hasattr(self, '_popout_overlay'):
            self._popout_overlay = QLabel("💬 แชทถูกแยกออกไปแล้ว (Popout)\n\nกดปุ่ม ↗ อีกครั้งเพื่อกลับมา")
            self._popout_overlay.setAlignment(Qt.AlignCenter)
            self._popout_overlay.setStyleSheet("color: #9ca3af; font-size: 16px; background-color: #0a0e1a; border: none;")
        # ★ วาง overlay บน chat panel (raise ขึ้นบน)
        self._popout_overlay.setParent(self.chat_panel)
        self._popout_overlay.setGeometry(self.chat_panel.rect())
        self._popout_overlay.show()
        self._popout_overlay.raise_()

    def _close_popout(self):
        """ปิด popout + คืน chat panel หลัก"""
        if hasattr(self, '_popout_window') and self._popout_window:
            self._popout_window.close()
            self._popout_window = None
        if hasattr(self, '_popout_overlay'):
            self._popout_overlay.setParent(None)
            self._popout_overlay.hide()

    def resizeEvent(self, event):
        """resize overlay ตาม chat panel"""
        super().resizeEvent(event)
        if hasattr(self, '_popout_overlay') and self._popout_overlay and self._popout_overlay.isVisible():
            self._popout_overlay.setGeometry(self.chat_panel.rect())

    def _toggle_translate(self):
        """เปิด/ปิดการแปลอัตโนมัติ (#6)"""
        if not self.settings:
            return
        self.settings.auto_translate_enabled = not getattr(self.settings, 'auto_translate_enabled', False)
        if self.pipeline:
            self.pipeline.config.auto_translate_enabled = self.settings.auto_translate_enabled
        state = "เปิด" if self.settings.auto_translate_enabled else "ปิด"
        self.status_bar.set_status(f"🌐 การแปลอัตโนมัติ: {state}")

    def _toggle_code_mute(self):
        """เปิด/ปิดเสียงโค้ดลับ (#11)"""
        if not self.settings:
            return
        self.settings.code_sound_muted = not getattr(self.settings, 'code_sound_muted', False)
        if self.pipeline:
            self.pipeline.config.code_sound_muted = self.settings.code_sound_muted
        state = "ปิด" if self.settings.code_sound_muted else "เปิด"
        self.status_bar.set_status(f"🔔 เสียงโค้ดลับ: {state}")

    def _open_author_modal(self, author):
        """เปิด modal ของผู้ใช้ — แก้ชื่อ / บล็อก / ประวัติข้อความ"""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QScrollArea, QWidget, QFrame
        from PySide6.QtCore import Qt

        dlg = QDialog(self)
        dlg.setWindowTitle(f"👤 {author}")
        dlg.setGeometry(200, 150, 500, 500)
        dlg.setMinimumSize(400, 360)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ★ Header
        header = QFrame()
        header.setFixedHeight(50)
        header.setStyleSheet("background: #131726; border-bottom: 1px solid #2a2f45;")
        hlayout = QHBoxLayout(header)
        hlayout.setContentsMargins(16, 0, 16, 0)
        title = QLabel(f"👤 {author}")
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #f59e0b;")
        hlayout.addWidget(title)
        hlayout.addStretch()
        layout.addWidget(header)

        # ★ Action buttons
        actions = QFrame()
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(16, 8, 16, 8)
        actions_layout.setSpacing(6)

        # ★ Rename
        renames = getattr(self.settings, 'user_renames', {}) or {}
        current_display = renames.get(author.lower(), author)
        rename_entry = QLineEdit(current_display)
        rename_entry.setPlaceholderText("ชื่อที่แสดง")
        actions_layout.addWidget(QLabel("ชื่อ:"))
        actions_layout.addWidget(rename_entry, 1)

        btn_save_name = QPushButton("💾")
        btn_save_name.setObjectName("Primary")
        btn_save_name.setFixedWidth(36)
        def _save_name():
            new_name = rename_entry.text().strip()
            if not self.settings:
                return
            renames = dict(getattr(self.settings, 'user_renames', {}) or {})
            if new_name and new_name != author:
                renames[author.lower()] = new_name
            else:
                renames.pop(author.lower(), None)
            self.settings.user_renames = renames
            try:
                from settings import save_settings
                save_settings(self.settings)
            except Exception:
                pass
            self._post_system_message(f"✏️ เปลี่ยนชื่อ {author} → {new_name}")
        btn_save_name.clicked.connect(_save_name)
        actions_layout.addWidget(btn_save_name)
        layout.addWidget(actions)

        # ★ Block buttons
        block_row = QHBoxLayout()
        block_row.setContentsMargins(16, 0, 16, 8)
        btn_block_all = QPushButton("🚫 บล็อกทุกอย่าง")
        btn_block_all.setObjectName("Danger")
        btn_block_tts = QPushButton("🔇 บล็อก TTS เท่านั้น")
        btn_unblock = QPushButton("✅ ปลดบล็อก")
        btn_block_all.clicked.connect(lambda: (self._block_user_from_chat(author), dlg.accept()))
        btn_block_tts.clicked.connect(lambda: (self._block_user_from_chat(author + "||tts_only"), dlg.accept()))
        btn_unblock.clicked.connect(lambda: self._unblock_user(author))
        block_row.addWidget(btn_block_all)
        block_row.addWidget(btn_block_tts)
        block_row.addWidget(btn_unblock)
        layout.addLayout(block_row)

        # ★ Message history
        hist_label = QLabel("💬 ข้อความล่าสุด:")
        hist_label.setStyleSheet("color: #9ca3af; padding: 8px 16px 4px; font-weight: 600;")
        layout.addWidget(hist_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        clayout = QVBoxLayout(container)
        clayout.setContentsMargins(12, 4, 12, 12)
        clayout.setSpacing(4)
        clayout.setAlignment(Qt.AlignTop)

        # ★ ดึงข้อความจาก message_history + chat rows
        msgs = []
        if self.message_history:
            try:
                msgs = self.message_history.get_messages_by_author(author) or []
            except Exception:
                pass
        # fallback: ดึงจาก chat rows ปัจจุบัน
        if not msgs:
            for row in self.chat_panel._rows:
                if getattr(row, 'msg', None) and getattr(row.msg, 'author', '') == author:
                    msgs.append(row.msg)

        if not msgs:
            empty = QLabel("ยังไม่มีข้อความ")
            empty.setStyleSheet("color: #6b7280; padding: 16px;")
            empty.setAlignment(Qt.AlignCenter)
            clayout.addWidget(empty)
        else:
            for msg in msgs[-50:]:
                text = getattr(msg, 'text', '') or ''
                platform = getattr(msg, 'platform', '')
                row_label = QLabel(f"[{platform}] {text}")
                row_label.setStyleSheet("color: #e5e7eb; padding: 4px; border-bottom: 1px solid rgba(42,47,69,0.3);")
                row_label.setWordWrap(True)
                clayout.addWidget(row_label)

        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        # ★ Close
        btn_close = QPushButton("ปิด")
        btn_close.setFixedWidth(80)
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(16, 8, 16, 8)
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)
        btn_close.clicked.connect(dlg.accept)

        dlg.exec()

    def _unblock_user(self, author):
        """ปลดบล็อกผู้ใช้"""
        if not self.settings:
            return
        blocked = list(getattr(self.settings, 'blocked_users', []) or [])
        if author in blocked:
            blocked.remove(author)
            self.settings.blocked_users = blocked
            try:
                from settings import save_settings
                save_settings(self.settings)
            except Exception:
                pass
        self._post_system_message(f"✅ ปลดบล็อก {author}")

    def _open_playroom_settings(self):
        """เปิด Playroom trigger editor (#13)"""
        from ui.dialogs.playroom_trigger import PlayroomTriggerDialog
        dlg = PlayroomTriggerDialog(self)
        dlg.exec()

    def _open_composer(self):
        """เปิด composer editor ในเบราว์เซอร์"""
        import webbrowser
        port = int(getattr(self.settings, 'composer_port', 8808))
        url = f"http://localhost:{port}/editor"
        webbrowser.open(url)

    def _copy_overlay_url(self):
        """คัดลอก URL ของ overlay server"""
        from PySide6.QtWidgets import QApplication
        port = getattr(self.settings, 'overlay_port', 8765)
        url = f"http://localhost:{port}/"
        QApplication.clipboard().setText(url)
        self.status_bar.set_status(f"📋 คัดลอก URL: {url}")

    def _increase_chat_font(self):
        """เพิ่มขนาด font แชท (#8)"""
        scale = getattr(self, '_chat_font_scale', 0)
        scale = min(scale + 2, 10)
        self._chat_font_scale = scale
        self._apply_chat_font()

    def _decrease_chat_font(self):
        """ลดขนาด font แชท"""
        scale = getattr(self, '_chat_font_scale', 0)
        scale = max(scale - 2, -4)
        self._chat_font_scale = scale
        self._apply_chat_font()

    def _apply_chat_font(self):
        """apply font scale ไปยัง chat rows — re-render ทั้งหมด"""
        scale = getattr(self, '_chat_font_scale', 0)
        base = 14
        size = base + scale
        # ★ เก็บขนาดปัจจุบัน → message ใหม่จะได้ใช้ขนาดนี้
        self.chat_panel._current_font_size = size
        if hasattr(self, '_popout_window') and self._popout_window:
            self._popout_window._current_font_size = size
        # ★ re-render ทุก row (ล้างเก่า + สร้างใหม่ด้วยขนาดใหม่)
        msgs = []
        for row in self.chat_panel._rows:
            if hasattr(row, 'msg'):
                msgs.append(row.msg)
        self.chat_panel.clear_messages()
        for msg in msgs:
            self.chat_panel.add_message(msg, size)
        # ★ re-render popout ด้วย
        if hasattr(self, '_popout_window') and self._popout_window:
            popout = self._popout_window
            popout_msgs = [row.msg for row in popout._rows if hasattr(row, 'msg')]
            popout.clear_messages()
            for msg in popout_msgs:
                popout.add_message(msg, size)
        self.status_bar.set_status(f"🔤 Font: {size}px")

    def _toggle_overlay(self):
        """เปิด/ปิด Game Overlay (ใช้ GameOverlay manager เหมือน v1)"""
        # ★ ถ้ารันอยู่ → ปิด
        if hasattr(self, '_game_overlay') and self._game_overlay and self._game_overlay.is_running:
            try:
                self._game_overlay.stop()
            except Exception:
                pass
            self._game_overlay = None
            self.status_bar.set_status("🔲 Overlay ปิดแล้ว")
            return
        # ★ เปิด (background thread — server + subprocess)
        def _bg_start():
            try:
                from game_overlay import GameOverlay
                ov = GameOverlay(self)
                ok = ov.start()
                QTimer.singleShot(0, lambda: self._on_overlay_started(ok, ov if ok else None))
            except Exception as e:
                logger.error(f"Failed to start overlay: {e}")
                QTimer.singleShot(0, lambda: self.status_bar.set_status(f"❌ Overlay: {e}"))

        threading.Thread(target=_bg_start, name="GameOverlayToggle", daemon=True).start()
        self.status_bar.set_status("⏳ Game Overlay กำลังเปิด...")

    def _on_overlay_started(self, ok, overlay):
        """หลัง Game Overlay เริ่มเสร็จ"""
        if ok and overlay:
            self._game_overlay = overlay
            self.status_bar.set_status("🔲 Overlay เปิดแล้ว")
        else:
            self._game_overlay = None
            self.status_bar.set_status("❌ Overlay เปิดไม่ได้")

    def _toggle_mute(self):
        """เปิด/ปิด TTS"""
        if self.pipeline:
            self.pipeline.toggle_mute()
        muted = getattr(self.pipeline, '_muted', False) if self.pipeline else False
        self.status_bar.set_status("🔇 TTS ปิดเสียงแล้ว" if muted else "🔊 TTS เปิดเสียงแล้ว")

    # ════════════════════════════════════════════════════════════
    # Logic bridges (เรียกจาก widgets)
    # ════════════════════════════════════════════════════════════

    def _maybe_auto_connect(self):
        """auto-connect แพลตฟอร์มที่เปิดไว้ (per-platform checkbox)"""
        if not self.settings:
            return
        auto_map = {
            'twitch': getattr(self.settings, 'auto_connect_twitch', False),
            'youtube': getattr(self.settings, 'auto_connect_youtube', False),
            'mylive': getattr(self.settings, 'auto_connect_mylive', False),
            'tiktok': getattr(self.settings, 'auto_connect_tiktok', False),
            'kick': getattr(self.settings, 'auto_connect_kick', False),
        }
        for plat, auto in auto_map.items():
            if auto and plat in self._platform_cards:
                target = self._get_platform_target(plat)
                if target:
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
        # ★ หยุด TTS engine + pipeline
        if self.pipeline:
            try:
                self.pipeline.stop()
            except Exception:
                pass
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
        # ★ หยุด Game Overlay
        if hasattr(self, '_game_overlay') and self._game_overlay:
            try:
                self._game_overlay.stop()
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
