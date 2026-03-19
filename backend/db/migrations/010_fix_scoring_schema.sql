-- Migration 009: Fix Scoring Schema - Emergency Repair
-- Fixes missing columns and tables causing score calculation failures

-- 1. Add missing columns to progress_metrics
ALTER TABLE progress_metrics 
ADD COLUMN IF NOT EXISTS avg_depth_score INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS transformation_score INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS momentum_score INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS alignment_score INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS consistency_score INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();

-- 2. Create missing coach_interventions table
CREATE TABLE IF NOT EXISTS coach_interventions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    intervention_type VARCHAR(50) NOT NULL,
    reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    resolved_at TIMESTAMP WITH TIME ZONE,
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_coach_interventions_user_id ON coach_interventions(user_id);
CREATE INDEX IF NOT EXISTS idx_coach_interventions_type ON coach_interventions(intervention_type);
CREATE INDEX IF NOT EXISTS idx_coach_interventions_created ON coach_interventions(created_at);

-- 3. Fix the update_user_scores function to handle NULLs gracefully
CREATE OR REPLACE FUNCTION update_user_scores(p_user_id UUID)
RETURNS VOID AS $$
DECLARE
    v_consistency INTEGER;
    v_depth INTEGER;
    v_momentum INTEGER;
    v_alignment INTEGER;
    v_transformation INTEGER;
BEGIN
    -- Calculate consistency (last 14 days)
    SELECT COALESCE(
        ROUND(
            (COUNT(*) FILTER (WHERE task_completed)::NUMERIC / 
            NULLIF(COUNT(*), 0) * 100
        ), 0)::INTEGER
    INTO v_consistency
    FROM progress_metrics
    WHERE user_id = p_user_id
    AND metric_date >= CURRENT_DATE - INTERVAL '14 days';

    -- Calculate depth (average reflection depth)
    SELECT COALESCE(ROUND(AVG(avg_depth_score)), 0)::INTEGER
    INTO v_depth
    FROM progress_metrics
    WHERE user_id = p_user_id
    AND metric_date >= CURRENT_DATE - INTERVAL '14 days'
    AND avg_depth_score IS NOT NULL;

    -- Calculate momentum (last 7 vs prior 7 days)
    WITH recent AS (
        SELECT COUNT(*) FILTER (WHERE task_completed) as completed
        FROM progress_metrics
        WHERE user_id = p_user_id
        AND metric_date >= CURRENT_DATE - INTERVAL '7 days'
    ),
    prior AS (
        SELECT COUNT(*) FILTER (WHERE task_completed) as completed
        FROM progress_metrics
        WHERE user_id = p_user_id
        AND metric_date >= CURRENT_DATE - INTERVAL '14 days'
        AND metric_date < CURRENT_DATE - INTERVAL '7 days'
    )
    SELECT COALESCE(
        ROUND(
            (r.completed::NUMERIC / NULLIF(p.completed, 0) * 50) + 50
        ), 50)::INTEGER
    INTO v_momentum
    FROM recent r, prior p;

    -- Calculate alignment from identity_traits
    SELECT COALESCE(ROUND(AVG(current_score) * 10), 0)::INTEGER
    INTO v_alignment
    FROM identity_traits
    WHERE user_id = p_user_id;

    -- Calculate transformation score
    v_transformation := ROUND(
        v_consistency * 0.35 + 
        v_depth * 0.25 + 
        v_momentum * 0.25 + 
        v_alignment * 0.15
    )::INTEGER;

    -- Update today's progress_metrics
    INSERT INTO progress_metrics (
        user_id, metric_date, task_completed, reflection_submitted,
        avg_depth_score, transformation_score, momentum_score, 
        alignment_score, consistency_score, updated_at
    )
    VALUES (
        p_user_id, CURRENT_DATE, FALSE, FALSE,
        v_depth, v_transformation, v_momentum,
        v_alignment, v_consistency, NOW()
    )
    ON CONFLICT (user_id, metric_date) 
    DO UPDATE SET
        avg_depth_score = EXCLUDED.avg_depth_score,
        transformation_score = EXCLUDED.transformation_score,
        momentum_score = EXCLUDED.momentum_score,
        alignment_score = EXCLUDED.alignment_score,
        consistency_score = EXCLUDED.consistency_score,
        updated_at = NOW();

    -- Update identity_profiles with latest scores
    UPDATE identity_profiles
    SET 
        consistency_score = v_consistency,
        depth_score = v_depth,
        momentum_score = v_momentum,
        alignment_score = v_alignment,
        transformation_score = v_transformation,
        momentum_state = CASE
            WHEN v_transformation >= 65 THEN 'rising'
            WHEN v_transformation >= 40 THEN 'holding'
            WHEN v_transformation >= 20 THEN 'declining'
            ELSE 'critical'
        END,
        updated_at = NOW()
    WHERE user_id = p_user_id;
    
END;
$$ LANGUAGE plpgsql;