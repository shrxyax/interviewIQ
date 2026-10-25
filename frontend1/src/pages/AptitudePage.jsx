import { useEffect, useRef, useState } from "react";
import { Timer, CheckCircle2, XCircle, ListChecks } from "lucide-react";

import { startAttempt, submitAttempt, listAttempts } from "../services/aptitude";
import Card from "../components/shared/Card";
import Badge from "../components/shared/Badge";
import ProgressBar from "../components/shared/ProgressBar";

const CATEGORY_LABELS = {
  quantitative: "Quantitative Aptitude",
  logical: "Logical Reasoning",
  verbal: "Verbal Ability",
};

function formatTime(seconds) {
  const s = Math.max(0, Math.floor(seconds));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${r.toString().padStart(2, "0")}`;
}

function Intro({ onStart, starting, history }) {
  return (
    <div>
      <Card style={{ marginBottom: 20 }}>
        <h2 style={{ fontSize: 18, marginBottom: 10 }}>Aptitude Test</h2>
        <p style={{ fontSize: 14, color: "var(--muted)", lineHeight: 1.7, marginBottom: 14 }}>
          A timed multiple-choice test covering the three areas most tech-interview
          aptitude rounds screen for: quantitative aptitude, logical reasoning, and
          verbal ability. You'll get 20 minutes for the full set; unanswered
          questions are scored as incorrect.
        </p>
        <button
          disabled={starting}
          onClick={onStart}
          style={{ background: "var(--primary)", border: "none", color: "white", borderRadius: 10, padding: "11px 22px", fontWeight: 700, fontSize: 13.5 }}
        >
          {starting ? "Starting..." : "Start test"}
        </button>
      </Card>

      {history && history.length > 0 && (
        <Card>
          <div style={{ fontSize: 12, fontWeight: 700, color: "var(--muted)", textTransform: "uppercase", marginBottom: 10 }}>
            Past attempts
          </div>
          {history.map((a) => (
            <div key={a.attempt_id} style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5, padding: "6px 0", borderBottom: "1px solid var(--border)" }}>
              <span>{a.status === "submitted" ? `${a.score}/${a.total}` : "In progress"}</span>
              <span style={{ color: "var(--muted)" }}>{new Date(a.started_at).toLocaleString()}</span>
            </div>
          ))}
        </Card>
      )}
    </div>
  );
}

function TestRunner({ attempt, onSubmitted }) {
  const [current, setCurrent] = useState(0);
  const [answers, setAnswers] = useState({});
  const [remaining, setRemaining] = useState(attempt.time_limit_seconds);
  const [submitting, setSubmitting] = useState(false);
  const submittedRef = useRef(false);

  const doSubmit = async () => {
    if (submittedRef.current) return;
    submittedRef.current = true;
    setSubmitting(true);
    try {
      const result = await submitAttempt(attempt.attempt_id, answers);
      onSubmitted(result);
    } finally {
      setSubmitting(false);
    }
  };

  useEffect(() => {
    const startedAtMs = new Date(attempt.started_at).getTime();
    const tick = () => {
      const left = attempt.time_limit_seconds - (Date.now() - startedAtMs) / 1000;
      setRemaining(left);
      if (left <= 0) doSubmit();
    };
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const questions = attempt.questions;
  const q = questions[current];
  const answeredCount = Object.keys(answers).length;
  const low = remaining <= 60;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <div style={{ fontSize: 13, color: "var(--muted)" }}>
          Question {current + 1} of {questions.length} &middot; {answeredCount} answered
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6, fontWeight: 700, color: low ? "var(--danger)" : "var(--text)" }}>
          <Timer size={16} /> {formatTime(remaining)}
        </div>
      </div>

      <ProgressBar value={current + 1} max={questions.length} />

      <Card style={{ marginTop: 16 }}>
        <Badge tone="info" style={{ marginBottom: 12 }}>{CATEGORY_LABELS[q.category] || q.category}</Badge>
        <p style={{ fontSize: 15, lineHeight: 1.7, marginBottom: 16 }}>{q.question}</p>

        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {q.options.map((opt, i) => {
            const selected = answers[q.id] === i;
            return (
              <button
                key={i}
                data-testid="aptitude-option"
                onClick={() => setAnswers((prev) => ({ ...prev, [q.id]: i }))}
                style={{
                  textAlign: "left",
                  padding: "10px 14px",
                  borderRadius: 10,
                  border: `1px solid ${selected ? "var(--primary)" : "var(--border)"}`,
                  background: selected ? "var(--primary-soft)" : "var(--bg)",
                  color: "var(--text)",
                  fontSize: 13.5,
                  cursor: "pointer",
                }}
              >
                {opt}
              </button>
            );
          })}
        </div>
      </Card>

      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 16, gap: 10 }}>
        <button
          disabled={current === 0}
          onClick={() => setCurrent((c) => c - 1)}
          style={{ background: "var(--card)", border: "1px solid var(--border)", color: "var(--text)", borderRadius: 10, padding: "10px 18px", fontWeight: 600, fontSize: 13.5 }}
        >
          Previous
        </button>

        <div style={{ display: "flex", gap: 10 }}>
          {current < questions.length - 1 ? (
            <button
              onClick={() => setCurrent((c) => c + 1)}
              style={{ background: "var(--card)", border: "1px solid var(--border)", color: "var(--text)", borderRadius: 10, padding: "10px 18px", fontWeight: 600, fontSize: 13.5 }}
            >
              Next
            </button>
          ) : null}
          <button
            disabled={submitting}
            onClick={doSubmit}
            style={{ background: "var(--primary)", border: "none", color: "white", borderRadius: 10, padding: "10px 18px", fontWeight: 700, fontSize: 13.5 }}
          >
            {submitting ? "Submitting..." : "Submit test"}
          </button>
        </div>
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 16 }}>
        {questions.map((qq, i) => (
          <button
            key={qq.id}
            onClick={() => setCurrent(i)}
            style={{
              width: 30,
              height: 30,
              borderRadius: 8,
              border: `1px solid ${i === current ? "var(--primary)" : "var(--border)"}`,
              background: answers[qq.id] !== undefined ? "var(--primary-soft)" : "var(--card)",
              color: "var(--text)",
              fontSize: 12,
              cursor: "pointer",
            }}
          >
            {i + 1}
          </button>
        ))}
      </div>
    </div>
  );
}

function Results({ result, onRetake }) {
  const categories = Object.keys(CATEGORY_LABELS).filter((c) => result.category_breakdown[c]);

  return (
    <div>
      <Card style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
          <ListChecks size={20} color="var(--primary)" />
          <h2 style={{ fontSize: 18 }}>
            Score: {result.score} / {result.total}
          </h2>
        </div>
        {result.expired && (
          <p style={{ fontSize: 13, color: "var(--warning)", marginBottom: 10 }}>
            Time ran out before you submitted — answers given up to that point were scored.
          </p>
        )}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12, marginTop: 10 }}>
          {categories.map((c) => {
            const b = result.category_breakdown[c];
            return (
              <div key={c}>
                <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 6 }}>{CATEGORY_LABELS[c]}</div>
                <ProgressBar value={b.correct} max={b.total} />
                <div style={{ fontSize: 12.5, marginTop: 4 }}>{b.correct}/{b.total}</div>
              </div>
            );
          })}
        </div>
        <button
          onClick={onRetake}
          style={{ marginTop: 16, background: "var(--primary)", border: "none", color: "white", borderRadius: 10, padding: "10px 18px", fontWeight: 700, fontSize: 13.5 }}
        >
          Take another attempt
        </button>
      </Card>

      {result.questions.map((q, i) => {
        const correct = q.selected_index === q.correct_index;
        return (
          <Card key={q.id} style={{ marginBottom: 12 }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
              <Badge tone="info">{CATEGORY_LABELS[q.category] || q.category}</Badge>
              {correct ? (
                <span style={{ color: "var(--success)", display: "flex", alignItems: "center", gap: 6, fontWeight: 600, fontSize: 13 }}>
                  <CheckCircle2 size={15} /> Correct
                </span>
              ) : (
                <span style={{ color: "var(--danger)", display: "flex", alignItems: "center", gap: 6, fontWeight: 600, fontSize: 13 }}>
                  <XCircle size={15} /> {q.selected_index === undefined || q.selected_index === null ? "Unanswered" : "Incorrect"}
                </span>
              )}
            </div>
            <p style={{ fontSize: 14, marginBottom: 10 }}>{i + 1}. {q.question}</p>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {q.options.map((opt, oi) => {
                const isCorrect = oi === q.correct_index;
                const isSelected = oi === q.selected_index;
                return (
                  <div
                    key={oi}
                    style={{
                      padding: "8px 12px",
                      borderRadius: 8,
                      fontSize: 13,
                      border: `1px solid ${isCorrect ? "var(--success)" : isSelected ? "var(--danger)" : "var(--border)"}`,
                      background: isCorrect ? "var(--success-soft)" : isSelected ? "var(--danger-soft)" : "transparent",
                    }}
                  >
                    {opt}
                  </div>
                );
              })}
            </div>
            {q.explanation && (
              <p style={{ fontSize: 12.5, color: "var(--muted)", marginTop: 10 }}>{q.explanation}</p>
            )}
          </Card>
        );
      })}
    </div>
  );
}

export default function AptitudePage() {
  const [attempt, setAttempt] = useState(null);
  const [result, setResult] = useState(null);
  const [starting, setStarting] = useState(false);
  const [history, setHistory] = useState(null);

  useEffect(() => {
    listAttempts().then(setHistory);
  }, []);

  const handleStart = async () => {
    setStarting(true);
    try {
      const a = await startAttempt();
      setAttempt(a);
      setResult(null);
    } finally {
      setStarting(false);
    }
  };

  const handleSubmitted = (r) => {
    setResult(r);
    setAttempt(null);
    listAttempts().then(setHistory);
  };

  return (
    <div className="page-content">
      <div className="page-header">
        <h1>Aptitude Test</h1>
        <p>Quantitative, logical, and verbal aptitude — the format used in most tech-interview screening rounds.</p>
      </div>

      {result ? (
        <Results result={result} onRetake={handleStart} />
      ) : attempt ? (
        <TestRunner attempt={attempt} onSubmitted={handleSubmitted} />
      ) : (
        <Intro onStart={handleStart} starting={starting} history={history} />
      )}
    </div>
  );
}
