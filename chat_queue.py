"""chat_queue.py — Queue + TTS pipeline orchestrator

รับ ChatMessage จาก chat clients → filter → queue → TTS → (RVC) → play
มี throttle (drop ข้อความเก่าถ้าเยอะ) + dedupe (ข้ามซ้ำ)

การใช้งาน:
    pipeline = ChatPipeline(tts_engine, audio_player)
    pipeline.set_filter(text_filter)
    pipeline.set_rvc(None)            # None = เสียง Premwadee ตรงๆ
    pipeline.start()
    # chat clients เรียก pipeline.enqueue(msg)
    ...
    pipeline.stop()
"""
from __future__ import annotations

import hashlib
import logging
import io
import os
import queue
import random
import re
import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np

logger = logging.getLogger("chat_queue")

from audio_player import AudioPlayer
from chat_twitch import ChatMessage
from tts_engine import (
    SILENCE_MARKER,
    STRETCH_MARKER,
    TTSEngine,
    TTSParams,
    split_mp3_with_silence_markers,
)


# ---------------------------------------------------------------------- #
# Default skip-notification sound
# ★ ต้อง "ห้ามหายไปเด็ดขาด" แม้ user ตั้งเสียงเองแล้วกด reset — ใช้ 2 ชั้น:
#   1. ไฟล์ bundled จริง (assets/default_skip_notify.wav) ← ตัวหลัก
#   2. ถ้าหาไฟล์ bundled ไม่เจอไม่ว่ากรณีใด (build พัง/ไฟล์หาย) → synth เสียง
#      "ติ๊ง" สั้นๆ สดๆ เป็น fallback สุดท้าย ไม่มีทางคืนค่าว่างเปล่า
# ---------------------------------------------------------------------- #
_default_notify_sound_cache: Optional[str] = None


def _bundled_default_notify_path() -> Optional[str]:
    """หา path ของ assets/default_skip_notify.wav ทั้ง dev mode และ frozen (PyInstaller)"""
    import sys
    candidates = []
    if getattr(sys, "frozen", False):
        # frozen: assets/ อยู่ข้าง exe ใน _internal/ (ดู main.py:317 สำหรับ pattern เดียวกัน)
        exe_dir = os.path.dirname(sys.executable)
        candidates.append(os.path.join(exe_dir, "_internal", "assets", "default_skip_notify.wav"))
        candidates.append(os.path.join(exe_dir, "assets", "default_skip_notify.wav"))
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(os.path.join(meipass, "assets", "default_skip_notify.wav"))
    # dev mode: ข้าง chat_queue.py เอง
    candidates.append(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "assets", "default_skip_notify.wav"
    ))
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def get_default_notify_sound_path() -> str:
    """คืน path ไฟล์เสียงแจ้งเตือน default — ต้องไม่คืนค่าว่าง/พังเด็ดขาด

    ลำดับ: (1) ไฟล์ bundled จริง (assets/default_skip_notify.wav)
           (2) synth เสียง "ติ๊ง" สั้นๆ สดๆ เป็น fallback สุดท้าย
    """
    global _default_notify_sound_cache
    if _default_notify_sound_cache and os.path.exists(_default_notify_sound_cache):
        return _default_notify_sound_cache

    bundled = _bundled_default_notify_path()
    if bundled:
        _default_notify_sound_cache = bundled
        return bundled

    # ── fallback: bundled asset หายไปด้วยเหตุผลใดก็ตาม → synth เสียงสดๆ กันเงียบสนิท ──
    try:
        from data_dir import get_data_dir
        path = os.path.join(get_data_dir(), "_default_skip_notify.wav")
        if not os.path.exists(path):
            import soundfile as sf
            sr = 44100
            dur = 0.25
            t = np.linspace(0, dur, int(sr * dur), endpoint=False)
            tone = np.sin(2 * np.pi * 700 * t).astype(np.float32)
            fade_in = int(0.015 * sr)
            fade_out = int(0.10 * sr)
            env = np.ones_like(tone)
            env[:fade_in] = np.linspace(0, 1, fade_in)
            env[-fade_out:] *= np.linspace(1, 0, fade_out)
            audio = tone * env * 0.35
            os.makedirs(os.path.dirname(path), exist_ok=True)
            sf.write(path, audio, sr, subtype="PCM_16")
        _default_notify_sound_cache = path
        return path
    except Exception as e:
        logger.debug(f"generate default notify sound failed: {e}")
        return ""


# ---------------------------------------------------------------------- #
# Spam filter regexes
# ---------------------------------------------------------------------- #
# URL ทุกแบบ: http(s)://, www., หรือ domain.tld
_URL_RE = re.compile(
    r"(?:https?://|www\.)\S+|\S+\.(?:com|net|org|io|gg|tv|me|co|xyz|info|biz|tk|live|link)\b",
    re.IGNORECASE,
)
# code block / คำสั่งพิเศษ: ```...```, บรรทัดที่ขึ้นต้นด้วย ! . / แล้วตามด้วยคำ
_CODE_RE = re.compile(
    r"```|^\s*[!/\.]\w{2,}", re.MULTILINE
)


# ---------------------------------------------------------------------- #
# Viewer command prefix ([x2]/[p1]/[v50] for speed/pitch/volume override)
# ---------------------------------------------------------------------- #
# รูปแบบ: [x2] [x0.5] = rate (x value; 1 = default, 2 = 2x เร็ว, 0.5 = ช้าลงครึ่ง)
#          [p1] [p-2]  = pitch (1 unit = 5Hz; p1 = +5Hz, p-2 = -10Hz)
#          [v50] [v150] = volume (100 = default, 50 = เบาครึ่ง, 150 = ดัง 1.5x)
# parse เฉพาะ prefix ที่ **ต้นข้อความ** เท่านั้น — กัน false positive ([valorant], [gg])
# รวมกันได้: [x2][p1]สวัสดี = เร็ว 2x + สูง 5Hz
_VIEWER_PREFIX_RE = re.compile(
    r"^\s*(?:\[(?:x-?\d*\.?\d+|p-?\d+|v\d+)\]\s*)+",
    re.IGNORECASE,
)
_VIEWER_TOKEN_RE = re.compile(
    r"\[(x-?\d*\.?\d+|p-?\d+|v\d+)\]",
    re.IGNORECASE,
)


def parse_viewer_command_prefix(text: str) -> tuple[str, Optional[dict]]:
    """Parse viewer command prefix จากต้นข้อความ

    Returns (cleaned_text, override_dict | None)
    override_dict keys มีเฉพาะที่ viewer ระบุ:
        {"rate": int (-90..+100), "pitch": int (-50..+50 Hz), "volume": int (-50..+50)}
    ถ้าไม่มี prefix → คืน (text, None)
    """
    if not text:
        return text, None
    m = _VIEWER_PREFIX_RE.match(text)
    if m is None:
        return text, None
    prefix = m.group(0)
    override: dict = {}
    for tok in _VIEWER_TOKEN_RE.finditer(prefix):
        key = tok.group(1)
        letter = key[0].lower()
        num_str = key[1:]
        try:
            if letter == "x":
                v = float(num_str)
                rate_pct = int(round((v - 1.0) * 100))
                override["rate"] = max(-90, min(100, rate_pct))
            elif letter == "p":
                v = int(num_str)
                override["pitch"] = max(-50, min(50, v * 5))
            elif letter == "v":
                v = int(num_str)
                override["volume"] = max(-50, min(50, v - 100))
        except (ValueError, TypeError):
            continue
    if not override:
        return text, None
    cleaned = text[len(prefix):].lstrip()
    return cleaned, override


# ---------------------------------------------------------------------- #
# Pipeline config
# ---------------------------------------------------------------------- #
@dataclass
class PipelineConfig:
    """ตั้งค่าการอ่าน"""

    voice: str = "th-TH-PremwadeeNeural"  # edge-tts voice id หรือ rvc_model_id
    edge_voice: str = "premwadee"    # "premwadee" | "niwat"
    read_author: bool = True  # อ่านชื่อผู้แชทก่อน
    read_message: bool = True  # อ่านข้อความ
    # ★ โหมดอ่านชื่อ: "{ชื่อ} [หยุด] พูดว่า [หยุด] {ข้อความ}" — ประกอบเป็นเสียงทีละท่อนแล้วคั่นด้วยความเงียบจริง
    #   (ใช้ได้ทั้ง edge-tts ปกติ และ mixed-voice) ชื่อที่ใช้ = ชื่อที่ตั้งเองใน User Manager ถ้ามี
    intro_word: str = "พูดว่า"
    intro_gap: float = 0.5  # วินาที ที่หยุดคั่นระหว่าง ชื่อ / "พูดว่า" / ข้อความ
    rate: int = 0  # % (+10 = เร็วขึรึ้น 10%)
    volume: int = 100  # master volume 0-100 (ใช้ player.set_volume ตอนเล่น — รองรับทุก engine)
    # RVC f0 method: "rmvpe" (สมดุล) | "crepe" (GPU, สวย) | "harvest" | "pm" (เร็วสุด)
    rvc_f0method: str = "rmvpe"
    # RVC pitch shift (semitones -12..+12) — ยก/ลดระดับเสียงเพิ่มเติม
    rvc_pitch: int = 0
    # ---- mute (ปิดการอ่านออกเสียงชั่วคราว) ----
    tts_muted: bool = False
    # ---- code sound mute (ปิดเสียงโค้ดลับทั้งหมด — ไม่เล่น + ไม่ติดคิว) ----
    code_sound_muted: bool = False
    # ---- จำกัดการเล่นโค้ดลับต่อ user/วัน (0 = ไม่จำกัด) ----
    secret_code_daily_limit: int = 0
    # ---- per-platform volume offset (0-100, default 100 = no change; 0 = เงียบ) ----
    platform_volumes: dict = None  # {"twitch": 80, "youtube": 100, ...}
    # ---- per-platform mute (ปุ่มลำโพงในการ์ดแพลตฟอร์ม) ----
    platform_muted: dict = None  # {"twitch": True, "youtube": False, ...}
    # ---- ข้ามข้อความยาวเกินไป + เสียงเตือน ----
    skip_long_enabled: bool = False  # ★ ปิด (เดิม True) — อ่านยาวเท่าไหร่ก็ได้
    skip_long_threshold: int = 9999  # ★ ไม่จำกัด (เดิม 200)
    warn_sound_path: str = ""
    warn_sound_volume: float = 0.6
    # ---- หลายภาษา (ตรวจจับภาษา → เลือก edge-tts voice) ----
    multilang_enabled: bool = False
    # ---- Mixed Voice (แยก segment ตามภาษา → หลาย voice อ่านต่อกัน) ----
    mixed_voice_enabled: bool = False
    # ภาษาที่รองรับในโหมด multilang (ถ้าข้อความมีภาษาอื่น → เงียบ)
    multilang_langs: list = field(default_factory=lambda: ["en", "ja", "ko", "zh", "zh-TW", "fr"])
    # ---- auto-speed (เร่งข้อความยาวอัตโนมัติ) ----
    auto_speed: bool = True        # เปิด/ปิด
    auto_speed_length: int = 80    # ถ้า len(text) > นี้ → เร่ง
    auto_speed_boost: int = 30     # เพิ่ม rate +% ตอนเร่ง
    # ---- viewer interaction commands ([x2]/[p1]/[v50] chat prefix) ----
    viewer_cmd_enabled: bool = False
    viewer_cmd_cooldown: float = 5.0  # วินาที ต่อ user
    # queue throttle
    max_queue: int = 20  # ถ้าเกิน → drop ข้อความ "แชททั่วไป" ที่เก่าสุด (โดเนท/ซับ/event ไม่ถูกทิ้ง และไม่ลัดคิว)
    # ★ ข้อความแชททั่วไปที่รอนานเกินนี้ (วินาที นับจากที่โปรแกรมได้รับ) → ข้าม ไม่อ่าน (0 = ไม่จำกัด)
    #   กันผู้ชมได้ยินข้อความที่ล้าสมัยไปนานแล้วตอนแชทท่วม — event (โดเนท/ซับ ฯลฯ) ไม่ถูกข้ามด้วยข้อนี้
    max_wait_seconds: float = 45.0
    dedupe_window: float = 0.0  # ปิด dedupe — อ่านข้อความซ้ำได้
    author_cooldown: float = 0.0  # ปิด author cooldown
    # ---- spam protection (ปิดหมด — อ่านทุกข้อความ) ----
    #   ★ ป้องกัน spam ทำผ่าน block user → ล้างคิวทันที (purge_blocked_user)
    user_rate_limit: int = 999
    user_rate_window: float = 10.0
    user_ban_duration: float = 0.0
    cross_dedupe_threshold: int = 999
    cross_dedupe_window: float = 0.0
    filter_urls: bool = True
    filter_code_blocks: bool = True
    max_msg_length: int = 99999
    global_rate_threshold: int = 99999
    throttle_keep_percent: int = 100
    # ---- Playroom (มินิเกมวิดีโอ — multi-trigger) ----
    playroom_enabled: bool = False
    playroom_triggers: list = field(default_factory=list)  # [{code, daily_limit, clips}]
    # ---- Auto Translate (แปลเป็นไทยก่อน TTS) ----
    auto_translate_enabled: bool = False
    auto_translate_provider: str = "google"
    auto_translate_api_key: str = ""
    auto_translate_host: str = ""
    auto_translate_target_lang: str = "th"
    auto_translate_langs: list = field(default_factory=lambda: ["en", "ja", "ko", "zh", "vi", "id"])
    force_translate_users: list = field(default_factory=list)


# ---------------------------------------------------------------------- #
# TTS pipeline
# ---------------------------------------------------------------------- #
class ChatPipeline:
    """เชื่อม chat → filter → TTS → (RVC) → player ใน worker thread"""

    def __init__(
        self,
        tts_engine: TTSEngine,
        audio_player: AudioPlayer,
        config: Optional[PipelineConfig] = None,
    ) -> None:
        self.tts = tts_engine
        self.player = audio_player
        self.config = config or PipelineConfig()

        # dependencies (injected ภายหลัง)
        self._filter = None  # TextFilter instance หรือ None
        self._rvc = None  # RVCEngine instance หรือ None
        self._rvc_current_id: Optional[str] = None  # track loaded model id
        self._rvc_index_path: str = ""  # .index path (optional — ใช้ตอน convert)

        # Playroom: track usage ต่อ user ต่อ trigger ต่อวัน
        # {author_lower: {trigger_code: {"date": "2026-07-22", "count": 2}}}
        self._playroom_usage: dict = {}
        # {author_lower: {code: {date, count}}} — track secret code daily usage
        self._secret_usage: dict = {}

        self._q: "queue.Queue[Optional[ChatMessage]]" = queue.Queue()
        self._worker: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._is_running = False

        # double-buffering: compute worker → ready queue → play worker
        # ทำให้ TTS+RVC ข้อความถัดไปขนานกับการเล่นข้อความปัจจุบัน
        self._ready_q: "queue.Queue[Optional[tuple[np.ndarray, int]]]" = queue.Queue(
            maxsize=5  # ★ ปรับจาก 2 → 5 (เพิ่ม buffer → ลดโอกาสขาดช่วงระหว่างข้อความ)
        )
        self._compute_thread: Optional[threading.Thread] = None
        self._play_thread: Optional[threading.Thread] = None
        self._current_playing_author: str = ""  # ★ track ว่ากำลังเล่นเสียงของใคร (สำหรับ purge)
        self._current_playing_platform: str = ""  # ★ ...และของแพลตฟอร์มไหน (สำหรับ purge_platform)

        # ★ "รุ่นของคิว" — เพิ่มทุกครั้งที่ล้างคิว (ปิดเสียง TTS): ข้อความ/เสียงที่ติดรุ่นเก่า (ที่ค้างอยู่ระหว่างสร้างเสียง)
        #   จะถูกทิ้งแทนที่จะหลุดไปออกเสียงหลังกดปิด. _play_lock ทำให้ "เช็ครุ่น + เริ่มเล่น" กับ "ล้างคิว + หยุดเสียง"
        #   ไม่แทรกกัน
        self._epoch = 0
        self._play_lock = threading.Lock()
        self._enq_count = 0
        # ★ ขั้นแปลภาษา (เธรดแยก): แถวรอแปล + จำนวนข้อความที่ค้างอยู่ในขั้นนี้ (ใช้คงลำดับ FIFO)
        self._xlate_q: "queue.Queue[Optional[tuple]]" = queue.Queue()
        self._xlate_thread: Optional[threading.Thread] = None
        self._xlate_lock = threading.Lock()
        self._xlate_inflight = 0

        # dedupe tracking
        self._recent_hashes: deque[tuple[str, float]] = deque(maxlen=50)
        self._author_last_time: dict[str, float] = {}

        # viewer command cooldown (author_lower → last-effect timestamp)
        self._viewer_cmd_last_time: dict[str, float] = {}

        # spam protection tracking
        # 4a — per-user rate limit
        self._user_msg_times: dict[str, deque] = {}  # author → recent timestamps
        self._user_temp_banned: dict[str, float] = {}  # author → unban time
        # 4b — cross-author duplicate text
        self._text_hash_authors: dict[str, deque] = {}  # text_hash → recent authors
        # 4d — global rate (auto-throttle)
        self._recent_arrivals: deque[float] = deque(maxlen=2000)

        # stats
        self.processed = 0
        self.dropped = 0
        self.skipped_dedupe = 0
        self.skipped_author = 0
        self.skipped_spam = 0  # รวมทุก spam filter (rate/cross/url/code/length/throttle)

        # ★ ชื่อที่จะอ่านแทนชื่อเดิม (ชื่อที่ตั้งเองใน User Manager) — app ผูก callable ไว้ อ่านสดทุกข้อความ
        #   เลยไม่ต้อง rebuild config ทุกครั้งที่แก้ชื่อ. คืน "" / None = ใช้ชื่อเดิม
        self.name_resolver: Optional[Callable[[str], Optional[str]]] = None
        # ★ cache เสียงท่อนสั้น (ชื่อ + "พูดว่า") — คำเดิมไม่ต้อง synth ซ้ำทุกข้อความ (ลด latency)
        self._intro_cache: "OrderedDict[tuple, np.ndarray]" = OrderedDict()
        self._intro_lock = threading.Lock()

        # callbacks (UI hook)
        self.on_status: Optional[Callable[[str], None]] = None
        self.on_dropped: Optional[Callable[[ChatMessage], None]] = None
        # เรียกเมื่อข้อความถูกแปล (หลัง _maybe_translate สำเร็จ) — UI hook เพื่อ re-render row
        self.on_translated: Optional[Callable[[ChatMessage], None]] = None
        # เรียกเมื่อ "ข้อความที่ต้องแปลจริง" ผ่านขั้นแปลเสร็จแล้ว (สำเร็จ/ไม่สำเร็จ/ถูกทิ้ง ก็เรียก) — app ใช้ส่งต่อ overlay
        self.on_translate_settled: Optional[Callable[[ChatMessage], None]] = None
        # ★ Avatar widget — สัญญาณ TTS เริ่ม/จบเล่น (สำหรับ Composer avatar widget)
        self.on_playback_start: Optional[Callable[[], None]] = None
        self.on_playback_end: Optional[Callable[[], None]] = None
        # ★ Playroom — เรียกทันทีที่ trigger โดน match (clip_name, widget_ids)
        self.on_playroom_clip: Optional[Callable[[str, list], None]] = None
        # ★ TTS status tracking — เรียกทุกครั้งที่สถานะ TTS ของข้อความเปลี่ยน
        #   (tts_id, status, info) — status: "computing" | "ready" | "playing" | "done"
        #   | "skipped" | "error"   info: dict (เช่น elapsed, reason)
        #   ใช้แสดงไอคอนสถานะริมข้อความใน Live Chat (รอคิว/กำลังอ่าน/อ่านแล้วกี่วิ)
        self.on_tts_status: Optional[Callable[[str, str, dict], None]] = None

    # ------------------------------------------------------------------ #
    # Wiring
    # ------------------------------------------------------------------ #
    def _emit_tts_status(self, msg_or_id, status: str, **info) -> None:
        """★ แจ้ง UI สถานะ TTS ของข้อความ (ไอคอนริมข้อความใน Live Chat)

        msg_or_id: ChatMessage หรือ tts_id string
        status: "computing" | "ready" | "playing" | "done" | "skipped" | "error"
        """
        try:
            if self.on_tts_status is None:
                return
            tts_id = msg_or_id
            if not isinstance(msg_or_id, str):
                tts_id = (getattr(msg_or_id, 'extra', None) or {}).get("_tts_id", "")
            if not tts_id:
                return
            self.on_tts_status(tts_id, status, info)
        except Exception:
            pass

    def set_filter(self, text_filter) -> None:
        self._filter = text_filter

    def set_rvc(self, rvc_engine, model_id: Optional[str] = None, index_path: str = "") -> None:
        """set RVC engine (None = ใช้ edge-tts voice ตรงๆ)

        index_path: path ของ .index file (optional) — ถ้ามี จะใช้ตอน convert
        """
        self._rvc = rvc_engine
        self._rvc_current_id = model_id
        self._rvc_index_path = index_path

    def update_config(self, config: PipelineConfig) -> None:
        self.config = config

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def start(self) -> None:
        if self._is_running:
            return
        self._is_running = True
        self._stop_event.clear()
        # drain any stale ready queue
        while not self._ready_q.empty():
            try:
                self._ready_q.get_nowait()
            except queue.Empty:
                break
        # compute worker: chat → TTS → RVC → ready queue
        self._compute_thread = threading.Thread(
            target=self._compute_loop, name="ChatCompute", daemon=True
        )
        # play worker: ready queue → speaker
        self._play_thread = threading.Thread(
            target=self._play_loop, name="ChatPlay", daemon=True
        )
        self._compute_thread.start()
        self._play_thread.start()
        self._xlate_thread = threading.Thread(target=self._xlate_loop, name="ChatTranslate", daemon=True)
        self._xlate_thread.start()

    def stop(self) -> None:
        if not self._is_running:
            return
        self._is_running = False
        self._stop_event.set()
        # wake all workers
        self._xlate_q.put(None)
        self._q.put(None)
        try:
            self._ready_q.put_nowait(None)
        except queue.Full:
            pass
        # drain ready queue so play worker's blocking get() returns
        while not self._ready_q.empty():
            try:
                self._ready_q.get_nowait()
            except queue.Empty:
                break
        if self._compute_thread is not None and self._compute_thread.is_alive():
            self._compute_thread.join(timeout=5)
        if self._play_thread is not None and self._play_thread.is_alive():
            self._play_thread.join(timeout=5)
        if self._xlate_thread is not None and self._xlate_thread.is_alive():
            self._xlate_thread.join(timeout=2)
        self._compute_thread = None
        self._play_thread = None
        self._xlate_thread = None

    @property
    def queue_size(self) -> int:
        return self._q.qsize()

    def clear_queues(self) -> None:
        """หยุดเสียงทันที + ล้างคิวทั้งหมด (เรียกตอน mute ON)

        - drain `_q` → compute loop ไม่เอาข้อความถัดไปไป synthesize
        - drain `_ready_q` → play loop ไม่เอา audio ที่ synthesize แล้วไปเล่น
        - player.stop() → หยุด audio ที่กำลังเล่นอยู่ทันที

        ไม่ kill worker threads (mute แค่พัก ไม่ใช่ shutdown)
        """
        with self._play_lock:
            # 0. ขึ้นรุ่นใหม่ก่อน — อะไรที่ยังค้างอยู่ระหว่างสร้างเสียง/รอเข้าคิวเล่น จะถูกทิ้งเองเมื่อเสร็จ
            self._epoch += 1
            # 1. drain input queue (ข้อความที่รอ synthesize)
            while not self._q.empty():
                try:
                    self._q.get_nowait()
                except queue.Empty:
                    break
            # 2. drain ready queue (audio ที่ synthesize แล้ว รอเล่น)
            while not self._ready_q.empty():
                try:
                    self._ready_q.get_nowait()
                except queue.Empty:
                    break
            # 3. หยุด audio ที่กำลังเล่นอยู่ทันที
            try:
                self.player.stop()
            except Exception:  # noqa: BLE001
                pass
        if self.on_status is not None:
            self.on_status("🔇 ปิดการอ่าน — ล้างคิวเรียบร้อย")

    def purge_blocked_user(self, author: str) -> int:
        """ล้างข้อความของ user ที่บล็อก ออกจาก queue ทั้งหมด

        ★ ใช้ตอนกดบล็อก user ขณะกำลังอ่านอยู่ → ทิ้งข้อความของคนนั้นทิ้งหมด
          - _q: ดึงออกหมด แล้วใส่กลับเฉพาะที่ไม่ใช่คนนั้น
          - _ready_q: ดึงออกหมด แล้วใส่กลับเฉพาะที่ไม่ใช่คนนั้น
          - player: ถ้ากำลังเล่นเสียงของคนนั้นอยู่ → หยุดทันที

        Returns: จำนวนข้อความที่ทิ้ง
        """
        author_lower = author.strip().lower()
        purged = 0

        # ★ 1. drain _q → กรอง → ใส่กลับ (เฉพาะที่ไม่ใช่ user ที่บล็อก)
        kept_msgs = []
        while not self._q.empty():
            try:
                msg = self._q.get_nowait()
                if msg is None:
                    continue  # shutdown signal — ไม่ใส่กลับ
                if msg.author and msg.author.strip().lower() == author_lower:
                    purged += 1
                else:
                    kept_msgs.append(msg)
            except queue.Empty:
                break
        for msg in kept_msgs:
            self._q.put(msg)

        # ★ 2. drain _ready_q → กรอง → ใส่กลับ
        #   ★ ready_q เก็บ (audio_np, sr, vol_offset) tuple — ไม่มี author info
        #   → ต้องเก็บ author ใน tuple เพิ่ม หรือเช็คจาก _current_playing
        #   ★ วิธีง่าย: เก็บ mapping author → track ใน ready_q
        kept_ready = []
        while not self._ready_q.empty():
            try:
                item = self._ready_q.get_nowait()
                if item is None:
                    continue
                # ★ item = (audio_np, sr, vol_offset, author) — ถ้ามี author อยู่
                if len(item) >= 4 and item[3] and item[3].strip().lower() == author_lower:
                    purged += 1
                else:
                    kept_ready.append(item)
            except queue.Empty:
                break
        for item in kept_ready:
            self._ready_q.put(item)

        # ★ 3. ถ้ากำลังเล่นเสียงของคนนั้นอยู่ → หยุด
        current_author = getattr(self, '_current_playing_author', '')
        if current_author and current_author.strip().lower() == author_lower:
            try:
                self.player.stop()
            except Exception:
                pass

        if purged > 0 and self.on_status is not None:
            self.on_status(f"🚫 ล้าง {purged} ข้อความของ {author} ออกจากคิว")
        return purged

    # ------------------------------------------------------------------ #
    def _maybe_translate(self, msg: ChatMessage) -> tuple:
        """(ยังเก็บไว้เพื่อความเข้ากันได้) ตรวจ + แปลข้อความเป็นไทย — คืน (translated_text, source_lang, skip_reason)
        skip_reason: None = ปกติ | "lang_not_configured" = ไม่ใช่ภาษาที่ตั้งค่าให้แปล  — ห้ามเรียกจากเธรด UI (เรียกเน็ต)"""
        plan = self._translation_plan(msg)
        if plan[0] == "translate":
            return self._do_translate(msg, plan)
        if plan[0] == "skip":
            return (None, plan[1], "lang_not_configured")
        return (None, None, None)

    def _is_thai_speaker(self, author: str) -> bool:
        """ตรวจว่า user เคยแชทภาษาไทยบ่อยไหม — ถ้าใช่ → ไม่ต้องแปล"""
        try:
            if not hasattr(self, "_history") or self._history is None:
                return False
            from language_detect import detect_language
            entries = self._history.get(author)
            if not entries:
                return False
            # นับจำนวนครั้งที่แชทภาษาไทย (สูงสุด 20 entries ล่าสุด)
            recent = entries[-20:]
            thai_count = 0
            for entry in recent:
                text = entry.get("text", "")
                if text and detect_language(text) == "th":
                    thai_count += 1
            return thai_count >= 3
        except Exception:
            return False

    # Enqueue (thread-safe — เรียกจาก chat client thread)
    # ------------------------------------------------------------------ #
    def enqueue(self, msg: ChatMessage) -> None:
        """รับ ChatMessage จาก chat client"""
        if not self._is_running:
            logger.warning("enqueue: pipeline not running — skip")
            self._emit_tts_status(msg, "skipped", reason="pipeline หยุดอยู่")
            return
        logger.info(f"TTS enqueue: {msg.author}: {msg.text[:60] if msg.text else '(empty)'}")
        # ★ ตีตรา "รุ่นของคิว" ตั้งแต่ตอนรับข้อความ (ก่อนรอแปล/รอคิว) — กดปิดเสียงหลังจากนี้ ข้อความนี้จะถูกทิ้ง
        if msg.extra is None:
            msg.extra = {}
        msg.extra.setdefault("_tts_epoch", self._epoch)

        # -1) Playroom trigger check — ถ้ามี trigger (!fortune) ในข้อความ:
        #     - เช็ค daily limit ต่อ user (กัน spam)
        #     - หา trigger ที่ match จาก playroom_triggers (หลายตัว)
        #     - ตัด trigger ออกจาก text → TTS อ่านส่วนที่เหลือปกติ
        #     - สุ่มคลิปจาก trigger นั้นตาม weight → เก็บใน extra
        #     - เช็ค daily limit ของ trigger นั้น
        #     - UI loop จะ push clip ไป PlayroomServer
        playroom_triggers = getattr(self.config, "playroom_triggers", [])
        if (msg.text and playroom_triggers
                and getattr(self.config, "playroom_enabled", False)):
            import re as _pr_re
            # เรียง trigger จากยาว→สั้น เพื่อ match ที่ยาวกว่าก่อน
            triggers_sorted = sorted(
                playroom_triggers,
                key=lambda t: len(t.get("code", "")), reverse=True,
            )
            matched_trigger = None
            for trig in triggers_sorted:
                code = trig.get("code", "")
                if not code:
                    continue
                pattern = _pr_re.compile(
                    r'(?<!\w)' + _pr_re.escape(code) + r'(?!\w)',
                    _pr_re.UNICODE,
                )
                if pattern.search(msg.text):
                    matched_trigger = trig
                    break
            if matched_trigger is not None:
                trig_code = matched_trigger.get("code", "")
                clips = matched_trigger.get("clips", [])
                daily_limit = int(matched_trigger.get("daily_limit", 0))
                # เช็ค daily limit ต่อ user ต่อ trigger
                author_key = msg.author.lower()
                today = time.strftime("%Y-%m-%d")
                user_usage = self._playroom_usage.setdefault(author_key, {})
                trig_usage = user_usage.get(trig_code)
                if trig_usage is None or trig_usage.get("date") != today:
                    trig_usage = {"date": today, "count": 0}
                    user_usage[trig_code] = trig_usage
                # ถ้าถึง limit แล้ว → ไม่เล่นคลิป (แต่ยังตัด trigger จาก TTS)
                if daily_limit > 0 and trig_usage["count"] >= daily_limit:
                    if self.on_status is not None:
                        self.on_status(
                            f"🎮 {msg.author} ใช้ {trig_code} ครบ {daily_limit} ครั้งวันนี้แล้ว"
                        )
                else:
                    # สุ่มคลิปตาม weight + นับ usage
                    import random as _pr_rand
                    names = [c.get("name", "") for c in clips if c.get("path")]
                    weights = [max(1, int(c.get("weight", 50))) for c in clips if c.get("path")]
                    if names:
                        chosen = _pr_rand.choices(names, weights=weights, k=1)[0]
                        if msg.extra is None:
                            msg.extra = {}
                        msg.extra["_playroom_clip"] = chosen
                        # ★ stash target widget ids (empty = all widgets)
                        msg.extra["_playroom_target"] = list(matched_trigger.get("widget_ids", []))
                        trig_usage["count"] += 1
                        # ★ push ทันทีผ่าน callback (ไม่ต้องรอ UI loop — เดิมหายเงียบๆ)
                        if self.on_playroom_clip is not None:
                            try:
                                self.on_playroom_clip(chosen, list(matched_trigger.get("widget_ids", []) or []))
                            except Exception:
                                pass
                # ตัด trigger ออกจากข้อความ (เหมือน secret code)
                strip_pattern = _pr_re.compile(
                    r'(?<!\w)' + _pr_re.escape(trig_code) + r'(?!\w)\s*',
                    _pr_re.UNICODE,
                )
                remaining = strip_pattern.sub('', msg.text).strip()
                remaining = _pr_re.sub(r'\s+', ' ', remaining).strip()
                msg = ChatMessage(
                    platform=msg.platform, author=msg.author,
                    text=remaining, event=msg.event, extra=msg.extra,
                )

        # 0) secret code check — ถ้ามี code ในข้อความ (ที่ไหนก็ได้ในประโยค):
        #    - ตัด code ออกจาก text → TTS อ่านส่วนที่เหลือปกติ
        #    - เก็บ code sound ไว้ใน extra → compute loop จะเล่นหลัง TTS จบ
        if self._filter is not None and msg.text and self._filter.secret_codes:
            import re as _re

            # หา code ทุกตัวในข้อความ (word boundary, รองรับ ! และอักขระพิเศษ)
            # เรียงจากยาว→สั้น เพื่อ match code ที่ยาวกว่าก่อน (เช่น !wow ไม่ควร match ก่อน !wowza)
            codes_sorted = sorted(
                self._filter.secret_codes,
                key=lambda c: len(c.code), reverse=True,
            )
            matched_code = None
            for code in codes_sorted:
                # escape code สำหรับ regex + word boundary
                pattern = _re.compile(
                    r'(?<!\w)' + _re.escape(code.code) + r'(?!\w)',
                    _re.UNICODE,
                )
                if pattern.search(msg.text):
                    matched_code = code
                    break

            if matched_code is not None:
                # ตัด code ออกจากข้อความทุกที่ที่เจอ
                pattern = _re.compile(
                    r'(?<!\w)' + _re.escape(matched_code.code) + r'(?!\w)\s*',
                    _re.UNICODE,
                )
                remaining = pattern.sub('', msg.text).strip()
                remaining = _re.sub(r'\s+', ' ', remaining).strip()

                # ── daily limit check (เหมือน playroom pattern) ──
                can_play_sound = True
                if self.config.secret_code_daily_limit > 0:
                    today = time.strftime("%Y-%m-%d")
                    user_key = msg.author.lower()
                    user_usage = self._secret_usage.setdefault(user_key, {})
                    code_key = matched_code.code
                    code_usage = user_usage.get(code_key)
                    if code_usage is None or code_usage.get("date") != today:
                        code_usage = {"date": today, "count": 0}
                        user_usage[code_key] = code_usage
                    if code_usage["count"] >= self.config.secret_code_daily_limit:
                        can_play_sound = False
                    else:
                        code_usage["count"] += 1

                # เก็บ code sound ไว้ใน extra สำหรับ compute loop (ถ้าไม่ถึง limit)
                if msg.extra is None:
                    msg.extra = {}
                if can_play_sound:
                    msg.extra["_pending_code_sound"] = (
                        matched_code.sound_path, matched_code.volume
                    )
                # สร้าง msg ใหม่ด้วย text ที่ตัด code ออกแล้ว
                msg = ChatMessage(
                    platform=msg.platform, author=msg.author,
                    text=remaining, event=msg.event, extra=msg.extra,
                )

        # ★ per-platform volume offset — แปลง slider 0-100 → offset -100..+100
        #   100 = no change (offset 0), 50 = half volume (offset -50), 0 = mute (offset -100)
        #   ★ ถ้า vol_val <= 0 → ถือว่าไม่ได้ตั้งค่า → ใช้ 100 (no change)
        pv = getattr(self.config, 'platform_volumes', None)
        if pv and msg.platform in pv:
            # ★ vol_val <= 0 ถูก skip ไปแล้วใน _compute_loop (ก่อนเรียก _compute_one)
            #   ตรงนี้จึงเหลือแค่ 1-100 จริง ไม่ต้อง reset กลับ 100 อีกต่อไป
            vol_val = pv[msg.platform]
            if vol_val != 100:
                offset = vol_val - 100
                if msg.extra is None:
                    msg.extra = {}
                msg.extra["_tts_vol_offset"] = offset

        # ───── SPAM PROTECTION ─────
        now = time.time()

        # NOTE: Mention (@user) detection ย้ายไปอยู่ใน app_gui.on_message แล้ว
        # (ต้อง set is_mention ก่อนเข้า overlay/TTS enqueue ใน poll loop)
        # ที่นี่จะได้รับ msg.extra["is_mention"] มาเป็นที่เรียบร้อย → ไม่ต้องตรวจซ้ำ

        # 1) block user + 2) banned words / replace (skip / replace)
        # ★ Replace ทำก่อนแปลเสมอ — เพราะคำทับศัพท์ (เช่น "Oracle Book" → "ออราเคิล บุ๊ค")
        #   ต้องถูกแทนก่อน translator เห็น → translator จะได้ไม่แปลเป็น "หนังสือพยากรณ์"
        if self._filter is not None:
            if self._filter.is_user_blocked(msg.author):
                self._emit_tts_status(msg, "skipped", reason="ผู้ใช้ถูกบล็อก")
                return
            filtered = self._filter.filter_text(msg.text)
            if filtered is None:
                self._emit_tts_status(msg, "skipped", reason="มีคำต้องห้าม (NG word)")
                return
            msg.text = filtered

        # 2.5) Auto Translate (ถ้าเปิด) — แปลเป็นไทยก่อน TTS + ผ่าน replace หลังแปล
        # ★ ข้ามถ้าเป็น Preview (จากหน้า Replace/Settings — ห้ามแปล)
        # ★ การแปลต้องเรียกเน็ต (ช้า) → ทำในเธรดแยก (_xlate_loop) ไม่ให้หน้าโปรแกรมค้าง:
        #   ข้อความแสดงในแชทเป็นต้นฉบับทันที → แปลเสร็จค่อยแก้ข้อความในแชทเป็นไทย (on_translated) → แล้วจึงเข้าคิวอ่าน
        #   ทุกข้อความต่อแถวเดียวกัน (FIFO) ตราบที่ยังมีข้อความรอแปลอยู่ → ลำดับการอ่านตรงกับลำดับที่เข้ามาเสมอ
        _is_preview = (msg.extra or {}).get("_preview", False)
        if getattr(self.config, "auto_translate_enabled", False) and msg.text and not _is_preview:
            plan = self._translation_plan(msg)
            if plan[0] == "translate" or self._xlate_inflight > 0:
                self._xlate_submit(msg, plan)
                return
            if not self._apply_translation(msg, plan):
                return
        self._enqueue_rest(msg)

    # ------------------------------------------------------------------ #
    # แปลภาษา: ตัดสินใจ (เบา ไม่เรียกเน็ต) → แปลจริง (เรียกเน็ต) → ทำต่อ (คิว)
    # ------------------------------------------------------------------ #
    def _translation_plan(self, msg: ChatMessage) -> tuple:
        """ตัดสินใจแบบเบา ไม่เรียกเน็ต: ("none",) | ("skip", src_lang) | ("translate", src_lang, is_forced)"""
        try:
            from language_detect import detect_language
            src_lang = detect_language(msg.text)
            config = self.config
            force_users = getattr(config, "force_translate_users", [])
            is_forced = msg.author.lower() in [u.lower() for u in force_users]
            if not is_forced:
                if src_lang == "th":
                    return ("none",)
                target_langs = getattr(config, "auto_translate_langs", [])
                if src_lang is not None and src_lang not in target_langs:
                    return ("skip", src_lang)
                if src_lang is None:
                    return ("none",)
                if self._is_thai_speaker(msg.author):
                    return ("none",)
            return ("translate", src_lang, is_forced)
        except Exception as exc:  # noqa: BLE001
            logger.warning("translation plan error: %s", exc)
            return ("none",)

    def _do_translate(self, msg: ChatMessage, plan: tuple) -> tuple:
        """แปลจริง (เรียกเน็ต — ห้ามเรียกจากเธรด UI) → (translated_text, source_lang, skip_reason)"""
        try:
            from translator import Translator
            _, src_lang, is_forced = plan
            config = self.config
            t = Translator(provider=getattr(config, "auto_translate_provider", "google"),
                           api_key=getattr(config, "auto_translate_api_key", ""),
                           host=getattr(config, "auto_translate_host", ""),
                           target_lang=getattr(config, "auto_translate_target_lang", "th"),
                           supported_langs=getattr(config, "auto_translate_langs", []))
            result = t.translate(msg.text, source_lang="auto" if is_forced else src_lang)
            if result:
                return (result, src_lang if not is_forced else "auto", None)
            # แปล fail → คืน src_lang ด้วย เพื่อให้ผู้เรียกตัดสินใจ skip ได้
            return (None, src_lang, None)
        except Exception as exc:  # noqa: BLE001
            logger.warning("auto_translate error: %s", exc)
            return (None, None, None)

    def _apply_translation(self, msg: ChatMessage, plan: tuple) -> bool:
        """ทำตามแผน (แปล/ข้าม) + อัปเดตข้อความ/UI — คืน False = ข้อความนี้ไม่ต้องอ่าน (แจ้งสถานะแล้ว)"""
        if plan[0] == "translate":
            translated, src_lang, tl_skip = self._do_translate(msg, plan)
        elif plan[0] == "skip":
            translated, src_lang, tl_skip = None, plan[1], "lang_not_configured"
        else:
            return True
        if msg.extra is None:
            msg.extra = {}
        if translated is not None and translated != msg.text:
            original_text = msg.text
            msg.extra["translated"] = True
            msg.extra["original_text"] = original_text
            msg.extra["source_lang"] = src_lang
            msg.extra["translated_text"] = translated
            # ใช้ข้อความแปลสำหรับ TTS
            msg.text = translated
            # ★ apply Replace หลังแปล — เพราะ translator อาจแปลคำทับศัพท์ผิด
            #   เช่น "Apex Legends" → translator แปลเป็น "เอเพ็ก" → Replace แทนเป็น "เอเป็ก เลเจนด์"
            if self._filter is not None and msg.text:
                try:
                    msg.text = self._filter.apply_pronunciation(msg.text)
                except Exception:
                    pass
            # notify UI เพื่อ re-render row (แสดงคำแปลทันทีหลังแปลเสร็จ)
            if self.on_translated is not None:
                try:
                    self.on_translated(msg)
                except Exception:
                    pass
        elif tl_skip == "lang_not_configured":
            # ★ ไม่ใช่ภาษาที่ตั้งค่าให้แปล → เงียบ + tooltip บอก (เดิมหลุดไปให้ Premwadee
            #   อ่านต่างภาษา = เสียงแปลก ๆ) — detect ไม่ออก (src=None) ไม่โดนดักจุดนี้
            self._emit_tts_status(
                msg, "skipped",
                reason=f"ไม่ใช่ภาษาที่ตั้งค่าให้อ่านหรือแปล ({src_lang})",
            )
            self.skipped_spam += 1
            return False
        elif (translated is None and src_lang is not None) or (translated == msg.text and src_lang not in ("th", None)):
            # กรณี A: แปล fail (rate limit / network) → src_lang ไม่ใช่ None
            # กรณี B: translator คืนข้อความเดิม (translated == msg.text) แต่ไม่ใช่ไทย
            #         → ถ้าปล่อยไป TTS → ใช้ Premwadee อ่านต่างภาษา → error "No audio"
            # ทั้งสองกรณี: ถ้าไม่ใช่ภาษาไทย → skip (ไม่อ่าน TTS)
            from language_detect import detect_language
            if detect_language(msg.text) != "th":
                import logging
                logging.getLogger(__name__).info(
                    "Auto translate: skip TTS (translate fail/same) for %s src=%s: %s",
                    msg.author, src_lang, msg.text[:50]
                )
                self.skipped_spam += 1
                self._emit_tts_status(msg, "skipped", reason="แปลไม่สำเร็จ (ไม่ใช่ไทย)")
                return False  # ไม่ enqueue → ไม่อ่าน
        return True

    def _xlate_submit(self, msg: ChatMessage, plan: tuple) -> None:
        """ส่งเข้าแถวรอแปล (เธรดแยก) — คืนทันที ไม่บล็อกผู้เรียก (เธรด UI)"""
        if msg.extra is None:
            msg.extra = {}
        with self._xlate_lock:
            self._xlate_inflight += 1
        # pending = ต้องแปลจริง (ผู้เรียกเลื่อนการส่งไป overlay ไว้จนกว่าจะแปลเสร็จ); False = แค่ต่อแถวรักษาลำดับ
        msg.extra["_translate_pending"] = (plan[0] == "translate")
        self._emit_tts_status(msg, "queued")
        self._xlate_q.put((msg, plan))

    def _xlate_loop(self) -> None:
        while not self._stop_event.is_set():
            item = self._xlate_q.get()
            if item is None:
                break
            msg, plan = item
            try:
                self._xlate_process(msg, plan)
            except Exception as exc:  # noqa: BLE001
                logger.error(f"translate stage error: {exc}", exc_info=True)
                self._emit_tts_status(msg, "error", reason=str(exc))
            finally:
                was_pending = (msg.extra or {}).pop("_translate_pending", None)
                with self._xlate_lock:
                    self._xlate_inflight = max(0, self._xlate_inflight - 1)
                if was_pending and self.on_translate_settled is not None:
                    try:
                        self.on_translate_settled(msg)
                    except Exception:  # noqa: BLE001
                        pass

    def _xlate_process(self, msg: ChatMessage, plan: tuple) -> None:
        # ล้างคิว/ปิดเสียงไปแล้วระหว่างรอ → ทิ้ง
        if (msg.extra or {}).get("_tts_epoch", self._epoch) != self._epoch:
            self._emit_tts_status(msg, "skipped", reason="ปิดเสียง TTS อยู่")
            return
        # ถูกบล็อกระหว่างรอแปล → ทิ้ง
        if self._filter is not None and self._filter.is_user_blocked(msg.author):
            self._emit_tts_status(msg, "skipped", reason="ผู้ใช้ถูกบล็อก")
            return
        # รอนานเกินกำหนดแล้ว (เช่นเน็ตช้า แถวแปลยาว) → ไม่ต้องเสียเวลาแปล
        if plan[0] == "translate" and self._too_old(msg):
            self._emit_tts_status(msg, "skipped", reason=f"รอนานเกิน {int(self.config.max_wait_seconds)} วินาที — ข้าม")
            return
        if self._apply_translation(msg, plan):
            self._enqueue_rest(msg)

    def _enqueue_rest(self, msg: ChatMessage) -> None:
        """ขั้นที่เหลือของ enqueue (หลังตัวกรอง+แปล): rate limit → ตัวกรองเนื้อหา → dedupe → เข้าคิวสร้างเสียง"""
        # ล้างคิว/ปิดเสียงไปแล้วหลังข้อความนี้เข้ามา → ทิ้ง (สำคัญสำหรับข้อความที่รอแปลอยู่)
        if (msg.extra or {}).get("_tts_epoch", self._epoch) != self._epoch:
            self._emit_tts_status(msg, "skipped", reason="ปิดเสียง TTS อยู่")
            return
        now = time.time()
        # 3) per-author temp-ban check (rate limit penalty)
        author_lower = msg.author.lower()
        unban_at = self._user_temp_banned.get(author_lower, 0)
        if now < unban_at:
            self.skipped_spam += 1
            self._emit_tts_status(msg, "skipped", reason="โดน rate limit ชั่วคราว")
            return

        # 4) content filters — url / code block / ยาวผิดปกติ
        if msg.text:
            if self.config.filter_urls and _URL_RE.search(msg.text):
                self.skipped_spam += 1
                self._emit_tts_status(msg, "skipped", reason="มีลิงก์")
                return
            if self.config.filter_code_blocks and _CODE_RE.search(msg.text):
                self.skipped_spam += 1
                self._emit_tts_status(msg, "skipped", reason="เป็น code block")
                return
            limit = self.config.max_msg_length
            # ยาวเกินกำหนด = ข้ามทั้งข้อความ (ไม่อ่านครึ่งๆ) · 0 = ไม่จำกัด · โดเนท/ซับ/อีเวนต์ไม่ถูกข้าม
            if limit and limit > 0 and len(msg.text) > limit and not self._is_protected(msg):
                self.skipped_spam += 1
                self._emit_tts_status(msg, "skipped", reason=f"ยาวเกิน {limit} ตัวอักษร")
                return

        # 5) auto-throttle — ตอน chat ระเบิด (global rate)
        self._recent_arrivals.append(now)
        cutoff_60 = now - 60.0
        while self._recent_arrivals and self._recent_arrivals[0] < cutoff_60:
            self._recent_arrivals.popleft()
        if len(self._recent_arrivals) > self.config.global_rate_threshold:
            # สุ่มข้ามตาม keep_percent
            if random.random() > self.config.throttle_keep_percent / 100.0:
                self.skipped_spam += 1
                self._emit_tts_status(msg, "skipped", reason="แชทระเบิด (throttle)")
                return

        # 6) per-user rate limit (sliding window)
        times = self._user_msg_times.setdefault(
            author_lower, deque(maxlen=self.config.user_rate_limit + 1)
        )
        times.append(now)
        cutoff_window = now - self.config.user_rate_window
        while times and times[0] < cutoff_window:
            times.popleft()
        if len(times) > self.config.user_rate_limit:
            # โดน temp-ban
            self._user_temp_banned[author_lower] = now + self.config.user_ban_duration
            self.skipped_spam += 1
            self._emit_tts_status(msg, "skipped", reason="พิมพ์เร็วเกิน (โดนแบนชั่วคราว)")
            return

        # 7) cross-author duplicate text (raid / copy-paste)
        if msg.text.strip():
            text_hash = hashlib.md5(
                msg.text.strip().lower().encode("utf-8")
            ).hexdigest()
            authors = self._text_hash_authors.setdefault(
                text_hash, deque(maxlen=self.config.cross_dedupe_threshold + 1)
            )
            authors.append(author_lower)
            cutoff_cross = now - self.config.cross_dedupe_window
            while authors and authors[0] != author_lower and len(authors) > 1:
                # deque ไม่เก็บ timestamp แยก — เก็บได้แค่ maxlen → ใช้ count unique
                break
            unique_authors = set(authors)
            # expire heuristic: ถ้า deque เต็มและ unique ≥ threshold → spam
            if (
                len(authors) >= self.config.cross_dedupe_threshold
                and len(unique_authors) >= self.config.cross_dedupe_threshold
            ):
                self.skipped_spam += 1
                self._emit_tts_status(msg, "skipped", reason="ข้อความซ้ำจากหลายคน")
                return

        # ───── END SPAM PROTECTION ─────

        # 9) dedupe — ข้ามข้อความซ้ำภายใน window (author + text + event)
        h = self._hash(msg)
        cutoff = now - self.config.dedupe_window
        # ล้าง hash เก่า
        while self._recent_hashes and self._recent_hashes[0][1] < cutoff:
            self._recent_hashes.popleft()
        if any(hh == h for hh, _ in self._recent_hashes):
            self.skipped_dedupe += 1
            self._emit_tts_status(msg, "skipped", reason="ข้อความซ้ำ")
            return
        self._recent_hashes.append((h, now))

        # 10) author cooldown — กัน user เดียวพิมพ์รัวๆ (distinct from rate-limit ban)
        last = self._author_last_time.get(author_lower, 0)
        if now - last < self.config.author_cooldown:
            self.skipped_author += 1
            self._emit_tts_status(msg, "skipped", reason="พิมพ์ถี่เกิน (cooldown)")
            return
        self._author_last_time[author_lower] = now

        # 11) viewer command cooldown — ถ้า user อยู่ในช่วง cooldown
        #     → ยกเลิก override (อ่านปกติ) แต่ไม่ block ข้อความ
        #     prefix ถูก strip ไปแล้วตั้งแต่ on_message → ข้อความที่เข้า TTS สะอาดเสมอ
        if msg.extra and msg.extra.get("_viewer_override") is not None:
            cooldown = getattr(self.config, "viewer_cmd_cooldown", 5.0)
            last_cmd = self._viewer_cmd_last_time.get(author_lower, 0)
            if cooldown > 0 and (now - last_cmd) < cooldown:
                # ยังอยู่ใน cooldown → ยกเลิก effect (แต่ยังอ่านข้อความปกติ)
                msg.extra.pop("_viewer_override", None)
            else:
                self._viewer_cmd_last_time[author_lower] = now

        # 12) queue เต็ม → ทิ้งข้อความแชททั่วไปที่เก่าสุด (event ไม่ถูกทิ้ง; ลำดับของที่เหลือไม่เปลี่ยน)
        #     ★ ทำตรงนี้ (หลังผ่านทุกตัวกรอง) — เดิมทิ้งของเก่าก่อน แล้วข้อความใหม่ค่อยโดนตัวกรองตัดทิ้ง = เสียสองข้อความ
        self._make_room()
        if msg.extra is None:
            msg.extra = {}
        msg.extra.setdefault("_tts_enq_ts", now)       # เวลาเข้าคิว (ใช้คิดอายุ ถ้าแอปไม่ได้ตั้ง _tts_recv_ts)
        self._enq_count += 1
        if self._enq_count % 500 == 0:
            self._prune_tables(now)
        self._q.put(msg)
        self._emit_tts_status(msg, "queued")

    @staticmethod
    def _is_protected(msg) -> bool:
        """event (โดเนท/ซับ/บิท/raid ฯลฯ) = ไม่ถูกทิ้งตอนคิวเต็ม และไม่ถูกข้ามเพราะรอนาน"""
        return getattr(msg, "event", "message") not in ("message", "system")

    def _make_room(self) -> None:
        """คิวเต็ม (>= max_queue) → เอาข้อความแชททั่วไปที่ "เก่าสุด" ออก 1 ข้อความ (ไม่แตะ event ไม่สลับลำดับ)
        ถ้าที่รออยู่เป็น event ล้วน → ปล่อยให้คิวยาวเกินได้ (event มีน้อยกว่าแชทมาก)"""
        limit = int(self.config.max_queue or 0)
        if limit <= 0:
            return
        while self._q.qsize() >= limit:
            victim = None
            with self._q.mutex:
                dq = self._q.queue
                for idx, item in enumerate(dq):
                    if item is not None and not self._is_protected(item):
                        victim = item
                        del dq[idx]
                        break
            if victim is None:
                return
            self.dropped += 1
            self._emit_tts_status(victim, "skipped", reason="คิวเต็ม — ทิ้งข้อความเก่า")
            if self.on_dropped is not None:
                try:
                    self.on_dropped(victim)
                except Exception:  # noqa: BLE001
                    pass

    def _prune_tables(self, now: float) -> None:
        """ล้างตารางนับ/กันสแปมที่โตตามจำนวนคน/ข้อความตลอดสตรีม (เรียกทุก ~500 ข้อความ) — กัน RAM โตไม่หยุด"""
        try:
            window = max(float(self.config.user_rate_window or 0), 60.0)
            for k in [k for k, v in self._user_msg_times.items() if not v or v[-1] < now - window]:
                del self._user_msg_times[k]
            for k in [k for k, t in self._user_temp_banned.items() if t < now]:
                del self._user_temp_banned[k]
            for k in [k for k, t in self._author_last_time.items() if t < now - 3600]:
                del self._author_last_time[k]
            for k in [k for k, t in self._viewer_cmd_last_time.items() if t < now - 3600]:
                del self._viewer_cmd_last_time[k]
            while len(self._text_hash_authors) > 2000:           # เก็บ hash ข้อความล่าสุดแค่ 2,000 ตัว
                self._text_hash_authors.pop(next(iter(self._text_hash_authors)))
            today = time.strftime("%Y-%m-%d")
            for usage in (self._playroom_usage, self._secret_usage):   # โควตารายวัน: ของวันก่อนไม่ต้องเก็บ
                for user in list(usage.keys()):
                    per = usage[user]
                    for code in [c for c, v in per.items() if v.get("date") != today]:
                        del per[code]
                    if not per:
                        del usage[user]
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"prune tables failed: {exc}")

    def _hash(self, msg: ChatMessage) -> str:
        """hash content สำหรับ dedupe (author + text)"""
        key = f"{msg.author}|{msg.text}|{msg.event}"
        return hashlib.md5(key.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------ #
    # Notification sound playback
    # ------------------------------------------------------------------ #
    def _play_notification_sound(self, mp3_path: str, volume: float) -> None:
        """เล่นไฟล์เสียงแจ้งเตือน — ทำใน worker thread เพื่อไม่บล็อก chat"""
        if not os.path.exists(mp3_path):
            return
        # ใส่เข้า queue แบบพิเศษ? ง่ายสุดคือเล่นเลยใน background thread แยก
        t = threading.Thread(
            target=self._play_sound_blocking,
            args=(mp3_path, volume),
            daemon=True,
        )
        t.start()

    def _play_sound_blocking(self, mp3_path: str, volume: float) -> None:
        try:
            import soundfile as sf

            audio, sr = sf.read(mp3_path, dtype="float32", always_2d=False)
            if audio.ndim == 2:
                audio = audio.mean(axis=1)
            audio = audio * max(0.0, min(1.0, volume))
            # interrupt current playback? เราจะใช้ separate mixer channel
            # สำหรับ notification — ใช้ pygame.mixer.Sound ตรงๆ
            import pygame

            tmp_wav = os.path.join(os.environ.get("TEMP", "/tmp"), "_tts_notif.wav")
            sf.write(tmp_wav, audio, sr, subtype="PCM_16")
            snd = pygame.mixer.Sound(tmp_wav)
            snd.set_volume(max(0.0, min(1.0, volume)))
            snd.play()
            # รอจนเล่นจบ
            while pygame.mixer.get_busy():
                time.sleep(0.05)
            try:
                os.unlink(tmp_wav)
            except OSError:
                pass
        except Exception:
            pass

    def _load_sound_to_array(self, mp3_path: str, volume: float = 1.0) -> Optional[tuple[np.ndarray, int]]:
        """โหลดไฟล์เสียง → numpy array (สำหรับ push เข้า ready_q เล่นต่อจาก TTS)

        ใช้สำหรับ secret code sound — เล่นหลังจาก TTS จบ
        ★ volume: 0.0-1.0 — multiply เข้า audio array ก่อนคืน
        คืน (audio_np, sample_rate) หรือ None ถ้าโหลดไม่ได้
        """
        try:
            import soundfile as sf

            audio, sr = sf.read(mp3_path, dtype="float32", always_2d=False)
            if audio.ndim == 2:
                audio = audio.mean(axis=1)
            # ★ apply volume
            audio = audio * max(0.0, min(1.0, volume))
            return (audio, sr)
        except Exception:
            return None

    # ------------------------------------------------------------------ #
    # Double-buffered worker loops
    # ------------------------------------------------------------------ #
    # Flow: [chat queue] → _compute_loop → [ready queue maxsize=2] → _play_loop → speaker
    #
    # compute ทำ TTS+RVC ของข้อความถัดไปไปพร้อมๆ กับที่ play เล่นข้อความปัจจุบัน
    # ข้อความแรกยังช้า (ต้องรอ TTS+RVC) แต่ตั้งแต่ข้อความที่ 2 latency แทบหายไป
    def _compute_loop(self) -> None:
        """ดึง message → TTS → decode → RVC → push เข้า ready queue"""
        while not self._stop_event.is_set():
            msg = self._q.get()
            if msg is None:
                break  # shutdown signal

            # ───── ล้างคิวไปแล้วหลังข้อความนี้เข้าคิว (เช่นกดปิดเสียง) → ทิ้ง ─────
            msg_epoch = (msg.extra or {}).get("_tts_epoch", self._epoch)
            if msg_epoch != self._epoch:
                self._emit_tts_status(msg, "skipped", reason="ปิดเสียง TTS อยู่")
                continue

            # ───── MUTE / PLATFORM MUTE ─────
            _why = self._mute_reason(msg)
            if _why:
                logger.info(f"TTS muted ({_why}) → skip message")
                self._emit_tts_status(msg, "skipped", reason=_why)
                continue

            # ───── รอนานเกินกำหนด → ข้าม (เฉพาะแชททั่วไป) ─────
            if self._too_old(msg):
                logger.info(f"TTS skip: waited too long ({msg.author})")
                self._emit_tts_status(msg, "skipped",
                                      reason=f"รอนานเกิน {int(self.config.max_wait_seconds)} วินาที — ข้าม")
                continue

            try:
                self._emit_tts_status(msg, "computing")
                result = self._compute_one(msg)
                logger.info(f"TTS compute result: {'OK' if result is not None else 'None'}")
                # ───── กดปิดเสียง/ล้างคิว "ระหว่างที่กำลังสร้างเสียง" → ทิ้งผลลัพธ์ ไม่ให้หลุดไปออกเสียง ─────
                _late = None
                if msg_epoch != self._epoch:
                    _late = "ปิดเสียง TTS อยู่"
                else:
                    _late = self._mute_reason(msg)
                if _late:
                    self._emit_tts_status(msg, "skipped", reason=_late)
                    continue
                if result is not None:
                    # แนบ per-platform volume offset (ถ้ามี)
                    vol_offset = 0
                    if msg.extra:
                        vol_offset = msg.extra.get("_tts_vol_offset", 0)
                    # ★ push (audio_np, sr, vol_offset, author, tts_id, recv_ts, epoch, protected) เข้า ready queue
                    #   author ใช้ตอน purge_blocked_user (ล้างคิวของ user ที่บล็อก)
                    #   tts_id + recv_ts ใช้แจ้งสถานะ "playing"/"done" + นับเวลารวม
                    #   epoch ใช้ทิ้งเสียงรุ่นเก่าหลังล้างคิว, protected = event (ไม่ถูกข้ามเพราะรอนาน)
                    _ex = msg.extra or {}
                    if self._put_ready((
                        result[0], result[1], vol_offset, msg.author,
                        _ex.get("_tts_id", ""), _ex.get("_tts_recv_ts", 0.0) or _ex.get("_tts_enq_ts", 0.0),
                        msg_epoch, self._is_protected(msg), msg.platform,
                    ), msg_epoch):
                        self._emit_tts_status(msg, "ready")
                    else:
                        self._emit_tts_status(msg, "skipped", reason="ปิดเสียง TTS อยู่")
                        continue
                else:
                    _skip_r = (msg.extra or {}).pop("_tts_skip_reason", None) or "สังเคราะห์เสียงไม่ได้"
                    self._emit_tts_status(msg, "skipped", reason=_skip_r)
                # secret code: เล่นเสียง code หลังจาก TTS จบ (ถ้ามี + ไม่ได้ปิด code sound)
                pending = (msg.extra or {}).get("_pending_code_sound")
                if pending and not getattr(self.config, "code_sound_muted", False):
                    mp3_path, vol = pending
                    # synthesize code sound → push ต่อจาก TTS (★ ส่ง volume ไปด้วย)
                    code_audio = self._load_sound_to_array(mp3_path, volume=vol)
                    if code_audio is not None:
                        self._put_ready((code_audio[0], code_audio[1], 0, "", "", 0.0, msg_epoch, True, msg.platform), msg_epoch)
            except Exception as exc:  # noqa: BLE001
                logger.error(f"TTS error in compute_loop: {exc}", exc_info=True)
                # ★ แจ้งไอคอน — สร้างเสียงพัง (ไม่งั้น ⏳ ค้างเรื่อย ๆ โดยไม่รู้ว่า error)
                self._emit_tts_status(msg, "error", reason=str(exc))
                if self.on_status is not None:
                    try:
                        self.on_status(f"❌ TTS error: {exc}")
                    except Exception:
                        pass

        # signal play worker ว่าหมดแล้ว
        try:
            self._ready_q.put_nowait(None)
        except queue.Full:
            pass

    def _mute_reason(self, msg) -> Optional[str]:
        """ข้อความนี้ถูกปิดเสียงอยู่ไหม (ปิดทั้งหมด / ปิดทั้งแพลตฟอร์ม / slider แพลตฟอร์ม = 0) → เหตุผล หรือ None"""
        if self.config.tts_muted:
            return "ปิดเสียง TTS อยู่"
        _pm = getattr(self.config, 'platform_muted', None) or {}
        _pv = getattr(self.config, 'platform_volumes', None) or {}
        if _pm.get(msg.platform) or _pv.get(msg.platform, 100) <= 0:
            return f"ปิดเสียง TTS ของแพลตฟอร์ม {msg.platform}"
        return None

    def _platform_muted_now(self, platform: str) -> bool:
        _pm = getattr(self.config, 'platform_muted', None) or {}
        _pv = getattr(self.config, 'platform_volumes', None) or {}
        return bool(_pm.get(platform)) or _pv.get(platform, 100) <= 0

    def _cancelled(self, msg) -> bool:
        """ข้อความนี้ถูกยกเลิกไปแล้วหรือยัง (ล้างคิว/ปิดเสียงหลังเข้าคิว) — ใช้หยุดงานหนักที่เหลือ (RVC) ทันที"""
        return (msg.extra or {}).get("_tts_epoch", self._epoch) != self._epoch

    def purge_platform(self, platform: str) -> int:
        """ปิดเสียงแพลตฟอร์มทันที (ปุ่มลำโพงในการ์ดแพลตฟอร์ม): ทิ้งข้อความของแพลตฟอร์มนี้ที่รอคิว/สร้างเสียงเสร็จรอเล่น
        + หยุดเสียงที่กำลังอ่านอยู่ถ้าเป็นของแพลตฟอร์มนี้ — แพลตฟอร์มอื่นไม่กระทบ. คืนจำนวนที่ทิ้ง"""
        purged = 0
        victims = []
        with self._q.mutex:                 # แก้ทั้งคิวในครั้งเดียว ไม่แทรกกับเธรดที่ put/get พร้อมกัน ลำดับของที่เหลือไม่เปลี่ยน
            keep = []
            for m in self._q.queue:
                if m is not None and getattr(m, "platform", None) == platform:
                    victims.append(m)
                else:
                    keep.append(m)
            self._q.queue.clear()
            self._q.queue.extend(keep)
        with self._ready_q.mutex:
            keep = []
            for it in self._ready_q.queue:
                if isinstance(it, tuple) and len(it) >= 9 and it[8] == platform:
                    purged += 1
                    if it[4]:
                        victims.append(it[4])
                else:
                    keep.append(it)
            self._ready_q.queue.clear()
            self._ready_q.queue.extend(keep)
        for v in victims:
            self._emit_tts_status(v, "skipped", reason=f"ปิดเสียง TTS ของแพลตฟอร์ม {platform}")
        purged += sum(1 for v in victims if not isinstance(v, str))
        with self._play_lock:
            if self._current_playing_platform == platform:
                try:
                    self.player.stop()
                except Exception:  # noqa: BLE001
                    pass
        if purged and self.on_status is not None:
            self.on_status(f"🔇 ปิดเสียง {platform} — ล้างคิว {purged} ข้อความ")
        return purged

    def _too_old(self, msg) -> bool:
        """แชททั่วไปที่รอนานเกิน max_wait_seconds (นับจากที่รับข้อความ) — event ไม่ถูกข้าม"""
        limit = float(getattr(self.config, "max_wait_seconds", 0) or 0)
        if limit <= 0 or self._is_protected(msg):
            return False
        ex = msg.extra or {}
        ref = ex.get("_tts_recv_ts") or ex.get("_tts_enq_ts")
        return bool(ref) and (time.time() - float(ref)) > limit

    def _put_ready(self, item: tuple, epoch: int) -> bool:
        """ใส่เสียงที่สร้างเสร็จลงคิวเล่น — ถ้าระหว่างรอที่ว่าง (คิวเต็ม) มีการล้างคิว → ทิ้ง (คืน False)"""
        while not self._stop_event.is_set():
            if epoch != self._epoch:
                return False
            try:
                self._ready_q.put(item, timeout=0.2)
                return True
            except queue.Full:
                continue
        return False

    def _play_loop(self) -> None:
        """pop จาก ready queue → load + play + wait until done"""
        while not self._stop_event.is_set():
            item = self._ready_q.get()
            if item is None:
                break  # shutdown signal
            # ★ tuple: (audio_np, sr, vol_offset, author, tts_id, recv_ts) —
            #   author ใช้ตอน purge_blocked_user, tts_id/recv_ts ใช้แจ้งสถานะ TTS
            audio_np = sr = vol_offset = 0
            play_author = ''
            play_tts_id = ''
            play_recv_ts = 0.0
            play_epoch = None
            play_protected = True
            play_platform = ''
            if isinstance(item, tuple):
                if len(item) >= 9:
                    (audio_np, sr, vol_offset, play_author, play_tts_id, play_recv_ts,
                     play_epoch, play_protected, play_platform) = item[:9]
                elif len(item) >= 8:
                    audio_np, sr, vol_offset, play_author, play_tts_id, play_recv_ts, play_epoch, play_protected = item[:8]
                elif len(item) >= 6:
                    audio_np, sr, vol_offset, play_author, play_tts_id, play_recv_ts = item[:6]
                elif len(item) >= 4:
                    audio_np, sr, vol_offset, play_author = item[:4]
                elif len(item) == 3:
                    audio_np, sr, vol_offset = item
                elif len(item) == 2:
                    audio_np, sr = item

            # ★ รอนานเกินระหว่างรอคิวเล่น (แชททั่วไป) → ข้ามก่อนเล่น
            _limit = float(getattr(self.config, "max_wait_seconds", 0) or 0)
            if (_limit > 0 and not play_protected and play_recv_ts
                    and (time.time() - float(play_recv_ts)) > _limit):
                if play_tts_id:
                    self._emit_tts_status(play_tts_id, "skipped", reason=f"รอนานเกิน {int(_limit)} วินาที — ข้าม")
                continue

            # ★ แพลตฟอร์มของข้อความนี้ถูกปิดเสียงระหว่างรอคิวเล่น → ไม่เล่น
            if play_platform and self._platform_muted_now(play_platform):
                if play_tts_id:
                    self._emit_tts_status(play_tts_id, "skipped", reason=f"ปิดเสียง TTS ของแพลตฟอร์ม {play_platform}")
                continue

            # ★ track current playing author (สำหรับ purge_blocked_user)
            self._current_playing_author = play_author
            self._current_playing_platform = play_platform
            # ★ แจ้ง UI — ข้อความนี้กำลังถูกอ่านอยู่
            _stale = False
            try:
                # per-platform volume: vol_offset = -50..+50 (% change)
                # ใช้ numpy multiply ที่ audio data เพื่อรองรับทั้งลดและเพิ่ม (เกิน 1.0 ได้)
                if vol_offset:
                    gain = max(0.0, 1.0 + vol_offset / 100.0)
                    audio_np = np.clip(audio_np * gain, -1.0, 1.0)
                # ★ เช็ค "รุ่นของคิว" + เริ่มเล่น ภายใต้ล็อกเดียวกับ clear_queues → ไม่มีช่องให้เสียงรุ่นเก่าหลุดหลังกดปิด
                with self._play_lock:
                    if play_epoch is not None and play_epoch != self._epoch:
                        _stale = True
                    else:
                        self.player.load_audio(audio_np.astype(np.float32), sr)
                        # ★ master volume (0-100%) — รองรับทั้ง edge-tts และ RVC
                        #   config.volume = 0..100 → player volume 0.0..1.0
                        master_vol = max(0.0, min(1.0, getattr(self.config, 'volume', 100) / 100.0))
                        self.player.set_volume(master_vol)
                        self.player.play()
                if _stale:
                    if play_tts_id:
                        self._emit_tts_status(play_tts_id, "skipped", reason="ปิดเสียง TTS อยู่")
                    self._current_playing_author = ''
                    continue
                if play_tts_id:
                    self._emit_tts_status(play_tts_id, "playing")
                # ★ Avatar widget — สัญญาณ TTS เริ่มเล่น (สำหรับ Composer avatar widget)
                #   ใช้ _avatar_started flag เพื่อ ensure ว่า end จะถูกเรียกเสมอ (แม้ exception)
                _avatar_started = False
                if self.on_playback_start is not None:
                    try:
                        self.on_playback_start()
                        _avatar_started = True
                    except Exception:  # noqa: BLE001
                        pass
                try:
                    # รอจนเล่นจบ — ขณะนี้ compute worker ทำข้อความถัดไปอยู่
                    # ★ ปรับจาก 50ms → 10ms (ลด gap ระหว่างจบเสียงเก่า + เริ่มเสียงใหม่)
                    # เดิม: sleep(0.05) → ใหม่: sleep(0.01)
                    while self.player.is_playing() and not self._stop_event.is_set():
                        time.sleep(0.01)
                finally:
                    # ★ Avatar widget — สัญญาณ TTS เล่นจบ (เสมอ ถ้า start ถูกเรียก)
                    if _avatar_started and self.on_playback_end is not None:
                        try:
                            self.on_playback_end()
                        except Exception:  # noqa: BLE001
                            pass
            except Exception as exc:  # noqa: BLE001
                if self.on_status is not None:
                    self.on_status(f"❌ playback error: {exc}")
                if play_tts_id:
                    self._emit_tts_status(play_tts_id, "error", reason=str(exc))

            # ★ แจ้ง UI — อ่านจบ + เวลารวมตั้งแต่รับข้อความถึงอ่านเสร็จ
            if play_tts_id:
                _elapsed = time.time() - play_recv_ts if play_recv_ts else None
                self._emit_tts_status(play_tts_id, "done", elapsed=_elapsed)

            self.processed += 1

        if self.on_status is not None:
            self.on_status("⚪ pipeline stopped")

    def _looks_like_emote_code(self, text: str) -> bool:
        """Heuristic: ตรวจว่าข้อความดูเหมือน emote code (ไม่ใช่คำพูด) ไหม

        กรณีใช้: emote ที่ไม่ได้อยู่ใน Twitch tag / third-party list → เหลือเป็น code ใน text
        → TTS ควรข้าม ไม่อ่านออกเสียง

        เงื่อนไข (ต้องครบทุกข้อ):
        1. เป็นคำเดียว (ไม่มี space) — emote code มักเป็นคำเดียว
        2. มีความยาว 4-30 ตัวอักษร
        3. ไม่ใช่คำไทย (ไม่มี Thai chars) — emote code เป็น ASCII
        4. ไม่ใช่ URL หรือ mention
        5. มีลักษณะ emote code อย่างน้อย 1 ข้อ:
           - มีตัวเลขผสมในคำ (เช่น men9ch)
           - เป็น camelCase ที่ชัดเจน (ตัวเล็ก+ตัวใหญ่สลับ เช่ men9chStronk, PopNemo)
           - มีอักขระพิเศษที่ไม่พบในคำปกติ (เช่น _ กลางคำ)
        """
        import re
        # 1. คำเดียว ไม่มี space (ยอม space ตอนท้ายที่ถูก strip แล้ว)
        stripped = text.strip()
        if not stripped or " " in stripped:
            return False
        # 2. ความยาว 4-30
        if not (4 <= len(stripped) <= 30):
            return False
        # 3. ไม่ใช่คำไทย
        if re.search(r"[\u0E00-\u0E7F]", stripped):
            return False
        # 4. ไม่ใช่ URL / mention / เครื่องหมายพิเศษต้นคำ
        if stripped.startswith(("http://", "https://", "www.", "@", "#", "!")):
            return False
        if "." in stripped and re.search(r"\.[a-z]{2,}", stripped, re.IGNORECASE):
            # มี TLD-like (เช่น .com) → น่าจะ URL ไม่ใช่ emote
            return False
        # 5. ตรวจลักษณะ emote code
        # 5a. มีตัวเลขผสมในคำ (เช่น men9ch, xqc2)
        if re.search(r"[a-zA-Z]\d", stripped) and re.search(r"\d[a-zA-Z]", stripped):
            return True
        # 5b. camelCase — มี transition ตัวเล็ก→ตัวใหญ่ อย่างน้อย 1 ครั้ง
        # เช่น PopNemo (p→N), men9chStronk (ch→S — แต่อันนี้มีตัวเลข ข้อ 5a จับแล้ว)
        # คำปกติที่เป็น camelCase (iPhone, YouTube) มี transition ที่ตำแหน่งเริ่มต้น (i→P, You→T)
        # → ต้องมี transition ที่ตำแหน่ง > 1 (กลางคำ) เพื่อกัน false positive
        # และความยาว >= 5 (PopNemo = 7, iPhone = 6 แต่ transition ที่ i→P ตำแหน่ง 1 ไม่นับ)
        # whitelist คำปกติที่เป็น camelCase (brand names, ฯลฯ)
        _CAMELCASE_WHITELIST = {
            "youtube", "instagram", "whatsapp", "tiktok", "snapchat",
            "airdrop", "bluetooth", "powerpoint", "photoshop",
            "facebook", "github", "gitlab", "linkedin", "discord",
            "minecraft", "playstation", "nintendo", "samsung",
        }
        if stripped.lower() in _CAMELCASE_WHITELIST:
            return False
        has_mid_transition = False
        for i in range(2, len(stripped)):  # เริ่มที่ index 2 (ข้าม 2 ตัวแรก)
            if stripped[i-1].islower() and stripped[i].isupper():
                has_mid_transition = True
                break
        if has_mid_transition and len(stripped) >= 5:
            return True
        # 5c. มี _ กลางคำ (เช่น BetterTTV emote: np_galaxy)
        # แต่ไฟล์ path ก็มี _ → เช็คว่าไม่มี . ด้วย
        if "_" in stripped[1:-1] and "." not in stripped:
            return True
        return False

    def _compute_one(self, msg: ChatMessage) -> Optional[tuple[np.ndarray, int]]:
        """สร้างเสียง (TTS + RVC) → คืน (audio_np, sample_rate) พร้อมเล่น

        Returns None ถ้าข้ามข้อความนี้
        """
        # ประกอบข้อความสำหรับอ่าน
        text = self._build_speak_text(msg)
        if not text.strip():
            logger.info(f"TTS skip: empty text after build_speak_text")
            msg.extra["_tts_skip_reason"] = "ข้อความว่าง (ไม่มีคำอ่าน)"
            return None

        # ── Heuristic: ข้ามถ้าข้อความดูเหมือน emote code (ไม่ใช่คำพูด) ──
        if self._looks_like_emote_code(text):
            logger.info(f"TTS skip: looks like emote code: {text[:30]}")
            msg.extra["_tts_skip_reason"] = "ดูเหมือน emote ไม่ใช่คำพูด"
            return None

        # ───── SKIP-LONG: ข้ามข้อความยาวเกินไป + เล่นเสียงเตือน ─────
        if (
            self.config.skip_long_enabled
            and len(text) > self.config.skip_long_threshold
        ):
            if self.config.warn_sound_path:
                try:
                    self._play_notification_sound(
                        self.config.warn_sound_path,
                        self.config.warn_sound_volume,
                    )
                except Exception:  # noqa: BLE001
                    pass
            msg.extra["_tts_skip_reason"] = (
                f"ยาวเกิน {self.config.skip_long_threshold} ตัวอักษร (skip-long)"
            )
            return None  # ข้ามข้อความนี้

        # ───── AUTO-SPEED: เร่งข้อความยาว ─────
        effective_rate = self.config.rate
        if (
            self.config.auto_speed
            and len(text) > self.config.auto_speed_length
            and self.config.auto_speed_boost > 0
        ):
            effective_rate = min(
                self.config.rate + self.config.auto_speed_boost, 100
            )

        # ───── Viewer command override (จาก chat prefix [x2]/[p1]/[v50]) ─────
        # override ทับ effective_rate/volume; pitch เริ่มจาก 0 (ระบบเดิมไม่ได้ตั้ง pitch)
        viewer_pitch = 0
        # ★ edge-tts volume offset (-50..+50) — จาก viewer command [v50] เท่านั้น
        #   master volume (0-100%) คุมที่ player.set_volume ตอนเล่น (รองรับทุก engine)
        viewer_volume = 0
        if msg.extra and msg.extra.get("_viewer_override"):
            ov = msg.extra["_viewer_override"]
            if "rate" in ov:
                # แทนที่ rate ทั้งหมด (override มีค่า absolute % offset)
                effective_rate = ov["rate"]
            if "pitch" in ov:
                viewer_pitch = ov["pitch"]
            if "volume" in ov:
                viewer_volume = max(-50, min(50, ov["volume"]))

        # ───── เลือก base voice ─────
        # กรณี 1: มี RVC → สร้างเสียงด้วย base voice แล้ว RVC ทับทับทีหลัง
        #          ถ้าเปิด multilang → base voice ตามภาษาที่ detect (RVC ยังทับเสมอ)
        #          ถ้าปิด multilang → ใช้ Premwadee (เดิม)
        # กรณี 2: ไม่มี RVC → ใช้ edge-tts voice ตรงๆ
        #          ถ้าเปิด multilang → เลือก voice ตามภาษา
        #          ถ้าปิด → ใช้ config.voice (Premwadee)
        # กรณี 3: Mixed Voice → แยก segment ตามภาษา → หลาย voice อ่านต่อกัน
        rvc_on = self._rvc is not None and self._rvc_current_id
        # ★ Preview mode — บังคับใช้ Premwadee (ข้าม multilang + RVC + translation)
        _is_preview = (msg.extra or {}).get("_preview", False)
        if _is_preview:
            rvc_on = False  # ไม่ RVC
        # Mixed Voice ใช้ได้เฉพาะโหมด multilang (ไม่ใช่โหมดแปล)
        _use_mixed = (getattr(self.config, "mixed_voice_enabled", False)
                      and getattr(self.config, "multilang_enabled", False)
                      and not getattr(self.config, "auto_translate_enabled", False)
                      and not _is_preview)  # ★ Preview ไม่ใช้ mixed voice
        if _use_mixed:
            # ── Mixed Voice: แยก segment ตามภาษา → TTS แต่ละ segment → concat ──
            _intro_th = self._start_intro_prefetch(msg, effective_rate, viewer_volume, viewer_pitch)
            audio_np = self._synth_mixed_voice(text, effective_rate, viewer_volume, viewer_pitch)
            if audio_np is not None:
                # ★ โหมดอ่านชื่อ: ต่อ [ชื่อ][หยุด][พูดว่า][หยุด] ก่อน RVC (RVC แปลงทั้งก้อนครั้งเดียว)
                audio_np = self._prepend_intro(audio_np, msg, effective_rate, viewer_volume, viewer_pitch,
                                               prefetch=_intro_th)
                # ★ ถูกยกเลิก (กดปิดเสียง/ล้างคิว) ระหว่างสร้างเสียง → ไม่ต้องเริ่ม RVC (ทำแล้วขัดจังหวะไม่ได้ กิน GPU นาน)
                if self._cancelled(msg):
                    return None
                # RVC convert ถ้ามี (ถ้า fail → ใช้ audio ต้นฉบับ)
                if rvc_on:
                    try:
                        from rvc_engine import RVCParams
                        f0method = getattr(self.config, "rvc_f0method", "rmvpe")
                        pitch = getattr(self.config, "rvc_pitch", 0)
                        params = RVCParams(f0method=f0method, f0up_key=pitch)
                        converted = self._rvc.convert_array(audio_np, 44100, params)
                        if converted is not None and len(converted) > 0:
                            audio_np = converted[0]
                    except Exception:
                        pass  # RVC fail → ใช้ audio ต้นฉบับ (ไม่ convert)
                return audio_np, 44100
            # fallback → ใช้ Premwadee ปกติ
            voice = "th-TH-PremwadeeNeural"
        elif rvc_on and not self.config.multilang_enabled:
            # RVC + ไม่เปิด multilang → ใช้ Premwadee เป็น base + skip ต่างภาษา (Premwadee อ่านไม่ได้)
            voice = "th-TH-PremwadeeNeural"
            # ★★ ถ้าเปิด auto_translate → ข้ามการตรวจภาษา (เพราะแปลเป็นไทยแล้ว)
            if not getattr(self.config, "auto_translate_enabled", False):
                from language_detect import detect_language
                _text_lang = detect_language(text)
                if _text_lang not in ("th", "en"):
                    msg.extra["_tts_skip_reason"] = (
                        f"ไม่ใช่ภาษาที่ตั้งค่าให้อ่าน ({_text_lang}) — Premwadee อ่านไม่ได้"
                    )
                    return None  # Premwadee อ่านต่างภาษาไม่ได้ → skip
        elif self.config.multilang_enabled and not _is_preview:
            # เปิด multilang → detect ภาษาแล้วเลือก voice (RVC จะทับทับทีหลังถ้ามี)
            from language_detect import VOICE_BY_LANG, detect_language

            lang = detect_language(text)
            # ภาษาที่ไม่รู้จัก (ฮินดี/อาหรับ/รัสเซีย) → ไม่มี voice → skip (กัน error "No audio")
            if lang not in VOICE_BY_LANG:
                msg.extra["_tts_skip_reason"] = (
                    f"ไม่ใช่ภาษาที่ตั้งค่าให้อ่าน ({lang}) — ไม่มี voice รองรับ"
                )
                return None
            voice = VOICE_BY_LANG.get(lang, self.config.voice)
        else:
            # default — base voice เท่านั้น (ไม่มี RVC + ไม่มี multilang)
            # ★ ใช้ edge_voice (premwadee/niwat) — ไม่ใช่ config.voice (อาจเป็น RVC model id ที่ยังไม่ได้โหลด)
            # guard: ถ้าเป็นภาษาที่ Premwadee/Niwat อ่านไม่ได้ (unknown/hindi/arabic/...) → skip
            # ★★ แต่ถ้าเปิด auto_translate → ข้ามการตรวจภาษา (เพราะแปลเป็นไทยแล้ว)
            if not getattr(self.config, "auto_translate_enabled", False):
                from language_detect import detect_language
                _def_lang = detect_language(text)
                if _def_lang not in ("th", "en"):
                    logger.info(f"TTS skip: language={_def_lang} not th/en (text: {text[:30]})")
                    msg.extra["_tts_skip_reason"] = (
                        f"ไม่ใช่ภาษาที่ตั้งค่าให้อ่านหรือแปล ({_def_lang})"
                    )
                    return None
            # ★ resolve เป็น edge-tts voice id จริง (premwadee → th-TH-PremwadeeNeural)
            _ev = getattr(self.config, "edge_voice", "premwadee")
            voice = {"premwadee": "th-TH-PremwadeeNeural", "niwat": "th-TH-NiwatNeural"}.get(_ev, "th-TH-PremwadeeNeural")

        # TTS synth — edge-tts (online) แล้วส่งต่อ RVC overlay ด้านล่าง (ถ้าเปิด)
        audio_np = None  # ★ init กัน UnboundLocalError ตอน fallback
        # ★ เลือก edge voice จาก config.edge_voice (premwadee/niwat)
        edge_voice_name = self._resolve_edge_voice_name(voice)
        # ★ โหมดอ่านชื่อ: edge-tts ส่ง "ชื่อ⏎พูดว่า⏎ข้อความ" เป็น request เดียวได้ → ไม่ต้อง prefetch ท่อนนำขนาน
        _sp_text = self._single_pass_text(msg, text, edge_voice_name)
        _intro_th = [] if _sp_text else self._start_intro_prefetch(
            msg, effective_rate, viewer_volume, viewer_pitch)

        def _edge_audio(txt: str):
            mp3 = self._synth_sync(TTSParams(
                text=txt,
                voice=edge_voice_name,
                rate=f"{effective_rate:+d}%",
                volume=f"{viewer_volume:+d}%",
                pitch=f"{viewer_pitch:+d}Hz",
            ))
            return mp3, (self._decode_mp3(mp3) if mp3 else None)

        mp3_bytes, audio_np = _edge_audio(_sp_text or text)
        if not mp3_bytes:
            # ★ edge-tts fail → skip (กันคิวกระจุก)
            logger.warning(f"TTS fail — skip message: {text[:50]!r}")
            msg.extra["_tts_skip_reason"] = "สร้างเสียงไม่สำเร็จ (TTS engine fail)"
            return None
        if _sp_text and audio_np is not None and len(audio_np) > 0:
            n_pauses = len(self._intro_parts(msg))
            fixed = self._normalize_intro_pauses(
                audio_np, n_pauses, float(getattr(self.config, "intro_gap", 0.5)))
            if fixed is not None:
                audio_np = fixed
                msg.extra["_intro_done"] = True      # ชื่อ+พูดว่า อยู่ในเสียงนี้แล้ว
            else:
                # ตรวจช่วงหยุดไม่เจอ (edge เปลี่ยนพฤติกรรม/ข้อความแปลก) → ถอยไปทำแบบทีละท่อน
                logger.info("intro single-pass: ไม่พบช่วงหยุดที่คาด → ทำทีละท่อน")
                mp3_bytes, audio_np = _edge_audio(text)
                if not mp3_bytes:
                    msg.extra["_tts_skip_reason"] = "สร้างเสียงไม่สำเร็จ (TTS engine fail)"
                    return None

        # decode MP3 → numpy (แยก silence/stretch markers)
        if audio_np is None or len(audio_np) == 0:
            logger.warning(f"MP3 decode fail — skip message: {text[:50]!r}")
            msg.extra["_tts_skip_reason"] = "ถอดรหัสไฟล์เสียงไม่สำเร็จ"
            return None

        # ★ โหมดอ่านชื่อ: ต่อ [ชื่อ][หยุด][พูดว่า][หยุด] หน้าเสียงข้อความ (engine เดียวกับที่ใช้จริง) ก่อน RVC
        audio_np = self._prepend_intro(audio_np, msg, effective_rate, viewer_volume, viewer_pitch,
                                       prefetch=_intro_th)

        # ★ ถูกยกเลิกไปแล้ว → ไม่เริ่ม RVC (ดูเหตุผลด้านบน)
        if self._cancelled(msg):
            return None
        # RVC convert (ถ้ามี) — ใช้ convert_array เร็วกว่า (bypass file I/O)
        if self._rvc is not None and self._rvc_current_id:
            try:
                from rvc_engine import RVCParams

                # f0method + pitch จาก config
                f0method = getattr(self.config, "rvc_f0method", "rmvpe")
                pitch = getattr(self.config, "rvc_pitch", 0)
                params = RVCParams(
                    f0method=f0method,
                    f0up_key=pitch,
                    index_rate=0.75,
                    protect=0.33,
                    index_path=getattr(self, "_rvc_index_path", "") or "",
                )
                # ใช้ fast path ตัด tempfile + load_audio + PyAV ทิ้งหมด
                converted, out_sr = self._rvc.convert_array(audio_np, 44100, params)
                return (converted, out_sr)
            except Exception as exc:  # noqa: BLE001
                if self.on_status is not None:
                    self.on_status(f"⚠️ RVC failed ({exc}) — using base voice")
                return (audio_np, 44100)

        return (audio_np, 44100)


    def _config_volume_float(self) -> float:
        """แปลง volume % → 0..1"""
        # edge-tts volume ปรับแล้วใน TTS step แล้ว ที่นี่ใช้ player master volume
        return 1.0

    def _synth_sync(self, params: TTSParams, timeout: float = 30.0) -> Optional[bytes]:
        """เรียก TTS engine แบบ synchronous

        ★ timeout 30s — ประโยคยาวใช้เวลานานเป็นธรรมชาติ (126 ตัว → ~9s)
          ถ้า < 10s จะ kill ประโยคยาวก่อนเสร็จ → skip message
        """
        done_event = threading.Event()
        result: dict = {}

        def on_done(data: bytes) -> None:
            result["data"] = data
            done_event.set()

        def on_error(err: str) -> None:
            result["error"] = err
            done_event.set()

        epoch0 = self._epoch
        self.tts.generate(params, on_done, on_error)
        # ★ รอแบบสั้นๆ ทีละ 50 ms — ถ้ากดปิดเสียง/ล้างคิวระหว่างรอ (เช่น สแปมประโยคยาวๆ ที่ใช้เวลาสร้างเสียงนาน)
        #   เลิกรอทันที ไม่ต้องรอจนเสร็จ/หมดเวลา — คำขอที่ค้างอยู่ทางเน็ตปล่อยให้จบเอง ผลลัพธ์ถูกทิ้ง
        deadline = time.monotonic() + timeout
        while not done_event.wait(0.05):
            if self._epoch != epoch0 or self._stop_event.is_set():
                return None
            if time.monotonic() >= deadline:
                logger.warning(f"edge-tts timeout ({timeout}s) — ข้ามข้อความนี้")
                if self.on_status is not None:
                    self.on_status(f"⚠️ edge-tts ค้าง {timeout}s → ข้ามข้อความ")
                return None
        if "error" in result:
            if self.on_status is not None:
                self.on_status(f"❌ TTS: {result['error']}")
            return None
        return result.get("data")

    def _resolve_edge_voice_name(self, fallback_voice: str) -> str:
        """แปลง edge_voice config ("premwadee"/"niwat") → edge-tts voice id

        ★ fallback_voice = voice ที่ pipeline เลือกไว้แล้ว (เช่น multilang voice)
          ถ้า config.edge_voice ว่าง → ใช้ fallback
        """
        edge_voice = getattr(self.config, "edge_voice", "premwadee")
        # ★ map config value → edge-tts voice id
        voice_map = {
            "premwadee": "th-TH-PremwadeeNeural",
            "niwat": "th-TH-NiwatNeural",
        }
        # ★ ถ้า multilang → ใช้ fallback (ภาษา-specific voice)
        if getattr(self.config, "multilang_enabled", False):
            return fallback_voice
        # ★ default → ใช้ edge_voice จาก config (user เลือกชาย/หญิง)
        return voice_map.get(edge_voice, fallback_voice)

    def _speak_name(self, author: str) -> str:
        """ชื่อที่จะอ่านออกเสียง — ชื่อที่ตั้งเองใน User Manager ถ้ามี ไม่งั้นชื่อเดิม"""
        fn = self.name_resolver
        if fn is not None:
            try:
                name = fn(author)
                if name and str(name).strip():
                    return str(name).strip()
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"name_resolver failed: {exc}")
        return author

    def _build_speak_text(self, msg: ChatMessage) -> str:
        """ประกอบข้อความสำหรับ TTS (ตัวที่ส่งเข้า engine + ใช้ตรวจภาษา/ความยาว)

        โหมดอ่านชื่อ (read_author) + มีข้อความ:
          คืนเฉพาะ "ข้อความ" แล้วเก็บชื่อไว้ใน msg.extra["_intro_name"] — เสียง "ชื่อ [หยุด 0.5s] พูดว่า
          [หยุด 0.5s]" ถูกประกอบแยกใน _prepend_intro (ให้หยุดคั่นได้จริง + ตรวจภาษา/emote จากข้อความจริง
          ไม่ปนกับชื่อ)
        """
        if msg.extra is None:
            msg.extra = {}
        msg.extra.pop("_intro_name", None)
        msg.extra.pop("_intro_done", None)
        # events พิเศษ — msg.text ถูก normalize แล้ว (มี author อยู่ใน text)
        # ไม่ต้องเพิ่ม author ซ้ำ
        if msg.event != "message" and msg.event != "system" and msg.text.strip():
            text = msg.text
            # ★ apply pronunciation (แก้การออกเสียง) — ส่ง TTS เท่านั้น ไม่กระทบแชท
            if self._filter is not None:
                text = self._filter.apply_pronunciation(text)
            return text

        def _pron(t: str) -> str:
            # ★ apply pronunciation (แก้การออกเสียง) — ส่ง TTS เท่านั้น ไม่กระทบแชท
            if self._filter is not None and t:
                try:
                    return self._filter.apply_pronunciation(t)
                except Exception:  # noqa: BLE001
                    return t
            return t

        name = _pron(self._speak_name(msg.author)) if self.config.read_author else ""
        comment = _pron(msg.text) if self.config.read_message else ""
        if name.strip() and comment.strip():
            msg.extra["_intro_name"] = name.strip()
            return comment
        return name if name.strip() else comment

    # ------------------------------------------------------------------ #
    # Intro: "{ชื่อ} [หยุด] พูดว่า [หยุด] {ข้อความ}" — ประกอบระดับเสียง (ทุก engine ใช้ร่วมกัน)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _trim_silence(audio: np.ndarray, lead: bool = True, tail: bool = True,
                      threshold: float = 0.01, pad_sec: float = 0.005, sr: int = 44100) -> np.ndarray:
        """ตัดความเงียบหัว/ท้าย (เหลือ pad นิดเดียว) — ให้ช่วงหยุด 0.5 วินาทีที่ใส่เอง เป็น 0.5 วินาทีจริง
        ไม่ถูกบวกด้วยความเงียบตามธรรมชาติของ engine"""
        if audio is None or len(audio) == 0:
            return audio
        idx = np.flatnonzero(np.abs(audio) >= threshold)
        if idx.size == 0:
            return audio
        pad = int(pad_sec * sr)
        start = max(0, int(idx[0]) - pad) if lead else 0
        end = min(len(audio), int(idx[-1]) + 1 + pad) if tail else len(audio)
        return audio[start:end]

    def _intro_edge_voice(self, text: str, kind: str) -> str:
        """edge voice ของท่อนนำ — "พูดว่า" = เสียงไทยเสมอ / ชื่อ = ตามภาษาของชื่อเมื่อเปิด multilang"""
        from language_detect import VOICE_BY_LANG, detect_language
        thai = VOICE_BY_LANG.get("th", "th-TH-PremwadeeNeural")
        voice = self._resolve_edge_voice_name(thai)   # multilang → ตาม thai ที่ส่งไป / ปกติ → edge_voice ที่ผู้ใช้เลือก
        if kind == "name" and getattr(self.config, "multilang_enabled", False):
            lang = detect_language(text)
            if lang in VOICE_BY_LANG and lang != "th":
                voice = VOICE_BY_LANG[lang]
        return voice

    def _intro_parts(self, msg: ChatMessage) -> list:
        """[(ข้อความ, kind)] ของท่อนนำที่ต้องมี — [] = ไม่ใช่โหมดอ่านชื่อ"""
        name = (msg.extra or {}).get("_intro_name")
        if not name:
            return []
        parts = [(name, "name")]
        word = str(getattr(self.config, "intro_word", "พูดว่า") or "").strip()
        if word:
            parts.append((word, "word"))
        return parts

    def _intro_key(self, text: str, kind: str, rate: int, volume: int, pitch: int) -> tuple:
        try:
            voice = self._intro_edge_voice(text, kind)
        except Exception:  # noqa: BLE001
            voice = "th-TH-PremwadeeNeural"
        return (voice, int(rate), int(pitch), int(volume), text)

    def _intro_cache_get(self, key: tuple) -> Optional[np.ndarray]:
        with self._intro_lock:
            cached = self._intro_cache.get(key)
            if cached is not None:
                self._intro_cache.move_to_end(key)
            return cached

    def _intro_cache_put(self, key: tuple, audio: np.ndarray) -> None:
        with self._intro_lock:
            self._intro_cache[key] = audio
            while len(self._intro_cache) > 64:
                self._intro_cache.popitem(last=False)

    def _synth_intro_part(self, text: str, kind: str,
                          rate: int, volume: int, pitch: int) -> Optional[np.ndarray]:
        """synth ท่อนสั้น 1 ท่อน (ชื่อ / "พูดว่า") → float32 mono 44100Hz ที่ตัดเงียบหัวท้ายแล้ว (None = ทำไม่ได้)
        มี cache — ชื่อ/คำเดิมไม่ต้อง synth ซ้ำทุกข้อความ"""
        key = self._intro_key(text, kind, rate, volume, pitch)
        cached = self._intro_cache_get(key)
        if cached is not None:
            return cached

        try:
            edge_voice = self._intro_edge_voice(text, kind)
        except Exception:  # noqa: BLE001
            edge_voice = "th-TH-PremwadeeNeural"
        mp3 = self._synth_sync(TTSParams(
            text=text, voice=edge_voice, rate=f"{rate:+d}%",
            volume=f"{volume:+d}%", pitch=f"{pitch:+d}Hz"))
        audio = self._decode_mp3(mp3) if mp3 else None
        if audio is None or len(audio) == 0:
            return None
        audio = np.asarray(self._trim_silence(audio), dtype=np.float32)
        self._intro_cache_put(key, audio)
        return audio

    def _start_intro_prefetch(self, msg: ChatMessage, rate: int, volume: int, pitch: int) -> list:
        """เริ่ม synth ท่อนนำที่ยังไม่มีใน cache ขนานกับการ synth ข้อความหลัก (คืน threads)
        — ใช้ตอนทำแบบทีละท่อน (multilang ต่างภาษา ฯลฯ) ที่ส่งเป็น request เดียวไม่ได้"""
        threads = []
        for text, kind in self._intro_parts(msg):
            if self._intro_cache_get(self._intro_key(text, kind, rate, volume, pitch)) is not None:
                continue

            def _job(t=text, k=kind):
                try:
                    self._synth_intro_part(t, k, rate, volume, pitch)
                except Exception as exc:  # noqa: BLE001
                    logger.debug(f"intro prefetch failed ({k}): {exc}")
            th = threading.Thread(target=_job, name="IntroPrefetch", daemon=True)
            th.start()
            threads.append(th)
        return threads

    # ── edge-tts: ประโยคเดียว "ชื่อ⏎พูดว่า⏎ข้อความ" ใน request เดียว แล้วปรับช่วงหยุดเป็น 0.5s เป๊ะ ──
    def _single_pass_text(self, msg: ChatMessage, comment: str, edge_voice_name: str) -> Optional[str]:
        """ข้อความสำหรับ edge-tts แบบ request เดียว (None = ทำแบบนี้ไม่ได้ ให้ต่อทีละท่อน)

        edge-tts ตีความ "\n" เป็นรอยต่อประโยค แล้วเว้นช่วงหยุด ~1.0s สม่ำเสมอ (ทดสอบจริง 3/3) — เราไม่ต้องพึ่งค่านั้น:
        ตรวจหาช่วงเงียบแล้วปรับให้เป็น intro_gap เป๊ะใน _normalize_intro_pauses
        ★ ใช้ได้เมื่อทุกท่อนใช้ voice เดียวกัน (ปกติ = เสียงไทยที่ผู้ใช้เลือก) — multilang ที่ข้อความเป็นภาษาอื่น
          ต้องแยก voice → ทำทีละท่อน"""
        parts = self._intro_parts(msg)
        if not parts or not comment.strip():
            return None
        try:
            if any(self._intro_edge_voice(t, k) != edge_voice_name for t, k in parts):
                return None
        except Exception:  # noqa: BLE001
            return None

        def _one_line(t: str) -> str:
            return re.sub(r"\s*[\r\n]+\s*", " ", t).strip()
        return "\n".join([_one_line(t) for t, _k in parts] + [_one_line(comment)])

    @staticmethod
    def _normalize_intro_pauses(audio: np.ndarray, expected: int, gap_sec: float,
                                sr: int = 44100) -> Optional[np.ndarray]:
        """หาช่วงเงียบยาว (≥0.55s) "ภายใน" เสียงพูด ตัวแรกๆ จำนวน expected ช่วง แล้วแทนด้วยความเงียบ gap_sec เป๊ะ
        (ตัดความเงียบหน้าสุดทิ้งด้วย) — ไม่เจอครบ/ผิดปกติ → None (caller ถอยไปทำทีละท่อน)"""
        if audio is None or len(audio) == 0 or expected <= 0:
            return None
        quiet = (np.abs(audio) < 0.012)
        loud = np.flatnonzero(~quiet)
        if loud.size == 0:
            return None
        first_speech, last_speech = int(loud[0]), int(loud[-1])
        edges = np.diff(np.concatenate(([0], quiet.astype(np.int8), [0])))
        starts, ends = np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)
        runs = [(int(s), int(e)) for s, e in zip(starts, ends)
                if s > first_speech and e <= last_speech and (e - s) >= int(0.55 * sr)]
        if len(runs) < expected:
            return None
        runs = runs[:expected]
        if any((e - s) > int(2.5 * sr) for s, e in runs):
            return None
        gap = np.zeros(int(sr * max(0.0, gap_sec)), dtype=np.float32)
        pieces, pos = [], first_speech
        for s, e in runs:
            pieces.append(audio[pos:s])
            pieces.append(gap)
            pos = e
        pieces.append(audio[pos:])
        return np.concatenate(pieces).astype(np.float32, copy=False)

    def _prepend_intro(self, audio_np: np.ndarray, msg: ChatMessage,
                       rate: int, volume: int, pitch: int, prefetch: Optional[list] = None) -> np.ndarray:
        """ต่อ [ชื่อ][หยุด][พูดว่า][หยุด] หน้าเสียงข้อความ — ไม่มี _intro_name / ทำไปแล้ว(single-pass) = คืนเดิม
        ชื่อสังเคราะห์ไม่ได้ → ไม่ใส่ intro เลย (อ่านแต่ข้อความ ดีกว่าได้ "พูดว่า…" ลอยๆ)"""
        parts = self._intro_parts(msg)
        if not parts or (msg.extra or {}).get("_intro_done") or audio_np is None or len(audio_np) == 0:
            return audio_np
        for th in (prefetch or []):   # รอท่อนที่ synth ขนานไว้ให้เสร็จ (ส่วนใหญ่เสร็จไปแล้วตอนข้อความหลักเสร็จ)
            th.join(timeout=35)
        try:
            sr = 44100
            gap = np.zeros(int(sr * max(0.0, float(getattr(self.config, "intro_gap", 0.5)))), dtype=np.float32)
            name, _k = parts[0]
            name_np = self._synth_intro_part(name, "name", rate, volume, pitch)
            if name_np is None:
                logger.info(f"intro: synth ชื่อไม่ได้ ({name!r}) → อ่านแต่ข้อความ")
                return audio_np
            pieces = [name_np, gap]
            if len(parts) > 1:
                word_np = self._synth_intro_part(parts[1][0], "word", rate, volume, pitch)
                if word_np is not None:
                    pieces += [word_np, gap]
            pieces.append(self._trim_silence(audio_np, tail=False))
            return np.concatenate(pieces).astype(np.float32, copy=False)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"intro failed ({exc}) → อ่านแต่ข้อความ")
            return audio_np

    def _synth_mixed_voice(self, text: str, rate: int, volume: int, pitch: int) -> Optional[np.ndarray]:
        """Mixed Voice — แยกข้อความตามภาษา → TTS แต่ละ segment → concat

        ตัวอย่าง: "นายลองไปเก็บ 雫石 มาใช้ก่อนนะ"
        → seg1 "นายลองไปเก็บ" (Premwadee th-TH)
        → seg2 "雫石" (Nanami ja-JP)
        → seg3 "มาใช้ก่อนนะ" (Premwadee th-TH)
        → concat ด้วย gap 50ms (ตัด trailing silence ของแต่ละ segment)

        Returns float32 numpy mono 44100Hz หรือ None ถ้า fail
        """
        from language_detect import VOICE_BY_LANG, _char_lang

        # ── 1. แยก text เป็น segments ตามภาษา ──
        segments = []  # [(text, lang), ...]
        current_text = ""
        current_lang = None
        for ch in text:
            lang = _char_lang(ch)
            # อักขระที่ไม่ใช่ภาษา (เลข, วรรคตอน, emoji, space) → ต่อเข้า segment ปัจจุบัน
            if lang is None:
                current_text += ch
                continue
            if current_lang is None:
                current_lang = lang
                current_text += ch
            elif lang == current_lang:
                current_text += ch
            else:
                # เปลี่ยนภาษา → push segment เดิม + เริ่มใหม่
                if current_text.strip():
                    segments.append((current_text.strip(), current_lang))
                current_text = ch
                current_lang = lang
        # push segment สุดท้าย
        if current_text.strip():
            segments.append((current_text.strip(), current_lang))

        # ถ้ามีแค่ 1 segment → ไม่ต้องใช้ mixed voice
        # แต่ถ้าเป็นภาษาต่างประเทศ (ไม่ใช่ไทย) → ต้องใช้ voice ของภาษานั้น
        # ไม่งั้น fallback ไป Premwadee → อ่านต่างภาษาไม่ได้ → error "No audio"
        if len(segments) <= 1:
            if segments and segments[0][1] != "th":
                # ภาษาเดียวที่ไม่ใช่ไทย → synth ด้วย voice ของภาษานั้น
                seg_text, seg_lang = segments[0]
                voice = VOICE_BY_LANG.get(seg_lang, "th-TH-PremwadeeNeural")
                tts_params = TTSParams(
                    text=seg_text,
                    voice=voice,
                    rate=f"{rate:+d}%",
                    volume=f"{volume:+d}%",
                    pitch=f"{pitch:+d}Hz",
                )
                mp3_bytes = self._synth_sync(tts_params)
                if mp3_bytes:
                    audio_np = self._decode_mp3(mp3_bytes)
                    if audio_np is not None and len(audio_np) > 0:
                        return audio_np
            return None

        # ── 1b. กรอง segment ที่ภาษาไม่ได้เลือก (เงียบ ไม่อ่าน) ──
        allowed_langs = getattr(self.config, "multilang_langs", ["en", "ja", "ko", "zh", "zh-TW", "fr"])
        # th อ่านได้เสมอ (เป็นภาษาหลัก)
        allowed_langs = list(allowed_langs) + ["th"]
        filtered_segments = []
        for seg_text, seg_lang in segments:
            if seg_lang in allowed_langs:
                filtered_segments.append((seg_text, seg_lang))
            # ภาษาที่ไม่ได้เลือก → skip (เงียบ)
        segments = filtered_segments
        if not segments:
            msg.extra["_tts_skip_reason"] = (
                "ไม่ใช่ภาษาที่ตั้งค่าให้อ่าน (multilang) — ถูกกรองทิ้งทั้งข้อความ"
            )
            return None  # ไม่มีภาษาที่รองรับเลย → เงียบ

        # ── 2. TTS แต่ละ segment ──
        audios = []
        for seg_text, seg_lang in segments:
            voice = VOICE_BY_LANG.get(seg_lang, "th-TH-PremwadeeNeural")
            tts_params = TTSParams(
                text=seg_text,
                voice=voice,
                rate=f"{rate:+d}%",
                volume=f"{volume:+d}%",
                pitch=f"{pitch:+d}Hz",
            )
            mp3_bytes = self._synth_sync(tts_params)
            if not mp3_bytes:
                # segment fail → skip (ไม่ทำลายทั้งประโยค)
                continue
            audio_np = self._decode_mp3(mp3_bytes)
            if audio_np is None or len(audio_np) == 0:
                continue
            # trim trailing silence (ลดช่องว่างระหว่าง segment)
            audio_np = self._trim_trailing_silence(audio_np)
            audios.append(audio_np)

        if not audios:
            return None

        # ── 3. concat ด้วย gap 50ms ──
        if len(audios) == 1:
            return audios[0]
        gap = np.zeros(int(44100 * 0.05), dtype=np.float32)  # 50ms silence
        result = audios[0]
        for audio in audios[1:]:
            result = np.concatenate([result, gap, audio])
        return result

    @staticmethod
    def _trim_trailing_silence(audio: np.ndarray, threshold: float = 0.01) -> np.ndarray:
        """ตัด silence ท้าย audio (ลดช่องว่างระหว่าง segment)

        threshold: amplitude ต่ำกว่านี้ = silence
        """
        if len(audio) == 0:
            return audio
        for i in range(len(audio) - 1, -1, -1):
            if abs(audio[i]) >= threshold:
                return audio[:i + 1]
        return audio  # ทั้งหมดเป็น silence → คืนเดิม

    # ------------------------------------------------------------------ #
    # MP3 decode (with silence/stretch markers)
    # ------------------------------------------------------------------ #
    def _decode_mp3(self, mp3_bytes: bytes) -> Optional[np.ndarray]:
        """decode MP3 → float32 numpy mono 44100Hz

        จัดการ silence markers (ฝังโดย tts_engine)
        """
        parts = split_mp3_with_silence_markers(mp3_bytes)
        audio_chunks: list[np.ndarray] = []

        for kind, data in parts:
            if kind == "audio":
                chunk = self._mp3_to_numpy(data)
                if chunk is not None:
                    audio_chunks.append(chunk)
            elif kind == "silence":
                # data = seconds (float)
                silence = np.zeros(int(44100 * float(data)), dtype=np.float32)
                audio_chunks.append(silence)
            elif kind == "stretch":
                # stretch = time-stretch ส่วนท้ายของ chunk ก่อนหน้า
                # (simplified: แค่เพิ่ม silence ตามจำนวน เพื่อหลีกเลี่ยง phase artifact)
                silence = np.zeros(int(44100 * float(data)), dtype=np.float32)
                audio_chunks.append(silence)

        if not audio_chunks:
            return None
        return np.concatenate(audio_chunks)

    def _mp3_to_numpy(self, mp3_bytes: bytes) -> Optional[np.ndarray]:
        """decode MP3 bytes → float32 mono numpy"""
        try:
            import subprocess
            import tempfile

            # ใช้ ffmpeg decode MP3 → WAV (raw) แล้วอ่านด้วย soundfile
            tmp_mp3 = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            tmp_wav = tmp_mp3.name.replace(".mp3", ".wav")
            tmp_mp3.write(mp3_bytes)
            tmp_mp3.close()
            try:
                ffmpeg = self._ffmpeg_path()
                # CREATE_NO_WINDOW — กัน console ของ ffmpeg เด้งขึ้นมา (สำคัญมากตอนเล่นเกม)
                _no_window = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
                subprocess.run(
                    [ffmpeg, "-y", "-i", tmp_mp3.name, "-ar", "44100",
                     "-ac", "1", "-f", "wav", tmp_wav],
                    check=True,
                    capture_output=True,
                    timeout=10,
                    creationflags=_no_window,
                )
                import soundfile as sf

                audio, _sr = sf.read(tmp_wav, dtype="float32", always_2d=False)
                if audio.ndim == 2:
                    audio = audio.mean(axis=1)
                return audio
            finally:
                for p in (tmp_mp3.name, tmp_wav):
                    try:
                        os.unlink(p)
                    except OSError:
                        pass
        except Exception:
            return None

    @staticmethod
    def _ffmpeg_path() -> str:
        """หา ffmpeg.exe — รองรับ PyInstaller frozen mode

        ลำดับค้นหา:
          1. ข้าง exe (sys.executable dir) — สำหรับ build
          2. ข้าง script (__file__ dir) — สำหรับ dev
          3. ใน _MEIPASS (PyInstaller onefile)
          4. fallback "ffmpeg" บน PATH
        """
        import sys

        # 1. ข้าง exe (frozen mode)
        if getattr(sys, "frozen", False):
            exe_dir = os.path.dirname(sys.executable)
            p = os.path.join(exe_dir, "ffmpeg.exe")
            if os.path.exists(p):
                return p
            # 3. ใน _MEIPASS (onefile bundle)
            meipass = getattr(sys, "_MEIPASS", None)
            if meipass:
                p = os.path.join(meipass, "ffmpeg.exe")
                if os.path.exists(p):
                    return p

        # 2. ข้าง script (dev mode)
        local = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "ffmpeg.exe"
        )
        if os.path.exists(local):
            return local

        return "ffmpeg"  # หวังว่าจะอยู่ใน PATH
