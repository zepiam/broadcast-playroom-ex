"""translator.py — Auto Translate (Google / DeepL / DeepSeek)

รองรับ 3 providers:
  - "google": deep-translator (Google Translate) — ฟรี ไม่ต้อง API key
  - "deepl": DeepL API — ต้อง API key (free 500k ตัว/เดือน)
  - "deepseek": DeepSeek (LLM) — ต้อง API key + host

Rate limit: 20 ครั้ง / 5 นาที — เกินแล้วจะไม่แปลจนกว่าจะหมดเวลา
Translation cache: เก็บคำแปลที่เคยแปลแล้ว → ลด request ไป 50-80%

Usage:
    t = Translator(provider="google", api_key="", target_lang="th")
    result = t.translate("hello world", source_lang="en")
    # result = "สวัสดีชาวโลก" or None (ถ้า fail หรือเกิน rate limit)
"""
from __future__ import annotations

import logging
import time
from typing import Optional

_log = logging.getLogger(__name__)


class RateLimiter:
    """จำกัดจำนวนคำขอในช่วงเวลาหนึ่ง — เกินแล้วปฏิเสธจนกว่าจะหมดเวลา

    ค่า default: 60 ครั้ง / 5 นาที (300 วินาที) — เพียงพอสำหรับ livestream
    """

    def __init__(self, max_requests: int = 60, window_seconds: int = 300):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._timestamps: list[float] = []
        self._rate_limited_until: float = 0  # เวลาที่จะเริ่มแปลได้อีกครั้ง

    def can_request(self) -> bool:
        """ตรวจว่าส่งคำขอได้ไหม — False ถ้าเกิน limit"""
        now = time.time()
        # ถ้ากำลังถูกจำกัดอยู่ → เช็คว่าหมดเวลายัง
        if now < self._rate_limited_until:
            return False
        # ลบ timestamps เก่าออก (เกิน window)
        self._timestamps = [t for t in self._timestamps if now - t < self.window_seconds]
        if len(self._timestamps) >= self.max_requests:
            # เกิน limit → จำกัดจนกว่าจะหมด window
            oldest = self._timestamps[0] if self._timestamps else now
            self._rate_limited_until = oldest + self.window_seconds
            remaining = int(self._rate_limited_until - now)
            _log.warning("Translation rate limited — รออีก %d วินาที", remaining)
            return False
        # บันทึก timestamp
        self._timestamps.append(now)
        return True

    def remaining(self) -> int:
        """จำนวนคำขอที่เหลือใน window ปัจจุบัน"""
        now = time.time()
        self._timestamps = [t for t in self._timestamps if now - t < self.window_seconds]
        return max(0, self.max_requests - len(self._timestamps))

    def cooldown_seconds(self) -> int:
        """วินาทีที่เหลือก่อนจะแปลได้อีก (0 ถ้าไม่ได้ถูกจำกัด)"""
        now = time.time()
        if now < self._rate_limited_until:
            return int(self._rate_limited_until - now)
        return 0


class Translator:
    """รวม translation logic สำหรับ 3 providers"""

    # default host สำหรับ DeepL / DeepSeek
    DEFAULT_HOSTS = {
        "deepl": "https://api-free.deepl.com",
        "deepseek": "https://api.deepseek.com",
    }

    # shared rate limiter + cache (ทุก Translator instance ใช้ร่วมกัน)
    _rate_limiter = RateLimiter(max_requests=60, window_seconds=300)
    _cache: dict[str, str] = {}  # cache_key → translated_text

    def __init__(self, provider: str = "google", api_key: str = "",
                 host: str = "", target_lang: str = "th",
                 supported_langs: list = None):
        self.provider = provider or "google"
        self.api_key = api_key or ""
        self.host = host or self.DEFAULT_HOSTS.get(self.provider, "")
        self.target_lang = target_lang or "th"
        # ภาษาที่รองรับ (สำหรับใส่ใน prompt ของ DeepSeek)
        self.supported_langs = supported_langs or []

    def translate(self, text: str, source_lang: str = "auto") -> Optional[str]:
        """แปล text → target_lang — คืน None ถ้า fail หรือเกิน rate limit

        source_lang: "en", "ja", "ko", ... หรือ "auto" (ให้ provider detect)

        Rate limit: 60 ครั้ง / 5 นาที — เกินแล้วคืน None (ไม่แปล + ไม่อ่าน)
        Cache: เคยแปลแล้ว → ใช้ cache (ไม่นับ rate limit)
        """
        if not text or not text.strip():
            return None
        # ── 1. เช็ค cache ก่อน (ไม่นับ rate limit) ──
        cache_key = f"{self.provider}:{source_lang}:{self.target_lang}:{text[:200]}"
        cached = self._cache.get(cache_key)
        if cached:
            return cached
        # ── 2. เช็ค rate limit ──
        if not self._rate_limiter.can_request():
            return None  # เกิน limit → ไม่แปล
        # ── 3. translate ──
        try:
            if self.provider == "google":
                result = self._translate_google(text, source_lang)
            elif self.provider == "deepl":
                result = self._translate_deepl(text, source_lang)
            elif self.provider == "deepseek":
                result = self._translate_deepseek(text, source_lang)
            else:
                result = self._translate_google(text, source_lang)
            # ── 4. cache ผลลัพธ์ ──
            if result:
                self._cache[cache_key] = result
            return result
        except Exception as exc:
            _log.warning("translate failed (%s): %s", self.provider, exc)
            return None

    # ── Google (deep-translator) ──
    # Google ใช้ "zh-CN" แทน "zh", "iw" แทน "he", "tl" แทน "fil"
    GOOGLE_LANG_MAP = {"zh": "zh-CN", "he": "iw", "fil": "tl"}

    def _translate_google(self, text: str, source_lang: str) -> Optional[str]:
        from deep_translator import GoogleTranslator
        src = "auto" if source_lang == "auto" else self.GOOGLE_LANG_MAP.get(source_lang, source_lang)
        translator = GoogleTranslator(source=src, target=self.target_lang)
        result = translator.translate(text)
        return result if result and result.strip() else None

    # ── DeepL ──
    def _translate_deepl(self, text: str, source_lang: str) -> Optional[str]:
        import requests
        base = self.host.rstrip("/")
        url = f"{base}/v2/translate"
        params = {
            "auth_key": self.api_key,
            "text": text,
            "target_lang": self.target_lang.upper(),
        }
        if source_lang != "auto":
            params["source_lang"] = source_lang.upper()
        resp = requests.post(url, data=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        translations = data.get("translations", [])
        if translations:
            result = translations[0].get("text", "")
            return result if result and result.strip() else None
        return None

    # ── DeepSeek (LLM) ──
    def _translate_deepseek(self, text: str, source_lang: str) -> Optional[str]:
        import requests
        # default host = https://api.deepseek.com (ถ้าไม่ได้ตั้ง)
        base = (self.host or self.DEFAULT_HOSTS["deepseek"]).rstrip("/")
        url = f"{base}/v1/chat/completions"
        # ── สร้าง prompt ตามภาษาที่รองรับ (ตามที่ตั้งใน settings) ──
        # ถ้ามี supported_langs → บอก AI ว่าแปลจากภาษาเหล่านี้เป็นไทย
        if self.supported_langs:
            from flag_utils import LANG_NAMES
            lang_names_th = []
            for code in self.supported_langs:
                name = LANG_NAMES.get(code, code)
                if name and name != "ไทย":  # ไม่รวมไทย (เป็น target)
                    lang_names_th.append(name)
            if lang_names_th:
                lang_list_str = " ".join(lang_names_th)
            else:
                lang_list_str = "ภาษาต่างประเทศทั้งหมด"
        else:
            lang_list_str = "ภาษาต่างประเทศทั้งหมด"
        # prompt ซ่อน — บอก AI ว่าเป็นระบบแปลภาษาสำหรับถ่ายทอดสด
        system_prompt = (
            f"คุณคือระบบแปลภาษาอัตโนมัติสำหรับการถ่ายทอดสดสด (livestream) "
            f"หน้าที่ของคุณคือแปลข้อความแชทจาก {lang_list_str} ให้เป็นภาษาไทย "
            f"เพื่อให้ streamer และผู้ชมชาวไทยเข้าใจได้ทันที\n\n"
            f"กฎสำคัญ:\n"
            f"1. ส่งกลับเฉพาะคำแปลภาษาไทล้วน — ห้ามมีคำอธิบาย ห้ามมีคำศัพท์ ห้ามมีหมายเหตุใดๆ\n"
            f"2. ห้ามใส่เครื่องหมายคำพูด วงเล็บ หรืออักขระพิเศษเพิ่มเติม\n"
            f"3. แปลให้เป็นธรรมชาติ เหมาะกับบริบทแชทสด (สั้น กระชับ เข้าใจง่าย)\n"
            f"4. ถ้าข้อความเป็นภาษาไทยอยู่แล้ว → ส่งกลับเดิมทั้งหมด\n"
            f"5. ถ้าเป็น emoji หรือสัญลักษณ์ → ส่งกลับเดิม\n"
            f"6. ถ้าแปลไม่ได้ (ข้อความว่าง/เป็นโค้ด) → ส่งกลับข้อความเดิม\n\n"
            f"ตอบกลับด้วยคำแปลภาษาไทยเท่านั้น ไม่ต้องพูดอย่างอื่น"
        )
        payload = {
            "model": "deepseek-v4-flash",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            "temperature": 0.1,
            "max_tokens": 500,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices", [])
        if choices:
            result = choices[0].get("message", {}).get("content", "").strip()
            # ทำความสะอาดผลลัพธ์ — ลบเครื่องหมายคำพูดที่ AI อาจใส่มา
            if result and len(result) >= 2:
                if (result.startswith('"') and result.endswith('"')) or \
                   (result.startswith("'") and result.endswith("'")):
                    result = result[1:-1].strip()
            return result if result else None
        return None


if __name__ == "__main__":
    # smoke test
    t = Translator(provider="google", target_lang="th")
    tests = [
        ("hello world", "en"),
        ("こんにちは", "ja"),
        ("안녕하세요", "ko"),
        ("你好世界", "zh"),
    ]
    for text, lang in tests:
        result = t.translate(text, source_lang=lang)
        print(f"  {lang}: {text!r} → {result!r}")
    print("✅ translator OK")
