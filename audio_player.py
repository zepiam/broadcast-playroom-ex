"""audio_player.py — เล่นไฟล์เสียงด้วย pygame mixer

รองรับ Play / Pause / Resume / Stop / Seek และควบคุม volume
เล่นใน background thread ของ pygame เอง ไม่บล็อก GUI
"""
from __future__ import annotations

import os
import tempfile
from typing import Callable, Optional

import numpy as np
import pygame
import soundfile as sf


class AudioPlayer:
    """เล่นไฟล์เสียง — รองรับ pause/resume/stop/seek"""

    def __init__(self) -> None:
        # เริ่ม pygame mixer ครั้งเดียว — ลองหลาย driver เพื่อกัน WASAPI ล้มเหลว
        # (เกิดได้ตอน device ถูก exclusive ใช้, Bluetooth กำลังเชื่อม, ฯลฯ)
        if not pygame.mixer.get_init():
            self._init_mixer_with_fallback()
        self._current_sound: Optional[pygame.mixer.Sound] = None
        self._current_file: Optional[str] = None  # path ไฟล์ temp ที่กำลังเล่น
        self._start_ms: int = 0       # เวลาที่เริ่มเล่น (pygame.time.get_ticks)
        self._offset_ms: int = 0      # ตำแหน่งที่กำลังเล่น (สะสม)
        self._is_paused: bool = False
        self._was_playing: bool = False  # เคยกด play แล้วหรือยัง (ใช้ตรวจ playback end)
        self._duration_ms: int = 0
        self._volume: float = 1.0
        self._end_callback: Optional[Callable[[], None]] = None

    @staticmethod
    def _init_mixer_with_fallback() -> None:
        """ลอง init mixer หลายวิธี — default → DirectSound → larger buffer"""
        import pygame
        last_err = None
        # วิธีสร้างลำดับ: default → DirectSound (fallback driver) → larger buffer
        attempts = [
            dict(frequency=44100, size=-16, channels=2, buffer=512),
            dict(frequency=44100, size=-16, channels=2, buffer=1024),
            dict(frequency=44100, size=-16, channels=2, buffer=2048),
            dict(frequency=22050, size=-16, channels=2, buffer=1024),
        ]
        for opts in attempts:
            try:
                pygame.mixer.init(**opts)
                return
            except pygame.error as e:
                last_err = e
                try:
                    pygame.mixer.quit()
                except Exception:
                    pass
        # ลอง force DirectSound driver บน Windows
        try:
            os.environ["SDL_AUDIODRIVER"] = "directsound"
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=1024)
            return
        except pygame.error as e:
            last_err = e
            try:
                pygame.mixer.quit()
            except Exception:
                pass
        # ทุกวิธีล้มเหลว — แจ้งเตือนชัดเจน
        raise RuntimeError(
            "ไม่สามารถเริ่มระบบเสียงได้\n\n"
            "อาจเกิดจาก:\n"
            "  • ไม่มีอุปกรณ์เสียงเสียบ / Bluetooth กำลังเชื่อมต่อ\n"
            "  • อุปกรณ์เสียงถูกใช้แบบ exclusive โดยแอปอื่น\n"
            "  • WASAPI ล้มเหลว\n\n"
            f"รายละเอียด: {last_err}\n\n"
            "ลอง: ปิดแอปเสียงอื่น (Discord, OBS) → เสียบหูฟัง → เปิดใหม่"
        )
        self._current_file: Optional[str] = None  # path ไฟล์ temp ที่กำลังเล่น
        self._start_ms: int = 0       # เวลาที่เริ่มเล่น (pygame.time.get_ticks)
        self._offset_ms: int = 0      # ตำแหน่งที่กำลังเล่น (สะสม)
        self._is_paused: bool = False
        self._was_playing: bool = False  # เคยกด play แล้วหรือยัง (ใช้ตรวจ playback end)
        self._duration_ms: int = 0
        self._volume: float = 1.0
        self._end_callback: Optional[Callable[[], None]] = None

    # ------------------------------------------------------------------ #
    # Loading
    # ------------------------------------------------------------------ #
    def load_audio(
        self,
        audio: np.ndarray,
        sample_rate: int,
        end_callback: Optional[Callable[[], None]] = None,
    ) -> None:
        """โหลด audio numpy array เข้า player

        Args:
            audio: float32 mono array
            sample_rate: sample rate
            end_callback: เรียกเมื่อเล่นจบ (ใช้สำหรับ UI อัปเดต)
        """
        # หยุดเสียงเดิม
        self.stop()

        # เขียนลง temp file แบบ WAV (pygame อ่าน WAV ได้ดีที่สุด)
        # ใช้ tempdir ของ OS และลบตอนโหลดใหม่
        audio_int16 = self._to_int16(audio)
        temp_dir = tempfile.gettempdir()
        path = os.path.join(temp_dir, "thai_tts_playback.wav")
        sf.write(path, audio_int16, sample_rate, subtype="PCM_16")

        self._current_file = path
        self._current_sound = pygame.mixer.Sound(path)
        self._current_sound.set_volume(self._volume)
        self._duration_ms = int(len(audio_int16) / sample_rate * 1000)
        self._offset_ms = 0
        self._is_paused = False
        self._was_playing = False
        self._end_callback = end_callback

    @staticmethod
    def _to_int16(audio: np.ndarray) -> np.ndarray:
        """แปลง float32 [-1, 1] → int16 [-32768, 32767]"""
        audio = np.clip(audio, -1.0, 1.0)
        audio_int16 = (audio * 32767).astype(np.int16)
        # pygame mixer เปิดด้วย stereo (2 channels) → ถ้า mono ให้ขยายเป็น stereo
        if audio_int16.ndim == 1:
            audio_int16 = np.stack([audio_int16, audio_int16], axis=1)
        return audio_int16

    # ------------------------------------------------------------------ #
    # Playback control
    # ------------------------------------------------------------------ #
    def play(self) -> None:
        """กด Play — เริ่มเล่นหรือ resume"""
        if self._current_sound is None:
            return

        if self._is_paused:
            # resume
            pygame.mixer.unpause()
            self._start_ms = pygame.time.get_ticks()
            self._is_paused = False
            self._was_playing = True
        elif not pygame.mixer.get_busy():
            # เริ่มเล่นใหม่
            self._current_sound.play()
            self._start_ms = pygame.time.get_ticks()
            self._was_playing = True

    def pause(self) -> None:
        """หยุดชั่วคราว"""
        if pygame.mixer.get_busy() and not self._is_paused:
            pygame.mixer.pause()
            # สะสมตำแหน่งที่เล่นถึง
            elapsed = pygame.time.get_ticks() - self._start_ms
            self._offset_ms += elapsed
            self._is_paused = True

    def stop(self) -> None:
        """หยุดเล่นและกลับไปที่จุดเริ่มต้น"""
        pygame.mixer.stop()
        self._offset_ms = 0
        self._is_paused = False
        self._was_playing = False

    def seek(self, position_ms: int) -> None:
        """กระโดดไปยังตำแหน่ง — อ่านจาก file ใหม่"""
        if self._current_sound is None or self._current_file is None:
            return
        position_ms = max(0, min(position_ms, self._duration_ms))

        was_playing = pygame.mixer.get_busy() and not self._is_paused
        pygame.mixer.stop()

        # pygame Sound ไม่รองรับ seek ตรงๆ ต้องโหลดใหม่แล้ว skip
        # วิธีง่ายสุดคือใช้ Channel + set_volume แล้วเล่นจาก sample offset
        # แต่ pygame ทำได้ยาก → เราจะใช้วิธี "โหลดใหม่แล้ว skip"
        # สำหรับ voice memo ความแม่นยำไม่สำคัญมาก
        self._offset_ms = position_ms
        if was_playing:
            self.play_from_offset()

    def play_from_offset(self) -> None:
        """เล่นจากตำแหน่ง _offset_ms"""
        if self._current_sound is None or self._current_file is None:
            return
        # pygame.mixer.music รองรับ start pos ดีกว่า Sound
        # แต่จะใช้ได้ต้อง load ใหม่เป็น music
        pygame.mixer.stop()
        # ใช้ mixer.music (รองรับ seek ด้วย set_pos)
        try:
            pygame.mixer.music.load(self._current_file)
            pygame.mixer.music.set_volume(self._volume)
            pygame.mixer.music.play(start=self._offset_ms / 1000.0)
            self._start_ms = pygame.time.get_ticks()
            self._is_paused = False
        except Exception:
            # ถ้า set_pos ไม่รองรับ ก็แค่เล่นใหม่ตั้งแต่ต้น
            self._current_sound.play()
            self._start_ms = pygame.time.get_ticks()
            self._offset_ms = 0

    # ------------------------------------------------------------------ #
    # Status
    # ------------------------------------------------------------------ #
    def get_position_ms(self) -> int:
        """ตำแหน่งปัจจุบัน (ms)"""
        if self._current_sound is None:
            return 0
        if self._is_paused:
            return self._offset_ms
        if pygame.mixer.get_busy():
            elapsed = pygame.time.get_ticks() - self._start_ms
            pos = self._offset_ms + elapsed
            return min(pos, self._duration_ms)
        return self._duration_ms if self._offset_ms > 0 else 0

    def get_duration_ms(self) -> int:
        return self._duration_ms

    def is_playing(self) -> bool:
        return pygame.mixer.get_busy() and not self._is_paused

    def is_paused(self) -> bool:
        return self._is_paused

    def is_loaded(self) -> bool:
        return self._current_sound is not None

    def set_volume(self, volume: float) -> None:
        """ตั้ง volume 0.0 - 1.0"""
        self._volume = max(0.0, min(1.0, volume))
        if self._current_sound is not None:
            self._current_sound.set_volume(self._volume)
        try:
            pygame.mixer.music.set_volume(self._volume)
        except Exception:
            pass

    def has_finished(self) -> bool:
        """เช็คว่าเล่นจบแล้วหรือยัง — เรียกเป็น polling

        ใช้ `_was_playing` flag เพื่อตรวจว่า "เคยเริ่มเล่นแล้วหยุดเอง"
        (pygame.mixer ไม่ได้บอกตรงๆ ว่าจบ — แค่บอกว่า not busy ตอนนี้)
        """
        if self._current_sound is None or self._is_paused:
            return False
        if pygame.mixer.get_busy():
            return False
        # ถ้าก่อนหน้านี้เคยเล่น (และไม่ได้ถูก stop) → จบเองแล้ว
        if self._was_playing:
            self._was_playing = False  # reset เพื่อกัน trigger ซ้ำ
            return True
        return False

    # ------------------------------------------------------------------ #
    # Cleanup
    # ------------------------------------------------------------------ #
    def cleanup(self) -> None:
        """ล้างทุกอย่าง — เรียกตอนปิดโปรแกรม"""
        try:
            pygame.mixer.stop()
            pygame.mixer.quit()
        except Exception:
            pass
