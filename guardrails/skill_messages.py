"""Human-readable explanations for skill guard findings."""

from __future__ import annotations

_DEFAULT = (
    "This pattern in agent instructions can expose sensitive data or cause harmful actions "
    "when the agent runs tools or sends context to a model."
)

_REASON_MESSAGES: dict[str, str] = {
    "gateway_api_key": "A gateway API key (grg_…) in the skill would be copied into the agent’s context and could reach the LLM or logs.",
    "groq_api_key": "A Groq API key in the skill can be exfiltrated if the agent or model provider logs context.",
    "openai_api_key": "An OpenAI API key in the skill can be leaked through agent context or transcripts.",
    "github_token": "A GitHub token in the skill grants repository access if the agent exposes it.",
    "aws_access_key": "An AWS access key in the skill could allow cloud resource abuse.",
    "private_key": "A private key block must never be embedded in skills or prompts.",
    "secret_detected": "Credential-like material was detected and should live only in a secret manager.",
    "pii_detected": "Personal data in skills may be sent to external models and violate privacy policy.",
    "database_url": "A database URL with credentials lets anyone with the skill connect to production data.",
    "credential_assignment": "Hard-coded passwords or tokens in instructions are often copied verbatim by agents.",
    "bearer_token": "Bearer tokens in skills are treated as trusted instructions and may be logged.",
    "env_assignment": "Environment variable assignments in skills often contain real production secrets.",
    "private_ip": "Internal IPs reveal network topology and may aid lateral movement.",
    "internal_path": "Host-specific paths can leak usernames, machine names, or layout of your environment.",
    "rm_rf_destructive": "Recursive delete against system paths can wipe the machine when an agent runs shell tools.",
    "drop_sql": "DROP statements can destroy production tables if the agent executes SQL.",
    "truncate_sql": "TRUNCATE can erase table data without a WHERE clause.",
    "delete_sql_unbounded": "DELETE without WHERE can remove entire tables.",
    "disk_wipe": "Disk imaging or format commands can destroy data on the host.",
    "curl_pipe_shell": "Piping a remote script into a shell runs arbitrary code with agent privileges.",
    "powershell_iex": "Invoke-Expression executes arbitrary PowerShell from strings in context.",
    "powershell_rm_force": "Forced recursive delete via PowerShell can remove critical files.",
    "windows_del_force": "Windows forced delete commands can destroy system or user data.",
    "chmod_world_writable_root": "World-writable permissions on / weaken the entire system.",
    "git_destructive": "Force push or hard reset can destroy shared git history.",
    "system_shutdown": "Shutdown or reboot commands can interrupt production services.",
    "fork_bomb": "Fork bombs can exhaust process limits and freeze the host.",
    "eval_exec_injection": "Dynamic eval/exec can run attacker-controlled shell from skill text.",
    "iptables_flush": "Flushing firewall rules exposes services to the network.",
    "kill_all": "Killing all processes can crash the system or editor environment.",
}


def explain_finding(reason_code: str, check: str) -> str:
    return _REASON_MESSAGES.get(reason_code, f"{check}. {_DEFAULT}")
