"""
services/billing.py

Stripe billing integration for subscription management.
"""

import os
from datetime import datetime
from typing import Optional

import stripe
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# Initialize Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")

# Price IDs from Stripe Dashboard (set these in env vars)
PRICE_IDS = {
    "forge_monthly": os.getenv("STRIPE_PRICE_FORGE_MONTHLY", ""),
    "forge_annual": os.getenv("STRIPE_PRICE_FORGE_ANNUAL", ""),
    "identity_monthly": os.getenv("STRIPE_PRICE_IDENTITY_MONTHLY", ""),
    "identity_annual": os.getenv("STRIPE_PRICE_IDENTITY_ANNUAL", ""),
}

PLAN_LIMITS = {
    "spark": {
        "coach_messages_per_day": 5,
        "has_weekly_reviews": False,
        "has_advanced_analytics": False,
    },
    "forge": {
        "coach_messages_per_day": float("inf"),
        "has_weekly_reviews": True,
        "has_advanced_analytics": True,
    },
    "identity": {
        "coach_messages_per_day": float("inf"),
        "has_weekly_reviews": True,
        "has_advanced_analytics": True,
        "has_priority_support": True,
        "has_re_interview": True,
    },
}


class BillingService:
    """Handle Stripe billing operations."""

    def __init__(self):
        self.stripe = stripe

    async def create_checkout_session(
        self,
        user_id: str,
        user_email: str,
        plan: str,  # "forge" or "identity"
        billing_cycle: str,  # "monthly" or "annual"
        success_url: str,
        cancel_url: str,
    ) -> dict:
        """Create Stripe Checkout session for subscription."""
        
        price_key = f"{plan}_{billing_cycle}"
        price_id = PRICE_IDS.get(price_key)
        
        if not price_id:
            raise ValueError(f"Invalid plan or billing cycle: {price_key}")

        try:
            # Create or get Stripe customer
            customer = await self._get_or_create_customer(user_id, user_email)
            
            # Create checkout session
            session = self.stripe.checkout.Session.create(
                customer=customer["id"],
                payment_method_types=["card"],
                line_items=[{
                    "price": price_id,
                    "quantity": 1,
                }],
                mode="subscription",
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={
                    "user_id": user_id,
                    "plan": plan,
                },
                subscription_data={
                    "metadata": {
                        "user_id": user_id,
                        "plan": plan,
                    }
                },
            )
            
            logger.info(
                "checkout_session_created",
                user_id=user_id,
                plan=plan,
                session_id=session.id,
            )
            
            return {
                "session_id": session.id,
                "url": session.url,
            }

        except stripe.error.StripeError as e:
            logger.error("stripe_checkout_error", user_id=user_id, error=str(e))
            raise

    async def create_customer_portal_session(
        self,
        user_id: str,
        stripe_customer_id: str,
        return_url: str,
    ) -> dict:
        """Create Stripe Customer Portal session for managing subscription."""
        
        try:
            session = self.stripe.billing_portal.Session.create(
                customer=stripe_customer_id,
                return_url=return_url,
            )
            
            return {"url": session.url}
            
        except stripe.error.StripeError as e:
            logger.error("portal_session_error", user_id=user_id, error=str(e))
            raise

    async def handle_webhook(
        self,
        payload: bytes,
        sig_header: str,
        db: AsyncSession,
    ) -> bool:
        """Process Stripe webhook events."""
        
        try:
            event = self.stripe.Webhook.construct_event(
                payload, sig_header, os.getenv("STRIPE_WEBHOOK_SECRET")
            )
        except ValueError:
            logger.error("stripe_webhook_invalid_payload")
            return False
        except stripe.error.SignatureVerificationError:
            logger.error("stripe_webhook_invalid_signature")
            return False

        event_type = event["type"]
        data = event["data"]["object"]
        
        logger.info("stripe_webhook_received", type=event_type)

        if event_type == "checkout.session.completed":
            await self._handle_subscription_created(data, db)
        
        elif event_type == "invoice.paid":
            await self._handle_invoice_paid(data, db)
        
        elif event_type == "invoice.payment_failed":
            await self._handle_payment_failed(data, db)
        
        elif event_type == "customer.subscription.deleted":
            await self._handle_subscription_cancelled(data, db)
        
        elif event_type == "customer.subscription.updated":
            await self._handle_subscription_updated(data, db)

        return True

    async def _get_or_create_customer(
        self,
        user_id: str,
        email: str,
    ) -> dict:
        """Get existing Stripe customer or create new one."""
        
        # Search for existing customer by email
        customers = self.stripe.Customer.list(email=email, limit=1)
        
        if customers.data:
            customer = customers.data[0]
            # Update metadata if needed
            if customer.metadata.get("user_id") != user_id:
                customer = self.stripe.Customer.modify(
                    customer.id,
                    metadata={"user_id": user_id},
                )
            return customer
        
        # Create new customer
        return self.stripe.Customer.create(
            email=email,
            metadata={"user_id": user_id},
        )

    async def _handle_subscription_created(
        self,
        session: dict,
        db: AsyncSession,
    ) -> None:
        """Handle successful checkout — subscription created."""
        
        user_id = session.get("metadata", {}).get("user_id")
        plan = session.get("metadata", {}).get("plan")
        
        if not user_id or not plan:
            logger.error("checkout_missing_metadata", session_id=session.get("id"))
            return

        # Get subscription details
        subscription_id = session.get("subscription")
        subscription = self.stripe.Subscription.retrieve(subscription_id)
        
        # Update user record
        await db.execute(
            text("""
                UPDATE users
                SET 
                    subscription_plan = :plan,
                    subscription_status = :status,
                    stripe_customer_id = :customer_id,
                    stripe_subscription_id = :subscription_id,
                    current_period_start = :period_start,
                    current_period_end = :period_end,
                    subscription_updated_at = NOW()
                WHERE id = :user_id
            """),
            {
                "user_id": user_id,
                "plan": plan,
                "status": subscription.status,  # active, trialing, etc.
                "customer_id": session.get("customer"),
                "subscription_id": subscription_id,
                "period_start": datetime.fromtimestamp(subscription.current_period_start),
                "period_end": datetime.fromtimestamp(subscription.current_period_end),
            },
        )
        
        logger.info("subscription_activated", user_id=user_id, plan=plan)

    async def _handle_invoice_paid(self, invoice: dict, db: AsyncSession) -> None:
        """Handle successful recurring payment."""
        
        subscription_id = invoice.get("subscription")
        if not subscription_id:
            return
        
        # Update period dates
        subscription = self.stripe.Subscription.retrieve(subscription_id)
        
        await db.execute(
            text("""
                UPDATE users
                SET 
                    current_period_start = :period_start,
                    current_period_end = :period_end,
                    subscription_status = 'active',
                    subscription_updated_at = NOW()
                WHERE stripe_subscription_id = :subscription_id
            """),
            {
                "subscription_id": subscription_id,
                "period_start": datetime.fromtimestamp(subscription.current_period_start),
                "period_end": datetime.fromtimestamp(subscription.current_period_end),
            },
        )
        
        logger.info("subscription_renewed", subscription_id=subscription_id)

    async def _handle_payment_failed(self, invoice: dict, db: AsyncSession) -> None:
        """Handle failed payment — mark for retry."""
        
        subscription_id = invoice.get("subscription")
        
        await db.execute(
            text("""
                UPDATE users
                SET subscription_status = 'past_due'
                WHERE stripe_subscription_id = :subscription_id
            """),
            {"subscription_id": subscription_id},
        )
        
        logger.warning("payment_failed", subscription_id=subscription_id)

    async def _handle_subscription_cancelled(
        self,
        subscription: dict,
        db: AsyncSession,
    ) -> None:
        """Handle subscription cancellation (end of period)."""
        
        subscription_id = subscription.get("id")
        
        await db.execute(
            text("""
                UPDATE users
                SET 
                    subscription_status = 'cancelled',
                    subscription_plan = 'spark',
                    subscription_updated_at = NOW()
                WHERE stripe_subscription_id = :subscription_id
            """),
            {"subscription_id": subscription_id},
        )
        
        logger.info("subscription_cancelled", subscription_id=subscription_id)

    async def _handle_subscription_updated(
        self,
        subscription: dict,
        db: AsyncSession,
    ) -> None:
        """Handle subscription changes (plan changes, etc.)."""
        
        subscription_id = subscription.get("id")
        status = subscription.get("status")
        
        await db.execute(
            text("""
                UPDATE users
                SET 
                    subscription_status = :status,
                    subscription_updated_at = NOW()
                WHERE stripe_subscription_id = :subscription_id
            """),
            {
                "subscription_id": subscription_id,
                "status": status,
            },
        )
        
        logger.info("subscription_updated", subscription_id=subscription_id, status=status)

    def check_quota(
        self,
        user_plan: str,
        usage_type: str,
        current_usage: int,
    ) -> bool:
        """Check if user has quota remaining for feature."""
        
        limits = PLAN_LIMITS.get(user_plan, PLAN_LIMITS["spark"])
        
        if usage_type == "coach_message":
            return current_usage < limits["coach_messages_per_day"]
        
        if usage_type == "weekly_review":
            return limits.get("has_weekly_reviews", False)
        
        return True


# Singleton instance
billing_service = BillingService()