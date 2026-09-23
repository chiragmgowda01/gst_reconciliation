import { ReconciliationTable } from "../components/ReconciliationTable";
import { KPICard } from "../components/KPICard";
import { CheckCircle2, AlertCircle, AlertTriangle, HelpCircle } from "lucide-react";

export function SalesReconciliationPage({ sales = [], onSelectInvoice }) {
  const matched = sales.filter((s) => s.status === "MATCH").length;
  const mismatched = sales.filter((s) => s.status === "MISMATCH").length;
  const missing = sales.filter((s) => s.status === "MISSING_IN_GST").length;
  const extra = sales.filter((s) => s.status === "EXTRA_IN_GST").length;

  return (
    <div className="animate-fade-in">
      <div className="kpi-grid" style={{ marginBottom: 20 }}>
        <KPICard
          title="Total Outward Records"
          value={sales.length}
          subtext="Sales Register & GSTR-1"
        />
        <KPICard
          title="Matched Sales"
          value={matched}
          icon={CheckCircle2}
          subtext="Properly filed in GSTR-1"
          iconBg="#ecfdf5"
          iconColor="#059669"
        />
        <KPICard
          title="Value Mismatches"
          value={mismatched}
          icon={AlertCircle}
          subtext="Rate / amount divergence"
          iconBg="#fff1f2"
          iconColor="#e11d48"
        />
        <KPICard
          title="Missing in GSTR-1"
          value={missing}
          icon={AlertTriangle}
          subtext="Unfiled sales liability"
          iconBg="#fffbeb"
          iconColor="#d97706"
        />
        <KPICard
          title="Extra on Portal"
          value={extra}
          icon={HelpCircle}
          subtext="Not in sales book"
          iconBg="#faf5ff"
          iconColor="#9333ea"
        />
      </div>

      <ReconciliationTable
        title="Sales Register ↔ GSTR-1 Comparison"
        subtitle="Verification of outward supplies recorded in books against filed GSTR-1 returns"
        records={sales}
        onSelectInvoice={onSelectInvoice}
      />
    </div>
  );
}
