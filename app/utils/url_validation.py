"""URL validation — SSRF prevention: block private/internal IP ranges."""

import asyncio
import ipaddress
import re
import socket
from typing import Optional
from urllib.parse import urlparse

_PRIVATE_RANGES = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("255.255.255.255/32"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("2001:db8::/32"),
]

_UNUSUAL_SCHEMES = re.compile(r"^(file|ftp|gopher|dict|ldap|data|jar):", re.IGNORECASE)


def _ip_is_blocked(ip: ipaddress._BaseAddress) -> bool:
    if ip.version == 6 and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return any(ip in net for net in _PRIVATE_RANGES)


def is_safe_external_url(url: str) -> Optional[str]:
    parsed = urlparse(url)
    if _UNUSUAL_SCHEMES.search(url):
        return "Unusual URL scheme blocked (SSRF prevention)"
    hostname = parsed.hostname
    if not hostname:
        return "URL missing hostname"
    if hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"):
        return "Localhost URL blocked (SSRF prevention)"
    if hostname.endswith(".local") or hostname.endswith(".internal"):
        return "Internal hostname blocked (SSRF prevention)"
    try:
        ip = ipaddress.ip_address(hostname)
        if _ip_is_blocked(ip):
            return "Private IP range blocked (SSRF prevention)"
    except ValueError:
        pass
    return None


def validate_webhook_url(url: str) -> None:
    reason = is_safe_external_url(url)
    if reason:
        raise ValueError(reason)


async def is_safe_external_url_resolved(url: str) -> Optional[str]:
    """
    SSRF check with DNS resolved at call time — defeats trivially resolvable
    names (rebinding hosts that answer public IPs to 127.0.0.1) and
    multi-A/AAAA records where any single answer is an internal address.

    Resolution failure is treated as UNSAFE (nothing to connect to).
    """
    static_reason = is_safe_external_url(url)
    if static_reason:
        return static_reason

    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        return "URL missing hostname"
    try:
        loop = asyncio.get_running_loop()
        infos = await loop.getaddrinfo(
            hostname,
            None,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
        )
    except (socket.gaierror, OSError):
        return "Hostname could not be resolved (SSRF prevention)"

    if not infos:
        return "Hostname resolved to no addresses (SSRF prevention)"

    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            return "Hostname resolved to an unusable address (SSRF prevention)"
        try:
            ip = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            return "Hostname resolved to a non-IP address (SSRF prevention)"
        if _ip_is_blocked(ip):
            return "Hostname resolves to a private/internal IP (SSRF prevention)"

    return None


async def validate_webhook_url_resolved(url: str) -> None:
    reason = await is_safe_external_url_resolved(url)
    if reason:
        raise ValueError(reason)
