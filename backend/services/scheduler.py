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

async def _nudge_24h() -> None:
    await run_interview_nudge(hours_since_signup=24)


async def _nudge_72h() -> None:
    await run_interview_nudge(hours_since_signup=72)

async def _weekly_digest_wrapper() -> None:
    await run_weekly_digest_emails()

# ─── Scheduler startup ────────────────────────────────────────────────────────

async def start_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")

    scheduler.add_job(func=run_daily_task_generation, trigger=CronTrigger(hour="*", minute=0),
        id="daily_task_generation", name="Generate daily tasks for users at midnight local time",
        replace_existing=True, max_instances=1, misfire_grace_time=3600)

    scheduler.add_job(func=run_morning_sweep, trigger=CronTrigger(hour=4, minute=0),
        id="morning_sweep", name="Morning sweep: Generate tasks for users missing today's task",
        replace_existing=True, max_instances=1, misfire_grace_time=3600)

    scheduler.add_job(func=run_score_updates, trigger=CronTrigger(hour=2, minute=0),
        id="score_update", name="Update transformation scores for all active users",
        replace_existing=True, max_instances=1, misfire_grace_time=3600)

    scheduler.add_job(func=run_weekly_review_generation, trigger=CronTrigger(day_of_week="mon", hour=2, minute=0),
        id="weekly_review", name="Generate weekly evolution reviews",
        replace_existing=True, max_instances=1, misfire_grace_time=7200)

    scheduler.add_job(func=_weekly_digest_wrapper, trigger=CronTrigger(day_of_week="mon", hour=6, minute=0),
        id="weekly_digest_emails", name="Send weekly digest emails to active users",
        replace_existing=True, max_instances=1, misfire_grace_time=3600)

    # Goal completion check — Monday 3am UTC, after score updates (2am) and weekly review (2am)
    # so transformation scores are fresh when the check runs.
    scheduler.add_job(func=run_goal_completion_check, trigger=CronTrigger(day_of_week="mon", hour=3, minute=0),
        id="goal_completion_check", name="Check for users approaching goal completion",
        replace_existing=True, max_instances=1, misfire_grace_time=3600)

    scheduler.add_job(func=run_intervention_check, trigger=CronTrigger(hour=10, minute=0),
        id="intervention_check", name="Detect and notify users needing coach check-ins",
        replace_existing=True, max_instances=1, misfire_grace_time=3600)

    scheduler.add_job(func=run_behavioral_snapshots, trigger=CronTrigger(day_of_week="mon", hour=2, minute=30),
        id="behavioral_snapshot", name="Build weekly behavioral fingerprints",
        replace_existing=True, max_instances=1, misfire_grace_time=3600)

    scheduler.add_job(func=run_data_purge, trigger=CronTrigger(hour=3, minute=0),
        id="data_purge", name="Permanently delete accounts past grace period",
        replace_existing=True, max_instances=1, misfire_grace_time=3600)

    scheduler.add_job(func=send_verification_reminders, trigger=CronTrigger(hour="*", minute=30),
        id="verification_reminders", name="Send email verification reminders at 24 hours",
        replace_existing=True, max_instances=1, misfire_grace_time=3600)

    scheduler.add_job(func=run_reengagement_emails, trigger=CronTrigger(hour=9, minute=0),
        id="reengagement_emails", name="Send re-engagement emails to inactive users",
        replace_existing=True, max_instances=1, misfire_grace_time=3600)

    scheduler.add_job(func=run_activation_reengagement, trigger=CronTrigger(hour=9, minute=30),
        id="activation_reengagement", name="48h activation reengagement — users who never completed a task",
        replace_existing=True, max_instances=1, misfire_grace_time=3600)

    scheduler.add_job(func=run_daily_push_notifications, trigger=CronTrigger(hour=8, minute=0),
        id="daily_push_notifications", name="Send daily push notifications",
        replace_existing=True, max_instances=1, misfire_grace_time=3600)

    scheduler.add_job(func=_nudge_24h, trigger=CronTrigger(hour="*", minute=0),
        id="interview_nudge_24h", name="Interview nudge - 24h",
        replace_existing=True, max_instances=1, misfire_grace_time=3600)

    scheduler.add_job(func=_nudge_72h, trigger=CronTrigger(hour="*", minute=0),
        id="interview_nudge_72h", name="Interview nudge - 72h",
        replace_existing=True, max_instances=1, misfire_grace_time=3600)

    scheduler.start()
    logger.info("scheduler_started", job_count=len(scheduler.get_jobs()))
    return scheduler


# ─── Job Implementations ──────────────────────────────────────────────────────

async def run_daily_task_generation() -> None:
    """
    Runs every hour. Generates tasks for users at midnight their local time.
    Includes users with approaching_completion goals — they still get daily tasks.
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
                JOIN goals g ON g.user_id = u.id AND g.status IN ('active', 'approaching_completion')
                WHERE u.is_active = TRUE
                  AND u.onboarding_status = 'active'
                  AND (
                    EXTRACT(HOUR FROM NOW() AT TIME ZONE u.timezone) = 0
                    OR NOT EXISTS (
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
                if tasks_generated > 0:
                    await _send_daily_task_email_for_user(user_id)
            except Exception as e:
                error_count += 1
                logger.error("task_generation_user_failed", user_id=user_id, error=str(e))

        logger.info("task_generation_complete", success=success_count, errors=error_count)

    finally:
        await release_lock("daily_task_generation")


async def _send_daily_task_email_for_user(user_id: str) -> None:
    """Fetch today's task and send the daily task email."""
    from core.database import get_db_context
    from services.email import email_service

    try:
        async with get_db_context() as db:
            from sqlalchemy import text
            result = await db.execute(text("""
                SELECT
                    u.email, u.display_name,
                    dt.title AS task_title, dt.description AS task_description,
                    g.required_identity
                FROM users u
                JOIN goals g ON g.user_id = u.id AND g.status IN ('active', 'approaching_completion')
                JOIN daily_tasks dt ON dt.user_id = u.id
                    AND dt.scheduled_date = CURRENT_DATE AND dt.status = 'pending'
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
            to_email=email, display_name=display_name,
            task_title=task_title, task_description=task_description or "",
            identity_anchor=identity_anchor or "the best version of yourself",
            app_url=settings.frontend_url,
        )
    except Exception as e:
        logger.error("daily_task_email_send_failed", user_id=user_id, error=str(e))


async def run_goal_completion_check() -> None:
    """
    Runs every Monday at 3am UTC — after score updates (2am) and weekly review (2am).

    Checks all users with ACTIVE goals against three completion signals:
      1. Goal started_at is 84+ days ago (12 weeks)
      2. Transformation score >= 70
      3. Task completion rate in last 30 days >= 60%

    When all three pass:
      - Goal status → 'approaching_completion'
      - approaching_completion_flagged_at and completion_check_score set
      - coach_intervention 'goal_approaching_completion' created so Coach PO
        shifts to reflective mode on next session (via context_builder)
      - For Identity tier: additional 'reinterview_available' intervention queued
        so Coach PO can surface the re-interview offer naturally in conversation

    Already-flagged goals (approaching_completion) are excluded — flag is set once.
    No emails. No UI changes. Entirely invisible to the user.
    The coach prompt receives {goal_completion_context} from context_builder.
    """
    from core.cache import acquire_lock, release_lock
    from core.database import get_db_context

    lock_acquired = await acquire_lock("goal_completion_check", ttl_seconds=3600)
    if not lock_acquired:
        logger.warning("goal_completion_check_lock_not_acquired")
        return

    try:
        async with get_db_context() as db:
            from sqlalchemy import text
            result = await db.execute(text("""
                SELECT
                    u.id AS user_id,
                    u.subscription_plan,
                    g.id AS goal_id,
                    g.started_at,
                    ip.transformation_score,
                    ROUND(
                        COUNT(CASE WHEN dt.status = 'completed' THEN 1 END)::numeric /
                        NULLIF(COUNT(dt.id), 0) * 100, 1
                    ) AS completion_rate_30d
                FROM users u
                JOIN goals g ON g.user_id = u.id AND g.status = 'active'
                JOIN identity_profiles ip ON ip.user_id = u.id
                LEFT JOIN daily_tasks dt ON dt.user_id = u.id
                    AND dt.scheduled_date >= CURRENT_DATE - INTERVAL '30 days'
                    AND dt.scheduled_date < CURRENT_DATE
                WHERE u.is_active = TRUE
                  AND u.onboarding_status = 'active'
                  AND g.started_at IS NOT NULL
                  AND g.started_at <= NOW() - INTERVAL '84 days'
                  AND ip.transformation_score >= 70
                GROUP BY u.id, u.subscription_plan, g.id, g.started_at, ip.transformation_score
                HAVING ROUND(
                    COUNT(CASE WHEN dt.status = 'completed' THEN 1 END)::numeric /
                    NULLIF(COUNT(dt.id), 0) * 100, 1
                ) >= 60
            """))
            users_approaching = result.fetchall()

        if not users_approaching:
            logger.info("goal_completion_check_no_users_qualifying")
            return

        logger.info("goal_completion_check_started", qualifying_count=len(users_approaching))

        from datetime import datetime, timezone
        flagged_count = 0
        identity_nudge_count = 0

        for row in users_approaching:
            user_id = str(row.user_id)
            goal_id = str(row.goal_id)
            subscription_plan = (row.subscription_plan or "spark").lower()
            transformation_score = float(row.transformation_score or 0)
            completion_rate = float(row.completion_rate_30d or 0)
            weeks_active = 0
            if row.started_at:
                weeks_active = (datetime.now(timezone.utc) - row.started_at).days // 7

            try:
                async with get_db_context() as db:
                    from sqlalchemy import text

                    # Flag the goal
                    await db.execute(text("""
                        UPDATE goals
                        SET status = 'approaching_completion',
                            approaching_completion_flagged_at = NOW(),
                            completion_check_score = :score,
                            updated_at = NOW()
                        WHERE id = CAST(:goal_id AS uuid)
                          AND user_id = CAST(:user_id AS uuid)
                    """), {"goal_id": goal_id, "user_id": user_id, "score": transformation_score})

                    # Coach intervention — shifts Coach PO tone to reflective/consolidation mode
                    await db.execute(text("""
                        INSERT INTO coach_interventions (user_id, intervention_type, message, urgency)
                        VALUES (
                            CAST(:user_id AS uuid),
                            'goal_approaching_completion',
                            :message,
                            'low'
                        )
                    """), {
                        "user_id": user_id,
                        "message": (
                            f"This user has been pursuing their goal for {weeks_active} weeks. "
                            f"Transformation score: {transformation_score:.0f}. "
                            f"Task completion rate (last 30 days): {completion_rate:.0f}%. "
                            f"They are approaching the end of this goal arc. "
                            f"Shift coaching mode toward consolidation: ask what has changed in who they are, "
                            f"not just what they have done. Surface the question of what comes next — "
                            f"but do not force it. Let them arrive at it."
                        ),
                    })

                    # Identity tier: queue re-interview nudge for Coach PO to surface naturally
                    if subscription_plan == "identity":
                        await db.execute(text("""
                            INSERT INTO coach_interventions (user_id, intervention_type, message, urgency)
                            VALUES (
                                CAST(:user_id AS uuid),
                                'reinterview_available',
                                :message,
                                'low'
                            )
                        """), {
                            "user_id": user_id,
                            "message": (
                                "This user is on The Identity plan and their goal is approaching completion. "
                                "When the moment is right — not forced — let them know a new Discovery Interview "
                                "is available. Frame it as evolution, not starting over: "
                                "'You came in as one person. You're leaving as another. "
                                "When you're ready to find out who that person wants to become next, "
                                "the interview is waiting.'"
                            ),
                        })
                        identity_nudge_count += 1

                    await db.commit()
                    flagged_count += 1

                    logger.info(
                        "goal_approaching_completion_flagged",
                        user_id=user_id, goal_id=goal_id,
                        weeks_active=weeks_active,
                        transformation_score=transformation_score,
                        completion_rate=completion_rate,
                        is_identity_tier=(subscription_plan == "identity"),
                    )

            except Exception as e:
                logger.error("goal_completion_flag_failed",
                    user_id=user_id, goal_id=goal_id, error=str(e))

        logger.info("goal_completion_check_complete",
            flagged=flagged_count,
            identity_nudges_queued=identity_nudge_count,
            total_checked=len(users_approaching))

    finally:
        await release_lock("goal_completion_check")


async def run_reengagement_emails() -> None:
    """
    Runs daily at 9am UTC.
    Sends re-engagement emails to users who have missed tasks and show no
    recent task completions. Uses notification_queue to prevent re-sending within 3 days.
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
            result = await db.execute(text("""
                SELECT u.id, u.email, u.display_name, COUNT(dt.id) AS missed_tasks
                FROM users u
                JOIN goals g ON g.user_id = u.id AND g.status IN ('active', 'approaching_completion')
                JOIN daily_tasks dt ON dt.user_id = u.id
                    AND dt.status = 'pending' AND dt.scheduled_date < CURRENT_DATE
                WHERE u.is_active = TRUE AND u.onboarding_status = 'active'
                  AND NOT EXISTS (
                    SELECT 1 FROM daily_tasks completed
                    WHERE completed.user_id = u.id AND completed.status = 'completed'
                      AND completed.updated_at >= NOW() - INTERVAL '3 days'
                  )
                  AND NOT EXISTS (
                    SELECT 1 FROM notification_queue nq
                    WHERE nq.user_id = u.id AND nq.channel = 'email'
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
                    to_email=email, display_name=display_name,
                    days_inactive=3, missed_tasks=int(missed_tasks),
                    app_url=settings.frontend_url,
                )
                if sent:
                    async with get_db_context() as db2:
                        from sqlalchemy import text as t
                        await db2.execute(t("""
                            INSERT INTO notification_queue
                                (user_id, type, title, body, channel, scheduled_at, sent_at)
                            VALUES (CAST(:user_id AS uuid), 'reengagement', 'Get back on track',
                                    'You have tasks waiting', 'email', NOW(), NOW())
                        """), {"user_id": str(user_id)})
                        await db2.commit()
                    sent_count += 1
            except Exception as e:
                logger.error("reengagement_email_failed", user_id=str(user_id), error=str(e))

        logger.info("reengagement_complete", sent=sent_count, total=len(users))

    finally:
        await release_lock("reengagement_emails")


async def run_activation_reengagement() -> None:
    """
    Runs daily at 9:30am UTC.
    Targets users who activated 48+ hours ago but have never completed a task.
    Sends one email referencing their commitment statement.
    Throttled: sends once only per user via activation_reengagement_sent_at on identity_profiles.
    """
    from core.cache import acquire_lock, release_lock
    from core.database import get_db_context
    from services.email import email_service

    lock_acquired = await acquire_lock("activation_reengagement", ttl_seconds=3600)
    if not lock_acquired:
        return

    try:
        async with get_db_context() as db:
            from sqlalchemy import text
            result = await db.execute(text("""
                SELECT
                    u.id,
                    u.email,
                    u.display_name,
                    ip.commitment_statement,
                    dt.title AS task_title
                FROM users u
                JOIN goals g ON g.user_id = u.id
                    AND g.status IN ('active', 'approaching_completion')
                JOIN identity_profiles ip ON ip.user_id = u.id
                LEFT JOIN daily_tasks dt ON dt.user_id = u.id
                    AND dt.scheduled_date = CURRENT_DATE
                    AND dt.status = 'pending'
                WHERE u.is_active = TRUE
                  AND u.onboarding_status = 'active'
                  AND g.started_at <= NOW() - INTERVAL '48 hours'
                  AND ip.activation_reengagement_sent_at IS NULL
                  AND NOT EXISTS (
                    SELECT 1 FROM daily_tasks completed
                    WHERE completed.user_id = u.id
                      AND completed.status = 'completed'
                  )
            """))
            users = result.fetchall()

        if not users:
            logger.info("activation_reengagement_no_users")
            return

        logger.info("activation_reengagement_started", user_count=len(users))
        sent_count = 0

        for row in users:
            user_id = str(row[0])
            email = row[1]
            display_name = row[2]
            commitment_statement = row[3]
            task_title = row[4]

            try:
                sent = await email_service.send_activation_reengagement_email(
                    to_email=email,
                    display_name=display_name,
                    commitment_statement=commitment_statement,
                    task_title=task_title,
                    app_url=settings.frontend_url,
                )
                if sent:
                    async with get_db_context() as db2:
                        from sqlalchemy import text as t
                        await db2.execute(t("""
                            UPDATE identity_profiles
                            SET activation_reengagement_sent_at = NOW()
                            WHERE user_id = CAST(:user_id AS uuid)
                        """), {"user_id": user_id})
                        await db2.commit()
                    sent_count += 1
                    logger.info("activation_reengagement_sent", user_id=user_id)
            except Exception as e:
                logger.error("activation_reengagement_failed", user_id=user_id, error=str(e))

        logger.info("activation_reengagement_complete", sent=sent_count, total=len(users))

    finally:
        await release_lock("activation_reengagement")


async def send_verification_reminders() -> None:
    """Send reminder emails 24 hours after initial verification email."""
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
            result = await db.execute(select(User).where(
                User.email_verification_token.is_not(None),
                User.email_verified_at.is_(None),
                User.email_verification_sent_at <= cutoff_time,
                User.email_verification_sent_at > max_time,
                User.email_reminder_sent_at.is_(None)
            ))
            users = result.scalars().all()

            for user in users:
                try:
                    verification_url = f"{settings.frontend_url}/verify-email?token={user.email_verification_token}"
                    await email_service.send_verification_reminder(
                        to_email=user.email, first_name=user.display_name,
                        verification_url=verification_url)
                    user.email_reminder_sent_at = datetime.now(timezone.utc)
                    await db.commit()
                    logger.info("verification_reminder_sent", user_id=str(user.id))
                except Exception as e:
                    logger.error("verification_reminder_failed", user_id=str(user.id), error=str(e))
                    await db.rollback()
    finally:
        await release_lock("verification_reminders")


async def run_morning_sweep() -> None:
    """4am UTC sweep — catches users missing today's task."""
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
                JOIN goals g ON g.user_id = u.id AND g.status IN ('active', 'approaching_completion')
                WHERE u.is_active = TRUE AND u.onboarding_status = 'active'
                  AND NOT EXISTS (
                      SELECT 1 FROM daily_tasks dt
                      WHERE dt.user_id = u.id AND dt.scheduled_date = CURRENT_DATE
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
                    user_id=user_id, target_date=date.today(), is_backlog=False)
                if task:
                    success_count += 1
                    async with get_db_context() as db2:
                        from sqlalchemy import text as t
                        await db2.execute(t("""
                            UPDATE daily_tasks
                            SET generation_context = generation_context || '{"sweep_generated": true}'::jsonb
                            WHERE user_id = :user_id AND scheduled_date = CURRENT_DATE
                        """), {"user_id": user_id})
                        await db2.commit()
                    await _send_daily_task_email_for_user(user_id)
                    logger.info("morning_sweep_task_generated", user_id=user_id, task_title=task.get("title"))
                else:
                    logger.info("morning_sweep_task_already_exists", user_id=user_id)
            except Exception as e:
                error_count += 1
                logger.error("morning_sweep_user_failed", user_id=user_id, error=str(e))

        logger.info("morning_sweep_complete", success=success_count, errors=error_count,
                    total_checked=len(user_ids))
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
                SELECT id FROM users WHERE is_active = TRUE AND onboarding_status = 'active'
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
                SELECT u.id FROM users u
                WHERE u.is_active = TRUE AND u.onboarding_status = 'active'
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
                SELECT u.id FROM users u
                WHERE u.is_active = TRUE AND u.onboarding_status = 'active'
                  AND EXISTS (
                    SELECT 1 FROM progress_metrics pm
                    WHERE pm.user_id = u.id AND pm.momentum_state = 'declining'
                      AND pm.metric_date >= CURRENT_DATE - INTERVAL '7 days'
                  )
                  AND NOT EXISTS (
                    SELECT 1 FROM coach_interventions ci
                    WHERE ci.user_id = u.id
                      AND ci.intervention_type NOT IN ('goal_approaching_completion', 'reinterview_available')
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
                    await db.execute(text("SELECT build_behavioral_snapshot(CAST(:user_id AS uuid))"), {"user_id": user_id})
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
                WHERE deletion_scheduled_at IS NOT NULL AND deletion_scheduled_at <= NOW()
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
                            display_name = NULL, hashed_password = 'DELETED',
                            avatar_url = NULL, timezone = 'UTC', locale = 'en',
                            is_active = FALSE, deletion_scheduled_at = NULL,
                            deletion_completed_at = NOW()
                        WHERE id = :user_id
                    """), {"user_id": str(user_id)})
                    await db.execute(text("DELETE FROM ai_coach_messages WHERE user_id = :user_id"), {"user_id": str(user_id)})
                    await db.execute(text("DELETE FROM onboarding_interview_state WHERE user_id = :user_id"), {"user_id": str(user_id)})
                    await db.execute(text("""
                        UPDATE progress_metrics SET user_id = '00000000-0000-0000-0000-000000000000'
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
    """Runs daily at 8am UTC. Sends push notifications for pending tasks."""
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
                    ps.user_id, ps.endpoint, ps.p256dh, ps.auth,
                    dt.title AS task_title,
                    dt.identity_focus
                FROM push_subscriptions ps
                JOIN daily_tasks dt ON dt.user_id = ps.user_id
                    AND dt.scheduled_date = CURRENT_DATE AND dt.status = 'pending'
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

        for user_id, endpoint, p256dh, auth, task_title, identity_focus in rows:
            # Use identity_focus as the notification body — it tells the user who
            # they are being today, not just what they are doing. Falls back to
            # task_title if identity_focus is missing (pre-migration tasks).
            push_body = identity_focus or task_title or "Your daily task is waiting."

            result = send_push_notification(
                endpoint=endpoint, p256dh=p256dh, auth=auth,
                title="Your identity task is ready",
                body=push_body,
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
                    await db2.execute(t("DELETE FROM push_subscriptions WHERE user_id = CAST(:uid AS uuid)"), {"uid": uid})
                await db2.commit()
            logger.info("push_subscriptions_expired_removed", count=len(expired_ids))

        logger.info("push_notifications_complete", sent=sent_count, failed=failed_count,
                    expired=len(expired_ids), total=len(rows))
    finally:
        await release_lock("daily_push_notifications")


async def run_interview_nudge(hours_since_signup: int) -> None:
    """Send interview completion nudge to users who signed up but haven't completed the interview."""
    from core.database import get_db_context
    from services.email import send_interview_nudge_email
    from services.push import send_push_notification

    window_start = hours_since_signup - 1
    window_end = hours_since_signup

    try:
        async with get_db_context() as db:
            from sqlalchemy import text
            result = await db.execute(text(f"""
                SELECT u.id, u.email, u.display_name, ps.endpoint, ps.p256dh, ps.auth
                FROM users u
                LEFT JOIN goals g ON g.user_id = u.id
                LEFT JOIN push_subscriptions ps ON ps.user_id = u.id
                WHERE u.is_active = TRUE AND g.id IS NULL
                  AND u.created_at >= NOW() - INTERVAL '{window_end} hours'
                  AND u.created_at < NOW() - INTERVAL '{window_start} hours'
            """))
            users = result.fetchall()
    except Exception as e:
        logger.error("interview_nudge_query_failed", error=str(e), hours=hours_since_signup)
        return

    attempt = 1 if hours_since_signup == 24 else 2
    logger.info("interview_nudge_starting", attempt=attempt, user_count=len(users))

    for user in users:
        first_name = (user.display_name or user.email).split()[0].capitalize()
        try:
            await send_interview_nudge_email(to_email=user.email, first_name=first_name, attempt=attempt)
            logger.info("interview_nudge_email_sent", user_id=str(user.id), attempt=attempt)
        except Exception as e:
            logger.warning("interview_nudge_email_failed", user_id=str(user.id), error=str(e))

        if user.endpoint and user.p256dh and user.auth:
            title = "Your interview is waiting" if attempt == 1 else "Still here when you're ready."
            body = ("You signed up but didn't finish. 10-15 min. One goal on the other side."
                    if attempt == 1 else
                    "The question isn't what you want. It's who you need to become.")
            try:
                send_push_notification(endpoint=user.endpoint, p256dh=user.p256dh, auth=user.auth,
                                       title=title, body=body, url="/interview")
                logger.info("interview_nudge_push_sent", user_id=str(user.id), attempt=attempt)
            except Exception as e:
                logger.warning("interview_nudge_push_failed", user_id=str(user.id), error=str(e))


async def run_weekly_digest_emails() -> None:
    """
    Runs every Monday at 6am UTC — after weekly review generation (2am).
    Reads the stored weekly_reviews letter for each user and sends it by email.
    Uses notification_queue to prevent duplicate sends within the same week.
    """
    from core.cache import acquire_lock, release_lock
    from core.database import get_db_context
    from services.email import email_service

    lock_acquired = await acquire_lock("weekly_digest_emails", ttl_seconds=3600)
    if not lock_acquired:
        logger.warning("weekly_digest_lock_not_acquired")
        return

    try:
        async with get_db_context() as db:
            from sqlalchemy import text
            result = await db.execute(text("""
                SELECT
                    u.id,
                    u.email,
                    u.display_name,
                    wr.evolution_letter,
                    wr.week_start_date,
                    ip.current_streak,
                    ip.transformation_score,
                    COALESCE(
                        (SELECT COUNT(*) FROM daily_tasks dt
                         WHERE dt.user_id = u.id
                           AND dt.status = 'completed'
                           AND dt.scheduled_date >= wr.week_start_date
                           AND dt.scheduled_date < wr.week_start_date + INTERVAL '7 days'),
                        0
                    ) AS tasks_completed_this_week
                FROM users u
                JOIN weekly_reviews wr ON wr.user_id = u.id
                JOIN identity_profiles ip ON ip.user_id = u.id
                WHERE u.is_active = TRUE
                  AND u.onboarding_status = 'active'
                  AND wr.week_start_date = date_trunc('week', CURRENT_DATE - INTERVAL '7 days')::DATE
                  AND wr.evolution_letter IS NOT NULL
                  AND LENGTH(TRIM(wr.evolution_letter)) > 50
                  AND NOT EXISTS (
                    SELECT 1 FROM notification_queue nq
                    WHERE nq.user_id = u.id
                      AND nq.type = 'weekly_digest'
                      AND nq.sent_at >= NOW() - INTERVAL '6 days'
                  )
            """))
            users = result.fetchall()

        if not users:
            logger.info("weekly_digest_no_users_to_send")
            return

        logger.info("weekly_digest_started", user_count=len(users))
        sent_count = 0
        error_count = 0

        for row in users:
            user_id = str(row[0])
            email = row[1]
            display_name = row[2]
            review_letter = row[3]
            week_start = row[4]
            streak = int(row[5] or 0)
            transformation_score = float(row[6] or 0)
            tasks_completed = int(row[7] or 0)

            week_label = week_start.strftime("Week of %-d %B") if week_start else "This week"

            try:
                sent = await email_service.send_weekly_digest_email(
                    to_email=email,
                    display_name=display_name,
                    week_label=week_label,
                    review_letter=review_letter,
                    streak=streak,
                    tasks_completed=tasks_completed,
                    transformation_score=transformation_score,
                    app_url=settings.frontend_url,
                )
                if sent:
                    async with get_db_context() as db2:
                        from sqlalchemy import text as t
                        await db2.execute(t("""
                            INSERT INTO notification_queue
                                (user_id, type, title, body, channel, scheduled_at, sent_at)
                            VALUES (
                                CAST(:user_id AS uuid),
                                'weekly_digest',
                                'Weekly review sent',
                                :week_label,
                                'email',
                                NOW(),
                                NOW()
                            )
                        """), {"user_id": user_id, "week_label": week_label})
                        await db2.commit()
                    sent_count += 1
                    logger.info("weekly_digest_sent", user_id=user_id, week=week_label)
            except Exception as e:
                error_count += 1
                logger.error("weekly_digest_failed", user_id=user_id, error=str(e))

        logger.info("weekly_digest_complete", sent=sent_count, errors=error_count, total=len(users))

    finally:
        await release_lock("weekly_digest_emails")