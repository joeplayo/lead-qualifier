from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Lead, Organization, QualificationJob
from app.services.profiles import active_profile_for_org, profile_payload
from app.services.provider import ProviderError
from app.services.qualifier import qualify
from app.services.usage import release_qualification, reserve_qualification


def utcnow():
    return datetime.now(timezone.utc)


def retry_delay_seconds(attempt: int) -> int:
    # 5s, 20s, 45s... capped for a small MVP worker.
    return min(300, max(5, attempt * attempt * 5))


def enqueue_qualification(
    db: Session,
    org: Organization,
    lead: Lead,
    *,
    inbound_endpoint_id: str | None = None,
    idempotency_key: str | None = None,
) -> QualificationJob:
    job = QualificationJob(
        organization_id=org.id,
        lead_id=lead.id,
        inbound_endpoint_id=inbound_endpoint_id,
        idempotency_key=idempotency_key,
        status="queued",
        max_attempts=settings.qualification_max_attempts,
        available_at=utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def recover_stale_jobs(db: Session) -> int:
    cutoff = utcnow() - timedelta(seconds=settings.worker_stale_seconds)
    rows = list(
        db.scalars(
            select(QualificationJob).where(
                QualificationJob.status == "processing",
                QualificationJob.started_at.is_not(None),
                QualificationJob.started_at < cutoff,
            )
        ).all()
    )
    for job in rows:
        if job.attempts >= job.max_attempts:
            job.status = "failed"
            job.completed_at = utcnow()
            job.last_error = job.last_error or "Worker stopped while processing this job."
        else:
            job.status = "retry"
            job.available_at = utcnow()
            job.started_at = None
    if rows:
        db.commit()
    return len(rows)


def claim_next_job(db: Session) -> QualificationJob | None:
    now = utcnow()
    stmt = (
        select(QualificationJob)
        .where(
            QualificationJob.status.in_(("queued", "retry")),
            QualificationJob.available_at <= now,
        )
        .order_by(QualificationJob.created_at.asc())
        .limit(1)
    )
    # PostgreSQL can safely skip jobs already claimed by another worker.
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)

    job = db.scalar(stmt)
    if not job:
        return None
    job.status = "processing"
    job.attempts += 1
    job.started_at = now
    db.commit()
    db.refresh(job)
    return job


def process_qualification_job(db: Session, job: QualificationJob, *, provider=None):
    org = db.get(Organization, job.organization_id)
    lead = db.get(Lead, job.lead_id)
    if not org or not lead:
        job.status = "failed"
        job.completed_at = utcnow()
        job.last_error = "Organization or lead no longer exists."
        db.commit()
        return None

    profile = active_profile_for_org(db, org.id)
    if not profile:
        job.status = "failed"
        job.completed_at = utcnow()
        job.last_error = "Organization has no active qualification profile."
        db.commit()
        return None

    import json

    try:
        attributes = json.loads(lead.payload_json or "{}")
    except json.JSONDecodeError:
        attributes = {}

    payload = {
        "name": lead.name,
        "company": lead.company,
        "email": lead.email,
        "phone": lead.phone,
        "source": lead.source,
        "notes": lead.notes,
        "attributes": attributes if isinstance(attributes, dict) else {},
    }

    try:
        reserve_qualification(db, org)
        result = qualify(profile_payload(profile), payload, provider=provider)
    except HTTPException as exc:
        # Plan-limit failures are deterministic until the account changes.
        job.status = "failed"
        job.completed_at = utcnow()
        job.last_error = str(exc.detail)
        db.commit()
        return None
    except ProviderError as exc:
        release_qualification(db, org)
        _retry_or_fail(db, job, str(exc))
        return None
    except Exception as exc:
        release_qualification(db, org)
        _retry_or_fail(db, job, str(exc))
        return None

    lead.score = result.score
    lead.status = result.status
    lead.next_action = result.next_action
    lead.reason = result.reason
    lead.qualified_at = utcnow()
    job.status = "succeeded"
    job.completed_at = utcnow()
    job.last_error = None
    db.commit()
    db.refresh(lead)
    return lead


def _retry_or_fail(db: Session, job: QualificationJob, message: str) -> None:
    job.last_error = (message or "Qualification failed.")[:4000]
    if job.attempts >= job.max_attempts:
        job.status = "failed"
        job.completed_at = utcnow()
    else:
        job.status = "retry"
        job.available_at = utcnow() + timedelta(seconds=retry_delay_seconds(job.attempts))
        job.started_at = None
    db.commit()
