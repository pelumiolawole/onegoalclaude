"""
api/routers/auth.py

Authentication endpoints:
    POST /auth/signup          — Email/password registration
    POST /auth/login           — Email/password login
    POST /auth/oauth/callback  — Google/Apple OAuth callback
    POST /auth/refresh         — Refresh access token
    POST /auth/logout          — Revoke session
    POST /auth/forgot-password — Request password reset email
    POST /auth/reset-password  — Complete password reset
    GET  /auth/me              — Get current user
    PUT  /auth/me              — Update profile
"""

from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies.auth import get_current_active_user
from api.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    OAuthCallbackRequest,
    RefreshTokenRequest,
    SignUpRequest,
    TokenResponse,
    UserSummary,
)
from core.cache import (
    get_refresh_token,
    invalidate_user_context,
    revoke_refresh_token,
    store_refresh_token,
)
from core.config import settings
from core.database import get_db
from core.security import (
    create_token_pair,
    decode_token,
    hash_password,
    verify_password,
    verify_supabase_token,
)
from db.models.user import AuthProvider, OnboardingStatus, User

logger = structlog.get_logger()

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ─── Helper ───────────────────────────────────────────────────────────────────

def _build_token_response(user: User) -> TokenResponse:
    """Build the standard token response after any successful auth."""
    tokens = create_token_pair(
        user_id=user.id,
        extra_claims={
            "onboarding_status": user.onboarding_status.value,
            "onboarding_step": user.onboarding_step,
        },
    )
    return TokenResponse(
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        token_type="bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        user=UserSummary.model_validate(user),
    )


# ─── Email/Password Signup ────────────────────────────────────────────────────

@router.post(
    "/signup",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register with email and password",
)
async def signup(
    payload: SignUpRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Create a new account with email and password.
    Automatically creates identity_profile and onboarding_state
    via database triggers (see migration 001).
    """
    # Check for existing account
    existing = await db.execute(
        select(User).where(User.email == payload.email.lower())
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    # Create user
    user = User(
        email=payload.email.lower(),
        display_name=payload.display_name,
        auth_provider=AuthProvider.EMAIL,
        hashed_password=hash_password(payload.password),
        timezone=payload.timezone,
        onboarding_status=OnboardingStatus.CREATED,
    )
    db.add(user)
    await db.flush()  # Get the generated ID before commit

    logger.info("user_signed_up", user_id=str(user.id), email=user.email)

    # Store refresh token in Redis
    tokens = create_token_pair(
        user_id=user.id,
        extra_claims={"onboarding_status": user.onboarding_status.value},
    )
    await store_refresh_token(str(user.id), tokens["refresh_token"])

    await db.commit()
    await db.refresh(user)

    return TokenResponse(
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        token_type="bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        user=UserSummary.model_validate(user),
    )


# ─── Email/Password Login ─────────────────────────────────────────────────────

@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login with email and password",
)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Authenticate with email and password.
    Returns access + refresh tokens on success.
    """
    # Find user — use consistent error message to prevent email enumeration
    result = await db.execute(
        select(User).where(User.email == payload.email.lower())
    )
    user = result.scalar_one_or_none()

    if not user or not user.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )

    if not verify_password(payload.password, user.hashed_password):
        logger.warning("failed_login_attempt", email=payload.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated.",
        )

    # Update last seen
    await db.execute(
        update(User)
        .where(User.id == user.id)
        .values(last_seen_at=datetime.now(timezone.utc))
    )

    # Rotate refresh token on login
    tokens = create_token_pair(
        user_id=user.id,
        extra_claims={
            "onboarding_status": user.onboarding_status.value,
            "onboarding_step": user.onboarding_step,
        },
    )
    await store_refresh_token(str(user.id), tokens["refresh_token"])

    logger.info("user_logged_in", user_id=str(user.id))

    return TokenResponse(
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        token_type="bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        user=UserSummary.model_validate(user),
    )


# ─── OAuth Callback (Google / Apple) ─────────────────────────────────────────

@router.post(
    "/oauth/callback",
    response_model=TokenResponse,
    summary="Complete OAuth login (Google or Apple)",
)
async def oauth_callback(
    payload: OAuthCallbackRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Called by the frontend after Google/Apple OAuth completes via Supabase.
    Flow:
        1. User authenticates with Google/Apple via Supabase on the frontend
        2. Frontend sends us the Supabase token
        3. We verify it, find/create our own user record
        4. Return our own JWT pair

    This decouples our auth from Supabase — we use Supabase only for
    the OAuth handshake, then issue our own tokens.
    """
    if not settings.feature_google_auth and not settings.feature_apple_auth:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="OAuth is not enabled.",
        )

    # Verify the Supabase token and extract user info
    supabase_user = await verify_supabase_token(payload.supabase_token)

    email = supabase_user["email"]
    provider_str = supabase_user["provider"]
    provider_id = supabase_user["id"]
    user_metadata = supabase_user.get("user_metadata", {})

    # Map Supabase provider to our enum
    try:
        provider = AuthProvider(provider_str)
    except ValueError:
        provider = AuthProvider.EMAIL

    # Find existing user or create new one
    result = await db.execute(select(User).where(User.email == email.lower()))
    user = result.scalar_one_or_none()

    if user is None:
        # New user — create account
        display_name = (
            payload.display_name
            or user_metadata.get("full_name")
            or user_metadata.get("name")
        )
        user = User(
            email=email.lower(),
            display_name=display_name,
            avatar_url=user_metadata.get("avatar_url") or user_metadata.get("picture"),
            auth_provider=provider,
            auth_provider_id=provider_id,
            timezone=payload.timezone,
            onboarding_status=OnboardingStatus.CREATED,
        )
        db.add(user)
        await db.flush()
        logger.info("oauth_user_created", user_id=str(user.id), provider=provider_str)
    else:
        # Existing user — update provider info if needed
        if user.auth_provider_id != provider_id:
            user.auth_provider = provider
            user.auth_provider_id = provider_id
        user.last_seen_at = datetime.now(timezone.utc)
        logger.info("oauth_user_logged_in", user_id=str(user.id))

    tokens = create_token_pair(
        user_id=user.id,
        extra_claims={
            "onboarding_status": user.onboarding_status.value,
            "onboarding_step": user.onboarding_step,
        },
    )
    await store_refresh_token(str(user.id), tokens["refresh_token"])
    await db.commit()
    await db.refresh(user)

    return TokenResponse(
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        token_type="bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        user=UserSummary.model_validate(user),
    )


# ─── Token Refresh ────────────────────────────────────────────────────────────

@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh access token using refresh token",
)
async def refresh_token(
    payload: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Exchange a valid refresh token for a new access + refresh token pair.
    Implements refresh token rotation — old token is invalidated.
    """
    # Validate the refresh token
    token_payload = decode_token(payload.refresh_token, expected_type="refresh")
    user_id = token_payload.get("sub")

    # Verify it matches what we stored in Redis (prevents token reuse)
    stored_token = await get_refresh_token(user_id)
    if not stored_token or stored_token != payload.refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is invalid or has been revoked.",
        )

    # Get current user
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        await revoke_refresh_token(user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or deactivated.",
        )

    # Issue new token pair (rotation)
    tokens = create_token_pair(
        user_id=user.id,
        extra_claims={
            "onboarding_status": user.onboarding_status.value,
            "onboarding_step": user.onboarding_step,
        },
    )
    await store_refresh_token(str(user.id), tokens["refresh_token"])

    logger.info("token_refreshed", user_id=str(user.id))

    return TokenResponse(
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        token_type="bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        user=UserSummary.model_validate(user),
    )


# ─── Logout ───────────────────────────────────────────────────────────────────

@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Logout and revoke session",
)
async def logout(
    current_user: User = Depends(get_current_active_user),
) -> None:
    """
    Revoke the user's refresh token.
    The access token remains technically valid until it expires (24h),
    but without a refresh token, the session cannot be extended.
    """
    await revoke_refresh_token(str(current_user.id))
    await invalidate_user_context(str(current_user.id))
    logger.info("user_logged_out", user_id=str(current_user.id))


# ─── Current User ─────────────────────────────────────────────────────────────

@router.get(
    "/me",
    response_model=UserSummary,
    summary="Get current authenticated user",
)
async def get_me(
    current_user: User = Depends(get_current_active_user),
) -> UserSummary:
    """Return the current user's profile summary."""
    return UserSummary.model_validate(current_user)


@router.put(
    "/me",
    response_model=UserSummary,
    summary="Update current user profile",
)
async def update_me(
    payload: dict,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> UserSummary:
    """
    Update display_name, timezone, or locale.
    Email and auth provider changes are handled separately.
    """
    allowed_fields = {"display_name", "timezone", "locale"}
    updates = {k: v for k, v in payload.items() if k in allowed_fields}

    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid fields to update.",
        )

    await db.execute(
        update(User).where(User.id == current_user.id).values(**updates)
    )
    await db.commit()
    await db.refresh(current_user)

    logger.info("user_profile_updated", user_id=str(current_user.id), fields=list(updates.keys()))

    return UserSummary.model_validate(current_user)


@router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Change password for email auth users",
)
async def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Change password. Requires current password for verification."""
    if not current_user.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password change is not available for OAuth accounts.",
        )

    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect.",
        )

    new_hash = hash_password(payload.new_password)
    await db.execute(
        update(User)
        .where(User.id == current_user.id)
        .values(hashed_password=new_hash)
    )
    # Revoke all existing sessions after password change
    await revoke_refresh_token(str(current_user.id))

    logger.info("password_changed", user_id=str(current_user.id))


# ─── Data Rights ──────────────────────────────────────────────────────────────

@router.get(
    "/export",
    summary="Export all personal data (GDPR)",
)
async def export_data(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Export all personal data as JSON.
    Calls the export_user_data() SQL function from migration 004.
    This satisfies GDPR Article 20 (right to data portability).
    """
    from sqlalchemy import text

    result = await db.execute(
        text("SELECT export_user_data(:user_id)"),
        {"user_id": str(current_user.id)},
    )
    data = result.scalar()
    logger.info("data_exported", user_id=str(current_user.id))
    return data


@router.delete(
    "/account",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete account and all data (GDPR)",
)
async def delete_account(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Permanently delete account and all associated data.
    This is irreversible. Calls delete_user_data() from migration 004.
    """
    from sqlalchemy import text

    user_id = str(current_user.id)
    await revoke_refresh_token(user_id)
    await invalidate_user_context(user_id)

    await db.execute(
        text("SELECT delete_user_data(:user_id)"),
        {"user_id": user_id},
    )
    await db.commit()

    logger.info("account_deleted", user_id=user_id)
