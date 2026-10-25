const TONE_VARS = {
  success: ["--success", "--success-soft"],
  warning: ["--warning", "--warning-soft"],
  danger: ["--danger", "--danger-soft"],
  info: ["--info", "--info-soft"],
  primary: ["--primary", "--primary-soft"],
  muted: ["--muted", null],
};

function toneFor(difficulty) {
  const d = (difficulty || "").toLowerCase();
  if (d === "easy") return "success";
  if (d === "medium") return "warning";
  if (d === "hard") return "danger";
  return "muted";
}

export default function Badge({ children, tone, difficulty, style }) {
  const resolvedTone = tone || toneFor(difficulty);
  const [colorVar, bgVar] = TONE_VARS[resolvedTone] || TONE_VARS.muted;

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        padding: "3px 10px",
        borderRadius: 999,
        fontSize: 12,
        fontWeight: 600,
        color: `var(${colorVar})`,
        background: bgVar ? `var(${bgVar})` : "var(--card-hover)",
        border: `1px solid ${bgVar ? `var(${bgVar})` : "var(--border)"}`,
        whiteSpace: "nowrap",
        ...style,
      }}
    >
      {children}
    </span>
  );
}
