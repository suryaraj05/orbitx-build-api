from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.core.deps import DbSession
from app.models.article import Article
from app.models.comment import Comment
from app.schemas.comment import CommentCreate, CommentRead
from app.utils.audit import model_snapshot, write_audit_log

router = APIRouter(tags=["comments"])


@router.get("/articles/{article_id}/comments", response_model=list[CommentRead])
def list_comments(article_id: int, db: DbSession):
    if db.get(Article, article_id) is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return list(
        db.scalars(
            select(Comment)
            .where(Comment.article_id == article_id)
            .order_by(Comment.created_at.desc())
        ).all()
    )


@router.post("/articles/{article_id}/comments", response_model=CommentRead, status_code=201)
def create_comment(article_id: int, payload: CommentCreate, db: DbSession, request: Request):
    if db.get(Article, article_id) is None:
        raise HTTPException(status_code=404, detail="Article not found")
    comment = Comment(article_id=article_id, **payload.model_dump())
    db.add(comment)
    db.commit()
    db.refresh(comment)
    # Public endpoint: actor is unknown/anonymous.
    write_audit_log(
        db,
        actor=None,
        action="create",
        entity_type="comment",
        entity_id=str(comment.id),
        before=None,
        after=model_snapshot(comment),
        request=request,
    )
    return comment
