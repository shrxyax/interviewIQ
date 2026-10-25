"""
Idempotent loader for authored concept graphs and probe templates.
Re-running updates content in place; it never duplicates rows.
"""

import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.modules.mkt.models import Concept, ConceptEdge, ProbeTemplate
from app.modules.mkt.states import PROBE_TYPES


SEED_DIR = Path(__file__).parent / "seed"


def load_seed_file(db: Session, path: Path) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    domain = data["domain"]

    for c in data["concepts"]:
        concept = db.get(Concept, c["id"]) or Concept(id=c["id"])
        concept.domain = domain
        concept.name = c["name"]
        concept.description = c.get("description", "")
        concept.difficulty = c.get("difficulty", 1)
        concept.key_facts = c.get("key_facts", [])
        concept.misconceptions = c.get("misconceptions", [])
        db.merge(concept)

    db.flush()

    for c in data["concepts"]:
        for parent in c.get("prereqs", []):
            exists = db.query(ConceptEdge).filter_by(src=parent, dst=c["id"], kind="prereq").first()

            if not exists:
                db.add(ConceptEdge(src=parent, dst=c["id"], kind="prereq"))

        for probe_type, spec_or_list in c.get("probes", {}).items():
            if probe_type not in PROBE_TYPES:
                raise ValueError(f"Unknown probe type {probe_type} in {c['id']}")

            # A probe type may seed either one spec (dict) or several (list),
            # e.g. multiple mr_transfer templates per concept.
            specs = spec_or_list if isinstance(spec_or_list, list) else [spec_or_list]

            for i, spec in enumerate(specs):
                seed_key = f"{c['id']}::{probe_type}::{i}"
                template = db.query(ProbeTemplate).filter_by(seed_key=seed_key).first() or ProbeTemplate(seed_key=seed_key)
                template.concept_id = c["id"]
                template.probe_type = probe_type
                template.question = spec["question"]
                template.relation_spec = {k: v for k, v in spec.items() if k != "question"}
                template.source = "authored"
                template.validated = True
                db.add(template)

    db.commit()
    return len(data["concepts"])


def seed_all(db: Session) -> int:
    return sum(load_seed_file(db, path) for path in sorted(SEED_DIR.glob("*.json")))
