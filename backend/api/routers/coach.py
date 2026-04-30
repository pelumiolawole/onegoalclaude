"""
api/routers/coach.py

AI Coach endpoints:
    GET  /coach/greeting              — Today's task greeting for coach opening message
    POST /coach/sessions              — Create a new session (V2: with opening context)
    GET  /coach/sessions              — List recent sessions
    GET  /coach/sessions/{id}         — Get session with messages
    POST /coach/sessions/{id}/message — Send message (streaming SSE, V2: moment tracking)
    GET  /coach/sessions/active       — Get or create active session (V2: continuity)
    DELETE /coach/sessions/{id}       — End a session (V2: with closing insight)

V2 Enhancements:
  - Sessions track opening context and closing insights
  - Messages trigger moment detection (breakthroughs, resistance, etc.)
  - Automatic session continuity between conversations
  - Crisis mode integration with safety flags
"""

import json
from collections.abc import AsyncGenerator
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai.engines.coach import CoachEngine
from api.dependencies.auth import get_onboarded_user, require_ai_quota
from core.database import get_db
from db.models.user import User

logger = structlog.get_logger()

router = APIRouter(prefix="/coach", tags=["AI Coach"])
coach_engine = CoachEngine()


# ─── Schemas ──────────────────────────────────────────────────────────────────

class MessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class CreateSessionRequest(BaseModel):
    opening_context: str | None = Field(
        default=None,
        description="What the user wants to discuss (optional, for V2 session tracking)"
    )


class EndSessionRequest(BaseModel):
    closing_insight: str | None = Field(
        default=None,
        description="Key takeaway from the session (optional, for V2 continuity)"
    )
    next_session_hook: str | None = Field(
        default=None,
        description="What to follow up on next time (optional)"
    )


class SessionResponse(BaseModel):
    id: str
    coaching_mode: str
    message_count: int
    started_at: str
    last_message_at: str | None


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    created_at: str


# ─── Greeting Endpoint ────────────────────────────────────────────────────────

@router.get(
    "/greeting",
    summary="Get today's task greeting for the coach opening message",
)
async def get_coach_greeting(
    current_user: User = Depends(get_onboarded_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Returns a pre-formatted coach greeting based on today's task.
    The frontend injects this as the opening assistant message when starting
    a new session.

    If no task exists for today (e.g. before the 4am sweep), returns a fallback
    greeting and triggers on-demand task generation in the background.

    Response shape:
        {
            "has_task": bool,
            "task_title": str | None,
            "guidance": str | None,
            "greeting": str,
        }
    """
    uid = str(current_user.id)
    first_name = (current_user.display_name or "").split()[0] or "there"

    # Fetch today's task for this user
    result = await db.execute(
        text("""
            SELECT title, guidance
            FROM daily_tasks
            WHERE user_id = :user_id
              AND scheduled_date = CURRENT_DATE
            ORDER BY created_at DESC
            LIMIT 1
        """),
        {"user_id": uid},
    )
    row = result.fetchone()

    if not row:
        # No task yet — return fallback and trigger generation in background
        logger.info("coach_greeting_no_task", user_id=uid)
        return {
            "has_task": False,
            "task_title": None,
            "guidance": None,
            "greeting": (
                f"Good morning {first_name}, your task for today is being prepared. "
                "While you wait, what's on your mind?"
            ),
        }

    task_title = row[0] or ""
    guidance = row[1]  # May be NULL for tasks generated before migration

    # Build guidance line — fall back gracefully if column is null
    if guidance:
        guidance_line = f"\n\nHow to approach it: {guidance}"
    else:
        guidance_line = ""

    greeting = (
        f"Good morning {first_name}. Your task today is: {task_title}.{guidance_line}"
        f"\n\nHow can I help you with today's task, or is there something else on your mind?"
    )

    logger.info("coach_greeting_served", user_id=uid, task_title=task_title, has_guidance=bool(guidance))

    return {
        "has_task": True,
        "task_title": task_title,
        "guidance": guidance,
        "greeting": greeting,
    }


# ─── Session Management (V2 Enhanced) ─────────────────────────────────────────

@router.post(
    "/sessions",
    status_code=status.HTTP_201_CREATED,
    summary="Create a new coach session",
)
async def create_session(
    payload: CreateSessionRequest | None = None,
    current_user: User = Depends(get_onboarded_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Create a new V2 coach session with optional opening context.
    The opening context helps the coach arrive with continuity from previous sessions.
    """
    opening = payload.opening_context if payload else None

    # Use V2 start_session which creates both V2 and legacy session records
    session_id = await coach_engine.start_session(
        current_user.id,
        db,
        opening_context=opening
    )

    logger.info(
        "coach_session_created_v2",
        user_id=str(current_user.id),
        session_id=session_id,
        has_opening_context=bool(opening),
    )

    return {
        "session_id": session_id,
        "version": "v2",
        "message": "Session created. Use /sessions/{id}/message to start the conversation.",
    }


@router.get(
    "/sessions/active",
    summary="Get or create the active coach session (with V2 continuity)",
)
async def get_active_session(
    current_user: User = Depends(get_onboarded_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Get the active session or create a new one.
    If creating new, automatically pulls in continuity from last session (V2).
    """
    session_id = await coach_engine.get_or_create_active_session(current_user.id, db)

    # Check if this is a fresh session (no messages yet) for continuity handling
    msg_result = await db.execute(
        text("""
            SELECT COUNT(*) FROM ai_coach_messages
            WHERE session_id = :session_id
        """),
        {"session_id": session_id},
    )
    message_count = msg_result.scalar() or 0
    is_new_session = message_count == 0

    # Load messages for this session
    result = await db.execute(
        text("""
            SELECT id, role, content, created_at
            FROM ai_coach_messages
            WHERE session_id = :session_id
            ORDER BY created_at ASC
            LIMIT 50
        """),
        {"session_id": session_id},
    )
    messages = [
        {
            "id": str(row.id),
            "role": row.role,
            "content": row.content,
            "created_at": str(row.created_at),
        }
        for row in result.fetchall()
    ]

    # V2: Get session continuity info for frontend
    continuity = None
    if is_new_session:
        cont_result = await db.execute(
            text("""
                SELECT next_session_hook, closing_insight
                FROM coach_sessions
                WHERE id = :session_id
            """),
            {"session_id": session_id},
        )
        cont_row = cont_result.fetchone()
        if cont_row:
            continuity = {
                "pending_follow_up": cont_row[0],
                "last_insight": cont_row[1],
            }

    return {
        "session_id": session_id,
        "is_new_session": is_new_session,
        "message_count": message_count,
        "messages": messages,
        "continuity": continuity,
    }


@router.get(
    "/sessions",
    summary="List recent coach sessions (V2 enhanced)",
)
async def list_sessions(
    limit: int = 10,
    include_v2_details: bool = False,
    current_user: User = Depends(get_onboarded_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    List recent sessions. Set include_v2_details=true to get opening/closing insights.
    """
    if include_v2_details:
        result = await db.execute(
            text("""
                SELECT
                    cs.id,
                    cs.coach_mode_used as coaching_mode,
                    cs.session_start as started_at,
                    cs.session_end as ended_at,
                    cs.opening_context,
                    cs.closing_insight,
                    cs.next_session_hook,
                    COUNT(acm.id) as message_count
                FROM coach_sessions cs
                LEFT JOIN ai_coach_messages acm ON acm.session_id = cs.id::text
                WHERE cs.user_id = :user_id
                GROUP BY cs.id, cs.coach_mode_used, cs.session_start,
                         cs.session_end, cs.opening_context, cs.closing_insight, cs.next_session_hook
                ORDER BY cs.session_start DESC
                LIMIT :limit
            """),
            {"user_id": str(current_user.id), "limit": min(limit, 50)},
        )
        sessions = [
            {
                "id": str(row.id),
                "coaching_mode": row.coaching_mode or "guide",
                "message_count": row.message_count,
                "started_at": str(row.started_at) if row.started_at else None,
                "ended_at": str(row.ended_at) if row.ended_at else None,
                "opening_context": row.opening_context,
                "closing_insight": row.closing_insight,
                "next_session_hook": row.next_session_hook,
                "is_v2": True,
            }
            for row in result.fetchall()
        ]
    else:
        result = await db.execute(
            text("""
                SELECT id, coaching_mode, message_count, started_at, last_message_at
                FROM ai_coach_sessions
                WHERE user_id = :user_id
                ORDER BY started_at DESC
                LIMIT :limit
            """),
            {"user_id": str(current_user.id), "limit": min(limit, 50)},
        )
        sessions = [
            {
                "id": str(row.id),
                "coaching_mode": row.coaching_mode,
                "message_count": row.message_count,
                "started_at": str(row.started_at),
                "last_message_at": str(row.last_message_at) if row.last_message_at else None,
            }
            for row in result.fetchall()
        ]

    return {"sessions": sessions, "version": "v2" if include_v2_details else "v1"}


# ─── Streaming Message (V2 Enhanced) ──────────────────────────────────────────

@router.post(
    "/sessions/{session_id}/message",
    summary="Send a message to the coach (streaming SSE response, V2)",
)
async def send_message(
    session_id: str,
    payload: MessageRequest,
    current_user: User = Depends(get_onboarded_user),
    db: AsyncSession = Depends(get_db),
    quota_info: dict = Depends(require_ai_quota("coach")),
) -> StreamingResponse:
    """
    Send a message to the AI coach and receive a streaming response.

    V2 Enhancements:
      - First message in session triggers is_new_session=True for continuity
      - Automatic moment detection (breakthroughs, resistance, commitments)
      - Crisis mode integration for safety concerns

    Quota headers included in response:
        X-Quota-Status: unlimited|active|warning
        X-Quota-Count: current usage count
        X-Quota-Limit: daily limit (or 'unlimited')
        X-Quota-Remaining: messages remaining (if applicable)
    """
    # Verify session belongs to this user (check both V2 and legacy)
    result = await db.execute(
        text("""
            SELECT id FROM coach_sessions
            WHERE id = :session_id AND user_id = :user_id AND session_end IS NULL
            UNION
            SELECT id FROM ai_coach_sessions
            WHERE id = :session_id AND user_id = :user_id AND is_active = TRUE
        """),
        {"session_id": session_id, "user_id": str(current_user.id)},
    )
    if not result.fetchone():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or not active.",
        )

    # Check if this is the first message (for V2 continuity)
    msg_count_result = await db.execute(
        text("""
            SELECT COUNT(*) FROM ai_coach_messages
            WHERE session_id = :session_id
        """),
        {"session_id": session_id},
    )
    is_new_session = (msg_count_result.scalar() or 0) == 0

    # Build quota headers for SSE
    quota_headers = {
        "X-Quota-Status": quota_info.get("quota_status", "unknown"),
        "X-Quota-Count": str(quota_info.get("count", 0)),
        "X-Quota-Limit": str(quota_info.get("limit", "unlimited")) if quota_info.get("limit") != float('inf') else "unlimited",
    }

    if quota_info.get("warning"):
        quota_headers["X-Quota-Warning"] = "true"
        quota_headers["X-Quota-Remaining"] = str(quota_info.get("remaining", 0))

    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            # Send polished quota warning as first SSE event if applicable
            if quota_info.get("warning"):
                remaining = quota_info.get("remaining", 0)
                count = quota_info.get("count", 0)
                limit = quota_info.get("limit", 10)

                if remaining == 0:
                    warning_level = "critical"
                    message = "This is your last message today"
                    subtext = "Upgrade to Forge for unlimited coaching sessions"
                elif remaining == 1:
                    warning_level = "urgent"
                    message = "1 message remaining today"
                    subtext = "Make it count — or upgrade to Forge for unlimited access"
                else:
                    warning_level = "notice"
                    message = f"{remaining} messages remaining today"
                    subtext = "You're making progress. Upgrade anytime for unlimited coaching."

                warning_event = {
                    "type": "quota_banner",
                    "level": warning_level,
                    "message": message,
                    "subtext": subtext,
                    "usage": {
                        "used": count,
                        "limit": limit,
                        "remaining": remaining
                    },
                    "action": {
                        "text": "Upgrade to Forge",
                        "link": "/settings/upgrade"
                    },
                    "style": {
                        "dismissible": True,
                        "position": "above_chat",
                        "theme": "amber" if warning_level == "notice" else "orange" if warning_level == "urgent" else "red"
                    }
                }
                yield f"event: system\nid: quota-warning\ndata: {json.dumps(warning_event)}\n\n"

            # V2: Stream without passing db — engine manages its own connections
            async for chunk in coach_engine.stream_response(
                user_id=current_user.id,
                session_id=session_id,
                user_message=payload.content,
                is_new_session=is_new_session,
            ):
                escaped = chunk.replace("\n", "\\n")
                yield f"data: {escaped}\n\n"

            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error(
                "coach_stream_error",
                user_id=str(current_user.id),
                session_id=session_id,
                error=str(e),
            )
            yield f"data: [ERROR] Something went wrong. Please try again.\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            **quota_headers,
        },
    )


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="End a coach session (V2: with closing insight)",
)
async def end_session(
    session_id: str,
    payload: EndSessionRequest | None = None,
    background_tasks: BackgroundTasks = None,
    current_user: User = Depends(get_onboarded_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    End a coach session with optional closing insight (V2).
    The closing insight and next_session_hook enable continuity in future sessions.
    """
    closing = payload.closing_insight if payload else None
    next_hook = payload.next_session_hook if payload else None

    await coach_engine.end_session(
        user_id=current_user.id,
        session_id=session_id,
        closing_insight=closing,
        next_hook=next_hook,
        db=db,
    )

    logger.info(
        "coach_session_ended_v2",
        user_id=str(current_user.id),
        session_id=session_id,
        has_closing_insight=bool(closing),
        has_next_hook=bool(next_hook),
    )