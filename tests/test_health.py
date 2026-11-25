"""Tests for Milestone 1: configuration, database initialization, and /health."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.logging_config import redact_secrets
from app.main import create_app


def test_health_endpoint_returns_200_and_request_id(tmp_path: Path) -> None:
    """Verify /health returns 200 OK, healthy database status, and X-Request-ID."""
    settings = Settings(
        app_env="test",
        sqlite_db_path=str(tmp_path / "test.db"),
        upload_dir=str(tmp_path / "uploads"),
        qdrant_path=str(tmp_path / "qdrant"),
    )
    app = create_app(settings_override=settings)

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["X-Request-ID"].startswith("req_")
    body = response.json()
    assert body["status"] == "healthy"
    assert body["database"] == "ok"
    assert body["environment"] == "test"


def test_secret_redaction_masks_keys_and_tokens() -> None:
    """Verify logging redactor masks Gemini API keys and Bearer tokens."""
    sample = "key=AIzaSyDummySecretKey1234567890 api_key=mysecret and Bearer eyJhbGciOiJIUzI1NiJ9.abc"
    cleaned = redact_secrets(sample)
    assert "AIzaSyDummySecretKey1234567890" not in cleaned
    assert "mysecret" not in cleaned
    assert "eyJhbGciOiJIUzI1NiJ9.abc" not in cleaned
    assert "[REDACTED_API_KEY]" in cleaned
    assert "[REDACTED_TOKEN]" in cleaned
