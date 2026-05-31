from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ProcedureGroup(str, Enum):
    administrative = "administrative"
    interlinked = "interlinked"


class ProcedureSummary(BaseModel):
    source_id: str
    procedure_code: str
    procedure_group: ProcedureGroup
    name: str
    field_name: str | None = None
    published_agency: str | None = None
    implementation_agency: str | None = None
    source_url: str
    raw_summary: dict[str, Any] = Field(default_factory=dict)


class ProcedureDetail(ProcedureSummary):
    target_audience: str | None = None
    implementation_level: str | None = None
    execution_methods: list[dict[str, Any]] = Field(default_factory=list)
    execution_steps: str | None = None
    required_documents: str | None = None
    processing_time: str | None = None
    fees: str | None = None
    requirements: str | None = None
    legal_basis: str | None = None
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    related_procedures: list[dict[str, Any]] = Field(default_factory=list)
    raw_detail: dict[str, Any] = Field(default_factory=dict)
    content_hash: str


class CrawlPreviewResponse(BaseModel):
    group: ProcedureGroup
    total: int
    items: list[ProcedureSummary]


class ProcedureListItem(BaseModel):
    id: str
    source_id: str
    procedure_code: str
    procedure_group: ProcedureGroup
    name: str
    target_audience: str | None = None
    field_name: str | None = None
    published_agency: str | None = None
    implementation_agency: str | None = None
    implementation_level: str | None = None
    processing_time: str | None = None
    fees: str | None = None
    source_url: str
    updated_at: str | None = None


class ProcedureListResponse(BaseModel):
    items: list[ProcedureListItem]
    total: int
    page: int
    page_size: int


class ProcedureRecord(ProcedureListItem):
    execution_methods: list[dict[str, Any]] = Field(default_factory=list)
    execution_steps: str | None = None
    required_documents: str | None = None
    requirements: str | None = None
    legal_basis: str | None = None
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    related_procedures: list[dict[str, Any]] = Field(default_factory=list)
    last_seen_at: str | None = None
    source_updated_at: str | None = None


class FilterOptionsResponse(BaseModel):
    fields: list[str]
    agencies: list[str]
    levels: list[str]


class StatsBucket(BaseModel):
    name: str
    count: int


class StatsOverviewResponse(BaseModel):
    total: int
    administrative: int
    interlinked: int
    individual: int
    business: int
    both_or_unknown: int
    by_field: list[StatsBucket]
    by_agency: list[StatsBucket]
    recently_updated: list[ProcedureListItem]


class VectorSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    group: ProcedureGroup | None = None
    target_audience: str | None = None
    limit: int = Field(default=9, ge=1, le=20)


class VectorSearchResult(BaseModel):
    procedure_id: str
    procedure_code: str
    procedure_group: ProcedureGroup
    name: str
    field_name: str | None = None
    target_audience: str | None = None
    source_url: str
    similarity: float


class VectorSearchResponse(BaseModel):
    items: list[VectorSearchResult]


class ChatStartRequest(BaseModel):
    user_type: str = Field(pattern="^(individual|business)$")
    question: str = Field(min_length=3)


class ChatMessageRequest(BaseModel):
    message: str = Field(min_length=1)


class ChatContextUpdateRequest(BaseModel):
    procedure_context: list[dict[str, Any]] = Field(default_factory=list)
    source_context: list[dict[str, Any]] = Field(default_factory=list)


class ChatContextSummarizeRequest(BaseModel):
    procedure_id: str
    user_type: str = Field(pattern="^(individual|business)$")
    question: str = Field(min_length=1)


class LocalChatMessageRequest(BaseModel):
    user_type: str = Field(pattern="^(individual|business)$")
    initial_question: str = Field(min_length=1)
    message: str = Field(min_length=1)
    procedure_context: list[dict[str, Any]] = Field(default_factory=list)
    source_context: list[dict[str, Any]] = Field(default_factory=list)
    history: list[dict[str, Any]] = Field(default_factory=list)


class ChatProcedureContext(BaseModel):
    procedure_id: str
    procedure_code: str
    procedure_group: ProcedureGroup
    name: str
    source_url: str
    field_name: str | None = None
    target_audience: str | None = None
    summary: str


class ChatSourceChunk(BaseModel):
    chunk_id: str
    citation: str
    procedure_id: str
    procedure_code: str
    procedure_group: ProcedureGroup
    name: str
    section_name: str
    source_url: str
    field_name: str | None = None
    target_audience: str | None = None
    implementation_agency: str | None = None
    score: float | None = None
    text: str


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    procedures: list[ChatProcedureContext] = Field(default_factory=list)
    sources: list[ChatSourceChunk] = Field(default_factory=list)
    inference_seconds: float | None = None
    expires_at: str | None = None


class ChatSessionListItem(BaseModel):
    id: str
    user_type: str | None = None
    initial_question: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    expires_at: str | None = None


class ChatMessageRecord(BaseModel):
    id: str
    role: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None


class ChatSessionDetail(BaseModel):
    id: str
    user_type: str | None = None
    initial_question: str | None = None
    procedure_context: list[ChatProcedureContext] = Field(default_factory=list)
    source_context: list[ChatSourceChunk] = Field(default_factory=list)
    messages: list[ChatMessageRecord] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None
    expires_at: str | None = None
