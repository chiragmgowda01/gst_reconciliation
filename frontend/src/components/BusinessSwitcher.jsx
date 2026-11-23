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
            backgroundColor: "#ffffff",
            borderColor: "var(--border-color)",
            borderRadius: "var(--radius-md)",
            fontSize: 12.5,
            fontWeight: 600,
            boxShadow: "var(--shadow-xs)",
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
              Registered Entities ({businesses.length})
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
                      backgroundColor: isSelected ? "#eff6ff" : "transparent",
                      borderLeft: isSelected ? "3px solid #2563eb" : "3px solid transparent",
                      transition: "background 0.15s ease",
                    }}
                    onMouseEnter={(e) => {
                      if (!isSelected) e.currentTarget.style.backgroundColor = "#f8fafc";
                    }}
                    onMouseLeave={(e) => {
                      if (!isSelected) e.currentTarget.style.backgroundColor = "transparent";
                    }}
                  >
                    <div style={{ overflow: "hidden", paddingRight: 8 }}>
                      <div style={{ fontSize: 12.5, fontWeight: isSelected ? 700 : 500, color: isSelected ? "#1d4ed8" : "#1e293b", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                        {biz.name}
                      </div>
                      <div style={{ fontSize: 11, fontFamily: "var(--font-mono)", color: isSelected ? "#2563eb" : "#64748b" }}>
                        {biz.gstin}
                      </div>
                    </div>
                    {isSelected && <Check size={14} color="#2563eb" style={{ flexShrink: 0 }} />}
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
                <Plus size={14} color="#2563eb" />
                <span>Register New Entity</span>
              </button>
            </div>
          </div>
        )}
      </div>

      {showAddModal &&
        createPortal(
          <div
            style={{
              position: "fixed",
              inset: 0,
              backgroundColor: "rgba(15, 23, 42, 0.55)",
              backdropFilter: "blur(6px)",
              WebkitBackdropFilter: "blur(6px)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              zIndex: 9999,
              padding: 16,
              animation: "fadeIn 0.15s ease",
            }}
          >
            <div
              style={{
                backgroundColor: "#ffffff",
                borderRadius: "16px",
                width: "100%",
                maxWidth: 440,
                boxShadow: "0 24px 48px -12px rgba(15, 23, 42, 0.25)",
                border: "1px solid #e2e8f0",
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "18px 22px",
                  borderBottom: "1px solid #f1f5f9",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <div
                    style={{
                      width: 32,
                      height: 32,
                      borderRadius: "8px",
                      backgroundColor: "#eff6ff",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      color: "#2563eb",
                    }}
                  >
                    <Building2 size={16} />
                  </div>
                  <h3 style={{ fontSize: 16, fontWeight: 700, color: "#0f172a", margin: 0 }}>
                    Register Business Entity
                  </h3>
                </div>
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  style={{
                    background: "none",
                    border: "none",
                    color: "#94a3b8",
                    cursor: "pointer",
                    padding: 4,
                    display: "flex",
                    borderRadius: "6px",
                  }}
                >
                  <X size={18} />
                </button>
              </div>

              <form onSubmit={handleAddSubmit} style={{ padding: "20px 22px" }}>
                {error && (
                  <div
                    style={{
                      padding: "8px 12px",
                      backgroundColor: "#fef2f2",
                      border: "1px solid #fca5a5",
                      borderRadius: "8px",
                      color: "#dc2626",
                      fontSize: 12.5,
                      marginBottom: 16,
                    }}
                  >
                    {error}
                  </div>
                )}

                <div style={{ marginBottom: 14 }}>
                  <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#475569", marginBottom: 6 }}>
                    Entity / Legal Business Name
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Apex Industrial Solutions Ltd"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    style={{
                      width: "100%",
                      height: 40,
                      padding: "0 12px",
                      border: "1px solid #cbd5e1",
                      borderRadius: "8px",
                      fontSize: 13,
                      boxSizing: "border-box",
                      outline: "none",
                    }}
                  />
                </div>

                <div style={{ marginBottom: 20 }}>
                  <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#475569", marginBottom: 6 }}>
                    15-digit GSTIN
                  </label>
                  <input
                    type="text"
                    required
                    maxLength={15}
                    placeholder="e.g. 29AAAAA1111A1Z5"
                    value={newGstin}
                    onChange={(e) => setNewGstin(e.target.value.toUpperCase())}
                    style={{
                      width: "100%",
                      height: 40,
                      padding: "0 12px",
                      border: "1px solid #cbd5e1",
                      borderRadius: "8px",
                      fontSize: 13,
                      fontFamily: "var(--font-mono)",
                      boxSizing: "border-box",
                      outline: "none",
                    }}
                  />
                </div>

                <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => setShowAddModal(false)}
                    disabled={loading}
                    style={{ height: 38, fontSize: 12.5 }}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="btn btn-primary"
                    disabled={loading}
                    style={{ height: 38, fontSize: 12.5, gap: 6 }}
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
export default BusinessSwitcher;
