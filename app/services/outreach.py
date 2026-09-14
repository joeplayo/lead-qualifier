
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    AgentAccessToken,
    Lead,
    LeadActivity,
    LeadLifecycle,
    OutreachEnrollment,
    OutreachSequence,
    OutreachStep,
    OutreachTask,
)
from app.services.leadops import ensure_lead_state, record_activity


def utcnow():
    return datetime.now(timezone.utc)


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def create_agent_access(db: Session, organization_id: str, name: str) -> tuple[AgentAccessToken, str]:
    raw = "lsa_" + secrets.token_urlsafe(30)
    row = AgentAccessToken(
        organization_id=organization_id,
        name=name,
        token_hash=token_hash(raw),
        token_prefix=raw[:12],
        active=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row, raw


def get_agent_access(db: Session, raw_token: str) -> AgentAccessToken | None:
    return db.scalar(
        select(AgentAccessToken).where(
            AgentAccessToken.token_hash == token_hash(raw_token),
            AgentAccessToken.active.is_(True),
        )
    )


def _lead_prompt(lead: Lead, step: OutreachStep) -> dict:
    try:
        attrs = json.loads(lead.payload_json or "{}")
    except Exception:
        attrs = {}
    return {
        "lead": {
            "id": lead.id,
            "name": lead.name,
            "company": lead.company,
            "email": lead.email,
            "phone": lead.phone,
            "source": lead.source,
            "notes": lead.notes,
            "qualification_status": lead.status,
            "qualification_score": lead.score,
            "qualification_reason": lead.reason,
            "attributes": attrs if isinstance(attrs, dict) else {},
        },
        "channel": step.channel,
        "instructions": step.instructions,
        "policy": {
            "goal": "Cultivate the lead with concise, relevant follow-up. Do not fabricate business facts, pricing, availability, guarantees, or commitments.",
            "handoff_when": [
                "The lead shows clear buying intent",
                "The lead asks a question that cannot be answered from known business context",
                "The lead requests a human",
                "The lead opts out or asks not to be contacted",
            ],
        },
    }


def create_default_sequence(db: Session, organization_id: str) -> OutreachSequence:
    seq = db.scalar(
        select(OutreachSequence).where(
            OutreachSequence.organization_id == organization_id,
            OutreachSequence.name == "Default AI nurture",
        )
    )
    if seq:
        return seq

    seq = OutreachSequence(
        organization_id=organization_id,
        name="Default AI nurture",
        active=True,
        mode="autopilot",
        stop_on_reply=True,
    )
    db.add(seq)
    db.flush()
    defaults = [
        ("email", 0, "Send a short personalized introduction/follow-up based only on the lead record and qualification context."),
        ("sms", 1440, "If a mobile number is available, send a brief conversational follow-up. Keep it appropriate for SMS."),
        ("email", 2880, "Send a useful second follow-up that references the prior outreach without pretending the lead engaged."),
        ("call", 4320, "If a callable number and permission are available, place or queue an AI-assisted call. Otherwise skip."),
        ("email", 10080, "Send a final polite follow-up and make it easy for the lead to opt out."),
    ]
    for pos, (channel, delay, instructions) in enumerate(defaults, start=1):
        db.add(OutreachStep(
            sequence_id=seq.id,
            position=pos,
            channel=channel,
            delay_minutes=delay,
            instructions=instructions,
            active=True,
        ))
    db.commit()
    db.refresh(seq)
    return seq


def enroll_lead(db: Session, sequence: OutreachSequence, lead: Lead, *, approval_required: bool = False) -> OutreachEnrollment:
    existing = db.scalar(
        select(OutreachEnrollment).where(
            OutreachEnrollment.sequence_id == sequence.id,
            OutreachEnrollment.lead_id == lead.id,
        )
    )
    if existing:
        return existing

    _, lifecycle = ensure_lead_state(db, lead)
    enrollment = OutreachEnrollment(
        organization_id=lead.organization_id,
        sequence_id=sequence.id,
        lead_id=lead.id,
        status="active",
        current_position=0,
    )
    db.add(enrollment)
    db.flush()
    lifecycle.stage = "nurturing"
    lifecycle.automation_state = "active"

    first_step = db.scalar(
        select(OutreachStep).where(
            OutreachStep.sequence_id == sequence.id,
            OutreachStep.active.is_(True),
        ).order_by(OutreachStep.position.asc())
    )
    if first_step:
        due_at = utcnow() + timedelta(minutes=first_step.delay_minutes)
        task = OutreachTask(
            organization_id=lead.organization_id,
            enrollment_id=enrollment.id,
            lead_id=lead.id,
            step_id=first_step.id,
            channel=first_step.channel,
            status="queued",
            approval_required=approval_required or sequence.mode == "approval",
            due_at=due_at,
            prompt_json=json.dumps(_lead_prompt(lead, first_step)),
        )
        db.add(task)
        lifecycle.next_followup_at = due_at
    record_activity(db, lead, "outreach.enrolled", f"Enrolled in {sequence.name}")
    db.commit()
    db.refresh(enrollment)
    return enrollment


def pause_for_handoff(db: Session, lead: Lead, reason: str, *, channel: str | None = None, reply_text: str | None = None) -> None:
    _, lifecycle = ensure_lead_state(db, lead)
    lifecycle.stage = "handoff"
    lifecycle.automation_state = "paused"
    lifecycle.handoff_reason = reason
    lifecycle.next_followup_at = None

    enrollments = list(db.scalars(
        select(OutreachEnrollment).where(
            OutreachEnrollment.lead_id == lead.id,
            OutreachEnrollment.status == "active",
        )
    ).all())
    for enrollment in enrollments:
        enrollment.status = "paused"

    tasks = list(db.scalars(
        select(OutreachTask).where(
            OutreachTask.lead_id == lead.id,
            OutreachTask.status.in_(("queued", "approved")),
        )
    ).all())
    for task in tasks:
        task.status = "paused"

    record_activity(
        db,
        lead,
        "handoff.required",
        reason,
        channel=channel,
        payload={"reply_text": reply_text or ""},
    )
    db.commit()


def maybe_autopilot_after_qualification(db: Session, lead: Lead) -> None:
    _, lifecycle = ensure_lead_state(db, lead)
    if lead.status == "Hot":
        pause_for_handoff(db, lead, "Lead qualified as Hot")
        lifecycle = db.scalar(select(LeadLifecycle).where(LeadLifecycle.lead_id == lead.id))
        if lifecycle:
            lifecycle.stage = "hot"
            db.commit()
        return

    seq = create_default_sequence(db, lead.organization_id)
    enroll_lead(db, seq, lead)


def claim_due_task(db: Session, access: AgentAccessToken, channel: str | None = None) -> OutreachTask | None:
    now = utcnow()
    stmt = select(OutreachTask).where(
        OutreachTask.organization_id == access.organization_id,
        OutreachTask.status == "queued",
        OutreachTask.approval_required.is_(False),
        OutreachTask.due_at <= now,
    )
    if channel:
        stmt = stmt.where(OutreachTask.channel == channel)
    stmt = stmt.order_by(OutreachTask.due_at.asc(), OutreachTask.created_at.asc()).limit(1)
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)
    task = db.scalar(stmt)
    if not task:
        return None
    task.status = "claimed"
    task.claimed_at = now
    task.attempt_count += 1
    db.commit()
    db.refresh(task)

    lead = db.get(Lead, task.lead_id)
    missing_destination = (
        not lead
        or (task.channel == "email" and not (lead.email or "").strip())
        or (task.channel in {"sms", "call"} and not (lead.phone or "").strip())
    )
    if missing_destination:
        complete_task(
            db,
            task,
            status="skipped",
            error=f"Skipped {task.channel}: required contact information is missing.",
        )
        return claim_due_task(db, access, channel)
    return task


def complete_task(
    db: Session,
    task: OutreachTask,
    *,
    status: str,
    message_id: str | None = None,
    reply_text: str | None = None,
    buying_intent: bool = False,
    unanswered_question: bool = False,
    error: str | None = None,
) -> None:
    lead = db.get(Lead, task.lead_id)
    now = utcnow()
    task.completed_at = now
    task.result_json = json.dumps({
        "message_id": message_id,
        "reply_text": reply_text,
        "buying_intent": buying_intent,
        "unanswered_question": unanswered_question,
    })
    task.last_error = error

    if status == "failed":
        task.status = "failed"
        if lead:
            record_activity(db, lead, "outreach.failed", error or "Outreach task failed", channel=task.channel)
        db.commit()
        return

    task.status = "completed" if status in ("sent", "replied") else "skipped"
    if not lead:
        db.commit()
        return

    _, lifecycle = ensure_lead_state(db, lead)
    if status == "skipped":
        record_activity(
            db,
            lead,
            "outreach.skipped",
            error or f"{task.channel.upper()} outreach skipped",
            channel=task.channel,
        )
    else:
        lifecycle.last_contact_at = now
        record_activity(
            db,
            lead,
            "outreach.replied" if status == "replied" else "outreach.sent",
            "Lead replied" if status == "replied" else f"{task.channel.upper()} outreach sent",
            channel=task.channel,
            payload={"message_id": message_id, "reply_text": reply_text or ""},
        )

    if status == "replied":
        reason = "Lead replied"
        if buying_intent:
            reason = "Lead replied with buying intent"
            lead.status = "Hot"
        elif unanswered_question:
            reason = "Lead asked a question the AI agent could not answer"
        pause_for_handoff(db, lead, reason, channel=task.channel, reply_text=reply_text)
        return

    enrollment = db.get(OutreachEnrollment, task.enrollment_id) if task.enrollment_id else None
    if not enrollment or enrollment.status != "active":
        lifecycle.next_followup_at = None
        db.commit()
        return

    current_step = db.get(OutreachStep, task.step_id) if task.step_id else None
    next_step = None
    if current_step:
        next_step = db.scalar(
            select(OutreachStep).where(
                OutreachStep.sequence_id == current_step.sequence_id,
                OutreachStep.position > current_step.position,
                OutreachStep.active.is_(True),
            ).order_by(OutreachStep.position.asc())
        )
    if not next_step:
        enrollment.status = "completed"
        enrollment.completed_at = now
        lifecycle.automation_state = "completed"
        lifecycle.next_followup_at = None
        record_activity(db, lead, "outreach.completed", "Nurture sequence completed")
        db.commit()
        return

    enrollment.current_position = next_step.position
    due_at = now + timedelta(minutes=next_step.delay_minutes)
    next_task = OutreachTask(
        organization_id=lead.organization_id,
        enrollment_id=enrollment.id,
        lead_id=lead.id,
        step_id=next_step.id,
        channel=next_step.channel,
        status="queued",
        approval_required=False,
        due_at=due_at,
        prompt_json=json.dumps(_lead_prompt(lead, next_step)),
    )
    db.add(next_task)
    lifecycle.next_followup_at = due_at
    db.commit()
