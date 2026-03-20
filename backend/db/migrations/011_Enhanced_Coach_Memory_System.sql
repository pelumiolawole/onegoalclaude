-- Migration 011: Enhanced Coach Memory System (CORRECTED - FINAL)
-- Date: 2026-03-20
-- Changes from original:
--   - Added message_count and updated_at to coach_sessions
--   - Added idx_coach_sessions_active index
--   - Added idx_coach_moments_session_id index
--   - Updated coach_safety_flags to match actual schema (source_type, source_id, excerpt, ai_response)
--   - Updated coach_interventions to include reason, metadata columns from partial migration

-- 1. Session tracking for intentional openings/closings
CREATE TABLE IF NOT EXISTS coach_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_start TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    session_end TIMESTAMP WITH TIME ZONE,
    opening_context TEXT,
    closing_insight TEXT,
    session_goal TEXT,
    emotional_arc TEXT,
    coach_mode_used TEXT,
    next_session_hook TEXT,
    message_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_coach_sessions_user_id ON coach_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_coach_sessions_start ON coach_sessions(session_start);
CREATE INDEX IF NOT EXISTS idx_coach_sessions_active ON coach_sessions(user_id, session_end) 
WHERE session_end IS NULL;

-- 2. Key moments database (breakthroughs, resistance, commitments)
CREATE TABLE IF NOT EXISTS coach_moments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id UUID REFERENCES coach_sessions(id) ON DELETE CASCADE,
    moment_type TEXT NOT NULL CHECK (moment_type IN ('breakthrough', 'resistance', 'commitment', 'vulnerability', 'pattern_repeat', 'insight')),
    moment_content TEXT NOT NULL,
    coach_observation TEXT,
    user_language TEXT,
    emotional_tone TEXT,
    trait_referenced TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_coach_moments_user_id ON coach_moments(user_id);
CREATE INDEX IF NOT EXISTS idx_coach_moments_session_id ON coach_moments(session_id);
CREATE INDEX IF NOT EXISTS idx_coach_moments_type ON coach_moments(moment_type);
CREATE INDEX IF NOT EXISTS idx_coach_moments_trait ON coach_moments(trait_referenced);

-- 3. Conversation continuity (for between-session touchpoints)
CREATE TABLE IF NOT EXISTS coach_touchpoints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    coach_acknowledgment TEXT,
    session_id UUID REFERENCES coach_sessions(id),
    is_processed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_coach_touchpoints_user_id ON coach_touchpoints(user_id);
CREATE INDEX IF NOT EXISTS idx_coach_touchpoints_unprocessed ON coach_touchpoints(user_id, is_processed) WHERE is_processed = FALSE;

-- 4. Pattern recognition tracking
CREATE TABLE IF NOT EXISTS coach_patterns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    pattern_name TEXT NOT NULL,
    pattern_type TEXT NOT NULL CHECK (pattern_type IN ('resistance', 'strength', 'growth_edge', 'avoidance', 'breakthrough_indicator')),
    description TEXT NOT NULL,
    evidence_count INTEGER DEFAULT 1,
    first_observed TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_observed TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    confidence_score NUMERIC(3,2) CHECK (confidence_score >= 0 AND confidence_score <= 1),
    is_active BOOLEAN DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_coach_patterns_user_id ON coach_patterns(user_id);
CREATE INDEX IF NOT EXISTS idx_coach_patterns_active ON coach_patterns(user_id, is_active) WHERE is_active = TRUE;

-- 5. Crisis/safety tracking (UPDATED to match actual deployed schema)
CREATE TABLE IF NOT EXISTS coach_safety_flags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id UUID REFERENCES coach_sessions(id),
    severity TEXT NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'immediate')),
    source_type TEXT NOT NULL,
    source_id UUID,
    excerpt TEXT,
    ai_response TEXT,
    admin_notified BOOLEAN DEFAULT FALSE,
    admin_resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_coach_safety_user_id ON coach_safety_flags(user_id);
CREATE INDEX IF NOT EXISTS idx_coach_safety_unresolved ON coach_safety_flags(admin_notified, admin_resolved) WHERE admin_notified = TRUE AND admin_resolved = FALSE;

-- 6. Coach interventions (UPDATED to match actual deployed schema)
CREATE TABLE IF NOT EXISTS coach_interventions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    intervention_type VARCHAR(50) NOT NULL,
    message TEXT NOT NULL,
    urgency VARCHAR(20) DEFAULT 'medium',
    reason TEXT,
    metadata JSONB,
    resolved BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    resolved_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_coach_interventions_user_id ON coach_interventions(user_id);
CREATE INDEX IF NOT EXISTS idx_coach_interventions_unresolved ON coach_interventions(user_id, resolved) WHERE resolved = FALSE;