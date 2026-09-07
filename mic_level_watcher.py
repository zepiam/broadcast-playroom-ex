"""mic_level_watcher.py — วัดระดับเสียงไมโครโฟนแบบ real-time (สำหรับ Avatar widget)

ใช้ PyAudio (PortAudio) แทน sounddevice เพราะ:
- sounddevice ไม่สามารถอ่านสัญญาณจากอุปกรณ์เสียงบางตัว (เช่น TASCAM) บน Windows
- PyAudio เข้าถึงได้ครบทุก device (เหมือน OBS)

Flow:
  1. เปิด PyAudio stream จากไมโครโฟนที่เลือก
  2. อ่าน chunk ใน background thread → คำนวณ RMS → dB
  3. smoothing (กัน flicker)
  4. เรียก on_level(dB) ทุก chunk
  5. app.py รับ → push ไป composer overlay
"""
from __future__ import annotations

import logging
import math
import threading
from typing import Callable, Optional

logger = logging.getLogger("mic_watcher")

# ★ lazy import pyaudio (กัน crash ถ้าไม่มีในระบบ)
_pa = None
def _get_pa():
    global _pa
    if _pa is None:
        try:
            import pyaudio
            _pa = pyaudio
        except Exception as e:
            logger.warning(f"pyaudio not available: {e}")
            _pa = False
    return _pa


def list_input_devices() -> list:
    """คืนรายการ audio input devices ในระบบ (PyAudio) — กรองซ้ำ + จัดลำดับ

    ★ แสดงเฉพาะ MME hostapi (hostApi=0) เพื่อลด device ซ้ำ
      (MME + DirectSound + WASAPI มักเป็น device เดียวกันซ้ำ 3-4 รอบ)

    Returns: [{index, name, channels, is_default, is_mic}, ...]
    """
    pa = _get_pa()
    if not pa:
        return []
    try:
        p = pa.PyAudio()
        result = []
        try:
            default_info = p.get_default_input_device_info()
            default_idx = default_info.get('index', -1)
        except Exception:
            default_idx = -1
        for i in range(p.get_device_count()):
            try:
                info = p.get_device_info_by_index(i)
                # ★ กรองเฉพาะ MME (hostApi=0) — กัน duplicate ข้าม hostapi
                if info.get('hostApi', -1) != 0:
                    continue
                if info.get('maxInputChannels', 0) <= 0:
                    continue
                name = str(info.get('name', f'Device {i}'))
                name_lower = name.lower()
                is_mic = any(kw in name_lower for kw in ['mic', 'microphone', 'ไมโคร'])
                result.append({
                    'index': i,
                    'name': name,
                    'channels': int(info.get('maxInputChannels', 0)),
                    'is_default': (i == default_idx),
                    'is_mic': is_mic,
                })
            except Exception:
                continue
        p.terminate()
        # ★ จัดลำดับ: default ก่อน → ไมโครโฟน → อันอื่น
        result.sort(key=lambda d: (0 if d['is_default'] else 1, 0 if d['is_mic'] else 1, d['index']))
        return result
    except Exception as e:
        logger.warning(f"list_input_devices failed: {e}")
        return []


def get_default_input_index() -> int:
    """คืน index ของ default input device (-1 ถ้าไม่มี)"""
    pa = _get_pa()
    if not pa:
        return -1
    try:
        p = pa.PyAudio()
        idx = p.get_default_input_device_info().get('index', -1)
        p.terminate()
        return idx
    except Exception:
        return -1


class MicLevelWatcher:
    """วัดระดับเสียงไมโครโฟนแบบ real-time ใน background thread (PyAudio)

    Args:
        on_level: callback(level_db: float) — เรียกทุก chunk (~30ms)
        device_index: index ของไมโครโฟน (None = system default)
        chunk_ms: ขนาด chunk มิลลิวินาที (default 30ms)
    """

    def __init__(self,
                 on_level: Optional[Callable[[float], None]] = None,
                 device_index: Optional[int] = None,
                 chunk_ms: int = 30,
                 gain: float = 100.0):
        self.on_level = on_level
        self.device_index = device_index
        self.chunk_ms = max(10, min(100, chunk_ms))
        # ★ software gain — ขยายสัญญาณ dynamic mic ที่เบา (~-74 dB → -34 dB)
        #   100x = +40 dB boost (เหมาะกับ dynamic mic ส่วนใหญ่)
        self.gain = max(1.0, float(gain))
        self._stream = None
        self._pa_instance = None
        self._running = False
        self._thread = None
        # ★ smoothing — ลด flicker (alpha สูง = ตอบสนองเร็ว)
        self._smooth_db = -60.0
        self._smooth_alpha = 0.6  # ใหม่ 60% + เก่า 40% (ตอบสนองเร็วขึ้น)
        self._lock = threading.Lock()
        self._stop_event = threading.Event()

    def start(self) -> bool:
        """เริ่มวัดเสียง — คืน True ถ้าสำเร็จ"""
        pa = _get_pa()
        if not pa:
            logger.warning("pyaudio not available — cannot start mic watcher")
            return False
        with self._lock:
            if self._running:
                return True
            try:
                self._pa_instance = pa.PyAudio()
                self._stop_event.clear()
                self._running = True
                # ★ รันใน background thread — PyAudio เป็น blocking API
                self._thread = threading.Thread(target=self._read_loop, name="MicWatcher", daemon=True)
                self._thread.start()
                logger.info(f"MicLevelWatcher started (device={self.device_index})")
                return True
            except Exception as e:
                logger.error(f"MicLevelWatcher start failed: {e}")
                self._running = False
                return False

    def _read_loop(self):
        """background thread — เปิด stream + อ่าน chunk ไปเรื่อยๆ"""
        pa = _get_pa()
        if not pa or self._pa_instance is None:
            self._running = False
            return
        try:
            RATE = 44100
            CHUNK = int(RATE * self.chunk_ms / 1000)
            # ★ เปิด stream — input_device_index=None = system default
            kwargs = dict(
                format=pa.paFloat32,
                channels=1,
                rate=RATE,
                input=True,
                frames_per_buffer=CHUNK,
            )
            if self.device_index is not None and self.device_index >= 0:
                kwargs['input_device_index'] = self.device_index
            self._stream = self._pa_instance.open(**kwargs)
            self._stream.start_stream()
            import numpy as np
            while not self._stop_event.is_set() and self._running:
                try:
                    data = self._stream.read(CHUNK, exception_on_overflow=False)
                except Exception as e:
                    logger.debug(f"read error: {e}")
                    break
                if not data:
                    continue
                # ★ compute RMS → dB (พร้อม software gain สำหรับ dynamic mic)
                samples = np.frombuffer(data, dtype=np.float32)
                # ★ ขยายสัญญาณ + clip กัน distortion
                if self.gain > 1.0:
                    samples = np.clip(samples * self.gain, -1.0, 1.0)
                rms = float(math.sqrt(float(np.mean(samples * samples)))) if len(samples) else 0.0
                rms = max(rms, 1e-7)
                db_raw = 20.0 * math.log10(rms)
                db = max(-60.0, min(0.0, db_raw))
                # ★ smoothing
                self._smooth_db = self._smooth_db * (1 - self._smooth_alpha) + db * self._smooth_alpha
                # ★ เรียก callback
                if self.on_level:
                    try:
                        self.on_level(self._smooth_db)
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"MicLevelWatcher read_loop error: {e}")
        finally:
            self._running = False
            try:
                if self._stream:
                    self._stream.stop_stream()
                    self._stream.close()
            except Exception:
                pass

    def stop(self):
        """หยุดวัด"""
        with self._lock:
            if not self._running and self._thread is None:
                return
            self._running = False
            self._stop_event.set()
        # ★ รอ thread จบ (นอก lock กัน deadlock)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None
        with self._lock:
            if self._pa_instance:
                try:
                    self._pa_instance.terminate()
                except Exception:
                    pass
                self._pa_instance = None
            self._stream = None

    @property
    def is_running(self) -> bool:
        return self._running

    def set_device(self, device_index: Optional[int]):
        """เปลี่ยนไมโครโฟน — restart stream"""
        was_running = self._running
        if was_running:
            self.stop()
        self.device_index = device_index
        if was_running:
            self.start()


if __name__ == "__main__":
    # ★ test — วัดเสียง 5 วินาที
    import time
    print("Testing mic level (5s)...")
    devices = list_input_devices()
    print(f"Found {len(devices)} input devices:")
    for d in devices[:8]:
        print(f"  [{d['index']}] {d['name']}")
    def on_lvl(db):
        bar = "█" * int((db + 60) / 60 * 30)
        print(f"  {db:6.1f} dB |{bar:<30}|")
    w = MicLevelWatcher(on_level=on_lvl)
    if w.start():
        time.sleep(5)
        w.stop()
        print("Done.")
    else:
        print("Failed to start.")
