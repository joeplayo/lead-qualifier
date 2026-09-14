
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import CRMConnection
from app.schemas import CRMConnectionCreate, CRMConnectionRead, CRMImportRequest, ImportResult
from app.security import require_session_user
from app.services.access import descendant_user_ids, normalized_role
from app.services.imports import import_contacts

router = APIRouter(prefix="/integrations", tags=["integrations"])


def _read(row: CRMConnection) -> CRMConnectionRead:
    try:
        config = json.loads(row.config_json or "{}")
    except Exception:
        config = {}
    try:
        secret = json.loads(row.secret_json or "{}")
    except Exception:
        secret = {}
    return CRMConnectionRead(
        id=row.id,
        provider=row.provider,
        name=row.name,
        status=row.status,
        config=config if isinstance(config, dict) else {},
        has_secret=bool(secret),
        last_synced_at=row.last_synced_at,
        created_at=row.created_at,
    )


@router.get("/crm", response_model=list[CRMConnectionRead])
def list_crm_connections(principal=Depends(require_session_user), db: Session = Depends(get_db)):
    rows = list(db.scalars(
        select(CRMConnection)
        .where(CRMConnection.organization_id == principal.organization.id)
        .order_by(CRMConnection.created_at.desc())
    ).all())
    return [_read(r) for r in rows]


@router.post("/crm", response_model=CRMConnectionRead, status_code=201)
def create_crm_connection(payload: CRMConnectionCreate, principal=Depends(require_session_user), db: Session = Depends(get_db)):
    if normalized_role(principal.role) not in {"admin", "superuser"}:
        raise HTTPException(status_code=403, detail="Admin access required")
    row = CRMConnection(
        organization_id=principal.organization.id,
        provider=payload.provider,
        name=payload.name.strip() or payload.provider.title(),
        status="configured",
        config_json=json.dumps(payload.config),
        secret_json=json.dumps(payload.secret),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _read(row)


@router.delete("/crm/{connection_id}", status_code=204)
def delete_crm_connection(connection_id: str, principal=Depends(require_session_user), db: Session = Depends(get_db)):
    if normalized_role(principal.role) not in {"admin", "superuser"}:
        raise HTTPException(status_code=403, detail="Admin access required")
    row = db.scalar(select(CRMConnection).where(
        CRMConnection.id == connection_id,
        CRMConnection.organization_id == principal.organization.id,
    ))
    if not row:
        raise HTTPException(status_code=404, detail="CRM connection not found")
    db.delete(row)
    db.commit()


@router.post("/crm/{connection_id}/import", response_model=ImportResult)
def import_from_crm(
    connection_id: str,
    payload: CRMImportRequest,
    principal=Depends(require_session_user),
    db: Session = Depends(get_db),
):
    if normalized_role(principal.role) not in {"admin", "manager", "superuser"}:
        raise HTTPException(status_code=403, detail="Manager or admin access required")
    row = db.scalar(select(CRMConnection).where(
        CRMConnection.id == connection_id,
        CRMConnection.organization_id == principal.organization.id,
    ))
    if not row:
        raise HTTPException(status_code=404, detail="CRM connection not found")
    contacts = [c.model_dump() for c in payload.contacts]
    role = normalized_role(principal.role)
    allowed_owner_ids = None
    if role == "manager":
        allowed_owner_ids = descendant_user_ids(db, principal)
    if allowed_owner_ids is not None:
        for contact in contacts:
            requested_owner = contact.get("owner_user_id")
            if requested_owner and requested_owner not in allowed_owner_ids:
                contact["owner_user_id"] = principal.user.id
    batch = import_contacts(
        db,
        principal.organization,
        contacts,
        source_type="crm",
        source_name=row.name or row.provider,
        created_by_user_id=principal.user.id,
        auto_qualify=payload.auto_qualify,
        crm_connection=row,
    )
    row.last_synced_at = datetime.now(timezone.utc)
    row.status = "synced"
    db.commit()
    return ImportResult(
        batch_id=batch.id,
        total=batch.total_rows,
        imported=batch.imported_rows,
        duplicates=batch.duplicate_rows,
        rejected=batch.rejected_rows,
        lead_ids=getattr(batch, "_lead_ids", []),
    )
