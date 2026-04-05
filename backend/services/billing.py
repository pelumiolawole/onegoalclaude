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

# Reverse mapping: price ID -> plan name
PRICE_TO_PLAN = {
    PRICE_IDS["forge_monthly"]: "Forge",
    PRICE_IDS["forge_annual"]: "Forge",
    PRICE_IDS["identity_monthly"]: "Identity",
    PRICE_IDS["identity_annual"]: "Identity",
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

    def _normalize_subscription_status(self, stripe_status: str, cancel_at_period_end: bool) -> str:
        """
        Normalize Stripe subscription status to 'active' or 'ended'.

        cancel_at_period_end=True means the user SCHEDULED a cancellation —
        they still have paid access until current_period_end.  Returning 'ended'
        here would immediately revoke access, which is wrong.
        """
        if stripe_status in ["active", "trialing"]:
            return "active"  # User retains access even if cancel is scheduled
        return "ended"

    async def create_checkout_session(
        self,
        user_id: str,
        user_email: str,
        plan: str,
        billing_cycle: str,
        success_url: str,
        cancel_url: str,
    ) -> dict:
        """Create Stripe Checkout session for subscription."""

        price_key = f"{plan}_{billing_cycle}"
        price_id = PRICE_IDS.get(price_key)

        if not price_id:
            raise ValueError(f"Invalid plan or billing cycle: {price_key}")

        try:
            customer = await self._get_or_create_customer(user_id, user_email)

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

    async def verify_checkout_session(
        self,
        session_id: str,
        user_id: str,
    ) -> dict:
        """Verify a completed Stripe checkout session and return subscription status."""
        try:
            session = self.stripe.checkout.Session.retrieve(
                session_id,
                expand=["subscription"],
            )

            if session.payment_status != "paid":
                return {"verified": False, "reason": "Payment not completed"}

            if session.metadata.get("user_id") != user_id:
                return {"verified": False, "reason": "Session does not belong to this user"}

            plan = session.metadata.get("plan", "unknown")

            return {
                "verified": True,
                "plan": plan,
                "status": "active",
            }

        except stripe.error.StripeError as e:
            logger.error("verify_session_error", session_id=session_id, error=str(e))
            return {"verified": False, "reason": "Stripe error"}

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

    async def cancel_subscription(
        self,
        subscription_id: str,
        db: AsyncSession,
    ) -> bool:
        """Cancel subscription at period end."""

        try:
            self.stripe.Subscription.modify(
                subscription_id,
                cancel_at_period_end=True
            )

            # User retains active access until period_end — only flag the scheduled cancel
            await db.execute(
                text("""
                    UPDATE users
                    SET subscription_status = 'active',
                        cancel_at_period_end = true,
                        subscription_updated_at = NOW()
                    WHERE stripe_subscription_id = :subscription_id
                """),
                {"subscription_id": subscription_id}
            )

            await db.execute(
                text("""
                    UPDATE subscriptions
                    SET status = 'active',
                        cancel_at_period_end = true,
                        updated_at = NOW()
                    WHERE stripe_subscription_id = :subscription_id
                """),
                {"subscription_id": subscription_id}
            )

            await db.commit()

            logger.info("subscription_cancel_scheduled", subscription_id=subscription_id)
            return True

        except stripe.error.StripeError as e:
            logger.error("cancel_subscription_error", error=str(e))
            return False

    async def reactivate_subscription(
        self,
        subscription_id: str,
        db: AsyncSession,
    ) -> bool:
        """Reactivate a subscription that was scheduled to cancel."""

        try:
            self.stripe.Subscription.modify(
                subscription_id,
                cancel_at_period_end=False
            )

            await db.execute(
                text("""
                    UPDATE users
                    SET subscription_status = 'active',
                        cancel_at_period_end = false,
                        subscription_updated_at = NOW()
                    WHERE stripe_subscription_id = :subscription_id
                """),
                {"subscription_id": subscription_id}
            )

            await db.execute(
                text("""
                    UPDATE subscriptions
                    SET status = 'active',
                        cancel_at_period_end = false,
                        updated_at = NOW()
                    WHERE stripe_subscription_id = :subscription_id
                """),
                {"subscription_id": subscription_id}
            )

            await db.commit()

            logger.info("subscription_reactivated", subscription_id=subscription_id)
            return True

        except stripe.error.StripeError as e:
            logger.error("reactivate_subscription_error", error=str(e))
            return False

    async def get_invoices(self, stripe_customer_id: str) -> list:
        """Get list of invoices for a customer with readable plan names."""
        try:
            invoices = self.stripe.Invoice.list(
                customer=stripe_customer_id,
                limit=24,
                status='paid',
                expand=['data.subscription']
            )

            result = []
            for inv in invoices.data:
                plan_name = self._get_plan_name_from_invoice(inv)

                result.append({
                    "id": inv.id,
                    "amount_due": inv.amount_due,
                    "amount_paid": inv.amount_paid,
                    "status": inv.status,
                    "created": inv.created,
                    "invoice_pdf": inv.invoice_pdf,
                    "description": f"Subscription - {plan_name}",
                })

            return result

        except self.stripe.error.StripeError as e:
            logger.error("Failed to fetch invoices", error=str(e))
            return []

    def _get_plan_name_from_invoice(self, inv) -> str:
        """Extract plan name from invoice data."""
        if hasattr(inv, 'subscription') and inv.subscription:
            if isinstance(inv.subscription, stripe.Subscription):
                plan = inv.subscription.metadata.get('plan', '')
                if plan:
                    return plan.title()

        try:
            if inv.lines and inv.lines.data:
                line = inv.lines.data[0]
                price_id = None

                if hasattr(line, 'price') and line.price:
                    price_id = line.price.id
                elif hasattr(line, 'plan') and line.plan:
                    price_id = line.plan.id

                if price_id and price_id in PRICE_TO_PLAN:
                    return PRICE_TO_PLAN[price_id]
        except Exception:
            pass

        if inv.billing_reason:
            reason = inv.billing_reason.replace('subscription_', '').replace('_', ' ')
            return reason.title()

        return "Plan"

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

        handlers = {
            "checkout.session.completed": self._handle_subscription_created,
            "invoice.paid": self._handle_invoice_paid,
            "invoice.payment_failed": self._handle_payment_failed,
            "customer.subscription.deleted": self._handle_subscription_cancelled,
            "customer.subscription.updated": self._handle_subscription_updated,
        }

        handler = handlers.get(event_type)
        if handler:
            try:
                await handler(data, db)
            except Exception as e:
                logger.error(
                    "webhook_handler_error",
                    event_type=event_type,
                    error=str(e),
                    exc_info=True,
                )
                # Return True so Stripe doesn't retry — log the error for investigation
                return True

        return True

    async def _get_or_create_customer(
        self,
        user_id: str,
        email: str,
    ) -> dict:
        """Get existing Stripe customer or create new one."""

        customers = self.stripe.Customer.list(email=email, limit=1)

        if customers.data:
            customer = customers.data[0]
            if customer.metadata.get("user_id") != user_id:
                customer = self.stripe.Customer.modify(
                    customer.id,
                    metadata={"user_id": user_id},
                )
            return customer

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

        subscription_id = session.get("subscription")
        customer_id = session.get("customer")
        subscription = self.stripe.Subscription.retrieve(subscription_id)

        period_start = datetime.fromtimestamp(subscription.current_period_start)
        period_end = datetime.fromtimestamp(subscription.current_period_end)

        # Update users table (existing behaviour)
        await db.execute(
            text("""
                UPDATE users
                SET
                    subscription_plan = :plan,
                    subscription_status = 'active',
                    stripe_customer_id = :customer_id,
                    stripe_subscription_id = :subscription_id,
                    current_period_start = :period_start,
                    current_period_end = :period_end,
                    cancel_at_period_end = false,
                    subscription_updated_at = NOW()
                WHERE id = CAST(:user_id AS uuid)
            """),
            {
                "user_id": user_id,
                "plan": plan,
                "customer_id": customer_id,
                "subscription_id": subscription_id,
                "period_start": period_start,
                "period_end": period_end,
            },
        )

        # Also write to subscriptions table
        await db.execute(
            text("""
                INSERT INTO subscriptions (user_id, plan, status, stripe_customer_id, stripe_subscription_id, current_period_start, current_period_end, cancel_at_period_end)
                VALUES (CAST(:user_id AS uuid), :plan, 'active', :customer_id, :subscription_id, :period_start, :period_end, false)
                ON CONFLICT (user_id) DO UPDATE SET
                    plan = EXCLUDED.plan,
                    status = 'active',
                    stripe_customer_id = EXCLUDED.stripe_customer_id,
                    stripe_subscription_id = EXCLUDED.stripe_subscription_id,
                    current_period_start = EXCLUDED.current_period_start,
                    current_period_end = EXCLUDED.current_period_end,
                    cancel_at_period_end = false,
                    updated_at = NOW()
            """),
            {
                "user_id": user_id,
                "plan": plan,
                "customer_id": customer_id,
                "subscription_id": subscription_id,
                "period_start": period_start,
                "period_end": period_end,
            },
        )

        await db.commit()

        logger.info("subscription_activated", user_id=user_id, plan=plan)

    async def _handle_invoice_paid(self, invoice: dict, db: AsyncSession) -> None:
        """Handle successful recurring payment."""

        subscription_id = invoice.get("subscription")
        if not subscription_id:
            return

        subscription = self.stripe.Subscription.retrieve(subscription_id)

        period_start = datetime.fromtimestamp(subscription.current_period_start)
        period_end = datetime.fromtimestamp(subscription.current_period_end)

        await db.execute(
            text("""
                UPDATE users
                SET
                    current_period_start = :period_start,
                    current_period_end = :period_end,
                    subscription_status = 'active',
                    cancel_at_period_end = false,
                    subscription_updated_at = NOW()
                WHERE stripe_subscription_id = :subscription_id
            """),
            {
                "subscription_id": subscription_id,
                "period_start": period_start,
                "period_end": period_end,
            },
        )

        await db.execute(
            text("""
                UPDATE subscriptions
                SET
                    current_period_start = :period_start,
                    current_period_end = :period_end,
                    status = 'active',
                    cancel_at_period_end = false,
                    updated_at = NOW()
                WHERE stripe_subscription_id = :subscription_id
            """),
            {
                "subscription_id": subscription_id,
                "period_start": period_start,
                "period_end": period_end,
            },
        )

        await db.commit()

        logger.info("subscription_renewed", subscription_id=subscription_id)

    async def _handle_payment_failed(self, invoice: dict, db: AsyncSession) -> None:
        """Handle failed payment — mark as ended."""

        subscription_id = invoice.get("subscription")
        if not subscription_id:
            return

        await db.execute(
            text("""
                UPDATE users
                SET subscription_status = 'ended'
                WHERE stripe_subscription_id = :subscription_id
            """),
            {"subscription_id": subscription_id},
        )

        await db.execute(
            text("""
                UPDATE subscriptions
                SET status = 'ended', updated_at = NOW()
                WHERE stripe_subscription_id = :subscription_id
            """),
            {"subscription_id": subscription_id},
        )

        await db.commit()

        logger.warning("payment_failed", subscription_id=subscription_id)

    async def _handle_subscription_cancelled(
        self,
        subscription: dict,
        db: AsyncSession,
    ) -> None:
        """Handle subscription cancellation (end of period)."""

        subscription_id = subscription.get("id")
        if not subscription_id:
            return

        await db.execute(
            text("""
                UPDATE users
                SET
                    subscription_status = 'ended',
                    subscription_plan = 'spark',
                    cancel_at_period_end = false,
                    subscription_updated_at = NOW()
                WHERE stripe_subscription_id = :subscription_id
            """),
            {"subscription_id": subscription_id},
        )

        await db.execute(
            text("""
                UPDATE subscriptions
                SET
                    status = 'ended',
                    plan = 'spark',
                    cancel_at_period_end = false,
                    updated_at = NOW()
                WHERE stripe_subscription_id = :subscription_id
            """),
            {"subscription_id": subscription_id},
        )

        await db.commit()

        logger.info("subscription_cancelled", subscription_id=subscription_id)

    async def _handle_subscription_updated(
        self,
        subscription: dict,
        db: AsyncSession,
    ) -> None:
        """Handle subscription changes (plan changes, cancel_at_period_end, etc.)."""

        subscription_id = subscription.get("id")
        stripe_status = subscription.get("status")
        cancel_at_period_end = subscription.get("cancel_at_period_end", False)

        if not subscription_id:
            return

        internal_status = self._normalize_subscription_status(stripe_status, cancel_at_period_end)

        await db.execute(
            text("""
                UPDATE users
                SET
                    subscription_status = :status,
                    cancel_at_period_end = :cancel_at_period_end,
                    subscription_updated_at = NOW()
                WHERE stripe_subscription_id = :subscription_id
            """),
            {
                "subscription_id": subscription_id,
                "status": internal_status,
                "cancel_at_period_end": cancel_at_period_end,
            },
        )

        await db.execute(
            text("""
                UPDATE subscriptions
                SET
                    status = :status,
                    cancel_at_period_end = :cancel_at_period_end,
                    updated_at = NOW()
                WHERE stripe_subscription_id = :subscription_id
            """),
            {
                "subscription_id": subscription_id,
                "status": internal_status,
                "cancel_at_period_end": cancel_at_period_end,
            },
        )

        await db.commit()

        logger.info(
            "subscription_updated",
            subscription_id=subscription_id,
            stripe_status=stripe_status,
            internal_status=internal_status,
            cancel_at_period_end=cancel_at_period_end,
        )

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