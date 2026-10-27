import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import Editor from "@monaco-editor/react";
import { Play, Send, ChevronLeft, CheckCircle2, XCircle, Clock, ShieldAlert } from "lucide-react";

import { listProblems, getProblem, runSamples, submit, listSubmissions } from "../services/coding";
import Badge from "../components/shared/Badge";
import Card from "../components/shared/Card";
import "./CodingPage.css";

const VERDICT_META = {
  AC: { label: "Accepted", color: "var(--success)", icon: CheckCircle2 },
  WA: { label: "Wrong Answer", color: "var(--danger)", icon: XCircle },
  RE: { label: "Runtime Error", color: "var(--danger)", icon: XCircle },
  TLE: { label: "Time Limit Exceeded", color: "var(--warning)", icon: Clock },
  UNSAFE: { label: "Blocked (unsafe code)", color: "var(--danger)", icon: ShieldAlert },
};

function ProblemList({ onSelect }) {
  const [problems, setProblems] = useState(null);

  useEffect(() => {
    listProblems().then(setProblems);
  }, []);

  if (!problems) return <p className="spinner-text">Loading problems...</p>;

  return (
    <div className="table-scroll">
    <table className="data-table">
      <thead>
        <tr>
          <th>Problem</th>
          <th>Difficulty</th>
        </tr>
      </thead>
      <tbody>
        {problems.map((p) => (
          <tr
            key={p.id}
            className="clickable-row"
            tabIndex={0}
            onClick={() => onSelect(p.id)}
            onKeyDown={(e) => e.key === "Enter" && onSelect(p.id)}
          >
            <td className="code-problem-title">{p.title}</td>
            <td><Badge difficulty={p.difficulty}>{p.difficulty}</Badge></td>
          </tr>
        ))}
      </tbody>
    </table>
    </div>
  );
}

function ProblemWorkspace({ problemId, onBack }) {
  const [problem, setProblem] = useState(null);
  const [code, setCode] = useState("");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);
  const [submissions, setSubmissions] = useState([]);

  useEffect(() => {
    getProblem(problemId).then((p) => {
      setProblem(p);
      setCode(p.starter_code);
    });
    listSubmissions(problemId).then(setSubmissions);
  }, [problemId]);

  const handleRun = async () => {
    setRunning(true);
    setResult(null);
    try {
      const r = await runSamples(problemId, code);
      setResult({ kind: "run", ...r });
    } finally {
      setRunning(false);
    }
  };

  const handleSubmit = async () => {
    setRunning(true);
    setResult(null);
    try {
      const r = await submit(problemId, code);
      setResult({ kind: "submit", ...r });
      listSubmissions(problemId).then(setSubmissions);
    } finally {
      setRunning(false);
    }
  };

  if (!problem) return <p className="spinner-text">Loading problem...</p>;

  return (
    <div>
      <button onClick={onBack} className="text-btn back-btn" style={{ marginBottom: 16 }}>
        <ChevronLeft size={16} /> All problems
      </button>

      <div className="grid grid-code">
        <div>
          <div className="row code-title-row">
            <h2>{problem.title}</h2>
            <Badge difficulty={problem.difficulty}>{problem.difficulty}</Badge>
          </div>
          <Card>
            <p className="code-statement">{problem.statement}</p>
            <div className="mono code-signature">{problem.signature}</div>

            <div className="section-label">Sample tests</div>
            {problem.sample_tests.map((t, i) => (
              <div key={i} className="mono code-sample">
                <div>args = {JSON.stringify(t.args)}</div>
                <div className="muted">expected = {JSON.stringify(t.expected)}</div>
              </div>
            ))}
          </Card>

          {submissions.length > 0 && (
            <Card className="code-card">
              <div className="section-label">Your submissions</div>
              {submissions.map((s) => {
                const meta = VERDICT_META[s.verdict] || {};
                return (
                  <div key={s.id} className="list-row">
                    <span className="code-verdict" style={{ color: meta.color }}>{meta.label}</span>
                    <span className="muted">{s.passed}/{s.total} tests · {s.runtime_ms.toFixed(0)}ms</span>
                  </div>
                );
              })}
            </Card>
          )}
        </div>

        <div>
          <div className="code-editor">
            <Editor
              height="420px"
              language="python"
              theme="vs-dark"
              value={code}
              onChange={(v) => setCode(v || "")}
              options={{ fontSize: 13, minimap: { enabled: false }, fontFamily: "JetBrains Mono, monospace" }}
            />
          </div>

          <div className="code-actions">
            <button
              disabled={running}
              onClick={handleRun}
              className="btn btn-secondary"
            >
              <Play size={14} /> Run sample tests
            </button>
            <button
              disabled={running}
              onClick={handleSubmit}
              className="btn btn-primary"
            >
              <Send size={14} /> Submit
            </button>
          </div>

          {result && (
            <Card className="code-card">
              {result.kind === "submit" ? (
                <>
                  {(() => {
                    const meta = VERDICT_META[result.verdict] || {};
                    const Icon = meta.icon || CheckCircle2;
                    return (
                      <div className="row code-result-title" style={{ color: meta.color }}>
                        <Icon size={18} /> {meta.label} &middot; {result.passed}/{result.total} tests passed
                      </div>
                    );
                  })()}
                </>
              ) : (
                <div className="code-result-title">{result.passed}/{result.total} sample tests passed</div>
              )}
              {(result.results || result.visible_results)?.map((r, i) => (
                <div key={i} className="code-test-row">
                  <span className={r.status === "ok" ? "text-success" : "text-danger"}>Test {i + 1}: {r.status}</span>
                  {r.error && <span className="code-test-error" title={r.error}>{r.error}</span>}
                </div>
              ))}
              {result.kind === "submit" && result.total > result.visible_results.length && (
                <div className="code-hidden-note">
                  + {result.total - result.visible_results.length} hidden test(s), not shown individually.
                </div>
              )}
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

export default function CodingPage() {
  const { problemId } = useParams();
  const navigate = useNavigate();

  return (
    <div className="page-content">
      <div className="page-header">
        <h1>Coding IDE</h1>
        <p>Write Python, run it against hidden test cases, right here.</p>
      </div>

      {problemId ? (
        <ProblemWorkspace problemId={problemId} onBack={() => navigate("/code")} />
      ) : (
        <ProblemList onSelect={(id) => navigate(`/code/${id}`)} />
      )}
    </div>
  );
}
