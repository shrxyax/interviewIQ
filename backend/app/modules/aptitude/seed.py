import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.modules.aptitude.models import AptitudeQuestion

SEED_PATH = Path(__file__).parent / "seed" / "questions.json"


def seed_all(db: Session) -> int:
    data = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    n = 0

    for order, q in enumerate(data["questions"]):
        row = db.get(AptitudeQuestion, q["id"]) or AptitudeQuestion(id=q["id"])
        row.category = q["category"]
        row.difficulty = q["difficulty"]
        row.question = q["question"]
        row.options = q["options"]
        row.correct_index = q["correct_index"]
        row.explanation = q.get("explanation", "")
        row.order = order
        db.merge(row)
        n += 1

    db.commit()
    return n
