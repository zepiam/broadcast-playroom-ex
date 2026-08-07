# -*- mode: python ; coding: utf-8 -*-
# ════════════════════════════════════════════════════════════════════
# tts_lite.spec — PyInstaller spec สำหรับ Broadcast Playroom v2 (Lite)
# PySide6 UI (ไม่ใช้ customtkinter อีกต่อไป)
# ไม่รวม RVC (PyTorch/CUDA) เพื่อให้ไฟล์เล็ก
# ════════════════════════════════════════════════════════════════════
import os
import sys

block_cipher = None

from PyInstaller.utils.hooks import collect_submodules, collect_data_files, collect_dynamic_libs

_requests_subs = collect_submodules('requests')
_urllib3_subs = collect_submodules('urllib3')

# ── ไฟล์ data ที่ต้อง bundle ──
datas = [
    ('assets', 'assets'),
    ('splash-lite.png', '.'),
    ('avatar.png', '.'),
    ('neon.json', '.'),
    ('overlay.html', '.'),
    ('game_overlay.html', '.'),
    ('viewer_overlay.html', '.'),
    ('composer.html', '.'),
    ('game_overlay_css_guide.md', '.'),
    ('FAQ.md', '.'),
    ('playroom.html', '.'),
    ('version.json', '.'),
    ('media/bad.mp4', 'playroom/media'),
    ('media/good.mp4', 'playroom/media'),
    ('media/normal.mp4', 'playroom/media'),
    ('game_overlay_qt.py', '.'),
    ('ffmpeg.exe', '.'),
    # ★ v2: ui/ folder (PySide6 widgets + dialogs + theme)
    ('ui', 'ui'),
]

# ── collect PySide6 data files (plugins, translations, etc.) ──
pyside_datas = collect_data_files('PySide6')
datas += pyside_datas

# ── exclude RVC stack (Lite) ──
excludes = [
    'torch', 'torchaudio', 'torchvision', 'fairseq', 'rvc_python',
    'torchcrepe', 'praatparselmouth', 'parselmouth', 'pyworld',
    'omegaconf', 'hydra', 'faiss', 'av', 'tensorrt', 'onnx', 'onnxruntime',
    'matplotlib', 'scipy', 'pandas', 'notebook', 'jupyter', 'IPython',
    'pytest', 'sphinx', 'tornado', 'zmq',
    # ★ v2: ไม่ใช้ customtkinter อีกต่อไป
    'customtkinter',
    'tkinter',  # ★ v2: ใช้ Qt ไม่ใช้ Tk (ยกเว้น splash เก่า — แต่ v2 ใช้ QSplashScreen)
    'darkdetect',
]

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # edge-tts + aiohttp
        'edge_tts', 'aiohttp', 'aiohttp.web',
        # PySide6 (main UI framework)
        'PySide6',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebEngineCore',
        'PySide6.QtWebChannel',
        'PySide6.QtNetwork',
        'shiboken6',
        # audio
        'pedalboard', 'numpy', 'soundfile', '_sounddevice',
        # TikTokLive
        'TikTokLive', 'TikTokLive.client', 'TikTokLive.client.client',
        'TikTokLive.client.web', 'TikTokLive.events', 'TikTokLive.proto',
        'TikTokLive.proto.custom_proto', 'betterproto2', 'betterproto2.cased',
        'websockets', 'websocket', '_websocket',
        # requests + urllib3
        'requests', 'urllib3', 'certifi',
        # v2 ui modules
        'ui', 'ui.theme', 'ui.widgets', 'ui.dialogs',
    ] + _requests_subs + _urllib3_subs,
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
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon='assets/icon.ico' if os.path.exists('assets/icon.ico') else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Broadcast Playroom Lite',
)
