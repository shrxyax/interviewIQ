"""
Closed-loop validation: does belief.update() still separate robust from
memorised knowledge when its outcomes come from the real verifier on real
answer text, instead of simulate.py's clean theta sample?

simulate.py's run_episode() samples o ~ theta_world[probe_type][z] directly
-- it never calls consistency.py. That tests the belief engine's math in
isolation from the observation model. This script closes the other half of
the loop: for each (concept, persona) group in verifier_corpus.json where
persona is "robust" or "memoriser", it runs the real hand-labelled answers
through assess_answer() (the real verifier + symbolic layer) to get a real
answer_class per probe, derives the outcome the same way
mkt/service.py::submit_answer() does (BASE_OUTCOME for the base probe,
relation_outcome() for metamorphic probes, including mr_constraint answer
similarity via the real embedding model), and feeds those outcomes into
belief.update() in probe order. The question: starting from a uniform
prior, does the resulting belief end up closer to ROBUST for robust
episodes and MEMORISED for memoriser episodes, or does verifier noise blur
the two together?

Usage (run from backend/, with the dev DB already seeded):
    python -m app.modules.mkt.eval.run_closed_loop --verifier local
    python -m app.modules.mkt.eval.run_closed_loop --verifier llm --sleep 13
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from app.core.db import SessionLocal
from app.modules.mkt.belief import UNIFORM_PRIOR, robustness_index, update
from app.modules.mkt.consistency import (
    BASE_OUTCOME,
    CONTRADICTED,
    Verifier,
    assess_answer,
    relation_outcome,
)
from app.modules.mkt.emissions import DEFAULT_THETA
from app.modules.mkt.eval.run_verifier_eval import build_verifier, load_corpus, patch_llm_rate_limit
from app.modules.mkt.models import Concept, ProbeTemplate
from app.modules.mkt.states import BASE, MR_CONSTRAINT, MR_PARAPHRASE, S_M, S_R, STATES

PROBE_ORDER = ["base", "mr_paraphrase", "mr_constraint", "mr_inversion", "mr_pushback"]
TRUE_STATE = {"robust": S_R, "memoriser": S_M}


def _template_and_concept(db, concept_id: str, probe_type: str) -> tuple[ProbeTemplate, Concept]:
    template = (
        db.query(ProbeTemplate)
        .filter_by(concept_id=concept_id, probe_type=probe_type, validated=True)
        .order_by(ProbeTemplate.id)
        .first()
    )

    if template is None:
        raise ValueError(f"No validated probe template for ({concept_id}, {probe_type}).")

    return template, db.get(Concept, concept_id)


def group_episodes(corpus: list[dict]) -> dict[tuple[str, str], dict[str, dict]]:
    """(concept_id, persona) -> {probe_type: item}, restricted to robust/memoriser."""

    groups: dict[tuple[str, str], dict[str, dict]] = defaultdict(dict)

    for item in corpus:
        if item["persona"] in TRUE_STATE:
            groups[(item["concept_id"], item["persona"])][item["probe_type"]] = item

    return groups


def run_episode(db, verifier: Verifier, embed, concept_id: str, persona: str, probes: dict[str, dict]) -> dict:
    belief = UNIFORM_PRIOR.copy()
    true_state = TRUE_STATE[persona]
    base_class, base_answer, base_propositions = None, None, []
    turns = []

    for probe_type in PROBE_ORDER:
        item = probes.get(probe_type)
        if item is None:
            continue

        template, concept = _template_and_concept(db, concept_id, probe_type)
        answer = item["answer"]

        if probe_type == BASE:
            assessment, _ = assess_answer(template.question, answer, template.relation_spec, concept.misconceptions, verifier)
            outcome = BASE_OUTCOME[assessment.answer_class]
            base_class, base_answer = assessment.answer_class, answer
            base_propositions = assessment.propositions[:6]
        else:
            extra = base_propositions if probe_type == MR_PARAPHRASE else []
            assessment, _ = assess_answer(
                template.question,
                answer,
                template.relation_spec,
                concept.misconceptions,
                verifier,
                extra_statements=extra,
            )

            contradicted = sum(
                1 for claim in extra if assessment.verdicts.get(claim, {}).get("label") == CONTRADICTED
            )

            similarity = None
            if probe_type == MR_CONSTRAINT and base_answer:
                vecs = np.asarray(embed([base_answer, answer]))
                similarity = float(vecs[0] @ vecs[1])

            outcome, _ = relation_outcome(
                probe_type,
                base_class,
                assessment,
                prior_claims_contradicted=contradicted,
                answer_similarity=similarity,
            )

        theta = DEFAULT_THETA[probe_type]
        belief = update(belief, theta, outcome)
        turns.append({"probe_type": probe_type, "answer_class": assessment.answer_class, "outcome": outcome})

    guess = int(np.argmax(belief))

    return {
        "concept_id": concept_id,
        "persona": persona,
        "true_state": STATES[true_state],
        "guessed_state": STATES[guess],
        "correct": guess == true_state,
        "belief": [round(float(p), 4) for p in belief],
        "robustness_index": robustness_index(belief),
        "turns": turns,
    }


def summarise(episodes: list[dict]) -> dict:
    by_persona = defaultdict(list)
    for e in episodes:
        by_persona[e["persona"]].append(e)

    summary = {"n_episodes": len(episodes), "overall_accuracy": sum(e["correct"] for e in episodes) / len(episodes)}

    for persona, group in by_persona.items():
        ri = [e["robustness_index"] for e in group if e["robustness_index"] is not None]
        summary[persona] = {
            "n": len(group),
            "accuracy": sum(e["correct"] for e in group) / len(group),
            "mean_robustness_index": float(np.mean(ri)) if ri else None,
        }

    return summary


def print_report(verifier_name: str, summary: dict) -> None:
    print(f"\n=== Closed-loop belief separation, verifier: {verifier_name} ===")
    print(f"n = {summary['n_episodes']} episodes, overall state accuracy = {summary['overall_accuracy']:.3f}\n")
    print(f"{'persona':<12} {'n':>4} {'accuracy':>10} {'mean RI':>10}")

    for persona in ("robust", "memoriser"):
        if persona not in summary:
            continue
        s = summary[persona]
        ri = f"{s['mean_robustness_index']:.3f}" if s["mean_robustness_index"] is not None else "n/a"
        print(f"{persona:<12} {s['n']:>4} {s['accuracy']:>10.3f} {ri:>10}")

    print(
        "\nRobustness index = P(robust) / (P(robust) + P(memorised)); 1.0 means the belief "
        "fully attributes 'known' mass to robust understanding, 0.0 fully to memorisation."
    )


def main():
    parser = argparse.ArgumentParser(description="Closed-loop MKT validation: real verifier -> real belief update.")
    parser.add_argument("--verifier", choices=["local", "llm", "fallback"], default="local")
    parser.add_argument("--out", type=str, default=None)
    parser.add_argument("--sleep", type=float, default=13.0, help="Min seconds between real Gemini calls (llm/fallback only).")
    args = parser.parse_args()

    if args.verifier in ("llm", "fallback"):
        patch_llm_rate_limit(args.sleep)

    corpus = load_corpus()
    groups = group_episodes(corpus)

    from app.services.embeddings import generate_embeddings

    with SessionLocal() as db:
        verifier = build_verifier(args.verifier)
        episodes = [
            run_episode(db, verifier, generate_embeddings, concept_id, persona, probes)
            for (concept_id, persona), probes in sorted(groups.items())
        ]

    summary = summarise(episodes)
    print_report(args.verifier, summary)

    if args.out:
        Path(args.out).write_text(json.dumps({"summary": summary, "episodes": episodes}, indent=2), encoding="utf-8")
        print(f"\nFull results written to {args.out}")


if __name__ == "__main__":
    main()
