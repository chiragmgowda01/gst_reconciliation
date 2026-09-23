import { useState } from "react";
import { UploadCloud, AlertCircle, FileCheck } from "lucide-react";
import { api } from "../api/client";

export function UploadPage({ onUploadSuccess }) {
  const [sourceType, setSourceType] = useState("sales_register");
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      setSelectedFile(e.target.files[0]);
      setResult(null);
      setError("");
    }
  };

  const handleUpload = async (e) => {
    e.preventDefault();
    if (!selectedFile) {
      setError("Please select a CSV file to upload.");
      return;
    }

    setUploading(true);
    setError("");
    setResult(null);

    try {
      const res = await api.uploadCsv(selectedFile, sourceType);
      setResult(res);
      if (onUploadSuccess) onUploadSuccess();
    } catch (err) {
      setError(err.message || "Failed to upload and validate CSV file.");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="animate-fade-in" style={{ maxWidth: 850, margin: "0 auto" }}>
      <div className="card">
        <div className="card-header">
          <div>
            <h3 className="card-title">CSV Data Ingestion & Statutory Validator</h3>
            <p className="card-subtitle">
              Upload company registers or portal return CSVs for structural verification and database ingestion
            </p>
          </div>
        </div>

        <form onSubmit={handleUpload}>
          {/* Target Register Selection */}
          <div style={{ marginBottom: 20 }}>
            <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "var(--text-main)", marginBottom: 8 }}>
              Select Data Target / Register Type:
            </label>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 10 }}>
              {[
                { id: "sales_register", label: "Sales Register (Outward)" },
                { id: "gstr1", label: "GSTR-1 (Portal Return)" },
                { id: "purchase_register", label: "Purchase Register (Inward)" },
                { id: "gstr2a", label: "GSTR-2A (Auto-Drafted ITC)" },
              ].map((opt) => (
                <div
                  key={opt.id}
                  onClick={() => setSourceType(opt.id)}
                  style={{
                    border: `1.5px solid ${sourceType === opt.id ? "var(--primary-600)" : "var(--border-color)"}`,
                    backgroundColor: sourceType === opt.id ? "var(--primary-50)" : "#fff",
                    borderRadius: "var(--radius-sm)",
                    padding: "12px",
                    cursor: "pointer",
                    textAlign: "center",
                    fontWeight: sourceType === opt.id ? 700 : 500,
                    fontSize: 12.5,
                    color: sourceType === opt.id ? "var(--primary-700)" : "var(--text-main)",
                    transition: "all 0.15s ease",
                  }}
                >
                  {opt.label}
                </div>
              ))}
            </div>
          </div>

          {/* Upload Drop Zone */}
          <div
            className="upload-card"
            onClick={() => document.getElementById("csv-file-input").click()}
          >
            <input
              id="csv-file-input"
              type="file"
              accept=".csv"
              style={{ display: "none" }}
              onChange={handleFileChange}
            />

            <UploadCloud size={40} color="#3b82f6" style={{ margin: "0 auto 12px" }} />

            {selectedFile ? (
              <div>
                <div style={{ fontSize: 15, fontWeight: 700, color: "var(--slate-800)" }}>
                  {selectedFile.name}
                </div>
                <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>
                  {(selectedFile.size / 1024).toFixed(1)} KB — Click to change file
                </div>
              </div>
            ) : (
              <div>
                <div style={{ fontSize: 14, fontWeight: 600, color: "var(--slate-800)" }}>
                  Click to select CSV file or drag and drop
                </div>
                <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>
                  Accepts standard CSV with headers: invoice_no, invoice_date, customer/supplier_gstin, taxable_value, gst_amount
                </div>
              </div>
            )}
          </div>

          {error && (
            <div
              style={{
                marginTop: 16,
                padding: "12px 14px",
                backgroundColor: "var(--mismatch-bg)",
                border: "1px solid var(--mismatch-border)",
                borderRadius: "var(--radius-sm)",
                color: "var(--mismatch-text)",
                fontSize: 13,
                display: "flex",
                alignItems: "center",
                gap: 8,
              }}
            >
              <AlertCircle size={16} />
              <span>{error}</span>
            </div>
          )}

          <div style={{ marginTop: 24, display: "flex", justifyContent: "flex-end" }}>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={!selectedFile || uploading}
              style={{ minWidth: 160, justifyContent: "center" }}
            >
              {uploading ? "Validating & Ingesting..." : "Validate & Upload"}
            </button>
          </div>
        </form>

        {/* Validation & Ingestion Results */}
        {result && (
          <div style={{ marginTop: 28, paddingTop: 20, borderTop: "1px solid var(--border-color)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
              <FileCheck size={20} color="#059669" />
              <h4 style={{ fontSize: 15, fontWeight: 700, color: "var(--text-main)" }}>
                Validation & Ingestion Summary
              </h4>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 16 }}>
              <div style={{ padding: 14, background: "var(--slate-50)", border: "1px solid var(--border-color)", borderRadius: 8 }}>
                <div style={{ fontSize: 11, color: "var(--text-muted)" }}>Total Records</div>
                <div style={{ fontSize: 20, fontWeight: 800 }}>{result.total_records}</div>
              </div>
              <div style={{ padding: 14, background: "#ecfdf5", border: "1px solid #a7f3d0", borderRadius: 8 }}>
                <div style={{ fontSize: 11, color: "#059669" }}>Imported to DB</div>
                <div style={{ fontSize: 20, fontWeight: 800, color: "#059669" }}>{result.imported}</div>
              </div>
              <div style={{ padding: 14, background: "#fffbeb", border: "1px solid #fde68a", borderRadius: 8 }}>
                <div style={{ fontSize: 11, color: "#d97706" }}>Duplicate Skipped</div>
                <div style={{ fontSize: 20, fontWeight: 800, color: "#d97706" }}>{result.duplicates}</div>
              </div>
              <div style={{ padding: 14, background: "#fff1f2", border: "1px solid #fecdd3", borderRadius: 8 }}>
                <div style={{ fontSize: 11, color: "#e11d48" }}>Invalid Records</div>
                <div style={{ fontSize: 20, fontWeight: 800, color: "#e11d48" }}>{result.invalid_records}</div>
              </div>
            </div>

            {result.errors && result.errors.length > 0 && (
              <div style={{ marginTop: 14 }}>
                <h5 style={{ fontSize: 12.5, fontWeight: 700, color: "#e11d48", marginBottom: 8 }}>
                  Validation Errors Flagged:
                </h5>
                <div style={{ maxHeight: 180, overflowY: "auto", background: "var(--slate-50)", border: "1px solid var(--border-color)", borderRadius: 6, padding: "8px 12px" }}>
                  {result.errors.map((err, i) => (
                    <div key={i} style={{ fontSize: 12, color: "#991b1b", padding: "4px 0", borderBottom: i < result.errors.length - 1 ? "1px solid #e2e8f0" : "none" }}>
                      • {err}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
