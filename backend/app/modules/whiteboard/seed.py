import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.modules.whiteboard.models import DesignPrompt

SEED_PATH = Path(__file__).parent / "seed_data" / "design_prompts.json"


def seed_all(db: Session) -> int:
    data = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    n = 0

    for p in data["prompts"]:
        row = db.get(DesignPrompt, p["id"]) or DesignPrompt(id=p["id"])
        row.subtopic_id = p["subtopic_id"]
        row.subtopic_name = p["subtopic_name"]
        row.title = p["title"]
        row.scenario = p["scenario"]
        row.difficulty = p["difficulty"]
        row.tags = p.get("tags", [])
        row.simulatable = p.get("simulatable", False)
        row.requirements = p.get("requirements")
        row.starter_graph = p.get("starter_graph")
        db.merge(row)
        n += 1

    db.commit()
    return n
