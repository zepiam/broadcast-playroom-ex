"""network_dns.py — ระบบ Custom DNS และ DoH (DNS-over-HTTPS) ภายในแอป

แก้ปัญหาเน็ตบ้านไทย (เช่น True CyberSafe, AIS Secure Net, หรือเน็ตหอพัก)
ที่ดักหรือบล็อก DNS UDP port 53 ทำให้เชื่อมต่อ Microsoft Speech / edge-tts ไม่ได้ (ไฟสถานะแดง)
ด้วยการใช้ DNS-over-HTTPS (DoH) ผ่าน HTTPS port 443 หรือ custom DNS server
โดยไม่ต้องแก้การตั้งค่าเน็ตเวิร์กของ Windows หรือเราเตอร์
"""
from __future__ import annotations

import asyncio
import json
import logging
import socket
import time
import urllib.request
from typing import Optional, List, Tuple
from aiohttp.resolver import AbstractResolver, ResolveResult

logger = logging.getLogger("network_dns")

# ── Preset DNS Services ──
DOH_PRESETS = {
    "cloudflare_doh": {
        "label": "⚡ Cloudflare DoH (แนะนำที่สุด - ทะลวงบล็อก 100%)",
        "type": "doh",
        "url": "https://1.1.1.1/dns-query",
    },
    "google_doh": {
        "label": "🔍 Google DoH (DNS-over-HTTPS)",
        "type": "doh",
        "url": "https://dns.google/resolve",
    },
    "quad9_doh": {
        "label": "🛡️ Quad9 DoH (DNS-over-HTTPS)",
        "type": "doh",
        "url": "https://dns.quad9.net/dns-query",
    },
    "cloudflare_udp": {
        "label": "🌐 Cloudflare DNS (1.1.1.1 / 1.0.0.1)",
        "type": "udp",
        "ip": "1.1.1.1",
    },
    "google_udp": {
        "label": "🌐 Google DNS (8.8.8.8 / 8.8.4.4)",
        "type": "udp",
        "ip": "8.8.8.8",
    },
    "custom": {
        "label": "✏️ กำหนดเอง (Custom DNS / DoH URL)",
        "type": "custom",
    },
}

# Cache: hostname -> (ips: list[str], expire_time: float)
_DNS_CACHE: dict[str, tuple[list[str], float]] = {}
_DNS_CACHE_TTL = 300.0  # 5 นาที


def query_doh(host: str, doh_url: str = "https://1.1.1.1/dns-query", timeout: float = 4.0) -> list[str]:
    """สืบค้น IP ผ่าน DNS-over-HTTPS (DoH) แบบเข้ารหัสผ่าน HTTPS พอร์ต 443"""
    sep = "&" if "?" in doh_url else "?"
    req_url = f"{doh_url}{sep}name={host}&type=A"
    req = urllib.request.Request(
        req_url,
        headers={
            "Accept": "application/dns-json",
            "User-Agent": "BroadcastPlayroom/2.9",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as res:
        payload = json.loads(res.read().decode("utf-8"))
    
    ips = []
    # Status == 0 คือ NoError
    if payload.get("Status") == 0:
        for ans in payload.get("Answer", []):
            if ans.get("type") == 1:  # Type A
                data = ans.get("data", "").strip()
                if data:
                    ips.append(data)
    return ips


def query_udp_dns(host: str, dns_ip: str = "1.1.1.1", timeout: float = 3.0) -> list[str]:
    """สืบค้น IP ผ่าน UDP DNS พอร์ต 53 แบบ Pure Python (ไม่พึ่งพา third-party library)"""
    packet = b"\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00"
    for part in host.split("."):
        packet += bytes([len(part)]) + part.encode("ascii")
    packet += b"\x00\x00\x01\x00\x01"  # QTYPE=A (1), QCLASS=IN (1)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.sendto(packet, (dns_ip, 53))
        data, _ = sock.recvfrom(2048)
    finally:
        sock.close()

    if len(data) < 12:
        return []

    ancount = int.from_bytes(data[6:8], "big")
    idx = 12
    # ข้าม Question section
    while idx < len(data) and data[idx] != 0:
        idx += 1 + data[idx]
    idx += 5  # 0x00 + QTYPE(2) + QCLASS(2)

    ips = []
    for _ in range(ancount):
        if idx >= len(data):
            break
        # ข้าม Name (Pointer 0xC0 หรือ labels)
        if data[idx] & 0xC0 == 0xC0:
            idx += 2
        else:
            while idx < len(data) and data[idx] != 0:
                idx += 1 + data[idx]
            idx += 1
        if idx + 10 > len(data):
            break
        rtype = int.from_bytes(data[idx : idx + 2], "big")
        idx += 2
        # rclass (2)
        idx += 2
        # ttl (4)
        idx += 4
        rdlength = int.from_bytes(data[idx : idx + 2], "big")
        idx += 2
        if rtype == 1 and rdlength == 4:  # Type A (IPv4)
            ip = ".".join(str(b) for b in data[idx : idx + 4])
            ips.append(ip)
        idx += rdlength
    return ips


def resolve_host_sync(
    host: str,
    service: str = "cloudflare_doh",
    custom_val: str = "",
    use_cache: bool = True,
) -> list[str]:
    """สืบค้น IP ตามคอนฟิกที่เลือก (Sync)"""
    now = time.monotonic()
    if use_cache and host in _DNS_CACHE:
        cached_ips, exp = _DNS_CACHE[host]
        if now < exp and cached_ips:
            return cached_ips

    cfg = DOH_PRESETS.get(service, DOH_PRESETS["cloudflare_doh"])
    stype = cfg.get("type")
    ips = []

    if stype == "doh":
        ips = query_doh(host, doh_url=cfg["url"])
    elif stype == "udp":
        ips = query_udp_dns(host, dns_ip=cfg["ip"])
    elif stype == "custom":
        custom = (custom_val or "").strip()
        if custom.startswith("http://") or custom.startswith("https://"):
            ips = query_doh(host, doh_url=custom)
        else:
            # สมมุติว่าเป็น IP
            ips = query_udp_dns(host, dns_ip=custom or "1.1.1.1")
    else:
        ips = query_doh(host, "https://1.1.1.1/dns-query")

    if ips and use_cache:
        _DNS_CACHE[host] = (ips, now + _DNS_CACHE_TTL)
    return ips


class AppDnsResolver(AbstractResolver):
    """aiohttp resolver ที่ใช้งาน Custom DNS / DoH"""

    def __init__(self, settings, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        self.settings = settings
        self._loop = loop

    async def resolve(
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> list[ResolveResult]:
        loop = self._loop or asyncio.get_running_loop()
        service = getattr(self.settings, "dns_service", "cloudflare_doh")
        custom_val = getattr(self.settings, "dns_custom", "")

        try:
            # รันการค้นหาใน ThreadPool
            ips = await loop.run_in_executor(
                None, resolve_host_sync, host, service, custom_val, True
            )
        except Exception as e:
            logger.warning(f"Custom DNS resolve failed for {host}: {e}")
            ips = []

        # Fallback: ถ้าหาไม่ได้ ให้ใช้ getaddrinfo ปกติของระบบ
        if not ips:
            logger.info(f"Fallback to system DNS for {host}")
            infos = await loop.getaddrinfo(
                host, port, type=socket.SOCK_STREAM, family=family
            )
            res = []
            for fam, _, proto, _, address in infos:
                res.append(
                    ResolveResult(
                        hostname=host,
                        host=address[0],
                        port=port,
                        family=fam,
                        proto=proto,
                        flags=0,
                    )
                )
            return res

        results: list[ResolveResult] = []
        for ip in ips:
            results.append(
                ResolveResult(
                    hostname=host,
                    host=ip,
                    port=port,
                    family=socket.AF_INET,
                    proto=6,  # IPPROTO_TCP
                    flags=0,
                )
            )
        return results

    async def close(self) -> None:
        pass


def test_dns_connection(
    service: str, custom_val: str = "", timeout: float = 6.0
) -> tuple[bool, float, str, str]:
    """ทดสอบเชื่อมต่อไปยัง Microsoft Speech Service ด้วย DNS ที่เลือก

    Returns:
        (success: bool, latency_ms: float, resolved_ip: str, detail_message: str)
    """
    import time
    import edge_tts
    import aiohttp

    test_host = "speech.platform.bing.com"
    t0 = time.monotonic()

    # 1. ทดสอบการสืบค้น DNS ก่อน
    try:
        ips = resolve_host_sync(test_host, service, custom_val, use_cache=False)
        if not ips:
            return (False, 0.0, "", "ไม่ได้รับ IP จากเซิร์ฟเวอร์ DNS ที่ระบุ")
        resolved_ip = ips[0]
    except Exception as e:
        return (False, 0.0, "", f"DNS Resolve ล้มเหลว: {e}")

    # 2. ทดสอบ handshake จริงกับ Microsoft Speech WebSocket โดยใช้ custom resolver
    class _MockSettings:
        pass

    mock_s = _MockSettings()
    mock_s.dns_service = service
    mock_s.dns_custom = custom_val

    async def _async_probe():
        resolver = AppDnsResolver(mock_s)
        conn = aiohttp.TCPConnector(resolver=resolver, family=socket.AF_INET)
        got_audio = False
        try:
            communicate = edge_tts.Communicate(
                "ok",
                voice="th-TH-PremwadeeNeural",
                connector=conn,
                connect_timeout=int(timeout),
                receive_timeout=int(timeout),
            )
            async for chunk in communicate.stream():
                if chunk["type"] == "audio" and len(chunk.get("data", b"")) > 0:
                    got_audio = True
                    break
        finally:
            if not conn.closed:
                await conn.close()
            await asyncio.sleep(0.05)
        return got_audio

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            got_audio = loop.run_until_complete(_async_probe())
        finally:
            loop.close()

        latency_ms = (time.monotonic() - t0) * 1000.0
        if got_audio:
            return (True, latency_ms, resolved_ip, f"เชื่อมต่อ Microsoft Speech สำเร็จ ({latency_ms:.0f} ms)")
        else:
            return (False, latency_ms, resolved_ip, "เชื่อมต่อได้ แต่ไม่ได้รับข้อมูลเสียงตอบกลับ")
    except Exception as exc:
        latency_ms = (time.monotonic() - t0) * 1000.0
        return (False, latency_ms, resolved_ip, f"เชื่อมต่อล้มเหลว: {exc}")
