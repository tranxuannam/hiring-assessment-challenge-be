from uuid import uuid4

from sqlalchemy.orm import Session

from app.models import Answer, AssessmentAssignment, Candidate, Question, Score
from app.models.candidate import Role
from app.services.authorization import create_personal_token


def seed_assignment(engine, email: str, role: str = "Backend"):
    with Session(engine) as db:
        candidate = Candidate(
            email=email,
            full_name="Candidate",
            role=Role.CANDIDATE,
        )
        question = Question(
            role=role,
            prompt="Explain a transaction.",
            position=1,
            evaluation_criteria="Mention atomicity.",
        )
        db.add_all([candidate, question])
        db.commit()
        token, token_hash = create_personal_token()
        assignment = AssessmentAssignment(
            candidate_id=candidate.id,
            role=role,
            token_hash=token_hash,
        )
        db.add(assignment)
        db.commit()
        return token, question.id, candidate.id


def test_hr_requires_mock_sign_in(client):
    response = client.get("/hr/candidates")
    assert response.status_code == 401


def test_non_hr_cannot_access_hr_data(client, test_engine):
    with Session(test_engine) as db:
        db.add(
            Candidate(
                email="candidate-auth@example.com",
                full_name="Candidate",
                role=Role.CANDIDATE,
            )
        )
        db.commit()
    response = client.get(
        "/hr/candidates",
        headers={"X-Mock-HR-Email": "candidate-auth@example.com"},
    )
    assert response.status_code == 403


def test_invalid_personal_link_is_rejected(client):
    response = client.get("/candidate/assessments/not-a-token")
    assert response.status_code == 404


def test_candidate_progress_and_duplicate_answer_are_safe(client, test_engine):
    token, question_id, _ = seed_assignment(
        test_engine, f"{uuid4()}@example.com"
    )
    first = client.post(
        f"/candidate/assessments/{token}/answers",
        json={"question_id": str(question_id), "answer_text": "It is atomic."},
    )
    retry = client.post(
        f"/candidate/assessments/{token}/answers",
        json={"question_id": str(question_id), "answer_text": "Changed on retry."},
    )

    assert first.status_code == 200
    assert retry.status_code == 200
    assert retry.json()["answer_id"] == first.json()["answer_id"]
    with Session(test_engine) as db:
        assert db.query(Answer).count() == 1
        assert db.query(Answer).one().answer_text == "It is atomic."

    refreshed = client.get(f"/candidate/assessments/{token}")
    assert refreshed.status_code == 200
    assert refreshed.json()["next_question"] is None


def test_candidate_progress_only_counts_answers_for_assignment_role(
    client, test_engine
):
    token, question_id, candidate_id = seed_assignment(
        test_engine, f"{uuid4()}@example.com"
    )
    with Session(test_engine) as db:
        other_question = Question(
            role="Private Role",
            prompt="Private question",
            position=1,
            evaluation_criteria="Private",
        )
        db.add(other_question)
        db.commit()
        db.add(
            Answer(
                candidate_id=candidate_id,
                question_id=other_question.id,
                answer_text="An answer for another assessment.",
            )
        )
        db.commit()

    response = client.get(f"/candidate/assessments/{token}")

    assert response.status_code == 200
    assert response.json()["answered_count"] == 0
    assert response.json()["total_questions"] == 1
    assert response.json()["next_question"]["question_id"] == str(question_id)


def test_candidate_cannot_submit_another_role_question(client, test_engine):
    token, _, _ = seed_assignment(test_engine, f"{uuid4()}@example.com")
    with Session(test_engine) as db:
        other_question = Question(
            role="Private Role",
            prompt="Private question",
            position=1,
            evaluation_criteria="Private",
        )
        db.add(other_question)
        db.commit()
        question_id = other_question.id

    response = client.post(
        f"/candidate/assessments/{token}/answers",
        json={"question_id": str(question_id), "answer_text": "Not allowed."},
    )
    assert response.status_code == 404


def test_candidate_submission_is_not_exposed_in_candidate_response(
    client, test_engine
):
    token, question_id, _ = seed_assignment(test_engine, f"{uuid4()}@example.com")
    with Session(test_engine) as db:
        answer = Answer(
            candidate_id=db.query(AssessmentAssignment).one().candidate_id,
            question_id=question_id,
            answer_text="Existing answer",
        )
        db.add(answer)
        db.commit()
        db.add(
            Score(
                answer_id=answer.id,
                score=4,
                reason="Suggested reason",
                model_name="test",
                prompt_version="test",
            )
        )
        db.commit()

    response = client.get(f"/candidate/assessments/{token}")
    assert response.status_code == 200
    assert "score" not in response.text.lower()
