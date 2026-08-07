"""user_manager.py — User Manager dialog

หน้าจัดการผู้ชม — แสดงรายชื่อ + รายละเอียดต่อ user
- Platform tabs (กรองเฉพาะ user ที่เคยแชทจาก platform นั้น)
- Search (ทั้งชื่อเดิม + ชื่อที่เปลี่ยน)
- User list: ชื่อ + จำนวนข้อความ
- Detail: stats + donate + history + export
"""
from __future__ import annotations

import os
import threading
from datetime import datetime
from typing import Optional

import customtkinter as ctk

# import colors + helpers from app_gui (lazy to avoid circular)
_COLOR_BG = "#0a0e1a"
_COLOR_CARD = "#131726"
_COLOR_CARD_HI = "#1a1f33"
_COLOR_ACCENT = "#7c3aed"
_COLOR_ACCENT_HOVER = "#6d28d9"
_COLOR_ACCENT_2 = "#06b6d4"
_COLOR_HEADING = "#f59e0b"
_COLOR_DANGER = "#ef4444"
_COLOR_DANGER_HOVER = "#dc2626"
_COLOR_SUCCESS = "#10b981"
_COLOR_SUCCESS_HOVER = "#059669"
_COLOR_INFO = "#06b6d4"            # สีฟ้า (cyan) — สำหรับปุ่ม "บังคับแปล"
_COLOR_INFO_HOVER = "#0891b2"
_COLOR_TEXT = "#e5e7eb"
_COLOR_TEXT_DIM = "#9ca3af"
_COLOR_BORDER = "#2a2f45"


def _font(size: int = 14, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(family="Segoe UI", size=size, weight=weight)


class UserManagerDialog(ctk.CTkToplevel):
    """หน้าจัดการผู้ชม — platform tabs + search + list + detail"""

    def __init__(self, parent_app) -> None:
        super().__init__(parent_app)
        self.parent_app = parent_app
        self.title("👤 User Manager")
        self.geometry("1100x680")
        self.minsize(900, 500)
        self.configure(fg_color=_COLOR_BG)
        self.transient(parent_app)
        self.grab_set()
        self.lift()
        self.focus_force()

        # state
        self._current_platform = "all"
        self._search_query = ""
        self._selected_author = None
        self._history_limit = 50
        self._last_refresh_ts = 0.0  # throttle: refresh ตอน focus ไม่เกินทุก 3 วิ

        # ── header ──
        header = ctk.CTkFrame(self, fg_color=_COLOR_CARD, corner_radius=0, height=44)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)
        ctk.CTkLabel(
            header, text="👤 User Manager",
            font=_font(16, "bold"), text_color=_COLOR_TEXT,
        ).pack(side="left", padx=16)
        # refresh button (ขวาสุด) — โหลดข้อมูลใหม่ทั้ง list + detail
        ctk.CTkButton(
            header, text="🔄 Refresh", width=92, height=28,
            fg_color=_COLOR_ACCENT_2, hover_color=_COLOR_INFO_HOVER,
            text_color="#fff", font=_font(12, "bold"),
            command=self._refresh_all,
        ).pack(side="right", padx=10)

        # auto-refresh ตอนกลับมา focus หน้าต่างนี้ (เช่น alt-tab กลับมา)
        # เผื่อกรณีเปิดค้างไว้แล้วมีข้อความใหม่เข้า — จะได้เห็น history ล่าสุด
        self.bind("<FocusIn>", self._on_focus_in)

        # ── platform tabs ──
        tab_frame = ctk.CTkFrame(self, fg_color="transparent", height=36)
        tab_frame.pack(fill="x", padx=8, pady=(4, 2))
        self._platform_tabs: dict[str, ctk.CTkButton] = {}
        platforms = ["all", "twitch", "youtube", "mylive", "tiktok", "kick"]
        plat_labels = {
            "all": "🌐 ทั้งหมด", "twitch": "🟣 Twitch", "youtube": "🔴 YouTube",
            "mylive": "🔵 MyLive", "tiktok": "⚫ TikTok", "kick": "🟢 KICK",
        }
        for plat in platforms:
            btn = ctk.CTkButton(
                tab_frame, text=plat_labels.get(plat, plat), width=90, height=28,
                fg_color=_COLOR_CARD_HI if plat == "all" else "transparent",
                hover_color=_COLOR_ACCENT, text_color=_COLOR_TEXT,
                font=_font(12, "bold"),
                command=lambda p=plat: self._select_platform(p),
            )
            btn.pack(side="left", padx=2)
            self._platform_tabs[plat] = btn

        # ── search bar ──
        search_frame = ctk.CTkFrame(self, fg_color="transparent")
        search_frame.pack(fill="x", padx=8, pady=(2, 4))
        self._search_entry = ctk.CTkEntry(
            search_frame, placeholder_text="ค้นหาชื่อ (เดิมหรือใหม่)...",
            width=300, height=28, font=_font(13),
        )
        self._search_entry.pack(side="left", padx=(4, 0))
        self._search_entry.bind("<KeyRelease>", lambda e: self._on_search())

        # ── main 2-column layout ──
        # สัดส่วน 25:75 (user list : detail) — เดิมใช้ width=300 คงที่
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        body.grid_columnconfigure(0, weight=0, minsize=220)  # left column (user list)
        body.grid_columnconfigure(1, weight=3)                # right column (detail) — 3x left
        body.grid_rowconfigure(0, weight=1)

        # left: user list (25% — ใช้ minsize ควบคุมความกว้างขั้นต่ำ)
        left = ctk.CTkFrame(body, fg_color=_COLOR_CARD, corner_radius=8)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        # ไม่ใช้ grid_propagate/width คงที่ — ให้ grid weight คุม (25:75)
        ctk.CTkLabel(
            left, text="รายชื่อผู้ชม", font=_font(13, "bold"),
            text_color=_COLOR_TEXT_DIM,
        ).pack(anchor="w", padx=10, pady=(8, 2))
        self._user_list_frame = ctk.CTkScrollableFrame(left, fg_color=_COLOR_BG)
        self._user_list_frame.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        # right: detail panel
        self._detail_frame = ctk.CTkScrollableFrame(body, fg_color=_COLOR_CARD)
        self._detail_frame.grid(row=0, column=1, sticky="nsew", padx=(4, 0))

        # ── close handler ──
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        # initial render
        self._refresh_user_list()

    def _smooth_update(self, fn):
        """run a UI update function without flicker — freeze layout → update → thaw"""
        try:
            self._user_list_frame.pack_forget()
            self._detail_frame.pack_forget()
        except Exception:
            pass
        try:
            fn()
        finally:
            self.update_idletasks()
            try:
                self._detail_frame.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    # Refresh — โหลดข้อมูลใหม่ทั้ง user list + detail panel
    # ------------------------------------------------------------------ #
    def _refresh_all(self) -> None:
        """refresh ทั้ง list + detail (เรียกจากปุ่ม Refresh หรือ focus event)"""
        if not self.winfo_exists():
            return
        self._refresh_user_list()
        if self._selected_author:
            self._render_detail()

    def _on_focus_in(self, _event=None) -> None:
        """refresh ตอนกลับมา focus หน้าต่างนี้ — throttle 3 วิเพื่อกัน refresh บ่อย"""
        import time as _t
        now = _t.time()
        if now - self._last_refresh_ts < 3.0:
            return
        self._last_refresh_ts = now
        self._refresh_all()

    # ------------------------------------------------------------------ #
    # Platform selection
    # ------------------------------------------------------------------ #
    def _select_platform(self, platform: str) -> None:
        self._current_platform = platform
        # update tab colors
        for plat, btn in self._platform_tabs.items():
            btn.configure(
                fg_color=_COLOR_CARD_HI if plat == platform else "transparent"
            )
        self._refresh_user_list()

    # ------------------------------------------------------------------ #
    # Search
    # ------------------------------------------------------------------ #
    def _on_search(self) -> None:
        self._search_query = self._search_entry.get().strip().lower()
        self._refresh_user_list()

    # ------------------------------------------------------------------ #
    # Build merged user list
    # ------------------------------------------------------------------ #
    def _get_filtered_users(self) -> list[tuple[str, int, str]]:
        """คืน list of (author_lower, msg_count, display_name) — filtered by platform + search"""
        mh = self.parent_app.message_history
        renames = self.parent_app.settings.user_renames
        all_authors = mh.all_authors()

        users = []
        for author_lower, entries in all_authors.items():
            # filter by platform
            if self._current_platform != "all":
                plats = {e.get("platform", "") for e in entries}
                if self._current_platform not in plats:
                    continue
            # filter by search (ทั้งชื่อเดิม + ชื่อใหม่)
            display_name = renames.get(author_lower, author_lower)
            if self._search_query:
                if (self._search_query not in author_lower
                        and self._search_query not in display_name.lower()):
                    continue
            msg_count = len(entries)
            users.append((author_lower, msg_count, display_name))

        # sort by msg_count desc
        users.sort(key=lambda x: x[1], reverse=True)
        return users

    # ------------------------------------------------------------------ #
    # User list rendering
    # ------------------------------------------------------------------ #
    def _update_selected_row_text(self):
        """update display name of selected row in-place (no rebuild)"""
        if self._selected_author is None:
            return
        renames = self.parent_app.settings.user_renames
        display = renames.get(self._selected_author, self._selected_author)
        # find the label in the list for this author
        for row in self._user_list_frame.winfo_children():
            for child in row.winfo_children():
                try:
                    # the first CTkLabel is the name label
                    if hasattr(child, 'configure') and child.cget('anchor') == 'w':
                        child.configure(text=display)
                        return
                except Exception:
                    pass

    def _refresh_user_list(self) -> None:
        """re-render user list — smooth (no flicker)"""
        # freeze visual updates during destroy+rebuild
        self._user_list_frame._parent_canvas.configure(width=0)
        for child in self._user_list_frame.winfo_children():
            child.destroy()

        users = self._get_filtered_users()
        if not users:
            ctk.CTkLabel(
                self._user_list_frame, text="(ยังไม่มีข้อมูล)",
                font=_font(13), text_color=_COLOR_TEXT_DIM,
            ).pack(pady=20)
            return

        for author_lower, msg_count, display_name in users:
            row = ctk.CTkFrame(self._user_list_frame, fg_color="transparent")
            row.pack(fill="x", padx=4, pady=1)
            is_selected = (self._selected_author == author_lower)
            bg = _COLOR_CARD_HI if is_selected else "transparent"
            row.configure(fg_color=bg)

            def on_enter(_e, r=row):
                if r.cget("fg_color") == "transparent":
                    r.configure(fg_color=_COLOR_BORDER)
            def on_leave(_e, r=row, sel=is_selected):
                r.configure(fg_color=_COLOR_CARD_HI if sel else "transparent")
            row.bind("<Enter>", on_enter)
            row.bind("<Leave>", on_leave)

            lbl = ctk.CTkLabel(
                row, text=display_name, width=180,
                font=_font(12, "bold"), text_color=_COLOR_TEXT, anchor="w",
            )
            lbl.pack(side="left", padx=(8, 4))
            ctk.CTkLabel(
                row, text=f"{msg_count}",
                font=_font(11), text_color=_COLOR_TEXT_DIM,
            ).pack(side="right", padx=(0, 8))

            # click → select
            for w in (row, lbl):
                w.bind("<Button-1>", lambda e, a=author_lower: self._select_user(a))

        # restore visual
        self._user_list_frame.update_idletasks()

    # ------------------------------------------------------------------ #
    # Detail panel
    # ------------------------------------------------------------------ #
    def _select_user(self, author_lower: str) -> None:
        self._selected_author = author_lower
        self._history_limit = 50
        # update highlight in-place (no full rebuild)
        for row in self._user_list_frame.winfo_children():
            # find which author this row is for
            is_sel = False
            for child in row.winfo_children():
                try:
                    if hasattr(child, 'cget') and child.cget('anchor') == 'w':
                        text = child.cget('text')
                        renames = self.parent_app.settings.user_renames
                        # check if this row matches selected author
                        for a, entries in self.parent_app.message_history.all_authors().items():
                            disp = renames.get(a, a)
                            if disp == text and a == author_lower:
                                is_sel = True
                                break
                except Exception:
                    pass
            row.configure(fg_color=_COLOR_CARD_HI if is_sel else "transparent")
            row._zebra_color = _COLOR_CARD_HI if is_sel else "transparent"
        # render detail (deferred to next tick = no flicker)
        self.after(10, self._render_detail)

    def _render_detail(self) -> None:
        """render detail panel — smooth update"""
        # batch destroy + rebuild in one frame
        self._detail_frame._parent_canvas.configure(width=0)
        for child in self._detail_frame.winfo_children():
            child.destroy()

        if self._selected_author is None:
            ctk.CTkLabel(
                self._detail_frame,
                text="← คลิกชื่อผู้ชมเพื่อดูรายละเอียด",
                font=_font(14), text_color=_COLOR_TEXT_DIM,
            ).pack(pady=60)
            return

        author_lower = self._selected_author
        renames = self.parent_app.settings.user_renames
        display_name = renames.get(author_lower, author_lower)
        is_renamed = author_lower in renames
        is_blocked = self.parent_app.text_filter.is_user_blocked(author_lower)

        # ── header ──
        hdr = ctk.CTkFrame(self._detail_frame, fg_color="transparent")
        hdr.pack(fill="x", padx=10, pady=(8, 4))
        ctk.CTkLabel(
            hdr, text=f"👤 {display_name}",
            font=_font(18, "bold"), text_color=_COLOR_TEXT,
        ).pack(side="left")
        if is_renamed:
            ctk.CTkLabel(
                hdr, text=f"(เดิม: {author_lower})",
                font=_font(12), text_color=_COLOR_TEXT_DIM,
            ).pack(side="left", padx=8)
        if is_blocked:
            ctk.CTkLabel(
                hdr, text="🚫 บล็อกอยู่",
                font=_font(11), text_color=_COLOR_DANGER,
            ).pack(side="left", padx=4)

        # ── action buttons ──
        btn_row = ctk.CTkFrame(self._detail_frame, fg_color="transparent")
        btn_row.pack(fill="x", padx=10, pady=(0, 8))
        ctk.CTkButton(
            btn_row, text="✏️ เปลี่ยนชื่อ", width=100, height=26,
            fg_color=_COLOR_ACCENT, hover_color=_COLOR_ACCENT_HOVER,
            text_color="#fff", font=_font(12),
            command=self._rename_user,
        ).pack(side="left", padx=(0, 4))
        ctk.CTkButton(
            btn_row, text="🚫 Block" if not is_blocked else "✅ Unblock",
            width=90, height=26,
            fg_color=_COLOR_DANGER if not is_blocked else _COLOR_SUCCESS,
            hover_color=_COLOR_DANGER_HOVER if not is_blocked else _COLOR_SUCCESS_HOVER,
            text_color="#fff", font=_font(12),
            command=self._toggle_block,
        ).pack(side="left", padx=4)
        # 🌐 บังคับแปล — แสดงเฉพาะโหมดแปลภาษา (เก็บค่าไว้ถ้าซ่อน)
        is_forced = author_lower in [u.lower() for u in getattr(self.parent_app.settings, "force_translate_users", [])]
        _translate_on = getattr(self.parent_app.settings, "auto_translate_enabled", False)
        if _translate_on:
            ctk.CTkButton(
                btn_row, text="🌐 บังคับแปล" if not is_forced else "🌐 ยกเลิกบังคับแปล",
                width=130, height=26,
                fg_color=_COLOR_INFO if not is_forced else _COLOR_DANGER,
                hover_color=_COLOR_INFO_HOVER if not is_forced else _COLOR_DANGER_HOVER,
                text_color="#fff", font=_font(12),
                command=self._toggle_force_translate,
            ).pack(side="left", padx=4)
        ctk.CTkButton(
            btn_row, text="🗑 ลบข้อมูล", width=90, height=26,
            fg_color=_COLOR_CARD_HI, hover_color=_COLOR_DANGER,
            text_color=_COLOR_TEXT_DIM, font=_font(12),
            command=self._delete_user,
        ).pack(side="left", padx=4)

        # ── stats ──
        mh = self.parent_app.message_history
        dt = self.parent_app.donate_tracker
        msg_count = mh.count(author_lower)
        visits = mh.visit_count(author_lower)
        platforms = mh.platforms(author_lower)
        plat_str = ", ".join(sorted(platforms)) if platforms else "-"

        stats_text = f"📊 {msg_count} คอมเม้น • {visits} ครั้งที่มารับชม • {plat_str}"
        ctk.CTkLabel(
            self._detail_frame, text=stats_text,
            font=_font(13), text_color=_COLOR_TEXT_DIM,
        ).pack(anchor="w", padx=10, pady=(0, 4))

        # ── donate stats ──
        donate = dt.get_user(author_lower)
        if donate:
            plat_filter = self._current_platform
            donate_lines = []
            for plat_key, fields in donate.items():
                if plat_key == "total_donate_count":
                    continue
                if plat_filter != "all" and plat_key != plat_filter:
                    continue
                parts = []
                for fk, fv in fields.items():
                    if isinstance(fv, (int, float)) and fv:
                        parts.append(f"{fv} {fk}")
                if parts:
                    donate_lines.append(f"  {plat_key}: {' • '.join(parts)}")
            if donate_lines:
                ctk.CTkLabel(
                    self._detail_frame, text="💸 การสนับสนุน",
                    font=_font(13, "bold"), text_color=_COLOR_HEADING,
                ).pack(anchor="w", padx=10, pady=(4, 0))
                for line in donate_lines:
                    ctk.CTkLabel(
                        self._detail_frame, text=line,
                        font=_font(12), text_color=_COLOR_TEXT,
                    ).pack(anchor="w", padx=20)

        # ── message history ──
        ctk.CTkLabel(
            self._detail_frame, text="── ประวัติข้อความ ──",
            font=_font(13, "bold"), text_color=_COLOR_ACCENT_2,
        ).pack(anchor="w", padx=10, pady=(8, 2))

        entries = mh.get(author_lower)
        # filter by platform
        if self._current_platform != "all":
            entries = [e for e in entries if e.get("platform") == self._current_platform]

        if not entries:
            ctk.CTkLabel(
                self._detail_frame, text="(ยังไม่มีประวัติ)",
                font=_font(13), text_color=_COLOR_TEXT_DIM,
            ).pack(pady=10)
        else:
            # entries เรียงเก่า→ใหม่ (จาก mh.get)
            # → เอา "ใหม่สุด N" มาแสดง โดยเรียงใหม่→เก่า (newest อยู่บนสุด)
            # กด Load more → แสดงเก่ากว่านั้นเพิ่ม (step ลึกขึ้นไปในอดีต)
            total = len(entries)
            take = min(self._history_limit, total)
            # slice ท้าย list = ใหม่สุด N, แล้ว reverse → ใหม่สุดอยู่บนสุด
            shown = list(reversed(entries[-take:]))
            self._history_container = ctk.CTkFrame(self._detail_frame, fg_color="transparent")
            self._history_container.pack(fill="x", padx=4, pady=2)
            for e in shown:
                self._render_history_entry(self._history_container, e)

            # load more button — แสดงถ้ายังมีของเก่ากว่าที่กำลังแสดง
            remaining = total - take
            if remaining > 0:
                self._load_more_btn = ctk.CTkButton(
                    self._detail_frame,
                    text=f"📜 โหลดเพิ่ม ({remaining} รายการที่เก่ากว่า)",
                    width=240, height=28,
                    fg_color=_COLOR_CARD_HI, hover_color=_COLOR_ACCENT,
                    text_color=_COLOR_TEXT_DIM, font=_font(12),
                    command=self._load_more,
                )
                self._load_more_btn.pack(pady=4)

            # export button
            ctk.CTkButton(
                self._detail_frame, text="📥 Export เป็น .md",
                width=160, height=28,
                fg_color=_COLOR_SUCCESS, hover_color=_COLOR_SUCCESS_HOVER,
                text_color="#fff", font=_font(12),
                command=self._export_md,
            ).pack(pady=4)

    def _render_history_entry(self, parent, entry: dict) -> None:
        """render 1 history entry"""
        ts_raw = entry.get("timestamp", "")
        try:
            dt = datetime.fromisoformat(ts_raw)
            ts = dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            ts = ts_raw

        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=1)
        ctk.CTkLabel(
            row, text=f"[{ts}]", width=140,
            font=_font(11), text_color=_COLOR_TEXT_DIM, anchor="w",
        ).pack(side="left")

        if entry.get("is_banned"):
            ctk.CTkLabel(
                row, text="🚫 " + entry.get("banned_original", entry.get("text", "")),
                font=_font(12), text_color=_COLOR_DANGER, anchor="w",
            ).pack(side="left", fill="x", expand=True, padx=4)
        else:
            text = entry.get("text", "")
            plat = entry.get("platform", "")
            plat_tag = f"[{plat}] " if plat and self._current_platform == "all" else ""
            ctk.CTkLabel(
                row, text=plat_tag + (text or "(ไม่มีข้อความ)"),
                font=_font(12), text_color=_COLOR_TEXT, anchor="w",
                wraplength=400,
            ).pack(side="left", fill="x", expand=True, padx=4)

    # ------------------------------------------------------------------ #
    # Actions
    # ------------------------------------------------------------------ #
    def _load_more(self) -> None:
        self._history_limit += 50
        self._render_detail()

    def _rename_user(self) -> None:
        """rename dialog — เพิ่ม checkbox ให้ TTS อ่านชื่อนี้ + ปุ่มลบการเปลี่ยนชื่อ"""
        author_lower = self._selected_author
        if not author_lower:
            return
        win = ctk.CTkToplevel(self)
        win.title("เปลี่ยนชื่อ")
        win.geometry("340x240")
        win.configure(fg_color=_COLOR_BG)
        win.transient(self)
        win.grab_set()
        win.lift()
        win.focus_force()

        ctk.CTkLabel(
            win, text=f"เปลี่ยนชื่อ: {author_lower}",
            font=_font(14, "bold"), text_color=_COLOR_TEXT,
        ).pack(pady=(16, 8))
        entry = ctk.CTkEntry(win, width=260, height=32, font=_font(14))
        current = self.parent_app.settings.user_renames.get(author_lower, author_lower)
        entry.insert(0, current)
        entry.pack(pady=4)
        entry.focus_set()

        # checkbox: ให้ TTS อ่านชื่อนี้
        _tts_renames = getattr(self.parent_app.settings, "tts_renames", {})
        read_tts_var = ctk.BooleanVar(value=author_lower in _tts_renames)
        ctk.CTkCheckBox(
            win, text="🔊 ให้ TTS อ่านชื่อนี้",
            variable=read_tts_var, font=_font(12),
        ).pack(pady=(8, 4))

        def do_rename():
            new = entry.get().strip()
            if new and new != author_lower:
                self.parent_app.settings.user_renames[author_lower] = new
                from settings import save_settings
                save_settings(self.parent_app.settings)
                self.parent_app._rerender_author_rows(author_lower)
            # บันทึก tts_renames
            if not hasattr(self.parent_app.settings, "tts_renames"):
                self.parent_app.settings.tts_renames = {}
            if read_tts_var.get():
                self.parent_app.settings.tts_renames[author_lower] = new or current
            else:
                self.parent_app.settings.tts_renames.pop(author_lower, None)
            from settings import save_settings
            save_settings(self.parent_app.settings)
            win.destroy()
            # smooth update — only update label text, don't rebuild list
            self._update_selected_row_text()
            self._render_detail()

        def do_remove_rename():
            """ลบการเปลี่ยนชื่อ → กลับเป็นชื่อเดิม"""
            self.parent_app.settings.user_renames.pop(author_lower, None)
            # ลบ tts_rename ด้วย
            if hasattr(self.parent_app.settings, "tts_renames"):
                self.parent_app.settings.tts_renames.pop(author_lower, None)
            from settings import save_settings
            save_settings(self.parent_app.settings)
            self.parent_app._rerender_author_rows(author_lower)
            win.destroy()
            self._update_selected_row_text()
            self._render_detail()

        btn_row = ctk.CTkFrame(win, fg_color="transparent")
        btn_row.pack(pady=8)
        ctk.CTkButton(
            btn_row, text="ตกลง", width=90, height=30,
            fg_color=_COLOR_SUCCESS, hover_color=_COLOR_SUCCESS_HOVER,
            font=_font(13, "bold"), command=do_rename,
        ).pack(side="left", padx=4)
        # ปุ่มลบการเปลี่ยนชื่อ (แสดงเฉพาะเมื่อเคยเปลี่ยนชื่อ)
        is_renamed = author_lower in self.parent_app.settings.user_renames
        if is_renamed:
            ctk.CTkButton(
                btn_row, text="↩️ ลบการเปลี่ยนชื่อ", width=130, height=30,
                fg_color=_COLOR_DANGER, hover_color=_COLOR_DANGER_HOVER,
                font=_font(12), command=do_remove_rename,
            ).pack(side="left", padx=4)
        ctk.CTkButton(
            btn_row, text="ยกเลิก", width=90, height=30,
            fg_color=_COLOR_CARD_HI, hover_color=_COLOR_ACCENT,
            font=_font(13), command=win.destroy,
        ).pack(side="left", padx=4)

    def _toggle_block(self) -> None:
        """block/unblock user"""
        author_lower = self._selected_author
        if not author_lower:
            return
        tf = self.parent_app.text_filter
        display = self.parent_app.settings.user_renames.get(author_lower, author_lower)
        if tf.is_user_blocked(author_lower):
            tf.remove_blocked_user(display)
        else:
            tf.add_blocked_user(display, hide_overlay=False)
        tf.rebuild()
        self.parent_app.settings.apply_text_filter(tf)
        from settings import save_settings
        save_settings(self.parent_app.settings)
        # smooth — only rebuild detail, not list
        self._render_detail()

    def _toggle_force_translate(self) -> None:
        """toggle force_translate_users — บังคับแปลทุกข้อความของ user นี้"""
        author_lower = self._selected_author
        if not author_lower:
            return
        s = self.parent_app.settings
        forced = [u.lower() for u in getattr(s, "force_translate_users", [])]
        if author_lower in forced:
            # ยกเลิกบังคับแปล
            s.force_translate_users = [u for u in s.force_translate_users if u.lower() != author_lower]
        else:
            # เพิ่มบังคับแปล (เก็บ author_lower เพื่อ match กับ msg.author.lower())
            s.force_translate_users.append(author_lower)
        from settings import save_settings
        save_settings(s)
        # sync เข้า pipeline config (สำคัญ! ไม่งั้น pipeline ยังใช้ค่าเก่า)
        self._sync_pipeline_translate_config()
        self._render_detail()

    def _sync_pipeline_translate_config(self) -> None:
        """อัปเดต pipeline.config.force_translate_users ให้ตรงกับ settings ปัจจุบัน"""
        try:
            pipeline = getattr(self.parent_app, "pipeline", None)
            if pipeline is not None and hasattr(pipeline, "config"):
                pipeline.config.force_translate_users = list(
                    getattr(self.parent_app.settings, "force_translate_users", [])
                )
        except Exception:
            pass

    def _delete_user(self) -> None:
        """ลบข้อมูล user — find + remove row in-place + clear detail"""
        from tkinter import messagebox
        author_lower = self._selected_author
        if not author_lower:
            return
        if not messagebox.askyesno(
            "ยืนยันการลบ",
            f"จะลบข้อมูลทั้งหมดของ {author_lower}?\n(ข้อความ + การสนับสนุน)\nไม่สามารถยกเลิกได้",
        ):
            return
        # delete from data stores
        with self.parent_app.message_history._lock:
            self.parent_app.message_history._data.pop(author_lower, None)
        self.parent_app.message_history._save_async()
        self.parent_app.donate_tracker.clear_user(author_lower)
        # smooth — remove the row widget, don't rebuild entire list
        for row in self._user_list_frame.winfo_children():
            # check if this row belongs to the deleted author
            for child in row.winfo_children():
                try:
                    if hasattr(child, 'cget') and child.cget('anchor') == 'w':
                        # this is the name label — check if it matches
                        pass
                except Exception:
                    pass
            try:
                row.destroy()
                break  # only delete one row
            except Exception:
                pass
        self._selected_author = None
        # render empty detail without flicker
        for child in self._detail_frame.winfo_children():
            child.destroy()
        ctk.CTkLabel(
            self._detail_frame,
            text="← คลิกชื่อผู้ชมเพื่อดูรายละเอียด",
            font=_font(14), text_color=_COLOR_TEXT_DIM,
        ).pack(pady=60)

    def _export_md(self) -> None:
        """export user history เป็น .md"""
        from tkinter import filedialog, messagebox
        author_lower = self._selected_author
        if not author_lower:
            return
        renames = self.parent_app.settings.user_renames
        display = renames.get(author_lower, author_lower)

        path = filedialog.asksaveasfilename(
            title="Export เป็น .md",
            defaultextension=".md",
            initialfile=f"{author_lower}_history.md",
            filetypes=[("Markdown", "*.md"), ("All files", "*.*")],
        )
        if not path:
            return

        mh = self.parent_app.message_history
        dt = self.parent_app.donate_tracker
        entries = mh.get(author_lower)
        donate = dt.get_user(author_lower)
        visits = mh.visit_count(author_lower)

        lines = [
            f"# {display}",
            f"",
            f"**ชื่อเดิม:** {author_lower}",
            f"**จำนวนข้อความ:** {len(entries)}",
            f"**จำนวนครั้งที่มารับชม:** {visits}",
            f"",
        ]
        if donate:
            lines.append("## การสนับสนุน")
            for plat, fields in donate.items():
                if plat == "total_donate_count":
                    continue
                parts = [f"{fv} {fk}" for fk, fv in fields.items() if isinstance(fv, (int, float)) and fv]
                if parts:
                    lines.append(f"- **{plat}:** {' • '.join(parts)}")
            lines.append("")

        lines.append("## ประวัติข้อความ")
        for e in entries:
            ts = e.get("timestamp", "")
            text = e.get("text", "")
            plat = e.get("platform", "")
            if e.get("is_banned"):
                text = f"~~{e.get('banned_original', text)}~~ *(ถูกซ่อน)*"
            lines.append(f"- `{ts}` [{plat}] {text}")

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            messagebox.showinfo("Export สำเร็จ", f"บันทึกไปที่:\n{path}")
        except Exception as exc:
            messagebox.showerror("Export ไม่ได้", str(exc))
