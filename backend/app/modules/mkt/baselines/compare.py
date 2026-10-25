"""
Head-to-head comparison: BKT (2-state literature baseline) vs the real MKT
engine (4-state belief + metamorphic probes), on the same simulated
population app.modules.mkt.simulate already uses.

Comparison design (task 1 of the phase brief; see results/README.md for the
full discussion): **same selection procedure, different state model**
(design (a) in the brief), held as primary. Both models greedily pick the
action expected to reduce entropy the most:

- MKT picks (concept, probe_type) from its full repertoire -- base question
  plus four metamorphic relations -- via the real, unmodified
  app.modules.mkt.selection.candidate_actions, and updates a 4-state belief
  via the real, unmodified app.modules.mkt.belief.update.
- BKT has no notion of a metamorphic relation at all -- that is its
  structural limitation, not an implementation gap -- so it only ever
  re-asks the equivalent of the base question for whichever concept it
  picks, using its own EIG over a 2-state belief (bkt.expected_information_gain)
  and its own update rule (bkt.update).

Both runs share one hidden ground-truth population per candidate (the same
4-state truth app.modules.mkt.simulate.sample_candidate draws) and observe
outcomes sampled from the same world model, app.modules.mkt.emissions.
DEFAULT_THETA: MKT sees the native 6-way outcome for whichever probe_type it
asked; BKT sees a binarised correct/incorrect projection of the BASE row,
since a repeated "base question" is the only action in its vocabulary.

A secondary design (b), "full pipeline vs full pipeline", is also run:
MKT's EIG policy vs BKT's classic fixed-order administration (round-robin
over concepts, no adaptive selection at all).

Run:  python -m app.modules.mkt.baselines.compare
"""

import argparse
from dataclasses import dataclass, field

import numpy as np

from app.modules.mkt.baselines.bkt import (
    BKTParams,
    entropy as bkt_entropy,
    expected_information_gain as bkt_eig,
    update as bkt_update,
)
from app.modules.mkt.belief import UNIFORM_PRIOR, update as mkt_update
from app.modules.mkt.emissions import DEFAULT_THETA
from app.modules.mkt.selection import candidate_actions
from app.modules.mkt.simulate import sample_candidate
from app.modules.mkt.states import BASE, CONSISTENT_CORRECT, OUTCOMES, PROBE_TYPES, S_M, S_R, STATES


# BKT has only one state bit of uncertainty (max entropy 1 bit, vs MKT's 2
# bits over 4 states), so its stopping thresholds are scaled down to match.
BKT_ENTROPY_THRESHOLD = 0.3
BKT_MIN_EIG = 0.01

DEFAULT_BKT_PARAMS = BKTParams(p_init=0.3, p_transit=0.1, p_slip=0.1, p_guess=0.2)


def collapse_to_known(z: int) -> int:
    """
    BKT's 2-state truth label: MEMORISED and ROBUST both count as "known",
    ABSENT and MISCONCEIVED both count as "unknown". This collapse is BKT's
    structural limitation -- it cannot represent misconception as distinct
    from not knowing, or memorisation as distinct from robust understanding
    -- not an artifact of this harness.
    """

    return 1 if z in (S_M, S_R) else 0


def _build_templates(concepts: list[str], probe_types: list[str]) -> dict[str, dict[str, list[int]]]:
    templates, next_id = {}, 0

    for c in concepts:
        templates[c] = {}
        for p in probe_types:
            templates[c][p] = [next_id]
            next_id += 1

    return templates


@dataclass
class MKTEpisode:
    beliefs: dict
    turns: int


def run_episode_mkt(
    true_states: dict[str, int],
    policy: str,
    budget: int,
    rng: np.random.Generator,
    theta_world: dict | None = None,
) -> MKTEpisode:
    """
    A thin re-implementation of simulate.run_episode that also returns the
    final belief vectors (needed for calibration here; simulate.SimResult
    only returns summary scalars). Uses the same, unmodified selection.py
    and belief.py primitives simulate.py uses -- not a reimplementation of
    the engine, just a different return shape.
    """

    theta_world = theta_world or DEFAULT_THETA
    concepts = list(true_states)
    probe_types = PROBE_TYPES
    templates = _build_templates(concepts, probe_types)

    beliefs = {c: UNIFORM_PRIOR.copy() for c in concepts}
    asked: set[int] = set()
    base_answered: set[str] = set()
    last_concept, last_probe_type = None, None
    fixed_queue = [(c, p) for c in concepts for p in probe_types]
    turns = 0

    for _ in range(budget):
        actions = candidate_actions(
            beliefs,
            templates,
            asked,
            base_answered,
            DEFAULT_THETA,
            descendants={},
            last_concept=last_concept,
            last_probe_type=last_probe_type,
        )

        if not actions:
            break

        if policy == "eig":
            action = actions[0]
        else:  # fixed_order
            legal = {(a.concept_id, a.probe_type): a for a in actions}
            action = None

            while fixed_queue:
                key = fixed_queue.pop(0)
                if key in legal:
                    action = legal[key]
                    break

            if action is None:
                break

        z = true_states[action.concept_id]
        o_idx = rng.choice(len(OUTCOMES), p=theta_world[action.probe_type][z])
        outcome = OUTCOMES[o_idx]

        beliefs[action.concept_id] = mkt_update(beliefs[action.concept_id], DEFAULT_THETA[action.probe_type], outcome)
        asked.add(action.template_id)

        if action.probe_type == BASE:
            base_answered.add(action.concept_id)

        last_concept, last_probe_type = action.concept_id, action.probe_type
        turns += 1

    return MKTEpisode(beliefs=beliefs, turns=turns)


@dataclass
class BKTEpisode:
    p_know: dict
    turns: int


def run_episode_bkt(
    true_states: dict[str, int],
    policy: str,
    budget: int,
    rng: np.random.Generator,
    params: BKTParams = DEFAULT_BKT_PARAMS,
    theta_world: dict | None = None,
) -> BKTEpisode:
    theta_world = theta_world or DEFAULT_THETA
    concepts = list(true_states)
    p_know = {c: params.p_init for c in concepts}
    attempts = {c: 0 for c in concepts}
    turns = 0

    for _ in range(budget):
        candidates = [c for c in concepts if bkt_entropy(p_know[c]) >= BKT_ENTROPY_THRESHOLD]

        if not candidates:
            break

        if policy == "eig":
            scored = sorted(((c, bkt_eig(p_know[c], params)) for c in candidates), key=lambda x: x[1], reverse=True)
            concept, eig = scored[0]

            if eig < BKT_MIN_EIG:
                break
        else:  # fixed_order: round-robin, fewest attempts first, ties by concept order
            concept = min(candidates, key=lambda c: (attempts[c], concepts.index(c)))

        z = true_states[concept]
        o_idx = rng.choice(len(OUTCOMES), p=theta_world[BASE][z])
        correct = OUTCOMES[o_idx] == CONSISTENT_CORRECT

        p_know[concept] = bkt_update(p_know[concept], correct, params)
        attempts[concept] += 1
        turns += 1

    return BKTEpisode(p_know=p_know, turns=turns)


@dataclass
class ModelResult:
    accuracy_2state: float
    brier: float
    turns: float
    calibration: list = field(default_factory=list)


def _calibration_bins(preds: list[float], truths: list[int], n_bins: int = 10) -> list[dict]:
    edges = np.linspace(0, 1, n_bins + 1)
    bins = []

    for lo, hi in zip(edges[:-1], edges[1:]):
        idx = [i for i, p in enumerate(preds) if (p >= lo and (p < hi or hi >= 1.0 - 1e-9))]

        if not idx:
            continue

        bins.append(
            {
                "range": (float(lo), float(hi)),
                "n": len(idx),
                "predicted": float(np.mean([preds[i] for i in idx])),
                "empirical": float(np.mean([truths[i] for i in idx])),
            }
        )

    return bins


def run_comparison(
    n_candidates: int = 500,
    n_concepts: int = 8,
    budget: int = 20,
    seed: int = 0,
    bkt_params: BKTParams = DEFAULT_BKT_PARAMS,
) -> dict[str, ModelResult]:
    results: dict[str, ModelResult] = {}

    runs = {
        "mkt_eig": ("mkt", "eig"),
        "mkt_fixed_order": ("mkt", "fixed_order"),
        "bkt_eig": ("bkt", "eig"),
        "bkt_fixed_order": ("bkt", "fixed_order"),
    }

    for name, (model, policy) in runs.items():
        rng = np.random.default_rng(seed)
        preds, truths, correct_count, turn_counts = [], [], 0, []

        for _ in range(n_candidates):
            true_states = sample_candidate(n_concepts, rng)

            if model == "mkt":
                ep = run_episode_mkt(true_states, policy, budget, rng)
                for c, z in true_states.items():
                    b = ep.beliefs[c]
                    p_known = float(b[S_R] + b[S_M])
                    truth = collapse_to_known(z)
                    preds.append(p_known)
                    truths.append(truth)
                    correct_count += int(p_known >= 0.5) == truth
                turn_counts.append(ep.turns)
            else:
                ep = run_episode_bkt(true_states, policy, budget, rng, bkt_params)
                for c, z in true_states.items():
                    p_known = ep.p_know[c]
                    truth = collapse_to_known(z)
                    preds.append(p_known)
                    truths.append(truth)
                    correct_count += int(p_known >= 0.5) == truth
                turn_counts.append(ep.turns)

        n = len(preds)
        brier = float(np.mean([(p - t) ** 2 for p, t in zip(preds, truths)]))

        results[name] = ModelResult(
            accuracy_2state=correct_count / n,
            brier=brier,
            turns=float(np.mean(turn_counts)),
            calibration=_calibration_bins(preds, truths),
        )

    return results


def em_sanity_check(n_sequences: int = 200, seq_len: int = 12, seed: int = 0) -> dict:
    """
    Fit EM on synthetic data generated from known BKT parameters and report
    how close the recovered parameters are. Used both as a standalone sanity
    check (task 3) and surfaced in the comparison report.
    """

    from app.modules.mkt.baselines.bkt import BKTParams, fit_em, observe, transit

    true_params = BKTParams(p_init=0.25, p_transit=0.15, p_slip=0.1, p_guess=0.2)
    rng = np.random.default_rng(seed)

    sequences = []
    for _ in range(n_sequences):
        known = rng.random() < true_params.p_init
        seq = []
        for _ in range(seq_len):
            p_correct = (1 - true_params.p_slip) if known else true_params.p_guess
            correct = rng.random() < p_correct
            seq.append(bool(correct))
            if not known and rng.random() < true_params.p_transit:
                known = True
        sequences.append(seq)

    fitted = fit_em(sequences, n_iter=50)

    return {
        "true": true_params,
        "fitted": fitted,
        "abs_error": {
            "p_init": abs(fitted.p_init - true_params.p_init),
            "p_transit": abs(fitted.p_transit - true_params.p_transit),
            "p_slip": abs(fitted.p_slip - true_params.p_slip),
            "p_guess": abs(fitted.p_guess - true_params.p_guess),
        },
    }


def print_report(results: dict[str, ModelResult], em_check: dict) -> None:
    print("=== EM convergence sanity check (synthetic data, known ground-truth params) ===")
    t, f = em_check["true"], em_check["fitted"]
    print(f"{'param':<12} {'true':>8} {'fitted':>8} {'abs err':>8}")
    for name in ("p_init", "p_transit", "p_slip", "p_guess"):
        print(f"{name:<12} {getattr(t, name):>8.3f} {getattr(f, name):>8.3f} {em_check['abs_error'][name]:>8.3f}")

    print("\n=== BKT vs MKT, same simulated population ===")
    print(f"{'run':<16} {'2-state acc':>12} {'brier':>8} {'turns':>7}")
    for name, r in results.items():
        print(f"{name:<16} {r.accuracy_2state:>12.3f} {r.brier:>8.3f} {r.turns:>7.1f}")


def main():
    parser = argparse.ArgumentParser(description="BKT vs MKT comparison")
    parser.add_argument("--candidates", type=int, default=500)
    parser.add_argument("--concepts", type=int, default=8)
    parser.add_argument("--budget", type=int, default=20)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    em_check = em_sanity_check()
    results = run_comparison(args.candidates, args.concepts, args.budget, args.seed)
    print_report(results, em_check)


if __name__ == "__main__":
    main()
