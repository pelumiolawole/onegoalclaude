"""
ai/engines/interview.py

AI Discovery Interview Engine

Drives the conversational onboarding experience.
Maintains conversation state, extracts structured data from natural dialogue,
and writes findings to the identity_profile and onboarding_interview_state tables.

Flow:
    1. User sends a message
    2. Engine loads conversation history from DB
    3. Builds prompt with current phase context
    4. Gets AI response
    5. Extracts any newly surfaced data points
    6. Updates onboarding_interview_state
    7. If interview is complete, writes to identity_profile + advances onboarding status

The extraction happens silently — the user just has a conversation.
"""

import json
from uuid import UUID

import structlog
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession

from ai.base import BaseAIEngine
from ai.prompts.system_prompts import get_prompt
from ai.utils.safety_filter import SafetyLevel, safety_filter
from core.config import settings
from core.security import sanitize_input

logger = structlog.get_logger()

# Phases in order — the interview moves through these
INTERVIEW_PHASES = [
    "intro",
    "life_direction",
    "vision",
    "habits",
    "strengths",
    "frustrations",
    "time",
    "lifestyle",
    "summary",
]


class InterviewEngine(BaseAIEngine):
    """
    Manages the AI discovery interview.
    Stateful — loads and saves conversation from the database.
    """

    engine_name = "interview"
    default_temperature = 0.8  # warmer, more conversational

    async def process_message(
        self,
        user_id: UUID | str,
        user_message: str,
        db: AsyncSession,
    ) -> dict:
        """
        Process a user message in the interview flow.

        Returns:
            {
                message: str,         — AI response to show user
                phase: str,           — current interview phase
                is_complete: bool,    — True when interview finishes
                extracted: dict,      — data extracted so far
            }
        """
        uid = str(user_id)

        # Safety check first
        safety_level = safety_filter.classify(user_message)
        if safety_level in (SafetyLevel.CRISIS, SafetyLevel.DISTRESS):
            safe_response = safety_filter.get_safe_response(safety_level)
            await safety_filter.log_safety_flag(
                user_id=uid,
                source_type="interview_message",
                source_id=uid,
                level=safety_level,
                excerpt=user_message[:200],
                ai_response=safe_response,
                db=db,
            )
            return {
                "message": safe_response,
                "phase": "paused",
                "is_complete": False,
                "extracted": {},
            }

        # Prompt injection check
        if safety_filter.detect_prompt_injection(user_message):
            return {
                "message": "I didn't quite follow that. Let's continue getting to know you — tell me more about where you are in your life right now.",
                "phase": "error",
                "is_complete": False,
                "extracted": {},
            }

        # Clean input
        clean_message = sanitize_input(user_message)

        # Load interview state
        state = await self._load_state(uid, db)
        messages = state.get("messages", [])
        current_phase = state.get("current_phase", "intro")
        extracted = state.get("extracted_data", {})

        # Advance onboarding status if this is the first message
        await self._ensure_interview_started(uid, db)

        # Add user message to history
        messages.append({"role": "user", "content": clean_message})

        # Build the prompt
        system_prompt = get_prompt("interview")

        # Keep last 20 messages for context (older context available via embeddings)
        context_messages = messages[-20:] if len(messages) > 20 else messages

        prompt_messages = [
            {"role": "system", "content": system_prompt},
            *context_messages,
        ]

        # Get AI response
        ai_response = await self._complete(
            messages=prompt_messages,
            user_id=uid,
            temperature=0.8,
            max_tokens=600,
        )

        # Add AI response to history
        messages.append({"role": "assistant", "content": ai_response})

        # Extract structured data from this exchange
        new_extractions = await self._extract_data(
            user_message=clean_message,
            ai_response=ai_response,
            current_extracted=extracted,
            current_phase=current_phase,
            db=db,
            user_id=uid,
        )
        extracted.update(new_extractions)

        # Determine if phase should advance
        next_phase = self._determine_phase(current_phase, ai_response, extracted)

        # Check if interview is complete
        is_complete = self._is_interview_complete(ai_response, extracted)

        # Save state
        await self._save_state(
            user_id=uid,
            messages=messages,
            current_phase=next_phase,
            extracted_data=extracted,
            is_complete=is_complete,
            db=db,
        )

        # If complete, write to identity profile
        if is_complete:
            await self._finalize_profile(uid, extracted, db)

        return {
            "message": ai_response,
            "phase": next_phase,
            "is_complete": is_complete,
            "extracted": extracted,
        }

    async def _extract_data(
        self,
        user_message: str,
        ai_response: str,
        current_extracted: dict,
        current_phase: str,
        db: AsyncSession,
        user_id: str,
    ) -> dict:
        """
        Silently extract structured profile data from a conversation turn.
        Uses a separate AI call with lower temperature for accuracy.
        """
        extraction_prompt = f"""Extract any new profile information from this conversation exchange.
Only extract what was explicitly stated or clearly implied by the user.
Return ONLY a JSON object with any of these fields that were discussed:
{{
  "life_direction": "...",
  "personal_vision": "...",
  "core_values": ["..."],
  "self_reported_strengths": ["..."],
  "self_reported_weaknesses": ["..."],
  "time_availability": {{"morning": 30, "evening": 60, "weekend": 120}},
  "lifestyle_context": {{"workStyle": "remote|office|hybrid", "familyStatus": "..."}},
  "resistance_triggers": ["..."],
  "motivation_style": "aspiration_driven|fear_driven|values_driven|achievement_driven",
  "peak_performance_time": "early_morning|late_morning|afternoon|evening"
}}

Conversation turn:
User: {user_message}
AI: {ai_response}

Already extracted: {json.dumps(current_extracted, indent=2)}

Return only NEW or UPDATED fields. Return empty object {{}} if nothing new was stated.
"""
        try:
            raw = await self._complete(
                messages=[{"role": "user", "content": extraction_prompt}],
                user_id=user_id,
                temperature=0.1,
                max_tokens=500,
            )
            return self._parse_json(raw, fallback={})
        except Exception as e:
            logger.warning("extraction_failed", error=str(e))
            return {}

    def _determine_phase(
        self,
        current_phase: str,
        ai_response: str,
        extracted: dict,
    ) -> str:
        """
        Determine if the conversation has moved to a new phase.
        Phases advance based on data coverage, not rigid turn counts.
        """
        phase_index = INTERVIEW_PHASES.index(current_phase) if current_phase in INTERVIEW_PHASES else 0

        # Check if current phase data is sufficiently covered
        phase_covered = {
            "intro": True,  # always move on
            "life_direction": bool(extracted.get("life_direction")),
            "vision": bool(extracted.get("personal_vision")),
            "habits": bool(extracted.get("lifestyle_context") or extracted.get("time_availability")),
            "strengths": bool(extracted.get("self_reported_strengths")),
            "frustrations": bool(extracted.get("self_reported_weaknesses") or extracted.get("resistance_triggers")),
            "time": bool(extracted.get("time_availability")),
            "lifestyle": bool(extracted.get("motivation_style") or extracted.get("peak_performance_time")),
            "summary": True,
        }

        if phase_covered.get(current_phase, False) and phase_index < len(INTERVIEW_PHASES) - 1:
            return INTERVIEW_PHASES[phase_index + 1]

        return current_phase

    def _is_interview_complete(self, ai_response: str, extracted: dict) -> bool:
        """Interview is complete when the AI signals it and core data is collected."""
        completion_signal = "let's define your one goal" in ai_response.lower()

        required_fields = ["life_direction", "personal_vision"]
        has_core_data = all(extracted.get(f) for f in required_fields)

        return completion_signal and has_core_data

    async def _load_state(self, user_id: str, db: AsyncSession) -> dict:
        """Load interview state from database."""
        result = await db.execute(
            text("""
                SELECT current_phase, messages, extracted_data, is_complete
                FROM onboarding_interview_state
                WHERE user_id = :user_id
            """),
            {"user_id": user_id},
        )
        row = result.fetchone()
        if not row:
            return {"current_phase": "intro", "messages": [], "extracted_data": {}}

        return {
            "current_phase": row.current_phase,
            "messages": row.messages or [],
            "extracted_data": row.extracted_data or {},
            "is_complete": row.is_complete,
        }

    async def _save_state(
        self,
        user_id: str,
        messages: list,
        current_phase: str,
        extracted_data: dict,
        is_complete: bool,
        db: AsyncSession,
    ) -> None:
        """Save interview state to database."""
        await db.execute(
            text("""
                UPDATE onboarding_interview_state
                SET current_phase = :phase,
                    messages = CAST(:messages AS jsonb),
                    extracted_data = CAST(:extracted AS jsonb),
                    is_complete = :is_complete,
                    completed_at = CASE WHEN :is_complete THEN NOW() ELSE completed_at END
                WHERE user_id = :user_id
            """),
            {
                "user_id": user_id,
                "phase": current_phase,
                "messages": json.dumps(messages),
                "extracted": json.dumps(extracted_data),
                "is_complete": is_complete,
            },
        )

    async def _ensure_interview_started(self, user_id: str, db: AsyncSession) -> None:
        """Advance onboarding status to interview_started on first message."""
        await db.execute(
            text("""
                UPDATE users
                SET onboarding_status = 'interview_started'
                WHERE id = :user_id AND onboarding_status = 'created'
            """),
            {"user_id": user_id},
        )

    async def _finalize_profile(
        self, user_id: str, extracted: dict, db: AsyncSession
    ) -> None:
        """
        Write extracted data to identity_profile and advance onboarding status.
        Called once when interview is complete.
        """
        # Write to identity profile
        await db.execute(
            text("""
                UPDATE identity_profiles SET
                    life_direction = COALESCE(:life_direction, life_direction),
                    personal_vision = COALESCE(:personal_vision, personal_vision),
                    core_values = COALESCE(:core_values, core_values),
                    self_reported_strengths = COALESCE(:strengths, self_reported_strengths),
                    self_reported_weaknesses = COALESCE(:weaknesses, self_reported_weaknesses),
                    time_availability = COALESCE(:time_availability, time_availability),
                    lifestyle_context = COALESCE(:lifestyle_context, lifestyle_context),
                    resistance_triggers = COALESCE(:resistance_triggers, resistance_triggers),
                    motivation_style = COALESCE(:motivation_style, motivation_style),
                    peak_performance_time = COALESCE(:peak_time, peak_performance_time),
                    last_ai_update = NOW()
                WHERE user_id = :user_id
            """),
            {
                "user_id": user_id,
                "life_direction": extracted.get("life_direction"),
                "personal_vision": extracted.get("personal_vision"),
                "core_values": extracted.get("core_values"),
                "strengths": extracted.get("self_reported_strengths"),
                "weaknesses": extracted.get("self_reported_weaknesses"),
                "time_availability": json.dumps(extracted.get("time_availability")) if extracted.get("time_availability") else None,
                "lifestyle_context": json.dumps(extracted.get("lifestyle_context")) if extracted.get("lifestyle_context") else None,
                "resistance_triggers": extracted.get("resistance_triggers"),
                "motivation_style": extracted.get("motivation_style"),
                "peak_time": extracted.get("peak_performance_time"),
            },
        )

        # Advance onboarding status
        await db.execute(
            text("UPDATE users SET onboarding_status = 'interview_complete' WHERE id = :user_id"),
            {"user_id": user_id},
        )

        logger.info("interview_finalized", user_id=user_id)
