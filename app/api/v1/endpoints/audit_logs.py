from fastapi import APIRouter, Query
from sqlalchemy import desc, select

from app.core.deps import AdminUser, DbSession
from app.models.audit_log import AuditLog

router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])


@router.get("")
def list_audit_logs(
    db: DbSession,
    _: AdminUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    query = select(AuditLog).order_by(desc(AuditLog.id))
    items = list(
        db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    )
    return {"items": items, "page": page, "page_size": page_size}

