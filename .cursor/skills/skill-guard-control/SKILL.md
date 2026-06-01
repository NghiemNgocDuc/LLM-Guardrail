---
name: skill-guard-control
description: When Skill Guard blocks, pause in chat and present Run once / Always allow / Reject / custom message — never the web dashboard.
---

# Skill Guard chat control

If `python scripts/scan_agent_skills.py` fails, or `.cursor/skill-guard-pause.json` exists:

1. Open the pause file and post `chat_prompt` to the user in this conversation.
2. Wait for: **Run once**, **Always allow**, **Reject**, or custom text.
3. Record with `scripts/skill_guard_decision.py` and continue only if allowed.

The web app's Skill Guard page is for **auditing** skills only — not for override buttons.
