"""
core/middleware.py

Application-level middleware stack:
  1. CORS — controls which origins can call the API
  2. Request logging — structured logs with request ID for tracing
  3. Global rate limiting — brute-force protection on auth endpoints
  4. Request timing — performance monitoring
  5. Error normalization — ensures consistent error response shape
"""

import time
import uuid
from collections.abc import Callable

import structlog
from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from core.config import settings

logger = structlog.get_logger()


# ─── CORS ────────────────────────────────────────────────────────────────────

def add_cors_middleware(app: FastAPI) -> None:
    """
    Configure CORS. In production, only the frontend domain is allowed.
    In development, localhost:3000 is allowed.
    """
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "X-Process-Time"],
    )


# ─── Request ID & Timing ─────────────────────────────────────────────────────

class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    Attaches a unique request ID to every request for distributed tracing.
    Adds X-Request-ID and X-Process-Time to every response.

    The request ID is available in route handlers via:
        request.state.request_id
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Use client-provided ID if present, else generate one
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id

        start_time = time.perf_counter()

        # Bind request context for structured logging
        with structlog.contextvars.bound_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            client_ip=request.client.host if request.client else "unknown",
        ):
            try:
                response = await call_next(request)
            except Exception as e:
                logger.error("unhandled_exception", error=str(e))
                raise

            process_time = (time.perf_counter() - start_time) * 1000  # ms

            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = f"{process_time:.2f}ms"

            logger.info(
                "request_complete",
                status_code=response.status_code,
                duration_ms=round(process_time, 2),
            )

        return response


# ─── Global Rate Limiter ──────────────────────────────────────────────────────

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Lightweight IP-based rate limiter for sensitive endpoints.
    Uses Redis for distributed counting across multiple workers.

    Limits:
        /api/auth/*     → 20 requests per minute per IP
        /api/*          → 200 requests per minute per IP
        Everything else → no limit
    """

    # Paths that get stricter limits
    AUTH_PATH_PREFIX = "/api/auth"
    API_PATH_PREFIX = "/api"

    AUTH_LIMIT = 20     # per minute
    API_LIMIT = 200     # per minute
    WINDOW = 60         # seconds

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"

        class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Lightweight IP-based rate limiter for sensitive endpoints.
    Uses Redis for distributed counting across multiple workers.

    Limits:
        /api/auth/*     → 20 requests per minute per IP
        /api/*          → 200 requests per minute per IP
        Everything else → no limit

    Additionally: if an IP hits 10+ 404s within 60 seconds, it gets
    blocked for 10 minutes. Catches credential-scanning attacks.
    """

    AUTH_PATH_PREFIX = "/api/auth"
    API_PATH_PREFIX = "/api"

    AUTH_LIMIT = 20
    API_LIMIT = 200
    WINDOW = 60

    NOT_FOUND_LIMIT = 10
    NOT_FOUND_WINDOW = 60
    NOT_FOUND_BLOCK_DURATION = 600  # 10 minutes

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"

        # Check if this IP is currently blocked for 404 scanning
        try:
            from core.cache import get_redis
            r = await get_redis()

            block_key = f"onegoal:blocked:{client_ip}"
            is_blocked = await r.get(block_key)
            if is_blocked:
                logger.warning(
                    "blocked_ip_request",
                    client_ip=client_ip,
                    path=path,
                )
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "error": "rate_limit_exceeded",
                        "detail": "Too many requests. Please slow down.",
                        "retry_after_seconds": self.NOT_FOUND_BLOCK_DURATION,
                    },
                    headers={"Retry-After": str(self.NOT_FOUND_BLOCK_DURATION)},
                )
        except Exception as e:
            logger.warning("rate_limit_redis_error", error=str(e), path=path)

        # Determine applicable rate limit
        if path.startswith(self.AUTH_PATH_PREFIX):
            limit = self.AUTH_LIMIT
            namespace = "rl:auth"
        elif path.startswith(self.API_PATH_PREFIX):
            limit = self.API_LIMIT
            namespace = "rl:api"
        else:
            return await call_next(request)

        # Check rate limit via Redis
        try:
            from core.cache import get_redis
            r = await get_redis()

            key = f"onegoal:{namespace}:{client_ip}"
            count = await r.incr(key)
            if count == 1:
                await r.expire(key, self.WINDOW)

            if count > limit:
                logger.warning(
                    "rate_limit_exceeded",
                    client_ip=client_ip,
                    path=path,
                    count=count,
                )
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "error": "rate_limit_exceeded",
                        "detail": "Too many requests. Please slow down.",
                        "retry_after_seconds": self.WINDOW,
                    },
                    headers={"Retry-After": str(self.WINDOW)},
                )
        except Exception as e:
            logger.warning("rate_limit_redis_error", error=str(e), path=path)
            if path.startswith(self.AUTH_PATH_PREFIX):
                return JSONResponse(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    content={
                        "error": "service_unavailable",
                        "detail": "Authentication service temporarily unavailable. Please try again shortly.",
                    },
                )

        # Process the request
        response = await call_next(request)

        # Track 404s and block IPs that hit too many
        if response.status_code == 404:
            try:
                from core.cache import get_redis
                r = await get_redis()

                not_found_key = f"onegoal:404s:{client_ip}"
                not_found_count = await r.incr(not_found_key)
                if not_found_count == 1:
                    await r.expire(not_found_key, self.NOT_FOUND_WINDOW)

                if not_found_count >= self.NOT_FOUND_LIMIT:
                    block_key = f"onegoal:blocked:{client_ip}"
                    await r.setex(block_key, self.NOT_FOUND_BLOCK_DURATION, "1")
                    logger.warning(
                        "ip_blocked_404_burst",
                        client_ip=client_ip,
                        not_found_count=not_found_count,
                        block_duration_seconds=self.NOT_FOUND_BLOCK_DURATION,
                    )
            except Exception as e:
                logger.warning("404_tracking_redis_error", error=str(e))

        return response

        # Check rate limit via Redis
        try:
            from core.cache import get_redis

            r = await get_redis()
            key = f"ongoal:{namespace}:{client_ip}"
            count = await r.incr(key)
            if count == 1:
                await r.expire(key, self.WINDOW)

            if count > limit:
                logger.warning(
                    "rate_limit_exceeded",
                    client_ip=client_ip,
                    path=path,
                    count=count,
                )
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "error": "rate_limit_exceeded",
                        "detail": "Too many requests. Please slow down.",
                        "retry_after_seconds": self.WINDOW,
                    },
                    headers={"Retry-After": str(self.WINDOW)},
                )
        except Exception as e:
            logger.warning("rate_limit_redis_error", error=str(e), path=path)
            # Fail closed on auth endpoints — brute-force protection is more important
            # than availability of these specific routes when Redis is down.
            # All other API routes fail open to preserve service availability.
            if path.startswith(self.AUTH_PATH_PREFIX):
                return JSONResponse(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    content={
                        "error": "service_unavailable",
                        "detail": "Authentication service temporarily unavailable. Please try again shortly.",
                    },
                )

        return await call_next(request)


# ─── Error Handler ────────────────────────────────────────────────────────────

async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Catch-all exception handler.
    Ensures all unhandled errors return a consistent JSON shape
    and never leak stack traces in production.
    """
    request_id = getattr(request.state, "request_id", "unknown")

    logger.error(
        "unhandled_exception",
        request_id=request_id,
        path=request.url.path,
        error=str(exc),
        exc_info=True,
    )

    if settings.is_production:
        # Never expose internal errors in production
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "internal_server_error",
                "detail": "An unexpected error occurred.",
                "request_id": request_id,
            },
        )
    else:
        # In development, include the actual error
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "internal_server_error",
                "detail": str(exc),
                "request_id": request_id,
            },
        )


# ─── Logging Configuration ───────────────────────────────────────────────────

def configure_logging() -> None:
    """
    Configure structlog for structured JSON logging.
    In development: human-readable console output.
    In production: JSON output for log aggregation (Datadog, etc.)
    """
    import logging

    import structlog

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_logger_name,
    ]

    if settings.is_development:
        # Pretty console output for development
        structlog.configure(
            processors=shared_processors + [
                structlog.dev.ConsoleRenderer(colors=True),
            ],
            wrapper_class=structlog.stdlib.BoundLogger,
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
        )
    else:
        # JSON output for production
        structlog.configure(
            processors=shared_processors + [
                structlog.processors.dict_tracebacks,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.stdlib.BoundLogger,
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
        )

    # Set root logger level
    logging.basicConfig(level=getattr(logging, settings.log_level.upper()))
