@echo off
REM ════════════════════════════════════════════════════════════════════
REM  build_lite.bat — Build Broadcast Playroom (Lite version, no RVC)
REM  Result: dist/BroadcastPlayroom/ folder with .exe + dependencies
REM ════════════════════════════════════════════════════════════════════
setlocal

echo ============================================
echo  Building Broadcast Playroom (Lite, no RVC)
echo ============================================
echo.

REM clean previous build
echo [1/3] Cleaning previous build...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
echo     done.
echo.

REM run PyInstaller with the lite spec
echo [2/3] Building with PyInstaller (this may take 5-10 minutes)...
python -m PyInstaller tts_lite.spec --noconfirm --log-level WARN
if errorlevel 1 (
    echo.
    echo [ERROR] Build failed. See output above.
    exit /b 1
)
echo.

echo [3/3] Build complete!
echo   Output: dist\BroadcastPlayroom\
echo   Exe:    dist\BroadcastPlayroom\BroadcastPlayroom.exe
echo.
pause
endlocal
