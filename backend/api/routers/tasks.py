"""
api/routers/tasks.py

Daily task endpoints — the core daily loop.

GET  /tasks/today               — get today's task
GET  /tasks/{date}              — get task for a specific date
POST /tasks/{id}/start          — mark task as started (enter execution mode)
POST /tasks/{id}/complete       — mark task as complete
POST /tasks/{id}/skip           — skip with a reason
GET  /tasks/history             — task history with completion stats
POST /tasks/generate            — manually trigger task generation (if none exists today)
"""

from datetime import date, timedelta

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai.engines.task_generator import TaskGeneratorEngine
from api.dependencies.auth import get_onboarded_user
from core.cache import invalidate_user_context
from core.database import get_db
from db.models.user import User

logger = structlog.get_logger()

router = APIRouter(prefix="/tasks", tags=["Daily Tasks"])
task_generator = TaskGeneratorEngine()


# ─── Schemas ──────────────────────────────────────────────────────────────────

class CompleteTaskRequest(BaseModel):
    execution_notes: str | None = Field(default=None, max_length=2000)
    actual_duration_minutes: int | None = Field(default=None, ge=1, le=480)


class SkipTaskRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


# ─── Today's Task ─────────────────────────────────────────────────────────────

@router.get(
    "/today",
    summary="Get today's becoming task",
)
async def get_today_task(
    current_user: User = Depends(get_onboarded_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Returns today's identity-focused task.

    If no task exists for today (e.g. new user before first generation),
    generates one on-demand.

    Response includes:
    - The identity focus (who you are today)
    - The task title and description
    - Execution guidance
    - Current status
    - Whether a reflection has been submitted
    """
    uid = str(current_user.id)
    today = date.today()

    result = await db.execute(
        text("""
            SELECT
                dt.id, dt.identity_focus, dt.title, dt.description,
                dt.execution_guidance, dt.time_estimate_minutes,
                dt.difficulty_level, dt.task_type, dt.status,
                dt.started_at, dt.completed_at, dt.execution_notes,
                r.id AS reflection_id,
                r.submitted_at AS reflected_at
            FROM daily_tasks dt
            LEFT JOIN reflections r ON r.task_id = dt.id
            WHERE dt.user_id = :user_id
              AND dt.scheduled_date = :today
              AND dt.status != 'skipped'
            LIMIT 1
        """),
        {"user_id": uid, "today": today},
    )
    task = result.fetchone()

    # Generate on-demand if no task exists
    if not task:
        logger.info("generating_on_demand_task", user_id=uid)
        generated = await task_generator.generate_task_for_user(
            user_id=current_user.id,
            target_date=today,
            db=db,
        )
        if not generated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Could not generate a task. Please try again.",
            )
        # Reload from DB after generation
        result = await db.execute(
            text("""
                SELECT dt.id, dt.identity_focus, dt.title, dt.description,
                       dt.execution_guidance, dt.time_estimate_minutes,
                       dt.difficulty_level, dt.task_type, dt.status,
                       dt.started_at, dt.completed_at, dt.execution_notes,
                       NULL AS reflection_id, NULL AS reflected_at
                FROM daily_tasks dt
                WHERE dt.user_id = :user_id
                  AND dt.scheduled_date = :today
                  AND dt.status != 'skipped'
                LIMIT 1
            """),
            {"user_id": uid, "today": today},
        )
        task = result.fetchone()

    return _format_task(task, today)


@router.get(
    "/{task_date}",
    summary="Get task for a specific date (YYYY-MM-DD)",
)
async def get_task_by_date(
    task_date: str,
    current_user: User = Depends(get_onboarded_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get a task for a specific date. Used for reviewing past days."""
    try:
        parsed_date = date.fromisoformat(task_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    result = await db.execute(
        text("""
            SELECT
                dt.id, dt.identity_focus, dt.title, dt.description,
                dt.execution_guidance, dt.time_estimate_minutes,
                dt.difficulty_level, dt.task_type, dt.status,
                dt.started_at, dt.completed_at, dt.execution_notes,
                r.id AS reflection_id,
                r.submitted_at AS reflected_at
            FROM daily_tasks dt
            LEFT JOIN reflections r ON r.task_id = dt.id
            WHERE dt.user_id = :user_id
              AND dt.scheduled_date = :date
              AND dt.status != 'skipped'
            LIMIT 1
        """),
        {"user_id": str(current_user.id), "date": parsed_date},
    )
    task = result.fetchone()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No task found for {task_date}.",
        )

    return _format_task(task, parsed_date)


# ─── Task Actions ─────────────────────────────────────────────────────────────

@router.post(
    "/{task_id}/start",
    summary="Enter execution mode — mark task as started",
)
async def start_task(
    task_id: str,
    current_user: User = Depends(get_onboarded_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Mark the task as started. This enters 'execution mode'.
    Records the start time for duration tracking.
    """
    result = await db.execute(
        text("""
            UPDATE daily_tasks
            SET status = 'pending',
                started_at = COALESCE(started_at, NOW()),
                updated_at = NOW()
            WHERE id = :id AND user_id = :user_id
            RETURNING id, started_at
        """),
        {"id": task_id, "user_id": str(current_user.id)},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Task not found.")

    # Log engagement event
    await _log_engagement(str(current_user.id), "task_start", db)

    return {"status": "started", "started_at": str(row.started_at)}


@router.post(
    "/{task_id}/complete",
    summary="Complete today's task",
)
async def complete_task(
    task_id: str,
    payload: CompleteTaskRequest,
    current_user: User = Depends(get_onboarded_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Mark the task as complete.

    Optionally include:
    - execution_notes: thoughts during the task
    - actual_duration_minutes: how long it actually took

    After completion, the reflection questions are available.
    The streak and scores update at end of day.
    """
    uid = str(current_user.id)

    result = await db.execute(
        text("""
            UPDATE daily_tasks
            SET status = 'completed',
                completed_at = NOW(),
                execution_notes = COALESCE(:notes, execution_notes),
                actual_duration_mins = COALESCE(:duration, actual_duration_mins),
                updated_at = NOW()
            WHERE id = :id AND user_id = :user_id
              AND status != 'completed'
            RETURNING id, scheduled_date
        """),
        {
            "id": task_id,
            "user_id": uid,
            "notes": payload.execution_notes,
            "duration": payload.actual_duration_minutes,
        },
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found or already completed.",
        )

    # Update today's progress metrics
    await db.execute(
        text("""
            INSERT INTO progress_metrics (user_id, metric_date, task_completed)
            VALUES (:user_id, :date, TRUE)
            ON CONFLICT (user_id, metric_date)
            DO UPDATE SET task_completed = TRUE
        """),
        {"user_id": uid, "date": row.scheduled_date},
    )

    # Log engagement
    await _log_engagement(uid, "task_complete", db)
    await invalidate_user_context(uid)

    logger.info("task_completed", user_id=uid, task_id=task_id)

    return {
        "status": "completed",
        "message": "Task complete. Take a moment to reflect.",
        "reflection_available": True,
    }


@router.post(
    "/{task_id}/skip",
    summary="Skip today's task with a reason",
)
async def skip_task(
    task_id: str,
    payload: SkipTaskRequest,
    current_user: User = Depends(get_onboarded_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Skip a task. The reason is stored and analyzed by the AI
    to detect resistance patterns.

    Skipping breaks the streak but doesn't end the journey.
    """
    uid = str(current_user.id)

    await db.execute(
        text("""
            UPDATE daily_tasks
            SET status = 'skipped',
                skipped_reason = :reason,
                updated_at = NOW()
            WHERE id = :id AND user_id = :user_id
              AND status NOT IN ('completed', 'skipped')
        """),
        {"id": task_id, "user_id": uid, "reason": payload.reason},
    )

    # Log as incomplete in progress metrics
    await db.execute(
        text("""
            INSERT INTO progress_metrics (user_id, metric_date, task_completed)
            VALUES (:user_id, CURRENT_DATE, FALSE)
            ON CONFLICT (user_id, metric_date) DO NOTHING
        """),
        {"user_id": uid},
    )

    logger.info("task_skipped", user_id=uid, task_id=task_id, reason=payload.reason)

    return {
        "status": "skipped",
        "message": "Noted. Tomorrow is a new opportunity to show up.",
    }


# ─── Task History ─────────────────────────────────────────────────────────────

@router.get(
    "/history",
    summary="Get task history with completion stats",
)
async def get_task_history(
    days: int = 30,
    current_user: User = Depends(get_onboarded_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Returns task history for the past N days with completion stats.
    Used for the progress/analytics screens.
    """
    uid = str(current_user.id)
    limit_days = min(days, 90)
    since = date.today() - timedelta(days=limit_days)

    result = await db.execute(
        text("""
            SELECT
                dt.id, dt.scheduled_date, dt.identity_focus,
                dt.title, dt.status, dt.difficulty_level,
                dt.completed_at, dt.skipped_reason,
                r.depth_score, r.sentiment
            FROM daily_tasks dt
            LEFT JOIN reflections r ON r.task_id = dt.id
            WHERE dt.user_id = :user_id
              AND dt.scheduled_date >= :since
              AND dt.status != 'skipped'
            ORDER BY dt.scheduled_date DESC
        """),
        {"user_id": uid, "since": since},
    )
    tasks = result.fetchall()

    # Compute stats
    total = len(tasks)
    completed = sum(1 for t in tasks if t.status == "completed")
    skipped = sum(1 for t in tasks if t.status == "skipped")
    reflected = sum(1 for t in tasks if t.depth_score is not None)

    return {
        "stats": {
            "total": total,
            "completed": completed,
            "skipped": skipped,
            "reflected": reflected,
            "completion_rate": round(completed / total * 100, 1) if total > 0 else 0,
        },
        "tasks": [
            {
                "id": str(t.id),
                "date": str(t.scheduled_date),
                "identity_focus": t.identity_focus,
                "title": t.title,
                "status": t.status,
                "difficulty": t.difficulty_level,
                "completed_at": str(t.completed_at) if t.completed_at else None,
                "skip_reason": t.skipped_reason,
                "reflection_depth": float(t.depth_score) if t.depth_score else None,
                "reflection_sentiment": t.sentiment,
            }
            for t in tasks
        ],
    }


@router.post(
    "/generate",
    summary="Manually generate today's task if none exists",
)
async def generate_task(
    current_user: User = Depends(get_onboarded_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Manually trigger task generation for today.
    Used as a fallback if the nightly scheduler missed this user.
    """
    today = date.today()
    generated = await task_generator.generate_task_for_user(
        user_id=current_user.id,
        target_date=today,
        db=db,
    )
    if not generated:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A task already exists for today.",
        )
    return {"status": "generated", "task": generated}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _format_task(task, task_date: date) -> dict:
    """Format a task row into the standard API response."""
    return {
        "id": str(task.id),
        "date": str(task_date),
        "identity_focus": task.identity_focus,
        "title": task.title,
        "description": task.description,
        "execution_guidance": task.execution_guidance,
        "time_estimate_minutes": task.time_estimate_minutes,
        "difficulty": task.difficulty_level,
        "task_type": task.task_type,
        "status": task.status,
        "started_at": str(task.started_at) if task.started_at else None,
        "completed_at": str(task.completed_at) if task.completed_at else None,
        "execution_notes": task.execution_notes,
        "reflection_submitted": task.reflection_id is not None,
        "reflected_at": str(task.reflected_at) if task.reflected_at else None,
    }


async def _log_engagement(user_id: str, event_type: str, db: AsyncSession) -> None:
    """Log an engagement event. Silent fail — never breaks main flow."""
    try:
        await db.execute(
            text("""
                INSERT INTO engagement_events (user_id, event_type)
                VALUES (:user_id, :event_type)
            """),
            {"user_id": user_id, "event_type": event_type},
        )
    except Exception:
        pass