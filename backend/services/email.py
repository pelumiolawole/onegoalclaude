"""
services/email.py

Email delivery service using Resend.
Handles transactional emails: verification, welcome, password reset,
daily task notifications, and re-engagement.
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
                <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #0A0908;">
                    <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #0A0908; padding: 40px 0;">
                        <tr>
                            <td align="center">
                                <table width="600" cellpadding="0" cellspacing="0" style="background-color: #141210; border-radius: 12px; overflow: hidden; max-width: 600px; width: 100%; border: 1px solid #2A2520;">
                                    <tr>
                                        <td style="padding: 8px 40px; background-color: #F59E0B;">
                                            <p style="margin: 0; font-size: 13px; font-weight: 600; color: #0A0908; letter-spacing: 0.1em; text-transform: uppercase;">OneGoal Pro</p>
                                        </td>
                                    </tr>
                                    <tr>
                                        <td style="padding: 40px;">
                                            <h1 style="margin: 0 0 20px 0; font-size: 24px; color: #F5F1ED; font-weight: 600;">Confirm your email</h1>

                                            <p style="margin: 0 0 20px 0; font-size: 16px; color: #A09690; line-height: 1.6;">
                                                Hi {first_name or "there"},
                                            </p>

                                            <p style="margin: 0 0 20px 0; font-size: 16px; color: #A09690; line-height: 1.6;">
                                                You signed up for OneGoal Pro. Click below to confirm your email and start the interview.
                                            </p>

                                            <table width="100%" cellpadding="0" cellspacing="0" style="margin: 30px 0;">
                                                <tr>
                                                    <td align="center">
                                                        <a href="{verification_url}" style="display: inline-block; padding: 14px 32px; background-color: #F59E0B; color: #0A0908; text-decoration: none; border-radius: 8px; font-size: 16px; font-weight: 600;">
                                                            Confirm email address
                                                        </a>
                                                    </td>
                                                </tr>
                                            </table>

                                            <p style="margin: 0 0 10px 0; font-size: 14px; color: #5C524A; line-height: 1.6;">
                                                This link expires in 24 hours.
                                            </p>

                                            <p style="margin: 0 0 20px 0; font-size: 14px; color: #5C524A; line-height: 1.6;">
                                                If you didn't sign up for OneGoal Pro, you can ignore this email.
                                            </p>

                                            <p style="margin: 0; font-size: 13px; color: #3D3630; line-height: 1.6;">
                                                Button not working? Copy and paste this link:<br>
                                                <a href="{verification_url}" style="color: #5C524A; word-break: break-all;">{verification_url}</a>
                                            </p>
                                        </td>
                                    </tr>
                                    <tr>
                                        <td style="padding: 20px 40px; border-top: 1px solid #2A2520;">
                                            <p style="margin: 0; font-size: 12px; color: #3D3630;">One goal. Full commitment. No excuses.</p>
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

    # ─── Daily Task Email ────────────────────────────────────────────────────

    async def send_daily_task_email(
        self,
        to_email: str,
        display_name: Optional[str],
        task_title: str,
        task_description: str,
        identity_anchor: str,
        app_url: str,
    ) -> bool:
        """
        Send daily task notification email.
        Triggered by scheduler after task generation at user's local midnight.
        """
        if not self.enabled:
            logger.warning("daily_task_email_disabled", email=to_email)
            return False

        name = display_name or "there"
        dashboard_url = f"{app_url}/dashboard"

        try:
            response = resend.Emails.send({
                "from": self.from_header,
                "to": to_email,
                "subject": f"Your identity task for today — {task_title}",
                "html": f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <title>Your task for today</title>
                </head>
                <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #0A0908;">
                    <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #0A0908; padding: 40px 0;">
                        <tr>
                            <td align="center">
                                <table width="600" cellpadding="0" cellspacing="0" style="background-color: #141210; border-radius: 12px; overflow: hidden; max-width: 600px; width: 100%; border: 1px solid #2A2520;">
                                    <!-- Header bar -->
                                    <tr>
                                        <td style="padding: 8px 40px; background-color: #F59E0B;">
                                            <p style="margin: 0; font-size: 13px; font-weight: 600; color: #0A0908; letter-spacing: 0.1em; text-transform: uppercase;">OneGoal Pro</p>
                                        </td>
                                    </tr>

                                    <!-- Identity anchor -->
                                    <tr>
                                        <td style="padding: 24px 40px 0 40px;">
                                            <p style="margin: 0; font-size: 12px; color: #5C524A; letter-spacing: 0.08em; text-transform: uppercase;">You are becoming</p>
                                            <p style="margin: 6px 0 0 0; font-size: 15px; color: #F59E0B; font-style: italic; line-height: 1.4;">{identity_anchor}</p>
                                        </td>
                                    </tr>

                                    <!-- Main content -->
                                    <tr>
                                        <td style="padding: 24px 40px 32px 40px;">
                                            <p style="margin: 0 0 20px 0; font-size: 16px; color: #7A6E65; line-height: 1.6;">
                                                {name},
                                            </p>

                                            <p style="margin: 0 0 24px 0; font-size: 15px; color: #7A6E65; line-height: 1.6;">
                                                Your identity task for today:
                                            </p>

                                            <!-- Task card -->
                                            <table width="100%" cellpadding="0" cellspacing="0" style="margin: 0 0 28px 0;">
                                                <tr>
                                                    <td style="padding: 24px; background-color: #1E1B18; border-radius: 10px; border-left: 3px solid #F59E0B;">
                                                        <p style="margin: 0 0 10px 0; font-size: 18px; color: #F5F1ED; font-weight: 600; line-height: 1.3;">{task_title}</p>
                                                        <p style="margin: 0; font-size: 14px; color: #7A6E65; line-height: 1.6;">{task_description}</p>
                                                    </td>
                                                </tr>
                                            </table>

                                            <!-- CTA -->
                                            <table width="100%" cellpadding="0" cellspacing="0" style="margin: 0 0 28px 0;">
                                                <tr>
                                                    <td align="center">
                                                        <a href="{dashboard_url}" style="display: inline-block; padding: 14px 36px; background-color: #F59E0B; color: #0A0908; text-decoration: none; border-radius: 8px; font-size: 15px; font-weight: 600;">
                                                            Open dashboard →
                                                        </a>
                                                    </td>
                                                </tr>
                                            </table>

                                            <p style="margin: 0; font-size: 14px; color: #3D3630; line-height: 1.6; text-align: center;">
                                                One task. Do it. Then talk to your coach.
                                            </p>
                                        </td>
                                    </tr>

                                    <!-- Footer -->
                                    <tr>
                                        <td style="padding: 20px 40px; border-top: 1px solid #2A2520;">
                                            <p style="margin: 0; font-size: 12px; color: #3D3630; line-height: 1.6;">
                                                One goal. Full commitment. No excuses. —
                                                <a href="{dashboard_url}" style="color: #5C524A; text-decoration: none;">onegoalpro.app</a>
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

            logger.info("daily_task_email_sent", email=to_email, task=task_title, message_id=response.get('id'))
            return True

        except Exception as e:
            logger.error("daily_task_email_failed", email=to_email, error=str(e))
            return False

    # ─── Re-engagement Email ─────────────────────────────────────────────────

    async def send_reengagement_email(
        self,
        to_email: str,
        display_name: Optional[str],
        days_inactive: int,
        missed_tasks: int,
        app_url: str,
    ) -> bool:
        """
        Send re-engagement email to users who haven't logged in for 3+ days.
        """
        if not self.enabled:
            logger.warning("reengagement_email_disabled", email=to_email)
            return False

        name = display_name or "there"
        dashboard_url = f"{app_url}/dashboard"

        try:
            response = resend.Emails.send({
                "from": self.from_header,
                "to": to_email,
                "subject": f"You have {missed_tasks} task{'s' if missed_tasks != 1 else ''} waiting",
                "html": f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <title>You have tasks waiting</title>
                </head>
                <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #0A0908;">
                    <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #0A0908; padding: 40px 0;">
                        <tr>
                            <td align="center">
                                <table width="600" cellpadding="0" cellspacing="0" style="background-color: #141210; border-radius: 12px; overflow: hidden; max-width: 600px; width: 100%; border: 1px solid #2A2520;">
                                    <tr>
                                        <td style="padding: 8px 40px; background-color: #F59E0B;">
                                            <p style="margin: 0; font-size: 13px; font-weight: 600; color: #0A0908; letter-spacing: 0.1em; text-transform: uppercase;">OneGoal Pro</p>
                                        </td>
                                    </tr>
                                    <tr>
                                        <td style="padding: 40px;">
                                            <p style="margin: 0 0 20px 0; font-size: 16px; color: #7A6E65; line-height: 1.6;">
                                                {name},
                                            </p>

                                            <p style="margin: 0 0 20px 0; font-size: 16px; color: #A09690; line-height: 1.6;">
                                                It's been {days_inactive} days. Your goal hasn't moved — but it hasn't gone anywhere either.
                                            </p>

                                            <p style="margin: 0 0 28px 0; font-size: 16px; color: #A09690; line-height: 1.6;">
                                                You have <strong style="color: #F59E0B;">{missed_tasks} task{'s' if missed_tasks != 1 else ''}</strong> waiting. They were built for you. They're not going to complete themselves.
                                            </p>

                                            <table width="100%" cellpadding="0" cellspacing="0" style="margin: 0 0 28px 0;">
                                                <tr>
                                                    <td align="center">
                                                        <a href="{dashboard_url}" style="display: inline-block; padding: 14px 36px; background-color: #F59E0B; color: #0A0908; text-decoration: none; border-radius: 8px; font-size: 15px; font-weight: 600;">
                                                            Get back on track →
                                                        </a>
                                                    </td>
                                                </tr>
                                            </table>

                                            <p style="margin: 0; font-size: 14px; color: #3D3630; line-height: 1.6; text-align: center; font-style: italic;">
                                                The version of you that finishes this started again today.
                                            </p>
                                        </td>
                                    </tr>
                                    <tr>
                                        <td style="padding: 20px 40px; border-top: 1px solid #2A2520;">
                                            <p style="margin: 0; font-size: 12px; color: #3D3630;">
                                                One goal. Full commitment. No excuses. —
                                                <a href="{dashboard_url}" style="color: #5C524A; text-decoration: none;">onegoalpro.app</a>
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

            logger.info("reengagement_email_sent", email=to_email, days_inactive=days_inactive, message_id=response.get('id'))
            return True

        except Exception as e:
            logger.error("reengagement_email_failed", email=to_email, error=str(e))
            return False

    # ─── Welcome Email ───────────────────────────────────────────────────────

    async def send_welcome_email(self, to_email: str, display_name: Optional[str]) -> bool:
        """Send welcome email after verification"""
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
                    <title>Welcome to OneGoal Pro</title>
                </head>
                <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #0A0908;">
                    <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #0A0908; padding: 40px 0;">
                        <tr>
                            <td align="center">
                                <table width="600" cellpadding="0" cellspacing="0" style="background-color: #141210; border-radius: 12px; overflow: hidden; max-width: 600px; width: 100%; border: 1px solid #2A2520;">
                                    <tr>
                                        <td style="padding: 8px 40px; background-color: #F59E0B;">
                                            <p style="margin: 0; font-size: 13px; font-weight: 600; color: #0A0908; letter-spacing: 0.1em; text-transform: uppercase;">OneGoal Pro</p>
                                        </td>
                                    </tr>
                                    <tr>
                                        <td style="padding: 40px;">
                                            <p style="margin: 0 0 20px 0; font-size: 16px; color: #7A6E65; line-height: 1.6;">
                                                Hi {name},
                                            </p>

                                            <p style="margin: 0 0 20px 0; font-size: 16px; color: #A09690; line-height: 1.6;">
                                                You signed up. That already puts you ahead of most people who just think about getting better.
                                            </p>

                                            <h2 style="margin: 30px 0 15px 0; font-size: 18px; color: #F5F1ED; font-weight: 600;">Why I built this</h2>

                                            <p style="margin: 0 0 20px 0; font-size: 16px; color: #A09690; line-height: 1.6;">
                                                I've spent nearly a decade watching talented people stay stuck. Not because they lacked ambition. Because they were chasing too many things at once, measuring themselves by what they <em>did</em> each day instead of who they were <em>becoming</em>.
                                            </p>

                                            <p style="margin: 0 0 20px 0; font-size: 16px; color: #A09690; line-height: 1.6;">
                                                OneGoal Pro is built on a simple belief: <strong style="color: #F5F1ED;">identity before strategy. To-be over to-do.</strong>
                                            </p>

                                            <h2 style="margin: 30px 0 15px 0; font-size: 18px; color: #F5F1ED; font-weight: 600;">How to get the most from it</h2>

                                            <ol style="margin: 0 0 20px 0; padding-left: 20px; font-size: 15px; color: #A09690; line-height: 1.8;">
                                                <li style="margin-bottom: 10px;"><strong style="color: #F5F1ED;">Start the interview today</strong> — it takes 15 minutes and it asks questions most apps never do.</li>
                                                <li style="margin-bottom: 10px;"><strong style="color: #F5F1ED;">Do your daily task every morning</strong> — one thing, built for who you're becoming.</li>
                                                <li style="margin-bottom: 10px;"><strong style="color: #F5F1ED;">Use the coach when stuck</strong> — it knows your goal, your history, your patterns.</li>
                                            </ol>

                                            <p style="margin: 0 0 20px 0; font-size: 16px; color: #A09690; line-height: 1.6;">
                                                I'm building this in public. If something isn't working, tell me. If it helps you, share it.
                                            </p>

                                            <p style="margin: 0 0 5px 0; font-size: 16px; color: #7A6E65; line-height: 1.6;">
                                                Let's get to work.
                                            </p>

                                            <p style="margin: 0 0 30px 0; font-size: 16px; color: #7A6E65;">
                                                — Pelumi (Coach PO)
                                            </p>

                                            <p style="margin: 0; padding-top: 20px; border-top: 1px solid #2A2520; font-size: 13px; color: #3D3630; font-style: italic;">
                                                P.S. — Your first goal doesn't need to be big. It needs to be clear. Who are you becoming?
                                            </p>
                                        </td>
                                    </tr>
                                    <tr>
                                        <td style="padding: 20px 40px; border-top: 1px solid #2A2520;">
                                            <p style="margin: 0; font-size: 12px; color: #3D3630;">
                                                Connect:
                                                <a href="https://onegoalpro.app" style="color: #5C524A; text-decoration: none;">onegoalpro.app</a> ·
                                                <a href="mailto:hello@onegoalpro.app" style="color: #5C524A; text-decoration: none;">hello@onegoalpro.app</a>
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
                <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #0A0908;">
                    <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #0A0908; padding: 40px 0;">
                        <tr>
                            <td align="center">
                                <table width="600" cellpadding="0" cellspacing="0" style="background-color: #141210; border-radius: 12px; overflow: hidden; max-width: 600px; width: 100%; border: 1px solid #2A2520;">
                                    <tr>
                                        <td style="padding: 8px 40px; background-color: #F59E0B;">
                                            <p style="margin: 0; font-size: 13px; font-weight: 600; color: #0A0908; letter-spacing: 0.1em; text-transform: uppercase;">OneGoal Pro</p>
                                        </td>
                                    </tr>
                                    <tr>
                                        <td style="padding: 40px;">
                                            <p style="margin: 0 0 20px 0; font-size: 16px; color: #7A6E65; line-height: 1.6;">
                                                Hi {first_name or "there"},
                                            </p>

                                            <p style="margin: 0 0 20px 0; font-size: 16px; color: #A09690; line-height: 1.6;">
                                                You started something yesterday. Most people never do.
                                            </p>

                                            <p style="margin: 0 0 20px 0; font-size: 16px; color: #A09690; line-height: 1.6;">
                                                Your verification link expires soon. Click below to confirm your email and get started.
                                            </p>

                                            <table width="100%" cellpadding="0" cellspacing="0" style="margin: 30px 0;">
                                                <tr>
                                                    <td align="center">
                                                        <a href="{verification_url}" style="display: inline-block; padding: 14px 32px; background-color: #F59E0B; color: #0A0908; text-decoration: none; border-radius: 8px; font-size: 16px; font-weight: 600;">
                                                            Confirm email address
                                                        </a>
                                                    </td>
                                                </tr>
                                            </table>

                                            <p style="margin: 0; font-size: 14px; color: #3D3630; line-height: 1.6;">
                                                If you didn't sign up for OneGoal Pro, ignore this email.
                                            </p>
                                        </td>
                                    </tr>
                                    <tr>
                                        <td style="padding: 20px 40px; border-top: 1px solid #2A2520;">
                                            <p style="margin: 0; font-size: 12px; color: #3D3630;">One goal. Full commitment. No excuses.</p>
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

    # ─── Password Reset ──────────────────────────────────────────────────────

    async def send_password_reset(self, to_email: str, reset_token: str) -> bool:
        """Send password reset email with magic link."""
        if not self.enabled:
            logger.warning("email_disabled", reason="no_api_key", email=to_email)
            if settings.is_development:
                logger.info("dev_reset_token", email=to_email, token=reset_token)
            return False

        reset_url = f"{settings.password_reset_frontend_url}?token={reset_token}"

        try:
            response = resend.Emails.send({
                "from": self.from_header,
                "to": to_email,
                "subject": "Reset your OneGoal Pro password",
                "html": f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                </head>
                <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #0A0908;">
                    <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #0A0908; padding: 40px 0;">
                        <tr>
                            <td align="center">
                                <table width="600" cellpadding="0" cellspacing="0" style="background-color: #141210; border-radius: 12px; overflow: hidden; max-width: 600px; width: 100%; border: 1px solid #2A2520;">
                                    <tr>
                                        <td style="padding: 8px 40px; background-color: #F59E0B;">
                                            <p style="margin: 0; font-size: 13px; font-weight: 600; color: #0A0908; letter-spacing: 0.1em; text-transform: uppercase;">OneGoal Pro</p>
                                        </td>
                                    </tr>
                                    <tr>
                                        <td style="padding: 40px;">
                                            <h2 style="margin: 0 0 20px 0; font-size: 22px; color: #F5F1ED; font-weight: 600;">Reset your password</h2>
                                            <p style="margin: 0 0 20px 0; font-size: 15px; color: #A09690; line-height: 1.6;">
                                                You requested a password reset. Click below to set a new password. This link expires in 24 hours.
                                            </p>
                                            <table width="100%" cellpadding="0" cellspacing="0" style="margin: 30px 0;">
                                                <tr>
                                                    <td align="center">
                                                        <a href="{reset_url}" style="display: inline-block; padding: 14px 32px; background-color: #F59E0B; color: #0A0908; text-decoration: none; border-radius: 8px; font-size: 15px; font-weight: 600;">
                                                            Reset password
                                                        </a>
                                                    </td>
                                                </tr>
                                            </table>
                                            <p style="margin: 0; font-size: 13px; color: #3D3630; line-height: 1.6;">
                                                If you didn't request this, ignore this email. Your password won't change.
                                            </p>
                                        </td>
                                    </tr>
                                    <tr>
                                        <td style="padding: 20px 40px; border-top: 1px solid #2A2520;">
                                            <p style="margin: 0; font-size: 12px; color: #3D3630;">One goal. Full commitment. No excuses.</p>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>
                    </table>
                </body>
                </html>
                """,
                "text": f"Reset your OneGoal Pro password\n\nVisit this link:\n{reset_url}\n\nExpires in 24 hours. If you didn't request this, ignore this email.",
            })

            logger.info("password_reset_email_sent", email=to_email, message_id=response.get('id'))
            return True

        except Exception as e:
            logger.error("password_reset_email_failed", email=to_email, error=str(e))
            return False


# Singleton instance
email_service = EmailService()


async def send_interview_nudge_email(
    to_email: str,
    first_name: str,
    attempt: int,
) -> None:
    """Send interview completion nudge email. Attempt 1 = 24h, attempt 2 = 72h."""
    resend.api_key = settings.resend_api_key

    if attempt == 1:
        subject = "You started something. Don't leave it there."
        body_html = f"""
        <div style="font-family: Georgia, serif; max-width: 560px; margin: 0 auto; color: #1a1714; line-height: 1.7;">
          <p style="margin-bottom: 20px;">Hey {first_name},</p>

          <p>You signed up for OneGoal Pro yesterday.</p>

          <p>That tells me something. You're thinking about a goal. Something you want to change, build, or become. You haven't stopped thinking about it, which is exactly why you clicked.</p>

          <p>But you didn't finish the interview.</p>

          <p>I get it. Life moves fast. Maybe it felt like a lot. Maybe you weren't sure what to expect.</p>

          <p>Here's what the interview actually is: a conversation. Not a form. The AI asks real questions, pushes back when answers are vague, and by the end it hands you one goal. The real one. Not the one you default to when someone asks.</p>

          <p>It takes 10 to 15 minutes. You do it once. Everything after that is one task a day.</p>

          <p>That's the whole thing.</p>

          <p style="margin: 32px 0;">
            <a href="https://onegoalpro.app/onboarding/interview"
               style="background: #F59E0B; color: #0A0908; padding: 14px 28px; text-decoration: none; border-radius: 8px; font-family: sans-serif; font-weight: 600; font-size: 15px;">
              Start your interview →
            </a>
          </p>

          <p>Pelumi<br>
          <span style="color: #7A6E65; font-size: 14px;">Founder, OneGoal Pro</span></p>

          <p style="color: #7A6E65; font-size: 14px; border-top: 1px solid #eee; padding-top: 16px; margin-top: 32px;">
            P.S. If you have questions before you start, just reply. I read every one.
          </p>
        </div>
        """
    else:
        subject = "Still here when you're ready."
        body_html = f"""
        <div style="font-family: Georgia, serif; max-width: 560px; margin: 0 auto; color: #1a1714; line-height: 1.7;">
          <p style="margin-bottom: 20px;">Hey {first_name},</p>

          <p>Three days ago you signed up. The interview is still waiting.</p>

          <p>I'm not going to pressure you. But I'll say this.</p>

          <p>Every person who has gone through the interview says some version of the same thing: <em>"I didn't expect it to ask me that."</em> It goes somewhere most apps don't bother going.</p>

          <p>The question it's trying to answer isn't what do you want to achieve. It's who do you need to become to achieve it. Most people have never been asked that second question properly.</p>

          <p>If now's not the right time, I understand. But if you signed up because something needs to change, the interview is where that starts.</p>

          <p>10 to 15 minutes. One conversation. One goal on the other side.</p>

          <p style="margin: 32px 0;">
            <a href="https://onegoalpro.app/onboarding/interview"
               style="background: #F59E0B; color: #0A0908; padding: 14px 28px; text-decoration: none; border-radius: 8px; font-family: sans-serif; font-weight: 600; font-size: 15px;">
              Start your interview →
            </a>
          </p>

          <p>Pelumi<br>
          <span style="color: #7A6E65; font-size: 14px;">Founder, OneGoal Pro</span></p>

          <p style="color: #7A6E65; font-size: 14px; border-top: 1px solid #eee; padding-top: 16px; margin-top: 32px;">
            P.S. After this I won't keep nudging you. But I'm here if you want to talk first. Just reply.
          </p>
        </div>
        """

    resend.Emails.send({
        "from": "Pelumi at OneGoal Pro <pelumi@onegoalpro.app>",
        "to": to_email,
        "subject": subject,
        "html": body_html,
    })