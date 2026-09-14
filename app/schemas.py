from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field, ConfigDict

class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    industry: str = Field(default="custom", max_length=100)

class OrganizationCreated(BaseModel):
    id: str
    name: str
    industry: str
    api_key: str

class RegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=10, max_length=200)
    organization_name: str = Field(min_length=2, max_length=200)
    industry: str = Field(default="custom", max_length=100)

class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=1, max_length=200)

class AuthUserRead(BaseModel):
    id: str
    email: str
    organization_id: str
    organization_name: str
    role: str
    plan: str
    subscription_status: str

class RegisterResponse(AuthUserRead):
    api_key: str

class LeadCreate(BaseModel):
    name: str = ""
    company: str = ""
    email: str = ""
    phone: str = ""
    source: str = ""
    notes: str = ""
    attributes: dict[str, Any] = Field(default_factory=dict)


class LeadUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    company: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=80)
    source: str | None = Field(default=None, max_length=120)
    notes: str | None = None
    attributes: dict[str, Any] | None = None

    # Elevated users may manually override AI/operational fields when needed.
    score: int | None = Field(default=None, ge=1, le=10)
    status: str | None = Field(default=None, pattern="^(Hot|Warm|Cold)$")
    next_action: str | None = None
    reason: str | None = None

    owner_user_id: str | None = None
    stage: str | None = Field(
        default=None,
        pattern="^(new|nurturing|handoff|hot|won|lost|disqualified)$",
    )
    automation_state: str | None = Field(
        default=None,
        pattern="^(eligible|active|paused|completed|disabled)$",
    )
    handoff_reason: str | None = None
    next_followup_at: datetime | None = None

class LeadDeleteResult(BaseModel):
    deleted: bool = True
    lead_id: str

class LeadDedupeResult(BaseModel):
    kept_lead_id: str
    deleted_count: int

class QualificationResult(BaseModel):
    score: int = Field(ge=1, le=10)
    status: str
    next_action: str
    reason: str

class LeadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    company: str
    email: str
    phone: str
    source: str
    notes: str
    score: int | None
    status: str | None
    next_action: str | None
    reason: str | None
    created_at: datetime
    qualified_at: datetime | None


class LeadDetailRead(LeadRead):
    attributes: dict[str, Any] = Field(default_factory=dict)

class LeadStats(BaseModel):
    total: int
    hot: int
    warm: int
    cold: int
    pending: int
    average_score: float | None

class ProfileUpdate(BaseModel):
    name: str = Field(default="Custom", max_length=120)
    business_context: str = Field(default="", max_length=4000)
    high_intent_signals: list[str] = Field(default_factory=list)
    medium_intent_signals: list[str] = Field(default_factory=list)
    disqualifiers: list[str] = Field(default_factory=list)
    required_questions: list[str] = Field(default_factory=list)
    custom_instructions: str = Field(default="", max_length=4000)

class ProfileRead(ProfileUpdate):
    id: str

class BillingSummary(BaseModel):
    plan: str
    subscription_status: str
    used: int
    limit: int
    remaining: int

class CheckoutRequest(BaseModel):
    plan: str = Field(pattern="^(starter|growth)$")

class CheckoutResponse(BaseModel):
    url: str

class PortalResponse(BaseModel):
    url: str


class InboundEndpointCreate(BaseModel):
    name: str = Field(default="Website", min_length=1, max_length=120)

class InboundEndpointRead(BaseModel):
    id: str
    name: str
    token_prefix: str
    active: bool
    last_used_at: datetime | None
    created_at: datetime

class InboundEndpointCreated(InboundEndpointRead):
    webhook_url: str

class IngestAccepted(BaseModel):
    accepted: bool = True
    lead_id: str
    job_id: str
    status: str

class QualificationJobRead(BaseModel):
    id: str
    lead_id: str
    status: str
    attempts: int
    max_attempts: int
    available_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    last_error: str | None
    created_at: datetime

class NotificationEndpointUpdate(BaseModel):
    url: str = Field(default="", max_length=2000)
    signing_secret: str | None = Field(default=None, max_length=500)
    active: bool = True

class NotificationEndpointRead(BaseModel):
    url: str
    active: bool
    has_signing_secret: bool


class AdminUserUpdate(BaseModel):
    is_active: bool

class AdminOrganizationUpdate(BaseModel):
    plan: str | None = Field(default=None, pattern="^(free|starter|growth)$")
    subscription_status: str | None = Field(default=None, max_length=40)

class TeamUserCreate(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=10, max_length=200)
    role: str = Field(default="user", pattern="^(user|manager)$")
    manager_user_id: str | None = None

class TeamUserRead(BaseModel):
    id: str
    email: str
    role: str
    manager_user_id: str | None
    is_active: bool

class TeamUserUpdate(BaseModel):
    role: str | None = Field(default=None, pattern="^(user|manager)$")
    manager_user_id: str | None = None
    is_active: bool | None = None

class CRMConnectionCreate(BaseModel):
    provider: str = Field(pattern="^(hubspot|salesforce|monday|generic)$")
    name: str = Field(default="", max_length=120)
    config: dict[str, Any] = Field(default_factory=dict)
    secret: dict[str, Any] = Field(default_factory=dict)

class CRMConnectionRead(BaseModel):
    id: str
    provider: str
    name: str
    status: str
    config: dict[str, Any] = Field(default_factory=dict)
    has_secret: bool
    last_synced_at: datetime | None
    created_at: datetime

class NormalizedContact(BaseModel):
    external_id: str | None = Field(default=None, max_length=200)
    name: str = ""
    company: str = ""
    email: str = ""
    phone: str = ""
    source: str = ""
    notes: str = ""
    attributes: dict[str, Any] = Field(default_factory=dict)
    owner_user_id: str | None = None

class CRMImportRequest(BaseModel):
    contacts: list[NormalizedContact]
    auto_qualify: bool = True

class ImportResult(BaseModel):
    batch_id: str
    total: int
    imported: int
    duplicates: int
    rejected: int
    lead_ids: list[str] = Field(default_factory=list)

class OutreachStepInput(BaseModel):
    channel: str = Field(pattern="^(email|sms|call|task)$")
    delay_minutes: int = Field(default=0, ge=0, le=525600)
    instructions: str = Field(default="", max_length=4000)

class OutreachSequenceCreate(BaseModel):
    name: str = Field(default="Default nurture", min_length=1, max_length=160)
    mode: str = Field(default="autopilot", pattern="^(autopilot|approval)$")
    stop_on_reply: bool = True
    steps: list[OutreachStepInput]

class OutreachSequenceRead(BaseModel):
    id: str
    name: str
    active: bool
    mode: str
    stop_on_reply: bool
    steps: list[dict[str, Any]]

class EnrollRequest(BaseModel):
    sequence_id: str
    lead_ids: list[str]

class OutreachTaskRead(BaseModel):
    id: str
    lead_id: str
    lead_name: str
    channel: str
    status: str
    approval_required: bool
    due_at: datetime
    prompt: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

class AgentAccessCreate(BaseModel):
    name: str = Field(default="OpenClaw", min_length=1, max_length=120)

class AgentAccessCreated(BaseModel):
    id: str
    name: str
    token_prefix: str
    agent_token: str
    claim_url: str

class AgentTaskComplete(BaseModel):
    status: str = Field(pattern="^(sent|failed|replied|skipped)$")
    message_id: str | None = None
    reply_text: str | None = None
    buying_intent: bool = False
    unanswered_question: bool = False
    error: str | None = None

class LeadOpsRead(BaseModel):
    lead_id: str
    owner_user_id: str | None
    stage: str
    automation_state: str
    handoff_reason: str | None
    last_contact_at: datetime | None
    next_followup_at: datetime | None

