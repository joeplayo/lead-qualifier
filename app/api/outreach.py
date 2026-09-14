
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import (
    AgentAccessToken,
    Lead,
    LeadActivity,
    LeadAssignment,
    LeadLifecycle,
    OutreachSequence,
    OutreachStep,
    OutreachTask,
)
from app.schemas import (
    AgentAccessCreate,
    AgentAccessCreated,
    AgentTaskComplete,
    EnrollRequest,
    LeadOpsRead,
    OutreachSequenceCreate,
    OutreachSequenceRead,
    OutreachTaskRead,
)
from app.security import get_principal, require_session_user
from app.services.access import lead_is_visible, normalized_role
from app.services.leadops import ensure_lead_state
from app.services.notifications import send_handoff_notification
from app.services.outreach import (
    claim_due_task,
    complete_task,
    create_agent_access,
    create_default_sequence,
    enroll_lead,
    get_agent_access,
)

router = APIRouter(prefix="/outreach", tags=["outreach"])
agent_router = APIRouter(prefix="/agent", tags=["agent"])


def _paid(org) -> bool:
    return org.plan in {"starter", "growth"} and org.subscription_status in {"active", "trialing"}


def _sequence_read(db: Session, seq: OutreachSequence) -> OutreachSequenceRead:
    steps = list(db.scalars(
        select(OutreachStep).where(OutreachStep.sequence_id == seq.id).order_by(OutreachStep.position.asc())
    ).all())
    return OutreachSequenceRead(
        id=seq.id,
        name=seq.name,
        active=seq.active,
        mode=seq.mode,
        stop_on_reply=seq.stop_on_reply,
        steps=[
            {
                "id": s.id,
                "position": s.position,
                "channel": s.channel,
                "delay_minutes": s.delay_minutes,
                "instructions": s.instructions,
                "active": s.active,
            }
            for s in steps
        ],
    )




@router.post("/sequences/default", response_model=OutreachSequenceRead)
def ensure_default_sequence(principal=Depends(require_session_user), db: Session = Depends(get_db)):
    seq = create_default_sequence(db, principal.organization.id)
    return _sequence_read(db, seq)


@router.get("/sequences", response_model=list[OutreachSequenceRead])
def list_sequences(principal=Depends(require_session_user), db: Session = Depends(get_db)):
    rows = list(db.scalars(
        select(OutreachSequence)
        .where(OutreachSequence.organization_id == principal.organization.id)
        .order_by(OutreachSequence.created_at.desc())
    ).all())
    return [_sequence_read(db, row) for row in rows]


@router.post("/sequences", response_model=OutreachSequenceRead, status_code=201)
def create_sequence(payload: OutreachSequenceCreate, principal=Depends(require_session_user), db: Session = Depends(get_db)):
    if normalized_role(principal.role) not in {"manager", "admin", "superuser"}:
        raise HTTPException(status_code=403, detail="Manager or admin access required")
    if payload.mode == "approval" and not _paid(principal.organization):
        raise HTTPException(status_code=402, detail="Approval-required outreach is available on paid accounts")
    if not payload.steps:
        raise HTTPException(status_code=422, detail="Sequence requires at least one step")
    seq = OutreachSequence(
        organization_id=principal.organization.id,
        name=payload.name,
        mode=payload.mode,
        stop_on_reply=payload.stop_on_reply,
        active=True,
    )
    db.add(seq)
    db.flush()
    for position, step in enumerate(payload.steps, start=1):
        db.add(OutreachStep(
            sequence_id=seq.id,
            position=position,
            channel=step.channel,
            delay_minutes=step.delay_minutes,
            instructions=step.instructions,
            active=True,
        ))
    db.commit()
    db.refresh(seq)
    return _sequence_read(db, seq)


@router.post("/enroll", status_code=202)
def enroll(payload: EnrollRequest, principal=Depends(require_session_user), db: Session = Depends(get_db)):
    seq = db.scalar(select(OutreachSequence).where(
        OutreachSequence.id == payload.sequence_id,
        OutreachSequence.organization_id == principal.organization.id,
        OutreachSequence.active.is_(True),
    ))
    if not seq:
        raise HTTPException(status_code=404, detail="Sequence not found")
    if seq.mode == "approval" and not _paid(principal.organization):
        raise HTTPException(status_code=402, detail="Approval-required outreach is available on paid accounts")

    enrolled = []
    skipped = []
    for lead_id in payload.lead_ids:
        lead = db.scalar(select(Lead).where(
            Lead.id == lead_id,
            Lead.organization_id == principal.organization.id,
        ))
        if not lead or not lead_is_visible(db, principal, lead):
            skipped.append(lead_id)
            continue
        row = enroll_lead(db, seq, lead, approval_required=seq.mode == "approval")
        enrolled.append(row.id)
    return {"enrolled": enrolled, "skipped": skipped}


@router.get("/tasks", response_model=list[OutreachTaskRead])
def list_tasks(
    status: str | None = Query(default=None, max_length=30),
    limit: int = Query(default=100, ge=1, le=500),
    principal=Depends(require_session_user),
    db: Session = Depends(get_db),
):
    stmt = select(OutreachTask, Lead).join(Lead, Lead.id == OutreachTask.lead_id).where(
        OutreachTask.organization_id == principal.organization.id
    )
    if status:
        stmt = stmt.where(OutreachTask.status == status)
    rows = db.execute(stmt.order_by(OutreachTask.due_at.asc()).limit(limit)).all()
    result = []
    for task, lead in rows:
        if not lead_is_visible(db, principal, lead):
            continue
        try:
            prompt = json.loads(task.prompt_json or "{}")
        except Exception:
            prompt = {}
        result.append(OutreachTaskRead(
            id=task.id,
            lead_id=lead.id,
            lead_name=lead.name or lead.company or lead.email or lead.phone or "Unnamed lead",
            channel=task.channel,
            status=task.status,
            approval_required=task.approval_required,
            due_at=task.due_at,
            prompt=prompt if isinstance(prompt, dict) else {},
            created_at=task.created_at,
        ))
    return result


@router.post("/tasks/{task_id}/approve")
def approve_task(task_id: str, principal=Depends(require_session_user), db: Session = Depends(get_db)):
    if normalized_role(principal.role) not in {"manager", "admin", "superuser"}:
        raise HTTPException(status_code=403, detail="Manager or admin approval required")
    if not _paid(principal.organization):
        raise HTTPException(status_code=402, detail="Approvals are available on paid accounts")
    task = db.scalar(select(OutreachTask).where(
        OutreachTask.id == task_id,
        OutreachTask.organization_id == principal.organization.id,
    ))
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status not in {"queued", "paused"}:
        raise HTTPException(status_code=409, detail="Task is not awaiting approval")
    task.approval_required = False
    task.status = "queued"
    db.commit()
    return {"ok": True, "task_id": task.id}


@router.get("/leads/{lead_id}/ops", response_model=LeadOpsRead)
def lead_ops(lead_id: str, principal=Depends(require_session_user), db: Session = Depends(get_db)):
    lead = db.scalar(select(Lead).where(
        Lead.id == lead_id,
        Lead.organization_id == principal.organization.id,
    ))
    if not lead or not lead_is_visible(db, principal, lead):
        raise HTTPException(status_code=404, detail="Lead not found")
    assignment, lifecycle = ensure_lead_state(db, lead)
    db.commit()
    return LeadOpsRead(
        lead_id=lead.id,
        owner_user_id=assignment.owner_user_id,
        stage=lifecycle.stage,
        automation_state=lifecycle.automation_state,
        handoff_reason=lifecycle.handoff_reason,
        last_contact_at=lifecycle.last_contact_at,
        next_followup_at=lifecycle.next_followup_at,
    )


@router.get("/leads/{lead_id}/activities")
def lead_activities(lead_id: str, principal=Depends(require_session_user), db: Session = Depends(get_db)):
    lead = db.scalar(select(Lead).where(
        Lead.id == lead_id,
        Lead.organization_id == principal.organization.id,
    ))
    if not lead or not lead_is_visible(db, principal, lead):
        raise HTTPException(status_code=404, detail="Lead not found")
    rows = list(db.scalars(
        select(LeadActivity).where(
            LeadActivity.organization_id == principal.organization.id,
            LeadActivity.lead_id == lead.id,
        ).order_by(LeadActivity.created_at.desc()).limit(200)
    ).all())
    return [
        {
            "id": row.id,
            "kind": row.kind,
            "channel": row.channel,
            "summary": row.summary,
            "created_at": row.created_at,
        }
        for row in rows
    ]




@router.get("/handoffs")
def list_handoffs(principal=Depends(require_session_user), db: Session = Depends(get_db)):
    rows = db.execute(
        select(LeadLifecycle, Lead, LeadAssignment)
        .join(Lead, Lead.id == LeadLifecycle.lead_id)
        .outerjoin(LeadAssignment, LeadAssignment.lead_id == Lead.id)
        .where(
            LeadLifecycle.organization_id == principal.organization.id,
            LeadLifecycle.automation_state == "paused",
            LeadLifecycle.handoff_reason.is_not(None),
        )
        .order_by(LeadLifecycle.updated_at.desc())
        .limit(200)
    ).all()
    result = []
    for lifecycle, lead, assignment in rows:
        if not lead_is_visible(db, principal, lead):
            continue
        result.append({
            "lead_id": lead.id,
            "lead_name": lead.name or lead.company or lead.email or lead.phone or "Unnamed lead",
            "status": lead.status,
            "score": lead.score,
            "owner_user_id": assignment.owner_user_id if assignment else None,
            "reason": lifecycle.handoff_reason,
            "updated_at": lifecycle.updated_at,
        })
    return result


@router.post("/agent-access", response_model=AgentAccessCreated, status_code=201)
def new_agent_access(payload: AgentAccessCreate, principal=Depends(require_session_user), db: Session = Depends(get_db)):
    if normalized_role(principal.role) not in {"admin", "superuser"}:
        raise HTTPException(status_code=403, detail="Admin access required")
    row, raw = create_agent_access(db, principal.organization.id, payload.name)
    return AgentAccessCreated(
        id=row.id,
        name=row.name,
        token_prefix=row.token_prefix,
        agent_token=raw,
        claim_url=f"{settings.app_base_url}/api/v1/agent/{raw}/claim",
    )


@router.get("/agent-access")
def list_agent_access(principal=Depends(require_session_user), db: Session = Depends(get_db)):
    if normalized_role(principal.role) not in {"admin", "superuser"}:
        raise HTTPException(status_code=403, detail="Admin access required")
    rows = list(db.scalars(select(AgentAccessToken).where(
        AgentAccessToken.organization_id == principal.organization.id
    ).order_by(AgentAccessToken.created_at.desc())).all())
    return [
        {
            "id": r.id,
            "name": r.name,
            "token_prefix": r.token_prefix,
            "active": r.active,
            "created_at": r.created_at,
        }
        for r in rows
    ]


@router.delete("/agent-access/{access_id}", status_code=204)
def revoke_agent_access(access_id: str, principal=Depends(require_session_user), db: Session = Depends(get_db)):
    if normalized_role(principal.role) not in {"admin", "superuser"}:
        raise HTTPException(status_code=403, detail="Admin access required")
    row = db.scalar(select(AgentAccessToken).where(
        AgentAccessToken.id == access_id,
        AgentAccessToken.organization_id == principal.organization.id,
    ))
    if not row:
        raise HTTPException(status_code=404, detail="Agent access not found")
    row.active = False
    db.commit()


@agent_router.post("/{token}/claim")
def agent_claim(token: str, channel: str | None = Query(default=None, pattern="^(email|sms|call|task)$"), db: Session = Depends(get_db)):
    access = get_agent_access(db, token)
    if not access:
        raise HTTPException(status_code=401, detail="Invalid agent token")
    task = claim_due_task(db, access, channel)
    if not task:
        return {"task": None}
    lead = db.get(Lead, task.lead_id)
    try:
        prompt = json.loads(task.prompt_json or "{}")
    except Exception:
        prompt = {}
    return {
        "task": {
            "id": task.id,
            "channel": task.channel,
            "lead_id": task.lead_id,
            "destination": {
                "email": lead.email if lead else "",
                "phone": lead.phone if lead else "",
            },
            "prompt": prompt,
        }
    }


@agent_router.post("/{token}/tasks/{task_id}/complete")
def agent_complete(token: str, task_id: str, payload: AgentTaskComplete, db: Session = Depends(get_db)):
    access = get_agent_access(db, token)
    if not access:
        raise HTTPException(status_code=401, detail="Invalid agent token")
    task = db.scalar(select(OutreachTask).where(
        OutreachTask.id == task_id,
        OutreachTask.organization_id == access.organization_id,
    ))
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status != "claimed":
        raise HTTPException(status_code=409, detail="Task is not currently claimed")
    complete_task(
        db,
        task,
        status=payload.status,
        message_id=payload.message_id,
        reply_text=payload.reply_text,
        buying_intent=payload.buying_intent,
        unanswered_question=payload.unanswered_question,
        error=payload.error,
    )
    if payload.status == "replied":
        lead = db.get(Lead, task.lead_id)
        org = None
        if lead:
            from app.models import Organization
            org = db.get(Organization, lead.organization_id)
        paid_alerts = bool(org and org.plan in {"starter", "growth"} and org.subscription_status in {"active", "trialing"})
        if paid_alerts and lead:
            reason = "Lead replied with buying intent" if payload.buying_intent else (
                "Lead asked a question the AI agent could not answer" if payload.unanswered_question else "Lead replied"
            )
            send_handoff_notification(db, org, lead, reason)
    return {"ok": True, "task_id": task.id}
