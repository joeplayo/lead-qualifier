from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import InboundEndpoint, NotificationEndpoint, Organization, QualificationJob
from app.schemas import (
    InboundEndpointCreate,
    InboundEndpointCreated,
    InboundEndpointRead,
    NotificationEndpointRead,
    NotificationEndpointUpdate,
    QualificationJobRead,
)
from app.security import get_current_org

router = APIRouter(prefix="/automations", tags=["automations"])


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _valid_webhook_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except Exception:
        return False


@router.get("/inbound-endpoints", response_model=list[InboundEndpointRead])
def list_inbound_endpoints(
    org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    rows = db.scalars(
        select(InboundEndpoint)
        .where(InboundEndpoint.organization_id == org.id)
        .order_by(InboundEndpoint.created_at.desc())
    ).all()
    return [
        InboundEndpointRead(
            id=x.id,
            name=x.name,
            token_prefix=x.token_prefix,
            active=x.active,
            last_used_at=x.last_used_at,
            created_at=x.created_at,
        )
        for x in rows
    ]


@router.post("/inbound-endpoints", response_model=InboundEndpointCreated)
def create_inbound_endpoint(
    payload: InboundEndpointCreate,
    org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    raw_token = "in_" + secrets.token_urlsafe(30)
    endpoint = InboundEndpoint(
        organization_id=org.id,
        name=payload.name.strip() or "Website",
        token_hash=_token_hash(raw_token),
        token_prefix=raw_token[:12],
    )
    db.add(endpoint)
    db.commit()
    db.refresh(endpoint)
    return InboundEndpointCreated(
        id=endpoint.id,
        name=endpoint.name,
        token_prefix=endpoint.token_prefix,
        active=endpoint.active,
        last_used_at=endpoint.last_used_at,
        created_at=endpoint.created_at,
        webhook_url=f"{settings.app_base_url}/api/v1/ingest/{raw_token}",
    )


@router.delete("/inbound-endpoints/{endpoint_id}", status_code=204)
def revoke_inbound_endpoint(
    endpoint_id: str,
    org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    endpoint = db.scalar(
        select(InboundEndpoint).where(
            InboundEndpoint.id == endpoint_id,
            InboundEndpoint.organization_id == org.id,
        )
    )
    if not endpoint:
        raise HTTPException(status_code=404, detail="Inbound endpoint not found")
    endpoint.active = False
    db.commit()


@router.get("/notification-endpoint", response_model=NotificationEndpointRead | None)
def get_notification_endpoint(
    org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    endpoint = db.scalar(
        select(NotificationEndpoint).where(NotificationEndpoint.organization_id == org.id)
    )
    if not endpoint:
        return None
    return NotificationEndpointRead(
        url=endpoint.url,
        active=endpoint.active,
        has_signing_secret=bool(endpoint.signing_secret),
    )


@router.put("/notification-endpoint", response_model=NotificationEndpointRead)
def set_notification_endpoint(
    payload: NotificationEndpointUpdate,
    org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    if org.plan not in {"starter", "growth"} or org.subscription_status not in {"active", "trialing"}:
        raise HTTPException(status_code=402, detail="External Hot-lead alerts are available on paid accounts")
    url = payload.url.strip()
    if not _valid_webhook_url(url):
        raise HTTPException(status_code=422, detail="Notification URL must be a valid http:// or https:// URL")

    endpoint = db.scalar(
        select(NotificationEndpoint).where(NotificationEndpoint.organization_id == org.id)
    )
    if not endpoint:
        endpoint = NotificationEndpoint(
            organization_id=org.id,
            url=url,
            signing_secret=payload.signing_secret or None,
            active=payload.active,
        )
        db.add(endpoint)
    else:
        endpoint.url = url
        endpoint.active = payload.active
        # Omitted/null secret keeps the current secret; empty string clears it.
        if payload.signing_secret is not None:
            endpoint.signing_secret = payload.signing_secret or None
    db.commit()
    db.refresh(endpoint)
    return NotificationEndpointRead(
        url=endpoint.url,
        active=endpoint.active,
        has_signing_secret=bool(endpoint.signing_secret),
    )


@router.get("/jobs/{job_id}", response_model=QualificationJobRead)
def get_job(
    job_id: str,
    org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    job = db.scalar(
        select(QualificationJob).where(
            QualificationJob.id == job_id,
            QualificationJob.organization_id == org.id,
        )
    )
    if not job:
        raise HTTPException(status_code=404, detail="Qualification job not found")
    return QualificationJobRead(
        id=job.id,
        lead_id=job.lead_id,
        status=job.status,
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        available_at=job.available_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        last_error=job.last_error,
        created_at=job.created_at,
    )
