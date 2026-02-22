-- ============================================================
-- ONE GOAL — Privacy, Safety & Row Level Security
-- Migration: 004_privacy_and_security
-- ============================================================

-- ============================================================
-- ROW LEVEL SECURITY (RLS)
-- Every table with user data is protected.
-- Users can only read/write their own rows.
-- ============================================================

-- Enable RLS on all user-data tables
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_traits ENABLE ROW LEVEL SECURITY;
ALTER TABLE goals ENABLE ROW LEVEL SECURITY;
ALTER TABLE objectives ENABLE ROW LEVEL SECURITY;
ALTER TABLE milestones ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE reflections ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_coach_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_coach_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE progress_metrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE behavioral_patterns ENABLE ROW LEVEL SECURITY;
ALTER TABLE behavioral_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE engagement_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE weekly_reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE notification_queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE integration_configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE onboarding_interview_state ENABLE ROW LEVEL SECURITY;

-- ============================================================
-- RLS POLICIES
-- Pattern: users can only access their own data.
-- Service role (backend) bypasses RLS for AI operations.
-- ============================================================

-- Users can only see and update their own record
CREATE POLICY users_self_access ON users
  USING (auth.uid() = id)
  WITH CHECK (auth.uid() = id);

-- Identity profile — only the owner
CREATE POLICY identity_profile_owner ON identity_profiles
  USING (auth.uid() = user_id);

CREATE POLICY identity_traits_owner ON identity_traits
  USING (auth.uid() = user_id);

CREATE POLICY goals_owner ON goals
  USING (auth.uid() = user_id);

CREATE POLICY objectives_owner ON objectives
  USING (auth.uid() = user_id);

CREATE POLICY milestones_owner ON milestones
  USING (auth.uid() = user_id);

CREATE POLICY daily_tasks_owner ON daily_tasks
  USING (auth.uid() = user_id);

CREATE POLICY reflections_owner ON reflections
  USING (auth.uid() = user_id);

CREATE POLICY coach_sessions_owner ON ai_coach_sessions
  USING (auth.uid() = user_id);

CREATE POLICY coach_messages_owner ON ai_coach_messages
  USING (auth.uid() = user_id);

CREATE POLICY progress_metrics_owner ON progress_metrics
  USING (auth.uid() = user_id);

CREATE POLICY behavioral_patterns_owner ON behavioral_patterns
  USING (auth.uid() = user_id);

CREATE POLICY behavioral_snapshots_owner ON behavioral_snapshots
  USING (auth.uid() = user_id);

CREATE POLICY engagement_events_owner ON engagement_events
  USING (auth.uid() = user_id);

CREATE POLICY weekly_reviews_owner ON weekly_reviews
  USING (auth.uid() = user_id);

CREATE POLICY notifications_owner ON notification_queue
  USING (auth.uid() = user_id);

CREATE POLICY integrations_owner ON integration_configs
  USING (auth.uid() = user_id);

CREATE POLICY onboarding_state_owner ON onboarding_interview_state
  USING (auth.uid() = user_id);

-- ============================================================
-- GDPR / DATA PORTABILITY
-- Function to export all user data as JSON
-- Called by "Download My Data" feature
-- ============================================================
CREATE OR REPLACE FUNCTION export_user_data(p_user_id UUID)
RETURNS JSONB AS $$
DECLARE
  v_result JSONB;
BEGIN
  SELECT jsonb_build_object(
    'export_date',      NOW(),
    'user',             row_to_json(u.*),
    'identity_profile', row_to_json(ip.*),
    'identity_traits', (
      SELECT jsonb_agg(row_to_json(it.*))
      FROM identity_traits it WHERE it.user_id = p_user_id
    ),
    'goals', (
      SELECT jsonb_agg(row_to_json(g.*))
      FROM goals g WHERE g.user_id = p_user_id
    ),
    'objectives', (
      SELECT jsonb_agg(row_to_json(o.*))
      FROM objectives o WHERE o.user_id = p_user_id
    ),
    'daily_tasks', (
      SELECT jsonb_agg(row_to_json(dt.*))
      FROM daily_tasks dt WHERE dt.user_id = p_user_id
    ),
    'reflections', (
      SELECT jsonb_agg(row_to_json(r.*))
      FROM reflections r WHERE r.user_id = p_user_id
    ),
    'coach_conversations', (
      SELECT jsonb_agg(jsonb_build_object(
        'session',  row_to_json(s.*),
        'messages', (
          SELECT jsonb_agg(row_to_json(m.*) ORDER BY m.created_at)
          FROM ai_coach_messages m WHERE m.session_id = s.id
        )
      ))
      FROM ai_coach_sessions s WHERE s.user_id = p_user_id
    ),
    'progress_history', (
      SELECT jsonb_agg(row_to_json(pm.*))
      FROM progress_metrics pm WHERE pm.user_id = p_user_id
    ),
    'weekly_reviews', (
      SELECT jsonb_agg(row_to_json(wr.*))
      FROM weekly_reviews wr WHERE wr.user_id = p_user_id
    )
  ) INTO v_result
  FROM users u
  JOIN identity_profiles ip ON ip.user_id = u.id
  WHERE u.id = p_user_id;

  RETURN v_result;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================================
-- FUNCTION: delete_user_data (GDPR right to erasure)
-- Cascading delete of all user data.
-- Embeddings, AI interaction logs, everything.
-- ============================================================
CREATE OR REPLACE FUNCTION delete_user_data(p_user_id UUID)
RETURNS void AS $$
BEGIN
  -- All child tables cascade automatically via FK ON DELETE CASCADE
  -- But we also clean up ai_interactions which uses SET NULL
  DELETE FROM ai_interactions WHERE user_id = p_user_id;

  -- Hard delete the user (triggers cascade to all owned data)
  DELETE FROM users WHERE id = p_user_id;

  -- Note: auth.users deletion must be handled by application layer
  -- via Supabase Auth API, not directly here
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================================
-- TABLE: ai_safety_flags
-- Tracks when the AI detected distress signals.
-- Used for safety auditing and coach mode switching.
-- Never shown to user in raw form.
-- ============================================================
CREATE TABLE ai_safety_flags (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  source_type     TEXT NOT NULL,   -- 'reflection', 'coach_message'
  source_id       UUID NOT NULL,   -- ID of the reflection or coach message
  flag_type       TEXT NOT NULL,   -- 'distress', 'crisis_language', 'self_harm_risk', 'out_of_scope_request'
  severity        INTEGER NOT NULL DEFAULT 1 CHECK (severity BETWEEN 1 AND 3),
  -- 1=mild (frustration), 2=moderate (hopelessness), 3=crisis (self-harm language)
  excerpt         TEXT,            -- sanitized excerpt that triggered the flag
  ai_response     TEXT,            -- what the AI said in response
  resources_shown BOOLEAN DEFAULT FALSE,
  reviewed        BOOLEAN DEFAULT FALSE,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- RLS: safety flags are only accessible by service role (not user-facing)
ALTER TABLE ai_safety_flags ENABLE ROW LEVEL SECURITY;
-- No user policy — only service role can access this table

CREATE INDEX idx_safety_flags_user ON ai_safety_flags(user_id, created_at DESC);
CREATE INDEX idx_safety_flags_severity ON ai_safety_flags(severity, reviewed, created_at DESC);

-- ============================================================
-- TABLE: data_processing_consent
-- Explicit consent records per processing type.
-- Required for GDPR compliance.
-- ============================================================
CREATE TABLE data_processing_consent (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  consent_type    TEXT NOT NULL,
  -- types: 'ai_coaching', 'behavioral_analysis', 'training_data', 'product_improvement'
  granted         BOOLEAN NOT NULL,
  granted_at      TIMESTAMPTZ,
  revoked_at      TIMESTAMPTZ,
  ip_address      INET,
  user_agent      TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  UNIQUE(user_id, consent_type)
);

ALTER TABLE data_processing_consent ENABLE ROW LEVEL SECURITY;
CREATE POLICY consent_owner ON data_processing_consent USING (auth.uid() = user_id);

-- Default consent entries created for each new user
CREATE OR REPLACE FUNCTION create_default_consent(p_user_id UUID)
RETURNS void AS $$
BEGIN
  INSERT INTO data_processing_consent (user_id, consent_type, granted, granted_at)
  VALUES
    (p_user_id, 'ai_coaching',         TRUE,  NOW()),
    (p_user_id, 'behavioral_analysis', TRUE,  NOW()),
    (p_user_id, 'training_data',       FALSE, NULL),  -- opt-in only, default OFF
    (p_user_id, 'product_improvement', TRUE,  NOW());
END;
$$ LANGUAGE plpgsql;

-- Trigger: create consent records for new users
CREATE OR REPLACE FUNCTION setup_new_user_consent()
RETURNS TRIGGER AS $$
BEGIN
  PERFORM create_default_consent(NEW.id);
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER auto_create_consent
  AFTER INSERT ON users
  FOR EACH ROW
  EXECUTE FUNCTION setup_new_user_consent();

-- ============================================================
-- FUNCTION: check_ai_usage_limits
-- Enforces daily AI usage limits for cost and safety
-- Returns TRUE if user can make another AI call
-- ============================================================
CREATE OR REPLACE FUNCTION check_ai_usage_limits(
  p_user_id UUID,
  p_engine  TEXT
)
RETURNS BOOLEAN AS $$
DECLARE
  v_limit       INTEGER;
  v_used        INTEGER;
  v_limit_config JSONB;
BEGIN
  -- Get limits from config
  SELECT value INTO v_limit_config
  FROM system_config WHERE key = 'coach_daily_message_limit';

  v_limit := CASE p_engine
    WHEN 'coach'     THEN (v_limit_config->>'coach')::INTEGER
    WHEN 'interview' THEN 50   -- generous during onboarding
    ELSE 10                    -- conservative for other engines
  END;

  -- Count today's usage
  SELECT COUNT(*)
  INTO v_used
  FROM ai_interactions
  WHERE user_id = p_user_id
    AND engine = p_engine
    AND success = TRUE
    AND created_at::DATE = CURRENT_DATE;

  RETURN v_used < v_limit;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- FUNCTION: sanitize_user_input
-- Called before any user text is included in an AI prompt.
-- Removes potential prompt injection patterns.
-- ============================================================
CREATE OR REPLACE FUNCTION sanitize_ai_input(p_input TEXT)
RETURNS TEXT AS $$
DECLARE
  v_cleaned TEXT := p_input;
  v_patterns TEXT[] := ARRAY[
    -- Prompt injection patterns
    'ignore (previous|all|the above|prior) instructions?',
    'you are now',
    'act as (if you are|a|an)',
    'pretend (you are|to be)',
    'disregard (your|all)',
    'forget (everything|all)',
    '\[INST\]',
    '<<SYS>>',
    '<\|im_start\|>',
    'system prompt',
    'jailbreak'
  ];
  v_pattern TEXT;
BEGIN
  FOREACH v_pattern IN ARRAY v_patterns LOOP
    -- Flag but don't silently remove — return sanitized flag for logging
    IF v_cleaned ~* v_pattern THEN
      -- Log the attempt
      INSERT INTO ai_safety_flags (
        user_id, source_type, source_id, flag_type, severity, excerpt
      ) VALUES (
        NULL, 'input_sanitization', uuid_generate_v4(),
        'prompt_injection_attempt', 2,
        LEFT(p_input, 200)
      );
      -- Return safe placeholder
      RETURN '[Message was flagged and could not be processed. Please rephrase.]';
    END IF;
  END LOOP;

  -- Truncate overly long inputs (prevent token stuffing)
  RETURN LEFT(v_cleaned, 4000);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
