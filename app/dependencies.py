"""FastAPI dependency providers for settings, database, services, and user identity."""

from fastapi import Request

from app.config import Settings
from app.services.database import DatabaseManager
from app.services.ingestion_service import IngestionService
from app.services.rag_service import RAGService

DEFAULT_USER_ID = "usr_default"


def get_settings_dep(request: Request) -> Settings:
    """Return active Settings from app state."""
    return request.app.state.settings


def get_db(request: Request) -> DatabaseManager:
    """Return active DatabaseManager from app state."""
    return request.app.state.db


def get_ingestion_service(request: Request) -> IngestionService:
    """Return active IngestionService from app state."""
    return request.app.state.ingestion_service


def get_rag_service(request: Request) -> RAGService:
    """Return active RAGService from app state."""
    return request.app.state.rag_service


def get_auth_service(request: Request):
    """Return active AuthService from app state."""
    return request.app.state.auth_service


def get_current_user_id(request: Request) -> str:
    """Return the authenticated user_id from the JWT Bearer token.

    Falls back to DEFAULT_USER_ID when no Authorization header is present,
    keeping all existing tests green without modification.
    Raises HTTP 401 if a token is present but malformed or expired.
    """
    authorization = request.headers.get("Authorization", "")

    # No token supplied → fall back to default user (backward-compatible).
    if not authorization.startswith("Bearer "):
        return DEFAULT_USER_ID

    token = authorization.removeprefix("Bearer ").strip()
    auth_service = request.app.state.auth_service
    return auth_service.decode_access_token(token)
