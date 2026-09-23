import { useState, useMemo } from "react";
import { ShieldAlert, AlertTriangle, AlertCircle, HelpCircle } from "lucide-react";
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
      <div className="kpi-grid">
        <KPICard
          title="Total Exceptions"
          value={anomalies.length}
          icon={AlertTriangle}
          subtext="Audited reconciliation risks"
          iconBg="#fef2f2"
          iconColor="#dc2626"
        />
        <KPICard
          title="High Severity"
          value={highCount}
          icon={ShieldAlert}
          subtext="Missing in GST / large differences"
          iconBg="#fef2f2"
          iconColor="#b91c1c"
        />
        <KPICard
          title="Medium Severity"
          value={mediumCount}
          icon={AlertCircle}
          subtext="Value mismatches / extra records"
          iconBg="#fffbeb"
          iconColor="#b45309"
        />
        <KPICard
          title="Low Severity"
          value={lowCount}
          icon={HelpCircle}
          subtext="Minor variances & informational"
          iconBg="#f1f5f9"
          iconColor="#475569"
        />
      </div>

      <div className="card">
        <div className="card-header">
          <div>
            <h3 className="card-title">Audit & Exception Register</h3>
            <p className="card-subtitle">
              Deterministic compliance flags graded by potential tax liability and ITC risk
            </p>
          </div>
          <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
            Showing <strong>{filtered.length}</strong> of {anomalies.length} exceptions
          </div>
        </div>

        {/* Filter Bar */}
        <div className="filter-bar">
          <div className="filter-left">
            <input
              type="text"
              className="filter-input"
              placeholder="Search exceptions..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />

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

            <select
              className="filter-select"
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
            >
              <option value="ALL">All Anomaly Types</option>
              <option value="MISSING_IN_GST">Missing in GST</option>
              <option value="EXTRA_IN_GST">Extra in GST</option>
              <option value="LARGE_TAX_DIFFERENCE">Large Tax Difference</option>
              <option value="MISMATCH">Mismatch</option>
              <option value="DUPLICATE_INVOICE">Duplicate Invoice</option>
              <option value="INVALID_GSTIN">Invalid GSTIN</option>
            </select>

            {(search || severityFilter !== "ALL" || typeFilter !== "ALL") && (
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => {
                  setSearch("");
                  setSeverityFilter("ALL");
                  setTypeFilter("ALL");
                }}
              >
                Reset Filters
              </button>
            )}
          </div>
        </div>

        {/* Table */}
        <div className="table-wrapper">
          <table className="data-table">
            <thead>
              <tr>
                <th>Invoice No</th>
                <th>Date</th>
                <th>GSTIN</th>
                <th>Source</th>
                <th>Type</th>
                <th>Severity</th>
                <th style={{ textAlign: "right" }}>Difference</th>
                <th>Discrepancy Details & Recommended Action</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={8} className="empty-state">
                    No exceptions match the selected filter.
                  </td>
                </tr>
              ) : (
                filtered.map((item) => (
                  <tr key={item.id}>
                    <td className="mono-cell" style={{ fontWeight: 600 }}>{item.invoice_no}</td>
                    <td>{item.date || "—"}</td>
                    <td className="mono-cell">{item.gstin || "—"}</td>
                    <td style={{ fontSize: 12, color: "var(--text-muted)" }}>{item.source}</td>
                    <td style={{ fontSize: 12, fontWeight: 600 }}>{item.type.replace(/_/g, " ")}</td>
                    <td>
                      <StatusBadge status={item.severity} />
                    </td>
                    <td style={{ textAlign: "right", fontFamily: "var(--font-mono)", fontWeight: 700, color: item.difference > 0 ? "#e11d48" : "inherit" }}>
                      {formatCurrency(item.difference)}
                    </td>
                    <td style={{ maxWidth: 380 }}>
                      <div style={{ fontSize: 12.5, fontWeight: 500, color: "var(--text-main)" }}>
                        {item.explanation}
                      </div>
                      {item.action_recommended && (
                        <div style={{ fontSize: 11.5, color: "#1d4ed8", marginTop: 4 }}>
                          ↳ <strong>Action:</strong> {item.action_recommended}
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
