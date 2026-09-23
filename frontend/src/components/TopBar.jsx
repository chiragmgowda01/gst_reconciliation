import { Search, RotateCw, Bell, LogOut } from "lucide-react";
import { BusinessSwitcher } from "./BusinessSwitcher";

export function TopBar({
  currentTab,
  onRefresh,
  isRefreshing,
  searchQuery,
  setSearchQuery,
  onOpenNotifications,
  businesses,
  activeBusiness,
  onSelectBusiness,
  onBusinessAdded,
  onLogout,
}) {
  const titles = {
    dashboard: { title: "Executive Dashboard", subtitle: "Comprehensive reconciliation health and tax overview" },
    sales: { title: "Sales Reconciliation", subtitle: "Sales Register ↔ GSTR-1 outward supplies matching" },
    purchase: { title: "Purchase Reconciliation", subtitle: "Purchase Register ↔ GSTR-2A eligible ITC verification" },
    gstr3b: { title: "GSTR-3B Summary", subtitle: "Monthly tax liability and Input Tax Credit reconciliation" },
    anomalies: { title: "Anomaly & Exception Center", subtitle: "Automated discrepancy detection and compliance risks" },
    invoices: { title: "Invoices Master Database", subtitle: "Centralized multi-source invoice registry" },
    upload: { title: "CSV Data Ingestion", subtitle: "Upload and validate sales, purchase, GSTR-1 and GSTR-2A files" },
    reports: { title: "Reports & Export Center", subtitle: "Download audit summaries and reconciliation schedules" },
    settings: { title: "System Settings", subtitle: "Reconciliation thresholds and business configuration" },
  };

  const current = titles[currentTab] || { title: "GST Reconciliation", subtitle: "Automated MSME GST Suite" };

  return (
    <header className="topbar">
      <div className="topbar-left">
        <div className="page-title-group">
          <h1>{current.title}</h1>
          <p>{current.subtitle}</p>
        </div>
      </div>

      <div className="topbar-right">
        <BusinessSwitcher
          businesses={businesses}
          activeBusiness={activeBusiness}
          onSelectBusiness={onSelectBusiness}
          onBusinessAdded={onBusinessAdded}
        />

        <div className="search-box">
          <Search size={15} color="#94a3b8" />
          <input
            type="text"
            placeholder="Search invoice or GSTIN..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        <button
          className="topbar-btn"
          title="Refresh Data"
          onClick={onRefresh}
          disabled={isRefreshing}
        >
          <RotateCw size={16} className={isRefreshing ? "animate-spin" : ""} />
        </button>

        <button
          className="topbar-btn"
          title="Notifications & Anomalies"
          onClick={onOpenNotifications}
        >
          <Bell size={16} />
          <span className="notif-dot" />
        </button>

        {onLogout && (
          <button
            className="topbar-btn"
            title="Sign Out"
            onClick={onLogout}
            style={{ color: "#ef4444" }}
          >
            <LogOut size={15} />
          </button>
        )}
      </div>
    </header>
  );
}
