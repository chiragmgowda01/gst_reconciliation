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
      subtitle: "Purchase Register ↔ GSTR-2A supplier filings",
    },
    gstr3b: {
      title: "Form GSTR-3B Summary",
      subtitle: "Monthly tax liability and Input Tax Credit",
    },
    anomalies: {
      title: "Anomaly Center",
      subtitle: "Audit exception tracking and discrepancy reviews",
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
          type="button"
          className="topbar-btn"
          title="Refresh Data"
          onClick={onRefresh}
          disabled={isRefreshing}
        >
          <RotateCw size={15} className={isRefreshing ? "animate-spin" : ""} />
        </button>

        <button
          type="button"
          className="topbar-btn"
          title="Anomalies & Notifications"
          onClick={onOpenNotifications}
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
          >
            <LogOut size={15} />
          </button>
        )}
      </div>
    </header>
  );
}
