"""
Failure scenarios: mutate a design graph (or its requirements) before
re-running the same analysis pipeline, so "what if X fails" is answered
by the identical queueing/structural machinery, not a special case.
"""

import copy


KILL_NODE = "kill_node"
LOSE_REPLICA = "lose_replica"
COLD_CACHE = "cold_cache"
LATENCY_INJECTION = "latency_injection"
TRAFFIC_SPIKE = "traffic_spike"  # handled as a requirements override, not a graph mutation

GRAPH_SCENARIOS = {KILL_NODE, LOSE_REPLICA, COLD_CACHE, LATENCY_INJECTION}


class ScenarioError(ValueError):
    pass


def _find_node(graph_json: dict, node_id: str) -> dict:
    for n in graph_json["nodes"]:
        if n["id"] == node_id:
            return n

    raise ScenarioError(f"Scenario references unknown node '{node_id}'.")


def apply_graph_scenario(graph_json: dict, scenario: dict) -> dict:
    """
    Returns a new graph dict with the scenario applied. The result is
    re-compiled and re-analysed through the normal pipeline.
    """

    mutated = copy.deepcopy(graph_json)
    scenario_type = scenario.get("type")

    if scenario_type == KILL_NODE:
        node_id = scenario["node_id"]
        _find_node(mutated, node_id)  # validate it exists
        mutated["nodes"] = [n for n in mutated["nodes"] if n["id"] != node_id]
        mutated["edges"] = [e for e in mutated["edges"] if node_id not in (e["src"], e["dst"])]

    elif scenario_type == LOSE_REPLICA:
        node = _find_node(mutated, scenario["node_id"])
        params = node.setdefault("params", {})
        current = int(params.get("replicas", 1))
        params["replicas"] = max(0, current - scenario.get("count", 1))

    elif scenario_type == COLD_CACHE:
        node = _find_node(mutated, scenario["node_id"])
        node.setdefault("params", {})["hit_ratio"] = scenario.get("hit_ratio", 0.0)

    elif scenario_type == LATENCY_INJECTION:
        node = _find_node(mutated, scenario["node_id"])
        params = node.setdefault("params", {})
        base = params.get("base_latency_ms")
        if base is None:
            from app.modules.whiteboard.catalog import get as catalog_get
            base = catalog_get(node["type"]).base_latency_ms
        params["base_latency_ms"] = base + scenario.get("extra_ms", 100)

    else:
        raise ScenarioError(f"Unknown or non-graph scenario type '{scenario_type}'.")

    return mutated


def apply_requirements_scenario(requirements: dict, scenario: dict) -> dict:
    mutated = dict(requirements)

    if scenario.get("type") == TRAFFIC_SPIKE:
        mutated["peak_rps"] = requirements["peak_rps"] * scenario.get("multiplier", 2.0)
    else:
        raise ScenarioError(f"Unknown requirements scenario type '{scenario.get('type')}'.")

    return mutated


SCENARIO_CATALOG = [
    {"type": KILL_NODE, "label": "Kill a node", "params": ["node_id"]},
    {"type": LOSE_REPLICA, "label": "Lose a replica", "params": ["node_id", "count"]},
    {"type": COLD_CACHE, "label": "Cold cache (cache stampede)", "params": ["node_id"]},
    {"type": LATENCY_INJECTION, "label": "Inject latency", "params": ["node_id", "extra_ms"]},
    {"type": TRAFFIC_SPIKE, "label": "Traffic spike", "params": ["multiplier"]},
]
