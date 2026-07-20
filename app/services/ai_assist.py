"""AI Assist Service — generates contextual suggestions for each requirement input step."""
from __future__ import annotations
import json
import re
from typing import Optional
from openai import OpenAI

from app.config import get_settings
from app.models import Project


def _build_context_upto(project: Project, upto_step: str) -> str:
    """Build context from project data up to a given step."""
    parts = [f"## Project: {project.name}"]
    
    # Basic info (always included)
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
    if project.stakeholders and upto_step in ("features", "func_reqs", "nfr", "data_model", "system_interactions"):
        parts.append("\n### Stakeholders")
        for s in project.stakeholders:
            parts.append(f"- {s.name} ({s.role}) — influence: {s.influence}, interest: {s.interest}")
    
    # Target Users
    if project.target_users and upto_step in ("features", "func_reqs", "data_model", "system_interactions"):
        parts.append("\n### Target Users")
        for u in project.target_users:
            pts = f" — Pain: {u.pain_points}" if u.pain_points else ""
            parts.append(f"- **{u.persona_name}**: {u.description}{pts}")
    
    # Features
    if project.features and upto_step in ("func_reqs", "data_model", "system_interactions"):
        parts.append("\n### Core Features")
        for f in project.features:
            parts.append(f"- [{f.priority.upper()}] **{f.name}**: {f.description}")
    
    # Functional Requirements
    if project.functional_reqs and upto_step in ("data_model", "system_interactions"):
        parts.append("\n### Functional Requirements")
        for r in project.functional_reqs:
            parts.append(f"- **{r.req_id}** ({r.category}, {r.priority}): {r.title} — {r.description}")
    
    # Non-Functional Requirements
    if project.non_functional_reqs and upto_step in ("data_model", "system_interactions"):
        parts.append("\n### Non-Functional Requirements")
        for n in project.non_functional_reqs:
            parts.append(f"- ({n.category}, {n.priority}): {n.description}" + (f" [Metric: {n.metric}]" if n.metric else ""))
    
    # Data Model (for system_interactions)
    if project.entities and upto_step in ("system_interactions",):
        parts.append("\n### Data Model / Entities")
        for e in project.entities:
            parts.append(f"- **{e.name}**: {e.description}")
            for a in (e.attributes or []):
                pk = "PK" if a.is_pk else ""
                fk = "FK" if a.is_fk else ""
                flags = f" [{pk} {fk}]".strip() if (pk or fk) else ""
                parts.append(f"  - `{a.name}`: {a.type_}{flags}")
        if project.relationships:
            parts.append("\n### Entity Relationships")
            for r in project.relationships:
                parts.append(f"- {r.source_entity} --({r.relationship_type})--> {r.target_entity}" + (f" — {r.description}" if r.description else ""))
    
    return "\n".join(parts)


# ─── System prompts per assist step ─────────────────────

ASSIST_PROMPTS = {
    "features": {
        "system": (
            "Kamu adalah Senior Product Manager dengan 15+ tahun pengalaman. "
            "Tugasmu: membantu user mendefinisikan **Core Features** untuk project software. "
            "Gunakan data project info, stakeholders, dan target users sebagai dasar.\n\n"
            "Output HARUS berupa **JSON array** dengan format:\n"
            '```json\n'
            '{\n'
            '  "explanation": "Penjelasan singkat mengapa fitur-fitur ini direkomendasikan (1-2 kalimat)",\n'
            '  "items": [\n'
            '    {\n'
            '      "name": "Nama Fitur",\n'
            '      "description": "Deskripsi singkat fitur",\n'
            '      "priority": "must|should|could|wont"\n'
            '    }\n'
            '  ]\n'
            '}\n'
            '```\n\n'
            "Output 4-6 fitur yang paling relevan. Gunakan Bahasa Indonesia. "
            "Jangan output markdown lain — hanya JSON."
        ),
        "user": (
            "Berdasarkan data project berikut, rekomendasikan core features "
            "yang paling penting menggunakan MoSCoW prioritization:\n\n{context}"
        ),
    },
    "func_reqs": {
        "system": (
            "Kamu adalah System Analyst berpengalaman. "
            "Tugasmu: membantu user mendefinisikan **Functional Requirements** (persyaratan fungsional). "
            "Gunakan data project info, stakeholders, target users, dan features.\n\n"
            "Output HARUS berupa **JSON** dengan format:\n"
            '```json\n'
            '{\n'
            '  "explanation": "Penjelasan singkat",\n'
            '  "items": [\n'
            '    {\n'
            '      "req_id": "FR-001",\n'
            '      "title": "Judul Requirement",\n'
            '      "description": "Deskripsi detail — apa yang sistem harus lakukan",\n'
            '      "category": "general|auth|data|ui|integration|reporting",\n'
            '      "priority": "low|medium|high|critical"\n'
            '    }\n'
            '  ]\n'
            '}\n'
            '```\n\n'
            "Output 5-8 functional requirements. Gunakan Bahasa Indonesia. "
            "Hanya JSON, tanpa markdown lain."
        ),
        "user": (
            "Berdasarkan data project berikut, rekomendasikan functional requirements:\n\n{context}"
        ),
    },
    "nfr": {
        "system": (
            "Kamu adalah Solution Architect berpengalaman. "
            "Tugasmu: membantu user mendefinisikan **Non-Functional Requirements** / persyaratan kualitas "
            "berdasarkan standar industri ISO 25010. "
            "Gunakan data project info dan tech stack sebagai acuan.\n\n"
            "Output HARUS berupa **JSON** dengan format:\n"
            '```json\n'
            '{\n'
            '  "explanation": "Penjelasan singkat",\n'
            '  "items": [\n'
            '    {\n'
            '      "category": "performance|security|usability|reliability|scalability|availability|maintainability",\n'
            '      "description": "Deskripsi requirement yang spesifik dan terukur",\n'
            '      "metric": "Target angka yang terukur (e.g. <500ms, 99.9%)",\n'
            '      "priority": "low|medium|high|critical"\n'
            '    }\n'
            '  ]\n'
            '}\n'
            '```\n\n'
            "Output 4-6 non-functional requirements. Pastikan metriknya realistis. "
            "Gunakan Bahasa Indonesia. Hanya JSON."
        ),
        "user": (
            "Berdasarkan data project berikut, rekomendasikan non-functional requirements "
            "yang sesuai standar industri:\n\n{context}"
        ),
    },
    "data_model": {
        "system": (
            "Kamu adalah Data Architect / Database Designer berpengalaman. "
            "Tugasmu: membantu user mendefinisikan **Data Model** — entity, atribut, dan relationships. "
            "Gunakan semua data yang sudah diisi sebelumnya.\n\n"
            "Output HARUS berupa **JSON** dengan format:\n"
            '```json\n'
            '{\n'
            '  "explanation": "Penjelasan singkat",\n'
            '  "entities": [\n'
            '    {\n'
            '      "name": "EntityName",\n'
            '      "description": "Deskripsi entity",\n'
            '      "attributes": [\n'
            '        {\n'
            '          "name": "field_name",\n'
            '          "type": "uuid|string|integer|float|boolean|date|datetime|json|text",\n'
            '          "is_pk": false,\n'
            '          "is_fk": false,\n'
            '          "nullable": true,\n'
            '          "description": "Deskripsi field"\n'
            '        }\n'
            '      ]\n'
            '    }\n'
            '  ],\n'
            '  "relationships": [\n'
            '    {\n'
            '      "source_entity": "EntityName",\n'
            '      "target_entity": "OtherEntity",\n'
            '      "relationship_type": "one-to-one|one-to-many|many-to-many",\n'
            '      "description": "Deskripsi hubungan"\n'
            '    }\n'
            '  ]\n'
            '}\n'
            '```\n\n'
            "Output 3-6 entity dengan 3-6 atribut per entity, serta relationships antar entity. "
            "Gunakan Bahasa Indonesia untuk description. Hanya JSON."
        ),
        "user": (
            "Berdasarkan data project berikut, rekomendasikan data model (entity, atribut, relationships):\n\n{context}"
        ),
    },
    "system_interactions": {
        "system": (
            "Kamu adalah System Architect berpengalaman. "
            "Tugasmu: membantu user mendefinisikan **System Interactions / Sequence Flows** — "
            "bagaimana actor dan sistem berinteraksi dalam urutan langkah-langkah. "
            "Gunakan project info, stakeholders, target users, functional reqs, dan data model.\n\n"
            "Output HARUS berupa **JSON** dengan format:\n"
            '```json\n'
            '{\n'
            '  "explanation": "Penjelasan singkat",\n'
            '  "flows": [\n'
            '    {\n'
            '      "title": "Nama Flow",\n'
            '      "actors": "Actor1, Actor2, System",\n'
            '      "steps": "Actor1 -> System: Action description\\nSystem -->> Actor1: Response description\\nActor1 -> Component: Another action"\n'
            '    }\n'
            '  ]\n'
            '}\n'
            '```\n\n'
            "Format steps: `Actor -> Target: Action` untuk request, `-->>` untuk response. "
            "Output 3-5 sequence flows yang mencakup happy path, alternatif, dan error scenarios. "
            "Gunakan Bahasa Indonesia. Hanya JSON."
        ),
        "user": (
            "Berdasarkan data project berikut, rekomendasikan system interactions / sequence flows:\n\n{context}"
        ),
    },
}


def _clean_json_output(text: str) -> str:
    """Extract JSON from possible markdown code fences."""
    # Remove markdown code fences
    text = text.strip()
    # Try to find JSON between ```json and ```
    match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if match:
        text = match.group(1).strip()
    # If starts with { or [, it's already clean
    if text.startswith("{") or text.startswith("["):
        return text
    # Try to find JSON object or array directly
    match = re.search(r'(\{|\[)[\s\S]*(\}|\])', text)
    if match:
        return match.group(0)
    return text


def suggest(project: Project, step: str) -> Optional[dict]:
    """Call AI to suggest content for a given input step."""
    if step not in ASSIST_PROMPTS:
        raise ValueError(f"Unknown assist step: {step}. Choose from {list(ASSIST_PROMPTS.keys())}")
    
    settings = get_settings()
    if not settings.ai_available:
        return {"error": "AI not configured. Please set OPENAI_API_KEY."}
    
    context = _build_context_upto(project, step)
    prompts = ASSIST_PROMPTS[step]
    
    client = OpenAI(
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL,
        timeout=settings.OPENAI_TIMEOUT,
    )
    
    response = client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": prompts["system"]},
            {"role": "user", "content": prompts["user"].format(context=context)},
        ],
        temperature=0.4,
        max_tokens=settings.OPENAI_MAX_TOKENS,
    )
    
    raw = response.choices[0].message.content
    clean = _clean_json_output(raw)
    
    try:
        result = json.loads(clean)
        return result
    except json.JSONDecodeError as e:
        return {"error": f"Failed to parse AI response: {e}", "raw": raw[:500]}
