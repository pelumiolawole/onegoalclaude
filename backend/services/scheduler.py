"""
services/scheduler.py

Background job scheduler using APScheduler.
Runs nightly AI jobs that power the adaptive system.

Jobs:
    1. nightly_task_generation   — 9pm UTC daily
       Generates tomorrow's becoming task for every active user

    2. score_update              — 11pm UTC daily
       Computes and stores all transformation scores

    3. weekly_review_generation  — 8pm UTC Sunday
       Generates AI evolution letters for the past week

    4. intervention_check        — 10am UTC daily
       Detects users needing coach check-ins and queues notifications

    5. behavioral_snapshot       — 11:30pm UTC Sunday
       Builds weekly behavioral fingerprints for all active users
"""

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from core.config import settings

logger = structlog.get_logger()


async def start_scheduler() -> AsyncIOScheduler:
    """
    Initialize and start the APScheduler.
    Returns the scheduler instance so it can be shut down on app close.
    """
    scheduler = AsyncIOScheduler(timezone="UTC")

    # ── Job 1: Nightly task generation ────────────────────────────────
    scheduler.add_job(
        func=run_nightly_task_generation,
        trigger=CronTrigger(hour=settings.task_generation_utc_hour, minute=0),
        id="nightly_task_generation",
        name="Generate tomorrow's tasks for all active users",
        replace_existing=True,
        max_instances=1,      # never run two instances simultaneously
        misfire_grace_time=3600,  # if missed, run up to 1 hour late
    )

    # ── Job 2: Score update ───────────────────────────────────────────
    scheduler.add_job(
        func=run_score_updates,
        trigger=CronTrigger(hour=23, minute=0),
        id="score_update",
        name="Update transformation scores for all active users",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    # ── Job 3: Weekly review (Sunday only) ───────────────────────────
    scheduler.add_job(
        func=run_weekly_review_generation,
        trigger=CronTrigger(
            day_of_week="sun",
            hour=settings.weekly_review_utc_hour,
            minute=0,
        ),
        id="weekly_review",
        name="Generate weekly evolution reviews",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=7200,
    )

    # ── Job 4: Intervention check ─────────────────────────────────────
    scheduler.add_job(
        func=run_intervention_check,
        trigger=CronTrigger(hour=10, minute=0),
        id="intervention_check",
        name="Detect and notify users needing coach check-ins",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    # ── Job 5: Behavioral snapshot (Sunday) ──────────────────────────
    scheduler.add_job(
        func=run_behavioral_snapshots,
        trigger=CronTrigger(day_of_week="sun", hour=23, minute=30),
        id="behavioral_snapshot",
        name="Build weekly behavioral fingerprints",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    scheduler.start()
    logger.info("scheduler_started", job_count=len(scheduler.get_jobs()))
    return scheduler


# ─── Job Implementations ──────────────────────────────────────────────────────

async def run_nightly_task_generation() -> None:
    """
    For every active user with an active goal,
    generate tomorrow's identity focus and becoming task.
    Uses a distributed lock to prevent duplicate runs.
    """
    from core.cache import acquire_lock, release_lock
    from core.database import get_db_context

    lock_acquired = await acquire_lock("nightly_task_generation", ttl_seconds=3600)
    if not lock_acquired:
        logger.warning("task_generation_lock_not_acquired")
        return

    try:
        async with get_db_context() as db:
            from sqlalchemy import text

            # Get all users who need a task generated for tomorrow
            result = await db.execute(text("""
                SELECT u.id
                FROM users u
                JOIN goals g ON g.user_id = u.id AND g.status = 'active'
                WHERE u.is_active = TRUE
                  AND u.onboarding_status = 'active'
                  AND NOT EXISTS (
                    SELECT 1 FROM daily_tasks dt
                    WHERE dt.user_id = u.id
                      AND dt.scheduled_date = CURRENT_DATE + 1
                      AND dt.task_type = 'becoming'
                  )
            """))
            user_ids = [str(row[0]) for row in result.fetchall()]

        logger.info("task_generation_started", user_count=len(user_ids))

        # Import here to avoid circular imports at module load
        from ai.engines.task_generator import TaskGeneratorEngine

        engine = TaskGeneratorEngine()
        success_count = 0
        error_count = 0

        for user_id in user_ids:
            try:
                await engine.generate_task_for_user(user_id)
                success_count += 1
            except Exception as e:
                error_count += 1
                logger.error(
                    "task_generation_user_failed",
                    user_id=user_id,
                    error=str(e),
                )

        logger.info(
            "task_generation_complete",
            success=success_count,
            errors=error_count,
        )

    finally:
        await release_lock("nightly_task_generation")


async def run_score_updates() -> None:
    """Update transformation scores for all active users."""
    from core.cache import acquire_lock, release_lock
    from core.database import get_db_context

    lock_acquired = await acquire_lock("score_updates", ttl_seconds=3600)
    if not lock_acquired:
        return

    try:
        async with get_db_context() as db:
            from sqlalchemy import text

            result = await db.execute(text("""
                SELECT id FROM users
                WHERE is_active = TRUE
                  AND onboarding_status = 'active'
            """))
            user_ids = [str(row[0]) for row in result.fetchall()]

            for user_id in user_ids:
                try:
                    await db.execute(
                        text("SELECT update_user_scores(:user_id)"),
                        {"user_id": user_id},
                    )
                    # Also check if intervention is needed
                    await db.execute(
                        text("SELECT check_momentum_and_queue_intervention(:user_id)"),
                        {"user_id": user_id},
                    )
                except Exception as e:
                    logger.error("score_update_failed", user_id=user_id, error=str(e))

        logger.info("score_updates_complete", user_count=len(user_ids))

    finally:
        await release_lock("score_updates")


async def run_weekly_review_generation() -> None:
    """Generate weekly evolution letters for all active users."""
    from core.cache import acquire_lock, release_lock

    lock_acquired = await acquire_lock("weekly_review_generation", ttl_seconds=7200)
    if not lock_acquired:
        return

    try:
        from ai.engines.reflection_analyzer import WeeklyReviewEngine
        from core.database import get_db_context

        async with get_db_context() as db:
            from sqlalchemy import text

            result = await db.execute(text("""
                SELECT u.id FROM users u
                WHERE u.is_active = TRUE
                  AND u.onboarding_status = 'active'
                  AND NOT EXISTS (
                    SELECT 1 FROM weekly_reviews wr
                    WHERE wr.user_id = u.id
                      AND wr.week_start_date = date_trunc('week', CURRENT_DATE)::DATE
                  )
            """))
            user_ids = [str(row[0]) for row in result.fetchall()]

        engine = WeeklyReviewEngine()
        for user_id in user_ids:
            try:
                await engine.generate_weekly_review(user_id)
            except Exception as e:
                logger.error("weekly_review_failed", user_id=user_id, error=str(e))

        logger.info("weekly_reviews_complete", user_count=len(user_ids))

    finally:
        await release_lock("weekly_review_generation")


async def run_intervention_check() -> None:
    """Check for users needing proactive coach intervention."""
    from core.database import get_db_context

    async with get_db_context() as db:
        from sqlalchemy import text

        # The view from migration 003 identifies users needing intervention
        result = await db.execute(text("""
            SELECT user_id, days_since_last_task, momentum_state
            FROM users_needing_intervention
        """))
        users = result.fetchall()

        for user_id, days_since, momentum in users:
            try:
                # Queue a personalized coach check-in notification
                await db.execute(text("""
                    INSERT INTO notification_queue
                        (user_id, type, title, body, channel, scheduled_at)
                    VALUES (
                        :user_id,
                        'coach_checkin',
                        'Your coach is thinking of you',
                        'Something important is waiting for you today.',
                        'push',
                        NOW() + INTERVAL '1 hour'
                    )
                    ON CONFLICT DO NOTHING
                """), {"user_id": str(user_id)})
            except Exception as e:
                logger.error("intervention_queue_failed", user_id=str(user_id), error=str(e))

    logger.info("intervention_check_complete", flagged_users=len(users))


async def run_behavioral_snapshots() -> None:
    """Build weekly behavioral fingerprints for all active users."""
    from core.database import get_db_context

    async with get_db_context() as db:
        from sqlalchemy import text

        result = await db.execute(text("""
            SELECT id FROM users
            WHERE is_active = TRUE AND onboarding_status = 'active'
        """))
        user_ids = [str(row[0]) for row in result.fetchall()]

        from datetime import date, timedelta
        week_start = date.today() - timedelta(days=6)  # Monday

        for user_id in user_ids:
            try:
                await db.execute(
                    text("SELECT compute_behavioral_snapshot(:user_id, :week_start)"),
                    {"user_id": user_id, "week_start": week_start},
                )
            except Exception as e:
                logger.error("behavioral_snapshot_failed", user_id=user_id, error=str(e))

    logger.info("behavioral_snapshots_complete", user_count=len(user_ids))
