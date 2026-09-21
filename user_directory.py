"""user_directory.py — รวมข้อมูลผู้ชมจากทุกแหล่งเป็น UserRecord เดียว (ไม่ผูกกับ Qt)

แหล่งข้อมูล: message_history (แชท) + donate_tracker (ยอดสนับสนุน) + event_log (อีเวนต์)
            + settings (ชื่อที่ตั้งเอง / บล็อก / บังคับแปล)
ใช้โดยหน้า User Manager (ui/dialogs/user_manager.py) และ Profile panel
"""
from __future__ import annotations

import zlib
from dataclasses import dataclass, field
from datetime import datetime

# ── แพลตฟอร์ม ──────────────────────────────────────────────
PLATFORM_ORDER = ["twitch", "youtube", "mylive", "tiktok", "kick", "soop"]
PLATFORM_LABELS = {
    "twitch": "Twitch", "youtube": "YouTube", "mylive": "MyLive",
    "tiktok": "TikTok", "kick": "KICK", "soop": "SOOP",
}
# สีเดียวกับ chat_row (สีที่ผู้ใช้เห็นในฟีดแชท) — ให้ทั้งแอปตรงกัน
PLATFORM_COLORS = {
    "twitch": "#bf94ff", "youtube": "#ff4444", "mylive": "#ff8800",
    "tiktok": "#00f2ea", "kick": "#53fc18", "soop": "#00d9ff",
}
DEFAULT_PLATFORM_COLOR = "#6b7280"

# ── อีเวนต์ ────────────────────────────────────────────────
EVENT_META = {
    "bits": ("💎", "Bits"), "superchat": ("💰", "SuperChat"), "donate": ("💰", "โดเนท"),
    "tip": ("💰", "ทิป"), "gift": ("🎁", "ของขวัญ"), "sub": ("⭐", "Sub"),
    "resub": ("🔁", "Resub"), "subgift": ("🎁", "Gift Sub"),
    "membership": ("🎖️", "Membership"), "sponsor": ("🤝", "Sponsor"),
    "raid": ("🚀", "Raid"), "follow": ("❤️", "ติดตาม"), "like": ("👍", "ไลก์"),
    "share": ("📢", "แชร์"), "join": ("👋", "เข้าห้อง"), "redeem": ("🎯", "แลกรางวัล"),
}
DONATION_EVENTS = {
    "bits", "superchat", "donate", "tip", "gift", "sub", "resub",
    "subgift", "membership", "sponsor",
}
# ชื่อที่จริงๆ เป็นชื่อ event ไม่ใช่คน (กรองออกจากรายชื่อ — ของเดิม + "?" ที่ event_log ใช้แทนไม่ทราบชื่อ)
_FAKE_NAMES = {
    "bits", "donate", "follow", "gift", "like", "share", "sub", "resub", "subgift",
    "raid", "superchat", "membership", "sponsor", "tip", "message", "system", "", "?",
}

REGULAR_MIN_DAYS = 3   # "แชทประจำ" = มาแชทอย่างน้อยกี่วัน

AVATAR_GRADIENTS = [
    ("#7C3AED", "#C084FC"), ("#0EA5E9", "#67E8F9"), ("#F43F5E", "#FDA4AF"),
    ("#10B981", "#6EE7B7"), ("#F59E0B", "#FDE68A"), ("#EC4899", "#F9A8D4"),
    ("#6366F1", "#A5B4FC"), ("#14B8A6", "#5EEAD4"),
]


def avatar_gradient(key: str) -> tuple[str, str]:
    """สี avatar ของคนนี้ — เสถียรข้ามการเปิดโปรแกรม (hash() ของ str สุ่มทุกครั้งที่รัน จึงใช้ crc32)"""
    return AVATAR_GRADIENTS[zlib.crc32((key or "").lower().encode("utf-8")) % len(AVATAR_GRADIENTS)]


def avatar_initial(name: str) -> str:
    """ตัวอักษรบน avatar — ข้ามสระ/วรรณยุกต์นำหน้าที่ไม่ควรอยู่โดดๆ ไม่ได้ ใช้ตัวแรกที่เป็นตัวอักษร/ตัวเลข"""
    for ch in name or "":
        if ch.isalnum():
            return ch.upper()
    return (name or "?")[:1] or "?"


def readable_on(hex_color: str) -> str:
    """สีตัวอักษรที่อ่านออกบนพื้น hex_color"""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return "#0b0e14" if (r * 299 + g * 587 + b * 114) / 1000 > 150 else "#ffffff"


# ── จัดรูปแบบ ──────────────────────────────────────────────
_TH_MONTHS = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
              "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]


def _parse(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts) if ts else None
    except Exception:
        return None


def fmt_int(n: int) -> str:
    return f"{int(n):,}"


def fmt_compact(n: int) -> str:
    """1234 → 1.2k (ให้พอดีในการ์ดเล็ก)"""
    n = int(n)
    if n < 10_000:
        return f"{n:,}"
    if n < 1_000_000:
        return f"{n / 1000:.1f}k".replace(".0k", "k")
    return f"{n / 1_000_000:.1f}M".replace(".0M", "M")


def fmt_date(ts: str) -> str:
    d = _parse(ts)
    return f"{d.day} {_TH_MONTHS[d.month - 1]} {d.year}" if d else "—"


def fmt_datetime_short(ts: str) -> str:
    d = _parse(ts)
    return f"{d.day} {_TH_MONTHS[d.month - 1]} {d:%H:%M}" if d else (ts or "")


def relative_time(ts: str, now: datetime | None = None) -> str:
    """'เมื่อครู่' / '5 นาทีที่แล้ว' / '2 ชม.ที่แล้ว' / 'เมื่อวาน' / '3 วันที่แล้ว' / วันที่เต็ม"""
    d = _parse(ts)
    if not d:
        return "—"
    now = now or datetime.now()
    secs = (now - d).total_seconds()
    if secs < 0:
        return fmt_date(ts)
    if secs < 60:
        return "เมื่อครู่"
    if secs < 3600:
        return f"{int(secs // 60)} นาทีที่แล้ว"
    if secs < 86400 and d.date() == now.date():
        return f"{int(secs // 3600)} ชม.ที่แล้ว"
    days = (now.date() - d.date()).days
    if days == 1:
        return "เมื่อวาน"
    if days < 7:
        return f"{days} วันที่แล้ว"
    return fmt_date(ts)


def event_amount_text(event: str, amount: int) -> str:
    """ยอดของ event พร้อมหน่วย ('' ถ้า event นี้ไม่มียอด)"""
    amount = int(amount or 0)
    if event == "bits":
        return f"{amount:,} bits" if amount else ""
    if event in ("superchat", "donate", "tip"):
        return f"{amount:,} THB" if amount else ""
    if event == "gift":
        return f"{amount:,} เพชร" if amount else ""
    if event == "raid":
        return f"{amount:,} คน" if amount else ""
    if event == "like":
        return f"×{amount:,}" if amount else ""
    return ""


# ── โครงข้อมูล ─────────────────────────────────────────────
@dataclass
class UserRecord:
    key: str                          # author_lower (ใช้เป็น id ทุกที่)
    display: str                      # ชื่อที่แสดง = ชื่อที่ตั้งเอง หรือชื่อเดิม
    original: str                     # ชื่อเดิมตัวพิมพ์จริง (ถ้าไม่เคยเก็บ = key)
    renamed: bool = False
    platforms: list = field(default_factory=list)   # เรียงตามจำนวนข้อความมาก→น้อย
    msg_count: int = 0                # ทั้งหมดตลอดกาล
    retained: int = 0                 # ที่ยังเก็บไว้จริง (สูงสุด 500)
    active_days: int = 0
    first_seen: str = ""
    last_seen: str = ""
    event_count: int = 0
    donate_total: int = 0             # total_donate_count จาก donate_tracker
    supporter: bool = False
    block_status: str | None = None   # None | "block_all" | "block_tts"
    forced_translate: bool = False
    is_new: bool = False              # เห็นครั้งแรกวันนี้
    is_regular: bool = False          # แชทประจำ
    is_bot: bool = False              # อยู่ใน tts_bot_blacklist (Nightbot ฯลฯ)
    search_blob: str = ""

    @property
    def blocked(self) -> bool:
        return self.block_status is not None

    @property
    def hidden_by_default(self) -> bool:
        """บล็อก/บอท → ซ่อนจากรายชื่อปกติ (แท็บ "ถูกบล็อก" หรือสวิตช์ "แสดงบล็อก/บอท" ยังเห็นเสมอ)"""
        return self.block_status is not None or self.is_bot


def _blocked_map(settings) -> dict[str, str]:
    out: dict[str, str] = {}
    for b in getattr(settings, "blocked_users", []) or []:
        if isinstance(b, dict):
            name = (b.get("name") or "").strip().lower()
            if name:
                out[name] = "block_all" if b.get("hide_overlay", True) else "block_tts"
        elif isinstance(b, str) and b.strip():
            out[b.strip().lower()] = "block_all"
    return out


def build_record(app, settings, key: str) -> UserRecord:
    """สร้าง UserRecord ของคนเดียว (ไม่ต้องรวมทั้งรายชื่อ) — ไม่มีข้อมูลเลยก็ได้ record ว่างที่ใช้แสดงผลได้"""
    return build_roster(app, settings, only_key=key)[0]


def build_roster(app, settings=None, only_key: str | None = None) -> list[UserRecord]:
    """รวมผู้ชมทุกคนจากทุกแหล่ง → list[UserRecord] (ยังไม่กรอง/เรียง)

    only_key: ระบุ → ดึงเฉพาะคนนี้ (ผลลัพธ์มี 1 รายการเสมอ แม้ไม่มีข้อมูลเลย)
    """
    settings = settings if settings is not None else getattr(app, "settings", None)
    mh = getattr(app, "message_history", None)
    dt = getattr(app, "donate_tracker", None)
    el = getattr(app, "event_log", None)
    only = only_key.strip().lower() if only_key else None

    renames = {str(k).lower(): v for k, v in (getattr(settings, "user_renames", {}) or {}).items() if v}
    blocked = _blocked_map(settings)
    forced = {str(u).lower() for u in (getattr(settings, "force_translate_users", []) or [])}
    bots = {str(b).strip().lower() for b in (getattr(settings, "tts_bot_blacklist", []) or []) if str(b).strip()}

    # ★ สรุปรายคนจาก message_history (สถิติแยกจากตัวข้อความ → ล้างประวัติข้อความแล้วข้อมูลรายคนยังอยู่ครบ
    #   และไม่ต้อง copy ข้อความทั้งหมดมานับใหม่ทุกครั้งที่เปิดหน้านี้)
    msgs: dict[str, dict] = {}
    if mh is not None:
        try:
            msgs = mh.roster_stats(only)
        except Exception:
            msgs = {}
    donors: dict[str, dict] = {}
    if dt is not None:
        try:
            if only:
                got = dt.get_user(only)
                donors = {only: got} if got else {}
            else:
                donors = dt.all_users()
        except Exception:
            donors = {}

    # event_log: จัดกลุ่มรอบเดียว (เดิมเรียก get_by_author ทีละคน = O(คน × event))
    ev: dict[str, dict] = {}
    if el is not None:
        try:
            source = el.get_by_author(only) if only else el.get_all()
            for e in source:
                k = (e.author or "").lower()
                if not k or (k in _FAKE_NAMES and not only):
                    continue
                s = ev.setdefault(k, {"n": 0, "first": e.timestamp, "last": e.timestamp,
                                      "days": set(), "don": False, "name": e.author, "plats": {}})
                s["n"] += 1
                if e.timestamp < s["first"]:
                    s["first"] = e.timestamp
                if e.timestamp > s["last"]:
                    s["last"] = e.timestamp
                    s["name"] = e.author
                s["days"].add(e.timestamp[:10])
                s["plats"][e.platform] = s["plats"].get(e.platform, 0) + 1
                if e.event in DONATION_EVENTS:
                    s["don"] = True
        except Exception:
            ev = {}

    if only:
        keys = {only}
    else:
        keys = set(renames) | set(blocked) | set(msgs) | set(donors) | set(ev)
        keys = {k for k in keys if k and k not in _FAKE_NAMES}

    today = datetime.now().date().isoformat()
    records: list[UserRecord] = []
    for key in keys:
        m_stat = msgs.get(key)
        e_stat = ev.get(key)

        plat_counts: dict[str, int] = dict(m_stat["plats"]) if m_stat else {}
        days: set[str] = set(m_stat["days"]) if m_stat else set()
        first = (m_stat["first"] if m_stat else "") or ""
        last = (m_stat["last"] if m_stat else "") or ""
        if e_stat:
            for p, n in e_stat["plats"].items():
                if p and p not in plat_counts:
                    plat_counts[p] = 0
            days |= e_stat["days"]
            first = min(x for x in (first, e_stat["first"]) if x) if (first or e_stat["first"]) else ""
            last = max(last, e_stat["last"])

        total_msgs = m_stat["n"] if m_stat else 0
        retained = m_stat["retained"] if m_stat else 0

        donate = donors.get(key, {}) or {}
        donate_total = int(donate.get("total_donate_count", 0) or 0)

        original = ""
        if mh is not None:
            try:
                original = mh.display_name(key)
            except Exception:
                original = ""
        if not original and e_stat:
            original = e_stat["name"] or ""
        original = original or key
        rename = renames.get(key, "")
        display = rename or original

        platforms = sorted(plat_counts, key=lambda p: (-plat_counts[p],
                           PLATFORM_ORDER.index(p) if p in PLATFORM_ORDER else 99, p))
        rec = UserRecord(
            key=key, display=display, original=original, renamed=bool(rename),
            platforms=platforms, msg_count=total_msgs, retained=retained,
            active_days=len(days), first_seen=first, last_seen=last,
            event_count=e_stat["n"] if e_stat else 0,
            donate_total=donate_total,
            supporter=donate_total > 0 or bool(e_stat and e_stat["don"]),
            block_status=blocked.get(key),
            forced_translate=key in forced,
            is_new=bool(first) and first[:10] == today,
            is_regular=len(days) >= REGULAR_MIN_DAYS,
            is_bot=key in bots,
            search_blob=f"{key} {display} {original}".lower(),
        )
        records.append(rec)
    return records


# ── กรอง / เรียง ───────────────────────────────────────────
TABS = ["all", "supporter", "regular", "new", "blocked"]
SORTS = ["recent", "messages", "days", "name", "support"]


def matches(rec: UserRecord, tab: str | None, platform: str | None, query: str | None,
            show_hidden: bool = True) -> bool:
    """tab/platform/query = None → ไม่ใช้เงื่อนไขนั้น (ใช้นับ facet)

    show_hidden=False → ซ่อนบัญชีที่ถูกบล็อก/บอท ยกเว้นตอนเปิดแท็บ "ถูกบล็อก" (แท็บนั้นขอดูพวกนี้โดยตรง)
    """
    if not show_hidden and tab != "blocked" and rec.hidden_by_default:
        return False
    if tab == "supporter" and not rec.supporter:
        return False
    if tab == "regular" and not rec.is_regular:
        return False
    if tab == "new" and not rec.is_new:
        return False
    if tab == "blocked" and not rec.blocked:
        return False
    if platform and platform != "all" and platform not in rec.platforms:
        return False
    if query and query not in rec.search_blob:
        return False
    return True


def sort_records(records: list[UserRecord], mode: str) -> list[UserRecord]:
    if mode == "messages":
        return sorted(records, key=lambda r: (-r.msg_count, r.display.casefold()))
    if mode == "days":
        return sorted(records, key=lambda r: (-r.active_days, -r.msg_count, r.display.casefold()))
    if mode == "name":
        return sorted(records, key=lambda r: r.display.casefold())
    if mode == "support":
        return sorted(records, key=lambda r: (-r.donate_total, -r.msg_count, r.display.casefold()))
    # recent: เห็นล่าสุดก่อน (ไม่มีเวลา → ท้ายสุด)
    return sorted(records, key=lambda r: (r.last_seen == "", _neg_ts(r.last_seen), r.display.casefold()))


def _neg_ts(ts: str):
    """คีย์เรียงเวลาใหม่→เก่า แบบไม่ต้อง parse (กลับค่าตัวอักษรแต่ละตัว)"""
    return tuple(-ord(c) for c in ts)


# ── แบ่งหน้า (pagination) ───────────────────────────────────
PAGE_SIZES = [24, 48, 96, 200]
DEFAULT_PAGE_SIZE = 48


def paginate(total: int, page: int, per_page: int) -> tuple[int, int, int, int]:
    """→ (page, pages, start, end)  หน้านับจาก 0 — page ถูกหนีบให้อยู่ในช่วงเสมอ (รายการหด/หน้าเกิน ก็ไม่พัง)
    start/end = ช่วง index ที่ใช้ slice รายการ"""
    per_page = max(1, int(per_page))
    pages = max(1, -(-max(0, int(total)) // per_page))
    page = min(max(0, int(page)), pages - 1)
    start = page * per_page
    return page, pages, start, min(total, start + per_page)


def page_buttons(cur: int, pages: int) -> list:
    """เลขหน้าที่จะโชว์บนแถบเปลี่ยนหน้า (0-based) เช่น [0, None, 4, 5, 6, None, 39] — None = "…"
    หน้าแรก/หน้าสุดท้ายอยู่เสมอ + หน้าปัจจุบันและข้างเคียง; ช่องว่างแค่ 1 หน้าจะแสดงเลขหน้านั้นแทน "…" """
    if pages <= 7:
        return list(range(pages))
    want = {0, pages - 1, cur - 1, cur, cur + 1}
    if cur <= 2:
        want |= {1, 2, 3}
    if cur >= pages - 3:
        want |= {pages - 2, pages - 3, pages - 4}
    nums = sorted(n for n in want if 0 <= n < pages)
    out: list = []
    for n in nums:
        if out:
            gap = n - out[-1]
            if gap == 2:
                out.append(out[-1] + 1)
            elif gap > 2:
                out.append(None)
        out.append(n)
    return out
