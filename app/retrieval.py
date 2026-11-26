"""Query embedding and filtered semantic retrieval from Qdrant."""

import logging
import time
from dataclasses import dataclass

from app.config import Settings
from app.schemas import RetrievedChunk
from app.services.embeddings import GeminiEmbeddingService
from app.services.vector_store import QdrantVectorStore

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RetrievalResult:
    """Retrieved chunks partitioned by similarity threshold along with timing."""

    all_chunks: list[RetrievedChunk]
    qualified_chunks: list[RetrievedChunk]
    retrieval_ms: float


class RetrievalService:
    """Embeds user questions and searches Qdrant with metadata filters."""

    def __init__(
        self,
        *,
        settings: Settings,
        embeddings: GeminiEmbeddingService,
        vector_store: QdrantVectorStore,
    ) -> None:
        self.settings = settings
        self.embeddings = embeddings
        self.vector_store = vector_store

    async def retrieve(
        self,
        *,
        question: str,
        user_id: str,
        document_ids: list[str] | None = None,
        top_k: int | None = None,
    ) -> RetrievalResult:
        """Embed query, search Qdrant for top_k chunks, and filter by similarity threshold."""
        start = time.perf_counter()
        k = top_k or self.settings.retrieval_top_k

        query_vector = await self.embeddings.embed_query(question)
        hits = await self.vector_store.search(
            query_vector=query_vector,
            user_id=user_id,
            top_k=k,
            document_ids=document_ids,
            score_threshold=None,
        )

        all_chunks = [
            RetrievedChunk(
                chunk_id=hit.chunk_id,
                document_id=hit.document_id,
                filename=hit.filename,
                page_or_section=hit.page_or_section,
                chunk_position=hit.chunk_position,
                text=hit.text,
                similarity_score=hit.score,
            )
            for hit in hits
        ]

        qualified_chunks = [
            chunk
            for chunk in all_chunks
            if chunk.similarity_score >= self.settings.similarity_threshold
        ]
        retrieval_ms = (time.perf_counter() - start) * 1000

        logger.info(
            "Retrieved %d chunks (%d >= threshold %.2f) in %.2f ms",
            len(all_chunks),
            len(qualified_chunks),
            self.settings.similarity_threshold,
            retrieval_ms,
        )
        return RetrievalResult(
            all_chunks=all_chunks,
            qualified_chunks=qualified_chunks,
            retrieval_ms=retrieval_ms,
        )
