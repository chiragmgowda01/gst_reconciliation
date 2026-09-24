import { ReconciliationTable } from "../components/ReconciliationTable";
import { KPICard } from "../components/KPICard";
import { CheckCircle2, AlertCircle, AlertTriangle, HelpCircle, FileText } from "lucide-react";

export function SalesReconciliationPage({ sales = [], onSelectInvoice }) {
  const matched = sales.filter((s) => s.status === "MATCH").length;
  const mismatched = sales.filter((s) => s.status === "MISMATCH").length;
  const missing = sales.filter((s) => s.status === "MISSING_IN_GST").length;
  const extra = sales.filter((s) => s.status === "EXTRA_IN_GST").length;

  return (
    <div className="animate-fade-in">
      <div className="section-header" style={{ marginBottom: 20 }}>
        <div>
          <h2 className="section-title">Sales Register ↔ GSTR-1 Reconciliation</h2>
          <p className="section-subtitle">
            Cross-matching internal sales bills against GSTR-1 outward supply portal returns
          </p>
        </div>
        <div className="section-badge">
          <FileText size={13} />
          <span>{sales.length} Outward Invoices</span>
        </div>
      </div>

      <div className="kpi-grid" style={{ marginBottom: 24 }}>
        <KPICard
          title="Total Outward Records"
          value={sales.length}
          subtext="Sales Register & GSTR-1"
          icon={FileText}
          iconBg="#eff6ff"
          iconColor="#2563eb"
          accentColor="#2563eb"
        />
        <KPICard
          title="Matched Sales"
          value={matched}
          icon={CheckCircle2}
          subtext="Properly filed in GSTR-1"
          iconBg="#ecfdf5"
          iconColor="#059669"
          accentColor="#059669"
        />
        <KPICard
          title="Value Mismatches"
          value={mismatched}
          icon={AlertCircle}
          subtext="Taxable or tax divergence"
          iconBg="#fef2f2"
          iconColor="#dc2626"
          accentColor="#dc2626"
        />
        <KPICard
          title="Missing in GSTR-1"
          value={missing}
          icon={AlertTriangle}
          subtext="Unfiled sales liability"
          iconBg="#fffbeb"
          iconColor="#d97706"
          accentColor="#d97706"
        />
        <KPICard
          title="Extra on Portal"
          value={extra}
          icon={HelpCircle}
          subtext="Portal records not in sales book"
          iconBg="#faf5ff"
          iconColor="#7c3aed"
          accentColor="#7c3aed"
        />
      </div>

      <ReconciliationTable
        title="Sales Register ↔ Form GSTR-1 Comparison Matrix"
        subtitle="Line-item verification of outward supplies recorded in internal books against filed GSTR-1 returns"
        records={sales}
        onSelectInvoice={onSelectInvoice}
      />
    </div>
  );
}
