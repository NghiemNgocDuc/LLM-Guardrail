"""Shared httpx client with connection pooling — reuse connections across requests.

Usage:
    client = get_http_client()
    resp = await client.get(url, timeout=...)  # per-request timeout override
"""

import httpx

_http_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        limits = httpx.Limits(
            max_keepalive_connections=20,
            max_connections=100,
            keepalive_expiry=55.0,
        )
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(120.0),
            limits=limits,
            follow_redirects=False,
        )
    return _http_client


async def close_http_client() -> None:
    global _http_client
    if _http_client:
        await _http_client.aclose()
        _http_client = None
