# LeadLift v0.6.4 — AI lead qualification, nurture, and revenue automation SaaS

LeadLift is a vertical-agnostic lead qualification platform. Roofing can be the first go-to-market preset, but qualification logic is tenant configuration rather than hard-coded industry behavior.


## v0.6.4 dashboard experience refresh

- Dashboard-first sales workspace with pipeline KPIs and a priority work queue.
- Simplified navigation: Dashboard, Leads, AI Rep, Activity, Imports & CRM, Team, and Settings.
- Cleaner enterprise SaaS visual system with a dark navigation rail and bright working canvas.
- Dashboard surfaces current hot leads, recommended next actions, and leads needing review.
- Preserves the v0.6.3 lead-management permissions, editable lead drawer, duplicate cleanup, and backend behavior.

## v0.6.3 lead-management hotfix

- Entire inbox rows are clickable and keyboard-accessible.
- Lead detail opens in the management drawer from anywhere on the row.
- Managers/Admins can edit contact fields, custom attributes, manual score/status, next action/reason, ownership, lifecycle, automation state, handoff reason, and next follow-up.
- Regular users remain read-only for manual overrides.
- Delete and duplicate cleanup are limited to Manager/Admin roles.


## What v0.2 adds

- Email/password customer accounts.
- HttpOnly session cookies for the browser dashboard.
- Organization memberships and role field.
- API-key authentication preserved for server-to-server integrations.
- Monthly qualification metering enforced before LLM calls.
- Free / Starter / Growth plan limits.
- Stripe Checkout for subscriptions.
- Stripe Billing Portal for self-service billing.
- Stripe webhook signature verification and subscription-state sync.
- A dashboard that supports register/login, usage visibility, lead scoring, upgrade, billing, and logout.
- Connector interfaces plus a documented roadmap for HubSpot, Salesforce, monday.com, Google/Microsoft SSO, and additional systems.

## Architecture

```text
Human user -> session auth -----------\
                                       -> tenant -> qualification profile -> usage gate -> qualifier -> Groq
Website / CRM / automation -> API key -/                                             |
                                                                                      -> Lead + result
Stripe -> signed webhook -> organization plan/subscription state
```

The core qualifier is still independent of the industry preset and LLM provider.

## Plans in this starter

The code ships with example monthly qualification allowances:

- Free: 25
- Starter: 500
- Growth: 2,500

These are product defaults, not pricing recommendations. Change `PLAN_LIMITS` in `app/config.py` after measuring actual AI cost and customer usage.

## Local start

Python 3.11+:

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Add your key to `.env`:

```env
GROQ_API_KEY=your_key
```

Both the API and worker load `.env` automatically. Then run:

```bash
uvicorn app.main:app --reload
```

Open:

- Dashboard: `http://localhost:8000/dashboard/`
- API docs: `http://localhost:8000/docs`
- Health: `http://localhost:8000/health`

The dashboard can create the first customer account directly. Registration returns the organization's integration API key once; store it securely.

## Authentication model

### Browser users

`POST /api/v1/auth/register`
- Creates a user.
- Creates an organization.
- Creates an owner membership.
- Applies the selected qualification preset.
- Creates a signed-in server-side session represented by an HttpOnly cookie.
- Returns the organization's API key once.

`POST /api/v1/auth/login` creates a new session.

`GET /api/v1/auth/me` returns the signed-in user's current organization context.

`POST /api/v1/auth/logout` deletes the server-side session and clears the cookie.

Passwords are stored using PBKDF2-HMAC-SHA256 with a random salt. For a larger production deployment, consider a dedicated auth platform or Argon2id plus email verification, password-reset flows, MFA, CSRF protection, login throttling, breached-password checks, and security notifications.

### Integrations

Server-to-server clients continue to send:

```http
X-Org-Key: ls_...
```

This is intentional: integrations should not depend on an employee's browser session.

A session user can optionally select an organization with `X-Organization-Id` once multi-organization UI is added.

## Usage enforcement

Every qualification call reserves one unit before invoking the model. If the model provider fails, the reservation is released.

`GET /api/v1/billing/summary` returns:

```json
{
  "plan": "free",
  "subscription_status": "inactive",
  "used": 3,
  "limit": 25,
  "remaining": 22
}
```

When the monthly allowance is exhausted, qualification endpoints return HTTP `402`.

PostgreSQL is the intended production database because row locking is used on usage counters. SQLite remains convenient for local development.

## Stripe setup

Configure:

```bash
APP_BASE_URL=https://your-app.example
STRIPE_SECRET_KEY=...
STRIPE_WEBHOOK_SECRET=...
STRIPE_PRICE_STARTER=price_...
STRIPE_PRICE_GROWTH=price_...
SESSION_COOKIE_SECURE=true
```

The app uses Stripe's hosted Checkout and Billing Portal; it does not store card data.

Browser session endpoints:

```http
POST /api/v1/billing/checkout
{"plan":"starter"}
```

```http
POST /api/v1/billing/portal
```

Configure Stripe to send subscription/Checkout events to:

```text
POST /api/v1/billing/stripe/webhook
```

The handler verifies the `Stripe-Signature` header and updates the organization customer ID, subscription ID, plan, and subscription status.

### Important Stripe implementation note

Live web access was unavailable while this version was assembled. The flow intentionally avoids pinning a Stripe SDK version and uses Stripe's HTTP API through `httpx`. Before production deployment, verify current Checkout parameters, Billing Portal requirements, webhook event shapes, signature requirements, subscription-status semantics, and API-version behavior against Stripe's current official docs.

## Lead API

Create and qualify a lead with either a signed-in browser session or organization API key:

```bash
curl -X POST http://localhost:8000/api/v1/leads \
  -H "Content-Type: application/json" \
  -H "X-Org-Key: ls_your_key" \
  -d '{
    "name": "Alex",
    "source": "Website",
    "notes": "Roof started leaking after yesterday storm and I want an inspection this week.",
    "attributes": {"zip": "07001"}
  }'
```

The same engine can instead be configured for agencies, solar, or a custom industry through the qualification profile APIs.

## CRM, work-management, and SSO roadmap

The connector layer is intentionally provider-neutral. See:

[`docs/INTEGRATIONS_ROADMAP.md`](docs/INTEGRATIONS_ROADMAP.md)

Penciled-in priorities include:

- HubSpot CRM.
- Salesforce.
- monday.com.
- Google Sign-In / OpenID Connect.
- Microsoft identity / Outlook ecosystem sign-in.
- CRM-linked sign-in where a provider offers an appropriate standards-based identity flow.
- Later enterprise OIDC/SAML/SCIM.
- Pipedrive, Zoho CRM, Dynamics 365, Google Sheets, Meta Lead Ads, Zapier/Make, Slack/Teams, SMS, and email actions.

The roadmap also defines planned `oauth_connections`, `external_identities`, connector configuration, external-record mapping, webhook-delivery, and sync-job data models.

Because live web access was unavailable, no current provider API versions, SDK versions, scopes, or endpoint paths are asserted in this repo. Those should be verified against each provider's official current developer documentation immediately before implementing the connector.

## Database upgrade note

v0.2 adds columns to `organizations` and introduces users, memberships, sessions, and usage tables. SQLAlchemy `create_all()` creates missing tables for a new database but does **not** migrate an existing v0.1 database.

For local evaluation, start with a fresh SQLite database. Before upgrading a deployed customer database, add Alembic migrations and test the migration on a backup. This should happen before production launch.

## Production hardening checklist

Before taking real customer payments:

1. Add Alembic migrations and automated migration tests.
2. Add email verification, password reset, MFA option, CSRF protection, login throttling, and stronger account-recovery flows.
3. Move secrets and future OAuth refresh tokens into encrypted storage backed by a managed KMS/secret service.
4. Move LLM calls to a durable worker queue with idempotency, retries, and rate limiting.
5. Verify Stripe integration against current official docs and add webhook-event idempotency storage.
6. Add observability, audit logs, backups, data-retention controls, and privacy/deletion workflows.
7. Add entitlement tests so canceled/downgraded subscriptions cannot exceed intended limits.
8. Add integration/webhook rate limits and abuse controls.
9. Build evaluation datasets tied to actual conversion outcomes before changing prompts/models.
10. Complete legal/privacy/security review before onboarding businesses with sensitive customer data.


## v0.3 dashboard milestone

The dashboard now includes a lead-operations inbox with server-side search and filtering, Hot/Warm/Cold KPI counts, lead detail drawers with qualification evidence and custom attributes, one-click requalification, and an editable qualification-rules screen with presets. New API endpoints include `GET /api/v1/leads/stats` and `GET /api/v1/leads/{lead_id}`; `GET /api/v1/leads` also accepts `offset`, `status`, `source`, `q`, `min_score`, and `max_score`.


## v0.4 automation milestone

v0.4 adds a durable ingestion path so leads can arrive and qualify without a person using the dashboard.

### Inbound webhook flow

Create a secret inbound URL from **Dashboard → Automations** or:

```http
POST /api/v1/automations/inbound-endpoints
{"name":"Website"}
```

The returned `webhook_url` is shown only at creation time. Treat it like a password. Post canonical lead JSON to it:

```bash
curl -X POST 'YOUR_WEBHOOK_URL' \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: form-submission-123' \
  -d '{
    "name": "Jordan Lee",
    "email": "jordan@example.com",
    "notes": "Requested a quote this week",
    "attributes": {"zip": "07001"}
  }'
```

The request returns HTTP `202` after persisting the lead and a `qualification_job`. It does not wait for the LLM. `Idempotency-Key` is optional but strongly recommended for retrying form/CRM deliveries without creating duplicate leads.

### Worker

Run the API and worker in separate terminals:

```bash
uvicorn app.main:app --reload
```

```bash
python -m app.worker
```

The worker claims queued jobs, reserves usage, calls the qualifier, and writes the score back to the lead. Provider failures are retried with bounded backoff; stale `processing` jobs are recovered after `WORKER_STALE_SECONDS`. Plan-limit failures are marked failed rather than retried.

Docker Compose now runs `app`, `worker`, and PostgreSQL together:

```bash
docker compose up --build
```

### Hot-lead notification webhook

From **Dashboard → Automations**, configure one outbound destination for the organization. When a queued lead finishes as `Hot`, the worker POSTs a `lead.hot` JSON payload to that URL.

If a signing secret is configured, LeadLift adds:

```http
X-LeadLift-Signature: sha256=<HMAC-SHA256 of the raw request body>
X-LeadLift-Event: lead.hot
```

The outbound delivery uses a small bounded retry loop. A notification failure does not undo a successful qualification.

### New data and endpoints

v0.4 adds `inbound_endpoints`, `qualification_jobs`, and `notification_endpoints`. These are new tables, so `create_all()` can add them to a local v0.3 database. Alembic is still required before production changes.

New routes:

- `GET/POST /api/v1/automations/inbound-endpoints`
- `DELETE /api/v1/automations/inbound-endpoints/{endpoint_id}`
- `GET/PUT /api/v1/automations/notification-endpoint`
- `GET /api/v1/automations/jobs/{job_id}`
- `POST /api/v1/ingest/{secret_token}`

### Security notes

Inbound webhook tokens are stored only as SHA-256 hashes and cannot be recovered from the database. The raw URL is returned once. Outbound signing secrets are currently stored in the application database so the worker can use them; encrypt these with a managed KMS/secret service before production. Also add outbound URL allowlisting/SSRF controls for a public multi-tenant deployment.



## v0.5 superuser admin console

v0.5 adds a browser admin console at:

```text
http://localhost:8000/admin/
```

For local SQLite development, the app bootstraps the requested superuser on startup:

```text
username: admin
password: joeplayo.com
```

This account is created directly by the superuser bootstrap service, so it does not require an email address and does not pass through normal customer-registration validation. Normal customer signup validation is unchanged. Internally, the existing `users.email` column remains the unique login-identifier column for schema compatibility, so the string `admin` is stored there for this special account.

The superuser console provides system-wide KPIs, organization/plan controls, user enable/disable controls, and recent qualification-queue visibility. A superuser can open any customer workspace from the admin console; the browser sends `X-Organization-ID` and the backend permits cross-tenant context only when the authenticated session belongs to a `superuser`.

Automatic bootstrap is restricted to SQLite by `app/services/superuser.py`. Configure these environment variables when needed:

```bash
export BOOTSTRAP_SUPERUSER_ENABLED=true
export BOOTSTRAP_SUPERUSER_USERNAME=admin
export BOOTSTRAP_SUPERUSER_PASSWORD=joeplayo.com
```

For a non-SQLite deployment, provision the account explicitly after setting a strong deployment password:

```bash
python -m scripts.bootstrap_superuser
```

**Before any internet-facing deployment, change the bootstrap password and disable automatic bootstrap after provisioning the account.** Do not ship a public service with the development credential above.


## v0.6 revenue automation milestone

v0.6 expands the product from qualification into lead intake, ownership, lifecycle management, AI nurture orchestration, and human handoff.

### User / Manager / Admin permissions

Customer workspaces use three roles:

- `user`: sees leads assigned to that user.
- `manager`: sees the manager's own leads plus descendants configured under that manager.
- `admin`: sees and configures the full organization.

The existing internal `superuser` remains the platform account for `/admin/`. Existing v0.5 `owner` memberships are normalized to Admin behavior for compatibility.

New organizations register their first customer account as `admin`. Admins can create Users and Managers from **Dashboard → Team**. Hierarchy relationships are stored in a separate table so upgrading a v0.5 SQLite database does not require changing the existing `memberships` table.

### CSV and normalized CRM intake

**Dashboard → Imports & CRM** accepts UTF-8 CSV files up to 10 MB. Common headers such as name, first/last name, company, email, phone, source, and notes are recognized automatically. Extra columns are preserved in lead attributes. The import path deduplicates against existing leads by email/phone and can queue qualification for every accepted record.

CRM connection records support:

- HubSpot
- Salesforce
- monday.com
- Generic CRM/middleware bridges

A connection can receive normalized contacts through:

```http
POST /api/v1/integrations/crm/{connection_id}/import
```

with contacts shaped as:

```json
{
  "contacts": [
    {
      "external_id": "crm-contact-123",
      "name": "Jordan Lee",
      "company": "Example Co",
      "email": "jordan@example.com",
      "phone": "+1 555 555 0100",
      "source": "HubSpot",
      "notes": "Requested information",
      "attributes": {"campaign": "Q3"},
      "owner_user_id": null
    }
  ],
  "auto_qualify": true
}
```

`external_id` is mapped to the resulting Lead so repeated bridge deliveries can be deduplicated.

The provider records and normalized bridge are implemented in this version. Direct provider-specific OAuth, provider API pull sync, and writeback are **not yet claimed as live integrations**. Those endpoint versions, scopes, webhook behavior, and OAuth details must be verified against each provider's current official developer documentation before turning them on. Until then, a CRM automation, middleware service, Zapier/Make flow, or agent can normalize contacts into the endpoint above.

The existing v0.4 secret inbound webhook remains another way for websites, lead-generation agents, or external apps to create leads automatically.

### AI Autopilot nurture

After worker qualification:

```text
Hot  -> pause automation -> human handoff
Warm -> enroll in default AI nurture
Cold -> enroll in default AI nurture
```

The default sequence is:

```text
Email now
-> SMS after 24 hours
-> Email after 48 hours
-> AI-assisted call after 72 hours
-> Final email after 7 days
```

Delays are relative to the prior completed/skipped step and can be customized from **Dashboard → AI outreach** or through the sequence API.

Outreach is data-aware. Email steps are skipped when the lead has no email address; SMS/call steps are skipped when no phone number is available. Skipping a channel advances the sequence without pretending contact occurred.

Any reported lead reply stops the automated sequence. Buying intent marks the lead Hot. An unanswered question, buying intent, or other reply creates an in-app human handoff with a reason and activity trail.

### OpenClaw / external AI agent queue

Admins can generate an agent access token from **Dashboard → AI outreach**. The raw token is shown once and only a SHA-256 hash is stored.

An agent claims one due task at a time:

```http
POST /api/v1/agent/{agent_token}/claim
```

Optional channel filter:

```text
?channel=email
?channel=sms
?channel=call
?channel=task
```

A claim returns the lead destination plus a structured prompt containing known lead details, qualification context, channel instructions, and handoff policy.

The agent reports completion:

```http
POST /api/v1/agent/{agent_token}/tasks/{task_id}/complete
```

Example:

```json
{
  "status": "replied",
  "message_id": "provider-message-id",
  "reply_text": "Can somebody call me this afternoon?",
  "buying_intent": true,
  "unanswered_question": false
}
```

Allowed result states are `sent`, `failed`, `replied`, and `skipped`.

### Paid account controls

AI Autopilot remains the default flow. Approval-required outreach sequences and external Hot/handoff alert webhooks are gated to active/trialing Starter or Growth accounts. Basic accounts still receive in-app human handoffs; paid accounts can additionally route alerts outward and use Manager/Admin approval queues.

### Activity and reporting foundation

v0.6 records lead-import, outreach, skip, reply, completion, and handoff events in `lead_activities`. It also stores assignment and lifecycle state separately from the original Lead table. These event records are the attribution foundation for the next reporting milestone: funnel conversion, response rates, dormant-lead recovery, pipeline/revenue impact, source performance, and AI-assisted conversion attribution.

### Database upgrade note

v0.6 adds new tables rather than altering the existing v0.5 Lead/User/Membership columns. For a local SQLite v0.5 database, `create_all()` can create these missing tables on startup. Production deployments should still use Alembic migrations, backups, and migration tests before rollout.


## Tests

Run:

```bash
pytest -q
```

The included tests cover qualifier behavior, authentication, automation/queue processing, superuser bootstrap, cross-tenant superuser access, and dashboard/admin controls.

## Product strategy

**Build broad, sell narrow.**

The software remains vertical-agnostic. Roofing can be the first landing page, preset, and outbound-sales message; additional verticals should be configuration and onboarding changes rather than code forks.

## Legacy prototype

The original Google-Sheets-first project remains under `legacy/`.
