from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Membership, Organization, User
from app.security import _principal_from_session, create_session, hash_api_key, hash_password, new_org_api_key, verify_password
from app.services.superuser import ensure_local_superuser


def memory_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_local_superuser_bootstrap_is_idempotent():
    from app.config import settings

    db = memory_session()
    first = ensure_local_superuser(db)
    second = ensure_local_superuser(db)

    assert first is not None
    assert second is not None
    assert first.id == second.id
    assert first.email == settings.bootstrap_superuser_username
    assert verify_password(settings.bootstrap_superuser_password, first.password_hash)

    memberships = list(
        db.scalars(select(Membership).where(Membership.user_id == first.id)).all()
    )
    assert len(memberships) == 1
    assert memberships[0].role == "superuser"


def test_superuser_can_target_any_organization():
    db = memory_session()
    admin = ensure_local_superuser(db)
    customer = Organization(
        name="Customer",
        industry="custom",
        api_key_hash=hash_api_key(new_org_api_key()),
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)

    token = create_session(db, admin)
    principal = _principal_from_session(db, token, customer.id)

    assert principal is not None
    assert principal.organization.id == customer.id
    assert principal.user.id == admin.id
    assert principal.role == "superuser"


def test_regular_user_cannot_target_unrelated_organization():
    db = memory_session()
    own = Organization(name="Own", industry="custom", api_key_hash=hash_api_key(new_org_api_key()))
    other = Organization(name="Other", industry="custom", api_key_hash=hash_api_key(new_org_api_key()))
    user = User(email="owner@example.com", password_hash=hash_password("a-very-good-password"))
    db.add_all([own, other, user])
    db.flush()
    db.add(Membership(user_id=user.id, organization_id=own.id, role="owner"))
    db.commit()

    token = create_session(db, user)
    assert _principal_from_session(db, token, other.id) is None


def test_admin_ui_and_dashboard_superuser_link_present():
    base = Path(__file__).parents[1] / "app"
    admin_html = (base / "admin_static" / "index.html").read_text()
    dashboard_html = (base / "static" / "index.html").read_text()

    assert "Superuser access" in admin_html
    assert "/api/v1/admin/overview" in admin_html
    assert 'id="adminNav"' in dashboard_html
    assert "X-Organization-ID" in dashboard_html
