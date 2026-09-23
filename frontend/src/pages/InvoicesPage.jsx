import { useState, useEffect, useCallback } from "react";
import { Eye, ChevronLeft, ChevronRight, Database, Search } from "lucide-react";
import { api } from "../api/client";
import { LoadingSkeleton } from "../components/LoadingSkeleton";
import { ErrorState } from "../components/ErrorState";

export function InvoicesPage({ onSelectInvoice }) {
  const [invoices, setInvoices] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [source, setSource] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const limit = 15;

  const fetchInvoices = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await api.getInvoices({
        source: source || undefined,
        search: search || undefined,
        limit,
        offset: (page - 1) * limit,
      });
      setInvoices(res.items || []);
      setTotal(res.total || 0);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [source, search, page, limit]);

  useEffect(() => {
    let ignore = false;
    api.getInvoices({
      source: source || undefined,
      search: search || undefined,
      limit,
      offset: (page - 1) * limit,
    })
      .then((res) => {
        if (!ignore) {
          setInvoices(res.items || []);
          setTotal(res.total || 0);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!ignore) {
          setError(err.message);
          setLoading(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, [source, search, page, limit]);

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    setPage(1);
    fetchInvoices();
  };

  const totalPages = Math.ceil(total / limit) || 1;

  const formatCurrency = (val) => {
    if (val === null || val === undefined) return "—";
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR",
      maximumFractionDigits: 2,
    }).format(val);
  };

  return (
    <div className="animate-fade-in">
      <div className="card">
        <div className="card-header">
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ width: 36, height: 36, borderRadius: 8, background: "#eff6ff", color: "#2563eb", display: "flex", alignItems: "center", justifyContent: "center" }}>
              <Database size={18} />
            </div>
            <div>
              <h3 className="card-title">Database Invoice Records</h3>
              <p className="card-subtitle">
                Centralized PostgreSQL/Supabase ledger across all uploaded registers and returns
              </p>
            </div>
          </div>
          <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
            Total <strong>{total}</strong> records stored
          </div>
        </div>

        {/* Filter bar */}
        <form onSubmit={handleSearchSubmit} className="filter-bar">
          <div className="filter-left">
            <input
              type="text"
              className="filter-input"
              placeholder="Search invoice or GSTIN..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />

            <select
              className="filter-select"
              value={source}
              onChange={(e) => {
                setSource(e.target.value);
                setPage(1);
              }}
            >
              <option value="">All Sources</option>
              <option value="sales_register">Sales Register</option>
              <option value="gstr1">GSTR-1</option>
              <option value="purchase_register">Purchase Register</option>
              <option value="gstr2a">GSTR-2A</option>
            </select>

            <button type="submit" className="btn btn-secondary btn-sm">
              <Search size={13} />
              <span>Search</span>
            </button>

            {(search || source) && (
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => {
                  setSearch("");
                  setSource("");
                  setPage(1);
                  fetchInvoices();
                }}
              >
                Reset
              </button>
            )}
          </div>
        </form>

        {loading ? (
          <LoadingSkeleton />
        ) : error ? (
          <ErrorState error={error} onRetry={fetchInvoices} />
        ) : (
          <>
            <div className="table-wrapper">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Invoice No</th>
                    <th>Date</th>
                    <th>GSTIN</th>
                    <th>Source Type</th>
                    <th style={{ textAlign: "right" }}>Taxable Value</th>
                    <th style={{ textAlign: "right" }}>GST Amount</th>
                    <th style={{ textAlign: "center" }}>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {invoices.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="empty-state">
                        No invoice records found in database.
                      </td>
                    </tr>
                  ) : (
                    invoices.map((inv) => (
                      <tr key={inv.id}>
                        <td className="mono-cell" style={{ fontWeight: 600 }}>{inv.invoice_no}</td>
                        <td>{inv.invoice_date || "—"}</td>
                        <td className="mono-cell">{inv.gstin || "—"}</td>
                        <td>
                          <span style={{ fontSize: 12, padding: "2px 8px", background: "var(--slate-100)", borderRadius: 4, textTransform: "capitalize" }}>
                            {inv.source.replace(/_/g, " ")}
                          </span>
                        </td>
                        <td style={{ textAlign: "right", fontWeight: 500 }}>
                          {formatCurrency(inv.taxable_value)}
                        </td>
                        <td style={{ textAlign: "right", fontWeight: 500 }}>
                          {formatCurrency(inv.gst_amount)}
                        </td>
                        <td style={{ textAlign: "center" }}>
                          <button
                            className="btn btn-secondary btn-sm"
                            onClick={() => onSelectInvoice(inv)}
                          >
                            <Eye size={13} />
                            <span>View</span>
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 16 }}>
                <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
                  Showing page {page} of {totalPages}
                </div>
                <div style={{ display: "flex", gap: 6 }}>
                  <button
                    className="btn btn-secondary btn-sm"
                    disabled={page === 1}
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                  >
                    <ChevronLeft size={14} /> Previous
                  </button>
                  <button
                    className="btn btn-secondary btn-sm"
                    disabled={page === totalPages}
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  >
                    Next <ChevronRight size={14} />
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
