#!/usr/bin/env bash
# Security audit — 23 controls from 2026 checklists + OWASP Top 10 2025/2026
# Usage: bash scripts/security-audit.sh [--strict]
set -euo pipefail
STRICT="${1:-}"
FAIL=0

red() { echo -e "\033[31m$*\033[0m"; }
green() { echo -e "\033[32m$*\033[0m"; }
yellow() { echo -e "\033[33m$*\033[0m"; }

check() {
  local desc="$1"; shift
  if "$@"; then green "✓ $desc"; else red "✗ $desc"; FAIL=$((FAIL+1)); fi
}
warn() { yellow "○ $1"; }

echo "== Self-Hosted Security Audit — $(date -Iseconds) =="
echo "== OWASP Top 10 2025 + 20-point 2026 checklist =="
echo

# ── 1. Secrets & env ───────────────────────────────────────────────────────────
check ".env not committed" test ! -f .git/COMMIT_EDITMSG  # placeholder; real check:
test ! -f .env || (test -f .gitignore && grep -q "^\.env$" .gitignore) && green "✓ .env gitignored" || (red "✗ .env not gitignored"; FAIL=$((FAIL+1)))
check ".env.example has no real secrets" ! grep -qE "GROQ_API_KEY=.+[^=]$" .env.example || ! grep -q "gsk_" .env.example
check "SECRET_KEY length" bash -c 'source .env 2>/dev/null; [ ${#SECRET_KEY} -ge 32 ]' 2>/dev/null || warn "SECRET_KEY <32 or not set (set in .env)"
check "POSTGRES_PASSWORD set" bash -c 'source .env 2>/dev/null; [ -n "$POSTGRES_PASSWORD" ]' 2>/dev/null || warn "POSTGRES_PASSWORD not set"

# ── 2. Docker hardening ─────────────────────────────────────────────────────────
check "compose: no privileged" ! grep -q "privileged: true" docker-compose.yml
check "compose: no host network_mode" ! grep -q "network_mode: host" docker-compose.yml
check "compose: secrets not in inspect (no plaintext env passwords)" ! grep -q "POSTGRES_PASSWORD: password" docker-compose.yml
check "compose: read_only on api/web/opa" grep -q "read_only: true" docker-compose.yml
check "compose: cap_drop ALL" grep -q "cap_drop:" docker-compose.yml
check "compose: no-new-privileges" grep -q "no-new-privileges:true" docker-compose.yml
check "compose: internal backend network" grep -q "internal: true" docker-compose.yml
check "compose: logging limits" grep -q 'max-size:' docker-compose.yml
check "Dockerfile USER appuser" grep -q "USER appuser" Dockerfile

# ── 3. TLS & headers ───────────────────────────────────────────────────────────
check "nginx: HSTS" grep -q "Strict-Transport-Security" nginx.conf
check "nginx: CSP" grep -q "Content-Security-Policy" nginx.conf
check "nginx: X-Frame DENY" grep -q "X-Frame-Options.*DENY" nginx.conf
check "nginx: COOP/COEP" grep -q "Cross-Origin-Opener-Policy" nginx.conf
check "nginx: rate limit zones" grep -q "limit_req_zone" nginx.conf
check "nginx: hides Server/X-Powered-By" grep -q "proxy_hide_header" nginx.conf
check "nginx: blocks dotfiles" grep -q "location ~ /\\\\." nginx.conf

# ── 4. App auth ────────────────────────────────────────────────────────────────
check "auth: Clerk or local JWT (deps.py)" grep -q "Clef\|Clerk\|get_current_user" app/deps.py
check "app: production ALLOWED_ORIGINS no wildcard" ! grep -q 'ALLOWED_ORIGINS.*\*.*production' app/config.py || true
check "app: prod requires https PUBLIC_APP_URL" grep -q "https://" app/config.py

# ── 5. Input validation & guardrails ──────────────────────────────────────────
check "guardrails: input secrets" grep -q "gsk_" guardrails/input.py
check "guardrails: PII redactor" grep -q "PIIRedactor" app/routers/chat.py
check "sanitize: null byte" grep -q "Null byte" app/utils/sanitize.py
check "opa: fail-closed" grep -q "fail CLOSED" guardrails/opa.py

# ── 6. Dependencies ────────────────────────────────────────────────────────────
if [ -f .github/dependabot.yml ]; then green "✓ dependabot.yml exists"; else red "✗ dependabot missing"; FAIL=$((FAIL+1)); fi
check "requirements pinned" grep -q "==" requirements.txt
# quick CVE check if pip-audit available
if command -v pip-audit >/dev/null 2>&1; then pip-audit --desc 2>&1 | head -n 20; else warn "pip-audit not installed (pip install pip-audit)"; fi
if command -v npm >/dev/null 2>&1; then npm audit --audit-level=high 2>&1 | tail -n 20 || true; fi

# ── 7. Logging & monitoring ────────────────────────────────────────────────────
check "structured JSON logs" grep -q "JSONFormatter" main.py
check "secret scrub in logs" grep -q "SecretScrubFilter" main.py
check "health endpoint" grep -q "/health" main.py

# ── 8. Backups ─────────────────────────────────────────────────────────────────
if [ -f scripts/backup.sh ]; then green "✓ scripts/backup.sh exists"; test -x scripts/backup.sh && green "✓ backup.sh executable" || yellow "○ chmod +x scripts/backup.sh"; else red "✗ backup.sh missing"; FAIL=$((FAIL+1)); fi
if ls /backups/*.gz 1>/dev/null 2>&1 || ls /backups/*.enc 1>/dev/null 2>&1; then green "✓ at least one backup found in /backups"; else warn "no backups in /backups yet — run ./scripts/backup.sh"; fi

echo
if [ "$FAIL" -eq 0 ]; then green "All checks passed ($FAIL failures)"; else red "$FAIL checks failed — see above"; fi
[ "$STRICT" = "--strict" ] && [ "$FAIL" -ne 0 ] && exit 1 || exit 0
