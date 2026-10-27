import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ReactFlow, Background, Controls,
  addEdge, applyNodeChanges, applyEdgeChanges,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { ChevronLeft, Plus, Save, Activity, Zap, ShieldAlert, MessageSquareText, FlagTriangleRight } from "lucide-react";

import {
  getCatalog, getSubtopics, getPrompts, startDesignSession, saveVersion,
  analyzeVersion, simulateVersion, runResilience, interviewerNext, respond, getDesignReport,
} from "../services/whiteboard";
import Card from "../components/shared/Card";
import Badge from "../components/shared/Badge";
import DesignNode from "../components/DesignNode";
import { flowToGraph, graphToFlow, newEdge, newNode, withParam } from "../services/designGraph";
import "./WhiteboardPage.css";

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
      <div className="wb-browser-bar">
        <div className="tab-row scroll">
          <button className={`tab-btn ${active === "all" ? "active" : ""}`} onClick={() => setActive("all")}>All</button>
          {subtopics.map((s) => (
            <button key={s.id} className={`tab-btn ${active === s.id ? "active" : ""}`} onClick={() => setActive(s.id)}>{s.name}</button>
          ))}
        </div>
        <label className="wb-sim-toggle">
          <input type="checkbox" checked={simOnly} onChange={(e) => setSimOnly(e.target.checked)} />
          Simulatable only
        </label>
      </div>

      <div className="grid grid-3">
        {prompts.map((p) => (
          <Card key={p.id} hoverable={p.simulatable} onClick={p.simulatable ? () => onSelect(p.id) : undefined} className={p.simulatable ? "" : "wb-prompt-card disabled"}>
            <div className="wb-prompt-badges">
              <Badge difficulty={p.difficulty}>{p.difficulty}</Badge>
              {p.simulatable && <Badge tone="info">Executable</Badge>}
            </div>
            <div className="wb-prompt-title">{p.title}</div>
            <p className="wb-prompt-scenario">{p.scenario}</p>
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
    const { nodes, edges } = graphToFlow(graph, setSelectedId);
    setRfNodes(nodes);
    setRfEdges(edges);
    setAnalysis(null);
  };

  const toGraphJson = useCallback(() => flowToGraph(rfNodes, rfEdges), [rfNodes, rfEdges]);

  const onNodesChange = useCallback((changes) => setRfNodes((nds) => applyNodeChanges(changes, nds)), []);
  const onEdgesChange = useCallback((changes) => setRfEdges((eds) => applyEdgeChanges(changes, eds)), []);
  const onConnect = useCallback((params) => setRfEdges((eds) => addEdge(newEdge(params), eds)), []);

  const addNode = () => {
    setRfNodes((nds) => [...nds, newNode(catalog, addType, setSelectedId)]);
  };

  const updateSelectedParam = (key, value) => {
    setRfNodes((nds) => withParam(nds, selectedId, key, value));
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
        <button onClick={onBack} className="text-btn back-btn" style={{ marginBottom: 16 }}>
          <ChevronLeft size={16} /> Back to prompts
        </button>
        <h2 className="wb-report-title">Final Report — {session.prompt.title}</h2>
        <div className="grid grid-3">
          <Card><div className="stat-label">SLOs Satisfied</div><div className={`wb-report-value ${report.slo_satisfied ? "text-success" : "text-danger"}`}>{report.slo_satisfied ? "Yes" : "No"}</div></Card>
          <Card><div className="stat-label">Resilience</div><div className="wb-report-value">{report.resilience.resilience_pct}%</div></Card>
          <Card><div className="stat-label">Cost Efficiency vs Reference</div><div className="wb-report-value">{report.cost_efficiency ?? "—"}x</div></Card>
        </div>
        <p className="note" style={{ marginTop: 16 }}>{report.revisions} version(s) submitted.</p>
      </div>
    );
  }

  return (
    <div>
      <button onClick={onBack} className="text-btn back-btn">
        <ChevronLeft size={16} /> All prompts
      </button>

      <div className="wb-header">
        <div>
          <h2>{session.prompt.title}</h2>
          <p>{session.prompt.scenario}</p>
        </div>
        <div className="wb-requirements">
          peak {session.requirements.peak_rps.toLocaleString()} rps · p99 SLO {session.requirements.p99_slo_ms}ms
        </div>
      </div>

      <div className="grid grid-split">
        <div>
          <div className="wb-toolbar">
            <select value={addType} onChange={(e) => setAddType(e.target.value)} className="field" aria-label="Component type">
              {catalog.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
            </select>
            <button onClick={addNode} className="btn btn-secondary btn-sm">
              <Plus size={13} /> Add
            </button>
            <button disabled={busy} onClick={saveAndAnalyze} className="btn btn-primary btn-sm">
              <Save size={13} /> Save &amp; Analyze
            </button>
            <button disabled={busy || !versionId} onClick={runSim} className="btn btn-secondary btn-sm">
              <Activity size={13} /> Simulate
            </button>
            <button disabled={busy || !versionId} onClick={runResilienceSuite} className="btn btn-secondary btn-sm">
              <ShieldAlert size={13} /> Resilience
            </button>
          </div>

          <div className="flow-canvas wb-canvas">
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
            <Card className="wb-result-card">
              <div className="metric-row" style={{ marginBottom: 12 }}>
                <div><div className="metric-label">p99 latency</div><div className="metric-value">{analysis.summary.end_to_end_latency_p99_ms ?? "—"} ms</div></div>
                <div><div className="metric-label">Max sustainable RPS</div><div className="metric-value">{analysis.summary.max_sustainable_rps ?? "—"}</div></div>
                <div><div className="metric-label">Capacity runway</div><div className="metric-value">{analysis.summary.capacity_runway_months ?? "—"} mo</div></div>
              </div>
              <div className="section-label">Findings ({analysis.findings.length})</div>
              {analysis.findings.length === 0 && <p className="note text-success">No issues found — the design satisfies its requirements.</p>}
              {analysis.findings.map((f, i) => (
                <div key={i} className="list-row">
                  <span>{f.message}</span>
                  <Badge tone={f.severity >= 7 ? "danger" : "warning"}>{f.type}</Badge>
                </div>
              ))}
            </Card>
          )}

          {simResult && (
            <Card className="wb-result-card">
              <div className="section-label">Discrete-Event Simulation</div>
              <div className="metric-row">
                <div><div className="metric-label">p50</div><div className="metric-value">{simResult.end_to_end_ms.p50} ms</div></div>
                <div><div className="metric-label">p95</div><div className="metric-value">{simResult.end_to_end_ms.p95} ms</div></div>
                <div><div className="metric-label">p99</div><div className="metric-value">{simResult.end_to_end_ms.p99} ± {simResult.end_to_end_ms.p99_ci95} ms</div></div>
              </div>
            </Card>
          )}

          {scenarioResult && (
            <Card className="wb-result-card">
              {scenarioResult.resilienceResult ? (
                <>
                  <div className="section-label">
                    Resilience: {scenarioResult.resilienceResult.resilience_pct}% ({scenarioResult.resilienceResult.scenarios_survived}/{scenarioResult.resilienceResult.scenarios_run} scenarios survived)
                  </div>
                  {scenarioResult.resilienceResult.results.map((r, i) => (
                    <div key={i} className={`wb-resilience-line ${r.survived ? "text-success" : "text-danger"}`}>
                      {r.survived ? "✓" : "✗"} {r.scenario.type}{r.scenario.node_id ? ` (${r.scenario.node_id})` : ""}
                    </div>
                  ))}
                </>
              ) : (
                <>
                  <div className="section-label">Scenario result</div>
                  {scenarioResult.findings.length === 0 ? (
                    <p className="note text-success">Design survives this scenario.</p>
                  ) : scenarioResult.findings.map((f, i) => (
                    <div key={i} className="wb-result-line">{f.message}</div>
                  ))}
                </>
              )}
            </Card>
          )}
        </div>

        <div className="wb-side">
          {selectedNode && (
            <Card>
              <div className="section-label">{selectedNode.data.label}</div>
              <label className="field-label" htmlFor="wb-replicas">Replicas</label>
              <input
                id="wb-replicas" type="number" min={0} value={selectedNode.data.params?.replicas ?? 1}
                onChange={(e) => updateSelectedParam("replicas", parseInt(e.target.value) || 0)}
                className="field wb-param"
              />
              {selectedNode.data.type === "cache" && (
                <>
                  <label className="field-label" htmlFor="wb-hit-ratio">Hit ratio</label>
                  <input
                    id="wb-hit-ratio" type="number" step={0.05} min={0} max={1} value={selectedNode.data.params?.hit_ratio ?? 0.8}
                    onChange={(e) => updateSelectedParam("hit_ratio", parseFloat(e.target.value))}
                    className="field wb-param"
                  />
                </>
              )}
              {selectedNode.data.type !== "client" && (
                <button onClick={deleteSelected} className="btn btn-sm btn-block btn-tone-danger">
                  Delete component
                </button>
              )}
            </Card>
          )}

          <Card>
            <div className="section-label">Failure Scenario</div>
            <select value={scenarioType} onChange={(e) => setScenarioType(e.target.value)} className="field" style={{ marginBottom: 8 }} aria-label="Failure scenario">
              {SCENARIOS.map((s) => <option key={s.type} value={s.type}>{s.label}</option>)}
            </select>
            {SCENARIOS.find((s) => s.type === scenarioType)?.needsNode && (
              <select value={scenarioNode} onChange={(e) => setScenarioNode(e.target.value)} className="field" style={{ marginBottom: 8 }} aria-label="Target node">
                <option value="">Select a node...</option>
                {rfNodes.filter((n) => n.data.type !== "client").map((n) => <option key={n.id} value={n.id}>{n.data.label}</option>)}
              </select>
            )}
            <button disabled={busy} onClick={runScenario} className="btn btn-sm btn-block btn-tone-warning">
              <Zap size={13} /> Run scenario
            </button>
          </Card>

          <Card>
            <div className="section-label with-icon">
              <MessageSquareText size={13} /> Interviewer
            </div>
            <div className="wb-dialogue">
              {dialogue.map((d, i) => (
                <div key={i} className={`wb-dialogue-line ${d.role === "interviewer" ? "" : "candidate"}`}>
                  <strong>{d.role === "interviewer" ? "Interviewer: " : "You: "}</strong>{d.text}
                </div>
              ))}
            </div>
            <button onClick={askInterviewer} className="btn btn-sm btn-block btn-tone-neutral" style={{ marginBottom: 8 }}>
              Ask next question
            </button>
            <div className="row" style={{ gap: 6 }}>
              <input value={reply} onChange={(e) => setReply(e.target.value)} placeholder="Your response..." className="field" style={{ flex: 1 }} aria-label="Your response" />
              <button onClick={sendReply} className="btn btn-primary btn-sm">Send</button>
            </div>
          </Card>

          <button onClick={finish} className="btn btn-block btn-tone-success">
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
