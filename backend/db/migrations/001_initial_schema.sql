-- ============================================================
-- ONE GOAL — Complete Database Schema
-- Migration: 001_initial_schema
-- ============================================================
-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgvector";
CREATE EXTENSION IF NOT EXISTS "pg_trgm"; -- for text search on reflections

-- ============================================================
-- ENUMS
-- ============================================================

CREATE TYPE auth_provider AS ENUM ('email', 'google', 'apple');
CREATE TYPE onboarding_status AS ENUM (
  'created',
  'interview_started',
  'interview_complete',
  'goal_defined',
  'strategy_generated',
  'active'
);
CREATE TYPE goal_status AS ENUM ('draft', 'active', 'paused', 'completed', 'abandoned');
CREATE TYPE task_status AS ENUM ('pending', 'completed', 'skipped', 'deferred');
CREATE TYPE task_type AS ENUM ('becoming', 'identity_anchor', 'micro_action', 'reflection_prompt', 'challenge');
CREATE TYPE reflection_sentiment AS ENUM ('positive', 'neutral', 'resistant', 'struggling', 'breakthrough');
CREATE TYPE coaching_mode AS ENUM ('guide', 'support', 'challenge', 'celebrate', 'intervention');
CREATE TYPE trait_category AS ENUM ('mindset', 'behavior', 'discipline', 'social', 'emotional', 'cognitive');
CREATE TYPE milestone_status AS ENUM ('upcoming', 'in_progress', 'completed', 'missed');
CREATE TYPE momentum_state AS ENUM ('rising', 'holding', 'declining', 'critical');

-- ============================================================
-- TABLE: users
-- Core identity. Minimal data stored here.
-- ============================================================
CREATE TABLE users (
  id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  email             TEXT UNIQUE NOT NULL,
  display_name      TEXT,
  avatar_url        TEXT,
  auth_provider     auth_provider NOT NULL DEFAULT 'email',
  auth_provider_id  TEXT,                        -- external ID from Google/Apple
  onboarding_status onboarding_status NOT NULL DEFAULT 'created',
  timezone          TEXT NOT NULL DEFAULT 'UTC',
  locale            TEXT NOT NULL DEFAULT 'en',
  is_active         BOOLEAN NOT NULL DEFAULT TRUE,
  last_seen_at      TIMESTAMPTZ,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_auth_provider ON users(auth_provider, auth_provider_id);

-- ============================================================
-- TABLE: identity_profiles
-- The living document that captures who the user is
-- and who they are becoming. One per user. Updated continuously.
-- ============================================================
CREATE TABLE identity_profiles (
  id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id                 UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,

  -- Static foundation (from onboarding interview)
  life_direction          TEXT,                  -- career/life direction in their words
  personal_vision         TEXT,                  -- where they want to be in 3-5 years
  core_values             TEXT[],                -- e.g. ['freedom', 'impact', 'growth']
  self_reported_strengths TEXT[],
  self_reported_weaknesses TEXT[],
  time_availability       JSONB,                 -- { morning: 30, evening: 60, weekend: 120 } minutes
  lifestyle_context       JSONB,                 -- { workStyle: 'remote', familyStatus: 'parent', etc }

  -- Behavioral baseline (built over first 2 weeks, AI-inferred)
  consistency_pattern     TEXT,                  -- 'morning_sprinter', 'evening_builder', 'weekend_warrior'
  motivation_style        TEXT,                  -- 'aspiration_driven', 'fear_driven', 'values_driven'
  execution_style         TEXT,                  -- 'planner', 'spontaneous', 'systems_thinker'
  social_context          TEXT,                  -- 'self_driven', 'accountability_seeker', 'community_motivated'
  resistance_triggers     TEXT[],                -- common patterns: ['overwhelm', 'perfectionism', 'fatigue']
  peak_performance_time   TEXT,                  -- 'early_morning', 'late_morning', 'afternoon', 'evening'

  -- AI-inferred personality signals (not MBTI — behavioral)
  personality_signals     JSONB,                 -- { introspective: 0.8, competitive: 0.3, ... }

  -- Transformation metrics (computed and updated)
  transformation_score    NUMERIC(5,2) DEFAULT 0, -- 0-100 composite
  consistency_score       NUMERIC(5,2) DEFAULT 0,
  depth_score             NUMERIC(5,2) DEFAULT 0,
  momentum_score          NUMERIC(5,2) DEFAULT 0,
  alignment_score         NUMERIC(5,2) DEFAULT 0,
  momentum_state          momentum_state DEFAULT 'holding',
  current_streak          INTEGER DEFAULT 0,
  longest_streak          INTEGER DEFAULT 0,

  -- AI profile embedding (for semantic memory retrieval)
  profile_embedding       vector(1536),          -- OpenAI ada-002 embedding of full profile summary

  -- Metadata
  last_ai_update          TIMESTAMPTZ,           -- when AI last updated this profile
  profile_version         INTEGER DEFAULT 1,     -- incremented on significant updates
  created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_identity_profiles_user ON identity_profiles(user_id);
CREATE INDEX idx_identity_profiles_embedding ON identity_profiles USING ivfflat (profile_embedding vector_cosine_ops);

-- ============================================================
-- TABLE: identity_traits
-- Individual traits the user needs to develop.
-- Each scored 1-10, tracked over time, AI-updated weekly.
-- ============================================================
CREATE TABLE identity_traits (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  goal_id         UUID,                          -- FK added after goals table (ALTER below)
  name            TEXT NOT NULL,                 -- 'disciplined', 'decisive', 'resilient'
  description     TEXT,                          -- what this trait means for this user specifically
  category        trait_category NOT NULL,
  is_ai_generated BOOLEAN DEFAULT TRUE,
  current_score   NUMERIC(3,1) DEFAULT 1.0,      -- 1.0 - 10.0
  target_score    NUMERIC(3,1) DEFAULT 8.0,
  velocity        NUMERIC(4,2) DEFAULT 0.0,      -- change per week, can be negative
  evidence_ids    UUID[],                        -- reflection IDs that demonstrate this trait
  blocker_signals TEXT[],                        -- signals indicating resistance to this trait
  is_active       BOOLEAN DEFAULT TRUE,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_identity_traits_user ON identity_traits(user_id);
CREATE INDEX idx_identity_traits_active ON identity_traits(user_id, is_active);

-- ============================================================
-- TABLE: goals
-- The ONE goal. A user should only have one active goal at a time.
-- Previous goals are preserved for history.
-- ============================================================
CREATE TABLE goals (
  id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  status              goal_status NOT NULL DEFAULT 'draft',

  -- Goal content
  raw_input           TEXT NOT NULL,             -- what the user typed originally
  refined_statement   TEXT,                      -- AI-refined version
  why_statement       TEXT,                      -- their deep motivation (from AI interview)
  success_definition  TEXT,                      -- what achievement looks like to them

  -- AI decomposition
  required_identity   TEXT,                      -- "The person who achieves this is someone who..."
  key_shifts          TEXT[],                    -- behavioral/mindset shifts required
  estimated_timeline  INTEGER,                   -- weeks, AI-estimated
  difficulty_level    INTEGER DEFAULT 5,         -- 1-10, AI-assessed, adaptive

  -- Progress
  progress_percentage NUMERIC(5,2) DEFAULT 0,
  objectives_count    INTEGER DEFAULT 0,
  objectives_completed INTEGER DEFAULT 0,

  -- Metadata
  started_at          TIMESTAMPTZ,
  target_date         DATE,
  completed_at        TIMESTAMPTZ,
  abandoned_at        TIMESTAMPTZ,
  abandon_reason      TEXT,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  -- Enforce single active goal per user
  CONSTRAINT one_active_goal_per_user UNIQUE (user_id, status) DEFERRABLE INITIALLY DEFERRED
);

-- Note: partial unique index enforces ONE active goal
CREATE UNIQUE INDEX idx_goals_one_active ON goals(user_id) WHERE status = 'active';
CREATE INDEX idx_goals_user ON goals(user_id, status);

-- Add FK from identity_traits to goals
ALTER TABLE identity_traits ADD CONSTRAINT fk_traits_goal FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE SET NULL;

-- ============================================================
-- TABLE: objectives
-- 3-5 sub-goals that together constitute achieving the main goal.
-- Each is a meaningful milestone, not a task.
-- ============================================================
CREATE TABLE objectives (
  id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  goal_id             UUID NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
  user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title               TEXT NOT NULL,
  description         TEXT,
  success_criteria    TEXT,                      -- what "done" looks like
  sequence_order      INTEGER NOT NULL,          -- 1, 2, 3...
  status              milestone_status DEFAULT 'upcoming',
  progress_percentage NUMERIC(5,2) DEFAULT 0,
  estimated_weeks     INTEGER,
  started_at          TIMESTAMPTZ,
  completed_at        TIMESTAMPTZ,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_objectives_goal ON objectives(goal_id, sequence_order);
CREATE INDEX idx_objectives_user ON objectives(user_id);

-- ============================================================
-- TABLE: milestones
-- Specific, AI-defined checkpoints within an objective.
-- ============================================================
CREATE TABLE milestones (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  objective_id    UUID NOT NULL REFERENCES objectives(id) ON DELETE CASCADE,
  user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title           TEXT NOT NULL,
  description     TEXT,
  identity_signal TEXT,                          -- "Reaching this means you are someone who..."
  target_date     DATE,
  status          milestone_status DEFAULT 'upcoming',
  completed_at    TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_milestones_objective ON milestones(objective_id);

-- ============================================================
-- TABLE: daily_tasks
-- The core daily loop unit. One primary task per day.
-- AI-generated nightly based on profile + progress.
-- ============================================================
CREATE TABLE daily_tasks (
  id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id               UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  goal_id               UUID REFERENCES goals(id) ON DELETE SET NULL,
  objective_id          UUID REFERENCES objectives(id) ON DELETE SET NULL,

  -- Scheduling
  scheduled_date        DATE NOT NULL,
  task_type             task_type NOT NULL DEFAULT 'becoming',

  -- Content (AI-generated)
  identity_focus        TEXT NOT NULL,           -- "Today you are someone who..."
  title                 TEXT NOT NULL,           -- the becoming task title
  description           TEXT,                    -- what to do and why it matters
  execution_guidance    TEXT,                    -- how to do it (step-by-step or approach)
  time_estimate_minutes INTEGER DEFAULT 30,
  difficulty_level      INTEGER DEFAULT 5,       -- 1-10, adaptive

  -- AI generation context
  generated_by_ai       BOOLEAN DEFAULT TRUE,
  generation_context    JSONB,                   -- snapshot of profile state when generated
  generation_model      TEXT DEFAULT 'gpt-4o',

  -- Status
  status                task_status DEFAULT 'pending',
  started_at            TIMESTAMPTZ,
  completed_at          TIMESTAMPTZ,
  skipped_reason        TEXT,

  -- Execution data
  execution_notes       TEXT,                    -- user's notes during execution
  actual_duration_mins  INTEGER,                 -- how long it actually took

  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_daily_tasks_user_date ON daily_tasks(user_id, scheduled_date DESC);
CREATE INDEX idx_daily_tasks_status ON daily_tasks(user_id, status);
CREATE UNIQUE INDEX idx_daily_tasks_one_per_day ON daily_tasks(user_id, scheduled_date) WHERE task_type = 'becoming';

-- ============================================================
-- TABLE: reflections
-- Daily end-of-day reflection. 2-3 AI-generated questions.
-- AI analyzes responses to update profile and score.
-- ============================================================
CREATE TABLE reflections (
  id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id               UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  task_id               UUID REFERENCES daily_tasks(id) ON DELETE SET NULL,
  reflection_date       DATE NOT NULL,

  -- Questions + responses (JSONB for flexibility)
  questions_answers     JSONB NOT NULL,
  -- Format: [{ question: "...", answer: "...", question_type: "execution|emotion|identity" }]

  -- AI analysis of this reflection
  sentiment             reflection_sentiment,
  depth_score           NUMERIC(3,1),            -- 1-10, how thoughtful the response was
  word_count            INTEGER,
  emotional_tone        TEXT,                    -- nuanced: 'encouraged', 'frustrated', 'curious', etc.
  key_themes            TEXT[],                  -- extracted themes
  resistance_detected   BOOLEAN DEFAULT FALSE,
  breakthrough_detected BOOLEAN DEFAULT FALSE,
  ai_insight            TEXT,                    -- AI's synthesized insight from this reflection
  ai_feedback_shown     TEXT,                    -- what feedback was displayed to user

  -- Trait evidence extracted from this reflection
  trait_evidence        JSONB,
  -- Format: [{ trait_id: uuid, signal: "positive|negative", excerpt: "..." }]

  -- Embedding for semantic memory
  content_embedding     vector(1536),

  -- Metadata
  submitted_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  analyzed_at           TIMESTAMPTZ,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_reflections_user_date ON reflections(user_id, reflection_date DESC);
CREATE INDEX idx_reflections_sentiment ON reflections(user_id, sentiment);
CREATE INDEX idx_reflections_embedding ON reflections USING ivfflat (content_embedding vector_cosine_ops);

-- ============================================================
-- TABLE: ai_coach_sessions
-- Each conversation thread with the AI coach.
-- Sessions group related messages.
-- ============================================================
CREATE TABLE ai_coach_sessions (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title           TEXT,                          -- auto-generated from first message
  coaching_mode   coaching_mode DEFAULT 'guide',
  message_count   INTEGER DEFAULT 0,
  is_active       BOOLEAN DEFAULT TRUE,
  started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_message_at TIMESTAMPTZ,
  ended_at        TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_coach_sessions_user ON ai_coach_sessions(user_id, started_at DESC);

-- ============================================================
-- TABLE: ai_coach_messages
-- Individual messages in a coach session.
-- Stores both user messages and AI responses with full context.
-- ============================================================
CREATE TABLE ai_coach_messages (
  id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  session_id          UUID NOT NULL REFERENCES ai_coach_sessions(id) ON DELETE CASCADE,
  user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role                TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
  content             TEXT NOT NULL,             -- Encrypted field in production

  -- AI generation metadata
  model_used          TEXT,
  prompt_tokens       INTEGER,
  completion_tokens   INTEGER,
  generation_latency_ms INTEGER,

  -- Semantic search
  content_embedding   vector(1536),

  -- Signals extracted from this message
  resistance_signal   BOOLEAN DEFAULT FALSE,
  sentiment           TEXT,
  key_topics          TEXT[],

  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_coach_messages_session ON ai_coach_messages(session_id, created_at ASC);
CREATE INDEX idx_coach_messages_user ON ai_coach_messages(user_id, created_at DESC);
CREATE INDEX idx_coach_messages_embedding ON ai_coach_messages USING ivfflat (content_embedding vector_cosine_ops);

-- ============================================================
-- TABLE: ai_interactions
-- Log of every AI call made across all engines.
-- Used for cost tracking, debugging, and safety auditing.
-- ============================================================
CREATE TABLE ai_interactions (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id         UUID REFERENCES users(id) ON DELETE SET NULL,
  engine          TEXT NOT NULL,                 -- 'interview', 'goal_decomposer', 'task_generator', 'reflection_analyzer', 'coach', 'profile_updater'
  model           TEXT NOT NULL,
  prompt_tokens   INTEGER NOT NULL DEFAULT 0,
  completion_tokens INTEGER NOT NULL DEFAULT 0,
  total_tokens    INTEGER GENERATED ALWAYS AS (prompt_tokens + completion_tokens) STORED,
  estimated_cost_usd NUMERIC(10,6),
  latency_ms      INTEGER,
  success         BOOLEAN DEFAULT TRUE,
  error_message   TEXT,
  request_hash    TEXT,                          -- for deduplication
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_ai_interactions_user ON ai_interactions(user_id, created_at DESC);
CREATE INDEX idx_ai_interactions_engine ON ai_interactions(engine, created_at DESC);
CREATE INDEX idx_ai_interactions_cost ON ai_interactions(created_at DESC) WHERE success = TRUE;

-- ============================================================
-- TABLE: progress_metrics
-- Daily snapshot of all computed metrics.
-- Preserved for analytics, graphs, weekly reviews.
-- ============================================================
CREATE TABLE progress_metrics (
  id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id                 UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  metric_date             DATE NOT NULL,

  -- Scores at end of day
  transformation_score    NUMERIC(5,2),
  consistency_score       NUMERIC(5,2),
  depth_score             NUMERIC(5,2),
  momentum_score          NUMERIC(5,2),
  alignment_score         NUMERIC(5,2),

  -- Daily activity
  task_completed          BOOLEAN DEFAULT FALSE,
  reflection_submitted    BOOLEAN DEFAULT FALSE,
  coach_messages_sent     INTEGER DEFAULT 0,
  execution_minutes       INTEGER DEFAULT 0,

  -- Streak data
  streak_count            INTEGER DEFAULT 0,
  streak_broken           BOOLEAN DEFAULT FALSE,
  momentum_state          momentum_state DEFAULT 'holding',

  -- Weekly aggregates (populated on Sunday)
  is_week_end             BOOLEAN DEFAULT FALSE,
  weekly_consistency_pct  NUMERIC(5,2),
  weekly_avg_depth        NUMERIC(5,2),
  weekly_evolution_text   TEXT,                  -- AI-written weekly evolution letter

  created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  UNIQUE(user_id, metric_date)
);

CREATE INDEX idx_progress_metrics_user_date ON progress_metrics(user_id, metric_date DESC);

-- ============================================================
-- TABLE: behavioral_patterns
-- AI-detected patterns stored for profile adaptation.
-- These feed the adaptive system and coaching strategy.
-- ============================================================
CREATE TABLE behavioral_patterns (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  pattern_type    TEXT NOT NULL,                 -- 'resistance', 'peak_performance', 'avoidance', 'breakthrough', 'consistency'
  pattern_name    TEXT NOT NULL,                 -- human-readable: 'Avoids tasks on Monday mornings'
  description     TEXT,
  confidence      NUMERIC(3,2) DEFAULT 0.5,      -- 0-1, AI confidence in this pattern
  evidence_count  INTEGER DEFAULT 1,             -- how many data points support this
  first_detected  DATE,
  last_confirmed  DATE,
  is_active       BOOLEAN DEFAULT TRUE,
  action_taken    TEXT,                          -- how the system responded to this pattern
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_behavioral_patterns_user ON behavioral_patterns(user_id, is_active);

-- ============================================================
-- TABLE: weekly_reviews
-- AI-generated weekly review stored for user access.
-- The highest-retention feature — users return to read these.
-- ============================================================
CREATE TABLE weekly_reviews (
  id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id               UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  week_start_date       DATE NOT NULL,
  week_end_date         DATE NOT NULL,

  -- Computed stats for the week
  tasks_completed       INTEGER DEFAULT 0,
  tasks_total           INTEGER DEFAULT 0,
  reflections_submitted INTEGER DEFAULT 0,
  avg_depth_score       NUMERIC(3,1),
  consistency_pct       NUMERIC(5,2),
  score_delta           NUMERIC(5,2),            -- transformation score change this week

  -- AI-generated content
  evolution_letter      TEXT,                    -- personal letter: who they became this week
  key_insights          TEXT[],                  -- 3 most important insights
  next_week_focus       TEXT,                    -- AI recommendation for next week
  trait_progress        JSONB,                   -- snapshot of trait scores this week

  -- Read tracking
  read_at               TIMESTAMPTZ,
  generated_at          TIMESTAMPTZ,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  UNIQUE(user_id, week_start_date)
);

CREATE INDEX idx_weekly_reviews_user ON weekly_reviews(user_id, week_start_date DESC);

-- ============================================================
-- TABLE: notification_queue
-- Future-ready: push notifications, prompts, reminders.
-- Architecture ready even if initially mocked.
-- ============================================================
CREATE TABLE notification_queue (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  type            TEXT NOT NULL,                 -- 'daily_task', 'streak_reminder', 'coach_checkin', 'milestone', 'weekly_review'
  title           TEXT NOT NULL,
  body            TEXT NOT NULL,
  data            JSONB,                         -- any extra data for deep linking
  channel         TEXT NOT NULL DEFAULT 'push', -- 'push', 'email', 'in_app'
  scheduled_at    TIMESTAMPTZ NOT NULL,
  sent_at         TIMESTAMPTZ,
  opened_at       TIMESTAMPTZ,
  cancelled_at    TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_notifications_user ON notification_queue(user_id, scheduled_at);
CREATE INDEX idx_notifications_pending ON notification_queue(scheduled_at) WHERE sent_at IS NULL AND cancelled_at IS NULL;

-- ============================================================
-- TABLE: integration_configs
-- Future-ready: calendar sync, wearables, widgets.
-- ============================================================
CREATE TABLE integration_configs (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  integration     TEXT NOT NULL,                 -- 'google_calendar', 'apple_calendar', 'apple_health', 'widget'
  is_enabled      BOOLEAN DEFAULT FALSE,
  config          JSONB,                         -- integration-specific config (tokens, settings)
  last_synced_at  TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  UNIQUE(user_id, integration)
);

-- ============================================================
-- TABLE: onboarding_interview_state
-- Tracks progress through the AI discovery interview.
-- Allows resuming if user drops off.
-- ============================================================
CREATE TABLE onboarding_interview_state (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id         UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
  current_phase   TEXT NOT NULL DEFAULT 'intro',
  -- phases: intro > life_direction > vision > habits > strengths > frustrations > time > lifestyle > summary
  messages        JSONB NOT NULL DEFAULT '[]',   -- full conversation history
  extracted_data  JSONB NOT NULL DEFAULT '{}',   -- structured data extracted so far
  phase_progress  JSONB NOT NULL DEFAULT '{}',   -- { phase: completed_bool }
  is_complete     BOOLEAN DEFAULT FALSE,
  started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at    TIMESTAMPTZ,
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- FUNCTIONS & TRIGGERS
-- ============================================================

-- Auto-update updated_at on all tables
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply to all tables with updated_at
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_identity_profiles_updated_at BEFORE UPDATE ON identity_profiles FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_identity_traits_updated_at BEFORE UPDATE ON identity_traits FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_goals_updated_at BEFORE UPDATE ON goals FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_objectives_updated_at BEFORE UPDATE ON objectives FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_milestones_updated_at BEFORE UPDATE ON milestones FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_daily_tasks_updated_at BEFORE UPDATE ON daily_tasks FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_behavioral_patterns_updated_at BEFORE UPDATE ON behavioral_patterns FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_integration_configs_updated_at BEFORE UPDATE ON integration_configs FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_onboarding_interview_state_updated_at BEFORE UPDATE ON onboarding_interview_state FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Auto-create identity profile when user is created
CREATE OR REPLACE FUNCTION create_identity_profile_for_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO identity_profiles (user_id)
  VALUES (NEW.id);
  RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER auto_create_identity_profile
  AFTER INSERT ON users
  FOR EACH ROW
  EXECUTE FUNCTION create_identity_profile_for_new_user();

-- Auto-create onboarding interview state when user is created
CREATE OR REPLACE FUNCTION create_onboarding_state_for_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO onboarding_interview_state (user_id)
  VALUES (NEW.id);
  RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER auto_create_onboarding_state
  AFTER INSERT ON users
  FOR EACH ROW
  EXECUTE FUNCTION create_onboarding_state_for_new_user();

-- Update goal progress when objectives change
CREATE OR REPLACE FUNCTION update_goal_progress()
RETURNS TRIGGER AS $$
DECLARE
  v_total INTEGER;
  v_completed INTEGER;
BEGIN
  SELECT COUNT(*), COUNT(*) FILTER (WHERE status = 'completed')
  INTO v_total, v_completed
  FROM objectives
  WHERE goal_id = COALESCE(NEW.goal_id, OLD.goal_id);

  UPDATE goals
  SET
    objectives_count = v_total,
    objectives_completed = v_completed,
    progress_percentage = CASE WHEN v_total > 0 THEN (v_completed::NUMERIC / v_total * 100) ELSE 0 END
  WHERE id = COALESCE(NEW.goal_id, OLD.goal_id);

  RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_goal_progress_on_objective_change
  AFTER INSERT OR UPDATE ON objectives
  FOR EACH ROW
  EXECUTE FUNCTION update_goal_progress();

-- ============================================================
-- VIEWS
-- Useful read-only views for the application layer
-- ============================================================

-- User dashboard summary — everything needed for daily screen
CREATE VIEW user_dashboard AS
SELECT
  u.id AS user_id,
  u.display_name,
  u.onboarding_status,
  ip.transformation_score,
  ip.consistency_score,
  ip.momentum_state,
  ip.current_streak,
  ip.longest_streak,
  g.id AS goal_id,
  g.refined_statement AS goal,
  g.progress_percentage AS goal_progress,
  -- Today's task
  dt.id AS today_task_id,
  dt.identity_focus,
  dt.title AS today_task,
  dt.status AS task_status,
  dt.scheduled_date AS task_date,
  -- This week stats
  (SELECT COUNT(*) FROM progress_metrics pm
   WHERE pm.user_id = u.id
   AND pm.metric_date >= DATE_TRUNC('week', CURRENT_DATE)
   AND pm.task_completed = TRUE) AS week_tasks_completed
FROM users u
LEFT JOIN identity_profiles ip ON ip.user_id = u.id
LEFT JOIN goals g ON g.user_id = u.id AND g.status = 'active'
LEFT JOIN daily_tasks dt ON dt.user_id = u.id AND dt.scheduled_date = CURRENT_DATE AND dt.task_type = 'becoming';

-- Active identity traits with progress
CREATE VIEW trait_progress_summary AS
SELECT
  it.user_id,
  it.id AS trait_id,
  it.name,
  it.category,
  it.current_score,
  it.target_score,
  it.velocity,
  ROUND(it.current_score / it.target_score * 100, 1) AS progress_pct,
  it.target_score - it.current_score AS gap,
  CASE
    WHEN it.velocity > 0.5 THEN 'accelerating'
    WHEN it.velocity > 0 THEN 'growing'
    WHEN it.velocity = 0 THEN 'stable'
    ELSE 'declining'
  END AS trend
FROM identity_traits it
WHERE it.is_active = TRUE
ORDER BY it.user_id, it.current_score ASC; -- show lowest-progress traits first

-- ============================================================
-- SEED: System configuration
-- ============================================================
CREATE TABLE system_config (
  key   TEXT PRIMARY KEY,
  value JSONB NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO system_config (key, value) VALUES
  ('scoring_weights', '{"consistency": 0.35, "depth": 0.25, "momentum": 0.25, "alignment": 0.15}'),
  ('streak_decay_rate', '5'),
  ('streak_recovery_rate', '3'),
  ('coach_daily_message_limit', '20'),
  ('task_generation_hour_utc', '21'),
  ('weekly_review_day', '"sunday"'),
  ('resistance_detection_threshold', '2'),
  ('max_active_traits', '7'),
  ('onboarding_interview_phases', '["intro","life_direction","vision","habits","strengths","frustrations","time","lifestyle","summary"]');
