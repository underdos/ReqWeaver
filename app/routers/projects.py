"""API Routes — CRUD projects + document generation (background) + download + history"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlmodel import Session, select, desc
from typing import List
import zipfile, io

from app.database import get_session
from app.models import (
    Project, Stakeholder, TargetUser, Feature,
    FunctionalRequirement, NonFunctionalRequirement,
    Entity, EntityAttribute, EntityRelationship, SequenceFlow,
    DocumentGeneration,
)
from app.schemas import ProjectCreate, ProjectUpdate, ProjectSummary, ProjectDetail
from app.services.document_generator import DOC_NAMES, get_doc_filename
from app.services.background_generator import run_generation
from app.services.ai_assist import suggest

from datetime import datetime, timezone
import uuid

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _new_id():
    return str(uuid.uuid4())


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


def _get_next_version(session: Session, project_id: str, doc_type: str) -> int:
    existing = session.exec(
        select(DocumentGeneration)
        .where(DocumentGeneration.project_id == project_id)
        .where(DocumentGeneration.doc_type == doc_type)
        .order_by(desc(DocumentGeneration.version))
        .limit(1)
    ).first()
    return (existing.version + 1) if existing else 1


# ─── CRUD ───────────────────────────────────────────────

@router.post("", response_model=ProjectDetail, status_code=201)
def create_project(data: ProjectCreate, session: Session = Depends(get_session)):
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
    session.flush()

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
    projects = session.exec(select(Project).order_by(Project.updated_at.desc())).all()
    result = []
    for p in projects:
        # Get latest generation status per doc type
        gen_statuses = {}
        for dt in ["prd", "fsd", "srs", "erd", "sequence"]:
            latest = session.exec(
                select(DocumentGeneration)
                .where(DocumentGeneration.project_id == p.id)
                .where(DocumentGeneration.doc_type == dt)
                .where(DocumentGeneration.status == "completed")
                .order_by(desc(DocumentGeneration.version))
                .limit(1)
            ).first()
            gen_statuses[dt] = latest.version if latest else 0

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
            generation_versions=gen_statuses,
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


# ─── Document Generation (Background) ───────────────────

@router.post("/{project_id}/generate/{doc_type}")
def trigger_generate_single(
    project_id: str,
    doc_type: str,
    mode: str = Query("auto", regex="^(ai|template|auto)$"),
    background_tasks: BackgroundTasks = None,
    session: Session = Depends(get_session),
):
    """Trigger background generation of a single document type.
    Returns immediately with generation_id — poll /generations/{id}/status for completion."""
    if doc_type not in DOC_NAMES:
        raise HTTPException(status_code=400, detail=f"Unknown document type. Choose from {list(DOC_NAMES.keys())}")
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    version = _get_next_version(session, project_id, doc_type)
    gen = DocumentGeneration(
        id=_new_id(),
        project_id=project_id,
        doc_type=doc_type,
        mode=mode,
        version=version,
        status="pending",
        created_at=datetime.now(timezone.utc),
    )
    session.add(gen)
    session.commit()
    session.refresh(gen)

    if background_tasks:
        background_tasks.add_task(run_generation, gen.id)
    else:
        run_generation(gen.id)

    return {
        "generation_id": gen.id,
        "project_id": project_id,
        "doc_type": doc_type,
        "version": version,
        "mode": mode,
        "status": "pending",
    }


@router.post("/{project_id}/generate")
def trigger_generate_all(
    project_id: str,
    mode: str = Query("auto", regex="^(ai|template|auto)$"),
    background_tasks: BackgroundTasks = None,
    session: Session = Depends(get_session),
):
    """Trigger background generation of ALL document types.
    Returns immediately with generation_ids — poll /generations/{id}/status for completion."""
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    generations = {}
    for doc_type in ["prd", "fsd", "srs", "erd", "sequence"]:
        version = _get_next_version(session, project_id, doc_type)
        gen = DocumentGeneration(
            id=_new_id(),
            project_id=project_id,
            doc_type=doc_type,
            mode=mode,
            version=version,
            status="pending",
            created_at=datetime.now(timezone.utc),
        )
        session.add(gen)
        session.commit()
        session.refresh(gen)

        if background_tasks:
            background_tasks.add_task(run_generation, gen.id)
        else:
            run_generation(gen.id)

        generations[doc_type] = {
            "generation_id": gen.id,
            "version": version,
            "status": "pending",
        }

    return {
        "project_id": project_id,
        "mode": mode,
        "generations": generations,
    }


# ─── Generation History & Poll ──────────────────────────

@router.get("/{project_id}/generations")
def list_generations(
    project_id: str,
    doc_type: str = Query(None, regex="^(prd|fsd|srs|erd|sequence)$"),
    limit: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_session),
):
    """List generation history for a project. Optionally filter by doc_type."""
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    query = select(DocumentGeneration).where(DocumentGeneration.project_id == project_id)
    if doc_type:
        query = query.where(DocumentGeneration.doc_type == doc_type)
    query = query.order_by(desc(DocumentGeneration.created_at)).limit(limit)

    gens = session.exec(query).all()
    return [
        {
            "id": g.id,
            "doc_type": g.doc_type,
            "version": g.version,
            "mode": g.mode,
            "status": g.status,
            "error": g.error,
            "created_at": g.created_at,
            "completed_at": g.completed_at,
        }
        for g in gens
    ]


@router.get("/{project_id}/generations/{gen_id}")
def get_generation(
    project_id: str,
    gen_id: str,
    session: Session = Depends(get_session),
):
    """Get full generation detail including content."""
    gen = session.get(DocumentGeneration, gen_id)
    if not gen or gen.project_id != project_id:
        raise HTTPException(status_code=404, detail="Generation not found")
    return {
        "id": gen.id,
        "project_id": gen.project_id,
        "doc_type": gen.doc_type,
        "version": gen.version,
        "mode": gen.mode,
        "status": gen.status,
        "error": gen.error,
        "content": gen.content,
        "created_at": gen.created_at,
        "completed_at": gen.completed_at,
    }


@router.get("/{project_id}/generations/{gen_id}/status")
def poll_generation_status(
    project_id: str,
    gen_id: str,
    session: Session = Depends(get_session),
):
    """Lightweight status poll for a generation job."""
    gen = session.get(DocumentGeneration, gen_id)
    if not gen or gen.project_id != project_id:
        raise HTTPException(status_code=404, detail="Generation not found")
    return {
        "id": gen.id,
        "doc_type": gen.doc_type,
        "version": gen.version,
        "status": gen.status,
        "error": gen.error,
        "completed_at": gen.completed_at,
    }


# ─── Download ───────────────────────────────────────────

@router.get("/{project_id}/download/{doc_type}")
def download_latest_doc(
    project_id: str,
    doc_type: str,
    session: Session = Depends(get_session),
):
    """Download the latest COMPLETED version of a document type as .md."""
    if doc_type not in DOC_NAMES:
        raise HTTPException(status_code=400, detail=f"Unknown document type. Choose from {list(DOC_NAMES.keys())}")
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    gen = session.exec(
        select(DocumentGeneration)
        .where(DocumentGeneration.project_id == project_id)
        .where(DocumentGeneration.doc_type == doc_type)
        .where(DocumentGeneration.status == "completed")
        .order_by(desc(DocumentGeneration.version))
        .limit(1)
    ).first()

    if not gen:
        raise HTTPException(status_code=404, detail=f"No completed {doc_type.upper()} generation found. Generate it first.")

    safe_name = project.name.replace(" ", "-").lower()
    filename = f"{safe_name}-{get_doc_filename(doc_type)}-v{gen.version}.md"
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(
        content=gen.content,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{project_id}/download/gen/{gen_id}")
def download_generation(
    project_id: str,
    gen_id: str,
    session: Session = Depends(get_session),
):
    """Download a specific generation by ID."""
    gen = session.get(DocumentGeneration, gen_id)
    if not gen or gen.project_id != project_id:
        raise HTTPException(status_code=404, detail="Generation not found")
    if gen.status != "completed":
        raise HTTPException(status_code=400, detail=f"Generation is {gen.status}, not completed yet.")

    project = session.get(Project, project_id)
    safe_name = project.name.replace(" ", "-").lower()
    filename = f"{safe_name}-{get_doc_filename(gen.doc_type)}-v{gen.version}.md"
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(
        content=gen.content,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─── AI Assist ──────────────────────────────────────────

ASSIST_STEPS = {
    "features": "Features — membantu mendefine feature dari project info, stakeholder, target user",
    "func_reqs": "Functional Requirements — membantu mendefine FR dari project info, stakeholder, target user, features",
    "nfr": "Non-Functional Requirements — membantu mendefine NFR dari standard industri",
    "data_model": "Data Model — membantu mendefine entity & relationships dari data yang sudah diisi",
    "system_interactions": "System Interactions — membantu mendefine sequence flow dari data yang sudah diisi",
}


@router.post("/{project_id}/ai-assist/{step}")
def ai_assist(
    project_id: str,
    step: str,
    session: Session = Depends(get_session),
):
    """Generate AI suggestions for a requirement input step."""
    if step not in ASSIST_STEPS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown assist step: {step}. Choose from {list(ASSIST_STEPS.keys())}",
        )

    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    result = suggest(project, step)
    if result is None:
        raise HTTPException(status_code=500, detail="AI returned empty response")
    if "error" in result:
        raise HTTPException(status_code=502, detail=result["error"])

    return result


@router.get("/{project_id}/download-all")
def download_all_completed(
    project_id: str,
    session: Session = Depends(get_session),
):
    """Download all latest completed documents as ZIP."""
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    safe_name = project.name.replace(" ", "-").lower()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for doc_type in ["prd", "fsd", "srs", "erd", "sequence"]:
            gen = session.exec(
                select(DocumentGeneration)
                .where(DocumentGeneration.project_id == project_id)
                .where(DocumentGeneration.doc_type == doc_type)
                .where(DocumentGeneration.status == "completed")
                .order_by(desc(DocumentGeneration.version))
                .limit(1)
            ).first()
            if gen and gen.content:
                filename = f"{safe_name}-{get_doc_filename(doc_type)}-v{gen.version}.md"
                zf.writestr(filename, gen.content)
    buf.seek(0)

    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}-all-docs.zip"'},
    )
