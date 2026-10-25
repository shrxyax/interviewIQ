"""
Probe selection by expected information gain.

An action is (concept, probe_type, template). Its score is

    score = EIG(b_c, theta_probe) * (1 + alpha * descendants(c)) * continuity / cost(probe)

- EIG: how much this probe is expected to reduce uncertainty about c.
- descendants: concepts that depend on c; resolving c also sharpens
  their priors.
- continuity: a small bonus for staying on the concept just discussed.
- cost: relative time the probe takes.

A transformed probe is only available after the concept's base question
has been answered, because the relation is checked against that answer.

Probe pairing: immediately after a BASE probe, the next probe is a
metamorphic transformation of the same concept (relation chosen by EIG),
unless the base answer already resolved the concept. EIG chooses freely
between concepts at pair boundaries.
"""

from dataclasses import dataclass

import numpy as np

from app.modules.mkt.belief import entropy, expected_information_gain
from app.modules.mkt.states import BASE, PROBE_COST


DESCENDANT_WEIGHT = 0.1
CONTINUITY_BONUS = 1.15

# Stop asking about a concept once it is this certain (bits).
ENTROPY_THRESHOLD = 0.6

# Stop the session when no probe is expected to teach us this much (bits).
MIN_EIG = 0.02


@dataclass
class Action:
    concept_id: str
    probe_type: str
    template_id: int | None
    eig: float
    score: float


def candidate_actions(
    beliefs: dict[str, np.ndarray],
    templates: dict[str, dict[str, list[int]]],
    asked_template_ids: set[int],
    base_answered: set[str],
    theta: dict[str, np.ndarray],
    descendants: dict[str, int],
    last_concept: str | None = None,
    last_probe_type: str | None = None,
) -> list[Action]:
    """
    templates: concept_id -> probe_type -> [template ids]
    """

    actions = []

    for concept_id, by_type in templates.items():
        if concept_id not in beliefs:
            continue
        belief = beliefs[concept_id]

        # Already resolved: further questions add little.
        if concept_id in base_answered and entropy(belief) < ENTROPY_THRESHOLD:
            continue

        for probe_type, template_ids in by_type.items():
            if probe_type == BASE and concept_id in base_answered:
                continue

            if probe_type != BASE and concept_id not in base_answered:
                continue

            unused = [t for t in template_ids if t not in asked_template_ids]

            if not unused:
                continue

            eig = expected_information_gain(belief, theta[probe_type])
            weight = 1 + DESCENDANT_WEIGHT * descendants.get(concept_id, 0)
            continuity = CONTINUITY_BONUS if concept_id == last_concept else 1.0
            score = eig * weight * continuity / PROBE_COST[probe_type]

            actions.append(Action(concept_id, probe_type, unused[0], eig, score))

    actions.sort(key=lambda a: a.score, reverse=True)

    if last_probe_type == BASE and last_concept is not None:
        follow_ups = [a for a in actions if a.concept_id == last_concept and a.probe_type != BASE]

        if follow_ups and follow_ups[0].eig >= MIN_EIG:
            return follow_ups + [a for a in actions if a.concept_id != last_concept]

    return actions


def select_next(*args, force: bool = False, **kwargs) -> Action | None:
    """
    force=True ignores the MIN_EIG stopping rule (used when a session
    starts, so a candidate can always re-test a well-known concept).
    """

    actions = candidate_actions(*args, **kwargs)

    if not actions or (actions[0].eig < MIN_EIG and not force):
        return None

    return actions[0]
