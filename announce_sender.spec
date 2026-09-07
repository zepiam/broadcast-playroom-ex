# -*- mode: python ; coding: utf-8 -*-
# announce_sender.spec — build โปรแกรมเล็กสำหรับเจ้าของ (เผยแพร่ประกาศ + สถิติ)
# Build: python -m PyInstaller announce_sender.spec --noconfirm
import os

a = Analysis(
    ['announce_sender.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['announcement'],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # ★ ตัดให้เล็กสุด — ไม่ใช้ torch/transformers/numpy อะไรเลย
        'torch', 'transformers', 'numpy', 'scipy', 'pandas', 'matplotlib',
        'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtQml',
        'PySide6.QtQuick', 'PySide6.Qt3DCore', 'PySide6.QtCharts', 'PySide6.QtNetwork',
        'sqlite3', 'tkinter', 'unittest', 'pydoc', 'doctest',
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='AnnounceSender',
    debug=False,
    strip=False,
    upx=False,
    console=False,          # GUI อย่างเดียว
    icon=None,
)
