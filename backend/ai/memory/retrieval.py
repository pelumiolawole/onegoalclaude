"""
ai/memory/retrieval.py

Semantic memory retrieval using pgvector.

This is what gives the AI coach the ability to say:
"Three weeks ago you mentioned feeling stuck on mornings --
how has that been since you shifted your schedule?"

Instead of loading the full conversation history (expensive, hits token limits),
we embed each reflection and coach message, then retrieve the semantically
closest ones to the current context at inference time.

Two retrieval modes:
    1. Reflection memory  -- find past reflections similar to current query
    2. Coach memory       -- find past coach exchanges relevant to current message
"""

from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai.base import BaseAIEngine

logger = structlog.get_logger()


class MemoryRetrieval(BaseAIEngine):
    """
    Stores and retrieves semantic memories from pgvector.
    Used by the Coach and Reflection Analyzer engines.
    """

    engine_name = "memory"

    # ─── Embedding Storage ───────────────────────────────────────────

    async def store_reflection_embedding(
        self,
        reflection_id: UUID | str,
        text_content: str,
        db: AsyncSession,
    ) -> None:
        """
        Generate and store embedding for a reflection.

        FIX: Use f-string to inline the embedding value directly into the SQL.
        asyncpg cannot parse :param::vector syntax when mixed with $N params.
        Inlining is safe here because the embedding is a float array we generate
        ourselves -- not user input.
        """
        embedding = await self._embed(text_content)
        embedding_str = f"[{','.join(str(v) for v in embedding)}]"

        await db.execute(
            text(f"""
                UPDATE reflections
                SET content_embedding = '{embedding_str}'::vector
                WHERE id = :reflection_id
            """),
            {"reflection_id": str(reflection_id)},
        )

    async def store_message_embedding(
        self,
        message_id: UUID | str,
        text_content: str,
        db: AsyncSession,
    ) -> None:
        """Store embedding for a coach message."""
        embedding = await self._embed(text_content)
        embedding_str = f"[{','.join(str(v) for v in embedding)}]"

        await db.execute(
            text(f"""
                UPDATE ai_coach_messages
                SET content_embedding = '{embedding_str}'::vector
                WHERE id = :message_id
            """),
            {"message_id": str(message_id)},
        )

    async def store_profile_embedding(
        self,
        user_id: UUID | str,
        profile_summary: str,
        db: AsyncSession,
    ) -> None:
        """Update the identity profile embedding after profile changes."""
        embedding = await self._embed(profile_summary)
        embedding_str = f"[{','.join(str(v) for v in embedding)}]"

        await db.execute(
            text(f"""
                UPDATE identity_profiles
                SET profile_embedding = '{embedding_str}'::vector
                WHERE user_id = :user_id
            """),
            {"user_id": str(user_id)},
        )

    # ─── Semantic Retrieval ──────────────────────────────────────────

    async def retrieve_relevant_reflections(
        self,
        user_id: UUID | str,
        query: str,
        limit: int = 3,
        db: AsyncSession = None,
    ) -> list[dict]:
        """
        Find the most semantically relevant past reflections to the query.
        """
        query_embedding = await self._embed(query)
        embedding_str = f"[{','.join(str(v) for v in query_embedding)}]"

        result = await db.execute(
            text(f"""
                SELECT
                    r.id,
                    r.reflection_date,
                    r.questions_answers,
                    r.sentiment,
                    r.depth_score,
                    r.key_themes,
                    r.ai_insight,
                    r.resistance_detected,
                    r.breakthrough_detected,
                    1 - (r.content_embedding <=> '{embedding_str}'::vector) AS similarity
                FROM reflections r
                WHERE r.user_id = :user_id
                  AND r.content_embedding IS NOT NULL
                ORDER BY r.content_embedding <=> '{embedding_str}'::vector
                LIMIT :limit
            """),
            {
                "user_id": str(user_id),
                "limit": limit,
            },
        )

        rows = result.fetchall()
        return [
            {
                "id": str(row.id),
                "date": str(row.reflection_date),
                "answers": row.questions_answers,
                "sentiment": row.sentiment,
                "depth_score": float(row.depth_score) if row.depth_score else None,
                "themes": row.key_themes or [],
                "insight": row.ai_insight,
                "resistance": row.resistance_detected,
                "breakthrough": row.breakthrough_detected,
                "similarity": float(row.similarity),
            }
            for row in rows
        ]

    async def retrieve_relevant_coach_exchanges(
        self,
        user_id: UUID | str,
        query: str,
        limit: int = 3,
        db: AsyncSession = None,
    ) -> list[dict]:
        """
        Find past coach exchanges most relevant to the current message.
        """
        query_embedding = await self._embed(query)
        embedding_str = f"[{','.join(str(v) for v in query_embedding)}]"

        result = await db.execute(
            text(f"""
                WITH ranked_messages AS (
                    SELECT
                        m.id,
                        m.session_id,
                        m.content,
                        m.role,
                        m.created_at,
                        1 - (m.content_embedding <=> '{embedding_str}'::vector) AS similarity,
                        LEAD(m.content) OVER (
                            PARTITION BY m.session_id
                            ORDER BY m.created_at
                        ) AS ai_response
                    FROM ai_coach_messages m
                    WHERE m.user_id = :user_id
                      AND m.role = 'user'
                      AND m.content_embedding IS NOT NULL
                    ORDER BY m.content_embedding <=> '{embedding_str}'::vector
                    LIMIT :limit
                )
                SELECT * FROM ranked_messages WHERE similarity > 0.75
            """),
            {
                "user_id": str(user_id),
                "limit": limit,
            },
        )

        rows = result.fetchall()
        return [
            {
                "date": str(row.created_at.date()),
                "user_said": row.content,
                "coach_responded": row.ai_response,
                "similarity": float(row.similarity),
            }
            for row in rows
        ]

    def format_memories_for_prompt(
        self,
        reflections: list[dict],
        exchanges: list[dict],
    ) -> str:
        """Format retrieved memories into a prompt section."""
        lines = []

        if reflections:
            lines.append("RELEVANT PAST REFLECTIONS")
            for r in reflections:
                themes = ", ".join(r.get("themes") or [])
                lines.append(
                    f"  [{r['date']}] Sentiment: {r['sentiment']} | "
                    f"Themes: {themes or 'general'}"
                )
                if r.get("insight"):
                    lines.append(f"  AI noted: {r['insight'][:120]}...")

        if exchanges:
            lines.append("")
            lines.append("RELEVANT PAST COACH EXCHANGES")
            for ex in exchanges:
                lines.append(f"  [{ex['date']}] User said: \"{ex['user_said'][:100]}\"")
                if ex.get("coach_responded"):
                    lines.append(
                        f"  Coach said: \"{ex['coach_responded'][:100]}...\""
                    )

        return "\n".join(lines) if lines else ""


# Singleton
memory_retrieval = MemoryRetrieval()