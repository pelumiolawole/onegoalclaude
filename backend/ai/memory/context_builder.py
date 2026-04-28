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

        # Enhanced Coach Memory (V2)
        last_session: { summary, closing_insight, days_since },
        active_patterns: [{ name, type, description, first_seen }],
        recent_moments: [{ type, content, when, trait_referenced }],
        current_coach_mode: str,  # guide|support|challenge|celebrate|intervention|crisis
        session_continuity: { opening_hook, pending_follow_up, last_commitment },

        # Goal completion (invisible to user, surfaces in coach prompt)
        goal_completion_context: str,  # "" when normal, instruction text when approaching completion
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

        # Commitment statement — written by user at activation
        commitment_result = await db.execute(
            text("""
                SELECT commitment_statement
                FROM identity_profiles
                WHERE user_id = CAST(:user_id AS uuid)
            """),
            {"user_id": uid},
        )
        commitment_row = commitment_result.fetchone()
        if commitment_row and commitment_row[0]:
            context["user_commitment"] = commitment_row[0]

        # Enrich with recent coach themes (not in the SQL function)
        context = await self._enrich_with_coach_themes(context, uid, db)

        # Enhanced coach memory (V2)
        context = await self._enrich_with_session_memory(context, uid, db)
        context = await self._enrich_with_active_patterns(context, uid, db)
        context = await self._enrich_with_recent_moments(context, uid, db)
        context = await self._determine_coach_mode(context, uid, db)

        # Goal completion context — populates {goal_completion_context} in coach prompt.
        # Empty string for normal users. Instruction text when approaching_completion is flagged.
        context = await self._enrich_with_goal_completion_context(context, uid, db)

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

    # =========================================================================
    # Enhanced Coach Memory Methods (V2)
    # =========================================================================

    async def _enrich_with_session_memory(
        self, context: dict, user_id: str, db: AsyncSession
    ) -> dict:
        """
        Pull last session summary, closing insights, and continuity hooks.
        Enables the coach to open with "Last time we talked about..."
        """
        result = await db.execute(
            text("""
                SELECT
                    id,
                    session_start,
                    session_end,
                    opening_context,
                    closing_insight,
                    session_goal,
                    emotional_arc,
                    coach_mode_used,
                    next_session_hook,
                    EXTRACT(EPOCH FROM (NOW() - session_end))/86400 as days_since
                FROM coach_sessions
                WHERE user_id = :user_id
                  AND session_end IS NOT NULL
                ORDER BY session_end DESC
                LIMIT 1
            """),
            {"user_id": user_id},
        )
        row = result.fetchone()

        if row:
            context["last_session"] = {
                "session_id": str(row[0]),
                "session_start": str(row[1]) if row[1] else None,
                "session_end": str(row[2]) if row[2] else None,
                "opening_context": row[3],
                "closing_insight": row[4],
                "session_goal": row[5],
                "emotional_arc": row[6],
                "coach_mode_used": row[7],
                "next_session_hook": row[8],
                "days_since": round(row[9], 1) if row[9] else None,
            }
            context["session_continuity"] = {
                "opening_hook": row[3] or row[8],
                "pending_follow_up": row[8],
                "last_commitment": None,
                "time_away": self._format_time_away(row[9]),
            }
        else:
            context["last_session"] = None
            context["session_continuity"] = None

        return context

    async def _enrich_with_active_patterns(
        self, context: dict, user_id: str, db: AsyncSession
    ) -> dict:
        """
        Pull recognized behavioral patterns for this user.
        Enables the coach to say "You tend to..." or "This is your pattern..."
        """
        result = await db.execute(
            text("""
                SELECT
                    pattern_name,
                    pattern_type,
                    description,
                    confidence_score,
                    first_observed,
                    last_observed,
                    evidence_count
                FROM coach_patterns
                WHERE user_id = :user_id
                  AND is_active = TRUE
                  AND confidence_score >= 0.6
                ORDER BY confidence_score DESC, last_observed DESC
                LIMIT 5
            """),
            {"user_id": user_id},
        )

        patterns = []
        for row in result.fetchall():
            patterns.append({
                "name": row[0],
                "type": row[1],
                "description": row[2],
                "confidence": float(row[3]),
                "first_seen": str(row[4]) if row[4] else None,
                "last_seen": str(row[5]) if row[5] else None,
                "evidence_count": row[6],
            })

        context["active_patterns"] = patterns
        context["patterns"] = [
            {"name": p["name"], "confidence": p["confidence"], "type": p["type"]}
            for p in patterns
        ]
        return context

    async def _enrich_with_recent_moments(
        self, context: dict, user_id: str, db: AsyncSession
    ) -> dict:
        """
        Pull recent breakthroughs, resistance moments, commitments, vulnerabilities.
        Enables the coach to reference specific moments: "Remember when you said..."
        """
        result = await db.execute(
            text("""
                SELECT
                    moment_type,
                    moment_content,
                    coach_observation,
                    user_language,
                    emotional_tone,
                    trait_referenced,
                    created_at,
                    EXTRACT(EPOCH FROM (NOW() - created_at))/86400 as days_ago
                FROM coach_moments
                WHERE user_id = :user_id
                ORDER BY created_at DESC
                LIMIT 10
            """),
            {"user_id": user_id},
        )

        moments = []
        recent_commitments = []

        for row in result.fetchall():
            moment = {
                "type": row[0],
                "content": row[1],
                "coach_observation": row[2],
                "user_language": row[3],
                "emotional_tone": row[4],
                "trait_referenced": row[5],
                "when": str(row[6]) if row[6] else None,
                "days_ago": round(row[7], 1) if row[7] else None,
            }
            moments.append(moment)
            if row[0] == "commitment" and row[7] and row[7] < 7:
                recent_commitments.append({
                    "commitment": row[1],
                    "days_ago": round(row[7], 1),
                })

        context["recent_moments"] = moments
        if context.get("session_continuity") and recent_commitments:
            context["session_continuity"]["last_commitment"] = recent_commitments[0]

        return context

    async def _determine_coach_mode(
        self, context: dict, user_id: str, db: AsyncSession
    ) -> dict:
        """
        Determine which coaching mode to use based on user state.
        Modes: guide|support|challenge|celebrate|intervention|crisis
        """
        scores = context.get("scores", {})
        retention = context.get("retention", {})
        last_session = context.get("last_session", {})

        crisis_result = await db.execute(
            text("""
                SELECT 1 FROM coach_safety_flags
                WHERE user_id = :user_id
                  AND severity IN ('high', 'immediate')
                  AND admin_resolved = FALSE
                LIMIT 1
            """),
            {"user_id": user_id},
        )
        if crisis_result.fetchone():
            context["current_coach_mode"] = "crisis"
            return context

        days_since = last_session.get("days_since", 0) if last_session else 0
        needs_intervention = retention.get("needs_intervention", False)
        momentum_state = scores.get("momentum_state", "holding")

        if needs_intervention or days_since > 3 or momentum_state == "critical":
            context["current_coach_mode"] = "intervention"
            return context

        recent_breakthrough = any(
            m.get("type") == "breakthrough" and m.get("days_ago", 999) < 2
            for m in context.get("recent_moments", [])
        )
        if recent_breakthrough:
            context["current_coach_mode"] = "celebrate"
            return context

        if momentum_state == "declining" or any(
            m.get("type") == "resistance" and m.get("days_ago", 999) < 1
            for m in context.get("recent_moments", [])
        ):
            context["current_coach_mode"] = "support"
            return context

        if momentum_state == "rising" and scores.get("consistency", 0) > 70:
            context["current_coach_mode"] = "challenge"
            return context

        context["current_coach_mode"] = "guide"
        return context

    async def _enrich_with_goal_completion_context(
        self, context: dict, user_id: str, db: AsyncSession
    ) -> dict:
        """
        Check for goal completion interventions and populate {goal_completion_context}
        for the coach system prompt.

        When a user's goal is flagged as approaching_completion by the weekly scheduler,
        two coach_interventions are created:
          - 'goal_approaching_completion': shifts coach to reflective/consolidation mode
          - 'reinterview_available' (Identity tier only): coach surfaces re-interview offer

        This method reads those interventions and builds the instruction string that
        gets injected into {goal_completion_context} in COACH_SYSTEM_V2.

        For users with no completion flag: returns empty string — no prompt change.
        The goal status check is done directly against the goals table, not just
        interventions, so it stays accurate even if interventions are manually cleared.
        """
        # Check if user's goal is in approaching_completion state
        goal_result = await db.execute(
            text("""
                SELECT
                    g.status,
                    g.approaching_completion_flagged_at,
                    g.completion_check_score,
                    EXTRACT(EPOCH FROM (NOW() - g.approaching_completion_flagged_at))/86400 AS days_since_flag,
                    u.subscription_plan
                FROM goals g
                JOIN users u ON u.id = g.user_id
                WHERE g.user_id = CAST(:user_id AS uuid)
                  AND g.status = 'approaching_completion'
                LIMIT 1
            """),
            {"user_id": user_id},
        )
        goal_row = goal_result.fetchone()

        if not goal_row:
            # Goal is not approaching completion — no change to coach prompt
            context["goal_completion_context"] = ""
            return context

        subscription_plan = (goal_row.subscription_plan or "spark").lower()
        days_since_flag = round(float(goal_row.days_since_flag or 0), 0)

        # Pull the most recent completion intervention message for context
        intervention_result = await db.execute(
            text("""
                SELECT intervention_type, message
                FROM coach_interventions
                WHERE user_id = CAST(:user_id AS uuid)
                  AND intervention_type IN ('goal_approaching_completion', 'reinterview_available')
                ORDER BY created_at DESC
                LIMIT 2
            """),
            {"user_id": user_id},
        )
        interventions = {row[0]: row[1] for row in intervention_result.fetchall()}

        # Build the completion context string for the prompt
        completion_lines = []

        if "goal_approaching_completion" in interventions:
            completion_lines.append(interventions["goal_approaching_completion"])

        # Add re-interview offer for Identity tier
        if subscription_plan == "identity" and "reinterview_available" in interventions:
            completion_lines.append("")
            completion_lines.append(interventions["reinterview_available"])

        context["goal_completion_context"] = "\n".join(completion_lines) if completion_lines else ""

        logger.debug(
            "goal_completion_context_set",
            user_id=user_id,
            days_since_flag=days_since_flag,
            is_identity_tier=(subscription_plan == "identity"),
        )

        return context

    def _format_time_away(self, days: float | None) -> str:
        """Format days since last session for natural language."""
        if days is None:
            return "a while"
        if days < 1:
            return "earlier today"
        if days < 2:
            return "yesterday"
        if days < 7:
            return f"{int(days)} days ago"
        if days < 14:
            return "last week"
        if days < 30:
            return "a few weeks ago"
        return "a while ago"

    # =========================================================================
    # Formatting for Prompts
    # =========================================================================

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

        last_session = context.get("last_session")
        active_patterns = context.get("active_patterns", [])
        recent_moments = context.get("recent_moments", [])
        session_continuity = context.get("session_continuity")
        current_mode = context.get("current_coach_mode", "guide")

        trait_lines = []
        for t in (traits or [])[:3]:
            gap = t.get("gap", 0)
            velocity = t.get("velocity", 0)
            trend = "growing" if velocity > 0 else "needs work"
            trait_lines.append(
                f"  - {t['name']}: {t['current_score']}/10 → target {t['target_score']}/10 ({trend})"
            )

        reflection_lines = []
        for r in (reflections or [])[:3]:
            sentiment = r.get("sentiment", "neutral")
            themes = ", ".join(r.get("key_themes") or [])
            reflection_lines.append(
                f"  - {r['date']}: {sentiment} | themes: {themes or 'none noted'}"
            )

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
            f"Commitment (in their own words): {context.get('user_commitment', 'not recorded')}",
            f"Commitment (in their own words): {context.get('user_commitment', 'not recorded')}",
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

        if last_session or active_patterns or recent_moments:
            lines += [
                f"",
                f"COACHING CONTEXT (Session Memory)",
            ]
            if last_session:
                lines += [
                    f"Last session: {self._format_time_away(last_session.get('days_since'))}",
                    f"Closing insight: {last_session.get('closing_insight', 'Not recorded')}",
                ]
                if last_session.get("next_session_hook"):
                    lines += [f"Follow-up: {last_session['next_session_hook']}"]

            if session_continuity and session_continuity.get("opening_hook"):
                lines += [f"Opening context: {session_continuity['opening_hook']}"]

            if active_patterns:
                lines += [f"", f"Recognized Patterns:"]
                for p in active_patterns[:3]:
                    lines += [f"  - {p['name']} ({p['type']}): {p['description'][:80]}..."]

            significant_moments = [
                m for m in recent_moments
                if m.get("type") in ["breakthrough", "commitment", "vulnerability"]
                and m.get("days_ago", 999) < 7
            ][:2]
            if significant_moments:
                lines += [f"", f"Recent Significant Moments:"]
                for m in significant_moments:
                    lines += [
                        f"  - {m['type'].upper()} ({int(m.get('days_ago', 0))} days ago): {m.get('user_language', m.get('content', ''))[:60]}..."
                    ]

            lines += [f"", f"Current Coaching Mode: {current_mode.upper()}"]

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