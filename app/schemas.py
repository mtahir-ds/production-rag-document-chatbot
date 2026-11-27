"""Pydantic v2 request and response schemas for the RAG API."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class HealthResponse(BaseModel):
    """Service health status response."""

    status: str = Field(..., examples=["healthy"])
    app_name: str = Field(..., examples=["Production RAG Service"])
    version: str = Field(..., examples=["0.1.0"])
    environment: str = Field(..., examples=["development"])
    database: str = Field(..., examples=["ok"])
    timestamp: datetime


class ErrorResponse(BaseModel):
    """Consistent error payload returned across all failure status codes."""

    error: str = Field(..., examples=["Validation Error"])
    detail: Any = Field(..., examples=["Uploaded file must be PDF, DOCX, TXT, MD, or PPTX."])
    status_code: int = Field(..., examples=[415])
    request_id: str = Field(..., examples=["req_a1b2c3d4"])


# --- Authentication Schemas (Bonus B1) ---


class UserSignupRequest(BaseModel):
    """Payload to register a new user account."""

    email: EmailStr = Field(..., examples=["student@example.com"])
    username: str = Field(..., min_length=3, max_length=50, examples=["tahir"])
    password: str = Field(..., min_length=8, max_length=128, examples=["StrongPass123!"])


class UserLoginRequest(BaseModel):
    """Payload to authenticate an existing user."""

    email: EmailStr = Field(..., examples=["student@example.com"])
    password: str = Field(..., min_length=1, max_length=128, examples=["StrongPass123!"])


class UserInfo(BaseModel):
    """Public user profile returned after authentication."""

    user_id: str
    email: EmailStr
    username: str
    created_at: datetime


class TokenResponse(BaseModel):
    """JWT access token response."""

    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    user: UserInfo


# --- Document Schemas ---


class DocumentMetadata(BaseModel):
    """Stored metadata for an ingested document."""

    model_config = ConfigDict(from_attributes=True)

    document_id: str = Field(..., examples=["doc_8f3a1c2b"])
    user_id: str = Field(..., examples=["usr_default"])
    filename: str = Field(..., examples=["company_handbook.pdf"])
    file_type: str = Field(..., examples=["pdf"])
    file_size_bytes: int = Field(..., examples=[245120])
    file_hash: str = Field(..., examples=["e3b0c44298fc1c149afbf4c8996fb924..."])
    page_count: int = Field(..., examples=[12])
    chunk_count: int = Field(..., examples=[28])
    status: str = Field(..., examples=["ingested"])
    created_at: datetime


class DocumentUploadResponse(BaseModel):
    """Response returned after successful document ingestion (201 Created)."""

    message: str = Field(..., examples=["Document uploaded and ingested successfully."])
    document: DocumentMetadata


class DocumentListResponse(BaseModel):
    """Response listing all documents owned by the user."""

    total: int = Field(..., examples=[2])
    documents: list[DocumentMetadata]


# --- Chat / RAG Schemas ---


class ChatAskRequest(BaseModel):
    """Question payload submitted to the RAG service."""

    question: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        examples=["What is the company policy on remote work reimbursement?"],
    )
    document_ids: list[str] | None = Field(
        default=None,
        description="Optional list of document IDs to restrict retrieval scope.",
        examples=[["doc_8f3a1c2b"]],
    )
    top_k: int | None = Field(
        default=None,
        ge=1,
        le=20,
        description="Optional override for the number of chunks to retrieve.",
        examples=[5],
    )


class Citation(BaseModel):
    """Verified citation referencing a retrieved chunk."""

    chunk_id: str = Field(..., examples=["doc_8f3a1c2b_chunk_3"])
    document_id: str = Field(..., examples=["doc_8f3a1c2b"])
    filename: str = Field(..., examples=["company_handbook.pdf"])
    page_or_section: str = Field(..., examples=["Page 4"])


class RetrievedChunk(BaseModel):
    """Chunk returned from vector search and exposed in the UI chunks panel."""

    chunk_id: str = Field(..., examples=["doc_8f3a1c2b_chunk_3"])
    document_id: str = Field(..., examples=["doc_8f3a1c2b"])
    filename: str = Field(..., examples=["company_handbook.pdf"])
    page_or_section: str = Field(..., examples=["Page 4"])
    chunk_position: int = Field(..., examples=[3])
    text: str = Field(..., examples=["Employees receive up to $500 annually for home office..."])
    similarity_score: float = Field(..., examples=[0.8421])


class ChatAskResponse(BaseModel):
    """Grounded RAG answer with verified citations and retrieved chunk evidence."""

    answer: str
    answered: bool = Field(
        ...,
        description="False if the service abstained due to insufficient context or guardrails.",
    )
    citations: list[Citation]
    retrieved_count: int = Field(..., ge=0)
    retrieved_chunks: list[RetrievedChunk]
    latency_ms: float = Field(..., ge=0.0)
    model_used: str
    request_id: str


# --- Observability / Metrics Schemas (Bonus B3) ---


class RequestMetricItem(BaseModel):
    """Single traced request record."""

    request_id: str
    endpoint: str
    method: str
    status_code: int
    latency_ms: float
    retrieval_ms: float
    llm_ms: float
    prompt_tokens: int
    completion_tokens: int
    estimated_cost_usd: float
    error_message: str | None = None
    created_at: datetime


class MetricsSummaryResponse(BaseModel):
    """Aggregated observability metrics for the monitoring dashboard."""

    total_requests: int
    ask_requests: int
    error_count: int
    error_rate: float
    p50_latency_ms: float
    p95_latency_ms: float
    total_prompt_tokens: int
    total_completion_tokens: int
    total_estimated_cost_usd: float
    recent_traces: list[RequestMetricItem]


class MetricsTracesResponse(BaseModel):
    """Paginated list of raw request trace records."""

    total: int
    traces: list[RequestMetricItem]
