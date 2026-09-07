"""announcement.py — ระบบประกาศถึงผู้ใช้ทุกเครื่อง (Announcement System)

สถาปัตยกรรม:
  - ข้อความประกาศเก็บที่ announce.json ใน GitHub repo
  - โปรแกรมทุกเครื่องดึงจาก raw.githubusercontent.com ตอนเปิด (ทุก 10 นาที)
  - เจ้าของเผยแพร่/ลบผ่านโปรแกรมด้วย fine-grained PAT (GitHub Contents API)

รูปแบบ announce.json:
  {"id": "a1697...", "text": "ข้อความ", "type": "update", "url": "https://..."}

  - id เปลี่ยนทุกครั้งที่เผยแพร่ → ผู้ใช้ที่เคยปิดอันเก่าจะเห็นอันใหม่
  - ลบประกาศ = push {"id": null} → แถบหายจากทุกเครื่อง

ความปลอดภัย:
  - fetch ใช้ default SSL verify เท่านั้น (ไม่มี fallback CERT_NONE)
  - URL ต้องเป็น http/https เท่านั้น — validate ทั้งตอน publish และตอน render
"""
from __future__ import annotations

import base64
import json
import logging
import ssl
import time
import urllib.request
import urllib.error

logger = logging.getLogger("announcement")

GITHUB_REPO = "zepiam/broadcast-playroom-ex"
ANNOUNCE_BRANCH = "main"
ANNOUNCE_PATH = "announce.json"
# ★ ใช้ Contents API แทน raw.githubusercontent — raw มี CDN cache ~5 นาที (ประกาศเห็นช้า)
#   API สดทันที + rate limit แบบไม่มี token 60 req/hr ต่อ IP (เราใช้แค่ ~8 req/hr)
CONTENTS_API = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{ANNOUNCE_PATH}"

VALID_TYPES = ("update", "info", "warning")
MAX_TEXT_LEN = 500
MAX_URL_LEN = 500

# ★ endpoint นับการอ่าน/ปิดประกาศ (server ของเจ้าของ — ไม่มี auth, ข้อมูลเป็นแค่ตัวเลขรวม)
HIT_URL = "https://men9ch.com/api/announce-hit.php"


def report_announcement_hit(ann_id: str, action: str):
    """แจ้งว่าผู้ใช้เห็นประกาศ (seen) หรือกดปิด (dismiss) — fire-and-forget

    ออกแบบให้เรียกจาก background thread: fail ทุกกรณี = เงียบผ่าน (ไม่มีผลต่อโปรแกรม)
    """
    if action not in ("seen", "dismiss") or not ann_id:
        return False
    try:
        url = f"{HIT_URL}?id={urllib.parse.quote(ann_id)}&action={action}"
        req = urllib.request.Request(url, headers={"User-Agent": "BroadcastPlayroom/2.x"})
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
            return resp.status == 200
    except Exception as e:
        logger.debug(f"report hit {action} failed: {e}")
        return False


def is_safe_url(url: str) -> bool:
    """อนุญาตเฉพาะ http/https — ปิด file://, javascript:, protocol แปลกทั้งหมด"""
    url = (url or "").strip()
    return url.startswith("http://") or url.startswith("https://")


def _fetch_via_requests(timeout: int):
    """ชั้น 1: requests (มี certifi มาในตัว — ใช้ได้ทุกเครื่อง)"""
    import requests
    r = requests.get(
        CONTENTS_API, timeout=timeout,
        headers={"User-Agent": "BroadcastPlayroom/2.x",
                 "Accept": "application/vnd.github+json"},
    )
    r.raise_for_status()
    return r.json()


def _fetch_via_urllib(timeout: int):
    """ชั้น 2-3: urllib (win_cert จาก Windows store → default) — เหมือน updater.py

    ★ exe บางเครื่อง default context หา CA ไม่เจอ → ต้องโหลดจาก Windows cert store
    """
    req = urllib.request.Request(CONTENTS_API, headers={
        "User-Agent": "BroadcastPlayroom/2.x",
        "Accept": "application/vnd.github+json",
    })
    last_err = None
    for ctx_mode in ("win_cert", "default"):
        try:
            kw = {"timeout": timeout}
            if ctx_mode == "win_cert":
                ctx = ssl.create_default_context()
                ctx.load_default_certs()  # ★ โหลดจาก Windows cert store
                kw["context"] = ctx
            with urllib.request.urlopen(req, **kw) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            last_err = e
    raise last_err or RuntimeError("urllib fetch failed")


def fetch_announcement(timeout: int = 8):
    """ดึงประกาศล่าสุดผ่าน GitHub Contents API (anonymous — สดทันที ไม่โดน CDN cache)

    ★ 3 ชั้นตามลำดับ: requests (certifi) → urllib+win_cert → urllib default
      (เครื่องที่ SSL fail เงียบๆ เคยทำให้ประกาศไม่ขึ้น — เหมือนปัญหา updater เดิม)
    คืน dict {id, text, type, url} ถ้ามีประกาศที่ id ไม่เป็น null
    คืน None ถ้าไม่มีประกาศ / ยังไม่มีไฟล์ / โหลดไม่ได้ (เงียบๆ ผ่าน)
    """
    resp_data = None
    last_err = None
    for fetcher in (_fetch_via_requests, _fetch_via_urllib):
        try:
            resp_data = fetcher(timeout)
            break
        except Exception as e:
            last_err = e
    if resp_data is None:
        # ★ เหลือชั้นเดียวก็ยังไปไม่ถึง → log warning ให้ตรวจได้จริง (ไม่เงียบอีก)
        logger.warning(f"fetch_announcement: ทุกชั้น fail — {last_err}")
        return None
    try:
        # Contents API คืน {content: <base64>, encoding: "base64", ...}
        if not isinstance(resp_data, dict) or not resp_data.get("content"):
            return None
        raw = base64.b64decode(resp_data["content"]).decode("utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict) or not data.get("id"):
            return None
        # sanitize + clamp ค่า (ข้อมูลจากภายนอก — ไม่เชื่ออะไรทั้งสิ้น)
        url = str(data.get("url") or "").strip()
        return {
            "id": str(data.get("id", ""))[:64],
            "text": str(data.get("text", ""))[:MAX_TEXT_LEN],
            "type": data.get("type") if data.get("type") in VALID_TYPES else "info",
            "url": url[:MAX_URL_LEN] if is_safe_url(url) else "",
        }
    except Exception as e:
        logger.debug(f"fetch_announcement parse: {e}")
        return None


def _github_request(url: str, token: str, method: str = "GET", payload: dict | None = None):
    """ยิง GitHub API ด้วย token — คืน (status_code, json_or_none, error_str)"""
    body = None
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "BroadcastPlayroom/2.x",
    }
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8") or "{}"), ""
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode("utf-8") or "{}")
        except Exception:
            detail = {}
        msg = detail.get("message", f"HTTP {e.code}")
        return e.code, detail, msg
    except Exception as e:
        return 0, None, str(e)


def publish_announcement(token: str, text: str, ann_type: str = "update", url: str = ""):
    """เผยแพร่ประกาศ → push announce.json ขึ้น GitHub

    คืน (ok, message) — message ภาษาไทยสำหรับแสดงใน UI
    """
    if not token.strip():
        return False, "ยังไม่ได้ใส่ GitHub Token"
    text = (text or "").strip()
    if not text:
        return False, "กรุณาพิมพ์ข้อความประกาศ"
    if ann_type not in VALID_TYPES:
        ann_type = "update"
    url = (url or "").strip()
    if url and not is_safe_url(url):
        return False, "URL ต้องขึ้นต้นด้วย http:// หรือ https:// เท่านั้น"

    announce = {
        "id": f"a{int(time.time() * 1000)}",
        "text": text[:MAX_TEXT_LEN],
        "type": ann_type,
        "url": url[:MAX_URL_LEN],
    }
    return _push_announce_file(token, announce, "เผยแพร่ประกาศ")


def delete_announcement(token: str):
    """ลบประกาศ → push {"id": null} → แถบหายจากทุกเครื่อง"""
    if not token.strip():
        return False, "ยังไม่ได้ใส่ GitHub Token"
    return _push_announce_file(token, {"id": None}, "ลบประกาศ")


def _push_announce_file(token: str, announce: dict, action_label: str):
    """push announce.json ผ่าน Contents API (อ่าน sha เดิมก่อน แล้ว PUT)"""
    token = token.strip()

    # 1) อ่านไฟล์เดิมเพื่อเอา sha (ถ้า 404 = ยังไม่มีไฟล์ → สร้างใหม่ไม่ต้องส่ง sha)
    status, data, err = _github_request(CONTENTS_API, token)
    sha = None
    if status == 200 and isinstance(data, dict):
        sha = data.get("sha")
    elif status == 404:
        sha = None
    elif status == 401:
        return False, "Token ไม่ถูกต้องหรือหมดอายุ (401)"
    elif status == 403:
        return False, "Token ไม่มีสิทธิ์ (403) — ตรวจ fine-grained PAT ให้เลือก repo นี้ + Contents: Read and write"
    else:
        return False, f"อ่านไฟล์เดิมไม่สำเร็จ: {err}"

    # 2) PUT เนื้อหาใหม่
    content_b64 = base64.b64encode(
        json.dumps(announce, ensure_ascii=False, indent=2).encode("utf-8")
    ).decode("ascii")
    payload = {
        "message": f"{action_label}: {announce.get('id') or 'cleared'}",
        "content": content_b64,
        "branch": ANNOUNCE_BRANCH,
    }
    if sha:
        payload["sha"] = sha

    status, data, err = _github_request(CONTENTS_API, token, method="PUT", payload=payload)
    if status in (200, 201):
        return True, f"✅ {action_label}สำเร็จ — ทุกเครื่องจะเห็นตอนเปิดโปรแกรมครั้งถัดไป"
    elif status == 401:
        return False, "Token ไม่ถูกต้องหรือหมดอายุ (401)"
    elif status == 403:
        return False, "Token ไม่มีสิทธิ์เขียน (403) — ต้องเป็น fine-grained PAT ที่เลือก repo นี้ + Contents: Read and write"
    elif status == 409:
        return False, "ไฟล์ถูกแก้พร้อมกัน (conflict) — ลองอีกครั้ง"
    else:
        return False, f"{action_label}ไม่สำเร็จ: {err}"
