@echo off
REM ════════════════════════════════════════════════════════════════════
REM  build_full.bat — Build Broadcast Playroom (Full version)
REM  ★ ไม่ลบ build/ cache → rebuild เร็ว 5-10x (3-5 นาที แทน 30-40 นาที)
REM  Result: dist/BroadcastPlayroom_Full/ folder
REM ════════════════════════════════════════════════════════════════════
setlocal

echo ============================================
echo  Building Broadcast Playroom (Full)
echo  with OmniVoice + RVC + PyTorch/CUDA
echo ============================================
echo.

REM ★ ใช้ --noconfirm แทนการลบ build/
REM PyInstaller จะ reuse cache ที่ build/tts_full/
REM ถ้า spec เปลี่ยน มันจะ rebuild เฉพาะส่วนที่เปลี่ยนเท่านั้น

echo [1/2] Building with PyInstaller (cache enabled)...
echo      First build: ~30-40 min (one-time)
echo      Rebuild:     ~3-5 min (cached)
echo.
python -m PyInstaller tts_full.spec --noconfirm --log-level WARN
if errorlevel 1 (
    echo.
    echo [ERROR] Build failed. See output above.
    exit /b 1
)
echo.

echo [2/2] Build complete!
echo   Output: dist\BroadcastPlayroom_Full\
echo   Exe:    dist\BroadcastPlayroom_Full\BroadcastPlayroom_Full.exe
echo.
echo   Tip: หาก rebuild แล้วผลลัพธ์ไม่เปลี่ยน ให้ลบ build\tts_full\ เอง
echo        ถ้า spec เปลี่ยนแบบ major ให้ลบ build\ ทิ้งแล้ว build ใหม่
echo.
endlocal
