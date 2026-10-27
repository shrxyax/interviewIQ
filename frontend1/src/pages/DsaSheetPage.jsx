import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Check, ExternalLink, Circle, Clock, BrainCircuit } from "lucide-react";

import { getDsaSheet, setProblemStatus } from "../services/content";
import Badge from "../components/shared/Badge";
import Card from "../components/shared/Card";
import ProgressBar from "../components/shared/ProgressBar";
import "./DsaSheetPage.css";

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
        <div className="row-between" style={{ alignItems: "baseline", marginBottom: 10 }}>
          <span className="note">Your Progress</span>
          <span className="dsa-progress-count">
            {sheet.solved} / {sheet.total}
          </span>
        </div>
        <ProgressBar value={sheet.solved} max={sheet.total} />
      </Card>

      <input
        placeholder="Search problems or patterns..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="field dsa-search"
        aria-label="Search problems or patterns"
        type="search"
      />

      <div className="tab-row scroll">
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

      <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            <th className="dsa-status-col"><span className="sr-only">Status</span></th>
            <th>Problem</th>
            <th className="dsa-topic-col">Topic</th>
            <th>Difficulty</th>
            <th>Pattern</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {problems.map((p) => (
            <tr key={p.id}>
              <td>
                <button onClick={() => cycleStatus(p)} className="dsa-icon-btn" title="Click to cycle: unsolved -> solved -> revisit" aria-label={`Status: ${p.status || "unsolved"}. Click to change`}>
                  <StatusIcon status={p.status} />
                </button>
              </td>
              <td className={`dsa-title ${p.status === "solved" ? "solved" : ""}`}>
                {p.title}
              </td>
              <td className="dsa-meta dsa-topic-col">{p.topicName}</td>
              <td><Badge difficulty={p.difficulty}>{p.difficulty}</Badge></td>
              <td className="dsa-meta">{p.pattern}</td>
              <td>
                <div className="dsa-actions">
                  {p.leetcode_url && (
                    <a href={p.leetcode_url} target="_blank" rel="noreferrer" title="Open on LeetCode" aria-label={`Open ${p.title} on LeetCode`} className="dsa-icon-btn muted">
                      <ExternalLink size={15} />
                    </a>
                  )}
                  {p.concept_id && (
                    <button
                      onClick={() => navigate("/mkt", { state: { conceptId: p.concept_id } })}
                      title="Test your robustness on this concept"
                      aria-label="Test your robustness on this concept"
                      className="dsa-icon-btn"
                      style={{ color: "var(--primary)" }}
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
      </div>

      {problems.length === 0 && <p className="spinner-text">No problems match your search.</p>}
    </div>
  );
}
