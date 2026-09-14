
import json
from datetime import datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import (
    Lead,
    LeadAssignment,
    LeadLifecycle,
    Membership,
    MembershipHierarchy,
    Organization,
    User,
)
from app.security import Principal, hash_password
from app.services.access import lead_is_visible
from app.services.imports import import_contacts, parse_csv, row_to_contact
from app.services.outreach import (
    claim_due_task,
    complete_task,
    create_agent_access,
    create_default_sequence,
    enroll_lead,
)


def memory_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def make_user(db, org, email, role):
    user = User(email=email, password_hash=hash_password("password-123"))
    db.add(user)
    db.flush()
    membership = Membership(user_id=user.id, organization_id=org.id, role=role)
    db.add(membership)
    db.flush()
    return user, membership


def test_manager_visibility_is_downward_not_sideways():
    db = memory_session()
    org = Organization(name="Acme", industry="custom", api_key_hash="a" * 64)
    db.add(org)
    db.flush()

    manager, manager_m = make_user(db, org, "manager@example.com", "manager")
    rep, rep_m = make_user(db, org, "rep@example.com", "user")
    sibling, sibling_m = make_user(db, org, "other@example.com", "user")
    db.add(MembershipHierarchy(
        organization_id=org.id,
        parent_membership_id=manager_m.id,
        child_membership_id=rep_m.id,
    ))

    rep_lead = Lead(organization_id=org.id, name="Rep lead")
    sibling_lead = Lead(organization_id=org.id, name="Sibling lead")
    db.add_all([rep_lead, sibling_lead])
    db.flush()
    db.add_all([
        LeadAssignment(organization_id=org.id, lead_id=rep_lead.id, owner_user_id=rep.id),
        LeadAssignment(organization_id=org.id, lead_id=sibling_lead.id, owner_user_id=sibling.id),
    ])
    db.commit()

    principal = Principal(organization=org, user=manager, role="manager", auth_type="session")
    assert lead_is_visible(db, principal, rep_lead) is True
    assert lead_is_visible(db, principal, sibling_lead) is False


def test_csv_import_maps_columns_keeps_extra_fields_and_dedupes():
    db = memory_session()
    org = Organization(name="CSV Co", industry="custom", api_key_hash="b" * 64)
    db.add(org)
    db.commit()

    text = "First Name,Last Name,Email,Phone,Company,Campaign\nAda,Lovelace,ada@example.com,5551112222,Analytical,Spring\n"
    rows, mapping = parse_csv(text)
    contacts = [row_to_contact(row, mapping, "CSV import") for row in rows]
    batch = import_contacts(
        db, org, contacts, source_type="csv", source_name="prospects.csv", auto_qualify=False
    )
    assert batch.imported_rows == 1
    lead = db.scalar(select(Lead).where(Lead.organization_id == org.id))
    assert lead.name == "Ada Lovelace"
    assert lead.email == "ada@example.com"
    assert json.loads(lead.payload_json)["Campaign"] == "Spring"

    batch2 = import_contacts(
        db, org, contacts, source_type="csv", source_name="prospects.csv", auto_qualify=False
    )
    assert batch2.imported_rows == 0
    assert batch2.duplicate_rows == 1


def test_agent_queue_staggers_followup_and_hands_off_on_reply():
    db = memory_session()
    org = Organization(name="Nurture Co", industry="custom", api_key_hash="c" * 64)
    db.add(org)
    db.flush()
    lead = Lead(
        organization_id=org.id,
        name="Jordan",
        email="jordan@example.com",
        phone="5552223333",
        status="Warm",
        score=7,
    )
    db.add(lead)
    db.commit()

    sequence = create_default_sequence(db, org.id)
    enrollment = enroll_lead(db, sequence, lead)
    access, raw = create_agent_access(db, org.id, "OpenClaw")

    first = claim_due_task(db, access, "email")
    assert first is not None
    assert first.channel == "email"
    complete_task(db, first, status="replied", reply_text="Can we talk today?", buying_intent=True)

    db.refresh(lead)
    lifecycle = db.scalar(select(LeadLifecycle).where(LeadLifecycle.lead_id == lead.id))
    assert lead.status == "Hot"
    assert lifecycle.automation_state == "paused"
    assert "buying intent" in lifecycle.handoff_reason.lower()

def test_outreach_skips_email_when_only_phone_is_available():
    db = memory_session()
    org = Organization(name="Phone Only", industry="custom", api_key_hash="d" * 64)
    db.add(org)
    db.flush()
    lead = Lead(
        organization_id=org.id,
        name="Phone Prospect",
        phone="5553334444",
        status="Warm",
        score=6,
    )
    db.add(lead)
    db.commit()

    sequence = create_default_sequence(db, org.id)
    enroll_lead(db, sequence, lead)
    access, _ = create_agent_access(db, org.id, "OpenClaw")

    task = claim_due_task(db, access, "email")
    assert task is None

    from app.models import OutreachTask
    first = db.scalar(
        select(OutreachTask).where(
            OutreachTask.lead_id == lead.id,
            OutreachTask.channel == "email",
        ).order_by(OutreachTask.created_at.asc())
    )
    assert first.status == "skipped"
    assert "missing" in (first.last_error or "").lower()

