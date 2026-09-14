from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import Membership, Organization, User
from app.presets import PRESETS
from app.schemas import AuthUserRead, LoginRequest, RegisterRequest, RegisterResponse
from app.security import (
    create_session,
    delete_session,
    get_principal,
    hash_api_key,
    hash_password,
    new_org_api_key,
    verify_password,
)
from app.services.profiles import replace_active_profile

router = APIRouter(prefix="/auth", tags=["auth"])

def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        settings.session_cookie_name,
        token,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        max_age=settings.session_ttl_days * 24 * 3600,
        path="/",
    )

@router.post("/register", response_model=RegisterResponse)
def register(payload: RegisterRequest, response: Response, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="Email is already registered")

    raw_key = new_org_api_key()
    industry = payload.industry if payload.industry in PRESETS else "custom"
    org = Organization(
        name=payload.organization_name.strip(),
        industry=industry,
        api_key_hash=hash_api_key(raw_key),
    )
    user = User(email=email, password_hash=hash_password(payload.password))
    db.add_all([org, user])
    db.flush()
    db.add(Membership(user_id=user.id, organization_id=org.id, role="admin"))
    replace_active_profile(db, org.id, PRESETS[industry]["name"], PRESETS[industry])
    db.commit()
    db.refresh(org)
    db.refresh(user)

    token = create_session(db, user)
    _set_cookie(response, token)
    return RegisterResponse(
        id=user.id,
        email=user.email,
        organization_id=org.id,
        organization_name=org.name,
        role="admin",
        plan=org.plan,
        subscription_status=org.subscription_status,
        api_key=raw_key,
    )

@router.post("/login", response_model=AuthUserRead)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if not user or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    membership_row = db.execute(
        select(Membership, Organization)
        .join(Organization, Organization.id == Membership.organization_id)
        .where(Membership.user_id == user.id)
        .order_by(Membership.id)
    ).first()
    if not membership_row:
        raise HTTPException(status_code=403, detail="User has no organization")
    membership, org = membership_row
    token = create_session(db, user)
    _set_cookie(response, token)
    return AuthUserRead(
        id=user.id,
        email=user.email,
        organization_id=org.id,
        organization_name=org.name,
        role=membership.role,
        plan=org.plan,
        subscription_status=org.subscription_status,
    )

@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(settings.session_cookie_name)
    delete_session(db, token)
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.status_code = 204
    return response

@router.get("/me", response_model=AuthUserRead)
def me(principal=Depends(get_principal)):
    if not principal.user:
        raise HTTPException(status_code=401, detail="Browser session required")
    org = principal.organization
    return AuthUserRead(
        id=principal.user.id,
        email=principal.user.email,
        organization_id=org.id,
        organization_name=org.name,
        role="admin" if principal.role == "owner" else (principal.role or "user"),
        plan=org.plan,
        subscription_status=org.subscription_status,
    )
