import { Building2, Database, Sliders, CheckCircle2, ShieldCheck } from "lucide-react";
import { api } from "../api/client";

const GST_STATES = {
  "01": "Jammu & Kashmir",
  "02": "Himachal Pradesh",
  "03": "Punjab",
  "04": "Chandigarh",
  "05": "Uttarakhand",
  "06": "Haryana",
  "07": "Delhi",
  "08": "Rajasthan",
  "09": "Uttar Pradesh",
  "10": "Bihar",
  "19": "West Bengal",
  "24": "Gujarat",
  "27": "Maharashtra",
  "29": "Karnataka",
  "32": "Kerala",
  "33": "Tamil Nadu",
  "36": "Telangana",
  "37": "Andhra Pradesh",
};

export function SettingsPage({ activeBusiness }) {
  const businessName = activeBusiness?.name || "Apex MSME Solutions Private Limited";
  const businessGstin = activeBusiness?.gstin || "29AAAAA1111A1Z5";
  const stateCode = businessGstin.slice(0, 2);
  const stateName = GST_STATES[stateCode] || "State Jurisdiction";
  const stateLabel = `${stateCode} — ${stateName}`;

  return (
    <div className="animate-fade-in" style={{ maxWidth: 880, margin: "0 auto", paddingBottom: 40 }}>
      {/* Page Header */}
      <div style={{ marginBottom: 22 }}>
        <h2 style={{ fontSize: 20, fontWeight: 800, color: "var(--navy-950)", letterSpacing: "-0.3px" }}>
          System Configuration & Profile
        </h2>
        <p style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 2 }}>
          MSME legal entity settings, database integration parameters, and statutory reconciliation tolerances
        </p>
      </div>

      {/* 1. MSME Business Profile Card */}
      <div
        className="institutional-card"
        style={{
          background: "#ffffff",
          border: "1px solid #e7e2dc",
          borderRadius: 18,
          boxShadow: "0 2px 10px rgba(15, 23, 42, 0.04)",
          padding: "26px 28px",
          marginBottom: 20,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20, paddingBottom: 14, borderBottom: "1px solid #f1f5f9" }}>
          <div
            style={{
              width: 38,
              height: 38,
              borderRadius: 10,
              backgroundColor: "rgba(234, 88, 12, 0.12)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "#ea580c",
            }}
          >
            <Building2 size={20} />
          </div>
          <div>
            <h3 style={{ fontSize: 15.5, fontWeight: 700, color: "#0f172a" }}>MSME Business Profile</h3>
            <p style={{ fontSize: 12, color: "#64748b" }}>Active statutory identity used for ledger matching and return filings</p>
          </div>
        </div>

        <div className="config-grid">
          <div>
            <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#475569", marginBottom: 6 }}>
              Legal Registered Entity Name
            </label>
            <div
              style={{
                height: 48,
                borderRadius: 10,
                backgroundColor: "#f8fafc",
                border: "1px solid #e2e8f0",
                padding: "0 14px",
                display: "flex",
                alignItems: "center",
                fontSize: 13.5,
                fontWeight: 600,
                color: "#1e293b",
              }}
            >
              {businessName}
            </div>
          </div>

          <div>
            <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#475569", marginBottom: 6 }}>
              Statutory GSTIN
            </label>
            <div
              style={{
                height: 48,
                borderRadius: 10,
                backgroundColor: "#f8fafc",
                border: "1px solid #e2e8f0",
                padding: "0 14px",
                display: "flex",
                alignItems: "center",
                fontSize: 13.5,
                fontWeight: 700,
                fontFamily: "var(--font-mono)",
                color: "#c2410c",
                letterSpacing: "0.5px",
              }}
            >
              {businessGstin}
            </div>
          </div>

          <div>
            <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#475569", marginBottom: 6 }}>
              State Jurisdiction
            </label>
            <div
              style={{
                height: 48,
                borderRadius: 10,
                backgroundColor: "#f8fafc",
                border: "1px solid #e2e8f0",
                padding: "0 14px",
                display: "flex",
                alignItems: "center",
                fontSize: 13.5,
                color: "#334155",
              }}
            >
              {stateLabel}
            </div>
          </div>

          <div>
            <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#475569", marginBottom: 6 }}>
              Taxpayer Classification
            </label>
            <div
              style={{
                height: 48,
                borderRadius: 10,
                backgroundColor: "#f8fafc",
                border: "1px solid #e2e8f0",
                padding: "0 14px",
                display: "flex",
                alignItems: "center",
                fontSize: 13.5,
                color: "#334155",
              }}
            >
              Regular MSME Taxpayer (Monthly GSTR-1 / GSTR-3B)
            </div>
          </div>
        </div>
      </div>

      {/* 2. Backend Architecture & Database Integration */}
      <div
        className="institutional-card"
        style={{
          background: "#ffffff",
          border: "1px solid #e7e2dc",
          borderRadius: 18,
          boxShadow: "0 2px 10px rgba(15, 23, 42, 0.04)",
          padding: "26px 28px",
          marginBottom: 20,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20, paddingBottom: 14, borderBottom: "1px solid #f1f5f9" }}>
          <div
            style={{
              width: 38,
              height: 38,
              borderRadius: 10,
              backgroundColor: "rgba(5, 150, 105, 0.12)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "#059669",
            }}
          >
            <Database size={20} />
          </div>
          <div>
            <h3 style={{ fontSize: 15.5, fontWeight: 700, color: "#0f172a" }}>Backend Architecture & Database Integration</h3>
            <p style={{ fontSize: 12, color: "#64748b" }}>FastAPI REST services and cloud PostgreSQL persistence</p>
          </div>
        </div>

        <div className="config-grid">
          <div>
            <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#475569", marginBottom: 6 }}>
              API Base URL
            </label>
            <div
              style={{
                height: 48,
                borderRadius: 10,
                backgroundColor: "#f8fafc",
                border: "1px solid #e2e8f0",
                padding: "0 14px",
                display: "flex",
                alignItems: "center",
                fontSize: 13,
                fontFamily: "var(--font-mono)",
                color: "#334155",
              }}
            >
              {api.baseUrl}
            </div>
          </div>

          <div>
            <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#475569", marginBottom: 6 }}>
              Database Provider
            </label>
            <div
              style={{
                height: 48,
                borderRadius: 10,
                backgroundColor: "#f8fafc",
                border: "1px solid #e2e8f0",
                padding: "0 14px",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span
                  style={{
                    width: 8,
                    height: 8,
                    borderRadius: "50%",
                    backgroundColor: "#10b981",
                    display: "inline-block",
                    boxShadow: "0 0 0 3px rgba(16, 185, 129, 0.2)",
                  }}
                />
                <span style={{ fontSize: 13.5, fontWeight: 700, color: "#0f172a" }}>
                  Supabase PostgreSQL
                </span>
              </div>
              <span
                style={{
                  fontSize: 11,
                  fontWeight: 600,
                  color: "#059669",
                  backgroundColor: "#ecfdf5",
                  padding: "3px 8px",
                  borderRadius: 6,
                  border: "1px solid #a7f3d0",
                }}
              >
                Connected
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* 3. Reconciliation Rules & Tolerances */}
      <div
        className="institutional-card"
        style={{
          background: "#ffffff",
          border: "1px solid #e7e2dc",
          borderRadius: 18,
          boxShadow: "0 2px 10px rgba(15, 23, 42, 0.04)",
          padding: "26px 28px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20, paddingBottom: 14, borderBottom: "1px solid #f1f5f9" }}>
          <div
            style={{
              width: 38,
              height: 38,
              borderRadius: 10,
              backgroundColor: "rgba(217, 119, 6, 0.12)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "#d97706",
            }}
          >
            <Sliders size={20} />
          </div>
          <div>
            <h3 style={{ fontSize: 15.5, fontWeight: 700, color: "#0f172a" }}>Reconciliation Rules & Tolerances</h3>
            <p style={{ fontSize: 12, color: "#64748b" }}>Automated variance thresholds and audit anomaly escalation criteria</p>
          </div>
        </div>

        <div className="config-grid">
          <div>
            <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#475569", marginBottom: 6 }}>
              Rounding Tolerance (₹)
            </label>
            <div
              style={{
                height: 48,
                borderRadius: 10,
                backgroundColor: "#f8fafc",
                border: "1px solid #e2e8f0",
                padding: "0 14px",
                display: "flex",
                alignItems: "center",
                fontSize: 13.5,
                color: "#1e293b",
                gap: 8,
              }}
            >
              <CheckCircle2 size={15} color="#059669" />
              <span>₹0.00 (Exact invoice matching enforced)</span>
            </div>
          </div>

          <div>
            <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#475569", marginBottom: 6 }}>
              High-Risk Anomaly Threshold (₹)
            </label>
            <div
              style={{
                height: 48,
                borderRadius: 10,
                backgroundColor: "#f8fafc",
                border: "1px solid #e2e8f0",
                padding: "0 14px",
                display: "flex",
                alignItems: "center",
                fontSize: 13.5,
                color: "#1e293b",
                gap: 8,
              }}
            >
              <ShieldCheck size={15} color="#ea580c" />
              <span>≥ ₹1,000.00 (Escalates to High Severity)</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
