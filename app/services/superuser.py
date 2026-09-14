from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Membership, Organization, User
from app.presets import PRESETS
from app.security import hash_api_key, hash_password, new_org_api_key, verify_password
from app.services.profiles import replace_active_profile


SYSTEM_ORG_NAME = "LeadSignal Administration"


def ensure_local_superuser(db: Session, *, force: bool = False) -> User | None:
    """Create the requested local superuser once, without weakening normal signup rules.

    The automatic bootstrap is intentionally limited to SQLite/local-style deployments.
    Production deployments should provision a superuser explicitly and disable this bootstrap.
    """
    if not force and not settings.bootstrap_superuser_enabled:
        return None
    if not force and not settings.database_url.startswith("sqlite"):
        return None

    username = settings.bootstrap_superuser_username.strip()
    password = settings.bootstrap_superuser_password
    if not username or not password:
        return None

    user = db.scalar(select(User).where(User.email == username))
    if user:
        membership = db.scalar(
            select(Membership).where(
                Membership.user_id == user.id,
                Membership.role == "superuser",
            )
        )
        if membership:
            return user
        if not verify_password(password, user.password_hash):
            raise RuntimeError(
                f"Cannot bootstrap superuser '{username}': that login already belongs to a non-superuser account."
            )

    org = db.scalar(select(Organization).where(Organization.name == SYSTEM_ORG_NAME))
    if not org:
        org = Organization(
            name=SYSTEM_ORG_NAME,
            industry="custom",
            api_key_hash=hash_api_key(new_org_api_key()),
            plan="growth",
            subscription_status="internal",
        )
        db.add(org)
        db.flush()
        replace_active_profile(db, org.id, PRESETS["custom"]["name"], PRESETS["custom"])

    if not user:
        # The existing schema uses the email column as the unique login identifier.
        # Storing "admin" here avoids a destructive migration while requiring no email address.
        user = User(email=username, password_hash=hash_password(password), is_active=True)
        db.add(user)
        db.flush()

    existing = db.scalar(
        select(Membership).where(
            Membership.user_id == user.id,
            Membership.organization_id == org.id,
        )
    )
    if existing:
        existing.role = "superuser"
    else:
        db.add(Membership(user_id=user.id, organization_id=org.id, role="superuser"))

    db.commit()
    db.refresh(user)
    return user
