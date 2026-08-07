# -*- mode: python ; coding: utf-8 -*-
# ════════════════════════════════════════════════════════════════════
# tts_full.spec — PyInstaller spec สำหรับ Broadcast Playroom (Full)
# รวม RVC (PyTorch/CUDA/fairseq/rvc_python) + 3 เสียง default (diona/yoimiya/shenhe)
# exe ใหญ่ ~5GB แต่ RVC ใช้ได้ครบ
#
# ★ ใช้ PyTorch 2.7.0+cu128 (รองรับ RTX 20xx → RTX 50xx+ ครบ — เลิกแยก Full Ex ตั้งแต่ v1.9.8)
#   • ไม่รองรับ GTX 10xx (Pascal) อีกต่อไป — torch 2.7 cu128 wheel ยังรวม sm_60/61 แต่
#     เลิกดูแล Pascal ทางการแล้วเพราะ user สตรีมยุคนี้ใช้ RTX
#
# ★ วิธี build:
#   1. pip install torch==2.7.0 torchaudio==2.7.0 --index-url https://download.pytorch.org/whl/cu128
#   2. python -m PyInstaller tts_full.spec --noconfirm
#   3. (dev) คืน torch 2.2.2 เพื่อเทส Lite/Full เดิม: pip install torch==2.2.2 torchaudio==2.2.2 --index-url https://download.pytorch.org/whl/cu121
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
    ('assets', 'assets'),           # logo แพลตฟอร์ม + icon + fonts
    ('splash-full.png', '.'),       # splash screen FULL
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
    ('ffmpeg.exe', '.'),            # MP3 decoder
    # RVC models — 3 เสียง default
    ('rvc_models/diona.pth', 'rvc_models'),
    ('rvc_models/yoimiya.pth', 'rvc_models'),
    ('rvc_models/shenhe.pth', 'rvc_models'),
]

# ── collect source .py files สำหรับ TorchScript (rvc_python ใช้ @torch.jit.script) ──
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# rvc_python + fairseq source — จำเป็นสำหรับ TorchScript + fairseq registry
_rvc_datas = collect_data_files('rvc_python', include_py_files=True)
datas += _rvc_datas
_fairseq_datas = collect_data_files('fairseq', include_py_files=True)
datas += _fairseq_datas
_rvc_hidden = collect_submodules('rvc_python')
_fairseq_hidden = collect_submodules('fairseq')

# ── excludes — เอาออกแค่ของที่ไม่จำเป็น ──
# ห้าม exclude scipy — RVC (rvc_python) ต้องใช้ scipy.signal
excludes = [
    'matplotlib',
    'pandas',
    'notebook',
    'jupyter',
    'IPython',
    'pytest',
    'sphinx',
    'tornado',
    'zmq',
    'tensorrt',
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
        'requests.adapters',
        'urllib3',
        'certifi',
        # RVC stack
        'torch',
        'torchaudio',
        'fairseq',
        'rvc_python',
        'rvc_python.infer',
        'torchcrepe',
        'pyworld',
        'scipy',
        'scipy.signal',
        'omegaconf',
        'faiss',
        'av',
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
    ] + _rvc_hidden + _fairseq_hidden,
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
    name='BroadcastPlayroom_Full',
    icon='assets/icon.ico',
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
    name='BroadcastPlayroom_Full',
)
