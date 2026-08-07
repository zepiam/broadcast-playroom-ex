# -*- mode: python ; coding: utf-8 -*-
# ════════════════════════════════════════════════════════════════════
# tts_lite.spec — PyInstaller spec สำหรับ TTS for Livestream (Lite)
# ไม่รวม RVC (PyTorch/CUDA/fairseq/rvc_python) เพื่อให้ไฟล์เล็ก ~250MB
# RVC จะ disabled ตอนรัน (main.py จัดการ gracefully) → ใช้ Premwadee ได้
# ════════════════════════════════════════════════════════════════════
import os
import sys

block_cipher = None

# ── collect requests + urllib3 submodules (PyInstaller ไม่เจอเพราะ lazy import) ──
from PyInstaller.utils.hooks import collect_submodules
_requests_subs = collect_submodules('requests')
_urllib3_subs = collect_submodules('urllib3')

# ── ไฟล์ data ที่ต้อง bundle ──
datas = [
    ('assets', 'assets'),           # logo แพลตฟอร์ม + fonts
    ('splash-lite.png', '.'),       # splash screen LITE
    ('avatar.png', '.'),            # ★ ภาพตัวละคร default (Character Talk)
    ('neon.json', '.'),             # theme
    ('overlay.html', '.'),          # OBS overlay web page
    ('game_overlay.html', '.'),     # Game overlay web page (Qt)
    ('viewer_overlay.html', '.'),   # Viewer overlay web page (ยอดคนดู)
    ('composer.html', '.'),         # Canvas Overlay Composer web page (1 URL รวมทุก widget)
    ('game_overlay_css_guide.md', '.'),  # CSS guide
    ('FAQ.md', '.'),                # คู่มือแก้ปัญหา
    ('playroom.html', '.'),         # Playroom overlay web page
    ('version.json', '.'),          # version info (สำหรับ updater)
    ('media/bad.mp4', 'playroom/media'),
    ('media/good.mp4', 'playroom/media'),
    ('media/normal.mp4', 'playroom/media'),
    ('game_overlay_qt.py', '.'),    # Game overlay Qt subprocess script
    ('ffmpeg.exe', '.'),            # MP3 decoder (จำเป็นต้องใช้)
]

# ── โมดูลหนักที่จะ exclude (ไม่รวมใน build) ──
# RVC stack — ประหยัดเนื้อที่ ~2.5GB
excludes = [
    'torch',
    'torchaudio',
    'torchvision',
    'fairseq',
    'rvc_python',
    'torchcrepe',
    'praatparselmouth',
    'parselmouth',
    'pyworld',
    'omegaconf',
    'hydra',
    'faiss',
    'av',                # PyAV (ใช้ตอน RVC)
    'tensorrt',
    'onnx',
    'onnxruntime',
    'matplotlib',
    'scipy',
    'pandas',
    'notebook',
    'jupyter',
    'IPython',
    'pytest',
    'sphinx',
    'tornado',
    'zmq',
]

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # requests + urllib3 (รวม submodules — สำหรับ updater + translator)
        # PyInstaller ไม่เจอเพราะ lazy import → ต้อง collect ทั้งหมด
    ] + _requests_subs + _urllib3_subs + [
        # edge-tts บางครั้ง PyInstaller ไม่เจอ
        'edge_tts',
        'aiohttp',
        'aiohttp.web',
        # customtkinter assets
        'customtkinter',
        # pedalboard (audio effects)
        'pedalboard',
        # numpy
        'numpy',
        # soundfile backend
        'soundfile',
        '_sounddevice',
        # TikTokLive (WebSocket protobuf — มี submodules มาก)
        'TikTokLive',
        'TikTokLive.client',
        'TikTokLive.client.client',
        'TikTokLive.client.web',
        'TikTokLive.events',
        'TikTokLive.proto',
        'TikTokLive.proto.custom_proto',
        'betterproto2',
        'betterproto2.cased',
        'websockets',
        'websocket',
        '_websocket',
        # requests (สำหรับ updater + translator — PyInstaller ไม่เจอเพราะ lazy import)
        'requests',
        'urllib3',
        'certifi',
        # PySide6 + QtWebEngine (Game Overlay)
        'PySide6',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebEngineCore',
        'PySide6.QtWebChannel',
        'shiboken6',
        # Auto Translate
        'deep_translator',
        'translator',
        'flag_utils',
        # Game Overlay themes (ใช้ใน overlay_server + game_overlay_server)
        'game_overlay_themes',
        # Third-party Twitch emotes (FFZ + BTTV + 7TV)
        'third_party_emotes',
        # Twemoji icon renderer (emoji สีสัน)
        'twemoji_icon',
        # Auto-updater
        'updater',
        # Splash screen
        'splash',
        # Main GUI module (lazy import in main.py → PyInstaller ไม่เจอ)
        'app_gui',
        # ★ Now Playing widget (Windows System Media)
        'now_playing',
        'winsdk',
        # ★ OBS WebSocket auto-refresh
        'obsws_python',
        'obs_refresh',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Broadcast Playroom Lite',
    icon='assets/icon_lite.ico',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,              # UPX ทำให้ customtkinter พัง — ปิดไว้
    console=False,          # ซ่อน console window (log ไปที่ tts.log ข้าง exe)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Broadcast Playroom Lite',
)
