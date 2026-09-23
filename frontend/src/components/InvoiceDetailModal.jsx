import { X, Calendar, Building, FileSpreadsheet, Info } from "lucide-react";
import { StatusBadge } from "./StatusBadge";

export function InvoiceDetailModal({ invoice, onClose }) {
  if (!invoice) return null;

  const isMissing = invoice.status === "MISSING_IN_GST";
  const isExtra = invoice.status === "EXTRA_IN_GST";

  const expTv = invoice.expected_taxable_value ?? (isMissing ? invoice.taxable_value : null);
  const actTv = invoice.actual_taxable_value ?? (isExtra ? invoice.taxable_value : null);
  const tvDiff = invoice.taxable_value_diff;

  const expGst = invoice.expected_gst_amount ?? (isMissing ? invoice.gst_amount : null);
  const actGst = invoice.actual_gst_amount ?? (isExtra ? invoice.gst_amount : null);
  const gstDiff = invoice.gst_amount_diff;

  const formatCurrency = (val) => {
    if (val === null || val === undefined) return "—";
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR",
      maximumFractionDigits: 2,
    }).format(val);
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content animate-fade-in" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <h3 className="modal-title">Invoice Inspection</h3>
            <p className="card-subtitle">Invoice #{invoice.invoice_no}</p>
          </div>
          <button className="topbar-btn" onClick={onClose}>
            <X size={16} />
          </button>
        </div>

        <div className="modal-body">
          {/* Header Metadata */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
            <StatusBadge status={invoice.status} />
            {invoice.source && (
              <span style={{ fontSize: 12, color: "var(--text-muted)", display: "flex", alignItems: "center", gap: 4 }}>
                <FileSpreadsheet size={13} />
                Source: <strong>{invoice.source}</strong>
              </span>
            )}
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 20 }}>
            <div style={{ padding: "10px 14px", backgroundColor: "var(--slate-50)", borderRadius: "var(--radius-sm)", border: "1px solid var(--border-color)" }}>
              <div style={{ fontSize: 11, color: "var(--text-muted)", display: "flex", alignItems: "center", gap: 4, marginBottom: 2 }}>
                <Calendar size={12} /> Invoice Date
              </div>
              <div style={{ fontWeight: 600 }}>{invoice.invoice_date || "—"}</div>
            </div>

            <div style={{ padding: "10px 14px", backgroundColor: "var(--slate-50)", borderRadius: "var(--radius-sm)", border: "1px solid var(--border-color)" }}>
              <div style={{ fontSize: 11, color: "var(--text-muted)", display: "flex", alignItems: "center", gap: 4, marginBottom: 2 }}>
                <Building size={12} /> Counterparty GSTIN
              </div>
              <div style={{ fontWeight: 600, fontFamily: "var(--font-mono)", fontSize: 12 }}>
                {invoice.gstin || "—"}
              </div>
            </div>
          </div>

          {/* Comparison Cards for Mismatches / Values */}
          <div>
            <h4 style={{ fontSize: 12.5, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 8 }}>
              Value Comparison (Internal Books vs GST Portal)
            </h4>

            {/* Taxable Value Comparison */}
            <div className="comparison-grid">
              <div className="comp-col">
                <h4>Expected (Books)</h4>
                <div className="val">{formatCurrency(expTv)}</div>
              </div>
              <div className="comp-col">
                <h4>Actual (GST Portal)</h4>
                <div className="val">{formatCurrency(actTv)}</div>
              </div>
              <div className="comp-col">
                <h4>Difference</h4>
                <div className={`val ${tvDiff && tvDiff !== 0 ? "diff" : ""}`}>
                  {formatCurrency(tvDiff)}
                </div>
              </div>
            </div>

            {/* GST Amount Comparison */}
            <div className="comparison-grid" style={{ marginTop: 8 }}>
              <div className="comp-col">
                <h4>Expected GST</h4>
                <div className="val">{formatCurrency(expGst)}</div>
              </div>
              <div className="comp-col">
                <h4>Actual GST Portal</h4>
                <div className="val">{formatCurrency(actGst)}</div>
              </div>
              <div className="comp-col">
                <h4>GST Difference</h4>
                <div className={`val ${gstDiff && gstDiff !== 0 ? "diff" : ""}`}>
                  {formatCurrency(gstDiff)}
                </div>
              </div>
            </div>
          </div>

          {/* Explanation Banner */}
          <div className="explanation-banner">
            <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
              <Info size={16} style={{ marginTop: 2, flexShrink: 0 }} />
              <div>
                <strong>Reconciliation Assessment:</strong>
                <p style={{ marginTop: 4 }}>
                  {invoice.explanation ||
                    (invoice.status === "MATCH"
                      ? "Invoice values match between the accounting register and the GST portal record."
                      : "Discrepancy detected between records. Please review invoice line items.")}
                </p>
              </div>
            </div>
          </div>
        </div>

        <div className="modal-footer">
          <button className="btn btn-secondary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
