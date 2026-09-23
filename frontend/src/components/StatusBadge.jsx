import { CheckCircle2, AlertTriangle, AlertCircle, HelpCircle, ShieldAlert } from "lucide-react";

export function StatusBadge({ status }) {
  if (!status) return null;
  const s = String(status).toUpperCase();

  if (s === "MATCH") {
    return (
      <span className="badge badge-match">
        <CheckCircle2 size={12} />
        MATCH
      </span>
    );
  }

  if (s === "MISMATCH") {
    return (
      <span className="badge badge-mismatch">
        <AlertCircle size={12} />
        MISMATCH
      </span>
    );
  }

  if (s.includes("MISSING")) {
    return (
      <span className="badge badge-missing">
        <AlertTriangle size={12} />
        MISSING IN GST
      </span>
    );
  }

  if (s.includes("EXTRA")) {
    return (
      <span className="badge badge-extra">
        <HelpCircle size={12} />
        EXTRA IN GST
      </span>
    );
  }

  if (s === "HIGH") {
    return (
      <span className="badge badge-high">
        <ShieldAlert size={12} />
        HIGH
      </span>
    );
  }

  if (s === "MEDIUM") {
    return (
      <span className="badge badge-medium">
        <AlertTriangle size={12} />
        MEDIUM
      </span>
    );
  }

  if (s === "LOW") {
    return (
      <span className="badge badge-low">
        <AlertCircle size={12} />
        LOW
      </span>
    );
  }

  return <span className="badge badge-low">{status}</span>;
}
