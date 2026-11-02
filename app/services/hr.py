from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Answer,
    AssessmentAssignment,
    Candidate,
    ScoreOverrideAudit,
)
from app.models.candidate import Role
from app.services.authorization import create_personal_token


def create_assignment(db: Session, candidate_id, role: str):
    candidate = db.scalar(
        select(Candidate).where(
            Candidate.id == candidate_id, Candidate.role == Role.CANDIDATE
        )
    )
    if not candidate:
        raise LookupError("Candidate not found")
    if db.scalar(
        select(AssessmentAssignment).where(
            AssessmentAssignment.candidate_id == candidate_id,
            AssessmentAssignment.role == role,
        )
    ):
        raise ValueError("Assignment already exists")
    token, token_hash = create_personal_token()
    assignment = AssessmentAssignment(
        candidate_id=candidate_id, role=role, token_hash=token_hash
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment, token


def list_candidates_by_role(db: Session):
    return db.execute(
        select(
            Candidate.id,
            Candidate.full_name,
            Candidate.email,
            Candidate.role,
            func.count(Answer.id).label("answer_count"),
        )
        .outerjoin(Answer, Answer.candidate_id == Candidate.id)
        .where(Candidate.role == Role.CANDIDATE)
        .group_by(Candidate.id)
        .order_by(Candidate.role, Candidate.full_name)
    ).all()


def get_answer_for_hr(db: Session, answer_id):
    return db.scalar(
        select(Answer).where(Answer.id == answer_id).join(Answer.candidate)
    )


def effective_score(db: Session, answer: Answer) -> float | None:
    if not answer.score:
        return None
    latest = db.scalar(
        select(ScoreOverrideAudit)
        .where(ScoreOverrideAudit.score_id == answer.score.id)
        .order_by(ScoreOverrideAudit.created_at.desc())
    )
    return float(latest.new_score) if latest else float(answer.score.score)


def override_score(db: Session, hr: Candidate, answer_id, new_score: int, reason: str):
    answer = get_answer_for_hr(db, answer_id)
    if not answer:
        raise LookupError("Answer not found")
    if not answer.score:
        status = answer.scoring_job.status.value if answer.scoring_job else "not_queued"
        raise ValueError(f"Answer has no suggested score; current scoring status: {status}")
    audit = ScoreOverrideAudit(
        score_id=answer.score.id,
        hr_user_id=hr.id,
        previous_score=effective_score(db, answer),
        new_score=new_score,
        reason=reason,
    )
    db.add(audit)
    db.commit()
    db.refresh(audit)
    return audit


def list_score_overrides(db: Session, answer_id):
    answer = get_answer_for_hr(db, answer_id)
    if not answer or not answer.score:
        raise LookupError("Scored answer not found")
    return db.scalars(
        select(ScoreOverrideAudit)
        .where(ScoreOverrideAudit.score_id == answer.score.id)
        .order_by(ScoreOverrideAudit.created_at)
    ).all()
