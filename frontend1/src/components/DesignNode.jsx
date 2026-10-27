import { Handle, Position } from "@xyflow/react";

import "./DesignNode.css";

// One component box on a system-design canvas (System Design Lab and the
// interview's design round), coloured by its analysed utilisation.

function utilColor(u) {
  if (u == null) return "var(--border)";
  if (u >= 1) return "var(--danger)";
  if (u >= 0.8) return "var(--warning)";
  return "var(--success)";
}

export default function DesignNode({ data }) {
  const m = data.metrics;
  return (
    <div
      onClick={() => data.onSelect(data.id)}
      className={`wb-node ${data.selected ? "selected" : ""}`}
      style={{ borderColor: m ? utilColor(m.utilisation) : undefined }}
    >
      <Handle type="target" position={Position.Left} className="flow-handle" />
      <div className="wb-node-type">{data.type}</div>
      <div className="wb-node-label">{data.label}</div>
      <div className="wb-node-meta">x{data.replicas}</div>
      {m && (
        <div className="wb-node-util" style={{ color: utilColor(m.utilisation) }}>
          {m.utilisation != null ? `${Math.round(m.utilisation * 100)}% util` : "—"}
          {m.saturated && " · SATURATED"}
        </div>
      )}
      <Handle type="source" position={Position.Right} className="flow-handle" />
    </div>
  );
}
