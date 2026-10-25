import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, ListChecks, Workflow } from "lucide-react";

import { getCompanyReadiness, getCompanyPlan } from "../services/content";
import Card from "../components/shared/Card";
import ProgressBar from "../components/shared/ProgressBar";

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

  useEffect(() => {
    getCompanyReadiness(companyId).then(setReadiness);
    getCompanyPlan(companyId).then(setPlan);
  }, [companyId]);

  if (!readiness) return <div className="page-content"><p className="spinner-text">Loading readiness...</p></div>;

  return (
    <div className="page-content">
      <div className="breadcrumb">
        <Link to="/companies">Companies</Link> / <span className="current">{readiness.company.name}</span>
      </div>

      <div className="page-header" style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <h1>{readiness.company.name}</h1>
          <p>{readiness.company.rounds.join(" · ")}</p>
        </div>
        <button onClick={() => navigate(-1)} style={{ background: "none", border: "none", color: "var(--muted)", display: "flex", alignItems: "center", gap: 6 }}>
          <ArrowLeft size={16} /> Back
        </button>
      </div>

      <Card style={{ marginBottom: 24 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
          <span style={{ color: "var(--muted)", fontSize: 13 }}>Overall Readiness</span>
          <span style={{ fontSize: 30, fontWeight: 800, color: readinessColor(readiness.readiness_pct) }}>
            {readiness.readiness_pct}%
          </span>
        </div>
        <ProgressBar value={readiness.readiness_pct} max={100} color={readinessColor(readiness.readiness_pct)} />
        <p style={{ color: "var(--muted)", fontSize: 12.5, marginTop: 10 }}>
          Weighted across DSA topics (from solved problems and Metamorphic Knowledge Testing beliefs) and system-design
          subtopics (from completed Executable Whiteboard sessions), using {readiness.company.name}'s own emphasis.
        </p>
      </Card>

      <div className="grid grid-2" style={{ alignItems: "start" }}>
        <div>
          <h2 style={{ fontSize: 16, marginBottom: 12 }}>Breakdown</h2>
          <Card>
            {readiness.breakdown.map((b) => (
              <div key={`${b.type}:${b.id}`} style={{ marginBottom: 14 }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 4 }}>
                  <span>{b.name}</span>
                  <span style={{ color: "var(--muted)" }}>{Math.round(b.mastery * 100)}%</span>
                </div>
                <ProgressBar value={b.mastery * 100} max={100} height={6} />
              </div>
            ))}
          </Card>
        </div>

        <div>
          <h2 style={{ fontSize: 16, marginBottom: 12 }}>Recommended Plan</h2>
          {!plan || plan.length === 0 ? (
            <Card><p style={{ color: "var(--muted)", fontSize: 14 }}>You're well prepared across every weighted area.</p></Card>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {plan.map((item) => (
                <Card key={`${item.type}:${item.ref_id}`}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: 14 }}>{item.focus}</div>
                      <div style={{ color: "var(--muted)", fontSize: 12.5, marginTop: 4 }}>{item.action}</div>
                      <div style={{ color: "var(--muted)", fontSize: 11.5, marginTop: 6 }}>{item.reason}</div>
                    </div>
                    <button
                      onClick={() => navigate(item.type === "dsa_topic" ? "/dsa-sheet" : "/design")}
                      style={{ background: "var(--primary-soft)", border: "none", color: "var(--primary)", borderRadius: 8, padding: 8, display: "flex", flexShrink: 0 }}
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
