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

from core.cache import get_cached_user_context, get_redis
from core.config import settings
from core.database import get_db
from core.security import decode_token
from db.models.user import User

logger = structlog.get_logger()

# Bearer token extractor — reads Authorization: Bearer <token> header
bearer_scheme = HTTPBearer(auto_error=True)


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
    # Decode and validate the JWT
    payload = decode_token(credentials.credentials, expected_type="access")
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

    # Fetch user from database
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
    Used for endpoints that behave differently for authenticated users.
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
    
    Free/Spark tier: 10 coach messages/day
    Forge/Identity tier: Unlimited
    
    Returns soft warning when approaching limit.
    """
    async def _check_quota(
        current_user: User = Depends(get_current_active_user),
    ) -> dict:
        from core.cache import check_and_increment_ai_rate, get_redis
        
        # Determine limit based on subscription tier
        plan = (current_user.subscription_plan or "spark").lower()
        status = (current_user.subscription_status or "inactive").lower()
        
        # Check if user has active paid subscription
        is_paid_active = (
            plan in ["forge", "identity"] and 
            status == "active"
        )
        
        if is_paid_active:
            # Paid users: unlimited, just track usage for analytics
            redis = await get_redis()
            count_key = f"ai_usage:{engine}:{current_user.id}:{datetime.now().strftime('%Y-%m-%d')}"
            count = await redis.incr(count_key)
            if count == 1:
                await redis.expire(count_key, 86400)  # 24 hours
            
            return {
                "quota_status": "unlimited",
                "count": count,
                "limit": float('inf'),
                "warning": False,
            }
        
        # Free/Spark tier: enforce 10 message limit
        FREE_DAILY_LIMIT = 10
        
        allowed, count = await check_and_increment_ai_rate(
            user_id=str(current_user.id),
            engine=engine,
            limit=FREE_DAILY_LIMIT,
        )
        
        # Calculate warning threshold (80% used)
        warning_threshold = int(FREE_DAILY_LIMIT * 0.8)
        show_warning = count >= warning_threshold and count < FREE_DAILY_LIMIT
        
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "code": "quota_exceeded",
                    "message": "You've reached your daily limit of 10 coach messages.",
                    "count": count,
                    "limit": FREE_DAILY_LIMIT,
                    "upgrade_prompt": True,
                    "upgrade_message": "Upgrade to Forge for unlimited AI coaching and deeper identity transformation.",
                    "upgrade_url": "/settings/subscription",
                },
            )
        
        return {
            "quota_status": "active",
            "count": count,
            "limit": FREE_DAILY_LIMIT,
            "warning": show_warning,
            "remaining": FREE_DAILY_LIMIT - count,
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

    Used by AI engine dependencies to get full user context.
    """
    from sqlalchemy import text

    user_id = str(current_user.id)

    # Try cache first
    cached = await get_cached_user_context(user_id)
    if cached:
        return cached

    # Build from database using the SQL function defined in migrations
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

    # Cache for 5 minutes
    from core.cache import cache_user_context
    await cache_user_context(user_id, context)

    return context


# ─── Admin Check ──────────────────────────────────────────────────────────────

async def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Dependency to require admin access.
    For now, checks if user email is in admin list.
    Later: add is_admin boolean to user model.
    """
    # List of admin emails - move to env var or database later
    ADMIN_EMAILS = [
        "coach@pelumiolawole.com",
        # Add other admin emails here
    ]
    
    if current_user.email not in ADMIN_EMAILS:
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