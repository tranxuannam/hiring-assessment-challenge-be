import argparse
import json
import re
import shutil
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import engine
from app.models import Answer, Candidate, Question, ScoringJob
from app.models.assessment import AnswerType
from app.models.candidate import Role
from app.models.scoring import ScoringJobStatus
from app.services.database import initialize_database


def parse_questions(path: Path) -> dict[int, tuple[str, str]]:
    questions: dict[int, tuple[str, str]] = {}
    current_id: int | None = None
    prompt_lines: list[str] = []
    guide_lines: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## Q"):
            if current_id is not None:
                questions[current_id] = (
                    " ".join(prompt_lines).strip(),
                    "\n".join(guide_lines).strip(),
                )
            match = re.match(r"## Q(\d+)\.\s*(.+)$", line)
            if not match:
                raise ValueError(f"Invalid question heading: {line}")
            current_id = int(match.group(1))
            prompt_lines = [match.group(2).strip()]
            guide_lines = []
        elif current_id is not None:
            if line.startswith("- "):
                guide_lines.append(line[2:].strip())
            elif line.strip() and not guide_lines:
                prompt_lines.append(line.strip())
    if current_id is not None:
        questions[current_id] = (
            " ".join(prompt_lines).strip(),
            "\n".join(guide_lines).strip(),
        )
    return questions


def import_data_pack(data_dir: Path, limit: int | None = None) -> dict[str, int]:
    initialize_database(engine)
    questions = parse_questions(data_dir / "questions.md")
    answer_files = sorted((data_dir / "answers").glob("A*.json"))
    if limit is not None:
        answer_files = answer_files[:limit]
    uploads_dir = Path("uploads") / "imported"
    counts = {"candidates": 0, "questions": 0, "answers": 0, "jobs": 0, "audio": 0}

    with Session(engine) as db:
        for answer_file in answer_files:
            payload = json.loads(answer_file.read_text(encoding="utf-8"))
            candidate_id = payload["candidate_id"]
            role = payload["role"]
            question_number = int(payload["question_id"].removeprefix("Q"))
            prompt, guide = questions[question_number]

            candidate = db.scalar(
                select(Candidate).where(
                    Candidate.email == f"{candidate_id.lower()}@synthetic.invalid"
                )
            )
            if candidate is None:
                candidate = Candidate(
                    email=f"{candidate_id.lower()}@synthetic.invalid",
                    full_name=f"Imported {candidate_id}",
                    role=Role.CANDIDATE,
                )
                db.add(candidate)
                db.flush()
                counts["candidates"] += 1

            question = db.scalar(
                select(Question).where(
                    Question.role == role, Question.position == question_number
                )
            )
            if question is None:
                question = Question(
                    role=role,
                    prompt=prompt,
                    position=question_number,
                    evaluation_criteria=guide,
                    max_score=4,
                )
                db.add(question)
                db.flush()
                counts["questions"] += 1

            existing = db.scalar(
                select(Answer).where(
                    Answer.candidate_id == candidate.id,
                    Answer.question_id == question.id,
                )
            )
            if existing is not None:
                continue

            transcript = payload.get("transcript")
            audio_source = answer_file.with_suffix(".m4a")
            audio_path = None
            answer_type = AnswerType.TEXT
            if transcript is None and audio_source.exists():
                target_dir = uploads_dir / candidate_id
                target_dir.mkdir(parents=True, exist_ok=True)
                target = target_dir / audio_source.name
                shutil.copyfile(audio_source, target)
                audio_path = str(target)
                answer_type = AnswerType.AUDIO
                counts["audio"] += 1

            answer = Answer(
                candidate_id=candidate.id,
                question_id=question.id,
                answer_type=answer_type,
                answer_text=transcript,
                audio_path=audio_path,
            )
            db.add(answer)
            db.flush()
            db.add(
                ScoringJob(
                    answer_id=answer.id,
                    status=ScoringJobStatus.QUEUED,
                )
            )
            counts["answers"] += 1
            counts["jobs"] += 1
        db.commit()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Import synthetic hiring data")
    parser.add_argument("data_dir", type=Path)
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of answer JSON files to import (default: 10)",
    )
    args = parser.parse_args()
    counts = import_data_pack(args.data_dir, args.limit)
    print(json.dumps(counts, indent=2))


if __name__ == "__main__":
    main()
