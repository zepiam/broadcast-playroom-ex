"""defender_helper.py — โมดูลจัดการ Windows Defender Exclusion อัตโนมัติในคลิกเดียว (พร้อมระบบตรวจจับการย้ายโฟลเดอร์)
"""
import os
import subprocess
import sys
from pathlib import Path
from typing import Tuple, Optional


class DefenderExclusionManager:
    """โมดูลจัดการ Windows Defender Exclusion อัตโนมัติ
    สามารถนำไปใช้กับโปรเจกต์ใดๆ ได้ทันทีโดยไม่ต้องแก้ไขชื่อไฟล์
    """

    @staticmethod
    def get_app_info() -> Tuple[Path, str]:
        """ดึง Path โฟลเดอร์ปัจจุบัน และชื่อไฟล์ Executable อัตโนมัติ"""
        if getattr(sys, 'frozen', False):
            # รันจาก PyInstaller (.exe)
            exe_path = Path(sys.executable).resolve()
            app_dir = exe_path.parent
            exe_name = exe_path.name
        else:
            # รันจาก Python script ปกติ
            app_dir = Path(__file__).resolve().parent
            exe_name = Path(sys.argv[0]).name
            if not exe_name.lower().endswith(".exe"):
                exe_name = f"{app_dir.name}.exe"
        return app_dir, exe_name

    @staticmethod
    def check_relocation_status(saved_path: Optional[str]) -> str:
        """ตรวจสอบสถานะการย้ายโฟลเดอร์:
        คืนค่า:
        - 'not_configured': ยังไม่เคยตั้งค่าข้อยกเว้น
        - 'relocated': เคยตั้งค่าแล้วแต่โฟลเดอร์ถูกย้ายที่ตั้ง
        - 'active': ข้อยกเว้นตรงกับโฟลเดอร์ปัจจุบัน
        """
        if not saved_path:
            return "not_configured"

        current_dir, _ = DefenderExclusionManager.get_app_info()
        norm_current = os.path.normpath(str(current_dir)).lower()
        norm_saved = os.path.normpath(str(saved_path)).lower()

        if norm_current != norm_saved:
            return "relocated"
        return "active"

    @staticmethod
    def apply_one_click_exclusion() -> bool:
        """ส่งคำสั่ง PowerShell พร้อมสิทธิ์ Administrator (UAC Prompt)
        เพื่อเพิ่มโฟลเดอร์และกระบวนการทำงานเข้า Windows Defender
        """
        app_dir, exe_name = DefenderExclusionManager.get_app_info()
        dir_str = str(app_dir).replace("'", "''")
        exe_str = exe_name.replace("'", "''")

        # คำสั่ง PowerShell ที่จะถูกส่งไปรันแบบ Elevated (RunAs)
        # เพิ่มทั้ง ExclusionPath (โฟลเดอร์) และ ExclusionProcess (exe)
        ps_script = (
            f"Add-MpPreference -ExclusionPath '{dir_str}'; "
            f"Add-MpPreference -ExclusionProcess '{exe_str}'; "
            f"Add-MpPreference -ExclusionProcess 'Broadcast Playroom Lite.exe'; "
            f"Add-MpPreference -ExclusionProcess 'Broadcast Playroom Full.exe'; "
            f"[System.Console]::Beep(1000, 200)"
        )

        try:
            # เรียก Start-Process powershell -Verb RunAs เพื่อเปิดหน้าต่าง UAC
            runner_cmd = (
                f'Start-Process powershell -ArgumentList '
                f'\'-NoProfile -ExecutionPolicy Bypass -Command "{ps_script}"\' '
                f'-Verb RunAs'
            )
            subprocess.Popen(["powershell", "-Command", runner_cmd], shell=False)
            return True
        except Exception as e:
            print(f"Error launching elevation: {e}")
            return False

    @staticmethod
    def open_windows_security():
        """เปิดหน้า Windows Security (Manual Fallback)"""
        try:
            os.system("start windowsdefender:")
        except Exception:
            pass
