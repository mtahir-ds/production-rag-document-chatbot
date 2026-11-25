"""Qdrant vector database service supporting Qdrant Cloud and local storage."""

import asyncio
import logging
from dataclasses import dataclass

from qdrant_client import QdrantClient, models
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import Settings
from app.ingestion.chunking import DocumentChunk
from app.services.exceptions import ExternalServiceError

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class VectorSearchHit:
    """Single vector search result returned from Qdrant."""

    chunk_id: str
    document_id: str
    filename: str
    page_or_section: str
    chunk_position: int
    text: str
    score: float


class QdrantVectorStore:
    """Manages Qdrant collection setup, upserts, filtered search, and deletions."""

    def __init__(self, settings: Settings) -> None:
        self.collection_name = settings.qdrant_collection
        self.dimensions = settings.embedding_dimensions
        self.timeout_seconds = settings.api_timeout_seconds
        self.max_retries = settings.api_max_retries
        self.mode = settings.qdrant_mode

        if settings.qdrant_mode == "cloud":
            if not settings.qdrant_url or not settings.qdrant_api_key:
                raise ExternalServiceError(
                    "Qdrant",
                    "QDRANT_URL and QDRANT_API_KEY must be set when QDRANT_MODE=cloud.",
                )
            self._client = QdrantClient(
                url=settings.qdrant_url,
                api_key=settings.qdrant_api_key,
                timeout=settings.api_timeout_seconds,
            )
        else:
            self._client = QdrantClient(path=settings.qdrant_path)

        self._collection_ready = False

    def _run_with_retry(self, fn):
        """Run a synchronous Qdrant client operation with bounded retries."""

        @retry(
            retry=retry_if_exception_type(Exception),
            stop=stop_after_attempt(self.max_retries + 1),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
            reraise=True,
        )
        def _wrapped():
            return fn()

        try:
            return _wrapped()
        except Exception as exc:
            logger.error("Qdrant operation failed (%s): %s", type(exc).__name__, exc)
            raise ExternalServiceError(
                "Qdrant",
                "Vector database request failed or timed out.",
            ) from exc

    def ensure_collection_sync(self) -> None:
        """Create the Qdrant collection and payload indexes if missing."""
        if self._collection_ready:
            return

        def _ensure() -> None:
            existing = {
                col.name for col in self._client.get_collections().collections
            }
            if self.collection_name not in existing:
                self._client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=models.VectorParams(
                        size=self.dimensions,
                        distance=models.Distance.COSINE,
                    ),
                )
                logger.info(
                    "Created Qdrant collection '%s' (dims=%d, cosine)",
                    self.collection_name,
                    self.dimensions,
                )

            # Payload indexes are required by Qdrant Cloud/server for filtered search/delete.
            if self.mode != "local":
                for field_name in ("user_id", "document_id"):
                    self._client.create_payload_index(
                        collection_name=self.collection_name,
                        field_name=field_name,
                        field_schema=models.PayloadSchemaType.KEYWORD,
                    )

        self._run_with_retry(_ensure)
        self._collection_ready = True

    async def ensure_collection(self) -> None:
        """Ensure Qdrant collection and indexes exist asynchronously."""
        await asyncio.wait_for(
            asyncio.to_thread(self.ensure_collection_sync),
            timeout=self.timeout_seconds,
        )

    async def upsert_chunks(
        self,
        chunks: list[DocumentChunk],
        vectors: list[list[float]],
        batch_size: int = 64,
    ) -> int:
        """Upsert chunk vectors and metadata payloads into Qdrant."""
        if len(chunks) != len(vectors):
            raise ValueError("Chunks and vectors lengths must match.")
        if not chunks:
            return 0

        await self.ensure_collection()

        points = [
            models.PointStruct(
                id=chunk.chunk_id,
                vector=vector,
                payload={
                    "chunk_id": chunk.chunk_id,
                    "document_id": chunk.document_id,
                    "user_id": chunk.user_id,
                    "filename": chunk.filename,
                    "page_or_section": chunk.page_or_section,
                    "chunk_position": chunk.chunk_position,
                    "token_count": chunk.token_count,
                    "text": chunk.text,
                },
            )
            for chunk, vector in zip(chunks, vectors)
        ]

        def _upsert_all() -> None:
            for i in range(0, len(points), batch_size):
                batch = points[i : i + batch_size]
                self._run_with_retry(
                    lambda b=batch: self._client.upsert(
                        collection_name=self.collection_name,
                        points=b,
                        wait=True,
                    )
                )

        try:
            await asyncio.wait_for(
                asyncio.to_thread(_upsert_all),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise ExternalServiceError("Qdrant", "Vector upsert timed out.") from exc

        return len(points)

    async def search(
        self,
        *,
        query_vector: list[float],
        user_id: str,
        top_k: int = 5,
        document_ids: list[str] | None = None,
        score_threshold: float | None = None,
    ) -> list[VectorSearchHit]:
        """Query top-k semantically similar chunks scoped to a user and optional documents."""
        await self.ensure_collection()

        conditions: list[models.Condition] = [
            models.FieldCondition(
                key="user_id",
                match=models.MatchValue(value=user_id),
            )
        ]
        if document_ids:
            conditions.append(
                models.FieldCondition(
                    key="document_id",
                    match=models.MatchAny(any=document_ids),
                )
            )
        query_filter = models.Filter(must=conditions)

        def _query():
            return self._run_with_retry(
                lambda: self._client.query_points(
                    collection_name=self.collection_name,
                    query=query_vector,
                    query_filter=query_filter,
                    limit=top_k,
                    score_threshold=score_threshold,
                    with_payload=True,
                )
            )

        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(_query),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise ExternalServiceError("Qdrant", "Vector search timed out.") from exc

        hits: list[VectorSearchHit] = []
        for point in response.points:
            payload = point.payload or {}
            hits.append(
                VectorSearchHit(
                    chunk_id=str(payload.get("chunk_id", point.id)),
                    document_id=str(payload.get("document_id", "")),
                    filename=str(payload.get("filename", "")),
                    page_or_section=str(payload.get("page_or_section", "")),
                    chunk_position=int(payload.get("chunk_position", 0)),
                    text=str(payload.get("text", "")),
                    score=round(float(point.score), 4),
                )
            )
        return hits

    async def delete_document_vectors(self, document_id: str, user_id: str) -> None:
        """Delete all vectors belonging to a document and user."""
        await self.ensure_collection()

        doc_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="document_id",
                    match=models.MatchValue(value=document_id),
                ),
                models.FieldCondition(
                    key="user_id",
                    match=models.MatchValue(value=user_id),
                ),
            ]
        )

        def _delete() -> None:
            self._run_with_retry(
                lambda: self._client.delete(
                    collection_name=self.collection_name,
                    points_selector=models.FilterSelector(filter=doc_filter),
                    wait=True,
                )
            )

        try:
            await asyncio.wait_for(
                asyncio.to_thread(_delete),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise ExternalServiceError("Qdrant", "Vector deletion timed out.") from exc

    async def count_document_vectors(self, document_id: str, user_id: str) -> int:
        """Count vectors currently stored for a specific document and user."""
        await self.ensure_collection()

        doc_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="document_id",
                    match=models.MatchValue(value=document_id),
                ),
                models.FieldCondition(
                    key="user_id",
                    match=models.MatchValue(value=user_id),
                ),
            ]
        )

        def _count() -> int:
            res = self._run_with_retry(
                lambda: self._client.count(
                    collection_name=self.collection_name,
                    count_filter=doc_filter,
                    exact=True,
                )
            )
            return int(res.count)

        return await asyncio.wait_for(
            asyncio.to_thread(_count),
            timeout=self.timeout_seconds,
        )

    def check_health_sync(self) -> bool:
        """Check Qdrant cluster/local reachability."""
        try:
            self._client.get_collections()
            return True
        except Exception:
            return False

    def close(self) -> None:
        """Close underlying Qdrant client resources."""
        try:
            self._client.close()
        except Exception:
            pass
