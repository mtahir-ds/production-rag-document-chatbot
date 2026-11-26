"""End-to-end RAG question-answering orchestration with guardrails and telemetry."""

import logging
import time

from fastapi import HTTPException, status

from app.config import Settings
from app.generation import GeminiGenerationService
from app.guardrails import sanitize_and_verify_output, validate_question_input
from app.retrieval import RetrievalService
from app.schemas import ChatAskResponse
from app.services.database import DatabaseManager

logger = logging.getLogger(__name__)


class RAGService:
    """Coordinates guardrails, retrieval, grounded generation, citation verification, and metrics."""

    def __init__(
        self,
        *,
        settings: Settings,
        db: DatabaseManager,
        retrieval: RetrievalService,
        generation: GeminiGenerationService,
    ) -> None:
        self.settings = settings
        self.db = db
        self.retrieval = retrieval
        self.generation = generation

    async def ask_question(
        self,
        *,
        question: str,
        user_id: str,
        request_id: str,
        document_ids: list[str] | None = None,
        top_k: int | None = None,
    ) -> ChatAskResponse:
        """Run the full guarded RAG workflow and persist observability trace metrics."""
        start_total = time.perf_counter()
        retrieval_ms = 0.0
        llm_ms = 0.0
        prompt_tokens = 0
        completion_tokens = 0
        estimated_cost_usd = 0.0

        # 1. Input guardrails (raises 422 on empty/long, 400 on injection/jailbreak).
        try:
            check = validate_question_input(
                question=question,
                max_length=self.settings.max_question_length,
            )
        except HTTPException as exc:
            total_ms = (time.perf_counter() - start_total) * 1000
            self.db.record_request_metric(
                request_id=request_id,
                user_id=user_id,
                endpoint="/api/chat/ask",
                method="POST",
                status_code=exc.status_code,
                latency_ms=total_ms,
                error_message=str(exc.detail),
            )
            raise

        # 2. Off-topic pre-retrieval refusal.
        if check.is_off_topic:
            total_ms = (time.perf_counter() - start_total) * 1000
            self.db.record_request_metric(
                request_id=request_id,
                user_id=user_id,
                endpoint="/api/chat/ask",
                method="POST",
                status_code=200,
                latency_ms=total_ms,
            )
            return ChatAskResponse(
                answer=check.off_topic_reason or "Off-topic request declined.",
                answered=False,
                citations=[],
                retrieved_count=0,
                retrieved_chunks=[],
                latency_ms=round(total_ms, 2),
                model_used=self.settings.gemini_llm_model,
                request_id=request_id,
            )

        # 3. Verify the user has documents (and requested document_ids exist).
        user_docs = self.db.list_documents(user_id=user_id)
        if not user_docs:
            total_ms = (time.perf_counter() - start_total) * 1000
            self.db.record_request_metric(
                request_id=request_id,
                user_id=user_id,
                endpoint="/api/chat/ask",
                method="POST",
                status_code=200,
                latency_ms=total_ms,
            )
            return ChatAskResponse(
                answer=(
                    "No documents are currently uploaded. Please upload at least one "
                    "document before asking a question."
                ),
                answered=False,
                citations=[],
                retrieved_count=0,
                retrieved_chunks=[],
                latency_ms=round(total_ms, 2),
                model_used=self.settings.gemini_llm_model,
                request_id=request_id,
            )

        if document_ids:
            owned_ids = {doc["document_id"] for doc in user_docs}
            missing = [doc_id for doc_id in document_ids if doc_id not in owned_ids]
            if missing:
                total_ms = (time.perf_counter() - start_total) * 1000
                detail = f"Document(s) not found: {', '.join(missing)}"
                self.db.record_request_metric(
                    request_id=request_id,
                    user_id=user_id,
                    endpoint="/api/chat/ask",
                    method="POST",
                    status_code=status.HTTP_404_NOT_FOUND,
                    latency_ms=total_ms,
                    error_message=detail,
                )
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)

        # 4. Semantic retrieval from Qdrant.
        try:
            retrieval_res = await self.retrieval.retrieve(
                question=check.cleaned_question,
                user_id=user_id,
                document_ids=document_ids,
                top_k=top_k,
            )
            retrieval_ms = retrieval_res.retrieval_ms

            # 5. If no chunks meet the similarity threshold, abstain safely.
            if not retrieval_res.qualified_chunks:
                total_ms = (time.perf_counter() - start_total) * 1000
                self.db.record_request_metric(
                    request_id=request_id,
                    user_id=user_id,
                    endpoint="/api/chat/ask",
                    method="POST",
                    status_code=200,
                    latency_ms=total_ms,
                    retrieval_ms=retrieval_ms,
                )
                return ChatAskResponse(
                    answer=(
                        "The uploaded documents do not contain enough relevant information "
                        "to answer this question."
                    ),
                    answered=False,
                    citations=[],
                    retrieved_count=len(retrieval_res.all_chunks),
                    retrieved_chunks=retrieval_res.all_chunks,
                    latency_ms=round(total_ms, 2),
                    model_used=self.settings.gemini_llm_model,
                    request_id=request_id,
                )

            # 6. Grounded generation via Gemini.
            gen_res = await self.generation.generate_answer(
                question=check.cleaned_question,
                chunks=retrieval_res.qualified_chunks,
            )
            llm_ms = gen_res.llm_ms
            prompt_tokens = gen_res.prompt_tokens
            completion_tokens = gen_res.completion_tokens
            estimated_cost_usd = gen_res.estimated_cost_usd

            # 7. Output guardrails and citation verification against actually retrieved chunks.
            verified = sanitize_and_verify_output(
                raw_answer=gen_res.answer,
                model_answered=gen_res.answered,
                cited_chunk_ids=gen_res.cited_chunk_ids,
                retrieved_chunks=retrieval_res.all_chunks,
            )

            total_ms = (time.perf_counter() - start_total) * 1000
            self.db.record_request_metric(
                request_id=request_id,
                user_id=user_id,
                endpoint="/api/chat/ask",
                method="POST",
                status_code=200,
                latency_ms=total_ms,
                retrieval_ms=retrieval_ms,
                llm_ms=llm_ms,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                estimated_cost_usd=estimated_cost_usd,
            )

            return ChatAskResponse(
                answer=verified.answer,
                answered=verified.answered,
                citations=verified.citations,
                retrieved_count=len(retrieval_res.all_chunks),
                retrieved_chunks=retrieval_res.all_chunks,
                latency_ms=round(total_ms, 2),
                model_used=gen_res.model_used,
                request_id=request_id,
            )
        except HTTPException as exc:
            total_ms = (time.perf_counter() - start_total) * 1000
            self.db.record_request_metric(
                request_id=request_id,
                user_id=user_id,
                endpoint="/api/chat/ask",
                method="POST",
                status_code=exc.status_code,
                latency_ms=total_ms,
                retrieval_ms=retrieval_ms,
                llm_ms=llm_ms,
                error_message=str(exc.detail),
            )
            raise
        except Exception as exc:
            total_ms = (time.perf_counter() - start_total) * 1000
            self.db.record_request_metric(
                request_id=request_id,
                user_id=user_id,
                endpoint="/api/chat/ask",
                method="POST",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                latency_ms=total_ms,
                retrieval_ms=retrieval_ms,
                llm_ms=llm_ms,
                error_message=str(exc),
            )
            raise
