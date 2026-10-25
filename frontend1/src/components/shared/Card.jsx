export default function Card({ children, style, hoverable, onClick, as: As = "div" }) {
  return (
    <As
      onClick={onClick}
      style={{
        background: "var(--card)",
        border: "1px solid var(--border)",
        borderRadius: 16,
        padding: 20,
        cursor: onClick ? "pointer" : "default",
        transition: "border-color 0.2s ease, background 0.2s ease",
        ...style,
      }}
      onMouseEnter={(e) => {
        if (hoverable) e.currentTarget.style.borderColor = "var(--primary)";
      }}
      onMouseLeave={(e) => {
        if (hoverable) e.currentTarget.style.borderColor = "var(--border)";
      }}
    >
      {children}
    </As>
  );
}
