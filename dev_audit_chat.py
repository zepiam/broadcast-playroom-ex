# -*- coding: utf-8 -*-
# ═══ FULL AUDIT: เครื่องมือทั้งหมดใน Chat Settings — 3 ชั้น ═══
# 1) Runtime: เซฟค่าผ่าน /import-profile (ท่อเดียวกับ modal) → อ่าน /chat-config เทียบ
# 2) Cross-check: key ที่ server ส่ง ↔ key ที่ overlay.html อ่าน (config.xxx)
# 3) Cross-check: CSS var ที่ applyConfig ตั้ง ↔ var() ที่ CSS ใช้จริง
import io, json, re, sys, time, urllib.request

sys.stdout.reconfigure(encoding="utf-8")
BASE = "http://127.0.0.1:8815"
WID = "aud1"

def post(path, payload):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    return json.load(urllib.request.urlopen(req, timeout=10))

def get_json(path):
    return json.load(urllib.request.urlopen(BASE + path, timeout=10))

def set_widget(w):
    # ★ ใช้ /save (ท่อจริงของ modal) + มี callback persist เหมือน app จริง
    post("/save?t=" + str(int(time.time()*1000)),
         {"widgets": [dict(w, id=WID, type="chat", enabled=True,
                           x=10, y=10, w=800, h=500, z=1)],
          "canvas_size": "1080p", "character_jobs": [], "character_default_image": ""})
    return get_json("/chat-config?id=" + WID)

results = []  # (mode, field, sent, got, ok)

def check(mode, fields, expect_fn=None):
    base = {"appearance_mode": mode}
    base.update(fields)
    cfg = set_widget(base)
    # key ที่ chat-config เปลี่ยนชื่อตอนส่งออก (by design)
    OUT_KEY = {"font_color": "text_color", "bg_opacity": "box_bg_opacity"}
    for f, v in fields.items():
        got = cfg.get(OUT_KEY.get(f, f))
        ok = (got == v)
        results.append((mode, f, v, got, ok))

# ─── 1) RUNTIME ทุกโหมด ───
check("default", {
    "show_logo": False, "show_timestamp": True, "direction": "top",
    "font_family": "Mitr", "font_weight": "700", "font_size": 26,
    "font_color": "#ff0000", "text_stroke": True, "text_stroke_color": "#112233",
    "text_stroke_width": 4, "text_shadow": False, "text_shadow_color": "#445566",
    "text_shadow_blur": 7, "emote_size": 40, "animation": "pop",
    "exit_animation": "slide_out_left", "auto_hide": True, "hide_after": 12,
    "layout": "stacked", "chat_align": "center",   # default บังคับ layout=inline
})
# default mode: layout ต้องถูกบังคับเป็น inline โดย client (server เก็บตามส่ง) — บันทึกผลแยก
check("theme", {
    "theme": "neon", "layout": "stacked", "box_width": "wide",
    "bg_opacity": 0.4, "chat_padding": 20, "msg_spacing": 9,
})
check("theme", {"theme": "glass"})
# (custom_css ดิบถูก server แปลงเป็น theme_css — ตรวจผ่านข้อ MARKER ด้านล่างแทน)
check("balloon", {
    "balloon_hide_after": 9, "balloon_font_family": "Sarabun",
    "balloon_font_weight": "700", "balloon_font_size": 30,
    "balloon_text_color": "#123456", "balloon_emote_size": 44,
})
check("character", {
    "character_bubble_width": 700, "font_size": 22,
    "character_hide_after": 11, "character_max_on_screen": 12,
    "character_font_family": "Prompt", "character_font_weight": "400",
    "character_font_color": "#654321", "character_stroke": True,
    "character_stroke_width": 3, "character_stroke_color": "#010101",
    "character_shadow": True, "character_shadow_blur": 6,
    "character_shadow_color": "#020202", "character_emote_size": 36,
    "character_show_name": False, "character_show_logo": False,
    "character_name_size": 15, "character_name_font_family": "Trirong",
    "character_name_font_weight": "300", "character_name_color": "#abcdef",
    "character_name_stroke": False, "character_name_stroke_color": "#333333",
    "character_name_stroke_width": 5, "character_name_shadow": True,
    "character_name_shadow_color": "#444444", "character_name_shadow_blur": 8,
})
check("slider", {
    "slider_font_family": "Chakra Petch", "slider_font_weight": "800",
    "slider_font_size": 38, "slider_text_color": "#ff00ff",
    "slider_text_stroke": True, "slider_text_stroke_color": "#001122",
    "slider_text_stroke_width": 5, "slider_text_shadow": True,
    "slider_text_shadow_color": "#334455", "slider_text_shadow_blur": 9,
    "slider_emote_size": 50, "slider_duration": 7, "slider_show_logo": False,
    "slider_lane_height": 55,
})

# theme_css checks
cfg = set_widget({"appearance_mode": "theme", "theme": "cute"})
results.append(("theme", "theme_css(cute) มีเนื้อหา", True, len(cfg.get("theme_css") or "") > 50,
                len(cfg.get("theme_css") or "") > 50))
cfg = set_widget({"appearance_mode": "default", "custom_css_enabled": True,
                  "custom_css": "/*MARKER1234*/"})
css = cfg.get("theme_css") or ""
results.append(("default", "custom_css ใช้ใน default", True, "MARKER1234" in css, "MARKER1234" in css))
cfg = set_widget({"appearance_mode": "slider"})
results.append(("slider", "slider_mode flag", True, cfg.get("slider_mode"), cfg.get("slider_mode")))
cfg = set_widget({"appearance_mode": "balloon"})
results.append(("balloon", "balloon_mode flag", True, cfg.get("balloon_mode"), cfg.get("balloon_mode")))
cfg = set_widget({"appearance_mode": "character"})
results.append(("character", "character_mode flag", True, cfg.get("character_mode"), cfg.get("character_mode")))

# ─── 2) CROSS-CHECK: server keys ↔ overlay reads ───
srv = io.open("composer_server.py", encoding="utf-8").read()
ov = io.open("overlay.html", encoding="utf-8").read()
i0 = srv.index("def _build_chat_widget_config")
body = srv[i0:]  # method สุดท้ายของไฟล์ — ยาวถึงจบ
sent_keys = set(re.findall(r'"([a-z_]+)":', body))
# keys ที่ overlay อ่าน
read_keys = set(re.findall('config' + chr(92) + '.([A-Za-z_]+)', ov))
# default config keys (ประกาศใน overlay)
defaults_keys = set(re.findall(r'^\s{2}([a-z_]+):\s', ov.split("let loadedFont")[0], re.M))
sent_but_never_read = sorted(k for k in sent_keys
                             if k not in read_keys and k not in defaults_keys
                             and k not in ("canvas_size", "canvas_w", "canvas_h", "widgets"))

# ─── 3) CROSS-CHECK: CSS vars ตั้ง ↔ ใช้ ───
set_vars = set(re.findall(r"setProperty\('--([a-z-]+)'", ov))
used_vars = set(re.findall(r"var\(--([a-z-]+)", ov))
set_but_unused = sorted(v for v in set_vars if v not in used_vars)
used_but_never_set_defaulted = sorted(v for v in used_vars if v not in set_vars)

# ─── รายงาน ───
fails = 0
print("═" * 78)
print("ชั้น 1 — RUNTIME: เซฟผ่านท่อจริง → อ่านกลับจาก /chat-config")
print("═" * 78)
cur_mode = None
for mode, f, sent, got, ok in results:
    if mode != cur_mode:
        cur_mode = mode
        print(f"\n[{mode}]")
    mark = "✓" if ok else "✗ FAIL"
    if not ok:
        fails += 1
        print(f"  {mark} {f}: ส่ง={sent!r} ได้={got!r}")
    else:
        print(f"  {mark} {f}")

print("\n" + "═" * 78)
print("ชั้น 2 — server ส่ง แต่ overlay ไม่มีทางอ่านเลย (บั๊กท่อขาด):")
print("═" * 78)
if sent_but_never_read:
    for k in sent_but_never_read:
        print("  ✗", k); fails += 1
else:
    print("  ✓ ครบ — ทุก key ที่ส่งมีผู้อ่าน")

print("\n" + "═" * 78)
print("ชั้น 3 — ตั้ง CSS var แต่ไม่มี CSS ไหนใช้ (ไร้ผล):")
print("═" * 78)
if set_but_unused:
    for v in set_but_unused:
        print("  ✗", v); fails += 1
else:
    print("  ✓ ครบ — ทุก var ที่ตั้งถูกใช้จริง")

print("\n" + "═" * 78)
print(f"สรุป: {'ทุกเครื่องมือผ่าน ✅' if fails == 0 else f'พบปัญหา {fails} จุด ❌'}")
