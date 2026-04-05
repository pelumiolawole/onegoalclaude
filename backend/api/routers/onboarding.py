"""
api/routers/onboarding.py

Onboarding flow endpoints — drives the user from signup to active.

Onboarding stages and their endpoints:
    Stage 1: Interview
        POST /onboarding/interview/message     — send message, get AI response
        GET  /onboarding/interview/state       — get current interview progress
        POST /onboarding/interview/restart     — start over

    Stage 2: Goal Definition
        POST /onboarding/goal-setup                  — submit raw goal for decomposition
        POST /onboarding/goal-setup/clarify          — answer AI clarifying questions
        GET  /onboarding/goal-setup/preview          — preview decomposed strategy before confirming
        POST /onboarding/goal-setup/confirm          — confirm and activate goal

    Stage 3: Strategy Review
        GET  /onboarding/strategy              — get full generated strategy
        POST /onboarding/activate              — activate account, generate first tasks

    Utility:
        GET  /onboarding/status                — get current onboarding step
"""

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai.engines.goal_decomposer import GoalDecomposerEngine
from ai.engines.interview import InterviewEngine
from ai.engines.task_generator import TaskGeneratorEngine
from api.dependencies.auth import get_current_active_user
from core.cache import check_and_increment_ai_rate, invalidate_user_context
from core.config import settings
from core.database import get_db
from db.models.user import OnboardingStatus, User

logger = structlog.get_logger()

router = APIRouter(prefix="/onboarding", tags=["Onboarding"])

# Engine singletons
interview_engine = InterviewEngine()
goal_decomposer = GoalDecomposerEngine()
task_generator = TaskGeneratorEngine()


# ─── Schemas ──────────────────────────────────────────────────────────────────

class InterviewMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class InterviewMessageResponse(BaseModel):
    message: str
    phase: str
    is_complete: bool
    onboarding_status: str


class GoalSubmitRequest(BaseModel):
    raw_goal: str = Field(
        min_length=10,
        max_length=1000,
        description="The user's stated goal in their own words",
    )


class GoalClarifyRequest(BaseModel):
    raw_goal: str = Field(min_length=10, max_length=1000)
    answers: str = Field(
        min_length=10,
        max_length=2000,
        description="User's answers to the AI's clarifying questions",
    )


class GoalDecompositionResponse(BaseModel):
    goal_id: str | None
    needs_clarification: bool
    clarifying_questions: list[str]
    strategy: dict | None


# ─── Status ───────────────────────────────────────────────────────────────────

@router.get(
    "/status",
    summary="Get current onboarding status and next step",
)
async def get_onboarding_status(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    status_map = {
        OnboardingStatus.CREATED: {
            "step": 0,
            "screen": "welcome",
            "message": "Welcome to One Goal. Let's start your discovery interview.",
        },
        OnboardingStatus.INTERVIEW_STARTED: {
            "step": 1,
            "screen": "interview",
            "message": "Your discovery interview is in progress.",
        },
        OnboardingStatus.INTERVIEW_COMPLETE: {
            "step": 2,
            "screen": "goal_definition",
            "message": "Interview complete. Now define your one goal.",
        },
        OnboardingStatus.GOAL_DEFINED: {
            "step": 3,
            "screen": "strategy_review",
            "message": "Your strategy is ready. Review it before activating.",
        },
        OnboardingStatus.STRATEGY_GENERATED: {
            "step": 4,
            "screen": "activation",
            "message": "Everything is ready. Activate to begin your transformation.",
        },
        OnboardingStatus.ACTIVE: {
            "step": 5,
            "screen": "dashboard",
            "message": "You're active. Your journey has started.",
        },
    }

    info = status_map.get(current_user.onboarding_status, status_map[OnboardingStatus.CREATED])

    return {
        "onboarding_status": current_user.onboarding_status.value,
        **info,
    }


# ─── Stage 1: Interview ───────────────────────────────────────────────────────

@router.post(
    "/interview/message",
    response_model=InterviewMessageResponse,
    summary="Send a message in the discovery interview",
)
async def send_interview_message(
    payload: InterviewMessageRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> InterviewMessageResponse:
    if current_user.onboarding_status not in (
        OnboardingStatus.CREATED,
        OnboardingStatus.INTERVIEW_STARTED,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "interview_already_complete",
                "message": "Interview is already complete.",
                "current_status": current_user.onboarding_status.value,
            },
        )

    # Enforce per-user interview message limit to prevent OpenAI cost drain
    allowed, count = await check_and_increment_ai_rate(
        user_id=str(current_user.id),
        engine="interview",
        limit=settings.ai_interview_message_limit,
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "interview_limit_reached",
                "message": "You've sent too many messages. Please try again later.",
                "count": count,
                "limit": settings.ai_interview_message_limit,
            },
        )

    result = await interview_engine.process_message(
        user_id=current_user.id,
        user_message=payload.message,
        db=db,
    )

    await db.refresh(current_user)

    return InterviewMessageResponse(
        message=result["message"],
        phase=result["phase"],
        is_complete=result["is_complete"],
        onboarding_status=current_user.onboarding_status.value,
    )


@router.get(
    "/interview/state",
    summary="Get current interview state and conversation history",
)
async def get_interview_state(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        text("""
            SELECT current_phase, messages, extracted_data, is_complete
            FROM onboarding_interview_state
            WHERE user_id = :user_id
        """),
        {"user_id": str(current_user.id)},
    )
    row = result.fetchone()

    if not row:
        return {
            "current_phase": "tension",
            "messages": [],
            "is_complete": False,
        }

    messages = [
        m for m in (row.messages or [])
        if m.get("role") in ("user", "assistant")
    ]

    return {
        "current_phase": row.current_phase,
        "messages": messages,
        "is_complete": row.is_complete,
    }


@router.post(
    "/interview/restart",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Restart the discovery interview",
)
async def restart_interview(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    if current_user.onboarding_status not in (
        OnboardingStatus.CREATED,
        OnboardingStatus.INTERVIEW_STARTED,
        OnboardingStatus.INTERVIEW_COMPLETE,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot restart interview after goal has been defined.",
        )

    await db.execute(
        text("""
            UPDATE onboarding_interview_state
            SET current_phase = 'tension',
                messages = '[]'::jsonb,
                extracted_data = '{}'::jsonb,
                is_complete = FALSE,
                completed_at = NULL
            WHERE user_id = :user_id
        """),
        {"user_id": str(current_user.id)},
    )
    await db.execute(
        text("UPDATE users SET onboarding_status = 'created' WHERE id = :user_id"),
        {"user_id": str(current_user.id)},
    )
    await invalidate_user_context(str(current_user.id))


# ─── Stage 2: Goal Definition ─────────────────────────────────────────────────

@router.post(
    "/goal-setup",
    response_model=GoalDecompositionResponse,
    summary="Submit goal for AI decomposition",
)
async def submit_goal(
    payload: GoalSubmitRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> GoalDecompositionResponse:
    """
    Submit your goal for AI decomposition into a full identity-based strategy.

    Two possible responses:
    1. needs_clarification=True  — AI has questions. Call /goal/clarify with answers.
    2. needs_clarification=False — Strategy is ready. Review it, then call /goal/confirm.

    Accepts any onboarding status except ACTIVE — users who reach this page
    directly (e.g. skipped or refreshed) are silently advanced to interview_complete
    so they are never blocked.
    """
    # Only block users who are already fully active
    if current_user.onboarding_status == OnboardingStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "already_active",
                "message": "Your account is already active.",
                "current_status": current_user.onboarding_status.value,
            },
        )

    # Silently advance users who haven't finished the interview
    # so they are never blocked by a status gate
    if current_user.onboarding_status in (
        OnboardingStatus.CREATED,
        OnboardingStatus.INTERVIEW_STARTED,
    ):
        await db.execute(
            text("UPDATE users SET onboarding_status = 'interview_complete' WHERE id = :user_id"),
            {"user_id": str(current_user.id)},
        )
        await db.refresh(current_user)

    result = await goal_decomposer.decompose(
        user_id=current_user.id,
        raw_goal=payload.raw_goal,
        db=db,
    )

    return GoalDecompositionResponse(**result)


@router.post(
    "/goal/clarify",
    response_model=GoalDecompositionResponse,
    summary="Answer AI clarifying questions about your goal",
)
async def clarify_goal(
    payload: GoalClarifyRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> GoalDecompositionResponse:
    result = await goal_decomposer.decompose_with_answers(
        user_id=current_user.id,
        raw_goal=payload.raw_goal,
        clarification_answers=payload.answers,
        db=db,
    )
    return GoalDecompositionResponse(**result)


@router.get(
    "/goal/preview",
    summary="Preview the decomposed goal strategy",
)
async def preview_goal_strategy(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if current_user.onboarding_status not in (
        OnboardingStatus.GOAL_DEFINED,
        OnboardingStatus.STRATEGY_GENERATED,
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No goal strategy found. Submit your goal first.",
        )

    goal_result = await db.execute(
        text("""
            SELECT
                g.id, g.refined_statement, g.why_statement,
                g.success_definition, g.required_identity,
                g.key_shifts, g.estimated_timeline,
                g.difficulty_level, g.progress_percentage
            FROM goals g
            WHERE g.user_id = :user_id AND g.status = 'active'
            LIMIT 1
        """),
        {"user_id": str(current_user.id)},
    )
    goal = goal_result.fetchone()

    if not goal:
        raise HTTPException(status_code=404, detail="No active goal found.")

    obj_result = await db.execute(
        text("""
            SELECT id, title, description, success_criteria,
                   sequence_order, estimated_weeks, status
            FROM objectives
            WHERE goal_id = :goal_id
            ORDER BY sequence_order
        """),
        {"goal_id": str(goal.id)},
    )
    objectives = [
        {
            "id": str(r.id),
            "title": r.title,
            "description": r.description,
            "success_criteria": r.success_criteria,
            "order": r.sequence_order,
            "estimated_weeks": r.estimated_weeks,
            "status": r.status,
        }
        for r in obj_result.fetchall()
    ]

    trait_result = await db.execute(
        text("""
            SELECT id, name, description, category,
                   current_score, target_score
            FROM identity_traits
            WHERE user_id = :user_id AND is_active = TRUE
            ORDER BY current_score ASC
        """),
        {"user_id": str(current_user.id)},
    )
    traits = [
        {
            "id": str(r.id),
            "name": r.name,
            "description": r.description,
            "category": r.category,
            "current_score": float(r.current_score),
            "target_score": float(r.target_score),
            "gap": float(r.target_score - r.current_score),
        }
        for r in trait_result.fetchall()
    ]

    return {
        "goal": {
            "id": str(goal.id),
            "statement": goal.refined_statement,
            "why": goal.why_statement,
            "success_definition": goal.success_definition,
            "required_identity": goal.required_identity,
            "key_shifts": goal.key_shifts or [],
            "estimated_weeks": goal.estimated_timeline,
            "difficulty": goal.difficulty_level,
        },
        "objectives": objectives,
        "identity_traits": traits,
    }


@router.post(
    "/goal/confirm",
    summary="Confirm goal strategy and advance to activation",
)
async def confirm_goal(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if current_user.onboarding_status != OnboardingStatus.GOAL_DEFINED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Goal must be defined before confirming.",
        )

    await db.execute(
        text("UPDATE users SET onboarding_status = 'strategy_generated' WHERE id = :user_id"),
        {"user_id": str(current_user.id)},
    )

    logger.info("goal_confirmed", user_id=str(current_user.id))
    return {"status": "confirmed", "next_step": "activate"}


# ─── Stage 3: Activation ──────────────────────────────────────────────────────

@router.post(
    "/activate",
    summary="Activate account and generate first tasks",
)
async def activate_account(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if current_user.onboarding_status != OnboardingStatus.STRATEGY_GENERATED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "not_ready_to_activate",
                "message": "Complete all onboarding steps before activating.",
                "current_status": current_user.onboarding_status.value,
            },
        )

    initial_tasks = await task_generator.generate_initial_tasks(
        user_id=current_user.id,
        db=db,
    )

    await db.execute(
        text("UPDATE users SET onboarding_status = 'active' WHERE id = :user_id"),
        {"user_id": str(current_user.id)},
    )

    await db.execute(
        text("""
            UPDATE objectives SET status = 'in_progress', started_at = NOW()
            WHERE id = (
                SELECT o.id FROM objectives o
                JOIN goals g ON g.id = o.goal_id
                WHERE g.user_id = :user_id AND g.status = 'active'
                ORDER BY o.sequence_order ASC
                LIMIT 1
            )
        """),
        {"user_id": str(current_user.id)},
    )

    await invalidate_user_context(str(current_user.id))

    logger.info(
        "user_activated",
        user_id=str(current_user.id),
        tasks_generated=len(initial_tasks),
    )

    return {
        "status": "active",
        "message": "Your transformation begins today.",
        "tasks_generated": len(initial_tasks),
        "redirect": "/dashboard",
    }