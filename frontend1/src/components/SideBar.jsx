import { NavLink, useNavigate } from "react-router-dom";
import {
  Plus,
  Video,
  Settings,
  LogOut,
  MessageSquare,
  ListChecks,
  BookOpen,
  Building2,
  BrainCircuit,
  Workflow,
  Code2,
  Calculator,
  Sparkles,
  RefreshCw,
} from "lucide-react";
import "./SideBar.css";
import { getUsername, isTransientGuest, logout } from "../services/auth";
import ThemeToggle from "./ThemeToggle";

const NAV_GROUPS = [
  {
    label: "Resume",
    items: [{ to: "/", icon: MessageSquare, label: "Chat & Mock Interview", end: true }],
  },
  {
    label: "Practice",
    items: [
      { to: "/dsa-sheet", icon: ListChecks, label: "DSA Sheet" },
      { to: "/core-cs", icon: BookOpen, label: "Core CS" },
      { to: "/code", icon: Code2, label: "Coding IDE" },
      { to: "/aptitude", icon: Calculator, label: "Aptitude Test" },
      { to: "/companies", icon: Building2, label: "Company Prep" },
    ],
  },
  {
    label: "Advanced Intelligence",
    items: [
      { to: "/mkt", icon: BrainCircuit, label: "Knowledge Testing" },
      { to: "/design", icon: Workflow, label: "System Design Lab" },
    ],
  },
  {
    label: "More",
    items: [{ to: "/onboarding", icon: RefreshCw, label: "Replay Intro" }],
  },
];

function linkStyle({ isActive }) {
  return {
    display: "flex",
    alignItems: "center",
    gap: 10,
    padding: "9px 10px",
    borderRadius: 10,
    fontSize: 13.5,
    fontWeight: isActive ? 600 : 500,
    color: isActive ? "var(--text)" : "var(--muted)",
    background: isActive ? "var(--primary-soft)" : "transparent",
    textDecoration: "none",
    transition: "background 0.2s ease, color 0.2s ease",
  };
}

export default function Sidebar() {
  const navigate = useNavigate();
  const username = getUsername();
  const initial = username.replace(/^guest_/, "").charAt(0).toUpperCase() || "G";
  const transient = isTransientGuest();

  const handleSignOut = (e) => {
    e.preventDefault();
    e.stopPropagation();
    logout();
    navigate("/sign-in");
  };

  return (
    <aside className="sidebar">
      <div style={{ overflowY: "auto", flex: 1, minHeight: 0 }}>
        <div className="logo">
          <div className="logo-brand">
            <div className="logo-mark">
              <Sparkles size={18} />
            </div>
            <h2>InterviewIQ</h2>
          </div>
          <ThemeToggle />
        </div>

        <button className="new-chat" onClick={() => navigate("/", { state: { action: "new" } })}>
          <Plus size={17} />
          New Chat
        </button>

        <button
          className="ai-interview-button"
          onClick={() => navigate("/", { state: { action: "interview" } })}
        >
          <Video size={16} />
          AI Interview
        </button>

        {NAV_GROUPS.map((group) => (
          <div className="nav-group" key={group.label}>
            <h4>{group.label}</h4>
            <nav style={{ display: "flex", flexDirection: "column", gap: 2 }}>
              {group.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  style={linkStyle}
                  className={({ isActive }) => (isActive ? "active-link" : "")}
                >
                  <item.icon size={16} />
                  {item.label}
                </NavLink>
              ))}
            </nav>
          </div>
        ))}
      </div>

      <div className="user-chip-row">
        <NavLink to="/profile" className="user-chip">
          <div className="user-avatar">{initial}</div>
          <div className="user-chip-text">
            <div className="user-chip-name">{username}</div>
            <div className="user-chip-sub">{transient ? "Guest session" : "Signed in"}</div>
          </div>
          <Settings size={15} color="var(--muted)" />
        </NavLink>
        {transient ? (
          <button
            className="sign-in-icon-btn"
            title="Sign in"
            aria-label="Sign in"
            onClick={() => navigate("/sign-in")}
          >
            <LogOut size={15} style={{ transform: "scaleX(-1)" }} />
          </button>
        ) : (
          <button
            className="sign-in-icon-btn"
            title="Sign out"
            aria-label="Sign out"
            onClick={handleSignOut}
          >
            <LogOut size={15} />
          </button>
        )}
      </div>
    </aside>
  );
}
