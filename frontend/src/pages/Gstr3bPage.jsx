import { useState, useEffect } from "react";
import {
  CheckCircle2,
  AlertCircle,
  AlertTriangle,
  FileText,
  Calendar,
  Building,
  Info,
  RefreshCw,
} from "lucide-react";
import { api } from "../api/client";
import { LoadingSkeleton } from "../components/LoadingSkeleton";

const severityColor = {
  HIGH: { bg: "#fef2f2", border: "#fca5a5", icon: "#dc2626", text: "#991b1b" },
  MEDIUM: { bg: "#fffbeb", border: "#fcd34d", icon: "#d97706", text: "#92400e" },
  INFO: { bg: "#eff6ff", border: "#93c5fd", icon: "#2563eb", text: "#1e40af" },
};

const SeverityIcon = ({ sev }) => {
  if (sev === "HIGH") return <AlertTriangle size={14} color={severityColor.HIGH.icon} />;
  if (sev === "MEDIUM") return <AlertCircle size={14} color={severityColor.MEDIUM.icon} />;
  return <Info size={14} color={severityColor.INFO.icon} />;
};

export function Gstr3bPage({ gstr3b, sales = [], purchases = [] }) {
  const [crossForm, setCrossForm] = useState(null);
  const [cfLoading, setCfLoading] = useState(true);
  const [cfError, setCfError] = useState("");

  useEffect(() => {
    let ignore = false;

    async function fetchCrossForm() {
      try {
        const data = await api.getGstr3bCrossForm();
        if (!ignore) {
          setCrossForm(data);
          setCfLoading(false);
        }
      } catch (err) {
        if (!ignore) {
          setCfError(err.message || "Failed to load cross-form analysis.");
          setCfLoading(false);
        }
      }
    }

    fetchCrossForm();
    return () => {
      ignore = true;
    };
  }, [gstr3b]);

  const formatCurrency = (val) => {
    if (val === null || val === undefined) return "—";
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR",
      maximumFractionDigits: 2,
    }).format(val);
  };

  const formatDiff = (val) => {
    if (val === null || val === undefined) return "—";
    const abs = Math.abs(val);
    const prefix = val > 0 ? "+" : val < 0 ? "−" : "";
    return (
      <span style={{ color: val === 0 ? "#10b981" : "#dc2626", fontWeight: 700 }}>
        {prefix}
        {new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(abs)}
      </span>
    );
  };

  // Fallback to props-based calculation if cross-form not yet loaded
  const salesRegisterTax = sales.reduce((acc, curr) => acc + (curr.gst_amount || 0), 0);
  const purchaseRegisterItc = purchases.reduce((acc, curr) => acc + (curr.gst_amount || 0), 0);

  const gstr3bData = gstr3b || crossForm?.gstr3b_summary;

  if (!gstr3bData && !cfLoading) {
    return (
      <div className="card">
        <div className="empty-state">
          <FileText size={36} className="empty-icon" />
          <p>No GSTR-3B summary data available for this business account.</p>
          <p style={{ fontSize: 12.5, color: "var(--text-muted)", marginTop: 4 }}>
            Upload GSTR-3B data or contact support.
          </p>
        </div>
      </div>
    );
  }

  const outputTax = gstr3bData?.output_tax ?? 0;
  const eligibleItc = gstr3bData?.eligible_itc ?? 0;
  const itcReversed = gstr3bData?.itc_reversed ?? 0;
  const netItc = gstr3bData?.net_itc ?? 0;
  const netTaxPayable = Math.max(0, outputTax - netItc);
  const taxPeriod = gstr3b?.tax_period || crossForm?.tax_period || "2026-07";

  return (
    <div className="animate-fade-in">
      {/* 1. Header */}
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
            <span>Tax Period: <strong>{taxPeriod}</strong></span>
          </div>
          {gstr3b?.business_id && (
            <div className="period-badge">
              <Building size={13} />
              <span>Business ID: <strong>{gstr3b.business_id}</strong></span>
            </div>
          )}
        </div>
      </div>

      {/* 2. Prominent Financial Statement Cards */}
      {gstr3bData && (
        <div className="gstr3b-statement-card">
          <div className="statement-header">
            <div>
              <span className="statement-tag">Statutory Summary</span>
              <h3 className="statement-title">Tax Return Liabilities & Credit Schedule</h3>
              <p className="statement-subtitle">Values declared in Form GSTR-3B for tax period {taxPeriod}</p>
            </div>
          </div>
          <div className="statement-grid">
            <div className="statement-box">
              <span className="box-label">Table 3.1: Output Tax Liability</span>
              <span className="box-val">{formatCurrency(outputTax)}</span>
              <span className="box-sub">Payable on outward taxable supplies</span>
            </div>
            <div className="statement-box highlight-green">
              <span className="box-label">Table 4(A): Eligible ITC Available</span>
              <span className="box-val text-green">{formatCurrency(eligibleItc)}</span>
              <span className="box-sub">Credit from inward taxable supplies</span>
            </div>
            <div className="statement-box highlight-red">
              <span className="box-label">Table 4(B): ITC Reversed / Ineligible</span>
              <span className="box-val text-red">{formatCurrency(itcReversed)}</span>
              <span className="box-sub">Ineligible / non-business reversals</span>
            </div>
            <div className="statement-box highlight-primary">
              <span className="box-label">Table 4(C): Net ITC Credited</span>
              <span className="box-val text-saffron">{formatCurrency(netItc)}</span>
              <span className="box-sub">Available in Electronic Credit Ledger</span>
            </div>
            <div className="statement-box highlight-amber">
              <span className="box-label">Table 6.1: Net Tax Payable (Cash)</span>
              <span className="box-val text-amber">{formatCurrency(netTaxPayable)}</span>
              <span className="box-sub">Tax payable after ITC utilization</span>
            </div>
          </div>
        </div>
      )}

      {/* 3. Cross-Form Analysis from backend */}
      <div className="institutional-card" style={{ marginTop: 20 }}>
        <div className="card-header">
          <div>
            <h3 className="card-title">Cross-Form Reconciliation Analysis</h3>
            <p className="card-subtitle">
              Comparison between GSTR-1, GSTR-2A, and GSTR-3B summary figures
            </p>
          </div>
          {cfLoading && <RefreshCw size={16} className="spinning" />}
        </div>

        {cfLoading ? (
          <LoadingSkeleton />
        ) : cfError ? (
          <div className="empty-state" style={{ padding: 20 }}>
            <AlertCircle size={22} color="#dc2626" />
            <p style={{ color: "#dc2626", marginTop: 8 }}>{cfError}</p>
          </div>
        ) : crossForm ? (
          <>
            {/* Register Sums vs GSTR-3B */}
            {crossForm.register_data_available && (
              <div className="table-wrapper" style={{ marginBottom: 16 }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Return Component</th>
                      <th style={{ textAlign: "right" }}>Sales Register</th>
                      <th style={{ textAlign: "right" }}>GSTR-1 Filed</th>
                      <th style={{ textAlign: "right" }}>GSTR-3B Declared</th>
                      <th style={{ textAlign: "right" }}>Register ↔ GSTR-3B</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td style={{ fontWeight: 600 }}>Output Tax (GST Amount)</td>
                      <td style={{ textAlign: "right" }}>{formatCurrency(crossForm.register_sums?.sales_register_gst)}</td>
                      <td style={{ textAlign: "right" }}>{formatCurrency(crossForm.register_sums?.gstr1_gst)}</td>
                      <td style={{ textAlign: "right" }}>{formatCurrency(crossForm.gstr3b_summary?.output_tax)}</td>
                      <td style={{ textAlign: "right" }}>
                        {formatDiff(crossForm.cross_form_differences?.gstr1_vs_gstr3b_output_tax)}
                      </td>
                    </tr>
                    <tr>
                      <td style={{ fontWeight: 600 }}>Input Tax Credit (ITC)</td>
                      <td style={{ textAlign: "right" }}>{formatCurrency(crossForm.register_sums?.purchase_register_gst)}</td>
                      <td style={{ textAlign: "right" }}>{formatCurrency(crossForm.register_sums?.gstr2a_gst)}</td>
                      <td style={{ textAlign: "right" }}>{formatCurrency(crossForm.gstr3b_summary?.eligible_itc)}</td>
                      <td style={{ textAlign: "right" }}>
                        {formatDiff(crossForm.cross_form_differences?.gstr2a_vs_gstr3b_itc)}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            )}

            {/* Findings List */}
            {crossForm.findings && crossForm.findings.length > 0 && (
              <div style={{ padding: "0 4px" }}>
                <p style={{ fontWeight: 600, fontSize: 13, marginBottom: 12, color: "var(--text-main)" }}>
                  Investigation Findings ({crossForm.findings.filter(f => f.severity !== "INFO").length} requiring review):
                </p>
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  {crossForm.findings.map((f) => {
                    const colors = severityColor[f.severity] || severityColor.INFO;
                    return (
                      <div
                        key={f.finding_id}
                        style={{
                          background: colors.bg,
                          border: `1px solid ${colors.border}`,
                          borderRadius: 8,
                          padding: "12px 16px",
                        }}
                      >
                        <div style={{ display: "flex", gap: 8, alignItems: "flex-start", marginBottom: 6 }}>
                          <SeverityIcon sev={f.severity} />
                          <span
                            style={{
                              fontSize: 12.5,
                              fontWeight: 600,
                              color: colors.text,
                              lineHeight: 1.4,
                            }}
                          >
                            {f.description}
                          </span>
                        </div>
                        {f.difference !== undefined && f.severity !== "INFO" && (
                          <div style={{ fontSize: 12, marginBottom: 4 }}>
                            <strong>Difference:</strong>{" "}
                            {formatDiff(f.difference)}
                            {f.register_value !== undefined && (
                              <span style={{ color: "var(--text-muted)", marginLeft: 8 }}>
                                (Register: {formatCurrency(f.register_value)} / Portal: {formatCurrency(f.gst_portal_value)})
                              </span>
                            )}
                          </div>
                        )}
                        {f.possible_causes && f.possible_causes.length > 0 && (
                          <div style={{ fontSize: 11.5, color: "var(--text-muted)", marginBottom: 4 }}>
                            <strong>Possible causes:</strong>{" "}
                            {f.possible_causes.join(" • ")}
                          </div>
                        )}
                        <div
                          style={{
                            fontSize: 12,
                            color: colors.text,
                            borderTop: `1px solid ${colors.border}`,
                            paddingTop: 6,
                            marginTop: 6,
                          }}
                        >
                          <strong>Recommended action:</strong> {f.recommendation}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Disclaimer */}
            {crossForm.note && (
              <div
                style={{
                  marginTop: 16,
                  padding: "10px 14px",
                  background: "#f8fafc",
                  borderRadius: 6,
                  fontSize: 11.5,
                  color: "var(--text-muted)",
                  borderLeft: "3px solid #94a3b8",
                }}
              >
                <Info size={12} style={{ display: "inline", marginRight: 6 }} />
                {crossForm.note}
              </div>
            )}
          </>
        ) : (
          <div className="empty-state">
            <p>No cross-form analysis data available.</p>
          </div>
        )}
      </div>

      {/* 4. Register vs GSTR-3B Quick Table (using passed props as fallback) */}
      {!crossForm?.register_data_available && (sales.length > 0 || purchases.length > 0) && gstr3bData && (
        <div className="institutional-card" style={{ marginTop: 20 }}>
          <div className="card-header">
            <div>
              <h3 className="card-title">Accounting Register vs Return Comparison</h3>
              <p className="card-subtitle">
                Verification of self-declared GSTR-3B totals against transaction-level invoices in database
              </p>
            </div>
            <span className="badge badge-medium">{sales.length + purchases.length} Registered Invoices</span>
          </div>

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
                  <td style={{ textAlign: "right" }}>{formatCurrency(outputTax)}</td>
                  <td style={{ textAlign: "right" }}>{formatDiff(Math.round((salesRegisterTax - outputTax) * 100) / 100)}</td>
                  <td>
                    {Math.abs(salesRegisterTax - outputTax) < 0.01 ? (
                      <span className="badge badge-match"><CheckCircle2 size={12} /> RECONCILED</span>
                    ) : (
                      <span className="badge badge-mismatch"><AlertCircle size={12} /> VARIANCE DETECTED</span>
                    )}
                  </td>
                  <td style={{ fontSize: 12, color: "var(--text-muted)" }}>
                    {Math.abs(salesRegisterTax - outputTax) < 0.01
                      ? "Full alignment between sales register and return"
                      : "Outward tax liability differs from sales register total"}
                  </td>
                </tr>
                <tr>
                  <td style={{ fontWeight: 600 }}>Input Tax Credit (Purchases)</td>
                  <td style={{ textAlign: "right" }}>{formatCurrency(purchaseRegisterItc)}</td>
                  <td style={{ textAlign: "right" }}>{formatCurrency(eligibleItc)}</td>
                  <td style={{ textAlign: "right" }}>{formatDiff(Math.round((purchaseRegisterItc - eligibleItc) * 100) / 100)}</td>
                  <td>
                    {Math.abs(purchaseRegisterItc - eligibleItc) < 0.01 ? (
                      <span className="badge badge-match"><CheckCircle2 size={12} /> RECONCILED</span>
                    ) : (
                      <span className="badge badge-mismatch"><AlertCircle size={12} /> VARIANCE DETECTED</span>
                    )}
                  </td>
                  <td style={{ fontSize: 12, color: "var(--text-muted)" }}>
                    {Math.abs(purchaseRegisterItc - eligibleItc) < 0.01
                      ? "Full alignment between purchase bills and ITC claimed"
                      : "Eligible ITC claimed differs from purchase register total"}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
