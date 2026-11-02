import secrets
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Answer, Question
from app.models.assessment import AnswerType
from app.schemas.candidate_api import (
    CandidateAnswerRequest,
    CandidateAnswerResponse,
    CandidateAssignmentResponse,
    CandidateQuestionResponse,
    CandidateSubmitResponse,
)
from app.services.authorization import get_assignment_by_token
from app.services.candidate import get_next_question, save_text_answer, submit_assignment
from app.services.scoring import enqueue_scoring_job

router = APIRouter(prefix="/candidate", tags=["candidate"])


@router.get("/assessments/{token}", response_model=CandidateAssignmentResponse)
def get_assignment(token: str, db: Session = Depends(get_db)):
    assignment, question, answered_count, total_questions = get_next_question(db, token)
    return CandidateAssignmentResponse(
        status=assignment.status.value,
        next_question=(
            CandidateQuestionResponse(
                question_id=question.id,
                position=question.position,
                prompt=question.prompt,
            )
            if question
            else None
        ),
        answered_count=answered_count,
        total_questions=total_questions,
    )


@router.post("/assessments/{token}/answers", response_model=CandidateAnswerResponse)
def submit_answer(
    token: str,
    payload: CandidateAnswerRequest,
    db: Session = Depends(get_db),
):
    try:
        answer = save_text_answer(db, token, payload.question_id, payload.answer_text)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return CandidateAnswerResponse(
        answer_id=answer.id, question_id=answer.question_id, status="accepted"
    )


@router.post("/assessments/{token}/audio", response_model=CandidateAnswerResponse)
async def upload_audio(
    token: str,
    question_id: UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    assignment = get_assignment_by_token(db, token)
    if assignment.status.value != "active":
        raise HTTPException(status_code=409, detail="Assignment is closed")
    allowed_audio_types = {
        "audio/m4a",
        "audio/mp4",
        "audio/x-m4a",
        "audio/mpeg",
        "audio/wav",
        "audio/webm",
        "audio/ogg",
    }
    file_extension = Path(file.filename or "").suffix.lower()
    if file.content_type not in allowed_audio_types and file_extension != ".m4a":
        raise HTTPException(status_code=415, detail="Unsupported audio type")
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Audio file is too large")
    question = db.scalar(
        select(Question).where(
            Question.id == question_id, Question.role == assignment.role
        )
    )
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    existing = db.scalar(
        select(Answer).where(
            Answer.candidate_id == assignment.candidate_id,
            Answer.question_id == question_id,
        )
    )
    if existing:
        return CandidateAnswerResponse(
            answer_id=existing.id, question_id=question_id, status="already_submitted"
        )
    upload_dir = Path("uploads") / str(assignment.candidate_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / f"{question_id}-{secrets.token_hex(16)}{file_extension or '.audio'}"
    path.write_bytes(content)
    answer = Answer(
        candidate_id=assignment.candidate_id,
        question_id=question_id,
        answer_type=AnswerType.AUDIO,
        audio_path=str(path),
    )
    db.add(answer)
    db.flush()
    enqueue_scoring_job(db, answer.id)
    db.commit()
    db.refresh(answer)
    return CandidateAnswerResponse(
        answer_id=answer.id, question_id=question_id, status="accepted"
    )


@router.post("/assessments/{token}/submit", response_model=CandidateSubmitResponse)
def submit(token: str, db: Session = Depends(get_db)):
    assignment = submit_assignment(db, token)
    return CandidateSubmitResponse(status=assignment.status.value)
