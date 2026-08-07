"""voice_downloader.py — ดาวน์โหลดเสียง RVC จาก Hugging Face

หน้าที่:
  - list_remote_voices() — ดึงรายชื่อเสียงจาก HF tree API (2 repo: Genshin + VTuber)
  - download_voice()     — โหลด .zip หรือไฟล์เดี่ยว + แตกใส่ rvc_models/
  - ทำงานใน background thread + report progress ผ่าน callback

Hugging Face URL pattern:
  - หน้าเว็บ:    https://huggingface.co/{repo}/tree/main/{path}
  - tree API:   https://huggingface.co/api/models/{repo}/tree/main/{path}
  - ดาวน์โหลด:  https://huggingface.co/{repo}/resolve/main/{path}

รูปแบบไฟล์ใน repo:
  - Genshin: ทุกอย่างเป็น .zip (ใน zip มี .pth + .index)
  - VTuber:  ผสม — บางอันเป็น .zip (top-level), บางอันเป็นโฟลเดอร์ย่อยที่มี .pth + .index แยกไฟล์
"""
from __future__ import annotations

import os
import re
import threading
import zipfile
from io import BytesIO
from typing import Callable, Optional
from urllib.parse import quote

import requests

# ---------------------------------------------------------------------- #
# ค่าคงที่ — 2 Hugging Face repositories
# ---------------------------------------------------------------------- #
REPO_GENSHIN = "ArkanDash/rvc-genshin-impact"
REPO_GENSHIN_PATH = "prezipped/v2"  # โฟลเดอร์ที่เก็บ .zip ทั้งหมด
REPO_VTUBER = "dacoolkid44/VTuber-RVC"
REPO_VTUBER_PATH = ""  # root (ผสม .zip และโฟลเดอร์ย่อย)

HF_BASE = "https://huggingface.co"
HF_API = "https://huggingface.co/api/models"


# ---------------------------------------------------------------------- #
# Catalog — รายการเสียงที่โหลดได้
# ---------------------------------------------------------------------- #
class RemoteVoice:
    """เสียง 1 ตัวที่ดาวน์โหลดได้จาก HF

    - name: ชื่อที่แสดง (เช่น "Raiden", "Gawr Gura")
    - category: "genshin" | "vtuber"
    - size: ขนาดรวม byte (สำหรับแสดง)
    - kind: "zip" (.zip ไฟล์เดียว — แตกแล้วได้ทั้ง .pth+.index)
            | "files" (.pth + .index แยกไฟล์ในโฟลเดอร์เดียวกัน)
    - files: list ของ path ใน repo ที่ต้องโหลด (สำหรับ kind="files")
    - zip_path: path ของ .zip ใน repo (สำหรับ kind="zip")
    """

    def __init__(
        self,
        name: str,
        category: str,
        size: int,
        kind: str,
        zip_path: str = "",
        files: Optional[list] = None,
    ):
        self.name = name
        self.category = category
        self.size = size
        self.kind = kind  # "zip" | "files"
        self.zip_path = zip_path
        self.files = files or []

    @property
    def size_mb(self) -> float:
        return self.size / (1024 * 1024)

    def __repr__(self) -> str:
        return f"<RemoteVoice {self.name} ({self.category}, {self.size_mb:.0f}MB)>"


# ---------------------------------------------------------------------- #
# VOICE_CATALOG — curated list (คัดเลือกไว้ล่วงหน้า ไม่ต้องดึง API ทุกครั้ง)
# ---------------------------------------------------------------------- #
# แต่ละ entry: (display_name, category, tag, repo, kind, zip_path/files)
# tag: "ใส" = เสียงใสฟังง่าย, "นุ่ม" = เสียงนุ่มนวล, "เด่น" = เสียงเด่นชัด
# category: "genshin" | "vtuber" | "anime"

VOICE_CATALOG = [
    # ═══ GENSHIN — คัดเฉพาะตัวละครหญิงที่เสียงใส/เหมาะกับ TTS ═══
    ("Paimon", "genshin", "ใส", REPO_GENSHIN, "zip", "prezipped/v2/paimon-jp 105 epochs 48k v2.zip", 339),
    ("Nahida", "genshin", "ใส", REPO_GENSHIN, "zip", "prezipped/v2/nahida-jp 102 epochs 48k v2.zip", 425),
    ("Furina", "genshin", "ใส", REPO_GENSHIN, "zip", "prezipped/v2/furina-jp 275 epochs 48k v2.zip", 153),
    ("Ayaka", "genshin", "นุ่ม", REPO_GENSHIN, "zip", "prezipped/v2/ayaka-jp 101 epochs 48k v2.zip", 348),
    ("Lumine", "genshin", "ใส", REPO_GENSHIN, "zip", "prezipped/v2/lumine-jp 700 epochs 48k v2.zip", 107),
    ("Diona", "genshin", "ใส", REPO_GENSHIN, "zip", "prezipped/v2/diona-jp 105 epochs 48k v2.zip", 368),
    ("Qiqi", "genshin", "ใส", REPO_GENSHIN, "zip", "prezipped/v2/qiqi-jp 409 epochs 48k v2.zip", 125),
    ("Charlotte", "genshin", "ใส", REPO_GENSHIN, "zip", "prezipped/v2/charlotte-jp 400 epochs 48k v2.zip", 150),
    ("Sigewinne", "genshin", "ใส", REPO_GENSHIN, "zip", "prezipped/v2/sigewinne-jp 307 epochs 48k v2.zip", 131),
    ("Faruzan", "genshin", "ใส", REPO_GENSHIN, "zip", "prezipped/v2/faruzan-jp 100 epochs 48k v2.zip", 82),
    ("Lynette", "genshin", "นุ่ม", REPO_GENSHIN, "zip", "prezipped/v2/lynette-jp 307 epochs 48k v2.zip", 187),
    ("Nilou", "genshin", "นุ่ม", REPO_GENSHIN, "zip", "prezipped/v2/nilou-jp 102 epochs 48k v2.zip", 370),
    ("Shenhe", "genshin", "เด่น", REPO_GENSHIN, "zip", "prezipped/v2/shenhe-jp 125 epochs 48k v2.zip", 263),
    ("Yoimiya (Navia)", "genshin", "ใส", REPO_GENSHIN, "zip", "prezipped/v2/navia-jp 114 epochs 48k v2.zip", 345),
    ("Barbara", "genshin", "ใส", REPO_GENSHIN, "zip", "prezipped/v2/barbara-jp 100 epochs 48k v2.zip", 373),
    ("Sucrose", "genshin", "ใส", REPO_GENSHIN, "zip", "prezipped/v2/sucrose-jp 104 epochs 48k v2.zip", 345),
    ("Noelle", "genshin", "นุ่ม", REPO_GENSHIN, "zip", "prezipped/v2/noelle-jp 101 epochs 48k v2.zip", 310),
    ("Kuki", "genshin", "เด่น", REPO_GENSHIN, "zip", "prezipped/v2/kuki-jp 101 epochs 48k v2.zip", 363),
    ("Yanfei", "genshin", "เด่น", REPO_GENSHIN, "zip", "prezipped/v2/yanfei-jp 107 epochs 48k v2.zip", 413),
    ("Amber", "genshin", "ใส", REPO_GENSHIN, "zip", "prezipped/v2/amber-jp 102 epochs 48k v2.zip", 310),

    # ═══ VTUBER — คัดเฉพาะเสียงที่เหมาะกับ TTS ═══
    ("Gawr Gura", "vtuber", "ใส", REPO_VTUBER, "files", "Gawr Gura", 225),
    ("Pekora", "vtuber", "ใส", REPO_VTUBER, "zip", "Pekora And Pekomama.zip", 491),
    ("Neuro-sama", "vtuber", "ใส", REPO_VTUBER, "files", "Neuro-sama", 87),
    ("Ninomae Ina'nis", "vtuber", "นุ่ม", REPO_VTUBER, "files", "Ninomae Ina'nis", 272),
    ("Ouro Kronii", "vtuber", "เด่น", REPO_VTUBER, "files", "Ouro Kronii", 269),
    ("Mori Calliope", "vtuber", "เด่น", REPO_VTUBER, "files", "Mori Calliope", 224),
    ("Hakos Baelz", "vtuber", "ใส", REPO_VTUBER, "files", "Hakos Baelz", 323),
    ("Kureiji Ollie", "vtuber", "ใส", REPO_VTUBER, "files", "Kureiji Ollie", 330),
    ("Amane Kanata", "vtuber", "นุ่ม", REPO_VTUBER, "files", "Amane Kanata", 331),
    ("Henya The Genius", "vtuber", "ใส", REPO_VTUBER, "files", "Henya The Genius", 361),
    ("Nina Kosaka", "vtuber", "นุ่ม", REPO_VTUBER, "files", "Nina Kosaka", 326),
    ("Rachie", "vtuber", "ใส", REPO_VTUBER, "files", "Rachie", 260),
    ("Dokibird", "vtuber", "เด่น", REPO_VTUBER, "zip", "Dokibird.zip", 357),

    # ═══ ANIME / VOCALOID / อื่นๆ — ตัวละครอนิเมะ + Vocaloid ยอดนิยม ═══
    ("Hatsune Miku", "anime", "ใส", "binant/Hatsune_Miku__RVC_v2_", "files", ["model.pth", "model.index"], 56),
    ("Nyanners", "anime", "ใส", REPO_VTUBER, "zip", "Nyanners.zip", 182),
    ("Elizabeth", "anime", "นุ่ม", REPO_VTUBER, "zip", "Elizabeth.zip", 153),
    ("Gigi", "anime", "ใส", REPO_VTUBER, "zip", "Gigi.zip", 158),
    ("Ayatsuno Yuni", "anime", "ใส", REPO_VTUBER, "zip", "AyatsunoYuni.zip", 203),
    ("Shella Nageru", "anime", "นุ่ม", REPO_VTUBER, "zip", "ShellaNageru.zip", 106),
    ("Su Mizumiya", "anime", "นุ่ม", REPO_VTUBER, "zip", "SuMizumiya.zip", 160),
    ("Towa Talk", "anime", "ใส", REPO_VTUBER, "zip", "TowaTalk.zip", 180),
    ("Yukinoshita Peo", "anime", "ใส", REPO_VTUBER, "zip", "Yukinoshita_Peo.zip", 313),
    ("Mano Aloe", "anime", "นุ่ม", REPO_VTUBER, "zip", "Mano_Aloe.zip", 180),

    # ═══ GENSHIN — เพิ่มเติม (ตัวละครชาย/หญิงที่เหลือ) ═══
    ("Aether", "genshin", "เด่น", REPO_GENSHIN, "zip", "prezipped/v2/aether-jp 100 epochs 48k v2.zip", 102),
    ("Albedo", "genshin", "นุ่ม", REPO_GENSHIN, "zip", "prezipped/v2/albedo-jp 110 epochs 48k v2.zip", 286),
    ("Alhaitam", "genshin", "เด่น", REPO_GENSHIN, "zip", "prezipped/v2/alhaitam-jp 100 epochs 48k v2.zip", 392),
    ("Bennett", "genshin", "ใส", REPO_GENSHIN, "zip", "prezipped/v2/bennett-jp 104 epochs 48k v2.zip", 288),
    ("Chongyun", "genshin", "ใส", REPO_GENSHIN, "zip", "prezipped/v2/chongyun-jp 104 epochs 48k v2.zip", 345),
    ("Cyno", "genshin", "เด่น", REPO_GENSHIN, "zip", "prezipped/v2/cyno-jp 100 epochs 48k v2.zip", 327),
    ("Dehya", "genshin", "เด่น", REPO_GENSHIN, "zip", "prezipped/v2/dehya-jp 100 epochs 48k v2.zip", 400),
    ("Dori", "genshin", "ใส", REPO_GENSHIN, "zip", "prezipped/v2/dori-jp 208 epochs 48k v2.zip", 325),
    ("Greater Lord Rukkhadevata", "genshin", "นุ่ม", REPO_GENSHIN, "zip", "prezipped/v2/greaterLordRukkhadevata-jp 750 epochs 48k v2.zip", 98),
    ("Itto", "genshin", "เด่น", REPO_GENSHIN, "zip", "prezipped/v2/itto-jp 100 epochs 40k v2.zip", 394),
    ("Jean", "genshin", "นุ่ม", REPO_GENSHIN, "zip", "prezipped/v2/jean-jp 155 epochs 48k v2.zip", 237),
    ("Kaveh", "genshin", "นุ่ม", REPO_GENSHIN, "zip", "prezipped/v2/kaveh-jp 100 epochs 48k v2.zip", 418),
    ("Kazuha", "genshin", "นุ่ม", REPO_GENSHIN, "zip", "prezipped/v2/kazuha-jp 100 epochs 48k v2.zip", 360),
    ("Lisa", "genshin", "นุ่ม", REPO_GENSHIN, "zip", "prezipped/v2/lisa-jp 104 epochs 48k v2.zip", 306),
    ("Lyney", "genshin", "เด่น", REPO_GENSHIN, "zip", "prezipped/v2/lyney-jp 101 epochs 48k v2.zip", 407),
    ("Neuvillette", "genshin", "เด่น", REPO_GENSHIN, "zip", "prezipped/v2/neuvillette-jp 105 epochs 48k v2.zip", 340),
    ("Ningguang", "genshin", "เด่น", REPO_GENSHIN, "zip", "prezipped/v2/ningguang-jp 103 epochs 48k v2.zip", 366),
    ("Raiden", "genshin", "เด่น", REPO_GENSHIN, "zip", "prezipped/v2/raiden-jp 104 epochs 48k v2.zip", 366),
    ("Razor", "genshin", "เด่น", REPO_GENSHIN, "zip", "prezipped/v2/razor-jp 303 epochs 48k v2.zip", 121),
    ("Rosaria", "genshin", "นุ่ม", REPO_GENSHIN, "zip", "prezipped/v2/rosaria-jp 500 epochs 48k v2.zip", 149),
    ("Sara", "genshin", "เด่น", REPO_GENSHIN, "zip", "prezipped/v2/sara-jp 208 epochs 48k v2.zip", 224),
    ("Signora", "genshin", "เด่น", REPO_GENSHIN, "zip", "prezipped/v2/signora-jp 1k epochs 48k v2.zip", 88),
    ("Tartaglia", "genshin", "เด่น", REPO_GENSHIN, "zip", "prezipped/v2/tartaglia-jp 103 epochs 48k v2.zip", 348),
    ("Venti", "genshin", "ใส", REPO_GENSHIN, "zip", "prezipped/v2/venti-jp 100 epochs 48k v2.zip", 317),
    ("Wriothesley", "genshin", "เด่น", REPO_GENSHIN, "zip", "prezipped/v2/wriothesley-jp 101 epochs 48k v2.zip", 381),
    ("Xiao", "genshin", "เด่น", REPO_GENSHIN, "zip", "prezipped/v2/xiao-jp 100 epochs 48k v2.zip", 289),
    ("Zhongli", "genshin", "เด่น", REPO_GENSHIN, "zip", "prezipped/v2/zhongli-jp 102 epochs 48k v2.zip", 361),

    # ═══ VTUBER — เพิ่มเติม (ที่ยังไม่มีใน catalog) ═══
    ("A-Chan", "vtuber", "นุ่ม", REPO_VTUBER, "files", "A-Chan", 325),
    ("Amelia Watson", "vtuber", "ใส", REPO_VTUBER, "files", "Amelia Watson", 667),
    ("Banzoin Hakka", "vtuber", "เด่น", REPO_VTUBER, "files", "Banzoin Hakka", 294),
    ("FalseEyeD", "vtuber", "เด่น", REPO_VTUBER, "files", "FalseEyeD", 300),
    ("Gawr Gura (Talking)", "vtuber", "ใส", REPO_VTUBER, "files", "Gawr Gura (Talking)", 411),
    ("Mysta Rias", "vtuber", "ใส", REPO_VTUBER, "files", "Mysta Rias", 279),
    ("Noir Vesper", "vtuber", "นุ่ม", REPO_VTUBER, "files", "Noir Vesper", 214),
    ("Takanashi Kiara", "vtuber", "ใส", REPO_VTUBER, "files", "Takanashi Kiara", 591),
    ("HenyaTheGenius V2", "vtuber", "ใส", REPO_VTUBER, "zip", "HenyaTheGeniusV2.zip", 317),
    ("Raora V1", "anime", "นุ่ม", REPO_VTUBER, "zip", "RaoraV1.zip", 190),
    ("Raora V2", "anime", "นุ่ม", REPO_VTUBER, "zip", "RaoraV2.zip", 156),

    # ═══ CARTOON / ANIMATION — ตัวการ์ตูนยอดนิยม (v2 เท่านั้น) ═══
    ("Vegeta (DBZ)", "anime", "เด่น", "binant/DBZ_Vegeta_-_RVC", "files", ["model.pth", "model.index"], 53),
]


def get_catalog_voices() -> list:
    """สร้าง RemoteVoice list จาก VOICE_CATALOG (curated — เร็วกว่า API)"""
    voices = []
    for name, cat, tag, repo, kind, path, size_mb in VOICE_CATALOG:
        if kind == "zip":
            v = RemoteVoice(name=name, category=cat, size=size_mb * 1024 * 1024,
                           kind="zip", zip_path=path)
        else:
            # path อาจเป็น string ("model.pth") หรือ list (["model.pth", "model.index"])
            files_list = path if isinstance(path, list) else [path]
            v = RemoteVoice(name=name, category=cat, size=size_mb * 1024 * 1024,
                           kind="files", files=files_list)
        v.tag = tag
        v.repo = repo
        voices.append(v)
    return voices


# ---------------------------------------------------------------------- #
# Catalog fetching — ดึงรายชื่อเสียงจาก HF
# ---------------------------------------------------------------------- #
def _hf_tree(repo: str, path: str = "") -> list:
    """เรียก HF tree API → คืน list ของ entries (file/directory)"""
    url = f"{HF_API}/{quote(repo)}/tree/main"
    if path:
        url += f"/{path}"
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        return r.json()
    except (requests.RequestException, ValueError):
        return []


def _list_genshin() -> list:
    """รวมรายชื่อเสียง Genshin — ทุกอย่างเป็น .zip ใน prezipped/v2/"""
    entries = _hf_tree(REPO_GENSHIN, REPO_GENSHIN_PATH)
    voices = []
    for e in entries:
        if e.get("type") != "file":
            continue
        fname = e.get("path", "")
        if not fname.lower().endswith(".zip"):
            continue
        # ชื่อไฟล์เช่น "prezipped/v2/raiden-jp 104 epochs 48k v2.zip"
        # → ตัด path ตัด .zip ตัด " epochs ..." ทิ้ง
        base = os.path.basename(fname)[:-4]  # ลบ .zip
        # ลบ suffix ที่ซ้ำซ้อน เช่น "raiden-jp 104 epochs 48k v2" → "Raiden (JP)"
        # เก็บแค่ส่วนแรก (ชื่อตัวละคร) แล้วทำให้สวย
        name = _pretty_genshin_name(base)
        voices.append(
            RemoteVoice(
                name=name,
                category="genshin",
                size=int(e.get("size", 0)),
                kind="zip",
                zip_path=fname,
            )
        )
    voices.sort(key=lambda v: v.name.lower())
    return voices


# รูปแบบชื่อไฟล์ Genshin: "{name}-{lang} {N} epochs {khz}k v2.zip"
# เช่น "raiden-jp 104 epochs 48k v2", "charlotte-jp 400 epochs 48k v2"
_GENSHIN_RE = re.compile(r"^(.*?)-([a-z]{2,4})\s+\d+\s+epochs", re.IGNORECASE)


def _pretty_genshin_name(raw: str) -> str:
    """แปลงชื่อไฟล์ HF → ชื่อที่อ่านง่าย

    เช่น:
      "raiden-jp 104 epochs 48k v2"   → "Raiden (JP)"
      "alhaitam-jp 100 epochs 48k v2"  → "Alhaitam (JP)"
      "charlotte-jp 400 epochs 48k v2" → "Charlotte (JP)"
    """
    m = _GENSHIN_RE.match(raw)
    if m:
        name = m.group(1).replace("_", " ").replace("-", " ").title()
        lang = m.group(2).upper()
        return f"{name} ({lang})"
    # fallback — ตัดตั้งแต่คำว่า epochs
    if " epochs" in raw:
        raw = raw.split(" epochs")[0]
    return raw.replace("_", " ").replace("-", " ").title()


def _list_vtuber() -> list:
    """รวมรายชื่อเสียง VTuber

    VTuber repo ผสม 2 รูปแบบ:
      1. top-level .zip (เช่น "Dokibird.zip")
      2. โฟลเดอร์ย่อยที่มี .pth + .index แยกไฟล์ (เช่น "A-Chan/")
    """
    # เรียก recursive เพื่อเห็นไฟล์ในทุก subfolder ในครั้งเดียว
    url = f"{HF_API}/{quote(REPO_VTUBER)}/tree/main?recursive=true"
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        entries = r.json()
    except (requests.RequestException, ValueError):
        entries = _hf_tree(REPO_VTUBER, "")  # fallback

    voices = []
    # กลุ่มที่ 1: top-level .zip
    for e in entries:
        if e.get("type") != "file":
            continue
        fname = e.get("path", "")
        # เฉพาะ .zip ที่อยู่ที่ root (ไม่มี /)
        if fname.lower().endswith(".zip") and "/" not in fname:
            name = os.path.basename(fname)[:-4]
            voices.append(
                RemoteVoice(
                    name=name.replace("_", " ").title(),
                    category="vtuber",
                    size=int(e.get("size", 0)),
                    kind="zip",
                    zip_path=fname,
                )
            )

    # กลุ่มที่ 2: subfolder ที่มี .pth (+ optional .index)
    # รวมตาม parent folder
    folder_files: dict[str, list] = {}  # folder → [{path, size}]
    for e in entries:
        if e.get("type") != "file":
            continue
        path = e.get("path", "")
        if "/" not in path:
            continue  # ไฟล์ root จัดไปแล้ว
        folder = path.split("/")[0]
        folder_files.setdefault(folder, []).append(
            {"path": path, "size": int(e.get("size", 0))}
        )

    for folder, files in folder_files.items():
        pth = next((f for f in files if f["path"].lower().endswith(".pth")), None)
        if not pth:
            continue  # ไม่มี .pth = ไม่ใช่เสียงที่ใช้ได้
        idx = next(
            (f for f in files if f["path"].lower().endswith(".index")), None
        )
        size = pth["size"] + (idx["size"] if idx else 0)
        voices.append(
            RemoteVoice(
                name=folder,
                category="vtuber",
                size=size,
                kind="files",
                files=[pth["path"]] + ([idx["path"]] if idx else []),
            )
        )

    voices.sort(key=lambda v: v.name.lower())
    return voices


def list_remote_voices() -> tuple[list, list, Optional[str]]:
    """ดึงรายชื่อเสียงจาก HF ทั้ง 2 repo

    คืน (genshin_voices, vtuber_voices, error_message)
    - ถ้าสำเร็จ → error_message = None
    - ถ้า fail ทั้งคู่ → voices = [], [], error_message
    - ถ้า fail บาง repo → voices ของ repo นั้นว่าง, error บอกว่าอันไหน fail
    """
    genshin = []
    vtuber = []
    errors = []
    try:
        genshin = _list_genshin()
    except Exception as e:
        errors.append(f"Genshin: {e}")
    try:
        vtuber = _list_vtuber()
    except Exception as e:
        errors.append(f"VTuber: {e}")

    err = "; ".join(errors) if errors else None
    return genshin, vtuber, err


# ---------------------------------------------------------------------- #
# Download — โหลดไฟล์ + แตกใส่ rvc_models/
# ---------------------------------------------------------------------- #
def _hf_resolve_url(repo: str, path: str) -> str:
    """สร้าง direct-download URL"""
    return f"{HF_BASE}/{quote(repo)}/resolve/main/{quote(path)}"


def _download_zip_voice(
    voice: RemoteVoice,
    repo: str,
    dest_dir: str,
    on_progress: Callable[[int, int], None],
    cancel_event: threading.Event,
) -> str:
    """โหลด .zip จาก HF + แตกใส่ dest_dir

    คืน ชื่อไฟล์ .pth ที่แตกออกมา (เพื่อเอาไปเลือกใน dropdown)
    """
    url = _hf_resolve_url(repo, voice.zip_path)
    # stream เพื่ออัปเดต progress ได้
    r = requests.get(url, stream=True, timeout=60)
    r.raise_for_status()
    total = int(r.headers.get("content-length", voice.size))
    buf = BytesIO()
    done = 0
    for chunk in r.iter_content(chunk_size=256 * 1024):
        if cancel_event.is_set():
            r.close()
            raise InterruptedError("cancelled")
        if chunk:
            buf.write(chunk)
            done += len(chunk)
            on_progress(done, total)
    buf.seek(0)

    # แตก zip — เอาเฉพาะ .pth + .index ทิ้ง junk (อย่าง .png .md)
    pth_name = ""
    with zipfile.ZipFile(buf) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            base = os.path.basename(info.filename)
            if not base:
                continue
            low = base.lower()
            if not (low.endswith(".pth") or low.endswith(".index")):
                continue
            dest = os.path.join(dest_dir, base)
            # กัน path traversal
            if not os.path.abspath(dest).startswith(
                os.path.abspath(dest_dir) + os.sep
            ):
                continue
            with zf.open(info) as src, open(dest, "wb") as dst:
                dst.write(src.read())
            if low.endswith(".pth"):
                pth_name = base
    if not pth_name:
        raise RuntimeError("zip ไม่มีไฟล์ .pth ที่ใช้ได้")
    return pth_name


def _download_files_voice(
    voice: RemoteVoice,
    repo: str,
    dest_dir: str,
    on_progress: Callable[[int, int], None],
    cancel_event: threading.Event,
) -> str:
    """โหลด .pth + .index แยกไฟล์จาก HF → ใส่ dest_dir"""
    pth_name = ""
    done = 0
    total = voice.size
    for fpath in voice.files:
        if cancel_event.is_set():
            raise InterruptedError("cancelled")
        url = _hf_resolve_url(repo, fpath)
        base = os.path.basename(fpath)
        dest = os.path.join(dest_dir, base)
        r = requests.get(url, stream=True, timeout=60)
        r.raise_for_status()
        with open(dest, "wb") as dst:
            for chunk in r.iter_content(chunk_size=256 * 1024):
                if cancel_event.is_set():
                    r.close()
                    raise InterruptedError("cancelled")
                if chunk:
                    dst.write(chunk)
                    done += len(chunk)
                    on_progress(done, total)
        if base.lower().endswith(".pth"):
            pth_name = base
    if not pth_name:
        raise RuntimeError("ไม่พบไฟล์ .pth")
    return pth_name


def download_voice(
    voice: RemoteVoice,
    dest_dir: str,
    on_progress: Callable[[int, int], None],
    cancel_event: Optional[threading.Event] = None,
) -> str:
    """ดาวน์โหลดเสียงจาก HF → แตกใส่ dest_dir

    on_progress(done_bytes, total_bytes) — เรียกตอนโหลด
    cancel_event — ตั้งเพื่อยกเลิกกลางทาง
    คืน ชื่อ .pth ที่ลงเรียบร้อย
    """
    if cancel_event is None:
        cancel_event = threading.Event()
    os.makedirs(dest_dir, exist_ok=True)

    # ★ ใช้ repo ของ voice เอง (catalog กำหนดไว้) — ไม่ใช่ hardcode ตาม category
    #   เพราะ anime/other voices อาจอยู่ใน repo อื่น (เช่น Hatsune Miku อยู่ใน binant/...)
    repo = getattr(voice, "repo", None)
    if not repo:
        repo = REPO_GENSHIN if voice.category == "genshin" else REPO_VTUBER

    if voice.kind == "zip":
        return _download_zip_voice(voice, repo, dest_dir, on_progress, cancel_event)
    else:
        return _download_files_voice(
            voice, repo, dest_dir, on_progress, cancel_event
        )


def _voice_key(voice: RemoteVoice) -> str:
    """สร้าง search key ปกติจากชื่อเสียง — สำหรับ match กับชื่อไฟล์

    เช่น:
      "Raiden (JP)" → "raiden-jp"
      "A-Chan"      → "a-chan"
      "Gawr Gura"   → "gawr gura"
    """
    key = voice.name.lower().strip()
    # "raiden (jp)" → "raiden-jp"
    key = key.replace(" (", "-").replace("(", "-").replace(")", "")
    key = key.strip()
    return key


def _match_keys(voice: RemoteVoice) -> list:
    """สร้าง candidate keys หลายแบบเพื่อ match ชื่อไฟล์ที่อาจตั้งต่างกัน

    เช่น "Raiden (JP)":
      ["raiden-jp", "raiden jp", "raidenjp", "raiden"]  (เรียงจาก specific → general)

    เช่น "Neuro-sama":
      ["neuro-sama", "neuro sama", "neurosama", "neuro"]

    เช่น "A-Chan":
      ["a-chan", "a chan", "achan", "a"]

    ใช้ fallback match เมื่อไฟล์ในเครื่องใช้ชื่อย่อ (เช่น raiden.pth ไม่ใช่ raiden-jp.pth)
    """
    key = _voice_key(voice)
    # แยกเป็น token ย่อย
    # "raiden-jp" → ["raiden", "jp"] ; "a-chan" → ["a", "chan"]
    tokens = [t for t in re.split(r"[- ]", key) if t]
    if not tokens:
        return [key]

    # สร้าง candidate จาก prefix ยาว→สั้น
    # ข้าม token สุดท้ายถ้าเป็นรหัสภาษา 2-4 ตัว (jp, en, kr, ...) เพื่อให้ "raiden" อยู่ใน candidate
    candidates = []
    n = len(tokens)
    # เริ่มจาก full key ก่อน
    full_key = key
    if full_key not in candidates:
        candidates.append(full_key)
    # ลดทีละ token จากท้าย
    for i in range(n, 0, -1):
        prefix = " ".join(tokens[:i])
        prefix_dash = "-".join(tokens[:i])
        prefix_nospace = "".join(tokens[:i])
        for p in (prefix_dash, prefix, prefix_nospace):
            if p and p not in candidates and len(p) >= 2:
                candidates.append(p)
    return candidates


def find_voice_files(voice: RemoteVoice, dest_dir: str) -> list:
    """หาไฟล์ (.pth + .index) ใน dest_dir ที่เป็นของเสียงนี้

    คืน list ของ absolute path (อาจว่างถ้าไม่ได้โหลด)
    เป็นฐานให้ is_voice_downloaded + delete_voice
    """
    if not os.path.isdir(dest_dir):
        return []

    # กรณี VTuber kind="files" — รู้ชื่อไฟล์ต้นทางแน่นอน → match exact basename
    if voice.kind == "files" and voice.files:
        exact = []
        for fpath in voice.files:
            base = os.path.basename(fpath)
            dest = os.path.join(dest_dir, base)
            if os.path.isfile(dest):
                exact.append(dest)
        # ถ้าเจอ .pth exact อย่างน้อย 1 ไฟล์ → ใช้ผล exact
        if any(p.lower().endswith(".pth") for p in exact):
            return exact

    # fallback — match ด้วย candidate keys (หลายรูปแบบ)
    # เพื่อรองรับไฟล์ที่ชื่อย่อกว่าต้นฉบับ (เช่น raiden.pth ไม่ใช่ raiden-jp.pth)
    candidates = _match_keys(voice)
    matched = []
    for f in os.listdir(dest_dir):
        low = f.lower()
        if not (low.endswith(".pth") or low.endswith(".index")):
            continue
        for key in candidates:
            # เทียบทั้งแบบมี sep และไม่มี sep (a-chan vs achan)
            hay_nospace = low.replace(" ", "").replace("-", "")
            key_nospace = key.replace(" ", "").replace("-", "")
            if key in low or key_nospace in hay_nospace:
                matched.append(os.path.join(dest_dir, f))
                break  # เจอแล้ว ไม่ต้องเช็ค candidate อื่นของไฟล์นี้
    return matched


def is_voice_downloaded(voice: RemoteVoice, dest_dir: str) -> bool:
    """เช็คว่าเสียงนี้โหลดแล้วหรือยัง (มี .pth ของเสียงนี้ใน dest_dir)"""
    files = find_voice_files(voice, dest_dir)
    return any(f.lower().endswith(".pth") for f in files)


def delete_voice(voice: RemoteVoice, dest_dir: str) -> int:
    """ลบเสียงนี้ (.pth + .index) ออกจาก dest_dir

    คืนจำนวนไฟล์ที่ลบ (0 = ไม่มีให้ลบ)
    ลบเฉพาะ .pth และ .index — ไม่แตะไฟล์อื่น
    """
    files = find_voice_files(voice, dest_dir)
    removed = 0
    for fpath in files:
        try:
            os.remove(fpath)
            removed += 1
        except OSError:
            pass
    return removed


# ---------------------------------------------------------------------- #
# Voice quality checker — ทดสอบ model หลังโหลดเสร็จ
# ---------------------------------------------------------------------- #
def test_voice_quality(pth_path: str) -> tuple:
    """ทดสอบคุณภาพ RVC model หลังโหลด

    คืน (status, message):
      status = "ok" | "warning" | "error"
      message = คำอธิบายผล (ภาษาไทย)

    ขั้นตอน:
      1. เช็คไฟล์ .pth มีจริงไหม
      2. โหลด model (RVCEngine.load) — เช็ค v1/v2 + corrupt
      3. synthesize ทดสอบสั้นๆ → ตรวจ silence + duration
    """
    if not os.path.exists(pth_path):
        return ("error", "ไม่พบไฟล์ model")

    # 1. เช็ค v1/v2 (เร็ว — ไม่ต้องโหลด RVCInference)
    try:
        import torch
        cpt = torch.load(pth_path, map_location="cpu", weights_only=False)
        emb = cpt.get("weight", {}).get("enc_p.emb_phone.weight")
        if emb is not None and len(emb) >= 2 and emb[1] != 768:
            return ("error", "Model เป็น RVC v1 (ไม่รองรับ) — ต้องใช้ v2 เท่านั้น")
    except Exception as e:
        # ถ้าเช็ค fail ให้ลองโหลดจริงในขั้นตอนถัดไป
        pass

    # 2. โหลด model + synthesize ทดสอบ
    try:
        from rvc_engine import RVCEngine, RVCParams
        import numpy as np

        engine = RVCEngine(model_path=pth_path)
        engine.load()

        # ★ สร้างเสียงพูดจริงด้วย edge-tts (เหมือนที่โปรแกรมทำจริง)
        #   ไม่ใช้ sine wave เพราะทำให้ RVC error (inhomogeneous shape)
        import asyncio
        import tempfile
        import os as _os

        async def _gen_test_audio():
            import edge_tts
            tmp_mp3 = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            tmp_mp3.close()
            tmp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp_wav.close()
            try:
                communicate = edge_tts.Communicate("สวัสดีครับ ทดสอบเสียง", "th-TH-PremwadeeNeural")
                await communicate.save(tmp_mp3.name)
                # แปลง mp3 → wav ด้วย ffmpeg (เหมือนที่โปรแกรมทำจริง)
                import subprocess
                subprocess.run(
                    ["ffmpeg", "-y", "-i", tmp_mp3.name, "-f", "wav", "-ac", "1", "-ar", "16000",
                     tmp_wav.name],
                    capture_output=True, timeout=10,
                )
                import soundfile as sf
                audio, sr = sf.read(tmp_wav.name, dtype="float32", always_2d=False)
                if audio.ndim == 2:
                    audio = audio.mean(axis=1)
                return audio, sr
            finally:
                try: _os.unlink(tmp_mp3.name)
                except: pass
                try: _os.unlink(tmp_wav.name)
                except: pass

        try:
            test_audio, sr = asyncio.run(_gen_test_audio())
        except Exception:
            return ("warning", "สร้างเสียงทดสอบไม่ได้ (edge-tts/ffmpeg error) — ลองใช้จริงดู")

        # convert ผ่าน RVC
        output = engine.convert(test_audio, sr, RVCParams())

        # 3. ตรวจผล
        if output is None or len(output) == 0:
            return ("error", "ไม่มีเสียงออก — model อาจเสีย")

        output = np.array(output, dtype=np.float32).flatten()
        # ตรวจ silence (ค่าเฉลี่ยเล็กเกินไป = เสียงแทบไม่ได้ยิน)
        rms = np.sqrt(np.mean(output ** 2))
        if rms < 0.001:
            return ("warning", "เสียงออกเบามาก — model อาจต้องปรับ pitch")

        # ตรวจ duration (สั้น/ยาวผิดปกติ)
        out_duration = len(output) / sr
        if out_duration < 0.3:
            return ("warning", "เสียงสั้นผิดปกติ — อาจไม่เหมาะกับ TTS")
        if out_duration > 10.0:
            return ("warning", "เสียงยาวผิดปกติ — อาจช้าเกินไป")

        # ตรวจ clipping (ค่าเกิน 0.95 = เสียงแตก)
        max_val = np.max(np.abs(output))
        if max_val > 0.98:
            return ("warning", "เสียงดังเกินไป — อาจแตก")

        return ("ok", "✅ ใช้งานได้ — เสียงปกติ")

    except RuntimeError as e:
        err = str(e)
        if "v1" in err:
            return ("error", "Model เป็น RVC v1 (ไม่รองรับ)")
        if "size mismatch" in err.lower():
            return ("error", "Model ไม่เข้ากัน (size mismatch)")
        return ("error", f"โหลดไม่ได้: {err[:100]}")
    except Exception as e:
        return ("error", f"ข้อผิดพลาด: {str(e)[:100]}")


def get_voice_repo(voice: RemoteVoice) -> str:
    """คืน repo ของ voice (curated หรือ dynamic)"""
    return getattr(voice, "repo", REPO_GENSHIN if voice.category == "genshin" else REPO_VTUBER)

