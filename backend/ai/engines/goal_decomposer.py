"""
ai/engines/goal_decomposer.py

Goal Decomposition Engine

Takes a user's stated goal and transforms it into a complete
identity-based strategy: refined goal statement, required identity,
behavioral shifts, objectives, milestones, and identity traits.

This is a single-pass generation (not conversational).
The output is written directly to the goals, objectives, and identity_traits tables.

Two modes:
    1. decompose()   — Full decomposition, returns structured data
    2. clarify()     — Returns clarifying questions if goal is vague
"""

import json
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai.base import BaseAIEngine
from ai.memory.context_builder import context_builder
from ai.prompts.system_prompts import get_prompt

logger = structlog.get_logger()


class GoalDecomposerEngine(BaseAIEngine):
    """
    Decomposes a raw goal into a complete identity-based strategy.
    """

    engine_name = "goal_decomposer"
    default_temperature = 0.7

    async def decompose(
        self,
        user_id: UUID | str,
        raw_goal: str,
        db: AsyncSession,
    ) -> dict:
        """
        Full goal decomposition.

        Returns the full strategy dict and writes it to the database.
        If the goal needs clarification first, returns clarifying_questions instead.

        Returns:
            {
                goal_id: str,
                needs_clarification: bool,
                clarifying_questions: list[str],
                strategy: dict,         — full decomposed strategy
            }
        """
        uid = str(user_id)

        # Get user context for personalization
        context = await context_builder.get_context(uid, db)
        context_str = context_builder.format_for_prompt(context)

        system_prompt = get_prompt("goal_decomposer").format(
            user_context=context_str
        )

        response_raw = await self._complete(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"My goal: {raw_goal}"},
            ],
            user_id=uid,
            temperature=0.7,
            max_tokens=2000,
        )

        strategy = self._parse_json(response_raw, fallback={})

        if not strategy:
            raise ValueError("Goal decomposer returned empty response")

        # Check if clarification is needed
        clarifying = strategy.get("clarifying_questions", [])
        if clarifying:
            return {
                "goal_id": None,
                "needs_clarification": True,
                "clarifying_questions": clarifying,
                "strategy": None,
            }

        # Write strategy to database
        goal_id = await self._persist_strategy(uid, raw_goal, strategy, db)

        # Invalidate context cache — profile has changed
        await context_builder.invalidate(uid)

        logger.info("goal_decomposed", user_id=uid, goal_id=str(goal_id))

        return {
            "goal_id": str(goal_id),
            "needs_clarification": False,
            "clarifying_questions": [],
            "strategy": strategy,
        }

    async def decompose_with_answers(
        self,
        user_id: UUID | str,
        raw_goal: str,
        clarification_answers: str,
        db: AsyncSession,
    ) -> dict:
        """
        Decompose after receiving answers to clarifying questions.
        Called when the first decompose() returned needs_clarification=True.
        """
        uid = str(user_id)
        context = await context_builder.get_context(uid, db)
        context_str = context_builder.format_for_prompt(context)

        system_prompt = get_prompt("goal_decomposer").format(
            user_context=context_str
        )

        response_raw = await self._complete(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"My goal: {raw_goal}"},
                {"role": "assistant", "content": "I have a few clarifying questions..."},
                {"role": "user", "content": clarification_answers},
            ],
            user_id=uid,
            temperature=0.7,
            max_tokens=2000,
        )

        strategy = self._parse_json(response_raw, fallback={})
        goal_id = await self._persist_strategy(uid, raw_goal, strategy, db)
        await context_builder.invalidate(uid)

        return {
            "goal_id": str(goal_id),
            "needs_clarification": False,
            "clarifying_questions": [],
            "strategy": strategy,
        }

    async def _persist_strategy(
        self,
        user_id: str,
        raw_goal: str,
        strategy: dict,
        db: AsyncSession,
    ) -> UUID:
        """
        Write the decomposed strategy to goals, objectives, and identity_traits tables.
        Deactivates any existing active goal first.
        """
        # Archive any existing active goal
        await db.execute(
            text("""
                UPDATE goals SET status = 'paused', updated_at = NOW()
                WHERE user_id = :user_id AND status = 'active'
            """),
            {"user_id": user_id},
        )

        # Create the new goal
        result = await db.execute(
            text("""
                INSERT INTO goals (
                    user_id, status, raw_input, refined_statement, why_statement,
                    success_definition, required_identity, key_shifts,
                    estimated_timeline, difficulty_level, started_at
                ) VALUES (
                    :user_id, 'active', :raw_input, :refined, :why,
                    :success_def, :required_identity, :key_shifts::text[],
                    :timeline, :difficulty, NOW()
                )
                RETURNING id
            """),
            {
                "user_id": user_id,
                "raw_input": raw_goal,
                "refined": strategy.get("refined_statement", raw_goal),
                "why": strategy.get("why_statement"),
                "success_def": strategy.get("success_definition"),
                "required_identity": strategy.get("required_identity"),
                "key_shifts": strategy.get("key_shifts", []),
                "timeline": strategy.get("estimated_timeline_weeks", 12),
                "difficulty": strategy.get("difficulty_level", 5),
            },
        )
        goal_id = result.scalar()

        # Create objectives
        for obj in strategy.get("objectives", []):
            await db.execute(
                text("""
                    INSERT INTO objectives (
                        goal_id, user_id, title, description,
                        success_criteria, sequence_order, estimated_weeks
                    ) VALUES (
                        :goal_id, :user_id, :title, :description,
                        :success_criteria, :order, :weeks
                    )
                """),
                {
                    "goal_id": str(goal_id),
                    "user_id": user_id,
                    "title": obj.get("title"),
                    "description": obj.get("description"),
                    "success_criteria": obj.get("success_criteria"),
                    "order": obj.get("sequence_order", 1),
                    "weeks": obj.get("estimated_weeks", 4),
                },
            )

        # Deactivate existing traits for this user
        await db.execute(
            text("UPDATE identity_traits SET is_active = FALSE WHERE user_id = :user_id"),
            {"user_id": user_id},
        )

        # Create identity traits
        for trait in strategy.get("identity_traits", []):
            await db.execute(
                text("""
                    INSERT INTO identity_traits (
                        user_id, goal_id, name, description, category,
                        current_score, target_score, is_ai_generated
                    ) VALUES (
                        :user_id, :goal_id, :name, :description, :category,
                        :current_score, :target_score, TRUE
                    )
                """),
                {
                    "user_id": user_id,
                    "goal_id": str(goal_id),
                    "name": trait.get("name"),
                    "description": trait.get("description"),
                    "category": trait.get("category", "behavior"),
                    "current_score": trait.get("current_score", 4.0),
                    "target_score": trait.get("target_score", 8.0),
                },
            )

        # Advance onboarding status
        await db.execute(
            text("""
                UPDATE users SET onboarding_status = 'goal_defined'
                WHERE id = :user_id AND onboarding_status IN ('interview_complete', 'goal_defined')
            """),
            {"user_id": user_id},
        )

        return goal_id
