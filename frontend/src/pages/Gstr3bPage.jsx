import { CheckCircle2, AlertCircle, FileText, Calendar, Building } from "lucide-react";

export function Gstr3bPage({ gstr3b, sales = [], purchases = [] }) {
  if (!gstr3b) {
    return (
      <div className="card">
        <div className="empty-state">
          <FileText size={36} className="empty-icon" />
          <p>No GSTR-3B summary data available for this business account.</p>
        </div>
      </div>
    );
  }

  const formatCurrency = (val) => {
    if (val === null || val === undefined) return "—";
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR",
      maximumFractionDigits: 2,
    }).format(val);
  };

  // Check if actual internal registers exist for comparison
  const hasRegisterData = sales.length > 0 || purchases.length > 0;
  const salesRegisterTax = sales.reduce((acc, curr) => acc + (curr.gst_amount || 0), 0);
  const purchaseRegisterItc = purchases.reduce((acc, curr) => acc + (curr.gst_amount || 0), 0);

  const outputTaxDiff = Math.round((salesRegisterTax - gstr3b.output_tax) * 100) / 100;
  const itcDiff = Math.round((purchaseRegisterItc - gstr3b.eligible_itc) * 100) / 100;
  const netTaxPayable = Math.max(0, gstr3b.output_tax - gstr3b.net_itc);

  return (
    <div className="animate-fade-in">
      {/* 1. Header Information Banner */}
      <div className="section-header" style={{ marginBottom: 20 }}>
        <div>
          <h2 className="section-title">Form GSTR-3B Self-Assessed Tax Return</h2>
          <p className="section-subtitle">
            Monthly statutory return of outward supplies, input tax credit claimed, and net cash tax liability
          </p>
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <div className="period-badge">
            <Calendar size={13} />
            <span>Tax Period: <strong>{gstr3b.tax_period}</strong></span>
          </div>
          <div className="period-badge">
            <Building size={13} />
            <span>Business ID: <strong>{gstr3b.business_id}</strong></span>
          </div>
        </div>
      </div>

      {/* 2. Prominent Financial Statement Hero Cards */}
      <div className="gstr3b-statement-card">
        <div className="statement-header">
          <div>
            <span className="statement-tag">Statutory Summary</span>
            <h3 className="statement-title">Tax Return Liabilities & Credit Schedule</h3>
            <p className="statement-subtitle">Values declared in Form GSTR-3B for tax period {gstr3b.tax_period}</p>
          </div>
        </div>

        <div className="statement-grid">
          <div className="statement-box">
            <span className="box-label">Table 3.1: Output Tax Liability</span>
            <span className="box-val">{formatCurrency(gstr3b.output_tax)}</span>
            <span className="box-sub">Payable on outward taxable supplies</span>
          </div>
          <div className="statement-box highlight-green">
            <span className="box-label">Table 4(A): Eligible ITC Available</span>
            <span className="box-val text-green">{formatCurrency(gstr3b.eligible_itc)}</span>
            <span className="box-sub">Credit from inward taxable supplies</span>
          </div>
          <div className="statement-box highlight-red">
            <span className="box-label">Table 4(B): ITC Reversed / Ineligible</span>
            <span className="box-val text-red">{formatCurrency(gstr3b.itc_reversed)}</span>
            <span className="box-sub">Ineligible / non-business reversals</span>
          </div>
          <div className="statement-box highlight-primary">
            <span className="box-label">Table 4(C): Net ITC Credited</span>
            <span className="box-val text-saffron">{formatCurrency(gstr3b.net_itc)}</span>
            <span className="box-sub">Available in Electronic Credit Ledger</span>
          </div>
          <div className="statement-box highlight-amber">
            <span className="box-label">Table 6.1: Net Tax Payable (Cash)</span>
            <span className="box-val text-amber">{formatCurrency(netTaxPayable)}</span>
            <span className="box-sub">Tax payable after ITC utilization</span>
          </div>
        </div>
      </div>

      {/* 3. Internal Register vs GSTR-3B Variance Analysis */}
      <div className="institutional-card">
        <div className="card-header">
          <div>
            <h3 className="card-title">Accounting Register vs Return Comparison</h3>
            <p className="card-subtitle">
              Verification of self-declared GSTR-3B totals against transaction-level invoices in database
            </p>
          </div>
          {hasRegisterData && (
            <span className="badge badge-medium">
              {sales.length + purchases.length} Registered Invoices
            </span>
          )}
        </div>

        {!hasRegisterData ? (
          <div className="empty-state" style={{ padding: "36px 20px" }}>
            <FileText size={32} className="empty-icon" />
            <p style={{ fontWeight: 600, color: "var(--text-main)" }}>
              Register comparison data is not available for this period.
            </p>
            <p style={{ fontSize: 12.5, color: "var(--text-muted)", marginTop: 4 }}>
              Upload Sales Register and Purchase Register CSV files to generate ledger variance analysis.
            </p>
          </div>
        ) : (
          <div className="table-wrapper">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Return Component</th>
                  <th style={{ textAlign: "right" }}>Internal Registers</th>
                  <th style={{ textAlign: "right" }}>Reported in GSTR-3B</th>
                  <th style={{ textAlign: "right" }}>Variance</th>
                  <th>Alignment Status</th>
                  <th>Audit Notes</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td style={{ fontWeight: 600 }}>Outward Tax Liability (Sales)</td>
                  <td style={{ textAlign: "right" }}>{formatCurrency(salesRegisterTax)}</td>
                  <td style={{ textAlign: "right" }}>{formatCurrency(gstr3b.output_tax)}</td>
                  <td
                    style={{
                      textAlign: "right",
                      fontFamily: "var(--font-mono)",
                      fontWeight: 700,
                      color: outputTaxDiff !== 0 ? "#dc2626" : "inherit",
                    }}
                  >
                    {formatCurrency(outputTaxDiff)}
                  </td>
                  <td>
                    {outputTaxDiff === 0 ? (
                      <span className="badge badge-match">
                        <CheckCircle2 size={12} /> RECONCILED
                      </span>
                    ) : (
                      <span className="badge badge-mismatch">
                        <AlertCircle size={12} /> VARIANCE DETECTED
                      </span>
                    )}
                  </td>
                  <td style={{ fontSize: 12, color: "var(--text-muted)" }}>
                    {outputTaxDiff === 0
                      ? "Full alignment between sales register and return"
                      : "Outward tax liability differs from sales register total"}
                  </td>
                </tr>
                <tr>
                  <td style={{ fontWeight: 600 }}>Input Tax Credit (Purchases)</td>
                  <td style={{ textAlign: "right" }}>{formatCurrency(purchaseRegisterItc)}</td>
                  <td style={{ textAlign: "right" }}>{formatCurrency(gstr3b.eligible_itc)}</td>
                  <td
                    style={{
                      textAlign: "right",
                      fontFamily: "var(--font-mono)",
                      fontWeight: 700,
                      color: itcDiff !== 0 ? "#dc2626" : "inherit",
                    }}
                  >
                    {formatCurrency(itcDiff)}
                  </td>
                  <td>
                    {itcDiff === 0 ? (
                      <span className="badge badge-match">
                        <CheckCircle2 size={12} /> RECONCILED
                      </span>
                    ) : (
                      <span className="badge badge-mismatch">
                        <AlertCircle size={12} /> VARIANCE DETECTED
                      </span>
                    )}
                  </td>
                  <td style={{ fontSize: 12, color: "var(--text-muted)" }}>
                    {itcDiff === 0
                      ? "Full alignment between purchase bills and ITC claimed"
                      : "Eligible ITC claimed differs from purchase register total"}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
