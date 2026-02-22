-- ============================================================
-- ONE GOAL — Scoring System Functions
-- Migration: 002_scoring_system
-- ============================================================

-- ============================================================
-- FUNCTION: compute_consistency_score
-- 35% of transformation score
-- Based on task completion over last 14 days
-- Decays 5 pts per missed day after day 3, recovers 3 pts per completed day
-- ============================================================
CREATE OR REPLACE FUNCTION compute_consistency_score(p_user_id UUID)
RETURNS NUMERIC AS $$
DECLARE
  v_completed    INTEGER := 0;
  v_total        INTEGER := 14;
  v_base_score   NUMERIC;
  v_streak       INTEGER;
  v_streak_bonus NUMERIC := 0;
BEGIN
  -- Count completed tasks in last 14 days
  SELECT COUNT(*)
  INTO v_completed
  FROM progress_metrics
  WHERE user_id = p_user_id
    AND metric_date >= CURRENT_DATE - INTERVAL '13 days'
    AND task_completed = TRUE;

  -- Base score: completion rate
  v_base_score := (v_completed::NUMERIC / v_total) * 100;

  -- Streak bonus: current streak adds up to 10 bonus points
  SELECT current_streak INTO v_streak
  FROM identity_profiles
  WHERE user_id = p_user_id;

  v_streak_bonus := LEAST(v_streak * 0.5, 10);

  RETURN LEAST(ROUND(v_base_score + v_streak_bonus, 2), 100);
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- FUNCTION: compute_depth_score
-- 25% of transformation score
-- Average reflection quality over last 14 days
-- ============================================================
CREATE OR REPLACE FUNCTION compute_depth_score(p_user_id UUID)
RETURNS NUMERIC AS $$
DECLARE
  v_avg_depth NUMERIC;
BEGIN
  SELECT AVG(depth_score)
  INTO v_avg_depth
  FROM reflections
  WHERE user_id = p_user_id
    AND reflection_date >= CURRENT_DATE - INTERVAL '13 days'
    AND depth_score IS NOT NULL;

  -- Convert 1-10 scale to 0-100
  RETURN COALESCE(ROUND(v_avg_depth * 10, 2), 0);
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- FUNCTION: compute_momentum_score
-- 25% of transformation score
-- Trajectory: last 7 days vs prior 7 days
-- ============================================================
CREATE OR REPLACE FUNCTION compute_momentum_score(p_user_id UUID)
RETURNS NUMERIC AS $$
DECLARE
  v_recent_avg  NUMERIC;
  v_prior_avg   NUMERIC;
  v_base_score  NUMERIC := 50; -- neutral baseline
  v_delta       NUMERIC;
BEGIN
  -- Recent 7 days performance
  SELECT AVG(CASE WHEN task_completed THEN 100 ELSE 0 END +
             COALESCE(avg_depth_score * 10, 0)) / 2
  INTO v_recent_avg
  FROM progress_metrics
  WHERE user_id = p_user_id
    AND metric_date >= CURRENT_DATE - INTERVAL '6 days';

  -- Prior 7 days performance
  SELECT AVG(CASE WHEN task_completed THEN 100 ELSE 0 END +
             COALESCE(avg_depth_score * 10, 0)) / 2
  INTO v_prior_avg
  FROM progress_metrics
  WHERE user_id = p_user_id
    AND metric_date >= CURRENT_DATE - INTERVAL '13 days'
    AND metric_date < CURRENT_DATE - INTERVAL '6 days';

  v_recent_avg := COALESCE(v_recent_avg, 0);
  v_prior_avg  := COALESCE(v_prior_avg, 50); -- neutral if no prior data

  -- Delta: improvement or decline
  v_delta := v_recent_avg - v_prior_avg;

  -- Map delta to 0-100 momentum score
  -- +30 delta = near 100, -30 delta = near 0
  RETURN LEAST(GREATEST(ROUND(v_base_score + (v_delta * 1.5), 2), 0), 100);
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- FUNCTION: compute_alignment_score
-- 15% of transformation score
-- Average of all active identity trait scores (normalized to 100)
-- ============================================================
CREATE OR REPLACE FUNCTION compute_alignment_score(p_user_id UUID)
RETURNS NUMERIC AS $$
DECLARE
  v_avg_trait NUMERIC;
BEGIN
  SELECT AVG(current_score)
  INTO v_avg_trait
  FROM identity_traits
  WHERE user_id = p_user_id
    AND is_active = TRUE;

  -- Convert 1-10 trait scale to 0-100
  RETURN COALESCE(ROUND(v_avg_trait * 10, 2), 0);
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- FUNCTION: compute_transformation_score
-- Composite score with defined weights
-- ============================================================
CREATE OR REPLACE FUNCTION compute_transformation_score(p_user_id UUID)
RETURNS NUMERIC AS $$
DECLARE
  v_consistency NUMERIC;
  v_depth       NUMERIC;
  v_momentum    NUMERIC;
  v_alignment   NUMERIC;
  v_weights     JSONB;
  v_composite   NUMERIC;
BEGIN
  -- Get scoring weights from config (allows runtime adjustment)
  SELECT value INTO v_weights
  FROM system_config WHERE key = 'scoring_weights';

  -- Compute individual scores
  v_consistency := compute_consistency_score(p_user_id);
  v_depth       := compute_depth_score(p_user_id);
  v_momentum    := compute_momentum_score(p_user_id);
  v_alignment   := compute_alignment_score(p_user_id);

  -- Weighted composite
  v_composite := (
    v_consistency * (v_weights->>'consistency')::NUMERIC +
    v_depth       * (v_weights->>'depth')::NUMERIC +
    v_momentum    * (v_weights->>'momentum')::NUMERIC +
    v_alignment   * (v_weights->>'alignment')::NUMERIC
  );

  RETURN ROUND(v_composite, 2);
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- FUNCTION: update_user_scores
-- Called end of each day by the task generator job
-- Updates all scores and momentum state in identity_profiles
-- ============================================================
CREATE OR REPLACE FUNCTION update_user_scores(p_user_id UUID)
RETURNS void AS $$
DECLARE
  v_consistency     NUMERIC;
  v_depth           NUMERIC;
  v_momentum        NUMERIC;
  v_alignment       NUMERIC;
  v_composite       NUMERIC;
  v_momentum_state  momentum_state;
  v_current_streak  INTEGER;
  v_longest_streak  INTEGER;
  v_task_today      BOOLEAN;
BEGIN
  -- Compute all scores
  v_consistency := compute_consistency_score(p_user_id);
  v_depth       := compute_depth_score(p_user_id);
  v_momentum    := compute_momentum_score(p_user_id);
  v_alignment   := compute_alignment_score(p_user_id);
  v_composite   := compute_transformation_score(p_user_id);

  -- Determine momentum state from momentum score
  v_momentum_state := CASE
    WHEN v_momentum >= 65 THEN 'rising'::momentum_state
    WHEN v_momentum >= 40 THEN 'holding'::momentum_state
    WHEN v_momentum >= 20 THEN 'declining'::momentum_state
    ELSE 'critical'::momentum_state
  END;

  -- Check if task was completed today
  SELECT task_completed INTO v_task_today
  FROM progress_metrics
  WHERE user_id = p_user_id AND metric_date = CURRENT_DATE;

  -- Update streak
  SELECT current_streak, longest_streak
  INTO v_current_streak, v_longest_streak
  FROM identity_profiles WHERE user_id = p_user_id;

  IF COALESCE(v_task_today, FALSE) THEN
    v_current_streak := v_current_streak + 1;
    v_longest_streak := GREATEST(v_current_streak, v_longest_streak);
  ELSE
    v_current_streak := 0; -- streak broken
  END IF;

  -- Write updated scores to identity profile
  UPDATE identity_profiles SET
    transformation_score = v_composite,
    consistency_score    = v_consistency,
    depth_score          = v_depth,
    momentum_score       = v_momentum,
    alignment_score      = v_alignment,
    momentum_state       = v_momentum_state,
    current_streak       = v_current_streak,
    longest_streak       = v_longest_streak,
    last_ai_update       = NOW()
  WHERE user_id = p_user_id;

END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- FUNCTION: update_streak
-- Called whenever a daily task status changes
-- ============================================================
CREATE OR REPLACE FUNCTION update_streak_on_task_complete()
RETURNS TRIGGER AS $$
BEGIN
  -- Only react to task completions (not skips or deferrals)
  IF NEW.status = 'completed' AND OLD.status != 'completed' THEN
    -- Mark today's progress metrics
    INSERT INTO progress_metrics (user_id, metric_date, task_completed)
    VALUES (NEW.user_id, NEW.scheduled_date, TRUE)
    ON CONFLICT (user_id, metric_date)
    DO UPDATE SET task_completed = TRUE;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER task_completion_streak_update
  AFTER UPDATE ON daily_tasks
  FOR EACH ROW
  EXECUTE FUNCTION update_streak_on_task_complete();

-- ============================================================
-- FUNCTION: detect_momentum_state_change
-- Fires notification when user drops to 'critical' momentum
-- ============================================================
CREATE OR REPLACE FUNCTION check_momentum_and_queue_intervention(p_user_id UUID)
RETURNS void AS $$
DECLARE
  v_state momentum_state;
BEGIN
  SELECT momentum_state INTO v_state
  FROM identity_profiles WHERE user_id = p_user_id;

  IF v_state = 'critical' THEN
    -- Queue an intervention check-in from the coach
    INSERT INTO notification_queue (user_id, type, title, body, channel, scheduled_at)
    VALUES (
      p_user_id,
      'coach_checkin',
      'Your momentum needs attention',
      'Your coach has something important for you today.',
      'push',
      NOW() + INTERVAL '1 hour'  -- give them an hour before the nudge
    )
    ON CONFLICT DO NOTHING; -- don't double-queue
  END IF;
END;
$$ LANGUAGE plpgsql;
