"""
api/routers/auth.py

Authentication endpoints:
    POST /auth/signup          — Email/password registration (NOW REQUIRES VERIFICATION)
    POST /auth/login           — Email/password login (NOW REQUIRES VERIFIED EMAIL)
    POST /auth/oauth/callback  — Google/Apple OAuth callback
    POST /auth/refresh         — Refresh access token
    POST /auth/logout          — Revoke session
    POST /auth/forgot-password — Request password reset email
    POST /auth/reset-password  — Complete password reset
    GET  /auth/me              — Get current user
    PUT  /auth/me              — Update profile
    GET  /auth/verify-email    — NEW: Verify email with token
    POST /auth/resend-verification — NEW: Resend verification email
"""

from datetime import datetime, timedelta, timezone
import secrets

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies.auth import get_current_active_user
from api.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    OAuthCallbackRequest,
    RefreshTokenRequest,
    ResetPasswordRequest,
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
from services.email import email_service

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


# ─── Email/Password Signup (MODIFIED FOR VERIFICATION) ─────────────────────────

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
    User must verify email before they can log in.
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

    # Create user with verification token
    verification_token = secrets.token_urlsafe(32)
    user = User(
        email=payload.email.lower(),
        display_name=payload.display_name,
        auth_provider=AuthProvider.EMAIL,
        hashed_password=hash_password(payload.password),
        timezone=payload.timezone,
        onboarding_status=OnboardingStatus.CREATED,
        email_verification_token=verification_token,
        email_verification_sent_at=datetime.now(timezone.utc),
        is_active=False,  # Inactive until verified
    )
    db.add(user)
    await db.flush()

    logger.info("user_signed_up", user_id=str(user.id), email=user.email)

    # Send verification email
    verification_url = f"{settings.frontend_url}/verify-email?token={verification_token}"
    await email_service.send_verification_email(
        to_email=user.email,
        first_name=user.display_name,
        verification_url=verification_url
    )

    # Store refresh token (so they can auto-login after verification)
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


# ─── Email Verification (NEW ENDPOINTS) ───────────────────────────────────────

@router.get(
    "/verify-email",
    summary="Verify email with magic link token",
)
async def verify_email(token: str, db: AsyncSession = Depends(get_db)):
    """Verify email with magic link token"""
    result = await db.execute(
        select(User).where(User.email_verification_token == token)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification link"
        )

    # Check if token is expired (24 hours)
    if user.email_verification_sent_at:
        expiry = user.email_verification_sent_at + timedelta(hours=24)
        if datetime.now(timezone.utc) > expiry:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Verification link has expired. Please request a new one."
            )

    # Check if already verified
    if user.email_verified_at:
        return {"message": "Email already verified", "verified": True}

    # Verify user
    user.email_verified_at = datetime.now(timezone.utc)
    user.is_active = True
    user.email_verification_token = None
    user.onboarding_status = OnboardingStatus.INTERVIEW_STARTED  # Ready for interview

    await db.commit()

    # Send welcome email
    await email_service.send_welcome_email(
        to_email=user.email,
        display_name=user.display_name
    )

    logger.info("email_verified", user_id=str(user.id))

    return {
        "message": "Email verified successfully",
        "verified": True,
        "redirect_to": "/interview"
    }


@router.post(
    "/resend-verification",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Resend verification email",
)
async def resend_verification(payload: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Resend verification email"""
    result = await db.execute(
        select(User).where(User.email == payload.email.lower())
    )
    user = result.scalar_one_or_none()

    # Always return success to prevent email enumeration
    if not user or user.email_verified_at:
        return {
            "status": "accepted",
            "message": "If an account exists with this email, a verification link has been sent."
        }

    # Generate new token
    user.email_verification_token = secrets.token_urlsafe(32)
    user.email_verification_sent_at = datetime.now(timezone.utc)

    await db.commit()

    # Send verification email
    verification_url = f"{settings.frontend_url}/verify-email?token={user.email_verification_token}"
    await email_service.send_verification_email(
        to_email=user.email,
        first_name=user.display_name,
        verification_url=verification_url
    )

    logger.info("verification_resent", user_id=str(user.id))

    return {
        "status": "accepted",
        "message": "If an account exists with this email, a verification link has been sent."
    }


# ─── Email/Password Login (MODIFIED TO CHECK VERIFICATION) ────────────────────

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
    Requires verified email.
    """
    # Find user
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

    # NEW: Check if email is verified
    if not user.email_verified_at:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified. Please check your email or request a new verification link."
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


# ─── OAuth Callback (UNCHANGED) ───────────────────────────────────────────────

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
    OAuth users are auto-verified (email already verified by provider).
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
        # New user — create account (auto-verified via OAuth)
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
            email_verified_at=datetime.now(timezone.utc),  # Auto-verified
            is_active=True,
        )
        db.add(user)
        await db.flush()
        logger.info("oauth_user_created", user_id=str(user.id), provider=provider_str)

        # Send welcome email for OAuth users too
        await email_service.send_welcome_email(
            to_email=user.email,
            display_name=user.display_name
        )
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


# ─── Token Refresh (UNCHANGED) ────────────────────────────────────────────────

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


# ─── Logout (UNCHANGED) ───────────────────────────────────────────────────────

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


# ─── Current User (UNCHANGED) ─────────────────────────────────────────────────

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


# ─── Password Reset (UNCHANGED) ───────────────────────────────────────────────

@router.post(
    "/forgot-password",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request password reset email",
)
async def forgot_password(
    payload: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Request a password reset email.
    Always returns 202 to prevent email enumeration attacks.
    """
    # Find user by email
    result = await db.execute(
        select(User).where(User.email == payload.email.lower())
    )
    user = result.scalar_one_or_none()

    # Generate token regardless of whether user exists (prevents enumeration)
    token = secrets.token_urlsafe(32)

    if user:
        # Only store token if user exists and has password auth
        if user.hashed_password:
            expires_at = datetime.now(timezone.utc) + timedelta(
                hours=settings.password_reset_token_expire_hours
            )

            await db.execute(
                update(User)
                .where(User.id == user.id)
                .values(
                    password_reset_token=token,
                    password_reset_expires_at=expires_at,
                    password_reset_used_at=None,
                )
            )
            await db.commit()

            # Send email (async, don't block response)
            await email_service.send_password_reset(user.email, token)

            logger.info("password_reset_requested", user_id=str(user.id))
        else:
            # OAuth user trying to reset password — log for support
            logger.warning("oauth_password_reset_attempt", 
                         user_id=str(user.id), 
                         email=user.email)

    # Always return same response to prevent enumeration
    return {
        "status": "accepted",
        "message": "If an account exists with this email, you will receive a password reset link."
    }


@router.post(
    "/reset-password",
    status_code=status.HTTP_200_OK,
    summary="Reset password using token",
)
async def reset_password(
    payload: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Complete password reset using the token from the email.
    """
    # Find user by token
    result = await db.execute(
        select(User).where(User.password_reset_token == payload.token)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token.",
        )

    # Validate token
    now = datetime.now(timezone.utc)

    if user.password_reset_used_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset link has already been used.",
        )

    if not user.password_reset_expires_at or user.password_reset_expires_at < now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token has expired. Please request a new one.",
        )

    # Update password and invalidate token
    new_hash = hash_password(payload.new_password)

    await db.execute(
        update(User)
        .where(User.id == user.id)
        .values(
            hashed_password=new_hash,
            password_reset_used_at=now,
            password_reset_token=None,  # Clear token
            password_reset_expires_at=None,
        )
    )

    # Revoke all existing sessions for security
    await revoke_refresh_token(str(user.id))

    await db.commit()

    logger.info("password_reset_completed", user_id=str(user.id))

    return {
        "status": "success",
        "message": "Password has been reset successfully. Please log in with your new password."
    }


# ─── Data Rights (UNCHANGED) ──────────────────────────────────────────────────

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


# ─── TEMPORARY ADMIN ENDPOINTS ────────────────────────────────────────────────
# TODO: Remove these endpoints after sending welcome emails to existing users

@router.post(
    "/admin/send-welcome-email",
    status_code=status.HTTP_200_OK,
    summary="TEMPORARY: Send welcome email to single user by email",
)
async def admin_send_welcome_email(
    email: str,
    db: AsyncSession = Depends(get_db),
):
    """
    TEMPORARY ADMIN ENDPOINT: Send welcome email to a specific user by email.
    TODO: Remove this endpoint after use.
    """
    result = await db.execute(
        select(User).where(User.email == email.lower())
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Only send to verified users
    if not user.email_verified_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot send welcome email: user email not verified"
        )

    try:
        await email_service.send_welcome_email(
            to_email=user.email,
            display_name=user.display_name
        )

        logger.info("admin_welcome_email_sent", user_id=str(user.id), email=user.email)

        return {
            "status": "success",
            "message": f"Welcome email sent to {user.email}",
            "user_id": str(user.id),
            "display_name": user.display_name
        }

    except Exception as e:
        logger.error("admin_welcome_email_failed", email=user.email, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send welcome email: {str(e)}"
        )


@router.post(
    "/admin/send-welcome-email-to-all",
    status_code=status.HTTP_200_OK,
    summary="TEMPORARY: Send welcome email to ALL verified users",
)
async def admin_send_welcome_email_to_all(
    confirm: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """
    TEMPORARY ADMIN ENDPOINT: Send welcome email to ALL verified users.

    This sends the welcome email to every user who has verified their email
    but may not have received the welcome email (registered before automation).

    Parameters:
        confirm: Must be set to True to actually send emails (safety check)

    TODO: Remove this endpoint after use.
    """
    # Safety check - require explicit confirmation
    if not confirm:
        # Preview mode - show how many users would receive emails
        result = await db.execute(
            select(User).where(
                User.email_verified_at.is_not(None)
            )
        )
        users = result.scalars().all()

        return {
            "status": "preview",
            "message": f"This would send welcome emails to {len(users)} verified user(s).",
            "user_count": len(users),
            "users": [
                {
                    "email": u.email,
                    "display_name": u.display_name,
                    "verified_at": u.email_verified_at.isoformat() if u.email_verified_at else None
                }
                for u in users
            ],
            "instruction": "Add '?confirm=true' to the URL to actually send the emails."
        }

    # Actually send emails
    result = await db.execute(
        select(User).where(
            User.email_verified_at.is_not(None)
        )
    )
    users = result.scalars().all()

    sent_count = 0
    failed_emails = []

    for user in users:
        try:
            await email_service.send_welcome_email(
                to_email=user.email,
                display_name=user.display_name
            )
            sent_count += 1
            logger.info("bulk_welcome_email_sent", user_id=str(user.id), email=user.email)
        except Exception as e:
            failed_emails.append({
                "email": user.email,
                "error": str(e)
            })
            logger.error("bulk_welcome_email_failed", email=user.email, error=str(e))

    return {
        "status": "completed",
        "message": f"Welcome emails sent to {sent_count} user(s).",
        "total_users": len(users),
        "sent_count": sent_count,
        "failed_count": len(failed_emails),
        "failed_emails": failed_emails
    }