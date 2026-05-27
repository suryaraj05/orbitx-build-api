from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import joinedload

from app.core.deps import AdminUser, DbSession, EditorUser
from app.models.article import Article, ArticleSection, ContentVisibility
from app.schemas.article import (
    ArticleCreate,
    ArticleDetailResponse,
    ArticleListResponse,
    ArticleRead,
    ArticleSectionCreate,
    ArticleSectionRead,
    ArticleUpdate,
)
from app.schemas.common import MessageResponse
from app.utils import apply_updates
from app.utils.audit import model_snapshot, write_audit_log

router = APIRouter(prefix="/articles", tags=["articles"])


@router.get("", response_model=ArticleListResponse)
def list_articles(
    db: DbSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category_id: int | None = None,
    featured: bool | None = None,
    search: str | None = None,
    published_only: bool = True,
):
    query = select(Article)
    if published_only:
        query = query.where(Article.published.is_(True))
        query = query.where(Article.visibility == ContentVisibility.PUBLIC)
    if category_id:
        query = query.where(Article.category_id == category_id)
    if featured is not None:
        query = query.where(Article.featured == featured)
    if search:
        pattern = f"%{search}%"
        query = query.where(
            or_(
                Article.title.ilike(pattern),
                Article.excerpt.ilike(pattern),
                Article.content_markdown.ilike(pattern),
            )
        )

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = list(
        db.scalars(
            query.order_by(Article.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return ArticleListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{slug}", response_model=ArticleDetailResponse)
def get_article(slug: str, db: DbSession):
    article = db.scalar(
        select(Article)
        .options(
            joinedload(Article.sections),
            joinedload(Article.author),
            joinedload(Article.theme),
            joinedload(Article.resources),
            joinedload(Article.videos),
        )
        .where(Article.slug == slug)
    )
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")

    related_query = select(Article).where(
        Article.id != article.id,
        Article.published.is_(True),
        Article.visibility == ContentVisibility.PUBLIC,
    )
    if article.category_id:
        related_query = related_query.where(Article.category_id == article.category_id)
    related = list(db.scalars(related_query.limit(4)).all())

    return ArticleDetailResponse(
        **ArticleRead.model_validate(article).model_dump(),
        sections=[ArticleSectionRead.model_validate(s) for s in article.sections],
        author=article.author,
        theme=article.theme,
        resources=article.resources,
        videos=article.videos,
        related_articles=related,
    )


@router.post("", response_model=ArticleRead, status_code=status.HTTP_201_CREATED)
def create_article(payload: ArticleCreate, db: DbSession, user: EditorUser, request: Request):
    data = payload.model_dump()
    if data.get("author_id") is None:
        data["author_id"] = user.id
    article = Article(**data)
    db.add(article)
    db.commit()
    db.refresh(article)
    write_audit_log(
        db,
        actor=user,
        action="create",
        entity_type="article",
        entity_id=str(article.id),
        before=None,
        after=model_snapshot(article),
        request=request,
    )
    return article


@router.patch("/{article_id}", response_model=ArticleRead)
def update_article(article_id: int, payload: ArticleUpdate, db: DbSession, user: EditorUser, request: Request):
    article = db.get(Article, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    before = model_snapshot(article)
    apply_updates(article, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(article)
    write_audit_log(
        db,
        actor=user,
        action="update",
        entity_type="article",
        entity_id=str(article.id),
        before=before,
        after=model_snapshot(article),
        request=request,
    )
    return article


@router.delete("/{article_id}", response_model=MessageResponse)
def delete_article(article_id: int, db: DbSession, user: AdminUser, request: Request):
    article = db.get(Article, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    before = model_snapshot(article)
    db.delete(article)
    db.commit()
    write_audit_log(
        db,
        actor=user,
        action="delete",
        entity_type="article",
        entity_id=str(article_id),
        before=before,
        after=None,
        request=request,
    )
    return MessageResponse(message="Article deleted")


@router.post("/{article_id}/sections", response_model=ArticleSectionRead, status_code=201)
def add_section(article_id: int, payload: ArticleSectionCreate, db: DbSession, user: EditorUser, request: Request):
    if db.get(Article, article_id) is None:
        raise HTTPException(status_code=404, detail="Article not found")
    section = ArticleSection(article_id=article_id, **payload.model_dump())
    db.add(section)
    db.commit()
    db.refresh(section)
    write_audit_log(
        db,
        actor=user,
        action="create",
        entity_type="article_section",
        entity_id=str(section.id),
        before=None,
        after=model_snapshot(section),
        request=request,
    )
    return section


@router.patch("/article-sections/{section_id}", response_model=ArticleSectionRead)
def update_section(section_id: int, payload: ArticleSectionCreate, db: DbSession, user: EditorUser, request: Request):
    section = db.get(ArticleSection, section_id)
    if section is None:
        raise HTTPException(status_code=404, detail="Section not found")
    before = model_snapshot(section)
    apply_updates(section, payload.model_dump())
    db.commit()
    db.refresh(section)
    write_audit_log(
        db,
        actor=user,
        action="update",
        entity_type="article_section",
        entity_id=str(section.id),
        before=before,
        after=model_snapshot(section),
        request=request,
    )
    return section


@router.delete("/article-sections/{section_id}", response_model=MessageResponse)
def delete_section(section_id: int, db: DbSession, user: EditorUser, request: Request):
    section = db.get(ArticleSection, section_id)
    if section is None:
        raise HTTPException(status_code=404, detail="Section not found")
    before = model_snapshot(section)
    db.delete(section)
    db.commit()
    write_audit_log(
        db,
        actor=user,
        action="delete",
        entity_type="article_section",
        entity_id=str(section_id),
        before=before,
        after=None,
        request=request,
    )
    return MessageResponse(message="Section deleted")
