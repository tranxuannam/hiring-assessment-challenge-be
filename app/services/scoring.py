from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.models import Answer, Score, ScoringJob
from app.models.scoring import ScoringJobStatus
from app.services.llm import (
    InvalidLLMOutput,
    LLMClient,
    OpenAIGradingClient,
    PROMPT_VERSION,
)
from app.schemas.scoring_result import ScoringResult


class ScoringJobNotFound(LookupError):
    pass


def enqueue_scoring_job(db: Session, answer_id: UUID) -> ScoringJob:
    existing = db.scalar(select(ScoringJob).where(ScoringJob.answer_id == answer_id))
    if existing:
        return existing
    if not db.get(Answer, answer_id):
        raise ScoringJobNotFound(f"Answer {answer_id} does not exist")
    job = ScoringJob(answer_id=answer_id, status=ScoringJobStatus.QUEUED)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def process_scoring_job(
    db: Session,
    job_id: UUID,
    client: LLMClient | None = None,
    settings: Settings | None = None,
) -> ScoringJob:
    settings = settings or get_settings()
    job = db.scalar(
        select(ScoringJob)
        .options(joinedload(ScoringJob.answer).joinedload(Answer.question))
        .where(ScoringJob.id == job_id)
    )
    if not job:
        raise ScoringJobNotFound(f"Scoring job {job_id} does not exist")
    if job.status == ScoringJobStatus.SCORED:
        return job
    if job.status == ScoringJobStatus.NEEDS_HUMAN:
        return job
    if job.status == ScoringJobStatus.FAILED and job.attempts >= settings.scoring_max_attempts:
        return job

    if job.status != ScoringJobStatus.PROCESSING:
        job.status = ScoringJobStatus.PROCESSING
        job.attempts += 1
        db.commit()

    try:
        provider = client or OpenAIGradingClient(settings)
        answer = job.answer
        if not answer.answer_text:
            job.status = ScoringJobStatus.NEEDS_HUMAN
            job.last_error = "Audio answer requires transcription before LLM scoring"
            db.commit()
            return job
        candidate_text = answer.answer_text
        result = ScoringResult.model_validate(provider.score(
            question=answer.question.prompt,
            grading_guide=answer.question.evaluation_criteria,
            answer=candidate_text,
        ))
    except (InvalidLLMOutput, ValidationError) as exc:
        job.status = ScoringJobStatus.NEEDS_HUMAN
        job.last_error = str(exc)
        db.commit()
        return job
    except Exception as exc:
        job.last_error = str(exc)[:1000]
        if job.attempts >= settings.scoring_max_attempts:
            job.status = ScoringJobStatus.FAILED
        else:
            job.status = ScoringJobStatus.QUEUED
            job.available_at = datetime.now(timezone.utc) + timedelta(
                seconds=2**job.attempts
            )
        db.commit()
        return job

    score = db.scalar(select(Score).where(Score.answer_id == answer.id))
    if score is None:
        db.add(
            Score(
                answer_id=answer.id,
                score=result.score,
                reason=result.reason,
                model_name=provider.model_name,
                prompt_version=PROMPT_VERSION,
            )
        )
    job.status = ScoringJobStatus.SCORED
    job.last_error = None
    db.commit()
    db.refresh(job)
    return job
