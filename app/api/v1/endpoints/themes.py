from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.core.deps import AdminUser, DbSession
from app.models.theme import Theme
from app.schemas.common import MessageResponse
from app.schemas.theme import ThemeCreate, ThemeRead, ThemeUpdate
from app.utils import apply_updates
from app.audit import model_snapshot, write_audit_log

router = APIRouter(prefix="/themes", tags=["themes"])


@router.get("", response_model=list[ThemeRead])
def list_themes(db: DbSession):
    return list(db.scalars(select(Theme).order_by(Theme.name)).all())


@router.get("/{theme_id}", response_model=ThemeRead)
def get_theme(theme_id: int, db: DbSession):
    theme = db.get(Theme, theme_id)
    if theme is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Theme not found")
    return theme


@router.post("", response_model=ThemeRead, status_code=status.HTTP_201_CREATED)
def create_theme(payload: ThemeCreate, db: DbSession, user: AdminUser, request: Request):
    theme = Theme(**payload.model_dump())
    db.add(theme)
    db.commit()
    db.refresh(theme)
    write_audit_log(
        db,
        actor=user,
        action="create",
        entity_type="theme",
        entity_id=str(theme.id),
        before=None,
        after=model_snapshot(theme),
        request=request,
    )
    return theme


@router.patch("/{theme_id}", response_model=ThemeRead)
def update_theme(theme_id: int, payload: ThemeUpdate, db: DbSession, user: AdminUser, request: Request):
    theme = db.get(Theme, theme_id)
    if theme is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Theme not found")
    before = model_snapshot(theme)
    apply_updates(theme, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(theme)
    write_audit_log(
        db,
        actor=user,
        action="update",
        entity_type="theme",
        entity_id=str(theme.id),
        before=before,
        after=model_snapshot(theme),
        request=request,
    )
    return theme


@router.delete("/{theme_id}", response_model=MessageResponse)
def delete_theme(theme_id: int, db: DbSession, user: AdminUser, request: Request):
    theme = db.get(Theme, theme_id)
    if theme is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Theme not found")
    before = model_snapshot(theme)
    db.delete(theme)
    db.commit()
    write_audit_log(
        db,
        actor=user,
        action="delete",
        entity_type="theme",
        entity_id=str(theme_id),
        before=before,
        after=None,
        request=request,
    )
    return MessageResponse(message="Theme deleted")
