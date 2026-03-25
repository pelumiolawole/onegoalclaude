"""
api/routers/billing.py

Stripe billing endpoints for subscription management.
"""

import os
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from api.dependencies.auth import get_current_user
from db.models.user import User
from services.billing import billing_service

router = APIRouter(prefix="/billing", tags=["billing"])

# Frontend URL — reads from environment variable, falls back to custom domain
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://onegoalpro.app")


class CheckoutRequest(BaseModel):
    plan: str = Field(..., pattern="^(forge|identity)$")
    billing_cycle: str = Field(..., pattern="^(monthly|annual)$")


@router.post("/checkout")
async def create_checkout(
    request: CheckoutRequest,
    current_user: User = Depends(get_current_user),
):
    """Create Stripe checkout session."""

    success_url = f"{FRONTEND_URL}/billing/success?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{FRONTEND_URL}/billing/cancel"

    result = await billing_service.create_checkout_session(
        user_id=str(current_user.id),
        user_email=current_user.email,
        plan=request.plan,
        billing_cycle=request.billing_cycle,
        success_url=success_url,
        cancel_url=cancel_url,
    )

    return result


@router.post("/portal")
async def create_portal(
    current_user: User = Depends(get_current_user),
):
    """Create Stripe customer portal session."""

    if not current_user.stripe_customer_id:
        raise HTTPException(
            status_code=400,
            detail="No Stripe customer found"
        )

    result = await billing_service.create_customer_portal_session(
        user_id=str(current_user.id),
        stripe_customer_id=current_user.stripe_customer_id,
        return_url=f"{FRONTEND_URL}/settings",
    )

    return result


@router.get("/subscription")
async def get_subscription(
    current_user: User = Depends(get_current_user),
):
    """Get current user's subscription details."""

    if not current_user.subscription_plan or current_user.subscription_plan == "spark":
        return {
            "plan": "spark",
            "status": "active",
            "billing_cycle": None,
            "current_period_start": None,
            "current_period_end": None,
            "cancel_at_period_end": False,
            "stripe_customer_id": None,
            "stripe_subscription_id": None,
        }

    return {
        "plan": current_user.subscription_plan,
        "status": current_user.subscription_status,
        "billing_cycle": current_user.billing_cycle or "monthly",
        "current_period_start": current_user.current_period_start.isoformat() if current_user.current_period_start else None,
        "current_period_end": current_user.current_period_end.isoformat() if current_user.current_period_end else None,
        "cancel_at_period_end": current_user.cancel_at_period_end or False,
        "stripe_customer_id": current_user.stripe_customer_id,
        "stripe_subscription_id": current_user.stripe_subscription_id,
    }


@router.post("/subscription/cancel")
async def cancel_subscription(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cancel subscription at period end."""

    if not current_user.stripe_subscription_id:
        raise HTTPException(
            status_code=400,
            detail="No active subscription found"
        )

    success = await billing_service.cancel_subscription(
        subscription_id=current_user.stripe_subscription_id,
        db=db,
    )

    if not success:
        raise HTTPException(
            status_code=400,
            detail="Failed to cancel subscription"
        )

    return {
        "status": "canceling",
        "message": "Your subscription will cancel at the end of this billing period. You'll keep access until then."
    }


@router.post("/subscription/resume")
async def resume_subscription(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Resume a subscription scheduled to cancel."""

    if not current_user.stripe_subscription_id:
        raise HTTPException(
            status_code=400,
            detail="No subscription found"
        )

    success = await billing_service.reactivate_subscription(
        subscription_id=current_user.stripe_subscription_id,
        db=db,
    )

    if not success:
        raise HTTPException(
            status_code=400,
            detail="Failed to resume subscription"
        )

    return {
        "status": "active",
        "message": "Your subscription has been resumed."
    }


@router.get("/invoices")
async def get_invoices(
    current_user: User = Depends(get_current_user),
):
    """Get billing history for current user."""

    if not current_user.stripe_customer_id:
        return {"invoices": []}

    invoices = await billing_service.get_invoices(
        stripe_customer_id=current_user.stripe_customer_id
    )

    return {"invoices": invoices}


@router.get("/verify-session")
async def verify_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    """Verify a completed Stripe checkout session."""

    if not session_id:
        raise HTTPException(status_code=400, detail="Missing session_id")

    result = await billing_service.verify_checkout_session(
        session_id=session_id,
        user_id=str(current_user.id),
    )

    return result


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Receive Stripe webhook events."""

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    if not sig_header:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing stripe-signature header",
        )

    success = await billing_service.handle_webhook(payload, sig_header, db)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook processing failed",
        )

    return {"status": "success"}