"use client";
// FlipRadar — banner de eroare discret pentru feed-uri (Radar / Auto / Imobiliare / Loturi).
// Vizibil DOAR cand `message` e setat; butonul reapeleaza loader-ul via onRetry.
import { AlertTriangle, RefreshCw } from "lucide-react";

export default function FeedErrorBanner({ message, onRetry }) {
  if (!message) return null;
  return (
    <div
      role="alert"
      style={{
        display: "flex", alignItems: "center", gap: "0.625rem",
        padding: "0.625rem 0.875rem", marginBottom: "1rem",
        backgroundColor: "rgba(220,38,38,0.08)",
        border: "1px solid rgba(220,38,38,0.35)",
        borderRadius: "0.5rem",
        color: "#fca5a5", fontSize: "0.8125rem",
      }}
    >
      <AlertTriangle style={{ width: "16px", height: "16px", flexShrink: 0 }} />
      <span style={{ flex: 1 }}>{message}</span>
      {onRetry && (
        <button
          onClick={onRetry}
          style={{
            display: "inline-flex", alignItems: "center", gap: "0.3rem",
            padding: "0.3rem 0.7rem",
            backgroundColor: "transparent",
            border: "1px solid rgba(220,38,38,0.45)",
            borderRadius: "0.375rem",
            color: "#fca5a5", fontSize: "0.75rem", fontWeight: 600,
            cursor: "pointer",
          }}
        >
          <RefreshCw style={{ width: "13px", height: "13px" }} />
          Reîncearcă
        </button>
      )}
    </div>
  );
}
