"""Business logic orchestrating document ingestion, listing, and deletion."""

import logging
import uuid
from datetime import datetime

from fastapi import HTTPException, status

from app.config import Settings
from app.ingestion.chunking import chunk_sections
from app.ingestion.extract import extract_document
from app.ingestion.upload import (
    compute_sha256,
    remove_uploaded_file,
    save_uploaded_file,
    validate_upload_file,
)
from app.schemas import DocumentMetadata
from app.services.database import DatabaseManager
from app.services.embeddings import GeminiEmbeddingService
from app.services.vector_store import QdrantVectorStore

logger = logging.getLogger(__name__)


class IngestionService:
    """Coordinates validation, extraction, chunking, embedding, and vector storage."""

    def __init__(
        self,
        *,
        settings: Settings,
        db: DatabaseManager,
        embeddings: GeminiEmbeddingService,
        vector_store: QdrantVectorStore,
    ) -> None:
        self.settings = settings
        self.db = db
        self.embeddings = embeddings
        self.vector_store = vector_store

    async def ingest_document(
        self,
        *,
        user_id: str,
        filename: str | None,
        content_type: str | None,
        content: bytes,
    ) -> DocumentMetadata:
        """Validate, extract, chunk, embed, and store a document end-to-end."""
        safe_name, file_type = validate_upload_file(
            filename=filename,
            content_type=content_type,
            content=content,
            max_file_size_bytes=self.settings.max_file_size_bytes,
        )

        file_hash = compute_sha256(content)
        existing = self.db.get_document_by_hash(user_id=user_id, file_hash=file_hash)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Duplicate document: '{existing['filename']}' with identical content "
                    f"(document_id={existing['document_id']}) already exists."
                ),
            )

        extraction = extract_document(
            content=content,
            file_type=file_type,
            max_pdf_pages=self.settings.max_pdf_pages,
        )

        document_id = f"doc_{uuid.uuid4().hex[:12]}"
        chunks = chunk_sections(
            sections=extraction.sections,
            document_id=document_id,
            user_id=user_id,
            filename=safe_name,
            chunk_size_tokens=self.settings.chunk_size_tokens,
            chunk_overlap_tokens=self.settings.chunk_overlap_tokens,
        )
        if not chunks:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document produced no usable text chunks after processing.",
            )

        storage_path = save_uploaded_file(
            upload_dir=self.settings.upload_dir,
            user_id=user_id,
            document_id=document_id,
            safe_filename=safe_name,
            content=content,
        )

        try:
            vectors = await self.embeddings.embed_documents([c.text for c in chunks])
            await self.vector_store.upsert_chunks(chunks, vectors)
            record = self.db.create_document(
                document_id=document_id,
                user_id=user_id,
                filename=safe_name,
                file_type=file_type,
                file_size_bytes=len(content),
                file_hash=file_hash,
                page_count=extraction.page_count,
                chunk_count=len(chunks),
                storage_path=str(storage_path),
                status="ingested",
            )
        except Exception:
            # Roll back stored file and partial vectors so failed ingestion leaves no orphans.
            remove_uploaded_file(str(storage_path))
            try:
                await self.vector_store.delete_document_vectors(document_id, user_id)
            except Exception:
                pass
            raise

        logger.info(
            "Ingested document %s (%s, %d pages, %d chunks)",
            document_id,
            safe_name,
            extraction.page_count,
            len(chunks),
        )
        return self._to_schema(record)

    def list_documents(self, user_id: str) -> list[DocumentMetadata]:
        """List all ingested documents for the current user."""
        rows = self.db.list_documents(user_id=user_id)
        return [self._to_schema(row) for row in rows]

    async def delete_document(self, document_id: str, user_id: str) -> None:
        """Delete a document's vectors from Qdrant, registry row, and stored file."""
        doc = self.db.get_document(document_id=document_id, user_id=user_id)
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document '{document_id}' was not found.",
            )

        await self.vector_store.delete_document_vectors(
            document_id=document_id,
            user_id=user_id,
        )
        self.db.delete_document(document_id=document_id, user_id=user_id)
        remove_uploaded_file(doc["storage_path"])
        logger.info("Deleted document %s and its vectors", document_id)

    @staticmethod
    def _to_schema(row: dict) -> DocumentMetadata:
        return DocumentMetadata(
            document_id=row["document_id"],
            user_id=row["user_id"],
            filename=row["filename"],
            file_type=row["file_type"],
            file_size_bytes=row["file_size_bytes"],
            file_hash=row["file_hash"],
            page_count=row["page_count"],
            chunk_count=row["chunk_count"],
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
