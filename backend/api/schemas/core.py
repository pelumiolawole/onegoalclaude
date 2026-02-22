"""
api/schemas/core.py

Pydantic v2 schemas for the core domain objects:
  - Goals
  - Objectives
  - Identity Traits
  - Daily Tasks
  - Reflections
  - Progress / Dashboard
  - Weekly Reviews

These are the response shapes the frontend depends on.
Changing these is a breaking change — version carefully.
"""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


# ─── Goals ────────────────────────────────────────────────────────────────────

class ObjectiveSummary(BaseModel):
    id: UUID
    title: str
    description: str | None
    success_criteria: str | None
    sequence_order: int
    estimated_weeks: int | None
    status: str
    progress_percentage: float

    model_config = {"from_attributes": True}


class TraitSummary(BaseModel):
    id: UUID
    name: str
    description: str | None
    category: str
    current_score: float
    target_score: float
    velocity: float
    gap: float
    progress_pct: float
    trend: str  # growing | stable | declining

    model_config = {"from_attributes": True}


class GoalDetail(BaseModel):
    id: UUID
    status: str
    raw_input: str
    refined_statement: str | None
    why_statement: str | None
    success_definition: str | None
    required_identity: str | None
    key_shifts: list[str] | None
    estimated_timeline: int | None
    difficulty_level: int | None
    progress_percentage: float
    weeks_active: int
    started_at: datetime | None
    objectives: list[ObjectiveSummary]
    identity_traits: list[TraitSummary]
    created_at: datetime

    model_config = {"from_attributes": True}


class GoalSummary(BaseModel):
    id: UUID
    status: str
    refined_statement: str | None
    progress_percentage: float
    weeks_active: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Tasks ────────────────────────────────────────────────────────────────────

class TaskDetail(BaseModel):
    id: UUID
    scheduled_date: date
    task_type: str
    status: str
    identity_focus: str | None
    title: str
    description: str | None
    execution_guidance: str | None
    time_estimate_minutes: int | None
    difficulty_level: int | None
    started_at: datetime | None
    completed_at: datetime | None
    has_reflection: bool

    model_config = {"from_attributes": True}


class TaskSummary(BaseModel):
    id: UUID
    scheduled_date: date
    title: str
    status: str
    identity_focus: str | None

    model_config = {"from_attributes": True}


# ─── Reflections ─────────────────────────────────────────────────────────────

class ReflectionDetail(BaseModel):
    id: UUID
    reflection_date: date
    questions_answers: list[dict] | None
    sentiment: str | None
    depth_score: float | None
    key_themes: list[str] | None
    resistance_detected: bool
    breakthrough_detected: bool
    ai_insight: str | None
    ai_feedback_shown: str | None
    submitted_at: datetime | None

    model_config = {"from_attributes": True}


class ReflectionSummary(BaseModel):
    id: UUID
    reflection_date: date
    sentiment: str | None
    depth_score: float | None
    breakthrough_detected: bool

    model_config = {"from_attributes": True}


# ─── Progress & Dashboard ────────────────────────────────────────────────────

class ScoreBreakdown(BaseModel):
    transformation: float        # 0-100 composite
    consistency: float           # 0-100
    depth: float                 # 0-100
    momentum: float              # 0-100
    alignment: float             # 0-100
    momentum_state: str          # rising|holding|declining|critical
    momentum_label: str          # human-readable


class StreakData(BaseModel):
    current_streak: int
    longest_streak: int
    last_active_date: date | None
    streak_label: str            # "14-day streak" or "Start your streak"


class DashboardResponse(BaseModel):
    """Single call that powers the main app screen."""
    today_task: TaskDetail | None
    scores: ScoreBreakdown
    streak: StreakData
    top_traits: list[TraitSummary]   # top 3 by gap
    recent_activity: list[dict]      # last 7 days summary
    latest_weekly_review: str | None # evolution letter preview
    days_active: int
    goal_summary: GoalSummary | None


# ─── Weekly Reviews ───────────────────────────────────────────────────────────

class WeeklyReviewSummary(BaseModel):
    week_start_date: date
    week_end_date: date
    tasks_completed: int
    tasks_total: int
    reflections_submitted: int
    consistency_pct: float
    evolution_letter: str
    generated_at: datetime

    model_config = {"from_attributes": True}


# ─── Onboarding ──────────────────────────────────────────────────────────────

class OnboardingStatusResponse(BaseModel):
    onboarding_status: str
    step: int
    total_steps: int
    next_action: str
    message: str | None
    is_complete: bool
