"""Thin API routes for document upload, listing, and deletion."""

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile, status

from app.dependencies import get_current_user_id, get_ingestion_service
from app.rate_limiter import limiter
from app.schemas import DocumentListResponse, DocumentUploadResponse, ErrorResponse
from app.services.ingestion_service import IngestionService

router = APIRouter(prefix="/api/documents", tags=["Documents"])

# Module-level variable read by slowapi at each request (no-arg callable).
# Injected from settings at app startup; monkeypatchable in tests.
_UPLOAD_RATE_LIMIT = "10/minute"


def _get_upload_rate_limit() -> str:
    return _UPLOAD_RATE_LIMIT


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and ingest a document",
    responses={
        400: {"model": ErrorResponse, "description": "Empty, corrupt, oversized, or unscannable file"},
        409: {"model": ErrorResponse, "description": "Duplicate file already uploaded"},
        415: {"model": ErrorResponse, "description": "Unsupported file type or mismatched MIME"},
        429: {"model": ErrorResponse, "description": "Upload rate limit exceeded"},
        503: {"model": ErrorResponse, "description": "Embedding API or vector DB unavailable"},
    },
)
@limiter.limit(_get_upload_rate_limit)
async def upload_document(
    request: Request,
    file: UploadFile = File(..., description="PDF, DOCX, PPTX, TXT, or MD document"),
    user_id: str = Depends(get_current_user_id),
    ingestion: IngestionService = Depends(get_ingestion_service),
) -> DocumentUploadResponse:
    """Upload a document, extract text, chunk, embed, and store vectors in Qdrant."""
    content = await file.read()
    document = await ingestion.ingest_document(
        user_id=user_id,
        filename=file.filename,
        content_type=file.content_type,
        content=content,
    )
    return DocumentUploadResponse(
        message="Document uploaded and ingested successfully.",
        document=document,
    )


@router.get(
    "",
    response_model=DocumentListResponse,
    status_code=status.HTTP_200_OK,
    summary="List uploaded documents",
)
async def list_documents(
    user_id: str = Depends(get_current_user_id),
    ingestion: IngestionService = Depends(get_ingestion_service),
) -> DocumentListResponse:
    """Return all uploaded documents belonging to the current user."""
    docs = ingestion.list_documents(user_id=user_id)
    return DocumentListResponse(total=len(docs), documents=docs)


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document and all of its vectors",
    responses={
        404: {"model": ErrorResponse, "description": "Document not found"},
        503: {"model": ErrorResponse, "description": "Vector database unavailable"},
    },
)
async def delete_document(
    document_id: str,
    user_id: str = Depends(get_current_user_id),
    ingestion: IngestionService = Depends(get_ingestion_service),
) -> Response:
    """Delete a document from Qdrant, SQLite, and local disk."""
    await ingestion.delete_document(document_id=document_id, user_id=user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
