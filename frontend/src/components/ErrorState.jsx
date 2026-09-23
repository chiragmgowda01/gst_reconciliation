import { AlertCircle, RefreshCw } from "lucide-react";

export function ErrorState({ error, onRetry }) {
  return (
    <div
      className="card"
      style={{
        margin: "40px auto",
        maxWidth: 600,
        textAlign: "center",
        padding: "40px 24px",
        borderColor: "var(--mismatch-border)",
        backgroundColor: "#fffdfd",
      }}
    >
      <div
        style={{
          width: 50,
          height: 50,
          borderRadius: 9999,
          backgroundColor: "var(--mismatch-bg)",
          color: "var(--mismatch-text)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          margin: "0 auto 16px",
        }}
      >
        <AlertCircle size={28} />
      </div>

      <h3 style={{ fontSize: 18, fontWeight: 700, color: "var(--slate-800)", marginBottom: 8 }}>
        Unable to Load Reconciliation Data
      </h3>

      <p style={{ color: "var(--text-muted)", fontSize: 13.5, marginBottom: 24, lineHeight: 1.6 }}>
        {error || "An unexpected error occurred while communicating with the backend API."}
      </p>

      {onRetry && (
        <button className="btn btn-primary" onClick={onRetry} style={{ margin: "0 auto" }}>
          <RefreshCw size={14} />
          <span>Retry Connection</span>
        </button>
      )}
    </div>
  );
}
