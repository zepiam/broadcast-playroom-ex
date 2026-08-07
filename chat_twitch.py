"""chat_twitch.py — Twitch chat client (anonymous IRC)

เชื่อมต่อ Twitch chat แบบ anonymous (justinfan####) ไม่ต้อง OAuth
อ่าน PRIVMSG (chat ปกติ + bits) และ USERNOTICE (sub/resub/subgift/raid)

การใช้งาน:
    client = TwitchChat(on_message=callback)
    client.connect("channel_name")
    ...
    client.disconnect()

Callback ได้รับ ChatMessage dataclass (ร่วมกับ YouTube client)
"""
from __future__ import annotations

import random
import re
import socket
import ssl
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

# ---------------------------------------------------------------------- #
# Chat event dataclass (ร่วมกับ chat_youtube.py)
# ---------------------------------------------------------------------- #


@dataclass
class ChatMessage:
    """ข้อความแชทจากแพลตฟอร์มใดก็ได้"""

    platform: str  # "twitch" | "youtube"
    author: str  # ชื่อผู้ส่ง (display name)
    text: str  # ข้อความ
    # event type: "message" | "bits" | "sub" | "resub" | "subgift" | "raid"
    event: str = "message"
    # จำนวน (bits หรือยอด donate ในหน่วยเงินถ้ามี)
    amount: Optional[int] = None
    # sub tier 1/2/3 หรือ raid viewers หรือ None
    tier: Optional[int] = None
    # ข้อความระบบ เช่น "Subbed for 12 months!" (ใช้ TTS ได้)
    system_text: Optional[str] = None
    # ของแถม: color, badges ฯลฯ (ไม่ได้ใช้ใน TTS)
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------- #
# Twitch IRC client (anonymous)
# ---------------------------------------------------------------------- #

# regex สำหรับกระชับ space หลายช่องติดกันที่เหลือหลังตัด emote
_MULTI_SPACE_RE = re.compile(r" {2,}")


def _parse_emotes(text: str, emotes_tag: str) -> list:
    """แยก emote list จาก Twitch emotes tag — เก็บ offset ตาม text เดิม (ก่อน strip)

    รูปแบบ emotes_tag: 'id:start-end,start-end/id2:start-end' หรือ '' (ว่าง)
    offset เป็น Unicode code point (Python str index ตรง), end inclusive

    emote_id มี 2 format:
      - ตัวเลข (เก่า): เช่น 25, 302222303
      - string (emotesv2): เช่น emotesv2_2d076ec967d946c8853d24dc4c943d82

    Returns: list of dict [{id, name, start, end}, ...]
      - id: str (emote id สำหรับดึงภาพจาก CDN — เก็บเป็น string ทั้งคู่)
      - name: str (ชื่อ emote ที่ user พิมพ์ เช่น "Kappa")
      - start, end: int (ตำแหน่งใน text เดิม, end inclusive)
    """
    out = []
    if not emotes_tag:
        return out
    for entry in emotes_tag.split("/"):
        if ":" not in entry:
            continue
        eid_str, _, ranges_part = entry.partition(":")
        # รองรับทั้ง emote_id แบบตัวเลข (เก่า) และ string emotesv2_XXX (ใหม่)
        # — เดิมเช็ค isdigit() เท่านั้น → ทิ้ง emote ใหม่หมด
        if not eid_str:
            continue
        eid = eid_str  # เก็บเป็น string เสมอ (CDN URL รับได้ทั้งคู่)
        for r in ranges_part.split(","):
            if "-" not in r:
                continue
            s_str, _, e_str = r.partition("-")
            if s_str.isdigit() and e_str.isdigit():
                start = int(s_str)
                end_incl = int(e_str)  # Twitch: end inclusive
                if 0 <= start <= end_incl < len(text):
                    name = text[start : end_incl + 1]
                    out.append(
                        {"id": eid, "name": name, "start": start, "end": end_incl}
                    )
    # เรียงตาม start เพื่อให้ GUI render ตามลำดับ
    out.sort(key=lambda e: e["start"])
    return out


def _strip_emotes(
    text: str,
    emotes_tag: str,
    emote_replacements: Optional[dict] = None,
) -> str:
    """ตัด emotes ออกจากข้อความ โดยใช้ offset จาก Twitch emotes tag

    รูปแบบ emotes_tag: 'id:start-end,start-end/id2:start-end' หรือ '' (ว่าง = ไม่มี emote)
    offset เป็น Unicode code point (Python str index ตรง), end inclusive

    Args:
        text: ข้อความต้นฉบับ
        emotes_tag: Twitch emotes IRC tag
        emote_replacements: dict {emote_name_lower: คำอ่าน}
            ถ้า emote ตรงกับ key → แทนที่ด้วยคำอ่าน (ไม่ตัดทิ้ง)
            ถ้าไม่ตรง → ตัดทิ้งตามปกติ

    ตัวอย่าง:
        text="Kappa hello", emotes_tag="25:0-4", replacements={"kappa":"ฮ่าฮ่า"}
        → "ฮ่าฮ่า hello"

        text="Kappa hello", emotes_tag="25:0-4", replacements={}
        → "hello" (ตัดทิ้ง)

    Returns: ข้อความที่ประมวลผลแล้ว (กระชับ space)
    """
    if not emotes_tag:
        return text

    replacements = emote_replacements or {}

    # รวบรวมช่วงพร้อมชื่อ emote ของแต่ละช่วง (เพื่อเช็คคำแทนที่)
    # เก็บเป็น list of (start, end_exclusive, emote_name)
    emote_spans: list[tuple[int, int, str]] = []
    for emote_entry in emotes_tag.split("/"):
        if ":" not in emote_entry:
            continue
        _emote_id, _, ranges_part = emote_entry.partition(":")
        for r in ranges_part.split(","):
            if "-" in r:
                s_str, _, e_str = r.partition("-")
                if s_str.isdigit() and e_str.isdigit():
                    start = int(s_str)
                    end_excl = int(e_str) + 1  # end → exclusive
                    # ดึงชื่อ emote จากตำแหน่งในข้อความ (offset ตรงกับ Python str index)
                    if 0 <= start < end_excl <= len(text):
                        emote_name = text[start:end_excl]
                        emote_spans.append((start, end_excl, emote_name))

    if not emote_spans:
        return text

    # ประมวลผลจากหลังไปหน้า เพื่อไม่ให้ offset เพี้ยน
    emote_spans.sort(reverse=True)
    chars = text
    for start, end_excl, emote_name in emote_spans:
        # ถ้ามีคำแทนที่ → แทนที่ด้วยคำอ่าน, มิฉะนั้นตัดทิ้ง
        replacement = replacements.get(emote_name.lower())
        if replacement is not None:
            chars = chars[:start] + replacement + chars[end_excl:]
        else:
            chars = chars[:start] + chars[end_excl:]
    # กระชับ space ที่เหลือหลายช่องติดกัน
    return _MULTI_SPACE_RE.sub(" ", chars).strip()


def _strip_emotes_by_list(
    text: str,
    emote_list: list[dict],
    emote_replacements: Optional[dict] = None,
) -> str:
    """ตัด emotes ออกจากข้อความ โดยใช้ emote_list (รวม Twitch + third-party)

    emote_list: list of {id, name, url, start, end} (offset ใน text, end inclusive)
    emote_replacements: dict {emote_name_lower: คำอ่าน} — ถ้าตรง → แทนที่ด้วยคำอ่าน

    ประมวลผลจากหลังไปหน้า เพื่อไม่ให้ offset เพี้ยน
    """
    if not emote_list:
        return text
    replacements = emote_replacements or {}
    # รวบรวมช่วง (start, end_exclusive, emote_name)
    spans: list[tuple[int, int, str]] = []
    for em in emote_list:
        start = em.get("start")
        end = em.get("end")
        name = em.get("name", "")
        if start is None or end is None or not name:
            continue
        end_excl = end + 1  # end inclusive → exclusive
        if 0 <= start < end_excl <= len(text):
            spans.append((start, end_excl, name))
    if not spans:
        return text
    # ประมวลผลจากหลังไปหน้า
    spans.sort(reverse=True)
    chars = text
    for start, end_excl, emote_name in spans:
        replacement = replacements.get(emote_name.lower())
        if replacement is not None:
            chars = chars[:start] + replacement + chars[end_excl:]
        else:
            chars = chars[:start] + chars[end_excl:]
    return _MULTI_SPACE_RE.sub(" ", chars).strip()


TWITCH_IRC_HOST = "irc.chat.twitch.tv"
TWITCH_IRC_PORT = 6697  # SSL
# anonymous login: justinfan + เลขสุ่ม 4-5 หลัก (ห้ามซ้ำของคนจริง)
ANON_NICK_PREFIX = "justinfan"

# กำหนด tags ที่ต้องการ (ช่วย parse ง่ายขึ้น)
TWITCH_CAPABILITIES = "twitch.tv/tags twitch.tv/commands"

# Twitch GraphQL API (ดึง viewer count โดยไม่ต้อง OAuth)
TWITCH_GQL_URL = "https://gql.twitch.tv/gql"
TWITCH_GQL_CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"  # public web client-ID


class TwitchChat:
    """Twitch chat client แบบ anonymous (อ่านได้อย่างเดียว ไม่ส่งได้)"""

    def __init__(
        self,
        on_message: Callable[[ChatMessage], None],
        on_status: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        on_viewer_count: Optional[Callable[[str, int], None]] = None,
        text_filter=None,
    ) -> None:
        """text_filter: TextFilter instance (optional) — ใช้ replace_words
        สำหรับแทนที่ emote ด้วยคำอ่านก่อนตัด"""
        self.on_message = on_message
        self.on_status = on_status or (lambda msg: None)
        self.on_error = on_error or (lambda msg: None)
        self.on_viewer_count = on_viewer_count or (lambda plat, cnt: None)
        self._text_filter = text_filter

        self._sock: Optional[ssl.SSLSocket] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._is_connected = False
        self._channel = ""

        # third-party emotes (FFZ + BTTV + 7TV) — โหลด async ตอน connect
        self._third_party_emotes = None  # ThirdPartyEmoteSet | None

        # Channel Points reward metadata cache — {uuid: {title, cost, icon_url}}
        # ดึงจาก GraphQL (anonymous) ตอน connect + refresh ทุก 10 นาที
        self._reward_cache: dict = {}
        self._room_id: str = ""  # numeric channel ID (จาก room-id tag) — ใช้สร้าง icon URL

        # สถิติ
        self.messages_read = 0

    # ------------------------------------------------------------------ #
    # Connection
    # ------------------------------------------------------------------ #
    @property
    def is_connected(self) -> bool:
        return self._is_connected

    def connect(self, channel: str) -> bool:
        """เชื่อมต่อ Twitch IRC — channel คือชื่อ Channel (ไม่ต้องมี #)

        Returns True ถ้าเชื่อมต่อสำเร็จ (ส่ง JOIN ได้)
        """
        channel = channel.strip().lstrip("#").lower()
        if not channel:
            self.on_error("กรุณาใส่ชื่อ Channel")
            return False

        if self._is_connected:
            self.on_error("เชื่อมต่ออยู่แล้ว — กด Disconnect ก่อน")
            return False

        # anonymous nick
        nick = f"{ANON_NICK_PREFIX}{random.randint(10000, 99999)}"
        token = "oauth:1234567890"  # arbitrary — anonymous ไม่ตรวจ

        try:
            self._connect_socket(nick, token)
        except OSError as exc:
            self.on_error(f"เชื่อมต่อ Twitch ไม่ได้: {exc}")
            self._is_connected = False
            return False

        self._channel = channel
        self._send_raw(f"JOIN #{channel}\r\n")
        self._is_connected = True

        # โหลด third-party emotes (FFZ + BTTV + 7TV) ของ channel ใน background
        # ไม่บล็อก connect และไม่แสดง status (ทำงานเงียบๆ)
        try:
            from third_party_emotes import load_channel_emotes
            self._third_party_emotes = load_channel_emotes(channel)
        except Exception:
            self._third_party_emotes = None

        # เริ่ม reader thread
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._reader_loop, name="TwitchIRCReader", daemon=True
        )
        self._thread.start()

        # เริ่ม viewer count poll thread (GraphQL API ทุก 60s)
        self._viewer_thread = threading.Thread(
            target=self._viewer_poll_loop, name="TwitchViewerPoll", daemon=True,
        )
        self._viewer_thread.start()

        self.on_status(f"✅ เชื่อมต่อ Twitch #{channel}")
        return True

    def _connect_socket(self, nick: str, token: str) -> None:
        """เปิด SSL socket ไปยัง Twitch IRC"""
        raw_sock = socket.create_connection((TWITCH_IRC_HOST, TWITCH_IRC_PORT), timeout=15)
        ctx = ssl.create_default_context()
        self._sock = ctx.wrap_socket(raw_sock, server_hostname=TWITCH_IRC_HOST)
        self._sock.settimeout(1.0)  # short timeout ให้ตอบ _stop_event ได้

        self._send_raw(f"CAP REQ :{TWITCH_CAPABILITIES}\r\n")
        self._send_raw(f"PASS {token}\r\n")
        self._send_raw(f"NICK {nick}\r\n")

    def disconnect(self) -> None:
        """ยกเลิกการเชื่อมต่อ"""
        if not self._is_connected and self._sock is None:
            return

        self._stop_event.set()
        self._is_connected = False
        # เคลียร์ third-party emotes (จะโหลดใหม่ตอน reconnect)
        self._third_party_emotes = None

        if self._sock is not None:
            try:
                self._send_raw("QUIT\r\n")
            except OSError:
                pass
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=3)
        self._thread = None
        self.on_status("⚪ ยกเลิกการเชื่อมต่อ Twitch")

    def _viewer_poll_loop(self) -> None:
        """poll Twitch GraphQL API สำหรับ viewer count ทุก 60s + reward metadata ทุก 10 นาที"""
        # poll ครั้งแรกทันที
        self._poll_viewer_count()
        self._fetch_reward_metadata()  # ดึง reward metadata ครั้งแรก
        reward_counter = 0  # นับรอบ (10 รอบ = 10 นาที)
        while not self._stop_event.is_set():
            slept = 0.0
            while slept < 60.0 and not self._stop_event.is_set():
                time.sleep(1.0)
                slept += 1.0
            if self._stop_event.is_set():
                break
            self._poll_viewer_count()
            reward_counter += 1
            if reward_counter >= 10:  # refresh reward metadata ทุก ~10 นาที
                self._fetch_reward_metadata()
                reward_counter = 0

    def _poll_viewer_count(self) -> None:
        """ดึง viewer count จาก Twitch GraphQL API (ไม่ต้อง OAuth)"""
        if not self._channel:
            return
        try:
            import requests as _req
            query = (
                'query { user(login: "%s") { stream { viewersCount } } }'
                % self._channel
            )
            r = _req.post(
                TWITCH_GQL_URL,
                json={"query": query},
                headers={"Client-ID": TWITCH_GQL_CLIENT_ID},
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                stream = (
                    data.get("data", {}).get("user", {}).get("stream")
                )
                count = stream.get("viewersCount", 0) if stream else 0
                self.on_viewer_count("twitch", int(count))
        except Exception:
            pass

    def _fetch_reward_metadata(self) -> None:
        """ดึง Channel Points reward metadata (title, cost) จาก GraphQL (anonymous)

        เก็บใน self._reward_cache = {uuid: {title, cost}}
        ไม่ได้ดึง icon URL เพราะ GraphQL ส่ง image=null ส่วนใหญ่
        → ใช้ fallback CDN pattern แทน (static-cdn.jtvnw.net/channel-points-icons/...)
        """
        if not self._channel:
            return
        try:
            import requests as _req
            query = (
                '{ user(login: "%s") { id channel { communityPointsSettings '
                '{ customRewards { id title cost } } } } }'
                % self._channel
            )
            r = _req.post(
                TWITCH_GQL_URL,
                json={"query": query},
                headers={"Client-ID": TWITCH_GQL_CLIENT_ID},
                timeout=10,
            )
            if r.status_code != 200:
                return
            data = r.json().get("data", {}).get("user") or {}
            # เก็บ room_id (numeric channel ID) สำหรับสร้าง icon URL
            if data.get("id"):
                self._room_id = str(data["id"])
            rewards = (
                data.get("channel", {})
                .get("communityPointsSettings", {})
                .get("customRewards", [])
                or []
            )
            new_cache = {}
            for rw in rewards:
                uuid = rw.get("id")
                if uuid:
                    new_cache[uuid] = {
                        "title": rw.get("title", ""),
                        "cost": int(rw.get("cost", 0) or 0),
                    }
            if new_cache:
                self._reward_cache = new_cache
        except Exception:
            pass

    def _send_raw(self, line: str) -> None:
        if self._sock is None:
            return
        self._sock.sendall(line.encode("utf-8"))

    # ------------------------------------------------------------------ #
    # Reader loop (background thread)
    # ------------------------------------------------------------------ #
    def _reader_loop(self) -> None:
        """อ่านข้อมูลจาก socket ตลอด จนกว่าจะ disconnect"""
        buf = ""
        while not self._stop_event.is_set():
            try:
                if self._sock is None:
                    break
                data = self._sock.recv(4096)
            except socket.timeout:
                continue  # timeout = loop ใหม่ (ตรวจ _stop_event)
            except (OSError, ssl.SSLError) as exc:
                if not self._stop_event.is_set():
                    self.on_error(f"การเชื่อมต่อ Twitch หลุด: {exc}")
                break

            if not data:
                # socket ถูกปิดจากฝั่งเซิร์ฟเวอร์
                if not self._stop_event.is_set():
                    self.on_error("การเชื่อมต่อ Twitch ถูกปิดจากเซิร์ฟเวอร์")
                break

            try:
                buf += data.decode("utf-8", errors="replace")
            except UnicodeDecodeError:
                buf += data.decode("latin-1", errors="replace")

            # แยกตามบรรทัด (IRC ปิดท้ายด้วย \r\n)
            while "\r\n" in buf:
                line, buf = buf.split("\r\n", 1)
                if line:
                    self._handle_line(line)

        self._is_connected = False

    # ------------------------------------------------------------------ #
    # IRC line dispatching
    # ------------------------------------------------------------------ #
    def _handle_line(self, line: str) -> None:
        """parse และ dispatch IRC line เดียว"""
        # PING/PONG keepalive
        if line.startswith("PING"):
            self._send_raw("PONG " + line.split(" ", 1)[1] + "\r\n")
            return

        # LOGIN FAILED (anonymous ไม่ควรเจอ แต่เผื่อไว้)
        if "LOGIN_UNSUCCESSFUL" in line or ":tmi.twitch.tv NOTICE * :Login unsuccessful" in line:
            self.on_error("Login ล้มเหลว (ไม่ควรเกิดกับ anonymous)")
            return

        # JOIN สำเร็จ
        if "JOIN" in line and f"#{self._channel}" in line:
            return

        # PRIVMSG = chat ปกติ + bits
        if "PRIVMSG" in line and "tmi.twitch.tv" not in line.split(" ", 2)[1]:
            # ระวัง PRIVMSG ใน MOTD — เช็คว่าเป็น user PRIVMSG จริง
            pass

        if " PRIVMSG " in line:
            self._handle_privmsg(line)
        elif " USERNOTICE " in line:
            self._handle_usernotice(line)

    # ------------------------------------------------------------------ #
    # Parsing helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _parse_tags(line: str) -> tuple[dict, str]:
        """แยก IRCv3 tags ( @key=val;key=val ) ออกจาก line body

        Returns (tags_dict, remaining_line)
        """
        tags: dict[str, str] = {}
        remaining = line
        if line.startswith("@"):
            tag_part, _, remaining = line.partition(" ")
            for pair in tag_part[1:].split(";"):
                if "=" in pair:
                    key, _, val = pair.partition("=")
                    # unescape IRC tag escapes
                    val = (
                        val.replace("\\s", " ")
                        .replace("\\n", "\n")
                        .replace("\\r", "\r")
                        .replace("\\:", ";")
                        .replace("\\\\", "\\")
                    )
                    tags[key] = val
        return tags, remaining

    @staticmethod
    def _parse_prefix(line: str) -> tuple[Optional[str], str]:
        """แยก :nick!user@host PREFIX ออก คืน (nick, remaining)"""
        if line.startswith(":"):
            prefix, _, remaining = line.partition(" ")
            nick = prefix[1:].split("!", 1)[0]
            return nick, remaining
        return None, line

    def _handle_privmsg(self, line: str) -> None:
        """parse PRIVMSG — chat ปกติหรือ bits donate"""
        tags, body = self._parse_tags(line)
        _, body = self._parse_prefix(body)
        # body: PRIVMSG #channel :message
        match = re.match(r"PRIVMSG\s+#\S+\s+:(.*)$", body, re.IGNORECASE | re.DOTALL)
        if not match:
            return
        text = match.group(1).strip()
        author = tags.get("display-name") or tags.get("login") or "?"

        # parse emote list ก่อน strip (offset ตรง text เดิม) — เก็บไว้ render เป็นภาพใน GUI
        emotes_tag = tags.get("emotes", "")
        emote_list = _parse_emotes(text, emotes_tag)
        raw_text = text  # text ก่อน strip (GUI render ใช้อันนี้เพื่อแสดง emote ในตำแหน่งถูก)

        # ── third-party emotes (FFZ/BTTV/7TV) — detect ใน raw_text ──
        # ค้นหา emote codes ที่ไม่ได้อยู่ใน Twitch emotes tag (เป็นของ third-party)
        if self._third_party_emotes is not None and self._third_party_emotes.loaded:
            try:
                tp_matches = self._third_party_emotes.find_in_text(raw_text)
                if tp_matches:
                    # เก็บเฉพาะที่ไม่ทับซ้อนกับ Twitch emotes ที่มีอยู่แล้ว
                    existing_ranges = [(e["start"], e["end"]) for e in emote_list]
                    for tp in tp_matches:
                        overlaps = any(
                            not (tp["end"] < s or tp["start"] > e)
                            for s, e in existing_ranges
                        )
                        if not overlaps:
                            emote_list.append({
                                "id": None,  # third-party ไม่มี numeric id
                                "name": tp["name"],
                                "url": tp["url"],  # static URL — GUI ใช้ URL นี้
                                "url_animated": tp.get("url_animated", tp["url"]),  # animated — OBS ใช้
                                "start": tp["start"],
                                "end": tp["end"],
                            })
                    # เรียงตาม start ใหม่
                    emote_list.sort(key=lambda e: e["start"])
            except Exception:
                pass

        # กรอง emotes ออกจากข้อความ ก่อนส่ง TTS (ใช้ offset จาก emote_list รวม Twitch + third-party)
        # ถ้ามี text_filter และมี replace_words → emote ที่ตรงจะถูกแทนด้วยคำอ่าน แทนที่จะตัดทิ้ง
        emote_replacements = None
        if self._text_filter is not None and self._text_filter.replace_words:
            # ★ format ใหม่: value = {display, read} — emote อ่านเสมอ ใช้ค่า "read"
            emote_replacements = {
                k.lower(): (v["read"] if isinstance(v, dict) else v)
                for k, v in self._text_filter.replace_words.items()
            }
        text = _strip_emotes_by_list(text, emote_list, emote_replacements)

        # ถ้าข้อความเป็น emote ล้วน (ว่างหลัง strip) → ไม่ส่ง TTS
        # แต่ยังส่งให้ GUI แสดงภาพ emote (text="" แต่มี emote_list)
        extra_base = {
            "color": tags.get("color", ""),
            "badges": tags.get("badges", ""),
            "emotes": emote_list,    # list of {id, name, start, end} (offset ใน raw_text)
            "raw_text": raw_text,    # text ก่อน strip — GUI render ใช้อันนี้
        }

        # bits donate? (PRIVMSG มี @bits=N tag)
        bits_str = tags.get("bits")
        if bits_str and bits_str.isdigit():
            self.messages_read += 1
            self.on_message(
                ChatMessage(
                    platform="twitch",
                    author=author,
                    text=text,
                    event="bits",
                    amount=int(bits_str),
                    extra=extra_base,
                )
            )
            return

        # Channel Point redemption? (PRIVMSG มี @custom-reward-id=<UUID>)
        # ⚠️ Twitch ส่ง IRC message เฉพาะ reward ที่มีช่องพิมพ์ข้อความ (text-prompt)
        #    reward ที่ไม่มี text-prompt จะไม่ปรากฏ (Twitch limitation)
        reward_uuid = tags.get("custom-reward-id")
        is_highlight = tags.get("msg-id") == "highlighted-message"
        if reward_uuid or is_highlight:
            # ดึง metadata จาก cache (title, cost) — ถ้า cache miss ใช้ default
            meta = self._reward_cache.get(reward_uuid, {}) if reward_uuid else {}
            room_id = tags.get("room-id", "") or self._room_id
            # สร้าง icon URL — ลอง GraphQL image ก่อน, ถ้าไม่มี ใช้ CDN pattern
            icon_url = ""
            if reward_uuid and room_id:
                icon_url = (
                    f"https://static-cdn.jtvnw.net/channel-points-icons/"
                    f"{room_id}/{reward_uuid}/icon-2.png"
                )
            reward_title = meta.get("title") or ("Highlight" if is_highlight else "Reward")
            reward_cost = meta.get("cost", 0)
            extra_base["reward_uuid"] = reward_uuid or ""
            extra_base["reward_title"] = reward_title
            extra_base["reward_cost"] = reward_cost
            extra_base["reward_icon"] = icon_url
            self.messages_read += 1
            self.on_message(
                ChatMessage(
                    platform="twitch",
                    author=author,
                    text=text,  # ข้อความที่ user พิมพ์ (ถ้ามี)
                    event="redeem",
                    amount=reward_cost if reward_cost else None,
                    extra=extra_base,
                )
            )
            return

        self.messages_read += 1
        self.on_message(
            ChatMessage(
                platform="twitch",
                author=author,
                text=text,
                event="message",
                extra=extra_base,
            )
        )

    def _handle_usernotice(self, line: str) -> None:
        """parse USERNOTICE — sub / resub / subgift / raid"""
        tags, body = self._parse_tags(line)
        msg_id = tags.get("msg-id", "")
        author = tags.get("display-name") or tags.get("login") or "?"

        # system message ที่ Twitch แนบมา (สำหรับ TTS)
        system_text = tags.get("system-msg", "")

        # ข้อความ user (จะมีเฉพาะ resub ที่พิมพ์คอมเม้นต์)
        match = re.search(r"USERNOTICE\s+#\S+\s+:(.*)$", body, re.IGNORECASE | re.DOTALL)
        user_text = match.group(1).strip() if match else ""

        event = "message"
        amount = None
        tier = None

        if msg_id in ("sub", "resub"):
            event = "resub" if msg_id == "resub" else "sub"
            # plan: Prime=1, 1000=tier1, 2000=tier2, 3000=tier3
            plan = tags.get("msg-param-sub-plan", "")
            tier = {"prime": 0, "1000": 1, "2000": 2, "3000": 3}.get(plan, 1)
            # resub มีจำนวนเดือน
            months = tags.get("msg-param-cumulative-months")
            if months and months.isdigit():
                system_text = system_text or f"subbed {months} months"
        elif msg_id == "subgift" or msg_id == "anonsubgift":
            event = "subgift"
            recipient = tags.get("msg-param-recipient-display-name", "?")
            system_text = system_text or f"gifted a sub to {recipient}"
        elif msg_id == "raid" or msg_id == "unraid":
            event = "raid"
            viewers = tags.get("msg-param-viewerCount")
            if viewers and viewers.isdigit():
                amount = int(viewers)
            raider = tags.get("msg-param-displayName") or tags.get(
                "msg-param-login", author
            )
            system_text = system_text or f"raided with {amount or '?'} viewers"
            author = raider
        else:
            # ไม่ใช่ event ที่เราสนใจ → ข้าม
            return

        self.messages_read += 1
        self.on_message(
            ChatMessage(
                platform="twitch",
                author=author,
                text=user_text,
                event=event,
                amount=amount,
                tier=tier,
                system_text=system_text,
                extra={"msg-id": msg_id},
            )
        )


# ---------------------------------------------------------------------- #
# Smoke test — อ่าน chat 10 วินาที
# ---------------------------------------------------------------------- #
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python chat_twitch.py <channel> [seconds]")
        print("Example: python chat_twitch.py twitch 10")
        sys.exit(1)

    channel = sys.argv[1]
    duration = int(sys.argv[2]) if len(sys.argv) > 2 else 10

    def cb(msg: ChatMessage) -> None:
        prefix = msg.event.upper()
        amount_str = f" [{msg.amount}]" if msg.amount else ""
        sys_str = f"  ({msg.system_text})" if msg.system_text else ""
        print(f"[{prefix}] {msg.author}{amount_str}: {msg.text}{sys_str}")

    def status(msg: str) -> None:
        print(f">> {msg}")

    client = TwitchChat(on_message=cb, on_status=status, on_error=status)
    if client.connect(channel):
        time.sleep(duration)
        client.disconnect()
        print(f">> read {client.messages_read} messages")
