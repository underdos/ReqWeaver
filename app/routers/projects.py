"""API Routes — CRUD projects + document generation + download"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlmodel import Session, select
from typing import List
import zipfile, io

from app.database import get_session
from app.models import (
    Project, Stakeholder, TargetUser, Feature,
    FunctionalRequirement, NonFunctionalRequirement,
    Entity, EntityAttribute, EntityRelationship, SequenceFlow,
)
from app.schemas import ProjectCreate, ProjectUpdate, ProjectSummary, ProjectDetail
from app.services.document_generator import DOC_NAMES, get_doc_filename
from app.services.ai_generator import generate_document as ai_generate_doc
from app.services.ai_generator import generate_all as ai_generate_all

from datetime import datetime, timezone
import uuid

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _new_id():
    return str(uuid.uuid4())


# ─── Helper ─────────────────────────────────────────────

def _project_to_detail(p: Project) -> ProjectDetail:
    return ProjectDetail(
        id=p.id,
        name=p.name,
        description=p.description,
        goals=p.goals,
        business_context=p.business_context,
        success_metrics=p.success_metrics,
        constraints=p.constraints,
        tech_stack=p.tech_stack,
        created_at=p.created_at,
        updated_at=p.updated_at,
        stakeholders=[s.model_dump() for s in (p.stakeholders or [])],
        target_users=[u.model_dump() for u in (p.target_users or [])],
        features=[f.model_dump() for f in (p.features or [])],
        functional_reqs=[r.model_dump() for r in (p.functional_reqs or [])],
        non_functional_reqs=[n.model_dump() for n in (p.non_functional_reqs or [])],
        entities=[e.model_dump() for e in (p.entities or [])],
        relationships=[r.model_dump() for r in (p.relationships or [])],
        sequence_flows=[f.model_dump() for f in (p.sequence_flows or [])],
    )


# ─── CRUD ───────────────────────────────────────────────

@router.post("", response_model=ProjectDetail, status_code=201)
def create_project(data: ProjectCreate, session: Session = Depends(get_session)):
    """Create a new project with all related data."""
    project = Project(
        id=_new_id(),
        name=data.name,
        description=data.description,
        goals=data.goals,
        business_context=data.business_context,
        success_metrics=data.success_metrics,
        constraints=data.constraints,
        tech_stack=data.tech_stack,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session.add(project)
    session.flush()  # get ID

    # Add relations
    for s in data.stakeholders:
        session.add(Stakeholder(id=_new_id(), project_id=project.id, **s.model_dump()))
    for u in data.target_users:
        session.add(TargetUser(id=_new_id(), project_id=project.id, **u.model_dump()))
    for f in data.features:
        session.add(Feature(id=_new_id(), project_id=project.id, **f.model_dump()))
    for r in data.functional_reqs:
        session.add(FunctionalRequirement(id=_new_id(), project_id=project.id, **r.model_dump()))
    for n in data.non_functional_reqs:
        session.add(NonFunctionalRequirement(id=_new_id(), project_id=project.id, **n.model_dump()))
    for e in data.entities:
        entity = Entity(id=_new_id(), project_id=project.id, name=e.name, description=e.description)
        session.add(entity)
        session.flush()
        for attr in e.attributes:
            session.add(EntityAttribute(id=_new_id(), entity_id=entity.id, name=attr.name, type_=attr.type_, is_pk=attr.is_pk, is_fk=attr.is_fk, nullable=attr.nullable, description=attr.description))
    for r in data.relationships:
        session.add(EntityRelationship(id=_new_id(), project_id=project.id, **r.model_dump()))
    for f in data.sequence_flows:
        session.add(SequenceFlow(id=_new_id(), project_id=project.id, **f.model_dump()))

    session.commit()
    session.refresh(project)
    return _project_to_detail(project)


@router.get("", response_model=List[ProjectSummary])
def list_projects(session: Session = Depends(get_session)):
    """List all projects with basic stats."""
    projects = session.exec(select(Project).order_by(Project.updated_at.desc())).all()
    result = []
    for p in projects:
        result.append(ProjectSummary(
            id=p.id,
            name=p.name,
            description=p.description[:200] + "..." if len(p.description or "") > 200 else (p.description or ""),
            created_at=p.created_at,
            updated_at=p.updated_at,
            stats={
                "stakeholders": len(p.stakeholders or []),
                "features": len(p.features or []),
                "functional_reqs": len(p.functional_reqs or []),
                "entities": len(p.entities or []),
            },
        ))
    return result


@router.get("/{project_id}", response_model=ProjectDetail)
def get_project(project_id: str, session: Session = Depends(get_session)):
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return _project_to_detail(project)


@router.patch("/{project_id}", response_model=ProjectDetail)
def update_project(project_id: str, data: ProjectUpdate, session: Session = Depends(get_session)):
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(project, key, value)
    session.add(project)
    session.commit()
    session.refresh(project)
    return _project_to_detail(project)


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str, session: Session = Depends(get_session)):
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    session.delete(project)
    session.commit()


# ─── Document Generation ────────────────────────────────

@router.post("/{project_id}/generate")
def generate_project_docs(
    project_id: str,
    mode: str = Query("auto", regex="^(ai|template|auto)$"),
    session: Session = Depends(get_session),
):
    """Generate all document types for a project. Mode: ai, template, auto."""
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    docs = ai_generate_all(project, mode)
    return {"project_id": project_id, "project_name": project.name, "mode": mode, "documents": docs}


@router.get("/{project_id}/generate/{doc_type}")
def generate_single_doc(
    project_id: str,
    doc_type: str,
    mode: str = Query("auto", regex="^(ai|template|auto)$"),
    session: Session = Depends(get_session),
):
    """Generate a single document type. Mode: ai, template, auto."""
    if doc_type not in DOC_NAMES:
        raise HTTPException(status_code=400, detail=f"Unknown document type. Choose from {list(DOC_NAMES.keys())}")
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    markdown = ai_generate_doc(project, doc_type, mode)
    return {"project_id": project_id, "project_name": project.name, "doc_type": doc_type, "mode": mode, "markdown": markdown}


@router.get("/{project_id}/download/{doc_type}")
def download_doc(
    project_id: str,
    doc_type: str,
    mode: str = Query("auto", regex="^(ai|template|auto)$"),
    session: Session = Depends(get_session),
):
    """Download a single document as .md file. Mode: ai, template, auto."""
    if doc_type not in DOC_NAMES:
        raise HTTPException(status_code=400, detail=f"Unknown document type. Choose from {list(DOC_NAMES.keys())}")
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    markdown = ai_generate_doc(project, doc_type, mode)
    safe_name = project.name.replace(" ", "-").lower()
    filename = f"{safe_name}-{get_doc_filename(doc_type)}.md"
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(
        content=markdown,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{project_id}/download-all")
def download_all(
    project_id: str,
    mode: str = Query("auto", regex="^(ai|template|auto)$"),
    session: Session = Depends(get_session),
):
    """Download all documents as a ZIP file. Mode: ai, template, auto."""
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    docs = ai_generate_all(project, mode)
    safe_name = project.name.replace(" ", "-").lower()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for doc_type, markdown in docs.items():
            filename = f"{safe_name}-{get_doc_filename(doc_type)}.md"
            zf.writestr(filename, markdown)
    buf.seek(0)

    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}-all-docs.zip"'},
    )
