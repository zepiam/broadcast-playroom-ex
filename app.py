"""app.py — Main application window (QMainWindow)

ประกอบ UI ทั้งหมดเข้าด้วยกัน + เชื่อม logic (chat clients, TTS, pipeline)
"""
import logging
import os
import threading
import time
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QFrame, QLabel, QPushButton, QLineEdit,
    QVBoxLayout, QHBoxLayout, QSplitter, QScrollArea,
    QSizePolicy, QApplication, QMessageBox,
)

from ui.theme import (
    COLOR_BG, COLOR_BG_DARK, COLOR_CARD, COLOR_CARD_HI, COLOR_ACCENT,
    COLOR_ACCENT_HOVER, COLOR_DANGER,
    COLOR_SUCCESS, COLOR_TEXT, COLOR_TEXT_DIM,
    COLOR_BORDER,
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
    _overlay_started_sig = Signal(bool, int)  # ok, ov_id
    _rvc_loaded_sig = Signal(object, str, str)  # engine, voice_id, index_path
    _rvc_failed_sig = Signal(str)  # error
    _game_overlay_cmd_sig = Signal(str)  # command from Qt overlay (toggle_demo, open_settings, etc.)
    # ★ Now Playing — watcher callback มาจาก background thread → ต้องใช้ Qt Signal marshal ไป main thread
    #   (QTimer.singleShot จาก non-Qt thread ไม่ทำงาน → widget เงียบไปเลย)
    _np_data_sig = Signal(object)  # now playing data dict (full or position update)
    # ★ OmniVoice load progress — background thread → main thread (update progress bar)
    _omnivoice_progress_sig = Signal(int, str)  # percent, stage_text
    _omnivoice_ready_sig = Signal()  # emit เมื่อ OmniVoice โหลดเสร็จ + inject แล้ว

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
        self._overlay_started_sig.connect(self._on_overlay_started_sig)
        self._rvc_loaded_sig.connect(self._on_rvc_loaded)
        self._rvc_failed_sig.connect(self._on_rvc_load_failed)
        self._game_overlay_cmd_sig.connect(self._on_game_overlay_cmd)
        self._np_data_sig.connect(self._on_np_data_sig)
        self._omnivoice_progress_sig.connect(self._on_omnivoice_progress)
        self._omnivoice_ready_sig.connect(self._on_omnivoice_ready)

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

        # ═══ Load settings ═══
        from data_dir import get_data_dir
        self._data_dir = get_data_dir()
        from settings import load_settings
        try:
            self.settings = load_settings()
        except Exception:
            self.settings = None

        # ★ Lite build fallback: ถ้า tts_engine=omnivoice แต่ import torch ไม่ได้ → force edge
        #   + ล้าง voice_id ที่เป็น RVC model (Lite ไม่มี RVC → status แสดงผิด + ค้าง)
        #   ★★ ต้องทำก่อน _init_engines เพื่อให้ pipeline config ถูกต้อง
        if getattr(self.settings, 'tts_engine', 'edge') == "omnivoice":
            try:
                import torch  # noqa: F401
            except ImportError:
                self.settings.tts_engine = "edge"
                logger.info("Lite build: torch not available → force edge-tts")
        # ★ ล้าง voice_id ที่เป็น RVC model ถ้าเป็น Lite build (ไม่มี RVC)
        _voice_id = getattr(self.settings, 'voice_id', '')
        if _voice_id and _voice_id not in ('premwadee', 'niwat', ''):
            try:
                import rvc_engine  # noqa: F401
            except ImportError:
                self.settings.voice_id = ''
                logger.info(f"Lite build: cleared RVC voice_id {_voice_id!r} (no RVC available)")

        # ═══ Init engines (pipeline + RVC) ═══
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
        self._last_np_data = {}
        self._obs_watcher = None
        self._start_servers()

        # ═══ Build UI ═══
        self._build_ui()
        # ★ push chat appearance settings ลง ChatRow (ก่อน message แรกเข้า)
        self._apply_chat_appearance()
        # ★ restore topbar state จาก settings
        self._restore_topbar_state()
        # ★ register global hotkeys (Game Overlay + Overlay+)
        self._game_hotkey_active = False
        self._more_overlay_hotkey_active = False
        self._start_all_hotkeys()

        # ═══ Start reconnect watcher (every 1s) ═══
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.timeout.connect(self._check_reconnect)
        self._reconnect_timer.start(1000)

        # ═══ Auto-connect + timers ═══
        QTimer.singleShot(500, self._maybe_auto_connect)

        logger.info("Main window initialized")

        # ★ Auto-load OmniVoice ถ้า settings เป็น omnivoice (เบื้องหลัง + progress bar)
        if getattr(self.settings, 'tts_engine', 'edge') == 'omnivoice':
            QTimer.singleShot(2000, self._auto_load_omnivoice)

        # ★ Auto-check อัพเดทเงียบๆ 10 วินาทีหลังเปิดโปรแกรม (เหมือน v1)
        QTimer.singleShot(10000, self._auto_check_update)

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
                # ★ sync topbar status (ให้สดใส — reconnect สำเร็จ)
                if hasattr(card, '_topbar_widget'):
                    self.topbar.update_platform_status(card._topbar_widget, True)
            st['attempts'] = 0
            st['last_attempt'] = None
            self._post_system_message(f"✅ เชื่อมต่อ {label} ใหม่สำเร็จ")
        else:
            backoff = min(st.get('attempts', 1) * interval, 60)
            st['last_attempt'] = now + backoff - interval
            self._post_system_message(f"❌ ยังเชื่อมต่อ {label} ไม่ได้ จะลองใหม่ใน {int(backoff)} วิ")

    def _post_system_message(self, text):
        """แทรกข้อความระบบเข้า chat feed (main thread only)

        ★ เคารพ toggle 🔔 (show_system_messages) — ถ้าปิด → ไม่แสดงในแชท
        ★ ไม่เคยส่งไป composer/overlay/game overlay (system messages อยู่ใน live chat เท่านั้น)
        """
        # ★ ถ้า toggle ปิด → ข้าม (เฉพาะใน live chat + popout)
        if not getattr(self.settings, 'show_system_messages', True):
            return
        try:
            from chat_twitch import ChatMessage
            msg = ChatMessage(platform='system', author='', text=text, event='system')
            self.chat_panel.add_message(msg)
            if hasattr(self, '_popout_window') and self._popout_window:
                self._popout_window.add_message(msg)
        except Exception:
            pass

    def _toggle_system_messages(self, checked):
        """toggle 🔔 — เปิด/ปิดแสดงสถานะเชื่อมต่อใน live chat"""
        self.settings.show_system_messages = bool(checked)
        try:
            from settings import save_settings
            save_settings(self.settings)
        except Exception:
            pass
        self._update_system_btn_state()

    def _update_system_btn_state(self):
        """อัปเดตสี/state ของปุ่ม 🔔 ตาม toggle"""
        on = bool(getattr(self.settings, 'show_system_messages', True))
        btn = self.chat_panel.btn_system
        if on:
            btn.setStyleSheet(
                "font-size: 14px; padding: 0px; "
                "background-color: #7c3aed; color: white; border: none; border-radius: 4px;"
            )
            btn.setToolTip("แสดงสถานะเชื่อมต่อในแชท: เปิด (คลิกเพื่อปิด)")
        else:
            btn.setStyleSheet(
                "font-size: 14px; padding: 0px; "
                "background-color: transparent; color: #6b7280; border: none; border-radius: 4px;"
            )
            btn.setToolTip("แสดงสถานะเชื่อมต่อในแชท: ปิด (คลิกเพื่อเปิด)")

    # ════════════════════════════════════════════════════════════
    # Code Sound mute (ปิดเสียงโค้ดลับ)
    # ════════════════════════════════════════════════════════════
    def _on_code_mute_toggled(self, muted):
        """toggle code sound mute จากปุ่มใน chat panel"""
        if self.settings:
            self.settings.code_sound_muted = muted
            try:
                from settings import save_settings
                save_settings(self.settings)
            except Exception:
                pass
        if self.pipeline:
            self.pipeline.config.code_sound_muted = muted
        # ★ sync button checked state + update visual
        self.chat_panel.btn_code_mute.setChecked(muted)
        self._update_code_mute_btn()
        state = "ปิด" if muted else "เปิด"
        self.status_bar.set_status(f"🎟 เสียงโค้ดลับ: {state}")

    def _update_code_mute_btn(self):
        """อัปเดตสี/icon ปุ่ม code mute ตาม state"""
        muted = self.chat_panel.btn_code_mute.isChecked()
        if muted:
            self.chat_panel.btn_code_mute.setText("🎟")
            self.chat_panel.btn_code_mute.setStyleSheet(
                "font-size: 14px; padding: 0px; background-color: #ef4444; border: none; border-radius: 4px;"
            )
            self.chat_panel.btn_code_mute.setToolTip("เสียงโค้ดลับ: ปิด (คลิกเพื่อเปิด)")
        else:
            self.chat_panel.btn_code_mute.setText("🎟")
            self.chat_panel.btn_code_mute.setStyleSheet("font-size: 14px; padding: 0px;")
            self.chat_panel.btn_code_mute.setToolTip("เสียงโค้ดลับ: เปิด (คลิกเพื่อปิด)")

    def _save_splitter_sizes(self):
        """บันทึกความกว้าง sidebar/chat/events + events collapsed state"""
        import json, os
        layout_path = os.path.join(self._data_dir, "layout.json")
        try:
            data = {
                'splitter_sizes': self.splitter.sizes(),
                'events_collapsed': getattr(self.events_panel, '_collapsed', False),
            }
            with open(layout_path, 'w', encoding='utf-8') as f:
                json.dump(data, f)
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
        # ★ OBS WebSocket auto-refresh (ถ้าเปิดไว้) — หน่วง 3 วิ หลัง composer start
        QTimer.singleShot(3000, self._obs_ws_auto_refresh)

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
        """เริ่ม Now Playing watcher (อ่านเพลงจาก Windows System Media)

        ★ callback มาจาก background thread → ใช้ Qt Signal (_np_data_sig) marshal ไป main thread
          (QTimer.singleShot จาก non-Qt thread ไม่ทำงาน)
        """
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
                self._np_data_sig.emit(data)  # ★ marshal ไป main thread

            def _on_np_position(pos, dur, playing):
                data = {"position": pos, "duration": dur, "is_playing": playing}
                self._np_data_sig.emit(data)  # ★ marshal ไป main thread

            self._np_watcher = NowPlayingWatcher(on_change=_on_np_change, on_position=_on_np_position)
            # ★ apply np_source ที่เคยบันทึกไว้ (จาก composer_widgets) ก่อน start
            self._sync_np_source_to_watcher(getattr(self.settings, 'composer_widgets', None))
            self._np_watcher.start()
            logger.info("Now Playing watcher started")
        except Exception as e:
            logger.error(f"Failed to start NP watcher: {e}")
            self._np_watcher = None

    def _on_np_data_sig(self, data):
        """slot: now playing data จาก watcher (รันใน main thread) → forward ไป composer"""
        self._composer_push_now_playing(data)

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

    # ═══ OBS WebSocket auto-refresh ═══
    def _obs_ws_auto_refresh(self):
        """★ OBS WebSocket persistent watcher — เชื่อมค้างไว้ + auto-retry จนกว่าจะติด

        แก้ปัญหา: เปิด OBS ก่อน Broadcast Playroom → browser source cache หน้าเก่า → overlay ไม่แสดง
        เมื่อเชื่อมติด → refresh browser sources ที่ URL ชี้ overlay ของเรา (cache-bust ?v=ts)

        ★ OBSWatcher callback มาจาก background thread → ใช้ status bar ผ่าน lambda ที่ marshal เอง
          (status_bar.set_status รับข้อความเข้า queue ที่ timer อ่าน → thread-safe)
        """
        if not getattr(self.settings, 'obs_ws_enabled', False):
            return
        try:
            from obs_refresh import OBSWatcher

            host = getattr(self.settings, 'obs_ws_host', 'localhost')
            port = int(getattr(self.settings, 'obs_ws_port', 4455))
            pw = getattr(self.settings, 'obs_ws_password', '')

            # ★ หยุด watcher เก่าถ้ามี (ตอน re-call จาก settings change)
            old = getattr(self, '_obs_watcher', None)
            if old:
                old.stop()

            self._obs_watcher = OBSWatcher(
                host=host, port=port, password=pw,
                on_connected=lambda: logger.info("OBS WS connected"),
                on_refreshed=lambda n: logger.info(f"OBS WS refreshed {n} source(s)"),
                on_status=lambda msg: self.status_bar.set_status(msg),
            )
            self._obs_watcher.start()
            logger.info(f"OBS WS watcher started (host={host}:{port})")
        except Exception as e:
            logger.error(f"OBS WS watcher error: {e}")

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
        """callback จาก composer editor → persist widgets + sync np_source ไป watcher"""
        try:
            self.settings.composer_widgets = list(widgets)
            if canvas_size in ("720p", "1080p"):
                self.settings.composer_canvas_size = canvas_size
            from settings import save_settings
            save_settings(self.settings)
            # ★ sync np_source จาก now_playing widget ตัวแรกที่เจอ → watcher
            #   (ผู้ใช้เลือก "เฉพาะ Spotify/YTMusic/browser" ใน composer UI → watcher ต้องรู้)
            self._sync_np_source_to_watcher(widgets)
        except Exception as e:
            logger.error(f"Failed to save composer widgets: {e}")

    def _sync_np_source_to_watcher(self, widgets):
        """อ่าน np_source จาก now_playing widget → set_source_filter() ให้ watcher"""
        try:
            if not self._np_watcher:
                return
            src = "auto"
            for w in (widgets or []):
                if isinstance(w, dict) and w.get("type") == "now_playing":
                    src = w.get("np_source", "auto") or "auto"
                    break
            self._np_watcher.set_source_filter(src)
        except Exception:
            pass

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
        """โหลด TTS engine + pipeline (settings โหลดแล้วใน __init__ ก่อน fallback)"""
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
        self._omnivoice_engine = None  # ★ OmniVoice (lazy load — None = ยังไม่โหลด)
        try:
            from chat_queue import ChatPipeline
            config = self._build_pipeline_config()
            self.pipeline = ChatPipeline(
                self.tts_engine, self.audio_player, config,
                omnivoice_engine=None,  # ★ จะ inject ทีหลังเมื่อโหลดเสร็จ
            )
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
                # ★ TTS engine choice
                tts_engine=getattr(s, 'tts_engine', 'edge'),
                omnivoice_voice=getattr(s, 'omnivoice_voice', 'female'),
                edge_voice=getattr(s, 'edge_voice', 'premwadee'),
                omnivoice_skip_enabled=bool(getattr(s, 'omnivoice_skip_enabled', True)),
                omnivoice_skip_min_length=int(getattr(s, 'omnivoice_skip_min_length', 3)),
                omnivoice_short_whitelist=list(getattr(s, 'omnivoice_short_whitelist', ["ได้", "มี", "ไป"])),
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
                # ★ viewer command ([x2]/[p1]/[v50] chat prefix)
                viewer_cmd_enabled=getattr(s, 'viewer_cmd_enabled', False),
                viewer_cmd_cooldown=getattr(s, 'viewer_cmd_cooldown', 5.0),
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
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(1)
        self.splitter.setChildrenCollapsible(False)

        self.sidebar = Sidebar(self)
        self.chat_panel = ChatPanel(self)
        self.events_panel = EventsPanel(self)

        self.splitter.addWidget(self.sidebar)
        self.splitter.addWidget(self.chat_panel)
        self.splitter.addWidget(self.events_panel)
        self.splitter.setStretchFactor(0, 0)  # sidebar fixed
        self.splitter.setStretchFactor(1, 1)  # chat expands
        self.splitter.setStretchFactor(2, 0)  # events fixed

        # ★ restore saved splitter sizes (บันทึกความกว้างที่ user ตั้งไว้)
        import json, os
        layout_path = os.path.join(self._data_dir, "layout.json")
        saved_sizes = None
        try:
            if os.path.exists(layout_path):
                with open(layout_path, encoding='utf-8') as f:
                    data = json.load(f)
                    saved_sizes = data.get('splitter_sizes')
        except Exception:
            pass
        if saved_sizes and len(saved_sizes) == 3:
            # ★ clamp sidebar width ให้อยู่ใน range ใหม่ (240-340) — กันอ่านค่าเก่าที่กว้างกว่า
            sb_min = self.sidebar.minimumWidth()
            sb_max = self.sidebar.maximumWidth()
            if saved_sizes[0] > sb_max or saved_sizes[0] < sb_min:
                saved_sizes = [270, saved_sizes[1] + (saved_sizes[0] - 270), saved_sizes[2]]
            self.splitter.setSizes(saved_sizes)
        else:
            self.splitter.setSizes([270, 630, 200])

        # ★ save splitter sizes เมื่อ user ขยาย/หด
        self.splitter.splitterMoved.connect(self._save_splitter_sizes)

        # ★ restore events panel collapsed state
        events_collapsed = False
        try:
            if os.path.exists(layout_path):
                with open(layout_path, encoding='utf-8') as f:
                    data = json.load(f)
                    events_collapsed = data.get('events_collapsed', False)
        except Exception:
            pass
        if events_collapsed:
            QTimer.singleShot(100, self.events_panel.toggle_collapse)

        layout.addWidget(self.splitter, 1)

        # ★ Floating "‹" button — ลอยขอบขวาของ main window ตอน events panel ซ่อน
        #   กด → โชว์ events panel กลับมา (ตอนโชว์ panel ปุ่มนี้ซ่อน)
        self._events_show_btn = QPushButton("‹", central)
        self._events_show_btn.setObjectName("IconButton")
        self._events_show_btn.setFixedSize(22, 80)
        self._events_show_btn.setCursor(Qt.PointingHandCursor)
        self._events_show_btn.setToolTip("แสดงแผง Events")
        self._events_show_btn.setStyleSheet("""
            QPushButton {
                border: none;
                border-top-left-radius: 6px;
                border-bottom-left-radius: 6px;
                background-color: #1a1f33;
                font-size: 18px;
                font-weight: 700;
                color: #9ca3af;
                padding: 0;
            }
            QPushButton:hover { color: #f59e0b; background-color: #252b42; }
        """)
        self._events_show_btn.clicked.connect(self.events_panel.expand)
        self._events_show_btn.hide()  # ★ ซ่อนตอนเริ่ม (โชว์เมื่อ events ถูก collapse)

        # ★ StatusBar
        self.status_bar = StatusBar(self)
        layout.addWidget(self.status_bar)

        # ═══ Connect TopBar signals ═══
        self.topbar.settings_clicked.connect(self._open_settings)
        # TTS toggle + volume
        self.topbar.tts_toggled.connect(self._on_tts_toggled)
        self.topbar.volume_changed.connect(self._on_tts_volume)
        # Composer (Canvas Overlay)
        self.topbar.composer_toggled.connect(self._toggle_composer)
        self.topbar.copy_overlay_url.connect(self._copy_overlay_url)
        # Translate
        self.topbar.translate_mode_changed.connect(self._on_translate_mode_changed)
        self.topbar.translate_settings.connect(lambda: self._open_settings_at("translate"))
        # Game Overlay
        self.topbar.game_overlay_toggled.connect(self._toggle_overlay)
        self.topbar.game_overlay_edit.connect(self._toggle_overlay_frames)
        self.topbar.game_overlay_settings.connect(self._open_game_overlay_settings)
        # Overlay+
        self.topbar.overlay_plus_toggled.connect(self._toggle_more_overlays)
        self.topbar.overlay_plus_edit.connect(self._toggle_more_overlay_edit)
        self.topbar.overlay_plus_settings.connect(lambda: self._open_settings_at("overlay_plus"))
        # Viewer Overlay (ใน Game Overlay dropdown)
        self.topbar.viewer_overlay_toggled.connect(self._toggle_viewer_overlay)
        # User manager (เก็บไว้)
        self.topbar.user_manager_clicked.connect(self._open_user_manager)

        # ═══ Build platform cards ═══
        self._platform_cards = {}
        self._build_platform_cards()

        # ★ gear button → open settings at platforms tab
        self.sidebar.gear_btn.clicked.connect(self._open_platform_settings)
        # ★ toggle platforms section
        self.sidebar.platform_toggle.clicked.connect(self.sidebar.toggle_platforms)

        # ═══ Connect sidebar voice controls ═══
        # ★ voice panel ใหม่ — text toggles (engine + base voice) + RVC combo
        self.sidebar.engine_btn_azure.clicked.connect(lambda: self._on_engine_toggle("edge"))
        self.sidebar.engine_btn_omni.clicked.connect(lambda: self._on_engine_toggle("omnivoice"))
        # ★ base voice = text toggle (หญิง/ชาย) — ส่ง voice key ตรงๆ
        self.sidebar.voice_btn_female.clicked.connect(lambda: self._on_base_voice_click("female"))
        self.sidebar.voice_btn_male.clicked.connect(lambda: self._on_base_voice_click("male"))
        # ★ ใช้ activated (ยิงเฉพาะตอน user เลือกจาก popup ไม่ใช่ programmatic)
        #   แก้ปัญหา Windows combo ต้องดับเบิ้ลคลิก — activated ยิงทันทีที่เลือก
        self.sidebar.rvc_combo.activated.connect(lambda idx: self._on_rvc_change(idx))
        self.sidebar.vol_slider.valueChanged.connect(self._on_volume_change)
        self.sidebar.rate_slider.valueChanged.connect(self._on_rate_change)
        self.sidebar.pitch_slider.valueChanged.connect(self._on_pitch_change)
        self.sidebar.voice_download_btn.clicked.connect(self._open_voice_downloader)
        self.sidebar.voice_test_btn.clicked.connect(self._test_voice)
        # ★ refresh voice panel button → rescan + rebuild dropdowns
        self.sidebar.voice_refresh_btn.clicked.connect(lambda: self._refresh_voice_panel())
        # ★ initial refresh
        self._refresh_voice_panel()

        # ★ restore slider values จาก settings (volume/rate/pitch — กัน default ทุกครั้ง)
        #   blockSignals กัน feedback loop (setValue จะ trigger valueChanged → save ซ้ำ)
        #   อัปเดต value label ด้วยมือ (เพราะ blockSignals กัน valueChanged ที่อัปเดต label)
        if self.settings:
            for slider, key, default, label, fmt in [
                (self.sidebar.vol_slider, 'volume', 100, self.sidebar.vol_val_label, '{:d}'),
                (self.sidebar.rate_slider, 'rate', 0, self.sidebar.rate_val_label, '{:+d}'),
                (self.sidebar.pitch_slider, 'rvc_pitch', 0, self.sidebar.pitch_val_label, '{:+d}'),
            ]:
                val = int(getattr(self.settings, key, default))
                slider.blockSignals(True)
                slider.setValue(val)
                slider.blockSignals(False)
                label.setText(fmt.format(val))

        # ═══ Connect chat panel signals ═══
        self.chat_panel.popout_requested.connect(self._open_popout)
        self.chat_panel.clear_requested.connect(self._clear_chat)
        self.chat_panel.block_user_requested.connect(self._block_user_from_chat)
        self.chat_panel.author_clicked.connect(self._open_author_modal)
        # ★ font buttons (อยู่ใน chat panel header ไม่ใช่ topbar)
        self.chat_panel.font_dec_btn.clicked.connect(self._decrease_chat_font)
        self.chat_panel.font_inc_btn.clicked.connect(self._increase_chat_font)
        # ★ system message toggle (🔔 ข้าง A+/A-)
        self.chat_panel.btn_system.setChecked(bool(getattr(self.settings, 'show_system_messages', True)))
        self.chat_panel.btn_system.toggled.connect(self._toggle_system_messages)
        # update visual state
        self._update_system_btn_state()
        # ★ Live Chat Settings gear (⚙ ขวาสุด)
        self.chat_panel.settings_clicked.connect(self._open_live_chat_settings)
        # ★ Code Mute (ปิดเสียงโค้ดลับ)
        self.chat_panel.code_mute_toggled.connect(self._on_code_mute_toggled)
        # ★ restore code mute state
        self.chat_panel.btn_code_mute.setChecked(getattr(self.settings, 'code_sound_muted', False))
        self._update_code_mute_btn()

        # ═══ Events panel toggle ═══
        # ★ btn_collapse/btn_expand จัดการ collapse/expand ภายในตัว
        #   เราแค่ listen collapsed_toggled เพื่อ save state
        self.events_panel.collapsed_toggled.connect(self._on_events_collapsed)

    def _on_events_collapsed(self, collapsed):
        """events panel collapse/expand → โชว์/ซ่อน floating button + save state"""
        if collapsed:
            # ★ ซ่อน events_panel แล้ว → โชว์ floating button (ลอยขอบขวา)
            self._events_show_btn.show()
            self._position_events_show_btn()
        else:
            # ★ โชว์ events_panel กลับมา → ซ่อน floating button
            self._events_show_btn.hide()
        self._save_splitter_sizes()

    def _position_events_show_btn(self):
        """จัดตำแหน่ง floating button ให้ลอยขอบขวา กลางความสูง (ใต้ topbar เหนือ statusbar)"""
        if not hasattr(self, '_events_show_btn'):
            return
        btn = self._events_show_btn
        # ★ x = ขอบขวาของ window, y = กลางพื้นที่ body
        btn_w = btn.width()
        btn_h = btn.height()
        win_w = self.width()
        win_h = self.height()
        topbar_h = self.topbar.height() if hasattr(self, 'topbar') else 0
        status_h = self.status_bar.height() if hasattr(self, 'status_bar') else 0
        body_h = win_h - topbar_h - status_h
        x = win_w - btn_w
        y = topbar_h + max(0, (body_h - btn_h) // 2)
        btn.move(x, y)
        btn.raise_()

    def _build_platform_cards(self):
        """สร้าง card สำหรับแต่ละแพลตฟอร์ม + เชื่อม connect signal"""
        # ★ อ่านว่าแสดงแพลตฟอร์มไหนบ้าง (จาก settings.show_*)
        show_map = {
            'twitch': getattr(self.settings, 'show_twitch', True),
            'youtube': getattr(self.settings, 'show_youtube', True),
            'mylive': getattr(self.settings, 'show_mylive', True),
            'tiktok': getattr(self.settings, 'show_tiktok', False),
            'kick': getattr(self.settings, 'show_kick', False),
        }

        for plat in PLATFORM_ORDER:
            if not show_map.get(plat, True):
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
            # ★ status จาก client → ทั้ง status bar + chat feed (เหมือน v1)
            #    สถานะสำคัญ เช่น "✅ เชื่อมต่อ Twitch", "⚪ ยกเลิกการเชื่อมต่อ",
            #    "⚠️ TikTok ถูกตัดการเชื่อมต่อ", "⏳ กำลังโหลดหน้า MyLive..."
            #    (client ฝังชื่อแพลตฟอร์มในข้อความแล้ว → ไม่ต้อง prefix ซ้ำ)
            self._chat_message.emit(_SystemMsg(msg_text))
            if any(prefix in msg_text for prefix in ('✅', '⚪', '⚠️', '❌', '🔄', '⏳', 'หลุด', 'ปิด', 'ตัด')):
                self._post_system_message(msg_text)

        def on_error(msg_text):
            self._platform_error.emit(platform, msg_text)

        return on_message, on_status, on_error

    def _on_chat_message(self, msg):
        """รับ message จาก signal (main thread) — render + pipeline + forward"""
        # ★ system status message
        if isinstance(msg, _SystemMsg):
            self.status_bar.set_status(msg.text)
            return
        # ★ Viewer command prefix ([x2]/[p1]/[v50]) → strip ออกจาก display + เก็บ override
        #   pipeline จะ apply ตอน TTS (ถ้า user เปิด viewer_cmd_enabled)
        #   prefix ถูก strip จาก text/raw_text/segments → Live Chat/Overlay ไม่เห็น prefix
        if (getattr(self.settings, 'viewer_cmd_enabled', False)
                and getattr(msg, 'event', 'message') == 'message'
                and (msg.text or '').strip()):
            try:
                from chat_queue import parse_viewer_command_prefix
                cleaned, override = parse_viewer_command_prefix(msg.text or '')
                if override is not None:
                    msg.text = cleaned
                    if msg.extra is None:
                        msg.extra = {}
                    msg.extra["_viewer_override"] = override
                    if msg.extra.get("raw_text"):
                        msg.extra["raw_text"] = cleaned
                    if msg.extra.get("segments"):
                        # ★ strip เฉพาะ text segment แรก (prefix อยู่ต้นข้อความจริง)
                        for seg in msg.extra["segments"]:
                            if seg.get("type") == "text":
                                seg_first, _ = parse_viewer_command_prefix(seg.get("content", ''))
                                seg["content"] = seg_first
                                break
            except Exception:
                pass
        # ★ record message history
        if self.message_history:
            try:
                # ★ สกัด emote names + URLs สำหรับแสดงใน log/Modal
                emote_str = ""
                emote_url_str = ""
                extra = getattr(msg, 'extra', None) or {}
                emotes_list = extra.get("emotes") or []
                if emotes_list:
                    names = [e.get("name", "") for e in emotes_list if e.get("name")]
                    urls = [e.get("url", "") for e in emotes_list if e.get("url")]
                    emote_str = " ".join(names)
                    emote_url_str = "|".join(urls)
                self.message_history.record(
                    author=getattr(msg, 'author', ''),
                    platform=getattr(msg, 'platform', ''),
                    text=getattr(msg, 'text', ''),
                    emotes=emote_str,
                    emote_urls=emote_url_str,
                )
            except Exception:
                pass
        # ★ record events
        if getattr(msg, 'event', 'message') != 'message':
            self._record_event(msg, getattr(msg, 'platform', ''))
        # ★ Blocklist check — ถ้า user ถูก block_all → ไม่แสดงใน Live Chat + ไม่อ่าน
        if (getattr(msg, 'event', 'message') == 'message'
                and self.pipeline and self.pipeline._filter is not None
                and msg.author):
            try:
                if self.pipeline._filter.is_user_blocked(msg.author):
                    # เช็คว่าเป็น block_all (hide_overlay) หรือ block_tts
                    user_info = self.pipeline._filter._users_map.get(msg.author.lower(), {})
                    if user_info.get('hide_overlay', True):
                        return  # block_all → ไม่แสดงเลย (เหมือน NG Words)
            except Exception:
                pass
        # ★ NG Words check — ถ้าติดคำต้องห้าม → ไม่แสดงใน Live Chat + ไม่อ่าน
        if (getattr(msg, 'event', 'message') == 'message'
                and self.pipeline and self.pipeline._filter is not None
                and msg.text):
            try:
                filtered = self.pipeline._filter.filter_text(msg.text)
                if filtered is None:
                    return  # banned → ไม่แสดง + ไม่อ่าน
                msg.text = filtered
            except Exception:
                pass
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
        # ★ system messages (สถานะเชื่อมต่อ ✅/⚪/⚠️) → ห้ามส่งไป composer + OBS overlay เด็ดขาด
        is_system = (getattr(msg, 'event', '') == 'system')
        if not is_system:
            # ★ forward to composer (Canvas overlay — includes playroom widget + emote party widget)
            self._composer_push_message(msg)
            self._composer_push_emotes(msg)
            # ★ forward to overlay server (OBS overlay)
            self._overlay_push_message(msg)
        # ★ forward to game overlay (ถ้าเปิดอยู่) — system messages ตาม toggle game_overlay_show_system
        if hasattr(self, '_game_overlay') and self._game_overlay and self._game_overlay.is_running:
            if is_system and not getattr(self.settings, 'game_overlay_show_system', False):
                pass  # ★ system message + toggle ปิด → ข้าม
            else:
                try:
                    self._game_overlay.add_row(msg)
                except Exception:
                    pass

    def _composer_push_emotes(self, msg):
        """สกัด emote จาก message → push ไป Emote Party widget"""
        if self.composer_server is None:
            return
        try:
            extra = getattr(msg, 'extra', {}) or {}
            has_ep = any(
                w.get("type") == "emote_party" and w.get("enabled", True)
                for w in getattr(self.settings, "composer_widgets", []) or []
            )
            if not has_ep:
                return
            emotes = []
            # Twitch emotes
            for em in (extra.get("emotes") or []):
                eid = em.get("id")
                url = em.get("url", "")
                if url:
                    emotes.append({"url": url, "text": "", "source": "twitch"})
                elif eid is not None:
                    emotes.append({"url": f"/emote/{eid}", "text": "", "source": "twitch"})
            # Segments (YouTube/TikTok/MyLive)
            for seg in (extra.get("segments") or []):
                if isinstance(seg, dict) and seg.get("type") == "emote":
                    url = seg.get("url", "") or seg.get("src", "")
                    if url:
                        emotes.append({"url": url, "text": "", "source": getattr(msg, 'platform', '')})
            # Unicode emoji
            any_ep_emoji = any(
                w.get("type") == "emote_party" and w.get("enabled", True) and w.get("ep_emoji_enabled", True)
                for w in getattr(self.settings, "composer_widgets", []) or []
            )
            if any_ep_emoji:
                raw_text = extra.get("raw_text") or getattr(msg, 'text', '') or ''
                emoji_groups = self._extract_emoji_groups(raw_text)
                for eg in emoji_groups:
                    emotes.append({"url": "", "text": eg, "source": "emoji"})
            if emotes:
                self.composer_server.push_emote_party(emotes)
        except Exception:
            pass

    @staticmethod
    def _extract_emoji_groups(text):
        """สกัด emoji จาก text"""
        if not text:
            return []
        result = []
        current = []
        def _is_emoji_cp(cp):
            return ((0x1F300 <= cp <= 0x1FAFF) or (0x2600 <= cp <= 0x27BF) or
                    (0x1F600 <= cp <= 0x1F64F) or (0x1F900 <= cp <= 0x1F9FF) or
                    (0x2B00 <= cp <= 0x2BFF) or (0x2300 <= cp <= 0x23FF))
        def _is_modifier_cp(cp):
            return (cp == 0x200D or cp == 0xFE0F or
                    (0x1F3FB <= cp <= 0x1F3FF) or (0xE0020 <= cp <= 0xE007F))
        for ch in text:
            cp = ord(ch)
            if _is_emoji_cp(cp):
                current.append(ch)
            elif _is_modifier_cp(cp) and current:
                current.append(ch)
            else:
                if current:
                    result.append("".join(current))
                    current = []
        if current:
            result.append("".join(current))
        filtered = []
        for em in result:
            stripped = em.replace("\uFE0F", "").replace("\u200D", "").strip()
            if not stripped or stripped.isdigit() or stripped in ("#", "*"):
                continue
            filtered.append(em)
        return filtered

    def _overlay_push_message(self, msg):
        """forward chat message ไป overlay server (OBS + game overlay)"""
        if self.overlay_server is None:
            return
        try:
            payload = self._serialize_msg_for_overlay(msg)
            if payload:
                self.overlay_server.push_message(payload)
        except Exception:
            pass

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
                # ★ sync topbar status (ให้จางลง — connect ล้มเหลว)
                if hasattr(card, '_topbar_widget'):
                    self.topbar.update_platform_status(card._topbar_widget, False)
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
                self.event_log.record(platform, author, event_type, amount)
            except Exception:
                pass
        # ★ donate tracker
        if self.donate_tracker and event_type in ('bits', 'donate', 'tip', 'superchat'):
            try:
                self.donate_tracker.record_donation(author, platform, event_type, amount or 0)
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

        # ★ push to Live Chat + Popout as event row (เหมือน v1 — ไม่ใช่ system message)
        #   แต่ไม่ส่ง overlay/composer (event เป็นของ Live Chat เท่านั้น)
        event_labels = {
            'sub': '⭐ Sub', 'resub': '🔁 Resub', 'bits': '💎 Bits',
            'raid': '🚀 Raid', 'follow': '❤️ Follow', 'superchat': '💎 SuperChat',
            'gift': '🎁 Gift', 'membership': '🎖️ Membership', 'sponsor': '🤝 Sponsor',
            'donate': '💰 Donate', 'tip': '💰 Tip', 'like': '👍 Like',
            'share': '📢 Share', 'subgift': '🎁 Subgift',
        }
        label = event_labels.get(event_type, event_type)
        amount_str = f" ×{amount}" if amount else ""
        event_text = f"{label}: {author}{amount_str}"
        # ★ สร้าง event message (ไม่ใช่ system) เพื่อแสดงเป็น event row
        try:
            from chat_twitch import ChatMessage
            event_msg = ChatMessage(
                platform=platform,
                author=author,
                text=event_text,
                event=event_type,
            )
            event_msg.amount = amount or 0
            # ★ แสดงใน Live Chat + Popout เท่านั้น (ไม่ enqueue TTS, ไม่ส่ง overlay)
            self.chat_panel.add_message(event_msg)
            if hasattr(self, '_popout_window') and self._popout_window:
                self._popout_window.add_message(event_msg)
        except Exception:
            pass

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
            # ★ sync topbar status (ให้จางลง — disconnected)
            if hasattr(card, '_topbar_widget'):
                self.topbar.update_platform_status(card._topbar_widget, False)
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
        """บล็อกผู้ใช้จาก context menu — author_info อาจมี ||tts_only suffix

        ★ tts_only = ไม่อ่าน TTS แต่ยังแสดงในแชท/overlay (hide_overlay=False)
        ★ block_all = ไม่อ่าน + ไม่แสดงใน overlay (hide_overlay=True)
        ★ sync ไป pipeline filter ทันที (กัน TTS ยังอ่านอยู่)
        """
        if '||tts_only' in author_info:
            author = author_info.replace('||tts_only', '').strip()
            hide_overlay = False  # tts_only = ยังแสดงใน overlay
            msg = f"🔇 บล็อก TTS: {author}"
        else:
            author = author_info.strip()
            hide_overlay = True  # block_all = ไม่แสดงใน overlay ด้วย
            msg = f"🚫 บล็อกผู้ใช้: {author}"
        if self.settings:
            # ★ เพิ่มเข้า settings.blocked_users (format: list[dict])
            blocked = list(getattr(self.settings, 'blocked_users', []) or [])
            author_lower = author.strip().lower()
            # check ซ้ำ
            already = False
            for u in blocked:
                if isinstance(u, dict) and u.get('name', '').strip().lower() == author_lower:
                    already = True
                    break
                elif isinstance(u, str) and u.strip().lower() == author_lower:
                    already = True
                    break
            if not already:
                blocked.append({"name": author, "hide_overlay": hide_overlay})
                self.settings.blocked_users = blocked
                try:
                    from settings import save_settings
                    save_settings(self.settings)
                except Exception:
                    pass
            # ★ sync ไป pipeline filter ทันที — กัน TTS ยังอ่านอยู่
            if self.pipeline:
                try:
                    self.pipeline.set_filter(self.settings.to_text_filter())
                    # ★ ล้างคิวของ user ที่บล็อก ทันที (กันอ่านต่อ)
                    self.pipeline.purge_blocked_user(author)
                except Exception:
                    pass
        self._post_system_message(msg)

    def _update_viewer_ui(self):
        """อัปเดตยอดคนดู — chat panel + popout + viewer overlay + composer

        ★ _viewer_counts = {platform: count} เช่น {'twitch': 50, 'youtube': 30}
        ★ ส่ง platform names ให้ composer เสมอ (แม้ count=0) → overlay แสดง platform icons
        """
        total = sum(self._viewer_counts.values())
        # ★ respect viewers hidden toggle
        if not getattr(self.chat_panel, '_viewers_hidden', False):
            self.chat_panel.viewers_label.setText(f"👥 {total:,}")
        self.chat_panel._last_viewer_count = total
        if hasattr(self, '_popout_window') and self._popout_window:
            self._popout_window.update_viewers(total)
        # ★ push ไป Viewer Overlay (ถ้าเปิดอยู่)
        if hasattr(self, '_viewer_overlay') and self._viewer_overlay and self._viewer_overlay.is_running:
            try:
                platforms = {k: v for k, v in self._viewer_counts.items() if v > 0}
                self._viewer_overlay.push_counts(total, platforms)
            except Exception:
                pass
        # ★ forward to composer — ส่งทุก platform ที่เชื่อมต่อ (แม้ count=0)
        #    เพื่อให้ overlay แสดง platform icons แม้ยังไม่ได้รับ viewer count
        all_platforms = {}
        for plat in self.chat_clients.keys():
            all_platforms[plat] = self._viewer_counts.get(plat, 0)
        # รวม platforms ที่มีใน _viewer_counts แต่ไม่มีใน chat_clients (เผื่อ)
        for plat, count in self._viewer_counts.items():
            if plat not in all_platforms:
                all_platforms[plat] = count
        self._composer_push_viewers(total, all_platforms)

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
    def _discover_rvc_models(self):
        """สแกน rvc_models/ หาไฟล์ .pth → return list ของ model id (DRY helper)

        ★ search dirs: ./rvc_models, ~/.tts-for-livestream/rvc_models, ../tts-for-livestream/rvc_models
        """
        import os
        search_dirs = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "rvc_models"),
            os.path.join(self._data_dir, "rvc_models"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tts-for-livestream", "rvc_models"),
        ]
        rvc_models = []
        seen = set()
        for models_dir in search_dirs:
            if not os.path.isdir(models_dir):
                continue
            try:
                for f in sorted(os.listdir(models_dir)):
                    if f.endswith('.pth') and f not in seen:
                        name = os.path.splitext(f)[0]
                        rvc_models.append(name)
                        seen.add(f)
            except Exception:
                pass
        return rvc_models

    def _is_full_build(self) -> bool:
        """ตรวจว่าเป็น Full build (มี torch + RVC) ไหม

        ★ เกณฑ์: import torch + rvc_engine ได้ = Full build
          ถ้า import ไม่ได้ = Lite build (ไม่มี RVC/OmniVoice)
        """
        try:
            import torch  # noqa: F401
            import rvc_engine  # noqa: F401
            return True
        except ImportError:
            return False

    def _populate_base_voices(self):
        """อัปเดต text labels ของ base voice ตาม engine toggle

        ★ Azure (edge): "หญิง" / "ชาย" (label เดียวกัน — เปลี่ยนเฉพาะ data ใต้ดิน)
        ★ Omni: "หญิง" / "ชาย"
        ★ ไม่ต้อง repopulate combo แล้ว (ใช้ text toggle 2 ตัว)
        """
        # ★ เก็บ data ใน combo ซ่อนไว้ (compat — settings dialog sync ยังใช้ combo)
        engine = getattr(self.settings, 'tts_engine', 'edge') if self.settings else 'edge'
        self.sidebar.base_voice_combo.blockSignals(True)
        self.sidebar.base_voice_combo.clear()
        if engine == "omnivoice":
            self.sidebar.base_voice_combo.addItem("หญิง", "female")
            self.sidebar.base_voice_combo.addItem("ชาย", "male")
        else:
            self.sidebar.base_voice_combo.addItem("หญิง (Premwadee)", "premwadee")
            self.sidebar.base_voice_combo.addItem("ชาย (Niwat)", "niwat")
        self.sidebar.base_voice_combo.blockSignals(False)

    def _populate_rvc_combo(self):
        """เติม rvc_combo — 'ไม่ใช้ RVC' + โมเดลที่พบ"""
        self.sidebar.rvc_combo.blockSignals(True)
        self.sidebar.rvc_combo.clear()
        self.sidebar.rvc_combo.addItem("ไม่ใช้ RVC", "")
        for name in self._discover_rvc_models():
            self.sidebar.rvc_combo.addItem(name, name)
        self.sidebar.rvc_combo.blockSignals(False)

    def _select_current_base_voice(self):
        """เลือก base voice จาก settings → highlight text toggle + sync combo ซ่อน"""
        if not self.settings:
            return
        engine = getattr(self.settings, 'tts_engine', 'edge')
        if engine == "omnivoice":
            target = getattr(self.settings, 'omnivoice_voice', 'female')
        else:
            target = getattr(self.settings, 'edge_voice', 'premwadee')
        # ★ normalize: child → female (เสียงเด็กเอาออกแล้ว)
        if target == "child":
            target = "female"
            self.settings.omnivoice_voice = "female"
        # ★ highlight text toggle
        self.sidebar.set_base_voice_active(target)
        # ★ sync combo ซ่อน (compat)
        for i in range(self.sidebar.base_voice_combo.count()):
            if self.sidebar.base_voice_combo.itemData(i) == target:
                self.sidebar.base_voice_combo.blockSignals(True)
                self.sidebar.base_voice_combo.setCurrentIndex(i)
                self.sidebar.base_voice_combo.blockSignals(False)
                return
        self.sidebar.base_voice_combo.setCurrentIndex(0)

    def _select_current_rvc(self):
        """เลือก RVC model จาก settings.voice_id (เรียกหลัง _populate_rvc_combo)"""
        voice_id = getattr(self.settings, 'voice_id', '') if self.settings else ''
        if not voice_id or voice_id in ('premwadee', 'niwat'):
            # ★ ไม่ใช้ RVC
            self.sidebar.rvc_combo.blockSignals(True)
            self.sidebar.rvc_combo.setCurrentIndex(0)
            self.sidebar.rvc_combo.blockSignals(False)
            return
        for i in range(self.sidebar.rvc_combo.count()):
            if self.sidebar.rvc_combo.itemData(i) == voice_id:
                self.sidebar.rvc_combo.blockSignals(True)
                self.sidebar.rvc_combo.setCurrentIndex(i)
                self.sidebar.rvc_combo.blockSignals(False)
                return
        # ★ voice_id ไม่ตรับกับ model ที่มี → index 0
        self.sidebar.rvc_combo.setCurrentIndex(0)

    def _refresh_voice_panel(self):
        """refresh ทั้ง voice panel — เรียกตอนเปิดโปรแกรม + หลัง download"""
        is_full = self._is_full_build()
        s = self.settings
        # ★ แสดง/ซ่อน container ตาม build
        self.sidebar.engine_toggle_container.setVisible(is_full)
        self.sidebar.rvc_container.setVisible(is_full)
        self.sidebar.voice_download_btn.setVisible(is_full)
        self.sidebar.voice_refresh_btn.setVisible(is_full)
        # ★ ซ่อน separator "|" ด้วยถ้าไม่มีปุ่มดาวโหลด (Lite)
        if hasattr(self.sidebar, 'voice_btn_sep'):
            self.sidebar.voice_btn_sep.setVisible(is_full)
        # ★ Lite build ที่มี OmniVoice → โชว์ toggle (พิเศษ: dev mode ที่ลง omnivoice แยก)
        if not is_full:
            try:
                from omnivoice_engine import is_omnivoice_available
                if is_omnivoice_available():
                    self.sidebar.engine_toggle_container.setVisible(True)
                    # ★ ซ่อนกล่อง RVC แต่โชว์ toggle ได้ (ไม่มีโมเดล RVC)
            except Exception:
                pass
        # ★ restore toggle state
        engine = getattr(s, 'tts_engine', 'edge') if s else 'edge'
        self.sidebar.set_engine_active(engine)
        # ★ repopulate combos
        self._populate_base_voices()
        self._populate_rvc_combo()
        # ★ select current
        self._select_current_base_voice()
        self._select_current_rvc()
        # ★ sync status label
        self._sync_voice_status_label()
        # ★ auto-load RVC ถ้ามี (กัน double-load)
        voice_id = getattr(s, 'voice_id', '') if s else ''
        if voice_id and voice_id not in ('premwadee', 'niwat') and not getattr(self, '_rvc_loading', False):
            # ★ เช็คว่า model มีจริงไหม
            if self._find_rvc_path(voice_id):
                self._rvc_loading = True
                self.sidebar.rvc_status.setText(f"⏳ กำลังโหลด {voice_id}...")
                self.sidebar.rvc_status.setStyleSheet("color: #f59e0b; font-size: 13px;")
                self.sidebar.rvc_combo.setEnabled(False)
                # ★ หน่วงเวลา RVC load ถ้า tts_engine=omnivoice (รอ OmniVoice โหลดเสร็จก่อน กัน GPU race)
                delay = 5000 if getattr(s, 'tts_engine', 'edge') == 'omnivoice' else 1000
                QTimer.singleShot(delay, lambda: self._auto_load_rvc(voice_id))

    def _find_rvc_path(self, voice_id: str):
        """หา path ของ RVC model (.pth) — return path หรือ None (DRY helper)"""
        import os
        search_dirs = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "rvc_models"),
            os.path.join(self._data_dir, "rvc_models"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tts-for-livestream", "rvc_models"),
        ]
        for d in search_dirs:
            p = os.path.join(d, f"{voice_id}.pth")
            if os.path.exists(p):
                return p
        return None

    def _auto_load_rvc(self, voice_id):
        """auto-load RVC model ตอนเปิดโปรแกรม — เรียก _load_rvc_model helper"""
        pth_path = self._find_rvc_path(voice_id)
        if not pth_path:
            # ★ ไม่พบ model → revert combo และ sync status
            self.settings.voice_id = ''
            self.sidebar.rvc_combo.blockSignals(True)
            self.sidebar.rvc_combo.setCurrentIndex(0)
            self.sidebar.rvc_combo.setEnabled(True)
            self.sidebar.rvc_combo.blockSignals(False)
            self._save_settings()
            self._sync_voice_status_label()
            self.status_bar.set_status("🎤 RVC model ไม่พบ → ใช้เสียงพื้นฐาน")
            return
        # ★ delegate ให้ _load_rvc_model (DRY)
        self._load_rvc_model(voice_id)

    def _set_rvc_status_premwadee(self):
        """คืนสถานะเป็น Premwadee (compat — เรียก _sync_voice_status_label แทน)"""
        self._sync_voice_status_label()

    def _on_engine_toggle(self, engine: str):
        """toggle Azure/Omni — เปลี่ยน tts_engine + repopulate base voice

        ★ engine: "edge" (Azure) หรือ "omnivoice" (Omni)
        """
        if not self.settings:
            return
        # ★ ถ้า Omni ไม่ available → บล็อก (revert UI)
        #   ★★ retry 3 ครั้งเพราะ RVC loading อาจทำให้ torch import ค้างชั่วคราว
        if engine == "omnivoice":
            import time as _time
            omni_ok = False
            for attempt in range(3):
                try:
                    from omnivoice_engine import is_omnivoice_available
                    if is_omnivoice_available():
                        omni_ok = True
                        break
                except Exception:
                    pass
                _time.sleep(0.5)
            if not omni_ok:
                # ★ debug: log สาเหตุจริง
                try:
                    import torch
                    torch_ok = True
                except Exception as e:
                    torch_ok = f"FAIL: {e}"
                try:
                    import omnivoice
                    omni_imp = True
                except Exception as e:
                    omni_imp = f"FAIL: {type(e).__name__}: {e}"
                logger.error(f"OmniVoice not available (3 retries) — torch={torch_ok}, omnivoice={omni_imp}")
                self.sidebar.set_engine_active("edge")
                self.status_bar.set_status("⚠ OmniVoice ไม่พร้อมใช้งาน (อาจกำลังโหลด RVC อยู่ ลองใหม่อีกครั้ง)")
                return
        self.settings.tts_engine = engine
        # ★ update UI toggle highlight
        self.sidebar.set_engine_active(engine)
        # ★ repopulate base voice combo (เพราะเปลี่ยนตัวเลือก)
        self._populate_base_voices()
        self._select_current_base_voice()
        # ★ sync pipeline config
        if self.pipeline:
            self.pipeline.config.tts_engine = engine
        # ★ lazy-load OmniVoice ถ้าเลือก Omni
        if engine == "omnivoice":
            self._ensure_omnivoice_loaded()
        # ★ update status
        self._sync_voice_status_label()
        # ★ sync settings dialog ด้วย (ถ้าเปิดอยู่)
        self._sync_settings_dialog_voice()
        self._save_settings()

    def _on_base_voice_click(self, voice_key: str):
        """user คลิก text toggle หญิง/ชาย — voice_key = "female" | "male"

        ★ แปลงเป็นค่าที่ engine ใช้:
          Omni: female/male (ตรงๆ)
          Azure: female→premwadee, male→niwat
        """
        if not self.settings:
            return
        engine = getattr(self.settings, 'tts_engine', 'edge')
        if engine == "omnivoice":
            self.settings.omnivoice_voice = voice_key  # "female" / "male"
            if self.pipeline:
                self.pipeline.config.omnivoice_voice = voice_key
            # ★ sync combo ซ่อน
            target = voice_key
        else:
            edge_val = "premwadee" if voice_key == "female" else "niwat"
            self.settings.edge_voice = edge_val
            if self.pipeline:
                self.pipeline.config.edge_voice = edge_val
            target = edge_val
        # ★ highlight text toggle
        self.sidebar.set_base_voice_active(target)
        # ★ sync combo ซ่อน (compat)
        for i in range(self.sidebar.base_voice_combo.count()):
            if self.sidebar.base_voice_combo.itemData(i) == target:
                self.sidebar.base_voice_combo.blockSignals(True)
                self.sidebar.base_voice_combo.setCurrentIndex(i)
                self.sidebar.base_voice_combo.blockSignals(False)
                break
        self._sync_voice_status_label()
        # ★ sync settings dialog
        self._sync_settings_dialog_voice()
        self._save_settings()

    def _on_rvc_change(self, index):
        """เลือก/ยกเลิกโมเดล RVC — เกิดเมื่อ user เลือกจาก dropdown"""
        if index < 0 or not self.settings:
            return
        # ★ กัน double-load (RVC loading)
        if getattr(self, '_rvc_loading', False):
            return
        voice_id = self.sidebar.rvc_combo.itemData(index) or ''
        if not voice_id:
            # ★ "ไม่ใช้ RVC"
            self.settings.voice_id = ''
            if self.pipeline:
                self.pipeline.config.voice = ''
                self.pipeline.set_rvc(None, '', '')
            self._sync_voice_status_label()
            self._save_settings()
            return
        # ★ โหลด RVC model
        self._load_rvc_model(voice_id)

    def _load_rvc_model(self, voice_id: str):
        """โหลด RVC model ใน background (DRY helper)

        ถูกเรียกจาก: _on_rvc_change (user เลือก) + _auto_load_rvc (เปิดโปรแกรม)
        """
        pth_path = self._find_rvc_path(voice_id)
        if not pth_path:
            self.status_bar.set_status(f"❌ ไม่พบ {voice_id}.pth")
            # ★ revert combo
            self.sidebar.rvc_combo.blockSignals(True)
            self.sidebar.rvc_combo.setCurrentIndex(0)
            self.sidebar.rvc_combo.blockSignals(False)
            return
        index_path = pth_path.replace('.pth', '.index')
        import os
        if not os.path.exists(index_path):
            index_path = ''
        # ★ update state
        self.settings.voice_id = voice_id
        if self.pipeline:
            self.pipeline.config.voice = voice_id
        self._rvc_loading = True
        self.status_bar.set_status(f"⏳ กำลังโหลด RVC: {voice_id}... (5-15 วินาที)")
        self.sidebar.rvc_status.setText(f"⏳ กำลังโหลด {voice_id}...")
        self.sidebar.rvc_status.setStyleSheet("color: #f59e0b; font-size: 13px;")
        self.sidebar.rvc_combo.setEnabled(False)

        _pth = pth_path
        _vid = voice_id
        _idx = index_path
        def _bg_load_rvc():
            try:
                from rvc_engine import RVCEngine
                engine = RVCEngine(model_path=_pth)
                engine.load()
                self._rvc_loaded_sig.emit(engine, _vid, _idx)
            except Exception as e:
                logger.error(f"Failed to load RVC voice: {e}")
                self._rvc_failed_sig.emit(str(e))

        threading.Thread(target=_bg_load_rvc, name="RvcLoad", daemon=True).start()

    def _sync_voice_status_label(self):
        """sync rvc_status label ตามสถานะปัจจุบัน (engine + base voice + RVC)"""
        if not self.settings:
            return
        voice_id = getattr(self.settings, 'voice_id', '')
        engine = getattr(self.settings, 'tts_engine', 'edge')
        # ★ RVC active → แสดงชื่อโมเดล + base engine (เลือกโมเดลจาก dropdown = RVC อยู่แล้ว ไม่ต้องบอก)
        if voice_id and voice_id not in ('premwadee', 'niwat'):
            base_label = "Omni" if engine == "omnivoice" else "Azure"
            voice_label = f"{voice_id} ({base_label})"
            status_text = f"🎤 เสียง: {voice_label}"
            self.sidebar.rvc_status.setText(f"✅ {voice_label}")
        else:
            # ★ base voice เท่านั้น
            if engine == "omnivoice":
                ov = getattr(self.settings, 'omnivoice_voice', 'female')
                label = "หญิง" if ov == "female" else "ชาย"
                status_text = f"🎤 เสียง: OmniVoice ({label})"
                self.sidebar.rvc_status.setText(f"✅ OmniVoice ({label})")
            else:
                ev = getattr(self.settings, 'edge_voice', 'premwadee')
                label = "Premwadee (หญิง)" if ev == "premwadee" else "Niwat (ชาย)"
                status_text = f"🎤 เสียง: {label} (Azure)"
                self.sidebar.rvc_status.setText(f"✅ {label} (Azure)")
        self.sidebar.rvc_status.setStyleSheet("color: #10b981; font-size: 13px;")
        self.status_bar.set_status(status_text)

    def _sync_settings_dialog_voice(self):
        """sync เสียงที่เลือกจาก sidebar → settings dialog (ถ้าเปิดอยู่)"""
        dlg = getattr(self, '_settings_dialog', None)
        if dlg is None or not dlg.isVisible():
            return
        s = self.settings
        if s is None:
            return
        try:
            # ★ engine radio
            if s.tts_engine == "omnivoice":
                dlg.tts_engine_omni.setChecked(True)
            else:
                dlg.tts_engine_edge.setChecked(True)
            # ★ edge voice combo
            ev = getattr(s, 'edge_voice', 'premwadee')
            for i in range(dlg.edge_voice_combo.count()):
                if dlg.edge_voice_combo.itemData(i) == ev:
                    dlg.edge_voice_combo.setCurrentIndex(i)
                    break
            # ★ omnivoice voice combo
            ov = getattr(s, 'omnivoice_voice', 'female')
            for i in range(dlg.omnivoice_voice_combo.count()):
                if dlg.omnivoice_voice_combo.itemData(i) == ov:
                    dlg.omnivoice_voice_combo.setCurrentIndex(i)
                    break
        except Exception as e:
            logger.debug(f"sync settings dialog voice: {e}")

    def _save_settings(self):
        """save settings (DRY helper)"""
        try:
            from settings import save_settings
            save_settings(self.settings)
        except Exception:
            pass

    def _ensure_omnivoice_loaded(self):
        """lazy-load OmniVoice engine — delegate ให้ _auto_load_omnivoice (มี progress bar)

        ★ กันโหลดซ้ำ: ถ้ากำลังโหลดอยู่แล้ว → return
        """
        if self._omnivoice_engine is not None:
            return  # โหลดแล้ว
        # ★ กัน double-load (ถ้า _auto_load_omnivoice ทำงานอยู่แล้ว)
        if getattr(self, '_omnivoice_loading', False):
            return
        self._omnivoice_loading = True
        # ★ delegate ให้ _auto_load_omnivoice (มี progress bar ทุก stage)
        self._auto_load_omnivoice()

    def _on_omnivoice_loaded(self):
        """OmniVoice โหลดเสร็จ (main thread)"""
        ov = getattr(self.settings, 'omnivoice_voice', 'female')
        self.status_bar.set_status(f"✅ OmniVoice พร้อม ({ov})")
        self.sidebar.rvc_status.setText(f"✅ OmniVoice ({ov})")
        self.sidebar.rvc_status.setStyleSheet("color: #10b981; font-size: 13px;")

    def _on_omnivoice_failed(self, error):
        """OmniVoice โหลดล้มเหลว (main thread) → fallback edge-tts"""
        self.status_bar.set_status(f"❌ OmniVoice ล้มเหลว: {error} → ใช้ edge-tts")
        self.sidebar.rvc_status.setText("✅ Premwadee (edge-tts)")
        self.sidebar.rvc_status.setStyleSheet("color: #10b981; font-size: 13px;")
        # ★ fallback เป็น edge-tts
        self.settings.tts_engine = "edge"
        if self.pipeline:
            self.pipeline.config.tts_engine = "edge"

    # ═══ Auto-load OmniVoice with progress bar ═══
    def _auto_check_update(self):
        """Auto-check อัพเดทเงียบๆ หลังเปิดโปรแกรม 10 วินาที (เหมือน v1)

        ★ ถ้ามีอัพเดท → แสดง status bar "มีอัพเดทใหม่" (ไม่บังคับ dialog)
        """
        try:
            from updater import check_update_async
            def _on_result(info):
                if info:
                    ver = info.get("latest", "?")
                    self.status_bar.set_status(f"🆕 มีอัพเดทใหม่ v{ver} — ไปที่ ตั้งค่า > เช็คอัพเดท")
            check_update_async(_on_result)
        except Exception as e:
            logger.debug(f"auto_check_update: {e}")

    def _auto_load_omnivoice(self):
        """auto-load OmniVoice ตอนเปิดโปรแกรม (เบื้องหลัง + progress bar)

        ★ pipeline เริ่มต้นใช้ edge-tts (fallback) จนกว่า OmniVoice จะพร้อม
          → user ใช้งาน TTS ได้ทันที (เสียง edge-tts) สักครู่ OmniVoice จะพร้อม
        """
        if self._omnivoice_engine is not None:
            return  # โหลดแล้ว
        try:
            from omnivoice_engine import is_omnivoice_available
            if not is_omnivoice_available():
                logger.info("OmniVoice not available — using edge-tts")
                return
        except ImportError:
            return
        # ★ show progress bar
        self.status_bar.show_progress()
        self.status_bar.set_progress(0, "กำลังเตรียม OmniVoice...")
        # ★ import ใน main thread ก่อน (กัน PyInstaller thread import issue)
        try:
            from omnivoice_engine import OmniVoiceEngine
        except ImportError as e:
            self._omnivoice_progress_sig.emit(-1, f"❌ OmniVoice import fail: {e}")
            return
        # ★ load in background thread
        def _bg():
            try:
                # ★ manual __init__ fields (เพื่อใช้ load_with_progress)
                import threading, collections
                engine = OmniVoiceEngine.__new__(OmniVoiceEngine)
                engine._instruct = getattr(self.settings, 'omnivoice_voice', 'female')
                engine._device = 'cuda:0'
                engine._model = None
                engine._loaded = False
                engine._lock = threading.Lock()
                # ★ TTS quality params (ต้องตรงกับ OmniVoiceEngine.__init__)
                engine._language = "Thai"
                engine._speed = 1.0
                engine._normalize_text = True
                # ★ init audio cache (เพราะ __new__ ข้าม __init__)
                engine._audio_cache = collections.OrderedDict()
                engine._audio_cache_max = 200
                engine._audio_cache_ttl = 300.0
                engine._max_cache_text_len = 80
                import torch
                engine._torch = torch
                if not torch.cuda.is_available():
                    engine._device = 'cpu'
                engine._dtype = torch.float16
                # ★ load with progress callback → emit signal (main thread)
                def _on_progress(pct, text):
                    self._omnivoice_progress_sig.emit(pct, text)
                engine.load_with_progress(on_progress=_on_progress)
                self._omnivoice_engine = engine
                if self.pipeline:
                    self.pipeline.omnivoice = engine
                self._omnivoice_ready_sig.emit()
            except Exception as e:
                logger.error(f"Auto OmniVoice load failed: {e}")
                self._omnivoice_progress_sig.emit(-1, f"❌ OmniVoice ล้มเหลว: {e}")
        import threading
        threading.Thread(target=_bg, name="OmniVoiceAutoLoad", daemon=True).start()

    def _on_omnivoice_progress(self, percent: int, text: str):
        """slot: OmniVoice load progress update (main thread) → update progress bar"""
        if percent < 0:
            # ★ error
            self._omnivoice_loading = False  # ★ รีเซ็ต flag
            self.status_bar.hide_progress()
            self.status_bar.set_status(text)
            self.sidebar.rvc_status.setText("✅ edge-tts (fallback)")
            self.sidebar.rvc_status.setStyleSheet("color: #10b981; font-size: 13px;")
            self.settings.tts_engine = "edge"
            if self.pipeline:
                self.pipeline.config.tts_engine = "edge"
            return
        self.status_bar.set_progress(percent, f"🎤 OmniVoice: {text}")

    def _on_omnivoice_ready(self):
        """slot: OmniVoice โหลดเสร็จ (main thread) → hide progress + update status"""
        self._omnivoice_loading = False  # ★ รีเซ็ต flag
        self.status_bar.hide_progress()
        ov = getattr(self.settings, 'omnivoice_voice', 'female')
        # ★ sync pipeline config (เปลี่ยน base engine เป็น omnivoice ตอนนี้)
        if self.pipeline:
            self.pipeline.config.tts_engine = "omnivoice"
            self.pipeline.config.omnivoice_voice = ov
        self.status_bar.set_status(f"✅ OmniVoice พร้อม ({ov})")
        # ★ update sidebar status (ถ้ามี RVC อยู่ → แสดงชื่อโมเดล + Omni)
        voice_id = getattr(self.settings, 'voice_id', '')
        if voice_id and voice_id not in ('premwadee', 'niwat', ''):
            self.sidebar.rvc_status.setText(f"✅ {voice_id} (Omni)")
        else:
            self.sidebar.rvc_status.setText(f"✅ OmniVoice ({ov})")
        self.sidebar.rvc_status.setStyleSheet("color: #10b981; font-size: 13px;")
        logger.info("OmniVoice auto-loaded and ready")

    def _on_rvc_loaded(self, engine, voice_id, index_path):
        """RVC โหลดเสร็จ (main thread)"""
        self._rvc_loading = False
        self.sidebar.rvc_combo.setEnabled(True)
        if self.pipeline:
            pitch = getattr(self.settings, 'rvc_pitch', 0)
            from rvc_engine import RVCParams
            params = RVCParams(f0up_key=pitch, f0method='rmvpe', index_path=index_path)
            self.pipeline.set_rvc(engine, voice_id, index_path)
        # ★ sync status label (DRY)
        self._sync_voice_status_label()
        # ★ ถ้า base engine = OmniVoice → ensure โหลดแล้ว (เผื่อเลือก RVC ทีหลัง)
        base_engine = getattr(self.settings, 'tts_engine', 'edge')
        if base_engine == "omnivoice":
            self._ensure_omnivoice_loaded()

    def _on_rvc_load_failed(self, error):
        """RVC โหลดล้มเหลว (main thread)"""
        self._rvc_loading = False
        self.sidebar.rvc_combo.setEnabled(True)
        self.status_bar.set_status(f"❌ โหลด RVC ไม่ได้: {error}")
        self.sidebar.rvc_status.setText(f"❌ โหลดไม่ได้")
        self.sidebar.rvc_status.setStyleSheet("color: #ef4444; font-size: 13px;")
        # ★ fallback — revert combo และ sync status
        self.settings.voice_id = ''
        self.sidebar.rvc_combo.blockSignals(True)
        self.sidebar.rvc_combo.setCurrentIndex(0)
        self.sidebar.rvc_combo.blockSignals(False)
        if self.pipeline:
            self.pipeline.set_rvc(None, '', '')
        QTimer.singleShot(3000, lambda: self._sync_voice_status_label())

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

    def _on_pitch_change(self, value):
        """ปรับ pitch (RVC)"""
        if self.settings:
            self.settings.rvc_pitch = value
        if self.pipeline:
            self.pipeline.config.rvc_pitch = value

    def _test_voice(self):
        """ทดสอบเสียง TTS — cooldown 3 วินาที + เปลี่ยนข้อความปุ่มเป็น 'รอซักครู่'"""
        if not self.pipeline:
            return
        btn = self.sidebar.voice_test_btn
        # ★ cooldown — ถ้ากดในช่วง 3 วินาทีที่ผ่านมา ให้ ignore
        now = time.time()
        last = getattr(self, '_test_voice_last', 0.0)
        if now - last < 3.0:
            return
        self._test_voice_last = now
        # ★ เปลี่ยนข้อความเป็น "รอซักครู่" + disable
        btn.setText("รอซักครู่")
        btn.setEnabled(False)
        # ★ คืนข้อความ + enable หลัง 3 วินาที
        def _restore():
            btn.setText("ทดสอบฟัง")
            btn.setEnabled(True)
        QTimer.singleShot(3000, _restore)
        import random
        phrases = [
            "สวัสดี นี่คือการทดสอบเสียงอ่านโมเดล",
            "ทดสอบออกเสียง เม้งแชนแนลดอทคอม",
            "ทดสอบออกเสียง เช้าฟาดผัดฟัก เย็นฟาดฟักผัด",
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
        self._refresh_voice_panel()

    def _safe_status(self, msg):
        """thread-safe status update (เรียกจาก game_overlay.py + pipeline)"""
        QTimer.singleShot(0, lambda: self.status_bar.set_status(msg))

    def after(self, ms, callback):
        """Tk compatibility shim — game_overlay.py อ้าง parent_app.after"""
        # ★ ถ้า callback คือ method reference → ใช้ signal แทน (thread-safe)
        QTimer.singleShot(ms, callback)

    def _on_game_overlay_cmd(self, cmd):
        """จัดการ command จาก Qt overlay (signal — main thread)"""
        go = getattr(self, '_game_overlay', None)
        if not go or not go.is_running:
            return
        if cmd == 'toggle_demo':
            try:
                go.toggle_demo()
            except Exception as e:
                logger.error(f"toggle_demo failed: {e}")
        elif cmd == 'open_settings':
            self._open_game_overlay_settings()
        elif cmd == 'exit_edit':
            go._edit_mode = False
            go._send_cmd("edit_off")
            self._safe_status("✅ Game Overlay: ปิด Edit Mode")

    def _open_game_overlay_settings(self):
        """เปิด Game Overlay settings dialog"""
        from ui.dialogs.game_overlay_settings import GameOverlaySettingsDialog
        dlg = GameOverlaySettingsDialog(self)
        self._go_settings_dlg = dlg  # ★ keep ref for _sync_demo_state_to_dialog
        dlg.exec()
        self._go_settings_dlg = None

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
        self._settings_dialog = dlg  # ★ เก็บ ref เพื่อ sync voice กลับ
        dlg.settings_changed.connect(self._on_settings_changed)
        dlg.exec()
        self._settings_dialog = None

    def _open_platform_settings(self):
        """เปิด Settings ไปที่แท็บแพลตฟอร์ม"""
        from ui.dialogs.settings import SettingsDialog
        dlg = SettingsDialog(self)
        self._settings_dialog = dlg
        dlg.settings_changed.connect(self._on_settings_changed)
        # ★ สลับไป section แพลตฟอร์ม (index 0)
        dlg.sidebar.setCurrentRow(0)
        dlg.exec()
        self._settings_dialog = None

    def _on_settings_changed(self):
        """เรียกเมื่อ settings เปลี่ยน"""
        if self.pipeline and self.settings:
            self.pipeline.set_filter(self.settings.to_text_filter())
            # ★ rebuild pipeline config (translation + mixed voice)
            new_config = self._build_pipeline_config()
            self.pipeline.config = new_config
        # ★ re-register hotkeys (เผื่อ user เปลี่ยน hotkey ใน settings)
        self._reregister_hotkeys()
        # ★ re-call OBS WebSocket watcher (เผื่อ user เปิด/ปิด หรือเปลี่ยน host/port/password)
        self._obs_ws_auto_refresh()
        # ★ sync translate mode ไป TopBar (เผื่อ user เปลี่ยนโหมดใน settings → ปุ่มต้องซ่อน/แสดง)
        if self.settings:
            if getattr(self.settings, 'multilang_enabled', False):
                self.topbar.set_translate_mode("multilang")
            elif getattr(self.settings, 'auto_translate_enabled', False):
                self.topbar.set_translate_mode("translate")
            else:
                self.topbar.set_translate_mode("off")
        # ★ sync voice panel (settings dialog อาจเปลี่ยน engine/voice → sidebar ต้องตาม)
        if self.settings:
            self._refresh_voice_panel()
        self.status_bar.set_status("✅ บันทึกการตั้งค่าแล้ว")

    def _open_user_manager(self):
        from ui.dialogs.user_manager import UserManagerDialog
        dlg = UserManagerDialog(self)
        dlg.exec()

    def _open_ngreplace(self):
        from ui.dialogs.ngreplace import NGReplaceDialog
        dlg = NGReplaceDialog(self)
        dlg.exec()

    def _open_omni_skip(self):
        """เปิด OmniVoice Word Skip editor"""
        from ui.dialogs.omni_skip import OmniSkipDialog
        dlg = OmniSkipDialog(self)
        dlg.settings_changed.connect(self._on_settings_changed)
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
        # ★ ซ่อนเฉพาะส่วนแชท (scroll area) ไม่ซ่อน header — ใช้ overlay เฉพาะส่วน scroll
        if not hasattr(self, '_popout_overlay'):
            self._popout_overlay = QLabel("💬 แชทถูกแยกออกไปแล้ว (Popout)\n\nกดปุ่ม ↗ อีกครั้งเพื่อกลับมา")
            self._popout_overlay.setAlignment(Qt.AlignCenter)
            self._popout_overlay.setStyleSheet("color: #9ca3af; font-size: 16px; background-color: #0a0e1a; border: none;")
        # ★ วาง overlay ทับเฉพาะ scroll area (ไม่ทับ header ของ chat panel)
        scroll = self.chat_panel.scroll
        self._popout_overlay.setParent(self.chat_panel)
        # ★ geometry = ใต้ header ลงมาถึงขอบล่าง
        header_h = 40  # ประมาณความสูง header
        self._popout_overlay.setGeometry(0, header_h, self.chat_panel.width(), self.chat_panel.height() - header_h)
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
        """resize overlay ตาม chat panel + re-position floating events button"""
        super().resizeEvent(event)
        if hasattr(self, '_popout_overlay') and self._popout_overlay and self._popout_overlay.isVisible():
            self._popout_overlay.setGeometry(self.chat_panel.rect())
        # ★ re-position floating "‹" button (ตอน events panel ซ่อน)
        if hasattr(self, '_events_show_btn'):
            self._position_events_show_btn()

    def _toggle_translate(self):
        """เปิด/ปิดการแปลอัตโนมัติ (#6)"""
        if not self.settings:
            return
        self.settings.auto_translate_enabled = not getattr(self.settings, 'auto_translate_enabled', False)
        if self.pipeline:
            self.pipeline.config.auto_translate_enabled = self.settings.auto_translate_enabled
        state = "เปิด" if self.settings.auto_translate_enabled else "ปิด"
        self.status_bar.set_status(f"🌐 การแปลอัตโนมัติ: {state}")

    def _open_author_modal(self, author):
        """เปิด Author Modal — สถิติ + donate + history + actions"""
        from ui.dialogs.author_modal import AuthorModal
        dlg = AuthorModal(self, author)
        dlg.exec()

    def _unblock_user(self, author):
        """ปลดบล็อกผู้ใช้ (รองรับทั้ง str + dict format)"""
        if not self.settings:
            return
        author_lower = author.strip().lower()
        blocked = list(getattr(self.settings, 'blocked_users', []) or [])
        new_blocked = []
        removed = False
        for u in blocked:
            if isinstance(u, dict):
                if u.get('name', '').strip().lower() == author_lower:
                    removed = True
                    continue
            elif isinstance(u, str):
                if u.strip().lower() == author_lower:
                    removed = True
                    continue
            new_blocked.append(u)
        if removed:
            self.settings.blocked_users = new_blocked
            try:
                from settings import save_settings
                save_settings(self.settings)
            except Exception:
                pass
            # ★ sync pipeline filter ทันที
            if self.pipeline:
                try:
                    self.pipeline.set_filter(self.settings.to_text_filter())
                except Exception:
                    pass
            self._post_system_message(f"✅ ปลดบล็อก {author}")

    def _get_block_status(self, author):
        """เช็คสถานะบล็อกของ user → คืน None | "block_all" | "block_tts" """
        if not self.settings:
            return None
        author_lower = author.strip().lower()
        for u in getattr(self.settings, 'blocked_users', []) or []:
            if isinstance(u, dict) and u.get('name', '').strip().lower() == author_lower:
                return "block_all" if u.get('hide_overlay', True) else "block_tts"
            elif isinstance(u, str) and u.strip().lower() == author_lower:
                return "block_all"
        return None

    def _update_block_button(self, btn, status, author):
        """อัปเดตปุ่มบล็อกตามสถานะปัจจุบัน"""
        if status == "block_all":
            btn.setText(f"🚫 บล็อกอยู่ (ทุกอย่าง) — คลิกเพื่อเปลี่ยน/ปลด")
            btn.setStyleSheet("QPushButton { background-color: #ef4444; color: white; font-weight: 600; border: none; border-radius: 6px; padding: 6px 16px; } QPushButton:hover { background-color: #dc2626; }")
        elif status == "block_tts":
            btn.setText(f"🔇 บล็อกอยู่ (TTS เท่านั้น) — คลิกเพื่อเปลี่ยน/ปลด")
            btn.setStyleSheet("QPushButton { background-color: #f59e0b; color: white; font-weight: 600; border: none; border-radius: 6px; padding: 6px 16px; } QPushButton:hover { background-color: #d97706; }")
        else:
            btn.setText("🚫 บล็อก")
            btn.setStyleSheet("QPushButton { background-color: #1a1f33; color: #e5e7eb; font-weight: 600; border: 1px solid #2a2f45; border-radius: 6px; padding: 6px 16px; } QPushButton:hover { background-color: #252b42; border-color: #ef4444; }")

    def _get_user_stats(self, author):
        """ดึงสถิติผู้ใช้ — จำนวนแชท + แพลตฟอร์ม + events (sub/bits/superchat/raid)

        Returns: {'msg_count': int, 'platforms': list[str], 'events': {event_type: count}}
        """
        stats = {'msg_count': 0, 'platforms': [], 'events': {}}
        author_lower = author.strip().lower()
        # ★ message count + platforms (จาก message_history)
        if self.message_history:
            try:
                stats['msg_count'] = self.message_history.count(author)
                plats = self.message_history.platforms(author)
                if plats:
                    stats['platforms'] = sorted(plats)
            except Exception:
                pass
        # ★ events (จาก event_log — sub/bits/superchat/raid/follow/etc)
        if self.event_log:
            try:
                all_entries = self.event_log.get_all()
                for entry in all_entries:
                    if entry.author and entry.author.strip().lower() == author_lower:
                        ev = entry.event or ''
                        if ev and ev != 'message':
                            stats['events'][ev] = stats['events'].get(ev, 0) + 1
            except Exception:
                pass
        return stats

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

    def _open_live_chat_settings(self):
        """เปิด Live Chat Settings dialog (เฟือง ⚙ ใน chat panel)"""
        from ui.dialogs.live_chat_settings import LiveChatSettingsDialog
        dlg = LiveChatSettingsDialog(self)
        dlg.settings_changed.connect(self._rerender_chat)
        dlg.exec()

    def _rerender_chat(self):
        """re-render ทุก chat row (ใช้เมื่อ settings เปลี่ยน: icon/color/timestamp/emote/font)"""
        # ★ push settings ล่าสุดเข้า ChatRow global ก่อน re-render
        self._apply_chat_appearance()
        size = getattr(self.chat_panel, '_current_font_size', 16)
        # main chat
        msgs = [row.msg for row in self.chat_panel._rows if hasattr(row, 'msg')]
        self.chat_panel.clear_messages()
        for msg in msgs:
            self.chat_panel.add_message(msg, size)
        # popout
        if hasattr(self, '_popout_window') and self._popout_window:
            popout = self._popout_window
            popout_msgs = [row.msg for row in popout._rows if hasattr(row, 'msg')]
            popout.clear_messages()
            for msg in popout_msgs:
                popout.add_message(msg, size)

    def _apply_chat_appearance(self):
        """push chat appearance settings เข้า ChatRow global (เรียกตอน init + re-render)"""
        try:
            from ui.widgets.chat_row import set_chat_settings
            s = self.settings
            set_chat_settings(
                show_platform_icon=getattr(s, 'chat_show_platform_icon', True),
                author_color_mode=getattr(s, 'chat_author_color_mode', 'platform'),
                show_timestamp=getattr(s, 'chat_show_timestamp', False),
                emote_size=getattr(s, 'chat_emote_size', 28),
                font_family=getattr(s, 'chat_font_family', 'Kanit'),
                zebra_stripes=getattr(s, 'chat_zebra_stripes', False),
            )
        except Exception as e:
            logger.debug(f"_apply_chat_appearance failed: {e}")

    def _apply_chat_font(self):
        """apply font scale ไปยัง chat rows — re-render ทั้งหมด"""
        scale = getattr(self, '_chat_font_scale', 0)
        base = 16  # ★ base 16px (เพิ่มจาก 14 ให้อ่านง่ายขึ้น) + scale จาก A-/A+
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
        """เปิด/ปิด Game Overlay"""
        if hasattr(self, '_game_overlay') and self._game_overlay and self._game_overlay.is_running:
            try:
                self._game_overlay.stop()
            except Exception:
                pass
            self._game_overlay = None
            self.topbar.set_game_overlay_active(False)
            self.status_bar.set_status("🎮 Game Overlay ปิดแล้ว")
            return

        self.status_bar.set_status("⏳ Game Overlay กำลังเปิด...")
        import threading
        def _bg_start():
            try:
                from game_overlay import GameOverlay
                ov = GameOverlay(self)
                ok = ov.start()
                self._overlay_started_sig.emit(ok, id(ov) if ok else 0)
                if ok:
                    self._game_overlay = ov
            except Exception as e:
                logger.error(f"Failed to start overlay: {e}")
                self._overlay_started_sig.emit(False, 0)

        threading.Thread(target=_bg_start, name="GameOverlayToggle", daemon=True).start()

    def _on_overlay_started_sig(self, ok, ov_id):
        """หลัง overlay start เสร็จ (signal — main thread)"""
        if ok:
            self.topbar.set_game_overlay_active(True)
            self.status_bar.set_status("🎮 Game Overlay เปิดแล้ว")
        else:
            self._game_overlay = None
            self.topbar.set_game_overlay_active(False)
            self.status_bar.set_status("❌ Game Overlay เปิดไม่ได้")

    def _on_overlay_started(self, ok, overlay):
        """หลัง Game Overlay เริ่มเสร็จ"""
        if ok and overlay:
            self._game_overlay = overlay
            self.status_bar.set_status("🔲 Overlay เปิดแล้ว")
        else:
            self._game_overlay = None
            self.status_bar.set_status("❌ Overlay เปิดไม่ได้")

    def _on_tts_toggled(self, on):
        """toggle TTS อ่านแชท — on=True เปิด, on=False ปิด (mute)"""
        if self.pipeline:
            self.pipeline.config.tts_muted = not on
        if self.settings:
            self.settings.tts_muted = not on
        state = "อ่านแชท TTS" if on else "ปิดการอ่านแชท"
        self.status_bar.set_status(f"🔊 {state}")

    def _restore_topbar_state(self):
        """restore topbar state จาก settings (เรียกตอน init)"""
        if not self.settings:
            return
        # TTS state
        muted = getattr(self.settings, 'tts_muted', False)
        self.topbar.set_tts_state(not muted)
        vol = getattr(self.settings, 'tts_volume', 100)
        self.topbar.set_volume(vol)
        # translate mode — ★ ถ้าทั้งสองปิด → "off" (ซ่อนปุ่ม translate ใน topbar)
        if getattr(self.settings, 'multilang_enabled', False):
            self.topbar.set_translate_mode("multilang")
        elif getattr(self.settings, 'auto_translate_enabled', False):
            self.topbar.set_translate_mode("translate")
        else:
            self.topbar.set_translate_mode("off")

    def _on_tts_volume(self, vol):
        """ปรับ volume จาก topbar slider"""
        if self.pipeline:
            try:
                self.pipeline.config.tts_volume = vol / 100.0
            except Exception:
                pass
        if self.settings:
            self.settings.tts_volume = vol

    # ════════════════════════════════════════════════════════════
    # Composer (Canvas Overlay) toggle
    # ════════════════════════════════════════════════════════════
    def _toggle_composer(self):
        """เปิด Composer editor ใน browser (ไม่ toggle server — server เปิดอยู่เสมอ)"""
        try:
            port = getattr(self.composer_server, '_port', 8808) if self.composer_server else 8808
            url = f"http://localhost:{port}/editor"
            import webbrowser
            webbrowser.open(url)
            self.status_bar.set_status(f"🎨 เปิด Composer Editor: {url}")
        except Exception as e:
            self.status_bar.set_status(f"❌ เปิด Composer ไม่ได้: {e}")

    def _copy_overlay_url(self):
        """คัดลอก Overlay URL ไปยัง clipboard"""
        try:
            port = getattr(self.composer_server, '_port', 8808) if self.composer_server else 8808
            url = f"http://localhost:{port}/canvas"
            from PySide6.QtWidgets import QApplication
            clipboard = QApplication.clipboard()
            clipboard.setText(url)
            self.status_bar.set_status(f"📋 คัดลอก URL: {url}")
        except Exception as e:
            self.status_bar.set_status(f"❌ คัดลอก URL ไม่ได้: {e}")

    # ════════════════════════════════════════════════════════════
    # Translate mode (3-state)
    # ════════════════════════════════════════════════════════════
    def _on_translate_mode_changed(self, mode):
        """ตอนปุ่ม translate เปลี่ยน mode — apply ไป settings + pipeline"""
        if not self.settings:
            return
        if mode == "multilang":
            self.settings.auto_translate_enabled = False
            self.settings.multilang_enabled = True
        else:  # translate (default)
            self.settings.auto_translate_enabled = True
            self.settings.multilang_enabled = False
        if self.pipeline:
            self.pipeline.config.auto_translate_enabled = self.settings.auto_translate_enabled
            self.pipeline.config.multilang_enabled = self.settings.multilang_enabled
        labels = {"multilang": "อ่านทุกภาษา", "translate": "แปลภาษา"}
        self.status_bar.set_status(f"🌐 โหมดภาษา: {labels.get(mode, mode)}")

    # ════════════════════════════════════════════════════════════
    # Game Overlay: edit frame toggle
    # ════════════════════════════════════════════════════════════
    def _toggle_overlay_frames(self):
        """ซ่อน/แสดงกรอบ Game Overlay + Viewer Overlay (edit mode toggle)"""
        if hasattr(self, '_game_overlay') and self._game_overlay and self._game_overlay.is_running:
            try:
                self._game_overlay.toggle_edit_mode()
            except Exception as e:
                logger.debug(f"toggle_edit_mode failed: {e}")
        if hasattr(self, '_viewer_overlay') and self._viewer_overlay and self._viewer_overlay.is_running:
            try:
                self._viewer_overlay.toggle_edit_mode()
            except Exception:
                pass

    # ════════════════════════════════════════════════════════════
    # Global hotkeys (Game Overlay + Overlay+)
    # ════════════════════════════════════════════════════════════
    def _start_all_hotkeys(self):
        """register global hotkeys สำหรับ Game Overlay + Overlay+"""
        self._start_game_hotkey()
        self._start_more_overlay_hotkey()

    def _stop_all_hotkeys(self):
        """unregister global hotkeys ทั้งหมด"""
        try:
            import keyboard
            keyboard.unhook_all()
        except Exception:
            pass
        self._game_hotkey_active = False
        self._more_overlay_hotkey_active = False

    def _start_game_hotkey(self):
        """register Game Overlay hotkeys: toggle overlay + edit mode"""
        if self._game_hotkey_active:
            return
        try:
            import keyboard
            hk_toggle = getattr(self.settings, 'game_overlay_hotkey', 'ctrl+shift+g').strip().lower() or 'ctrl+shift+g'
            hk_edit = getattr(self.settings, 'game_overlay_hotkey_edit', 'ctrl+shift+h').strip().lower() or 'ctrl+shift+h'
            keyboard.add_hotkey(hk_toggle, self._on_game_hotkey_toggle, suppress=False)
            keyboard.add_hotkey(hk_edit, self._on_game_hotkey_edit, suppress=False)
            self._game_hotkey_active = True
        except Exception as e:
            logger.debug(f"Game hotkey register failed: {e}")

    def _start_more_overlay_hotkey(self):
        """register Overlay+ hotkeys: toggle + edit mode"""
        if self._more_overlay_hotkey_active:
            return
        try:
            import keyboard
            hk_toggle = getattr(self.settings, 'more_overlay_hotkey', 'ctrl+shift+m').strip().lower() or 'ctrl+shift+m'
            hk_edit = getattr(self.settings, 'more_overlay_hotkey_edit', 'ctrl+shift+n').strip().lower() or 'ctrl+shift+n'
            keyboard.add_hotkey(hk_toggle, self._on_more_overlay_hotkey_toggle, suppress=False)
            keyboard.add_hotkey(hk_edit, self._on_more_overlay_hotkey_edit, suppress=False)
            self._more_overlay_hotkey_active = True
        except Exception as e:
            logger.debug(f"Overlay+ hotkey register failed: {e}")

    def _reregister_hotkeys(self):
        """re-register hotkeys ทั้งหมด (เรียกหลัง settings เปลี่ยน hotkey)"""
        self._stop_all_hotkeys()
        self._start_all_hotkeys()

    def _on_game_hotkey_toggle(self):
        """hotkey callback: toggle Game Overlay — marshal ไป main thread"""
        QTimer.singleShot(0, self._toggle_overlay)

    def _on_game_hotkey_edit(self):
        """hotkey callback: toggle edit mode (Game Overlay + Viewer Overlay)"""
        QTimer.singleShot(0, self._toggle_overlay_frames)

    def _on_more_overlay_hotkey_toggle(self):
        """hotkey callback: toggle Overlay+ ทั้งหมด"""
        QTimer.singleShot(0, self._toggle_more_overlays)

    def _on_more_overlay_hotkey_edit(self):
        """hotkey callback: toggle edit mode Overlay+ ทั้งหมด"""
        QTimer.singleShot(0, self._toggle_more_overlay_edit)

    # ════════════════════════════════════════════════════════════
    # Overlay+ (MoreOverlay) — เปิด/ปิด/edit/settings
    # ════════════════════════════════════════════════════════════
    def _toggle_more_overlays(self):
        """เปิด/ปิด Overlay+ ทั้งหมด (max 3)"""
        if not hasattr(self, '_more_overlays'):
            self._more_overlays = []
        # ถ้ามีอันที่กำลังรันอยู่ → stop ทั้งหมด
        running = [mo for mo in self._more_overlays if mo.is_running]
        if running:
            self._stop_all_more_overlays()
            self.topbar.set_overlay_plus_active(False)
            self.status_bar.set_status(f"🪟 Overlay+ ปิดแล้ว ({len(running)} อัน)")
            return
        # spawn ใหม่
        self._open_all_more_overlays()

    def _open_all_more_overlays(self):
        """spawn Overlay+ ทั้งหมดที่ enabled + มี url (max 3)"""
        if not hasattr(self, '_more_overlays'):
            self._more_overlays = []
        from game_overlay import MoreOverlay
        overlays = list(getattr(self.settings, 'more_overlays', []))[:3]
        # pad ให้ครบ 3
        while len(overlays) < 3:
            overlays.append({"url": "", "x": -1, "y": -1, "w": 400, "h": 300, "alpha": 0.85, "enabled": False})
        spawned = 0
        for i, cfg in enumerate(overlays):
            url = cfg.get("url", "").strip()
            enabled = cfg.get("enabled", True)
            if not url or not enabled:
                continue
            mo = MoreOverlay(
                self, overlay_id=f"mo{i}", url=url,
                x=cfg.get("x", -1), y=cfg.get("y", -1),
                w=cfg.get("w", 400), h=cfg.get("h", 300),
                alpha=cfg.get("alpha", 0.85),
            )
            if mo.start():
                self._more_overlays.append(mo)
                spawned += 1
        if spawned > 0:
            self.topbar.set_overlay_plus_active(True)
            self.status_bar.set_status(f"🪟 Overlay+ เปิดแล้ว ({spawned} อัน)")
        else:
            self.status_bar.set_status("⚠️ Overlay+ ไม่มี URL ที่ตั้งไว้ — ไปตั้งค่าก่อน")

    def _stop_all_more_overlays(self):
        """stop Overlay+ ทั้งหมด"""
        if not hasattr(self, '_more_overlays'):
            return
        for mo in self._more_overlays:
            try:
                mo.stop()
            except Exception:
                pass
        self._more_overlays.clear()

    def _toggle_more_overlay_edit(self):
        """toggle edit mode ของ Overlay+ ทั้งหมด"""
        if not hasattr(self, '_more_overlays'):
            return
        for mo in self._more_overlays:
            if mo.is_running:
                try:
                    mo.toggle_edit_mode()
                except Exception:
                    pass

    def _save_more_overlay_position(self, overlay_id, x, y, w, h):
        """บันทึกตำแหน่ง Overlay+ ที่ผู้ใช้ลาก (callback จาก MoreOverlay)"""
        try:
            # parse index จาก overlay_id (mo0/mo1/mo2)
            idx = int(overlay_id.replace("mo", ""))
            overlays = list(getattr(self.settings, 'more_overlays', []))
            while len(overlays) <= idx:
                overlays.append({"url": "", "x": -1, "y": -1, "w": 400, "h": 300, "alpha": 0.85, "enabled": False})
            overlays[idx]["x"] = x
            overlays[idx]["y"] = y
            overlays[idx]["w"] = w
            overlays[idx]["h"] = h
            self.settings.more_overlays = overlays[:3]
            from settings import save_settings
            save_settings(self.settings)
        except Exception as e:
            logger.debug(f"_save_more_overlay_position failed: {e}")

    # ════════════════════════════════════════════════════════════
    # Viewer Overlay
    # ════════════════════════════════════════════════════════════
    def _toggle_viewer_overlay(self):
        """เปิด/ปิด Viewer Overlay — toggle สลับกัน (กดซ้ำไม่เพิ่มหน้าต่าง)"""
        # ★ ถ้ามี viewer overlay อยู่แล้ว (ไม่ว่าจะ running หรือค้าง) → stop ให้หมดก่อน
        existing = getattr(self, '_viewer_overlay', None)
        if existing is not None:
            try:
                existing.stop()
            except Exception:
                pass
            self._viewer_overlay = None
            if self.settings:
                self.settings.viewer_overlay_enabled = False
            self.status_bar.set_status("👥 Viewer Overlay ปิดแล้ว")
            return
        # spawn ใหม่
        self.status_bar.set_status("⏳ Viewer Overlay กำลังเปิด...")
        import threading
        def _bg_start():
            try:
                # ★ double-check กัน race condition
                if getattr(self, '_viewer_overlay', None) is not None:
                    return
                from game_overlay import ViewerOverlay
                ov = ViewerOverlay(self)
                ok = ov.start()
                if ok:
                    self._viewer_overlay = ov
                    QTimer.singleShot(0, lambda: self._on_viewer_overlay_started())
                else:
                    QTimer.singleShot(0, lambda: self.status_bar.set_status("❌ Viewer Overlay เปิดไม่ได้"))
            except Exception as e:
                logger.error(f"Viewer Overlay start failed: {e}")
                QTimer.singleShot(0, lambda: self.status_bar.set_status(f"❌ Viewer Overlay: {e}"))
        threading.Thread(target=_bg_start, name="ViewerOverlayToggle", daemon=True).start()

    def _on_viewer_overlay_started(self):
        """หลัง Viewer Overlay เปิดสำเร็จ"""
        if self.settings:
            self.settings.viewer_overlay_enabled = True
        self.status_bar.set_status("👥 Viewer Overlay เปิดแล้ว")
        # push counts ทันที
        self._update_viewer_ui()

    # ════════════════════════════════════════════════════════════
    # _open_settings_at — เปิด Settings ไปที่ section เฉพาะ
    # ════════════════════════════════════════════════════════════
    def _open_settings_at(self, section_key):
        """เปิด SettingsDialog ไปที่ section เฉพาะ"""
        from ui.dialogs.settings import SettingsDialog
        dlg = SettingsDialog(self)
        self._settings_dialog = dlg
        dlg.settings_changed.connect(self._on_settings_changed)
        # switch to section
        if section_key in dlg._sections:
            for i in range(dlg.sidebar.count()):
                item = dlg.sidebar.item(i)
                if item.data(Qt.UserRole) == section_key:
                    dlg.sidebar.setCurrentRow(i)
                    break
        dlg.exec()
        self._settings_dialog = None

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
                    self.status_bar.set_status(f"🔌 Auto-connect {plat}...")
                    self._connect_platform(plat)
                    return  # ★ connect ทีละตัว (กัน race condition)

    def closeEvent(self, event):
        """cleanup on close"""
        self._closing = True
        # ★ หยุด chat clients
        for plat, client in list(self.chat_clients.items()):
            try:
                client.disconnect()
            except Exception:
                pass
        # ★ หยุด global hotkeys
        self._stop_all_hotkeys()
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
        # ★ หยุด OBS WebSocket watcher
        if getattr(self, '_obs_watcher', None):
            try:
                self._obs_watcher.stop()
            except Exception:
                pass
        # ★ หยุด Game Overlay
        if hasattr(self, '_game_overlay') and self._game_overlay:
            try:
                self._game_overlay.stop()
            except Exception:
                pass
        # ★ หยุด Viewer Overlay
        if hasattr(self, '_viewer_overlay') and self._viewer_overlay:
            try:
                self._viewer_overlay.stop()
            except Exception:
                pass
        # ★ หยุด Overlay+ (MoreOverlay) ทั้งหมด
        self._stop_all_more_overlays()
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
