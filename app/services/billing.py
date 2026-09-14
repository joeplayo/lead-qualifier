import hashlib
import hmac
import json
import time
from typing import Any

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Organization

STRIPE_API = "https://api.stripe.com/v1"

class BillingError(RuntimeError):
    pass

def _secret() -> str:
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=503, detail="Stripe billing is not configured")
    return settings.stripe_secret_key

def price_for_plan(plan: str) -> str:
    price = {
        "starter": settings.stripe_price_starter,
        "growth": settings.stripe_price_growth,
    }.get(plan)
    if not price:
        raise HTTPException(status_code=503, detail=f"Stripe price for {plan} is not configured")
    return price

def plan_for_price(price_id: str | None) -> str:
    if price_id and price_id == settings.stripe_price_growth:
        return "growth"
    if price_id and price_id == settings.stripe_price_starter:
        return "starter"
    return "free"

def create_checkout(org: Organization, user_email: str, plan: str) -> str:
    data: dict[str, str] = {
        "mode": "subscription",
        "line_items[0][price]": price_for_plan(plan),
        "line_items[0][quantity]": "1",
        "success_url": f"{settings.app_base_url}/dashboard/?billing=success",
        "cancel_url": f"{settings.app_base_url}/dashboard/?billing=cancelled",
        "client_reference_id": org.id,
        "metadata[organization_id]": org.id,
        "subscription_data[metadata][organization_id]": org.id,
        "allow_promotion_codes": "true",
    }
    if org.stripe_customer_id:
        data["customer"] = org.stripe_customer_id
    else:
        data["customer_email"] = user_email
    try:
        response = httpx.post(
            f"{STRIPE_API}/checkout/sessions",
            data=data,
            auth=(_secret(), ""),
            timeout=20.0,
        )
        payload = response.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Could not reach Stripe") from exc
    if response.status_code >= 400 or not payload.get("url"):
        message = payload.get("error", {}).get("message", "Stripe checkout creation failed")
        raise HTTPException(status_code=502, detail=message)
    return payload["url"]

def create_portal(org: Organization) -> str:
    if not org.stripe_customer_id:
        raise HTTPException(status_code=409, detail="Organization has no Stripe customer yet")
    try:
        response = httpx.post(
            f"{STRIPE_API}/billing_portal/sessions",
            data={
                "customer": org.stripe_customer_id,
                "return_url": f"{settings.app_base_url}/dashboard/",
            },
            auth=(_secret(), ""),
            timeout=20.0,
        )
        payload = response.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Could not reach Stripe") from exc
    if response.status_code >= 400 or not payload.get("url"):
        message = payload.get("error", {}).get("message", "Stripe portal creation failed")
        raise HTTPException(status_code=502, detail=message)
    return payload["url"]

def verify_stripe_signature(payload: bytes, signature_header: str | None, tolerance_seconds: int = 300) -> None:
    secret = settings.stripe_webhook_secret
    if not secret:
        raise HTTPException(status_code=503, detail="Stripe webhook secret is not configured")
    if not signature_header:
        raise HTTPException(status_code=400, detail="Missing Stripe-Signature")
    pieces: dict[str, list[str]] = {}
    for part in signature_header.split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            pieces.setdefault(k, []).append(v)
    try:
        timestamp = int(pieces["t"][0])
        signatures = pieces.get("v1", [])
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Malformed Stripe-Signature") from exc
    if abs(int(time.time()) - timestamp) > tolerance_seconds:
        raise HTTPException(status_code=400, detail="Stripe webhook timestamp outside tolerance")
    signed = f"{timestamp}.".encode() + payload
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, sig) for sig in signatures):
        raise HTTPException(status_code=400, detail="Invalid Stripe webhook signature")

def apply_stripe_event(db: Session, event: dict[str, Any]) -> None:
    event_type = event.get("type", "")
    obj = event.get("data", {}).get("object", {}) or {}
    org: Organization | None = None

    metadata = obj.get("metadata", {}) or {}
    org_id = metadata.get("organization_id") or obj.get("client_reference_id")
    if org_id:
        org = db.get(Organization, org_id)
    if org is None and obj.get("customer"):
        org = db.scalar(select(Organization).where(Organization.stripe_customer_id == obj["customer"]))
    if org is None:
        return

    if event_type == "checkout.session.completed":
        if obj.get("customer"):
            org.stripe_customer_id = obj["customer"]
        if obj.get("subscription"):
            org.stripe_subscription_id = obj["subscription"]
        org.subscription_status = "checkout_complete"

    elif event_type.startswith("customer.subscription."):
        org.stripe_customer_id = obj.get("customer") or org.stripe_customer_id
        org.stripe_subscription_id = obj.get("id") or org.stripe_subscription_id
        status = obj.get("status", "inactive")
        org.subscription_status = status
        items = obj.get("items", {}).get("data", [])
        price_id = None
        if items:
            price_id = (items[0].get("price") or {}).get("id")
        if status in {"active", "trialing", "past_due"}:
            org.plan = plan_for_price(price_id)
        else:
            org.plan = "free"

    db.commit()
