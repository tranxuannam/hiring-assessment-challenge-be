import argparse
import time
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.session import engine
from app.models import ScoringJob
from app.models.scoring import ScoringJobStatus
from app.services.database import initialize_database
from app.services.scoring import process_scoring_job


def claim_job(db: Session):
    now = datetime.now(timezone.utc)
    job = db.scalar(
        select(ScoringJob)
        .where(
            ScoringJob.status == ScoringJobStatus.QUEUED,
            (ScoringJob.available_at.is_(None) | (ScoringJob.available_at <= now)),
        )
        .order_by(ScoringJob.created_at)
        .limit(1)
    )
    if job is None:
        return None
    result = db.execute(
        update(ScoringJob)
        .where(
            ScoringJob.id == job.id,
            ScoringJob.status == ScoringJobStatus.QUEUED,
        )
        .values(
            status=ScoringJobStatus.PROCESSING,
            attempts=ScoringJob.attempts + 1,
        )
    )
    if result.rowcount != 1:
        db.rollback()
        return None
    db.commit()
    return job.id


def run_worker(once: bool = False, poll_seconds: float = 2.0) -> None:
    initialize_database(engine)
    summary = {status.value: 0 for status in ScoringJobStatus}
    while True:
        with Session(engine) as db:
            job_id = claim_job(db)
            if job_id is not None:
                job = process_scoring_job(db, job_id)
                summary[job.status.value] += 1
                print(f"{job.id}: {job.status.value}")
                continue
        if once:
            print(summary)
            return
        time.sleep(poll_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Process queued scoring jobs")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process currently available jobs, then exit",
    )
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    args = parser.parse_args()
    run_worker(once=args.once, poll_seconds=args.poll_seconds)


if __name__ == "__main__":
    main()
