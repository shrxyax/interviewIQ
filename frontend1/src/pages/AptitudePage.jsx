import { useEffect, useRef, useState } from "react";
import { Timer, CheckCircle2, XCircle, ListChecks } from "lucide-react";

import { startAttempt, submitAttempt, listAttempts } from "../services/aptitude";
import Card from "../components/shared/Card";
import Badge from "../components/shared/Badge";
import ProgressBar from "../components/shared/ProgressBar";
import "./AptitudePage.css";

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
        <h2 className="section-title" style={{ marginBottom: 10 }}>Aptitude Test</h2>
        <p className="apt-intro">
          A timed multiple-choice test covering the three areas most tech-interview
          aptitude rounds screen for: quantitative aptitude, logical reasoning, and
          verbal ability. You'll get 20 minutes for the full set; unanswered
          questions are scored as incorrect.
        </p>
        <button
          disabled={starting}
          onClick={onStart}
          className="btn btn-primary apt-start"
        >
          {starting ? "Starting..." : "Start test"}
        </button>
      </Card>

      {history && history.length > 0 && (
        <Card>
          <div className="section-label">
            Past attempts
          </div>
          {history.map((a) => (
            <div key={a.attempt_id} className="list-row">
              <span>{a.status === "submitted" ? `${a.score}/${a.total}` : "In progress"}</span>
              <span className="muted">{new Date(a.started_at).toLocaleString()}</span>
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
      <div className="row-between" style={{ marginBottom: 16 }}>
        <div className="note">
          Question {current + 1} of {questions.length} &middot; {answeredCount} answered
        </div>
        <div className={`apt-timer ${low ? "low" : ""}`} aria-live="polite">
          <Timer size={16} /> {formatTime(remaining)}
        </div>
      </div>

      <ProgressBar value={current + 1} max={questions.length} />

      <Card style={{ marginTop: 16 }}>
        <Badge tone="info" className="apt-category">{CATEGORY_LABELS[q.category] || q.category}</Badge>
        <p className="apt-question">{q.question}</p>

        <div className="stack">
          {q.options.map((opt, i) => {
            const selected = answers[q.id] === i;
            return (
              <button
                key={i}
                data-testid="aptitude-option"
                onClick={() => setAnswers((prev) => ({ ...prev, [q.id]: i }))}
                className={`apt-option ${selected ? "selected" : ""}`}
                aria-pressed={selected}
              >
                {opt}
              </button>
            );
          })}
        </div>
      </Card>

      <div className="row-between" style={{ marginTop: 16 }}>
        <button
          disabled={current === 0}
          onClick={() => setCurrent((c) => c - 1)}
          className="btn btn-secondary"
        >
          Previous
        </button>

        <div className="row" style={{ gap: 10 }}>
          {current < questions.length - 1 ? (
            <button
              onClick={() => setCurrent((c) => c + 1)}
              className="btn btn-secondary"
            >
              Next
            </button>
          ) : null}
          <button
            disabled={submitting}
            onClick={doSubmit}
            className="btn btn-primary"
          >
            {submitting ? "Submitting..." : "Submit test"}
          </button>
        </div>
      </div>

      <div className="apt-jump" aria-label="Jump to question">
        {questions.map((qq, i) => (
          <button
            key={qq.id}
            onClick={() => setCurrent(i)}
            className={`apt-jump-btn ${i === current ? "current" : ""} ${answers[qq.id] !== undefined ? "answered" : ""}`}
            aria-label={`Question ${i + 1}${answers[qq.id] !== undefined ? ", answered" : ""}`}
            aria-current={i === current ? "step" : undefined}
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
        <div className="row" style={{ gap: 10, marginBottom: 10 }}>
          <ListChecks size={20} color="var(--primary)" />
          <h2 className="section-title">
            Score: {result.score} / {result.total}
          </h2>
        </div>
        {result.expired && (
          <p className="note" style={{ color: "var(--warning)", marginBottom: 10 }}>
            Time ran out before you submitted — answers given up to that point were scored.
          </p>
        )}
        <div className="apt-breakdown">
          {categories.map((c) => {
            const b = result.category_breakdown[c];
            return (
              <div key={c}>
                <div className="stat-label" style={{ marginBottom: 6 }}>{CATEGORY_LABELS[c]}</div>
                <ProgressBar value={b.correct} max={b.total} />
                <div className="apt-breakdown-count">{b.correct}/{b.total}</div>
              </div>
            );
          })}
        </div>
        <button
          onClick={onRetake}
          className="btn btn-primary" style={{ marginTop: 16 }}
        >
          Take another attempt
        </button>
      </Card>

      {result.questions.map((q, i) => {
        const correct = q.selected_index === q.correct_index;
        return (
          <Card key={q.id} style={{ marginBottom: 12 }}>
            <div className="row-between" style={{ marginBottom: 8 }}>
              <Badge tone="info">{CATEGORY_LABELS[q.category] || q.category}</Badge>
              {correct ? (
                <span className="apt-verdict text-success">
                  <CheckCircle2 size={15} /> Correct
                </span>
              ) : (
                <span className="apt-verdict text-danger">
                  <XCircle size={15} /> {q.selected_index === undefined || q.selected_index === null ? "Unanswered" : "Incorrect"}
                </span>
              )}
            </div>
            <p className="apt-review-question">{i + 1}. {q.question}</p>
            <div className="stack" style={{ gap: 6 }}>
              {q.options.map((opt, oi) => {
                const isCorrect = oi === q.correct_index;
                const isSelected = oi === q.selected_index;
                return (
                  <div
                    key={oi}
                    className={`apt-review-option ${isCorrect ? "correct" : isSelected ? "wrong" : ""}`}
                  >
                    {opt}
                  </div>
                );
              })}
            </div>
            {q.explanation && (
              <p className="apt-explanation">{q.explanation}</p>
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
  const [startError, setStartError] = useState(null);

  useEffect(() => {
    listAttempts().then(setHistory).catch(() => {});
  }, []);

  const handleStart = async () => {
    setStarting(true);
    setStartError(null);
    try {
      const a = await startAttempt();
      setAttempt(a);
      setResult(null);
    } catch (e) {
      setStartError(e.response?.data?.detail || "Failed to start the test.");
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
        <>
          {startError && (
            <p className="error-text" style={{ marginBottom: 14 }}>{startError}</p>
          )}
          <Intro onStart={handleStart} starting={starting} history={history} />
        </>
      )}
    </div>
  );
}
