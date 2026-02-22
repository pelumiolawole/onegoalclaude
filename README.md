# One Goal — Complete Architecture & Schema Reference

## Project Structure

```
one-goal/
├── frontend/                      # Next.js 14 (App Router)
│   └── src/
│       ├── app/                   # Pages and layouts
│       │   ├── (auth)/            # Auth screens: login, signup
│       │   ├── (onboarding)/      # Interview + goal setup
│       │   ├── (app)/             # Protected app screens
│       │   │   ├── dashboard/     # Daily home screen
│       │   │   ├── coach/         # AI coach chat
│       │   │   ├── progress/      # Analytics and tracking
│       │   │   ├── goal/          # Goal management
│       │   │   └── settings/      # Account, privacy, data export
│       │   └── api/               # Next.js API routes (BFF layer)
│       ├── components/
│       │   ├── ui/                # Base design system components
│       │   ├── onboarding/        # Interview chat components
│       │   ├── dashboard/         # Daily loop components
│       │   ├── coach/             # Coach chat UI
│       │   └── progress/          # Charts and metrics
│       ├── hooks/                 # Custom React hooks
│       ├── lib/                   # API client, utilities
│       ├── stores/                # Zustand state management
│       └── types/                 # TypeScript types (shared)
│
├── backend/                       # FastAPI (Python)
│   ├── main.py                    # App entrypoint
│   ├── api/
│   │   ├── routers/
│   │   │   ├── auth.py            # Auth endpoints
│   │   │   ├── users.py           # User profile endpoints
│   │   │   ├── goals.py           # Goal CRUD + decomposition
│   │   │   ├── tasks.py           # Daily task endpoints
│   │   │   ├── reflections.py     # Reflection submission
│   │   │   ├── coach.py           # AI coach chat (streaming)
│   │   │   ├── progress.py        # Analytics + metrics
│   │   │   ├── onboarding.py      # Interview endpoints
│   │   │   └── data.py            # Export + delete endpoints
│   │   ├── schemas/               # Pydantic request/response models
│   │   └── dependencies/          # Auth, DB, rate limiting deps
│   ├── ai/
│   │   ├── engines/
│   │   │   ├── interview.py       # AI Discovery Interview engine
│   │   │   ├── goal_decomposer.py # Goal → Strategy engine
│   │   │   ├── task_generator.py  # Daily task generation
│   │   │   ├── reflection_analyzer.py # Reflection scoring + insights
│   │   │   ├── coach.py           # AI Coach with full context
│   │   │   └── profile_updater.py # Identity profile evolution
│   │   ├── prompts/               # All system prompts (versioned)
│   │   │   ├── interview.py
│   │   │   ├── goal_decomposer.py
│   │   │   ├── task_generator.py
│   │   │   ├── reflection_analyzer.py
│   │   │   ├── coach.py
│   │   │   └── safety.py          # Safety detection prompts
│   │   ├── memory/
│   │   │   ├── context_builder.py # Assembles user context for AI
│   │   │   ├── embedding.py       # Embedding generation + storage
│   │   │   └── retrieval.py       # Semantic memory search
│   │   └── utils/
│   │       ├── cost_tracker.py    # Token counting + cost logging
│   │       ├── safety_filter.py   # Crisis + safety detection
│   │       └── output_parser.py   # Structured output parsing
│   ├── db/
│   │   ├── migrations/            # SQL migration files (numbered)
│   │   ├── seeds/                 # Test data seeds
│   │   └── models/                # SQLAlchemy ORM models
│   ├── services/
│   │   ├── scoring.py             # Score computation service
│   │   ├── streak.py              # Streak management
│   │   ├── weekly_review.py       # Weekly review generation
│   │   ├── notifications.py       # Notification queue service
│   │   └── scheduler.py           # Background job scheduler (APScheduler)
│   └── core/
│       ├── config.py              # Environment config (pydantic-settings)
│       ├── security.py            # JWT, auth helpers
│       ├── database.py            # DB connection pool
│       ├── cache.py               # Redis connection
│       └── middleware.py          # CORS, rate limiting, logging
│
├── shared/
│   └── types/                     # Shared TypeScript type definitions
│
└── infrastructure/
    ├── docker/
    │   ├── docker-compose.yml     # Local dev environment
    │   ├── Dockerfile.backend
    │   └── Dockerfile.frontend
    └── scripts/
        ├── migrate.sh             # Run migrations
        ├── seed.sh                # Seed development data
        └── backup.sh              # DB backup script
```

---

## Database Schema Reference

### Entity Relationship Overview

```
users
  └── identity_profiles (1:1)       ← Living profile document
  └── identity_traits (1:many)      ← Per-goal traits, AI-generated
  └── goals (1:many, 1 active)      ← The ONE goal
        └── objectives (1:many)     ← 3-5 sub-goals
              └── milestones (1:many) ← Checkpoint markers
  └── daily_tasks (1:many)          ← One primary task per day
        └── reflections (1:1)       ← End-of-day reflection
  └── ai_coach_sessions (1:many)    ← Conversation threads
        └── ai_coach_messages (1:many) ← Individual messages
  └── progress_metrics (1:many)     ← Daily snapshot archive
  └── behavioral_patterns (1:many)  ← AI-detected behavior patterns
  └── behavioral_snapshots (1:many) ← Weekly behavioral fingerprint
  └── weekly_reviews (1:many)       ← AI evolution letters
  └── notification_queue (1:many)   ← Scheduled notifications
  └── integration_configs (1:many)  ← External service connections
  └── onboarding_interview_state (1:1) ← Interview progress
  └── data_processing_consent (1:many) ← GDPR consent records
```

---

## Scoring System

### Transformation Score Formula

```
Score = (Consistency × 0.35) + (Depth × 0.25) + (Momentum × 0.25) + (Alignment × 0.15)
```

| Dimension | Weight | Source | Range |
|-----------|--------|--------|-------|
| Consistency | 35% | Task completion last 14 days | 0–100 |
| Depth | 25% | Average reflection quality (AI-graded) | 0–100 |
| Momentum | 25% | Last 7 days vs prior 7 days trajectory | 0–100 |
| Alignment | 15% | Average identity trait scores | 0–100 |

### Momentum States

| State | Score Range | System Behavior |
|-------|------------|-----------------|
| Rising | 65–100 | Celebrate mode, increase challenge |
| Holding | 40–64 | Steady guidance, maintain pace |
| Declining | 20–39 | Support mode, reduce friction |
| Critical | 0–19 | Intervention mode, coach check-in |

### Identity Trait Scoring

Each trait scored 1–10, updated weekly by the Reflection Analyzer.

Trait Velocity = (current_score - score_7_days_ago) / 7

Displayed to user as qualitative language, never raw numbers.

---

## AI Engine Summary

| Engine | Trigger | Input | Output |
|--------|---------|-------|--------|
| Interview Engine | Onboarding | User messages | Structured profile data |
| Goal Decomposer | Goal submission | Raw goal + profile | Refined goal, objectives, traits |
| Task Generator | Nightly job (9pm UTC) | Profile + history | Tomorrow's identity focus + task |
| Reflection Analyzer | Reflection submission | Reflection text + context | Scores, sentiment, trait evidence |
| AI Coach | User message | Full context + history | Streaming response |
| Profile Updater | Weekly (Sunday) | All weekly data | Updated identity profile |

---

## Migrations Execution Order

```bash
psql $DATABASE_URL -f migrations/001_initial_schema.sql
psql $DATABASE_URL -f migrations/002_scoring_system.sql
psql $DATABASE_URL -f migrations/003_behavioral_analytics.sql
psql $DATABASE_URL -f migrations/004_privacy_and_security.sql
```

---

## Key Design Decisions

**1. One Active Goal Constraint**
Enforced at the database level via a partial unique index. Application layer also validates this. The constraint is the product.

**2. Embeddings Alongside Relational Data**
pgvector lives in the same PostgreSQL instance as all other data. This avoids a separate vector database while still enabling semantic memory retrieval.

**3. get_user_ai_context() as Central Contract**
Every AI engine calls this function to get user context. This means context assembly logic lives in one place and all engines stay synchronized.

**4. Safety Flags Separate from User Data**
The ai_safety_flags table is only accessible by the service role. Users cannot see or delete their safety flags — this is intentional for welfare tracking purposes.

**5. Scores Stored, Not Computed on Read**
All scores are computed nightly by a background job and stored in identity_profiles. This makes dashboard reads instant and avoids expensive real-time computation.
