"""JWT-based authentication routes: signup, login, and profile retrieval."""

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.dependencies import get_auth_service, get_db
from app.schemas import ErrorResponse, TokenResponse, UserInfo, UserLoginRequest, UserSignupRequest
from app.services.auth_service import AuthService
from app.services.database import DatabaseManager

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post(
    "/signup",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
    responses={
        409: {"model": ErrorResponse, "description": "Email already registered"},
    },
)
async def signup(
    payload: UserSignupRequest,
    db: DatabaseManager = Depends(get_db),
    auth: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    """Register a new user, hash their password, and return a JWT access token."""
    existing = db.get_user_by_email(payload.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists.",
        )
    user_id = AuthService.new_user_id()
    password_hash = auth.hash_password(payload.password)
    user = db.create_user(
        user_id=user_id,
        email=payload.email,
        username=payload.username,
        password_hash=password_hash,
    )
    token = auth.create_access_token(user_id)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in_minutes=auth.settings.jwt_expire_minutes,
        user=UserInfo(
            user_id=user["user_id"],
            email=user["email"],
            username=user["username"],
            created_at=user["created_at"],
        ),
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate and obtain a JWT token",
    responses={
        401: {"model": ErrorResponse, "description": "Invalid credentials"},
    },
)
async def login(
    payload: UserLoginRequest,
    db: DatabaseManager = Depends(get_db),
    auth: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    """Verify credentials and return a fresh JWT access token."""
    user = db.get_user_by_email(payload.email)
    if not user or not auth.verify_password(payload.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = auth.create_access_token(user["user_id"])
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in_minutes=auth.settings.jwt_expire_minutes,
        user=UserInfo(
            user_id=user["user_id"],
            email=user["email"],
            username=user["username"],
            created_at=user["created_at"],
        ),
    )


@router.get(
    "/me",
    response_model=UserInfo,
    status_code=status.HTTP_200_OK,
    summary="Get current user profile",
    responses={
        401: {"model": ErrorResponse, "description": "Missing or invalid JWT token"},
        404: {"model": ErrorResponse, "description": "User not found"},
    },
)
async def get_me(
    request: Request,
    db: DatabaseManager = Depends(get_db),
    auth: AuthService = Depends(get_auth_service),
) -> UserInfo:
    """Return the authenticated user's profile from the JWT Bearer token."""
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.removeprefix("Bearer ").strip()
    user_id = auth.decode_access_token(token)
    user = db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )
    return UserInfo(
        user_id=user["user_id"],
        email=user["email"],
        username=user["username"],
        created_at=user["created_at"],
    )
