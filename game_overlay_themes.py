"""game_overlay_themes.py — CSS theme presets สำหรับ Game Overlay

20 themes:
  - default   → ไร้การปรุงแต่ง (CSS ว่าง — ใช้ค่า settings ล้วน)
  - neon      → glow pulse + สีม่วง neon
  - glass     → backdrop-blur glassmorphism
  - cute      → pink/soft + bounce
  - minimal   → fade เรียบ อ่านง่าย
  - aurora    → แสงออโรร่าเขียว-ม่วง
  - sunset    → สีส้ม-ชมพูยามอาทิตย์ตก
  - ocean     → ฟ้า-น้ำเงินทะเลลึก
  - forest    → เขียวป่า
  - royal     → ทอง-ม่วงราชา
  - cyberpunk → ส้ม-ฟ้า neon ไซเบอร์
  - cherry    → ซากุระชมพู
  - galaxy    → ดำ-ม่วงดารา
  - mint      → เขียวมิ้นต์สด
  - peach     → พีชพาสเทล
  - lavender  → ม่วงลาเวนเดอร์
  - crimson   → แดงเข้ม
  - slate     → เทาสแลต
  - gold      → ทองหรูหรา
  - ice       → น้ำแข็งฟ้าขาว
  - custom    → ใช้ game_overlay_custom_css
"""
from __future__ import annotations


def _t(label: str, css: str, anim: str = "fade") -> dict:
    """helper สร้าง theme entry"""
    return {"label": label, "css": css, "default_animation": anim}


THEMES: dict[str, dict] = {
    # ── Default (ไร้การปรุงแต่ง) ──
    "default": _t("⚪ Default (ไร้การปรุงแต่ง)", ""),

    # ── Neon ──
    "neon": _t("🌈 Neon", """
:root {
  --box-bg: rgba(20, 10, 40, 0.55) !important;
  --box-border: 1px solid rgba(168, 85, 247, 0.4) !important;
  --box-shadow: 0 0 20px rgba(124, 58, 237, 0.45), 0 4px 12px rgba(0,0,0,0.4) !important;
  --box-glow: rgba(124, 58, 237, 0.7) !important;
  --box-radius: 12px !important;
  --text-shadow: 0 0 8px rgba(168, 85, 247, 0.8), 0 1px 3px rgba(0,0,0,0.9) !important;
}
.msg .author { text-shadow: 0 0 6px currentColor; }
""", "glow"),

    # ── Glass ──
    "glass": _t("🪟 Glass", """
:root {
  --box-bg: rgba(255, 255, 255, 0.08) !important;
  --box-border: 1px solid rgba(255, 255, 255, 0.18) !important;
  --box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3) !important;
  --box-blur: 12px !important;
  --box-radius: 16px !important;
  --text-shadow: 0 1px 2px rgba(0,0,0,0.6) !important;
}
.msg { backdrop-filter: blur(var(--box-blur)) saturate(180%); -webkit-backdrop-filter: blur(var(--box-blur)) saturate(180%); }
.msg .author { color: #fff !important; text-shadow: 0 0 4px rgba(255,255,255,0.3); }
""", "glassy"),

    # ── Cute ──
    "cute": _t("🌸 Cute", """
:root {
  --box-bg: rgba(255, 192, 203, 0.25) !important;
  --box-border: 2px solid rgba(255, 105, 180, 0.6) !important;
  --box-shadow: 0 4px 16px rgba(255, 105, 180, 0.35) !important;
  --box-glow: rgba(255, 105, 180, 0.6) !important;
  --box-radius: 20px !important;
  --text-color: #fff5f8 !important;
  --text-shadow: 0 1px 3px rgba(255, 105, 180, 0.6) !important;
}
.msg .author { color: #ff6b9d !important; text-shadow: 0 0 6px rgba(255, 105, 180, 0.5); }
.msg { border-style: dashed !important; }
""", "bounce"),

    # ── Minimal ──
    "minimal": _t("⬛ Minimal", """
:root {
  --box-bg: rgba(0, 0, 0, 0.65) !important;
  --box-border: none !important;
  --box-shadow: none !important;
  --box-radius: 4px !important;
  --text-shadow: 0 1px 2px rgba(0,0,0,0.8) !important;
}
.msg { backdrop-filter: none; -webkit-backdrop-filter: none; }
""", "fade"),

    # ── Aurora ──
    "aurora": _t("🌌 Aurora", """
:root {
  --box-bg: rgba(16, 33, 29, 0.55) !important;
  --box-border: 1px solid rgba(110, 231, 183, 0.4) !important;
  --box-shadow: 0 0 18px rgba(110, 231, 183, 0.4), 0 0 30px rgba(167, 139, 250, 0.3) !important;
  --box-glow: rgba(110, 231, 183, 0.6) !important;
  --box-radius: 14px !important;
  --text-shadow: 0 0 6px rgba(110, 231, 183, 0.5) !important;
}
.msg .author { color: #6ee7b7 !important; }
""", "glow"),

    # ── Sunset ──
    "sunset": _t("🌅 Sunset", """
:root {
  --box-bg: rgba(60, 20, 30, 0.55) !important;
  --box-border: 1px solid rgba(251, 146, 60, 0.5) !important;
  --box-shadow: 0 0 18px rgba(251, 146, 60, 0.4), 0 4px 12px rgba(0,0,0,0.4) !important;
  --box-glow: rgba(251, 146, 60, 0.7) !important;
  --box-radius: 14px !important;
  --text-shadow: 0 0 6px rgba(251, 146, 60, 0.5) !important;
}
.msg .author { color: #fb923c !important; }
""", "neon_pulse"),

    # ── Ocean ──
    "ocean": _t("🌊 Ocean", """
:root {
  --box-bg: rgba(8, 25, 50, 0.6) !important;
  --box-border: 1px solid rgba(59, 130, 246, 0.4) !important;
  --box-shadow: 0 4px 18px rgba(59, 130, 246, 0.35) !important;
  --box-blur: 6px !important;
  --box-radius: 14px !important;
  --text-shadow: 0 0 5px rgba(96, 165, 250, 0.4) !important;
}
.msg { backdrop-filter: blur(var(--box-blur)); -webkit-backdrop-filter: blur(var(--box-blur)); }
.msg .author { color: #60a5fa !important; }
""", "slide_up"),

    # ── Forest ──
    "forest": _t("🌲 Forest", """
:root {
  --box-bg: rgba(20, 35, 25, 0.6) !important;
  --box-border: 1px solid rgba(34, 197, 94, 0.4) !important;
  --box-shadow: 0 4px 12px rgba(0,0,0,0.4) !important;
  --box-radius: 10px !important;
  --text-shadow: 0 1px 3px rgba(0,0,0,0.8) !important;
}
.msg .author { color: #4ade80 !important; }
""", "fade"),

    # ── Royal ──
    "royal": _t("👑 Royal", """
:root {
  --box-bg: rgba(40, 25, 60, 0.6) !important;
  --box-border: 2px solid rgba(250, 204, 21, 0.5) !important;
  --box-shadow: 0 4px 16px rgba(0,0,0,0.5), 0 0 14px rgba(250, 204, 21, 0.3) !important;
  --box-glow: rgba(250, 204, 21, 0.6) !important;
  --box-radius: 12px !important;
  --text-shadow: 0 0 4px rgba(250, 204, 21, 0.3) !important;
}
.msg .author { color: #fbbf24 !important; font-weight: 700; }
""", "card_flip"),

    # ── Cyberpunk ──
    "cyberpunk": _t("🤖 Cyberpunk", """
:root {
  --box-bg: rgba(20, 10, 10, 0.65) !important;
  --box-border: 1px solid rgba(255, 176, 0, 0.6) !important;
  --box-shadow: 0 0 18px rgba(0, 255, 255, 0.5), 0 0 30px rgba(255, 176, 0, 0.3) !important;
  --box-glow: rgba(0, 255, 255, 0.7) !important;
  --box-radius: 0px !important;
  --text-shadow: 0 0 4px rgba(0, 255, 255, 0.6) !important;
}
.msg .author { color: #00ffff !important; text-shadow: 0 0 6px #00ffff; }
.msg { clip-path: polygon(0 0, 100% 0, 100% calc(100% - 8px), calc(100% - 8px) 100%, 0 100%); }
""", "neon_pulse"),

    # ── Cherry ──
    "cherry": _t("🌸 Cherry", """
:root {
  --box-bg: rgba(255, 220, 230, 0.4) !important;
  --box-border: 1px solid rgba(244, 114, 182, 0.5) !important;
  --box-shadow: 0 4px 14px rgba(244, 114, 182, 0.3) !important;
  --box-radius: 18px !important;
  --text-color: #4a1a2a !important;
  --text-shadow: 0 1px 2px rgba(255,255,255,0.5) !important;
}
.msg .author { color: #db2777 !important; }
""", "bounce"),

    # ── Galaxy ──
    "galaxy": _t("✨ Galaxy", """
:root {
  --box-bg: rgba(15, 10, 40, 0.6) !important;
  --box-border: 1px solid rgba(168, 85, 247, 0.4) !important;
  --box-shadow: 0 0 25px rgba(124, 58, 237, 0.5), inset 0 0 20px rgba(59, 130, 246, 0.2) !important;
  --box-glow: rgba(124, 58, 237, 0.6) !important;
  --box-radius: 14px !important;
  --text-shadow: 0 0 5px rgba(255,255,255,0.4) !important;
}
.msg .author { color: #c4b5fd !important; text-shadow: 0 0 8px #a855f7; }
""", "glow"),

    # ── Mint ──
    "mint": _t("🌿 Mint", """
:root {
  --box-bg: rgba(220, 252, 231, 0.5) !important;
  --box-border: 1px solid rgba(34, 197, 94, 0.4) !important;
  --box-shadow: 0 2px 10px rgba(34, 197, 94, 0.2) !important;
  --box-radius: 12px !important;
  --text-color: #14532d !important;
  --text-shadow: 0 1px 2px rgba(255,255,255,0.4) !important;
}
.msg .author { color: #16a34a !important; }
""", "slide_up"),

    # ── Peach ──
    "peach": _t("🍑 Peach", """
:root {
  --box-bg: rgba(255, 237, 213, 0.55) !important;
  --box-border: 1px solid rgba(251, 146, 60, 0.4) !important;
  --box-shadow: 0 2px 10px rgba(251, 146, 60, 0.2) !important;
  --box-radius: 16px !important;
  --text-color: #7c2d12 !important;
  --text-shadow: 0 1px 2px rgba(255,255,255,0.4) !important;
}
.msg .author { color: #c2410c !important; }
""", "pop"),

    # ── Lavender ──
    "lavender": _t("💜 Lavender", """
:root {
  --box-bg: rgba(237, 233, 254, 0.5) !important;
  --box-border: 1px solid rgba(139, 92, 246, 0.4) !important;
  --box-shadow: 0 2px 12px rgba(139, 92, 246, 0.25) !important;
  --box-radius: 14px !important;
  --text-color: #3b0764 !important;
  --text-shadow: 0 1px 2px rgba(255,255,255,0.4) !important;
}
.msg .author { color: #7c3aed !important; }
""", "fade"),

    # ── Crimson ──
    "crimson": _t("🔴 Crimson", """
:root {
  --box-bg: rgba(50, 10, 15, 0.65) !important;
  --box-border: 1px solid rgba(220, 38, 38, 0.5) !important;
  --box-shadow: 0 4px 14px rgba(220, 38, 38, 0.4), 0 0 18px rgba(220, 38, 38, 0.3) !important;
  --box-glow: rgba(220, 38, 38, 0.6) !important;
  --box-radius: 8px !important;
  --text-shadow: 0 0 4px rgba(220, 38, 38, 0.4) !important;
}
.msg .author { color: #ef4444 !important; text-shadow: 0 0 6px #dc2626; }
""", "neon_pulse"),

    # ── Slate ──
    "slate": _t("🪨 Slate", """
:root {
  --box-bg: rgba(30, 41, 59, 0.7) !important;
  --box-border: 1px solid rgba(100, 116, 139, 0.5) !important;
  --box-shadow: 0 4px 12px rgba(0,0,0,0.4) !important;
  --box-radius: 6px !important;
  --text-shadow: 0 1px 2px rgba(0,0,0,0.7) !important;
}
.msg .author { color: #cbd5e1 !important; }
""", "fade"),

    # ── Gold ──
    "gold": _t("🏆 Gold", """
:root {
  --box-bg: rgba(45, 35, 10, 0.65) !important;
  --box-border: 2px solid rgba(250, 204, 21, 0.6) !important;
  --box-shadow: 0 0 20px rgba(250, 204, 21, 0.4), 0 4px 12px rgba(0,0,0,0.4) !important;
  --box-glow: rgba(250, 204, 21, 0.7) !important;
  --box-radius: 10px !important;
  --text-color: #fef3c7 !important;
  --text-shadow: 0 0 5px rgba(250, 204, 21, 0.4) !important;
}
.msg .author { color: #fbbf24 !important; text-shadow: 0 0 6px #facc15; }
""", "glow"),

    # ── Ice ──
    "ice": _t("❄️ Ice", """
:root {
  --box-bg: rgba(219, 234, 254, 0.5) !important;
  --box-border: 1px solid rgba(147, 197, 253, 0.6) !important;
  --box-shadow: 0 0 14px rgba(147, 197, 253, 0.4) !important;
  --box-radius: 14px !important;
  --text-color: #1e3a8a !important;
  --text-shadow: 0 1px 2px rgba(255,255,255,0.5) !important;
}
.msg .author { color: #2563eb !important; }
""", "glassy"),

    # ════════════════════════════════════════════════════════════════
    # ── Theme กรอบลูกเล่น (frame shapes / decorations) ──
    # ════════════════════════════════════════════════════════════════

    # ── Comic Speech (กรอบคำพูดการ์ตูน + หาง) ──
    "comic": _t("🗨️ Comic Speech (กรอบคำพูดการ์ตูน)", """
.msg-bg {
  background: #ffffff !important;
  border: 3px solid #1a1a1a !important;
  border-radius: 18px !important;
  box-shadow: 4px 4px 0 #1a1a1a !important;
}
.msg::before {
  content: ""; position: absolute; left: 18px; bottom: -14px;
  width: 0; height: 0; pointer-events: none;
  border: 12px solid transparent; border-top-color: #1a1a1a; border-bottom: 0;
}
.msg .author { color: #d63384 !important; text-shadow: none !important; }
.msg .text { color: #1a1a1a !important; text-shadow: none !important; }
""", "pop"),

    # ── Retro RPG (กรอบ dialog box เกม Famicom คลาสสิก — มุม pixel staircase) ──
    "retro": _t("🎮 Retro RPG (dialog box Famicom)", """
.msg {
  font-family: "Courier New", monospace !important;
  /* มุม pixel staircase 4 มุม — เหมือนกรอบเกม Famicom (ขั้นละ 4px) */
  clip-path: polygon(
    4px 4px, 4px 2px, 6px 2px, 6px 0,
    calc(100% - 6px) 0, calc(100% - 6px) 2px, calc(100% - 4px) 2px, calc(100% - 4px) 4px,
    100% 4px,
    100% calc(100% - 4px), calc(100% - 4px) calc(100% - 4px), calc(100% - 4px) calc(100% - 2px), calc(100% - 6px) calc(100% - 2px), calc(100% - 6px) 100%,
    6px 100%, 6px calc(100% - 2px), 4px calc(100% - 2px), 4px calc(100% - 4px),
    0 calc(100% - 4px),
    0 4px
  ) !important;
}
.msg-bg {
  background: #000000 !important;
  border: 4px solid #ffffff !important;
  border-radius: 0 !important;
}
/* ▼ กระพริบมุมขวาล่าง — เหมือน cursor รอกดไปต่อ */
.msg::before {
  content: "▼"; position: absolute; right: 8px; bottom: 4px;
  color: #ffffff !important; font-size: 0.9em; line-height: 1;
  animation: retro-cursor 0.9s steps(2) infinite;
}
@keyframes retro-cursor { 0%, 50% { opacity: 1; } 51%, 100% { opacity: 0; } }
.msg .author { color: #ffffff !important; text-shadow: 2px 2px 0 #000000 !important; font-weight: 700 !important; }
.msg .text { color: #ffffff !important; text-shadow: 2px 2px 0 #000000 !important; padding-right: 16px !important; }
""", "fade"),

    # ── Pixel Block (กรอบบล็อกพิกเซล มุมบันได) ──
    "pixel": _t("🧱 Pixel Block (มุมบันไดพิกเซล)", """
.msg {
  clip-path: polygon(0 4px, 4px 4px, 4px 0, calc(100% - 4px) 0, calc(100% - 4px) 4px, 100% 4px, 100% calc(100% - 4px), calc(100% - 4px) calc(100% - 4px), calc(100% - 4px) 100%, 4px 100%, 4px calc(100% - 4px), 0 calc(100% - 4px)) !important;
}
.msg-bg {
  background: #2d1b69 !important;
  border: 3px solid #9d4edd !important;
  border-radius: 0 !important;
}
.msg .author { color: #c77dff !important; text-shadow: 2px 2px 0 #240046 !important; }
.msg .text { color: #e0aaff !important; }
""", "slide_up"),

    # ── Sticky Note (กระดาษโน้ตเหลือง) ──
    "sticky": _t("📝 Sticky Note (กระดาษโน้ต)", """
.msg {
  font-family: "Comic Sans MS", "Segoe Print", cursive !important;
}
.msg-bg {
  background: #fff9c4 !important;
  border: none !important;
  border-radius: 2px !important;
  box-shadow: 2px 4px 8px rgba(0,0,0,0.3) !important;
}
.msg .author { color: #c62828 !important; text-shadow: none !important; }
.msg .text { color: #4e342e !important; text-shadow: none !important; }
""", "slide_up"),

    # ── Terminal (จอคอมโบราณ) ──
    "terminal": _t("💻 Terminal (จอคอมเขียว)", """
.msg {
  font-family: "Consolas", "Courier New", monospace !important;
}
.msg-bg {
  background: #0a0a0a !important;
  border: 1px solid #00ff00 !important;
  border-radius: 0 !important;
  box-shadow: 0 0 8px rgba(0,255,0,0.4) !important;
}
.msg .text { color: #00ff00 !important; text-shadow: 0 0 4px rgba(0,255,0,0.6) !important; }
.msg .author { color: #7fff00 !important; text-shadow: 0 0 4px rgba(127,255,0,0.6) !important; }
.msg .author::before { content: "> "; color: #00ff00; }
""", "fade"),

    # ── Shield Frame (กรอบโล่หกเหลี่ยม) ──
    "shield": _t("🛡️ Shield Frame (กรอบโล่)", """
.msg {
  clip-path: polygon(10px 0, calc(100% - 10px) 0, 100% 50%, calc(100% - 10px) 100%, 10px 100%, 0 50%) !important;
  filter: drop-shadow(0 0 6px rgba(255,215,0,0.6)) !important;
}
.msg-bg {
  background: rgba(30, 40, 60, 0.85) !important;
  border: none !important;
  border-radius: 0 !important;
}
.msg .author { color: #ffd700 !important; text-shadow: 1px 1px 2px #000 !important; }
.msg .text { color: #f0f0f0 !important; }
""", "card_flip"),

    # ── Neon Pill (แคปซูลมนโค้งเต็ม) ──
    "neon-pill": _t("💊 Neon Pill (แคปซูลนีออน)", """
.msg-bg {
  background: rgba(20, 5, 30, 0.7) !important;
  border: 2px solid #ff00ff !important;
  border-radius: 50px !important;
  box-shadow: 0 0 15px #ff00ff, inset 0 0 10px rgba(255,0,255,0.3) !important;
}
.msg .author { color: #ff66ff !important; text-shadow: 0 0 6px #ff00ff !important; }
.msg .text { color: #ffffff !important; text-shadow: 0 0 4px rgba(255,0,255,0.5) !important; }
""", "glow"),

    # ── Scroll (กรอบม้วนคัมภีร์) ──
    "scroll": _t("📜 Scroll (ม้วนคัมภีร์)", """
.msg-bg {
  background: linear-gradient(90deg, #8b6914 0%, #8b6914 6px, #f4e4bc 6px, #f4e4bc calc(100% - 6px), #8b6914 calc(100% - 6px)) !important;
  border: 1px solid #5c4515 !important;
  border-radius: 0 !important;
  box-shadow: 0 2px 6px rgba(0,0,0,0.3) !important;
}
.msg .author { color: #6b3410 !important; text-shadow: none !important; }
.msg .text { color: #3d2b0f !important; text-shadow: none !important; }
""", "fade"),

    # ── Ticket (ตั๋วขอบหยัก) ──
    "ticket": _t("🎫 Ticket (ตั๋วขอบหยัก)", """
.msg-bg {
  background: #e91e63 !important;
  border: 2px dashed #ffffff !important;
  border-radius: 4px !important;
  box-shadow: 0 4px 10px rgba(0,0,0,0.3) !important;
}
.msg .author { color: #ffe082 !important; text-shadow: 1px 1px 2px rgba(0,0,0,0.4) !important; }
.msg .text { color: #ffffff !important; text-shadow: 1px 1px 2px rgba(0,0,0,0.4) !important; }
""", "bounce"),

    # ── Game Card (การ์ดเกมขอบทองคู่) ──
    "gamecard": _t("🃏 Game Card (การ์ดเกม)", """
.msg-bg {
  background: linear-gradient(145deg, #2a2a4a 0%, #1a1a2e 100%) !important;
  border: 2px solid #ffd700 !important;
  border-radius: 12px !important;
  box-shadow: 0 0 0 1px #b8860b, 0 4px 12px rgba(0,0,0,0.6) !important;
}
.msg .author { color: #ffd700 !important; text-shadow: 0 0 4px rgba(255,215,0,0.5) !important; }
.msg .text { color: #f0f0f0 !important; }
""", "card_flip"),

    # ════════════════════════════════════════════════════════════════
    # ── Theme กรอบลูกเล่น เพิ่มเติม (วงที่ 2) ──
    # ════════════════════════════════════════════════════════════════

    # ── Hologram (โฮโลแกรมมีเส้น scanline) ──
    "hologram": _t("🔮 Hologram (โฮโลแกรม)", """
.msg {
  position: relative !important;
  overflow: hidden !important;
}
.msg-bg {
  background: linear-gradient(180deg, rgba(0,80,120,0.55), rgba(0,120,160,0.4)) !important;
  border: 1px solid #00e5ff !important;
  border-radius: 4px !important;
  box-shadow: 0 0 12px rgba(0,229,255,0.5) !important;
}
.msg::before {
  content: ""; position: absolute; inset: 0; pointer-events: none;
  background: repeating-linear-gradient(0deg, transparent 0, transparent 3px, rgba(0,229,255,0.08) 3px, rgba(0,229,255,0.08) 4px);
}
.msg .author { color: #00e5ff !important; text-shadow: 0 0 6px #00e5ff !important; }
.msg .text { color: #b3f5ff !important; text-shadow: 0 0 3px rgba(0,229,255,0.5) !important; }
""", "glassy"),

    # ── Graffiti (สpray paint เอียง outline) ──
    "graffiti": _t("🎨 Graffiti (สpray paint)", """
.msg {
  transform: rotate(-1.5deg) !important;
}
.msg-bg {
  background: #1a1a1a !important;
  border: none !important;
  border-radius: 6px !important;
  box-shadow: 3px 3px 0 #ff006e, 6px 6px 0 #8338ec !important;
}
.msg .author {
  color: #ff006e !important;
  text-shadow: 2px 2px 0 #8338ec, -1px -1px 0 #3a86ff !important;
  font-weight: 900 !important;
}
.msg .text { color: #ffbe0b !important; text-shadow: 1px 1px 0 #1a1a1a !important; }
""", "pop"),

    # ── Wooden (กรอบไม้) ──
    "wooden": _t("🪵 Wooden (กรอบไม้)", """
.msg-bg {
  background: #d4a373 !important;
  border: 4px solid #6b3410 !important;
  border-radius: 6px !important;
  box-shadow: inset 0 0 0 2px #a0522d, 0 3px 6px rgba(0,0,0,0.4) !important;
}
.msg .author { color: #3d2b0f !important; text-shadow: 1px 1px 0 #f4e4bc !important; }
.msg .text { color: #3d2b0f !important; text-shadow: none !important; }
""", "slide_up"),

    # ── Bubble (ฟองน้ำโปร่งกลม) ──
    "bubble": _t("🫧 Bubble (ฟองน้ำโปร่ง)", """
.msg-bg {
  background: radial-gradient(circle at 30% 30%, rgba(255,255,255,0.4), rgba(150,200,255,0.25)) !important;
  border: 2px solid rgba(255,255,255,0.6) !important;
  border-radius: 50px !important;
  box-shadow: inset 4px 4px 8px rgba(255,255,255,0.4), inset -4px -4px 8px rgba(0,100,200,0.2) !important;
}
.msg .author { color: #ffffff !important; text-shadow: 0 0 4px rgba(100,150,255,0.8) !important; }
.msg .text { color: #ffffff !important; text-shadow: 0 1px 2px rgba(0,50,100,0.6) !important; }
""", "bounce"),

    # ── Stamp (แสตมป์ขอบหยัก) ──
    "stamp": _t("📮 Stamp (แสตมป์)", """
.msg-bg {
  background: #fff5e6 !important;
  border: 3px dashed #c0392b !important;
  border-radius: 0 !important;
  box-shadow: 2px 2px 0 rgba(0,0,0,0.2) !important;
}
.msg .author { color: #c0392b !important; text-shadow: none !important; font-weight: 900 !important; }
.msg .text { color: #2c1810 !important; text-shadow: none !important; }
""", "fade"),

    # ── Crystal (คริสตัลมุมเอียง) ──
    "crystal": _t("💎 Crystal (คริสตัล)", """
.msg {
  clip-path: polygon(8px 0, 100% 0, 100% calc(100% - 8px), calc(100% - 8px) 100%, 0 100%, 0 8px) !important;
}
.msg-bg {
  background: linear-gradient(135deg, rgba(180,220,255,0.35), rgba(220,200,255,0.25)) !important;
  border: 1px solid rgba(255,255,255,0.7) !important;
  border-radius: 0 !important;
  box-shadow: 4px 4px 12px rgba(100,150,255,0.4) !important;
}
.msg .author { color: #6c5ce7 !important; text-shadow: 0 0 4px rgba(255,255,255,0.8) !important; }
.msg .text { color: #2d3436 !important; text-shadow: 0 1px 1px rgba(255,255,255,0.5) !important; }
""", "glassy"),

    # ── Paper Torn (กระดาษฉีกขอบ) ──
    "paper-torn": _t("📄 Paper Torn (กระดาษฉีก)", """
.msg {
  clip-path: polygon(0 2px, 3px 0, 8px 3px, 14px 0, 20px 2px, 30px 0, 100% 3px, calc(100% - 4px) 0, calc(100% - 12px) 3px, calc(100% - 20px) 0, calc(100% - 4px) calc(100% - 3px), calc(100% - 10px) 100%, calc(100% - 18px) calc(100% - 3px), 20px 100%, 12px calc(100% - 2px), 4px 100%, 8px calc(100% - 3px), 0 calc(100% - 4px)) !important;
}
.msg-bg {
  background: #fafafa !important;
  border: none !important;
  border-radius: 0 !important;
  box-shadow: 2px 4px 10px rgba(0,0,0,0.15) !important;
}
.msg .author { color: #2c3e50 !important; text-shadow: none !important; }
.msg .text { color: #34495e !important; text-shadow: none !important; }
""", "slide_up"),

    # ── Neon Sign (ป้ายนีออนขอบคู่) ──
    "neon-sign": _t("💡 Neon Sign (ป้ายนีออน)", """
.msg-bg {
  background: #0d0d0d !important;
  border: 1px solid #ff0080 !important;
  border-radius: 2px !important;
  box-shadow: 0 0 6px #ff0080, 0 0 14px #ff0080, inset 0 0 8px rgba(255,0,128,0.3) !important;
}
.msg .author {
  color: #ff66b3 !important;
  text-shadow: 0 0 4px #ff0080, 0 0 8px #ff0080, 0 0 12px #ff0080 !important;
}
.msg .text {
  color: #80f0ff !important;
  text-shadow: 0 0 4px #00d4ff, 0 0 8px #00d4ff !important;
}
""", "glow"),

    # ════════════════════════════════════════════════════════════════
    # ── Theme กรอบลูกเล่น เพิ่มเติม (วงที่ 3) ──
    # ════════════════════════════════════════════════════════════════

    # ── Ribbon (ป้ายโบว์ผูก มีหางเฉียง) ──
    "ribbon": _t("🎀 Ribbon (ป้ายโบว์)", """
.msg {
  clip-path: polygon(0 0, 100% 0, 100% 100%, 50% calc(100% - 10px), 0 100%) !important;
}
.msg-bg {
  background: #e11d48 !important;
  border: none !important;
  border-radius: 4px !important;
  box-shadow: 0 3px 6px rgba(0,0,0,0.3) !important;
}
.msg .author { color: #fff1f2 !important; text-shadow: 1px 1px 2px rgba(0,0,0,0.4) !important; }
.msg .text { color: #ffffff !important; text-shadow: 1px 1px 2px rgba(0,0,0,0.4) !important; }
""", "slide_up"),

    # ── Cloud (ก้อนเมฆมุมกลมซ้อน) ──
    "cloud": _t("☁️ Cloud (ก้อนเมฆ)", """
.msg-bg {
  background: #ffffff !important;
  border: none !important;
  border-radius: 24px 12px 30px 16px / 16px 28px 12px 24px !important;
  box-shadow: 0 6px 16px rgba(100,150,200,0.3) !important;
}
.msg .author { color: #4a90d9 !important; text-shadow: none !important; }
.msg .text { color: #2c3e50 !important; text-shadow: none !important; }
""", "bounce"),

    # ── Circuit (วงจรไฟฟ้า + จุดต่อ) ──
    "circuit": _t("🔌 Circuit (วงจรไฟฟ้า)", """
.msg-bg {
  background: #0a1929 !important;
  border: 1px solid #00ff88 !important;
  border-radius: 0 !important;
  box-shadow: inset 0 0 0 1px #0a1929, inset 0 0 0 2px #00ff88, 0 0 8px rgba(0,255,136,0.3) !important;
}
.msg::before {
  content: ""; position: absolute; top: 4px; left: 4px;
  width: 5px; height: 5px; background: #00ff88; border-radius: 50%;
  box-shadow: calc(100% - 13px) 0 0 #00ff88;
}
.msg .author { color: #00ff88 !important; text-shadow: 0 0 4px rgba(0,255,136,0.6) !important; font-family: "Consolas", monospace !important; }
.msg .text { color: #b9f6ca !important; font-family: "Consolas", monospace !important; }
""", "slide_up"),

    # ── Tag (ป้าย tag มีรูเสียบซ้าย) ──
    "tag": _t("🏷️ Tag (ป้ายมีรู)", """
.msg {
  clip-path: polygon(12px 0, 100% 0, 100% 100%, 12px 100%, 0 50%) !important;
}
.msg-bg {
  background: #6366f1 !important;
  border: none !important;
  border-radius: 0 8px 8px 0 !important;
  box-shadow: 0 2px 6px rgba(0,0,0,0.2) !important;
}
.msg::before {
  content: ""; position: absolute; left: 4px; top: 50%;
  width: 6px; height: 6px; background: #ffffff; border-radius: 50%;
  transform: translateY(-50%);
}
.msg .author { color: #e0e7ff !important; text-shadow: none !important; }
.msg .text { color: #ffffff !important; text-shadow: none !important; padding-left: 8px !important; }
""", "slide_up"),

    # ── Receipt (ใบเสร็จขอบฟันปลา) ──
    "receipt": _t("🧾 Receipt (ใบเสร็จ)", """
.msg {
  clip-path: polygon(0 0, 100% 0, 100% calc(100% - 6px), 96% 100%, 92% calc(100% - 6px), 88% 100%, 84% calc(100% - 6px), 80% 100%, 76% calc(100% - 6px), 72% 100%, 68% calc(100% - 6px), 64% 100%, 60% calc(100% - 6px), 56% 100%, 52% calc(100% - 6px), 48% 100%, 44% calc(100% - 6px), 40% 100%, 36% calc(100% - 6px), 32% 100%, 28% calc(100% - 6px), 24% 100%, 20% calc(100% - 6px), 16% 100%, 12% calc(100% - 6px), 8% 100%, 4% calc(100% - 6px), 0 100%) !important;
  font-family: "Consolas", monospace !important;
}
.msg-bg {
  background: #fffbeb !important;
  border: none !important;
  border-radius: 0 !important;
  box-shadow: 2px 4px 8px rgba(0,0,0,0.15) !important;
}
.msg .author { color: #92400e !important; text-shadow: none !important; }
.msg .text { color: #1f2937 !important; text-shadow: none !important; }
""", "slide_up"),

    # ── TV (จอทีวีเก่า กรอบหนามุมโค้ง) ──
    "tv": _t("📺 TV (จอทีวีเก่า)", """
.msg-bg {
  background: #1a1a1a !important;
  border: 6px solid #6b7280 !important;
  border-radius: 18px !important;
  box-shadow: inset 0 0 0 2px #374151, inset 0 0 12px rgba(0,255,100,0.2), 0 4px 0 #374151 !important;
}
.msg::before {
  content: ""; position: absolute; right: 8px; top: 4px;
  width: 4px; height: 4px; background: #ef4444; border-radius: 50%;
  box-shadow: 0 0 4px #ef4444;
}
.msg .author { color: #4ade80 !important; text-shadow: 0 0 4px rgba(74,222,128,0.6) !important; font-family: "Consolas", monospace !important; }
.msg .text { color: #86efac !important; text-shadow: 0 0 3px rgba(134,239,172,0.4) !important; font-family: "Consolas", monospace !important; }
""", "fade"),

    # ════════════════════════════════════════════════════════════════
    # ── Theme สไตล์ผู้หญิง (น่ารัก/หวาน/แฟชั่น) ──
    # ════════════════════════════════════════════════════════════════

    # ── Sakura (กลีบซากุระร่วง พื้นชมพูอ่อน) ──
    "sakura": _t("🌸 Sakura (ซากุระ)", """
.msg-bg {
  background: linear-gradient(135deg, rgba(255, 240, 245, 0.85), rgba(255, 218, 230, 0.8)) !important;
  border: 1px solid rgba(255, 105, 180, 0.4) !important;
  border-radius: 16px !important;
  box-shadow: 0 4px 12px rgba(255, 105, 180, 0.2) !important;
}
.msg .author { color: #d6336c !important; text-shadow: 0 0 4px rgba(255, 192, 203, 0.6) !important; font-weight: 700 !important; }
.msg .text { color: #8b3a52 !important; text-shadow: none !important; }
""", "bounce"),

    # ── Princess (เจ้าหญิง ชมพู+ทอง+sparkle) ──
    "princess": _t("👑 Princess (เจ้าหญิง)", """
.msg-bg {
  background: linear-gradient(145deg, #fff0f5 0%, #ffe4ec 100%) !important;
  border: 2px solid #ffd700 !important;
  border-radius: 20px !important;
  box-shadow: 0 0 0 1px #ffb6c1, 0 4px 14px rgba(255, 182, 193, 0.4) !important;
}
.msg .author { color: #c71585 !important; text-shadow: 0 0 4px rgba(255, 215, 0, 0.5) !important; font-weight: 700 !important; }
.msg .text { color: #8b4570 !important; text-shadow: none !important; }
""", "pop"),

    # ── Macaron (ขนมหวานสีพาสเทล) ──
    "macaron": _t("🍬 Macaron (พาสเทลหวาน)", """
.msg-bg {
  background: linear-gradient(135deg, #fce4ec 0%, #e3f2fd 50%, #f3e5f5 100%) !important;
  border: 2px solid #f8bbd0 !important;
  border-radius: 24px !important;
  box-shadow: 0 3px 10px rgba(248, 187, 209, 0.3) !important;
}
.msg .author { color: #ec407a !important; text-shadow: none !important; font-weight: 600 !important; }
.msg .text { color: #7e57c2 !important; text-shadow: none !important; }
""", "slide_up"),

    # ── Galaxy Girl (อวกาศสาว ม่วง-ชมพู-ดาว) ──
    "galaxy-girl": _t("🌙 Galaxy Girl (อวกาศสาว)", """
.msg-bg {
  background: linear-gradient(135deg, #2d1b4e 0%, #4a2456 50%, #6b2d5c 100%) !important;
  border: 1px solid rgba(255, 192, 203, 0.5) !important;
  border-radius: 14px !important;
  box-shadow: 0 0 14px rgba(186, 104, 200, 0.4), inset 0 0 12px rgba(255, 182, 193, 0.15) !important;
}
.msg .author { color: #ffb6dd !important; text-shadow: 0 0 6px rgba(255, 182, 209, 0.7) !important; font-weight: 700 !important; }
.msg .text { color: #e1bee7 !important; text-shadow: 0 0 3px rgba(186, 104, 200, 0.5) !important; }
""", "glow"),

    # ── Cotton Candy (ฝ้ายขนมหวาน ชมพู+ฟ้า pastel) ──
    "cotton-candy": _t("🍭 Cotton Candy (ฝ้ายขนมหวาน)", """
.msg-bg {
  background: linear-gradient(135deg, #ffc0cb 0%, #b0e0e6 100%) !important;
  border: 2px solid rgba(255, 255, 255, 0.6) !important;
  border-radius: 18px !important;
  box-shadow: 0 4px 14px rgba(255, 182, 193, 0.4) !important;
}
.msg .author { color: #e91e63 !important; text-shadow: 1px 1px 0 #fff !important; font-weight: 700 !important; }
.msg .text { color: #5e35b1 !important; text-shadow: 1px 1px 0 rgba(255,255,255,0.5) !important; }
""", "bounce"),

    # ── Kawaii (โมเอะ ชมพูสด โค้งมน โบว์) ──
    "kawaii": _t("🎀 Kawaii (โมเอะ)", """
.msg-bg {
  background: #ffe0ec !important;
  border: 3px solid #ff69b4 !important;
  border-radius: 24px !important;
  box-shadow: 0 4px 0 #ff69b4, 0 6px 10px rgba(255, 105, 180, 0.3) !important;
}
.msg::before {
  content: "🎀"; position: absolute; top: -12px; right: 10px; font-size: 1.2em;
}
.msg .author { color: #d81b60 !important; text-shadow: none !important; font-weight: 700 !important; }
.msg .text { color: #ad1457 !important; text-shadow: none !important; }
""", "pop"),

    # ── Mermaid (นางเงือก เขียวมินต์+ม่วง) ──
    "mermaid": _t("🧜‍♀️ Mermaid (นางเงือก)", """
.msg-bg {
  background: linear-gradient(135deg, #a8edea 0%, #fed6e3 100%) !important;
  border: 2px solid rgba(72, 209, 204, 0.5) !important;
  border-radius: 20px !important;
  box-shadow: 0 0 12px rgba(72, 209, 204, 0.3), inset 0 0 10px rgba(255, 255, 255, 0.3) !important;
}
.msg .author { color: #00838f !important; text-shadow: 0 0 4px rgba(178, 235, 242, 0.7) !important; font-weight: 700 !important; }
.msg .text { color: #6a1b9a !important; text-shadow: none !important; }
""", "slide_up"),

    # ── Rose Gold (ทองกุหลาบ metallic gradient) ──
    "rose-gold": _t("🌹 Rose Gold (ทองกุหลาบ)", """
.msg-bg {
  background: linear-gradient(135deg, #f5d0c5 0%, #e8b4a0 50%, #f7cac9 100%) !important;
  border: 2px solid #b76e79 !important;
  border-radius: 14px !important;
  box-shadow: 0 0 0 1px rgba(183, 110, 121, 0.3), 0 4px 12px rgba(183, 110, 121, 0.25) !important;
}
.msg .author { color: #8b4a52 !important; text-shadow: 0 1px 0 rgba(255, 255, 255, 0.5) !important; font-weight: 700 !important; }
.msg .text { color: #6d3d44 !important; text-shadow: none !important; }
""", "glassy"),

    # ── Pip-Boy (จอ CRT เขียว phosphor สไตล์ Fallout) ──
    "pipboy": _t("☢️ Pip-Boy (จอเขียว Fallout)", """
.msg {
  font-family: "Consolas", "Courier New", monospace !important;
  position: relative !important;
  overflow: hidden !important;
}
.msg-bg {
  background: #0a1a0a !important;
  border: 2px solid #2d5a2d !important;
  border-radius: 0 !important;
  box-shadow: inset 0 0 12px rgba(46, 220, 46, 0.25), 0 0 8px rgba(46, 220, 46, 0.3) !important;
}
/* scanline เหมือนจอ CRT */
.msg::before {
  content: ""; position: absolute; inset: 0; pointer-events: none;
  background: repeating-linear-gradient(0deg, transparent 0, transparent 2px, rgba(46, 220, 46, 0.06) 2px, rgba(46, 220, 46, 0.06) 3px);
}
.msg .author {
  color: #7fff5e !important;
  text-shadow: 0 0 4px rgba(127, 255, 94, 0.8), 0 0 8px rgba(46, 220, 46, 0.5) !important;
  font-weight: 700 !important;
}
.msg .text {
  color: #5fff3a !important;
  text-shadow: 0 0 3px rgba(95, 255, 58, 0.7), 0 0 6px rgba(46, 220, 46, 0.4) !important;
}
.msg .author::before { content: "> "; color: #2edc2e; }
""", "fade"),

    # ══ Theme Part 2 (2026-09) — กล่องหลังข้อความจริง ต่อธีม ══
    # ── Coral Reef ──
    "coral-reef": _t("🪸 Coral Reef (แนวปะการัง)", """
.msg {
  position: relative !important; overflow: hidden !important;
}
.msg-bg {
  background: linear-gradient(120deg,#ff7a59 0%,#ff5f9e 45%,#22c3c8 100%) !important;
  border-radius: 10px !important;
  box-shadow: 0 3px 8px rgba(255,90,140,.3) !important;
}
.msg::after {
  content: ""; position: absolute; inset: 0; pointer-events: none;
  background: radial-gradient(circle 2px at 18% 30%,rgba(255,240,180,.8),transparent), radial-gradient(circle 2px at 75% 65%,rgba(255,255,255,.7),transparent);
}
""", "fade"),

    # ── Bio Forest ──
    "bio-forest": _t("🍃 Bio Forest (ป่าเรืองแสง)", """
.msg {
  position: relative !important; overflow: hidden !important;
}
.msg-bg {
  background: radial-gradient(circle at 25% 60%,#0d2b1a 0%,#04120a 85%) !important;
  border: 1px solid rgba(120,255,180,.28) !important;
  border-radius: 10px !important;
  box-shadow: 0 0 10px rgba(80,220,150,.2) !important;
}
.msg::after {
  content: ""; position: absolute; inset: 0; pointer-events: none;
  background: radial-gradient(circle 2px at 30% 35%,rgba(130,255,190,.6),transparent), radial-gradient(circle 2px at 78% 55%,rgba(130,255,190,.45),transparent);
}
""", "fade"),

    # ── Desert Dune ──
    "desert-dune": _t("🏜️ Desert Dune (เนินทราย)", """
.msg-bg {
  background: repeating-linear-gradient(100deg,rgba(255,255,255,.12) 0 2px,transparent 2px 22px), linear-gradient(180deg,#f3d9a4 0%,#e0b578 55%,#c99a5c 100%) !important;
  border: 1px solid #b8895a !important;
  border-radius: 10px !important;
}
""", "fade"),

    # ── Frozen Lake ──
    "frozen-lake": _t("🧊 Frozen Lake (ทะเลสาบน้ำแข็ง)", """
.msg-bg {
  background: repeating-linear-gradient(35deg,rgba(190,235,255,.1) 0 1px,transparent 1px 26px), repeating-linear-gradient(-50deg,rgba(190,235,255,.08) 0 1px,transparent 1px 34px), linear-gradient(160deg,#0c2430 0%,#173a4a 100%) !important;
  border: 1px solid rgba(180,230,255,.3) !important;
  border-radius: 6px !important;
}
""", "fade"),

    # ── Denim Patch ──
    "denim-patch": _t("🧵 Denim Patch (ผ้ายีนส์ปะ)", """
.msg-bg {
  background: repeating-linear-gradient(45deg,#3a5a8a 0 3px,#33517d 3px 6px) !important;
  border: 2px dashed #f0e6c8 !important;
  border-radius: 4px !important;
}
""", "fade"),

    # ── Steampunk ──
    "steampunk": _t("⚙️ Steampunk (จักรกลไอน้ำ)", """
.msg {
  padding-right: 26px !important;
  position: relative !important; overflow: hidden !important;
}
.msg-bg {
  background: linear-gradient(160deg,#3a2a18 0%,#241a0e 100%) !important;
  border: 2px solid #b8863a !important;
  border-radius: 5px !important;
}
.msg::after {
  content: ""; position: absolute; top: 5px; right: 5px; width: 14px; height: 14px; pointer-events: none;
  border-radius: 50%; border: 2px dashed #b8863a; opacity: .75;
}
""", "fade"),

    # ── Ramen Steam ──
    "ramen-steam": _t("🍜 Ramen Steam (ราเมงร้อนๆ)", """
.msg-bg {
  background: linear-gradient(180deg,#5a1a12 0%,#8a2a12 100%) !important;
  border-radius: 6px 6px 18px 18px !important;
}
""", "fade"),

    # ── Knit Sweater ──
    "knit-sweater": _t("🧶 Knit Sweater (ไหมพรมถัก)", """
.msg-bg {
  background: repeating-linear-gradient(-45deg,rgba(0,0,0,.08) 0 8px,transparent 8px 16px), repeating-linear-gradient(45deg,#c94f4f 0 8px,#b23e3e 8px 16px) !important;
  border: 2px solid #8a2e2e !important;
  border-radius: 10px !important;
}
""", "fade"),

    # ── Equalizer ──
    "equalizer": _t("🎚️ Equalizer (คลื่นเสียง)", """
.msg {
  padding-left: 16px !important;
  position: relative !important; overflow: hidden !important;
}
.msg-bg {
  background: #0a0a0f !important;
  border: 1px solid #2a2a35 !important;
  border-radius: 6px !important;
}
.msg::before {
  content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 8px; pointer-events: none;
  background: repeating-linear-gradient(0deg,#22d3ee 0 4px,#7c3aed 4px 5px,transparent 5px 8px);
}
""", "fade"),

    # ── Holo Badge ──
    "holo-badge": _t("🎫 Holo Badge (บัตรโฮโลแกรม)", """
.msg {
  padding-bottom: 10px !important;
  position: relative !important; overflow: hidden !important;
}
.msg-bg {
  background: linear-gradient(100deg,#dce8ff 0%,#ffe8f5 25%,#e8fff5 50%,#fff8dc 75%,#dce8ff 100%) !important;
  border: 1px solid #c9c9d9 !important;
  border-radius: 4px !important;
}
.msg::after {
  content: ""; position: absolute; left: 0; right: 0; bottom: 0; height: 5px; pointer-events: none;
  background: repeating-linear-gradient(90deg,#1a1a1a 0 2px,transparent 2px 5px); opacity: .5;
}
""", "fade"),

    # ── Cross Stitch ──
    "cross-stitch": _t("🪡 Cross Stitch (ปักครอสติช)", """
.msg {
  padding-top: 11px !important;
  position: relative !important; overflow: hidden !important;
}
.msg-bg {
  background: #f2ead9 !important;
  border: 2px dashed #b23a4a !important;
  border-radius: 5px !important;
}
.msg::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0; height: 5px; pointer-events: none;
  background: repeating-linear-gradient(90deg,#b23a4a 0 5px,#3a6a9a 5px 10px);
}
""", "fade"),

    # ── Frost Window ──
    "frost-window": _t("🌬️ Frost Window (กระจกเกาะน้ำแข็ง)", """
.msg {
  position: relative !important; overflow: hidden !important;
}
.msg-bg {
  background: linear-gradient(160deg,#eaf6ff 0%,#cfe9fb 100%) !important;
  border: 1px solid #a9d4ec !important;
  border-radius: 8px !important;
}
.msg::after {
  content: ""; position: absolute; left: 0; bottom: 0; width: 26px; height: 26px; pointer-events: none;
  background: radial-gradient(circle at 0% 100%,rgba(255,255,255,.65),transparent 70%);
}
""", "fade"),

    # ── Lunar Lantern ──
    "lunar-lantern": _t("🏮 Lunar Lantern (โคมจันทร์)", """
.msg {
  padding-bottom: 9px !important;
  position: relative !important; overflow: hidden !important;
}
.msg-bg {
  background: radial-gradient(circle at 50% 20%,#ff5a3c 0%,#c2181b 80%) !important;
  border-top: 3px solid #f0c65e !important;
  border-radius: 10px !important;
}
.msg::after {
  content: ""; position: absolute; left: 0; right: 0; bottom: 0; height: 4px; pointer-events: none;
  background: repeating-linear-gradient(90deg,#f0c65e 0 3px,transparent 3px 8px);
}
""", "fade"),

    # ══ Theme Part 2 — batch 2 (2026-09-25) ══
    # ── Retrowave Sunset Grid ──
    "retrowave-sunset-grid": _t("🌇 Retrowave Sunset Grid (คลื่นวิทยุย้อนยุค)", """
.msg {
  position: relative !important; overflow: hidden !important;
}
.msg-bg {
  background: linear-gradient(180deg,#2d1b4e 0%,#7b2d6e 50%,#ff6b35 100%) !important;
  border-bottom: 3px solid #ffb347 !important;
  border-radius: 4px !important;
  box-shadow: 0 0 16px rgba(255,107,53,.4) !important;
}
.msg::after {
  content: ""; position: absolute; left: 0; right: 0; bottom: 0; height: 50%; pointer-events: none;
  background: repeating-linear-gradient(90deg, rgba(255,255,255,.25) 0 1px, transparent 1px 14px), repeating-linear-gradient(0deg, rgba(255,255,255,.2) 0 1px, transparent 1px 8px);
  -webkit-mask-image: linear-gradient(180deg, transparent, black);
  mask-image: linear-gradient(180deg, transparent, black);
}
""", "fade"),

    # ── Obsidian Prism ──
    "obsidian-prism": _t("🖤 Obsidian Prism (แก้วภูเขาไฟปริซึม)", """
.msg {
  position: relative !important; overflow: hidden !important;
}
.msg-bg {
  background: linear-gradient(135deg,#0a0a0f 0%,#1a1a2e 100%) !important;
  border: 1px solid rgba(255,255,255,.15) !important;
  border-radius: 8px !important;
  box-shadow: 0 4px 16px rgba(0,0,0,.5) !important;
}
.msg::before {
  content: ""; position: absolute; top: 0; left: 0; width: 3px; height: 100%; pointer-events: none;
  background: linear-gradient(180deg,#ff6b9d,#ffb347,#7ee787,#58a6ff,#a78bfa);
}
.msg::after {
  content: ""; position: absolute; top: -20%; left: -10%; width: 40%; height: 140%; pointer-events: none;
  background: linear-gradient(105deg, transparent 40%, rgba(255,255,255,.12) 48%, rgba(255,255,255,.03) 52%, transparent 60%);
  transform: skewX(-15deg);
}
""", "fade"),

    # ── Washi Paper ──
    "washi-paper": _t("🎏 Washi Paper (กระดาษวาชิญี่ปุ่น)", """
.msg {
  position: relative !important; overflow: hidden !important;
}
.msg-bg {
  background: #f4ede0 !important;
  background-image: repeating-linear-gradient(90deg, rgba(180,150,110,.06) 0 2px, transparent 2px 5px), repeating-linear-gradient(0deg, rgba(180,150,110,.05) 0 2px, transparent 2px 5px) !important;
  border: 1px solid #d8c8a8 !important;
  border-radius: 3px !important;
  box-shadow: 0 2px 6px rgba(120,90,50,.15) !important;
}
.msg::after {
  content: ""; position: absolute; top: 6px; right: 6px; width: 16px; height: 16px; border-radius: 50%; pointer-events: none;
  background: rgba(178,42,58,.75);
}
""", "fade"),

    # ── Midnight Aquarium ──
    "midnight-aquarium": _t("🐟 Midnight Aquarium (ตู้ปลายามดึก)", """
.msg {
  position: relative !important; overflow: hidden !important;
}
.msg-bg {
  background: linear-gradient(180deg,#031225 0%,#062a4a 100%) !important;
  border: 1px solid rgba(100,200,255,.25) !important;
  border-radius: 12px !important;
  box-shadow: inset 0 0 20px rgba(0,50,100,.4), 0 0 10px rgba(50,150,255,.2) !important;
}
.msg::after {
  content: ""; position: absolute; inset: 0; pointer-events: none;
  background: radial-gradient(circle 3px at 15% 75%,rgba(150,230,255,.5),transparent), radial-gradient(circle 2px at 40% 30%,rgba(150,230,255,.4),transparent), radial-gradient(circle 2px at 70% 60%,rgba(150,230,255,.35),transparent), radial-gradient(circle 4px at 88% 20%,rgba(150,230,255,.3),transparent);
}
""", "fade"),

    # ── Esports HUD ──
    "esports-hud": _t("🎮 Esports HUD (จอเกมมิ่ง HUD)", """
.msg {
  clip-path: polygon(10px 0, 100% 0, 100% calc(100% - 10px), calc(100% - 10px) 100%, 0 100%, 0 10px) !important;
  position: relative !important; overflow: hidden !important;
}
.msg-bg {
  background: linear-gradient(90deg,#0d0d14 0%,#151522 100%) !important;
  border: 1px solid #2effc7 !important;
  border-radius: 0 !important;
  box-shadow: 0 0 10px rgba(46,255,199,.35) !important;
}
.msg::before {
  content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 4px; pointer-events: none;
  background: linear-gradient(180deg,#2effc7,#ff2e6c);
}
""", "fade"),

    # ── Vinyl Record ──
    "vinyl-record": _t("💿 Vinyl Record (แผ่นเสียงไวนิล)", """
.msg-bg {
  background: radial-gradient(circle at 85% 50%, #b0202f 0 8%, #111 9% 100%) !important;
  background-image: repeating-radial-gradient(circle at 85% 50%, rgba(255,255,255,.05) 0 2px, transparent 2px 5px), radial-gradient(circle at 85% 50%, #b0202f 0 8%, #111 9% 100%) !important;
  border-radius: 8px !important;
  box-shadow: 0 3px 10px rgba(0,0,0,.4) !important;
}
""", "fade"),

    # ── Royal Velvet Curtain ──
    "royal-velvet-curtain": _t("🎭 Royal Velvet Curtain (ม่านกำมะหยี่ราชวงศ์)", """
.msg {
  position: relative !important; overflow: hidden !important;
}
.msg-bg {
  background: repeating-linear-gradient(90deg,#5a1030 0 14px,#4a0c26 14px 28px) !important;
  border-top: 4px solid #d4af37 !important;
  border-radius: 4px 4px 10px 10px !important;
  box-shadow: 0 4px 12px rgba(0,0,0,.4) !important;
}
.msg::after {
  content: ""; position: absolute; left: 0; right: 0; bottom: 0; height: 5px; pointer-events: none;
  background: repeating-linear-gradient(90deg,#d4af37 0 4px,transparent 4px 10px);
}
""", "fade"),

    # ── Neon Arcade Cabinet ──
    "neon-arcade-cabinet": _t("🕹️ Neon Arcade Cabinet (ตู้เกมอาเขตนีออน)", """
.msg {
  position: relative !important; overflow: hidden !important;
}
.msg-bg {
  background: #0a0512 !important;
  border: 3px solid #ff2ec4 !important;
  border-radius: 10px !important;
  box-shadow: 0 0 8px #ff2ec4, inset 0 0 8px rgba(255,46,196,.3), 0 0 16px rgba(46,200,255,.3) !important;
}
.msg::before {
  content: ""; position: absolute; inset: 2px; border-radius: 8px; pointer-events: none;
  border: 1px solid #2ec8ff;
}
""", "fade"),

    # ── Storm Cloud Thunder ──
    "storm-cloud-thunder": _t("⛈️ Storm Cloud Thunder (เมฆพายุฟ้าผ่า)", """
.msg {
  position: relative !important; overflow: hidden !important;
}
.msg-bg {
  background: linear-gradient(180deg,#2a3038 0%,#4a5560 60%,#5a6570 100%) !important;
  border-radius: 10px !important;
  box-shadow: 0 4px 14px rgba(0,0,0,.35) !important;
}
.msg::after {
  content: ""; position: absolute; top: -10%; right: 12%; width: 3px; height: 130%; pointer-events: none;
  background: #ffe066; clip-path: polygon(50% 0,20% 45%,50% 45%,10% 100%,60% 50%,35% 50%);
  filter: drop-shadow(0 0 4px rgba(255,224,102,.8));
}
""", "fade"),

    # ── Lucky Red Envelope ──
    "lucky-red-envelope": _t("🧧 Lucky Red Envelope (อั่งเปาโชคดี)", """
.msg {
  position: relative !important; overflow: hidden !important;
}
.msg-bg {
  background: linear-gradient(160deg,#b8202c 0%,#8f1620 100%) !important;
  border: 1px solid #f0c65e !important;
  border-radius: 6px !important;
  box-shadow: 0 3px 10px rgba(140,20,20,.4) !important;
}
.msg::before {
  content: ""; position: absolute; inset: 4px; border-radius: 3px; pointer-events: none;
  background-image: repeating-linear-gradient(45deg, rgba(240,198,94,.12) 0 2px, transparent 2px 14px);
}
.msg::after {
  content: ""; position: absolute; top: 0; left: 50%; transform: translateX(-50%); width: 26px; height: 10px; pointer-events: none;
  background: #f0c65e; border-radius: 0 0 8px 8px;
}
""", "fade"),

    # ── Origami Crane Fold ──
    "origami-crane-fold": _t("🕊️ Origami Crane Fold (นกกระเรียนกระดาษพับ)", """
.msg {
  clip-path: polygon(0 12px, 12px 0, 100% 0, 100% calc(100% - 12px), calc(100% - 12px) 100%, 0 100%) !important;
  position: relative !important; overflow: hidden !important;
}
.msg-bg {
  background: linear-gradient(135deg,#fef3e2 0%,#fcd5ce 50%,#f8a8c8 100%) !important;
  box-shadow: 0 3px 10px rgba(248,168,200,.35) !important;
}
.msg::after {
  content: ""; position: absolute; inset: 0; pointer-events: none;
  background: linear-gradient(45deg, transparent 48%, rgba(255,255,255,.5) 50%, transparent 52%), linear-gradient(-45deg, transparent 48%, rgba(180,120,140,.15) 50%, transparent 52%);
}
""", "fade"),

    # ── Vintage Film Strip ──
    "vintage-film-strip": _t("🎞️ Vintage Film Strip (ฟิล์มหนังย้อนยุค)", """
.msg {
  padding-left: 18px !important; padding-right: 18px !important;
  position: relative !important; overflow: hidden !important;
}
.msg-bg {
  background: #1c1a17 !important;
  border-radius: 4px !important;
  box-shadow: 0 3px 10px rgba(0,0,0,.4) !important;
}
.msg::before, .msg::after {
  content: ""; position: absolute; top: 0; bottom: 0; width: 14px; pointer-events: none;
  background: repeating-linear-gradient(180deg, #0a0908 0 6px, #3a3530 6px 14px);
}
.msg::before { left: 0; }
.msg::after { right: 0; }
""", "fade"),

    # ── Thai Silk ──
    "thai-silk": _t("🧵 Thai Silk (ผ้าไหมไทย)", """
.msg-bg {
  background: linear-gradient(120deg,#7a1f3d 0%,#b8860b 45%,#1a5f4a 100%) !important;
  background-image: repeating-linear-gradient(45deg, rgba(255,255,255,.08) 0 3px, transparent 3px 9px), linear-gradient(120deg,#7a1f3d 0%,#b8860b 45%,#1a5f4a 100%) !important;
  border: 1px solid #d4af37 !important;
  border-radius: 6px !important;
  box-shadow: 0 3px 12px rgba(184,134,11,.3) !important;
}
""", "fade"),

    # ── Holo Foil Sticker ──
    "holo-foil-sticker": _t("🌈 Holo Foil Sticker (สติกเกอร์โฮโลแกรม)", """
.msg {
  position: relative !important; overflow: hidden !important;
}
.msg-bg {
  background: linear-gradient(120deg,#ff9a9e 0%,#fecfef 20%,#a1c4fd 40%,#c2e9fb 60%,#fbc2eb 80%,#ff9a9e 100%) !important;
  border: 1px solid rgba(255,255,255,.7) !important;
  border-radius: 14px !important;
  box-shadow: 0 3px 10px rgba(160,140,255,.35) !important;
}
.msg::after {
  content: ""; position: absolute; inset: 0; pointer-events: none;
  background: repeating-linear-gradient(115deg, rgba(255,255,255,.35) 0 2px, transparent 2px 18px);
  mix-blend-mode: overlay;
}
""", "fade"),

    # ── Custom ──
    "custom": _t("✏️ Custom (เขียน CSS เอง)", ""),
}


def get_theme_css(theme: str, custom_css: str = "") -> str:
    """คืน CSS ของ theme ที่เลือก (custom → ใช้ custom_css)"""
    if theme == "custom":
        return custom_css or "/* Custom CSS ว่าง — กด 📖 CSS Guide เพื่อดูตัวอย่าง */"
    t = THEMES.get(theme, THEMES["default"])
    return t["css"]


def get_theme_default_animation(theme: str) -> str:
    t = THEMES.get(theme, THEMES["default"])
    return t.get("default_animation", "fade")


def _strip_vs(label: str) -> str:
    """strip variation selector (U+FE0F) ออกจาก emoji เพื่อให้ dropdown text ชิดเสมอกัน
    emoji ที่มี VS (เช่น 🛡️ ❄️ ✏️) จะกว้างกว่า emoji ทั่วไป ทำให้ text ไม่ชิดเส้นเดียวกัน
    """
    return label.replace("\ufe0f", "")


def get_theme_label(theme: str) -> str:
    t = THEMES.get(theme, THEMES["default"])
    return _strip_vs(t.get("label", theme))


def get_theme_list() -> list[tuple[str, str]]:
    """list of (theme_key, label) สำหรับ dropdown"""
    return [(key, _strip_vs(t["label"])) for key, t in THEMES.items()]


if __name__ == "__main__":
    for key, t in THEMES.items():
        css = get_theme_css(key, "/* test */")
        print(f"  {key}: css={len(css)}c anim={t['default_animation']}")
    print(f"✅ {len(THEMES)} themes total")
