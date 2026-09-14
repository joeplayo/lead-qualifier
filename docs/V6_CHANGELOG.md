# LeadSignal v0.6 changelog

## Revenue automation

v0.6 adds the first complete nurture orchestration layer on top of the existing lead qualification worker.

### Intake
- CSV upload endpoint with common-header inference, UTF-8 support, extra-column preservation, 10 MB request cap, email/phone dedupe, import batches, ownership, and optional qualification queueing.
- CRM connection records for HubSpot, Salesforce, monday.com, and generic bridges.
- Normalized CRM contact import endpoint with external-contact mapping and idempotent external IDs.
- Existing inbound webhook/API ingestion remains supported.

### Ownership and permissions
- Customer roles standardized to User, Manager, and Admin.
- Existing Owner roles receive Admin behavior for backward compatibility.
- Manager/child hierarchy stored separately from memberships.
- Lead assignment stored separately from the Lead table.
- Browser lead visibility is owner-scoped for Users, descendant-scoped for Managers, and org-wide for Admins.
- Machine API keys remain organization-wide.

### AI outreach
- Outreach sequences, ordered steps, enrollments, tasks, and agent access tokens.
- Default cadence covering email, SMS, email, call, and final email.
- User-configurable delays and Autopilot/Approval sequence mode.
- Data-aware channel skipping when required email/phone data is absent.
- Agent claim/complete protocol suitable for OpenClaw or another execution agent.
- Reply, buying-intent, and unanswered-question handoff handling.
- Human-handoff queue and per-lead activity timeline.

### Plan entitlements
- AI Autopilot is available without approval mode.
- Approval-required sequences are limited to active/trialing Starter/Growth organizations.
- External Hot/handoff webhooks are limited to active/trialing Starter/Growth organizations.
- Basic organizations retain in-app human handoffs.

### Compatibility
- Version is now 0.6.0.
- New V6 persistence is implemented using new tables so a local v0.5 SQLite database can be reused without altering existing table columns.
- Production deployments still need Alembic migrations before rollout.
