#!/usr/bin/env python
"""Create an external HTTP health monitor using UptimeRobot's documented v2 API.

Run from the repository root; .env values are loaded without overriding the
process environment. No application/provider credentials are sent to the monitor.
"""
import argparse
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit, urlunsplit

import httpx
from dotenv import load_dotenv

API_BASE = "https://api.uptimerobot.com/v2"


def health_url(base_url: str) -> str:
    parts = urlsplit(base_url.strip())
    if (parts.scheme != "https" or not parts.hostname or parts.username
            or parts.password or parts.query or parts.fragment
            or parts.path not in ("", "/", "/health")):
        raise ValueError("Use a public HTTPS app origin or its /health URL, without credentials or query parameters.")
    if parts.hostname.lower() in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("UptimeRobot needs a publicly reachable URL.")
    return urlunsplit((parts.scheme, parts.netloc, "/health", "", ""))


def api_call(client: httpx.Client, api_key: str, method: str, **params) -> dict:
    try:
        response = client.post(
            f"{API_BASE}/{method}",
            data={"api_key": api_key, "format": "json", **params},
        )
        response.raise_for_status()
        result = response.json()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"UptimeRobot {method} returned HTTP {exc.response.status_code}.") from None
    except (httpx.RequestError, ValueError):
        raise RuntimeError(f"UptimeRobot {method} failed; check network access and retry.") from None
    # Never echo response bodies or exception text: they may contain credentials.
    if not isinstance(result, dict) or result.get("stat") != "ok":
        raise RuntimeError(f"UptimeRobot {method} rejected the request; check the API key, account limits and settings.")
    return result


def ensure_monitor(client: httpx.Client, api_key: str, params: dict) -> tuple[str, int]:
    offset = 0
    matches = []
    while True:
        result = api_call(client, api_key, "getMonitors", offset=offset, limit=50)
        monitors = result["monitors"]
        matches.extend(m for m in monitors if m["url"] == params["url"] and int(m["type"]) == 1)
        offset += len(monitors)
        if offset >= int(result["pagination"]["total"]):
            break
        if not monitors:
            raise RuntimeError("UptimeRobot returned incomplete monitor pagination; no monitor created.")
    if len(matches) > 1:
        raise RuntimeError("Multiple HTTP monitors already use this URL; resolve duplicates in UptimeRobot.")
    if matches:
        monitor = matches[0]
        if int(monitor["status"]) == 0:
            raise RuntimeError("The existing monitor is paused; resume it in UptimeRobot.")
        return "existing", int(monitor["id"])
    result = api_call(client, api_key, "newMonitor", **params)
    return "created", int(result["monitor"]["id"])


def main(argv=None) -> int:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.getenv("PUBLIC_APP_URL", ""))
    parser.add_argument("--name", default="LLM Guardrails - API health")
    parser.add_argument("--interval", type=int, default=300, help="Seconds between probes (default: 300)")
    parser.add_argument("--alert-contacts", default=os.getenv("UPTIMEROBOT_ALERT_CONTACTS", ""),
                        help="UptimeRobot contact IDs, e.g. 123_0_0-456_0_0")
    parser.add_argument("--dry-run", action="store_true", help="Print configuration without network calls or credentials")
    args = parser.parse_args(argv)
    try:
        url = health_url(args.url)
        if args.interval < 300 or args.interval % 60:
            raise ValueError("Interval must be at least 300 seconds and a multiple of 60.")
        contacts = args.alert_contacts.strip()
        if contacts and not re.fullmatch(r"\d+_\d+_\d+(?:-\d+_\d+_\d+)*", contacts):
            raise ValueError("Alert contacts must use the format 123_0_0-456_0_0.")
        params = {"friendly_name": args.name, "url": url, "type": 1,
                  "http_method": 2, "interval": args.interval, "timeout": 30,
                  "custom_http_statuses": "200:1_503:0", "ignore_ssl_errors": 0}
        if contacts:
            params["alert_contacts"] = contacts
        if args.dry_run:
            print(json.dumps(params, indent=2))
            return 0
        api_key = os.getenv("UPTIMEROBOT_API_KEY", "").strip()
        if not api_key:
            raise ValueError("Set UPTIMEROBOT_API_KEY to an account API key with write access.")
        if not contacts:
            raise ValueError("Set UPTIMEROBOT_ALERT_CONTACTS or --alert-contacts so downtime alerts have a recipient.")
        with httpx.Client(timeout=30, follow_redirects=False) as client:
            action, monitor_id = ensure_monitor(client, api_key, params)
        print(f"Monitor {action}: {monitor_id} ({url})")
        if action == "existing":
            print("Existing settings preserved; verify its interval, HTTP method and alert contacts in UptimeRobot.")
        return 0
    except (ValueError, RuntimeError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
