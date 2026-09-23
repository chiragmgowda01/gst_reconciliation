export function LoadingSkeleton() {
  return (
    <div style={{ padding: 20 }}>
      {/* KPI Cards skeleton */}
      <div className="kpi-grid">
        {[1, 2, 3, 4, 5, 6].map((i) => (
          <div
            key={i}
            className="kpi-card"
            style={{ minHeight: 110, backgroundColor: "#fff", animation: "pulse 1.5s infinite" }}
          >
            <div style={{ height: 14, width: "60%", backgroundColor: "var(--slate-200)", borderRadius: 4, marginBottom: 12 }} />
            <div style={{ height: 28, width: "40%", backgroundColor: "var(--slate-200)", borderRadius: 4 }} />
          </div>
        ))}
      </div>

      {/* Main card skeleton */}
      <div className="card" style={{ minHeight: 300, animation: "pulse 1.5s infinite" }}>
        <div style={{ height: 20, width: "30%", backgroundColor: "var(--slate-200)", borderRadius: 4, marginBottom: 20 }} />
        <div style={{ height: 40, width: "100%", backgroundColor: "var(--slate-100)", borderRadius: 6, marginBottom: 12 }} />
        <div style={{ height: 40, width: "100%", backgroundColor: "var(--slate-100)", borderRadius: 6, marginBottom: 12 }} />
        <div style={{ height: 40, width: "100%", backgroundColor: "var(--slate-100)", borderRadius: 6 }} />
      </div>
    </div>
  );
}
