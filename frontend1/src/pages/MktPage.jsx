import { useCallback, useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { ReactFlow, Background, Handle, Position } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Send, RotateCcw, Info } from "lucide-react";

import { getConceptGraph, startMktSession, answerMktTurn } from "../services/mkt";
import Card from "../components/shared/Card";
import ProgressBar from "../components/shared/ProgressBar";
import "./MktPage.css";

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
      className="mkt-node"
      style={{ borderColor: data.observations > 0 ? STATE_COLOR[data.most_likely] : undefined }}
    >
      <Handle type="target" position={Position.Top} className="flow-handle" />
      <div className="mkt-node-name">{data.name}</div>
      {data.observations > 0 ? (
        <div className="mkt-node-state" style={{ color: STATE_COLOR[data.most_likely] }}>
          {STATE_LABEL[data.most_likely]} &middot; {Math.round(data.confidence * 100)}%
        </div>
      ) : (
        <div className="mkt-node-state untested">Not yet tested</div>
      )}
      <Handle type="source" position={Position.Bottom} className="flow-handle" />
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
    <div className="flow-canvas mkt-canvas">
      <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} fitView proOptions={{ hideAttribution: true }}>
        <Background color="var(--border)" gap={20} />
      </ReactFlow>
    </div>
  );
}

function BeliefBars({ belief }) {
  return (
    <div className="belief-bars">
      {["absent", "memorised", "misconceived", "robust"].map((s) => (
        <div key={s} className="belief-row">
          <span className="belief-label">{STATE_LABEL[s]}</span>
          <ProgressBar value={(belief?.[s] || 0) * 100} max={100} height={6} color={STATE_COLOR[s]} />
          <span className="belief-pct">
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
          <div className="row mkt-start-row">
            <button
              disabled={busy}
              onClick={() => startSession(10)}
              className="btn btn-primary btn-lg"
            >
              {selectedConcepts ? `Probe this concept` : "Start a Probing Session (10 probes)"}
            </button>
            {selectedConcepts && (
              <button onClick={() => setSelectedConcepts(null)} className="text-btn">
                Clear concept filter
              </button>
            )}
          </div>
        </>
      )}

      {session && (
        <div className="grid grid-2 mkt-session">
          <div>
            <Card>
              <div className="row-between" style={{ marginBottom: 10 }}>
                <span className="section-label mkt-probe-type">
                  {PROBE_LABEL[session.turn.probe_type]}
                </span>
                <span className="stat-label">{session.turn.concept_name}</span>
              </div>
              <p data-testid="probe-question" className="mkt-question">{session.turn.question}</p>
              <textarea
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
                placeholder="Type your answer..."
                rows={6}
                className="field mkt-answer"
                aria-label="Your answer"
              />
              <div className="row-between" style={{ marginTop: 12 }}>
                <button onClick={() => setShowWhy((v) => !v)} className="text-btn" aria-expanded={showWhy}>
                  <Info size={14} /> Why this question?
                </button>
                <button
                  disabled={busy || !answer.trim()}
                  onClick={submitAnswer}
                  className="btn btn-primary"
                  style={{ padding: "10px 20px" }}
                >
                  <Send size={14} /> Submit
                </button>
              </div>

              {showWhy && (
                <div className="mkt-why">
                  This probe was chosen because it maximises expected information gain (EIG ={" "}
                  <strong className="text-strong">{session.turn.eig}</strong> bits) about{" "}
                  <strong className="text-strong">{session.turn.concept_name}</strong>, given your current
                  belief distribution below.
                </div>
              )}
            </Card>

            {lastResult && (
              <Card style={{ marginTop: 16, borderColor: STATE_COLOR[["absent", "memorised", "misconceived", "robust"][lastResult.belief_after.indexOf(Math.max(...lastResult.belief_after))]] }}>
                <div className="section-label" style={{ marginBottom: 6 }}>
                  Previous outcome: {lastResult.outcome.replace(/_/g, " ")}
                </div>
                <p className="note">{lastResult.reasons.join(" · ")}</p>
              </Card>
            )}
          </div>

          <div>
            <Card>
              <div className="mkt-belief-title">
                Current belief: {session.turn.concept_name}
              </div>
              <BeliefBars belief={currentBelief} />
            </Card>
          </div>
        </div>
      )}

      {report && (
        <div className="mkt-report">
          <div className="grid grid-3" style={{ marginBottom: 20 }}>
            <Card>
              <div className="stat-label">Conventional Score (base answers only)</div>
              <div className="stat-value">
                {report.conventional_score !== null ? `${Math.round(report.conventional_score * 100)}%` : "--"}
              </div>
            </Card>
            <Card>
              <div className="stat-label">Mean Robustness Index</div>
              <div className="stat-value" style={{ color: "var(--primary)" }}>
                {report.mean_robustness_index !== null ? `${Math.round(report.mean_robustness_index * 100)}%` : "--"}
              </div>
            </Card>
            <Card>
              <div className="stat-label">Capitulations under pushback</div>
              <div className="stat-value">{report.capitulations}</div>
            </Card>
          </div>

          {report.misconceptions.length > 0 && (
            <Card style={{ marginBottom: 20, borderColor: "var(--danger)" }}>
              <div className="mkt-misconceptions-title">Misconceptions detected</div>
              <ul className="note mkt-misconceptions">
                {report.misconceptions.map((m) => <li key={m}>{m}</li>)}
              </ul>
            </Card>
          )}

          <div className="grid grid-3">
            {report.concepts.filter((c) => c.probed).map((c) => (
              <Card key={c.concept_id}>
                <div className="concept-head">
                  <span className="concept-name">{c.name}</span>
                  <span className="concept-state" style={{ color: STATE_COLOR[c.most_likely] }}>{STATE_LABEL[c.most_likely]}</span>
                </div>
                <BeliefBars belief={c.belief} />
              </Card>
            ))}
          </div>

          <button
            onClick={() => startSession(10)}
            className="btn btn-primary btn-lg" style={{ marginTop: 20 }}
          >
            <RotateCcw size={15} /> Run another session
          </button>
        </div>
      )}
    </div>
  );
}
