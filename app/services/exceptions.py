"""Custom domain exceptions for external service failures."""


class ExternalServiceError(Exception):
    """Raised when an external API (Gemini or Qdrant) fails or times out."""

    def __init__(self, service: str, detail: str) -> None:
        self.service = service
        self.detail = detail
        super().__init__(f"{service}: {detail}")
