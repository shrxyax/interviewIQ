import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Building2 } from "lucide-react";

import { getCompanies } from "../services/content";
import Card from "../components/shared/Card";
import Badge from "../components/shared/Badge";
import { LoadingState, ErrorState } from "../components/shared/LoadingState";

export default function CompaniesPage() {
  const [companies, setCompanies] = useState(null);
  const [error, setError] = useState(null);
  const navigate = useNavigate();

  const load = () => {
    setError(null);
    getCompanies().then(setCompanies).catch((e) => setError(e.message || "Failed to load companies."));
  };

  useEffect(() => {
    load();
  }, []);

  if (error) return <ErrorState message={`Couldn't load companies: ${error}`} onRetry={load} />;
  if (!companies) return <LoadingState label="Loading companies..." />;

  return (
    <div className="page-content">
      <div className="page-header">
        <h1>Company Preparation</h1>
        <p>Pick a company to see your readiness, weighted by what that company actually tests for.</p>
      </div>

      <div className="grid grid-3">
        {companies.map((c) => (
          <Card key={c.id} hoverable onClick={() => navigate(`/companies/${c.id}`)}>
            <div className="row" style={{ gap: 12, marginBottom: 12 }}>
              <div className="company-logo">
                <Building2 size={20} color="var(--primary)" />
              </div>
              <div>
                <div className="company-name">{c.name}</div>
                {c.tier === "top" && <Badge tone="info">Top Tier</Badge>}
              </div>
            </div>
            <div className="company-rounds">
              {c.rounds.map((r) => (
                <span key={r} className="company-round">
                  {r}
                </span>
              ))}
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
