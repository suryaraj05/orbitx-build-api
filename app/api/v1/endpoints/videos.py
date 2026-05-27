from fastapi import APIRouter, HTTPException, Request, status

from app.core.deps import DbSession, EditorUser
from app.models.video import Video
from app.schemas.common import MessageResponse
from app.schemas.video import VideoCreate, VideoRead, VideoUpdate
from app.utils import apply_updates
from app.audit import model_snapshot, write_audit_log

router = APIRouter(prefix="/videos", tags=["videos"])


@router.post("", response_model=VideoRead, status_code=status.HTTP_201_CREATED)
def create_video(payload: VideoCreate, db: DbSession, user: EditorUser, request: Request):
    video = Video(**payload.model_dump())
    db.add(video)
    db.commit()
    db.refresh(video)
    write_audit_log(
        db,
        actor=user,
        action="create",
        entity_type="video",
        entity_id=str(video.id),
        before=None,
        after=model_snapshot(video),
        request=request,
    )
    return video


@router.patch("/{video_id}", response_model=VideoRead)
def update_video(video_id: int, payload: VideoUpdate, db: DbSession, user: EditorUser, request: Request):
    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    before = model_snapshot(video)
    apply_updates(video, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(video)
    write_audit_log(
        db,
        actor=user,
        action="update",
        entity_type="video",
        entity_id=str(video.id),
        before=before,
        after=model_snapshot(video),
        request=request,
    )
    return video


@router.delete("/{video_id}", response_model=MessageResponse)
def delete_video(video_id: int, db: DbSession, user: EditorUser, request: Request):
    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    before = model_snapshot(video)
    db.delete(video)
    db.commit()
    write_audit_log(
        db,
        actor=user,
        action="delete",
        entity_type="video",
        entity_id=str(video_id),
        before=before,
        after=None,
        request=request,
    )
    return MessageResponse(message="Video deleted")
