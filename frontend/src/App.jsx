import { useEffect, useState, useCallback } from "react";
import "./App.css";
import { api, authStorage } from "./api/client";
import { Sidebar } from "./components/Sidebar";
import { TopBar } from "./components/TopBar";
import { InvoiceDetailModal } from "./components/InvoiceDetailModal";
import { LoadingSkeleton } from "./components/LoadingSkeleton";
import { ErrorState } from "./components/ErrorState";

import { LoginPage } from "./pages/LoginPage";
import { DashboardPage } from "./pages/DashboardPage";
import { SalesReconciliationPage } from "./pages/SalesReconciliationPage";
import { PurchaseReconciliationPage } from "./pages/PurchaseReconciliationPage";
import { Gstr3bPage } from "./pages/Gstr3bPage";
import { AnomaliesPage } from "./pages/AnomaliesPage";
import { InvoicesPage } from "./pages/InvoicesPage";
import { UploadPage } from "./pages/UploadPage";
import { ReportsPage } from "./pages/ReportsPage";
import { SettingsPage } from "./pages/SettingsPage";

export function App() {
  const [user, setUser] = useState(null);
  const [businesses, setBusinesses] = useState([]);
  const [activeBusiness, setActiveBusiness] = useState(null);
  const [isAuthChecking, setIsAuthChecking] = useState(true);

  const [currentTab, setCurrentTab] = useState("dashboard");
  const [reconciliationData, setReconciliationData] = useState(null);
  const [gstr3b, setGstr3b] = useState(null);
  const [anomalies, setAnomalies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [selectedInvoice, setSelectedInvoice] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");

  const loadDashboardData = useCallback(async (showRefreshing = false) => {
    if (showRefreshing) setIsRefreshing(true);
    else setLoading(true);
    setError("");

    try {
      const [recRes, gstr3bRes, anomRes] = await Promise.all([
        api.getReconciliation(),
        api.getGstr3bSummary(),
        api.getAnomalies(),
      ]);

      setReconciliationData(recRes);
      setGstr3b(gstr3bRes);
      setAnomalies(anomRes?.items || []);
    } catch (err) {
      setError(err.message || "Failed to communicate with the GST reconciliation server.");
    } finally {
      setLoading(false);
      setIsRefreshing(false);
    }
  }, []);

  // Initial Auth Check
  useEffect(() => {
    const checkAuth = async () => {
      const token = authStorage.getToken();
      if (!token) {
        setIsAuthChecking(false);
        return;
      }

      try {
        const me = await api.getMe();
        setUser(me.user);
        setBusinesses(me.businesses || []);

        const savedBizId = authStorage.getActiveBusinessId();
        const found = me.businesses?.find((b) => String(b.id) === String(savedBizId));
        const initialBiz = found || me.businesses?.[0] || null;

        setActiveBusiness(initialBiz);
        if (initialBiz) {
          authStorage.setActiveBusinessId(initialBiz.id);
        }
      } catch {
        authStorage.clear();
        setUser(null);
      } finally {
        setIsAuthChecking(false);
      }
    };

    checkAuth();

    const handleUnauthorized = () => {
      setUser(null);
      setBusinesses([]);
      setActiveBusiness(null);
    };

    window.addEventListener("auth:unauthorized", handleUnauthorized);
    return () => window.removeEventListener("auth:unauthorized", handleUnauthorized);
  }, []);

  // When active business changes and user is authenticated, fetch dashboard data
  useEffect(() => {
    if (!user || !activeBusiness) return;
    let ignore = false;

    Promise.all([
      api.getReconciliation(),
      api.getGstr3bSummary(),
      api.getAnomalies(),
    ])
      .then(([recRes, gstr3bRes, anomRes]) => {
        if (!ignore) {
          setReconciliationData(recRes);
          setGstr3b(gstr3bRes);
          setAnomalies(anomRes?.items || []);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!ignore) {
          setError(err.message || "Failed to communicate with the GST reconciliation server.");
          setLoading(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, [user, activeBusiness]);

  const handleLoginSuccess = (userData, userBusinesses) => {
    setUser(userData);
    setBusinesses(userBusinesses || []);
    const initialBiz = userBusinesses?.[0] || null;
    setActiveBusiness(initialBiz);
    if (initialBiz) {
      authStorage.setActiveBusinessId(initialBiz.id);
    }
    setCurrentTab("dashboard");
  };

  const handleLogout = async () => {
    await api.logout();
    setUser(null);
    setBusinesses([]);
    setActiveBusiness(null);
    setReconciliationData(null);
    setGstr3b(null);
    setAnomalies([]);
  };

  const handleSelectBusiness = (biz) => {
    setActiveBusiness(biz);
    authStorage.setActiveBusinessId(biz.id);
  };

  const handleBusinessAdded = (newBiz) => {
    setBusinesses((prev) => [...prev, newBiz]);
  };

  if (isAuthChecking) {
    return (
      <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <LoadingSkeleton />
      </div>
    );
  }

  if (!user) {
    return <LoginPage onLoginSuccess={handleLoginSuccess} />;
  }

  const sales = reconciliationData?.sales || [];
  const purchases = reconciliationData?.purchases || [];

  return (
    <div className="app-container">
      {/* Sidebar Navigation */}
      <Sidebar
        currentTab={currentTab}
        setCurrentTab={setCurrentTab}
        anomalyCount={anomalies.length}
        user={user}
        activeBusiness={activeBusiness}
        onLogout={handleLogout}
      />

      {/* Main Content Area */}
      <div className="main-wrapper">
        <TopBar
          currentTab={currentTab}
          onRefresh={() => loadDashboardData(true)}
          isRefreshing={isRefreshing}
          searchQuery={searchQuery}
          setSearchQuery={setSearchQuery}
          onOpenNotifications={() => setCurrentTab("anomalies")}
          businesses={businesses}
          activeBusiness={activeBusiness}
          onSelectBusiness={handleSelectBusiness}
          onBusinessAdded={handleBusinessAdded}
          onLogout={handleLogout}
        />

        <main className="page-content">
          {loading ? (
            <LoadingSkeleton />
          ) : error ? (
            <ErrorState error={error} onRetry={() => loadDashboardData(false)} />
          ) : (
            <>
              {currentTab === "dashboard" && (
                <DashboardPage
                  data={reconciliationData}
                  gstr3b={gstr3b}
                  anomalies={anomalies}
                  onSelectInvoice={setSelectedInvoice}
                  onNavigate={setCurrentTab}
                />
              )}

              {currentTab === "sales" && (
                <SalesReconciliationPage
                  sales={sales}
                  onSelectInvoice={setSelectedInvoice}
                />
              )}

              {currentTab === "purchase" && (
                <PurchaseReconciliationPage
                  purchases={purchases}
                  onSelectInvoice={setSelectedInvoice}
                />
              )}

              {currentTab === "gstr3b" && (
                <Gstr3bPage
                  gstr3b={gstr3b}
                  sales={sales}
                  purchases={purchases}
                />
              )}

              {currentTab === "anomalies" && (
                <AnomaliesPage
                  anomalies={anomalies}
                />
              )}

              {currentTab === "invoices" && (
                <InvoicesPage
                  onSelectInvoice={setSelectedInvoice}
                />
              )}

              {currentTab === "upload" && (
                <UploadPage
                  onUploadSuccess={() => loadDashboardData(true)}
                />
              )}

              {currentTab === "reports" && (
                <ReportsPage />
              )}

              {currentTab === "settings" && (
                <SettingsPage />
              )}
            </>
          )}
        </main>
      </div>

      {/* Side-by-side Inspection Modal */}
      {selectedInvoice && (
        <InvoiceDetailModal
          invoice={selectedInvoice}
          onClose={() => setSelectedInvoice(null)}
        />
      )}
    </div>
  );
}

export default App;