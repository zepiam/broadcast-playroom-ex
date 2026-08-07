@echo off
chcp 65001 >nul
REM ===============================================
REM  TTS for Livestream - Run script
REM  Uses Python 3.10 (required for fairseq)
REM ===============================================

title TTS for Livestream

cd /d "%~dp0"

REM Find Python 3.10
set "PY=%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
if not exist "%PY%" (
    where py >nul 2>&1
    if not errorlevel 1 (
        for /f "delims=" %%i in ('py -3.10 -c "import sys; print(sys.executable)" 2^>nul') do set "PY=%%i"
    )
)
if not exist "%PY%" (
    echo [ERROR] Python 3.10 not found
    echo Please run setup.bat first
    pause
    exit /b 1
)

echo [INFO] Starting TTS for Livestream...
echo [INFO] Python: %PY%
echo.

"%PY%" main.py

if errorlevel 1 (
    echo.
    echo [ERROR] Program exited with error
    pause
)
