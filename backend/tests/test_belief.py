import numpy as np
import pytest

from app.modules.mkt import belief as B
from app.modules.mkt.emissions import DEFAULT_THETA
from app.modules.mkt.states import (
    BASE,
    CAPITULATED,
    CONSISTENT_CORRECT,
    INCONSISTENT,
    MR_CONSTRAINT,
    MR_PUSHBACK,
    S_A,
    S_M,
    S_R,
    S_X,
)


def test_emission_rows_are_distributions():
    for theta in DEFAULT_THETA.values():
        assert np.allclose(theta.sum(axis=1), 1.0)
        assert (theta > 0).all()  # epsilon floor: no outcome is impossible


def test_update_is_normalised_and_moves_towards_evidence():
    b = B.UNIFORM_PRIOR.copy()
    after = B.update(b, DEFAULT_THETA[MR_CONSTRAINT], INCONSISTENT)

    assert after.sum() == pytest.approx(1.0)
    assert after[S_M] > b[S_M]  # inconsistency under a changed constraint signals memorisation
    assert after[S_R] < b[S_R]


def test_entropy_bounds():
    assert B.entropy(np.full(4, 0.25)) == pytest.approx(2.0)
    assert B.entropy(np.array([1.0, 0, 0, 0])) == pytest.approx(0.0)


def test_eig_is_mutual_information_and_non_negative():
    for theta in DEFAULT_THETA.values():
        assert B.expected_information_gain(B.UNIFORM_PRIOR, theta) >= 0

    certain = np.array([0.0, 0.0, 0.0, 1.0])
    assert B.expected_information_gain(certain, DEFAULT_THETA[BASE]) == pytest.approx(0.0, abs=1e-9)


def test_constraint_probe_beats_base_probe_when_memorised_vs_robust_is_unclear():
    """
    The core hypothesis encoded in the model: once a candidate has answered
    the canonical question correctly, a base question cannot tell memorised
    from robust, but a metamorphic constraint change can.
    """

    split = np.array([0.02, 0.48, 0.02, 0.48])

    eig_base = B.expected_information_gain(split, DEFAULT_THETA[BASE])
    eig_constraint = B.expected_information_gain(split, DEFAULT_THETA[MR_CONSTRAINT])

    assert eig_constraint > 3 * eig_base


def test_pushback_capitulation_lowers_robustness():
    b = np.array([0.05, 0.3, 0.05, 0.6])
    held = B.update(b, DEFAULT_THETA[MR_PUSHBACK], CONSISTENT_CORRECT)
    caved = B.update(b, DEFAULT_THETA[MR_PUSHBACK], CAPITULATED)

    assert B.robustness_index(held) > B.robustness_index(b) > B.robustness_index(caved)


def test_robustness_index():
    assert B.robustness_index(np.array([0.1, 0.0, 0.1, 0.8])) == pytest.approx(1.0)
    assert B.robustness_index(np.array([0.1, 0.8, 0.1, 0.0])) == pytest.approx(0.0)
    assert B.robustness_index(np.array([1.0, 0.0, 0.0, 0.0])) is None


def test_prior_from_parents():
    strong = np.array([0.0, 0.0, 0.0, 1.0])
    weak = np.array([1.0, 0.0, 0.0, 0.0])

    assert np.allclose(B.prior_from_parents([]), B.UNIFORM_PRIOR)
    assert B.prior_from_parents([strong])[S_R] > B.UNIFORM_PRIOR[S_R]
    assert B.prior_from_parents([weak])[S_A] > B.UNIFORM_PRIOR[S_A]


def test_propagation_is_weaker_than_direct_evidence_and_ignores_misconception():
    b = B.UNIFORM_PRIOR.copy()
    theta = DEFAULT_THETA[MR_CONSTRAINT]

    direct = B.update(b, theta, INCONSISTENT)
    propagated = B.propagate_to_parent(b, theta, INCONSISTENT)

    assert abs(propagated - b).sum() < abs(direct - b).sum()
    # The misconceived component moves only through renormalisation.
    ratio = propagated / b
    assert ratio[S_X] == pytest.approx(np.exp(np.log(ratio[[S_A, S_M, S_R]]).mean()), rel=1e-6)


def test_decay_moves_towards_prior():
    b = np.array([0.0, 0.0, 0.0, 1.0])

    assert np.allclose(B.decay(b, 0), b)
    assert B.decay(b, 21)[S_R] == pytest.approx(0.5 * 1.0 + 0.5 * B.UNIFORM_PRIOR[S_R])
    assert B.decay(b, 365)[S_R] < B.decay(b, 21)[S_R]
