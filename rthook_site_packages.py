"""rthook_site_packages.py — Runtime hook for plugin system

★ Force-load torch + numpy + omnivoice จาก site-packages/ ข้าง exe
  โดยใช้ importlib ข้าม PyInstaller's module stub
"""
import os
import sys
import importlib

if getattr(sys, 'frozen', False):
    base_dir = os.path.dirname(sys.executable)
else:
    base_dir = os.path.dirname(os.path.abspath(__file__))

site_packages = os.path.join(base_dir, "site-packages")

if os.path.isdir(site_packages):
    # ★ เพิ่ม site-packages ที่ต้น sys.path
    if site_packages not in sys.path:
        sys.path.insert(0, site_packages)

    # ★ ลบ PyInstaller stubs สำหรับ modules ที่ exclude
    _force_reload = [
        'numpy', 'torch', 'torchaudio', 'torchvision',
        'scipy', 'sympy', 'mpmath', 'networkx', 'filelock', 'fsspec',
        'jinja2', 'markupsafe',
        'omnivoice', 'transformers', 'huggingface_hub', 'tokenizers',
        'safetensors', 'accelerate', 'cached_path', 'vocos',
        'ema_pytorch', 'torchdiffeq', 'torch_einops_utils',
        'fairseq', 'rvc_python', 'faiss', 'torchcrepe', 'pyworld',
        'regex', 'tqdm', 'yaml', 'packaging', 'PIL',
        'pydub', 'librosa', 'omnivoice_engine', 'rvc_engine',
        'soundfile', '_soundfile',
    ]
    for mod_name in _force_reload:
        # ลบทุก submodule ที่ขึ้นต้นด้วยชื่อนี้
        for key in list(sys.modules.keys()):
            if key == mod_name or key.startswith(mod_name + '.'):
                del sys.modules[key]

    # ★ force import numpy ก่อน (torch ต้องการ)
    try:
        importlib.import_module('numpy')
    except Exception:
        pass

    # ★ force import torch
    try:
        importlib.import_module('torch')
        import logging
        logging.getLogger("rthook").info("torch loaded from site-packages")
    except Exception as e:
        import logging
        logging.getLogger("rthook").warning(f"torch import failed: {e}")

    # ★ force import omnivoice + transformers (ลบ stub ออกจาก sys.modules ก่อน)
    _omni_deps = ['omnivoice', 'transformers', 'huggingface_hub', 'tokenizers',
                  'safetensors', 'accelerate', 'cached_path', 'vocos',
                  'ema_pytorch', 'torchdiffeq', 'torch_einops_utils']
    for mod_name in _omni_deps:
        for key in list(sys.modules.keys()):
            if key == mod_name or key.startswith(mod_name + '.'):
                del sys.modules[key]

    # ★ invalidate import cache → บังคับ import ใหม่จาก site-packages
    importlib.invalidate_caches()

    try:
        importlib.import_module('omnivoice')
        import logging
        logging.getLogger("rthook").info("omnivoice loaded from site-packages")
    except Exception as e:
        import logging
        logging.getLogger("rthook").warning(f"omnivoice import failed: {e}")
