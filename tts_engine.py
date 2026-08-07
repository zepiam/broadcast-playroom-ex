"""tts_engine.py — Text-to-Speech wrapper สำหรับ edge-tts + prosody tag parsing

รันงาน edge-tts ใน worker thread แยก + รองรับ prosody tags แบบง่าย:
  <break time="500ms"/>  → แทรกความเงียบ
  <emph>คำสำคัญ</emph>   → render แยกด้วย rate ลดลง + pitch สูงขึ้น

อัลกอริทึม prosody:
  1. parse text ออกเป็น segment (text ปกติ, break, emph)
  2. render แต่ละ segment ผ่าน edge-tts แยก (emph ใช้ rate="-20%" pitch="+10Hz")
  3. สำหรับ break → สร้าง silence ตามเวลาที่กำหนด
  4. concat ทุก segment เป็น MP3 ชุดเดียว
"""
from __future__ import annotations

import asyncio
import io
import re
import threading
from dataclasses import dataclass, field
from typing import Callable, Optional

import edge_tts
import numpy as np


# ---------------------------------------------------------------------- #
# Prosody parsing
# ---------------------------------------------------------------------- #
# regex หา tag <break time="500ms"/> และ <emph>...</emph>
_BREAK_RE = re.compile(
    r'<break\s+time\s*=\s*["\'](\d+(?:\.\d+)?)(ms|s)["\']\s*/?>',
    re.IGNORECASE,
)
_EMPH_RE = re.compile(r'<emph\s*>(.*?)</emph\s*>', re.IGNORECASE | re.DOTALL)
# underscore pattern: 2+ underscores ติดกันคือ pause (n × 0.05s)
# 1 underscore เดี่ยวไม่นับ (อาจเป็นคำปกติเช่น "file_name")
_UNDERSCORE_RE = re.compile(r'_{2,}')

# pipe pattern: 1+ pipes ติดกันต่อท้ายคำ = stretch เสียงสุดท้าย (n × 0.1s)
# เช่น "มาก|" = ลาก 0.1s, "มาก|||" = ลาก 0.3s
_PIPE_RE = re.compile(r'\|+')

# แต่ละ underscore = 0.05 วินาที
SECONDS_PER_UNDERSCORE = 0.05
# แต่ละ pipe = 0.1 วินาที stretch
SECONDS_PER_PIPE = 0.1


@dataclass
class Segment:
    """segment หนึ่งของข้อความที่จะ render"""

    kind: str  # "text" | "break" | "emph" | "stretch"
    text: str = ""
    break_seconds: float = 0.0
    stretch_seconds: float = 0.0  # ใช้ตอน kind="stretch"


def parse_text_to_segments(text: str) -> list[Segment]:
    """แยกข้อความออกเป็น segments ตาม prosody tags

    Tags ที่รองรับ:
      <break time='500ms'/>  → แทรก 0.5 วินาที
      <emph>คำสำคัญ</emph>   → เน้นคำนั้น
      __ (2+ underscores)    → pause ตามจำนวน × 0.05 วิ
      | (1+ pipes)            → stretch เสียงสุดท้าย × 0.1 วิ

    Example:
      "สวัสดี__ครับ"     → [text "สวัสดี", break 0.1s, text "ครับ"]
      "มาก|||"          → [stretch "มาก" 0.3s]
      "เรียน|||เก่ง"     → [stretch "เรียน" 0.3s, text "เก่ง"]
    """
    segments: list[Segment] = []
    pos = 0

    # รวม tag ทั้งหมดเป็น list of matches เรียงตามตำแหน่ง
    # (start, end, kind, data)
    matches: list[tuple[int, int, str, dict]] = []

    for m in _BREAK_RE.finditer(text):
        time_val = float(m.group(1))
        unit = m.group(2).lower()
        seconds = time_val / 1000 if unit == "ms" else time_val
        matches.append((m.start(), m.end(), "break", {"seconds": seconds}))

    for m in _EMPH_RE.finditer(text):
        matches.append((m.start(), m.end(), "emph", {"text": m.group(1)}))

    # underscore sequences (2+ ตัว)
    for m in _UNDERSCORE_RE.finditer(text):
        n_underscores = len(m.group(0))
        seconds = n_underscores * SECONDS_PER_UNDERSCORE
        matches.append((m.start(), m.end(), "break", {"seconds": seconds}))

    # pipe sequences (1+ ตัว) — สื่อว่า stretch เสียงสุดท้ายของ text ก่อนหน้า
    for m in _PIPE_RE.finditer(text):
        n_pipes = len(m.group(0))
        seconds = n_pipes * SECONDS_PER_PIPE
        matches.append((m.start(), m.end(), "stretch", {"seconds": seconds}))

    # เรียงตาม start position; ถ้าตำแหน่งเท่ากัน → break ก่อน stretch ก่อน emph
    priority = {"break": 0, "stretch": 1, "emph": 2}
    matches.sort(key=lambda x: (x[0], priority.get(x[2], 3)))

    for start, end, kind, data in matches:
        # เก็บ text ที่อยู่ก่อน tag นี้
        if start > pos:
            segments.append(Segment(kind="text", text=text[pos:start]))
        if kind == "break":
            segments.append(Segment(kind="break", break_seconds=data["seconds"]))
        elif kind == "stretch":
            # stretch ไม่สร้าง segment ใหม่ แต่ mark ว่า segment ก่อนหน้าต้อง stretch
            # เก็บเป็น segment คู่กับ text ที่จะ stretch
            # วิธี: สร้าง segment ชนิด "stretch" ที่มี stretch_seconds
            # decode ที่หลังจะรู้ว่าต้องไป stretch ส่วนท้ายของ segment ก่อนหน้า
            segments.append(Segment(kind="stretch_marker", stretch_seconds=data["seconds"]))
        elif kind == "emph":
            segments.append(Segment(kind="emph", text=data["text"]))
        pos = end

    # เก็บ text ที่เหลือท้าย
    if pos < len(text):
        segments.append(Segment(kind="text", text=text[pos:]))

    # กรอง segment ว่าง
    return [s for s in segments if s.kind != "text" or s.text.strip()]


# ---------------------------------------------------------------------- #
# TTSParams + Engine
# ---------------------------------------------------------------------- #
@dataclass
class TTSParams:
    """พารามิเตอร์สำหรับสั่งสร้างเสียง"""

    text: str
    voice: str = "th-TH-PremwadeeNeural"
    rate: str = "+0%"
    volume: str = "+0%"
    pitch: str = "+0Hz"
    # emphasis settings — ใช้ตอน render <emph> tag
    emph_rate: str = "-20%"
    emph_pitch: str = "+10Hz"


class TTSEngine:
    """เรียก edge-tts แบบ async ใน worker thread"""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self._worker = threading.Thread(target=self._run_loop, daemon=True)
        self._worker.start()
        self._ready.wait(timeout=5)

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._ready.set()
        self._loop.run_forever()

    def shutdown(self) -> None:
        try:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._worker.join(timeout=2)
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # Synthesis (core)
    # ------------------------------------------------------------------ #
    async def _synthesize_segment(
        self, text: str, voice: str, rate: str, volume: str, pitch: str
    ) -> bytes:
        """สร้างเสียงให้ segment เดียว → คืน MP3 bytes"""
        communicate = edge_tts.Communicate(
            text, voice=voice, rate=rate, volume=volume, pitch=pitch,
        )
        buffer = bytearray()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buffer.extend(chunk["data"])
        return bytes(buffer)

    async def _synthesize_with_prosody(self, params: TTSParams) -> bytes:
        """สร้างเสียงพร้อม prosody tags → คืน MP3 bytes ที่ concat แล้ว

        ถ้าไม่มี prosody tag ใน text → render ทีเดียว (เร็ว)
        ถ้ามี → render แต่ละ segment แยกแล้ว concat (ช้ากว่า)
        """
        text = params.text

        # เช็คว่ามี prosody tag อะไรไหม
        has_prosody = bool(
            _BREAK_RE.search(text)
            or _EMPH_RE.search(text)
            or _UNDERSCORE_RE.search(text)
            or _PIPE_RE.search(text)
        )

        if not has_prosody:
            return await self._synthesize_segment(
                text, params.voice, params.rate, params.volume, params.pitch
            )

        # มี prosody — split และ render ทีละ segment
        segments = parse_text_to_segments(text)
        if not segments:
            return b""

        mp3_chunks: list[bytes] = []
        for seg in segments:
            if seg.kind == "text":
                chunk = await self._synthesize_segment(
                    seg.text, params.voice, params.rate, params.volume, params.pitch
                )
                if chunk:
                    mp3_chunks.append(chunk)
            elif seg.kind == "emph":
                chunk = await self._synthesize_segment(
                    seg.text, params.voice, params.emph_rate, params.volume, params.emph_pitch
                )
                if chunk:
                    mp3_chunks.append(chunk)
            elif seg.kind == "break" and seg.break_seconds > 0:
                # silence marker (decode ที่หลังใน GUI)
                microseconds = int(seg.break_seconds * 1_000_000)
                marker = SILENCE_MARKER + microseconds.to_bytes(8, "little", signed=False)
                mp3_chunks.append(marker)
            elif seg.kind == "stretch_marker" and seg.stretch_seconds > 0:
                # stretch marker — เก็บเป็น microseconds แล้ว decode ที่หลังจะ time-stretch
                # เสียงส่วนท้ายของ segment ก่อนหน้า
                microseconds = int(seg.stretch_seconds * 1_000_000)
                marker = STRETCH_MARKER + microseconds.to_bytes(8, "little", signed=False)
                mp3_chunks.append(marker)

        return b"".join(mp3_chunks)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def generate(
        self,
        params: TTSParams,
        on_done: Callable[[bytes], None],
        on_error: Callable[[str], None],
    ) -> None:
        if not params.text.strip():
            on_error("กรุณาพิมพ์ข้อความก่อน")
            return

        def _task_done(fut: asyncio.Future) -> None:
            try:
                result = fut.result()
                on_done(result)
            except Exception as exc:  # noqa: BLE001
                on_error(self._format_error(exc))

        coroutine = self._synthesize_with_prosody(params)
        future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        future.add_done_callback(_task_done)

    def list_voices(
        self,
        on_done: Callable[[list[dict]], None],
        on_error: Callable[[str], None],
    ) -> None:
        async def _fetch() -> list[dict]:
            voices = await edge_tts.list_voices()
            return list(voices)

        def _task_done(fut: asyncio.Future) -> None:
            try:
                on_done(fut.result())
            except Exception as exc:  # noqa: BLE001
                on_error(self._format_error(exc))

        future = asyncio.run_coroutine_threadsafe(_fetch(), self._loop)
        future.add_done_callback(_task_done)

    @staticmethod
    def _format_error(exc: Exception) -> str:
        msg = str(exc).lower()
        if "no audio received" in msg or "401" in msg or "403" in msg:
            return (
                "ไม่สามารถสร้างเสียงได้ — ตรวจสอบการเชื่อมต่ออินเทอร์เน็ต "
                "หรืออัปเดต edge-tts (pip install -U edge-tts)"
            )
        if "websocket" in msg or "connection" in msg or "timeout" in msg:
            return "เชื่อมต่อเซิร์ฟเวอร์ไม่ได้ — ตรวจสอบอินเทอร์เน็ต"
        return f"เกิดข้อผิดพลาด: {exc}"


# ---------------------------------------------------------------------- #
# Silence marker utilities (สำหรับ decode ใน GUI)
# ---------------------------------------------------------------------- #
SILENCE_MARKER = b"\x00\x00TTSSILENCE"
STRETCH_MARKER = b"\x00\x00TTSSTRETCH"


def split_mp3_with_silence_markers(combined: bytes) -> list[tuple[str, bytes | float]]:
    """แยก MP3 ที่ concat กับ silence/stretch markers

    Returns:
        list of (kind, data):
          ("audio", mp3_bytes)
          ("silence", seconds_float)
          ("stretch", seconds_float)
    """
    parts: list[tuple[str, bytes | float]] = []
    pos = 0
    current_audio = bytearray()

    while pos < len(combined):
        # หา silence marker หรือ stretch marker (เลือกอันที่ใกล้สุด)
        silence_pos = combined.find(SILENCE_MARKER, pos)
        stretch_pos = combined.find(STRETCH_MARKER, pos)

        # เลือก marker ที่ใกล้สุด
        candidates = []
        if silence_pos != -1:
            candidates.append((silence_pos, SILENCE_MARKER, "silence"))
        if stretch_pos != -1:
            candidates.append((stretch_pos, STRETCH_MARKER, "stretch"))

        if not candidates:
            current_audio.extend(combined[pos:])
            break

        marker_pos, marker, kind = min(candidates, key=lambda x: x[0])

        # เก็บ audio ก่อน marker
        if marker_pos > pos:
            current_audio.extend(combined[pos:marker_pos])

        # flush current audio
        if current_audio:
            parts.append(("audio", bytes(current_audio)))
            current_audio = bytearray()

        # อ่าน duration (8 bytes หลัง marker = microseconds)
        dur_start = marker_pos + len(marker)
        dur_end = dur_start + 8
        if dur_end > len(combined):
            pos = dur_end
            continue
        microseconds = int.from_bytes(combined[dur_start:dur_end], "little", signed=False)
        parts.append((kind, microseconds / 1_000_000.0))
        pos = dur_end

    if current_audio:
        parts.append(("audio", bytes(current_audio)))

    return parts


# ---------------------------------------------------------------------- #
# CLI smoke test
# ---------------------------------------------------------------------- #
if __name__ == "__main__":
    import sys

    text = sys.argv[1] if len(sys.argv) > 1 else "สวัสดี<break time='500ms'/>ครับ <emph>มาก</emph>ๆ"
    voice = sys.argv[2] if len(sys.argv) > 2 else "th-TH-PremwadeeNeural"

    engine = TTSEngine()
    done_event = threading.Event()
    result: dict[str, object] = {}

    def on_done(data: bytes) -> None:
        result["data"] = data
        done_event.set()

    def on_error(err: str) -> None:
        result["error"] = err
        done_event.set()

    engine.generate(TTSParams(text=text, voice=voice), on_done, on_error)
    done_event.wait(timeout=60)
    engine.shutdown()

    if "error" in result:
        print(f"❌ {result['error']}", file=sys.stderr)
        sys.exit(1)

    out_path = "test_prosody.mp3"
    with open(out_path, "wb") as f:
        f.write(result["data"])  # type: ignore[arg-type]
    print(f"✅ บันทึกไฟล์ {out_path} ({len(result['data'])} bytes)")  # type: ignore[arg-type]

    # แสดง segments
    parts = split_mp3_with_silence_markers(result["data"])  # type: ignore[arg-type]
    print(f"Segments: {len(parts)}")
    for kind, data in parts:
        if kind == "audio":
            print(f"  - audio: {len(data)} bytes")
        else:
            print(f"  - silence: {data:.2f}s")
