import { useState, useEffect, useCallback, useMemo } from "react";
import {
  Server,
  ShieldAlert,
  ShieldCheck,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  RotateCw,
  Search,
  FileText,
  Receipt,
  ArrowUpRight,
  ArrowDownLeft,
  Calendar,
  Layers,
  Info,
  Filter,
  UploadCloud,
  X,
  ExternalLink,
} from "lucide-react";
import { api } from "../api/client";
import { LoadingSkeleton } from "../components/LoadingSkeleton";

const formatINR = (val) => {
  if (val === null || val === undefined || isNaN(val)) return "₹0.00";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format(Number(val));
};

const GSTR3B_SUMMARY_FIELDS = [
  ["output_tax", "Output tax liability"],
  ["eligible_itc", "Eligible ITC"],
  ["itc_reversed", "ITC reversed"],
  ["net_itc", "Net ITC"],
];

function Gstr3bImportPreview({ previewData, onCancel, onConfirm, confirmLoading }) {
  if (previewData.status === "no_data") {
    return (
      <div>
        <div className="empty-state" style={{ padding: 24 }}>
          <Receipt size={30} className="empty-icon" />
          <h3>No fixture data for this period</h3>
          <p>{previewData.message}</p>
        </div>
        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <button type="button" className="btn btn-secondary" onClick={onCancel}>Close</button>
        </div>
      </div>
    );
  }

  const operationLabels = {
    new_import: "New summary will be imported",
    duplicate: "Saved summary already matches",
    revision: "Saved summary will be revised",
  };
  const canConfirm = previewData.operation === "new_import" || previewData.operation === "revision";

  return (
    <div>
      <div
        role="alert"
        style={{
          display: "flex",
          gap: 8,
          alignItems: "flex-start",
          padding: "10px 12px",
          marginBottom: 14,
          border: "1px solid #fcd34d",
          borderRadius: 6,
          background: "#fffbeb",
          color: "#92400e",
          fontSize: 12,
          lineHeight: 1.5,
        }}
      >
        <ShieldAlert size={15} style={{ flexShrink: 0, marginTop: 1 }} />
        <span>
          Synthetic demonstration figures from <code>gstr3b.csv</code>. They do not represent an actual filed GST return. Confirm only if you want these values saved for this business.
        </span>
      </div>

      <div style={{ marginBottom: 12, fontSize: 13 }}>
        <strong>{operationLabels[previewData.operation] || "Review summary"}</strong>
        <div style={{ color: "var(--text-muted)", marginTop: 4 }}>
          Business: <strong>{previewData.business_name}</strong> · Tax period: <strong>{previewData.tax_period}</strong>
        </div>
        <div style={{ color: "var(--text-muted)", marginTop: 4 }}>{previewData.message}</div>
      </div>

      <div className="table-wrapper" style={{ marginBottom: 16 }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>Summary amount</th>
              <th style={{ textAlign: "right" }}>Synthetic fixture</th>
              <th style={{ textAlign: "right" }}>Saved value</th>
              <th style={{ textAlign: "right" }}>Change</th>
            </tr>
          </thead>
          <tbody>
            {GSTR3B_SUMMARY_FIELDS.map(([field, label]) => {
              const fixtureValue = previewData.fixture_summary[field];
              const existingValue = previewData.existing_summary?.[field];
              const difference = previewData.differences?.[field];
              return (
                <tr key={field}>
                  <td>{label}</td>
                  <td style={{ textAlign: "right" }}>{formatINR(fixtureValue)}</td>
                  <td style={{ textAlign: "right" }}>
                    {existingValue === undefined ? "No saved value" : formatINR(existingValue)}
                  </td>
                  <td style={{ textAlign: "right" }}>
                    {difference === undefined ? "—" : `${difference > 0 ? "+" : ""}${formatINR(difference)}`}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, flexWrap: "wrap" }}>
        <button type="button" className="btn btn-secondary" onClick={onCancel} disabled={confirmLoading}>
          Cancel
        </button>
        <button
          type="button"
          className="btn btn-primary"
          onClick={onConfirm}
          disabled={!canConfirm || confirmLoading}
        >
          {confirmLoading ? "Saving..." : previewData.operation === "revision" ? "Confirm Revision" : "Confirm & Import"}
        </button>
      </div>
    </div>
  );
}

export function GstApiPage({ activeBusiness, onImportSuccess, onNavigate }) {
  // Status state
  const [statusData, setStatusData] = useState(null);
  const [statusLoading, setStatusLoading] = useState(true);
  const [statusError, setStatusError] = useState("");

  // GSTIN verification state
  const [verifyInput, setVerifyInput] = useState("29ABCDE1234F1Z5");
  const [verifyLoading, setVerifyLoading] = useState(false);
  const [verifyResult, setVerifyResult] = useState(null);
  const [verifyError, setVerifyError] = useState("");

  // Return data query state
  const [selectedReturn, setSelectedReturn] = useState("gstr1"); // gstr1, gstr2a, gstr2b, gstr3b
  const [taxPeriod, setTaxPeriod] = useState("2026-07");
  const [counterpartyGstin, setCounterpartyGstin] = useState("");
  const [tableSearch, setTableSearch] = useState("");

  // Return data result state
  const [returnData, setReturnData] = useState(null);
  const [returnLoading, setReturnLoading] = useState(false);
  const [returnError, setReturnError] = useState("");

  // Import workflow state
  const [showImportModal, setShowImportModal] = useState(false);
  const [previewData, setPreviewData] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState("");
  const [confirmLoading, setConfirmLoading] = useState(false);
  const [confirmResult, setConfirmResult] = useState(null);
  const [importBanner, setImportBanner] = useState(null);

  // 1. Fetch GST Adapter Status
  const loadStatus = useCallback(async () => {
    setStatusLoading(true);
    setStatusError("");
    try {
      const data = await api.getGstStatus();
      setStatusData(data);
    } catch (err) {
      setStatusError(err.message || "Failed to load GST API simulator status.");
    } finally {
      setStatusLoading(false);
    }
  }, []);

  useEffect(() => {
    let ignore = false;
    api.getGstStatus()
      .then((data) => {
        if (!ignore) {
          setStatusData(data);
          setStatusLoading(false);
        }
      })
      .catch((err) => {
        if (!ignore) {
          setStatusError(err.message || "Failed to load GST API simulator status.");
          setStatusLoading(false);
        }
      });
    return () => {
      ignore = true;
    };
  }, []);

  // 2. Handle GSTIN Verification
  const handleVerifyGstin = async (e) => {
    if (e) e.preventDefault();
    const g = (verifyInput || "").trim().toUpperCase();
    if (!g) {
      setVerifyError("Please enter a 15-character GSTIN.");
      return;
    }
    setVerifyLoading(true);
    setVerifyError("");
    setVerifyResult(null);

    try {
      const res = await api.verifyGstin(g);
      setVerifyResult(res);
    } catch (err) {
      setVerifyError(err.message || "GSTIN verification request failed.");
    } finally {
      setVerifyLoading(false);
    }
  };

  // 3. Fetch Selected Return Data (Manual Apply)
  const handleApplyQuery = useCallback(async () => {
    if (!taxPeriod || !taxPeriod.trim()) {
      setReturnError("Please specify a tax period in YYYY-MM format (e.g. 2026-07).");
      return;
    }
    setReturnLoading(true);
    setReturnError("");

    const period = taxPeriod.trim();
    const cp = counterpartyGstin.trim() || undefined;

    try {
      let res;
      if (selectedReturn === "gstr1") {
        res = await api.getGstr1({ tax_period: period, counterparty_gstin: cp });
      } else if (selectedReturn === "gstr2a") {
        res = await api.getGstr2a({ tax_period: period, counterparty_gstin: cp });
      } else if (selectedReturn === "gstr2b") {
        res = await api.getGstr2b({ tax_period: period, counterparty_gstin: cp });
      } else if (selectedReturn === "gstr3b") {
        res = await api.getGstr3b(period);
      }
      setReturnData(res);
    } catch (err) {
      setReturnError(err.message || `Failed to fetch ${selectedReturn.toUpperCase()} data.`);
    } finally {
      setReturnLoading(false);
    }
  }, [selectedReturn, taxPeriod, counterpartyGstin]);

  // Effect to load return data when return type or period changes
  useEffect(() => {
    if (!taxPeriod || !taxPeriod.trim()) return;
    let ignore = false;
    const period = taxPeriod.trim();
    const cp = counterpartyGstin.trim() || undefined;

    const requestPromise =
      selectedReturn === "gstr1"
        ? api.getGstr1({ tax_period: period, counterparty_gstin: cp })
        : selectedReturn === "gstr2a"
        ? api.getGstr2a({ tax_period: period, counterparty_gstin: cp })
        : selectedReturn === "gstr2b"
        ? api.getGstr2b({ tax_period: period, counterparty_gstin: cp })
        : api.getGstr3b(period);

    requestPromise
      .then((res) => {
        if (!ignore) {
          setReturnData(res);
          setReturnLoading(false);
          setReturnError("");
        }
      })
      .catch((err) => {
        if (!ignore) {
          setReturnError(err.message || `Failed to fetch ${selectedReturn.toUpperCase()} data.`);
          setReturnLoading(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, [selectedReturn, taxPeriod, counterpartyGstin]);

  // 4. Open Import Preview Modal
  const handleOpenImportPreview = async () => {
    setShowImportModal(true);
    setPreviewLoading(true);
    setPreviewError("");
    setPreviewData(null);
    setConfirmResult(null);

    try {
      const res = selectedReturn === "gstr3b"
        ? await api.previewGstr3bImport(taxPeriod.trim())
        : await api.previewGstImport({
            return_type: selectedReturn,
            tax_period: taxPeriod.trim(),
            counterparty_gstin: counterpartyGstin.trim() || null,
          });
      setPreviewData(res);
    } catch (err) {
      setPreviewError(err.message || "Failed to generate import preview.");
    } finally {
      setPreviewLoading(false);
    }
  };

  // 5. Execute Confirmed Import
  const handleExecuteImport = async () => {
    if (confirmLoading) return;
    setConfirmLoading(true);
    setPreviewError("");

    try {
      const res = selectedReturn === "gstr3b"
        ? await api.confirmGstr3bImport(taxPeriod.trim())
        : await api.confirmGstImport({
            return_type: selectedReturn,
            tax_period: taxPeriod.trim(),
            counterparty_gstin: counterpartyGstin.trim() || null,
          });
      setConfirmResult(res);
      if (res.status === "success" || res.status === "partial") {
        setImportBanner(res);
      } else {
        setImportBanner(null);
      }

      // Notify parent App to refresh dashboard & reconciliation calculations
      if (res.imported_count > 0 && onImportSuccess) {
        onImportSuccess();
      }
    } catch (err) {
      setPreviewError(err.message || "Failed to execute return import.");
    } finally {
      setConfirmLoading(false);
    }
  };

  // Filter table rows for invoice-level returns
  const filteredRecords = useMemo(() => {
    if (!returnData || !returnData.records || !Array.isArray(returnData.records)) {
      return [];
    }
    const q = tableSearch.toLowerCase().trim();
    if (!q) return returnData.records;
    return returnData.records.filter((r) => {
      const invNo = String(r.invoice_no || "").toLowerCase();
      const gstin = String(r.gstin || "").toLowerCase();
      const date = String(r.invoice_date || "").toLowerCase();
      return invNo.includes(q) || gstin.includes(q) || date.includes(q);
    });
  }, [returnData, tableSearch]);

  // Record totals for invoice-level returns
  const { totalTaxable, totalGst } = useMemo(() => {
    if (!returnData || !returnData.records || !Array.isArray(returnData.records)) {
      return { totalTaxable: 0, totalGst: 0 };
    }
    return returnData.records.reduce(
      (acc, r) => {
        acc.totalTaxable += Number(r.taxable_value || 0);
        acc.totalGst += Number(r.gst_amount || 0);
        return acc;
      },
      { totalTaxable: 0, totalGst: 0 }
    );
  }, [returnData]);

  return (
    <div className="gst-datacenter-page" style={{ padding: "4px 0" }}>
      {/* ─────────────────────────────────────────────────────────────
          PERMANENT DEMO MODE / SAFETY DISCLAIMER BANNER
          ───────────────────────────────────────────────────────────── */}
      <div
        className="card"
        style={{
          borderLeft: "4px solid var(--primary-blue)",
          backgroundColor: "#f8fafc",
          padding: "16px 20px",
          marginBottom: 20,
        }}
      >
        <div style={{ display: "flex", alignItems: "flex-start", gap: 14 }}>
          <div
            style={{
              padding: 8,
              borderRadius: 8,
              backgroundColor: "var(--primary-blue-light)",
              color: "var(--primary-blue)",
              display: "flex",
            }}
          >
            <Server size={20} />
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 4 }}>
              <h2 style={{ fontSize: 15, fontWeight: 700, color: "var(--text-main)", margin: 0 }}>
                GST Data Center
              </h2>
              <span
                className="badge"
                style={{
                  backgroundColor: "#f0fdf4",
                  color: "#15803d",
                  border: "1px solid #bbf7d0",
                  fontWeight: 600,
                  fontSize: 11,
                }}
              >
                Preview before import
              </span>
            </div>
            <p style={{ fontSize: 12.5, color: "var(--text-muted)", margin: 0, lineHeight: 1.5 }}>
              This simulator shows synthetic CSV data and does not connect to GSTN or a GSP.
              Browsing is read-only. Records are saved to the selected business only after you preview and confirm an import.
            </p>
          </div>
        </div>
      </div>

      {/* ─────────────────────────────────────────────────────────────
          SUCCESS BANNER AFTER IMPORT
          ───────────────────────────────────────────────────────────── */}
      {importBanner && (
        <div
          style={{
            padding: "14px 18px",
            borderRadius: "var(--radius-md)",
            backgroundColor: importBanner.status === "partial" ? "#fffbeb" : "#f0fdf4",
            border: importBanner.status === "partial" ? "1px solid #fde68a" : "1px solid #86efac",
            color: importBanner.status === "partial" ? "#92400e" : "#14532d",
            marginBottom: 20,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: 12,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            {importBanner.status === "partial" ? (
              <AlertTriangle size={18} color="#d97706" />
            ) : (
              <CheckCircle2 size={18} color="#16a34a" />
            )}
            <div style={{ fontSize: 13 }}>
              <strong>{importBanner.status === "partial" ? "Import Partially Completed:" : "Import Successful:"}</strong>{" "}
              {importBanner.message}
            </div>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            {selectedReturn === "gstr3b" ? (
              <button
                type="button"
                className="btn btn-primary btn-sm"
                onClick={() => onNavigate && onNavigate("gstr3b")}
              >
                <FileText size={13} />
                <span>Open GSTR-3B Summary</span>
              </button>
            ) : selectedReturn === "gstr1" ? (
              <button
                type="button"
                className="btn btn-primary btn-sm"
                onClick={() => onNavigate && onNavigate("sales")}
              >
                <ArrowUpRight size={13} />
                <span>Open Sales Reconciliation</span>
              </button>
            ) : (
              <button
                type="button"
                className="btn btn-primary btn-sm"
                onClick={() => onNavigate && onNavigate("purchase")}
              >
                <ArrowDownLeft size={13} />
                <span>Open Purchase Reconciliation</span>
              </button>
            )}
            {selectedReturn !== "gstr3b" && (
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => onNavigate && onNavigate("invoices")}
              >
                <FileText size={13} />
                <span>Invoice Master</span>
              </button>
            )}
            <button
              type="button"
              onClick={() => setImportBanner(null)}
              style={{ background: "none", border: "none", cursor: "pointer", color: "#14532d" }}
              title="Dismiss"
            >
              <X size={16} />
            </button>
          </div>
        </div>
      )}

      {/* ─────────────────────────────────────────────────────────────
          ROW 1: STATUS PANEL & GSTIN VERIFIER (2 COLUMNS)
          ───────────────────────────────────────────────────────────── */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 360px), 1fr))",
          gap: 20,
          marginBottom: 20,
        }}
      >
        {/* PANEL 1: GST SIMULATOR STATUS */}
        <div className="card" style={{ marginBottom: 0 }}>
          <div className="card-header" style={{ marginBottom: 14 }}>
            <div>
              <div className="card-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Server size={16} color="var(--primary-blue)" />
                GST Data Simulator
              </div>
            </div>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={loadStatus}
              disabled={statusLoading}
              title="Refresh status"
            >
              <RotateCw size={13} className={statusLoading ? "spin-icon" : ""} />
              <span>Refresh</span>
            </button>
          </div>

          {statusLoading ? (
            <div style={{ padding: "20px 0" }}>
              <LoadingSkeleton />
            </div>
          ) : statusError ? (
            <div
              style={{
                padding: "12px 14px",
                borderRadius: 8,
                backgroundColor: "var(--error-bg)",
                color: "var(--error-text)",
                fontSize: 12.5,
              }}
            >
              <AlertTriangle size={15} style={{ display: "inline", marginRight: 6, verticalAlign: "-2px" }} />
              {statusError}
            </div>
          ) : statusData ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, color: "#15803d", fontSize: 14 }}>
                <CheckCircle2 size={17} />
                <strong>Status: Available</strong>
              </div>
              <p style={{ margin: 0, fontSize: 13, color: "var(--text-main)" }}>
                Synthetic demonstration records are available.
              </p>
              <p style={{ margin: 0, fontSize: 13, color: "var(--text-muted)" }}>
                No live GST Portal connection is configured.
              </p>

              <details style={{ borderTop: "1px solid var(--border-subtle)", paddingTop: 10 }}>
                <summary style={{ cursor: "pointer", fontSize: 12, fontWeight: 600, color: "var(--text-muted)" }}>
                  Technical diagnostics
                </summary>
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 160px), 1fr))",
                    gap: 10,
                    marginTop: 10,
                    padding: "10px 12px",
                    borderRadius: "var(--radius-sm)",
                    backgroundColor: "var(--bg-subtle)",
                    fontSize: 12,
                  }}
                >
                  <div><span>Adapter class: </span><strong>{statusData.adapter_type || "Unknown"}</strong></div>
                  <div><span>Provider: </span><strong>{String(statusData.provider || "unknown").toUpperCase()}</strong></div>
                  <div><span>Data source: </span><strong>{statusData.data_source || "Unknown"}</strong></div>
                  <div><span>Integration: </span><strong>{statusData.live_integration_status || "Unknown"}</strong></div>
                  <div><span>Health: </span><strong>{statusData.healthcheck?.status || "Unknown"}</strong></div>
                  {activeBusiness && (
                    <div><span>Business: </span><strong>{activeBusiness.name}</strong></div>
                  )}
                </div>
                <div style={{ marginTop: 10 }}>
                  <span style={{ fontSize: 11.5, fontWeight: 700, color: "var(--text-muted)" }}>Available fixture files</span>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 6 }}>
                    {(statusData.available_fixtures || ["gstr1.csv", "gstr2a.csv", "gstr2b.csv", "gstr3b.csv"]).map((f) => (
                      <span key={f} style={{ fontFamily: "var(--font-mono)", fontSize: 11, padding: "3px 8px", border: "1px solid var(--border-color)", borderRadius: 4 }}>
                        <FileText size={11} style={{ marginRight: 4, verticalAlign: "-2px" }} />{f}
                      </span>
                    ))}
                  </div>
                </div>
              </details>
            </div>
          ) : null}
        </div>

        {/* PANEL 2: GSTIN SYNTACTIC VERIFIER */}
        <div className="card" style={{ marginBottom: 0 }}>
          <div className="card-header" style={{ marginBottom: 14 }}>
            <div>
              <div className="card-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <ShieldCheck size={16} color="var(--teal-accent)" />
                GSTIN Format Verifier
              </div>
              <div className="card-subtitle">Syntactic structure check & synthetic fixture lookup</div>
            </div>
          </div>

          <form onSubmit={handleVerifyGstin} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div style={{ display: "flex", gap: 8 }}>
              <div style={{ position: "relative", flex: 1 }}>
                <input
                  type="text"
                  maxLength={15}
                  value={verifyInput}
                  onChange={(e) => setVerifyInput(e.target.value.toUpperCase())}
                  placeholder="e.g. 29ABCDE1234F1Z5"
                  style={{
                    width: "100%",
                    padding: "9px 12px",
                    fontFamily: "var(--font-mono)",
                    fontSize: 13,
                    borderRadius: "var(--radius-sm)",
                    border: "1px solid var(--border-color)",
                    backgroundColor: "#fff",
                    textTransform: "uppercase",
                  }}
                />
                <span
                  style={{
                    position: "absolute",
                    right: 8,
                    top: "50%",
                    transform: "translateY(-50%)",
                    fontSize: 11,
                    color: verifyInput.length === 15 ? "var(--success)" : "var(--text-dim)",
                    fontFamily: "var(--font-mono)",
                  }}
                >
                  {verifyInput.length}/15
                </span>
              </div>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={verifyLoading}
                style={{ padding: "9px 16px" }}
              >
                {verifyLoading ? <RotateCw size={13} className="spin-icon" /> : <Search size={13} />}
                <span>Verify</span>
              </button>
            </div>

            {/* Quick sample chips */}
            <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
              <span style={{ fontSize: 11, color: "var(--text-muted)" }}>Presets:</span>
              {[
                { label: "Fixture GSTR-1", gstin: "29ABCDE1234F1Z5" },
                { label: "Fixture GSTR-2A", gstin: "29PQRST1234A1Z1" },
                { label: "Valid Non-Seed", gstin: "27BBBBB2222B2Z6" },
                { label: "Malformed", gstin: "BADGSTIN123" },
              ].map((p) => (
                <button
                  key={p.gstin}
                  type="button"
                  onClick={() => {
                    setVerifyInput(p.gstin);
                    setVerifyResult(null);
                    setVerifyError("");
                  }}
                  style={{
                    background: "none",
                    border: "1px solid var(--border-color)",
                    borderRadius: 4,
                    padding: "2px 7px",
                    fontSize: 11,
                    cursor: "pointer",
                    color: "var(--text-main)",
                    backgroundColor: "#f8fafc",
                  }}
                >
                  {p.label}
                </button>
              ))}
            </div>

            {verifyError && (
              <div
                style={{
                  padding: "10px 12px",
                  borderRadius: 6,
                  backgroundColor: "var(--error-bg)",
                  color: "var(--error-text)",
                  fontSize: 12,
                }}
              >
                <XCircle size={14} style={{ display: "inline", marginRight: 6, verticalAlign: "-2px" }} />
                {verifyError}
              </div>
            )}

            {verifyResult && (
              <div
                style={{
                  border: "1px solid var(--border-color)",
                  borderRadius: 8,
                  padding: 12,
                  backgroundColor: "#ffffff",
                  fontSize: 12,
                  display: "flex",
                  flexDirection: "column",
                  gap: 8,
                }}
              >
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <span style={{ color: "var(--text-muted)" }}>Format Syntax:</span>
                  {verifyResult.format_valid ? (
                    <span className="badge badge-match">
                      <CheckCircle2 size={12} /> Valid 15-char structure
                    </span>
                  ) : (
                    <span className="badge badge-mismatch">
                      <XCircle size={12} /> Invalid GSTIN Syntax
                    </span>
                  )}
                </div>

                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <span style={{ color: "var(--text-muted)" }}>Found in Seed Fixtures:</span>
                  {verifyResult.found_in_demo_fixtures ? (
                    <span style={{ color: "var(--success)", fontWeight: 600 }}>
                      Yes (
                      {verifyResult.fixture_files_containing_gstin &&
                        verifyResult.fixture_files_containing_gstin.join(", ")}
                      )
                    </span>
                  ) : (
                    <span style={{ color: "var(--text-dim)", fontWeight: 500 }}>No match in local CSVs</span>
                  )}
                </div>

                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <span style={{ color: "var(--text-muted)" }}>Official GSTN Registration:</span>
                  <span
                    style={{
                      color: "#b45309",
                      backgroundColor: "#fef3c7",
                      padding: "2px 6px",
                      borderRadius: 4,
                      fontWeight: 600,
                      fontSize: 11,
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 4,
                    }}
                  >
                    <AlertTriangle size={11} />
                    NOT VERIFIED (Demo Only)
                  </span>
                </div>

                <div
                  style={{
                    backgroundColor: "#f8fafc",
                    padding: "8px 10px",
                    borderRadius: 4,
                    color: "var(--text-muted)",
                    fontSize: 11,
                    lineHeight: 1.4,
                    border: "1px solid #e2e8f0",
                  }}
                >
                  <Info size={11} style={{ display: "inline", marginRight: 4, verticalAlign: "-1px" }} />
                  {verifyResult.disclaimer ||
                    "A valid format does not confirm real tax registration on the official GST portal."}
                </div>
              </div>
            )}
          </form>
        </div>
      </div>

      {/* ─────────────────────────────────────────────────────────────
          SECTION: RETURN DATA VIEWER (TABS + QUERY TOOLBAR)
          ───────────────────────────────────────────────────────────── */}
      <div className="card" style={{ marginBottom: 20 }}>
        {/* Navigation Tabs for Return Types */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: 12,
            borderBottom: "1px solid var(--border-color)",
            paddingBottom: 14,
            marginBottom: 16,
          }}
        >
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {[
              { id: "gstr1", label: "Form GSTR-1", desc: "Outward Supplies", icon: ArrowUpRight },
              { id: "gstr2a", label: "Form GSTR-2A", desc: "Dynamic ITC", icon: ArrowDownLeft },
              { id: "gstr2b", label: "Form GSTR-2B", desc: "Static ITC Cut-off", icon: Layers },
              { id: "gstr3b", label: "Form GSTR-3B", desc: "Monthly Summary", icon: Receipt },
            ].map((tab) => {
              const active = selectedReturn === tab.id;
              const IconComp = tab.icon;
              return (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setSelectedReturn(tab.id)}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    padding: "8px 14px",
                    borderRadius: "var(--radius-sm)",
                    border: active ? "1px solid var(--primary-blue)" : "1px solid var(--border-color)",
                    backgroundColor: active ? "var(--primary-blue)" : "#ffffff",
                    color: active ? "#ffffff" : "var(--text-main)",
                    fontWeight: 600,
                    fontSize: 13,
                    cursor: "pointer",
                    transition: "all 0.15s ease",
                  }}
                >
                  <IconComp size={15} />
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <span
              style={{
                fontSize: 11.5,
                color: "var(--text-muted)",
                backgroundColor: "var(--bg-subtle)",
                padding: "4px 8px",
                borderRadius: 4,
              }}
            >
              Source: <code>data/{selectedReturn}.csv</code>
            </span>
          </div>
        </div>

        {/* Query Controls: Tax Period & Counterparty GSTIN + Import Action */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            flexWrap: "wrap",
            marginBottom: 18,
            padding: "12px 14px",
            backgroundColor: "var(--bg-subtle)",
            borderRadius: "var(--radius-sm)",
          }}
        >
          {/* Tax Period Input */}
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <label
              htmlFor="gst-tax-period"
              style={{
                fontSize: 12.5,
                fontWeight: 600,
                color: "var(--text-main)",
                display: "flex",
                alignItems: "center",
                gap: 5,
              }}
            >
              <Calendar size={14} color="var(--primary-blue)" />
              Tax Period:
            </label>
            <input
              id="gst-tax-period"
              type="text"
              pattern="^\d{4}-(0[1-9]|1[0-2])$"
              placeholder="YYYY-MM"
              value={taxPeriod}
              onChange={(e) => setTaxPeriod(e.target.value.trim())}
              style={{
                width: 100,
                padding: "6px 10px",
                fontFamily: "var(--font-mono)",
                fontSize: 12.5,
                borderRadius: "var(--radius-sm)",
                border: "1px solid var(--border-color)",
                backgroundColor: "#fff",
              }}
            />
          </div>

          {/* Quick Period Presets */}
          <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
            {["2026-07", "2026-06", "2026-08"].map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => setTaxPeriod(p)}
                style={{
                  background: taxPeriod === p ? "var(--primary-blue-light)" : "#fff",
                  border:
                    taxPeriod === p ? "1px solid var(--primary-blue-border)" : "1px solid var(--border-color)",
                  color: taxPeriod === p ? "var(--primary-blue)" : "var(--text-main)",
                  fontSize: 11,
                  padding: "3px 7px",
                  borderRadius: 4,
                  cursor: "pointer",
                  fontFamily: "var(--font-mono)",
                  fontWeight: taxPeriod === p ? 700 : 500,
                }}
              >
                {p}
              </button>
            ))}
          </div>

          {/* Counterparty GSTIN Filter (for GSTR-1/2A/2B only) */}
          {selectedReturn !== "gstr3b" && (
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginLeft: "auto" }}>
              <label
                htmlFor="counterparty-filter"
                style={{
                  fontSize: 12.5,
                  fontWeight: 600,
                  color: "var(--text-main)",
                  display: "flex",
                  alignItems: "center",
                  gap: 5,
                }}
              >
                <Filter size={13} color="var(--teal-accent)" />
                {selectedReturn === "gstr1" ? "Customer GSTIN:" : "Supplier GSTIN:"}
              </label>
              <input
                id="counterparty-filter"
                type="text"
                placeholder="Optional filter"
                value={counterpartyGstin}
                onChange={(e) => setCounterpartyGstin(e.target.value.toUpperCase().trim())}
                style={{
                  width: 160,
                  padding: "6px 10px",
                  fontFamily: "var(--font-mono)",
                  fontSize: 12,
                  borderRadius: "var(--radius-sm)",
                  border: "1px solid var(--border-color)",
                  backgroundColor: "#fff",
                  textTransform: "uppercase",
                }}
              />
            </div>
          )}

          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={handleApplyQuery}
            disabled={returnLoading}
            style={{ padding: "6px 12px" }}
          >
            <RotateCw size={12} className={returnLoading ? "spin-icon" : ""} />
            <span>Apply</span>
          </button>

          {/* ─────────────────────────────────────────────────────────────
              IMPORT WORKFLOW BUTTON OR SUMMARY NOTE
              ───────────────────────────────────────────────────────────── */}
          {selectedReturn !== "gstr3b" ? (
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={handleOpenImportPreview}
              disabled={returnLoading || previewLoading || !returnData || returnData.record_count === 0}
              style={{
                marginLeft: selectedReturn === "gstr3b" ? "auto" : undefined,
                fontWeight: 600,
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
              }}
              title="Stage return records into business reconciliation ledger"
            >
              <UploadCloud size={13} />
              <span>Import to Reconciliation</span>
            </button>
          ) : (
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={handleOpenImportPreview}
              disabled={returnLoading || previewLoading}
              style={{ fontWeight: 600, display: "inline-flex", alignItems: "center", gap: 6 }}
              title="Preview and confirm saving this synthetic monthly summary to the business database"
            >
              <UploadCloud size={13} />
              <span>Preview GSTR-3B Import</span>
            </button>
          )}
        </div>

        {/* ─────────────────────────────────────────────────────────────
            RETURN DISPLAY: GSTR-3B MONTHLY SUMMARY OR INVOICE TABLES
            ───────────────────────────────────────────────────────────── */}
        {returnLoading ? (
          <div style={{ padding: "40px 0", textAlign: "center" }}>
            <LoadingSkeleton />
          </div>
        ) : returnError ? (
          <div
            style={{
              padding: "20px 24px",
              borderRadius: "var(--radius-md)",
              backgroundColor: "var(--error-bg)",
              color: "var(--error-text)",
              border: "1px solid var(--error-border)",
              marginBottom: 16,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
              <AlertTriangle size={18} />
              <strong style={{ fontSize: 14 }}>Return Query Error</strong>
            </div>
            <p style={{ margin: 0, fontSize: 13, lineHeight: 1.5 }}>{returnError}</p>
          </div>
        ) : selectedReturn === "gstr3b" ? (
          /* GSTR-3B SUMMARY VIEW */
          <div>
            {returnData?.summary?.found === true && (
              <div
                role="note"
                style={{
                  display: "flex",
                  gap: 8,
                  alignItems: "flex-start",
                  padding: "10px 12px",
                  marginBottom: 14,
                  border: "1px solid #fcd34d",
                  borderRadius: 6,
                  background: "#fffbeb",
                  color: "#92400e",
                  fontSize: 12,
                  lineHeight: 1.5,
                }}
              >
                <ShieldAlert size={15} style={{ flexShrink: 0, marginTop: 1 }} />
                <span>
                  Synthetic demonstration figures only. They do not represent an actual filed GST return. Use Preview GSTR-3B Import to review and explicitly save them to this business.
                </span>
              </div>
            )}
            {returnData?.summary?.found === false ? (
              <div
                style={{
                  padding: "36px 20px",
                  textAlign: "center",
                  backgroundColor: "#f8fafc",
                  borderRadius: "var(--radius-md)",
                  border: "1px dashed var(--border-color)",
                }}
              >
                <Receipt size={36} color="var(--text-dim)" style={{ marginBottom: 12 }} />
                  <h3 style={{ fontSize: 15, fontWeight: 700, color: "var(--text-main)", marginBottom: 6 }}>
                    No GSTR-3B Fixture for Period {taxPeriod}
                </h3>
                <p style={{ fontSize: 13, color: "var(--text-muted)", maxWidth: 480, margin: "0 auto" }}>
                  {returnData?.summary?.note ||
                    "Synthetic fixtures only contain GSTR-3B return summary for period 2026-07. No fallback period data is substituted."}
                </p>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => setTaxPeriod("2026-07")}
                  style={{ marginTop: 14 }}
                >
                  Switch to 2026-07
                </button>
              </div>
            ) : returnData?.summary ? (
              <div>
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))",
                    gap: 14,
                    marginBottom: 20,
                  }}
                >
                  <div className="kpi-card">
                    <span className="kpi-label">Output Tax Liability (1)</span>
                    <div className="kpi-value" style={{ color: "var(--error-text)" }}>
                      {formatINR(returnData.summary.output_tax)}
                    </div>
                    <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                      Table 3.1 Outward Taxable Supplies
                    </span>
                  </div>

                  <div className="kpi-card">
                    <span className="kpi-label">Eligible ITC (2)</span>
                    <div className="kpi-value" style={{ color: "var(--teal-accent)" }}>
                      {formatINR(returnData.summary.eligible_itc)}
                    </div>
                    <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                      Table 4(A) ITC Available from Inward
                    </span>
                  </div>

                  <div className="kpi-card">
                    <span className="kpi-label">Reversed ITC (3)</span>
                    <div className="kpi-value" style={{ color: "var(--warning)" }}>
                      {formatINR(returnData.summary.itc_reversed)}
                    </div>
                    <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                      Table 4(B) Ineligible / Reversal
                    </span>
                  </div>

                  <div className="kpi-card" style={{ borderLeft: "4px solid var(--primary-blue)" }}>
                    <span className="kpi-label">Net Eligible ITC (2 - 3)</span>
                    <div className="kpi-value" style={{ color: "var(--primary-blue)" }}>
                      {formatINR(returnData.summary.net_itc)}
                    </div>
                    <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                      Table 4(C) Net Input Credit Claimed
                    </span>
                  </div>
                </div>

                {/* Net Balance Breakdown Banner */}
                <div
                  style={{
                    padding: "14px 18px",
                    borderRadius: "var(--radius-sm)",
                    backgroundColor: "var(--primary-blue-light)",
                    border: "1px solid var(--primary-blue-border)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    flexWrap: "wrap",
                    gap: 12,
                    fontSize: 12.5,
                  }}
                >
                  <div>
                    <strong style={{ color: "var(--primary-blue)" }}>Statutory Balance Formula:</strong>{" "}
                    <span style={{ color: "var(--text-main)" }}>
                      Eligible ITC ({formatINR(returnData.summary.eligible_itc)}) − Reversed ITC (
                      {formatINR(returnData.summary.itc_reversed)}) = <strong>{formatINR(returnData.summary.net_itc)}</strong> Net ITC
                    </span>
                  </div>
                  <span
                    className="badge"
                    style={{
                      backgroundColor: "#fff",
                      color: "var(--primary-blue)",
                      border: "1px solid var(--primary-blue-border)",
                      fontWeight: 700,
                    }}
                  >
                    PERIOD {returnData.tax_period}
                  </span>
                </div>
              </div>
            ) : null}
          </div>
        ) : (
          /* INVOICE-LEVEL RETURNS (GSTR-1, GSTR-2A, GSTR-2B) */
          <div>
            {/* KPI Header Bar for this Return */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
                gap: 12,
                marginBottom: 16,
              }}
            >
              <div
                style={{
                  backgroundColor: "var(--bg-subtle)",
                  padding: "10px 14px",
                  borderRadius: "var(--radius-sm)",
                }}
              >
                <span style={{ fontSize: 11, color: "var(--text-muted)", display: "block" }}>
                  Total Invoices
                </span>
                <strong style={{ fontSize: 18, color: "var(--text-main)" }}>
                  {returnData?.record_count || 0}
                </strong>
              </div>
              <div
                style={{
                  backgroundColor: "var(--bg-subtle)",
                  padding: "10px 14px",
                  borderRadius: "var(--radius-sm)",
                }}
              >
                <span style={{ fontSize: 11, color: "var(--text-muted)", display: "block" }}>
                  Total Taxable Value
                </span>
                <strong style={{ fontSize: 16, color: "var(--text-main)" }}>
                  {formatINR(totalTaxable)}
                </strong>
              </div>
              <div
                style={{
                  backgroundColor: "var(--bg-subtle)",
                  padding: "10px 14px",
                  borderRadius: "var(--radius-sm)",
                }}
              >
                <span style={{ fontSize: 11, color: "var(--text-muted)", display: "block" }}>
                  Total GST Amount
                </span>
                <strong style={{ fontSize: 16, color: "var(--teal-accent)" }}>
                  {formatINR(totalGst)}
                </strong>
              </div>
              <div
                style={{
                  backgroundColor: "var(--bg-subtle)",
                  padding: "10px 14px",
                  borderRadius: "var(--radius-sm)",
                }}
              >
                <span style={{ fontSize: 11, color: "var(--text-muted)", display: "block" }}>
                  Simulated File
                </span>
                <strong style={{ fontSize: 13, fontFamily: "var(--font-mono)", color: "var(--primary-blue)" }}>
                  {returnData?.source_file || `${selectedReturn}.csv`}
                </strong>
              </div>
            </div>

            {/* In-table search filter */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
              <div style={{ position: "relative", width: 260 }}>
                <Search
                  size={14}
                  style={{
                    position: "absolute",
                    left: 10,
                    top: "50%",
                    transform: "translateY(-50%)",
                    color: "var(--text-dim)",
                  }}
                />
                <input
                  type="text"
                  placeholder="Search invoice or GSTIN..."
                  value={tableSearch}
                  onChange={(e) => setTableSearch(e.target.value)}
                  style={{
                    width: "100%",
                    padding: "7px 10px 7px 30px",
                    fontSize: 12,
                    borderRadius: "var(--radius-sm)",
                    border: "1px solid var(--border-color)",
                    backgroundColor: "#fff",
                  }}
                />
              </div>

              <span style={{ fontSize: 11.5, color: "var(--text-muted)" }}>
                Showing <strong>{filteredRecords.length}</strong> of {returnData?.record_count || 0} records
              </span>
            </div>

            {/* Table or Empty State */}
            {filteredRecords.length === 0 ? (
              <div
                style={{
                  padding: "36px 20px",
                  textAlign: "center",
                  backgroundColor: "#f8fafc",
                  borderRadius: "var(--radius-md)",
                  border: "1px dashed var(--border-color)",
                }}
              >
                <FileText size={32} color="var(--text-dim)" style={{ marginBottom: 10 }} />
                <h4 style={{ fontSize: 14, fontWeight: 700, color: "var(--text-main)", marginBottom: 4 }}>
                  No Records Found for Period {taxPeriod}
                </h4>
                <p style={{ fontSize: 12.5, color: "var(--text-muted)", margin: 0 }}>
                  {returnData?.record_count === 0
                    ? `No ${selectedReturn.toUpperCase()} invoices were found in synthetic fixtures for ${taxPeriod}.`
                    : "No records match your search filter."}
                </p>
                {taxPeriod !== "2026-07" && (
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => setTaxPeriod("2026-07")}
                    style={{ marginTop: 12 }}
                  >
                    View 2026-07 Fixtures
                  </button>
                )}
              </div>
            ) : (
              <div className="table-wrapper">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th style={{ width: 40 }}>#</th>
                      <th>Invoice No</th>
                      <th>Invoice Date</th>
                      <th>{selectedReturn === "gstr1" ? "Customer GSTIN" : "Supplier GSTIN"}</th>
                      <th style={{ textAlign: "right" }}>Taxable Value</th>
                      <th style={{ textAlign: "right" }}>GST Amount</th>
                      <th style={{ width: 100 }}>Source Tag</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredRecords.map((r, idx) => (
                      <tr key={`${r.invoice_no}-${idx}`}>
                        <td style={{ color: "var(--text-dim)", fontSize: 11 }}>{idx + 1}</td>
                        <td className="mono-cell" style={{ fontWeight: 600, color: "var(--text-main)" }}>
                          {r.invoice_no}
                        </td>
                        <td>{r.invoice_date}</td>
                        <td>
                          <span className="gstin-tag">{r.gstin}</span>
                        </td>
                        <td style={{ textAlign: "right", fontFamily: "var(--font-mono)", fontWeight: 500 }}>
                          {formatINR(r.taxable_value)}
                        </td>
                        <td
                          style={{
                            textAlign: "right",
                            fontFamily: "var(--font-mono)",
                            color: "var(--teal-accent)",
                            fontWeight: 600,
                          }}
                        >
                          {formatINR(r.gst_amount)}
                        </td>
                        <td>
                          <span
                            style={{
                              fontSize: 10.5,
                              fontFamily: "var(--font-mono)",
                              backgroundColor: "var(--bg-subtle)",
                              padding: "2px 6px",
                              borderRadius: 4,
                              color: "var(--text-muted)",
                            }}
                          >
                            {r.source || selectedReturn}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ─────────────────────────────────────────────────────────────
          IMPORT REVIEW & CONFIRMATION MODAL
          ───────────────────────────────────────────────────────────── */}
      {showImportModal && (
        <div
          className="modal-overlay"
          style={{
            position: "fixed",
            inset: 0,
            backgroundColor: "rgba(15, 23, 42, 0.65)",
            backdropFilter: "blur(4px)",
            zIndex: 1000,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: 16,
          }}
          onClick={(e) => {
            if (e.target === e.currentTarget && !confirmLoading) setShowImportModal(false);
          }}
        >
          <div
            className="modal-card"
            style={{
              backgroundColor: "#ffffff",
              borderRadius: "var(--radius-lg)",
              maxWidth: 680,
              width: "100%",
              maxHeight: "90vh",
              overflowY: "auto",
              boxShadow: "var(--shadow-lg)",
              border: "1px solid var(--border-color)",
              padding: 24,
            }}
          >
            {/* Modal Header */}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                borderBottom: "1px solid var(--border-color)",
                paddingBottom: 14,
                marginBottom: 16,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <div
                  style={{
                    width: 36,
                    height: 36,
                    borderRadius: 8,
                    backgroundColor: "var(--primary-blue-light)",
                    color: "var(--primary-blue)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  <UploadCloud size={20} />
                </div>
                <div>
                  <h3 style={{ fontSize: 16, fontWeight: 700, margin: 0, color: "var(--text-main)" }}>
                    {confirmResult
                      ? "Import result"
                      : selectedReturn === "gstr3b"
                        ? "Preview GSTR-3B Summary Import"
                        : `Import ${selectedReturn.toUpperCase()} to Reconciliation Ledger`}
                  </h3>
                  <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
                    Tax Period: <strong>{taxPeriod}</strong>
                    {selectedReturn === "gstr3b" ? " · Synthetic fixture" : <> • Target Source: <code>{selectedReturn}</code></>}
                  </span>
                </div>
              </div>
              {!confirmLoading && (
                <button
                  type="button"
                  onClick={() => setShowImportModal(false)}
                  style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)" }}
                >
                  <X size={18} />
                </button>
              )}
            </div>

            {/* Modal Body */}
            {previewLoading ? (
              <div style={{ textAlign: "center", padding: "40px 0" }}>
                <LoadingSkeleton />
                <p style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 12 }}>
                    {selectedReturn === "gstr3b"
                      ? "Checking the synthetic summary against the saved business period..."
                      : "Analyzing return records and checking duplicates in active ledger..."}
                </p>
              </div>
            ) : previewError ? (
              <div
                style={{
                  padding: "16px",
                  borderRadius: 8,
                  backgroundColor: "var(--error-bg)",
                  color: "var(--error-text)",
                  border: "1px solid var(--error-border)",
                  fontSize: 13,
                  marginBottom: 16,
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                  <AlertTriangle size={16} />
                  <strong>Import Error</strong>
                </div>
                {previewError}
              </div>
            ) : confirmResult ? (
              /* RESULT VIEW AFTER CONFIRMATION */
              <div>
                <div
                  style={{
                    backgroundColor: confirmResult.status === "success" ? "#f0fdf4" : "#fffbeb",
                    border: confirmResult.status === "success" ? "1px solid #86efac" : "1px solid #fde68a",
                    borderRadius: "var(--radius-md)",
                    padding: "20px",
                    textAlign: "center",
                    marginBottom: 20,
                  }}
                >
                  {confirmResult.status === "success" ? (
                    <CheckCircle2 size={36} color="#16a34a" style={{ marginBottom: 8 }} />
                  ) : (
                    <AlertTriangle size={36} color="#d97706" style={{ marginBottom: 8 }} />
                  )}
                  <h4
                    style={{
                      fontSize: 16,
                      fontWeight: 700,
                      color: confirmResult.status === "success" ? "#14532d" : "#92400e",
                      margin: "0 0 6px",
                    }}
                  >
                    {confirmResult.status === "success"
                      ? confirmResult.operation === "revision" ? "GSTR-3B summary revised" : "Import completed"
                      : confirmResult.status === "duplicate"
                        ? "No changes needed"
                        : confirmResult.status === "no_data"
                          ? "No records available"
                          : confirmResult.status === "failed"
                            ? "Import failed"
                            : confirmResult.status === "partial"
                              ? "Import partially completed"
                              : "Import result"}
                  </h4>
                  <p
                    style={{
                      fontSize: 13,
                      color: confirmResult.status === "success" ? "#166534" : "#92400e",
                      margin: 0,
                    }}
                  >
                    {confirmResult.message}
                  </p>
                </div>

                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(3, 1fr)",
                    gap: 10,
                    marginBottom: 20,
                    textAlign: "center",
                  }}
                >
                  <div style={{ backgroundColor: "#f8fafc", padding: 10, borderRadius: 6, border: "1px solid #e2e8f0" }}>
                    <span style={{ fontSize: 11, color: "var(--text-muted)", display: "block" }}>Imported</span>
                    <strong style={{ fontSize: 18, color: "var(--success)" }}>{confirmResult.imported_count ?? 0}</strong>
                  </div>
                  <div style={{ backgroundColor: "#f8fafc", padding: 10, borderRadius: 6, border: "1px solid #e2e8f0" }}>
                    <span style={{ fontSize: 11, color: "var(--text-muted)", display: "block" }}>Skipped Duplicates</span>
                    <strong style={{ fontSize: 18, color: "var(--warning)" }}>{confirmResult.duplicate_count ?? 0}</strong>
                  </div>
                  <div style={{ backgroundColor: "#f8fafc", padding: 10, borderRadius: 6, border: "1px solid #e2e8f0" }}>
                    <span style={{ fontSize: 11, color: "var(--text-muted)", display: "block" }}>Rejected</span>
                    <strong style={{ fontSize: 18, color: "var(--text-dim)" }}>{confirmResult.rejected_count ?? 0}</strong>
                  </div>
                </div>

                {/* Navigation Action Buttons */}
                <div style={{ display: "flex", gap: 10, justifyContent: "flex-end", flexWrap: "wrap" }}>
                  {selectedReturn === "gstr3b" ? (
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={() => {
                        setShowImportModal(false);
                        if (onNavigate) onNavigate("gstr3b");
                      }}
                    >
                      <FileText size={14} />
                      <span>Open GSTR-3B Summary</span>
                    </button>
                  ) : selectedReturn === "gstr1" ? (
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={() => {
                        setShowImportModal(false);
                        if (onNavigate) onNavigate("sales");
                      }}
                    >
                      <ArrowUpRight size={14} />
                      <span>View in Sales Reconciliation</span>
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={() => {
                        setShowImportModal(false);
                        if (onNavigate) onNavigate("purchase");
                      }}
                    >
                      <ArrowDownLeft size={14} />
                      <span>View in Purchase Reconciliation</span>
                    </button>
                  )}
                  {selectedReturn !== "gstr3b" && (
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={() => {
                        setShowImportModal(false);
                        if (onNavigate) onNavigate("invoices");
                      }}
                    >
                      <ExternalLink size={14} />
                      <span>View in Invoice Master</span>
                    </button>
                  )}
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => setShowImportModal(false)}
                  >
                    Close
                  </button>
                </div>
              </div>
            ) : selectedReturn === "gstr3b" && previewData ? (
              <Gstr3bImportPreview
                previewData={previewData}
                onCancel={() => setShowImportModal(false)}
                onConfirm={handleExecuteImport}
                confirmLoading={confirmLoading}
              />
            ) : previewData ? (
              /* PREVIEW BREAKDOWN & CONFIRMATION */
              <div>
                {/* Target Information Strip */}
                <div
                  style={{
                    backgroundColor: "var(--bg-subtle)",
                    padding: "10px 14px",
                    borderRadius: 6,
                    fontSize: 12,
                    marginBottom: 16,
                    display: "flex",
                    justifyContent: "space-between",
                    flexWrap: "wrap",
                    gap: 8,
                  }}
                >
                  <div>
                    <span style={{ color: "var(--text-muted)" }}>Target Business: </span>
                    <strong>{previewData.target_business_name}</strong> (<code>{previewData.target_business_gstin}</code>)
                  </div>
                  <div>
                    <span style={{ color: "var(--text-muted)" }}>Ledger Source Tag: </span>
                    <strong style={{ fontFamily: "var(--font-mono)", color: "var(--primary-blue)" }}>
                      {previewData.source}
                    </strong>
                  </div>
                </div>

                {/* Staging Metrics KPI Grid */}
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(4, 1fr)",
                    gap: 10,
                    marginBottom: 16,
                    textAlign: "center",
                  }}
                >
                  <div style={{ backgroundColor: "#f8fafc", padding: "10px 8px", borderRadius: 6, border: "1px solid #e2e8f0" }}>
                    <span style={{ fontSize: 11, color: "var(--text-muted)", display: "block" }}>Total Fetched</span>
                    <strong style={{ fontSize: 16, color: "var(--text-main)" }}>{previewData.total_records}</strong>
                  </div>
                  <div style={{ backgroundColor: "#f0fdf4", padding: "10px 8px", borderRadius: 6, border: "1px solid #bbf7d0" }}>
                    <span style={{ fontSize: 11, color: "#166534", display: "block" }}>Ready to Import</span>
                    <strong style={{ fontSize: 16, color: "var(--success)" }}>{previewData.ready_to_import}</strong>
                  </div>
                  <div style={{ backgroundColor: "#fffbeb", padding: "10px 8px", borderRadius: 6, border: "1px solid #fde68a" }}>
                    <span style={{ fontSize: 11, color: "#92400e", display: "block" }}>Duplicates (Skip)</span>
                    <strong style={{ fontSize: 16, color: "var(--warning)" }}>{previewData.duplicate_count}</strong>
                  </div>
                  <div style={{ backgroundColor: "#fef2f2", padding: "10px 8px", borderRadius: 6, border: "1px solid #fecaca" }}>
                    <span style={{ fontSize: 11, color: "#991b1b", display: "block" }}>Invalid/Rejected</span>
                    <strong style={{ fontSize: 16, color: "var(--error)" }}>{previewData.rejected_count}</strong>
                  </div>
                </div>

                {/* Safety & Synthetic Data Warning */}
                <div
                  style={{
                    backgroundColor: "#eff6ff",
                    border: "1px solid #bfdbfe",
                    borderRadius: 6,
                    padding: "10px 14px",
                    marginBottom: 16,
                    fontSize: 12,
                    color: "#1e40af",
                    lineHeight: 1.5,
                  }}
                >
                  <ShieldAlert size={14} style={{ display: "inline", marginRight: 6, verticalAlign: "-2px" }} />
                  <strong>DEMO ENVIRONMENT NOTICE:</strong> These records are sourced from synthetic CSV fixtures in{" "}
                  <code>data/{selectedReturn}.csv</code>. Upon confirmation, they will be inserted into the database
                  for your active business under source <code>{previewData.source}</code> so the reconciliation engine can
                  cross-match them. <strong>No real filings are submitted to the GST portal.</strong>
                </div>

                {/* Sample Records Table */}
                {previewData.preview_records && previewData.preview_records.length > 0 && (
                  <div style={{ marginBottom: 16 }}>
                    <div style={{ fontSize: 11.5, fontWeight: 700, color: "var(--text-muted)", marginBottom: 6 }}>
                      INVOICE STAGING PREVIEW (FIRST {previewData.preview_records.length} ROWS):
                    </div>
                    <div style={{ maxHeight: 180, overflowY: "auto", border: "1px solid var(--border-color)", borderRadius: 6 }}>
                      <table className="data-table" style={{ fontSize: 11.5 }}>
                        <thead>
                          <tr>
                            <th>Invoice No</th>
                            <th>Date</th>
                            <th>GSTIN</th>
                            <th style={{ textAlign: "right" }}>Taxable</th>
                            <th style={{ textAlign: "right" }}>GST</th>
                            <th>Action</th>
                          </tr>
                        </thead>
                        <tbody>
                          {previewData.preview_records.map((r, i) => (
                            <tr key={`${r.invoice_no}-${i}`}>
                              <td className="mono-cell" style={{ fontWeight: 600 }}>{r.invoice_no}</td>
                              <td>{r.invoice_date}</td>
                              <td><span className="gstin-tag" style={{ fontSize: 10 }}>{r.gstin}</span></td>
                              <td style={{ textAlign: "right", fontFamily: "var(--font-mono)" }}>
                                {formatINR(r.taxable_value)}
                              </td>
                              <td style={{ textAlign: "right", fontFamily: "var(--font-mono)", color: "var(--teal-accent)" }}>
                                {formatINR(r.gst_amount)}
                              </td>
                              <td>
                                {r.status === "duplicate" ? (
                                  <span style={{ fontSize: 10.5, color: "var(--warning)", fontWeight: 600 }}>
                                    Skip (Exists)
                                  </span>
                                ) : (
                                  <span style={{ fontSize: 10.5, color: "var(--success)", fontWeight: 600 }}>
                                    Import
                                  </span>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* Import behavior note */}
                <div style={{ fontSize: 11, color: "var(--text-dim)", marginBottom: 16 }}>
                  * Repeated imports skip active records with the same invoice number and source for this business.
                </div>

                {/* Footer Buttons */}
                <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 10 }}>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => setShowImportModal(false)}
                    disabled={confirmLoading}
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={handleExecuteImport}
                    disabled={confirmLoading || previewData.ready_to_import === 0}
                    style={{ minWidth: 160 }}
                  >
                    {confirmLoading ? (
                      <>
                        <RotateCw size={14} className="spin-icon" />
                        <span>Importing...</span>
                      </>
                    ) : (
                      <>
                        <UploadCloud size={14} />
                        <span>
                          {previewData.ready_to_import > 0
                            ? `Confirm & Import (${previewData.ready_to_import})`
                            : "All Already Imported"}
                        </span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}

export default GstApiPage;
