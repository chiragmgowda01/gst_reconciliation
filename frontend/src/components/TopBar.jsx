import { Search, RotateCw, Bell, LogOut, Menu } from "lucide-react";
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
  onToggleSidebar,
  isSyntheticDemo = true,
}) {
  const titles = {
    dashboard: {
      title: "Executive Dashboard",
      subtitle: "GST reconciliation overview & compliance health",
    },
    sales: {
      title: "Sales Reconciliation",
      subtitle: "Sales Register ↔ GSTR-1 outward matching",
    },
    purchase: {
      title: "Purchase & ITC Reconciliation",
      subtitle: "Purchase Register ↔ GSTR-2A/2B supplier filings",
    },
    gstr3b: {
      title: "Form GSTR-3B Summary",
      subtitle: "Monthly tax liability and Input Tax Credit",
    },
    anomalies: {
      title: "Anomaly Center",
      subtitle: "Audit exception tracking and discrepancy reviews",
    },
    gst_api: {
      title: "GST Data Center",
      subtitle: "Simulated GST Suvidha Provider (GSP) & return filings",
    },
    invoices: {
      title: "Invoice Master",
      subtitle: "Multi-source invoice database records",
    },
    upload: {
      title: "CSV Ingestion",
      subtitle: "Upload and validate register CSV files",
    },
    reports: {
      title: "Statutory Reports",
      subtitle: "Download reconciliation schedules and audit CSVs",
    },
    settings: {
      title: "Configuration",
      subtitle: "System parameters and tenant settings",
    },
  };

  const current = titles[currentTab] || {
    title: "ReconcilePro",
    subtitle: "MSME GST Reconciliation Platform",
  };

  return (
    <header className="topbar">
      <div className="topbar-left">
        {onToggleSidebar && (
          <button
            type="button"
            className="topbar-toggle-btn"
            onClick={onToggleSidebar}
            title="Toggle Navigation Menu"
            aria-label="Toggle Navigation Menu"
          >
            <Menu size={18} />
          </button>
        )}

        <div className="page-title-group">
          <div className="page-title-row">
            <h1>{current.title}</h1>
            {isSyntheticDemo ? (
              <div className="demo-mode-pill" title="Synthetic simulated GST transaction ledger">
                <span className="demo-mode-dot" />
                <span>Demo Data</span>
              </div>
            ) : (
              <div className="live-mode-pill" title="Connected to live registered enterprise ledger">
                <span className="live-mode-dot" />
                <span>Live Data</span>
              </div>
            )}
          </div>
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
          type="button"
          className="topbar-btn"
          title="Refresh Data"
          onClick={onRefresh}
          disabled={isRefreshing}
          aria-label="Refresh Data"
        >
          <RotateCw size={15} className={isRefreshing ? "animate-spin" : ""} />
        </button>

        <button
          type="button"
          className="topbar-btn"
          title="Anomalies & Notifications"
          onClick={onOpenNotifications}
          aria-label="Anomalies & Notifications"
        >
          <Bell size={15} />
          <span className="notif-dot" />
        </button>

        {onLogout && (
          <button
            type="button"
            className="topbar-btn btn-signout"
            title="Sign Out"
            onClick={onLogout}
            aria-label="Sign Out"
          >
            <LogOut size={15} />
          </button>
        )}
      </div>
    </header>
  );
}
export default TopBar;
