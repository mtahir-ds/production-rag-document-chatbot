"""Thin API route for grounded question answering over uploaded documents."""

from fastapi import APIRouter, Depends, Request, status

from app.dependencies import get_current_user_id, get_rag_service
from app.rate_limiter import limiter
from app.schemas import ChatAskRequest, ChatAskResponse, ErrorResponse
from app.services.rag_service import RAGService

router = APIRouter(prefix="/api/chat", tags=["Chat & RAG"])

# Module-level variable read by slowapi at each request (no-arg callable).
# Injected from settings at app startup; monkeypatchable in tests.
_ASK_RATE_LIMIT = "20/minute"


def _get_ask_rate_limit() -> str:
    return _ASK_RATE_LIMIT


@router.post(
    "/ask",
    response_model=ChatAskResponse,
    status_code=status.HTTP_200_OK,
    summary="Ask a question over uploaded documents",
    responses={
        400: {"model": ErrorResponse, "description": "Blocked by input security guardrail"},
        404: {"model": ErrorResponse, "description": "Specified document_id not found"},
        422: {"model": ErrorResponse, "description": "Invalid, empty, or overly long question"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        503: {"model": ErrorResponse, "description": "Gemini API or Qdrant unavailable"},
    },
)
@limiter.limit(_get_ask_rate_limit)
async def ask_question(
    request: Request,
    payload: ChatAskRequest,
    user_id: str = Depends(get_current_user_id),
    rag_service: RAGService = Depends(get_rag_service),
) -> ChatAskResponse:
    """Retrieve relevant chunks, generate a grounded answer with citations, and expose scores."""
    req_id = getattr(request.state, "request_id", "-")
    return await rag_service.ask_question(
        question=payload.question,
        user_id=user_id,
        request_id=req_id,
        document_ids=payload.document_ids,
        top_k=payload.top_k,
    )
