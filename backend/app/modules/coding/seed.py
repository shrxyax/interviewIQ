import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.modules.coding.models import CodingProblem

SEED_PATH = Path(__file__).parent / "seed" / "problems.json"


def seed_all(db: Session) -> int:
    data = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    n = 0

    for order, p in enumerate(data["problems"]):
        row = db.get(CodingProblem, p["id"]) or CodingProblem(id=p["id"])
        row.title = p["title"]
        row.difficulty = p["difficulty"]
        row.statement = p["statement"]
        row.signature = p["signature"]
        row.starter_code = p["starter_code"]
        row.sample_tests = p["sample_tests"]
        row.hidden_tests = p["hidden_tests"]
        row.order = order
        db.merge(row)
        n += 1

    db.commit()
    return n
