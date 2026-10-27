import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ArrowLeft, ArrowRight, CheckCircle2, Circle } from "lucide-react";

import { getCoreCsTopic } from "../services/content";
import { getReadTopics, setTopicRead } from "../services/coreCsProgress";
import { LoadingState, ErrorState } from "../components/shared/LoadingState";
import "./CoreCs.css";

const shortId = (id) => id.replace(/^core_cs\./, "");

export default function CoreCsTopicPage() {
  const { noteId } = useParams();
  const [topic, setTopic] = useState(null);
  const [error, setError] = useState(null);
  const [read, setRead] = useState(() => getReadTopics().has(noteId));

  const load = () => {
    setError(null);
    setTopic(null);
    getCoreCsTopic(noteId)
      .then(setTopic)
      .catch((e) =>
        setError(e.response?.status === 404 ? "That topic doesn't exist." : e.message || "Failed to load topic.")
      );
  };

  useEffect(() => {
    load();
    setRead(getReadTopics().has(noteId));
    document.querySelector(".page-content")?.scrollTo(0, 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [noteId]);

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!topic) return <LoadingState label="Loading topic..." />;

  const subjectLink = `/core-cs?subject=${shortId(topic.subject.id)}`;

  const toggleRead = () => {
    setTopicRead(topic.id, !read);
    setRead(!read);
  };

  return (
    <div className="page-content">
      <article className="cs-article">
        <div className="breadcrumb">
          <Link to="/core-cs">Core CS</Link> / <Link to={subjectLink}>{topic.subject.name}</Link> /{" "}
          <span className="current">{topic.title}</span>
        </div>

        <header className="cs-article-header">
          <span className="cs-article-position">
            Topic {topic.position} of {topic.total}
          </span>
          <h1>{topic.title}</h1>
        </header>

        <div className="cs-prose">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{topic.body_markdown}</ReactMarkdown>
        </div>

        <button
          type="button"
          className={`btn ${read ? "btn-tone-success" : "btn-secondary"} cs-read-toggle`}
          onClick={toggleRead}
          aria-pressed={read}
        >
          {read ? <CheckCircle2 size={16} /> : <Circle size={16} />}
          {read ? "Marked as read" : "Mark as read"}
        </button>

        <nav className="cs-pager" aria-label="Topic navigation">
          {topic.prev ? (
            <Link to={`/core-cs/${topic.prev.id}`} className="cs-pager-link">
              <span className="cs-pager-label">
                <ArrowLeft size={14} /> Previous
              </span>
              <span className="cs-pager-title">{topic.prev.title}</span>
            </Link>
          ) : (
            <span />
          )}
          {topic.next ? (
            <Link to={`/core-cs/${topic.next.id}`} className="cs-pager-link next">
              <span className="cs-pager-label">
                Next <ArrowRight size={14} />
              </span>
              <span className="cs-pager-title">{topic.next.title}</span>
            </Link>
          ) : (
            <Link to={subjectLink} className="cs-pager-link next">
              <span className="cs-pager-label">
                Done <ArrowRight size={14} />
              </span>
              <span className="cs-pager-title">Back to all {topic.subject.name} topics</span>
            </Link>
          )}
        </nav>
      </article>
    </div>
  );
}
