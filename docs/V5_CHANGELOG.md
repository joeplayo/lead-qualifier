# LeadSignal v0.5 changelog

## Superuser administration

- Added a dedicated `/admin/` browser console.
- Added local SQLite superuser bootstrap for `admin`.
- Bootstrap bypasses customer email/password validation only for this special account.
- Added the `superuser` membership role and session authorization guard.
- Added safe cross-tenant organization context for superusers via `X-Organization-ID`.
- Added system-wide overview metrics.
- Added organization listing and plan updates.
- Added user listing plus enable/disable actions.
- Added recent qualification-job visibility.
- Added an Admin Console link to the main dashboard for superusers.
- Preserved the existing `ADMIN_API_KEY` organization-provisioning endpoint.
- Added a collision guard so an unrelated existing `admin` account is not silently promoted.\n- Added `scripts/bootstrap_superuser.py` for explicit non-SQLite provisioning.

## Security note

The requested development credential is intentionally supported for local SQLite startup. Rotate it and disable bootstrap before exposing the service to the public internet.
