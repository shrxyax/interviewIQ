// Each tone maps to a .badge-<tone> class in App.css.
const TONE_VARS = {
  success: true,
  warning: true,
  danger: true,
  info: true,
  primary: true,
  muted: true,
};

function toneFor(difficulty) {
  const d = (difficulty || "").toLowerCase();
  if (d === "easy") return "success";
  if (d === "medium") return "warning";
  if (d === "hard") return "danger";
  return "muted";
}

export default function Badge({ children, tone, difficulty, style, className = "" }) {
  const resolvedTone = tone || toneFor(difficulty);
  const known = resolvedTone in TONE_VARS ? resolvedTone : "muted";

  return (
    <span className={`badge badge-${known} ${className}`.trim()} style={style}>
      {children}
    </span>
  );
}
