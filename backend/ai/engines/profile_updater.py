"""
ai/engines/profile_updater.py

Profile Updater Engine

Synthesizes a week of behavioral data and evolves the user's identity profile.
Runs every Sunday night after the weekly review is generated.

This is the engine that makes the system truly adaptive over time.
It updates:
  - Behavioral patterns (with confidence scoring)
  - Identity trait scores (with velocity tracking)
  - Profile narrative (re-embedded for semantic memory)
  - Resistance triggers (cumulative, never removed)
  - Personality signals

The profile is a living document. This engine is its heartbeat.
"""

import json
from datetime import date, timedelta
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai.base import BaseAIEngine
from ai.memory.context_builder import context_builder
from ai.memory.retrieval import memory_retrieval
from ai.prompts.system_prompts import get_prompt

logger = structlog.get_logger()


class ProfileUpdaterEngine(BaseAIEngine):
    """
    Updates the identity profile weekly based on behavioral data synthesis.
    """

    engine_name = "profile_updater"
    default_temperature = 0.3  # deterministic: we want consistent profile updates

    async def update_profile(
        self,
        user_id: UUID | str,
        db: AsyncSession | None = None,
    ) -> dict:
        """
        Synthesize the past week's data and update the identity profile.
        Should be called every Sunday night after weekly review generation.
        """
        from core.database import get_db_context

        uid = str(user_id)

        async def _run(db: AsyncSession):
            week_start = date.today() - timedelta(days=6)
            week_end = date.today()

            # Get current context before update
            context = await context_builder.get_context(uid, db, force_refresh=True)
            context_str = context_builder.format_for_prompt(context)

            # Gather week data for the prompt
            week_data = await self._gather_week_data(uid, week_start, week_end, db)

            system_prompt = get_prompt("profile_updater").format(
                user_context=context_str,
                week_data=json.dumps(week_data, indent=2, default=str),
            )

            response_raw = await self._complete(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": "Update the identity profile based on this week's data."},
                ],
                user_id=uid,
                temperature=0.3,
                max_tokens=1500,
            )

            updates = self._parse_json(response_raw, fallback={})

            if not updates:
                logger.warning("profile_updater_empty_response", user_id=uid)
                return {}

            # Apply all updates to the database
            await self._apply_profile_updates(uid, updates, db)
            await self._update_trait_scores(uid, updates.get("trait_score_updates", []), db)
            await self._upsert_behavioral_patterns(uid, updates.get("new_behavioral_patterns", []), db)

            # Re-embed the updated profile summary for semantic memory
            profile_summary = updates.get("profile_summary")
            if profile_summary:
                await memory_retrieval.store_profile_embedding(uid, profile_summary, db)

            # Invalidate context cache — profile has fundamentally changed
            await context_builder.invalidate(uid)

            # Advance onboarding to active if still in strategy_generated
            await db.execute(
                text("""
                    UPDATE users SET onboarding_status = 'active'
                    WHERE id = :user_id
                      AND onboarding_status = 'strategy_generated'
                """),
                {"user_id": uid},
            )

            logger.info(
                "profile_updated",
                user_id=uid,
                traits_updated=len(updates.get("trait_score_updates", [])),
                patterns_added=len(updates.get("new_behavioral_patterns", [])),
            )

            return updates

        if db:
            return await _run(db)
        else:
            async with get_db_context() as db:
                return await _run(db)

    async def _gather_week_data(
        self, user_id: str, week_start: date, week_end: date, db: AsyncSession
    ) -> dict:
        """Collect comprehensive week data for the AI to analyze."""

        # Task and reflection stats
        stats_result = await db.execute(
            text("""
                SELECT
                    COUNT(*) FILTER (WHERE task_completed) as tasks_done,
                    COUNT(*) as days_tracked,
                    AVG(CASE WHEN task_completed THEN 1.0 ELSE 0.0 END) * 100 as consistency_pct
                FROM progress_metrics
                WHERE user_id = :user_id
                  AND metric_date BETWEEN :start AND :end
            """),
            {"user_id": user_id, "start": week_start, "end": week_end},
        )
        stats_row = stats_result.fetchone()

        # Reflection sentiments and themes
        reflections_result = await db.execute(
            text("""
                SELECT
                    reflection_date,
                    sentiment,
                    depth_score,
                    key_themes,
                    resistance_detected,
                    breakthrough_detected,
                    emotional_tone,
                    ai_insight
                FROM reflections
                WHERE user_id = :user_id
                  AND reflection_date BETWEEN :start AND :end
                ORDER BY reflection_date
            """),
            {"user_id": user_id, "start": week_start, "end": week_end},
        )
        reflections = [
            {
                "date": str(row.reflection_date),
                "sentiment": row.sentiment,
                "depth_score": float(row.depth_score) if row.depth_score else None,
                "themes": row.key_themes or [],
                "resistance": row.resistance_detected,
                "breakthrough": row.breakthrough_detected,
                "emotional_tone": row.emotional_tone,
                "insight": row.ai_insight,
            }
            for row in reflections_result.fetchall()
        ]

        # Current trait scores
        traits_result = await db.execute(
            text("""
                SELECT name, current_score, target_score, velocity, category
                FROM identity_traits
                WHERE user_id = :user_id AND is_active = TRUE
                ORDER BY current_score ASC
            """),
            {"user_id": user_id},
        )
        traits = [
            {
                "name": row.name,
                "current_score": float(row.current_score),
                "target_score": float(row.target_score),
                "velocity": float(row.velocity),
                "category": row.category,
            }
            for row in traits_result.fetchall()
        ]

        # Coach conversation themes this week
        coach_result = await db.execute(
            text("""
                SELECT DISTINCT unnest(key_topics) as topic
                FROM ai_coach_messages
                WHERE user_id = :user_id
                  AND created_at::date BETWEEN :start AND :end
                  AND key_topics IS NOT NULL
                  AND role = 'user'
                LIMIT 10
            """),
            {"user_id": user_id, "start": week_start, "end": week_end},
        )
        coach_themes = [row[0] for row in coach_result.fetchall() if row[0]]

        return {
            "week_start": str(week_start),
            "week_end": str(week_end),
            "stats": {
                "tasks_completed": stats_row.tasks_done or 0 if stats_row else 0,
                "days_tracked": stats_row.days_tracked or 0 if stats_row else 0,
                "consistency_pct": float(stats_row.consistency_pct) if stats_row and stats_row.consistency_pct else 0.0,
            },
            "reflections": reflections,
            "current_traits": traits,
            "coach_themes": coach_themes,
        }

    async def _apply_profile_updates(
        self, user_id: str, updates: dict, db: AsyncSession
    ) -> None:
        """Apply top-level profile field updates."""
        field_map = {
            "consistency_pattern": "consistency_pattern",
            "motivation_style": "motivation_style",
            "execution_style": "execution_style",
            "peak_performance_time": "peak_performance_time",
        }

        update_parts = []
        params = {"user_id": user_id}

        for key, col in field_map.items():
            if updates.get(key):
                update_parts.append(f"{col} = :{key}")
                params[key] = updates[key]

        # Resistance triggers are cumulative
        if updates.get("resistance_triggers"):
            update_parts.append(
                "resistance_triggers = array(SELECT DISTINCT unnest(COALESCE(resistance_triggers, '{}') || :new_triggers::text[]))"
            )
            params["new_triggers"] = updates["resistance_triggers"]

        if not update_parts:
            return

        update_parts.append("last_ai_update = NOW()")
        update_parts.append("profile_version = profile_version + 1")

        await db.execute(
            text(f"UPDATE identity_profiles SET {', '.join(update_parts)} WHERE user_id = :user_id"),
            params,
        )

    async def _update_trait_scores(
        self, user_id: str, trait_updates: list[dict], db: AsyncSession
    ) -> None:
        """Update trait scores and recalculate velocity."""
        for update in trait_updates:
            trait_name = update.get("trait_name")
            delta = float(update.get("score_delta", 0))

            if not trait_name or delta == 0:
                continue

            # Clamp delta: weekly changes should be modest
            delta = max(-0.5, min(0.5, delta))

            await db.execute(
                text("""
                    UPDATE identity_traits SET
                        current_score = GREATEST(1.0, LEAST(10.0, current_score + :delta)),
                        -- Velocity = exponential moving average of recent deltas
                        velocity = velocity * 0.7 + :delta * 0.3,
                        updated_at = NOW()
                    WHERE user_id = :user_id
                      AND LOWER(name) = LOWER(:trait_name)
                      AND is_active = TRUE
                """),
                {"user_id": user_id, "delta": delta, "trait_name": trait_name},
            )

    async def _upsert_behavioral_patterns(
        self, user_id: str, patterns: list[dict], db: AsyncSession
    ) -> None:
        """Insert new behavioral patterns or increase confidence on existing ones."""
        for pattern in patterns:
            pattern_name = pattern.get("pattern_name")
            if not pattern_name:
                continue

            await db.execute(
                text("""
                    INSERT INTO behavioral_patterns
                        (user_id, pattern_type, pattern_name, description,
                         confidence, evidence_count, first_detected, last_confirmed)
                    VALUES
                        (:user_id, :type, :name, :desc,
                         :confidence, 1, CURRENT_DATE, CURRENT_DATE)
                    ON CONFLICT DO NOTHING
                """),
                {
                    "user_id": user_id,
                    "type": pattern.get("pattern_type", "behavior"),
                    "name": pattern_name,
                    "desc": pattern.get("description"),
                    "confidence": pattern.get("confidence", 0.5),
                },
            )

            # If pattern already exists, update confidence and evidence count
            await db.execute(
                text("""
                    UPDATE behavioral_patterns SET
                        confidence = LEAST(0.95, confidence + 0.1),
                        evidence_count = evidence_count + 1,
                        last_confirmed = CURRENT_DATE
                    WHERE user_id = :user_id AND pattern_name = :name
                """),
                {"user_id": user_id, "name": pattern_name},
            )
