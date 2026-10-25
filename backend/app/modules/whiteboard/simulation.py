"""
Discrete-event simulation (SimPy): an independent check on the analytic
M/M/c model (queueing.py), and the only way to see a failure scenario
unfold over time rather than as a single before/after snapshot.

Each node with finite capacity is a simpy.Resource(capacity=replicas).
A request is simulated hop by hop; at each node it either terminates
there (served) or is routed onward using the SAME edge-fraction logic as
the analytic traffic solver (queueing.edge_fraction), which is what
makes the two models comparable.

We simulate a FIXED NUMBER of requests per replication rather than a
fixed wall-clock duration: for a Poisson/exponential network the
per-request latency distribution does not depend on how long the clock
runs, only on how many requests are observed, so bounding the request
count bounds the work regardless of how high peak_rps is.
"""

import random
from dataclasses import dataclass, field

import numpy as np
import simpy

from app.modules.whiteboard.compiler import CompiledGraph
from app.modules.whiteboard.queueing import edge_fraction


DEFAULT_REQUESTS = 3000
DEFAULT_REPLICATIONS = 3
MAX_HOPS = 20  # guards against a routing bug producing an infinite loop


@dataclass
class ReplicationResult:
    end_to_end_ms: list[float] = field(default_factory=list)
    node_wait_ms: dict[str, list[float]] = field(default_factory=dict)
    timed_out: int = 0


def _choose_next(graph: CompiledGraph, node_id: str, rng: random.Random) -> str | None:
    edges = graph.children(node_id)
    if not edges:
        return None

    r = rng.random()
    cumulative = 0.0

    for e in edges:
        cumulative += edge_fraction(graph, e)
        if r < cumulative:
            return e.dst

    return None  # remaining probability: served at this node


def _run_one_replication(graph, peak_rps, client_id, n_requests, seed, scenario_delay_at=None) -> ReplicationResult:
    """
    One replication, run to true completion (simpy's `env.run()` with no
    `until` runs until no more events are scheduled).
    """

    rng = random.Random(seed)
    env = simpy.Environment()

    resources = {
        node_id: simpy.Resource(env, capacity=max(1, node.replicas))
        for node_id, node in graph.nodes.items()
        if node.type != "client"
    }

    result = ReplicationResult(node_wait_ms={n: [] for n in resources})

    def request_process():
        start = env.now
        node_id = client_id
        hops = 0

        while hops < MAX_HOPS:
            nxt = _choose_next(graph, node_id, rng)
            if nxt is None:
                break

            node = graph.nodes[nxt]
            hops += 1

            with resources[nxt].request() as req:
                wait_start = env.now
                yield req
                result.node_wait_ms[nxt].append((env.now - wait_start) * 1000)
                yield env.timeout(rng.expovariate(node.mu))

            extra = scenario_delay_at[1] / 1000 if scenario_delay_at and scenario_delay_at[0] == nxt else 0
            yield env.timeout(node.base_latency_ms / 1000 + extra)

            node_id = nxt

        if hops >= MAX_HOPS:
            result.timed_out += 1

        result.end_to_end_ms.append((env.now - start) * 1000)

    def arrivals():
        for _ in range(n_requests):
            yield env.timeout(rng.expovariate(peak_rps))
            env.process(request_process())

    env.process(arrivals())
    env.run()
    return result


def _percentile_ci(samples: list[float], pct: float, n_boot: int = 200, seed: int = 0) -> tuple[float, float]:
    """
    Bootstrap confidence interval for a percentile (mean/variance-based
    CIs are not valid for tail percentiles of a skewed distribution).
    """

    if not samples:
        return float("nan"), 0.0

    arr = np.asarray(samples)
    point = float(np.percentile(arr, pct))

    rng = np.random.default_rng(seed)
    boot = [float(np.percentile(rng.choice(arr, size=len(arr), replace=True), pct)) for _ in range(n_boot)]

    return point, float(1.96 * np.std(boot))


def simulate(
    graph: CompiledGraph,
    peak_rps: float,
    client_id: str,
    n_requests: int = DEFAULT_REQUESTS,
    replications: int = DEFAULT_REPLICATIONS,
    seed: int = 0,
    scenario_delay_at: tuple[str, float] | None = None,
) -> dict:
    runs = [
        _run_one_replication(graph, peak_rps, client_id, n_requests, seed + i, scenario_delay_at)
        for i in range(replications)
    ]

    all_latencies = [v for r in runs for v in r.end_to_end_ms]
    p50, p50_ci = _percentile_ci(all_latencies, 50, seed=seed)
    p95, p95_ci = _percentile_ci(all_latencies, 95, seed=seed + 1)
    p99, p99_ci = _percentile_ci(all_latencies, 99, seed=seed + 2)

    mean_per_run = [float(np.mean(r.end_to_end_ms)) if r.end_to_end_ms else float("nan") for r in runs]

    node_summary = {}
    for node_id in runs[0].node_wait_ms:
        pooled = [v for r in runs for v in r.node_wait_ms[node_id]]
        if pooled:
            node_summary[node_id] = {
                "mean_wait_ms": round(float(np.mean(pooled)), 3),
                "p99_wait_ms": round(float(np.percentile(pooled, 99)), 3),
                "samples": len(pooled),
            }

    return {
        "requests_per_replication": n_requests,
        "replications": replications,
        "end_to_end_ms": {
            "mean": round(float(np.mean(mean_per_run)), 3),
            "mean_ci95": round(float(1.96 * np.std(mean_per_run) / max(len(mean_per_run) ** 0.5, 1)), 3),
            "p50": round(p50, 3), "p50_ci95": round(p50_ci, 3),
            "p95": round(p95, 3), "p95_ci95": round(p95_ci, 3),
            "p99": round(p99, 3), "p99_ci95": round(p99_ci, 3),
        },
        "timed_out_requests": sum(r.timed_out for r in runs),
        "node_wait": node_summary,
    }
