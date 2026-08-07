@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

REM ============================================================
REM  TTS for Livestream - Setup Script
REM  - Installs Python 3.10 (required for fairseq)
REM  - Installs PyTorch + CUDA
REM  - Installs RVC + fairseq (from prebuilt wheel)
REM  - RVC models bundled (no download needed)
REM
REM  WARNING: Takes 15-30 minutes (PyTorch+CUDA is ~2GB)
REM ============================================================

title TTS for Livestream - Setup

cd /d "%~dp0"

echo.
echo ===============================================
echo   TTS for Livestream - Setup
echo   (RVC Voice Conversion - NVIDIA GPU recommended)
echo ===============================================
echo.

REM ---- 0) Check GPU ----
echo [0/5] Checking NVIDIA GPU...
nvidia-smi >nul 2>&1
if errorlevel 1 (
    echo [WARNING] nvidia-smi not found - might not have NVIDIA GPU
    echo          RVC will run on CPU (very slow)
    choice /c YN /m "Continue anyway"
    if errorlevel 2 exit /b 1
) else (
    echo [OK] NVIDIA GPU detected
)

REM ---- 1) Find or install Python 3.10 ----
echo.
echo [1/5] Looking for Python 3.10...
set "PY="

if exist "%LOCALAPPDATA%\Programs\Python\Python310\python.exe" (
    set "PY=%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
)

if not defined PY (
    echo [INFO] Python 3.10 not found, installing...
    winget install -e --id Python.Python.3.10 --accept-package-agreements --accept-source-agreements --scope user
    if exist "%LOCALAPPDATA%\Programs\Python\Python310\python.exe" (
        set "PY=%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    ) else (
        echo [ERROR] Failed to install Python 3.10
        pause
        exit /b 1
    )
)

echo [OK] Python 3.10: %PY%
"%PY%" --version

REM ---- 2) Install old pip/setuptools (required for fairseq) ----
echo.
echo [2/5] Installing compatible pip/setuptools...
"%PY%" -m pip install "pip<24.0" "setuptools<60" "wheel<0.40"

REM ---- 3) Install PyTorch + CUDA ----
echo.
echo [3/5] Installing PyTorch + CUDA 12.1...
echo       (Large download ~2GB, may take 5-15 minutes)
"%PY%" -m pip install torch==2.2.2 torchaudio==2.2.2 --index-url https://download.pytorch.org/whl/cu121
if errorlevel 1 (
    echo [ERROR] Failed to install PyTorch
    pause
    exit /b 1
)

REM ---- 4) Install fairseq from prebuilt wheel ----
echo.
echo [4/5] Installing fairseq (from prebuilt wheel)...
set "FAIRSEQ_WHEEL=%TEMP%\fairseq-0.12.2-cp310-cp310-win_amd64.whl"
if not exist "%FAIRSEQ_WHEEL%" (
    echo [INFO] Downloading fairseq wheel...
    curl -L -o "%FAIRSEQ_WHEEL%" "https://huggingface.co/Jmica/rvc/resolve/main/fairseq-0.12.2-cp310-cp310-win_amd64.whl"
)
"%PY%" -m pip install "%FAIRSEQ_WHEEL%"
if errorlevel 1 (
    echo [WARNING] fairseq wheel install failed - trying pip install
    "%PY%" -m pip install fairseq==0.12.2
)

REM ---- 5) Install remaining dependencies ----
echo.
echo [5/5] Installing remaining dependencies...
"%PY%" -m pip install omegaconf==2.0.6 hydra-core==1.0.7
"%PY%" -m pip install rvc-python --no-deps
"%PY%" -m pip install faiss-cpu torchcrepe praat-parselmouth pyworld av
"%PY%" -m pip install edge-tts customtkinter pygame pydub soundfile
"%PY%" -m pip install aiohttp requests
"%PY%" -m pip install "numpy<2"

REM ---- Playwright (สำหรับ MyLive chat — optional แต่แนะนำ) ----
echo.
echo ===============================================
echo   Installing Playwright + Chromium (MyLive)...
echo   (Chromium ~300MB, โหลดครั้งแรกช้าหน่อย)
echo ===============================================
"%PY%" -m pip install "playwright>=1.40"
if not errorlevel 1 (
    "%PY%" -m playwright install chromium
) else (
    echo [WARNING] Playwright install failed - MyLive chat จะใช้ไม่ได้
    echo          Twitch/YouTube ยังใช้ได้ปกติ
)

REM ---- Done ----
echo.
echo ===============================================
echo   Setup complete!
echo ===============================================
echo.
echo   Bundled voices (9): Haruka, Hikari, A-Chan,
echo     Neuro-sama, Keqing, Yae Miko, Shenhe,
echo     Yoimiya, Diona
echo.
echo   To run the program:
echo     "%PY%" "%~dp0main.py"
echo.
echo   Or just double-click: run.bat
echo.
pause
