"""app.py — Main application window (QMainWindow)

ประกอบ UI ทั้งหมดเข้าด้วยกัน + เชื่อม logic (chat clients, TTS, pipeline)
"""
import logging
import os
import sys
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
    # ★ Auto-reconnect result — background thread → main thread (เดิมใช้ QTimer.singleShot
    #   จาก threading.Thread ธรรมดา ไม่มี Qt event loop → callback ไม่ยิงอย่างน่าเชื่อถือ
    #   → _on_reconnect_done ไม่เคยถูกเรียก → _connecting_platforms ค้าง + client ซอมบี้สะสม
    #   ระหว่างช่วงหลุด-reconnect → โปรแกรมค้าง/หนักขึ้นเรื่อย ๆ)
    _reconnect_result = Signal(str, object, bool, str)  # platform, client, ok, label
    _chat_message = Signal(object)  # ChatMessage
    _platform_error = Signal(str, str)  # platform, error_msg
    _viewer_update = Signal()
    # ★ Composer "เพิ่ม/แก้ไข Trigger" — callback มาจาก aiohttp thread → Signal marshal ไป main thread
    _open_playroom_sig = Signal()
    # ★ OBS status — tasklist/EnumWindows หนัก ห้ามรันบน UI thread (ค้าง UI ทุก 3 วิ) → bg + Signal marshal
    _obs_status_sig = Signal(bool)
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
    # ★ Twitch OAuth result — background thread → main thread (เก็บ token)
    _twitch_oauth_result_sig = Signal(object)  # result dict or None
    # ★ Chat echo — background thread (IRC reader) → main thread (add_message)
    _bot_response_sig = Signal(str, str)  # (platform, text) — bot ตอบ → echo ใน Live Chat
    # ★ YouTube OAuth result — background thread → main thread
    _youtube_oauth_result_sig = Signal(object)  # result dict or None
    # ★ Stream title — background thread → main thread (update card)
    _stream_title_sig = Signal(str, str)  # (platform, title)
    # ★ KICK OAuth result — background thread → main thread
    _kick_oauth_result_sig = Signal(object)  # result dict or None
    # ★ TTS status per message — pipeline thread → main thread (ไอคอนสถานะริมข้อความ)
    _tts_status_sig = Signal(str, str, object)  # (tts_id, status, info dict)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Broadcast Playroom by MeN9CH")
        self.setGeometry(100, 100, 1080, 720)
        self.setMinimumSize(960, 640)

        # ═══ Connect cross-thread signals ═══
        self._connect_result.connect(self._on_connect_result)
        self._reconnect_result.connect(self._on_reconnect_done)
        self._chat_message.connect(self._on_chat_message)
        self._tts_status_sig.connect(self._on_tts_status_ui)
        self._platform_error.connect(self._on_platform_error_signal)
        self._viewer_update.connect(self._update_viewer_ui)
        self._open_playroom_sig.connect(self._open_playroom_settings_tab)
        self._obs_status_sig.connect(self._on_obs_status_result)
        self._msg_translated.connect(self._on_msg_translated)
        self._overlay_started_sig.connect(self._on_overlay_started_sig)
        self._rvc_loaded_sig.connect(self._on_rvc_loaded)
        self._rvc_failed_sig.connect(self._on_rvc_load_failed)
        self._game_overlay_cmd_sig.connect(self._on_game_overlay_cmd)
        self._np_data_sig.connect(self._on_np_data_sig)
        self._omnivoice_progress_sig.connect(self._on_omnivoice_progress)
        self._omnivoice_ready_sig.connect(self._on_omnivoice_ready)
        self._twitch_oauth_result_sig.connect(self._on_twitch_oauth_result)
        self._bot_response_sig.connect(self._on_bot_response)
        self._youtube_oauth_result_sig.connect(self._on_youtube_oauth_result)
        self._stream_title_sig.connect(self._on_stream_title)
        self._kick_oauth_result_sig.connect(self._on_kick_oauth_result)

        # ═══ State ═══
        self._closing = False
        self.settings = None
        self.pipeline = None
        self.tts_engine = None
        self.audio_player = None
        self.chat_clients = {}
        self._chat_bots = {}  # ★ Chat Bots แยกตามแพลตฟอร์ม: {platform: TwitchBot}
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

        # ★ ตรวจ Twitch OAuth token ตอนเปิดโปรแกรม — หมดอายุ → ลอง refresh, refresh ไม่ได้ → ลบ + เตือน
        #   ปู้ม _oauth_expired_flags ไว้แจ้งเตือนใน Live Chat หลัง UI พร้อม
        self._oauth_expired_flags = []  # ["twitch", "kick", ...]
        if self.settings and getattr(self.settings, 'twitch_oauth_token', ''):
            def _twitch_clear(msg):
                logger.warning(msg)
                self.settings.twitch_oauth_token = ''
                self.settings.twitch_oauth_refresh = ''
                self.settings.twitch_bot_username = ''
                self._oauth_expired_flags.append("twitch")
            try:
                import urllib.request, json
                req = urllib.request.Request('https://id.twitch.tv/oauth2/validate')
                req.add_header('Authorization', f'OAuth {self.settings.twitch_oauth_token}')
                with urllib.request.urlopen(req, timeout=10) as resp:
                    result = json.loads(resp.read().decode())
                if result.get('expires_in', 0) < 300:  # เหลือ < 5 นาที → refresh เลย
                    logger.info("Twitch token expiring soon — refreshing on startup")
                    from twitch_oauth import refresh_access_token
                    refresh_result = refresh_access_token(self.settings.twitch_oauth_refresh)
                    if refresh_result and refresh_result.get('access_token'):
                        self.settings.twitch_oauth_token = refresh_result['access_token']
                        # ★ เก็บ refresh_token ใหม่ด้วย (Twitch หมุนเวียน — ตัวเก่าถูก invalidate)
                        if refresh_result.get('refresh_token'):
                            self.settings.twitch_oauth_refresh = refresh_result['refresh_token']
                        try:
                            import time as _t2
                            self.settings.twitch_token_expiry_ts = _t2.time() + int(refresh_result.get('expires_in', 0) or 0)
                        except Exception:
                            pass
                        logger.info("Twitch token refreshed on startup")
                    else:
                        _twitch_clear("Twitch token refresh failed — clearing token")
            except Exception as e:
                # ★ token invalid/หมดอายุ → ลอง refresh ก่อน (refresh token อาจยังใช้ได้)
                refreshed = False
                try:
                    from twitch_oauth import refresh_access_token as _tr
                    rr = _tr(self.settings.twitch_oauth_refresh)
                    if rr and rr.get('access_token'):
                        self.settings.twitch_oauth_token = rr['access_token']
                        self.settings.twitch_oauth_refresh = rr.get('refresh_token', '') or self.settings.twitch_oauth_refresh
                        refreshed = True
                        logger.info("Twitch token refreshed on startup (after validate fail)")
                except Exception:
                    pass
                if not refreshed:
                    _twitch_clear(f"Twitch token invalid/expired — clearing: {e}")
            try:
                self.settings.save_settings()
            except Exception:
                pass

        # ★ ตรวจ KICK OAuth token ตอนเปิดโปรแกรม — invalid → ลอง refresh, refresh ไม่ได้ → ลบ
        if self.settings and getattr(self.settings, 'kick_oauth_token', ''):
            try:
                from kick_oauth import get_user_info
                info = get_user_info(self.settings.kick_oauth_token)
                if not info:
                    raise RuntimeError("invalid token")
            except Exception as e:
                # ★ token invalid/หมดอายุ → ลอง refresh ก่อน (refresh token ยังใช้ได้)
                refreshed = False
                try:
                    from kick_oauth import refresh_access_token as _kr
                    rr = _kr(self.settings.kick_oauth_refresh)
                    if rr and rr.get('access_token'):
                        self.settings.kick_oauth_token = rr['access_token']
                        self.settings.kick_oauth_refresh = rr.get('refresh_token', '')
                        refreshed = True
                        logger.info("KICK token refreshed on startup")
                except Exception:
                    pass
                if not refreshed:
                    logger.warning(f"KICK token invalid/expired — clearing: {e}")
                    self.settings.kick_oauth_token = ''
                    self.settings.kick_oauth_refresh = ''
                    self.settings.kick_bot_username = ''
                    self.settings.kick_user_id = 0
                    self._oauth_expired_flags.append("kick")
                try:
                    self.settings.save_settings()
                except Exception:
                    pass

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
        # ★ single-connection enforcement — จดทุก client ที่สร้าง + กัน connect ซ้อน
        self._client_registry = {}          # platform → set ของ client ทั้งหมดที่เคยสร้าง
        self._connecting_platforms = {}     # platform → เวลาที่เริ่ม connect (กัน race + เคลียร์เองถ้าค้างเกิน 60 วิ)
        # ★ ASK Widget (โพลบน Overlay) — state + timers
        self._ask_state = None          # poll active หรือ None
        self._ask_gen = 0               # token กัน timer รุ่นเก่าปิดโพลใหม่
        self._ask_panel = None          # AskPanel (สร้างเมื่อกดปุ่มครั้งแรก)
        # ★ ข้อความที่เพิ่งส่งผ่านช่องพิมพ์โปรแกรม [(text, ts), ...]
        #   ใช้แยก: IRC echo ของที่โปรแกรมส่ง (ซ่อน — โปรแกรม echo แล้ว)
        #   กับข้อความที่เราพิมพ์ตรง ๆ บนหน้า Twitch (แสดงปกติ แต่ไม่อ่าน TTS)
        self._recent_own_sends = []
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
        # ★ start avatar mic watcher (ถ้ามี avatar widget แบบ mic mode อยู่แล้วตอน startup)
        self._sync_avatar_mic_watcher()
        self._sync_donate_goal_watcher()

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

        # ═══ OBS status poll (every 3s) — เปลี่ยนข้อความปุ่ม OBS ╢ู้กว่ารันอยู่หรือไม ═══
        self._obs_running_state = False
        self._obs_status_timer = QTimer(self)
        self._obs_status_timer.timeout.connect(self._poll_obs_status)
        self._obs_status_timer.start(3000)

        # ═══ Stream title — ไม่ auto refresh (มีปุ่ม 🔄 refresh ข้าง Edit ในการ์ดแพลตฟอร์ม)
        #    ดึง title ครั้งเดียวหลัง connect (singleShot ใน _on_connected) ═══

        # ═══ Auto-connect + timers ═══
        QTimer.singleShot(500, self._maybe_auto_connect)

        logger.info("Main window initialized")

        # ★ Auto-load OmniVoice ถ้า settings เป็น omnivoice (เบื้องหลัง + progress bar)
        if getattr(self.settings, 'tts_engine', 'edge') == 'omnivoice':
            QTimer.singleShot(2000, self._auto_load_omnivoice)

        # ★ Auto-check อัพเดท 5 วินาทีหลังเปิดโปรแกรม
        logger.info("scheduling auto_check_update in 5s")
        QTimer.singleShot(5000, self._auto_check_update)

        # ★ Auto-fetch รายชื่อผู้สนับสนุน 8 วินาทีหลังเปิดโปรแกรม (background)
        #   เก็บ cache ไว้ → แสดงตอน user เปิดหน้า สนับสนุน
        self._supporters_cache = None
        QTimer.singleShot(8000, self._load_supporters)

        # ★ Announcement — ดึงประกาศจากเจ้าของโปรแกรม (GitHub repo) 6 วินาทีหลังเปิด
        #   + refresh ทุก 1 ชั่วโมง (1 request ต่อรอบ — เบามาก)
        #   ★ user กดปิดแถบได้ — ประกาศใหม่ (id ใหม่) จะเด้งกลับมาเอง
        QTimer.singleShot(6000, self._check_announcement)
        self._announce_timer = QTimer(self)
        self._announce_timer.timeout.connect(self._check_announcement)
        self._announce_timer.start(60 * 60 * 1000)
        self._announce_thread = None

        # ★ แจ้งเตือนใน Live Chat เมื่อล็อกอินแพลตฟอร์มหมดอายุ (ตรวจตอนเปิดโปรแกรมแล้ว)
        QTimer.singleShot(5000, self._notify_expired_logins)

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
            # ★ ถ้ากำลัง connect อยู่ → รอเฉย ๆ (ไม่นับ attempts — กันนับเบิ้ลระหว่าง
            #   รอบเดิมยังบินอยู่ จนเกิน 5 แล้วหยุดทั้งที่รอบที่บินอยู่อาจกำลังจะสำเร็จ)
            _busy = self._connecting_platforms.get(platform)
            if _busy is not None and (now - _busy) < 60:
                continue
            # จำกัดจำนวน
            attempts = st.get('attempts', 0)
            if attempts >= 5:
                label = PLATFORM_LABELS.get(platform, platform)
                self._post_system_message(f"❌ หยุดพยายามเชื่อมต่อ {label} — เชื่อมไม่ได้ 5 ครั้งแล้ว")
                st['manual_disconnect'] = True
                st['attempts'] = 0
                # ★ การ์ดต้องกลับเป็น "ยังไม่เชื่อมต่อ" (เดิมค้างสถานะเดิมทิ้งไว้ = ปุ่มแดงค้าง)
                card = self._platform_cards.get(platform)
                if card:
                    card.set_connected(False)
                continue
            st['attempts'] = attempts + 1
            st['last_attempt'] = now
            self._do_reconnect(platform, target)

    def _do_reconnect(self, platform, target):
        """พยายาม reconnect platform (background thread)

        ★ ถ้ากำลัง connect อยู่แล้ว (มือหรืออีก reconnect) → ข้าม กัน client ซ้อน
        """
        st = self._reconnect_state.get(platform, {})
        label = PLATFORM_LABELS.get(platform, platform)
        # ★ guard — กำลัง connect อยู่แล้ว (มือหรืออีก reconnect) → ข้าม กัน client ซ้อน
        _busy_since = self._connecting_platforms.get(platform)
        if _busy_since is not None and (time.time() - _busy_since) < 60:
            logger.info(f"Reconnect {platform} skipped — already connecting")
            st['last_attempt'] = time.time()  # เลื่อนรอบไปรอบหน้า
            return
        self._connecting_platforms[platform] = time.time()
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
            # ★ ใช้ Signal แทน QTimer.singleShot (เดิมเรียกจาก threading.Thread ธรรมดา
            #   ไม่มี Qt event loop → callback ไม่ยิงอย่างน่าเชื่อถือ — pattern เดียวกับ
            #   _connect_result ที่ใช้กับปุ่มเชื่อมต่อมือ)
            self._reconnect_result.emit(platform, client, ok, label)

        threading.Thread(target=_bg_reconnect, name=f"Reconnect-{platform}", daemon=True).start()

    def _on_reconnect_done(self, platform, client, ok, label):
        """หลัง reconnect เสร็จ"""
        st = self._reconnect_state.get(platform, {})
        now = time.time()
        interval = getattr(self.settings, 'auto_reconnect_interval', 10.0)
        self._connecting_platforms.pop(platform, None)
        if ok and client:
            # ★ user สั่งตัดระหว่าง reconnect กำลังบิน → ไม่รับ client ตัวนี้ (เหมือน manual path)
            if st.get('manual_disconnect'):
                threading.Thread(target=lambda: self._safe_disconnect(client),
                                 name=f"Reject-{platform}", daemon=True).start()
                self._post_system_message(f"🛑 {label} ยกเลิกการเชื่อมต่อตามคำสั่ง (สั่งตัดระหว่างเชื่อมต่อ)")
                card = self._platform_cards.get(platform)
                if card:
                    card.set_connected(False)
                self._update_platform_count()
                return
            # ★ บังคับเหลือ client เดียว — กวาด client ซอมบี้ที่อาจเชื่อมสำเร็จช้ากว่า
            self._retire_other_clients(platform, client)
            self.chat_clients[platform] = client
            card = self._platform_cards.get(platform)
            if card:
                card.set_connected(True)
            st['attempts'] = 0
            st['last_attempt'] = None
            self._post_system_message(f"✅ เชื่อมต่อ {label} ใหม่สำเร็จ")
        else:
            # ★ reconnect ไม่สำเร็จ → ตัด client ที่สร้างค้างไว้ทิ้ง (กัน orphan — เฉพาะตัว
            #   กัน race กับรอบถัดไป; registry จะถูกกวาดตอนเชื่อมสำเร็จ)
            if client is not None:
                try:
                    client.disconnect()
                except Exception:
                    pass
            backoff = min(st.get('attempts', 1) * interval, 60)
            st['last_attempt'] = now + backoff - interval
            # ★ อัปเดตการ์ดเป็น "ยังไม่เชื่อมต่อ" ตามความจริง (กันค้างสถานะเชื่อมอยู่)
            card = self._platform_cards.get(platform)
            if card:
                card.set_connected(False)
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
            port = (self.composer_server.port if (self.composer_server and hasattr(self.composer_server, 'port')) else int(getattr(self.settings, 'composer_port', 8801)))
            self.composer_server = ComposerServer(self.settings, port=port)
            # ★ callbacks
            self.composer_server.on_save_widgets = self._save_composer_widgets
            self.composer_server.on_save_playroom_triggers = self._save_playroom_triggers
            # ★ "เพิ่ม/แก้ไข Trigger" ใน composer → เปิดแท็บ Playroom settings
            #   (ถูกเรียกจาก aiohttp thread → emit Signal เพื่อ marshal ไป main thread)
            self.composer_server.on_open_playroom_settings = lambda: self._open_playroom_sig.emit()
            if self.composer_server.start():
                actual_port = self.composer_server.port  # ★ port จริง (อาจเปลี่ยนถ้า default ไม่ว่าง)
                logger.info(f"Composer server: http://localhost:{actual_port}")
                # ★ ถ้า port เปลี่ยน → อัปเดต settings เพื่อจำไว้
                if actual_port != port:
                    self.settings.composer_port = actual_port
                    try:
                        from settings import save_settings
                        save_settings(self.settings)
                    except Exception:
                        pass
                    # ★ เตือนผู้ใช้ — OBS ที่ยังชี้ port เดิมจะเห็น overlay เก่า/ว่าง
                    #   (แจ้งแบบ defer — รอ UI พร้อม กันเรียกก่อน chat_panel ถูกสร้าง)
                    _old_port, _new_port = port, actual_port
                    def _warn_port_changed(op=_old_port, np_=_new_port):
                        try:
                            self._post_system_message(
                                f"⚠️ Composer เปิดที่ port {np_} (port {op} ไม่ว่าง) — "
                                f"ถ้า OBS ยังชี้ port {op} ให้เปลี่ยน Browser Source "
                                f"เป็น http://localhost:{np_}/ (ก๊อปได้ที่ปุ่ม Overlay ▸ คัดลอก URL)")
                            self.status_bar.set_status(
                                f"⚠️ Composer ใช้ port {np_} — Overlay URL: http://localhost:{np_}/")
                        except Exception:
                            pass
                    QTimer.singleShot(3000, _warn_port_changed)
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

    # ═══ Avatar widget — TTS speaking state ═══
    def _on_avatar_tts_speaking(self, talking: bool):
        """push TTS speaking state ไป Composer avatar widget (TTS mode only)

        เรียกจาก pipeline.on_playback_start/end (background thread) → push_avatar_state thread-safe
        ★ Mic mode ไม่ใช้ push นี้ — วัด RMS ใน Python แล้ว push เอง
        """
        if self.composer_server is None:
            return
        try:
            widgets = getattr(self.settings, 'composer_widgets', None) or []
            for w in widgets:
                if not isinstance(w, dict):
                    continue
                if w.get("type") == "avatar" and w.get("avatar_mode", "tts") == "tts":
                    wid = w.get("id", "")
                    if wid:
                        self.composer_server.push_avatar_state(wid, talking)
        except Exception:
            pass

    def _sync_avatar_mic_watcher(self):
        """★ sync mic watcher ตาม avatar widgets ที่ตั้งค่าเป็น mic mode

        ⚠ ตอนนี้โหมดไมโครโฟนถูกซ่อนชั่วคราว → หยุด watcher เสมอ
        """
        if self.composer_server is None:
            return
        # ★ หยุด watcher เสมอ (โหมดไมโครโฟนซ่อนอยู่)
        try:
            self.composer_server.stop_mic_watcher()
        except Exception:
            pass

    # ═══ Donate Goal widget — EasyDonate API watcher ═══
    def _sync_donate_goal_watcher(self):
        """★ sync donate goal watcher ตาม widget config

        เรียกตอน _on_settings_changed + _save_composer_widgets + startup
        - ถ้ามี donate_goal widget ที่มี API key → start watcher
        - ถ้าไม่มี → stop watcher
        """
        if self.composer_server is None or not self.settings:
            return
        try:
            # ★ stop existing watcher
            old = getattr(self, "_donate_goal_watcher", None)
            if old:
                old.stop()
                self._donate_goal_watcher = None

            widgets = getattr(self.settings, 'composer_widgets', None) or []
            dg_widget = None
            for w in widgets:
                if isinstance(w, dict) and w.get("type") == "donate_goal":
                    api_key = w.get("dg_api_key", "").strip()
                    if api_key:
                        dg_widget = w
                        break
            if dg_widget is None:
                return

            # ★ start watcher
            from easydonate_api import DonateGoalWatcher
            api_key = dg_widget.get("dg_api_key", "").strip()
            goal = dg_widget.get("dg_goal_amount", 1000)
            widget_id = dg_widget.get("id", "")

            def on_update(current, goal_amt, last_donor, last_amount, donor_count):
                """callback จาก background thread → push ไป overlay"""
                try:
                    self.composer_server.push_donate_goal(
                        widget_id, current, goal_amt, last_donor, last_amount, donor_count
                    )
                except Exception:
                    pass

            watcher = DonateGoalWatcher(api_key, on_update=on_update)
            ok = watcher.start(goal_amount=goal)
            if ok:
                self._donate_goal_watcher = watcher
                logger.info(f"donate goal watcher started — goal={goal}, widget={widget_id}")
            else:
                logger.warning("donate goal watcher: API key ไม่ถูกต้องหรือเชื่อมต่อไม่ได้")
        except Exception as e:
            logger.error(f"_sync_donate_goal_watcher error: {e}", exc_info=True)

    # ═══ OBS WebSocket auto-refresh ═══
    def _obs_ws_auto_refresh(self):
        """★ OBS WebSocket persistent watcher — เชื่อมค้างไว้ + auto-retry จนกว่าจะติด

        แก้ปัญหา: เปิด OBS ก่อน Broadcast Playroom → browser source cache หน้าเก่า → overlay ไม่แสดง
        เมื่อเชื่อมติด → refresh browser sources ที่ URL ชี้ overlay ของเรา (cache-bust ?v=ts)

        ★ ถ้า obs_ws_enabled=False → หยุด watcher เก่า + ไม่ขึ้นสถานะอะไรเลย (กัน "รอ OBS" ค้าง)

        ★ OBSWatcher callback มาจาก background thread → ใช้ status bar ผ่าน lambda ที่ marshal เอง
          (status_bar.set_status รับข้อความเข้า queue ที่ timer อ่าน → thread-safe)
        """
        # ★ หยุด watcher เก่าเสมอ (ตอน re-call จาก settings change)
        old = getattr(self, '_obs_watcher', None)
        if old:
            old.stop()
            self._obs_watcher = None

        if not getattr(self.settings, 'obs_ws_enabled', False):
            # ★ ปิดใช้งาน → ไม่เริ่ม watcher, ไม่ขึ้นสถานะเลย
            logger.info("OBS WS disabled — skipping watcher")
            return
        try:
            from obs_refresh import OBSWatcher

            host = getattr(self.settings, 'obs_ws_host', 'localhost')
            port = int(getattr(self.settings, 'obs_ws_port', 4455))
            pw = getattr(self.settings, 'obs_ws_password', '')

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
            logger.info(f"_save_composer_widgets called with {len(widgets)} widgets")
            self.settings.composer_widgets = list(widgets)
            if canvas_size in ("720p", "1080p"):
                self.settings.composer_canvas_size = canvas_size
            from settings import save_settings
            save_settings(self.settings)
            # ★ sync np_source จาก now_playing widget → set_source_filter() ให้ watcher
            #   (ผู้ใช้เลือก "เฉพาะ Spotify/YTMusic/browser" ใน composer UI → watcher ต้องรู้)
            self._sync_np_source_to_watcher(widgets)
            # ★ sync avatar mic watcher — ถ้ามี avatar widget แบบ mic mode → start/stop watcher
            #   สำคัญมาก: ถ้าไม่เรียกที่นี่ การแก้ avatar ใน composer จะไม่ start watcher
            self._sync_avatar_mic_watcher()
            self._sync_donate_goal_watcher()
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
        port = (self.composer_server.port if (self.composer_server and hasattr(self.composer_server, 'port')) else int(getattr(self.settings, 'composer_port', 8801)))
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
            # ★ TTS status tracking — ไอคอนสถานะริมข้อความ (รอคิว/กำลังอ่าน/อ่านแล้วกี่วิ)
            #   เรียกจาก compute/play thread → marshal ผ่าน signal (thread-safe)
            self.pipeline.on_tts_status = lambda tid, st, info: self._tts_status_sig.emit(tid, st, info)
            # ★ translation callback → re-render chat row (thread-safe via signal)
            self.pipeline.on_translated = lambda msg: self._msg_translated.emit(msg)
            # ★ Avatar widget — TTS speaking state (ส่งไป Composer avatar widget แบบ TTS mode)
            self.pipeline.on_playback_start = lambda: self._on_avatar_tts_speaking(True)
            self.pipeline.on_playback_end = lambda: self._on_avatar_tts_speaking(False)
            # ★ Playroom trigger → push clip ไป composer widget (เรียกจาก pipeline thread
            #   ตอน enqueue — hook ที่ _on_chat_message ไม่ได้เพราะ extra ยังไม่ถูกตั้งตอนนั้น)
            self.pipeline.on_playroom_clip = lambda clip, targets: self._push_playroom_clip(clip, targets)
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
                omnivoice_skip_min_length=int(getattr(s, 'omnivoice_skip_min_length', 6)),
                # ★ EXPERIMENTAL: คำสั้นเดี่ยว → ลองพูดซ้ำ+ตัดก่อน fallback edge-tts
                omnivoice_short_word_retry=bool(getattr(s, 'omnivoice_short_word_retry', False)),
                omnivoice_short_word_repeat=int(getattr(s, 'omnivoice_short_word_repeat', 3)),
                warn_sound_path=str(getattr(s, 'warn_sound_path', '') or ''),
                warn_sound_volume=float(getattr(s, 'warn_sound_volume', 0.6)),
                read_author=getattr(s, 'read_author', True),
                read_message=getattr(s, 'read_message', True),
                # ★ ต้องอ่านจาก settings เสมอ — เดิมไม่ได้ใส่ตรงนี้ → ทุกครั้งที่ settings
                #   auto-save (_on_settings_changed rebuild config ใหม่ทับของเดิม) mute
                #   จะรีเซ็ตกลับเป็น False เงียบ ๆ ทั้งที่ปุ่ม topbar ยังโชว์ "ปิดอ่าน" อยู่
                tts_muted=bool(getattr(s, 'tts_muted', False)),
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
                # ★ เอา max(1, ...) ออก — เดิมบังคับ floor 1 ทำให้ volume ที่ผู้ใช้ตั้งไว้ 0
                #   (ลาก slider สุดซ้าย = ต้องการเงียบ) ถูกดันกลับเป็น 1 ทุกครั้งที่ settings
                #   auto-save rebuild config (แทบไม่ต่างจาก 100 หลัง gain calculation)
                platform_volumes={
                    'twitch': getattr(s, 'tts_volume_twitch', 100),
                    'youtube': getattr(s, 'tts_volume_youtube', 100),
                    'mylive': getattr(s, 'tts_volume_mylive', 100),
                    'tiktok': getattr(s, 'tts_volume_tiktok', 100),
                    'kick': getattr(s, 'tts_volume_kick', 100),
                },
                # ★ per-platform mute (ปุ่มลำโพงในการ์ดแพลตฟอร์ม) — เดิมไม่เคยส่งเข้า
                #   pipeline เลย ปุ่มเป็นแค่ไอคอน ไม่เงียบเสียงจริง
                platform_muted={
                    'twitch': bool(getattr(s, 'tts_muted_twitch', False)),
                    'youtube': bool(getattr(s, 'tts_muted_youtube', False)),
                    'mylive': bool(getattr(s, 'tts_muted_mylive', False)),
                    'tiktok': bool(getattr(s, 'tts_muted_tiktok', False)),
                    'kick': bool(getattr(s, 'tts_muted_kick', False)),
                },
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
        # ★ wire toggle callback — ตอนกดซ่อน/แสดงยอดรวม → อัปเดตยอดในการ์ดแพลตฟอร์มทันที
        self.chat_panel.viewer_toggle_callback = self._update_viewer_ui
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

        # ★ AnnouncementBar — แถบประกาศจากเจ้าของโปรแกรม (อยู่เหนือ footer)
        #   ดึงจาก GitHub repo ตอนเปิดโปรแกรม + ทุก 10 นาที — ซ่อน default
        from ui.widgets.announcement_bar import AnnouncementBar
        self.announce_bar = AnnouncementBar(self)
        self.announce_bar.dismissed.connect(self._on_announcement_dismissed)
        layout.addWidget(self.announce_bar)

        # ★ StatusBar
        self.status_bar = StatusBar(self)
        # ★ sync version จาก version.json (อัปเดตหลัง patch ด้วย)
        try:
            from updater import get_current_version
            self.status_bar.set_version(f"v{get_current_version()}")
        except Exception:
            pass
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
        # ★ Update button — กดแล้วเด้ง dialog changelog + อัพเดท
        self.topbar.update_clicked.connect(self._on_update_button_clicked)
        # ★ OBS launch button — เปิด OBS หรือดึงหน้าต่าง OBS ขึ้นมา
        self.topbar.obs_launch_clicked.connect(self._on_obs_launch)

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
        # ★ Chat send (พิมพ์ส่งแชท — ต้องล็อกอิน Twitch OAuth ก่อน)
        self.chat_panel.send_requested.connect(self._on_chat_send)
        # ★ ปุ่ม ASK (หลัง A+) — toggle แผงโพล
        self.chat_panel.ask_toggled.connect(self._toggle_ask_panel)
        # ★ checkbox "TTS" ข้างปุ่มส่ง — โหลดค่าล่าสุดจาก settings + บันทึกทุกครั้งที่ติ๊ก
        try:
            self.chat_panel.tts_check.setChecked(
                bool(getattr(self.settings, 'chat_input_read_tts', False)))
            self.chat_panel.tts_check.toggled.connect(self._on_tts_check_toggled)
        except Exception as e:
            logger.debug(f"tts_check init error: {e}")
        # ★ ปุ่ม "เชื่อมต่อแชทบอท" overlay → เปิด settings หน้าแพลตฟอร์ม
        self.chat_panel.connect_bot_requested.connect(self._on_connect_bot_requested)
        # ★ Bot toggle (ON/OFF) → sync settings
        self.chat_panel.bot_toggle_requested.connect(self._on_bot_toggle)
        # ★ เมนูเร็ว (hold/คลิกขวาปุ่ม Bot) → เปิด-ปิด Bot เฉพาะแพลตฟอร์ม
        self.chat_panel.bot_platforms_changed.connect(self._on_bot_platforms_changed)
        self.chat_panel.set_bot_platforms(getattr(self.settings, 'bot_platforms', {}) or {})
        # ★ เฟือง → เปิด settings Chat Bot section
        self.chat_panel.bot_settings_requested.connect(lambda: self._open_settings_at("twitch_bot"))

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
            card.edit_stream_requested.connect(self._on_edit_stream_info)
            card.go_requested.connect(self._on_open_platform_page)
            card.refresh_stream_requested.connect(self._on_refresh_stream_title)
            card.mute_toggled.connect(self._on_platform_mute)
            card.volume_changed.connect(self._on_platform_volume)
            # ★ restore volume slider จาก settings (default 100 ถ้าไม่มี)
            vol_val = max(1, getattr(self.settings, f'tts_volume_{plat}', 100))
            card.vol_slider.setValue(vol_val)
            # ★ restore mute state จาก settings
            #   (เดิมใช้ setChecked() ซึ่งไม่มีผลเพราะปุ่มนี้ไม่ใช่ checkable button
            #   → ค่า mute รายแพลตฟอร์มที่เคยตั้งไว้ไม่เคย restore จริงหลัง rebuild)
            muted_val = getattr(self.settings, f'tts_muted_{plat}', False)
            card.set_muted(muted_val)
            self._platform_cards[plat] = card
            # ★ restore สถานะการเชื่อมต่อ (ถ้า platform นี้กำลังเชื่อมต่ออยู่ใน chat_clients)
            #   สำคัญมาก — ถ้าไม่ restore หลัง rebuild (เช่น ปิด settings) ปุ่มจะกลับเป็น "เชื่อมต่อ" ทั้งที่ยังเชื่อมอยู่
            if plat in self.chat_clients:
                card.set_connected(True)
                # ★ restore viewer count (ถ้ามีใน _viewer_counts อยู่แล้ว — กันหายตอน rebuild)
                if plat in self._viewer_counts:
                    viewers_hidden = getattr(self.chat_panel, '_viewers_hidden', False)
                    try:
                        card.set_viewer_count(self._viewer_counts[plat], hidden=viewers_hidden)
                    except Exception:
                        pass
            # ★ sync ไอคอนลำโพงกับ master mute ปัจจุบันทันที (กันการ์ดใหม่โชว์ 🔊
            #   ทั้งที่ "ปิดอ่าน" เปิดอยู่ — เกิดตอน initial build และตอน rebuild
            #   หลังเปลี่ยน show/hide platform ใน settings)
            master_muted = getattr(self.settings, 'tts_muted', False) if self.settings else False
            card.set_master_muted(master_muted)

    def _rebuild_platform_cards(self):
        """★ rebuild platform cards ใน sidebar (เรียกเมื่อ settings.show_* เปลี่ยน)"""
        # ★ disconnect clients ที่กำลังเชื่อมต่ออยู่ของ platform ที่ถูกซ่อน
        show_map = {
            'twitch': getattr(self.settings, 'show_twitch', True),
            'youtube': getattr(self.settings, 'show_youtube', True),
            'mylive': getattr(self.settings, 'show_mylive', True),
            'tiktok': getattr(self.settings, 'show_tiktok', False),
            'kick': getattr(self.settings, 'show_kick', False),
        }
        for plat, client in list(self.chat_clients.items()):
            if not show_map.get(plat, True):
                try: client.disconnect()
                except Exception: pass

        # ★ clear old cards
        self.sidebar.clear_platforms()
        self._platform_cards = {}

        # ★ rebuild
        self._build_platform_cards()

    def _on_platform_mute(self, platform, muted):
        """ปิด/เปิดเสียง TTS ของแพลตฟอร์ม — save + sync pipeline ทันที (live, ไม่ต้องรอ rebuild)

        ★ เดิมแค่ save settings เฉยๆ ไม่เคยส่งเข้า pipeline เลย → ปุ่มลำโพงเป็นแค่ไอคอน
        """
        if self.settings:
            muted_key = f'tts_muted_{platform}'
            setattr(self.settings, muted_key, muted)
        if self.pipeline and hasattr(self.pipeline, 'config'):
            pm = getattr(self.pipeline.config, 'platform_muted', None)
            if pm is None:
                pm = {}
                self.pipeline.config.platform_muted = pm
            pm[platform] = muted
        label = PLATFORM_LABELS.get(platform, platform)
        state = "ปิด" if muted else "เปิด"
        self.status_bar.set_status(f"🔊 {label}: {state}")

    def _update_platform_count(self):
        """อัปเดตตัวเลขจำนวนแพลตฟอร์มที่เชื่อมต่อใน sidebar"""
        connected = len(self.chat_clients)
        total = len(self._platform_cards)
        self.sidebar.update_platform_count(connected, total)

    def _on_platform_volume(self, platform, volume):
        """★ ปรับ volume ของแพลตฟอร์ม — save + sync pipeline ทันที"""
        if self.settings:
            vol_key = f'tts_volume_{platform}'
            setattr(self.settings, vol_key, volume)
        # ★ sync ไป pipeline (live update ไม่ต้องรอ rebuild)
        if self.pipeline and hasattr(self.pipeline, 'config'):
            pv = getattr(self.pipeline.config, 'platform_volumes', None)
            if pv is None:
                pv = {}
                self.pipeline.config.platform_volumes = pv
            pv[platform] = volume

    # ════════════════════════════════════════════════════════════
    # Platform connect/disconnect
    # ════════════════════════════════════════════════════════════
    def _get_platform_target(self, platform):
        """ดึง target (channel/URL) จาก settings"""
        if not self.settings:
            return ""
        target_map = {
            "twitch": getattr(self.settings, 'twitch_channel', ''),
            "youtube": getattr(self.settings, 'youtube_url', ''),
            "mylive": getattr(self.settings, 'mylive_url', ''),
            "tiktok": getattr(self.settings, 'tiktok_username', '') or getattr(self.settings, 'tiktok_user', ''),
            "kick": getattr(self.settings, 'kick_channel', ''),
        }
        return target_map.get(platform, '')

    def _connect_platform(self, platform):
        """เชื่อมต่อแพลตฟอร์ม

        ★ กัน client กำพร้า (เคยบั๊ก: reconnect ล้มเหลว 4 ครั้ง + กดมือ → client เก่ายัง
          JOIN ห้องค้าง → รับ echo ข้อความตัวเองซ้ำ 4 รอบ):
          1. ถ้ากำลัง connect อยู่แล้ว → ข้าม (กัน race)
          2. disconnect client เดิมทิ้งก่อนสร้างใหม่เสมอ
        """
        target = self._get_platform_target(platform)
        if not target:
            label = PLATFORM_LABELS.get(platform, platform)
            QMessageBox.warning(self, "ยังไม่ได้ตั้งค่า", f"กรุณาตั้งค่า {label} ใน Settings ก่อน")
            return

        # ★ guard — กำลัง connect/reconnect แพลตฟอร์มนี้อยู่ → ข้าม (กัน client ซ้อน)
        #   (ค้างเกิน 60 วิ = thread ตายค้าง → ปลดล็อกให้เริ่มใหม่ได้)
        _busy_since = self._connecting_platforms.get(platform)
        if _busy_since is not None and (time.time() - _busy_since) < 60:
            logger.info(f"Connect {platform} skipped — already connecting")
            return
        self._connecting_platforms[platform] = time.time()

        # ★ ตัด client เดิมทิ้งก่อน (ถ้ามี) — กัน orphan ที่ยัง JOIN ห้องค้างอยู่
        #   (ตัดเฉพาะตัวนี้ — การกวาด registry ทั้งหมดจะทำตอน connect ใหม่สำเร็จ
        #    กัน race ฆ่า client ใหม่ที่กำลังถูกสร้างพร้อมกัน)
        old = self.chat_clients.pop(platform, None)
        if old is not None:
            def _kill_old():
                try:
                    old.disconnect()
                except Exception:
                    pass
            threading.Thread(target=_kill_old, name=f"KillOld-{platform}", daemon=True).start()

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
                logger.info(f"Connecting to {platform} (target={target})...")
                client = self._create_client(platform)
                if client:
                    logger.info(f"{platform} client created, connecting...")
                    ok = client.connect(target)
                    logger.info(f"{platform} connect result: {ok}")
                else:
                    logger.error(f"{platform} client creation returned None!")
                    ok = False
                    client = None
            except Exception as e:
                logger.error(f"Connect {platform} failed: {e}", exc_info=True)
                ok = False
                client = None
            # ★ use signal to marshal back to main thread
            self._connect_result.emit(platform, client, ok)

        threading.Thread(target=_bg_connect, name=f"Connect-{platform}", daemon=True).start()

    def _create_client(self, platform):
        """สร้าง chat client สำหรับแพลตฟอร์ม + จดลง registry (เพื่อบังคับ connection เดียว)"""
        client = self._build_client(platform)
        if client is not None:
            self._client_registry.setdefault(platform, set()).add(client)
        return client

    def _safe_disconnect(self, client):
        """disconnect client แบบไม่มีทางโยน exception (ใช้ใน bg thread)"""
        try:
            client.disconnect()
        except Exception:
            pass

    def _retire_other_clients(self, platform, keep):
        """★ บังคับเหลือ client เดียวต่อแพลตฟอร์ม — disconnect ทุกตัวที่ไม่ใช่ keep

        เคยบั๊ก: reconnect ล้มเหลวหลายครั้ง + กดเชื่อมต่อมือ → client เก่าบางตัว
        เชื่อมสำเร็จช้ากว่า (ซอมบี้ JOIN ห้องค้าง) → พิมพ์ครั้งเดียวโดน echo เบิ้ลหลายรอบ
        """
        try:
            stale = [c for c in self._client_registry.get(platform, ()) if c is not keep]
            for c in stale:
                try:
                    c.disconnect()
                except Exception:
                    pass
            if keep is not None:
                self._client_registry[platform] = {keep}
            else:
                self._client_registry[platform] = set()
            if stale:
                logger.info(f"Retired {len(stale)} stale {platform} client(s)")
        except Exception as e:
            logger.debug(f"_retire_other_clients error: {e}")

    def _build_client(self, platform):
        """สร้าง chat client ตามแพลตฟอร์ม (ถูกเรียกจาก _create_client)"""
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
                # ★ ส่ง OAuth token + username ให้ TwitchChat (ถ้ามี → ส่งแชทได้)
                oauth_tok = getattr(self.settings, 'twitch_oauth_token', '') or ''
                bot_user = getattr(self.settings, 'twitch_bot_username', '') or ''
                client = TwitchChat(
                    on_message=on_message, on_status=on_status,
                    on_error=on_error, on_viewer_count=on_viewer_count,
                    text_filter=text_filter,
                    oauth_token=oauth_tok, bot_username=bot_user,
                )
                # ★ ส่ง refresh_token ด้วย (เพื่อ auto-refresh เมื่อ token หมดอายุ)
                #   ★ เดิมบรรทัดนี้อยู่หลัง return = dead code → client ไม่เคยได้
                #     refresh_token → token หมดอายุแล้วตก anonymous ทันที
                client._refresh_token = getattr(self.settings, 'twitch_oauth_refresh', '') or ''
                client._on_token_refreshed = (
                    lambda tok, ref, exp: self._on_twitch_token_refreshed(tok, ref, exp)
                )
                return client
            elif platform == "youtube":
                from chat_youtube import YouTubeChat
                # ★ ส่ง OAuth token + channel name (ถ้ามี → ส่งแชทได้)
                yt_oauth = getattr(self.settings, 'youtube_oauth_token', '') or ''
                yt_channel = getattr(self.settings, 'youtube_channel_name', '') or ''
                client = YouTubeChat(
                    on_message=on_message, on_status=on_status,
                    on_error=on_error, on_viewer_count=on_viewer_count,
                    oauth_token=yt_oauth, bot_username=yt_channel,
                )
                # ★ quota exceeded callback → mark quota
                client.on_quota_exceeded = lambda: self._on_youtube_quota_exceeded()
                # ★ ส่ง channel ID ของเรา (เพื่อเช็คว่าเป็นห้องเราไหม — กัน bot โพสในห้องคนอื่น)
                client._own_channel_id = getattr(self.settings, 'youtube_channel_id', '') or ''
                # ★ ส่ง refresh_token + callback (auto-refresh เมื่อ token หมดอายุ)
                client._refresh_token = getattr(self.settings, 'youtube_oauth_refresh', '') or ''
                client._on_token_refreshed = lambda new_token: self._on_youtube_token_refreshed(new_token)
                return client
            elif platform == "mylive":
                from chat_mylive import MyLiveChat
                return MyLiveChat(on_message=on_message, on_status=on_status, on_error=on_error, on_viewer_count=on_viewer_count)
            elif platform == "tiktok":
                from chat_tiktok import TikTokChat
                return TikTokChat(on_message=on_message, on_status=on_status, on_error=on_error, on_viewer_count=on_viewer_count)
            elif platform == "kick":
                from chat_kick import KickChat
                # ★ ส่ง OAuth token + user_id (ถ้ามี → ส่งแชท + bot + แก้ชื่อห้องได้)
                client = KickChat(
                    on_message=on_message, on_status=on_status,
                    on_error=on_error, on_viewer_count=on_viewer_count,
                    oauth_token=getattr(self.settings, 'kick_oauth_token', '') or '',
                    bot_username=getattr(self.settings, 'kick_bot_username', '') or '',
                    broadcaster_user_id=getattr(self.settings, 'kick_user_id', 0) or 0,
                )
                # ★ auto-refresh เมื่อ token หมดอายุระหว่างใช้งาน (ส่งแชทเจอ 401)
                client._refresh_token = getattr(self.settings, 'kick_oauth_refresh', '') or ''
                client._on_token_refreshed = (
                    lambda tok, ref: self._on_kick_token_refreshed(tok, ref)
                )
                return client
        except Exception as e:
            logger.error(f"Failed to create {platform} client: {e}")
        return None

    def _bot_handle_own_echo(self, msg):
        """★ echo ข้อความตัวเอง (ชื่อ account เรา) — ข้าม panel/TTS แต่ให้ bot ตอบคำสั่งได้

        (คงพฤติกรรมเดิม: พิมพ์ !xxx เอง → bot ตอบ — ใช้ทดสอบโดยไม่ต้องมีบัญชีแยก)
        """
        try:
            platform = getattr(msg, 'platform', '')
            if (getattr(msg, 'event', '') != 'message'
                    or not (getattr(msg, 'text', '') or '').strip().startswith('!')
                    or not getattr(self.settings, 'twitch_bot_enabled', False)):
                return
            bot = self._chat_bots.get(platform)
            if not bot:
                return
            client = self.chat_clients.get(platform)
            if not (client and getattr(client, 'can_send', False)):
                return
            if not (getattr(self.settings, 'bot_platforms', {}) or {}).get(platform, True):
                return
            bot.handle_message(getattr(msg, 'author', '') or '', getattr(msg, 'text', '') or '')
        except Exception as e:
            logger.debug(f"_bot_handle_own_echo error: {e}")

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

    def _push_playroom_clip(self, clip_name, widget_ids):
        """★ Playroom trigger จากแชท → push clip ไป composer playroom widgets
        (เรียกจาก pipeline thread — push_clip เป็น threadsafe อยู่แล้ว)
        """
        if self.composer_server is None or not clip_name:
            return
        try:
            self.composer_server.push_clip(clip_name, widget_ids=widget_ids or None)
        except Exception as e:
            logger.debug(f"playroom clip push failed: {e}")

    def _on_chat_message(self, msg):
        """รับ message จาก signal (main thread) — render + pipeline + forward"""
        # ★ system status message
        if isinstance(msg, _SystemMsg):
            self.status_bar.set_status(msg.text)
            return
        # ★ ดัก echo ของข้อความตัวเอง (Twitch IRC / KICK WebSocket สะท้อนข้อความเรากลับมา)
        #   แยก 2 กรณี:
        #   a. เป็นข้อความที่เพิ่งส่งผ่านช่องพิมพ์โปรแกรม → ซ่อน (โปรแกรม echo ให้แล้ว
        #      — เคยเบิ้ล 4 รอบตอน client ซ้อน) แต่ยังให้ bot ตอบ !xxx ที่เราพิมพ์เองได้
        #   b. เราพิมพ์ตรง ๆ บนหน้าเว็บ (Twitch/KICK) → แสดงใน Live Chat ปกติ แต่ห้ามอ่าน TTS
        try:
            _plat = getattr(msg, 'platform', '')
            if _plat in ('twitch', 'kick') and getattr(msg, 'event', 'message') == 'message':
                _own_login = ''
                if _plat == 'twitch':
                    _own_login = (getattr(self.settings, 'twitch_bot_username', '') or '').lower().strip()
                elif _plat == 'kick':
                    _own_login = (getattr(self.settings, 'kick_bot_username', '') or '').lower().strip()
                _author = (getattr(msg, 'author', '') or '').lower().strip()
                if _own_login and _author and _author == _own_login:
                    _now_own = time.time()
                    self._recent_own_sends = [
                        (t, ts) for t, ts in self._recent_own_sends if _now_own - ts < 15
                    ]
                    _text_norm = (getattr(msg, 'text', '') or '').strip()
                    _is_program_echo = any(t == _text_norm for t, _ in self._recent_own_sends)
                    if _is_program_echo:
                        self._bot_handle_own_echo(msg)
                        return
                    # ★ พิมพ์เองบนหน้าเว็บ → แสดงเสมอ + อ่าน TTS ตามค่าตั้งค่า > TTS
                    #   (read_own_web_messages — default เปิด = อ่านเสมอ)
                    #   คำตอบบอทไม่มาทางนี้ (ถูกจำเป็นส่งผ่านโปรแกรมแล้ว)
                    if not getattr(self.settings, 'read_own_web_messages', True):
                        if getattr(msg, 'extra', None) is None:
                            msg.extra = {}
                        msg.extra["_own_message"] = True  # แสดง แต่ไม่อ่าน
        except Exception:
            pass
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
        # ★ ติด id + เวลารับ — สำหรับติดตามสถานะ TTS (ไอคอนริมข้อความใน Live Chat)
        try:
            if getattr(msg, 'event', 'message') == 'message':
                if msg.extra is None:
                    msg.extra = {}
                if not msg.extra.get("_tts_id"):
                    import uuid as _uuid
                    msg.extra["_tts_id"] = _uuid.uuid4().hex[:8]
                    msg.extra["_tts_recv_ts"] = time.time()
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
        # ★ Chat Bot — ตรวจคำสั่ง !xxx และตอบกลับ (ตอบเฉพาะแพลตฟอร์มที่ถามมา)
        #   ★ bot แยกตามแพลตฟอร์ม → พิมพ์ใน Twitch ตอบใน Twitch ไม่ส่งทะลักไปที่อื่น
        msg_platform = getattr(msg, 'platform', '')
        if getattr(msg, 'event', 'message') == 'message':
            bot_enabled = getattr(self.settings, 'twitch_bot_enabled', False)
            has_bot = msg_platform in self._chat_bots
            # ★ ดักสำคัญ: ต้อง can_send=True ถึงจะให้ bot ตอบ (กันโพสในห้องคนอื่น)
            client = self.chat_clients.get(msg_platform)
            client_can_send = bool(client and getattr(client, 'can_send', False))
            # ★ ปิด Bot เฉพาะแพลตฟอร์มนี้ → ไม่ตอบคำสั่ง
            plat_bot_ok = (getattr(self.settings, 'bot_platforms', {}) or {}).get(msg_platform, True)
            if bot_enabled and has_bot and client_can_send and plat_bot_ok:
                try:
                    bot = self._chat_bots[msg_platform]
                    bot.count_chat_activity(msg.author or '')
                    bot.handle_message(msg.author or '', msg.text or '')
                except Exception as e:
                    logger.error(f"bot handle_message error: {e}", exc_info=True)
        # ★ Chat Bot — event responses (sub/bits/raid/follow → ตอบในแพลตฟอร์มเดียวกัน)
        # ★ ดักสำคัญ: ต้อง can_send=True (กัน event response ในห้องคนอื่น)
        if (getattr(msg, 'event', 'message') in ('sub', 'resub', 'bits', 'raid', 'follow', 'subgift')
                and msg_platform in self._chat_bots
                and getattr(self.settings, 'twitch_bot_enabled', False)
                and client_can_send
                and (getattr(self.settings, 'bot_platforms', {}) or {}).get(msg_platform, True)):
            try:
                event_type = getattr(msg, 'event', '')
                # ★ KICK subgift → ใช้ template "sub" (ข้อความ "มอบ KICK Sub")
                template_type = "sub" if event_type == "subgift" else event_type
                kwargs = {"user": getattr(msg, 'author', '') or '?'}
                if event_type in ("sub", "resub"):
                    extra = getattr(msg, 'extra', {}) or {}
                    months = extra.get('months', '1')
                    kwargs["months"] = months
                elif event_type == "bits":
                    kwargs["amount"] = getattr(msg, 'amount', 0) or 0
                elif event_type == "raid":
                    kwargs["raid_count"] = getattr(msg, 'amount', 0) or 0
                self._chat_bots[msg_platform].handle_event(template_type, **kwargs)
            except Exception as e:
                logger.debug(f"bot handle_event error: {e}")
        # ★ system message → status bar
        if getattr(msg, 'event', '') == 'system':
            self.status_bar.set_status(msg.text or msg.system_text or '')

        # ★ Bot filter — เช็คว่าผู้ส่งเป็นบอทไหม (ไม่อ่าน TTS + อาจซ่อนจาก overlay)
        is_bot = self._is_bot_author(msg.author or '', msg)
        # ★ ดักคำสั่ง !xxx → ไม่อ่าน TTS (กัน !%donate ถูกอ่านเป็น "โดเนท")
        is_command = (getattr(msg, 'text', '') or '').strip().startswith('!')
        skip_tts = is_bot or is_command
        # ★ ASK — จับโหวต (ข้อความตัวเดียว A/B/1/2) → ไม่อ่าน TTS แต่ยังแสดงในแชท
        if (not skip_tts and self._ask_state is not None
                and self._ask_state.get('phase') == 'voting'
                and getattr(msg, 'event', 'message') == 'message'):
            if self._ask_try_vote(getattr(msg, 'platform', ''), msg.author or '', msg.text or ''):
                skip_tts = True

        # ★ ไอคอนสถานะ TTS — ข้าม → ⊘ / pipeline ไม่พร้อม → ⊘
        if getattr(msg, 'event', 'message') == 'message':
            _tid = (msg.extra or {}).get("_tts_id", "")
            if skip_tts:
                _reason = "คำสั่ง !xxx (ไม่อ่าน)" if is_command else "บอท/ข้อความของเราเอง"
                self._on_tts_status_ui(_tid, "skipped", {"reason": _reason})
            elif not self.pipeline:
                self._on_tts_status_ui(_tid, "skipped", {"reason": "TTS ไม่พร้อม"})

        # ★ pipeline (TTS queue) — ข้ามบอท + ข้ามคำสั่ง !xxx
        if self.pipeline and getattr(msg, 'event', 'message') == 'message' and not skip_tts:
            try:
                # ★ strip }color{ prefix สำหรับ TTS โดยใช้ COPY — ไม่แตะ msg ต้นฉบับ
                #   (overlay ต้องได้ }red{ครบ เพื่อ render สี — จึงห้าม modify ที่นี่)
                import re as _re_color
                import copy as _copy
                _tts_msg = msg
                _cm = _re_color.match(r'^\}([a-zA-Z]+)\{\s*', msg.text or '')
                if _cm:
                    _tts_msg = _copy.copy(msg)
                    _tts_msg.text = (msg.text or '')[_cm.end():]
                    _extra = dict(getattr(msg, 'extra', None) or {})
                    if _extra.get('raw_text'):
                        _extra['raw_text'] = _extra['raw_text'][_cm.end():]
                    _tts_msg.extra = _extra
                self.pipeline.enqueue(_tts_msg)
            except Exception:
                pass
        # ★ system messages (สถานะเชื่อมต่อ ✅/⚪/⚠️) → ห้ามส่งไป composer + OBS overlay เด็ดขาด
        is_system = (getattr(msg, 'event', '') == 'system')
        if not is_system:
            # ★ overlay filter — ถ้าเป็นบอท + user เลือกซ่อน → ข้าม overlay
            hide_from_overlay = is_bot and getattr(self.settings, 'overlay_hide_bots', True)
            if not hide_from_overlay:
                # ★ forward to composer (Canvas overlay — includes playroom widget + emote party widget)
                self._composer_push_message(msg)
                self._composer_push_emotes(msg)
                # ★ forward to overlay server (OBS overlay)
                self._overlay_push_message(msg)
        # ★ forward to game overlay (ถ้าเปิดอยู่) — ★ system messages ห้ามขึ้น overlay ทุกส่วน
        if hasattr(self, '_game_overlay') and self._game_overlay and self._game_overlay.is_running:
            if is_system:
                pass  # ★ system message → แสดงในโปรแกรมเท่านั้น (Live Chat)
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
        self._connecting_platforms.pop(platform, None)
        if ok and client:
            # ★ user สั่งตัดการเชื่อมต่อระหว่างที่กำลัง connect อยู่ → ไม่รับ client ตัวนี้
            #   (เดิม: เสร็จทีหลังแล้วเก็บเข้าระบบ = เชื่อมสวนคำสั่งผู้ใช้)
            st = self._reconnect_state.get(platform, {})
            if st.get('manual_disconnect'):
                threading.Thread(target=lambda: self._safe_disconnect(client),
                                 name=f"Reject-{platform}", daemon=True).start()
                self._post_system_message(f"🛑 {label} ยกเลิกการเชื่อมต่อตามคำสั่ง (สั่งตัดระหว่างเชื่อมต่อ)")
                if card:
                    card.set_connected(False)
                self._update_platform_count()
                return
            # ★ บังคับเหลือ client เดียว — disconnect ทุกตัวที่เคยสร้างแล้วไม่ใช่ตัวนี้
            self._retire_other_clients(platform, client)
            self.chat_clients[platform] = client
            if card:
                card.set_connected(True)
            self._post_system_message(f"✅ {label} เชื่อมต่อแล้ว")
            self.status_bar.set_status(f"✅ {label} เชื่อมต่อแล้ว")
            # ★ เชื่อมต่อสำเร็จ → อัปเดตช่องพิมพ์ (แสดงถ้า OAuth พร้อม)
            self._update_chat_send_state()
            # ★ push viewer ทันที (icon แพลตฟอร์ม + 0) — กันรอยอดจริงนาน
            self._update_viewer_ui()
            # ★ YouTube: liveChatId อาจยังไม่พร้อมทันที → recheck หลัง 3 วิ
            if platform == "youtube":
                QTimer.singleShot(3000, self._update_chat_send_state)
                QTimer.singleShot(6000, self._update_chat_send_state)
            # ★ connect → start bot + timer (ถ้าเปิดใช้ + client รองรับการส่ง)
            self._start_twitch_bot(platform)
            # ★ ดึง stream title ทันที (รอ 3 วิ ให้ connection พร้อม) — QTimer ใช้ได้เพราะอยู่ใน main thread
            QTimer.singleShot(3000, self._poll_stream_titles)
        else:
            # ★ connect ไม่สำเร็จ → ตัด client ที่สร้างค้างไว้ทิ้ง (กัน orphan — ตัดเฉพาะตัว
            #   กัน race กับการ connect รอบใหม่ที่อาจเริ่มขึ้นแล้ว)
            if client is not None:
                def _kill_failed(c=client):
                    try:
                        c.disconnect()
                    except Exception:
                        pass
                threading.Thread(target=_kill_failed, name=f"KillFailed-{platform}", daemon=True).start()
            if card:
                card.set_connected(False)
            self._post_system_message(f"❌ {label} เชื่อมต่อไม่ได้")
            self.status_bar.set_status(f"❌ {label} เชื่อมต่อไม่ได้")
            # ★ หลุดการเชื่อมต่อ → ซ่อนช่องพิมพ์ + หยุด bot
            self._update_chat_send_state()
            self._stop_twitch_bot(platform)
        self._update_platform_count()

    # ════════════════════════════════════════════════════════════
    # ★ Chat Send + Twitch OAuth (Phase 1)
    # ════════════════════════════════════════════════════════════

    def _start_twitch_bot(self, platform: str = "twitch"):
        """★ เริ่ม Chat Bot — สร้าง instance + start timer (เรียกตอนแพลตฟอร์ม connect)

        Args:
            platform: แพลตฟอร์มที่เชื่อมต่อ ("twitch", "youtube", ฯลฯ)
        """
        try:
            client = self.chat_clients.get(platform)
            if not client or not getattr(client, 'can_send', False):
                return  # ไม่ได้ล็อกอิน → ไม่สร้าง bot
            # ★ ปิด Bot เฉพาะแพลตฟอร์มนี้ (settings → Chat Bot → ให้ Bot ทำงานที่)
            if platform in ("twitch", "youtube", "kick"):
                _bp = getattr(self.settings, 'bot_platforms', {}) or {}
                if not _bp.get(platform, True):
                    logger.info(f"Chat Bot disabled for {platform} (per-platform toggle)")
                    return
            if not hasattr(client, 'send_message'):
                return  # client ไม่รองรับการส่ง → ข้าม
            from twitch_bot import TwitchBot
            # ★ รวบรวม event responses จาก settings
            event_responses = self._get_bot_event_responses()
            bot_username = self._get_bot_username(platform)
            # ★ สร้าง/อัปเดต bot สำหรับแพลตฟอร์มนี้
            if platform not in self._chat_bots:
                # ★ เลือก commands/timers/events ตามแพลตฟอร์ม
                if platform == "youtube":
                    commands = getattr(self.settings, 'youtube_bot_commands', {}) or {}
                    timers = getattr(self.settings, 'youtube_bot_timers', []) or []
                    event_responses = {
                        "sub": getattr(self.settings, 'youtube_bot_event_sub', '') or '',
                        "superchat": getattr(self.settings, 'youtube_bot_event_superchat', '') or '',
                        "member": getattr(self.settings, 'youtube_bot_event_member', '') or '',
                    }
                    events_enabled = getattr(self.settings, 'youtube_bot_events_enabled', True)
                else:
                    commands = getattr(self.settings, 'twitch_bot_commands', {}) or {}
                    timers = getattr(self.settings, 'twitch_bot_timers', []) or []
                    event_responses = self._get_bot_event_responses()
                    events_enabled = getattr(self.settings, 'twitch_bot_events_enabled', True)
                self._chat_bots[platform] = TwitchBot(
                    send_callback=client.send_message,
                    bot_username=bot_username,
                    commands=commands,
                    timers=timers,
                    event_responses=event_responses,
                    events_enabled=events_enabled,
                    on_bot_response=lambda text, p=platform: self._bot_response_sig.emit(p, text),
                )
                logger.info(f"Chat Bot started for {platform}")
            else:
                # ★ อัปเดต send_callback (เผื่อ client เปลี่ยน)
                self._chat_bots[platform]._send = client.send_message
                self._chat_bots[platform].update_commands(getattr(self.settings, 'twitch_bot_commands', {}) or {})
                self._chat_bots[platform].update_timers(getattr(self.settings, 'twitch_bot_timers', []) or [])
                self._chat_bots[platform].update_event_responses(
                    event_responses,
                    getattr(self.settings, 'twitch_bot_events_enabled', True),
                )
            # ★ start timer (ถ้ามี timers + bot enabled)
            if getattr(self.settings, 'twitch_bot_enabled', False):
                self._chat_bots[platform].start_timers()
        except Exception as e:
            logger.error(f"_start_twitch_bot error ({platform}): {e}")

    def _get_bot_event_responses(self):
        """★ รวบรวม event responses จาก settings → dict"""
        return {
            "sub": getattr(self.settings, 'twitch_bot_event_sub', '') or '',
            "resub": getattr(self.settings, 'twitch_bot_event_resub', '') or '',
            "bits": getattr(self.settings, 'twitch_bot_event_bits', '') or '',
            "raid": getattr(self.settings, 'twitch_bot_event_raid', '') or '',
            "follow": getattr(self.settings, 'twitch_bot_event_follow', '') or '',
        }

    def _get_bot_username(self, platform: str) -> str:
        """★ ดึง bot username สำหรับแพลตฟอร์มนั้น"""
        if platform == "twitch":
            return getattr(self.settings, 'twitch_bot_username', '') or ''
        if platform == "youtube":
            return getattr(self.settings, 'youtube_channel_name', '') or ''
        if platform == "kick":
            return getattr(self.settings, 'kick_bot_username', '') or ''
        return ""

    def _stop_twitch_bot(self, platform: str = "twitch"):
        """★ หยุด Chat Bot ของแพลตฟอร์มนั้น — stop timer (เรียกตอน disconnect)"""
        try:
            bot = self._chat_bots.get(platform)
            if bot is not None:
                bot.stop_timers()
                del self._chat_bots[platform]
                logger.info(f"Chat Bot stopped for {platform}")
        except Exception as e:
            logger.debug(f"_stop_twitch_bot error ({platform}): {e}")

    def _update_twitch_bot_config(self):
        """★ อัปเดต bot config ทุกตัวจาก settings (เรียกเมื่อ settings เปลี่ยน)"""
        try:
            if not self._chat_bots:
                return
            commands = getattr(self.settings, 'twitch_bot_commands', {}) or {}
            timers = getattr(self.settings, 'twitch_bot_timers', []) or []
            event_responses = self._get_bot_event_responses()
            events_enabled = getattr(self.settings, 'twitch_bot_events_enabled', True)
            bot_enabled = getattr(self.settings, 'twitch_bot_enabled', False)
            for platform, bot in self._chat_bots.items():
                bot.update_commands(commands)
                bot.update_timers(timers)
                bot.update_event_responses(event_responses, events_enabled)
                # ★ ถ้า bot_enabled = False → stop timer
                if not bot_enabled:
                    bot.stop_timers()
                else:
                    # ★ bot_enabled = True + แพลตฟอร์มเชื่อมต่อ → start timer
                    client = self.chat_clients.get(platform)
                    if client and getattr(client, 'is_connected', False):
                        bot.start_timers()
        except Exception as e:
            logger.debug(f"_update_twitch_bot_config error: {e}")

    def _on_bot_response(self, platform: str, text: str):
        """★ Bot ส่งข้อความตอบ → echo ลงใน Live Chat ด้วยชื่อ Baitoei-Bot

        ★ ใช้ชื่อ twitch_bot_name (default "Baitoei-Bot") ไม่ใช่ชื่อเรา
        ★ mark เป็น _own_message → ข้าม TTS + bot filter
        """
        try:
            # ★ จำข้อความที่บอทเพิ่งส่ง — ให้ IRC/WS echo ที่ย้อนกลับมาถูกจัดเป็น
            #   "ส่งผ่านโปรแกรม" (ซ่อน ไม่อ่าน) ตามกฎ กันโดนตีความเป็นพิมพ์บนเว็บ
            #   แล้วโดนอ่านออกเสียงซ้ำ
            try:
                _now_bot = time.time()
                self._recent_own_sends = [
                    (t, ts) for t, ts in self._recent_own_sends if _now_bot - ts < 15
                ]
                for _line in text.split("\n"):
                    _line = _line.strip()
                    if _line:
                        self._recent_own_sends.append((_line, _now_bot))
            except Exception:
                pass
            from chat_twitch import ChatMessage
            bot_name = getattr(self.settings, 'twitch_bot_name', '') or 'Bot'
            my_msg = ChatMessage(
                platform=platform,
                author=bot_name,
                text=text,
                event="message",
                extra={
                    "_own_message": True,
                    "_is_bot_response": True,
                    "color": "#a78bfa",
                    "badges": ["broadcaster"],
                    "timestamp": time.time(),
                },
            )
            self.chat_panel.add_message(my_msg)
            if hasattr(self, '_popout_window') and self._popout_window:
                self._popout_window.add_message(my_msg)
            logger.info(f"Bot response echoed: {bot_name}: {text[:50]}")
        except Exception as e:
            logger.error(f"_on_bot_response error: {e}", exc_info=True)

    def _is_bot_author(self, author: str, msg=None) -> bool:
        """★ เช็คว่าผู้ส่งเป็นบอทไหม (เพื่อข้าม TTS + ซ่อน overlay)

        เช็ค:
        1. msg.extra["_own_message"] = True (ข้อความ echo ที่เราพิมพ์เอง — ข้าม TTS แต่แสดงใน Live Chat)
        2. ตรงกับ twitch_bot_username (account ที่ OAuth — ข้อความที่โปรแกรม/บอทส่ง
           จะ echo กลับมาเป็นชื่อนี้ → ห้ามอ่าน TTS เด็ดขาด)
        3. ตรงกับ twitch_bot_name (default "Baitoei-Bot")
        4. อยู่ใน tts_bot_blacklist (Nightbot, StreamElements, ฯลฯ)

        Returns:
            True = เป็นบอท/ของเรา → ข้าม TTS + (อาจ) ซ่อน overlay
            False = คนจริง → อ่านปกติ
        """
        # ★ เช็ค own_message flag (ข้อความ echo ที่เราพิมพ์ → ข้าม TTS)
        if msg is not None:
            extra = getattr(msg, 'extra', {}) or {}
            if extra.get("_own_message"):
                return True
        if not author:
            return False
        author_lower = author.lower().strip()
        # ★ ไม่ดักชื่อ account ตัวเอง (twitch/kick username) อีกแล้ว —
        #   กฎใหม่: ข้อความที่เราพิมพ์บนหน้าเว็บ = อ่าน TTS ปกติ
        #   (ของที่ส่งผ่านโปรแกรม/บอท ถูกดักที่ประตู _on_chat_message แล้ว
        #    หรือมีธง _own_message จาก echo ฝั่งโปรแกรม)
        # ★ เช็ค bot_name (label ที่ user ตั้ง — default Baitoei-Bot)
        bot_name = (getattr(self.settings, 'twitch_bot_name', '') or '').lower().strip()
        if bot_name and author_lower == bot_name:
            return True
        # ★ เช็ค blacklist (Nightbot, StreamElements, ฯลฯ)
        blacklist = getattr(self.settings, 'tts_bot_blacklist', []) or []
        if author_lower in [b.lower().strip() for b in blacklist]:
            return True
        return False

    def _update_chat_send_state(self):
        """★ อัปเดต platform chips — โชว์เฉพาะเมื่อเชื่อมต่อแชท + OAuth login สำเร็จ

        ★ กฎ:
          ไม่เชื่อมต่อแชท = ไม่มีช่องพิมพ์
          เชื่อมต่อแชท + ไม่มี OAuth = ไม่มีช่องพิมพ์
          เชื่อมต่อแชท + OAuth = มีช่องพิมพ์
        """
        try:
            from ui.platform_icons import get_platform_pixmap
            from PySide6.QtGui import QPixmap
            platforms = []
            # ★ เช็คจาก settings (ไม่ใช่ client — client อาจเก็บ token เก่า)
            has_twitch_oauth = bool(getattr(self.settings, 'twitch_oauth_token', ''))
            twitch_connected = "twitch" in self.chat_clients and getattr(self.chat_clients["twitch"], '_is_connected', False)
            if has_twitch_oauth and twitch_connected:
                icon = QPixmap()
                try:
                    icon = get_platform_pixmap("twitch", 16) or QPixmap()
                except Exception:
                    pass
                platforms.append({
                    "key": "twitch",
                    "label": "Twitch",
                    "icon": icon,
                    "active": True,
                })
            # ★ KICK chip — เชื่อมต่อ + ล็อกอิน OAuth = พิมพ์ส่งได้
            has_kick_oauth = bool(getattr(self.settings, 'kick_oauth_token', ''))
            kick_connected = "kick" in self.chat_clients and getattr(self.chat_clients["kick"], '_is_connected', False)
            if has_kick_oauth and kick_connected:
                icon = QPixmap()
                try:
                    icon = get_platform_pixmap("kick", 16) or QPixmap()
                except Exception:
                    pass
                platforms.append({
                    "key": "kick",
                    "label": "KICK",
                    "icon": icon,
                    "active": True,
                })
            # ★ overlay ล็อคช่องพิมพ์ = มีแพลตฟอร์มเชื่อมแชทอยู่ แต่ไม่มีแพลตฟอร์มไหนส่งได้เลย
            #   (ถ้ามีตัวใดตัวหนึ่ง OAuth แล้ว → ปลดล็อคทันที แม้อีกตัวจะยังไม่ล็อกอิน)
            twitch_no_oauth = twitch_connected and not has_twitch_oauth
            kick_no_oauth = kick_connected and not has_kick_oauth
            show_lock_overlay = (twitch_no_oauth or kick_no_oauth) and not platforms
            self.chat_panel.update_platform_chips(platforms, twitch_connected_no_oauth=show_lock_overlay)
        except Exception as e:
            logger.error(f"_update_chat_send_state error: {e}", exc_info=True)

    def _on_bot_platforms_changed(self, platforms: dict):
        """★ เมนูเร็ว (hold ปุ่ม Bot) — เปิด/ปิด Bot เฉพาะแพลตฟอร์ม + sync ทันที"""
        try:
            self.settings.bot_platforms = {
                k: bool(v) for k, v in (platforms or {}).items()}
            self.settings.save_settings()
        except Exception:
            pass
        # ★ sync start/stop ตาม toggle
        _bp = self.settings.bot_platforms
        for _plat in ("twitch", "youtube", "kick"):
            if _plat not in self.chat_clients:
                continue
            if _bp.get(_plat, True):
                if getattr(self.settings, 'twitch_bot_enabled', False):
                    self._start_twitch_bot(_plat)
            else:
                self._stop_twitch_bot(_plat)
        off = [p for p, on in _bp.items() if not on]
        if off:
            self.status_bar.set_status(f"🤖 Bot ปิดที่: {', '.join(off.upper())}")
        else:
            self.status_bar.set_status("🤖 Bot เปิดทุกแพลตฟอร์ม")

    def _on_bot_toggle(self, enabled):
        """★ toggle Bot ON/OFF จาก chat panel → sync settings"""
        self.settings.twitch_bot_enabled = enabled
        try:
            self.settings.save_settings()
        except Exception:
            pass
        if enabled:
            self._start_twitch_bot("twitch")
        else:
            self._stop_twitch_bot("twitch")
        self.status_bar.set_status(f"🤖 Chat Bot: {'เปิด' if enabled else 'ปิด'}")

    def _on_open_platform_page(self, platform):
        """★ ปุ่ม 🚀 GO — เปิดหน้าช่อง/ห้อง live ปัจจุบันของแพลตฟอร์มในเบราว์เซอร์"""
        import webbrowser
        url = ""
        try:
            if platform == "twitch":
                ch = (getattr(self.settings, 'twitch_channel', '') or '').strip().lstrip('@')
                if ch:
                    url = f"https://www.twitch.tv/{ch}"
            elif platform == "youtube":
                # ★ ใช้ห้อง live จริงที่ client เกาะอยู่ (resolve จาก profile แล้ว)
                #   fallback = ค่าที่ user กรอก (ถ้าเป็นลิงก์วิดีโอ)
                client = self.chat_clients.get("youtube")
                url = (getattr(client, '_video_url', '') or '').strip()
                if not url:
                    raw = (getattr(self.settings, 'youtube_url', '') or '').strip()
                    if 'watch?v=' in raw or 'youtu.be/' in raw:
                        url = raw
                    elif raw:
                        # profile handle → เปิดหน้าช่อง (ไม่รู้ห้อง live ตอนนี้)
                        handle = raw.strip().lstrip('@')
                        url = f"https://www.youtube.com/@{handle}"
            elif platform == "mylive":
                raw = (getattr(self.settings, 'mylive_url', '') or '').strip()
                if raw:
                    url = raw if raw.startswith('http') else f"https://mylive.in.th/streams/{raw}"
            elif platform == "tiktok":
                user = (getattr(self.settings, 'tiktok_username', '') or '').strip().lstrip('@')
                if user:
                    url = f"https://www.tiktok.com/@{user}/live"
            elif platform == "kick":
                ch = (getattr(self.settings, 'kick_channel', '') or
                      getattr(self.settings, 'kick_bot_username', '') or '').strip().lstrip('@')
                if ch:
                    url = f"https://kick.com/{ch}"
        except Exception as e:
            logger.debug(f"go url build error: {e}")
        if url:
            webbrowser.open(url)
            self.status_bar.set_status(f"🚀 เปิดหน้า {platform.upper()}")
        else:
            self.status_bar.set_status(f"❌ ไม่พบชื่อช่อง {platform} — กรอกในตั้งค่า → แพลตฟอร์มก่อน")

    def _on_edit_stream_info(self, platform):
        """★ เปิดหน้า edit stream info บนเว็บ"""
        import webbrowser
        if platform == "twitch":
            webbrowser.open("https://dashboard.twitch.tv/popout/stream-manager/edit-stream-info")
            self.status_bar.set_status("🔗 เปิดหน้าแก้ไขข้อมูลสตรีม Twitch")
        elif platform == "youtube":
            # ★ YouTube: Live Control Room (แก้หัวข้อ/แชท/คุมไลฟ์ ในหน้าเดียว)
            webbrowser.open("https://www.youtube.com/live/dashboard")
            self.status_bar.set_status("🔗 เปิด YouTube Live Dashboard (แก้หัวข้อ + แชทได้)")
        elif platform == "kick":
            # ★ KICK: ล็อกอินแล้ว → แก้ชื่อห้องในโปรแกรมเลย (PATCH API)
            client = self.chat_clients.get("kick")
            if not client or not getattr(client, 'can_send', False):
                # ★ ยังไม่ล็อกอิน → เปิดหน้าแก้ข้อมูลสตรีมบนเว็บ KICK ของช่องตัวเอง
                #   (ใส่ slug ของ user แต่ละคน — จากช่อง KICK ที่กรอกไว้ หรือบัญชีที่ล็อกอิน)
                slug = (getattr(self.settings, 'kick_channel', '') or
                        getattr(self.settings, 'kick_bot_username', '') or '').strip().lstrip('@')
                if not slug:
                    self.status_bar.set_status("❌ กรอกชื่อช่อง KICK ในตั้งค่า → แพลตฟอร์ม ก่อน")
                    return
                webbrowser.open(f"https://dashboard.kick.com/popout/{slug}/stream-info")
                self.status_bar.set_status(f"🔗 เปิดหน้าแก้ไขข้อมูลสตรีม KICK ({slug})")
                return
            from PySide6.QtWidgets import QInputDialog
            current = getattr(self, '_kick_stream_title', '') or ''
            title, ok = QInputDialog.getText(
                self, "แก้ไขชื่อห้อง KICK", "ชื่อห้อง (Stream Title):", text=current)
            if not ok or not title.strip():
                return
            def _bg_update():
                ok2 = client.update_stream_title(title.strip())
                self._stream_title_sig.emit(
                    "kick", title.strip() if ok2 else "__edit_failed__")
            threading.Thread(target=_bg_update, daemon=True).start()
            self.status_bar.set_status("⏳ กำลังแก้ไขชื่อห้อง KICK...")

    def _on_connect_bot_requested(self):
        """★ กดปุ่ม 'เชื่อมต่อแชทบอท' overlay → เปิด settings หน้าแพลตฟอร์ม → OAuth login"""
        self._open_platform_settings()

    # ════════════════════════════════════════════════════════════
    # ★ ASK Widget — โพล/แบบสอบถามบน Composer Overlay
    # ════════════════════════════════════════════════════════════
    def _ask_widget_exists(self) -> bool:
        """★ มี ASK widget ใน Composer layout ไหม (เปิดใช้งานอยู่)"""
        try:
            widgets = getattr(self.settings, "composer_widgets", None) or []
            return any(isinstance(w, dict) and w.get("type") == "ask"
                       and w.get("enabled", True) for w in widgets)
        except Exception:
            return False

    def _ask_require_widget(self) -> bool:
        """★ เช็คก่อนใช้ ASK — ไม่มี widget ใน Overlay → บล็อก + แจ้งวิธีแก้"""
        if self._ask_widget_exists():
            return True
        self._post_system_message(
            "⚠️ โหมด ASK จำเป็นต้องใส่ Overlay ASK ก่อนถึงจะใช้ได้ "
            "(เพิ่มได้ที่ Composer → เพิ่ม Widget → 🗳️ ASK)")
        self.status_bar.set_status("⚠️ ยังไม่มี ASK widget ใน Overlay — เพิ่มก่อนที่ Composer")
        return False

    def _toggle_ask_panel(self):
        """เปิด/ปิดแผง ASK (หน้าต่างลอยด้านขวา ใต้ TopBar)

        ★ ต้องมี ASK widget ใน Composer layout ก่อน — ไม่มี = กดไม่ได้ + แจ้งเตือน
        """
        try:
            if not self._ask_require_widget():
                return
            if self._ask_panel is None:
                from ui.widgets.ask_panel import AskPanel
                self._ask_panel = AskPanel(self)
                self._ask_panel.start_requested.connect(self._ask_start)
                self._ask_panel.end_requested.connect(self._ask_end_vote)
                self._ask_panel.close_requested.connect(self._ask_close)
                # ★ presets — ขอ/บันทึก/ลบ ผ่าน settings
                self._ask_panel.presets_load_requested.connect(self._ask_push_presets)
                self._ask_panel.preset_save_requested.connect(self._ask_save_preset)
                self._ask_panel.preset_delete_requested.connect(self._ask_delete_preset)
                self._ask_push_presets()
                # restore สถานะโพลเดิม (ถ้ามี)
                if self._ask_state:
                    self._ask_panel.inp_question.setText(self._ask_state.get("question", ""))
                    if self._ask_state.get("phase") == "voting":
                        self._ask_panel.show_voting(self._ask_payload())
                    else:
                        self._ask_panel.show_ended(self._ask_payload())
            if self._ask_panel.isVisible():
                self._ask_panel.hide()
            else:
                # ★ ข้อ 6: ชิดขวาตามขอบโปรแกรมเสมอ (resize/เต็มจอก็ตาม)
                self._ask_panel.adjustSize()
                self._ask_panel.move(
                    max(10, self.width() - self._ask_panel.width() - 16), 84)
                self._ask_panel.show()
                self._ask_panel.raise_()
            # ★ sync สีปุ่ม ASK ใน composer toolbar (เทา=ปิด / เขียว=เปิด)
            self._update_ask_panel_btn()
        except Exception as e:
            logger.error(f"_toggle_ask_panel error: {e}", exc_info=True)

    def _ask_push_presets(self):
        """ส่งรายการ preset ล่าสุดให้ panel"""
        try:
            if self._ask_panel:
                self._ask_panel.set_presets(getattr(self.settings, 'ask_presets', []) or [])
        except Exception as e:
            logger.debug(f"_ask_push_presets error: {e}")

    def _ask_save_preset(self, pr: dict):
        """บันทึก/อัปเดต preset (ชื่อซ้ำ = ทับตัวเก่า)"""
        try:
            presets = list(getattr(self.settings, 'ask_presets', []) or [])
            name = pr.get("name", "")
            presets = [p for p in presets if (p or {}).get("name") != name]
            presets.append(dict(pr))
            self.settings.ask_presets = presets
            self.settings.save_settings()
            self._ask_push_presets()
            self._post_system_message(f"💾 บันทึก Preset ASK: {name}")
        except Exception as e:
            logger.error(f"_ask_save_preset error: {e}", exc_info=True)

    def _ask_delete_preset(self, name: str):
        """ลบ preset ตามชื่อ"""
        try:
            presets = [p for p in (getattr(self.settings, 'ask_presets', []) or [])
                       if (p or {}).get("name") != name]
            self.settings.ask_presets = presets
            self.settings.save_settings()
            self._ask_push_presets()
            self._post_system_message(f"🗑 ลบ Preset ASK: {name}")
        except Exception as e:
            logger.error(f"_ask_delete_preset error: {e}", exc_info=True)

    def _update_ask_panel_btn(self):
        """★ sync สีปุ่ม ASK ใน Live Chat (หลัง A+) — เทาจาง=ยังไม่เปิด / เขียว=กำลังใช้"""
        try:
            self.chat_panel.set_ask_active(
                bool(self._ask_panel and self._ask_panel.isVisible()))
        except Exception:
            pass

    def _ask_start(self, cfg: dict):
        """เริ่มโพลใหม่ — สร้าง state + push ไป overlay

        ★ ต้องมี ASK widget อยู่ก่อน (เช็คตอนเปิดแผง — อันนี้กัน double)
        """
        try:
            if not self._ask_require_widget():
                return
            import time as _t
            self._ask_gen += 1
            gen = self._ask_gen
            n = len(cfg.get("choices", []))
            keys = []
            for i in range(n):
                keys.append(chr(ord('A') + i) if cfg.get("answer_mode") == "letters" else str(i + 1))
            duration = cfg.get("duration_sec")
            self._ask_state = {
                "question": cfg.get("question", ""),
                "choices": list(cfg.get("choices", [])),
                "keys": keys,
                "answer_mode": cfg.get("answer_mode", "letters"),
                "realtime": bool(cfg.get("realtime", True)),
                "phase": "voting",
                "duration_sec": duration,
                "end_ts": (_t.time() + duration) if duration else None,
                "results_duration_sec": cfg.get("results_duration_sec"),
                "voters": {},
                "counts": [0] * n,
                "started_ts": _t.time(),
            }
            if duration:
                QTimer.singleShot(int(duration * 1000),
                                  lambda: self._ask_end_vote_guarded(gen))
            self._ask_push()
            if self._ask_panel:
                self._ask_panel.show_voting(self._ask_payload())
            self._post_system_message(f"🗳 ASK เริ่มโหวต: {cfg.get('question','')[:60]}")
        except Exception as e:
            logger.error(f"_ask_start error: {e}", exc_info=True)

    def _ask_end_vote_guarded(self, gen: int):
        """จบโหวตจาก timer — เฉพาะถ้ายังเป็นโพลรุ่นนี้อยู่ (กัน timer เก่าปิดโพลใหม่)"""
        if (self._ask_state is not None and gen == self._ask_gen
                and self._ask_state.get("phase") == "voting"):
            self._ask_end_vote()

    def _ask_end_vote(self):
        """จบการโหวต (กดมือ หรือหมดเวลา) → เข้าสู่ช่วงแสดงสรุปผล"""
        try:
            if self._ask_state is None or self._ask_state.get("phase") != "voting":
                return
            self._ask_state["phase"] = "ended"
            self._ask_state["ended_ts"] = time.time()
            gen = self._ask_gen
            rd = self._ask_state.get("results_duration_sec")
            if rd:
                QTimer.singleShot(int(rd * 1000),
                                  lambda: self._ask_close_guarded(gen))
            self._ask_push()
            if self._ask_panel:
                self._ask_panel.show_ended(self._ask_payload())
            # ★ สรุปผลลง Live Chat เป็น system message หลายบรรทัด (เฉพาะในโปรแกรม)
            self._ask_summary_system_message()
            # ★ โพสผลสรุปลงแชททุกแพลตฟอร์มที่เชื่อมไว้ (ตาม checkbox ใน Chat Bot Setting)
            self._ask_post_result_to_chat()
        except Exception as e:
            logger.error(f"_ask_end_vote error: {e}", exc_info=True)

    def _ask_summary_system_message(self):
        """★ สรุปผลโหวตเป็น system message หลายบรรทัดใน Live Chat (แสดงเฉพาะในโปรแกรม)

        รูปแบบ: หัวข้อ + จำนวนผู้โหวต + ผลแต่ละข้อเรียงมาก→น้อย (winner สีเขียว)
        + แยกยอดตามแพลตฟอร์ม (เฉพาะแพลตฟอร์มที่มีคนโหวตจริง)
        ★ ไม่มีใครโหวต → แสดงแค่ "ไม่มีผู้โหวตในครั้งนี้"
        ★ chat row ใช้ RichText → ใช้ <br> ขึ้นบรรทัดใหม่ + <b>/<span> ตกแต่งได้
        """
        try:
            st = self._ask_state
            if st is None:
                return
            import html as _html
            total = len(st.get("voters", {}))
            if total == 0:
                self._post_system_message("📊 ไม่มีผู้โหวตในครั้งนี้")
                return
            counts = st.get("counts", [])
            keys = st.get("keys", [])
            choices = st.get("choices", [])
            order = sorted(range(len(choices)),
                           key=lambda i: -(counts[i] if i < len(counts) else 0))
            lines = []
            lines.append(f"📊 <b>สรุปผลโหวต :</b> {_html.escape(str(st.get('question', '')))}")
            lines.append(f"จำนวนผู้โหวต <b>{total}</b> คน")
            for rank, i in enumerate(order):
                k = keys[i] if i < len(keys) else "?"
                label = choices[i] if i < len(choices) else ""
                c = counts[i] if i < len(counts) else 0
                pct = round(c * 100 / total)
                row = f"[{k} - {_html.escape(str(label))}] {c} คน ({pct}%)"
                if rank == 0:
                    row = f"<span style='color:#34d399'>{row}</span>"
                lines.append(row)
            # ★ ยอดแยกตามแพลตฟอร์ม — เฉพาะแพลตฟอร์มที่มีคนโหวต ≥1 (ไม่มีสิทธิ์ = ไม่ขึ้น)
            #   แสดงโลโก้แทนชื่อ + รวมทุกแพลตฟอร์มไว้บรรทัดเดียว
            per_plat = {}
            for (plat, _author), _idx in st.get("voters", {}).items():
                per_plat[plat] = per_plat.get(plat, 0) + 1
            plat_labels = [("twitch", "Twitch"), ("youtube", "YouTube"),
                           ("mylive", "MyLive"), ("kick", "KICK"), ("tiktok", "TikTok")]
            plat_parts = []
            for p, lbl in plat_labels:
                n = per_plat.get(p, 0)
                if n <= 0:
                    continue
                icon = self._ask_platform_icon_html(p)
                plat_parts.append(f"{icon} {n} คน" if icon else f"{lbl} {n} คน")
            # แพลตฟอร์มนอกลิสต์ (กันอนาคต) — ไม่มีโลโก้ แสดงชื่อ capitalize
            for p in sorted(set(per_plat) - {pk for pk, _ in plat_labels}):
                if per_plat[p] > 0:
                    plat_parts.append(f"{str(p).capitalize()} {per_plat[p]} คน")
            if plat_parts:
                lines.append("โหวตจาก : " + "&nbsp;&nbsp;".join(plat_parts))
            self._post_system_message("<br>".join(lines))
        except Exception as e:
            logger.error(f"_ask_summary_system_message error: {e}", exc_info=True)

    def _ask_platform_icon_html(self, platform: str):
        """★ โลโก้แพลตฟอร์มเป็น <img> สำหรับ RichText system message (16px)

        คืน None ถ้าไม่มีไฟล์โลโก้ → caller ใช้ชื่อแพลตฟอร์มแทน
        ★ QLabel RichText อ่านไฟล์ผ่าน file:// URI — Path.as_uri จัด encoding ให้
        """
        try:
            import os
            from pathlib import Path
            from ui.platform_icons import _get_assets_dir, PLATFORM_FILES
            fname = PLATFORM_FILES.get(platform)
            if not fname:
                return None
            path = os.path.join(_get_assets_dir(), fname)
            if not os.path.exists(path):
                return None
            return f"<img src='{Path(path).as_uri()}' width='16' height='16'>"
        except Exception:
            return None

    def _ask_post_result_to_chat(self):
        """★ ASK จบโหวต → สรุปผลลงแชทแพลตฟอร์มที่เชื่อมอยู่ (บรรทัดเดียว — Twitch ขึ้นบรรทัดใหม่ไม่ได้)

        รูปแบบ: [ผลสรุปการโหวต] หัวข้อ : ... | จากคนโหวต N คน | ผลออกมาดังนี้ [C- เย็น 50 คน] ...
        เรียงผลจากยอดมาก → น้อย (ตรงกับหน้าสรุปผลบน Overlay)
        """
        try:
            st = self._ask_state
            if st is None or not getattr(self.settings, 'ask_post_result', True):
                return
            total = len(st.get("voters", {}))
            # ★ ไม่มีใครโหวตเลย → ไม่ต้องสรุปลงแชท (ปล่อยเฉย ๆ ไม่สแปม)
            if total == 0:
                return
            counts = st.get("counts", [])
            keys = st.get("keys", [])
            choices = st.get("choices", [])
            # เรียงมาก→น้อย (เสมอกันคงลำดับเดิม)
            order = sorted(range(len(choices)), key=lambda i: -(counts[i] if i < len(counts) else 0))
            parts = []
            for i in order:
                k = keys[i] if i < len(keys) else "?"
                label = choices[i] if i < len(choices) else ""
                c = counts[i] if i < len(counts) else 0
                parts.append(f"[{k}- {label} {c} โหวต]")
            msg = (f"[ผลสรุปการโหวต] หัวข้อ : {st.get('question', '')} "
                   f"| จาก {total} คนโหวต | ผลออกมาดังนี้ {' '.join(parts)}")
            # ★ ส่งทุกแพลตฟอร์มที่เชื่อม + ส่งได้ (OAuth) + echo ใน Live Chat เป็นชื่อบอท
            sent_any = False
            for plat, client in list(self.chat_clients.items()):
                try:
                    if client and getattr(client, 'can_send', False) and client.send_message(msg):
                        sent_any = True
                except Exception as e:
                    logger.debug(f"ask result send to {plat} failed: {e}")
            if sent_any:
                # echo เป็นชื่อบอท + จำใน _recent_own_sends (กัน IRC echo ซ้ำ/โดนอ่าน TTS)
                self._on_bot_response("twitch", msg)
                self.status_bar.set_status("📣 สรุปผลโหวตลงแชทแล้ว")
        except Exception as e:
            logger.error(f"_ask_post_result_to_chat error: {e}", exc_info=True)

    def _ask_close_guarded(self, gen: int):
        if gen == self._ask_gen:
            self._ask_close()

    def _ask_close(self):
        """ปิดผลออกจาก Overlay (กดมือ หรือครบเวลาแสดงผล)"""
        try:
            if self._ask_state is None:
                return
            self._ask_state = None
            self._ask_gen += 1  # invalidate timers เก่า
            self._ask_push()
            if self._ask_panel:
                self._ask_panel.show_idle()
        except Exception as e:
            logger.error(f"_ask_close error: {e}", exc_info=True)

    def _ask_try_vote(self, platform: str, author: str, text: str) -> bool:
        """ตรวจว่าข้อความนี้เป็นการโหวตไหม — นับเฉพาะตัวอักษร/เลขตัวเดียวจริง ๆ

        Returns True ถ้านับเป็นโหวต (→ ข้อความนี้จะไม่ถูกอ่าน TTS แต่ยังแสดงในแชท)
        """
        try:
            st = self._ask_state
            if st is None or st.get("phase") != "voting":
                return False
            t = (text or "").strip()
            if not t:
                return False
            idx = None
            for i, k in enumerate(st["keys"]):
                if t.lower() == k.lower():
                    idx = i
                    break
            if idx is None:
                return False
            voter = ((platform or "").lower(), (author or "").lower().strip())
            if not voter[1]:
                return False
            if voter in st["voters"]:
                return True  # โหวตซ้ำ = ไม่นับซ้ำ (แต่ยังถือเป็นโหวต → ไม่อ่าน TTS)
            st["voters"][voter] = idx
            st["counts"][idx] += 1
            self._ask_push()
            if self._ask_panel:
                self._ask_panel.update_live_counts(self._ask_payload())
            return True
        except Exception as e:
            logger.debug(f"_ask_try_vote error: {e}")
            return False

    def _ask_payload(self) -> dict:
        """สร้าง payload สำหรับ push ไป overlay + ใช้ใน panel สด"""
        st = self._ask_state
        if st is None:
            return {"active": False}
        # ★ ยอดโหวตแยกตามแพลตฟอร์ม (สำหรับแสดงใน panel สด)
        per_plat = {}
        for (plat, _author), _idx in st.get("voters", {}).items():
            per_plat[plat] = per_plat.get(plat, 0) + 1
        return {
            "active": True,
            "phase": st.get("phase"),
            "question": st.get("question", ""),
            "choices": st.get("choices", []),
            "keys": st.get("keys", []),
            "counts": st.get("counts", []),
            "total_voters": len(st.get("voters", {})),
            "per_platform": per_plat,
            "realtime": st.get("realtime", True),
            "end_ts": st.get("end_ts"),
            "duration_sec": st.get("duration_sec"),  # ★ ใช้คิด % หลอดเวลานับถอยหลัง
        }

    def _ask_push(self):
        """push state ล่าสุดไป composer overlay"""
        try:
            if self.composer_server is not None:
                self.composer_server.push_ask_state(self._ask_payload())
        except Exception as e:
            logger.debug(f"_ask_push error: {e}")

    def _on_tts_status_ui(self, tts_id: str, status: str, info):
        """★ อัปเดตไอคอนสถานะ TTS ริมข้อความ (main thread — รับจาก pipeline ผ่าน signal)

        status: queued | computing | ready | playing | done | skipped | error
        """
        if not tts_id:
            return
        try:
            self.chat_panel.update_tts_status(tts_id, status, info or {})
            if hasattr(self, '_popout_window') and self._popout_window:
                self._popout_window.update_tts_status(tts_id, status, info or {})
        except Exception:
            pass

    def _on_tts_check_toggled(self, checked):
        """★ checkbox "TTS" ข้างปุ่มส่ง — จำค่าล่าสุดไว้ใน settings (เปิดรอบหน้าใช้ค่าเดิม)

        คุมเฉพาะ "ข้อความที่พิมพ์ผ่านช่องนี้" — ติ๊ก = อ่าน / ไม่ติ๊ก = เงียบ
        (ข้อความบนหน้าเว็บคุมแยกที่ ตั้งค่า > TTS → read_own_web_messages
         ส่วนคำตอบ Chat Bot ไม่อ่านเด็ดขาด ไม่มีสวิตช์)
        """
        try:
            self.settings.chat_input_read_tts = bool(checked)
            self.settings.save_settings()
        except Exception as e:
            logger.debug(f"save chat_input_read_tts failed: {e}")

    def _on_chat_send(self, text: str, platforms_json: str, read_tts: bool = False):
        """★ กดส่งข้อความ → ส่งไปทุกแพลตฟอร์มที่เลือก + echo 1 ครั้ง

        Args:
            text: ข้อความที่พิมพ์
            platforms_json: JSON string ของ list แพลตฟอร์มที่เลือก
            read_tts: True = ให้ TTS อ่านข้อความนี้ด้วย (checkbox TTS ข้างปุ่มส่ง)
        """
        import json
        try:
            platforms = json.loads(platforms_json)
        except Exception:
            platforms = []
        if not platforms:
            self.status_bar.set_status("❌ เลือกแพลตฟอร์มอย่างน้อย 1 ตัว")
            return
        sent_count = 0
        for plat in platforms:
            client = self.chat_clients.get(plat)
            if not client or not getattr(client, 'can_send', False):
                continue
            try:
                if client.send_message(text):
                    sent_count += 1
            except Exception as e:
                logger.error(f"send to {plat} failed: {e}")
        if sent_count == 0:
            self.status_bar.set_status("❌ ส่งไม่ได้ — ตรวจสอบการเชื่อมต่อ")
            return
        # ★ จำข้อความที่เพิ่งส่ง (แยกเป็นรายบรรทัด — Twitch echo กลับมาทีละบรรทัด)
        #   ไว้ดัก IRC echo ตัวเองไม่ให้แสดงซ้ำ (ใช้ ~15 วิ — พอสำหรับ echo กลับ)
        try:
            import time as _t_send
            _now_send = _t_send.time()
            self._recent_own_sends = [
                (t, ts) for t, ts in self._recent_own_sends if _now_send - ts < 15
            ]
            for _line in text.split("\n"):
                _line = _line.strip()
                if _line:
                    self._recent_own_sends.append((_line, _now_send))
        except Exception:
            pass
        # ★ echo ข้อความของเราเอง 1 ครั้ง — เก็บรายชื่อแพลตฟอร์มที่ส่งทั้งหมด
        try:
            from chat_twitch import ChatMessage
            first_plat = platforms[0] if platforms else "twitch"
            # ★ กฎ: โพสในโปรแกรม = ขึ้นชื่อเราของแพลตฟอร์มนั้น + ไม่อ่าน TTS
            #   ชื่อบอท (Baitoei-Bot) สงวนไว้สำหรับข้อความที่บอทตอบเท่านั้น (_on_bot_response)
            if first_plat == "twitch":
                username = getattr(self.settings, 'twitch_bot_username', '') or 'You'
            elif first_plat == "kick":
                username = getattr(self.settings, 'kick_bot_username', '') or 'You'
            else:
                username = 'You'
            my_msg = ChatMessage(
                platform=first_plat,
                author=username,
                text=text,
                event="message",
                extra={
                    "_own_message": True,
                    "_sent_platforms": platforms,  # ★ list แพลตฟอร์มที่ส่งไป
                    "color": "#a78bfa",
                    "badges": ["broadcaster"],
                    "timestamp": time.time(),
                },
            )
            # ★ ติด id สำหรับไอคอนสถานะ TTS (ก่อน add — แถวจะได้มีป้ายสถานะ)
            try:
                import uuid as _uuid_send
                my_msg.extra["_tts_id"] = _uuid_send.uuid4().hex[:8]
                my_msg.extra["_tts_recv_ts"] = time.time()
            except Exception:
                pass
            self.chat_panel.add_message(my_msg)
            if hasattr(self, '_popout_window') and self._popout_window:
                self._popout_window.add_message(my_msg)
            # ★ checkbox TTS ติ๊ก → ส่งเข้า pipeline ให้อ่านออกเสียงด้วย
            #   (ใช้ copy ที่ถอดธง _own_message ออก — ไม่งั้นโดนดักว่าเป็นข้อความเราเอง
            #    แชร์ _tts_id เดิม → ไอคอนสถานะอัปเดตบนแถวเดิม / IRC echo ที่ย้อนมา
            #    โดนซ่อนอยู่แล้วจาก _recent_own_sends → อ่านครั้งเดียวพอดี)
            if read_tts and self.pipeline:
                try:
                    import copy as _copy_send
                    _tts_copy = _copy_send.copy(my_msg)   # ★ copy.copy (เคยพิมพ์ผิดเรียก module → ไม่อ่าน+ค้าง⏳)
                    _tts_copy.extra = dict(my_msg.extra)
                    _tts_copy.extra.pop("_own_message", None)
                    self.pipeline.enqueue(_tts_copy)
                except Exception as e:
                    logger.error(f"enqueue own message for TTS failed: {e}")
            elif not read_tts:
                self._on_tts_status_ui(
                    my_msg.extra.get("_tts_id", ""), "skipped",
                    {"reason": "ส่งผ่านโปรแกรม (ไม่ติ๊ก TTS)"},
                )
        except Exception as e:
            logger.error(f"echo own message failed: {e}", exc_info=True)
            self.status_bar.set_status(f"❌ echo error: {e}")
        plat_names = ", ".join(platforms)
        self.status_bar.set_status(f"✉️ ส่งแล้วไป {plat_names}: {text[:40]}")

    def _on_twitch_oauth_connect(self):
        """★ เริ่ม OAuth flow — เปิดเบราว์เซอร์ขอ authorize + เก็บ token

        เรียกจากปุ่มใน settings dialog (เชื่อมต่อ Twitch)
        """
        try:
            from twitch_oauth import start_oauth_flow
            self.status_bar.set_status("🔐 กำลังเปิดเบราว์เซอร์เพื่อล็อกอิน Twitch...")
            # ★ OAuth flow ใน background thread (กัน block UI — รอ user authorize)
            import threading
            def _bg_oauth():
                try:
                    result = start_oauth_flow()
                    if result and result.get("access_token"):
                        # ★ เก็บ token + username ใน settings (main thread via signal)
                        self._twitch_oauth_result_sig.emit(result)
                    else:
                        self._twitch_oauth_result_sig.emit(None)
                except Exception as e:
                    logger.error(f"OAuth flow error: {e}")
                    self._twitch_oauth_result_sig.emit(None)
            t = threading.Thread(target=_bg_oauth, daemon=True)
            t.start()
        except Exception as e:
            logger.error(f"_on_twitch_oauth_connect error: {e}")
            self.status_bar.set_status(f"❌ OAuth error: {e}")

    def _on_twitch_oauth_result(self, result):
        """★ รับผล OAuth flow (main thread) — เก็บ token + reconnect Twitch + แสดงช่องพิมพ์"""
        if not result or not result.get("access_token"):
            self.status_bar.set_status("❌ ล็อกอิน Twitch ไม่สำเร็จ (ยกเลิก หรือ error)")
            return
        # ★ เก็บ token + refresh + username + วันหมดอายุ
        self.settings.twitch_oauth_token = result["access_token"]
        self.settings.twitch_oauth_refresh = result.get("refresh_token", "")
        self.settings.twitch_bot_username = result.get("username", "")
        try:
            import time as _t
            self.settings.twitch_token_expiry_ts = _t.time() + int(result.get("expires_in", 0) or 0)
        except Exception:
            pass
        try:
            self.settings.save_settings()
        except Exception:
            pass
        username = self.settings.twitch_bot_username or "ไม่ทราบ"
        self._post_system_message(f"✅ เชื่อมต่อ Twitch สำเร็จ — ล็อกอิน: {username} (ส่งแชท + bot ได้)")
        self.status_bar.set_status(f"✅ ล็อกอิน Twitch: {username}")
        # ★ reconnect Twitch ด้วย OAuth ใหม่ (disconnect anonymous → connect OAuth)
        twitch = self.chat_clients.get("twitch")
        if twitch:
            try:
                twitch.disconnect()
                # ★ อัปเดต token ใน client ก่อน reconnect
                twitch._oauth_token = self.settings.twitch_oauth_token
                twitch._bot_username = self.settings.twitch_bot_username
                twitch._can_send = True
                twitch._refresh_token = self.settings.twitch_oauth_refresh
                # ★ reconnect
                threading.Thread(target=lambda: self._reconnect_twitch_oauth(), daemon=True).start()
            except Exception as e:
                logger.error(f"Twitch reconnect after OAuth failed: {e}")
        # ★ อัปเดตช่องพิมพ์ทันที (ซ่อน overlay → แสดงช่องพิมพ์)
        self._update_chat_send_state()
        # ★ Chat Bot — default OFF หลังเชื่อมต่อครั้งแรก
        #    และจำสถานะที่ผู้ใช้ตั้งไว้เสมอ (persist ใน settings.json — ไม่ต้องกดใหม่ทุกครั้ง)
        self.chat_panel.set_bot_enabled(getattr(self.settings, 'twitch_bot_enabled', False))
        if getattr(self.settings, 'twitch_bot_enabled', False):
            self._start_twitch_bot("twitch")
        # ★ แจ้ง settings dialog
        if hasattr(self, '_refresh_twitch_oauth_ui'):
            try: self._refresh_twitch_oauth_ui()
            except Exception: pass

    def _reconnect_twitch_oauth(self):
        """★ reconnect Twitch ด้วย OAuth token ใหม่ (background thread)

        ★ ถ้า user เพิ่งกดตัดการเชื่อมต่อระหว่างนี้ → ไม่ต่อ (กันสวนคำสั่ง —
          _connect_platform จะล้างธง manual_disconnect ทิ้ง ทำให้ปุ่มค้างแดง)
        """
        import time as _t
        _t.sleep(1)
        try:
            st = self._reconnect_state.get("twitch")
            if st and st.get('manual_disconnect'):
                logger.info("Twitch OAuth reconnect skipped — user disconnected")
                return
            target = self._get_platform_target("twitch")
            if target:
                self._connect_platform("twitch")
        except Exception as e:
            logger.error(f"Twitch reconnect failed: {e}")

    # ════════════════════════════════════════════════════════════
    # ★ KICK OAuth (ส่งแชท + Bot + แก้ชื่อห้อง)
    # ════════════════════════════════════════════════════════════

    def _on_kick_oauth_connect(self):
        """★ เริ่ม KICK OAuth flow — เปิดเบราว์เซอร์ขอ authorize + เก็บ token"""
        try:
            from kick_oauth import start_oauth_flow
            self.status_bar.set_status("🔐 กำลังเปิดเบราว์เซอร์เพื่อล็อกอิน KICK...")
            import threading
            def _bg_oauth():
                try:
                    result = start_oauth_flow()
                    self._kick_oauth_result_sig.emit(
                        result if result and result.get("access_token") else None)
                except Exception as e:
                    logger.error(f"KICK OAuth flow error: {e}")
                    self._kick_oauth_result_sig.emit(None)
            threading.Thread(target=_bg_oauth, daemon=True).start()
        except Exception as e:
            logger.error(f"_on_kick_oauth_connect error: {e}")
            self.status_bar.set_status(f"❌ KICK OAuth error: {e}")

    def _on_kick_oauth_result(self, result):
        """★ รับผล KICK OAuth (main thread) — เก็บ token + reconnect KICK"""
        if not result or not result.get("access_token"):
            self.status_bar.set_status("❌ ล็อกอิน KICK ไม่สำเร็จ (ยกเลิก หรือ error)")
            return
        self.settings.kick_oauth_token = result["access_token"]
        self.settings.kick_oauth_refresh = result.get("refresh_token", "")
        self.settings.kick_bot_username = result.get("username", "")
        self.settings.kick_user_id = int(result.get("user_id", 0) or 0)
        try:
            import time as _t
            self.settings.kick_token_expiry_ts = _t.time() + int(result.get("expires_in", 0) or 0)
        except Exception:
            pass
        try:
            self.settings.save_settings()
        except Exception:
            pass
        username = self.settings.kick_bot_username or "ไม่ทราบ"
        self._post_system_message(f"✅ เชื่อมต่อ KICK สำเร็จ — ล็อกอิน: {username} (ส่งแชท + bot + แก้ชื่อห้องได้)")
        self.status_bar.set_status(f"✅ ล็อกอิน KICK: {username}")
        # ★ reconnect KICK ด้วย token ใหม่ (อ่านยังใช้ได้อยู่ — แค่อัปเดต token ฝั่ง client)
        kick = self.chat_clients.get("kick")
        if kick:
            try:
                kick.set_oauth(
                    self.settings.kick_oauth_token,
                    self.settings.kick_user_id,
                    self.settings.kick_bot_username,
                )
                kick._refresh_token = self.settings.kick_oauth_refresh
            except Exception as e:
                logger.error(f"KICK client token update failed: {e}")
        # ★ แจ้งช่องพิมพ์ + เริ่ม bot (ถ้าเปิดอยู่)
        self._update_chat_send_state()
        if getattr(self.settings, 'twitch_bot_enabled', False):
            self._start_twitch_bot("kick")
        # ★ แจ้ง settings dialog
        if hasattr(self, '_refresh_kick_oauth_ui'):
            try: self._refresh_kick_oauth_ui()
            except Exception: pass

    def _on_kick_oauth_disconnect(self):
        """★ ลบ KICK token → กลับเป็นอ่านอย่างเดียว"""
        self.settings.kick_oauth_token = ""
        self.settings.kick_oauth_refresh = ""
        self.settings.kick_bot_username = ""
        self.settings.kick_user_id = 0
        try:
            self.settings.save_settings()
        except Exception:
            pass
        # ★ ล้าง token ใน client + หยุด bot ของ kick
        kick = self.chat_clients.get("kick")
        if kick:
            try:
                kick._oauth_token = ""
                kick._refresh_token = ""
            except Exception:
                pass
        self._stop_twitch_bot("kick")
        self._update_chat_send_state()
        self._post_system_message("⚪ ยกเลิกการเชื่อมต่อบัญชี KICK (กลับเป็นอ่านอย่างเดียว)")
        if hasattr(self, '_refresh_kick_oauth_ui'):
            try: self._refresh_kick_oauth_ui()
            except Exception: pass

    def _on_twitch_token_refreshed(self, new_token: str, new_refresh: str, expires_in: int = 0):
        """★ Twitch client refresh token สำเร็จระหว่างใช้งาน → เซฟลง settings

        (เหมือน KICK/YouTube — เดิม Twitch ไม่มีตัวนี้ → token ใหม่อยู่แค่ใน RAM
         พอ restart หรือสร้าง client ใหม่ ได้ token เก่า → วน LOGIN_UNSUCCESSFUL)
        เรียกจาก reader thread — เขียน settings ตรงๆ ได้เพราะไม่แตะ UI
        """
        try:
            self.settings.twitch_oauth_token = new_token
            if new_refresh:
                self.settings.twitch_oauth_refresh = new_refresh
            if expires_in:
                import time as _t
                self.settings.twitch_token_expiry_ts = _t.time() + int(expires_in)
            self.settings.save_settings()
            logger.info("Twitch token auto-refreshed + saved")
        except Exception as e:
            logger.debug(f"Twitch token refresh save failed: {e}")

    def _on_kick_token_refreshed(self, new_token: str, new_refresh: str):
        """★ client refresh token สำเร็จระหว่างใช้งาน → เซฟลง settings
        (เรียกจาก send thread — เขียน settings ตรงๆ ได้เพราะไม่แตะ UI)
        """
        try:
            self.settings.kick_oauth_token = new_token
            self.settings.kick_oauth_refresh = new_refresh
            import time as _t
            self.settings.kick_token_expiry_ts = _t.time() + 7200  # KICK access = 2 ชม.
            self.settings.save_settings()
            logger.info("KICK token auto-refreshed + saved")
        except Exception as e:
            logger.debug(f"KICK token refresh save failed: {e}")


    def _on_twitch_oauth_disconnect(self):
        """★ ลบ OAuth token → กลับเป็น anonymous (อ่านได้อย่างเดียว)"""
        self.settings.twitch_oauth_token = ""
        self.settings.twitch_oauth_refresh = ""
        self.settings.twitch_bot_username = ""
        self.settings.twitch_bot_enabled = False
        try:
            self.settings.save_settings()
        except Exception:
            pass
        # ★ หยุด Chat Bot (ถ้ารันอยู่)
        self._stop_twitch_bot("twitch")
        # ★ ซ่อนช่องพิมพ์ทันที (เพราะ OAuth หมดแล้ว)
        self._update_chat_send_state()
        self._post_system_message("⚪ ยกเลิกการล็อกอิน Twitch — กลับเป็น anonymous (อ่านได้อย่างเดียว)")
        self.status_bar.set_status("⚪ ยกเลิกล็อกอิน Twitch")
        # ★ แจ้ง settings dialog
        if hasattr(self, '_refresh_twitch_oauth_ui'):
            try: self._refresh_twitch_oauth_ui()
            except Exception: pass

    def _on_youtube_oauth_connect(self):
        """★ เริ่ม YouTube OAuth flow — กดปุ่มเชื่อมต่อใน settings"""
        try:
            from youtube_oauth import start_oauth_flow
            self.status_bar.set_status("🔐 กำลังเปิดเบราว์เซอร์เพื่อล็อกอิน YouTube...")
            import threading
            def _bg_oauth():
                try:
                    result = start_oauth_flow()
                    if result and result.get("access_token"):
                        self._youtube_oauth_result_sig.emit(result)
                    else:
                        self._youtube_oauth_result_sig.emit(None)
                except Exception as e:
                    logger.error(f"YouTube OAuth flow error: {e}")
                    self._youtube_oauth_result_sig.emit(None)
            t = threading.Thread(target=_bg_oauth, daemon=True)
            t.start()
        except Exception as e:
            logger.error(f"_on_youtube_oauth_connect error: {e}")
            self.status_bar.set_status(f"❌ YouTube OAuth error: {e}")

    def _on_youtube_token_refreshed(self, new_token: str):
        """★ YouTube token ถูก refresh อัตโนมัติ (เรียกจาก chat_youtube.py) → เก็บลง settings"""
        try:
            self.settings.youtube_oauth_token = new_token
            self.settings.save_settings()
            logger.info("YouTube token saved after auto-refresh")
        except Exception as e:
            logger.error(f"Save refreshed YouTube token failed: {e}")

    def _on_youtube_oauth_result(self, result):
        """★ รับผล YouTube OAuth flow (main thread) — เก็บ token"""
        if not result or not result.get("access_token"):
            self.status_bar.set_status("❌ ล็อกอิน YouTube ไม่สำเร็จ")
            return
        self.settings.youtube_oauth_token = result["access_token"]
        self.settings.youtube_oauth_refresh = result.get("refresh_token", "")
        self.settings.youtube_channel_name = result.get("channel_name", "")
        self.settings.youtube_channel_id = result.get("channel_id", "")
        try:
            self.settings.save_settings()
        except Exception:
            pass
        channel = self.settings.youtube_channel_name or "ไม่ทราบ"
        self._post_system_message(f"✅ เชื่อมต่อ YouTube สำเร็จ — ช่อง: {channel} (ส่งแชท + bot ได้)")
        self.status_bar.set_status(f"✅ ล็อกอิน YouTube: {channel}")
        if hasattr(self, '_refresh_youtube_oauth_ui'):
            try: self._refresh_youtube_oauth_ui()
            except Exception: pass

    def _on_youtube_oauth_disconnect(self):
        """★ ลบ YouTube OAuth token"""
        self.settings.youtube_oauth_token = ""
        self.settings.youtube_oauth_refresh = ""
        self.settings.youtube_channel_name = ""
        self.settings.youtube_bot_enabled = False
        try:
            self.settings.save_settings()
        except Exception:
            pass
        self._post_system_message("⚪ ยกเลิกการล็อกอิน YouTube")
        self.status_bar.set_status("⚪ ยกเลิกล็อกอิน YouTube")
        if hasattr(self, '_refresh_youtube_oauth_ui'):
            try: self._refresh_youtube_oauth_ui()
            except Exception: pass

    def _on_youtube_quota_exceeded(self):
        """★ YouTube quota หมด → mark + แจ้งเตือน"""
        try:
            from youtube_oauth import quota_tracker
            quota_tracker.mark_exceeded()
            quota_tracker.save_to_settings(self.settings)
            countdown = quota_tracker.get_reset_countdown()
            self._post_system_message(f"⚠️ YouTube quota หมดแล้ว — จะใช้ได้ในอีก {countdown}")
            self.status_bar.set_status(f"⚠️ YouTube Bot หยุดทำงาน — quota หมด (รีเซ็ตใน {countdown})")
        except Exception as e:
            logger.error(f"quota exceeded handler error: {e}")

    def _on_platform_error_signal(self, platform, error_msg):
        """รับ error จาก signal (main thread)"""
        card = self._platform_cards.get(platform)
        if card:
            card.set_connected(False)
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
        label = PLATFORM_LABELS.get(platform, platform)
        self.status_bar.set_status(f"🛑 {label} ยุติการเชื่อมต่อแล้ว")
        # ★ mark manual disconnect (หยุด auto-reconnect)
        st = self._reconnect_state.get(platform)
        if st:
            st['manual_disconnect'] = True
            st['last_attempt'] = None
            st['attempts'] = 0
        # ★ หยุด Chat Bot + ซ่อนช่องพิมพ์ + ซ่อน overlay
        self._stop_twitch_bot(platform)
        self._update_chat_send_state()
        self._update_platform_count()

    # ════════════════════════════════════════════════════════════
    # Chat feed (event-driven via signals — ไม่ต้อง poll)
    # ════════════════════════════════════════════════════════════
    def _clear_chat(self):
        """ล้าง chat feed"""
        self.chat_panel.clear_messages()
        if hasattr(self, '_popout_window') and self._popout_window:
            self._popout_window.clear_messages()

    def _block_user_from_chat(self, author_info, tts_only=False):
        """บล็อกผู้ใช้ — รองรับทั้ง context menu (string) และ author modal (tts_only param)

        ★ tts_only = ไม่อ่าน TTS แต่ยังแสดงในแชท/overlay (hide_overlay=False)
        ★ block_all = ไม่อ่าน + ไม่แสดงใน overlay (hide_overlay=True)
        ★ sync ไป pipeline filter ทันที (กัน TTS ยังอ่านอยู่)
        """
        # ★ ถ้าเรียกจาก author modal → ใช้ tts_only param โดยตรง
        if tts_only:
            author = author_info.strip() if isinstance(author_info, str) else str(author_info)
            hide_overlay = False
            msg = f"🔇 บล็อก TTS: {author}"
        elif '||tts_only' in str(author_info):
            author = str(author_info).replace('||tts_only', '').strip()
            hide_overlay = False
            msg = f"🔇 บล็อก TTS: {author}"
        else:
            author = str(author_info).strip()
            hide_overlay = True
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
        """อัปเดตยอดคนดู — chat panel + popout + viewer overlay + composer + การ์ดแพลตฟอร์ม

        ★ _viewer_counts = {platform: count} เช่น {'twitch': 50, 'youtube': 30}
        ★ ส่ง platform names ให้ composer เสมอ (แม้ count=0) → overlay แสดง platform icons
        ★ ถ้าผู้ใช้กดซ่อนยอด (chat_panel._viewers_hidden) → การ์ดแสดง "👥 --" เหมือนยอดรวม
        """
        total = sum(self._viewer_counts.values())
        # ★ อ่านสถานะซ่อนยอดจาก chat panel
        viewers_hidden = getattr(self.chat_panel, '_viewers_hidden', False)
        # ★ ส่งยอดคนดูไปการ์ดแพลตฟอร์มใน sidebar (เฉพาะที่เชื่อมต่ออยู่)
        for plat, card in self._platform_cards.items():
            try:
                count = self._viewer_counts.get(plat, 0)
                card.set_viewer_count(count, hidden=viewers_hidden)
            except Exception:
                pass
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
        """OmniVoice โหลดเสร็จ (main thread)

        ★ เดิม set rvc_status ตรงๆ เป็น "OmniVoice (เสียง)" เสมอ — ถ้ามี RVC model
        ถูกเลือกไว้อยู่แล้ว (voice_id) ป้ายจะถูกเขียนทับ ทำให้ดูเหมือน RVC ไม่ได้ใช้งาน
        ทั้งที่จริงยังใช้อยู่ (แค่ป้ายบอกผิด) → ใช้ _sync_voice_status_label() แทน ซึ่งเช็ค
        voice_id ก่อนว่ามี RVC model ที่ควรโชว์ชื่อหรือไม่
        """
        self.status_bar.set_status(f"✅ OmniVoice พร้อม")
        self._sync_voice_status_label()

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
        """Auto-check อัพเดทหลังเปิดโปรแกรม 5 วินาที

        ★ ใช้ QThread + Signal (กัน QTimer.singleShot จาก background thread ไม่ทำงาน)
        ★ ถ้ามีอัพเดท → แสดงปุ่ม "New Update" ใน topbar
        ★ user กดปุ่ม → เด้ง dialog changelog + อัพเดท
        """
        logger.info("auto_check_update: starting")
        if not getattr(sys, 'frozen', False):
            logger.info("auto_check_update: dev mode — MOCKUP show")
            return  # dev mode — no mockup
            return
        try:
            from PySide6.QtCore import QThread, Signal as QSignal

            class _UpdateCheckThread(QThread):
                result_ready = QSignal(object)  # dict / None / {"error": ...}
                def run(self):
                    try:
                        from updater import check_for_update
                        info = check_for_update()
                        self.result_ready.emit(info)
                    except RuntimeError as e:
                        self.result_ready.emit({"error": str(e)})
                    except Exception as e:
                        self.result_ready.emit({"error": str(e)})

            self._update_check_thread = _UpdateCheckThread()
            self._update_check_thread.result_ready.connect(self._on_auto_update_result)
            self._update_check_thread.start()
        except Exception as e:
            logger.error(f"auto_check_update error: {e}")

    def _on_auto_update_result(self, info):
        """slot ที่ทำงานใน main thread หลัง auto-check เสร็จ"""
        logger.info(f"auto_check_update: result = {info}")
        if info and isinstance(info, dict) and not info.get("error"):
            ver = info.get("latest", "?")
            logger.info(f"auto_check_update: showing update button for v{ver}")
            self._pending_update_info = info
            self.topbar.show_update_button(ver)

    # ═══ Announcement — ประกาศจากเจ้าของโปรแกรม (GitHub repo) ═══
    def _notify_expired_logins(self):
        """★ แจ้งเตือนใน Live Chat เมื่อล็อกอินแพลตฟอร์มหมดอายุ (ตรวจตอนเปิดโปรแกรม)

        โผล่ 5 วินาทีหลังเปิด UI — หลังการตรวจ token เสร็จแล้ว
        """
        try:
            flags = getattr(self, '_oauth_expired_flags', None) or []
            labels = {"twitch": "Twitch", "kick": "KICK"}
            for plat in flags:
                label = labels.get(plat, plat)
                self._post_system_message(
                    f"⚠️ การเชื่อมต่อ {label} หมดอายุ — กรุณาเชื่อมต่อใหม่ "
                    f"(ตั้งค่า → แพลตฟอร์ม → ล็อกอิน {label})")
                self.status_bar.set_status(f"⚠️ ล็อกอิน {label} หมดอายุ — กรุณาเชื่อมต่อใหม่")
            if flags:
                # ★ ล้าง flag — โพสต์ครั้งเดียวพอ (ไม่เตือนซ้ำระหว่างเปิดโปรแกรม)
                self._oauth_expired_flags = []
        except Exception as e:
            logger.debug(f"_notify_expired_logins error: {e}")

    def _check_announcement(self):
        """ดึงประกาศจาก GitHub (QThread + Signal pattern เดียวกับ update check)

        ★ ทำงานทั้ง dev/frozen — dev ต้องเห็นด้วยเพื่อเทส
        ★ network fail → เงียบๆ ผ่าน (ไม่รบกวน user)
        """
        if self._announce_thread is not None and self._announce_thread.isRunning():
            return
        try:
            from PySide6.QtCore import QThread, Signal as QSignal

            class _AnnounceFetchThread(QThread):
                result_ready = QSignal(object)

                def run(self):
                    try:
                        from announcement import fetch_announcement
                        self.result_ready.emit(fetch_announcement())
                    except Exception:
                        self.result_ready.emit(None)

            self._announce_thread = _AnnounceFetchThread()
            self._announce_thread.result_ready.connect(self._on_announcement_result)
            self._announce_thread.start()
        except Exception as e:
            logger.debug(f"_check_announcement error: {e}")

    def _on_announcement_result(self, ann):
        """slot: ได้ประกาศจาก background → แสดงแถบ (ถ้าไม่ใช่อันที่ user เคยปิด)"""
        if not ann:
            # ไม่มีประกาศ / ถูกลบแล้ว → ซ่อนแถบ (กันอันเก่าค้าง)
            self.announce_bar.hide_bar()
            return
        dismissed_id = getattr(self.settings, 'announce_dismissed_id', '')
        if dismissed_id and ann.get('id') == dismissed_id:
            return  # user เคยปิดอันนี้แล้ว — ไม่เด้งซ้ำ
        self.announce_bar.show_announcement(ann)
        # ★ รายงาน "seen" ให้เจ้าของ (background — ไม่ block UI, fail = ผ่านเงียบๆ)
        ann_id = ann.get('id', '')
        threading.Thread(
            target=lambda: __import__('announcement').report_announcement_hit(ann_id, 'seen'),
            daemon=True,
        ).start()

    def _on_announcement_dismissed(self, ann_id: str):
        """user กด X ปิดประกาศ → จำ id ไว้ (จนกว่าจะมีประกาศใหม่ id ใหม่)
        + รายงาน "dismiss" ให้เจ้าของ"""
        try:
            self.settings.announce_dismissed_id = ann_id
            from settings import save_settings
            save_settings(self.settings)
        except Exception as e:
            logger.debug(f"save dismissed id failed: {e}")
        try:
            threading.Thread(
                target=lambda: __import__('announcement').report_announcement_hit(ann_id, 'dismiss'),
                daemon=True,
            ).start()
        except Exception:
            pass

    # ════════════════════════════════════════════════════════════
    # ★ OBS launch — เปิด OBS หรือดึงหน้าต่าง OBS ขึ้นมา
    # ════════════════════════════════════════════════════════════

    def _on_obs_launch(self):
        """★ กดปุ่ม เปิด OBS → สั่งเปิด OBS จาก path มาตรฐาน

        OBS มี single-instance ของตัวเอง → ถ้ารันอยู่แล้ว OBS จะขึ้น dialog เอง
        เราไม่ต้องตรวจสอบหรือจัดการอะไร
        """
        try:
            from obs_launcher import launch_obs
            ok, message = launch_obs()
            icon = "🎬" if ok else "❌"
            self.status_bar.set_status(f"{icon} {message}")
        except Exception as e:
            logger.error(f"OBS launch failed: {e}", exc_info=True)
            self.status_bar.set_status(f"❌ เปิด OBS ไม่ได้: {e}")

    def _poll_stream_titles(self):
        """★ ดึง title ของ live stream — ทำใน background thread + emit signal"""
        import threading
        def _bg():
            for platform, client in list(self.chat_clients.items()):
                if not client or not getattr(client, 'is_connected', False):
                    continue
                try:
                    title = self._fetch_stream_title(platform, client)
                    self._stream_title_sig.emit(platform, title or "")
                except Exception as e:
                    logger.debug(f"stream title {platform} error: {e}")
        threading.Thread(target=_bg, daemon=True).start()

    def _on_refresh_stream_title(self, platform: str):
        """★ กดปุ่ม 🔄 refresh ในการ์ดแพลตฟอร์ม → ดึง title ใหม่เฉพาะ platform นั้น (ไม่ auto)"""
        client = self.chat_clients.get(platform)
        if not client or not getattr(client, 'is_connected', False):
            self.status_bar.set_status(f"📖 {PLATFORM_LABELS.get(platform, platform)}: ยังไม่เชื่อมต่อ — ดึง Title ไม่ได้")
            return
        self.status_bar.set_status(f"📖 กำลังดึง Title ของ {PLATFORM_LABELS.get(platform, platform)}...")
        import threading
        def _bg():
            try:
                title = self._fetch_stream_title(platform, client)
                self._stream_title_sig.emit(platform, title or "")
            except Exception as e:
                logger.debug(f"refresh stream title {platform} error: {e}")
                self._stream_title_sig.emit(platform, "")
        threading.Thread(target=_bg, daemon=True).start()

    def _on_stream_title(self, platform: str, title: str):
        """★ รับ title จาก background thread → update card (main thread)"""
        card = self._platform_cards.get(platform)
        if not card:
            return
        # ★ แก้ชื่อห้อง KICK ไม่สำเร็จ → แจ้งเตือน
        if title == "__edit_failed__":
            self.status_bar.set_status("❌ แก้ไขชื่อห้อง KICK ไม่สำเร็จ")
            return
        # ★ ถ้าเป็น start time signal → ตั้ง uptime
        if title.startswith("__start_time__:"):
            start_time = title.replace("__start_time__:", "")
            if hasattr(card, 'set_stream_start_time'):
                card.set_stream_start_time(start_time)
        else:
            # ★ cache ชื่อห้องล่าสุด (ใช้เป็นค่าเริ่มต้นใน dialog แก้ชื่อห้อง)
            if platform == "kick":
                self._kick_stream_title = title
            if hasattr(card, 'set_stream_title'):
                card.set_stream_title(title)

    def _fetch_stream_title(self, platform: str, client) -> str:
        """★ ดึง title ของ live stream จาก client (แต่ละแพลตฟอร์มดึงต่างกัน)"""
        try:
            if platform == "twitch":
                # ★ Twitch: ดึง title จาก broadcastSettings (มีเสมอ แม้ไม่ได้ live)
                #   + ถ้า live อยู่ → ดึง createdAt สำหรับ uptime
                import requests
                channel = getattr(self.settings, 'twitch_channel', '') or ''
                if not channel:
                    return ""
                query = (
                    '{ user(login: "%s") { '
                    'broadcastSettings { title } '
                    'stream { title createdAt } '
                    '} }' % channel
                )
                resp = requests.post(
                    "https://gql.twitch.tv/gql",
                    json={"query": query},
                    headers={"Client-ID": "kimne78kx3ncx6brgo4mv6wki5h1ko"},
                    timeout=10,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    user = data.get("data", {}).get("user", {})
                    # ★ title: ถ้า live → ใช้ stream.title, ถ้าไม่ live → ใช้ broadcastSettings.title
                    stream = user.get("stream")
                    if stream:
                        title = stream.get("title") or user.get("broadcastSettings", {}).get("title", "")
                        created = stream.get("createdAt", "")
                        if created:
                            self._stream_title_sig.emit(platform, "__start_time__:" + created)
                    else:
                        title = user.get("broadcastSettings", {}).get("title", "")
                    return title or ""
                return ""

            elif platform == "youtube":
                # ★ YouTube: ใช้ InnerTube API
                import requests
                video_id = getattr(client, '_video_id', '') or ''
                if not video_id:
                    return ""
                url = "https://www.youtube.com/youtubei/v1/next"
                payload = {
                    "context": {"client": {"clientName": "WEB", "clientVersion": "2.20240101.00.00"}},
                    "videoId": video_id,
                }
                resp = requests.post(url, json=payload, timeout=10)
                if resp.status_code == 200:
                    import json, re
                    text = resp.text
                    # หา title
                    m = re.search(r'"title":"([^"]{3,200})"', text)
                    if m:
                        return m.group(1).replace("\\u0026", "&").replace("\\\"", "\"")
                return ""

            elif platform == "mylive":
                # ★ MyLive: ดึงจาก client ถ้ามี
                return getattr(client, '_stream_title', '') or ''

            elif platform == "kick":
                # ★ KICK: ดึงจาก API
                import requests
                channel = getattr(self.settings, 'kick_channel', '') or ''
                if not channel:
                    return ""
                resp = requests.get(f"https://kick.com/api/v2/channels/{channel}",
                                   headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("lazy_properties", {}).get("livestream", {}).get("session_title", "") or ""
                return ""

        except Exception as e:
            logger.debug(f"fetch title {platform}: {e}")
        return ""

    def _poll_obs_status(self):
        """★ Poll สถานะ OBS ทุก 3 วิ — เปลี่ยนข้อความ/สีปุ่ม OBS

        ★ tasklist + EnumWindows กิน 100-500ms → ห้ามรันบน UI thread
          (เคยทำให้ UI ค้างเป็นจังหวะทุก 3 วิ — คลิกช่องกรอกแล้วติดเสี้ยววิ)
          → รันใน background thread แล้ว marshal กลับ main ผ่าน Signal
        ★ กันซ้อน: ถ้ารอบก่อนยังรันอยู่ → ข้ามรอบนี้
        """
        if getattr(self, '_obs_poll_busy', False):
            return
        self._obs_poll_busy = True

        def _bg():
            try:
                from obs_launcher import _find_obs_window
                hwnd = _find_obs_window()
                running = hwnd is not None
            except Exception:
                running = False
            finally:
                self._obs_poll_busy = False
            self._obs_status_sig.emit(running)

        threading.Thread(target=_bg, name="OBSPoll", daemon=True).start()

    def _on_obs_status_result(self, running: bool):
        """slot (main thread): อัปเดตปุ่ม OBS เฉพาะเมื่อสถานะเปลี่ยน"""
        if running != self._obs_running_state:
            self._obs_running_state = running
            self.topbar.set_obs_running(running)

    # ════════════════════════════════════════════════════════════
    # ★ Update dialog + download + apply_patch + restart
    # ════════════════════════════════════════════════════════════

    def _on_update_button_clicked(self):
        """★ กดปุ่ม New Update ใน topbar → เด้ง dialog changelog + อัพเดท"""
        info = getattr(self, '_pending_update_info', None)
        if info:
            self.topbar.hide_update_button()
            self._show_update_dialog(info)

    def _show_update_dialog(self, info: dict):
        """เด้ง dialog บอกมีอัพเดทใหม่ — ถามจะอัพเดทเลยหรือภายหลัง

        info = {"current", "latest", "changelog", "type", "url", "build_type"}
        """
        if getattr(self, '_update_in_progress', False):
            return
        if getattr(self, '_update_dialog_shown', False):
            return
        self._update_dialog_shown = True

        from PySide6.QtWidgets import (
            QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout,
            QTextEdit, QProgressBar, QFrame,
        )

        current = info.get("current", "?")
        latest = info.get("latest", "?")
        changelog = info.get("changelog", "")
        url = info.get("url", "")
        update_type = info.get("type", "major")
        bt = info.get("build_type", "")
        bt_label = "Lite" if bt == "lite" else "Full"

        dlg = QDialog(self)
        dlg.setWindowTitle("🆕 มีอัพเดทใหม่ — Broadcast Playroom")
        dlg.setModal(True)
        dlg.setMinimumWidth(480)
        # ★ อยู่บนสุดเสมอ + อยู่กึ่งกลางจอ (กันถูกบัง)
        dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowStaysOnTopHint)
        dlg.setStyleSheet("""
            QDialog { background-color: #0f172a; color: #e2e8f0; }
            QLabel { color: #e2e8f0; }
            QLabel[role="title"] { font-size: 18px; font-weight: 700; color: #10b981; }
            QLabel[role="version"] { font-size: 13px; color: #94a3b8; }
            QLabel[role="badge-patch"] { background: #10b981; color: #fff; padding: 4px 12px; border-radius: 4px; font-weight: 700; font-size: 12px; }
            QLabel[role="badge-major"] { background: #ef4444; color: #fff; padding: 4px 12px; border-radius: 4px; font-weight: 700; font-size: 12px; }
            QTextEdit { background: #1e293b; border: 1px solid #334155; border-radius: 6px; padding: 8px; color: #d1d5db; font-size: 12px; }
            QPushButton#Primary { background: #10b981; color: white; font-weight: 700; border: none; border-radius: 6px; padding: 10px 20px; }
            QPushButton#Primary:hover { background: #059669; }
            QPushButton#Primary:disabled { background: #334155; color: #64748b; }
            QPushButton#Secondary { background: #334155; color: #e2e8f0; font-weight: 600; border: none; border-radius: 6px; padding: 10px 20px; }
            QPushButton#Secondary:hover { background: #475569; }
            QProgressBar { background: #1e293b; border: 1px solid #334155; border-radius: 4px; text-align: center; color: #e2e8f0; }
            QProgressBar::chunk { background: #10b981; border-radius: 3px; }
        """)

        layout = QVBoxLayout(dlg)
        layout.setSpacing(10)
        layout.setContentsMargins(24, 20, 24, 20)

        # ── title ──
        title = QLabel("🆕 เวอร์ชั่นใหม่พร้อมใช้งาน!")
        title.setProperty("role", "title")
        layout.addWidget(title)

        # ── version row ──
        ver_row = QHBoxLayout()
        ver_lbl = QLabel(f"เวอร์ชั่นปัจจุบัน: <b>v{current}</b> ({bt_label}) → เวอร์ชั่นล่าสุด: <b>v{latest}</b>")
        ver_lbl.setProperty("role", "version")
        ver_lbl.setTextFormat(Qt.RichText)
        ver_row.addWidget(ver_lbl)
        ver_row.addStretch()
        layout.addLayout(ver_row)

        # ── type badge + size ──
        is_patch = (update_type == "patch")
        badge = QLabel(f"📦 Patch" if is_patch else "⚠️ Major")
        badge.setProperty("role", "badge-patch" if is_patch else "badge-major")
        layout.addWidget(badge)

        if is_patch:
            size_hint = QLabel("★ อัพเดทแบบ Patch — โหลดเร็ว ไม่ต้องโหลดใหม่ทั้งโปรแกรม")
            size_hint.setStyleSheet("font-size: 12px; color: #10b981;")
        else:
            size_hint = QLabel("★ อัพเดทใหญ่ — จะเปิดเบราว์เซอร์ให้ดาวน์โหลดไฟล์ใหม่")
            size_hint.setStyleSheet("font-size: 12px; color: #f59e0b;")
        size_hint.setWordWrap(True)
        layout.addWidget(size_hint)

        # ── changelog ──
        if changelog:
            cl_label = QLabel("📝 มีอะไรใหม่:")
            cl_label.setStyleSheet("font-size: 13px; font-weight: 600; color: #f59e0b; margin-top: 4px;")
            layout.addWidget(cl_label)
            cl_text = QTextEdit()
            cl_text.setReadOnly(True)
            cl_text.setPlainText(changelog)
            cl_text.setMaximumHeight(140)
            layout.addWidget(cl_text)

        # ── progress (hidden ตอนแรก) ──
        progress = QProgressBar()
        progress.setVisible(False)
        progress.setTextVisible(True)
        layout.addWidget(progress)

        progress_lbl = QLabel("")
        progress_lbl.setStyleSheet("font-size: 12px; color: #06b6d4;")
        progress_lbl.setAlignment(Qt.AlignCenter)
        progress_lbl.setVisible(False)
        layout.addWidget(progress_lbl)

        # ── buttons ──
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_later = QPushButton("ภายหลัง")
        btn_later.setObjectName("Secondary")
        btn_later.clicked.connect(dlg.reject)
        btn_row.addWidget(btn_later)

        btn_update = QPushButton("อัพเดทตอนนี้" if is_patch else "ดาวน์โหลด")
        btn_update.setObjectName("Primary")
        btn_row.addWidget(btn_update)
        layout.addLayout(btn_row)

        # ★ wire update action
        def _do_update():
            if is_patch and url:
                # ★ patch → auto-download + apply_patch + restart
                #   sha256 จาก manifest (ถ้ามี) → download_file ตรวจความถูกต้องของ zip
                sha256 = (info or {}).get("sha256") or ""
                self._start_patch_update(url, dlg, btn_update, btn_later, progress, progress_lbl, sha256)
            else:
                # ★ major → เปิด browser
                from updater import open_url
                target = url or "https://github.com/zepiam/broadcast-playroom-ex/releases/latest"
                open_url(target)
                dlg.accept()

        btn_update.clicked.connect(_do_update)

        # ★ จัดกึ่งกลางจอ + โชว์เด่นๆ
        from PySide6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().geometry()
        dlg.move((screen.width() - dlg.width()) // 2, (screen.height() - dlg.height()) // 2)
        dlg.raise_()
        dlg.activateWindow()
        dlg.exec()

    def _start_patch_update(self, url, dlg, btn_update, btn_later, progress, progress_lbl, sha256=""):
        """เริ่มดาวน์โหลด patch + apply_patch — แสดง progress

        ★ ใช้ QThread + Signal (กัน QTimer.singleShot จาก background thread ไม่ทำงาน)
        ★ sha256 จาก version.json → ตรวจ zip หลังโหลด (ไม่ตรง = ปฏิเสธ)
        """
        from PySide6.QtCore import QThread, Signal as QSignal

        self._update_in_progress = True
        btn_update.setEnabled(False)
        btn_update.setText("⏳ กำลังดาวน์โหลด...")
        btn_later.setEnabled(False)
        progress.setVisible(True)
        progress_lbl.setVisible(True)
        progress.setValue(0)

        class _DownloadThread(QThread):
            progress_sig = QSignal(int, int)  # downloaded, total
            done_sig = QSignal(bool, str)     # success, message

            def __init__(self, url, sha256=""):
                super().__init__()
                self.url = url
                self.sha256 = sha256

            def run(self):
                try:
                    from updater import download_file, apply_patch
                    import os, sys

                    install_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
                    temp_zip = os.path.join(install_dir, ".update_patch.zip")

                    ok = download_file(self.url, temp_zip,
                                       progress_cb=lambda d, t: self.progress_sig.emit(d, t),
                                       expected_sha256=self.sha256 or None)
                    if not ok:
                        self.done_sig.emit(False, "ดาวน์โหลดไม่สำเร็จ — ตรวจสอบอินเทอร์เน็ต\n(หรือไฟล์ไม่ผ่านการตรวจสอบความถูกต้อง)")
                        return

                    ok = apply_patch(temp_zip)
                    if ok:
                        self.done_sig.emit(True, "กำลังติดตั้งและรีสตาร์ท...")
                    else:
                        self.done_sig.emit(False, "ไม่สามารถติดตั้งอัพเดทได้")
                except Exception as e:
                    self.done_sig.emit(False, f"เกิดข้อผิดพลาด: {e}")

        # ★ สร้าง thread + connect signals (cross-thread → main thread)
        self._update_dl_thread = _DownloadThread(url, sha256)

        def _on_progress(downloaded, total):
            if total > 0:
                pct = int(downloaded * 100 / total)
                progress.setValue(pct)
                mb_done = downloaded / 1024 / 1024
                mb_total = total / 1024 / 1024
                progress_lbl.setText(f"⏳ {pct}% ({mb_done:.1f}/{mb_total:.1f} MB)")
            else:
                progress_lbl.setText(f"⏳ กำลังดาวน์โหลด... ({downloaded/1024/1024:.1f} MB)")

        def _on_done(success, message):
            if success:
                progress.setValue(100)
                progress_lbl.setText("✅ ติดตั้งเสร็จ — กำลังรีสตาร์ท...")
                progress_lbl.setStyleSheet("font-size: 12px; color: #10b981;")
                self.status_bar.set_status("🔄 กำลังอัพเดท — โปรแกรมจะรีสตาร์ท...")
                dlg.accept()
                QTimer.singleShot(500, self._close_for_update)
            else:
                progress_lbl.setText(f"❌ {message}")
                progress_lbl.setStyleSheet("font-size: 12px; color: #ef4444;")
                btn_update.setEnabled(True)
                btn_update.setText("อัพเดทตอนนี้")
                btn_later.setEnabled(True)
                self._update_in_progress = False

        self._update_dl_thread.progress_sig.connect(_on_progress)
        self._update_dl_thread.done_sig.connect(_on_done)
        self._update_dl_thread.start()

    def _close_for_update(self):
        """ปิดโปรแกรม — batch (.update.bat) จะรอจน exe ปิด แล้ว xcopy + restart"""
        logger.info("Closing for update — batch will restart")
        self.close()

    def _load_supporters(self):
        """★ ดึงรายชื่อผู้สนับสนุนจาก men9ch.com API (QThread + Signal)

        ★ เก็บ cache ใน self._supporters_cache
        ★ ถ้า settings dialog เปิดอยู่ → update list ทันที
        ★ ถ้าปิด → เก็บไว้แสดงตอนเปิด dialog ครั้งต่อไป
        """
        # ★ ใช้ QThread + Signal (กัน QTimer.singleShot จาก background thread ไม่ทำงาน)
        from PySide6.QtCore import QThread, Signal

        class _FetchThread(QThread):
            fetched = Signal(dict)
            def run(self):
                try:
                    from supporters_api import fetch_supporters
                    result = fetch_supporters()
                except Exception as e:
                    result = {"ok": False, "error": str(e)}
                self.fetched.emit(result)

        # ★ เก็บ ref กัน garbage collect
        self._supporters_fetch_thread = _FetchThread()
        self._supporters_fetch_thread.fetched.connect(self._on_supporters_loaded)
        self._supporters_fetch_thread.start()

    def _on_supporters_loaded(self, result: dict):
        """★ slot ที่ทำงานใน main thread หลัง fetch เสร็จ"""
        self._supporters_cache = result

        # ★ ถ้า settings dialog เปิดอยู่ → update list (ผ่าน _on_supporters_fetched เพื่อ unlock ปุ่มด้วย)
        dlg = getattr(self, '_settings_dialog', None)
        if dlg is not None:
            # ★ ถ้า dialog มี method _on_supporters_fetched → เรียก (จะ unlock ปุ่ม + populate)
            if hasattr(dlg, '_on_supporters_fetched'):
                dlg._on_supporters_fetched(result)
            elif hasattr(dlg, '_populate_supporters_list'):
                # fallback: populate โดยตรง (กรณี dialog เก่า)
                dlg._populate_supporters_list(result)

    def _open_settings_supporters(self):
        """เปิด Settings ไปที่หน้าสนับสนุน"""
        self._open_settings_at_section("supporters")

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
            # ★ save ทันที (กันไม่ยอมเซฟค่า volume)
            from settings import save_settings
            save_settings(self.settings)
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
        self._setup_twitch_oauth_in_dialog(dlg)
        dlg.settings_changed.connect(self._on_settings_changed)
        dlg.exec()
        self._settings_dialog = None

    def _setup_twitch_oauth_in_dialog(self, dlg):
        """★ ตั้งค่า OAuth handlers ใน settings dialog (Twitch / YouTube / KICK)

        ★ แต่ละแพลตฟอร์มแยก try กันเอง — YouTube ถูกปิดไปแล้ว (ไม่มี UI)
          ห้ามให้พังทั้งฟังก์ชัน ไม่งั้น KICK จะไม่มี handler ติดตั้ง
        """
        # ★ Twitch
        try:
            dlg.setup_twitch_oauth_handlers(
                connect_handler=self._on_twitch_oauth_connect,
                disconnect_handler=self._on_twitch_oauth_disconnect,
                refresh_callback=dlg._refresh_twitch_oauth_status,
            )
            self._refresh_twitch_oauth_ui = dlg._refresh_twitch_oauth_status
            dlg._refresh_twitch_oauth_status()
        except Exception as e:
            logger.debug(f"setup twitch oauth dialog error: {e}")
        # ★ YouTube (feature ปิดอยู่ — ติดตั้งเมื่อ UI กลับมา)
        try:
            if hasattr(dlg, 'setup_youtube_oauth_handlers'):
                dlg.setup_youtube_oauth_handlers(
                    connect_handler=self._on_youtube_oauth_connect,
                    disconnect_handler=self._on_youtube_oauth_disconnect,
                    refresh_callback=dlg._refresh_youtube_oauth_status,
                )
                self._refresh_youtube_oauth_ui = dlg._refresh_youtube_oauth_status
                dlg._refresh_youtube_oauth_status()
        except Exception as e:
            logger.debug(f"setup youtube oauth dialog error: {e}")
        # ★ KICK
        try:
            dlg.setup_kick_oauth_handlers(
                connect_handler=self._on_kick_oauth_connect,
                disconnect_handler=self._on_kick_oauth_disconnect,
                refresh_callback=dlg._refresh_kick_oauth_status,
            )
            self._refresh_kick_oauth_ui = dlg._refresh_kick_oauth_status
            dlg._refresh_kick_oauth_status()
        except Exception as e:
            logger.debug(f"setup kick oauth dialog error: {e}")

    def _open_platform_settings(self):
        """เปิด Settings ไปที่แท็บแพลตฟอร์ม"""
        from ui.dialogs.settings import SettingsDialog
        dlg = SettingsDialog(self)
        self._settings_dialog = dlg
        self._setup_twitch_oauth_in_dialog(dlg)
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
        # ★ sync per-platform bot toggles (เปิด/ปิด Bot เฉพาะแพลตฟอร์ม)
        if self.settings:
            _bp = getattr(self.settings, 'bot_platforms', {}) or {}
            for _plat in ("twitch", "youtube", "kick"):
                if _plat not in self.chat_clients:
                    continue
                if _bp.get(_plat, True):
                    if getattr(self.settings, 'twitch_bot_enabled', False):
                        self._start_twitch_bot(_plat)
                else:
                    self._stop_twitch_bot(_plat)
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
        # ★ rebuild platform cards (เผื่อ user เปิด/ปิดการแสดงแพลตฟอร์ม)
        self._rebuild_platform_cards()
        # ★ sync mic watcher (ถ้ามี avatar widget แบบ mic mode → เริ่มวัด)
        self._sync_avatar_mic_watcher()
        self._sync_donate_goal_watcher()
        # ★ sync Twitch Bot config (commands/timers/enabled เปลี่ยน)
        self._update_twitch_bot_config()
        # ★ sync chat send state (OAuth token/username เปลี่ยน → chip ต้องอัปเดต)
        self._update_chat_send_state()
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
        """resize overlay ตาม chat panel + re-position floating events button + ASK panel ชิดขวา"""
        super().resizeEvent(event)
        if hasattr(self, '_popout_overlay') and self._popout_overlay and self._popout_overlay.isVisible():
            self._popout_overlay.setGeometry(self.chat_panel.rect())
        # ★ re-position floating "‹" button (ตอน events panel ซ่อน)
        if hasattr(self, '_events_show_btn'):
            self._position_events_show_btn()
        # ★ ASK panel — ตามชิดขวาเสมอ (ไม่ค้างกลางจอเวลา maximize/resize)
        #   เดิม logic นี้อยู่ resizeEvent อีกอันที่ถูก override โดยอันนี้ (Python ใช้ method ท้ายสุด)
        try:
            if getattr(self, '_ask_panel', None) and self._ask_panel.isVisible():
                self._ask_panel.move(
                    max(10, self.width() - self._ask_panel.width() - 16),
                    min(self._ask_panel.y(), max(84, self.height() - 100)))
        except Exception:
            pass

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
        port = (self.composer_server.port if (self.composer_server and hasattr(self.composer_server, 'port')) else int(getattr(self.settings, 'composer_port', 8801)))
        url = f"http://localhost:{port}/editor"
        webbrowser.open(url)

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
        """toggle TTS อ่านแชท — on=True เปิด, on=False ปิด (mute)

        ★ เมื่อปิด → หยุดเสียงทันที + ล้างคิวทั้งหมด
        ★ เมื่อเปิด → คิว reset รอคำสั่งใหม่เท่านั้น
        """
        if self.pipeline:
            self.pipeline.config.tts_muted = not on
            if not on:
                # ★ ปิด → หยุดเสียงที่กำลังเล่น + ล้างคิวทั้งหมดทันที
                try:
                    self.pipeline.clear_queues()
                except Exception as e:
                    logger.debug(f"clear_queues on TTS off: {e}")
        if self.settings:
            self.settings.tts_muted = not on
        # ★ sync ไอคอนลำโพงในการ์ดแพลตฟอร์มทุกใบให้ตรงกับ master mute — ปิด "อ่านแชท"
        #   ต้องบังคับทุกการ์ดเป็น mute + กดปรับทีละแพลตฟอร์มไม่ได้ จนกว่าจะเปิดกลับ
        for card in self._platform_cards.values():
            try:
                card.set_master_muted(not on)
            except Exception as e:
                logger.debug(f"set_master_muted error: {e}")
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
        # ★ restore sidebar master volume/rate/pitch sliders
        master_vol = getattr(self.settings, 'volume', 100)
        self.sidebar.vol_slider.setValue(master_vol)
        self.sidebar.vol_val_label.setText(f"{master_vol}")
        rate_val = getattr(self.settings, 'rate', 0)
        if hasattr(self.sidebar, 'rate_slider'):
            self.sidebar.rate_slider.setValue(rate_val)
            if hasattr(self.sidebar, 'rate_val_label'):
                self.sidebar.rate_val_label.setText(f"{rate_val:+d}%")
        pitch_val = getattr(self.settings, 'rvc_pitch', 0)
        if hasattr(self.sidebar, 'pitch_slider'):
            self.sidebar.pitch_slider.setValue(pitch_val)
            if hasattr(self.sidebar, 'pitch_val_label'):
                self.sidebar.pitch_val_label.setText(f"{pitch_val:+d}")
        # translate mode — ★ sync topbar + pipeline config ให้ตรงกับ settings
        multilang = getattr(self.settings, 'multilang_enabled', False)
        translate = getattr(self.settings, 'auto_translate_enabled', False)
        if multilang and translate:
            # ★ ถ้าเปิดทั้งคู่ → priority ให้ multilang (ปิด translate)
            translate = False
            self.settings.auto_translate_enabled = False
        if multilang:
            self.topbar.set_translate_mode("multilang")
            logger.info(f"restore: translate mode = multilang")
        elif translate:
            self.topbar.set_translate_mode("translate")
            logger.info(f"restore: translate mode = translate")
        else:
            self.topbar.set_translate_mode("off")
            logger.info(f"restore: translate mode = off")
        # ★ sync pipeline config ทันที
        if self.pipeline:
            self.pipeline.config.multilang_enabled = multilang
            self.pipeline.config.auto_translate_enabled = translate

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
        """เปิด Composer editor ใน browser (ไม่ toggle server — server เปิดอยู่เสมอ)

        ★ ถ้ายังไม่ได้เชื่อม OBS WebSocket → เด้ง modal แนะนำก่อน (ไม่บังคับ)
        """
        try:
            # ★ ยังไม่ได้เชื่อม WS → แนะนำก่อนเปิด Composer
            if not getattr(self.settings, 'obs_ws_enabled', False):
                action = self._show_ws_recommend_modal()
                if action == "settings":
                    self._open_settings_to("obs_ws")
                    return
                elif action == "guide":
                    import webbrowser
                    webbrowser.open("https://men9ch.com/broadcastplayroom-websocket-setting/")
                    return
                elif action == "close":
                    return  # ★ ปิด modal ด้วย X/Escape → ปิดเฉย ๆ ไม่เปิด composer
                # action == "ignore" → เปิด Composer ตามเดิม
            port = (self.composer_server.port if (self.composer_server and hasattr(self.composer_server, 'port')) else int(getattr(self.settings, 'composer_port', 8801)))
            url = f"http://localhost:{port}/editor"
            import webbrowser
            webbrowser.open(url)
            self.status_bar.set_status(f"🎨 เปิด Composer Editor: {url}")
        except Exception as e:
            self.status_bar.set_status(f"❌ เปิด Composer ไม่ได้: {e}")

    def _show_ws_recommend_modal(self) -> str:
        """★ Modal แนะนำเชื่อม OBS WebSocket (ไม่บังคับ — มีปุ่ม "ไม่สนใจ")

        ★ ใช้ QDialog เอง (ไม่ใช่ QMessageBox) เพราะ QMessageBox จัดปุ่มตาม role
          ไม่ยอมฟังลำดับ — ใช้ QDialog คุม layout เองได้ 100%

        Returns: "settings" | "guide" | "ignore"
        """
        from PySide6.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
        )
        from PySide6.QtCore import Qt

        dlg = QDialog(self)
        dlg.setWindowTitle("แนะนำเชื่อมต่อ OBS WebSocket")
        dlg.setFixedWidth(360)
        dlg.setStyleSheet("""
            QDialog { background: #131726; }
            QLabel { color: #e2e8f0; background: transparent; border: none; }
        """)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)

        # ── Title ──
        title_lbl = QLabel("ยังไม่ได้เชื่อมต่อ WebSocket")
        title_lbl.setAlignment(Qt.AlignCenter)
        title_lbl.setWordWrap(True)
        from PySide6.QtWidgets import QSizePolicy
        title_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        title_lbl.setStyleSheet(
            "font-size: 17px; font-weight: 700; color: #f59e0b;"
            "background: transparent; border: none;")
        layout.addWidget(title_lbl)

        # ── Message ──
        msg_lbl = QLabel(
            "แนะนำให้เชื่อมต่อ เพื่อทำให้ Overlay แสดงผลขึ้นบนจอ OBS อย่างรวดเร็วยิ่งขึ้น"
        )
        msg_lbl.setWordWrap(True)
        msg_lbl.setAlignment(Qt.AlignCenter)
        msg_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        msg_lbl.setStyleSheet(
            "font-size: 14px; color: #94a3b8; background: transparent; border: none;"
            "line-height: 1.5;")
        layout.addWidget(msg_lbl)

        # ── ปุ่ม 3 อัน (จัดกลาง — แถวเดียว compact) ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        btn_row.addStretch(1)

        result = {"action": "ignore"}

        btn_connect = QPushButton("เชื่อม WebSocket")
        btn_connect.setCursor(Qt.PointingHandCursor)
        btn_connect.setStyleSheet(
            "QPushButton { background: #059669; color: #fff; border: none;"
            "border-radius: 5px; padding: 7px 12px; font-size: 12px; font-weight: 600; }"
            "QPushButton:hover { background: #047857; }")
        btn_connect.clicked.connect(lambda: (result.__setitem__("action", "settings"), dlg.accept()))
        btn_row.addWidget(btn_connect)

        btn_guide = QPushButton("วิธีเชื่อม")
        btn_guide.setCursor(Qt.PointingHandCursor)
        btn_guide.setStyleSheet(
            "QPushButton { background: transparent; color: #94a3b8;"
            "border: 1px solid #334155; border-radius: 5px;"
            "padding: 7px 10px; font-size: 12px; }"
            "QPushButton:hover { border-color: #7c3aed; color: #e2e8f0; }")
        btn_guide.clicked.connect(lambda: (result.__setitem__("action", "guide"), dlg.accept()))
        btn_row.addWidget(btn_guide)

        btn_ignore = QPushButton("ไม่สนใจ")
        btn_ignore.setCursor(Qt.PointingHandCursor)
        btn_ignore.setStyleSheet(
            "QPushButton { background: #dc2626; color: #fff; border: none;"
            "border-radius: 5px; padding: 7px 10px; font-size: 12px; font-weight: 600; }"
            "QPushButton:hover { background: #b91c1c; }")
        btn_ignore.clicked.connect(lambda: (result.__setitem__("action", "ignore"), dlg.accept()))
        btn_row.addWidget(btn_ignore)
        btn_row.addStretch(1)

        layout.addLayout(btn_row)
        btn_connect.setFocus()

        dlg.exec()
        # ★ ปิดด้วย X / Escape → Rejected → ปิด modal เฉย ๆ ไม่เปิด composer
        if dlg.result() == QDialog.Rejected:
            return "close"
        return result["action"]

    def _open_settings_to(self, section_key: str):
        """เปิด Settings dialog แล้วสลับไปหน้าที่ต้องการทันที

        ★ ต้องสร้าง dialog เอง (ไม่เรียก _open_settings) เพราะ exec() เป็น blocking
          — ถาเรียก _show_section หลัง exec() จะทำหลัง dialog ปิดไปแล้ว
        """
        try:
            from ui.dialogs.settings import SettingsDialog
            dlg = SettingsDialog(self)
            self._settings_dialog = dlg
            self._setup_twitch_oauth_in_dialog(dlg)
            dlg.settings_changed.connect(self._on_settings_changed)
            # ★ สลับไปหน้าที่ต้องการ ก่อน exec() (เพราะ exec() blocking)
            if hasattr(dlg, '_show_section'):
                dlg._show_section(section_key)
            dlg.exec()
            self._settings_dialog = None
        except Exception as e:
            logger.error(f"_open_settings_to error: {e}", exc_info=True)

    def _copy_overlay_url(self):
        """คัดลอก Overlay URL ไปยัง clipboard (URL สำหรับใส่ใน OBS Browser Source)"""
        try:
            port = (self.composer_server.port if (self.composer_server and hasattr(self.composer_server, 'port')) else int(getattr(self.settings, 'composer_port', 8801)))
            # ★ URL สำหรับ OBS — root path (/) ไม่ใช่ /canvas (ไม่มี route นี้)
            #   ?edit=1 = หน้าจัดวาง (สำหรับ streamer)
            #   /       = หน้า overlay ล้วน (สำหรับ OBS)
            url = f"http://localhost:{port}/"
            from PySide6.QtWidgets import QApplication
            clipboard = QApplication.clipboard()
            clipboard.setText(url)
            self.status_bar.set_status(f"📋 คัดลอก Overlay URL: {url} (วางใน OBS Browser Source)")
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
        self._setup_twitch_oauth_in_dialog(dlg)
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

    def _open_settings_at_section(self, section_key):
        """alias — เปิด Settings ไปที่ section (ถ้า dialog เปิดอยู่แล้ว = สลับ section ใน dialog เดิม)"""
        # ★ ถ้ามี dialog เปิดค้างอยู่ → แค่สลับ section (ไม่เปิดซ้อน)
        existing = getattr(self, '_settings_dialog', None)
        if existing is not None:
            try:
                if section_key in existing._sections:
                    for i in range(existing.sidebar.count()):
                        item = existing.sidebar.item(i)
                        if item.data(Qt.UserRole) == section_key:
                            existing.sidebar.setCurrentRow(i)
                            break
                existing.raise_()
                existing.activateWindow()
                return
            except Exception:
                pass
        self._open_settings_at(section_key)

    def _open_playroom_settings_tab(self):
        """เปิด Settings ไปที่แท็บ Playroom (เรียกผ่าน signal จาก composer server)"""
        self._open_settings_at_section("playroom")

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
                    # ★ delay เล็กน้อยกัน race condition (ไม่ return — connect ทุกตัวที่เปิดไว้)
                    import time as _time
                    _time.sleep(1)

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
