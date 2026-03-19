"""
services/scheduler.py

Background job scheduler using APScheduler.
Runs nightly AI jobs that power the adaptive system.
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

    scheduler.add_job(
        func=run_daily_task_generation,
        trigger=CronTrigger(hour="*", minute=0),
        id="daily_task_generation",
        name="Generate daily tasks for users at midnight local time",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    scheduler.add_job(
        func=run_morning_sweep,
        trigger=CronTrigger(hour=4, minute=0),
        id="morning_sweep",
        name="Morning sweep: Generate tasks for users missing today's task",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    scheduler.add_job(
        func=run_score_updates,
        trigger=CronTrigger(hour=2, minute=0),
        id="score_update",
        name="Update transformation scores for all active users",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    scheduler.add_job(
        func=run_weekly_review_generation,
        trigger=CronTrigger(day_of_week="mon", hour=2, minute=0),
        id="weekly_review",
        name="Generate weekly evolution reviews",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=7200,
    )

    scheduler.add_job(
        func=run_intervention_check,
        trigger=CronTrigger(hour=10, minute=0),
        id="intervention_check",
        name="Detect and notify users needing coach check-ins",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    scheduler.add_job(
        func=run_behavioral_snapshots,
        trigger=CronTrigger(day_of_week="mon", hour=2, minute=30),
        id="behavioral_snapshot",
        name="Build weekly behavioral fingerprints",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    scheduler.add_job(
        func=run_data_purge,
        trigger=CronTrigger(hour=3, minute=0),
        id="data_purge",
        name="Permanently delete accounts past grace period",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    scheduler.add_job(
        func=send_verification_reminders,
        trigger=CronTrigger(hour="*", minute=30),
        id="verification_reminders",
        name="Send email verification reminders at 24 hours",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    scheduler.start()
    logger.info("scheduler_started", job_count=len(scheduler.get_jobs()))
    return scheduler


# ─── Job Implementations ──────────────────────────────────────────────────────

async def send_verification_reminders() -> None:
    """Send reminder emails 24 hours after initial verification email"""
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import select
    from core.cache import acquire_lock, release_lock
    from core.database import get_db_context
    from services.email import email_service

    lock_acquired = await acquire_lock("verification_reminders", ttl_seconds=3600)
    if not lock_acquired:
        return

    try:
        async with get_db_context() as db:
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24)
            max_time = datetime.now(timezone.utc) - timedelta(hours=48)

            from db.models.user import User

            result = await db.execute(
                select(User).where(
                    User.email_verification_token.is_not(None),
                    User.email_verified_at.is_(None),
                    User.email_verification_sent_at <= cutoff_time,
                    User.email_verification_sent_at > max_time,
                    User.email_reminder_sent_at.is_(None)
                )
            )
            users = result.scalars().all()

            for user in users:
                try:
                    verification_url = f"{settings.frontend_url}/verify-email?token={user.email_verification_token}"
                    await email_service.send_verification_reminder(
                        to_email=user.email,
                        first_name=user.display_name,
                        verification_url=verification_url
                    )
                    user.email_reminder_sent_at = datetime.now(timezone.utc)
                    await db.commit()
                    logger.info("verification_reminder_sent", user_id=str(user.id))
                except Exception as e:
                    logger.error("verification_reminder_failed", user_id=str(user.id), error=str(e))
                    await db.rollback()
    finally:
        await release_lock("verification_reminders")


async def run_daily_task_generation() -> None:
    """
    Runs every hour. Generates tasks for users at midnight their local time.
    Also catches users who just activated and have no task yet.
    """
    from datetime import datetime, date, timedelta
    import pytz

    from core.cache import acquire_lock, release_lock
    from core.database import get_db_context

    lock_acquired = await acquire_lock("daily_task_generation", ttl_seconds=3600)
    if not lock_acquired:
        logger.warning("task_generation_lock_not_acquired")
        return

    try:
        current_utc_hour = datetime.now(pytz.UTC).hour

        async with get_db_context() as db:
            from sqlalchemy import text

            result = await db.execute(text("""
                SELECT DISTINCT u.id, u.timezone
                FROM users u
                JOIN goals g ON g.user_id = u.id AND g.status = 'active'
                WHERE u.is_active = TRUE
                  AND u.onboarding_status = 'active'
                  AND (
                    EXTRACT(HOUR FROM NOW() AT TIME ZONE u.timezone) = 0
                    OR
                    NOT EXISTS (
                        SELECT 1 FROM daily_tasks dt
                        WHERE dt.user_id = u.id
                        AND dt.scheduled_date = CURRENT_DATE
                    )
                  )
            """))
            user_rows = result.fetchall()

        if not user_rows:
            logger.info("no_users_for_task_generation", utc_hour=current_utc_hour)
            return

        user_ids = [str(row[0]) for row in user_rows]
        logger.info("task_generation_started", user_count=len(user_ids))

        from ai.engines.task_generator import TaskGeneratorEngine
        engine = TaskGeneratorEngine()

        success_count = 0
        error_count = 0

        for user_id in user_ids:
            try:
                tasks_generated = await engine.generate_daily_tasks_with_backlog(user_id)
                success_count += 1
                if tasks_generated > 1:
                    logger.info("backlog_tasks_generated", user_id=user_id, tasks_generated=tasks_generated)
            except Exception as e:
                error_count += 1
                logger.error("task_generation_user_failed", user_id=user_id, error=str(e))

        logger.info("task_generation_complete", success=success_count, errors=error_count)

    finally:
        await release_lock("daily_task_generation")


async def run_morning_sweep() -> None:
    """
    MORNING SWEEP (4:00 AM UTC)
    Catches any active users who don't have a task for today.

    FIX: Removed task_type = 'becoming' filter. Any task type counts --
    previously this caused the sweep to skip users who had identity_anchor
    or micro_action tasks, leaving them with no task showing on dashboard.
    """
    from datetime import datetime, date
    import pytz

    from core.cache import acquire_lock, release_lock
    from core.database import get_db_context

    lock_acquired = await acquire_lock("morning_sweep", ttl_seconds=3600)
    if not lock_acquired:
        logger.warning("morning_sweep_lock_not_acquired")
        return

    try:
        async with get_db_context() as db:
            from sqlalchemy import text

            # FIX: No task_type filter -- any task for today counts
            result = await db.execute(text("""
                SELECT DISTINCT u.id
                FROM users u
                JOIN goals g ON g.user_id = u.id AND g.status = 'active'
                WHERE u.is_active = TRUE
                  AND u.onboarding_status = 'active'
                  AND NOT EXISTS (
                      SELECT 1 FROM daily_tasks dt
                      WHERE dt.user_id = u.id
                        AND dt.scheduled_date = CURRENT_DATE
                  )
            """))
            user_rows = result.fetchall()

        if not user_rows:
            logger.info("morning_sweep_no_users_missing_tasks")
            return

        user_ids = [str(row[0]) for row in user_rows]
        logger.info("morning_sweep_started", user_count=len(user_ids), date=str(date.today()))

        from ai.engines.task_generator import TaskGeneratorEngine
        engine = TaskGeneratorEngine()

        success_count = 0
        error_count = 0

        for user_id in user_ids:
            try:
                task = await engine.generate_task_for_user(
                    user_id=user_id,
                    target_date=date.today(),
                    is_backlog=False,
                )

                if task:
                    success_count += 1
                    async with get_db_context() as db2:
                        from sqlalchemy import text as t
                        await db2.execute(t("""
                            UPDATE daily_tasks
                            SET generation_context = generation_context || '{"sweep_generated": true}'::jsonb
                            WHERE user_id = :user_id
                              AND scheduled_date = CURRENT_DATE
                        """), {"user_id": user_id})
                        await db2.commit()
                    logger.info("morning_sweep_task_generated", user_id=user_id, task_title=task.get("title"))
                else:
                    logger.info("morning_sweep_task_already_exists", user_id=user_id)

            except Exception as e:
                error_count += 1
                logger.error("morning_sweep_user_failed", user_id=user_id, error=str(e))

        logger.info(
            "morning_sweep_complete",
            success=success_count,
            errors=error_count,
            total_checked=len(user_ids),
        )

    finally:
        await release_lock("morning_sweep")


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
                WHERE is_active = TRUE AND onboarding_status = 'active'
            """))
            user_ids = [str(row[0]) for row in result.fetchall()]

            for user_id in user_ids:
                try:
                    await db.execute(text("SELECT update_user_scores(:user_id)"), {"user_id": user_id})
                    await db.execute(text("SELECT check_momentum_and_queue_intervention(:user_id)"), {"user_id": user_id})
                except Exception as e:
                    logger.error("score_update_failed", user_id=user_id, error=str(e))

        logger.info("score_updates_complete", user_count=len(user_ids))

    finally:
        await release_lock("score_updates")


async def run_weekly_review_generation() -> None:
    """Generate weekly evolution letters for all active users."""
    from core.cache import acquire_lock, release_lock
    from core.database import get_db_context

    lock_acquired = await acquire_lock("weekly_review_generation", ttl_seconds=7200)
    if not lock_acquired:
        logger.warning("weekly_review_lock_not_acquired")
        return

    try:
        async with get_db_context() as db:
            from sqlalchemy import text
            from ai.engines.reflection_analyzer import WeeklyReviewEngine

            result = await db.execute(text("""
                SELECT u.id
                FROM users u
                WHERE u.is_active = TRUE
                  AND u.onboarding_status = 'active'
                  AND NOT EXISTS (
                    SELECT 1 FROM weekly_reviews wr
                    WHERE wr.user_id = u.id
                      AND wr.week_start_date = date_trunc('week', CURRENT_DATE - INTERVAL '7 days')::DATE
                  )
            """))
            user_ids = [str(row[0]) for row in result.fetchall()]

        if not user_ids:
            logger.info("no_users_need_weekly_review")
            return

        logger.info("weekly_review_started", user_count=len(user_ids))
        engine = WeeklyReviewEngine()
        success_count = 0
        error_count = 0

        for user_id in user_ids:
            try:
                await engine.generate_weekly_review(user_id)
                success_count += 1
            except Exception as e:
                error_count += 1
                logger.error("weekly_review_failed", user_id=user_id, error=str(e))

        logger.info("weekly_review_complete", success=success_count, errors=error_count)

    finally:
        await release_lock("weekly_review_generation")


async def run_intervention_check() -> None:
    """Check for users who need coach interventions."""
    from core.cache import acquire_lock, release_lock
    from core.database import get_db_context

    lock_acquired = await acquire_lock("intervention_check", ttl_seconds=3600)
    if not lock_acquired:
        return

    try:
        async with get_db_context() as db:
            from sqlalchemy import text

            # FIXED: Removed pm.updated_at reference which doesn't exist in progress_metrics
            # Using metric_date instead to check for recent declining momentum
            result = await db.execute(text("""
                SELECT u.id
                FROM users u
                WHERE u.is_active = TRUE
                  AND u.onboarding_status = 'active'
                  AND EXISTS (
                    SELECT 1 FROM progress_metrics pm
                    WHERE pm.user_id = u.id
                      AND pm.momentum_state = 'declining'
                      AND pm.metric_date >= CURRENT_DATE - INTERVAL '7 days'
                  )
                  AND NOT EXISTS (
                    SELECT 1 FROM coach_interventions ci
                    WHERE ci.user_id = u.id
                      AND ci.created_at > NOW() - INTERVAL '7 days'
                  )
            """))
            user_ids = [str(row[0]) for row in result.fetchall()]

            for user_id in user_ids:
                try:
                    await db.execute(text("SELECT check_momentum_and_queue_intervention(:user_id)"), {"user_id": user_id})
                except Exception as e:
                    logger.error("intervention_check_failed", user_id=user_id, error=str(e))

        logger.info("intervention_check_complete", user_count=len(user_ids))

    finally:
        await release_lock("intervention_check")


async def run_behavioral_snapshots() -> None:
    """Build weekly behavioral fingerprints."""
    from core.cache import acquire_lock, release_lock
    from core.database import get_db_context

    lock_acquired = await acquire_lock("behavioral_snapshots", ttl_seconds=3600)
    if not lock_acquired:
        return

    try:
        async with get_db_context() as db:
            from sqlalchemy import text

            result = await db.execute(text("""
                SELECT id FROM users WHERE is_active = TRUE AND onboarding_status = 'active'
            """))
            user_ids = [str(row[0]) for row in result.fetchall()]

            for user_id in user_ids:
                try:
                    await db.execute(text("SELECT build_behavioral_snapshot(:user_id)"), {"user_id": user_id})
                except Exception as e:
                    logger.error("behavioral_snapshot_failed", user_id=user_id, error=str(e))

        logger.info("behavioral_snapshots_complete", user_count=len(user_ids))

    finally:
        await release_lock("behavioral_snapshots")


async def run_data_purge() -> None:
    """Permanently delete user data after grace period."""
    from core.cache import acquire_lock, release_lock
    from core.database import get_db_context

    lock_acquired = await acquire_lock("data_purge", ttl_seconds=3600)
    if not lock_acquired:
        return

    try:
        async with get_db_context() as db:
            from sqlalchemy import text

            result = await db.execute(text("""
                SELECT id, email FROM users
                WHERE deletion_scheduled_at IS NOT NULL
                  AND deletion_scheduled_at <= NOW()
                LIMIT 100
            """))
            users_to_purge = result.fetchall()

            if not users_to_purge:
                logger.info("no_users_to_purge")
                return

            purged_count = 0
            for user_id, email in users_to_purge:
                try:
                    await db.execute(text("""
                        UPDATE users SET
                            email = CONCAT('deleted.', MD5(id::text), '@deleted.onegoal.pro'),
                            display_name = NULL,
                            hashed_password = 'DELETED',
                            avatar_url = NULL,
                            timezone = 'UTC',
                            locale = 'en',
                            is_active = FALSE,
                            deletion_scheduled_at = NULL,
                            deletion_completed_at = NOW()
                        WHERE id = :user_id
                    """), {"user_id": str(user_id)})

                    await db.execute(text("DELETE FROM ai_coach_messages WHERE user_id = :user_id"), {"user_id": str(user_id)})
                    await db.execute(text("DELETE FROM onboarding_interview_state WHERE user_id = :user_id"), {"user_id": str(user_id)})
                    await db.execute(text("""
                        UPDATE progress_metrics
                        SET user_id = '00000000-0000-0000-0000-000000000000'
                        WHERE user_id = :user_id
                    """), {"user_id": str(user_id)})

                    purged_count += 1
                    logger.info("user_data_purged", user_id=str(user_id), original_email=email)

                except Exception as e:
                    logger.error("user_purge_failed", user_id=str(user_id), error=str(e))

            logger.info("data_purge_complete", purged_count=purged_count, total_found=len(users_to_purge))

    finally:
        await release_lock("data_purge")