"""
ai/utils/safety_filter.py

Safety classification and response system for user messages.
Detects crisis, distress, and out-of-scope content.
"""

import enum
import re
from dataclasses import dataclass
from typing import Optional

import structlog

logger = structlog.get_logger()


class SafetyLevel(enum.Enum):
    NORMAL = "normal"
    DISTRESS = "distress"  # User struggling but not immediate danger
    CRISIS = "crisis"      # Potential self-harm or emergency


@dataclass
class SafetyResult:
    level: SafetyLevel
    flag_type: str
    severity: int  # 1-10
    reason: str


class SafetyFilter:
    """
    Classifies user messages for safety concerns.
    Conservative: flags borderline cases for human review.
    """

    # Crisis indicators - immediate concern
    CRISIS_PATTERNS = [
        r"\b(kill\s+(myself|me)|suicide|end\s+(my\s+)?life)\b",
        r"\b(hurt\s+(myself|me)|self.?harm|cut\s+myself)\b",
        r"\b(want\s+to\s+die|better\s+off\s+dead|not\s+worth\s+living)\b",
        r"\b(overdose|pills?\s+to\s+end|jump\s+(off|from))\b",
    ]

    # Distress indicators - struggling but not immediate
    DISTRESS_PATTERNS = [
        r"\b(depressed|depression|hopeless|can'?t\s+go\s+on)\b",
        r"\b(anxiety|panic\s+attack|can'?t\s+breathe|overwhelmed)\b",
        r"\b(trauma|ptsd|abuse[sd]|assaulted)\b",
        r"\b(addiction|relapse|using\s+again|can'?t\s+stop)\b",
        r"\b(burnout|exhausted|empty|numb)\b",
    ]

    # Out of scope - medical/legal/financial advice
    OUT_OF_SCOPE_PATTERNS = [
        r"\b(diagnose|diagnosis|medication|prescription|therapist|psychiatrist)\b",
        r"\b(lawsuit|sue|legal\s+advice|lawyer|court)\b",
        r"\b(invest|stock|crypto|financial\s+advisor|tax\s+advice)\b",
    ]

    def classify(self, text: str) -> SafetyResult:
        """Classify message safety level."""
        text_lower = text.lower()

        # Check crisis first (highest priority)
        for pattern in self.CRISIS_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return SafetyResult(
                    level=SafetyLevel.CRISIS,
                    flag_type="crisis_self_harm",
                    severity=9,
                    reason="Detected potential self-harm or crisis language"
                )

        # Check distress
        for pattern in self.DISTRESS_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return SafetyResult(
                    level=SafetyLevel.DISTRESS,
                    flag_type="emotional_distress",
                    severity=6,
                    reason="Detected emotional distress or mental health struggle"
                )

        return SafetyResult(
            level=SafetyLevel.NORMAL,
            flag_type="none",
            severity=1,
            reason="No concerns detected"
        )

    def detect_prompt_injection(self, text: str) -> bool:
        """Detect attempts to manipulate the AI."""
        injection_patterns = [
            r"ignore\s+(previous|prior|above)\s+instructions",
            r"system\s+prompt",
            r"you\s+are\s+now\s+a",
            r"forget\s+everything",
            r" DAN |jailbreak",
            r"\"\"\"[\s\S]*?\"\"\"",  # Triple quote blocks
        ]
        text_lower = text.lower()
        return any(re.search(p, text_lower) for p in injection_patterns)

    def detect_out_of_scope(self, text: str) -> bool:
        """Detect requests for professional advice."""
        text_lower = text.lower()
        return any(
            re.search(p, text_lower, re.IGNORECASE)
            for p in self.OUT_OF_SCOPE_PATTERNS
        )

    def get_safe_response(self, level: SafetyLevel) -> str:
        """Get appropriate response for safety level."""
        if level == SafetyLevel.CRISIS:
            return """I'm not equipped to help with what you're describing, and I want to make sure you get the right support.

If you're in immediate danger, please contact emergency services or go to your nearest hospital.

For support right now:
• **UK**: Samaritans at 116 123 or text SHOUT to 85258
• **US**: 988 Suicide & Crisis Lifeline
• **Nigeria**: 0806 210 6493 (NSPI)
• **Global**: Befrienders.org (find your country)

Your coach has been notified and will reach out within 24 hours."""

        if level == SafetyLevel.DISTRESS:
            return """I hear that you're going through a difficult time. While I'm here to support your goals, what you're describing sounds like it needs human care.

Consider reaching out to:
• A mental health professional
• Your doctor or GP
• A trusted friend or family member

You can also message your OneGoal coach directly — they've been notified and will check in with you."""

        return "I didn't follow that. Could you rephrase?"

    def get_out_of_scope_response(self) -> str:
        """Response for professional advice requests."""
        return """I'm your identity and goal coach, not a professional advisor. For what you're asking, you'd be better served by:

• Medical questions → Your doctor or healthcare provider
• Legal questions → A qualified solicitor or attorney  
• Financial questions → A financial advisor or accountant

I'm here for your goals, habits, and who you're becoming. What would you like to work on in that space?"""

    async def log_safety_flag(
        self,
        user_id: str,
        source_type: str,
        source_id: str,
        level: SafetyLevel,
        excerpt: str,
        ai_response: str,
        db=None,
    ) -> Optional[str]:
        """
        Log safety flag to database and trigger alert if needed.
        Returns flag ID if created.
        """
        from sqlalchemy import text
        
        flag_id = None
        
        try:
            # Insert into database
            if db:
                result = await db.execute(
                    text("""
                        INSERT INTO ai_safety_flags (
                            user_id, source_type, source_id,
                            flag_type, severity, excerpt, ai_response,
                            resources_shown, reviewed
                        ) VALUES (
                            :user_id, :source_type, :source_id,
                            :flag_type, :severity, :excerpt, :ai_response,
                            TRUE, FALSE
                        )
                        RETURNING id
                    """),
                    {
                        "user_id": user_id,
                        "source_type": source_type,
                        "source_id": source_id,
                        "flag_type": level.value,
                        "severity": 9 if level == SafetyLevel.CRISIS else 6,
                        "excerpt": excerpt[:500],
                        "ai_response": ai_response[:500],
                    }
                )
                flag_id = str(result.scalar())
                
                logger.info(
                    "safety_flag_logged",
                    flag_id=flag_id,
                    user_id=user_id,
                    level=level.value,
                    severity=9 if level == SafetyLevel.CRISIS else 6
                )

                # Send email alert for crisis/distress
                if level in (SafetyLevel.CRISIS, SafetyLevel.DISTRESS):
                    try:
                        from core.email import send_safety_alert
                        await send_safety_alert(
                            user_id=user_id,
                            flag_type=level.value,
                            severity=9 if level == SafetyLevel.CRISIS else 6,
                            excerpt=excerpt,
                            ai_response=ai_response,
                        )
                    except Exception as e:
                        logger.error("safety_alert_failed", error=str(e))
                        # Don't fail the request if email fails

            return flag_id

        except Exception as e:
            logger.error("safety_flag_log_failed", error=str(e), user_id=user_id)
            return None


# Singleton instance
safety_filter = SafetyFilter()