
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Lead, LeadAssignment, Membership, MembershipHierarchy, User
from app.security import Principal

ADMIN_ROLES = {"admin", "owner", "superuser"}
MANAGER_ROLES = {"manager"}
USER_ROLES = {"user", "member"}

def normalized_role(role: str | None) -> str:
    role = (role or "user").lower()
    if role == "owner":
        return "admin"
    if role == "member":
        return "user"
    return role

def membership_for_principal(db: Session, principal: Principal) -> Membership | None:
    if not principal.user:
        return None
    return db.scalar(
        select(Membership).where(
            Membership.user_id == principal.user.id,
            Membership.organization_id == principal.organization.id,
        )
    )

def descendant_user_ids(db: Session, principal: Principal) -> set[str]:
    if not principal.user:
        return set()
    role = normalized_role(principal.role)
    if role in ADMIN_ROLES:
        return set(db.scalars(
            select(Membership.user_id).where(Membership.organization_id == principal.organization.id)
        ).all())
    if role not in MANAGER_ROLES:
        return {principal.user.id}

    membership = membership_for_principal(db, principal)
    if not membership:
        return {principal.user.id}

    visible_memberships = {membership.id}
    frontier = {membership.id}
    while frontier:
        children = set(db.scalars(
            select(MembershipHierarchy.child_membership_id).where(
                MembershipHierarchy.organization_id == principal.organization.id,
                MembershipHierarchy.parent_membership_id.in_(frontier),
            )
        ).all())
        children -= visible_memberships
        if not children:
            break
        visible_memberships |= children
        frontier = children

    return set(db.scalars(
        select(Membership.user_id).where(Membership.id.in_(visible_memberships))
    ).all())

def can_manage_user(db: Session, principal: Principal, target_user_id: str) -> bool:
    role = normalized_role(principal.role)
    if role in ADMIN_ROLES:
        return True
    if role == "manager":
        return target_user_id in descendant_user_ids(db, principal)
    return principal.user is not None and principal.user.id == target_user_id

def lead_is_visible(db: Session, principal: Principal, lead: Lead) -> bool:
    if principal.auth_type == "api_key":
        return lead.organization_id == principal.organization.id
    role = normalized_role(principal.role)
    if role in ADMIN_ROLES:
        return lead.organization_id == principal.organization.id
    assignment = db.scalar(select(LeadAssignment).where(LeadAssignment.lead_id == lead.id))
    return bool(assignment and assignment.owner_user_id in descendant_user_ids(db, principal))

def visible_lead_ids_subquery(db: Session, principal: Principal):
    # Used only for browser-session principals. API keys/admins should skip this filter.
    visible_users = descendant_user_ids(db, principal)
    return select(LeadAssignment.lead_id).where(
        LeadAssignment.organization_id == principal.organization.id,
        LeadAssignment.owner_user_id.in_(visible_users),
    )
