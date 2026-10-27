import { useEffect, useState } from "react";
import { Brain, MessageSquareText, Smile, HelpCircle } from "lucide-react";

import { getSessionEvidence } from "../services/interviewContext";
import Card from "./shared/Card";
import Badge from "./shared/Badge";
import ProgressBar from "./shared/ProgressBar";
import "./EvidenceTimeline.css";

const STATES = ["absent", "memorised", "misconceived", "robust"];
const STATE_COLOR = { robust: "var(--success)", memorised: "var(--warning)", misconceived: "var(--danger)", absent: "var(--muted)" };

const SOURCE_META = {
  mkt: { label: "Knowledge probe", icon: Brain, tone: "info" },
  interview: { label: "Answer scored", icon: MessageSquareText, tone: "primary" },
  comms: { label: "Communication / emotion", icon: Smile, tone: "warning" },
};

function sourceMeta(source) {
  return SOURCE_META[source] || { label: source, icon: HelpCircle, tone: "muted" };
}

function BeliefBars({ belief }) {
  if (!belief) return null;

  return (
    <div className="belief-bars evidence-belief">
      {STATES.map((s, i) => (
        <div key={s} className="belief-row">
          <span className="belief-label evidence-state">{s}</span>
          <ProgressBar value={(belief[i] || 0) * 100} max={100} height={6} color={STATE_COLOR[s]} />
          <span className="belief-pct">
            {Math.round((belief[i] || 0) * 100)}%
          </span>
        </div>
      ))}
    </div>
  );
}

function EvidenceItem({ item }) {
  const meta = sourceMeta(item.source);
  const Icon = meta.icon;

  return (
    <Card style={{ marginBottom: 14 }}>
      <div className="row-between" style={{ flexWrap: "wrap", gap: 10 }}>
        <div className="row" style={{ gap: 10 }}>
          <div className="evidence-icon">
            <Icon size={16} />
          </div>

          <div>
            <div className="evidence-turn">Turn {item.seq}</div>
            <Badge tone={meta.tone}>{meta.label}</Badge>
          </div>
        </div>

        {item.score !== undefined && item.score !== null && (
          <div className="evidence-score">{item.score}/10</div>
        )}

        {item.outcome && <Badge tone="info">{item.outcome.replace(/_/g, " ")}</Badge>}
      </div>

      <p className="evidence-description">{item.description}</p>

      {item.source === "mkt" && (
        <div className="evidence-beliefs">
          <div>
            <div className="metric-label">Belief before</div>
            <BeliefBars belief={item.belief_before} />
          </div>

          <div>
            <div className="metric-label">Belief after</div>
            <BeliefBars belief={item.belief_after} />
          </div>
        </div>
      )}

      {item.source === "comms" && item.metrics && (
        <div className="evidence-metrics">
          {Object.entries(item.metrics)
            .filter(([k]) => k !== "session_id" && k !== "seq")
            .map(([k, v]) => (
              <div key={k} className="evidence-metric">
                <strong className="text-strong">{typeof v === "number" ? Math.round(v * 100) / 100 : String(v)}</strong>{" "}
                {k.replace(/_/g, " ")}
              </div>
            ))}
        </div>
      )}
    </Card>
  );
}

export default function EvidenceTimeline({ sessionId }) {
  const [state, setState] = useState({ loading: true, error: null, items: [] });

  useEffect(() => {
    let cancelled = false;

    setState({ loading: true, error: null, items: [] });

    getSessionEvidence(sessionId)
      .then((data) => {
        if (!cancelled) setState({ loading: false, error: null, items: data.items || [] });
      })
      .catch((err) => {
        if (!cancelled) {
          setState({
            loading: false,
            error: err.response?.data?.detail || "Failed to load the evidence trail.",
            items: [],
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  if (state.loading) {
    return <p className="evidence-status muted">Loading evidence trail…</p>;
  }

  if (state.error) {
    return <p className="evidence-status text-danger">{state.error}</p>;
  }

  if (state.items.length === 0) {
    return <p className="evidence-status muted">No evidence was recorded for this session.</p>;
  }

  return (
    <div className="evidence-timeline">
      <p className="report-section-note" style={{ marginBottom: 16 }}>
        The raw signal trail behind this session's evaluation — every turn score, knowledge
        probe and belief update, and communication/emotion sample, in the order it was recorded.
      </p>

      {state.items.map((item, idx) => (
        <EvidenceItem key={idx} item={item} />
      ))}
    </div>
  );
}
