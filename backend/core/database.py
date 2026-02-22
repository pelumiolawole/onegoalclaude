"""
core/database.py

Async PostgreSQL connection pool using SQLAlchemy 2.0 + asyncpg.
All database operations in this app are async — never use the
synchronous session in API handlers.

Usage in route handlers:
    async def my_route(db: AsyncSession = Depends(get_db)):
        result = await db.execute(select(User).where(User.id == user_id))
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from core.config import settings


class Base(DeclarativeBase):
    """
    SQLAlchemy declarative base.
    All ORM models inherit from this.
    """
    pass


# ─── Engine ─────────────────────────────────────────────────────────────────

def _create_engine() -> AsyncEngine:
    """
    Create the async engine with appropriate settings per environment.
    In testing, NullPool prevents connection leaks between test cases.
    """
    kwargs: dict = {
        "echo": settings.debug,           # log SQL in development
        "pool_size": settings.database_pool_size,
        "max_overflow": settings.database_max_overflow,
        "pool_timeout": settings.database_pool_timeout,
        "pool_pre_ping": True,            # verify connections before use
        "pool_recycle": 3600,             # recycle connections every hour
    }

    if settings.environment == "testing":
        # NullPool for tests: each connection is independent
        kwargs = {"echo": True, "poolclass": NullPool}

    return create_async_engine(settings.async_database_url, **kwargs)


engine: AsyncEngine = _create_engine()

# ─── Session Factory ────────────────────────────────────────────────────────

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,  # prevent lazy-load errors after commit
)


# ─── Dependencies ────────────────────────────────────────────────────────────

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that provides a database session per request.
    Session is committed on success, rolled back on any exception,
    and always closed at the end of the request.

    Example:
        @router.get("/users/{id}")
        async def get_user(id: UUID, db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager version for use outside of FastAPI request context.
    Used by background jobs and scheduled tasks.

    Example:
        async with get_db_context() as db:
            await db.execute(...)
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ─── Lifecycle ───────────────────────────────────────────────────────────────

async def init_db() -> None:
    """
    Called at application startup.
    Does NOT run migrations — use Alembic for that.
    Just verifies the connection and pgvector extension.
    """
    from sqlalchemy import text

    async with engine.begin() as conn:
        # Verify connection
        await conn.execute(text("SELECT 1"))

        # Verify pgvector is installed
        result = await conn.execute(
            text("SELECT COUNT(*) FROM pg_extension WHERE extname = 'vector'")
        )
        count = result.scalar()
        if count == 0:
            raise RuntimeError(
                "pgvector extension is not installed. "
                "Run: CREATE EXTENSION vector; in your PostgreSQL instance."
            )


async def close_db() -> None:
    """Called at application shutdown to cleanly close the connection pool."""
    await engine.dispose()
