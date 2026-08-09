"""updater.py — Auto-update checker (GitHub Releases)

ตรวจสอบเวอร์ชั่นใหม่จาก GitHub Releases API
→ เทียบกับ version.json ในเครื่อง
→ แจ้งเตือน + เปิด browser ดาวน์โหลด

★ Private repo: ต้องส่ง token ใน header
"""
import json
import logging
import os
import threading
import webbrowser
from typing import Optional, Callable

logger = logging.getLogger("updater")

# GitHub API
REPO = "zepiam/broadcast-playroom-ex"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"


def get_current_version() -> str:
    """อ่านเวอร์ชั่นปัจจุบันจาก version.json"""
    try:
        import sys
        if getattr(sys, 'frozen', False):
            base = os.path.dirname(sys.executable)
            internal = os.path.join(base, "_internal")
            path = os.path.join(internal, "version.json")
            if not os.path.exists(path):
                path = os.path.join(base, "version.json")
        else:
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "version.json")
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        return data.get('version', '0.0.0')
    except Exception as e:
        logger.debug(f"get_current_version: {e}")
        return '0.0.0'


def get_latest_version(token: str = "") -> Optional[dict]:
    """เช็คเวอร์ชั่นล่าสุดจาก GitHub Releases API"""
    try:
        import urllib.request
        import urllib.error
        req = urllib.request.Request(API_URL)
        req.add_header('Accept', 'application/vnd.github+json')
        req.add_header('User-Agent', 'BroadcastPlayroom-Updater')
        if token:
            req.add_header('Authorization', f'token {token}')
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        tag = data.get('tag_name', '').lstrip('v')
        body = data.get('body', '')
        release_url = data.get('html_url', '')
        assets = data.get('assets', [])
        download_urls = {}
        for asset in assets:
            name = asset.get('name', '').lower()
            url = asset.get('browser_download_url', '')
            if 'lite' in name:
                download_urls['lite'] = url
            elif 'full' in name:
                download_urls['full'] = url
        return {
            'version': tag,
            'changelog': body,
            'release_url': release_url,
            'download_urls': download_urls,
        }
    except Exception as e:
        logger.debug(f"get_latest_version: {e}")
        return None


def compare_versions(current: str, latest: str) -> bool:
    """เทียบเวอร์ชั่น — คืน True ถ้า latest > current"""
    try:
        cur = [int(x) for x in current.split('.')]
        new = [int(x) for x in latest.split('.')]
        while len(cur) < len(new):
            cur.append(0)
        while len(new) < len(cur):
            new.append(0)
        return new > cur
    except Exception:
        return False


def check_update_async(callback: Callable[[Optional[dict]], None], token: str = ""):
    """เช็คอัพเดทใน background thread"""
    def _bg():
        try:
            current = get_current_version()
            latest = get_latest_version(token)
            if latest is None:
                callback(None)
                return
            if compare_versions(current, latest['version']):
                latest['current_version'] = current
                callback(latest)
            else:
                callback(None)
        except Exception as e:
            logger.debug(f"check_update_async: {e}")
            callback(None)
    threading.Thread(target=_bg, name="UpdateChecker", daemon=True).start()


def open_release_page(release_url: str):
    """เปิดหน้า release ใน browser"""
    try:
        webbrowser.open(release_url)
    except Exception as e:
        logger.debug(f"open_release_page: {e}")
