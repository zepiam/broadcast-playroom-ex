"""language_detect.py — ตรวจจับภาษาจาก Unicode script ranges

ใช้นับตัวอักษรในแต่ละ Unicode range เพื่อหาภาษาหลักของข้อความ
(edge-tts อ่านทั้งข้อความด้วย voice เดียว → เลือก voice ตามภาษาที่เยอะสุด)

รองรับ 7 ภาษา: ไทย / อังกฤษ / ญี่ปุ่น / เกาหลี / จีน / จีนไต้หวัน / ฝรั่งเศส
"""
from __future__ import annotations


# edge-tts voice ID สำหรับแต่ละภาษา (คัดมาแล้ว — Neural voice เสียงดี)
VOICE_BY_LANG: dict[str, str] = {
    "th": "th-TH-PremwadeeNeural",  # ไทย
    "en": "en-US-AriaNeural",       # อังกฤษ
    "ja": "ja-JP-NanamiNeural",     # ญี่ปุ่น
    "ko": "ko-KR-SunHiNeural",      # เกาหลี
    "zh": "zh-CN-XiaoxiaoNeural",   # จีนกลาง
    "zh-TW": "zh-TW-HsiaoChenNeural",  # จีนไต้หวัน
    "fr": "fr-FR-DeniseNeural",     # ฝรั่งเศส
}


def _char_lang(ch: str) -> str | None:
    """แมปตัวอักษร 1 ตัว → รหัสภาษา หรือ None ถ้าไม่ใช่ภาษาที่รู้จัก

    Unicode ranges:
      Thai:       \\u0E00-\\u0E7F
      Hangul:     \\uAC00-\\uFFD7AF, \\u1100-\\u11FF, \\u3130-\\u318F
      Hiragana:   \\u3040-\\u309F
      Katakana:   \\u30A0-\\u30FF
      CJK:        \\u4E00-\\u9FFF (แยกจีน/ญี่ปุ่นไม่ได้ → default ja แต่เก็บเป็น "ja")
      Latin accented: À-ÿ → fr (ฝรั่งเศส หรือละตินแบบมี accent)
      Latin/ASCII: A-Z a-z → en
    """
    cp = ord(ch)
    # ไทย
    if 0x0E00 <= cp <= 0x0E7F:
        return "th"
    # เกาหลี (Hangul syllables + jamo + compatibility)
    if 0xAC00 <= cp <= 0xD7AF or 0x1100 <= cp <= 0x11FF or 0x3130 <= cp <= 0x318F:
        return "ko"
    # ญี่ปุ่น (Hiragana + Katakana)
    if 0x3040 <= cp <= 0x30FF:
        return "ja"
    # CJK unified ideographs → ถือว่า ja (แยกจีน/ญี่ปุ่นยาก)
    # ผู้ใช้สามารถเลือกว่าจะให้แปลเป็น ja หรือ zh ใน settings
    if 0x4E00 <= cp <= 0x9FFF:
        return "ja"
    # ละตินแบบมี accent (À-ÿ) → อาจเป็นฝรั่งเศส
    if 0x00C0 <= cp <= 0x00FF:
        return "fr"
    # ASCII/Latin พื้นฐาน (A-Z a-z) → อังกฤษ
    # สำคัญ: ต้องจำกัดเฉพาะ ASCII เท่านั้น — ไม่ใช่ isalpha() ทุกตัว
    # (เพราะ isalpha() จับฮินดี/อาหรับ/รัสเซียเป็น en ด้วย → ทำให้ TTS error)
    if 0x0041 <= cp <= 0x005A or 0x0061 <= cp <= 0x007A:  # A-Z / a-z
        return "en"
    return None  # ภาษาอื่น (ฮินดี/อาหรับ/รัสเซีย) + ตัวเลข/วรรคตอน/emoji → ไม่รู้จัก



def detect_language(text: str) -> str:
    """ตรวจจับภาษาหลักของข้อความ → คืน 'th' | 'en' | 'ja' | 'ko' | 'zh' | ... | 'unknown'

    นับตัวอักษรในแต่ละ Unicode range → ภาษาที่นับได้เยอะสุด = ภาษาหลัก
    - ถ้าไม่มีตัวอักษรที่ตรวจได้ (เป็นตัวเลข/emoji/ว่างทั้งหมด) → 'th' (default — ไม่มีเนื้อหา)
    - ถ้าเป็นภาษาที่ไม่รู้จัก (ฮินดี/อาหรับ/รัสเซีย) → 'unknown' (จะถูก skip TTS ปลอดภัย)
    """
    if not text:
        return "th"
    counts: dict[str, int] = {}
    has_unknown_script = False  # มีตัวอักษรที่ isalpha=True แต่ไม่ใช่ภาษาที่รู้จัก
    for ch in text:
        lang = _char_lang(ch)
        if lang:
            counts[lang] = counts.get(lang, 0) + 1
        elif ch.isalpha():
            # ตัวอักษรที่เป็น alpha แต่ไม่ใช่ภาษาที่รู้จัก → ภาษาอื่น (ฮินดี/อาหรับ/ฯลฯ)
            has_unknown_script = True
    if counts:
        # หาภาษาที่มากสุด
        return max(counts, key=counts.get)
    # ไม่มีภาษาที่รู้จักเลย
    if has_unknown_script:
        return "unknown"  # ภาษาที่ไม่รองรับ → caller จะ skip TTS
    return "th"  # ไม่มีเนื้อหาเลย (ตัวเลข/emoji/ว่าง) → default ไทย
