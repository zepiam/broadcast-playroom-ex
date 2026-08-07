"""game_overlay_qt.py — Qt overlay แบบ standalone (รันเป็น subprocess)

ทำไมต้องแยก?
  Tk (customtkinter) และ Qt ต่างก็ต้องการเป็น event loop หลักของ process
  ถ้ารันพร้อมกันใน process เดียว → crash / ค้าง / conflict

  ทางออก: Tk main process spawn subprocess ตัวนี้ ที่รัน Qt เพียว ๆ
  คุยกันผ่าน localhost HTTP/WS (game_overlay_server.py port 8767)

วิธีรัน (เรียกจาก game_overlay.py):
  python game_overlay_qt.py --port 8767 --x 100 --y 200 --w 360 --h 500 --alpha 0.85

ตัวนี้ทำ:
  1) สร้าง Qt + QWebEngineView borderless transparent window
  2) โหลด http://127.0.0.1:{port}/
  3) ตั้ง click-through (WS_EX_TRANSPARENT)
  4) รอ command จาก stdin (JSON lines) สำหรับ toggle edit / quit
"""
from __future__ import annotations

import argparse
import ctypes
import json
import sys
import threading
import time

_user32 = ctypes.windll.user32
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
HWND_TOPMOST = -1
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010


def set_click_through(hwnd: int, on: bool) -> None:
    """toggle WS_EX_TRANSPARENT — on = เม้าส์คลิกผ่าน, off = interactive

    สำคัญ: ห้ามเพิ่ม/ลบ WS_EX_LAYERED เอง เพราะ Qt จัดการ layered window
    เองอยู่แล้ว (ผ่าน WA_TranslucentBackground) — ถ้าเราเขียนทับ จะ reset
    alpha ของ layered window เป็น 0 ทำให้ window ล่องหน
    ใส่แค่ WS_EX_TRANSPARENT พอ (สำหรับ click-through)
    """
    if not hwnd:
        return
    try:
        style = _user32.GetWindowLongA(hwnd, GWL_EXSTYLE)
        if on:
            new_style = style | WS_EX_TRANSPARENT
        else:
            new_style = style & ~WS_EX_TRANSPARENT
        _user32.SetWindowLongA(hwnd, GWL_EXSTYLE, new_style)
        _user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                             SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
    except Exception:
        pass


# overlay id สำหรับแยก queue file (Overlay+ ใช้ id เพื่อไม่ใชนกับ Game Overlay หลัก)
_OVERLAY_ID = ""

def _send_to_parent(msg: dict):
    """ส่ง command กลับ parent ผ่าน file-based queue (ทำงานได้ใน exe แน่นอน)"""
    import tempfile, os as _os
    suffix = f"_{_OVERLAY_ID}" if _OVERLAY_ID else ""
    queue_file = _os.path.join(tempfile.gettempdir(), f"game_overlay_response_queue{suffix}.json")
    try:
        existing = []
        if _os.path.exists(queue_file):
            with open(queue_file, "r", encoding="utf-8") as f:
                existing = json.load(f)
        existing.append(msg)
        with open(queue_file, "w", encoding="utf-8") as f:
            json.dump(existing, f)
        # verify เขียนติดจริง
        if not _os.path.exists(queue_file):
            raise RuntimeError("file not created after write")
    except Exception as exc:
        # log error จริง (ไม่กลืน)
        try:
            err_log = _os.path.join(tempfile.gettempdir(), f"qt_send_error_{_OVERLAY_ID or 'main'}.log")
            with open(err_log, "a", encoding="utf-8") as f:
                f.write(f"_send_to_parent FAILED: {type(exc).__name__}: {exc} | file={queue_file}\n")
        except Exception:
            pass


def main():
    # กรอง --game-overlay-qt ออก (เป็น flag สำหรับ exe เท่านั้น)
    import sys as _sys
    clean_argv = [a for a in _sys.argv if a != "--game-overlay-qt"]
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8767)
    parser.add_argument("--x", type=int, default=-1)
    parser.add_argument("--y", type=int, default=-1)
    parser.add_argument("--w", type=int, default=360)
    parser.add_argument("--h", type=int, default=500)
    parser.add_argument("--alpha", type=float, default=0.85)
    parser.add_argument("--url", type=str, default="", help="custom URL (Overlay+ — ถ้าว่างใช้ localhost)")
    parser.add_argument("--id", type=str, default="", help="overlay id (สำหรับแยก queue file)")
    parser.add_argument("--mode", type=str, default="game", help="game | overlay+ (กำหนดปุ่มใน edit bar)")
    parser.add_argument("--hk-toggle", type=str, default="", help="hotkey toggle (แสดงใน edit bar)")
    parser.add_argument("--hk-edit", type=str, default="", help="hotkey edit (แสดงใน edit bar)")
    args = parser.parse_args(clean_argv[1:])

    # ตั้ง overlay id สำหรับแยก queue file (Overlay+ ใช้ id ไม่ให้ชนกับ Game Overlay หลัก)
    global _OVERLAY_ID
    _OVERLAY_ID = args.id or ""

    # debug: log ทุกขั้นตอนเริ่มต้น (เขียนลง temp — กัน cwd ผิด)
    import tempfile as _tf, os as _os
    _qt_debug = _os.path.join(_tf.gettempdir(), f"qt_startup_{_OVERLAY_ID or 'main'}.log")
    def _qtlog(msg):
        try:
            with open(_qt_debug, "a", encoding="utf-8") as f:
                f.write(msg + "\n")
        except Exception:
            pass
    _qtlog(f"=== Qt subprocess start ===")
    _qtlog(f"argv: {clean_argv}")
    _qtlog(f"args: url={args.url} id={args.id} mode={args.mode} port={args.port}")
    _qtlog(f"_OVERLAY_ID={_OVERLAY_ID}")

    # import Qt (delayed — กัน Tk import ที่อาจจะมาก่อน)
    _qtlog("importing PySide6...")
    from PySide6 import QtCore, QtGui, QtWidgets
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings, QWebEngineUrlRequestInterceptor, QWebEngineProfile
    _qtlog("PySide6 imported OK")

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["GameOverlay"])
    _qtlog("QApplication created")

    # ★ ใช้ off-the-record profile (incognito) — ไม่เก็บ HTTP cache ป้องกัน HTML เวอร์ชันเก่า
    #    ★★ ต้องสร้างหลัง QApplication เสมอ (Qt ต้องการ QApp ก่อน QWebEngineProfile)
    _incognito_profile = QWebEngineProfile("incognito_overlay")
    _incognito_profile.setHttpCacheType(QWebEngineProfile.MemoryHttpCache)
    _incognito_profile.setPersistentCookiesPolicy(QWebEngineProfile.NoPersistentCookies)
    _qtlog("incognito profile created")

    # ★ ลบ QtWebEngine persistent cache เก่า — กัน HTML เวอร์ชันเก่าค้าง
    #    (เกิดจาก default profile ที่เคยใช้ก่อนเปลี่ยนเป็น incognito)
    try:
        import shutil
        _old_cache = os.path.join(os.path.expanduser("~"), ".tts-for-livestream", "game_overlay_chrome")
        if os.path.isdir(_old_cache):
            shutil.rmtree(_old_cache, ignore_errors=True)
            _qtlog(f"cleared old QtWebEngine cache: {_old_cache}")
    except Exception as _e:
        _qtlog(f"cache clear skipped: {_e}")

    # ── Cross-thread signal (cmd_poller thread → Qt main thread) ──
    class CommandRelay(QtCore.QObject):
        cmdReceived = QtCore.Signal(str, dict)

    relay = CommandRelay()

    # ── Command handler QObject (cross-thread safe) ──
    # stdin_reader (background thread) → invokeMethod → Qt main thread
    class CommandHandler(QtCore.QObject):
        def __init__(self):
            super().__init__()
            self._commands = []  # queue of (cmd, msg)

        @QtCore.Slot(str, str)
        def handle_command(self, cmd: str, msg_json: str):
            """รับ command ใน Qt main thread (เรียกจาก invokeMethod)"""
            import json as _json
            try:
                msg = _json.loads(msg_json) if msg_json else {}
            except Exception:
                msg = {}
            # dispatch ไปยัง handler เดิม (ตอนนี้อยู่ใน Qt main thread แล้ว → safe)
            _dispatch_command(cmd, msg)

    cmd_handler = CommandHandler()

    class TransparentPage(QWebEnginePage):
        def __init__(self, *a, **kw):
            # ★ ใช้ incognito profile (no persistent cache) — กัน HTML เก่า
            #    PySide6: profile ต้องส่งเป็น positional arg ตัวที่ 2 (ไม่ใช่ kwarg)
            if len(a) < 2:
                a = (a[0] if a else None, _incognito_profile) + a[2:]
            super().__init__(*a, **kw)
            self.setBackgroundColor(QtCore.Qt.transparent)

        def javaScriptConsoleMessage(self, level, message, line, source):
            # ★ ส่ง JS console.log ไป Qt log file (สำหรับ debug)
            _qtlog(f"[JS] {message}")

    class OverlayWindow(QtWidgets.QWidget):
        pass

    win = OverlayWindow()
    win.setWindowFlags(
        QtCore.Qt.FramelessWindowHint
        | QtCore.Qt.WindowStaysOnTopHint
    )
    win.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
    win.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)
    # container เป็น inner frame — เพื่อทำกรอบสีแดง (edit mode) ได้
    # (win เองโปร่งใส ส่วน inner frame จะมี border)

    # position + size
    screen_w = _user32.GetSystemMetrics(0)
    screen_h = _user32.GetSystemMetrics(1)
    x = args.x if args.x >= 0 else screen_w - args.w - 20
    y = args.y if args.y >= 0 else screen_h - args.h - 60
    win.setGeometry(x, y, args.w, args.h)
    # ★ window alpha = 1.0 เสมอ → กรอบ edit frame (แดง) ชัด 100% เสมอ (จัดวางได้แม่น)
    #   การปรับโปร่งใสย้ายไปคุมที่ webview content แทน (ดู _view_opacity ด้านล่าง)

    layout = QtWidgets.QVBoxLayout(win)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)

    page = TransparentPage()
    # JS → Python bridge ผ่าน URL interceptor
    class ApiInterceptor(QWebEngineUrlRequestInterceptor):
        def interceptRequest(self, info):
            url = info.requestUrl().toString()
            if url.startswith("qt://api/"):
                method = url[len("qt://api/"):].split("?")[0]
                # ส่ง command ออก stdout ให้ parent process จัดการ
                try:
                    sys.stdout.write(json.dumps({"cmd": method}) + "\n")
                    sys.stdout.flush()
                    _send_to_parent({"cmd": method})
                except Exception:
                    pass
                info.block(True)

    interceptor = ApiInterceptor()

    # state
    edit_mode = [False]  # mutable ref

    # ─── native edit bar (Qt widget — ดัก mouse ได้จริง) ───
    # อยู่ด้านบนของ view, โชว์เฉพาะ edit mode
    edit_bar = QtWidgets.QFrame()
    edit_bar.setFixedHeight(28)
    edit_bar.setStyleSheet(
        "QFrame { background: rgba(0,0,0,0.92); border-bottom: 2px solid #ef4444; }"
        "QLabel { color: #fbbf24; font-weight: 600; font-size: 12px; padding-left: 8px; }"
        "QPushButton { background: #374151; color: #fff; border: 0; padding: 4px 10px;"
        "              border-radius: 4px; font-size: 12px; margin-right: 4px; }"
        "QPushButton:hover { background: #4b5563; }"
        "QPushButton#gear:hover { background: #7c3aed; }"
        "QPushButton#confirm:hover { background: #ef4444; }"
    )
    edit_bar_layout = QtWidgets.QHBoxLayout(edit_bar)
    edit_bar_layout.setContentsMargins(0, 0, 4, 0)
    edit_bar_layout.setSpacing(0)
    title_lbl = QtWidgets.QLabel("Edit Mode — คลิกตรงนี้เพื่อลากย้ายตำแหน่ง")
    edit_bar_layout.addWidget(title_lbl)
    edit_bar_layout.addStretch()
    edit_bar.hide()  # ซ่อนตอนเริ่ม (ไม่มีปุ่มใน edit_bar — ย้ายลง bottom_bar หมด)

    def on_gear():
        _send_to_parent({"cmd": "open_settings"})
    def on_confirm():
        _send_to_parent({"cmd": "exit_edit"})

    # drag handler บน edit_bar (Qt widget ดัก mouse ได้จริง)
    drag_state = {"active": False, "start": None, "win_pos": None}

    class DragBar(QtWidgets.QFrame):
        """edit bar ที่ลาก window ได้ — แต่ปุ่มด้านในคลิกได้"""
        def mousePressEvent(self, event):
            if event.button() == QtCore.Qt.LeftButton:
                # เช็คว่า click ตรงปุ่มไหม — ถ้าใช่ ส่งต่อให้ปุ่ม (ไม่ลาก)
                child = self.childAt(event.position().toPoint())
                if child and isinstance(child, QtWidgets.QPushButton):
                    super().mousePressEvent(event)
                    return
                # ไม่ใช่ปุ่ม → เริ่มลาก
                drag_state["active"] = True
                drag_state["start"] = event.globalPosition().toPoint()
                drag_state["win_pos"] = win.frameGeometry().topLeft()
            else:
                super().mousePressEvent(event)

        def mouseMoveEvent(self, event):
            if drag_state["active"] and (event.buttons() & QtCore.Qt.LeftButton):
                delta = event.globalPosition().toPoint() - drag_state["start"]
                win.move(drag_state["win_pos"] + delta)
            else:
                super().mouseMoveEvent(event)

        def mouseReleaseEvent(self, event):
            if event.button() == QtCore.Qt.LeftButton:
                drag_state["active"] = False
            else:
                super().mouseReleaseEvent(event)

    # แทนที่ edit_bar ด้วย DragBar (rebuild)
    edit_bar.setParent(None)
    edit_bar = DragBar()
    edit_bar.setFixedHeight(28)
    edit_bar.setStyleSheet(
        "DragBar { background: rgba(0,0,0,0.92); border-bottom: 2px solid #ef4444; }"
        "QLabel { color: #fbbf24; font-weight: 600; font-size: 12px; padding-left: 8px; }"
        "QPushButton { background: #374151; color: #fff; border: 0; padding: 4px 10px;"
        "              border-radius: 4px; font-size: 12px; margin-right: 4px; }"
        "QPushButton:hover { background: #4b5563; }"
        "QPushButton#gear:hover { background: #7c3aed; }"
        "QPushButton#confirm:hover { background: #ef4444; }"
        "QPushButton#stopdemo { background: #b91c1c; }"
        "QPushButton#stopdemo:hover { background: #ef4444; }"
    )
    edit_bar_layout = QtWidgets.QHBoxLayout(edit_bar)
    edit_bar_layout.setContentsMargins(0, 0, 4, 0)
    edit_bar_layout.setSpacing(0)
    title_lbl = QtWidgets.QLabel("Edit Mode — คลิกตรงนี้เพื่อลากย้ายตำแหน่ง")
    edit_bar_layout.addWidget(title_lbl)
    edit_bar_layout.addStretch()
    edit_bar.hide()

    layout.addWidget(edit_bar)

    # ─── bottom bar (edit mode) — ปุ่มเล็ก ๆ ด้านล่าง ───
    class BottomBar(QtWidgets.QFrame):
        pass

    bottom_bar = BottomBar()
    bottom_bar.setFixedHeight(24)
    bottom_bar.setStyleSheet(
        "BottomBar { background: rgba(0,0,0,0.85); border-top: 1px solid #ef4444; }"
        "QPushButton { background: #374151; color: #fff; border: 0; padding: 2px 8px;"
        "              border-radius: 3px; font-size: 11px; margin: 2px 4px 2px 0; }"
        "QPushButton:hover { background: #4b5563; }"
        "QPushButton#stopdemo { background: #b91c1c; }"
        "QPushButton#stopdemo:hover { background: #ef4444; }"
        "QPushButton#toggledemo { background: #16a34a; }"
        "QPushButton#toggledemo:hover { background: #22c55e; }"
        "QPushButton#toggledemo.running { background: #b91c1c; }"
        "QPushButton#toggledemo.running:hover { background: #ef4444; }"
        "QPushButton#clearmsg { background: #6b7280; }"
        "QPushButton#clearmsg:hover { background: #9ca3af; }"
    )
    bottom_bar_layout = QtWidgets.QHBoxLayout(bottom_bar)
    bottom_bar_layout.setContentsMargins(4, 0, 4, 0)
    bottom_bar_layout.setSpacing(0)
    bottom_bar_layout.addStretch()

    def on_toggle_demo():
        """toggle loop demo — ส่ง toggle_demo command ให้ parent"""
        _send_to_parent({"cmd": "toggle_demo"})

    def on_clear_msgs():
        _send_to_parent({"cmd": "clear_msgs"})

    def on_close_overlay():
        """ปิด overlay+ (Overlay+ mode only)"""
        _send_to_parent({"cmd": "quit"})

    # ── ปุ่มใน bottom bar ต่างกันตาม mode ──
    _is_overlay_plus = (args.mode == "overlay+")
    _is_viewer = (args.mode == "viewer")
    if _is_overlay_plus:
        # Overlay+ mode: hint text แทนปุ่ม (ปุ่มใช้ไม่ได้เพราะ click-through + queue issue)
        hk_t = args.hk_toggle or "ctrl+shift+m"
        hk_e = args.hk_edit or "ctrl+shift+n"
        hint_lbl = QtWidgets.QLabel(
            f"  Hint: กด [{hk_e}] = ซ่อน Edit  |  กด [{hk_t}] = ปิด Overlay+"
        )
        hint_lbl.setStyleSheet("color: #9ca3af; font-size: 11px; padding: 2px 8px;")
        bottom_bar_layout.addWidget(hint_lbl)
        bottom_bar.hide()
    elif _is_viewer:
        # Viewer mode: hint text สั้นๆ (ไม่มีปุ่ม demo/clear)
        hint_lbl = QtWidgets.QLabel("  👥 Viewer Overlay — ลากเพื่อย้าย")
        hint_lbl.setStyleSheet("color: #9ca3af; font-size: 11px; padding: 2px 8px;")
        bottom_bar_layout.addWidget(hint_lbl)
        bottom_bar.hide()
    else:
        # Game mode: Demo + Clear + เฟืองขวาสุด
        demo_btn = QtWidgets.QPushButton("🎬 เปิด Loop Demo")
        demo_btn.setObjectName("toggledemo")
        clear_msg_btn = QtWidgets.QPushButton("🗑 ล้างข้อความ")
        clear_msg_btn.setObjectName("clearmsg")
        bottom_bar_layout.addWidget(demo_btn)
        bottom_bar_layout.addWidget(clear_msg_btn)
        bottom_bar_layout.addStretch()
        # เฟือง (เปิด settings) ขวาสุด
        gear_btn2 = QtWidgets.QPushButton("⚙ ตั้งค่า")
        gear_btn2.setObjectName("gear")
        bottom_bar_layout.addWidget(gear_btn2)
        bottom_bar.hide()
        demo_btn.clicked.connect(on_toggle_demo)
        clear_msg_btn.clicked.connect(on_clear_msgs)
        gear_btn2.clicked.connect(on_gear)

    layout.addWidget(bottom_bar)
    class ResizeGrip(QtWidgets.QSizeGrip):
        """SizeGrip ปกติ แต่ style เด่นชัด"""
        pass

    resize_grip = ResizeGrip(win)
    resize_grip.setFixedSize(20, 20)
    resize_grip.setStyleSheet(
        # พื้นหลังเทาเข้ม + ขอบแดง + มีลวดลายบอกว่าลากได้
        "QSizeGrip {"
        "  background: rgba(0,0,0,0.85);"
        "  border: 2px solid #ef4444;"
        "  border-top-left-radius: 4px;"
        "  border-bottom-right-radius: 0px;"
        "  image: none;"  # กัน icon default
        "}"
        "QSizeGrip:hover {"
        "  background: #ef4444;"
        "  border: 2px solid #fca5a5;"
        "}"
    )
    resize_grip.setCursor(QtCore.Qt.SizeFDiagCursor)
    resize_grip.hide()  # ซ่อนตอนเริ่ม (โชว์เฉพาะ edit mode)

    # ─── view container (QFrame ทำกรอบที่เห็นได้จริง) ───
    # QtWebEngine ไม่ support border บนตัวมันเอง → wrap ใน QFrame
    view_container = QtWidgets.QFrame()
    view_container.setObjectName("viewContainer")
    view_layout = QtWidgets.QVBoxLayout(view_container)
    view_layout.setContentsMargins(0, 0, 0, 0)

    # ─── web view (QWebEngineView) ───
    view = QWebEngineView()
    view.setPage(page)
    view.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
    view.page().setBackgroundColor(QtCore.Qt.transparent)
    view.setContextMenuPolicy(QtCore.Qt.NoContextMenu)
    view.page().settings().setAttribute(QWebEngineSettings.ShowScrollBars, False)
    view.page().setUrlRequestInterceptor(interceptor)
    view_layout.addWidget(view)
    # ★ opacity effect บน webview content เท่านั้น (window + edit frame ยัง 100%)
    view_opacity_effect = QtWidgets.QGraphicsOpacityEffect(view)
    view_opacity_effect.setOpacity(max(0.0, min(1.0, args.alpha)))
    view.setGraphicsEffect(view_opacity_effect)
    layout.addWidget(view_container, 1)  # stretch=1 — container ขยายเต็ม

    # ─── กรอบสีแดง (edit mode) — setStyleSheet ตรง ๆ บน container ───
    NORMAL_BORDER = "QFrame { background: transparent; border: 0px; }"
    EDIT_BORDER = (
        "QFrame { background: transparent; border: 2px dashed #ef4444; }"
    )

    def apply_edit_border(editing: bool):
        """ตั้งกรอบสีแดง (edit mode) ผ่าน QFrame container"""
        view_container.setStyleSheet(EDIT_BORDER if editing else NORMAL_BORDER)

    # load URL — ถ้ามี --url (Overlay+) ใช้ URL นั้น ไม่งั้นใช้ localhost (Game Overlay)
    if args.url:
        url = QtCore.QUrl(args.url)
    else:
        # ★ cache-bust: เพิ่ม timestamp query string กัน Qt WebEngine ใช้ HTML เก่าจาก cache
        import time
        url = QtCore.QUrl(f"http://127.0.0.1:{args.port}/?_t={int(time.time())}")
    view.load(url)
    # ตั้ง style เริ่มต้นของ container (ยังไม่มีกรอบ — จะโชว์ตอน edit mode)
    apply_edit_border(False)
    win.show()
    win.raise_()
    win.activateWindow()

    # ─── position resize_grip ที่มุมขวาล่าง + reposition เมื่อ window resize ───
    def update_grip_pos():
        # วางที่มุมขวาล่างของ win (absolute ภายใน win)
        grip_size = 20
        resize_grip.move(win.width() - grip_size - 2, win.height() - grip_size - 2)
        resize_grip.raise_()

    # hook resizeEvent
    orig_resize = win.resizeEvent

    def on_resize(event):
        orig_resize(event)
        update_grip_pos()
    win.resizeEvent = on_resize
    QtCore.QTimer.singleShot(100, update_grip_pos)  # initial position

    # get hwnd + apply click-through
    hwnd = int(win.winId())
    _qtlog(f"hwnd={hwnd}, window created, mode={args.mode}")

    def bring_to_foreground(target_hwnd):
        """ขอ foreground + bypass cross-process input restriction"""
        try:
            import ctypes as _ctypes
            pid_buf = _ctypes.c_uint32()
            cur_thread = _user32.GetWindowThreadProcessId(
                _user32.GetForegroundWindow(), _ctypes.byref(pid_buf)
            )
            my_thread = _user32.GetWindowThreadProcessId(
                target_hwnd, _ctypes.byref(pid_buf)
            )
            if cur_thread != my_thread:
                _user32.AttachThreadInput(cur_thread, my_thread, True)
            _user32.SetForegroundWindow(target_hwnd)
            _user32.SetActiveWindow(target_hwnd)
            _user32.BringWindowToTop(target_hwnd)
            if cur_thread != my_thread:
                _user32.AttachThreadInput(cur_thread, my_thread, False)
            win.raise_()
            win.activateWindow()
            win.setFocus()
        except Exception:
            pass

    def init_click_through():
        nonlocal hwnd
        hwnd = int(win.winId())
        # เริ่มต้น: edit mode ON (interactive — โชว์ native edit bar + ลากได้)
        edit_mode[0] = True
        set_click_through(hwnd, False)
        edit_bar.show()  # โชว์ native Qt edit bar
        bottom_bar.show()  # โชว์ native bottom bar (ปิด demo + ล้าง)
        resize_grip.show()  # โชว์ resize grip
        apply_edit_border(True)  # กรอบสีแดง
        update_grip_pos()
        # ขอ foreground ทันที เพื่อให้คลิก/ลาก ได้
        bring_to_foreground(hwnd)

    QtCore.QTimer.singleShot(500, init_click_through)

    # topmost re-enforce every 2s
    def keep_topmost():
        if hwnd:
            try:
                _user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                                     SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
            except Exception:
                pass

    topmost_timer = QtCore.QTimer()
    topmost_timer.timeout.connect(keep_topmost)
    topmost_timer.start(2000)

    # ─── stdin command listener (รับจาก parent process) ───
    # commands: {"cmd": "edit_on"} / {"cmd": "edit_off"} / {"cmd": "quit"} / {"cmd": "save_pos"}
    def _dispatch_command(cmd, msg):
        """จัดการ command ใน Qt main thread"""
        # debug log (absolute path — กัน cwd ผิด)
        try:
            import tempfile as _tf
            log_path = _tf.path.join(_tf.gettempdir(), f"game_overlay_qt_{_OVERLAY_ID or 'main'}.log")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"dispatch: cmd={cmd} msg={msg}\n")
        except Exception:
            pass
        if cmd == "edit_on":
            edit_mode[0] = True
            set_click_through(hwnd, False)
            edit_bar.show()
            bottom_bar.show()
            resize_grip.show()
            apply_edit_border(True)
            update_grip_pos()
            bring_to_foreground(hwnd)
        elif cmd == "edit_off":
            # ทำทุกอย่างใน QTimer.singleShot (ให้แน่ใจอยู่ใน Qt main thread)
            def _do_edit_off():
                edit_mode[0] = False
                edit_bar.hide()
                bottom_bar.hide()
                resize_grip.hide()
                apply_edit_border(False)
                try:
                    geo = win.geometry()
                    _send_to_parent({
                        "cmd": "position",
                        "x": geo.x(), "y": geo.y(),
                        "w": geo.width(), "h": geo.height(),
                    })
                except Exception:
                    pass
                set_click_through(hwnd, True)
            QtCore.QTimer.singleShot(0, _do_edit_off)
        elif cmd == "quit" or cmd == "__quit__":
            app.quit()
        elif cmd == "reload":
            view.reload()
        elif cmd == "edit_toggle":
            # toggle edit mode ใน Qt เอง (ไม่ต้อง track state ใน parent → กัน state mismatch)
            if edit_mode[0]:
                # ปิด edit mode
                edit_mode[0] = False
                edit_bar.hide()
                bottom_bar.hide()
                resize_grip.hide()
                apply_edit_border(False)
                try:
                    geo = win.geometry()
                    _send_to_parent({
                        "cmd": "position",
                        "x": geo.x(), "y": geo.y(),
                        "w": geo.width(), "h": geo.height(),
                    })
                except Exception:
                    pass
                set_click_through(hwnd, True)
            else:
                # เปิด edit mode
                edit_mode[0] = True
                set_click_through(hwnd, False)
                edit_bar.show()
                bottom_bar.show()
                resize_grip.show()
                apply_edit_border(True)
                update_grip_pos()
                bring_to_foreground(hwnd)
        elif cmd == "demo_state":
            running = bool(msg.get("running", False))
            if running:
                demo_btn.setText("⏸ ปิด Loop Demo")
                demo_btn.setProperty("class", "running")
            else:
                demo_btn.setText("🎬 เปิด Loop Demo")
                demo_btn.setProperty("class", "")
            demo_btn.style().unpolish(demo_btn)
            demo_btn.style().polish(demo_btn)
        elif cmd == "set_alpha":
            # ★ alpha คุม webview content เท่านั้น (window + edit frame ยัง 100%)
            alpha_val = float(msg.get("alpha", 0.85))
            view_opacity_effect.setOpacity(max(0.0, min(1.0, alpha_val)))

    def cmd_poller():
        """poll command จาก file-based queue ทุก 200ms → ส่งไป Qt main thread"""
        import tempfile, os as _os
        suffix = f"_{_OVERLAY_ID}" if _OVERLAY_ID else ""
        queue_file = _os.path.join(tempfile.gettempdir(), f"game_overlay_cmd_queue{suffix}.json")
        while True:
            try:
                if _os.path.exists(queue_file):
                    with open(queue_file, "r", encoding="utf-8") as f:
                        cmds = json.load(f)
                    # clear file
                    with open(queue_file, "w", encoding="utf-8") as f:
                        json.dump([], f)
                    if cmds:
                        try:
                            with open("game_overlay_qt.log", "a", encoding="utf-8") as f:
                                f.write(f"poll got {len(cmds)} cmds: {[c.get('cmd') for c in cmds]}\n")
                        except Exception:
                            pass
                    for cmd_msg in cmds:
                        cmd = cmd_msg.get("cmd")
                        if cmd:
                            relay.cmdReceived.emit(cmd, cmd_msg)
                            if cmd == "quit":
                                relay.cmdReceived.emit("__quit__", {})
                                return
            except Exception as exc:
                try:
                    with open("game_overlay_qt.log", "a", encoding="utf-8") as f:
                        f.write(f"poll error: {exc}\n")
                except Exception:
                    pass
            import time as _t
            _t.sleep(0.2)

    # เชื่อม relay signal → _dispatch_command (Qt main thread)
    relay.cmdReceived.connect(_dispatch_command)

    cmd_thread = threading.Thread(target=cmd_poller, daemon=True)
    cmd_thread.start()
    _qtlog("cmd_poller thread started")

    # บอก parent ว่าพร้อมแล้ว — ส่งทั้ง stdout + file queue (parent อ่าน stdout ก่อน)
    sys.stdout.write(json.dumps({"cmd": "ready", "hwnd": hwnd}) + "\n")
    sys.stdout.flush()
    _send_to_parent({"cmd": "ready", "hwnd": hwnd})
    _qtlog(f"ready sent: hwnd={hwnd} (stdout + file queue)")

    # เช็คว่า cmd_queue file path ถูกต้องไหม
    import tempfile as _tf2, os as _os2
    _cmd_qf = _os2.path.join(_tf2.gettempdir(), f"game_overlay_cmd_queue_{_OVERLAY_ID}.json" if _OVERLAY_ID else "game_overlay_cmd_queue.json")
    _qtlog(f"cmd_queue path: {_cmd_qf}")

    # run Qt event loop (blocking)
    try:
        app.exec()
    except Exception:
        pass


if __name__ == "__main__":
    main()
