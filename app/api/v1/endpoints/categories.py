from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.core.deps import AdminUser, DbSession, EditorUser
from app.models.category import Category
from app.schemas.category import CategoryCreate, CategoryRead, CategoryUpdate
from app.schemas.common import MessageResponse
from app.utils import apply_updates
from app.audit import model_snapshot, write_audit_log

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryRead])
def list_categories(db: DbSession):
    return list(db.scalars(select(Category).order_by(Category.name)).all())


@router.post("", response_model=CategoryRead, status_code=status.HTTP_201_CREATED)
def create_category(payload: CategoryCreate, db: DbSession, user: EditorUser, request: Request):
    category = Category(**payload.model_dump())
    db.add(category)
    db.commit()
    db.refresh(category)
    write_audit_log(
        db,
        actor=user,
        action="create",
        entity_type="category",
        entity_id=str(category.id),
        before=None,
        after=model_snapshot(category),
        request=request,
    )
    return category


@router.patch("/{category_id}", response_model=CategoryRead)
def update_category(category_id: int, payload: CategoryUpdate, db: DbSession, user: EditorUser, request: Request):
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    before = model_snapshot(category)
    apply_updates(category, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(category)
    write_audit_log(
        db,
        actor=user,
        action="update",
        entity_type="category",
        entity_id=str(category.id),
        before=before,
        after=model_snapshot(category),
        request=request,
    )
    return category


@router.delete("/{category_id}", response_model=MessageResponse)
def delete_category(category_id: int, db: DbSession, user: AdminUser, request: Request):
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    before = model_snapshot(category)
    db.delete(category)
    db.commit()
    write_audit_log(
        db,
        actor=user,
        action="delete",
        entity_type="category",
        entity_id=str(category_id),
        before=before,
        after=None,
        request=request,
    )
    return MessageResponse(message="Category deleted")
