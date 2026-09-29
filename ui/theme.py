"""theme.py — QSS stylesheet + color constants + font setup (PySide6)

Modern flat design — Discord/Spotify style dark theme
เก็บ color palette เดิมจาก v1 (เพราะคุ้นเคย + สวยอยู่แล้ว)
"""
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

# ═══════════════════════════════════════════════════════════════
# Themes — palette ต่อธีม (ui_theme ใน settings เก็บ key ในนี้)
# ★ "default" = ค่าเดิมจาก v1 เป๊ะๆ ทุกตัว (ห้ามแก้ค่าพวกนี้ — ผู้ใช้เดิมต้องไม่เห็นอะไรเปลี่ยน
#   ถ้าไม่ได้เข้าไปเลือกธีมใหม่เองใน Settings)
# ═══════════════════════════════════════════════════════════════
THEMES = {
    "default": {
        "BG": "#0a0e1a", "BG_DARK": "#060912", "CARD": "#131726",
        "CARD_HI": "#1a1f33", "CARD_HOVER": "#1e2438",
        "ACCENT": "#7c3aed", "ACCENT_HOVER": "#6d28d9", "ACCENT_2": "#06b6d4",
        "HEADING": "#f59e0b",
        "DANGER": "#ef4444", "DANGER_HOVER": "#dc2626",
        "SUCCESS": "#10b981", "SUCCESS_HOVER": "#059669",
        "TEXT": "#e5e7eb", "TEXT_DIM": "#9ca3af", "TEXT_FAINT": "#6b7280",
        "BORDER": "#2a2f45", "BORDER_LIGHT": "#374151",
    },
    "aurora_violet": {
        "BG": "#0d0b1a", "BG_DARK": "#08060f", "CARD": "#181430",
        "CARD_HI": "#211c3d", "CARD_HOVER": "#251f45",
        "ACCENT": "#8b5cf6", "ACCENT_HOVER": "#7c3aed", "ACCENT_2": "#22d3ee",
        "HEADING": "#c4b5fd",
        "DANGER": "#f87171", "DANGER_HOVER": "#ef4444",
        "SUCCESS": "#34d399", "SUCCESS_HOVER": "#10b981",
        "TEXT": "#ece9f7", "TEXT_DIM": "#b4aecb", "TEXT_FAINT": "#8b87a3",
        "BORDER": "#332b52", "BORDER_LIGHT": "#453a6e",
    },
    "ember_dusk": {
        "BG": "#17110d", "BG_DARK": "#100c09", "CARD": "#201611",
        "CARD_HI": "#2a1d15", "CARD_HOVER": "#33241a",
        "ACCENT": "#ea580c", "ACCENT_HOVER": "#c2410c", "ACCENT_2": "#fb923c",
        "HEADING": "#fbbf24",
        "DANGER": "#dc2626", "DANGER_HOVER": "#991b1b",
        "SUCCESS": "#16a34a", "SUCCESS_HOVER": "#15803d",
        "TEXT": "#f5ece2", "TEXT_DIM": "#c9b5a1", "TEXT_FAINT": "#8a7562",
        "BORDER": "#3d2a1c", "BORDER_LIGHT": "#4d3624",
    },
    "nightwave_cyan": {
        "BG": "#070c0f", "BG_DARK": "#04080a", "CARD": "#0a1417",
        "CARD_HI": "#0d1a1e", "CARD_HOVER": "#112128",
        "ACCENT": "#22d3ee", "ACCENT_HOVER": "#0e7490", "ACCENT_2": "#67e8f9",
        "HEADING": "#22d3ee",
        "DANGER": "#f87171", "DANGER_HOVER": "#dc2626",
        "SUCCESS": "#4ade80", "SUCCESS_HOVER": "#22c55e",
        "TEXT": "#dbe7ea", "TEXT_DIM": "#8fb0b6", "TEXT_FAINT": "#4d6469",
        "BORDER": "#16292e", "BORDER_LIGHT": "#1c383f",
    },
    # ── ธีมเพิ่มเติม (2026-09) — ทั้งหมดเป็นโทนมืด เหมือนธีมเดิม ──
    "sakura_night": {   # ชมพูซากุระบนพื้นบอร์โดว์เข้ม
        "BG": "#150b14", "BG_DARK": "#0e070d", "CARD": "#211220",
        "CARD_HI": "#2c1a2b", "CARD_HOVER": "#35213a",
        "ACCENT": "#ec4899", "ACCENT_HOVER": "#be185d", "ACCENT_2": "#a78bfa",
        "HEADING": "#f9a8d4",
        "DANGER": "#f87171", "DANGER_HOVER": "#ef4444",
        "SUCCESS": "#34d399", "SUCCESS_HOVER": "#10b981",
        "TEXT": "#f6e9f1", "TEXT_DIM": "#cbb0c2", "TEXT_FAINT": "#8c7085",
        "BORDER": "#40243c", "BORDER_LIGHT": "#56324f",
    },
    "forest_moss": {    # เขียวมะนาวบนพื้นเขียวป่าเข้ม
        "BG": "#0b130e", "BG_DARK": "#070d09", "CARD": "#111d15",
        "CARD_HI": "#17271d", "CARD_HOVER": "#1c3024",
        "ACCENT": "#84cc16", "ACCENT_HOVER": "#a3e635", "ACCENT_2": "#2dd4bf",
        "HEADING": "#bef264",
        "DANGER": "#f87171", "DANGER_HOVER": "#ef4444",
        "SUCCESS": "#34d399", "SUCCESS_HOVER": "#10b981",
        "TEXT": "#e6f0e8", "TEXT_DIM": "#a9c2af", "TEXT_FAINT": "#66806e",
        "BORDER": "#1f3627", "BORDER_LIGHT": "#2b4a36",
    },
    "ocean_royal": {    # น้ำเงินรอยัลบนพื้นกรมท่าเข้ม
        "BG": "#0a1020", "BG_DARK": "#060a15", "CARD": "#111a30",
        "CARD_HI": "#182442", "CARD_HOVER": "#1d2b4f",
        "ACCENT": "#3b82f6", "ACCENT_HOVER": "#2563eb", "ACCENT_2": "#38bdf8",
        "HEADING": "#93c5fd",
        "DANGER": "#f87171", "DANGER_HOVER": "#ef4444",
        "SUCCESS": "#34d399", "SUCCESS_HOVER": "#10b981",
        "TEXT": "#e6edf9", "TEXT_DIM": "#a6b6d2", "TEXT_FAINT": "#66779a",
        "BORDER": "#22305a", "BORDER_LIGHT": "#2f4177",
    },
    "golden_hour": {    # ทองบนพื้นดำอมน้ำตาลเทา (ไม่ซ้ำกับ Ember ที่เป็นส้ม-น้ำตาล)
        "BG": "#0f0e0b", "BG_DARK": "#080706", "CARD": "#1a1813",
        "CARD_HI": "#252219", "CARD_HOVER": "#2e2a1e",
        "ACCENT": "#eab308", "ACCENT_HOVER": "#facc15", "ACCENT_2": "#38bdf8",
        "HEADING": "#fde68a",
        "DANGER": "#f87171", "DANGER_HOVER": "#ef4444",
        "SUCCESS": "#4ade80", "SUCCESS_HOVER": "#22c55e",
        "TEXT": "#f3efe4", "TEXT_DIM": "#c2b99f", "TEXT_FAINT": "#877f69",
        "BORDER": "#352f20", "BORDER_LIGHT": "#4a4230",
    },
    "graphite_mist": {  # โทนเทากราไฟต์เรียบๆ สบายตา — เน้นตัวอักษร ไม่มีสีฉูดฉาด
        "BG": "#0f1114", "BG_DARK": "#090a0c", "CARD": "#181b20",
        "CARD_HI": "#20242b", "CARD_HOVER": "#282d35",
        "ACCENT": "#94a3b8", "ACCENT_HOVER": "#cbd5e1", "ACCENT_2": "#7dd3fc",
        "HEADING": "#e2e8f0",
        "DANGER": "#f87171", "DANGER_HOVER": "#ef4444",
        "SUCCESS": "#4ade80", "SUCCESS_HOVER": "#22c55e",
        "TEXT": "#e8ebf0", "TEXT_DIM": "#a3acb9", "TEXT_FAINT": "#6b7482",
        "BORDER": "#2b313a", "BORDER_LIGHT": "#3a424e",
    },
    # ── ธีมเพิ่มเติมชุดที่ 2 (2026-09) ──
    "teal_lagoon": {    # เขียวน้ำทะเลสีเทอร์คอยส์บนพื้นเขียวอมฟ้าเข้ม
        "BG": "#071211", "BG_DARK": "#040b0a", "CARD": "#0d1f1d",
        "CARD_HI": "#132a27", "CARD_HOVER": "#18342f",
        "ACCENT": "#14b8a6", "ACCENT_HOVER": "#2dd4bf", "ACCENT_2": "#818cf8",
        "HEADING": "#5eead4",
        "DANGER": "#f87171", "DANGER_HOVER": "#ef4444",
        "SUCCESS": "#4ade80", "SUCCESS_HOVER": "#22c55e",
        "TEXT": "#e2f2f0", "TEXT_DIM": "#9fc4bf", "TEXT_FAINT": "#5f807b",
        "BORDER": "#17403b", "BORDER_LIGHT": "#21574f",
    },
    "midnight_indigo": {  # อินดิโกเข้มแบบท้องฟ้ายามค่ำ
        "BG": "#0c0b22", "BG_DARK": "#07061a", "CARD": "#16153a",
        "CARD_HI": "#1e1d4a", "CARD_HOVER": "#25235a",
        "ACCENT": "#5f62ee", "ACCENT_HOVER": "#4f46e5", "ACCENT_2": "#2dd4bf",
        "HEADING": "#a5b4fc",
        "DANGER": "#f87171", "DANGER_HOVER": "#ef4444",
        "SUCCESS": "#34d399", "SUCCESS_HOVER": "#10b981",
        "TEXT": "#e8e9fb", "TEXT_DIM": "#aeb0d8", "TEXT_FAINT": "#7274a3",
        "BORDER": "#2b2a63", "BORDER_LIGHT": "#3a3985",
    },
    "neon_fuchsia": {   # ม่วงบานเย็นนีออนบนพื้นม่วงดำ
        "BG": "#14081a", "BG_DARK": "#0d0511", "CARD": "#221030",
        "CARD_HI": "#2e1741", "CARD_HOVER": "#391d50",
        "ACCENT": "#d946ef", "ACCENT_HOVER": "#a21caf", "ACCENT_2": "#22d3ee",
        "HEADING": "#f0abfc",
        "DANGER": "#f87171", "DANGER_HOVER": "#ef4444",
        "SUCCESS": "#4ade80", "SUCCESS_HOVER": "#22c55e",
        "TEXT": "#f7e9fb", "TEXT_DIM": "#cfaed8", "TEXT_FAINT": "#8f6f9b",
        "BORDER": "#43205c", "BORDER_LIGHT": "#5a2d7b",
    },
    "crimson_noir": {   # แดงเข้มบนพื้นดำอมแดง
        "BG": "#140a0c", "BG_DARK": "#0c0607", "CARD": "#1f1013",
        "CARD_HI": "#2b171b", "CARD_HOVER": "#351d22",
        "ACCENT": "#e11d48", "ACCENT_HOVER": "#be123c", "ACCENT_2": "#38bdf8",
        "HEADING": "#fda4af",
        "DANGER": "#f87171", "DANGER_HOVER": "#ef4444",
        "SUCCESS": "#34d399", "SUCCESS_HOVER": "#10b981",
        "TEXT": "#f8e8ea", "TEXT_DIM": "#cfaeb3", "TEXT_FAINT": "#8f6f75",
        "BORDER": "#40202a", "BORDER_LIGHT": "#57303c",
    },
    "lavender_mist": {  # ลาเวนเดอร์พาสเทลบนพื้นม่วงเทาเข้ม — นุ่มตา
        "BG": "#100e1a", "BG_DARK": "#0a0912", "CARD": "#1a1727",
        "CARD_HI": "#231f34", "CARD_HOVER": "#2b2640",
        "ACCENT": "#c4b5fd", "ACCENT_HOVER": "#ddd6fe", "ACCENT_2": "#67e8f9",
        "HEADING": "#ddd6fe",
        "DANGER": "#f87171", "DANGER_HOVER": "#ef4444",
        "SUCCESS": "#4ade80", "SUCCESS_HOVER": "#22c55e",
        "TEXT": "#ece9f6", "TEXT_DIM": "#b3adc8", "TEXT_FAINT": "#7d7794",
        "BORDER": "#2f2a45", "BORDER_LIGHT": "#40395c",
    },
    "mocha_latte": {    # น้ำตาลกาแฟ + ครีมลาเต้ อบอุ่น
        "BG": "#14100d", "BG_DARK": "#0c0907", "CARD": "#1f1915",
        "CARD_HI": "#2a221c", "CARD_HOVER": "#342b23",
        "ACCENT": "#d6a77a", "ACCENT_HOVER": "#e7c29d", "ACCENT_2": "#7dd3fc",
        "HEADING": "#ecd3b6",
        "DANGER": "#f87171", "DANGER_HOVER": "#ef4444",
        "SUCCESS": "#4ade80", "SUCCESS_HOVER": "#22c55e",
        "TEXT": "#f1e9e0", "TEXT_DIM": "#c4b4a3", "TEXT_FAINT": "#86776a",
        "BORDER": "#3a2f26", "BORDER_LIGHT": "#4e4034",
    },
    "oled_black": {     # ดำสนิท (ประหยัดไฟจอ OLED) + ฟ้าสว่าง
        "BG": "#000000", "BG_DARK": "#000000", "CARD": "#0c0c0f",
        "CARD_HI": "#141418", "CARD_HOVER": "#1b1b21",
        "ACCENT": "#38bdf8", "ACCENT_HOVER": "#7dd3fc", "ACCENT_2": "#a78bfa",
        "HEADING": "#7dd3fc",
        "DANGER": "#f87171", "DANGER_HOVER": "#ef4444",
        "SUCCESS": "#4ade80", "SUCCESS_HOVER": "#22c55e",
        "TEXT": "#ececf1", "TEXT_DIM": "#a0a0ad", "TEXT_FAINT": "#6a6a78",
        "BORDER": "#1f1f27", "BORDER_LIGHT": "#2c2c36",
    },
    "arctic_ice": {     # ฟ้าไอซ์บลูประกายหิมะ หรูหรา สะอาดตา
        "BG": "#080e18", "BG_DARK": "#04070d", "CARD": "#0e1828",
        "CARD_HI": "#142238", "CARD_HOVER": "#1a2b47",
        "ACCENT": "#38bdf8", "ACCENT_HOVER": "#0284c7", "ACCENT_2": "#a5f3fc",
        "HEADING": "#bae6fd",
        "DANGER": "#f87171", "DANGER_HOVER": "#ef4444",
        "SUCCESS": "#34d399", "SUCCESS_HOVER": "#10b981",
        "TEXT": "#e0f2fe", "TEXT_DIM": "#93c5fd", "TEXT_FAINT": "#5b7b9d",
        "BORDER": "#1c2e4a", "BORDER_LIGHT": "#284269",
    },
    "sunset_coral": {   # ส้มพีชคอรัล อบอุ่น มีชีวิตชีวา
        "BG": "#150d12", "BG_DARK": "#0e070b", "CARD": "#22141c",
        "CARD_HI": "#2e1b26", "CARD_HOVER": "#3b2230",
        "ACCENT": "#fb7185", "ACCENT_HOVER": "#e11d48", "ACCENT_2": "#fb923c",
        "HEADING": "#fecdd3",
        "DANGER": "#ef4444", "DANGER_HOVER": "#dc2626",
        "SUCCESS": "#34d399", "SUCCESS_HOVER": "#10b981",
        "TEXT": "#fdf2f4", "TEXT_DIM": "#cca5b0", "TEXT_FAINT": "#8f6b76",
        "BORDER": "#432233", "BORDER_LIGHT": "#592e44",
    },
    "cyber_matrix": {   # เขียวเมทริกซ์นีออน สไตล์แฮกเกอร์ ดุดัน
        "BG": "#070e0a", "BG_DARK": "#030705", "CARD": "#0e1c14",
        "CARD_HI": "#14271c", "CARD_HOVER": "#1a3325",
        "ACCENT": "#22c55e", "ACCENT_HOVER": "#16a34a", "ACCENT_2": "#06b6d4",
        "HEADING": "#86efac",
        "DANGER": "#f87171", "DANGER_HOVER": "#ef4444",
        "SUCCESS": "#4ade80", "SUCCESS_HOVER": "#22c55e",
        "TEXT": "#e6f9ed", "TEXT_DIM": "#9dc4a9", "TEXT_FAINT": "#5b7e66",
        "BORDER": "#1b3826", "BORDER_LIGHT": "#275237",
    },
    "matcha_mellow": {  # มัทฉะชาเขียวมินิมอล ผ่อนคลาย สบายตา
        "BG": "#11140e", "BG_DARK": "#0a0d08", "CARD": "#1a2016",
        "CARD_HI": "#232c1e", "CARD_HOVER": "#2d3827",
        "ACCENT": "#84cc16", "ACCENT_HOVER": "#65a30d", "ACCENT_2": "#eab308",
        "HEADING": "#d9f99d",
        "DANGER": "#f87171", "DANGER_HOVER": "#ef4444",
        "SUCCESS": "#4ade80", "SUCCESS_HOVER": "#22c55e",
        "TEXT": "#f2f7ec", "TEXT_DIM": "#b3c2a6", "TEXT_FAINT": "#738267",
        "BORDER": "#303b29", "BORDER_LIGHT": "#425239",
    },
}

THEME_ORDER = ["default", "aurora_violet", "ember_dusk", "nightwave_cyan",
               "sakura_night", "forest_moss", "ocean_royal", "golden_hour", "graphite_mist",
               "teal_lagoon", "midnight_indigo", "neon_fuchsia", "crimson_noir",
               "lavender_mist", "mocha_latte", "oled_black",
               "arctic_ice", "sunset_coral", "cyber_matrix", "matcha_mellow"]
THEME_LABELS = {
    "default": "ค่าเริ่มต้น (ม่วง-กรมท่า)",
    "aurora_violet": "Aurora Violet",
    "ember_dusk": "Ember Dusk",
    "nightwave_cyan": "Nightwave Cyan",
    "sakura_night": "Sakura Night (ชมพู)",
    "forest_moss": "Forest Moss (เขียว)",
    "ocean_royal": "Ocean Royal (น้ำเงิน)",
    "golden_hour": "Golden Hour (ทอง)",
    "graphite_mist": "Graphite Mist (เทา)",
    "teal_lagoon": "Teal Lagoon (เขียวน้ำทะเล)",
    "midnight_indigo": "Midnight Indigo (อินดิโก)",
    "neon_fuchsia": "Neon Fuchsia (บานเย็น)",
    "crimson_noir": "Crimson Noir (แดงเข้ม)",
    "lavender_mist": "Lavender Mist (ลาเวนเดอร์)",
    "mocha_latte": "Mocha Latte (น้ำตาลกาแฟ)",
    "oled_black": "Pure Black (ดำสนิท)",
    "arctic_ice": "Arctic Ice (ธารน้ำแข็ง)",
    "sunset_coral": "Sunset Coral (ส้มคอรัล)",
    "cyber_matrix": "Cyber Matrix (นีออนเขียว)",
    "matcha_mellow": "Matcha Mellow (มัทฉะ)",
}
# ★ swatch สีเด่นของแต่ละธีม (ใช้โชว์ preview ใน Settings)
THEME_SWATCH = {k: v["ACCENT"] for k, v in THEMES.items()}


def _luma(hex_color: str) -> float:
    """ความสว่างคร่าวๆ ของสี hex (0=ดำ, 255=ขาว) — ใช้เลือกสีตัวอักษรที่อ่านออก"""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (r * 299 + g * 587 + b * 114) / 1000


def _readable_on(hex_color: str, dark: str = "#0b0e14", light: str = "#ffffff") -> str:
    """เลือกสีตัวอักษรที่อ่านง่ายบนพื้น hex_color — พื้นสว่างเกิน threshold ใช้ตัวหนังสือเข้มแทนขาว

    ★ Qt Style Sheets ไม่รองรับ text-shadow/box-shadow (ไม่อยู่ใน property ที่ QSS รองรับเลย)
      วิธีแก้ contrast ที่ถูกต้องคือสลับสีตัวอักษรตามความสว่างพื้นหลัง แทนการใส่เงา
    """
    return dark if _luma(hex_color) > 150 else light


def _rel_lum(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    def ch(v):
        v = int(v, 16) / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(h[0:2]) + 0.7152 * ch(h[2:4]) + 0.0722 * ch(h[4:6])


def _best_text_on(hex_color: str, dark: str = "#0b0e14", light: str = "#ffffff") -> str:
    """เลือกขาว/เกือบดำตาม contrast จริง (WCAG) — แม่นกว่า _readable_on ที่เทียบแค่ความสว่างหยาบๆ"""
    lb = _rel_lum(hex_color)
    def c(fg):
        lf = _rel_lum(fg)
        return (max(lf, lb) + 0.05) / (min(lf, lb) + 0.05)
    return dark if c(dark) >= c(light) else light


# ★ ธีมเดิม 4 ธีม: คงกติกาเดิม (_readable_on) เพื่อไม่ให้หน้าตาที่ผู้ใช้เคยเห็นเปลี่ยน
#   ธีมที่เพิ่มทีหลัง: ใช้ contrast จริง
_LEGACY_THEMES = {"default", "aurora_violet", "ember_dusk", "nightwave_cyan"}

# ★ เติมสีตัวอักษรที่อ่านออกให้ทุกธีม (คำนวณจาก ACCENT/DANGER/SUCCESS/HEADING ของธีมนั้นๆ)
#   ใช้กับปุ่ม state="on"/"danger"/"warning" (topbar split-button) + ปุ่ม TTS เขียว/แดง + ปุ่ม Primary/Danger/Success
for _key, _pal in THEMES.items():
    _on = _readable_on if _key in _LEGACY_THEMES else _best_text_on
    _pal["ON_ACCENT_TEXT"] = _on(_pal["ACCENT"])
    _pal["ON_DANGER_TEXT"] = _on(_pal["DANGER"])
    _pal["ON_SUCCESS_TEXT"] = _on(_pal["SUCCESS"])
    _pal["ON_WARNING_TEXT"] = _on(_pal["HEADING"])
    # ★ ตัวอักษรบนปุ่มตอน hover (พื้นเปลี่ยนเป็นสี *_HOVER — บางธีมสว่างขึ้น บางธีมเข้มลง เลยต้องคำนวณแยก)
    _pal["ON_ACCENT_HOVER_TEXT"] = _on(_pal["ACCENT_HOVER"])
    _pal["ON_DANGER_HOVER_TEXT"] = _on(_pal["DANGER_HOVER"])
    _pal["ON_SUCCESS_HOVER_TEXT"] = _on(_pal["SUCCESS_HOVER"])


# ════════════════════════════════════════════════════════
# ★ โทเคนสีที่คำนวณต่อธีม (2026-09) — แทนที่สี hex ตายตัวของธีม default ที่เคยฝังใน widget
#   หลักการ: "default" ต้องได้ค่าเดิมเป๊ะ (ผู้ใช้เดิมหน้าตาไม่เปลี่ยน) / ธีมอื่นได้สีที่ derive จากพาเลตของธีมนั้น
# ════════════════════════════════════════════════════════
def _mix(a: str, b: str, t: float) -> str:
    """ผสมสี a→b ที่สัดส่วน t (0=a, 1=b)"""
    a, b = a.lstrip("#"), b.lstrip("#")
    ca = [int(a[i:i + 2], 16) for i in (0, 2, 4)]
    cb = [int(b[i:i + 2], 16) for i in (0, 2, 4)]
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(ca, cb))


def rgba(hex_color: str, alpha: float) -> str:
    """'#rrggbb' + alpha(0-1) → 'rgba(r, g, b, a)' สำหรับ QSS"""
    h = hex_color.lstrip("#")
    return "rgba(%d, %d, %d, %s)" % (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha)


def _contrast(fg: str, bg: str) -> float:
    lf, lb = _rel_lum(fg), _rel_lum(bg)
    return (max(lf, lb) + 0.05) / (min(lf, lb) + 0.05)


# ธีมเดิมที่ปุ่มแดงอ่านออกอยู่แล้ว (ตัวอักษรขาวบนแดงเข้ม) — คงค่าเดิม
_DANGER_BTN_UNCHANGED = {"default", "ember_dusk"}
# ปุ่ม/ช่อง "ระดับ control" ของ chat panel + topbar ที่เดิมใช้โทน slate ตายตัว (Tailwind slate)
_SLATE = {
    "CTRL_BG": "#1e293b", "CTRL_BORDER": "#334155", "CTRL_BORDER_HI": "#475569", "CTRL_DEEP": "#0f172a",
    "CTRL_TEXT": "#e2e8f0", "CTRL_DIM": "#94a3b8", "CTRL_FAINT": "#64748b", "CTRL_SEP": "#475569",
}

for _key, _pal in THEMES.items():
    # ── ปุ่มแดง (#Danger / ปุ่มปิดอ่านบน topbar / ปุ่ม "หยุดเชื่อมต่อ"): ตัวอักษร "ขาว" เสมอ ──
    #    พื้นปุ่มเข้มลงเท่าที่จำเป็นให้ขาวอ่านชัด (WCAG >= 4.5:1) — ไม่แตะ DANGER เดิม (ยังใช้เป็นสีข้อความ/ไอคอนบนพื้นมืด)
    _white = "#ffffff"
    _pal["ON_DANGER_TEXT"] = _white
    _pal["ON_DANGER_HOVER_TEXT"] = _white
    if _key in _DANGER_BTN_UNCHANGED:
        _pal["DANGER_BTN"], _pal["DANGER_BTN_HOVER"] = _pal["DANGER"], _pal["DANGER_HOVER"]
    else:
        # เข้มลงแบบคงเฉด + เพิ่มความอิ่มสี (ผสมกับดำตรงๆ จะได้แดงหม่นออกอิฐ) จนขาวอ่านชัด
        import colorsys as _cs
        _rgb = [int(_pal["DANGER"].lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        _h, _s, _v = _cs.rgb_to_hsv(*_rgb)
        _s = max(_s, 0.80)
        _bg = _pal["DANGER"]
        while _v > 0.30:
            _bg = "#%02x%02x%02x" % tuple(round(c * 255) for c in _cs.hsv_to_rgb(_h, _s, _v))
            if _contrast(_white, _bg) >= 4.5:
                break
            _v -= 0.01
        _pal["DANGER_BTN"] = _bg
        _pal["DANGER_BTN_HOVER"] = _mix(_bg, "#000000", 0.14)

    # ── สีแถบสลับ (zebra) ของแถวแชท: ยกพื้นหลังเล็กน้อยไปทางสี ACCENT ของธีม ให้เห็นชัดแต่ไม่แย่งตัวอักษร ──
    if _key == "default":
        _pal["ZEBRA"] = "#101524"                      # ค่าเดิมของโปรแกรม
    else:
        _t = 0.05
        _zb = _mix(_pal["BG"], _pal["ACCENT"], _t)
        while _contrast(_zb, _pal["BG"]) < 1.10 and _t < 0.30:
            _t += 0.01
            _zb = _mix(_pal["BG"], _pal["ACCENT"], _t)
        _pal["ZEBRA"] = _zb

    # ── เส้นขอบปุ่ม "หยุดเชื่อมต่อ": default/ember คงเดิม / ธีมอื่นใช้แดงสดเท่ากับพื้นปุ่มแดง (ไม่เข้มจนจม) ──
    _pal["DANGER_EDGE"] = _pal["DANGER_HOVER"] if _key in _DANGER_BTN_UNCHANGED else _pal["DANGER_BTN"]
    # ── เทาอ่อน/เทาเข้มที่ sidebar ใช้ (default = ค่าเดิม) ──
    _pal["TEXT_SOFT"] = "#d1d5db" if _key == "default" else _mix(_pal["TEXT"], _pal["TEXT_DIM"], 0.45)
    _pal["TEXT_MUTE"] = "#4b5563" if _key == "default" else _pal["TEXT_FAINT"]

    # ── สี accent อ่อน (ข้อความ/ชิปบนพื้นมืด) ──
    _pal["ACCENT_SOFT"] = "#a78bfa" if _key == "default" else _mix(_pal["ACCENT"], "#ffffff", 0.40)

    # ── โทน "control" (เดิม slate ตายตัว): default = ค่าเดิมเป๊ะ / ธีมอื่น = derive จากพาเลต ──
    if _key == "default":
        _pal.update(_SLATE)
    else:
        _pal.update({
            "CTRL_BG": _pal["CARD_HI"], "CTRL_BORDER": _pal["BORDER"], "CTRL_BORDER_HI": _pal["BORDER_LIGHT"],
            "CTRL_DEEP": _pal["BG_DARK"], "CTRL_TEXT": _pal["TEXT"], "CTRL_DIM": _pal["TEXT_DIM"],
            "CTRL_FAINT": _pal["TEXT_FAINT"], "CTRL_SEP": _pal["TEXT_FAINT"],
        })

# ═══════════════════════════════════════════════════════════════
# Color constants (module-level) — apply_theme() จะเขียนทับตัวแปรพวกนี้
# ตาม theme ที่เลือกไว้ใน settings ตอนเปิดโปรแกรม (ก่อนสร้าง widget ใดๆ)
# ★ ไฟล์ widget อื่นที่ต้องการสีให้ตรงธีมสด ต้อง `import ui.theme as theme` แล้วอ้าง
#   `theme.COLOR_X` ตอนสร้าง widget (ไม่ใช่ `from ui.theme import COLOR_X` ที่ตายตัว
#   ตั้งแต่ตอน import module — ค่าจะไม่ขยับตามถ้า apply_theme() มาทีหลัง)
# ═══════════════════════════════════════════════════════════════
COLOR_BG = THEMES["default"]["BG"]
COLOR_BG_DARK = THEMES["default"]["BG_DARK"]
COLOR_CARD = THEMES["default"]["CARD"]
COLOR_CARD_HI = THEMES["default"]["CARD_HI"]
COLOR_CARD_HOVER = THEMES["default"]["CARD_HOVER"]
COLOR_ACCENT = THEMES["default"]["ACCENT"]
COLOR_ACCENT_HOVER = THEMES["default"]["ACCENT_HOVER"]
COLOR_ACCENT_2 = THEMES["default"]["ACCENT_2"]
COLOR_HEADING = THEMES["default"]["HEADING"]
COLOR_DANGER = THEMES["default"]["DANGER"]
COLOR_DANGER_HOVER = THEMES["default"]["DANGER_HOVER"]
COLOR_SUCCESS = THEMES["default"]["SUCCESS"]
COLOR_SUCCESS_HOVER = THEMES["default"]["SUCCESS_HOVER"]
COLOR_TEXT = THEMES["default"]["TEXT"]
COLOR_TEXT_DIM = THEMES["default"]["TEXT_DIM"]
COLOR_TEXT_FAINT = THEMES["default"]["TEXT_FAINT"]
COLOR_BORDER = THEMES["default"]["BORDER"]
COLOR_BORDER_LIGHT = THEMES["default"]["BORDER_LIGHT"]
COLOR_ON_ACCENT_TEXT = THEMES["default"]["ON_ACCENT_TEXT"]
COLOR_ON_DANGER_TEXT = THEMES["default"]["ON_DANGER_TEXT"]
COLOR_ON_SUCCESS_TEXT = THEMES["default"]["ON_SUCCESS_TEXT"]
COLOR_ON_WARNING_TEXT = THEMES["default"]["ON_WARNING_TEXT"]
COLOR_DANGER_BTN = THEMES["default"]["DANGER_BTN"]
COLOR_DANGER_BTN_HOVER = THEMES["default"]["DANGER_BTN_HOVER"]
COLOR_ZEBRA = THEMES["default"]["ZEBRA"]
COLOR_ACCENT_SOFT = THEMES["default"]["ACCENT_SOFT"]
COLOR_CTRL_BG = THEMES["default"]["CTRL_BG"]
COLOR_CTRL_BORDER = THEMES["default"]["CTRL_BORDER"]
COLOR_CTRL_BORDER_HI = THEMES["default"]["CTRL_BORDER_HI"]
COLOR_CTRL_DEEP = THEMES["default"]["CTRL_DEEP"]
COLOR_CTRL_TEXT = THEMES["default"]["CTRL_TEXT"]
COLOR_CTRL_DIM = THEMES["default"]["CTRL_DIM"]
COLOR_CTRL_FAINT = THEMES["default"]["CTRL_FAINT"]
COLOR_CTRL_SEP = THEMES["default"]["CTRL_SEP"]

# ════════════════════════════════════════════════════════
# ★ Live re-theme: widget ที่ตั้งสีด้วย setStyleSheet() ตรงๆ (ไม่ผ่าน QSS กลาง) ลงทะเบียนเมธอด
#   refresh ของตัวเองที่นี่ → apply_theme() เรียกให้ทุกครั้งที่สลับธีม (ไม่ต้องรีสตาร์ท)
# ════════════════════════════════════════════════════════
import re as _re
import weakref as _weakref
_THEME_LISTENERS = []

# ── ตัวช่วยกลาง: แปลงสี hex "ของธีม default" ที่ฝังในสไตล์ชีตให้เป็นสีของธีมปัจจุบัน ──
#    ใช้ theme.styled(widget, "color: #9ca3af; ...") แทน widget.setStyleSheet(...) →
#    (1) ได้สีตามธีมที่เลือกตั้งแต่สร้าง (2) รีเฟรชสดเมื่อสลับธีม (3) ธีม default ได้ค่าเดิมเป๊ะ (แปลง hex เป็นตัวมันเอง)
_HEX_TOKEN_ORDER = ["BG", "BG_DARK", "CARD", "CARD_HI", "CARD_HOVER", "ACCENT", "ACCENT_HOVER", "ACCENT_2", "HEADING",
                    "DANGER", "DANGER_HOVER", "SUCCESS", "SUCCESS_HOVER", "TEXT", "TEXT_DIM", "TEXT_FAINT", "BORDER",
                    "BORDER_LIGHT", "CTRL_BG", "CTRL_BORDER", "CTRL_BORDER_HI", "CTRL_DEEP", "CTRL_TEXT", "CTRL_DIM",
                    "CTRL_FAINT", "ACCENT_SOFT", "TEXT_SOFT", "TEXT_MUTE"]
_DEFAULT_HEX_TO_TOKEN = {}
for _k in _HEX_TOKEN_ORDER:
    _DEFAULT_HEX_TO_TOKEN.setdefault(THEMES["default"][_k].lower(), _k)
_HEX_RE = _re.compile(r"#[0-9a-fA-F]{6}\b")
_ACCENT_RGBA_RE = _re.compile(r"rgba\(\s*124\s*,\s*58\s*,\s*237\s*,")
_CURRENT_PALETTE = THEMES["default"]


def T(css: str) -> str:
    """แปลงสีของธีม default ในสตริงสไตล์ชีต → สีของธีมปัจจุบัน (สีที่ไม่ใช่ของพาเลต เช่นสีแพลตฟอร์ม คงเดิม)"""
    pal = _CURRENT_PALETTE

    def _sub(m):
        key = _DEFAULT_HEX_TO_TOKEN.get(m.group(0).lower())
        return pal[key] if key else m.group(0)
    css = _HEX_RE.sub(_sub, css)
    h = pal["ACCENT"].lstrip("#")
    return _ACCENT_RGBA_RE.sub("rgba(%d, %d, %d," % (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)), css)


_STYLED = _weakref.WeakKeyDictionary()      # widget -> สไตล์ชีตต้นฉบับ (ก่อนแปลง)


def styled(widget, css: str) -> None:
    """setStyleSheet(T(css)) + จำไว้เพื่อรีเฟรชอัตโนมัติเมื่อสลับธีม (เรียกซ้ำกับ widget เดิม = แทนที่สไตล์ชีตที่จำไว้)"""
    try:
        _STYLED[widget] = css
    except TypeError:
        pass
    widget.setStyleSheet(T(css))


def _restyle_registered() -> None:
    for w, css in list(_STYLED.items()):
        try:
            w.setStyleSheet(T(css))
        except RuntimeError:
            pass                      # C++ object ถูกลบไปแล้ว


def register_theme_listener(bound_method) -> None:
    """ลงทะเบียน bound method (เช่น self._apply_theme_styles) — เก็บแบบ weak ไม่ค้าง widget ที่ถูกลบ"""
    # การ์ด Events ถูกสร้างต่อเนื่องตลอดเซสชัน → ล้างรายการของ widget ที่ถูกลบแล้วเป็นระยะ กันลิสต์โตไม่จำกัด
    if len(_THEME_LISTENERS) >= 256 and len(_THEME_LISTENERS) % 128 == 0:
        _THEME_LISTENERS[:] = [r for r in _THEME_LISTENERS if r() is not None]
    try:
        _THEME_LISTENERS.append(_weakref.WeakMethod(bound_method))
    except TypeError:
        _THEME_LISTENERS.append(lambda f=bound_method: f)


def notify_theme_changed() -> None:
    """เรียกทุก listener (ข้ามตัวที่ widget ถูกลบไปแล้ว / error ของตัวใดตัวหนึ่งไม่ทำให้ตัวอื่นพัง)"""
    import logging as _logging
    alive = []
    for ref in list(_THEME_LISTENERS):
        fn = ref()
        if fn is None:
            continue
        try:
            fn()
            alive.append(ref)
        except RuntimeError:
            pass                  # C++ object ถูกลบไปแล้ว — ตัดออกจากรายการ
        except Exception as e:    # pragma: no cover
            alive.append(ref)
            _logging.getLogger("theme").warning("theme listener failed: %s", e)
    _THEME_LISTENERS[:] = alive

# ═══════════════════════════════════════════════════════════════
# Fonts
# ═══════════════════════════════════════════════════════════════
def setup_fonts(app: QApplication) -> None:
    """ตั้ง font default + โหลด Kanit + NotoSansThai (fallback ภาษาไทย)"""
    import os, sys
    # ★ หา assets/fonts path — รองรับทั้ง dev + PyInstaller frozen
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        fonts_dir = os.path.join(exe_dir, "_internal", "assets", "fonts")
        if not os.path.isdir(fonts_dir):
            fonts_dir = os.path.join(exe_dir, "assets", "fonts")
    else:
        fonts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "fonts")

    # ★ โหลด Kanit (ถ้ามี) + NotoSansThai (fallback ภาษาไทย — ติดมากับโปรแกรมเสมอ)
    font_files = [
        "Kanit-Regular.ttf", "Kanit-Medium.ttf", "Kanit-SemiBold.ttf", "Kanit-Bold.ttf",
        "NotoSansThai-Regular.ttf", "NotoSansThai-Medium.ttf", "NotoSansThai-Bold.ttf",
    ]
    for fname in font_files:
        p = os.path.join(fonts_dir, fname)
        if os.path.exists(p):
            QFontDatabase.addApplicationFont(p)

    # ★ default font — Kanit ถ้ามี, ถ้าไม่มี Qt จะ fallback เป็น NotoSansThai อัตโนมัติ
    font = QFont("Kanit", 11)
    font.setStyleHint(QFont.SansSerif)
    app.setFont(font)


# ═══════════════════════════════════════════════════════════════
# QSS Stylesheet — Modern Flat Design
# ═══════════════════════════════════════════════════════════════
QSS = """
/* ═══ Global ═══ */
* {
    font-family: 'Kanit', 'Noto Sans Thai', 'Segoe UI', sans-serif;
    color: __TEXT__;
    outline: none;
}

QWidget {
    background-color: __BG__;
    font-size: 16px;
}

/* ★ label — ไม่ตัดความสูง */
QLabel {
    background-color: transparent;
    color: __TEXT__;
    min-height: 20px;
    font-size: 16px;
}

/* ═══ Windows ═══ */
QMainWindow, QDialog {
    background-color: __BG__;
}

/* ═══ Frames / Panels ═══ */
QFrame#Sidebar {
    background-color: __BG_DARK__;
    border-right: 1px solid __BORDER__;
}
QFrame#TopBar {
    background-color: __CARD__;
    border-bottom: 1px solid __BORDER__;
}
QFrame#StatusBar {
    background-color: __CARD__;
    border-top: 1px solid __BORDER__;
}
QFrame#ChatPanel {
    background-color: __BG__;
}
QFrame#EventsPanel {
    background-color: __CARD__;
    border-left: 1px solid __BORDER__;
}

/* ═══ Cards ═══ */
QFrame#Card {
    background-color: __CARD__;
    border-radius: 8px;
    border: 1px solid __BORDER__;
}

/* ═══ Buttons ═══ */
QPushButton {
    background-color: __CARD_HI__;
    border: 2px solid __BORDER_LIGHT__;
    border-radius: 6px;
    padding: 8px 16px;
    color: __TEXT__;
    font-weight: 600;
    font-size: 16px;
    min-height: 22px;
}
QPushButton:hover {
    background-color: __CARD_HOVER__;
    border-color: __ACCENT__;
}
QPushButton:pressed {
    background-color: __CARD__;
}
QPushButton:disabled {
    color: __TEXT_FAINT__;
    background-color: __CARD__;
    border-color: __BORDER__;
}

/* Primary button (accent) */
QPushButton#Primary {
    background-color: __ACCENT__;
    border: 2px solid __ACCENT_HOVER__;
    color: __ON_ACCENT_TEXT__;
    font-weight: 600;
}
QPushButton#Primary:hover {
    background-color: __ACCENT_HOVER__;
    color: __ON_ACCENT_HOVER_TEXT__;
}

/* Danger button */
QPushButton#Danger {
    background-color: __DANGER_BTN__;
    border: 2px solid __DANGER_EDGE__;
    color: __ON_DANGER_TEXT__;
    font-weight: 600;
}
QPushButton#Danger:hover {
    background-color: __DANGER_BTN_HOVER__;
    color: __ON_DANGER_HOVER_TEXT__;
    border-color: #fca5a5;
}

/* Success button */
QPushButton#Success {
    background-color: __SUCCESS__;
    border: none;
    color: __ON_SUCCESS_TEXT__;
}
QPushButton#Success:hover {
    background-color: __SUCCESS_HOVER__;
    color: __ON_SUCCESS_HOVER_TEXT__;
}

/* Icon button (topbar/chat panel — flat, no border) */
QPushButton#IconButton {
    background-color: transparent;
    border: none;
    padding: 2px 4px;
    font-size: 16px;
    border-radius: 6px;
}
QPushButton#IconButton:hover {
    background-color: __CARD_HI__;
}

/* ═══ SplitButton (QPushButton — topbar split button with dropdown) ═══ */
/* flat pill design — main button + arrow button คู่กัน */
QPushButton#SplitButtonMain {
    background-color: rgba(255, 255, 255, 0.04);
    border: none;
    border-radius: 14px 0 0 14px;
    padding: 4px 6px 4px 14px;
    font-size: 12px;
    font-weight: 600;
    color: __TEXT_DIM__;
    min-height: 18px;
}
QPushButton#SplitButtonMain:hover {
    background-color: rgba(255, 255, 255, 0.10);
    color: __TEXT__;
}
QPushButton#SplitButtonMain:pressed {
    background-color: rgba(255, 255, 255, 0.06);
}
/* arrow button (dropdown) */
QPushButton#SplitButtonArrow {
    background-color: rgba(255, 255, 255, 0.04);
    border: none;
    border-radius: 0 14px 14px 0;
    padding: 4px 2px;
    font-size: 11px;
    color: __TEXT_DIM__;
    min-height: 18px;
}
QPushButton#SplitButtonArrow:hover {
    background-color: rgba(255, 255, 255, 0.10);
    color: __TEXT__;
}
/* ★ state="on" — accent (ม่วง) ตอนเปิดใช้งาน */
QPushButton#SplitButtonMain[state="on"],
QPushButton#SplitButtonArrow[state="on"] {
    background-color: __ACCENT__;
    color: __ON_ACCENT_TEXT__;
}
QPushButton#SplitButtonMain[state="on"]:hover,
QPushButton#SplitButtonArrow[state="on"]:hover {
    background-color: __ACCENT_HOVER__;
}
/* ★ state="danger" — แดง */
QPushButton#SplitButtonMain[state="danger"],
QPushButton#SplitButtonArrow[state="danger"] {
    background-color: __DANGER__;
    color: __ON_DANGER_TEXT__;
}
QPushButton#SplitButtonMain[state="danger"]:hover,
QPushButton#SplitButtonArrow[state="danger"]:hover {
    background-color: __DANGER_HOVER__;
}
/* ★ state="warning" — amber */
QPushButton#SplitButtonMain[state="warning"],
QPushButton#SplitButtonArrow[state="warning"] {
    background-color: __HEADING__;
    color: __ON_WARNING_TEXT__;
}
QPushButton#SplitButtonMain[state="warning"]:hover,
QPushButton#SplitButtonArrow[state="warning"]:hover {
    background-color: #d97706;
}

/* ═══ Input ═══ */
QLineEdit {
    background-color: __CARD__;
    border: 1px solid __BORDER__;
    border-radius: 6px;
    padding: 8px 12px;
    color: __TEXT__;
    selection-background-color: __ACCENT__;
}
QLineEdit:focus {
    border-color: __ACCENT__;
}
QLineEdit::placeholder {
    color: __TEXT_FAINT__;
}

QTextEdit, QPlainTextEdit {
    background-color: __CARD__;
    border: 1px solid __BORDER__;
    border-radius: 6px;
    padding: 8px;
    color: __TEXT__;
}

/* ═══ ComboBox ═══ */
QComboBox {
    background-color: __CARD__;
    border: 1px solid __BORDER__;
    border-radius: 6px;
    padding: 6px 12px;
    color: __TEXT__;
    min-height: 20px;
}
QComboBox:hover {
    border-color: __ACCENT__;
}
QComboBox::drop-down {
    border: none;
    width: 26px;
}
QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid __TEXT_DIM__;
    margin-right: 10px;
}
QComboBox QAbstractItemView {
    background-color: __CARD__;
    border: 1px solid __BORDER__;
    border-radius: 6px;
    padding: 4px;
    selection-background-color: __ACCENT__;
    outline: none;
}

/* ═══ CheckBox ═══ */
QCheckBox {
    spacing: 8px;
    color: __TEXT__;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 2px solid __BORDER_LIGHT__;
    background-color: __CARD__;
}
QCheckBox::indicator:checked {
    background-color: __ACCENT__;
    border-color: __ACCENT__;
    image: none;
}
QCheckBox::indicator:hover {
    border-color: __ACCENT__;
}

/* ═══ RadioButton ═══ */
QRadioButton {
    spacing: 8px;
    color: __TEXT__;
    font-size: 16px;
    padding: 4px;
}
QRadioButton::indicator {
    width: 18px;
    height: 18px;
    border-radius: 9px;
    border: 2px solid __BORDER_LIGHT__;
    background-color: __CARD__;
}
QRadioButton::indicator:checked {
    background-color: __ACCENT__;
    border-color: __ACCENT__;
}
QRadioButton::indicator:hover {
    border-color: __ACCENT__;
}

/* ═══ Slider ═══ */
QSlider::groove:horizontal {
    height: 6px;
    background: __CARD_HI__;
    border-radius: 3px;
}
QSlider::sub-page:horizontal {
    background: __ACCENT__;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    width: 16px;
    height: 16px;
    margin: -6px 0;
    background: white;
    border-radius: 8px;
    border: 2px solid __ACCENT__;
}
QSlider::handle:horizontal:hover {
    background: __ACCENT__;
}

/* ═══ ScrollArea ═══ */
QScrollArea {
    background-color: transparent;
    border: none;
}
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: __BORDER_LIGHT__;
    min-height: 30px;
    border-radius: 5px;
}
QScrollBar::handle:vertical:hover {
    background: __TEXT_FAINT__;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: __BORDER_LIGHT__;
    min-width: 30px;
    border-radius: 5px;
}
QScrollBar::handle:horizontal:hover {
    background: __TEXT_FAINT__;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}

/* ═══ Label ═══ */
QLabel {
    background-color: transparent;
    color: __TEXT__;
}
QLabel#Heading {
    color: __HEADING__;
    font-size: 16px;
    font-weight: 600;
}
QLabel#Dim {
    color: __TEXT_DIM__;
}
QLabel#Faint {
    color: __TEXT_FAINT__;
    font-size: 13px;
}
QLabel#Section {
    color: __ACCENT_2__;
    font-size: 14px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
}

/* ═══ ProgressBar ═══ */
QProgressBar {
    background-color: __CARD_HI__;
    border: none;
    border-radius: 4px;
    height: 8px;
    text-align: center;
    font-size: 12px;
    color: __TEXT_DIM__;
}
QProgressBar::chunk {
    background-color: __ACCENT__;
    border-radius: 4px;
}

/* ═══ Splitter ═══ */
QSplitter::handle {
    background-color: __BORDER__;
}
QSplitter::handle:horizontal {
    width: 1px;
}
QSplitter::handle:vertical {
    height: 1px;
}

/* ═══ ToolTip ═══ */
QToolTip {
    background-color: __CARD_HI__;
    color: __TEXT__;
    border: 1px solid __BORDER__;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 14px;
}

/* ═══ Menu (context menu / dropdown) ═══ */
QMenu {
    background-color: __CARD__;
    border: 1px solid __BORDER__;
    border-radius: 8px;
    padding: 4px;
}
QMenu::item {
    padding: 8px 24px;
    border-radius: 4px;
}
QMenu::item:selected {
    background-color: __ACCENT__;
}
QMenu::separator {
    height: 1px;
    background-color: __BORDER__;
    margin: 4px 8px;
}

/* ═══ List (chat feed, events) ═══ */
QListWidget, QListView {
    background-color: transparent;
    border: none;
    outline: none;
}
QListWidget::item {
    border-bottom: 1px solid rgba(42, 47, 69, 0.3);
    padding: 4px;
}
"""


def apply_theme(app: QApplication, theme_name: str = "default") -> None:
    """ตั้ง font + apply QSS stylesheet ตามธีมที่เลือก (settings.ui_theme)

    ★ เขียนทับตัวแปร COLOR_* ระดับโมดูลด้วย — ต้องเรียกฟังก์ชันนี้ "ก่อน" สร้าง
    QMainWindow/widget ใดๆ เสมอ (main.py เรียกก่อน TTSForLivestreamApp() อยู่แล้ว)
    เพื่อให้ widget ที่อ้าง `theme.COLOR_X` ตอนสร้างตัวเอง (ไม่ใช่ from-import ตายตัว)
    ได้ค่าตามธีมที่เลือกจริง — ถ้า theme_name ไม่รู้จัก fallback เป็น "default" เงียบๆ
    (กันไฟล์ settings.json เก่า/พัง ทำให้เปิดโปรแกรมไม่ได้)
    """
    global COLOR_BG, COLOR_BG_DARK, COLOR_CARD, COLOR_CARD_HI, COLOR_CARD_HOVER
    global COLOR_ACCENT, COLOR_ACCENT_HOVER, COLOR_ACCENT_2, COLOR_HEADING
    global COLOR_DANGER, COLOR_DANGER_HOVER, COLOR_SUCCESS, COLOR_SUCCESS_HOVER
    global COLOR_TEXT, COLOR_TEXT_DIM, COLOR_TEXT_FAINT, COLOR_BORDER, COLOR_BORDER_LIGHT
    global COLOR_ON_ACCENT_TEXT, COLOR_ON_DANGER_TEXT, COLOR_ON_SUCCESS_TEXT, COLOR_ON_WARNING_TEXT
    global COLOR_DANGER_BTN, COLOR_DANGER_BTN_HOVER, COLOR_ZEBRA, COLOR_ACCENT_SOFT
    global COLOR_CTRL_BG, COLOR_CTRL_BORDER, COLOR_CTRL_BORDER_HI, COLOR_CTRL_DEEP
    global COLOR_CTRL_TEXT, COLOR_CTRL_DIM, COLOR_CTRL_FAINT, COLOR_CTRL_SEP, _CURRENT_PALETTE

    setup_fonts(app)
    palette = THEMES.get(theme_name) or THEMES["default"]
    _CURRENT_PALETTE = palette

    COLOR_BG = palette["BG"]
    COLOR_BG_DARK = palette["BG_DARK"]
    COLOR_CARD = palette["CARD"]
    COLOR_CARD_HI = palette["CARD_HI"]
    COLOR_CARD_HOVER = palette["CARD_HOVER"]
    COLOR_ACCENT = palette["ACCENT"]
    COLOR_ACCENT_HOVER = palette["ACCENT_HOVER"]
    COLOR_ACCENT_2 = palette["ACCENT_2"]
    COLOR_HEADING = palette["HEADING"]
    COLOR_DANGER = palette["DANGER"]
    COLOR_DANGER_HOVER = palette["DANGER_HOVER"]
    COLOR_SUCCESS = palette["SUCCESS"]
    COLOR_SUCCESS_HOVER = palette["SUCCESS_HOVER"]
    COLOR_TEXT = palette["TEXT"]
    COLOR_TEXT_DIM = palette["TEXT_DIM"]
    COLOR_TEXT_FAINT = palette["TEXT_FAINT"]
    COLOR_BORDER = palette["BORDER"]
    COLOR_BORDER_LIGHT = palette["BORDER_LIGHT"]
    COLOR_ON_ACCENT_TEXT = palette["ON_ACCENT_TEXT"]
    COLOR_ON_DANGER_TEXT = palette["ON_DANGER_TEXT"]
    COLOR_ON_SUCCESS_TEXT = palette["ON_SUCCESS_TEXT"]
    COLOR_ON_WARNING_TEXT = palette["ON_WARNING_TEXT"]
    COLOR_DANGER_BTN = palette["DANGER_BTN"]
    COLOR_DANGER_BTN_HOVER = palette["DANGER_BTN_HOVER"]
    COLOR_ZEBRA = palette["ZEBRA"]
    COLOR_ACCENT_SOFT = palette["ACCENT_SOFT"]
    COLOR_CTRL_BG = palette["CTRL_BG"]
    COLOR_CTRL_BORDER = palette["CTRL_BORDER"]
    COLOR_CTRL_BORDER_HI = palette["CTRL_BORDER_HI"]
    COLOR_CTRL_DEEP = palette["CTRL_DEEP"]
    COLOR_CTRL_TEXT = palette["CTRL_TEXT"]
    COLOR_CTRL_DIM = palette["CTRL_DIM"]
    COLOR_CTRL_FAINT = palette["CTRL_FAINT"]
    COLOR_CTRL_SEP = palette["CTRL_SEP"]

    # ★ replace placeholders with actual colors
    qss = QSS
    replacements = {
        '__BG__': COLOR_BG,
        '__BG_DARK__': COLOR_BG_DARK,
        '__CARD__': COLOR_CARD,
        '__CARD_HI__': COLOR_CARD_HI,
        '__CARD_HOVER__': COLOR_CARD_HOVER,
        '__ACCENT__': COLOR_ACCENT,
        '__ACCENT_HOVER__': COLOR_ACCENT_HOVER,
        '__ACCENT_2__': COLOR_ACCENT_2,
        '__HEADING__': COLOR_HEADING,
        '__DANGER__': COLOR_DANGER,
        '__DANGER_HOVER__': COLOR_DANGER_HOVER,
        '__SUCCESS__': COLOR_SUCCESS,
        '__SUCCESS_HOVER__': COLOR_SUCCESS_HOVER,
        '__TEXT__': COLOR_TEXT,
        '__TEXT_DIM__': COLOR_TEXT_DIM,
        '__TEXT_FAINT__': COLOR_TEXT_FAINT,
        '__BORDER__': COLOR_BORDER,
        '__BORDER_LIGHT__': COLOR_BORDER_LIGHT,
        '__ON_ACCENT_TEXT__': COLOR_ON_ACCENT_TEXT,
        '__ON_DANGER_TEXT__': COLOR_ON_DANGER_TEXT,
        '__ON_WARNING_TEXT__': COLOR_ON_WARNING_TEXT,
        '__ON_SUCCESS_TEXT__': COLOR_ON_SUCCESS_TEXT,
        '__ON_ACCENT_HOVER_TEXT__': palette["ON_ACCENT_HOVER_TEXT"],
        '__ON_DANGER_HOVER_TEXT__': palette["ON_DANGER_HOVER_TEXT"],
        '__ON_SUCCESS_HOVER_TEXT__': palette["ON_SUCCESS_HOVER_TEXT"],
        '__DANGER_BTN__': COLOR_DANGER_BTN,
        '__DANGER_EDGE__': palette["DANGER_EDGE"],
        '__DANGER_BTN_HOVER__': COLOR_DANGER_BTN_HOVER,
    }
    for placeholder, color in replacements.items():
        qss = qss.replace(placeholder, color)
    app.setStyleSheet(qss)
    _restyle_registered()       # ★ widget ที่ตั้งสีผ่าน theme.styled() รีเฟรชตามธีมใหม่สดๆ
    notify_theme_changed()      # ★ widget ที่มีเมธอดรีเฟรชของตัวเอง (register_theme_listener)
