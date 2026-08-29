"""Tool approvals — human gate for high-risk MCP actions."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.deps import CurrentUser
from app.i18n import _t
from app.models import ToolApproval

router = APIRouter(prefix="/tool-approvals", tags=["ToolApprovals"])

def _require_admin(u):
    if not u.is_admin:
        raise HTTPException(status_code=403, detail=_t("admin.access_required"))

@router.get("", response_model=list[dict])
async def list_pending(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    _require_admin(current_user)
    q = await db.execute(select(ToolApproval).where(ToolApproval.org_id == current_user.org_id, ToolApproval.status == "pending").order_by(ToolApproval.created_at.desc()).limit(50))
    return [{"id": r.id, "tool_name": r.tool_name, "tool_input": r.tool_input, "risk_level": r.risk_level, "status": r.status, "created_at": r.created_at} for r in q.scalars().all()]

@router.post("/{approval_id}/decision")
async def decide(approval_id: str, body: dict, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    _require_admin(current_user)
    ap = await db.get(ToolApproval, approval_id)
    if not ap or ap.org_id != current_user.org_id:
        raise HTTPException(status_code=404, detail="approval not found")
    action = body.get("action")  # approved|rejected
    if action not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="action must be approved|rejected")
    from datetime import datetime, timezone
    ap.status = action
    ap.decided_at = datetime.now(timezone.utc)
    await db.flush()
    return {"id": ap.id, "status": ap.status}
