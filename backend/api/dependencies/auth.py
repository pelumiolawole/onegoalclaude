"""
api/dependencies/auth.py

FastAPI dependency injection for authentication.

Usage in route handlers:
    @router.get("/me")
    async def get_me(current_user: User = Depends(get_current_user)):
        ...

    @router.post("/reflect")
    async def submit_reflection(
        current_user: User = Depends(get_current_active_user),
        db: AsyncSession = Depends(get_db),
    ):
        ...
"""

from datetime import datetime
from uuid import UUID

import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.cache import get_cached_user_context, get_redis, is_token_blocklisted
from core.config import settings
from core.database import get_db
from core.security import decode_token
from db.models.user import User

logger = structlog.get_logger()

# Bearer token extractor — reads Authorization: Bearer <token> header
bearer_scheme = HTTPBearer(auto_error=True)

# ─── Tier limits ──────────────────────────────────────────────────────────────
# Free (Spark): 5 coach messages/day
# Paid (Forge, Identity): unlimited
FREE_DAILY_COACH_LIMIT = 5


# ─── Core Auth Dependency ─────────────────────────────────────────────────────

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Primary authentication dependency.

    Validates the JWT access token and returns the full User ORM object.
    Raises 401 if:
        - Token is missing or malformed
        - Token is expired
        - User no longer exists
    """
    payload = decode_token(credentials.credentials, expected_type="access")

    # Reject blocklisted tokens (revoked on logout)
    jti = payload.get("jti")
    if jti and await is_token_blocklisted(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id_str = payload.get("sub")

    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing user identifier",
        )

    try:
        user_id = UUID(user_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user identifier in token",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Extends get_current_user with active status check.
    Use this for all routes that require a fully active account.
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Contact support to reactivate.",
        )
    return current_user


async def get_onboarded_user(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """
    Extends get_current_active_user with onboarding completion check.
    Use for routes that require a fully onboarded user (goal, tasks, coach).
    """
    from db.models.user import OnboardingStatus

    if current_user.onboarding_status != OnboardingStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "onboarding_incomplete",
                "message": "Please complete onboarding first.",
                "onboarding_status": current_user.onboarding_status.value,
            },
        )
    return current_user


# ─── Optional Auth ────────────────────────────────────────────────────────────

optional_bearer = HTTPBearer(auto_error=False)


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_bearer),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """
    Auth dependency that doesn't require authentication.
    Returns the user if token is valid, None if no token provided.
    """
    if credentials is None:
        return None
    try:
        return await get_current_user(credentials, db)
    except HTTPException:
        return None


# ─── AI Rate Limit Check ──────────────────────────────────────────────────────

def require_ai_quota(engine: str):
    """
    Factory function that returns a dependency checking AI usage quota
    based on subscription tier.

    Free (Spark): 5 coach messages/day
    Forge / Identity: Unlimited

    Returns soft warning when approaching limit.
    """
    async def _check_quota(
        current_user: User = Depends(get_current_active_user),
    ) -> dict:
        from core.cache import check_and_increment_ai_rate, get_redis

        plan = (current_user.subscription_plan or "spark").lower()
        sub_status = (current_user.subscription_status or "inactive").lower()

        is_paid_active = (
            plan in ["forge", "identity"] and
            sub_status == "active"
        )

        if is_paid_active:
            # Paid users: unlimited — just track for analytics
            redis = await get_redis()
            count_key = f"ai_usage:{engine}:{current_user.id}:{datetime.now().strftime('%Y-%m-%d')}"
            count = await redis.incr(count_key)
            if count == 1:
                await redis.expire(count_key, 86400)

            return {
                "quota_status": "unlimited",
                "count": count,
                "limit": float('inf'),
                "warning": False,
            }

        # Free (Spark) tier: 5 messages/day
        allowed, count = await check_and_increment_ai_rate(
            user_id=str(current_user.id),
            engine=engine,
            limit=FREE_DAILY_COACH_LIMIT,
        )

        warning_threshold = int(FREE_DAILY_COACH_LIMIT * 0.8)  # warn at 4/5
        show_warning = count >= warning_threshold and count < FREE_DAILY_COACH_LIMIT

        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "code": "quota_exceeded",
                    "message": f"You've reached your daily limit of {FREE_DAILY_COACH_LIMIT} coach messages.",
                    "count": count,
                    "limit": FREE_DAILY_COACH_LIMIT,
                    "upgrade_prompt": True,
                    "upgrade_message": "Upgrade to The Forge for unlimited AI coaching.",
                    "upgrade_url": "/settings/upgrade",
                },
            )

        return {
            "quota_status": "active",
            "count": count,
            "limit": FREE_DAILY_COACH_LIMIT,
            "warning": show_warning,
            "remaining": FREE_DAILY_COACH_LIMIT - count,
        }

    return _check_quota


# ─── User Context Provider ────────────────────────────────────────────────────

async def get_user_ai_context(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Returns the assembled AI context for the current user.
    Checks Redis cache first (5 min TTL) before hitting the database.
    """
    from sqlalchemy import text

    user_id = str(current_user.id)

    cached = await get_cached_user_context(user_id)
    if cached:
        return cached

    result = await db.execute(
        text("SELECT get_user_ai_context(:user_id)"),
        {"user_id": user_id},
    )
    context = result.scalar()

    if context is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User context not found",
        )

    from core.cache import cache_user_context
    await cache_user_context(user_id, context)

    return context


# ─── Admin Check ──────────────────────────────────────────────────────────────

async def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Dependency to require admin access.
    Admin emails are configured via the ADMIN_EMAILS environment variable.
    """
    if current_user.email.lower() not in settings.admin_emails_list:
        logger.warning(
            "admin_access_denied",
            user_id=str(current_user.id),
            email=current_user.email,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    return current_user