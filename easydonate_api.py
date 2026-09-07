"""easydonate_api.py — EasyDonate API client + Donate Goal Watcher

เชื่อมต่อกับ EasyDonate API เพื่อดึงข้อมูลโดเนท
ใช้สำหรับ Donate Goal widget ใน Composer overlay

API docs: https://docs.easydonate.app/developer/

Endpoints ที่ใช้:
  GET /api/v1/me                 — เช็ค API key
  GET /api/v1/donations/breakdown — ยอดรวม + จำนวนครั้ง
  GET /api/v1/donations?page=1   — รายการโดเนท (หา last donor)

Auth: Authorization: Bearer ezdn_v1_xxx
Rate limit: 60 req/min → poll ทุก 15 วิ = 4 req/min (ปลอดภัย)
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Callable, Optional

import requests

logger = logging.getLogger("easydonate")

BASE_URL = "https://api.easydonate.app/api/v1"
TIMEOUT = 15
POLL_INTERVAL = 15.0  # วินาที (4 req/min < 60 limit)


class EasyDonateClient:
    """เรียก EasyDonate API"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        }

    def _get(self, path: str, params: dict = None) -> Optional[dict]:
        """GET request → คืน data field หรือ None ถ้า error"""
        url = f"{BASE_URL}{path}"
        try:
            r = requests.get(url, headers=self._headers, params=params, timeout=TIMEOUT)
            if r.status_code != 200:
                logger.warning(f"EasyDonate {path}: HTTP {r.status_code}")
                return None
            body = r.json()
            if body.get("statusCode") != 200:
                logger.warning(f"EasyDonate {path}: statusCode {body.get('statusCode')}")
                return None
            return body.get("data")
        except Exception as e:
            logger.warning(f"EasyDonate {path} error: {e}")
            return None

    def get_me(self) -> Optional[dict]:
        """GET /me — ข้อมูลแอคเคาท์ (เช็คว่า API key ใช้ได้)"""
        return self._get("/me")

    def get_breakdown(self) -> Optional[dict]:
        """GET /donations/breakdown — ยอดรวมโดเนท

        คืน: {totalAmount: float, totalCount: int, channels: [...]}
        """
        return self._get("/donations/breakdown")

    def get_donations(self, page: int = 1, start_date: str = None) -> Optional[dict]:
        """GET /donations — รายการโดเนท

        คืน: {size, total, totalPage, histories: [...]}
        histories[]: {amount, donatorName, message, createdAt, ...}
        """
        params = {"page": page}
        if start_date:
            params["startDate"] = start_date
        return self._get("/donations", params=params)

    def test_key(self) -> bool:
        """ทดสอบว่า API key ใช้ได้ → คืน True/False"""
        me = self.get_me()
        return me is not None and "id" in me


class DonateGoalWatcher:
    """Background poller — ดึงยอดโดเนทจาก EasyDonate ทุก 15 วิ

    Flow:
      1. start(goal_amount) — เริ่มที่ 0 + จำ started_at timestamp
      2. poll ทุก 15 วิ:
         - get_breakdown() → totalAmount (ยอดรวมตั้งแต่เปิดบัญชี)
         - get_donations() → last donor name
      3. คำนวณ current = totalAmount ณ ตอนเริ่ม widget → ลบออก
         เพื่อให้เริ่มที่ 0 จริงๆ (นับเฉพาะที่เข้ามาหลังเปิด widget)
      4. เรียก on_update(current, goal, last_donor, donor_count)
    """

    def __init__(self, api_key: str, on_update: Callable):
        self.api_key = api_key
        self.on_update = on_update
        self.goal = 0
        self._client = None
        self._thread = None
        self._stop_event = threading.Event()
        self._running = False

        # ★ baseline — ยอดรวม ณ ตอนเริ่ม widget (เพื่อนับเฉพาะใหม่)
        self._baseline_amount = 0
        self._baseline_count = 0
        self._started_at_iso = None

    def start(self, goal_amount: float) -> bool:
        """เริ่มวัด — คืน True ถ้าสำเร็จ"""
        if self._running:
            self.stop()

        self.goal = max(1, float(goal_amount))
        self._client = EasyDonateClient(self.api_key)

        # ★ ทดสอบ API key ก่อน
        if not self._client.test_key():
            logger.warning("DonateGoalWatcher: API key ไม่ถูกต้อง")
            return False

        # ★ จำ baseline (ยอดรวมตอนเริ่ม) — เพื่อนับเฉพาะที่เข้ามาใหม่
        breakdown = self._client.get_breakdown()
        if breakdown:
            self._baseline_amount = float(breakdown.get("totalAmount", 0))
            self._baseline_count = int(breakdown.get("totalCount", 0))
        else:
            self._baseline_amount = 0
            self._baseline_count = 0

        self._started_at_iso = datetime.now(timezone.utc).isoformat()
        logger.info(f"DonateGoalWatcher started — goal={self.goal}, baseline={self._baseline_amount}")

        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_loop, name="DonateGoal", daemon=True)
        self._thread.start()

        # ★ push ครั้งแรกทันที (0 / goal)
        self._push_update()
        return True

    def stop(self):
        """หยุดวัด"""
        self._running = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        self._thread = None

    def _poll_loop(self):
        """background thread — poll ทุก 15 วิ"""
        while not self._stop_event.is_set():
            try:
                self._push_update()
            except Exception as e:
                logger.warning(f"DonateGoal poll error: {e}")
            self._stop_event.wait(POLL_INTERVAL)

    def _push_update(self):
        """ดึงข้อมูลล่าสุด + เรียก on_update"""
        if not self._client:
            return

        # ★ ดึง breakdown (ยอดรวม)
        breakdown = self._client.get_breakdown()
        if not breakdown:
            return

        total_amount = float(breakdown.get("totalAmount", 0))
        total_count = int(breakdown.get("totalCount", 0))

        # ★ คำนวณ current = ยอดตอนนี้ - baseline (เริ่มที่ 0)
        current = max(0, total_amount - self._baseline_amount)
        donor_count = max(0, total_count - self._baseline_count)

        # ★ ดึง last donor (รายการล่าสุด)
        last_donor = ""
        last_amount = 0
        donations = self._client.get_donations(page=1)
        if donations:
            histories = donations.get("histories", [])
            if histories:
                last = histories[0]  # ล่าสุดอยู่บนสุด
                last_donor = last.get("donatorName", "")
                last_amount = float(last.get("amount", 0))

        # ★ เรียก callback
        try:
            self.on_update(current, self.goal, last_donor, last_amount, donor_count)
        except Exception as e:
            logger.warning(f"on_update error: {e}")

    @property
    def is_running(self) -> bool:
        return self._running


if __name__ == "__main__":
    # ★ test — ต้องใส่ API key จริง
    import sys
    if len(sys.argv) < 2:
        print("Usage: python easydonate_api.py <api_key>")
        sys.exit(1)

    key = sys.argv[1]
    client = EasyDonateClient(key)

    print("=== /me ===")
    me = client.get_me()
    print(f"  username: {me.get('username') if me else 'FAIL'}")

    print("\n=== /donations/breakdown ===")
    bd = client.get_breakdown()
    if bd:
        print(f"  totalAmount: {bd.get('totalAmount')}")
        print(f"  totalCount: {bd.get('totalCount')}")

    print("\n=== /donations ===")
    dons = client.get_donations(page=1)
    if dons:
        print(f"  total: {dons.get('total')}")
        h = dons.get("histories", [])
        if h:
            print(f"  last donor: {h[0].get('donatorName')} — {h[0].get('amount')}")

    print("\n=== Watcher test (10s) ===")
    def on_upd(current, goal, donor, amount, count):
        print(f"  current={current} goal={goal} donor={donor} amount={amount} count={count}")

    w = DonateGoalWatcher(key, on_update=on_upd)
    if w.start(goal_amount=1000):
        time.sleep(10)
        w.stop()
        print("Done.")
    else:
        print("Failed to start watcher.")
