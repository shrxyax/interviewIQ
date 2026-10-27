export default function Card({ children, style, className = "", hoverable, onClick, as: As = "div" }) {
  // Clickable cards behave like buttons for keyboard users too.
  const interactive = onClick
    ? {
        role: "button",
        tabIndex: 0,
        onKeyDown: (e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onClick(e);
          }
        },
      }
    : {};

  return (
    <As
      onClick={onClick}
      className={`card ${hoverable ? "card-hoverable" : ""} ${onClick ? "card-clickable" : ""} ${className}`.trim()}
      style={style}
      {...interactive}
    >
      {children}
    </As>
  );
}
