# -*- mode: python ; coding: utf-8 -*-
# ════════════════════════════════════════════════════════════════════
# tts_full.spec — PyInstaller spec สำหรับ Broadcast Playroom v2 (Full)
# ฟีเจอร์ครบทุกอย่าง + Edge-TTS + OmniVoice + RVC (PyTorch/CUDA)
# ════════════════════════════════════════════════════════════════════
import os
import sys

block_cipher = None

from PyInstaller.utils.hooks import collect_submodules, collect_data_files, collect_dynamic_libs

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
for _v in ['lumine-jp.pth', 'paimon-jp.pth']:
    datas += _data(f'rvc_models/{_v}', 'rvc_models')

_rvc_datas = collect_data_files('rvc_python', include_py_files=True)
datas += _rvc_datas
_fairseq_datas = collect_data_files('fairseq', include_py_files=True)
datas += _fairseq_datas
_rvc_hidden = collect_submodules('rvc_python')
_fairseq_hidden = collect_submodules('fairseq')
# ★ OmniVoice + transformers data + submodules + metadata
_omni_datas = collect_data_files('omnivoice', include_py_files=True)
datas += _omni_datas
_omni_hidden = collect_submodules('omnivoice')
_tf_datas = collect_data_files('transformers', include_py_files=False)
datas += _tf_datas
_tf_hidden = collect_submodules('transformers')
# ★ collect metadata (.dist-info) — omnivoice/__init__.py ใช้ importlib.metadata
from PyInstaller.utils.hooks import copy_metadata
datas += copy_metadata('omnivoice')
datas += copy_metadata('torch')
datas += copy_metadata('torchaudio')
datas += copy_metadata('torchvision')
datas += copy_metadata('transformers')
datas += copy_metadata('tqdm')
datas += copy_metadata('numpy')
datas += copy_metadata('scipy')
datas += copy_metadata('huggingface-hub')
datas += copy_metadata('tokenizers')
datas += copy_metadata('safetensors')
datas += copy_metadata('soundfile')
datas += copy_metadata('accelerate')

excludes = [
    'matplotlib', 'pandas', 'notebook', 'jupyter', 'IPython',
    'pytest', 'sphinx', 'tornado', 'zmq', 'tensorrt',
    'customtkinter', 'tkinter', 'darkdetect',
]

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'edge_tts', 'aiohttp', 'aiohttp.web',
        'pygame', 'pygame.mixer',
        'pedalboard', 'numpy', 'soundfile', '_sounddevice',
        'TikTokLive', 'TikTokLive.client', 'TikTokLive.client.client',
        'TikTokLive.client.web', 'TikTokLive.events', 'TikTokLive.proto',
        'TikTokLive.proto.custom_proto', 'betterproto2', 'betterproto2.cased',
        'websockets', 'websocket', '_websocket',
        'requests', 'urllib3', 'certifi',
        # RVC stack
        'torch', 'torchaudio', 'fairseq', 'rvc_python', 'rvc_python.infer',
        'torchcrepe', 'pyworld', 'scipy', 'scipy.signal', 'omegaconf', 'faiss', 'av',
        '_sitebuiltins',
        # OmniVoice
        'omnivoice', 'transformers',
        # ★ OmniVoice deps — HiggsAudioV2TokenizerModel (transformers dynamic import)
        'transformers.models.higgs_audio_v2_tokenizer',
        'transformers.models.higgs_audio_v2_tokenizer.modeling_higgs_audio_v2_tokenizer',
        'transformers.models.higgs_audio_v2_tokenizer.configuration_higgs_audio_v2_tokenizer',
        # PySide6
        'PySide6', 'PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets',
        'PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineCore',
        'PySide6.QtWebChannel', 'PySide6.QtNetwork', 'shiboken6',
        # other
        'deep_translator', 'translator', 'flag_utils',
        'game_overlay_themes', 'third_party_emotes', 'twemoji_icon',
        'updater', 'splash',
        'now_playing', 'winsdk',
        'obsws_python', 'obs_refresh',
        'omnivoice_engine', 'rvc_engine', 'engine_plugin_loader',
    ] + _requests_subs + _urllib3_subs + _rvc_hidden + _fairseq_hidden + _omni_hidden + _tf_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['rthook_help.py'],
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
    icon='assets/icon_full.ico' if os.path.exists('assets/icon_full.ico') else None,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
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
