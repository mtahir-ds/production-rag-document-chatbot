"""JWT authentication service: token creation, verification, and bcrypt password hashing."""

import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import HTTPException, status

from app.config import Settings


class AuthService:
    """Handles JWT token lifecycle and bcrypt password operations."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    # --- Password helpers ---

    def hash_password(self, plain: str) -> str:
        """Return a bcrypt hash of the given plaintext password."""
        return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()

    def verify_password(self, plain: str, hashed: str) -> bool:
        """Return True if the plaintext matches the stored bcrypt hash."""
        return bcrypt.checkpw(plain.encode(), hashed.encode())

    # --- JWT helpers ---

    def create_access_token(self, user_id: str) -> str:
        """Create a signed JWT access token for the given user_id."""
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=self.settings.jwt_expire_minutes
        )
        payload = {
            "sub": user_id,
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "jti": uuid.uuid4().hex,
        }
        return jwt.encode(
            payload,
            self.settings.jwt_secret_key,
            algorithm=self.settings.jwt_algorithm,
        )

    def decode_access_token(self, token: str) -> str:
        """Decode and validate a JWT token; return the user_id (sub claim)."""
        try:
            payload = jwt.decode(
                token,
                self.settings.jwt_secret_key,
                algorithms=[self.settings.jwt_algorithm],
            )
            user_id: str | None = payload.get("sub")
            if not user_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token: missing subject.",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return user_id
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.InvalidTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or malformed token.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # --- New user ID generator ---

    @staticmethod
    def new_user_id() -> str:
        """Generate a unique user_id string."""
        return f"usr_{uuid.uuid4().hex[:12]}"
