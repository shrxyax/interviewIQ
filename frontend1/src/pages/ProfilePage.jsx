import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Copy, LogIn, LogOut, ShieldCheck } from "lucide-react";

import { getDsaSheet } from "../services/content";
import { getProfileBeliefs } from "../services/mkt";
import { getUsername, getGeneratedPassword, isTransientGuest, logout, register } from "../services/auth";
import Card from "../components/shared/Card";
import ProgressBar from "../components/shared/ProgressBar";

const STATE_COLOR = { robust: "var(--success)", memorised: "var(--warning)", misconceived: "var(--danger)", absent: "var(--muted)" };
const STATE_LABEL = { robust: "Robust", memorised: "Memorised", misconceived: "Misconceived", absent: "Absent" };

export default function ProfilePage() {
  const navigate = useNavigate();
  const [sheet, setSheet] = useState(null);
  const [beliefs, setBeliefs] = useState(null);
  const [claiming, setClaiming] = useState(false);
  const [form, setForm] = useState({ username: "", password: "" });
  const [claimError, setClaimError] = useState("");

  useEffect(() => {
    getDsaSheet().then(setSheet).catch(() => {});
    getProfileBeliefs().then(setBeliefs).catch(() => {});
  }, []);

  const username = getUsername();
  const isGuest = isTransientGuest();
  const generatedPassword = getGeneratedPassword();

  const probed = beliefs?.concepts || [];
  const meanRobustness =
    probed.length > 0
      ? Math.round((probed.reduce((s, c) => s + (c.robustness_index ?? 0.5), 0) / probed.length) * 100)
      : null;

  const handleClaim = async (e) => {
    e.preventDefault();
    setClaimError("");
    try {
      await register(form.username, form.password);
      window.location.reload();
    } catch (err) {
      setClaimError(err.response?.data?.detail || "Could not create that account.");
    }
  };

  const handleSignOut = () => {
    logout();
    window.location.assign("/sign-in");
  };

  return (
    <div className="page-content">
      <div className="page-header">
        <h1>Profile</h1>
        <p>Your candidate intelligence: practice progress and measured knowledge robustness.</p>
      </div>

      <div className="grid grid-2" style={{ alignItems: "start" }}>
        <Card>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, marginBottom: 16 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <div
                style={{
                  width: 48, height: 48, borderRadius: 999, background: "var(--primary-soft)",
                  color: "var(--primary)", display: "flex", alignItems: "center", justifyContent: "center",
                  fontWeight: 700, fontSize: 18,
                }}
              >
                {username.replace(/^guest_/, "").charAt(0).toUpperCase()}
              </div>
              <div>
                <div style={{ fontWeight: 700, fontSize: 16 }}>{username}</div>
                <div style={{ color: "var(--muted)", fontSize: 13, display: "flex", alignItems: "center", gap: 6 }}>
                  {isGuest ? "Temporary guest session" : (
                    <>
                      <ShieldCheck size={13} color="var(--success)" /> Signed in
                    </>
                  )}
                </div>
              </div>
            </div>

            <button
              onClick={handleSignOut}
              title="Sign out"
              style={{
                display: "flex", alignItems: "center", gap: 6, flexShrink: 0,
                background: "transparent", border: "1px solid var(--border)", borderRadius: 10,
                padding: "8px 12px", color: "var(--muted)", fontSize: 12.5, fontWeight: 600,
              }}
            >
              <LogOut size={13} /> Sign out
            </button>
          </div>

          {isGuest && (
            <>
              <p style={{ color: "var(--muted)", fontSize: 13, marginBottom: 12 }}>
                This browser was given a temporary account so your progress is saved. Set your own username and
                password to keep access from another device.
              </p>

              <div
                style={{
                  background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 10,
                  padding: "10px 12px", fontSize: 13, display: "flex", justifyContent: "space-between",
                  alignItems: "center", marginBottom: 12, fontFamily: "monospace",
                }}
              >
                <span>{username} / {generatedPassword}</span>
                <button
                  onClick={() => navigator.clipboard?.writeText(`${username} / ${generatedPassword}`)}
                  style={{ background: "none", border: "none", color: "var(--muted)", display: "flex" }}
                  title="Copy credentials"
                >
                  <Copy size={14} />
                </button>
              </div>

              {!claiming ? (
                <button
                  onClick={() => setClaiming(true)}
                  style={{
                    width: "100%", padding: "10px 0", borderRadius: 10, border: "1px solid var(--border)",
                    background: "transparent", color: "var(--text)", fontWeight: 600, fontSize: 13,
                    display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
                  }}
                >
                  <LogIn size={14} /> Set a permanent username &amp; password
                </button>
              ) : (
                <form onSubmit={handleClaim} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  <input
                    placeholder="Username"
                    value={form.username}
                    onChange={(e) => setForm((f) => ({ ...f, username: e.target.value }))}
                    style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 8, padding: "9px 12px", color: "var(--text)", fontSize: 13 }}
                  />
                  <input
                    placeholder="Password"
                    type="password"
                    value={form.password}
                    onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
                    style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 8, padding: "9px 12px", color: "var(--text)", fontSize: 13 }}
                  />
                  {claimError && <span style={{ color: "var(--danger)", fontSize: 12 }}>{claimError}</span>}
                  <button type="submit" style={{ background: "var(--primary)", color: "white", border: "none", borderRadius: 8, padding: "9px 0", fontWeight: 600, fontSize: 13 }}>
                    Save
                  </button>
                </form>
              )}
            </>
          )}
        </Card>

        <Card>
          <div style={{ color: "var(--muted)", fontSize: 13, marginBottom: 8 }}>DSA Sheet Progress</div>
          {sheet ? (
            <>
              <div style={{ fontSize: 26, fontWeight: 700, marginBottom: 10 }}>{sheet.solved} / {sheet.total}</div>
              <ProgressBar value={sheet.solved} max={sheet.total} />
            </>
          ) : (
            <p className="spinner-text">Loading...</p>
          )}
          <button
            onClick={() => navigate("/dsa-sheet")}
            style={{ marginTop: 14, background: "none", border: "none", color: "var(--primary)", fontSize: 13, fontWeight: 600, padding: 0 }}
          >
            Go to sheet &rarr;
          </button>
        </Card>
      </div>

      <h2 style={{ fontSize: 18, margin: "32px 0 14px" }}>Knowledge Robustness</h2>

      {probed.length === 0 ? (
        <Card>
          <p style={{ color: "var(--muted)", fontSize: 14 }}>
            You haven't been probed on any concepts yet.{" "}
            <button onClick={() => navigate("/mkt")} style={{ background: "none", border: "none", color: "var(--primary)", fontWeight: 600, padding: 0 }}>
              Start a Metamorphic Knowledge Testing session &rarr;
            </button>
          </p>
        </Card>
      ) : (
        <>
          {meanRobustness !== null && (
            <Card style={{ marginBottom: 16 }}>
              <div style={{ color: "var(--muted)", fontSize: 13, marginBottom: 6 }}>Mean Robustness Index</div>
              <div style={{ fontSize: 26, fontWeight: 700 }}>{meanRobustness}%</div>
            </Card>
          )}

          <div className="grid grid-3">
            {probed.map((c) => (
              <Card key={c.id}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
                  <span style={{ fontWeight: 600, fontSize: 14 }}>{c.name}</span>
                  <span style={{ fontSize: 12, fontWeight: 700, color: STATE_COLOR[c.most_likely] }}>
                    {STATE_LABEL[c.most_likely]}
                  </span>
                </div>
                {["absent", "memorised", "misconceived", "robust"].map((s) => (
                  <div key={s} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                    <span style={{ width: 70, fontSize: 10.5, color: "var(--muted)" }}>{STATE_LABEL[s]}</span>
                    <ProgressBar value={c.belief[s] * 100} max={100} height={5} color={STATE_COLOR[s]} />
                  </div>
                ))}
              </Card>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
