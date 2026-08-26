"""Open Policy Agent (OPA) sidecar client for org custom Rego rules.

Org custom rules are written in Rego (``OrgPolicy.custom_rule_rego``) and
evaluated by a dedicated OPA server process (the ``opa`` service in
docker-compose.yml) rather than an embedded interpreter. Rego's language
design has no filesystem/network/OS capabilities to sandbox away, which is
why it is the right tool here instead of a general-purpose embedded language.

Topology
--------
OPA runs as a sidecar on the API's internal Docker network only
(``internal`` network in docker-compose.yml) — it is not reachable from web/
Nginx or the public internet. The API talks to it over plain HTTP on
``OPA_URL`` (default ``http://opa:8181``).

Fail-closed policy
------------------
This is a security product, so OPA failures are treated as guardrail
failures, not skips:

  * OPA unreachable / connection error / HTTP 5xx  -> block the request
  * query takes longer than ``OPA_TIMEOUT_SECONDS``  -> block the request
  * decision missing, malformed, or action not in    -> block the request
    {block, warn, pass}
  * Rego fails to compile at save time               -> reject the save

The timeout defaults to 2.0 seconds (``OPA_TIMEOUT_SECONDS``). A trivial
Rego query against a localhost sidecar normally completes in single-digit
milliseconds, so 2s is far above the normal envelope while still bounding
how long a hung OPA can hold a request.

Policy loading
--------------
Each org's Rego is stored in OPA's in-memory store under the policy id
``org_<sanitized org id>``. The org's ``package`` declaration is rewritten
to a per-org package (``package org_<sanitized org id>``) so policies from
different orgs can never collide in the shared store. Evaluation queries
``/v1/data/<package>/decision`` with input ``{"prompt", "findings"}`` where
``findings`` is the list of standard guardrail checks that already ran
(``[{"check", "reason_code", "matched"}]``).

Policies are not pushed on save: at request time the data query is tried
first, and on a 404 (e.g. OPA restarted and the in-memory store was lost)
the policy is upserted and the query retried once. This is self-healing and
adds no per-request writes in the common case.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import uuid

import httpx

from app.config import get_settings

# Rego identifiers: letters, digits, underscores; must not start with a digit.
_PACKAGE_RE = re.compile(r"(?im)^\s*package\s+([A-Za-z_][A-Za-z0-9_.]*)\s*$")


class OPAValidationError(Exception):
    """The Rego source does not compile (raised by ``validate``)."""


class OPAUnavailableError(Exception):
    """OPA is unreachable, timed out, or returned an error response."""


def sanitize_org_id(org_id: str) -> str:
    """OPA-safe token for an org: policy ids allow [A-Za-z0-9_-], Rego
    package segments must be valid identifiers (no hyphens)."""
    return "org_" + re.sub(r"[^A-Za-z0-9_]", "", org_id)


def rewrite_package(rego: str, org_id: str) -> str:
    """Rewrite the org's ``package <name>`` to a per-org package so orgs can
    never collide in the shared OPA store. The package line must exist —
    ``validate`` enforces this at save time."""
    pkg = sanitize_org_id(org_id)
    replaced = _PACKAGE_RE.sub(lambda m: f"package {pkg}", rego, count=1)
    if replaced == rego:
        raise OPAValidationError(
            "Rego must declare a package (e.g. `package guardrails`)"
        )
    return replaced


def _default_url() -> str:
    return get_settings().OPA_URL or "http://opa:8181"


def _timeout() -> float:
    return get_settings().OPA_TIMEOUT_SECONDS


def _client() -> httpx.Client:
    """Module-level shared sync client (OPA is a localhost sidecar; the call
    is a short bounded HTTP hop, see the timeout contract above)."""
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = httpx.Client(base_url=_default_url(), timeout=_timeout())
    return _CLIENT


_CLIENT: httpx.Client | None = None


def reset_client() -> None:
    """Drop the cached client (tests / dev reloads)."""
    global _CLIENT
    if _CLIENT is not None:
        _CLIENT.close()
        _CLIENT = None


def rego_lint(rego: str) -> None:
    """Optional fast-fail pre-check via the Haskell `rego-lint` CLI.

    Runs before the authoritative OPA compile check in ``validate`` when a
    rego-lint binary is available (``REGOLINT_BIN`` env var, or on PATH).
    Skipped silently when the binary is not installed — the OPA round trip
    stays the source of truth.

    Raises ``OPAValidationError`` with the linter's per-issue output on a
    failed check.
    """
    binary = os.environ.get("REGOLINT_BIN") or shutil.which("rego-lint")
    if not binary:
        return None
    proc = subprocess.run(
        [binary, "-"], input=rego, capture_output=True, text=True, timeout=10
    )
    if proc.returncode == 0:
        return None
    detail = proc.stderr.strip() or f"rego-lint exited with status {proc.returncode}"
    raise OPAValidationError(f"rego-lint: {detail}")


def validate(rego: str) -> None:
    """Compile-check a Rego source WITHOUT keeping it in OPA.

    Raises ``OPAValidationError`` (bad Rego, including missing package) or
    ``OPAUnavailableError`` (OPA unreachable — save must be rejected; a
    policy we could not validate must not be persisted).
    """
    if not rego or not rego.strip():
        raise OPAValidationError("Rego source is empty")
    rego_lint(rego)  # optional fast-fail; the OPA check below is authoritative
    if _PACKAGE_RE.search(rego) is None:
        raise OPAValidationError(
            "Rego must declare a package (e.g. `package guardrails`)"
        )
    probe_id = "validate_" + uuid.uuid4().hex
    try:
        resp = _client().put(f"/v1/policies/{probe_id}", json={"policy": rego})
    except httpx.HTTPError as e:
        raise OPAUnavailableError(f"OPA unreachable during validation: {e}") from e
    try:
        if resp.status_code in (200, 201):
            return
        if resp.status_code == 400:
            raise OPAValidationError(_opa_error_text(resp))
        raise OPAUnavailableError(
            f"OPA validation failed with status {resp.status_code}"
        )
    finally:
        try:
            _client().delete(f"/v1/policies/{probe_id}")
        except httpx.HTTPError:
            pass  # best-effort cleanup; probe ids are unique and harmless


def _opa_error_text(resp: httpx.Response) -> str:
    try:
        data = resp.json()
        errors = data.get("errors") or []
        if errors:
            msg = errors[0].get("message") or str(errors[0])
            return f"Invalid Rego: {msg}"
        return "Invalid Rego"
    except ValueError:
        return f"Invalid Rego (HTTP {resp.status_code})"


def evaluate(rego: str, org_id: str, prompt: str, findings: list[dict]) -> tuple[str, str]:
    """Evaluate the org's Rego against a prompt plus the standard checks'
    findings. Returns (action, reason) with action in {"block","warn","pass"}.

    Raises ``OPAUnavailableError`` on ANY failure (unreachable, timeout,
    HTTP error, malformed/missing decision) — the caller fails closed.
    """
    source = rewrite_package(rego, org_id)
    path = f"/v1/data/{sanitize_org_id(org_id)}/decision"
    body = {"input": {"prompt": prompt, "findings": findings}}

    resp = _query(path, body)
    if resp.status_code == 404:
        _put_policy(org_id, source)
        resp = _query(path, body)
    if resp.status_code == 400:
        raise OPAUnavailableError(_opa_error_text(resp))
    if resp.status_code != 200:
        raise OPAUnavailableError(f"OPA query failed with status {resp.status_code}")
    try:
        result = resp.json().get("result")
    except ValueError as e:
        raise OPAUnavailableError("OPA returned a non-JSON response") from e

    if not isinstance(result, dict):
        raise OPAUnavailableError(
            "OPA decision is not defined — Rego must set a `decision` object "
            "with {action, reason}"
        )
    action = result.get("action")
    reason = result.get("reason")
    if action not in ("block", "warn", "pass") or not isinstance(reason, str):
        raise OPAUnavailableError(
            "OPA decision must be an object with `action` in "
            "{block, warn, pass} and a string `reason`"
        )
    return action, reason


def _query(path: str, body: dict) -> httpx.Response:
    try:
        return _client().post(path, json=body)
    except httpx.HTTPError as e:
        raise OPAUnavailableError(f"OPA unreachable: {e}") from e


def _put_policy(org_id: str, source: str) -> None:
    resp = _client().put(
        f"/v1/policies/{sanitize_org_id(org_id)}", json={"policy": source}
    )
    if resp.status_code not in (200, 201):
        raise OPAUnavailableError(
            f"OPA policy upload failed with status {resp.status_code}"
        )
