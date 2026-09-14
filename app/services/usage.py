from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import PLAN_LIMITS
from app.models import Organization, UsageCounter

def current_period_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")

def plan_limit(org: Organization) -> int:
    return PLAN_LIMITS.get(org.plan, PLAN_LIMITS["free"])

def get_usage(db: Session, org: Organization) -> tuple[int, int]:
    row = db.scalar(
        select(UsageCounter).where(
            UsageCounter.organization_id == org.id,
            UsageCounter.period_key == current_period_key(),
        )
    )
    used = row.qualification_count if row else 0
    return used, plan_limit(org)

def reserve_qualification(db: Session, org: Organization) -> None:
    period = current_period_key()
    # Row lock protects the common PostgreSQL path. SQLite remains suitable for local/dev use.
    row = db.scalar(
        select(UsageCounter)
        .where(UsageCounter.organization_id == org.id, UsageCounter.period_key == period)
        .with_for_update()
    )
    if row is None:
        row = UsageCounter(organization_id=org.id, period_key=period, qualification_count=0)
        db.add(row)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            row = db.scalar(
                select(UsageCounter)
                .where(UsageCounter.organization_id == org.id, UsageCounter.period_key == period)
                .with_for_update()
            )
            if row is None:
                raise

    limit = plan_limit(org)
    if row.qualification_count >= limit:
        db.rollback()
        raise HTTPException(
            status_code=402,
            detail=f"Monthly qualification limit reached for the {org.plan} plan ({limit}).",
        )
    row.qualification_count += 1
    db.commit()

def release_qualification(db: Session, org: Organization) -> None:
    row = db.scalar(
        select(UsageCounter).where(
            UsageCounter.organization_id == org.id,
            UsageCounter.period_key == current_period_key(),
        )
    )
    if row and row.qualification_count > 0:
        row.qualification_count -= 1
        db.commit()
