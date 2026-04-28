"""
db/models/identity_profile.py

ORM model for the identity_profiles table — the living user profile
that drives all AI personalization.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base


class IdentityProfile(Base):
    __tablename__ = "identity_profiles"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )

    # ── Layer 1: Static Foundation ────────────────────────────────────
    life_direction: Mapped[str | None] = mapped_column(Text)
    personal_vision: Mapped[str | None] = mapped_column(Text)
    core_values: Mapped[list | None] = mapped_column(ARRAY(String))
    self_reported_strengths: Mapped[list | None] = mapped_column(ARRAY(String))
    self_reported_weaknesses: Mapped[list | None] = mapped_column(ARRAY(String))
    time_availability: Mapped[dict | None] = mapped_column(JSONB)   # {morning: 30, evening: 60, weekend: 120}
    lifestyle_context: Mapped[dict | None] = mapped_column(JSONB)   # {workStyle, familyStatus, ...}

    # ── Layer 2: Behavioral Baseline ──────────────────────────────────
    consistency_pattern: Mapped[str | None] = mapped_column(String(50))   # daily_consistent|burst_worker|...
    motivation_style: Mapped[str | None] = mapped_column(String(50))      # aspiration_driven|fear_driven|...
    execution_style: Mapped[str | None] = mapped_column(String(50))       # planner|spontaneous|structured|...
    peak_performance_time: Mapped[str | None] = mapped_column(String(30)) # early_morning|afternoon|...
    resistance_triggers: Mapped[list | None] = mapped_column(ARRAY(String))
    social_context: Mapped[str | None] = mapped_column(String(50))        # self_driven|accountability_seeker|...

    # ── Layer 5: Transformation Scores (computed) ─────────────────────
    transformation_score: Mapped[float] = mapped_column(Float, default=0.0)
    consistency_score: Mapped[float] = mapped_column(Float, default=0.0)
    depth_score: Mapped[float] = mapped_column(Float, default=0.0)
    momentum_score: Mapped[float] = mapped_column(Float, default=0.0)
    alignment_score: Mapped[float] = mapped_column(Float, default=0.0)
    momentum_state: Mapped[str] = mapped_column(String(20), default="holding")  # rising|holding|declining|critical

    # Streak
    current_streak: Mapped[int] = mapped_column(Integer, default=0)
    longest_streak: Mapped[int] = mapped_column(Integer, default=0)
    last_active_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Profile metadata
    profile_version: Mapped[int] = mapped_column(Integer, default=1)
    last_ai_update: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # ── Commitment Gate ───────────────────────────────────────────────
    commitment_statement: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="identity_profile")  # noqa: F821

    def __repr__(self) -> str:
        return f"<IdentityProfile user_id={self.user_id} score={self.transformation_score}>"

    @property
    def momentum_label(self) -> str:
        labels = {
            "rising": "Rising",
            "holding": "Steady",
            "declining": "Needs attention",
            "critical": "Time to reconnect",
        }
        return labels.get(self.momentum_state, "Steady")
