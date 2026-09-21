"""event_details.py — รายละเอียดของ event (sub / donate / gift / raid ...) สำหรับหน้าจอ "กดดูรายละเอียด"

แต่ละแพลตฟอร์มส่งข้อมูลมาไม่เหมือนกัน — chat_*.py ใส่ข้อมูลเชิงโครงสร้างไว้ใน ``msg.extra["detail"]``
(เช่น Twitch: months / streak / recipient, YouTube: purchase_amount / currency ...) ไฟล์นี้รวมทุกแหล่ง
(detail + msg.amount/tier/system_text + extra เดิมอย่าง TikTok gift_name) ให้เป็น dict เดียวที่ JSON ได้:

    info = build_info(msg)
    info["headline"]   สรุปบรรทัดเดียว เช่น "ซับต่อ 14 เดือน · Tier 1"
    info["fields"]     [[ป้าย, ค่า], ...] เฉพาะข้อมูลที่ "มี" จริง (ไม่มีก็ไม่แสดงแถวนั้น ไม่เดา)
    info["message"]    ข้อความที่ผู้ให้แนบมา (ถ้ามี)

เก็บลง event_log ทั้งก้อน (EventEntry.detail) → เปิดดูย้อนหลังได้หลังรีสตาร์ท
ไม่พึ่ง Qt — ทดสอบได้ตรงๆ
"""
from __future__ import annotations

import re
from datetime import datetime

# event → (ไอคอน, ป้ายชื่อ, หมวด)   หมวด: money (เงิน/ของขวัญ) | sub (สมาชิก) | gift (มอบซับ) | other
EVENT_META = {
    "sub": ("⭐", "Subscribe", "sub"),
    "resub": ("🔁", "Resub (ซับต่อเนื่อง)", "sub"),
    "subgift": ("🎁", "Gift Sub (มอบซับ)", "gift"),
    "membership": ("🎖️", "สมาชิกช่อง (Membership)", "sub"),
    "member": ("🎖️", "สมาชิกช่อง (Membership)", "sub"),
    "sponsor": ("🤝", "Sponsor", "sub"),
    "bits": ("💎", "Bits", "money"),
    "superchat": ("💎", "Super Chat", "money"),
    "gift": ("🎁", "ของขวัญ", "money"),
    "donate": ("💰", "Donate", "money"),
    "tip": ("💰", "Tip", "money"),
    "raid": ("🚀", "Raid", "other"),
    "follow": ("❤️", "Follow", "other"),
    "like": ("👍", "Like", "other"),
    "share": ("📢", "Share", "other"),
    "join": ("👋", "เข้าห้อง", "other"),
    "redeem": ("🎯", "แลกของรางวัล (Channel Points)", "other"),
}

PLATFORM_NAMES = {
    "twitch": "Twitch", "youtube": "YouTube", "kick": "KICK",
    "tiktok": "TikTok", "mylive": "MyLive", "soop": "SOOP",
}

# MyLive ส่งทุกอย่างเป็น event "bits" + detail.kind
_MYLIVE_KINDS = {"gift": "ส่งของขวัญ", "tip": "บริจาค", "subscribe": "สมัครสมาชิก"}


def _int(v):
    try:
        if v is None or v == "":
            return None
        return int(float(str(v).strip().replace(",", "")))
    except (ValueError, TypeError):
        return None


def _s(v) -> str:
    return "" if v is None else str(v).strip()


def _tier_text(tier, plan_name: str = "") -> str:
    t = _int(tier)
    if t is None:
        return ""
    return "Prime" if t == 0 else f"Tier {t}"


def _months_text(n) -> str:
    n = _int(n)
    return f"{n:,} เดือน" if n is not None else ""


def _recipients(d: dict) -> list:
    r = d.get("recipients")
    if isinstance(r, (list, tuple)):
        out = [_s(x) for x in r if _s(x)]
        if out:
            return out
    one = _s(d.get("recipient"))
    return [one] if one else []


def _names_text(names: list, limit: int = 6) -> str:
    if len(names) <= limit:
        return ", ".join(names)
    return ", ".join(names[:limit]) + f" และอีก {len(names) - limit:,} คน"


def kind_of(event: str, platform: str = "", detail: dict | None = None) -> tuple[str, str, str]:
    """(icon, label, category) ของ event นี้ — MyLive แยกตามชนิดจริงที่หน้าเว็บส่งมา"""
    icon, label, cat = EVENT_META.get(event, ("🔔", event or "Event", "other"))
    if platform == "mylive" and event in ("bits", "sub"):
        k = _s((detail or {}).get("kind"))
        if k in _MYLIVE_KINDS:
            label = f"{_MYLIVE_KINDS[k]} (MyLive)"
            icon = {"gift": "🎁", "tip": "💰", "subscribe": "⭐"}[k]
            cat = "sub" if k == "subscribe" else "money"
    if platform == "twitch" and event == "bits":
        label = "Bits (Cheer)"
    if platform == "kick" and event == "bits":
        label = "KICKs (ทิป)"
        icon = "💚"
    if platform == "tiktok" and event == "gift":
        label = "ของขวัญ TikTok"
    return icon, label, cat


def build_info(msg) -> dict:
    """ChatMessage (event != message) → dict รายละเอียดที่พร้อมแสดง/เก็บ"""
    event = _s(getattr(msg, "event", "")) or "event"
    platform = _s(getattr(msg, "platform", ""))
    author = _s(getattr(msg, "author", "")) or "?"
    extra = getattr(msg, "extra", None) or {}
    d = dict(extra.get("detail") or {}) if isinstance(extra.get("detail"), dict) else {}
    amount = _int(getattr(msg, "amount", None))
    tier = getattr(msg, "tier", None)
    system_text = _s(getattr(msg, "system_text", ""))
    text = _s(getattr(msg, "text", ""))

    icon, label, cat = kind_of(event, platform, d)
    fields: list[list[str]] = []

    def add(name: str, value) -> None:
        v = _s(value)
        if v:
            fields.append([name, v])

    headline = label

    # ── ซับ / ซับต่อเนื่อง / สมาชิก ──
    if event in ("sub", "resub", "membership", "member", "sponsor"):
        months = _int(d.get("months"))
        if months is None and event == "resub":
            m = re.search(r"(\d+)\s+months?", system_text, re.I)   # เผื่อ detail ไม่มี (เก็บจากข้อความระบบ)
            months = _int(m.group(1)) if m else None
        streak = _int(d.get("streak_months"))
        tier_t = _tier_text(d.get("tier", tier), d.get("plan_name", ""))
        add("ระดับ (Tier)", tier_t)
        add("แผนสมาชิก", d.get("plan_name"))
        if months is not None:
            add("ซับมาแล้วรวม", _months_text(months))
        elif event == "sub":
            add("ซับมาแล้วรวม", "เดือนแรก (ซับใหม่)")
        if streak:
            add("ซับต่อเนื่องติดกัน", _months_text(streak))
        add("ระยะเวลาที่ซื้อ", _months_text(d.get("gift_months")) if _int(d.get("gift_months")) and _int(d.get("gift_months")) > 1 else "")
        if platform == "youtube":
            add("สถานะสมาชิก", d.get("header"))
        base = {"sub": "สมัครซับ", "resub": "ซับต่อ", "membership": "สมัครสมาชิกช่อง", "member": "สมัครสมาชิกช่อง",
                "sponsor": "Sponsor"}[event]
        if event in ("member", "membership") and months:
            base = f"สมาชิกครบ {months:,} เดือน"
        parts = [f"{base} {months:,} เดือน" if (event == "resub" and months) else base]
        if tier_t:
            parts.append(tier_t)
        headline = " · ".join(parts)

    # ── มอบซับ ──
    elif event == "subgift":
        names = _recipients(d)
        count = _int(d.get("count")) or (len(names) if len(names) > 1 else None)
        gifter_view = d.get("is_gifter")
        if names:
            add("มอบให้" if gifter_view is not False else "ผู้รับ", _names_text(names))
        add("จำนวนที่มอบ", f"{count:,} ซับ" if count and count > 1 else ("1 ซับ" if names or count == 1 else ""))
        gm = _int(d.get("gift_months"))
        add("ระยะเวลาต่อซับ", _months_text(gm) if gm and gm > 1 else "")
        add("ระดับ (Tier)", _tier_text(d.get("tier", tier), d.get("plan_name", "")))
        add("แผนสมาชิก", d.get("plan_name"))
        add("ผู้รับซับมาแล้วรวม", _months_text(d.get("months")))
        st = _int(d.get("sender_total"))
        add("คนนี้มอบไปแล้วรวมทั้งหมด", f"{st:,} ซับ" if st else "")
        if d.get("anonymous"):
            add("หมายเหตุ", "มอบแบบไม่ระบุตัวตน")
        if names and (count or 1) <= 1:
            headline = f"มอบซับให้ {names[0]}"
        elif count and count > 1:
            headline = f"มอบซับ ×{count:,}" + (f" (เช่น {names[0]})" if names else "")
        else:
            headline = "มอบซับ"

    # ── Bits / ทิป / บริจาค ──
    elif event == "bits":
        if platform == "twitch":
            n = amount if amount is not None else _int(d.get("bits"))
            add("จำนวน Bits", f"{n:,}" if n is not None else "")
            headline = f"ส่ง {n:,} Bits" if n else "ส่ง Bits"
        elif platform == "kick":
            add("จำนวน KICKs", f"{amount:,}" if amount else "")
            add("ชื่อของขวัญ", d.get("gift_name"))
            headline = f"ส่ง {amount:,} KICKs" if amount else "ส่ง KICKs"
        else:   # MyLive gift/tip
            k = _s(d.get("kind"))
            add("ชนิด", _MYLIVE_KINDS.get(k, "") or system_text)
            if amount:
                add("จำนวน", f"{amount:,}")
            headline = label
    elif event == "superchat":
        disp = _s(d.get("amount_display") or d.get("purchase_amount") or extra.get("purchase_amount")
                  or (extra.get("amount") if isinstance(extra.get("amount"), str) else ""))
        cur = _s(d.get("currency") or extra.get("currency"))
        if disp:
            add("มูลค่า", disp + (f"  ({cur})" if cur and cur not in disp else ""))
        elif amount is not None:
            add("มูลค่า", f"{amount:,} {cur}".strip())
        if d.get("sticker"):
            add("สติกเกอร์", d.get("sticker"))
        base = "Super Sticker" if d.get("header") == "Super Sticker" else "Super Chat"
        headline = f"{base} {disp or (f'{amount:,} {cur}'.strip() if amount is not None else '')}".strip()
    elif event in ("donate", "tip"):
        cur = _s(d.get("currency"))
        if amount is not None:
            add("มูลค่า", f"{amount:,} {cur}".strip())
        headline = f"{label} {amount:,} {cur}".strip() if amount is not None else label

    # ── ของขวัญ (TikTok) ──
    elif event == "gift":
        name = _s(d.get("gift_name") or extra.get("gift_name"))
        rep = _int(d.get("repeat_count") or extra.get("repeat_count")) or 1
        each = _int(d.get("diamond_count") or extra.get("diamond_count"))
        total = amount if amount is not None else (each * rep if each else None)
        add("ของขวัญ", name)
        add("จำนวน", f"×{rep:,}")
        add("เพชรต่อชิ้น", f"{each:,}" if each else "")
        add("เพชรรวม", f"{total:,}" if total else "")
        headline = f"{name or 'ของขวัญ'} ×{rep:,}" + (f" ({total:,} เพชร)" if total else "")

    # ── Raid / Follow / Like / Share / Join / Redeem ──
    elif event == "raid":
        n = amount if amount is not None else _int(d.get("viewers"))
        add("ผู้ชมที่พามาด้วย", f"{n:,} คน" if n is not None else "")
        headline = f"Raid {n:,} คน" if n is not None else "Raid"
    elif event == "like":
        n = amount if amount is not None else _int(d.get("count"))
        add("จำนวนที่กด", f"{n:,}" if n is not None else "")
        headline = f"กดหัวใจ {n:,}" if n else "กดหัวใจ"
    elif event == "redeem":
        title = _s(d.get("reward_title") or extra.get("reward_title"))
        cost = _int(d.get("reward_cost") or extra.get("reward_cost"))
        add("รางวัลที่แลก", title)
        add("ราคา (Channel Points)", f"{cost:,}" if cost else "")
        headline = f"แลก “{title}”" if title else "แลกของรางวัล"
    elif event == "follow":
        headline = "ติดตามช่อง"
    elif event == "share":
        headline = "แชร์ไลฟ์"
    elif event == "join":
        headline = "เข้าห้อง"
    else:
        headline = system_text or label

    return {
        "v": 1,
        "event": event,
        "platform": platform,
        "author": author,
        "ts": datetime.now().isoformat(timespec="seconds"),
        "icon": icon,
        "label": label,
        "category": cat,
        "headline": headline,
        "amount": amount or 0,
        "message": text,
        "system_text": system_text,
        "fields": fields,
    }


def from_entry(entry) -> dict:
    """EventEntry จาก event_log → info dict (ของเก่าที่ไม่มี detail ก็ได้ข้อมูลเท่าที่มี)"""
    d = getattr(entry, "detail", None)
    if isinstance(d, dict) and d.get("v"):
        info = dict(d)
        info.setdefault("ts", getattr(entry, "timestamp", ""))
        return info
    event = _s(getattr(entry, "event", ""))
    icon, label, cat = kind_of(event, _s(getattr(entry, "platform", "")))
    amount = _int(getattr(entry, "amount", 0)) or 0
    fields = []
    if amount:
        fields.append(["จำนวน", f"{amount:,}"])
    return {
        "v": 1, "event": event, "platform": _s(getattr(entry, "platform", "")),
        "author": _s(getattr(entry, "author", "")) or "?", "ts": _s(getattr(entry, "timestamp", "")),
        "icon": icon, "label": label, "category": cat,
        "headline": _s(getattr(entry, "display_text", "")) or label, "amount": amount,
        "message": _s(getattr(entry, "message", "")), "system_text": _s(getattr(entry, "system_text", "")),
        "fields": fields,
    }
