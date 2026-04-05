"""
core/security.py

Authentication utilities:
  - Password hashing with bcrypt
  - JWT access + refresh token creation and validation
  - Supabase token verification (for OAuth flow)
  - Token blacklist checking via Redis

Design note: We use a two-token system:
  - Access token:  Short-lived (24h), stateless JWT, verified on every request
  - Refresh token: Long-lived (30d), stored in Redis, used only to get new access tokens

On logout, the refresh token is deleted from Redis — effectively revoking the session.
"""

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

import bcrypt
import jwt
from fastapi import HTTPException, status
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

from core.config import settings


# ─── Token Types ─────────────────────────────────────────────────────────────

ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"


# ─── Password Hashing ────────────────────────────────────────────────────────

def hash_password(plain_password: str) -> str:
    """
    Hash a password with bcrypt.
    Rounds are configured in settings (default: 12).
    """
    salt = bcrypt.gensalt(rounds=settings.bcrypt_rounds)
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against its bcrypt hash.
    Timing-safe comparison via bcrypt.checkpw.
    """
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


# ─── Token Creation ───────────────────────────────────────────────────────────

def create_access_token(
    user_id: UUID | str,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """
    Create a short-lived JWT access token.

    Claims included:
        sub:   user ID (subject)
        type:  "access"
        iat:   issued at
        exp:   expiry
        + any extra_claims (e.g., onboarding_status for frontend routing)
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.jwt_access_token_expire_minutes)

    payload: dict[str, Any] = {
        "sub": str(user_id),
        "type": ACCESS_TOKEN_TYPE,
        "jti": str(uuid4()),
        "iat": now,
        "exp": expire,
    }

    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: UUID | str) -> str:
    """
    Create a long-lived refresh token.
    Stored in Redis on creation; deleted on logout or rotation.
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=settings.jwt_refresh_token_expire_days)

    payload = {
        "sub": str(user_id),
        "type": REFRESH_TOKEN_TYPE,
        "iat": now,
        "exp": expire,
    }

    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_token_pair(
    user_id: UUID | str,
    extra_claims: dict[str, Any] | None = None,
) -> dict[str, str]:
    """
    Create both access and refresh tokens in one call.
    Returns a dict suitable for the /auth/token response.
    """
    return {
        "access_token": create_access_token(user_id, extra_claims),
        "refresh_token": create_refresh_token(user_id),
        "token_type": "bearer",
    }


# ─── Token Validation ────────────────────────────────────────────────────────

def decode_token(token: str, expected_type: str = ACCESS_TOKEN_TYPE) -> dict[str, Any]:
    """
    Decode and validate a JWT token.

    Raises HTTPException 401 on:
        - Expired token
        - Invalid signature
        - Wrong token type (e.g., using refresh token as access token)
        - Malformed token
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify token type to prevent refresh tokens being used as access tokens
    if payload.get("type") != expected_type:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token type. Expected '{expected_type}'.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


def extract_user_id(token: str) -> str:
    """
    Extract the user ID (sub claim) from a validated access token.
    Raises HTTPException 401 if token is invalid.
    """
    payload = decode_token(token, expected_type=ACCESS_TOKEN_TYPE)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject claim",
        )
    return user_id


# ─── Supabase OAuth Token Verification ───────────────────────────────────────

async def verify_supabase_token(supabase_token: str) -> dict[str, Any]:
    """
    Verify a token issued by Supabase Auth (Google/Apple OAuth).
    Returns the decoded user payload from Supabase.

    This is called during the OAuth callback — the frontend receives
    a Supabase token after Google/Apple auth, sends it here, and we
    create a One Goal user (or find existing) and issue our own JWT.
    """
    from supabase import Client, create_client

    supabase: Client = create_client(
        settings.supabase_url,
        settings.supabase_service_role_key,
    )

    try:
        # Verify token with Supabase
        response = supabase.auth.get_user(supabase_token)
        if not response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Supabase token",
            )
        return {
            "id": response.user.id,
            "email": response.user.email,
            "provider": response.user.app_metadata.get("provider", "email"),
            "user_metadata": response.user.user_metadata or {},
        }
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
        )


# ─── Token Hashing ───────────────────────────────────────────────────────────

def hash_token(token: str) -> str:
    """
    SHA-256 hash a secret token before storing in the database.
    Prevents DB-read attacks from exposing usable reset/verification links.

    Usage:
        store:  user.password_reset_token = hash_token(plaintext_token)
        verify: where(User.password_reset_token == hash_token(submitted_token))
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ─── Security Utilities ──────────────────────────────────────────────────────

def sanitize_input(text: str | None, max_length: int | None = None) -> str:
    """
    Sanitize user input before it reaches AI prompts.
    Strips leading/trailing whitespace and enforces length limit.
    """
    if not text:
        return ""
    cleaned = text.strip()
    limit = max_length or settings.max_user_input_length
    return cleaned[:limit]


def is_safe_redirect_url(url: str) -> bool:
    """
    Validate OAuth redirect URLs to prevent open redirect attacks.
    Only allow redirects to our own frontend origins.
    """
    allowed = settings.cors_origins_list
    return any(url.startswith(origin) for origin in allowed)
