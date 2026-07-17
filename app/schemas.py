from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ─── Nested Schemas ─────────────────────────────────────

class StakeholderSchema(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    role: str = Field(..., min_length=1, max_length=200)
    email: str = ""
    influence: str = "medium"
    interest: str = "medium"

class TargetUserSchema(BaseModel):
    persona_name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    pain_points: str = ""

class FeatureSchema(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    priority: str = "medium"

class FunctionalReqSchema(BaseModel):
    req_id: str = ""
    title: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    category: str = "general"
    priority: str = "medium"

class NonFunctionalReqSchema(BaseModel):
    category: str = "performance"
    description: str = ""
    metric: str = ""
    priority: str = "medium"

class EntityAttributeSchema(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    type_: str = Field("string", alias="type")
    is_pk: bool = False
    is_fk: bool = False
    nullable: bool = True
    description: str = ""

class EntitySchema(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    attributes: List[EntityAttributeSchema] = []

class EntityRelationshipSchema(BaseModel):
    source_entity: str = Field(..., min_length=1)
    target_entity: str = Field(..., min_length=1)
    relationship_type: str = "one-to-many"
    description: str = ""

class SequenceFlowSchema(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    actors: str = ""
    steps: str = ""


# ─── Project Schemas ───────────────────────────────────

class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    goals: str = ""
    business_context: str = ""
    success_metrics: str = ""
    constraints: str = ""
    tech_stack: str = ""
    stakeholders: List[StakeholderSchema] = []
    target_users: List[TargetUserSchema] = []
    features: List[FeatureSchema] = []
    functional_reqs: List[FunctionalReqSchema] = []
    non_functional_reqs: List[NonFunctionalReqSchema] = []
    entities: List[EntitySchema] = []
    relationships: List[EntityRelationshipSchema] = []
    sequence_flows: List[SequenceFlowSchema] = []

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    goals: Optional[str] = None
    business_context: Optional[str] = None
    success_metrics: Optional[str] = None
    constraints: Optional[str] = None
    tech_stack: Optional[str] = None


# ─── Response Schemas ──────────────────────────────────

class ProjectSummary(BaseModel):
    id: str
    name: str
    description: str
    created_at: datetime
    updated_at: datetime
    stats: dict = {}

    model_config = {"from_attributes": True}

class ProjectDetail(BaseModel):
    id: str
    name: str
    description: str
    goals: str
    business_context: str
    success_metrics: str
    constraints: str
    tech_stack: str
    created_at: datetime
    updated_at: datetime
    stakeholders: list = []
    target_users: list = []
    features: list = []
    functional_reqs: list = []
    non_functional_reqs: list = []
    entities: list = []
    relationships: list = []
    sequence_flows: list = []

    model_config = {"from_attributes": True}

class GenerateRequest(BaseModel):
    doc_types: List[str] = ["prd", "fsd", "srs", "erd", "sequence"]
