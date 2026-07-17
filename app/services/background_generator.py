"""
Background Document Generator — runs generation in a background thread
and saves results to the DocumentGeneration history table.
"""
from __future__ import annotations
from datetime import datetime, timezone

from app.database import create_session
from app.models import Project, DocumentGeneration
from app.services.ai_generator import generate_document


def run_generation(gen_id: str) -> None:
    """Background task: generate document content and save to DB.
    
    Opens its own DB session so it's independent of the request session.
    """
    session = create_session()
    try:
        gen = session.get(DocumentGeneration, gen_id)
        if not gen:
            return

        # Mark as processing
        gen.status = "processing"
        session.add(gen)
        session.commit()
        session.refresh(gen)

        # Fetch project with all relations (lazy='selectin' handles this)
        project = session.get(Project, gen.project_id)
        if not project:
            gen.status = "failed"
            gen.error = "Project not found"
            session.add(gen)
            session.commit()
            return

        # Generate the document
        content = generate_document(project, gen.doc_type, gen.mode)

        # Save result
        gen.content = content
        gen.status = "completed"
        gen.completed_at = datetime.now(timezone.utc)
        session.add(gen)
        session.commit()

    except Exception as e:
        try:
            gen.status = "failed"
            gen.error = str(e)
            session.add(gen)
            session.commit()
        except Exception:
            pass
    finally:
        session.close()
