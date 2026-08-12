"""OPA/Rego custom rule (OrgPolicy.custom_rule_rego) — guardrails/input.py.

The rule runs in the OPA sidecar (guardrails/opa.py) with a read-only
`prompt` / `findings` view and must return a decision object
`{action, reason}` with action in block|warn|pass. The rule is the FINAL
gate: when configured, the standard checks feed findings to the rule instead
of blocking directly. Every failure fails closed — an unreachable OPA, a
timeout, a 5xx, or a malformed decision blocks the request, never silently
skips.

The OPA server itself is NOT required for these tests: a fake OPA backed by
httpx.MockTransport stands in for the sidecar (guardrails.opa._CLIENT is
swapped). guardrails/opa.py's own wire contract (package rewrite, 404-retry
upsert, probe cleanup) is exercised through the fake's request log.
"""

import json
import time

import httpx
import pytest

from guardrails import opa
from guardrails.input import InputGuardrail

GOOD_REGO = """
package guardrails

decision := {"action": "pass", "reason": "ok"}
"""

# The fake OPA rejects sources containing "broken". The marker must live in
# the decision body, NOT the package line — package names are rewritten to a
# per-org package before upload, so a marker in `package broken` would vanish.
BROKEN_REGO = GOOD_REGO.replace('"ok"', '"broken!!"')


@pytest.fixture
def fake_opa(monkeypatch):
    """Fake OPA sidecar. Routes:

    - PUT /v1/policies/<id>      — stores the source (400 when it contains
      "broken", emulating a Rego parse error). Returns 404 on POST until a
      policy exists, so the 404-retry upsert path is exercised naturally.
    - POST /v1/data/<pkg>/decision — consults `decision_fn(input)` if set,
      else passes.
    """
    state = {
        "policies": {},
        "decision_fn": None,
        "puts": [],
        "deletes": [],
        "posts": [],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PUT":
            source = json.loads(request.content)["policy"]
            state["puts"].append((request.url.path, source))
            if "broken" in source:
                return httpx.Response(
                    400,
                    json={"errors": [{"message": "rego_parse_error: unexpected token"}]},
                )
            state["policies"][request.url.path] = source
            return httpx.Response(200)
        if request.method == "DELETE":
            state["deletes"].append(request.url.path)
            state["policies"].pop(request.url.path, None)
            return httpx.Response(200)
        if request.method == "POST":
            body = json.loads(request.content)
            state["posts"].append((request.url.path, body))
            # /v1/data/<org>/decision → the org policy id is path segment 3.
            # 404 when THIS org's policy is missing (OPA data path undefined),
            # mirroring the real per-org behaviour.
            org_policy = request.url.path.split("/")[3]
            if f"/v1/policies/{org_policy}" not in state["policies"]:
                return httpx.Response(404)
            if state["decision_fn"] is not None:
                return httpx.Response(200, json={"result": state["decision_fn"](body["input"])})
            return httpx.Response(200, json={"result": {"action": "pass", "reason": "ok"}})
        return httpx.Response(404)

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="http://opa.test:8181",
        timeout=5.0,
    )
    opa.reset_client()
    monkeypatch.setattr(opa, "_CLIENT", client)
    yield state
    opa.reset_client()


@pytest.fixture
def unreachable_opa(monkeypatch):
    """OPA that is never reachable (connection refused)."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://opa.test:8181")
    opa.reset_client()
    monkeypatch.setattr(opa, "_CLIENT", client)
    yield
    opa.reset_client()


def _policy(**extra):
    return {"block_secrets": True, **extra}


def _guard(rego=None, **policy_extra):
    return InputGuardrail(
        _policy(**policy_extra),
        custom_rule_rego=rego,
        org_id="acme",
    )


# ── InputGuardrail integration (guardrails/input.py) ─────────────────────


def test_rego_rule_blocks_on_match(fake_opa):
    fake_opa["decision_fn"] = lambda i: {"action": "block", "reason": "acme is banned"}
    r = _guard(GOOD_REGO).check("please discuss acme pricing")
    assert not r.allowed
    assert r.reason_code == "rego_custom_rule"
    assert r.reason == "acme is banned"


def test_rego_rule_passes_when_clean(fake_opa):
    r = _guard(GOOD_REGO).check("please discuss competitor pricing")
    assert r.allowed
    assert r.reason_code == "clean"


def test_rego_rule_warns(fake_opa):
    fake_opa["decision_fn"] = lambda i: {"action": "warn", "reason": "legal review"}
    r = _guard(GOOD_REGO).check("anything")
    assert r.allowed
    assert r.warned
    assert r.reason_code == "warned_rego_custom_rule"
    assert r.reason == "legal review"


def test_rego_rule_is_final_gate_and_sees_findings(fake_opa):
    # A standard secret check fires; the rule sees the finding and decides.
    seen = []

    def decide(i):
        matched = [f["reason_code"] for f in i["findings"] if f["matched"]]
        seen.append(list(matched))
        return {"action": "block", "reason": "found: " + ",".join(matched)}

    fake_opa["decision_fn"] = decide
    r = _guard(GOOD_REGO).check("Here is a key gsk_abcdefghijklmnopqrstuvwxyz123456")
    assert not r.allowed
    assert r.reason == "found: secret_detected"
    assert seen and "secret_detected" in seen[0]


def test_rego_rule_can_override_standard_block(fake_opa):
    # Final-gate semantics: the rule may allow what the standard checks flag.
    def decide(i):
        if any(f["reason_code"] == "secret_detected" and f["matched"] for f in i["findings"]):
            return {"action": "pass", "reason": "allowed sandbox key"}
        return {"action": "pass", "reason": "ok"}

    fake_opa["decision_fn"] = decide
    r = _guard(GOOD_REGO).check("Here is a key gsk_abcdefghijklmnopqrstuvwxyz123456")
    assert r.allowed


def test_rego_rule_unreachable_fails_closed(unreachable_opa):
    r = _guard(GOOD_REGO).check("hello")
    assert not r.allowed
    assert r.reason_code == "rego_rule_error"
    assert "unreachable" in r.reason.lower() or "refused" in r.reason.lower()


def test_rego_rule_timeout_fails_closed(monkeypatch):
    # httpx.MockTransport runs handlers synchronously and does not enforce
    # client timeouts, so the handler raises the exact exception a real
    # timeout produces: httpx.ReadTimeout.
    def slow_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out reading response", request=request)

    client = httpx.Client(
        transport=httpx.MockTransport(slow_handler),
        base_url="http://opa.test:8181",
    )
    opa.reset_client()
    monkeypatch.setattr(opa, "_CLIENT", client)
    try:
        start = time.monotonic()
        r = _guard(GOOD_REGO).check("hello")
        elapsed = time.monotonic() - start
        assert not r.allowed
        assert r.reason_code == "rego_rule_error"
        assert "timed out" in r.reason or "unreachable" in r.reason
        assert elapsed < 1.0, "timeout must bound the query, not hang it"
    finally:
        opa.reset_client()


def test_rego_rule_compile_error_fails_closed(fake_opa):
    # The policy is not in OPA yet → 404 → upsert → OPA rejects it with 400.
    r = _guard(BROKEN_REGO).check("hello")
    assert not r.allowed
    assert r.reason_code == "rego_rule_error"


def test_rego_rule_decision_missing_fails_closed(fake_opa):
    fake_opa["decision_fn"] = lambda i: None  # decision is not defined
    r = _guard(GOOD_REGO).check("hello")
    assert not r.allowed
    assert r.reason_code == "rego_rule_error"
    assert "decision" in r.reason.lower()


def test_rego_rule_malformed_decision_fails_closed(fake_opa):
    for bad in [
        {"action": "banana", "reason": "x"},
        {"action": "block"},                       # missing reason
        {"action": "block", "reason": 42},         # non-string reason
        ["block", "x"],                            # not an object
    ]:
        fake_opa["decision_fn"] = lambda i, b=bad: b
        r = _guard(GOOD_REGO).check("hello")
        assert not r.allowed, f"should fail closed: {bad!r}"
        assert r.reason_code == "rego_rule_error"


def test_no_rego_rule_unchanged_short_circuit(fake_opa):
    # Without a rule the standard checks short-circuit exactly as before,
    # and OPA is never contacted.
    g = InputGuardrail(_policy())
    r = g.check("Here is a key gsk_abcdefghijklmnopqrstuvwxyz123456")
    assert not r.allowed
    assert r.reason_code == "secret_detected"
    assert not fake_opa["posts"]


# ── guardrails/opa.py wire contract ──────────────────────────────────────


def test_validate_accepts_valid_rego(fake_opa):
    opa.validate(GOOD_REGO)
    assert fake_opa["puts"], "probe policy must be uploaded for compilation"
    assert fake_opa["deletes"], "probe policy must be cleaned up after validation"


def test_validate_rejects_bad_rego(fake_opa):
    with pytest.raises(opa.OPAValidationError, match="Invalid Rego"):
        opa.validate(BROKEN_REGO)
    assert fake_opa["deletes"], "probe must be cleaned up even on failure"


def test_validate_unreachable_fails_closed(unreachable_opa):
    with pytest.raises(opa.OPAUnavailableError):
        opa.validate(GOOD_REGO)


def test_validate_requires_package_and_content(fake_opa):
    with pytest.raises(opa.OPAValidationError, match="package"):
        opa.validate("decision := 1")
    with pytest.raises(opa.OPAValidationError, match="empty"):
        opa.validate("   ")
    assert not fake_opa["puts"], "no HTTP call for trivially-invalid source"


def test_evaluate_rewrites_package_per_org(fake_opa):
    opa.evaluate(GOOD_REGO, org_id="acme-2!", prompt="hi", findings=[])
    opa.evaluate(GOOD_REGO, org_id="acme", prompt="hi", findings=[])
    ids = [p for p, _ in fake_opa["puts"]]
    assert ids == ["/v1/policies/org_acme2", "/v1/policies/org_acme"]
    assert "package org_acme2" in fake_opa["puts"][0][1]
    assert "package org_acme" in fake_opa["puts"][1][1]
def test_evaluate_requires_package(fake_opa):
    with pytest.raises(opa.OPAValidationError, match="package"):
        opa.evaluate("decision := 1", org_id="acme", prompt="hi", findings=[])


def test_evaluate_retries_after_404_upsert(fake_opa):
    # Fake starts empty: first POST 404s, PUT stores, second POST succeeds.
    action, reason = opa.evaluate(GOOD_REGO, org_id="acme", prompt="hi", findings=[])
    assert action == "pass"
    assert reason == "ok"
    assert [p for p, _ in fake_opa["puts"]] == ["/v1/policies/org_acme"]
    assert len(fake_opa["posts"]) == 2  # 404, then success
