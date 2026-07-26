"""URL validation — SSRF prevention: block private/internal IP ranges."""

import ipaddress
import re
from typing import Optional
from urllib.parse import urlparse

_PRIVATE_RANGES = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

_UNUSUAL_SCHEMES = re.compile(r"^(file|ftp|gopher|dict|ldap|data|jar):", re.IGNORECASE)


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
        for net in _PRIVATE_RANGES:
            if ip in net:
                return "Private IP range blocked (SSRF prevention)"
    except ValueError:
        pass
    return None


def validate_webhook_url(url: str) -> None:
    reason = is_safe_external_url(url)
    if reason:
        raise ValueError(reason)
