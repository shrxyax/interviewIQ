import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Building2 } from "lucide-react";

import { getCompanies } from "../services/content";
import Card from "../components/shared/Card";
import Badge from "../components/shared/Badge";

export default function CompaniesPage() {
  const [companies, setCompanies] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    getCompanies().then(setCompanies);
  }, []);

  if (!companies) return <div className="page-content"><p className="spinner-text">Loading companies...</p></div>;

  return (
    <div className="page-content">
      <div className="page-header">
        <h1>Company Preparation</h1>
        <p>Pick a company to see your readiness, weighted by what that company actually tests for.</p>
      </div>

      <div className="grid grid-3">
        {companies.map((c) => (
          <Card key={c.id} hoverable onClick={() => navigate(`/companies/${c.id}`)}>
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
              <div
                style={{
                  width: 42, height: 42, borderRadius: 10, background: "var(--primary-soft)",
                  display: "flex", alignItems: "center", justifyContent: "center",
                }}
              >
                <Building2 size={20} color="var(--primary)" />
              </div>
              <div>
                <div style={{ fontWeight: 700, fontSize: 15 }}>{c.name}</div>
                {c.tier === "top" && <Badge tone="info">Top Tier</Badge>}
              </div>
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {c.rounds.map((r) => (
                <span key={r} style={{ fontSize: 11.5, color: "var(--muted)", background: "var(--bg)", padding: "3px 8px", borderRadius: 6 }}>
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
