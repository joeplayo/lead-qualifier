import json
from pathlib import Path
from datetime import datetime, timezone

from app.api.leads import _detail_model
from app.models import Lead
from app.schemas import LeadStats


def test_lead_detail_exposes_custom_attributes():
    lead = Lead(
        id="lead-1",
        organization_id="org-1",
        name="Jordan",
        company="Acme",
        email="jordan@example.com",
        phone="555-0100",
        source="Website",
        notes="Needs a quote",
        payload_json=json.dumps({"zip": "07001", "budget_band": "known"}),
        score=8,
        status="Hot",
        next_action="Call",
        reason="Clear quote request",
        created_at=datetime.now(timezone.utc),
        qualified_at=datetime.now(timezone.utc),
    )
    detail = _detail_model(lead)
    assert detail.attributes["zip"] == "07001"
    assert detail.score == 8


def test_stats_schema_accepts_empty_average():
    stats = LeadStats(total=0, hot=0, warm=0, cold=0, pending=0, average_score=None)
    assert stats.average_score is None


def test_dashboard_contains_v3_inbox_and_rules_editor():
    html = (Path(__file__).parents[1] / "app" / "static" / "index.html").read_text()
    assert 'id="leadSearch"' in html
    assert 'id="leadDrawer"' in html
    assert 'id="profileForm"' in html
