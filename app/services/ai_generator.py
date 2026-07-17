"""
AI Document Generator — generates PRD/FSD/SRS/ERD/Sequence documents
using OpenAI's API with context-rich prompting for 80-90% quality output.
Falls back to Jinja2 templates if AI is unavailable.
"""
from __future__ import annotations
import json
from datetime import datetime
from typing import Optional
from openai import OpenAI

from app.config import get_settings
from app.models import Project
from app.services.document_generator import generate_document as template_generate


# ─── System prompts per document type ─────────────────────

SYSTEM_PROMPTS = {
    "prd": (
        "Kamu adalah Principal Product Manager berpengalaman 15+ tahun. "
        "Buatkan **Product Requirements Document (PRD)** yang sangat komprehensif dalam Bahasa Indonesia "
        "berdasarkan data project yang diberikan.\n\n"
        "FORMAT: Gunakan Markdown dengan struktur berikut:\n"
        "# Product Requirements Document (PRD)\n\n"
        "## 1. Document Control\n"
        "| Field | Value |\n"
        "|-------|-------|\n"
        "| Project Name | ... |\n"
        "| Document Version | 1.0 |\n"
        "| Date | ... |\n\n"
        "## 2. Executive Summary\n"
        "*(Paragraf ringkasan eksekutif — latar belakang, tujuan, nilai bisnis)*\n\n"
        "## 3. Business Objectives\n"
        "| Objective | Metric | Target |\n"
        "|-----------|--------|-------|\n"
        "| ... | ... | ... |\n\n"
        "## 4. Problem Statement\n\n"
        "## 5. Target Audience\n"
        "- Persona 1: ...\n"
        "- Persona 2: ...\n\n"
        "## 6. User Stories\n"
        "- As a [user], I want to [action] so that [benefit]\n\n"
        "## 7. Functional Requirements\n"
        "| ID | Module | Description | Priority |\n"
        "|----|--------|-------------|----------|\n\n"
        "## 8. Non-Functional Requirements\n"
        "| Category | Requirement | Metric |\n"
        "|----------|-------------|--------|\n\n"
        "## 9. Success Metrics & KPIs\n\n"
        "## 10. Constraints & Assumptions\n\n"
        "## 11. Timeline & Milestones (Recommended)\n\n"
        "## 12. Risks & Mitigation\n\n"
        "JANGAN gunakan data placeholder/template — gunakan data real dari project. "
        "Jika ada informasi yang kurang, buatlah asumsi yang logis dan realistis berdasarkan konteks project. "
        "Tandai asumsi dengan *(asumsi)*. "
        "Output harus siap pakai 80-90% — minimal editing.\n"
    ),
    "fsd": (
        "Kamu adalah Technical Lead / System Architect berpengalaman. "
        "Buatkan **Functional Specification Document (FSD)** yang detail dalam Bahasa Indonesia "
        "berdasarkan data project.\n\n"
        "FORMAT Markdown:\n"
        "# Functional Specification Document (FSD)\n\n"
        "## 1. Document Control\n\n"
        "## 2. System Overview\n\n"
        "## 3. Functional Architecture\n"
        "*(Gambaran arsitektur fungsional — diagram alur fitur)*\n\n"
        "## 4. Detailed Functional Specifications\n"
        "### 4.1 [Modul/Fitur 1]\n"
        "| ID | Deskripsi | Input | Proses | Output |\n"
        "|----|-----------|-------|--------|-------|\n"
        "| ... | ... | ... | ... | ... |\n\n"
        "### 4.2 [Modul/Fitur 2]\n"
        "*(dan seterusnya untuk setiap modul/fitur)*\n\n"
        "## 5. Business Rules\n"
        "- Rule 1: ...\n\n"
        "## 6. User Interface Specifications\n"
        "*(Deskripsi screen/flow untuk setiap fitur utama)*\n\n"
        "## 7. Data Dictionary\n"
        "| Entity | Field | Type | Description |\n"
        "|--------|-------|------|-------------|\n\n"
        "## 8. Error Handling\n\n"
        "## 9. Integration Points\n\n"
        "Semua konten harus konkret, berdasarkan data project. Kembangkan dengan asumsi logis bila perlu. "
        "Tandai asumsi dengan *(asumsi)*.\n"
    ),
    "srs": (
        "Kamu adalah System Analyst / Requirements Engineer berpengalaman. "
        "Buatkan **Software Requirements Specification (SRS)** yang detail dan formal dalam Bahasa Indonesia "
        "berdasarkan standar IEEE 830.\n\n"
        "FORMAT Markdown:\n"
        "# Software Requirements Specification (SRS)\n\n"
        "## 1. Introduction\n"
        "### 1.1 Purpose\n"
        "### 1.2 Document Conventions\n"
        "### 1.3 Intended Audience\n"
        "### 1.4 Scope\n"
        "### 1.5 References\n\n"
        "## 2. General Description\n"
        "### 2.1 Product Perspective\n"
        "### 2.2 Product Functions\n"
        "### 2.3 User Characteristics\n"
        "### 2.4 Assumptions & Dependencies\n\n"
        "## 3. Functional Requirements\n"
        "### 3.1 [Module/Feature]\n"
        "| ID | Title | Description | Actor | Priority |\n"
        "|----|-------|-------------|-------|----------|\n"
        "*(Detail use case untuk setiap FR — precondition, postcondition, main flow, alternate flow)*\n\n"
        "## 4. External Interface Requirements\n"
        "### 4.1 User Interfaces\n"
        "### 4.2 Hardware Interfaces\n"
        "### 4.3 Software Interfaces\n"
        "### 4.4 Communication Interfaces\n\n"
        "## 5. Non-Functional Requirements\n"
        "| Category | Requirement | Metric | Priority |\n"
        "|----------|-------------|--------|----------|\n\n"
        "## 6. Data Model & Relationships\n\n"
        "Use case format per requirement:\n"
        "- **UC-ID**: [Title]\n"
        "  - **Actor**: ...\n"
        "  - **Precondition**: ...\n"
        "  - **Postcondition**: ...\n"
        "  - **Main Flow**: 1. ... 2. ... 3. ...\n"
        "  - **Alternate Flow**: ...\n\n"
        "Gunakan data real. Kembangkan dengan asumsi teknis yang realistis. "
        "Tandai asumsi.\n"
    ),
    "erd": (
        "Kamu adalah Data Architect / Database Designer berpengalaman. "
        "Buatkan **Entity Relationship Diagram (ERD)** documentation dalam Bahasa Indonesia "
        "berdasarkan data model project.\n\n"
        "FORMAT Markdown:\n"
        "# Entity Relationship Diagram (ERD)\n\n"
        "## 1. Document Control\n\n"
        "## 2. Entity Overview\n"
        "*(Gambaran umum entity dalam sistem)*\n\n"
        "## 3. Entity Definitions\n"
        "### Entity: [Nama Entity]\n"
        "| Attribute | Type | PK | FK | Nullable | Description |\n"
        "|-----------|------|----|----|----------|-------------|\n"
        "*(detail untuk setiap entity)*\n\n"
        "## 4. Relationship Summary\n"
        "| Source | Type | Target | Description |\n"
        "|--------|------|--------|-------------|\n\n"
        "## 5. Entity Relationship Diagram\n"
        "```mermaid\nerDiagram\n"
        "    [Entity1] ||--o{ [Entity2] : \"has\"\n"
        "    ...\n"
        "```\n\n"
        "## 6. Cardinality & Business Rules\n\n"
        "Jika ada entity yang belum lengkap di data project, "
        "kembangkan dengan asumsi yang logis untuk mencapai completeness 80-90%. "
        "Tandai asumsi dengan *(asumsi)*.\n"
    ),
    "sequence": (
        "Kamu adalah System Architect berpengalaman. "
        "Buatkan dokumentasi **Sequence Diagram** dalam Bahasa Indonesia "
        "yang menggambarkan interaksi sistem secara detail.\n\n"
        "FORMAT Markdown:\n"
        "# Sequence Diagrams\n\n"
        "## 1. Document Control\n\n"
        "## 2. System Actors\n"
        "*(Daftar actor yang terlibat)*\n\n"
        "## 3. Sequence Flows\n\n"
        "### 3.1 [Nama Flow 1]\n\n"
        "```mermaid\n"
        "sequenceDiagram\n"
        "    participant Actor1\n"
        "    participant System\n"
        "    participant Component\n"
        "    Actor1->>System: Action\n"
        "    System->>Component: Process\n"
        "    Component-->>System: Response\n"
        "    System-->>Actor1: Result\n"
        "```\n\n"
        "*Deskripsi alur:*\n"
        "1. Langkah 1\n"
        "2. Langkah 2\n\n"
        "### 3.2 [Nama Flow 2]\n"
        "*(dan seterusnya)*\n\n"
        "## 4. Alternative Flows & Error Scenarios\n\n"
        "Kembangkan flow yang komprehensif — happy path, alternatif, dan error scenario. "
        "Gunakan data real dari project. Tandai asumsi dengan *(asumsi)*.\n"
    ),
}


def _build_context(project: Project) -> str:
    """Build structured context from project data for AI prompt."""
    parts = []
    
    # Basic info
    parts.append(f"## Project: {project.name}")
    if project.description:
        parts.append(f"**Description:** {project.description}")
    if project.goals:
        parts.append(f"**Goals:**\n{project.goals}")
    if project.business_context:
        parts.append(f"**Business Context:** {project.business_context}")
    if project.success_metrics:
        parts.append(f"**Success Metrics:** {project.success_metrics}")
    if project.constraints:
        parts.append(f"**Constraints:** {project.constraints}")
    if project.tech_stack:
        parts.append(f"**Tech Stack:** {project.tech_stack}")
    
    # Stakeholders
    if project.stakeholders:
        parts.append("\n### Stakeholders")
        for s in project.stakeholders:
            parts.append(f"- {s.name} ({s.role}) — influence: {s.influence}, interest: {s.interest}")
    
    # Target Users
    if project.target_users:
        parts.append("\n### Target Users")
        for u in project.target_users:
            pts = f" — Pain: {u.pain_points}" if u.pain_points else ""
            parts.append(f"- **{u.persona_name}**: {u.description}{pts}")
    
    # Features
    if project.features:
        parts.append("\n### Core Features")
        for f in project.features:
            parts.append(f"- [{f.priority.upper()}] **{f.name}**: {f.description}")
    
    # Functional Requirements
    if project.functional_reqs:
        parts.append("\n### Functional Requirements")
        for r in project.functional_reqs:
            parts.append(f"- **{r.req_id}** ({r.category}, {r.priority}): {r.title} — {r.description}")
    
    # Non-Functional Requirements
    if project.non_functional_reqs:
        parts.append("\n### Non-Functional Requirements")
        for n in project.non_functional_reqs:
            parts.append(f"- ({n.category}, {n.priority}): {n.description}" + (f" [Metric: {n.metric}]" if n.metric else ""))
    
    # Entities
    if project.entities:
        parts.append("\n### Data Model / Entities")
        for e in project.entities:
            parts.append(f"- **{e.name}**: {e.description}")
            for a in (e.attributes or []):
                pk = "PK" if a.is_pk else ""
                fk = "FK" if a.is_fk else ""
                flags = f" [{pk} {fk}]".strip() if (pk or fk) else ""
                nullable = " NOT NULL" if not a.nullable else ""
                parts.append(f"  - `{a.name}`: {a.type_}{flags}{nullable} — {a.description}")
    
    # Relationships
    if project.relationships:
        parts.append("\n### Entity Relationships")
        for r in project.relationships:
            parts.append(f"- {r.source_entity} --({r.relationship_type})--> {r.target_entity}" + (f" — {r.description}" if r.description else ""))
    
    # Sequence Flows
    if project.sequence_flows:
        parts.append("\n### System Interactions / Sequence Flows")
        for f in project.sequence_flows:
            parts.append(f"- **{f.title}** (Actors: {f.actors})")
            if f.steps:
                for line in f.steps.strip().split("\n"):
                    parts.append(f"  - {line.strip()}")
    
    return "\n".join(parts)


def _call_ai(doc_type: str, context: str, settings) -> Optional[str]:
    """Call OpenAI API with prompts for the given document type."""
    system_prompt = SYSTEM_PROMPTS.get(doc_type, SYSTEM_PROMPTS["prd"])
    
    user_prompt = (
        f"Buatkan dokumen **{doc_type.upper()}** yang komprehensif dan siap pakai "
        f"berdasarkan data project berikut:\n\n"
        f"{context}\n\n"
        f"Hasilkan dokumen Markdown yang lengkap, profesional, dan detail. "
        f"Gunakan data di atas sebagai fondasi, kembangkan dengan asumsi yang logis jika ada informasi kurang. "
        f"Tandai asumsi dengan *(asumsi)*. Target: 80-90% kelengkapan."
    )
    
    client = OpenAI(
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL,
        timeout=settings.OPENAI_TIMEOUT,
    )
    
    response = client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.4,
        max_tokens=4096,
    )
    
    return response.choices[0].message.content


def generate_document(project: Project, doc_type: str, mode: str = "auto") -> str:
    """
    Generate a document using AI if available, else fallback to template.
    
    Args:
        project: Project model with all relations
        doc_type: One of 'prd', 'fsd', 'srs', 'erd', 'sequence'
        mode: 'ai' -> force AI, 'template' -> force template, 'auto' -> AI if key configured
    
    Returns:
        Markdown string
    """
    if doc_type not in SYSTEM_PROMPTS:
        raise ValueError(f"Unknown document type: {doc_type}. Choose from {list(SYSTEM_PROMPTS.keys())}")
    
    settings = get_settings()
    
    # Decide whether to use AI
    use_ai = False
    if mode == "ai":
        use_ai = True
    elif mode == "auto" and settings.ai_available:
        use_ai = True
    
    if use_ai:
        try:
            context = _build_context(project)
            result = _call_ai(doc_type, context, settings)
            if result:
                return result
        except Exception as e:
            # Log the error and fallback
            import logging
            logging.getLogger(__name__).warning(
                f"AI generation failed for {doc_type}, falling back to template: {e}"
            )
    
    # Fallback: use Jinja2 template
    return template_generate(project, doc_type)


def generate_all(project: Project, mode: str = "auto") -> dict[str, str]:
    """Generate all document types using AI or template."""
    return {dt: generate_document(project, dt, mode) for dt in SYSTEM_PROMPTS}
