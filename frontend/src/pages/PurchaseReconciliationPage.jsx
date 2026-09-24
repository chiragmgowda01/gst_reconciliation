import { ReconciliationTable } from "../components/ReconciliationTable";
import { KPICard } from "../components/KPICard";
import { CheckCircle2, AlertCircle, AlertTriangle, HelpCircle, FileText } from "lucide-react";

export function PurchaseReconciliationPage({ purchases = [], onSelectInvoice }) {
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

  return (
    <div className="animate-fade-in">
      <div className="section-header" style={{ marginBottom: 20 }}>
        <div>
          <h2 className="section-title">Purchase Register ↔ GSTR-2A Reconciliation</h2>
          <p className="section-subtitle">
            Verifying Input Tax Credit (ITC) eligibility between vendor invoices and auto-drafted portal records
          </p>
        </div>
        <div className="section-badge">
          <FileText size={13} />
          <span>{purchases.length} Inward Invoices</span>
        </div>
      </div>

      <div className="kpi-grid" style={{ marginBottom: 24 }}>
        <KPICard
          title="Total Inward Records"
          value={purchases.length}
          subtext="Purchase Register & GSTR-2A"
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
          subtext={`Est. ${formatCurrency(missingItc)} unclaimed`}
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

      <ReconciliationTable
        title="Purchase Register ↔ Form GSTR-2A Comparison Matrix"
        subtitle="Verification of inward bills and Input Tax Credit (ITC) eligibility against supplier portal filings"
        records={purchases}
        onSelectInvoice={onSelectInvoice}
      />
    </div>
  );
}
