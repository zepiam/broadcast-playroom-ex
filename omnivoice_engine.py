"""omnivoice_engine.py — Wrapper สำหรับ OmniVoice TTS (offline, zero-shot, 600+ languages)

ทำงาน:
- โหลดโมเดล OmniVoice ครั้งเดียว (~36s, 2.45GB)
- generate(text, on_done, on_error) — เลียนแบบ TTSEngine API (callback-based)
- ส่งคืน WAV bytes (numpy 24kHz → resample 44100Hz → WAV) เพื่อเข้ากับ _decode pipeline เดิม

★ Lazy import: ถ้า Lite build ไม่มี omnivoice/torch → import fail ก็ไม่ crash (caller เช็ต is_available)

Usage:
    engine = OmniVoiceEngine(instruct="female")
    engine.generate(text, on_done=callback, on_error=err_callback)
"""
from __future__ import annotations

# ★ PyInstaller warm-up ย้ายไป main.py แล้ว (ต้องทำก่อน import omnivoice)

import io
import logging
import threading
from typing import Callable, Optional

logger = logging.getLogger("omnivoice_engine")

# ★ sample rate เป้าหมาย (ตาม pipeline ที่ใช้ 44100)
TARGET_SR = 44100
# ★ OmniVoice ส่งคืน 24kHz
OMNIVOICE_SR = 24000

# ★ guidance_scale ต่ำกว่า default ของโมเดล (2.0) — ลดความ "ใส่อารมณ์" ที่โมเดลชอบทำเอง
#   ทดสอบฟังเทียบหลายค่าจริงแล้วเลือก 0.5 เป็นจุดที่นิ่งสุดโดยยังฟังเป็นธรรมชาติ (ต่ำกว่านี้
#   เริ่มหลุด/ไม่เป็นธรรมชาติ) — สำคัญเพราะเสียงนี้จะถูกส่งต่อเข้า RVC อีกที ถ้าต้นทางมีอารมณ์
#   ขึ้นๆ ลงๆ RVC จะพาอารมณ์นั้นติดไปด้วย ไม่ได้ทำให้เสียงนิ่งขึ้นเอง
OMNIVOICE_GUIDANCE_SCALE = 0.5


class OmniVoiceEngine:
    """Wrapper สำหรับ OmniVoice TTS — เลียนแบบ TTSEngine API"""

    # ★ valid instruct values (จากการทดสอบ)
    VALID_INSTRUCTS = {
        "male": "male",
        "female": "female",
        "child": "child",
        "teenager": "teenager",
        "elderly": "elderly",
        "young_adult": "young adult",
        "middle_aged": "middle-aged",
    }

    def __init__(self, instruct: str = "female", device: str = "cuda:0", dtype=None,
                 language: str = "Thai", speed: float = 1.0, normalize_text: bool = True):
        """โหลดโมเดล OmniVoice

        Args:
            instruct: "male" | "female" | "child" (เปลี่ยนได้ภายหลังด้วย set_instruct)
            device: "cuda:0" | "cpu" (default = cuda ถ้ามี)
            dtype: torch.float16 (default) หรือ torch.float32
            language: ภาษาที่จะอ่าน — "Thai" (default) / "English" / "Chinese" / None (auto)
                      ★ ระบุให้ชัดเจนจะทำให้โมเดลออกเสียงเป็นธรรมชาติขึ้นมาก
            speed: อัตราการพูด 1.0=ปกติ, 0.9=ช้าลง(ชัดขึ้น), 1.1=เร็วขึ้น
            normalize_text: True = แปลงตัวเลข/วันที่/เงินตรา → คำอ่าน (๒๓๔๕ → สองพัน...)
        """
        self._instruct = instruct
        self._device = device
        self._model = None
        self._loaded = False
        self._lock = threading.Lock()
        # ★ TTS quality params (ส่งให้ model.generate)
        self._language = language
        self._speed = speed
        self._normalize_text = normalize_text

        # ★ TTS audio cache — ข้อความซ้ำ → เล่นเสียงเดิม (ไม่ต้อง synth ใหม่)
        #   key = (text_lower, instruct) → value = WAV bytes
        #   ★ cache เฉพาะข้อความสั้น (≤80 ตัวอักษร) — ยาวเกินไม่ cache (กิน RAM)
        #   ★ TTL 5 นาที + max 200 entries (LRU eviction)
        import collections, time as _time
        self._audio_cache = collections.OrderedDict()
        self._audio_cache_max = 200
        self._audio_cache_ttl = 300.0  # 5 นาที
        self._max_cache_text_len = 80

        # ★ lazy import torch + omnivoice (Lite build ไม่มี)
        try:
            import torch
            self._torch = torch
            if dtype is None:
                dtype = torch.float16
            self._dtype = dtype
            # ★ ตรวจ CUDA
            if device.startswith("cuda") and not torch.cuda.is_available():
                self._device = "cpu"
                logger.info("CUDA not available — falling back to CPU")
        except ImportError as e:
            raise ImportError(f"torch not available: {e}")

        # ★ โหลดโมเดอืทันที (lazy load ทำใน app.py — ถ้าเรียก __init__ แปลว่าต้องการใช้)
        self._load_model()

    def _load_model(self):
        """โหลดโมเดล OmniVoice จาก HuggingFace (no progress callback)"""
        self.load_with_progress(on_progress=None)

    def load_with_progress(self, on_progress: Optional[Callable[[int, str], None]] = None):
        """โหลดโมเดล OmniVoice แบบ manual stages — รายงาน % จริง

        Args:
            on_progress: callback(percent: int 0-100, stage_text: str) — เรียกหลังแต่ละ stage
                         None = ไม่รายงาน (เหมือน _load_model เดิม)

        ★ stages (วัดจากการทดสอบจริง — cache แล้วใช้เวลา ~2-8s, ครั้งแรก ~30-40s):
          0-5%   : resolve path (เช็ค cache / download metadata)
          5-55%  : load main model (safetensors 2.45GB — นานสุด)
          55-70% : text tokenizer
          70-90% : audio tokenizer (HiggsAudioV2)
          90-100%: feature extractor + ready
        """
        def _report(pct, text):
            if on_progress:
                try:
                    on_progress(pct, text)
                except Exception:
                    pass

        try:
            _report(2, "กำลังเตรียมไฟล์โมเดล...")
            from omnivoice import OmniVoice
            # ★ PyInstaller fix: import HiggsAudioV2TokenizerModel จาก transformers ตรงๆ
            #   (ไม่ผ่าน omnivoice.models.omnivoice ที่ใช้ transformers LazyModule)
            from omnivoice.models.omnivoice import (
                _resolve_model_path, AutoTokenizer, AutoFeatureExtractor,
                RuleDurationEstimator,
            )
            # ★ import HiggsAudioV2TokenizerModel จาก full path (ทำงานใน PyInstaller)
            from transformers.models.higgs_audio_v2_tokenizer.modeling_higgs_audio_v2_tokenizer import (
                HiggsAudioV2TokenizerModel,
            )
            import os as _os
            import logging as _logging

            logger.info("Loading OmniVoice model with progress...")

            # ── Stage 1: resolve path ──
            _report(5, "กำลังเช็คแคชโมเดล...")
            _prev_disable = _logging.root.manager.disable
            _logging.disable(_logging.INFO)
            try:
                resolved_path = _resolve_model_path("k2-fsa/OmniVoice")

                # ── Stage 2: load full model (from_pretrained ปกติ — โหลดครบทุกส่วน) ──
                # ★ ใช้ from_pretrained แบบปกติ ไม่ใช้ train=True (train=True ข้าม tokenizers → dtype mismatch)
                #   progress bar จะวิ่งเร็วเพราะเป็น single call แต่ก็แม่นยำกว่า (ไม่พัง)
                _report(10, "กำลังโหลดโมเดลหลัก (2.45GB)...")
                # ★ timer thread เพื่อ update progress ระหว่างโหลด (กัน user คิดว่าค้าง)
                import threading as _th
                _stop_timer = _th.Event()
                _progress_val = [10]
                def _timer():
                    while not _stop_timer.is_set():
                        # ★ ค่อยๆ ขยาย progress จาก 10→90 ระหว่างโหลด (heuristic)
                        if _progress_val[0] < 90:
                            _progress_val[0] += 1
                            _report(_progress_val[0], "กำลังโหลดโมเดลหลัก...")
                        _stop_timer.wait(0.5)
                _timer_thread = _th.Thread(target=_timer, daemon=True)
                _timer_thread.start()

                model = OmniVoice.from_pretrained(
                    resolved_path,
                    device_map=self._device,
                    dtype=self._dtype,
                )

                _stop_timer.set()
                _report(100, "พร้อมใช้งาน")

                self._model = model
                self._loaded = True
                logger.info(f"OmniVoice loaded successfully (device={self._device}, dtype={self._dtype})")
            finally:
                _logging.disable(_prev_disable)

        except Exception as e:
            logger.error(f"Failed to load OmniVoice: {e}", exc_info=True)
            raise

    def set_instruct(self, instruct: str):
        """เปลี่ยนเสียง (male/female/child) โดยไม่ต้องโหลดโมเดลใหม่"""
        self._instruct = instruct

    def set_language(self, language: str):
        """เปลี่ยนภาษาที่จะอ่าน — "Thai" / "English" / "Chinese" / None (auto)"""
        self._language = language

    def set_speed(self, speed: float):
        """ปรับอัตราการพูด — 1.0=ปกติ, 0.9=ช้าลง, 1.1=เร็วขึ้น"""
        self._speed = max(0.5, min(2.0, speed))

    def _resolve_language(self, text: str) -> str:
        """ตัดสินใจภาษาที่จะส่งให้ OmniVoice

        ★ ถ้า user ระบุ language ไว้ → ใช้ค่านั้น
        ★ ถ้าไม่ระบุ (None) → auto-detect จากข้อความ
          - มีอักษรไทย → "Thai"
          - มี CJK → "Chinese"
          - อื่นๆ → "English"
        """
        if self._language:
            return self._language
        # auto-detect
        for ch in text:
            if '\u0E00' <= ch <= '\u0E7F':
                return "Thai"
            if '\u4E00' <= ch <= '\u9FFF':
                return "Chinese"
        return "English"

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def current_instruct(self) -> str:
        return self._instruct

    def _make_generation_config(self):
        """คืน OmniVoiceGenerationConfig ที่ลด guidance_scale ลง — ดู OMNIVOICE_GUIDANCE_SCALE"""
        from omnivoice.models.omnivoice import OmniVoiceGenerationConfig
        return OmniVoiceGenerationConfig(guidance_scale=OMNIVOICE_GUIDANCE_SCALE)

    def generate(
        self,
        text: str,
        on_done: Callable[[bytes], None],
        on_error: Callable[[str], None],
    ) -> None:
        """สร้างเสียง TTS — callback-based (เหมือน TTSEngine)

        Args:
            text: ข้อความที่จะอ่าน
            on_done: callback รับ WAV bytes (44100Hz mono)
            on_error: callback รับ error message
        """
        if not self._loaded or self._model is None:
            on_error("OmniVoice not loaded")
            return
        if not text.strip():
            on_error("empty text")
            return

        # ★ ทำงานใน thread ปัจจุบัน (pipeline เรียกจาก _compute_thread อยู่แล้ว)
        try:
            # ★ cache ปิดแล้ว — OmniVoice แปลงข้อความสั้นๆ ไม่ค่อยดี + cache เก็บเสียงเพี้ยน
            #   แปลงใหม่ทุกครั้งดีกว่า (เสียงคมชัดกว่า ไม่มีปัญหาเสียงซ่า)
            with self._lock:
                # ★ resolve instruct → model.generate parameter (default = female)
                instruct_val = self.VALID_INSTRUCTS.get(self._instruct, "female")
                # ★ ระบุภาษาให้ชัดเจน → โมเดลออกเสียงเป็นธรรมชาติขึ้นมาก
                #   ถ้าไม่ระบุ OmniVoice จะเดาเอง บางทีเดาผิด → ภาษาไทยออกเสียงเพี้ยน
                lang = self._resolve_language(text)
                kwargs = {
                    "text": text,
                    "instruct": instruct_val,
                    "language": lang,
                    "normalize_text": self._normalize_text,
                    "generation_config": self._make_generation_config(),
                }
                # ★ speed เฉพาะกรณีไม่ใช่ default (1.0) — ปล่อยให้โมเดลเดาถ้า default
                if self._speed and abs(self._speed - 1.0) > 0.01:
                    kwargs["speed"] = self._speed

                logger.debug(f"OmniVoice generate: lang={lang}, instruct={instruct_val}, "
                             f"speed={self._speed}, normalize={self._normalize_text}")
                audio_list = self._model.generate(**kwargs)

            if not audio_list or len(audio_list) == 0:
                on_error("OmniVoice returned empty audio")
                return

            audio_np = audio_list[0]  # numpy array shape (T,) at 24kHz
            self._log_audio_stats(f"generate raw {text!r}", audio_np, OMNIVOICE_SR)

            # ★ resample 24kHz → 44100Hz (เข้ากับ pipeline + RVC)
            audio_np = self._resample(audio_np, OMNIVOICE_SR, TARGET_SR)

            # ★ post-process: ลบ DC offset + normalize (ปรับคุณภาพเสียง)
            #   OmniVoice สร้างเสียงสั้นๆ บางครั้งมี DC offset → เสียงแหบ/แน่น
            audio_np = self._postprocess_audio(audio_np)
            self._log_audio_stats(f"generate post {text!r}", audio_np, TARGET_SR)

            # ★ numpy → WAV bytes (เพื่อเข้ากับ _decode pipeline เดิม)
            wav_bytes = self._numpy_to_wav(audio_np, TARGET_SR)

            on_done(wav_bytes)

        except Exception as e:
            logger.error(f"OmniVoice generate failed: {e}")
            on_error(str(e))

    def generate_short_word_doubled(
        self,
        word: str,
        on_done: Callable[[bytes], None],
        on_error: Callable[[str], None],
        repeat_count: int = 2,
    ) -> None:
        """★ EXPERIMENTAL — คำเดี่ยวสั้นๆ (เช่น "ครับ", "โอเค") ที่ OmniVoice อ่านพังบ่อย

        แนวคิด: OmniVoice อ่านคำสั้นได้ปกติถ้าอยู่ใน "วลี" (มีคำอื่นร่วมด้วย) ปัญหาเกิด
        เฉพาะตอนเป็นคำโดดๆ คำเดียว → เราจึงสร้างวลีปลอมโดยพูดคำเดิมซ้ำ N ครั้ง
        ("ครับ ครับ ครับ") ให้โมเดล "warm up" จังหวะจากคำแรกๆ ก่อน แล้วตัดเอาแค่
        ท่อนสุดท้าย (คำที่ N) มาเป็นเสียงจริงที่เล่น — ไม่ต้องพึ่ง fallback ไป edge-tts

        repeat_count: จำนวนครั้งที่พูดซ้ำ (2-5, จาก settings.omnivoice_short_word_repeat) —
        ยิ่งเยอะยิ่งให้โมเดล warm up นานขึ้น แต่ก็ยิ่งช้าลง (synth ยาวขึ้นตามจำนวนครั้ง)

        ถ้าตัดไม่ได้ผลดี (เสียงที่ได้สั้นผิดปกติ) → on_error() ให้ caller fallback เอง
        (เหมือนกรณี OmniVoice fail ปกติ — ไม่มีความเสี่ยงเพิ่มจาก path เดิม)
        """
        if not self._loaded or self._model is None:
            on_error("OmniVoice not loaded")
            return
        word = (word or "").strip()
        if not word:
            on_error("empty text")
            return
        repeat_count = max(2, min(5, int(repeat_count or 2)))

        doubled_text = " ".join([word] * repeat_count)
        try:
            with self._lock:
                instruct_val = self.VALID_INSTRUCTS.get(self._instruct, "female")
                lang = self._resolve_language(doubled_text)
                kwargs = {
                    "text": doubled_text,
                    "instruct": instruct_val,
                    "language": lang,
                    "normalize_text": self._normalize_text,
                    "generation_config": self._make_generation_config(),
                }
                if self._speed and abs(self._speed - 1.0) > 0.01:
                    kwargs["speed"] = self._speed
                logger.info(f"OmniVoice short-word retry (x{repeat_count}): {doubled_text!r}")
                audio_list = self._model.generate(**kwargs)

            if not audio_list or len(audio_list) == 0:
                on_error("OmniVoice returned empty audio (doubled)")
                return

            audio_np = audio_list[0]  # (T,) ที่ 24kHz — ก่อน resample/postprocess
            self._log_audio_stats(f"retry raw (x{repeat_count}) {doubled_text!r}", audio_np, OMNIVOICE_SR)

            split_idx = self._find_repeat_split(audio_np, OMNIVOICE_SR, repeat_count)
            trimmed = audio_np[split_idx:]
            logger.info(
                f"OmniVoice short-word split: total={len(audio_np)/OMNIVOICE_SR*1000:.0f}ms, "
                f"split_at={split_idx/OMNIVOICE_SR*1000:.0f}ms, kept={len(trimmed)/OMNIVOICE_SR*1000:.0f}ms, "
                f"repeat_count={repeat_count}"
            )
            self._log_audio_stats(f"retry trimmed (pre-postprocess) {word!r}", trimmed, OMNIVOICE_SR)

            # ★ กันเคสตัดพัง — เหลือสั้นกว่า 120ms ถือว่าไม่ใช่คำจริง (ตัดผิดจุด/โมเดลพังทั้งคู่)
            min_samples = int(0.12 * OMNIVOICE_SR)
            if len(trimmed) < min_samples:
                on_error(
                    f"trim produced too-short audio ({len(trimmed)/OMNIVOICE_SR*1000:.0f}ms) — likely bad split"
                )
                return

            trimmed = self._resample(trimmed, OMNIVOICE_SR, TARGET_SR)
            trimmed = self._postprocess_audio(trimmed)
            self._log_audio_stats(f"retry final (post-postprocess) {word!r}", trimmed, TARGET_SR)
            wav_bytes = self._numpy_to_wav(trimmed, TARGET_SR)
            on_done(wav_bytes)

        except Exception as e:
            logger.error(f"OmniVoice short-word retry failed: {e}")
            on_error(str(e))

    def _log_audio_stats(self, label: str, audio_np, sr: int) -> None:
        """★ DEBUG (INFO level) — log peak/RMS/duration ของ audio array ณ จุดหนึ่งใน pipeline

        ใช้หาสาเหตุ "เสียงลม/ไม่มีเสียงพูด" โดยไม่ต้องฟังเสียงจริง — ถ้า peak ต่ำมาก
        (ใกล้ 0) ตั้งแต่ raw ก่อน postprocess แปลว่าโมเดลไม่ได้ generate เสียงพูดจริง
        เลย (ไม่ใช่ปัญหาการตัด/normalize) — ถ้า peak ปกติตอน raw แต่ RMS ต่ำมากหลัง
        postprocess ให้สงสัยว่า normalize ไปขยาย noise floor แทนเสียงจริง
        """
        try:
            import numpy as np
            if audio_np is None or len(audio_np) == 0:
                logger.info(f"[audio-stats] {label}: EMPTY array")
                return
            a = audio_np.astype(np.float64)
            peak = float(np.max(np.abs(a)))
            rms = float(np.sqrt(np.mean(a ** 2)))
            dur_ms = len(a) / sr * 1000
            logger.info(
                f"[audio-stats] {label}: dur={dur_ms:.0f}ms peak={peak:.4f} rms={rms:.4f} "
                f"samples={len(a)}"
            )
        except Exception as e:
            logger.debug(f"_log_audio_stats failed: {e}")

    def _find_repeat_split(self, audio_np, sr: int, repeat_count: int = 2) -> int:
        """หาจุดตัดก่อนคำ "สุดท้าย" ของเสียงที่พูดซ้ำ N ครั้ง ("word word ... word")

        กลยุทธ์: มอง short-time RMS energy (หน้าต่าง 20ms, overlap 50%) เฉพาะรอบๆ
        จุดที่คาดว่าเป็นรอยต่อระหว่างคำที่ (N-1) กับคำที่ N คือประมาณ (N-1)/N ของ
        ความยาวคลิปทั้งหมด (แต่ละคำควรยาวใกล้เคียงกัน) หาโพสิชันที่เงียบที่สุดในช่วงนั้น
        — ถ้าเงียบกว่า RMS เฉลี่ยทั้งคลิปมากพอ (< 25%) ถือว่าเจอช่องว่างจริงระหว่างคำ
        ตัดตรงนั้น ★ ถ้าโมเดลพูดต่อกันไม่มีช่วงเงียบชัดเจน (เจอบ่อยกับโมเดลเร็ว) →
        fallback ไปจุด (N-1)/N ของความยาวทั้งหมดเป๊ะๆ (คร่าวกว่า แต่ยังดีกว่าไม่ตัดเลย)
        """
        import numpy as np
        n = len(audio_np)
        repeat_count = max(2, int(repeat_count or 2))
        win = max(1, int(0.02 * sr))  # 20ms

        # ★ จุดแบ่งที่คาดไว้ = (N-1)/N ของความยาวทั้งหมด — ค้นหารอบๆ จุดนี้ในช่วง
        #   กว้าง 1 ท่อน (1/N ของความยาวทั้งหมด) โดยเอาครึ่งท่อนก่อน+หลังจุดที่คาด
        center = n * (repeat_count - 1) / repeat_count
        half_span = n / repeat_count / 2
        lo = int(max(0, center - half_span))
        hi = int(min(n, center + half_span))
        fallback_split = int(center)
        if hi <= lo + win:
            return fallback_split  # คลิปสั้นเกินจะหาแบบละเอียด

        audio_f = audio_np.astype(np.float64)
        overall_rms = float(np.sqrt(np.mean(audio_f ** 2)) + 1e-9)

        best_idx = lo
        best_rms = None
        step = max(1, win // 2)
        i = lo
        while i < hi:
            seg = audio_f[i:i + win]
            if len(seg) == 0:
                break
            rms = float(np.sqrt(np.mean(seg ** 2)) + 1e-9)
            if best_rms is None or rms < best_rms:
                best_rms = rms
                best_idx = i
            i += step

        if best_rms is not None and best_rms < overall_rms * 0.25:
            return best_idx + win // 2  # กึ่งกลางของช่วงเงียบที่เจอ
        return fallback_split  # ไม่เจอช่วงเงียบชัดเจน → ใช้จุด (N-1)/N ตรงๆ

    def _postprocess_audio(self, audio_np):
        """post-process audio หลัง OmniVoice generate — แก้ปัญหา DC offset

        ★ 3 ขั้นตอน:
          1. DC offset removal (ลบค่าเฉลี่ย ≠ 0 → กันเสียงแหบ/ลำโพงดันข้างเดียว)
          2. Normalize peak → -3dB (0.707) — กัน clipping + รักษา dynamics
          3. Fade in/out 5ms (กัน click/pop ตอนเริ่ม-จบ)

        ★ หมายเหตุ: เคยลอง high-pass filter 200Hz แต่ตัดเสียงพูดจริงไปด้วย → ลบออก
        """
        import numpy as np
        if audio_np is None or len(audio_np) == 0:
            return audio_np
        try:
            audio = audio_np.astype(np.float32)
            # ── 1. DC offset removal ──
            dc = float(np.mean(audio))
            if abs(dc) > 0.001:
                audio = audio - dc
            # ── 2. Normalize to -3dB (peak = 0.707) ──
            peak = float(np.max(np.abs(audio)))
            if peak > 0.01:
                target_peak = 0.707  # -3dB
                audio = audio * (target_peak / peak)
            # ── 3. Fade in/out 5ms (กัน click) ──
            fade_samples = min(int(0.005 * TARGET_SR), len(audio) // 4)
            if fade_samples > 0:
                fade = np.linspace(0, 1, fade_samples, dtype=np.float32)
                audio[:fade_samples] *= fade
                audio[-fade_samples:] *= fade[::-1]
            audio = np.clip(audio, -1.0, 1.0)
            return audio
        except Exception as e:
            logger.debug(f"postprocess audio failed: {e}")
            return audio_np

    def _resample(self, audio_np, from_sr: int, to_sr: int):
        """resample ด้วย scipy (ถ้ามี) หรือ linear interpolation"""
        if from_sr == to_sr:
            return audio_np
        try:
            from scipy.signal import resample_poly
            import numpy as np
            # ★ resample_poly เร็ว + คุณภาพดี
            from math import gcd
            g = gcd(from_sr, to_sr)
            up = to_sr // g
            down = from_sr // g
            return resample_poly(audio_np.astype(np.float32), up, down)
        except ImportError:
            # ★ fallback: linear interpolation
            import numpy as np
            n_out = int(len(audio_np) * to_sr / from_sr)
            indices = np.linspace(0, len(audio_np) - 1, n_out)
            return np.interp(indices, np.arange(len(audio_np)), audio_np).astype(np.float32)

    def _numpy_to_wav(self, audio_np, sample_rate: int) -> bytes:
        """แปลง numpy float32 → WAV bytes (16-bit PCM)"""
        import numpy as np
        # ★ clip + normalize → int16
        audio_np = np.clip(audio_np, -1.0, 1.0)
        audio_int16 = (audio_np * 32767).astype(np.int16)
        # ★ ใช้ soundfile (มีอยู่แล้วใน deps) → WAV bytes
        buf = io.BytesIO()
        try:
            import soundfile as sf
            sf.write(buf, audio_int16, sample_rate, format='WAV', subtype='PCM_16')
        except Exception:
            # ★ fallback: ใช้ wave module (stdlib)
            import wave
            w = wave.open(buf, 'wb')
            w.setnchannels(1)
            w.setsampwidth(2)  # 16-bit
            w.setframerate(sample_rate)
            w.writeframes(audio_int16.tobytes())
            w.close()
        return buf.getvalue()

    def shutdown(self):
        """คืน VRAM"""
        try:
            if self._model is not None:
                del self._model
                self._model = None
            self._loaded = False
            # ★ empty CUDA cache
            if hasattr(self, '_torch') and self._torch.cuda.is_available():
                self._torch.cuda.empty_cache()
            logger.info("OmniVoice shutdown — VRAM freed")
        except Exception as e:
            logger.debug(f"OmniVoice shutdown error: {e}")


def is_omnivoice_available() -> bool:
    """เช็คว่า OmniVoice + torch พร้อมใช้ไหม

    ★ PyInstaller exe: transformers LazyModule พัง → ใช้การตรวจแบบง่าย
      - ถ้าเป็น frozen exe (Full build) → เช็คแค่ torch (omnivoice bundle มาแน่)
      - ถ้าเป็น dev/Lite → import จริง
    """
    import sys
    # 1. torch ต้องมี
    try:
        import torch  # noqa: F401
    except Exception:
        return False
    # 2. ★ PyInstaller frozen exe → trust ว่ามี omnivoice (bundle มาแล้วใน spec)
    #    transformers LazyModule พังใน PyInstaller แต่ตัวโมเดลทำงานได้ปกติตอน runtime
    if getattr(sys, 'frozen', False):
        return True
    # 3. dev/Lite → import จริง
    try:
        import omnivoice  # noqa: F401
        return True
    except Exception:
        return False
