import { Fragment } from "react";
import {
  LayoutDashboard,
  ArrowUpRight,
  ArrowDownLeft,
  Receipt,
  AlertTriangle,
  FileText,
  UploadCloud,
  BarChart3,
  Settings,
  Building2,
  LogOut,
} from "lucide-react";

export function Sidebar({ currentTab, setCurrentTab, anomalyCount = 0, user, activeBusiness, onLogout }) {
  const navItems = [
    { id: "dashboard", label: "Dashboard", icon: LayoutDashboard, section: "Overview" },
    { id: "sales", label: "Sales ↔ GSTR-1", icon: ArrowUpRight, section: "Reconciliation" },
    { id: "purchase", label: "Purchase ↔ GSTR-2A", icon: ArrowDownLeft, section: "Reconciliation" },
    { id: "gstr3b", label: "GSTR-3B Summary", icon: Receipt, section: "Tax Filing" },
    { id: "anomalies", label: "Anomaly Center", icon: AlertTriangle, section: "Audit", badge: anomalyCount },
    { id: "invoices", label: "Invoice Records", icon: FileText, section: "Data Management" },
    { id: "upload", label: "CSV Ingestion", icon: UploadCloud, section: "Data Management" },
    { id: "reports", label: "Reports & Export", icon: BarChart3, section: "Analytics" },
    { id: "settings", label: "Settings", icon: Settings, section: "Configuration" },
  ];

  let lastSection = "";

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="sidebar-logo-icon">GST</div>
        <div className="sidebar-logo-text">
          <h2>ReconcilePro</h2>
          <span>MSME GST Engine v1.0</span>
        </div>
      </div>

      <div className="sidebar-nav">
        {navItems.map((item) => {
          const showSection = item.section !== lastSection;
          lastSection = item.section;

          return (
            <Fragment key={item.id}>
              {showSection && <div className="nav-section-title">{item.section}</div>}
              <button
                className={`nav-item ${currentTab === item.id ? "active" : ""}`}
                onClick={() => setCurrentTab(item.id)}
              >
                <item.icon size={17} />
                <span>{item.label}</span>
                {item.badge !== undefined && item.badge > 0 && (
                  <span className="nav-badge">{item.badge}</span>
                )}
              </button>
            </Fragment>
          );
        })}
      </div>

      <div className="sidebar-footer">
        <div className="business-pill" style={{ marginBottom: 12 }}>
          <div className="business-avatar">
            <Building2 size={16} />
          </div>
          <div className="business-info">
            <div className="business-name">{activeBusiness ? activeBusiness.name : "No Business Selected"}</div>
            <div className="business-gstin">{activeBusiness ? activeBusiness.gstin : "—"}</div>
          </div>
        </div>

        {user && (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", paddingTop: 8, borderTop: "1px solid #1e293b" }}>
            <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", marginRight: 8 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: "#f8fafc" }}>{user.name}</div>
              <div style={{ fontSize: 10.5, color: "#64748b" }}>{user.email}</div>
            </div>
            {onLogout && (
              <button
                className="topbar-btn"
                title="Sign Out"
                onClick={onLogout}
                style={{ width: 28, height: 28, backgroundColor: "#1e293b", borderColor: "#334155", color: "#f87171" }}
              >
                <LogOut size={13} />
              </button>
            )}
          </div>
        )}
      </div>
    </aside>
  );
}
