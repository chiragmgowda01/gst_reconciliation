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

  const total = allRecords.length;
  const matched = allRecords.filter((r) => r.status === "MATCH").length;
  const mismatched = allRecords.filter((r) => r.status === "MISMATCH").length;
  const missing = allRecords.filter((r) => r.status === "MISSING_IN_GST").length;
  const extra = allRecords.filter((r) => r.status === "EXTRA_IN_GST").length;
  const anomalyCount = anomalies?.length || 0;

  // Real calculations strictly derived from actual reconciliation data
  const matchRate = total > 0 ? ((matched / total) * 100).toFixed(1) : "0.0";
  const mismatchRate = total > 0 ? ((mismatched / total) * 100).toFixed(1) : "0.0";
  const missingRate = total > 0 ? ((missing / total) * 100).toFixed(1) : "0.0";
  const extraRate = total > 0 ? ((extra / total) * 100).toFixed(1) : "0.0";

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

  const businessName = activeBusiness?.name || data?.summary?.business_name || "Demo MSME Enterprise";
  const businessGstin = activeBusiness?.gstin || data?.summary?.gstin || "29AAAAA1111A1Z5";
  const taxPeriod = gstr3b?.tax_period || "2026-07";

  return (
    <div className="dashboard-page animate-fade-in">
      {/* 1. Concise Executive Hero Card */}
      <section className="dashboard-hero-section">
        <div className="hero-content">
          <div className="hero-badge">
            <span className="hero-badge-dot"></span>
            <span>ReconcilePro Active Ledger</span>
          </div>
          <h1 className="hero-title">{businessName}</h1>
          <div className="hero-meta-row">
            <div className="hero-meta-item">
              <Building size={14} />
              <span>GSTIN: <strong>{businessGstin}</strong></span>
            </div>
            <div className="hero-meta-item">
              <Calendar size={14} />
              <span>Period: <strong>{taxPeriod}</strong></span>
            </div>
            <div className="hero-meta-item">
              <TrendingUp size={14} color="#10b981" />
              <span>Health: <strong>{matchRate}%</strong></span>
            </div>
          </div>
        </div>

        <div className="hero-actions">
          {total === 0 ? (
            <button
              type="button"
              className="btn btn-primary"
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
          <p className="section-subtitle">Real-time status across books and portal filings</p>
        </div>
        <div className="section-badge">{total} Invoices</div>
      </div>

      {/* 6 Clean KPI Cards */}
      <div className="kpi-grid">
        <KPICard
          title="TOTAL RECORDS"
          value={total}
          icon={FileText}
          subtext="Sales & Purchase bills"
          iconBg="#f1f5f9"
          iconColor="#475569"
          accentColor="#94a3b8"
        />
        <KPICard
          title="MATCHED"
          value={matched}
          icon={CheckCircle2}
          subtext={`${matchRate}% match rate`}
          iconBg="#ecfdf5"
          iconColor="#059669"
          accentColor="#059669"
        />
        <KPICard
          title="MISMATCHED"
          value={mismatched}
          icon={AlertCircle}
          subtext={`${mismatchRate}% rate variance`}
          iconBg="#fef2f2"
          iconColor="#dc2626"
          accentColor="#dc2626"
        />
        <KPICard
          title="MISSING"
          value={missing}
          icon={AlertTriangle}
          subtext="Missing in portal"
          iconBg="#fffbeb"
          iconColor="#d97706"
          accentColor="#d97706"
        />
        <KPICard
          title="EXTRA"
          value={extra}
          icon={HelpCircle}
          subtext="Not in books"
          iconBg="#faf5ff"
          iconColor="#7c3aed"
          accentColor="#7c3aed"
        />
        <KPICard
          title="POTENTIAL ANOMALIES"
          value={anomalyCount}
          icon={ShieldAlert}
          subtext="Requires review"
          iconBg="#fff7ed"
          iconColor="#ea580c"
          accentColor="#ea580c"
        />
      </div>

      {/* Empty State Banner if Business has 0 records */}
      {total === 0 && (
        <div
          className="institutional-card"
          style={{
            textAlign: "center",
            padding: "48px 24px",
            borderRadius: "18px",
            background: "#ffffff",
            border: "1px solid #e7e2dc",
            boxShadow: "0 2px 8px rgba(15, 23, 42, 0.04)",
            marginBottom: "24px",
          }}
        >
          <div
            style={{
              width: 56,
              height: 56,
              borderRadius: "16px",
              background: "#fff7ed",
              border: "1px solid #fed7aa",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              margin: "0 auto 16px",
              color: "#ea580c",
            }}
          >
            <UploadCloud size={28} />
          </div>
          <h3 style={{ fontSize: 18, fontWeight: 800, color: "#1e293b", marginBottom: 6 }}>
            No reconciliation data available
          </h3>
          <p style={{ fontSize: 13.5, color: "#64748b", maxWidth: 440, margin: "0 auto 20px" }}>
            No invoices have been uploaded for this business.
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
      {total > 0 && gstr3b && (
        <div className="gstr3b-statement-card">
          <div className="statement-header">
            <div>
              <span className="statement-tag">Self-Assessed Return</span>
              <h3 className="statement-title">Form GSTR-3B Summary</h3>
              <p className="statement-subtitle">Monthly tax liability & ITC for {gstr3b.tax_period}</p>
            </div>
            <button
              type="button"
              className="btn btn-outline-light btn-sm"
              onClick={() => onNavigate("gstr3b")}
            >
              Details <ArrowRight size={13} />
            </button>
          </div>

          <div className="statement-grid">
            <div className="statement-box">
              <span className="box-label">Output Tax (Table 3.1)</span>
              <span className="box-val">{formatCurrency(gstr3b.output_tax)}</span>
              <span className="box-sub">Outward supplies</span>
            </div>
            <div className="statement-box highlight-green">
              <span className="box-label">Eligible ITC (Table 4A)</span>
              <span className="box-val text-green">{formatCurrency(gstr3b.eligible_itc)}</span>
              <span className="box-sub">Inward supplies</span>
            </div>
            <div className="statement-box highlight-red">
              <span className="box-label">ITC Reversed (Table 4B)</span>
              <span className="box-val text-red">{formatCurrency(gstr3b.itc_reversed)}</span>
              <span className="box-sub">Ineligible credit</span>
            </div>
            <div className="statement-box highlight-primary">
              <span className="box-label">Net ITC (Table 4C)</span>
              <span className="box-val text-saffron">{formatCurrency(gstr3b.net_itc)}</span>
              <span className="box-sub">Available credit</span>
            </div>
          </div>
        </div>
      )}

      {/* 4. Two-Column Layout: Health Progress + Attention Required */}
      {total > 0 && (
      <div className="dashboard-dual-grid">
        {/* Left: Health Visual Breakdown */}
        <div className="institutional-card">
          <div className="card-header">
            <div>
              <h3 className="card-title">Reconciliation Health</h3>
              <p className="card-subtitle">Filing alignment distribution</p>
            </div>
            <span className="health-percentage-badge">{matchRate}% Matched</span>
          </div>

          <div className="health-breakdown-list">
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

        {/* Right: Attention Required Section */}
        <div className="institutional-card">
          <div className="card-header">
            <div>
              <h3 className="card-title">Attention Required</h3>
              <p className="card-subtitle">Discrepancies requiring review</p>
            </div>
            <span className="badge badge-high">{attentionItems.length} Invoices</span>
          </div>

          <div className="attention-items-list">
            {attentionItems.length === 0 ? (
              <div className="empty-state">
                <CheckCircle2 size={32} color="#059669" className="empty-icon" />
                <p>All ledger records reconciled.</p>
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
            <p className="section-subtitle">Common compliance workflows</p>
          </div>
        </div>

        <div className="quick-actions-grid">
          <div className="quick-action-card" onClick={() => onNavigate("sales")}>
            <div className="action-icon-wrap bg-saffron">
              <CheckCircle2 size={18} color="#ea580c" />
            </div>
            <h4>Reconcile Sales</h4>
            <p>Match sales book with GSTR-1</p>
            <div className="action-arrow"><ArrowRight size={14} /></div>
          </div>

          <div className="quick-action-card" onClick={() => onNavigate("upload")}>
            <div className="action-icon-wrap bg-saffron">
              <UploadCloud size={18} color="#ea580c" />
            </div>
            <h4>Upload Ledger</h4>
            <p>Ingest sales or purchase CSV</p>
            <div className="action-arrow"><ArrowRight size={14} /></div>
          </div>

          <div className="quick-action-card" onClick={() => onNavigate("anomalies")}>
            <div className="action-icon-wrap bg-red">
              <ShieldAlert size={18} color="#dc2626" />
            </div>
            <h4>Audit Exceptions</h4>
            <p>Review flagged transactions</p>
            <div className="action-arrow"><ArrowRight size={14} /></div>
          </div>

          <div className="quick-action-card" onClick={() => onNavigate("reports")}>
            <div className="action-icon-wrap bg-green">
              <BarChart3 size={18} color="#059669" />
            </div>
            <h4>Export Reports</h4>
            <p>Download audit schedules</p>
            <div className="action-arrow"><ArrowRight size={14} /></div>
          </div>
        </div>
      </div>

      {/* 6. Recent Invoices Snapshot */}
      {total > 0 && (
        <div className="institutional-card">
          <div className="card-header">
            <div>
              <h3 className="card-title">Recent Invoices</h3>
              <p className="card-subtitle">Active transactions snapshot</p>
            </div>
            <div className="header-actions">
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => onNavigate("sales")}>
                View All Sales
              </button>
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => onNavigate("purchase")}>
                View All Purchases
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
                    <td style={{ textAlign: "right" }}>{formatCurrency(row.taxable_value)}</td>
                    <td style={{ textAlign: "right" }}>{formatCurrency(row.gst_amount)}</td>
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
