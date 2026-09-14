
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Lead, LeadActivity, LeadAssignment, LeadLifecycle
from app.security import Principal

def ensure_lead_state(
    db: Session,
    lead: Lead,
    owner_user_id: str | None = None,
    assigned_by_user_id: str | None = None,
) -> tuple[LeadAssignment, LeadLifecycle]:
    assignment = db.scalar(select(LeadAssignment).where(LeadAssignment.lead_id == lead.id))
    if not assignment:
        assignment = LeadAssignment(
            organization_id=lead.organization_id,
            lead_id=lead.id,
            owner_user_id=owner_user_id,
            assigned_by_user_id=assigned_by_user_id,
        )
        db.add(assignment)
    elif owner_user_id and not assignment.owner_user_id:
        assignment.owner_user_id = owner_user_id
        assignment.assigned_by_user_id = assigned_by_user_id

    lifecycle = db.scalar(select(LeadLifecycle).where(LeadLifecycle.lead_id == lead.id))
    if not lifecycle:
        lifecycle = LeadLifecycle(
            organization_id=lead.organization_id,
            lead_id=lead.id,
            stage="new",
            automation_state="eligible",
        )
        db.add(lifecycle)
    db.flush()
    return assignment, lifecycle

def record_activity(
    db: Session,
    lead: Lead,
    kind: str,
    summary: str,
    *,
    actor_user_id: str | None = None,
    channel: str | None = None,
    payload: dict | None = None,
) -> LeadActivity:
    activity = LeadActivity(
        organization_id=lead.organization_id,
        lead_id=lead.id,
        actor_user_id=actor_user_id,
        kind=kind,
        channel=channel,
        summary=summary,
        payload_json=json.dumps(payload or {}),
    )
    db.add(activity)
    return activity

def dedupe_lead(db: Session, organization_id: str, email: str = "", phone: str = "") -> Lead | None:
    clauses = []
    email = (email or "").strip().lower()
    phone = "".join(ch for ch in (phone or "") if ch.isdigit())
    if email:
        clauses.append(Lead.email.ilike(email))
    if phone:
        clauses.append(Lead.phone.ilike(f"%{phone[-10:]}"))
    if not clauses:
        return None
    return db.scalar(
        select(Lead).where(Lead.organization_id == organization_id, or_(*clauses)).order_by(Lead.created_at.desc())
    )
