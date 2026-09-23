import {
  FileText,
  CheckCircle2,
  AlertCircle,
  AlertTriangle,
  HelpCircle,
  ShieldAlert,
  ArrowRight,
} from "lucide-react";
import { KPICard } from "../components/KPICard";
import { StatusBadge } from "../components/StatusBadge";

export function DashboardPage({ data, gstr3b, anomalies, onSelectInvoice, onNavigate }) {
  const sales = data?.sales || [];
  const purchases = data?.purchases || [];
  const allRecords = [...sales, ...purchases];

  const total = allRecords.length;
  const matched = allRecords.filter((r) => r.status === "MATCH").length;
  const mismatched = allRecords.filter((r) => r.status === "MISMATCH").length;
  const missing = allRecords.filter((r) => r.status === "MISSING_IN_GST").length;
  const extra = allRecords.filter((r) => r.status === "EXTRA_IN_GST").length;
  const anomalyCount = anomalies?.length || 0;

  const matchRate = total > 0 ? ((matched / total) * 100).toFixed(1) : "0.0";
  const mismatchRate = total > 0 ? ((mismatched / total) * 100).toFixed(1) : "0.0";
  const missingRate = total > 0 ? ((missing / total) * 100).toFixed(1) : "0.0";
  const extraRate = total > 0 ? ((extra / total) * 100).toFixed(1) : "0.0";

  // Attention items: Mismatches and Missing Invoices
  const attentionItems = allRecords.filter(
    (r) => r.status === "MISMATCH" || r.status === "MISSING_IN_GST"
  );

  const formatCurrency = (val) => {
    if (val === null || val === undefined) return "—";
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR",
      maximumFractionDigits: 0,
    }).format(val);
  };

  return (
    <div className="dashboard-page animate-fade-in">
      {/* KPI Cards Grid */}
      <div className="kpi-grid">
        <KPICard
          title="Total Invoices"
          value={total}
          icon={FileText}
          subtext="Across sales and purchase registers"
          iconBg="#eff6ff"
          iconColor="#2563eb"
        />
        <KPICard
          title="Matched"
          value={matched}
          icon={CheckCircle2}
          subtext={`${matchRate}% match rate`}
          iconBg="#ecfdf5"
          iconColor="#059669"
        />
        <KPICard
          title="Mismatched"
          value={mismatched}
          icon={AlertCircle}
          subtext={`${mismatchRate}% discrepancies found`}
          iconBg="#fff1f2"
          iconColor="#e11d48"
        />
        <KPICard
          title="Missing in GST"
          value={missing}
          icon={AlertTriangle}
          subtext="Risk of unclaimed ITC / unfiled sales"
          iconBg="#fffbeb"
          iconColor="#d97706"
        />
        <KPICard
          title="Extra in GST"
          value={extra}
          icon={HelpCircle}
          subtext="Portal records not in internal books"
          iconBg="#faf5ff"
          iconColor="#9333ea"
        />
        <KPICard
          title="Audit Anomalies"
          value={anomalyCount}
          icon={ShieldAlert}
          subtext="High & medium risk exceptions"
          iconBg="#fef2f2"
          iconColor="#dc2626"
        />
      </div>

      {/* GSTR-3B Hero Summary (Visually Distinct Section) */}
      {gstr3b && (
        <div className="gstr3b-hero">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 12 }}>
            <div>
              <h2>GSTR-3B Return Summary</h2>
              <p>Statutory tax summary for Tax Period: <strong>{gstr3b.tax_period}</strong></p>
            </div>
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => onNavigate("gstr3b")}
              style={{ backgroundColor: "rgba(255,255,255,0.15)", color: "#fff", borderColor: "rgba(255,255,255,0.25)" }}
            >
              Detailed Breakdown <ArrowRight size={13} />
            </button>
          </div>

          <div className="gstr3b-grid">
            <div className="gstr3b-box">
              <div className="gstr3b-box-label">Output Tax Liability</div>
              <div className="gstr3b-box-val">{formatCurrency(gstr3b.output_tax)}</div>
            </div>
            <div className="gstr3b-box">
              <div className="gstr3b-box-label">Eligible Input Tax Credit (ITC)</div>
              <div className="gstr3b-box-val" style={{ color: "#86efac" }}>{formatCurrency(gstr3b.eligible_itc)}</div>
            </div>
            <div className="gstr3b-box">
              <div className="gstr3b-box-label">ITC Reversed</div>
              <div className="gstr3b-box-val" style={{ color: "#fca5a5" }}>{formatCurrency(gstr3b.itc_reversed)}</div>
            </div>
            <div className="gstr3b-box" style={{ background: "rgba(59, 130, 246, 0.25)", borderColor: "#60a5fa" }}>
              <div className="gstr3b-box-label" style={{ color: "#dbeafe" }}>Net ITC Available</div>
              <div className="gstr3b-box-val">{formatCurrency(gstr3b.net_itc)}</div>
            </div>
          </div>
        </div>
      )}

      {/* Two Column Layout: Visual Breakdown + Attention Required */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(420px, 1fr))", gap: 24, marginBottom: 24 }}>
        {/* Reconciliation Health Overview */}
        <div className="card" style={{ marginBottom: 0 }}>
          <div className="card-header">
            <div>
              <h3 className="card-title">Reconciliation Health Status</h3>
              <p className="card-subtitle">Distribution of matched and flagged invoices</p>
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {/* MATCH */}
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5, marginBottom: 6 }}>
                <span style={{ fontWeight: 600, color: "#059669" }}>MATCH</span>
                <span style={{ fontWeight: 700 }}>{matched} ({matchRate}%)</span>
              </div>
              <div className="progress-bar-bg">
                <div className="progress-bar-fill" style={{ width: `${matchRate}%`, backgroundColor: "#10b981" }} />
              </div>
            </div>

            {/* MISMATCH */}
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5, marginBottom: 6 }}>
                <span style={{ fontWeight: 600, color: "#e11d48" }}>MISMATCH</span>
                <span style={{ fontWeight: 700 }}>{mismatched} ({mismatchRate}%)</span>
              </div>
              <div className="progress-bar-bg">
                <div className="progress-bar-fill" style={{ width: `${mismatchRate}%`, backgroundColor: "#f43f5e" }} />
              </div>
            </div>

            {/* MISSING IN GST */}
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5, marginBottom: 6 }}>
                <span style={{ fontWeight: 600, color: "#d97706" }}>MISSING IN GST</span>
                <span style={{ fontWeight: 700 }}>{missing} ({missingRate}%)</span>
              </div>
              <div className="progress-bar-bg">
                <div className="progress-bar-fill" style={{ width: `${missingRate}%`, backgroundColor: "#f59e0b" }} />
              </div>
            </div>

            {/* EXTRA IN GST */}
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5, marginBottom: 6 }}>
                <span style={{ fontWeight: 600, color: "#9333ea" }}>EXTRA IN GST</span>
                <span style={{ fontWeight: 700 }}>{extra} ({extraRate}%)</span>
              </div>
              <div className="progress-bar-bg">
                <div className="progress-bar-fill" style={{ width: `${extraRate}%`, backgroundColor: "#a855f7" }} />
              </div>
            </div>
          </div>
        </div>

        {/* Attention Required Section */}
        <div className="card" style={{ marginBottom: 0 }}>
          <div className="card-header">
            <div>
              <h3 className="card-title">Attention Required</h3>
              <p className="card-subtitle">Invoices with discrepancies requiring MSME review</p>
            </div>
            <span className="badge badge-high">{attentionItems.length} Pending</span>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {attentionItems.length === 0 ? (
              <div className="empty-state">No discrepancies requiring attention! All records reconciled.</div>
            ) : (
              attentionItems.slice(0, 4).map((item) => (
                <div
                  key={item.invoice_no}
                  onClick={() => onSelectInvoice(item)}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "10px 12px",
                    backgroundColor: "var(--slate-50)",
                    border: "1px solid var(--border-color)",
                    borderRadius: "var(--radius-sm)",
                    cursor: "pointer",
                    transition: "background 0.15s ease",
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = "#f1f5f9")}
                  onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "var(--slate-50)")}
                >
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ fontWeight: 700, fontFamily: "var(--font-mono)", fontSize: 13 }}>
                        {item.invoice_no}
                      </span>
                      <StatusBadge status={item.status} />
                    </div>
                    <div style={{ fontSize: 11.5, color: "var(--text-muted)", marginTop: 2 }}>
                      {item.explanation || "Discrepancy identified in values"}
                    </div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: "#e11d48", fontFamily: "var(--font-mono)" }}>
                      {item.taxable_value_diff ? `Diff: ${formatCurrency(item.taxable_value_diff)}` : "Missing in Portal"}
                    </div>
                    <div style={{ fontSize: 11, color: "#2563eb", display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 3, marginTop: 2 }}>
                      Inspect <ArrowRight size={11} />
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Recent Reconciliation Activity */}
      <div className="card">
        <div className="card-header">
          <div>
            <h3 className="card-title">Recent Invoices Reconciled</h3>
            <p className="card-subtitle">Quick snapshot of recent transactions across sales and purchase books</p>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn btn-secondary btn-sm" onClick={() => onNavigate("sales")}>
              View All Sales
            </button>
            <button className="btn btn-secondary btn-sm" onClick={() => onNavigate("purchase")}>
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
                <th>GSTIN</th>
                <th style={{ textAlign: "right" }}>Taxable Value</th>
                <th style={{ textAlign: "right" }}>GST Amount</th>
                <th>Status</th>
                <th style={{ textAlign: "center" }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {allRecords.slice(0, 6).map((row) => (
                <tr key={row.invoice_no}>
                  <td className="mono-cell" style={{ fontWeight: 600 }}>{row.invoice_no}</td>
                  <td>{row.invoice_date || "—"}</td>
                  <td className="mono-cell">{row.gstin || "—"}</td>
                  <td style={{ textAlign: "right" }}>{formatCurrency(row.taxable_value)}</td>
                  <td style={{ textAlign: "right" }}>{formatCurrency(row.gst_amount)}</td>
                  <td><StatusBadge status={row.status} /></td>
                  <td style={{ textAlign: "center" }}>
                    <button
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
    </div>
  );
}
