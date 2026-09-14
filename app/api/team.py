
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Membership, MembershipHierarchy, User
from app.schemas import TeamUserCreate, TeamUserRead, TeamUserUpdate
from app.security import require_session_user, hash_password
from app.services.access import descendant_user_ids, membership_for_principal, normalized_role

router = APIRouter(prefix="/team", tags=["team"])


def _row_to_read(db: Session, membership: Membership, user: User) -> TeamUserRead:
    parent = db.scalar(
        select(MembershipHierarchy).where(
            MembershipHierarchy.organization_id == membership.organization_id,
            MembershipHierarchy.child_membership_id == membership.id,
        )
    )
    manager_user_id = None
    if parent and parent.parent_membership_id:
        manager = db.get(Membership, parent.parent_membership_id)
        manager_user_id = manager.user_id if manager else None
    return TeamUserRead(
        id=user.id,
        email=user.email,
        role=normalized_role(membership.role),
        manager_user_id=manager_user_id,
        is_active=user.is_active,
    )


@router.get("/users", response_model=list[TeamUserRead])
def list_team_users(principal=Depends(require_session_user), db: Session = Depends(get_db)):
    role = normalized_role(principal.role)
    if role == "user":
        ids = {principal.user.id}
    elif role == "manager":
        ids = descendant_user_ids(db, principal)
    else:
        ids = set(db.scalars(
            select(Membership.user_id).where(Membership.organization_id == principal.organization.id)
        ).all())
    if not ids:
        return []
    rows = db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(
            Membership.organization_id == principal.organization.id,
            Membership.user_id.in_(ids),
        )
        .order_by(User.email.asc())
    ).all()
    return [_row_to_read(db, membership, user) for membership, user in rows]


@router.post("/users", response_model=TeamUserRead, status_code=201)
def create_team_user(payload: TeamUserCreate, principal=Depends(require_session_user), db: Session = Depends(get_db)):
    if normalized_role(principal.role) not in {"admin", "superuser"}:
        raise HTTPException(status_code=403, detail="Admin access required")
    email = payload.email.strip().lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="Email is already registered")

    user = User(email=email, password_hash=hash_password(payload.password), is_active=True)
    db.add(user)
    db.flush()
    membership = Membership(
        user_id=user.id,
        organization_id=principal.organization.id,
        role=payload.role,
    )
    db.add(membership)
    db.flush()

    if payload.manager_user_id:
        manager_membership = db.scalar(
            select(Membership).where(
                Membership.organization_id == principal.organization.id,
                Membership.user_id == payload.manager_user_id,
                Membership.role.in_(("manager", "admin", "owner")),
            )
        )
        if not manager_membership:
            raise HTTPException(status_code=422, detail="Manager must be a manager or admin in this organization")
        db.add(MembershipHierarchy(
            organization_id=principal.organization.id,
            parent_membership_id=manager_membership.id,
            child_membership_id=membership.id,
        ))

    db.commit()
    db.refresh(user)
    return _row_to_read(db, membership, user)


@router.patch("/users/{user_id}", response_model=TeamUserRead)
def update_team_user(user_id: str, payload: TeamUserUpdate, principal=Depends(require_session_user), db: Session = Depends(get_db)):
    if normalized_role(principal.role) not in {"admin", "superuser"}:
        raise HTTPException(status_code=403, detail="Admin access required")
    membership = db.scalar(
        select(Membership).where(
            Membership.organization_id == principal.organization.id,
            Membership.user_id == user_id,
        )
    )
    user = db.get(User, user_id)
    if not membership or not user:
        raise HTTPException(status_code=404, detail="User not found")
    if normalized_role(membership.role) == "admin" and user.id == principal.user.id:
        if payload.role and payload.role != "admin":
            raise HTTPException(status_code=409, detail="You cannot demote your own admin account")

    if payload.role is not None:
        membership.role = payload.role
    if payload.is_active is not None:
        if user.id == principal.user.id and not payload.is_active:
            raise HTTPException(status_code=409, detail="You cannot disable your own account")
        user.is_active = payload.is_active

    hierarchy = db.scalar(
        select(MembershipHierarchy).where(
            MembershipHierarchy.organization_id == principal.organization.id,
            MembershipHierarchy.child_membership_id == membership.id,
        )
    )
    if payload.manager_user_id is not None:
        if payload.manager_user_id == "":
            if hierarchy:
                db.delete(hierarchy)
        else:
            manager_membership = db.scalar(
                select(Membership).where(
                    Membership.organization_id == principal.organization.id,
                    Membership.user_id == payload.manager_user_id,
                    Membership.role.in_(("manager", "admin", "owner")),
                )
            )
            if not manager_membership or manager_membership.id == membership.id:
                raise HTTPException(status_code=422, detail="Invalid manager")
            if hierarchy:
                hierarchy.parent_membership_id = manager_membership.id
            else:
                db.add(MembershipHierarchy(
                    organization_id=principal.organization.id,
                    parent_membership_id=manager_membership.id,
                    child_membership_id=membership.id,
                ))
    db.commit()
    return _row_to_read(db, membership, user)
