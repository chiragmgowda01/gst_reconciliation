import { Building2, Database, Sliders } from "lucide-react";
import { api } from "../api/client";

export function SettingsPage() {
  return (
    <div className="animate-fade-in" style={{ maxWidth: 850, margin: "0 auto" }}>
      {/* Business Profile */}
      <div className="card">
        <div className="card-header">
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <Building2 size={20} color="#2563eb" />
            <div>
              <h3 className="card-title">MSME Business Profile</h3>
              <p className="card-subtitle">Entity details used for reconciliation and return filings</p>
            </div>
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>
              Legal Registered Entity Name
            </label>
            <input
              type="text"
              className="filter-input"
              style={{ width: "100%" }}
              value="Apex MSME Solutions Private Limited"
              readOnly
            />
          </div>

          <div>
            <label style={{ fontSize: 12, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>
              Statutory GSTIN
            </label>
            <input
              type="text"
              className="filter-input mono-cell"
              style={{ width: "100%", fontWeight: 600 }}
              value="29AAAAA1111A1Z5"
              readOnly
            />
          </div>

          <div>
            <label style={{ fontSize: 12, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>
              State Jurisdiction
            </label>
            <input
              type="text"
              className="filter-input"
              style={{ width: "100%" }}
              value="29 — Karnataka"
              readOnly
            />
          </div>

          <div>
            <label style={{ fontSize: 12, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>
              Taxpayer Classification
            </label>
            <input
              type="text"
              className="filter-input"
              style={{ width: "100%" }}
              value="Regular MSME Taxpayer (Monthly GSTR-1 / GSTR-3B)"
              readOnly
            />
          </div>
        </div>
      </div>

      {/* Backend & Database Integration */}
      <div className="card">
        <div className="card-header">
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <Database size={20} color="#059669" />
            <div>
              <h3 className="card-title">Backend Architecture & Database Integration</h3>
              <p className="card-subtitle">PostgreSQL / Supabase connection parameters and API status</p>
            </div>
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>
              API Base Gateway
            </label>
            <input
              type="text"
              className="filter-input mono-cell"
              style={{ width: "100%" }}
              value={api.baseUrl}
              readOnly
            />
          </div>

          <div>
            <label style={{ fontSize: 12, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>
              Database Provider
            </label>
            <div style={{ display: "flex", alignItems: "center", gap: 8, height: 35 }}>
              <span className="live-pulse" />
              <span style={{ fontSize: 13, fontWeight: 600 }}>Supabase PostgreSQL / Local Fallback Active</span>
            </div>
          </div>
        </div>
      </div>

      {/* Reconciliation Engine Thresholds */}
      <div className="card">
        <div className="card-header">
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <Sliders size={20} color="#d97706" />
            <div>
              <h3 className="card-title">Reconciliation Rules & Tolerances</h3>
              <p className="card-subtitle">Statutory thresholds and exception detection parameters</p>
            </div>
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>
              Rounding Tolerance (₹)
            </label>
            <input
              type="text"
              className="filter-input"
              style={{ width: "100%" }}
              value="₹0.00 (Exact matching enforced)"
              readOnly
            />
          </div>

          <div>
            <label style={{ fontSize: 12, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>
              High-Risk Anomaly Threshold (₹)
            </label>
            <input
              type="text"
              className="filter-input"
              style={{ width: "100%" }}
              value="≥ ₹1,000.00 (Escalates to High Severity)"
              readOnly
            />
          </div>
        </div>
      </div>
    </div>
  );
}
