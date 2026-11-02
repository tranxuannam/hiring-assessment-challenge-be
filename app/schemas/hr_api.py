from uuid import UUID

from pydantic import BaseModel, Field


class MockHRSignInRequest(BaseModel):
    email: str


class MockHRSignInResponse(BaseModel):
    label: str
    header: str


class AssignmentCreateRequest(BaseModel):
    candidate_id: UUID
    role: str = Field(min_length=1, max_length=120)


class AssignmentCreateResponse(BaseModel):
    assignment_id: UUID
    personal_link_token: str
    status: str


class HRCandidateSummary(BaseModel):
    candidate_id: UUID
    candidate_name: str
    email: str
    role: str
    answer_count: int


class HRAnswerResponse(BaseModel):
    answer_id: UUID
    candidate_id: UUID
    candidate_name: str
    question_id: UUID
    question: str
    answer_text: str | None
    audio_path: str | None
    audio_url: str | None
    suggested_score: float | None
    suggested_reason: str | None
    effective_score: float | None
    scoring_status: str | None


class ScoreOverrideRequest(BaseModel):
    score: int = Field(ge=1, le=4)
    reason: str = Field(min_length=1, max_length=2000)


class ScoreOverrideResponse(BaseModel):
    answer_id: UUID
    score: int
    reason: str


class ScoreRetryResponse(BaseModel):
    answer_id: UUID
    status: str


class ScoreOverrideAuditResponse(BaseModel):
    previous_score: float
    new_score: float
    reason: str
    hr_user_id: UUID
