# Point this repo at .githooks/ so pre-push runs Skill Guard before GitHub push.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

git config core.hooksPath .githooks

Write-Host "Installed git hooks from .githooks/"
Write-Host "  pre-push -> guardrail-scan --pre-push (Go binary if built, else scripts/scan_agent_skills.py --pre-push)"
Write-Host ""
Write-Host "To use the fast Go binary, build it first:"
Write-Host "  cd cli/guardrail-scan && go build -o guardrail-scan.exe ."
Write-Host ""
Write-Host "Pushes that change .cursor/skills/ are blocked when secrets, PII, or destructive commands are detected."
Write-Host "To uninstall: git config --unset core.hooksPath"
