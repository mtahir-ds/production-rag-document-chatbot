"""Google Gemini embedding service with batching, timeouts, and retries."""

import asyncio
import logging

from google import genai
from google.genai import types
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import Settings
from app.services.exceptions import ExternalServiceError

logger = logging.getLogger(__name__)


class _TransientEmbeddingError(Exception):
    """Internal wrapper for retryable embedding failures."""


class GeminiEmbeddingService:
    """Generates dense vector embeddings using the Google Gemini API."""

    def __init__(self, settings: Settings) -> None:
        self.model = settings.gemini_embedding_model
        self.dimensions = settings.embedding_dimensions
        self.timeout_seconds = settings.api_timeout_seconds
        self.max_retries = settings.api_max_retries
        self._api_key = settings.gemini_api_key
        self._client = (
            genai.Client(api_key=settings.gemini_api_key)
            if settings.gemini_api_key
            else None
        )

    def _require_client(self) -> genai.Client:
        if not self._client or not self._api_key:
            raise ExternalServiceError(
                "Gemini Embeddings",
                "GEMINI_API_KEY is not configured.",
            )
        return self._client

    def _embed_batch_sync(self, texts: list[str], task_type: str) -> list[list[float]]:
        """Call Gemini embed_content synchronously inside a worker thread."""
        client = self._require_client()
        try:
            response = client.models.embed_content(
                model=self.model,
                contents=texts,
                config=types.EmbedContentConfig(
                    task_type=task_type,
                    output_dimensionality=self.dimensions,
                ),
            )
            vectors = [list(emb.values) for emb in (response.embeddings or [])]
            if len(vectors) != len(texts):
                raise ExternalServiceError(
                    "Gemini Embeddings",
                    f"Expected {len(texts)} embeddings, received {len(vectors)}.",
                )
            return vectors
        except ExternalServiceError:
            raise
        except Exception as exc:
            msg = str(exc)
            # Fail fast on auth or invalid model errors; retry transient/rate/network issues.
            if any(code in msg for code in ("401", "403", "API_KEY_INVALID", "NOT_FOUND")):
                raise ExternalServiceError("Gemini Embeddings", msg) from exc
            raise _TransientEmbeddingError(msg) from exc

    async def _embed_with_retry(self, texts: list[str], task_type: str) -> list[list[float]]:
        """Execute a single batch embedding with configured timeout and retries."""

        @retry(
            retry=retry_if_exception_type((_TransientEmbeddingError, asyncio.TimeoutError)),
            stop=stop_after_attempt(self.max_retries + 1),
            wait=wait_exponential(multiplier=1, min=1, max=6),
            reraise=True,
        )
        async def _call() -> list[list[float]]:
            return await asyncio.wait_for(
                asyncio.to_thread(self._embed_batch_sync, texts, task_type),
                timeout=self.timeout_seconds,
            )

        try:
            return await _call()
        except (_TransientEmbeddingError, asyncio.TimeoutError) as exc:
            logger.error("Gemini embedding call failed after retries: %s", type(exc).__name__)
            raise ExternalServiceError(
                "Gemini Embeddings",
                "Embedding API timed out or is temporarily unavailable.",
            ) from exc

    async def embed_documents(
        self, texts: list[str], batch_size: int = 32
    ) -> list[list[float]]:
        """Embed document chunks in parallelized batches."""
        if not texts:
            return []

        batches = [texts[i : i + batch_size] for i in range(0, len(texts), batch_size)]
        results = await asyncio.gather(
            *(self._embed_with_retry(batch, "RETRIEVAL_DOCUMENT") for batch in batches)
        )
        vectors: list[list[float]] = []
        for batch_vectors in results:
            vectors.extend(batch_vectors)
        return vectors

    async def embed_query(self, query: str) -> list[float]:
        """Embed a single user question for semantic search."""
        vectors = await self._embed_with_retry([query], "RETRIEVAL_QUERY")
        return vectors[0]
