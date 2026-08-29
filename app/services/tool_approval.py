"""Tool approval gate — InfrastructureSentinel style."""
from app.models import ToolApproval
from datetime import datetime, timezone, timedelta

RISK = {
    "read_file": "low", "query_db": "medium", "send_email": "high",
    "delete_record": "critical", "payment": "critical", "infra_change": "critical",
}

def risk_of(tool: str) -> str:
    return RISK.get(tool, "medium")

async def require_approval(db, org_id: str, user_id: str, tool: str, tool_input: dict, correlation_id: str | None = None):
    """Return approval or create pending. High/critical need human gate."""
    level = risk_of(tool)
    if level in ("low",):
        return None  # auto-allow
    # check existing approved within 1h?
    from sqlalchemy import select
    q = await db.execute(
        select(ToolApproval).where(
            ToolApproval.org_id == org_id, ToolApproval.tool_name == tool,
            ToolApproval.user_id == user_id, ToolApproval.status == "approved",
            ToolApproval.created_at > datetime.now(timezone.utc) - timedelta(hours=1)
        ).limit(1)
    )
    if q.scalar_one_or_none():
        return "approved"
    # create pending
    ap = ToolApproval(
        org_id=org_id, user_id=user_id, tool_name=tool,
        tool_input=tool_input, risk_level=level, status="pending",
        correlation_id=correlation_id,
    )
    db.add(ap)
    await db.flush()
    return ap
