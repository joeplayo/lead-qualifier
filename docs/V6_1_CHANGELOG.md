# LeadLift v0.6.1 hotfix

This hotfix addresses duplicate manual leads and missing lead maintenance controls.

## Fixed
- Manual scoring retries reuse an existing contact when the email or phone already exists.
- A failed first-time qualification removes the just-created lead instead of leaving an unqualified duplicate behind.
- Lead records can be edited from the dashboard drawer.
- Lead records can be permanently deleted with their lead-scoped queue, outreach, CRM mapping, lifecycle, assignment, and activity rows.
- A selected lead can remove other visible duplicate copies with the same email or phone in one action.
- `.env` is loaded automatically by both the API and worker.
- Visible product branding is updated to LeadLift while legacy database/cookie/protocol identifiers remain unchanged for compatibility.

## API additions
- `PATCH /api/v1/leads/{lead_id}`
- `DELETE /api/v1/leads/{lead_id}`
- `DELETE /api/v1/leads/{lead_id}/duplicates`

All mutation endpoints enforce the existing lead visibility hierarchy.
