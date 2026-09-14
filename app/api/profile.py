from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Organization
from app.presets import PRESETS
from app.schemas import ProfileRead, ProfileUpdate
from app.security import get_current_org
from app.services.profiles import active_profile_for_org, profile_payload, replace_active_profile

router = APIRouter(prefix="/profile", tags=["profile"])

def _read_model(profile) -> ProfileRead:
    payload = profile_payload(profile)
    return ProfileRead(id=profile.id, **payload)

@router.get("", response_model=ProfileRead)
def get_profile(
    org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    profile = active_profile_for_org(db, org.id)
    if not profile:
        raise HTTPException(status_code=404, detail="No active qualification profile")
    return _read_model(profile)

@router.put("", response_model=ProfileRead)
def update_profile(
    payload: ProfileUpdate,
    org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    data = payload.model_dump()
    profile = replace_active_profile(db, org.id, payload.name, data)
    return _read_model(profile)

@router.post("/preset/{preset_name}", response_model=ProfileRead)
def use_preset(
    preset_name: str,
    org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    preset = PRESETS.get(preset_name)
    if not preset:
        raise HTTPException(status_code=404, detail="Unknown preset")
    profile = replace_active_profile(db, org.id, preset["name"], preset)
    org.industry = preset_name
    db.commit()
    return _read_model(profile)
