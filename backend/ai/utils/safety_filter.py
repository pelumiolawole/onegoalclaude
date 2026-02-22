"""
ai/utils/safety_filter.py

Safety filter for all user-generated content.

Two layers of protection:
    1. Pattern matching  — fast, runs on every input before AI call
    2. AI classification — deeper check for ambiguous content

Safety levels:
    SAFE        — process normally
    CAUTION     — AI coach shifts to support mode, no advice given
    DISTRESS    — coaching paused, supportive response + resources
    CRISIS      — coaching stops completely, crisis resources shown immediately

This module is called:
    - Before every coach message is processed
    - After every reflection is submitted
    - Before any AI response is shown to the user

Design principle: When in doubt, escalate. A false positive
(treating frustration as distress) is far better than a false negative.
"""

import re
from enum import Enum

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


class SafetyLevel(str, Enum):
    SAFE = "safe"
    CAUTION = "caution"       # frustration, mild negativity
    DISTRESS = "distress"     # hopelessness, self-criticism, despair
    CRISIS = "crisis"         # self-harm, suicidal ideation


# ─── Pattern dictionaries ─────────────────────────────────────────────────────

CRISIS_PATTERNS = [
    r"\bsuicid",
    r"\bkill\s+(my)?self\b",
    r"\bend\s+(my|it\s+all|everything)\b",
    r"\bwant\s+to\s+die\b",
    r"\bno\s+reason\s+to\s+(live|go\s+on)\b",
    r"\bself.harm\b",
    r"\bhurt\s+myself\b",
    r"\bcut\s+myself\b",
    r"\bsaying\s+goodbye\b",
    r"\bnot\s+be\s+here\b",
]

DISTRESS_PATTERNS = [
    r"\bhopeless\b",
    r"\bgive\s+up\b",
    r"\bcan'?t\s+(do\s+this|go\s+on)\b",
    r"\bworthless\b",
    r"\bfailure\b.*\b(am|feel)\b",
    r"\bnothing\s+(matters|works)\b",
    r"\balone\b.*\b(always|forever)\b",
    r"\bdesperate\b",
    r"\bbroken\b",
    r"\bno\s+point\b",
]

CAUTION_PATTERNS = [
    r"\bstressed\b",
    r"\boverwhelmed\b",
    r"\bburnt?\s+out\b",
    r"\bfrustrat",
    r"\banxious\b",
    r"\bstrugglin",
    r"\bgiving\s+up\b",
    r"\bcan'?t\s+keep\b",
]

OUT_OF_SCOPE_PATTERNS = [
    r"\bdiagnos",
    r"\bmedication\b",
    r"\btherapist\b.*\badvice\b",
    r"\blegal\s+(advice|counsel)\b",
    r"\binvest\b.*\b(money|stock|crypto)\b",
    r"\bprescri",
]

PROMPT_INJECTION_PATTERNS = [
    r"ignore\s+(previous|all|prior|above)\s+instructions?",
    r"you\s+are\s+now\s+",
    r"act\s+as\s+(if|a|an)\s+",
    r"pretend\s+(you\s+are|to\s+be)",
    r"(disregard|forget)\s+(your|all)\s+",
    r"\[INST\]",
    r"<<SYS>>",
    r"<\|im_start\|>",
    r"jailbreak",
    r"dan\s+mode",
]

# Crisis resources shown when safety level is DISTRESS or CRISIS
CRISIS_RESOURCES = """
If you're going through something difficult right now, please know you don't have to face it alone.

**Crisis & Mental Health Support:**
- **988 Suicide & Crisis Lifeline**: Call or text 988 (US)
- **Crisis Text Line**: Text HOME to 741741
- **International Association for Suicide Prevention**: https://www.iasp.info/resources/Crisis_Centres/
- **NAMI Helpline**: 1-800-950-NAMI (6264)

Speaking with a therapist or counselor can make a real difference. You deserve support.
"""


# ─── SafetyFilter ────────────────────────────────────────────────────────────

class SafetyFilter:

    def classify(self, text: str) -> SafetyLevel:
        """
        Fast pattern-based safety classification.
        Called synchronously before any AI processing.
        """
        if not text:
            return SafetyLevel.SAFE

        lower = text.lower()

        # Check most severe first
        for pattern in CRISIS_PATTERNS:
            if re.search(pattern, lower):
                return SafetyLevel.CRISIS

        for pattern in DISTRESS_PATTERNS:
            if re.search(pattern, lower):
                return SafetyLevel.DISTRESS

        for pattern in CAUTION_PATTERNS:
            if re.search(pattern, lower):
                return SafetyLevel.CAUTION

        return SafetyLevel.SAFE

    def detect_prompt_injection(self, text: str) -> bool:
        """Return True if the text contains prompt injection patterns."""
        lower = text.lower()
        return any(re.search(p, lower) for p in PROMPT_INJECTION_PATTERNS)

    def detect_out_of_scope(self, text: str) -> bool:
        """Return True if user is asking for advice outside coaching scope."""
        lower = text.lower()
        return any(re.search(p, lower) for p in OUT_OF_SCOPE_PATTERNS)

    def get_safe_response(self, level: SafetyLevel, context: str = "") -> str:
        """
        Return a pre-written safe response for each safety level.
        The AI coach is NOT called when level is CRISIS.
        """
        if level == SafetyLevel.CRISIS:
            return (
                "I hear you, and I want you to know that what you're feeling matters. "
                "This is beyond what I'm able to help with, and I want to make sure "
                "you get real support right now.\n\n"
                + CRISIS_RESOURCES
            )

        if level == SafetyLevel.DISTRESS:
            return (
                "It sounds like you're carrying something really heavy right now. "
                "I'm not going to push forward with goals or tasks — that's not "
                "what you need in this moment.\n\n"
                "What you're feeling is valid. Sometimes the most important thing "
                "is just to pause and breathe.\n\n"
                "If things feel really dark, please reach out to someone who can "
                "genuinely support you:\n\n"
                + CRISIS_RESOURCES
            )

        return ""  # SAFE and CAUTION: let the AI respond, but shift mode

    def get_out_of_scope_response(self) -> str:
        return (
            "That's outside what I can helpfully guide you on. For medical, legal, "
            "or financial questions, please speak with a qualified professional who "
            "knows your specific situation. I'm here to help with your identity "
            "transformation and goal journey."
        )

    async def log_safety_flag(
        self,
        user_id: str,
        source_type: str,
        source_id: str,
        level: SafetyLevel,
        excerpt: str,
        ai_response: str,
        db: AsyncSession,
    ) -> None:
        """
        Log safety events to ai_safety_flags table.
        These are only accessible by the service role — never shown to the user.
        """
        severity = {
            SafetyLevel.CAUTION: 1,
            SafetyLevel.DISTRESS: 2,
            SafetyLevel.CRISIS: 3,
        }.get(level, 1)

        try:
            await db.execute(
                text("""
                    INSERT INTO ai_safety_flags
                        (user_id, source_type, source_id, flag_type, severity,
                         excerpt, ai_response, resources_shown)
                    VALUES
                        (:user_id, :source_type, :source_id, :flag_type, :severity,
                         :excerpt, :ai_response, :resources_shown)
                """),
                {
                    "user_id": user_id,
                    "source_type": source_type,
                    "source_id": source_id,
                    "flag_type": level.value,
                    "severity": severity,
                    "excerpt": excerpt[:200],
                    "ai_response": ai_response[:500],
                    "resources_shown": level in (SafetyLevel.DISTRESS, SafetyLevel.CRISIS),
                },
            )
        except Exception as e:
            logger.error("safety_flag_log_failed", error=str(e))


# Singleton
safety_filter = SafetyFilter()
