"""build_playroom.py — Build script สำหรับ Broadcast Playroom

★ Build exe + _internal โดยไม่ลบ site-packages/
  1. PyInstaller build ไป dist/Broadcast_Playroom_tmp/
  2. ย้าย exe + _internal ทับเข้า dist/Broadcast Playroom/
  3. ไม่แตะ site-packages/ (เก็บถาวร)
"""
import os
import shutil
import subprocess
import sys

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
TMP_DIR = os.path.join(PROJECT_DIR, "dist", "Broadcast_Playroom_tmp")
FINAL_DIR = os.path.join(PROJECT_DIR, "dist", "Broadcast Playroom")

def main():
    print("=== Step 1: PyInstaller build → tmp folder ===")
    # ลบ tmp เก่า
    if os.path.isdir(TMP_DIR):
        shutil.rmtree(TMP_DIR)
    # build
    ret = subprocess.run([
        sys.executable, "-m", "PyInstaller",
        "tts_playroom.spec", "--noconfirm", "--log-level", "WARN",
    ], cwd=PROJECT_DIR)
    if ret.returncode != 0:
        print("BUILD FAILED!")
        return 1

    print("=== Step 2: Move exe + _internal to final (keep site-packages) ===")
    os.makedirs(FINAL_DIR, exist_ok=True)

    # ย้าย exe
    tmp_exe = os.path.join(TMP_DIR, "Broadcast Playroom.exe")
    final_exe = os.path.join(FINAL_DIR, "Broadcast Playroom.exe")
    if os.path.exists(tmp_exe):
        shutil.copy2(tmp_exe, final_exe)
        print(f"  exe: copied")

    # ย้าย _internal (ทับของเก่า)
    tmp_internal = os.path.join(TMP_DIR, "_internal")
    final_internal = os.path.join(FINAL_DIR, "_internal")
    if os.path.isdir(final_internal):
        shutil.rmtree(final_internal)
    if os.path.isdir(tmp_internal):
        shutil.copytree(tmp_internal, final_internal)
        print(f"  _internal: copied")

    # ★ ไม่แตะ site-packages/ (เก็บไว้)

    print("=== Step 3: Cleanup tmp ===")
    shutil.rmtree(TMP_DIR, ignore_errors=True)

    print(f"=== DONE → {FINAL_DIR} ===")
    return 0

if __name__ == "__main__":
    sys.exit(main())
