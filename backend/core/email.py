"""
core/email.py

Email sending utility for system alerts and notifications.
Uses Resend API for reliable delivery.
"""

import os

import httpx
import structlog

logger = structlog.get_logger()

# Configuration from environment
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "coach@pelumiolawole.com")
ALERT_RECIPIENT = os.getenv("ALERT_EMAIL", "coach@pelumiolawole.com")
RESEND_API_URL = "https://api.resend.com/emails"


async def send_safety_alert(
    user_id: str,
    flag_type: str,
    severity: int,
    excerpt: str,
    ai_response: str,
) -> bool:
    """
    Send immediate email alert when user safety is flagged.
    
    Args:
        user_id: UUID of the user who triggered the flag
        flag_type: Type of flag (crisis, distress, etc.)
        severity: 1-10 severity score
        excerpt: The concerning message excerpt
        ai_response: What the AI responded with
    """
    if not RESEND_API_KEY:
        logger.warning("resend_api_key_not_set", msg="Safety alert queued but email not sent")
        return False

    try:
        from datetime import datetime
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M UTC')
        severity_emoji = "🚨" if severity >= 8 else "⚠️"
        
        # Plain text version
        text_body = f"""
SAFETY ALERT - OneGoal Pro

User ID: {user_id}
Flag Type: {flag_type}
Severity: {severity}/10
Time: {timestamp}

USER MESSAGE EXCERPT:
{excerpt}

AI RESPONSE SENT:
{ai_response}

ACTION REQUIRED:
1. Review full context in admin dashboard
2. Assess if human intervention needed
3. Respond within 24 hours per SLA

---
This is an automated alert from OneGoal Pro.
        """

        # HTML version
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Safety Alert - OneGoal Pro</title>
        </head>
        <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #f3f4f6;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f3f4f6;">
                <tr>
                    <td align="center" style="padding: 40px 20px;">
                        <table width="600" cellpadding="0" cellspacing="0" style="max-width: 600px; width: 100%; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                            
                            <!-- Header -->
                            <tr>
                                <td style="background-color: #dc2626; padding: 24px; text-align: center;">
                                    <h1 style="margin: 0; color: #ffffff; font-size: 24px; font-weight: 600;">
                                        {severity_emoji} Safety Alert
                                    </h1>
                                    <p style="margin: 8px 0 0 0; color: #fecaca; font-size: 14px; text-transform: uppercase; letter-spacing: 0.05em;">
                                        {flag_type.upper()} — Severity {severity}/10
                                    </p>
                                </td>
                            </tr>
                            
                            <!-- Meta Info -->
                            <tr>
                                <td style="padding: 24px; background-color: #f9fafb; border-bottom: 1px solid #e5e7eb;">
                                    <table width="100%" cellpadding="0" cellspacing="0">
                                        <tr>
                                            <td style="padding-bottom: 8px;">
                                                <span style="color: #6b7280; font-size: 12px; text-transform: uppercase; font-weight: 600;">User ID</span>
                                                <p style="margin: 4px 0 0 0; color: #111827; font-family: monospace; font-size: 13px;">{user_id}</p>
                                            </td>
                                            <td style="padding-bottom: 8px; text-align: right;">
                                                <span style="color: #6b7280; font-size: 12px; text-transform: uppercase; font-weight: 600;">Time</span>
                                                <p style="margin: 4px 0 0 0; color: #111827; font-size: 13px;">{timestamp}</p>
                                            </td>
                                        </tr>
                                    </table>
                                </td>
                            </tr>
                            
                            <!-- User Message -->
                            <tr>
                                <td style="padding: 24px;">
                                    <h3 style="margin: 0 0 12px 0; color: #374151; font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 600;">
                                        User Message Excerpt
                                    </h3>
                                    <div style="background-color: #fffbeb; border-left: 4px solid #f59e0b; padding: 16px; border-radius: 0 6px 6px 0; color: #92400e; font-size: 14px; line-height: 1.5;">
                                        {excerpt[:500]}{'...' if len(excerpt) > 500 else ''}
                                    </div>
                                </td>
                            </tr>
                            
                            <!-- AI Response -->
                            <tr>
                                <td style="padding: 0 24px 24px 24px;">
                                    <h3 style="margin: 0 0 12px 0; color: #374151; font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 600;">
                                        AI Response Sent
                                    </h3>
                                    <div style="background-color: #ecfdf5; border-left: 4px solid #10b981; padding: 16px; border-radius: 0 6px 6px 0; color: #065f46; font-size: 14px; line-height: 1.5;">
                                        {ai_response[:300]}{'...' if len(ai_response) > 300 else ''}
                                    </div>
                                </td>
                            </tr>
                            
                            <!-- Action Required -->
                            <tr>
                                <td style="padding: 0 24px 24px 24px;">
                                    <div style="background-color: #fee2e2; border-radius: 8px; padding: 20px;">
                                        <h3 style="margin: 0 0 16px 0; color: #991b1b; font-size: 16px; font-weight: 600;">
                                            Action Required
                                        </h3>
                                        <ol style="margin: 0; padding-left: 20px; color: #7f1d1d; font-size: 14px; line-height: 1.6;">
                                            <li style="margin-bottom: 8px;">Review full context in admin dashboard</li>
                                            <li style="margin-bottom: 8px;">Assess if human intervention needed</li>
                                            <li>Respond within 24 hours per SLA</li>
                                        </ol>
                                    </div>
                                </td>
                            </tr>
                            
                            <!-- Footer -->
                            <tr>
                                <td style="padding: 24px; background-color: #f9fafb; border-top: 1px solid #e5e7eb; text-align: center;">
                                    <p style="margin: 0; color: #9ca3af; font-size: 12px;">
                                        This is an automated alert from OneGoal Pro.<br>
                                        Please do not reply to this email.
                                    </p>
                                </td>
                            </tr>
                            
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """

        # Send via Resend API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                RESEND_API_URL,
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": f"OneGoal Safety <{FROM_EMAIL}>",
                    "to": [ALERT_RECIPIENT],
                    "subject": f"{severity_emoji} OneGoal Safety Alert: {flag_type.upper()} (Severity {severity})",
                    "text": text_body,
                    "html": html_body,
                },
                timeout=30.0,
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(
                    "safety_alert_sent",
                    user_id=user_id,
                    flag_type=flag_type,
                    severity=severity,
                    email_id=result.get("id"),
                )
                return True
            else:
                logger.error(
                    "resend_api_error",
                    status_code=response.status_code,
                    response=response.text,
                )
                return False

    except Exception as e:
        logger.error("safety_alert_failed", user_id=user_id, error=str(e))
        return False


async def send_test_email(to_email: str) -> bool:
    """Send a test email to verify configuration."""
    if not RESEND_API_KEY:
        logger.error("resend_api_key_not_set")
        return False

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                RESEND_API_URL,
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": f"OneGoal <{FROM_EMAIL}>",
                    "to": [to_email],
                    "subject": "Test Email from OneGoal Pro",
                    "html": "<p>This is a test email. Your Resend integration is working!</p>",
                },
                timeout=30.0,
            )
            
            return response.status_code == 200

    except Exception as e:
        logger.error("test_email_failed", error=str(e))
        return False