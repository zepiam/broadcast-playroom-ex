"""build_patch.py — สร้างไฟล์สำหรับอัพเดท (patch + full) สำหรับ Broadcast Playroom

วิธีใช้:
  python build_patch.py patch lite    # สร้าง patch สำหรับ Lite (~20-50MB)
  python build_patch.py patch full    # สร้าง patch สำหรับ Full
  python build_patch.py full lite     # สร้าง full zip สำหรับ Lite (~900MB)
  python build_patch.py full full     # สร้าง full zip สำหรับ Full (~5GB)
  python build_patch.py version       # สร้าง remote_version.json สำหรับ GitHub

output: release/ folder
  ├── patch_lite.zip          ← อัพ GitHub release
  ├── patch_full.zip
  ├── full_lite.zip           ← อัพ Google Drive
  ├── full_full.zip
  └── remote_version.json     ← อัพ GitHub release

patch ประกอบด้วย:
  - *.py (main, app_gui, settings, ฯลฯ)
  - *.html (overlay, game_overlay, playroom)
  - *.json (neon, version)
  - assets/ (logo, fonts, icon)
  - exe (Broadcast Playroom Lite.exe หรือ BroadcastPlayroom_Full.exe)

full ประกอบด้วย:
  - ทั้งโฟลเดอร์ dist/BroadcastPlayroom_*/
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path


# ── ⚠️ เปลี่ยนเป็น GitHub repo ของคุณ (format: user/repo) ──
GITHUB_REPO = "zepiam/broadcast-playroom"
# URL สำหรับ major update (Lite → GitHub, Full → Google Drive เพราะใหญ่เกิน 2GB)
FULL_DOWNLOAD_PAGE = "https://men9ch.com/broadcast-playroom/"


# ── ไฟล์ที่จะรวมใน patch (delta update — เล็ก ~20-50MB) ──
PATCH_PATTERNS = [
    # Python source
    "*.py",
    # HTML/CSS
    "*.html",
    # JSON config
    "neon.json",
    "version.json",
    # assets (recursive — logo, fonts, icon)
    "assets/**",
    # CSS guide
    "game_overlay_css_guide.md",
    # ★ ภาพตัวละคร default (Character Talk) — bundle ใน exe และ ship ใน patch
    "avatar.png",
    # splash screens
    "splash-lite.png",
    "splash-full.png",
]

# ไฟล์ที่จะแยกต่างหาก (ไม่ glob) — exe
EXE_NAMES = {
    "lite": "Broadcast Playroom Lite.exe",
    "full": "BroadcastPlayroom_Full.exe",
}

# ชื่อโฟลเดอร์ใน dist/ หลัง build (อาจมี space ได้)
DIST_FOLDER = {
    "lite": "Broadcast Playroom Lite",
    "full": "BroadcastPlayroom_Full",
}


def _read_local_version() -> str:
    """อ่านเวอร์ชันจาก version.json"""
    try:
        with open("version.json", "r", encoding="utf-8") as f:
            return json.load(f).get("version", "0.0.0")
    except Exception:
        return "0.0.0"


def _read_changelog() -> str:
    """อ่าน changelog จาก version.json"""
    try:
        with open("version.json", "r", encoding="utf-8") as f:
            return json.load(f).get("changelog", "")
    except Exception:
        return ""


def pack_patch(build_type: str) -> str:
    """สร้าง patch zip — คืน path ของไฟล์"""
    version = _read_local_version()
    dist_dir = Path("dist") / DIST_FOLDER[build_type]
    exe_path = dist_dir / EXE_NAMES[build_type]
    out_path = Path(f"release/patch_{build_type}.zip")

    if not exe_path.exists():
        print(f"❌ ไม่พบ exe: {exe_path}")
        print(f"   กรุณา build {build_type} ก่อน (python -m PyInstaller tts_{build_type}.spec)")
        sys.exit(1)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()

    print(f"📦 สร้าง patch {build_type} v{version}...")
    # ★ ซิงค์ version.json ล่าสุดไป _internal/ ก่อน (กันใช้ของเก่าจาก PyInstaller)
    import shutil
    internal_dir = dist_dir / "_internal"
    local_version_json = Path("version.json")
    dist_version_json = internal_dir / "version.json"
    if local_version_json.exists() and internal_dir.exists():
        shutil.copy2(local_version_json, dist_version_json)
    count = 0
    total_size = 0
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        # 1. exe (สำคัญที่สุด — โค้ดทั้งหมดอยู่ในนี้) → วางที่ root ของ zip
        print(f"   + {exe_path.name} ({exe_path.stat().st_size / 1024 / 1024:.1f} MB)")
        zf.write(exe_path, exe_path.name)
        total_size += exe_path.stat().st_size
        count += 1

        # 2. ไฟล์ตาม pattern (จาก _internal/) → วางใน _internal/ ของ zip
        #    เพื่อให้ตอน xcopy ไฟล์ไปถูกที่ (exe → root, *.py/html/json → _internal/)
        internal = dist_dir / "_internal"
        for pattern in PATCH_PATTERNS:
            if "/" in pattern or "**" in pattern:
                # recursive pattern — ค้นใน _internal
                base_dir = internal
                if pattern.startswith("assets/"):
                    base_dir = internal
                for fpath in base_dir.glob(pattern):
                    if fpath.is_file():
                        # เก็บ path สัมพัทธ์ใต้ _internal แล้วเติม _internal/ นำหน้า
                        rel = fpath.relative_to(internal)
                        arcname = str(Path("_internal") / rel)
                        zf.write(fpath, arcname)
                        total_size += fpath.stat().st_size
                        count += 1
            else:
                # simple pattern — ค้นใน _internal/
                for fpath in internal.glob(pattern):
                    if fpath.is_file():
                        arcname = str(Path("_internal") / fpath.name)
                        zf.write(fpath, arcname)
                        total_size += fpath.stat().st_size
                        count += 1

    size_mb = out_path.stat().st_size / 1024 / 1024
    print(f"✅ สร้าง patch เสร็จ: {out_path} ({size_mb:.1f} MB, {count} files)")
    return str(out_path)


def pack_full(build_type: str) -> str:
    """สร้าง full zip — คืน path ของไฟล์"""
    dist_dir = Path("dist") / DIST_FOLDER[build_type]
    out_path = Path(f"release/full_{build_type}.zip")

    if not dist_dir.exists():
        print(f"❌ ไม่พบ dist folder: {dist_dir}")
        sys.exit(1)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()

    print(f"📦 สร้าง full {build_type} zip... (อาจใช้เวลานาน)")
    # ใช้ PowerShell Compress-Archive (เร็วกว่า Python zipfile สำหรับไฟล์ใหญ่)
    ps_cmd = f"Compress-Archive -Path '{dist_dir}/*' -DestinationPath '{out_path}' -Force"
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_cmd],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"❌ PowerShell error: {result.stderr}")
        sys.exit(1)

    size_mb = out_path.stat().st_size / 1024 / 1024
    print(f"✅ สร้าง full zip เสร็จ: {out_path} ({size_mb:.1f} MB)")
    return str(out_path)


def make_remote_version() -> str:
    """สร้าง remote_version.json สำหรับ GitHub

    อ่าน URL อัตโนมัติจาก GITHUB_REPO + ขนาดจาก release/patch_*.zip จริง
    """
    version = _read_local_version()
    changelog = _read_changelog()
    base = f"https://github.com/{GITHUB_REPO}/releases/download/latest"

    # อ่านขนาด patch จริง (ถ้ามี)
    patch_sizes = {}
    for bt in ("lite", "full"):
        p = Path(f"release/patch_{bt}.zip")
        if p.exists():
            patch_sizes[bt] = p.stat().st_size

    remote = {
        "version": version,
        "changelog": changelog,
        "lite": {
            "type": "patch" if "lite" in patch_sizes else "major",
            "url": f"{base}/patch_lite.zip" if "lite" in patch_sizes else FULL_DOWNLOAD_PAGE,
            "size": patch_sizes.get("lite", 0),
        },
        "full": {
            "type": "patch" if "full" in patch_sizes else "major",
            "url": f"{base}/patch_full.zip" if "full" in patch_sizes else FULL_DOWNLOAD_PAGE,
            "size": patch_sizes.get("full", 0),
        },
    }

    out_path = Path("release/remote_version.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(remote, f, ensure_ascii=False, indent=2)
    # ★ สร้าง version.json ด้วย (updater อ่านไฟล์นี้ — ต้องมี lite/full blocks ครบ)
    version_path = Path("version.json")
    with open(version_path, "w", encoding="utf-8") as f:
        json.dump(remote, f, ensure_ascii=False, indent=2)
    print(f"✅ สร้าง remote_version.json + version.json (เหมือนกัน)")
    print(f"   version: {version}")
    print(f"   lite: {remote['lite']['type']} ({remote['lite']['size']/1024/1024:.1f} MB)")
    print(f"   full: {remote['full']['type']} ({remote['full']['size']/1024/1024:.1f} MB)")
    return str(out_path)


def main():
    if len(sys.argv) < 2:
        print("วิธีใช้:")
        print("  python build_patch.py patch lite    # สร้าง patch สำหรับ Lite")
        print("  python build_patch.py patch full    # สร้าง patch สำหรับ Full")
        print("  python build_patch.py full lite     # สร้าง full zip Lite")
        print("  python build_patch.py full full     # สร้าง full zip Full")
        print("  python build_patch.py version       # สร้าง remote_version.json")
        sys.exit(0)

    cmd = sys.argv[1].lower()
    if cmd == "patch":
        bt = sys.argv[2].lower() if len(sys.argv) > 2 else "lite"
        pack_patch(bt)
    elif cmd == "full":
        bt = sys.argv[2].lower() if len(sys.argv) > 2 else "lite"
        pack_full(bt)
    elif cmd == "version":
        # สร้าง remote_version.json อัตโนมัติจาก GITHUB_REPO + patch files
        make_remote_version()
    else:
        print(f"คำสั่งไม่ถูกต้อง: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
