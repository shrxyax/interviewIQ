import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Sparkles,
  ArrowRight,
  PlayCircle,
  Volume2,
  CheckCircle2,
  Circle,
  Video,
  BrainCircuit,
  Workflow,
  ListChecks,
  BookOpen,
  Code2,
  ChevronsRight,
} from "lucide-react";
import "./OnboardingPage.css";

const TABS = [
  {
    key: "interview",
    label: "Mock Interview",
    icon: Video,
    title: "Realistic, conversational mock interviews",
    description:
      "An AI interviewer that listens, adapts, and follows up based on your resume and target role — not a static list of questions.",
    bullets: ["Voice-based question & answer", "Resume-grounded follow-ups", "Full session report at the end"],
    preview: (
      <div className="landing-mock-window inline">
        <div className="landing-mock-avatar">AI</div>
        <div className="landing-mock-status">
          <Volume2 size={13} /> AI Interviewer is speaking
        </div>
        <p className="landing-mock-question">
          "I see you worked on a React dashboard at Flipkart — what bottleneck did you run into?"
        </p>
        <div className="landing-mock-timer">24:18 remaining</div>
      </div>
    ),
  },
  {
    key: "mkt",
    label: "Knowledge Testing",
    icon: BrainCircuit,
    title: "Metamorphic Knowledge Testing",
    description:
      "We don't just grade one answer. We transform the question — a changed constraint, an inversion, interviewer pushback — and check whether your understanding survives.",
    bullets: ["Paraphrase, constraint & pushback probes", "Bayesian belief tracking per concept", "Measures robustness, not just correctness"],
    preview: (
      <div className="lp-beliefs">
        {[
          { label: "Robust", value: 72, color: "var(--success)" },
          { label: "Memorised", value: 18, color: "var(--warning)" },
          { label: "Misconceived", value: 6, color: "var(--danger)" },
          { label: "Absent", value: 4, color: "var(--muted)" },
        ].map((s) => (
          <div key={s.label} className="lp-belief">
            <span className="lp-belief-label">{s.label}</span>
            <div className="lp-belief-track">
              <div className="lp-belief-fill" style={{ width: `${s.value}%`, background: s.color }} />
            </div>
            <span className="lp-belief-pct">{s.value}%</span>
          </div>
        ))}
      </div>
    ),
  },
  {
    key: "whiteboard",
    label: "System Design",
    icon: Workflow,
    title: "Executable System-Design Whiteboard",
    description:
      "Draw your architecture and actually run it: queueing theory, failure injection, and bottleneck detection — so feedback comes from simulation, not an LLM's opinion.",
    bullets: ["Queueing-theory simulation", "Failure injection", "Automated bottleneck detection"],
    preview: (
      <div className="lp-flow">
        {["API", "Queue", "DB"].map((n, i) => (
          <div key={n} className="lp-flow-step">
            <div className={`lp-flow-node ${i === 1 ? "hot" : ""}`}>
              {n}
              {i === 1 && <div className="lp-flow-tag">bottleneck</div>}
            </div>
            {i < 2 && <ChevronsRight size={16} className="lp-flow-arrow" />}
          </div>
        ))}
      </div>
    ),
  },
  {
    key: "dsa",
    label: "DSA Sheet",
    icon: ListChecks,
    title: "Curated DSA Sheet",
    description: "206 problems across 20 topics, ordered so each one builds on the last — tracked against your real progress.",
    bullets: ["206 problems, 20 topics", "Progress tracked per problem", "Linked to your knowledge profile"],
    preview: (
      <div className="lp-list" style={{ gap: 9 }}>
        {[
          { label: "Two Sum", done: true },
          { label: "Valid Parentheses", done: true },
          { label: "Climbing Stairs", done: true },
          { label: "House Robber", done: false },
          { label: "Invert Binary Tree", done: false },
        ].map((item) => (
          <div key={item.label} className={`landing-checklist-item lp-checklist ${item.done ? "done" : ""}`}>
            {item.done ? <CheckCircle2 size={15} /> : <Circle size={15} />}
            {item.label}
          </div>
        ))}
      </div>
    ),
  },
  {
    key: "corecs",
    label: "Core CS",
    icon: BookOpen,
    title: "Core CS Fundamentals",
    description: "OS, DBMS, networks and the other fundamentals interviewers actually probe — concise notes, not textbooks.",
    bullets: ["Short, interview-focused notes", "Linked to knowledge-testing concepts", "Covers OS, DBMS, networks & more"],
    preview: (
      <div className="lp-list">
        {["Process vs Thread", "ACID Properties", "TCP vs UDP", "Indexing & B-Trees"].map((t) => (
          <div key={t} className="lp-topic">
            <div className="lp-topic-dot" />
            {t}
          </div>
        ))}
      </div>
    ),
  },
  {
    key: "ide",
    label: "Coding IDE",
    icon: Code2,
    title: "In-Browser Coding IDE",
    description: "Write and run real code against hidden test cases, right in the browser — no setup required.",
    bullets: ["Python, JavaScript, C++, Java", "Runs against hidden test cases", "No local setup"],
    preview: (
      <pre className="lp-code">
        <span className="lp-code-ln">1</span>{"  "}
        <span className="lp-code-kw">def</span> twoSum(nums, target):{"\n"}
        <span className="lp-code-ln">2</span>{"  "}  seen = {"{}"}{"\n"}
        <span className="lp-code-ln">3</span>{"  "}  <span className="lp-code-kw">for</span> i, n <span className="lp-code-kw">in</span> enumerate(nums):{"\n"}
        <span className="lp-code-ln">4</span>{"  "}    <span className="lp-code-kw">if</span> target - n <span className="lp-code-kw">in</span> seen:{"\n"}
        <span className="lp-code-ln">5</span>{"  "}      <span className="lp-code-kw">return</span> [seen[target - n], i]
      </pre>
    ),
  },
];

const COMPANIES = ["Google", "Amazon", "Microsoft", "Meta", "Apple", "Netflix"];

const FOOTER_LINKS = [
  { to: "/dsa-sheet", label: "DSA Sheet" },
  { to: "/core-cs", label: "Core CS" },
  { to: "/mkt", label: "Knowledge Testing" },
  { to: "/design", label: "System Design Lab" },
  { to: "/code", label: "Coding IDE" },
  { to: "/companies", label: "Company Prep" },
];

export default function OnboardingPage({ onComplete }) {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState(0);
  const tab = TABS[activeTab];

  return (
    <div className="landing-page">
      <nav className="landing-nav">
        <div className="landing-nav-logo">
          <div className="landing-nav-logo-mark">
            <Sparkles size={17} />
          </div>
          InterviewIQ
        </div>

        <div className="landing-nav-links">
          <a href="#features">Features</a>
        </div>

        <div className="landing-nav-actions">
          <button className="landing-nav-signin" onClick={() => navigate("/sign-in")}>
            Sign In
          </button>
          <button className="landing-nav-cta" onClick={onComplete}>
            Get Started <ArrowRight size={14} className="icon-after" />
          </button>
        </div>
      </nav>

      <section className="landing-hero">
        <div>
          <span className="landing-eyebrow">Beyond memorized answers</span>

          <h1>
            Prepare today,
            <br />
            for interviews that
            <br />
            <span className="accent">actually test you.</span>
          </h1>

          <p className="landing-subtitle">
            An AI interview platform built on metamorphic knowledge testing and an executable
            system-design whiteboard — so your prep measures real understanding, not memorized answers.
          </p>

          <div className="landing-hero-actions">
            <button className="landing-cta-primary" onClick={onComplete}>
              Start for free <ArrowRight size={17} />
            </button>

            <a className="landing-cta-secondary" href="#features">
              <span className="landing-cta-secondary-icon">
                <PlayCircle size={15} />
              </span>
              See how it works
            </a>
          </div>

          <div>
            <div className="landing-logos-label">Practise for interviews at</div>
            <div className="landing-logos-row">
              {COMPANIES.map((c) => (
                <span key={c}>{c}</span>
              ))}
            </div>
          </div>
        </div>

        <div className="landing-hero-visual">
          <div className="landing-mock-window">
            <div className="landing-mock-avatar">AI</div>
            <div className="landing-mock-status">
              <Volume2 size={13} /> AI Interviewer
            </div>
            <p className="landing-mock-question">
              "Suppose the array isn't sorted — how does that change your approach?"
            </p>
            <div className="landing-mock-timer">18:42 remaining</div>
          </div>

          <div className="landing-float-card card-robustness">
            <div className="landing-ring">
              <span>82%</span>
            </div>
            <div>
              <div className="landing-float-card-title">Knowledge Robustness</div>
              <div className="landing-float-card-sub">Across 12 concepts</div>
            </div>
          </div>

          <div className="landing-float-card card-checklist">
            <div className="landing-checklist-header">
              <span>Today's Prep</span>
              <span>4/6</span>
            </div>
            <div className="landing-checklist-item done">
              <CheckCircle2 size={14} /> Two Sum
            </div>
            <div className="landing-checklist-item done">
              <CheckCircle2 size={14} /> Valid Parentheses
            </div>
            <div className="landing-checklist-item">
              <Circle size={14} /> System Design: Load Balancer
            </div>
          </div>
        </div>
      </section>

      <section className="landing-features" id="features">
        <div className="landing-features-header">
          <h2>One platform. Everything to get hired.</h2>
          <p>Mock interviews, knowledge testing, system design and practice sheets — the whole prep loop, in one account.</p>
        </div>

        <div className="landing-tabs-row">
          <div className="landing-tabs-scroll">
            {TABS.map((t, i) => (
              <button
                key={t.key}
                className={`landing-tab-pill ${i === activeTab ? "active" : ""}`}
                onClick={() => setActiveTab(i)}
              >
                <t.icon size={14} />
                {t.label}
              </button>
            ))}
          </div>

          <div className="landing-swipe-hint">
            <ChevronsRight size={14} /> Swipe to browse
          </div>
        </div>

        <div className="landing-tab-panel">
          <div className="landing-tab-info" key={tab.key}>
            <div className="landing-tab-icon">
              <tab.icon size={22} />
            </div>
            <h3>{tab.title}</h3>
            <p>{tab.description}</p>
            <ul className="landing-tab-bullets">
              {tab.bullets.map((b) => (
                <li key={b}>{b}</li>
              ))}
            </ul>
          </div>

          <div className="landing-preview-window" key={`${tab.key}-preview`}>
            <div className="landing-preview-titlebar">
              <div className="landing-preview-dot red" />
              <div className="landing-preview-dot yellow" />
              <div className="landing-preview-dot green" />
              <span>interviewiq.app &middot; {tab.key}</span>
            </div>
            <div className="landing-preview-body">{tab.preview}</div>
          </div>
        </div>
      </section>

      <footer className="landing-footer">
        <div className="landing-footer-top">
          <div>
            <div className="landing-footer-brand">
              <div className="landing-nav-logo-mark">
                <Sparkles size={15} />
              </div>
              InterviewIQ
            </div>
            <p>
              An AI interview-prep platform built on metamorphic knowledge testing and an executable
              system-design whiteboard.
            </p>
          </div>

          <div className="landing-footer-links">
            <h4>Product</h4>
            {FOOTER_LINKS.map((l) => (
              <a
                key={l.to}
                onClick={(e) => {
                  e.preventDefault();
                  onComplete();
                  navigate(l.to);
                }}
                href={l.to}
              >
                {l.label}
              </a>
            ))}
          </div>
        </div>

        <div className="landing-footer-bottom">&copy; {new Date().getFullYear()} InterviewIQ.</div>
      </footer>
    </div>
  );
}
