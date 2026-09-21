@echo off
REM ════════════════════════════════════════════════════════════════════
REM  build_lite.bat — Build Broadcast Playroom (Lite version)
REM  ★ ไม่ลบ build/ cache → rebuild เร็ว 5-10x
REM  Result: dist/Broadcast Playroom Lite/ folder
REM ════════════════════════════════════════════════════════════════════
setlocal

echo ============================================
echo  Building Broadcast Playroom (Lite)
echo  Edge-TTS only (no RVC)
echo ============================================
echo.

REM ★ ใช้ --noconfirm แทนการลบ build/
REM PyInstaller จะ reuse cache ที่ build/tts_lite/

echo [1/2] Building with PyInstaller (cache enabled)...
echo      First build: ~10-15 min (one-time)
echo      Rebuild:     ~2-3 min (cached)
echo.
python -m PyInstaller tts_lite.spec --noconfirm --log-level WARN
if errorlevel 1 (
    echo.
    echo [ERROR] Build failed. See output above.
    exit /b 1
)
echo.

echo [2/2] Build complete!
echo   Output: dist\Broadcast Playroom Lite\
echo.
echo   Tip: หาก rebuild แล้วผลลัพธ์ไม่เปลี่ยน ให้ลบ build\tts_lite\ เอง
echo        ถ้า spec เปลี่ยนแบบ major ให้ลบ build\ ทิ้งแล้ว build ใหม่
echo.
endlocal
