import { useState, useMemo } from "react";
import { Eye, ArrowUpDown, ChevronLeft, ChevronRight, Search, Filter } from "lucide-react";
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
    <div className="institutional-card">
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
          <div className="search-input-wrapper">
            <Search size={14} color="#94a3b8" />
            <input
              type="text"
              className="filter-input-with-icon"
              placeholder="Search invoice or GSTIN..."
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setCurrentPage(1);
              }}
            />
          </div>

          <div className="filter-dropdown-wrapper">
            <Filter size={13} color="#94a3b8" />
            <select
              className="filter-select"
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setCurrentPage(1);
              }}
            >
              <option value="ALL">All Statuses</option>
              <option value="MATCH">MATCH Only</option>
              <option value="MISMATCH">MISMATCH Only</option>
              <option value="MISSING">MISSING IN GST Only</option>
              <option value="EXTRA">EXTRA IN GST Only</option>
            </select>
          </div>

          {uniqueGstins.length > 0 && (
            <select
              className="filter-select"
              value={gstinFilter}
              onChange={(e) => {
                setGstinFilter(e.target.value);
                setCurrentPage(1);
              }}
            >
              <option value="ALL">All Counterparties</option>
              {uniqueGstins.map((g) => (
                <option key={g} value={g}>
                  {g}
                </option>
              ))}
            </select>
          )}

          {(search || statusFilter !== "ALL" || gstinFilter !== "ALL") && (
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => {
                setSearch("");
                setStatusFilter("ALL");
                setGstinFilter("ALL");
                setCurrentPage(1);
              }}
            >
              Clear Filters
            </button>
          )}
        </div>
      </div>

      {/* Data Table */}
      <div className="table-wrapper">
        <table className="data-table">
          <thead>
            <tr>
              <th onClick={() => handleSort("invoice_no")} style={{ cursor: "pointer" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span>Invoice No</span>
                  <ArrowUpDown size={12} color="#94a3b8" />
                </div>
              </th>
              <th onClick={() => handleSort("invoice_date")} style={{ cursor: "pointer" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span>Date</span>
                  <ArrowUpDown size={12} color="#94a3b8" />
                </div>
              </th>
              <th>Counterparty GSTIN</th>
              <th onClick={() => handleSort("taxable_value")} style={{ textAlign: "right", cursor: "pointer" }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 6 }}>
                  <span>Taxable Value</span>
                  <ArrowUpDown size={12} color="#94a3b8" />
                </div>
              </th>
              <th onClick={() => handleSort("gst_amount")} style={{ textAlign: "right", cursor: "pointer" }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 6 }}>
                  <span>GST Amount</span>
                  <ArrowUpDown size={12} color="#94a3b8" />
                </div>
              </th>
              <th>Status</th>
              <th style={{ textAlign: "right" }}>Difference</th>
              <th style={{ textAlign: "center" }}>Inspect</th>
            </tr>
          </thead>
          <tbody>
            {paginatedRecords.length === 0 ? (
              <tr>
                <td colSpan={8} className="empty-state">
                  No records match the current search and filter criteria.
                </td>
              </tr>
            ) : (
              paginatedRecords.map((row, idx) => {
                const diff = row.taxable_value_diff ?? row.gst_amount_diff;
                const hasDiff = diff !== null && diff !== undefined && diff !== 0;

                return (
                  <tr
                    key={`${row.invoice_no || "inv"}-${row.status || ""}-${row.gstin || ""}-${idx}`}
                    onClick={() => onSelectInvoice && onSelectInvoice(row)}
                    style={{ cursor: onSelectInvoice ? "pointer" : "default" }}
                  >
                    <td className="mono-cell" style={{ fontWeight: 600 }}>
                      {row.invoice_no}
                    </td>
                    <td>{row.invoice_date || "—"}</td>
                    <td className="mono-cell">
                      <span className="gstin-tag">{row.gstin || "—"}</span>
                    </td>
                    <td style={{ textAlign: "right", fontFamily: "var(--font-mono)" }}>
                      {formatCurrency(row.taxable_value)}
                    </td>
                    <td style={{ textAlign: "right", fontFamily: "var(--font-mono)" }}>
                      {formatCurrency(row.gst_amount)}
                    </td>
                    <td>
                      <StatusBadge status={row.status} />
                    </td>
                    <td
                      style={{
                        textAlign: "right",
                        fontFamily: "var(--font-mono)",
                        fontWeight: hasDiff ? 700 : 400,
                        color: hasDiff ? "#dc2626" : "var(--text-muted)",
                      }}
                    >
                      {hasDiff ? formatCurrency(diff) : "—"}
                    </td>
                    <td style={{ textAlign: "center" }}>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={(e) => {
                          e.stopPropagation();
                          if (onSelectInvoice) onSelectInvoice(row);
                        }}
                      >
                        <Eye size={13} />
                        <span>View</span>
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
        <div className="pagination-bar">
          <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
            Page <strong>{currentPage}</strong> of <strong>{totalPages}</strong> ({sortedRecords.length} records)
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={currentPage === 1}
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
            >
              <ChevronLeft size={14} /> Previous
            </button>
            <button
              type="button"
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
