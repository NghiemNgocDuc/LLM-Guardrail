#!/bin/sh
# Point this repo at .githooks/ so pre-push runs Skill Guard before GitHub push.
set -e

ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

chmod +x .githooks/pre-push 2>/dev/null || true
git config core.hooksPath .githooks

echo "Installed git hooks from .githooks/"
echo "  pre-push → guardrail-scan --pre-push (Go binary if built, else scripts/scan_agent_skills.py --pre-push)"
echo ""
echo "To use the fast Go binary, build it first:"
echo "  cd cli/guardrail-scan && make build"
echo ""
echo "Pushes that change .cursor/skills/ are blocked when secrets, PII, or destructive commands are detected."
echo "To uninstall: git config --unset core.hooksPath"
