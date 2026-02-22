"""
ai/memory/context_builder.py

Context Builder — the most important module in the AI layer.

Every AI engine needs a rich, structured snapshot of the user
to generate relevant, personalized output. This module assembles
that context from the database and caches it in Redis.

The context object is the shared language between all AI engines.
If you change this, update all engine prompts accordingly.

Context structure:
    {
        user_id, display_name, timezone, days_active,
        identity: { life_direction, vision, values, patterns, ... },
        scores: { transformation, consistency, depth, momentum, ... },
        goal: { statement, why, required_identity, progress, ... },
        active_objective: { title, description, progress, ... },
        traits: [{ name, current_score, target_score, gap, velocity }],
        recent_reflections: [{ date, sentiment, depth_score, themes }],
        today_task: { identity_focus, title, status },
        patterns: [{ type, name, confidence }],
        retention: { streak, days_since_last_task, needs_intervention },
        recent_coach_themes: [str],
    }
"""

import json
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.cache import cache_user_context, get_cached_user_context, invalidate_user_context

logger = structlog.get_logger()


class ContextBuilder:
    """
    Assembles and caches the user AI context.
    All AI engines instantiate this to get user context.
    """

    async def get_context(
        self,
        user_id: UUID | str,
        db: AsyncSession,
        force_refresh: bool = False,
    ) -> dict:
        """
        Get full user context. Checks Redis cache first.
        Pass force_refresh=True after profile updates.
        """
        uid = str(user_id)

        if not force_refresh:
            cached = await get_cached_user_context(uid)
            if cached:
                return cached

        # Build from database using the SQL function from migration 003
        result = await db.execute(
            text("SELECT get_user_ai_context(:user_id)"),
            {"user_id": uid},
        )
        context = result.scalar()

        if not context:
            raise ValueError(f"No context found for user {uid}")

        # Enrich with recent coach themes (not in the SQL function)
        context = await self._enrich_with_coach_themes(context, uid, db)

        # Cache for 5 minutes
        await cache_user_context(uid, context)

        return context

    async def invalidate(self, user_id: UUID | str) -> None:
        """
        Invalidate cached context.
        Called after: reflection submit, task complete, profile update, trait change.
        """
        await invalidate_user_context(str(user_id))

    async def _enrich_with_coach_themes(
        self, context: dict, user_id: str, db: AsyncSession
    ) -> dict:
        """
        Add recent coach conversation themes to context.
        These are critical for the coach to maintain continuity.
        """
        result = await db.execute(
            text("""
                SELECT DISTINCT unnest(key_topics) as topic
                FROM ai_coach_messages
                WHERE user_id = :user_id
                  AND role = 'user'
                  AND created_at > NOW() - INTERVAL '7 days'
                  AND key_topics IS NOT NULL
                LIMIT 10
            """),
            {"user_id": user_id},
        )
        themes = [row[0] for row in result.fetchall() if row[0]]
        context["recent_coach_themes"] = themes
        return context

    def format_for_prompt(self, context: dict) -> str:
        """
        Format the context object as a clean string for inclusion in AI prompts.
        Extracts the most relevant fields and formats them for readability.
        """
        identity = context.get("identity", {})
        scores = context.get("scores", {})
        goal = context.get("goal") or {}
        traits = context.get("traits") or []
        reflections = context.get("recent_reflections") or []
        patterns = context.get("patterns") or []
        retention = context.get("retention", {})

        # Format traits — only show top 3 with lowest progress
        trait_lines = []
        for t in (traits or [])[:3]:
            gap = t.get("gap", 0)
            velocity = t.get("velocity", 0)
            trend = "growing" if velocity > 0 else "needs work"
            trait_lines.append(
                f"  - {t['name']}: {t['current_score']}/10 → target {t['target_score']}/10 ({trend})"
            )

        # Format recent reflections
        reflection_lines = []
        for r in (reflections or [])[:3]:
            sentiment = r.get("sentiment", "neutral")
            themes = ", ".join(r.get("key_themes") or [])
            reflection_lines.append(
                f"  - {r['date']}: {sentiment} | themes: {themes or 'none noted'}"
            )

        # Format behavioral patterns
        pattern_lines = []
        for p in (patterns or [])[:3]:
            pattern_lines.append(f"  - {p.get('name', '')} (confidence: {p.get('confidence', 0):.0%})")

        momentum_state = scores.get("momentum_state", "holding")
        streak = scores.get("streak", 0)
        days_active = context.get("days_active", 0)

        lines = [
            f"USER CONTEXT",
            f"Name: {context.get('display_name', 'the user')}",
            f"Days active: {days_active} | Current streak: {streak} days | Momentum: {momentum_state}",
            f"",
            f"IDENTITY",
            f"Life direction: {identity.get('life_direction', 'not set')}",
            f"Vision: {identity.get('personal_vision', 'not set')}",
            f"Values: {', '.join(identity.get('core_values') or [])}",
            f"Motivation style: {identity.get('motivation_style', 'unknown')}",
            f"Execution style: {identity.get('execution_style', 'unknown')}",
            f"Resistance triggers: {', '.join(identity.get('resistance_triggers') or [])}",
            f"",
            f"CURRENT GOAL",
            f"Goal: {goal.get('statement', 'not set')}",
            f"Why it matters: {goal.get('why', 'not stated')}",
            f"Required identity: {goal.get('required_identity', 'not defined')}",
            f"Progress: {goal.get('progress_pct', 0):.0f}% | Weeks active: {goal.get('weeks_active', 0)}",
            f"",
            f"IDENTITY TRAITS (lowest progress first)",
        ] + (trait_lines if trait_lines else ["  No traits defined yet"]) + [
            f"",
            f"RECENT REFLECTION PATTERNS",
        ] + (reflection_lines if reflection_lines else ["  No reflections yet"]) + [
            f"",
            f"BEHAVIORAL PATTERNS",
        ] + (pattern_lines if pattern_lines else ["  None detected yet"]) + [
            f"",
            f"SCORES",
            f"Transformation: {scores.get('transformation', 0):.1f}/100",
            f"Consistency: {scores.get('consistency', 0):.1f} | Depth: {scores.get('depth', 0):.1f} | Alignment: {scores.get('alignment', 0):.1f}",
        ]

        if context.get("recent_coach_themes"):
            lines += [
                f"",
                f"RECENT COACH CONVERSATION THEMES",
                f"  {', '.join(context['recent_coach_themes'])}",
            ]

        needs_intervention = (retention or {}).get("needs_intervention", False)
        if needs_intervention:
            days_away = (retention or {}).get("days_since_last_task", 0)
            lines += [
                f"",
                f"⚠ INTERVENTION FLAG: User has been absent {days_away} days. Use support mode.",
            ]

        return "\n".join(lines)


# Singleton instance used throughout the app
context_builder = ContextBuilder()
