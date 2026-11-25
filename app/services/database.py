"""SQLite persistence layer for users, document registry, and request metrics."""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


class DatabaseManager:
    """Manages SQLite schema initialization and thread-safe connections."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Yield a SQLite connection with row mapping and WAL concurrency enabled."""
        conn = sqlite3.connect(self.db_path, timeout=15.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA foreign_keys=ON;")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self) -> None:
        """Create required tables and indexes if they do not already exist."""
        with self.connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    username TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS documents (
                    document_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    file_type TEXT NOT NULL,
                    file_size_bytes INTEGER NOT NULL,
                    file_hash TEXT NOT NULL,
                    page_count INTEGER NOT NULL DEFAULT 0,
                    chunk_count INTEGER NOT NULL DEFAULT 0,
                    storage_path TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'ingested',
                    created_at TEXT NOT NULL,
                    UNIQUE (user_id, file_hash)
                );

                CREATE INDEX IF NOT EXISTS idx_documents_user
                    ON documents (user_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS request_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL,
                    user_id TEXT,
                    endpoint TEXT NOT NULL,
                    method TEXT NOT NULL,
                    status_code INTEGER NOT NULL,
                    latency_ms REAL NOT NULL,
                    retrieval_ms REAL NOT NULL DEFAULT 0.0,
                    llm_ms REAL NOT NULL DEFAULT 0.0,
                    prompt_tokens INTEGER NOT NULL DEFAULT 0,
                    completion_tokens INTEGER NOT NULL DEFAULT 0,
                    estimated_cost_usd REAL NOT NULL DEFAULT 0.0,
                    error_message TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_metrics_created
                    ON request_metrics (created_at DESC);
                """
            )

    def check_health(self) -> bool:
        """Verify database connectivity by executing a lightweight query."""
        with self.connection() as conn:
            row = conn.execute("SELECT 1 AS ok;").fetchone()
            return bool(row and row["ok"] == 1)

    def record_request_metric(
        self,
        *,
        request_id: str,
        user_id: str | None,
        endpoint: str,
        method: str,
        status_code: int,
        latency_ms: float,
        retrieval_ms: float = 0.0,
        llm_ms: float = 0.0,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        estimated_cost_usd: float = 0.0,
        error_message: str | None = None,
    ) -> None:
        """Persist a single API request trace for observability reporting."""
        now = datetime.now(timezone.utc).isoformat()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO request_metrics (
                    request_id, user_id, endpoint, method, status_code,
                    latency_ms, retrieval_ms, llm_ms, prompt_tokens,
                    completion_tokens, estimated_cost_usd, error_message, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    request_id,
                    user_id,
                    endpoint,
                    method,
                    status_code,
                    round(latency_ms, 2),
                    round(retrieval_ms, 2),
                    round(llm_ms, 2),
                    prompt_tokens,
                    completion_tokens,
                    round(estimated_cost_usd, 8),
                    error_message,
                    now,
                ),
            )
