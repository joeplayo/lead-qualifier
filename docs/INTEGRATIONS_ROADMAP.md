# Integrations & SSO roadmap

This document captures the next integration layer without coupling the core qualifier to any one CRM.

## Design principle

All external systems should connect through adapters behind stable internal interfaces:

- **LeadSourceAdapter**: imports/pushes leads into the normalized lead schema.
- **CRMAdapter**: reads/writes contacts, leads, deals/opportunities, owners, notes, and qualification results.
- **ActionAdapter**: sends downstream actions such as task creation, notifications, email, or SMS.
- **IdentityProviderAdapter**: handles OAuth/OIDC sign-in and maps the external identity to a LeadSignal user + organization membership.

Credentials/tokens should be encrypted at rest and isolated per organization. OAuth refresh should happen server-side, and connector jobs should be idempotent with retry/backoff.

## CRM / work-management connectors

### HubSpot
Planned scope:
- OAuth app connection per customer.
- Contact/lead import and webhook ingestion.
- Write score, status, reason, and next action into mapped CRM properties.
- Optionally create/update deals, tasks, notes, and owner assignments.
- Bi-directional sync with external-object IDs + idempotency keys.

Before implementation, verify HubSpot's current OAuth, CRM Objects, Webhooks, rate-limit, and official SDK guidance in the current developer documentation.

### Salesforce
Planned scope:
- OAuth/OIDC connection.
- Lead, Contact, Account, Opportunity, Task, and custom-field mappings.
- Platform Events / Change Data Capture or webhook-equivalent eventing where appropriate.
- Upsert using Salesforce IDs/external IDs to avoid duplicates.
- Optional package/custom metadata for easier enterprise setup.

Before implementation, verify current Salesforce REST/Composite/Bulk API versions, Connected App / External Client App guidance, event APIs, limits, and the supported Python SDK approach.

### monday.com
Planned scope:
- OAuth connection.
- Workspace/board selection and column mapping.
- Import board items as leads and write qualification results back into mapped columns.
- Webhooks for board/item changes.
- Optional creation of updates/tasks for hot leads.

Before implementation, verify monday.com's current GraphQL API, OAuth scopes, webhook behavior, complexity/rate limits, and current SDK recommendations.

## Additional connectors penciled in

- Pipedrive
- Zoho CRM
- Microsoft Dynamics 365
- Google Sheets
- Zapier / Make via generic webhook + API
- Meta/Facebook Lead Ads
- Website forms / embeddable form endpoint
- Slack / Microsoft Teams notifications
- Twilio or comparable SMS provider
- Gmail / Microsoft 365 email actions

## SSO / identity roadmap

### Google
Use standards-based OAuth 2.0 / OpenID Connect for sign-in. Link identity using verified subject + issuer, not email alone.

### Microsoft
Use Microsoft identity platform / OpenID Connect for work/school and, if desired, personal Microsoft accounts. Keep identity separate from Microsoft 365 mail/calendar permissions so customers can grant only what they need.

### CRM-linked sign-in
Where a CRM supports standards-based identity flows suitable for end-user sign-in, allow a customer to connect/sign in using that provider. Treat CRM authorization and application identity as separate consent grants when feasible.

### Enterprise SSO
Later enterprise tier:
- OIDC
- SAML 2.0
- Domain verification
- Just-in-time user provisioning
- SCIM provisioning/deprovisioning
- Role/group mapping
- Enforced SSO per organization

## Data model additions planned

- `oauth_connections`: org, provider, encrypted access/refresh token, scopes, expiry, external tenant/account ID.
- `external_identities`: user, issuer/provider, subject, profile metadata.
- `connector_configs`: org, connector type, mappings, sync direction, enabled flags.
- `external_records`: org, connector, local record type/id, external object type/id, sync cursor/hash.
- `webhook_deliveries`: provider event ID, idempotency state, attempts, last error.
- `sync_jobs`: cursor, status, timing, retry data.

## Security requirements before shipping connectors

- Encrypt refresh/access tokens with a managed KMS/secret service.
- Never expose provider secrets to the browser.
- Verify webhook signatures where supported.
- Use least-privilege scopes.
- Store provider tenant/account identifiers.
- Rotate revoked/expired tokens safely.
- Add audit logs for connection, sync, and write-back actions.
- Support disconnect + token revocation.
- Add per-connector rate limiting, retries, and dead-letter handling.
- Add data retention/deletion workflows.

## Documentation note

Live web access was unavailable when this roadmap was authored, so it intentionally does **not** pin API versions, SDK versions, scopes, endpoint paths, or provider-specific implementation details. Those must be checked against each provider's current official developer documentation immediately before implementation.
