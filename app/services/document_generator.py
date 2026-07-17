"""Document Generator Service — renders Jinja2 templates → Markdown"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from app.models import Project

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
env.globals["now"] = lambda: datetime.now()

DOC_NAMES = {
    "prd": "Product Requirements Document (PRD)",
    "fsd": "Functional Specification Document (FSD)",
    "srs": "Software Requirements Specification (SRS)",
    "erd": "Entity Relationship Diagram (ERD)",
    "sequence": "Sequence Diagram",
}

DOC_FILENAMES = {
    "prd": "PRD",
    "fsd": "FSD",
    "srs": "SRS",
    "erd": "ERD",
    "sequence": "Sequence-Diagram",
}


def _collect_context(project: Project) -> dict:
    """Flatten project + relations for template rendering."""
    return {
        "project": project,
        "stakeholders": project.stakeholders or [],
        "target_users": project.target_users or [],
        "features": project.features or [],
        "functional_reqs": project.functional_reqs or [],
        "non_functional_reqs": project.non_functional_reqs or [],
        "entities": project.entities or [],
        "relationships": project.relationships or [],
        "sequence_flows": project.sequence_flows or [],
    }


def generate_document(project: Project, doc_type: str) -> str:
    """Render a single document type → Markdown string."""
    if doc_type not in DOC_NAMES:
        raise ValueError(f"Unknown document type: {doc_type}. Choose from {list(DOC_NAMES.keys())}")

    template = env.get_template(f"{doc_type}.md.j2")
    context = _collect_context(project)
    return template.render(**context)


def generate_all(project: Project) -> dict[str, str]:
    """Generate all document types → dict[doc_type, markdown]."""
    return {dt: generate_document(project, dt) for dt in DOC_NAMES}


def get_doc_title(doc_type: str) -> str:
    return DOC_NAMES.get(doc_type, doc_type)


def get_doc_filename(doc_type: str) -> str:
    return DOC_FILENAMES.get(doc_type, doc_type)
