import { useState } from "react";
import { Building2, Lock, Mail, User, AlertCircle, ArrowRight, Shield } from "lucide-react";
import { api } from "../api/client";

export function LoginPage({ onLoginSuccess }) {
  const [tab, setTab] = useState("login"); // "login" | "register"
  const [email, setEmail] = useState("default@gst.local");
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
      setError(err.message || "Invalid email or password. Please verify credentials.");
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
    <div className="login-viewport">
      {/* Abstract decorative ambient blobs for glassmorphism */}
      <div className="login-ambient-blob blob-1"></div>
      <div className="login-ambient-blob blob-2"></div>
      <div className="login-ambient-blob blob-3"></div>

      {/* Centered Glassmorphic Authentication Card */}
      <div className="login-card-container animate-fade-in">
        <div className="login-card">
          {/* Brand Header */}
          <div className="login-brand-header">
            <div className="login-logo-box">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <rect x="2" y="3" width="20" height="18" rx="4" fill="url(#loginSaffronGrad)" />
                <path d="M7 8h10M7 12h6M7 16h8" stroke="#ffffff" strokeWidth="2" strokeLinecap="round" />
                <circle cx="16" cy="14" r="3.5" fill="#0f1e36" stroke="#ffffff" strokeWidth="1.5" />
                <path d="M15 14l1 1 2-2" stroke="#ffffff" strokeWidth="1.2" strokeLinecap="round" />
                <defs>
                  <linearGradient id="loginSaffronGrad" x1="2" y1="3" x2="22" y2="21" gradientUnits="userSpaceOnUse">
                    <stop stopColor="#f97316" />
                    <stop offset="1" stopColor="#ea580c" />
                  </linearGradient>
                </defs>
              </svg>
            </div>
            <h1 className="login-title">ReconcilePro</h1>
            <p className="login-subtitle">MSME GST Reconciliation & Anomaly Detection</p>
          </div>

          {/* Segmented Tab Switch */}
          <div className="login-segmented-control">
            <button
              type="button"
              className={`segmented-tab ${tab === "login" ? "active" : ""}`}
              onClick={() => {
                setTab("login");
                setError("");
              }}
            >
              Sign In
            </button>
            <button
              type="button"
              className={`segmented-tab ${tab === "register" ? "active" : ""}`}
              onClick={() => {
                setTab("register");
                setError("");
              }}
            >
              Register MSME
            </button>
          </div>

          {/* Error Alert */}
          {error && (
            <div className="login-error-alert">
              <AlertCircle size={16} className="error-icon" />
              <span>{error}</span>
            </div>
          )}

          {/* Sign In Form */}
          {tab === "login" ? (
            <form onSubmit={handleLoginSubmit} className="login-form">
              <div className="form-group">
                <label className="form-label">Email Address</label>
                <div className="input-box-wrapper">
                  <Mail size={17} className="input-leading-icon" />
                  <input
                    type="email"
                    className="polished-input"
                    placeholder="name@company.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    autoComplete="username"
                    required
                  />
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">Password</label>
                <div className="input-box-wrapper">
                  <Lock size={17} className="input-leading-icon" />
                  <input
                    type="password"
                    className="polished-input"
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
                className="login-primary-btn"
                disabled={loading}
              >
                {loading ? "Signing In..." : "Sign In"}
                {!loading && <ArrowRight size={16} />}
              </button>

              {/* Compact Demo Access Box */}
              <div className="demo-access-box">
                <div className="demo-header">
                  <Shield size={13} color="#ea580c" />
                  <span>Demo Access</span>
                </div>
                <div className="demo-credentials">
                  <div>Email: <strong>default@gst.local</strong></div>
                  <div>Password: <strong>Demo@123</strong> (or <strong>password123</strong>)</div>
                </div>
              </div>
            </form>
          ) : (
            /* Register Form */
            <form onSubmit={handleRegisterSubmit} className="login-form">
              <div className="form-group">
                <label className="form-label">Full Name</label>
                <div className="input-box-wrapper">
                  <User size={17} className="input-leading-icon" />
                  <input
                    type="text"
                    className="polished-input"
                    placeholder="Ramesh Kumar"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    required
                  />
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">Email Address</label>
                <div className="input-box-wrapper">
                  <Mail size={17} className="input-leading-icon" />
                  <input
                    type="email"
                    className="polished-input"
                    placeholder="name@company.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                  />
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">Password</label>
                <div className="input-box-wrapper">
                  <Lock size={17} className="input-leading-icon" />
                  <input
                    type="password"
                    className="polished-input"
                    placeholder="••••••••"
                    minLength={6}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                  />
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">Business Name</label>
                <div className="input-box-wrapper">
                  <Building2 size={17} className="input-leading-icon" />
                  <input
                    type="text"
                    className="polished-input"
                    placeholder="Precision Components Pvt Ltd"
                    value={businessName}
                    onChange={(e) => setBusinessName(e.target.value)}
                    required
                  />
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">GSTIN (15 characters)</label>
                <div className="input-box-wrapper">
                  <input
                    type="text"
                    className="polished-input mono-font uppercase"
                    style={{ paddingLeft: "14px" }}
                    placeholder="29AAAAA0000A1Z5"
                    maxLength={15}
                    value={gstin}
                    onChange={(e) => setGstin(e.target.value.toUpperCase())}
                    required
                  />
                </div>
              </div>

              <button
                type="submit"
                className="login-primary-btn"
                disabled={loading}
              >
                {loading ? "Registering..." : "Register MSME"}
                {!loading && <ArrowRight size={16} />}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
