# CRM Bridge Contract

LeadSignal v0.6 implements a provider-neutral contact import contract and connection records for HubSpot, Salesforce, monday.com, and generic middleware.

Direct provider OAuth and provider-specific API synchronization are intentionally not represented as complete in v0.6. Current provider endpoint versions, OAuth scopes, pagination, webhook signatures, rate limits, and writeback semantics must be verified against official provider documentation before activation.

## Create a CRM record

```http
POST /api/v1/integrations/crm
Content-Type: application/json

{
  "provider": "hubspot",
  "name": "Sales CRM",
  "config": {},
  "secret": {}
}
```

CRM credential configuration is Admin-only. Secrets are never returned by the read API. The MVP stores `secret_json` in the application database; production should encrypt tokens through a managed KMS/secret service.

## Import normalized contacts

```http
POST /api/v1/integrations/crm/{connection_id}/import
Content-Type: application/json
```

```json
{
  "contacts": [
    {
      "external_id": "123",
      "name": "Jordan Lee",
      "company": "Example Co",
      "email": "jordan@example.com",
      "phone": "+1 555 555 0100",
      "source": "CRM",
      "notes": "",
      "attributes": {
        "pipeline": "New Business"
      },
      "owner_user_id": null
    }
  ],
  "auto_qualify": true
}
```

External IDs are mapped to Lead IDs. Email/phone dedupe also protects against duplicates arriving through another source.

Managers may import records but cannot configure CRM credentials. A Manager-supplied owner outside the Manager's descendant tree is replaced by the importing Manager.

## Bridge architecture

A provider-specific adapter or automation can:

1. Read contacts from the provider.
2. Normalize them to the schema above.
3. POST them to LeadSignal.
4. Let LeadSignal qualify/nurture them.
5. Use future writeback endpoints/events to update the originating provider.

This keeps the LeadSignal data model provider-neutral and lets direct adapters be added without changing qualification or nurture behavior.
