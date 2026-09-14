import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass

from fastapi import Cookie, Depends, Header, HTTPException, Request
from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import AuthSession, Membership, Organization, User

PBKDF2_ITERATIONS = 310_000

def hash_api_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

def new_org_api_key() -> str:
    return "ls_" + secrets.token_urlsafe(30)

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(digest).decode()}"

def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, iterations, salt_b64, digest_b64 = encoded.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_b64.encode())
        expected = base64.urlsafe_b64decode(digest_b64.encode())
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False

def new_session_token() -> str:
    return secrets.token_urlsafe(32)

def session_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def create_session(db: Session, user: User) -> str:
    raw = new_session_token()
    expires = datetime.now(timezone.utc) + timedelta(days=settings.session_ttl_days)
    db.add(AuthSession(user_id=user.id, token_hash=session_hash(raw), expires_at=expires))
    db.commit()
    return raw

def delete_session(db: Session, raw_token: str | None) -> None:
    if not raw_token:
        return
    db.execute(delete(AuthSession).where(AuthSession.token_hash == session_hash(raw_token)))
    db.commit()

def require_admin(x_admin_key: str | None = Header(default=None)) -> None:
    if not settings.admin_api_key:
        raise HTTPException(status_code=503, detail="ADMIN_API_KEY is not configured")
    if not x_admin_key or not hmac.compare_digest(x_admin_key, settings.admin_api_key):
        raise HTTPException(status_code=401, detail="Invalid admin key")



def _user_is_superuser(db: Session, user_id: str) -> bool:
    return db.scalar(
        select(Membership.id).where(
            Membership.user_id == user_id,
            Membership.role == "superuser",
        ).limit(1)
    ) is not None



@dataclass
class Principal:
    organization: Organization
    user: User | None = None
    role: str | None = None
    auth_type: str = "api_key"

def _principal_from_session(db: Session, token: str, requested_org_id: str | None) -> Principal | None:
    now = datetime.now(timezone.utc)
    row = db.execute(
        select(AuthSession, User)
        .join(User, User.id == AuthSession.user_id)
        .where(AuthSession.token_hash == session_hash(token), User.is_active.is_(True))
    ).first()
    if not row:
        return None
    auth_session, user = row
    expires = auth_session.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= now:
        db.delete(auth_session)
        db.commit()
        return None

    is_superuser = _user_is_superuser(db, user.id)

    # A superuser may intentionally act in any organization by sending X-Organization-ID.
    if requested_org_id and is_superuser:
        org = db.get(Organization, requested_org_id)
        if not org:
            return None
        return Principal(organization=org, user=user, role="superuser", auth_type="session")

    query = select(Membership, Organization).join(
        Organization, Organization.id == Membership.organization_id
    ).where(Membership.user_id == user.id)
    if requested_org_id:
        query = query.where(Membership.organization_id == requested_org_id)
    if is_superuser:
        query = query.order_by((Membership.role == "superuser").desc(), Membership.id)
    else:
        query = query.order_by(Membership.id)
    membership_row = db.execute(query).first()
    if not membership_row:
        return None
    membership, org = membership_row
    role = "superuser" if is_superuser else membership.role
    return Principal(organization=org, user=user, role=role, auth_type="session")

def get_principal(
    request: Request,
    x_org_key: str | None = Header(default=None),
    x_organization_id: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Principal:
    if x_org_key:
        key_hash = hash_api_key(x_org_key)
        org = db.scalar(select(Organization).where(Organization.api_key_hash == key_hash))
        if not org:
            raise HTTPException(status_code=401, detail="Invalid organization key")
        return Principal(organization=org, auth_type="api_key")

    token = request.cookies.get(settings.session_cookie_name)
    if token:
        principal = _principal_from_session(db, token, x_organization_id)
        if principal:
            return principal
    raise HTTPException(status_code=401, detail="Authentication required")

def get_current_org(principal: Principal = Depends(get_principal)) -> Organization:
    return principal.organization

def require_session_user(principal: Principal = Depends(get_principal)) -> Principal:
    if principal.auth_type != "session" or not principal.user:
        raise HTTPException(status_code=401, detail="Browser session required")
    return principal


def require_superuser(
    principal: Principal = Depends(require_session_user),
    db: Session = Depends(get_db),
) -> Principal:
    if not principal.user or not _user_is_superuser(db, principal.user.id):
        raise HTTPException(status_code=403, detail="Superuser access required")
    principal.role = "superuser"
    return principal
