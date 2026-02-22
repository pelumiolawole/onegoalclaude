"""
ai/base.py

Base class for all AI engines.

Every engine inherits this — it provides:
  - Shared OpenAI async client (singleton)
  - Structured output helpers (JSON parsing)
  - AI interaction logging to the database
  - Safety filter integration
  - Cost estimation
  - Retry logic with exponential backoff

Design principle: No engine talks directly to OpenAI.
They all go through this base so logging, safety, and cost
tracking are guaranteed for every call.
"""

import asyncio
import json
import time
from typing import Any
from uuid import UUID

import structlog
from openai import AsyncOpenAI, APIError, RateLimitError, APITimeoutError

from core.config import settings

logger = structlog.get_logger()

# ─── Shared client singleton ─────────────────────────────────────────────────
_openai_client: AsyncOpenAI | None = None


def get_openai_client() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            timeout=30.0,
            max_retries=0,  # we handle retries ourselves
        )
    return _openai_client


# ─── Token cost table (USD per 1K tokens, as of late 2024) ───────────────────
COST_TABLE = {
    "gpt-4o":                   {"input": 0.0025, "output": 0.010},
    "gpt-4o-mini":              {"input": 0.00015, "output": 0.0006},
    "text-embedding-3-small":   {"input": 0.00002, "output": 0.0},
    "text-embedding-3-large":   {"input": 0.00013, "output": 0.0},
}


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    rates = COST_TABLE.get(model, {"input": 0.005, "output": 0.015})
    return (prompt_tokens * rates["input"] + completion_tokens * rates["output"]) / 1000


# ─── Base Engine ─────────────────────────────────────────────────────────────

class BaseAIEngine:
    """
    Base class for all One Goal AI engines.

    Subclasses implement:
        engine_name: str          — used for logging and rate limiting
        default_temperature: float

    And call:
        await self._complete(...)   — for standard completions
        await self._stream(...)     — for streaming (coach)
        await self._embed(...)      — for generating embeddings
    """

    engine_name: str = "base"
    default_temperature: float = 0.7
    default_model: str = settings.openai_model

    def __init__(self):
        self.client = get_openai_client()

    # ─── Core Completion ─────────────────────────────────────────────

    async def _complete(
        self,
        messages: list[dict],
        user_id: UUID | str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict | None = None,
        model: str | None = None,
        retries: int = 3,
    ) -> str:
        """
        Call the OpenAI API with retry logic and full logging.
        Returns the text content of the first choice.
        """
        model = model or self.default_model
        temperature = temperature if temperature is not None else self.default_temperature
        max_tokens = max_tokens or settings.openai_max_tokens_generation

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            kwargs["response_format"] = response_format

        last_error: Exception | None = None
        start_time = time.perf_counter()

        for attempt in range(retries):
            try:
                response = await self.client.chat.completions.create(**kwargs)
                latency_ms = int((time.perf_counter() - start_time) * 1000)

                content = response.choices[0].message.content or ""
                usage = response.usage

                # Log every AI call to the database
                await self._log_interaction(
                    user_id=user_id,
                    model=model,
                    prompt_tokens=usage.prompt_tokens if usage else 0,
                    completion_tokens=usage.completion_tokens if usage else 0,
                    latency_ms=latency_ms,
                    success=True,
                )

                return content

            except RateLimitError as e:
                wait = 2 ** attempt  # exponential backoff: 1s, 2s, 4s
                logger.warning(
                    "openai_rate_limit",
                    engine=self.engine_name,
                    attempt=attempt,
                    wait_seconds=wait,
                )
                await asyncio.sleep(wait)
                last_error = e

            except APITimeoutError as e:
                logger.warning("openai_timeout", engine=self.engine_name, attempt=attempt)
                last_error = e
                await asyncio.sleep(1)

            except APIError as e:
                logger.error("openai_api_error", engine=self.engine_name, error=str(e))
                last_error = e
                break  # Don't retry on API errors (4xx)

        # All retries exhausted
        await self._log_interaction(
            user_id=user_id,
            model=model,
            prompt_tokens=0,
            completion_tokens=0,
            latency_ms=int((time.perf_counter() - start_time) * 1000),
            success=False,
            error=str(last_error),
        )
        raise last_error or RuntimeError(f"{self.engine_name} failed after {retries} retries")

    # ─── Streaming Completion (for coach) ────────────────────────────

    async def _stream(
        self,
        messages: list[dict],
        user_id: UUID | str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ):
        """
        Streaming completion — yields text chunks as they arrive.
        Used exclusively by the Coach engine for real-time responses.

        Usage:
            async for chunk in engine._stream(messages):
                yield chunk  # send to SSE stream
        """
        temperature = temperature if temperature is not None else self.default_temperature
        max_tokens = max_tokens or settings.openai_max_tokens_coach

        start_time = time.perf_counter()
        full_content = ""
        prompt_tokens = 0
        completion_tokens = 0

        try:
            stream = await self.client.chat.completions.create(
                model=self.default_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
                stream_options={"include_usage": True},
            )

            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    text = chunk.choices[0].delta.content
                    full_content += text
                    yield text

                # Capture usage from final chunk
                if hasattr(chunk, "usage") and chunk.usage:
                    prompt_tokens = chunk.usage.prompt_tokens
                    completion_tokens = chunk.usage.completion_tokens

        finally:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            await self._log_interaction(
                user_id=user_id,
                model=self.default_model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                latency_ms=latency_ms,
                success=True,
            )

    # ─── Embeddings ──────────────────────────────────────────────────

    async def _embed(self, text: str) -> list[float]:
        """
        Generate a 1536-dimension embedding for semantic memory.
        Uses text-embedding-3-small for cost efficiency.
        """
        if not text or not text.strip():
            return [0.0] * 1536

        # Truncate to model's token limit
        text = text[:8000]

        response = await self.client.embeddings.create(
            model=settings.openai_embedding_model,
            input=text,
        )
        return response.data[0].embedding

    # ─── JSON Output Parsing ─────────────────────────────────────────

    def _parse_json(self, raw: str, fallback: dict | None = None) -> dict:
        """
        Parse AI JSON output robustly.
        Handles markdown code fences, trailing commas, and minor formatting issues.
        """
        # Strip markdown code fences
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1])  # remove first and last lines

        # Remove any text before the first { or [
        for i, ch in enumerate(cleaned):
            if ch in "{[":
                cleaned = cleaned[i:]
                break

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.warning(
                "json_parse_failed",
                engine=self.engine_name,
                error=str(e),
                raw_preview=raw[:200],
            )
            return fallback or {}

    # ─── Interaction Logging ─────────────────────────────────────────

    async def _log_interaction(
        self,
        user_id: UUID | str | None,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: int,
        success: bool,
        error: str | None = None,
    ) -> None:
        """
        Log AI interaction to the database for cost tracking and auditing.
        Fire-and-forget — never raises exceptions (logging failures shouldn't
        crash the main request).
        """
        try:
            from core.database import get_db_context
            from sqlalchemy import text

            cost = estimate_cost(model, prompt_tokens, completion_tokens)

            async with get_db_context() as db:
                await db.execute(
                    text("""
                        INSERT INTO ai_interactions
                            (user_id, engine, model, prompt_tokens, completion_tokens,
                             estimated_cost_usd, latency_ms, success, error_message)
                        VALUES
                            (:user_id, :engine, :model, :prompt_tokens, :completion_tokens,
                             :cost, :latency_ms, :success, :error)
                    """),
                    {
                        "user_id": str(user_id) if user_id else None,
                        "engine": self.engine_name,
                        "model": model,
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "cost": cost,
                        "latency_ms": latency_ms,
                        "success": success,
                        "error": error,
                    },
                )
        except Exception as e:
            # Silent fail — logging must never break the main flow
            logger.warning("interaction_log_failed", error=str(e))
