"""
ai/engines/reflection_analyzer.py

Reflection Analyzer Engine

Analyzes user's daily reflection responses to:
  1. Score reflection quality (depth score)
  2. Detect sentiment and emotional tone
  3. Extract trait evidence (positive and negative signals)
  4. Detect resistance or breakthrough episodes
  5. Generate personalized AI feedback to show the user
  6. Update identity profile traits and behavioral patterns
  7. Signal task difficulty adjustment for tomorrow

Also contains WeeklyReviewEngine — generates the weekly evolution letter.
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
from ai.utils.safety_filter import SafetyLevel, safety_filter

logger = structlog.get_logger()


class ReflectionAnalyzerEngine(BaseAIEngine):
    """
    Analyzes daily reflections and updates the identity profile.
    """

    engine_name = "reflection_analyzer"
    default_temperature = 0.3  # low temperature: scoring needs consistency

    async def analyze(
        self,
        user_id: UUID | str,
        reflection_id: UUID | str,
        questions_answers: list[dict],
        task_id: UUID | str | None,
        db: AsyncSession,
    ) -> dict:
        """
        Analyze a submitted reflection.

        questions_answers format:
            [{"question": "...", "answer": "...", "question_type": "execution|emotion|identity"}]

        Returns the analysis dict and writes it to the reflections table.
        """
        uid = str(user_id)
        rid = str(reflection_id)

        # Combine all answers into a single text for safety check and embedding
        full_text = " ".join(qa.get("answer", "") for qa in questions_answers)

        # Safety check
        safety_level = safety_filter.classify(full_text)
        if safety_level in (SafetyLevel.CRISIS, SafetyLevel.DISTRESS):
            safe_response = safety_filter.get_safe_response(safety_level)
            await safety_filter.log_safety_flag(
                user_id=uid,
                source_type="reflection",
                source_id=rid,
                level=safety_level,
                excerpt=full_text[:200],
                ai_response=safe_response,
                db=db,
            )
            # Store the safe response as AI feedback and mark resistance
            await self._save_analysis(
                reflection_id=rid,
                analysis={
                    "sentiment": "struggling",
                    "depth_score": 5.0,
                    "word_count": len(full_text.split()),
                    "emotional_tone": "distressed",
                    "key_themes": ["wellbeing"],
                    "resistance_detected": True,
                    "breakthrough_detected": False,
                    "ai_insight": "User expressed significant difficulty.",
                    "ai_feedback": safe_response,
                    "trait_evidence": [],
                    "tomorrow_signal": "lower",
                    "coach_flag": True,
                    "coach_flag_reason": f"Safety level: {safety_level.value}",
                },
                db=db,
            )
            return {"ai_feedback": safe_response, "safety_triggered": True}

        # Get user context
        context = await context_builder.get_context(uid, db)
        context_str = context_builder.format_for_prompt(context)

        # Get today's task context
        task_context = await self._get_task_context(task_id, db) if task_id else "No task context available."

        # Build analysis prompt
        system_prompt = get_prompt("reflection_analyzer").format(
            user_context=context_str,
            task_context=task_context,
        )

        # Format Q&A for the prompt
        qa_text = "\n".join(
            f"Q: {qa['question']}\nA: {qa.get('answer', '(no answer)')}"
            for qa in questions_answers
        )

        response_raw = await self._complete(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Reflection responses:\n\n{qa_text}"},
            ],
            user_id=uid,
            temperature=0.3,
            max_tokens=1200,
        )

        analysis = self._parse_json(response_raw, fallback={})
        analysis["word_count"] = len(full_text.split())

        # Save analysis to reflection record
        await self._save_analysis(rid, analysis, db)

        # Store embedding for semantic memory
        await memory_retrieval.store_reflection_embedding(rid, full_text, db)

        # Update identity traits based on evidence
        await self._update_traits(uid, analysis.get("trait_evidence", []), db)

        # Update behavioral patterns if resistance or breakthrough detected
        if analysis.get("resistance_detected") or analysis.get("breakthrough_detected"):
            await self._update_behavioral_patterns(uid, analysis, db)

        # Apply profile updates from analysis
        profile_updates = analysis.get("profile_updates", {})
        if profile_updates:
            await self._apply_profile_updates(uid, profile_updates, db)

        # Invalidate context cache
        await context_builder.invalidate(uid)

        logger.info(
            "reflection_analyzed",
            user_id=uid,
            reflection_id=rid,
            sentiment=analysis.get("sentiment"),
            depth_score=analysis.get("depth_score"),
            resistance=analysis.get("resistance_detected"),
            breakthrough=analysis.get("breakthrough_detected"),
        )

        return {
            "ai_feedback": analysis.get("ai_feedback", ""),
            "ai_insight": analysis.get("ai_insight", ""),
            "sentiment": analysis.get("sentiment"),
            "depth_score": analysis.get("depth_score"),
            "safety_triggered": False,
        }

    async def generate_reflection_questions(
        self,
        user_id: UUID | str,
        task_id: UUID | str,
        db: AsyncSession,
    ) -> list[dict]:
        """
        Generate 2-3 personalized reflection questions for today's task.
        Called when the user enters reflection mode.
        """
        uid = str(user_id)
        context = await context_builder.get_context(uid, db)
        task_context = await self._get_task_context(task_id, db)
        context_str = context_builder.format_for_prompt(context)

        momentum = context.get("scores", {}).get("momentum_state", "holding")

        prompt = f"""Generate 2-3 reflection questions for this person after completing their daily becoming task.

USER CONTEXT:
{context_str}

TODAY'S TASK:
{task_context}

CURRENT MOMENTUM: {momentum}

Rules:
- Always include one question about execution (what happened)
- Always include one question about identity (who they're becoming)
- If momentum is struggling/declining, include an emotional question
- If momentum is rising, include a growth edge question
- Questions should be specific to THIS task and THIS person — never generic
- Each question should be 1 sentence, open-ended, and thought-provoking

Return a JSON array:
[
  {{"question": "...", "question_type": "execution|emotion|identity|growth"}},
  ...
]
"""
        response_raw = await self._complete(
            messages=[{"role": "user", "content": prompt}],
            user_id=uid,
            temperature=0.7,
            max_tokens=400,
        )

        questions = self._parse_json(response_raw, fallback=[])
        if not isinstance(questions, list):
            # Fallback questions if generation fails
            return [
                {"question": "What actually happened when you did this today?", "question_type": "execution"},
                {"question": "What did this reveal about who you're becoming?", "question_type": "identity"},
            ]

        return questions

    async def _get_task_context(self, task_id, db: AsyncSession) -> str:
        """Get task details for context in analysis."""
        result = await db.execute(
            text("""
                SELECT identity_focus, title, description
                FROM daily_tasks WHERE id = :task_id
            """),
            {"task_id": str(task_id)},
        )
        row = result.fetchone()
        if not row:
            return "Task not found."
        return f"Identity focus: {row.identity_focus}\nTask: {row.title}\n{row.description}"

    async def _save_analysis(self, reflection_id: str, analysis: dict, db: AsyncSession) -> None:
        """Write analysis results back to the reflection record."""
        await db.execute(
            text("""
                UPDATE reflections SET
                    sentiment = :sentiment,
                    depth_score = :depth_score,
                    word_count = :word_count,
                    emotional_tone = :emotional_tone,
                    key_themes = :key_themes,
                    resistance_detected = :resistance,
                    breakthrough_detected = :breakthrough,
                    ai_insight = :ai_insight,
                    ai_feedback_shown = :ai_feedback,
                    trait_evidence = :trait_evidence::jsonb,
                    analyzed_at = NOW()
                WHERE id = :reflection_id
            """),
            {
                "reflection_id": reflection_id,
                "sentiment": analysis.get("sentiment", "neutral"),
                "depth_score": analysis.get("depth_score", 5.0),
                "word_count": analysis.get("word_count", 0),
                "emotional_tone": analysis.get("emotional_tone"),
                "key_themes": analysis.get("key_themes", []),
                "resistance": analysis.get("resistance_detected", False),
                "breakthrough": analysis.get("breakthrough_detected", False),
                "ai_insight": analysis.get("ai_insight"),
                "ai_feedback": analysis.get("ai_feedback"),
                "trait_evidence": json.dumps(analysis.get("trait_evidence", [])),
            },
        )

    async def _update_traits(
        self, user_id: str, trait_evidence: list[dict], db: AsyncSession
    ) -> None:
        """Update identity trait scores based on reflection evidence."""
        for evidence in trait_evidence:
            trait_name = evidence.get("trait_name")
            score_delta = float(evidence.get("score_delta", 0))
            signal = evidence.get("signal", "neutral")

            if not trait_name or score_delta == 0:
                continue

            # Clamp delta: never change a trait by more than 0.5 in one day
            score_delta = max(-0.5, min(0.5, score_delta))
            if signal == "negative":
                score_delta = -abs(score_delta)

            await db.execute(
                text("""
                    UPDATE identity_traits SET
                        current_score = GREATEST(1.0, LEAST(10.0, current_score + :delta)),
                        updated_at = NOW()
                    WHERE user_id = :user_id
                      AND LOWER(name) = LOWER(:trait_name)
                      AND is_active = TRUE
                """),
                {"user_id": user_id, "delta": score_delta, "trait_name": trait_name},
            )

    async def _update_behavioral_patterns(
        self, user_id: str, analysis: dict, db: AsyncSession
    ) -> None:
        """Log detected behavioral patterns from this reflection."""
        pattern_type = "breakthrough" if analysis.get("breakthrough_detected") else "resistance"
        signals = analysis.get("resistance_signals") or analysis.get("breakthrough_signals") or []
        pattern_name = signals[0] if signals else f"Unknown {pattern_type}"

        await db.execute(
            text("""
                INSERT INTO behavioral_patterns
                    (user_id, pattern_type, pattern_name, description, confidence,
                     evidence_count, first_detected, last_confirmed)
                VALUES
                    (:user_id, :type, :name, :desc, 0.5, 1, CURRENT_DATE, CURRENT_DATE)
                ON CONFLICT DO NOTHING
            """),
            {
                "user_id": user_id,
                "type": pattern_type,
                "name": pattern_name,
                "desc": f"Detected in reflection: {', '.join(signals[:3])}",
            },
        )

    async def _apply_profile_updates(
        self, user_id: str, updates: dict, db: AsyncSession
    ) -> None:
        """Apply partial updates to the identity profile from analysis signals."""
        if not updates:
            return

        update_parts = []
        params = {"user_id": user_id}

        if updates.get("resistance_triggers"):
            # Append new triggers, don't replace existing ones
            update_parts.append(
                "resistance_triggers = array(SELECT DISTINCT unnest(resistance_triggers || :new_triggers::text[]))"
            )
            params["new_triggers"] = updates["resistance_triggers"]

        if updates.get("consistency_pattern"):
            update_parts.append("consistency_pattern = :consistency_pattern")
            params["consistency_pattern"] = updates["consistency_pattern"]

        if updates.get("motivation_style"):
            update_parts.append("motivation_style = :motivation_style")
            params["motivation_style"] = updates["motivation_style"]

        if not update_parts:
            return

        await db.execute(
            text(f"UPDATE identity_profiles SET {', '.join(update_parts)} WHERE user_id = :user_id"),
            params,
        )


# ─── Weekly Review Engine ────────────────────────────────────────────────────

class WeeklyReviewEngine(BaseAIEngine):
    """
    Generates the weekly evolution letter — the highest-retention feature.
    Runs every Sunday evening.
    """

    engine_name = "weekly_review"
    default_temperature = 0.8  # warmer, more narrative

    async def generate_weekly_review(
        self,
        user_id: UUID | str,
        db: AsyncSession | None = None,
    ) -> dict:
        """
        Generate and store the weekly evolution letter.
        """
        from core.database import get_db_context

        uid = str(user_id)

        async def _run(db: AsyncSession):
            week_start = date.today() - timedelta(days=6)
            week_end = date.today()

            context = await context_builder.get_context(uid, db, force_refresh=True)
            context_str = context_builder.format_for_prompt(context)

            # Gather week's data
            week_data = await self._gather_week_data(uid, week_start, week_end, db)

            system_prompt = get_prompt("weekly_review").format(
                user_context=context_str,
                week_data=json.dumps(week_data, indent=2, default=str),
            )

            letter = await self._complete(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": "Write my weekly evolution letter."},
                ],
                user_id=uid,
                temperature=0.8,
                max_tokens=1000,
            )

            # Store the review
            await db.execute(
                text("""
                    INSERT INTO weekly_reviews (
                        user_id, week_start_date, week_end_date,
                        tasks_completed, tasks_total, reflections_submitted,
                        avg_depth_score, consistency_pct, score_delta,
                        evolution_letter, generated_at
                    ) VALUES (
                        :user_id, :week_start, :week_end,
                        :completed, :total, :reflections,
                        :avg_depth, :consistency, :score_delta,
                        :letter, NOW()
                    )
                    ON CONFLICT (user_id, week_start_date)
                    DO UPDATE SET evolution_letter = EXCLUDED.evolution_letter,
                                  generated_at = NOW()
                """),
                {
                    "user_id": uid,
                    "week_start": week_start,
                    "week_end": week_end,
                    **week_data["stats"],
                    "letter": letter,
                },
            )

            logger.info("weekly_review_generated", user_id=uid, week=str(week_start))
            return {"letter": letter, "week_data": week_data}

        if db:
            return await _run(db)
        else:
            async with get_db_context() as db:
                return await _run(db)

    async def _gather_week_data(
        self, user_id: str, week_start: date, week_end: date, db: AsyncSession
    ) -> dict:
        """Collect all data points for the week."""
        result = await db.execute(
            text("""
                SELECT
                    COUNT(*) FILTER (WHERE task_completed) AS completed,
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE reflection_submitted) AS reflections,
                    AVG(avg_depth_score) AS avg_depth,
                    AVG(CASE WHEN task_completed THEN 100.0 ELSE 0.0 END) AS consistency_pct,
                    MAX(transformation_score) - MIN(transformation_score) AS score_delta
                FROM progress_metrics
                WHERE user_id = :user_id
                  AND metric_date BETWEEN :start AND :end
            """),
            {"user_id": user_id, "start": week_start, "end": week_end},
        )
        row = result.fetchone()

        stats = {
            "completed": row.completed or 0,
            "total": row.total or 7,
            "reflections": row.reflections or 0,
            "avg_depth": float(row.avg_depth) if row.avg_depth else None,
            "consistency": float(row.consistency_pct) if row.consistency_pct else 0.0,
            "score_delta": float(row.score_delta) if row.score_delta else 0.0,
        }

        # Get reflection themes for the week
        themes_result = await db.execute(
            text("""
                SELECT DISTINCT unnest(key_themes) as theme
                FROM reflections
                WHERE user_id = :user_id
                  AND reflection_date BETWEEN :start AND :end
                  AND key_themes IS NOT NULL
                LIMIT 8
            """),
            {"user_id": user_id, "start": week_start, "end": week_end},
        )
        themes = [row[0] for row in themes_result.fetchall() if row[0]]

        return {"stats": stats, "themes": themes, "week_start": str(week_start), "week_end": str(week_end)}
