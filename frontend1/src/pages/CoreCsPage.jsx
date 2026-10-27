import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { CheckCircle2, Search } from "lucide-react";

import { getCoreCs } from "../services/content";
import { getReadTopics } from "../services/coreCsProgress";
import ProgressBar from "../components/shared/ProgressBar";
import { LoadingState, ErrorState } from "../components/shared/LoadingState";
import "./CoreCs.css";

// "core_cs.os" -> "os", used as the ?subject= value.
const shortId = (id) => id.replace(/^core_cs\./, "");

export default function CoreCsPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [query, setQuery] = useState("");
  const [searchParams, setSearchParams] = useSearchParams();
  const [read] = useState(getReadTopics);

  const load = () => {
    setError(null);
    getCoreCs()
      .then(setData)
      .catch((e) => setError(e.message || "Failed to load Core CS topics."));
  };

  useEffect(() => {
    load();
  }, []);

  const subjects = useMemo(() => data?.topics ?? [], [data]);
  const active =
    subjects.find((s) => shortId(s.id) === searchParams.get("subject")) || subjects[0];

  // Searching looks across every subject, not just the selected one.
  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return null;

    return subjects.flatMap((s) =>
      s.notes
        .filter((n) => n.title.toLowerCase().includes(q) || n.summary.toLowerCase().includes(q))
        .map((n) => ({ ...n, subject: s }))
    );
  }, [query, subjects]);

  if (error) return <ErrorState message={`Couldn't load Core CS topics: ${error}`} onRetry={load} />;
  if (!data) return <LoadingState label="Loading Core CS topics..." />;

  const total = subjects.reduce((sum, s) => sum + s.notes.length, 0);
  const readIn = (s) => s.notes.filter((n) => read.has(n.id)).length;

  return (
    <div className="page-content">
      <div className="page-header">
        <h1>Core CS Fundamentals</h1>
        <p>
          {total} interview topics across {subjects.length} subjects. Pick a topic to read its full notes,
          examples and common interview questions.
        </p>
      </div>

      <div className="cs-search">
        <Search size={16} />
        <input
          type="search"
          className="field"
          placeholder="Search all topics (e.g. deadlock, indexing, TCP)"
          aria-label="Search Core CS topics"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>

      {results ? (
        <>
          <p className="note cs-result-count">
            {results.length} {results.length === 1 ? "topic" : "topics"} matching “{query.trim()}”
          </p>
          <div className="cs-topic-grid">
            {results.map((n) => (
              <TopicCard key={n.id} note={n} subjectName={n.subject.name} read={read.has(n.id)} />
            ))}
          </div>
        </>
      ) : (
        <>
          <div className="tab-row scroll" role="tablist" aria-label="Subjects">
            {subjects.map((s) => (
              <button
                key={s.id}
                role="tab"
                aria-selected={s.id === active.id}
                className={`tab-btn ${s.id === active.id ? "active" : ""}`}
                onClick={() => setSearchParams({ subject: shortId(s.id) }, { replace: true })}
              >
                {s.name} <span className="cs-tab-count">{s.notes.length}</span>
              </button>
            ))}
          </div>

          <div className="cs-subject-progress">
            <span className="note">
              {readIn(active)} of {active.notes.length} topics read
            </span>
            <ProgressBar value={readIn(active)} max={active.notes.length} height={6} />
          </div>

          <ol className="cs-topic-grid">
            {active.notes.map((n, i) => (
              <li key={n.id}>
                <TopicCard note={n} number={i + 1} read={read.has(n.id)} />
              </li>
            ))}
          </ol>
        </>
      )}
    </div>
  );
}

function TopicCard({ note, number, subjectName, read }) {
  return (
    <Link to={`/core-cs/${note.id}`} className={`cs-topic-card ${read ? "read" : ""}`}>
      <div className="cs-topic-head">
        {number !== undefined && <span className="cs-topic-number">{String(number).padStart(2, "0")}</span>}
        {subjectName && <span className="cs-topic-subject">{subjectName}</span>}
        {read && (
          <span className="cs-topic-read">
            <CheckCircle2 size={14} /> Read
          </span>
        )}
      </div>
      <h3>{note.title}</h3>
      <p>{note.summary}</p>
    </Link>
  );
}
