"use client";
import { RefreshCw } from "lucide-react";

// Buton "Scaneaza acum" cu iconita RefreshCw + spinner, refolosit in feed-uri.
// props: onScan — functie async; scanning — bool controlat de parinte; label — optional.
// Necesita @keyframes spin definit in pagina parinte (ambele feed-uri il au inline).
export default function ScanNowButton({ onScan, scanning, label = "Scanează acum" }) {
  return (
    <button onClick={onScan} disabled={scanning} style={{
      display: "inline-flex", alignItems: "center", gap: "0.375rem", padding: "0.5rem 1rem",
      backgroundColor: scanning ? "rgba(37,99,235,0.08)" : "rgba(37,99,235,0.15)", color: "#60a5fa",
      border: "1px solid rgba(37,99,235,0.3)", borderRadius: "0.5rem", fontSize: "0.8125rem",
      fontWeight: 500, cursor: scanning ? "default" : "pointer", opacity: scanning ? 0.7 : 1, transition: "all 0.15s",
    }}>
      <RefreshCw style={{ width: "14px", height: "14px", animation: scanning ? "spin 1s linear infinite" : "none" }} />
      {scanning ? "Se scanează..." : label}
    </button>
  );
}
