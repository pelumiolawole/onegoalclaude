"""
ai/engines/coach.py

AI Coach Engine

The persistent, context-aware coach that knows the user deeply.

Features:
  - Full user context loaded on every message
  - Semantic memory retrieval (finds relevant past exchanges)
  - Adaptive coaching mode (guide/support/challenge/celebrate/intervention)
  - Streaming responses for real-time feel
  - Safety filter on every message
  - Persistent session management
  - Key topic extraction for profile updates

The coach is the only real-time AI interaction in the product.
All other engines run in batch or on-submission.
"""

import json
from collections.abc import AsyncGenerator
from typing import Literal
from uuid import UUID, uuid4

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai.base import BaseAIEngine
from ai.memory.context_builder import context_builder
from ai.memory.retrieval import memory_retrieval
from ai.prompts.system_prompts import get_prompt
from ai.utils.safety_filter import SafetyLevel, safety_filter
from core.config import settings
from core.security import sanitize_input

logger = structlog.get_logger()

CoachingMode = Literal["guide", "support", "challenge", "celebrate", "intervention"]


class CoachEngine(BaseAIEngine):
    """
    Streaming AI coach with full user context and semantic memory.
    """

    engine_name = "coach"
    default_temperature = 0.7

    async def stream_response(
        self,
        user_id: UUID | str,
        session_id: UUID | str,
        user_message: str,
        db: AsyncSession,
    ) -> AsyncGenerator[str, None]:
        """
        Stream a coach response to a user message.

        Yields text chunks as they arrive from the OpenAI streaming API.
        After streaming completes, saves the full exchange to the database.

        Usage in SSE endpoint:
            async for chunk in coach.stream_response(...):
                yield f"data: {chunk}\\n\\n"
        """
        uid = str(user_id)
        sid = str(session_id)

        # ── Safety check ──────────────────────────────────────────────
        safety_level = safety_filter.classify(user_message)
        if safety_level in (SafetyLevel.CRISIS, SafetyLevel.DISTRESS):
            safe_response = safety_filter.get_safe_response(safety_level)
            await safety_filter.log_safety_flag(
                user_id=uid,
                source_type="coach_message",
                source_id=str(uuid4()),
                level=safety_level,
                excerpt=user_message[:200],
                ai_response=safe_response,
                db=db,
            )
            # Yield safe response without calling the AI
            yield safe_response
            # Save the exchange
            await self._save_message(uid, sid, "user", user_message, db)
            await self._save_message(uid, sid, "assistant", safe_response, db)
            return

        # ── Prompt injection check ────────────────────────────────────
        if safety_filter.detect_prompt_injection(user_message):
            response = "I didn't follow that. What's on your mind regarding your goal?"
            yield response
            return

        # ── Out of scope check ─────────────────────────────────────────
        if safety_filter.detect_out_of_scope(user_message):
            response = safety_filter.get_out_of_scope_response()
            yield response
            await self._save_message(uid, sid, "user", user_message, db)
            await self._save_message(uid, sid, "assistant", response, db)
            return

        # ── Clean input ───────────────────────────────────────────────
        clean_message = sanitize_input(user_message)

        # ── Load context ──────────────────────────────────────────────
        context = await context_builder.get_context(uid, db)
        context_str = context_builder.format_for_prompt(context)

        # ── Determine coaching mode ───────────────────────────────────
        coaching_mode = self._determine_coaching_mode(context, user_message)

        # ── Retrieve semantic memories ────────────────────────────────
        relevant_reflections = await memory_retrieval.retrieve_relevant_reflections(
            user_id=uid,
            query=clean_message,
            limit=2,
            db=db,
        )
        relevant_exchanges = await memory_retrieval.retrieve_relevant_coach_exchanges(
            user_id=uid,
            query=clean_message,
            limit=2,
            db=db,
        )
        memories_str = memory_retrieval.format_memories_for_prompt(
            relevant_reflections, relevant_exchanges
        )

        # ── Build today's context ─────────────────────────────────────
        daily_context = await self._get_daily_context(uid, db)

        # ── Build system prompt ───────────────────────────────────────
        system_prompt = get_prompt("coach").format(
            user_context=context_str,
            memories=memories_str or "No relevant memories retrieved.",
            coaching_mode=coaching_mode,
            daily_context=daily_context,
        )

        # ── Load recent conversation history ──────────────────────────
        recent_messages = await self._load_recent_messages(sid, db, limit=10)

        # ── Assemble full message list ────────────────────────────────
        prompt_messages = [
            {"role": "system", "content": system_prompt},
            *recent_messages,
            {"role": "user", "content": clean_message},
        ]

        # ── Save user message first ───────────────────────────────────
        user_msg_id = await self._save_message(uid, sid, "user", clean_message, db)

        # ── Stream AI response ────────────────────────────────────────
        full_response = ""
        async for chunk in self._stream(
            messages=prompt_messages,
            user_id=uid,
            temperature=self.default_temperature,
            max_tokens=settings.openai_max_tokens_coach,
        ):
            full_response += chunk
            yield chunk

        # ── Save AI response ──────────────────────────────────────────
        ai_msg_id = await self._save_message(uid, sid, "assistant", full_response, db)

        # ── Store embeddings (async, non-blocking) ────────────────────
        try:
            await memory_retrieval.store_message_embedding(user_msg_id, clean_message, db)
        except Exception as e:
            logger.warning("embedding_storage_failed", error=str(e))

        # ── Extract topics and update session ─────────────────────────
        await self._update_session_after_message(uid, sid, clean_message, db)

        logger.info(
            "coach_message_processed",
            user_id=uid,
            session_id=sid,
            coaching_mode=coaching_mode,
            message_length=len(clean_message),
            response_length=len(full_response),
        )

    async def create_session(self, user_id: UUID | str, db: AsyncSession) -> str:
        """Create a new coach session and return its ID."""
        uid = str(user_id)
        
        # Create session
        result = await db.execute(
            text("""
                INSERT INTO ai_coach_sessions (user_id, coaching_mode)
                VALUES (:user_id, 'guide')
                RETURNING id
            """),
            {"user_id": uid},
        )
        session_id = str(result.scalar())
        
        # Seed with welcome message so AI doesn't repeat it
        welcome_message = "I'm here. What's on your mind regarding your goal?"
        await self._save_message(uid, session_id, "assistant", welcome_message, db)
        
        logger.info("coach_session_created", user_id=uid, session_id=session_id)
        return session_id

    async def get_or_create_active_session(
        self, user_id: UUID | str, db: AsyncSession
    ) -> str:
        """Get the most recent active session or create a new one."""
        uid = str(user_id)
        result = await db.execute(
            text("""
                SELECT id FROM ai_coach_sessions
                WHERE user_id = :user_id AND is_active = TRUE
                ORDER BY started_at DESC
                LIMIT 1
            """),
            {"user_id": uid},
        )
        row = result.fetchone()
        if row:
            return str(row[0])
        return await self.create_session(uid, db)

    def _determine_coaching_mode(self, context: dict, message: str) -> CoachingMode:
        """
        Determine the appropriate coaching mode from context and message.
        The mode shapes the coach's tone and approach.
        """
        scores = context.get("scores", {})
        retention = context.get("retention", {})
        message_lower = message.lower()

        # Intervention: user has been absent
        if (retention or {}).get("needs_intervention"):
            return "intervention"

        # Celebrate: explicit wins or breakthroughs
        win_words = ["did it", "completed", "achieved", "finished", "proud", "nailed", "success"]
        if any(w in message_lower for w in win_words):
            return "celebrate"

        # Support: struggling signals
        struggle_words = ["stuck", "struggling", "can't", "failed", "hard", "difficult", "help"]
        if any(w in message_lower for w in struggle_words):
            return "support"

        # Support: low/critical momentum
        if scores.get("momentum_state") in ("declining", "critical"):
            return "support"

        # Challenge: rising momentum and they seem ready
        challenge_words = ["push", "more", "harder", "next level", "challenge", "ready"]
        if scores.get("momentum_state") == "rising" and any(w in message_lower for w in challenge_words):
            return "challenge"

        return "guide"

    async def _get_daily_context(self, user_id: str, db: AsyncSession) -> str:
        """Get today's task and reflection status for the coach."""
        result = await db.execute(
            text("""
                SELECT
                    dt.identity_focus,
                    dt.title,
                    dt.status AS task_status,
                    r.sentiment AS reflection_sentiment,
                    r.submitted_at AS reflected_at
                FROM daily_tasks dt
                LEFT JOIN reflections r ON r.task_id = dt.id
                WHERE dt.user_id = :user_id
                  AND dt.scheduled_date = CURRENT_DATE
                  AND dt.task_type = 'becoming'
                LIMIT 1
            """),
            {"user_id": user_id},
        )
        row = result.fetchone()

        if not row:
            return "No task scheduled for today yet."

        lines = [f"Today's task: {row.title} ({row.task_status})"]
        if row.identity_focus:
            lines.append(f"Today's identity focus: {row.identity_focus}")
        if row.reflected_at:
            lines.append(f"Reflected at: {row.reflected_at} | Sentiment: {row.reflection_sentiment}")
        else:
            lines.append("Not yet reflected on today's task.")

        return "\n".join(lines)

            async def _load_recent_messages(
        self, session_id: str, db: AsyncSession, limit: int = 10
    ) -> list[dict]:
        """Load recent messages in a session for conversation context."""
        # Get total count first
        count_result = await db.execute(
            text("""
                SELECT COUNT(*) FROM ai_coach_messages
                WHERE session_id = :session_id
            """),
            {"session_id": session_id},
        )
        total_count = count_result.scalar() or 0
        
        # Calculate offset to get the most recent 'limit' messages
        offset = max(0, total_count - limit)
        
        result = await db.execute(
            text("""
                SELECT role, content
                FROM ai_coach_messages
                WHERE session_id = :session_id
                ORDER BY created_at ASC
                LIMIT :limit OFFSET :offset
            """),
            {"session_id": session_id, "limit": limit, "offset": offset},
        )
        rows = result.fetchall()
        return [{"role": row.role, "content": row.content} for row in rows]
    
    async def _save_message(
        self,
        user_id: str,
        session_id: str,
        role: str,
        content: str,
        db: AsyncSession,
    ) -> UUID:
        """Save a single message to the database. Returns the message ID."""
        result = await db.execute(
            text("""
                INSERT INTO ai_coach_messages (user_id, session_id, role, content)
                VALUES (:user_id, :session_id, :role, :content)
                RETURNING id
            """),
            {
                "user_id": user_id,
                "session_id": session_id,
                "role": role,
                "content": content,
            },
        )
        msg_id = result.scalar()

        # Update session message count and last_message_at
        await db.execute(
            text("""
                UPDATE ai_coach_sessions
                SET message_count = message_count + 1, last_message_at = NOW()
                WHERE id = :session_id
            """),
            {"session_id": session_id},
        )

        return msg_id

    async def _update_session_after_message(
        self, user_id: str, session_id: str, user_message: str, db: AsyncSession
    ) -> None:
        """
        Extract key topics from the message and update session.
        Async background task — failures are silent.
        """
        try:
            # Simple keyword extraction (avoid another AI call for cost)
            topic_keywords = [
                "goal", "motivation", "habit", "fear", "failure", "success",
                "discipline", "focus", "energy", "stress", "confidence",
                "morning", "evening", "work", "family", "health", "money",
            ]
            found_topics = [kw for kw in topic_keywords if kw in user_message.lower()]

            if found_topics:
                await db.execute(
                    text("""
                        UPDATE ai_coach_messages
                        SET key_topics = :topics
                        WHERE session_id = :session_id
                          AND role = 'user'
                          AND created_at = (
                            SELECT MAX(created_at) FROM ai_coach_messages
                            WHERE session_id = :session_id AND role = 'user'
                          )
                    """),
                    {"session_id": session_id, "topics": found_topics},
                )
        except Exception:
            pass  # Topic extraction is best-effort
