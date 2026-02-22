"""
ai/engines/task_generator.py

Daily Task Generator Engine

Runs nightly (9pm UTC) to generate tomorrow's identity-focused becoming task.
Also generates an initial strategy when a goal is first defined.

The task generator is the heartbeat of the product.
Every task it generates is informed by:
    - Current identity traits (lowest-scoring get priority)
    - Recent reflection patterns (avoid triggering resistance)
    - Behavioral snapshots (know their peak performance time)
    - Momentum state (scale difficulty to current energy)
    - User's time availability
    - Day of week (lighter tasks on weekends if that's their pattern)
"""

import json
from datetime import date, timedelta
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai.base import BaseAIEngine
from ai.memory.context_builder import context_builder
from ai.prompts.system_prompts import get_prompt

logger = structlog.get_logger()


class TaskGeneratorEngine(BaseAIEngine):
    """
    Generates adaptive daily becoming tasks.
    """

    engine_name = "task_generator"
    default_temperature = 0.85  # higher creativity for varied tasks

    async def generate_task_for_user(
        self,
        user_id: UUID | str,
        target_date: date | None = None,
        db: AsyncSession | None = None,
    ) -> dict:
        """
        Generate tomorrow's task for a specific user.
        Called by the nightly scheduler for each active user.

        Returns the created task as a dict.
        """
        from core.database import get_db_context

        uid = str(user_id)
        task_date = target_date or date.today() + timedelta(days=1)

        async def _run(db: AsyncSession):
            # Check if task already exists for this date
            existing = await db.execute(
                text("""
                    SELECT id FROM daily_tasks
                    WHERE user_id = :user_id
                      AND scheduled_date = :date
                      AND task_type = 'becoming'
                """),
                {"user_id": uid, "date": task_date},
            )
            if existing.scalar():
                logger.info("task_already_exists", user_id=uid, date=str(task_date))
                return None

            # Get full user context
            context = await context_builder.get_context(uid, db, force_refresh=True)
            context_str = context_builder.format_for_prompt(context)

            # Get time availability
            identity = context.get("identity", {})
            time_avail = identity.get("time_availability") or {}
            # Determine time available based on day of week
            day_name = task_date.strftime("%A").lower()
            if day_name in ("saturday", "sunday"):
                time_available = time_avail.get("weekend", 45)
            elif task_date.strftime("%p") == "AM":
                time_available = time_avail.get("morning", 30)
            else:
                time_available = time_avail.get("evening", 45)
            time_available = max(15, min(120, time_available or 30))

            # Get recent task titles to avoid repetition
            recent_tasks = await self._get_recent_task_titles(uid, db)

            # Build the generation prompt
            system_prompt = get_prompt("task_generator").format(
                user_context=context_str,
                time_available=time_available,
            )

            avoid_note = ""
            if recent_tasks:
                avoid_note = f"\nAvoid generating tasks similar to these recent ones:\n" + \
                             "\n".join(f"  - {t}" for t in recent_tasks)

            response_raw = await self._complete(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": f"Generate tomorrow's becoming task for {task_date.strftime('%A, %B %d')}.{avoid_note}",
                    },
                ],
                user_id=uid,
                temperature=0.85,
                max_tokens=800,
            )

            task_data = self._parse_json(response_raw, fallback={})

            if not task_data or not task_data.get("title"):
                raise ValueError(f"Task generator returned empty/invalid data for user {uid}")

            # Write task to database
            task_id = await self._persist_task(uid, task_date, task_data, context, db)

            logger.info(
                "task_generated",
                user_id=uid,
                date=str(task_date),
                task_title=task_data.get("title"),
                task_type=task_data.get("task_type"),
            )

            return {**task_data, "id": str(task_id), "scheduled_date": str(task_date)}

        if db:
            return await _run(db)
        else:
            async with get_db_context() as db:
                return await _run(db)

    async def generate_initial_tasks(
        self,
        user_id: UUID | str,
        db: AsyncSession,
    ) -> list[dict]:
        """
        Generate the first 3 days of tasks when a user activates.
        Gives them immediate value and establishes the pattern.
        """
        uid = str(user_id)
        tasks = []
        today = date.today()

        for i in range(3):
            task_date = today + timedelta(days=i)
            try:
                task = await self.generate_task_for_user(uid, target_date=task_date, db=db)
                if task:
                    tasks.append(task)
            except Exception as e:
                logger.error(
                    "initial_task_generation_failed",
                    user_id=uid,
                    day=i,
                    error=str(e),
                )

        return tasks

    async def _get_recent_task_titles(
        self, user_id: str, db: AsyncSession, days: int = 7
    ) -> list[str]:
        """Get titles of tasks from the last N days to avoid repetition."""
        result = await db.execute(
            text("""
                SELECT title FROM daily_tasks
                WHERE user_id = :user_id
                  AND scheduled_date >= CURRENT_DATE - :days
                ORDER BY scheduled_date DESC
                LIMIT 7
            """),
            {"user_id": user_id, "days": days},
        )
        return [row[0] for row in result.fetchall() if row[0]]

    async def _persist_task(
        self,
        user_id: str,
        task_date: date,
        task_data: dict,
        context: dict,
        db: AsyncSession,
    ) -> UUID:
        """Write the generated task to the database."""
        goal = context.get("goal") or {}
        goal_id = goal.get("id")

        # Find current active objective
        obj_id = await self._get_current_objective_id(user_id, db)

        # Store a snapshot of the context used for generation (for debugging/analysis)
        generation_context = {
            "momentum_state": context.get("scores", {}).get("momentum_state"),
            "streak": context.get("scores", {}).get("streak"),
            "top_trait_gap": (context.get("traits") or [{}])[0].get("name") if context.get("traits") else None,
        }

        result = await db.execute(
            text("""
                INSERT INTO daily_tasks (
                    user_id, goal_id, objective_id,
                    scheduled_date, task_type,
                    identity_focus, title, description,
                    execution_guidance, time_estimate_minutes,
                    difficulty_level, generated_by_ai, generation_context
                ) VALUES (
                    :user_id, :goal_id, :objective_id,
                    :date, :task_type,
                    :identity_focus, :title, :description,
                    :execution_guidance, :time_estimate,
                    :difficulty, TRUE, :gen_context::jsonb
                )
                RETURNING id
            """),
            {
                "user_id": user_id,
                "goal_id": goal_id,
                "objective_id": str(obj_id) if obj_id else None,
                "date": task_date,
                "task_type": task_data.get("task_type", "becoming"),
                "identity_focus": task_data.get("identity_focus", ""),
                "title": task_data.get("title", ""),
                "description": task_data.get("description", ""),
                "execution_guidance": task_data.get("execution_guidance", ""),
                "time_estimate": task_data.get("time_estimate_minutes", 30),
                "difficulty": task_data.get("difficulty_level", 5),
                "gen_context": json.dumps(generation_context),
            },
        )
        return result.scalar()

    async def _get_current_objective_id(self, user_id: str, db: AsyncSession):
        """Get the ID of the first in-progress or upcoming objective."""
        result = await db.execute(
            text("""
                SELECT o.id FROM objectives o
                JOIN goals g ON g.id = o.goal_id
                WHERE g.user_id = :user_id AND g.status = 'active'
                  AND o.status IN ('in_progress', 'upcoming')
                ORDER BY o.sequence_order ASC
                LIMIT 1
            """),
            {"user_id": user_id},
        )
        row = result.fetchone()
        return row[0] if row else None
