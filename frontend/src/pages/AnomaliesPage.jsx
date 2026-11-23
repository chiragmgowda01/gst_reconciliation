import { useState, useMemo } from "react";
import { ShieldAlert, AlertTriangle, AlertCircle, Search, Filter, CheckCircle2, Brain } from "lucide-react";
import { StatusBadge } from "../components/StatusBadge";
import { KPICard } from "../components/KPICard";

export function AnomaliesPage({ anomalies = [], mlMeta = null }) {
  const [severityFilter, setSeverityFilter] = useState("ALL");
  const [typeFilter, setTypeFilter] = useState("ALL");
  const [search, setSearch] = useState("");

  const highCount = anomalies.filter((a) => a.severity === "HIGH").length;
  const mediumCount = anomalies.filter((a) => a.severity === "MEDIUM").length;
  const lowCount = anomalies.filter((a) => a.severity === "LOW").length;

  const filtered = useMemo(() => {
    return anomalies.filter((a) => {
      const matchSev = severityFilter === "ALL" || a.severity === severityFilter;
      const matchType = typeFilter === "ALL" || a.type === typeFilter;
      const matchSearch =
        !search ||
        a.invoice_no?.toLowerCase().includes(search.toLowerCase()) ||
        a.gstin?.toLowerCase().includes(search.toLowerCase()) ||
        a.explanation?.toLowerCase().includes(search.toLowerCase());

      return matchSev && matchType && matchSearch;
    });
  }, [anomalies, severityFilter, typeFilter, search]);

  const formatCurrency = (val) => {
    if (!val) return "₹0.00";
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR",
      maximumFractionDigits: 2,
    }).format(val);
  };

  const mlCount = anomalies.filter((a) => a.type === "ML_UNUSUAL_PATTERN").length;

  return (
    <div className="animate-fade-in">
      {/* ML Analysis Status Banner */}
      {mlMeta && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            padding: "10px 16px",
            marginBottom: 16,
            borderRadius: 8,
            background: mlMeta.ml_available ? "#f0fdfa" : "#f8fafc",
            border: `1px solid ${mlMeta.ml_available ? "#99f6e4" : "#e2e8f0"}`,
            fontSize: 12.5,
            color: mlMeta.ml_available ? "#0f766e" : "#64748b",
          }}
        >
          <Brain size={16} color={mlMeta.ml_available ? "#0d9488" : "#94a3b8"} />
          <span>
            <strong>Isolation Forest ML Analysis:</strong>{" "}
            {mlMeta.ml_available
              ? `Active — analysed ${mlMeta.n_records_used} records, flagged ${mlMeta.n_outliers} unusual patterns.`
              : mlMeta.reason || "Not available."}
          </span>
          {!mlMeta.ml_available && (
            <span style={{ marginLeft: 4, color: "#94a3b8" }}>(Deterministic rules still active)</span>
          )}
        </div>
      )}

      {/* 1. Page Header */}
      <div className="section-header" style={{ marginBottom: 20 }}>
        <div>
          <h2 className="section-title">Anomaly & Risk Analysis Center</h2>
          <p className="section-subtitle">
            Deterministic audit rules + Isolation Forest ML analysis for reconciliation exceptions and unusual patterns
          </p>
        </div>
        <div className="section-badge">
          {anomalies.length} Potential Anomalies Tracked ({mlCount} ML-Scored)
        </div>
      </div>

      {/* 2. KPI Severity Cards */}
      <div className="kpi-grid">
        <KPICard
          title="Potential Anomalies"
          value={anomalies.length}
          icon={AlertTriangle}
          subtext="Audited exceptions requiring review"
          iconBg="#eff6ff"
          iconColor="#2563eb"
          accentColor="#2563eb"
        />
        <KPICard
          title="High Priority"
          value={highCount}
          icon={ShieldAlert}
          subtext="Missing in portal / major tax gap"
          iconBg="#fef2f2"
          iconColor="#dc2626"
          accentColor="#dc2626"
        />
        <KPICard
          title="Medium Priority"
          value={mediumCount}
          icon={AlertCircle}
          subtext="Rate variances & minor gaps"
          iconBg="#fffbeb"
          iconColor="#d97706"
          accentColor="#d97706"
        />
        <KPICard
          title="Low Priority"
          value={lowCount}
          icon={CheckCircle2}
          subtext="Unusual pattern warnings"
          iconBg="#f0fdfa"
          iconColor="#0d9488"
          accentColor="#0d9488"
        />
      </div>

      {/* 3. Filter Controls */}
      <div className="institutional-card" style={{ marginBottom: 16, padding: "14px 18px" }}>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
          {/* Search */}
          <div style={{ display: "flex", alignItems: "center", gap: 8, flex: 1, minWidth: 200 }}>
            <Search size={15} color="#94a3b8" />
            <input
              type="text"
              placeholder="Filter by invoice no, GSTIN or reason..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{
                width: "100%",
                padding: "6px 10px",
                border: "1px solid #e2e8f0",
                borderRadius: 6,
                fontSize: 12.5,
                outline: "none",
              }}
            />
          </div>

          {/* Severity filter */}
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <Filter size={13} color="#64748b" />
            <span style={{ fontSize: 12, fontWeight: 600, color: "#64748b" }}>Severity:</span>
            {["ALL", "HIGH", "MEDIUM", "LOW"].map((s) => (
              <button
                key={s}
                type="button"
                className={`btn btn-sm ${severityFilter === s ? "btn-primary" : "btn-secondary"}`}
                style={{ fontSize: 11.5, padding: "3px 10px", height: 28 }}
                onClick={() => setSeverityFilter(s)}
              >
                {s}
              </button>
            ))}
          </div>

          {/* Type filter */}
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontSize: 12, fontWeight: 600, color: "#64748b" }}>Type:</span>
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              style={{
                padding: "4px 8px",
                borderRadius: 6,
                border: "1px solid #e2e8f0",
                fontSize: 12,
                backgroundColor: "#fff",
                outline: "none",
              }}
            >
              <option value="ALL">All Rule Categories</option>
              <option value="VALUE_MISMATCH">Value Mismatch</option>
              <option value="MISSING_INVOICE">Missing Invoice</option>
              <option value="RATE_DISCREPANCY">Rate Discrepancy</option>
              <option value="DUPLICATE_INVOICE">Duplicate Invoice</option>
              <option value="ML_UNUSUAL_PATTERN">ML Unusual Pattern</option>
            </select>
          </div>
        </div>
      </div>

      {/* 4. Anomalies Table */}
      <div className="institutional-card">
        <div className="table-wrapper">
          <table className="data-table">
            <thead>
              <tr>
                <th>Invoice No</th>
                <th>Party GSTIN</th>
                <th>Register / Source</th>
                <th style={{ textAlign: "right" }}>Value</th>
                <th style={{ textAlign: "right" }}>Variance</th>
                <th>Severity</th>
                <th>Category</th>
                <th>Diagnostic Explanation</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={8} style={{ textAlign: "center", padding: "32px 16px", color: "#64748b" }}>
                    No anomalies match the current filter criteria.
                  </td>
                </tr>
              ) : (
                filtered.map((item, idx) => (
                  <tr key={`${item.invoice_no}-${item.type}-${idx}`}>
                    <td className="mono-cell" style={{ fontWeight: 600 }}>{item.invoice_no || "—"}</td>
                    <td className="mono-cell">{item.gstin || "—"}</td>
                    <td>{item.source || "Ledger"}</td>
                    <td style={{ textAlign: "right" }} className="mono-cell">{formatCurrency(item.value)}</td>
                    <td style={{ textAlign: "right", color: item.variance ? "#dc2626" : "inherit" }} className="mono-cell">
                      {item.variance ? formatCurrency(item.variance) : "—"}
                    </td>
                    <td><StatusBadge status={item.severity} /></td>
                    <td>
                      <span
                        style={{
                          display: "inline-block",
                          padding: "2px 8px",
                          borderRadius: 4,
                          fontSize: 11,
                          fontWeight: 600,
                          backgroundColor: item.type === "ML_UNUSUAL_PATTERN" ? "#f0fdfa" : "#f1f5f9",
                          color: item.type === "ML_UNUSUAL_PATTERN" ? "#0f766e" : "#475569",
                        }}
                      >
                        {item.type || "RULE"}
                      </span>
                    </td>
                    <td style={{ fontSize: 12, color: "#475569", maxWidth: 300 }}>
                      {item.explanation || "Discrepancy detected during rule check."}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
export default AnomaliesPage;
