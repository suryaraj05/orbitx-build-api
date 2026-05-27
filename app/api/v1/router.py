from fastapi import APIRouter

from app.api.v1.endpoints import (
    articles,
    auth,
    audit_logs,
    categories,
    comments,
    newsletter,
    projects,
    resources,
    search,
    themes,
    videos,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(themes.router)
api_router.include_router(projects.router)
api_router.include_router(articles.router)
api_router.include_router(categories.router)
api_router.include_router(videos.router)
api_router.include_router(resources.router)
api_router.include_router(comments.router)
api_router.include_router(search.router)
api_router.include_router(newsletter.router)
api_router.include_router(audit_logs.router)
