import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, Sparkles } from "lucide-react";

import { login, register } from "../services/auth";
import "./AuthPage.css";

export default function SignInPage() {
  const navigate = useNavigate();
  const [mode, setMode] = useState("signin"); // "signin" | "signup"
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);

    try {
      if (mode === "signin") {
        await login(username.trim(), password);
      } else {
        await register(username.trim(), password);
      }
      // Signing in means they're past the intro. Hard-navigate so App
      // re-reads onboarding state and every page refetches as this user.
      localStorage.setItem("iq_onboarded", "true");
      window.location.assign("/");
      return;
    } catch (err) {
      // FastAPI returns `detail` as a list of objects for 422 validation
      // errors; rendering that directly would crash the page.
      const detail = err.response?.data?.detail;
      setError(
        typeof detail === "string"
          ? detail
          : Array.isArray(detail)
          ? "Username must be at least 3 characters and password at least 6."
          : err.response
          ? mode === "signin"
            ? "Invalid username or password."
            : "Could not create that account."
          : "Can't reach the server. Is the backend running on port 8000?"
      );
    } finally {
      setSubmitting(false);
    }
  };

  const switchMode = (next) => {
    setMode(next);
    setError("");
  };

  return (
    <div className="auth-page">
      <button className="auth-back" onClick={() => navigate("/onboarding")}>
        <ArrowLeft size={16} /> Back
      </button>

      <div className="auth-card">
        <div className="auth-mark">
          <Sparkles size={22} color="var(--on-primary)" />
        </div>

        <div className="auth-switch">
          <button
            type="button"
            className={mode === "signin" ? "active" : ""}
            onClick={() => switchMode("signin")}
          >
            Sign In
          </button>
          <button
            type="button"
            className={mode === "signup" ? "active" : ""}
            onClick={() => switchMode("signup")}
          >
            Create Account
          </button>
        </div>

        <h1>{mode === "signin" ? "Welcome back" : "Create your account"}</h1>
        <p className="auth-card-subtitle">
          {mode === "signin"
            ? "Sign in to pick up where you left off."
            : "Claim a username and password to keep your progress across devices."}
        </p>

        <form className="auth-form" onSubmit={handleSubmit}>
          <input
            className="auth-input"
            placeholder="Username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoFocus
          />
          <input
            className="auth-input"
            placeholder="Password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />

          {error && <div className="auth-error">{error}</div>}

          <button className="auth-submit" type="submit" disabled={submitting || !username.trim() || !password}>
            {submitting
              ? mode === "signin"
                ? "Signing in..."
                : "Creating account..."
              : mode === "signin"
              ? "Sign In"
              : "Create Account"}
          </button>
        </form>

        <div className="auth-footer">
          {mode === "signin" ? (
            <>
              Don't have an account?{" "}
              <button onClick={() => switchMode("signup")}>Create one</button>
            </>
          ) : (
            <>
              Already have an account?{" "}
              <button onClick={() => switchMode("signin")}>Sign in</button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
