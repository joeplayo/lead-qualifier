from fastapi import APIRouter
from app.presets import PRESETS

router = APIRouter(prefix="/presets", tags=["presets"])

@router.get("")
def list_presets():
    return PRESETS
