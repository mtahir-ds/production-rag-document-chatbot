"""Rate limiting configuration using slowapi."""

from slowapi import Limiter
from slowapi.util import get_remote_address

# Shared limiter instance attached to FastAPI app.state.limiter.
limiter = Limiter(key_func=get_remote_address)
