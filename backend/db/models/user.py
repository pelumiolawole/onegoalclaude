"""
db/models/user.py

SQLAlchemy ORM model for the users table.
Maps directly to the schema defined in migration 001.
"""

import enum
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Enum, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base


class AuthProvider(str, enum.Enum):
    EMAIL = "email"
    GOOGLE = "google"
    APPLE = "apple"


class OnboardingStatus(str, enum.Enum):
    CREATED = "created"
    INTERVIEW_STARTED = "interview_started"
    INTERVIEW_COMPLETE = "interview_complete"
    GOAL_DEFINED = "goal_defined"
    STRATEGY_GENERATED = "strategy_generated"
    ACTIVE = "active"


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(255))
    avatar_url: Mapped[str | None] = mapped_column(Text)
    auth_provider: Mapped[AuthProvider] = mapped_column(
        Enum(AuthProvider, name="auth_provider", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=AuthProvider.EMAIL,
    )
    auth_provider_id: Mapped[str | None] = mapped_column(String(255), index=True)
    onboarding_status: Mapped[OnboardingStatus] = mapped_column(
        Enum(OnboardingStatus, name="onboarding_status", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=OnboardingStatus.CREATED,
    )
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    locale: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Stored as hashed value — None for OAuth users
    hashed_password: Mapped[str | None] = mapped_column(String(255))

    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    # Add to User class:
    subscription_plan: Mapped[str] = mapped_column(String(20), nullable=False, default="spark")
    subscription_status: Mapped[str | None] = mapped_column(String(20))
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255))
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255))
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    subscription_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    
    # ─── Relationships ─────────────────────────────────────────────────
    # lazy="selectin" means relationships are loaded automatically
    # on access without triggering lazy-load errors in async context

    identity_profile: Mapped["IdentityProfile"] = relationship(  # noqa: F821
        "IdentityProfile",
        back_populates="user",
        uselist=False,
        lazy="selectin",
    )
    goals: Mapped[list["Goal"]] = relationship(  # noqa: F821
        "Goal",
        back_populates="user",
        lazy="selectin",
        order_by="Goal.created_at.desc()",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email}>"

    @property
    def active_goal(self) -> "Goal | None":  # noqa: F821
        """Return the current active goal, if any."""
        return next((g for g in self.goals if g.status.value == "active"), None)

    @property
    def is_onboarded(self) -> bool:
        return self.onboarding_status == OnboardingStatus.ACTIVE

    @property
    def onboarding_step(self) -> int:
        """Return numeric step for frontend routing."""
        steps = {
            OnboardingStatus.CREATED: 0,
            OnboardingStatus.INTERVIEW_STARTED: 1,
            OnboardingStatus.INTERVIEW_COMPLETE: 2,
            OnboardingStatus.GOAL_DEFINED: 3,
            OnboardingStatus.STRATEGY_GENERATED: 4,
            OnboardingStatus.ACTIVE: 5,
        }
        return steps.get(self.onboarding_status, 0)
