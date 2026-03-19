"""
api/routers/reflections.py

Reflection endpoints -- the daily meaning-making loop.

GET  /reflections/questions/{task_id}  -- get AI-generated reflection questions
POST /reflections                      -- submit reflection answers
GET  /reflections/today                -- get today's reflection
GET  /reflections/history              -- list reflection history
GET  /reflections/weekly-review        -- get latest weekly evolution letter
GET  /reflections/weekly-review/{date} -- get weekly review for a specific week
GET  /reflections/{date}               -- get reflection for a specific date
"""

import json
from datetime import date, timedelta

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai.engines.reflection_analyzer import ReflectionAnalyzerEngine
from api.dependencies.auth import get_onboarded_user
from core.cache import invalidate_user_context
from core.database import get_db
from db.models.user import User
from services.scoring import trigger_score_update

logger = structlog.get_logger()

router = APIRouter(prefix="/reflections", tags=["Reflections"])
reflection_analyzer = ReflectionAnalyzerEngine()


# ─── Schemas ──────────────────────────────────────────────────────────────────

class ReflectionAnswer(BaseModel):
    question: str
    answer: str = Field(min_length=1, max_length=2000)
    question_type: str = "general"


class SubmitReflectionRequest(BaseModel):
    task_id: str
    answers: list[ReflectionAnswer] = Field(min_length=1, max_length=5)


# ─── Reflection Questions ─────────────────────────────────────────────────────

@router.get(
    "/questions/{task_id}",
    summary="Get AI-generated reflection questions for a task",
)
async def get_reflection_questions(
    task_id: str,
    current_user: User = Depends(get_onboarded_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        text("""
            SELECT id, status, scheduled_date
            FROM daily_tasks
            WHERE id = :task_id AND user_id = :user_id
        """),
        {"task_id": task_id, "user_id": str(current_user.id)},
    )
    task = result.fetchone()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")

    existing = await db.execute(
        text("SELECT id FROM reflections WHERE task_id = :task_id AND user_id = :user_id"),
        {"task_id": task_id, "user_id": str(current_user.id)},
    )
    if existing.fetchone():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Reflection already submitted for this task.",
        )

    questions = await reflection_analyzer.generate_reflection_questions(
        user_id=current_user.id,
        task_id=task_id,
        db=db,
    )

    return {"task_id": task_id, "questions": questions}


# ─── Submit Reflection ────────────────────────────────────────────────────────

@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Submit reflection answers and receive AI analysis",
)
async def submit_reflection(
    payload: SubmitReflectionRequest,
    current_user: User = Depends(get_onboarded_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    uid = str(current_user.id)

    task_result = await db.execute(
        text("""
            SELECT id, scheduled_date, status
            FROM daily_tasks
            WHERE id = :task_id AND user_id = :user_id
        """),
        {"task_id": payload.task_id, "user_id": uid},
    )
    task = task_result.fetchone()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")

    existing = await db.execute(
        text("SELECT id FROM reflections WHERE task_id = :task_id AND user_id = :user_id"),
        {"task_id": payload.task_id, "user_id": uid},
    )
    if existing.fetchone():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You've already reflected on this task.",
        )

    qa_list = [
        {
            "question": a.question,
            "answer": a.answer,
            "question_type": a.question_type,
        }
        for a in payload.answers
    ]

    reflection_result = await db.execute(
        text("""
            INSERT INTO reflections
                (user_id, task_id, reflection_date, questions_answers)
            VALUES
                (:user_id, :task_id, :date, CAST(:qa AS jsonb))
            RETURNING id
        """),
        {
            "user_id": uid,
            "task_id": payload.task_id,
            "date": task.scheduled_date,
            "qa": json.dumps(qa_list),
        },
    )
    reflection_id = reflection_result.scalar()

    if not reflection_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save reflection. Please try again.",
        )

    analysis = await reflection_analyzer.analyze(
        user_id=current_user.id,
        reflection_id=reflection_id,
        questions_answers=qa_list,
        task_id=payload.task_id,
        db=db,
    )

    # FIXED: Insert progress_metrics with depth_score and trigger score update
    await db.execute(
        text("""
            INSERT INTO progress_metrics
                (user_id, metric_date, reflection_submitted, depth_score, updated_at)
            VALUES (:user_id, :date, TRUE, :depth, NOW())
            ON CONFLICT (user_id, metric_date)
            DO UPDATE SET
                reflection_submitted = TRUE,
                depth_score = EXCLUDED.depth_score,
                updated_at = NOW()
        """),
        {
            "user_id": uid,
            "date": task.scheduled_date,
            "depth": analysis.get("depth_score", 5.0),
        },
    )

    # FIXED: Trigger immediate score recalculation after reflection submission
    try:
        updated_scores = await trigger_score_update(db, uid)
        logger.info("scores_updated_after_reflection", user_id=uid, reflection_id=str(reflection_id), scores=updated_scores)
    except Exception as e:
        logger.error("score_update_failed_after_reflection", user_id=uid, reflection_id=str(reflection_id), error=str(e))
        # Don't fail the reflection submission if scoring fails

    await db.commit()
    await invalidate_user_context(uid)

    logger.info(
        "reflection_submitted",
        user_id=uid,
        reflection_id=str(reflection_id),
        sentiment=analysis.get("sentiment"),
        depth=analysis.get("depth_score"),
    )

    return {
        "reflection_id": str(reflection_id),
        "ai_feedback": analysis.get("ai_feedback", ""),
        "sentiment": analysis.get("sentiment"),
        "safety_triggered": analysis.get("safety_triggered", False),
        "scores_updated": True,
    }


# ─── Named routes BEFORE /{date} catch-all ────────────────────────────────────

@router.get("/today", summary="Get today's reflection if submitted")
async def get_today_reflection(
    current_user: User = Depends(get_onboarded_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await _get_reflection_by_date(str(current_user.id), date.today(), db)


@router.get("/history", summary="Get reflection history with trends")
async def get_reflection_history(
    days: int = 30,
    current_user: User = Depends(get_onboarded_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    uid = str(current_user.id)
    since = date.today() - timedelta(days=min(days, 90))

    result = await db.execute(
        text("""
            SELECT
                r.id, r.reflection_date, r.sentiment,
                r.depth_score, r.emotional_tone, r.key_themes,
                r.resistance_detected, r.breakthrough_detected,
                dt.title AS task_title
            FROM reflections r
            LEFT JOIN daily_tasks dt ON dt.id = r.task_id
            WHERE r.user_id = :user_id AND r.reflection_date >= :since
            ORDER BY r.reflection_date DESC
        """),
        {"user_id": uid, "since": since},
    )
    rows = result.fetchall()

    total = len(rows)
    avg_depth = sum(float(r.depth_score or 0) for r in rows) / total if total else 0
    sentiment_counts: dict = {}
    for r in rows:
        sentiment_counts[r.sentiment] = sentiment_counts.get(r.sentiment, 0) + 1

    return {
        "stats": {
            "total_reflections": total,
            "avg_depth_score": round(avg_depth, 1),
            "sentiment_breakdown": sentiment_counts,
            "breakthrough_days": sum(1 for r in rows if r.breakthrough_detected),
            "resistance_days": sum(1 for r in rows if r.resistance_detected),
        },
        "reflections": [
            {
                "id": str(r.id),
                "date": str(r.reflection_date),
                "task_title": r.task_title,
                "sentiment": r.sentiment,
                "depth_score": float(r.depth_score) if r.depth_score else None,
                "emotional_tone": r.emotional_tone,
                "themes": r.key_themes or [],
                "resistance": r.resistance_detected,
                "breakthrough": r.breakthrough_detected,
            }
            for r in rows
        ],
    }


@router.get("/weekly-review", summary="Get the latest weekly evolution letter")
async def get_latest_weekly_review(
    current_user: User = Depends(get_onboarded_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await _get_weekly_review(str(current_user.id), None, db)


@router.get("/weekly-review/{week_start}", summary="Get weekly review for a specific week")
async def get_weekly_review_by_date(
    week_start: str,
    current_user: User = Depends(get_onboarded_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        parsed = date.fromisoformat(week_start)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date. Use YYYY-MM-DD.")
    return await _get_weekly_review(str(current_user.id), parsed, db)


@router.get("/{reflection_date}", summary="Get reflection for a specific date (YYYY-MM-DD)")
async def get_reflection_by_date(
    reflection_date: str,
    current_user: User = Depends(get_onboarded_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        parsed = date.fromisoformat(reflection_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")
    return await _get_reflection_by_date(str(current_user.id), parsed, db)


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _get_reflection_by_date(user_id: str, target_date: date, db: AsyncSession) -> dict:
    result = await db.execute(
        text("""
            SELECT
                r.id, r.reflection_date, r.questions_answers,
                r.sentiment, r.depth_score, r.emotional_tone,
                r.key_themes, r.resistance_detected,
                r.breakthrough_detected, r.ai_feedback_shown,
                r.submitted_at,
                dt.title AS task_title,
                dt.identity_focus
            FROM reflections r
            LEFT JOIN daily_tasks dt ON dt.id = r.task_id
            WHERE r.user_id = :user_id AND r.reflection_date = :date
            LIMIT 1
        """),
        {"user_id": user_id, "date": target_date},
    )
    row = result.fetchone()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No reflection found for {target_date}.",
        )

    return {
        "id": str(row.id),
        "date": str(row.reflection_date),
        "task_title": row.task_title,
        "identity_focus": row.identity_focus,
        "answers": row.questions_answers or [],
        "sentiment": row.sentiment,
        "depth_score": float(row.depth_score) if row.depth_score else None,
        "emotional_tone": row.emotional_tone,
        "themes": row.key_themes or [],
        "resistance_detected": row.resistance_detected,
        "breakthrough_detected": row.breakthrough_detected,
        "ai_feedback": row.ai_feedback_shown,
        "submitted_at": str(row.submitted_at) if row.submitted_at else None,
    }


async def _get_weekly_review(user_id: str, week_start: date | None, db: AsyncSession) -> dict:
    if week_start:
        query = text("""
            SELECT id, week_start_date, week_end_date,
                   tasks_completed, tasks_total, reflections_submitted,
                   avg_depth_score, consistency_pct, score_delta,
                   evolution_letter, generated_at
            FROM weekly_reviews
            WHERE user_id = :user_id AND week_start_date = :week_start
        """)
        params = {"user_id": user_id, "week_start": week_start}
    else:
        query = text("""
            SELECT id, week_start_date, week_end_date,
                   tasks_completed, tasks_total, reflections_submitted,
                   avg_depth_score, consistency_pct, score_delta,
                   evolution_letter, generated_at
            FROM weekly_reviews
            WHERE user_id = :user_id
            ORDER BY week_start_date DESC
            LIMIT 1
        """)
        params = {"user_id": user_id}

    result = await db.execute(query, params)
    row = result.fetchone()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No weekly review found yet. Reviews are generated every Monday.",
        )

    return {
        "id": str(row.id),
        "week_start": str(row.week_start_date),
        "week_end": str(row.week_end_date),
        "stats": {
            "tasks_completed": row.tasks_completed,
            "tasks_total": row.tasks_total,
            "reflections_submitted": row.reflections_submitted,
            "avg_depth_score": float(row.avg_depth_score) if row.avg_depth_score else None,
            "consistency_pct": float(row.consistency_pct) if row.consistency_pct else 0.0,
            "score_delta": float(row.score_delta) if row.score_delta else 0.0,
        },
        "letter": row.evolution_letter,
        "generated_at": str(row.generated_at),
    }