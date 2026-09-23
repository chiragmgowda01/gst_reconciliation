import { useState } from "react";
import { Building2, ChevronDown, Check, Plus, X } from "lucide-react";
import { api } from "../api/client";

export function BusinessSwitcher({ businesses = [], activeBusiness, onSelectBusiness, onBusinessAdded }) {
  const [isOpen, setIsOpen] = useState(false);
  const [showAddModal, setShowAddModal] = useState(false);
  const [newName, setNewName] = useState("");
  const [newGstin, setNewGstin] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSelect = (biz) => {
    onSelectBusiness(biz);
    setIsOpen(false);
  };

  const handleAddSubmit = async (e) => {
    e.preventDefault();
    if (!newName.trim() || !newGstin.trim()) {
      setError("Please provide both business name and 15-character GSTIN.");
      return;
    }
    setLoading(true);
    setError("");

    try {
      const added = await api.addBusiness(newName.trim(), newGstin.trim().toUpperCase());
      setNewName("");
      setNewGstin("");
      setShowAddModal(false);
      if (onBusinessAdded) onBusinessAdded(added);
      onSelectBusiness(added);
    } catch (err) {
      setError(err.message || "Failed to register business.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <div style={{ position: "relative" }}>
        <button
          className="btn btn-secondary"
          onClick={() => setIsOpen(!isOpen)}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "6px 12px",
            backgroundColor: "var(--slate-50)",
            borderColor: "var(--slate-200)",
            fontSize: 12.5,
            fontWeight: 600,
          }}
        >
          <Building2 size={15} color="#2563eb" />
          <div style={{ textAlign: "left", lineHeight: 1.2 }}>
            <div style={{ color: "var(--text-main)", maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {activeBusiness ? activeBusiness.name : "Select Business"}
            </div>
            {activeBusiness && (
              <div style={{ fontSize: 10, color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                {activeBusiness.gstin}
              </div>
            )}
          </div>
          <ChevronDown size={13} color="#64748b" style={{ marginLeft: 4 }} />
        </button>

        {isOpen && (
          <div
            style={{
              position: "absolute",
              top: "100%",
              right: 0,
              marginTop: 6,
              width: 280,
              backgroundColor: "#fff",
              borderRadius: "var(--radius-md)",
              boxShadow: "var(--shadow-xl)",
              border: "1px solid var(--border-color)",
              zIndex: 50,
              padding: "6px 0",
              animation: "fadeIn 0.15s ease",
            }}
          >
            <div style={{ padding: "8px 14px", fontSize: 11, fontWeight: 700, textTransform: "uppercase", color: "var(--text-muted)", letterSpacing: 0.5 }}>
              Your Registered Entities ({businesses.length})
            </div>

            <div style={{ maxHeight: 220, overflowY: "auto" }}>
              {businesses.map((biz) => {
                const isSelected = activeBusiness && activeBusiness.id === biz.id;
                return (
                  <div
                    key={biz.id}
                    onClick={() => handleSelect(biz)}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      padding: "8px 14px",
                      cursor: "pointer",
                      backgroundColor: isSelected ? "var(--primary-50)" : "transparent",
                      borderLeft: isSelected ? "3px solid var(--primary-600)" : "3px solid transparent",
                      transition: "background 0.1s ease",
                    }}
                    onMouseEnter={(e) => {
                      if (!isSelected) e.currentTarget.style.backgroundColor = "var(--slate-50)";
                    }}
                    onMouseLeave={(e) => {
                      if (!isSelected) e.currentTarget.style.backgroundColor = "transparent";
                    }}
                  >
                    <div>
                      <div style={{ fontSize: 13, fontWeight: isSelected ? 700 : 500, color: isSelected ? "var(--primary-700)" : "var(--text-main)" }}>
                        {biz.name}
                      </div>
                      <div style={{ fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>
                        {biz.gstin}
                      </div>
                    </div>
                    {isSelected && <Check size={14} color="#2563eb" />}
                  </div>
                );
              })}
            </div>

            <div style={{ borderTop: "1px solid var(--border-color)", marginTop: 6, padding: "6px 8px 2px" }}>
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => {
                  setIsOpen(false);
                  setShowAddModal(true);
                }}
                style={{ width: "100%", justifyContent: "center" }}
              >
                <Plus size={13} />
                <span>Add Another Business</span>
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Modal to Register Additional Business */}
      {showAddModal && (
        <div className="modal-overlay" onClick={() => setShowAddModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 460 }}>
            <div className="modal-header">
              <h3 className="modal-title">Link New Business Entity</h3>
              <button className="topbar-btn" onClick={() => setShowAddModal(false)}>
                <X size={16} />
              </button>
            </div>

            <form onSubmit={handleAddSubmit}>
              <div className="modal-body">
                {error && (
                  <div style={{ padding: "10px 12px", background: "var(--mismatch-bg)", border: "1px solid var(--mismatch-border)", borderRadius: 6, color: "var(--mismatch-text)", fontSize: 12.5, marginBottom: 14 }}>
                    {error}
                  </div>
                )}

                <div style={{ marginBottom: 14 }}>
                  <label style={{ display: "block", fontSize: 12.5, fontWeight: 600, marginBottom: 4 }}>
                    Business Legal Name
                  </label>
                  <input
                    type="text"
                    className="filter-input"
                    style={{ width: "100%" }}
                    placeholder="e.g. Apex Industrial Supplies"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    required
                  />
                </div>

                <div>
                  <label style={{ display: "block", fontSize: 12.5, fontWeight: 600, marginBottom: 4 }}>
                    Statutory GSTIN (15 characters)
                  </label>
                  <input
                    type="text"
                    className="filter-input mono-cell"
                    style={{ width: "100%", textTransform: "uppercase" }}
                    placeholder="29AAAAA0000A1Z5"
                    maxLength={15}
                    value={newGstin}
                    onChange={(e) => setNewGstin(e.target.value.toUpperCase())}
                    required
                  />
                </div>
              </div>

              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowAddModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={loading}>
                  {loading ? "Registering..." : "Add Business"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
