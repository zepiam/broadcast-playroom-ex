@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

REM ═══════════════════════════════════════════════════════════════
REM release.bat — สคริปต์อัตโนมัติสำหรับปล่อยอัพเดท
REM
REM วิธีใช้:
REM   release.bat              ← build + pack + แสดงคำสั่งอัพโหลด
REM   release.bat upload       ← build + pack + อัพโหลดทันที
REM
REM ก่อนใช้: ต้องล็อกอิน gh CLI แล้ว (gh auth login)
REM ═══════════════════════════════════════════════════════════════

set DO_UPLOAD=0
if /i "%~1"=="upload" set DO_UPLOAD=1

cd /d "%~dp0"

echo.
echo ═══════════════════════════════════════════════════════════════
echo  📦 Broadcast Playroom Release Script
echo ═══════════════════════════════════════════════════════════════
echo.

REM ── Step 1: อ่านเลขเวอร์ชันจาก version.json ──
echo [1/5] 📋 เลขเวอร์ชัน local:
type version.json
echo.

REM ── Step 2: ปิด exe ถ้ารันอยู่ (กัน PermissionError ตอน build) ──
echo [2/5] 🔍 ตรวจโปรแกรมที่รันอยู่...
tasklist /fi "imagename eq Broadcast Playroom Lite.exe" 2>nul | find /i "Lite.exe" >nul
if not errorlevel 1 (
    echo   ⚠️  Broadcast Playroom Lite กำลังรัน — ปิดอัตโนมัติ
    taskkill /f /im "Broadcast Playroom Lite.exe" 2>nul
    timeout /t 2 >nul
)
tasklist /fi "imagename eq BroadcastPlayroom_Full.exe" 2>nul | find /i "Full.exe" >nul
if not errorlevel 1 (
    echo   ⚠️  BroadcastPlayroom Full กำลังรัน — ปิดอัตโนมัติ
    taskkill /f /im "BroadcastPlayroom_Full.exe" 2>nul
    timeout /t 2 >nul
)
echo   ✅ ไม่มีโปรแกรมรันอยู่
echo.

REM ── Step 3: Build ทั้ง 2 เวอร์ชัน ──
echo [3/5] 🔨 Build Lite...
python -m PyInstaller tts_lite.spec --noconfirm
if errorlevel 1 (
    echo   ❌ Build Lite ล้มเหลว
    pause
    exit /b 1
)
echo.
echo       🔨 Build Full... (ใช้เวลานาน ~5-10 นาที)
python -m PyInstaller tts_full.spec --noconfirm
if errorlevel 1 (
    echo   ❌ Build Full ล้มเหลว
    pause
    exit /b 1
)
echo   ✅ Build เสร็จ
echo.

REM ── Step 4: สร้าง patch + version.json ──
echo [4/5] 📦 สร้าง patch files...
python build_patch.py patch lite
python build_patch.py patch full
python build_patch.py version
if errorlevel 1 (
    echo   ❌ สร้าง patch ล้มเหลว
    pause
    exit /b 1
)
REM คัดลอกเป็นชื่อที่โปรแกรมคาดหวัง
copy /y release\remote_version.json release\version.json >nul
echo   ✅ สร้างไฟล์ release สำเร็จ
echo.

REM ── Step 5: แสดงผลลัพธ์ / อัพโหลด ──
echo [5/5] 📁 ไฟล์ที่พร้อมอัพโหลด:
dir /b release\patch_lite.zip release\patch_full.zip release\version.json
echo.

if "%DO_UPLOAD%"=="1" (
    echo 🚀 กำลังอัพโหลดขึ้น GitHub...
    gh release upload latest ^
        release\patch_lite.zip ^
        release\patch_full.zip ^
        release\version.json ^
        --repo zepiam/broadcast-playroom --clobber
    if errorlevel 1 (
        echo   ❌ อัพโหลดล้มเหลว — ตรวจสอบ gh auth login
        pause
        exit /b 1
    )
    echo.
    echo ═══════════════════════════════════════════════════════════════
    echo  ✅ อัพเดทถูกปล่อยแล้ว! ผู้ใช้จะเห็นในครั้งถัดไปที่เปิดโปรแกรม
    echo ═══════════════════════════════════════════════════════════════
) else (
    echo ═══════════════════════════════════════════════════════════════
    echo  ✅ พร้อมอัพโหลด! รันคำสั่งต่อไปนี้:
    echo ═══════════════════════════════════════════════════════════════
    echo.
    echo   gh release upload latest ^
    echo       release\patch_lite.zip ^
    echo       release\patch_full.zip ^
    echo       release\version.json ^
    echo       --repo zepiam/broadcast-playroom --clobber
    echo.
    echo  หรือรันใหม่ด้วย:  release.bat upload
)

echo.
pause
