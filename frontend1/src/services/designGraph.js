import { MarkerType } from "@xyflow/react";

// Conversions between the backend's design graph JSON
// ({nodes: [{id, type, label, params}], edges: [{src, dst, fraction, kind}]})
// and React Flow nodes/edges. Shared by the System Design Lab and the
// interview's design round.

export const designNodeTypes = "design";

const edgeStyle = (kind) => ({ stroke: kind === "async" ? "var(--info)" : "var(--border)" });
const arrow = { type: MarkerType.ArrowClosed, color: "var(--muted)" };

// Left-to-right layers by hop distance from the clients, for graphs saved
// without positions: client -> load balancer -> API -> cache -> database.
function layeredPositions(graph) {
  const depth = {};
  const queue = graph.nodes.filter((n) => n.type === "client").map((n) => n.id);
  queue.forEach((id) => (depth[id] = 0));

  while (queue.length) {
    const id = queue.shift();
    for (const e of graph.edges) {
      if (e.src === id && depth[e.dst] === undefined) {
        depth[e.dst] = depth[id] + 1;
        queue.push(e.dst);
      }
    }
  }

  const maxDepth = Math.max(0, ...Object.values(depth));
  const rows = {};
  const positions = {};

  for (const n of graph.nodes) {
    const d = depth[n.id] ?? maxDepth + 1; // unconnected nodes go last
    rows[d] = (rows[d] ?? 0) + 1;
    positions[n.id] = { x: d * 220, y: (rows[d] - 1) * 130 };
  }

  return positions;
}

export function graphToFlow(graph, onSelect) {
  const layout = layeredPositions(graph);
  const nodes = graph.nodes.map((n) => ({
    id: n.id,
    type: designNodeTypes,
    position: n.position || layout[n.id],
    data: { ...n, replicas: n.params?.replicas ?? 1, onSelect },
  }));
  const edges = graph.edges.map((e) => ({
    id: `${e.src}-${e.dst}`,
    source: e.src,
    target: e.dst,
    label: e.fraction === "miss" ? "miss" : String(e.fraction),
    style: edgeStyle(e.kind),
    markerEnd: arrow,
  }));
  return { nodes, edges };
}

export function flowToGraph(nodes, edges) {
  return {
    nodes: nodes.map((n) => ({ id: n.id, type: n.data.type, label: n.data.label, params: n.data.params })),
    edges: edges.map((e) => ({
      src: e.source,
      dst: e.target,
      fraction: e.label === "miss" ? "miss" : parseFloat(e.label) || 1.0,
      kind: e.style?.stroke === "var(--info)" ? "async" : "sync",
    })),
  };
}

// A new connection drawn on the canvas: synchronous, carries all traffic.
export const newEdge = (params) => ({
  ...params,
  label: "1.0",
  style: edgeStyle("sync"),
  markerEnd: arrow,
});

export function newNode(catalog, type, onSelect) {
  const def = catalog.find((c) => c.id === type);
  const id = `${type}_${Date.now().toString(36)}`;
  const params = {
    replicas: 1,
    ...(def?.defaults?.hit_ratio !== undefined ? { hit_ratio: def.defaults.hit_ratio } : {}),
  };
  return {
    id,
    type: designNodeTypes,
    position: { x: 80 + Math.random() * 300, y: 80 + Math.random() * 240 },
    data: { id, type, label: def?.label || type, params, replicas: 1, onSelect },
  };
}

// Sets one param on one node (replicas also mirrored for the node's label).
export const withParam = (nodes, nodeId, key, value) =>
  nodes.map((n) =>
    n.id === nodeId
      ? {
          ...n,
          data: {
            ...n.data,
            params: { ...n.data.params, [key]: value },
            replicas: key === "replicas" ? value : n.data.replicas,
          },
        }
      : n
  );
