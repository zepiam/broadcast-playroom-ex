"""text_filter.py — กรอง/แทนที่/block user/secret code

ฟังก์ชัน:
  - is_user_blocked(author) → ถ้า author อยู่ใน blocklist → True
  - filter_text(text) → คืนข้อความที่แทนที่แล้ว หรือ None ถ้าติดคำต้องห้าม
  - check_secret_code(text) → ถ้า text ตรงกับ secret code → คืน (mp3_path, volume)

คำสั่ง:
  - blocked_users: list[str]     ชื่อ user ที่ไม่อ่าน (case-insensitive)
  - banned_words: list[str]      คำที่จะ skip ข้อความทั้งข้อความ
  - replace_words: dict[str, dict] แทนที่คำ — value = {"display": str, "read": str}
      display="" (ว่าง) = แสดงคำเดิมในแชท, TTS อ่าน "read" (แก้การออกเสียงล้วน)
      display!=" "      = แสดง "display" ในแชท, TTS อ่าน "read" (แทนที่คำ)
  - secret_codes: dict[str, (path, volume)]  โค้ด → (mp3_path, 0..1)

การ match:
  - blocked_users: เทียบชื่อแบบ case-insensitive, exact match
  - banned_words / replace_words: case-insensitive substring (word-boundary ที่ใกล้ที่สุด)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class SecretCode:
    """โค้ดลับ → เล่นเสียง"""

    code: str  # เช่น "!wow"
    sound_path: str  # path ไฟล์เสียง
    volume: float = 0.8  # 0..1


@dataclass
class TextFilter:
    """ตัวกรองข้อความสำหรับ TTS

    blocked_users รองรับ 2 รูปแบบ (backward-compatible):
      - list[str] เก่า: ["troll", "bot123"]
      - list[dict] ใหม่: [{"name": "troll", "hide_overlay": false}, ...]
        hide_overlay=True = ไม่อ่าน + ไม่แสดง overlay (แสดงแค่ Live Chat)
        hide_overlay=False = ไม่อ่าน + แสดง overlay (เหมือนเดิม)
    """

    blocked_users: list = field(default_factory=list)
    banned_words: list[str] = field(default_factory=list)
    replace_words: dict[str, dict] = field(default_factory=dict)
    secret_codes: list[SecretCode] = field(default_factory=list)

    # cache regex หลังจาก rebuild
    _banned_re: re.Pattern = field(default=None, repr=False, compare=False)
    _replace_re: re.Pattern = field(default=None, repr=False, compare=False)
    # _replace_patterns = entries ที่ display != "" (แทนใน filter_text — แสดงในแชท)
    _replace_patterns: list = field(default_factory=list, repr=False, compare=False)
    # _pronounce_patterns = entries ทั้งหมด (แทน read ใน apply_pronunciation — ส่ง TTS)
    _pronounce_patterns: list = field(default_factory=list, repr=False, compare=False)
    # name_lower → {"hide_overlay": bool}  (rebuilt cache)
    _users_map: dict = field(default_factory=dict, repr=False, compare=False)
    _dirty: bool = True

    def __post_init__(self) -> None:
        self.rebuild()

    # ------------------------------------------------------------------ #
    # Mutators — เปลี่ยนแล้ว rebuild cache
    # ------------------------------------------------------------------ #
    def add_blocked_user(self, user: str, hide_overlay: bool = False) -> None:
        """เพิ่ม user เข้า blocklist

        hide_overlay=True = ไม่อ่าน + ไม่แสดง overlay (แสดงแค่ Live Chat)
        hide_overlay=False = ไม่อ่าน + แสดง overlay (เหมือนเดิม)
        """
        user = user.strip().lower()
        if user and user not in self._users_map:
            self.blocked_users.append(
                {"name": user, "hide_overlay": bool(hide_overlay)}
            )
            self._users_map[user] = {"hide_overlay": bool(hide_overlay)}
            self._dirty = True

    def remove_blocked_user(self, user: str) -> None:
        user = user.strip().lower()
        # ลบจาก _users_map
        if user in self._users_map:
            del self._users_map[user]
            self._dirty = True
        # ลบจาก blocked_users (ทั้งรูปแบบ str เก่าและ dict ใหม่)
        self.blocked_users = [
            u for u in self.blocked_users
            if not (
                (isinstance(u, str) and u.strip().lower() == user)
                or (isinstance(u, dict) and u.get("name", "").strip().lower() == user)
            )
        ]

    def set_blocked_user_mode(self, user: str, hide_overlay: bool) -> None:
        """เปลี่ยนโหมดของ user ที่บล็อกอยู่แล้ว (show/hide overlay)"""
        user_lower = user.strip().lower()
        if user_lower in self._users_map:
            self._users_map[user_lower]["hide_overlay"] = bool(hide_overlay)
            for u in self.blocked_users:
                if isinstance(u, dict) and u.get("name", "").strip().lower() == user_lower:
                    u["hide_overlay"] = bool(hide_overlay)
            self._dirty = True

    def add_banned_word(self, word: str) -> None:
        word = word.strip()
        if word and word not in self.banned_words:
            self.banned_words.append(word)
            self._dirty = True

    def remove_banned_word(self, word: str) -> None:
        if word in self.banned_words:
            self.banned_words.remove(word)
            self._dirty = True

    def set_replace(self, src: str, display: str, read: str) -> None:
        """เพิ่ม/แก้คำแทนที่

        display="" (ว่าง) = แสดงคำเดิมในแชท, TTS อ่าน read (แก้การออกเสียง)
        display!=""         = แสดง display ในแชท, TTS อ่าน read (แทนที่คำ)
        """
        src = src.strip()
        display = display.strip()
        read = read.strip()
        if src and read:
            self.replace_words[src] = {"display": display, "read": read}
            self._dirty = True

    def remove_replace(self, src: str) -> None:
        if src in self.replace_words:
            del self.replace_words[src]
            self._dirty = True

    @staticmethod
    def _normalize_entry(v) -> dict:
        """migrate value เก่า → format ใหม่ {"display": str, "read": str}

        - string เก่า "ปั๊กอิน" → {"display": "ปั๊กอิน", "read": "ปั๊กอิน"}
        - {to, mode} เก่า → {display: to if replace else "", read: to}
        - {display, read} ใหม่ → ผ่านตรง ๆ
        """
        if isinstance(v, dict):
            if "to" in v:  # format เก่า {to, mode}
                mode = v.get("mode", "replace")
                to = str(v.get("to", ""))
                return {"display": to if mode == "replace" else "", "read": to}
            return {"display": str(v.get("display", "")), "read": str(v.get("read", ""))}
        return {"display": str(v), "read": str(v)}  # legacy string

    def add_secret_code(self, code: SecretCode) -> None:
        # ลบอันเดิมถ้ามี code ซ้ำ
        self.secret_codes = [c for c in self.secret_codes if c.code != code.code]
        self.secret_codes.append(code)

    def remove_secret_code(self, code: str) -> None:
        self.secret_codes = [c for c in self.secret_codes if c.code != code]

    def rebuild(self) -> None:
        """rebuild regex caches — เรียกหลัง mutate ทั้งหมด"""
        # users — รองรับทั้ง list[str] เก่าและ list[dict] ใหม่
        self._users_map = {}
        for u in self.blocked_users:
            if isinstance(u, dict):
                name = u.get("name", "").strip().lower()
                if name:
                    self._users_map[name] = {"hide_overlay": bool(u.get("hide_overlay", False))}
            elif isinstance(u, str):
                name = u.strip().lower()
                if name:
                    self._users_map[name] = {"hide_overlay": False}

        # banned: build alternation (longest first เพื่อ match คำยาวก่อน)
        banned_sorted = sorted(
            (re.escape(w) for w in self.banned_words if w),
            key=len,
            reverse=True,
        )
        if banned_sorted:
            self._banned_re = re.compile(
                "|".join(banned_sorted), re.IGNORECASE | re.UNICODE
            )
        else:
            self._banned_re = None

        # replace: build patterns — รองรับ 3 รูปแบบพิเศษ
        # 1. {URL} → URL regex
        # 2. X{N+} → X ซ้ำขั้นต่ำ N ตัว (เช่น 5{4+} = 5555+ แทนด้วยคำเดียว)
        # 3. X@ → X ซ้ำ 2 ตัวขึ้นไป (เช่น w@ = ww, www, wwww แทนด้วยคำเดียว)
        # 4. ปกติ → exact match
        # ★ migrate entries เก่า → format ใหม่ {display, read} ก่อน build patterns
        for src in list(self.replace_words.keys()):
            self.replace_words[src] = self._normalize_entry(self.replace_words[src])

        def _build_pattern(src: str, dst: str, ptype: str):
            """build single regex pattern tuple (pat, dst, ptype)"""
            if src == "{URL}":
                url_re = r'https?://\S+|www\.\S+'
                return (re.compile(url_re, re.IGNORECASE), dst, "{URL}")
            elif re.fullmatch(r'(.+?)\{(\d+)\+\}', src):
                m = re.fullmatch(r'(.+?)\{(\d+)\+\}', src)
                char = re.escape(m.group(1)[0])
                min_count = int(m.group(2))
                pat = re.compile(char + '{' + str(min_count) + r',}', re.IGNORECASE | re.UNICODE)
                return (pat, dst, "repeat_min")
            elif src.endswith('@') and len(src) > 1:
                char = re.escape(src[:-1][0])
                pat = re.compile(char + '{2,}', re.IGNORECASE | re.UNICODE)
                return (pat, dst, "repeat_any")
            else:
                return (re.compile(re.escape(src), re.IGNORECASE | re.UNICODE), dst, "exact")

        # _replace_patterns = entries ที่ display != "" (แทนใน filter_text — แสดงในแชท)
        replace_pats = []
        for src in self.replace_words.keys():
            if not src:
                continue
            entry = self.replace_words[src]
            display = entry.get("display", "")
            if display:  # มี display → แทนในแชท
                replace_pats.append(_build_pattern(src, display, "exact"))
        # _pronounce_patterns = entries ทั้งหมด (แทน read ใน apply_pronunciation — ส่ง TTS)
        # ★ ต้อง match ทั้ง original และ display (เพราะ filter_text อาจแทน original → display ไปแล้ว)
        pronounce_pats = []
        for src in self.replace_words.keys():
            if not src:
                continue
            entry = self.replace_words[src]
            read = entry.get("read", "")
            display = entry.get("display", "")
            if read:
                pronounce_pats.append(_build_pattern(src, read, "exact"))
                # ถ้า display ไม่ว่าง + ไม่ตรง original → เพิ่ม pattern สำหรับ display ด้วย
                if display and display != src:
                    pronounce_pats.append(_build_pattern(display, read, "exact"))

        # sort: special patterns (URL + repeat) ทำก่อนเสมอ → exact ทำทีหลัง
        def _sort_patterns(pats):
            exact = [p for p in pats if p[2] == "exact"]
            special = [p for p in pats if p[2] != "exact"]
            url_p = [p for p in special if p[2] == "{URL}"]
            repeat_p = [p for p in special if p[2] != "{URL}"]
            exact.sort(key=lambda p: len(p[1]), reverse=True)
            return url_p + repeat_p + exact

        self._replace_patterns = _sort_patterns(replace_pats)
        self._pronounce_patterns = _sort_patterns(pronounce_pats)
        # backward compat: ยังเก็บ _replace_re สำหรับ old code ที่อ้างถึง
        replace_sorted = sorted(
            (re.escape(k) for k in self.replace_words.keys() if k and not k.startswith('{') and not k.endswith('@') and not re.fullmatch(r'(.+?)\{(\d+)\+\}', k)),
            key=len,
            reverse=True,
        )
        if replace_sorted:
            self._replace_re = re.compile(
                "|".join(replace_sorted), re.IGNORECASE | re.UNICODE
            )
        else:
            self._replace_re = None

        self._dirty = False

    # ------------------------------------------------------------------ #
    # Checks (เรียกจาก chat_queue pipeline)
    # ------------------------------------------------------------------ #
    def is_user_blocked(self, author: str) -> bool:
        """ถ้า author อยู่ใน blocklist → True (ไม่ว่าจะโหมดไหน)"""
        if self._dirty:
            self.rebuild()
        return author.strip().lower() in self._users_map

    def is_user_hidden_from_overlay(self, author: str) -> bool:
        """ถ้า author อยู่ใน blocklist และตั้ง hide_overlay=True → True

        ใช้ตัดสินใจว่าจะ push ไป overlay หรือไม่
        (แสดงใน Live Chat เสมอ แต่ overlay ขึ้นกับโหมด)
        """
        if self._dirty:
            self.rebuild()
        info = self._users_map.get(author.strip().lower())
        return bool(info and info.get("hide_overlay"))

    def get_blocked_user_mode(self, author: str) -> bool:
        """คืน hide_overlay flag ของ author (False = แสดง overlay, True = ซ่อน overlay)"""
        if self._dirty:
            self.rebuild()
        info = self._users_map.get(author.strip().lower())
        return bool(info and info.get("hide_overlay")) if info else False

    def check_secret_code(self, text: str) -> tuple[str, float] | None:
        """ถ้า text = secret code (หรือมี code) → คืน (sound_path, volume)

        เช็คแบบ prefix match: "!wow" จะ match "!wow" หรือ "!wow extra"
        Returns None ถ้าไม่ใช่ secret code
        """
        text = text.strip()
        if not text:
            return None
        for code in self.secret_codes:
            # exact match หรือ "code args..."
            if text == code.code or text.startswith(code.code + " "):
                return (code.sound_path, code.volume)
        return None

    def filter_text(self, text: str) -> str | None:
        """filter ข้อความ (สำหรับแสดงในแชท + ส่ง TTS)

        Returns:
          - None ถ้าติดคำต้องห้าม → caller ควร skip ทั้งข้อความ
          - ข้อความใหม่ถ้าผ่าน (อาจถูก replace — เฉพาะ entries ที่ display != "")

        หมายเหตุ: การแทน "read" (แก้การออกเสียง) ทำใน apply_pronunciation() แยกต่างหาก
        เพื่อให้แชทแสดงคำเดิม แต่ TTS อ่านคำใหม่
        """
        if self._dirty:
            self.rebuild()

        if not text:
            return text

        # 1) banned word → skip ทั้งข้อความ
        if self._banned_re is not None and self._banned_re.search(text):
            return None

        # 2) replace words — ใช้ _replace_patterns (เฉพาะ display != "" — แสดงในแชท)
        if self._replace_patterns:
            for pat, dst, ptype in self._replace_patterns:
                text = pat.sub(dst, text)

        return text

    def apply_pronunciation(self, text: str) -> str:
        """แทนคำ "read" (แก้การออกเสียง) สำหรับ TTS เท่านั้น — ไม่กระทบข้อความที่แสดงในแชท

        เรียกจาก _build_speak_text() ใน chat_queue ก่อนส่ง TTS
        ใช้ _pronounce_patterns (entries ทั้งหมด — ทั้ง display != "" และ display == "")
        """
        if self._dirty:
            self.rebuild()
        if not text or not self._pronounce_patterns:
            return text
        for pat, dst, ptype in self._pronounce_patterns:
            text = pat.sub(dst, text)
        return text

    # ------------------------------------------------------------------ #
    # Serialization (สำหรับ settings persistence)
    # ------------------------------------------------------------------ #
    def to_dict(self) -> dict:
        return {
            "blocked_users": list(self.blocked_users),
            "banned_words": list(self.banned_words),
            "replace_words": dict(self.replace_words),
            "secret_codes": [
                {"code": c.code, "sound_path": c.sound_path, "volume": c.volume}
                for c in self.secret_codes
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TextFilter":
        codes = [
            SecretCode(
                code=c["code"],
                sound_path=c["sound_path"],
                volume=float(c.get("volume", 0.8)),
            )
            for c in data.get("secret_codes", [])
        ]
        # ★ migrate replace_words เก่า → format ใหม่ {display, read}
        raw_replace = dict(data.get("replace_words", {}))
        replace_words = {k: cls._normalize_entry(v) for k, v in raw_replace.items()}
        f = cls(
            blocked_users=list(data.get("blocked_users", [])),
            banned_words=list(data.get("banned_words", [])),
            replace_words=replace_words,
            secret_codes=codes,
        )
        f.rebuild()
        return f


# ---------------------------------------------------------------------- #
# Smoke test
# ---------------------------------------------------------------------- #
if __name__ == "__main__":
    f = TextFilter(
        blocked_users=["troll", "bot123"],
        banned_words=["คำหยาบ", "fuck"],
        replace_words={
            "ห่วย": {"display": "ดี", "read": "ดี"},          # replace mode
            "สวัสดี": {"display": "หวัดดี", "read": "หวัดดี"},  # replace mode
        },
        secret_codes=[SecretCode("!wow", "sounds/wow.mp3", 0.7)],
    )

    assert f.is_user_blocked("TROLL") is True  # case-insensitive
    assert f.is_user_blocked("NormalUser") is False

    assert f.filter_text("คำหยาบจริงๆ") is None  # banned → None
    assert f.filter_text("เล่นห่วยจัง") == "เล่นดีจัง"  # replaced
    assert f.filter_text("สวัสดีครับ") == "หวัดดีครับ"  # replaced
    assert f.filter_text("ปกติ") == "ปกติ"  # unchanged

    assert f.check_secret_code("!wow") == ("sounds/wow.mp3", 0.7)
    assert f.check_secret_code("!wow extra") == ("sounds/wow.mp3", 0.7)
    assert f.check_secret_code("hello") is None

    # ---- Pronunciation: display="" = แสดงคำเดิม แต่ TTS อ่าน read ----
    f3 = TextFilter(
        replace_words={
            "plugin": {"display": "", "read": "ปั๊กอิน"},       # pronunciation (แสดงคำเดิม)
            "ห่วย": {"display": "ดี", "read": "ดี"},              # replace (แสดงคำใหม่)
        }
    )
    # filter_text (แชท) — plugin ไม่ถูกแทน (display ว่าง), ห่วยถูกแทนเป็น ดี
    assert f3.filter_text("plugin ห่วยจัง") == "plugin ดีจัง"
    # apply_pronunciation (TTS) — plugin ถูกแทนเป็น ปั๊กอิน
    assert f3.apply_pronunciation("plugin ดีจัง") == "ปั๊กอิน ดีจัง"

    # ---- Migration: legacy string → {display, read} ----
    f4 = TextFilter(replace_words={"ห่วย": "ดี"})  # string เก่า
    assert f4.replace_words["ห่วย"] == {"display": "ดี", "read": "ดี"}
    assert f4.filter_text("ห่วยจัง") == "ดีจัง"

    # ---- Replace patterns ใหม่: URL / X{N+} / X@ ----
    f2 = TextFilter(
        replace_words={
            "{URL}": {"display": "[ลิงก์]", "read": "[ลิงก์]"},
            "5{4+}": {"display": "ฮ่าฮ่าฮ่าฮ่า", "read": "ฮ่าฮ่าฮ่าฮ่า"},
            "w@": {"display": "หัวเราะ", "read": "หัวเราะ"},
            "ห่วย": {"display": "ดี", "read": "ดี"},
        }
    )

    # {URL} — http/https/www
    assert f2.filter_text("ดูเลย https://example.com/x") == "ดูเลย [ลิงก์]"
    assert f2.filter_text("เว็บ www.example.com นะ") == "เว็บ [ลิงก์] นะ"
    assert f2.filter_text("http://a.b คือเว็บ") == "[ลิงก์] คือเว็บ"

    # 5{4+} — 5555 (4 ตัว) / 555555 (6 ตัว) แทน แต่ 555 (3 ตัว) ไม่ match
    assert f2.filter_text("ขำ5555") == "ขำฮ่าฮ่าฮ่าฮ่า"
    assert f2.filter_text("ขำ55555555") == "ขำฮ่าฮ่าฮ่าฮ่า"
    assert f2.filter_text("ขำ555") == "ขำ555"  # ต่ำกว่า 4 ตัว → ไม่ replace

    # w@ — ww / www / wwww แทน แต่ w ตัวเดียวไม่ match
    assert f2.filter_text("ww ดี") == "หัวเราะ ดี"
    assert f2.filter_text("wwww ดี") == "หัวเราะ ดี"
    assert f2.filter_text("w ดี") == "w ดี"  # ตัวเดียว → ไม่ match

    # exact ยังทำงานปกติ
    assert f2.filter_text("เล่นห่วยจัง") == "เล่นดีจัง"

    # ---- Priority ordering: URL ทำก่อน w@ ----
    # "www.google.com" ต้องกลายเป็น "[ลิงก์]" ไม่ใช่ "หัวเราะ.google.com"
    assert f2.filter_text("www.google.com") == "[ลิงก์]"

    print("✅ text_filter tests passed (incl. pronunciation + URL / X{N+} / X@ patterns)")
