from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

def utcnow():
    return datetime.now(timezone.utc)

def uuid_str():
    return str(uuid4())

class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    industry: Mapped[str] = mapped_column(String(100), default="custom")
    api_key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    plan: Mapped[str] = mapped_column(String(30), default="free", index=True)
    subscription_status: Mapped[str] = mapped_column(String(40), default="inactive", index=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True, index=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    profiles = relationship("QualificationProfile", back_populates="organization", cascade="all, delete-orphan")
    leads = relationship("Lead", back_populates="organization", cascade="all, delete-orphan")
    memberships = relationship("Membership", back_populates="organization", cascade="all, delete-orphan")
    usage_counters = relationship("UsageCounter", back_populates="organization", cascade="all, delete-orphan")
    inbound_endpoints = relationship("InboundEndpoint", back_populates="organization", cascade="all, delete-orphan")
    qualification_jobs = relationship("QualificationJob", back_populates="organization", cascade="all, delete-orphan")
    notification_endpoints = relationship("NotificationEndpoint", back_populates="organization", cascade="all, delete-orphan")

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    memberships = relationship("Membership", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("AuthSession", back_populates="user", cascade="all, delete-orphan")

class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "organization_id", name="uq_membership_user_org"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(30), default="owner")

    user = relationship("User", back_populates="memberships")
    organization = relationship("Organization", back_populates="memberships")

class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user = relationship("User", back_populates="sessions")

class QualificationProfile(Base):
    __tablename__ = "qualification_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    rules_json: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    organization = relationship("Organization", back_populates="profiles")

class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)

    name: Mapped[str] = mapped_column(String(200), default="")
    company: Mapped[str] = mapped_column(String(200), default="")
    email: Mapped[str] = mapped_column(String(320), default="")
    phone: Mapped[str] = mapped_column(String(80), default="")
    source: Mapped[str] = mapped_column(String(120), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")

    score: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    status: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    next_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    qualified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    organization = relationship("Organization", back_populates="leads")
    qualification_jobs = relationship("QualificationJob", back_populates="lead", cascade="all, delete-orphan")

class UsageCounter(Base):
    __tablename__ = "usage_counters"
    __table_args__ = (UniqueConstraint("organization_id", "period_key", name="uq_usage_org_period"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    period_key: Mapped[str] = mapped_column(String(7), index=True)  # YYYY-MM
    qualification_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    organization = relationship("Organization", back_populates="usage_counters")

class InboundEndpoint(Base):
    __tablename__ = "inbound_endpoints"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120), default="Website")
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    token_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    organization = relationship("Organization", back_populates="inbound_endpoints")
    jobs = relationship("QualificationJob", back_populates="inbound_endpoint")


class QualificationJob(Base):
    __tablename__ = "qualification_jobs"
    __table_args__ = (
        UniqueConstraint("inbound_endpoint_id", "idempotency_key", name="uq_job_endpoint_idempotency"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    inbound_endpoint_id: Mapped[str | None] = mapped_column(ForeignKey("inbound_endpoints.id", ondelete="SET NULL"), nullable=True, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    organization = relationship("Organization", back_populates="qualification_jobs")
    lead = relationship("Lead", back_populates="qualification_jobs")
    inbound_endpoint = relationship("InboundEndpoint", back_populates="jobs")


class NotificationEndpoint(Base):
    __tablename__ = "notification_endpoints"
    __table_args__ = (UniqueConstraint("organization_id", name="uq_notification_org"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    signing_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    organization = relationship("Organization", back_populates="notification_endpoints")

class MembershipHierarchy(Base):
    __tablename__ = "membership_hierarchy"
    __table_args__ = (
        UniqueConstraint("child_membership_id", name="uq_hierarchy_child"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    parent_membership_id: Mapped[str | None] = mapped_column(ForeignKey("memberships.id", ondelete="SET NULL"), nullable=True, index=True)
    child_membership_id: Mapped[str] = mapped_column(ForeignKey("memberships.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LeadAssignment(Base):
    __tablename__ = "lead_assignments"
    __table_args__ = (UniqueConstraint("lead_id", name="uq_lead_assignment"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    owner_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    assigned_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class LeadLifecycle(Base):
    __tablename__ = "lead_lifecycles"
    __table_args__ = (UniqueConstraint("lead_id", name="uq_lead_lifecycle"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    stage: Mapped[str] = mapped_column(String(40), default="new", index=True)
    automation_state: Mapped[str] = mapped_column(String(40), default="eligible", index=True)
    handoff_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_contact_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_followup_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class LeadActivity(Base):
    __tablename__ = "lead_activities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(60), index=True)
    channel: Mapped[str | None] = mapped_column(String(30), nullable=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class CRMConnection(Base):
    __tablename__ = "crm_connections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(30), default="configured", index=True)
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    secret_json: Mapped[str] = mapped_column(Text, default="{}")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExternalContactMap(Base):
    __tablename__ = "external_contact_maps"
    __table_args__ = (
        UniqueConstraint("crm_connection_id", "external_id", name="uq_external_contact"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    crm_connection_id: Mapped[str] = mapped_column(ForeignKey("crm_connections.id", ondelete="CASCADE"), index=True)
    external_id: Mapped[str] = mapped_column(String(200), index=True)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OutreachSequence(Base):
    __tablename__ = "outreach_sequences"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160), default="Default nurture")
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    mode: Mapped[str] = mapped_column(String(30), default="autopilot")
    stop_on_reply: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OutreachStep(Base):
    __tablename__ = "outreach_steps"
    __table_args__ = (
        UniqueConstraint("sequence_id", "position", name="uq_sequence_step_position"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    sequence_id: Mapped[str] = mapped_column(ForeignKey("outreach_sequences.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    channel: Mapped[str] = mapped_column(String(30), default="email")
    delay_minutes: Mapped[int] = mapped_column(Integer, default=0)
    instructions: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class OutreachEnrollment(Base):
    __tablename__ = "outreach_enrollments"
    __table_args__ = (
        UniqueConstraint("sequence_id", "lead_id", name="uq_sequence_lead_enrollment"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    sequence_id: Mapped[str] = mapped_column(ForeignKey("outreach_sequences.id", ondelete="CASCADE"), index=True)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    current_position: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OutreachTask(Base):
    __tablename__ = "outreach_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    enrollment_id: Mapped[str | None] = mapped_column(ForeignKey("outreach_enrollments.id", ondelete="SET NULL"), nullable=True, index=True)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    step_id: Mapped[str | None] = mapped_column(ForeignKey("outreach_steps.id", ondelete="SET NULL"), nullable=True)
    channel: Mapped[str] = mapped_column(String(30), index=True)
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    approval_required: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    prompt_json: Mapped[str] = mapped_column(Text, default="{}")
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class AgentAccessToken(Base):
    __tablename__ = "agent_access_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120), default="OpenClaw")
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    token_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    source_type: Mapped[str] = mapped_column(String(40), default="csv")
    source_name: Mapped[str] = mapped_column(String(160), default="")
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    imported_rows: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_rows: Mapped[int] = mapped_column(Integer, default=0)
    rejected_rows: Mapped[int] = mapped_column(Integer, default=0)
    created_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

