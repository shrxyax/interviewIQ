import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import Editor from "@monaco-editor/react";
import { Play, Send, ChevronLeft, CheckCircle2, XCircle, Clock, ShieldAlert } from "lucide-react";

import { listProblems, getProblem, runSamples, submit, listSubmissions } from "../services/coding";
import Badge from "../components/shared/Badge";
import Card from "../components/shared/Card";

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
    <table className="data-table">
      <thead>
        <tr>
          <th>Problem</th>
          <th>Difficulty</th>
        </tr>
      </thead>
      <tbody>
        {problems.map((p) => (
          <tr key={p.id} onClick={() => onSelect(p.id)} style={{ cursor: "pointer" }}>
            <td style={{ fontWeight: 500 }}>{p.title}</td>
            <td><Badge difficulty={p.difficulty}>{p.difficulty}</Badge></td>
          </tr>
        ))}
      </tbody>
    </table>
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
      <button onClick={onBack} style={{ background: "none", border: "none", color: "var(--muted)", display: "flex", alignItems: "center", gap: 6, marginBottom: 16, fontSize: 13 }}>
        <ChevronLeft size={16} /> All problems
      </button>

      <div className="grid grid-2" style={{ alignItems: "start", gridTemplateColumns: "1fr 1.3fr" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
            <h2 style={{ fontSize: 20 }}>{problem.title}</h2>
            <Badge difficulty={problem.difficulty}>{problem.difficulty}</Badge>
          </div>
          <Card>
            <p style={{ fontSize: 14, lineHeight: 1.7, color: "var(--muted)", marginBottom: 14 }}>{problem.statement}</p>
            <div className="mono" style={{ fontSize: 12.5, color: "var(--text)", marginBottom: 14 }}>{problem.signature}</div>

            <div style={{ fontSize: 12, fontWeight: 700, color: "var(--muted)", textTransform: "uppercase", marginBottom: 8 }}>Sample tests</div>
            {problem.sample_tests.map((t, i) => (
              <div key={i} className="mono" style={{ fontSize: 12, background: "var(--bg)", borderRadius: 8, padding: 10, marginBottom: 8 }}>
                <div>args = {JSON.stringify(t.args)}</div>
                <div style={{ color: "var(--muted)" }}>expected = {JSON.stringify(t.expected)}</div>
              </div>
            ))}
          </Card>

          {submissions.length > 0 && (
            <Card style={{ marginTop: 14 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: "var(--muted)", textTransform: "uppercase", marginBottom: 10 }}>Your submissions</div>
              {submissions.map((s) => {
                const meta = VERDICT_META[s.verdict] || {};
                return (
                  <div key={s.id} style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5, padding: "6px 0", borderBottom: "1px solid var(--border)" }}>
                    <span style={{ color: meta.color, fontWeight: 600 }}>{meta.label}</span>
                    <span style={{ color: "var(--muted)" }}>{s.passed}/{s.total} tests · {s.runtime_ms.toFixed(0)}ms</span>
                  </div>
                );
              })}
            </Card>
          )}
        </div>

        <div>
          <div style={{ border: "1px solid var(--border)", borderRadius: 12, overflow: "hidden" }}>
            <Editor
              height="420px"
              language="python"
              theme="vs-dark"
              value={code}
              onChange={(v) => setCode(v || "")}
              options={{ fontSize: 13, minimap: { enabled: false }, fontFamily: "JetBrains Mono, monospace" }}
            />
          </div>

          <div style={{ display: "flex", gap: 10, marginTop: 12 }}>
            <button
              disabled={running}
              onClick={handleRun}
              style={{ flex: 1, background: "var(--card)", border: "1px solid var(--border)", color: "var(--text)", borderRadius: 10, padding: "11px 0", fontWeight: 600, fontSize: 13.5, display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}
            >
              <Play size={14} /> Run sample tests
            </button>
            <button
              disabled={running}
              onClick={handleSubmit}
              style={{ flex: 1, background: "var(--primary)", border: "none", color: "white", borderRadius: 10, padding: "11px 0", fontWeight: 700, fontSize: 13.5, display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}
            >
              <Send size={14} /> Submit
            </button>
          </div>

          {result && (
            <Card style={{ marginTop: 14 }}>
              {result.kind === "submit" ? (
                <>
                  {(() => {
                    const meta = VERDICT_META[result.verdict] || {};
                    const Icon = meta.icon || CheckCircle2;
                    return (
                      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10, color: meta.color, fontWeight: 700 }}>
                        <Icon size={18} /> {meta.label} &middot; {result.passed}/{result.total} tests passed
                      </div>
                    );
                  })()}
                </>
              ) : (
                <div style={{ fontWeight: 700, marginBottom: 10 }}>{result.passed}/{result.total} sample tests passed</div>
              )}
              {(result.results || result.visible_results)?.map((r, i) => (
                <div key={i} style={{ fontSize: 12.5, display: "flex", justifyContent: "space-between", padding: "4px 0" }}>
                  <span style={{ color: r.status === "ok" ? "var(--success)" : "var(--danger)" }}>Test {i + 1}: {r.status}</span>
                  {r.error && <span style={{ color: "var(--muted)", maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.error}</span>}
                </div>
              ))}
              {result.kind === "submit" && result.total > result.visible_results.length && (
                <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 6 }}>
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
