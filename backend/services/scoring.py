"""
services/scoring.py

Centralized scoring service for real-time and batch score updates.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from core.logging import get_logger

logger = get_logger(__name__)


async def trigger_score_update(db: AsyncSession, user_id: str) -> dict:
    """
    Trigger immediate score recalculation for a user.
    Returns the updated scores.
    """
    try:
        # Call the database function
        await db.execute(
            text("SELECT update_user_scores(:user_id)"),
            {"user_id": user_id},
        )

        # Fetch the results
        result = await db.execute(
            text("""
                SELECT
                    transformation_score,
                    consistency_score,
                    depth_score,
                    momentum_score,
                    alignment_score,
                    momentum_state
                FROM identity_profiles
                WHERE user_id = :user_id
            """),
            {"user_id": user_id},
        )

        scores = result.mappings().one_or_none()

        if scores:
            logger.info(
                "scores_updated",
                user_id=user_id,
                transformation=scores["transformation_score"],
            )
            return dict(scores)
        else:
            logger.warning("no_profile_found_for_scores", user_id=user_id)
            return {}

    except Exception as e:
        logger.error("score_update_failed", user_id=user_id, error=str(e))
        raise


async def batch_update_all_scores(db: AsyncSession) -> int:
    """
    Batch update scores for all active users.
    Called by nightly scheduler job.
    """
    try:
        result = await db.execute(
            text("""
                SELECT id FROM users
                WHERE is_active = TRUE
                AND onboarding_status = 'active'
            """)
        )

        user_ids = result.scalars().all()
        updated_count = 0

        for user_id in user_ids:
            try:
                await trigger_score_update(db, str(user_id))
                updated_count += 1
            except Exception as e:
                logger.error(
                    "batch_score_update_failed",
                    user_id=user_id,
                    error=str(e),
                )
                continue

        await db.commit()
        logger.info(
            "batch_scores_complete",
            updated=updated_count,
            total=len(user_ids),
        )
        return updated_count

    except Exception as e:
        await db.rollback()
        logger.error("batch_score_update_failed", error=str(e))
        raise