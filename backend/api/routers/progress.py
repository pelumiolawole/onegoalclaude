"""
api/routers/progress.py

Progress and analytics endpoints.

GET  /progress/dashboard        — main dashboard data (single call for all UI)
GET  /progress/scores           — transformation score breakdown
GET  /progress/streak           — streak data with history
GET  /progress/timeline         — score history over time (for charts)
GET  /progress/traits/timeline  — trait score history
GET  /progress/weekly-reviews   — list of all weekly reviews
"""

from datetime import date, timedelta

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies.auth import get_onboarded_user
from core.database import get_db
from db.models.user import User

logger = structlog.get_logger()

router = APIRouter(prefix="/progress", tags=["Progress"])


# ─── Dashboard ────────────────────────────────────────────────────────────────

@router.get(
    "/dashboard",
    summary="Full dashboard data — single call for the main app screen",
)
async def get_dashboard(
    current_user: User = Depends(get_onboarded_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Returns everything the dashboard needs in a single API call:
    - Today's task
    - Current transformation scores
    - Streak data
    - Active traits (top 3)
    - Recent activity (last 7 days)
    - Latest weekly review summary

    Optimized to minimize roundtrips — the dashboard is the first
    screen users see every day.
    """
    uid = str(current_user.id)
    today = date.today()

    # ── Today's task ──────────────────────────────────────────────
    task_result = await db.execute(
        text("""
            SELECT
                dt.id, dt.identity_focus, dt.title, dt.description,
                dt.time_estimate_minutes, dt.difficulty_level,
                dt.status, dt.task_type,
                r.id AS reflection_id
            FROM daily_tasks dt
            LEFT JOIN reflections r ON r.task_id = dt.id
            WHERE dt.user_id = :user_id
              AND dt.scheduled_date = :today
              AND dt.status != 'skipped'
            LIMIT 1
        """),
        {"user_id": uid, "today": today},
    )
    task_row = task_result.fetchone()
    today_task = None
    if task_row:
        today_task = {
            "id": str(task_row.id),
            "identity_focus": task_row.identity_focus,
            "title": task_row.title,
            "description": task_row.description,
            "time_estimate_minutes": task_row.time_estimate_minutes,
            "difficulty": task_row.difficulty_level,
            "status": task_row.status,
            "reflection_submitted": task_row.reflection_id is not None,
        }

    # ── Scores & streak ───────────────────────────────────────────
    scores_result = await db.execute(
        text("""
            SELECT
                transformation_score, consistency_score,
                depth_score, momentum_score, alignment_score,
                momentum_state, current_streak, longest_streak,
                days_active
            FROM identity_profiles
            WHERE user_id = :user_id
        """),
        {"user_id": uid},
    )
    scores_row = scores_result.fetchone()
    scores = {
        "transformation": 0.0,
        "consistency": 0.0,
        "depth": 0.0,
        "momentum": 0.0,
        "alignment": 0.0,
        "momentum_state": "holding",
        "streak": 0,
        "longest_streak": 0,
        "days_active": 0,
    }
    if scores_row:
        scores = {
            "transformation": round(float(scores_row.transformation_score or 0), 1),
            "consistency": round(float(scores_row.consistency_score or 0), 1),
            "depth": round(float(scores_row.depth_score or 0), 1),
            "momentum": round(float(scores_row.momentum_score or 0), 1),
            "alignment": round(float(scores_row.alignment_score or 0), 1),
            "momentum_state": scores_row.momentum_state or "holding",
            "streak": scores_row.current_streak or 0,
            "longest_streak": scores_row.longest_streak or 0,
            "days_active": scores_row.days_active or 0,
        }

    # ── Top identity traits (lowest progress first) ───────────────
    traits_result = await db.execute(
        text("""
            SELECT name, current_score, target_score, velocity
            FROM identity_traits
            WHERE user_id = :user_id AND is_active = TRUE
            ORDER BY (target_score - current_score) DESC
            LIMIT 3
        """),
        {"user_id": uid},
    )
    top_traits = [
        {
            "name": r.name,
            "current_score": float(r.current_score),
            "target_score": float(r.target_score),
            "progress_pct": round(float(r.current_score) / float(r.target_score) * 100, 1),
            "trend": "growing" if r.velocity > 0 else ("declining" if r.velocity < 0 else "stable"),
        }
        for r in traits_result.fetchall()
    ]

    # ── Last 7 days activity ──────────────────────────────────────
    week_result = await db.execute(
        text("""
            SELECT
                metric_date,
                task_completed,
                reflection_submitted,
                transformation_score
            FROM progress_metrics
            WHERE user_id = :user_id
              AND metric_date >= :since
            ORDER BY metric_date ASC
        """),
        {"user_id": uid, "since": today - timedelta(days=6)},
    )
    week_data = [
        {
            "date": str(r.metric_date),
            "completed": r.task_completed,
            "reflected": r.reflection_submitted,
            "score": float(r.transformation_score) if r.transformation_score else None,
        }
        for r in week_result.fetchall()
    ]

    # ── Latest weekly review (preview only) ───────────────────────
    review_result = await db.execute(
        text("""
            SELECT week_start_date, tasks_completed, tasks_total,
                   consistency_pct, score_delta
            FROM weekly_reviews
            WHERE user_id = :user_id
            ORDER BY week_start_date DESC
            LIMIT 1
        """),
        {"user_id": uid},
    )
    review_row = review_result.fetchone()
    latest_review = None
    if review_row:
        latest_review = {
            "week_start": str(review_row.week_start_date),
            "tasks_completed": review_row.tasks_completed,
            "tasks_total": review_row.tasks_total,
            "consistency_pct": float(review_row.consistency_pct or 0),
            "score_delta": float(review_row.score_delta or 0),
        }

    # ── Goal progress ─────────────────────────────────────────────
    goal_result = await db.execute(
        text("""
            SELECT refined_statement, progress_percentage,
                   objectives_count, objectives_completed
            FROM goals
            WHERE user_id = :user_id AND status = 'active'
            LIMIT 1
        """),
        {"user_id": uid},
    )
    goal_row = goal_result.fetchone()
    goal_summary = None
    if goal_row:
        goal_summary = {
            "statement": goal_row.refined_statement,
            "progress": float(goal_row.progress_percentage or 0),
            "objectives_total": goal_row.objectives_count or 0,
            "objectives_done": goal_row.objectives_completed or 0,
        }

    return {
        "today": str(today),
        "today_task": today_task,
        "scores": scores,
        "top_traits": top_traits,
        "week_activity": week_data,
        "goal": goal_summary,
        "latest_review": latest_review,
    }


# ─── Score Detail ─────────────────────────────────────────────────────────────

@router.get(
    "/scores",
    summary="Detailed transformation score breakdown",
)
async def get_scores(
    current_user: User = Depends(get_onboarded_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Full score breakdown with explanations.
    The scores are shown qualitatively to the user — never as raw numbers.
    """
    uid = str(current_user.id)

    result = await db.execute(
        text("""
            SELECT
                transformation_score, consistency_score,
                depth_score, momentum_score, alignment_score,
                momentum_state, current_streak, longest_streak,
                days_active, last_task_date
            FROM identity_profiles
            WHERE user_id = :user_id
        """),
        {"user_id": uid},
    )
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Profile not found.")

    transformation = float(row.transformation_score or 0)

    # Translate score to qualitative grade
    def to_grade(score: float) -> str:
        if score >= 80:
            return "A"
        elif score >= 65:
            return "B"
        elif score >= 50:
            return "C"
        elif score >= 35:
            return "D"
        return "F"

    # Translate momentum state to human language
    momentum_labels = {
        "rising": "Building momentum",
        "holding": "Staying consistent",
        "declining": "Needs attention",
        "critical": "Time to reconnect",
    }

    return {
        "transformation_score": round(transformation, 1),
        "grade": to_grade(transformation),
        "momentum_label": momentum_labels.get(row.momentum_state or "holding", "Staying consistent"),
        "momentum_state": row.momentum_state,
        "breakdown": {
            "consistency": {
                "score": round(float(row.consistency_score or 0), 1),
                "label": "Show-up rate",
                "weight": "35%",
                "grade": to_grade(float(row.consistency_score or 0)),
            },
            "depth": {
                "score": round(float(row.depth_score or 0), 1),
                "label": "Reflection quality",
                "weight": "25%",
                "grade": to_grade(float(row.depth_score or 0)),
            },
            "momentum": {
                "score": round(float(row.momentum_score or 0), 1),
                "label": "Growth trajectory",
                "weight": "25%",
                "grade": to_grade(float(row.momentum_score or 0)),
            },
            "alignment": {
                "score": round(float(row.alignment_score or 0), 1),
                "label": "Identity progress",
                "weight": "15%",
                "grade": to_grade(float(row.alignment_score or 0)),
            },
        },
        "streak": {
            "current": row.current_streak or 0,
            "longest": row.longest_streak or 0,
            "last_task": str(row.last_task_date) if row.last_task_date else None,
        },
        "days_active": row.days_active or 0,
    }


# ─── Streak ───────────────────────────────────────────────────────────────────

@router.get(
    "/streak",
    summary="Streak data with calendar history",
)
async def get_streak(
    current_user: User = Depends(get_onboarded_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    uid = str(current_user.id)
    since = date.today() - timedelta(days=30)

    # Get last 30 days of activity
    result = await db.execute(
        text("""
            SELECT metric_date, task_completed, reflection_submitted
            FROM progress_metrics
            WHERE user_id = :user_id AND metric_date >= :since
            ORDER BY metric_date ASC
        """),
        {"user_id": uid, "since": since},
    )
    days = {str(r.metric_date): {"completed": r.task_completed, "reflected": r.reflection_submitted}
            for r in result.fetchall()}

    # Get streak from profile
    streak_result = await db.execute(
        text("SELECT current_streak, longest_streak FROM identity_profiles WHERE user_id = :user_id"),
        {"user_id": uid},
    )
    streak_row = streak_result.fetchone()

    return {
        "current_streak": streak_row.current_streak if streak_row else 0,
        "longest_streak": streak_row.longest_streak if streak_row else 0,
        "calendar": days,
    }


# ─── Score Timeline ───────────────────────────────────────────────────────────

@router.get(
    "/timeline",
    summary="Transformation score history over time (for charts)",
)
async def get_score_timeline(
    days: int = 30,
    current_user: User = Depends(get_onboarded_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Returns daily transformation scores for charting.
    Frontend uses this to draw the progress curve.
    """
    uid = str(current_user.id)
    since = date.today() - timedelta(days=min(days, 90))

    result = await db.execute(
        text("""
            SELECT
                metric_date,
                transformation_score,
                consistency_score,
                task_completed,
                reflection_submitted
            FROM progress_metrics
            WHERE user_id = :user_id AND metric_date >= :since
            ORDER BY metric_date ASC
        """),
        {"user_id": uid, "since": since},
    )
    rows = result.fetchall()

    return {
        "timeline": [
            {
                "date": str(r.metric_date),
                "transformation_score": float(r.transformation_score) if r.transformation_score else None,
                "consistency_score": float(r.consistency_score) if r.consistency_score else None,
                "completed": r.task_completed,
                "reflected": r.reflection_submitted,
            }
            for r in rows
        ]
    }


# ─── Traits Timeline ──────────────────────────────────────────────────────────

@router.get(
    "/traits/timeline",
    summary="Identity trait score history (for radar/line charts)",
)
async def get_traits_timeline(
    current_user: User = Depends(get_onboarded_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Returns current trait scores and velocities for visualization.
    """
    uid = str(current_user.id)

    result = await db.execute(
        text("""
            SELECT name, category, current_score, target_score,
                   velocity, created_at, updated_at
            FROM identity_traits
            WHERE user_id = :user_id AND is_active = TRUE
            ORDER BY category, name
        """),
        {"user_id": uid},
    )
    traits = [
        {
            "name": r.name,
            "category": r.category,
            "current": float(r.current_score),
            "target": float(r.target_score),
            "velocity": float(r.velocity),
            "progress_pct": round(float(r.current_score) / float(r.target_score) * 100, 1),
            "trend": "growing" if r.velocity > 0.05 else ("declining" if r.velocity < -0.05 else "stable"),
        }
        for r in result.fetchall()
    ]

    return {"traits": traits}