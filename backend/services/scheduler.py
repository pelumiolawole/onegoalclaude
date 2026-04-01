"""
services/scheduler.py

Background job scheduler using APScheduler.
Runs nightly AI jobs that power the adaptive system.
"""

import asyncio
import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from core.config import settings

logger = structlog.get_logger()


# ─── Nudge wrappers ───────────────────────────────────────────────────────────
# APScheduler with AsyncIOScheduler supports async job functions directly.
# These thin wrappers let us pass a named async function with a fixed argument
# instead of a lambda that would return a dropped coroutine.

async def _nudge_24h() -> None:
    await run_interview_nudge(hours_since_signup=24)


async def _nudge_72h() -> None:
    await run_interview_nudge(hours_since_signup=72)


# ─── Scheduler startup ────────────────────────────────────────────────────────

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

    scheduler.add_job(
        func=run_reengagement_emails,
        trigger=CronTrigger(hour=9, minute=0),
        id="reengagement_emails",
        name="Send re-engagement emails to inactive users",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    scheduler.add_job(
        func=run_daily_push_notifications,
        trigger=CronTrigger(hour=8, minute=0),
        id="daily_push_notifications",
        name="Send daily push notifications",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    # FIX: Use named async wrapper functions instead of lambdas.
    # Previously: lambda: run_interview_nudge(...) — this creates a coroutine
    # and discards it. APScheduler ran the lambda successfully but the actual
    # nudge function never executed. Now we pass async functions directly so
    # AsyncIOScheduler can properly await them.
    scheduler.add_job(
        func=_nudge_24h,
        trigger=CronTrigger(hour="*", minute=0),
        id="interview_nudge_24h",
        name="Interview nudge - 24h",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    scheduler.add_job(
        func=_nudge_72h,
        trigger=CronTrigger(hour="*", minute=0),
        id="interview_nudge_72h",
        name="Interview nudge - 72h",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    scheduler.start()
    logger.info("scheduler_started", job_count=len(scheduler.get_jobs()))
    return scheduler


# ─── Job Implementations ──────────────────────────────────────────────────────

async def run_daily_task_generation() -> None:
    """
    Runs every hour. Generates tasks for users at midnight their local time.
    After generating tasks, sends daily task email to each user.
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

                await _send_daily_task_email_for_user(user_id)

            except Exception as e:
                error_count += 1
                logger.error("task_generation_user_failed", user_id=user_id, error=str(e))

        logger.info("task_generation_complete", success=success_count, errors=error_count)

    finally:
        await release_lock("daily_task_generation")


async def _send_daily_task_email_for_user(user_id: str) -> None:
    """
    Fetch the user's today task and identity anchor, then send the daily task email.
    Called after successful task generation.
    """
    from core.database import get_db_context
    from services.email import email_service

    try:
        async with get_db_context() as db:
            from sqlalchemy import text

            result = await db.execute(text("""
                SELECT
                    u.email,
                    u.display_name,
                    dt.title AS task_title,
                    dt.description AS task_description,
                    g.required_identity
                FROM users u
                JOIN goals g ON g.user_id = u.id AND g.status = 'active'
                JOIN daily_tasks dt ON dt.user_id = u.id
                    AND dt.scheduled_date = CURRENT_DATE
                    AND dt.status = 'pending'
                WHERE u.id = CAST(:user_id AS uuid)
                ORDER BY dt.created_at DESC
                LIMIT 1
            """), {"user_id": user_id})

            row = result.fetchone()
            if not row:
                logger.warning("daily_task_email_no_task_found", user_id=user_id)
                return

            email, display_name, task_title, task_description, identity_anchor = row

        await email_service.send_daily_task_email(
            to_email=email,
            display_name=display_name,
            task_title=task_title,
            task_description=task_description or "",
            identity_anchor=identity_anchor or "the best version of yourself",
            app_url=settings.frontend_url,
        )

    except Exception as e:
        logger.error("daily_task_email_send_failed", user_id=user_id, error=str(e))


async def run_reengagement_emails() -> None:
    """
    Runs daily at 9am UTC.
    Sends re-engagement emails to users who have missed tasks and show no
    recent task completions (proxy for inactivity — no last_active_at column).
    Uses notification_queue to prevent re-sending within 3 days.
    """
    from core.cache import acquire_lock, release_lock
    from core.database import get_db_context
    from services.email import email_service

    lock_acquired = await acquire_lock("reengagement_emails", ttl_seconds=3600)
    if not lock_acquired:
        return

    try:
        async with get_db_context() as db:
            from sqlalchemy import text

            # FIX: Removed u.last_active_at and u.last_reengagement_email_sent_at —
            # neither column exists in the users table. Inactivity is now detected by
            # the absence of any completed task in the last 3 days. Re-send throttling
            # uses notification_queue (channel='email') which already exists in the schema.
            result = await db.execute(text("""
                SELECT
                    u.id,
                    u.email,
                    u.display_name,
                    COUNT(dt.id) AS missed_tasks
                FROM users u
                JOIN goals g ON g.user_id = u.id AND g.status = 'active'
                JOIN daily_tasks dt ON dt.user_id = u.id
                    AND dt.status = 'pending'
                    AND dt.scheduled_date < CURRENT_DATE
                WHERE u.is_active = TRUE
                  AND u.onboarding_status = 'active'
                  AND NOT EXISTS (
                    SELECT 1 FROM daily_tasks completed
                    WHERE completed.user_id = u.id
                      AND completed.status = 'completed'
                      AND completed.updated_at >= NOW() - INTERVAL '3 days'
                  )
                  AND NOT EXISTS (
                    SELECT 1 FROM notification_queue nq
                    WHERE nq.user_id = u.id
                      AND nq.channel = 'email'
                      AND nq.sent_at >= NOW() - INTERVAL '3 days'
                  )
                GROUP BY u.id, u.email, u.display_name
                HAVING COUNT(dt.id) > 0
            """))
            users = result.fetchall()

        if not users:
            logger.info("reengagement_no_users_to_contact")
            return

        logger.info("reengagement_started", user_count=len(users))
        sent_count = 0

        for row in users:
            user_id, email, display_name, missed_tasks = row
            try:
                sent = await email_service.send_reengagement_email(
                    to_email=email,
                    display_name=display_name,
                    days_inactive=3,
                    missed_tasks=int(missed_tasks),
                    app_url=settings.frontend_url,
                )

                if sent:
                    async with get_db_context() as db2:
                        from sqlalchemy import text as t
                        await db2.execute(t("""
                            INSERT INTO notification_queue
                                (user_id, type, title, body, channel, scheduled_at, sent_at)
                            VALUES
                                (CAST(:user_id AS uuid), 'reengagement', 'Get back on track',
                                 'You have tasks waiting', 'email', NOW(), NOW())
                        """), {"user_id": str(user_id)})
                        await db2.commit()
                    sent_count += 1

            except Exception as e:
                logger.error("reengagement_email_failed", user_id=str(user_id), error=str(e))

        logger.info("reengagement_complete", sent=sent_count, total=len(users))

    finally:
        await release_lock("reengagement_emails")


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


async def run_morning_sweep() -> None:
    """
    MORNING SWEEP (4:00 AM UTC)
    Catches any active users who don't have a task for today.
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

                    await _send_daily_task_email_for_user(user_id)
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


async def run_daily_push_notifications() -> None:
    """
    Runs daily at 8am UTC.
    Sends web push notifications to users with a pending task today.
    Deletes stale subscriptions that return HTTP 410.
    """
    from core.cache import acquire_lock, release_lock
    from core.database import get_db_context
    from services.push import send_push_notification, PUSH_EXPIRED

    lock_acquired = await acquire_lock("daily_push_notifications", ttl_seconds=3600)
    if not lock_acquired:
        return

    try:
        async with get_db_context() as db:
            from sqlalchemy import text

            result = await db.execute(text("""
                SELECT
                    ps.user_id,
                    ps.endpoint,
                    ps.p256dh,
                    ps.auth,
                    dt.title AS task_title
                FROM push_subscriptions ps
                JOIN daily_tasks dt ON dt.user_id = ps.user_id
                    AND dt.scheduled_date = CURRENT_DATE
                    AND dt.status = 'pending'
                JOIN users u ON u.id = ps.user_id
                WHERE u.is_active = TRUE
            """))
            rows = result.fetchall()

        if not rows:
            logger.info("push_notifications_no_targets")
            return

        logger.info("push_notifications_started", user_count=len(rows))
        sent_count = 0
        failed_count = 0
        expired_ids = []

        for user_id, endpoint, p256dh, auth, task_title in rows:
            result = send_push_notification(
                endpoint=endpoint,
                p256dh=p256dh,
                auth=auth,
                title="Your identity task is ready",
                body=task_title or "Your daily task is waiting for you.",
                url="/dashboard",
            )

            if result is True:
                sent_count += 1
                logger.info("push_sent", user_id=str(user_id))
            elif result == PUSH_EXPIRED:
                expired_ids.append(str(user_id))
            else:
                failed_count += 1
                logger.warning("push_failed", user_id=str(user_id))

        if expired_ids:
            async with get_db_context() as db2:
                from sqlalchemy import text as t
                for uid in expired_ids:
                    await db2.execute(
                        t("DELETE FROM push_subscriptions WHERE user_id = CAST(:uid AS uuid)"),
                        {"uid": uid},
                    )
                await db2.commit()
            logger.info("push_subscriptions_expired_removed", count=len(expired_ids))

        logger.info(
            "push_notifications_complete",
            sent=sent_count,
            failed=failed_count,
            expired=len(expired_ids),
            total=len(rows),
        )

    finally:
        await release_lock("daily_push_notifications")


async def run_interview_nudge(hours_since_signup: int) -> None:
    """
    Send interview completion nudge to users who signed up
    but have not completed the interview.
    hours_since_signup: 24 for attempt 1, 72 for attempt 2
    """
    from core.database import get_db_context
    from services.email import send_interview_nudge_email
    from services.push import send_push_notification

    window_start = hours_since_signup - 1  # 1-hour window to catch the cohort
    window_end = hours_since_signup

    try:
        async with get_db_context() as db:
            from sqlalchemy import text

            result = await db.execute(
                text(f"""
                    SELECT
                        u.id,
                        u.email,
                        u.display_name,
                        ps.endpoint,
                        ps.p256dh,
                        ps.auth
                    FROM users u
                    LEFT JOIN goals g ON g.user_id = u.id
                    LEFT JOIN push_subscriptions ps ON ps.user_id = u.id
                    WHERE u.is_active = TRUE
                      AND g.id IS NULL
                      AND u.created_at >= NOW() - INTERVAL '{window_end} hours'
                      AND u.created_at < NOW() - INTERVAL '{window_start} hours'
                """)
            )
            users = result.fetchall()
    except Exception as e:
        logger.error("interview_nudge_query_failed", error=str(e), hours=hours_since_signup)
        return

    attempt = 1 if hours_since_signup == 24 else 2
    logger.info("interview_nudge_starting", attempt=attempt, user_count=len(users))

    for user in users:
        first_name = (user.display_name or user.email).split()[0].capitalize()

        try:
            await send_interview_nudge_email(
                to_email=user.email,
                first_name=first_name,
                attempt=attempt,
            )
            logger.info("interview_nudge_email_sent", user_id=str(user.id), attempt=attempt)
        except Exception as e:
            logger.warning("interview_nudge_email_failed", user_id=str(user.id), error=str(e))

        if user.endpoint and user.p256dh and user.auth:
            if attempt == 1:
                title = "Your interview is waiting"
                body = "You signed up but didn't finish. 10-15 min. One goal on the other side."
            else:
                title = "Still here when you're ready."
                body = "The question isn't what you want. It's who you need to become."

            try:
                send_push_notification(
                    endpoint=user.endpoint,
                    p256dh=user.p256dh,
                    auth=user.auth,
                    title=title,
                    body=body,
                    url="/onboarding/interview",
                )
                logger.info("interview_nudge_push_sent", user_id=str(user.id), attempt=attempt)
            except Exception as e:
                logger.warning("interview_nudge_push_failed", user_id=str(user.id), error=str(e))