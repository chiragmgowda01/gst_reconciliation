import { useState, useMemo } from "react";
import { ShieldAlert, AlertTriangle, AlertCircle, HelpCircle, Search, Filter, CheckCircle2 } from "lucide-react";
import { StatusBadge } from "../components/StatusBadge";
import { KPICard } from "../components/KPICard";

export function AnomaliesPage({ anomalies = [] }) {
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

  return (
    <div className="animate-fade-in">
      {/* 1. Page Header */}
      <div className="section-header" style={{ marginBottom: 20 }}>
        <div>
          <h2 className="section-title">Anomaly & Risk Analysis Center</h2>
          <p className="section-subtitle">
            Deterministic audit rules evaluating reconciliation exceptions, value variances, and filing gaps
          </p>
        </div>
        <div className="section-badge">
          {anomalies.length} Potential Anomalies Tracked
        </div>
      </div>

      {/* 2. KPI Severity Cards */}
      <div className="kpi-grid">
        <KPICard
          title="Potential Anomalies"
          value={anomalies.length}
          icon={AlertTriangle}
          subtext="Audited exceptions requiring review"
          iconBg="#fff7ed"
          iconColor="#ea580c"
          accentColor="#ea580c"
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
          subtext="Value differences / unbooked items"
          iconBg="#fffbeb"
          iconColor="#d97706"
          accentColor="#d97706"
        />
        <KPICard
          title="Low Priority"
          value={lowCount}
          icon={HelpCircle}
          subtext="Minor variances & informational"
          iconBg="#f8fafc"
          iconColor="#475569"
          accentColor="#94a3b8"
        />
      </div>

      {/* 3. Main Anomaly Register */}
      <div className="institutional-card">
        <div className="card-header">
          <div>
            <h3 className="card-title">Exception Register & Recommended Review Actions</h3>
            <p className="card-subtitle">
              Detailed list of flagged records graded by tax risk and recommended accountant resolution
            </p>
          </div>
          <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
            Showing <strong>{filtered.length}</strong> of {anomalies.length} items
          </div>
        </div>

        {/* Filter Controls Bar */}
        <div className="filter-bar">
          <div className="filter-left">
            <div className="search-input-wrapper">
              <Search size={14} color="#94a3b8" />
              <input
                type="text"
                className="filter-input-with-icon"
                placeholder="Search invoice, GSTIN or reason..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>

            <div className="filter-dropdown-wrapper">
              <Filter size={13} color="#94a3b8" />
              <select
                className="filter-select"
                value={severityFilter}
                onChange={(e) => setSeverityFilter(e.target.value)}
              >
                <option value="ALL">All Severities</option>
                <option value="HIGH">High Severity</option>
                <option value="MEDIUM">Medium Severity</option>
                <option value="LOW">Low Severity</option>
              </select>
            </div>

            <select
              className="filter-select"
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
            >
              <option value="ALL">All Exception Types</option>
              <option value="MISSING_IN_GST">Missing in GST</option>
              <option value="EXTRA_IN_GST">Extra on Portal</option>
              <option value="LARGE_TAX_DIFFERENCE">Tax Discrepancy</option>
              <option value="MISMATCH">Value Mismatch</option>
              <option value="DUPLICATE_INVOICE">Duplicate Invoice</option>
              <option value="INVALID_GSTIN">Invalid GSTIN</option>
            </select>

            {(search || severityFilter !== "ALL" || typeFilter !== "ALL") && (
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => {
                  setSearch("");
                  setSeverityFilter("ALL");
                  setTypeFilter("ALL");
                }}
              >
                Clear Filters
              </button>
            )}
          </div>
        </div>

        {/* Data Table */}
        <div className="table-wrapper">
          <table className="data-table">
            <thead>
              <tr>
                <th>Invoice No</th>
                <th>Date</th>
                <th>Counterparty GSTIN</th>
                <th>Source Register</th>
                <th>Exception Pattern</th>
                <th>Severity</th>
                <th style={{ textAlign: "right" }}>Difference</th>
                <th>Audit Reason & Recommended Review Action</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={8} className="empty-state">
                    <CheckCircle2 size={28} color="#10b981" className="empty-icon" />
                    <p style={{ fontWeight: 600 }}>No anomalies found matching current criteria.</p>
                  </td>
                </tr>
              ) : (
                filtered.map((item) => (
                  <tr key={item.id}>
                    <td className="mono-cell" style={{ fontWeight: 600 }}>{item.invoice_no}</td>
                    <td>{item.date || "—"}</td>
                    <td className="mono-cell">{item.gstin || "—"}</td>
                    <td style={{ fontSize: 12, color: "var(--text-muted)" }}>{item.source}</td>
                    <td style={{ fontSize: 12, fontWeight: 600 }}>
                      <span className="anomaly-type-tag">
                        {item.type ? item.type.replace(/_/g, " ") : "Unusual Pattern"}
                      </span>
                    </td>
                    <td>
                      <StatusBadge status={item.severity} />
                    </td>
                    <td
                      style={{
                        textAlign: "right",
                        fontFamily: "var(--font-mono)",
                        fontWeight: 700,
                        color: item.difference > 0 ? "#dc2626" : "inherit",
                      }}
                    >
                      {formatCurrency(item.difference)}
                    </td>
                    <td style={{ maxWidth: 400 }}>
                      <div style={{ fontSize: 12.5, fontWeight: 500, color: "var(--text-main)" }}>
                        {item.explanation}
                      </div>
                      {item.action_recommended && (
                        <div className="recommended-action-pill">
                          <span>Action:</span> {item.action_recommended}
                        </div>
                      )}
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
