import { ShieldCheck, ExternalLink, ArrowRight } from "lucide-react";

export function Footer({ onNavigate }) {
  return (
    <footer className="app-footer">
      <div className="footer-top">
        <div className="footer-col brand-col">
          <div className="footer-logo">
            <div className="footer-logo-mark">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="3" width="18" height="18" rx="2" />
                <path d="M7 8h10" />
                <path d="M7 12h6" />
                <path d="M7 16h4" />
                <path d="M15 13l2 2 4-4" />
              </svg>
            </div>
            <div>
              <h3>GST Reconciliation & Anomaly Detection Platform</h3>
              <p className="footer-sub">MSME GST Compliance & Financial Reconciliation</p>
            </div>
          </div>
          <p className="footer-desc">
            An automated reconciliation and exception detection system engineered for Indian MSMEs to verify outward sales against GSTR-1, validate eligible Input Tax Credit against GSTR-2A, and audit discrepancy risks.
          </p>
          <div className="footer-badge">
            <ShieldCheck size={14} color="#ea580c" />
            <span>Authenticated Multi-Tenant Architecture</span>
          </div>
        </div>

        <div className="footer-col">
          <h4>Module Navigation</h4>
          <ul className="footer-links">
            <li>
              <button type="button" onClick={() => onNavigate && onNavigate("dashboard")}>
                <ArrowRight size={12} /> Dashboard Overview
              </button>
            </li>
            <li>
              <button type="button" onClick={() => onNavigate && onNavigate("sales")}>
                <ArrowRight size={12} /> Sales ↔ GSTR-1 Reconciliation
              </button>
            </li>
            <li>
              <button type="button" onClick={() => onNavigate && onNavigate("purchase")}>
                <ArrowRight size={12} /> Purchase ↔ GSTR-2A (ITC)
              </button>
            </li>
            <li>
              <button type="button" onClick={() => onNavigate && onNavigate("gstr3b")}>
                <ArrowRight size={12} /> GSTR-3B Tax Return Summary
              </button>
            </li>
            <li>
              <button type="button" onClick={() => onNavigate && onNavigate("anomalies")}>
                <ArrowRight size={12} /> Anomaly & Exception Center
              </button>
            </li>
            <li>
              <button type="button" onClick={() => onNavigate && onNavigate("reports")}>
                <ArrowRight size={12} /> Statutory Schedules & Export
              </button>
            </li>
          </ul>
        </div>

        <div className="footer-col">
          <h4>Statutory & Public Resources</h4>
          <ul className="footer-links">
            <li>
              <a href="https://www.gst.gov.in" target="_blank" rel="noopener noreferrer">
                GST Common Portal <ExternalLink size={11} />
              </a>
            </li>
            <li>
              <a href="https://www.cbic.gov.in" target="_blank" rel="noopener noreferrer">
                CBIC Central Board of Indirect Taxes <ExternalLink size={11} />
              </a>
            </li>
            <li>
              <a href="https://msme.gov.in" target="_blank" rel="noopener noreferrer">
                Ministry of Micro, Small and Medium Enterprises <ExternalLink size={11} />
              </a>
            </li>
            <li>
              <a href="https://www.mca.gov.in" target="_blank" rel="noopener noreferrer">
                Ministry of Corporate Affairs <ExternalLink size={11} />
              </a>
            </li>
          </ul>
        </div>
      </div>

      <div className="footer-bottom">
        <div className="footer-bottom-content">
          <p>© 2026 GST Reconciliation & Anomaly Detection Platform. Educational & demonstration project.</p>
          <div className="footer-meta">
            <span className="status-indicator">
              <span className="status-dot"></span> System Status: Active
            </span>
            <span className="meta-sep">•</span>
            <span>Release v1.2.0-Production</span>
          </div>
        </div>
      </div>
    </footer>
  );
}
