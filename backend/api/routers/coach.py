"""
api/routers/coach.py

AI Coach endpoints:
    POST /coach/sessions              — Create a new session
    GET  /coach/sessions              — List recent sessions
    GET  /coach/sessions/{id}         — Get session with messages
    POST /coach/sessions/{id}/message — Send message (streaming SSE)
    GET  /coach/sessions/active       — Get or create active session
    DELETE /coach/sessions/{id}       — End a session
"""

import json
from collections.abc import AsyncGenerator
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
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


# ─── Session Management ───────────────────────────────────────────────────────

@router.post(
    "/sessions",
    status_code=status.HTTP_201_CREATED,
    summary="Create a new coach session",
)
async def create_session(
    current_user: User = Depends(get_onboarded_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    session_id = await coach_engine.create_session(current_user.id, db)
    return {"session_id": session_id}


@router.get(
    "/sessions/active",
    summary="Get or create the active coach session",
)
async def get_active_session(
    current_user: User = Depends(get_onboarded_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    session_id = await coach_engine.get_or_create_active_session(current_user.id, db)

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

    return {"session_id": session_id, "messages": messages}


@router.get(
    "/sessions",
    summary="List recent coach sessions",
)
async def list_sessions(
    limit: int = 10,
    current_user: User = Depends(get_onboarded_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
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
    return {"sessions": sessions}


# ─── Streaming Message ────────────────────────────────────────────────────────

@router.post(
    "/sessions/{session_id}/message",
    summary="Send a message to the coach (streaming SSE response)",
)
async def send_message(
    session_id: str,
    payload: MessageRequest,
    current_user: User = Depends(get_onboarded_user),
    db: AsyncSession = Depends(get_db),
    _quota: None = Depends(require_ai_quota("coach")),
) -> StreamingResponse:
    """
    Send a message to the AI coach and receive a streaming response.

    Returns Server-Sent Events (SSE) stream.
    Each event has the format: data: <text_chunk>

    The stream ends with: data: [DONE]

    Frontend usage with EventSource or fetch:
        const response = await fetch('/api/coach/sessions/{id}/message', {
            method: 'POST',
            headers: { 'Authorization': 'Bearer ...', 'Content-Type': 'application/json' },
            body: JSON.stringify({ content: 'message here' })
        });
        const reader = response.body.getReader();
        // read chunks...
    """
    # Verify session belongs to this user
    result = await db.execute(
        text("""
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

    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            async for chunk in coach_engine.stream_response(
                user_id=current_user.id,
                session_id=session_id,
                user_message=payload.content,
                db=db,
            ):
                # SSE format: each event is "data: <content>\n\n"
                escaped = chunk.replace("\n", "\\n")
                yield f"data: {escaped}\n\n"

            # Signal stream completion
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
            "X-Accel-Buffering": "no",  # disable nginx buffering for SSE
        },
    )


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="End a coach session",
)
async def end_session(
    session_id: str,
    current_user: User = Depends(get_onboarded_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await db.execute(
        text("""
            UPDATE ai_coach_sessions
            SET is_active = FALSE, ended_at = NOW()
            WHERE id = :session_id AND user_id = :user_id
        """),
        {"session_id": session_id, "user_id": str(current_user.id)},
    )
