import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.modules.content.models import Company, CompanyWeight, CoreCSNote, SheetProblem, SheetTopic

SEED_DIR = Path(__file__).parent / "seed"


def seed_dsa_sheet(db: Session) -> int:
    data = json.loads((SEED_DIR / "dsa_sheet.json").read_text(encoding="utf-8"))
    n = 0

    for order, topic in enumerate(data["topics"]):
        row = db.get(SheetTopic, topic["id"]) or SheetTopic(id=topic["id"])
        row.sheet, row.name, row.order = "dsa", topic["name"], order
        db.merge(row)

        for p_order, p in enumerate(topic["problems"]):
            prow = db.get(SheetProblem, p["id"]) or SheetProblem(id=p["id"])
            prow.topic_id = topic["id"]
            prow.title = p["title"]
            prow.difficulty = p["difficulty"]
            prow.pattern = p.get("pattern", "")
            prow.leetcode_url = p.get("leetcode_url")
            prow.source_path = p.get("source_path")
            prow.concept_id = p.get("concept_id")
            prow.order = p_order
            db.merge(prow)
            n += 1

    db.commit()
    return n


def seed_core_cs(db: Session) -> int:
    data = json.loads((SEED_DIR / "core_cs_notes.json").read_text(encoding="utf-8"))
    n = 0

    for order, topic in enumerate(data["topics"]):
        row = db.get(SheetTopic, topic["id"]) or SheetTopic(id=topic["id"])
        row.sheet, row.name, row.order = "core_cs", topic["name"], order
        db.merge(row)

        for note_order, note in enumerate(topic["notes"]):
            note_id = f"{topic['id']}.n{note_order + 1:02d}"
            nrow = db.get(CoreCSNote, note_id) or CoreCSNote(id=note_id)
            nrow.topic_id = topic["id"]
            nrow.title = note["title"]
            nrow.body_markdown = note["body"]
            nrow.order = note_order
            db.merge(nrow)
            n += 1

    db.commit()
    return n


def seed_companies(db: Session) -> int:
    data = json.loads((SEED_DIR / "companies.json").read_text(encoding="utf-8"))
    n = 0

    for c in data["companies"]:
        row = db.get(Company, c["id"]) or Company(id=c["id"])
        row.name, row.tier, row.rounds = c["name"], c["tier"], c["rounds"]
        db.merge(row)
        db.flush()

        for ref_type, weights in c.get("emphasis", {}).items():
            for ref_id, weight in weights.items():
                existing = db.query(CompanyWeight).filter_by(company_id=c["id"], ref_type=ref_type, ref_id=ref_id).first()
                w = existing or CompanyWeight(company_id=c["id"], ref_type=ref_type, ref_id=ref_id)
                w.weight = weight
                db.add(w)
                n += 1

    db.commit()
    return n


def seed_all(db: Session) -> dict:
    return {
        "dsa_problems": seed_dsa_sheet(db),
        "core_cs_notes": seed_core_cs(db),
        "company_weights": seed_companies(db),
    }
