"""Structured logging configuration with secret redaction."""

import logging
import re
from contextvars import ContextVar

# Context variable to propagate a per-request ID through all log records.
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

_SECRET_PATTERNS = [
    re.compile(r"(AIza[0-9A-Za-z\-_]{20,})"),
    re.compile(r"(Bearer\s+[A-Za-z0-9\-._~+/]+=*)", re.IGNORECASE),
    re.compile(r"(api[_-]?key\s*[=:]\s*)\S+", re.IGNORECASE),
]


def redact_secrets(message: str) -> str:
    """Mask API keys and bearer tokens before writing log lines."""
    masked = message
    masked = _SECRET_PATTERNS[0].sub("[REDACTED_API_KEY]", masked)
    masked = _SECRET_PATTERNS[1].sub("Bearer [REDACTED_TOKEN]", masked)
    masked = _SECRET_PATTERNS[2].sub(r"\1[REDACTED]", masked)
    return masked


class RequestContextFilter(logging.Filter):
    """Inject the current request_id and redact sensitive patterns."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get("-")
        if isinstance(record.msg, str):
            record.msg = redact_secrets(record.msg)
        return True


def configure_logging(level: str = "INFO") -> None:
    """Configure application-wide logging once at startup."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | req=%(request_id)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    handler.addFilter(RequestContextFilter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(numeric_level)
    root_logger.addHandler(handler)
