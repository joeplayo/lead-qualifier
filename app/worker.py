from __future__ import annotations

import logging
import time

from app.config import settings
from app.db import Base, SessionLocal, engine
from app.models import Organization
from app.services.notifications import send_hot_lead_notification
from app.services.queue import claim_next_job, process_qualification_job, recover_stale_jobs
from app.services.outreach import maybe_autopilot_after_qualification

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("leadsignal.worker")


def run_once() -> bool:
    with SessionLocal() as db:
        recover_stale_jobs(db)
        job = claim_next_job(db)
        if not job:
            return False
        job_id = job.id
        log.info("processing qualification job %s attempt %s/%s", job.id, job.attempts, job.max_attempts)
        lead = process_qualification_job(db, job)
        if lead:
            org = db.get(Organization, lead.organization_id)
            maybe_autopilot_after_qualification(db, lead)
            paid_alerts = bool(org and org.plan in {"starter", "growth"} and org.subscription_status in {"active", "trialing"})
            delivered = send_hot_lead_notification(db, org, lead) if org and lead.status == "Hot" and paid_alerts else False
            log.info(
                "qualified lead %s as %s (%s/10)%s",
                lead.id,
                lead.status,
                lead.score,
                " and sent hot-lead webhook" if delivered else "",
            )
        else:
            db.refresh(job)
            log.warning("job %s ended as %s: %s", job_id, job.status, job.last_error or "retry scheduled")
        return True


def main():
    Base.metadata.create_all(bind=engine)
    log.info("LeadSignal worker started")
    while True:
        worked = run_once()
        if not worked:
            time.sleep(settings.worker_poll_seconds)


if __name__ == "__main__":
    main()
