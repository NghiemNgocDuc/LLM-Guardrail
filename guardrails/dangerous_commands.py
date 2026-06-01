"""
Destructive or high-risk shell/SQL/system command patterns for agent skill scanning.

Flags commands that skills should not instruct agents to run (disk wipe, force push,
pipe-to-shell, etc.). Used by guardrails/skill.py and CI skill scans.
"""
from __future__ import annotations

# (reason_code, check_name, regex, risk_score)
DANGEROUS_COMMAND_PATTERNS: list[tuple[str, str, str, float]] = [
    (
        "rm_rf_destructive",
        "Destructive recursive delete",
        (
            r"(?i)\brm\s+(-[a-zA-Z]+\s+)*-rf\b[^\n]*"
            r"(\s+/\s*|\s+/\*|\s+~|--no-preserve-root|"
            r"\s+/(?:etc|usr|var|bin|sbin|boot|System32)(?:\s|$))"
        ),
        0.98,
    ),
    (
        "drop_sql",
        "SQL DROP statement",
        r"(?i)\bDROP\s+(TABLE|DATABASE|SCHEMA)\b",
        0.95,
    ),
    (
        "truncate_sql",
        "SQL TRUNCATE statement",
        r"(?i)\bTRUNCATE\s+TABLE\b",
        0.9,
    ),
    (
        "delete_sql_unbounded",
        "SQL DELETE without WHERE",
        r"(?i)\bDELETE\s+FROM\s+[`'\"]?\w+[`'\"]?\s*;",
        0.85,
    ),
    (
        "disk_wipe",
        "Disk overwrite / format",
        r"(?i)\bdd\s+if=[^\s]+\s+of=/dev/|\bmkfs\.|format\s+[a-z]:",
        0.98,
    ),
    (
        "curl_pipe_shell",
        "Remote script piped to shell",
        r"(?i)\b(curl|wget)\s+[^\n|]+\|\s*(ba)?sh\b",
        0.95,
    ),
    (
        "powershell_iex",
        "PowerShell invoke-expression",
        r"(?i)\bInvoke-Expression\b|\biex\s*\(",
        0.92,
    ),
    (
        "powershell_rm_force",
        "PowerShell recursive force delete",
        r"(?i)Remove-Item\s+[^\n]*-Recurse[^\n]*-Force",
        0.9,
    ),
    (
        "windows_del_force",
        "Windows forced delete",
        r"(?i)\bdel\s+/[fq]s?\b|Format-Volume",
        0.9,
    ),
    (
        "chmod_world_writable_root",
        "World-writable permissions on root",
        r"(?i)\bchmod\s+(-R\s+)?777\s+/",
        0.88,
    ),
    (
        "git_destructive",
        "Destructive git operation",
        r"(?i)\bgit\s+push\s+[^\n]*--force|\bgit\s+reset\s+--hard|\bgit\s+clean\s+-[a-z]*f",
        0.85,
    ),
    (
        "system_shutdown",
        "System shutdown or reboot",
        r"(?i)\b(shutdown|reboot|poweroff|halt)\s+(-[hfr]|/s|now)\b",
        0.88,
    ),
    (
        "fork_bomb",
        "Fork bomb pattern",
        r":\(\)\s*\{\s*:\|:",
        0.99,
    ),
    (
        "eval_exec_injection",
        "Dynamic eval/exec of shell",
        r"(?i)\beval\s+[`$]|\bexec\s*\(\s*[`$]",
        0.9,
    ),
    (
        "iptables_flush",
        "Flush firewall rules",
        r"(?i)\biptables\s+-F\b",
        0.85,
    ),
    (
        "kill_all",
        "Kill all processes",
        r"(?i)\bkill(all)?\s+-9\s+(-1|0)\b|\bpkill\s+-9\b",
        0.9,
    ),
]
