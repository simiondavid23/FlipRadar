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
        display: "flex", alignItems: "center", gap: "10px",
        padding: "11px 14px", marginTop: "14px",
        borderRadius: "12px",
        background:
          "linear-gradient(rgba(8,14,27,.72),rgba(8,14,27,.72)) padding-box, linear-gradient(135deg, rgba(248,113,113,.45), rgba(248,113,113,.06) 55%, transparent) border-box",
        border: "1px solid transparent",
        backdropFilter: "blur(20px)",
        color: "#fca5a5", fontSize: "12.5px",
      }}
    >
      <AlertTriangle style={{ width: "15px", height: "15px", flexShrink: 0 }} strokeWidth={1.8} />
      <span style={{ flex: 1 }}>{message}</span>
      {onRetry && (
        <button onClick={onRetry} className="btn-danger" style={{ padding: "6px 12px", fontSize: "11.5px" }}>
          <RefreshCw style={{ width: "12px", height: "12px" }} strokeWidth={2} />
          Reîncearcă
        </button>
      )}
    </div>
  );
}
