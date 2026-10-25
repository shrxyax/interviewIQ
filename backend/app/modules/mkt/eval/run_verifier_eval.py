"""
Verifier validation: the one link in the MKT pipeline that isn't covered
by simulate.py's offline benchmark. simulate.py samples probe outcomes
directly from theta; it never touches consistency.py. This script does
the opposite - it runs real, hand-labelled answer text through the real
verifier (LLMVerifier, LocalVerifier, or FallbackVerifier) and the real
symbolic layer, and compares the resulting answer_class (and, for
pushback probes, the false_claim verdict) against ground truth.

The corpus (verifier_corpus.json) was authored against the actual seeded
probe templates in app/modules/mkt/seed/dsa.json: every question quoted
in the corpus is the live `question` text for that (concept_id,
probe_type) pair, and every answer deliberately PARAPHRASES the
template's must_entail/must_not_entail statements rather than quoting
them, so this measures semantic verification, not string overlap.

Usage (run from backend/, with the dev DB already seeded):
    python -m app.modules.mkt.eval.run_verifier_eval --verifier local
    python -m app.modules.mkt.eval.run_verifier_eval --verifier llm
    python -m app.modules.mkt.eval.run_verifier_eval --verifier both
"""

import argparse
import json
import re
import time
from collections import defaultdict
from pathlib import Path

from app.core.db import SessionLocal
from app.modules.mkt.consistency import FallbackVerifier, LLMVerifier, LocalVerifier, Verifier, assess_answer
from app.modules.mkt.models import Concept, ProbeTemplate

CORPUS_PATH = Path(__file__).parent / "verifier_corpus.json"
CLASSES = ["empty", "partial", "wrong", "correct"]


def _extract_retry_delay(exc: Exception) -> float | None:
    """Pull the server-suggested backoff (seconds) out of a Gemini 429, if present."""

    details = getattr(exc, "details", None)
    blob = json.dumps(details) if isinstance(details, (dict, list)) else str(exc)
    match = re.search(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"', blob)
    return float(match.group(1)) if match else None


def patch_llm_rate_limit(min_interval_s: float):
    """
    Monkeypatch llm_gateway's retry loop so real Gemini calls stay under the
    free-tier rate limit (5 req/min for gemini-3.5-flash). Only calls that miss
    the prompt-hash cache ever reach this path, so a half-finished run can be
    safely rerun: cached items replay instantly, new ones get rate-limited.
    """

    from app.core import llm_gateway

    state = {"last_call": 0.0}

    def rate_limited_retry(fn, attempts: int = 6):
        wait = min_interval_s - (time.monotonic() - state["last_call"])
        if wait > 0:
            time.sleep(wait)

        delay = 2.0

        for attempt in range(attempts):
            try:
                result = fn()
                state["last_call"] = time.monotonic()
                return result
            except llm_gateway.LLMUnavailable:
                raise
            except Exception as exc:
                state["last_call"] = time.monotonic()

                if attempt == attempts - 1:
                    raise

                backoff = _extract_retry_delay(exc) or delay
                print(f"  (LLM call failed: {exc!r}; backing off {backoff:.1f}s)")
                time.sleep(backoff)
                delay *= 2

    llm_gateway._call_with_retry = rate_limited_retry


def load_corpus() -> list[dict]:
    return json.loads(CORPUS_PATH.read_text(encoding="utf-8"))["items"]


def _template_and_concept(db, concept_id: str, probe_type: str) -> tuple[ProbeTemplate, Concept]:
    template = (
        db.query(ProbeTemplate)
        .filter_by(concept_id=concept_id, probe_type=probe_type, validated=True)
        .order_by(ProbeTemplate.id)
        .first()
    )

    if template is None:
        raise ValueError(f"No validated probe template for ({concept_id}, {probe_type}). Is the dev DB seeded?")

    concept = db.get(Concept, concept_id)
    return template, concept


def run_item(db, verifier: Verifier, item: dict) -> dict:
    template, concept = _template_and_concept(db, item["concept_id"], item["probe_type"])

    assessment, _ = assess_answer(
        question=template.question,
        answer=item["answer"],
        spec=template.relation_spec,
        misconceptions=concept.misconceptions,
        verifier=verifier,
    )

    result = {
        **item,
        "predicted_class": assessment.answer_class,
        "correct_class": assessment.answer_class == item["expected_class"],
    }

    if "expected_false_claim" in item:
        result["predicted_false_claim"] = assessment.false_claim
        result["correct_false_claim"] = assessment.false_claim == item["expected_false_claim"]

    return result


def summarise(results: list[dict]) -> dict:
    confusion = defaultdict(lambda: defaultdict(int))  # confusion[expected][predicted]
    per_class = {c: {"tp": 0, "fp": 0, "fn": 0} for c in CLASSES}

    for r in results:
        expected, predicted = r["expected_class"], r["predicted_class"]
        confusion[expected][predicted] += 1

        if expected == predicted:
            per_class[expected]["tp"] += 1
        else:
            per_class[predicted]["fp"] += 1
            per_class[expected]["fn"] += 1

    precision_recall = {}

    for c in CLASSES:
        tp, fp, fn = per_class[c]["tp"], per_class[c]["fp"], per_class[c]["fn"]
        precision = tp / (tp + fp) if (tp + fp) else float("nan")
        recall = tp / (tp + fn) if (tp + fn) else float("nan")
        precision_recall[c] = {"precision": precision, "recall": recall, "support": tp + fn}

    overall_accuracy = sum(1 for r in results if r["correct_class"]) / len(results)

    pushback = [r for r in results if "expected_false_claim" in r]
    pushback_accuracy = (
        sum(1 for r in pushback if r["correct_false_claim"]) / len(pushback) if pushback else float("nan")
    )

    # Where it matters most: does memorised-vs-robust survive the verifier?
    # (memoriser persona should fail under mr_constraint/mr_pushback; robust should pass.)
    non_base = [r for r in results if r["probe_type"] != "base" and r["persona"] in ("robust", "memoriser")]
    non_base_accuracy = sum(1 for r in non_base if r["correct_class"]) / len(non_base) if non_base else float("nan")

    return {
        "n_items": len(results),
        "overall_accuracy": overall_accuracy,
        "pushback_false_claim_accuracy": pushback_accuracy,
        "metamorphic_probe_accuracy": non_base_accuracy,
        "per_class": precision_recall,
        "confusion": {e: dict(p) for e, p in confusion.items()},
    }


def print_report(verifier_name: str, summary: dict) -> None:
    print(f"\n=== Verifier: {verifier_name} ===")
    print(f"n = {summary['n_items']}")
    print(f"Overall answer-class accuracy:        {summary['overall_accuracy']:.3f}")
    print(f"Metamorphic-probe accuracy (R/M only): {summary['metamorphic_probe_accuracy']:.3f}")
    print(f"Pushback false-claim accuracy:         {summary['pushback_false_claim_accuracy']:.3f}")

    print(f"\n{'class':<10} {'precision':>10} {'recall':>8} {'support':>8}")
    for c in CLASSES:
        pr = summary["per_class"][c]
        print(f"{c:<10} {pr['precision']:>10.3f} {pr['recall']:>8.3f} {pr['support']:>8}")

    print("\nConfusion matrix (rows = expected, cols = predicted):")
    header = "            " + "".join(f"{c:>10}" for c in CLASSES)
    print(header)
    for expected in CLASSES:
        row = summary["confusion"].get(expected, {})
        print(f"{expected:<12}" + "".join(f"{row.get(c, 0):>10}" for c in CLASSES))


def build_verifier(name: str) -> Verifier:
    if name == "local":
        return LocalVerifier()
    if name == "llm":
        return LLMVerifier()
    if name == "fallback":
        return FallbackVerifier(LLMVerifier(), LocalVerifier())
    raise ValueError(f"Unknown verifier {name!r}")


def main():
    parser = argparse.ArgumentParser(description="Validate the MKT verifier against hand-labelled answers.")
    parser.add_argument("--verifier", choices=["local", "llm", "fallback", "both"], default="local")
    parser.add_argument("--out", type=str, default=None, help="Optional path to dump full per-item predictions as JSON.")
    parser.add_argument(
        "--sleep",
        type=float,
        default=13.0,
        help="Minimum seconds between real Gemini calls (ignored for cached items). "
        "Gemini free tier allows 5 req/min for gemini-3.5-flash; 13s pads that minimum.",
    )
    args = parser.parse_args()

    corpus = load_corpus()
    names = ["local", "llm"] if args.verifier == "both" else [args.verifier]

    if "llm" in names:
        patch_llm_rate_limit(args.sleep)

    all_results = {}

    with SessionLocal() as db:
        for name in names:
            verifier = build_verifier(name)
            results = []

            for i, item in enumerate(corpus):
                results.append(run_item(db, verifier, item))
                if name == "llm":
                    print(f"  [{i + 1}/{len(corpus)}] {item['concept_id']} / {item['probe_type']} / {item['persona']}")

            summary = summarise(results)
            print_report(name, summary)
            all_results[name] = {"summary": summary, "results": results}

    if args.out:
        Path(args.out).write_text(json.dumps(all_results, indent=2), encoding="utf-8")
        print(f"\nFull results written to {args.out}")


if __name__ == "__main__":
    main()
