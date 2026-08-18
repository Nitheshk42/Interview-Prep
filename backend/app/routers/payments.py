"""Career Sprint one-time purchase via Stripe Checkout. Built and wired up ahead of actually
turning monetization on: every endpoint here works end-to-end against real Stripe test/live keys
the moment STRIPE_SECRET_KEY / STRIPE_WEBHOOK_SECRET / STRIPE_PRICE_ID_SPRINT are set in the
environment, but returns a clear 503 (not a raw SDK crash) while they're unset - which is the
default, so nothing here charges anyone until those three env vars are deliberately added.

Flow: frontend hits POST /payments/checkout -> gets a Stripe-hosted Checkout URL -> user pays on
Stripe's own page (StudySager never sees card details) -> Stripe redirects the browser back to
FRONTEND_BASE_URL/payment-result -> Stripe ALSO calls POST /payments/webhook server-to-server,
which is the only signal actually trusted to activate the purchase (the browser redirect alone
proves nothing - a user could hit the success URL without paying)."""
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from app.deps import get_current_user
from app.core.config import (
    STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, STRIPE_PRICE_ID_SPRINT,
    FRONTEND_BASE_URL, SPRINT_DURATION_DAYS,
)
from app import db

router = APIRouter(prefix="/payments", tags=["payments"])


def _stripe():
    """Imports and configures the Stripe SDK lazily, per-call, rather than at module load time -
    so a missing/placeholder STRIPE_SECRET_KEY never breaks app startup or any other router; it
    only surfaces as a 503 the moment someone actually tries to check out."""
    if not STRIPE_SECRET_KEY or not STRIPE_PRICE_ID_SPRINT:
        raise HTTPException(
            status_code=503,
            detail="Payments aren't turned on yet. (STRIPE_SECRET_KEY / STRIPE_PRICE_ID_SPRINT not configured.)",
        )
    import stripe
    stripe.api_key = STRIPE_SECRET_KEY
    return stripe


class CheckoutResponse(BaseModel):
    checkout_url: str


class StatusResponse(BaseModel):
    active: bool
    expires_at: str | None = None


@router.get("/status", response_model=StatusResponse)
def status(username: str = Depends(get_current_user)):
    """Lets the frontend show a 'Sprint active - expires in X days' badge without needing to
    know anything about Stripe - just asks Postgres via db.has_active_sprint()."""
    if not db.has_active_sprint(username):
        return StatusResponse(active=False)
    return StatusResponse(active=True, expires_at=db.get_active_sprint_expiry(username))


@router.post("/checkout", response_model=CheckoutResponse)
def create_checkout(username: str = Depends(get_current_user)):
    stripe = _stripe()
    session = stripe.checkout.Session.create(
        mode="payment",  # one-time charge, not a subscription - matches the Career Sprint SKU
        line_items=[{"price": STRIPE_PRICE_ID_SPRINT, "quantity": 1}],
        client_reference_id=username,
        success_url=f"{FRONTEND_BASE_URL}/payment-result?status=success",
        cancel_url=f"{FRONTEND_BASE_URL}/payment-result?status=cancelled",
    )
    db.create_pending_purchase(username, "sprint", session.id)
    return CheckoutResponse(checkout_url=session.url)


@router.post("/webhook")
async def webhook(request: Request):
    """Stripe calls this directly (never the browser) once a Checkout Session completes. Verifies
    the request actually came from Stripe via the signed Stripe-Signature header before trusting
    anything in the payload - without that check, anyone who discovered this URL could POST a
    fake 'payment succeeded' event and activate a free Sprint for themselves."""
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
        expires_at = (datetime.now(timezone.utc) + timedelta(days=SPRINT_DURATION_DAYS)).isoformat()
        db.activate_purchase(
            stripe_session_id=session["id"],
            stripe_customer_id=session.get("customer"),
            expires_at=expires_at,
        )

    return {"received": True}
