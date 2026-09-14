from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import InboundEndpoint, Lead, QualificationJob
from app.schemas import IngestAccepted, LeadCreate

router = APIRouter(prefix="/ingest", tags=["inbound webhooks"])


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@router.post("/{token}", response_model=IngestAccepted, status_code=status.HTTP_202_ACCEPTED)
def ingest_lead(
    token: str,
    payload: LeadCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=200),
    db: Session = Depends(get_db),
):
    endpoint = db.scalar(
        select(InboundEndpoint).where(
            InboundEndpoint.token_hash == _token_hash(token),
            InboundEndpoint.active.is_(True),
        )
    )
    if not endpoint:
        raise HTTPException(status_code=404, detail="Inbound webhook not found")

    clean_idempotency = idempotency_key.strip() if idempotency_key and idempotency_key.strip() else None
    if clean_idempotency:
        existing = db.scalar(
            select(QualificationJob).where(
                QualificationJob.inbound_endpoint_id == endpoint.id,
                QualificationJob.idempotency_key == clean_idempotency,
            )
        )
        if existing:
            return IngestAccepted(
                lead_id=existing.lead_id,
                job_id=existing.id,
                status=existing.status,
            )

    import json

    lead = Lead(
        organization_id=endpoint.organization_id,
        name=payload.name,
        company=payload.company,
        email=payload.email,
        phone=payload.phone,
        source=payload.source or endpoint.name,
        notes=payload.notes,
        payload_json=json.dumps(payload.attributes),
    )
    job = QualificationJob(
        organization_id=endpoint.organization_id,
        lead=lead,
        inbound_endpoint_id=endpoint.id,
        idempotency_key=clean_idempotency,
        status="queued",
        max_attempts=settings.qualification_max_attempts,
        available_at=datetime.now(timezone.utc),
    )
    endpoint.last_used_at = datetime.now(timezone.utc)
    db.add_all([lead, job])

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if clean_idempotency:
            existing = db.scalar(
                select(QualificationJob).where(
                    QualificationJob.inbound_endpoint_id == endpoint.id,
                    QualificationJob.idempotency_key == clean_idempotency,
                )
            )
            if existing:
                return IngestAccepted(
                    lead_id=existing.lead_id,
                    job_id=existing.id,
                    status=existing.status,
                )
        raise

    db.refresh(lead)
    db.refresh(job)
    return IngestAccepted(lead_id=lead.id, job_id=job.id, status=job.status)
