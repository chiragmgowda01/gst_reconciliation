import { useState, useEffect } from "react";
import { Download, FileSpreadsheet, CheckCircle2, AlertTriangle, ShieldCheck, FileText } from "lucide-react";
import { api } from "../api/client";
import { KPICard } from "../components/KPICard";
import { LoadingSkeleton } from "../components/LoadingSkeleton";

export function ReportsPage() {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let ignore = false;
    api.getReportsSummary()
      .then((data) => {
        if (!ignore) {
          setSummary(data);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!ignore) setLoading(false);
      });

    return () => {
      ignore = true;
    };
  }, []);

  const handleExport = (type) => {
    const url = api.getExportUrl(type);
    window.open(url, "_blank");
  };

  const reportsList = [
    {
      id: "sales",
      title: "Sales Reconciliation Register Schedule",
      desc: "Complete matching matrix of internal Sales Register invoices against filed GSTR-1 returns with difference calculations.",
      badge: "Outward Supplies",
      frequency: "Monthly Tax Period",
    },
    {
      id: "purchases",
      title: "Purchase & ITC Eligibility Schedule",
      desc: "Inward supply comparison between Purchase Register bills and auto-drafted GSTR-2A vendor portal filings.",
      badge: "Inward ITC Verification",
      frequency: "Monthly Tax Period",
    },
    {
      id: "mismatches",
      title: "Tax Value & Rate Discrepancy Report",
      desc: "Filtered schedule of transactions where taxable values or GST amounts differ between company ledger and GST portal.",
      badge: "Audit Variance",
      frequency: "Immediate Action",
    },
    {
      id: "missing",
      title: "Missing Invoices (ITC at Risk / Unfiled Liability)",
      desc: "Invoices present in internal registers but completely missing on the portal, representing unclaimed ITC or unfiled outward sales.",
      badge: "Compliance Risk",
      frequency: "High Priority",
    },
    {
      id: "anomalies",
      title: "Statutory Anomaly & Exceptions Log",
      desc: "Ranked exception audit log including duplicate invoices, large rate differences, and invalid counterparty GSTINs.",
      badge: "Risk Audit",
      frequency: "Monthly Audit",
    },
  ];

  if (loading) return <LoadingSkeleton />;

  return (
    <div className="animate-fade-in">
      {/* 1. Page Header */}
      <div className="section-header" style={{ marginBottom: 20 }}>
        <div>
          <h2 className="section-title">Statutory Audit & Export Reports</h2>
          <p className="section-subtitle">
            Export structured reconciliation schedules for Chartered Accountants, management review, and compliance records
          </p>
        </div>
        <div className="section-badge">
          <FileText size={13} />
          <span>5 Standard Export Schedules</span>
        </div>
      </div>

      {/* 2. Top Summary Metrics Cards (derived from real API summary data) */}
      {summary && (
        <div className="kpi-grid">
          <KPICard
            title="Reconciliation Health"
            value={`${summary.audit_health_score ?? 0}%`}
            icon={ShieldCheck}
            subtext="Weighted reconciliation alignment score"
            iconBg="#ecfdf5"
            iconColor="#059669"
            accentColor="#059669"
          />
          <KPICard
            title="Sales Match Rate"
            value={`${summary.sales_summary?.match_rate_percentage ?? 0}%`}
            icon={CheckCircle2}
            subtext={`${summary.sales_summary?.matched ?? 0} of ${summary.sales_summary?.total_records ?? 0} outward verified`}
            iconBg="#eff6ff"
            iconColor="#2563eb"
            accentColor="#2563eb"
          />
          <KPICard
            title="Purchase ITC Match Rate"
            value={`${summary.purchase_summary?.match_rate_percentage ?? 0}%`}
            icon={CheckCircle2}
            subtext={`${summary.purchase_summary?.matched ?? 0} of ${summary.purchase_summary?.total_records ?? 0} inward verified`}
            iconBg="#eff6ff"
            iconColor="#2563eb"
            accentColor="#2563eb"
          />
          <KPICard
            title="High Priority Exceptions"
            value={summary.anomalies_summary?.high_risk ?? 0}
            icon={AlertTriangle}
            subtext="Requiring immediate review"
            iconBg="#fef2f2"
            iconColor="#dc2626"
            accentColor="#dc2626"
          />
        </div>
      )}

      {/* 3. Export Schedules List */}
      <div className="institutional-card">
        <div className="card-header">
          <div>
            <h3 className="card-title">Available Export Schedules</h3>
            <p className="card-subtitle">
              Click export to download formatted CSV schedules with full transaction metadata and difference calculations
            </p>
          </div>
        </div>

        <div className="reports-schedules-list">
          {reportsList.map((rep) => (
            <div key={rep.id} className="report-item-card">
              <div className="report-item-left">
                <div className="report-icon-box">
                  <FileSpreadsheet size={20} />
                </div>
                <div className="report-details">
                  <div className="report-title-row">
                    <h4 className="report-title">{rep.title}</h4>
                    <span className="report-badge">{rep.badge}</span>
                    <span className="report-freq-tag">{rep.frequency}</span>
                  </div>
                  <p className="report-desc">{rep.desc}</p>
                </div>
              </div>

              <div className="report-item-right">
                <button
                  type="button"
                  className="btn btn-secondary report-download-btn"
                  onClick={() => handleExport(rep.id)}
                >
                  <Download size={14} />
                  <span>Download CSV</span>
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
