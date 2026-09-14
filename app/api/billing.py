import json

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import BillingSummary, CheckoutRequest, CheckoutResponse, PortalResponse
from app.security import Principal, get_principal, require_session_user
from app.services.billing import apply_stripe_event, create_checkout, create_portal, verify_stripe_signature
from app.services.usage import get_usage

router = APIRouter(prefix="/billing", tags=["billing"])

@router.get("/summary", response_model=BillingSummary)
def summary(
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    org = principal.organization
    used, limit = get_usage(db, org)
    return BillingSummary(
        plan=org.plan,
        subscription_status=org.subscription_status,
        used=used,
        limit=limit,
        remaining=max(limit - used, 0),
    )

@router.post("/checkout", response_model=CheckoutResponse)
def checkout(
    payload: CheckoutRequest,
    principal: Principal = Depends(require_session_user),
):
    return CheckoutResponse(
        url=create_checkout(principal.organization, principal.user.email, payload.plan)
    )

@router.post("/portal", response_model=PortalResponse)
def portal(principal: Principal = Depends(require_session_user)):
    return PortalResponse(url=create_portal(principal.organization))

@router.post("/stripe/webhook", include_in_schema=False)
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
    db: Session = Depends(get_db),
):
    raw = await request.body()
    verify_stripe_signature(raw, stripe_signature)
    event = json.loads(raw.decode("utf-8"))
    apply_stripe_event(db, event)
    return {"received": True}
