"""The repository scan must distinguish prefixes from credentials and bind approvals."""
from scripts.check_repository_secrets import content_digest, scan_content


def test_prefix_documentation_is_not_a_credential():
    assert scan_content("guide.md", "Provider prefixes: gsk_ and sk-; keep keys server-side.", {}) == []


def test_realistic_key_is_reported_without_exposing_the_value():
    credential = "g" + "sk_" + "a" * 32
    findings = scan_content("config.py", "# config\nkey = '" + credential + "'", {})
    assert len(findings) == 1
    assert findings[0].line == 2 and findings[0].rule == "groq_key"
    assert credential not in repr(findings)


def test_reviewed_fixture_approval_expires_on_any_edit():
    content = "key = 'sk-" + "A" * 32 + "'"
    allowlist = {"fixture.py": content_digest(content)}
    assert scan_content("fixture.py", content, allowlist) == []
    assert scan_content("fixture.py", content + "\n# changed", allowlist)
    assert scan_content("other.py", content, allowlist)


def test_environment_secret_and_database_password_are_reported():
    assert scan_content(".env", "SECRET_KEY=" + "a" * 32, {})
    assert scan_content(".env", "DATABASE_URL=postgresql://owner:" + "b" * 20 + "@database/app", {})


def test_empty_environment_fields_and_secret_references_do_not_match():
    assert scan_content(".env.example", "SECRET_KEY=\n\nPOSTGRES_PASSWORD=\nDEFAULT_MODEL=mock-local", {}) == []
    assert scan_content("compose.yml", "postgresql://owner:${POSTGRES_PASSWORD}@db/app", {}) == []
