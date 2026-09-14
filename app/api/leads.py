
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import (
    ExternalContactMap,
    Lead,
    LeadActivity,
    LeadAssignment,
    LeadLifecycle,
    Membership,
    Organization,
    OutreachEnrollment,
    OutreachTask,
    QualificationJob,
)
from app.schemas import (
    LeadCreate,
    LeadDeleteResult,
    LeadDedupeResult,
    LeadDetailRead,
    LeadRead,
    LeadStats,
    LeadUpdate,
    QualificationResult,
)
from app.security import get_principal
from app.services.access import can_manage_user, lead_is_visible, normalized_role, visible_lead_ids_subquery
from app.services.leadops import dedupe_lead, ensure_lead_state, record_activity
from app.services.outreach import maybe_autopilot_after_qualification
from app.services.profiles import active_profile_for_org, profile_payload
from app.services.provider import ProviderError
from app.services.qualifier import qualify
from app.services.usage import release_qualification, reserve_qualification

router = APIRouter(prefix="/leads", tags=["leads"])


MANUAL_MANAGE_ROLES = {"manager", "admin", "superuser"}


def _require_manual_manage(principal) -> None:
    if principal.auth_type != "session" or not principal.user:
        raise HTTPException(status_code=403, detail="Manager or admin access required")
    if normalized_role(principal.role) not in MANUAL_MANAGE_ROLES:
        raise HTTPException(status_code=403, detail="Manager or admin access required")



def _qualify_record(db: Session, org: Organization, lead: Lead) -> QualificationResult:
    profile = active_profile_for_org(db, org.id)
    if not profile:
        raise HTTPException(status_code=409, detail="Organization has no active qualification profile")

    lead_payload = {
        "name": lead.name,
        "company": lead.company,
        "email": lead.email,
        "phone": lead.phone,
        "source": lead.source,
        "notes": lead.notes,
        "attributes": json.loads(lead.payload_json or "{}"),
    }

    reserve_qualification(db, org)
    try:
        result = qualify(profile_payload(profile), lead_payload)
    except ProviderError as exc:
        release_qualification(db, org)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception:
        release_qualification(db, org)
        raise

    lead.score = result.score
    lead.status = result.status
    lead.next_action = result.next_action
    lead.reason = result.reason
    lead.qualified_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(lead)
    maybe_autopilot_after_qualification(db, lead)
    return result


def _detail_model(lead: Lead) -> LeadDetailRead:
    try:
        attributes = json.loads(lead.payload_json or "{}")
    except json.JSONDecodeError:
        attributes = {}
    if not isinstance(attributes, dict):
        attributes = {}
    return LeadDetailRead.model_validate(lead).model_copy(update={"attributes": attributes})


def _scope_stmt(stmt, db: Session, principal):
    if principal.auth_type == "api_key" or normalized_role(principal.role) in {"admin", "superuser"}:
        return stmt
    return stmt.where(Lead.id.in_(visible_lead_ids_subquery(db, principal)))



def _delete_lead_graph(db: Session, lead: Lead) -> None:
    """Delete a lead and every lead-scoped V4/V6 child record.

    Production databases enforce ON DELETE CASCADE. This explicit cleanup also
    keeps local SQLite databases safe when foreign-key pragmas were not enabled
    when the database was originally created.
    """
    lead_id = lead.id
    db.execute(delete(OutreachTask).where(OutreachTask.lead_id == lead_id))
    db.execute(delete(OutreachEnrollment).where(OutreachEnrollment.lead_id == lead_id))
    db.execute(delete(ExternalContactMap).where(ExternalContactMap.lead_id == lead_id))
    db.execute(delete(LeadActivity).where(LeadActivity.lead_id == lead_id))
    db.execute(delete(LeadLifecycle).where(LeadLifecycle.lead_id == lead_id))
    db.execute(delete(LeadAssignment).where(LeadAssignment.lead_id == lead_id))
    db.execute(delete(QualificationJob).where(QualificationJob.lead_id == lead_id))
    db.delete(lead)


def _same_contact_candidates(db: Session, lead: Lead) -> list[Lead]:
    email = (lead.email or "").strip().lower()
    digits = "".join(ch for ch in (lead.phone or "") if ch.isdigit())
    candidates = list(db.scalars(
        select(Lead).where(
            Lead.organization_id == lead.organization_id,
            Lead.id != lead.id,
        )
    ).all())
    matches: list[Lead] = []
    for candidate in candidates:
        same_email = bool(email) and (candidate.email or "").strip().lower() == email
        candidate_digits = "".join(ch for ch in (candidate.phone or "") if ch.isdigit())
        same_phone = bool(digits) and bool(candidate_digits) and candidate_digits[-10:] == digits[-10:]
        if same_email or same_phone:
            matches.append(candidate)
    return matches


@router.post("", response_model=LeadRead)
def create_and_qualify_lead(
    payload: LeadCreate,
    principal=Depends(get_principal),
    db: Session = Depends(get_db),
):
    org = principal.organization
    owner_user_id = principal.user.id if principal.user else None

    # Manual retries should never create another row for the same contact.
    existing = dedupe_lead(db, org.id, payload.email, payload.phone)
    if existing:
        if not lead_is_visible(db, principal, existing):
            raise HTTPException(
                status_code=409,
                detail="A lead with this email or phone already exists in this organization.",
            )
        _qualify_record(db, org, existing)
        record_activity(
            db,
            existing,
            "lead.retry_reused",
            "Existing lead reused instead of creating a duplicate",
            actor_user_id=owner_user_id,
        )
        db.commit()
        return existing

    lead = Lead(
        organization_id=org.id,
        name=payload.name,
        company=payload.company,
        email=payload.email,
        phone=payload.phone,
        source=payload.source,
        notes=payload.notes,
        payload_json=json.dumps(payload.attributes),
    )
    db.add(lead)
    db.flush()

    # reserve_qualification commits usage before the model call. If the model
    # call fails, explicitly remove this just-created lead so retrying the form
    # does not spray unqualified duplicates into the inbox.
    try:
        _qualify_record(db, org, lead)
    except Exception:
        persisted = db.get(Lead, lead.id)
        if persisted is not None:
            _delete_lead_graph(db, persisted)
            db.commit()
        raise

    ensure_lead_state(db, lead, owner_user_id=owner_user_id, assigned_by_user_id=owner_user_id)
    record_activity(
        db,
        lead,
        "lead.created",
        "Lead created",
        actor_user_id=owner_user_id,
        payload={"source": payload.source},
    )
    db.commit()
    db.refresh(lead)
    return lead


@router.get("", response_model=list[LeadRead])
def list_leads(
    limit: int = Query(default=50, ge=1, le=250),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None, pattern="^(Hot|Warm|Cold)$"),
    source: str | None = Query(default=None, max_length=120),
    q: str | None = Query(default=None, max_length=200),
    min_score: int | None = Query(default=None, ge=1, le=10),
    max_score: int | None = Query(default=None, ge=1, le=10),
    principal=Depends(get_principal),
    db: Session = Depends(get_db),
):
    if min_score is not None and max_score is not None and min_score > max_score:
        raise HTTPException(status_code=422, detail="min_score cannot be greater than max_score")
    org = principal.organization
    stmt = select(Lead).where(Lead.organization_id == org.id)
    stmt = _scope_stmt(stmt, db, principal)

    if status:
        stmt = stmt.where(Lead.status == status)
    if source:
        stmt = stmt.where(Lead.source == source)
    if min_score is not None:
        stmt = stmt.where(Lead.score >= min_score)
    if max_score is not None:
        stmt = stmt.where(Lead.score <= max_score)
    if q and q.strip():
        needle = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Lead.name.ilike(needle),
                Lead.company.ilike(needle),
                Lead.email.ilike(needle),
                Lead.phone.ilike(needle),
                Lead.source.ilike(needle),
                Lead.notes.ilike(needle),
            )
        )

    return list(db.scalars(stmt.order_by(Lead.created_at.desc()).offset(offset).limit(limit)).all())


@router.get("/stats", response_model=LeadStats)
def lead_stats(principal=Depends(get_principal), db: Session = Depends(get_db)):
    org = principal.organization
    base = select(Lead).where(Lead.organization_id == org.id)
    base = _scope_stmt(base, db, principal)
    ids = base.with_only_columns(Lead.id)

    total = db.scalar(select(func.count(Lead.id)).where(Lead.id.in_(ids))) or 0
    hot = db.scalar(select(func.count(Lead.id)).where(Lead.id.in_(ids), Lead.status == "Hot")) or 0
    warm = db.scalar(select(func.count(Lead.id)).where(Lead.id.in_(ids), Lead.status == "Warm")) or 0
    cold = db.scalar(select(func.count(Lead.id)).where(Lead.id.in_(ids), Lead.status == "Cold")) or 0
    pending = db.scalar(select(func.count(Lead.id)).where(Lead.id.in_(ids), Lead.status.is_(None))) or 0
    average_score = db.scalar(select(func.avg(Lead.score)).where(Lead.id.in_(ids), Lead.score.is_not(None)))
    return LeadStats(
        total=total,
        hot=hot,
        warm=warm,
        cold=cold,
        pending=pending,
        average_score=round(float(average_score), 1) if average_score is not None else None,
    )


@router.get("/{lead_id}", response_model=LeadDetailRead)
def get_lead(lead_id: str, principal=Depends(get_principal), db: Session = Depends(get_db)):
    org = principal.organization
    lead = db.scalar(select(Lead).where(Lead.id == lead_id, Lead.organization_id == org.id))
    if not lead or not lead_is_visible(db, principal, lead):
        raise HTTPException(status_code=404, detail="Lead not found")
    return _detail_model(lead)



@router.patch("/{lead_id}", response_model=LeadDetailRead)
def update_lead(
    lead_id: str,
    payload: LeadUpdate,
    principal=Depends(get_principal),
    db: Session = Depends(get_db),
):
    _require_manual_manage(principal)
    org = principal.organization
    lead = db.scalar(select(Lead).where(Lead.id == lead_id, Lead.organization_id == org.id))
    if not lead or not lead_is_visible(db, principal, lead):
        raise HTTPException(status_code=404, detail="Lead not found")

    changed: list[str] = []
    supplied = payload.model_fields_set

    # Core contact/source data.
    for field in ("name", "company", "email", "phone", "source", "notes"):
        if field in supplied:
            value = getattr(payload, field)
            setattr(lead, field, value or "")
            changed.append(field)

    if "attributes" in supplied:
        lead.payload_json = json.dumps(payload.attributes or {})
        changed.append("attributes")

    # Manual qualification overrides. These are intentionally elevated-only:
    # reps can see their assigned lead, while a manager/admin can correct the AI.
    for field in ("score", "status", "next_action", "reason"):
        if field in supplied:
            setattr(lead, field, getattr(payload, field))
            changed.append(field)

    assignment, lifecycle = ensure_lead_state(db, lead)

    if "owner_user_id" in supplied:
        owner_user_id = payload.owner_user_id or None
        if owner_user_id:
            membership = db.scalar(
                select(Membership).where(
                    Membership.organization_id == org.id,
                    Membership.user_id == owner_user_id,
                )
            )
            if not membership:
                raise HTTPException(status_code=422, detail="Owner must be a user in this organization")
            if normalized_role(principal.role) == "manager" and not can_manage_user(db, principal, owner_user_id):
                raise HTTPException(status_code=403, detail="Managers may only assign leads within their reporting tree")
        assignment.owner_user_id = owner_user_id
        assignment.assigned_by_user_id = principal.user.id
        changed.append("owner_user_id")

    for field in ("stage", "automation_state", "handoff_reason", "next_followup_at"):
        if field in supplied:
            setattr(lifecycle, field, getattr(payload, field))
            changed.append(field)

    if changed:
        record_activity(
            db,
            lead,
            "lead.manual_override",
            "Lead fields manually updated",
            actor_user_id=principal.user.id,
            payload={"fields": changed},
        )
        db.commit()
        db.refresh(lead)
    return _detail_model(lead)


@router.delete("/{lead_id}/duplicates", response_model=LeadDedupeResult)
def delete_duplicate_copies(
    lead_id: str,
    principal=Depends(get_principal),
    db: Session = Depends(get_db),
):
    _require_manual_manage(principal)
    org = principal.organization
    lead = db.scalar(select(Lead).where(Lead.id == lead_id, Lead.organization_id == org.id))
    if not lead or not lead_is_visible(db, principal, lead):
        raise HTTPException(status_code=404, detail="Lead not found")
    if not (lead.email or "").strip() and not (lead.phone or "").strip():
        return LeadDedupeResult(kept_lead_id=lead.id, deleted_count=0)

    deleted_count = 0
    for candidate in _same_contact_candidates(db, lead):
        if lead_is_visible(db, principal, candidate):
            _delete_lead_graph(db, candidate)
            deleted_count += 1
    db.commit()
    return LeadDedupeResult(kept_lead_id=lead.id, deleted_count=deleted_count)


@router.delete("/{lead_id}", response_model=LeadDeleteResult)
def delete_lead(
    lead_id: str,
    principal=Depends(get_principal),
    db: Session = Depends(get_db),
):
    _require_manual_manage(principal)
    org = principal.organization
    lead = db.scalar(select(Lead).where(Lead.id == lead_id, Lead.organization_id == org.id))
    if not lead or not lead_is_visible(db, principal, lead):
        raise HTTPException(status_code=404, detail="Lead not found")
    _delete_lead_graph(db, lead)
    db.commit()
    return LeadDeleteResult(lead_id=lead_id)


@router.post("/{lead_id}/requalify", response_model=LeadRead)
def requalify_lead(lead_id: str, principal=Depends(get_principal), db: Session = Depends(get_db)):
    org = principal.organization
    lead = db.scalar(select(Lead).where(Lead.id == lead_id, Lead.organization_id == org.id))
    if not lead or not lead_is_visible(db, principal, lead):
        raise HTTPException(status_code=404, detail="Lead not found")
    _qualify_record(db, org, lead)
    return lead
