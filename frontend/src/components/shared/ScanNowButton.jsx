"use client";
import { Zap, RefreshCw } from "lucide-react";

// Buton primar "Scaneaza acum" (cyan-ghost), refolosit in feed-uri si in top bar.
// props: onScan — functie async; scanning — bool controlat de parinte; label — optional.
// Animatia `spin` este definita global in globals.css.
export default function ScanNowButton({ onScan, scanning, label = "Scanează acum" }) {
  const Icon = scanning ? RefreshCw : Zap;
  return (
    <button onClick={onScan} disabled={scanning} className="btn-cyan">
      <Icon
        style={{ width: "13px", height: "13px", animation: scanning ? "spin 1s linear infinite" : "none" }}
        strokeWidth={2}
      />
      {scanning ? "Se scanează…" : label}
    </button>
  );
}
