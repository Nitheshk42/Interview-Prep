"""Three pricing tiers via Stripe Checkout - built and wired up ahead of actually turning
monetization on. Each tier works end-to-end against real Stripe test/live keys the moment
STRIPE_SECRET_KEY / STRIPE_WEBHOOK_SECRET / that tier's price ID are set in the environment, but
returns a clear 503 (not a raw SDK crash) while they're unset - which is the default, so nothing
here charges anyone until those env vars are deliberately added. Tiers can be turned on one at a
time (e.g. Career Sprint live while Pro Monthly's price ID is still blank).

Tiers:
- sprint: one-time charge, 14-day access window (STRIPE_PRICE_ID_SPRINT)
- student: one-time charge, discounted rate, same 14-day window (STRIPE_PRICE_ID_STUDENT)
- pro_monthly: recurring monthly subscription, active until cancelled (STRIPE_PRICE_ID_PRO_MONTHLY)

Flow: frontend hits POST /payments/checkout with a tier name -> gets a Stripe-hosted Checkout URL
-> user pays on Stripe's own page (StudySager never sees card details) -> Stripe redirects the
browser back to FRONTEND_BASE_URL/payment-result -> Stripe ALSO calls POST /payments/webhook
server-to-server, which is the only signal actually trusted to activate the purchase (the browser
redirect alone proves nothing - a user could hit the success URL without paying). For pro_monthly,
a separate customer.subscription.deleted webhook event is what marks access as ended, since a
subscription doesn't expire on a fixed date the way the one-time tiers do."""
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from app.deps import get_current_user
from app.core.config import (
    STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET,
    STRIPE_PRICE_ID_SPRINT, STRIPE_PRICE_ID_STUDENT, STRIPE_PRICE_ID_PRO_MONTHLY,
    FRONTEND_BASE_URL, SPRINT_DURATION_DAYS,
)
from app import db

router = APIRouter(prefix="/payments", tags=["payments"])

# Single source of truth for what each tier means to Stripe. "mode" matches Stripe Checkout's
# own mode parameter ("payment" = one-time, "subscription" = recurring). duration_days is None
# for the subscription tier - see activate_purchase()'s docstring for why that matters.
TIERS = {
    "sprint": {"price_id": STRIPE_PRICE_ID_SPRINT, "mode": "payment", "duration_days": SPRINT_DURATION_DAYS},
    "student": {"price_id": STRIPE_PRICE_ID_STUDENT, "mode": "payment", "duration_days": SPRINT_DURATION_DAYS},
    "pro_monthly": {"price_id": STRIPE_PRICE_ID_PRO_MONTHLY, "mode": "subscription", "duration_days": None},
}


def _stripe():
    """Imports and configures the Stripe SDK lazily, per-call, rather than at module load time -
    so a missing/placeholder STRIPE_SECRET_KEY never breaks app startup or any other router; it
    only surfaces as a 503 the moment someone actually tries to check out."""
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Payments aren't turned on yet. (STRIPE_SECRET_KEY not configured.)")
    import stripe
    stripe.api_key = STRIPE_SECRET_KEY
    return stripe


class CheckoutRequest(BaseModel):
    tier: str = "sprint"


class CheckoutResponse(BaseModel):
    checkout_url: str


class StatusResponse(BaseModel):
    active: bool
    tier: str | None = None
    expires_at: str | None = None  # None for an active pro_monthly subscription - see db.py


class PlansResponse(BaseModel):
    available_tiers: list[str]  # which tiers actually have a price ID configured right now


@router.get("/plans", response_model=PlansResponse)
def plans():
    """Lets the frontend only show tiers that are actually turned on (have a real price ID set),
    rather than hardcoding the tier list client-side and having some of them 503 on click."""
    return PlansResponse(available_tiers=[t for t, cfg in TIERS.items() if cfg["price_id"]])


@router.get("/status", response_model=StatusResponse)
def status(username: str = Depends(get_current_user)):
    """Lets the frontend show a 'X active - expires in Y days' badge without needing to know
    anything about Stripe - just asks Postgres via db.get_active_purchase()."""
    purchase = db.get_active_purchase(username)
    if not purchase:
        return StatusResponse(active=False)
    return StatusResponse(active=True, tier=purchase["tier"], expires_at=purchase["expires_at"])


@router.post("/checkout", response_model=CheckoutResponse)
def create_checkout(payload: CheckoutRequest, username: str = Depends(get_current_user)):
    stripe = _stripe()
    tier_cfg = TIERS.get(payload.tier)
    if not tier_cfg:
        raise HTTPException(status_code=400, detail=f"Unknown plan '{payload.tier}'.")
    if not tier_cfg["price_id"]:
        raise HTTPException(
            status_code=503,
            detail=f"The '{payload.tier}' plan isn't turned on yet. (Its Stripe price ID isn't configured.)",
        )
    session = stripe.checkout.Session.create(
        mode=tier_cfg["mode"],
        line_items=[{"price": tier_cfg["price_id"], "quantity": 1}],
        client_reference_id=username,
        # metadata survives onto the Checkout Session object the webhook receives, which is how
        # the webhook knows which tier this was without re-deriving it from the price ID alone.
        metadata={"username": username, "tier": payload.tier},
        success_url=f"{FRONTEND_BASE_URL}/payment-result?status=success",
        cancel_url=f"{FRONTEND_BASE_URL}/payment-result?status=cancelled",
    )
    db.create_pending_purchase(username, payload.tier, session.id)
    return CheckoutResponse(checkout_url=session.url)


@router.post("/webhook")
async def webhook(request: Request):
    """Stripe calls this directly (never the browser). Verifies the request actually came from
    Stripe via the signed Stripe-Signature header before trusting anything in the payload -
    without that check, anyone who discovered this URL could POST a fake event and activate a
    free tier for themselves."""
    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Webhook not configured.")
    import stripe

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError):
        raise HTTPException(status_code=400, detail="Invalid webhook signature.")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        tier = (session.get("metadata") or {}).get("tier", "sprint")
        duration_days = TIERS.get(tier, TIERS["sprint"])["duration_days"]
        # None duration (pro_monthly) -> None expires_at, i.e. "active until cancelled" rather
        # than "active until a fixed date" - see db.activate_purchase()'s docstring.
        expires_at = (
            (datetime.now(timezone.utc) + timedelta(days=duration_days)).isoformat()
            if duration_days is not None else None
        )
        db.activate_purchase(
            stripe_session_id=session["id"],
            stripe_customer_id=session.get("customer"),
            expires_at=expires_at,
            stripe_subscription_id=session.get("subscription"),
        )

    elif event["type"] == "customer.subscription.deleted":
        # Fires when a pro_monthly subscription actually ends - cancelled by the user, or Stripe
        # gave up retrying a failed payment. This is the only signal that ends a subscription's
        # access, since (unlike sprint/student) it has no expires_at counting down on its own.
        subscription = event["data"]["object"]
        db.deactivate_subscription(subscription["id"])

    return {"received": True}
