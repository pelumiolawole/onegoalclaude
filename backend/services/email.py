"""
services/email.py

Email service using Resend API for transactional emails.
Handles verification, password reset, and welcome emails.
"""

import asyncio
from datetime import datetime, timezone

import resend
import structlog

from core.config import settings

logger = structlog.get_logger()


class EmailService:
    def __init__(self):
        self.api_key = settings.resend_api_key
        self.from_address = settings.email_from_address
        self.from_name = settings.email_from_name
        self.frontend_url = settings.frontend_url
        
        # Initialize Resend client
        if self.api_key:
            resend.api_key = self.api_key

    async def send_verification_email(
        self,
        to_email: str,
        first_name: str | None,
        verification_url: str,
    ) -> dict:
        """
        Send email verification link to new users.
        """
        if not self.api_key:
            logger.warning("email_service_disabled", reason="no_api_key")
            return {"id": "mock-email-id", "status": "mock"}

        name = first_name or "there"
        
        subject = "Confirm your email"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Confirm your email</title>
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #1a1a1a; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: #fafafa; padding: 40px 20px; text-align: center; border-bottom: 3px solid #0d9488;">
                <h1 style="margin: 0; font-size: 28px; font-weight: 700; color: #0d9488;">One Goal</h1>
                <p style="margin: 10px 0 0 0; color: #666; font-size: 14px;">One identity. One day at a time.</p>
            </div>
            
            <div style="background: white; padding: 40px 30px; border-radius: 0 0 8px 8px;">
                <p style="font-size: 18px; margin-bottom: 20px;">Hi {name},</p>
                
                <p>Thanks for signing up. You're one step away from starting your transformation.</p>
                
                <p>Click the button below to verify your email and begin your onboarding:</p>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{verification_url}" style="display: inline-block; background: #0d9488; color: white; padding: 14px 32px; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 16px;">Verify Email</a>
                </div>
                
                <p style="color: #666; font-size: 14px;">Or copy this link:<br>
                <code style="background: #f5f5f5; padding: 8px 12px; border-radius: 4px; word-break: break-all;">{verification_url}</code></p>
                
                <p style="color: #666; font-size: 14px; margin-top: 30px;">This link expires in 24 hours. If you didn't sign up, you can ignore this email.</p>
                
                <hr style="border: none; border-top: 1px solid #e5e5e5; margin: 30px 0;">
                
                <p style="color: #999; font-size: 13px; text-align: center;">
                    One Goal Pro<br>
                    <a href="https://onegoalpro.vercel.app" style="color: #0d9488;">onegoalpro.vercel.app</a>
                </p>
            </div>
        </body>
        </html>
        """

        try:
            params = {
                "from": f"{self.from_name} <{self.from_address}>",
                "to": [to_email],
                "subject": subject,
                "html": html_content,
            }
            
            response = await asyncio.to_thread(resend.Emails.send, params)
            
            logger.info(
                "verification_email_sent",
                email=to_email,
                message_id=response.get("id"),
            )
            
            return response
            
        except Exception as e:
            logger.error(
                "verification_email_failed",
                email=to_email,
                error=str(e),
            )
            raise

    async def send_welcome_email(
        self,
        to_email: str,
        display_name: str | None,
    ) -> dict:
        """
        Send welcome email after email verification.
        """
        if not self.api_key:
            logger.warning("email_service_disabled", reason="no_api_key")
            return {"id": "mock-email-id", "status": "mock"}

        name = display_name or "there"
        
        subject = "You're in — let's talk about who you're becoming"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Welcome to One Goal</title>
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #1a1a1a; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: #fafafa; padding: 40px 20px; text-align: center; border-bottom: 3px solid #0d9488;">
                <h1 style="margin: 0; font-size: 28px; font-weight: 700; color: #0d9488;">One Goal</h1>
                <p style="margin: 10px 0 0 0; color: #666; font-size: 14px;">One identity. One day at a time.</p>
            </div>
            
            <div style="background: white; padding: 40px 30px; border-radius: 0 0 8px 8px;">
                <p style="font-size: 18px; margin-bottom: 20px;">Hi {name},</p>
                
                <p>You signed up. That already puts you ahead of most people who just think about getting better.</p>
                
                <h2 style="color: #0d9488; font-size: 20px; margin-top: 30px;">Why I built this</h2>
                <p>I've spent nearly a decade watching talented people stay stuck. Not because they lacked ambition. Because they were chasing too many things at once, measuring themselves by what they <em>did</em> each day instead of who they were <em>becoming</em>.</p>
                
                <p>OneGoal is built on a simple belief: <strong>identity before strategy, to-be over to-do.</strong> You don't need another task list. You need a system that shapes the person who gets the results.</p>
                
                <h2 style="color: #0d9488; font-size: 20px; margin-top: 30px;">What this helps you do</h2>
                <ul style="padding-left: 20px;">
                    <li style="margin-bottom: 10px;"><strong>Focus</strong> — One priority. One direction. No more scattered energy.</li>
                    <li style="margin-bottom: 10px;"><strong>Build</strong> — Small daily actions that compound into real transformation.</li>
                    <li style="margin-bottom: 10px;"><strong>Reflect</strong> — Your coach, your journal, your progress. All in one place.</li>
                </ul>
                
                <h2 style="color: #0d9488; font-size: 20px; margin-top: 30px;">How to get the most from it</h2>
                <ol style="padding-left: 20px;">
                    <li style="margin-bottom: 10px;"><strong>Set your first goal today</strong> — Not ten. One. Make it about who you want to become, not just what you want to finish.</li>
                    <li style="margin-bottom: 10px;"><strong>Check in each morning</strong> — Two minutes to set your intention.</li>
                    <li style="margin-bottom: 10px;"><strong>Review each evening</strong> — Two minutes to ask: did my actions match who I'm becoming?</li>
                    <li style="margin-bottom: 10px;"><strong>Use your AI coach when stuck</strong> — Don't stay stuck.</li>
                </ol>
                
                <h2 style="color: #0d9488; font-size: 20px; margin-top: 30px;">One thing before you go</h2>
                <p>Building discipline is hard work. But you don't do it alone.</p>
                
                <p>I'm building this in public. If something isn't working, tell me. If this helps you, share it with someone else who's trying to get better.</p>
                
                <p>Connect with me:<br>
                <a href="https://linkedin.com/in/pelumiolawole" style="color: #0d9488;">LinkedIn</a> | 
                <a href="https://instagram.com/pelumi.olawole" style="color: #0d9488;">Instagram</a> | 
                <a href="https://x.com/pelumiolawole" style="color: #0d9488;">X</a></p>
                
                <p>Let's get to work.</p>
                
                <p>— Pelumi (Coach PO)</p>
                
                <p style="color: #666; font-size: 14px; margin-top: 20px; padding-top: 20px; border-top: 1px solid #e5e5e5;">
                    <strong>P.S.</strong> — Your first goal doesn't need to be big. It needs to be clear. Who are you becoming?
                </p>
            </div>
        </body>
        </html>
        """

        try:
            params = {
                "from": f"{self.from_name} <{self.from_address}>",
                "to": [to_email],
                "subject": subject,
                "html": html_content,
            }
            
            response = await asyncio.to_thread(resend.Emails.send, params)
            
            logger.info(
                "welcome_email_sent",
                email=to_email,
                message_id=response.get("id"),
            )
            
            return response
            
        except Exception as e:
            logger.error(
                "welcome_email_failed",
                email=to_email,
                error=str(e),
            )
            raise

    async def send_password_reset(
        self,
        to_email: str,
        reset_token: str,
    ) -> dict:
        """
        Send password reset email.
        """
        if not self.api_key:
            logger.warning("email_service_disabled", reason="no_api_key")
            return {"id": "mock-email-id", "status": "mock"}

        reset_url = f"{settings.password_reset_frontend_url}?token={reset_token}"
        
        subject = "Reset your password"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Reset your password</title>
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #1a1a1a; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: #fafafa; padding: 40px 20px; text-align: center; border-bottom: 3px solid #0d9488;">
                <h1 style="margin: 0; font-size: 28px; font-weight: 700; color: #0d9488;">One Goal</h1>
                <p style="margin: 10px 0 0 0; color: #666; font-size: 14px;">One identity. One day at a time.</p>
            </div>
            
            <div style="background: white; padding: 40px 30px; border-radius: 0 0 8px 8px;">
                <h2 style="margin-top: 0;">Reset your password</h2>
                
                <p>You requested a password reset for your OneGoal account.</p>
                
                <p>Click the button below to set a new password. This link expires in 24 hours.</p>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{reset_url}" style="display: inline-block; background: #0d9488; color: white; padding: 14px 32px; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 16px;">Reset Password</a>
                </div>
                
                <p style="color: #666; font-size: 14px;">If you didn't request this, you can safely ignore this email.<br>
                Your password won't change until you click the link above.</p>
                
                <hr style="border: none; border-top: 1px solid #