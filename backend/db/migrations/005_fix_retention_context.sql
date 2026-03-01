-- ============================================================
-- Migration 005: Fix get_user_retention_context type bug
--
-- Bug: v_last_seen was declared as DATE but assigned the result
-- of (CURRENT_DATE - MAX(event_date)) which is an INTEGER.
-- When the user has no engagement events, COALESCE returns 999,
-- and PostgreSQL raises:
--   "invalid input syntax for type date: 999"
--
-- Fix: declare v_last_seen as INTEGER and use it directly
-- instead of subtracting from CURRENT_DATE a second time.
-- ============================================================

CREATE OR REPLACE FUNCTION get_user_retention_context(p_user_id UUID)
RETURNS JSONB AS $$
DECLARE
  v_profile     RECORD;
  v_recent_days INTEGER;
  v_last_seen   INTEGER;
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
    'days_since_last_seen',   v_last_seen,
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
