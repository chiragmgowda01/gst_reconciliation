import { CheckCircle, AlertCircle } from "lucide-react";

export function Gstr3bPage({ gstr3b, sales = [], purchases = [] }) {
  if (!gstr3b) {
    return <div className="card">No GSTR-3B summary data available.</div>;
  }

  const formatCurrency = (val) => {
    if (val === null || val === undefined) return "—";
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR",
      maximumFractionDigits: 2,
    }).format(val);
  };

  // Compare against internal registers
  const salesRegisterTax = sales.reduce((acc, curr) => acc + (curr.gst_amount || 0), 0);
  const purchaseRegisterItc = purchases.reduce((acc, curr) => acc + (curr.gst_amount || 0), 0);

  const outputTaxDiff = Math.round((salesRegisterTax - gstr3b.output_tax) * 100) / 100;
  const itcDiff = Math.round((purchaseRegisterItc - gstr3b.eligible_itc) * 100) / 100;
  const netTaxPayable = Math.max(0, gstr3b.output_tax - gstr3b.net_itc);

  return (
    <div className="animate-fade-in">
      {/* Top Banner */}
      <div className="gstr3b-hero">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <h2>Monthly Return — Form GSTR-3B</h2>
            <p>Self-assessed summary return of outward supplies and input tax credit</p>
          </div>
          <div style={{ background: "rgba(255,255,255,0.2)", padding: "6px 14px", borderRadius: 8, fontWeight: 700 }}>
            Tax Period: {gstr3b.tax_period}
          </div>
        </div>

        <div className="gstr3b-grid">
          <div className="gstr3b-box">
            <div className="gstr3b-box-label">Table 3.1: Output Tax Liability</div>
            <div className="gstr3b-box-val">{formatCurrency(gstr3b.output_tax)}</div>
          </div>
          <div className="gstr3b-box">
            <div className="gstr3b-box-label">Table 4(A): Eligible ITC Available</div>
            <div className="gstr3b-box-val" style={{ color: "#86efac" }}>{formatCurrency(gstr3b.eligible_itc)}</div>
          </div>
          <div className="gstr3b-box">
            <div className="gstr3b-box-label">Table 4(B): ITC Reversed / Ineligible</div>
            <div className="gstr3b-box-val" style={{ color: "#fca5a5" }}>{formatCurrency(gstr3b.itc_reversed)}</div>
          </div>
          <div className="gstr3b-box">
            <div className="gstr3b-box-label">Table 4(C): Net ITC Credited</div>
            <div className="gstr3b-box-val" style={{ color: "#93c5fd" }}>{formatCurrency(gstr3b.net_itc)}</div>
          </div>
          <div className="gstr3b-box" style={{ background: "rgba(234, 179, 8, 0.2)", borderColor: "#eab308" }}>
            <div className="gstr3b-box-label" style={{ color: "#fef08a" }}>Table 6.1: Net Tax Payable (Cash)</div>
            <div className="gstr3b-box-val" style={{ color: "#fef08a" }}>{formatCurrency(netTaxPayable)}</div>
          </div>
        </div>
      </div>

      {/* Internal Register vs GSTR-3B Reconciliation */}
      <div className="card">
        <div className="card-header">
          <div>
            <h3 className="card-title">GSTR-3B vs Register Reconciliation</h3>
            <p className="card-subtitle">
              Comparison between self-declared return figures and transaction-level accounting registers
            </p>
          </div>
        </div>

        <div className="table-wrapper">
          <table className="data-table">
            <thead>
              <tr>
                <th>Component</th>
                <th style={{ textAlign: "right" }}>Internal Registers</th>
                <th style={{ textAlign: "right" }}>Reported in GSTR-3B</th>
                <th style={{ textAlign: "right" }}>Difference</th>
                <th>Status</th>
                <th>Notes</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td style={{ fontWeight: 600 }}>Outward Tax Liability (Sales)</td>
                <td style={{ textAlign: "right" }}>{formatCurrency(salesRegisterTax)}</td>
                <td style={{ textAlign: "right" }}>{formatCurrency(gstr3b.output_tax)}</td>
                <td style={{ textAlign: "right", fontFamily: "var(--font-mono)", color: outputTaxDiff !== 0 ? "#e11d48" : "inherit" }}>
                  {formatCurrency(outputTaxDiff)}
                </td>
                <td>
                  {outputTaxDiff === 0 ? (
                    <span className="badge badge-match"><CheckCircle size={12} /> ALIGNED</span>
                  ) : (
                    <span className="badge badge-mismatch"><AlertCircle size={12} /> VARIANCE</span>
                  )}
                </td>
                <td style={{ fontSize: 12, color: "var(--text-muted)" }}>
                  {outputTaxDiff === 0
                    ? "Full alignment with recorded sales invoices"
                    : "Review unfiled sales or manual return adjustment"}
                </td>
              </tr>
              <tr>
                <td style={{ fontWeight: 600 }}>Input Tax Credit (Purchases)</td>
                <td style={{ textAlign: "right" }}>{formatCurrency(purchaseRegisterItc)}</td>
                <td style={{ textAlign: "right" }}>{formatCurrency(gstr3b.eligible_itc)}</td>
                <td style={{ textAlign: "right", fontFamily: "var(--font-mono)", color: itcDiff !== 0 ? "#e11d48" : "inherit" }}>
                  {formatCurrency(itcDiff)}
                </td>
                <td>
                  {itcDiff === 0 ? (
                    <span className="badge badge-match"><CheckCircle size={12} /> ALIGNED</span>
                  ) : (
                    <span className="badge badge-mismatch"><AlertCircle size={12} /> VARIANCE</span>
                  )}
                </td>
                <td style={{ fontSize: 12, color: "var(--text-muted)" }}>
                  {itcDiff === 0
                    ? "Full alignment with recorded purchase bills"
                    : "Verify invoices missing in GSTR-2A before claiming credit"}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
