"""rvc_engine.py — Wrapper สำหรับ RVC voice conversion

ใช้ rvc-python library เพื่อโหลด .pth model + inference
auto-detect NVIDIA GPU; fallback CPU (ช้ากว่ามาก)

การใช้งาน:
    engine = RVCEngine(model_path="rvc_models/haruka.pth")
    engine.load()
    output_audio = engine.convert(input_audio, sample_rate)
"""
from __future__ import annotations

import os
import sys
import threading

# ★ monkey-patch torch.load ให้ใช้ weights_only=False เป็น default
#    PyTorch 2.6+ เปลี่ยน default เป็น weights_only=True → fairseq (HuBERT) โหลดไม่ได้
#    เพราะ checkpoint มี custom Python objects (fairseq Dictionary)
#    ปลอดภัยเพราะโหลดเฉพาะไฟล์ของเราเอง (hubert_base.pt + .pth models)
try:
    import torch
    _orig_torch_load = torch.load
    def _patched_torch_load(*args, **kwargs):
        if 'weights_only' not in kwargs:
            kwargs['weights_only'] = False
        return _orig_torch_load(*args, **kwargs)
    torch.load = _patched_torch_load
except Exception:
    pass
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np


# ── HuBERT cache (แชร์ระหว่าง instance — กันโหลดซ้ำทุกครั้งที่เปลี่ยนโมเดล) ──
# HuBERT เป็น feature extractor ที่ใช้ร่วมกันได้ทุกโมเดล → โหลดครั้งเดียวพอ
_HUBERT_CACHE: dict = {}  # {device: hubert_model}
_HUBERT_LOCK = threading.Lock()
# track ว่าเคย warm-up ครั้งแรกแล้วหรือยัง (ข้าม warm-up ถ้าเปลี่ยนโมเดล)
_WARMUP_DONE = False


def check_gpu() -> Optional[str]:
    """เช็ค NVIDIA GPU + VRAM — คืนชื่อ GPU ถ้าพบ"""
    try:
        import torch
        if torch.cuda.is_available():
            return torch.cuda.get_device_name(0)
    except Exception:
        pass
    return None


@dataclass
class RVCParams:
    """พารามิเตอร์สำหรับ RVC inference"""

    f0up_key: int = 0           # pitch shift semitones (-12 to +12)
    f0method: str = "rmvpe"     # pitch extraction: "rmvpe" (best), "crepe", "harvest", "pm"
    index_rate: float = 0.75    # 0-1 feature index retrieval (สูกว่า = คล้ายต้นฉบับ)
    index_path: str = ""        # path ของ .index file (optional)
    filter_radius: int = 3      # median filter radius (0=no filter)
    resample_sr: int = 0        # output sample rate (0=keep input)
    rms_mix_rate: float = 0.25  # 0-1 mix RMS envelope
    protect: float = 0.33       # 0-1 protect unvoiced consonants (สำคัญสำหรับไทย!)


class RVCEngine:
    """RVC voice conversion engine"""

    def __init__(self, model_path: str = "", device: Optional[str] = None) -> None:
        self.model_path = model_path
        self.device = device or ("cuda:0" if check_gpu() else "cpu")
        self._inference = None
        self._is_loaded = False
        self._lock = threading.Lock()

    @property
    def is_loaded(self) -> bool:
        return self._is_loaded

    def load(self) -> None:
        """โหลด model เข้า memory — ใช้เวลา 5-15 วินาที"""
        if not self.model_path or not os.path.exists(self.model_path):
            raise FileNotFoundError(f"RVC model not found: {self.model_path}")

        if self._is_loaded:
            return

        # ตรวจ version ก่อน — rvc-python รองรับเฉพาะ v2
        # v1 model จะทำให้เกิด size mismatch error ที่สับสน
        try:
            import torch
            cpt = torch.load(self.model_path, map_location="cpu", weights_only=False)
            emb_shape = cpt.get("weight", {}).get("enc_p.emb_phone.weight")
            if emb_shape is not None and len(emb_shape) >= 2 and emb_shape[1] != 768:
                raise RuntimeError(
                    f"Model นี้เป็น RVC v1 (ไม่รองรับ) — กรุณาใช้ model v2 เท่านั้น\n"
                    f"emb_phone shape: {list(emb_shape)} (v2 ต้องเป็น 768)"
                )
        except RuntimeError as e:
            if "v1" in str(e):
                raise  # re-raise ข้อความที่อ่านง่าย
            # อาจเป็น error อื่น ให้ผ่านไป
        except Exception:
            pass  # ถ้าเช็ค fail ให้ลองโหลดจริง

        # import lazy เพื่อให้ GUI เปิดเร็ว
        from rvc_python.infer import RVCInference

        # ติดตั้ง source patch สำหรับ TorchScript (PyInstaller ไม่ bundle .py source)
        # ต้องทำหลัง torch import สำเร็จ (rvc_python import torch ไปแล้ว)
        try:
            import main as _main
            if hasattr(_main, '_apply_rvc_source_patch'):
                _main._apply_rvc_source_patch()
        except Exception:
            pass

        # แก้ lib_dir สำหรับ PyInstaller exe — ต้องทำก่อน RVCInference()
        # เพราะ __init__ ใช้ lib_dir ตอน download_rvc_models + VC()
        import sys as _sys
        if getattr(_sys, "frozen", False):
            try:
                import rvc_python as _rvc_pkg
                _rvc_dir = os.path.dirname(_rvc_pkg.__file__)
                # patch __file__ ของ infer module ให้ lib_dir ถูก
                import rvc_python.infer as _rvc_infer
                _rvc_infer.__file__ = os.path.join(_rvc_dir, "infer.py")
            except Exception:
                pass

        with self._lock:
            self._inference = RVCInference(
                model_path=self.model_path,
                device=self.device,
            )
            self._inference.set_params(
                f0method="rmvpe",  # default — best for Thai tones
                f0up_key=0,
            )
            self._is_loaded = True

            # แก้ lib_dir สำหรับ PyInstaller exe — vc.lib_dir อ้างถึง site-packages
            # ที่ไม่มีใน exe → แก้ให้อ้างถึง rvc_python path ใน exe
            import sys as _sys
            if getattr(_sys, "frozen", False):
                try:
                    import rvc_python as _rvc_pkg
                    _rvc_dir = os.path.dirname(_rvc_pkg.__file__)
                    self._inference.vc.lib_dir = _rvc_dir
                    # config.lib_dir ด้วย (ใช้โดย load_hubert)
                    if hasattr(self._inference.vc.config, 'lib_dir'):
                        self._inference.vc.config.lib_dir = _rvc_dir
                except Exception:
                    pass

            # preload HuBERT — ใช้ cache ร่วม (โหลดครั้งเดียว ไม่ซ้ำทุกโมเดล)
            try:
                from rvc_python.modules.vc.utils import load_hubert
                global _HUBERT_CACHE

                with _HUBERT_LOCK:
                    cached_hubert = _HUBERT_CACHE.get(self.device)
                if cached_hubert is not None:
                    # reuse HuBERT จาก cache (เร็วมาก — ไม่ต้องโหลดใหม่)
                    self._inference.vc.hubert_model = cached_hubert
                else:
                    hubert_model = load_hubert(
                        self._inference.vc.config, self._inference.vc.lib_dir
                    )
                    if hubert_model is not None:
                        self._inference.vc.hubert_model = hubert_model
                        with _HUBERT_LOCK:
                            _HUBERT_CACHE[self.device] = hubert_model
                    else:
                        # load_hubert returned None — try alternate path
                        import rvc_python as _rvc_pkg2
                        _alt_dir = os.path.dirname(_rvc_pkg2.__file__)
                        hubert_model = load_hubert(
                            self._inference.vc.config, _alt_dir
                        )
                        if hubert_model is not None:
                            self._inference.vc.hubert_model = hubert_model
                            with _HUBERT_LOCK:
                                _HUBERT_CACHE[self.device] = hubert_model
            except Exception as _hubert_err:
                # log error but don't crash — pipeline will lazy-load
                pass

            # warm-up pipeline ด้วย silence 0.5s — เฉพาะครั้งแรกเท่านั้น
            # (warm-up โหลด f0 model rmvpe/crepe ซึ่งใช้ร่วมกันได้ทุกโมเดล)
            global _WARMUP_DONE
            if not _WARMUP_DONE:
                try:
                    silence_16k = np.zeros(8000, dtype=np.float32)  # 0.5s @ 16kHz
                    self._convert_array_locked(silence_16k, RVCParams())
                    _WARMUP_DONE = True
                except Exception:
                    # warm-up fail ไม่ fatal — ข้อความแรกจะช้าหน่อยแต่ยังใช้ได้
                    pass

    def unload(self) -> None:
        """unload model เพื่อคืน VRAM"""
        with self._lock:
            self._inference = None
            self._is_loaded = False
            # garbage collect VRAM
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass

    def convert(
        self,
        audio: np.ndarray,
        sample_rate: int,
        params: Optional[RVCParams] = None,
    ) -> tuple[np.ndarray, int]:
        """แปลงเสียงด้วย RVC

        Args:
            audio: float32 mono array
            sample_rate: input sample rate
            params: RVC parameters (ใช้ default ถ้า None)

        Returns:
            (converted_audio_float32, output_sample_rate)
        """
        if not self._is_loaded or self._inference is None:
            raise RuntimeError("Model not loaded — call load() first")

        params = params or RVCParams()

        # ตั้งค่า params
        self._inference.set_params(
            f0method=params.f0method,
            f0up_key=params.f0up_key,
            index_rate=params.index_rate if params.index_path else 0,
            index_path=params.index_path or "",
            filter_radius=params.filter_radius,
            resample_sr=params.resample_sr,
            rms_mix_rate=params.rms_mix_rate,
            protect=params.protect,
        )

        # เขียน input ลง temp file (rvc-python อ่านจาก file)
        import tempfile
        import soundfile as sf

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_in:
            in_path = tmp_in.name
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_out:
            out_path = tmp_out.name

        try:
            # write input
            audio_int = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
            sf.write(in_path, audio_int, sample_rate, subtype="PCM_16")

            # inference (this is the slow GPU part)
            with self._lock:
                self._inference.infer_file(in_path, out_path)

            # read output
            out_audio, out_sr = sf.read(out_path, dtype="float32", always_2d=False)
            if out_audio.ndim == 2:
                out_audio = out_audio.mean(axis=1)
            return out_audio, out_sr

        finally:
            for p in (in_path, out_path):
                try:
                    os.unlink(p)
                except OSError:
                    pass

    # ------------------------------------------------------------------ #
    # Fast path — bypass file I/O entirely (for streaming)
    # ------------------------------------------------------------------ #
    def convert_array(
        self,
        audio: np.ndarray,
        sample_rate: int,
        params: Optional[RVCParams] = None,
    ) -> tuple[np.ndarray, int]:
        """แปลงเสียงตรงจาก numpy — ไม่มี file I/O (เร็วกว่า convert() ~30-50%)

        ต่างจาก convert():
          - ไม่เขียน/อ่าน tempfile (ตัด soundfile + load_audio + PyAV)
          - เรียก vc.pipeline.pipeline() ตรง ส่ง numpy เข้าไป
          - normalize peak ก่อน return (กัน clip)
          - resample output กลับ 44100 เสมอ (กัน pygame mixer pitch drift)

        Args:
            audio: float32 mono array (sample_rate ใดก็ได้ แต่แนะนำ 44100)
            sample_rate: sample rate ของ audio input
            params: RVC parameters (ใช้ default ถ้า None)

        Returns:
            (converted_audio_float32, 44100)  — mono, peak-normalized
        """
        if not self._is_loaded or self._inference is None:
            raise RuntimeError("Model not loaded — call load() first")

        params = params or RVCParams()

        # resample input → 16kHz (RVC ทำงานที่ 16kHz เสมอ)
        if sample_rate != 16000:
            audio_16k = self._resample_linear(audio, sample_rate, 16000)
        else:
            audio_16k = audio.astype(np.float32, copy=False)

        # vc_single ทำ peak normalize ด้วย (np.abs(audio).max() / 0.95) เราทำบ้าง
        audio_max = np.abs(audio_16k).max() / 0.95 if len(audio_16k) else 0.0
        if audio_max > 1:
            audio_16k = audio_16k / audio_max

        with self._lock:
            out_int16 = self._convert_array_locked(audio_16k, params)

        # out เป็น int16 → float32
        out_f32 = out_int16.astype(np.float32) / 32768.0

        # resample output กลับ 44100 (pygame mixer ตั้ง 44100 ตายตัว)
        out_sr = self._inference.vc.tgt_sr
        if out_sr != 44100:
            out_f32 = self._resample_linear(out_f32, out_sr, 44100)

        # normalize peak กัน clip ตอน play
        peak = np.abs(out_f32).max()
        if peak > 1.0 and peak > 0:
            out_f32 = out_f32 / peak

        return out_f32, 44100

    def _convert_array_locked(
        self, audio_16k: np.ndarray, params: RVCParams
    ) -> np.ndarray:
        """เรียก vc.pipeline.pipeline() ตรง — ต้องถือ self._lock อยู่แล้ว

        Returns: int16 numpy mono ที่ tgt_sr
        """
        vc = self._inference.vc

        # หา index path — ใช้ model index ถ้ามี (RVCInference เก็บใน self.models)
        file_index = ""
        if params.index_path:
            file_index = params.index_path
        elif self._inference.current_model:
            model_info = self._inference.models.get(self._inference.current_model, {})
            file_index = model_info.get("index", "")

        index_rate = params.index_rate if file_index else 0

        # input_audio_path ใช้เป็น cache key ของ harvest f0 — ใช้ dummy ไม่ซ้ำเพื่อกัน stale cache
        cache_key = f"stream_{id(audio_16k)}_{len(audio_16k)}"

        # pipeline() รับ numpy ตรง ไม่อ่านไฟล์ — input_audio_path เป็น cache key เท่านั้น
        out = vc.pipeline.pipeline(
            vc.hubert_model,
            vc.net_g,
            0,                      # sid (speaker id)
            audio_16k,
            cache_key,
            [0, 0, 0],              # times
            params.f0up_key,
            params.f0method,
            file_index,
            index_rate,
            vc.if_f0,
            params.filter_radius,
            vc.tgt_sr,
            params.resample_sr,
            params.rms_mix_rate,
            vc.version,
            params.protect,
            None,                   # f0_file
        )
        # pipeline() อาจคืน (audio_np, sr) หรือ None (ถ้า HuBERT ไม่ได้โหลด)
        if out is None:
            raise RuntimeError("RVC pipeline returned None — HuBERT model may not be loaded")
        # ถ้าเป็น tuple → unpack
        if isinstance(out, tuple):
            out = out[0]  # เอาแค่ audio_np
        if not isinstance(out, np.ndarray):
            raise RuntimeError(f"RVC pipeline returned unexpected type: {type(out)}")
        return out

    @staticmethod
    def _resample_linear(
        audio: np.ndarray, orig_sr: int, target_sr: int
    ) -> np.ndarray:
        """resample แบบ linear interpolation — เร็วกว่า librosa/PyAV มาก

        คุณภาพพอใช้สำหรับ streaming voice (ไม่ใช่ music)
        """
        if orig_sr == target_sr or len(audio) == 0:
            return audio.astype(np.float32, copy=False)
        ratio = target_sr / orig_sr
        n_out = int(len(audio) * ratio)
        if n_out < 1:
            return np.zeros(1, dtype=np.float32)
        # index แบบ fractional → linear interp
        idx = np.arange(n_out, dtype=np.float32) / ratio
        i0 = idx.astype(np.int32)
        i1 = np.minimum(i0 + 1, len(audio) - 1)
        frac = idx - i0
        return (audio[i0] * (1.0 - frac) + audio[i1] * frac).astype(np.float32)



# ---------------------------------------------------------------------- #
# Bundled model registry
# ---------------------------------------------------------------------- #
def _get_app_base_dir() -> str:
    """หา base directory — รองรับทั้ง dev และ PyInstaller bundle

    - dev mode: โฟลเดอร์ของ script
    - PyInstaller onefile: sys._MEIPASS (temp extract dir)
    - PyInstaller onedir: โฟลเดอร์ของ exe
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        # onefile mode
        return sys._MEIPASS
    if getattr(sys, "frozen", False):
        # onedir mode — exe path's directory
        return os.path.dirname(sys.executable)
    # dev mode
    return os.path.dirname(os.path.abspath(__file__))


def get_bundled_models() -> list[dict]:
    """รายการ model ที่มากับโปรแกรม"""
    # หาจาก 3 ที่: PyInstaller bundle, ข้างๆ exe, ข้างๆ script
    candidates = [
        os.path.join(_get_app_base_dir(), "rvc_models"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "rvc_models"),
    ]
    base = None
    for c in candidates:
        if os.path.isdir(c):
            base = c
            break
    if base is None:
        return []  # ไม่มี models

    # นิยาม model ทั้งหมด (id, name, emoji, description, pth, gender, category)
    definitions = [
        # === AIHeaven — anime/TTS voices (มี index) ===
        ("haruka",   "Haruka (อนิเมะ)",   "🌸", "เสียงผู้หญิงอนิเมะน่ารัก",       "haruka.pth",   "haruka.index",   "หญิง", "อนิเมะ"),
        ("hikari",   "Hikari (นุ่มนวล)",  "🌙", "เสียงนุ่มนวล อ่านข่าว/สารคดี",    "hikari.pth",   "hikari.index",   "หญิง", "อนิเมะ"),
        # === Hololive EN VTubers ===
        ("gura",     "Gawr Gura",         "🦈", "เด็กผู้หญิงน่ารัก Hololive",      "gura.pth",     "",               "หญิง", "VTuber"),
        ("calliope", "Mori Calliope",     "💀", "หญิงเสียงทุ้ม Hololive",          "calliope.pth", "",               "หญิง", "VTuber"),
        ("kronii",   "Ouro Kronii",       "⏰", "หญิงเสียงนุ่มนวล Hololive",       "kronii.pth",   "",               "หญิง", "VTuber"),
        ("baelz",    "Hakos Baelz",       "🐀", "ผู้หญิงพลังบวก Hololive",        "baelz.pth",    "",               "หญิง", "VTuber"),
        ("ina",      "Ninomae Ina'nis",   "🔮", "หญิงเสียงนุ่ม Hololive",          "ina.pth",      "",               "หญิง", "VTuber"),
        ("amelia",   "Amelia Watson",     "🕰️", "หญิงสดใส Hololive EN",          "amelia.pth",   "",               "หญิง", "VTuber"),
        # === Hololive JP VTubers ===
        ("pekora",   "Usada Pekora",      "🐰", "หญิงเสียงสูงน่ารัก Hololive JP",  "pekora.pth",   "",               "หญิง", "VTuber"),
        ("marine",   "Houshou Marine",    "🏴‍☠️", "หญิงเสียงเป็นผู้ใหญ่ Hololive", "marine.pth",   "",               "หญิง", "VTuber"),
        ("kiara",    "Takanashi Kiara",   "🐔", "หญิงเสียงสูง Hololive EN",       "kiara.pth",    "",               "หญิง", "VTuber"),
        ("okayu",    "Nekomata Okayu",    "🐱", "หญิงเสียงทุ้ม Hololive",          "okayu.pth",    "",               "หญิง", "VTuber"),
        ("kanata",   "Amane Kanata",      "👼", "หญิงเสียงนุ่มนวล Hololive",       "kanata.pth",   "",               "หญิง", "VTuber"),
        ("ollie",    "Kureiji Ollie",     "🧟", "หญิงเสียงแหลม Hololive ID",      "ollie.pth",    "",               "หญิง", "VTuber"),
        ("a-chan",   "A-Chan",            "📋", "หญิงผู้ประกาศ Hololive",          "a-chan.pth",   "",               "หญิง", "ผู้ประกาศ"),
        # === VShojo / others ===
        ("ironmouse","Ironmouse",         "🎹", "หญิงเสียงสูง VShojo",             "ironmouse.pth","",               "หญิง", "VTuber"),
        ("henya",    "Henya",             "🌟", "เด็กผู้หญิงเสียงสูง VShojo",      "henya.pth",    "",               "หญิง", "VTuber"),
        ("nina",     "Nina Kosaka",       "🦊", "หญิงเสียงแม่ Nijisanji",         "nina.pth",     "",               "หญิง", "VTuber"),
        # === Holostars — ชาย ===
        ("vesper",   "Noir Vesper",       "🦇", "ชายเสียงทุ้ม Holostars",          "vesper.pth",   "",               "ชาย", "VTuber"),
        ("mysta",    "Mysta Rias",        "🕵️", "ชายหนุ่ม Nijisanji",             "mysta.pth",    "",               "ชาย", "VTuber"),
        ("hakka",    "Banzoin Hakka",     "🎯", "ชายหนุ่ม Holostars",             "hakka.pth",    "",               "ชาย", "VTuber"),
        ("rikka",    "Rikka",             "🎸", "ชายเสียงทุ้ม Holostars",          "rikka.pth",    "",               "ชาย", "VTuber"),
        ("miyabi",   "Hanasaki Miyabi",   "🌸", "ชายเสียงนุ่ม Holostars",         "miyabi.pth",   "",               "ชาย", "VTuber"),
        # === Robotic / AI ===
        ("neuro",    "Neuro-sama",        "🤖", "AI หุ่นยนต์ผู้หญิง",              "neuro.pth",    "",               "หญิง", "AI"),
        ("falseyed", "FalseEyeD",         "👁️", "ชายหุ่นยนต์ monotone",         "falseyed.pth", "",               "ชาย", "AI"),
        # === Genshin Impact ===
        ("keqing",   "Keqing",            "⚔️", "หญิงทรนง Genshin",              "keqing.pth",   "",               "หญิง", "Genshin"),
        ("raiden",   "Yae Miko",          "🦊", "หญิงเสียงเป็นผู้ใหญ่ Genshin",    "raiden.pth",   "",               "หญิง", "Genshin"),
        ("shenhe",   "Shenhe",            "❄️", "หญิงเสียงนุ่ม Genshin",          "shenhe.pth",   "",               "หญิง", "Genshin"),
        ("yoimiya",  "Yoimiya",           "🎆", "หญิงสดใส Genshin",              "yoimiya.pth",  "",               "หญิง", "Genshin"),
        ("diona",    "Diona",             "🍸", "เด็กผู้หญิง Genshin",            "diona.pth",    "",               "หญิง", "Genshin"),
    ]

    models = []
    for model_id, name, emoji, desc, pth_name, index_name, gender, category in definitions:
        pth_path = os.path.join(base, pth_name)
        if not os.path.exists(pth_path):
            continue  # ข้ามถ้าไฟล์ไม่มี
        index_path = os.path.join(base, index_name) if index_name else ""
        if index_path and not os.path.exists(index_path):
            index_path = ""
        models.append({
            "id": model_id,
            "name": name,
            "emoji": emoji,
            "description": desc,
            "pth_path": pth_path,
            "index_path": index_path,
            "author": "VTuber-RVC / AIHeaven",
            "fictional": True,
            "gender": gender,
            "category": category,
        })
    return models


def get_model_info(model_id: str) -> Optional[dict]:
    """หา model info ตาม id"""
    for m in get_bundled_models():
        if m["id"] == model_id:
            return m
    return None


# ---------------------------------------------------------------------- #
# CLI test — ทดสอบ Thai tone preservation
# ---------------------------------------------------------------------- #
if __name__ == "__main__":
    import sys
    import time

    if len(sys.argv) < 3:
        print("Usage: python rvc_engine.py <input.wav> <model_id|path.pth>")
        print("Bundled: haruka, hikari")
        sys.exit(1)

    input_path = sys.argv[1]
    model_arg = sys.argv[2]

    print("=== GPU check ===")
    gpu = check_gpu()
    print(f"GPU: {gpu or 'NOT FOUND — using CPU (slow!)'}")
    print()

    # resolve model
    if model_arg in ("haruka", "hikari"):
        info = get_model_info(model_arg)
        if info is None:
            print(f"Unknown model: {model_arg}")
            sys.exit(1)
        if not os.path.exists(info["pth_path"]):
            print(f"Model file missing: {info['pth_path']}")
            sys.exit(1)
        model_path = info["pth_path"]
        index_path = info["index_path"]
        print(f"Using bundled: {info['emoji']} {info['name']}")
    else:
        model_path = model_arg
        index_path = ""

    print(f"Loading model: {model_path}")
    t0 = time.time()
    engine = RVCEngine(model_path=model_path)
    engine.load()
    print(f"  Loaded in {time.time() - t0:.1f}s")
    print()

    # load input
    import soundfile as sf
    audio, sr = sf.read(input_path, dtype="float32")
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    print(f"Input: {len(audio)} samples @ {sr}Hz = {len(audio)/sr:.2f}s")

    # convert
    params = RVCParams(
        f0method="rmvpe",     # best for Thai
        index_rate=0.75,
        protect=0.33,         # preserve unvoiced consonants
        index_path=index_path,
    )
    print(f"Converting with f0method={params.f0method} protect={params.protect}...")
    t0 = time.time()
    out, out_sr = engine.convert(audio, sr, params)
    elapsed = time.time() - t0
    print(f"  Done in {elapsed:.2f}s ({elapsed / (len(audio)/sr):.2f}x real-time)")
    print(f"  Output: {len(out)} samples @ {out_sr}Hz = {len(out)/out_sr:.2f}s")

    # save
    out_path = f"rvc_output_{model_arg}.wav"
    out_int = (np.clip(out, -1, 1) * 32767).astype(np.int16)
    sf.write(out_path, out_int, out_sr, subtype="PCM_16")
    print(f"Saved: {out_path}")
