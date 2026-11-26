import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Eye, RefreshCw, Trash2 } from "lucide-react";
import { api } from "../api/client";

const formatDate = (value) => value ? new Date(value).toLocaleString() : "—";
const sourceLabel = (batch) => batch.source_category === "gst_simulator"
  ? `GST simulator · ${batch.source_type}`
  : batch.source_category === "csv_upload"
    ? `CSV · ${batch.source_type}`
    : "Legacy / untracked";

export function ImportHistoryPage({ onDataChanged }) {
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [sourceType, setSourceType] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [showDeleted, setShowDeleted] = useState(false);
  const [selected, setSelected] = useState(null);
  const [preview, setPreview] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const refresh = useCallback(async () => {
    setBusy(true);
    setError("");
    try {
      const data = await api.getImportBatches({
        limit: 20,
        offset,
        source_type: sourceType || undefined,
        status: statusFilter || undefined,
        include_deleted: showDeleted || statusFilter === "deleted",
      });
      setRows(data.items || []);
      setTotal(data.total || 0);
    } catch (err) {
      setError(err.message || "Import history could not be loaded.");
    } finally {
      setBusy(false);
    }
  }, [offset, sourceType, statusFilter, showDeleted]);

  useEffect(() => {
    const timer = window.setTimeout(() => refresh(), 0);
    return () => window.clearTimeout(timer);
  }, [refresh]);

  const openDetails = async (batch) => {
    setError("");
    try {
      setSelected(await api.getImportBatch(batch.batch_id));
    } catch (err) {
      setError(err.message || "Batch details could not be loaded.");
    }
  };

  const startDelete = async (batch) => {
    setError("");
    setNotice("");
    try {
      setSelected(await api.getImportBatch(batch.batch_id));
      setPreview(await api.previewImportBatchDeletion(batch.batch_id));
      setConfirmDelete(false);
    } catch (err) {
      setError(err.message || "Deletion preview could not be loaded.");
    }
  };

  const commitDelete = async () => {
    if (!selected || !confirmDelete) return;
    setBusy(true);
    setError("");
    try {
      await api.deleteImportBatch(selected.batch_id);
      setNotice("Import batch deleted. Its audit history remains available.");
      setPreview(null);
      setSelected(null);
      setConfirmDelete(false);
      await refresh();
      onDataChanged?.();
    } catch (err) {
      setError(err.message || "The batch could not be deleted.");
      // Refresh the preview because the underlying period may have changed.
      try { setPreview(await api.previewImportBatchDeletion(selected.batch_id)); } catch { /* keep original error */ }
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="page-section import-history-page">
      <div className="page-header">
        <div>
          <h1>Import History</h1>
          <p>Review imports saved to this business and safely remove an import batch.</p>
        </div>
        <button type="button" className="btn btn-secondary" onClick={refresh} disabled={busy}>
          <RefreshCw size={15} /> Refresh
        </button>
      </div>

      {error && <div className="alert alert-error" role="alert">{error}</div>}
      {notice && <div className="alert alert-success" role="status">{notice}</div>}

      <div className="card import-history-toolbar">
        <label>Data type
          <select value={sourceType} onChange={(event) => { setOffset(0); setSourceType(event.target.value); }}>
            <option value="">All types</option>
            <option value="sales_register">Sales register</option>
            <option value="gstr1">GSTR-1</option>
            <option value="purchase_register">Purchase register</option>
            <option value="gstr2a">GSTR-2A</option>
            <option value="gstr2b">GSTR-2B</option>
            <option value="gstr3b">GSTR-3B</option>
          </select>
        </label>
        <label>Status
          <select value={statusFilter} onChange={(event) => { setOffset(0); setStatusFilter(event.target.value); }}>
            <option value="">All statuses</option>
            <option value="in_progress">In progress</option>
            <option value="completed">Completed</option>
            <option value="partial">Partial</option>
            <option value="failed">Failed</option>
            <option value="deleted">Deleted</option>
          </select>
        </label>
        <label className="import-history-check">
          <input type="checkbox" checked={showDeleted} onChange={(event) => { setOffset(0); setShowDeleted(event.target.checked); }} />
          Show deleted batches
        </label>
        <span>{total} {total === 1 ? "batch" : "batches"}</span>
      </div>

      <div className="card import-history-table-wrap">
        {rows.length === 0 ? (
          <div className="empty-state">
            <h3>{busy ? "Loading import history…" : "No imports found"}</h3>
            {!busy && <p>CSV uploads and confirmed GST simulator imports will appear here.</p>}
          </div>
        ) : (
          <table className="data-table">
            <thead><tr><th>Imported</th><th>Source</th><th>File / fixture</th><th>Period</th><th>Rows</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody>{rows.map((batch) => (
              <tr key={batch.batch_id}>
                <td>{formatDate(batch.created_at)}</td>
                <td>{sourceLabel(batch)}</td>
                <td>{batch.original_filename || batch.fixture_identifier || "—"}</td>
                <td>{batch.tax_period || "—"}</td>
                <td>{batch.imported_rows} imported · {batch.duplicate_rows} duplicate · {batch.revised_rows || 0} revised · {batch.rejected_rows} rejected</td>
                <td><span className={`status-badge ${batch.status === "deleted" ? "status-muted" : ""}`}>{batch.status}</span></td>
                <td className="import-history-actions">
                  <button type="button" className="btn btn-secondary btn-sm" onClick={() => openDetails(batch)}><Eye size={14} /> Details</button>
                  {!batch.deleted_at && <button type="button" className="btn btn-danger btn-sm" onClick={() => startDelete(batch)}><Trash2 size={14} /> Delete</button>}
                </td>
              </tr>
            ))}</tbody>
          </table>
        )}
        <div className="import-history-pagination">
          <button type="button" className="btn btn-secondary btn-sm" disabled={offset === 0 || busy} onClick={() => setOffset((value) => Math.max(0, value - 20))}>Previous</button>
          <span>{total ? `${offset + 1}–${Math.min(offset + 20, total)} of ${total}` : "0 results"}</span>
          <button type="button" className="btn btn-secondary btn-sm" disabled={offset + 20 >= total || busy} onClick={() => setOffset((value) => value + 20)}>Next</button>
        </div>
      </div>

      {(selected || preview) && (
        <div className="modal-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) { setSelected(null); setPreview(null); } }}>
          <div className="modal-content import-history-modal" role="dialog" aria-modal="true" aria-labelledby="import-history-modal-title">
            <div className="modal-header"><h2 id="import-history-modal-title">{preview ? "Review batch deletion" : "Import details"}</h2><button type="button" className="modal-close" onClick={() => { setSelected(null); setPreview(null); }}>×</button></div>
            {selected && <div className="import-history-detail">
              <p><strong>Source:</strong> {sourceLabel(selected)}</p>
              <p><strong>File / fixture:</strong> {selected.original_filename || selected.fixture_identifier || "—"}</p>
              <p><strong>Tax period:</strong> {selected.tax_period || "—"}</p>
              <p><strong>Created:</strong> {formatDate(selected.created_at)} · <strong>Completed:</strong> {formatDate(selected.completed_at)}</p>
              <p><strong>Rows:</strong> {selected.imported_rows} imported, {selected.duplicate_rows} duplicate, {selected.revised_rows || 0} revised, {selected.rejected_rows} rejected</p>
              {selected.deleted_at && <p><strong>Deleted:</strong> {formatDate(selected.deleted_at)} · audit records retained</p>}
              {!preview && <div className="import-history-items"><h3>Row outcomes</h3>{selected.items?.length ? selected.items.map((item) => <div key={item.id} className="import-history-item"><span>{item.target_record_type} · {item.outcome}</span><span>{item.target_period || (item.invoice_id ? `Invoice #${item.invoice_id}` : item.rejection_reason || "Rejected row")}</span></div>) : <p>No row-level items were recorded for this batch.</p>}</div>}
            </div>}
            {preview && <div className="import-history-detail">
              {preview.can_delete ? <>
                <p>This action will soft-delete <strong>{preview.affected.invoice_count} invoice record(s)</strong>, soft-delete <strong>{preview.affected.gstr3b_originals.length} original GSTR-3B period(s)</strong>, and restore <strong>{preview.affected.gstr3b_revisions.length} prior revision(s)</strong> where safe.</p>
                <p>Duplicate references, rejected rows, and legacy untracked records are not removed. The batch and row audit history will be retained.</p>
                <label className="import-history-confirm"><input type="checkbox" checked={confirmDelete} onChange={(event) => setConfirmDelete(event.target.checked)} /> I reviewed this preview and confirm deleting this batch’s imported records.</label>
              </> : <div className="alert alert-warning"><AlertTriangle size={17} /> <div><strong>Deletion is blocked to protect newer data.</strong><ul>{preview.blocked_reasons?.map((reason) => <li key={reason}>{reason}</li>)}</ul></div></div>}
              <div className="import-history-modal-actions">
                <button type="button" className="btn btn-secondary" onClick={() => { setPreview(null); setConfirmDelete(false); }}>Cancel</button>
                {preview.can_delete && <button type="button" className="btn btn-danger" disabled={!confirmDelete || busy} onClick={commitDelete}><Trash2 size={15} /> {busy ? "Deleting…" : "Delete selected batch"}</button>}
              </div>
            </div>}
          </div>
        </div>
      )}
    </section>
  );
}
