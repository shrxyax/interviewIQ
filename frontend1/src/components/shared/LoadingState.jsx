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
      <p className="spinner-text text-danger">
        {message}
      </p>
      {onRetry && (
        <button onClick={onRetry} className="btn btn-sm btn-soft" style={{ alignSelf: "flex-start" }}>
          Try again
        </button>
      )}
    </div>
  );
}
