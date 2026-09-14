import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Lead, Organization, QualificationProfile
from app.services.notifications import sign_body
from app.services.queue import claim_next_job, enqueue_qualification, process_qualification_job, retry_delay_seconds


class FakeProvider:
    def complete_json(self, system, user):
        return {
            "score": 9,
            "status": "Hot",
            "next_action": "Call now",
            "reason": "Requested a quote this week.",
        }


def memory_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_queued_job_qualifies_lead():
    db = memory_session()
    org = Organization(name="Example", industry="custom", api_key_hash="a" * 64)
    db.add(org)
    db.flush()
    profile = QualificationProfile(
        organization_id=org.id,
        name="Custom",
        rules_json=json.dumps({
            "name": "Custom",
            "business_context": "",
            "high_intent_signals": ["asks for quote"],
            "medium_intent_signals": [],
            "disqualifiers": [],
            "required_questions": [],
            "custom_instructions": "",
        }),
        active=True,
    )
    lead = Lead(organization_id=org.id, name="Jordan", notes="Please quote this week")
    db.add_all([profile, lead])
    db.commit()

    queued = enqueue_qualification(db, org, lead)
    assert queued.status == "queued"

    job = claim_next_job(db)
    assert job.id == queued.id
    assert job.status == "processing"
    assert job.attempts == 1

    result_lead = process_qualification_job(db, job, provider=FakeProvider())
    assert result_lead.status == "Hot"
    assert result_lead.score == 9
    db.refresh(job)
    assert job.status == "succeeded"


def test_retry_backoff_increases_and_is_bounded():
    assert retry_delay_seconds(1) == 5
    assert retry_delay_seconds(2) == 20
    assert retry_delay_seconds(20) == 300


def test_webhook_signature_is_deterministic():
    body = b'{"event":"lead.hot"}'
    assert sign_body("secret", body) == sign_body("secret", body)
    assert sign_body("different", body) != sign_body("secret", body)


def test_dashboard_contains_automation_controls():
    html = (Path(__file__).parents[1] / "app" / "static" / "index.html").read_text()
    assert 'data-view="automations"' in html
    assert 'id="createInbound"' in html
    assert 'id="notificationForm"' in html
