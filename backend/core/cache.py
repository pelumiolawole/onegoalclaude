"""
core/cache.py

Redis client for session caching, AI rate limiting, and job state.
Uses redis.asyncio for non-blocking operations.

Namespacing convention:
    ongoal:{namespace}:{key}

Namespaces:
    session:    JWT refresh token tracking
    ratelimit:  AI engine call counting
    context:    Cached user AI context (TTL: 5 min)
    lock:       Distributed locks for background jobs
"""

from typing import Any

import redis.asyncio as aioredis

from core.config import settings

# ─── Client ──────────────────────────────────────────────────────────────────

_redis_client: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """
    Returns a singleton Redis client.
    Connection is lazy — first call establishes the pool.
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            str(settings.redis_url),
            encoding="utf-8",
            decode_responses=True,
            max_connections=20,
        )
    return _redis_client


async def close_redis() -> None:
    """Called at app shutdown."""
    global _redis_client
    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None


# ─── Namespaced Key Helpers ───────────────────────────────────────────────────

def _key(namespace: str, identifier: str) -> str:
    return f"ongoal:{namespace}:{identifier}"


# ─── Session Operations ──────────────────────────────────────────────────────

async def store_refresh_token(user_id: str, token: str) -> None:
    """Store a refresh token with TTL matching JWT config."""
    r = await get_redis()
    ttl = settings.jwt_refresh_token_expire_days * 86400
    await r.setex(_key("session", user_id), ttl, token)


async def get_refresh_token(user_id: str) -> str | None:
    """Retrieve stored refresh token for validation."""
    r = await get_redis()
    return await r.get(_key("session", user_id))


async def revoke_refresh_token(user_id: str) -> None:
    """Revoke refresh token on logout or password change."""
    r = await get_redis()
    await r.delete(_key("session", user_id))


# ─── AI Rate Limiting ────────────────────────────────────────────────────────

async def check_and_increment_ai_rate(
    user_id: str,
    engine: str,
    limit: int,
    window_seconds: int = 86400,  # default: daily window
) -> tuple[bool, int]:
    """
    Check and increment AI call counter for a user+engine combination.

    Returns:
        (allowed: bool, current_count: int)

    Uses an atomic Lua script to prevent race conditions.
    """
    r = await get_redis()
    key = _key("ratelimit", f"{user_id}:{engine}")

    # Lua script: increment counter, set TTL if new, return count
    lua_script = """
    local current = redis.call('INCR', KEYS[1])
    if current == 1 then
        redis.call('EXPIRE', KEYS[1], ARGV[1])
    end
    return current
    """
    count = await r.eval(lua_script, 1, key, window_seconds)
    return count <= limit, int(count)


async def get_ai_usage(user_id: str, engine: str) -> int:
    """Get current AI usage count for a user+engine today."""
    r = await get_redis()
    key = _key("ratelimit", f"{user_id}:{engine}")
    count = await r.get(key)
    return int(count) if count else 0


# ─── User Context Cache ──────────────────────────────────────────────────────

async def cache_user_context(user_id: str, context: dict[str, Any]) -> None:
    """
    Cache the assembled user AI context for 5 minutes.
    Avoids re-running the expensive get_user_ai_context() SQL function
    on every coach message in a session.
    """
    import json
    r = await get_redis()
    await r.setex(
        _key("context", user_id),
        300,  # 5 minute TTL
        json.dumps(context, default=str),
    )


async def get_cached_user_context(user_id: str) -> dict[str, Any] | None:
    """Retrieve cached user context, returns None if expired or missing."""
    import json
    r = await get_redis()
    data = await r.get(_key("context", user_id))
    return json.loads(data) if data else None


async def invalidate_user_context(user_id: str) -> None:
    """
    Invalidate context cache when profile is updated.
    Called after: reflection submission, task completion, trait update.
    """
    r = await get_redis()
    await r.delete(_key("context", user_id))


# ─── Distributed Locks ───────────────────────────────────────────────────────

async def acquire_lock(resource: str, ttl_seconds: int = 60) -> bool:
    """
    Acquire a distributed lock for background jobs.
    Prevents multiple workers from running the same job simultaneously.

    Returns True if lock was acquired, False if already held.
    """
    r = await get_redis()
    result = await r.set(
        _key("lock", resource),
        "1",
        nx=True,       # Only set if not exists
        ex=ttl_seconds,
    )
    return result is True


async def release_lock(resource: str) -> None:
    """Release a distributed lock after job completes."""
    r = await get_redis()
    await r.delete(_key("lock", resource))


# ─── Access Token Blocklist ──────────────────────────────────────────────────

async def blocklist_access_token(jti: str, ttl_seconds: int) -> None:
    """
    Add a JWT access token's JTI to the blocklist.
    Called on logout so the token cannot be reused before it expires.

    TTL should equal the token's remaining lifetime so the blocklist
    entry auto-expires at the same time as the token itself.
    """
    r = await get_redis()
    await r.setex(_key("blocklist", jti), max(ttl_seconds, 1), "1")


async def is_token_blocklisted(jti: str) -> bool:
    """
    Check whether a JWT access token has been blocklisted.
    Called on every authenticated request in get_current_user().
    """
    r = await get_redis()
    return bool(await r.exists(_key("blocklist", jti)))
