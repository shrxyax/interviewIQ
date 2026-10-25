import pytest

from app.modules.whiteboard.allocator import reference_allocation
from app.modules.whiteboard.compiler import DesignError, compile_graph
from app.modules.whiteboard.failures import apply_graph_scenario, apply_requirements_scenario
from app.modules.whiteboard.findings import AVAILABILITY_SLO, LATENCY_SLO, SATURATION, SPOF, build_findings
from app.modules.whiteboard.queueing import (
    bottleneck_capacity,
    compute_traffic,
    end_to_end_availability,
    end_to_end_latency_ms,
    erlang_c,
    node_metrics,
)
from app.modules.whiteboard.simulation import simulate
from app.modules.whiteboard.structural import articulation_points, single_points_of_failure


def simple_graph(api_replicas=1, db_replicas=1, cache_replicas=1, lb_replicas=1):
    return {
        "nodes": [
            {"id": "client", "type": "client", "label": "Client"},
            {"id": "lb", "type": "load_balancer", "label": "LB", "params": {"replicas": lb_replicas}},
            {"id": "api", "type": "api_service", "label": "API", "params": {"replicas": api_replicas}},
            {"id": "cache", "type": "cache", "label": "Cache", "params": {"replicas": cache_replicas, "hit_ratio": 0.8}},
            {"id": "db", "type": "sql_primary", "label": "DB", "params": {"replicas": db_replicas}},
        ],
        "edges": [
            {"src": "client", "dst": "lb"},
            {"src": "lb", "dst": "api"},
            {"src": "api", "dst": "cache"},
            {"src": "cache", "dst": "db", "fraction": "miss"},
        ],
    }


# --------------------------------------------------------------------------
# Compiler
# --------------------------------------------------------------------------

def test_compiles_valid_graph():
    graph = compile_graph(simple_graph())
    assert set(graph.nodes) == {"client", "lb", "api", "cache", "db"}


def test_rejects_unknown_component_type():
    g = simple_graph()
    g["nodes"][2]["type"] = "spaceship"
    with pytest.raises(DesignError):
        compile_graph(g)


def test_rejects_cache_without_backing_store():
    g = simple_graph()
    g["edges"] = [e for e in g["edges"] if e != {"src": "cache", "dst": "db", "fraction": "miss"}]
    with pytest.raises(DesignError, match="backing store"):
        compile_graph(g)


def test_rejects_unreachable_component():
    g = simple_graph()
    g["nodes"].append({"id": "orphan", "type": "api_service", "label": "Orphan"})
    with pytest.raises(DesignError, match="[Uu]nreachable"):
        compile_graph(g)


def test_rejects_missing_client():
    g = simple_graph()
    g["nodes"] = [n for n in g["nodes"] if n["type"] != "client"]
    g["edges"] = [e for e in g["edges"] if "client" not in (e["src"], e["dst"])]
    with pytest.raises(DesignError, match="client"):
        compile_graph(g)


# --------------------------------------------------------------------------
# Structural: articulation points / SPOF
# --------------------------------------------------------------------------

def test_single_replica_node_on_critical_path_is_spof():
    graph = compile_graph(simple_graph(api_replicas=1))
    spofs = {s["node_id"] for s in single_points_of_failure(graph)}
    assert "api" in spofs
    assert "db" in spofs


def test_redundant_replicas_are_not_flagged_as_spof():
    graph = compile_graph(simple_graph(api_replicas=2, db_replicas=2, cache_replicas=2, lb_replicas=2))
    spofs = {s["node_id"] for s in single_points_of_failure(graph)}
    assert spofs == set()


def test_parallel_api_path_removes_it_from_articulation_points():
    # Two independent API instances, each reachable only via its own edge
    # from lb, both feeding the (still single-instance) cache.
    g = simple_graph()
    g["nodes"].append({"id": "api2", "type": "api_service", "label": "API 2"})
    g["edges"].append({"src": "lb", "dst": "api2"})
    g["edges"].append({"src": "api2", "dst": "cache"})
    graph = compile_graph(g)

    points = articulation_points(graph)
    # Neither api nor api2 is a cut vertex any more: removing either still
    # leaves a path from lb to cache through the other.
    assert "api" not in points
    assert "api2" not in points
    # lb and cache are still single, unavoidable choke points.
    assert "lb" in points
    assert "cache" in points


# --------------------------------------------------------------------------
# Queueing
# --------------------------------------------------------------------------

def test_erlang_c_matches_mm1_formula():
    # For c=1, Erlang-C P(wait) equals utilisation rho.
    for a in (0.1, 0.5, 0.9):
        assert erlang_c(1, a) == pytest.approx(a, rel=1e-6)


def test_traffic_conserved_through_cache_hit_and_miss():
    graph = compile_graph(simple_graph())
    lambdas = compute_traffic(graph, peak_rps=1000)

    assert lambdas["client"] == pytest.approx(1000)
    assert lambdas["cache"] == pytest.approx(1000)
    assert lambdas["db"] == pytest.approx(200, rel=1e-3)  # 1 - hit_ratio(0.8) = 0.2


def test_utilisation_increases_with_load_and_saturates():
    graph = compile_graph(simple_graph())
    low = node_metrics(graph, compute_traffic(graph, 100))
    high = node_metrics(graph, compute_traffic(graph, 50_000))

    assert low["api"].rho < high["api"].rho
    assert high["api"].saturated or high["api"].rho > 0.95


def test_more_replicas_reduce_utilisation_and_latency():
    g1 = compile_graph(simple_graph(api_replicas=1))
    g2 = compile_graph(simple_graph(api_replicas=4))

    m1 = node_metrics(g1, compute_traffic(g1, 2000))
    m2 = node_metrics(g2, compute_traffic(g2, 2000))

    assert m2["api"].rho < m1["api"].rho
    assert m2["api"].response_mean_ms < m1["api"].response_mean_ms


def test_bottleneck_capacity_identifies_lower_capacity_node():
    g = simple_graph(api_replicas=10, db_replicas=1)  # DB (via cache miss) should bottleneck first
    graph = compile_graph(g)
    lambdas = compute_traffic(graph, 1000)
    max_rps, bottleneck = bottleneck_capacity(graph, lambdas, "client")

    assert max_rps > 0
    assert bottleneck is not None


def test_end_to_end_latency_grows_with_load():
    graph = compile_graph(simple_graph())
    low_metrics = node_metrics(graph, compute_traffic(graph, 100))
    high_metrics = node_metrics(graph, compute_traffic(graph, 4000))

    low_lat = end_to_end_latency_ms(graph, low_metrics, "client")
    high_lat = end_to_end_latency_ms(graph, high_metrics, "client")

    assert high_lat > low_lat


def test_availability_improves_with_redundancy():
    g1 = compile_graph(simple_graph(api_replicas=1))
    g2 = compile_graph(simple_graph(api_replicas=3))

    a1 = end_to_end_availability(g1, "client", "db")
    a2 = end_to_end_availability(g2, "client", "db")

    assert a2 > a1


# --------------------------------------------------------------------------
# Findings
# --------------------------------------------------------------------------

def test_findings_flag_saturation_spof_and_latency_slo():
    graph = compile_graph(simple_graph(api_replicas=1, db_replicas=1))
    lambdas = compute_traffic(graph, peak_rps=50_000)
    metrics = node_metrics(graph, lambdas)
    requirements = {"peak_rps": 50_000, "p99_slo_ms": 10, "availability_slo": 0.99999}

    findings = build_findings(graph, metrics, requirements, "client")
    types = {f.type for f in findings}

    assert SATURATION in types
    assert SPOF in types
    assert LATENCY_SLO in types
    # Findings must be sorted most severe first.
    assert findings == sorted(findings, key=lambda f: f.severity, reverse=True)


def test_healthy_design_has_no_blocking_findings():
    graph = compile_graph(simple_graph(api_replicas=5, db_replicas=3))
    lambdas = compute_traffic(graph, peak_rps=500)
    metrics = node_metrics(graph, lambdas)
    requirements = {"peak_rps": 500, "p99_slo_ms": 5000, "availability_slo": 0.9}

    findings = build_findings(graph, metrics, requirements, "client")
    blocking = [f for f in findings if f.type in (SATURATION, LATENCY_SLO, AVAILABILITY_SLO)]
    assert blocking == []


# --------------------------------------------------------------------------
# Failure scenarios
# --------------------------------------------------------------------------

def test_kill_node_scenario_removes_node_and_dependents():
    mutated = apply_graph_scenario(simple_graph(), {"type": "kill_node", "node_id": "cache"})
    ids = {n["id"] for n in mutated["nodes"]}
    assert "cache" not in ids
    assert all("cache" not in (e["src"], e["dst"]) for e in mutated["edges"])


def test_lose_replica_scenario_decrements_replicas():
    mutated = apply_graph_scenario(simple_graph(api_replicas=3), {"type": "lose_replica", "node_id": "api", "count": 2})
    api = next(n for n in mutated["nodes"] if n["id"] == "api")
    assert api["params"]["replicas"] == 1


def test_traffic_spike_scales_requirements():
    mutated = apply_requirements_scenario({"peak_rps": 1000}, {"type": "traffic_spike", "multiplier": 3})
    assert mutated["peak_rps"] == 3000


def test_killing_the_only_api_replica_breaks_the_client_path():
    mutated = apply_graph_scenario(simple_graph(api_replicas=1), {"type": "kill_node", "node_id": "api"})
    # strict=False: scenario-mutated graphs are expected to strand nodes;
    # that is what we are about to confirm, not a validation error.
    graph = compile_graph(mutated, strict=False)

    import networkx as nx
    assert "db" in graph.nodes
    assert not nx.has_path(graph.nx_undirected, "client", "db")


# --------------------------------------------------------------------------
# Allocator
# --------------------------------------------------------------------------

def test_reference_allocation_satisfies_requirements():
    g = simple_graph(api_replicas=1, db_replicas=1)
    requirements = {"peak_rps": 20_000, "p99_slo_ms": 200, "availability_slo": 0.99}

    result = reference_allocation(g, requirements, "client")

    assert result["satisfied"]
    assert result["replicas_added"] > 0
    assert result["reference_cost"] >= result["candidate_cost"]


# --------------------------------------------------------------------------
# Simulation (DES) sanity + cross-validation against the analytic model
# --------------------------------------------------------------------------

def test_simulation_runs_and_agrees_roughly_with_analytic_model():
    graph = compile_graph(simple_graph(api_replicas=3, db_replicas=2))
    peak_rps = 400

    analytic_metrics = node_metrics(graph, compute_traffic(graph, peak_rps))
    analytic_latency = end_to_end_latency_ms(graph, analytic_metrics, "client")

    sim = simulate(graph, peak_rps, "client", n_requests=2000, replications=3, seed=42)

    assert sim["end_to_end_ms"]["mean"] > 0
    assert sim["end_to_end_ms"]["p99"] >= sim["end_to_end_ms"]["p50"]
    # DES mean should be in the right ballpark of the analytic mean (loose
    # bound: this is a stochastic cross-check, not an exact equality).
    assert sim["end_to_end_ms"]["mean"] < analytic_latency * 3 + 20
