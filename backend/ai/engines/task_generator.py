"""
ai/engines/task_generator.py

Daily Task Generator Engine

Generates identity-focused becoming tasks with backlog support.
Handles missed days (max 3 backlog) and triggers interventions.
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
    Generates adaptive daily becoming tasks with backlog handling.
    """

    engine_name = "task_generator"
    default_temperature = 0.85

    # Fallback template tasks when AI generation fails
    FALLBACK_TASKS = [
        {
            "title": "15-Minute Identity Anchor",
            "description": "Spend 15 minutes on one action that reinforces who you're becoming. No perfection required—just presence.",
            "identity_focus": "Today you are someone who shows up, even when it's hard.",
            "execution_guidance": "Set a timer for 15 minutes. Work on one small thing related to your goal. When the timer ends, you're done.",
            "guidance": "Pick one specific action connected to your goal — not planning it, doing it. Set a timer for 15 minutes. Start before you feel ready. Stop when it ends.",
            "time_estimate_minutes": 15,
            "difficulty_level": 3,
            "task_type": "identity_anchor",
        },
        {
            "title": "The Minimum Effective Dose",
            "description": "Do the smallest possible version of your goal-related action. Consistency beats intensity.",
            "identity_focus": "Today you are someone who chooses consistency over perfection.",
            "execution_guidance": "Identify the absolute minimum action that still moves you forward. Do only that. Celebrate completion.",
            "guidance": "Write down the single smallest action that still counts as forward movement. Not the plan — the action. Do it now. That's the whole task.",
            "time_estimate_minutes": 10,
            "difficulty_level": 2,
            "task_type": "micro_action",
        },
        {
            "title": "Reflection in Action",
            "description": "Take one small step toward your goal, then pause to notice how it felt.",
            "identity_focus": "Today you are someone who learns by doing, not just planning.",
            "execution_guidance": "Spend 10 minutes on your goal. Then write one sentence about what you noticed.",
            "guidance": "Do 10 minutes of actual work on your goal — not thinking about it, doing it. Immediately after, write one honest sentence: what did you notice about yourself while you were doing it?",
            "time_estimate_minutes": 15,
            "difficulty_level": 3,
            "task_type": "becoming",
        },
    ]

    async def generate_daily_tasks_with_backlog(
        self,
        user_id: UUID | str,
        db: AsyncSession | None = None,
    ) -> int:
        """
        Generate today's task plus any missed tasks (max 3 backlog).
        Returns number of tasks generated.
        """
        from core.database import get_db_context

        uid = str(user_id)
        today = date.today()
        tasks_generated = 0

        async def _run(db: AsyncSession):
            nonlocal tasks_generated

            # Get dates that need tasks (today + missed days)
            dates_needed = await self._get_missed_task_dates(uid, today, db)

            # Limit to max 3 tasks (today + up to 2 missed)
            if len(dates_needed) > 3:
                # Keep only the most recent 3
                dates_needed = sorted(dates_needed)[-3:]
                logger.warning(
                    "backlog_exceeds_limit",
                    user_id=uid,
                    total_missed=len(dates_needed),
                    limiting_to=3
                )

            # Generate tasks for each date
            for task_date in dates_needed:
                try:
                    task = await self.generate_task_for_user(
                        user_id=uid,
                        target_date=task_date,
                        db=db,
                        is_backlog=(task_date < today)
                    )
                    if task:
                        tasks_generated += 1
                except Exception as e:
                    logger.error(
                        "backlog_task_generation_failed",
                        user_id=uid,
                        date=str(task_date),
                        error=str(e)
                    )
                    # Rollback aborted transaction before attempting fallback
                    try:
                        await db.rollback()
                    except Exception:
                        pass
                    # Try fallback template for this date
                    try:
                        await self._create_fallback_task(uid, task_date, db)
                        tasks_generated += 1
                    except Exception as fallback_error:
                        logger.error(
                            "fallback_task_failed",
                            user_id=uid,
                            date=str(task_date),
                            error=str(fallback_error)
                        )

            # Check if intervention needed (3 missed tasks)
            await self._trigger_intervention_if_needed(uid, db)

            return tasks_generated

        if db:
            return await _run(db)
        else:
            async with get_db_context() as db:
                return await _run(db)

    async def _get_missed_task_dates(
        self,
        user_id: str,
        today: date,
        db: AsyncSession,
    ) -> list[date]:
        """
        Find dates from last 3 days that don't have tasks.
        Returns list of dates that need tasks generated.
        """
        # Check last 3 days + today
        check_dates = [today - timedelta(days=i) for i in range(3, -1, -1)]

        result = await db.execute(
            text("""
                SELECT scheduled_date
                FROM daily_tasks
                WHERE user_id = :user_id
                  AND scheduled_date >= :start_date
                  AND scheduled_date <= :end_date
                  AND status != 'skipped'
            """),
            {
                "user_id": user_id,
                "start_date": check_dates[0],
                "end_date": check_dates[-1],
            },
        )
        existing_dates = {row[0] for row in result.fetchall()}

        # Return dates that don't have tasks
        missing_dates = [d for d in check_dates if d not in existing_dates]
        return missing_dates

    async def _trigger_intervention_if_needed(
        self,
        user_id: str,
        db: AsyncSession,
    ) -> None:
        """
        Check if user has 3+ missed tasks and trigger intervention.
        Creates a coach intervention message.
        """
        # Count missed tasks (pending tasks from past dates)
        result = await db.execute(
            text("""
                SELECT COUNT(*)
                FROM daily_tasks
                WHERE user_id = :user_id
                  AND scheduled_date < CURRENT_DATE
                  AND status = 'pending'
                  AND task_type = 'becoming'
            """),
            {"user_id": user_id},
        )
        missed_count = result.scalar() or 0

        if missed_count >= 3:
            # Check if intervention already exists for this reason
            existing = await db.execute(
                text("""
                    SELECT id FROM coach_interventions
                    WHERE user_id = :user_id
                      AND intervention_type = 'backlog_crisis'
                      AND created_at > NOW() - INTERVAL '3 days'
                    LIMIT 1
                """),
                {"user_id": user_id},
            )

            if not existing.fetchone():
                # Create intervention
                await db.execute(
                    text("""
                        INSERT INTO coach_interventions
                        (user_id, intervention_type, message, urgency)
                        VALUES
                        (:user_id, 'backlog_crisis', :message, 'high')
                    """),
                    {
                        "user_id": user_id,
                        "message": "You've missed 3 days of transformation work. This isn't about perfection—it's about choosing who you want to become. Start with just today's task. The past is data, not destiny."
                    }
                )
                await db.commit()

                logger.info(
                    "backlog_intervention_triggered",
                    user_id=user_id,
                    missed_count=missed_count
                )

    async def _create_fallback_task(
        self,
        user_id: str,
        task_date: date,
        db: AsyncSession,
    ) -> None:
        """Create a template fallback task when AI generation fails."""
        # Rotate through fallback tasks based on date
        fallback_index = task_date.day % len(self.FALLBACK_TASKS)
        fallback = self.FALLBACK_TASKS[fallback_index]

        await db.execute(
            text("""
                INSERT INTO daily_tasks (
                    user_id, scheduled_date, task_type,
                    identity_focus, title, description,
                    execution_guidance, guidance, time_estimate_minutes,
                    difficulty_level, generated_by_ai, generation_context
                ) VALUES (
                    :user_id, :date, :task_type,
                    :identity_focus, :title, :description,
                    :execution_guidance, :guidance, :time_estimate,
                    :difficulty, FALSE, CAST(:gen_context AS jsonb)
                )
            """),
            {
                "user_id": user_id,
                "date": task_date,
                "task_type": fallback["task_type"],
                "identity_focus": fallback["identity_focus"],
                "title": fallback["title"],
                "description": fallback["description"],
                "execution_guidance": fallback["execution_guidance"],
                "guidance": fallback["guidance"],
                "time_estimate": fallback["time_estimate_minutes"],
                "difficulty": fallback["difficulty_level"],
                "gen_context": json.dumps({"fallback": True, "reason": "ai_generation_failed"}),
            }
        )
        await db.commit()

    async def generate_task_for_user(
        self,
        user_id: UUID | str,
        target_date: date | None = None,
        db: AsyncSession | None = None,
        is_backlog: bool = False,
    ) -> dict:
        """
        Generate a task for a specific user and date.

        Args:
            is_backlog: If True, this is a missed day task (adjusts messaging)
        """
        from core.database import get_db_context

        uid = str(user_id)
        task_date = target_date or date.today() + timedelta(days=1)

        async def _run(db: AsyncSession):
            # Check if task already exists
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
            day_name = task_date.strftime("%A").lower()
            if day_name in ("saturday", "sunday"):
                time_available = time_avail.get("weekend", 45)
            else:
                time_available = time_avail.get("weekday", 30)
            time_available = max(15, min(120, time_available or 30))

            # Fetch enriched history context
            task_history_str = await self._get_task_history(uid, db)
            reflection_history_str = await self._get_reflection_history(uid, db)
            progress_context_str = await self._get_progress_context(context)

            # Get day-of-week context signal
            day_of_week, day_context = self._get_day_context(task_date)

            # Build the generation prompt
            system_prompt = get_prompt("task_generator").format(
                user_context=context_str,
                time_available=time_available,
                task_history=task_history_str,
                reflection_history=reflection_history_str,
                progress_context=progress_context_str,
                day_of_week=day_of_week,
                day_context=day_context,
            )

            # Adjust prompt for backlog tasks
            date_note = ""
            if is_backlog:
                date_note = f"\n\nNOTE: This task is for {task_date.strftime('%A, %B %d')} (a missed day). Keep the tone supportive and non-judgmental. Focus on 'starting fresh' rather than 'catching up'."

            # Build task type description
            task_type_desc = "a catch-up" if is_backlog else "tomorrow's"

            try:
                response_raw = await self._complete(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {
                            "role": "user",
                            "content": f"Generate {task_type_desc} becoming task for {task_date.strftime('%A, %B %d')}.{date_note}",
                        },
                    ],
                    user_id=uid,
                    temperature=0.85,
                    max_tokens=800,
                )

                task_data = self._parse_json(response_raw, fallback={})

                if not task_data or not task_data.get("title"):
                    raise ValueError("Empty task data from AI")

            except Exception as e:
                logger.error(
                    "ai_task_generation_failed",
                    user_id=uid,
                    date=str(task_date),
                    error=str(e)
                )
                # Use fallback template
                fallback_index = task_date.day % len(self.FALLBACK_TASKS)
                task_data = self.FALLBACK_TASKS[fallback_index].copy()
                task_data["fallback"] = True

            # Write task to database
            task_id = await self._persist_task(uid, task_date, task_data, context, db)

            logger.info(
                "task_generated",
                user_id=uid,
                date=str(task_date),
                task_title=task_data.get("title"),
                is_backlog=is_backlog,
                is_fallback=task_data.get("fallback", False),
                day_of_week=day_of_week,
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
                await db.rollback()

        return tasks

    async def _get_task_history(
        self, user_id: str, db: AsyncSession, days: int = 30
    ) -> str:
        """
        Fetch the last 30 days of tasks with date, title, and status.
        Returned as a formatted string for prompt injection.
        """
        result = await db.execute(
            text("""
                SELECT scheduled_date, title, status
                FROM daily_tasks
                WHERE user_id = :user_id
                  AND scheduled_date >= CURRENT_DATE - (:days * INTERVAL '1 day')
                ORDER BY scheduled_date DESC
                LIMIT 30
            """),
            {"user_id": user_id, "days": days},
        )
        rows = result.fetchall()

        if not rows:
            return "No task history yet."

        lines = []
        for row in rows:
            task_date, title, status = row
            lines.append(f"  {task_date} | {status} | {title}")

        return "\n".join(lines)

    async def _get_reflection_history(
        self, user_id: str, db: AsyncSession, limit: int = 10
    ) -> str:
        """
        Fetch the last 10 reflections with associated task title and what the user said.
        Returned as a formatted string for prompt injection.
        """
        result = await db.execute(
            text("""
                SELECT
                    r.created_at::date AS reflection_date,
                    dt.title AS task_title,
                    r.questions_answers,
                    r.depth_score
                FROM reflections r
                LEFT JOIN daily_tasks dt ON dt.user_id = r.user_id
                    AND dt.scheduled_date = r.created_at::date
                WHERE r.user_id = :user_id
                ORDER BY r.created_at DESC
                LIMIT :limit
            """),
            {"user_id": user_id, "limit": limit},
        )
        rows = result.fetchall()

        if not rows:
            return "No reflections yet."

        lines = []
        for row in rows:
            reflection_date, task_title, questions_answers, depth_score = row
            task_label = task_title or "unknown task"

            # Extract user responses from questions_answers JSONB
            user_responses = []
            if questions_answers:
                pairs = questions_answers if isinstance(questions_answers, list) else []
                for pair in pairs:
                    answer = pair.get("answer") or pair.get("response") or ""
                    if answer and len(answer) > 10:
                        user_responses.append(answer[:120])

            response_text = " / ".join(user_responses[:2]) if user_responses else "no response recorded"
            lines.append(
                f"  {reflection_date} | task: {task_label} | depth: {depth_score or 'n/a'} | said: \"{response_text}\""
            )

        return "\n".join(lines)

    async def _get_progress_context(self, context: dict) -> str:
        """
        Build a short progress summary string from the already-loaded context.
        No additional DB query needed.
        """
        scores = context.get("scores", {})
        retention = context.get("retention", {})

        streak = scores.get("streak", 0)
        momentum = scores.get("momentum_state", "holding")
        transformation = scores.get("transformation", 0)
        consistency = scores.get("consistency", 0)
        days_active = context.get("days_active", 0)
        days_since_last = retention.get("days_since_last_task", 0)

        lines = [
            f"Streak: {streak} days",
            f"Momentum: {momentum}",
            f"Transformation score: {transformation:.1f}/100",
            f"Consistency: {consistency:.1f}",
            f"Days active: {days_active}",
            f"Days since last task: {days_since_last}",
        ]
        return "\n".join(lines)

    def _get_day_context(self, task_date: date) -> tuple[str, str]:
        """
        Returns (day_name, day_context_string) for the task generation prompt.
        Day context is a soft signal — the AI weighs it alongside momentum and scores.
        Not an override. A user in high momentum on Sunday still gets a challenging task.
        """
        day = task_date.strftime("%A")
        contexts = {
            "Monday": (
                "Monday — re-entry day. The user may be coming back after a weekend gap. "
                "Favour tasks that feel like a clean recommitment to their identity — something "
                "that resets the anchor rather than continuing mid-thread. Keep friction low "
                "enough to guarantee completion. A won Monday builds the week."
            ),
            "Tuesday": (
                "Tuesday — the week is finding its rhythm. Energy is typically higher than Monday. "
                "A good day for tasks that require focus or a degree of stretch. "
                "If momentum is rising, use it. If it stalled on Monday, Tuesday is the recovery point."
            ),
            "Wednesday": (
                "Wednesday — mid-week. The highest-leverage day of the week for identity work. "
                "Momentum is either building or has visibly stalled. Calibrate difficulty accordingly. "
                "A strong Wednesday task often determines whether the week is a win."
            ),
            "Thursday": (
                "Thursday — late-week push. The user knows how the week has gone. "
                "If it has been strong, a slightly harder task capitalises on momentum. "
                "If it has been difficult, favour something achievable that closes the week on a completion."
            ),
            "Friday": (
                "Friday — energy and attention are shifting toward the weekend. "
                "Favour tasks that can be completed and felt within a shorter window. "
                "Avoid tasks requiring sustained multi-hour focus. "
                "A task that ends the work week with a clear identity moment works well here."
            ),
            "Saturday": (
                "Saturday — weekend. More time available but context has shifted away from desk work. "
                "Favour tasks that happen in real life rather than at a screen: physical action, "
                "a conversation, a real-world experience connected to their goal. "
                "Identity is built in the world, not just at the desk."
            ),
            "Sunday": (
                "Sunday — reflective and transitional. The week is closing, the next is approaching. "
                "A good day for consolidation: reviewing the week, clarifying one intention for Monday, "
                "or completing something that closes a loop. Avoid tasks that feel like starting something large. "
                "Tasks that help the user arrive at Monday with clarity and purpose are ideal."
            ),
        }
        return day, contexts.get(day, contexts["Monday"])

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

        # Store generation context
        generation_context = {
            "momentum_state": context.get("scores", {}).get("momentum_state"),
            "streak": context.get("scores", {}).get("streak"),
            "top_trait_gap": (context.get("traits") or [{}])[0].get("name") if context.get("traits") else None,
            "is_fallback": task_data.get("fallback", False),
        }

        result = await db.execute(
            text("""
                INSERT INTO daily_tasks (
                    user_id, goal_id, objective_id,
                    scheduled_date, task_type,
                    identity_focus, title, description,
                    execution_guidance, guidance, time_estimate_minutes,
                    difficulty_level, generated_by_ai, generation_context
                ) VALUES (
                    :user_id, :goal_id, :objective_id,
                    :date, :task_type,
                    :identity_focus, :title, :description,
                    :execution_guidance, :guidance, :time_estimate,
                    :difficulty, :generated_by_ai, CAST(:gen_context AS jsonb)
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
                "guidance": task_data.get("guidance", ""),
                "time_estimate": task_data.get("time_estimate_minutes", 30),
                "difficulty": task_data.get("difficulty_level", 5),
                "generated_by_ai": not task_data.get("fallback", False),
                "gen_context": json.dumps(generation_context),
            },
        )
        await db.commit()
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