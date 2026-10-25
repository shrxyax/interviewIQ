"""
Structural analysis: single points of failure via articulation points and
minimum vertex cuts (Menger's theorem, via networkx max-flow).
"""

import networkx as nx

from app.modules.whiteboard.catalog import DURABLE_STORE_TYPES
from app.modules.whiteboard.compiler import CompiledGraph


def articulation_points(graph: CompiledGraph) -> set[str]:
    """
    A node whose removal disconnects the (undirected) serving graph.
    O(V + E) via Tarjan's algorithm (networkx implementation).
    """

    return set(nx.articulation_points(graph.nx_undirected))


def min_cut_size(graph: CompiledGraph, source: str, target: str) -> int:
    """
    Minimum number of NODES whose removal disconnects source from target
    (vertex connectivity). Computed via node-splitting + max-flow/min-cut,
    which is what networkx's `minimum_node_cut` does internally.
    """

    if source == target:
        return 0

    try:
        return len(nx.minimum_node_cut(graph.nx_undirected, source, target))
    except nx.NetworkXError:
        return 0


def single_points_of_failure(graph: CompiledGraph) -> list[dict]:
    """
    A node is a SPOF if it has only 1 replica AND removing it entirely
    cuts off at least one client from at least one durable data store
    (blast_radius is non-empty). This directly covers both internal cut
    vertices (e.g. a single load balancer or cache) and terminal store
    nodes themselves (a lone database with no replica is trivially a
    SPOF, even though leaf nodes are never "articulation points" in the
    graph-theoretic sense).

    Internally-redundant nodes (replicas > 1) are never flagged: the
    compiler/queueing layer already models them as a pool.
    """

    findings = []

    for node in graph.nodes.values():
        if node.type == "client" or node.replicas > 1:
            continue

        affected = blast_radius(graph, node.id)

        if affected:
            findings.append({"node_id": node.id, "min_cut_size": 1, "blast_radius": affected})

    return findings


def blast_radius(graph: CompiledGraph, failed_node_id: str) -> list[str]:
    """
    Clients that lose all paths to all durable data stores if
    `failed_node_id` is removed. Used both for SPOF reporting and
    failure-injection scenarios. Caches are deliberately not counted as
    a "store" here (see DURABLE_STORE_TYPES): losing a cache matters
    only insofar as it also cuts off the real store behind it, which
    this still detects.

    If the design has no durable store at all, any client losing all
    connectivity counts as affected instead.
    """

    remaining = graph.nx_undirected.copy()
    remaining.remove_node(failed_node_id)

    clients = [n.id for n in graph.nodes.values() if n.type == "client"]
    data_stores = [n.id for n in graph.nodes.values() if n.type in DURABLE_STORE_TYPES]

    affected = []

    for client in clients:
        if client not in remaining:
            affected.append(client)
            continue

        if data_stores:
            reachable_stores = [s for s in data_stores if s in remaining and nx.has_path(remaining, client, s)]
            if not reachable_stores:
                affected.append(client)
        elif remaining.number_of_nodes() > 1 and not nx.node_connected_component(remaining, client) - {client}:
            affected.append(client)

    return affected
