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
from collections import deque
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
    # ★ TTS engine: "edge" (edge-tts online) | "omnivoice" (offline, RTX only)
    tts_engine: str = "edge"
    omnivoice_voice: str = "female"  # "male" | "female" | "child" | "auto"
    edge_voice: str = "premwadee"    # "premwadee" | "niwat"
    # ★ OmniVoice short word policy — คำเดียวสั้นกว่า min_length → ไม่อ่าน
    #   แต่ถ้าอยู่ใน whitelist → อ่าน (ยกเว้น)
    omnivoice_skip_enabled: bool = True
    omnivoice_skip_min_length: int = 3
    omnivoice_short_whitelist: list = field(default_factory=lambda: ["ได้", "มี", "ไป", "กิน", "ดี", "ใช่"])
    read_author: bool = True  # อ่านชื่อผู้แชทก่อน
    read_message: bool = True  # อ่านข้อความ
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
    max_queue: int = 20  # ถ้าเกิน → drop ข้อความเก่า
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
        omnivoice_engine=None,  # ★ OmniVoiceEngine instance (optional — None = ใช้ edge-tts อย่างเดียว)
    ) -> None:
        self.tts = tts_engine
        self.player = audio_player
        self.config = config or PipelineConfig()
        self.omnivoice = omnivoice_engine  # ★ None ถ้า Lite build หรือยังไม่ได้โหลด

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

        # callbacks (UI hook)
        self.on_status: Optional[Callable[[str], None]] = None
        self.on_dropped: Optional[Callable[[ChatMessage], None]] = None
        # เรียกเมื่อข้อความถูกแปล (หลัง _maybe_translate สำเร็จ) — UI hook เพื่อ re-render row
        self.on_translated: Optional[Callable[[ChatMessage], None]] = None

    # ------------------------------------------------------------------ #
    # Wiring
    # ------------------------------------------------------------------ #
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

    def stop(self) -> None:
        if not self._is_running:
            return
        self._is_running = False
        self._stop_event.set()
        # wake both workers
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
        self._compute_thread = None
        self._play_thread = None

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
        """ตรวจ + แปลข้อความเป็นไทย — คืน (translated_text, source_lang) หรือ (None, None)

        Logic:
        1. force_translate_users → บังคับแปลทุกข้อความ (ข้าม history check)
        2. detect language → ถ้าเป็นไทยอยู่แล้ว → skip (ยกเว่าน force)
        3. History check — ถ้า user เคยแชทภาษาไทย ≥3 ครั้ง → คนไทย → skip
        4. ถ้าภาษาอยู่ใน auto_translate_langs → translate
        """
        import logging
        _log = logging.getLogger(__name__)
        try:
            from language_detect import detect_language
            src_lang = detect_language(msg.text)
            config = self.config
            # 1. force_translate_users → บังคับแปล (ข้ามทุก check)
            force_users = getattr(config, "force_translate_users", [])
            is_forced = msg.author.lower() in [u.lower() for u in force_users]
            if not is_forced:
                # ถ้าเป็นไทยอยู่แล้ว → skip
                if src_lang == "th":
                    return (None, None)
                # ถ้าไม่ใช่ภาษาที่ต้องการแปล → skip
                target_langs = getattr(config, "auto_translate_langs", [])
                if src_lang not in target_langs:
                    return (None, None)
                # History check — ถ้า user เคยแชทภาษาไทย ≥3 ครั้ง → คนไทย → skip
                if self._is_thai_speaker(msg.author):
                    return (None, None)
            # Translate
            from translator import Translator
            provider = getattr(config, "auto_translate_provider", "google")
            api_key = getattr(config, "auto_translate_api_key", "")
            host = getattr(config, "auto_translate_host", "")
            target = getattr(config, "auto_translate_target_lang", "th")
            langs = getattr(config, "auto_translate_langs", [])
            t = Translator(provider=provider, api_key=api_key, host=host,
                           target_lang=target, supported_langs=langs)
            # force users → source_lang = "auto" (ให้ translator detect เอง)
            result = t.translate(msg.text, source_lang="auto" if is_forced else src_lang)
            if result:
                return (result, src_lang if not is_forced else "auto")
            # แปล fail → คืน src_lang ด้วย เพื่อให้ enqueue ตัดสินใจ skip ได้
            return (None, src_lang)
        except Exception as exc:
            _log.warning("auto_translate error: %s", exc)
            return (None, None)

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
            return

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
                return
            filtered = self._filter.filter_text(msg.text)
            if filtered is None:
                return
            msg.text = filtered

        # 2.5) Auto Translate (ถ้าเปิด) — แปลเป็นไทยก่อน TTS + ผ่าน replace หลังแปล
        if getattr(self.config, "auto_translate_enabled", False) and msg.text:
            translated, src_lang = self._maybe_translate(msg)
            if translated is not None and translated != msg.text:
                original_text = msg.text
                msg.extra["translated"] = True
                msg.extra["original_text"] = original_text
                msg.extra["source_lang"] = src_lang
                msg.extra["translated_text"] = translated
                # ใช้ข้อความแปลสำหรับ TTS
                msg.text = translated
                # ★ ไม่ replace หลังแปล (โหมดแปลไม่ใช้ Replace — เพราะแปลเป็นไทยหมดแล้ว)
                # notify UI เพื่อ re-render row (แสดงคำแปลทันทีหลังแปลเสร็จ)
                if self.on_translated is not None:
                    try:
                        self.on_translated(msg)
                    except Exception:
                        pass
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
                    return  # ไม่ enqueue → ไม่อ่าน

        # 3) per-author temp-ban check (rate limit penalty)
        author_lower = msg.author.lower()
        unban_at = self._user_temp_banned.get(author_lower, 0)
        if now < unban_at:
            self.skipped_spam += 1
            return

        # 4) content filters — url / code block / ยาวผิดปกติ
        if msg.text:
            if self.config.filter_urls and _URL_RE.search(msg.text):
                self.skipped_spam += 1
                return
            if self.config.filter_code_blocks and _CODE_RE.search(msg.text):
                self.skipped_spam += 1
                return
            if len(msg.text) > self.config.max_msg_length:
                self.skipped_spam += 1
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
                return

        # ───── END SPAM PROTECTION ─────

        # 8) throttle — ถ้า queue เต็ม → drop เก่า
        if self._q.qsize() >= self.config.max_queue:
            try:
                self._q.get_nowait()
                self.dropped += 1
                if self.on_dropped is not None:
                    self.on_dropped(msg)
            except queue.Empty:
                pass

        # 9) dedupe — ข้ามข้อความซ้ำภายใน window (author + text + event)
        h = self._hash(msg)
        cutoff = now - self.config.dedupe_window
        # ล้าง hash เก่า
        while self._recent_hashes and self._recent_hashes[0][1] < cutoff:
            self._recent_hashes.popleft()
        if any(hh == h for hh, _ in self._recent_hashes):
            self.skipped_dedupe += 1
            return
        self._recent_hashes.append((h, now))

        # 10) author cooldown — กัน user เดียวพิมพ์รัวๆ (distinct from rate-limit ban)
        last = self._author_last_time.get(author_lower, 0)
        if now - last < self.config.author_cooldown:
            self.skipped_author += 1
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

        self._q.put(msg)

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

    def _load_sound_to_array(self, mp3_path: str) -> Optional[tuple[np.ndarray, int]]:
        """โหลดไฟล์เสียง → numpy array (สำหรับ push เข้า ready_q เล่นต่อจาก TTS)

        ใช้สำหรับ secret code sound — เล่นหลังจาก TTS จบ
        คืน (audio_np, sample_rate) หรือ None ถ้าโหลดไม่ได้
        """
        try:
            import soundfile as sf

            audio, sr = sf.read(mp3_path, dtype="float32", always_2d=False)
            if audio.ndim == 2:
                audio = audio.mean(axis=1)
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

            # ───── MUTE: ถ้าปิดเสียง → ทิ้งข้อความ ไม่ synthesize (ประหยัด CPU/GPU) ─────
            if self.config.tts_muted:
                logger.debug("TTS muted → skip message")
                continue

            try:
                result = self._compute_one(msg)
                if result is not None:
                    # แนบ per-platform volume offset (ถ้ามี)
                    vol_offset = 0
                    if msg.extra:
                        vol_offset = msg.extra.get("_tts_vol_offset", 0)
                    # ★ push (audio_np, sr, vol_offset, author) เข้า ready queue
                    #   author ใช้ตอน purge_blocked_user (ล้างคิวของ user ที่บล็อก)
                    self._ready_q.put((result[0], result[1], vol_offset, msg.author))
                # secret code: เล่นเสียง code หลังจาก TTS จบ (ถ้ามี + ไม่ได้ปิด code sound)
                pending = (msg.extra or {}).get("_pending_code_sound")
                if pending and not getattr(self.config, "code_sound_muted", False):
                    mp3_path, vol = pending
                    # synthesize code sound → push ต่อจาก TTS
                    code_audio = self._load_sound_to_array(mp3_path)
                    if code_audio is not None:
                        self._ready_q.put(code_audio)
            except Exception as exc:  # noqa: BLE001
                logger.error(f"TTS error in compute_loop: {exc}", exc_info=True)
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

    def _play_loop(self) -> None:
        """pop จาก ready queue → load + play + wait until done"""
        while not self._stop_event.is_set():
            item = self._ready_q.get()
            if item is None:
                break  # shutdown signal
            # ★ tuple: (audio_np, sr, vol_offset, author) — author ใช้ตอน purge_blocked_user
            audio_np = sr = vol_offset = 0
            play_author = ''
            if isinstance(item, tuple):
                if len(item) >= 4:
                    audio_np, sr, vol_offset, play_author = item
                elif len(item) == 3:
                    audio_np, sr, vol_offset = item
                elif len(item) == 2:
                    audio_np, sr = item

            # ★ track current playing author (สำหรับ purge_blocked_user)
            self._current_playing_author = play_author

            try:
                # per-platform volume: vol_offset = -50..+50 (% change)
                # ใช้ numpy multiply ที่ audio data เพื่อรองรับทั้งลดและเพิ่ม (เกิน 1.0 ได้)
                if vol_offset:
                    gain = max(0.0, 1.0 + vol_offset / 100.0)
                    audio_np = np.clip(audio_np * gain, -1.0, 1.0)
                self.player.load_audio(audio_np.astype(np.float32), sr)
                # ★ master volume (0-100%) — รองรับทุก engine (edge-tts/OmniVoice/RVC)
                #   config.volume = 0..100 → player volume 0.0..1.0
                master_vol = max(0.0, min(1.0, getattr(self.config, 'volume', 100) / 100.0))
                self.player.set_volume(master_vol)
                self.player.play()
                # รอจนเล่นจบ — ขณะนี้ compute worker ทำข้อความถัดไปอยู่
                # ★ ปรับจาก 50ms → 10ms (ลด gap ระหว่างจบเสียงเก่า + เริ่มเสียงใหม่)
                # เดิม: sleep(0.05) → ใหม่: sleep(0.01)
                while self.player.is_playing() and not self._stop_event.is_set():
                    time.sleep(0.01)
            except Exception as exc:  # noqa: BLE001
                if self.on_status is not None:
                    self.on_status(f"❌ playback error: {exc}")

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
        # ── OmniVoice short word policy ──
        # ★ คำเดียวสั้นกว่า min_length → ไม่อ่าน (default)
        #   แต่ถ้าอยู่ใน whitelist → อ่าน (ยกเว้น)
        #   "อ๋อ" (คำเดียว สั้น) → skip / "อ๋อ แบบนี้" (มี space) → อ่านปกติ
        #
        # ★★ สำคัญ: ตรวจ Replace ก่อน skip!
        #   ถ้า user ตั้ง Replace "อ๋อ" → "อ๋อเข้าใจแล้ว" ต้องอ่าน (เพราะเปลี่ยนคำใหม่แล้ว)
        #   จึง apply_pronunciation ก่อน แล้วค่อยเช็ค skip กับข้อความที่แปลงแล้ว
        engine_choice = getattr(self.config, "tts_engine", "edge")
        if engine_choice == "omnivoice" and getattr(self.config, "omnivoice_skip_enabled", True):
            logger.debug(f"omni skip check: enabled={getattr(self.config, 'omnivoice_skip_enabled', True)}, min_len={getattr(self.config, 'omnivoice_skip_min_length', 0)}")
            # ★ apply Replace (pronunciation) ก่อน — ถ้าเปลี่ยนคำแล้ว ใช้ข้อความใหม่
            check_text = (msg.text or "").strip()
            if self._filter is not None and check_text:
                try:
                    check_text = self._filter.apply_pronunciation(check_text).strip()
                except Exception:
                    pass
            if check_text and " " not in check_text:
                min_len = getattr(self.config, "omnivoice_skip_min_length", 0)
                if min_len > 0 and len(check_text) < min_len:
                    # ★ เช็ค whitelist ก่อน fallback (เทียบกับข้อความที่แปลงแล้ว)
                    whitelist = getattr(self.config, "omnivoice_short_whitelist", [])
                    if whitelist and check_text.lower() in (w.lower() for w in whitelist):
                        pass  # อยู่ใน whitelist → OmniVoice อ่าน
                    else:
                        # ★ คำสั้น → สลับไป Azure (edge-tts) แทน OmniVoice
                        logger.info(f"OmniVoice short word → Azure fallback: {check_text!r} (len={len(check_text)} < {min_len})")
                        engine_choice = "edge"  # fallback ไป edge-tts
        # ประกอบข้อความสำหรับอ่าน
        text = self._build_speak_text(msg)
        if not text.strip():
            return None

        # ── Heuristic: ข้ามถ้าข้อความดูเหมือน emote code (ไม่ใช่คำพูด) ──
        # กรณี: emote ที่ไม่ได้อยู่ใน Twitch tag / third-party list → เหลือเป็น code ใน text
        # ลักษณะ: คำเดียว + มี camelCase หรือตัวเลขผสม + ไม่ใช่คำไทย + ไม่ใช่ URL
        if self._looks_like_emote_code(text):
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
        # Mixed Voice ใช้ได้เฉพาะโหมด multilang (ไม่ใช่โหมดแปล)
        _use_mixed = (getattr(self.config, "mixed_voice_enabled", False)
                      and getattr(self.config, "multilang_enabled", False)
                      and not getattr(self.config, "auto_translate_enabled", False))
        if _use_mixed:
            # ── Mixed Voice: แยก segment ตามภาษา → TTS แต่ละ segment → concat ──
            audio_np = self._synth_mixed_voice(text, effective_rate, viewer_volume, viewer_pitch)
            if audio_np is not None:
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
            # RVC + ไม่เปิด multilang → base voice ตาม tts_engine
            # ★ OmniVoice อ่านได้ทุกภาษา → ไม่ต้อง skip ต่างภาษา
            if getattr(self.config, "tts_engine", "edge") == "omnivoice":
                voice = ""  # ★ OmniVoice path ไม่ใช้ voice variable (ใช้ instruct แทน)
            else:
                # edge-tts base → ใช้ Premwadee เป็น base + skip ต่างภาษา (Premwadee อ่านไม่ได้)
                voice = "th-TH-PremwadeeNeural"
                from language_detect import detect_language
                _text_lang = detect_language(text)
                if _text_lang not in ("th", "en"):
                    return None  # Premwadee อ่านต่างภาษาไม่ได้ → skip
        elif self.config.multilang_enabled:
            # เปิด multilang → detect ภาษาแล้วเลือก voice (RVC จะทับทับทีหลังถ้ามี)
            from language_detect import VOICE_BY_LANG, detect_language

            lang = detect_language(text)
            # ภาษาที่ไม่รู้จัก (ฮินดี/อาหรับ/รัสเซีย) → ไม่มี voice → skip (กัน error "No audio")
            if lang not in VOICE_BY_LANG:
                return None
            voice = VOICE_BY_LANG.get(lang, self.config.voice)
        else:
            # default — base voice เท่านั้น (ไม่มี RVC + ไม่มี multilang)
            # ★ ใช้ edge_voice (premwadee/niwat) — ไม่ใช่ config.voice (อาจเป็น RVC model id ที่ยังไม่ได้โหลด)
            # guard: ถ้าเป็นภาษาที่ Premwadee/Niwat อ่านไม่ได้ (unknown/hindi/arabic/...) → skip
            from language_detect import detect_language
            _def_lang = detect_language(text)
            if _def_lang not in ("th", "en"):
                return None
            # ★ resolve เป็น edge-tts voice id จริง (premwadee → th-TH-PremwadeeNeural)
            _ev = getattr(self.config, "edge_voice", "premwadee")
            voice = {"premwadee": "th-TH-PremwadeeNeural", "niwat": "th-TH-NiwatNeural"}.get(_ev, "th-TH-PremwadeeNeural")

        # TTS synth — ★ เลือก engine ตาม engine_choice (อาจถูกเปลี่ยนโดย skip logic ข้างบน)
        #   OmniVoice → RVC overlay ได้ (เหมือน edge-tts → RVC)
        #   ★ ไม่อ่านใหม่จาก config — ใช้ค่า engine_choice ที่ skip logic อาจเปลี่ยนไว้
        audio_np = None  # ★ init กัน UnboundLocalError ตอน fallback
        if engine_choice == "omnivoice" and self.omnivoice is not None and self.omnivoice.is_loaded:
            # ── OmniVoice path (offline, zero-shot) ──
            audio_bytes = self._synth_omnivoice_sync(text)
            if not audio_bytes:
                # ★ OmniVoice fail → fallback edge-tts (กันเงียบ)
                engine_choice = "edge"
            else:
                # decode WAV → numpy (OmniVoice ส่งคืน WAV ไม่ใช่ MP3)
                audio_np = self._decode_wav(audio_bytes)
                if audio_np is None or len(audio_np) == 0:
                    engine_choice = "edge"  # fallback
                # ★ audio_np พร้อมแล้ว → ไป RVC overlay section (เหมือน edge-tts path)
        if engine_choice != "omnivoice":
            # ── edge-tts path (online) — ใช้ตอนปกติ + fallback ตอน OmniVoice fail ──
            # ★ เลือก edge voice จาก config.edge_voice (premwadee/niwat)
            edge_voice_name = self._resolve_edge_voice_name(voice)
            tts_params = TTSParams(
                text=text,
                voice=edge_voice_name,
                rate=f"{effective_rate:+d}%",
                volume=f"{viewer_volume:+d}%",
                pitch=f"{viewer_pitch:+d}Hz",
            )

            # sync wrapper รอ TTS เสร็จ
            mp3_bytes = self._synth_sync(tts_params)
            if not mp3_bytes:
                # ★ ทั้ง OmniVoice และ edge-tts fail → skip (กันคิวกระจุก)
                logger.warning(f"TTS fail ทั้งคู่ — skip message: {text[:50]!r}")
                return None

            # decode MP3 → numpy (แยก silence/stretch markers)
            audio_np = self._decode_mp3(mp3_bytes)
            if audio_np is None or len(audio_np) == 0:
                logger.warning(f"MP3 decode fail — skip message: {text[:50]!r}")
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

        self.tts.generate(params, on_done, on_error)
        if not done_event.wait(timeout):
            logger.warning(f"edge-tts timeout ({timeout}s) — ข้ามข้อความนี้")
            if self.on_status is not None:
                self.on_status(f"⚠️ edge-tts ค้าง {timeout}s → ข้ามข้อความ")
            return None
        if "error" in result:
            if self.on_status is not None:
                self.on_status(f"❌ TTS: {result['error']}")
            return None
        return result.get("data")

    # ═══ OmniVoice helpers ═══
    def _synth_omnivoice_sync(self, text: str, timeout: float = 15.0) -> Optional[bytes]:
        """เรียก OmniVoice engine แบบ synchronous — ส่งคืน WAV bytes (44100Hz)

        ★ timeout 15s (ปกติใช้ 1-2s) — ถ้าเกินแสดงว่าค้าง → return None → fallback edge-tts
        """
        if not self.omnivoice or not self.omnivoice.is_loaded:
            return None
        done_event = threading.Event()
        result: dict = {}

        def on_done(data: bytes) -> None:
            result["data"] = data
            done_event.set()

        def on_error(err: str) -> None:
            result["error"] = err
            done_event.set()

        # ★ sync instruct + speed จาก config
        #   OmniVoice speed เป็น multiplier (1.0=ปกติ) ส่วน settings.rate เป็น percent (-50..+50)
        #   แปลง: omnivoice_speed = 1.0 + (rate / 100)  →  +50 → 1.5x, 0 → 1.0x, -50 → 0.5x
        self.omnivoice.set_instruct(getattr(self.config, "omnivoice_voice", "female"))
        _cfg_rate = getattr(self.config, "rate", 0)
        if _cfg_rate:
            self.omnivoice.set_speed(1.0 + (_cfg_rate / 100.0))
        else:
            self.omnivoice.set_speed(1.0)
        self.omnivoice.generate(text, on_done, on_error)
        # ★ รอพร้อม timeout — ถ้าเกิน → return None (caller จะ fallback edge-tts)
        if not done_event.wait(timeout):
            logger.warning(f"OmniVoice timeout ({timeout}s) — will fallback to edge-tts")
            if self.on_status is not None:
                self.on_status(f"⚠️ OmniVoice ค้าง {timeout}s → ใช้ edge-tts ชั่วคราว")
            return None
        if "error" in result:
            if self.on_status is not None:
                self.on_status(f"❌ OmniVoice: {result['error']}")
            return None
        return result.get("data")

    def _decode_wav(self, wav_bytes: bytes) -> Optional[np.ndarray]:
        """decode WAV bytes → numpy float32 mono (44100Hz)

        OmniVoice ส่งคืน WAV 16-bit PCM → แปลงเป็น float32
        """
        try:
            import io as _io
            import soundfile as sf
            data, sr = sf.read(_io.BytesIO(wav_bytes), dtype="float32")
            # ★ แปลงเป็น mono ถ้า stereo
            if data.ndim > 1:
                data = data.mean(axis=1)
            return data
        except Exception as e:
            logger.warning(f"WAV decode failed: {e}")
            return None

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

    def _build_speak_text(self, msg: ChatMessage) -> str:
        """ประกอบข้อความสำหรับ TTS + Overlay"""
        # events พิเศษ — msg.text ถูก normalize แล้ว (มี author อยู่ใน text)
        # ไม่ต้องเพิ่ม author ซ้ำ
        if msg.event != "message" and msg.event != "system" and msg.text.strip():
            text = msg.text
            # ★ apply pronunciation (แก้การออกเสียง) — ส่ง TTS เท่านั้น ไม่กระทบแชท
            if self._filter is not None:
                text = self._filter.apply_pronunciation(text)
            return text
        author = msg.author
        # message ปกติ — ประกอบ author + text
        parts = []
        if self.config.read_author:
            parts.append(author)
        if self.config.read_message:
            parts.append(msg.text)
        if not parts:
            return ""
        if len(parts) == 2:
            text = f"{parts[0]}… {parts[1]}"
        else:
            text = parts[0]
        # ★ apply pronunciation (แก้การออกเสียง) — ส่ง TTS เท่านั้น ไม่กระทบแชท
        if self._filter is not None:
            text = self._filter.apply_pronunciation(text)
        return text

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
