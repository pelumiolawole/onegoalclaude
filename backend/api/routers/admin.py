"""
api/routers/admin.py

Admin endpoints for reviewing safety flags and system health.
Protected by admin authentication.
"""

from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies.auth import get_current_user, require_admin
from core.database import get_db
from db.models.user import User

logger = structlog.get_logger()

router = APIRouter(prefix="/admin", tags=["Admin"])


# ─── Schemas ──────────────────────────────────────────────────────────────────

class SafetyFlagResponse(BaseModel):
    id: str
    user_id: str
    source_type: str
    flag_type: str
    severity: int = Field(ge=1, le=10)
    excerpt: str
    ai_response: str
    resources_shown: bool
    reviewed: bool
    created_at: str
    
    class Config:
        from_attributes = True


class SafetyFlagReviewRequest(BaseModel):
    reviewed: bool = True
    notes: Optional[str] = None


class SafetyStatsResponse(BaseModel):
    total_flags: int
    unreviewed_flags: int
    crisis_flags: int
    distress_flags: int
    last_24h: int


# ─── Safety Flag Endpoints ────────────────────────────────────────────────────

@router.get(
    "/safety-flags",
    response_model=List[SafetyFlagResponse],
    summary="List safety flags with filtering",
)
async def list_safety_flags(
    reviewed: Optional[bool] = Query(None, description="Filter by review status"),
    flag_type: Optional[str] = Query(None, description="Filter by type (crisis, distress)"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> List[SafetyFlagResponse]:
    """
    List safety flags for admin review.
    
    Query parameters:
    - reviewed: true/false (default: all)
    - flag_type: crisis, distress (default: all)
    - limit: number of results (1-100, default 50)
    - offset: pagination offset
    """
    
    # Build query dynamically
    conditions = ["1=1"]
    params = {"limit": limit, "offset": offset}
    
    if reviewed is not None:
        conditions.append("reviewed = :reviewed")
        params["reviewed"] = reviewed
    
    if flag_type:
        conditions.append("flag_type = :flag_type")
        params["flag_type"] = flag_type
    
    where_clause = " AND ".join(conditions)
    
    result = await db.execute(
        text(f"""
            SELECT 
                id, user_id, source_type, flag_type, severity,
                excerpt, ai_response, resources_shown, reviewed, created_at
            FROM ai_safety_flags
            WHERE {where_clause}
            ORDER BY 
                CASE WHEN reviewed = FALSE THEN 0 ELSE 1 END,
                severity DESC,
                created_at DESC
            LIMIT :limit OFFSET :offset
        """),
        params,
    )
    
    flags = []
    for row in result.fetchall():
        flags.append(SafetyFlagResponse(
            id=str(row.id),
            user_id=str(row.user_id),
            source_type=row.source_type,
            flag_type=row.flag_type,
            severity=row.severity,
            excerpt=row.excerpt or "",
            ai_response=row.ai_response or "",
            resources_shown=row.resources_shown,
            reviewed=row.reviewed,
            created_at=str(row.created_at),
        ))
    
    logger.info(
        "safety_flags_listed",
        admin_id=str(current_user.id),
        count=len(flags),
        filters={"reviewed": reviewed, "flag_type": flag_type},
    )
    
    return flags


@router.get(
    "/safety-flags/stats",
    response_model=SafetyStatsResponse,
    summary="Get safety flag statistics",
)
async def get_safety_stats(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> SafetyStatsResponse:
    """Get summary statistics of safety flags."""
    
    result = await db.execute(
        text("""
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE reviewed = FALSE) as unreviewed,
                COUNT(*) FILTER (WHERE flag_type = 'crisis') as crisis,
                COUNT(*) FILTER (WHERE flag_type = 'distress') as distress,
                COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '24 hours') as last_24h
            FROM ai_safety_flags
        """)
    )
    
    row = result.fetchone()
    
    return SafetyStatsResponse(
        total_flags=row.total or 0,
        unreviewed_flags=row.unreviewed or 0,
        crisis_flags=row.crisis or 0,
        distress_flags=row.distress or 0,
        last_24h=row.last_24h or 0,
    )


@router.post(
    "/safety-flags/{flag_id}/review",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mark a safety flag as reviewed",
)
async def review_safety_flag(
    flag_id: str,
    request: SafetyFlagReviewRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Mark a safety flag as reviewed with optional notes."""
    
    # Check if flag exists
    result = await db.execute(
        text("SELECT id FROM ai_safety_flags WHERE id = :flag_id"),
        {"flag_id": flag_id},
    )
    
    if not result.fetchone():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Safety flag not found",
        )
    
    # Update the flag
    await db.execute(
        text("""
            UPDATE ai_safety_flags
            SET reviewed = :reviewed,
                reviewed_at = CASE WHEN :reviewed THEN NOW() ELSE NULL END,
                reviewed_by = CASE WHEN :reviewed THEN :admin_id ELSE NULL END,
                notes = COALESCE(:notes, notes)
            WHERE id = :flag_id
        """),
        {
            "flag_id": flag_id,
            "reviewed": request.reviewed,
            "admin_id": str(current_user.id),
            "notes": request.notes,
        },
    )
    
    logger.info(
        "safety_flag_reviewed",
        flag_id=flag_id,
        admin_id=str(current_user.id),
        reviewed=request.reviewed,
    )


@router.get(
    "/safety-flags/unreviewed-count",
    summary="Get count of unreviewed flags",
)
async def get_unreviewed_count(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Quick endpoint for dashboard badge."""
    
    result = await db.execute(
        text("""
            SELECT COUNT(*) as count
            FROM ai_safety_flags
            WHERE reviewed = FALSE
        """)
    )
    
    return {"unreviewed_count": result.scalar() or 0}