import { ReconciliationTable } from "../components/ReconciliationTable";
import { KPICard } from "../components/KPICard";
import { CheckCircle2, AlertCircle, AlertTriangle, HelpCircle } from "lucide-react";

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
      <div className="kpi-grid" style={{ marginBottom: 20 }}>
        <KPICard
          title="Total Inward Records"
          value={purchases.length}
          subtext="Purchase Register & GSTR-2A"
        />
        <KPICard
          title="Eligible Matched ITC"
          value={matched}
          icon={CheckCircle2}
          subtext="Confirmed supplier filings"
          iconBg="#ecfdf5"
          iconColor="#059669"
        />
        <KPICard
          title="ITC Mismatches"
          value={mismatched}
          icon={AlertCircle}
          subtext="Tax difference with vendor"
          iconBg="#fff1f2"
          iconColor="#e11d48"
        />
        <KPICard
          title="ITC at Risk (Missing)"
          value={missing}
          icon={AlertTriangle}
          subtext={`Est. ${formatCurrency(missingItc)} unclaimed`}
          iconBg="#fffbeb"
          iconColor="#d97706"
        />
        <KPICard
          title="Unbooked Invoices"
          value={extra}
          icon={HelpCircle}
          subtext="Supplier filed, not in books"
          iconBg="#faf5ff"
          iconColor="#9333ea"
        />
      </div>

      <ReconciliationTable
        title="Purchase Register ↔ GSTR-2A Comparison"
        subtitle="Verification of inward supplies and Input Tax Credit (ITC) eligibility against vendor filings"
        records={purchases}
        onSelectInvoice={onSelectInvoice}
      />
    </div>
  );
}
