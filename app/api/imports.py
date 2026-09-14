
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import ImportResult
from app.security import require_session_user
from app.services.imports import import_contacts, parse_csv, row_to_contact

router = APIRouter(prefix="/imports", tags=["imports"])


@router.post("/csv", response_model=ImportResult)
async def import_csv(
    request: Request,
    source_name: str = Query(default="CSV import", max_length=160),
    auto_qualify: bool = Query(default=True),
    principal=Depends(require_session_user),
    db: Session = Depends(get_db),
):
    raw = await request.body()
    if not raw:
        raise HTTPException(status_code=422, detail="CSV file is empty")
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="CSV file exceeds 10 MB")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="CSV must be UTF-8 encoded") from exc

    rows, mapping = parse_csv(text)
    if not rows:
        raise HTTPException(status_code=422, detail="CSV has no data rows")
    if not any(k in mapping for k in ("name", "first_name", "last_name", "email", "phone", "company")):
        raise HTTPException(
            status_code=422,
            detail="Could not identify lead columns. Include headers such as name, email, phone, or company.",
        )

    contacts = [row_to_contact(row, mapping, source_name) for row in rows]
    batch = import_contacts(
        db,
        principal.organization,
        contacts,
        source_type="csv",
        source_name=source_name,
        created_by_user_id=principal.user.id,
        auto_qualify=auto_qualify,
    )
    return ImportResult(
        batch_id=batch.id,
        total=batch.total_rows,
        imported=batch.imported_rows,
        duplicates=batch.duplicate_rows,
        rejected=batch.rejected_rows,
        lead_ids=getattr(batch, "_lead_ids", []),
    )
