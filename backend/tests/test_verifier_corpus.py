"""
Schema sanity for verifier_corpus.json. Deliberately does NOT call a real
verifier (LLM cost, NLI model load time); see eval/run_verifier_eval.py for
the actual accuracy measurement.
"""

import json
from pathlib import Path

import pytest

from app.core.db import SessionLocal, init_db
from app.modules.mkt.models import Concept, ProbeTemplate
from app.modules.mkt.seed import seed_all

CORPUS_PATH = Path(__file__).parent.parent / "app/modules/mkt/eval/verifier_corpus.json"
PERSONAS = {"robust", "memoriser", "misconceived", "absent"}
CLASSES = {"empty", "partial", "wrong", "correct"}
FALSE_CLAIM_LABELS = {"supported", "contradicted", "not_addressed"}


@pytest.fixture(scope="module")
def corpus():
    return json.loads(CORPUS_PATH.read_text(encoding="utf-8"))["items"]


@pytest.fixture(scope="module", autouse=True)
def seeded_db():
    init_db()

    with SessionLocal() as db:
        seed_all(db)


def test_corpus_items_are_well_formed(corpus):
    assert len(corpus) > 0

    for item in corpus:
        assert item["persona"] in PERSONAS
        assert item["expected_class"] in CLASSES
        assert item["probe_type"]
        assert item["concept_id"]
        assert item["answer"].strip() != ""

        if "expected_false_claim" in item:
            assert item["expected_false_claim"] in FALSE_CLAIM_LABELS


def test_every_item_resolves_to_a_seeded_template_and_concept(corpus):
    with SessionLocal() as db:
        missing = []

        for item in corpus:
            template = (
                db.query(ProbeTemplate)
                .filter_by(concept_id=item["concept_id"], probe_type=item["probe_type"], validated=True)
                .first()
            )
            concept = db.get(Concept, item["concept_id"])

            if template is None or concept is None:
                missing.append((item["concept_id"], item["probe_type"]))

        assert not missing, f"Corpus items with no matching seeded (concept, probe_type): {missing}"


def test_pushback_items_have_a_false_claim_in_their_template(corpus):
    with SessionLocal() as db:
        for item in corpus:
            if "expected_false_claim" not in item:
                continue

            template = (
                db.query(ProbeTemplate)
                .filter_by(concept_id=item["concept_id"], probe_type=item["probe_type"], validated=True)
                .first()
            )
            assert template.relation_spec.get("false_claim"), (
                f"({item['concept_id']}, {item['probe_type']}) has an expected_false_claim "
                "but its template's relation_spec has none."
            )
