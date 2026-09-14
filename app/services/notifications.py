from __future__ import annotations

import hashlib
import hmac
import json
import time

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Lead, NotificationEndpoint, Organization


def notification_payload(org: Organization, lead: Lead) -> dict:
    return {
        "event": "lead.hot",
        "organization_id": org.id,
        "lead": {
            "id": lead.id,
            "name": lead.name,
            "company": lead.company,
            "email": lead.email,
            "phone": lead.phone,
            "source": lead.source,
            "score": lead.score,
            "status": lead.status,
            "next_action": lead.next_action,
            "reason": lead.reason,
            "qualified_at": lead.qualified_at.isoformat() if lead.qualified_at else None,
        },
    }


def sign_body(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def send_hot_lead_notification(db: Session, org: Organization, lead: Lead) -> bool:
    if lead.status != "Hot":
        return False
    endpoint = db.scalar(
        select(NotificationEndpoint).where(
            NotificationEndpoint.organization_id == org.id,
            NotificationEndpoint.active.is_(True),
        )
    )
    if not endpoint:
        return False

    body = json.dumps(notification_payload(org, lead), separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "LeadSignal-Webhook/0.4",
        "X-LeadSignal-Event": "lead.hot",
    }
    if endpoint.signing_secret:
        headers["X-LeadSignal-Signature"] = "sha256=" + sign_body(endpoint.signing_secret, body)

    # Small bounded retry loop for outbound delivery. Qualification remains successful
    # even when the recipient endpoint is temporarily unavailable.
    for attempt in range(1, 4):
        try:
            response = httpx.post(
                endpoint.url,
                content=body,
                headers=headers,
                timeout=settings.notification_timeout_seconds,
            )
            if 200 <= response.status_code < 300:
                return True
        except httpx.HTTPError:
            pass
        if attempt < 3:
            time.sleep(min(2 ** (attempt - 1), 2))
    return False

def send_handoff_notification(db: Session, org: Organization, lead: Lead, reason: str) -> bool:
    endpoint = db.scalar(
        select(NotificationEndpoint).where(
            NotificationEndpoint.organization_id == org.id,
            NotificationEndpoint.active.is_(True),
        )
    )
    if not endpoint:
        return False
    payload = notification_payload(org, lead)
    payload["event"] = "lead.handoff"
    payload["handoff_reason"] = reason
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "LeadSignal-Webhook/0.6",
        "X-LeadSignal-Event": "lead.handoff",
    }
    if endpoint.signing_secret:
        headers["X-LeadSignal-Signature"] = "sha256=" + sign_body(endpoint.signing_secret, body)
    for attempt in range(1, 4):
        try:
            response = httpx.post(
                endpoint.url,
                content=body,
                headers=headers,
                timeout=settings.notification_timeout_seconds,
            )
            if 200 <= response.status_code < 300:
                return True
        except httpx.HTTPError:
            pass
        if attempt < 3:
            time.sleep(min(2 ** (attempt - 1), 2))
    return False

