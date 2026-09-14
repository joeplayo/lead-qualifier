# External AI Agent Protocol

This protocol lets OpenClaw or another trusted execution agent consume LeadSignal outreach jobs without receiving the organization's browser session or API key.

## 1. Create a token

An Admin creates an access token from Dashboard → AI outreach or:

```http
POST /api/v1/outreach/agent-access
Content-Type: application/json

{"name":"OpenClaw"}
```

The raw `agent_token` and `claim_url` are returned once. Store the token as a secret. LeadSignal stores only its SHA-256 hash.

## 2. Claim a due task

```http
POST /api/v1/agent/{agent_token}/claim
```

Optionally restrict the worker to one channel:

```http
POST /api/v1/agent/{agent_token}/claim?channel=email
```

A response with no due task is:

```json
{"task": null}
```

A claimed task contains:

```json
{
  "task": {
    "id": "...",
    "channel": "email",
    "lead_id": "...",
    "destination": {
      "email": "lead@example.com",
      "phone": ""
    },
    "prompt": {
      "lead": {},
      "channel": "email",
      "instructions": "...",
      "policy": {}
    }
  }
}
```

The prompt is intentionally factual: the execution agent must not fabricate prices, availability, guarantees, offers, or other business facts absent from the provided context.

## 3. Execute through an approved channel

The external agent decides how to execute the task through the organization's connected email, SMS, phone, or task system. LeadSignal v0.6 does not embed third-party channel credentials into an agent claim.

If the required destination is missing, LeadSignal skips that task before it is claimed and advances the cadence.

## 4. Report the outcome

```http
POST /api/v1/agent/{agent_token}/tasks/{task_id}/complete
Content-Type: application/json
```

Sent:

```json
{
  "status": "sent",
  "message_id": "provider-message-id"
}
```

Reply with buying intent:

```json
{
  "status": "replied",
  "message_id": "provider-message-id",
  "reply_text": "Can somebody call me?",
  "buying_intent": true,
  "unanswered_question": false
}
```

AI could not safely answer:

```json
{
  "status": "replied",
  "reply_text": "What guarantee do you offer?",
  "buying_intent": false,
  "unanswered_question": true
}
```

Failure:

```json
{
  "status": "failed",
  "error": "Provider rejected the send"
}
```

Allowed statuses are `sent`, `failed`, `replied`, and `skipped`.

## 5. Handoff behavior

Any reported reply pauses the nurture sequence. Buying intent also marks the lead Hot. The application records the reason and surfaces the lead in Dashboard → AI outreach → Human handoffs.

Active/trialing paid organizations can also send an external handoff webhook. Basic organizations retain the in-app handoff.

## Security before production

Use HTTPS, rotate/revoke agent tokens, rate-limit claim and completion routes, add agent-IP/device constraints where practical, and audit each delivery. For high-volume multi-worker deployments use PostgreSQL row locking and add claim leases/recovery for abandoned outreach tasks.
