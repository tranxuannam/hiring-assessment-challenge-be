from uuid import UUID

from pydantic import BaseModel, Field


class CandidateQuestionResponse(BaseModel):
    question_id: UUID
    position: int
    prompt: str


class CandidateAssignmentResponse(BaseModel):
    status: str
    next_question: CandidateQuestionResponse | None
    answered_count: int
    total_questions: int


class CandidateAnswerRequest(BaseModel):
    question_id: UUID
    answer_text: str = Field(min_length=1, max_length=20000)


class CandidateAnswerResponse(BaseModel):
    answer_id: UUID
    question_id: UUID
    status: str


class CandidateSubmitResponse(BaseModel):
    status: str
