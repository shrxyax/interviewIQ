import { useCallback, useEffect, useMemo, useState } from "react";
import { ReactFlow, Background, Controls, addEdge, applyNodeChanges, applyEdgeChanges } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Activity, Plus, Send, Trash2 } from "lucide-react";

import Badge from "./shared/Badge";
import DesignNode from "./DesignNode";
import { flowToGraph, graphToFlow, newEdge, newNode, withParam } from "../services/designGraph";

// The system-design lab round inside an interview: the brief (left, in the
// interviewer's stage) and an executable whiteboard with Analyze/Submit
// (right, in place of the spoken-answer box).

const nodeTypes = { design: DesignNode };

const pct = (x) => `${(x * 100).toFixed(x >= 0.999 ? 2 : 0)}%`;

export function DesignProblemPanel({ design }) {
  const { prompt, catalog } = design;
  const r = prompt.requirements;

  return (
    <div className="coding-problem design-brief">
      <div className="coding-problem-head">
        <h2>{prompt.title}</h2>
        <Badge difficulty={prompt.difficulty}>{prompt.difficulty}</Badge>
      </div>

      <p className="coding-statement">{prompt.scenario}</p>

      <div className="section-label">Requirements</div>
      <ul className="design-requirements">
        <li><span>Peak traffic</span>{r.peak_rps.toLocaleString()} requests/s</li>
        <li><span>p99 latency</span>under {r.p99_slo_ms} ms</li>
        {r.availability_slo && <li><span>Availability</span>at least {pct(r.availability_slo)}</li>}
        {r.read_ratio != null && <li><span>Reads</span>{pct(r.read_ratio)} of traffic</li>}
        {r.growth_per_month && <li><span>Growth</span>{pct(r.growth_per_month)} per month</li>}
      </ul>

      <div className="section-label">Capacity of one replica</div>
      <ul className="design-catalog">
        {catalog
          .filter((c) => c.defaults.mu)
          .map((c) => (
            <li key={c.id}>
              <span>{c.label}</span>
              {c.defaults.mu.toLocaleString()} req/s
            </li>
          ))}
      </ul>

      <p className="note">
        Click a component to change its replicas, drag from a box&apos;s right edge to another box to connect
        them, then Analyze to see utilisation, latency and problems.
      </p>
    </div>
  );
}

export function DesignWorkspace({
  design,
  onGraphChange,
  explanation,
  onExplanationChange,
  analyze,
  onSubmit,
  submitting,
  disabled,
  error,
}) {
  // Built from the exercise's saved draft (or starter) on mount, so the
  // canvas can fit the whole diagram on first render. The parent remounts
  // this component (key) for a new exercise.
  const [initial] = useState(() => graphToFlow(design.graph, (id) => setSelectedId(id)));
  const [rfNodes, setRfNodes] = useState(initial.nodes);
  const [rfEdges, setRfEdges] = useState(initial.edges);
  const [selectedId, setSelectedId] = useState(null);
  const [addType, setAddType] = useState("api_service");
  const [analysis, setAnalysis] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzeError, setAnalyzeError] = useState("");

  // Keep the parent's copy current, for submit / ending the interview.
  useEffect(() => {
    if (rfNodes.length) onGraphChange(flowToGraph(rfNodes, rfEdges));
  }, [rfNodes, rfEdges, onGraphChange]);

  const onNodesChange = useCallback((changes) => setRfNodes((nds) => applyNodeChanges(changes, nds)), []);
  const onEdgesChange = useCallback((changes) => setRfEdges((eds) => applyEdgeChanges(changes, eds)), []);
  const onConnect = useCallback((params) => setRfEdges((eds) => addEdge(newEdge(params), eds)), []);

  const selectedNode = rfNodes.find((n) => n.id === selectedId);
  const nodesWithSelection = useMemo(
    () => rfNodes.map((n) => ({ ...n, data: { ...n.data, selected: n.id === selectedId } })),
    [rfNodes, selectedId]
  );

  const setParam = (key, value) => setRfNodes((nds) => withParam(nds, selectedId, key, value));

  const deleteSelected = () => {
    setRfNodes((nds) => nds.filter((n) => n.id !== selectedId));
    setRfEdges((eds) => eds.filter((e) => e.source !== selectedId && e.target !== selectedId));
    setSelectedId(null);
  };

  const runAnalyze = async () => {
    setAnalyzing(true);
    setAnalyzeError("");
    try {
      const result = await analyze(flowToGraph(rfNodes, rfEdges));
      setAnalysis(result);
      setRfNodes((nds) => nds.map((n) => ({ ...n, data: { ...n.data, metrics: result.node_metrics[n.id] } })));
    } catch (err) {
      setAnalysis(null);
      setAnalyzeError(err?.response?.data?.detail || "Couldn't analyse the design. Please try again.");
    } finally {
      setAnalyzing(false);
    }
  };

  const busy = analyzing || submitting;
  const summary = analysis?.summary;

  return (
    <div className="coding-workspace design-workspace">
      <div className="design-toolbar">
        <select
          value={addType}
          onChange={(e) => setAddType(e.target.value)}
          className="field"
          aria-label="Component type"
          disabled={disabled}
        >
          {design.catalog
            .filter((c) => c.id !== "client")
            .map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
              </option>
            ))}
        </select>
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={() => setRfNodes((nds) => [...nds, newNode(design.catalog, addType, setSelectedId)])}
          disabled={disabled}
        >
          <Plus size={14} /> Add
        </button>
      </div>

      <div className="flow-canvas design-canvas">
        <ReactFlow
          nodes={nodesWithSelection}
          edges={rfEdges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          fitView
          fitViewOptions={{ padding: 0.15 }}
          proOptions={{ hideAttribution: true }}
          nodesDraggable={!disabled}
          nodesConnectable={!disabled}
        >
          <Background color="var(--border)" gap={20} />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>

      {selectedNode && (
        <div className="design-selected">
          <strong>{selectedNode.data.label}</strong>
          <label>
            Replicas
            <input
              type="number"
              min={1}
              className="field"
              value={selectedNode.data.params?.replicas ?? 1}
              onChange={(e) => setParam("replicas", Math.max(1, parseInt(e.target.value) || 1))}
              disabled={disabled}
            />
          </label>
          {selectedNode.data.type === "cache" && (
            <label>
              Hit ratio
              <input
                type="number"
                step={0.05}
                min={0}
                max={1}
                className="field"
                value={selectedNode.data.params?.hit_ratio ?? 0.8}
                onChange={(e) => setParam("hit_ratio", parseFloat(e.target.value))}
                disabled={disabled}
              />
            </label>
          )}
          {selectedNode.data.type !== "client" && (
            <button
              type="button"
              className="btn btn-sm btn-tone-danger"
              onClick={deleteSelected}
              disabled={disabled}
              aria-label={`Delete ${selectedNode.data.label}`}
            >
              <Trash2 size={13} />
            </button>
          )}
        </div>
      )}

      <div className="coding-results design-results" aria-live="polite">
        {analyzeError && <div className="interview-error">{analyzeError}</div>}
        {!analysis ? (
          !analyzeError && <p className="note">Analyze your design to see whether it meets the requirements.</p>
        ) : (
          <>
            <div className="design-metrics">
              <div>
                <span>p99 latency</span>
                {summary.end_to_end_latency_p99_ms != null ? `${Math.round(summary.end_to_end_latency_p99_ms)} ms` : "overloaded"}
              </div>
              <div>
                <span>Max throughput</span>
                {summary.max_sustainable_rps != null ? `${Math.round(summary.max_sustainable_rps).toLocaleString()} rps` : "—"}
              </div>
              <div>
                <span>Bottleneck</span>
                {summary.bottleneck_node ?? "—"}
              </div>
            </div>
            {analysis.findings.length === 0 ? (
              <div className="coding-results-summary pass">No problems found: the design meets its requirements.</div>
            ) : (
              <>
                <div className="coding-results-summary fail">
                  {analysis.findings.length} problem{analysis.findings.length === 1 ? "" : "s"} found
                </div>
                {analysis.findings.map((f, i) => (
                  <div key={i} className={`coding-result ${f.severity >= 7 ? "fail" : "warn"}`}>
                    <div className="coding-result-title">{f.type.replace("_", " ")}</div>
                    <div className="coding-result-body">{f.message}</div>
                  </div>
                ))}
              </>
            )}
          </>
        )}
      </div>

      <textarea
        className="field design-explanation"
        rows={2}
        value={explanation}
        onChange={(e) => onExplanationChange(e.target.value)}
        placeholder="Briefly explain your design choices (optional)..."
        disabled={disabled}
        aria-label="Explain your design"
      />

      {error && <div className="interview-error">{error}</div>}

      <div className="coding-actions">
        <button type="button" className="btn btn-secondary" onClick={runAnalyze} disabled={disabled || busy}>
          <Activity size={15} />
          {analyzing ? "Analyzing..." : "Analyze"}
        </button>
        <button type="button" className="submit-answer-button" onClick={onSubmit} disabled={disabled || busy}>
          <Send size={16} />
          {submitting ? "Grading..." : "Submit Design"}
        </button>
      </div>
    </div>
  );
}
