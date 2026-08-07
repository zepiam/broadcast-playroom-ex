"""audio_effects.py — ระบบ effects chain แบบละเอียดสำหรับประเสียง

อัปเกรดจาก v1 — เพิ่มพารามิเตอร์ทุกตัวของ effect + Formant + Harmonizer + Noise Gate + 5-band EQ

ใช้ pedalboard (Spotify, JUCE C++) เป็นหัวใจ + formant.py + harmonizer.py ที่ implement เอง
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from pedalboard import (
    Bitcrush,
    Chorus,
    Compressor,
    Delay,
    Distortion,
    Gain,
    HighShelfFilter,
    HighpassFilter,
    LowShelfFilter,
    LowpassFilter,
    NoiseGate,
    Pedalboard,
    PeakFilter,
    PitchShift,
    Reverb,
)

# ค่าเริ่มต้น sample rate ของ edge-tts output (24kHz mono MP3)
DEFAULT_SR = 24000
# sample rate สำหรับ output (upsample ให้เป็น 44.1kHz เพื่อคุณภาพ effects ที่ดีขึ้น)
OUTPUT_SR = 44100


# ---------------------------------------------------------------------- #
# Effect parameter dataclasses (เพิ่มพารามิเตอร์ทุกตัว)
# ---------------------------------------------------------------------- #
@dataclass
class PitchShiftParams:
    enabled: bool = False
    semitones: float = 0.0  # -12 ถึง +12


@dataclass
class FormantParams:
    """Formant shift — เปลี่ยนลักษณะเสียงโดย pitch เดิม"""

    enabled: bool = False
    ratio: float = 1.0  # 0.5 - 2.0 (1.0 = เดิม, >1 = หญิง/เด็ก, <1 = ชาย/ผู้สูงอายุ)


@dataclass
class SpeedParams:
    enabled: bool = False
    factor: float = 1.0  # 0.5 - 2.0


@dataclass
class HarmonizerParams:
    """Harmonizer / Octaver — เพิ่มเสียงคู่แปด"""

    enabled: bool = False
    # voice 1 (เช่น octave up)
    voice1_semitones: float = 12.0   # -24 ถึง +24
    voice1_gain: float = 0.5         # 0.0 - 1.0
    # voice 2 (เช่น octave down)
    voice2_semitones: float = -12.0  # -24 ถึง +24
    voice2_gain: float = 0.5         # 0.0 - 1.0
    # dry mix
    dry_mix: float = 1.0             # 0.0 - 2.0


@dataclass
class ReverbParams:
    enabled: bool = False
    room_size: float = 0.5     # 0.0 - 1.0
    damping: float = 0.5       # 0.0 - 1.0
    wet_level: float = 0.33    # 0.0 - 1.0
    dry_level: float = 0.4     # 0.0 - 1.0
    width: float = 1.0         # 0.0 - 1.0 (stereo width — mono input = ไม่มีผล)
    freeze_mode: float = 0.0   # 0.0 - 1.0 (1.0 = reverb เดินตลอด)


@dataclass
class DelayParams:
    enabled: bool = False
    delay_seconds: float = 0.25  # 0.01 - 2.0
    feedback: float = 0.3        # 0.0 - 0.95
    mix: float = 0.3             # 0.0 - 1.0
    ping_pong: bool = False      # สลับซ้ายขวา (mono = ไม่มีผล)


@dataclass
class ChorusParams:
    enabled: bool = False
    rate_hz: float = 1.5       # 0.1 - 10
    depth: float = 0.25        # 0.0 - 1.0
    mix: float = 0.5           # 0.0 - 1.0
    feedback: float = 0.0      # 0.0 - 0.95
    centre_delay_ms: float = 7.0  # 0 - 50


@dataclass
class DistortionParams:
    enabled: bool = False
    drive_db: float = 10.0  # 0 - 30


@dataclass
class BitcrushParams:
    enabled: bool = False
    bit_depth: float = 8.0           # 1 - 16
    downsample_factor: float = 1.0   # 1 - 16 (1 = ปกติ, >1 = ลด sample rate)


@dataclass
class LowpassParams:
    enabled: bool = False
    cutoff_hz: float = 2000.0  # 200 - 20000


@dataclass
class HighpassParams:
    enabled: bool = False
    cutoff_hz: float = 200.0  # 20 - 5000


@dataclass
class TelephoneParams:
    """Bandpass แบบคลาสสิกของโทรศัพท์: 300Hz - 3400Hz"""

    enabled: bool = False


@dataclass
class EQBand:
    """แถว EQ 1 band"""

    freq_hz: float
    gain_db: float = 0.0  # -15 - +15
    q: float = 1.0  # 0.1 - 10


@dataclass
class EQParams:
    """5-band parametric EQ"""

    enabled: bool = False
    band1: EQBand = field(default_factory=lambda: EQBand(freq_hz=60))     # sub bass
    band2: EQBand = field(default_factory=lambda: EQBand(freq_hz=250))    # bass
    band3: EQBand = field(default_factory=lambda: EQBand(freq_hz=1000))   # mid
    band4: EQBand = field(default_factory=lambda: EQBand(freq_hz=4000))   # presence
    band5: EQBand = field(default_factory=lambda: EQBand(freq_hz=10000))  # brilliance

    def bands(self) -> list[EQBand]:
        return [self.band1, self.band2, self.band3, self.band4, self.band5]


@dataclass
class CompressorParams:
    enabled: bool = False
    threshold_db: float = -20.0  # -60 - 0
    ratio: float = 4.0           # 1 - 20
    attack_ms: float = 5.0       # 0.1 - 100
    release_ms: float = 100.0    # 10 - 1000


@dataclass
class NoiseGateParams:
    """ตัดเสียงพื้นหลังเบาๆ"""

    enabled: bool = False
    threshold_db: float = -50.0  # -100 - 0
    attack_ms: float = 1.0       # 0.1 - 100
    release_ms: float = 100.0    # 10 - 1000
    ratio: float = 10.0          # 1 - 20


@dataclass
class WhisperParams:
    """Whisper effect — เปลี่ยนเสียงพูดให้กลายเป็นเสียงกระซิบ

    ทำงานโดย randomize phase ของ signal + เพิ่ม noise + high-pass
    ทำให้เสียงเสมือนว่าเป็นลมหายใจแต่ยังรักษา formant ของคำพูดไว้
    """

    enabled: bool = False
    amount: float = 0.7        # 0.0 - 1.0 (mix ระหว่างเสียงเดิมกับ whisper)
    noise_level: float = 0.15  # 0.0 - 0.5 (เสียงลมรบก)
    cutoff_hz: float = 1500.0  # high-pass cutoff (ตัดเสียงทุ้ม ทำให้เหมือนกระซิบ)


@dataclass
class VocoderParams:
    """Channel vocoder — ทำเสียงหุ่นยนต์แบบ AquesTalk/YMM

    ใช้ carrier oscillator + spectral envelope ของ input
    ทำให้ได้เสียง "หุ่นยนต์พูดได้" ที่มี character เฉพาะตัว
    """

    enabled: bool = False
    carrier_f0: float = 0.0      # 0=track pitch input, >0=monotone pitch
    waveform: int = 0            # 0=sawtooth, 1=square, 2=sine
    mix: float = 0.85            # 0=เดิม 1=vocoder เต็ม
    formant_shift: float = 1.0   # warp formant (1.0=ปกติ >1=สูง)
    smoothing: float = 0.5       # envelope smoothing


@dataclass
class ShimmerParams:
    """Shimmer + Jitter — ความผันแปรของ amplitude/pitch

    ทำให้เสียงมี character "synthesized" แบบ AquesTalk
    """

    enabled: bool = False
    shimmer_db: float = 1.5      # 0-6 dB (amplitude variation)
    jitter_percent: float = 0.5  # 0-3% (pitch variation)


@dataclass
class GainParams:
    enabled: bool = False
    gain_db: float = 0.0  # -24 - +24


@dataclass
class EffectsConfig:
    """โครงสร้างการตั้งค่า effects ทั้งหมด"""

    pitch_shift: PitchShiftParams = field(default_factory=PitchShiftParams)
    formant: FormantParams = field(default_factory=FormantParams)
    speed: SpeedParams = field(default_factory=SpeedParams)
    harmonizer: HarmonizerParams = field(default_factory=HarmonizerParams)
    reverb: ReverbParams = field(default_factory=ReverbParams)
    delay: DelayParams = field(default_factory=DelayParams)
    chorus: ChorusParams = field(default_factory=ChorusParams)
    distortion: DistortionParams = field(default_factory=DistortionParams)
    bitcrush: BitcrushParams = field(default_factory=BitcrushParams)
    lowpass: LowpassParams = field(default_factory=LowpassParams)
    highpass: HighpassParams = field(default_factory=HighpassParams)
    telephone: TelephoneParams = field(default_factory=TelephoneParams)
    eq: EQParams = field(default_factory=EQParams)
    compressor: CompressorParams = field(default_factory=CompressorParams)
    noise_gate: NoiseGateParams = field(default_factory=NoiseGateParams)
    whisper: WhisperParams = field(default_factory=WhisperParams)
    vocoder: VocoderParams = field(default_factory=VocoderParams)
    shimmer: ShimmerParams = field(default_factory=ShimmerParams)
    gain: GainParams = field(default_factory=GainParams)

    def clone(self) -> "EffectsConfig":
        return copy.deepcopy(self)

    def any_enabled(self) -> bool:
        return any(
            getattr(p, "enabled", False)
            for p in [
                self.pitch_shift,
                self.formant,
                self.speed,
                self.harmonizer,
                self.reverb,
                self.delay,
                self.chorus,
                self.distortion,
                self.bitcrush,
                self.lowpass,
                self.highpass,
                self.telephone,
                self.eq,
                self.compressor,
                self.noise_gate,
                self.whisper,
                self.vocoder,
                self.shimmer,
                self.gain,
            ]
        )

    def to_dict(self) -> dict:
        """convert เป็น dict (สำหรับ JSON serialization ใน profiles)"""
        import dataclasses

        def _convert(obj):
            if dataclasses.is_dataclass(obj):
                return {k: _convert(v) for k, v in dataclasses.asdict(obj).items()}
            return obj
        return _convert(self)

    @classmethod
    def from_dict(cls, data: dict) -> "EffectsConfig":
        """สร้างจาก dict (load profile)"""
        import dataclasses

        cfg = cls()
        # map field name → dataclass type
        field_types = {f.name: f.type for f in dataclasses.fields(cls)}

        # resolve type hints (string → class)
        type_map = {
            "PitchShiftParams": PitchShiftParams,
            "FormantParams": FormantParams,
            "SpeedParams": SpeedParams,
            "HarmonizerParams": HarmonizerParams,
            "ReverbParams": ReverbParams,
            "DelayParams": DelayParams,
            "ChorusParams": ChorusParams,
            "DistortionParams": DistortionParams,
            "BitcrushParams": BitcrushParams,
            "LowpassParams": LowpassParams,
            "HighpassParams": HighpassParams,
            "TelephoneParams": TelephoneParams,
            "EQParams": EQParams,
            "CompressorParams": CompressorParams,
            "NoiseGateParams": NoiseGateParams,
            "WhisperParams": WhisperParams,
            "VocoderParams": VocoderParams,
            "ShimmerParams": ShimmerParams,
            "GainParams": GainParams,
        }

        for key, value in data.items():
            if not hasattr(cfg, key):
                continue
            type_name = field_types.get(key)
            param_cls = type_map.get(type_name) if isinstance(type_name, str) else type_name
            if param_cls is None or not isinstance(value, dict):
                continue
            # nested EQBand สำหรับ EQ
            if param_cls is EQParams:
                eq_params = EQParams(enabled=value.get("enabled", False))
                for band_name in ["band1", "band2", "band3", "band4", "band5"]:
                    if band_name in value:
                        band_data = value[band_name]
                        band = EQBand(
                            freq_hz=band_data.get("freq_hz", 1000),
                            gain_db=band_data.get("gain_db", 0),
                            q=band_data.get("q", 1.0),
                        )
                        setattr(eq_params, band_name, band)
                setattr(cfg, key, eq_params)
            else:
                setattr(cfg, key, param_cls(**{
                    k: v for k, v in value.items()
                    if k in {f.name for f in dataclasses.fields(param_cls)}
                }))
        return cfg


# ---------------------------------------------------------------------- #
# Build the pedalboard chain
# ---------------------------------------------------------------------- #
def build_pedalboard(cfg: EffectsConfig) -> Pedalboard:
    """สร้าง Pedalboard ตาม config ที่เปิดไว้เท่านั้น

    ลำดับของ effects สำคัญ — ส่งผลต่อเสียงออก
    Note: Formant + Harmonizer ไม่อยู่ใน pedalboard (apply แยกใน apply_effects)
    """
    plugins = []

    # 1. Filters
    if cfg.highpass.enabled:
        plugins.append(HighpassFilter(cutoff_frequency_hz=cfg.highpass.cutoff_hz))

    if cfg.lowpass.enabled:
        plugins.append(LowpassFilter(cutoff_frequency_hz=cfg.lowpass.cutoff_hz))

    if cfg.telephone.enabled:
        plugins.append(HighpassFilter(cutoff_frequency_hz=300.0))
        plugins.append(LowpassFilter(cutoff_frequency_hz=3400.0))

    # 2. Noise gate
    if cfg.noise_gate.enabled:
        plugins.append(
            NoiseGate(
                threshold_db=cfg.noise_gate.threshold_db,
                attack_ms=cfg.noise_gate.attack_ms,
                release_ms=cfg.noise_gate.release_ms,
                ratio=cfg.noise_gate.ratio,
            )
        )

    # 3. EQ (5-band)
    if cfg.eq.enabled:
        for band in cfg.eq.bands():
            if band.gain_db != 0:
                plugins.append(
                    PeakFilter(
                        cutoff_frequency_hz=band.freq_hz,
                        gain_db=band.gain_db,
                        q=band.q,
                    )
                )

    # 4. Compressor
    if cfg.compressor.enabled:
        plugins.append(
            Compressor(
                threshold_db=cfg.compressor.threshold_db,
                ratio=cfg.compressor.ratio,
                attack_ms=cfg.compressor.attack_ms,
                release_ms=cfg.compressor.release_ms,
            )
        )

    # 5. Pitch shift
    if cfg.pitch_shift.enabled and cfg.pitch_shift.semitones != 0:
        plugins.append(PitchShift(semitones=cfg.pitch_shift.semitones))

    # 6. Bitcrush
    if cfg.bitcrush.enabled:
        plugins.append(Bitcrush(bit_depth=cfg.bitcrush.bit_depth))

    # 7. Distortion
    if cfg.distortion.enabled:
        plugins.append(Distortion(drive_db=cfg.distortion.drive_db))

    # 8. Chorus
    if cfg.chorus.enabled:
        plugins.append(
            Chorus(
                rate_hz=cfg.chorus.rate_hz,
                depth=cfg.chorus.depth,
                mix=cfg.chorus.mix,
                feedback=cfg.chorus.feedback,
                centre_delay_ms=cfg.chorus.centre_delay_ms,
            )
        )

    # 9. Reverb
    if cfg.reverb.enabled:
        plugins.append(
            Reverb(
                room_size=cfg.reverb.room_size,
                damping=cfg.reverb.damping,
                wet_level=cfg.reverb.wet_level,
                dry_level=cfg.reverb.dry_level,
                width=cfg.reverb.width,
                freeze_mode=cfg.reverb.freeze_mode,
            )
        )

    # 10. Delay
    if cfg.delay.enabled:
        plugins.append(
            Delay(
                delay_seconds=cfg.delay.delay_seconds,
                feedback=cfg.delay.feedback,
                mix=cfg.delay.mix,
            )
        )

    # 11. Gain
    if cfg.gain.enabled and cfg.gain.gain_db != 0:
        plugins.append(Gain(gain_db=cfg.gain.gain_db))

    return Pedalboard(plugins)


# ---------------------------------------------------------------------- #
# Apply effects
# ---------------------------------------------------------------------- #
def _resample_linear(audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """Resample แบบ linear interpolation"""
    if orig_sr == target_sr:
        return audio
    if audio.ndim == 1:
        n_samples = int(round(len(audio) * target_sr / orig_sr))
        idx = np.linspace(0, len(audio) - 1, n_samples)
        return np.interp(idx, np.arange(len(audio)), audio).astype(np.float32)
    n_samples = int(round(audio.shape[0] * target_sr / orig_sr))
    idx = np.linspace(0, audio.shape[0] - 1, n_samples)
    channels = [
        np.interp(idx, np.arange(audio.shape[0]), audio[:, c]).astype(np.float32)
        for c in range(audio.shape[1])
    ]
    return np.stack(channels, axis=1)


def apply_speed(audio: np.ndarray, factor: float) -> np.ndarray:
    """Time-stretch ผ่าน resample"""
    if factor == 1.0 or factor <= 0:
        return audio
    if factor > 1:
        indices = np.arange(0, len(audio), factor)
        return audio[indices.astype(int)]
    else:
        new_len = int(len(audio) / factor)
        idx = np.linspace(0, len(audio) - 1, new_len)
        if audio.ndim == 1:
            return np.interp(idx, np.arange(len(audio)), audio).astype(np.float32)
        return audio[idx.astype(int)]


def apply_downsample(audio: np.ndarray, factor: float) -> np.ndarray:
    """ลด sample rate แบบ sample-and-hold (ใช้กับ bitcrush)"""
    if factor <= 1:
        return audio
    # sample every Nth + hold
    out = np.zeros_like(audio)
    chunk = int(factor)
    if chunk < 1:
        chunk = 1
    for i in range(0, len(audio), chunk):
        end = min(i + chunk, len(audio))
        out[i:end] = audio[i]
    return out


def apply_whisper(
    audio: np.ndarray,
    sample_rate: int,
    amount: float = 0.7,
    noise_level: float = 0.15,
    cutoff_hz: float = 1500.0,
) -> np.ndarray:
    """เปลี่ยนเสียงพูดให้เป็นเสียงกระซิบ

    อัลกอริทึม:
      1. STFT ของ audio
      2. เก็บ magnitude (formant shape) แต่ randomize phase → เสียงกลายเป็น "ลม"
         (ยังรักษารูปร่างคำพูดจาก magnitude แต่เสียเสียง harmonic ของเสียงพูด)
      3. เพิ่ม white noise ตาม noise_level
      4. high-pass filter ตัดเสียงทุ้ม (เสียงกระซิบมี high-frequency เป็นหลัก)
      5. mix กับเสียงเดิมตาม amount
    """
    if amount <= 0 or len(audio) < 100:
        return audio.astype(np.float32, copy=False)

    n_fft = 2048
    hop = n_fft // 4
    window = np.hanning(n_fft)

    # pad ให้ยาวเป็นจำนวนเต็มของ hop
    pad_len = hop - (len(audio) % hop)
    padded = np.pad(audio, (0, pad_len))
    n_frames = 1 + (len(padded) - n_fft) // hop

    out = np.zeros(len(padded))
    norm = np.zeros(len(padded))

    # สร้าง noise สำหรับ phase randomization (fixed seed ให้ reproducible)
    rng = np.random.default_rng(42)

    for i in range(n_frames):
        start = i * hop
        frame = padded[start : start + n_fft] * window

        spectrum = np.fft.rfft(frame, n=n_fft)
        mag = np.abs(spectrum)

        # randomize phase แต่รักษา magnitude (formant shape)
        random_phase = np.exp(1j * rng.uniform(0, 2 * np.pi, len(mag)))
        whisper_spectrum = mag * random_phase
        whisper_frame = np.fft.irfft(whisper_spectrum, n=n_fft)

        # overlap-add
        out[start : start + n_fft] += whisper_frame * window
        norm[start : start + n_fft] += window**2

    norm = np.where(norm < 1e-8, 1e-8, norm)
    out = out / norm
    out = out[: len(audio)]

    # เพิ่ม white noise
    if noise_level > 0:
        noise = rng.standard_normal(len(out)).astype(np.float32) * noise_level * 0.1
        out = out + noise

    # high-pass filter (ตัดเสียงทุ้ม)
    if cutoff_hz > 0:
        hp = HighpassFilter(cutoff_frequency_hz=cutoff_hz)
        out = hp(out.astype(np.float32), sample_rate)

    # mix กับต้นฉบับ
    mixed = (1 - amount) * audio + amount * out

    # normalize
    peak = float(np.max(np.abs(mixed))) if mixed.size > 0 else 0.0
    if peak > 1.0:
        mixed = mixed / peak

    return mixed.astype(np.float32)


def apply_effects(
    audio: np.ndarray,
    sample_rate: int,
    cfg: EffectsConfig,
) -> tuple[np.ndarray, int]:
    """รัน effects chain บน audio

    Returns:
        (processed_audio, output_sample_rate)
    """
    # Imports ที่นี่เพื่อหลีกเลี่ยง circular import
    from formant import formant_shift_safe
    from harmonizer import harmonizer
    from vocoder import channel_vocoder, add_shimmer_jitter

    if audio.ndim == 2 and audio.shape[1] > 1:
        audio = audio.mean(axis=1)
    audio = audio.astype(np.float32, copy=False)

    # Upsample
    working_sr = sample_rate
    if sample_rate < OUTPUT_SR:
        audio = _resample_linear(audio, sample_rate, OUTPUT_SR)
        working_sr = OUTPUT_SR

    # 1. Whisper (ก่อน formant เพราะเปลี่ยน phase ทั้งหมด)
    if cfg.whisper.enabled:
        audio = apply_whisper(
            audio, working_sr,
            amount=cfg.whisper.amount,
            noise_level=cfg.whisper.noise_level,
            cutoff_hz=cfg.whisper.cutoff_hz,
        )

    # 2. Vocoder (AquesTalk-style robot voice) — ก่อน formant shift
    if cfg.vocoder.enabled:
        waveforms = ["sawtooth", "square", "sine"]
        wf = waveforms[int(cfg.vocoder.waveform) % 3]
        audio = channel_vocoder(
            audio, working_sr,
            carrier_f0=cfg.vocoder.carrier_f0,
            carrier_waveform=wf,
            mix=cfg.vocoder.mix,
            formant_shift=cfg.vocoder.formant_shift,
            smoothing=cfg.vocoder.smoothing,
        )

    # 3. Shimmer/Jitter (character variation)
    if cfg.shimmer.enabled:
        audio = add_shimmer_jitter(
            audio, working_sr,
            shimmer_db=cfg.shimmer.shimmer_db,
            jitter_percent=cfg.shimmer.jitter_percent,
        )

    # 4. Formant shift (ใช้ safe version)
    if cfg.formant.enabled and abs(cfg.formant.ratio - 1.0) >= 0.02:
        audio = formant_shift_safe(audio, working_sr, shift_ratio=cfg.formant.ratio)

    # 5. Speed
    if cfg.speed.enabled and cfg.speed.factor != 1.0:
        audio = apply_speed(audio, cfg.speed.factor)

    # 6. Harmonizer
    if cfg.harmonizer.enabled:
        voices = []
        if cfg.harmonizer.voice1_gain > 0:
            voices.append((cfg.harmonizer.voice1_semitones, cfg.harmonizer.voice1_gain))
        if cfg.harmonizer.voice2_gain > 0:
            voices.append((cfg.harmonizer.voice2_semitones, cfg.harmonizer.voice2_gain))
        if voices:
            audio = harmonizer(audio, working_sr, voices=voices, dry_mix=cfg.harmonizer.dry_mix)

    # 7. Bitcrush downsampling
    if cfg.bitcrush.enabled and cfg.bitcrush.downsample_factor > 1:
        audio = apply_downsample(audio, cfg.bitcrush.downsample_factor)

    # 8. Pedalboard chain (filters, EQ, compressor, pitch, distortion, chorus, reverb, delay, gain)
    board = build_pedalboard(cfg)
    if len(board) > 0:
        audio = board(audio, working_sr)

    # 9. Normalize ป้องกัน clipping
    peak = float(np.max(np.abs(audio))) if audio.size > 0 else 0.0
    if peak > 1.0:
        audio = audio / peak

    # ตรวจ NaN/inf
    if not np.all(np.isfinite(audio)):
        audio = _resample_linear(audio, sample_rate, working_sr) if sample_rate < OUTPUT_SR else audio

    return audio.astype(np.float32), working_sr
