import argparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import engine
from app.models import AssessmentAssignment, Candidate
from app.models.candidate import Role
from app.services.authorization import create_personal_token
from app.services.database import initialize_database


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a candidate test assignment")
    parser.add_argument("candidate_id", help="Imported candidate ID, such as C2041")
    parser.add_argument("--role", required=True, help="Question role to assign")
    args = parser.parse_args()

    initialize_database(engine)
    with Session(engine) as db:
        candidate = db.scalar(
            select(Candidate).where(
                Candidate.email == f"{args.candidate_id.lower()}@synthetic.invalid",
                Candidate.role == Role.CANDIDATE,
            )
        )
        if candidate is None:
            raise SystemExit(f"Candidate {args.candidate_id} was not found")

        existing = db.scalar(
            select(AssessmentAssignment).where(
                AssessmentAssignment.candidate_id == candidate.id,
                AssessmentAssignment.role == args.role,
            )
        )
        if existing:
            raise SystemExit("An assignment already exists for this candidate and role")

        token, token_hash = create_personal_token()
        assignment = AssessmentAssignment(
            candidate_id=candidate.id,
            role=args.role,
            token_hash=token_hash,
        )
        db.add(assignment)
        db.commit()
        print(f"Candidate: {args.candidate_id}")
        print(f"Role: {args.role}")
        print(f"Personal link token: {token}")
        print(f"Personal link path: /candidate/assessments/{token}")


if __name__ == "__main__":
    main()
