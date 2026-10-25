"""
Emission model: theta[probe_type][state, outcome] = P(outcome | state, probe_type).

These are expert-initialised values. They encode the central hypothesis
of the project:

- BASE probes barely separate MEMORISED from ROBUST (both answer the
  canonical question correctly).
- MR_CONSTRAINT and MR_INVERSION separate them sharply (memorised
  knowledge does not adapt to a changed problem).
- MR_PUSHBACK separates ROBUST (holds) from everything else (capitulates).

Once real session data exists, these tables are re-estimated with EM.
Rows are states (absent, memorised, misconceived, robust); columns follow
states.OUTCOMES:
  consistent_correct, partial, inconsistent, consistent_wrong, empty, capitulated
"""

import numpy as np

from app.modules.mkt.states import (
    BASE,
    MR_CONSTRAINT,
    MR_INVERSION,
    MR_PARAPHRASE,
    MR_PUSHBACK,
    MR_TRANSFER,
    OUTCOMES,
    STATES,
)


DEFAULT_THETA_RAW = {
    BASE: [
        [0.05, 0.20, 0.00, 0.15, 0.60, 0.00],  # absent
        [0.75, 0.20, 0.00, 0.03, 0.02, 0.00],  # memorised
        [0.10, 0.15, 0.00, 0.70, 0.05, 0.00],  # misconceived
        [0.80, 0.17, 0.00, 0.02, 0.01, 0.00],  # robust
    ],
    MR_PARAPHRASE: [
        [0.03, 0.15, 0.15, 0.12, 0.55, 0.00],
        [0.50, 0.20, 0.25, 0.03, 0.02, 0.00],
        [0.05, 0.10, 0.10, 0.70, 0.05, 0.00],
        [0.80, 0.14, 0.04, 0.01, 0.01, 0.00],
    ],
    MR_CONSTRAINT: [
        [0.03, 0.12, 0.20, 0.15, 0.50, 0.00],
        [0.10, 0.15, 0.65, 0.05, 0.05, 0.00],
        [0.05, 0.10, 0.15, 0.65, 0.05, 0.00],
        [0.78, 0.15, 0.05, 0.01, 0.01, 0.00],
    ],
    MR_INVERSION: [
        [0.03, 0.12, 0.20, 0.10, 0.55, 0.00],
        [0.25, 0.20, 0.45, 0.05, 0.05, 0.00],
        [0.05, 0.10, 0.15, 0.65, 0.05, 0.00],
        [0.75, 0.17, 0.06, 0.01, 0.01, 0.00],
    ],
    MR_PUSHBACK: [
        [0.05, 0.20, 0.05, 0.05, 0.15, 0.50],
        [0.25, 0.20, 0.05, 0.05, 0.02, 0.43],
        [0.05, 0.10, 0.05, 0.30, 0.05, 0.45],
        [0.80, 0.12, 0.02, 0.01, 0.01, 0.04],
    ],
    # Transfer asks the candidate to apply the concept to an unseen,
    # structurally analogous context. Like MR_CONSTRAINT/MR_INVERSION,
    # memorised knowledge (the canned explanation) does not carry over.
    MR_TRANSFER: [
        [0.03, 0.12, 0.20, 0.15, 0.50, 0.00],
        [0.08, 0.15, 0.68, 0.04, 0.05, 0.00],
        [0.05, 0.10, 0.15, 0.65, 0.05, 0.00],
        [0.78, 0.15, 0.05, 0.01, 0.01, 0.00],
    ],
}

# Noise floor: every outcome is possible in every state because the
# extractor, the NLI model and the candidate's phrasing are all noisy.
EPSILON = 0.03


def build_theta(raw=None, epsilon: float = EPSILON) -> dict[str, np.ndarray]:
    """
    Normalise rows and mix with a uniform distribution:
        theta = (1 - eps) * theta_raw + eps / |O|
    """

    raw = raw or DEFAULT_THETA_RAW
    theta = {}

    for probe_type, rows in raw.items():
        matrix = np.asarray(rows, dtype=float)

        if matrix.shape != (len(STATES), len(OUTCOMES)):
            raise ValueError(f"Emission table for {probe_type} has shape {matrix.shape}")

        matrix = matrix / matrix.sum(axis=1, keepdims=True)
        theta[probe_type] = (1 - epsilon) * matrix + epsilon / len(OUTCOMES)

    return theta


DEFAULT_THETA = build_theta()
