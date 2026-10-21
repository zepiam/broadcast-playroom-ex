"""topbar.py — Top bar widget (new design with split buttons + TTS toggle)

Layout (ซ้าย → ขวา):
  [platform status dots] [stretch]
  [เปิด/ปิด อ่านแชท + volume slider]
  [Overlay ▼]
  [อ่านทุกภาษา/แปล ▼⚙]
  [Game Overlay ▼]
  [Overlay+ ▼]
  [⚙ Settings]
"""
from PySide6.QtCore import Qt, Signal, QVariantAnimation, QSize, QEasingCurve, QPointF
import math
from PySide6.QtWidgets import (
    QFrame, QLabel, QPushButton, QHBoxLayout, QWidget,
    QSlider, QWidgetAction, QDialog, QCheckBox, QVBoxLayout, QMenu,
)
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QPainterPath, QCursor, QRadialGradient, QBrush
import ui.theme as theme  # ★ อ้าง theme.COLOR_X สดตอนสร้าง widget (ตามธีมที่เลือกไว้จริง)
from ui.widgets.split_button import SplitButton


class NeonButton(QPushButton):
    """ปุ่มนีออนสไตล์ Motion Reference (Open Neon Sign)
    - ตัวอักษรและกรอบวาดเป็นหลอดนีออนดัด (Dual-stroke tube)
    - หลอดแกนในสีขาวสว่างจ้า (Core White Tube)
    - ขอบนอกและแสงเรืองรอง (Aura Glow) เปลี่ยนสีตามธีม
    - พื้นหลังโปร่งใส (Hollow Glass Look) สวยงามแบบป้ายนีออนแท้
    """
    def __init__(self, text: str = "NEW UPDATE", parent=None):
        super().__init__(text, parent)
        self.setFixedHeight(32)
        self.setCursor(Qt.PointingHandCursor)
        self.brightness = 1.0
        self.glow_alpha = 180
        self.blur_radius = 16
        self._neon_color = QColor(theme.COLOR_ACCENT)
        # พื้นหลังโปร่งใส ขอบและตัวอักษรจัดการผ่าน paintEvent
        self.setStyleSheet("QPushButton { background: transparent; border: none; }")

    def set_neon_state(self, brightness: float, glow_alpha: int, blur_radius: int):
        self.brightness = brightness
        self.glow_alpha = glow_alpha
        self.blur_radius = blur_radius
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        rect = self.rect().adjusted(2, 2, -2, -2)
        accent = getattr(theme, "COLOR_ACCENT", "#7c3aed")
        ac_color = QColor(accent)

        b = max(0.1, min(1.3, self.brightness))
        
        # สีหลอดนีออนภายนอก (Outer Neon Color)
        neon_outer = QColor(
            int(min(255, ac_color.red() * b)),
            int(min(255, ac_color.green() * b)),
            int(min(255, ac_color.blue() * b)),
            int(min(255, self.glow_alpha))
        )
        # สีแกนหลอดด้านใน (Core Tube - ขาวอมสีนีออนจางๆ)
        core_white = QColor(
            int(min(255, 230 + ac_color.red() * 0.1 * b)),
            int(min(255, 230 + ac_color.green() * 0.1 * b)),
            int(min(255, 230 + ac_color.blue() * 0.1 * b)),
            int(min(255, 220 * b))
        )

        # 1. วาดกรอบหลอดนีออนรอบนอก (Rounded Rect Tube)
        # ชั้นที่ 1: แสงออร่ารอบเส้นกรอบ (Thick Outer Glow)
        aura_pen = QPen(neon_outer, 3.5)
        aura_pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(aura_pen)
        painter.setBrush(QColor(ac_color.red(), ac_color.green(), ac_color.blue(), int(15 * b)))
        painter.drawRoundedRect(rect, 14, 14)

        # ชั้นที่ 2: แกนหลอดนีออนเส้นคม (Core Tube Line)
        core_pen = QPen(core_white, 1.5)
        core_pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(core_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect, 14, 14)

        # 2. วาดตัวอักษร Retro Pixel คมกริบ (Razor-Sharp Pure Pixel)
        font = QFont("genxBigPixel", 10)
        if not font.exactMatch():
            font = QFont("Fixedsys", 10)
        font.setPixelSize(12)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 1.0)
        painter.setFont(font)

        # วาดตัวหนังสือพิกเซลเพียวๆ สีขาวสว่างจ้า คมกริบ ไร้เงากวนสายตา
        painter.setPen(core_white)
        painter.drawText(rect, Qt.AlignCenter, self.text())


MENU_STYLE = """
    QMenu {
        background-color: #0f172a;
        color: #e2e8f0;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 4px;
        font-size: 13px;
    }
    QMenu::item {
        padding: 6px 14px;
        border-radius: 4px;
    }
    QMenu::item:selected {
        background-color: #1e293b;
        color: #38bdf8;
    }
    QMenu::item:disabled {
        color: #64748b;
    }
    QMenu::separator {
        height: 1px;
        background: #334155;
        margin: 4px 6px;
    }
"""


class RestoreButtonsDialog(QDialog):
    """ไดอะล็อกเลือกแสดงปุ่มบน Topbar ที่ถูกซ่อนอยู่"""
    def __init__(self, hidden_items: list[tuple[str, str]], parent=None):
        super().__init__(parent)
        self.setWindowTitle("แสดงปุ่มบนแถบด้านบน")
        self.setFixedWidth(360)
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        import os as _os
        _icon_path = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))), "assets", "check_white.png").replace("\\", "/")

        self.setStyleSheet(f"""
            QDialog {{
                background-color: #0b1120;
                border: 1px solid #1e293b;
                border-radius: 12px;
            }}
            QLabel {{
                color: #e2e8f0;
                font-size: 13px;
            }}
            QCheckBox {{
                color: #f1f5f9;
                font-size: 13.5px;
                font-weight: 500;
                spacing: 10px;
                padding: 6px 8px;
                border-radius: 6px;
            }}
            QCheckBox:hover {{
                background-color: #1e293b;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 1.5px solid #475569;
                background-color: #0b1120;
            }}
            QCheckBox::indicator:hover {{
                border-color: #a78bfa;
            }}
            QCheckBox::indicator:checked {{
                background-color: #7c3aed;
                border-color: #8b5cf6;
                image: url(\"{_icon_path}\");
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(14)

        title_lbl = QLabel("เลือกปุ่มที่ต้องการให้กลับมาแสดง:")
        title_lbl.setStyleSheet("font-size: 14px; font-weight: 700; color: #f8fafc;")
        layout.addWidget(title_lbl)

        hint_lbl = QLabel('ทำเครื่องหมายถูกที่ปุ่มที่ต้องการแสดง แล้วกด "แสดงปุ่มที่เลือก"')
        hint_lbl.setStyleSheet("font-size: 12px; color: #94a3b8;")
        hint_lbl.setWordWrap(True)
        layout.addWidget(hint_lbl)

        chk_container = QWidget(self)
        chk_layout = QVBoxLayout(chk_container)
        chk_layout.setContentsMargins(10, 8, 10, 8)
        chk_layout.setSpacing(4)
        chk_container.setStyleSheet("background-color: #131d31; border: 1px solid #1e293b; border-radius: 8px;")

        self._checkboxes = {}
        icon_map = {
            "game_overlay": "🎮 ",
            "overlay_plus": "🪟 ",
            "user_manager": "👤 ",
        }
        for key, name in hidden_items:
            prefix = icon_map.get(key, "")
            chk = QCheckBox(f"{prefix}{name}")
            chk.setChecked(False)  # ★ เริ่มต้นไม่ติ๊กข้อไหนเลยตามที่คุณต้องการ
            chk.setCursor(Qt.PointingHandCursor)
            chk.stateChanged.connect(self._on_check_changed)
            chk_layout.addWidget(chk)
            self._checkboxes[key] = chk

        layout.addWidget(chk_container)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("ยกเลิก")
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #94a3b8;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #334155;
                color: #f1f5f9;
            }
        """)
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_restore = QPushButton("แสดงปุ่มที่เลือก")
        self.btn_restore.setCursor(Qt.PointingHandCursor)
        self.btn_restore.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_restore)

        layout.addLayout(btn_layout)
        self._on_check_changed()

    def _on_check_changed(self):
        """ถ้าไม่มีการติ๊กเลือกเลย ให้ disable ปุ่ม 'แสดงปุ่มที่เลือก'"""
        has_checked = any(chk.isChecked() for chk in self._checkboxes.values())
        self.btn_restore.setEnabled(has_checked)
        if has_checked:
            self.btn_restore.setStyleSheet("""
                QPushButton {
                    background-color: #7c3aed;
                    color: #ffffff;
                    border: 1px solid #8b5cf6;
                    border-radius: 6px;
                    padding: 6px 16px;
                    font-size: 12px;
                    font-weight: 700;
                }
                QPushButton:hover {
                    background-color: #6d28d9;
                    border-color: #a78bfa;
                }
            """)
        else:
            self.btn_restore.setStyleSheet("""
                QPushButton {
                    background-color: #1e293b;
                    color: #475569;
                    border: 1px solid #334155;
                    border-radius: 6px;
                    padding: 6px 16px;
                    font-size: 12px;
                    font-weight: 700;
                }
            """)

    def get_selected_keys(self) -> list[str]:
        return [k for k, chk in self._checkboxes.items() if chk.isChecked()]


class CloverButton(QPushButton):
    """ปุ่ม 🍀 สนับสนุนการพัฒนาโปรแกรม
    - ไม่มีกรอบ วาง 🍀 ลงไปแบบไร้ขอบ (Flat & Transparent)
    - เวลา Hover จะมีอนิเมชั่น 'Aurora Glow' (แสงออโรร่าสีเขียวมรกต-ฟ้าไซแอน-ม่วงพาสเทลเรืองแสงนุ่มนวล)
    - เมื่อเลิก Hover แสงจะค่อยๆ จางหายไปและกลับสู่สถานะ 0% GPU idle
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(34, 32)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("สนับสนุนการพัฒนาโปรแกรม")
        self.setStyleSheet("QPushButton { background: transparent; border: none; padding: 0px; margin: 0px; }")

        # Animation states
        self._hover_progress = 0.0  # 0.0 (idle) -> 1.0 (hovered)
        self._phase = 0.0           # 0.0 -> 360.0 (aurora rotation angle)
        self._is_hovered = False

        # Fade in/out transition
        self._fade_anim = QVariantAnimation(self)
        self._fade_anim.setDuration(220)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._fade_anim.valueChanged.connect(self._on_fade_value)

        # Continuous gentle aurora rotation loop while hovered
        self._aurora_loop = QVariantAnimation(self)
        self._aurora_loop.setDuration(3600)
        self._aurora_loop.setStartValue(0.0)
        self._aurora_loop.setEndValue(360.0)
        self._aurora_loop.setLoopCount(-1)
        self._aurora_loop.valueChanged.connect(self._on_phase_value)

    def _on_fade_value(self, val):
        self._hover_progress = float(val)
        self.update()

    def _on_phase_value(self, val):
        self._phase = float(val)
        self.update()

    def enterEvent(self, event):
        self._is_hovered = True
        self._fade_anim.stop()
        self._fade_anim.setStartValue(self._hover_progress)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.start()
        if self._aurora_loop.state() != QVariantAnimation.Running:
            self._aurora_loop.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._is_hovered = False
        self._aurora_loop.stop()
        self._fade_anim.stop()
        self._fade_anim.setStartValue(self._hover_progress)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.start()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.TextAntialiasing)

        w = self.width()
        h = self.height()
        cx = w / 2.0
        cy = h / 2.0

        # ── 1. วาด Aurora Glow ด้านหลังเมื่อ hover ──
        if self._hover_progress > 0.01:
            hp = self._hover_progress
            painter.save()

            rad = math.radians(self._phase)
            shift_x = math.cos(rad) * 2.5 * hp
            shift_y = math.sin(rad) * 2.0 * hp
            glow_center = QPointF(cx + shift_x, cy + shift_y)

            # ชั้นที่ 1: Outer Ethereal Bloom (รัศมีกว้าง ละมุน)
            grad1 = QRadialGradient(glow_center, 22.0)
            # สีออโรร่า: เขียวมรกต (#10b981) ผสาน ฟ้าเทอร์ควอยซ์ (#06b6d4)
            grad1.setColorAt(0.0, QColor(16, 185, 129, int(150 * hp)))
            grad1.setColorAt(0.45, QColor(6, 182, 212, int(95 * hp)))
            grad1.setColorAt(0.75, QColor(139, 92, 246, int(45 * hp)))
            grad1.setColorAt(1.0, QColor(139, 92, 246, 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(grad1))
            painter.drawEllipse(glow_center, 22, 22)

            # ชั้นที่ 2: Core Aurora Shimmer (รัศมีแกนกลางสดสว่าง)
            grad2 = QRadialGradient(glow_center, 13.0)
            grad2.setColorAt(0.0, QColor(52, 211, 153, int(180 * hp)))
            grad2.setColorAt(0.6, QColor(16, 185, 129, int(110 * hp)))
            grad2.setColorAt(1.0, QColor(16, 185, 129, 0))
            painter.setBrush(QBrush(grad2))
            painter.drawEllipse(glow_center, 13, 13)

            painter.restore()

        # ── 2. วาดไอคอน 🍀 (พร้อมสเกลเล็กน้อย 1.0 -> 1.15 บน hover) ──
        painter.save()
        scale = 1.0 + (0.15 * self._hover_progress)
        painter.translate(cx, cy)
        painter.scale(scale, scale)
        painter.translate(-cx, -cy)

        font = QFont("Segoe UI Emoji", 15)
        if not font.exactMatch():
            font = QFont("Apple Color Emoji", 15)
        font.setPixelSize(18)
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(self.rect(), Qt.AlignCenter, "🍀")
        painter.restore()


class TopBar(QFrame):
    """Top bar — platform status + action buttons (new design)"""

    # ═══ Signals ═══
    supporters_clicked = Signal()                       # 🍀 สนับสนุนการพัฒนาโปรแกรม
    settings_clicked = Signal()                         # ⚙ Settings
    # TTS toggle
    tts_toggled = Signal(bool)                          # True = เปิดอ่าน, False = ปิด
    volume_changed = Signal(int)                        # 0-100
    # Composer (Canvas Overlay)
    composer_toggled = Signal()                         # เปิด/ปิด Composer
    copy_overlay_url = Signal()                         # คัดลอก Overlay URL
    # Translate
    translate_mode_changed = Signal(str)                # "off" | "multilang" | "translate"
    translate_settings = Signal()                       # ⚙ ตั้งค่าการแปล
    # Game Overlay
    game_overlay_toggled = Signal()                     # เปิด/ปิด Game Overlay
    game_overlay_edit = Signal()                        # ซ่อน/แสดงกรอบ
    game_overlay_settings = Signal()                    # ⚙ Game Overlay Settings
    # Overlay+
    overlay_plus_toggled = Signal()                     # เปิด/ปิด Overlay+ ทั้งหมด
    overlay_plus_edit = Signal()                        # Edit Mode
    overlay_plus_settings = Signal()                    # ⚙ ตั้งค่า Overlay+
    # Viewer Overlay (ใน Game Overlay dropdown)
    viewer_overlay_toggled = Signal()                   # เปิด/ปิด Viewer Overlay
    # User manager (เก็บไว้ — เปิดจาก menu อื่นหรือ settings)
    user_manager_clicked = Signal()
    # ★ Update notification
    update_clicked = Signal()
    # ★ Launch OBS (เปิดโปรแกรม OBS หรือ bring-to-front ถ้ารันอยู่แล้ว)
    obs_launch_clicked = Signal()
    # ★ Clip marker
    mark_clip_clicked = Signal()
    mark_clip_settings = Signal()
    mark_clip_open_file = Signal()
    mark_clip_open_location = Signal()
    mark_clip_clear_history = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TopBar")
        self.setMinimumHeight(48)
        self.setMaximumHeight(52)
        self._translate_mode = "off"  # "off" | "multilang" | "translate"
        self._tts_on = True
        self._settings = None
        self._hideable_buttons = {}
        self._hidden_button_keys = []
        self._build_ui()
        self._setup_hideable_buttons()
        theme.register_theme_listener(self._update_tts_button)   # ★ ปุ่มอ่านแชท/ปิดอ่านตั้งสีเอง → รีเฟรชสดตอนสลับธีม

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(6)

        # ═══ Left 0: 🍀 สนับสนุนการพัฒนาโปรแกรม (Aurora Glow on hover) ═══
        self.btn_clover = CloverButton(self)
        self.btn_clover.clicked.connect(self.supporters_clicked.emit)
        layout.addWidget(self.btn_clover)

        # ═══ Left 1: เปิด OBS (icon จาก obs64.exe) ═══
        #   ★ กด 1 ครั้ง → เปิด OBS (ถ้ายังไม่รัน) หรือ bring-to-front (ถ้ารันอยู่)
        self.btn_obs = QPushButton("  OBS")
        self.btn_obs.setObjectName("OBSButton")
        self.btn_obs.setFixedHeight(32)
        self.btn_obs.setCursor(Qt.PointingHandCursor)
        self.btn_obs.setToolTip("เปิดโปรแกรม OBS (หรือดึงหน้าต่าง OBS ที่ซ่อนไว้ขึ้นมาแสดง)")
        theme.styled(self.btn_obs, "QPushButton { background-color: #1e293b; color: #e2e8f0; border: 1px solid #334155; "
            "border-radius: 6px; padding: 4px 12px; font-size: 13px; font-weight: 600; }"
            "QPushButton:hover { background-color: #334155; border-color: #475569; }"
            "QPushButton:pressed { background-color: #0f172a; }")
        # ★ โหลด OBS icon จาก assets/obs_icon.png (extract จาก obs64.exe)
        import os as _os
        from PySide6.QtGui import QPixmap, QIcon
        _icon_path = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))), "assets", "obs_icon.png")
        # ★ PyInstaller bundled: assets/ อยู่ใน _internal/assets/
        try:
            import sys as _sys
            if getattr(_sys, 'frozen', False):
                _internal = _os.path.join(_os.path.dirname(_sys.executable), "_internal")
                if _os.path.isdir(_internal):
                    _icon_path = _os.path.join(_internal, "assets", "obs_icon.png")
        except Exception:
            pass
        if _os.path.exists(_icon_path):
            _obs_pix = QPixmap(_icon_path)
            if not _obs_pix.isNull():
                self.btn_obs.setIcon(QIcon(_obs_pix))
                self.btn_obs.setIconSize(QSize(20, 20))
        self.btn_obs.clicked.connect(self.obs_launch_clicked.emit)
        layout.addWidget(self.btn_obs)
        # ★ default state = ยังไม่เปิด
        self._obs_running = False

        layout.addStretch()

        # ═══ 1. เปิด/ปิด อ่านแชท (SplitButton — toggle + volume slider ใน dropdown) ═══
        self.btn_tts = SplitButton(
            "🔊 อ่านแชท", tooltip="เปิด/ปิดการอ่านแชทด้วย TTS",
            parent=self, on_click=self._on_tts_click,
        )
        # ★ volume slider widget สำหรับใส่ใน dropdown menu
        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(100)
        self.vol_slider.setFixedHeight(20)
        self.vol_slider.setMinimumWidth(140)
        self.vol_slider.setToolTip("ระดับเสียง TTS")
        self.vol_slider.valueChanged.connect(self.volume_changed.emit)
        # ★ สร้าง custom menu ที่มี slider widget action
        vol_action = QWidgetAction(self.btn_tts)
        vol_widget = QWidget()
        vol_layout = QHBoxLayout(vol_widget)
        vol_layout.setContentsMargins(12, 8, 12, 8)
        vol_layout.setSpacing(8)
        vol_lbl = QLabel("🔊")
        vol_layout.addWidget(vol_lbl)
        vol_layout.addWidget(self.vol_slider, 1)
        self.vol_value_lbl = QLabel("100%")
        theme.styled(self.vol_value_lbl, "color: #7c3aed; font-weight: 600; min-width: 36px;")
        self.vol_slider.valueChanged.connect(lambda v: self.vol_value_lbl.setText(f"{v}%"))
        vol_layout.addWidget(self.vol_value_lbl)
        vol_action.setDefaultWidget(vol_widget)
        # ★ เพิ่ม slider เป็น menu action แรก
        self.btn_tts._menu.addAction(vol_action)
        layout.addWidget(self.btn_tts)
        # initial state: TTS เปิดอยู่ (default)
        self._tts_on = True
        self._update_tts_button()

        # ═══ 2. แปลภาษา/อ่านทุกภาษา ▼ (toggle 2-state + settings) ═══
        self.btn_translate = SplitButton(
            "🌐 แปลภาษา", tooltip="คลิกเพื่อสลับโหมด — แปลภาษา ↔ อ่านทุกภาษา",
            parent=self,
        )
        self.btn_translate.set_menu_actions([
            ("⚙ ตั้งค่าภาษาที่รองรับ", self.translate_settings.emit),
        ])
        self.btn_translate.main_clicked.connect(self._toggle_translate)
        layout.addWidget(self.btn_translate)

        # ═══ 3. Overlay ▼ (Composer toggle + copy URL) ═══
        self.btn_composer = SplitButton(
            "🖥️ Overlay", tooltip="เปิด/ปิด Composer (Canvas Overlay)",
            parent=self,
        )
        self.btn_composer.set_menu_actions([
            ("📋 คัดลอก Overlay URL", self.copy_overlay_url.emit),
        ])
        self.btn_composer.main_clicked.connect(self.composer_toggled.emit)
        self.btn_composer.set_active(True)  # ★ สี accent ตลอดเวลา (composer เปิดอยู่เสมอ)
        layout.addWidget(self.btn_composer)

        # ═══ 4. Game Overlay ▼ (toggle + edit/settings) ═══
        self.btn_game = SplitButton(
            "🎮 Game Overlay", tooltip="เปิด/ปิด Game Overlay",
            parent=self,
        )
        self.btn_game.set_menu_actions([
            ("👥 Viewer Overlay", self.viewer_overlay_toggled.emit),
            ("👁 ซ่อน/แสดงกรอบ", self.game_overlay_edit.emit),
            ("—", None),
            ("⚙ ตั้งค่า Game Overlay", self.game_overlay_settings.emit),
        ])
        self.btn_game.main_clicked.connect(self.game_overlay_toggled.emit)
        layout.addWidget(self.btn_game)

        # ═══ 5. Overlay+ ▼ (toggle + edit/settings) ═══
        self.btn_overlay_plus = SplitButton(
            "🪟 Overlay+", tooltip="เปิด/ปิด Overlay+ (custom URL overlays)",
            parent=self,
        )
        self.btn_overlay_plus.set_menu_actions([
            ("👁 ซ่อน/แสดงกรอบ", self.overlay_plus_edit.emit),
            ("⚙ ตั้งค่า Overlay+", self.overlay_plus_settings.emit),
        ])
        self.btn_overlay_plus.main_clicked.connect(self.overlay_plus_toggled.emit)
        layout.addWidget(self.btn_overlay_plus)

        # ═══ 6. 👤 User Manager ═══
        self.btn_user_manager = QPushButton("👤")
        self.btn_user_manager.setObjectName("IconButton")
        self.btn_user_manager.setFixedSize(36, 32)
        self.btn_user_manager.setToolTip("จัดการผู้ชม — ดูรายชื่อ + สถิติ + แบน/เปลี่ยนชื่อ")
        self.btn_user_manager.setCursor(Qt.PointingHandCursor)
        self.btn_user_manager.setStyleSheet("font-size: 16px; padding: 0px;")
        self.btn_user_manager.clicked.connect(self.user_manager_clicked.emit)
        layout.addWidget(self.btn_user_manager)

        # ═══ 7. ⚙ Settings ═══
        self.btn_settings = QPushButton("⚙")
        self.btn_settings.setObjectName("IconButton")
        self.btn_settings.setFixedSize(36, 32)
        self.btn_settings.setToolTip("ตั้งค่า")
        self.btn_settings.setCursor(Qt.PointingHandCursor)
        self.btn_settings.setStyleSheet("font-size: 18px; padding: 0px;")
        self.btn_settings.clicked.connect(self.settings_clicked.emit)
        layout.addWidget(self.btn_settings)

        # ═══ 9. 🆕 New Update (ขวาสุด — ซ่อนไว้ แสดงเมื่อมีอัพเดท) ═══
        self.btn_update = NeonButton("NEW UPDATE")
        self.btn_update.setToolTip("มีเวอร์ชั่นใหม่ — คลิกเพื่ออัพเดท")

        # ★ glow effect (Pulse Aura รอบปุ่ม)
        from PySide6.QtWidgets import QGraphicsDropShadowEffect
        from PySide6.QtGui import QColor

        self._update_glow = QGraphicsDropShadowEffect()
        self._update_glow.setBlurRadius(20)
        self._update_glow.setColor(QColor(theme.COLOR_ACCENT))
        self._update_glow.setOffset(0, 0)
        self._update_glow.setEnabled(False)
        self.btn_update.setGraphicsEffect(self._update_glow)

        self._shimmer_label = None  # ไม่ใช้ label ซ้อนแข็งๆ แทนที่ด้วย Pulse Glow หรูๆ
        self.btn_update.clicked.connect(self.update_clicked.emit)
        self.btn_update.setVisible(False)
        layout.addWidget(self.btn_update)

        # ★ Motion Reference: Neon Flicker Cycle (2500ms)
        self._update_pulse = QVariantAnimation(self)
        self._update_pulse.setDuration(2500)
        self._update_pulse.setStartValue(0.0)
        self._update_pulse.setEndValue(1.0)
        self._update_pulse.setLoopCount(-1)
        self._update_pulse.valueChanged.connect(self._on_pulse_update)

    # ════════════════════════════════════════════════════════════
    # TTS toggle
    # ════════════════════════════════════════════════════════════
    def _on_tts_click(self):
        self._tts_on = not self._tts_on
        self._update_tts_button()
        self.tts_toggled.emit(self._tts_on)

    def _update_tts_button(self):
        """อัปเดตปุ่ม TTS — SplitButton ใช้ set_state + setText"""
        if self._tts_on:
            self.btn_tts.setText("🔊 อ่านแชท")
            self.btn_tts.set_state("on")  # green via custom — but we use "on" (accent)
            # ★ override to success color ตามธีมที่เลือกไว้ — สีตัวอักษรสลับเข้ม/อ่อนตามความสว่าง
            #   ของพื้นหลัง (QSS ไม่รองรับ text-shadow ให้ใส่เงาใต้ตัวอักษร — สลับสีให้ contrast
            #   พอแทน) ★ ธีมที่พื้นสว่างมาก (เช่น Nightwave Cyan) จะได้ตัวอักษรเข้มแทนขาวอ่านไม่ออก
            _on_success = theme.COLOR_ON_SUCCESS_TEXT
            _on_danger = theme.COLOR_ON_DANGER_TEXT
            self.btn_tts._main_btn.setStyleSheet(
                f"QPushButton {{ background-color: {theme.COLOR_SUCCESS}; color: {_on_success}; border: none; "
                "border-radius: 14px 0 0 14px; padding: 4px 6px 4px 14px; "
                "font-weight: 600; font-size: 12px; }"
                f"QPushButton:hover {{ background-color: {theme.COLOR_SUCCESS_HOVER}; }}"
            )
            self.btn_tts._arrow_btn.setStyleSheet(
                f"QPushButton {{ background-color: {theme.COLOR_SUCCESS}; color: {_on_success}; border: none; "
                "border-radius: 0 14px 14px 0; padding: 4px 2px; font-size: 11px; }"
                f"QPushButton:hover {{ background-color: {theme.COLOR_SUCCESS_HOVER}; }}"
            )
        else:
            self.btn_tts.setText("🔇 ปิดอ่าน")
            _on_danger = theme.COLOR_ON_DANGER_TEXT
            self.btn_tts._main_btn.setStyleSheet(
                f"QPushButton {{ background-color: {theme.COLOR_DANGER_BTN}; color: {_on_danger}; border: none; "
                "border-radius: 14px 0 0 14px; padding: 4px 6px 4px 14px; "
                "font-weight: 600; font-size: 12px; }"
                f"QPushButton:hover {{ background-color: {theme.COLOR_DANGER_BTN_HOVER}; }}"
            )
            self.btn_tts._arrow_btn.setStyleSheet(
                f"QPushButton {{ background-color: {theme.COLOR_DANGER_BTN}; color: {_on_danger}; border: none; "
                "border-radius: 0 14px 14px 0; padding: 4px 2px; font-size: 11px; }"
                f"QPushButton:hover {{ background-color: {theme.COLOR_DANGER_BTN_HOVER}; }}"
            )
        self._update_translate_button()

    def set_tts_state(self, on):
        """set TTS state จากภายนอก (เช่น restore จาก settings)"""
        self._tts_on = bool(on)
        self._update_tts_button()

    def set_volume(self, vol):
        """set volume จากภายนอก (ไม่ trigger signal)"""
        self.vol_slider.blockSignals(True)
        self.vol_slider.setValue(int(vol))
        self.vol_slider.blockSignals(False)
        if hasattr(self, 'vol_value_lbl'):
            self.vol_value_lbl.setText(f"{int(vol)}%")

    # ════════════════════════════════════════════════════════════
    # Translate mode (แสดงสถานะ — คลิกเพื่อเปิด Settings > การแปล)
    # ════════════════════════════════════════════════════════════
    def _toggle_translate(self):
        """คลิกปุ่ม → เปิด Settings > การแปล (ไม่ toggle โหมดแล้ว)"""
        self.translate_settings.emit()

    def _update_translate_button(self):
        """อัปเดตข้อความปุ่ม translate ให้สอดคล้องกับสถานะ TTS อ่านแชท/ปิดอ่าน"""
        if not hasattr(self, "btn_translate"):
            return
        if self._translate_mode == "off":
            self.btn_translate.setVisible(False)
            return
        self.btn_translate.setVisible(True)
        if self._tts_on:
            labels = {
                "multilang": ("🌐 อ่านทุกภาษา", "on"),
                "translate": ("🔄 แปลภาษา", "warning"),
            }
        else:
            labels = {
                "multilang": ("🌐 แสดงทุกภาษาในแชท", "on"),
                "translate": ("🔄 แปลภาษาในแชท", "warning"),
            }
        text, state = labels.get(self._translate_mode, ("🔄 แปลภาษา", "warning"))
        self.btn_translate.setText(text)
        self.btn_translate.set_state(state)

    def set_translate_mode(self, mode):
        """set translate mode จากภายนอก + update button (แสดงสถานะเท่านั้น)

        ★ mode="off" → ซ่อนปุ่ม (ปิดแล้วไม่ควรเห็น)
        """
        self._translate_mode = mode
        self._update_translate_button()

    # ════════════════════════════════════════════════════════════
    # ปุ่มบน TopBar: ซ่อน / คืนค่า ผ่านคลิกขวา (Game Overlay, Overlay+, User Manager)
    # ════════════════════════════════════════════════════════════
    def _setup_hideable_buttons(self):
        self._hideable_buttons = {
            "game_overlay": ("Game Overlay", self.btn_game),
            "overlay_plus": ("Overlay+", self.btn_overlay_plus),
            "user_manager": ("User Manager", self.btn_user_manager),
        }
        for key, (label, widget) in self._hideable_buttons.items():
            self._bind_hideable_context_menu(key, label, widget)

    def _bind_hideable_context_menu(self, key: str, label: str, widget: QWidget):
        def show_menu(pos):
            menu = QMenu(self)
            menu.setStyleSheet(MENU_STYLE)
            act_hide = menu.addAction(f"ซ่อนปุ่ม {label}")
            act_hide.triggered.connect(lambda: self.hide_button(key))
            hidden = self.get_hidden_buttons()
            if hidden:
                menu.addSeparator()
                act_restore = menu.addAction("👁️ แสดงปุ่มที่ซ่อนอยู่...")
                act_restore.triggered.connect(self.open_restore_dialog)
            menu.exec_(QCursor.pos())

        widget.setContextMenuPolicy(Qt.CustomContextMenu)
        widget.customContextMenuRequested.connect(show_menu)
        if isinstance(widget, SplitButton):
            widget._main_btn.setContextMenuPolicy(Qt.CustomContextMenu)
            widget._main_btn.customContextMenuRequested.connect(show_menu)
            widget._arrow_btn.setContextMenuPolicy(Qt.CustomContextMenu)
            widget._arrow_btn.customContextMenuRequested.connect(show_menu)

    def contextMenuEvent(self, event):
        """คลิกขวาบนพื้นที่ว่างของแถบด้านบน → แสดงเมนูคืนค่าปุ่มที่ซ่อน"""
        menu = QMenu(self)
        menu.setStyleSheet(MENU_STYLE)
        hidden = self.get_hidden_buttons()
        act_restore = menu.addAction("👁️ แสดงปุ่มที่ซ่อนอยู่...")
        if hidden:
            act_restore.triggered.connect(self.open_restore_dialog)
        else:
            act_restore.setEnabled(False)
            act_restore.setText("👁️ แสดงปุ่มที่ซ่อนอยู่ (ไม่มีปุ่มที่ซ่อน)")
        menu.exec_(event.globalPos())

    def hide_button(self, key: str, save: bool = True):
        """ซ่อนปุ่มตาม key และบันทึกค่าลง settings"""
        if key in self._hideable_buttons:
            label, widget = self._hideable_buttons[key]
            widget.setVisible(False)
            if key not in self._hidden_button_keys:
                self._hidden_button_keys.append(key)
            if save and self._settings is not None:
                self._settings.topbar_hidden_buttons = list(self._hidden_button_keys)
                self._settings.save_settings()

    def restore_button(self, key: str, save: bool = True):
        """คืนค่าแสดงปุ่มตาม key และบันทึกค่าลง settings"""
        if key in self._hideable_buttons:
            label, widget = self._hideable_buttons[key]
            widget.setVisible(True)
            if key in self._hidden_button_keys:
                self._hidden_button_keys.remove(key)
            if save and self._settings is not None:
                self._settings.topbar_hidden_buttons = list(self._hidden_button_keys)
                self._settings.save_settings()

    def get_hidden_buttons(self) -> list[tuple[str, str]]:
        """คืนค่ารายการ (key, label) ของปุ่มที่กำลังถูกซ่อนอยู่"""
        return [(k, self._hideable_buttons[k][0]) for k in self._hidden_button_keys if k in self._hideable_buttons]

    def open_restore_dialog(self):
        """เปิดหน้าต่างกล่องเล็กๆ เลือกปุ่มที่ต้องการกู้คืน"""
        hidden = self.get_hidden_buttons()
        if not hidden:
            return
        dlg = RestoreButtonsDialog(hidden, parent=self.window())
        if dlg.exec_() == QDialog.Accepted:
            selected_keys = dlg.get_selected_keys()
            for key in selected_keys:
                self.restore_button(key, save=False)
            if self._settings is not None:
                self._settings.topbar_hidden_buttons = list(self._hidden_button_keys)
                self._settings.save_settings()

    def set_settings(self, settings):
        """ผูก AppSettings และซ่อนปุ่มตามที่บันทึกไว้ใน settings"""
        self._settings = settings
        hidden_keys = getattr(settings, "topbar_hidden_buttons", []) or []
        for key in list(hidden_keys):
            if key in self._hideable_buttons:
                self.hide_button(key, save=False)

    # ════════════════════════════════════════════════════════════
    # Game Overlay + Overlay+ state updates (เรียกจาก app.py)
    # ════════════════════════════════════════════════════════════
    def set_composer_active(self, active):
        self.btn_composer.set_active(active)

    def set_game_overlay_active(self, active):
        self.btn_game.set_active(active)

    def set_overlay_plus_active(self, active):
        self.btn_overlay_plus.set_active(active, state="warning" if active else "")

    # ════════════════════════════════════════════════════════════
    # ★ Update notification button (pulse animation)
    # ════════════════════════════════════════════════════════════
    def _get_update_btn_style(self, brightness: float = 1.0, border_alpha: float = 0.8) -> str:
        """สไตล์ Neon Sign ตามธีม: มีเส้นขอบนีออนเรืองแสง และความสว่างที่กระพริบตามแรงดันไฟ"""
        accent = getattr(theme, "COLOR_ACCENT", "#7c3aed")
        accent_hover = getattr(theme, "COLOR_ACCENT_HOVER", "#6d28d9")
        on_text = getattr(theme, "COLOR_ON_ACCENT_TEXT", "#ffffff")

        from PySide6.QtGui import QColor
        ac_color = QColor(accent)
        r, g, b = ac_color.red(), ac_color.green(), ac_color.blue()

        # คำนวณความสว่างของหลอดนีออน (Tube Brightness)
        bg_r = int(min(255, r * (0.6 + brightness * 0.4)))
        bg_g = int(min(255, g * (0.6 + brightness * 0.4)))
        bg_b = int(min(255, b * (0.6 + brightness * 0.4)))
        bg_hex = f"#{bg_r:02x}{bg_g:02x}{bg_b:02x}"

        return (
            "QPushButton { "
            f"background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {bg_hex}, stop:1 {accent_hover}); "
            f"color: {on_text}; "
            f"border: 1.5px solid rgba({r}, {g}, {b}, {border_alpha:.2f}); "
            "border-radius: 16px; "
            "padding: 4px 18px; "
            "font-size: 12px; "
            "font-weight: 700; "
            "letter-spacing: 0.8px; "
            "} "
            "QPushButton:hover { "
            f"background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {accent_hover}, stop:1 {accent}); "
            f"border: 1.5px solid rgba(255, 255, 255, 0.9); "
            "} "
            "QPushButton:pressed { "
            f"background: {accent_hover}; "
            "padding-top: 5px; padding-bottom: 3px; "
            "}"
        )

    def show_update_button(self, version=""):
        """แสดงปุ่ม UPDATE + เริ่ม Motion Reference Neon Flicker Effect"""
        self.btn_update.setText("NEW UPDATE")
        if version:
            self.btn_update.setToolTip(f"มีเวอร์ชั่นใหม่ v{version} — คลิกเพื่ออัพเดท")
        self.btn_update.set_neon_state(1.0, 180, 16)
        self.btn_update.setVisible(True)
        self.btn_update.raise_()
        self._update_glow.setEnabled(True)
        if self._update_pulse.state() != QVariantAnimation.Running:
            self._update_pulse.start()

    def hide_update_button(self):
        """ซ่อนปุ่ม UPDATE + หยุด animation"""
        self.btn_update.setVisible(False)
        self._update_pulse.stop()
        self._update_glow.setEnabled(False)

    def _on_pulse_update(self, val):
        """Motion Reference: Neon Flicker Pattern
        จำลองหลอดไฟนีออนวินเทจ: สว่างคงที่ 80% ของเวลา แล้วเกิดการสั่นไหว/ไฟตกแบบสุ่ม (Electric Micro-flicker)
        """
        import math
        from PySide6.QtGui import QColor

        # คำนวณความสว่างของนีออนตามช่วงเวลาของลูป
        if val < 0.65:
            # นิ่งสงบ สว่างเต็มที่ พร้อม breathing เล็กๆ
            p = (math.sin(val / 0.65 * math.pi * 2) + 1.0) / 2.0
            brightness = 0.95 + 0.1 * p
            blur = int(14 + p * 4)
            glow_alpha = int(180 + p * 50)
        elif val < 0.70:
            # ไฟวูบลง (Dip)
            brightness = 0.35
            blur = 6
            glow_alpha = 70
        elif val < 0.74:
            # สว่างวาบ (Burst)
            brightness = 1.3
            blur = 28
            glow_alpha = 255
        elif val < 0.78:
            # สั่นไหว
            brightness = 0.5
            blur = 8
            glow_alpha = 90
        elif val < 0.82:
            # ดับชั่วพริบตา (Flicker off)
            brightness = 0.15
            blur = 2
            glow_alpha = 20
        elif val < 0.88:
            # วาบครั้งสุดท้ายก่อนนิ่ง
            brightness = 1.2
            blur = 24
            glow_alpha = 240
        else:
            # คืนค่าสว่างนิ่ง
            brightness = 1.0
            blur = 16
            glow_alpha = 200

        # 1. อัปเดต DropShadow Aura ด้านหลังปุ่ม
        self._update_glow.setBlurRadius(blur)
        accent = getattr(theme, "COLOR_ACCENT", "#7c3aed")
        ac_col = QColor(accent)
        self._update_glow.setColor(QColor(ac_col.red(), ac_col.green(), ac_col.blue(), glow_alpha))

        # 2. ให้ NeonButton วาดเส้นหลอดนีออนและข้อความเรืองแสงใหม่แบบ Realtime
        self.btn_update.set_neon_state(brightness, glow_alpha, blur)

    # ════════════════════════════════════════════════════════════
    # OBS button state (poll จาก app.py ทุก 3 วิ)
    # ════════════════════════════════════════════════════════════
    def set_obs_running(self, running: bool):
        """★ เปลี่ยนสถานะปุ่ม OBS — เรียกจาก app.py (poll ทุก 3 วิ)

        running=True  → "กำลังใช้งาน OBS" (สีเขียว)
        running=False → "เปิด OBS" (สีเทา)
        """
        if self._obs_running == running:
            return  # ไม่เปลี่ยน → ไม่ต้อง update
        self._obs_running = running
        if running:
            self.btn_obs.setText("  กำลังใช้งาน OBS")
            theme.styled(self.btn_obs, "QPushButton { background-color: #064e3b; color: #6ee7b7; border: 1px solid #10b981; "
                "border-radius: 6px; padding: 4px 12px; font-size: 13px; font-weight: 600; }"
                "QPushButton:hover { background-color: #065f46; border-color: #34d399; }"
                "QPushButton:pressed { background-color: #064e3b; }")
            self.btn_obs.setToolTip("OBS กำลังรันอยู่ — กดเพื่อเปิดหน้าต่าง")
        else:
            self.btn_obs.setText("  เปิด OBS")
            theme.styled(self.btn_obs, "QPushButton { background-color: #1e293b; color: #e2e8f0; border: 1px solid #334155; "
                "border-radius: 6px; padding: 4px 12px; font-size: 13px; font-weight: 600; }"
                "QPushButton:hover { background-color: #334155; border-color: #475569; }"
                "QPushButton:pressed { background-color: #0f172a; }")
            self.btn_obs.setToolTip("เปิดโปรแกรม OBS")

    def update_clip_hotkey_label(self, hotkey_str: str = "f9"):
        """อัปเดตข้อความปุ่ม Mark ให้แสดงปุ่มลัดปัจจุบัน เช่น ⭐ Mark (F9)"""
        hk_label = (hotkey_str or "F9").upper()
        if hasattr(self, "btn_mark_clip"):
            self.btn_mark_clip.setText(f"⭐ Mark ({hk_label})")
