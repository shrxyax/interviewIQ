import { useEffect, useState } from "react";
import { Brain, MessageSquareText, Smile, HelpCircle } from "lucide-react";

import { getSessionEvidence } from "../services/interviewContext";
import Card from "./shared/Card";
import Badge from "./shared/Badge";
import ProgressBar from "./shared/ProgressBar";

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
    <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 10 }}>
      {STATES.map((s, i) => (
        <div key={s} style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ width: 76, fontSize: 11, color: "var(--muted)", textTransform: "capitalize" }}>{s}</span>
          <ProgressBar value={(belief[i] || 0) * 100} max={100} height={6} color={STATE_COLOR[s]} />
          <span style={{ width: 34, fontSize: 11, color: "var(--muted)", textAlign: "right" }}>
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
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div
            style={{
              width: 32, height: 32, borderRadius: 10, display: "flex", alignItems: "center", justifyContent: "center",
              background: "var(--card-hover)",
            }}
          >
            <Icon size={16} />
          </div>

          <div>
            <div style={{ fontSize: 12, color: "var(--muted)", fontWeight: 600 }}>Turn {item.seq}</div>
            <Badge tone={meta.tone}>{meta.label}</Badge>
          </div>
        </div>

        {item.score !== undefined && item.score !== null && (
          <div style={{ fontSize: 13, fontWeight: 700 }}>{item.score}/10</div>
        )}

        {item.outcome && <Badge tone="info">{item.outcome.replace(/_/g, " ")}</Badge>}
      </div>

      <p style={{ marginTop: 10, fontSize: 13.5, lineHeight: 1.5 }}>{item.description}</p>

      {item.source === "mkt" && (
        <div style={{ display: "flex", gap: 20, flexWrap: "wrap" }}>
          <div style={{ flex: 1, minWidth: 180 }}>
            <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 2 }}>Belief before</div>
            <BeliefBars belief={item.belief_before} />
          </div>

          <div style={{ flex: 1, minWidth: 180 }}>
            <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 2 }}>Belief after</div>
            <BeliefBars belief={item.belief_after} />
          </div>
        </div>
      )}

      {item.source === "comms" && item.metrics && (
        <div style={{ display: "flex", gap: 14, flexWrap: "wrap", marginTop: 8 }}>
          {Object.entries(item.metrics)
            .filter(([k]) => k !== "session_id" && k !== "seq")
            .map(([k, v]) => (
              <div key={k} style={{ fontSize: 11.5, color: "var(--muted)" }}>
                <strong style={{ color: "var(--text)" }}>{typeof v === "number" ? Math.round(v * 100) / 100 : String(v)}</strong>{" "}
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
    return <p style={{ color: "var(--muted)", padding: "20px 0" }}>Loading evidence trail…</p>;
  }

  if (state.error) {
    return <p style={{ color: "var(--danger)", padding: "20px 0" }}>{state.error}</p>;
  }

  if (state.items.length === 0) {
    return <p style={{ color: "var(--muted)", padding: "20px 0" }}>No evidence was recorded for this session.</p>;
  }

  return (
    <div style={{ padding: "4px 0 20px" }}>
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
