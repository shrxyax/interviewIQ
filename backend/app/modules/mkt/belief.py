"""
Bayesian belief over the latent knowledge state of each concept.

A belief is a length-4 probability vector over
(absent, memorised, misconceived, robust).

Everything here is pure numpy so it can be unit-tested and reasoned
about independently of the LLM and NLI components.
"""

import numpy as np

from app.modules.mkt.states import OUTCOME_INDEX, S_A, S_M, S_R, S_X


# Prior for a concept we know nothing about.
UNIFORM_PRIOR = np.array([0.25, 0.25, 0.15, 0.35])

# How strongly prerequisite mastery shifts a concept's prior.
PARENT_INFLUENCE = 1.5

# Tempering exponent for evidence passed to prerequisites. Evidence on
# Dijkstra says something about heaps, but much less than evidence on heaps.
PROPAGATION_LAMBDA = 0.3


def normalise(belief: np.ndarray) -> np.ndarray:
    total = belief.sum()

    if total <= 0:
        return UNIFORM_PRIOR.copy()

    return belief / total


def entropy(belief: np.ndarray) -> float:
    """
    Shannon entropy in bits.
    """

    p = belief[belief > 0]
    return float(-(p * np.log2(p)).sum())


def update(belief: np.ndarray, theta: np.ndarray, outcome: str) -> np.ndarray:
    """
    Bayes' rule for one observation:
        b'(z) = b(z) * P(o | z) / sum_z' b(z') * P(o | z')
    """

    likelihood = theta[:, OUTCOME_INDEX[outcome]]
    return normalise(belief * likelihood)


def predictive(belief: np.ndarray, theta: np.ndarray) -> np.ndarray:
    """
    Predictive distribution over outcomes before asking the probe:
        P(o | b) = sum_z b(z) * P(o | z)
    """

    return belief @ theta


def expected_information_gain(belief: np.ndarray, theta: np.ndarray) -> float:
    """
    EIG = H(Z) - E_o[ H(Z | o) ], which equals the mutual information
    I(Z; O) between the latent state and the probe outcome.
    """

    prior_entropy = entropy(belief)
    p_outcome = predictive(belief, theta)
    expected_posterior_entropy = 0.0

    for o_idx, p_o in enumerate(p_outcome):
        if p_o <= 1e-12:
            continue

        posterior = normalise(belief * theta[:, o_idx])
        expected_posterior_entropy += p_o * entropy(posterior)

    return max(0.0, prior_entropy - expected_posterior_entropy)


def mastery(belief: np.ndarray) -> float:
    """
    Scalar summary used for priors, readiness and plans:
    robust knowledge counts fully, memorised knowledge half.
    """

    return float(belief[S_R] + 0.5 * belief[S_M])


def robustness_index(belief: np.ndarray) -> float | None:
    """
    RI = P(robust) / (P(robust) + P(memorised)).
    Of the probability that the candidate "knows" the concept, how much
    is robust understanding rather than memorisation?
    """

    known = belief[S_R] + belief[S_M]

    if known < 1e-9:
        return None

    return float(belief[S_R] / known)


def prior_from_parents(parent_beliefs: list[np.ndarray], base: np.ndarray = UNIFORM_PRIOR) -> np.ndarray:
    """
    Graph-informed prior for a concept that has not been observed yet.

    Each observed prerequisite multiplies the prior by
        f = [1 + k(0.5 - m), 1, 1, 1 + k(m - 0.5)]
    where m is the prerequisite's mastery. f is neutral at m = 0.5,
    shifts mass towards ROBUST for strong prerequisites and towards
    ABSENT for weak ones.
    """

    prior = base.copy()

    for parent in parent_beliefs:
        m = mastery(parent)
        factor = np.ones(4)
        factor[S_A] = 1 + PARENT_INFLUENCE * (0.5 - m)
        factor[S_R] = 1 + PARENT_INFLUENCE * (m - 0.5)
        prior = prior * np.clip(factor, 0.05, None)

    return normalise(prior)


def propagate_to_parent(parent_belief: np.ndarray, theta: np.ndarray, outcome: str, lam: float = PROPAGATION_LAMBDA) -> np.ndarray:
    """
    Pass tempered evidence from a concept to one of its prerequisites.

    The likelihood is raised to the power lambda (< 1) so it counts as weak
    evidence. The MISCONCEIVED component is neutralised, because a
    misconception about Dijkstra is not evidence of a misconception about
    heaps, only of weaker mastery.

    This is a one-hop approximation to belief propagation in a Bayesian
    network over the concept graph.
    """

    likelihood = theta[:, OUTCOME_INDEX[outcome]] ** lam
    likelihood = likelihood.copy()

    others = [S_A, S_M, S_R]
    likelihood[S_X] = float(np.exp(np.log(likelihood[others]).mean()))

    return normalise(parent_belief * likelihood)


def decay(belief: np.ndarray, days_elapsed: float, half_life_days: float = 21.0, prior: np.ndarray = UNIFORM_PRIOR) -> np.ndarray:
    """
    Forgetting between sessions: move the belief towards the prior with
        delta = 1 - 2^(-days / half_life)
    """

    if days_elapsed <= 0:
        return belief

    delta = 1 - 2 ** (-days_elapsed / half_life_days)
    return normalise((1 - delta) * belief + delta * prior)
