export function LoadingState({ label = "Loading..." }) {
  return (
    <div className="page-content">
      <p className="spinner-text">{label}</p>
    </div>
  );
}

export function ErrorState({ message = "Something went wrong.", onRetry }) {
  return (
    <div className="page-content">
      <p className="spinner-text" style={{ color: "var(--danger)" }}>
        {message}
      </p>
      {onRetry && (
        <button
          onClick={onRetry}
          style={{
            background: "var(--primary-soft)", color: "var(--primary)", border: "none",
            borderRadius: 10, padding: "8px 16px", fontWeight: 600, fontSize: 13, alignSelf: "flex-start",
          }}
        >
          Try again
        </button>
      )}
    </div>
  );
}
