import numpy as np
import pytest

from app.modules.mkt.baselines.bkt import BKTParams, entropy, fit_em, observe, transit, update


def test_observe_bounds_and_direction():
    params = BKTParams(p_init=0.3, p_transit=0.1, p_slip=0.1, p_guess=0.2)

    for p_know in (0.05, 0.3, 0.5, 0.7, 0.95):
        p_correct = observe(p_know, True, params)
        p_wrong = observe(p_know, False, params)

        assert 0.0 <= p_correct <= 1.0
        assert 0.0 <= p_wrong <= 1.0
        # A correct answer should raise belief in "known"; an incorrect
        # answer should lower it, relative to the prior.
        assert p_correct >= p_know
        assert p_wrong <= p_know


def test_transit_only_moves_toward_known():
    params = BKTParams(p_transit=0.2)

    for p_know in (0.0, 0.3, 0.7, 1.0):
        assert transit(p_know, params) >= p_know


def test_update_bounded():
    params = BKTParams()
    rng = np.random.default_rng(0)

    p_know = 0.3
    for _ in range(50):
        p_know = update(p_know, bool(rng.random() < 0.5), params)
        assert 0.0 <= p_know <= 1.0


def test_update_hand_computed_single_step():
    # p_know=0.3, p_slip=0.1, p_guess=0.2, p_transit=0.1, observe correct.
    params = BKTParams(p_init=0.3, p_transit=0.1, p_slip=0.1, p_guess=0.2)

    num = 0.3 * 0.9  # p_know * (1 - p_slip)
    den = num + 0.7 * 0.2  # + (1 - p_know) * p_guess
    expected_posterior = num / den
    expected_after_transit = expected_posterior + (1 - expected_posterior) * 0.1

    assert observe(0.3, True, params) == pytest.approx(expected_posterior, abs=1e-9)
    assert update(0.3, True, params) == pytest.approx(expected_after_transit, abs=1e-9)


def test_entropy_bounds():
    assert entropy(0.5) == pytest.approx(1.0, abs=1e-9)
    assert entropy(0.0) == pytest.approx(0.0, abs=1e-6)
    assert entropy(1.0) == pytest.approx(0.0, abs=1e-6)


def test_em_recovers_known_parameters_on_synthetic_data():
    true_params = BKTParams(p_init=0.25, p_transit=0.15, p_slip=0.1, p_guess=0.2)
    rng = np.random.default_rng(7)

    sequences = []
    for _ in range(300):
        known = rng.random() < true_params.p_init
        seq = []
        for _ in range(12):
            p_correct = (1 - true_params.p_slip) if known else true_params.p_guess
            seq.append(bool(rng.random() < p_correct))
            if not known and rng.random() < true_params.p_transit:
                known = True
        sequences.append(seq)

    fitted = fit_em(sequences, n_iter=50)

    assert abs(fitted.p_init - true_params.p_init) < 0.07
    assert abs(fitted.p_transit - true_params.p_transit) < 0.07
    assert abs(fitted.p_slip - true_params.p_slip) < 0.05
    assert abs(fitted.p_guess - true_params.p_guess) < 0.05


def test_em_is_well_defined_on_degenerate_sequences():
    # All-correct and all-incorrect sequences should not raise or produce
    # out-of-range parameters (division-by-near-zero guards in fit_em).
    sequences = [[True] * 10, [False] * 10, []]
    fitted = fit_em(sequences, n_iter=10)

    for value in (fitted.p_init, fitted.p_transit, fitted.p_slip, fitted.p_guess):
        assert 0.0 <= value <= 1.0
