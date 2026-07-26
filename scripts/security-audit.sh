#!/usr/bin/env bash
set -euo pipefail

echo "=== Python dependency audit ==="
pip install -q pip-audit 2>/dev/null
pip-audit || echo "WARNING: pip-audit found vulnerabilities (review above)"

echo ""
echo "=== JavaScript dependency audit ==="
if [ -f "node_modules/.package-lock.json" ]; then
  npm audit --audit-level=high || echo "WARNING: npm audit found vulnerabilities (review above)"
else
  echo "(node_modules not installed — skipping)"
fi

echo ""
echo "=== Secrets scan (truffleHog / gitleaks) ==="
if command -v gitleaks &>/dev/null; then
  gitleaks detect --no-git -v
elif command -v trufflehog3 &>/dev/null; then
  trufflehog3 filesystem --root .
else
  echo "No secret scanner installed. Install gitleaks: brew install gitleaks"
  echo "Scanning for common secret patterns with grep..."
  grep -rn --include="*.py" --include="*.jsx" --include="*.js" \
    -E '(sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9_]{36,}|-----BEGIN (RSA|OPENSSH) PRIVATE)' \
    . 2>/dev/null || echo "(no secrets found)"
fi

echo ""
echo "=== File permission check ==="
find . -type f -perm /o+w -not -path "./.git/*" -not -path "./node_modules/*" 2>/dev/null | \
  while read f; do echo "WARNING: world-writable: $f"; done

echo ""
echo "=== Security audit complete ==="
