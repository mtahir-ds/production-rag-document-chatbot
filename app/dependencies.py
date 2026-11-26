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


def get_current_user_id() -> str:
    """Return the active user ID (upgraded to JWT verification in Milestone 5)."""
    return DEFAULT_USER_ID
