"""
main.py

FastAPI application entrypoint.

Startup sequence:
    1. Configure structured logging
    2. Connect to PostgreSQL (verify pgvector)
    3. Connect to Redis
    4. Mount all API routers
    5. Start background scheduler

Shutdown sequence:
    1. Stop scheduler (complete running jobs)
    2. Close database connection pool
    3. Close Redis connection
"""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from core.cache import close_redis, get_redis
from core.config import settings
from core.database import close_db, init_db
from core.middleware import (
    RateLimitMiddleware,
    RequestContextMiddleware,
    add_cors_middleware,
    configure_logging,
    global_exception_handler,
)

logger = structlog.get_logger()


# ─── Lifespan ────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.
    Everything before yield: startup.
    Everything after yield: shutdown.
    """
    # ── Startup ──────────────────────────────────────────────────────
    configure_logging()
    logger.info(
        "starting_one_goal",
        version=settings.app_version,
        environment=settings.environment,
    )

    # Verify database connection and pgvector extension
    await init_db()
    logger.info("database_connected")

    # Verify Redis connection
    redis = await get_redis()
    await redis.ping()
    logger.info("redis_connected")

    # Start background job scheduler
    from services.scheduler import start_scheduler
    scheduler = await start_scheduler()
    logger.info("scheduler_started")

    logger.info("one_goal_ready", port=settings.port)

    yield  # Application runs here

    # ── Shutdown ─────────────────────────────────────────────────────
    logger.info("shutting_down")

    scheduler.shutdown(wait=True)
    await close_db()
    await close_redis()

    logger.info("shutdown_complete")


# ─── App Factory ─────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Identity transformation system API",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ── Middleware (order matters — outermost executes first) ─────────
    add_cors_middleware(app)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(RateLimitMiddleware)

    # ── Exception Handlers ────────────────────────────────────────────
    app.add_exception_handler(Exception, global_exception_handler)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """
        Return structured validation errors from Pydantic.
        Makes it easy for the frontend to map errors to form fields.
        """
        errors = []
        for error in exc.errors():
            errors.append({
                "field": ".".join(str(loc) for loc in error["loc"][1:]),  # skip "body"
                "message": error["msg"],
                "type": error["type"],
            })
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error": "validation_error", "detail": errors},
        )

    # ── Routers ───────────────────────────────────────────────────────
    _register_routers(app)

    return app


def _register_routers(app: FastAPI) -> None:
    """Mount all API routers under /api prefix."""
    from api.routers.auth import router as auth_router

    # Import remaining routers as they're built in subsequent steps
    # from api.routers.onboarding import router as onboarding_router
    # from api.routers.goals import router as goals_router
    # from api.routers.tasks import router as tasks_router
    # from api.routers.reflections import router as reflections_router
    # from api.routers.coach import router as coach_router
    # from api.routers.progress import router as progress_router
    # from api.routers.data import router as data_router

    API_PREFIX = "/api"

    app.include_router(auth_router, prefix=API_PREFIX)
    # app.include_router(onboarding_router, prefix=API_PREFIX)
    # app.include_router(goals_router, prefix=API_PREFIX)
    # app.include_router(tasks_router, prefix=API_PREFIX)
    # app.include_router(reflections_router, prefix=API_PREFIX)
    # app.include_router(coach_router, prefix=API_PREFIX)
    # app.include_router(progress_router, prefix=API_PREFIX)
    # app.include_router(data_router, prefix=API_PREFIX)


# ── Health Check ──────────────────────────────────────────────────────────────

def _add_health_routes(app: FastAPI) -> None:
    """Health check endpoints for load balancer and uptime monitoring."""

    @app.get("/health", tags=["System"], include_in_schema=False)
    async def health_check() -> dict:
        """Basic liveness check — if this returns 200, the process is alive."""
        return {"status": "ok", "version": settings.app_version}

    @app.get("/health/ready", tags=["System"], include_in_schema=False)
    async def readiness_check() -> dict:
        """
        Readiness check — verifies DB and Redis are reachable.
        Used by Kubernetes/Railway to decide if traffic should be routed here.
        """
        from sqlalchemy import text

        from core.database import AsyncSessionLocal

        checks = {"database": False, "redis": False}

        try:
            async with AsyncSessionLocal() as db:
                await db.execute(text("SELECT 1"))
            checks["database"] = True
        except Exception as e:
            logger.error("db_health_check_failed", error=str(e))

        try:
            redis = await get_redis()
            await redis.ping()
            checks["redis"] = True
        except Exception as e:
            logger.error("redis_health_check_failed", error=str(e))

        all_healthy = all(checks.values())
        return JSONResponse(
            status_code=200 if all_healthy else 503,
            content={"status": "ready" if all_healthy else "not_ready", "checks": checks},
        )


# ─── Create Application ───────────────────────────────────────────────────────

app = create_app()
_add_health_routes(app)


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.is_development,
        log_level=settings.log_level.lower(),
        access_log=False,  # We handle request logging in middleware
    )
