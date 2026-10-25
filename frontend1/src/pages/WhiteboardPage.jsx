import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ReactFlow, Background, Controls, Handle, Position,
  addEdge, applyNodeChanges, applyEdgeChanges, MarkerType,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { ChevronLeft, Plus, Save, Activity, Zap, ShieldAlert, MessageSquareText, FlagTriangleRight } from "lucide-react";

import {
  getCatalog, getSubtopics, getPrompts, startDesignSession, saveVersion,
  analyzeVersion, simulateVersion, runResilience, interviewerNext, respond, getDesignReport,
} from "../services/whiteboard";
import Card from "../components/shared/Card";
import Badge from "../components/shared/Badge";

function utilColor(u) {
  if (u == null) return "var(--border)";
  if (u >= 1) return "var(--danger)";
  if (u >= 0.8) return "var(--warning)";
  return "var(--success)";
}

function DesignNode({ data }) {
  const m = data.metrics;
  return (
    <div
      onClick={() => data.onSelect(data.id)}
      style={{
        padding: "10px 14px", borderRadius: 12, minWidth: 150, cursor: "pointer",
        background: "var(--card)",
        border: `2px solid ${m ? utilColor(m.utilisation) : "var(--border)"}`,
        boxShadow: data.selected ? "0 0 0 2px var(--primary)" : "none",
      }}
    >
      <Handle type="target" position={Position.Left} style={{ opacity: 0 }} />
      <div style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>{data.type}</div>
      <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 4 }}>{data.label}</div>
      <div style={{ fontSize: 10.5, color: "var(--muted)" }}>x{data.replicas}</div>
      {m && (
        <div style={{ fontSize: 10.5, fontWeight: 700, color: utilColor(m.utilisation), marginTop: 4 }}>
          {m.utilisation != null ? `${Math.round(m.utilisation * 100)}% util` : "—"}
          {m.saturated && " · SATURATED"}
        </div>
      )}
      <Handle type="source" position={Position.Right} style={{ opacity: 0 }} />
    </div>
  );
}

const nodeTypes = { design: DesignNode };

function PromptBrowser({ onSelect }) {
  const [subtopics, setSubtopics] = useState([]);
  const [active, setActive] = useState("all");
  const [prompts, setPrompts] = useState([]);
  const [simOnly, setSimOnly] = useState(true);

  useEffect(() => { getSubtopics().then(setSubtopics); }, []);

  useEffect(() => {
    getPrompts({ subtopic_id: active === "all" ? undefined : active, simulatable_only: simOnly }).then(setPrompts);
  }, [active, simOnly]);

  return (
    <>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
        <div className="tab-row" style={{ marginBottom: 0 }}>
          <button className={`tab-btn ${active === "all" ? "active" : ""}`} onClick={() => setActive("all")}>All</button>
          {subtopics.map((s) => (
            <button key={s.id} className={`tab-btn ${active === s.id ? "active" : ""}`} onClick={() => setActive(s.id)}>{s.name}</button>
          ))}
        </div>
        <label style={{ fontSize: 12.5, color: "var(--muted)", display: "flex", alignItems: "center", gap: 6, whiteSpace: "nowrap" }}>
          <input type="checkbox" checked={simOnly} onChange={(e) => setSimOnly(e.target.checked)} />
          Simulatable only
        </label>
      </div>

      <div className="grid grid-3">
        {prompts.map((p) => (
          <Card key={p.id} hoverable={p.simulatable} onClick={p.simulatable ? () => onSelect(p.id) : undefined} style={{ opacity: p.simulatable ? 1 : 0.6 }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
              <Badge difficulty={p.difficulty}>{p.difficulty}</Badge>
              {p.simulatable && <Badge tone="info">Executable</Badge>}
            </div>
            <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 6 }}>{p.title}</div>
            <p style={{ fontSize: 12.5, color: "var(--muted)", lineHeight: 1.5 }}>{p.scenario}</p>
          </Card>
        ))}
      </div>
    </>
  );
}

const SCENARIOS = [
  { type: "kill_node", label: "Kill a node", needsNode: true },
  { type: "lose_replica", label: "Lose a replica", needsNode: true },
  { type: "cold_cache", label: "Cold cache", needsNode: true },
  { type: "latency_injection", label: "Inject latency", needsNode: true },
  { type: "traffic_spike", label: "Traffic spike (2x)", needsNode: false },
];

function DesignWorkspace({ promptId, onBack }) {
  const [catalog, setCatalog] = useState([]);
  const [session, setSession] = useState(null);
  const [versionId, setVersionId] = useState(null);
  const [rfNodes, setRfNodes] = useState([]);
  const [rfEdges, setRfEdges] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [addType, setAddType] = useState("api_service");
  const [analysis, setAnalysis] = useState(null);
  const [scenarioType, setScenarioType] = useState("kill_node");
  const [scenarioNode, setScenarioNode] = useState("");
  const [scenarioResult, setScenarioResult] = useState(null);
  const [simResult, setSimResult] = useState(null);
  const [dialogue, setDialogue] = useState([]);
  const [reply, setReply] = useState("");
  const [report, setReport] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { getCatalog().then(setCatalog); }, []);

  useEffect(() => {
    startDesignSession(promptId).then((data) => {
      setSession(data);
      setVersionId(data.version.id);
      loadGraph(data.version.graph);
    });
  }, [promptId]);

  const loadGraph = (graph) => {
    const nodes = graph.nodes.map((n, i) => ({
      id: n.id,
      type: "design",
      position: n.position || { x: (i % 4) * 220, y: Math.floor(i / 4) * 140 },
      data: { ...n, replicas: n.params?.replicas ?? 1, onSelect: setSelectedId },
    }));
    const edges = graph.edges.map((e) => ({
      id: `${e.src}-${e.dst}`,
      source: e.src,
      target: e.dst,
      label: e.fraction === "miss" ? "miss" : String(e.fraction),
      style: { stroke: e.kind === "async" ? "var(--info)" : "var(--border)" },
      markerEnd: { type: MarkerType.ArrowClosed, color: "var(--muted)" },
    }));
    setRfNodes(nodes);
    setRfEdges(edges);
    setAnalysis(null);
  };

  const toGraphJson = useCallback(() => ({
    nodes: rfNodes.map((n) => ({ id: n.id, type: n.data.type, label: n.data.label, params: n.data.params })),
    edges: rfEdges.map((e) => ({
      src: e.source, dst: e.target,
      fraction: e.label === "miss" ? "miss" : parseFloat(e.label) || 1.0,
      kind: e.style?.stroke === "var(--info)" ? "async" : "sync",
    })),
  }), [rfNodes, rfEdges]);

  const onNodesChange = useCallback((changes) => setRfNodes((nds) => applyNodeChanges(changes, nds)), []);
  const onEdgesChange = useCallback((changes) => setRfEdges((eds) => applyEdgeChanges(changes, eds)), []);
  const onConnect = useCallback((params) => setRfEdges((eds) => addEdge({
    ...params,
    label: "1.0",
    style: { stroke: "var(--border)" },
    markerEnd: { type: MarkerType.ArrowClosed, color: "var(--muted)" },
  }, eds)), []);

  const addNode = () => {
    const def = catalog.find((c) => c.id === addType);
    const id = `${addType}_${Date.now().toString(36)}`;
    setRfNodes((nds) => [
      ...nds,
      {
        id, type: "design",
        position: { x: 80 + Math.random() * 300, y: 80 + Math.random() * 240 },
        data: { id, type: addType, label: def?.label || addType, params: { replicas: 1, ...(def?.defaults?.hit_ratio !== undefined ? { hit_ratio: def.defaults.hit_ratio } : {}) }, replicas: 1, onSelect: setSelectedId },
      },
    ]);
  };

  const updateSelectedParam = (key, value) => {
    setRfNodes((nds) => nds.map((n) => n.id === selectedId ? { ...n, data: { ...n.data, params: { ...n.data.params, [key]: value }, replicas: key === "replicas" ? value : n.data.replicas } } : n));
  };

  const deleteSelected = () => {
    setRfNodes((nds) => nds.filter((n) => n.id !== selectedId));
    setRfEdges((eds) => eds.filter((e) => e.source !== selectedId && e.target !== selectedId));
    setSelectedId(null);
  };

  const saveAndAnalyze = async () => {
    setBusy(true);
    try {
      const graph = toGraphJson();
      const v = await saveVersion(session.session_id, graph);
      setVersionId(v.version_id);
      const result = await analyzeVersion(v.version_id, {});
      setAnalysis(result);
      setRfNodes((nds) => nds.map((n) => ({ ...n, data: { ...n.data, metrics: result.node_metrics[n.id] } })));
      setScenarioResult(null);
    } finally {
      setBusy(false);
    }
  };

  const runScenario = async () => {
    if (!versionId) return;
    setBusy(true);
    try {
      const scenario = scenarioType === "traffic_spike"
        ? { type: "traffic_spike", multiplier: 2.0 }
        : scenarioType === "lose_replica"
          ? { type: "lose_replica", node_id: scenarioNode, count: 1 }
          : scenarioType === "latency_injection"
            ? { type: "latency_injection", node_id: scenarioNode, extra_ms: 150 }
            : { type: scenarioType, node_id: scenarioNode };

      const result = await analyzeVersion(versionId, { scenario });
      setScenarioResult(result);
    } finally {
      setBusy(false);
    }
  };

  const runSim = async () => {
    if (!versionId) return;
    setBusy(true);
    try {
      const result = await simulateVersion(versionId, { n_requests: 1500, replications: 2 });
      setSimResult(result);
    } finally {
      setBusy(false);
    }
  };

  const runResilienceSuite = async () => {
    if (!versionId) return;
    setBusy(true);
    try {
      const result = await runResilience(versionId);
      setScenarioResult({ resilienceResult: result });
    } finally {
      setBusy(false);
    }
  };

  const askInterviewer = async () => {
    const q = await interviewerNext(session.session_id);
    setDialogue((d) => [...d, { role: "interviewer", text: q.question || q.message }]);
  };

  const sendReply = async () => {
    if (!reply.trim()) return;
    setDialogue((d) => [...d, { role: "candidate", text: reply }]);
    await respond(session.session_id, reply);
    setReply("");
  };

  const finish = async () => {
    const r = await getDesignReport(session.session_id);
    setReport(r);
  };

  const selectedNode = rfNodes.find((n) => n.id === selectedId);

  const nodesWithSelection = useMemo(
    () => rfNodes.map((n) => ({ ...n, data: { ...n.data, selected: n.id === selectedId } })),
    [rfNodes, selectedId],
  );

  if (!session) return <p className="spinner-text">Starting session...</p>;

  if (report) {
    return (
      <div>
        <button onClick={onBack} style={{ background: "none", border: "none", color: "var(--muted)", display: "flex", alignItems: "center", gap: 6, marginBottom: 16 }}>
          <ChevronLeft size={16} /> Back to prompts
        </button>
        <h2 style={{ fontSize: 20, marginBottom: 16 }}>Final Report — {session.prompt.title}</h2>
        <div className="grid grid-3">
          <Card><div style={{ color: "var(--muted)", fontSize: 12 }}>SLOs Satisfied</div><div style={{ fontSize: 24, fontWeight: 700, color: report.slo_satisfied ? "var(--success)" : "var(--danger)" }}>{report.slo_satisfied ? "Yes" : "No"}</div></Card>
          <Card><div style={{ color: "var(--muted)", fontSize: 12 }}>Resilience</div><div style={{ fontSize: 24, fontWeight: 700 }}>{report.resilience.resilience_pct}%</div></Card>
          <Card><div style={{ color: "var(--muted)", fontSize: 12 }}>Cost Efficiency vs Reference</div><div style={{ fontSize: 24, fontWeight: 700 }}>{report.cost_efficiency ?? "—"}x</div></Card>
        </div>
        <p style={{ color: "var(--muted)", fontSize: 13, marginTop: 16 }}>{report.revisions} version(s) submitted.</p>
      </div>
    );
  }

  return (
    <div>
      <button onClick={onBack} style={{ background: "none", border: "none", color: "var(--muted)", display: "flex", alignItems: "center", gap: 6, marginBottom: 12 }}>
        <ChevronLeft size={16} /> All prompts
      </button>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 14 }}>
        <div>
          <h2 style={{ fontSize: 19 }}>{session.prompt.title}</h2>
          <p style={{ color: "var(--muted)", fontSize: 13, maxWidth: 560 }}>{session.prompt.scenario}</p>
        </div>
        <div style={{ fontSize: 12, color: "var(--muted)", textAlign: "right" }}>
          peak {session.requirements.peak_rps.toLocaleString()} rps · p99 SLO {session.requirements.p99_slo_ms}ms
        </div>
      </div>

      <div className="grid" style={{ gridTemplateColumns: "2.2fr 1fr", gap: 16, alignItems: "start" }}>
        <div>
          <div style={{ display: "flex", gap: 8, marginBottom: 10, flexWrap: "wrap" }}>
            <select value={addType} onChange={(e) => setAddType(e.target.value)} style={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8, color: "var(--text)", padding: "6px 10px", fontSize: 12.5 }}>
              {catalog.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
            </select>
            <button onClick={addNode} style={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8, color: "var(--text)", padding: "6px 12px", fontSize: 12.5, display: "flex", alignItems: "center", gap: 6 }}>
              <Plus size={13} /> Add
            </button>
            <button disabled={busy} onClick={saveAndAnalyze} style={{ background: "var(--primary)", border: "none", borderRadius: 8, color: "white", padding: "6px 14px", fontSize: 12.5, fontWeight: 700, display: "flex", alignItems: "center", gap: 6 }}>
              <Save size={13} /> Save &amp; Analyze
            </button>
            <button disabled={busy || !versionId} onClick={runSim} style={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8, color: "var(--text)", padding: "6px 12px", fontSize: 12.5, display: "flex", alignItems: "center", gap: 6 }}>
              <Activity size={13} /> Simulate
            </button>
            <button disabled={busy || !versionId} onClick={runResilienceSuite} style={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8, color: "var(--text)", padding: "6px 12px", fontSize: 12.5, display: "flex", alignItems: "center", gap: 6 }}>
              <ShieldAlert size={13} /> Resilience
            </button>
          </div>

          <div style={{ height: 460, border: "1px solid var(--border)", borderRadius: 16, background: "var(--card)" }}>
            <ReactFlow
              nodes={nodesWithSelection} edges={rfEdges} nodeTypes={nodeTypes}
              onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onConnect={onConnect}
              fitView proOptions={{ hideAttribution: true }}
            >
              <Background color="var(--border)" gap={20} />
              <Controls />
            </ReactFlow>
          </div>

          {analysis && (
            <Card style={{ marginTop: 14 }}>
              <div style={{ display: "flex", gap: 24, marginBottom: 12, flexWrap: "wrap" }}>
                <div><div style={{ fontSize: 11, color: "var(--muted)" }}>p99 latency</div><div style={{ fontWeight: 700 }}>{analysis.summary.end_to_end_latency_p99_ms ?? "—"} ms</div></div>
                <div><div style={{ fontSize: 11, color: "var(--muted)" }}>Max sustainable RPS</div><div style={{ fontWeight: 700 }}>{analysis.summary.max_sustainable_rps ?? "—"}</div></div>
                <div><div style={{ fontSize: 11, color: "var(--muted)" }}>Capacity runway</div><div style={{ fontWeight: 700 }}>{analysis.summary.capacity_runway_months ?? "—"} mo</div></div>
              </div>
              <div style={{ fontSize: 12, fontWeight: 700, color: "var(--muted)", textTransform: "uppercase", marginBottom: 8 }}>Findings ({analysis.findings.length})</div>
              {analysis.findings.length === 0 && <p style={{ fontSize: 13, color: "var(--success)" }}>No issues found — the design satisfies its requirements.</p>}
              {analysis.findings.map((f, i) => (
                <div key={i} style={{ fontSize: 12.5, padding: "6px 0", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between" }}>
                  <span>{f.message}</span>
                  <Badge tone={f.severity >= 7 ? "danger" : "warning"}>{f.type}</Badge>
                </div>
              ))}
            </Card>
          )}

          {simResult && (
            <Card style={{ marginTop: 14 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: "var(--muted)", textTransform: "uppercase", marginBottom: 8 }}>Discrete-Event Simulation</div>
              <div style={{ display: "flex", gap: 24 }}>
                <div><div style={{ fontSize: 11, color: "var(--muted)" }}>p50</div><div style={{ fontWeight: 700 }}>{simResult.end_to_end_ms.p50} ms</div></div>
                <div><div style={{ fontSize: 11, color: "var(--muted)" }}>p95</div><div style={{ fontWeight: 700 }}>{simResult.end_to_end_ms.p95} ms</div></div>
                <div><div style={{ fontSize: 11, color: "var(--muted)" }}>p99</div><div style={{ fontWeight: 700 }}>{simResult.end_to_end_ms.p99} ± {simResult.end_to_end_ms.p99_ci95} ms</div></div>
              </div>
            </Card>
          )}

          {scenarioResult && (
            <Card style={{ marginTop: 14 }}>
              {scenarioResult.resilienceResult ? (
                <>
                  <div style={{ fontSize: 12, fontWeight: 700, color: "var(--muted)", textTransform: "uppercase", marginBottom: 8 }}>
                    Resilience: {scenarioResult.resilienceResult.resilience_pct}% ({scenarioResult.resilienceResult.scenarios_survived}/{scenarioResult.resilienceResult.scenarios_run} scenarios survived)
                  </div>
                  {scenarioResult.resilienceResult.results.map((r, i) => (
                    <div key={i} style={{ fontSize: 12, padding: "4px 0", color: r.survived ? "var(--success)" : "var(--danger)" }}>
                      {r.survived ? "✓" : "✗"} {r.scenario.type}{r.scenario.node_id ? ` (${r.scenario.node_id})` : ""}
                    </div>
                  ))}
                </>
              ) : (
                <>
                  <div style={{ fontSize: 12, fontWeight: 700, color: "var(--muted)", textTransform: "uppercase", marginBottom: 8 }}>Scenario result</div>
                  {scenarioResult.findings.length === 0 ? (
                    <p style={{ fontSize: 13, color: "var(--success)" }}>Design survives this scenario.</p>
                  ) : scenarioResult.findings.map((f, i) => (
                    <div key={i} style={{ fontSize: 12.5, padding: "4px 0" }}>{f.message}</div>
                  ))}
                </>
              )}
            </Card>
          )}
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {selectedNode && (
            <Card>
              <div style={{ fontSize: 12, fontWeight: 700, color: "var(--muted)", textTransform: "uppercase", marginBottom: 10 }}>{selectedNode.data.label}</div>
              <label style={{ fontSize: 12, color: "var(--muted)" }}>Replicas</label>
              <input
                type="number" min={0} value={selectedNode.data.params?.replicas ?? 1}
                onChange={(e) => updateSelectedParam("replicas", parseInt(e.target.value) || 0)}
                style={{ width: "100%", background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 8, color: "var(--text)", padding: "6px 10px", marginBottom: 10, marginTop: 4 }}
              />
              {selectedNode.data.type === "cache" && (
                <>
                  <label style={{ fontSize: 12, color: "var(--muted)" }}>Hit ratio</label>
                  <input
                    type="number" step={0.05} min={0} max={1} value={selectedNode.data.params?.hit_ratio ?? 0.8}
                    onChange={(e) => updateSelectedParam("hit_ratio", parseFloat(e.target.value))}
                    style={{ width: "100%", background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 8, color: "var(--text)", padding: "6px 10px", marginBottom: 10, marginTop: 4 }}
                  />
                </>
              )}
              {selectedNode.data.type !== "client" && (
                <button onClick={deleteSelected} style={{ width: "100%", background: "var(--danger-soft)", border: "1px solid var(--danger)", color: "var(--danger)", borderRadius: 8, padding: "7px 0", fontSize: 12.5, fontWeight: 600 }}>
                  Delete component
                </button>
              )}
            </Card>
          )}

          <Card>
            <div style={{ fontSize: 12, fontWeight: 700, color: "var(--muted)", textTransform: "uppercase", marginBottom: 10 }}>Failure Scenario</div>
            <select value={scenarioType} onChange={(e) => setScenarioType(e.target.value)} style={{ width: "100%", background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 8, color: "var(--text)", padding: "7px 10px", marginBottom: 8, fontSize: 12.5 }}>
              {SCENARIOS.map((s) => <option key={s.type} value={s.type}>{s.label}</option>)}
            </select>
            {SCENARIOS.find((s) => s.type === scenarioType)?.needsNode && (
              <select value={scenarioNode} onChange={(e) => setScenarioNode(e.target.value)} style={{ width: "100%", background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 8, color: "var(--text)", padding: "7px 10px", marginBottom: 8, fontSize: 12.5 }}>
                <option value="">Select a node...</option>
                {rfNodes.filter((n) => n.data.type !== "client").map((n) => <option key={n.id} value={n.id}>{n.data.label}</option>)}
              </select>
            )}
            <button disabled={busy} onClick={runScenario} style={{ width: "100%", background: "var(--warning-soft)", border: "1px solid var(--warning)", color: "var(--warning)", borderRadius: 8, padding: "7px 0", fontSize: 12.5, fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}>
              <Zap size={13} /> Run scenario
            </button>
          </Card>

          <Card>
            <div style={{ fontSize: 12, fontWeight: 700, color: "var(--muted)", textTransform: "uppercase", marginBottom: 10, display: "flex", alignItems: "center", gap: 6 }}>
              <MessageSquareText size={13} /> Interviewer
            </div>
            <div style={{ maxHeight: 160, overflowY: "auto", marginBottom: 8 }}>
              {dialogue.map((d, i) => (
                <div key={i} style={{ fontSize: 12.5, marginBottom: 8, color: d.role === "interviewer" ? "var(--text)" : "var(--primary)" }}>
                  <strong>{d.role === "interviewer" ? "Interviewer: " : "You: "}</strong>{d.text}
                </div>
              ))}
            </div>
            <button onClick={askInterviewer} style={{ width: "100%", background: "var(--card-hover)", border: "1px solid var(--border)", color: "var(--text)", borderRadius: 8, padding: "7px 0", fontSize: 12.5, marginBottom: 8 }}>
              Ask next question
            </button>
            <div style={{ display: "flex", gap: 6 }}>
              <input value={reply} onChange={(e) => setReply(e.target.value)} placeholder="Your response..." style={{ flex: 1, background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 8, color: "var(--text)", padding: "6px 10px", fontSize: 12.5 }} />
              <button onClick={sendReply} style={{ background: "var(--primary)", border: "none", color: "white", borderRadius: 8, padding: "6px 12px", fontSize: 12.5 }}>Send</button>
            </div>
          </Card>

          <button onClick={finish} style={{ background: "var(--success-soft)", border: "1px solid var(--success)", color: "var(--success)", borderRadius: 10, padding: "10px 0", fontWeight: 700, fontSize: 13, display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}>
            <FlagTriangleRight size={14} /> Finish &amp; Get Report
          </button>
        </div>
      </div>
    </div>
  );
}

export default function WhiteboardPage() {
  const [promptId, setPromptId] = useState(null);

  return (
    <div className="page-content">
      <div className="page-header">
        <h1>Executable System-Design Whiteboard</h1>
        <p>Draw an architecture and actually run it — queueing theory, failure injection, and bottleneck detection.</p>
      </div>

      {promptId ? (
        <DesignWorkspace promptId={promptId} onBack={() => setPromptId(null)} />
      ) : (
        <PromptBrowser onSelect={setPromptId} />
      )}
    </div>
  );
}
