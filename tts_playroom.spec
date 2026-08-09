# -*- mode: python ; coding: utf-8 -*-
# ════════════════════════════════════════════════════════════════════
# tts_playroom.spec — Broadcast Playroom (base + plugin system)
#
# exe ตัวเดียว (~1GB) — Edge-TTS + ฟีเจอร์ครบ
# torch/omnivoice/rvc แยกใน site-packages/ ข้าง exe (ไม่ bundle)
# → build เร็ว (~2 นาที)
# → อัปเดต exe ไม่ต้อง rebuild torch 7GB
# ════════════════════════════════════════════════════════════════════
import os
import sys

block_cipher = None

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

_requests_subs = collect_submodules('requests')
_urllib3_subs = collect_submodules('urllib3')

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

# ── exclude ทุกอย่างที่อยู่ใน site-packages/ (plugin) ──
excludes = [
    'torch', 'torchaudio', 'torchvision', 'torchgen', 'torio',
    'fairseq', 'rvc_python', 'torchcrepe', 'praatparselmouth', 'parselmouth',
    'pyworld', 'omegaconf', 'hydra', 'faiss', 'av',
    'scipy', 'pandas', 'notebook', 'jupyter', 'IPython', 'numpy',
    'pytest', 'sphinx', 'tornado', 'zmq', 'tensorrt', 'onnx', 'onnxruntime',
    'matplotlib',
    'customtkinter', 'tkinter', 'darkdetect',
    'omnivoice', 'transformers', 'accelerate', 'datasets',
    'safetensors', 'tokenizers', 'huggingface_hub',
    'cached_path', 'vocos', 'ema_pytorch', 'torchdiffeq',
    'bitsandbytes', 'wandb', 'gradio',
    'omnivoice_engine', 'rvc_engine',
    'sympy', 'mpmath', 'networkx', 'filelock', 'fsspec', 'jinja2',
    'regex', 'tqdm', 'pyyaml', 'packaging', 'PIL', 'pillow',
    'librosa', 'typer', 'tensorboardx', 'webdataset',
]

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'edge_tts', 'aiohttp', 'aiohttp.web',
        'pygame', 'pygame.mixer',
        'PySide6', 'PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets',
        'PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineCore',
        'PySide6.QtWebChannel', 'PySide6.QtNetwork', 'shiboken6',
        'soundfile', '_sounddevice', 'pedalboard',
        # ★ stdlib modules ที่ torch ต้องการ (PyInstaller อาจไม่ bundle เพราะ torch ถูก exclude)
        'timeit', 'pickletools', 'shutil', 'tarfile', 'zipfile', 'gzip',
        'multiprocessing', 'multiprocessing.dummy',
        'pydoc', 'pydoc_data', 'difflib', 'tokenize', 'tabnanny',
        'unittest', 'unittest.mock',
        '_sitebuiltins',
        'importlib.metadata', 'importlib.resources',
        # ★ stdlib เพิ่มเติมที่ torch/transformers ต้องการ
        'filecmp', 'tempfile', 'subprocess', 'platform', 'locale',
        'string', 'textwrap', 'keyword', 'token', 'struct',
        'ctypes', 'ctypes.wintypes', 'ctypes.util',
        'concurrent', 'concurrent.futures',
        'asyncio', 'selectors', 'ssl', 'hashlib',
        'sqlite3', 'csv', 'configparser', 'tomllib',
        'json', 'json.decoder', 'json.encoder',
        'TikTokLive', 'TikTokLive.client', 'TikTokLive.client.client',
        'TikTokLive.client.web', 'TikTokLive.events', 'TikTokLive.proto',
        'TikTokLive.proto.custom_proto', 'betterproto2', 'betterproto2.cased',
        'websockets', 'websocket', '_websocket',
        'requests', 'urllib3', 'certifi',
        'ui', 'ui.theme', 'ui.widgets', 'ui.dialogs',
        'deep_translator', 'translator', 'flag_utils',
        'game_overlay_themes', 'third_party_emotes', 'twemoji_icon',
        'updater', 'splash',
        'now_playing', 'winsdk',
        'obsws_python', 'obs_refresh',
    ] + _requests_subs + _urllib3_subs,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['rthook_site_packages.py'],
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
    name='Broadcast Playroom',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon='assets/icon_full.ico' if os.path.exists('assets/icon_full.ico') else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Broadcast_Playroom_tmp',
)
