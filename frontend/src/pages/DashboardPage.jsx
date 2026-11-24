import {
  FileText,
  CheckCircle2,
  AlertCircle,
  AlertTriangle,
  HelpCircle,
  ShieldAlert,
  ArrowRight,
  TrendingUp,
  UploadCloud,
  BarChart3,
  Calendar,
  Building,
} from "lucide-react";
import { KPICard } from "../components/KPICard";
import { StatusBadge } from "../components/StatusBadge";

export function DashboardPage({
  data,
  gstr3b,
  anomalies,
  onSelectInvoice,
  onNavigate,
  activeBusiness,
}) {
  const sales = data?.sales || [];
  const purchases = data?.purchases || [];
  const allRecords = [...sales, ...purchases];

  const comparisonCount = allRecords.length;
  const invoiceRecordCount = Number(data?.summary?.invoice_record_count || 0);
  const matched = allRecords.filter((r) => r.status === "MATCH").length;
  const mismatched = allRecords.filter((r) => r.status === "MISMATCH").length;
  const missing = allRecords.filter((r) => r.status === "MISSING_IN_GST").length;
  const extra = allRecords.filter((r) => r.status === "EXTRA_IN_GST").length;
  const anomalyCount = anomalies?.length || 0;

  // Real calculations strictly derived from actual reconciliation data
  const matchRate = comparisonCount > 0 ? ((matched / comparisonCount) * 100).toFixed(1) : null;
  const mismatchRate = comparisonCount > 0 ? ((mismatched / comparisonCount) * 100).toFixed(1) : null;
  const missingRate = comparisonCount > 0 ? ((missing / comparisonCount) * 100).toFixed(1) : null;
  const extraRate = comparisonCount > 0 ? ((extra / comparisonCount) * 100).toFixed(1) : null;

  // Attention items: Mismatches, Missing, and Extra records
  const attentionItems = allRecords.filter(
    (r) => r.status === "MISMATCH" || r.status === "MISSING_IN_GST" || r.status === "EXTRA_IN_GST"
  );

  const formatCurrency = (val) => {
    if (val === null || val === undefined) return "—";
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR",
      maximumFractionDigits: 0,
    }).format(val);
  };

  const businessName = activeBusiness?.name || data?.summary?.business_name || "Business overview";
  const businessGstin = activeBusiness?.gstin || data?.summary?.gstin || "—";
  const taxPeriod = gstr3b?.data_available ? gstr3b.tax_period : null;

  // Pure SVG Donut Chart Geometry Calculations
  const radius = 54;
  const circumference = 2 * Math.PI * radius; // ~339.29
  const matchLength = comparisonCount > 0 ? (matched / comparisonCount) * circumference : 0;
  const mismatchLength = comparisonCount > 0 ? (mismatched / comparisonCount) * circumference : 0;
  const missingLength = comparisonCount > 0 ? (missing / comparisonCount) * circumference : 0;
  const extraLength = comparisonCount > 0 ? (extra / comparisonCount) * circumference : 0;

  const matchOffset = 0;
  const mismatchOffset = -matchLength;
  const missingOffset = -(matchLength + mismatchLength);
  const extraOffset = -(matchLength + mismatchLength + missingLength);

  return (
    <div className="dashboard-page animate-fade-in">
      {/* 1. Modern Executive Hero Card */}
      <section className="dashboard-hero-section">
        <div className="hero-content">
          <div className="hero-badge">
            <span className="hero-badge-dot"></span>
            <span>Business workspace</span>
          </div>
          <h2 className="hero-title">{businessName}</h2>
          <div className="hero-meta-row">
            <div className="hero-meta-item">
              <Building size={14} />
              <span>GSTIN: <strong>{businessGstin}</strong></span>
            </div>
            <div className="hero-meta-item">
              <Calendar size={14} />
              <span>Period: <strong>{taxPeriod || "Not available"}</strong></span>
            </div>
            <div className="hero-meta-item">
              <TrendingUp size={14} color="#10b981" />
              <span>Health: <strong>{matchRate === null ? "No data available" : `${matchRate}%`}</strong></span>
            </div>
          </div>
        </div>

        <div className="hero-actions">
          {invoiceRecordCount === 0 ? (
            <button
              type="button"
              className="btn btn-outline-light"
              onClick={() => onNavigate("upload")}
            >
              <UploadCloud size={14} />
              <span>Upload Registers</span>
            </button>
          ) : (
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => onNavigate("sales")}
            >
              <span>Run Reconciliation</span>
              <ArrowRight size={14} />
            </button>
          )}
        </div>
      </section>

      {/* 2. Section Header & KPI Grid */}
      <div className="section-header">
        <div>
          <h2 className="section-title">Reconciliation KPI Summary</h2>
          <p className="section-subtitle">Real-time matching status across company books and portal filings</p>
        </div>
      </div>

      {/* 6 Clean Fintech KPI Cards */}
      <div className="kpi-grid">
        <KPICard
          title="INVOICE RECORDS"
          value={invoiceRecordCount}
          icon={FileText}
          subtext="Saved business invoice records"
          iconBg="#eff6ff"
          iconColor="#2563eb"
          accentColor="#2563eb"
        />
        <KPICard
          title="MATCHED"
          value={matched}
          icon={CheckCircle2}
          subtext={matchRate === null ? "No data available" : `${matchRate}% match rate`}
          iconBg="#ecfdf5"
          iconColor="#16a34a"
          accentColor="#16a34a"
        />
        <KPICard
          title="MISMATCHED"
          value={mismatched}
          icon={AlertCircle}
          subtext={mismatchRate === null ? "No data available" : `${mismatchRate}% of comparisons`}
          iconBg="#fef2f2"
          iconColor="#dc2626"
          accentColor="#dc2626"
        />
        <KPICard
          title="MISSING IN GST"
          value={missing}
          icon={AlertTriangle}
          subtext="Omitted in portal"
          iconBg="#fffbeb"
          iconColor="#d97706"
          accentColor="#d97706"
        />
        <KPICard
          title="EXTRA IN GST"
          value={extra}
          icon={HelpCircle}
          subtext="Not in company books"
          iconBg="#faf5ff"
          iconColor="#7c3aed"
          accentColor="#7c3aed"
        />
        <KPICard
          title="AUDIT ANOMALIES"
          value={anomalyCount}
          icon={ShieldAlert}
          subtext="Requires inspection"
          iconBg="#eff6ff"
          iconColor="#0d9488"
          accentColor="#0d9488"
        />
      </div>

      {/* Empty State Banner if Business has 0 records */}
      {comparisonCount === 0 && (
        <div
          className="institutional-card"
          style={{
            textAlign: "center",
            padding: "48px 24px",
            borderRadius: "16px",
            background: "#ffffff",
            border: "1px solid var(--border-color)",
            boxShadow: "var(--shadow-sm)",
            marginBottom: "24px",
          }}
        >
          <div
            style={{
              width: 56,
              height: 56,
              borderRadius: "14px",
              background: "#eff6ff",
              border: "1px solid #bfdbfe",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              margin: "0 auto 16px",
              color: "#2563eb",
            }}
          >
            <UploadCloud size={28} />
          </div>
          <h3 style={{ fontSize: 18, fontWeight: 800, color: "#1e293b", marginBottom: 6 }}>
            No reconciliation data available
          </h3>
          <p style={{ fontSize: 13.5, color: "#64748b", maxWidth: 440, margin: "0 auto 20px" }}>
            No invoice records found for this business. Upload sales and purchase registers to generate compliance insights.
          </p>
          <div style={{ display: "flex", justifyContent: "center", gap: 12 }}>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => onNavigate("upload")}
              style={{ padding: "0 22px", height: 44, borderRadius: 10, fontSize: 13, fontWeight: 700, gap: 8 }}
            >
              <UploadCloud size={16} />
              <span>Upload Registers</span>
            </button>
          </div>
        </div>
      )}

      {/* 3. GSTR-3B Summary Card (When Data Exists) */}
      {comparisonCount > 0 && gstr3b?.data_available && (
        <div className="gstr3b-statement-card">
          <div className="statement-header">
            <div>
              <span className="statement-tag">Self-Assessed Return</span>
              <h3 className="statement-title">Form GSTR-3B Summary</h3>
              <p className="statement-subtitle">Monthly statutory tax liability & Input Tax Credit for {gstr3b.tax_period}</p>
            </div>
            <button
              type="button"
              className="btn btn-outline-light btn-sm"
              onClick={() => onNavigate("gstr3b")}
            >
              Full Return Statement <ArrowRight size={13} />
            </button>
          </div>

          <div className="statement-grid">
            <div className="statement-box">
              <span className="box-label">Output Tax (Table 3.1)</span>
              <span className="box-val">{formatCurrency(gstr3b.output_tax)}</span>
              <span className="box-sub">Outward taxable supplies</span>
            </div>
            <div className="statement-box highlight-green">
              <span className="box-label">Eligible ITC (Table 4A)</span>
              <span className="box-val text-green">{formatCurrency(gstr3b.eligible_itc)}</span>
              <span className="box-sub">Inward supplies claimed</span>
            </div>
            <div className="statement-box highlight-red">
              <span className="box-label">ITC Reversed (Table 4B)</span>
              <span className="box-val text-red">{formatCurrency(gstr3b.itc_reversed)}</span>
              <span className="box-sub">Rule 42/43 ineligibility</span>
            </div>
            <div className="statement-box highlight-primary">
              <span className="box-label">Net ITC (Table 4C)</span>
              <span className="box-val text-primary">{formatCurrency(gstr3b.net_itc)}</span>
              <span className="box-sub">Net credited balance</span>
            </div>
          </div>
        </div>
      )}

      {/* 4. Two-Column Layout: Visual Health Chart + Attention Required */}
      {comparisonCount > 0 && (
        <div className="dashboard-dual-grid">
          {/* Left: Modern SVG Donut Chart + Health Distribution */}
          <div className="institutional-card">
            <div className="card-header">
              <div>
                <h3 className="card-title">Reconciliation Health</h3>
                <p className="card-subtitle">Ledger alignment and statutory distribution</p>
              </div>
              <span className="health-percentage-badge">{matchRate}% Matched</span>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: 24, padding: "8px 0 16px", flexWrap: "wrap" }}>
              {/* Pure SVG Donut Chart */}
              <div style={{ position: "relative", width: 140, height: 140, flexShrink: 0, margin: "0 auto" }}>
                <svg width="140" height="140" viewBox="0 0 140 140" style={{ transform: "rotate(-90deg)" }}>
                  {/* Background Track */}
                  <circle
                    cx="70"
                    cy="70"
                    r={radius}
                    fill="none"
                    stroke="#f1f5f9"
                    strokeWidth="14"
                  />
                  {/* Matched Arc */}
                  {matched > 0 && (
                    <circle
                      cx="70"
                      cy="70"
                      r={radius}
                      fill="none"
                      stroke="#16a34a"
                      strokeWidth="14"
                      strokeDasharray={`${matchLength} ${circumference}`}
                      strokeDashoffset={matchOffset}
                      strokeLinecap="round"
                    />
                  )}
                  {/* Mismatched Arc */}
                  {mismatched > 0 && (
                    <circle
                      cx="70"
                      cy="70"
                      r={radius}
                      fill="none"
                      stroke="#dc2626"
                      strokeWidth="14"
                      strokeDasharray={`${mismatchLength} ${circumference}`}
                      strokeDashoffset={mismatchOffset}
                    />
                  )}
                  {/* Missing Arc */}
                  {missing > 0 && (
                    <circle
                      cx="70"
                      cy="70"
                      r={radius}
                      fill="none"
                      stroke="#d97706"
                      strokeWidth="14"
                      strokeDasharray={`${missingLength} ${circumference}`}
                      strokeDashoffset={missingOffset}
                    />
                  )}
                  {/* Extra Arc */}
                  {extra > 0 && (
                    <circle
                      cx="70"
                      cy="70"
                      r={radius}
                      fill="none"
                      stroke="#7c3aed"
                      strokeWidth="14"
                      strokeDasharray={`${extraLength} ${circumference}`}
                      strokeDashoffset={extraOffset}
                    />
                  )}
                </svg>
                {/* Center Badge */}
                <div
                  style={{
                    position: "absolute",
                    inset: 0,
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    justifyContent: "center",
                    pointerEvents: "none",
                  }}
                >
                  <span style={{ fontSize: 20, fontWeight: 800, fontFamily: "var(--font-mono)", color: "#0f172a" }}>
                    {matchRate}%
                  </span>
                  <span style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", color: "#64748b" }}>
                    Matched
                  </span>
                </div>
              </div>

              {/* Status List with Progress Bars */}
              <div className="health-breakdown-list" style={{ flex: 1, minWidth: 200 }}>
                <div className="health-row">
                  <div className="health-labels">
                    <span className="health-status-name text-match">MATCH</span>
                    <span className="health-status-val">{matched} ({matchRate}%)</span>
                  </div>
                  <div className="progress-bar-bg">
                    <div className="progress-bar-fill fill-match" style={{ width: `${matchRate}%` }} />
                  </div>
                </div>

                <div className="health-row">
                  <div className="health-labels">
                    <span className="health-status-name text-mismatch">MISMATCH</span>
                    <span className="health-status-val">{mismatched} ({mismatchRate}%)</span>
                  </div>
                  <div className="progress-bar-bg">
                    <div className="progress-bar-fill fill-mismatch" style={{ width: `${mismatchRate}%` }} />
                  </div>
                </div>

                <div className="health-row">
                  <div className="health-labels">
                    <span className="health-status-name text-missing">MISSING IN GST</span>
                    <span className="health-status-val">{missing} ({missingRate}%)</span>
                  </div>
                  <div className="progress-bar-bg">
                    <div className="progress-bar-fill fill-missing" style={{ width: `${missingRate}%` }} />
                  </div>
                </div>

                <div className="health-row">
                  <div className="health-labels">
                    <span className="health-status-name text-extra">EXTRA IN GST</span>
                    <span className="health-status-val">{extra} ({extraRate}%)</span>
                  </div>
                  <div className="progress-bar-bg">
                    <div className="progress-bar-fill fill-extra" style={{ width: `${extraRate}%` }} />
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Right: Attention Required Section */}
          <div className="institutional-card">
            <div className="card-header">
              <div>
                <h3 className="card-title">Attention Required</h3>
                <p className="card-subtitle">Ledger discrepancies requiring immediate audit</p>
              </div>
              <span className="badge badge-high">{attentionItems.length} Invoices</span>
            </div>

            <div className="attention-items-list">
              {attentionItems.length === 0 ? (
                <div className="empty-state">
                  <CheckCircle2 size={32} color="#16a34a" className="empty-icon" />
                  <p>All transactions reconciled perfectly.</p>
                </div>
              ) : (
                attentionItems.slice(0, 4).map((item, idx) => (
                  <div
                    key={`${item.invoice_no}-${item.status}-${idx}`}
                    className="attention-item-card"
                    onClick={() => onSelectInvoice(item)}
                  >
                    <div className="attention-item-left">
                      <div className="attention-item-top">
                        <span className="attention-inv-no">{item.invoice_no}</span>
                        <StatusBadge status={item.status} />
                      </div>
                      <div className="attention-inv-desc">
                        {item.explanation || item.reason || "Discrepancy identified in values"}
                      </div>
                    </div>

                    <div className="attention-item-right">
                      <div className="attention-inv-diff">
                        {item.taxable_value_diff ? `Diff: ${formatCurrency(item.taxable_value_diff)}` : "Missing in Portal"}
                      </div>
                      <div className="attention-inspect-link">
                        <span>Inspect</span>
                        <ArrowRight size={11} />
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {/* 5. Quick Actions Grid */}
      <div className="quick-actions-section">
        <div className="section-header" style={{ marginBottom: 14 }}>
          <div>
            <h2 className="section-title">Quick Actions</h2>
            <p className="section-subtitle">Common compliance workflows and statutory registers</p>
          </div>
        </div>

        <div className="quick-actions-grid">
          <div className="quick-action-card" onClick={() => onNavigate("sales")}>
            <div className="action-icon-wrap" style={{ background: "#eff6ff", color: "#2563eb" }}>
              <CheckCircle2 size={20} />
            </div>
            <h3>Reconcile Sales</h3>
            <p>Match sales book with Form GSTR-1</p>
            <div className="action-arrow"><ArrowRight size={14} /></div>
          </div>

          <div className="quick-action-card" onClick={() => onNavigate("purchase")}>
            <div className="action-icon-wrap" style={{ background: "#ecfdf5", color: "#0d9488" }}>
              <TrendingUp size={20} />
            </div>
            <h3>Reconcile Purchases</h3>
            <p>Compare purchase register with GSTR-2B</p>
            <div className="action-arrow"><ArrowRight size={14} /></div>
          </div>

          <div className="quick-action-card" onClick={() => onNavigate("anomalies")}>
            <div className="action-icon-wrap" style={{ background: "#fef2f2", color: "#dc2626" }}>
              <ShieldAlert size={20} />
            </div>
            <h3>Audit Exceptions</h3>
            <p>Review ML outliers & flagged transactions</p>
            <div className="action-arrow"><ArrowRight size={14} /></div>
          </div>

          <div className="quick-action-card" onClick={() => onNavigate("reports")}>
            <div className="action-icon-wrap" style={{ background: "#f8fafc", color: "#0f172a" }}>
              <BarChart3 size={20} />
            </div>
            <h3>Statutory Reports</h3>
            <p>Export reconciliation schedules & CSVs</p>
            <div className="action-arrow"><ArrowRight size={14} /></div>
          </div>
        </div>
      </div>

      {/* 6. Recent Invoices Snapshot */}
      {comparisonCount > 0 && (
        <div className="institutional-card">
          <div className="card-header">
            <div>
              <h3 className="card-title">Recent Invoices</h3>
              <p className="card-subtitle">Active transactions snapshot from company books</p>
            </div>
            <div className="header-actions">
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => onNavigate("sales")}>
                View Sales
              </button>
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => onNavigate("purchase")}>
                View Purchases
              </button>
            </div>
          </div>

          <div className="table-wrapper">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Invoice No</th>
                  <th>Date</th>
                  <th>Counterparty GSTIN</th>
                  <th style={{ textAlign: "right" }}>Taxable Value</th>
                  <th style={{ textAlign: "right" }}>GST Amount</th>
                  <th>Status</th>
                  <th style={{ textAlign: "center" }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {allRecords.slice(0, 6).map((row, idx) => (
                  <tr key={`${row.invoice_no}-${row.status}-${idx}`}>
                    <td className="mono-cell" style={{ fontWeight: 600 }}>{row.invoice_no}</td>
                    <td>{row.invoice_date || "—"}</td>
                    <td className="mono-cell">{row.gstin || "—"}</td>
                    <td style={{ textAlign: "right" }} className="mono-cell">{formatCurrency(row.taxable_value)}</td>
                    <td style={{ textAlign: "right" }} className="mono-cell">{formatCurrency(row.gst_amount)}</td>
                    <td><StatusBadge status={row.status} /></td>
                    <td style={{ textAlign: "center" }}>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => onSelectInvoice(row)}
                      >
                        Inspect
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
export default DashboardPage;
