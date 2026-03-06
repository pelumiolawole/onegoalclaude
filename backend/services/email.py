"""
services/email.py

Email delivery service using Resend.
Handles transactional emails: verification, welcome, password reset, etc.
"""

import structlog
from datetime import datetime, timezone
from typing import Optional

import resend
from core.config import settings

logger = structlog.get_logger()

class EmailService:
    def __init__(self):
        self.api_key = settings.resend_api_key
        self.from_address = settings.email_from_address
        self.from_name = settings.email_from_name or "Pelumi Olawole (Coach PO)"
        self.from_header = f"{self.from_name} <{self.from_address}>"
        self.enabled = bool(self.api_key)
        
        if self.enabled:
            resend.api_key = self.api_key

    # ─── Verification Email ─────────────────────────────────────────────────

    async def send_verification_email(self, to_email: str, first_name: str, verification_url: str) -> bool:
        """Send email verification magic link"""
        if not self.enabled:
            logger.warning("verification_email_disabled", email=to_email)
            if settings.is_development:
                logger.info("dev_verification_url", email=to_email, url=verification_url)
            return False

        try:
            response = resend.Emails.send({
                "from": self.from_header,
                "to": to_email,
                "subject": "Confirm your email - OneGoal",
                "html": f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <title>Confirm your email</title>
                </head>
                <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #f5f5f5;">
                    <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f5f5f5; padding: 40px 0;">
                        <tr>
                            <td align="center">
                                <table width="600" cellpadding="0" cellspacing="0" style="background-color: #ffffff; border-radius: 8px; overflow: hidden; max-width: 600px; width: 100%;">
                                    <tr>
                                        <td style="padding: 40px;">
                                            <h1 style="margin: 0 0 20px 0; font-size: 24px; color: #111827; font-weight: 600;">Confirm your email</h1>
                                            
                                            <p style="margin: 0 0 20px 0; font-size: 16px; color: #374151; line-height: 1.6;">
                                                Hi {first_name or "there"},
                                            </p>
                                            
                                            <p style="margin: 0 0 20px 0; font-size: 16px; color: #374151; line-height: 1.6;">
                                                You signed up for OneGoal. Click the button below to confirm your email and get started.
                                            </p>
                                            
                                            <table width="100%" cellpadding="0" cellspacing="0" style="margin: 30px 0;">
                                                <tr>
                                                    <td align="center">
                                                        <a href="{verification_url}" style="display: inline-block; padding: 14px 32px; background-color: #111827; color: #ffffff; text-decoration: none; border-radius: 6px; font-size: 16px; font-weight: 500;">
                                                            Confirm email address
                                                        </a>
                                                    </td>
                                                </tr>
                                            </table>
                                            
                                            <p style="margin: 0 0 10px 0; font-size: 14px; color: #6b7280; line-height: 1.6;">
                                                This link expires in 24 hours.
                                            </p>
                                            
                                            <p style="margin: 0 0 20px 0; font-size: 14px; color: #6b7280; line-height: 1.6;">
                                                If you didn't sign up for OneGoal, you can ignore this email.
                                            </p>
                                            
                                            <p style="margin: 0; font-size: 14px; color: #6b7280; line-height: 1.6;">
                                                Button not working? Copy and paste this link:<br>
                                                <a href="{verification_url}" style="color: #6b7280; word-break: break-all;">{verification_url}</a>
                                            </p>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>
                    </table>
                </body>
                </html>
                """,
            })
            
            logger.info("verification_email_sent", email=to_email, message_id=response.get('id'))
            return True
            
        except Exception as e:
            logger.error("verification_email_failed", email=to_email, error=str(e))
            return False

    # ─── Welcome Email (UPDATED COPY) ───────────────────────────────────────

    async def send_welcome_email(self, to_email: str, display_name: Optional[str]) -> bool:
        """Send welcome email after verification with new copy"""
        if not self.enabled:
            logger.warning("welcome_email_disabled", email=to_email)
            return False
            
        name = display_name or "there"
        
        try:
            response = resend.Emails.send({
                "from": self.from_header,
                "to": to_email,
                "subject": "You're in — let's talk about who you're becoming",
                "html": f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <title>Welcome to OneGoal</title>
                </head>
                <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #f5f5f5;">
                    <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f5f5f5; padding: 40px 0;">
                        <tr>
                            <td align="center">
                                <table width="600" cellpadding="0" cellspacing="0" style="background-color: #ffffff; border-radius: 8px; overflow: hidden; max-width: 600px; width: 100%;">
                                    <tr>
                                        <td style="padding: 40px;">
                                            <p style="margin: 0 0 20px 0; font-size: 16px; color: #374151; line-height: 1.6;">
                                                Hi {name},
                                            </p>
                                            
                                            <p style="margin: 0 0 20px 0; font-size: 16px; color: #374151; line-height: 1.6;">
                                                You signed up. That already puts you ahead of most people who just think about getting better.
                                            </p>
                                            
                                            <h2 style="margin: 30px 0 15px 0; font-size: 18px; color: #111827; font-weight: 600;">Why I built this</h2>
                                            
                                            <p style="margin: 0 0 20px 0; font-size: 16px; color: #374151; line-height: 1.6;">
                                                I've spent nearly a decade watching talented people stay stuck. Not because they lacked ambition. Because they were chasing too many things at once, measuring themselves by what they <em>did</em> each day instead of who they were <em>becoming</em>.
                                            </p>
                                            
                                            <p style="margin: 0 0 20px 0; font-size: 16px; color: #374151; line-height: 1.6;">
                                                OneGoal is built on a simple belief: <strong>identity before strategy, to-be over to-do.</strong> You don't need another task list. You need a system that shapes the person who gets the results.
                                            </p>
                                            
                                            <h2 style="margin: 30px 0 15px 0; font-size: 18px; color: #111827; font-weight: 600;">What this helps you do</h2>
                                            
                                            <ul style="margin: 0 0 20px 0; padding-left: 20px; font-size: 16px; color: #374151; line-height: 1.6;">
                                                <li style="margin-bottom: 10px;"><strong>Focus</strong> — One priority. One direction. No more scattered energy.</li>
                                                <li style="margin-bottom: 10px;"><strong>Build</strong> — Small daily actions that compound into real transformation.</li>
                                                <li style="margin-bottom: 10px;"><strong>Reflect</strong> — Your coach, your journal, your progress. All in one place.</li>
                                            </ul>
                                            
                                            <h2 style="margin: 30px 0 15px 0; font-size: 18px; color: #111827; font-weight: 600;">How to get the most from it</h2>
                                            
                                            <ol style="margin: 0 0 20px 0; padding-left: 20px; font-size: 16px; color: #374151; line-height: 1.6;">
                                                <li style="margin-bottom: 10px;"><strong>Set your first goal today</strong> — Not ten. One. Make it about who you want to become, not just what you want to finish.</li>
                                                <li style="margin-bottom: 10px;"><strong>Check in each morning</strong> — Two minutes to set your intention.</li>
                                                <li style="margin-bottom: 10px;"><strong>Review each evening</strong> — Two minutes to ask: did my actions match who I'm becoming?</li>
                                                <li style="margin-bottom: 10px;"><strong>Use your AI coach when stuck</strong> — Don't stay stuck.</li>
                                            </ol>
                                            
                                            <h2 style="margin: 30px 0 15px 0; font-size: 18px; color: #111827; font-weight: 600;">One thing before you go</h2>
                                            
                                            <p style="margin: 0 0 20px 0; font-size: 16px; color: #374151; line-height: 1.6;">
                                                Building discipline is hard work. But you don't do it alone.
                                            </p>
                                            
                                            <p style="margin: 0 0 20px 0; font-size: 16px; color: #374151; line-height: 1.6;">
                                                I'm building this in public. If something isn't working, tell me. If this helps you, share it with someone else who's trying to get better.
                                            </p>
                                            
                                            <p style="margin: 0 0 30px 0; font-size: 16px; color: #374151; line-height: 1.6;">
                                                Connect with me: 
                                                <a href="https://www.linkedin.com/in/pelumiolawole/" style="color: #111827; text-decoration: underline;">LinkedIn</a> | 
                                                <a href="https://instagram.com/peluolawole" style="color: #111827; text-decoration: underline;">Instagram</a> | 
                                                <a href="https://x.com/peluolawole" style="color: #111827; text-decoration: underline;">X</a>
                                            </p>
                                            
                                            <p style="margin: 0 0 5px 0; font-size: 16px; color: #374151; line-height: 1.6;">
                                                Let's get to work.
                                            </p>
                                            
                                            <p style="margin: 0; font-size: 16px; color: #374151;">
                                                — Pelumi Olawole(Coach PO)
                                            </p>
                                            
                                            <p style="margin: 30px 0 0 0; padding-top: 20px; border-top: 1px solid #e5e7eb; font-size: 14px; color: #6b7280; font-style: italic;">
                                                P.S. — Your first goal doesn't need to be big. It needs to be clear. Who are you becoming?
                                            </p>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>
                    </table>
                </body>
                </html>
                """,
            })
            
            logger.info("welcome_email_sent", email=to_email, message_id=response.get('id'))
            return True
            
        except Exception as e:
            logger.error("welcome_email_failed", email=to_email, error=str(e))
            return False

    # ─── Verification Reminder ──────────────────────────────────────────────

    async def send_verification_reminder(self, to_email: str, first_name: str, verification_url: str) -> bool:
        """Send reminder email after 24 hours if not verified"""
        if not self.enabled:
            return False

        try:
            response = resend.Emails.send({
                "from": self.from_header,
                "to": to_email,
                "subject": "Your OneGoal verification link expires soon",
                "html": f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <title>Verify your email</title>
                </head>
                <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #f5f5f5;">
                    <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f5f5f5; padding: 40px 0;">
                        <tr>
                            <td align="center">
                                <table width="600" cellpadding="0" cellspacing="0" style="background-color: #ffffff; border-radius: 8px; overflow: hidden; max-width: 600px; width: 100%;">
                                    <tr>
                                        <td style="padding: 40px;">
                                            <p style="margin: 0 0 20px 0; font-size: 16px; color: #374151; line-height: 1.6;">
                                                Hi {first_name or "there"},
                                            </p>
                                            
                                            <p style="margin: 0 0 20px 0; font-size: 16px; color: #374151; line-height: 1.6;">
                                                You started something yesterday. Most people never do.
                                            </p>
                                            
                                            <p style="margin: 0 0 20px 0; font-size: 16px; color: #374151; line-height: 1.6;">
                                                Your verification link expires in a few hours. Click below to confirm your email and get started.
                                            </p>
                                            
                                            <table width="100%" cellpadding="0" cellspacing="0" style="margin: 30px 0;">
                                                <tr>
                                                    <td align="center">
                                                        <a href="{verification_url}" style="display: inline-block; padding: 14px 32px; background-color: #111827; color: #ffffff; text-decoration: none; border-radius: 6px; font-size: 16px; font-weight: 500;">
                                                            Confirm email address
                                                        </a>
                                                    </td>
                                                </tr>
                                            </table>
                                            
                                            <p style="margin: 0; font-size: 14px; color: #6b7280; line-height: 1.6;">
                                                If you didn't sign up for OneGoal, ignore this email.
                                            </p>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>
                    </table>
                </body>
                </html>
                """,
            })
            
            logger.info("verification_reminder_sent", email=to_email)
            return True
            
        except Exception as e:
            logger.error("verification_reminder_failed", email=to_email, error=str(e))
            return False

    # ─── Password Reset (EXISTING - unchanged) ──────────────────────────────

    async def send_password_reset(self, to_email: str, reset_token: str) -> bool:
        """
        Send password reset email with magic link.
        Returns True if sent successfully, False otherwise.
        """
        if not self.enabled:
            logger.warning("email_disabled", reason="no_api_key", email=to_email)
            if settings.is_development:
                logger.info("dev_reset_token", email=to_email, token=reset_token)
            return False

        reset_url = f"{settings.password_reset_frontend_url}?token={reset_token}"
        
        try:
            response = resend.Emails.send({
                "from": self.from_address,
                "to": to_email,
                "subject": "Reset your OneGoal password",
                "html": f"""
                <div style="font-family: system-ui, sans-serif; max-width: 480px; margin: 0 auto; padding: 40px 20px;">
                    <h2 style="color: #F59E0B; margin-bottom: 24px;">Reset your password</h2>
                    <p style="color: #4A4A4A; line-height: 1.6; margin-bottom: 24px;">
                        You requested a password reset for your OneGoal account. 
                        Click the button below to set a new password. This link expires in 24 hours.
                    </p>
                    <a href="{reset_url}" 
                       style="display: inline-block; background: #F59E0B; color: #0A0908; 
                              padding: 14px 28px; text-decoration: none; border-radius: 8px;
                              font-weight: 600; margin-bottom: 24px;">
                        Reset Password
                    </a>
                    <p style="color: #7A6E65; font-size: 14px; line-height: 1.5;">
                        If you didn't request this, you can safely ignore this email. 
                        Your password won't change until you click the link above.
                    </p>
                    <hr style="border: none; border-top: 1px solid #E8E2DC; margin: 32px 0;">
                    <p style="color: #A09690; font-size: 12px;">
                        One Goal. One identity. One day at a time.
                    </p>
                </div>
                """,
                "text": f"""
Reset your OneGoal password

You requested a password reset. Visit this link to set a new password:
{reset_url}

This link expires in 24 hours.

If you didn't request this, ignore this email.
                """,
            })
            
            logger.info("password_reset_email_sent", 
                       email=to_email, 
                       message_id=response.get('id'))
            return True
            
        except Exception as e:
            logger.error("password_reset_email_failed", 
                        email=to_email, 
                        error=str(e))
            return False


# Singleton instance
email_service = EmailService()