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
  X,
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

export default function Sidebar({ open = false, onClose }) {
  const navigate = useNavigate();
  const username = getUsername();
  const initial = username.replace(/^guest_/, "").charAt(0).toUpperCase() || "G";
  const transient = isTransientGuest();

  const handleSignOut = (e) => {
    e.preventDefault();
    e.stopPropagation();
    logout();
    // Full reload so ensureIdentity() issues a fresh guest session and
    // all cached per-user state is dropped.
    window.location.assign("/sign-in");
  };

  return (
    <>
    <button
      type="button"
      className={`sidebar-backdrop ${open ? "open" : ""}`}
      aria-label="Close menu"
      tabIndex={open ? 0 : -1}
      onClick={onClose}
    />
    <aside className={`sidebar ${open ? "open" : ""}`} id="app-sidebar">
      <div className="sidebar-scroll">
        <div className="logo">
          <div className="logo-brand">
            <div className="logo-mark">
              <Sparkles size={18} />
            </div>
            <h2>InterviewIQ</h2>
          </div>
          <div className="row" style={{ gap: 6 }}>
            <ThemeToggle />
            <button type="button" className="theme-toggle sidebar-close" aria-label="Close menu" onClick={onClose}>
              <X size={16} />
            </button>
          </div>
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
            <nav className="nav-list">
              {group.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
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
            <LogOut size={15} className="icon-flip" />
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
    </>
  );
}
