from app.modules.mkt.simulate import benchmark


def test_eig_selection_beats_baselines_and_metamorphic_probes_matter():
    r = benchmark(n_candidates=200, n_concepts=8, budget=20, seed=1)

    # Information-gain selection identifies states better than random or a fixed script.
    assert r["eig"]["accuracy"] > r["random"]["accuracy"]
    assert r["eig"]["accuracy"] > r["fixed_order"]["accuracy"]

    # Without metamorphic probes, memorised vs robust is near chance.
    assert r["base_only"]["mem_vs_robust_acc"] < 0.6
    assert r["eig"]["mem_vs_robust_acc"] > r["base_only"]["mem_vs_robust_acc"] + 0.2
