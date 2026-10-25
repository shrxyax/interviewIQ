"""
Compiles a candidate's JSON design graph into a validated internal
representation. Pure structure/validation; no performance maths here
(see queueing.py / structural.py).
"""

from dataclasses import dataclass, field

import networkx as nx

from app.modules.whiteboard.catalog import CATALOG, get


class DesignError(ValueError):
    def __init__(self, message: str, node_id: str | None = None):
        super().__init__(message)
        self.node_id = node_id


@dataclass
class Node:
    id: str
    type: str
    label: str
    replicas: int
    params: dict = field(default_factory=dict)

    @property
    def catalog(self):
        return get(self.type)

    def param(self, name: str, default=None):
        if name in self.params:
            return self.params[name]
        return self.catalog.extra_params.get(name, default)

    @property
    def mu(self) -> float:
        return float(self.params.get("mu", self.catalog.mu))

    @property
    def base_latency_ms(self) -> float:
        return float(self.params.get("base_latency_ms", self.catalog.base_latency_ms))

    @property
    def availability(self) -> float:
        return float(self.params.get("availability", self.catalog.availability))


@dataclass
class Edge:
    src: str
    dst: str
    fraction: float | str  # a number, or the symbolic value "miss"
    kind: str  # sync | async


@dataclass
class CompiledGraph:
    nodes: dict[str, Node]
    edges: list[Edge]
    nx: nx.DiGraph  # directed, for traffic propagation / ordering
    nx_undirected: nx.Graph  # for articulation points / min-cut

    def children(self, node_id: str) -> list[Edge]:
        return [e for e in self.edges if e.src == node_id]

    def parents(self, node_id: str) -> list[Edge]:
        return [e for e in self.edges if e.dst == node_id]


def compile_graph(graph_json: dict, strict: bool = True) -> CompiledGraph:
    """
    strict=True (default): the candidate's own submitted design must have
    every component reachable from a client (catches "you forgot to wire
    this up" mistakes).

    strict=False: used for graphs already mutated by a failure scenario
    (failures.py), where a kill_node/lose_replica scenario is EXPECTED to
    strand some components — that is the thing being measured, not a
    validation error. Unreachable nodes still compile; they simply carry
    zero traffic in compute_traffic and are reported via blast_radius.
    """
    raw_nodes = graph_json.get("nodes", [])
    raw_edges = graph_json.get("edges", [])

    if not raw_nodes:
        raise DesignError("The design has no components yet.")

    nodes: dict[str, Node] = {}

    for n in raw_nodes:
        node_id = n.get("id")

        if not node_id:
            raise DesignError("Every node needs an id.")

        if node_id in nodes:
            raise DesignError(f"Duplicate node id '{node_id}'.", node_id)

        node_type = n.get("type")

        if node_type not in CATALOG:
            raise DesignError(f"Unknown component type '{node_type}'.", node_id)

        replicas = int(n.get("params", {}).get("replicas", 1))

        if replicas < 1:
            raise DesignError("replicas must be at least 1.", node_id)

        nodes[node_id] = Node(
            id=node_id,
            type=node_type,
            label=n.get("label", get(node_type).label),
            replicas=replicas,
            params=n.get("params", {}),
        )

    client_nodes = [n for n in nodes.values() if n.type == "client"]

    if not client_nodes:
        raise DesignError("The design needs at least one client node.")

    edges: list[Edge] = []
    digraph = nx.DiGraph()
    ugraph = nx.Graph()

    for node_id in nodes:
        digraph.add_node(node_id)
        ugraph.add_node(node_id)

    for e in raw_edges:
        src, dst = e.get("src"), e.get("dst")

        if src not in nodes:
            raise DesignError(f"Edge references unknown node '{src}'.")
        if dst not in nodes:
            raise DesignError(f"Edge references unknown node '{dst}'.")
        if src == dst:
            raise DesignError(f"Node '{src}' cannot connect to itself.", src)

        fraction = e.get("fraction", 1.0)

        if fraction != "miss":
            fraction = float(fraction)
            if not (0 <= fraction <= 1):
                raise DesignError(f"Edge fraction must be between 0 and 1, got {fraction}.")

        kind = e.get("kind", "sync")

        if kind not in ("sync", "async"):
            raise DesignError(f"Edge kind must be 'sync' or 'async', got '{kind}'.")

        edges.append(Edge(src=src, dst=dst, fraction=fraction, kind=kind))
        digraph.add_edge(src, dst)
        ugraph.add_edge(src, dst)

    # Structural rules.
    for node in nodes.values():
        if strict and node.catalog.role == "data" and node.type == "cache":
            backs = [e for e in edges if e.src == node.id and e.fraction == "miss"]
            if not backs:
                raise DesignError(
                    f"Cache '{node.id}' has no backing store (add a 'miss' edge to a database).",
                    node.id,
                )

        if strict and node.type == "read_replica":
            if not any(e.dst == node.id for e in edges):
                raise DesignError(f"Read replica '{node.id}' is not connected to anything.", node.id)

    reachable = set()
    for client in client_nodes:
        reachable |= nx.descendants(digraph, client.id) | {client.id}

    unreachable = set(nodes) - reachable

    if unreachable and strict:
        raise DesignError(f"These components are unreachable from any client: {sorted(unreachable)}.")

    if not nx.is_directed_acyclic_graph(digraph):
        cycle_edges = [e for e in edges if e.kind == "sync"]
        cycle_digraph = nx.DiGraph([(e.src, e.dst) for e in cycle_edges])
        if not nx.is_directed_acyclic_graph(cycle_digraph):
            raise DesignError("Synchronous call edges must not form a cycle (async/queue edges may).")

    return CompiledGraph(nodes=nodes, edges=edges, nx=digraph, nx_undirected=ugraph)
