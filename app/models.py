"""ReqWeaver Data Models — semua tabel disimpan di SQLite"""
from typing import Optional, List, TYPE_CHECKING
from sqlmodel import SQLModel, Field, Relationship, Column, JSON
from datetime import datetime, timezone
import uuid


def _utcnow():
    return datetime.now(timezone.utc)


def _new_id():
    return str(uuid.uuid4())


# ─── Stakeholder ───────────────────────────────────────────
class Stakeholder(SQLModel, table=True):
    __tablename__ = "stakeholders"
    id: str = Field(default=None, primary_key=True)
    project_id: str = Field(foreign_key="projects.id")
    name: str
    role: str
    email: str = ""
    influence: str = "medium"  # low / medium / high
    interest: str = "medium"   # low / medium / high

    project: Optional["Project"] = Relationship(back_populates="stakeholders")


# ─── Target User ──────────────────────────────────────────
class TargetUser(SQLModel, table=True):
    __tablename__ = "target_users"
    id: str = Field(default=None, primary_key=True)
    project_id: str = Field(foreign_key="projects.id")
    persona_name: str
    description: str
    pain_points: str = ""

    project: Optional["Project"] = Relationship(back_populates="target_users")


# ─── Feature ──────────────────────────────────────────────
class Feature(SQLModel, table=True):
    __tablename__ = "features"
    id: str = Field(default=None, primary_key=True)
    project_id: str = Field(foreign_key="projects.id")
    name: str
    description: str
    priority: str = "medium"  # must / should / could / wont

    project: Optional["Project"] = Relationship(back_populates="features")


# ─── Functional Requirement ───────────────────────────────
class FunctionalRequirement(SQLModel, table=True):
    __tablename__ = "functional_requirements"
    id: str = Field(default=None, primary_key=True)
    project_id: str = Field(foreign_key="projects.id")
    req_id: str = "FR-001"
    title: str
    description: str
    category: str = "general"   # auth / data / ui / integration / reporting
    priority: str = "medium"    # critical / high / medium / low

    project: Optional["Project"] = Relationship(back_populates="functional_reqs")


# ─── Non-Functional Requirement ──────────────────────────
class NonFunctionalRequirement(SQLModel, table=True):
    __tablename__ = "non_functional_requirements"
    id: str = Field(default=None, primary_key=True)
    project_id: str = Field(foreign_key="projects.id")
    category: str = "performance"  # performance / security / usability / reliability / scalability
    description: str
    metric: str = ""
    priority: str = "medium"

    project: Optional["Project"] = Relationship(back_populates="non_functional_reqs")


# ─── Entity (Data Model) ─────────────────────────────────
class EntityAttribute(SQLModel, table=True):
    __tablename__ = "entity_attributes"
    id: str = Field(default=None, primary_key=True)
    entity_id: str = Field(foreign_key="entities.id")
    name: str
    type_: str = Field("string", alias="type")
    is_pk: bool = False
    is_fk: bool = False
    nullable: bool = True
    description: str = ""


class Entity(SQLModel, table=True):
    __tablename__ = "entities"
    id: str = Field(default=None, primary_key=True)
    project_id: str = Field(foreign_key="projects.id")
    name: str
    description: str = ""

    project: Optional["Project"] = Relationship(back_populates="entities")
    attributes: List[EntityAttribute] = Relationship(
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "lazy": "selectin",
        }
    )


# ─── Relationship (for ERD) ──────────────────────────────
class EntityRelationship(SQLModel, table=True):
    __tablename__ = "entity_relationships"
    id: str = Field(default=None, primary_key=True)
    project_id: str = Field(foreign_key="projects.id")
    source_entity: str
    target_entity: str
    relationship_type: str = "one-to-many"   # one-to-one / one-to-many / many-to-many
    description: str = ""


# ─── Sequence Flow ──────────────────────────────────────
class SequenceFlow(SQLModel, table=True):
    __tablename__ = "sequence_flows"
    id: str = Field(default=None, primary_key=True)
    project_id: str = Field(foreign_key="projects.id")
    title: str
    actors: str = ""  # comma-separated actor names
    steps: str = ""   # newline-separated: actor -> action -> note


# ─── Project ─────────────────────────────────────────────
class Project(SQLModel, table=True):
    __tablename__ = "projects"
    id: str = Field(default=None, primary_key=True)
    name: str
    description: str = ""
    goals: str = ""
    business_context: str = ""
    success_metrics: str = ""
    constraints: str = ""
    tech_stack: str = ""
    created_at: datetime = Field(default=None)
    updated_at: datetime = Field(default=None)

    stakeholders: List[Stakeholder] = Relationship(
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "lazy": "selectin"}
    )
    target_users: List[TargetUser] = Relationship(
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "lazy": "selectin"}
    )
    features: List[Feature] = Relationship(
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "lazy": "selectin"}
    )
    functional_reqs: List[FunctionalRequirement] = Relationship(
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "lazy": "selectin"}
    )
    non_functional_reqs: List[NonFunctionalRequirement] = Relationship(
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "lazy": "selectin"}
    )
    entities: List[Entity] = Relationship(
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "lazy": "selectin"}
    )
    relationships: List[EntityRelationship] = Relationship(
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "lazy": "selectin"}
    )
    sequence_flows: List[SequenceFlow] = Relationship(
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "lazy": "selectin"}
    )
