import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Copy, LogIn, LogOut, ShieldCheck } from "lucide-react";

import { getDsaSheet } from "../services/content";
import { getProfileBeliefs } from "../services/mkt";
import { getUsername, getGeneratedPassword, isTransientGuest, logout, register } from "../services/auth";
import Card from "../components/shared/Card";
import ProgressBar from "../components/shared/ProgressBar";
import "./ProfilePage.css";

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

      <div className="grid grid-2 profile-grid">
        <Card>
          <div className="row-between" style={{ marginBottom: 16 }}>
            <div className="row" style={{ gap: 12, minWidth: 0 }}>
              <div className="profile-avatar">
                {username.replace(/^guest_/, "").charAt(0).toUpperCase()}
              </div>
              <div>
                <div className="profile-name">{username}</div>
                <div className="note row" style={{ gap: 6 }}>
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
              className="btn btn-sm profile-signout"
            >
              <LogOut size={13} /> Sign out
            </button>
          </div>

          {isGuest && (
            <>
              <p className="note" style={{ marginBottom: 12 }}>
                This browser was given a temporary account so your progress is saved. Set your own username and
                password to keep access from another device.
              </p>

              <div className="profile-credentials mono">
                <span>{username} / {generatedPassword}</span>
                <button
                  onClick={() => navigator.clipboard?.writeText(`${username} / ${generatedPassword}`)}
                  className="text-btn"
                  title="Copy credentials"
                  aria-label="Copy credentials"
                >
                  <Copy size={14} />
                </button>
              </div>

              {!claiming ? (
                <button
                  onClick={() => setClaiming(true)}
                  className="btn btn-secondary btn-block profile-claim"
                >
                  <LogIn size={14} /> Set a permanent username &amp; password
                </button>
              ) : (
                <form onSubmit={handleClaim} className="stack">
                  <input
                    placeholder="Username"
                    aria-label="Username"
                    autoComplete="username"
                    value={form.username}
                    onChange={(e) => setForm((f) => ({ ...f, username: e.target.value }))}
                    className="field profile-input"
                  />
                  <input
                    placeholder="Password"
                    type="password"
                    value={form.password}
                    onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
                    aria-label="Password"
                    autoComplete="new-password"
                    className="field profile-input"
                  />
                  {claimError && <span className="error-text" style={{ fontSize: 12 }}>{claimError}</span>}
                  <button type="submit" className="btn btn-primary btn-block profile-save">
                    Save
                  </button>
                </form>
              )}
            </>
          )}
        </Card>

        <Card>
          <div className="note" style={{ marginBottom: 8 }}>DSA Sheet Progress</div>
          {sheet ? (
            <>
              <div className="stat-value" style={{ marginTop: 0, marginBottom: 10 }}>{sheet.solved} / {sheet.total}</div>
              <ProgressBar value={sheet.solved} max={sheet.total} />
            </>
          ) : (
            <p className="spinner-text">Loading...</p>
          )}
          <button
            onClick={() => navigate("/dsa-sheet")}
            className="link-btn"
            style={{ marginTop: 14, fontSize: 13 }}
          >
            Go to sheet &rarr;
          </button>
        </Card>
      </div>

      <h2 className="section-title profile-section-title">Knowledge Robustness</h2>

      {probed.length === 0 ? (
        <Card>
          <p className="muted" style={{ fontSize: 14 }}>
            You haven't been probed on any concepts yet.{" "}
            <button onClick={() => navigate("/mkt")} className="link-btn">
              Start a Metamorphic Knowledge Testing session &rarr;
            </button>
          </p>
        </Card>
      ) : (
        <>
          {meanRobustness !== null && (
            <Card style={{ marginBottom: 16 }}>
              <div className="note" style={{ marginBottom: 6 }}>Mean Robustness Index</div>
              <div className="stat-value" style={{ marginTop: 0 }}>{meanRobustness}%</div>
            </Card>
          )}

          <div className="grid grid-3">
            {probed.map((c) => (
              <Card key={c.id}>
                <div className="concept-head">
                  <span className="concept-name">{c.name}</span>
                  <span className="concept-state" style={{ color: STATE_COLOR[c.most_likely] }}>
                    {STATE_LABEL[c.most_likely]}
                  </span>
                </div>
                {["absent", "memorised", "misconceived", "robust"].map((s) => (
                  <div key={s} className="belief-row" style={{ marginBottom: 4 }}>
                    <span className="belief-label">{STATE_LABEL[s]}</span>
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
