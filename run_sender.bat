@echo off
chcp 65001 >nul
REM ===============================================
REM  Announce Sender (owner tool)
REM  Publish/delete announcement + read stats
REM  Double-click this file to run
REM ===============================================

title Announce Sender

cd /d "%~dp0"

set "PY=%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
if not exist "%PY%" (
    where python >nul 2>&1
    if not errorlevel 1 (
        for /f "delims=" %%i in ('python -c "import sys; print(sys.executable)" 2^>nul') do set "PY=%%i"
    )
)
if not exist "%PY%" (
    echo [ERROR] Python not found
    pause
    exit /b 1
)

"%PY%" announce_sender.py
if errorlevel 1 (
    echo.
    echo [ERROR] Program exited with an error
    pause
)
