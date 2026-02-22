-- ============================================================
-- ONE GOAL — Behavioral Analytics & Retention Mechanics
-- Migration: 003_behavioral_analytics
-- ============================================================

-- ============================================================
-- TABLE: behavioral_snapshots
-- Weekly behavioral fingerprint. Computed every Sunday.
-- Foundation for the adaptive task generation system.
-- ============================================================
CREATE TABLE behavioral_snapshots (
  id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id                 UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  week_start_date         DATE NOT NULL,

  -- Activity patterns
  avg_completion_time     TIME,               -- average time of day they complete tasks
  most_active_day         TEXT,               -- 'monday', 'tuesday', etc.
  least_active_day        TEXT,
  morning_person_score    NUMERIC(3,2),       -- 0-1, higher = morning engagement
  weekend_engagement      NUMERIC(3,2),       -- 0-1, relative to weekday engagement

  -- Quality patterns
  avg_reflection_words    INTEGER,
  avg_depth_score         NUMERIC(3,1),
  reflection_growth       NUMERIC(4,2),       -- depth score delta from prior week
  emotional_range         TEXT[],             -- sentiments observed: ['positive', 'resistant']

  -- Behavioral signals
  resistance_episodes     INTEGER DEFAULT 0,
  breakthrough_episodes   INTEGER DEFAULT 0,
  coach_engagement_count  INTEGER DEFAULT 0,
  avg_session_length_mins INTEGER,

  -- AI-written behavioral summary for this week
  behavior_summary        TEXT,
  dominant_pattern        TEXT,               -- 'building_momentum', 'struggling', 'consistent', 'erratic'

  created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  UNIQUE(user_id, week_start_date)
);

CREATE INDEX idx_behavioral_snapshots_user ON behavioral_snapshots(user_id, week_start_date DESC);

-- ============================================================
-- TABLE: engagement_events
-- Granular engagement tracking without being invasive.
-- Used for retention analysis and adaptive scheduling.
-- ============================================================
CREATE TABLE engagement_events (
  id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  event_type    TEXT NOT NULL,
  -- event types: 'app_open', 'task_start', 'task_complete', 'reflection_start',
  --              'reflection_submit', 'coach_open', 'weekly_review_read',
  --              'milestone_view', 'streak_view', 'goal_view'
  event_date    DATE NOT NULL DEFAULT CURRENT_DATE,
  event_time    TIME NOT NULL DEFAULT CURRENT_TIME,
  session_id    TEXT,                        -- groups events in same app session
  metadata      JSONB,                       -- event-specific data
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_engagement_events_user_date ON engagement_events(user_id, event_date DESC);
CREATE INDEX idx_engagement_events_type ON engagement_events(user_id, event_type, event_date DESC);

-- ============================================================
-- FUNCTION: compute_behavioral_fingerprint
-- Called weekly (Sunday night) to build the snapshot
-- ============================================================
CREATE OR REPLACE FUNCTION compute_behavioral_snapshot(p_user_id UUID, p_week_start DATE)
RETURNS void AS $$
DECLARE
  v_week_end        DATE := p_week_start + INTERVAL '6 days';
  v_avg_words       INTEGER;
  v_avg_depth       NUMERIC;
  v_resistance      INTEGER;
  v_breakthrough    INTEGER;
  v_coach_count     INTEGER;
  v_morning_score   NUMERIC;
BEGIN
  -- Average reflection words
  SELECT AVG(word_count)
  INTO v_avg_words
  FROM reflections
  WHERE user_id = p_user_id
    AND reflection_date BETWEEN p_week_start AND v_week_end;

  -- Average depth score
  SELECT AVG(depth_score)
  INTO v_avg_depth
  FROM reflections
  WHERE user_id = p_user_id
    AND reflection_date BETWEEN p_week_start AND v_week_end;

  -- Count resistance and breakthrough episodes
  SELECT
    COUNT(*) FILTER (WHERE resistance_detected = TRUE),
    COUNT(*) FILTER (WHERE breakthrough_detected = TRUE)
  INTO v_resistance, v_breakthrough
  FROM reflections
  WHERE user_id = p_user_id
    AND reflection_date BETWEEN p_week_start AND v_week_end;

  -- Coach engagement count
  SELECT COUNT(*)
  INTO v_coach_count
  FROM ai_coach_messages
  WHERE user_id = p_user_id
    AND role = 'user'
    AND created_at::DATE BETWEEN p_week_start AND v_week_end;

  -- Morning person score (tasks completed before noon vs total)
  SELECT
    COALESCE(COUNT(*) FILTER (
      WHERE EXTRACT(HOUR FROM completed_at) < 12
    )::NUMERIC / NULLIF(COUNT(*) FILTER (WHERE status = 'completed'), 0), 0.5)
  INTO v_morning_score
  FROM daily_tasks
  WHERE user_id = p_user_id
    AND scheduled_date BETWEEN p_week_start AND v_week_end;

  -- Insert or update snapshot
  INSERT INTO behavioral_snapshots (
    user_id, week_start_date,
    avg_reflection_words, avg_depth_score,
    resistance_episodes, breakthrough_episodes,
    coach_engagement_count, morning_person_score
  ) VALUES (
    p_user_id, p_week_start,
    v_avg_words, v_avg_depth,
    v_resistance, v_breakthrough,
    v_coach_count, v_morning_score
  )
  ON CONFLICT (user_id, week_start_date)
  DO UPDATE SET
    avg_reflection_words    = EXCLUDED.avg_reflection_words,
    avg_depth_score         = EXCLUDED.avg_depth_score,
    resistance_episodes     = EXCLUDED.resistance_episodes,
    breakthrough_episodes   = EXCLUDED.breakthrough_episodes,
    coach_engagement_count  = EXCLUDED.coach_engagement_count,
    morning_person_score    = EXCLUDED.morning_person_score;

END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- FUNCTION: get_retention_context
-- Returns everything needed for AI to understand engagement state
-- Used by task generator and coach context builder
-- ============================================================
CREATE OR REPLACE FUNCTION get_user_retention_context(p_user_id UUID)
RETURNS JSONB AS $$
DECLARE
  v_profile     RECORD;
  v_recent_days INTEGER;
  v_last_seen   DATE;
  v_result      JSONB;
BEGIN
  -- Get identity profile state
  SELECT
    current_streak,
    longest_streak,
    momentum_state,
    transformation_score,
    consistency_score
  INTO v_profile
  FROM identity_profiles
  WHERE user_id = p_user_id;

  -- Days since last task completion
  SELECT COALESCE(CURRENT_DATE - MAX(metric_date), 999)
  INTO v_recent_days
  FROM progress_metrics
  WHERE user_id = p_user_id AND task_completed = TRUE;

  -- Days since last app engagement
  SELECT COALESCE(CURRENT_DATE - MAX(event_date), 999)
  INTO v_last_seen
  FROM engagement_events
  WHERE user_id = p_user_id;

  v_result := jsonb_build_object(
    'current_streak',         v_profile.current_streak,
    'longest_streak',         v_profile.longest_streak,
    'momentum_state',         v_profile.momentum_state,
    'transformation_score',   v_profile.transformation_score,
    'days_since_last_task',   v_recent_days,
    'days_since_last_seen',   CURRENT_DATE - v_last_seen,
    'needs_intervention',     (v_recent_days >= 2 OR v_profile.momentum_state = 'critical'),
    'approaching_milestone',  (
      SELECT COUNT(*) > 0
      FROM milestones m
      JOIN objectives o ON o.id = m.objective_id
      WHERE o.user_id = p_user_id
        AND m.status = 'in_progress'
        AND m.target_date <= CURRENT_DATE + 3
    )
  );

  RETURN v_result;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- FUNCTION: get_full_user_context_for_ai
-- The primary function used by all AI engines
-- Returns a complete, structured snapshot of the user
-- for inclusion in AI prompts
-- ============================================================
CREATE OR REPLACE FUNCTION get_user_ai_context(p_user_id UUID)
RETURNS JSONB AS $$
DECLARE
  v_result JSONB;
BEGIN
  SELECT jsonb_build_object(
    -- User basics
    'user_id',            u.id,
    'display_name',       u.display_name,
    'timezone',           u.timezone,
    'days_active',        (CURRENT_DATE - u.created_at::DATE),
    'onboarding_status',  u.onboarding_status,

    -- Identity profile
    'identity', jsonb_build_object(
      'life_direction',       ip.life_direction,
      'personal_vision',      ip.personal_vision,
      'core_values',          ip.core_values,
      'consistency_pattern',  ip.consistency_pattern,
      'motivation_style',     ip.motivation_style,
      'execution_style',      ip.execution_style,
      'resistance_triggers',  ip.resistance_triggers,
      'peak_performance_time',ip.peak_performance_time
    ),

    -- Scores
    'scores', jsonb_build_object(
      'transformation',   ip.transformation_score,
      'consistency',      ip.consistency_score,
      'depth',            ip.depth_score,
      'momentum',         ip.momentum_score,
      'alignment',        ip.alignment_score,
      'momentum_state',   ip.momentum_state,
      'streak',           ip.current_streak
    ),

    -- Active goal
    'goal', (
      SELECT jsonb_build_object(
        'id',               g.id,
        'statement',        g.refined_statement,
        'why',              g.why_statement,
        'required_identity',g.required_identity,
        'progress_pct',     g.progress_percentage,
        'started_at',       g.started_at,
        'weeks_active',     (CURRENT_DATE - g.started_at::DATE) / 7
      )
      FROM goals g
      WHERE g.user_id = p_user_id AND g.status = 'active'
      LIMIT 1
    ),

    -- Active traits (lowest scoring first — most growth needed)
    'traits', (
      SELECT jsonb_agg(jsonb_build_object(
        'name',          it.name,
        'current_score', it.current_score,
        'target_score',  it.target_score,
        'velocity',      it.velocity,
        'gap',           it.target_score - it.current_score
      ) ORDER BY it.current_score ASC)
      FROM identity_traits it
      WHERE it.user_id = p_user_id AND it.is_active = TRUE
    ),

    -- Last 3 reflections (for AI to sense recent state)
    'recent_reflections', (
      SELECT jsonb_agg(jsonb_build_object(
        'date',        r.reflection_date,
        'sentiment',   r.sentiment,
        'depth_score', r.depth_score,
        'key_themes',  r.key_themes,
        'resistance',  r.resistance_detected,
        'breakthrough',r.breakthrough_detected
      ) ORDER BY r.reflection_date DESC)
      FROM reflections r
      WHERE r.user_id = p_user_id
      LIMIT 3
    ),

    -- Detected behavioral patterns
    'patterns', (
      SELECT jsonb_agg(jsonb_build_object(
        'type',        bp.pattern_type,
        'name',        bp.pattern_name,
        'confidence',  bp.confidence
      ))
      FROM behavioral_patterns bp
      WHERE bp.user_id = p_user_id AND bp.is_active = TRUE
    ),

    -- Retention context
    'retention', get_user_retention_context(p_user_id)

  ) INTO v_result
  FROM users u
  JOIN identity_profiles ip ON ip.user_id = u.id
  WHERE u.id = p_user_id;

  RETURN v_result;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- VIEW: resistance_patterns
-- Shows users who need coach intervention
-- Used by scheduled jobs to trigger proactive check-ins
-- ============================================================
CREATE VIEW users_needing_intervention AS
SELECT
  u.id AS user_id,
  u.display_name,
  u.email,
  ip.momentum_state,
  ip.current_streak,
  ip.transformation_score,
  (CURRENT_DATE - MAX(pm.metric_date)) AS days_since_last_task
FROM users u
JOIN identity_profiles ip ON ip.user_id = u.id
LEFT JOIN progress_metrics pm ON pm.user_id = u.id AND pm.task_completed = TRUE
WHERE u.is_active = TRUE
  AND u.onboarding_status = 'active'
GROUP BY u.id, u.display_name, u.email, ip.momentum_state, ip.current_streak, ip.transformation_score
HAVING
  (CURRENT_DATE - MAX(pm.metric_date)) >= 2      -- missed 2+ days
  OR ip.momentum_state IN ('declining', 'critical');
