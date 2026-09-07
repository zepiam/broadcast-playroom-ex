# -*- mode: python ; coding: utf-8 -*-
# ════════════════════════════════════════════════════════════════════
# tts_lite.spec — PyInstaller spec สำหรับ Broadcast Playroom v2 (Lite)
# ฟีเจอร์ครบทุกอย่าง + Edge-TTS (ไม่มี OmniVoice/RVC)
# ════════════════════════════════════════════════════════════════════
import os
import sys

block_cipher = None

from PyInstaller.utils.hooks import collect_submodules, collect_data_files, collect_dynamic_libs

_requests_subs = collect_submodules('requests')
_urllib3_subs = collect_submodules('urllib3')

# ── ไฟล์ data ที่ต้อง bundle ──
def _data(src, dst):
    return [(src, dst)] if os.path.exists(src) else []

datas = [
    ('assets', 'assets'),
    ('avatar.png', '.'),
    ('neon.json', '.'),
    ('overlay.html', '.'),
    ('game_overlay.html', '.'),
    ('viewer_overlay.html', '.'),
    ('composer.html', '.'),
    ('FAQ.md', '.'),
    ('playroom.html', '.'),
    ('version.json', '.'),
    ('game_overlay_qt.py', '.'),
    ('ffmpeg.exe', '.'),
    ('ui', 'ui'),
]
for _clip in ['bad.mp4', 'good.mp4', 'normal.mp4']:
    datas += _data(f'media/{_clip}', 'playroom/media')

pyside_datas = collect_data_files('PySide6')
datas += pyside_datas

# ── exclude RVC + OmniVoice stack (Lite) ──
excludes = [
    'torch', 'torchaudio', 'torchvision', 'fairseq', 'rvc_python',
    'torchcrepe', 'praatparselmouth', 'parselmouth', 'pyworld',
    'omegaconf', 'hydra', 'faiss', 'av', 'tensorrt', 'onnx', 'onnxruntime',
    'matplotlib', 'scipy', 'pandas', 'notebook', 'jupyter', 'IPython',
    'pytest', 'sphinx', 'tornado', 'zmq',
    'customtkinter', 'tkinter', 'darkdetect',
    'omnivoice', 'transformers', 'accelerate', 'datasets',
    'safetensors', 'tokenizers', 'huggingface_hub',
    'cached_path', 'vocos', 'ema_pytorch', 'torchdiffeq',
    'bitsandbytes', 'wandb', 'gradio',
    # engine modules — ไม่ bundle (Lite ไม่ใช้)
    'omnivoice_engine', 'rvc_engine',
]

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'edge_tts', 'aiohttp', 'aiohttp.web',
        'PySide6', 'PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets',
        'PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineCore',
        'PySide6.QtWebChannel', 'PySide6.QtNetwork', 'shiboken6',
        'pedalboard', 'numpy', 'soundfile', '_sounddevice', 'sounddevice', 'pyaudio',
        'TikTokLive', 'TikTokLive.client', 'TikTokLive.client.client',
        'TikTokLive.client.web', 'TikTokLive.events', 'TikTokLive.proto',
        'TikTokLive.proto.custom_proto', 'betterproto2', 'betterproto2.cased',
        'websockets', 'websocket', '_websocket',
        'requests', 'urllib3', 'certifi',
        'ui', 'ui.theme', 'ui.widgets', 'ui.dialogs',
        'engine_plugin_loader',
        # ★ v2.5.0 — Chat Bot + OAuth + OBS + Single Instance
        'twitch_oauth', 'twitch_bot', 'youtube_oauth', 'kick_oauth', 'announcement', 'server_guard',
        'single_instance', 'obs_launcher',
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
    icon='assets/icon_lite.ico' if os.path.exists('assets/icon_lite.ico') else None,
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
