"""
Traffic propagation and M/M/c queueing analysis over a compiled design
graph. Pure numpy/math; the discrete-event simulation in simulation.py
is a second, independent way of computing (and validating) these numbers.

All internal time units are seconds unless a name ends in _ms.
"""

import math
from dataclasses import dataclass

import numpy as np

from app.modules.whiteboard.compiler import CompiledGraph


SATURATED_RHO = 0.999  # treat utilisation at/above this as "will not stabilise"


def edge_fraction(graph: CompiledGraph, edge) -> float:
    if edge.fraction == "miss":
        src = graph.nodes[edge.src]
        hit_ratio = float(src.param("hit_ratio", 0.8))
        return 1 - hit_ratio

    return float(edge.fraction)


def compute_traffic(graph: CompiledGraph, peak_rps: float) -> dict[str, float]:
    """
    Solve the Jackson traffic equations  x = lambda_ext + P^T x  for the
    arrival rate at every node, where P[u][v] is the (possibly dynamic,
    e.g. cache-miss) routing probability on edge u->v.
    """

    ids = list(graph.nodes)
    index = {node_id: i for i, node_id in enumerate(ids)}
    n = len(ids)

    P = np.zeros((n, n))
    for e in graph.edges:
        P[index[e.src], index[e.dst]] += edge_fraction(graph, e)

    lambda_ext = np.zeros(n)
    clients = [node_id for node_id, node in graph.nodes.items() if node.type == "client"]

    for client_id in clients:
        lambda_ext[index[client_id]] = peak_rps / len(clients)

    A = np.eye(n) - P.T

    try:
        x = np.linalg.solve(A, lambda_ext)
    except np.linalg.LinAlgError:
        x, *_ = np.linalg.lstsq(A, lambda_ext, rcond=None)

    return {node_id: max(0.0, float(x[index[node_id]])) for node_id in ids}


def erlang_c(c: int, offered_load: float) -> float:
    """
    P(an arrival must wait), via the numerically stable Erlang-B
    recursion converted to Erlang-C. `offered_load` = lambda / mu
    (in Erlangs), not yet divided by c.
    """

    if offered_load <= 0:
        return 0.0

    b = 1.0
    for k in range(1, c + 1):
        b = (offered_load * b) / (k + offered_load * b)

    rho = offered_load / c
    denom = 1 - rho + rho * b

    return b / denom if denom > 1e-12 else 1.0


@dataclass
class NodeMetrics:
    node_id: str
    lambda_: float
    capacity: float
    rho: float
    p_wait: float
    wq_mean_ms: float
    wq_p99_ms: float
    response_mean_ms: float
    response_p99_ms: float
    saturated: bool


def node_metrics(graph: CompiledGraph, lambdas: dict[str, float]) -> dict[str, NodeMetrics]:
    results = {}

    for node_id, node in graph.nodes.items():
        lam = lambdas[node_id]

        if node.type == "client" or math.isinf(node.mu):
            results[node_id] = NodeMetrics(node_id, lam, float("inf"), 0.0, 0.0, 0.0, 0.0, node.base_latency_ms, node.base_latency_ms, False)
            continue

        capacity = node.replicas * node.mu
        rho = lam / capacity if capacity > 0 else float("inf")

        if rho >= SATURATED_RHO:
            results[node_id] = NodeMetrics(
                node_id, lam, capacity, rho, 1.0, float("inf"), float("inf"),
                float("inf"), float("inf"), True,
            )
            continue

        offered = lam / node.mu
        p_wait = erlang_c(node.replicas, offered)

        service_rate_excess = capacity - lam  # c*mu - lambda, in requests/sec
        wq_mean = p_wait / service_rate_excess if service_rate_excess > 0 else float("inf")

        if p_wait <= 0.01:
            wq_p99 = 0.0
        else:
            wq_p99 = math.log(p_wait / 0.01) / service_rate_excess if service_rate_excess > 0 else float("inf")

        service_mean = 1 / node.mu
        response_mean_ms = (wq_mean + service_mean) * 1000 + node.base_latency_ms
        response_p99_ms = (wq_p99 + service_mean) * 1000 + node.base_latency_ms

        results[node_id] = NodeMetrics(
            node_id, lam, capacity, rho, p_wait,
            wq_mean * 1000, wq_p99 * 1000,
            response_mean_ms, response_p99_ms, False,
        )

    return results


def visit_ratios(lambdas: dict[str, float], client_id: str) -> dict[str, float]:
    base = lambdas[client_id]
    if base <= 0:
        return {node_id: 0.0 for node_id in lambdas}
    return {node_id: lam / base for node_id, lam in lambdas.items()}


def end_to_end_latency_ms(graph: CompiledGraph, metrics: dict[str, NodeMetrics], client_id: str, percentile: str = "mean") -> float:
    """
    Aggregate expected latency per client request via visit ratios
    (an operational-analysis identity: exact for the "mean" case under
    the model's own assumptions; the p99 version is an additive
    approximation, called out as such in the report).
    """

    lambdas = {k: v.lambda_ for k, v in metrics.items()}
    ratios = visit_ratios(lambdas, client_id)
    total = 0.0

    for node_id, ratio in ratios.items():
        if node_id == client_id or ratio <= 0:
            continue

        m = metrics[node_id]
        value = m.response_p99_ms if percentile == "p99" else m.response_mean_ms

        if math.isinf(value):
            return float("inf")

        total += ratio * value

    return total


def bottleneck_capacity(graph: CompiledGraph, lambdas: dict[str, float], client_id: str) -> tuple[float, str | None]:
    """
    Bottleneck law: the max client-level throughput the system can sustain
    before some node's utilisation hits 1, given today's routing fractions.
    """

    ratios = visit_ratios(lambdas, client_id)
    best_x, bottleneck = float("inf"), None

    for node_id, node in graph.nodes.items():
        if node.type == "client" or math.isinf(node.mu) or ratios.get(node_id, 0) <= 0:
            continue

        capacity = node.replicas * node.mu
        x_max = capacity / ratios[node_id]

        if x_max < best_x:
            best_x, bottleneck = x_max, node_id

    return best_x, bottleneck


def capacity_runway_months(current_rps: float, max_rps: float, growth_per_month: float) -> float | None:
    if growth_per_month <= 0 or max_rps <= current_rps:
        return None

    return math.log(max_rps / current_rps) / math.log(1 + growth_per_month)


def group_availability(node) -> float:
    """
    A node is modelled as `replicas` independent instances; the group is
    up if at least one instance is up (simple binary availability, not a
    capacity-weighted degradation model).
    """

    return 1 - (1 - node.availability) ** node.replicas


def path_availability(graph: CompiledGraph, path: list[str]) -> float:
    value = 1.0
    for node_id in path:
        value *= group_availability(graph.nodes[node_id])
    return value


def end_to_end_availability(graph: CompiledGraph, client_id: str, store_id: str, max_paths: int = 12) -> float:
    """
    Series-parallel reliability: enumerate simple paths (capped, these
    design graphs are small) and combine as 1 - product(1 - A_path).
    """

    import networkx as nx

    try:
        paths = list(nx.all_simple_paths(graph.nx, client_id, store_id, cutoff=8))
    except nx.NodeNotFound:
        return 0.0

    if not paths:
        return 0.0

    paths = paths[:max_paths]
    failure_prob = 1.0

    for path in paths:
        failure_prob *= 1 - path_availability(graph, path)

    return 1 - failure_prob
