"""
Offline evaluation with simulated candidates.

Each simulated candidate has a hidden true state for every concept.
When asked a probe, it produces an outcome sampled from
P(outcome | true state, probe type). The engine never sees the true
state; we compare its final beliefs with the truth.

This answers, cheaply and repeatably:
- Does EIG selection identify states faster than random or fixed-order questioning?
- Do metamorphic probes matter? (ablation: base questions only)

Run:  python -m app.modules.mkt.simulate
"""

import argparse
from dataclasses import dataclass, field

import numpy as np

from app.modules.mkt.belief import UNIFORM_PRIOR, update
from app.modules.mkt.emissions import DEFAULT_THETA
from app.modules.mkt.selection import Action, candidate_actions
from app.modules.mkt.states import BASE, OUTCOMES, PROBE_TYPES, STATES


POLICIES = ["eig", "random", "fixed_order", "base_only"]


@dataclass
class SimResult:
    accuracy: float           # MAP state == true state
    brier: float              # mean squared error of belief vs one-hot truth
    mem_vs_robust_acc: float  # accuracy restricted to concepts truly M or R
    turns: int
    per_concept: list = field(default_factory=list)


def _build_templates(concepts: list[str], probe_types: list[str]) -> dict[str, dict[str, list[int]]]:
    templates, next_id = {}, 0

    for c in concepts:
        templates[c] = {}

        for p in probe_types:
            templates[c][p] = [next_id]
            next_id += 1

    return templates


def run_episode(
    true_states: dict[str, int],
    policy: str,
    budget: int,
    rng: np.random.Generator,
    theta_engine=None,
    theta_world=None,
) -> SimResult:
    """
    theta_engine: emission model the engine believes.
    theta_world:  emission model the simulated candidate actually follows.
    Using different tables tests robustness to model misspecification.
    """

    theta_engine = theta_engine or DEFAULT_THETA
    theta_world = theta_world or DEFAULT_THETA

    concepts = list(true_states)
    probe_types = [BASE] if policy == "base_only" else PROBE_TYPES
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
            theta_engine,
            descendants={},
            last_concept=last_concept,
            last_probe_type=last_probe_type,
        )

        if not actions:
            break

        if policy in ("eig", "base_only"):
            action = actions[0]
        elif policy == "random":
            action = actions[rng.integers(len(actions))]
        else:  # fixed_order: the next legal (concept, probe) in a fixed script
            legal = {(a.concept_id, a.probe_type): a for a in actions}
            action: Action | None = None

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

        beliefs[action.concept_id] = update(
            beliefs[action.concept_id],
            theta_engine[action.probe_type],
            outcome,
        )

        asked.add(action.template_id)

        if action.probe_type == BASE:
            base_answered.add(action.concept_id)

        last_concept, last_probe_type = action.concept_id, action.probe_type
        turns += 1

    correct, brier, mr_total, mr_correct = 0, 0.0, 0, 0
    per_concept = []

    for c in concepts:
        z = true_states[c]
        b = beliefs[c]
        guess = int(np.argmax(b))
        one_hot = np.eye(len(STATES))[z]

        correct += guess == z
        brier += float(((b - one_hot) ** 2).sum())

        if z in (1, 3):  # memorised or robust
            mr_total += 1
            mr_correct += guess == z

        per_concept.append((c, STATES[z], STATES[guess], round(float(b[z]), 3)))

    n = len(concepts)

    return SimResult(
        accuracy=correct / n,
        brier=brier / n,
        mem_vs_robust_acc=(mr_correct / mr_total) if mr_total else float("nan"),
        turns=turns,
        per_concept=per_concept,
    )


def sample_candidate(n_concepts: int, rng: np.random.Generator) -> dict[str, int]:
    # Hidden states drawn from a plausible student population.
    population = np.array([0.20, 0.30, 0.15, 0.35])
    return {f"c{i}": int(rng.choice(4, p=population)) for i in range(n_concepts)}


def benchmark(n_candidates: int = 500, n_concepts: int = 8, budget: int = 20, seed: int = 0) -> dict[str, dict[str, float]]:
    results = {}

    for policy in POLICIES:
        rng = np.random.default_rng(seed)
        runs = [
            run_episode(sample_candidate(n_concepts, rng), policy, budget, rng)
            for _ in range(n_candidates)
        ]

        results[policy] = {
            "accuracy": float(np.mean([r.accuracy for r in runs])),
            "brier": float(np.mean([r.brier for r in runs])),
            "mem_vs_robust_acc": float(np.nanmean([r.mem_vs_robust_acc for r in runs])),
            "turns": float(np.mean([r.turns for r in runs])),
        }

    return results


def main():
    parser = argparse.ArgumentParser(description="MKT simulated-candidate benchmark")
    parser.add_argument("--candidates", type=int, default=500)
    parser.add_argument("--concepts", type=int, default=8)
    parser.add_argument("--budget", type=int, default=20)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    results = benchmark(args.candidates, args.concepts, args.budget, args.seed)

    print(f"{args.candidates} simulated candidates, {args.concepts} concepts, budget {args.budget} probes\n")
    print(f"{'policy':<12} {'state acc':>10} {'M-vs-R acc':>11} {'brier':>8} {'turns':>7}")

    for policy, r in results.items():
        print(f"{policy:<12} {r['accuracy']:>10.3f} {r['mem_vs_robust_acc']:>11.3f} {r['brier']:>8.3f} {r['turns']:>7.1f}")


if __name__ == "__main__":
    main()
