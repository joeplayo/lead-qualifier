
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import leads as leads_api
from app.db import Base
from app.models import Lead, LeadAssignment, Membership, Organization, QualificationProfile, User
from app.schemas import LeadCreate, LeadUpdate, QualificationResult
from app.security import Principal, hash_password
from app.services.provider import ProviderError


def memory_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def admin_context(db):
    org = Organization(name="Hotfix Co", industry="custom", api_key_hash="f" * 64)
    user = User(email="owner@example.com", password_hash=hash_password("password-123"))
    db.add_all([org, user])
    db.flush()
    db.add(Membership(user_id=user.id, organization_id=org.id, role="admin"))
    db.add(QualificationProfile(
        organization_id=org.id,
        name="Custom",
        rules_json="{}",
        active=True,
    ))
    db.commit()
    principal = Principal(organization=org, user=user, role="admin", auth_type="session")
    return org, user, principal


def fake_result(*args, **kwargs):
    return QualificationResult(
        score=7,
        status="Warm",
        next_action="Follow up",
        reason="Test result",
    )


def test_failed_manual_scoring_does_not_leave_a_lead(monkeypatch):
    db = memory_session()
    _, _, principal = admin_context(db)

    def fail(*args, **kwargs):
        raise ProviderError("provider unavailable")

    monkeypatch.setattr(leads_api, "qualify", fail)

    try:
        leads_api.create_and_qualify_lead(
            LeadCreate(name="Retry", email="retry@example.com"),
            principal=principal,
            db=db,
        )
        assert False, "Expected qualification to fail"
    except HTTPException as exc:
        assert exc.status_code == 502

    assert db.scalar(select(func.count(Lead.id))) == 0


def test_repeated_manual_submission_reuses_existing_contact(monkeypatch):
    db = memory_session()
    _, _, principal = admin_context(db)
    monkeypatch.setattr(leads_api, "qualify", fake_result)

    first = leads_api.create_and_qualify_lead(
        LeadCreate(name="Jordan", email="Jordan@Example.com", notes="First try"),
        principal=principal,
        db=db,
    )
    second = leads_api.create_and_qualify_lead(
        LeadCreate(name="Jordan Again", email="jordan@example.com", notes="Second try"),
        principal=principal,
        db=db,
    )

    assert first.id == second.id
    assert db.scalar(select(func.count(Lead.id))) == 1


def test_lead_can_be_edited_deduped_and_deleted():
    db = memory_session()
    org, user, principal = admin_context(db)

    keep = Lead(organization_id=org.id, name="Keep", email="same@example.com")
    copy = Lead(organization_id=org.id, name="Copy", email="SAME@example.com")
    db.add_all([keep, copy])
    db.flush()
    db.add_all([
        LeadAssignment(organization_id=org.id, lead_id=keep.id, owner_user_id=user.id),
        LeadAssignment(organization_id=org.id, lead_id=copy.id, owner_user_id=user.id),
    ])
    db.commit()

    updated = leads_api.update_lead(
        keep.id,
        LeadUpdate(company="Updated Co", phone="555-111-2222", notes="Updated notes"),
        principal=principal,
        db=db,
    )
    assert updated.company == "Updated Co"
    assert updated.phone == "555-111-2222"

    result = leads_api.delete_duplicate_copies(keep.id, principal=principal, db=db)
    assert result.deleted_count == 1
    assert db.scalar(select(func.count(Lead.id))) == 1

    deleted = leads_api.delete_lead(keep.id, principal=principal, db=db)
    assert deleted.deleted is True
    assert db.scalar(select(func.count(Lead.id))) == 0


def test_dashboard_exposes_edit_delete_and_duplicate_cleanup():
    from pathlib import Path
    html = (Path(__file__).parents[1] / "app" / "static" / "index.html").read_text()
    assert 'id="saveLeadBtn"' in html
    assert 'id="deleteLeadBtn"' in html
    assert 'id="dedupeLeadBtn"' in html
    assert "LeadLift" in html
