from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.core.deps import DbSession, EditorUser
from app.models.resource import Resource
from app.schemas.common import MessageResponse
from app.schemas.resource import ResourceCreate, ResourceRead, ResourceUpdate
from app.utils import apply_updates
from app.utils.audit import model_snapshot, write_audit_log

router = APIRouter(prefix="/resources", tags=["resources"])


@router.get("", response_model=list[ResourceRead])
def list_resources(db: DbSession):
    return list(db.scalars(select(Resource).order_by(Resource.title)).all())


@router.post("", response_model=ResourceRead, status_code=status.HTTP_201_CREATED)
def create_resource(payload: ResourceCreate, db: DbSession, user: EditorUser, request: Request):
    resource = Resource(**payload.model_dump())
    db.add(resource)
    db.commit()
    db.refresh(resource)
    write_audit_log(
        db,
        actor=user,
        action="create",
        entity_type="resource",
        entity_id=str(resource.id),
        before=None,
        after=model_snapshot(resource),
        request=request,
    )
    return resource


@router.patch("/{resource_id}", response_model=ResourceRead)
def update_resource(resource_id: int, payload: ResourceUpdate, db: DbSession, user: EditorUser, request: Request):
    resource = db.get(Resource, resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    before = model_snapshot(resource)
    apply_updates(resource, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(resource)
    write_audit_log(
        db,
        actor=user,
        action="update",
        entity_type="resource",
        entity_id=str(resource.id),
        before=before,
        after=model_snapshot(resource),
        request=request,
    )
    return resource


@router.delete("/{resource_id}", response_model=MessageResponse)
def delete_resource(resource_id: int, db: DbSession, user: EditorUser, request: Request):
    resource = db.get(Resource, resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    before = model_snapshot(resource)
    db.delete(resource)
    db.commit()
    write_audit_log(
        db,
        actor=user,
        action="delete",
        entity_type="resource",
        entity_id=str(resource_id),
        before=before,
        after=None,
        request=request,
    )
    return MessageResponse(message="Resource deleted")
