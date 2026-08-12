#!/usr/bin/env python
"""Benchmark the OPA/Rego final-gate overhead added to /chat.

The Rego rule is the FINAL gate inside InputGuardrail.check â€” the only part
of /chat that changes when a custom rule is configured. This measures the
end-to-end InputGuardrail.check() cost with and without a trivial Rego rule
against a REAL OPA server (the same sidecar topology as docker-compose,
minus the Docker wrapper).

Usage:
    scripts/benchmark_rego_overhead.py [--requests N]

OPA binary: set OPA_BIN to the opa executable (default: tries
opa_windows_amd64.exe next to the script, then `opa` on PATH). A real OPA
server is required â€” the numbers below are only meaningful against the
actual engine.
"""
import argparse
import os
import socket
import statistics
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))  # importable when run as scripts/...py

# A trivial rule: block anything containing "acme". This is the cheapest
# realistic policy â€” real org rules do more work (string matching, findings
# inspection), so real overhead is >= what is measured here.
TRIVIAL_REGO = r"""
package guardrails

decision := {"action": "block", "reason": "acme is banned"} {
    contains(input.prompt, "acme")
}
decision := {"action": "pass", "reason": "ok"} {
    not contains(input.prompt, "acme")
}
"""

PORT = 18181
OPA_URL = f"http://127.0.0.1:{PORT}"

CLEAN_PROMPT = "Please write a haiku about the ocean at sunrise."
FLAGGED_PROMPT = "Please discuss the acme pricing tiers in detail."


def _find_opa() -> Path:
    for candidate in (
        os.environ.get("OPA_BIN"),
        SCRIPT_DIR / "opa_windows_amd64.exe",
        PROJECT_ROOT / "opa_windows_amd64.exe",
        "opa",
    ):
        if not candidate:
            continue
        if isinstance(candidate, str) and candidate == "opa":
            import shutil
            found = shutil.which("opa")
            if found:
                return Path(found)
            continue
        p = Path(candidate)
        if p.is_file():
            return p
    raise SystemExit(
        "OPA binary not found. Set OPA_BIN or place opa_windows_amd64.exe in "
        "scripts/. Download: https://github.com/open-policy-agent/opa/releases"
    )


def _wait_ready(timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{OPA_URL}/health", timeout=1):
                return
        except Exception:
            time.sleep(0.2)
    raise SystemExit("OPA server did not become healthy")


def _pick_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requests", type=int, default=1000, help="checks per mode")
    args = parser.parse_args()
    n = args.requests
    global PORT, OPA_URL
    PORT = _pick_port()
    OPA_URL = f"http://127.0.0.1:{PORT}"

    os.environ["OPA_URL"] = OPA_URL
    os.environ["OPA_TIMEOUT_SECONDS"] = "2.0"

    opa_bin = _find_opa()
    proc = subprocess.Popen(
        [str(opa_bin), "run", "--server", "--addr", f"127.0.0.1:{PORT}", "--log-level", "error"],
        cwd=PROJECT_ROOT,
    )
    try:
        _wait_ready()

        # Import AFTER OPA_URL is set so the settings read at first use are right.
        import guardrails.opa as opa
        from guardrails.input import InputGuardrail

        opa.reset_client()
        policy = {"block_secrets": True, "block_pii": True}

        # â”€â”€ 0. Cold path: first check triggers 404 â†’ policy PUT â†’ query â”€â”€â”€â”€â”€
        cold_guard = InputGuardrail(policy, custom_rule_rego=TRIVIAL_REGO, org_id="bench")
        t0 = time.perf_counter()
        cold_guard.check(FLAGGED_PROMPT)
        cold_ms = (time.perf_counter() - t0) * 1000
        # warm the HTTP client connection
        cold_guard.check(CLEAN_PROMPT)

        def bench(check_fn) -> list[float]:
            times: list[float] = []
            for i in range(n):
                prompt = FLAGGED_PROMPT if i % 2 else CLEAN_PROMPT
                t0 = time.perf_counter()
                check_fn(prompt)
                times.append((time.perf_counter() - t0) * 1000)
            return times

        baseline = InputGuardrail(policy)
        rego = InputGuardrail(policy, custom_rule_rego=TRIVIAL_REGO, org_id="bench")

        base_times = bench(baseline.check)
        rego_times = bench(rego.check)

        base_avg = statistics.fmean(base_times)
        rego_avg = statistics.fmean(rego_times)
        overhead = rego_avg - base_avg
        overhead_pct = (overhead / base_avg * 100) if base_avg else float("inf")

        print(f"OPA binary : {opa_bin}")
        print(f"OPA server : {OPA_URL} (sidecar topology, loopback)")
        print(f"Requests   : {n} per mode (alternating clean/flagged)")
        print()
        print(f"Baseline (no custom rule):  {base_avg:8.3f} ms/check  (p50 {statistics.median(base_times):.3f} ms)")
        print(f"With Rego rule:            {rego_avg:8.3f} ms/check  (p50 {statistics.median(rego_times):.3f} ms)")
        print(f"Cold first check (404->PUT): {cold_ms:8.3f} ms")
        print(f"Overhead: {overhead:+.3f} ms/check ({overhead_pct:+.1f}%)")
        print()
        print("Notes: overhead is one HTTP round-trip to a loopback sidecar +")
        print("Rego evaluation of a trivial rule. On the compose network the")
        print("round-trip is similar (same host). p50 < p95 for real policies")
        print("that scan findings; the timeout bound is OPA_TIMEOUT_SECONDS.")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    main()
