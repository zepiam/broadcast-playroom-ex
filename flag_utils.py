"""flag_utils.py — แปลง language code → flag emoji + ชื่อภาษาไทย"""
from __future__ import annotations

# language code → flag emoji
LANG_FLAGS: dict[str, str] = {
    "th": "🇹🇭", "en": "🇺🇸", "ja": "🇯🇵", "ko": "🇰🇷", "zh": "🇨🇳",
    "zh-CN": "🇨🇳", "zh-TW": "🇹🇼", "vi": "🇻🇳", "id": "🇮🇩", "ms": "🇲🇾",
    "fr": "🇫🇷", "de": "🇩🇪", "es": "🇪🇸", "ru": "🇷🇺", "pt": "🇧🇷",
    "it": "🇮🇹", "ar": "🇸🇦", "hi": "🇮🇳", "tr": "🇹🇷", "nl": "🇳🇱",
    "pl": "🇵🇱", "sv": "🇸🇪", "uk": "🇺🇦", "fil": "🇵🇭", "lo": "🇱🇦",
    "my": "🇲🇲", "bn": "🇧🇩", "fa": "🇮🇷", "he": "🇮🇱",
}

# language code → ชื่อภาษาไทย
LANG_NAMES: dict[str, str] = {
    "th": "ไทย", "en": "อังกฤษ", "ja": "ญี่ปุ่น", "ko": "เกาหลี", "zh": "จีน",
    "zh-CN": "จีนกลาง", "zh-TW": "ไต้หวัน", "vi": "เวียดนาม", "id": "อินโดนีเซีย",
    "ms": "มาเลย์", "fr": "ฝรั่งเศส", "de": "เยอรมัน", "es": "สเปน", "ru": "รัสเซีย",
    "pt": "โปรตุเกส", "it": "อิตาลี", "ar": "อาหรับ", "hi": "ฮินดี", "tr": "ตุรกี",
    "nl": "ดัตช์", "pl": "โปแลนด์", "sv": "สวีเดน", "uk": "ยูเครน", "fil": "ฟิลิปปินส์",
    "lo": "ลาว", "my": "พม่า", "bn": "เบงกาลี", "fa": "เปอร์เซีย",
    "he": "ฮีบรู",
}


def flag_for(lang: str) -> str:
    """คืน flag emoji ของภาษา — fallback 🌐 ถ้าไม่เจอ"""
    return LANG_FLAGS.get(lang, LANG_FLAGS.get(lang.split("-")[0], "🌐"))


def name_for(lang: str) -> str:
    """คืนชื่อภาษาไทย — fallback รหัสเดิม ถ้าไม่เจอ"""
    return LANG_NAMES.get(lang, LANG_NAMES.get(lang.split("-")[0], lang))


def lang_options() -> list[tuple[str, str]]:
    """list ของ (code, ชื่อไทย + flag) สำหรับ checkbox ใน Setting"""
    return [(code, f"{flag} {name}") for code, name in LANG_NAMES.items() if code != "th"]
