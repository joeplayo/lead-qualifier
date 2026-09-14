# v0.4 Automation Milestone

## Added

- Revocable inbound webhook endpoints with one-time secret URLs.
- Optional `Idempotency-Key` support to deduplicate retried inbound deliveries.
- Database-backed `qualification_jobs` queue.
- Separate `python -m app.worker` process with retry/backoff and stale-job recovery.
- Per-organization Hot-lead outbound webhook configuration.
- Optional HMAC-SHA256 signatures for outbound notifications.
- Dashboard Automations screen for webhook and notification setup.
- Inbox auto-refresh while visible.
- Docker Compose worker service.
- v0.4 queue, signature, and dashboard tests.

## Git commit

Suggested commit message:

`feat: add async lead ingestion and hot-lead automations`

## Local run

Terminal 1:

```bash
uvicorn app.main:app --reload
```

Terminal 2:

```bash
python -m app.worker
```

Or:

```bash
docker compose up --build
```
