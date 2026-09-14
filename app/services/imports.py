
from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CRMConnection, ExternalContactMap, ImportBatch, Lead, Organization
from app.services.leadops import dedupe_lead, ensure_lead_state, record_activity
from app.services.queue import enqueue_qualification


HEADER_ALIASES = {
    "name": {"name", "full name", "full_name", "contact name", "contact_name"},
    "first_name": {"first name", "first_name", "firstname"},
    "last_name": {"last name", "last_name", "lastname", "surname"},
    "company": {"company", "company name", "company_name", "organization", "account"},
    "email": {"email", "email address", "email_address", "e-mail"},
    "phone": {"phone", "phone number", "phone_number", "mobile", "mobile phone", "telephone"},
    "source": {"source", "lead source", "lead_source"},
    "notes": {"notes", "note", "description", "comments", "comment"},
}


def _norm_header(value: str) -> str:
    return " ".join((value or "").replace("-", " ").replace("_", " ").strip().lower().split())


def infer_mapping(fieldnames: list[str]) -> dict[str, str]:
    normalized = {_norm_header(f): f for f in fieldnames}
    mapping: dict[str, str] = {}
    for target, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            key = _norm_header(alias)
            if key in normalized:
                mapping[target] = normalized[key]
                break
    return mapping


def parse_csv(text: str) -> tuple[list[dict], dict[str, str]]:
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        return [], {}
    mapping = infer_mapping(list(reader.fieldnames))
    return [dict(r) for r in reader], mapping


def row_to_contact(row: dict, mapping: dict[str, str], source_name: str) -> dict:
    first = (row.get(mapping.get("first_name", ""), "") or "").strip()
    last = (row.get(mapping.get("last_name", ""), "") or "").strip()
    name = (row.get(mapping.get("name", ""), "") or "").strip() or " ".join(x for x in (first, last) if x)
    known_cols = {v for v in mapping.values()}
    attrs = {str(k): v for k, v in row.items() if k not in known_cols and v not in (None, "")}
    return {
        "name": name,
        "company": (row.get(mapping.get("company", ""), "") or "").strip(),
        "email": (row.get(mapping.get("email", ""), "") or "").strip(),
        "phone": (row.get(mapping.get("phone", ""), "") or "").strip(),
        "source": (row.get(mapping.get("source", ""), "") or "").strip() or source_name,
        "notes": (row.get(mapping.get("notes", ""), "") or "").strip(),
        "attributes": attrs,
    }


def import_contacts(
    db: Session,
    org: Organization,
    contacts: list[dict],
    *,
    source_type: str,
    source_name: str,
    created_by_user_id: str | None = None,
    auto_qualify: bool = True,
    crm_connection: CRMConnection | None = None,
) -> ImportBatch:
    batch = ImportBatch(
        organization_id=org.id,
        source_type=source_type,
        source_name=source_name,
        total_rows=len(contacts),
        created_by_user_id=created_by_user_id,
    )
    db.add(batch)
    db.flush()

    imported = duplicates = rejected = 0
    lead_ids: list[str] = []

    for contact in contacts:
        email = (contact.get("email") or "").strip()
        phone = (contact.get("phone") or "").strip()
        name = (contact.get("name") or "").strip()
        company = (contact.get("company") or "").strip()
        if not any((email, phone, name, company)):
            rejected += 1
            continue

        external_id = str(contact.get("external_id") or "").strip()
        if crm_connection and external_id:
            mapped = db.scalar(
                select(ExternalContactMap).where(
                    ExternalContactMap.crm_connection_id == crm_connection.id,
                    ExternalContactMap.external_id == external_id,
                )
            )
            if mapped:
                duplicates += 1
                continue

        duplicate = dedupe_lead(db, org.id, email=email, phone=phone)
        if duplicate:
            duplicates += 1
            if crm_connection and external_id:
                db.add(ExternalContactMap(
                    organization_id=org.id,
                    crm_connection_id=crm_connection.id,
                    external_id=external_id,
                    lead_id=duplicate.id,
                ))
                db.commit()
            continue

        attrs = contact.get("attributes") or {}
        if not isinstance(attrs, dict):
            attrs = {}
        lead = Lead(
            organization_id=org.id,
            name=name,
            company=company,
            email=email,
            phone=phone,
            source=(contact.get("source") or source_name or source_type).strip(),
            notes=(contact.get("notes") or "").strip(),
            payload_json=json.dumps(attrs),
        )
        db.add(lead)
        db.flush()
        owner_user_id = contact.get("owner_user_id") or created_by_user_id
        ensure_lead_state(db, lead, owner_user_id=owner_user_id, assigned_by_user_id=created_by_user_id)
        record_activity(
            db,
            lead,
            "lead.imported",
            f"Imported from {source_name or source_type}",
            actor_user_id=created_by_user_id,
            payload={"source_type": source_type, "batch_id": batch.id},
        )
        db.commit()
        db.refresh(lead)

        if crm_connection and external_id:
            db.add(ExternalContactMap(
                organization_id=org.id,
                crm_connection_id=crm_connection.id,
                external_id=external_id,
                lead_id=lead.id,
            ))
            db.commit()

        if auto_qualify:
            enqueue_qualification(db, org, lead)
        lead_ids.append(lead.id)
        imported += 1

    batch.imported_rows = imported
    batch.duplicate_rows = duplicates
    batch.rejected_rows = rejected
    # Stash lead ids on the transient instance for API response convenience.
    batch._lead_ids = lead_ids
    db.commit()
    db.refresh(batch)
    return batch
