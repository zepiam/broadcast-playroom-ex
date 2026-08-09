"""rthook_stdlib.py — PyInstaller runtime hook

★ บังคับ import stdlib modules ที่ torch (ใน plugin) ต้องการ
  PyInstaller ไม่ bundle เพราะ torch ไม่ได้อยู่ใน build → ต้อง import ตอน runtime
"""
import sys

# ★ stdlib ที่ torch ใช้ (PyInstaller อาจไม่ bundle)
_stdlibs = [
    'timeit', 'pickletools', 'shutil', 'tarfile', 'zipfile', 'gzip',
    'multiprocessing', 'multiprocessing.dummy',
    'xml.dom', 'xml.sax', 'xml.etree',
    'pydoc', 'difflib', 'csv', 'configparser',
    'pickle', 'json', 'csv', 'tokenize', 'tabnanny',
]

for mod in _stdlibs:
    try:
        __import__(mod)
    except ImportError:
        pass
