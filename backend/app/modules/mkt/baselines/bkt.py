"""
Bayesian Knowledge Tracing (BKT) -- the standard 2-state latent-knowledge
model from the educational-data-mining literature (Corbett & Anderson,
1995). Self-contained: no imports from app.modules.mkt.belief or any other
MKT module, because the point of this file is an independent reference
implementation to benchmark the 4-state MKT model against, not a wrapper
around it.

State: a single scalar P(known) per concept, versus MKT's 4-way belief
vector. Observation: binary correct/incorrect, versus MKT's 6-way outcome
vocabulary. Four parameters per concept:

    p_init     P(known) before any observation
    p_transit  P(unknown -> known) between observations ("learning")
    p_slip     P(incorrect | known)   -- a known skill answered wrong
    p_guess    P(correct | unknown)   -- an unknown skill answered right

Update rule (standard BKT):
    P(L_t | correct)   = P(L_t-1)(1-p_slip) / [P(L_t-1)(1-p_slip) + (1-P(L_t-1))p_guess]
    P(L_t | incorrect) = P(L_t-1)p_slip     / [P(L_t-1)p_slip     + (1-P(L_t-1))(1-p_guess)]
    P(L_t+1)           = P(L_t | obs) + (1 - P(L_t | obs)) * p_transit

EM (Baum-Welch) parameter fitting is also implemented here: see fit_em().
"""

from dataclasses import dataclass

import numpy as np


@dataclass
class BKTParams:
    p_init: float = 0.3
    p_transit: float = 0.1
    p_slip: float = 0.1
    p_guess: float = 0.2

    def clipped(self, eps: float = 1e-4) -> "BKTParams":
        return BKTParams(
            p_init=float(np.clip(self.p_init, eps, 1 - eps)),
            p_transit=float(np.clip(self.p_transit, eps, 1 - eps)),
            p_slip=float(np.clip(self.p_slip, eps, 1 - eps)),
            p_guess=float(np.clip(self.p_guess, eps, 1 - eps)),
        )


def observe(p_know: float, correct: bool, params: BKTParams) -> float:
    """
    Bayes' rule on one observation, before the learning transition.
    """

    if correct:
        num = p_know * (1 - params.p_slip)
        den = num + (1 - p_know) * params.p_guess
    else:
        num = p_know * params.p_slip
        den = num + (1 - p_know) * (1 - params.p_guess)

    if den <= 1e-12:
        return p_know

    return num / den


def transit(p_know: float, params: BKTParams) -> float:
    """
    Learning opportunity between observations: unknown can become known,
    known never reverts (classic BKT has no forgetting term).
    """

    return p_know + (1 - p_know) * params.p_transit


def update(p_know: float, correct: bool, params: BKTParams) -> float:
    return transit(observe(p_know, correct, params), params)


def predict_correct(p_know: float, params: BKTParams) -> float:
    """P(next observation is correct), before seeing it."""

    return p_know * (1 - params.p_slip) + (1 - p_know) * params.p_guess


def entropy(p: float) -> float:
    """Shannon entropy in bits of a Bernoulli(p)."""

    p = min(max(p, 1e-12), 1 - 1e-12)
    return float(-(p * np.log2(p) + (1 - p) * np.log2(1 - p)))


def expected_information_gain(p_know: float, params: BKTParams) -> float:
    """
    EIG of asking one more question about this concept, measured on the
    pre-transition Bayes update (the estimation step) rather than the
    transition (a learning effect, not new information about the current
    state). Mirrors belief.expected_information_gain's mutual-information
    formulation for the 2-state case.
    """

    prior_h = entropy(p_know)
    p_correct = predict_correct(p_know, params)

    h_correct = entropy(observe(p_know, True, params))
    h_wrong = entropy(observe(p_know, False, params))
    expected_posterior_h = p_correct * h_correct + (1 - p_correct) * h_wrong

    return max(0.0, prior_h - expected_posterior_h)


def _hmm_matrices(params: BKTParams):
    """
    A[z, z'] = P(Z_{t+1}=z' | Z_t=z), states ordered (unknown=0, known=1).
    Classic BKT: unknown can transition to known; known is absorbing.
    """

    A = np.array(
        [
            [1 - params.p_transit, params.p_transit],
            [0.0, 1.0],
        ]
    )
    return A


def _emission(z: int, o: bool, params: BKTParams) -> float:
    if z == 0:  # unknown
        return params.p_guess if o else (1 - params.p_guess)
    return (1 - params.p_slip) if o else params.p_slip  # known


def forward_backward(obs: list[bool], params: BKTParams):
    """
    Scaled forward-backward for the 2-state BKT HMM.

    Returns (gamma, xi, scale) where gamma[t, z] = P(Z_t=z | obs, params)
    and xi[t, z, z'] = P(Z_t=z, Z_{t+1}=z' | obs, params) for t in [0, T-2].
    """

    T = len(obs)
    A = _hmm_matrices(params)
    pi = np.array([1 - params.p_init, params.p_init])
    B = np.array([[_emission(z, o, params) for o in (False, True)] for z in (0, 1)])

    alpha = np.zeros((T, 2))
    scale = np.zeros(T)

    alpha[0] = pi * B[:, int(obs[0])]
    scale[0] = max(alpha[0].sum(), 1e-300)
    alpha[0] /= scale[0]

    for t in range(1, T):
        alpha[t] = (alpha[t - 1] @ A) * B[:, int(obs[t])]
        scale[t] = max(alpha[t].sum(), 1e-300)
        alpha[t] /= scale[t]

    beta = np.zeros((T, 2))
    beta[T - 1] = 1.0

    for t in range(T - 2, -1, -1):
        beta[t] = (A @ (B[:, int(obs[t + 1])] * beta[t + 1])) / scale[t + 1]

    gamma = alpha * beta
    gamma /= gamma.sum(axis=1, keepdims=True)

    xi = np.zeros((max(T - 1, 0), 2, 2))

    for t in range(T - 1):
        joint = alpha[t][:, None] * A * (B[:, int(obs[t + 1])] * beta[t + 1])[None, :]
        xi[t] = joint / scale[t + 1]

    return gamma, xi


def fit_em(
    sequences: list[list[bool]],
    init_params: BKTParams | None = None,
    n_iter: int = 30,
    tol: float = 1e-6,
) -> BKTParams:
    """
    Baum-Welch EM for BKT's four parameters, pooling statistics across all
    given sequences (one sequence per candidate/episode for a single
    concept/skill).

    E-step: forward-backward smoothing per sequence.
    M-step: re-estimate p_init/p_transit/p_slip/p_guess from the expected
    sufficient statistics, pooled across sequences.
    """

    params = (init_params or BKTParams()).clipped()
    sequences = [s for s in sequences if len(s) > 0]

    if not sequences:
        return params

    for _ in range(n_iter):
        sum_gamma1_known = 0.0
        sum_xi_unknown_known = 0.0
        sum_gamma_unknown_not_last = 0.0
        sum_gamma_known = 0.0
        sum_gamma_known_incorrect = 0.0
        sum_gamma_unknown = 0.0
        sum_gamma_unknown_correct = 0.0

        for obs in sequences:
            gamma, xi = forward_backward(obs, params)
            sum_gamma1_known += gamma[0, 1]

            for t, o in enumerate(obs):
                sum_gamma_known += gamma[t, 1]
                sum_gamma_unknown += gamma[t, 0]

                if o:
                    sum_gamma_unknown_correct += gamma[t, 0]
                else:
                    sum_gamma_known_incorrect += gamma[t, 1]

            for t in range(len(obs) - 1):
                sum_xi_unknown_known += xi[t, 0, 1]
                sum_gamma_unknown_not_last += gamma[t, 0]

        new_params = BKTParams(
            p_init=sum_gamma1_known / len(sequences),
            p_transit=(
                sum_xi_unknown_known / sum_gamma_unknown_not_last
                if sum_gamma_unknown_not_last > 1e-9
                else params.p_transit
            ),
            p_slip=(sum_gamma_known_incorrect / sum_gamma_known if sum_gamma_known > 1e-9 else params.p_slip),
            p_guess=(
                sum_gamma_unknown_correct / sum_gamma_unknown if sum_gamma_unknown > 1e-9 else params.p_guess
            ),
        ).clipped()

        delta = max(
            abs(new_params.p_init - params.p_init),
            abs(new_params.p_transit - params.p_transit),
            abs(new_params.p_slip - params.p_slip),
            abs(new_params.p_guess - params.p_guess),
        )
        params = new_params

        if delta < tol:
            break

    return params
