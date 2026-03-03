"""
api/routers/billing.py

Billing endpoints for subscriptions and checkout.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies.auth import get_current_user
from core.database import get_db
from db.models.user import User
from services.billing import billing_service, STRIPE_PUBLISHABLE_KEY

router = APIRouter(prefix="/billing", tags=["Billing"])


class CheckoutRequest(BaseModel):
    plan: str = Field(..., regex="^(forge|identity)$")
    billing_cycle: str = Field(..., regex="^(monthly|annual)$")


class CheckoutResponse(BaseModel):
    session_id: str
    url: str


@router.get("/config")
async def get_stripe_config():
    """Get Stripe publishable key for frontend."""
    return {
        "publishable_key": STRIPE_PUBLISHABLE_KEY,
        "prices": {
            "forge_monthly": "$3.99",
            "forge_annual": "$2.99",
            "identity_monthly": "$8.99",
            "identity_annual": "$6.99",
        }
    }


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    request: CheckoutRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create Stripe Checkout session for subscription."""
    
    # Prevent duplicate subscriptions
    if current_user.subscription_plan in ["forge", "identity"]:
        if current_user.subscription_status == "active":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Already has active subscription. Use customer portal to manage.",
            )
    
    # Build URLs
    base_url = "https://onegoalpro.vercel.app"  # Update with your domain
    success_url = f"{base_url}/billing/success?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{base_url}/billing/cancel"
    
    result = await billing_service.create_checkout_session(
        user_id=str(current_user.id),
        user_email=current_user.email,
        plan=request.plan,
        billing_cycle=request.billing_cycle,
        success_url=success_url,
        cancel_url=cancel_url,
    )
    
    return CheckoutResponse(**result)


@router.post("/portal")
async def create_portal_session(
    current_user: User = Depends(get_current_user),
):
    """Create Stripe Customer Portal session to manage subscription."""
    
    if not current_user.stripe_customer_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No subscription found",
        )
    
    base_url = "https://onegoalpro.vercel.app"
    
    result = await billing_service.create_customer_portal_session(
        user_id=str(current_user.id),
        stripe_customer_id=current_user.stripe_customer_id,
        return_url=f"{base_url}/settings/billing",
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


@router.get("/status")
async def get_subscription_status(
    current_user: User = Depends(get_current_user),
):
    """Get current user's subscription status."""
    
    return {
        "plan": current_user.subscription_plan or "spark",
        "status": current_user.subscription_status or "inactive",
        "period_start": current_user.current_period_start,
        "period_end": current_user.current_period_end,
        "features": {
            "coach_messages": "unlimited" if current_user.subscription_plan in ["forge", "identity"] else "5/day",
            "weekly_reviews": current_user.subscription_plan in ["forge", "identity"],
            "priority_support": current_user.subscription_plan == "identity",
        }
    }