import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, ListChecks, Workflow } from "lucide-react";

import { getCompanyReadiness, getCompanyPlan } from "../services/content";
import Card from "../components/shared/Card";
import ProgressBar from "../components/shared/ProgressBar";
import { LoadingState, ErrorState } from "../components/shared/LoadingState";
import "./CompanyPages.css";

function readinessColor(pct) {
  if (pct >= 70) return "var(--success)";
  if (pct >= 40) return "var(--warning)";
  return "var(--danger)";
}

export default function CompanyDetailPage() {
  const { companyId } = useParams();
  const navigate = useNavigate();
  const [readiness, setReadiness] = useState(null);
  const [plan, setPlan] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(() => {
    setError(null);
    getCompanyReadiness(companyId).then(setReadiness).catch((e) => setError(e.message || "Failed to load readiness."));
    getCompanyPlan(companyId).then(setPlan).catch(() => {});
  }, [companyId]);

  useEffect(() => {
    load();
  }, [load]);

  if (error) return <ErrorState message={`Couldn't load this company: ${error}`} onRetry={load} />;
  if (!readiness) return <LoadingState label="Loading readiness..." />;

  return (
    <div className="page-content">
      <div className="breadcrumb">
        <Link to="/companies">Companies</Link> / <span className="current">{readiness.company.name}</span>
      </div>

      <div className="page-header row-between">
        <div>
          <h1>{readiness.company.name}</h1>
          <p>{readiness.company.rounds.join(" · ")}</p>
        </div>
        <button onClick={() => navigate(-1)} className="text-btn" style={{ fontSize: 14 }}>
          <ArrowLeft size={16} /> Back
        </button>
      </div>

      <Card style={{ marginBottom: 24 }}>
        <div className="row-between" style={{ marginBottom: 10 }}>
          <span className="note">Overall Readiness</span>
          <span className="company-readiness" style={{ color: readinessColor(readiness.readiness_pct) }}>
            {readiness.readiness_pct}%
          </span>
        </div>
        <ProgressBar value={readiness.readiness_pct} max={100} color={readinessColor(readiness.readiness_pct)} />
        <p className="note" style={{ fontSize: 12.5, marginTop: 10 }}>
          Weighted across DSA topics (from solved problems and Metamorphic Knowledge Testing beliefs) and system-design
          subtopics (from completed Executable Whiteboard sessions), using {readiness.company.name}'s own emphasis.
        </p>
      </Card>

      <div className="grid grid-2" style={{ alignItems: "start", gap: 24 }}>
        <div>
          <h2 className="company-section-title">Breakdown</h2>
          <Card>
            {readiness.breakdown.map((b) => (
              <div key={`${b.type}:${b.id}`} className="company-breakdown-item">
                <div className="row-between company-breakdown-head">
                  <span>{b.name}</span>
                  <span className="muted">{Math.round(b.mastery * 100)}%</span>
                </div>
                <ProgressBar value={b.mastery * 100} max={100} height={6} />
              </div>
            ))}
          </Card>
        </div>

        <div>
          <h2 className="company-section-title">Recommended Plan</h2>
          {!plan || plan.length === 0 ? (
            <Card><p className="muted" style={{ fontSize: 14 }}>You're well prepared across every weighted area.</p></Card>
          ) : (
            <div className="stack" style={{ gap: 10 }}>
              {plan.map((item) => (
                <Card key={`${item.type}:${item.ref_id}`}>
                  <div className="row-between" style={{ alignItems: "flex-start" }}>
                    <div>
                      <div className="company-plan-focus">{item.focus}</div>
                      <div className="company-plan-action">{item.action}</div>
                      <div className="company-plan-reason">{item.reason}</div>
                    </div>
                    <button
                      onClick={() => navigate(item.type === "dsa_topic" ? "/dsa-sheet" : "/design")}
                      className="btn btn-soft company-plan-go"
                      aria-label={item.type === "dsa_topic" ? "Open DSA sheet" : "Open System Design Lab"}
                      title={item.type === "dsa_topic" ? "Open DSA sheet" : "Open System Design Lab"}
                    >
                      {item.type === "dsa_topic" ? <ListChecks size={15} /> : <Workflow size={15} />}
                    </button>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
