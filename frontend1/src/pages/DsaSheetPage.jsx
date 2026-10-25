import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Check, ExternalLink, Circle, Clock, BrainCircuit } from "lucide-react";

import { getDsaSheet, setProblemStatus } from "../services/content";
import Badge from "../components/shared/Badge";
import Card from "../components/shared/Card";
import ProgressBar from "../components/shared/ProgressBar";

const STATUS_CYCLE = ["unsolved", "solved", "revisit"];

function StatusIcon({ status }) {
  if (status === "solved") return <Check size={16} color="var(--success)" />;
  if (status === "revisit") return <Clock size={16} color="var(--warning)" />;
  return <Circle size={16} color="var(--muted)" />;
}

export default function DsaSheetPage() {
  const navigate = useNavigate();
  const [sheet, setSheet] = useState(null);
  const [activeTopic, setActiveTopic] = useState("all");
  const [search, setSearch] = useState("");
  const [error, setError] = useState(null);

  const load = () => getDsaSheet().then(setSheet).catch((e) => setError(e.message));

  useEffect(() => {
    load();
  }, []);

  const problems = useMemo(() => {
    if (!sheet) return [];

    const rows = [];
    for (const topic of sheet.topics) {
      if (activeTopic !== "all" && topic.id !== activeTopic) continue;
      for (const p of topic.problems) {
        rows.push({ ...p, topicName: topic.name });
      }
    }

    if (!search.trim()) return rows;
    const q = search.toLowerCase();
    return rows.filter((r) => r.title.toLowerCase().includes(q) || r.pattern.toLowerCase().includes(q));
  }, [sheet, activeTopic, search]);

  const cycleStatus = async (problem) => {
    const next = STATUS_CYCLE[(STATUS_CYCLE.indexOf(problem.status) + 1) % STATUS_CYCLE.length];
    await setProblemStatus(problem.id, next);
    load();
  };

  if (error) return <div className="page-content"><p className="spinner-text">Couldn't load the sheet: {error}</p></div>;
  if (!sheet) return <div className="page-content"><p className="spinner-text">Loading DSA sheet...</p></div>;

  return (
    <div className="page-content">
      <div className="page-header">
        <h1>DSA Practice Sheet</h1>
        <p>{sheet.total} problems across {sheet.topics.length} topics, curated from a public DSA prep repository.</p>
      </div>

      <Card style={{ marginBottom: 24 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 10 }}>
          <span style={{ color: "var(--muted)", fontSize: 13 }}>Your Progress</span>
          <span style={{ fontSize: 22, fontWeight: 700 }}>
            {sheet.solved} / {sheet.total}
          </span>
        </div>
        <ProgressBar value={sheet.solved} max={sheet.total} />
      </Card>

      <input
        placeholder="Search problems or patterns..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        style={{
          background: "var(--card)", border: "1px solid var(--border)", borderRadius: 12,
          padding: "12px 16px", color: "var(--text)", marginBottom: 16, fontSize: 14, outline: "none",
        }}
      />

      <div className="tab-row">
        <button className={`tab-btn ${activeTopic === "all" ? "active" : ""}`} onClick={() => setActiveTopic("all")}>
          All
        </button>
        {sheet.topics.map((t) => (
          <button
            key={t.id}
            className={`tab-btn ${activeTopic === t.id ? "active" : ""}`}
            onClick={() => setActiveTopic(t.id)}
          >
            {t.name} ({t.solved}/{t.total})
          </button>
        ))}
      </div>

      <table className="data-table">
        <thead>
          <tr>
            <th style={{ width: 36 }}></th>
            <th>Problem</th>
            <th>Topic</th>
            <th>Difficulty</th>
            <th>Pattern</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {problems.map((p) => (
            <tr key={p.id}>
              <td>
                <button onClick={() => cycleStatus(p)} style={{ background: "none", border: "none", display: "flex", padding: 0 }} title="Click to cycle: unsolved -> solved -> revisit">
                  <StatusIcon status={p.status} />
                </button>
              </td>
              <td style={{ fontWeight: 500, textDecoration: p.status === "solved" ? "line-through" : "none", color: p.status === "solved" ? "var(--muted)" : "var(--text)" }}>
                {p.title}
              </td>
              <td style={{ color: "var(--muted)", fontSize: 13 }}>{p.topicName}</td>
              <td><Badge difficulty={p.difficulty}>{p.difficulty}</Badge></td>
              <td style={{ color: "var(--muted)", fontSize: 13 }}>{p.pattern}</td>
              <td>
                <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
                  {p.leetcode_url && (
                    <a href={p.leetcode_url} target="_blank" rel="noreferrer" title="Open on LeetCode" style={{ color: "var(--muted)", display: "flex" }}>
                      <ExternalLink size={15} />
                    </a>
                  )}
                  {p.concept_id && (
                    <button
                      onClick={() => navigate("/mkt", { state: { conceptId: p.concept_id } })}
                      title="Test your robustness on this concept"
                      style={{ background: "none", border: "none", color: "var(--primary)", display: "flex", padding: 0 }}
                    >
                      <BrainCircuit size={15} />
                    </button>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {problems.length === 0 && <p className="spinner-text">No problems match your search.</p>}
    </div>
  );
}
