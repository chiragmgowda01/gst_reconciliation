import { ReconciliationTable } from "../components/ReconciliationTable";
import { KPICard } from "../components/KPICard";
import { CheckCircle2, AlertCircle, AlertTriangle, HelpCircle, FileText, Info } from "lucide-react";

export function PurchaseReconciliationPage({
  purchases = [],
  onSelectInvoice,
  purchaseSource = "gstr2a",
  onSelectPurchaseSource,
}) {
  const matched = purchases.filter((p) => p.status === "MATCH").length;
  const mismatched = purchases.filter((p) => p.status === "MISMATCH").length;
  const missing = purchases.filter((p) => p.status === "MISSING_IN_GST").length;
  const extra = purchases.filter((p) => p.status === "EXTRA_IN_GST").length;

  const missingItc = purchases
    .filter((p) => p.status === "MISSING_IN_GST")
    .reduce((acc, curr) => acc + (curr.gst_amount || 0), 0);

  const formatCurrency = (val) => {
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR",
      maximumFractionDigits: 0,
    }).format(val);
  };

  const is2B = purchaseSource === "gstr2b";
  const sourceName = is2B ? "GSTR-2B" : "GSTR-2A";

  return (
    <div className="animate-fade-in">
      {/* 1. Header with Source Dataset Selector */}
      <div className="section-header" style={{ marginBottom: 16 }}>
        <div>
          <h2 className="section-title">Purchase Register ↔ {sourceName} Reconciliation</h2>
          <p className="section-subtitle">
            {is2B
              ? "Verifying Input Tax Credit (ITC) eligibility under Rule 36(4) against static auto-drafted statement"
              : "Verifying inward supply invoices against dynamic supplier portal filings"}
          </p>
        </div>

        {/* Source Switcher: GSTR-2A vs GSTR-2B */}
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div
            style={{
              display: "inline-flex",
              background: "#f1f5f9",
              padding: 3,
              borderRadius: 8,
              border: "1px solid #e2e8f0",
            }}
          >
            <button
              type="button"
              className={`btn btn-sm ${!is2B ? "btn-primary" : "btn-secondary"}`}
              style={{
                fontSize: 12,
                padding: "4px 12px",
                height: 30,
                borderRadius: 6,
                fontWeight: !is2B ? 700 : 500,
              }}
              onClick={() => onSelectPurchaseSource && onSelectPurchaseSource("gstr2a")}
            >
              Form GSTR-2A (Dynamic)
            </button>
            <button
              type="button"
              className={`btn btn-sm ${is2B ? "btn-primary" : "btn-secondary"}`}
              style={{
                fontSize: 12,
                padding: "4px 12px",
                height: 30,
                borderRadius: 6,
                fontWeight: is2B ? 700 : 500,
              }}
              onClick={() => onSelectPurchaseSource && onSelectPurchaseSource("gstr2b")}
            >
              Form GSTR-2B (Static)
            </button>
          </div>

          <div className="section-badge">
            <FileText size={13} />
            <span>{purchases.length} Invoices</span>
          </div>
        </div>
      </div>

      {/* Statutory ITC Guidance Banner */}
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          gap: 10,
          padding: "10px 14px",
          background: is2B ? "#eff6ff" : "#f8fafc",
          border: `1px solid ${is2B ? "#bfdbfe" : "#e2e8f0"}`,
          borderRadius: 8,
          marginBottom: 20,
          fontSize: 12,
          color: is2B ? "#1e40af" : "#475569",
          lineHeight: 1.5,
        }}
      >
        <Info size={15} style={{ flexShrink: 0, marginTop: 2, color: is2B ? "#2563eb" : "#64748b" }} />
        <div>
          {is2B ? (
            <span>
              <strong>Rule 36(4) Compliance Guidance:</strong> Form GSTR-2B is the official static auto-drafted statement
              used to determine eligible ITC for monthly GSTR-3B filings. Invoices missing in GSTR-2B do not automatically establish
              statutory ineligibility; suppliers filing after the 11th/13th cut-off will reflect in next month’s statement.
            </span>
          ) : (
            <span>
              <strong>Dynamic Verification:</strong> Form GSTR-2A reflects all supplier filings continuously as they are submitted.
              Use GSTR-2A for ongoing vendor tracking, and GSTR-2B for final GSTR-3B Table 4(A) claim determination.
            </span>
          )}
        </div>
      </div>

      {/* 2. KPI Cards */}
      <div className="kpi-grid" style={{ marginBottom: 24 }}>
        <KPICard
          title="Total Inward Records"
          value={purchases.length}
          subtext={`Purchase Register & ${sourceName}`}
          icon={FileText}
          iconBg="#eff6ff"
          iconColor="#2563eb"
          accentColor="#2563eb"
        />
        <KPICard
          title="Eligible Matched ITC"
          value={matched}
          icon={CheckCircle2}
          subtext="Confirmed vendor filings"
          iconBg="#ecfdf5"
          iconColor="#059669"
          accentColor="#059669"
        />
        <KPICard
          title="ITC Mismatches"
          value={mismatched}
          icon={AlertCircle}
          subtext="Tax divergence with vendor"
          iconBg="#fef2f2"
          iconColor="#dc2626"
          accentColor="#dc2626"
        />
        <KPICard
          title="ITC at Risk (Missing)"
          value={missing}
          icon={AlertTriangle}
          subtext={`Est. ${formatCurrency(missingItc)} requiring review`}
          iconBg="#fffbeb"
          iconColor="#d97706"
          accentColor="#d97706"
        />
        <KPICard
          title="Unbooked Invoices"
          value={extra}
          icon={HelpCircle}
          subtext="Supplier filed, not in books"
          iconBg="#faf5ff"
          iconColor="#7c3aed"
          accentColor="#7c3aed"
        />
      </div>

      {/* 3. Table */}
      <ReconciliationTable
        title={`Purchase Register ↔ Form ${sourceName} Comparison Matrix`}
        subtitle={`Verification of inward bills and Input Tax Credit (ITC) eligibility against supplier ${sourceName} filings`}
        records={purchases}
        onSelectInvoice={onSelectInvoice}
      />
    </div>
  );
}
