"""twitch_bot.py — Twitch Chat Bot (คำสั่งอัตโนมัติ + Timer)

ทำงาน:
1. **คำสั่ง** — เมื่อมีข้อความขึ้นต้นด้วย ! (เช่น !dc) → ส่งคำตอบกลับแชท
2. **Timer** — ส่งข้อความซ้ำตามช่วงเวลาที่ตั้ง (เช่นทุก 10 นาที)

★ cooldown per-command (default 5 วิ) — กัน spam
★ rate limit รวม 20 ข้อความ/30 วิ (Twitch limit) — ใช้ queue + timestamp check
★ ไม่ตอบคำสั่งของตัวเอง (กัน loop)
"""
import logging
import time
import threading
from typing import Callable, Optional

logger = logging.getLogger("twitch_bot")


class TwitchBot:
    """Twitch Chat Bot — ตอบคำสั่ง + timer + event responses

    Args:
        send_callback: callable(text: str) — ฟังก์ชันส่งข้อความไปแชท (TwitchChat.send_message)
        bot_username: username ของ bot (เพื่อไม่ตอบข้อความตัวเอง)
        commands: dict {command: response} เช่น {"!dc": "Discord: ..."}
        timers: list [{"text": "...", "interval_min": 10}]
        event_responses: dict {event_type: response_template}
            event_type: "sub" | "resub" | "bits" | "raid" | "follow"
            response_template: ใช้ {user}, {amount}, {months}, {raid_count}
        cooldown_sec: cooldown per-command (default 5 วิ)
    """

    def __init__(
        self,
        send_callback: Callable[[str], bool],
        bot_username: str = "",
        commands: Optional[dict] = None,
        timers: Optional[list] = None,
        event_responses: Optional[dict] = None,
        events_enabled: bool = True,
        cooldown_sec: int = 5,
        on_bot_response: Optional[Callable[[str], None]] = None,
    ):
        self._send = send_callback
        self._bot_username = (bot_username or "").lower()
        self._commands = commands or {}
        self._timers = timers or []
        self._event_responses = event_responses or {}
        self._events_enabled = events_enabled
        self._cooldown_sec = cooldown_sec
        # ★ callback เมื่อ bot ส่งข้อความ (echo กลับไปแสดงใน Live Chat)
        self._on_bot_response = on_bot_response

        # cooldown tracking: {command: last_trigger_timestamp}
        self._cooldowns: dict[str, float] = {}
        # event cooldown: {event_type: last_trigger} — กัน spam ถ้าหลายคน sub พร้อมกัน
        self._event_cooldowns: dict[str, float] = {}
        self._event_cooldown_sec = 3  # 3 วิระหว่าง event แต่ละประเภท

        # rate limit: เก็บเวลาส่งล่าสุด (Twitch = 20 msg / 30 วิ)
        self._send_times: list[float] = []
        self._rate_lock = threading.Lock()

        # timer state
        self._timer_thread: Optional[threading.Thread] = None
        self._timer_stop = threading.Event()
        self._timer_intervals: dict[str, float] = {}  # {timer_text: next_trigger_time}
        # ★ chat activity counter — นับจำนวนข้อความจากคนอื่น (ไม่นับบอทตัวเอง)
        self._chat_count = 0
        self._chat_count_lock = threading.Lock()
        # ★ timer trigger state — เก็บว่าแต่ละ timer ส่งครั้งล่าสุดเมื่อไหร่ + นับไปกี่ข้อความแล้ว
        self._timer_last_sent: dict[str, float] = {}  # {timer_text: last_sent_timestamp}

        logger.info(f"TwitchBot initialized — {len(self._commands)} commands, "
                    f"{len(self._timers)} timers, {len(self._event_responses)} events")

    # ------------------------------------------------------------------ #
    # Command handling
    # ------------------------------------------------------------------ #
    def update_commands(self, commands: dict):
        """อัปเดตรายการคำสั่ง (เรียกเมื่อ settings เปลี่ยน)"""
        self._commands = commands or {}
        logger.info(f"Bot commands updated — {len(self._commands)} commands")

    def update_event_responses(self, event_responses: dict, events_enabled: bool = True):
        """อัปเดต event responses (เรียกเมื่อ settings เปลี่ยน)"""
        self._event_responses = event_responses or {}
        self._events_enabled = events_enabled
        logger.info(f"Bot event responses updated — {len(self._event_responses)} events "
                    f"(enabled={events_enabled})")

    def handle_event(self, event_type: str, **kwargs):
        """ประมวลผล Twitch event → ส่งข้อความตอบอัตโนมัติ

        Args:
            event_type: "sub" | "resub" | "bits" | "raid" | "follow"
            **kwargs: ข้อมูล event เช่น user="xxx", amount=100, months=3, raid_count=50
        """
        if not self._events_enabled:
            return
        # ★ หา template สำหรับ event นี้
        template = self._event_responses.get(event_type, "")
        if not template:
            return
        # ★ event cooldown (กัน spam ถ้าหลายคน sub พร้อมกัน)
        now = time.time()
        last = self._event_cooldowns.get(event_type, 0)
        if now - last < self._event_cooldown_sec:
            logger.debug(f"Event {event_type} on cooldown")
            return
        self._event_cooldowns[event_type] = now
        # ★ แทน placeholders {user} {amount} {months} {raid_count}
        try:
            response = template.format(**kwargs)
        except (KeyError, ValueError) as e:
            logger.warning(f"Event template error ({event_type}): {e}")
            response = template  # ใช้ template เดิมถ้า placeholder ผิด
        logger.info(f"Bot event {event_type} → sending: {response[:60]}")
        self._rate_limited_send(response)

    def handle_message(self, author: str, text: str):
        """ประมวลผลข้อความเข้า — ถ้าเป็นคำสั่ง → ส่งคำตอบ

        Args:
            author: ชื่อคนส่ง
            text: ข้อความ
        """
        # ★ ตอบข้อความตัวเองได้ (เพื่อให้ทดสอบได้โดยไม่ต้องสมัครบัญชีใหม่)
        #   แต่กัน loop: ถ้า bot_username ตอบคำสั่งเดิม → cooldown จะดักซ้ำอยู่แล้ว

        text = text.strip()
        if not text.startswith("!"):
            return

        # ★ แยก command ออกจาก args (!dc args → !dc)
        cmd_key = text.split()[0].lower() if text.split() else ""
        if not cmd_key:
            return

        # ★ หาคำสั่งใน registry (case-insensitive)
        response = None
        for key, val in self._commands.items():
            if key.lower() == cmd_key:
                response = val
                break

        if not response:
            return

        # ★ cooldown check (กัน spam — คำสั่งเดิมใน 5 วิ จะไม่ตอบซ้ำ)
        now = time.time()
        last = self._cooldowns.get(cmd_key, 0)
        if now - last < self._cooldown_sec:
            logger.debug(f"Command {cmd_key} on cooldown ({self._cooldown_sec - (now - last):.1f}s left)")
            return
        self._cooldowns[cmd_key] = now

        # ★ ส่งคำตอบ (ผ่าน rate-limited send)
        logger.info(f"Bot command {cmd_key} from {author} → sending response")
        self._rate_limited_send(response)

    # ------------------------------------------------------------------ #
    # Rate limiting (Twitch: 20 msg / 30 วิ)
    # ------------------------------------------------------------------ #
    def _rate_limited_send(self, text: str) -> bool:
        """ส่งข้อความโดยเช็ค rate limit (20 msg / 30 วิ)

        ★ ถ้าใกล้ limit → ข้ามข้อความนี้ (ไม่หน่วง — กัน user รอ)
        """
        with self._rate_lock:
            now = time.time()
            # ลบเวลาที่เก่ากว่า 30 วิออก
            self._send_times = [t for t in self._send_times if now - t < 30]
            # ถ้าส่งแล้ว 18 ครั้งใน 30 วิ → skip (เผื่อ 2 ครั้งให้ user)
            if len(self._send_times) >= 18:
                logger.warning(f"Rate limit near (18/30s) — skipping: {text[:50]}")
                return False
            self._send_times.append(now)

        try:
            ok = self._send(text)
            # ★ echo กลับไปแสดงใน Live Chat (ถ้าส่งสำเร็จ + มี callback)
            if ok and self._on_bot_response:
                try:
                    self._on_bot_response(text)
                except Exception as e:
                    logger.debug(f"on_bot_response callback error: {e}")
            return ok
        except Exception as e:
            logger.error(f"Bot send failed: {e}")
            return False

    # ------------------------------------------------------------------ #
    # Timer (ส่งข้อความซ้ำตามช่วงเวลา)
    # ------------------------------------------------------------------ #
    def count_chat_activity(self, author: str = ""):
        """★ นับข้อความเข้า — เรียกทุกครั้งที่มีข้อความจากคน (ไม่ใช่บอทตัวเอง)

        ★ ใช้สำหรับ timer trigger condition (ต้องมีคนแชท N ครั้ง ถึงจะส่ง timer)
        """
        # ★ ไม่นับข้อความของบอทตัวเอง
        if author and author.lower() == self._bot_username:
            return
        with self._chat_count_lock:
            self._chat_count += 1

    def update_timers(self, timers: list):
        """อัปเดตรายการ timer (เรียกเมื่อ settings เปลี่ยน)"""
        self._timers = timers or []
        now = time.time()
        self._timer_intervals = {}
        self._timer_last_sent = {}
        for t in self._timers:
            text = t.get("text", "")
            interval_min = max(1, int(t.get("interval_min", 10)))
            if text:
                self._timer_intervals[text] = now + (interval_min * 60)
                self._timer_last_sent[text] = 0  # ยังไม่เคยส่ง
        logger.info(f"Bot timers updated — {len(self._timers)} timers")

    def start_timers(self):
        """เริ่ม timer thread (เรียกตอน Twitch connect)"""
        if self._timer_thread and self._timer_thread.is_alive():
            return  # รันอยู่แล้ว
        self._timer_stop.clear()
        # ★ init intervals ถ้ายังไม่ได้ตั้ง
        if not self._timer_intervals and self._timers:
            self.update_timers(self._timers)
        self._timer_thread = threading.Thread(
            target=self._timer_loop, name="TwitchBotTimer", daemon=True
        )
        self._timer_thread.start()
        logger.info("Bot timer thread started")

    def stop_timers(self):
        """หยุด timer thread (เรียกตอน Twitch disconnect)"""
        self._timer_stop.set()
        if self._timer_thread and self._timer_thread.is_alive():
            self._timer_thread.join(timeout=3)
        self._timer_thread = None
        self._timer_intervals = {}
        logger.info("Bot timer thread stopped")

    def _timer_loop(self):
        """loop ตรวจ timer ทุก 5 วิ — รองรับ 2 โหมด:
        - interval mode (min_chat_count=0): ส่งทุก N นาที
        - chat_count mode (interval_min=0): ส่งเมื่อมีคนแชท N ครั้ง
        """
        while not self._timer_stop.is_set():
            try:
                now = time.time()
                with self._chat_count_lock:
                    chat_count = self._chat_count
                for timer in list(self._timers):
                    if self._timer_stop.is_set():
                        break
                    text = timer.get("text", "")
                    interval_min = int(timer.get("interval_min", 10))
                    min_chat_count = int(timer.get("min_chat_count", 0))
                    if not text:
                        continue

                    # ★ โหมด 1: interval mode (chat_count=0) → ส่งทุก N นาที
                    if min_chat_count == 0 and interval_min > 0:
                        next_trigger = self._timer_intervals.get(text, 0)
                        if now >= next_trigger:
                            logger.info(f"Timer (interval) trigger: {text[:50]}")
                            self._rate_limited_send(text)
                            self._timer_intervals[text] = now + (interval_min * 60)

                    # ★ โหมด 2: chat_count mode (interval=0) → ส่งเมื่อมีคนแชท N ครั้ง
                    elif interval_min == 0 and min_chat_count > 0:
                        if chat_count >= min_chat_count:
                            logger.info(f"Timer (chat_count) trigger: {text[:50]} "
                                        f"(count={chat_count}, need={min_chat_count})")
                            self._rate_limited_send(text)
                            with self._chat_count_lock:
                                self._chat_count = 0  # reset หลังส่ง

                    # ★ โหมด 3: ทั้งคู่ > 0 → ต้องครบทั้ง 2 เงื่อนไข (สำหรับอนาคต)
                    elif interval_min > 0 and min_chat_count > 0:
                        next_trigger = self._timer_intervals.get(text, 0)
                        if now >= next_trigger and chat_count >= min_chat_count:
                            logger.info(f"Timer (both) trigger: {text[:50]}")
                            self._rate_limited_send(text)
                            self._timer_intervals[text] = now + (interval_min * 60)
                            with self._chat_count_lock:
                                self._chat_count = 0
            except Exception as e:
                logger.error(f"Timer loop error: {e}")
            # ★ check ทุก 5 วิ (เร็วขึ้นเพื่อ chat_count mode ตอบสนองทันที)
            self._timer_stop.wait(5)
