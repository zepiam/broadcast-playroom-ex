"""now_playing.py — อ่านข้อมูลเพลงที่กำลังเล่นจาก Windows System Media

ใช้ winsdk (Windows Runtime) อ่าน GlobalSystemMediaTransportControlsSessionManager
รองรับ: Spotify, YouTube Music (browser), VLC, ฯลฯ — อะไรก็ตามที่ Windows รู้จัก

Callback:
  on_media_change(title, artist, album, thumbnail_path, position, duration, is_playing)
  - เรียกเมื่อเปลี่ยนเพลง (title/artist เปลี่ยน)
  - thumbnail_path = path ไฟล์ปกที่บันทึกแล้ว (หรือ "" ถ้าไม่มี)

  on_position_update(position, duration, is_playing)
  - เรียกทุก 3 วินาที (เพื่อ update progress bar)
"""
from __future__ import annotations

import asyncio
import os
import threading
import time

CACHE_DIR = os.path.join(os.path.expanduser("~"), ".tts-for-livestream", "np_cache")


class NowPlayingWatcher:
    """อ่านข้อมูลเพลงจาก Windows System Media ใน background thread"""

    POLL_INTERVAL = 3.0  # วินาที — poll position/duration

    def __init__(self, on_change=None, on_position=None):
        self.on_change = on_change
        self.on_position = on_position
        self._stop_event = threading.Event()
        self._thread = None
        self._last_title = ""
        self._last_artist = ""
        self._running = False
        self._none_count = 0
        self._poll_interval = 3.0
        self._source_filter = "auto"  # "auto" | "spotify" | "ytmusic" | "browser" | "any"

    def set_source_filter(self, source):
        """กำหนดแหล่งเพลงที่จะจับ"""
        self._source_filter = source or "auto"

    def start(self):
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_loop, name="NowPlaying", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        self._running = False

    def set_poll_interval(self, seconds):
        """ปรับ poll interval แบบ dynamic (1.0 = precise, 3.0 = economy)"""
        self._poll_interval = max(0.5, float(seconds))

    def _poll_loop(self):
        """Background loop — poll Windows Media ทุก POLL_INTERVAL วินาที"""
        try:
            from winsdk.windows.media.control import (
                GlobalSystemMediaTransportControlsSessionManager as Manager,
            )
        except ImportError:
            return  # winsdk ไม่ได้ติดตั้ง (non-Windows หรือ Lite ที่ไม่มี)

        while not self._stop_event.is_set():
            try:
                # ★ ใช้ event loop เดียวตลอด (สร้างใหม่ทุกครั้งทำให้ Windows API cache ไม่ refresh)
                if not hasattr(self, '_loop') or self._loop.is_closed():
                    self._loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(self._loop)
                self._loop.run_until_complete(self._poll_once(Manager))
            except Exception:
                pass
            self._stop_event.wait(self._poll_interval)

    # ★ source matching rules — keyword ใน source_app_user_model_id
    SOURCE_KEYWORDS = {
        "spotify":    ["spotify"],
        "ytmusic":    ["youtube.music", "ytmdesktop", "th-ch.youtube"],
        "browser":    ["chrome", "firefox", "edge", "msedge", "opera", "brave"],
    }

    def _match_source(self, source_id, filter_type):
        """เช็คว่า session ตรงกับ filter ที่เลือกไหม"""
        if filter_type == "auto" or filter_type == "any":
            return True
        sid = (source_id or "").lower()
        keywords = self.SOURCE_KEYWORDS.get(filter_type, [])
        return any(kw in sid for kw in keywords)

    def _find_session(self, manager):
        """หา session ที่ตรงกับ source filter + กำลังเล่นอยู่"""
        filt = self._source_filter

        # ถ้า auto → ใช้ current session (หรือหา playing session)
        if filt == "auto":
            session = manager.get_current_session()
            if session:
                pb = session.get_playback_info()
                if pb.playback_status == 4:
                    return session
            # หา session อื่นที่ playing
            sessions = manager.get_sessions()
            for i in range(sessions.size):
                s = sessions.get_at(i)
                pb = s.get_playback_info()
                if pb.playback_status == 4:
                    return s
            return session  # คืน current แม้ไม่ playing

        # ★ specific source → หา session ที่ตรง keyword + playing ก่อน
        sessions = manager.get_sessions()
        # รอบ 1: หา matching + playing
        for i in range(sessions.size):
            s = sessions.get_at(i)
            if self._match_source(s.source_app_user_model_id, filt):
                pb = s.get_playback_info()
                if pb.playback_status == 4:
                    return s
        # รอบ 2: หา matching (ไม่สน playing)
        for i in range(sessions.size):
            s = sessions.get_at(i)
            if self._match_source(s.source_app_user_model_id, filt):
                return s
        return None

    async def _poll_once(self, Manager):
        """อ่านข้อมูลครั้งเดียว"""
        manager = await Manager.request_async()
        session = self._find_session(manager)
        if session is None:
            # ★ session อาจเป็น None ชั่วคราว (ตอนเปลี่ยนเพลง/minimize/switch app)
            # รอ 3 ครั้งก่อนบอกว่าไม่มีเพลงจริง ๆ (กัน flicker "ไม่มีเพลง" → กลับมาแสดง)
            self._none_count = getattr(self, '_none_count', 0) + 1
            if self._none_count >= 3 and self._last_title:
                self._last_title = ""
                self._last_artist = ""
                if self.on_change:
                    self.on_change("", "", "", "", 0, 0, False)
            return

        # มี session → reset counter
        self._none_count = 0

        # อ่าน media properties (title, artist, album, thumbnail)
        info = await session.try_get_media_properties_async()
        title = info.title or ""
        artist = info.artist or ""
        album = info.album_title or ""

        # ★ ถ้า title ว่าง (แอปส่งข้อมูลไม่ครบ) → ใช้ข้อมูลเดิม ไม่ส่ง empty
        if not title:
            if self._last_title and self.on_position:
                self.on_position(0, 0, False)
            return

        # playback status
        pb = session.get_playback_info()
        # 1 = closed, 2 = changing, 3 = stopped, 4 = playing, 5 = paused
        is_playing = (pb.playback_status == 4) if pb else False

        # timeline — Windows API อัปเดต timeline ล่าช้า → interpolate จากเวลาจริง
        tl = session.get_timeline_properties()
        api_pos = tl.position.total_seconds() if tl else 0
        duration = tl.end_time.total_seconds() if tl else 0
        # ★ interpolation: ถ้ากำลังเล่น → ใช้เวลาจริงคำนวณ position (API ไม่ละเอียดพอ)
        # แต่ถ้าเพลงเปลี่ยน → reset interpolation + ใช้ api_pos ตรง ๆ
        song_changed = (title != self._last_title or artist != self._last_artist)
        if song_changed:
            # ★ เพลงใหม่ → reset interpolation ทั้งหมด
            position = api_pos
            self._last_pos = api_pos
            self._last_pos_time = time.monotonic() if is_playing else None
        elif is_playing:
            if hasattr(self, '_last_pos') and hasattr(self, '_last_pos_time') and self._last_pos_time:
                elapsed = time.monotonic() - self._last_pos_time
                expected = self._last_pos + elapsed
                # ถ้า API ส่งค่าถอยหลังหรือเดิม → ใช้ค่าคำนวณ (API cache เก่า)
                if api_pos < expected - 0.5 or api_pos < self._last_pos:
                    position = expected
                else:
                    position = api_pos
                    self._last_pos = position
                    self._last_pos_time = time.monotonic()
            else:
                position = api_pos
                self._last_pos = position
                self._last_pos_time = time.monotonic()
        else:
            position = api_pos
            self._last_pos = position
            self._last_pos_time = None

        # ตรวจการเปลี่ยนเพลง (title หรือ artist เปลี่ยน)
        if title != self._last_title or artist != self._last_artist:
            self._last_title = title
            self._last_artist = artist

            # บันทึก thumbnail (ถ้ามี)
            thumb_path = ""
            if info.thumbnail:
                try:
                    thumb_path = await self._save_thumbnail(info.thumbnail, title)
                except Exception:
                    pass

            if self.on_change:
                self.on_change(title, artist, album, thumb_path, position, duration, is_playing)
        else:
            # ไม่เปลี่ยนเพลง → update position/duration เท่านั้น
            if self.on_position:
                self.on_position(position, duration, is_playing)

    async def _save_thumbnail(self, thumbnail_ref, title) -> str:
        """บันทึก thumbnail เป็นไฟล์ → คืน path"""
        try:
            import hashlib
            os.makedirs(CACHE_DIR, exist_ok=True)
            fname = hashlib.md5(title.encode('utf-8')).hexdigest()[:12] + ".jpg"
            fpath = os.path.join(CACHE_DIR, fname)

            if os.path.exists(fpath) and os.path.getsize(fpath) > 0:
                return fpath

            # เปิด IRandomAccessStreamWithContentType จาก reference
            stream = await thumbnail_ref.open_read_async()
            # อ่านทั้งหมดผ่าน DataReader
            from winsdk.windows.storage.streams import DataReader
            reader = DataReader(stream)
            await reader.load_async(stream.size)
            buf = bytearray(stream.size)
            reader.read_bytes(buf)
            reader.detach_buffer()
            with open(fpath, 'wb') as f:
                f.write(buf)
            return fpath
        except Exception as e:
            try:
                with open(os.path.join(CACHE_DIR, '_error.log'), 'a') as f:
                    f.write(f"{time.strftime('%H:%M:%S')} thumb: {e}\n")
            except Exception:
                pass
            return ""
