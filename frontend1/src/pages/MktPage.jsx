import { useCallback, useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { ReactFlow, Background, Handle, Position } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Send, RotateCcw, Info } from "lucide-react";

import { getConceptGraph, startMktSession, answerMktTurn } from "../services/mkt";
import Card from "../components/shared/Card";
import ProgressBar from "../components/shared/ProgressBar";

const STATE_COLOR = { robust: "var(--success)", memorised: "var(--warning)", misconceived: "var(--danger)", absent: "var(--muted)" };
const STATE_LABEL = { robust: "Robust", memorised: "Memorised", misconceived: "Misconceived", absent: "Absent" };
const PROBE_LABEL = {
  base: "Canonical question",
  mr_paraphrase: "Metamorphic: paraphrase",
  mr_constraint: "Metamorphic: changed constraint",
  mr_inversion: "Metamorphic: inversion",
  mr_pushback: "Metamorphic: interviewer pushback",
};

function ConceptNode({ data }) {
  return (
    <div
      style={{
        padding: "10px 14px", borderRadius: 12, minWidth: 150,
        background: "var(--card)",
        border: `1.5px solid ${data.observations > 0 ? STATE_COLOR[data.most_likely] : "var(--border)"}`,
      }}
    >
      <Handle type="target" position={Position.Top} style={{ opacity: 0 }} />
      <div style={{ fontWeight: 600, fontSize: 12.5, marginBottom: 4 }}>{data.name}</div>
      {data.observations > 0 ? (
        <div style={{ fontSize: 10.5, color: STATE_COLOR[data.most_likely], fontWeight: 700 }}>
          {STATE_LABEL[data.most_likely]} &middot; {Math.round(data.confidence * 100)}%
        </div>
      ) : (
        <div style={{ fontSize: 10.5, color: "var(--muted)", fontWeight: 600 }}>Not yet tested</div>
      )}
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0 }} />
    </div>
  );
}

const nodeTypes = { concept: ConceptNode };

function ConceptMap({ graph }) {
  const { nodes, edges } = useMemo(() => {
    if (!graph) return { nodes: [], edges: [] };

    const depth = {};
    const children = {};
    graph.nodes.forEach((n) => (children[n.id] = []));
    graph.edges.forEach((e) => children[e.source]?.push(e.target));

    const parentsOf = {};
    graph.nodes.forEach((n) => (parentsOf[n.id] = []));
    graph.edges.forEach((e) => parentsOf[e.target]?.push(e.source));

    const order = [];
    const visited = new Set();
    const visit = (id) => {
      if (visited.has(id)) return;
      const parents = parentsOf[id] || [];
      parents.forEach(visit);
      visited.add(id);
      depth[id] = parents.length ? Math.max(...parents.map((p) => depth[p])) + 1 : 0;
      order.push(id);
    };
    graph.nodes.forEach((n) => visit(n.id));

    const perDepth = {};
    const nodes = graph.nodes.map((n) => {
      const d = depth[n.id] || 0;
      perDepth[d] = (perDepth[d] || 0) + 1;
      return {
        id: n.id,
        type: "concept",
        position: { x: d * 230, y: (perDepth[d] - 1) * 90 },
        data: n,
      };
    });

    const edges = graph.edges.map((e) => ({
      id: `${e.source}-${e.target}`,
      source: e.source,
      target: e.target,
      animated: false,
      style: { stroke: "var(--border)" },
    }));

    return { nodes, edges };
  }, [graph]);

  return (
    <div style={{ height: 420, border: "1px solid var(--border)", borderRadius: 16, background: "var(--card)" }}>
      <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} fitView proOptions={{ hideAttribution: true }}>
        <Background color="var(--border)" gap={20} />
      </ReactFlow>
    </div>
  );
}

function BeliefBars({ belief }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {["absent", "memorised", "misconceived", "robust"].map((s) => (
        <div key={s} style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ width: 80, fontSize: 11, color: "var(--muted)" }}>{STATE_LABEL[s]}</span>
          <ProgressBar value={(belief?.[s] || 0) * 100} max={100} height={6} color={STATE_COLOR[s]} />
          <span style={{ width: 36, fontSize: 11, color: "var(--muted)", textAlign: "right" }}>
            {Math.round((belief?.[s] || 0) * 100)}%
          </span>
        </div>
      ))}
    </div>
  );
}

export default function MktPage() {
  const location = useLocation();
  const [graph, setGraph] = useState(null);
  const [session, setSession] = useState(null); // {session_id, budget, turn}
  const [answer, setAnswer] = useState("");
  const [lastResult, setLastResult] = useState(null);
  const [report, setReport] = useState(null);
  const [busy, setBusy] = useState(false);
  const [showWhy, setShowWhy] = useState(false);
  const [selectedConcepts, setSelectedConcepts] = useState(null);

  const loadGraph = useCallback(() => getConceptGraph("dsa").then(setGraph), []);

  useEffect(() => {
    loadGraph();
    if (location.state?.conceptId) {
      setSelectedConcepts([location.state.conceptId]);
    }
  }, [loadGraph, location.state]);

  const startSession = async (budget = 10) => {
    setBusy(true);
    setReport(null);
    setLastResult(null);
    try {
      const body = { domain: "dsa", budget };
      if (selectedConcepts) body.concept_ids = selectedConcepts;
      const data = await startMktSession(body);
      setSession(data);
    } finally {
      setBusy(false);
    }
  };

  const submitAnswer = async () => {
    if (!answer.trim() || !session) return;
    setBusy(true);
    try {
      const data = await answerMktTurn(session.session_id, { turn_id: session.turn.turn_id, answer });
      setLastResult(data.turn_result);
      setAnswer("");

      if (data.completed) {
        setReport(data.report);
        setSession(null);
      } else {
        setSession((prev) => ({ ...prev, turn: data.turn }));
      }
      loadGraph();
    } finally {
      setBusy(false);
    }
  };

  const currentBelief = session?.turn
    ? Object.fromEntries(["absent", "memorised", "misconceived", "robust"].map((s, i) => [s, session.turn.belief[i]]))
    : null;

  return (
    <div className="page-content">
      <div className="page-header">
        <h1>Metamorphic Knowledge Testing</h1>
        <p>We don't just ask one question. We transform it, and watch whether your understanding survives.</p>
      </div>

      {!session && !report && (
        <>
          <ConceptMap graph={graph} />
          <div style={{ marginTop: 20, display: "flex", gap: 12, alignItems: "center" }}>
            <button
              disabled={busy}
              onClick={() => startSession(10)}
              style={{ background: "var(--primary)", color: "white", border: "none", borderRadius: 12, padding: "12px 24px", fontWeight: 700, fontSize: 14 }}
            >
              {selectedConcepts ? `Probe this concept` : "Start a Probing Session (10 probes)"}
            </button>
            {selectedConcepts && (
              <button onClick={() => setSelectedConcepts(null)} style={{ background: "none", border: "none", color: "var(--muted)", fontSize: 13 }}>
                Clear concept filter
              </button>
            )}
          </div>
        </>
      )}

      {session && (
        <div className="grid grid-2" style={{ alignItems: "start", marginTop: 8 }}>
          <div>
            <Card>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 10 }}>
                <span style={{ fontSize: 12, fontWeight: 700, color: "var(--primary)", textTransform: "uppercase" }}>
                  {PROBE_LABEL[session.turn.probe_type]}
                </span>
                <span style={{ fontSize: 12, color: "var(--muted)" }}>{session.turn.concept_name}</span>
              </div>
              <p data-testid="probe-question" style={{ fontSize: 17, fontWeight: 500, lineHeight: 1.6, marginBottom: 20 }}>{session.turn.question}</p>
              <textarea
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
                placeholder="Type your answer..."
                rows={6}
                style={{
                  width: "100%", background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 12,
                  padding: 14, color: "var(--text)", fontSize: 14, resize: "vertical", outline: "none",
                }}
              />
              <div style={{ display: "flex", justifyContent: "space-between", marginTop: 12 }}>
                <button onClick={() => setShowWhy((v) => !v)} style={{ background: "none", border: "none", color: "var(--muted)", display: "flex", alignItems: "center", gap: 6, fontSize: 12.5 }}>
                  <Info size={14} /> Why this question?
                </button>
                <button
                  disabled={busy || !answer.trim()}
                  onClick={submitAnswer}
                  style={{
                    background: "var(--primary)", color: "white", border: "none", borderRadius: 10,
                    padding: "10px 20px", fontWeight: 700, fontSize: 13.5, display: "flex", alignItems: "center", gap: 8,
                    opacity: busy || !answer.trim() ? 0.6 : 1,
                  }}
                >
                  <Send size={14} /> Submit
                </button>
              </div>

              {showWhy && (
                <div style={{ marginTop: 14, padding: 12, background: "var(--bg)", borderRadius: 10, fontSize: 12.5, color: "var(--muted)" }}>
                  This probe was chosen because it maximises expected information gain (EIG ={" "}
                  <strong style={{ color: "var(--text)" }}>{session.turn.eig}</strong> bits) about{" "}
                  <strong style={{ color: "var(--text)" }}>{session.turn.concept_name}</strong>, given your current
                  belief distribution below.
                </div>
              )}
            </Card>

            {lastResult && (
              <Card style={{ marginTop: 16, borderColor: STATE_COLOR[["absent", "memorised", "misconceived", "robust"][lastResult.belief_after.indexOf(Math.max(...lastResult.belief_after))]] }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: "var(--muted)", textTransform: "uppercase", marginBottom: 6 }}>
                  Previous outcome: {lastResult.outcome.replace(/_/g, " ")}
                </div>
                <p style={{ fontSize: 13, color: "var(--muted)" }}>{lastResult.reasons.join(" · ")}</p>
              </Card>
            )}
          </div>

          <div>
            <Card>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 10 }}>
                Current belief: {session.turn.concept_name}
              </div>
              <BeliefBars belief={currentBelief} />
            </Card>
          </div>
        </div>
      )}

      {report && (
        <div style={{ marginTop: 8 }}>
          <div className="grid grid-3" style={{ marginBottom: 20 }}>
            <Card>
              <div style={{ color: "var(--muted)", fontSize: 12 }}>Conventional Score (base answers only)</div>
              <div style={{ fontSize: 26, fontWeight: 700, marginTop: 6 }}>
                {report.conventional_score !== null ? `${Math.round(report.conventional_score * 100)}%` : "--"}
              </div>
            </Card>
            <Card>
              <div style={{ color: "var(--muted)", fontSize: 12 }}>Mean Robustness Index</div>
              <div style={{ fontSize: 26, fontWeight: 700, marginTop: 6, color: "var(--primary)" }}>
                {report.mean_robustness_index !== null ? `${Math.round(report.mean_robustness_index * 100)}%` : "--"}
              </div>
            </Card>
            <Card>
              <div style={{ color: "var(--muted)", fontSize: 12 }}>Capitulations under pushback</div>
              <div style={{ fontSize: 26, fontWeight: 700, marginTop: 6 }}>{report.capitulations}</div>
            </Card>
          </div>

          {report.misconceptions.length > 0 && (
            <Card style={{ marginBottom: 20, borderColor: "var(--danger)" }}>
              <div style={{ fontWeight: 700, fontSize: 13, color: "var(--danger)", marginBottom: 8 }}>Misconceptions detected</div>
              <ul style={{ paddingLeft: 18, fontSize: 13, color: "var(--muted)" }}>
                {report.misconceptions.map((m) => <li key={m}>{m}</li>)}
              </ul>
            </Card>
          )}

          <div className="grid grid-3">
            {report.concepts.filter((c) => c.probed).map((c) => (
              <Card key={c.concept_id}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
                  <span style={{ fontWeight: 600, fontSize: 14 }}>{c.name}</span>
                  <span style={{ fontSize: 12, fontWeight: 700, color: STATE_COLOR[c.most_likely] }}>{STATE_LABEL[c.most_likely]}</span>
                </div>
                <BeliefBars belief={c.belief} />
              </Card>
            ))}
          </div>

          <button
            onClick={() => startSession(10)}
            style={{ marginTop: 20, background: "var(--primary)", color: "white", border: "none", borderRadius: 12, padding: "12px 24px", fontWeight: 700, fontSize: 14, display: "flex", alignItems: "center", gap: 8 }}
          >
            <RotateCcw size={15} /> Run another session
          </button>
        </div>
      )}
    </div>
  );
}
