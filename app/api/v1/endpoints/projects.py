import re

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.core.deps import AdminUser, DbSession, EditorUser
from app.models.project import (
    Project,
    ProjectArchitectureNode,
    ProjectFeature,
    ProjectTechStack,
    ProjectStatus,
    ProjectVisibility,
)
from app.schemas.common import MessageResponse
from app.schemas.project import (
    ProjectArchitectureNodeCreate,
    ProjectArchitectureNodeRead,
    ProjectCreate,
    ProjectDetailResponse,
    ProjectFeatureCreate,
    ProjectFeatureRead,
    ProjectListResponse,
    ProjectRead,
    ProjectTechStackCreate,
    ProjectTechStackRead,
    ProjectUpdate,
)
from app.utils import apply_updates
from app.audit import model_snapshot, write_audit_log

router = APIRouter(prefix="/projects", tags=["projects"])

MERMAID_RE = re.compile(r"^\s*graph\s+(TD|LR|TB)\b", re.IGNORECASE | re.MULTILINE)


def is_mermaid_graph(source: str) -> bool:
    return bool(MERMAID_RE.search(source or ""))


def synthesize_mermaid_from_architecture_nodes(nodes: list[ProjectArchitectureNode]) -> str:
    lines = ["graph TD"]
    for n in nodes:
        # Mermaid label parsing is brittle; strip characters that commonly break node syntax.
        safe = re.sub(r"[\[\]{}()<>]", "", n.label or "").replace("\n", " ").strip()
        if not safe:
            safe = f"Node {n.id}"
        node_id = f"N{n.id}"
        lines.append(f"  {node_id}[{safe}]")
    return "\n".join(lines)


def normalize_project_for_response(project: Project) -> None:
    # Architecture mermaid: prefer explicit architecture_mermaid; fallback to overview if it contains mermaid.
    if not project.architecture_mermaid:
        if project.architecture_overview and is_mermaid_graph(project.architecture_overview):
            project.architecture_mermaid = project.architecture_overview
        elif project.architecture_nodes:
            project.architecture_mermaid = synthesize_mermaid_from_architecture_nodes(project.architecture_nodes)

    # Tech stack pills: use tech_stack JSON if present; fallback to legacy relation.
    if not project.tech_stack:
        if project.tech_stack_rows:
            project.tech_stack = [s.name for s in project.tech_stack_rows]
        else:
            project.tech_stack = []

    # Core features grid: use core_features JSON if present; fallback to legacy feature relation.
    if not project.core_features:
        if project.features:
            project.core_features = [
                {"title": f.title, "description": f.description} for f in project.features
            ]
        else:
            project.core_features = []

    # Lessons/roadmap: schema expects arrays; leave empty when not provided.
    if project.lessons_learned is None:
        project.lessons_learned = []
    if project.roadmap is None:
        project.roadmap = []

    # featured_article_ids fallback for legacy rows
    if project.featured_article_ids is None or project.featured_article_ids == []:
        if project.featured_article_id is not None:
            project.featured_article_ids = [project.featured_article_id]
        else:
            project.featured_article_ids = []


@router.get("", response_model=ProjectListResponse)
def list_projects(
    db: DbSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: ProjectStatus | None = Query(None, alias="status"),
    is_featured: bool | None = Query(None, alias="is_featured"),
    featured: bool | None = Query(None, alias="featured"),
    visibility: ProjectVisibility | None = None,
    theme_id: int | None = Query(None, alias="theme_id"),
):
    query = select(Project)
    query = query.options(
        joinedload(Project.features),
        joinedload(Project.tech_stack_rows),
        joinedload(Project.architecture_nodes),
    )

    if status:
        query = query.where(Project.status == status)

    effective_featured = is_featured if is_featured is not None else featured
    if effective_featured is not None:
        query = query.where(Project.is_featured == effective_featured)

    # Default for non-admins: only public. (This endpoint is public; we enforce a safe default.)
    if visibility is not None:
        query = query.where(Project.visibility == visibility)
    else:
        query = query.where(Project.visibility == ProjectVisibility.PUBLIC)

    if theme_id is not None:
        query = query.where(Project.theme_id == theme_id)

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    stmt = (
        query.order_by(Project.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    # joinedload() on collection relationships requires unique() to avoid duplicate parent rows.
    items = list(db.execute(stmt).unique().scalars().all())
    for p in items:
        normalize_project_for_response(p)

    return ProjectListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{slug}", response_model=ProjectDetailResponse)
def get_project(slug: str, db: DbSession):
    stmt = (
        select(Project)
        .options(
            joinedload(Project.features),
            joinedload(Project.tech_stack_rows),
            joinedload(Project.architecture_nodes),
        )
        .where(Project.slug == slug)
    )
    project = db.execute(stmt).unique().scalars().one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    normalize_project_for_response(project)
    return project


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, db: DbSession, user: EditorUser, request: Request):
    project = Project(**payload.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)
    write_audit_log(
        db,
        actor=user,
        action="create",
        entity_type="project",
        entity_id=str(project.id),
        before=None,
        after=model_snapshot(project),
        request=request,
    )
    return project


@router.put("/{slug}", response_model=ProjectRead)
def put_project(slug: str, payload: ProjectCreate, db: DbSession, user: EditorUser, request: Request):
    project = db.scalar(select(Project).where(Project.slug == slug))
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    before = model_snapshot(project)
    data = payload.model_dump()
    for key, value in data.items():
        setattr(project, key, value)

    db.commit()
    db.refresh(project)
    normalize_project_for_response(project)
    write_audit_log(
        db,
        actor=user,
        action="update",
        entity_type="project",
        entity_id=str(project.id),
        before=before,
        after=model_snapshot(project),
        request=request,
    )
    return project


@router.patch("/{slug}", response_model=ProjectRead)
def patch_project(slug: str, payload: ProjectUpdate, db: DbSession, user: EditorUser, request: Request):
    project = db.scalar(select(Project).where(Project.slug == slug))
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    before = model_snapshot(project)
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(project, key, value)

    db.commit()
    db.refresh(project)
    normalize_project_for_response(project)
    write_audit_log(
        db,
        actor=user,
        action="update",
        entity_type="project",
        entity_id=str(project.id),
        before=before,
        after=model_snapshot(project),
        request=request,
    )
    return project


@router.delete("/{slug}", response_model=MessageResponse)
def delete_project_by_slug(slug: str, db: DbSession, user: AdminUser, request: Request):
    project = db.scalar(select(Project).where(Project.slug == slug))
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    before = model_snapshot(project)
    db.delete(project)
    db.commit()
    write_audit_log(
        db,
        actor=user,
        action="delete",
        entity_type="project",
        entity_id=str(project.id),
        before=before,
        after=None,
        request=request,
    )
    return MessageResponse(message="Project deleted")


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(project_id: int, payload: ProjectUpdate, db: DbSession, user: EditorUser, request: Request):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    before = model_snapshot(project)
    apply_updates(project, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(project)
    normalize_project_for_response(project)
    write_audit_log(
        db,
        actor=user,
        action="update",
        entity_type="project",
        entity_id=str(project.id),
        before=before,
        after=model_snapshot(project),
        request=request,
    )
    return project


@router.delete("/{project_id}", response_model=MessageResponse)
def delete_project(project_id: int, db: DbSession, user: AdminUser, request: Request):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    before = model_snapshot(project)
    db.delete(project)
    db.commit()
    write_audit_log(
        db,
        actor=user,
        action="delete",
        entity_type="project",
        entity_id=str(project_id),
        before=before,
        after=None,
        request=request,
    )
    return MessageResponse(message="Project deleted")


# --- Features ---


@router.post("/{project_id}/features", response_model=ProjectFeatureRead, status_code=201)
def add_feature(project_id: int, payload: ProjectFeatureCreate, db: DbSession, user: EditorUser, request: Request):
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    feature = ProjectFeature(project_id=project_id, **payload.model_dump())
    db.add(feature)
    db.commit()
    db.refresh(feature)
    write_audit_log(
        db,
        actor=user,
        action="create",
        entity_type="project_feature",
        entity_id=str(feature.id),
        before=None,
        after=model_snapshot(feature),
        request=request,
    )
    return feature


@router.patch("/project-features/{feature_id}", response_model=ProjectFeatureRead)
def update_feature(feature_id: int, payload: ProjectFeatureCreate, db: DbSession, user: EditorUser, request: Request):
    feature = db.get(ProjectFeature, feature_id)
    if feature is None:
        raise HTTPException(status_code=404, detail="Feature not found")
    before = model_snapshot(feature)
    apply_updates(feature, payload.model_dump())
    db.commit()
    db.refresh(feature)
    write_audit_log(
        db,
        actor=user,
        action="update",
        entity_type="project_feature",
        entity_id=str(feature.id),
        before=before,
        after=model_snapshot(feature),
        request=request,
    )
    return feature


@router.delete("/project-features/{feature_id}", response_model=MessageResponse)
def delete_feature(feature_id: int, db: DbSession, user: EditorUser, request: Request):
    feature = db.get(ProjectFeature, feature_id)
    if feature is None:
        raise HTTPException(status_code=404, detail="Feature not found")
    before = model_snapshot(feature)
    db.delete(feature)
    db.commit()
    write_audit_log(
        db,
        actor=user,
        action="delete",
        entity_type="project_feature",
        entity_id=str(feature_id),
        before=before,
        after=None,
        request=request,
    )
    return MessageResponse(message="Feature deleted")


# --- Tech stack ---


@router.post("/{project_id}/stack", response_model=ProjectTechStackRead, status_code=201)
def add_stack_item(project_id: int, payload: ProjectTechStackCreate, db: DbSession, user: EditorUser, request: Request):
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    item = ProjectTechStack(project_id=project_id, **payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    write_audit_log(
        db,
        actor=user,
        action="create",
        entity_type="project_stack_item",
        entity_id=str(item.id),
        before=None,
        after=model_snapshot(item),
        request=request,
    )
    return item


@router.patch("/project-stack/{stack_id}", response_model=ProjectTechStackRead)
def update_stack_item(stack_id: int, payload: ProjectTechStackCreate, db: DbSession, user: EditorUser, request: Request):
    item = db.get(ProjectTechStack, stack_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Stack item not found")
    before = model_snapshot(item)
    apply_updates(item, payload.model_dump())
    db.commit()
    db.refresh(item)
    write_audit_log(
        db,
        actor=user,
        action="update",
        entity_type="project_stack_item",
        entity_id=str(item.id),
        before=before,
        after=model_snapshot(item),
        request=request,
    )
    return item


@router.delete("/project-stack/{stack_id}", response_model=MessageResponse)
def delete_stack_item(stack_id: int, db: DbSession, user: EditorUser, request: Request):
    item = db.get(ProjectTechStack, stack_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Stack item not found")
    before = model_snapshot(item)
    db.delete(item)
    db.commit()
    write_audit_log(
        db,
        actor=user,
        action="delete",
        entity_type="project_stack_item",
        entity_id=str(stack_id),
        before=before,
        after=None,
        request=request,
    )
    return MessageResponse(message="Stack item deleted")


# --- Architecture ---


@router.get("/{project_id}/architecture", response_model=list[ProjectArchitectureNodeRead])
def get_architecture(project_id: int, db: DbSession):
    return list(
        db.scalars(
            select(ProjectArchitectureNode)
            .where(ProjectArchitectureNode.project_id == project_id)
            .order_by(ProjectArchitectureNode.id)
        ).all()
    )


@router.post("/{project_id}/architecture", response_model=ProjectArchitectureNodeRead, status_code=201)
def add_architecture_node(
    project_id: int, payload: ProjectArchitectureNodeCreate, db: DbSession, _: EditorUser
):
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    node = ProjectArchitectureNode(project_id=project_id, **payload.model_dump())
    db.add(node)
    db.commit()
    db.refresh(node)
    return node
