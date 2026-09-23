import { useState, useMemo } from "react";
import { Eye, ArrowUpDown, ChevronLeft, ChevronRight } from "lucide-react";
import { StatusBadge } from "./StatusBadge";

export function ReconciliationTable({ records = [], onSelectInvoice, title, subtitle }) {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [gstinFilter, setGstinFilter] = useState("ALL");
  const [sortBy, setSortBy] = useState("invoice_no");
  const [sortOrder, setSortOrder] = useState("asc");
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 10;

  // Extract unique GSTINs for dropdown filter
  const uniqueGstins = useMemo(() => {
    const set = new Set();
    records.forEach((r) => {
      if (r.gstin) set.add(r.gstin);
    });
    return Array.from(set);
  }, [records]);

  // Filtering
  const filteredRecords = useMemo(() => {
    return records.filter((r) => {
      const matchesSearch =
        !search ||
        r.invoice_no?.toLowerCase().includes(search.toLowerCase()) ||
        r.gstin?.toLowerCase().includes(search.toLowerCase());

      const matchesStatus =
        statusFilter === "ALL" ||
        (statusFilter === "MATCH" && r.status === "MATCH") ||
        (statusFilter === "MISMATCH" && r.status === "MISMATCH") ||
        (statusFilter === "MISSING" && r.status.includes("MISSING")) ||
        (statusFilter === "EXTRA" && r.status.includes("EXTRA"));

      const matchesGstin = gstinFilter === "ALL" || r.gstin === gstinFilter;

      return matchesSearch && matchesStatus && matchesGstin;
    });
  }, [records, search, statusFilter, gstinFilter]);

  // Sorting
  const sortedRecords = useMemo(() => {
    return [...filteredRecords].sort((a, b) => {
      let aVal = a[sortBy];
      let bVal = b[sortBy];

      if (aVal === null || aVal === undefined) aVal = "";
      if (bVal === null || bVal === undefined) bVal = "";

      if (typeof aVal === "number" && typeof bVal === "number") {
        return sortOrder === "asc" ? aVal - bVal : bVal - aVal;
      }

      return sortOrder === "asc"
        ? String(aVal).localeCompare(String(bVal))
        : String(bVal).localeCompare(String(aVal));
    });
  }, [filteredRecords, sortBy, sortOrder]);

  // Pagination
  const totalPages = Math.ceil(sortedRecords.length / pageSize) || 1;
  const paginatedRecords = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return sortedRecords.slice(start, start + pageSize);
  }, [sortedRecords, currentPage, pageSize]);

  const handleSort = (field) => {
    if (sortBy === field) {
      setSortOrder(sortOrder === "asc" ? "desc" : "asc");
    } else {
      setSortBy(field);
      setSortOrder("asc");
    }
  };

  const formatCurrency = (val) => {
    if (val === null || val === undefined) return "—";
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR",
      maximumFractionDigits: 2,
    }).format(val);
  };

  return (
    <div className="card">
      <div className="card-header">
        <div>
          <h3 className="card-title">{title}</h3>
          {subtitle && <p className="card-subtitle">{subtitle}</p>}
        </div>
        <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
          Showing <strong>{sortedRecords.length}</strong> of {records.length} records
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="filter-bar">
        <div className="filter-left">
          <input
            type="text"
            className="filter-input"
            placeholder="Search invoice or GSTIN..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setCurrentPage(1);
            }}
          />

          <select
            className="filter-select"
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setCurrentPage(1);
            }}
          >
            <option value="ALL">All Statuses</option>
            <option value="MATCH">Matched</option>
            <option value="MISMATCH">Mismatched</option>
            <option value="MISSING">Missing in GST</option>
            <option value="EXTRA">Extra in GST</option>
          </select>

          <select
            className="filter-select"
            value={gstinFilter}
            onChange={(e) => {
              setGstinFilter(e.target.value);
              setCurrentPage(1);
            }}
          >
            <option value="ALL">All GSTINs</option>
            {uniqueGstins.map((gstin) => (
              <option key={gstin} value={gstin}>
                {gstin}
              </option>
            ))}
          </select>

          {(search || statusFilter !== "ALL" || gstinFilter !== "ALL") && (
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => {
                setSearch("");
                setStatusFilter("ALL");
                setGstinFilter("ALL");
                setCurrentPage(1);
              }}
            >
              Reset Filters
            </button>
          )}
        </div>
      </div>

      {/* Table Content */}
      <div className="table-wrapper">
        <table className="data-table">
          <thead>
            <tr>
              <th onClick={() => handleSort("invoice_no")} style={{ cursor: "pointer" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                  Invoice No <ArrowUpDown size={12} />
                </div>
              </th>
              <th onClick={() => handleSort("invoice_date")} style={{ cursor: "pointer" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                  Date <ArrowUpDown size={12} />
                </div>
              </th>
              <th>GSTIN</th>
              <th onClick={() => handleSort("taxable_value")} style={{ cursor: "pointer", textAlign: "right" }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 4 }}>
                  Taxable Value <ArrowUpDown size={12} />
                </div>
              </th>
              <th onClick={() => handleSort("gst_amount")} style={{ cursor: "pointer", textAlign: "right" }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 4 }}>
                  GST Amount <ArrowUpDown size={12} />
                </div>
              </th>
              <th>Status</th>
              <th style={{ textAlign: "right" }}>Difference</th>
              <th style={{ textAlign: "center" }}>Action</th>
            </tr>
          </thead>
          <tbody>
            {paginatedRecords.length === 0 ? (
              <tr>
                <td colSpan={8} className="empty-state">
                  No records match your filter criteria.
                </td>
              </tr>
            ) : (
              paginatedRecords.map((row) => {
                const diff = row.taxable_value_diff ?? row.gst_amount_diff;
                const hasDiff = diff !== null && diff !== undefined && diff !== 0;

                return (
                  <tr key={row.invoice_no}>
                    <td className="mono-cell" style={{ fontWeight: 600 }}>
                      {row.invoice_no}
                    </td>
                    <td>{row.invoice_date || "—"}</td>
                    <td className="mono-cell" style={{ color: "var(--slate-600)" }}>
                      {row.gstin || "—"}
                    </td>
                    <td style={{ textAlign: "right", fontWeight: 500 }}>
                      {formatCurrency(row.taxable_value)}
                    </td>
                    <td style={{ textAlign: "right", fontWeight: 500 }}>
                      {formatCurrency(row.gst_amount)}
                    </td>
                    <td>
                      <StatusBadge status={row.status} />
                    </td>
                    <td
                      style={{
                        textAlign: "right",
                        fontFamily: "var(--font-mono)",
                        color: hasDiff ? "#e11d48" : "var(--slate-500)",
                        fontWeight: hasDiff ? 700 : 400,
                      }}
                    >
                      {hasDiff ? formatCurrency(diff) : "₹0.00"}
                    </td>
                    <td style={{ textAlign: "center" }}>
                      <button
                        className="btn btn-secondary btn-sm"
                        title="Inspect reconciliation details"
                        onClick={() => onSelectInvoice(row)}
                      >
                        <Eye size={13} />
                        <span>Inspect</span>
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Controls */}
      {totalPages > 1 && (
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 16 }}>
          <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
            Page {currentPage} of {totalPages}
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            <button
              className="btn btn-secondary btn-sm"
              disabled={currentPage === 1}
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
            >
              <ChevronLeft size={14} /> Previous
            </button>
            <button
              className="btn btn-secondary btn-sm"
              disabled={currentPage === totalPages}
              onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
            >
              Next <ChevronRight size={14} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
