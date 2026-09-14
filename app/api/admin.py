from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Lead, Membership, Organization, QualificationJob, User
from app.presets import PRESETS
from app.schemas import (
    AdminOrganizationUpdate,
    AdminUserUpdate,
    OrganizationCreate,
    OrganizationCreated,
)
from app.security import (
    Principal,
    hash_api_key,
    new_org_api_key,
    require_admin,
    require_superuser,
)
from app.services.profiles import replace_active_profile
from app.services.superuser import SYSTEM_ORG_NAME

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/organizations", response_model=OrganizationCreated, dependencies=[Depends(require_admin)])
def create_organization(payload: OrganizationCreate, db: Session = Depends(get_db)):
    """Legacy/API-key admin provisioning endpoint retained for compatibility."""
    raw_key = new_org_api_key()
    industry = payload.industry if payload.industry in PRESETS else "custom"
    org = Organization(
        name=payload.name,
        industry=industry,
        api_key_hash=hash_api_key(raw_key),
    )
    db.add(org)
    db.commit()
    db.refresh(org)

    preset = PRESETS[industry]
    replace_active_profile(db, org.id, preset["name"], preset)
    return OrganizationCreated(id=org.id, name=org.name, industry=org.industry, api_key=raw_key)


@router.get("/overview")
def admin_overview(
    _: Principal = Depends(require_superuser),
    db: Session = Depends(get_db),
):
    organizations = db.scalar(
        select(func.count(Organization.id)).where(Organization.name != SYSTEM_ORG_NAME)
    ) or 0
    users = db.scalar(select(func.count(User.id))) or 0
    leads = db.scalar(select(func.count(Lead.id))) or 0
    hot = db.scalar(select(func.count(Lead.id)).where(Lead.status == "Hot")) or 0
    queued = db.scalar(
        select(func.count(QualificationJob.id)).where(
            QualificationJob.status.in_(("queued", "retry", "processing"))
        )
    ) or 0
    failed = db.scalar(
        select(func.count(QualificationJob.id)).where(QualificationJob.status == "failed")
    ) or 0
    return {
        "organizations": organizations,
        "users": users,
        "leads": leads,
        "hot_leads": hot,
        "active_jobs": queued,
        "failed_jobs": failed,
    }


@router.get("/organizations")
def admin_organizations(
    _: Principal = Depends(require_superuser),
    db: Session = Depends(get_db),
):
    rows = list(db.scalars(select(Organization).order_by(Organization.created_at.desc())).all())
    result = []
    for org in rows:
        lead_count = db.scalar(
            select(func.count(Lead.id)).where(Lead.organization_id == org.id)
        ) or 0
        user_count = db.scalar(
            select(func.count(Membership.id)).where(Membership.organization_id == org.id)
        ) or 0
        active_jobs = db.scalar(
            select(func.count(QualificationJob.id)).where(
                QualificationJob.organization_id == org.id,
                QualificationJob.status.in_(("queued", "retry", "processing")),
            )
        ) or 0
        result.append({
            "id": org.id,
            "name": org.name,
            "industry": org.industry,
            "plan": org.plan,
            "subscription_status": org.subscription_status,
            "lead_count": lead_count,
            "user_count": user_count,
            "active_jobs": active_jobs,
            "is_internal": org.name == SYSTEM_ORG_NAME,
            "created_at": org.created_at,
        })
    return result


@router.patch("/organizations/{organization_id}")
def admin_update_organization(
    organization_id: str,
    payload: AdminOrganizationUpdate,
    _: Principal = Depends(require_superuser),
    db: Session = Depends(get_db),
):
    org = db.get(Organization, organization_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    if payload.plan is not None:
        org.plan = payload.plan
    if payload.subscription_status is not None:
        org.subscription_status = payload.subscription_status.strip() or "inactive"
    db.commit()
    db.refresh(org)
    return {
        "id": org.id,
        "name": org.name,
        "plan": org.plan,
        "subscription_status": org.subscription_status,
    }


@router.get("/users")
def admin_users(
    _: Principal = Depends(require_superuser),
    db: Session = Depends(get_db),
):
    memberships = db.execute(
        select(User, Membership, Organization)
        .join(Membership, Membership.user_id == User.id)
        .join(Organization, Organization.id == Membership.organization_id)
        .order_by(User.created_at.desc(), Membership.id)
    ).all()
    return [{
        "id": user.id,
        "login": user.email,
        "is_active": user.is_active,
        "role": membership.role,
        "organization_id": org.id,
        "organization_name": org.name,
        "created_at": user.created_at,
    } for user, membership, org in memberships]


@router.patch("/users/{user_id}")
def admin_update_user(
    user_id: str,
    payload: AdminUserUpdate,
    principal: Principal = Depends(require_superuser),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if principal.user and user.id == principal.user.id and payload.is_active is False:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own superuser account")
    user.is_active = payload.is_active
    db.commit()
    return {"id": user.id, "login": user.email, "is_active": user.is_active}


@router.get("/jobs")
def admin_jobs(
    limit: int = Query(default=100, ge=1, le=250),
    _: Principal = Depends(require_superuser),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(QualificationJob, Organization, Lead)
        .join(Organization, Organization.id == QualificationJob.organization_id)
        .join(Lead, Lead.id == QualificationJob.lead_id)
        .order_by(QualificationJob.created_at.desc())
        .limit(limit)
    ).all()
    return [{
        "id": job.id,
        "status": job.status,
        "attempts": job.attempts,
        "max_attempts": job.max_attempts,
        "last_error": job.last_error,
        "organization_id": org.id,
        "organization_name": org.name,
        "lead_id": lead.id,
        "lead_name": lead.name or lead.company or "Unnamed lead",
        "created_at": job.created_at,
        "completed_at": job.completed_at,
    } for job, org, lead in rows]
