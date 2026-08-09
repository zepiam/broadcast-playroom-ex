"""rthook_help.py — PyInstaller runtime hook

★ fairseq/dataclass/configs.py ใช้ `help` เป็น dict key โดยไม่ใส่ quotes:
    metadata={help: "store exponential moving average shadow model"}

  ใน Python ปกติ `help` เป็น builtin ที่ site.py register ผ่าน _sitebuiltins
  แต่ PyInstaller ไม่รัน site.py → `help` ไม่ถูก register → NameError ตอน import fairseq

  ★ runtime hook นี้ register `help` builtin กลับมา (ก่อนที่ fairseq จะถูก import)
"""
import builtins

if not hasattr(builtins, 'help'):
    try:
        from _sitebuiltins import Helper, _Helper
        builtins.help = _Helper()
    except Exception:
        # fallback: ใช้ object ธรรมดา เพราะ fairseq แค่ใช้เป็น dict key (ไม่ได้เรียก)
        builtins.help = "help"
