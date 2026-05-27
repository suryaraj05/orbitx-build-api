from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import Request
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.user import User


def _jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def model_snapshot(obj: Any) -> dict[str, Any]:
    """Best-effort snapshot of SQLAlchemy model columns (no relationships)."""
    data: dict[str, Any] = {}
    mapper = inspect(obj).mapper
    for attr in mapper.column_attrs:
        key = attr.key
        data[key] = _jsonable(getattr(obj, key))
    return data


def request_meta(request: Request | None) -> dict[str, Any] | None:
    if request is None:
        return None
    return {
        "ip": request.client.host if request.client else None,
        "path": str(request.url.path),
        "method": request.method,
        "user_agent": request.headers.get("user-agent"),
    }


def write_audit_log(
    db: Session,
    *,
    actor: User | None,
    action: str,
    entity_type: str,
    entity_id: str | None,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    request: Request | None = None,
) -> None:
    log = AuditLog(
        actor_id=actor.id if actor else None,
        actor_email=actor.email if actor else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before=before,
        after=after,
        meta=request_meta(request),
    )
    db.add(log)
    db.commit()

