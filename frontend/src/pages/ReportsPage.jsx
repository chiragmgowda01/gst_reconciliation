import { useState, useEffect } from "react";
import {
  Download,
  FileSpreadsheet,
  CheckCircle2,
  AlertCircle,
  ShieldCheck,
  FileText,
  RotateCw,
  Info,
  Calendar,
} from "lucide-react";
import { api } from "../api/client";
import { KPICard } from "../components/KPICard";
import { LoadingSkeleton } from "../components/LoadingSkeleton";

export function ReportsPage({ onNavigate }) {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [purchaseSource, setPurchaseSource] = useState("gstr2a");
  const [taxPeriod, setTaxPeriod] = useState("");

  const [downloadingId, setDownloadingId] = useState(null);
  const [downloadError, setDownloadError] = useState("");
  const [downloadSuccess, setDownloadSuccess] = useState("");

  useEffect(() => {
    let ignore = false;
    api.getReportsSummary({
      purchase_source: purchaseSource,
      tax_period: taxPeriod || undefined,
    })
      .then((data) => {
        if (!ignore) {
          setSummary(data);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!ignore) {
          setLoading(false);
          setDownloadError(err.message || "Failed to load report summary metrics from server.");
        }
      });

    return () => {
      ignore = true;
    };
  }, [purchaseSource, taxPeriod]);

  const handleExport = async (type, title) => {
    setDownloadingId(type);
    setDownloadError("");
    setDownloadSuccess("");

    try {
      const res = await api.downloadReport(type, purchaseSource, taxPeriod || null);
      if (res && res.success) {
        setDownloadSuccess(`Successfully triggered download for "${res.filename || title}" (${(res.size / 1024).toFixed(1)} KB).`);
        setTimeout(() => setDownloadSuccess(""), 4500);
      }
    } catch (err) {
      setDownloadError(err.message || `Download failed for report: ${title}. Please check server connectivity.`);
    } finally {
      setDownloadingId(null);
    }
  };

  const reportsList = [
    // ── Group 1: 6 Sales & GSTR-1 Outward Supply Reports ──
    {
      id: "sales",
      group: "sales",
      title: "Sales Reconciliation Register Schedule",
      desc: "Complete matching matrix of internal Sales Register invoices against Form GSTR-1 outward returns with difference calculations.",
      badge: "Outward Supplies",
      frequency: "Monthly Tax Period",
    },
    {
      id: "sales_matched",
      group: "sales",
      title: "Sales Matched Outward Supplies Register",
      desc: "Verified sales invoices where taxable values and GST liabilities match between sales register and Form GSTR-1.",
      badge: "Outward Matched",
      frequency: "Monthly Filing",
    },
    {
      id: "sales_mismatches",
      group: "sales",
      title: "Sales Tax Value & Rate Discrepancy Report",
      desc: "Filtered schedule of sales transactions where taxable value or GST amount differs between company books and GSTR-1 return.",
      badge: "Outward Variance",
      frequency: "Immediate Review",
    },
    {
      id: "sales_missing",
      group: "sales",
      title: "Sales Invoices Missing in GSTR-1 (Unfiled Liability)",
      desc: "Sales recorded in internal books but absent in Form GSTR-1, representing unfiled outward tax liability requiring addition to GSTR-1.",
      badge: "Compliance Risk",
      frequency: "High Priority",
    },
    {
      id: "sales_extra",
      group: "sales",
      title: "Unrecorded Return Sales (Extra on GSTR-1)",
      desc: "Invoices filed on Form GSTR-1 but not found in the internal sales register, indicating omitted accounting entries.",
      badge: "Ledger Omission",
      frequency: "Monthly Audit",
    },
    {
      id: "sales_tax_liability",
      group: "sales",
      title: "Outward Tax Liability Variance Schedule",
      desc: "Structured tax liability comparison schedule itemizing expected vs filed output tax for GSTR-3B Table 3.1 alignment.",
      badge: "Liability Breakdown",
      frequency: "GSTR-3B Preparation",
    },

    // ── Group 2: 6 Purchase & Inward ITC Reports ──
    {
      id: "purchases",
      group: "purchases",
      title: `Purchase & ITC Reconciliation Matrix (${purchaseSource === "gstr2b" ? "GSTR-2B" : "GSTR-2A"})`,
      desc: `Comprehensive matching matrix between inward Purchase Register bills and ${purchaseSource === "gstr2b" ? "static auto-drafted Form GSTR-2B statement" : "imported dynamic Form GSTR-2A supplier filings"}.`,
      badge: "Inward Verification",
      frequency: "Monthly Tax Period",
    },
    {
      id: "purchase_matched",
      group: "purchases",
      title: `Verified Eligible ITC Schedule (${purchaseSource === "gstr2b" ? "GSTR-2B" : "GSTR-2A"})`,
      desc: "Inward bills with confirmed matching supplier filings, representing verified eligible Input Tax Credit for GSTR-3B Table 4(A).",
      badge: "Confirmed ITC",
      frequency: "Monthly Return",
    },
    {
      id: "purchase_mismatches",
      group: "purchases",
      title: `Inward Tax Value & ITC Rate Variance Report`,
      desc: "Inward vendor invoices where taxable value or GST amounts diverge between accounting books and supplier filings.",
      badge: "ITC Variance",
      frequency: "Vendor Action",
    },
    {
      id: "purchase_missing",
      group: "purchases",
      title: `Purchase Invoices Missing in Supplier Filings (ITC at Risk)`,
      desc: `Purchases booked in internal accounts but absent from ${purchaseSource === "gstr2b" ? "Form GSTR-2B" : "Form GSTR-2A"}, representing unconfirmed ITC requiring supplier communication.`,
      badge: "At-Risk ITC",
      frequency: "Urgent Vendor Follow-up",
    },
    {
      id: "purchase_extra",
      group: "purchases",
      title: `Unbooked Supplier Filings (Extra Invoices in Statement)`,
      desc: `Invoices filed by vendors that are not yet recorded in the purchase register, representing unbooked expenses and unclaimed ITC.`,
      badge: "Unclaimed ITC",
      frequency: "Accounts Payable Review",
    },
    {
      id: "itc_eligibility_variance",
      group: "purchases",
      title: `ITC Eligibility & Statement Variance Schedule`,
      desc: `Itemized comparison statement between purchase ledger claims and auto-drafted ITC statements for statutory compliance under Rule 36(4).`,
      badge: "Rule 36(4) Audit",
      frequency: "Monthly CA Review",
    },
  ];

  const filteredReports = categoryFilter === "all"
    ? reportsList
    : reportsList.filter((r) => r.group === categoryFilter);

  if (loading && !summary) return <LoadingSkeleton />;

  return (
    <div className="animate-fade-in">
      <div className="data-source-note" role="note">
        <Info size={16} />
        <span>Reports use records saved for this business. GST portal statements must be imported; live GSTN sync is not connected.</span>
      </div>

      {/* 1. Page Header */}
      <div className="section-header" style={{ marginBottom: 20 }}>
        <div>
          <h2 className="section-title">Reports</h2>
          <p className="section-subtitle">
            Review reconciliation results or download a CSV schedule.
          </p>
        </div>
      </div>

      {/* Download Alert Banners */}
      {downloadError && (
        <div
          className="upload-error-banner"
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: 16,
            padding: "10px 14px",
            background: "#fef2f2",
            border: "1px solid #fecaca",
            borderRadius: 8,
            color: "#b91c1c",
            fontSize: 13,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <AlertCircle size={16} />
            <span>{downloadError}</span>
          </div>
          <button
            type="button"
            className="btn btn-sm btn-secondary"
            style={{ fontSize: 11, padding: "2px 8px", height: 24 }}
            onClick={() => setDownloadError("")}
          >
            Dismiss
          </button>
        </div>
      )}

      {downloadSuccess && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            marginBottom: 16,
            padding: "10px 14px",
            background: "#ecfdf5",
            border: "1px solid #a7f3d0",
            borderRadius: 8,
            color: "#047857",
            fontSize: 13,
            fontWeight: 500,
          }}
        >
          <CheckCircle2 size={16} color="#059669" />
          <span>{downloadSuccess}</span>
        </div>
      )}

      {/* 2. Top Summary Metrics Cards (derived from real API summary data) */}
      {summary?.has_data ? (
        <div className="kpi-grid">
          <KPICard
            title="Reconciliation Health"
            value={`${summary.audit_health_score}%`}
            icon={ShieldCheck}
            subtext="Weighted reconciliation alignment score"
            iconBg="#ecfdf5"
            iconColor="#059669"
            accentColor="#059669"
          />
          <KPICard
            title="Sales Match Rate"
            value={`${summary.sales_summary.match_rate_percentage}%`}
            icon={CheckCircle2}
            subtext={`${summary.sales_summary?.matched ?? 0} of ${summary.sales_summary?.total_records ?? 0} outward verified`}
            iconBg="#eff6ff"
            iconColor="#2563eb"
            accentColor="#2563eb"
          />
          <KPICard
            title="Purchase ITC Match Rate"
            value={`${summary.purchase_summary.match_rate_percentage}%`}
            icon={CheckCircle2}
            subtext={`${summary.purchase_summary?.matched ?? 0} of ${summary.purchase_summary?.total_records ?? 0} inward verified`}
            iconBg="#eff6ff"
            iconColor="#2563eb"
            accentColor="#2563eb"
          />
        </div>
      ) : summary ? (
        <div className="institutional-card empty-state-card">
          <div className="empty-state">
            <FileText size={34} className="empty-icon" />
            <h3>No report data yet</h3>
            <p>Upload your registers and import the GST statements you want to compare. Performance rates will appear after records are available.</p>
            <button type="button" className="btn btn-primary" onClick={() => onNavigate?.("upload")}>
              Upload records
            </button>
          </div>
        </div>
      ) : null}

      {/* 3. Export Schedules List */}
      <div className="institutional-card">
        <div className="card-header" style={{ flexWrap: "wrap", gap: 12 }}>
          <div>
            <h3 className="card-title">Available report templates (12)</h3>
            <p className="card-subtitle">
              Choose a schedule to download. It contains business records only when matching data has been uploaded or imported.
            </p>
          </div>

          {/* Controls: Tax Period + Category Filter + Purchase Source Selector */}
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            {/* Tax Period Selector */}
            <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12 }}>
              <Calendar size={13} color="#64748b" />
              <span style={{ color: "var(--text-muted)", fontWeight: 500 }}>Tax Period:</span>
              <select
                id="select-tax-period"
                className="filter-select"
                style={{ height: 28, fontSize: 12, padding: "2px 8px", width: 140 }}
                value={taxPeriod}
                onChange={(e) => setTaxPeriod(e.target.value)}
              >
                <option value="2026-07">2026-07 (July)</option>
                <option value="2026-08">2026-08 (August)</option>
                <option value="">All Tax Periods</option>
              </select>
            </div>

            {/* Purchase source toggle for purchase schedules */}
            <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12 }}>
              <span style={{ color: "var(--text-muted)", fontWeight: 500 }}>Inward Source:</span>
              <div
                style={{
                  display: "inline-flex",
                  background: "#f1f5f9",
                  padding: 2,
                  borderRadius: 6,
                  border: "1px solid #e2e8f0",
                }}
              >
                <button
                  id="btn-source-gstr2a"
                  type="button"
                  className={`btn btn-sm ${purchaseSource === "gstr2a" ? "btn-primary" : "btn-secondary"}`}
                  style={{
                    fontSize: 11,
                    padding: "2px 8px",
                    height: 26,
                    borderRadius: 4,
                    fontWeight: purchaseSource === "gstr2a" ? 700 : 500,
                  }}
                  onClick={() => setPurchaseSource("gstr2a")}
                >
                  GSTR-2A
                </button>
                <button
                  id="btn-source-gstr2b"
                  type="button"
                  className={`btn btn-sm ${purchaseSource === "gstr2b" ? "btn-primary" : "btn-secondary"}`}
                  style={{
                    fontSize: 11,
                    padding: "2px 8px",
                    height: 26,
                    borderRadius: 4,
                    fontWeight: purchaseSource === "gstr2b" ? 700 : 500,
                  }}
                  onClick={() => setPurchaseSource("gstr2b")}
                >
                  GSTR-2B
                </button>
              </div>
            </div>

            {/* Filter Tabs */}
            <div style={{ display: "flex", gap: 4 }}>
              <button
                id="btn-filter-all"
                type="button"
                className={`btn btn-sm ${categoryFilter === "all" ? "btn-primary" : "btn-secondary"}`}
                style={{ fontSize: 12, height: 28, padding: "0 10px" }}
                onClick={() => setCategoryFilter("all")}
              >
                All (12)
              </button>
              <button
                id="btn-filter-sales"
                type="button"
                className={`btn btn-sm ${categoryFilter === "sales" ? "btn-primary" : "btn-secondary"}`}
                style={{ fontSize: 12, height: 28, padding: "0 10px" }}
                onClick={() => setCategoryFilter("sales")}
              >
                Sales / GSTR-1 (6)
              </button>
              <button
                id="btn-filter-purchases"
                type="button"
                className={`btn btn-sm ${categoryFilter === "purchases" ? "btn-primary" : "btn-secondary"}`}
                style={{ fontSize: 12, height: 28, padding: "0 10px" }}
                onClick={() => setCategoryFilter("purchases")}
              >
                Purchase & ITC (6)
              </button>
            </div>
          </div>
        </div>

        <div className="reports-schedules-list">
          {filteredReports.map((rep) => (
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
                  id={`btn-download-${rep.id}`}
                  type="button"
                  className="btn btn-secondary report-download-btn"
                  disabled={downloadingId !== null}
                  onClick={() => handleExport(rep.id, rep.title)}
                >
                  {downloadingId === rep.id ? (
                    <>
                      <RotateCw size={14} className="animate-spin" />
                      <span>Exporting...</span>
                    </>
                  ) : (
                    <>
                      <Download size={14} />
                      <span>Download CSV</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default ReportsPage;

