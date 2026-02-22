"""
ai/utils/cost_tracker.py

AI cost tracking and reporting utilities.

Used by:
  - Background jobs to estimate daily spend
  - Admin API (future) to monitor per-user costs
  - Cost alerts when daily spend exceeds threshold
"""

from datetime import date, timedelta

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


async def get_daily_cost_summary(db: AsyncSession, for_date: date | None = None) -> dict:
    """Get total AI costs for a specific day, broken down by engine."""
    target_date = for_date or date.today()

    result = await db.execute(
        text("""
            SELECT
                engine,
                COUNT(*) as call_count,
                SUM(prompt_tokens) as total_prompt_tokens,
                SUM(completion_tokens) as total_completion_tokens,
                SUM(estimated_cost_usd) as total_cost_usd,
                AVG(latency_ms) as avg_latency_ms
            FROM ai_interactions
            WHERE created_at::date = :date
              AND success = TRUE
            GROUP BY engine
            ORDER BY total_cost_usd DESC
        """),
        {"date": target_date},
    )

    rows = result.fetchall()
    engines = [
        {
            "engine": row.engine,
            "calls": row.call_count,
            "prompt_tokens": row.total_prompt_tokens or 0,
            "completion_tokens": row.total_completion_tokens or 0,
            "cost_usd": float(row.total_cost_usd) if row.total_cost_usd else 0.0,
            "avg_latency_ms": float(row.avg_latency_ms) if row.avg_latency_ms else 0.0,
        }
        for row in rows
    ]

    total_cost = sum(e["cost_usd"] for e in engines)
    total_calls = sum(e["calls"] for e in engines)

    return {
        "date": str(target_date),
        "total_cost_usd": round(total_cost, 4),
        "total_calls": total_calls,
        "by_engine": engines,
    }


async def get_user_cost_summary(user_id: str, db: AsyncSession, days: int = 30) -> dict:
    """Get AI cost breakdown for a specific user over the past N days."""
    result = await db.execute(
        text("""
            SELECT
                engine,
                COUNT(*) as calls,
                SUM(estimated_cost_usd) as cost_usd
            FROM ai_interactions
            WHERE user_id = :user_id
              AND created_at >= NOW() - INTERVAL ':days days'
              AND success = TRUE
            GROUP BY engine
        """),
        {"user_id": user_id, "days": days},
    )

    rows = result.fetchall()
    total = sum(float(row.cost_usd or 0) for row in rows)

    return {
        "user_id": user_id,
        "period_days": days,
        "total_cost_usd": round(total, 4),
        "by_engine": [
            {"engine": row.engine, "calls": row.calls, "cost_usd": float(row.cost_usd or 0)}
            for row in rows
        ],
    }
