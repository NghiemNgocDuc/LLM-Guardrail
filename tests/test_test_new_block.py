"""Test auto-generated test cases for new blocks."""
from guardrails.test_case_generator import generate_test_cases, run_test_cases

def test_generate_and_run_secret_block():
    # Content with actual secret pattern triggers secret cases
    content = "Here is a secret: gsk_" + "A"*30
    cases = generate_test_cases(content, org_policy={"block_secrets": True, "block_pii": True})
    # Should generate secret + still have benign
    assert any(c.category == "secret" and c.expected_blocked for c in cases)
    assert any(c.category == "benign" and not c.expected_blocked for c in cases)
    results = run_test_cases(cases, org_policy={"block_secrets": True, "block_pii": True})
    fails = [r for r in results if not r["passed"]]
    assert not fails, fails

def test_generate_from_safe_content_still_has_smoke_tests():
    content = "Summarize docs."
    cases = generate_test_cases(content, org_policy={"block_secrets": True})
    # Even safe content gets smoke secret tests
    assert len(cases) >= 3
    results = run_test_cases(cases, org_policy={"block_secrets": True})
    fails = [r for r in results if not r["passed"]]
    assert not fails, fails

def test_destructive_generates_destructive_cases():
    content = "Run rm -rf / and DROP TABLE"
    cases = generate_test_cases(content, org_policy={"block_secrets": True})
    assert any(c.category == "destructive" for c in cases)
