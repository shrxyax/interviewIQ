export default function ProgressBar({ value, max = 100, height = 8, color = "var(--primary)" }) {
  const pct = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0;

  return (
    <div
      style={{
        width: "100%",
        height,
        borderRadius: height,
        background: "var(--border)",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          width: `${pct}%`,
          height: "100%",
          background: color,
          borderRadius: height,
          transition: "width 0.3s ease",
        }}
      />
    </div>
  );
}
