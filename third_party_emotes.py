"""third_party_emotes.py — โหลด third-party emotes (FFZ + BTTV + 7TV) ของ Twitch channel

ทำงานแบบ async (background thread) ตอนเชื่อม Twitch channel:
  1. FFZ: GET /room/{login} → ได้ twitch_id + FFZ emotes
  2. BTTV: GET /cached/users/twitch/{twitch_id} → channelEmotes + sharedEmotes
  3. 7TV: GET /users/twitch/{twitch_id} → emote_set

เก็บผลลัพธ์ใน ThirdPartyEmoteSet:
  - emotes: dict {name_lower: {url, provider}} — สำหรับ detect ในข้อความ
  - twitch_id: str — twitch user id ของ channel

การ detect: ค้นหา emote name (word boundary) ในข้อความ
  ถ้าเจอ → แทนที่ด้วย URL ของ emote นั้น
"""
from __future__ import annotations

import json
import re
import threading
import urllib.request
from typing import Callable, Optional


# ── API endpoints ──
FFZ_ROOM_URL = "https://api.frankerfacez.com/v1/room/{login}"
BTTV_USER_URL = "https://api.betterttv.net/3/cached/users/twitch/{twitch_id}"
SEVENTV_USER_URL = "https://7tv.io/v3/users/twitch/{twitch_id}"

# CDN URL patterns
FFZ_CDN = "https://cdn.frankerfacez.com/emote/{id}/{scale}"
BTTV_CDN = "https://cdn.betterttv.net/emote/{id}/{scale}x"
# 7TV: ต้องระบุ extension (.webp = static, .gif = animated)
# — ถ้าไม่ระบุจะได้ HTTP 308 redirect → urllib ไม่ตาม → fail
SEVENTV_CDN_STATIC = "https://cdn.7tv.app/emote/{id}/{scale}x.webp"
SEVENTV_CDN_ANIMATED = "https://cdn.7tv.app/emote/{id}/{scale}x.gif"


def _http_get_json(url: str, timeout: float = 10.0) -> Optional[dict]:
    """GET JSON จาก URL — คืน None ถ้า fail"""
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "TTS-for-Livestream/1.0", "Accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
            if not data:
                return None
            return json.loads(data.decode("utf-8"))
    except Exception:
        return None


def _get_twitch_id_via_gql(login: str, timeout: float = 10.0) -> Optional[str]:
    """ดึง Twitch user ID จาก login name ผ่าน Twitch GraphQL API (ไม่ต้อง auth จริง)

    ใช้เมื่อ FFZ ไม่มีข้อมูล channel (FFZ ไม่ครอบคลุมทุก channel)
    — ใช้ public web Client-ID ที่หลายเครื่องมือใช้ (ไม่ใช่ OAuth จริง)
    """
    url = "https://gql.twitch.tv/gql"
    query = {"query": '{ user(login: "%s") { id } }' % login}
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(query).encode("utf-8"),
            headers={
                "User-Agent": "TTS-for-Livestream/1.0",
                "Client-Id": "kimne78kx3ncx6brgo4mv6wki5h1ko",  # public web client-ID
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode("utf-8"))
        user = d.get("data", {}).get("user")
        if user and user.get("id"):
            return str(user["id"])
    except Exception:
        pass
    return None


class ThirdPartyEmoteSet:
    """เก็บ third-party emotes ของ channel 1 ช่อง

    Attributes:
        channel: str — channel login name (lowercase)
        twitch_id: Optional[str] — twitch user id (ได้จาก FFZ)
        emotes: dict {name_lower: {"url": str, "provider": str, "name": str}}
        loaded: bool — โหลดเสร็จแล้วหรือยัง
    """

    def __init__(self, channel: str = "") -> None:
        self.channel = channel.lower().strip().lstrip("#")
        self.twitch_id: Optional[str] = None
        self.emotes: dict[str, dict] = {}
        self.loaded: bool = False
        self._lock = threading.Lock()

    def get(self, name: str) -> Optional[dict]:
        """ค้นหา emote ตามชื่อ (case-insensitive) → คืน {url, provider, name} หรือ None"""
        with self._lock:
            return self.emotes.get(name.lower())

    def find_in_text(self, text: str) -> list[dict]:
        """ค้นหา third-party emotes ในข้อความ → คืน list of {name, url, provider, start, end}

        ใช้ word boundary match (emote name ต้องเป็นคำเต็ม ไม่ใช่ส่วนของคำ)
        match case-insensitive (lowercase text ก่อน แล้ว match กับ lowercase names)
        Returns list เรียงตาม start ascending
        """
        if not self.emotes or not text:
            return []
        with self._lock:
            if not self.emotes:
                return []
            # สร้าง regex pattern จาก emote names (escape special chars)
            # เรียงจากยาว→สั้น เพื่อ match ที่ยาวกว่าก่อน (เช่น "NotLikeThis" ก่อน "Not")
            names = sorted(self.emotes.keys(), key=len, reverse=True)
            if not names:
                return []
            pattern = r"(?<!\w)(" + "|".join(re.escape(n) for n in names) + r")(?!\w)"
        # match บน lowercase text (case-insensitive)
        # แต่เก็บ start/end จากตำแหน่งเดิม (offset เท่ากันเพราะ ASCII)
        # NOTE: ภาษาที่มี multi-byte จะ offset ไม่ตรง แต่ emote names มักเป็น ASCII เท่านั้น
        text_lower = text.lower()
        compiled = re.compile(pattern)
        matches = []
        for m in compiled.finditer(text_lower):
            name_lower = m.group(1)
            info = self.emotes.get(name_lower)
            if info:
                matches.append({
                    "name": info["name"],
                    "url": info["url"],  # static URL (สำหรับ GUI)
                    "url_animated": info.get("url_animated", info["url"]),  # animated URL (สำหรับ OBS)
                    "provider": info["provider"],
                    "start": m.start(),
                    "end": m.end() - 1,  # inclusive (เหมือน Twitch emote format)
                })
        # เรียงตาม start
        matches.sort(key=lambda x: x["start"])
        return matches


def load_channel_emotes(
    channel: str,
    on_done: Optional[Callable[[ThirdPartyEmoteSet], None]] = None,
) -> ThirdPartyEmoteSet:
    """โหลด third-party emotes ของ channel (FFZ + BTTV + 7TV)

    ทำงานใน background thread — เรียก on_done(set) เมื่อเสร็จ
    คืน ThirdPartyEmoteSet ทันที (loaded=False) → caller เก็บ ref แล้วรอ on_done

    Flow:
      1. FFZ /room/{login} → ได้ twitch_id + FFZ emotes
      2. BTTV /cached/users/twitch/{twitch_id} → channelEmotes + sharedEmotes
      3. 7TV /users/twitch/{twitch_id} → emote_set
    """
    result = ThirdPartyEmoteSet(channel)

    def _worker():
        try:
            result.channel = channel.lower().strip().lstrip("#")
            # ── 1. FFZ (ใช้ login name ได้เลย + ได้ twitch_id) ──
            ffz_data = _http_get_json(FFZ_ROOM_URL.format(login=result.channel))
            if ffz_data:
                # twitch_id จาก FFZ room data
                room = ffz_data.get("room", {})
                tid = room.get("twitch_id")
                if tid:
                    result.twitch_id = str(tid)
                # FFZ emotes
                sets = ffz_data.get("sets", {})
                for _set_id, set_data in sets.items():
                    for em in set_data.get("emoticons", []):
                        name = em.get("name", "")
                        urls = em.get("urls", {})
                        if not name or not urls:
                            continue
                        # เลือก scale ที่ดีที่สุด (4 = ใหญ่สุด, 2 = กลาง, 1 = เล็ก)
                        scale = "4" if "4" in urls else ("2" if "2" in urls else "1")
                        url = urls.get(scale) or urls.get("1")
                        if url:
                            # FFZ URL อาจเป็น //cdn หรือ https://cdn
                            if url.startswith("//"):
                                url = "https:" + url
                            with result._lock:
                                result.emotes[name.lower()] = {
                                    "name": name,
                                    "url": url,
                                    "url_animated": url,  # FFZ emote URL เดียวกัน (ส่วนใหญ่เป็น png static)
                                    "provider": "ffz",
                                    "animated": False,
                                }
            # ── 2. + 3. BTTV + 7TV (ต้องการ twitch_id) ──
            # ถ้า FFZ ไม่มี twitch_id → ใช้ Twitch GraphQL หา (FFZ ไม่ครอบคลุมทุก channel)
            if not result.twitch_id:
                result.twitch_id = _get_twitch_id_via_gql(result.channel)
            if result.twitch_id:
                # BTTV
                bttv_data = _http_get_json(BTTV_USER_URL.format(twitch_id=result.twitch_id))
                if bttv_data:
                    # channelEmotes + sharedEmotes
                    for key in ("channelEmotes", "sharedEmotes"):
                        for em in bttv_data.get(key, []):
                            name = em.get("code", "")
                            eid = em.get("id", "")
                            if not name or not eid:
                                continue
                            # BTTV CDN: scale 3 = ใหญ่สุด
                            url = BTTV_CDN.format(id=eid, scale="3")
                            # imageType บอก format — gif = animated, png = static
                            is_animated = (em.get("imageType") == "gif")
                            with result._lock:
                                # ถ้าซ้ำกับ FFZ → FFZ ชนะ (เก็บตัวแรก)
                                if name.lower() not in result.emotes:
                                    result.emotes[name.lower()] = {
                                        "name": name,
                                        "url": url,
                                        "url_animated": url,  # BTTV CDN URL เดียวกัน (browser auto-detect gif)
                                        "provider": "bttv",
                                        "animated": is_animated,
                                    }
                # 7TV
                seventv_data = _http_get_json(SEVENTV_USER_URL.format(twitch_id=result.twitch_id))
                if seventv_data:
                    emote_set = seventv_data.get("emote_set", {})
                    for em_entry in emote_set.get("emotes", []):
                        em = em_entry.get("data", {}) or {}
                        name = em.get("name", "")
                        eid = em_entry.get("id") or em.get("id", "")
                        if not name or not eid:
                            continue
                        # 7TV CDN: ใช้ .webp (static) สำหรับ GUI, .gif (animated) สำหรับ OBS
                        # เก็บทั้งสอง URL — GUI เลือกเองตาม context
                        url_static = SEVENTV_CDN_STATIC.format(id=eid, scale="2")
                        url_animated = SEVENTV_CDN_ANIMATED.format(id=eid, scale="2")
                        # ตรวจว่าเป็น animated จริงไหม (flags หรือ animated field)
                        is_animated = bool(em.get("animated", False)) or (em.get("flags", 0) & 1)
                        with result._lock:
                            if name.lower() not in result.emotes:
                                result.emotes[name.lower()] = {
                                    "name": name,
                                    "url": url_static,  # default = static (สำหรับ GUI)
                                    "url_animated": url_animated if is_animated else url_static,
                                    "provider": "7tv",
                                    "animated": is_animated,
                                }
        except Exception:
            pass
        finally:
            result.loaded = True
            if on_done is not None:
                try:
                    on_done(result)
                except Exception:
                    pass

    t = threading.Thread(target=_worker, name=f"thirdparty-emotes-{channel}", daemon=True)
    t.start()
    return result


if __name__ == "__main__":
    # smoke test
    import time
    print("Loading third-party emotes for 'xqc'...")
    done = threading.Event()
    result_ref = [None]

    def _on_done(s):
        result_ref[0] = s
        done.set()

    load_channel_emotes("xqc", _on_done)
    done.wait(timeout=30)
    s = result_ref[0]
    if s:
        print(f"twitch_id: {s.twitch_id}")
        print(f"total emotes: {len(s.emotes)}")
        # breakdown by provider
        from collections import Counter
        providers = Counter(e["provider"] for e in s.emotes.values())
        print(f"by provider: {dict(providers)}")
        # sample
        for name_lower, info in list(s.emotes.items())[:5]:
            print(f"  {info['name']!r:25} [{info['provider']}] {info['url']}")
        # find in text
        print("\nfind_in_text('hello WideHard GAMBA world'):")
        for m in s.find_in_text("hello WideHard GAMBA world"):
            print(f"  {m}")
