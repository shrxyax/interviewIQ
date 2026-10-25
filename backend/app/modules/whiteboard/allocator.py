"""
Greedy reference allocation: starting from the candidate's own topology,
find a near-minimal-cost replica count per node that satisfies the SLOs.
Used only as a cost-efficiency baseline in the report ("the reference
allocation would cost X; yours costs Y"), never shown as "the correct
answer" since it keeps the candidate's own architecture, just resources.
"""

import copy

from app.modules.whiteboard.compiler import compile_graph
from app.modules.whiteboard.findings import LATENCY_SLO, SATURATION, build_findings
from app.modules.whiteboard.queueing import compute_traffic, node_metrics

MAX_STEPS = 60
REPLICA_COST = 1.0  # relative unit cost per replica; all node types treated equally


def _violations(graph_json: dict, requirements: dict, client_id: str) -> tuple[int, dict]:
    graph = compile_graph(graph_json)
    lambdas = compute_traffic(graph, requirements["peak_rps"])
    metrics = node_metrics(graph, lambdas)
    findings = build_findings(graph, metrics, requirements, client_id)

    blocking = [f for f in findings if f.type in (SATURATION, LATENCY_SLO)]
    return len(blocking), {"graph": graph, "metrics": metrics, "findings": findings}


def reference_allocation(graph_json: dict, requirements: dict, client_id: str) -> dict:
    """
    Greedy marginal analysis: repeatedly add one replica to whichever
    scalable node currently has the highest utilisation, until no
    saturation/latency-SLO findings remain or a step budget is hit.
    """

    working = copy.deepcopy(graph_json)
    total_added = 0

    for _ in range(MAX_STEPS):
        n_violations, ctx = _violations(working, requirements, client_id)

        if n_violations == 0:
            break

        graph, metrics = ctx["graph"], ctx["metrics"]
        scalable = [
            (node_id, m.rho)
            for node_id, m in metrics.items()
            if graph.nodes[node_id].type not in ("client",) and m.rho not in (float("inf"),)
        ]

        if not scalable:
            break

        worst_node_id = max(scalable, key=lambda x: x[1])[0]

        for n in working["nodes"]:
            if n["id"] == worst_node_id:
                params = n.setdefault("params", {})
                params["replicas"] = int(params.get("replicas", 1)) + 1
                total_added += 1
                break

    n_violations, _ = _violations(working, requirements, client_id)
    reference_cost = sum(n.get("params", {}).get("replicas", 1) * REPLICA_COST for n in working["nodes"] if n["type"] != "client")
    candidate_cost = sum(n.get("params", {}).get("replicas", 1) * REPLICA_COST for n in graph_json["nodes"] if n["type"] != "client")

    return {
        "satisfied": n_violations == 0,
        "replicas_added": total_added,
        "reference_cost": reference_cost,
        "candidate_cost": candidate_cost,
        "cost_efficiency": round(reference_cost / candidate_cost, 3) if candidate_cost else None,
        "reference_graph": working,
    }
