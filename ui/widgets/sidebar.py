"""sidebar.py — Left sidebar (platforms + voice panel)"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QScrollArea,
    QWidget, QComboBox, QSlider, QSizePolicy,
)
import ui.theme as theme  # ★ อ้าง theme.COLOR_X สดตอนสร้าง widget (ตามธีมที่เลือกไว้จริง)


class _ConstrainedScrollArea(QScrollArea):
    """QScrollArea ที่บังคับ widget ภายในให้หดตามความกว้าง viewport

    QScrollArea.setWidgetResizable(True) ใช้ไม่ได้ในทุกกรณี (เมื่อ sizeHint ของ widget
    ใหญ่กว่า viewport → widget ไม่ยอมหด) → เราบังคับ maximumWidth เอง
    """

    def resizeEvent(self, event):
        super().resizeEvent(event)
        try:
            vp_w = self.viewport().width()
            cw = self.widget()
            if cw is not None and vp_w > 0:
                cw.setMaximumWidth(vp_w)
                cw.updateGeometry()
        except Exception:
            pass


class PlatformCard(QFrame):
    """Card สำหรับแพลตฟอร์มเดียว (logo + name + connect/disconnect + mute + volume)"""

    connect_requested = Signal(str)  # platform key
    disconnect_requested = Signal(str)
    mute_toggled = Signal(str, bool)  # platform, muted
    volume_changed = Signal(str, int)  # platform, volume
    edit_stream_requested = Signal(str)  # ★ platform key — เปิดหน้า edit stream info
    refresh_stream_requested = Signal(str)  # ★ platform key — ดึง title ใหม่ตามคำสั่ง (ไม่ auto)
    go_requested = Signal(str)  # ★ platform key — เปิดหน้าช่อง/ห้อง live ในเบราว์เซอร์

    def __init__(self, platform_key, label, icon="📺", parent=None):
        super().__init__(parent)
        self.platform_key = platform_key
        self.setObjectName("Card")
        self._connected = False
        self._muted = False
        self._stream_start_time = None  # ★ timestamp ที่ stream เริ่ม (สำหรับนับเวลา)
        self._build_ui(label, icon)
        # ★ ปรับขนาดอัตโนมัติตามเนื้อหา
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        # ★ timer สำหรับอัปเดตเวลาสตรีมทุก 1 นาที
        from PySide6.QtCore import QTimer
        self._uptime_timer = QTimer(self)
        self._uptime_timer.setInterval(60000)  # ทุก 1 นาที
        self._uptime_timer.timeout.connect(self._update_uptime)

    def _build_ui(self, label, icon):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(4)

        # ★ Row 1: icon + name/status (เท่านั้น — ไม่มีปุ่ม เพื่อกินพื้นที่แนวนอนน้อยสุด)
        row1 = QHBoxLayout()
        row1.setSpacing(6)
        # ★ ไอคอนแพลตฟอร์มจริง (assets/*.png) — fallback emoji ถ้าไม่มีไฟล์
        try:
            from ui.platform_icons import get_platform_pixmap
            pix = get_platform_pixmap(self.platform_key, 20)
        except Exception:
            pix = QPixmap()
        icon_label = QLabel()
        icon_label.setFixedSize(20, 20)
        if not pix.isNull():
            icon_label.setPixmap(pix)
        else:
            icon_label.setText(icon)
            icon_label.setStyleSheet("font-size: 16px;")
        row1.addWidget(icon_label)

        info = QVBoxLayout()
        info.setSpacing(0)
        self.name_label = QLabel(label)
        self.name_label.setStyleSheet("font-weight: 600; color: #e5e7eb; font-size: 14px;")
        self.name_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        # ★ ปุ่ม GO (🚀 เปิดหน้าช่อง/ห้อง live ในเบราว์เซอร์ — แสดงเมื่อเชื่อมต่อแล้ว)
        from PySide6.QtWidgets import QToolButton
        self.go_btn = QToolButton()
        self.go_btn.setText("🚀")
        self.go_btn.setToolTip("เปิดหน้าช่อง/ห้อง live ของแพลตฟอร์มนี้ในเบราว์เซอร์")
        self.go_btn.setStyleSheet(
            "QToolButton { background: transparent; border: none; font-size: 12px; padding: 0 2px; }"
            "QToolButton:hover { background: rgba(34,197,94,0.2); border-radius: 3px; }"
        )
        self.go_btn.setCursor(Qt.PointingHandCursor)
        self.go_btn.setVisible(False)
        self.go_btn.clicked.connect(lambda: self.go_requested.emit(self.platform_key))
        name_row = QHBoxLayout()
        name_row.setContentsMargins(0, 0, 0, 0)
        name_row.setSpacing(4)
        name_row.addWidget(self.name_label)
        name_row.addWidget(self.go_btn)
        self.status_label = QLabel("ยังไม่เชื่อมต่อ")
        self.status_label.setStyleSheet("font-size: 12px; color: #6b7280;")
        # ★ stream title (แสดงเมื่อเชื่อมต่อสำเร็จ — ดึงจาก live stream จริง)
        self.stream_title_label = QLabel("")
        self.stream_title_label.setStyleSheet("font-size: 11px; color: #9ca3af; font-style: italic;")
        self.stream_title_label.setWordWrap(False)
        self.stream_title_label.setVisible(False)
        info.addLayout(name_row)
        info.addWidget(self.status_label)
        # ★ title + refresh + Edit อยู่ในแถวเดียวกัน — title ชิดซ้าย, refresh + Edit ชิดขวาของการ์ด
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(4)
        title_row.addWidget(self.stream_title_label, 1)
        # ★ ปุ่ม refresh title (กดเพื่อดึง title ใหม่ — ไม่ auto refresh)
        from PySide6.QtWidgets import QPushButton, QToolButton
        self.refresh_btn = QToolButton()
        self.refresh_btn.setText("🔄")
        self.refresh_btn.setToolTip("ดึง Title ใหม่จากแพลตฟอร์ม")
        self.refresh_btn.setStyleSheet("""
            QToolButton { background: transparent; border: none; font-size: 11px; padding: 0 2px; }
            QToolButton:hover { background: rgba(124,58,237,0.15); border-radius: 3px; }
        """)
        self.refresh_btn.setCursor(Qt.PointingHandCursor)
        self.refresh_btn.setVisible(False)
        self.refresh_btn.clicked.connect(lambda: self.refresh_stream_requested.emit(self.platform_key))
        title_row.addWidget(self.refresh_btn)
        self.edit_link_label = QLabel('<span style="color:#7c3aed; text-decoration: underline;">Edit</span>')
        self.edit_link_label.setTextFormat(Qt.RichText)
        self.edit_link_label.setStyleSheet("font-size: 11px; background: transparent;")
        self.edit_link_label.setCursor(Qt.PointingHandCursor)
        self.edit_link_label.setVisible(False)
        self.edit_link_label.mousePressEvent = lambda e: self.edit_stream_requested.emit(self.platform_key)
        title_row.addWidget(self.edit_link_label)
        info.addLayout(title_row)
        row1.addLayout(info, 1)
        # ★ viewer count (ฝั่งขวา — แสดงเมื่อเชื่อมต่อแล้วได้รับยอดจริง)
        self.viewer_label = QLabel("")
        self.viewer_label.setStyleSheet("font-size: 12px; color: #9ca3af; font-weight: 600; background: transparent; border: none;")
        self.viewer_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.viewer_label.setVisible(False)  # ★ ซ่อนตอนเริ่ม (ยังไม่มียอด)
        row1.addWidget(self.viewer_label)
        layout.addLayout(row1)

        # ★ Row 2: [connect/disconnect (stretch)] [mute button]
        # ปุ่มเชื่อมต่อขยายเต็มความกว้างที่เหลือ → mute มีที่พอแสดงเต็ม
        row2 = QHBoxLayout()
        row2.setSpacing(6)
        self.btn = QPushButton("เชื่อมต่อ")
        self.btn.setFixedHeight(22)
        self.btn.setCursor(Qt.PointingHandCursor)
        self.btn.setStyleSheet("font-size: 11px; padding: 1px 8px;")
        self.btn.clicked.connect(self._on_btn)
        row2.addWidget(self.btn, 1)

        self.mute_btn = QPushButton("🔊")
        self.mute_btn.setObjectName("IconButton")
        # ★ ขยาย mute ให้ใหญ่พอแสดง emoji เต็ม + override padding จาก QSS
        #    (IconButton QSS มี padding 6px 10px → บีบ emoji ใน button เล็ก)
        self.mute_btn.setFixedSize(34, 28)
        self.mute_btn.setStyleSheet("padding: 2px; font-size: 16px;")
        self.mute_btn.setCursor(Qt.PointingHandCursor)
        self.mute_btn.setToolTip("ปิดเสียง TTS ของแพลตฟอร์มนี้")
        self.mute_btn.clicked.connect(self._on_mute)
        row2.addWidget(self.mute_btn)
        layout.addLayout(row2)

        # ★ Row 3: volume slider (ขยายเต็มความกว้าง + มีระยะห่างจากปุ่มด้านบน)
        layout.addSpacing(2)
        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(100)
        self.vol_slider.setFixedHeight(16)
        self.vol_slider.valueChanged.connect(lambda v: self.volume_changed.emit(self.platform_key, v))
        layout.addWidget(self.vol_slider)


    def _on_btn(self):
        if self.btn.text() in ("เชื่อมต่อ", "ลองใหม่"):
            self.connect_requested.emit(self.platform_key)
        else:
            self.disconnect_requested.emit(self.platform_key)

    def _on_mute(self):
        # ★ ปุ่มควรถูก disable ระหว่าง master mute อยู่แล้ว (set_master_muted) —
        #   guard นี้กันไว้เผื่อ event หลุดมาได้ทางอื่น
        if getattr(self, '_master_muted', False):
            return
        self._muted = not getattr(self, '_muted', False)
        self.mute_btn.setText("🔇" if self._muted else "🔊")
        self.mute_toggled.emit(self.platform_key, self._muted)

    def set_muted(self, muted: bool):
        """★ ตั้งสถานะ mute เฉพาะแพลตฟอร์มนี้จากภายนอก (เช่น restore จาก settings ตอน
        rebuild การ์ด) — ไม่ emit mute_toggled (ค่าจาก settings อยู่แล้ว ไม่ต้อง save ซ้ำ)

        เดิมใช้ mute_btn.setChecked() ซึ่งไม่มีผล เพราะปุ่มนี้ไม่ได้ setCheckable(True)
        → ค่า mute ที่เคยตั้งไว้ไม่เคย restore กลับมาจริงหลัง rebuild
        """
        self._muted = bool(muted)
        if not getattr(self, '_master_muted', False):
            self.mute_btn.setText("🔇" if self._muted else "🔊")

    def set_master_muted(self, master_muted: bool):
        """★ Sync กับปุ่ม master TTS mute ("ปิดอ่าน" บน topbar)

        - master mute เปิด → บังคับไอคอนเป็น 🔇 + ปิดปุ่ม (แก้กลับได้ทาง
          "ปิดอ่าน" → "อ่านแชท" เท่านั้น ไม่ใช่กดปุ่มลำโพงรายแพลตฟอร์ม)
        - master mute ปิด → คืนปุ่ม/ไอคอนตามสถานะ mute เฉพาะแพลตฟอร์มของตัวเอง (self._muted)
        """
        self._master_muted = master_muted
        if master_muted:
            self.mute_btn.setText("🔇")
            self.mute_btn.setEnabled(False)
            self.mute_btn.setToolTip(
                "ปิดเสียง TTS ทั้งหมดอยู่ (ปุ่ม \"ปิดอ่าน\" บนแถบด้านบน) — "
                "เปิด \"อ่านแชท\" กลับก่อน ถึงจะปรับทีละแพลตฟอร์มได้"
            )
        else:
            self.mute_btn.setEnabled(True)
            self.mute_btn.setText("🔇" if getattr(self, '_muted', False) else "🔊")
            self.mute_btn.setToolTip("ปิดเสียง TTS ของแพลตฟอร์มนี้")

    def set_connecting(self):
        """แสดงสถานะกำลังเชื่อมต่อ"""
        self.btn.setText("...")
        self.btn.setEnabled(False)
        self.status_label.setText("กำลังเชื่อมต่อ...")
        self.status_label.setStyleSheet("font-size: 12px; color: #f59e0b;")

    def set_connected(self, connected):
        """อัปเดตสถานะ"""
        self._connected = connected
        self.btn.setEnabled(True)
        if connected:
            self.btn.setText("หยุดเชื่อมต่อ")
            self.btn.setObjectName("Danger")
            self.status_label.setText("✅ เชื่อมต่อแล้ว")
            self.status_label.setStyleSheet("font-size: 12px; color: #10b981;")
            self.viewer_label.setText("👥 0")
            self.viewer_label.setVisible(True)
            self.go_btn.setVisible(True)
        else:
            self.btn.setText("เชื่อมต่อ")
            self.btn.setObjectName("")
            self.status_label.setText("ยังไม่เชื่อมต่อ")
            # (repolish อยู่ท้ายฟังก์ชัน — ครอบทั้งสอง branch)
            self.status_label.setStyleSheet("font-size: 12px; color: #6b7280;")
            self.viewer_label.setVisible(False)
            self.viewer_label.setText("")
            self.go_btn.setVisible(False)
            self.stream_title_label.setVisible(False)
            self.stream_title_label.setText("")
            self.refresh_btn.setVisible(False)
            self.edit_link_label.setVisible(False)
            self._uptime_timer.stop()
            self._stream_start_time = None
        # ★ setObjectName เปลี่ยนตัว selector ของ QSS (#Danger) แต่ Qt ไม่ re-evaluate
        #   สไตล์ให้อัตโนมัติ — ต้อง unpolish/polish บังคับ ไม่งั้นขอบปุ่มค้างสีเดิม
        #   (บางทีถึงหลุดเอง เพราะ event อื่น เช่น hover/resize ไปกระตุ้น repolish ให้บังเอิญ)
        self.btn.style().unpolish(self.btn)
        self.btn.style().polish(self.btn)

    def set_stream_title(self, title: str):
        """★ แสดง title ของ live stream ในการ์ด + refresh/Edit ปุ่ม (ชิดขวา)

        title ชิดซ้าย, 🔄 refresh (ทุกแพลตฟอร์ม) + Edit (Twitch only) ชิดขวาของการ์ด
        """
        if title:
            short = title[:50] + "…" if len(title) > 50 else title
            self.stream_title_label.setTextFormat(Qt.PlainText)
            self.stream_title_label.setText(f"📺 {short}")
            self.stream_title_label.setVisible(True)
            # ★ refresh ปุ่ม — แสดงทุกแพลตฟอร์ม (กดดึง title ใหม่)
            self.refresh_btn.setVisible(True)
            # ★ Edit — Twitch (เว็บ) + KICK (API ในโปรแกรม) + YouTube (Live Dashboard)
            if self.platform_key in ("twitch", "kick", "youtube"):
                self.edit_link_label.setVisible(True)
            else:
                self.edit_link_label.setVisible(False)
        else:
            self.stream_title_label.setVisible(False)
            self.stream_title_label.setText("")
            self.refresh_btn.setVisible(False)
            self.edit_link_label.setVisible(False)

    def set_stream_start_time(self, start_time):
        """★ ตั้งเวลาเริ่มสตรีม → เริ่มนับ uptime

        Args:
            start_time: datetime object หรือ ISO string หรือ None (ใช้เวลาปัจจุบัน)
        """
        from datetime import datetime, timezone
        if start_time is None:
            self._stream_start_time = datetime.now(timezone.utc)
        elif isinstance(start_time, str):
            try:
                self._stream_start_time = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            except Exception:
                self._stream_start_time = datetime.now(timezone.utc)
        elif hasattr(start_time, 'timestamp'):
            self._stream_start_time = start_time
        else:
            self._stream_start_time = datetime.now(timezone.utc)
        self._update_uptime()
        self._uptime_timer.start()

    def _update_uptime(self):
        """★ อัปเดตเวลาสตรีม (แสดงใน status_label ถ้าเชื่อมต่อแล้ว)"""
        if not self._connected or not self._stream_start_time:
            return
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        diff = now - self._stream_start_time
        hours = int(diff.total_seconds() // 3600)
        minutes = int((diff.total_seconds() % 3600) // 60)
        if hours > 0:
            uptime = f"⏱ {hours}ชม.{minutes:02d}น."
        else:
            uptime = f"⏱ {minutes}นาที"
        # ★ แสดง uptime ต่อจาก status (เช่น "✅ เชื่อมต่อแล้ว · ⏱ 15นาที")
        self.status_label.setText(f"✅ เชื่อมต่อแล้ว · {uptime}")
        # refresh style
        self.btn.style().unpolish(self.btn)
        self.btn.style().polish(self.btn)

    def set_viewer_count(self, count, hidden=False):
        """★ แสดงยอดคนดูในการ์ด (เรียกจาก app._update_viewer_ui)

        - ไม่ได้เชื่อมต่อ → ซ่อน
        - hidden=True → แสดง "👥 --"
        - เชื่อมต่อแล้ว → แสดง "👥 {count}" เสมอ (รวม 0)
        """
        if not self._connected:
            self.viewer_label.setVisible(False)
            self.viewer_label.setText("")
            return
        if hidden:
            self.viewer_label.setText("👥 --")
            self.viewer_label.setVisible(True)
            return
        self.viewer_label.setText(f"👥 {count:,}")
        self.viewer_label.setVisible(True)


class Sidebar(QFrame):
    """Left sidebar — platforms list + voice panel"""

    toggle_requested = Signal()  # ซ่อน/แสดง sidebar

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setMinimumWidth(240)
        self.setMaximumWidth(340)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ★ Scrollable content (ใช้ _ConstrainedScrollArea ที่บังคับ container หดตาม viewport)
        self.scroll = _ConstrainedScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        container.setMinimumWidth(0)
        clayout = QVBoxLayout(container)
        clayout.setContentsMargins(8, 8, 8, 8)
        clayout.setSpacing(6)

        # ★ Platforms header (collapsible)
        ph = QHBoxLayout()
        ph.setContentsMargins(0, 0, 0, 0)
        ph.setSpacing(4)
        # ★ collapse toggle button
        self.platform_toggle = QPushButton("▼")
        self.platform_toggle.setObjectName("IconButton")
        self.platform_toggle.setFixedSize(20, 20)
        self.platform_toggle.setCursor(Qt.PointingHandCursor)
        self.platform_toggle.setStyleSheet("font-size: 12px; padding: 0px; margin: 0px;")
        self.platform_toggle.setToolTip("หด/ขยาย")
        ph.addWidget(self.platform_toggle)
        header = QLabel("🔌 แพลตฟอร์ม")
        header.setObjectName("Heading")
        header.setStyleSheet("font-size: 16px; font-weight: 700; color: #f59e0b;")
        ph.addWidget(header)
        ph.addStretch()
        # ★ connected count
        self.platform_count = QLabel("0/0")
        self.platform_count.setStyleSheet("color: #10b981; font-size: 12px; font-weight: 600;")
        ph.addWidget(self.platform_count)
        # ★ Settings gear
        self.gear_btn = QPushButton("⚙")
        self.gear_btn.setObjectName("IconButton")
        self.gear_btn.setFixedSize(24, 24)
        self.gear_btn.setCursor(Qt.PointingHandCursor)
        self.gear_btn.setToolTip("ตั้งค่าแพลตฟอร์ม")
        self.gear_btn.setStyleSheet("font-size: 16px; padding: 0px; margin: 0px;")
        ph.addWidget(self.gear_btn)
        clayout.addLayout(ph)

        # ★ Platform container (collapsible)
        self.platforms_container = QVBoxLayout()
        self.platforms_container.setSpacing(6)
        clayout.addLayout(self.platforms_container)

        # ★ Separator
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background-color: {theme.COLOR_BORDER};")
        clayout.addWidget(sep)

        # ★ Voice header — เหลือแค่หัวข้อ (สถานะย้ายไปใต้ RVC combo แล้ว)
        voice_header = QLabel("🎤 เสียง")
        voice_header.setObjectName("Heading")
        voice_header.setStyleSheet("font-size: 16px; font-weight: 700; color: #f59e0b;")
        clayout.addWidget(voice_header)

        # ════════════════════════════════════════════════════════════════
        # ★ Voice panel ใหม่ — แยก 3 ส่วน: engine toggle / base voice / RVC
        # ════════════════════════════════════════════════════════════════

        # ─── (1) Engine toggle: Azure / Omni (text labels คลิกได้) ───
        self.engine_toggle_container = QWidget()
        et_layout = QVBoxLayout(self.engine_toggle_container)
        et_layout.setContentsMargins(0, 2, 0, 2)
        et_layout.setSpacing(2)
        et_title = QLabel("เครื่องมืออ่าน")
        # ★ ฉากหลังยาวเต็มซ้าย-ขวา (เหมือน zebra row) + padding บนล่าง
        et_title.setStyleSheet(
            "color: #d1d5db; font-size: 11px; font-weight: 600;"
            "background-color: rgba(255, 255, 255, 0.04);"
            "padding: 4px 8px; border-radius: 4px;"
        )
        et_title.setAlignment(Qt.AlignCenter)
        et_layout.addWidget(et_title)
        et_row = QHBoxLayout()
        et_row.setContentsMargins(0, 0, 0, 0)
        et_row.setSpacing(0)
        et_row.addStretch()  # ★ center: stretch ทั้ง 2 ข้าง
        self.engine_btn_azure = self._make_text_toggle("Azure")
        self.engine_btn_azure.setToolTip("Microsoft Azure (edge-tts) — เสียงอ่านออนไลน์")
        et_row.addWidget(self.engine_btn_azure)
        sep = QLabel("|")
        sep.setStyleSheet("color: #4b5563; font-size: 13px; padding: 0 6px;")
        et_row.addWidget(sep)
        self.engine_btn_omni = self._make_text_toggle("Omni")
        self.engine_btn_omni.setToolTip("OmniVoice — เสียง AI ออฟไลน์ (ต้องโหลดโมเดล)")
        et_row.addWidget(self.engine_btn_omni)
        et_row.addStretch()
        et_layout.addLayout(et_row)
        clayout.addWidget(self.engine_toggle_container)

        # ─── (2) Base voice: หญิง/ชาย (text labels คลิกได้) ───
        self.base_voice_container = QWidget()
        bv_layout = QVBoxLayout(self.base_voice_container)
        bv_layout.setContentsMargins(0, 2, 0, 2)
        bv_layout.setSpacing(2)
        bv_title = QLabel("เสียงพื้นฐาน")
        bv_title.setStyleSheet(
            "color: #d1d5db; font-size: 11px; font-weight: 600;"
            "background-color: rgba(255, 255, 255, 0.04);"
            "padding: 4px 8px; border-radius: 4px;"
        )
        bv_title.setAlignment(Qt.AlignCenter)
        bv_layout.addWidget(bv_title)
        bv_row = QHBoxLayout()
        bv_row.setContentsMargins(0, 0, 0, 0)
        bv_row.setSpacing(0)
        bv_row.addStretch()  # ★ center
        self.voice_btn_female = self._make_text_toggle("หญิง")
        bv_row.addWidget(self.voice_btn_female)
        bv_sep = QLabel("|")
        bv_sep.setStyleSheet("color: #4b5563; font-size: 13px; padding: 0 6px;")
        bv_row.addWidget(bv_sep)
        self.voice_btn_male = self._make_text_toggle("ชาย")
        bv_row.addWidget(self.voice_btn_male)
        bv_row.addStretch()
        bv_layout.addLayout(bv_row)
        # ★ combo ซ่อนไว้ (เก็บ data ให้ app.py compatibility — ไม่แสดง)
        self.base_voice_combo = QComboBox()
        self.base_voice_combo.setVisible(False)
        bv_layout.addWidget(self.base_voice_combo)
        clayout.addWidget(self.base_voice_container)

        # ─── (3) RVC model selector (Full build เท่านั้น) ───
        self.rvc_container = QWidget()
        rvc_layout = QVBoxLayout(self.rvc_container)
        rvc_layout.setContentsMargins(0, 4, 0, 4)
        rvc_layout.setSpacing(2)
        rvc_title = QLabel("โมเดลเสียง RVC")
        rvc_title.setStyleSheet(
            "color: #d1d5db; font-size: 11px; font-weight: 600;"
            "background-color: rgba(255, 255, 255, 0.04);"
            "padding: 4px 8px; border-radius: 4px;"
        )
        rvc_layout.addWidget(rvc_title)
        # ★ combo + refresh อยู่บรรทัดเดียวกัน (combo stretch, refresh ชิดขวา)
        rvc_row = QHBoxLayout()
        rvc_row.setContentsMargins(0, 0, 0, 0)
        rvc_row.setSpacing(4)
        self.rvc_combo = QComboBox()
        self.rvc_combo.addItem("ไม่ใช้ RVC")
        self.rvc_combo.setFocusPolicy(Qt.StrongFocus)
        rvc_row.addWidget(self.rvc_combo, 1)  # ★ stretch
        self.voice_refresh_btn = QPushButton("🔄")
        self.voice_refresh_btn.setObjectName("IconButton")
        self.voice_refresh_btn.setFixedSize(28, 26)
        self.voice_refresh_btn.setCursor(Qt.PointingHandCursor)
        self.voice_refresh_btn.setStyleSheet("font-size: 14px; padding: 0px;")
        self.voice_refresh_btn.setToolTip("รีเฟรชโมเดลเสียง (สแกนโฟลเดอร์ใหม่)")
        rvc_row.addWidget(self.voice_refresh_btn)
        rvc_layout.addLayout(rvc_row)
        clayout.addWidget(self.rvc_container)

        # ★ สถานะเสียงปัจจุบัน (ย้ายมาจาก header — อยู่ใต้ RVC combo)
        #   อยู่นอก rvc_container เพื่อให้ Lite build (ไม่มี RVC) ก็แสดงได้
        self.rvc_status = QLabel("✅ Premwadee (Azure)")
        self.rvc_status.setStyleSheet("color: #10b981; font-size: 12px;")
        self.rvc_status.setAlignment(Qt.AlignCenter)
        self.rvc_status.setWordWrap(True)
        clayout.addWidget(self.rvc_status)

        # ★ Separator ก่อนปุ่ม action (ทดสอบ / ดาวน์โหลด / รีเฟรช)
        voice_sep = QFrame()
        voice_sep.setFixedHeight(1)
        voice_sep.setStyleSheet(f"background-color: {theme.COLOR_BORDER};")
        clayout.addWidget(voice_sep)

        # ★ Voice buttons — text labels: ทดสอบฟัง | ดาวโหลดโมเดลเสียง
        voice_btn_row = QHBoxLayout()
        voice_btn_row.setContentsMargins(0, 0, 0, 0)
        voice_btn_row.setSpacing(0)
        voice_btn_row.addStretch()
        self.voice_test_btn = self._make_text_toggle("ทดสอบฟัง")
        self.voice_test_btn.setToolTip("ทดสอบเสียง TTS")
        voice_btn_row.addWidget(self.voice_test_btn)
        self.voice_btn_sep = QLabel("|")
        self.voice_btn_sep.setStyleSheet("color: #4b5563; font-size: 13px; padding: 0 6px;")
        voice_btn_row.addWidget(self.voice_btn_sep)
        self.voice_download_btn = self._make_text_toggle("ดาวโหลดโมเดลเสียง")
        self.voice_download_btn.setToolTip("ดาวน์โหลดเสียง RVC")
        voice_btn_row.addWidget(self.voice_download_btn)
        voice_btn_row.addStretch()
        clayout.addLayout(voice_btn_row)

        # ★ Separator ก่อน sliders
        sep2 = QFrame()
        sep2.setFixedHeight(1)
        sep2.setStyleSheet(f"background-color: {theme.COLOR_BORDER};")
        clayout.addWidget(sep2)

        # ★ Volume slider (label + value on right)
        vol_row = QHBoxLayout()
        vol_row.setContentsMargins(0, 0, 0, 0)
        vol_label = QLabel("🔊 Volume")
        vol_label.setStyleSheet("color: #9ca3af; font-size: 12px;")
        vol_row.addWidget(vol_label)
        vol_row.addStretch()
        self.vol_val_label = QLabel("100")
        self.vol_val_label.setStyleSheet("color: #06b6d4; font-size: 12px;")
        vol_row.addWidget(self.vol_val_label)
        clayout.addLayout(vol_row)
        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(100)
        self.vol_slider.valueChanged.connect(lambda v: self.vol_val_label.setText(f"{v}"))
        clayout.addWidget(self.vol_slider)

        # ★ Rate slider (label + value on right)
        rate_row = QHBoxLayout()
        rate_row.setContentsMargins(0, 0, 0, 0)
        rate_label = QLabel("⚡ Speed")
        rate_label.setStyleSheet("color: #9ca3af; font-size: 12px;")
        rate_row.addWidget(rate_label)
        rate_row.addStretch()
        self.rate_val_label = QLabel("+0")
        self.rate_val_label.setStyleSheet("color: #06b6d4; font-size: 12px;")
        rate_row.addWidget(self.rate_val_label)
        clayout.addLayout(rate_row)
        self.rate_slider = QSlider(Qt.Horizontal)
        self.rate_slider.setRange(-50, 50)
        self.rate_slider.setValue(0)
        self.rate_slider.valueChanged.connect(lambda v: self.rate_val_label.setText(f"{v:+d}"))
        clayout.addWidget(self.rate_slider)

        # ★ RVC controls (Pitch เท่านั้น — f0method ใช้ rmvpe default)
        self.rvc_controls = QWidget()
        rvc_layout = QVBoxLayout(self.rvc_controls)
        rvc_layout.setContentsMargins(0, 0, 0, 0)
        rvc_layout.setSpacing(2)
        # pitch slider
        pitch_label_row = QHBoxLayout()
        pitch_label = QLabel("Pitch (ระดับเสียง)")
        pitch_label.setStyleSheet("color: #9ca3af; font-size: 12px;")
        self.pitch_val_label = QLabel("+0")
        self.pitch_val_label.setStyleSheet("color: #06b6d4; font-size: 12px;")
        pitch_label_row.addWidget(pitch_label)
        pitch_label_row.addStretch()
        pitch_label_row.addWidget(self.pitch_val_label)
        rvc_layout.addLayout(pitch_label_row)
        self.pitch_slider = QSlider(Qt.Horizontal)
        self.pitch_slider.setRange(-24, 24)
        self.pitch_slider.setValue(0)
        self.pitch_slider.valueChanged.connect(lambda v: self.pitch_val_label.setText(f"{v:+d}"))
        rvc_layout.addWidget(self.pitch_slider)
        clayout.addWidget(self.rvc_controls)
        # ★ ซ่อน RVC controls ถ้าเป็น Lite (ไม่มี RVC)
        try:
            import rvc_engine
            self.rvc_controls.setVisible(True)
        except ImportError:
            self.rvc_controls.setVisible(False)

        clayout.addStretch()
        self.scroll.setWidget(container)
        layout.addWidget(self.scroll, 1)

    def add_platform(self, key, label, icon="📺"):
        """เพิ่ม platform card เข้า sidebar"""
        card = PlatformCard(key, label, icon, self)
        self.platforms_container.addWidget(card)
        return card

    def clear_platforms(self):
        """★ ลบ platform cards ทั้งหมด (เรียกก่อน rebuild)"""
        while self.platforms_container.count():
            item = self.platforms_container.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _make_text_toggle(self, text: str) -> QPushButton:
        """สร้าง text label ที่คลิกได้ (flat, no border) — ใช้แบบ Azure/Omni และ หญิง/ชาย

        ★ active = สีเขียว (#10b981), inactive = สีเทา (#9ca3af)
        ★ ใช้ QPushButton แบบ flat (ไม่ใช่ QLabel เพราะต้องคลิกได้ + cursor pointing)
        """
        btn = QPushButton(text)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFlat(True)
        btn.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        btn.setFocusPolicy(Qt.NoFocus)
        # ★ default style = inactive (เทา)
        btn.setStyleSheet(self._text_toggle_style(active=False))
        return btn

    @staticmethod
    def _text_toggle_style(active: bool) -> str:
        """style สำหรับ text toggle — active=เขียว, inactive=เทา, hover=เหลือง"""
        color = "#10b981" if active else "#9ca3af"
        weight = "700" if active else "500"
        return (
            f"QPushButton {{ color: {color}; font-size: 13px; font-weight: {weight}; "
            f"padding: 2px 4px; border: none; background: transparent; text-align: left; }}"
            f"QPushButton:hover {{ color: #fbbf24; }}"  # ★ เหลืองตอน hover (ทุกสถานะ)
        )

    def _set_text_toggle_active(self, btn: QPushButton, active: bool):
        """ตั้ง active/inactive style ให้ text toggle"""
        btn.setStyleSheet(self._text_toggle_style(active))

    def set_engine_active(self, engine: str):
        """highlight engine toggle ที่ active — engine = "edge" | "omnivoice" """
        is_edge = (engine == "edge")
        self._set_text_toggle_active(self.engine_btn_azure, is_edge)
        self._set_text_toggle_active(self.engine_btn_omni, not is_edge)

    def set_base_voice_active(self, voice: str):
        """highlight base voice toggle — voice = "female" | "male" | "premwadee" | "niwat"

        ★ premwadee = female, niwat = male (compat)
        """
        is_female = voice in ("female", "premwadee")
        self._set_text_toggle_active(self.voice_btn_female, is_female)
        self._set_text_toggle_active(self.voice_btn_male, not is_female)

    def toggle_platforms(self):
        """หด/ขยาย section แพลตฟอร์ม"""
        self._platforms_collapsed = not getattr(self, '_platforms_collapsed', False)
        collapsed = self._platforms_collapsed
        self.platform_toggle.setText("▶" if collapsed else "▼")
        # ★ toggle visibility ของทุก card
        for i in range(self.platforms_container.count()):
            item = self.platforms_container.itemAt(i)
            if item.widget():
                item.widget().setVisible(not collapsed)

    def update_platform_count(self, connected, total):
        """อัปเดตตัวเลขจำนวนแพลตฟอร์มที่เชื่อมต่ออยู่"""
        color = "#10b981" if connected > 0 else "#6b7280"
        self.platform_count.setText(f"{connected}/{total}")
        self.platform_count.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: 600;")
