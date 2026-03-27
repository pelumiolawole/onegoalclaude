"""
ai/engines/coach.py

AI Coach Engine

The persistent, context-aware coach that knows the user deeply.

Features:
  - Full user context loaded on every message (including session memory V2)
  - Semantic memory retrieval (finds relevant past exchanges)
  - Adaptive coaching mode (guide/support/challenge/celebrate/intervention/crisis)
  - Session architecture with intentional openings/closings
  - Pattern recognition and moment tracking
  - Streaming responses for real-time feel
  - Safety filter with crisis escalation
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

# Extended coaching modes for V2 (includes crisis)
CoachingMode = Literal["guide", "support", "challenge", "celebrate", "intervention", "crisis"]


async def _safe_rollback(db: AsyncSession) -> None:
    """Rollback without raising. Call after any caught DB exception to prevent poisoned transactions."""
    try:
        await db.rollback()
    except Exception:
        pass


class CoachEngine(BaseAIEngine):
    """
    Streaming AI coach with full user context, semantic memory, and session architecture.
    """

    engine_name = "coach"
    default_temperature = 0.7

    async def stream_response(
        self,
        user_id: UUID | str,
        session_id: UUID | str,
        user_message: str,
        db: AsyncSession,
        is_new_session: bool = False,
    ) -> AsyncGenerator[str, None]:
        uid = str(user_id)
        sid = str(session_id)

        # ── Safety check (including crisis) ───────────────────────────
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
            if safety_level == SafetyLevel.CRISIS:
                await self._log_moment(
                    uid, sid, "crisis_signal", user_message[:500],
                    "Crisis language detected", db
                )
            yield safe_response
            await self._save_message(uid, sid, "user", user_message, db)
            await self._save_message(uid, sid, "assistant", safe_response, db)
            return

        # ── Prompt injection check ─────────────────────────────────────
        if safety_filter.detect_prompt_injection(user_message):
            response = "I didn't follow that. What's on your mind regarding your goal?"
            yield response
            return

        # ── Out of scope check ───────────────────────────────────────
        if safety_filter.detect_out_of_scope(user_message):
            response = safety_filter.get_out_of_scope_response()
            yield response
            await self._save_message(uid, sid, "user", user_message, db)
            await self._save_message(uid, sid, "assistant", response, db)
            return

        # ── Clean input ──────────────────────────────────────────────
        clean_message = sanitize_input(user_message)

        # ── Load context (with enhanced V2 memory) ───────────────────
        context = await context_builder.get_context(uid, db)
        context_str = context_builder.format_for_prompt(context)

        # ── Get coaching mode from context ─────────────────────────
        coaching_mode = context.get("current_coach_mode", "guide")

        # ── Retrieve semantic memories ─────────────────────────────────
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

        # ── Build today's context ────────────────────────────────────
        daily_context = await self._get_daily_context(uid, db)

        # ── Build session-aware context strings (V2) ───────────────────
        session_continuity = context.get("session_continuity", {})
        last_session = context.get("last_session", {})
        active_patterns = context.get("active_patterns", [])
        recent_moments = context.get("recent_moments", [])

        last_session_summary = self._format_last_session_summary(last_session)
        recent_behavior_pattern = self._format_behavior_pattern(active_patterns, recent_moments)

        # ── Build system prompt ─────────────────────────────────────
        system_prompt = get_prompt("coach").format(
            user_name=context.get("display_name", "the user"),
            goal_statement=context.get("goal", {}).get("statement", "not set"),
            identity_anchor=context.get("identity", {}).get("life_direction", "not set"),
            momentum_state=context.get("scores", {}).get("momentum_state", "holding"),
            last_session_summary=last_session_summary,
            recent_behavior_pattern=recent_behavior_pattern,
            user_context=context_str,
            memories=memories_str or "No relevant memories retrieved.",
            coaching_mode=coaching_mode,
            daily_context=daily_context,
        )

        # ── Load recent conversation history ─────────────────────────
        recent_messages = await self._load_recent_messages(sid, db, limit=10)

        # ── Detect and log significant moments (V2) ──────────────────
        moment_type = self._detect_moment_type(clean_message, full_response="", context=context)
        if moment_type:
            await self._log_moment(uid, sid, moment_type, clean_message, None, db)

        # ── Assemble full message list ──────────────────────────────
        prompt_messages = [
            {"role": "system", "content": system_prompt},
            *recent_messages,
            {"role": "user", "content": clean_message},
        ]

        # ── Save user message first ──────────────────────────────────
        user_msg_id = await self._save_message(uid, sid, "user", clean_message, db)

        # ── Update session opening if new session (V2) ───────────────
        if is_new_session and session_continuity:
            await self._update_session_opening(uid, sid, session_continuity, db)

        # ── Stream AI response ───────────────────────────────────────
        full_response = ""
        async for chunk in self._stream(
            messages=prompt_messages,
            user_id=uid,
            temperature=self.default_temperature,
            max_tokens=settings.openai_max_tokens_coach,
        ):
            full_response += chunk
            yield chunk

        # ── Save AI response ─────────────────────────────────────────
        ai_msg_id = await self._save_message(uid, sid, "assistant", full_response, db)

        # ── Detect response moments and update session (V2) ────────────
        response_moment = self._detect_response_moment(full_response)
        if response_moment:
            await self._log_moment(uid, sid, response_moment, full_response[:300], None, db)

        # ── Update session closing insight periodically (V2) ─────────
        await self._maybe_update_session_closing(uid, sid, full_response, db)

        # ── Store embeddings (async, non-blocking) ───────────────────
        try:
            await memory_retrieval.store_message_embedding(user_msg_id, clean_message, db)
        except Exception as e:
            logger.warning("embedding_storage_failed", error=str(e))
            await _safe_rollback(db)

        # ── Extract topics and update session ────────────────────────
        await self._update_session_after_message(uid, sid, clean_message, db)

        logger.info(
            "coach_message_processed",
            user_id=uid,
            session_id=sid,
            coaching_mode=coaching_mode,
            message_length=len(clean_message),
            response_length=len(full_response),
        )

    # ========================================================================
    # Session Architecture Methods (V2)
    # ========================================================================

    async def start_session(
        self, user_id: UUID | str, db: AsyncSession, opening_context: str = None
    ) -> str:
        uid = str(user_id)

        result = await db.execute(
            text("""
                INSERT INTO coach_sessions (
                    user_id, session_start, opening_context, coach_mode_used
                )
                VALUES (:user_id, NOW(), :opening_context, 'guide')
                RETURNING id
            """),
            {"user_id": uid, "opening_context": opening_context or "User initiated session"},
        )
        session_id = str(result.scalar())

        await db.execute(
            text("""
                INSERT INTO ai_coach_sessions (id, user_id, coaching_mode, started_at)
                VALUES (:id, :user_id, 'guide', NOW())
            """),
            {"id": session_id, "user_id": uid},
        )

        logger.info("coach_session_started_v2", user_id=uid, session_id=session_id)
        return session_id

    async def end_session(
        self, user_id: UUID | str, session_id: UUID | str, closing_insight: str = None,
        next_hook: str = None, db: AsyncSession = None
    ) -> None:
        uid = str(user_id)
        sid = str(session_id)

        await db.execute(
            text("""
                UPDATE coach_sessions
                SET session_end = NOW(),
                    closing_insight = :closing_insight,
                    next_session_hook = :next_hook,
                    message_count = (
                        SELECT COUNT(*) FROM ai_coach_messages
                        WHERE session_id = :session_id
                    )
                WHERE id = :session_id AND user_id = :user_id
            """),
            {
                "session_id": sid,
                "user_id": uid,
                "closing_insight": closing_insight,
                "next_hook": next_hook,
            },
        )

        await db.execute(
            text("""
                UPDATE ai_coach_sessions
                SET is_active = FALSE, ended_at = NOW()
                WHERE id = :session_id
            """),
            {"session_id": sid},
        )

        logger.info("coach_session_ended_v2", user_id=uid, session_id=sid)

    async def _update_session_opening(
        self, user_id: str, session_id: str, session_continuity: dict, db: AsyncSession
    ) -> None:
        opening = session_continuity.get("opening_hook", "")
        if opening:
            try:
                await db.execute(
                    text("""
                        UPDATE coach_sessions
                        SET opening_context = COALESCE(opening_context, :opening)
                        WHERE id = :session_id AND user_id = :user_id
                    """),
                    {"session_id": session_id, "user_id": user_id, "opening": opening},
                )
            except Exception as e:
                logger.warning("session_opening_update_failed", error=str(e))
                await _safe_rollback(db)

    async def _maybe_update_session_closing(
        self, user_id: str, session_id: str, ai_response: str, db: AsyncSession
    ) -> None:
        try:
            msg_count = await db.execute(
                text("""
                    SELECT COUNT(*) FROM ai_coach_messages
                    WHERE session_id = :session_id
                """),
                {"session_id": session_id},
            )
            count = msg_count.scalar() or 0

            if count % 5 == 0:
                closing = self._extract_closing_insight(ai_response)
                if closing:
                    await db.execute(
                        text("""
                            UPDATE coach_sessions
                            SET closing_insight = :closing,
                                next_session_hook = :hook
                            WHERE id = :session_id AND user_id = :user_id
                        """),
                        {
                            "session_id": session_id,
                            "user_id": user_id,
                            "closing": closing[:200],
                            "hook": self._extract_follow_up(ai_response),
                        },
                    )
        except Exception as e:
            logger.warning("session_closing_update_failed", error=str(e))
            await _safe_rollback(db)

    # ========================================================================
    # Moment and Pattern Tracking (V2)
    # ========================================================================

    async def _log_moment(
        self, user_id: str, session_id: str, moment_type: str,
        content: str, coach_observation: str = None, db: AsyncSession = None
    ) -> None:
        try:
            user_language = content[:150] if len(content) > 50 else content

            await db.execute(
                text("""
                    INSERT INTO coach_moments (
                        user_id, session_id, moment_type, moment_content,
                        coach_observation, user_language, emotional_tone
                    )
                    VALUES (
                        :user_id, :session_id, :moment_type, :content,
                        :observation, :user_language,
                        (SELECT sentiment FROM reflections
                         WHERE user_id = :user_id
                         ORDER BY created_at DESC LIMIT 1)
                    )
                """),
                {
                    "user_id": user_id,
                    "session_id": session_id,
                    "moment_type": moment_type,
                    "content": content[:500],
                    "observation": coach_observation,
                    "user_language": user_language,
                },
            )
            logger.debug("moment_logged", user_id=user_id, type=moment_type)
        except Exception as e:
            logger.warning("moment_log_failed", error=str(e))
            # Must rollback after any failed DB op — otherwise PostgreSQL
            # marks the whole transaction as aborted and all subsequent
            # queries in the same connection will fail with InFailedSQLTransactionError
            await _safe_rollback(db)

    def _detect_moment_type(self, message: str, full_response: str, context: dict) -> str | None:
        msg_lower = message.lower()

        breakthrough_words = ["realized", "finally", "click", "shift", "different", "see it now"]
        if any(w in msg_lower for w in breakthrough_words):
            return "breakthrough"

        resistance_words = ["can't", "impossible", "never", "always fail", "not for me"]
        if any(w in msg_lower for w in resistance_words):
            return "resistance"

        commit_words = ["will do", "commit", "promise", "starting tomorrow", "from now on"]
        if any(w in msg_lower for w in commit_words):
            return "commitment"

        vuln_words = ["scared", "ashamed", "embarrassed", "never told", "secret"]
        if any(w in msg_lower for w in vuln_words):
            return "vulnerability"

        return None

    def _detect_response_moment(self, response: str) -> str | None:
        if "resistance" in response.lower() or "avoiding" in response.lower():
            return "resistance_named"
        if "breakthrough" in response.lower() or "shift" in response.lower():
            return "breakthrough_affirmed"
        return None

    # ========================================================================
    # Formatting Helpers
    # ========================================================================

    def _format_last_session_summary(self, last_session: dict | None) -> str:
        if not last_session:
            return "First session with this user."

        days_since = last_session.get("days_since", 0)
        closing = last_session.get("closing_insight", "")
        hook = last_session.get("next_session_hook", "")

        parts = []
        if days_since < 1:
            parts.append("Earlier today")
        elif days_since < 2:
            parts.append("Yesterday")
        else:
            parts.append(f"{int(days_since)} days ago")

        if closing:
            parts.append(f"we left with: {closing[:100]}")
        if hook:
            parts.append(f"Follow-up pending: {hook[:100]}")

        return " | ".join(parts) if parts else "Recent session, details not recorded."

    def _format_behavior_pattern(self, active_patterns: list, recent_moments: list) -> str:
        if not active_patterns and not recent_moments:
            return "Still learning this person's patterns."

        parts = []

        if active_patterns:
            top = active_patterns[0]
            parts.append(f"Pattern: {top['name']} ({top['type']}) - {top['description'][:80]}")

        significant = [m for m in recent_moments if m.get("type") in ["breakthrough", "commitment"]]
        if significant:
            m = significant[0]
            parts.append(f"Recent {m['type']}: {m.get('user_language', '')[:60]}...")

        return " | ".join(parts) if parts else "Patterns emerging."

    def _extract_closing_insight(self, response: str) -> str:
        sentences = response.split(". ")
        candidates = [s for s in sentences[-2:] if "?" in s or len(s) > 20]
        return candidates[-1] if candidates else response[-150:]

    def _extract_follow_up(self, response: str) -> str:
        if "next time" in response.lower():
            idx = response.lower().find("next time")
            return response[idx:idx+100]
        if "check" in response.lower() and "?" in response:
            for sent in response.split(". "):
                if "check" in sent.lower() and "?" in sent:
                    return sent
        return ""

    # ========================================================================
    # Legacy Methods
    # ========================================================================

    async def create_session(self, user_id: UUID | str, db: AsyncSession) -> str:
        return await self.start_session(user_id, db)

    async def get_or_create_active_session(
        self, user_id: UUID | str, db: AsyncSession
    ) -> str:
        uid = str(user_id)

        result = await db.execute(
            text("""
                SELECT id FROM coach_sessions
                WHERE user_id = :user_id AND session_end IS NULL
                ORDER BY session_start DESC
                LIMIT 1
            """),
            {"user_id": uid},
        )
        row = result.fetchone()
        if row:
            return str(row[0])

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

        return await self.start_session(uid, db)

    def _determine_coaching_mode(self, context: dict, message: str) -> CoachingMode:
        ctx_mode = context.get("current_coach_mode")
        if ctx_mode:
            return ctx_mode

        message_lower = message.lower()
        scores = context.get("scores", {})

        win_words = ["did it", "completed", "achieved", "finished", "proud", "nailed"]
        if any(w in message_lower for w in win_words):
            return "celebrate"

        struggle_words = ["stuck", "struggling", "can't", "failed", "hard", "help"]
        if any(w in message_lower for w in struggle_words):
            return "support"

        if scores.get("momentum_state") == "rising":
            return "challenge"

        return "guide"

    async def _get_daily_context(self, user_id: str, db: AsyncSession) -> str:
        result = await db.execute(
            text("""
                SELECT
                    dt.title,
                    dt.status AS task_status,
                    r.sentiment AS reflection_sentiment,
                    r.submitted_at AS reflected_at
                FROM daily_tasks dt
                LEFT JOIN reflections r ON r.task_id = dt.id
                WHERE dt.user_id = :user_id
                  AND dt.scheduled_date = CURRENT_DATE
                LIMIT 1
            """),
            {"user_id": user_id},
        )
        row = result.fetchone()

        if not row:
            return "No task scheduled for today yet."

        lines = [f"Today's task: {row.title} ({row.task_status})"]
        if row.reflected_at:
            lines.append(f"Reflected at: {row.reflected_at} | Sentiment: {row.reflection_sentiment}")
        else:
            lines.append("Not yet reflected on today's task.")

        return "\n".join(lines)

    async def _load_recent_messages(
        self, session_id: str, db: AsyncSession, limit: int = 10
    ) -> list[dict]:
        count_result = await db.execute(
            text("""
                SELECT COUNT(*) FROM ai_coach_messages
                WHERE session_id = :session_id
            """),
            {"session_id": session_id},
        )
        total_count = count_result.scalar() or 0

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

        # Counter update is analytics-only — timeout must never poison the transaction
        try:
            await db.execute(
                text("""
                    UPDATE ai_coach_sessions
                    SET message_count = message_count + 1, last_message_at = NOW()
                    WHERE id = :session_id
                """),
                {"session_id": session_id},
            )
        except Exception as e:
            logger.warning("session_counter_update_failed", session_id=session_id, error=str(e))
            await _safe_rollback(db)

        return msg_id

    async def _update_session_after_message(
        self, user_id: str, session_id: str, user_message: str, db: AsyncSession
    ) -> None:
        try:
            topic_keywords = [
                "goal", "motivation", "habit", "fear", "failure", "success",
                "discipline", "focus", "energy", "stress", "confidence",
                "morning", "evening", "work", "family", "health", "money",
                "forge", "field", "harbor", "war room",
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
        except Exception as e:
            logger.warning("topic_update_failed", error=str(e))
            await _safe_rollback(db)