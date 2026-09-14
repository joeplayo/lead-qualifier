import json
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import QualificationProfile
from app.presets import PRESETS

def active_profile_for_org(db: Session, organization_id: str) -> QualificationProfile | None:
    return db.scalar(
        select(QualificationProfile)
        .where(
            QualificationProfile.organization_id == organization_id,
            QualificationProfile.active.is_(True),
        )
        .order_by(QualificationProfile.created_at.desc())
    )

def profile_payload(profile: QualificationProfile) -> dict:
    return json.loads(profile.rules_json)

def replace_active_profile(db: Session, organization_id: str, name: str, payload: dict) -> QualificationProfile:
    existing = db.scalars(
        select(QualificationProfile).where(
            QualificationProfile.organization_id == organization_id,
            QualificationProfile.active.is_(True),
        )
    ).all()
    for item in existing:
        item.active = False

    profile = QualificationProfile(
        organization_id=organization_id,
        name=name,
        rules_json=json.dumps(payload),
        active=True,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile

def preset_or_404(name: str) -> dict:
    if name not in PRESETS:
        raise KeyError(name)
    return PRESETS[name]
