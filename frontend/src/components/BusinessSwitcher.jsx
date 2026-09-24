import { useState } from "react";
import { createPortal } from "react-dom";
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
            backgroundColor: "rgba(255, 255, 255, 0.9)",
            borderColor: "var(--border-color)",
            borderRadius: "var(--radius-md)",
            fontSize: 12.5,
            fontWeight: 600,
            boxShadow: "0 1px 3px rgba(0, 0, 0, 0.04)",
          }}
        >
          <Building2 size={15} color="#ea580c" />
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
              top: "calc(100% + 6px)",
              right: 0,
              width: 310,
              backgroundColor: "rgba(255, 255, 255, 0.98)",
              backdropFilter: "blur(16px)",
              WebkitBackdropFilter: "blur(16px)",
              borderRadius: "14px",
              boxShadow: "0 16px 36px -4px rgba(15, 23, 42, 0.14), 0 4px 12px rgba(0, 0, 0, 0.04)",
              border: "1px solid rgba(226, 232, 240, 0.9)",
              zIndex: 100,
              padding: "6px 0",
              animation: "fadeIn 0.15s ease",
            }}
          >
            <div style={{ padding: "10px 14px 6px", fontSize: 11, fontWeight: 700, textTransform: "uppercase", color: "#64748b", letterSpacing: "0.6px" }}>
              Your Registered Entities ({businesses.length})
            </div>

            <div style={{ maxHeight: 240, overflowY: "auto" }}>
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
                      padding: "9px 14px",
                      cursor: "pointer",
                      backgroundColor: isSelected ? "#fff7ed" : "transparent",
                      borderLeft: isSelected ? "3px solid #ea580c" : "3px solid transparent",
                      transition: "background 0.15s ease",
                    }}
                    onMouseEnter={(e) => {
                      if (!isSelected) e.currentTarget.style.backgroundColor = "#fffbf7";
                    }}
                    onMouseLeave={(e) => {
                      if (!isSelected) e.currentTarget.style.backgroundColor = "transparent";
                    }}
                  >
                    <div style={{ overflow: "hidden", paddingRight: 8 }}>
                      <div style={{ fontSize: 12.5, fontWeight: isSelected ? 700 : 500, color: isSelected ? "#c2410c" : "#1e293b", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                        {biz.name}
                      </div>
                      <div style={{ fontSize: 11, fontFamily: "var(--font-mono)", color: isSelected ? "#ea580c" : "#64748b" }}>
                        {biz.gstin}
                      </div>
                    </div>
                    {isSelected && <Check size={14} color="#ea580c" style={{ flexShrink: 0 }} />}
                  </div>
                );
              })}
            </div>

            <div style={{ borderTop: "1px solid #f1f5f9", marginTop: 4, padding: "8px 10px 4px" }}>
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => {
                  setIsOpen(false);
                  setShowAddModal(true);
                }}
                style={{
                  width: "100%",
                  justifyContent: "center",
                  borderRadius: "8px",
                  fontSize: 12,
                  fontWeight: 600,
                  gap: 6,
                }}
              >
                <Plus size={13} color="#ea580c" />
                <span>Add Another Business</span>
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Modal to Register Additional Business - Rendered via Portal for True Center Alignment */}
      {showAddModal &&
        createPortal(
          <div
            className="modal-overlay"
            onClick={() => setShowAddModal(false)}
            style={{
              position: "fixed",
              inset: 0,
              backgroundColor: "rgba(15, 23, 42, 0.45)",
              backdropFilter: "blur(8px)",
              WebkitBackdropFilter: "blur(8px)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              zIndex: 9999,
              padding: 20,
            }}
          >
            <div
              className="modal-content"
              onClick={(e) => e.stopPropagation()}
              style={{
                maxWidth: 520,
                width: "100%",
                borderRadius: 20,
                backgroundColor: "#ffffff",
                boxShadow: "0 24px 48px -12px rgba(15, 23, 42, 0.2), 0 8px 16px -4px rgba(0, 0, 0, 0.06)",
                border: "1px solid rgba(226, 232, 240, 0.9)",
                overflow: "hidden",
                animation: "fadeIn 0.2s ease",
              }}
            >
              <div className="modal-header" style={{ padding: "20px 24px", borderBottom: "1px solid #f1f5f9" }}>
                <div>
                  <h3 className="modal-title" style={{ fontSize: 16, fontWeight: 800, color: "#0f172a" }}>
                    Link New Business Entity
                  </h3>
                  <p style={{ fontSize: 12, color: "#64748b", marginTop: 2 }}>
                    Add a GSTIN to switch and reconcile separate business ledgers
                  </p>
                </div>
                <button
                  type="button"
                  className="topbar-btn"
                  onClick={() => setShowAddModal(false)}
                  style={{ width: 32, height: 32, borderRadius: 8 }}
                >
                  <X size={15} />
                </button>
              </div>

              <form onSubmit={handleAddSubmit}>
                <div className="modal-body" style={{ padding: "24px" }}>
                  {error && (
                    <div
                      style={{
                        padding: "10px 14px",
                        background: "var(--mismatch-bg)",
                        border: "1px solid var(--mismatch-border)",
                        borderRadius: 10,
                        color: "var(--mismatch-text)",
                        fontSize: 12.5,
                        marginBottom: 16,
                      }}
                    >
                      {error}
                    </div>
                  )}

                  <div style={{ marginBottom: 18 }}>
                    <label style={{ display: "block", fontSize: 12.5, fontWeight: 600, color: "#334155", marginBottom: 6 }}>
                      Business Legal Name
                    </label>
                    <input
                      type="text"
                      className="filter-input"
                      style={{
                        width: "100%",
                        height: 48,
                        borderRadius: 10,
                        padding: "0 14px",
                        fontSize: 13.5,
                        backgroundColor: "rgba(255, 255, 255, 0.9)",
                        border: "1px solid #e2e8f0",
                        color: "#0f172a",
                      }}
                      placeholder="e.g. Apex Industrial Supplies"
                      value={newName}
                      onChange={(e) => setNewName(e.target.value)}
                      required
                    />
                  </div>

                  <div>
                    <label style={{ display: "block", fontSize: 12.5, fontWeight: 600, color: "#334155", marginBottom: 6 }}>
                      Statutory GSTIN (15 characters)
                    </label>
                    <input
                      type="text"
                      className="filter-input mono-cell"
                      style={{
                        width: "100%",
                        height: 48,
                        borderRadius: 10,
                        padding: "0 14px",
                        fontSize: 13.5,
                        textTransform: "uppercase",
                        backgroundColor: "rgba(255, 255, 255, 0.9)",
                        border: "1px solid #e2e8f0",
                        color: "#0f172a",
                      }}
                      placeholder="29AAAAA0000A1Z5"
                      maxLength={15}
                      value={newGstin}
                      onChange={(e) => setNewGstin(e.target.value.toUpperCase())}
                      required
                    />
                  </div>
                </div>

                <div
                  className="modal-footer"
                  style={{
                    padding: "16px 24px",
                    borderTop: "1px solid #f1f5f9",
                    backgroundColor: "#fafafa",
                    display: "flex",
                    justifyContent: "flex-end",
                    gap: 10,
                  }}
                >
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => setShowAddModal(false)}
                    style={{ height: 44, padding: "0 18px", borderRadius: 10, fontSize: 13, fontWeight: 600 }}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="btn btn-primary"
                    disabled={loading}
                    style={{ height: 44, padding: "0 22px", borderRadius: 10, fontSize: 13, fontWeight: 700 }}
                  >
                    {loading ? "Registering..." : "Add Business"}
                  </button>
                </div>
              </form>
            </div>
          </div>,
          document.body
        )}
    </>
  );
}
