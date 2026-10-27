import Editor from "@monaco-editor/react";
import ReactMarkdown from "react-markdown";
import { CheckCircle2, XCircle, Clock, ShieldAlert, Play, Send } from "lucide-react";

import Badge from "./shared/Badge";

// The live coding round inside an interview: the problem (left, in the
// interviewer's stage) and the editor with run/submit and test results
// (right, in place of the spoken-answer box).

const STATUS_META = {
  ok: { label: "Passed", icon: CheckCircle2, tone: "pass" },
  wrong_answer: { label: "Wrong answer", icon: XCircle, tone: "fail" },
  runtime_error: { label: "Error", icon: XCircle, tone: "fail" },
  timeout: { label: "Time limit exceeded", icon: Clock, tone: "warn" },
  unsafe: { label: "Blocked", icon: ShieldAlert, tone: "fail" },
};

// "def solve(nums, target):" -> ["nums", "target"]
const paramNames = (signature) =>
  (signature.match(/\(([^)]*)\)/)?.[1] || "")
    .split(",")
    .map((p) => p.trim().split(/[:=]/)[0].trim())
    .filter(Boolean);

const show = (value) => JSON.stringify(value);

function formatArgs(signature, args) {
  const names = paramNames(signature);
  return args.map((a, i) => `${names[i] ?? `arg${i + 1}`} = ${show(a)}`).join(", ");
}

export function CodingProblemPanel({ problem }) {
  return (
    <div className="coding-problem">
      <div className="coding-problem-head">
        <h2>{problem.title}</h2>
        <Badge difficulty={problem.difficulty}>{problem.difficulty}</Badge>
      </div>

      <div className="coding-statement">
        <ReactMarkdown>{problem.statement}</ReactMarkdown>
      </div>

      <div className="coding-signature mono">{problem.signature}</div>

      <div className="section-label">Test cases</div>
      <ol className="coding-tests">
        {problem.tests.map((t, i) => (
          <li key={i} className="mono">
            <div>
              <span className="muted">Input:</span> {formatArgs(problem.signature, t.args)}
            </div>
            <div>
              <span className="muted">Expected:</span> {show(t.expected)}
            </div>
          </li>
        ))}
      </ol>

      {problem.hidden_test_count > 0 && (
        <p className="note">
          + {problem.hidden_test_count} hidden test{problem.hidden_test_count === 1 ? "" : "s"}, checked when you
          submit.
        </p>
      )}
    </div>
  );
}

export function CodingWorkspace({
  problem,
  code,
  onChange,
  onRun,
  onSubmit,
  running,
  submitting,
  disabled,
  result,
  error,
}) {
  const busy = running || submitting;

  return (
    <div className="coding-workspace">
      <div className="answer-heading">
        <span>Your Solution (Python)</span>
      </div>

      <div className="coding-editor">
        <Editor
          height="100%"
          language="python"
          theme="vs-dark"
          value={code}
          onChange={(v) => onChange(v || "")}
          options={{
            fontSize: 13,
            minimap: { enabled: false },
            fontFamily: "JetBrains Mono, monospace",
            scrollBeyondLastLine: false,
            readOnly: disabled,
            automaticLayout: true,
          }}
        />
      </div>

      {error && <div className="interview-error">{error}</div>}

      <div className="coding-actions">
        <button type="button" className="btn btn-secondary" onClick={onRun} disabled={disabled || busy}>
          <Play size={15} />
          {running ? "Running..." : "Run tests"}
        </button>
        <button type="button" className="submit-answer-button" onClick={onSubmit} disabled={disabled || busy}>
          <Send size={16} />
          {submitting ? "Grading..." : "Submit Solution"}
        </button>
      </div>

      <div className="coding-results" aria-live="polite">
        {!result ? (
          <p className="note">Run your code to check it against the test cases.</p>
        ) : (
          <>
            <div className={`coding-results-summary ${result.passed === result.total ? "pass" : "fail"}`}>
              {result.passed}/{result.total} test{result.total === 1 ? "" : "s"} passing
            </div>

            {result.results.map((r, i) => {
              const meta = STATUS_META[r.status] || STATUS_META.runtime_error;
              const Icon = meta.icon;

              return (
                <div key={i} className={`coding-result ${meta.tone}`}>
                  <div className="coding-result-title">
                    <Icon size={15} />
                    Test {i + 1}: {meta.label}
                    {r.runtime_ms ? <span className="muted"> · {Math.round(r.runtime_ms)}ms</span> : null}
                  </div>
                  <div className="mono coding-result-body">
                    <div>
                      <span className="muted">Input:</span> {formatArgs(problem.signature, r.args)}
                    </div>
                    <div>
                      <span className="muted">Expected:</span> {show(r.expected)}
                    </div>
                    {r.status !== "runtime_error" && r.status !== "timeout" && r.status !== "unsafe" && (
                      <div>
                        <span className="muted">Output:</span> {show(r.output)}
                      </div>
                    )}
                    {r.error && <pre className="coding-error">{r.error}</pre>}
                  </div>
                </div>
              );
            })}
          </>
        )}
      </div>
    </div>
  );
}
