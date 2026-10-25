import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";

import { getCoreCs } from "../services/content";
import Card from "../components/shared/Card";

export default function CoreCsPage() {
  const [data, setData] = useState(null);
  const [activeTopic, setActiveTopic] = useState(null);

  useEffect(() => {
    getCoreCs().then((d) => {
      setData(d);
      setActiveTopic(d.topics[0]?.id);
    });
  }, []);

  if (!data) return <div className="page-content"><p className="spinner-text">Loading Core CS notes...</p></div>;

  const topic = data.topics.find((t) => t.id === activeTopic);

  return (
    <div className="page-content">
      <div className="page-header">
        <h1>Core CS Fundamentals</h1>
        <p>Short, interview-focused notes on Operating Systems, DBMS, Computer Networks, OOP, and Architecture.</p>
      </div>

      <div className="tab-row">
        {data.topics.map((t) => (
          <button
            key={t.id}
            className={`tab-btn ${activeTopic === t.id ? "active" : ""}`}
            onClick={() => setActiveTopic(t.id)}
          >
            {t.name}
          </button>
        ))}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {topic?.notes.map((note) => (
          <Card key={note.id}>
            <h3 style={{ fontSize: 17, marginBottom: 10 }}>{note.title}</h3>
            <div style={{ color: "var(--muted)", fontSize: 14.5, lineHeight: 1.8 }} className="markdown-note">
              <ReactMarkdown>{note.body_markdown}</ReactMarkdown>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
