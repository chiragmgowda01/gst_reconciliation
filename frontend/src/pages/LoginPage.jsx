import { useState } from "react";
import { Building2, Lock, Mail, User, ShieldCheck, AlertCircle, ArrowRight } from "lucide-react";
import { api } from "../api/client";

export function LoginPage({ onLoginSuccess }) {
  const [tab, setTab] = useState("login"); // "login" | "register"
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  // Register fields
  const [name, setName] = useState("");
  const [businessName, setBusinessName] = useState("");
  const [gstin, setGstin] = useState("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleLoginSubmit = async (e) => {
    e.preventDefault();
    if (!email || !password) {
      setError("Please enter your email and password.");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const res = await api.login(email.trim(), password);
      if (onLoginSuccess) {
        onLoginSuccess(res.user, res.businesses);
      }
    } catch (err) {
      setError(err.message || "Invalid credentials. Please verify and try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleRegisterSubmit = async (e) => {
    e.preventDefault();
    if (!name || !email || !password || !businessName || !gstin) {
      setError("All fields are required for registration.");
      return;
    }
    if (gstin.trim().length !== 15) {
      setError("GSTIN must be exactly 15 characters.");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const res = await api.register({
        name: name.trim(),
        email: email.trim(),
        password,
        business_name: businessName.trim(),
        gstin: gstin.trim().toUpperCase(),
      });
      if (onLoginSuccess) {
        onLoginSuccess(res.user, res.businesses);
      }
    } catch (err) {
      setError(err.message || "Registration failed. Please check inputs.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        backgroundColor: "var(--slate-50)",
        padding: "24px 16px",
      }}
    >
      <div
        className="card animate-fade-in"
        style={{
          width: "100%",
          maxWidth: 480,
          padding: "36px 32px",
          boxShadow: "var(--shadow-xl)",
          border: "1px solid var(--border-color)",
          backgroundColor: "#ffffff",
          borderRadius: "var(--radius-xl)",
        }}
      >
        {/* Header Branding */}
        <div style={{ textAlign: "center", marginBottom: 28 }}>
          <div
            style={{
              width: 48,
              height: 48,
              margin: "0 auto 12px",
              background: "linear-gradient(135deg, #2563eb, #1d4ed8)",
              borderRadius: "var(--radius-md)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "#fff",
              fontWeight: 800,
              fontSize: 20,
              boxShadow: "0 8px 16px rgba(37, 99, 235, 0.3)",
            }}
          >
            GST
          </div>
          <h2 style={{ fontSize: 22, fontWeight: 800, color: "var(--text-main)", letterSpacing: -0.5 }}>
            ReconcilePro
          </h2>
          <p style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 4 }}>
            Automated MSME GST Reconciliation & Anomaly Detector
          </p>
        </div>

        {/* Auth Mode Tabs */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 4,
            backgroundColor: "var(--slate-100)",
            padding: 4,
            borderRadius: "var(--radius-md)",
            marginBottom: 24,
          }}
        >
          <button
            type="button"
            onClick={() => {
              setTab("login");
              setError("");
            }}
            style={{
              padding: "8px 0",
              border: "none",
              borderRadius: "var(--radius-sm)",
              backgroundColor: tab === "login" ? "#ffffff" : "transparent",
              color: tab === "login" ? "var(--text-main)" : "var(--text-muted)",
              fontWeight: tab === "login" ? 700 : 500,
              fontSize: 13,
              cursor: "pointer",
              boxShadow: tab === "login" ? "var(--shadow-sm)" : "none",
              transition: "all 0.15s ease",
            }}
          >
            Sign In
          </button>
          <button
            type="button"
            onClick={() => {
              setTab("register");
              setError("");
            }}
            style={{
              padding: "8px 0",
              border: "none",
              borderRadius: "var(--radius-sm)",
              backgroundColor: tab === "register" ? "#ffffff" : "transparent",
              color: tab === "register" ? "var(--text-main)" : "var(--text-muted)",
              fontWeight: tab === "register" ? 700 : 500,
              fontSize: 13,
              cursor: "pointer",
              boxShadow: tab === "register" ? "var(--shadow-sm)" : "none",
              transition: "all 0.15s ease",
            }}
          >
            Register MSME
          </button>
        </div>

        {/* Error Alert */}
        {error && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              padding: "10px 14px",
              backgroundColor: "var(--mismatch-bg)",
              border: "1px solid var(--mismatch-border)",
              borderRadius: "var(--radius-sm)",
              color: "var(--mismatch-text)",
              fontSize: 12.5,
              marginBottom: 18,
            }}
          >
            <AlertCircle size={15} style={{ flexShrink: 0 }} />
            <span>{error}</span>
          </div>
        )}

        {/* Login Form */}
        {tab === "login" ? (
          <form onSubmit={handleLoginSubmit}>
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: "block", fontSize: 12.5, fontWeight: 600, color: "var(--text-main)", marginBottom: 6 }}>
                Work Email Address
              </label>
              <div style={{ position: "relative" }}>
                <Mail size={16} color="#94a3b8" style={{ position: "absolute", left: 12, top: 11 }} />
                <input
                  type="email"
                  className="filter-input"
                  style={{ width: "100%", paddingLeft: 36 }}
                  placeholder="name@company.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="username"
                  required
                />
              </div>
            </div>

            <div style={{ marginBottom: 22 }}>
              <label style={{ display: "block", fontSize: 12.5, fontWeight: 600, color: "var(--text-main)", marginBottom: 6 }}>
                Account Password
              </label>
              <div style={{ position: "relative" }}>
                <Lock size={16} color="#94a3b8" style={{ position: "absolute", left: 12, top: 11 }} />
                <input
                  type="password"
                  className="filter-input"
                  style={{ width: "100%", paddingLeft: 36 }}
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  required
                />
              </div>
            </div>

            <button
              type="submit"
              className="btn btn-primary"
              disabled={loading}
              style={{ width: "100%", justifyContent: "center", padding: "10px 0", fontSize: 14 }}
            >
              {loading ? "Authenticating..." : "Sign In to Dashboard"}
              {!loading && <ArrowRight size={15} />}
            </button>

            {/* Local Demonstration / College Project Evaluation Note */}
            <div
              style={{
                marginTop: 24,
                padding: "12px 14px",
                backgroundColor: "var(--slate-50)",
                borderRadius: "var(--radius-sm)",
                border: "1px solid var(--border-color)",
                fontSize: 12,
                color: "var(--text-muted)",
                lineHeight: 1.5,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 6, fontWeight: 600, color: "var(--slate-700)", marginBottom: 4 }}>
                <ShieldCheck size={14} color="#059669" />
                Local Evaluation Guide
              </div>
              For demonstration access with pre-seeded demo registers, sign in with email <code>default@gst.local</code> and the setup password. Legacy passwords are automatically upgraded to PBKDF2-SHA256 upon verification.
            </div>
          </form>
        ) : (
          /* Register Form */
          <form onSubmit={handleRegisterSubmit}>
            <div style={{ marginBottom: 14 }}>
              <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--text-main)", marginBottom: 4 }}>
                Contact Person Name
              </label>
              <div style={{ position: "relative" }}>
                <User size={15} color="#94a3b8" style={{ position: "absolute", left: 12, top: 10 }} />
                <input
                  type="text"
                  className="filter-input"
                  style={{ width: "100%", paddingLeft: 34 }}
                  placeholder="e.g. Ramesh Kumar"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                />
              </div>
            </div>

            <div style={{ marginBottom: 14 }}>
              <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--text-main)", marginBottom: 4 }}>
                Work Email Address
              </label>
              <div style={{ position: "relative" }}>
                <Mail size={15} color="#94a3b8" style={{ position: "absolute", left: 12, top: 10 }} />
                <input
                  type="email"
                  className="filter-input"
                  style={{ width: "100%", paddingLeft: 34 }}
                  placeholder="finance@msme.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </div>
            </div>

            <div style={{ marginBottom: 14 }}>
              <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--text-main)", marginBottom: 4 }}>
                Password (min 6 characters)
              </label>
              <div style={{ position: "relative" }}>
                <Lock size={15} color="#94a3b8" style={{ position: "absolute", left: 12, top: 10 }} />
                <input
                  type="password"
                  className="filter-input"
                  style={{ width: "100%", paddingLeft: 34 }}
                  placeholder="••••••••"
                  minLength={6}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </div>
            </div>

            <div style={{ marginBottom: 14 }}>
              <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--text-main)", marginBottom: 4 }}>
                Business Legal Name
              </label>
              <div style={{ position: "relative" }}>
                <Building2 size={15} color="#94a3b8" style={{ position: "absolute", left: 12, top: 10 }} />
                <input
                  type="text"
                  className="filter-input"
                  style={{ width: "100%", paddingLeft: 34 }}
                  placeholder="e.g. Precision Components Pvt Ltd"
                  value={businessName}
                  onChange={(e) => setBusinessName(e.target.value)}
                  required
                />
              </div>
            </div>

            <div style={{ marginBottom: 20 }}>
              <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--text-main)", marginBottom: 4 }}>
                Statutory GSTIN (15 characters)
              </label>
              <input
                type="text"
                className="filter-input mono-cell"
                style={{ width: "100%", textTransform: "uppercase" }}
                placeholder="29AAAAA0000A1Z5"
                maxLength={15}
                value={gstin}
                onChange={(e) => setGstin(e.target.value.toUpperCase())}
                required
              />
            </div>

            <button
              type="submit"
              className="btn btn-primary"
              disabled={loading}
              style={{ width: "100%", justifyContent: "center", padding: "10px 0", fontSize: 14 }}
            >
              {loading ? "Creating Account..." : "Register & Enter Dashboard"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
