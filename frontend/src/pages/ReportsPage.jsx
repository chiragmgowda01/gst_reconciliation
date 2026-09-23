import { useState, useEffect } from "react";
import { Download, FileSpreadsheet, CheckCircle, AlertTriangle, ShieldCheck } from "lucide-react";
import { api } from "../api/client";
import { KPICard } from "../components/KPICard";
import { LoadingSkeleton } from "../components/LoadingSkeleton";

export function ReportsPage() {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getReportsSummary()
      .then((data) => {
        setSummary(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const handleExport = (type) => {
    const url = api.getExportUrl(type);
    window.open(url, "_blank");
  };

  const reportsList = [
    {
      id: "sales",
      title: "Sales Reconciliation Schedule",
      desc: "Complete matching matrix of Sales Register invoices against filed GSTR-1 returns.",
      badge: "Outward Supplies",
    },
    {
      id: "purchases",
      title: "Purchase & ITC Eligibility Schedule",
      desc: "Inward supply comparison between Purchase Register and auto-drafted GSTR-2A vendor filings.",
      badge: "Inward Supplies / ITC",
    },
    {
      id: "mismatches",
      title: "Tax & Value Discrepancy Report",
      desc: "Filtered list of invoices where taxable values or GST amounts differ between books and portal.",
      badge: "Audit Discrepancies",
    },
    {
      id: "missing",
      title: "Missing Invoices (ITC at Risk / Unreported)",
      desc: "Invoices present in internal accounting registers but missing on the GST portal.",
      badge: "Compliance Risk",
    },
    {
      id: "anomalies",
      title: "Statutory Anomaly & Exceptions Log",
      desc: "Severity-ranked audit exceptions including duplicates, large tax gaps, and missing records.",
      badge: "Risk Audit",
    },
  ];

  if (loading) return <LoadingSkeleton />;

  return (
    <div className="animate-fade-in">
      {/* Top summary cards */}
      {summary && (
        <div className="kpi-grid">
          <KPICard
            title="Overall Audit Health"
            value={`${summary.audit_health_score}%`}
            icon={ShieldCheck}
            subtext="Weighted reconciliation match rate"
            iconBg="#ecfdf5"
            iconColor="#059669"
          />
          <KPICard
            title="Sales Match Rate"
            value={`${summary.sales_summary?.match_rate_percentage}%`}
            icon={CheckCircle}
            subtext={`${summary.sales_summary?.matched} of ${summary.sales_summary?.total_records} matched`}
            iconBg="#eff6ff"
            iconColor="#2563eb"
          />
          <KPICard
            title="Purchase ITC Match Rate"
            value={`${summary.purchase_summary?.match_rate_percentage}%`}
            icon={CheckCircle}
            subtext={`${summary.purchase_summary?.matched} of ${summary.purchase_summary?.total_records} verified`}
            iconBg="#eff6ff"
            iconColor="#2563eb"
          />
          <KPICard
            title="High Risk Exceptions"
            value={summary.anomalies_summary?.high_risk}
            icon={AlertTriangle}
            subtext="Requires immediate accountant action"
            iconBg="#fef2f2"
            iconColor="#dc2626"
          />
        </div>
      )}

      {/* Export List Card */}
      <div className="card">
        <div className="card-header">
          <div>
            <h3 className="card-title">Statutory Audit Reports & CSV Export</h3>
            <p className="card-subtitle">
              Export standardized reconciliation schedules for Chartered Accountants, management review, or GST filing
            </p>
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {reportsList.map((rep) => (
            <div
              key={rep.id}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "16px 20px",
                backgroundColor: "var(--slate-50)",
                border: "1px solid var(--border-color)",
                borderRadius: "var(--radius-md)",
                flexWrap: "wrap",
                gap: 12,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 14, minWidth: 280 }}>
                <div
                  style={{
                    width: 40,
                    height: 40,
                    borderRadius: 8,
                    backgroundColor: "#eff6ff",
                    color: "#2563eb",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  <FileSpreadsheet size={20} />
                </div>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <h4 style={{ fontSize: 14, fontWeight: 700, color: "var(--text-main)" }}>
                      {rep.title}
                    </h4>
                    <span style={{ fontSize: 11, background: "var(--slate-200)", padding: "2px 7px", borderRadius: 4 }}>
                      {rep.badge}
                    </span>
                  </div>
                  <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>
                    {rep.desc}
                  </p>
                </div>
              </div>

              <button
                className="btn btn-secondary"
                onClick={() => handleExport(rep.id)}
                style={{ marginLeft: "auto" }}
              >
                <Download size={14} />
                <span>Export CSV</span>
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
