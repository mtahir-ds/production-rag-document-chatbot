"""FastAPI application entry point, middleware, error handlers, and routes."""

import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded

from app.config import Settings, get_settings
from app.generation import GeminiGenerationService
from app.services.groq_service import GroqGenerationService
from app.logging_config import configure_logging, request_id_ctx
from app.rate_limiter import limiter
from app.retrieval import RetrievalService
from app.routes.auth import router as auth_router
from app.routes.chat import router as chat_router
from app.routes.documents import router as documents_router
from app.routes.metrics import router as metrics_router
from app.schemas import ErrorResponse, HealthResponse
from app.services.auth_service import AuthService
from app.services.database import DatabaseManager
from app.services.embeddings import GeminiEmbeddingService
from app.services.exceptions import ExternalServiceError
from app.services.ingestion_service import IngestionService
from app.services.rag_service import RAGService
from app.services.vector_store import QdrantVectorStore

logger = logging.getLogger(__name__)


def create_app(
    settings_override: Settings | None = None,
    *,
    embeddings_override: GeminiEmbeddingService | None = None,
    vector_store_override: QdrantVectorStore | None = None,
    generation_override: GeminiGenerationService | None = None,
    enable_rate_limit: bool = True,
) -> FastAPI:
    """Construct and configure the FastAPI application instance."""
    settings = settings_override or get_settings()
    configure_logging(settings.log_level)
    db = DatabaseManager(settings.sqlite_db_path)

    def _init_services(app_instance: FastAPI) -> None:
        settings.ensure_directories()
        db.init_db()

        # Inject rate limits from settings into route-level module vars.
        import app.routes.chat as chat_route
        import app.routes.documents as doc_route
        chat_route._ASK_RATE_LIMIT = settings.rate_limit_ask
        doc_route._UPLOAD_RATE_LIMIT = settings.rate_limit_upload
        embeddings = embeddings_override or GeminiEmbeddingService(settings)
        vector_store = vector_store_override or QdrantVectorStore(settings)
        ingestion_service = IngestionService(
            settings=settings,
            db=db,
            embeddings=embeddings,
            vector_store=vector_store,
        )
        retrieval_service = RetrievalService(
            settings=settings,
            embeddings=embeddings,
            vector_store=vector_store,
        )
        if generation_override:
            generation_service = generation_override
        elif settings.llm_provider == "groq":
            generation_service = GroqGenerationService(settings)
            logger.info("LLM provider: Groq (%s)", settings.groq_model)
        else:
            generation_service = GeminiGenerationService(settings)
            logger.info("LLM provider: Gemini (%s)", settings.gemini_llm_model)
        rag_service = RAGService(
            settings=settings,
            db=db,
            retrieval=retrieval_service,
            generation=generation_service,
        )
        auth_service = AuthService(settings)
        app_instance.state.settings = settings
        app_instance.state.db = db
        app_instance.state.embeddings = embeddings
        app_instance.state.vector_store = vector_store
        app_instance.state.ingestion_service = ingestion_service
        app_instance.state.retrieval_service = retrieval_service
        app_instance.state.generation_service = generation_service
        app_instance.state.rag_service = rag_service
        app_instance.state.auth_service = auth_service

    @asynccontextmanager
    async def lifespan(app_instance: FastAPI) -> AsyncIterator[None]:
        _init_services(app_instance)
        logger.info(
            "Service started (env=%s, qdrant_mode=%s)",
            settings.app_env,
            settings.qdrant_mode,
        )
        yield
        vector_store = getattr(app_instance.state, "vector_store", None)
        if vector_store is not None:
            vector_store.close()
        logger.info("Service shutting down")

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Production-grade Retrieval-Augmented Generation (RAG) service with "
            "document ingestion, grounded citations, guardrails, and observability."
        ),
        lifespan=lifespan,
    )

    # Initialize state safely for tests that call routes without triggering lifespan.
    app.state.settings = settings
    app.state.db = db
    app.state.auth_service = AuthService(settings)
    limiter.enabled = enable_rate_limit
    limiter.reset()
    app.state.limiter = limiter

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_logging_middleware(request: Request, call_next):
        """Attach a request ID, measure latency, and log every request safely."""
        req_id = f"req_{uuid.uuid4().hex[:12]}"
        token = request_id_ctx.set(req_id)
        request.state.request_id = req_id
        start_time = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception as exc:
            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.exception(
                "Unhandled error on %s %s (%.2f ms): %s",
                request.method,
                request.url.path,
                latency_ms,
                type(exc).__name__,
            )
            request_id_ctx.reset(token)
            raise

        latency_ms = (time.perf_counter() - start_time) * 1000
        response.headers["X-Request-ID"] = req_id
        logger.info(
            "%s %s -> %d (%.2f ms)",
            request.method,
            request.url.path,
            response.status_code,
            latency_ms,
        )
        request_id_ctx.reset(token)
        return response

    @app.exception_handler(ExternalServiceError)
    async def external_service_exception_handler(
        request: Request, exc: ExternalServiceError
    ) -> JSONResponse:
        req_id = getattr(request.state, "request_id", "-")
        payload = ErrorResponse(
            error=f"{exc.service} Unavailable",
            detail=exc.detail,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            request_id=req_id,
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=payload.model_dump(),
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        req_id = getattr(request.state, "request_id", "-")
        payload = ErrorResponse(
            error="HTTP Error",
            detail=exc.detail,
            status_code=exc.status_code,
            request_id=req_id,
        )
        return JSONResponse(status_code=exc.status_code, content=payload.model_dump())

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        req_id = getattr(request.state, "request_id", "-")
        payload = ErrorResponse(
            error="Validation Error",
            detail=exc.errors(),
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            request_id=req_id,
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=payload.model_dump(),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        req_id = getattr(request.state, "request_id", "-")
        payload = ErrorResponse(
            error="Internal Server Error",
            detail="An unexpected error occurred. Please check server logs with your request_id.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            request_id=req_id,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=payload.model_dump(),
        )

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_exception_handler(
        request: Request, exc: RateLimitExceeded
    ) -> JSONResponse:
        req_id = getattr(request.state, "request_id", "-")
        payload = ErrorResponse(
            error="Too Many Requests",
            detail="Rate limit exceeded. Please wait before sending more requests.",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            request_id=req_id,
        )
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content=payload.model_dump(),
        )

    app.include_router(auth_router)
    app.include_router(documents_router)
    app.include_router(chat_router)
    app.include_router(metrics_router)

    @app.get(
        "/health",
        response_model=HealthResponse,
        tags=["System"],
        summary="Check service and database availability",
    )
    async def health_check(request: Request) -> HealthResponse:
        """Return service health metadata and verify SQLite connectivity."""
        db_ok = request.app.state.db.check_health()
        if not db_ok:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database health check failed.",
            )
        return HealthResponse(
            status="healthy",
            app_name=settings.app_name,
            version=settings.app_version,
            environment=settings.app_env,
            database="ok",
            timestamp=datetime.now(timezone.utc),
        )

    # Serve the frontend SPA at root — MUST be mounted last so it doesn't shadow API routes.
    _frontend = Path("frontend")
    if _frontend.is_dir():
        app.mount("/", StaticFiles(directory=str(_frontend), html=True), name="frontend")

    return app


app = create_app()
